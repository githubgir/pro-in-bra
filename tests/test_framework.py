from dataclasses import replace

import cvxpy as cp
import numpy as np
import pytest

from optattr import (Optimizer, PortfolioSpec, attribute, covariance_ladder, factor_shapley,
                     prior_holdings, synthetic_universe)
from optattr.attribution import TOL


@pytest.fixture(scope="module")
def setup():
    u = synthetic_universe(n=300, n_pairs=10, seed=11)
    spec = PortfolioSpec(stock_max=max(0.015, float(u.b.max()) - 0.005))
    u = u.with_prior(prior_holdings(u, spec))
    opt = Optimizer(u, spec)
    sol = opt.solve()
    return u, spec, opt, sol, attribute(sol, n_peers=8)


def test_cvxpy_dual_convention_matches_spec():
    # min 1/2 x^2 - 2x  s.t. x <= 0.5 (and == 0.5): grad f + mu * grad g = 0
    for make in (lambda x: x <= 0.5, lambda x: x == 0.5):
        x = cp.Variable()
        con = make(x)
        cp.Problem(cp.Minimize(0.5 * cp.square(x) - 2 * x), [con]).solve(solver="CLARABEL")
        assert np.isclose((x.value - 2.0) + con.dual_value, 0.0, atol=1e-7)


def test_covariance_restrict_preserves_vols_and_psd(setup):
    u = setup[0]
    full = u.cov
    for groups in ((), ("style",), ("style", "sector", "country")):
        v = full.restrict(full.column_mask(groups=groups))
        np.testing.assert_allclose(v.vols(), full.vols(), rtol=1e-12)
        assert np.linalg.eigvalsh(v.dense()).min() > 0


def test_reconciliation_identities(setup):
    rec = setup[4].reconciliation()
    assert rec["pass"].all(), rec


def test_pressure_sum_is_kkt(setup):
    u, _, _, sol, att = setup
    np.testing.assert_allclose(u.cov.dense() @ sol.x.to_numpy(), sol.h, atol=1e-12)
    np.testing.assert_allclose(att.Xr.sum(axis=1), sol.x.to_numpy(), atol=1e-12)


def test_inactive_constraints_have_zero_pressure(setup):
    sol = setup[3]
    for src, status in sol.status.items():
        p = np.abs(sol.pressures[src]).max()
        if status == "inactive":
            assert p < 1e-8, src
        elif status == "binding":
            assert p > 1e-8, src


def test_budget_is_equality_and_targets_labelled(setup):
    sol = setup[3]
    assert sol.status["Budget"] == "equality"
    assert all(sol.status[s] == "target" for s in sol.target_pressure)
    assert sol.status["Turnover"] == "binding"


def test_stock_table_reconciles(setup):
    att = setup[4]
    for stock in att.top_stocks(5):
        t = att.stock_table(stock, peer_detail=True)
        body = t.drop(index=["TOTAL", "Optimised active weight"])
        np.testing.assert_allclose(body["Own precision"] + body["Network"], body["Weight contribution"], atol=1e-12)
        np.testing.assert_allclose(body["Peer common"] + body["Peer differentiated"] + body["Other network"],
                                   body["Network"], atol=1e-12)
        assert t.loc["TOTAL", "Status"] == "reconciles"


def test_peer_weights(setup):
    att = setup[4]
    assert np.all(att.peer_w >= 0)
    np.testing.assert_allclose(att.peer_w.sum(axis=1), 1.0)
    assert not np.any(att.peers == np.arange(len(att.sigma))[:, None])


def test_risk_contributions_sum_to_te(setup):
    att = setup[4]
    x = att.sol.x.to_numpy()
    te = np.sqrt(x @ att.Sigma @ x)
    assert np.isclose(att.source_summary()["Active risk contrib"].sum(), te, rtol=1e-9)


def test_ladder_telescopes_to_optimum(setup):
    _, _, opt, sol, _ = setup
    lad = covariance_ladder(opt, reference=sol)
    assert lad.telescoping_error() < 1e-14
    assert lad.summary.attrs["final_vs_reference"] < 1e-8


def test_shapley_efficiency(setup):
    _, _, opt, sol, _ = setup
    sh = factor_shapley(opt, players=["Market", "Value", "Momentum"])
    assert sh.n_solves == 8
    assert sh.efficiency_error() < 1e-14
    np.testing.assert_allclose(sh.x_all, sol.x, atol=1e-8)


def test_single_player_shapley_is_marginal(setup):
    opt = setup[2]
    sh = factor_shapley(opt, players=["Value"])
    np.testing.assert_allclose(sh.phi["Value"], sh.x_all - sh.x_none, atol=1e-15)


def test_turnover_and_active_share_limits(setup):
    u, spec, _, sol, _ = setup
    assert 0.5 * (sol.w - u.w0).abs().sum() <= spec.turnover_oneway + 1e-8
    assert 0.5 * sol.x.abs().sum() <= spec.active_share_max + 1e-8
    assert sol.w.min() >= -1e-9 and abs(sol.w.sum() - 1) < 1e-9


def test_disabling_constraint_removes_source(setup):
    u, spec, _, _, _ = setup
    sol = Optimizer(u, replace(spec, turnover_oneway=None, active_share_max=None)).solve()
    assert "Turnover" not in sol.status and "Active share" not in sol.status
    assert attribute(sol).reconciliation()["rel_error"].max() < TOL
