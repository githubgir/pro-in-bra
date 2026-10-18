"""Monthly return proxies for Bridgewater's All Weather asset classes.

precious metals : gold, monthly price (datahub.io gold-prices, LBMA-based); free-floating from 1968
TIPS            : iShares TIP ETF total return (Yahoo adjusted close), 2004+
commodities     : S&P GSCI (Yahoo ^SPGSCI) from 1985, spliced before with an equal-weight spot composite
                  of WTI oil, PPI metals and PPI farm products (FRED), plus T-bill collateral yield
govt bonds      : 10y constant-maturity Treasury total return built from FRED GS10 (carry + duration
                  + convexity)
cyclical equity : equal weight of French 10-industry Durbl, Manuf, HiTec, Shops
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd

from .data import RAW, _fetch, industries

ADIR = os.path.join(RAW, "assets")
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{}?period1=0&period2=9999999999&interval=1mo&events=div"


def _fred_m(sid):
    s = pd.read_csv(_fetch(FRED.format(sid), os.path.join(ADIR, f"{sid}.csv")), index_col=0, parse_dates=True).iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s.groupby(s.index.to_period("M")).last()


def _yahoo_m(sym, fname):
    path = os.path.join(ADIR, fname)
    if not os.path.exists(path):
        req = urllib.request.Request(YAHOO.format(sym), headers={"User-Agent": "Mozilla/5.0"})
        os.makedirs(ADIR, exist_ok=True)
        open(path, "wb").write(urllib.request.urlopen(req).read())
    d = json.load(open(path))["chart"]["result"][0]
    px = d["indicators"].get("adjclose", [{}])[0].get("adjclose") or d["indicators"]["quote"][0]["close"]
    s = pd.Series(px, index=pd.to_datetime(d["timestamp"], unit="s")).dropna()
    s = s.groupby(s.index.to_period("M")).last()
    return s


def gold():
    p = pd.read_csv(_fetch("https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv",
                           os.path.join(ADIR, "gold_datahub.csv")))
    s = pd.Series(p["Price"].values, index=pd.PeriodIndex(p["Date"], freq="M"))
    return s.pct_change().loc["1968-04":]


def tips():
    return _yahoo_m("TIP", "TIP.json").pct_change().loc["2004-01":]


def commodities(rf):
    gsci = _yahoo_m("%5ESPGSCI", "GSCI.json").pct_change().loc["1985-02":]
    parts = [np.log(_fred_m(s)).diff() for s in ("WTISPLC", "WPU10", "WPU01")]
    spot = np.exp(pd.concat(parts, axis=1).mean(axis=1)) - 1 + rf.reindex(parts[0].index)
    return pd.concat([spot.loc[:"1985-01"], gsci + rf.reindex(gsci.index)]).dropna()


def treasury10(maturity=10):
    y = _fred_m("GS10") / 100
    y0, y1 = y.shift(1), y
    # par bond priced at y0, revalued at y1 one month later (maturity ~unchanged for CMT)
    D = (1 - (1 + y0 / 2) ** (-2 * maturity)) / y0
    C = 2 / y0 ** 2 * (1 - (1 + y0 / 2) ** (-2 * maturity)) - 2 * maturity / (y0 * (1 + y0 / 2) ** (2 * maturity + 1))
    dy = y1 - y0
    return (y0 / 12 - D * dy + 0.5 * C * dy ** 2).dropna()


def cyclicals():
    x = industries(10)
    return x[["Durbl", "Manuf", "HiTec", "Shops"]].mean(axis=1)


def all_assets(rf):
    return pd.DataFrame({"Gold": gold(), "TIPS": tips(), "Commodities": commodities(rf),
                         "Treasuries": treasury10(), "Cyclicals": cyclicals()})
