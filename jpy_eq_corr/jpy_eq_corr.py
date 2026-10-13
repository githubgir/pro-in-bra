"""Rolling correlation between Japanese equities and the yen, using FRED data.

Series (FRED):
    NIKKEI225 : Nikkei 225 Stock Average, daily close (price index, JPY)
    DEXJPUS   : Japanese Yen to U.S. Dollar spot rate, JPY per USD (NY noon buying rate)

Yen return is defined as -dlog(DEXJPUS): positive = yen appreciates vs USD.
The Nikkei closes in Tokyo before the NY noon FX fix, so daily returns are
non-synchronous; weekly (Fri-Fri) returns are the primary measure.

Usage: python jpy_eq_corr.py [--years 20] [--outdir output]
"""
import argparse
import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
SERIES = {"NIKKEI225": "nikkei", "DEXJPUS": "usdjpy"}


def fetch_fred(sid: str, start: str) -> pd.Series:
    r = requests.get(FRED_URL.format(sid=sid, start=start), timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), na_values=".")
    df.columns = ["date", sid]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[sid].astype(float).dropna()


def load_levels(start: str, cache: Path) -> pd.DataFrame:
    frames = {}
    for sid, name in SERIES.items():
        s = fetch_fred(sid, start)
        s.to_csv(cache / f"{sid}.csv")
        frames[name] = s
    return pd.DataFrame(frames)


def returns(levels: pd.DataFrame, freq: str | None) -> pd.DataFrame:
    lv = levels.dropna() if freq is None else levels.ffill().resample(freq).last()
    r = np.log(lv).diff().dropna()
    return pd.DataFrame({"nikkei": r["nikkei"], "jpy": -r["usdjpy"]})


def rolling_corr(r: pd.DataFrame, window: int) -> pd.Series:
    return r["nikkei"].rolling(window, min_periods=int(window * 0.8)).corr(r["jpy"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--outdir", default=str(Path(__file__).parent / "output"))
    args = ap.parse_args()

    out = Path(args.outdir)
    (out / "data").mkdir(parents=True, exist_ok=True)

    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=args.years)
    # extra year of history so the first rolling window is full at `start`
    levels = load_levels((start - pd.DateOffset(years=1)).strftime("%Y-%m-%d"), out / "data")

    rd = returns(levels, None)          # daily, common trading days
    rw = returns(levels, "W-FRI")       # weekly Fri-Fri

    corr = pd.DataFrame({
        "weekly_26w": rolling_corr(rw, 26),
        "weekly_52w": rolling_corr(rw, 52),
        "weekly_156w": rolling_corr(rw, 156),
    })
    corr_d = pd.DataFrame({
        "daily_63d": rolling_corr(rd, 63),
        "daily_252d": rolling_corr(rd, 252),
    })
    corr, corr_d = corr.loc[start:], corr_d.loc[start:]
    rw_s, rd_s = rw.loc[start:], rd.loc[start:]

    corr.to_csv(out / "rolling_corr_weekly.csv", float_format="%.4f")
    corr_d.to_csv(out / "rolling_corr_daily.csv", float_format="%.4f")

    # summary
    lines = [
        f"Sample: {rw_s.index[0].date()} to {rw_s.index[-1].date()} "
        f"({len(rw_s)} weekly / {len(rd_s)} daily obs)",
        f"Full-sample corr  weekly: {rw_s.corr().iloc[0, 1]:+.3f}   daily: {rd_s.corr().iloc[0, 1]:+.3f}",
        "",
        "Rolling correlation distribution:",
        pd.concat([corr, corr_d], axis=1, sort=True).describe().T[["mean", "min", "25%", "50%", "75%", "max"]]
        .round(3).to_string(),
        "",
        "Latest values:",
        pd.Series({**corr.dropna().iloc[-1].to_dict(), **corr_d.dropna().iloc[-1].to_dict()}).round(3).to_string(),
        "",
        "Full-period weekly corr by calendar year:",
        rw_s.groupby(rw_s.index.year).apply(lambda g: g.corr().iloc[0, 1]).round(3).to_string(),
    ]
    summary = "\n".join(lines)
    (out / "summary.txt").write_text(summary + "\n")
    print(summary)

    # plot
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    ax = axes[0]
    ax.plot(corr.index, corr["weekly_26w"], lw=0.8, color="#9aa7b8", label="26w (weekly returns)")
    ax.plot(corr.index, corr["weekly_52w"], lw=1.6, color="#1f4e8c", label="52w (weekly returns)")
    ax.plot(corr.index, corr["weekly_156w"], lw=1.6, color="#c0392b", label="3y (weekly returns)")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Correlation")
    ax.set_title("Rolling correlation: Nikkei 225 vs JPY (yen appreciation vs USD)  -  FRED NIKKEI225, DEXJPUS")
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.grid(alpha=0.3)

    ax2 = axes[1]
    lv = levels.loc[start:].ffill()
    ax2.plot(lv.index, lv["nikkei"], color="#1f4e8c", lw=1)
    ax2.set_ylabel("Nikkei 225", color="#1f4e8c")
    ax3 = ax2.twinx()
    ax3.plot(lv.index, lv["usdjpy"], color="#e67e22", lw=1)
    ax3.set_ylabel("USD/JPY (JPY per USD)", color="#e67e22")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "rolling_corr.png", dpi=130)


if __name__ == "__main__":
    main()
