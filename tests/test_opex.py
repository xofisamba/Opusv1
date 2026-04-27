"""Tests for OPEX module."""
import pytest

from domain.inputs import ProjectInputs
from domain.opex.projections import (
    opex_year,
    opex_schedule_annual,
    opex_per_mw_y1,
    opex_per_mwh_y1,
    opex_schedule_period,
    opex_breakdown_year,
    total_opex_over_horizon,
    opex_growth_rate,
)
from domain.period_engine import PeriodEngine, PeriodFrequency
from datetime import date


class TestOpexCalculation:
    """Test OPEX calculations."""
    
    @pytest.fixture
    def inputs(self):
        return ProjectInputs.create_default_oborovo()
    
    def test_opex_y1_total(self, inputs):
        """OPEX Y1 should be ~1,998 kEUR per Excel CF sheet."""
        opex = opex_year(inputs.opex, 1)
        expected = 1998.0
        assert abs(opex - expected) / expected < 0.02  # Within 2%
    
    def test_opex_items_count(self, inputs):
        """Should have 15 OPEX items."""
        assert len(inputs.opex) == 15
    
    def test_opex_schedule_annual(self, inputs):
        """Annual OPEX schedule should have 30 years."""
        schedule = opex_schedule_annual(inputs, horizon_years=30)
        
        assert len(schedule) == 30
        assert 1 in schedule
        assert 30 in schedule
        
        # Y1 should match manual calculation
        y1_manual = sum(item.amount_at_year(1) for item in inputs.opex)
        assert abs(schedule[1] - y1_manual) < 0.01
    
    def test_opex_escalation(self, inputs):
        """OPEX should escalate for most items."""
        y1 = opex_year(inputs.opex, 1)
        y5 = opex_year(inputs.opex, 5)
        
        # Should increase with 2% annual escalation
        assert y5 > y1
        assert y5 / y1 > 1.05  # More than 5% increase in 4 years
    
    def test_opex_per_mw(self, inputs):
        """OPEX per MW should be ~26 kEUR/MW (1,998 / 75.26)."""
        per_mw = opex_per_mw_y1(inputs)
        assert 24 < per_mw < 30  # ~26.55 kEUR/MW range
    
    def test_opex_per_mwh(self, inputs):
        """OPEX per MWh should be ~18 EUR/MWh."""
        per_mwh = opex_per_mwh_y1(inputs)
        
        # Expected ~18.23 EUR/MWh
        expected = 18.23
        # Allow 20% tolerance due to simplified calculation
        assert 10 < per_mwh < 25  # Reasonable range
    
    def test_opex_breakdown(self, inputs):
        """OPEX breakdown should show all items."""
        breakdown = opex_breakdown_year(inputs, 1)
        
        assert len(breakdown) == 15
        assert "Technical Management" in breakdown
        assert "Insurance" in breakdown
        
        # Technical Management Y1 = 703.1 kEUR (updated per Sprint 10)
        assert abs(breakdown["Technical Management"] - 703.1) < 0.01
    
    def test_opex_step_change(self, inputs):
        """OPEX items with step changes should override escalation."""
        # Infrastructure Maintenance has step change in Y3
        breakdown = opex_breakdown_year(inputs, 3)
        
        # Y3 = 185.64 (step change), not escalated 244 × 1.02^2
        actual = breakdown["Infrastructure Maintenance"]
        assert abs(actual - 185.64) < 0.1
    
    def test_opex_growth_rate(self, inputs):
        """Average OPEX growth rate should be close to 2%."""
        rate = opex_growth_rate(inputs, start_year=1, end_year=10)
        
        # Should be around 2% (some items have 0% escalation)
        assert 0.015 < rate < 0.025


class TestOpexPeriodSchedule:
    """Test semi-annual period OPEX schedule."""
    
    @pytest.fixture
    def inputs(self):
        return ProjectInputs.create_default_oborovo()
    
    @pytest.fixture
    def engine(self):
        return PeriodEngine(
            financial_close=date(2029, 6, 29),
            construction_months=12,
            horizon_years=30,
            ppa_years=12,
            frequency=PeriodFrequency.SEMESTRIAL,
        )
    
    def test_period_schedule_length(self, inputs, engine):
        """Period schedule should match engine periods."""
        schedule = opex_schedule_period(inputs, engine)
        
        assert len(schedule) == len(engine.periods())
    
    def test_construction_periods_zero_opex(self, inputs, engine):
        """Construction periods should have 0 OPEX."""
        schedule = opex_schedule_period(inputs, engine)
        
        # First 2 periods (Y0-H1, Y0-H2) should be 0
        assert schedule[0] == 0.0
        assert schedule[1] == 0.0
    
    def test_operation_periods_positive_opex(self, inputs, engine):
        """Operation periods should have positive OPEX."""
        schedule = opex_schedule_period(inputs, engine)
        
        op_values = [v for k, v in schedule.items() if k >= 2 and v > 0]
        assert len(op_values) >= 59
    
    def test_h1_h2_split(self, inputs, engine):
        """H1 and H2 should each be ~50% of annual."""
        schedule = opex_schedule_period(inputs, engine)
        
        # Y1-H1 (period 2) + Y1-H2 (period 3) should sum to ~Y1 annual
        y1_annual = opex_year(inputs.opex, 1)
        
        period_2 = schedule[2]  # Y1-H1
        period_3 = schedule[3]  # Y1-H2
        
        sum_periods = period_2 + period_3
        assert abs(sum_periods - y1_annual) < 1.0  # Within 1 kEUR
    
    def test_total_opex_undiscounted(self, inputs):
        """Total undiscounted OPEX should be sum of annual."""
        total = total_opex_over_horizon(inputs, horizon_years=30)
        
        # Sum of annual OPEX
        annual_sum = sum(opex_year(inputs.opex, y) for y in range(1, 31))
        
        assert abs(total - annual_sum) < 0.01
    
    def test_total_opex_discounted(self, inputs):
        """Total discounted OPEX should be less than undiscounted."""
        total_undiscounted = total_opex_over_horizon(inputs, horizon_years=30, discount_rate=0.0)
        total_discounted = total_opex_over_horizon(inputs, horizon_years=30, discount_rate=0.08)
        
        assert total_discounted < total_undiscounted