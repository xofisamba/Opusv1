"""Hybrid Engine — OpusCore v2 Phase 1 Task 1.8.

Grid limit enforcement and dispatch for hybrid (Solar+Wind+BESS) projects.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class HybridDispatchResult:
    """Result of hybrid dispatch optimization."""
    annual_export_mwh: float
    annual_clipping_mwh: float
    clipping_pct: float
    bess_throughput_mwh: float
    grid_utilization_pct: float


def hybrid_dispatch(
    solar_gen_mwh_annual: float,
    wind_gen_mwh_annual: float,
    bess,  # BESSConfig | None — avoid circular import
    grid_limit_mw: float,
    capacity_factor_solar: float = 0.20,
    capacity_factor_wind: float = 0.35,
    strategy: str = "energy_priority",
    hours: int = 8760,
) -> HybridDispatchResult:
    """Simplified annual hybrid dispatch — no hourly simulation.

    Uses capacity factor to estimate peak hours.

    Strategies:
        energy_priority: Solar/wind have dispatch priority, BESS fills excess
        store_excess: Clipping goes to BESS, reduces total clipping

    Args:
        solar_gen_mwh_annual: Annual solar generation (MWh)
        wind_gen_mwh_annual: Annual wind generation (MWh)
        bess: BESSConfig or None
        grid_limit_mw: Grid export limit (MW)
        capacity_factor_solar: Solar capacity factor (default 0.20)
        capacity_factor_wind: Wind capacity factor (default 0.35)
        strategy: "energy_priority" or "store_excess"
        hours: Hours per year (default 8760)

    Returns:
        HybridDispatchResult with export, clipping, and BESS metrics.
    """
    gross_mwh = solar_gen_mwh_annual + wind_gen_mwh_annual
    grid_capacity_mwh = grid_limit_mw * hours

    if gross_mwh <= grid_capacity_mwh:
        return HybridDispatchResult(
            annual_export_mwh=gross_mwh,
            annual_clipping_mwh=0.0,
            clipping_pct=0.0,
            bess_throughput_mwh=0.0,
            grid_utilization_pct=(
                gross_mwh / grid_capacity_mwh if grid_capacity_mwh > 0 else 0
            ),
        )

    raw_clipping = gross_mwh - grid_capacity_mwh

    if strategy == "store_excess" and bess is not None:
        # BESS absorbs portion of clipping
        bess_usable = (
            bess.capacity_mwh
            * (bess.soc_max_pct - bess.soc_min_pct)
        )
        # Annual storage capacity (limited by cycle count)
        bess_annual_storage = min(
            raw_clipping,
            bess.cycle_limit_per_day * 365 * bess.capacity_mwh,
        )
        clipping = max(0.0, raw_clipping - bess_annual_storage)
        bess_throughput = bess_annual_storage * bess.roundtrip_efficiency
    else:
        clipping = raw_clipping
        bess_throughput = 0.0

    export = gross_mwh - clipping
    export = min(export, grid_capacity_mwh)

    return HybridDispatchResult(
        annual_export_mwh=export,
        annual_clipping_mwh=clipping,
        clipping_pct=clipping / gross_mwh if gross_mwh > 0 else 0.0,
        bess_throughput_mwh=bess_throughput,
        grid_utilization_pct=export / grid_capacity_mwh if grid_capacity_mwh > 0 else 0.0,
    )
