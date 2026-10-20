import cvxpy as cp
import numpy as np
import pytest

from examples.synthetic_problem import build_problem
from portfolio_attribution import (
    ConstraintAttribution,
    LowRankDiagCov,
    average_correlation,
    average_vol,
    constant_correlation_cov,
    constant_correlation_vol_cov,
)

pytestmark = pytest.mark.filterwarnings("ignore:dropping")


@pytest.fixture(scope="module")
def setup():
    p = build_problem(n=40, seed=2)
    p["problem"].solve()
    attr = ConstraintAttribution(p["problem"], p["w"], p["b"], p["B"], p["F"], p["D"],
                                 groups=p["groups"], fixed=["budget", "long_only"],
                                 row_labels=p["row_labels"])
    return p, attr


def dense(cov):
    return cov.U @ cov.U.T + np.diag(cov.d)


def test_rebuilt_problem_matches_user_solution(setup):
    _, attr = setup
    assert attr.consistency_check() < 1e-5


@pytest.mark.parametrize("variant", ["full", "avg_corr", "avg_corr_vol"])
def test_kkt_identities(setup, variant):
    p, attr = setup
    cov = attr.covariance(variant)
    sol = attr.solve(cov)
    k = attr.kkt(cov, sol)
    # active weights are exactly the sum of constraint contributions
    assert np.abs(k.weights["residual"]).max() < 1e-6
    # TE^2 = sum_k 1/2 mu_k' g_k(b)
    assert k.risk.loc["total", "te2_contrib"] == pytest.approx(sol.te2, rel=1e-9)
    assert k.risk.drop("total")["te2_contrib"].sum() == pytest.approx(sol.te2, rel=1e-5)
    # ... and equals the Euler risk contribution a_k' Sigma a*
    S = dense(cov)
    for g in attr.groups:
        assert k.weights[g] @ S @ sol.a == pytest.approx(k.risk.loc[g, "te2_contrib"], abs=1e-9)
    # row-level contributions add up to the group column
    np.testing.assert_allclose(attr.row_weight_contributions("country", cov, sol).sum(axis=1),
                               k.weights["country"], atol=1e-10)


def test_dual_is_rhs_sensitivity(setup):
    p, attr = setup
    sol = attr.solve(attr.cov)
    nu = sol.duals["signal"][0]
    # signal row is g = s'a - target; raising the target by eps shifts g by -eps
    eps = 1e-4
    w, b, s = p["w"], p["b"], p["signal"]
    cons = [c for g, cs in attr.groups.items() if g != "signal" for c in cs.constraints]
    prob = cp.Problem(cp.Minimize(attr.cov.cvx_variance(w - b)), cons + [s @ (w - b) == 0.5 + eps])
    prob.solve(**attr.solve_kwargs)
    fd = (attr.cov.quad(w.value - b) - sol.te2) / eps
    assert fd == pytest.approx(-nu, rel=1e-2)


def test_avg_corr_vol_is_euclidean_projection(setup):
    p, attr = setup
    w, b = p["w"], p["b"]
    cons = [c for g in attr.groups.values() for c in g.constraints]
    cp.Problem(cp.Minimize(cp.sum_squares(w - b)), cons).solve(**attr.solve_kwargs)
    proj = w.value - b
    for rho, vol in [(0.1, 0.2), (0.6, 0.4)]:
        sol = attr.solve(constant_correlation_vol_cov(attr.n, rho, vol))
        np.testing.assert_allclose(sol.a, proj, atol=1e-6)


def test_counterfactuals_shapes(setup):
    _, attr = setup
    loo = attr.leave_one_out()
    aoi = attr.add_one_in()
    assert list(loo.summary.index) == ["signal", "max_weight", "country", "industry"]
    np.testing.assert_allclose(loo.weights.drop(columns="total").sum(axis=1), loo.weights["total"], atol=1e-12)
    assert (loo.summary["delta_te"] > -1e-6).all()  # removing a constraint never raises TE
    assert (aoi.summary["delta_te"] > -1e-6).all()


def test_report_waterfall(setup):
    _, attr = setup
    rep = attr.run("cap", counterfactuals=False)
    wf = rep.waterfall
    np.testing.assert_allclose(wf.drop(columns="total").sum(axis=1), wf["total"], atol=1e-12)
    # the full-model portfolio is TE-optimal under the full model
    assert rep.te.loc["full", "te_full_model"] <= rep.te["te_full_model"].min() + 1e-9


def test_average_correlation_and_vol_vs_brute_force():
    rng = np.random.default_rng(3)
    n, k = 25, 4
    cov = LowRankDiagCov.from_factor_model(0.1 + rng.standard_normal((n, k)) * 0.1, np.eye(k), rng.uniform(0.01, 0.05, n))
    S = dense(cov)
    s = np.sqrt(np.diag(S))
    R = S / np.outer(s, s)
    off = ~np.eye(n, dtype=bool)
    b = rng.uniform(0, 1, n)
    b /= b.sum()
    for v, method in [(np.ones(n), "equal"), (b, "cap"), (b * s, "implied")]:
        W = np.outer(v, v)
        assert average_correlation(cov, method, b) == pytest.approx((W * R)[off].sum() / W[off].sum())
    # implied rho preserves benchmark variance under constant correlation; implied vol under constant corr+vol
    rho = average_correlation(cov, "implied", b)
    assert constant_correlation_cov(cov, rho).quad(b) == pytest.approx(b @ S @ b)
    vol = average_vol(cov, "implied", b)
    assert constant_correlation_vol_cov(n, rho, vol).quad(b) == pytest.approx(b @ S @ b)
    assert average_vol(cov, "equal") == pytest.approx(np.sqrt(np.mean(s**2)))
    # Woodbury solve
    X = rng.standard_normal((n, 3))
    np.testing.assert_allclose(cov.solve(X), np.linalg.solve(S, X), rtol=1e-8, atol=1e-8)


def test_variable_attributes_rejected():
    w = cp.Variable(3, nonneg=True)
    prob = cp.Problem(cp.Minimize(cp.sum_squares(w)), [cp.sum(w) == 1])
    with pytest.raises(ValueError, match="explicit constraints"):
        ConstraintAttribution(prob, w, np.ones(3) / 3, np.ones((3, 1)), np.eye(1), np.ones(3))
