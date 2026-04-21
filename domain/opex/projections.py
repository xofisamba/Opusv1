"""OPEX projections - per-year and per-period operational costs.

Matches Excel Inputs rows 146-161 (15 OPEX categories).
Each item has:
- Y1 amount in kEUR
- Annual escalation (2% for most, 0% for some)
- Step changes at specific years (e.g., Infrastructure Maintenance Y3: 185.64)

Total Y1 OPEX for Oborovo: 1,353.91 kEUR
"""
import streamlit as st
from typing import Sequence
from domain.inputs import OpexItem, ProjectInputs
from domain.period_engine import PeriodEngine, PeriodMeta


def _hash_engine(e: PeriodEngine) -> tuple:
    return (e.fc, e.construction_months, e.horizon_years, e.ppa_years, e.freq)


def opex_year(
    items: Sequence[OpexItem],
    year_index: int,
) -> float:
    """Calculate total OPEX for a given year.
    
    Args:
        items: Sequence of OpexItems
        year_index: Year index (1-based, 1=Y1)
    
    Returns:
        Total OPEX in kEUR for this year
    """
    return sum(item.amount_at_year(year_index) for item in items)


@st.cache_data(show_spinner=False)
def opex_schedule_annual(
    inputs: ProjectInputs,
    horizon_years: int = 30,
) -> dict[int, float]:
    """Generate annual OPEX schedule.
    
    Args:
        inputs: Project inputs
        horizon_years: Number of years to project
    
    Returns:
        Dict mapping year_index → OPEX in kEUR
    """
    schedule = {}
    
    for year in range(1, horizon_years + 1):
        schedule[year] = opex_year(inputs.opex, year)
    
    return schedule


def opex_per_mw_y1(
    inputs: ProjectInputs,
) -> float:
    """Calculate OPEX per MW (Y1) in kEUR/MW.
    
    Args:
        inputs: Project inputs
    
    Returns:
        OPEX per MW in kEUR/MW
    """
    opex_y1 = opex_year(inputs.opex, 1)
    return opex_y1 / inputs.technical.capacity_mw


def opex_per_mwh_y1(
    inputs: ProjectInputs,
) -> float:
    """Calculate OPEX per MWh (Y1) in EUR/MWh.
    
    Args:
        inputs: Project inputs
    
    Returns:
        OPEX per MWh in EUR/MWh
    """
    opex_y1 = opex_year(inputs.opex, 1)
    
    # Generation Y1 in MWh
    hours = inputs.technical.operating_hours_p50
    availability = inputs.technical.combined_availability
    generation_y1_mwh = inputs.technical.capacity_mw * hours * availability
    
    # EUR/MWh = kEUR / MWh × 1000
    return (opex_y1 * 1000) / generation_y1_mwh


@st.cache_data(show_spinner=False, hash_funcs={PeriodEngine: _hash_engine})
def opex_schedule_period(
    inputs: ProjectInputs,
    engine: PeriodEngine,
) -> dict[int, float]:
    """Generate semi-annual period OPEX schedule.
    
    OPEX is typically annual, but in semi-annual model it's split:
    - H1: 50% of annual
    - H2: 50% of annual
    
    Args:
        inputs: Project inputs
        engine: Period engine
    
    Returns:
        Dict mapping period_index → OPEX in kEUR
    """
    schedule = {}
    annual_schedule = opex_schedule_annual(inputs, inputs.info.horizon_years)
    
    for period in engine.periods():
        if not period.is_operation:
            schedule[period.index] = 0.0
            continue
        
        # Annual OPEX for this year
        annual_opex = annual_schedule.get(period.year_index, 0.0)
        
        # Split semi-annually (50/50 for simplicity)
        # Some items may have different patterns but 50/50 is standard
        if period.period_in_year == 1:
            # H1: 50% of annual
            schedule[period.index] = annual_opex * 0.5
        else:
            # H2: 50% of annual
            schedule[period.index] = annual_opex * 0.5
    
    return schedule


def opex_breakdown_year(
    inputs: ProjectInputs,
    year_index: int,
) -> dict[str, float]:
    """Get breakdown of OPEX by category for a given year.
    
    Args:
        inputs: Project inputs
        year_index: Year index (1-based)
    
    Returns:
        Dict mapping item name → amount in kEUR
    """
    return {item.name: item.amount_at_year(year_index) for item in inputs.opex}


def total_opex_over_horizon(
    inputs: ProjectInputs,
    horizon_years: int = 30,
    discount_rate: float = 0.0,
) -> float:
    """Calculate total (optionally discounted) OPEX over horizon.
    
    Args:
        inputs: Project inputs
        horizon_years: Number of years
        discount_rate: Discount rate (0 for undiscounted)
    
    Returns:
        Total OPEX in kEUR (undiscounted or discounted)
    """
    total = 0.0
    
    for year in range(1, horizon_years + 1):
        annual_opex = opex_year(inputs.opex, year)
        
        if discount_rate > 0:
            annual_opex /= (1 + discount_rate) ** (year - 1)
        
        total += annual_opex
    
    return total


def opex_growth_rate(
    inputs: ProjectInputs,
    start_year: int = 1,
    end_year: int = 30,
) -> float:
    """Calculate average annual OPEX growth rate.
    
    Args:
        inputs: Project inputs
        start_year: Starting year (1-based)
        end_year: Ending year (1-based)
    
    Returns:
        Average annual growth rate (e.g., 0.018 for 1.8%)
    """
    opex_start = opex_year(inputs.opex, start_year)
    opex_end = opex_year(inputs.opex, end_year)
    
    if opex_start <= 0:
        return 0.0
    
    years = end_year - start_year
    if years <= 0:
        return 0.0
    
    return (opex_end / opex_start) ** (1 / years) - 1