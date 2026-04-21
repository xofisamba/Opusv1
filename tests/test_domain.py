"""Pytest testovi za domain logiku Opusv1."""
import pytest
from datetime import date

from domain.inputs import (
    ProjectInputs, CapexItem, TechnicalParams, RevenueParams, FinancingParams
)
from domain.period_engine import PeriodEngine


class TestCapexItem:
    """Test suite for CapexItem spending profile logic."""

    def test_spending_shares_sum_to_one(self):
        """Svi defaultni CapexItem udjeli moraju zbrojiti na 1.0."""
        inputs = ProjectInputs.create_default_oborovo()
        items = [
            inputs.capex.epc_contract, inputs.capex.production_units,
            inputs.capex.epc_other, inputs.capex.grid_connection,
        ]
        for item in items:
            if item.y0_share > 0 or item.spending_profile:
                total = item.total_spending_shares
                assert abs(total - 1.0) < 0.01, (
                    f'{item.name}: suma = {total:.4f}'
                )

    def test_amount_in_period_y0(self):
        """Amount za Y0 = amount_keur * y0_share."""
        item = CapexItem('Test', 1000.0, y0_share=0.3, spending_profile=(0.7,))
        assert item.amount_in_period(0) == pytest.approx(300.0)

    def test_amount_in_period_y1(self):
        """Amount za Y1 = amount_keur * spending_profile[0]."""
        item = CapexItem('Test', 1000.0, y0_share=0.3, spending_profile=(0.7,))
        assert item.amount_in_period(1) == pytest.approx(700.0)

    def test_amount_in_period_invalid(self):
        """Period izvan profile vraća 0."""
        item = CapexItem('Test', 1000.0, y0_share=0.0, spending_profile=(0.5, 0.5))
        assert item.amount_in_period(0) == pytest.approx(0.0)
        assert item.amount_in_period(5) == pytest.approx(0.0)


class TestPeriodEngine:
    """Test suite for PeriodEngine period generation."""

    @pytest.fixture
    def engine(self):
        return PeriodEngine(
            financial_close=date(2029, 6, 29),
            construction_months=12,
            horizon_years=30,
            ppa_years=12,
        )

    def test_period_count(self, engine):
        """30 godina x 2 perioda + 2 construction = 63 perioda ukupno (ukljucujuci kratak prvi operation period)."""
        assert len(engine.periods()) == 63

    def test_construction_periods(self, engine):
        """2 construction perioda."""
        periods = engine.periods()
        construction = [p for p in periods if p.is_construction]
        assert len(construction) == 2

    def test_first_operation_year_index(self, engine):
        """H1 i H2 prve operativne godine imaju year_index=1."""
        op = engine.operation_periods()
        assert op[0].year_index == 1
        assert op[1].year_index == 1

    def test_second_operation_year_index(self, engine):
        """Prva dva perioda Y2 imaju year_index=2."""
        op = engine.operation_periods()
        assert op[2].year_index == 2
        assert op[3].year_index == 2

    def test_last_year_index(self, engine):
        """Zadnji period ima year_index=31."""
        op = engine.operation_periods()
        assert op[-1].year_index == 31

    def test_ppa_period_count(self, engine):
        """PPA traje 12 godina = 25 perioda (ukljucujuci kratki prvi period)."""
        assert len(engine.ppa_periods()) == 25

    def test_cod_date(self, engine):
        """COD = FC + 12 months."""
        assert engine.cod == date(2030, 6, 29)


class TestRevenueParams:
    """Test suite for Revenue calculations."""

    def test_tariff_escalation_year1(self):
        """Year 1 tariff = base tariff (no escalation yet)."""
        r = RevenueParams(ppa_base_tariff=57.0, ppa_term_years=12, ppa_index=0.02)
        assert r.tariff_at_year(1) == pytest.approx(57.0)

    def test_tariff_escalation_year2(self):
        """Year 2 tariff = base * (1 + index)."""
        r = RevenueParams(ppa_base_tariff=57.0, ppa_term_years=12, ppa_index=0.02)
        assert r.tariff_at_year(2) == pytest.approx(57.0 * 1.02)

    def test_ppa_index_is_fraction_not_percent(self):
        """ppa_index=0.02 znaci 2%, ne 200%."""
        r = RevenueParams(ppa_base_tariff=57.0, ppa_term_years=12, ppa_index=0.02)
        assert r.tariff_at_year(2) < 100  # 200% bi dalo > 100 EUR/MWh Y2

    def test_tariff_outside_ppa_term(self):
        """Tariff after PPA term - may be market or zero."""
        r = RevenueParams(ppa_base_tariff=57.0, ppa_term_years=12, ppa_index=0.02)
        # After PPA term - implementation depends on model
        # But should not crash
        result = r.tariff_at_year(15)
        assert result is not None


class TestFinancingParams:
    """Test suite for Financing calculations."""

    def test_all_in_rate(self):
        """all_in_rate = base_rate + margin_bps/10000."""
        f = FinancingParams(base_rate=0.03, margin_bps=265)
        assert f.all_in_rate == pytest.approx(0.0565)

    def test_base_rate_is_fraction(self):
        """base_rate=0.03 znaci 3%, ne 300%."""
        f = FinancingParams(base_rate=0.03, margin_bps=265)
        assert f.all_in_rate < 0.20  # 300% bi dalo > 1.0

    def test_gearing_ratio(self):
        """Gearing ratio should be stored as fraction."""
        f = FinancingParams(base_rate=0.03, margin_bps=200, gearing_ratio=0.75)
        assert f.gearing_ratio == pytest.approx(0.75)
        assert f.gearing_ratio < 1.0


class TestProjectInputs:
    """Test suite for ProjectInputs factory and defaults."""

    def test_create_default_oborovo(self):
        """Default Oborovo inputs should be valid."""
        inputs = ProjectInputs.create_default_oborovo()
        assert "Oborovo" in inputs.info.name
        assert inputs.technical.capacity_mw > 0
        assert inputs.capex.total_capex > 0

    def test_default_revenue_params(self):
        """Default revenue should be reasonable."""
        r = RevenueParams(ppa_base_tariff=57.0, ppa_term_years=12, ppa_index=0.02)
        assert r.ppa_base_tariff == 57.0
        assert r.ppa_term_years == 12
        assert r.ppa_index == 0.02

    def test_ppa_index_bounds(self):
        """ppa_index should be small fraction, not percent."""
        r = RevenueParams(ppa_base_tariff=100.0, ppa_term_years=10, ppa_index=0.03)
        assert r.ppa_index < 0.1  # 10% max
        # After 10 years: 100 * 1.03^10 ≈ 134 EUR/MWh
        assert r.tariff_at_year(10) < 200  # Reasonable bound