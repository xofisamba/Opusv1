"""Tests for BESS Engine — Phase 1 Task 1.4."""
import math
import pytest
from core.engines.bess_engine import (
    BESSConfig,
    optimize_dispatch_arbitrage,
    bess_degradation_schedule,
)


@pytest.fixture
def standard_bess():
    """Standard BESS: 20 MWh / 10 MW."""
    return BESSConfig(capacity_mwh=20.0, power_mw=10.0)


def test_dispatch_respects_soc_bounds(standard_bess):
    """SOC must stay within [soc_min, soc_max] for all hours."""
    # Simple price: cheap 0-5h, expensive 12-17h
    prices = ([20.0] * 6 + [50.0] * 6 + [80.0] * 6 + [50.0] * 6) * 7
    result = optimize_dispatch_arbitrage(prices, standard_bess)
    soc_min = standard_bess.capacity_mwh * standard_bess.soc_min_pct
    soc_max = standard_bess.capacity_mwh * standard_bess.soc_max_pct
    for s in result.hourly_soc:
        assert soc_min - 0.01 <= s <= soc_max + 0.01, f"SOC {s:.2f} outside bounds"


def test_dispatch_positive_revenue(standard_bess):
    """Arbitrage on high-low price spread should generate positive revenue."""
    prices = ([20.0] * 12 + [80.0] * 12) * 7
    result = optimize_dispatch_arbitrage(prices, standard_bess)
    assert result.arbitrage_revenue_keur > 0, "Arbitrage should generate positive revenue"


def test_cycle_limit_respected(standard_bess):
    """Annual cycles should not exceed cycle_limit × 365 × 1.05."""
    prices = ([10.0] * 12 + [90.0] * 12) * 7
    result = optimize_dispatch_arbitrage(prices, standard_bess)
    max_annual_cycles = standard_bess.cycle_limit_per_day * 365 * 1.05
    assert result.annual_cycles <= max_annual_cycles


def test_degradation_schedule_decreases(standard_bess):
    """SoH should monotonically decrease over time."""
    soh = bess_degradation_schedule(standard_bess, 5000.0, 10)
    assert len(soh) == 10
    for i in range(len(soh) - 1):
        assert soh[i] >= soh[i + 1], f"SoH increased at year {i+1}"


def test_degradation_schedule_bounded(standard_bess):
    """SoH should stay between 0 and 1."""
    soh = bess_degradation_schedule(standard_bess, 5000.0, 30)
    for s in soh:
        assert 0.0 <= s <= 1.0


def test_dispatch_fallback_on_bad_prices(standard_bess):
    """If LP fails, should return zero dispatch (not crash)."""
    # Edge case: all same price = no arbitrage opportunity
    prices = [50.0] * 168
    result = optimize_dispatch_arbitrage(prices, standard_bess)
    assert isinstance(result.arbitrage_revenue_keur, float)
    assert len(result.hourly_dispatch) == 168


def test_throughput_calculation(standard_bess):
    """Throughput should be calculated correctly."""
    prices = ([20.0] * 12 + [80.0] * 12) * 7
    result = optimize_dispatch_arbitrage(prices, standard_bess)
    assert result.annual_throughput_mwh > 0
    assert result.annual_cycles > 0


def test_charge_and_discharge_prices(standard_bess):
    """Avg discharge price should be higher than avg charge price."""
    prices = ([20.0] * 12 + [80.0] * 12) * 7
    result = optimize_dispatch_arbitrage(prices, standard_bess)
    if result.annual_throughput_mwh > 0:
        assert result.avg_discharge_price > result.avg_charge_price
