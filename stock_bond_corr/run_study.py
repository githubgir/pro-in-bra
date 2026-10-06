"""US stock/bond correlation: shock-driven or regime-driven?

Run:  python run_study.py
Writes tables to output/tables, figures to output/figures, key numbers to output/results.json.
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import analytics as an
import plots
import regimes as rg
from data_prep import MONTHLY_RATES_START, SPECS, build_returns, load_raw

warnings.filterwarnings("ignore")
OUT = Path(__file__).parent / "output"
TAB, FIG = OUT / "tables", OUT / "figures"
N = 36
WINDOWS = (6, 12, 24, 36, 60)


def rolling_spearman(x: pd.Series, y: pd.Series, n=N) -> pd.Series:
    X, Y = an.windows(x.values, n), an.windows(y.values, n)
    rx, ry = X.argsort(1).argsort(1).astype(float), Y.argsort(1).argsort(1).astype(float)
    return pd.Series(np.r_[np.full(n - 1, np.nan), an.corr_rows(rx, ry)], index=x.index)


def window_diagnostics(r: pd.DataFrame, xcol: str, ycol: str):
    x, y = r[xcol].values, r[ycol].values
    conc, infl = an.concentration(x, y, N)
    diag = pd.DataFrame(conc, index=r.index)
    diag["max_influence_month"] = [
        str(r.index[t - N + 1 + int(p)]) if np.isfinite(diag.rho.iloc[t]) else None
        for t, p in enumerate(np.nan_to_num(diag.max_influence_pos.values).astype(int))]
    diag["spearman"] = rolling_spearman(r[xcol], r[ycol])
    diag["n_to_flip_sign"] = diag.n_to_flip_sign.replace(np.inf, 99)  # 99 = not flipped by removing 12 months
    return diag, infl


def episode_table(r, rc, diag, ee, ns_corr, thresh=0.30):
    eps = an.zigzag(rc["36m"], thresh)
    rows, top_rows = [], []
    for s, e in eps:
        sl = ee.loc[s:e].iloc[1:]                        # months whose update moves rho from s to e
        d = rc["36m"][e] - rc["36m"][s]
        sgn = np.sign(d)
        # attribute each update's entry/exit term to the calendar month entering / exiting
        att = pd.concat([sl.set_index("entering_month")["entry"],
                         sl.set_index("exiting_month")["exit"]]).groupby(level=0).sum()
        role = {m: "enter" for m in sl.entering_month} | {m: "exit" for m in sl.exiting_month}
        both = set(sl.entering_month) & set(sl.exiting_month)
        aligned = att * sgn
        top = aligned.sort_values(ascending=False).head(3)
        n_eff = aligned.abs().sum() ** 2 / (aligned ** 2).sum()
        comp = sl[["entry", "exit", "mean_shift", "rescaling"]].sum()
        top3_share = top.sum() / abs(d)
        top_roles = [("enter+exit" if m in both else role[m]) for m in top.index]
        exit_top = sum(sgn * sl.set_index("exiting_month")["exit"].reindex(top.index).fillna(0))
        robust = (diag.rho_trim3[e] - diag.rho_trim3[s]) / d
        d60 = rc["60m"][e] - rc["60m"][s] if np.isfinite(rc["60m"][s]) else np.nan
        d12 = rc["12m"][e] - rc["12m"][s]
        months = (e - s).n
        # Classification rules (transparent, applied to every swing):
        #  shock-driven : 3 months deliver >=90% of the net swing, or >=60% while the outlier-trimmed
        #                 correlation moves <50% as much and the 60m window does not confirm the move
        #  persistent   : <60% from the top 3 months AND trimmed correlation moves >=50% as much
        #  mixed        : everything else (typically a shock entering/exiting on top of a real shift)
        broad_horizon = np.isfinite(d60) and np.sign(d60) == sgn and abs(d60) >= 0.15
        if top3_share >= 0.9 or (top3_share >= 0.6 and robust < 0.5 and not broad_horizon):
            cls = "Shock EXIT (window artifact)" if exit_top > 0.5 * top.sum() else "Shock ENTRY"
        elif top3_share < 0.6 and robust >= 0.5:
            cls = "Persistent / broad-based"
        else:
            cls = "Mixed (shock + broad shift)"
        rows.append(dict(
            start=str(s), end=str(e), months=months, rho36_start=rc["36m"][s], rho36_end=rc["36m"][e], d_rho36=d,
            d_rho12=d12, d_rho60=d60, d_rho_trim3=diag.rho_trim3[e] - diag.rho_trim3[s],
            robust_ratio=robust, d_spearman=diag.spearman[e] - diag.spearman[s],
            sum_entry=comp.entry, sum_exit=comp.exit, sum_mean_shift=comp.mean_shift, sum_rescaling=comp.rescaling,
            top3_share=top3_share, n_eff_months=n_eff,
            top3_months="; ".join(f"{m} ({ro}, {v:+.2f})" for (m, v), ro in zip(top.items(), top_roles)),
            S_start=diag.S_demeaned[s], S_end=diag.S_demeaned[e],
            C3_end=diag.C3_abs_share[e], max_LOO_end=diag.max_abs_influence[e], n_flip_end=diag.n_to_flip_sign[e],
            ms_prob_pos_start=ns_corr[s], ms_prob_pos_end=ns_corr[e],
            classification=cls))
    return pd.DataFrame(rows)


def top_influential(r, xcol, ycol, infl, diag, ep, k=5):
    """Top-k leave-one-out influential months in the window at the end of each episode."""
    out = []
    for _, row in ep.iterrows():
        t = r.index.get_loc(pd.Period(row.end, "M"))
        months = r.index[t - N + 1:t + 1]
        c = an.contributions(r[xcol].values, r[ycol].values, N)["c"][t]
        o = np.argsort(-np.abs(infl[t]))[:k]
        for rank, j in enumerate(o, 1):
            out.append(dict(episode_end=row.end, window_rho=diag.rho.iloc[t], rank=rank, month=str(months[j]),
                            stock_ret=r[xcol].iloc[t - N + 1 + j], bond_side=r[ycol].iloc[t - N + 1 + j],
                            c_i=c[j], rho_without=diag.rho.iloc[t] + infl[t, j], influence=infl[t, j]))
    return pd.DataFrame(out)


def shock_lifecycle(ee: pd.DataFrame, top=20):
    """For the months with the largest entry effect, compare entry vs exit effect 36m later."""
    ent = ee.set_index("entering_month")[["shapley_entry", "rho"]]
    ext = ee.set_index("exiting_month")[["shapley_exit"]].rename_axis("entering_month")
    life = ent.join(ext, how="inner").dropna()
    rho = ee.set_index("entering_month").rho
    idx = list(rho.index)
    pos = {m: i for i, m in enumerate(idx)}
    life["rho_before_entry"] = [rho.iloc[pos[m] - 1] if pos[m] > 0 else np.nan for m in life.index]
    life["rho_after_exit"] = [rho.iloc[pos[m] + N] if pos[m] + N < len(rho) else np.nan for m in life.index]
    life["exit_reverses_entry_%"] = -100 * life.shapley_exit / life.shapley_entry
    big = life.reindex(life.shapley_entry.abs().sort_values(ascending=False).index).head(top)
    return life, big


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    full = build_returns()
    r = full.loc[MONTHLY_RATES_START:].copy()
    results = {"sample": f"{r.index[0]} to {r.index[-1]}", "n_months": len(r)}
    r.to_csv(TAB / "monthly_returns.csv")

    # ------------------------------------------------ rolling correlations, both specs (+ real-return robustness)
    rcs = {}
    for name, (xc, yc, desc) in SPECS.items():
        rcs[name] = an.rolling_corr(r[xc], r[yc], WINDOWS)
        rcs[name].to_csv(TAB / f"rolling_corr_{name}.csv")
    rcs["B_real"] = an.rolling_corr(r.stock_real, r.bond_real, WINDOWS)
    rc = rcs["B_bond_return"]
    results["full_sample_corr"] = {k: float(r[SPECS[k][0]].corr(r[SPECS[k][1]])) for k in SPECS}
    results["corr_36m_specB_vs_minus_specA"] = float(rc["36m"].corr(-rcs["A_rate_change"]["36m"]))
    results["horizon_corr_of_levels"] = rc.corr().round(3).to_dict()
    results["horizon_corr_of_12m_changes"] = rc.diff(12).corr().round(3).to_dict()

    # ------------------------------------------------ main window diagnostics for each spec
    outputs = {}
    for name, (xc, yc, desc) in SPECS.items():
        x, y = r[xc].values, r[yc].values
        an.contributions_long(r.index, x, y, N).to_csv(TAB / f"contributions_36m_{name}.csv.gz", index=False)
        diag, infl = window_diagnostics(r, xc, yc)
        diag.to_csv(TAB / f"window_diagnostics_36m_{name}.csv")
        ee = an.entry_exit(r.index, x, y, N)
        ee.to_csv(TAB / f"entry_exit_decomposition_36m_{name}.csv")
        # long-format leave-one-out table
        loo = pd.DataFrame({"window_end": np.repeat(r.index[N - 1:].astype(str), N),
                            "month": [str(r.index[t - N + 1 + j]) for t in range(N - 1, len(r)) for j in range(N)],
                            "rho": np.repeat(diag.rho.values[N - 1:], N),
                            "influence": infl[N - 1:].ravel()})
        loo["rho_without"] = loo.rho + loo.influence
        loo.to_csv(TAB / f"leave_one_out_36m_{name}.csv.gz", index=False)
        outputs[name] = dict(diag=diag, infl=infl, ee=ee)

    B = outputs["B_bond_return"]
    diag, infl, ee = B["diag"], B["infl"], B["ee"]
    xcol, ycol = SPECS["B_bond_return"][:2]

    # ------------------------------------------------ concentration vs. constant-correlation nulls
    nulls = an.null_benchmarks(N)
    nulls.to_csv(TAB / "concentration_null_benchmarks.csv", index=False)
    nn = nulls[(nulls.dist == "normal") & (nulls.true_rho == 0.3)].set_index("stat")
    nt = nulls[(nulls.dist == "t4") & (nulls.true_rho == 0.3)].set_index("stat")
    d = diag.dropna(subset=["rho"])
    results["concentration"] = {
        "median_C1": d.C1_abs_share.median(), "median_C3": d.C3_abs_share.median(), "median_C5": d.C5_abs_share.median(),
        "median_C10": d.C10_abs_share.median(),
        "null_normal_median_C3": nn.loc["C3_abs_share", "p50"], "null_normal_p95_C3": nn.loc["C3_abs_share", "p95"],
        "null_t4_median_C3": nt.loc["C3_abs_share", "p50"], "null_t4_p95_C3": nt.loc["C3_abs_share", "p95"],
        "share_windows_C3_above_normal_p95": float((d.C3_abs_share > nn.loc["C3_abs_share", "p95"]).mean()),
        "share_windows_C3_above_t4_p95": float((d.C3_abs_share > nt.loc["C3_abs_share", "p95"]).mean()),
        "median_max_abs_LOO": d.max_abs_influence.median(), "null_normal_p95_maxLOO": nn.loc["max_abs_influence", "p95"],
        "null_t4_p95_maxLOO": nt.loc["max_abs_influence", "p95"],
        "share_windows_maxLOO_gt_0.15": float((d.max_abs_influence > 0.15).mean()),
        "share_windows_maxLOO_gt_0.25": float((d.max_abs_influence > 0.25).mean()),
        "share_strong_windows_(|rho|>0.4)_flip_with_<=3_removed":
            float((d[d.rho.abs() > 0.4].n_to_flip_sign <= 3).mean()),
        "share_weak_windows_(|rho|<0.2)_flip_with_<=3_removed":
            float((d[d.rho.abs() < 0.2].n_to_flip_sign <= 3).mean()),
        "corr_rho_vs_trim3": float(d.rho.corr(d.rho_trim3)), "corr_rho_vs_spearman": float(d.rho.corr(d.spearman)),
        "std_rho": float(d.rho.std()), "std_trim3": float(d.rho_trim3.std()), "std_spearman": float(d.spearman.std()),
    }
    # concentration by correlation bucket
    d["rho_bucket"] = pd.cut(d.rho, [-1, -0.4, -0.2, 0.2, 0.4, 1])
    bucket = d.groupby("rho_bucket", observed=True)[
        ["C1_abs_share", "C3_abs_share", "C5_abs_share", "max_abs_influence", "n_to_flip_sign", "S_demeaned",
         "mean_abs_c_same", "mean_abs_c_opp", "rho_trim3", "spearman"]].median()
    bucket["n_windows"] = d.groupby("rho_bucket", observed=True).size()
    bucket.to_csv(TAB / "concentration_by_rho_bucket.csv")

    # ------------------------------------------------ sign agreement: frequency vs magnitude
    # rho*(n-1)/n = S*m_same - (1-S)*m_opp  ->  decompose changes over time
    fm = pd.DataFrame({"rho": d.rho, "S": d.S_demeaned, "m_same": d.mean_abs_c_same, "m_opp": d.mean_abs_c_opp,
                       "S_raw": d.S_raw})
    fm["identity_check"] = N / (N - 1) * (fm.S * fm.m_same - (1 - fm.S) * fm.m_opp) - fm.rho
    # frequency-only counterfactual: rho if both groups had the full-sample average magnitude
    mbar = (fm.m_same.mean() + fm.m_opp.mean()) / 2
    fm["rho_freq_only"] = N / (N - 1) * mbar * (2 * fm.S - 1)
    fm.to_csv(TAB / "sign_agreement_36m.csv")
    results["sign_agreement"] = {
        "corr_rho_vs_S": float(fm.rho.corr(fm.S)), "corr_rho_vs_S_raw": float(fm.rho.corr(fm.S_raw)),
        "corr_rho_vs_freq_only": float(fm.rho.corr(fm.rho_freq_only)),
        "R2_rho_on_S": float(fm.rho.corr(fm.S) ** 2),
        "corr_rho_vs_(m_same-m_opp)": float(fm.rho.corr(fm.m_same - fm.m_opp)),
        "max_identity_error": float(fm.identity_check.abs().max()),
    }

    # ------------------------------------------------ entry/exit global attribution
    comp = ee[["entry", "exit", "mean_shift", "rescaling"]]
    cov_share = comp.apply(lambda c: np.cov(c, ee.d_rho)[0, 1] / ee.d_rho.var())
    results["entry_exit"] = {
        "variance_share_of_monthly_d_rho": cov_share.to_dict(),
        "max_residual": float(ee.check_residual.abs().max()),
        "share_big_moves_(|d|>0.08)_entry_dominated":
            float((ee[ee.d_rho.abs() > 0.08].shapley_entry.abs() > ee[ee.d_rho.abs() > 0.08].shapley_exit.abs()).mean()),
        "n_big_moves": int((ee.d_rho.abs() > 0.08).sum()),
    }
    life, big = shock_lifecycle(ee, top=25)
    life.to_csv(TAB / "shock_lifecycle_all_months.csv")
    big.to_csv(TAB / "shock_lifecycle_top25.csv")
    results["entry_exit"]["corr_entry_vs_exit_effect_same_month"] = float(life.shapley_entry.corr(life.shapley_exit))
    results["entry_exit"]["top25_median_exit_reversal_%"] = float(big["exit_reverses_entry_%"].median())
    # how much of the variation of rho36 is the sum of the 'echo' (exit) terms?
    roll = ee[["entry", "exit", "mean_shift", "rescaling"]].rolling(12).sum().assign(d12=ee.rho.diff(12)).dropna()
    results["entry_exit"]["variance_share_of_12m_d_rho"] = {
        c: float(np.cov(roll[c], roll.d12)[0, 1] / roll.d12.var()) for c in ("entry", "exit", "mean_shift", "rescaling")}

    # ------------------------------------------------ regimes / EWMA / DCC
    ew = an.ewma_corr(r[xcol], r[ycol])
    dcc, dinfo = rg.dcc_fit(r[xcol], r[ycol])
    E = dinfo["std_resid"]
    Y = np.column_stack([r[xcol] * 100, r[ycol] * 100])
    model_rows = []
    ms_raw = {K: rg.ms_em(Y, K, n_starts=12) for K in (1, 2, 3)}
    for K, m in ms_raw.items():
        model_rows.append(dict(data="raw returns", model=f"MS-{K} Gaussian (means, vols, corr switch)", K=K, loglik=m["ll"],
                               k_par=m["k_par"], BIC=m["bic"], state_corrs=np.round(m["rho"], 2).tolist(),
                               durations_m=np.round(m["duration_m"], 1).tolist()))
    mcc = rg.ms_common_corr(Y, ms_raw[2])
    model_rows.append(dict(data="raw returns", model="MS-2 Gaussian, vols switch / corr CONSTANT", K=2, loglik=mcc["ll"],
                           k_par=mcc["k_par"], BIC=mcc["bic"], state_corrs=[round(mcc["rho"], 2)], durations_m=None))
    bt = rg.biv_t_constant(Y)
    model_rows.append(dict(data="raw returns", model="1-state bivariate t (constant corr, fat tails)", K=1, loglik=bt["ll"],
                           k_par=bt["k_par"], BIC=bt["bic"], state_corrs=[round(bt["rho"], 2)], durations_m=None))
    tc = rg.t_corr_constant(E)
    model_rows.append(dict(data="GARCH-standardised", model="Constant corr, Student-t shocks", K=1, loglik=tc["ll"],
                           k_par=tc["k_par"], BIC=tc["bic"], state_corrs=[round(tc["rho"], 2)], durations_m=None))
    dll = rg.dcc_gaussian_ll(E, dcc.values)
    model_rows.append(dict(data="GARCH-standardised", model="DCC(1,1) Gaussian (smooth time variation)", K=None, loglik=dll,
                           k_par=3, BIC=-2 * dll + 3 * np.log(len(E)), state_corrs=None, durations_m=None))
    ms_c, ms_t = {}, {}
    for K in (1, 2, 3):
        ms_c[K] = rg.ms_corr_only(E, K, n_starts=12)
        model_rows.append(dict(data="GARCH-standardised", model=f"MS-{K} corr-only, Gaussian", K=K, loglik=ms_c[K]["ll"],
                               k_par=ms_c[K]["k_par"], BIC=ms_c[K]["bic"], state_corrs=np.round(ms_c[K]["rho"], 2).tolist(),
                               durations_m=np.round(ms_c[K]["duration_m"], 1).tolist()))
        if K > 1:
            ms_t[K] = rg.ms_corr_t(E, ms_c[K])
            model_rows.append(dict(data="GARCH-standardised", model=f"MS-{K} corr-only, Student-t shocks", K=K,
                                   loglik=ms_t[K]["ll"], k_par=ms_t[K]["k_par"], BIC=ms_t[K]["bic"],
                                   state_corrs=np.round(ms_t[K]["rho"], 2).tolist(),
                                   durations_m=np.round(ms_t[K]["duration_m"], 1).tolist()))
    models = pd.DataFrame(model_rows)
    models.to_csv(TAB / "regime_model_comparison.csv", index=False)
    results["dcc"] = {k: dinfo[k] for k in ("a", "b", "half_life_m")}
    prob_pos = pd.Series(ms_t[2]["g"][:, 1], index=r.index, name="P(positive-corr regime)")
    regime_df = pd.DataFrame({"rho36": rc["36m"], "DCC": dcc, "P_pos_regime_MS2t": prob_pos}).join(ew)
    regime_df.to_csv(TAB / "regime_and_ewma_series.csv")
    st = (prob_pos > 0.5).astype(int)
    spells = (st.diff() != 0).cumsum()
    spell_tab = st.groupby(spells).agg(["first", "size"]).rename(columns={"first": "state", "size": "months"})
    spell_tab["start"] = [str(st.index[(spells == s).values][0]) for s in spell_tab.index]
    spell_tab["end"] = [str(st.index[(spells == s).values][-1]) for s in spell_tab.index]
    spell_tab["state"] = spell_tab.state.map({1: f"positive (rho={ms_t[2]['rho'][1]:.2f})", 0: f"negative (rho={ms_t[2]['rho'][0]:.2f})"})
    spell_tab.to_csv(TAB / "ms2t_regime_spells.csv", index=False)
    results["regimes"] = {"ms2t_rho": ms_t[2]["rho"].tolist(), "ms2t_nu": ms_t[2]["nu"],
                          "ms2t_durations_m": ms_t[2]["duration_m"].tolist(),
                          "bic_gain_ms2t_vs_const_t": tc["bic"] - ms_t[2]["bic"],
                          "spells": spell_tab.to_dict("records")}

    # ------------------------------------------------ is the rolling-corr variation consistent with a stable relationship?
    nr = rg.null_rolling(r[xcol].values, r[ycol].values, dinfo, N, sims=2000)
    obs = rg.rolling_stats(r[xcol].values, r[ycol].values, N).iloc[0]
    obs_trim = pd.Series({"std": d.rho_trim3.std(), "ac_nonoverlap": d.rho_trim3.corr(d.rho_trim3.shift(-N))})
    nr.to_csv(TAB / "null_rolling_simulations.csv", index=False)
    pvals = {f"{nm}:{c}": float((g[c] >= obs[c]).mean()) for nm, g in nr.groupby("null")
             for c in ("std", "share_abs_gt_04", "ac_nonoverlap")}
    pvals.update({f"{nm}:sign_changes(<=)": float((g.sign_changes <= obs.sign_changes).mean()) for nm, g in nr.groupby("null")})
    results["stability_test"] = {"observed": obs.to_dict(), "observed_trim3": obs_trim.to_dict(),
                                 "null_p95": nr.groupby("null").quantile(0.95).to_dict(), "p_values": pvals}

    # ------------------------------------------------ episodes
    ep = episode_table(r, rc, diag, ee, prob_pos)
    ep.to_csv(TAB / "episodes_36m.csv", index=False)
    ti = top_influential(r, xcol, ycol, infl, diag, ep)
    ti.to_csv(TAB / "episode_top_influential_months.csv", index=False)
    results["episodes_by_class"] = ep.classification.value_counts().to_dict()
    results["episode_abs_swing_by_class"] = ep.assign(a=ep.d_rho36.abs()).groupby("classification").a.sum().to_dict()
    results["latest"] = {"month": str(r.index[-1]), **{k: float(v) for k, v in rc.iloc[-1].items()},
                         "trim3": float(diag.rho_trim3.iloc[-1]), "max_LOO": float(diag.max_abs_influence.iloc[-1]),
                         "max_LOO_month": diag.max_influence_month.iloc[-1], "P_pos_regime": float(prob_pos.iloc[-1])}

    # spec A episodes for comparison
    epA = episode_table(r, -rcs["A_rate_change"], outputs["A_rate_change"]["diag"].assign(
        rho_trim3=-outputs["A_rate_change"]["diag"].rho_trim3, S_demeaned=1 - outputs["A_rate_change"]["diag"].S_demeaned),
        outputs["A_rate_change"]["ee"].assign(**{c: -outputs["A_rate_change"]["ee"][c] for c in
                                                 ("entry", "exit", "mean_shift", "rescaling", "rho", "d_rho")}), prob_pos)
    epA.to_csv(TAB / "episodes_36m_specA_sign_flipped.csv", index=False)

    # ------------------------------------------------ long history appendix (annual data, 1872+)
    raw = load_raw()
    ann = pd.DataFrame({"stock": ((raw.P + raw.D.ffill() / 12) / raw.P.shift(1)).groupby(raw.index.year).prod() - 1,
                        "bond": raw.bond_gross_fwd.shift(1).groupby(raw.index.year).prod() - 1})
    ann = ann.loc[1872:2025]
    ann_rc = pd.DataFrame({"10y window": ann.stock.rolling(10).corr(ann.bond),
                           "20y window": ann.stock.rolling(20).corr(ann.bond)})
    ann_rc.to_csv(TAB / "annual_rolling_corr_1872_2025.csv")

    # ------------------------------------------------ figures
    plots.make_all(r, rcs, outputs, nulls, ee, life, big, fm, ep, ti, regime_df, ms_t[2], nr, obs, ann_rc, FIG, N)

    with open(OUT / "results.json", "w") as f:
        json.dump(results, f, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 80)
    print(json.dumps(results, indent=1, default=str)[:6000])
    print(models.to_string())
    print(ep.drop(columns=["top3_months"]).round(2).to_string())
    print(ep[["start", "end", "classification", "top3_months"]].to_string())
    print(bucket.round(3).to_string())
    print(big.round(3).to_string())


if __name__ == "__main__":
    main()
