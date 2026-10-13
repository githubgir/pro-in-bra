"""Rolling correlation of USD and EUR (priced in local currency) with local equity markets,
raw and with extreme returns excluded / jumps smoothed.

For each market with local currency LOC, correlate
    equity index return in LOC   vs   dlog(price of 1 USD / 1 EUR in LOC)
so a positive FX return = the foreign currency appreciates, i.e. LOC weakens.
A negative correlation means the local currency strengthens when local equities
rise (risk-on currency); positive = LOC strengthens when equities fall
(safe-haven / funding-currency behaviour).

Two estimators
    raw    : equal-weight rolling window (3y monthly / 52w weekly) on all returns
    robust : (1) exclude extreme observations - a period is dropped from a pair if
                 either return is more than Z_CUT robust sigmas from its trailing
                 median, scale = 1.4826 * MAD over the trailing lookback (5y)
                 (causal: uses only data before the observation);
             (2) exponentially weighted correlation with half-life N/2 (18m for the
                 3y window, 26w for 52w). An observation fades out gradually instead
                 of falling out of the window in one step, which removes the
                 "drop-off" jumps of the equal-weight window. (Matching the window's
                 average data age, com=(N-1)/2, was tested and is jumpier than the
                 raw window, because it puts more weight on the newest period.)
Jumps are measured by the largest and 95th-percentile absolute period-on-period
change of the rolling correlation.

FX from FRED H.10 noon NY buying rates; EUR crosses (EUR/JPY, EUR/GBP, ...) are built
from the same fixings, so both legs are synchronous.

Equities: OECD monthly local-currency share price indices (SPASTT01xxM661N) for all
markets - the like-for-like cross-country set (FRED has no daily index for most).
These are monthly averages of daily prices, so FX is averaged by month too.
Weekly cross-checks use the daily NIKKEI225, NASDAQCOM and SP500 (FRED keeps 10y).
CNY was tightly managed (de facto USD peg mid-2008 to mid-2010), so USD/CNY
correlations around that window carry little information.

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
USD_VALUE = {
    "EUR": ("DEXUSEU", +1), "GBP": ("DEXUSUK", +1), "AUD": ("DEXUSAL", +1),
    "JPY": ("DEXJPUS", -1), "CHF": ("DEXSZUS", -1), "CAD": ("DEXCAUS", -1),
    "CNY": ("DEXCHUS", -1), "INR": ("DEXINUS", -1), "BRL": ("DEXBZUS", -1), "MXN": ("DEXMXUS", -1),
}
FOREIGN = ["USD", "EUR"]

FREQ = {  # rolling window, short window, outlier lookback, min history for z-scores (periods)
    "M": dict(window=36, label="3y", short=12, lookback=60, min_hist=24, unit="monthly"),
    "W": dict(window=52, label="52w", short=26, lookback=260, min_hist=104, unit="weekly"),
}
Z_CUT = 3.0


def oecd(cc, name, loc, group):
    return dict(eq=f"SPASTT01{cc}M661N", name=name, loc=loc, freq="M", group=group)


MARKETS = {
    "jp": oecd("JP", "Japan", "JPY", "DM"),
    "uk": oecd("GB", "UK", "GBP", "DM"),
    "us": oecd("US", "US", "USD", "DM"),
    "ca": oecd("CA", "Canada", "CAD", "DM"),
    "ez": oecd("EZ", "Euro area", "EUR", "DM"),  # FRED series ends Jan 2026
    "ch": oecd("CH", "Switzerland", "CHF", "DM"),
    "au": oecd("AU", "Australia", "AUD", "DM"),
    "cn": oecd("CN", "China", "CNY", "EM"),
    "in": oecd("IN", "India", "INR", "EM"),
    "br": oecd("BR", "Brazil", "BRL", "EM"),
    "mx": oecd("MX", "Mexico", "MXN", "EM"),
    "nikkei": dict(eq="NIKKEI225", name="Nikkei 225", loc="JPY", freq="W", group="weekly"),
    "nasdaq": dict(eq="NASDAQCOM", name="Nasdaq Composite", loc="USD", freq="W", group="weekly"),
    "sp500": dict(eq="SP500", name="S&P 500 (10y)", loc="USD", freq="W", group="weekly"),
}
GROUPS = {"DM": "Developed markets", "EM": "Emerging markets", "weekly": "Daily indices, weekly returns"}


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
    return (num / den).dropna()  # cross from the same NY noon fixing


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


def robust_z(x: pd.Series, lookback: int, min_hist: int) -> pd.Series:
    """Causal robust z-score: distance from trailing median in units of 1.4826*MAD."""
    past = x.shift(1)
    med = past.rolling(lookback, min_periods=min_hist).median()
    mad = (past - med).abs().rolling(lookback, min_periods=min_hist).median() * 1.4826
    # floor the scale so near-pegged stretches (e.g. CNY 2008-10) don't flag every move
    scale = np.maximum(mad, 0.25 * past.rolling(lookback, min_periods=min_hist).std())
    return (x - med) / scale


def pair_corr(r: pd.DataFrame, f: str, fp: dict) -> pd.DataFrame:
    """Raw and robust rolling correlations for equity vs FX column f."""
    n = fp["window"]
    d = r[["eq", f]]
    z = pd.concat([robust_z(d[c], fp["lookback"], fp["min_hist"]) for c in d], axis=1)
    extreme = (z.abs() > Z_CUT).any(axis=1)
    clean = d[~extreme]
    out = pd.DataFrame({
        "raw": d["eq"].rolling(n, min_periods=int(n * 0.8)).corr(d[f]),
        "raw_short": d["eq"].rolling(fp["short"], min_periods=int(fp["short"] * 0.8)).corr(d[f]),
        "trimmed": clean["eq"].rolling(n, min_periods=int(n * 0.8)).corr(clean[f]),
        "robust": clean["eq"].ewm(halflife=n / 2, min_periods=int(n * 0.8)).corr(clean[f]),
    }, index=d.index)
    # excluded periods carry the last estimate forward
    out[["trimmed", "robust"]] = out[["trimmed", "robust"]].ffill()
    out["excluded"] = extreme.astype(int)
    return out


def jumps(s: pd.Series) -> tuple[float, float]:
    """(max, 95th pct) absolute period-on-period change of a rolling correlation."""
    d = s.diff().abs()
    return d.max(), d.quantile(0.95)


def plot_group(keys, all_corr, title, path):
    """Rows = markets, col 1 = price of USD in LOC, col 2 = price of EUR in LOC."""
    nrow = len(keys)
    h = 2.0 * nrow + 1.2
    fig, axes = plt.subplots(nrow, 2, figsize=(13, h), sharex=True, sharey=True, squeeze=False)
    for i, k in enumerate(keys):
        cfg = MARKETS[k]
        for j, f in enumerate(FOREIGN):
            ax = axes[i, j]
            ax.set_ylim(-1, 1)
            if (k, f) not in all_corr:
                ax.set_title(f"{cfg['name']}: {f}/{cfg['loc']}", fontsize=9.5, loc="left")
                ax.text(0.5, 0.5, f"n/a (local currency is {f})", transform=ax.transAxes,
                        ha="center", va="center", color="#7f8c8d")
                continue
            ax.axhline(0, color="black", lw=0.6)
            ax.grid(alpha=0.3)
            c = all_corr[(k, f)]
            ax.plot(c.index, c["raw"], lw=1.0, color="#9aa7b8")
            ax.plot(c.index, c["robust"], lw=1.8, color="#1f4e8c" if f == "USD" else "#c0392b")
            ex = c.index[c["excluded"] == 1]
            ax.plot(ex, np.full(len(ex), -0.93), "|", color="#e67e22", ms=7, mew=1.2)
            ax.set_title(f"{cfg['name']}: {f}/{cfg['loc']}   ({len(ex)} of {len(c)} periods excluded)",
                         fontsize=9.5, loc="left")
    for j, f in enumerate(FOREIGN):
        axes[0, j].annotate(f"Price of {f} in LOC", xy=(0.5, 1.2), xycoords="axes fraction",
                            ha="center", fontsize=11, weight="bold")
    fp = FREQ[MARKETS[keys[0]]["freq"]]
    handles = [plt.Line2D([], [], color="#9aa7b8", lw=1.0),
               plt.Line2D([], [], color="#34495e", lw=1.8),
               plt.Line2D([], [], color="#e67e22", ls="none", marker="|", ms=7, mew=1.2)]
    fig.legend(handles, [f"raw: equal-weight {fp['label']} window, all returns",
                         f"robust: extremes (|z|>{Z_CUT:g}) excluded, exp. weighted (half-life {fp['window'] // 2} "
                         f"{'months' if fp['unit'] == 'monthly' else 'weeks'})",
                         "excluded period"],
               loc="upper center", bbox_to_anchor=(0.5, 1 - 0.5 / h), ncol=3, frameon=False, fontsize=9)
    fig.suptitle(f"{title}: local equities ({fp['unit']}, in LOC) vs price of USD / EUR in LOC  "
                 f"(+ = LOC weakens as equities rise)", y=1 - 0.12 / h)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.75 / h), h_pad=1.2)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_bars(table: pd.DataFrame, path: Path):
    t = table[table["freq"] == "monthly"]
    labels = [f"{m}\n{fx}" for m, fx in t.index]
    x = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(15, 5))
    spec = [("full_raw", "#9aa7b8", "full sample, raw"),
            ("full_robust", "#34495e", "full sample, extremes excluded"),
            ("pre_2020_robust", "#95a5a6", "pre-2020, extremes excluded"),
            ("since_2020_robust", "#e67e22", "2020+, extremes excluded")]
    w = 0.2
    for i, (col, color, lab) in enumerate(spec):
        ax.bar(x + (i - 1.5) * w, t[col].astype(float), width=w, color=color, label=lab)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel("Correlation")
    ax.set_title("Local equities (OECD, monthly, in LOC) vs price of USD / EUR in LOC  "
                 "(+ = LOC weakens as equities rise)")
    ax.legend(frameon=False, ncol=4, fontsize=9)
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
    (out / "rolling").mkdir(exist_ok=True)
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=args.years)
    # extra history: outlier lookback + rolling window before `start`
    fred = Fred((start - pd.DateOffset(years=6)).strftime("%Y-%m-%d"), out / "data")

    rows, all_corr, yearly_txt = {}, {}, []
    for k, cfg in MARKETS.items():
        fp = FREQ[cfg["freq"]]
        r_full = market_returns(fred, cfg)
        for f in [c for c in r_full.columns if c != "eq"]:
            c = pair_corr(r_full, f, fp).loc[start:]
            all_corr[(k, f)] = c
            c.to_csv(out / "rolling" / f"{k}_{f.lower()}.csv", float_format="%.4f")

            r = r_full.loc[start:, ["eq", f]]
            rc = r[c["excluded"] == 0]

            def corr(d):
                return d["eq"].corr(d[f])

            last = c.dropna().iloc[-1]
            pair = f"{f}/{cfg['loc']}"
            rows[(cfg["name"], pair)] = {
                "freq": fp["unit"],
                "pct_excluded": 100 * c["excluded"].mean(),
                "full_raw": corr(r),
                "full_robust": corr(rc),
                "pre_2020_robust": corr(rc.loc[:"2019"]),
                "since_2020_robust": corr(rc.loc["2020":]),
                "latest_raw": last["raw"],
                "latest_robust": last["robust"],
                "max_jump_raw": jumps(c["raw"])[0],
                "max_jump_trimmed": jumps(c["trimmed"])[0],
                "max_jump_robust": jumps(c["robust"])[0],
                "p95_jump_raw": jumps(c["raw"])[1],
                "p95_jump_robust": jumps(c["robust"])[1],
            }
            min_obs = 6 if cfg["freq"] == "M" else 20
            yearly = rc.groupby(rc.index.year).apply(
                lambda g: corr(g) if len(g) >= min_obs else np.nan).dropna()
            yearly_txt.append(f"{cfg['name']:<18} {pair:<8} "
                              + " ".join(f"{y % 100:02d}:{v:+.2f}" for y, v in yearly.items()))

    table = pd.DataFrame(rows).T
    table.index.names = ["market (equities in LOC)", "FX (price in LOC)"]
    num = table.columns.drop("freq")
    table[num] = table[num].astype(float).round(3)
    table.to_csv(out / "summary_table.csv")

    text = (
        "Correlation of local equity returns with the price of USD / EUR in local currency "
        "(+ FX = LOC weakens)\n"
        f"robust = periods with |robust z| > {Z_CUT:g} on either leg excluded (trailing 5y median/MAD); "
        "latest_robust is also exponentially weighted (half-life = half the window).\n"
        "Window: 3y (monthly OECD) / 52w (weekly daily-index cross-checks). max/p95_jump_* = largest / 95th pct "
        "|period change| of the rolling corr: raw, trimmed equal-weight, robust (trimmed + exp. weighted).\n\n"
        + table.to_string() + "\n\n"
        "Calendar-year correlations, extremes excluded\n" + "\n".join(yearly_txt) + "\n"
    )
    (out / "summary.txt").write_text(text)
    print(text)

    for g, title in GROUPS.items():
        keys = [k for k, cfg in MARKETS.items() if cfg["group"] == g]
        plot_group(keys, all_corr, title, out / f"grid_{g.lower()}.png")
    plot_bars(table, out / "compare_full_sample.png")


if __name__ == "__main__":
    main()
