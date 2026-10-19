"""Counterfactual covariance analysis (spec §14) and factor Shapley attribution.

Both re-solve the full constrained problem with the target pressure h held
fixed and only the covariance changed:

    x^(k) = argmin_{x in C}  1/2 x^T Sigma^(k) x - h_target^T x

Every covariance variant keeps the production asset volatilities (removed
factor variance is moved into the diagonal), so the ladder and the Shapley
players isolate correlation structure, not changes in vol.

Ladder:   x^(K) = x^(0) + sum_k dx^(k),  dx^(k) = x^(k) - x^(k-1)   (telescoping, exact)
Shapley:  x(all) - x(none) = sum_f phi_f                              (efficiency, exact)
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import factorial
from typing import Sequence

import numpy as np
import pandas as pd

from .problem import Optimizer, Solution

DEFAULT_LADDER = (
    ("Volatility only", ()),
    ("Factor covariance", ("style",)),
    ("Enriched residual", ("style", "sector", "country")),
    ("Production", ("style", "sector", "country", "pair")),
)


@dataclass
class LadderResult:
    weights: pd.DataFrame     # (N, rungs) x^(k)
    steps: pd.DataFrame       # (N, rungs) x^(0), dx^(1), ..., dx^(K)
    summary: pd.DataFrame
    solutions: list[Solution]

    def telescoping_error(self) -> float:
        return float(np.abs(self.steps.sum(axis=1) - self.weights.iloc[:, -1]).max())

    def stock(self, stock: str) -> pd.Series:
        return self.steps.loc[stock]


def covariance_ladder(opt: Optimizer, ladder: Sequence[tuple[str, Sequence[str]]] = DEFAULT_LADDER,
                      reference: Solution | None = None) -> LadderResult:
    base = opt.cov
    sigma_prod = base.dense()
    sols, rows = [], []
    for label, groups in ladder:
        cov = base.restrict(base.column_mask(groups=groups))
        sol = opt.solve(cov)
        x = sol.x.to_numpy()
        sols.append(sol)
        rows.append({
            "Rung": label,
            "TE (own cov)": float(np.sqrt(x @ cov.dense() @ x)),
            "TE (production cov)": float(np.sqrt(x @ sigma_prod @ x)),
            "Active share": 0.5 * np.abs(x).sum(),
            "Binding sources": sum(v == "binding" for v in sol.status.values()),
            "Solve s": sol.solve_seconds,
        })
    labels = [lbl for lbl, _ in ladder]
    W = pd.concat([s.x.rename(lbl) for s, lbl in zip(sols, labels)], axis=1)
    steps = W.diff(axis=1)
    steps.iloc[:, 0] = W.iloc[:, 0]
    steps.columns = [labels[0]] + [f"d {lbl}" for lbl in labels[1:]]
    summary = pd.DataFrame(rows).set_index("Rung")
    summary["Gross |dx|"] = [np.abs(steps.iloc[:, k]).sum() for k in range(len(labels))]
    if reference is not None:
        summary.attrs["final_vs_reference"] = float(np.abs(W.iloc[:, -1] - reference.x).max())
    return LadderResult(weights=W, steps=steps, summary=summary, solutions=sols)


@dataclass
class ShapleyResult:
    players: list[str]
    phi: pd.DataFrame          # (N, players)
    x_none: pd.Series
    x_all: pd.Series
    n_solves: int

    def efficiency_error(self) -> float:
        return float(np.abs(self.phi.sum(axis=1) - (self.x_all - self.x_none)).max())

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Gross |phi|": self.phi.abs().sum(),
            "Net phi": self.phi.sum(),
            "Max |phi|": self.phi.abs().max(),
        })


def factor_shapley(opt: Optimizer, players: Sequence[str] | None = None,
                   player_group: str = "style") -> ShapleyResult:
    """Exact Shapley over covariance columns (default: the style factors).

    Non-player columns stay at production; coalition S switches on Phi[S, S]
    of the players. Cost: 2^|players| solves.
    """
    base = opt.cov
    if players is None:
        players = [c for c, g in zip(base.columns, base.groups) if g == player_group]
    players = list(players)
    n = len(players)
    is_player = base.column_mask(columns=players)
    fixed = ~is_player

    cache: dict[frozenset, np.ndarray] = {}

    def value(S: frozenset) -> np.ndarray:
        if S not in cache:
            keep = fixed | base.column_mask(columns=S)
            cache[S] = opt.solve(base.restrict(keep)).x.to_numpy()
        return cache[S]

    phi = np.zeros((base.n, n))
    for k, p in enumerate(players):
        others = [q for q in players if q != p]
        for size in range(n):
            wgt = factorial(size) * factorial(n - size - 1) / factorial(n)
            for S in combinations(others, size):
                S = frozenset(S)
                phi[:, k] += wgt * (value(S | {p}) - value(S))

    ids = opt.u.ids
    return ShapleyResult(
        players=players,
        phi=pd.DataFrame(phi, index=ids, columns=players),
        x_none=pd.Series(value(frozenset()), index=ids),
        x_all=pd.Series(value(frozenset(players)), index=ids),
        n_solves=len(cache),
    )
