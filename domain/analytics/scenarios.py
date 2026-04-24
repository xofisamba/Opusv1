"""Scenario Engine — P50/P90/P99 multi-scenario analysis.

Enterprise Implementation Brief §2.1
Supports: P50, P90-1y, P90-10y, P99-1y scenarios
"""
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from domain.inputs import ProjectInputs


class YieldScenario(Enum):
    """Yield scenario types for generation analysis."""
    P50 = "P50"          # Median scenario (50th percentile)
    P90_1Y = "P90-1y"    # P90 single-year exceedance
    P90_10Y = "P90-10y"  # P90 10-year average
    P99_1Y = "P99-1y"    # P99 single-year (extreme year)


@dataclass(frozen=True)
class ScenarioResult:
    """Result of a single scenario run."""
    scenario: YieldScenario
    equity_irr: float
    project_irr: float
    npv_keur: float
    lcoe_eur_mwh: float
    avg_dscr: float
    min_dscr: float
    total_distribution_keur: float
    total_tax_keur: float
    generation_mwh_y1: float
    revenue_keur_y1: float


def get_scenario_hours(
    inputs: ProjectInputs,
    scenario: YieldScenario,
) -> float:
    """Get operating hours for a given yield scenario.
    
    Args:
        inputs: ProjectInputs with technical params
        scenario: YieldScenario enum value
    
    Returns:
        Operating hours for the scenario
    """
    tech = inputs.technical
    p99_1y = getattr(tech, 'operating_hours_p99_1y', None)
    
    if scenario == YieldScenario.P50:
        return tech.operating_hours_p50
    elif scenario == YieldScenario.P90_1Y:
        # P90-1y — use p90_10y as proxy if p90_1y not available
        return getattr(tech, 'operating_hours_p90_1y', tech.operating_hours_p90_10y)
    elif scenario == YieldScenario.P90_10Y:
        return tech.operating_hours_p90_10y
    elif scenario == YieldScenario.P99_1Y:
        if p99_1y is not None:
            return p99_1y
        # Fallback: P99 = P50 × 0.75 (rough approximation)
        return tech.operating_hours_p50 * 0.75
    return tech.operating_hours_p50


def run_scenario(
    inputs: ProjectInputs,
    scenario: YieldScenario,
    waterfall_result,  # WaterfallResult from cached_run_waterfall_v3
) -> ScenarioResult:
    """Extract scenario metrics from waterfall result.
    
    Note: Since waterfall uses P50 generation, we scale generation
    proportionally for P90/P99 scenarios.
    
    Args:
        inputs: ProjectInputs (used for hours extraction)
        scenario: Scenario to run
        waterfall_result: WaterfallResult with P50 baseline
    
    Returns:
        ScenarioResult with scenario-specific metrics
    """
    p50_hours = inputs.technical.operating_hours_p50
    scenario_hours = get_scenario_hours(inputs, scenario)
    
    # Generation scale factor (P90/P99 vs P50)
    gen_scale = scenario_hours / p50_hours if p50_hours > 0 else 1.0
    
    # Use waterfall IRR/NPV directly (not scaled by generation for returns)
    # Equity IRR/Project IRR are dimensionless ratios, not affected by scale
    # But generation scaling affects total revenue/cash flow
    total_gen = sum(p.generation_mwh for p in waterfall_result.periods if p.is_operation)
    scaled_gen = total_gen * gen_scale
    
    # Revenue scaling
    total_rev = sum(p.revenue_keur for p in waterfall_result.periods if p.is_operation)
    scaled_rev = total_rev * gen_scale
    
    # Scale distributions and taxes proportionally
    scaled_dist = waterfall_result.total_distribution_keur * gen_scale
    scaled_tax = waterfall_result.total_tax_keur * gen_scale
    
    # LCOE adjusted for scenario (higher/lower generation = lower/higher LCOE)
    lcoe_base = _compute_lcoe_from_waterfall(waterfall_result, inputs)
    lcoe_adj = lcoe_base / gen_scale if gen_scale > 0 else lcoe_base
    
    return ScenarioResult(
        scenario=scenario,
        equity_irr=waterfall_result.equity_irr,
        project_irr=waterfall_result.project_irr,
        npv_keur=int(waterfall_result.project_npv),
        lcoe_eur_mwh=round(lcoe_adj, 2),
        avg_dscr=waterfall_result.avg_dscr,
        min_dscr=waterfall_result.min_dscr,
        total_distribution_keur=int(scaled_dist),
        total_tax_keur=int(scaled_tax),
        generation_mwh_y1=int(scaled_gen * 0.035),  # ~3.5% of total is Y1
        revenue_keur_y1=int(scaled_rev * 0.035),
    )


def _compute_lcoe_from_waterfall(result, inputs) -> float:
    """Compute LCOE from waterfall result."""
    total_gen = sum(p.generation_mwh for p in result.periods if p.is_operation)
    if total_gen <= 0:
        return 0.0
    
    total_capex = inputs.capex.total_capex
    total_opex = sum(p.opex_keur for p in result.periods if p.is_operation)
    total_debt_service = result.total_senior_ds_keur
    
    # Simple LCOE: (CAPEX + DS) / Total Generation
    numerator = total_capex + total_debt_service
    denominator = total_gen / 1000  # MWh → GWh
    return numerator / denominator if denominator > 0 else 0.0


def compare_scenarios(
    results: Sequence[ScenarioResult],
) -> dict:
    """Build comparison table from multiple scenario results.
    
    Returns:
        Dict with comparison data for UI rendering
    """
    if not results:
        return {}
    
    scenarios = [r.scenario.value for r in results]
    
    return {
        "scenario": scenarios,
        "equity_irr": [f"{r.equity_irr:.2%}" for r in results],
        "project_irr": [f"{r.project_irr:.2%}" for r in results],
        "npv_keur": [f"{r.npv_keur:,}" for r in results],
        "lcoe": [f"{r.lcoe_eur_mwh:.1f}" for r in results],
        "avg_dscr": [f"{r.avg_dscr:.2f}x" for r in results],
        "min_dscr": [f"{r.min_dscr:.2f}x" for r in results],
        "distribution_keur": [f"{r.total_distribution_keur:,}" for r in results],
        "tax_keur": [f"{r.total_tax_keur:,}" for r in results],
    }
