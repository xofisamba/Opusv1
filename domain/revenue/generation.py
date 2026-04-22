"""Generation calculation - period-based production in MWh.

Matches Excel CF sheet row 21 formula:
    G21 = $B21 × G$7 × G$6 × G$20 × (1-G$19) × (1-Degradation)
    
Where:
- B21: capacity (MW)
- G7: day_fraction (period days / 365)
- G6: operation flag (1 if operating, 0 if not)
- G20: operating hours for yield scenario
- G19: curtailment assumption
- Degradation: annual degradation factor
"""
import streamlit as st
from typing import Sequence
from domain.inputs import TechnicalParams, ProjectInputs
from domain.period_engine import PeriodEngine, PeriodMeta, hash_engine_for_cache


def period_generation(
    tech: TechnicalParams,
    periods: Sequence[PeriodMeta],
    year_index: int,
    yield_scenario: str = "P50",
) -> float:
    """Calculate annual generation (sum of H1 + H2) in MWh.

    For semi-annual models, year has 2 periods. Sum both H1 and H2.

    Args:
        tech: Technical parameters
        periods: All periods (for looking up year_index)
        year_index: Year index (1-based, 1=Y1)
        yield_scenario: "P50" or "P90-10y"

    Returns:
        Generation in MWh for this year (H1 + H2)
    """
    # Find all operation periods for this year_index (H1 + H2)
    op_periods = [p for p in periods if p.is_operation and p.year_index == year_index]
    if not op_periods:
        return 0.0

    # Operating hours based on scenario
    if yield_scenario == "P90-10y":
        hours = tech.operating_hours_p90_10y
    else:
        hours = tech.operating_hours_p50

    # Combined availability (plant × grid)
    availability = tech.plant_availability * tech.grid_availability

    # Degradation factor: (1 - degradation)^(year_index - 1)
    degradation_factor = (1 - tech.pv_degradation) ** (year_index - 1)

    # Sum generation for all periods in this year (H1 + H2)
    total_generation = 0.0
    for period in op_periods:
        generation = (
            tech.capacity_mw
            * hours
            * period.day_fraction
            * availability
            * degradation_factor
        )
        total_generation += generation

    return total_generation


def annual_generation_mwh(
    tech: TechnicalParams,
    year_index: int,
    yield_scenario: str = "P50",
) -> float:
    """Calculate annual generation in MWh.
    
    Simplified version that doesn't need period engine.
    Uses P50 or P90-10y hours and assumes full year (no degradation in year 1).
    
    Args:
        tech: Technical parameters
        year_index: Year (1-based, 1=Y1)
        yield_scenario: "P50" or "P90-10y"
    
    Returns:
        Annual generation in MWh
    """
    if yield_scenario == "P90-10y":
        hours = tech.operating_hours_p90_10y
    else:
        hours = tech.operating_hours_p50
    
    availability = tech.plant_availability * tech.grid_availability
    
    # Degradation from previous years
    degradation = (1 - tech.pv_degradation) ** (year_index - 1)
    
    return tech.capacity_mw * hours * availability * degradation


def period_revenue(
    tech: TechnicalParams,
    period: PeriodMeta,
    ppa_tariff_eur_mwh: float,
    market_price_eur_mwh: float | None = None,
    ppa_active: bool = True,
) -> float:
    """Calculate revenue for a single period.
    
    Args:
        tech: Technical parameters
        period: Period metadata
        ppa_tariff_eur_mwh: PPA tariff in EUR/MWh
        market_price_eur_mwh: Market price if not PPA
        ppa_active: Whether PPA tariff applies
    
    Returns:
        Revenue in kEUR for this period
    """
    if not period.is_operation:
        return 0.0
    
    # Generation for this period
    if period.period_in_year == 1:
        # H1
        hours = tech.operating_hours_p50 if tech.yield_scenario == "P_50" else tech.operating_hours_p90_10y
    else:
        # H2 (same hours)
        hours = tech.operating_hours_p50 if tech.yield_scenario == "P_50" else tech.operating_hours_p90_10y
    
    availability = tech.plant_availability * tech.grid_availability
    degradation = (1 - tech.pv_degradation) ** (period.year_index - 1)
    
    generation_mwh = tech.capacity_mw * hours * period.day_fraction * availability * degradation
    
    # Revenue = generation × price
    if ppa_active:
        price = ppa_tariff_eur_mwh
    elif market_price_eur_mwh is not None:
        price = market_price_eur_mwh
    else:
        price = ppa_tariff_eur_mwh  # fallback
    
    revenue_keur = generation_mwh * price / 1000
    
    return revenue_keur


@st.cache_data(show_spinner=False, hash_funcs={PeriodEngine: hash_engine_for_cache})
def full_generation_schedule(
    inputs: ProjectInputs,
    engine: PeriodEngine,
    yield_scenario: str = "P50",
) -> dict[int, float]:
    """Generate full schedule of period generation in MWh.
    
    Args:
        inputs: Project inputs
        engine: Period engine
        yield_scenario: "P50" or "P90-10y"
    
    Returns:
        Dict mapping period_index → generation_MWh
    """
    schedule = {}
    
    for period in engine.periods():
        if not period.is_operation:
            schedule[period.index] = 0.0
            continue
        
        if yield_scenario == "P90-10y":
            hours = inputs.technical.operating_hours_p90_10y
        else:
            hours = inputs.technical.operating_hours_p50
        
        availability = inputs.technical.combined_availability
        degradation = (1 - inputs.technical.pv_degradation) ** (period.year_index - 1)
        
        generation = (
            inputs.technical.capacity_mw
            * hours
            * period.day_fraction
            * availability
            * degradation
        )
        
        schedule[period.index] = generation
    
    return schedule


@st.cache_data(show_spinner=False, hash_funcs={PeriodEngine: hash_engine_for_cache})
def full_revenue_schedule(
    inputs: ProjectInputs,
    engine: PeriodEngine,
) -> dict[int, float]:
    """Generate full schedule of period revenue in kEUR.
    
    Revenue includes:
    - PPA revenue (during PPA term)
    - Spot/market revenue (after PPA)
    - Balancing cost deduction (PV)
    - CO2 certificates (if enabled)
    
    Args:
        inputs: Project inputs
        engine: Period engine
    
    Returns:
        Dict mapping period_index → revenue_kEUR
    """
    revenue = {}
    
    for period in engine.periods():
        if not period.is_operation:
            revenue[period.index] = 0.0
            continue
        
        # Generation
        if inputs.technical.yield_scenario == "P_50":
            hours = inputs.technical.operating_hours_p50
        else:
            hours = inputs.technical.operating_hours_p90_10y
        
        availability = inputs.technical.combined_availability
        degradation = (1 - inputs.technical.pv_degradation) ** (period.year_index - 1)
        
        generation_mwh = (
            inputs.technical.capacity_mw
            * hours
            * period.day_fraction
            * availability
            * degradation
        )
        
        # Determine price
        if period.is_ppa_active:
            # PPA active: use tariff with PPA index
            tariff = inputs.revenue.tariff_at_year(period.year_index)
            revenue_keur = generation_mwh * tariff / 1000
        else:
            # Post-PPA: use market price
            market_price = inputs.revenue.market_price_at_year(period.year_index)
            revenue_keur = generation_mwh * market_price / 1000
        
        # Apply balancing cost deduction (PV)
        balancing_deduction = revenue_keur * inputs.revenue.balancing_cost_pv
        revenue_keur -= balancing_deduction
        
        # CO2 certificates (if enabled)
        if inputs.revenue.co2_enabled:
            co2_revenue = generation_mwh * inputs.revenue.co2_price_eur / 1000
            revenue_keur += co2_revenue
        
        revenue[period.index] = revenue_keur
    
    return revenue