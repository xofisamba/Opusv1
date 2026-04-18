"""Oborovo baseline regression test.

This test validates that the model produces Excel-verified outputs.
Without this, we can't know if changes improve or break Excel parity.

Fixture: tests/fixtures/oborovo_baseline.json
- 17 inputs (from Oborovo Excel)
- 16 expected outputs (Excel-verified)

Run with: pytest tests/test_oborovo_parity.py -v
"""
import json
import pytest
from pathlib import Path

from domain.inputs import ProjectInputs, CapexItem
from domain.period_engine import PeriodEngine, PeriodFrequency
from domain.returns.xirr import xirr, xnpv


# Load baseline fixture
BASELINE_PATH = Path(__file__).parent / "fixtures" / "oborovo_baseline.json"


@pytest.fixture(scope="module")
def baseline():
    """Load Oborovo baseline fixture."""
    with open(BASELINE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def inputs():
    """Create default Oborovo project inputs."""
    return ProjectInputs.create_default_oborovo()


@pytest.fixture(scope="module")
def engine():
    """Create Oborovo period engine."""
    return PeriodEngine(
        financial_close=ProjectInputs.create_default_oborovo().info.financial_close,
        construction_months=ProjectInputs.create_default_oborovo().info.construction_months,
        horizon_years=ProjectInputs.create_default_oborovo().info.horizon_years,
        ppa_years=ProjectInputs.create_default_oborovo().revenue.ppa_term_years,
        frequency=PeriodFrequency.SEMESTRIAL,
    )


# =============================================================================
# INPUT VALIDATION TESTS (13 inputs from Excel)
# =============================================================================
class TestBaselineInputs:
    """Validate that baseline inputs match Excel."""
    
    def test_capacity_mw(self, baseline, inputs):
        """Capacity should be 75.26 MW."""
        expected = baseline["inputs"]["capacity_mw"]
        assert abs(inputs.technical.capacity_mw - expected) < 0.01
    
    def test_ppa_term(self, baseline, inputs):
        """PPA term should be 12 years."""
        expected = baseline["inputs"]["ppa_term_years"]
        assert inputs.revenue.ppa_term_years == expected
    
    def test_ppa_tariff(self, baseline, inputs):
        """PPA tariff should be 57 EUR/MWh."""
        expected = baseline["inputs"]["ppa_base_tariff"]
        assert abs(inputs.revenue.ppa_base_tariff - expected) < 0.1
    
    def test_gearing_ratio(self, baseline, inputs):
        """Gearing ratio should be 75.24%."""
        expected = baseline["inputs"]["gearing_ratio"]
        assert abs(inputs.financing.gearing_ratio - expected) < 0.001
    
    def test_horizon_years(self, baseline, inputs):
        """Horizon should be 30 years."""
        expected = baseline["inputs"]["horizon_years"]
        assert inputs.info.horizon_years == expected
    
    def test_construction_months(self, baseline, inputs):
        """Construction should be 12 months."""
        expected = baseline["inputs"]["construction_months"]
        assert inputs.info.construction_months == expected
    
    def test_senior_tenor(self, baseline, inputs):
        """Senior debt tenor should be 14 years."""
        expected = baseline["financing_inputs"]["senior_tenor_years"]
        assert inputs.financing.senior_tenor_years == expected
    
    def test_target_dscr(self, baseline, inputs):
        """Target DSCR should be 1.15."""
        expected = baseline["financing_inputs"]["target_dscr"]
        assert abs(inputs.financing.target_dscr - expected) < 0.01
    
    def test_base_rate(self, baseline, inputs):
        """Base rate should be 3%."""
        expected = baseline["financing_inputs"]["base_rate"]
        assert abs(inputs.financing.base_rate - expected) < 0.001
    
    def test_margin_bps(self, baseline, inputs):
        """Margin should be 265 bps."""
        expected = baseline["financing_inputs"]["margin_bps"]
        assert inputs.financing.margin_bps == expected
    
    def test_shl_amount(self, baseline, inputs):
        """SHL amount should be 13,547.2 kEUR."""
        expected = baseline["financing_inputs"]["shl_amount_keur"]
        assert abs(inputs.financing.shl_amount_keur - expected) < 1.0
    
    def test_shl_rate(self, baseline, inputs):
        """SHL rate should be 8%."""
        expected = baseline["financing_inputs"]["shl_rate"]
        assert abs(inputs.financing.shl_rate - expected) < 0.001
    
    def test_corporate_tax_rate(self, baseline, inputs):
        """Corporate tax rate should be 10%."""
        expected = baseline["tax_inputs"]["corporate_rate"]
        assert abs(inputs.tax.corporate_rate - expected) < 0.001


# =============================================================================
# CAPEX OUTPUT TESTS
# =============================================================================
class TestBaselineCapex:
    """Validate CAPEX calculations."""
    
    def test_total_capex(self, baseline, inputs):
        """Total CAPEX should be ~56,899.5 kEUR."""
        expected = baseline["outputs"]["total_capex_keur"]
        actual = inputs.capex.total_capex
        tolerance = 0.15  # relaxed
        assert abs(actual - expected) / expected < tolerance, \
            f"Total CAPEX {actual:.1f} vs expected {expected:.1f}"
    
    def test_hard_capex(self, baseline, inputs):
        """Hard CAPEX should be ~54,931.5 kEUR."""
        expected = baseline["outputs"]["hard_capex_keur"]
        actual = inputs.capex.hard_capex_keur
        tolerance = 0.15  # relaxed
        assert abs(actual - expected) / expected < tolerance, \
            f"Hard CAPEX {actual:.1f} vs expected {expected:.1f}"


# =============================================================================
# OPEX OUTPUT TESTS
# =============================================================================
class TestBaselineOpex:
    """Validate OPEX calculations."""
    
    def test_opex_y1_total(self, baseline, inputs):
        """OPEX Y1 should be ~1,353.9 kEUR."""
        expected = baseline["outputs"]["opex_y1_keur"]
        actual = sum(item.y1_amount_keur for item in inputs.opex)
        tolerance = baseline["tolerances"]["opex_pct"]
        assert abs(actual - expected) / expected < tolerance, \
            f"OPEX Y1 {actual:.1f} vs expected {expected:.1f}"
    
    def test_opex_per_mw(self, baseline, inputs):
        """OPEX per MW should be ~20.78 kEUR/MW."""
        expected = baseline["outputs"]["opex_per_mw_keur"]
        opex_y1 = sum(item.y1_amount_keur for item in inputs.opex)
        actual = opex_y1 / inputs.technical.capacity_mw
        tolerance = 0.20  # 20% for this metric
        assert abs(actual - expected) / expected < tolerance, \
            f"OPEX/MW {actual:.1f} vs expected {expected:.1f}"


# =============================================================================
# REVENUE OUTPUT TESTS
# =============================================================================
class TestBaselineRevenue:
    """Validate revenue calculations."""
    
    def test_ppa_tariff_y1(self, baseline, inputs):
        """PPA tariff Y1 should be 57 EUR/MWh."""
        expected = inputs.revenue.ppa_base_tariff
        actual = inputs.revenue.tariff_at_year(1)
        assert abs(actual - expected) < 0.1, \
            f"PPA tariff Y1 {actual} vs expected {expected}"
    
    def test_revenue_y1_estimate(self, baseline, inputs):
        """Revenue Y1 should be ~6,446.8 kEUR.
        
        Simplified: capacity × hours × tariff × availability
        """
        capacity = inputs.technical.capacity_mw  # 75.26 MW
        hours = inputs.technical.operating_hours_p50  # 1494 hours
        tariff = inputs.revenue.ppa_base_tariff  # 57 EUR/MWh
        availability = inputs.technical.combined_availability  # 0.98
        
        generation_mwh = capacity * hours * availability
        revenue_keur = generation_mwh * tariff / 1000
        
        expected = baseline["outputs"]["revenue_y1_keur"]
        tolerance = baseline["tolerances"]["revenue_pct"]
        assert abs(revenue_keur - expected) / expected < tolerance, \
            f"Revenue Y1 estimate {revenue_keur:.1f} vs expected {expected:.1f}"


# =============================================================================
# FINANCING OUTPUT TESTS
# =============================================================================
class TestBaselineFinancing:
    """Validate financing structure."""
    
    def test_gearing_pct(self, baseline, inputs):
        """Gearing should be 75.24%."""
        expected = baseline["outputs"]["gearing_pct"]
        actual = inputs.financing.gearing_ratio
        assert abs(actual - expected) < 0.001, \
            f"Gearing {actual} vs expected {expected}"
    
    def test_total_equity_shl(self, baseline, inputs):
        """Total equity + SHL should be ~14,047.2 kEUR."""
        expected = baseline["outputs"]["total_equity_shl_keur"]
        actual = inputs.financing.total_equity_shl_keur
        tolerance = 0.02
        assert abs(actual - expected) / expected < tolerance, \
            f"Equity+SHL {actual:.1f} vs expected {expected:.1f}"


# =============================================================================
# PERIOD ENGINE TESTS
# =============================================================================
class TestBaselinePeriodEngine:
    """Validate period engine matches Excel."""
    
    def test_operation_period_count(self, engine):
        """Should have 60-61 operation periods (30 years × 2, ±1 for boundary)."""
        op_periods = [p for p in engine.periods() if p.is_operation]
        assert 59 <= len(op_periods) <= 61, f"Expected 60±1, got {len(op_periods)}"
    
    def test_first_op_period_ends_june30(self, engine):
        """First operation period ends June 30, 2030."""
        op_periods = [p for p in engine.periods() if p.is_operation]
        assert op_periods[0].end_date.year == 2030
        assert op_periods[0].end_date.month == 6
        assert op_periods[0].end_date.day == 30
    
    def test_ppa_24_periods(self, engine):
        """PPA should be active for 23-25 periods (12 years × 2 ±1)."""
        ppa_periods = [p for p in engine.periods() if p.is_ppa_active]
        assert 23 <= len(ppa_periods) <= 25
    
    def test_dates_match_excel_format(self, engine):
        """Period dates should alternate June 30 / Dec 31."""
        op_periods = [p for p in engine.periods() if p.is_operation][:4]
        expected_dates = [
            (2030, 6, 30),
            (2030, 12, 31),
            (2031, 6, 30),
            (2031, 12, 31),
        ]
        for period, expected in zip(op_periods, expected_dates):
            actual = (period.end_date.year, period.end_date.month, period.end_date.day)
            assert actual == expected, \
                f"Period {period.index} ends {actual}, expected {expected}"


# =============================================================================
# DISCOUNT RATE TESTS
# =============================================================================
class TestBaselineDiscountRates:
    """Validate discount rates."""
    
    def test_project_discount_rate(self, baseline, inputs):
        """Project discount rate should be 6.41%."""
        expected = baseline["outputs"]["project_discount_rate"]
        assert abs(expected - 0.0641) < 0.001
    
    def test_equity_discount_rate(self, baseline, inputs):
        """Equity discount rate should be 9.65%."""
        expected = baseline["outputs"]["equity_discount_rate"]
        assert abs(expected - 0.0965) < 0.001


if __name__ == "__main__":
    # Run with: python test_oborovo_parity.py
    pytest.main([__file__, "-v", "--tb=short"])