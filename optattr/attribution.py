"""Pressure attribution, covariance propagation and precision decomposition.

Primary layer (spec §3-4), per source r (each target, each constraint family):

    h = sum_r h^(r),   Sigma x = h,   x^(r) = Sigma^-1 h^(r),   x = sum_r x^(r)

Structural layer (spec §6), with Sigma = D R D and Omega = R^-1:

    z^(r) = D^-1 h^(r)
    sigma_i x_i^(r) = Omega_ii z_i^(r)  +  sum_{j!=i} Omega_ij z_j^(r)
                      \\__ own O_i^(r) __/   \\_____ network N_i^(r) _____/

Own / network terms are reported in weight units (divided by sigma_i), so
own + network = x_i^(r) exactly.

Peer layer (spec §8, presentation only). P_i = top-k stocks by |partial corr|
rho_ij = -Omega_ij / sqrt(Omega_ii Omega_jj), a_ij proportional to |Omega_ij|.
The network term is split exactly as

    N_i = (sum_{j in P_i} Omega_ij) z_i            common  : peers absorb shared pressure
        + sum_{j in P_i} Omega_ij (z_j - z_i)      differentiated peer effect
        + sum_{j not in P_i, j!=i} Omega_ij z_j    rest of network

and the spec's peer averages  Omega_bar_i = sum a_ij Omega_ij,
z_bar_i = sum a_ij z_j  are reported as diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.linalg import cho_factor, cho_solve

from .covariance import correlation_split
from .problem import Solution

TOL = 1e-8  # relative reconciliation tolerance


@dataclass
class Attribution:
    sol: Solution
    sources: list[str]
    H: np.ndarray        # (N, S) pressures h^(r)
    Xr: np.ndarray       # (N, S) weight contributions x^(r)
    own: np.ndarray      # (N, S) own-precision contribution, weight units
    net: np.ndarray      # (N, S) network contribution, weight units
    sigma: np.ndarray
    Omega: np.ndarray
    Sigma: np.ndarray
    peers: np.ndarray    # (N, k) peer indices
    peer_w: np.ndarray   # (N, k) a_ij
    common: np.ndarray   # (N, S) weight units
    differentiated: np.ndarray
    rest_network: np.ndarray
    peer_pressure: np.ndarray   # (N, S) z_bar
    peer_precision: np.ndarray  # (N,) Omega_bar

    @property
    def ids(self) -> pd.Index:
        return self.sol.x.index

    # ------------------------------------------------------------ tables
    def stock_table(self, stock: str, peer_detail: bool = False) -> pd.DataFrame:
        """Spec §9 table for one stock (rows = sources, plus TOTAL)."""
        i = self.ids.get_loc(stock)
        df = pd.DataFrame({
            "Pressure": self.H[i],
            "Own precision": self.own[i],
            "Network": self.net[i],
            "Weight contribution": self.Xr[i],
        }, index=pd.Index(self.sources, name="Source"))
        if peer_detail:
            df["Peer common"] = self.common[i]
            df["Peer differentiated"] = self.differentiated[i]
            df["Other network"] = self.rest_network[i]
        df["Status"] = [self._stock_status(stock, s) for s in self.sources]
        total = df.drop(columns="Status").sum()
        gap = abs(total["Weight contribution"] - self.sol.x.iloc[i]) / np.abs(self.sol.x).max()
        total["Status"] = "reconciles" if gap <= TOL else f"BREAK ({gap:.1e})"
        df.loc["TOTAL"] = total
        df.loc["Optimised active weight"] = [np.nan] * (df.shape[1] - 2) + [self.sol.x.iloc[i], ""]
        return df

    def _stock_status(self, stock: str, source: str) -> str:
        status = self.sol.status[source]
        if status in ("target", "equality", "inactive"):
            return status
        for blk, src in self.sol.block_source.items():
            mu = self.sol.row_duals[blk]
            if src == source and stock in mu.index and abs(mu[stock]) > self.sol.dual_tol:
                return "binding (this stock)"
        return "binding"

    def source_summary(self) -> pd.DataFrame:
        """Portfolio-level roll-up of each source."""
        x = self.sol.x.to_numpy()
        h = self.H.sum(axis=1)
        te = float(np.sqrt(x @ self.Sigma @ x))
        risk = self.Xr.T @ h  # x^(r)T Sigma x ; sums to TE^2
        B = _style_matrix(self.sol)
        go, gn = np.abs(self.own).sum(axis=0), np.abs(self.net).sum(axis=0)
        active = np.abs(self.Xr).sum(axis=0) > 1e-9
        own_share = np.where(active, go / np.where(active, go + gn, 1.0), np.nan)
        expo = pd.DataFrame(self.Xr.T @ B.to_numpy(), index=self.sources, columns=B.columns)
        df = pd.DataFrame({
            "Status": [self.sol.status[s] for s in self.sources],
            "Gross pressure": np.abs(self.H).sum(axis=0),
            "Gross weight": np.abs(self.Xr).sum(axis=0),
            "Net weight": self.Xr.sum(axis=0),
            "Own share": own_share,
            "Active risk contrib": risk / te,
        }, index=pd.Index(self.sources, name="Source"))
        return df.join(expo.add_prefix("Exp "))

    def contributions(self) -> pd.DataFrame:
        """(N x S) stock-by-source weight contribution matrix."""
        return pd.DataFrame(self.Xr, index=self.ids, columns=self.sources)

    def top_stocks(self, n: int = 10) -> pd.Index:
        return self.sol.x.abs().sort_values(ascending=False).index[:n]

    # ------------------------------------------------------------ checks
    def reconciliation(self) -> pd.DataFrame:
        """Spec §10 identities with relative errors and pass/fail."""
        x = self.sol.x.to_numpy()
        h = self.H.sum(axis=1)
        hs, xs = np.abs(h).max(), np.abs(x).max()
        sx = self.sigma[:, None] * self.Xr
        rows = {
            "KKT: Sigma x = sum_r h^(r)": np.abs(self.Sigma @ x - h).max() / hs,
            "Propagation: Sigma x^(r) = h^(r)": np.abs(self.Sigma @ self.Xr - self.H).max() / hs,
            "Weights: x = sum_r x^(r)": np.abs(x - self.Xr.sum(axis=1)).max() / xs,
            "Precision: sigma x^(r) = O + N": np.abs(
                sx - self.sigma[:, None] * (self.own + self.net)).max() / np.abs(sx).max(),
            "Peer split: N = common + diff + rest": np.abs(
                self.net - self.common - self.differentiated - self.rest_network).max() / xs,
            "Primal feasibility (max violation)": self.sol.max_violation,
        }
        df = pd.DataFrame({"rel_error": rows})
        df["tolerance"] = TOL
        df["pass"] = df["rel_error"] <= TOL
        return df


def _style_matrix(sol: Solution) -> pd.DataFrame:
    cov = sol.cov
    cols = [c for c, g in zip(cov.columns, cov.groups) if g == "style"]
    idx = [cov.columns.index(c) for c in cols]
    return pd.DataFrame(cov.X[:, idx], index=sol.x.index, columns=cols)


def attribute(sol: Solution, n_peers: int = 10) -> Attribution:
    sources = list(sol.target_pressure) + list(sol.constraint_pressure)
    H = np.column_stack([sol.pressures[s] for s in sources])

    Sigma = sol.cov.dense()
    sigma, R = correlation_split(Sigma)
    Xr = cho_solve(cho_factor(Sigma), H)

    Rf = cho_factor(R)
    Omega = cho_solve(Rf, np.eye(len(sigma)))
    Omega = 0.5 * (Omega + Omega.T)
    Z = H / sigma[:, None]
    diag = np.diag(Omega)
    O = diag[:, None] * Z
    Nw = Omega @ Z - O
    own, net = O / sigma[:, None], Nw / sigma[:, None]

    # peer layer
    pc = -Omega / np.sqrt(np.outer(diag, diag))
    np.fill_diagonal(pc, 0.0)
    k = min(n_peers, len(sigma) - 1)
    peers = np.argpartition(-np.abs(pc), k - 1, axis=1)[:, :k]
    Om_p = np.take_along_axis(Omega, peers, axis=1)            # (N, k)
    a = np.abs(Om_p) / np.abs(Om_p).sum(axis=1, keepdims=True)
    Zp = Z[peers]                                               # (N, k, S)
    common = Om_p.sum(axis=1)[:, None] * Z
    differentiated = np.einsum("ik,iks->is", Om_p, Zp - Z[:, None, :])
    rest = Nw - common - differentiated
    peer_pressure = np.einsum("ik,iks->is", a, Zp)
    peer_precision = (a * Om_p).sum(axis=1)

    s = sigma[:, None]
    return Attribution(
        sol=sol, sources=sources, H=H, Xr=Xr, own=own, net=net,
        sigma=sigma, Omega=Omega, Sigma=Sigma, peers=peers, peer_w=a,
        common=common / s, differentiated=differentiated / s, rest_network=rest / s,
        peer_pressure=peer_pressure, peer_precision=peer_precision,
    )
