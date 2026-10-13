"""Quadrant and All-Weather portfolio construction (monthly rebalanced, long-only)."""
import numpy as np
import pandas as pd

from .classify import QUADS

WINDOW = 60       # months of history for vol / covariance
MIN_OBS = 36      # an industry needs this much history to be held
SHRINK = 0.2      # shrink sample covariance toward its diagonal


def erc_weights(cov, tol=1e-10, max_iter=2000):
    """Equal-risk-contribution weights via cyclical coordinate descent (Griveau-Billion et al. 2013)."""
    S = np.asarray(cov, float)
    n = len(S)
    if n == 1:
        return np.ones(1)
    w = 1 / np.sqrt(np.diag(S))
    w /= w.sum()
    for _ in range(max_iter):
        w_old = w.copy()
        for i in range(n):
            b = S[i] @ w - S[i, i] * w[i]
            w[i] = (-b + np.sqrt(b * b + 4 * S[i, i] / n)) / (2 * S[i, i])
        if np.abs(w - w_old).max() < tol:
            break
    return w / w.sum()


def _scheme_weights(hist, scheme):
    if scheme == "EW":
        return np.full(hist.shape[1], 1 / hist.shape[1])
    if scheme == "IV":
        w = 1 / hist.std().values
        return w / w.sum()
    if scheme == "ERC":
        S = hist.cov().values
        S = (1 - SHRINK) * S + SHRINK * np.diag(np.diag(S))
        return erc_weights(S)
    raise ValueError(scheme)


def quad_returns(rets, quads_at, within="EW", warmup="1931-01", end=None):
    """Monthly returns of the four quadrant portfolios and the industry weights inside them.

    rets     : monthly industry total returns (PeriodIndex M), NaN where missing
    quads_at : callable(period) -> dict quad -> list[industry]; membership known at formation
    within   : EW | IV | ERC weighting of industries inside each quadrant
    Weights at t use only returns up to t-1. Built from `warmup` so that across-quadrant
    risk models have history when reporting starts.
    """
    idx = rets.loc[warmup:end].index
    qret = pd.DataFrame(index=idx, columns=QUADS, dtype=float)
    ind_w = {q: {} for q in QUADS}
    for t in idx:
        pos = rets.index.get_loc(t)
        hist = rets.iloc[max(0, pos - WINDOW):pos]
        r_t = rets.loc[t]
        members = quads_at(t)
        for q in QUADS:
            cand = [c for c in members[q] if hist[c].tail(MIN_OBS).notna().all() and pd.notna(r_t[c])]
            if not cand:
                continue
            w = _scheme_weights(hist[cand].dropna(how="all"), within)
            ind_w[q][t] = pd.Series(w, index=cand)
            qret.loc[t, q] = float(np.dot(w, r_t[cand]))
    return qret, ind_w


def combine(qret, ind_w, across="EW", start="1952-01", end=None):
    """Combine quadrant portfolios into All Weather. Returns dict aw, quads, qw, w."""
    out_idx = qret.loc[start:end].index
    qw = pd.DataFrame(index=out_idx, columns=QUADS, dtype=float)
    aw = pd.Series(index=out_idx, dtype=float)
    rows = {}
    for t in out_idx:
        pos = qret.index.get_loc(t)
        hist = qret.iloc[max(0, pos - WINDOW):pos]
        avail = [q for q in QUADS if pd.notna(qret.loc[t, q]) and hist[q].tail(MIN_OBS).notna().all()]
        w = _scheme_weights(hist[avail], across)
        qw.loc[t, avail] = w
        aw[t] = float(np.dot(w, qret.loc[t, avail]))
        tot = pd.Series(dtype=float)
        for q, wq in zip(avail, w):
            tot = tot.add(ind_w[q][t] * wq, fill_value=0)
        rows[t] = tot
    W = pd.DataFrame(rows).T.fillna(0.0)
    return {"aw": aw, "quads": qret.loc[start:end], "w": W, "qw": qw}


def build(rets, quads_at, within="EW", across="EW", start="1952-01", end=None, warmup="1931-01"):
    qret, ind_w = quad_returns(rets, quads_at, within, warmup, end)
    return combine(qret, ind_w, across, start, end)


def static(quad_map):
    return lambda t: quad_map


def turnover(W, rets):
    """Average annual one-way turnover accounting for drift between rebalances."""
    R = rets.reindex(index=W.index, columns=W.columns).fillna(0)
    drift = W * (1 + R)
    drift = drift.div(drift.sum(axis=1), axis=0).shift(1)
    return 0.5 * (W - drift).abs().sum(axis=1).iloc[1:].mean() * 12
