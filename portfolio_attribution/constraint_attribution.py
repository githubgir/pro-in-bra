"""Attribution of tracking-error-minimising active weights to linear constraints.

Given a solved cvxpy problem

    min_w (w - b)' Sigma (w - b)   s.t.  linear equality / inequality constraints on w

this module explains the active weights a* = w* - b by

1. KKT decomposition (exact, additive):
       a* = sum_k a_k,     a_k = -1/2 Sigma^{-1} C_k' mu_k
       TE^2 = sum_k 1/2 mu_k' g_k(b)            (dual x constraint value at the benchmark)
2. Counterfactual on/off re-solves:
       leave-one-out  a*(all) - a*(all but k)
       add-one-in     a*(fixed + k) - a*(fixed)
3. Risk-model variants (full factor model -> constant correlation -> constant
   correlation and vol), with the weight differences read as a waterfall.

The maths is in docs/constraint_attribution.md.  Sign convention is cvxpy's: every
constraint is held as g(w) = lhs - rhs (<= 0 or == 0) with Lagrangian f + mu' g(w).
"""

from __future__ import annotations

import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np
import pandas as pd
import scipy.sparse as sp
from cvxpy.constraints import Equality, Inequality

from .risk import (
    LowRankDiagCov,
    average_correlation,
    average_vol,
    constant_correlation_cov,
    constant_correlation_vol_cov,
)

VARIANTS = ("full", "avg_corr", "avg_corr_vol")
_DEFAULT_SOLVE = {"solver": cp.CLARABEL, "tol_gap_abs": 1e-10, "tol_gap_rel": 1e-10, "tol_feas": 1e-10}


@dataclass
class _Group:
    name: str
    constraints: list
    C: sp.csr_matrix  # (m, N) Jacobian of g w.r.t. w
    g_bench: np.ndarray  # g(b), the constraint value at the benchmark
    is_eq: np.ndarray  # (m,) bool
    labels: list[str]


@dataclass
class _Solution:
    w: np.ndarray
    a: np.ndarray
    te2: float
    duals: dict[str, np.ndarray]


@dataclass
class KKTAttribution:
    """Exact additive decomposition of one solved problem."""

    te: float
    weights: pd.DataFrame  # N x (groups + residual + total): a_k per constraint group
    risk: pd.DataFrame  # per group: te2 contribution, te contribution, share
    rows: pd.DataFrame  # per constraint row: dual, value at benchmark/solution, sensitivities


@dataclass
class Counterfactual:
    """On/off re-solves for one risk model."""

    weights: pd.DataFrame  # N x groups (+ interaction for leave-one-out)
    summary: pd.DataFrame  # per group: TE with / without, delta


@dataclass
class AttributionReport:
    rho_bar: float
    vol_bar: float
    corr_weighting: object
    active_weights: pd.DataFrame  # benchmark + active weights per variant
    waterfall: pd.DataFrame  # avg_corr_vol + vol dispersion + correlation = full
    te: pd.DataFrame  # TE of each variant portfolio, under its own and the full model
    kkt: dict[str, KKTAttribution] = field(default_factory=dict)
    leave_one_out: dict[str, Counterfactual] = field(default_factory=dict)
    add_one_in: dict[str, Counterfactual] = field(default_factory=dict)


class ConstraintAttribution:
    """
    Parameters
    ----------
    problem : cvxpy.Problem
        Your TE-minimisation problem.  Only its constraints are used; the objective is
        rebuilt from (B, F, D) so all variants share one, known scaling.  Constraints
        that involve variables other than ``w`` (e.g. ``y == B.T @ (w - b)`` used to
        define the risk term) are treated as risk-model plumbing and dropped.
    w : cvxpy.Variable
        The (N,) holdings variable.  Long-only / bounds must be explicit constraints
        (``w >= 0``), not variable attributes, so that they have duals.
    benchmark : array (N,)
    B, F, D : factor exposures (N, K), factor covariance (K, K), specific variances (N,)
    groups : dict[str, Constraint | list[Constraint]], optional
        Named constraint groups (e.g. {"budget": c0, "signal": c1, "country": [c2, c3]}).
        Default: one group per constraint of ``problem``, named c0, c1, ...
    fixed : iterable of group names
        Groups that are never switched off in the counterfactuals (typically budget and
        long-only).  They are still attributed in the KKT decomposition.
    asset_names : sequence, optional
    row_labels : dict[str, list[str]], optional
        Labels for the rows of a group, e.g. {"country": ["US lo", "US hi", ...]}.
    solve_kwargs : dict, optional
        Passed to ``Problem.solve``.  Default: Clarabel with tight tolerances (accurate
        duals matter here).
    """

    def __init__(
        self,
        problem: cp.Problem,
        w: cp.Variable,
        benchmark,
        B,
        F,
        D,
        groups: dict | None = None,
        fixed=(),
        asset_names=None,
        row_labels: dict | None = None,
        solve_kwargs: dict | None = None,
    ):
        if w.ndim != 1:
            raise ValueError("w must be a 1-D cvxpy Variable")
        bad_attrs = [k for k in ("nonneg", "nonpos", "bounds", "boolean", "integer") if w.attributes.get(k)]
        if bad_attrs:
            raise ValueError(
                f"w has attributes {bad_attrs}; express them as explicit constraints (e.g. w >= 0) "
                "so they carry a dual value"
            )
        self.problem = problem
        self.w = w
        self.n = w.shape[0]
        self.b = np.asarray(benchmark, float).ravel()
        if self.b.shape != (self.n,):
            raise ValueError("benchmark must have the same length as w")
        self.cov = LowRankDiagCov.from_factor_model(B, F, D)
        self.asset_names = pd.Index(asset_names if asset_names is not None else range(self.n), name="asset")
        self.solve_kwargs = dict(_DEFAULT_SOLVE if solve_kwargs is None else solve_kwargs)
        self._user_w = None if w.value is None else np.array(w.value, float)

        with self._preserve_w():
            self.groups = self._build_groups(groups, row_labels or {})
        self.fixed = list(fixed)
        unknown = set(self.fixed) - set(self.groups)
        if unknown:
            raise ValueError(f"fixed groups not found: {sorted(unknown)}")

    # ------------------------------------------------------------------ setup

    @contextmanager
    def _preserve_w(self):
        saved = None if self.w.value is None else np.array(self.w.value)
        try:
            yield
        finally:
            self.w.value = saved

    def _depends_only_on_w(self, con) -> bool:
        return all(v.id == self.w.id for v in con.variables())

    def _build_groups(self, groups, row_labels) -> dict[str, _Group]:
        all_cons = list(self.problem.constraints)
        if groups is None:
            named = {f"c{i}": [c] for i, c in enumerate(all_cons) if self._depends_only_on_w(c)}
        else:
            named = {k: (list(v) if isinstance(v, (list, tuple)) else [v]) for k, v in groups.items()}
            seen = {c.id for cs in named.values() for c in cs}
            leftover = [c for c in all_cons if c.id not in seen and self._depends_only_on_w(c)]
            if leftover:
                warnings.warn(f"{len(leftover)} constraint(s) on w not in `groups`; attributed as 'other'", stacklevel=3)
                named["other"] = leftover
        dropped = [c for c in all_cons if not self._depends_only_on_w(c)]
        if dropped:
            warnings.warn(
                f"dropping {len(dropped)} constraint(s) that involve variables other than w "
                "(assumed to define the risk term; the objective is rebuilt from B, F, D)",
                stacklevel=3,
            )

        self.w.value = self.b  # gradients of affine expressions are constant; values give g(b)
        out = {}
        for name, cons in named.items():
            Cs, gs, eqs = [], [], []
            for con in cons:
                if not isinstance(con, (Equality, Inequality)):
                    raise TypeError(f"group '{name}': only linear == / <= / >= constraints are supported, got {type(con).__name__}")
                if not self._depends_only_on_w(con):
                    raise ValueError(f"group '{name}': constraints must depend on w only")
                if not con.expr.is_affine():
                    raise ValueError(f"group '{name}': constraint is not affine in w")
                J = con.expr.grad.get(self.w)
                g = np.atleast_1d(np.asarray(con.expr.value, float)).ravel(order="F")
                C = sp.csr_matrix((g.size, self.n)) if J is None else sp.csr_matrix(J).T
                Cs.append(C)
                gs.append(g)
                eqs.append(np.full(g.size, isinstance(con, Equality)))
            g_all = np.concatenate(gs)
            labels = list(row_labels.get(name, [f"{name}[{j}]" for j in range(g_all.size)]))
            if len(labels) != g_all.size:
                raise ValueError(f"row_labels['{name}'] has {len(labels)} labels for {g_all.size} rows")
            out[name] = _Group(name, cons, sp.vstack(Cs).tocsr(), g_all, np.concatenate(eqs), labels)
        return out

    # ------------------------------------------------------------- core solve

    def covariance(self, variant: str, corr_weighting="equal") -> LowRankDiagCov:
        if variant == "full":
            return self.cov
        rho = average_correlation(self.cov, corr_weighting, self.b)
        if variant == "avg_corr":
            return constant_correlation_cov(self.cov, rho)
        if variant == "avg_corr_vol":
            vol = average_vol(self.cov, corr_weighting, self.b, rho_bar=rho)
            return constant_correlation_vol_cov(self.n, rho, vol)
        raise ValueError(f"variant must be one of {VARIANTS}")

    def solve(self, cov: LowRankDiagCov, group_names=None) -> _Solution:
        names = list(self.groups) if group_names is None else list(group_names)
        cons = [c for g in names for c in self.groups[g].constraints]
        with self._preserve_w():
            prob = cp.Problem(cp.Minimize(cov.cvx_variance(self.w - self.b)), cons)
            prob.solve(**self.solve_kwargs)
            if prob.status == cp.OPTIMAL_INACCURATE:
                warnings.warn(f"solver returned optimal_inaccurate for groups {names}", stacklevel=2)
            elif prob.status != cp.OPTIMAL:
                raise RuntimeError(f"solve failed ({prob.status}) for groups {names}")
            w = np.array(self.w.value, float)
            # read duals now: constraint objects are shared between re-solves
            duals = {g: np.concatenate([np.atleast_1d(np.asarray(c.dual_value, float)).ravel(order="F")
                                        for c in self.groups[g].constraints]) for g in names}
        a = w - self.b
        return _Solution(w, a, cov.quad(a), duals)

    def consistency_check(self) -> float | None:
        """max |w_yours - w_rebuilt| if the problem you passed was already solved."""
        if self._user_w is None:
            return None
        return float(np.max(np.abs(self._user_w - self.solve(self.cov).w)))

    # -------------------------------------------------------- KKT attribution

    def kkt(self, cov: LowRankDiagCov | None = None, sol: _Solution | None = None, active_tol=1e-7) -> KKTAttribution:
        cov = self.cov if cov is None else cov
        sol = self.solve(cov) if sol is None else sol
        te = np.sqrt(sol.te2)

        a_k, risk, rows = {}, {}, []
        for name, grp in self.groups.items():
            mu = sol.duals[name]
            a_k[name] = -0.5 * cov.solve(grp.C.T @ mu)
            te2_rows = 0.5 * mu * grp.g_bench
            risk[name] = te2_rows.sum()
            g_sol = grp.g_bench + grp.C @ sol.a
            rows.append(pd.DataFrame({
                "group": name,
                "type": np.where(grp.is_eq, "==", "<="),
                "dual": mu,
                "g_at_benchmark": grp.g_bench,
                "g_at_solution": g_sol,
                "active": grp.is_eq | (np.abs(g_sol) < active_tol),
                "te2_contrib": te2_rows,
                "te_contrib": te2_rows / te if te > 0 else 0.0,
                # shifting g by +delta (tightening a <= row) raises TE^2 by mu*delta
                "dTE2_d_tighten": mu,
                "dTE_d_tighten": mu / (2 * te) if te > 0 else np.nan,
            }, index=pd.Index(grp.labels, name="row")))

        weights = pd.DataFrame(a_k, index=self.asset_names)
        weights["residual"] = sol.a - weights.sum(axis=1)
        weights["total"] = sol.a
        risk = pd.DataFrame({"te2_contrib": pd.Series(risk)})
        risk["te_contrib"] = risk["te2_contrib"] / te if te > 0 else 0.0
        risk["share"] = risk["te2_contrib"] / sol.te2 if sol.te2 > 0 else 0.0
        risk.loc["total"] = [sol.te2, te, risk["share"].sum()]
        return KKTAttribution(te, weights, risk, pd.concat(rows))

    def row_weight_contributions(self, group: str, cov: LowRankDiagCov | None = None,
                                 sol: _Solution | None = None) -> pd.DataFrame:
        """a_k split by individual rows of a group (e.g. one column per country band)."""
        cov = self.cov if cov is None else cov
        sol = self.solve(cov) if sol is None else sol
        grp = self.groups[group]
        mu = sol.duals[group]
        M = grp.C.T.multiply(mu[None, :]).toarray()  # column j = C_j' mu_j
        return pd.DataFrame(-0.5 * cov.solve(M), index=self.asset_names, columns=grp.labels)

    # --------------------------------------------------------- counterfactuals

    def _switchable(self) -> list[str]:
        return [g for g in self.groups if g not in self.fixed]

    def leave_one_out(self, cov: LowRankDiagCov | None = None, sol: _Solution | None = None) -> Counterfactual:
        """Contribution of k = a*(all) - a*(all but k).  Not additive: see 'interaction'."""
        cov = self.cov if cov is None else cov
        sol = self.solve(cov) if sol is None else sol
        cols, summ = {}, {}
        for k in self._switchable():
            s = self.solve(cov, [g for g in self.groups if g != k])
            cols[k] = sol.a - s.a
            summ[k] = (np.sqrt(sol.te2), np.sqrt(s.te2))
        weights = pd.DataFrame(cols, index=self.asset_names)
        weights["interaction"] = sol.a - weights.sum(axis=1)
        weights["total"] = sol.a
        summary = pd.DataFrame(summ, index=["te_with", "te_without"]).T
        summary["delta_te"] = summary["te_with"] - summary["te_without"]
        return Counterfactual(weights, summary)

    def add_one_in(self, cov: LowRankDiagCov | None = None) -> Counterfactual:
        """Contribution of k = a*(fixed + k) - a*(fixed)."""
        cov = self.cov if cov is None else cov
        base = self.solve(cov, self.fixed)
        cols, summ = {}, {}
        for k in self._switchable():
            s = self.solve(cov, self.fixed + [k])
            cols[k] = s.a - base.a
            summ[k] = (np.sqrt(s.te2), np.sqrt(base.te2))
        weights = pd.DataFrame(cols, index=self.asset_names)
        weights["fixed_only"] = base.a
        summary = pd.DataFrame(summ, index=["te_with", "te_without"]).T
        summary["delta_te"] = summary["te_with"] - summary["te_without"]
        return Counterfactual(weights, summary)

    # ------------------------------------------------------------- full report

    def run(self, corr_weighting="equal", variants=VARIANTS, counterfactuals=True) -> AttributionReport:
        """KKT + counterfactual attribution under the full and simplified risk models.

        corr_weighting : "equal" | "cap" | "implied" | array of pair weights
            How rho_bar (and vol_bar) are averaged; see docs/constraint_attribution.md.
        """
        rho = average_correlation(self.cov, corr_weighting, self.b)
        vol = average_vol(self.cov, corr_weighting, self.b, rho_bar=rho)
        covs = {v: self.covariance(v, corr_weighting) for v in variants}
        sols = {v: self.solve(c) for v, c in covs.items()}

        active = pd.DataFrame({v: s.a for v, s in sols.items()}, index=self.asset_names)
        active.insert(0, "benchmark", self.b)

        waterfall = pd.DataFrame(index=self.asset_names)
        if set(VARIANTS) <= set(sols):
            waterfall["constraint_geometry"] = sols["avg_corr_vol"].a
            waterfall["vol_dispersion"] = sols["avg_corr"].a - sols["avg_corr_vol"].a
            waterfall["correlation_structure"] = sols["full"].a - sols["avg_corr"].a
            waterfall["total"] = sols["full"].a

        te = pd.DataFrame({
            "te_own_model": {v: np.sqrt(s.te2) for v, s in sols.items()},
            "te_full_model": {v: np.sqrt(self.cov.quad(s.a)) for v, s in sols.items()},
        })

        report = AttributionReport(rho, vol, corr_weighting, active, waterfall, te)
        for v in variants:
            report.kkt[v] = self.kkt(covs[v], sols[v])
            if counterfactuals:
                report.leave_one_out[v] = self.leave_one_out(covs[v], sols[v])
                report.add_one_in[v] = self.add_one_in(covs[v])
        return report
