"""Hybrid clipping integration test — Blueprint §6.3.

Solar 90 MWp × gross CF 0.20 = ~157,680 MWh
Grid limit 80 MW × 8760h = 700,800 MWh

Expected:
    □ Clipping > 0 (excess must go somewhere)
    □ store_excess reduces clipping by > 10% vs energy_priority
    □ Export ≤ grid_limit × 8760
"""
import pytest
from core.engines.hybrid_engine import hybrid_dispatch
from core.engines.bess_engine import BESSConfig


SOLAR_MWH = 876000.0  # 500 MWp × 1752h (gross CF 0.20) > grid limit 700,800 MWh
GRID_LIMIT_MW = 80.0
HOURS = 8760


def test_hybrid_clipping_occurs():
    """Clipping must be > 0 when solar exceeds grid limit."""
    result = hybrid_dispatch(
        solar_gen_mwh_annual=SOLAR_MWH,
        wind_gen_mwh_annual=0.0,
        bess=None,
        grid_limit_mw=GRID_LIMIT_MW,
        hours=HOURS,
    )
    assert result.annual_clipping_mwh > 0, (
        f"Expected clipping > 0, got {result.annual_clipping_mwh}"
    )
    assert result.annual_export_mwh <= GRID_LIMIT_MW * HOURS + 1


def test_store_excess_reduces_clipping():
    """store_excess strategy should reduce clipping by > 10% vs energy_priority."""
    bess = BESSConfig(capacity_mwh=40.0, power_mw=20.0)

    r_energy = hybrid_dispatch(
        SOLAR_MWH, 0, None,
        grid_limit_mw=GRID_LIMIT_MW,
        strategy="energy_priority",
        hours=HOURS,
    )
    r_store = hybrid_dispatch(
        SOLAR_MWH, 0, bess,
        grid_limit_mw=GRID_LIMIT_MW,
        strategy="store_excess",
        hours=HOURS,
    )
    reduction = (r_energy.annual_clipping_mwh - r_store.annual_clipping_mwh)
    reduction_pct = reduction / r_energy.annual_clipping_mwh
    assert reduction_pct > 0.10, (
        f"store_excess clipping reduction {reduction_pct:.1%} < 10%"
    )


def test_export_under_grid_limit():
    """Export must never exceed grid capacity."""
    result = hybrid_dispatch(
        SOLAR_MWH, 0, None,
        grid_limit_mw=GRID_LIMIT_MW,
        hours=HOURS,
    )
    assert result.annual_export_mwh <= GRID_LIMIT_MW * HOURS


def test_grid_utilization_above_zero():
    """Grid utilization should be a meaningful fraction."""
    result = hybrid_dispatch(
        SOLAR_MWH, 0, None,
        grid_limit_mw=GRID_LIMIT_MW,
        hours=HOURS,
    )
    assert 0 < result.grid_utilization_pct <= 1.0


def test_bess_store_excess_records_throughput():
    """store_excess should record positive BESS throughput."""
    bess = BESSConfig(capacity_mwh=40.0, power_mw=20.0)
    result = hybrid_dispatch(
        SOLAR_MWH, 0, bess,
        grid_limit_mw=GRID_LIMIT_MW,
        strategy="store_excess",
        hours=HOURS,
    )
    assert result.bess_throughput_mwh > 0
