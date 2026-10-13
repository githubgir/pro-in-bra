"""Performance, risk and drawdown analytics."""
import numpy as np
import pandas as pd


def wealth(r):
    return (1 + r.fillna(0)).cumprod()


def drawdown(r):
    w = wealth(r)
    return w / w.cummax() - 1


def stats(r, rf, mkt=None):
    r = r.dropna()
    rf = rf.reindex(r.index)
    ex = r - rf
    n = len(r) / 12
    cagr = wealth(r).iloc[-1] ** (1 / n) - 1
    vol = r.std() * np.sqrt(12)
    down = ex[ex < 0].std() * np.sqrt(12)
    dd = drawdown(r)
    out = {
        "CAGR": cagr,
        "Vol": vol,
        "Sharpe": ex.mean() * 12 / vol,
        "Sortino": ex.mean() * 12 / down,
        "MaxDD": dd.min(),
        "Calmar": cagr / -dd.min(),
        "Worst 12m": ((1 + r).rolling(12).apply(np.prod, raw=True) - 1).min(),
        "Skew": r.skew(),
    }
    if mkt is not None:
        m = mkt.reindex(r.index) - rf
        b = np.cov(ex, m)[0, 1] / m.var()
        out["Beta"] = b
        out["Alpha"] = (ex.mean() - b * m.mean()) * 12
        out["Corr"] = np.corrcoef(ex, m)[0, 1]
        out["TE"] = (ex - m).std() * np.sqrt(12)
    return pd.Series(out)


def dd_episodes(r, top=5):
    """Top drawdown episodes: peak, trough, recovery, depth, length."""
    w = wealth(r)
    peak = w.cummax()
    dd = w / peak - 1
    eps, in_dd, start = [], False, None
    for t, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, t
        elif v == 0 and in_dd:
            seg = dd.loc[start:t]
            eps.append((start, seg.idxmin(), t, seg.min()))
            in_dd = False
    if in_dd:
        seg = dd.loc[start:]
        eps.append((start, seg.idxmin(), None, seg.min()))
    df = pd.DataFrame(eps, columns=["Start", "Trough", "Recovery", "Depth"]).sort_values("Depth").head(top)
    return df


def regime_table(qrets_q, mkt_q, macro):
    """Average annualised quarterly return of each quadrant portfolio minus market, per realised regime."""
    reg = (np.where(macro["dG"] > 0, "GU", "GD").astype(object) + "_" + np.where(macro["dI"] > 0, "IU", "ID"))
    reg = pd.Series(reg, index=macro.index)
    ex = qrets_q.sub(mkt_q, axis=0).dropna()
    reg = reg.reindex(ex.index)
    return (ex.groupby(reg).mean() * 4).T, reg.value_counts()
