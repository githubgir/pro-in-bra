"""Figures and tables for the drawdown-anchored classification (c) section."""
import html
import pickle

import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from allweather import analytics as A
from allweather import data as D
from allweather import ddcluster as DC
from allweather import portfolio as P
from allweather.classify import QUADS
from allweather.figures import QSLOT, date_axis, pct, render, ts
from report import P as PF, N as NF, table, STAT_FMT, QSHORT, CLS_SHORT

R = pickle.load(open("results/results.pkl", "rb"))
Q = pickle.load(open("results/results_dd.pkl", "rb"))
F = R["factors"]; RF, MKT = F["RF"], F["Mkt"]
S70, S00, END = "1970-01", "2000-01", "2026-08"
QNUM = {"GD_IU": "Q1", "GU_IU": "Q2", "GD_ID": "Q3", "GU_ID": "Q4"}
QORDER = ["GD_IU", "GU_IU", "GD_ID", "GU_ID"]
QNAME = {q: f"{QNUM[q]} {DC.ANCHOR_LABEL[q]} ({QSHORT[q]})" for q in QORDER}


def st(r, s):
    return A.stats(r.loc[s:END], RF, MKT)


def aw_c(n, cls, wi="ERC", ac="ERC"):
    return Q["levels"][n]["runs"][(cls, wi, ac)]["aw"]


def aw_ab(n, cls, wi="ERC", ac="ERC"):
    return R["levels"][n]["runs"][(cls, wi, ac)]["aw"]


fit48 = Q["levels"][48]["fit"]
x48 = D.industries(48)

# sensitivity: no beta adjustment
fit_nb = DC.fit(x48, Q["assets"], MKT, RF, beta_adjust=False)
nb = P.build(x48, P.static(fit_nb["quads"]), "ERC", "ERC", S70)["aw"]

# low-beta reference: EW of the 10 lowest trailing-60m-beta industries
ex, m = x48.sub(RF, axis=0), MKT - RF
idx = x48.loc[S70:END].index
lb = []
for t in idx:
    p = x48.index.get_loc(t)
    h, mh = ex.iloc[p - 60:p].dropna(axis=1), m.iloc[p - 60:p]
    b = h.apply(lambda c: np.cov(c, mh)[0, 1] / mh.var())
    sel = [c for c in b.nsmallest(10).index if pd.notna(x48.loc[t, c])]
    lb.append(x48.loc[t, sel].mean())
LOWB = pd.Series(lb, index=idx)

# asset All Weather (Bridgewater-style building blocks), unlevered and vol-matched to the market
AAW = Q["asset_aw"]["ERC"]["aw"].loc[S70:END]
AAW_EW = Q["asset_aw"]["EW"]["aw"].loc[S70:END]
k = MKT.loc[S70:END].std() / AAW.std()
AAW_L = RF.reindex(AAW.index) + k * (AAW - RF.reindex(AAW.index))

# ---------------------------------------------------------------- tables
rows = {"US equity market": st(MKT, S70),
        "AW (a) macro · ERC/ERC": st(aw_ab(48, "a"), S70),
        "AW (c) drawdown-anchored · EW/EW": st(aw_c(48, "c", "EW", "EW"), S70),
        "AW (c) drawdown-anchored · ERC/ERC": st(aw_c(48, "c"), S70),
        "AW (c) without beta adjustment · ERC/ERC": st(nb, S70),
        "10 lowest-beta industries, EW": st(LOWB, S70),
        "Asset All Weather · EW, unlevered": st(AAW_EW, S70),
        "Asset All Weather · ERC, unlevered": st(AAW, S70),
        f"Asset All Weather · ERC, levered {k:.1f}× to market vol": st(AAW_L, S70)}
COLS = ["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "Worst 12m", "Beta"]
T_DD_MAIN = table(pd.DataFrame(rows).T[COLS], STAT_FMT, hl=["AW (c) drawdown-anchored · ERC/ERC"])

rows = {"US equity market": st(MKT, S00), "AW (a) macro · ERC/ERC": st(aw_ab(48, "a"), S00),
        "AW (b) regression OOS · ERC/ERC": st(aw_ab(48, "b_oos"), S00),
        "AW (c) drawdown-anchored, full sample · ERC/ERC": st(aw_c(48, "c"), S00),
        "AW (c) drawdown-anchored, OOS · ERC/ERC": st(aw_c(48, "c_oos"), S00),
        "Asset All Weather · ERC, unlevered": st(AAW, S00)}
T_DD_OOS = table(pd.DataFrame(rows).T[COLS], STAT_FMT, hl=["AW (c) drawdown-anchored, OOS · ERC/ERC"])

lev = {}
for n in D.LEVELS:
    lev[str(n)] = {"(a) Sharpe": st(aw_ab(n, "a"), S70)["Sharpe"], "(c) Sharpe": st(aw_c(n, "c"), S70)["Sharpe"],
                   "(a) MaxDD": st(aw_ab(n, "a"), S70)["MaxDD"], "(c) MaxDD": st(aw_c(n, "c"), S70)["MaxDD"],
                   "(c-OOS) Sharpe 2000+": st(aw_c(n, "c_oos"), S00)["Sharpe"],
                   "(c-OOS) MaxDD 2000+": st(aw_c(n, "c_oos"), S00)["MaxDD"]}
LEV = pd.DataFrame(lev)
T_DD_LEV = table(LEV, {c: (lambda v, r=None: v) for c in LEV.columns})
# format rows (Sharpe vs pct)
LEVF = LEV.copy().astype(object)
for r_ in LEVF.index:
    LEVF.loc[r_] = [NF(v) if "Sharpe" in r_ else PF(v) for v in LEV.loc[r_]]
T_DD_LEV = table(LEVF, {})

EPS = fit48["episodes"]
EPS_T = EPS.copy()
EPS_T.index = [f"#{i+1}" for i in range(len(EPS_T))]
EPS_T = pd.DataFrame({"Peak": EPS.peak.dt.strftime("%b %Y").values, "Trough": EPS.trough.dt.strftime("%b %Y").values,
                      "Market drawdown": EPS.depth.values,
                      "Recovery": [r.strftime("%b %Y") if r is not None and not pd.isna(r) else "–" for r in EPS.recovery]},
                     index=EPS_T.index)
T_EPS = table(EPS_T, {"Market drawdown": lambda v: PF(v, 0)})

# quadrant cards for (c) and comparison with (a)
qa = R["levels"][48]["quads"]["a"]
lab_a = {c: q for q in QUADS for c in qa[q]}
QC = "".join(
    f"<div class='qcard q-{q}'><h4>{QNAME[q]}</h4><p>{', '.join(fit48['quads'][q])}</p>"
    f"<p class='small'>{sum(lab_a.get(c) == q for c in fit48['quads'][q])} of {len(fit48['quads'][q])} also in this quadrant under (a)</p></div>"
    for q in QORDER)
agree_ac = np.mean([lab_a.get(c) == fit48["label"][c] for c in fit48["label"].index])

# ---------------------------------------------------------------- figures
FIG = {}
ANAMES = ["Gold", "TIPS", "Commodities", "Treasuries", "Cyclicals"]


def f_epheat(fig_, T):
    ie = fit48["ind_ep"]
    order = []
    for q in QORDER:
        mem = fit48["label"].index[fit48["label"] == q]
        order += list(fit48["corr"].loc[mem, q].sort_values(ascending=False).index)
    M = pd.concat([fit48["ast_ep"].loc[ANAMES], ie.loc[order]])
    lab = [f"{a}  [asset]" for a in ANAMES] + order
    ax = fig_.subplots()
    cm = LinearSegmentedColormap.from_list("div", [T["neg"], T["mid"], T["pos"]])
    ax.imshow(np.clip(M.values, -0.4, 0.4), cmap=cm, vmin=-0.4, vmax=0.4, aspect="auto")
    ax.set_yticks(range(len(lab)), lab, fontsize=6.6)
    ax.set_xticks(range(M.shape[1]), [c.replace("→", "\n→") for c in M.columns], fontsize=6.6)
    ax.xaxis.tick_top(); ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M.values[i, j]
            ax.text(j, i, "·" if np.isnan(v) else f"{v*100:+.0f}", ha="center", va="center", fontsize=5.6, color=T["ink"])
    # group separators and labels
    y = len(ANAMES) - 0.5
    ax.axhline(y, color=T["ink"], lw=1.2)
    for q in QORDER:
        nmem = int((fit48["label"] == q).sum())
        ax.add_patch(__import__("matplotlib").patches.Rectangle((-0.62, y), 0.1, nmem, color=T["s"][QSLOT[q]], clip_on=False))
        ax.text(M.shape[1] - 0.45, y + nmem / 2, f"{QNUM[q]}\n{QSHORT[q]}", fontsize=7.5, va="center", ha="left",
                color=T["ink2"], fontweight="bold")
        y += nmem
        ax.axhline(y, color=T["surface"], lw=2.5)
    ax.set_xlim(-0.65, M.shape[1] + 0.4)
FIG["epheat"] = render(f_epheat, (9, 13))


def f_epbars(fig_, T):
    qr = Q["levels"][48]["runs"][("c", "EW", "EW")]["quads"]
    ax = fig_.subplots()
    xs = np.arange(len(EPS)); w = 0.16
    mk = [(1 + MKT.loc[e.peak + 1:e.trough]).prod() - 1 for _, e in EPS.iterrows()]
    ax.bar(xs - 2 * w, mk, w * 0.9, color=T["ref"], label="Market", zorder=3)
    for j, q in enumerate(QORDER):
        v = [(1 + qr[q].loc[e.peak + 1:e.trough]).prod() - 1 for _, e in EPS.iterrows()]
        ax.bar(xs + (j - 1) * w, v, w * 0.9, color=T["s"][QSLOT[q]], label=f"{QNUM[q]} {QSHORT[q]}", zorder=3)
    ax.axhline(0, color=T["axis"], lw=1)
    ax.set_xticks(xs, [f"{e.peak.strftime('%b %y')}\n–{e.trough.strftime('%b %y')}" for _, e in EPS.iterrows()], fontsize=7.5)
    pct(ax); ax.set_ylabel("total return over the episode")
    ax.legend(ncol=5, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0))
FIG["epbars"] = render(f_epbars, (10, 4.2))


def f_dd2(fig_, T):
    ax = fig_.subplots()
    m = MKT.loc[S70:END]; x = ts(m.index)
    ax.fill_between(x, A.drawdown(m), 0, color=T["ref"], alpha=0.22, lw=0, label="US equity market")
    ax.plot(x, A.drawdown(aw_c(48, "c").loc[S70:END]), color=T["s"][1], lw=1.2, label="AW (c) drawdown-anchored, ERC/ERC")
    ax.plot(x, A.drawdown(LOWB), color=T["s"][3], lw=1.2, label="10 lowest-beta industries")
    ax.plot(x, A.drawdown(AAW_L), color=T["s"][2], lw=1.5, label=f"Asset All Weather, levered to market vol")
    pct(ax); ax.set_ylabel("drawdown from peak"); date_axis(ax, 5)
    ax.legend(loc="lower left", fontsize=8, ncol=2)
FIG["dd2"] = render(f_dd2, (9, 4.0))

# ---------------------------------------------------------------- facts
s_c, s_a, s_m = st(aw_c(48, "c"), S70), st(aw_ab(48, "a"), S70), st(MKT, S70)
gfc = {q: (1 + Q["levels"][48]["runs"][("c", "EW", "EW")]["quads"][q].loc["2007-11":"2009-02"]).prod() - 1 for q in QORDER}
gx = (1 + x48.loc["2007-11":"2009-02"]).prod() - 1
facts = dict(
    dd_c=PF(s_c["MaxDD"], 0), dd_a=PF(s_a["MaxDD"], 0), dd_m=PF(s_m["MaxDD"], 0),
    sh_c=NF(s_c["Sharpe"]), sh_a=NF(s_a["Sharpe"]), sh_m=NF(s_m["Sharpe"]),
    dd_nb=PF(st(nb, S70)["MaxDD"], 0), dd_lb=PF(st(LOWB, S70)["MaxDD"], 0), sh_lb=NF(st(LOWB, S70)["Sharpe"]),
    beta_lb=NF(st(LOWB, S70)["Beta"]),
    dd_aaw=PF(st(AAW, S70)["MaxDD"], 0), sh_aaw=NF(st(AAW, S70)["Sharpe"]), vol_aaw=PF(st(AAW, S70)["Vol"], 1),
    dd_aawl=PF(st(AAW_L, S70)["MaxDD"], 0), sh_aawl=NF(st(AAW_L, S70)["Sharpe"]), lev=f"{k:.1f}",
    cagr_aawl=PF(st(AAW_L, S70)["CAGR"]), cagr_m=PF(s_m["CAGR"]),
    gfc_best_q=PF(max(gfc.values()), 0), gfc_worst_q=PF(min(gfc.values()), 0),
    gfc_med_ind=PF(gx.median(), 0), gfc_best_ind=f"{gx.idxmax()} {PF(gx.max(), 0)}",
    agree_ac=PF(agree_ac, 0),
    sh_coos=NF(st(aw_c(48, "c_oos"), S00)["Sharpe"]), dd_coos=PF(st(aw_c(48, "c_oos"), S00)["MaxDD"], 0),
    sh_aoo=NF(st(aw_ab(48, "a"), S00)["Sharpe"]), sh_m00=NF(st(MKT, S00)["Sharpe"]),
    n_q=" / ".join(str(len(fit48["quads"][q])) for q in QORDER),
)
for kk, v in facts.items():
    print(f"{kk:12s} {v}")
pickle.dump({"FIG": FIG, "T": dict(T_DD_MAIN=T_DD_MAIN, T_DD_OOS=T_DD_OOS, T_DD_LEV=T_DD_LEV, T_EPS=T_EPS, QC=QC),
             "facts": facts}, open("results/report_dd_parts.pkl", "wb"))
