"""Build the structure report (self-contained HTML with Plotly charts).

Run: python -m gdp_icb.report      (runs the pipeline first)
"""
from __future__ import annotations

import html
import json

import numpy as np
import pandas as pd

from . import config as C
from .pipeline import run

LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
OTHER = "#898781"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def esc(x) -> str:
    return html.escape(str(x))


def pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f}%"


def table(df: pd.DataFrame, cls: str = "") -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in r) + "</tr>" for r in df.itertuples(index=False))
    return f'<div class="tw"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def fold_top(df: pd.DataFrame, key: str, val: str, k: int = 7, order_by: pd.Series | None = None) -> list[str]:
    s = order_by if order_by is not None else df.groupby(key)[val].sum()
    return list(s.sort_values(ascending=False).index[:k])


# ------------------------------------------------------------------ figures (plotly JSON dicts)
def fig_stacked_area(df: pd.DataFrame, x: str, key: str, val: str, top: list[str], title: str, ytitle: str) -> dict:
    d = df.copy()
    d[key] = np.where(d[key].isin(top), d[key], "Other")
    p = d.pivot_table(index=x, columns=key, values=val, aggfunc="sum").fillna(0)
    traces = []
    for i, k in enumerate(top + (["Other"] if "Other" in p.columns else [])):
        color = LIGHT[i] if k != "Other" else OTHER
        traces.append({
            "type": "scatter", "mode": "lines", "stackgroup": "one", "name": k,
            "x": [str(v) for v in p.index], "y": [round(float(v), 6) for v in p[k]],
            "line": {"width": 1, "color": color, "shape": "hv"}, "fillcolor": color,
            "hovertemplate": "%{y:.2%}<extra>" + esc(k) + "</extra>",
        })
    return {"data": traces, "layout": {"title": {"text": title}, "yaxis": {"title": {"text": ytitle}, "tickformat": ".0%", "range": [0, 1]},
                                       "hovermode": "x unified", "height": 440}}


def fig_lines(series: dict[str, tuple[list, list]], title: str, ytitle: str, fmt: str = ".0%", step: bool = True,
              height: int = 360) -> dict:
    traces = []
    for i, (name, (xs, ys)) in enumerate(series.items()):
        traces.append({"type": "scatter", "mode": "lines+markers", "name": name, "x": xs, "y": ys,
                       "line": {"width": 2, "color": LIGHT[i], "shape": "hv" if step else "linear"},
                       "marker": {"size": 6, "color": LIGHT[i]},
                       "hovertemplate": "%{y:" + fmt + "}<extra>" + esc(name) + "</extra>"})
    return {"data": traces, "layout": {"title": {"text": title}, "yaxis": {"title": {"text": ytitle}, "tickformat": fmt, "rangemode": "tozero"},
                                       "hovermode": "x unified", "height": height}}


def fig_hbar(labels: list[str], values: list[float], title: str, height: int = 900, fmt: str = ".1%") -> dict:
    return {"data": [{"type": "bar", "orientation": "h", "y": labels, "x": values, "marker": {"color": LIGHT[0]},
                      "hovertemplate": "%{y}: %{x:" + fmt + "}<extra></extra>"}],
            "layout": {"title": {"text": title}, "xaxis": {"tickformat": fmt}, "yaxis": {"autorange": "reversed", "automargin": True},
                       "height": height, "bargap": 0.25, "showlegend": False}}


def fig_grouped_hbar(labels: list[str], series: dict[str, list[float]], title: str, height: int = 560) -> dict:
    traces = [{"type": "bar", "orientation": "h", "name": n, "y": labels, "x": v, "marker": {"color": LIGHT[i]},
               "hovertemplate": "%{y}: %{x:.1%}<extra>" + esc(n) + "</extra>"} for i, (n, v) in enumerate(series.items())]
    return {"data": traces, "layout": {"title": {"text": title}, "barmode": "group", "xaxis": {"tickformat": ".0%"},
                                       "yaxis": {"autorange": "reversed", "automargin": True}, "height": height, "bargap": 0.3}}


def fig_stacked_hbar(mat: pd.DataFrame, title: str, height: int = 520) -> dict:
    traces = []
    for i, k in enumerate(mat.columns):
        color = OTHER if k == "Other" else LIGHT[i]
        traces.append({"type": "bar", "orientation": "h", "name": k, "y": list(mat.index), "x": [round(float(v), 5) for v in mat[k]],
                       "marker": {"color": color, "line": {"width": 1, "color": "rgba(0,0,0,0)"}},
                       "hovertemplate": "%{y}: %{x:.1%}<extra>" + esc(k) + "</extra>"})
    return {"data": traces, "layout": {"title": {"text": title}, "barmode": "stack", "xaxis": {"tickformat": ".0%", "range": [0, 1]},
                                       "yaxis": {"autorange": "reversed", "automargin": True}, "height": height, "bargap": 0.3}}


def fig_heatmap(mat: pd.DataFrame, title: str, height: int = 620) -> dict:
    z = mat.values
    return {"data": [{"type": "heatmap", "z": [[round(float(v), 6) for v in row] for row in z], "x": list(mat.columns),
                      "y": list(mat.index), "colorscale": [[i / (len(SEQ) - 1), c] for i, c in enumerate(SEQ)],
                      "xgap": 2, "ygap": 2, "colorbar": {"tickformat": ".1%", "title": {"text": "weight"}},
                      "hovertemplate": "%{y} × %{x}: %{z:.2%}<extra></extra>"}],
            "layout": {"title": {"text": title}, "height": height, "xaxis": {"tickangle": -60, "automargin": True},
                       "yaxis": {"autorange": "reversed", "automargin": True}}}


# ------------------------------------------------------------------ report
def build() -> str:
    o = run()
    w, cw, cal, buckets, icb = o["weights"], o["country_weights"], o["calendar"], o["buckets"], o["icb"]
    gb, to, latest = o["global_buckets"], o["turnover"], o["latest"]
    rv = w[w["event"] == "review"]
    lat = rv[rv["review"] == latest]
    lat_c = cw[cw["review"] == latest].sort_values("country_weight", ascending=False)
    first = cal["review"].iloc[0]
    n_sets = w["effective_date"].nunique()

    figs: dict[str, dict] = {}

    # 1 data age
    figs["age"] = fig_lines({
        "IMF PPP GDP (country level)": (list(cal["review"]), [int(v) for v in cal["imf_lag_years"]]),
        "OECD ICIO value added (industry mix)": (list(cal["review"]), [int(v) for v in cal["icio_lag_years"]]),
    }, "Age of data used at each review (review year minus data year)", "years", fmt="d")

    # 2 country weights
    top_c = list(lat_c["country"].head(7))
    figs["country"] = fig_stacked_area(cw, "review", "country", "country_weight", top_c,
                                       "Country weights (IMF PPP GDP, latest reported year)", "weight")

    # 3 global ICB industry
    gbr = gb[gb["event"] == "review"]
    ind_latest = gbr[gbr["review"] == latest].groupby("reporting_icb_industry")["weight"].sum()
    top_i = fold_top(gbr, "reporting_icb_industry", "weight", 7, ind_latest)
    figs["industry"] = fig_stacked_area(gbr, "review", "reporting_icb_industry", "weight", top_i,
                                        "Global weight by reporting ICB industry", "weight")

    # 4 latest bucket bar
    lb = lat.groupby(["bucket_id", "bucket_name"])["weight"].sum().sort_values(ascending=False).reset_index()
    figs["buckets"] = fig_hbar([f"{r.bucket_name} ({r.bucket_id})" for r in lb.itertuples()],
                               [round(float(v), 6) for v in lb["weight"]],
                               f"Global weight by ICB bucket, {latest} review", height=980)

    # 5 heatmap
    hm = lat.pivot_table(index="country", columns="bucket_id", values="weight", aggfunc="sum").fillna(0)
    hm = hm.loc[lat_c["country"].head(20), list(lb["bucket_id"])]
    figs["heat"] = fig_heatmap(hm, f"Country × bucket weights, top 20 countries, {latest} review")

    # 6 within-country mix
    mixc = list(lat_c["country"].head(12))
    m = lat[lat["country"].isin(mixc)].copy()
    m["grp"] = np.where(m["reporting_icb_industry"].isin(top_i), m["reporting_icb_industry"], "Other")
    mm = m.pivot_table(index="country", columns="grp", values="within_country_share", aggfunc="sum").fillna(0)
    mm = mm.loc[mixc, [c for c in top_i + ["Other"] if c in mm.columns]]
    figs["mix"] = fig_stacked_hbar(mm, f"Within-country industry mix (ICIO {int(lat['review'].map(cal.set_index('review')['icio_year']).iloc[0])}), largest 12 countries")

    # 7 turnover
    to2 = to.copy()
    to2["effective_date"] = to2["effective_date"].astype(str)
    figs["turnover"] = {"data": [
        {"type": "bar", "name": "Total (country × bucket)", "x": list(to2["effective_date"]), "y": [round(float(v), 5) for v in to2["total_turnover"]],
         "marker": {"color": LIGHT[0]}, "hovertemplate": "%{y:.2%}<extra>total</extra>"},
        {"type": "bar", "name": "Country level only", "x": list(to2["effective_date"]), "y": [round(float(v), 5) for v in to2["country_level_turnover"]],
         "marker": {"color": LIGHT[1]}, "hovertemplate": "%{y:.2%}<extra>country level</extra>"}],
        "layout": {"title": {"text": "One-way turnover of the weight vector at each weight change"}, "barmode": "group",
                   "yaxis": {"tickformat": ".0%"}, "height": 380, "hovermode": "x unified", "bargap": 0.25}}

    # 8 imputed rent effect
    g0 = o["global_buckets_no_rent_adj"]
    g0 = g0[(g0["event"] == "review") & (g0["bucket_id"] == "REAL")]
    g1 = gbr[gbr["bucket_id"] == "REAL"]
    figs["rent"] = fig_lines({
        "Real estate, full ICIO L": (list(g0["review"]), [round(float(v), 5) for v in g0["weight"]]),
        "Real estate, imputed rent removed (used)": (list(g1["review"]), [round(float(v), 5) for v in g1["weight"]]),
    }, "Effect of removing owner-occupier imputed rent on the global Real Estate weight", "weight", fmt=".1%")

    # 9 PPP vs USD
    pu = o["ppp_usd"]
    pu = pu[pu["review"] == latest].sort_values("ppp_weight", ascending=False).head(15)
    figs["pppusd"] = fig_grouped_hbar(list(pu["country"]), {
        "PPP GDP weight (used)": [round(float(v), 5) for v in pu["ppp_weight"]],
        "USD GDP weight (reference)": [round(float(v), 5) for v in pu["usd_weight"]],
    }, f"PPP vs market-exchange-rate country weights, {latest} review (15 largest)")

    # ------------------------------------------------ tables
    datasets = pd.DataFrame([
        ["OECD Inter-Country Input-Output tables, 2025 edition (via TiVA 2025 'Principal indicators, levels', measure VALU)",
         "Value added at basic prices by country × industry, USD mn, current prices", "76 economies + rest of world × 50 ISIC Rev.4 industries, 1995–2022",
         "sdmx.oecd.org → OECD.STI.PIE / DSD_TIVA_MAINLV@DF_MAINLV v1.1", "Within-country industry mix"],
        ["IMF World Economic Outlook (latest Oct-2026, plus frozen Oct-2025 and Apr-2026 vintages)",
         "GDP, current prices, PPP international $ (PPPGDP); GDP in USD (NGDPD) for diagnostics; latest-actual-year metadata",
         "~195 economies, 1980–2031 (projections beyond latest actual)", "api.imf.org SDMX 2.1 → IMF.RES / WEO", "Country weights"],
        ["OECD National Accounts Table 6A",
         "GVA of L (real estate) and L68A (imputed rents of owner-occupied dwellings), national currency, current prices",
         "OECD + partner countries with an L68A split, 1995–latest", "sdmx.oecd.org → OECD.SDD.NAD / DSD_NAMAIN10@DF_TABLE6", "Remove imputed rent from ICIO L"],
        ["ICB structure and definitions (LSEG/FTSE Russell)", "11 industries / 20 supersectors / 45 sectors / 173 subsectors",
         "Current structure (post-2019/2021 revision)", "lseg.com icb-structure-and-definitions.xlsx", "Target classification"],
        ["FTSE country classification updates (2006–2026, annual + interim) and FTSE GDP Weighted / GDP-Adjusted ground rules",
         "Market status changes, effective dates, phase-ins", "2006–2026", "lseg.com country-classification PDFs", "Universe history and review calendar"],
    ], columns=["Dataset", "Content used", "Coverage", "Access", "Role"])

    uni = pd.read_csv(C.REFERENCE / "ftse_allworld_universe.csv", dtype=str).fillna("")
    ev = uni[(uni["first_review"] != "2000-03") | (uni["last_review"] != "") | (uni["flag"] != "")]
    ev = ev[["country", "first_review", "last_review", "exit_effective", "flag", "source_note"]].rename(columns={
        "first_review": "first review in", "last_review": "last review in", "exit_effective": "intra-review exit"})

    cal_t = cal[["review", "data_cutoff", "effective_date", "imf_year", "imf_vintage_used", "icio_year",
                 "icio_edition_available", "n_countries", "provisional"]].rename(columns={
        "data_cutoff": "data cut-off", "effective_date": "effective", "imf_year": "IMF data year",
        "imf_vintage_used": "IMF vintage", "icio_year": "ICIO data year", "icio_edition_available": "ICIO edition at cut-off",
        "n_countries": "countries"})

    bt = buckets[buckets["in_scope"] == 1].merge(lb[["bucket_id", "weight"]], on="bucket_id", how="left")
    bt["weight"] = bt["weight"].map(lambda v: pct(v, 2))
    bt = bt[["bucket_id", "bucket_name", "icio_codes", "reporting_icb_industry", "icb_industries", "weight", "icb_subsectors"]].rename(columns={
        "icio_codes": "ICIO industries", "reporting_icb_industry": "reporting industry", "icb_industries": "ICB industries spanned",
        "weight": f"weight {latest}", "icb_subsectors": "ICB subsectors"})
    bt["ICB industries spanned"] = bt["ICB industries spanned"].str.replace(";", ", ")

    merges = icb[icb["icio_codes"].str.contains(";")][["sub_code", "subsector", "icio_codes", "bucket_id", "rationale"]]
    zero = icb[icb["in_scope"] == 0][["sub_code", "subsector", "icio_codes", "rationale"]]
    judgement_ids = [10101015, 20101020, 20102010, 35102060, 40201050, 40501015, 50203000, 50203030, 50205015,
                     30201030, 60102020, 65102000, 40204030]
    judg = icb[icb["sub_code"].isin(judgement_ids)][["sub_code", "subsector", "icio_codes", "bucket_id", "rationale"]]

    ed = pd.read_csv(C.REFERENCE / "icio_editions.csv")
    rent = o["rent_shares"]
    rent_lat = rent[rent["year"] == 2022].sort_values("imputed_rent_share")
    rmed = float(o["rent_median"].loc[2022])

    flagged = cw[(cw["review"] == latest) & (cw["flags"] != "")][["country", "country_weight", "imf_year", "imf_latest_actual", "icio_source", "flags"]]
    flagged = flagged.assign(country_weight=flagged["country_weight"].map(lambda v: pct(v, 2)))

    files = pd.DataFrame([
        ["output/weights_country_bucket_long.csv", "One row per weight set × country × bucket: weight, country_weight, within_country_share, event (review / intra-review deletion)"],
        [f"output/weights_matrix_{latest}.csv", "Country × bucket weight matrix for the latest live review"],
        ["output/country_weights.csv", "Country weights per review with IMF data year, vintage, latest-actual year, ICIO year/source and flags"],
        ["output/global_bucket_weights.csv", "Global bucket weights per weight set"],
        ["output/bucket_definitions.csv", "Buckets: ICIO members, ICB subsectors, ICB industries spanned, reporting industry"],
        ["output/icb_subsector_to_bucket.csv", "Lookup to apply the weights to stocks: ICB subsector → bucket (+ rationale)"],
        ["output/review_calendar.csv", "Review dates, data cut-offs, IMF/ICIO data years and editions"],
        ["output/turnover.csv", "One-way turnover between consecutive weight sets"],
        ["data/reference/*.csv", "Hand-curated inputs: ICIO industries & scope, ICB→ICIO mapping, bucket names, FTSE universe history, ICIO editions"],
        ["data/processed/*.csv", "Tidy downloads: ICIO VA, IMF WEO GDP (3 vintages), OECD imputed-rent split"],
    ], columns=["File", "Content"])

    usa = lat_c.set_index("country")["country_weight"]
    big_to = list(to.sort_values("total_turnover", ascending=False)["effective_date"].head(4).sort_values())
    re_raw = float(g0[g0["review"] == latest]["weight"].iloc[0])
    re_adj = float(g1[g1["review"] == latest]["weight"].iloc[0])
    pu_all = o["ppp_usd"][o["ppp_usd"]["review"] == latest].set_index("country")

    def ratio(c: str) -> str:
        return f"{pu_all.at[c, 'ppp_weight'] / pu_all.at[c, 'usd_weight']:.1f}"

    mi = lat.pivot_table(index="country", columns="reporting_icb_industry", values="within_country_share", aggfunc="sum")
    bk = lat.pivot_table(index="country", columns="bucket_id", values="within_country_share", aggfunc="sum")

    def sh(c: str, k: str, src=mi) -> str:
        return pct(src.at[c, k]) if c in src.index else "n/a"

    mix_text = (
        f"Agriculture is {sh('India', 'AGRI', bk)} of India's in-scope value added against {sh('USA', 'AGRI', bk)} in the USA, "
        f"which lifts Consumer Staples to {sh('India', 'Consumer Staples')} in India and {sh('Indonesia', 'Consumer Staples')} in Indonesia. "
        f"Energy is {sh('Indonesia', 'Energy')} in Indonesia; Basic Materials is {sh('China', 'Basic Materials')} in China and {sh('South Korea', 'Basic Materials')} in Korea; "
        f"Technology is {sh('South Korea', 'Technology')} in Korea. "
        f"Financials are {sh('UK', 'Financials')} in the UK and {sh('USA', 'Financials')} in the USA, against {sh('China', 'Financials')} in China. "
        "Industrials is large everywhere because it collects construction, professional and administrative services.")
    top3 = lb.head(3)
    k_n = int(buckets["in_scope"].sum())
    mixed_n = int(buckets[(buckets["in_scope"] == 1)]["is_mixed_icb_industry"].sum())
    mean_to = to["total_turnover"].mean()
    cal_live = cal[~cal["provisional"]]

    body = f"""
<header>
<p class="eyebrow">Index methodology study · built {C.AS_OF}</p>
<h1>GDP × Industry Weighted All-World</h1>
<p class="lede">The FTSE All-World GDP Weighted idea, pushed one level down. Country weights follow IMF PPP GDP, as in the FTSE rules.
Within each country, weight is split across ICB-based industry buckets in proportion to each bucket's share of market-sector value added in the OECD Inter-Country Input-Output (ICIO) tables.
The result is {n_sets} weight sets from {first} to {cal['review'].iloc[-1]}: {len(cal)} semi-annual reviews plus {n_sets - len(cal)} intra-review deletions.</p>
<div class="tiles">
  <div class="tile"><div class="v">{lat_c.shape[0]}</div><div class="l">countries at {latest}</div></div>
  <div class="tile"><div class="v">{k_n}</div><div class="l">ICB industry buckets (no I/O industry split)</div></div>
  <div class="tile"><div class="v">{len(cal)}</div><div class="l">reviews, Mar &amp; Sep, {first}–{cal['review'].iloc[-1]}</div></div>
  <div class="tile"><div class="v">{pct(mean_to)}</div><div class="l">mean one-way turnover per weight change</div></div>
</div>
</header>

<nav class="toc"><a href="#method">Method</a><a href="#data">Datasets</a><a href="#timing">Timing &amp; lags</a><a href="#universe">Universe</a>
<a href="#mapping">ICIO → ICB mapping</a><a href="#results">Weight histories</a><a href="#nuances">Nuances &amp; caveats</a><a href="#files">Files</a></nav>

<section id="method">
<h2>1. Method</h2>
<h3>Relation to the FTSE ground rules</h3>
<p>FTSE has two GDP-based All-World variants:</p>
<ul>
<li><b>FTSE GDP Weighted Index Series (v3.8, Jul-2026).</b> Reviewed annually in March. Country weight is proportional to the IMF five-year-ahead <i>forecast</i> of PPP GDP, and stocks are rescaled within each country by free-float market cap (w<sub>i</sub> = w′<sub>i</sub> × GDP%<sub>j</sub> / MC%<sub>j</sub>), with a 5% company cap.</li>
<li><b>FTSE All-World GDP-Adjusted (v1.0, Jan-2026).</b> Reviewed semi-annually in March and September. It uses IMF nominal USD GDP for the <i>most recent published year</i>: the April WEO feeds the September review and the October WEO feeds the following March review.</li>
</ul>
<p>This build keeps the FTSE structure but makes the following choices:</p>
<table class="kv">
<tr><th>Country weight</th><td>IMF WEO <b>PPP</b> GDP of the <b>latest reported year</b>, not a forecast, as a share of the universe total. The vintage timing follows the GDP-Adjusted rule: March reviews use the October WEO (year Y−2), September reviews use the April WEO (year Y−1).</td></tr>
<tr><th>Industry split</th><td>Within each country, OECD ICIO value added of each bucket ÷ in-scope value added for the <b>latest ICIO year published before the review data cut-off</b>.</td></tr>
<tr><th>Bucket weight</th><td>w<sub>c,b</sub> = GDP%<sub>c</sub> × VA%<sub>b|c</sub>. Because VA% is a within-country share, ICIO only determines the <i>mix</i>. The more timely IMF figure sets each country's <i>level</i>, which is equivalent to rescaling the lagged ICIO table to IMF GDP.</td></tr>
<tr><th>Scope</th><td>Market sector: ICIO A–N and R–S. O (public administration), P (education), Q (health and social work) and T (households) are excluded. L (real estate) is kept net of owner-occupier imputed rent.</td></tr>
<tr><th>Calendar</th><td>Semi-annual reviews, implemented after the close on the 3rd Friday of March and September (effective Monday). Data cut-off is the Wednesday before the 1st Friday of the review month.</td></tr>
<tr><th>Intra-review deletions</th><td>Following rule 6.2, a deleted country's weight is redistributed pro rata across all remaining country × bucket cells. This applies to Morocco (22-Jun-2015) and Russia (07-Mar-2022). There are no intra-review additions.</td></tr>
<tr><th>Stock level (implementation)</th><td>Map each constituent's ICB subsector to its bucket (<code>icb_subsector_to_bucket.csv</code>). Each country × bucket weight is then spread across its stocks by free-float market cap, the same w′ × target / MC% rescaling as FTSE rule 5.2.2, applied at the country × bucket level. A cell with no constituents needs a redistribution rule, e.g. pro rata within the country (see caveats).</td></tr>
</table>
</section>

<section id="data">
<h2>2. Datasets</h2>
{table(datasets)}
<p class="note">All values are downloaded programmatically (<code>python -m gdp_icb.download</code>). The ICIO data comes from the TiVA 2025 release, whose levels table holds the ICIO 2025 value-added row by country × industry. This is identical to the VALU row of the full ICIO matrices, without downloading the large per-year matrix files.</p>
</section>

<section id="timing">
<h2>3. Timing and publication lag</h2>
<p><b>IMF.</b> Country weights use the latest <i>reported</i> year, never projections: Y−2 at March reviews (October WEO) and Y−1 at September reviews (April WEO). The two reviews from Mar-2026 and the provisional Mar-2027 use the actual frozen WEO vintages, so they are genuinely point-in-time. Earlier reviews use the year that would have been reported, but with the <i>latest revised</i> values, because the IMF API only serves the last few vintages.</p>
<p>A consequence of this rule is that a September review and the following March review use the <i>same</i> data year. With revised history, country weights therefore only change once a year, except for universe changes. In live use, March picks up the October revision.</p>
<p><b>ICIO.</b> OECD publishes roughly every two years with a 3-year lag, so at a review the industry mix is 4–7 years old (review year minus data year). The edition timeline below is applied strictly: an edition counts only if it was published before the review's data cut-off. Before the first ICIO release (Jan-2013) the history is <i>simulated</i> with a 4-year lag. Values always come from the 2025 edition, which back-casts 1995–2022 on a consistent basis.</p>
{table(ed)}
<div class="chart" id="c_age"></div>
<details><summary>Full review calendar ({len(cal)} reviews)</summary>{table(cal_t)}</details>
</section>

<section id="universe">
<h2>4. Universe: historical FTSE All-World membership</h2>
<p>The All-World universe is Developed + Advanced Emerging + Secondary Emerging markets. Membership was reconstructed from FTSE's annual and interim country-classification announcements for 2006–2026. The 2006 classification is assumed to hold from 2000. Phased-in markets enter at the first review after their phase-in completes. The FTSE GDP Weighted rules do this explicitly for Saudi Arabia (eligible from March 2020), and the same rule is applied to Qatar and Kuwait. Countries whose status changed <i>within</i> the All-World universe, such as Korea, Israel, Poland and Greece, are unaffected.</p>
{table(ev)}
</section>

<section id="mapping">
<h2>5. ICIO → ICB mapping</h2>
<h3>Principle: finest common partition</h3>
<p>Each of the 173 ICB subsectors is assigned to the ICIO industry that carries its <i>primary economic activity</i> under ISIC Rev.4. A few subsectors genuinely span two ICIO industries according to their ICB definition. Examples are Integrated Oil &amp; Gas (extraction B06 + refining C19), and Iron &amp; Steel, whose ICB definition includes iron-ore mining (B07 + C241). In those cases the two ICIO industries are linked. Buckets are then the connected components of the ICIO ↔ ICB graph. This makes them the finest partition where <b>no ICIO industry and no ICB subsector is ever split</b>: every stock maps to exactly one bucket, and every bucket's GDP measure is a sum of whole ICIO industries.</p>
<p>The result is {k_n} in-scope buckets. {mixed_n} of them span more than one ICB Industry. For example, G (wholesale &amp; retail) holds Consumer Discretionary retailers, Consumer Staples grocers and Industrial distributors; C20 holds chemicals as well as personal and household products. Each bucket carries a judgement-based <i>reporting industry</i>, used only to group charts and never to split weight.</p>
<p>The ICIO tables report the financial sector as a single industry K, so banks and insurers cannot be separated. All 19 financial subsectors, plus payment processors and HMOs, form one bucket.</p>
{table(bt, "small")}
<h3>Subsectors that merge ICIO industries</h3>
{table(merges, "small")}
<h3>Judgement calls (primary-activity assignment)</h3>
{table(judg, "small")}
<h3>Subsectors that receive zero weight (mapped to excluded non-market industries)</h3>
{table(zero, "small")}
</section>

<section id="results">
<h2>6. Weight histories</h2>
<p>At the {latest} review the three largest buckets are {', '.join(f'{r.bucket_name} ({pct(r.weight)})' for r in top3.itertuples())}.
China ({pct(usa.get('China', 0))}), the USA ({pct(usa.get('USA', 0))}) and India ({pct(usa.get('India', 0))}) dominate on a PPP basis.</p>
<div class="chart" id="c_country"></div>
<div class="chart" id="c_industry"></div>
<div class="chart" id="c_buckets"></div>
<div class="chart" id="c_heat"></div>
<p>The country × bucket matrix is the product of the two inputs. Its rows sum to the country weight; columns are the global bucket weights.</p>
<div class="chart" id="c_mix"></div>
<p>The within-country mix shows where the industry overlay matters most. {mix_text}</p>
<div class="chart" id="c_turnover"></div>
<p>Turnover is low: on average {pct(mean_to)} one-way per weight change. The largest changes are at {', '.join(str(d) for d in big_to)}. These coincide with a new ICIO edition rolling the industry mix forward by 2–4 years, with universe changes (e.g. Kuwait entering in Mar-2019), and with the Russia deletion. Zero turnover means a March review used the same data years as the preceding September, which is inherent to the WEO timing rule with revised history.</p>
<div class="chart" id="c_rent"></div>
<p>Removing owner-occupier imputed rent cuts the global Real Estate bucket from {pct(re_raw)} to {pct(re_adj)} at the {latest} review. That rent is a national-accounts imputation, with no listed-equity counterpart. The L68A share of L is taken from OECD Table 6A where the split exists and is plausible ({C.IMPUTED_RENT_VALID[0]:.2f}–{C.IMPUTED_RENT_VALID[1]:.2f}). Shares of ≈1.0, reported by Brazil, Mexico and Saudi Arabia, signal that no split is available. Gaps are interpolated within country; countries without any split (China, India, Japan, Korea, …) use the cross-country median, {pct(rmed)} in 2022.</p>
<div class="chart" id="c_pppusd"></div>
<p>PPP versus market exchange rates is the largest single design lever at the country level. Relative to nominal-USD weights, PPP scales India by {ratio('India')}×, Indonesia by {ratio('Indonesia')}× and China by {ratio('China')}×, and the USA by {ratio('USA')}×. Switching is a one-line change (the NGDPD series is already downloaded).</p>
</section>

<section id="nuances">
<h2>7. Nuances and caveats</h2>
<ol>
<li><b>Revised versus real-time data.</b> Only the 2025 ICIO edition and the last three WEO vintages can be downloaded. For earlier reviews the <i>timing</i> is point-in-time (which data year was knowable), but the <i>values</i> are today's revised estimates. Backtests therefore carry mild revision look-ahead, typically small for within-country industry shares.</li>
<li><b>Pre-2013 ICIO history is simulated.</b> ICIO did not exist before Jan-2013; earlier reviews assume a 4-year lag. Note that the 2018 edition only started in 2005.</li>
<li><b>Lag mismatch.</b> The industry mix (4–7 years old) lags the country weight (1–2 years old) by 2–6 years. Mixing them is consistent, because shares are scale-free, but structural shifts appear with a delay, e.g. China's construction and real-estate boom and bust, or commodity-price swings in OILG/METL. A possible refinement is to nowcast within-country shares with OECD/UN national-accounts GVA by activity, which has a 1–2 year lag. It is not done here so that the build stays with I/O tables as requested.</li>
<li><b>PPP versus sector prices.</b> PPP converts whole-economy GDP. Sector price levels differ: non-tradables are relatively cheap in emerging markets. Applying one PPP factor to every bucket is a simplification.</li>
<li><b>Value added ≠ listed market.</b> Many buckets are dominated by unlisted activity: agriculture, construction, trade, professional services and other personal services. In a stock-level implementation, cells with few or no constituents (e.g. AGRI in the USA, COAL in Japan) need a fallback: redistribute pro rata within the country, pro rata within the bucket across countries, or apply a cap. Concentration also needs controlling, e.g. the 5% company cap from the FTSE rules, applied within cells.</li>
<li><b>Negative value added.</b> A few ICIO cells are negative (e.g. Brazil C19, 2011–2014, from administered fuel prices). They are summed within buckets and floored at zero.</li>
<li><b>Missing ICIO countries.</b> Kuwait and Qatar have no ICIO table; Saudi Arabia's industry mix is used as a Gulf proxy. Belgium and Luxembourg are summed, matching FTSE's single Belgium/Luxembourg market.</li>
<li><b>Thin markets.</b> Romania (Sep-2020) and Iceland (Sep-2022) are Secondary Emerging but may have few or no large/mid-cap All-World constituents. Pakistan exited on 23-Sep-2024. Vietnam's phase-in starts Sep-2026 and is not yet included; edit <code>ftse_allworld_universe.csv</code> to change any of this.</li>
<li><b>IMF 'latest reported year'.</b> For some countries the September review's Y−1 value is still an IMF staff estimate in the April WEO; these are flagged <code>imf_estimate</code>. Fiscal-year reporters (India, Egypt, Pakistan) follow WEO conventions.</li>
<li><b>Mapping judgement calls.</b> Software (ISIC 5820 publishing vs 62 programming), packaging, conglomerates and renewable-energy equipment are inherently multi-activity. Each is assigned to its modal activity and documented. Changing a row in <code>icb_to_icio.csv</code> re-derives the buckets automatically, with assertions that no industry is split.</li>
<li><b>Excluded health care.</b> With Q out of scope, hospitals, labs and other care providers get zero weight. Managed care (HMOs) maps to K, as health insurance. Pharma (C21) and medical devices (C26 / C31T33) stay in.</li>
<li><b>Provisional review.</b> Mar-2027 is computed from already-published inputs (Oct-2026 WEO, ICIO 2025) and is marked provisional; universe changes announced later are not reflected.</li>
</ol>
<h3>Flags at the {latest} review</h3>
{table(flagged)}
</section>

<section id="files">
<h2>8. Output files and reproduction</h2>
<pre>pip install -r requirements.txt
python -m gdp_icb.download   # fetch OECD / IMF / ICB inputs
python -m gdp_icb.report     # build weights + this report
pytest -q                    # structural checks</pre>
{table(files)}
</section>
"""
    return page(body, figs)


def page(body: str, figs: dict[str, dict]) -> str:
    light_dark = json.dumps(dict(zip(LIGHT, DARK)))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GDP Industry Weights</title>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<style>
:root{{--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--accent:#2a78d6;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--accent:#3987e5;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--accent:#3987e5;color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:32px 16px 80px}}
h1{{font-size:34px;line-height:1.15;margin:4px 0 12px;letter-spacing:-.01em}}
h2{{font-size:22px;margin:48px 0 12px;padding-top:8px;border-top:1px solid var(--border)}}
h3{{font-size:16px;margin:24px 0 8px}}
.eyebrow{{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:12px;margin:0}}
.lede{{color:var(--ink2);font-size:17px;max-width:880px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:24px 0}}
.tile{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}}
.tile .v{{font-size:28px;font-weight:600}} .tile .l{{color:var(--ink2);font-size:13px}}
.toc{{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px;margin:8px 0 0}}
.toc a,a{{color:var(--accent);text-decoration:none}}
.chart{{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin:16px 0;min-height:200px;overflow:hidden}}
.tw{{overflow-x:auto;margin:12px 0;border:1px solid var(--border);border-radius:8px;background:var(--surface)}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--grid);vertical-align:top}}
th{{color:var(--ink2);font-weight:600;background:var(--surface);position:sticky;top:0}}
td{{font-variant-numeric:tabular-nums}}
table.small td{{font-size:12px}}
table.kv{{border:1px solid var(--border);border-radius:8px;background:var(--surface)}} table.kv th{{width:190px;position:static}}
.note{{color:var(--ink2);font-size:13px}}
code,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}}
pre{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;overflow-x:auto}}
details{{margin:12px 0}} summary{{cursor:pointer;color:var(--accent)}}
li{{margin:6px 0}}
</style></head>
<body><main>
{body}
</main>
<script>
const FIGS={json.dumps(figs)};
const L2D={light_dark};
function css(v){{return getComputedStyle(document.documentElement).getPropertyValue(v).trim()}}
function isDark(){{return css('--surface').toLowerCase()==='#1a1a19'}}
function themed(fig){{
  const f=JSON.parse(JSON.stringify(fig)); const dark=isDark();
  if(dark) f.data.forEach(t=>{{const sw=c=>L2D[c]||c; if(t.line&&t.line.color)t.line.color=sw(t.line.color); if(t.fillcolor)t.fillcolor=sw(t.fillcolor); if(t.marker&&t.marker.color&&typeof t.marker.color==='string')t.marker.color=sw(t.marker.color);}});
  f.data.forEach(t=>{{if(t.type==='bar')t.marker.line={{width:1,color:css('--surface')}}; if(t.stackgroup)t.line.color=css('--surface');}});
  const ax={{gridcolor:css('--grid'),linecolor:css('--axis'),zerolinecolor:css('--axis'),tickfont:{{color:css('--muted')}},title:{{font:{{color:css('--ink2')}}}}}};
  const lay=Object.assign({{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{{family:'system-ui,-apple-system,Segoe UI,sans-serif',color:css('--ink'),size:12}},
    margin:{{l:60,r:20,t:56,b:50}},legend:{{orientation:'h',y:-0.18,font:{{color:css('--ink2')}}}},hoverlabel:{{bgcolor:css('--surface'),font:{{color:css('--ink')}}}}}},f.layout);
  lay.title=Object.assign({{x:0.01,font:{{size:15,color:css('--ink')}}}},f.layout.title||{{}});
  lay.xaxis=Object.assign({{}},ax,f.layout.xaxis||{{}}); lay.yaxis=Object.assign({{}},ax,f.layout.yaxis||{{}});
  if(f.layout.xaxis&&f.layout.xaxis.title)lay.xaxis.title=Object.assign({{}},ax.title,f.layout.xaxis.title);
  if(f.layout.yaxis&&f.layout.yaxis.title)lay.yaxis.title=Object.assign({{}},ax.title,f.layout.yaxis.title);
  if(f.data[0]&&f.data[0].type==='heatmap'){{f.data[0].colorbar.tickfont={{color:css('--muted')}};f.data[0].colorbar.title.font={{color:css('--ink2')}};}}
  return [f.data,lay];
}}
function render(){{for(const [k,fig] of Object.entries(FIGS)){{const el=document.getElementById('c_'+k); if(!el)continue; const [d,l]=themed(fig); el.style.height=(l.height||420)+'px'; Plotly.react(el,d,l,{{responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d']}});}}}}
if(window.Plotly){{render(); window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',render);
  new MutationObserver(render).observe(document.documentElement,{{attributes:true,attributeFilter:['data-theme']}});}}
else document.querySelectorAll('.chart').forEach(e=>e.textContent='Charts need plotly.js (cdn.jsdelivr.net); tables below carry the same data.');
</script>
</body></html>"""


def main() -> None:
    out = C.OUTPUT / "report"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(build(), encoding="utf-8")
    print("wrote", out / "index.html")


if __name__ == "__main__":
    main()
