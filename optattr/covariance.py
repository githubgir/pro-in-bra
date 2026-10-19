"""Structured covariance model  Sigma = X Phi X^T + diag(d).

Every covariance used in the framework (production, factor-only, vol-only,
Shapley coalitions) is expressed in this one form over a fixed column set X,
so the optimizer can be built once and re-solved by swapping (Phi, d).

Columns of X carry a group label (e.g. "style", "sector", "country", "pair"),
which is what the counterfactual ladder switches on and off.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class CovModel:
    X: np.ndarray            # (N, K) exposures
    Phi: np.ndarray          # (K, K) PSD factor covariance
    d: np.ndarray            # (N,) diagonal (specific) variance, > 0
    columns: tuple[str, ...]  # K column names
    groups: tuple[str, ...]   # K column group labels

    def __post_init__(self):
        n, k = self.X.shape
        if self.Phi.shape != (k, k) or self.d.shape != (n,):
            raise ValueError("inconsistent CovModel shapes")
        if len(self.columns) != k or len(self.groups) != k:
            raise ValueError("columns/groups must have one label per X column")
        if np.any(self.d <= 0):
            raise ValueError("diagonal variance d must be strictly positive")

    @property
    def n(self) -> int:
        return self.X.shape[0]

    def dense(self) -> np.ndarray:
        S = self.X @ self.Phi @ self.X.T
        S[np.diag_indices_from(S)] += self.d
        return 0.5 * (S + S.T)

    def total_var(self) -> np.ndarray:
        return np.einsum("ik,kl,il->i", self.X, self.Phi, self.X) + self.d

    def vols(self) -> np.ndarray:
        return np.sqrt(self.total_var())

    def phi_sqrt(self) -> np.ndarray:
        """L with Phi = L L^T (eigen square root, valid for singular Phi)."""
        vals, vecs = np.linalg.eigh(0.5 * (self.Phi + self.Phi.T))
        return vecs * np.sqrt(np.clip(vals, 0.0, None))

    def column_mask(self, groups: Iterable[str] = (), columns: Iterable[str] = ()) -> np.ndarray:
        groups, columns = set(groups), set(columns)
        return np.array([g in groups or c in columns for g, c in zip(self.groups, self.columns)])

    def restrict(self, keep: Sequence[bool], preserve_total_var: bool = True) -> "CovModel":
        """Zero all Phi rows/cols outside `keep` (a principal submatrix stays PSD).

        With preserve_total_var the removed variance is moved into d, so asset
        volatilities are identical across variants and only correlation changes.
        """
        keep = np.asarray(keep, dtype=bool)
        Phi = self.Phi * np.outer(keep, keep)
        d = self.d
        if preserve_total_var:
            removed = self.total_var() - np.einsum("ik,kl,il->i", self.X, Phi, self.X)
            d = removed
        return replace(self, Phi=Phi, d=d)

    def vol_only(self) -> "CovModel":
        return self.restrict(np.zeros(len(self.columns), dtype=bool))


def correlation_split(Sigma: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sigma = D R D  ->  (sigma vector, R)."""
    sig = np.sqrt(np.diag(Sigma))
    R = Sigma / np.outer(sig, sig)
    return sig, 0.5 * (R + R.T)
