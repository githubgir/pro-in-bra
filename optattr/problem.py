"""Active-weight QP with named targets and named constraint blocks.

    min_x  1/2 x^T Sigma x - h_target^T x,   h_target = lambda * sum_m theta_m s_m
    s.t.   every block  A_k x (+ aux terms)  <= / ==  c_k

The canonical convention (verified in tests, and matching CVXPY) is

    Sigma x - h_target + sum_k A_k^T mu_k = 0     =>   h_constraint,k = -A_k^T mu_k

where A_k holds only the x-columns of block k. Auxiliary variables (turnover,
active-share splits) never enter Sigma x = h; their own stationarity conditions
only tie the linking-row duals to the budget-row dual.

The problem is built once with CVXPY parameters for (Phi^1/2, sqrt d, h), so
counterfactual and Shapley covariance variants re-solve without re-canonicalising.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Literal

import cvxpy as cp
import numpy as np
import pandas as pd
import scipy.sparse as sp

from .covariance import CovModel
from .universe import Universe

DEFAULT_TARGETS = {
    "Value": 1.0, "Momentum": 0.8, "Quality": 0.8, "Profitability": 0.5,
    "LowVol": 0.4, "Growth": 0.2, "Size": -0.3, "Market": 0.0, "Alpha": 1.0,
}
DEFAULT_BANDS = {
    "Market": (-0.05, 0.05), "Value": (-0.30, 0.30), "Growth": (-0.30, 0.30),
    "Momentum": (-0.30, 0.30), "Quality": (-0.30, 0.30), "Size": (-0.20, 0.20),
    "LowVol": (-0.30, 0.30), "Profitability": (-0.30, 0.30),
}


@dataclass(frozen=True)
class PortfolioSpec:
    risk_aversion: float = 0.004            # lambda: scales all target pressures
    targets: dict = field(default_factory=lambda: dict(DEFAULT_TARGETS))
    stock_max: float = 0.015                # w_i <= stock_max
    active_bound: float = 0.0075            # |w_i - b_i| <= active_bound
    sector_active: float = 0.02             # |sum_{i in s} x_i| <= sector_active
    country_active: float = 0.015
    exposure_bands: dict = field(default_factory=lambda: dict(DEFAULT_BANDS))
    turnover_oneway: float | None = 0.10    # 1/2 sum |w - w0| <= T
    active_share_max: float | None = 0.25   # 1/2 sum |w - b|  <= AS
    objective_scale: float = 1e4            # numerical scaling; duals are unscaled
    solver: str = "CLARABEL"
    solver_opts: dict = field(default_factory=lambda: {
        "tol_gap_abs": 1e-10, "tol_gap_rel": 1e-10, "tol_feas": 1e-10, "max_iter": 500})
    dual_tol: float = 1e-7                  # |mu| above this (unscaled) => binding


@dataclass
class Block:
    """One CVXPY constraint object = a set of rows with a stable attribution name."""
    source: str                         # attribution source it rolls up into
    name: str                           # row-family name, e.g. "Sector max"
    rows: list[str]                     # row labels
    A: sp.csr_matrix                    # (rows, N) x-coefficients
    sense: Literal["le", "eq"]
    con: cp.Constraint | None = None


@dataclass
class Solution:
    x: pd.Series
    w: pd.Series
    target_pressure: dict[str, np.ndarray]       # source -> h^(r)
    constraint_pressure: dict[str, np.ndarray]   # source -> h^(r)
    status: dict[str, str]                       # source -> target/binding/inactive/equality
    row_duals: dict[str, pd.Series]              # block name -> per-row mu
    block_source: dict[str, str]                 # block name -> source
    max_violation: float                         # primal feasibility
    dual_tol: float
    cov: CovModel
    solver_status: str
    solve_seconds: float

    @property
    def pressures(self) -> dict[str, np.ndarray]:
        return {**self.target_pressure, **self.constraint_pressure}

    @property
    def h(self) -> np.ndarray:
        return sum(self.pressures.values())


class Optimizer:
    def __init__(self, universe: Universe, spec: PortfolioSpec, cov: CovModel | None = None):
        self.u, self.spec = universe, spec
        self.cov = cov if cov is not None else universe.cov
        n, K = self.u.n, self.cov.X.shape[1]
        b = self.u.b.to_numpy()

        self.x = cp.Variable(n, name="x")
        self.L = cp.Parameter((K, K), name="Phi_sqrt")
        self.sqrt_d = cp.Parameter(n, nonneg=True, name="sqrt_d")
        self.h = cp.Parameter(n, name="h_target")

        # f = X^T x as its own variable keeps the solver's KKT system sparse;
        # its linking equality carries no attribution (stationarity in f gives
        # its dual = -Phi f, which folds back into Sigma x exactly).
        f = cp.Variable(K, name="f")
        risk = 0.5 * (cp.sum_squares(self.L.T @ f) + cp.sum_squares(cp.multiply(self.sqrt_d, self.x)))
        objective = cp.Minimize(spec.objective_scale * (risk - self.h @ self.x))

        self.blocks = self._build_blocks(b)
        link = f == self.cov.X.T @ self.x
        self.problem = cp.Problem(objective, [link] + [blk.con for blk in self.blocks])
        self.target_pressure = self._targets(self.u.scores)

    # ------------------------------------------------------------------ build
    def _targets(self, scores: pd.DataFrame) -> dict[str, np.ndarray]:
        lam = self.spec.risk_aversion
        return {f"Target: {k}": lam * th * scores[k].to_numpy()
                for k, th in self.spec.targets.items() if th != 0.0}

    def _build_blocks(self, b: np.ndarray) -> list[Block]:
        s, u, x, n = self.spec, self.u, self.x, self.u.n
        ids = list(u.ids)
        I = sp.identity(n, format="csr")
        blocks: list[Block] = []

        def add(source, name, rows, A, rhs, sense="le", aux=None):
            A = sp.csr_matrix(A)
            lhs = A @ x + (aux if aux is not None else 0)
            con = (lhs == rhs) if sense == "eq" else (lhs <= rhs)
            blocks.append(Block(source, name, rows, A, sense, con))

        add("Budget", "Budget", ["sum w = 1"], np.ones((1, n)), np.zeros(1), sense="eq")
        add("Non-negativity", "Non-negativity", ids, -I, b)
        add("Stock max", "Stock max", ids, I, s.stock_max - b)
        add("Active-weight bound", "Active-weight upper", ids, I, np.full(n, s.active_bound))
        add("Active-weight bound", "Active-weight lower", ids, -I, np.full(n, s.active_bound))

        for grp, lim, label in ((u.sector, s.sector_active, "Sector"),
                                (u.country, s.country_active, "Country")):
            names = sorted(grp.unique())
            G = np.array([(grp == g).to_numpy(float) for g in names])
            add(f"{label} max", f"{label} max", names, G, np.full(len(names), lim))
            add(f"{label} min", f"{label} min", names, -G, np.full(len(names), lim))

        for fac, (lo, hi) in s.exposure_bands.items():
            e = u.styles[fac].to_numpy()[None, :]
            add(f"Exposure band: {fac}", f"{fac} exposure max", [fac], e, np.array([hi]))
            add(f"Exposure band: {fac}", f"{fac} exposure min", [fac], -e, np.array([-lo]))

        if s.turnover_oneway is not None:
            if u.w0 is None:
                raise ValueError("turnover constraint needs prior holdings w0 (Universe.with_prior)")
            dw0 = u.w0.to_numpy() - b          # w - w0 = x - dw0
            t = cp.Variable(n, nonneg=True, name="trade")
            add("Turnover", "Turnover buy link", ids, I, dw0, aux=-t)
            add("Turnover", "Turnover sell link", ids, -I, -dw0, aux=-t)
            add("Turnover", "Turnover budget", ["1/2 sum|w-w0|"], sp.csr_matrix((1, n)),
                np.array([2 * s.turnover_oneway]), aux=cp.sum(t, keepdims=True))

        if s.active_share_max is not None:
            a = cp.Variable(n, nonneg=True, name="abs_active")
            zero = np.zeros(n)
            add("Active share", "Active share upper link", ids, I, zero, aux=-a)
            add("Active share", "Active share lower link", ids, -I, zero, aux=-a)
            add("Active share", "Active share budget", ["1/2 sum|w-b|"], sp.csr_matrix((1, n)),
                np.array([2 * s.active_share_max]), aux=cp.sum(a, keepdims=True))
        return blocks

    # ------------------------------------------------------------------ solve
    def solve(self, cov: CovModel | None = None, h_target: dict[str, np.ndarray] | None = None) -> Solution:
        cov = cov if cov is not None else self.cov
        if cov.X.shape != self.cov.X.shape or not np.array_equal(cov.X, self.cov.X):
            raise ValueError("covariance variants must share the optimizer's X columns")
        targets = h_target if h_target is not None else self.target_pressure

        self.L.value = cov.phi_sqrt()
        self.sqrt_d.value = np.sqrt(cov.d)
        self.h.value = sum(targets.values())

        t0 = time.perf_counter()
        self.problem.solve(solver=self.spec.solver, **self.spec.solver_opts)
        elapsed = time.perf_counter() - t0
        if self.problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            raise RuntimeError(f"solver failed: {self.problem.status}")

        k = 1.0 / self.spec.objective_scale
        pressures: dict[str, np.ndarray] = {}
        binding: dict[str, bool] = {}
        equality: dict[str, bool] = {}
        row_duals: dict[str, pd.Series] = {}
        for blk in self.blocks:
            mu = np.atleast_1d(blk.con.dual_value) * k
            row_duals[blk.name] = pd.Series(mu, index=blk.rows)
            pressures[blk.source] = pressures.get(blk.source, 0) - blk.A.T @ mu
            equality[blk.source] = equality.get(blk.source, False) or blk.sense == "eq"
            binding[blk.source] = binding.get(blk.source, False) or bool(np.any(np.abs(mu) > self.spec.dual_tol))

        status = {name: "target" for name in targets}
        for src in pressures:
            status[src] = "equality" if equality[src] else ("binding" if binding[src] else "inactive")

        x = pd.Series(self.x.value, index=self.u.ids, name="active")
        return Solution(
            x=x, w=(self.u.b + x).rename("weight"),
            target_pressure={k_: np.asarray(v) for k_, v in targets.items()},
            constraint_pressure={k_: np.asarray(v).ravel() for k_, v in pressures.items()},
            status=status, row_duals=row_duals,
            block_source={blk.name: blk.source for blk in self.blocks},
            max_violation=max(float(np.max(blk.con.violation())) for blk in self.blocks),
            dual_tol=self.spec.dual_tol, cov=cov,
            solver_status=self.problem.status, solve_seconds=elapsed,
        )


def prior_holdings(universe: Universe, spec: PortfolioSpec) -> pd.Series:
    """Last period's portfolio: same mandate, prior signals, no turnover limit."""
    opt = Optimizer(universe, replace(spec, turnover_oneway=None))
    sol = opt.solve(h_target=opt._targets(universe.prior_scores))
    w0 = sol.w.clip(lower=0.0)
    return (w0 / w0.sum()).rename("prior")
