"""Window-level diagnostics explaining *why* a rolling correlation moves.

All functions take aligned 1-d numpy arrays x, y (no NaNs) and a window length n.
Window t covers observations t-n+1 .. t; arrays indexed by window are aligned to
the window END and are NaN for t < n-1.  Inside each window position k = 0 is the
OLDEST observation and k = n-1 the NEWEST.
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def windows(a: np.ndarray, n: int) -> np.ndarray:
    """(T-n+1, n) view of rolling windows."""
    return sliding_window_view(a, n)


def _pad(a: np.ndarray, n: int, T: int) -> np.ndarray:
    out = np.full((T,) + a.shape[1:], np.nan)
    out[n - 1:] = a
    return out


def corr_rows(X: np.ndarray, Y: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Pearson correlation along the last axis, optionally on a boolean subset mask."""
    if mask is None:
        mask = np.ones_like(X, dtype=bool)
    w = mask.astype(float)
    m = w.sum(-1, keepdims=True)
    mx = (X * w).sum(-1, keepdims=True) / m
    my = (Y * w).sum(-1, keepdims=True) / m
    dx, dy = (X - mx) * w, (Y - my) * w
    return (dx * dy).sum(-1) / np.sqrt((dx * dx).sum(-1) * (dy * dy).sum(-1))


# ---------------------------------------------------------------- 2. rolling correlations
def rolling_corr(x: pd.Series, y: pd.Series, ns=(6, 12, 24, 36, 60)) -> pd.DataFrame:
    return pd.DataFrame({f"{n}m": x.rolling(n).corr(y) for n in ns})


def ewma_corr(x: pd.Series, y: pd.Series, lambdas=(0.94, 0.97, 0.98, 0.99)) -> pd.DataFrame:
    """RiskMetrics-style EWMA correlation (demeaned with the same EWMA)."""
    out = {}
    for lam in lambdas:
        a = 1 - lam
        cov = x.ewm(alpha=a).cov(y)
        vx, vy = x.ewm(alpha=a).var(), y.ewm(alpha=a).var()
        hl = np.log(0.5) / np.log(lam)
        out[f"EWMA λ={lam} (HL {hl:.0f}m)"] = (cov / np.sqrt(vx * vy)).where(np.arange(len(x)) >= 24)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- 3. contribution decomposition
def contributions(x, y, n=36):
    """z-scores and c_i = zx_i * zy_i for every window (ddof=1).

    With sample std (ddof=1) the identity rho = sum(c_i) / (n-1) is exact.
    Returns dict of (T, n) arrays.
    """
    T = len(x)
    X, Y = windows(x, n), windows(y, n)
    zx = (X - X.mean(1, keepdims=True)) / X.std(1, ddof=1, keepdims=True)
    zy = (Y - Y.mean(1, keepdims=True)) / Y.std(1, ddof=1, keepdims=True)
    c = zx * zy
    return {k: _pad(v, n, T) for k, v in dict(zx=zx, zy=zy, c=c).items()}


def contributions_long(index: pd.PeriodIndex, x, y, n=36) -> pd.DataFrame:
    """Every monthly contribution in every window, long format."""
    d = contributions(x, y, n)
    T = len(x)
    ends = np.arange(n - 1, T)
    pos = np.arange(n)
    obs = ends[:, None] - (n - 1) + pos[None, :]
    rho = np.nansum(d["c"][ends], 1) / (n - 1)
    return pd.DataFrame({
        "window_end": np.repeat(index[ends].astype(str), n),
        "obs_month": index[obs.ravel()].astype(str),
        "age_months": np.tile(n - 1 - pos, len(ends)),   # 0 = newest month in window
        "x": x[obs.ravel()], "y": y[obs.ravel()],
        "zx": d["zx"][ends].ravel(), "zy": d["zy"][ends].ravel(),
        "c": d["c"][ends].ravel(),
        "c_over_n1": d["c"][ends].ravel() / (n - 1),       # additive share of rho
        "window_rho": np.repeat(rho, n),
    })


# ---------------------------------------------------------------- 5. leave-one-out influence
def loo_corr(x, y, n=36):
    """rho_{-i} for every window and position, via running sums (exact)."""
    T = len(x)
    X, Y = windows(x, n), windows(y, n)
    Sx, Sy = X.sum(1, keepdims=True), Y.sum(1, keepdims=True)
    Sxx, Syy, Sxy = (X * X).sum(1, keepdims=True), (Y * Y).sum(1, keepdims=True), (X * Y).sum(1, keepdims=True)
    m = n - 1
    sx, sy = Sx - X, Sy - Y
    cxy = (Sxy - X * Y) - sx * sy / m
    vx = (Sxx - X * X) - sx ** 2 / m
    vy = (Syy - Y * Y) - sy ** 2 / m
    return _pad(cxy / np.sqrt(vx * vy), n, T)


# ---------------------------------------------------------------- 4. concentration / robustness
def concentration(x, y, n=36, ks=(1, 2, 3, 5, 10), max_flip=12):
    T = len(x)
    c = contributions(x, y, n)["c"]
    rho = np.nansum(c, 1) / (n - 1)
    rho[: n - 1] = np.nan
    loo = loo_corr(x, y, n)
    infl = loo - rho[:, None]
    out = {"rho": rho}
    absc = np.abs(c)
    order = np.argsort(-np.nan_to_num(absc, nan=-1), axis=1)
    abs_sorted = np.take_along_axis(absc, order, 1)
    c_sorted = np.take_along_axis(c, order, 1)
    tot = absc.sum(1)
    X, Y = windows(x, n), windows(y, n)
    for k in ks:
        out[f"C{k}_abs_share"] = abs_sorted[:, :k].sum(1) / tot
        # signed: rho that remains if the top-k |c| months are given zero weight,
        # holding the window's standardisation fixed (static, additive view)
        out[f"rho_ex_top{k}_static"] = (np.nansum(c, 1) - c_sorted[:, :k].sum(1)) / (n - 1)
        # recomputed: drop the k most influential months and re-estimate the correlation
        mask = np.ones((T - n + 1, n), bool)
        top = order[n - 1:, :k]
        np.put_along_axis(mask, top, False, 1)
        out[f"rho_trim{k}"] = _pad(corr_rows(X, Y, mask), n, T)
    out["max_abs_influence"] = np.nanmax(np.abs(infl), 1)
    imax = np.nanargmax(np.nan_to_num(np.abs(infl), nan=-1), 1)
    out["max_influence_signed"] = np.take_along_axis(infl, imax[:, None], 1)[:, 0]
    out["max_influence_pos"] = imax          # position in window (0 = oldest)
    out["n_to_flip_sign"] = _pad(n_to_flip(X, Y, max_flip), n, T)
    # sign agreement (spec: raw X*Y > 0) and the demeaned analogue (c > 0)
    out["S_raw"] = _pad((X * Y > 0).mean(1), n, T)
    pos = c > 0
    out["S_demeaned"] = pos.mean(1)
    with np.errstate(invalid="ignore"):
        out["mean_abs_c_same"] = np.nanmean(np.where(pos, absc, np.nan), 1)
        out["mean_abs_c_opp"] = np.nanmean(np.where(~pos & ~np.isnan(c), absc, np.nan), 1)
    for k in [k for k in out if isinstance(out[k], np.ndarray) and out[k].ndim == 1]:
        out[k] = np.asarray(out[k], float)
        out[k][: n - 1] = np.nan
    return out, infl


def n_to_flip(X, Y, max_k=12):
    """Greedy: minimum number of months whose removal flips the sign of rho (capped)."""
    W, n = X.shape
    res = np.full(W, np.inf)
    mask = np.ones((W, n), bool)
    rho0 = np.sign(corr_rows(X, Y))
    active = np.ones(W, bool)
    for k in range(1, max_k + 1):
        # evaluate removing each remaining month; pick the one pushing rho most against its sign
        best = np.full(W, np.inf)
        best_j = np.zeros(W, int)
        for j in range(n):
            m2 = mask.copy()
            m2[:, j] = False
            r = corr_rows(X, Y, m2) * rho0
            r[~mask[:, j]] = np.inf
            better = r < best
            best[better], best_j[better] = r[better], j
        mask[np.arange(W), best_j] = False
        newly = active & (best <= 0)
        res[newly] = k
        active &= ~newly
        if not active.any():
            break
    return res


# ---------------------------------------------------------------- 6/11. entry / exit decomposition
def entry_exit(index: pd.PeriodIndex, x, y, n=36) -> pd.DataFrame:
    """Exact decomposition of d rho_t = rho_t - rho_{t-1}.

    With C = sample covariance, B = 1/(s_x s_y), a, b = old-window means, and
    in/out = cross-products of the entering/exiting month around the OLD means:

        (n-1) dC = in - out - n * dmx * dmy
        d rho   = dC * Bbar + Cbar * dB                       (exact product rule)

    =>  d rho = ENTRY  + EXIT + MEAN-SHIFT + RESCALING, where
        ENTRY = Bbar * in / (n-1)      EXIT = -Bbar * out / (n-1)
        MEAN  = -Bbar * n dmx dmy / (n-1)
        RESC  = Cbar * dB  (change in the window's volatilities re-weights everything)
    """
    s = pd.DataFrame({"x": x, "y": y}, index=index)
    mx, my = s.x.rolling(n).mean(), s.y.rolling(n).mean()
    C = s.x.rolling(n).cov(s.y)
    B = 1 / (s.x.rolling(n).std() * s.y.rolling(n).std())
    a, b = mx.shift(1), my.shift(1)
    x_out, y_out = s.x.shift(n), s.y.shift(n)
    cin = (s.x - a) * (s.y - b)
    cout = (x_out - a) * (y_out - b)
    Bbar, Cbar = (B + B.shift(1)) / 2, (C + C.shift(1)) / 2
    rho = C * B
    d = pd.DataFrame(index=index)
    d["rho"] = rho
    d["d_rho"] = rho.diff()
    d["entry"] = Bbar * cin / (n - 1)
    d["exit"] = -Bbar * cout / (n - 1)
    d["mean_shift"] = -Bbar * n * mx.diff() * my.diff() / (n - 1)
    d["rescaling"] = Cbar * B.diff()
    d["check_residual"] = d.d_rho - d[["entry", "exit", "mean_shift", "rescaling"]].sum(1)
    d["entering_month"] = index.astype(str)
    d["exiting_month"] = pd.Series(index.astype(str), index=index).shift(n)
    # contributions of entering / exiting months in their own window's z-units
    cc = contributions(x, y, n)["c"]
    d["c_entering_new_window"] = cc[:, -1]
    d["c_exiting_old_window"] = np.r_[np.nan, cc[:-1, 0]]
    # Shapley-style pure entry/exit effects on rho (two-step re-estimation)
    X, Y = windows(x, n + 1), windows(y, n + 1)          # [exit, ..., entry]
    r_old = corr_rows(X[:, :-1], Y[:, :-1])
    r_new = corr_rows(X[:, 1:], Y[:, 1:])
    r_mid = corr_rows(X[:, 1:-1], Y[:, 1:-1])            # exit removed, entry not added
    r_big = corr_rows(X, Y)                              # entry added, exit not removed
    ex = 0.5 * ((r_mid - r_old) + (r_new - r_big))
    en = 0.5 * ((r_big - r_old) + (r_new - r_mid))
    d["shapley_exit"] = np.r_[np.full(n, np.nan), ex]
    d["shapley_entry"] = np.r_[np.full(n, np.nan), en]
    return d.iloc[n:]


# ---------------------------------------------------------------- null benchmarks for concentration
def null_benchmarks(n=36, sims=20000, rhos=(0.0, 0.3, 0.6), seed=0):
    """Concentration statistics when the relationship is truly constant.

    Normal and Student-t(4) (fat-tailed, common shocks) bivariate draws.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for dist in ("normal", "t4"):
        for r in rhos:
            L = np.linalg.cholesky([[1, r], [r, 1]])
            Z = rng.standard_normal((sims, n, 2)) @ L.T
            if dist == "t4":
                Z = Z / np.sqrt(rng.chisquare(4, (sims, n, 1)) / 4)
            x, y = Z[..., 0], Z[..., 1]
            zx = (x - x.mean(1, keepdims=True)) / x.std(1, ddof=1, keepdims=True)
            zy = (y - y.mean(1, keepdims=True)) / y.std(1, ddof=1, keepdims=True)
            c = np.abs(zx * zy)
            cs = -np.sort(-c, 1)
            rho = corr_rows(x, y)
            # LOO via sums
            m = n - 1
            sx, sy = x.sum(1, keepdims=True) - x, y.sum(1, keepdims=True) - y
            cxy = ((x * y).sum(1, keepdims=True) - x * y) - sx * sy / m
            vx = ((x * x).sum(1, keepdims=True) - x * x) - sx ** 2 / m
            vy = ((y * y).sum(1, keepdims=True) - y * y) - sy ** 2 / m
            maxinf = np.abs(cxy / np.sqrt(vx * vy) - rho[:, None]).max(1)
            for name, v in {"C1_abs_share": cs[:, 0] / cs.sum(1),
                            "C3_abs_share": cs[:, :3].sum(1) / cs.sum(1),
                            "C5_abs_share": cs[:, :5].sum(1) / cs.sum(1),
                            "max_abs_influence": maxinf,
                            "rho_hat": rho}.items():
                q = np.quantile(v, [0.05, 0.5, 0.95, 0.99])
                rows.append(dict(dist=dist, true_rho=r, stat=name, p05=q[0], p50=q[1], p95=q[2], p99=q[3]))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 7. episodes
def zigzag(s: pd.Series, thresh=0.30) -> list[tuple]:
    """Swings between turning points that reverse by at least `thresh`."""
    s = s.dropna()
    v = s.values
    pivots, direction, e = [], 0, 0
    lo = hi = 0
    for i in range(1, len(v)):
        if direction == 0:
            lo = i if v[i] < v[lo] else lo
            hi = i if v[i] > v[hi] else hi
            if v[i] - v[lo] >= thresh:
                pivots.append(lo); direction, e = 1, i
            elif v[hi] - v[i] >= thresh:
                pivots.append(hi); direction, e = -1, i
        elif direction == 1:
            if v[i] > v[e]:
                e = i
            elif v[e] - v[i] >= thresh:
                pivots.append(e); direction, e = -1, i
        else:
            if v[i] < v[e]:
                e = i
            elif v[i] - v[e] >= thresh:
                pivots.append(e); direction, e = 1, i
    pivots.append(e)
    return [(s.index[a], s.index[b]) for a, b in zip(pivots[:-1], pivots[1:])]
