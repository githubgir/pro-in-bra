"""Download and parse Ken French industry portfolios, FF factors, and FRED macro series."""
import io
import os
import urllib.request
import zipfile

import numpy as np
import pandas as pd

FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
LEVELS = [5, 10, 12, 17, 30, 38, 48, 49]
RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def _fetch(url, path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        urllib.request.urlretrieve(url, path)
    return path


def _read_french_monthly(zip_path):
    """Return the first (value-weighted, monthly) block of a French CSV as decimal returns."""
    with zipfile.ZipFile(zip_path) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(","))
    rows = []
    for l in lines[start + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if len(parts[0]) != 6 or not parts[0].isdigit():
            break
        rows.append(parts)
    cols = [c.strip() for c in lines[start].split(",")[1:]]
    df = pd.DataFrame([r[1:] for r in rows], columns=cols,
                      index=pd.PeriodIndex([r[0] for r in rows], freq="M")).astype(float)
    df = df.mask(df <= -99.99)
    return df / 100.0


def industries(n):
    path = _fetch(f"{FRENCH}/{n}_Industry_Portfolios_CSV.zip", os.path.join(RAW, f"{n}_Industry_Portfolios_CSV.zip"))
    return _read_french_monthly(path)


def factors():
    path = _fetch(f"{FRENCH}/F-F_Research_Data_Factors_CSV.zip", os.path.join(RAW, "F-F_Research_Data_Factors_CSV.zip"))
    f = _read_french_monthly(path)
    f["Mkt"] = f["Mkt-RF"] + f["RF"]
    return f


def _fred(sid):
    path = _fetch(FRED.format(sid), os.path.join(RAW, f"{sid}.csv"))
    s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
    return pd.to_numeric(s, errors="coerce").dropna()


def macro_quarterly():
    """Quarterly growth / inflation 'surprise' proxies.

    growth    : YoY real GDP growth (%)
    inflation : YoY CPI inflation (%), CPI averaged within the quarter
    dG, dI    : quarter-on-quarter change in those YoY rates -> 'rising' vs 'falling'
    """
    gdp = _fred("GDPC1")
    gdp.index = gdp.index.to_period("Q")
    cpi = _fred("CPIAUCSL")
    cpi = cpi.groupby(cpi.index.to_period("Q")).mean()
    m = pd.DataFrame({"growth": 100 * np.log(gdp).diff(4), "inflation": 100 * np.log(cpi).diff(4)})
    m["dG"] = m["growth"].diff()
    m["dI"] = m["inflation"].diff()
    return m.dropna()


def to_quarterly(monthly):
    """Compound monthly returns into calendar-quarter returns (NaN if any month missing)."""
    g = (1 + monthly).groupby(monthly.index.asfreq("Q"))
    q = g.prod(min_count=3) - 1
    q[g.count() < 3] = np.nan
    return q
