"""Build the HTML report (results/industry_all_weather.html) from results/results.pkl."""
import html
import pickle

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from allweather import analytics as A
from allweather import data as D
from allweather.classify import QUADS, QUAD_LABEL, quad_table
from allweather.figures import QSLOT, date_axis, pct, render, ts

EVAL = ("1965-01", None)      # common window: OOS classification starts 1965
R = pickle.load(open("results/results.pkl", "rb"))
F, L, MACRO = R["factors"], R["levels"], R["macro"]
RF, MKT = F["RF"], F["Mkt"]
MKT_Q = D.to_quarterly(F[["Mkt"]])["Mkt"]
CLS_NAME = {"a": "(a) Macro view", "b": "(b) Regression, full sample", "b_oos": "(b) Regression, out-of-sample"}
CLS_SHORT = {"a": "(a) macro", "b": "(b) regr. IS", "b_oos": "(b) regr. OOS"}
QSHORT = {"GU_IU": "G↑ I↑", "GU_ID": "G↑ I↓", "GD_IU": "G↓ I↑", "GD_ID": "G↓ I↓"}
SCHEMES = [("EW", "EW"), ("IV", "EW"), ("ERC", "EW"), ("EW", "ERC"), ("IV", "ERC"), ("ERC", "ERC")]


def ev(s):
    return s.loc[EVAL[0]:EVAL[1]]


def aw(n, cls, wi="EW", ac="EW"):
    return ev(L[n]["runs"][(cls, wi, ac)]["aw"])


def st(r):
    return A.stats(r, RF, MKT)


MKT_E = ev(MKT).loc[: aw(48, "a").index[-1]]
PERIOD = f"{MKT_E.index[0].strftime('%b %Y')} – {MKT_E.index[-1].strftime('%b %Y')}"

# ---------------------------------------------------------------- formatting helpers
P = lambda x, d=1: f"{x * 100:.{d}f}%"
N = lambda x, d=2: f"{x:.{d}f}"


def table(df, fmt, cls="", hl=None):
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = []
    for i, (idx, row) in enumerate(df.iterrows()):
        tr_cls = ' class="hl"' if hl is not None and idx in hl else ""
        cells = "".join(f"<td>{fmt.get(c, lambda v: v)(v) if not (isinstance(v, float) and np.isnan(v)) else '–'}</td>"
                        for c, v in row.items())
        body.append(f"<tr{tr_cls}><th scope='row'>{html.escape(str(idx))}</th>{cells}</tr>")
    return (f"<div class='tbl {cls}'><table><thead><tr><th></th>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


STAT_FMT = {"CAGR": P, "Vol": P, "Sharpe": N, "Sortino": N, "MaxDD": P, "Calmar": N, "Worst 12m": P,
            "Beta": N, "Alpha": P, "Corr": N, "TE": P, "Turnover": lambda x: P(x, 0)}
STAT_COLS = ["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD", "Calmar", "Worst 12m", "Beta", "Alpha", "TE"]


def fig(imgs, alt, cap=""):
    c = f"<figcaption>{cap}</figcaption>" if cap else ""
    return (f"<figure><img class='th-light' alt='{html.escape(alt)}' src='data:image/png;base64,{imgs['light']}'>"
            f"<img class='th-dark' alt='{html.escape(alt)}' src='data:image/png;base64,{imgs['dark']}'>{c}</figure>")


# ================================================================ FIGURES
FIG = {}

# F1 macro regimes ---------------------------------------------------------
def f_macro(fig_, T):
    m = MACRO.loc["1950":]
    x = ts(m.index)
    axs = fig_.subplots(3, 1, sharex=True, gridspec_kw={"height_ratios": [3, 3, 0.7]})
    for ax, col, title, slot in [(axs[0], "growth", "Real GDP growth, % YoY", 0), (axs[1], "inflation", "CPI inflation, % YoY", 1)]:
        ax.plot(x, m[col], color=T["s"][slot], lw=1.4)
        ax.axhline(0, color=T["axis"], lw=0.8)
        ax.set_title(title, fontsize=10)
    reg = (np.where(m.dG > 0, "GU", "GD").astype(object) + "_" + np.where(m.dI > 0, "IU", "ID"))
    for xi, r in zip(x, reg):
        axs[2].axvspan(xi, xi + pd.offsets.QuarterEnd(1), color=T["s"][QSLOT[r]], lw=0)
    axs[2].set_yticks([]); axs[2].grid(False)
    axs[2].set_title("Realised regime each quarter (direction of change in YoY growth and inflation)", fontsize=9, fontweight="normal", color=T["ink2"])
    axs[2].legend(handles=[Patch(color=T["s"][QSLOT[q]], label=QSHORT[q]) for q in QUADS], ncol=4,
                  loc="upper center", bbox_to_anchor=(0.5, -0.6), fontsize=8.5)
    date_axis(axs[2], 10)
FIG["macro"] = render(f_macro, (9, 5.6))

# F2 classification scatter (48) -------------------------------------------
def f_scatter(fig_, T, n=48):
    ax = fig_.subplots()
    sb, sa = L[n]["scores"]["b"], L[n]["scores"]["a"]
    qa = quad_table(sa)
    lim = max(4.5, np.ceil(sb[["t_g", "t_i"]].abs().max().max() + 0.3))
    ax.axhline(0, color=T["axis"], lw=1); ax.axvline(0, color=T["axis"], lw=1)
    for q in QUADS:
        idx = qa.index[qa == q]
        ax.scatter(sb.loc[idx, "t_g"], sb.loc[idx, "t_i"], s=46, color=T["s"][QSLOT[q]], edgecolor=T["surface"],
                   linewidth=1.5, zorder=3, label=f"(a) {QSHORT[q]}")
    from adjustText import adjust_text
    texts = [ax.text(r.t_g, r.t_i, c, fontsize=7.2, color=T["ink2"]) for c, r in sb.iterrows()]
    adjust_text(texts, x=sb.t_g.values, y=sb.t_i.values, ax=ax, expand=(1.15, 1.3),
                arrowprops=dict(arrowstyle="-", color=T["muted"], lw=0.5))
    for (sx, sy), q in {(1, 1): "GU_IU", (1, -1): "GU_ID", (-1, 1): "GD_IU", (-1, -1): "GD_ID"}.items():
        ax.text(sx * (lim - 0.15), sy * (lim - 0.25), "(b) " + QSHORT[q], ha="right" if sx > 0 else "left",
                va="top" if sy > 0 else "bottom", fontsize=9, color=T["muted"], fontweight="bold")
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    ax.set_xlabel("growth sensitivity  (HAC t-stat of β on Δ GDP growth)")
    ax.set_ylabel("inflation sensitivity  (HAC t-stat of β on Δ CPI inflation)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4, fontsize=8.5, title=None)
FIG["scatter"] = render(f_scatter, (9, 7.4))

# F3 regime validation heatmaps ---------------------------------------------
REGTAB = {}
for cls in ["a", "b", "b_oos"]:
    q = ev(L[48]["runs"][(cls, "EW", "EW")]["quads"])
    t, cnt = A.regime_table(D.to_quarterly(q), MKT_Q, MACRO)
    REGTAB[cls] = t.loc[QUADS, QUADS]
REG_COUNT = cnt


def f_heat(fig_, T):
    axs = fig_.subplots(1, 3)
    cm = LinearSegmentedColormap.from_list("div", [T["neg"], T["mid"], T["pos"]])
    for ax, cls in zip(axs, ["a", "b", "b_oos"]):
        M = REGTAB[cls].values * 100
        ax.imshow(M, cmap=cm, vmin=-6, vmax=6)
        ax.set_xticks(range(4), [QSHORT[q] for q in QUADS], fontsize=8)
        ax.set_yticks(range(4), [QSHORT[q] for q in QUADS] if cls == "a" else [""] * 4, fontsize=8)
        ax.grid(False)
        for i in range(4):
            for j in range(4):
                ax.text(j, i, f"{M[i, j]:+.1f}", ha="center", va="center", fontsize=8.5,
                        color=T["ink"], fontweight="bold" if i == j else "normal")
            ax.add_patch(__import__("matplotlib").patches.Rectangle((i - .5, i - .5), 1, 1, fill=False, ec=T["ink"], lw=1.2))
        ax.set_title(CLS_SHORT[cls], fontsize=10)
        ax.set_xlabel("realised regime", fontsize=8.5)
        for s in ax.spines.values():
            s.set_visible(False)
    axs[0].set_ylabel("quadrant portfolio", fontsize=8.5)
FIG["heat"] = render(f_heat, (10, 3.8))

# F4 wealth -----------------------------------------------------------------
BASE = {c: aw(48, c) for c in ["a", "b", "b_oos"]}


def f_wealth(fig_, T):
    ax = fig_.subplots()
    x = ts(MKT_E.index)
    ax.plot(x, A.wealth(MKT_E), color=T["ref"], lw=1.4, label="US equity market (CRSP VW)")
    for k, c in zip(["a", "b", "b_oos"], [0, 1, 2]):
        ax.plot(x, A.wealth(BASE[k]), color=T["s"][c], lw=1.6, label=f"All Weather {CLS_SHORT[k]}")
    ax.set_yscale("log"); ax.set_ylabel("growth of $1 (log scale)")
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.legend(loc="upper left", fontsize=8.5); date_axis(ax, 5)
FIG["wealth"] = render(f_wealth, (9, 4.4))

# F5 drawdowns --------------------------------------------------------------
def f_dd(fig_, T):
    ax = fig_.subplots()
    x = ts(MKT_E.index)
    ax.fill_between(x, A.drawdown(MKT_E), 0, color=T["ref"], alpha=0.22, lw=0, label="US equity market")
    ax.plot(x, A.drawdown(MKT_E), color=T["ref"], lw=0.8)
    ax.plot(x, A.drawdown(BASE["a"]), color=T["s"][0], lw=1.4, label="All Weather (a) macro")
    pct(ax); ax.set_ylabel("drawdown from peak"); ax.legend(loc="lower left", fontsize=8.5); date_axis(ax, 5)
FIG["dd"] = render(f_dd, (9, 3.6))

# F6 relative wealth --------------------------------------------------------
def f_rel(fig_, T):
    ax = fig_.subplots()
    x = ts(MKT_E.index)
    for k, c in zip(["a", "b", "b_oos"], [0, 1, 2]):
        ax.plot(x, A.wealth(BASE[k]) / A.wealth(MKT_E), color=T["s"][c], lw=1.5, label=CLS_SHORT[k])
    ax.axhline(1, color=T["axis"], lw=1)
    ax.set_ylabel("All Weather wealth ÷ market wealth")
    for lab, (s, e) in {"oil shocks": ("1973-01", "1974-09"), "dot-com": ("2000-03", "2002-09"),
                        "GFC": ("2007-11", "2009-02"), "2022": ("2022-01", "2022-09")}.items():
        ax.axvspan(pd.Period(s).to_timestamp(), pd.Period(e).to_timestamp(), color=T["grid"], alpha=0.8, lw=0)
        ax.text(pd.Period(s).to_timestamp(), ax.get_ylim()[1], " " + lab, fontsize=7.5, color=T["muted"], va="top")
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.92), fontsize=8.5); date_axis(ax, 5)
FIG["rel"] = render(f_rel, (9, 3.8))

# F7 quadrant portfolios relative to market ---------------------------------
def f_quads(fig_, T):
    axs = fig_.subplots(1, 2, sharey=True)
    for ax, cls in zip(axs, ["a", "b_oos"]):
        q = ev(L[48]["runs"][(cls, "EW", "EW")]["quads"])
        x = ts(q.index)
        for qq in QUADS:
            ax.plot(x, A.wealth(q[qq]) / A.wealth(MKT_E.reindex(q.index)), color=T["s"][QSLOT[qq]], lw=1.4, label=QSHORT[qq])
        ax.axhline(1, color=T["axis"], lw=1); ax.set_yscale("log")
        ax.set_title(CLS_SHORT[cls], fontsize=10); date_axis(ax, 10)
        from matplotlib.ticker import ScalarFormatter, FixedLocator
        ax.yaxis.set_major_locator(FixedLocator([0.25, 0.5, 1, 2, 4, 8]))
        ax.yaxis.set_major_formatter(ScalarFormatter()); ax.yaxis.set_minor_formatter(__import__("matplotlib").ticker.NullFormatter())
    axs[0].set_ylabel("quadrant wealth ÷ market wealth (log)")
    axs[1].legend(loc="upper left", fontsize=8.5)
FIG["quads"] = render(f_quads, (10, 3.9))

# F8 weighting variants (48) -------------------------------------------------
VAR = []
for cls in ["a", "b", "b_oos"]:
    for wi, ac in SCHEMES:
        s = st(aw(48, cls, wi, ac)); s["Turnover"] = L[48]["runs"][(cls, wi, ac)]["turnover"]
        VAR.append(dict(cls=cls, scheme=f"{wi} / {ac}", **s))
VAR = pd.DataFrame(VAR)


def f_var(fig_, T):
    axs = fig_.subplots(1, 2)
    xs = np.arange(len(SCHEMES)); w = 0.26
    for ax, col, lab in [(axs[0], "Sharpe", "Sharpe ratio"), (axs[1], "MaxDD", "maximum drawdown")]:
        for j, cls in enumerate(["a", "b", "b_oos"]):
            v = VAR[VAR.cls == cls][col].values
            ax.bar(xs + (j - 1) * w, v, w * 0.92, color=T["s"][j], label=CLS_SHORT[cls], zorder=3)
        ref = st(MKT_E)[col]
        ax.axhline(ref, color=T["ref"], lw=1.2, ls="--", zorder=4)
        ax.text(-0.45, ref, "market", fontsize=8, color=T["ink2"], va="bottom" if col == "Sharpe" else "top", ha="left")
        ax.set_xticks(xs, [s.replace(" / ", "\n") for s in VAR.scheme.unique()], fontsize=8)
        ax.set_title(lab, fontsize=10)
        if col == "Sharpe":
            ax.set_ylim(0.4, max(VAR.Sharpe) + 0.03)
        else:
            pct(ax); ax.set_ylim(min(VAR.MaxDD) - 0.02, -0.4)
    axs[0].legend(loc="upper left", fontsize=8, ncol=3)
    fig_.text(0.5, 0.01, "within-quadrant weighting / across-quadrant weighting", ha="center", fontsize=8.5, color=T["ink2"])
    return (0, 0.04, 1, 1)
FIG["var"] = render(f_var, (10, 3.9))

# F9 industry granularity ----------------------------------------------------
LEV = []
for n in D.LEVELS:
    for cls in ["a", "b", "b_oos"]:
        for wi, ac in [("EW", "EW"), ("ERC", "ERC")]:
            s = st(aw(n, cls, wi, ac)); LEV.append(dict(n=n, cls=cls, scheme=f"{wi}/{ac}", **s))
    s = st(ev(L[n]["ew_all"])); LEV.append(dict(n=n, cls="EWall", scheme="EW", **s))
LEV = pd.DataFrame(LEV)


def f_lev(fig_, T):
    axs = fig_.subplots(1, 2)
    xs = np.arange(len(D.LEVELS))
    for ax, col, lab in [(axs[0], "Sharpe", "Sharpe ratio"), (axs[1], "MaxDD", "maximum drawdown")]:
        for j, cls in enumerate(["a", "b", "b_oos"]):
            v = LEV[(LEV.cls == cls) & (LEV.scheme == "ERC/ERC")].set_index("n")[col]
            ax.plot(xs, v.values, color=T["s"][j], marker="o", ms=5, mec=T["surface"], mew=1.5, label=f"{CLS_SHORT[cls]}  ERC/ERC")
        v = LEV[LEV.cls == "EWall"].set_index("n")[col]
        ax.plot(xs, v.values, color=T["s"][3], marker="s", ms=5, mec=T["surface"], mew=1.5, lw=1.2, label="all industries EW")
        ax.axhline(st(MKT_E)[col], color=T["ref"], lw=1.2, ls="--")
        ax.text(xs[0], st(MKT_E)[col], "market", fontsize=8, color=T["ink2"], va="bottom", ha="left")
        ax.set_xticks(xs, D.LEVELS); ax.set_xlabel("number of French industries")
        ax.set_title(lab, fontsize=10)
        if col == "MaxDD":
            pct(ax)
    h, l = axs[0].get_legend_handles_labels()
    fig_.legend(h, l, loc="lower center", ncol=4, fontsize=8.2, bbox_to_anchor=(0.5, -0.01))
    return (0, 0.08, 1, 1)
FIG["lev"] = render(f_lev, (10, 4.3))

# F10 quadrant weights through time (48, a, ERC/ERC) -------------------------
def f_qw(fig_, T):
    ax = fig_.subplots()
    qw = ev(L[48]["runs"][("a", "ERC", "ERC")]["qw"]).fillna(0)[QUADS]
    x = ts(qw.index)
    ax.stackplot(x, qw.T.values, colors=[T["s"][QSLOT[q]] for q in QUADS], labels=[QSHORT[q] for q in QUADS],
                 edgecolor=T["surface"], linewidth=0.4)
    ax.axhline(0.25, color=T["surface"], lw=0.6, ls=":"); ax.axhline(0.5, color=T["surface"], lw=0.6, ls=":"); ax.axhline(0.75, color=T["surface"], lw=0.6, ls=":")
    ax.set_ylim(0, 1); ax.set_xlim(x[0], x[-1]); pct(ax); ax.grid(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), ncol=4, fontsize=8.5); date_axis(ax, 5)
    ax.set_ylabel("capital weight")
FIG["qw"] = render(f_qw, (9, 3.4))

# ================================================================ TABLES
HEAD = pd.DataFrame({"US equity market": st(MKT_E), "All industries, EW": st(ev(L[48]["ew_all"])),
                     **{f"All Weather {CLS_SHORT[k]}": st(BASE[k]) for k in ["a", "b", "b_oos"]},
                     "All Weather (a) ERC/ERC": st(aw(48, "a", "ERC", "ERC"))}).T[STAT_COLS]
T_HEAD = table(HEAD, STAT_FMT, hl=["All Weather (a) macro"])

EPIS = {"1973–74 oil shock": ("1973-01", "1974-09"), "1980–82 Volcker": ("1980-12", "1982-07"),
        "2000–02 dot-com bust": ("2000-09", "2002-09"), "2007–09 GFC": ("2007-11", "2009-02"),
        "2020 Covid crash": ("2020-01", "2020-03"), "2022 inflation shock": ("2022-01", "2022-09")}
cr = {}
for k, (s, e) in EPIS.items():
    row = {"Market": (1 + MKT.loc[s:e]).prod() - 1}
    for c in ["a", "b", "b_oos"]:
        row[CLS_SHORT[c]] = (1 + BASE[c].loc[s:e]).prod() - 1
    cr[k] = row
CRISIS = pd.DataFrame(cr).T
T_CRISIS = table(CRISIS, {c: P for c in CRISIS.columns})

EPI = A.dd_episodes(BASE["a"], 5)
EPI_M = A.dd_episodes(MKT_E, 5)
def _epi(df):
    d = df.copy()
    d.index = [f"#{i+1}" for i in range(len(d))]
    for c in ["Start", "Trough", "Recovery"]:
        d[c] = d[c].map(lambda v: v.strftime("%b %Y") if v is not None and not pd.isna(v) else "not yet")
    d["Months to trough"] = [(t - s).n if True else 0 for s, t in zip(df.Start, df.Trough)]
    return d[["Start", "Trough", "Recovery", "Depth", "Months to trough"]]
T_EPI = table(_epi(EPI), {"Depth": P})
T_EPI_M = table(_epi(EPI_M), {"Depth": P})

aw_reg = {}
for c in ["a", "b", "b_oos"]:
    t, _ = A.regime_table(D.to_quarterly(BASE[c].to_frame("aw")), MKT_Q, MACRO)
    aw_reg[CLS_SHORT[c]] = t.loc["aw", QUADS]
AWREG = pd.DataFrame(aw_reg).T
AWREG.columns = [QSHORT[q] + f" ({REG_COUNT.get(q, 0)}q)" for q in QUADS]
T_AWREG = table(AWREG, {c: (lambda v: f"{v*100:+.1f}%") for c in AWREG.columns})

VT = VAR.copy()
VT.index = [f"{CLS_SHORT[c]} · {s}" for c, s in zip(VT.cls, VT.scheme)]
T_VAR = table(VT[["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "Beta", "Alpha", "Turnover"]], STAT_FMT,
              hl=[i for i in VT.index if i.endswith("ERC / ERC")])

LT = LEV[LEV.scheme.isin(["ERC/ERC", "EW"]) | (LEV.scheme == "EW/EW")]
def _lev_tab(col, f):
    d = LEV.assign(key=lambda x: x.cls.map(lambda c: CLS_SHORT.get(c, "all industries EW")) + np.where(x.cls == "EWall", "", " " + x.scheme))
    return d.pivot(index="key", columns="n", values=col).loc[
        [f"{CLS_SHORT[c]} {s}" for c in ["a", "b", "b_oos"] for s in ["EW/EW", "ERC/ERC"]] + ["all industries EW"]].rename(columns=str)
T_LEV_S = table(_lev_tab("Sharpe", N), {str(n): N for n in D.LEVELS})
T_LEV_D = table(_lev_tab("MaxDD", P), {str(n): P for n in D.LEVELS})

AGREE = {}
for n in D.LEVELS:
    a, b = quad_table(L[n]["scores"]["a"]), quad_table(L[n]["scores"]["b"]).reindex(quad_table(L[n]["scores"]["a"]).index)
    sa, sb = L[n]["scores"]["a"], L[n]["scores"]["b"].reindex(sa.index if False else L[n]["scores"]["a"].index)
    AGREE[str(n)] = {"same quadrant": (a == b).mean(), "same growth sign": (np.sign(sa.g) == np.sign(sb.g)).mean(),
                     "same inflation sign": (np.sign(sa.i) == np.sign(sb.i)).mean(),
                     "(a) sizes G↑I↑/G↑I↓/G↓I↑/G↓I↓": "/".join(str((a == q).sum()) for q in QUADS),
                     "(b) sizes": "/".join(str((b == q).sum()) for q in QUADS)}
AG = pd.DataFrame(AGREE)
T_AGREE = table(AG, {c: (lambda v: P(v, 0) if isinstance(v, float) else v) for c in AG.columns})

# full 48 classification table
sa48, sb48 = L[48]["scores"]["a"], L[48]["scores"]["b"]
oos_last = quad_table(L[48]["oos_fits"][max(L[48]["oos_fits"])])
oos_hist = pd.DataFrame({y: quad_table(s) for y, s in L[48]["oos_fits"].items()}).T
oos_stab = (oos_hist == quad_table(sb48).reindex(oos_hist.columns)).mean()
rows = []
for c in sa48.index:
    qa, qb = quad_table(sa48)[c], quad_table(sb48)[c]
    rows.append(f"<tr><th scope='row'>{c}</th><td><span class='q q-{qa}'>{QSHORT[qa]}</span></td>"
                f"<td class='why'>{html.escape(sa48.loc[c, 'why'])}</td>"
                f"<td>{sb48.loc[c, 'b_g']:+.2f}</td><td>{sb48.loc[c, 't_g']:+.1f}</td>"
                f"<td>{sb48.loc[c, 'b_i']:+.2f}</td><td>{sb48.loc[c, 't_i']:+.1f}</td>"
                f"<td><span class='q q-{qb}'>{QSHORT[qb]}</span></td>"
                f"<td>{'✓' if qa == qb else '✗'}</td><td>{oos_stab[c]*100:.0f}%</td></tr>")
T_CLASS48 = ("<div class='tbl wide'><table><thead><tr><th>Industry</th><th>(a) quadrant</th><th>(a) rationale</th>"
             "<th>β growth</th><th>t</th><th>β infl.</th><th>t</th><th>(b) quadrant</th><th>agree</th>"
             "<th>OOS = full-sample</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")

QA48 = L[48]["quads"]["a"]; QB48 = L[48]["quads"]["b"]
QLIST = "".join(f"<div class='qcard q-{q}'><h4>{QUAD_LABEL[q]}</h4><p><b>(a)</b> {', '.join(QA48[q])}</p>"
                f"<p><b>(b)</b> {', '.join(QB48[q])}</p></div>" for q in QUADS)

# ================================================================ FACTS for narrative
h = HEAD
fa = dict(
    sh_m=N(h.loc["US equity market", "Sharpe"]), sh_a=N(h.loc["All Weather (a) macro", "Sharpe"]),
    sh_b=N(h.loc["All Weather (b) regr. IS", "Sharpe"]), sh_o=N(h.loc["All Weather (b) regr. OOS", "Sharpe"]),
    sh_ew=N(h.loc["All industries, EW", "Sharpe"]), sh_aerc=N(h.loc["All Weather (a) ERC/ERC", "Sharpe"]),
    cagr_m=P(h.loc["US equity market", "CAGR"]), cagr_a=P(h.loc["All Weather (a) macro", "CAGR"]),
    vol_m=P(h.loc["US equity market", "Vol"]), vol_a=P(h.loc["All Weather (a) macro", "Vol"]),
    dd_m=P(h.loc["US equity market", "MaxDD"], 0), dd_a=P(h.loc["All Weather (a) macro", "MaxDD"], 0),
    dd_aerc=P(h.loc["All Weather (a) ERC/ERC", "MaxDD"], 0),
    beta_a=N(h.loc["All Weather (a) macro", "Beta"]), corr_a=N(st(BASE["a"])["Corr"]),
    alpha_a=P(h.loc["All Weather (a) macro", "Alpha"]), te_a=P(h.loc["All Weather (a) macro", "TE"]),
    dot_a=P(CRISIS.loc["2000–02 dot-com bust", CLS_SHORT["a"]], 0), dot_m=P(CRISIS.loc["2000–02 dot-com bust", "Market"], 0),
    gfc_a=P(CRISIS.loc["2007–09 GFC", CLS_SHORT["a"]], 0), gfc_m=P(CRISIS.loc["2007–09 GFC", "Market"], 0),
    i22_a=P(CRISIS.loc["2022 inflation shock", CLS_SHORT["a"]], 0), i22_m=P(CRISIS.loc["2022 inflation shock", "Market"], 0),
    oil_a=P(CRISIS.loc["1973–74 oil shock", CLS_SHORT["a"]], 0), oil_m=P(CRISIS.loc["1973–74 oil shock", "Market"], 0),
    cov_a=P(CRISIS.loc["2020 Covid crash", CLS_SHORT["a"]], 0), cov_m=P(CRISIS.loc["2020 Covid crash", "Market"], 0),
    agree48=P(AG.loc["same quadrant", "48"], 0), gagree48=P(AG.loc["same growth sign", "48"], 0),
    iagree48=P(AG.loc["same inflation sign", "48"], 0),
    diag_a=" / ".join(f"{REGTAB['a'].loc[q, q]*100:+.1f}%" for q in QUADS),
    diag_o=" / ".join(f"{REGTAB['b_oos'].loc[q, q]*100:+.1f}%" for q in QUADS),
    period=PERIOD,
)
for k, v in fa.items():
    print(f"{k:10s} {v}")
pickle.dump({"FIG": FIG, "tables": dict(T_HEAD=T_HEAD, T_CRISIS=T_CRISIS, T_EPI=T_EPI, T_EPI_M=T_EPI_M, T_AWREG=T_AWREG,
             T_VAR=T_VAR, T_LEV_S=T_LEV_S, T_LEV_D=T_LEV_D, T_AGREE=T_AGREE, T_CLASS48=T_CLASS48, QLIST=QLIST),
             "facts": fa}, open("results/report_parts.pkl", "wb"))
