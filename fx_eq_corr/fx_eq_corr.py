"""Rolling correlation between equity indices and their currency vs USD, using FRED data.

FX returns are signed so that positive = the non-USD currency appreciates vs USD:
    JPY : -dlog(DEXJPUS)   (DEXJPUS = JPY per USD)
    CHF : -dlog(DEXSZUS)   (DEXSZUS = CHF per USD)
    EUR : +dlog(DEXUSEU)   (DEXUSEU = USD per EUR; EUR up = USD down)

Pairs
    jpy_nikkei   NIKKEI225 (daily)              vs JPY, weekly returns
    eur_nasdaq   NASDAQCOM (daily)              vs EUR, weekly returns
    eur_sp500    SP500 (daily, FRED keeps 10y)  vs EUR, weekly returns
    chf_oecd     OECD Swiss share prices (monthly, SPASTT01CHM661N) vs CHF, monthly
    usd_oecd     OECD US share prices    (monthly, SPASTT01USM661N) vs EUR, monthly
    jpy_oecd     OECD Japan share prices (monthly, SPASTT01JPM661N) vs JPY, monthly

FRED carries no SMI series, so Switzerland uses the OECD monthly index. OECD share
price indices are monthly averages of daily prices, so the matching FX series is
also averaged by month. The monthly OECD pairs give a like-for-like cross-country
comparison.

Daily FX is the NY noon fix, which is non-synchronous with Asian/European closes,
hence weekly (Fri-Fri) returns for the daily index pairs.

Usage: python fx_eq_corr.py [--years 20] [--outdir output]
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

FX = {  # FRED id, sign so that + = currency appreciates vs USD
    "JPY": ("DEXJPUS", -1),
    "CHF": ("DEXSZUS", -1),
    "EUR": ("DEXUSEU", +1),
}

WEEKLY_WINDOWS = {"26w": 26, "52w": 52, "3y": 156}
MONTHLY_WINDOWS = {"12m": 12, "24m": 24, "3y": 36}

PAIRS = {
    "jpy_nikkei": dict(eq="NIKKEI225", eq_name="Nikkei 225", ccy="JPY", freq="W"),
    "eur_nasdaq": dict(eq="NASDAQCOM", eq_name="Nasdaq Composite", ccy="EUR", freq="W"),
    "eur_sp500": dict(eq="SP500", eq_name="S&P 500 (10y on FRED)", ccy="EUR", freq="W"),
    "chf_oecd": dict(eq="SPASTT01CHM661N", eq_name="Swiss share prices (OECD)", ccy="CHF", freq="M"),
    "usd_oecd": dict(eq="SPASTT01USM661N", eq_name="US share prices (OECD)", ccy="EUR", freq="M"),
    "jpy_oecd": dict(eq="SPASTT01JPM661N", eq_name="Japan share prices (OECD)", ccy="JPY", freq="M"),
}


class Fred:
    def __init__(self, start: str, cache: Path):
        self.start, self.cache, self._mem = start, cache, {}

    def __call__(self, sid: str) -> pd.Series:
        if sid not in self._mem:
            r = requests.get(FRED_URL.format(sid=sid, start=self.start), timeout=60)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text), na_values=".")
            df.columns = ["date", sid]
            df["date"] = pd.to_datetime(df["date"])
            s = df.set_index("date")[sid].astype(float).dropna()
            s.to_csv(self.cache / f"{sid}.csv")
            self._mem[sid] = s
        return self._mem[sid]


def pair_returns(fred: Fred, cfg: dict) -> pd.DataFrame:
    fx_id, sign = FX[cfg["ccy"]]
    eq, fx = fred(cfg["eq"]), fred(fx_id)
    if cfg["freq"] == "W":
        # stop at the last date both series have, and keep only complete weeks,
        # so stale forward-filled prices never create artificial zero returns
        last = min(eq.index[-1], fx.index[-1])
        lv = pd.DataFrame({"eq": eq, "fx": fx}).loc[:last].ffill().resample("W-FRI").last()
        lv = lv.loc[:last]
    else:  # OECD index is a monthly average -> average FX over the month too
        fx_m = fx.resample("MS").mean()
        if fx.index[-1] < fx_m.index[-1] + pd.offsets.MonthEnd(0) - pd.Timedelta(days=7):
            fx_m = fx_m.iloc[:-1]  # drop a month with too little FX history for a fair average
        lv = pd.DataFrame({"eq": eq.resample("MS").last(), "fx": fx_m})
    r = np.log(lv.dropna()).diff().dropna()
    return pd.DataFrame({"eq": r["eq"], "fx": sign * r["fx"]})


def rolling(r: pd.DataFrame, windows: dict) -> pd.DataFrame:
    return pd.DataFrame({k: r["eq"].rolling(w, min_periods=int(w * 0.8)).corr(r["fx"])
                         for k, w in windows.items()})


def plot_pair(name, cfg, corr, r, out):
    fig, ax = plt.subplots(figsize=(12, 5))
    styles = [dict(lw=0.8, color="#9aa7b8"), dict(lw=1.6, color="#1f4e8c"), dict(lw=1.6, color="#c0392b")]
    for col, st in zip(corr.columns, styles):
        ax.plot(corr.index, corr[col], label=col, **st)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Correlation")
    unit = "weekly" if cfg["freq"] == "W" else "monthly"
    ax.set_title(f"Rolling correlation: {cfg['eq_name']} vs {cfg['ccy']} (+ = {cfg['ccy']} up vs USD), "
                 f"{unit} returns  -  full-sample {r.corr().iloc[0, 1]:+.2f}")
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"{name}.png", dpi=130)
    plt.close(fig)


def plot_compare(series: dict, title: str, path: Path):
    colors = ["#1f4e8c", "#c0392b", "#e67e22", "#27ae60"]
    fig, ax = plt.subplots(figsize=(12, 5))
    for (lab, s), c in zip(series.items(), colors):
        ax.plot(s.index, s, lw=1.6, color=c, label=lab)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Correlation")
    ax.set_title(title)
    ax.legend(loc="upper left", frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=20)
    ap.add_argument("--outdir", default=str(Path(__file__).parent / "output"))
    args = ap.parse_args()

    out = Path(args.outdir)
    (out / "data").mkdir(parents=True, exist_ok=True)
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=args.years)
    # extra history so the 3y rolling window is populated from `start`
    fred = Fred((start - pd.DateOffset(years=3)).strftime("%Y-%m-%d"), out / "data")

    summary, latest, corrs = [], {}, {}
    for name, cfg in PAIRS.items():
        r = pair_returns(fred, cfg)
        corr = rolling(r, WEEKLY_WINDOWS if cfg["freq"] == "W" else MONTHLY_WINDOWS).loc[start:]
        r = r.loc[start:]
        corrs[name] = corr
        corr.to_csv(out / f"rolling_corr_{name}.csv", float_format="%.4f")
        plot_pair(name, cfg, corr, r, out)

        min_obs = 20 if cfg["freq"] == "W" else 6
        yearly = r.groupby(r.index.year).apply(
            lambda g: g["eq"].corr(g["fx"]) if len(g) >= min_obs else np.nan).dropna()
        summary += [
            f"=== {name}: {cfg['eq_name']} ({cfg['eq']}) vs {cfg['ccy']} ({FX[cfg['ccy']][0]}) ===",
            f"Sample {r.index[0].date()} to {r.index[-1].date()}, {len(r)} "
            f"{'weekly' if cfg['freq'] == 'W' else 'monthly'} obs; full-sample corr {r.corr().iloc[0, 1]:+.3f}",
            corr.describe().T[["mean", "min", "25%", "50%", "75%", "max"]].round(3).to_string(),
            f"latest: {corr.dropna().iloc[-1].round(3).to_dict()}",
            "by calendar year: " + ", ".join(f"{y}:{v:+.2f}" for y, v in yearly.items()),
            "",
        ]
        latest[name] = {"full_sample": r.corr().iloc[0, 1],
                        "pre_2020": r.loc[:"2019"].corr().iloc[0, 1],
                        "2020_on": r.loc["2020":].corr().iloc[0, 1],
                        **corr.dropna().iloc[-1].to_dict()}

    table = pd.DataFrame(latest).T.round(3)
    text = "Summary (full-sample / sub-period corr and latest rolling values)\n" \
        + table.to_string(na_rep="") \
        + "\n\n" + "\n".join(summary)
    (out / "summary.txt").write_text(text)
    print(text)

    plot_compare({"Japan (OECD) vs JPY": corrs["jpy_oecd"]["3y"],
                  "Switzerland (OECD) vs CHF": corrs["chf_oecd"]["3y"],
                  "US (OECD) vs EUR": corrs["usd_oecd"]["3y"]},
                 "3y rolling correlation, monthly returns: local equities vs currency (+ = currency up vs USD)",
                 out / "compare_monthly_3y.png")
    plot_compare({"Nikkei 225 vs JPY": corrs["jpy_nikkei"]["52w"],
                  "Nasdaq vs EUR": corrs["eur_nasdaq"]["52w"],
                  "S&P 500 vs EUR": corrs["eur_sp500"]["52w"]},
                 "52w rolling correlation, weekly returns: equities vs currency (+ = currency up vs USD)",
                 out / "compare_weekly_52w.png")


if __name__ == "__main__":
    main()
