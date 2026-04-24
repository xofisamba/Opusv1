"""Tests for domain/financing/depreciation.py"""
import pytest
from domain.financing.depreciation import (
    DepreciationParams,
    financial_depreciation_schedule,
    tax_depreciation_schedule,
    semi_annual_depreciation,
)


class TestDepreciationParams:
    def test_solar_hr(self):
        p = DepreciationParams.create_solar_hr()
        assert p.financial_life_years == 30
        assert p.tax_life_years == 20

    def test_wind_hr(self):
        p = DepreciationParams.create_wind_hr()
        assert p.financial_life_years == 25
        assert p.tax_life_years == 20

    def test_bess_hr(self):
        p = DepreciationParams.create_bess_hr()
        assert p.financial_life_years == 15
        assert p.tax_life_years == 10


class TestFinancialDepreciation:
    def test_straight_line_solar_30y(self):
        p = DepreciationParams.create_solar_hr()
        schedule = financial_depreciation_schedule(30000, p, 30)
        assert len(schedule) == 30
        assert abs(schedule[0] - 1000) < 0.01  # 30,000 / 30 = 1,000
        assert schedule[19] == schedule[0]  # Y20 = Y1
        assert schedule[29] == schedule[0]  # Y30 = Y1 (still depreciating)

    def test_solar_full_capex_recovered(self):
        """Full capex should be depreciated over financial life."""
        p = DepreciationParams.create_solar_hr()
        capex = 60000
        schedule = financial_depreciation_schedule(capex, p, 30)
        # 30 years × 2,000/year = 60,000
        total = sum(s for s in schedule)
        assert abs(total - capex) < 0.01

    def test_zero_after_financial_life(self):
        """No depreciation after financial life ends."""
        p = DepreciationParams.create_solar_hr()
        capex = 60000
        schedule = financial_depreciation_schedule(capex, p, 35)
        # Financial life is 30 years, so Y31+ = 0
        assert schedule[30] == 0.0  # Y31
        assert schedule[34] == 0.0  # Y35


class TestTaxDepreciation:
    def test_straight_line_solar_20y(self):
        """Tax depreciation over 20 years (HR law)."""
        p = DepreciationParams.create_solar_hr()
        schedule = tax_depreciation_schedule(20000, p, 30)
        assert len(schedule) == 30
        assert schedule[0] == 1000  # 20,000 / 20 = 1,000
        assert schedule[19] == 1000  # Y20 = 1,000
        assert schedule[20] == 0.0  # Y21 = 0 (tax life ended)

    def test_tax_vs_financial_tax_ends_sooner(self):
        """Tax life is 20 years, financial is 30 years."""
        p = DepreciationParams.create_solar_hr()
        capex = 60000
        fin = financial_depreciation_schedule(capex, p, 30)
        tax = tax_depreciation_schedule(capex, p, 30)
        # In Y20: both active
        assert fin[19] == 2000
        assert tax[19] == 3000
        # In Y21: tax ended, financial continues
        assert tax[20] == 0.0
        assert fin[20] == 2000

    def test_full_capex_recovered_in_tax_life(self):
        """Full capex depreciated within tax life."""
        p = DepreciationParams.create_solar_hr()
        capex = 40000
        schedule = tax_depreciation_schedule(capex, p, 30)
        # 20 years × 2,000/year = 40,000
        total = sum(s for s in schedule)
        assert abs(total - capex) < 0.01


class TestSemiAnnualDepreciation:
    def test_split_h1_h2_equal(self):
        """Annual depreciation splits 50/50 between H1 and H2."""
        p = DepreciationParams.create_solar_hr()
        annual = [2000.0, 2000.0]  # 2 years × 2,000

        # Mock periods
        class MockPeriod:
            def __init__(self, index, year_index, period_in_year, is_op):
                self.index = index
                self.year_index = year_index
                self.period_in_year = period_in_year
                self.is_operation = is_op

        periods = [
            MockPeriod(1, 1, 1, True),   # Y1 H1
            MockPeriod(2, 1, 2, True),   # Y1 H2
            MockPeriod(3, 2, 1, True),   # Y2 H1
            MockPeriod(4, 2, 2, True),   # Y2 H2
        ]

        result = semi_annual_depreciation(annual, periods)

        # Each operation period gets half of annual
        assert result[1] == 1000.0  # Y1 H1 = 2000/2
        assert result[2] == 1000.0  # Y1 H2 = 2000/2
        assert result[3] == 1000.0  # Y2 H1 = 2000/2
        assert result[4] == 1000.0  # Y2 H2 = 2000/2
