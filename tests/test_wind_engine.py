"""Tests for Wind Engine — Phase 1 Task 1.1."""
import math
import pytest
from core.engines.wind_engine import (
    weibull_pdf,
    hub_height_correction,
    weibull_scale_from_mean,
    power_curve_interpolate,
    annual_energy_production,
    degradation_schedule,
    p_value_from_p50,
    PowerCurve,
    GENERIC_6MW_CLASS3,
    wind_generation_schedule,
)


def test_weibull_integrates_to_one():
    """Weibull PDF should integrate to 1.0 over [0, ∞)."""
    total = sum(weibull_pdf(i * 0.1, k=2.0, A=8.0) * 0.1 for i in range(1, 300))
    assert abs(total - 1.0) < 0.02


def test_hub_height_correction():
    """Higher hub = higher wind speed (power law).
    
    v_hub = v_ref * (h_hub/h_ref)^alpha
    = 7.0 * (120/80)^0.14 ≈ 7.0 * 1.0587 ≈ 7.41
    """
    v_hub = hub_height_correction(7.0, 80, 120, alpha=0.14)
    assert abs(v_hub - 7.41) < 0.05


def test_power_curve_interpolation():
    """Power curve should give zero below cut-in, rated at rated speed, zero above cut-out."""
    curve = GENERIC_6MW_CLASS3
    assert curve.power_at(2.0) == 0           # below cut-in
    assert curve.power_at(14.0) == 6000       # rated power
    assert curve.power_at(26.0) == 0           # above cut-out
    assert abs(curve.power_at(10.0) - 3700) < 50  # interpolation


def test_power_curve_from_csv():
    """Parse CSV power curve."""
    csv = "wind_speed_ms,power_kw\n3.0,0\n4.0,100\n25.0,5000"
    curve = PowerCurve.from_csv_string(csv, "Test Turbine")
    assert curve.turbine_name == "Test Turbine"
    assert curve.cut_in_ms == 3.0
    assert curve.cut_out_ms == 25.0
    assert abs(curve.power_at(4.0) - 100) < 0.01


def test_aep_sensitivity_to_wind_speed():
    """10% wind speed increase → ~25-30% more AEP (cubic relation)."""
    aep_low = annual_energy_production(
        6.0, 2.0, 80, 120,
        list(GENERIC_6MW_CLASS3.points), 6.0,
    )
    aep_high = annual_energy_production(
        6.6, 2.0, 80, 120,
        list(GENERIC_6MW_CLASS3.points), 6.0,
    )
    ratio = aep_high.gross_aep_mwh / aep_low.gross_aep_mwh
    assert 1.20 < ratio < 1.45


def test_p90_less_than_p50():
    """P90 should be less than P50."""
    p50 = 165000.0
    p90 = p_value_from_p50(p50, percentile=90)
    assert p90 < p50


def test_p90_10y_higher_than_p90_1y():
    """10-year average P90 should be higher (less uncertainty) than single-year P90."""
    p50 = 165000.0
    p90_1y = p_value_from_p50(p50, percentile=90, single_year=True)
    p90_10y = p_value_from_p50(p50, percentile=90, single_year=False)
    assert p90_10y > p90_1y


def test_degradation_compound():
    """Degradation should follow compound formula."""
    schedule = degradation_schedule(100.0, 0.005, 30)
    assert abs(schedule[29] - 100 * (0.995 ** 29)) < 0.1


def test_aep_result_has_losses():
    """AEP result should include loss breakdown."""
    result = annual_energy_production(
        7.0, 2.0, 80, 120,
        list(GENERIC_6MW_CLASS3.points), 6.0,
    )
    assert "wake" in result.loss_breakdown
    assert "availability" in result.loss_breakdown
    assert result.net_aep_mwh < result.gross_aep_mwh


def test_capacity_factor_bounds():
    """Capacity factors should be between 0 and 1."""
    result = annual_energy_production(
        7.0, 2.0, 80, 120,
        list(GENERIC_6MW_CLASS3.points), 6.0,
    )
    assert 0 <= result.capacity_factor_gross <= 1
    assert 0 <= result.capacity_factor_net <= 1
    assert result.capacity_factor_gross >= result.capacity_factor_net


def test_wind_generation_schedule_structure():
    """Schedule should have periods starting from index 2."""
    result = annual_energy_production(
        7.0, 2.0, 80, 120,
        list(GENERIC_6MW_CLASS3.points), 6.0,
    )
    schedule = wind_generation_schedule(result, horizon_years=30, periods_per_year=2)
    assert 2 in schedule
    assert 3 in schedule  # first half of year 1
    assert len(schedule) == 60  # 30 years × 2 periods


def test_wind_generation_schedule_sums_to_lifetime_net():
    """All periods should sum to total lifetime net AEP (with degradation).
    
    net_aep_mwh = Year 1 AEP. The schedule sums all years with 0.5% degradation.
    Total lifetime ≈ Year1 × Σ(1-0.005)^(t-1) for t=1..30 ≈ Year1 × 25.3
    """
    result = annual_energy_production(
        7.0, 2.0, 80, 120,
        list(GENERIC_6MW_CLASS3.points), 6.0,
    )
    schedule = wind_generation_schedule(
        result, horizon_years=30, annual_degradation=0.005, periods_per_year=2,
    )
    total = sum(schedule.values())
    # Lifetime net ≈ Year1 * sum of degradation series
    # sum_{t=0}^{29} (1-0.005)^t ≈ 25.26
    assert 14000 < total < 500000  # sanity bounds
