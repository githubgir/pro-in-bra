"""Static figures (matplotlib).  Palette: validated reference categorical order,
blue<->gray<->red diverging for signed contributions."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

S1, S2, S3, S4, S5, S6, S7, S8 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
DIV = LinearSegmentedColormap.from_list("div", ["#104281", "#3987e5", "#cde2fb", "#f0efec", "#f7c9c5", "#e34948", "#8f1d1c"])
CLS_COL = {"Persistent / broad-based": S1, "Shock ENTRY": S2, "Shock EXIT (window artifact)": S5, "Mixed (shock + broad shift)": "#b9b8b2"}

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "lines.linewidth": 1.4, "figure.dpi": 130,
})


def _t(idx):
    return idx.to_timestamp() if isinstance(idx, pd.PeriodIndex) else idx


def _zero(ax):
    ax.axhline(0, color=INK2, lw=0.8)


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_rolling(rcs, FIG):
    rc = rcs["B_bond_return"]
    fig, axs = plt.subplots(2, 1, figsize=(11, 7.2), sharex=True)
    cols = {"6m": "#b9b8b2", "12m": S2, "24m": S3, "36m": S1, "60m": S7}
    for k, c in cols.items():
        axs[0].plot(_t(rc.index), rc[k], color=c, lw=2.2 if k == "36m" else (0.7 if k == "6m" else 1.1), label=k)
    axs[0].set_title("Rolling correlation, S&P 500 total return vs 10y Treasury total return (Spec B), all windows")
    axs[0].legend(ncol=5, loc="lower left")
    for k in ("12m", "36m", "60m"):
        axs[1].plot(_t(rc.index), rc[k], color=cols[k], lw=2 if k == "36m" else 1.2, label=k)
    axs[1].set_title("12 / 36 / 60-month only: short-window spikes vs. slow migration across horizons")
    axs[1].legend(ncol=3, loc="lower left")
    for ax in axs:
        _zero(ax); ax.set_ylim(-1, 1); ax.set_ylabel("correlation")
        for y in (-0.4, 0.4):
            ax.axhline(y, color=GRID, lw=1, ls="--")
    _save(fig, FIG / "fig01_rolling_correlations.png")


def fig_specs(rcs, FIG):
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(_t(rcs["B_bond_return"].index), rcs["B_bond_return"]["36m"], color=S1, lw=2, label="Spec B: corr(stocks, bond return)")
    ax.plot(_t(rcs["A_rate_change"].index), -rcs["A_rate_change"]["36m"], color=S2, lw=1.2, label="Spec A: −corr(stocks, Δyield)")
    ax.plot(_t(rcs["B_real"].index), rcs["B_real"]["36m"], color=S3, lw=1, ls="--", label="Spec B in real terms (CPI-deflated)")
    _zero(ax); ax.set_ylim(-1, 1); ax.legend(ncol=3, loc="lower left")
    ax.set_title("36-month correlation under each specification (Spec A sign-flipped so that up = stocks and bonds move together)")
    _save(fig, FIG / "fig02_specifications.png")


def _age_heatmap(ax, c, t, sl, N, lim):
    M = c[sl, ::-1].T
    x0, x1 = mdates.date2num(t[sl][0]), mdates.date2num(t[sl][-1])
    im = ax.imshow(M, aspect="auto", cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim), extent=[x0, x1, N - 0.5, -0.5],
                   interpolation="nearest")
    ax.xaxis_date(); ax.grid(False); ax.set_ylabel("age in window (months)")
    return im


def fig_heatmap(outputs, r, FIG, N, zoom="2005-01", cal_start="2015-01"):
    from analytics import contributions
    from data_prep import SPECS
    xc, yc = SPECS["B_bond_return"][:2]
    c = contributions(r[xc].values, r[yc].values, N)["c"] / (N - 1)
    rho = np.nansum(c, 1); rho[: N - 1] = np.nan
    t = _t(r.index)
    lim = 0.06
    z0 = r.index.get_loc(pd.Period(zoom, "M"))
    sl = slice(z0, None)
    fig, axs = plt.subplots(3, 1, figsize=(11, 10), gridspec_kw={"height_ratios": [1, 2, 2.4]})
    axs[0].plot(t[sl], rho[sl], color=S1, lw=1.6); _zero(axs[0]); axs[0].set_ylim(-1, 1)
    axs[0].set_xlim(t[sl][0], t[-1])
    axs[0].set_title(f"36m correlation since {zoom[:4]} = column sum of the contributions below")
    im = _age_heatmap(axs[1], c, t, sl, N, lim)
    axs[1].set_xlim(t[sl][0], t[-1])
    axs[1].set_title("Contribution c_i/(N−1) by age in window: each shock is a diagonal streak that lives exactly 36 months")
    start = r.index.get_loc(pd.Period(cal_start, "M"))
    T = len(r)
    G = np.full((T - start, T - start), np.nan)
    for w in range(max(start, N - 1), T):
        for j in range(N):
            m = w - N + 1 + j
            if m >= start:
                G[m - start, w - start] = c[w, j]
    tt = t[start:]
    xa, xb = mdates.date2num(tt[0]), mdates.date2num(tt[-1])
    axs[2].imshow(G, aspect="auto", cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim), extent=[xa, xb, xb, xa], interpolation="nearest")
    axs[2].xaxis_date(); axs[2].yaxis_date(); axs[2].grid(False)
    axs[2].set_xlabel("window end"); axs[2].set_ylabel("observation month")
    axs[2].set_title(f"Calendar view since {cal_start[:4]}: each row is one month, coloured in every window that contains it")
    cb = fig.colorbar(im, ax=axs[1:], orientation="vertical", fraction=0.025, pad=0.01)
    cb.set_label("c_i / (N−1)   (red = pushes correlation up, clipped at ±0.06)")
    fig.savefig(FIG / "fig03_contribution_heatmap.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    # full-sample age heatmap
    fig, axs = plt.subplots(2, 1, figsize=(13, 6), gridspec_kw={"height_ratios": [1, 2]}, sharex=True)
    axs[0].plot(t, rho, color=S1, lw=1.4); _zero(axs[0]); axs[0].set_ylim(-1, 1)
    axs[0].set_title("Full sample: 36m correlation and the age-in-window contribution heatmap")
    im = _age_heatmap(axs[1], c, t, slice(N - 1, None), N, lim)
    axs[1].set_xlim(t[0], t[-1])
    fig.colorbar(im, ax=axs, fraction=0.02, pad=0.01)
    fig.savefig(FIG / "fig03b_contribution_heatmap_full.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def fig_distribution(r, FIG, N):
    from analytics import contributions
    from data_prep import SPECS
    xc, yc = SPECS["B_bond_return"][:2]
    c = contributions(r[xc].values, r[yc].values, N)["c"]
    allc = c[N - 1:].ravel()
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6))
    bins = np.linspace(-6, 10, 161)
    axs[0].hist(allc, bins=bins, color=S1, edgecolor=SURF, lw=0.2)
    axs[0].set_yscale("log"); axs[0].set_title("All c_i = z_x z_y (all 36m windows)")
    axs[0].set_xlabel("c_i")
    pos, neg = allc[allc > 0], -allc[allc < 0]
    b2 = np.linspace(0, 8, 81)
    axs[1].hist(pos, bins=b2, color=S8, alpha=0.75, label=f"same-sign (n={len(pos)}, mean {pos.mean():.2f})", edgecolor=SURF, lw=0.2)
    axs[1].hist(neg, bins=b2, color=S1, alpha=0.65, label=f"opposite-sign (n={len(neg)}, mean {neg.mean():.2f})", edgecolor=SURF, lw=0.2)
    axs[1].set_yscale("log"); axs[1].legend(loc="upper right"); axs[1].set_xlabel("|c_i|")
    axs[1].set_title("|c_i| by sign")
    srt = -np.sort(-np.abs(c[N - 1:]), 1)
    share = np.cumsum(srt, 1) / srt.sum(1, keepdims=True)
    ks = np.arange(1, N + 1)
    axs[2].fill_between(ks, np.percentile(share, 5, 0), np.percentile(share, 95, 0), color=S1, alpha=0.2, lw=0, label="5–95% of windows")
    axs[2].plot(ks, np.median(share, 0), color=S1, lw=2, label="median window")
    axs[2].plot(ks, ks / N, color=INK2, lw=1, ls="--", label="perfectly even")
    axs[2].set_xlabel("k largest |c_i|"); axs[2].set_ylabel("share of Σ|c_i|"); axs[2].legend(loc="lower right")
    axs[2].set_title("Concentration curve")
    _save(fig, FIG / "fig04_contribution_distribution.png")


def fig_concentration(diag, nulls, FIG):
    d = diag.dropna(subset=["rho"])
    t = _t(d.index)
    nn = nulls[(nulls.dist == "normal") & (nulls.true_rho == 0.3)].set_index("stat")
    nt = nulls[(nulls.dist == "t4") & (nulls.true_rho == 0.3)].set_index("stat")
    fig, axs = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
    axs[0].plot(t, d.rho, color=S1, lw=1.6, label="36m ρ"); _zero(axs[0]); axs[0].set_ylim(-1, 1)
    axs[0].legend(loc="lower left"); axs[0].set_title("36m correlation")
    for k, col in ((1, S2), (3, S1), (5, S3)):
        axs[1].plot(t, d[f"C{k}_abs_share"], color=col, lw=1.1, label=f"C{k}: top-{k} share of Σ|c|")
    axs[1].axhline(nn.loc["C3_abs_share", "p95"], color=S1, lw=0.9, ls="--", label="C3 95th pct, constant-ρ Normal")
    axs[1].axhline(nt.loc["C3_abs_share", "p95"], color=S1, lw=0.9, ls=":", label="C3 95th pct, constant-ρ t(4)")
    axs[1].legend(ncol=3, loc="upper left"); axs[1].set_ylim(0, 1); axs[1].set_title("Contribution concentration")
    axs[2].plot(t, d.max_abs_influence, color=S2, lw=1.1, label="max |ρ − ρ₋ᵢ| (most influential single month)")
    axs[2].axhline(nn.loc["max_abs_influence", "p95"], color=S2, lw=0.9, ls="--", label="95th pct, Normal null")
    axs[2].axhline(nt.loc["max_abs_influence", "p95"], color=S2, lw=0.9, ls=":", label="95th pct, t(4) null")
    axs[2].legend(loc="upper left", ncol=3); axs[2].set_title("Leave-one-out influence")
    axs[3].plot(t, d.n_to_flip_sign.clip(upper=13), color=S7, lw=1.1, drawstyle="steps-post")
    axs[3].set_yticks([1, 3, 5, 8, 13]); axs[3].set_yticklabels(["1", "3", "5", "8", ">12"])
    axs[3].set_title("Fragility: number of months whose removal flips the sign of ρ (greedy)")
    _save(fig, FIG / "fig05_concentration_influence.png")


def fig_trimmed(diag, FIG):
    d = diag.dropna(subset=["rho"])
    t = _t(d.index)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(t, d.rho, color=S1, lw=2, label="36m Pearson ρ")
    ax.plot(t, d.rho_trim1, color=S2, lw=1, label="drop top-1 |c| month, re-estimate")
    ax.plot(t, d.rho_trim3, color=S3, lw=1, label="drop top-3")
    ax.plot(t, d.rho_trim5, color=S4, lw=1, label="drop top-5")
    ax.plot(t, d.spearman, color=S7, lw=1, ls="--", label="36m Spearman (rank)")
    _zero(ax); ax.set_ylim(-1, 1); ax.legend(ncol=5, loc="lower left")
    ax.set_title("Does the correlation survive removal of its most extreme months?")
    _save(fig, FIG / "fig06_outlier_robust_correlation.png")


def fig_entry_exit(ee, life, big, FIG):
    fig = plt.figure(figsize=(11, 8.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.3, 1])
    ax = fig.add_subplot(gs[0, :])
    a = ee[["entry", "exit", "mean_shift", "rescaling"]].rolling(12).sum().iloc[11::12]
    t = _t(a.index)
    w = 300
    bottom_p = np.zeros(len(a)); bottom_n = np.zeros(len(a))
    for c, col in zip(a.columns, (S2, S5, S4, S3)):
        v = a[c].values
        bp = np.where(v > 0, bottom_p, bottom_n)
        ax.bar(t, v, bottom=bp, width=w, color=col, label=c, edgecolor=SURF, lw=0.5)
        bottom_p += np.clip(v, 0, None); bottom_n += np.clip(v, None, 0)
    ax.plot(_t(ee.index), ee.rho.diff(12), color=INK, lw=1, label="12m change in ρ36")
    _zero(ax); ax.legend(ncol=5, loc="lower left")
    ax.set_title("Exact decomposition of the 12-month change in ρ36: entering months, exiting months, mean shift, vol re-scaling")
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.scatter(life.shapley_entry, life.shapley_exit, s=9, color=S1, alpha=0.5, edgecolor="none")
    lim = np.nanmax(np.abs(life[["shapley_entry", "shapley_exit"]].values)) * 1.05
    ax2.plot([-lim, lim], [lim, -lim], color=INK2, ls="--", lw=0.9, label="exit = −entry (pure window artifact)")
    for m, row in big.head(8).iterrows():
        ax2.annotate(m, (row.shapley_entry, row.shapley_exit), fontsize=7, color=INK2, xytext=(3, 3), textcoords="offset points")
    ax2.set_xlabel("effect on ρ36 when the month ENTERS"); ax2.set_ylabel("effect when it EXITS 36m later")
    ax2.legend(loc="upper right"); ax2.set_title("Shock life-cycle: entry vs exit effect")
    ax3 = fig.add_subplot(gs[1, 1])
    dd = ee.d_rho.abs()
    srt = ee.loc[dd.sort_values(ascending=False).index[:60]]
    ax3.scatter(srt.shapley_entry.abs(), srt.shapley_exit.abs(), s=14, color=S2, edgecolor="none")
    m = max(srt.shapley_entry.abs().max(), srt.shapley_exit.abs().max()) * 1.05
    ax3.plot([0, m], [0, m], color=INK2, ls="--", lw=0.9)
    ax3.set_xlabel("|entry effect|"); ax3.set_ylabel("|exit effect|")
    ax3.set_title("60 largest monthly moves in ρ36: entry- vs exit-driven")
    _save(fig, FIG / "fig07_entry_exit.png")


def fig_sign(fm, FIG):
    t = _t(fm.index)
    fig, axs = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    axs[0].plot(t, fm.rho, color=S1, lw=1.8, label="36m ρ")
    axs[0].plot(t, fm.rho_freq_only, color=S2, lw=1.1, label="frequency-only ρ (sign agreement, average magnitudes)")
    _zero(axs[0]); axs[0].legend(loc="lower left"); axs[0].set_ylim(-1, 1)
    axs[0].set_title("Frequency vs magnitude: how much of ρ is just 'how often they move together'?")
    axs[1].plot(t, fm.S, color=S3, lw=1.2, label="S: share of months with z_x z_y > 0")
    axs[1].plot(t, fm.S_raw, color=S7, lw=1, ls="--", label="S_raw: share with X·Y > 0 (raw returns)")
    axs[1].plot(t, fm.m_same / (fm.m_same + fm.m_opp), color=S4, lw=1, label="magnitude tilt: m_same/(m_same+m_opp)")
    axs[1].axhline(0.5, color=INK2, lw=0.8); axs[1].legend(loc="lower left", ncol=3); axs[1].set_ylim(0.1, 0.95)
    _save(fig, FIG / "fig08_sign_agreement.png")


def fig_episodes(rc, ep, FIG):
    fig, ax = plt.subplots(figsize=(11, 4.8))
    t = _t(rc.index)
    for _, e in ep.iterrows():
        ax.axvspan(pd.Period(e.start, "M").to_timestamp(), pd.Period(e.end, "M").to_timestamp(),
                   color=CLS_COL[e.classification], alpha=0.18, lw=0)
    ax.plot(t, rc["36m"], color=INK, lw=1.6)
    ax.plot(t, rc["60m"], color=S7, lw=1, ls="--", label="60m")
    for _, e in ep.iterrows():
        first = e.top3_months.split(";")[0].strip()
        top = f"{first.split(' (')[0]} {first.split('(')[1].split(',')[0]}"
        te = pd.Period(e.end, "M").to_timestamp()
        ax.annotate(top, (te, e.rho36_end), fontsize=6.5, color=INK2, xytext=(0, 6 if e.d_rho36 > 0 else -11),
                    textcoords="offset points", ha="center")
    from matplotlib.patches import Patch
    handles = [Patch(color=c, alpha=0.35, label=k) for k, c in CLS_COL.items()] + [
        plt.Line2D([], [], color=INK, label="36m ρ"), plt.Line2D([], [], color=S7, ls="--", label="60m ρ")]
    ax.legend(handles=handles, ncol=6, loc="lower left", fontsize=7.5)
    _zero(ax); ax.set_ylim(-1, 1)
    ax.set_title("Major 36m correlation swings (≥0.30) classified; label = month (and whether it entered or exited) contributing most to the swing")
    _save(fig, FIG / "fig09_episodes.png")


def fig_ewma(regime_df, rcs, FIG):
    rc = rcs["B_bond_return"]
    fig, axs = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    t = _t(rc.index)
    for k, c in (("12m", S2), ("24m", S3), ("36m", S1), ("60m", S7)):
        axs[0].plot(t, rc[k], color=c, lw=1.6 if k == "36m" else 1, label=f"rolling {k}")
    axs[0].set_title("Rolling windows"); axs[0].legend(ncol=4, loc="lower left")
    cols = [c for c in regime_df.columns if c.startswith("EWMA")]
    for c, col in zip(cols, (S2, S3, S1, S7)):
        axs[1].plot(t, regime_df[c], color=col, lw=1, label=c)
    axs[1].plot(t, regime_df.DCC, color="#b9b8b2", lw=0.8, label="DCC-GARCH(1,1)")
    axs[1].set_title("EWMA (several decays) and DCC conditional correlation"); axs[1].legend(ncol=3, loc="lower left", fontsize=7.5)
    for ax in axs:
        _zero(ax); ax.set_ylim(-1, 1)
    _save(fig, FIG / "fig10_ewma_dcc.png")


def fig_regimes(regime_df, ms, FIG):
    fig, ax = plt.subplots(figsize=(11, 4))
    t = _t(regime_df.index)
    ax.fill_between(t, 0, regime_df.P_pos_regime_MS2t, color=S8, alpha=0.18, lw=0,
                    label=f"P(positive regime, ρ={ms['rho'][1]:.2f}, mean duration {ms['duration_m'][1] / 12:.0f}y)")
    ax.plot(t, regime_df.rho36, color=S1, lw=1.6, label="36m ρ")
    ax.plot(t, regime_df.DCC, color="#b9b8b2", lw=0.7, label="DCC")
    _zero(ax); ax.set_ylim(-1, 1); ax.legend(loc="lower left", ncol=3)
    ax.set_title(f"2-state Markov-switching correlation (Student-t shocks, ν={ms['nu']:.1f}) on GARCH-standardised returns; "
                 f"negative state ρ={ms['rho'][0]:.2f}")
    _save(fig, FIG / "fig11_regime_switching.png")


def fig_null(nr, obs, FIG):
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.4))
    for ax, c, lab in zip(axs, ("std", "share_abs_gt_04", "ac_nonoverlap"),
                          ("std. dev. of ρ36 over time", "share of time |ρ36| > 0.4", "corr(ρ36 window, next disjoint window)")):
        for nm, col in (("iid_pairs", S2), ("ccc_garch", S3)):
            ax.hist(nr[nr.null == nm][c], bins=40, color=col, alpha=0.6, label=nm, edgecolor=SURF, lw=0.2)
        ax.axvline(obs[c], color=INK, lw=2, label="observed")
        ax.set_title(lab, fontsize=9); ax.legend(fontsize=7)
    fig.suptitle("Could a stable relationship (with fat-tailed shocks and vol clustering) produce the observed rolling ρ?",
                 x=0.01, ha="left", fontsize=10.5, fontweight="bold")
    _save(fig, FIG / "fig12_stability_nulls.png")


def fig_annual(ann_rc, FIG):
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.plot(ann_rc.index, ann_rc["10y window"], color=S2, lw=1, label="10-year window")
    ax.plot(ann_rc.index, ann_rc["20y window"], color=S1, lw=1.8, label="20-year window")
    ax.axvline(1953, color=INK2, ls="--", lw=0.8)
    _zero(ax); ax.set_ylim(-1, 1); ax.legend(loc="lower left")
    ax.set_title("Appendix: long history with ANNUAL returns, 1872–2025 (monthly bond data are interpolated before 1953)")
    _save(fig, FIG / "fig13_annual_long_history.png")


def make_all(r, rcs, outputs, nulls, ee, life, big, fm, ep, ti, regime_df, ms, nr, obs, ann_rc, FIG, N):
    diag = outputs["B_bond_return"]["diag"]
    fig_rolling(rcs, FIG)
    fig_specs(rcs, FIG)
    fig_heatmap(outputs, r, FIG, N)
    fig_distribution(r, FIG, N)
    fig_concentration(diag, nulls, FIG)
    fig_trimmed(diag, FIG)
    fig_entry_exit(ee, life, big, FIG)
    fig_sign(fm, FIG)
    fig_episodes(rcs["B_bond_return"], ep, FIG)
    fig_ewma(regime_df, rcs, FIG)
    fig_regimes(regime_df, ms, FIG)
    fig_null(nr, obs, FIG)
    fig_annual(ann_rc, FIG)
