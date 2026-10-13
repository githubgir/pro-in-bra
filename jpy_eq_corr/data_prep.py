"""Download Nikkei 225 and USD/JPY from FRED and build aligned return series.

FRED series
  NIKKEI225 : Nikkei Stock Average, index level (Tokyo close, price index, no dividends)
  DEXJPUS   : Japanese yen per US dollar, noon buying rate in New York

Sign convention: DEXJPUS rises when the yen weakens. ``jpy_ret`` is the return on
holding yen versus the dollar (i.e. -log change of DEXJPUS), so a positive value
means yen appreciation.
"""
from io import StringIO
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
SERIES = {"NIKKEI225": "nikkei", "DEXJPUS": "usdjpy"}
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def fetch_fred(sid: str, refresh: bool = False) -> pd.Series:
    """Return a FRED series, cached as data/<sid>.csv. FRED codes missing values as '.'."""
    path = DATA / f"{sid}.csv"
    if refresh or not path.exists():
        with urlopen(FRED_CSV.format(sid=sid), timeout=60) as resp:
            text = resp.read().decode()
        DATA.mkdir(exist_ok=True)
        path.write_text(text)
    df = pd.read_csv(path, na_values=".")
    df = df.set_index(pd.to_datetime(df.iloc[:, 0])).iloc[:, 1]
    return pd.to_numeric(df, errors="coerce").dropna().rename(sid)


def load_levels(start: str, refresh: bool = False) -> pd.DataFrame:
    """Daily levels on dates where both markets have a fix (inner join)."""
    lv = pd.concat([fetch_fred(s, refresh).rename(n) for s, n in SERIES.items()], axis=1, join="inner")
    return lv.loc[start:]


def build_returns(levels: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Log returns at daily ('D') or weekly Friday-to-Friday ('W') frequency.

    Weekly returns are the main specification: the Nikkei closes in Tokyo ~15 hours
    before the New York noon FX fix, so daily returns are asynchronous and bias the
    daily correlation towards zero. Over a week the overlap is ~6/7 of the period.
    """
    lv = levels if freq == "D" else levels.resample("W-FRI").last().dropna()
    r = np.log(lv).diff().dropna()
    return pd.DataFrame({"nikkei_ret": r["nikkei"], "jpy_ret": -r["usdjpy"]})
