"""Rolling correlation of USD and EUR (priced in local currency) with local equity markets.

For each market with local currency LOC, correlate
    equity index return in LOC   vs   dlog(price of 1 USD / 1 EUR in LOC)
so a positive FX return = the foreign currency appreciates, i.e. LOC weakens.
A negative correlation means the local currency strengthens when local equities
fall (safe-haven / funding-currency behaviour).

FX from FRED H.10 noon NY buying rates; EUR crosses (EUR/JPY, EUR/GBP, ...) are built
from the same fixings, so both legs are synchronous:
    DEXJPUS JPY per USD, DEXSZUS CHF per USD, DEXCAUS CAD per USD,
    DEXUSEU USD per EUR, DEXUSUK USD per GBP, DEXUSAL USD per AUD

Markets
    nikkei   NIKKEI225 (daily)                   LOC=JPY  weekly returns
    jp_oecd  OECD Japan share prices (monthly)   LOC=JPY  monthly
    ch_oecd  OECD Swiss share prices (monthly)   LOC=CHF  monthly  (FRED has no SMI)
    uk_oecd  OECD UK share prices (monthly)      LOC=GBP  monthly
    ca_oecd  OECD Canada share prices (monthly)  LOC=CAD  monthly
    au_oecd  OECD Australia share prices (monthly) LOC=AUD monthly
    nasdaq   NASDAQCOM (daily)                   LOC=USD  weekly
    sp500    SP500 (daily, FRED keeps 10y only)  LOC=USD  weekly
    us_oecd  OECD US share prices (monthly)      LOC=USD  monthly
    ez_oecd  OECD euro-area share prices (monthly) LOC=EUR monthly (FRED series ends Jan 2026)

The monthly OECD indices are the like-for-like cross-country comparison; FRED has
no daily equity index for UK, Canada, euro area, Switzerland or Australia.

OECD share price indices are monthly averages of daily prices, so FX is averaged by
month too. Daily FX (NY noon) is non-synchronous with Tokyo closes, hence weekly
(Fri-Fri) returns for the daily index series.

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

# value of one unit of each currency in USD, as (FRED id, exponent)
USD_VALUE = {"EUR": ("DEXUSEU", +1), "GBP": ("DEXUSUK", +1), "AUD": ("DEXUSAL", +1),
             "JPY": ("DEXJPUS", -1), "CHF": ("DEXSZUS", -1), "CAD": ("DEXCAUS", -1)}
FOREIGN = ["USD", "EUR"]

WEEKLY_WINDOWS = {"26w": 26, "52w": 52, "3y": 156}
MONTHLY_WINDOWS = {"12m": 12, "24m": 24, "3y": 36}

MARKETS = {
    "nikkei": dict(eq="NIKKEI225", name="Nikkei 225", loc="JPY", freq="W"),
    "jp_oecd": dict(eq="SPASTT01JPM661N", name="Japan share prices (OECD)", loc="JPY", freq="M"),
    "ch_oecd": dict(eq="SPASTT01CHM661N", name="Swiss share prices (OECD)", loc="CHF", freq="M"),
    "uk_oecd": dict(eq="SPASTT01GBM661N", name="UK share prices (OECD)", loc="GBP", freq="M"),
    "ca_oecd": dict(eq="SPASTT01CAM661N", name="Canada share prices (OECD)", loc="CAD", freq="M"),
    "au_oecd": dict(eq="SPASTT01AUM661N", name="Australia share prices (OECD)", loc="AUD", freq="M"),
    "nasdaq": dict(eq="NASDAQCOM", name="Nasdaq Composite", loc="USD", freq="W"),
    "sp500": dict(eq="SP500", name="S&P 500 (10y on FRED)", loc="USD", freq="W"),
    "us_oecd": dict(eq="SPASTT01USM661N", name="US share prices (OECD)", loc="USD", freq="M"),
    "ez_oecd": dict(eq="SPASTT01EZM661N", name="Euro-area share prices (OECD)", loc="EUR", freq="M"),
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


def fx_in_loc(fred: Fred, foreign: str, loc: str) -> pd.Series:
    """Daily price of one unit of `foreign` in units of `loc`."""
    def usd_value(ccy):
        if ccy == "USD":
            return None
        sid, p = USD_VALUE[ccy]
        return fred(sid) ** p

    num, den = usd_value(foreign), usd_value(loc)
    if den is None:
        return num
    if num is None:
        return 1.0 / den
    # cross rate: both legs are the same NY noon fixing, align on common dates
    return (num / den).dropna()


def market_returns(fred: Fred, cfg: dict) -> pd.DataFrame:
    """Returns: column 'eq' plus one FX column per foreign currency (price in LOC)."""
    eq = fred(cfg["eq"])
    fx = {f: fx_in_loc(fred, f, cfg["loc"]) for f in FOREIGN if f != cfg["loc"]}
    if cfg["freq"] == "W":
        # stop at the last date all series have and keep only complete weeks,
        # so stale forward-filled prices never create artificial zero returns
        last = min([eq.index[-1]] + [s.index[-1] for s in fx.values()])
        lv = pd.DataFrame({"eq": eq, **fx}).loc[:last].ffill().resample("W-FRI").last().loc[:last]
    else:  # OECD index is a monthly average -> average FX over the month too
        cols = {"eq": eq.resample("MS").last()}
        for f, s in fx.items():
            m = s.resample("MS").mean()
            if s.index[-1] < m.index[-1] + pd.offsets.MonthEnd(0) - pd.Timedelta(days=7):
                m = m.iloc[:-1]  # too little FX history in the last month for a fair average
            cols[f] = m
        lv = pd.DataFrame(cols)
    return np.log(lv.dropna()).diff().dropna()


def rolling(r: pd.DataFrame, f: str, windows: dict) -> pd.DataFrame:
    return pd.DataFrame({k: r["eq"].rolling(w, min_periods=int(w * 0.8)).corr(r[f])
                         for k, w in windows.items()})


def plot_market(key, cfg, corrs: dict, r, out):
    fig, ax = plt.subplots(figsize=(12, 5))
    colors = {"USD": "#1f4e8c", "EUR": "#c0392b"}
    long_w, short_w = list(corrs[next(iter(corrs))].columns)[-1], list(corrs[next(iter(corrs))].columns)[1]
    for f, c in corrs.items():
        ax.plot(c.index, c[short_w], lw=0.8, alpha=0.5, color=colors[f])
        ax.plot(c.index, c[long_w], lw=1.8, color=colors[f],
                label=f"{f}/{cfg['loc']}  ({short_w} thin, {long_w} thick)  full-sample {r['eq'].corr(r[f]):+.2f}")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Correlation")
    unit = "weekly" if cfg["freq"] == "W" else "monthly"
    ax.set_title(f"{cfg['name']} (in {cfg['loc']}) vs price of USD / EUR in {cfg['loc']}  -  {unit} returns"
                 f"\n+ = foreign currency up / {cfg['loc']} down")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"{key}.png", dpi=130)
    plt.close(fig)


def plot_compare(series: dict, title: str, path: Path):
    """series: label -> (Series, color, linestyle)"""
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for lab, (s, c, ls) in series.items():
        ax.plot(s.index, s, lw=1.6, color=c, ls=ls, label=lab)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Correlation")
    ax.set_title(title)
    ax.legend(loc="lower left", frameon=False, ncol=3, fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


FX_COLORS = {"USD": "#1f4e8c", "EUR": "#c0392b"}


def plot_grid(markets, all_corrs, path: Path):
    """Small multiples: 3y (thick) and 12m (thin) monthly rolling corr per market."""
    n = len(markets)
    ncol = 2
    nrow = -(-n // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 2.6 * nrow), sharex=True, sharey=True)
    axes = axes.ravel()
    for ax, (k, lab) in zip(axes, markets):
        loc = MARKETS[k]["loc"]
        for f in FOREIGN:
            if (k, f) not in all_corrs:
                continue
            c = all_corrs[(k, f)]
            ax.plot(c.index, c["12m"], lw=0.7, alpha=0.4, color=FX_COLORS[f])
            ax.plot(c.index, c["3y"], lw=1.8, color=FX_COLORS[f])
        ax.axhline(0, color="black", lw=0.6)
        ax.set_ylim(-1, 1)
        ax.set_title(f"{lab} (equities in {loc})", fontsize=10, loc="left")
        ax.grid(alpha=0.3)
    for i, ax in enumerate(axes[n:], start=n):
        ax.set_visible(False)
        axes[i - ncol].tick_params(labelbottom=True)  # panel above the gap needs date labels
    handles = [plt.Line2D([], [], color=c, lw=1.8) for c in FX_COLORS.values()]
    fig.legend(handles, ["price of USD in LOC", "price of EUR in LOC"], loc="lower right",
               bbox_to_anchor=(0.92, 0.1), frameon=False)
    fig.suptitle("Rolling corr of local equities (OECD, monthly, in LOC) with price of USD / EUR in LOC  -  "
                 "3y thick, 12m thin\n+ = local currency weakens as local equities rise")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_bars(table: pd.DataFrame, markets, path: Path):
    """Full-sample, pre-2020 and 2020+ correlations per market / FX pair (OECD monthly)."""
    names = [MARKETS[k]["name"] for k, _ in markets]
    t = table.loc[[ix for ix in table.index if ix[0] in names]]
    labels = [f"{dict((MARKETS[k]['name'], l) for k, l in markets)[m]}\n{fx}" for m, fx in t.index]
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(13, 5))
    for i, (col, color) in enumerate([("full_sample", "#34495e"), ("pre_2020", "#95a5a6"), ("2020_on", "#e67e22")]):
        ax.bar(x + (i - 1) * 0.27, t[col].astype(float), width=0.27, color=color, label=col.replace("_", " "))
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Correlation")
    ax.set_title("Local equities (OECD, monthly, in LOC) vs price of USD / EUR in LOC  (+ = LOC weakens as equities rise)")
    ax.legend(frameon=False)
    ax.grid(alpha=0.3, axis="y")
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

    summary, rows, all_corrs = [], {}, {}
    for key, cfg in MARKETS.items():
        r_full = market_returns(fred, cfg)
        r = r_full.loc[start:]
        windows = WEEKLY_WINDOWS if cfg["freq"] == "W" else MONTHLY_WINDOWS
        unit = "weekly" if cfg["freq"] == "W" else "monthly"
        min_obs = 20 if cfg["freq"] == "W" else 6
        corrs = {}
        summary.append(f"=== {key}: {cfg['name']} ({cfg['eq']}), LOC={cfg['loc']}, {unit} returns, "
                       f"{r.index[0].date()} to {r.index[-1].date()} ({len(r)} obs) ===")
        for f in [c for c in r.columns if c != "eq"]:
            pair = f"{f}/{cfg['loc']}"
            c = rolling(r_full, f, windows).loc[start:]
            corrs[f] = all_corrs[(key, f)] = c
            c.to_csv(out / f"rolling_corr_{key}_{f.lower()}.csv", float_format="%.4f")
            yearly = r.groupby(r.index.year).apply(
                lambda g: g["eq"].corr(g[f]) if len(g) >= min_obs else np.nan).dropna()
            summary += [
                f"--- vs {pair}: full-sample corr {r['eq'].corr(r[f]):+.3f}",
                c.describe().T[["mean", "min", "25%", "50%", "75%", "max"]].round(3).to_string(),
                f"latest: {c.dropna().iloc[-1].round(3).to_dict()}",
                "by calendar year: " + ", ".join(f"{y}:{v:+.2f}" for y, v in yearly.items()),
            ]
            last = c.dropna().iloc[-1]
            rows[(cfg["name"], pair)] = {
                "freq": unit,
                "full_sample": r["eq"].corr(r[f]),
                "pre_2020": r.loc[:"2019"].pipe(lambda d: d["eq"].corr(d[f])),
                "2020_on": r.loc["2020":].pipe(lambda d: d["eq"].corr(d[f])),
                "latest_1y": last.iloc[1] if cfg["freq"] == "W" else last.iloc[0],
                "latest_3y": last["3y"],
            }
        summary.append("")
        plot_market(key, cfg, corrs, r, out)

    table = pd.DataFrame(rows).T
    table.index.names = ["market (in LOC)", "FX (price in LOC)"]
    num = table.columns.drop("freq")
    table[num] = table[num].astype(float).round(3)
    table.to_csv(out / "summary_table.csv")
    text = ("Correlation of local equity returns with the price of USD / EUR in local currency\n"
            "(+ FX = local currency weakens). latest_1y = 52w (weekly) or 12m (monthly) window.\n\n"
            + table.to_string() + "\n\n" + "\n".join(summary))
    (out / "summary.txt").write_text(text)
    print(text)

    oecd = [("jp_oecd", "Japan"), ("uk_oecd", "UK"), ("us_oecd", "US"), ("ca_oecd", "Canada"),
            ("ez_oecd", "Euro area"), ("ch_oecd", "Switzerland"), ("au_oecd", "Australia")]
    plot_grid(oecd, all_corrs, out / "compare_monthly_3y.png")
    plot_bars(table, oecd, out / "compare_full_sample.png")

    c = {"JPY": "#1f4e8c", "USD": "#e67e22", "EUR": "#27ae60"}
    plot_compare({f"{lab}: {f}/{MARKETS[k]['loc']}": (all_corrs[(k, f)]["52w"], col, ls)
                  for k, lab, f, col, ls in [("nikkei", "Nikkei", "USD", c["JPY"], "-"),
                                             ("nikkei", "Nikkei", "EUR", c["JPY"], "--"),
                                             ("nasdaq", "Nasdaq", "EUR", c["USD"], "--"),
                                             ("sp500", "S&P 500", "EUR", c["EUR"], "--")]},
                 "52w rolling corr, weekly returns: equities (in LOC) vs price of USD (solid) / EUR (dashed) in LOC",
                 out / "compare_weekly_52w.png")


if __name__ == "__main__":
    main()
