"""End-to-end example: python -m examples.run_attribution"""

import pandas as pd

from examples.synthetic_problem import build_problem
from portfolio_attribution import ConstraintAttribution

pd.set_option("display.width", 160, "display.float_format", "{:.5f}".format)

p = build_problem()
p["problem"].solve()  # your own solve

attr = ConstraintAttribution(
    p["problem"], p["w"], p["b"], p["B"], p["F"], p["D"],
    groups=p["groups"], fixed=["budget", "long_only"], row_labels=p["row_labels"],
)
print("max |w_yours - w_rebuilt| =", attr.consistency_check())

rep = attr.run(corr_weighting="equal")
print(f"\nrho_bar = {rep.rho_bar:.4f}, vol_bar = {rep.vol_bar:.4f}")
print("\nTE by risk-model variant\n", rep.te)

for v in rep.kkt:
    print(f"\n=== {v}: KKT risk attribution (TE^2 = sum 1/2 mu' g(b)) ===\n", rep.kkt[v].risk)
print("\nBinding rows (full model)\n", rep.kkt["full"].rows.query("active and abs(dual) > 1e-9"))
print("\nKKT active-weight decomposition, top 10 names by |a| (full model)")
w = rep.kkt["full"].weights
print(w.loc[w["total"].abs().sort_values(ascending=False).index[:10]])

print("\nLeave-one-out (full model)\n", rep.leave_one_out["full"].summary)
print("\nAdd-one-in (full model)\n", rep.add_one_in["full"].summary)
print("\nRisk-model waterfall, top 10 names\n",
      rep.waterfall.loc[rep.waterfall["total"].abs().sort_values(ascending=False).index[:10]])
