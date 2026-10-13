"""Rolling correlation of Japanese equities (Nikkei 225) with the yen, last 20 years.

Run:  python run_study.py [--refresh]
Downloads FRED data into data/, writes tables to output/tables, figures to output/figures.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from data_prep import build_returns, load_levels

OUT = Path(__file__).parent / "output"
TAB, FIG = OUT / "tables", OUT / "figures"
YEARS = 20
# window label -> (frequency, observations)
WINDOWS = {"3m_daily": ("D", 63), "1y_daily": ("D", 252), "1y_weekly": ("W", 52), "3y_weekly": ("W", 156)}


def rolling_corr(r: pd.DataFrame, n: int) -> pd.Series:
    return r["nikkei_ret"].rolling(n, min_periods=n).corr(r["jpy_ret"])


def main(refresh: bool = False):
    TAB.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    end = load_levels("1900", refresh).index[-1]
    # load the extra history needed so the longest window is populated from day one
    start = end - pd.DateOffset(years=YEARS)
    levels = load_levels(str((start - pd.DateOffset(years=3, weeks=2)).date()))
    rets = {f: build_returns(levels, f) for f in ("D", "W")}

    roll = {k: rolling_corr(rets[f], n).loc[start:] for k, (f, n) in WINDOWS.items()}
    daily = pd.concat({k: v for k, v in roll.items() if WINDOWS[k][0] == "D"}, axis=1)
    weekly = pd.concat({k: v for k, v in roll.items() if WINDOWS[k][0] == "W"}, axis=1)
    daily.to_csv(TAB / "rolling_corr_daily.csv")
    weekly.to_csv(TAB / "rolling_corr_weekly.csv")

    full = {f: r.loc[start:] for f, r in rets.items()}
    by_year = full["W"].groupby(full["W"].index.year).apply(lambda g: g["nikkei_ret"].corr(g["jpy_ret"]))
    by_year.rename("weekly_corr").to_csv(TAB / "calendar_year_corr_weekly.csv")

    summary = {
        "sample": [str(start.date()), str(end.date())],
        "full_sample_corr": {f: round(r["nikkei_ret"].corr(r["jpy_ret"]), 3) for f, r in full.items()},
        "rolling": {k: {"latest": round(v.dropna().iloc[-1], 3), "mean": round(v.mean(), 3),
                        "min": round(v.min(), 3), "min_date": str(v.idxmin().date()),
                        "max": round(v.max(), 3), "max_date": str(v.idxmax().date()),
                        "pct_negative": round((v.dropna() < 0).mean(), 3)} for k, v in roll.items()},
    }
    (OUT / "results.json").write_text(json.dumps(summary, indent=2))

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for ax, df, title in ((axes[0], daily, "Daily log returns"), (axes[1], weekly, "Weekly log returns (Fri-Fri)")):
        for c in df:
            ax.plot(df.index, df[c], lw=1.1 if "1y" in c else 0.7, label=c.replace("_", " "))
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_ylim(-1, 1)
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_ylabel("correlation")
        ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("Rolling correlation: Nikkei 225 vs yen strength (JPY per USD inverted)\n"
                 "negative = Nikkei falls when the yen appreciates", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "rolling_corr.png", dpi=130)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
