"""Assemble results/industry_all_weather.html from results/report_parts.pkl."""
import pickle

d = pickle.load(open("results/report_parts.pkl", "rb"))
FIG, T, f = d["FIG"], d["tables"], d["facts"]
dd = pickle.load(open("results/report_dd_parts.pkl", "rb"))
FIG.update({"dd_" + k: v for k, v in dd["FIG"].items()})
T.update(dd["T"])
g = dd["facts"]


def fig(k, alt, cap):
    return (f"<figure><img class='th-light' alt='{alt}' src='data:image/png;base64,{FIG[k]['light']}'>"
            f"<img class='th-dark' alt='{alt}' src='data:image/png;base64,{FIG[k]['dark']}'>"
            f"<figcaption>{cap}</figcaption></figure>")


CSS = """
/* Layout: one reading column (~68ch) with figures and tables breaking out to 1040px. */
:root{
  --bg:#f6f7f8; --paper:#fcfcfb; --ink:#14181f; --ink2:#4a505b; --muted:#7d838d; --rule:#dde0e4;
  --accent:#1f62b8; --accent-soft:#e3ecf8; --hl:#eef4fc;
  --q-GU_IU:#eb6834; --q-GU_ID:#2a78d6; --q-GD_IU:#eda100; --q-GD_ID:#1baf7a; --chip-ink:#0b0b0b;
  --f-head:"IBM Plex Sans Condensed","Arial Narrow",system-ui,sans-serif;
  --f-body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#111214; --paper:#1a1a19; --ink:#eceef1; --ink2:#bfc4cc; --muted:#8d939c; --rule:#2e3034;
  --accent:#6ea6ee; --accent-soft:#1d2a3c; --hl:#1b2533;
  --q-GU_IU:#d95926; --q-GU_ID:#3987e5; --q-GD_IU:#c98500; --q-GD_ID:#199e70; --chip-ink:#0b0b0b; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#111214; --paper:#1a1a19; --ink:#eceef1; --ink2:#bfc4cc; --muted:#8d939c; --rule:#2e3034;
  --accent:#6ea6ee; --accent-soft:#1d2a3c; --hl:#1b2533;
  --q-GU_IU:#d95926; --q-GU_ID:#3987e5; --q-GD_IU:#c98500; --q-GD_ID:#199e70; --chip-ink:#0b0b0b; color-scheme:dark}
.th-dark{display:none}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .th-light{display:none}:root:not([data-theme="light"]) .th-dark{display:block}}
:root[data-theme="dark"] .th-light{display:none} :root[data-theme="dark"] .th-dark{display:block}

body{background:var(--bg);color:var(--ink);font:15.5px/1.62 var(--f-body);}
.wrap{max-width:1040px;margin:0 auto;padding-inline:20px;padding-block:28px 80px}
.col{max-width:70ch}
header.top{border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:26px;display:grid;gap:8px}
.eyebrow{font:600 12px/1 var(--f-mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font:600 clamp(30px,5vw,46px)/1.05 var(--f-head);margin:0;letter-spacing:-.01em;text-wrap:balance}
.sub{color:var(--ink2);font-size:17px;margin:0;max-width:62ch}
.meta{font:12.5px/1.5 var(--f-mono);color:var(--muted)}
nav.toc{display:flex;flex-wrap:wrap;gap:6px 18px;font:500 13px/1.4 var(--f-head);margin:6px 0 30px;padding:10px 0;border-bottom:1px solid var(--rule)}
nav.toc a{color:var(--ink2);text-decoration:none} nav.toc a:hover,nav.toc a:focus-visible{color:var(--accent);text-decoration:underline}
h2{font:600 26px/1.2 var(--f-head);margin:56px 0 12px;text-wrap:balance;display:flex;gap:12px;align-items:baseline}
h2 .n{font:500 13px/1 var(--f-mono);color:var(--muted)}
h3{font:600 18px/1.3 var(--f-head);margin:30px 0 8px}
p{margin:0 0 14px} a{color:var(--accent)}
.findings{background:var(--paper);border:1px solid var(--rule);border-radius:6px;padding:20px 22px;display:grid;gap:12px;margin:0 0 10px}
.findings h2{margin:0;font-size:19px}
.findings ol{margin:0;padding-left:20px;display:grid;gap:8px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:6px;overflow:hidden;margin:18px 0 8px}
.kpi{background:var(--paper);padding:14px 16px;display:grid;gap:4px}
.kpi .l{font:500 11.5px/1.2 var(--f-mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.kpi .v{font:600 26px/1.1 var(--f-head)}
.kpi .c{font-size:12.5px;color:var(--ink2)}
figure{margin:18px 0 26px;background:var(--paper);border:1px solid var(--rule);border-radius:6px;padding:12px}
figure img{width:100%;height:auto}
figcaption{font-size:13.5px;color:var(--ink2);padding:8px 4px 2px;max-width:90ch}
.tbl{overflow-x:auto;margin:12px 0 22px;border:1px solid var(--rule);border-radius:6px;background:var(--paper)}
table{border-collapse:collapse;width:100%;font:13px/1.4 var(--f-body)}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--rule);white-space:nowrap;font-variant-numeric:tabular-nums}
thead th{font:600 11.5px/1.3 var(--f-mono);text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:var(--paper);position:sticky;top:0}
tbody th{text-align:left;font-weight:600}
tbody tr:last-child>*{border-bottom:0}
tr.hl>*{background:var(--hl)}
td.why{white-space:normal;text-align:left;min-width:260px;color:var(--ink2)}
.tbl.wide td:nth-child(2),.tbl.wide td:nth-child(8){text-align:left}
.q{display:inline-block;font:600 11.5px/1 var(--f-mono);padding:4px 7px;border-radius:4px;color:var(--chip-ink);white-space:nowrap}
.q-GU_IU{--qc:var(--q-GU_IU)} .q-GU_ID{--qc:var(--q-GU_ID)} .q-GD_IU{--qc:var(--q-GD_IU)} .q-GD_ID{--qc:var(--q-GD_ID)}
span.q{background:var(--qc)}
.quadgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:14px 0 22px}
.qcard{background:var(--paper);border:1px solid var(--rule);border-top:4px solid var(--qc);border-radius:6px;padding:12px 14px;font-size:13.5px;min-width:0}
.qcard h4{margin:0 0 6px;font:600 15px/1.2 var(--f-head)}
.qcard p{margin:0 0 6px;color:var(--ink2)}
.aw-diagram{display:grid;grid-template-columns:auto 1fr 1fr;gap:6px;max-width:640px;margin:16px 0 22px;font-size:13px}
.aw-diagram .hd{font:600 12px/1.2 var(--f-mono);color:var(--muted);text-transform:uppercase;letter-spacing:.04em;align-self:center}
.aw-diagram .cell{background:var(--paper);border:1px solid var(--rule);border-left:4px solid var(--qc);border-radius:4px;padding:10px 12px;min-width:0}
.aw-diagram .cell b{display:block;font-family:var(--f-head);font-size:14px}
.note{border-left:3px solid var(--accent);background:var(--accent-soft);padding:12px 16px;border-radius:0 6px 6px 0;margin:14px 0 20px;font-size:14.5px}
details{margin:10px 0 24px} summary{cursor:pointer;font:600 14px/1.4 var(--f-head);color:var(--accent)}
summary:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.two>div{min-width:0}
code{font:13px var(--f-mono);background:var(--accent-soft);padding:1px 5px;border-radius:3px}
footer{margin-top:60px;padding-top:16px;border-top:1px solid var(--rule);font-size:13px;color:var(--muted)}
@media (max-width:560px){body{font-size:15px}.aw-diagram{grid-template-columns:1fr}.aw-diagram .hd:empty{display:none}}
"""

SUB = '''<h3>Variant: industry − β × market residuals</h3>
<div class="col">
<p>Two further tests use residual returns, industry − β × market. <b>(c2)</b> keeps the drawdown clustering but estimates β over the 60 months <i>before</i> each episode, not over the full sample. Industry betas drift (technology's beta was far higher going into 2000 than on average), so ex-ante residuals should separate industries more cleanly. <b>Hedged All Weather</b> goes further and holds the residuals: each industry is held long and β × market (trailing 60-month β, known at t−1) is shorted. The quadrant portfolios then contain only the regime tilts, with no market beta.</p>
<p>The ex-ante betas change {chg_c2} of the 48 assignments (cluster sizes {n_q2}). As a long-only portfolio, (c2) still has a {dd_c2} maximum drawdown and a Sharpe ratio of {sh_c2}.</p>
</div>
<div class="quadgrid">{QC2}</div>
{fig_hedbars}
<div class="col"><p>Hedged, the quadrants differentiate strongly in crashes driven by a regime. The beta-neutral All Weather (a, equal-weighted) made {h_7374} in 1973–74, {h_8082} in 1980–82 and {h_0002} in 2000–02, while the market fell. In 2007–09 it made only {h_0709}. The GFC was a pure beta event: after removing beta, every quadrant's residual was close to zero. On its own the hedged portfolio has {h_vol} volatility, beta {h_beta} and a Sharpe ratio of only {h_sh}. Its maximum drawdown of {h_dd} came in the late-1990s tech melt-up, when short-beta, long-defensive positions lost.</p></div>
<h3>Hedged All Weather: standalone, with returns in each episode</h3>
{T_HEDGED}
<div class="col"><p>Added to the market as an overlay, it helps less than these episodes suggest. Market + 1× hedged AW has a {ov_dd} maximum drawdown (Sharpe {ov_sh}), and 2× gives {ov2_dd}. The overlay pays off in 1973–74, 1980–82 and 2000–02, but the worst drawdown is 2008, when it contributed almost nothing.</p></div>
<h3>Long-only (c2) and market + hedged-overlay combinations</h3>
{T_OVERLAY}
'''

SEC = '''
<h2 id="drawdown"><span class="n">8</span>Drawdown-anchored classification (c)</h2>
<div class="col">
<p>The drawdown reduction above is small. This section tests a classification aimed directly at crashes. Industries are clustered by how they behave in the equity market's worst drawdowns, and each cluster is anchored on the asset classes Bridgewater actually uses:</p>
<ul>
<li><b>Q1 precious metals &amp; TIPS</b> (growth ↓, inflation ↑): gold; TIPS where available (2004+)</li>
<li><b>Q2 other commodities</b> (growth ↑, inflation ↑): S&amp;P GSCI from 1985, a spot composite of oil, metals and farm prices before that</li>
<li><b>Q3 government bonds</b> (growth ↓, inflation ↓): 10-year Treasury total return built from the constant-maturity yield</li>
<li><b>Q4 cyclical equities</b> (growth ↑, inflation ↓): equal weight of durables, manufacturing, tech and shops (French 10-industry)</li>
</ul>
<p><b>Method.</b> (1) Take the 10 deepest non-overlapping peak-to-trough drawdowns of the US market since 1970, when gold began floating freely. (2) For each industry and each anchor asset, compute the beta-adjusted excess return over each episode: the sum of monthly (r − r<sub>f</sub>) − β(r<sub>m</sub> − r<sub>f</sub>), with β from monthly regressions since 1970. (3) Within each episode, subtract the cross-industry average from the industry profiles (and from the cyclicals anchor, itself an industry basket). Without this step 31 of 48 industries land in Q4, because in 2000–02 almost every industry beat the cap-weighted, tech-heavy market. (4) Assign each industry to the anchor its 10-episode profile is most correlated with. An out-of-sample version (c-OOS) re-fits every January from 2000 using only drawdowns that had already bottomed.</p>
</div>
<div class="two"><div><h3>The 10 market drawdowns</h3>{T_EPS}</div>
<div><h3>Resulting clusters (48 industries)</h3><div class="quadgrid">{QC}</div></div></div>
<div class="col"><p>Cluster sizes are {n_q} (Q1–Q4). Only {agree_ac} of industries land in the same quadrant as the macro view (a). The data-driven groups are intuitive in places: gold, coal, mines, oil and agriculture follow gold and commodities. Elsewhere they are driven by one or two episodes. Q3 collects staples, healthcare and retailers that rallied in the 2000–02 and 2007–09 bond rallies. Q4 collects tech, telecom and utilities that fell with the market in 2000–02.</p></div>
{fig_epheat}
{fig_epbars}
<div class="col"><p>The bar chart explains the result. The clusters do diverge where regimes really differed: in 1973–74 Q1 lost about 20% against the market's 47%; in 1980–82 Q3 gained while Q1 lost about 40%; in 2000–02 Q1 and Q3 rose while the market fell 45%. But in the deepest episode, 2007–09, all four quadrants fell between 48% and 69%. The median industry lost {gfc_med_ind}; the best was {gfc_best_ind}. A long-only, fully invested industry portfolio's maximum drawdown is set by that episode, so regime balancing has very little room to improve it.</p></div>
<h3>Performance, Jan 1970 – Aug 2026</h3>
{T_DD_MAIN}
{fig_dd2}
<div class="col">
<p>Four comparisons frame the result:</p>
<ul>
<li><b>(c) is worse than (a)</b>: Sharpe ratio {sh_c} vs {sh_a}, maximum drawdown {dd_c} vs {dd_a}. That is despite (c) being fitted on the same drawdowns it is judged on. Dropping the beta adjustment changes little ({dd_nb}).</li>
<li><b>Industry beta is what controls drawdowns.</b> Simply holding the 10 lowest-beta industries (beta {beta_lb}) gives the best industry-only result: maximum drawdown {dd_lb}, Sharpe {sh_lb}. Beta-adjusting the classification removes exactly this information.</li>
<li><b>Real All Weather assets do what industries cannot.</b> The same four quadrants built from the anchor assets, ERC-weighted and unlevered, have {vol_aaw} volatility and a {dd_aaw} maximum drawdown (Sharpe {sh_aaw}). Levered {lev}× to market volatility, as Bridgewater does, they return {cagr_aawl} a year (market {cagr_m}) with a {dd_aawl} maximum drawdown. Its worst drawdown was in late 2008, when commodities collapsed and leverage magnified the equity loss; 2022–23 was nearly as bad (−35%), because bonds and equities fell together.</li>
<li><b>Out-of-sample, from 2000</b>, (c-OOS) has a Sharpe ratio of {sh_coos} against {sh_aoo} for (a) and {sh_m00} for the market, with a {dd_coos} maximum drawdown.</li>
</ul>
</div>
<h3>Out-of-sample window, Jan 2000 – Aug 2026</h3>
{T_DD_OOS}
<h3>Across industry levels (ERC within and across)</h3>
{T_DD_LEV}
SUB_HEDGE
<div class="note">The drawdown you expected is a property of the asset mix, not of the industry classification. Industries give a robust relative-value regime map, worth about +0.05 Sharpe. Crash protection needs assets whose beta to equities is near zero or negative, namely Treasuries and gold, sized by risk. A practical hybrid: use the macro-classified industry quadrants as the equity sleeve inside an asset-class All Weather.</div>
'''

H = f"""<meta charset="utf-8"><title>Industry All Weather</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="top">
  <div class="eyebrow">Research note · US equity industries · Kenneth French data library</div>
  <h1>Industry All Weather</h1>
  <p class="sub">Can Bridgewater's four-environment risk balance be built from equity industries alone? We classify French industries by growth and inflation sensitivity, build four quadrant portfolios and combine them.</p>
  <div class="meta">Evaluation window {f['period']} (740 months, monthly rebalanced, before costs) · industry data CRSP 2026-08 · macro: FRED GDPC1, CPIAUCSL</div>
</header>

<nav class="toc" aria-label="Sections">
<a href="#findings">Key findings</a><a href="#allweather">All Weather</a><a href="#regimes">Macro regimes</a><a href="#classification">Classification</a>
<a href="#validation">Does it work?</a><a href="#base">48-industry portfolio</a><a href="#variants">Weighting variants</a><a href="#levels">Industry granularity</a><a href="#drawdown">Drawdown-anchored (c)</a><a href="#conclusions">Conclusions</a><a href="#method">Method</a>
</nav>

<section id="findings" class="findings">
<h2>Key findings</h2>
<div class="kpis">
 <div class="kpi"><span class="l">Sharpe · AW (a) EW/EW</span><span class="v">{f['sh_a']}</span><span class="c">market {f['sh_m']}</span></div>
 <div class="kpi"><span class="l">Sharpe · AW (a) ERC/ERC</span><span class="v">{f['sh_aerc']}</span><span class="c">best 48-industry variant</span></div>
 <div class="kpi"><span class="l">Max drawdown</span><span class="v">{f['dd_aerc']}</span><span class="c">market {f['dd_m']}</span></div>
 <div class="kpi"><span class="l">Beta / correlation</span><span class="v">{f['beta_a']} / {f['corr_a']}</span><span class="c">still an equity portfolio</span></div>
 <div class="kpi"><span class="l">2000–02 bust</span><span class="v">{f['dot_a']}</span><span class="c">market {f['dot_m']}</span></div>
</div>
<ol>
<li><b>The macro classification is real.</b> Every quadrant portfolio earns its best return relative to the market in its own regime. With the judgement-based classification (a) the diagonal excess returns are {f['diag_a']} a year; with regressions re-estimated out-of-sample they are still {f['diag_o']}.</li>
<li><b>The All Weather combination beats the market modestly.</b> On 48 industries, equal weights everywhere: CAGR {f['cagr_a']} vs {f['cagr_m']}, Sharpe {f['sh_a']} vs {f['sh_m']}, alpha {f['alpha_a']} a year. Risk-based weights (ERC inside and across quadrants) lift the Sharpe ratio to {f['sh_aerc']} and cut the maximum drawdown to {f['dd_aerc']}.</li>
<li><b>It does not deliver Bridgewater-style crash protection.</b> Beta is {f['beta_a']} and correlation {f['corr_a']}. Balancing industries only diversifies the part of returns that is <i>relative</i> to the market (tracking error {f['te_a']}). Market-wide crashes hit almost in full: 1973–74 {f['oil_a']} (market {f['oil_m']}), 2007–09 {f['gfc_a']} ({f['gfc_m']}).</li>
<li><b>It shines when the market is concentrated in one regime bet</b>: 2000–02 {f['dot_a']} vs {f['dot_m']}, 2022 {f['i22_a']} vs {f['i22_m']}. It lags when one regime's winners dominate cap weights, as with mega-cap tech after 2011.</li>
<li><b>Judgement beats regression.</b> The macro view (a) gives the best Sharpe ratio at every granularity except 10 industries. Full-sample regressions (b) agree with (a) on {f['agree48']} of the 48 industries. Out-of-sample regressions (b-OOS) only roughly match the market's Sharpe ratio, because t-statistics of 1–2 make the quadrant labels noisy.</li>
<li><b>Drawdown-anchored clusters (c) do not cut drawdowns.</b> Assigning industries to quadrants by how their beta-adjusted returns in the market's 10 worst drawdowns resemble gold/TIPS, commodities, Treasuries and cyclicals gives a maximum drawdown of {g['dd_c']} (market {g['dd_m']}). The maximum drawdown is set by 2008, when every quadrant lost {g['gfc_best_q']} or more. Industries alone bottom out near {g['dd_lb']} (the 10 lowest-beta industries). Bridgewater's asset classes, levered to equity volatility, reach {g['dd_aawl']}. Residuals (industry − β·market) do separate the quadrants: a beta-hedged All Weather made {g['h_0002']} in 2000–02 and {g['h_7374']} in 1973–74. But it made only {g['h_0709']} in 2008, so a market + hedged overlay still draws down {g['ov_dd']}.</li>
<li><b>Granularity matters little.</b> From 5 to 49 industries the Sharpe ratio of (a) ERC/ERC stays in a 0.51–0.53 band. What matters is the regime structure, not the number of industries. Equal-weighting all industries gets worse as the set gets finer, while All Weather does not.</li>
</ol>
</section>

<h2 id="allweather"><span class="n">1</span>All Weather in brief, and how we translate it</h2>
<div class="col">
<p>Bridgewater's All Weather portfolio, launched in 1996, starts from the view that asset prices move when <b>growth</b> and <b>inflation</b> differ from what is discounted. Each can come in above or below expectations, giving four environments. Each asset class is biased toward some of them: equities and credit like rising growth, nominal bonds like falling growth and falling inflation, and commodities and inflation-linked bonds like rising inflation. All Weather holds a portfolio for each environment and gives them <b>equal risk</b>, using leverage on low-volatility assets, so it does not have to forecast which environment comes next.</p>
</div>
<div class="aw-diagram" role="table" aria-label="Four environments">
  <span class="hd"></span><span class="hd">Inflation rising</span><span class="hd">Inflation falling</span>
  <span class="hd">Growth rising</span>
  <div class="cell q-GU_IU"><b>G↑ I↑ · reflation</b>Asset classes: commodities, EM credit, linkers. Our industries: steel, machinery, mines, paper, banks.</div>
  <div class="cell q-GU_ID"><b>G↑ I↓ · goldilocks</b>Asset classes: equities, corporate credit. Our industries: tech, autos, retail, restaurants, apparel.</div>
  <span class="hd">Growth falling</span>
  <div class="cell q-GD_IU"><b>G↓ I↑ · stagflation</b>Asset classes: linkers, gold, commodities. Our industries: gold, oil, agriculture, food, tobacco, defence.</div>
  <div class="cell q-GD_ID"><b>G↓ I↓ · disinflationary bust</b>Asset classes: nominal bonds. Our industries: utilities, telecom, drugs, healthcare, insurance.</div>
</div>
<div class="col">
<p>Here the investable universe is <b>only US equity industries</b>. So each industry is classified by how its return <b>in excess of the equity market</b> responds to growth and inflation. Quadrant portfolios are long-only industry baskets, and All Weather is a fully invested, unlevered mix of the four.</p>
<div class="note">This changes what the exercise can achieve. Every industry carries a market beta near one, so balancing them diversifies the regime-driven <i>relative</i> returns and leaves the market factor untouched. Bridgewater's version gets most of its crash protection from bonds. Ours can only beat the market by tilting away from whichever regime bet the cap-weighted index happens to be concentrated in.</div>
</div>

<h2 id="regimes"><span class="n">2</span>Measuring growth and inflation regimes</h2>
<div class="col">
<p>Growth is year-on-year real GDP growth; inflation is year-on-year CPI inflation (quarterly average of monthly CPI). Bridgewater frames regimes relative to expectations. Without a long consensus-forecast history, we use the <b>quarter-on-quarter change</b> in those YoY rates as the surprise proxy: growth is "rising" when YoY growth accelerates. From 1948Q2 to 2026Q2 the 313 quarters split 69 / 78 / 94 / 72 across G↑I↑ / G↑I↓ / G↓I↑ / G↓I↓, and the regime changes in 61% of quarters. That is why a static, balanced portfolio makes sense: the regime is hard to time.</p>
</div>
{fig('macro', 'GDP growth and CPI inflation with regime strip', 'Quarterly regime = sign of the change in YoY real GDP growth × sign of the change in YoY CPI inflation. Macro data from FRED.')}

<h2 id="classification"><span class="n">3</span>Classifying industries</h2>
<div class="two">
<div><h3>(a) Macro-economic view</h3>
<p>Each industry gets a judgement score of ±1 or ±2 on growth and on inflation, based on its business economics: commodity exposure, pricing power, demand elasticity, cash-flow duration and rate sensitivity. Gold miners are the textbook stagflation hedge (G↓ I↑). Oil follows the 1973/79/2022 supply-shock pattern (G↓ I↑). Steel and machinery are capex-cycle commodity producers (G↑ I↑). Tech, autos and restaurants are long-duration or discretionary (G↑ I↓). Utilities, telecoms and drugs are bond proxies (G↓ I↓). The sign pair sets the quadrant. Scores were written down before looking at any regression.</p></div>
<div><h3>(b) Regression view</h3>
<p>Quarterly industry return minus market return is regressed on the standardised changes in YoY GDP growth and YoY CPI inflation (both entered together, clipped at ±3σ to contain the 2020 swing, Newey-West t-stats with 4 lags, 1948Q2–2026Q2). The signs of the two betas set the quadrant. A strictly out-of-sample version (<b>b-OOS</b>) re-estimates every January on an expanding window, using data only through Q3 of the prior year.</p></div>
</div>
<div class="col"><p>If a quadrant would be empty (only at coarse levels), the industry with the highest score in that direction is borrowed into it. The chart shows both views at once: position is the regression t-statistics (b), colour is the macro view (a). Industries whose colour matches their corner are the {f['agree48']} where the two agree.</p></div>
{fig('scatter', 'Regression t-stats per industry coloured by macro classification', '48 industries. Axes: HAC t-statistics of the growth and inflation betas of industry-minus-market returns (b). Colour: judgement quadrant (a). The two views agree on the growth sign for ' + f['gagree48'] + ' of industries and on the inflation sign for ' + f['iagree48'] + '.')}
<div class="col"><p>The regressions support the textbook macro calls: coal, oil, steel, machinery, gold and agriculture load positively on inflation surprises, while restaurants, retail, apparel and consumer services are hurt. The surprises are interesting too. <b>Banks</b> behave defensively rather than as reflation trades. <b>Utilities</b> and <b>insurers</b> carry slightly positive inflation betas once the market is netted out. <b>Construction</b> and <b>building materials</b> act as rate-sensitive housing plays (I↓) rather than real-asset plays.</p></div>
<div class="quadgrid">{T['QLIST']}</div>
<h3>Agreement between (a) and (b) at each level</h3>
{T['T_AGREE']}
<details><summary>Full 48-industry classification table (rationale, betas, t-stats, out-of-sample stability)</summary>
<p style="margin-top:10px">β = change in annualised quarterly excess-of-market return (%) per 1σ move in the macro surprise. "OOS = full-sample" = share of years in which the out-of-sample classification matched the full-sample one.</p>
{T['T_CLASS48']}</details>

<h2 id="validation"><span class="n">4</span>Does the classification work?</h2>
<div class="col"><p>The direct test: in which realised regimes does each quadrant portfolio beat the market? If the classification is right, the diagonal should be the best cell in each row. For (a) this is a genuine test, since the scores were set from economics rather than fitted. For (b) in-sample the diagonal is partly built in, which is why the out-of-sample panel matters.</p></div>
{fig('heat', 'Regime heatmaps', 'Average annualised quarterly return of each 48-industry quadrant portfolio (equal-weighted) minus the market, by realised regime, ' + f['period'] + '. Outlined: own regime.')}
<div class="col"><p>All three panels have a positive diagonal. The macro view gives the cleanest pattern: its stagflation basket returns +7.1% a year over the market in stagflation quarters and −3.5% in goldilocks quarters. In the macro view the reflation (G↑ I↑) quadrant is the weakest, because industrial cyclicals respond to growth more than to inflation. Over the long run the quadrant portfolios drift a long way apart against the market. That dispersion is what an equal-risk mix diversifies.</p></div>
{fig('quads', 'Quadrant portfolio wealth relative to market', 'Wealth of each quadrant portfolio divided by market wealth (log scale), 48 industries, equal-weighted. Left: macro view. Right: out-of-sample regression view.')}

<h2 id="base"><span class="n">5</span>The 48-industry All Weather portfolio</h2>
<div class="col"><p>Base case: industries equal-weighted within each quadrant, quadrants equal-weighted in All Weather, rebalanced monthly. The table adds the equal-weighted average of all 48 industries as a benchmark. Some of any industry strategy's edge over the cap-weighted market comes from equal weighting itself, and this separates the two.</p></div>
{fig('wealth', 'Cumulative wealth', 'Growth of $1, log scale. All Weather variants use equal weights within and across quadrants.')}
{T['T_HEAD']}
<div class="col"><p>All Weather (a) beats both the market and the equal-weighted industry average on every risk-adjusted measure. The edge over the market is around 1% a year, with near-identical volatility. Beta stays near one: this is a better-diversified equity portfolio, not a different asset class.</p></div>
<h3>Drawdowns</h3>
{fig('dd', 'Drawdown chart', 'Drawdown from running peak. Shaded: market. Line: All Weather (a), equal-weighted.')}
<div class="two"><div><h3>All Weather (a): five worst drawdowns</h3>{T['T_EPI']}</div><div><h3>Market: five worst drawdowns</h3>{T['T_EPI_M']}</div></div>
<h3>Behaviour in stress episodes</h3>
{T['T_CRISIS']}
<div class="col"><p>The pattern is clear. When the market falls on a <b>concentrated regime bet</b>, All Weather protects. The 2000–02 bust was a goldilocks/tech unwind and the 2022 sell-off was an inflation shock; in both, the stagflation and defensive quadrants offset the losers. In <b>systemic</b> sell-offs (1973–74, 2008, March 2020) every industry falls together and the quadrant structure cannot help. In March 2020 the cyclical and energy-heavy quadrants fell more than the market. Bonds, which All Weather lacks here, are the missing hedge.</p></div>
{fig('rel', 'Relative wealth vs market', 'All Weather wealth divided by market wealth. Rising = outperforming. Shaded: stress episodes.')}
<h3>Excess return vs market by realised regime</h3>
{T['T_AWREG']}
<div class="col"><p>The macro-view portfolio beats the market on average in all four regimes, most in disinflationary busts and stagflation, and roughly matches it in reflation. That is what "all weather" should mean for a relative-to-market portfolio.</p></div>

<h2 id="variants"><span class="n">6</span>Weighting variants</h2>
<div class="col"><p>Within each quadrant: equal weight (EW), inverse volatility (IV) or equal risk contribution (ERC) of the industries. Across quadrants: EW or ERC of the four quadrant portfolios. Risk models use 60 months of returns (ERC covariance shrunk 20% toward its diagonal), estimated with data to t−1. Turnover is annual one-way and includes drift.</p></div>
{fig('var', 'Sharpe and drawdown by weighting scheme', '48 industries. Dashed line: market. Labels read within-quadrant / across-quadrant scheme.')}
{T['T_VAR']}
<div class="col"><p>Risk-based weighting helps consistently but modestly: about +0.01 Sharpe from IV or ERC within quadrants and another +0.01 from ERC across them, which also takes 2–3 points off the maximum drawdown. The two steps add about the same Sharpe, but only ERC across quadrants reduces drawdowns. It cuts the growth quadrants to about 21% of capital each and raises the two growth-down quadrants to about 29% each. That is the true risk-parity step, and the equity analogue of Bridgewater levering up bonds. Turnover stays around 20% a year for all schemes. The classification choice, (a) vs (b) vs (b-OOS), matters about twice as much as the weighting scheme.</p></div>
{fig('qw', 'Quadrant capital weights over time', 'Capital weights of the four quadrants under ERC across quadrants (48 industries, macro view, ERC within). Equal risk means unequal capital: the lower-volatility growth-down quadrants get the most.')}

<h2 id="levels"><span class="n">7</span>Industry granularity: 5 to 49 industries</h2>
<div class="col"><p>French publishes 5, 10, 12, 17, 30, 38, 48 and 49 industry sets (there is no 11, 20 or 120). We hand-classified every set with view (a) and re-ran the regressions (b) for each.</p></div>
{fig('lev', 'Sharpe and drawdown by number of industries', 'All Weather with ERC within and across quadrants, plus the equal-weighted all-industry benchmark. Dashed line: market.')}
<div class="two"><div><h3>Sharpe ratio</h3>{T['T_LEV_S']}</div><div><h3>Maximum drawdown</h3>{T['T_LEV_D']}</div></div>
<div class="col"><p>More industries do not mean better macro balance. The macro view is stable from 5 to 49 (Sharpe 0.51–0.53), and the 17-industry set has the shallowest drawdown. The regression views are less stable. With few industries, a single misclassified sector moves a whole quadrant, and the 5- and 10-industry sets need a borrowed industry to fill the stagflation quadrant. With many, the t-statistics are noisier. The equal-weighted benchmark gets <i>worse</i> with granularity, because finer sets over-weight small cyclical niches. The quadrant structure stops that from happening, which is a direct way to see its diversification value.</p></div>

SECTION_DD
<h2 id="conclusions"><span class="n">9</span>Conclusions and next steps</h2>
<div class="col">
<ul>
<li>The growth/inflation framework transfers well to equity industries as a <b>relative-value</b> map. Industries sort reliably into regime winners and losers, and an economically reasoned classification holds up better than a fitted one.</li>
<li>An industry-only All Weather is a <b>better-diversified equity portfolio</b>: Sharpe 0.50–0.53 vs 0.46, slightly smaller drawdowns, strong protection against concentration unwinds. It is not a multi-asset crash hedge.</li>
<li>Clustering industries on their behaviour in the 10 worst market drawdowns (c) does <b>not</b> reduce drawdowns, because every industry falls in a systemic crash. Lower drawdowns need lower beta: low-beta industries reach about −40%, and real bonds and gold reach −16% unlevered. Beta-hedged residuals protect in regime-driven crashes (1973–74, 1980–82, 2000–02) but not in the 2008 beta crash.</li>
<li>Prefer <b>ERC across quadrants</b>, the step that actually equalises regime risk, together with the macro classification. Industry granularity is a second-order choice; 17–48 industries is a sensible range.</li>
</ul>
<p><b>Suggested extensions.</b> (1) Use the macro-classified industry quadrants as the equity sleeve of an asset-class All Weather (Treasuries, gold/TIPS, commodities), or run the beta-hedged industry All Weather of section 8 as a separate sleeve. It pays off in regime-driven crashes and is uncorrelated with the market. (2) Measure surprises against expectations (Survey of Professional Forecasters, breakevens) rather than as changes in realised data. (3) Use time-varying, shrunk betas for (b), Bayesian-blended with the (a) priors. (4) Lever to a target volatility and add transaction costs.</p>
</div>

<h2 id="method"><span class="n">10</span>Method and data notes</h2>
<div class="col">
<ul>
<li><b>Returns:</b> Kenneth French value-weighted monthly industry portfolios (5…49), CRSP 2026-08 vintage. Market = Mkt-RF + RF from the Fama-French research factors. Missing values (−99.99) are treated as not investable.</li>
<li><b>Eligibility:</b> an industry is held from month t only if it has 36 consecutive months of returns to t−1 (for example, Gold, Soda, Guns and FabPr enter in the mid-1960s). Quadrant portfolios are built from 1931 to give the across-quadrant risk models history. All results are reported over {f['period']}, the window where the out-of-sample classification exists.</li>
<li><b>Look-ahead:</b> weights use only past returns. Classification (a) and (b) are static over the full sample. (b) is in-sample by construction, and (b-OOS) is the honest benchmark for it. (a) uses no fitted data, but it is written with today's knowledge of industry economics.</li>
<li><b>Not included:</b> transaction costs (turnover is about 20% a year one-way, so cost drag is small), leverage, taxes.</li>
<li><b>Code:</b> <code>allweather/</code> package (data, classify, portfolio, analytics, figures), <code>run.py</code> (study grid), <code>run_dd.py</code> + <code>allweather/ddcluster.py</code> + <code>allweather/assets.py</code> (drawdown-anchored section), <code>report.py</code>, <code>report_dd.py</code> and <code>build_html.py</code> (this page).</li>
<li><b>Asset proxies (section 8):</b> gold from datahub.io (LBMA-based monthly prices); TIPS = iShares TIP ETF total return (Yahoo, 2004+); commodities = S&amp;P GSCI (Yahoo, 1985+) spliced with an FRED spot composite (WTI, PPI metals, PPI farm products) plus T-bill yield; Treasuries = 10-year constant-maturity total return from FRED GS10. Spot-based commodity returns before 1985 ignore roll yield.</li>
</ul>
</div>
<footer>Sources: Kenneth R. French Data Library (Dartmouth Tuck); FRED, Federal Reserve Bank of St. Louis; Bridgewater Associates, "The All Weather Story". Past performance of back-tested portfolios is hypothetical and does not include costs.</footer>
</div>
"""
SEC_FILLED = SEC.format(T_EPS=T["T_EPS"], QC=T["QC"], T_DD_MAIN=T["T_DD_MAIN"], T_DD_OOS=T["T_DD_OOS"], T_DD_LEV=T["T_DD_LEV"],
    fig_epheat=fig("dd_epheat", "Episode heatmap", "Beta-adjusted excess return (%) of each anchor asset and each industry over the 10 market drawdowns. Industry rows are demeaned across industries within each episode and grouped by cluster, ordered by correlation with the cluster anchor. Colour clipped at ±40%."),
    fig_epbars=fig("dd_epbars", "Quadrant returns per drawdown episode", "Total return of the market and of each (c) quadrant portfolio (48 industries, equal-weighted) over each of the 10 drawdown episodes."),
    fig_dd2=fig("dd_dd2", "Drawdown comparison", "Drawdowns since 1970. The asset All Weather is ERC across the four anchor quadrants, levered with a constant multiple (financed at the T-bill rate) to the market's realised volatility. This is ex-post scaling, shown for illustration."),
    **g)
SUB_FILLED = SUB.format(QC2=T["QC2"], T_HEDGED=T["T_HEDGED"], T_OVERLAY=T["T_OVERLAY"],
    chg_c2=f"{100 - int(g['agree_c2'].rstrip('%'))}%",
    fig_hedbars=fig("dd_hedbars", "Hedged All Weather returns per drawdown episode", "Total return over each of the 10 market drawdowns: market vs beta-hedged All Weather (industry − β·market, trailing 60-month β), equal weights within and across quadrants."),
    **g)
SEC_FILLED = SEC_FILLED.replace("SUB_HEDGE", SUB_FILLED)
H = H.replace("SECTION_DD", SEC_FILLED)
open("results/industry_all_weather.html", "w", encoding="utf-8").write(H)
print(len(H) / 1e6, "MB")
