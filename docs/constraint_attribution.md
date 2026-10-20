# Attributing TE-minimising active weights to linear constraints

Code: `portfolio_attribution/constraint_attribution.py`, `portfolio_attribution/risk.py`.
Example: `python -m examples.run_attribution`. Tests: `pytest tests`.

## 1. Problem

$N$ assets, benchmark $b$, holdings $w$, active weights $a = w - b$, factor-model covariance

$$\Sigma = B F B^\top + D \quad(\text{handled as } UU^\top + \operatorname{diag}(d),\ U = BF^{1/2}).$$

$$\min_w\ a^\top \Sigma a \quad\text{s.t.}\quad g_k(w) = C_k w - h_k \;\le 0 \text{ or } = 0,\qquad k = 1,\dots,K$$

where each group $k$ (budget, long-only, signal targets, max weight, country bands, industry bands)
stacks $m_k$ rows. Without constraints the optimum is $a^* = 0$: **every active weight exists
because some constraint forces it**. That is what makes the attribution well posed.

The objective is $a^\top\Sigma a$ (no ½). TE $=\sqrt{a^\top\Sigma a}$, in whatever units $\Sigma$ is in.
Signs follow cvxpy: every constraint is held as $g = \text{lhs} - \text{rhs}$, so `x >= lo` becomes
$lo - x \le 0$.

## 2. KKT conditions

Lagrangian $\mathcal L = a^\top\Sigma a + \sum_k \mu_k^\top g_k(w)$, with $\mu_k \ge 0$ for inequalities and free for equalities.

| condition | statement |
|---|---|
| stationarity | $2\Sigma a^* + \sum_k C_k^\top \mu_k = 0$ |
| primal feasibility | $g_k(w^*) \le 0$ / $= 0$ |
| dual feasibility | $\mu_k \ge 0$ (inequalities) |
| complementary slackness | $\mu_k^\top g_k(w^*) = 0$ |

The problem is a convex QP with linear constraints, so these are necessary and sufficient, and $\mu$ is
what cvxpy returns in `constraint.dual_value`.

## 3. Exact additive decomposition of the active weights

Solve stationarity for $a^*$:

$$\boxed{a^* = \sum_k a_k,\qquad a_k = -\tfrac12\,\Sigma^{-1} C_k^\top \mu_k}$$

$a_k$ is the active portfolio that constraint $k$'s "force" $C_k^\top\mu_k$ induces, after the risk
model has spread it across correlated names. It is exact and additive: no residual beyond solver
tolerance. $\Sigma^{-1}$ comes from Woodbury in $O(NK^2)$:

$$\Sigma^{-1} = D^{-1} - D^{-1}U\,(I + U^\top D^{-1}U)^{-1}U^\top D^{-1}.$$

The decomposition also works row by row. For example, one column per country band
(`row_weight_contributions`), because $C_k^\top\mu_k = \sum_j c_{kj}\,\mu_{kj}$.

The budget row ($\mathbf 1^\top w = 1$) gets $a_{\text{budget}} = -\tfrac12\nu\,\Sigma^{-1}\mathbf 1$, the
minimum-variance funding leg that makes the other legs sum to zero.

## 4. Multiplier × RHS: the TE decomposition

Multiply stationarity by $a^{*\top}$:

$$a^{*\top}\Sigma a^* = -\tfrac12 \sum_k \mu_k^\top C_k a^* = -\tfrac12\sum_k \mu_k^\top\big(g_k(w^*) - g_k(b)\big).$$

Complementary slackness removes $\mu_k^\top g_k(w^*)$, which leaves

$$\boxed{\mathrm{TE}^2 = \sum_k \tfrac12\,\mu_k^\top g_k(b)},\qquad \mathrm{TE}_k = \frac{\tfrac12\mu_k^\top g_k(b)}{\mathrm{TE}} \;\;(\textstyle\sum_k \mathrm{TE}_k = \mathrm{TE}).$$

* $g_k(b)$ is **the constraint evaluated at the benchmark**: how far the benchmark is from satisfying
  it, i.e. the RHS measured relative to the benchmark. For a signal target $s^\top a = t$ it is $-t$. For
  max weight it is $b_i - w_{\max}$. For a country band it is the benchmark's distance to the band edge.
* This is the "Lagrange multiplier × RHS" decomposition. It is exact, not just first order. With the
  active set fixed, $\mathrm{TE}^2 = r^\top (C_A\Sigma^{-1}C_A^\top)^{-1} r$ with $r = -g_A(b)$,
  which is homogeneous of degree 2 in $r$, so Euler's theorem gives $\mathrm{TE}^2 = \tfrac12 r^\top\nabla_r\mathrm{TE}^2$.
* It equals the Euler / x-σ-ρ risk contribution of the sub-portfolio $a_k$:
  $\tfrac12\mu_k^\top g_k(b) = a_k^\top\Sigma a^*$. So §3 and §4 are the same decomposition, seen in weight space and in risk space.
* **Shadow prices.** By the envelope theorem, shifting $g_k$ by $+\delta$ (tightening a `<=` row)
  changes $\mathrm{TE}^2$ by $\mu_k\delta$, and changes TE by $\mu_k\delta/(2\,\mathrm{TE})$. For a row written `lhs == rhs`
  or `lhs <= rhs`, $\partial\mathrm{TE}^2/\partial\,\text{rhs} = -\mu$. Reported as `dTE2_d_tighten`, `dTE_d_tighten`.

**Primary vs secondary constraints.** If $g_k(b) > 0$, the benchmark violates the constraint. It is a
*primary* driver and gets a positive contribution. If $g_k(b) < 0$ but the constraint still binds, it was
only pushed into play by other constraints (typically long-only, once the signal target makes you
underweight a small name). Its KKT contribution is negative, because its leg $a_k$ offsets part of the
primary legs. Its marginal cost is still non-negative, as the leave-one-out shows. Both views are correct;
they answer different questions.

## 5. Counterfactual on/off attribution

Let $a^*(S)$ be the optimum with constraint groups $S$ switched on, and let $\mathcal F$ be the groups
that are always on (budget, long-only).

* **Leave one out:** $\Delta_k^{\text{LOO}} = a^*(\text{all}) - a^*(\text{all}\setminus k)$, with
  $\Delta\mathrm{TE}_k \ge 0$. Removing a constraint only relaxes the problem, so it never becomes infeasible.
* **Add one in:** $\Delta_k^{\text{AOI}} = a^*(\mathcal F\cup k) - a^*(\mathcal F)$, which shows what the constraint does on its own.
* Neither sums to $a^*$. The gap is reported as `interaction`. A constraint that binds weakly
  ($\mu = 0$ while active) shows zero LOO effect. With LOO = 0 and a nonzero AOI, the constraint is
  redundant given the others.
* If you need an additive *and* global split, take the Shapley value over the $2^{|K\setminus\mathcal F|}$
  subsets. That is affordable for 4–8 groups, and the same `solve(cov, groups)` call does it.

KKT (§3–4) is exact, additive and local to the solution. Counterfactuals are global but not additive.
Report both.

## 6. Risk-model variants: why the weights look the way they do

Re-solve the same constraints under three covariances:

| variant | $\Sigma$ | low-rank form |
|---|---|---|
| `full` | $BFB^\top + D$ | $U = BF^{1/2},\ d = D$ |
| `avg_corr` | $\operatorname{diag}(\sigma)\,[(1-\bar\rho)I + \bar\rho\,\mathbf{11}^\top]\,\operatorname{diag}(\sigma)$ | $U = \sqrt{\bar\rho}\,\sigma,\ d = (1-\bar\rho)\sigma^2$ |
| `avg_corr_vol` | $\bar\sigma^2[(1-\bar\rho)I + \bar\rho\,\mathbf{11}^\top]$ | $U = \sqrt{\bar\rho}\,\bar\sigma\mathbf 1,\ d = (1-\bar\rho)\bar\sigma^2$ |

The objectives are:

* `avg_corr`: $(1-\bar\rho)\sum_i\sigma_i^2a_i^2 + \bar\rho\,(\sigma^\top a)^2$. This penalises name-level
  dispersion scaled by own variance, plus one "vol-weighted net bet" (long high-vol, short low-vol).
* `avg_corr_vol`: $\bar\sigma^2[(1-\bar\rho)\lVert a\rVert^2 + \bar\rho(\mathbf 1^\top a)^2]$. With the budget
  constraint, $\mathbf 1^\top a = 0$, so **the solution is the Euclidean projection of $b$ onto the
  constraint set**, $\min\lVert w-b\rVert_2$. It does not depend on $\bar\rho$ or $\bar\sigma$. It is pure
  constraint geometry: the smallest weight change that satisfies the constraints.

The weight differences then form a waterfall (`report.waterfall`):

$$a^*_{\text{full}} = \underbrace{a^*_{\bar\rho\bar\sigma}}_{\text{constraint geometry}} + \underbrace{(a^*_{\bar\rho} - a^*_{\bar\rho\bar\sigma})}_{\text{vol dispersion}} + \underbrace{(a^*_{\text{full}} - a^*_{\bar\rho})}_{\text{correlation structure}}.$$

* *Vol dispersion:* the optimiser shifts the forced bets toward low-vol names, because a unit of weight costs $\sigma_i^2$.
* *Correlation structure:* it hedges through correlated names, for example by funding an overweight
  with an underweight in the same industry or country, and loads on factors where that is cheap.

The order (vol first, then correlation) is a choice. The reverse path, avg-vol with true correlations,
would split the last two bars differently. The KKT decomposition can be run under each variant
(`report.kkt[variant]`), which tells you how each constraint's leg changes as structure is added.
`report.te` also shows the TE of each variant's portfolio under the full model. That is the cost of
ignoring the structure.

## 7. Computing $\bar\rho$ and $\bar\sigma$: equal vs cap weighted

All averages come from the **model-implied** correlations $\rho_{ij} = \Sigma_{ij}/(\sigma_i\sigma_j)$ of the
same factor model, so the variants differ only in structure and not in data source. For pair weights
$v_iv_j$:

$$\bar\rho_v = \frac{\sum_{i\ne j} v_iv_j\rho_{ij}}{\sum_{i\ne j} v_iv_j} = \frac{(v/\sigma)^\top\Sigma\,(v/\sigma) - \sum_i v_i^2}{(\sum_i v_i)^2 - \sum_i v_i^2}$$

This is $O(NK)$ and never forms $N\times N$.

| `corr_weighting` | $v$ | meaning |
|---|---|---|
| `"equal"` (default) | $\mathbf 1$ | average over all pairs in the optimisation universe |
| `"cap"` | $b$ | benchmark-weighted pairs, dominated by mega-caps |
| `"implied"` | $b\circ\sigma$ | the CBOE-style implied correlation: the $\bar\rho$ for which $b^\top\Sigma_{\bar\rho} b = b^\top\Sigma b$ (benchmark variance preserved) |
| array | custom | e.g. $\lvert a^*\rvert$ to weight the pairs you actually trade |

$\bar\sigma$ is the weighted RMS $\sqrt{\sum v_i\sigma_i^2/\sum v_i}$, which preserves average variance. For
`"implied"`, $\bar\sigma$ is instead set so that the benchmark variance is matched again.

**Recommendation: equal weighted.**

1. $\bar\sigma$, and for budget-constrained problems also $\bar\rho$, have no effect on the
   `avg_corr_vol` weights (§6). They only scale its TE. The choice only matters for $\bar\rho$ in `avg_corr`.
2. There $\bar\rho$ prices the net vol-weighted bet $(\sigma^\top a)^2$ against name dispersion, and that
   trade-off involves *active* positions. Active positions are not cap-weighted: the optimiser spreads
   them across the whole universe, and small names carry as much active weight as large ones. Equal
   weighting over the universe describes the pairs that make up active risk.
3. Cap weighting describes the correlation of the benchmark's mega-caps, which usually share size,
   quality and sector exposures and so are more correlated. That is the right number for benchmark
   *total* risk, but it overstates the systematic penalty in an active-risk problem. Use `"implied"`
   when you want the simplified model to reproduce benchmark variance exactly, for example to compare
   risk levels across variants.
4. Run both. It costs two QPs. If the `avg_corr` weights barely move between `"equal"` and `"cap"`, the
   choice doesn't matter for your conclusions.

Averaging over benchmark constituents only, rather than the whole universe, is a custom `v`
(`v = (b > 0).astype(float)`).

## 8. Practical notes

* **Explicit constraints.** Long-only and bounds must be constraints (`w >= 0`), not
  `Variable(nonneg=True)`. Variable attributes have no dual. The code checks for this.
* **Objective rebuilt.** Only the constraints of your problem are used. The objective is rebuilt as
  $a^\top\Sigma a$ from $(B,F,D)$, so all variants share one scaling. Constraints involving
  other variables (e.g. `y == B.T @ (w - b)`) are dropped as risk-model plumbing.
  `consistency_check()` compares the rebuilt solution to yours.
* **Dual accuracy.** Clarabel is used with tight tolerances. First-order solvers (OSQP, SCS) give
  noisy duals, and that shows up as a `residual` column.
* **Degenerate duals.** If active constraint rows are linearly dependent (e.g. all country upper bands
  bind and sum to the budget row), $\mu$ is not unique. The split *between* those rows depends on the
  solver, but their sum is unique. Group dependent rows together, or read the group total.
