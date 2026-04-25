"""Tests for Hybrid Engine — Phase 1 Task 1.8."""
import pytest
from core.engines.hybrid_engine import hybrid_dispatch
from core.engines.bess_engine import BESSConfig


def test_no_clipping_under_limit():
    """No clipping when generation is below grid limit."""
    result = hybrid_dispatch(50000, 0, None, grid_limit_mw=100, hours=8760)
    assert result.annual_clipping_mwh == 0.0
    assert result.annual_export_mwh == 50000


def test_clipping_above_limit():
    """Clipping occurs when generation exceeds grid capacity."""
    # 80 MW × 8760 h = 700,800 MWh grid capacity
    # 800,000 MWh → 99,200 MWh clipping
    result = hybrid_dispatch(800000, 0, None, grid_limit_mw=80, hours=8760)
    assert result.annual_clipping_mwh > 0
    assert result.annual_export_mwh <= 80 * 8760 + 1


def test_store_excess_reduces_clipping():
    """BESS with store_excess strategy should reduce clipping."""
    bess = BESSConfig(capacity_mwh=40.0, power_mw=20.0)
    r_no_bess = hybrid_dispatch(800000, 0, None, grid_limit_mw=80, hours=8760)
    r_bess = hybrid_dispatch(
        800000, 0, bess, grid_limit_mw=80,
        strategy="store_excess", hours=8760,
    )
    assert r_bess.annual_clipping_mwh < r_no_bess.annual_clipping_mwh


def test_export_plus_clipping_equals_gross():
    """Export + Clipping should equal gross generation."""
    result = hybrid_dispatch(500000, 200000, None, grid_limit_mw=60, hours=8760)
    gross = 700000
    assert abs(result.annual_export_mwh + result.annual_clipping_mwh - gross) < 1.0


def test_grid_utilization_bounded():
    """Grid utilization should be between 0 and 1."""
    result = hybrid_dispatch(50000, 0, None, grid_limit_mw=100, hours=8760)
    assert 0 <= result.grid_utilization_pct <= 1.0


def test_bess_throughput_recorded():
    """store_excess should record BESS throughput."""
    bess = BESSConfig(capacity_mwh=40.0, power_mw=20.0)
    result = hybrid_dispatch(
        800000, 0, bess, grid_limit_mw=80,
        strategy="store_excess", hours=8760,
    )
    assert result.bess_throughput_mwh >= 0


def test_wind_contribution():
    """Wind generation should add to total without clipping if under limit."""
    result = hybrid_dispatch(300000, 400000, None, grid_limit_mw=100, hours=8760)
    # 700 MW × 8760 h = 876,000 MWh capacity
    # 700,000 MWh → no clipping
    assert result.annual_clipping_mwh == 0.0
    assert result.annual_export_mwh == 700000


def test_clipping_pct_calculation():
    """Clipping percentage should be clipping / gross."""
    result = hybrid_dispatch(800000, 0, None, grid_limit_mw=80, hours=8760)
    expected_pct = result.annual_clipping_mwh / 800000
    assert abs(result.clipping_pct - expected_pct) < 0.0001
