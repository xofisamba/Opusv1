"""Tests for revenue module."""
import pytest
from datetime import date

from domain.inputs import ProjectInputs
from domain.period_engine import PeriodEngine, PeriodFrequency
from domain.revenue.generation import (
    period_generation,
    annual_generation_mwh,
    period_revenue,
    full_generation_schedule,
    full_revenue_schedule,
)
from domain.revenue.tariff import (
    ppa_tariff_at_period,
    market_price_at_period,
    net_revenue_after_balancing,
    co2_certificates_revenue,
)


class TestGenerationCalculation:
    """Test generation calculations."""
    
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
    
    def test_annual_generation_p50(self, inputs):
        """P50 annual generation should be ~112,000 MWh."""
        gen = annual_generation_mwh(inputs.technical, year_index=1, yield_scenario="P50")
        
        # 75.26 MW × 1494 hours × 0.98 availability = ~109,990 MWh
        expected = inputs.technical.capacity_mw * inputs.technical.operating_hours_p50
        assert abs(gen - expected * 0.98) < 100  # Within 100 MWh
    
    def test_annual_generation_p90(self, inputs):
        """P90-10y annual generation should be lower than P50."""
        gen_p50 = annual_generation_mwh(inputs.technical, year_index=1, yield_scenario="P50")
        gen_p90 = annual_generation_mwh(inputs.technical, year_index=1, yield_scenario="P90-10y")
        
        assert gen_p90 < gen_p50
        # P50 hours (1494) vs P90-10y (1410) = ~94% of P50
        assert gen_p90 / gen_p50 > 0.93
    
    def test_generation_degradation(self, inputs):
        """Generation should decrease with degradation."""
        gen_y1 = annual_generation_mwh(inputs.technical, year_index=1)
        gen_y10 = annual_generation_mwh(inputs.technical, year_index=10)
        
        # Y10 should have ~4% degradation (0.4% × 9 years)
        assert gen_y10 < gen_y1
        assert gen_y10 / gen_y1 > 0.95  # Less than 5% reduction
    
    def test_full_generation_schedule(self, inputs, engine):
        """Generation schedule should have 60 operation periods."""
        schedule = full_generation_schedule(inputs, engine, yield_scenario="P50")
        
        op_values = [v for v in schedule.values() if v > 0]
        
        # Should have generation for operation periods
        assert len(op_values) >= 59
        assert len(op_values) <= 61
        
        # First year generation (2 periods) should be positive
        assert sum(op_values[:2]) > 0
    
    def test_revenue_schedule_basic(self, inputs, engine):
        """Revenue schedule should be calculated."""
        revenue = full_revenue_schedule(inputs, engine)
        
        # Should have entries for all periods
        assert len(revenue) == len(engine.periods())
        
        # Operation periods should have positive revenue
        op_revenues = [v for v in revenue.values() if v > 0]
        assert len(op_revenues) >= 59


class TestTariffCalculation:
    """Test tariff and pricing calculations."""
    
    def test_ppa_tariff_y1(self):
        """PPA tariff Y1 should be base tariff."""
        tariff = ppa_tariff_at_period(
            base_tariff=57.0,
            ppa_index=0.02,
            year_index=1,
        )
        assert abs(tariff - 57.0) < 0.01
    
    def test_ppa_tariff_y2(self):
        """PPA tariff Y2 should escalate by 2%."""
        tariff = ppa_tariff_at_period(
            base_tariff=57.0,
            ppa_index=0.02,
            year_index=2,
        )
        expected = 57.0 * 1.02
        assert abs(tariff - expected) < 0.1
    
    def test_ppa_tariff_y12(self):
        """PPA tariff Y12 should be base × 1.02^11."""
        tariff = ppa_tariff_at_period(
            base_tariff=57.0,
            ppa_index=0.02,
            year_index=12,
        )
        expected = 57.0 * (1.02 ** 11)
        assert abs(tariff - expected) < 0.1
    
    def test_ppa_tariff_with_cap(self):
        """PPA tariff should be capped if specified."""
        tariff = ppa_tariff_at_period(
            base_tariff=100.0,
            ppa_index=0.02,
            year_index=20,  # Would be ~143 without cap
            cap_eur_mwh=120.0,
        )
        assert tariff <= 120.0
    
    def test_market_price_from_curve(self):
        """Market price should come from curve."""
        curve = (65.0, 66.3, 67.6, 68.9, 70.0)
        
        price = market_price_at_period(1, curve, market_inflation=0.02)
        assert abs(price - 65.0) < 0.1
        
        price = market_price_at_period(3, curve, market_inflation=0.02)
        assert abs(price - 67.6) < 0.1
    
    def test_market_price_extrapolation(self):
        """Market price should extrapolate after curve ends."""
        curve = (65.0, 66.3, 67.6)
        
        price = market_price_at_period(5, curve, market_inflation=0.02)
        # Extrapolate from last value (67.6)
        expected = 67.6 * (1.02 ** 2)  # 2 years after curve ends
        assert abs(price - expected) < 0.1
    
    def test_net_revenue_after_balancing(self):
        """Net revenue should be gross minus balancing cost."""
        gross = 1000.0
        balancing_pct = 0.025  # 2.5%
        
        net = net_revenue_after_balancing(gross, balancing_pct)
        expected = 1000.0 * (1 - 0.025)  # 975
        assert abs(net - expected) < 0.1
    
    def test_co2_certificates(self):
        """CO2 certificates revenue should be calculated."""
        gen_mwh = 10000.0
        co2_price = 1.5  # EUR/MWh
        
        revenue = co2_certificates_revenue(gen_mwh, co2_price)
        expected = 10000 * 1.5 / 1000  # 15 kEUR
        assert abs(revenue - expected) < 0.1