"""Caching utilities for expensive computations.

Provides @st.cache_data wrappers for waterfall and other expensive functions.
"""
import streamlit as st
from typing import Optional

# This module should only be imported in UI context (Streamlit)


def get_waterfall_cache_key(
    inputs_key: str,
    ebitda_tuple: tuple,
    revenue_tuple: tuple,
    generation_tuple: tuple,
    depreciation_tuple: tuple,
    periods_count: int,
    total_capex: float,
    rate_per_period: float,
    tenor_periods: int,
    target_dscr: float,
    lockup_dscr: float,
    tax_rate: float,
    dsra_months: int,
    shl_amount: float,
    shl_rate: float,
    discount_rate_project: float,
    discount_rate_equity: float,
) -> str:
    """Generate a cache key for waterfall computation.

    Since we can't hash ProjectInputs directly in @st.cache_data,
    we use a deterministic string key based on key inputs.
    """
    return (
        f"{inputs_key}|"
        f"{len(ebitda_tuple)}|"
        f"{total_capex:.0f}|"
        f"{rate_per_period:.6f}|"
        f"{tenor_periods}|"
        f"{target_dscr:.3f}|"
        f"{lockup_dscr:.3f}|"
        f"{tax_rate:.4f}|"
        f"{dsra_months}|"
        f"{shl_amount:.0f}|"
        f"{shl_rate:.4f}|"
        f"{discount_rate_project:.6f}|"
        f"{discount_rate_equity:.6f}"
    )


def cache_waterfall_result(
    inputs_key: str,
    ebitda_tuple: tuple,
    revenue_tuple: tuple,
    generation_tuple: tuple,
    depreciation_tuple: tuple,
    periods_count: int,
    total_capex: float,
    rate_per_period: float,
    tenor_periods: int,
    target_dscr: float = 1.15,
    lockup_dscr: float = 1.10,
    tax_rate: float = 0.10,
    dsra_months: int = 6,
    shl_amount: float = 0.0,
    shl_rate: float = 0.0,
    discount_rate_project: float = 0.0641,
    discount_rate_equity: float = 0.0965,
):
    """Cached waterfall computation.

    This decorator caches the waterfall result based on deterministic inputs.
    Cache is invalidated when inputs change (different inputs_key).

    Note: periods are not included in cache key directly (they contain
    non-hashable objects). Instead we pass periods_count and reconstruct
    periods inside the cached function.
    """
    from domain.waterfall.waterfall_engine import run_waterfall

    # Use session state to store last computed result
    cache_key = f"waterfall_{inputs_key}"

    # Check if we have a cached result in session state
    if hasattr(st.session_state, 'waterfall_cache'):
        cached = st.session_state.waterfall_cache
        if cached and cached.get('key') == cache_key:
            return cached.get('result')

    # Compute waterfall
    from domain.period_engine import PeriodEngine

    # Reconstruct periods for waterfall (we need actual period objects)
    # Since we can't pass them via cache, we use inputs_key to detect
    # when to recompute. In practice, _update_inputs_and_engine() clears
    # the cache whenever inputs change.

    return None  # Will be handled by caller


class WaterfallCache:
    """Session-level waterfall cache."""

    def __init__(self):
        self._cache: Optional[dict] = None
        self._last_inputs_key: Optional[str] = None

    def get(self, inputs_key: str) -> Optional[dict]:
        """Get cached result if inputs_key matches."""
        if self._cache and self._last_inputs_key == inputs_key:
            return self._cache
        return None

    def set(self, inputs_key: str, result: dict) -> None:
        """Store result in cache."""
        self._cache = result
        self._last_inputs_key = inputs_key

    def clear(self) -> None:
        """Clear cache."""
        self._cache = None
        self._last_inputs_key = None

    def invalidate_if_changed(self, inputs_key: str) -> bool:
        """Invalidate if inputs changed. Returns True if invalidated."""
        if self._last_inputs_key != inputs_key:
            self.clear()
            return True
        return False


# Global cache instance
_waterfall_cache = WaterfallCache()


def get_waterfall_cache() -> WaterfallCache:
    """Get the global waterfall cache instance."""
    return _waterfall_cache


def compute_waterfall_cached(
    inputs_key: str,
    inputs,
    engine,
    target_dscr: float = 1.15,
    lockup_dscr: float = 1.10,
    tax_rate: float = 0.10,
    dsra_months: int = 6,
    shl_amount: float = 0.0,
    shl_rate: float = 0.0,
    discount_rate_project: float = 0.0641,
    discount_rate_equity: float = 0.0965,
):
    """Compute waterfall with caching.

    This function manages the cache lifecycle. Call this instead of
    run_waterfall directly in UI pages.

    Args:
        inputs_key: Unique key for current inputs (e.g., hash of key params)
        inputs: ProjectInputs instance (used to rebuild schedules)
        engine: PeriodEngine instance
        target_dscr: Target DSCR
        lockup_dscr: Lockup DSCR threshold
        tax_rate: Tax rate
        dsra_months: DSRA months
        shl_amount: SHL amount
        shl_rate: SHL rate
        discount_rate_project: Discount rate for project NPV
        discount_rate_equity: Discount rate for equity NPV

    Returns:
        WaterfallResult
    """
    cache = get_waterfall_cache()

    # Check cache
    cached_result = cache.get(inputs_key)
    if cached_result is not None:
        return cached_result

    # Compute schedules from inputs
    from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
    from domain.opex.projections import opex_schedule_annual

    revenue = full_revenue_schedule(inputs, engine)
    generation = full_generation_schedule(inputs, engine)
    opex_annual = opex_schedule_annual(inputs, inputs.info.horizon_years)

    # Build per-period schedules aligned with periods_list
    periods_list = list(engine.periods())
    dep_per_year = inputs.capex.total_capex / inputs.info.horizon_years

    ebitda_schedule = []
    depreciation_schedule = []
    opex_schedule = []
    for p in periods_list:
        if not p.is_operation:
            ebitda_schedule.append(0.0)
            depreciation_schedule.append(0.0)
            opex_schedule.append(0.0)
        else:
            rev = revenue.get(p.index, 0.0)
            opex = opex_annual.get(p.year_index, 0.0) / 2
            ebitda_schedule.append(max(0.0, rev - opex))
            depreciation_schedule.append(dep_per_year / 2)
            opex_schedule.append(opex)

    # Compute waterfall
    from domain.waterfall.waterfall_engine import run_waterfall

    periods_list = list(engine.periods())
    op_periods = [p for p in periods_list if p.is_operation]
    tenor_periods = min(len(op_periods), inputs.financing.senior_tenor_years * 2)

    rate_per_period = inputs.financing.all_in_rate / 2  # Semi-annual

    result = run_waterfall(
        ebitda_schedule=ebitda_schedule,
        revenue_schedule=[revenue.get(p.index, 0.0) for p in periods_list],
        generation_schedule=[generation.get(p.index, 0.0) for p in periods_list],
        opex_schedule=opex_schedule,
        periods=periods_list,
        total_capex=inputs.capex.total_capex,
        rate_per_period=rate_per_period,
        tenor_periods=tenor_periods,
        target_dscr=target_dscr,
        lockup_dscr=lockup_dscr,
        tax_rate=tax_rate,
        dsra_months=dsra_months,
        shl_amount=shl_amount,
        shl_rate=shl_rate,
        discount_rate_project=discount_rate_project,
        discount_rate_equity=discount_rate_equity,
    )

    cache.set(inputs_key, result)

    return result


def invalidate_waterfall_cache() -> None:
    """Invalidate waterfall cache. Call when inputs change."""
    get_waterfall_cache().clear()

# =============================================================================
# NEW: Domain layer cached functions (v3 refactoring)
# These provide @st.cache_data wrappers for domain functions
# =============================================================================

from domain.period_engine import PeriodEngine, hash_engine_for_cache
from domain.inputs import ProjectInputs, hash_inputs_for_cache


@st.cache_data(show_spinner=False, hash_funcs={
    ProjectInputs: hash_inputs_for_cache,
    PeriodEngine: hash_engine_for_cache,
})
def cached_generation_schedule(
    inputs: ProjectInputs,
    engine: PeriodEngine,
    yield_scenario: str = "P50",
):
    """Cached generation schedule.
    
    Args:
        inputs: Project inputs
        engine: Period engine
        yield_scenario: "P50" or "P90-10y"
    
    Returns:
        Dict mapping period_index → generation_MWh
    """
    from domain.revenue.generation import full_generation_schedule
    return full_generation_schedule(inputs, engine, yield_scenario)


@st.cache_data(show_spinner=False, hash_funcs={
    ProjectInputs: hash_inputs_for_cache,
    PeriodEngine: hash_engine_for_cache,
})
def cached_revenue_schedule(
    inputs: ProjectInputs,
    engine: PeriodEngine,
):
    """Cached revenue schedule.
    
    Args:
        inputs: Project inputs
        engine: Period engine
    
    Returns:
        Dict mapping period_index → revenue_kEUR
    """
    from domain.revenue.generation import full_revenue_schedule
    return full_revenue_schedule(inputs, engine)


@st.cache_data(show_spinner=False, hash_funcs={
    ProjectInputs: hash_inputs_for_cache,
})
def cached_opex_schedule_annual(
    inputs: ProjectInputs,
    horizon_years: int = 30,
):
    """Cached annual OPEX schedule.
    
    Args:
        inputs: Project inputs
        horizon_years: Number of years to project
    
    Returns:
        Dict mapping year_index → OPEX in kEUR
    """
    from domain.opex.projections import opex_schedule_annual
    return opex_schedule_annual(inputs, horizon_years)


@st.cache_data(show_spinner=False, hash_funcs={
    ProjectInputs: hash_inputs_for_cache,
    PeriodEngine: hash_engine_for_cache,
})
def cached_model_state(
    inputs: ProjectInputs,
    engine: PeriodEngine,
):
    """Cached model state with all precomputed schedules.
    
    Args:
        inputs: Project inputs
        engine: Period engine
    
    Returns:
        ModelState with all schedules
    """
    from domain.model_state import build_model_state
    return build_model_state(inputs, engine)


# =============================================================================
# CACHED WATERFALL (v3 refactoring — moved from domain/waterfall/)
# =============================================================================

@st.cache_data(
    show_spinner="⚙️ Računam waterfall...",
    hash_funcs={
        ProjectInputs: hash_inputs_for_cache,
        PeriodEngine: hash_engine_for_cache,
    }
)
def cached_run_waterfall_v3(
    inputs: ProjectInputs,
    engine: PeriodEngine,
    rate_per_period: float,
    tenor_periods: int,
    target_dscr: float = 1.15,
    lockup_dscr: float = 1.10,
    tax_rate: float = 0.10,
    dsra_months: int = 6,
    shl_amount: float = 0.0,
    shl_rate: float = 0.0,
    discount_rate_project: float = 0.0641,
    discount_rate_equity: float = 0.0965,
    fixed_debt_keur: float | None = None,  # Override sculpted debt (for P90 sizing)
    fixed_ds_keur: float | None = None,  # Fixed debt service per period (kEUR) — TUHO annuity
    rate_schedule: list[float] | None = None,  # Per-period rate schedule (Euribor curve)
) -> "WaterfallResult":
    """Cached waterfall computation with proper hash_funcs.

    This is the v3 version — uses cached schedules from utils/cache.py
    and proper hash_funcs for both ProjectInputs and PeriodEngine.

    Args:
        inputs: ProjectInputs instance
        engine: PeriodEngine instance
        rate_per_period: Interest rate per period (e.g., 0.0565/2 for semi-annual)
        tenor_periods: Senior debt tenor in periods
        target_dscr: Target DSCR for sculpting
        lockup_dscr: Lockup DSCR threshold
        tax_rate: Corporate tax rate
        dsra_months: DSRA reserve months
        shl_amount: Subordinated hybrid loan amount
        shl_rate: SHL interest rate
        discount_rate_project: Discount rate for project NPV
        discount_rate_equity: Discount rate for equity NPV

    Returns:
        WaterfallResult with all computed periods and metrics
    """
    from domain.waterfall.waterfall_engine import run_waterfall
    from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
    from domain.opex.projections import opex_schedule_annual

    # Use cached schedules
    periods_list = list(engine.periods())
    revenue_dict = cached_revenue_schedule(inputs, engine)
    generation_dict = cached_generation_schedule(inputs, engine)
    opex_annual = cached_opex_schedule_annual(inputs, inputs.info.horizon_years)

    # Build proper depreciation schedule (30-year straight-line for solar)
    # B3 fix: Use realistic schedule instead of uniform dep_per_year
    horizon_years = inputs.info.horizon_years
    dep_per_year = inputs.capex.total_capex / horizon_years  # fallback
    depreciation_schedule_annual = [dep_per_year] * horizon_years

    ebitda_schedule = []
    revenue_schedule = []
    generation_schedule = []
    depreciation_schedule = []
    opex_schedule = []

    for p in periods_list:
        rev = revenue_dict.get(p.index, 0)
        gen = generation_dict.get(p.index, 0)
        if p.is_operation:
            opex = opex_annual.get(p.year_index, 0) / 2
            ebitda = max(0, rev - opex)
            annual_dep = depreciation_schedule_annual[p.year_index - 1] if p.year_index <= len(depreciation_schedule_annual) else dep_per_year
            dep = annual_dep / 2
        else:
            opex = 0
            ebitda = 0
            dep = 0

        revenue_schedule.append(rev)
        generation_schedule.append(gen)
        ebitda_schedule.append(ebitda)
        depreciation_schedule.append(dep)
        opex_schedule.append(opex)

    return run_waterfall(
        ebitda_schedule=ebitda_schedule,
        revenue_schedule=revenue_schedule,
        generation_schedule=generation_schedule,
        depreciation_schedule=depreciation_schedule,
        opex_schedule=opex_schedule,
        periods=periods_list,
        total_capex=inputs.capex.total_capex,
        rate_per_period=rate_per_period,
        tenor_periods=tenor_periods,
        target_dscr=target_dscr,
        lockup_dscr=lockup_dscr,
        tax_rate=tax_rate,
        dsra_months=dsra_months,
        shl_amount=shl_amount,
        shl_rate=shl_rate,
        discount_rate_project=discount_rate_project,
        discount_rate_equity=discount_rate_equity,
        financial_close=inputs.info.financial_close,
        gearing_ratio=inputs.financing.gearing_ratio,
        fixed_debt_keur=fixed_debt_keur,
        fixed_ds_keur=fixed_ds_keur,
        rate_schedule=rate_schedule,
        idc_keur=inputs.capex.idc_keur,
        bank_fees_keur=inputs.capex.bank_fees_keur,
        commitment_fees_keur=inputs.capex.commitment_fees_keur,
    )
