"""Low-rank-plus-diagonal covariance and the simplified (average corr / vol) variants.

Every covariance used by the attribution has the form

    Sigma = U U' + diag(d),        U: (N, r),  d: (N,) > 0

which covers the factor model (U = B F^{1/2}, d = specific variance), the
constant-correlation model (U = sqrt(rho) * sigma, d = (1 - rho) sigma^2) and the
constant-correlation / constant-vol model (U = sqrt(rho) * vol * 1,
d = (1 - rho) vol^2).  Nothing here ever forms the N x N matrix.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import cvxpy as cp
import numpy as np

CORR_WEIGHTINGS = ("equal", "cap", "implied")


@dataclass(frozen=True)
class LowRankDiagCov:
    U: np.ndarray
    d: np.ndarray

    def __post_init__(self):
        if np.any(self.d <= 0):
            raise ValueError("diagonal (specific) variances must be strictly positive")

    @classmethod
    def from_factor_model(cls, B, F, D) -> "LowRankDiagCov":
        """Sigma = B F B' + diag(D).  F may be PSD; it is square-rooted by eigh."""
        B = np.asarray(B, float)
        F = np.asarray(F, float)
        D = np.asarray(D, float).ravel()
        lam, Q = np.linalg.eigh(0.5 * (F + F.T))
        U = B @ (Q * np.sqrt(np.clip(lam, 0.0, None)))
        return cls(U, D)

    @property
    def n(self) -> int:
        return self.d.shape[0]

    @property
    def vols(self) -> np.ndarray:
        return np.sqrt(np.einsum("ij,ij->i", self.U, self.U) + self.d)

    def quad(self, x: np.ndarray) -> float:
        """x' Sigma x."""
        return float(np.sum((self.U.T @ x) ** 2) + np.sum(self.d * x**2))

    def matmul(self, X: np.ndarray) -> np.ndarray:
        return self.U @ (self.U.T @ X) + (self.d * X.T).T

    def solve(self, X: np.ndarray) -> np.ndarray:
        """Sigma^{-1} X by Woodbury (O(N r^2))."""
        X = np.asarray(X, float)
        Dinv_X = (X.T / self.d).T
        Dinv_U = self.U / self.d[:, None]
        cap = np.eye(self.U.shape[1]) + self.U.T @ Dinv_U
        return Dinv_X - Dinv_U @ np.linalg.solve(cap, self.U.T @ Dinv_X)

    def cvx_variance(self, a: cp.Expression) -> cp.Expression:
        """a' Sigma a as a DCP expression."""
        return cp.sum_squares(self.U.T @ a) + cp.sum_squares(cp.multiply(np.sqrt(self.d), a))


def _pair_weights(cov: LowRankDiagCov, method, benchmark) -> np.ndarray:
    if isinstance(method, str):
        if method == "equal":
            return np.ones(cov.n)
        if method == "cap":
            return np.asarray(benchmark, float)
        if method == "implied":
            # pairs weighted by b_i sigma_i b_j sigma_j -> preserves benchmark variance
            return np.asarray(benchmark, float) * cov.vols
        raise ValueError(f"corr weighting must be one of {CORR_WEIGHTINGS} or an array")
    v = np.asarray(method, float).ravel()
    if v.shape != (cov.n,) or np.any(v < 0):
        raise ValueError("custom pair weights must be a non-negative length-N array")
    return v


def average_correlation(cov: LowRankDiagCov, method="equal", benchmark=None) -> float:
    """Weighted average off-diagonal correlation  sum_{i!=j} v_i v_j rho_ij / sum_{i!=j} v_i v_j.

    Uses  sum_{i,j} v_i v_j rho_ij = (v/sigma)' Sigma (v/sigma)  so it is O(N r).
    """
    v = _pair_weights(cov, method, benchmark)
    s2 = np.sum(v**2)
    num = cov.quad(v / cov.vols) - s2
    den = v.sum() ** 2 - s2
    if den <= 0:
        raise ValueError("need at least two assets with positive weight to average correlations")
    return float(num / den)


def average_vol(cov: LowRankDiagCov, method="equal", benchmark=None, rho_bar=None) -> float:
    """Average vol: weighted RMS of sigma_i (preserves average variance).

    For method="implied" the vol is instead chosen so that the benchmark variance
    under the constant-corr / constant-vol model equals b' Sigma b.
    """
    if isinstance(method, str) and method == "implied":
        b = np.asarray(benchmark, float)
        rho = average_correlation(cov, "implied", b) if rho_bar is None else rho_bar
        denom = (1 - rho) * np.sum(b**2) + rho * b.sum() ** 2
        return float(np.sqrt(cov.quad(b) / denom))
    v = _pair_weights(cov, method, benchmark)
    return float(np.sqrt(np.sum(v * cov.vols**2) / v.sum()))


def _clip_rho(rho: float, n: int) -> float:
    if rho < 0:
        warnings.warn(f"average correlation {rho:.4f} < 0; clipped to 0", stacklevel=3)
    return float(np.clip(rho, 0.0, 1.0 - 1e-6))


def constant_correlation_cov(cov: LowRankDiagCov, rho_bar: float) -> LowRankDiagCov:
    """Keep each asset's vol, replace every pairwise correlation by rho_bar."""
    rho = _clip_rho(rho_bar, cov.n)
    s = cov.vols
    return LowRankDiagCov(np.sqrt(rho) * s[:, None], (1 - rho) * s**2)


def constant_correlation_vol_cov(n: int, rho_bar: float, vol_bar: float) -> LowRankDiagCov:
    """Every asset has vol vol_bar, every pair correlation rho_bar."""
    rho = _clip_rho(rho_bar, n)
    return LowRankDiagCov(np.full((n, 1), np.sqrt(rho) * vol_bar), np.full(n, (1 - rho) * vol_bar**2))
