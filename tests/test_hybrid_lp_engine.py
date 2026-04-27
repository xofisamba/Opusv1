"""Tests for Hybrid LP Dispatch Engine — Sprint 5B."""
import pytest
import math
from core.engines.hybrid_engine import hybrid_dispatch_lp, hybrid_dispatch
from core.engines.bess_engine import BESSConfig
from core.engines.representative_weeks import generate_representative_weeks


class TestRepresentativeWeeks:
    """Tests for representative weeks generation."""

    def test_generates_8_active_weeks(self):
        weeks = generate_representative_weeks(50, 0, 0.17, 0, 60)
        assert len(weeks) == 8
        assert all(w.weight > 0 for w in weeks)

    def test_weights_sum_to_52(self):
        weeks = generate_representative_weeks(50, 0, 0.17, 0, 60)
        assert abs(sum(w.weight for w in weeks) - 52.0) < 0.01

    def test_each_profile_has_168_hours(self):
        weeks = generate_representative_weeks(50, 35, 0.17, 0.475, 60)
        for w in weeks:
            assert len(w.solar_profile_mw) == 168
            assert len(w.wind_profile_mw) == 168
            assert len(w.price_profile_eur_mwh) == 168

    def test_solar_profile_nonnegative(self):
        weeks = generate_representative_weeks(75, 0, 0.17, 0, 60)
        for week in weeks:
            assert all(v >= 0 for v in week.solar_profile_mw)

    def test_solar_zero_at_night(self):
        """Hour 2 (2:00 AM) must be 0 for all seasons."""
        weeks = generate_representative_weeks(75, 0, 0.17, 0, 60)
        for week in weeks:
            assert week.solar_profile_mw[2] == 0.0

    def test_wind_profile_bounded(self):
        weeks = generate_representative_weeks(0, 35, 0, 0.475, 60)
        for week in weeks:
            assert all(0 <= v <= 35 for v in week.wind_profile_mw)

    def test_wind_zero_when_no_capacity(self):
        weeks = generate_representative_weeks(50, 0, 0.17, 0, 60)
        for week in weeks:
            assert all(v == 0.0 for v in week.wind_profile_mw)

    def test_covers_all_four_seasons(self):
        weeks = generate_representative_weeks(50, 0, 0.17, 0, 60)
        # Winter weeks (1,2) should have lower solar than summer weeks (5,6)
        winter_weeks = [w for w in weeks if w.week_id in (1, 2)]
        summer_weeks = [w for w in weeks if w.week_id in (5, 6)]
        winter_avg = sum(sum(w.solar_profile_mw) for w in winter_weeks) / len(winter_weeks)
        summer_avg = sum(sum(w.solar_profile_mw) for w in summer_weeks) / len(summer_weeks)
        assert summer_avg > winter_avg


class TestHybridDispatchLP:
    """Tests for LP-based hybrid dispatch."""

    def test_no_clipping_under_grid_limit(self):
        """When generation << grid limit, no clipping."""
        result = hybrid_dispatch_lp(
            solar_capacity_mw=10, wind_capacity_mw=0,
            bess=None, grid_limit_mw=100,
            solar_cf_annual=0.17, wind_cf_annual=0,
        )
        assert result.annual_clipping_mwh < result.annual_export_mwh * 0.01

    def test_clipping_when_over_grid_limit(self):
        """When generation >> grid limit, significant clipping."""
        result = hybrid_dispatch_lp(
            solar_capacity_mw=200, wind_capacity_mw=0,
            bess=None, grid_limit_mw=50,
            solar_cf_annual=0.20, wind_cf_annual=0,
        )
        assert result.annual_clipping_mwh > 0
        assert result.clipping_pct > 0.05

    def test_bess_reduces_clipping(self):
        """BESS must reduce clipping vs without BESS."""
        kwargs = dict(
            solar_capacity_mw=150, wind_capacity_mw=0,
            grid_limit_mw=50, solar_cf_annual=0.20, wind_cf_annual=0,
        )
        result_no_bess = hybrid_dispatch_lp(bess=None, **kwargs)
        result_bess = hybrid_dispatch_lp(
            bess=BESSConfig(capacity_mwh=100.0, power_mw=50.0), **kwargs
        )
        assert result_bess.annual_clipping_mwh < result_no_bess.annual_clipping_mwh

    def test_bess_generates_arbitrage_revenue(self):
        """BESS LP dispatch must give positive arbitrage revenue."""
        result = hybrid_dispatch_lp(
            solar_capacity_mw=0, wind_capacity_mw=35,
            bess=BESSConfig(capacity_mwh=50.0, power_mw=25.0),
            grid_limit_mw=100,
            solar_cf_annual=0, wind_cf_annual=0.475,
            spot_price_eur_mwh=80.0,
        )
        assert result.bess_arbitrage_revenue_keur > 0

    def test_no_bess_revenue_without_bess(self):
        """Without BESS, arbitrage revenue must be 0."""
        result = hybrid_dispatch_lp(
            solar_capacity_mw=75, wind_capacity_mw=0,
            bess=None, grid_limit_mw=80,
            solar_cf_annual=0.17, wind_cf_annual=0,
        )
        assert result.bess_arbitrage_revenue_keur == 0.0

    def test_result_method_and_n_weeks(self):
        result = hybrid_dispatch_lp(
            solar_capacity_mw=75, wind_capacity_mw=0,
            bess=None, grid_limit_mw=80,
            solar_cf_annual=0.17, wind_cf_annual=0,
        )
        assert result.method == "lp_representative_weeks"
        assert result.n_weeks == 8

    def test_weekly_results_structure(self):
        """LP result must have per-week breakdown."""
        result = hybrid_dispatch_lp(
            solar_capacity_mw=75, wind_capacity_mw=0,
            bess=None, grid_limit_mw=80,
            solar_cf_annual=0.17, wind_cf_annual=0,
        )
        assert len(result.weekly_results) == 8
        for w in result.weekly_results:
            assert "export_mwh" in w
            assert "week_id" in w
            assert "weight" in w

    def test_solar_wind_hybrid_exports_more(self):
        """Solar + wind hybrid exports more than solar only."""
        solar_only = hybrid_dispatch_lp(
            solar_capacity_mw=75, wind_capacity_mw=0,
            bess=None, grid_limit_mw=200,
            solar_cf_annual=0.17, wind_cf_annual=0,
        )
        hybrid = hybrid_dispatch_lp(
            solar_capacity_mw=75, wind_capacity_mw=35,
            bess=None, grid_limit_mw=200,
            solar_cf_annual=0.17, wind_cf_annual=0.475,
        )
        assert hybrid.annual_export_mwh > solar_only.annual_export_mwh

    def test_solar_approximation_within_5pct(self):
        """LP export must be within 5% of CF approximation."""
        mw = 75.26
        cf = 0.17
        hours = 8760
        cf_estimate = mw * cf * hours

        result = hybrid_dispatch_lp(
            solar_capacity_mw=mw, wind_capacity_mw=0,
            bess=None, grid_limit_mw=mw,
            solar_cf_annual=cf, wind_cf_annual=0,
        )
        diff_pct = abs(result.annual_export_mwh - cf_estimate) / cf_estimate
        assert diff_pct < 0.05, (
            f"LP export {result.annual_export_mwh:.0f} vs CF {cf_estimate:.0f} "
            f"({diff_pct:.1%})"
        )

    def test_wind_approximation_within_5pct(self):
        """LP wind export must be within 5% of CF approximation."""
        mw = 35
        cf = 0.475
        hours = 8760
        cf_estimate = mw * cf * hours

        result = hybrid_dispatch_lp(
            solar_capacity_mw=0, wind_capacity_mw=mw,
            bess=None, grid_limit_mw=mw,
            solar_cf_annual=0, wind_cf_annual=cf,
        )
        diff_pct = abs(result.annual_export_mwh - cf_estimate) / cf_estimate
        assert diff_pct < 0.05


class TestBackwardCompatibility:
    """Tests for backward-compatible hybrid_dispatch() wrapper."""

    def test_wrapper_returns_lp_result(self):
        """Old hybrid_dispatch() calls new LP engine."""
        result = hybrid_dispatch(50000, 0, None, grid_limit_mw=100)
        assert result.method == "lp_representative_weeks"
        assert result.annual_export_mwh > 0

    def test_wrapper_clipping(self):
        """High generation → clipping."""
        result = hybrid_dispatch(800000, 0, None, grid_limit_mw=80)
        assert result.annual_clipping_mwh > 0

    def test_wind_gen_positive(self):
        """Wind generation > 0."""
        result = hybrid_dispatch(0, 145000, None, grid_limit_mw=35)
        assert result.annual_export_mwh > 0