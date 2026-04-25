"""Wind Project 1 — Blueprint §6.1 fixture.

Parameters:
    capacity_mw = 60.0 MW (10 × 6 MW turbines)
    v_mean = 7.2 m/s, k = 2.1, h_hub = 120m, h_ref = 80m
    wake = 8%, availability = 97%, curtailment = 2%,
    electrical = 2%, icing = 1%
    degradation = 0.5%/year, horizon = 30 years

Note: engine uses single-turbine power curve; farm AEP = n_turbines × single_turbine_aep.
"""
import pytest
from core.engines.wind_engine import (
    annual_energy_production,
    degradation_schedule,
    p_value_from_p50,
    GENERIC_6MW_CLASS3,
    wind_generation_schedule,
)


TURBINE_MW = 6.0
N_TURBINES = 10
FARM_MW = TURBINE_MW * N_TURBINES


def wind_project1_aep():
    """Run annual_energy_production with Blueprint §6.1 parameters."""
    return annual_energy_production(
        v_mean_ms=7.2,
        k_shape=2.1,
        h_ref_m=80.0,
        h_hub_m=120.0,
        power_curve=list(GENERIC_6MW_CLASS3.points),
        installed_capacity_mw=TURBINE_MW,  # one turbine; farm = n_turbines × this
        wake_loss=0.08,
        availability=0.97,
        curtailment=0.02,
        electrical_loss=0.02,
        icing_soiling=0.01,
    )


def test_wind1_net_aep_in_range():
    """Blueprint §6.1: net_aep_y1 should be 150,000–180,000 MWh."""
    result = wind_project1_aep()
    farm_aep = result.net_aep_mwh * N_TURBINES
    assert 150_000 <= farm_aep <= 180_000, (
        f"Wind Project 1 AEP {farm_aep:,.0f} MWh outside range [150k, 180k]"
    )


def test_wind1_capacity_factor():
    """CF_net should be between 0.28 and 0.35 for good wind site."""
    result = wind_project1_aep()
    assert 0.28 <= result.capacity_factor_net <= 0.35, (
        f"CF_net {result.capacity_factor_net:.3f} outside [0.28, 0.35]"
    )


def test_wind1_p90_less_than_p50():
    """P90 values should be less than P50."""
    result = wind_project1_aep()
    p50 = result.net_aep_mwh * N_TURBINES
    p90_1y = p_value_from_p50(p50, percentile=90, single_year=True)
    p90_10y = p_value_from_p50(p50, percentile=90, single_year=False)
    assert p90_1y < p50
    assert p90_10y < p50
    assert p90_10y > p90_1y  # 10-year average is less uncertain


def test_wind1_degradation_schedule_decreases():
    """Degradation schedule should monotonically decrease."""
    result = wind_project1_aep()
    y1 = result.net_aep_mwh * N_TURBINES
    schedule = degradation_schedule(y1, 0.005, 30)
    for i in range(len(schedule) - 1):
        assert schedule[i] >= schedule[i + 1], (
            f"Degradation schedule increased at year {i+2}"
        )


def test_wind1_degradation_final_less_than_initial():
    """Year 30 AEP should be notably lower than Year 1."""
    result = wind_project1_aep()
    y1 = result.net_aep_mwh * N_TURBINES
    schedule = degradation_schedule(y1, 0.005, 30)
    # After 30 years at 0.5%/yr: (1-0.005)^29 ≈ 0.865
    assert schedule[29] < schedule[0] * 0.88


def test_wind1_generation_schedule_structure():
    """Schedule should have 60 periods (30 years × 2 semi-annual)."""
    result = wind_project1_aep()
    schedule = wind_generation_schedule(
        result, horizon_years=30, annual_degradation=0.005, periods_per_year=2,
    )
    assert len(schedule) == 60
    assert 2 in schedule
    assert 61 in schedule  # last period index
