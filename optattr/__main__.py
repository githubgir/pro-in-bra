"""End-to-end demo following the spec §15 reporting hierarchy.

    python -m optattr [--stocks 3] [--peers 10] [--no-shapley] [--out output]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import (Optimizer, PortfolioSpec, attribute, covariance_ladder, factor_shapley,
               prior_holdings, synthetic_universe)


def _section(title: str) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stocks", type=int, default=3, help="stock tables to print (largest |active|)")
    ap.add_argument("--peers", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-shapley", action="store_true")
    ap.add_argument("--out", type=Path, default=None, help="directory for CSV output")
    args = ap.parse_args(argv)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.float_format", lambda v: f"{v: .6f}")

    t0 = time.perf_counter()
    spec = PortfolioSpec()
    u = synthetic_universe(seed=args.seed)
    u = u.with_prior(prior_holdings(u, spec))
    opt = Optimizer(u, spec)
    sol = opt.solve()
    att = attribute(sol, n_peers=args.peers)

    x = sol.x.to_numpy()
    _section("1. Headline")
    print(pd.Series({
        "solver status": sol.solver_status,
        "tracking error": float(np.sqrt(x @ att.Sigma @ x)),
        "active share": 0.5 * np.abs(x).sum(),
        "one-way turnover": 0.5 * float((sol.w - u.w0).abs().sum()),
        "names held": int((sol.w > 1e-6).sum()),
    }).to_string())

    _section("2. Primary attribution: source summary (pressure -> weight)")
    print(att.source_summary().to_string())

    _section("3. Stock attribution tables (own / network split, peer-netted detail)")
    for stock in att.top_stocks(args.stocks):
        print(f"\n{stock}  sector={u.sector[stock]}  country={u.country[stock]}  "
              f"b={u.b[stock]:.4%}  w={sol.w[stock]:.4%}  x={sol.x[stock]:+.4%}")
        print(att.stock_table(stock, peer_detail=True).to_string())

    _section("4. Peer diagnostic (top-k |partial correlation|)")
    for stock in att.top_stocks(args.stocks):
        i = att.ids.get_loc(stock)
        j = att.peers[i]
        pc = -att.Omega[i, j] / np.sqrt(att.Omega[i, i] * np.diag(att.Omega)[j])
        df = pd.DataFrame({"partial corr": pc, "a_ij": att.peer_w[i],
                           "sector": u.sector.iloc[j].to_numpy(), "x_j": sol.x.iloc[j].to_numpy()},
                          index=att.ids[j]).sort_values("a_ij", ascending=False)
        print(f"\n{stock}: Omega_bar = {att.peer_precision[i]:.4f}")
        print(df.head(5).to_string())

    _section("5. Reconciliation")
    rec = att.reconciliation()
    print(rec.to_string(float_format="{:.2e}".format))

    _section("6a. Counterfactual covariance ladder (h_target fixed, constraints re-imposed)")
    ladder = covariance_ladder(opt, reference=sol)
    print(ladder.summary.to_string())
    print(f"telescoping error {ladder.telescoping_error():.2e}; "
          f"top rung vs optimised x {ladder.summary.attrs['final_vs_reference']:.2e}")
    movers = ladder.steps.iloc[:, 1:].abs().sum(axis=1).nlargest(args.stocks).index
    print("largest covariance-driven moves:")
    print(ladder.steps.loc[movers].to_string())

    shap = None
    if not args.no_shapley:
        _section("6b. Factor-by-factor Shapley (style covariance blocks)")
        shap = factor_shapley(opt)
        print(shap.summary().to_string())
        print(f"{shap.n_solves} solves; efficiency error {shap.efficiency_error():.2e}")
        movers = shap.phi.abs().sum(axis=1).nlargest(args.stocks).index
        print(shap.phi.loc[movers].to_string())

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        pd.concat([u.b, sol.w, sol.x, u.w0], axis=1).to_csv(args.out / "weights.csv")
        att.contributions().to_csv(args.out / "weight_contributions.csv")
        att.source_summary().to_csv(args.out / "source_summary.csv")
        rec.to_csv(args.out / "reconciliation.csv")
        ladder.steps.to_csv(args.out / "ladder_steps.csv")
        ladder.summary.to_csv(args.out / "ladder_summary.csv")
        if shap is not None:
            shap.phi.to_csv(args.out / "shapley_phi.csv")
        print(f"\nCSV written to {args.out}/")
    print(f"\nTotal runtime {time.perf_counter() - t0:.1f}s")
    if not rec["pass"].all():
        raise SystemExit("reconciliation FAILED")


if __name__ == "__main__":
    main()
