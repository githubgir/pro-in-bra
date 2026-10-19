"""Deterministic synthetic equity universe.

1,000 stocks, 8 style factors, 10 sectors, 8 countries, cap-weighted benchmark,
and a production covariance with four column groups:

    style    8 style factors (BFB^T)
    sector   sector residual blocks      } "enriched residual"
    country  country residual blocks     }
    pair     sparse twin-stock residual links (production-only structure)

Target signals (``scores``) are the current style exposures plus a stock alpha;
``prior_scores`` are decayed versions used to build last period's holdings w0.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .covariance import CovModel

STYLES = ("Market", "Value", "Growth", "Momentum", "Quality", "Size", "LowVol", "Profitability")
SECTORS = ("Energy", "Materials", "Industrials", "ConsDisc", "ConsStaples",
           "HealthCare", "Financials", "InfoTech", "CommServices", "Utilities")
COUNTRIES = ("US", "JP", "GB", "FR", "DE", "CA", "CH", "AU")
COUNTRY_PROBS = (0.45, 0.12, 0.09, 0.08, 0.08, 0.07, 0.06, 0.05)

# annualised style factor vols and correlation
_STYLE_VOL = np.array([0.16, 0.040, 0.035, 0.060, 0.030, 0.035, 0.040, 0.025])
_STYLE_CORR = np.array([
    # Mkt   Val    Grw    Mom    Qual   Size   LowV   Prof
    [1.00, 0.10, 0.05, -0.15, -0.10, 0.20, -0.40, -0.05],
    [0.10, 1.00, -0.50, -0.25, -0.15, 0.10, 0.10, -0.10],
    [0.05, -0.50, 1.00, 0.20, 0.10, -0.05, -0.15, 0.15],
    [-0.15, -0.25, 0.20, 1.00, 0.15, -0.05, 0.10, 0.10],
    [-0.10, -0.15, 0.10, 0.15, 1.00, -0.10, 0.30, 0.45],
    [0.20, 0.10, -0.05, -0.05, -0.10, 1.00, -0.20, -0.10],
    [-0.40, 0.10, -0.15, 0.10, 0.30, -0.20, 1.00, 0.20],
    [-0.05, -0.10, 0.15, 0.10, 0.45, -0.10, 0.20, 1.00],
])
_SECTOR_VOL = 0.05
_COUNTRY_VOL = 0.06


@dataclass(frozen=True)
class Universe:
    ids: pd.Index
    sector: pd.Series
    country: pd.Series
    b: pd.Series                 # benchmark weights
    styles: pd.DataFrame         # style exposures B (N x 8)
    scores: pd.DataFrame         # current target signals (styles + Alpha)
    prior_scores: pd.DataFrame   # last period's target signals
    cov: CovModel                # production covariance
    w0: pd.Series | None = field(default=None)  # prior holdings

    @property
    def n(self) -> int:
        return len(self.ids)

    def with_prior(self, w0: pd.Series) -> "Universe":
        return replace(self, w0=w0.reindex(self.ids))


def _cap_standardise(v: np.ndarray, b: np.ndarray) -> np.ndarray:
    v = v - b @ v
    return v / v.std()


def synthetic_universe(n: int = 1000, n_pairs: int = 40, seed: int = 7) -> Universe:
    rng = np.random.default_rng(seed)
    ids = pd.Index([f"S{i:04d}" for i in range(n)], name="stock")

    sec_probs = rng.dirichlet(np.full(len(SECTORS), 8.0))
    sec = rng.choice(len(SECTORS), size=n, p=sec_probs)
    cty = rng.choice(len(COUNTRIES), size=n, p=COUNTRY_PROBS)

    log_cap = rng.normal(0.0, 1.2, n) + 0.3 * (cty == 0)
    cap = np.exp(log_cap)
    b = cap / cap.sum()

    # correlated raw style characteristics with sector-level tilts
    raw_corr = _STYLE_CORR[1:, 1:].copy()
    raw_corr = np.delete(np.delete(raw_corr, 4, 0), 4, 1)  # drop Size (from cap)
    L = np.linalg.cholesky(raw_corr)
    Z = rng.standard_normal((n, 6)) @ L.T
    sector_tilt = rng.normal(0.0, 0.5, (len(SECTORS), 6))
    Z += sector_tilt[sec]
    value, growth, mom, quality, lowvol, prof = Z.T

    beta = 1.0 + 0.25 * rng.standard_normal(n) + rng.normal(0, 0.15, len(SECTORS))[sec]
    lowvol = lowvol - 1.5 * (beta - 1.0)
    size = log_cap

    exposures = {
        "Market": beta - b @ beta + 1.0,  # benchmark beta = 1
        "Value": _cap_standardise(value, b),
        "Growth": _cap_standardise(growth, b),
        "Momentum": _cap_standardise(mom, b),
        "Quality": _cap_standardise(quality, b),
        "Size": _cap_standardise(size, b),
        "LowVol": _cap_standardise(lowvol, b),
        "Profitability": _cap_standardise(prof, b),
    }
    styles = pd.DataFrame(exposures, index=ids)[list(STYLES)]

    alpha = _cap_standardise(rng.standard_normal(n), b)
    scores = styles.copy()
    scores["Market"] = styles["Market"] - 1.0
    scores["Alpha"] = alpha

    # last period's signals: slow styles barely move, momentum/alpha decay
    persistence = {"Market": 0.98, "Value": 0.95, "Growth": 0.93, "Momentum": 0.55,
                   "Quality": 0.95, "Size": 0.99, "LowVol": 0.95, "Profitability": 0.93,
                   "Alpha": 0.30}
    prior_scores = scores.copy()
    for k, rho in persistence.items():
        prior_scores[k] = rho * scores[k] + np.sqrt(1 - rho**2) * scores[k].std() * rng.standard_normal(n)

    # specific vol: smaller caps are noisier
    spec_vol = np.clip(0.24 - 0.06 * exposures["Size"] + 0.04 * rng.standard_normal(n), 0.12, 0.60)
    spec_var = spec_vol**2

    # twin-stock residual links inside a sector
    pair_cols, pair_var, pair_names = [], [], []
    used: set[int] = set()
    while len(pair_cols) < n_pairs:
        s = rng.integers(len(SECTORS))
        members = [i for i in np.flatnonzero(sec == s) if i not in used]
        if len(members) < 2:
            continue
        i, j = rng.choice(members, 2, replace=False)
        used.update((i, j))
        c = min(0.6 * spec_vol[i] * spec_vol[j], 0.7 * min(spec_var[i], spec_var[j]))
        col = np.zeros(n)
        col[[i, j]] = 1.0
        pair_cols.append(col)
        pair_var.append(c)
        pair_names.append(f"pair:{ids[i]}~{ids[j]}")
    P = np.column_stack(pair_cols)
    d = spec_var - P @ np.array(pair_var)

    X = np.column_stack([
        styles.to_numpy(),
        np.eye(len(SECTORS))[sec],
        np.eye(len(COUNTRIES))[cty],
        P,
    ])
    F = _STYLE_CORR * np.outer(_STYLE_VOL, _STYLE_VOL)
    Phi = np.zeros((X.shape[1], X.shape[1]))
    k0 = len(STYLES)
    Phi[:k0, :k0] = F
    k1 = k0 + len(SECTORS)
    Phi[k0:k1, k0:k1] = np.eye(len(SECTORS)) * _SECTOR_VOL**2
    k2 = k1 + len(COUNTRIES)
    Phi[k1:k2, k1:k2] = np.eye(len(COUNTRIES)) * _COUNTRY_VOL**2
    Phi[k2:, k2:] = np.diag(pair_var)

    columns = (*STYLES, *(f"sector:{s}" for s in SECTORS),
               *(f"country:{c}" for c in COUNTRIES), *pair_names)
    groups = (*["style"] * len(STYLES), *["sector"] * len(SECTORS),
              *["country"] * len(COUNTRIES), *["pair"] * n_pairs)
    cov = CovModel(X=X, Phi=Phi, d=d, columns=columns, groups=groups)

    return Universe(
        ids=ids,
        sector=pd.Series(np.array(SECTORS)[sec], index=ids, name="sector"),
        country=pd.Series(np.array(COUNTRIES)[cty], index=ids, name="country"),
        b=pd.Series(b, index=ids, name="benchmark"),
        styles=styles,
        scores=scores,
        prior_scores=prior_scores,
        cov=cov,
    )
