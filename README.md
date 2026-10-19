# optattr: Optimization Attribution Framework (spec v3)

Explains every stock active weight as the sum of individual **target** and
**constraint pressures**, propagated through the covariance / precision
structure.

```
sources h^(r)  --Sigma^-1-->  x^(r)  --precision split-->  own + network (+ peer-netted view)
x_i = sum_r x_i^(r)          Sigma x = h = sum_r h^(r)     (KKT, exact)
```

## Run

```bash
python -m venv .venv && .venv/bin/pip install -e .[dev]
.venv/bin/python -m optattr --out output        # full demo (~70s incl. 256-solve Shapley)
.venv/bin/python -m optattr --no-shapley        # ~3s
.venv/bin/python -m pytest -q
```

## Modules

| module | spec | contents |
|---|---|---|
| `universe.py` | §11 | deterministic 1,000-stock universe: 8 styles, 10 sectors, 8 countries, cap-weighted benchmark, current and prior signals |
| `covariance.py` | §13–14 | `Sigma = X Phi X^T + diag(d)` with grouped columns (style / sector / country / pair); vol-preserving restrictions |
| `problem.py` | §2–3, §11–12 | CVXPY + Clarabel QP; each constraint block is named and keeps its explicit x-row matrix, so `h_k = -A_k^T mu_k` |
| `attribution.py` | §4–10 | propagation `x^(r) = Sigma^-1 h^(r)`, own/network split, peer layer, §9 stock table, source summary, reconciliation |
| `counterfactual.py` | §14, §15.6 | covariance ladder and exact factor-by-factor Shapley (2^K re-solves) |

## Design decisions (beyond the spec)

- **Sign convention.** `Sigma x - h_target + sum_k A_k^T mu_k = 0` for both `<=` and `==` rows. This matches CVXPY and is covered by a test. Two-sided limits are separate upper and lower rows.
- **Targets.** Each target is an objective tilt `h_m = lambda * theta_m * score_m` (the 8 styles plus a stock alpha). Style *exposure bands* are separate constraints, and each gets its own dual pressure (`Exposure band: <factor>`).
- **Turnover and active share are both modelled.**
  - Turnover is `1/2 sum|w - w0| <= 10%` against prior holdings `w0`. `w0` is last period's optimum under decayed signals.
  - Active share is `1/2 sum|w - b| <= 25%`.
  - Both use auxiliary split variables. Only their x-linking rows produce pressure.
- **Peer set (§8).** For each stock, the top-k stocks by |partial correlation| `-Omega_ij / sqrt(Omega_ii Omega_jj)`, with `a_ij ∝ |Omega_ij|`. The network term is split exactly into three parts:
  - **common:** `(sum_P Omega_ij) z_i`
  - **differentiated:** `sum_P Omega_ij (z_j - z_i)`
  - **rest of network**
- **Counterfactuals.** Every covariance variant keeps the production asset vols, with removed factor variance moved into `d`. So the ladder (vol-only → factor → +sector/country residual → +pair links = production) and the Shapley players isolate *correlation* effects. `h_target` is held fixed and the constraints are re-imposed at every rung.
- **Shapley players.** The 8 style factor blocks `Phi[S,S]`. Sector, country and pair residual blocks stay at production.
- **Numerics.** `f = X^T x` is an explicit variable, which keeps the KKT system sparse (about 0.2 s per solve at N=1,000). The objective is scaled by 1e4, and the duals are unscaled on extraction.
