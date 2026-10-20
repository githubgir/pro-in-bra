"""Synthetic TE-minimisation problem with a factor risk model, used by the example and tests."""

from __future__ import annotations

import cvxpy as cp
import numpy as np


def build_problem(n=60, n_style=3, n_country=3, n_industry=4, max_w=0.05, band=0.01,
                  signal_target=0.5, seed=0):
    rng = np.random.default_rng(seed)
    country = rng.integers(0, n_country, n)
    industry = rng.integers(0, n_industry, n)
    Xc = np.eye(n_country)[country]
    Xi = np.eye(n_industry)[industry]
    style = rng.standard_normal((n, n_style))
    B = np.hstack([np.ones((n, 1)), style, Xc, Xi])
    k = B.shape[1]
    vols_f = np.r_[0.16, np.full(n_style, 0.04), np.full(n_country, 0.06), np.full(n_industry, 0.05)]
    corr_f = 0.2 * np.ones((k, k)) + 0.8 * np.eye(k)
    F = corr_f * np.outer(vols_f, vols_f)
    D = rng.uniform(0.15, 0.35, n) ** 2

    mcap = rng.lognormal(0, 1.2, n)
    b = mcap / mcap.sum()
    s = rng.standard_normal(n)
    s = (s - b @ s) / s.std()  # benchmark-neutral signal z-score

    w = cp.Variable(n, name="w")
    a = w - b
    y = cp.Variable(k, name="y")  # factor exposures; definitional, gets dropped by the attribution
    cons = {
        "budget": cp.sum(w) == 1,
        "long_only": w >= 0,
        "signal": s @ a == signal_target,
        "max_weight": w <= max_w,
        "country": [Xc.T @ a <= band, Xc.T @ a >= -band],
        "industry": [Xi.T @ a <= band, Xi.T @ a >= -band],
    }
    flat = [c for v in cons.values() for c in (v if isinstance(v, list) else [v])]
    objective = cp.quad_form(y, F) + cp.sum_squares(cp.multiply(np.sqrt(D), a))
    prob = cp.Problem(cp.Minimize(objective), flat + [y == B.T @ a])

    labels = {
        "country": [f"C{j} hi" for j in range(n_country)] + [f"C{j} lo" for j in range(n_country)],
        "industry": [f"I{j} hi" for j in range(n_industry)] + [f"I{j} lo" for j in range(n_industry)],
    }
    return dict(problem=prob, w=w, b=b, B=B, F=F, D=D, groups=cons, row_labels=labels, signal=s)
