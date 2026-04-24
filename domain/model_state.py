"""Model state - pre-computed schedules shared across all UI pages.

This module provides cached computation of expensive model outputs
(revenue, generation, OPEX) that are used by multiple UI pages.

NOTE: This module uses @st.cache_data but is called from the app layer.
The actual caching happens in the UI layer, not here.
"""
from dataclasses import dataclass
from typing import Optional

from domain.inputs import ProjectInputs, PeriodFrequency
from domain.period_engine import PeriodEngine


@dataclass(frozen=True)
class ModelState:
    """Pre-computed schedules shared across all UI pages."""
    revenue: dict[int, float]
    generation: dict[int, float]
    opex_annual: dict[int, float]
    periods: list
    op_periods: list
    depreciation_schedule: list[float]


def build_model_state(inputs: ProjectInputs, engine: PeriodEngine) -> ModelState:
    """Build model state with all precomputed schedules.

    This function is decorated with @st.cache_data in the UI layer.
    Call it once per inputs/engine change.
    
    Args:
        inputs: ProjectInputs instance
        engine: PeriodEngine instance
    
    Returns:
        ModelState with all precomputed schedules
    """
    # Revenue schedule
    from domain.revenue.generation import full_revenue_schedule
    revenue = full_revenue_schedule(inputs, engine)

    # Generation schedule
    from domain.revenue.generation import full_generation_schedule
    generation = full_generation_schedule(inputs, engine)

    # OPEX annual
    from domain.opex.projections import opex_schedule_annual
    opex_annual = opex_schedule_annual(inputs, inputs.info.horizon_years)

    # Build periods list
    periods = list(engine.periods())
    op_periods = [p for p in periods if p.is_operation]

    # Depreciation schedule
    total_capex = inputs.capex.total_capex
    horizon = inputs.info.horizon_years
    dep_per_year = total_capex / horizon if horizon > 0 else 0.0

    depreciation_schedule = []
    for p in periods:
        if p.is_operation:
            depreciation_schedule.append(dep_per_year / 2)  # Semi-annual
        else:
            depreciation_schedule.append(0.0)

    return ModelState(
        revenue=revenue,
        generation=generation,
        opex_annual=opex_annual,
        periods=periods,
        op_periods=op_periods,
        depreciation_schedule=depreciation_schedule,
    )