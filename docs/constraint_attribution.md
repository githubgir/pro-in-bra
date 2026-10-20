# Constraint attribution for tracking-error-minimising portfolios

**Contents**

1. [Purpose and scope](#1-purpose-and-scope)
2. [Design decisions taken](#2-design-decisions-taken)
3. [Notation and problem](#3-notation-and-problem)
4. [KKT conditions](#4-kkt-conditions)
5. [Attribution I: active weights from the KKT conditions](#5-attribution-i-active-weights-from-the-kkt-conditions)
6. [Attribution II: multiplier × RHS decomposition of TE](#6-attribution-ii-multiplier--rhs-decomposition-of-te)
7. [Attribution III: counterfactual on/off re-solves](#7-attribution-iii-counterfactual-onoff-re-solves)
8. [Attribution IV: risk-model variants and the weight waterfall](#8-attribution-iv-risk-model-variants-and-the-weight-waterfall)
9. [Average correlation and average vol: options and recommendation](#9-average-correlation-and-average-vol-options-and-recommendation)
10. [Worked example](#10-worked-example)
11. [Implementation](#11-implementation)
12. [Practical notes, pitfalls and extensions](#12-practical-notes-pitfalls-and-extensions)

---

## 1. Purpose and scope

A long-only portfolio is built by minimising ex-ante tracking error (TE) against a benchmark,
subject only to **linear constraints**:

* signal targets (active exposure to one or more alpha signals),
* maximum (and minimum) weights,
* country bands and industry bands on active weights,
* budget and long-only.

If there were no constraints, the optimal portfolio would be the benchmark. Every active weight
therefore exists because at least one constraint forces it. The goal is to say **which constraint is
responsible for which part of the active weights and of the TE**. Four complementary views are used:

| view | question it answers | additive? | cost |
|---|---|---|---|
| KKT weight decomposition (§5) | which part of each active weight does constraint *k* "push"? | exact | one solve |
| Multiplier × RHS (§6) | how much of TE² is due to constraint *k*, and how much would TE change if *k* were relaxed by one unit? | exact | one solve |
| Counterfactual on/off (§7) | what happens if constraint *k* is removed, or applied alone? | no (interaction term) | *K* re-solves |
| Risk-model variants (§8) | how much of the weight pattern comes from constraint geometry, vol dispersion and correlation structure? | exact (waterfall) | 3 solves |

Each view can be repeated under each of the three risk models in §8.

## 2. Design decisions taken

| decision | options considered | chosen | reason |
|---|---|---|---|
| Risk model representation | full $N\times N$ $\Sigma$; factor model $BFB^\top + D$; both | **factor model** | This is what the production problem uses. All three covariance variants are written in one "low rank + diagonal" form, so nothing $N\times N$ is ever built. |
| Interface | pass the data matrices and let the library build the problem; pass the solved `cvxpy.Problem` | **pass the `cvxpy.Problem`** (+ `w`, `b`, `B`, `F`, `D`) | Requested by the user. The constraints are taken from the problem as they are. The objective is rebuilt from $(B,F,D)$ so that all variants share one known scaling. |
| Constraint grouping | one group per cvxpy constraint; user-named groups | **both**: default `c0, c1, …`, optional `groups={name: constraint or list}` | Named groups give readable reports. Row labels (e.g. `"US hi"`) are optional. |
| Dual sign convention | own convention; cvxpy's | **cvxpy's**: $g = \text{lhs}-\text{rhs}$, Lagrangian $f + \mu^\top g$ | Checked numerically. The constraint's Jacobian comes from `constraint.expr.grad`. |
| Objective scaling | $\tfrac12 a^\top\Sigma a$; $a^\top\Sigma a$; TE | $a^\top\Sigma a$ | TE² is the objective value with no extra factors. All formulas below carry the factor ½ explicitly. |
| Always-on constraints in counterfactuals | none; user-chosen | **user-chosen `fixed`** (typically budget and long-only) | Removing the budget constraint does not give a meaningful counterfactual. |
| Counterfactual flavours | leave-one-out; add-one-in; Shapley | **leave-one-out and add-one-in** (Shapley described in §7.3) | Shapley needs $2^{K}$ solves, so it is left as an optional extension. |
| Average corr / vol weighting | equal; cap; implied (variance-preserving); custom | **all four available; default equal** | See §9. |
| Solver | whatever the user problem uses; Clarabel | **Clarabel with tight tolerances** (overridable) | The attribution needs accurate duals. Interior-point solvers give them; first-order solvers do not. |

## 3. Notation and problem

| symbol | meaning |
|---|---|
| $N$ | number of assets |
| $w\in\mathbb R^N$ | portfolio weights (cvxpy variable) |
| $b\in\mathbb R^N$ | benchmark weights, $\mathbf 1^\top b = 1$ |
| $a = w - b$ | active weights |
| $B\in\mathbb R^{N\times F}$, $F$, $D$ | factor exposures, factor covariance, specific variances |
| $\Sigma = BFB^\top + \operatorname{diag}(D)$ | asset covariance |
| $\sigma_i = \sqrt{\Sigma_{ii}}$ | asset total vol |
| $k = 1,\dots,K$ | constraint groups; group $k$ has $m_k$ rows |
| $g_k(w) = C_k w - h_k$ | constraint function of group $k$ ($C_k\in\mathbb R^{m_k\times N}$) |
| $\mu_k\in\mathbb R^{m_k}$ | Lagrange multipliers (duals) of group $k$ |

**Low-rank + diagonal form.** Every covariance used here is written as

$$\Sigma = UU^\top + \operatorname{diag}(d),\qquad d>0 .$$

For the factor model $U = BF^{1/2}$ with $F^{1/2} = Q\Lambda^{1/2}$ from $F = Q\Lambda Q^\top$, and $d = D$.

**Problem.**

$$
\min_{w}\; a^\top\Sigma a
\quad\text{s.t.}\quad
g_k(w) \le 0 \;\;(k\in\mathcal I),\qquad g_k(w) = 0 \;\;(k\in\mathcal E).
$$

Typical constraint groups in cvxpy form ($g = \text{lhs}-\text{rhs}$):

| group | cvxpy | $g(w)$ | $g(b)$ |
|---|---|---|---|
| budget | `sum(w) == 1` | $\mathbf 1^\top w - 1$ | $0$ |
| long-only | `w >= 0` | $-w$ | $-b$ |
| signal target | `s @ (w-b) == t` | $s^\top(w-b) - t$ | $-t$ |
| max weight | `w <= w_max` | $w - w_{\max}$ | $b - w_{\max}$ |
| country upper band | `X_c.T @ (w-b) <= u` | $X_c^\top(w-b) - u$ | $-u$ |
| country lower band | `X_c.T @ (w-b) >= -l` | $-l - X_c^\top(w-b)$ | $-l$ |

> In cvxpy, `x >= y` is stored as `y - x <= 0`, so every inequality is a `<= 0` constraint.

TE is $\sqrt{a^\top\Sigma a}$, in the units of $\Sigma$: if $\Sigma$ is annualised, TE is annualised.

## 4. KKT conditions

Lagrangian:

$$
\mathcal L(w,\mu) = (w-b)^\top\Sigma(w-b) + \sum_k \mu_k^\top g_k(w).
$$

The problem is a convex QP with linear constraints. Linear constraints satisfy a constraint
qualification automatically, so the KKT conditions below are necessary and sufficient. The duals
reported by the solver are the $\mu_k$.

| | condition |
|---|---|
| stationarity | $\nabla_w\mathcal L = 2\Sigma a^* + \sum_k C_k^\top\mu_k = 0$ |
| primal feasibility | $g_k(w^*)\le 0\ (k\in\mathcal I)$, $g_k(w^*) = 0\ (k\in\mathcal E)$ |
| dual feasibility | $\mu_k\ge 0\ (k\in\mathcal I)$, $\mu_k$ free $(k\in\mathcal E)$ |
| complementary slackness | $\mu_{kj}\,g_{kj}(w^*) = 0$ for every row $j$ |

Note that $\nabla_w g_k = C_k^\top$ and that $C_k a = g_k(w) - g_k(b)$, because $g_k$ is affine.

## 5. Attribution I: active weights from the KKT conditions

### 5.1 Derivation

$\Sigma$ is positive definite ($d>0$), so stationarity can be solved for $a^*$:

$$
2\Sigma a^* = -\sum_k C_k^\top\mu_k
\quad\Longrightarrow\quad
\boxed{\,a^* = \sum_{k=1}^K a_k,\qquad a_k := -\tfrac12\,\Sigma^{-1}C_k^\top\mu_k\,}
$$

### 5.2 Interpretation

* $C_k^\top\mu_k$ is the "force" that constraint $k$ exerts on the portfolio. It is the gradient of the
  constraint, scaled by its price. $\Sigma^{-1}$ turns that force into the cheapest way of moving
  the weights under the risk model.
* The decomposition is **exact and additive**. The only residual is solver tolerance, reported as the
  `residual` column.
* Inactive inequality rows have $\mu = 0$ and therefore contribute nothing.

### 5.3 Row-level decomposition

$C_k^\top\mu_k = \sum_j c_{kj}\mu_{kj}$, where $c_{kj}^\top$ is row $j$ of $C_k$. So

$$
a_k = \sum_j a_{kj},\qquad a_{kj} = -\tfrac12\Sigma^{-1}c_{kj}\mu_{kj}.
$$

This gives, for example, one column per country band or per signal (`row_weight_contributions`).

### 5.4 Special legs

* **Budget:** $a_{\text{budget}} = -\tfrac12\nu\,\Sigma^{-1}\mathbf 1$. This is the minimum-variance
  "funding leg" that makes the other legs net to zero.
* **Signal target:** $a_{\text{signal}} = -\tfrac12\nu\,\Sigma^{-1}s$. This is the minimum-TE mimicking
  portfolio of the signal, scaled by its price.
* **Max weight / long-only:** $\Sigma^{-1}e_i$ is the minimum-variance hedge of a single position. The
  leg is a position in asset $i$ together with its hedge across correlated names.

### 5.5 Computing $\Sigma^{-1}$ (Woodbury)

$$
\Sigma^{-1}X = D^{-1}X - D^{-1}U\,(I_r + U^\top D^{-1}U)^{-1}U^\top D^{-1}X .
$$

The cost is $O(Nr^2)$ for rank $r$. The $N\times N$ matrix is never formed.

## 6. Attribution II: multiplier × RHS decomposition of TE

### 6.1 Derivation via complementary slackness

Multiply stationarity on the left by $a^{*\top}$:

$$
2\,a^{*\top}\Sigma a^* = -\sum_k \mu_k^\top C_k a^*
= -\sum_k \mu_k^\top\big(g_k(w^*) - g_k(b)\big).
$$

By complementary slackness (and $g_k(w^*) = 0$ for equalities), $\mu_k^\top g_k(w^*) = 0$. Hence

$$
\boxed{\;\mathrm{TE}^2 = a^{*\top}\Sigma a^* = \sum_k \tfrac12\,\mu_k^\top g_k(b)\;}
\qquad
\mathrm{TE}_k = \frac{\tfrac12\mu_k^\top g_k(b)}{\mathrm{TE}},\quad \sum_k\mathrm{TE}_k = \mathrm{TE}.
$$

$g_k(b)$ is **the constraint evaluated at the benchmark**: the right-hand side measured relative to
the benchmark. This is the "Lagrange multiplier × RHS" attribution. It holds row by row as well:
$\tfrac12\mu_{kj}g_{kj}(b)$.

### 6.2 Derivation via homogeneity (why it is exact, not first order)

Fix the active set $A$ (all equality rows plus the binding inequality rows) and let
$r = -g_A(b)$, so that the binding constraints read $C_A a = r$. Minimising $a^\top\Sigma a$ subject to
$C_A a = r$ gives

$$
a^* = \Sigma^{-1}C_A^\top(C_A\Sigma^{-1}C_A^\top)^{-1}r,\qquad
\mu_A = -2\,(C_A\Sigma^{-1}C_A^\top)^{-1}r,\qquad
\mathrm{TE}^2 = r^\top(C_A\Sigma^{-1}C_A^\top)^{-1}r .
$$

$\mathrm{TE}^2$ is a homogeneous function of degree 2 in $r$. Euler's theorem therefore gives

$$
\mathrm{TE}^2 = \tfrac12\,r^\top\nabla_r\mathrm{TE}^2 = \tfrac12\,r^\top\big(2(C_A\Sigma^{-1}C_A^\top)^{-1}r\big) = -\tfrac12\mu_A^\top r = \tfrac12\mu_A^\top g_A(b),
$$

which is the same result. The decomposition is the Euler allocation of TE² over the constraint
right-hand sides, with each RHS measured from the benchmark.

### 6.3 Link to the weight decomposition

$$
a_k^\top\Sigma a^* = -\tfrac12\mu_k^\top C_k\Sigma^{-1}\Sigma a^* = -\tfrac12\mu_k^\top C_k a^* = \tfrac12\mu_k^\top g_k(b).
$$

The TE contribution of constraint $k$ is exactly the **x-σ-ρ (Euler) risk contribution of its weight
leg** $a_k$ to the total active portfolio. §5 and §6 are one decomposition, seen in weight space and in
risk space.

### 6.4 Shadow prices (sensitivity to the RHS)

By the envelope theorem, perturbing row $j$ to $g_{kj}(w) + \delta \le 0$ (tightening it by $\delta$) gives

$$
\frac{\partial\,\mathrm{TE}^2}{\partial\delta} = \mu_{kj},\qquad
\frac{\partial\,\mathrm{TE}}{\partial\delta} = \frac{\mu_{kj}}{2\,\mathrm{TE}} .
$$

For rows written `lhs <= rhs` or `lhs == rhs`, $\partial\mathrm{TE}^2/\partial\,\text{rhs} = -\mu$.
For example, raising a signal target $t$ by $\Delta t$ changes TE² by $-\nu\,\Delta t$. Because
TE² is quadratic in $r$, these derivatives are only exact locally. For large changes, re-solve (§7).

### 6.5 Primary vs secondary constraints

| case | $g_k(b)$ | $\mu_k$ | KKT TE contribution | reading |
|---|---|---|---|---|
| primary | $>0$, or an equality with $t\ne 0$ | binding | positive | The benchmark itself violates the constraint, so it drives active risk. |
| secondary | $<0$ | binding, $\mu>0$ | **negative** | It binds only because other constraints pushed the portfolio into it (typically long-only, once the signal target makes you underweight a small name). Its leg offsets part of the primary legs. |
| inactive | any | $0$ | 0 | |

A negative KKT contribution does **not** mean the constraint lowers TE. Adding a constraint can never
lower the optimal TE. The negative number is an allocation: the constraint's leg is anti-correlated
with the total. Its standalone marginal cost is non-negative and is shown by leave-one-out (§7).

## 7. Attribution III: counterfactual on/off re-solves

Let $a^*(S)$ be the optimum when only the constraint groups in $S$ are switched on. Let $\mathcal F$ be the
groups that are always on (`fixed`, e.g. budget and long-only), and $\mathcal M$ the switchable groups.

### 7.1 Leave-one-out (LOO)

$$
\Delta_k^{\text{LOO}} = a^*(\mathcal F\cup\mathcal M) - a^*(\mathcal F\cup\mathcal M\setminus\{k\}),\qquad
\Delta\mathrm{TE}_k^{\text{LOO}} = \mathrm{TE}(\text{all}) - \mathrm{TE}(\text{all}\setminus k)\ \ge 0 .
$$

Removing a constraint only enlarges the feasible set, so the re-solve is always feasible and TE can
only fall. LOO measures the **marginal** cost of each constraint, given all the others.

### 7.2 Add-one-in (AOI)

$$
\Delta_k^{\text{AOI}} = a^*(\mathcal F\cup\{k\}) - a^*(\mathcal F) .
$$

This is what the constraint does **on its own**. $a^*(\mathcal F)$ is usually $0$, because the benchmark
satisfies budget and long-only.

### 7.3 Interaction and Shapley

Neither LOO nor AOI sums to $a^*$. The LOO gap is reported as

$$
\text{interaction} = a^* - \sum_{k\in\mathcal M}\Delta_k^{\text{LOO}} .
$$

If you need an allocation that is both global and additive, the Shapley value averages the marginal
contribution over all orderings:

$$
\phi_k = \sum_{S\subseteq\mathcal M\setminus\{k\}} \frac{|S|!\,(|\mathcal M|-|S|-1)!}{|\mathcal M|!}\Big[a^*(\mathcal F\cup S\cup\{k\}) - a^*(\mathcal F\cup S)\Big],
\qquad \sum_k\phi_k = a^*(\text{all}) - a^*(\mathcal F).
$$

This costs $2^{|\mathcal M|}$ solves, which is fine for 4–8 groups. `solve(cov, groups)` is the building
block. It is not implemented as a method yet.

### 7.4 How the views relate

* KKT (§5–6) is exact, additive and **local**: it explains the solution at the current active set.
* LOO and AOI are **global** but not additive.
* Reading the two together:
  * LOO ≈ 0 and AOI ≠ 0: the constraint is redundant given the others.
  * Large AOI, small LOO: other constraints largely do the same job.
  * Binding with $\mu = 0$ (degenerate binding): the constraint shows no KKT contribution and no LOO effect.

## 8. Attribution IV: risk-model variants and the weight waterfall

### 8.1 The three covariances

All three are in low-rank + diagonal form, so the same code solves and attributes under each:

| variant | $\Sigma$ | $U$ | $d$ |
|---|---|---|---|
| `full` | $BFB^\top + D$ | $BF^{1/2}$ | $D$ |
| `avg_corr` (actual vols, constant correlation $\bar\rho$) | $\operatorname{diag}(\sigma)\big[(1-\bar\rho)I + \bar\rho\mathbf{11}^\top\big]\operatorname{diag}(\sigma)$ | $\sqrt{\bar\rho}\,\sigma$ | $(1-\bar\rho)\sigma^2$ |
| `avg_corr_vol` (constant vol $\bar\sigma$, constant correlation $\bar\rho$) | $\bar\sigma^2\big[(1-\bar\rho)I + \bar\rho\mathbf{11}^\top\big]$ | $\sqrt{\bar\rho}\,\bar\sigma\mathbf 1$ | $(1-\bar\rho)\bar\sigma^2\mathbf 1$ |

$\bar\rho$ is clipped to $[0,1)$. The vols $\sigma_i$ in `avg_corr` are the full model's total vols, so
the first two variants differ **only** in their correlations.

### 8.2 What each objective penalises

**avg_corr:**

$$
a^\top\Sigma_{\bar\rho}a = (1-\bar\rho)\sum_i\sigma_i^2a_i^2 + \bar\rho\,(\sigma^\top a)^2 .
$$

The first term penalises name-level dispersion, weighted by each name's own variance. The second
term penalises a single "vol-weighted net bet" (long high-vol names against short low-vol names). The
average correlation $\bar\rho$ sets the trade-off between the two.

**avg_corr_vol:**

$$
a^\top\Sigma_{\bar\rho\bar\sigma}a = \bar\sigma^2\big[(1-\bar\rho)\lVert a\rVert_2^2 + \bar\rho\,(\mathbf 1^\top a)^2\big].
$$

### 8.3 Proposition: avg_corr_vol is the Euclidean projection

If the budget constraint $\mathbf 1^\top w = 1$ is present and $\mathbf 1^\top b = 1$, then every feasible
point has $\mathbf 1^\top a = 0$. The objective becomes $\bar\sigma^2(1-\bar\rho)\lVert a\rVert^2$, a
positive multiple of $\lVert a\rVert^2$. Hence

$$
a^*_{\bar\rho\bar\sigma} = \arg\min_{w\ \text{feasible}}\lVert w - b\rVert_2 ,
$$

which is the Euclidean projection of the benchmark onto the constraint set, **independent of $\bar\rho$
and $\bar\sigma$** (for $\bar\rho<1$). It is pure constraint geometry: the smallest set of trades that
satisfies the constraints. In this variant the KKT legs are simply $a_k = -C_k^\top\mu_k/\big(2\bar\sigma^2(1-\bar\rho)\big)$,
i.e. the constraint normals themselves. (The test suite checks the proposition.) Without a budget
constraint, the $(\mathbf 1^\top a)^2$ term survives and $\bar\rho$ matters.

### 8.4 Waterfall

$$
a^*_{\text{full}}
= \underbrace{a^*_{\bar\rho\bar\sigma}}_{\text{constraint geometry}}
+ \underbrace{\big(a^*_{\bar\rho} - a^*_{\bar\rho\bar\sigma}\big)}_{\text{vol dispersion}}
+ \underbrace{\big(a^*_{\text{full}} - a^*_{\bar\rho}\big)}_{\text{correlation structure}} .
$$

* **Vol dispersion.** One unit of weight in asset $i$ costs $\sigma_i^2$, so the forced bets move
  toward low-vol names.
* **Correlation structure.** The optimiser hedges through correlated names, for example by funding an
  overweight with underweights in the same country, industry or style. It also lets bets ride on
  factors where that is cheap.

The waterfall is exact by construction (it telescopes).

**Path dependence.** The order "vol first, then correlation" is a choice. The alternative path goes
through "average vol, true correlation", with $\Sigma = \bar\sigma^2 R$ where $R$ is the full correlation
matrix. It splits the last two bars differently. If the two paths disagree a lot, the vol and correlation
effects interact strongly. Averaging the two paths gives a two-player Shapley split.

### 8.5 Additional outputs per variant

* `report.kkt[variant]`: the KKT decomposition under each risk model. It shows how each constraint's
  leg changes as structure is added.
* `report.te`: the TE of each variant's portfolio under its own model and under the full model. The
  full-model TE of a simplified portfolio is the cost of ignoring structure. By optimality it is never
  below the full portfolio's TE.

## 9. Average correlation and average vol: options and recommendation

### 9.1 Weighted average correlation without forming $N\times N$

Use the **model-implied** correlations of the same factor model,
$\rho_{ij} = \Sigma_{ij}/(\sigma_i\sigma_j)$, so the variants differ only in structure and not in data
source. For non-negative pair weights $v_iv_j$:

$$
\bar\rho_v = \frac{\sum_{i\ne j}v_iv_j\rho_{ij}}{\sum_{i\ne j}v_iv_j}.
$$

Since $\sum_{i,j}v_iv_j\rho_{ij} = (v/\sigma)^\top\Sigma(v/\sigma)$ and the diagonal terms contribute $\sum_i v_i^2$:

$$
\boxed{\;\bar\rho_v = \frac{(v/\sigma)^\top\Sigma\,(v/\sigma) - \sum_i v_i^2}{\big(\sum_i v_i\big)^2 - \sum_i v_i^2}\;}
$$

with $(v/\sigma)^\top\Sigma(v/\sigma) = \lVert U^\top(v/\sigma)\rVert^2 + \sum_i d_i v_i^2/\sigma_i^2$. This is $O(Nr)$.

### 9.2 Options

| `corr_weighting` | pair weights $v$ | $\bar\rho$ | $\bar\sigma$ |
|---|---|---|---|
| `"equal"` (default) | $\mathbf 1$ | average over all pairs in the universe | $\sqrt{\tfrac1N\sum\sigma_i^2}$ |
| `"cap"` | $b$ | benchmark-weighted pairs (dominated by mega-caps) | $\sqrt{\sum b_i\sigma_i^2}$ |
| `"implied"` | $b\circ\sigma$ | CBOE-style implied correlation; preserves benchmark variance | preserves benchmark variance (below) |
| array | custom $v$ | e.g. $\lvert a^*\rvert$ (pairs you actually trade), or $\mathbb 1[b>0]$ (benchmark constituents, equal-weighted) | weighted RMS |

$\bar\sigma$ is a weighted RMS rather than a weighted mean, so the average variance is preserved.

**Implied $\bar\rho$.** Require $b^\top\Sigma_{\bar\rho}b = b^\top\Sigma b$:

$$
(1-\bar\rho)\sum_i b_i^2\sigma_i^2 + \bar\rho\,(b^\top\sigma)^2 = b^\top\Sigma b
\;\Longrightarrow\;
\bar\rho = \frac{b^\top\Sigma b - \sum_i b_i^2\sigma_i^2}{(b^\top\sigma)^2 - \sum_i b_i^2\sigma_i^2}.
$$

This is exactly §9.1 with $v = b\circ\sigma$.

**Implied $\bar\sigma$.** Require $b^\top\Sigma_{\bar\rho\bar\sigma}b = b^\top\Sigma b$:

$$
\bar\sigma^2 = \frac{b^\top\Sigma b}{(1-\bar\rho)\sum_i b_i^2 + \bar\rho\,(\mathbf 1^\top b)^2}.
$$

### 9.3 Recommendation: equal-weighted (with a sensitivity check)

1. **The choice matters for one number only.** By §8.3, $\bar\sigma$ and (with a budget constraint)
   $\bar\rho$ do not affect the `avg_corr_vol` weights; they only scale its TE. The weighting therefore
   matters only through $\bar\rho$ in `avg_corr`.
2. **That $\bar\rho$ prices active bets.** It sets the penalty on the net vol-weighted bet
   $(\sigma^\top a)^2$ relative to name dispersion. Active positions are not cap-weighted: the optimiser
   spreads them across the whole universe, and small names carry as much active weight as large ones.
   Weighting all pairs equally across the optimisation universe describes the pairs that make up active risk.
3. **Cap weighting answers a different question.** It measures how correlated the benchmark's
   mega-caps are. They usually share size, quality and sector exposures, so their correlation is higher.
   That is the right number for benchmark *total* risk, but it overstates the systematic penalty in an
   active-risk problem.
4. **Use `"implied"`** when you want the simplified models to reproduce benchmark variance exactly, for
   example to compare risk *levels* across variants.
5. **Run more than one.** It costs a few QPs. If the `avg_corr` weights barely move between `"equal"`
   and `"cap"` (in the example below the maximum difference is $6\times10^{-5}$), the choice does not
   affect the conclusions.

## 10. Worked example

Run with `python -m examples.run_attribution`. The synthetic universe has $N = 60$ assets, a market
factor, 3 style factors, 3 countries and 4 industries. The constraints are: budget; long-only;
signal $s^\top a = 0.5$ ($z$-score units); $w\le 5\%$; country and industry bands of ±1%. Budget and
long-only are `fixed`.

**Averages from the factor model**

| weighting | $\bar\rho$ | $\bar\sigma$ |
|---|---|---|
| equal | 0.320 | 0.342 |
| cap | 0.338 | 0.334 |
| implied | 0.327 | 0.331 |

**TE by variant (equal weighting)**

| portfolio from | TE, own model | TE, full model |
|---|---|---|
| full | 2.53% | 2.53% |
| avg_corr | 2.81% | 2.57% |
| avg_corr_vol | 3.01% | 2.61% |

Ignoring all risk structure (the pure projection) costs about 8 bp of TE under the true model.

**KKT TE attribution (full model)**

| group | TE² share | TE contribution |
|---|---|---|
| signal | 76.3% | 1.93% |
| max weight | 32.2% | 0.81% |
| long-only | −7.3% | −0.19% |
| industry | −0.7% | −0.02% |
| country | −0.3% | −0.01% |
| budget | 0.0% | 0.00% |
| **total** | 100% | 2.53% |

Signal and max weight are primary: the benchmark is off target and holds names above 5%. Long-only
and the bands are secondary (§6.5): they bind only because the signal tilt pushes into them, which is
why they get negative allocations.

**Counterfactuals (full model, TE)**

| group | leave-one-out ΔTE | add-one-in TE |
|---|---|---|
| signal | 1.17% | 1.92% |
| max weight | 0.48% | 1.34% |
| country | 0.01% | 0.00% |
| industry | 0.01% | 0.00% |

The bands are not binding at the benchmark. On their own they do nothing; given the other constraints
they cost about 1 bp each.

**Waterfall (sum of |weights| across names)**

| component | Σ\|·\| |
|---|---|
| constraint geometry | 0.589 |
| vol dispersion | 0.078 |
| correlation structure | 0.077 |
| total active (full) | 0.614 |

Most of the active weight pattern is explained by constraint geometry alone. Vol dispersion and
correlation structure reshuffle about 0.08 each. Names capped at 5% have identical weights in all three
variants, so their vol and correlation bars are zero.

## 11. Implementation

### 11.1 Files

| file | content |
|---|---|
| `portfolio_attribution/risk.py` | `LowRankDiagCov` (variance, Woodbury solve, cvxpy objective); `average_correlation`, `average_vol`; `constant_correlation_cov`, `constant_correlation_vol_cov` |
| `portfolio_attribution/constraint_attribution.py` | `ConstraintAttribution` and the result dataclasses |
| `examples/synthetic_problem.py`, `examples/run_attribution.py` | synthetic problem and end-to-end example |
| `tests/test_constraint_attribution.py` | identity and property tests |

### 11.2 API

```python
from portfolio_attribution import ConstraintAttribution

attr = ConstraintAttribution(
    prob, w, b, B, F, D,
    groups={"budget": c0, "long_only": c1, "signal": c2, "max_weight": c3,
            "country": [c_hi, c_lo], "industry": [i_hi, i_lo]},   # optional
    fixed=["budget", "long_only"],
    row_labels={"country": ["US hi", "UK hi", ..., "US lo", ...]},  # optional
    asset_names=tickers,                                            # optional
    solve_kwargs=None,                                              # default: Clarabel, tol 1e-10
)

attr.consistency_check()                   # max |w_yours - w_rebuilt|
rep = attr.run(corr_weighting="equal")     # "cap" | "implied" | array; counterfactuals=True

rep.rho_bar, rep.vol_bar
rep.active_weights        # benchmark + active weights per variant
rep.waterfall             # constraint_geometry | vol_dispersion | correlation_structure | total
rep.te                    # te_own_model, te_full_model per variant
rep.kkt[v].weights        # N x (groups, residual, total): a_k
rep.kkt[v].risk           # te2_contrib, te_contrib, share per group
rep.kkt[v].rows           # per row: type, dual, g_at_benchmark, g_at_solution, active,
                          #          te2_contrib, te_contrib, dTE2_d_tighten, dTE_d_tighten
rep.leave_one_out[v]      # .weights (with interaction), .summary (te_with, te_without, delta_te)
rep.add_one_in[v]         # .weights (with fixed_only), .summary

attr.row_weight_contributions("country", cov=attr.covariance("full"))
attr.solve(cov, group_names)    # building block for Shapley or custom counterfactuals
```

### 11.3 How the constraints are read from the `cvxpy.Problem`

1. **Grouping.** Constraints that involve only `w` are grouped (by default, one group per constraint).
   Constraints that involve other variables, such as a factor-exposure definition `y == B.T @ (w-b)`,
   are dropped with a warning. They are treated as risk-model plumbing, because the objective is rebuilt.
2. **Affine form.** With `w.value = b`, each constraint gives `C = expr.grad[w].T` and $g(b)$ = `expr.value`
   (flattened in Fortran order, matching `dual_value`).
3. **Re-solve.** Each variant and counterfactual solves $\min (w-b)^\top\Sigma_v(w-b)$ over the chosen
   groups, using `sum_squares(U.T @ a) + sum_squares(sqrt(d) * a)`. Duals are read straight after each
   solve, because the constraint objects are shared between solves. The user's `w.value` is restored afterwards.

### 11.4 What the tests verify

* $\sum_k a_k = a^*$ (residual < 1e-6) under all three variants.
* $\mathrm{TE}^2 = \sum_k\tfrac12\mu_k^\top g_k(b)$ and $= \sum_k a_k^\top\Sigma a^*$.
* Row-level legs sum to the group leg.
* The signal dual matches a finite-difference RHS sensitivity.
* The `avg_corr_vol` solution equals the Euclidean projection for several $(\bar\rho,\bar\sigma)$.
* LOO weights plus interaction equal $a^*$; ΔTE ≥ 0 for both LOO and AOI.
* The waterfall telescopes; the full portfolio has the lowest full-model TE.
* The $O(Nr)$ average-correlation formulas match brute force for equal, cap and implied; the implied
  $\bar\rho$ and $\bar\sigma$ preserve benchmark variance.
* Woodbury matches a dense solve.
* Variable attributes such as `nonneg=True` are rejected.

## 12. Practical notes, pitfalls and extensions

* **Explicit constraints.** Write long-only and bounds as constraints (`w >= 0`, `w <= ub`), not as
  `Variable(nonneg=True)` or `bounds=`. Variable attributes have no duals, and the class raises an error.
* **Dual accuracy.** Use an interior-point solver (Clarabel, MOSEK). First-order solvers (OSQP, SCS) give
  approximate duals, which show up as a non-zero `residual` and violate the TE² identity.
* **Degenerate duals.** If the binding rows are linearly dependent, $\mu$ is not unique. Example: all
  country upper bands bind, and the country dummies sum to the budget row. The split *within* the
  dependent set then depends on the solver; its total is unique. Put dependent rows in the same group,
  or read only the group total.
* **Degenerate binding** ($g = 0$, $\mu = 0$). The row is flagged `active`, but it has no KKT or LOO
  effect. It may still matter for larger RHS changes.
* **Signal targets as inequalities** ($s^\top a\ge t$). These are handled the same way; $\mu\ge0$ applies.
* **Other objective terms** (transaction costs, alpha in the objective) break the "benchmark is the
  unconstrained optimum" premise. The KKT decomposition then gains an extra leg,
  $-\tfrac12\Sigma^{-1}\nabla(\text{other terms})$. This is not implemented, since the problem is
  pure TE minimisation.
* **Possible extensions:**
  * Shapley over constraint groups (§7.3).
  * The alternative waterfall path, average vol with true correlations (§8.4).
  * Attribution of the factor exposures $B^\top a_k$ of each leg. This is cheap: multiply each column
    of `kkt.weights` by $B^\top$.
  * Risk split of each leg into factor and specific parts: $a_k^\top BFB^\top a^*$ and $a_k^\top Da^*$.
