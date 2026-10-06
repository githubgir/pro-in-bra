"""Section 9/10: does the data support genuine correlation regimes?

* DCC-GARCH(1,1) conditional correlation
* Bivariate Gaussian Markov-switching models (EM / Hamilton filter), compared by BIC
  against a constant-correlation fat-tailed alternative and a variance-only MS model
* Simulation nulls: what rolling-correlation behaviour does a *stable* relationship
  (constant dependence, fat tails, volatility clustering) generate?
"""
import numpy as np
import pandas as pd
from arch import arch_model
from scipy import optimize, stats
from scipy.special import logsumexp

from analytics import windows, corr_rows


# ---------------------------------------------------------------- univariate GARCH + DCC
def garch_fit(r: pd.Series):
    res = arch_model(r * 100, mean="Constant", vol="GARCH", p=1, q=1, dist="normal").fit(disp="off")
    return res


def dcc_fit(x: pd.Series, y: pd.Series):
    gx, gy = garch_fit(x), garch_fit(y)
    e = np.column_stack([gx.std_resid, gy.std_resid])
    Qbar = np.cov(e.T, bias=True)
    Qbar = Qbar / np.sqrt(np.outer(np.diag(Qbar), np.diag(Qbar)))

    def path(a, b):
        T = len(e)
        Q = Qbar.copy()
        R = np.empty(T)
        ll = 0.0
        for t in range(T):
            if t > 0:
                Q = (1 - a - b) * Qbar + a * np.outer(e[t - 1], e[t - 1]) + b * Q
            r = Q[0, 1] / np.sqrt(Q[0, 0] * Q[1, 1])
            R[t] = r
            z1, z2 = e[t]
            ll += -0.5 * (np.log(1 - r * r) + (z1 * z1 - 2 * r * z1 * z2 + z2 * z2) / (1 - r * r) - z1 * z1 - z2 * z2)
        return R, ll

    def nll(p):
        a, b = p
        if a < 0 or b < 0 or a + b >= 0.999:
            return 1e10
        return -path(a, b)[1]

    best = min((optimize.minimize(nll, p0, method="Nelder-Mead") for p0 in [(0.02, 0.95), (0.05, 0.9), (0.01, 0.98)]),
               key=lambda o: o.fun)
    a, b = best.x
    R, ll = path(a, b)
    return pd.Series(R, index=x.index, name="DCC"), dict(a=a, b=b, half_life_m=np.log(0.5) / np.log(a + b),
                                                         garch_x=gx.params.to_dict(), garch_y=gy.params.to_dict(),
                                                         std_resid=e, ll=ll)


# ---------------------------------------------------------------- Markov switching (bivariate Gaussian)
def _mvn_logpdf(Y, mu, S):
    d = Y - mu
    Si = np.linalg.inv(S)
    return -0.5 * (np.einsum("ti,ij,tj->t", d, Si, d) + np.log(np.linalg.det(S)) + 2 * np.log(2 * np.pi))


def _forward_backward(logB, P, pi0):
    """Scaled forward-backward (Rabiner).  Returns loglik, smoothed probs, expected
    transition counts and filtered probs."""
    T, K = logB.shape
    shift = logB.max(1, keepdims=True)
    Bm = np.exp(logB - shift)
    alpha = np.empty((T, K)); c = np.empty(T)
    a = pi0 * Bm[0]; c[0] = a.sum(); alpha[0] = a / c[0]
    for t in range(1, T):
        a = (alpha[t - 1] @ P) * Bm[t]
        c[t] = a.sum(); alpha[t] = a / c[t]
    ll = np.log(c).sum() + shift.sum()
    beta = np.ones((T, K))
    for t in range(T - 2, -1, -1):
        beta[t] = (P @ (Bm[t + 1] * beta[t + 1])) / c[t + 1]
    g = alpha * beta
    g /= g.sum(1, keepdims=True)
    xi = P * (alpha[:-1].T @ (Bm[1:] * beta[1:] / c[1:, None]))
    return ll, g, xi, alpha


def _hamilton_ll(logB, P, pi0):
    return _forward_backward(logB, P, pi0)[0]


def ms_em(Y: np.ndarray, K: int, n_starts=20, iters=500, seed=0):
    """Unrestricted K-state bivariate Gaussian HMM (state-specific means, vols, correlation)."""
    rng = np.random.default_rng(seed)
    T = len(Y)
    best = None
    for s in range(n_starts):
        g = rng.dirichlet(np.ones(K) * 0.5, T)
        # smooth random initial assignment to encourage persistent states
        g = pd.DataFrame(g).rolling(24, min_periods=1).mean().values
        P = np.full((K, K), 0.05 / max(K - 1, 1)) + np.eye(K) * (0.95 - 0.05 / max(K - 1, 1)) if K > 1 else np.ones((1, 1))
        pi0 = np.ones(K) / K
        ll_old = -np.inf
        for it in range(iters):
            mus, Ss = [], []
            for k in range(K):
                w = g[:, k] / g[:, k].sum()
                mu = w @ Y
                d = Y - mu
                S = (d * w[:, None]).T @ d + 1e-8 * np.eye(2)
                mus.append(mu); Ss.append(S)
            logB = np.column_stack([_mvn_logpdf(Y, mus[k], Ss[k]) for k in range(K)])
            ll, g, xi, filt = _forward_backward(logB, P, pi0)
            if K > 1:
                P = xi / xi.sum(1, keepdims=True)
                P = np.clip(P, 1e-6, None); P /= P.sum(1, keepdims=True)
            pi0 = np.clip(g[0], 1e-6, None); pi0 /= pi0.sum()
            if ll - ll_old < 1e-7:
                break
            ll_old = ll
        if best is None or ll > best["ll"]:
            best = dict(ll=ll, mu=mus, S=Ss, P=P, g=g, filt=filt)
    k_par = K * 5 + K * (K - 1)
    best.update(K=K, k_par=k_par, bic=-2 * best["ll"] + k_par * np.log(T), aic=-2 * best["ll"] + 2 * k_par)
    # order states by correlation
    rho = np.array([S[0, 1] / np.sqrt(S[0, 0] * S[1, 1]) for S in best["S"]])
    o = np.argsort(rho)
    best["rho"] = rho[o]
    best["vol"] = np.array([np.sqrt(np.diag(best["S"][k])) for k in o])
    best["P"] = best["P"][np.ix_(o, o)]
    best["g"], best["filt"] = best["g"][:, o], best["filt"][:, o]
    best["duration_m"] = 1 / (1 - np.diag(best["P"]))
    return best


def ms_common_corr(Y: np.ndarray, init: dict):
    """2-state MS with state-specific means and vols but ONE common correlation
    ("stable relationship, switching volatility"), by direct likelihood maximisation."""
    T = len(Y)

    def unpack(p):
        mu = p[0:4].reshape(2, 2)
        sd = np.exp(p[4:8]).reshape(2, 2)
        r = np.tanh(p[8])
        p11, p22 = 1 / (1 + np.exp(-p[9])), 1 / (1 + np.exp(-p[10]))
        P = np.array([[p11, 1 - p11], [1 - p22, p22]])
        S = [np.array([[sd[k, 0] ** 2, r * sd[k, 0] * sd[k, 1]], [r * sd[k, 0] * sd[k, 1], sd[k, 1] ** 2]]) for k in range(2)]
        return mu, S, P, r

    def nll(p):
        mu, S, P, _ = unpack(p)
        logB = np.column_stack([_mvn_logpdf(Y, mu[k], S[k]) for k in range(2)])
        return -_hamilton_ll(logB, P, np.array([0.5, 0.5]))

    # start from the variance-sorted unrestricted 2-state solution
    v = init["vol"]
    o = np.argsort(v[:, 0])
    mu0 = np.array(init["mu"])
    p0 = np.r_[np.zeros(4), np.log(v[o]).ravel(), np.arctanh(np.mean(init["rho"])), 3.0, 3.0]
    p0[0:4] = Y.mean(0).tolist() * 2
    res = optimize.minimize(nll, p0, method="L-BFGS-B")
    mu, S, P, r = unpack(res.x)
    k_par = 11
    return dict(ll=-res.fun, rho=r, P=P, k_par=k_par, bic=2 * res.fun + k_par * np.log(T), aic=2 * res.fun + 2 * k_par)


def biv_t_constant(Y: np.ndarray):
    """Single-regime bivariate Student-t: constant dependence with fat-tailed joint shocks."""
    T = len(Y)

    def unpack(p):
        mu = p[:2]; sd = np.exp(p[2:4]); r = np.tanh(p[4]); nu = 2.05 + np.exp(p[5])
        S = np.array([[sd[0] ** 2, r * sd[0] * sd[1]], [r * sd[0] * sd[1], sd[1] ** 2]])
        return mu, S, nu, r

    def nll(p):
        mu, S, nu, _ = unpack(p)
        return -stats.multivariate_t(mu, S, df=nu).logpdf(Y).sum()

    p0 = np.r_[Y.mean(0), np.log(Y.std(0)), np.arctanh(np.corrcoef(Y.T)[0, 1]), np.log(4)]
    res = optimize.minimize(nll, p0, method="L-BFGS-B")
    mu, S, nu, r = unpack(res.x)
    return dict(ll=-res.fun, rho=r, nu=nu, k_par=6, bic=2 * res.fun + 6 * np.log(T), aic=2 * res.fun + 12)


# ---------------------------------------------------------------- simulation nulls for rolling correlation
def rolling_stats(X: np.ndarray, Y: np.ndarray, n=36) -> pd.DataFrame:
    """Rolling-correlation summary stats for a batch of paths, X/Y shape (sims, T)."""
    r = corr_rows(windows(X, n, ), windows(Y, n)) if X.ndim == 1 else corr_rows(
        np.lib.stride_tricks.sliding_window_view(X, n, axis=1),
        np.lib.stride_tricks.sliding_window_view(Y, n, axis=1))
    r = np.atleast_2d(r)
    lead, lag = r[:, :-n], r[:, n:]
    lc, gc = lead - lead.mean(1, keepdims=True), lag - lag.mean(1, keepdims=True)
    ac = (lc * gc).sum(1) / np.sqrt((lc ** 2).sum(1) * (gc ** 2).sum(1))
    return pd.DataFrame(dict(
        std=r.std(1), range=np.ptp(r, 1), share_abs_gt_04=(np.abs(r) > 0.4).mean(1),
        ac_nonoverlap=ac,                                   # rho(window t) vs rho(next DISJOINT window)
        sign_changes=(np.diff(np.sign(r), axis=1) != 0).sum(1)))


def null_rolling(x: np.ndarray, y: np.ndarray, dcc_info: dict, n=36, sims=1000, seed=1):
    """Two nulls of a STABLE relationship.

    iid_pairs : resample (x_t, y_t) pairs iid -> keeps fat tails and the empirical joint
                shock distribution (incl. common crash months), destroys time variation.
    ccc_garch : constant-dependence GARCH(1,1) for each leg, shocks drawn as iid pairs of
                the fitted standardised residuals -> adds volatility clustering, which
                inflates the sampling noise of rolling Pearson estimates.
    """
    rng = np.random.default_rng(seed)
    T = len(x)
    i = rng.integers(0, T, (sims, T))
    out = [rolling_stats(x[i], y[i], n).assign(null="iid_pairs")]
    e = dcc_info["std_resid"]
    burn = 200
    j = rng.integers(0, len(e), (sims, T + burn))
    paths = []
    for g, col in ((dcc_info["garch_x"], 0), (dcc_info["garch_y"], 1)):
        om, al, be = g["omega"], g["alpha[1]"], g["beta[1]"]
        h = np.full(sims, om / max(1 - al - be, 0.02))   # bond GARCH is near-integrated
        p = np.empty((sims, T + burn))
        for t in range(T + burn):
            eps = np.sqrt(h) * e[j[:, t], col]
            p[:, t] = eps
            h = om + al * eps * eps + be * h
        paths.append(p[:, burn:])
    out.append(rolling_stats(*paths, n).assign(null="ccc_garch"))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- correlation-only regimes on de-volatilised shocks
def _corr_logpdf(E, r):
    z1, z2 = E[:, 0], E[:, 1]
    return -0.5 * (2 * np.log(2 * np.pi) + np.log(1 - r * r) + (z1 * z1 - 2 * r * z1 * z2 + z2 * z2) / (1 - r * r))


def ms_corr_only(E: np.ndarray, K: int, n_starts=20, iters=1000, seed=0):
    """K-state HMM in which ONLY the correlation switches.

    E are GARCH-standardised residuals (unit variance), so volatility regimes are
    already removed and any surviving state structure is about co-movement itself.
    """
    rng = np.random.default_rng(seed)
    T = len(E)
    best = None
    for s in range(n_starts):
        rho = np.sort(rng.uniform(-0.7, 0.7, K))
        P = np.full((K, K), 0.02 / max(K - 1, 1)) + np.eye(K) * (0.98 - 0.02 / max(K - 1, 1)) if K > 1 else np.ones((1, 1))
        pi0 = np.ones(K) / K
        ll_old = -np.inf
        for it in range(iters):
            logB = np.column_stack([_corr_logpdf(E, r) for r in rho])
            ll, g, xi, filt = _forward_backward(logB, P, pi0)
            for k in range(K):
                w = g[:, k]
                rho[k] = optimize.minimize_scalar(lambda r: -(w * _corr_logpdf(E, r)).sum(),
                                                  bounds=(-0.99, 0.99), method="bounded").x
            if K > 1:
                P = np.clip(xi / xi.sum(1, keepdims=True), 1e-8, None); P /= P.sum(1, keepdims=True)
            pi0 = np.clip(g[0], 1e-8, None); pi0 /= pi0.sum()
            if ll - ll_old < 1e-8:
                break
            ll_old = ll
        if best is None or ll > best["ll"]:
            o = np.argsort(rho)
            best = dict(ll=ll, rho=rho[o].copy(), P=P[np.ix_(o, o)].copy(), g=g[:, o].copy(), filt=filt[:, o].copy())
    k_par = K + K * (K - 1)
    best.update(K=K, k_par=k_par, bic=-2 * best["ll"] + k_par * np.log(T), aic=-2 * best["ll"] + 2 * k_par,
                duration_m=1 / (1 - np.diag(best["P"])) if K > 1 else np.array([np.inf]))
    return best


def t_corr_constant(E: np.ndarray):
    """Constant-correlation Student-t on unit-variance shocks (fat-tailed common shocks)."""
    T = len(E)

    def nll(p):
        r, nu = np.tanh(p[0]), 2.05 + np.exp(p[1])
        S = np.array([[1, r], [r, 1]]) * (nu - 2) / nu      # unit variance
        return -stats.multivariate_t(np.zeros(2), S, df=nu).logpdf(E).sum()

    res = optimize.minimize(nll, [0.0, np.log(5)], method="Nelder-Mead")
    return dict(ll=-res.fun, rho=np.tanh(res.x[0]), nu=2.05 + np.exp(res.x[1]), k_par=2,
                bic=2 * res.fun + 2 * np.log(T), aic=2 * res.fun + 4)


def dcc_gaussian_ll(E: np.ndarray, R: np.ndarray):
    """Full bivariate Gaussian log-likelihood of E under a correlation path R (comparable to the above)."""
    return sum(_corr_logpdf(E[t:t + 1], R[t])[0] for t in range(len(E)))


def _t_corr_logpdf(E, r, nu):
    S = np.array([[1, r], [r, 1]]) * (nu - 2) / nu
    return stats.multivariate_t(np.zeros(2), S, df=nu).logpdf(E)


def ms_corr_t(E: np.ndarray, init: dict):
    """Correlation-only regimes WITH fat-tailed (Student-t, common nu) shocks.

    This is the fair test against `t_corr_constant`: both allow occasional extreme
    joint months; only this one allows the correlation itself to switch persistently.
    """
    K = init["K"]
    T = len(E)

    def unpack(p):
        rho = np.tanh(p[:K]); nu = 2.05 + np.exp(p[K])
        L = p[K + 1:].reshape(K, K - 1)
        P = np.empty((K, K))
        for i in range(K):
            z = np.r_[L[i][:i], 0.0, L[i][i:]]
            P[i] = np.exp(z - logsumexp(z))
        return rho, nu, P

    def nll(p):
        rho, nu, P = unpack(p)
        logB = np.column_stack([_t_corr_logpdf(E, r, nu) for r in rho])
        return -_forward_backward(logB, P, np.ones(K) / K)[0]

    Pi = init["P"]
    L0 = np.array([[np.log(Pi[i, j] / Pi[i, i]) for j in range(K) if j != i] for i in range(K)])
    p0 = np.r_[np.arctanh(init["rho"]), np.log(5), L0.ravel()]
    res = optimize.minimize(nll, p0, method="L-BFGS-B")
    rho, nu, P = unpack(res.x)
    logB = np.column_stack([_t_corr_logpdf(E, r, nu) for r in rho])
    _, g, _, filt = _forward_backward(logB, P, np.ones(K) / K)
    k_par = K + 1 + K * (K - 1)
    return dict(K=K, ll=-res.fun, rho=rho, nu=nu, P=P, g=g, filt=filt, k_par=k_par,
                bic=2 * res.fun + k_par * np.log(T), aic=2 * res.fun + 2 * k_par,
                duration_m=1 / (1 - np.diag(P)))
