"""BESS Engine — OpusCore v2 Phase 1 Task 1.4.

Linear programming dispatch for battery energy storage system (BESS) arbitrage.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BESSConfig:
    """Battery energy storage system configuration."""
    capacity_mwh: float          # Usable energy capacity (MWh)
    power_mw: float             # Power rating (MW)
    roundtrip_efficiency: float = 0.88
    soc_min_pct: float = 0.10   # Minimum state of charge
    soc_max_pct: float = 0.90   # Maximum state of charge
    cycle_limit_per_day: float = 1.5
    calendar_degradation_pct: float = 0.015
    cycle_degradation_per_cycle: float = 0.00003


@dataclass
class BESSDispatchResult:
    """Result of BESS arbitrage dispatch optimization."""
    annual_throughput_mwh: float
    annual_cycles: float
    avg_charge_price: float
    avg_discharge_price: float
    arbitrage_revenue_keur: float
    hourly_dispatch: list[float]   # positive=discharge, negative=charge
    hourly_soc: list[float]


def optimize_dispatch_arbitrage(
    price_curve: list[float],
    bess: BESSConfig,
    initial_soc_pct: float = 0.50,
) -> BESSDispatchResult:
    """LP arbitrage dispatch for one week (168 hours).

    Variables (2×168):
        x[0:168]   = p_charge[h] ≥ 0 (MW)
        x[168:336] = p_discharge[h] ≥ 0 (MW)

    Objective (cost minimization):
        min Σ_h ( price[h]*charge[h]/η_c - price[h]*discharge[h]*η_d )

    Constraints:
        - SOC equation: cumulative balance stays in [soc_min, soc_max]
        - 0 ≤ charge[h] ≤ power_mw
        - 0 ≤ discharge[h] ≤ power_mw
        - Weekly cycles ≤ cycle_limit × 7

    Args:
        price_curve: 168 hourly prices (EUR/MWh)
        bess: BESS configuration
        initial_soc_pct: Initial state of charge (default 50%)

    Returns:
        BESSDispatchResult with dispatch schedule and economics.
    """
    n = len(price_curve)  # 168
    eta = math.sqrt(bess.roundtrip_efficiency)
    eta_c = eta
    eta_d = eta
    soc_min = bess.capacity_mwh * bess.soc_min_pct
    soc_max = bess.capacity_mwh * bess.soc_max_pct
    initial_soc = bess.capacity_mwh * initial_soc_pct

    # Objective: min Σ price*charge/eta_c - price*discharge*eta_d
    c_charge = [p / eta_c for p in price_curve]
    c_discharge = [-p * eta_d for p in price_curve]
    c = c_charge + c_discharge

    # Bounds: 0 ≤ charge, discharge ≤ power_mw
    bounds = ([(0.0, bess.power_mw)] * n) + ([(0.0, bess.power_mw)] * n)

    # SOC constraints: cumulative balance stays within [soc_min, soc_max]
    A_ub = []
    b_ub = []
    for h in range(n):
        # Upper bound: cumsum ≤ soc_max - initial_soc
        row = [0.0] * (2 * n)
        for t in range(h + 1):
            row[t] = eta_c          # charge contributes
            row[n + t] = -1 / eta_d  # discharge depletes
        A_ub.append(row)
        b_ub.append(soc_max - initial_soc)

        # Lower bound: -cumsum ≤ -(soc_min - initial_soc)
        row_lb = [-x for x in row]
        A_ub.append(row_lb)
        b_ub.append(-(soc_min - initial_soc))

    # Weekly cycle limit: Σ discharge ≤ cycle_limit × 7 × capacity
    row_cycle = [0.0] * n + [1.0] * n
    A_ub.append(row_cycle)
    b_ub.append(bess.cycle_limit_per_day * 7 * bess.capacity_mwh)

    from scipy.optimize import linprog
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')

    if result.status != 0:
        # Fallback: zero dispatch
        return BESSDispatchResult(
            annual_throughput_mwh=0.0,
            annual_cycles=0.0,
            avg_charge_price=0.0,
            avg_discharge_price=0.0,
            arbitrage_revenue_keur=0.0,
            hourly_dispatch=[0.0] * n,
            hourly_soc=[initial_soc] * n,
        )

    charge = result.x[:n]
    discharge = result.x[n:]

    # Reconstruct SOC trajectory
    soc = []
    s = initial_soc
    for h in range(n):
        s += charge[h] * eta_c - discharge[h] / eta_d
        s = max(soc_min, min(soc_max, s))
        soc.append(s)

    dispatch = [discharge[h] - charge[h] for h in range(n)]
    throughput_week = sum(discharge)
    annual_throughput = throughput_week * 52
    annual_cycles = annual_throughput / bess.capacity_mwh

    # Revenue
    weekly_revenue = sum(
        price_curve[h] * discharge[h] * eta_d
        - price_curve[h] * charge[h] / eta_c
        for h in range(n)
    )
    annual_revenue_keur = weekly_revenue * 52 / 1000

    charge_vol = sum(charge)
    discharge_vol = sum(discharge)
    avg_charge = (
        sum(price_curve[h] * charge[h] for h in range(n)) / charge_vol
        if charge_vol > 0 else 0.0
    )
    avg_discharge = (
        sum(price_curve[h] * discharge[h] for h in range(n)) / discharge_vol
        if discharge_vol > 0 else 0.0
    )

    return BESSDispatchResult(
        annual_throughput_mwh=annual_throughput,
        annual_cycles=annual_cycles,
        avg_charge_price=avg_charge,
        avg_discharge_price=avg_discharge,
        arbitrage_revenue_keur=annual_revenue_keur,
        hourly_dispatch=list(dispatch),
        hourly_soc=list(soc),
    )


def bess_degradation_schedule(
    bess: BESSConfig,
    annual_throughput_mwh: float,
    horizon_years: int,
) -> list[float]:
    """SoH schedule accounting for calendar and cycle degradation.

    SoH[t] = SoH[t-1]
        - calendar_degradation_pct
        - (annual_throughput / capacity_mwh) × cycle_degradation_per_cycle

    Args:
        bess: BESS configuration
        annual_throughput_mwh: Year 1 annual throughput (MWh)
        horizon_years: Investment horizon (years)

    Returns:
        List of SoH values for years 1..N (converges in ~5 iterations).
    """
    soh = [1.0]
    throughput = annual_throughput_mwh
    for _ in range(horizon_years):
        cycle_deg = (
            (throughput / bess.capacity_mwh)
            * bess.cycle_degradation_per_cycle
        )
        new_soh = max(
            0.0,
            soh[-1] - bess.calendar_degradation_pct - cycle_deg,
        )
        soh.append(new_soh)
        # Throughput scales with SoH
        throughput = annual_throughput_mwh * new_soh
    return soh[1:]  # Year 1..N
