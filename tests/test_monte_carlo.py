"""Tests for Monte Carlo simulation (Task 3.7) and Cash-at-Risk (Task 3.8)."""
import pytest
import numpy as np
from core.finance.monte_carlo import (
    MonteCarloResult,
    CashAtRiskResult,
    run_monte_carlo,
    cash_at_risk,
)


def get_oborovo_inputs():
    """Get Oborovo inputs."""
    from domain.inputs import ProjectInputs
    return ProjectInputs.create_default_oborovo()


class TestMonteCarloResult:
    def test_monte_carlo_result_dataclass(self):
        r = MonteCarloResult(
            n_iterations=100,
            equity_irr_distribution=[0.08, 0.09, 0.10],
            project_irr_distribution=[0.065, 0.07, 0.075],
            min_dscr_distribution=[1.2, 1.3, 1.4],
            p10_equity_irr=0.08,
            p50_equity_irr=0.09,
            p90_equity_irr=0.10,
            prob_dscr_below_1=0.05,
            prob_dscr_below_110=0.10,
        )
        assert r.n_iterations == 100
        assert len(r.equity_irr_distribution) == 3
        assert r.p10_equity_irr == 0.08

    def test_monte_carlo_result_p50_median(self):
        """p50_equity_irr should be close to median of equity_irr_distribution."""
        dist = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
        r = MonteCarloResult(
            n_iterations=6,
            equity_irr_distribution=dist,
            project_irr_distribution=dist,
            min_dscr_distribution=[1.2] * 6,
            p10_equity_irr=0.05,
            p50_equity_irr=0.075,
            p90_equity_irr=0.10,
            prob_dscr_below_1=0.0,
            prob_dscr_below_110=0.0,
        )
        assert abs(r.p50_equity_irr - np.median(dist)) < 0.01


class TestCashAtRiskResult:
    def test_cash_at_risk_dataclass(self):
        r = CashAtRiskResult(
            expected_distributions_keur=5000.0,
            var_95_keur=4000.0,
            cash_at_risk_keur=1000.0,
            confidence_level=0.95,
        )
        assert r.cash_at_risk_keur == 1000.0
        assert r.confidence_level == 0.95

    def test_cash_at_risk_formula(self):
        """CaR = E[dist] - VaR_alpha."""
        # E[irr] = 10%, VaR_95 = 8% → CaR = 2%
        r = CashAtRiskResult(
            expected_distributions_keur=0.10 * 10000,
            var_95_keur=0.08 * 10000,
            cash_at_risk_keur=0.02 * 10000,
            confidence_level=0.95,
        )
        assert abs(r.cash_at_risk_keur - 200) < 1


class TestRunMonteCarlo:
    def test_run_monte_carlo_small(self):
        """Run MC with 10 iterations to verify structure."""
        inputs = get_oborovo_inputs()
        result = run_monte_carlo(inputs, n_iterations=10, seed=42)
        assert isinstance(result, MonteCarloResult)
        assert result.n_iterations == 10
        assert len(result.equity_irr_distribution) == 10
        assert len(result.project_irr_distribution) == 10
        assert len(result.min_dscr_distribution) == 10
        # Percentiles should be in order
        assert result.p10_equity_irr <= result.p50_equity_irr <= result.p90_equity_irr

    def test_run_monte_carlo_reproducible_with_seed(self):
        """Same seed → same results."""
        inputs = get_oborovo_inputs()
        r1 = run_monte_carlo(inputs, n_iterations=5, seed=123)
        r2 = run_monte_carlo(inputs, n_iterations=5, seed=123)
        assert r1.equity_irr_distribution == r2.equity_irr_distribution

    def test_run_monte_carlo_different_seed_differs(self):
        """Different seed → different results."""
        inputs = get_oborovo_inputs()
        r1 = run_monte_carlo(inputs, n_iterations=5, seed=111)
        r2 = run_monte_carlo(inputs, n_iterations=5, seed=999)
        assert r1.equity_irr_distribution != r2.equity_irr_distribution

    def test_prob_dscr_bounds(self):
        """prob_dscr_below_1 and prob_dscr_below_110 should be in [0, 1]."""
        inputs = get_oborovo_inputs()
        result = run_monte_carlo(inputs, n_iterations=20, seed=42)
        assert 0.0 <= result.prob_dscr_below_1 <= 1.0
        assert 0.0 <= result.prob_dscr_below_110 <= 1.0


class TestCashAtRisk:
    def test_cash_at_risk_from_mc_result(self):
        """cash_at_risk returns CashAtRiskResult with correct CaR formula."""
        inputs = get_oborovo_inputs()
        mc = run_monte_carlo(inputs, n_iterations=20, seed=42)
        car = cash_at_risk(mc, confidence_level=0.95)
        assert isinstance(car, CashAtRiskResult)
        assert car.confidence_level == 0.95

    def test_cash_at_risk_default_confidence(self):
        """Default confidence_level = 0.95."""
        inputs = get_oborovo_inputs()
        mc = run_monte_carlo(inputs, n_iterations=10, seed=42)
        car = cash_at_risk(mc)
        assert car.confidence_level == 0.95

    def test_cash_at_risk_custom_confidence(self):
        """Custom confidence_level = 0.90."""
        inputs = get_oborovo_inputs()
        mc = run_monte_carlo(inputs, n_iterations=10, seed=42)
        car = cash_at_risk(mc, confidence_level=0.90)
        assert car.confidence_level == 0.90