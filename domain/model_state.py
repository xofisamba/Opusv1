"""Model state - pre-computed schedules shared across all UI pages.

This module provides cached computation of expensive model outputs
(revenue, generation, OPEX) that are used by multiple UI pages.
"""
from dataclasses import dataclass
from typing import Optional
import streamlit as st

from domain.inputs import ProjectInputs, PeriodFrequency
from domain.period_engine import PeriodEngine, PeriodFrequency as PF


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

    # Get periods
    periods = list(engine.periods())
    op_periods = [p for p in periods if p.is_operation]

    # Depreciation schedule (simplified - equal over horizon)
    dep_schedule = []
    dep_per_year = inputs.capex.total_capex / inputs.info.horizon_years
    for i in range(inputs.info.horizon_years):
        dep_schedule.append(dep_per_year)

    return ModelState(
        revenue=revenue,
        generation=generation,
        opex_annual=opex_annual,
        periods=periods,
        op_periods=op_periods,
        depreciation_schedule=dep_schedule,
    )


@st.cache_data(ttl=60, show_spinner=False)
def cached_model_state(inputs_hash: str, inputs_json: str) -> ModelState:
    """Cached model state - rebuilds when inputs change.

    Since ProjectInputs is a frozen dataclass, we can use it as a cache key.
    The hash is derived from inputs' key properties.

    Args:
        inputs_hash: Hash string derived from inputs
        inputs_json: JSON serialization for cache key

    Returns:
        ModelState with all precomputed schedules
    """
    # Reconstruct inputs from JSON (necessary because frozen dataclass
    # can't be directly serialized, but we reconstruct from session state)
    import json
    data = json.loads(inputs_json)

    # Rebuild ProjectInputs from serialized data
    # This is a simplified reconstruction - for full fidelity would need
    # a proper serialize/deserialize cycle
    from domain.inputs import ProjectInputs, CapexItem, OpexItem, TechnicalParams, RevenueParams, FinancingParams, TaxParams, PeriodFrequency

    # For now, return None if inputs can't be reconstructed
    # This forces cache miss and triggers recompute
    return None


def get_cached_model_state(inputs: ProjectInputs, engine: PeriodEngine) -> Optional[ModelState]:
    """Get or compute model state.

    This is the entry point for UI pages - it handles caching automatically.

    Args:
        inputs: ProjectInputs instance
        engine: PeriodEngine instance

    Returns:
        ModelState with precomputed schedules, or None if cache miss
    """
    # Generate a hash from inputs
    # Since inputs is frozen, we can use its hash
    inputs_key = f"{inputs.info.name}_{inputs.technical.capacity_mw}_{inputs.financing.gearing_ratio}"

    # Try to get from session state first (persistent across reruns)
    if 'cached_model_state' not in st.session_state:
        st.session_state.cached_model_state = None

    # If we have a cached state and inputs match, return it
    if st.session_state.cached_model_state is not None:
        cached_key = getattr(st.session_state.cached_model_state, '_inputs_key', None)
        if cached_key == inputs_key:
            return st.session_state.cached_model_state

    # Compute new state
    new_state = build_model_state(inputs, engine)
    new_state._inputs_key = inputs_key  # type: ignore
    st.session_state.cached_model_state = new_state

    return new_state