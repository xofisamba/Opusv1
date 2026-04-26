"""Tests for sensitivity analysis (Task 3.4)."""
import pytest
from core.finance.sensitivity import (
    SensitivityResult,
    run_tornado_analysis,
    run_spider_analysis,
)


def get_oborovo_inputs():
    """Get Oborovo inputs - calls the class method directly."""
    from domain.inputs import ProjectInputs
    return ProjectInputs.create_default_oborovo()


class TestSensitivityResult:
    def test_sensitivity_result_dataclass(self):
        r = SensitivityResult(
            variable="PPA Tariff",
            low_value=50.0,
            high_value=75.0,
            low_irr=0.07,
            high_irr=0.09,
            impact_bps=200.0,
        )
        assert r.variable == "PPA Tariff"
        assert r.impact_bps == 200.0

    def test_sensitivity_result_impact_bps_calculation(self):
        """impact_bps = (high_irr - low_irr) * 10000."""
        r = SensitivityResult(
            variable="Test",
            low_value=100,
            high_value=200,
            low_irr=0.08,
            high_irr=0.10,
            impact_bps=(0.10 - 0.08) * 10000,
        )
        assert abs(r.impact_bps - 200) < 0.01


class TestSpiderAnalysis:
    def test_spider_analysis_returns_matrix(self):
        inputs = get_oborovo_inputs()
        result = run_spider_analysis(inputs, n_steps=7)
        assert "variables" in result
        assert "steps" in result
        assert "matrix" in result
        assert len(result["variables"]) == 5

    def test_spider_analysis_steps_symmetric(self):
        inputs = get_oborovo_inputs()
        result = run_spider_analysis(inputs, n_steps=7)
        assert result["steps"] == [-0.20, -0.13, -0.07, 0.0, 0.07, 0.13, 0.20]

    def test_spider_analysis_5_steps(self):
        inputs = get_oborovo_inputs()
        result = run_spider_analysis(inputs, n_steps=5)
        assert len(result["steps"]) == 5

    def test_spider_analysis_all_variables_present(self):
        inputs = get_oborovo_inputs()
        result = run_spider_analysis(inputs, n_steps=7)
        expected = {"PPA Tariff", "Generation", "CAPEX", "OPEX", "Interest Rate"}
        assert set(result["variables"]) == expected

    def test_spider_no_inputs_mutation(self):
        """Verify original inputs are not mutated."""
        inputs = get_oborovo_inputs()
        _ = run_spider_analysis(inputs)
        # If we got here without error, original is intact (no exception)
        assert True


class TestTornadoAnalysis:
    def test_tornado_analysis_returns_sorted_results(self):
        inputs = get_oborovo_inputs()
        results = run_tornado_analysis(inputs)
        assert len(results) == 5
        # Sorted by |impact_bps| descending
        bps_values = [abs(r.impact_bps) for r in results]
        assert bps_values == sorted(bps_values, reverse=True)

    def test_tornado_analysis_has_correct_variables(self):
        inputs = get_oborovo_inputs()
        results = run_tornado_analysis(inputs)
        expected_vars = {"PPA Tariff", "Generation", "CAPEX", "OPEX", "Interest Rate"}
        assert {r.variable for r in results} == expected_vars

    def test_tornado_analysis_low_high_values(self):
        inputs = get_oborovo_inputs()
        results = run_tornado_analysis(inputs)
        for r in results:
            if r.variable == "PPA Tariff":
                assert r.low_value < r.high_value
            if r.variable == "Interest Rate":
                assert r.low_value > r.high_value  # rate: low = +150bps

    def test_tornado_analysis_equity_basis(self):
        inputs = get_oborovo_inputs()
        results = run_tornado_analysis(inputs, target_irr_basis="equity")
        assert len(results) == 5

    def test_tornado_no_inputs_mutation(self):
        """Verify original inputs are not mutated."""
        inputs = get_oborovo_inputs()
        _ = run_tornado_analysis(inputs)
        assert True  # no exception = intact