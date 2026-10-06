"""Load Shiller's ie_data.xls and build aligned monthly stock / bond series."""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_FILE = Path(__file__).parent / "data" / "ie_data.xls"

# Before 1953 Shiller's long rate is an annual series linearly interpolated to
# monthly, so monthly rate changes are constant within each year.  GS10 is a
# genuine monthly series from April 1953; the first clean monthly change is May 1953.
MONTHLY_RATES_START = "1953-05"


def load_raw(path=DATA_FILE) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Data", header=None, skiprows=8)
    raw = raw[pd.to_numeric(raw[0], errors="coerce").notna()].reset_index(drop=True)
    # Shiller's date column is a float (1871.1 == October), so build the index by position
    idx = pd.period_range("1871-01", periods=len(raw), freq="M")
    first = float(raw[0].iloc[0])
    assert abs(first - 1871.01) < 1e-9, first
    df = pd.DataFrame(
        {
            "P": raw[1].values, "D": raw[2].values, "CPI": raw[4].values, "GS10": raw[6].values,
            "bond_gross_fwd": raw[17].values,  # Shiller: nominal bond return from month t to t+1
        },
        index=idx,
    ).apply(pd.to_numeric, errors="coerce")
    return df


def build_returns(df: pd.DataFrame | None = None, end: str = "2026-08") -> pd.DataFrame:
    """Monthly nominal series, labelled by the month in which the return ends.

    stock_ret : S&P Composite total return (P_t + D_t/12) / P_{t-1} - 1
    d_rate    : change in long rate, percentage points (spec A)
    bond_ret  : Shiller 10y Treasury total return, t-1 -> t (spec B)
    """
    df = load_raw() if df is None else df
    # The final month (Sept 2026) is a 1st-of-month snapshot rather than a monthly
    # average, so it is excluded. Dividends for the last months are not yet published:
    # carry the last value forward (dividends are smooth; effect on returns ~0.01%).
    df = df.loc[:end].copy()
    df["D"] = df["D"].ffill()
    out = pd.DataFrame(index=df.index)
    out["stock_ret"] = (df["P"] + df["D"] / 12) / df["P"].shift(1) - 1
    out["d_rate"] = df["GS10"].diff()
    out["bond_ret"] = df["bond_gross_fwd"].shift(1) - 1
    out["infl"] = df["CPI"].pct_change()
    out["stock_real"] = (1 + out["stock_ret"]) / (1 + out["infl"]) - 1
    out["bond_real"] = (1 + out["bond_ret"]) / (1 + out["infl"]) - 1
    return out.dropna(subset=["stock_ret", "d_rate", "bond_ret"])


SPECS = {
    # label -> (x column, y column, description)
    "B_bond_return": ("stock_ret", "bond_ret", "Spec B: S&P total return vs 10y Treasury total return"),
    "A_rate_change": ("stock_ret", "d_rate", "Spec A: S&P total return vs change in 10y yield"),
}
