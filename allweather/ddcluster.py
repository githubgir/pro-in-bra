"""(c) Drawdown-anchored classification.

1. Take the N deepest peak-to-trough drawdowns of the US equity market (non-overlapping).
2. For every industry and every All Weather reference asset, compute its beta-adjusted excess return
   in each episode: sum over episode months of (r - rf) - beta * (r_m - rf), beta from monthly OLS.
   Industry profiles (and the cyclical-equity anchor, itself an industry basket) are demeaned across
   industries within each episode, so the comparison is about relative behaviour, not about the
   equal-weighted industry average beating the cap-weighted market in some crashes.
3. Each quadrant has an anchor profile across the episodes, built from Bridgewater's asset mapping:
       GD_IU (q1) precious metals & TIPS   GU_IU (q2) other commodities
       GD_ID (q3) government bonds         GU_ID (q4) cyclical equities
4. An industry joins the quadrant whose anchor profile it is most correlated with across episodes.
"""
import numpy as np
import pandas as pd

from .analytics import wealth

ANCHORS = {"GD_IU": ["Gold", "TIPS"], "GU_IU": ["Commodities"], "GD_ID": ["Treasuries"], "GU_ID": ["Cyclicals"]}
ANCHOR_LABEL = {"GD_IU": "Precious metals & TIPS", "GU_IU": "Other commodities",
                "GD_ID": "Government bonds", "GU_ID": "Cyclical equities"}


def market_drawdowns(mkt, n=10, start="1970-01", end=None, completed_before=None):
    """N deepest non-overlapping drawdowns: list of (peak, trough, recovery, depth). Episode = peak+1 .. trough."""
    r = mkt.loc[start:end].dropna()
    w = wealth(r)
    peak_val, peak_t = w.iloc[0], w.index[0]
    eps, cur = [], None
    for t, v in w.items():
        if v >= peak_val:
            if cur is not None:
                eps.append({**cur, "recovery": t})
                cur = None
            peak_val, peak_t = v, t
        else:
            dd = v / peak_val - 1
            if cur is None:
                cur = {"peak": peak_t, "trough": t, "depth": dd}
            elif dd < cur["depth"]:
                cur.update(trough=t, depth=dd)
    if cur is not None:
        eps.append({**cur, "recovery": None})
    df = pd.DataFrame(eps)
    if completed_before is not None:
        df = df[df.trough < completed_before]
    return df.sort_values("depth").head(n).sort_values("peak").reset_index(drop=True)


def betas(rets, mkt, rf, start=None, end=None):
    ex = rets.sub(rf, axis=0).loc[start:end]
    m = (mkt - rf).loc[start:end]
    out = {}
    for c in ex.columns:
        ok = ex[c].notna() & m.notna()
        if ok.sum() < 36:
            continue
        out[c] = np.cov(ex[c][ok], m[ok])[0, 1] / m[ok].var()
    return pd.Series(out)


def episode_returns(rets, mkt, rf, episodes, beta, exante=None):
    """Beta-adjusted excess return of each column in each episode (NaN if data missing).

    exante: if an int W, beta is re-estimated per episode on the W months before the peak
    (residual = r - beta_t * r_m, beta known before the drawdown started)."""
    rows = {}
    for _, e in episodes.iterrows():
        sl = slice(e.peak + 1, e.trough)
        if exante:
            beta = betas(rets, mkt, rf, e.peak - exante + 1, e.peak).reindex(rets.columns)
        ex = rets.loc[sl].sub(rf.loc[sl], axis=0)
        mx = (mkt - rf).loc[sl]
        a = ex.sub(np.outer(mx.values, beta.reindex(rets.columns).values), axis=0)
        val = a.sum(min_count=1)
        val[ex.isna().any()] = np.nan          # require the full episode
        rows[f"{e.peak.strftime('%Y-%m')}→{e.trough.strftime('%Y-%m')}"] = val
    return pd.DataFrame(rows)


def anchor_profiles(asset_ep):
    """Quadrant anchor = mean of its assets' episode profiles, each asset scaled to unit cross-episode std."""
    prof = {}
    for q, names in ANCHORS.items():
        z = asset_ep.loc[names]
        z = z.div(z.std(axis=1), axis=0)
        prof[q] = z.mean(axis=0, skipna=True)
    return pd.DataFrame(prof)


def classify(ind_ep, anchors):
    """Correlation of each industry's episode profile with each anchor -> scores and quadrant."""
    corr = pd.DataFrame({q: ind_ep.T.corrwith(anchors[q]) for q in anchors.columns})
    ok = ind_ep.notna().sum(axis=1) >= 5
    corr = corr[ok]
    return corr, corr.idxmax(axis=1)


def assign_from_corr(corr):
    """Quadrant dict; empty quadrants borrow the industry with the highest correlation to that anchor."""
    lab = corr.idxmax(axis=1)
    q = {k: list(lab.index[lab == k]) for k in ANCHORS}
    for k in q:
        if not q[k]:
            q[k] = [corr[k].idxmax()]
    return q


def fit(ind, assets, mkt, rf, n=10, start="1970-01", end=None, completed_before=None, demean=True, beta_adjust=True, exante=None):
    eps = market_drawdowns(mkt, n, start, end, completed_before)
    stop = end if completed_before is None else completed_before - 1
    b_i = betas(ind, mkt, rf, start, stop)
    b_a = betas(assets, mkt, rf, start, stop)
    if not beta_adjust:                     # plain excess-of-market returns instead
        b_i[:] = 1.0
        b_a[:] = 1.0
    ind_ep = episode_returns(ind[b_i.index], mkt, rf, eps, b_i, exante)
    ast_ep = episode_returns(assets, mkt, rf, eps, b_a, exante)
    if demean:
        # remove the episode's common industry component (e.g. equal-weight beating cap-weight in 2000-02)
        xs_mean = ind_ep.mean(axis=0)
        ind_ep = ind_ep - xs_mean
        ast_ep.loc["Cyclicals"] = ast_ep.loc["Cyclicals"] - xs_mean
    anchors = anchor_profiles(ast_ep)
    corr, lab = classify(ind_ep, anchors)
    return {"episodes": eps, "beta_ind": b_i, "beta_ast": b_a, "ind_ep": ind_ep, "ast_ep": ast_ep,
            "anchors": anchors, "corr": corr, "label": lab, "quads": assign_from_corr(corr)}


def rolling_quads(ind, assets, mkt, rf, first_year=2000, last_year=None, n=10, start="1970-01", **kw):
    """Out-of-sample: every January re-fit using only drawdowns whose trough is before that January."""
    last_year = last_year or ind.index[-1].year
    fits = {y: fit(ind, assets, mkt, rf, n, start, completed_before=pd.Period(f"{y}-01", "M"), **kw)
            for y in range(first_year, last_year + 1)}
    cache = {y: f["quads"] for y, f in fits.items()}
    return (lambda t: cache[max(first_year, min(t.year, last_year))]), fits


def hedged_returns(rets, mkt, rf, window=60, min_obs=36):
    """Beta-hedged industry returns: r_i - beta_i,t * (r_m - rf), beta from the trailing window to t-1.
    Long the industry, short beta x market (futures-style, so the cash return stays in)."""
    ex, m = rets.sub(rf, axis=0), mkt - rf
    cov = ex.rolling(window, min_periods=min_obs).cov(m)
    var = m.rolling(window, min_periods=min_obs).var()
    beta = cov.div(var, axis=0).shift(1)
    return rets.sub(beta.mul(m, axis=0)), beta
