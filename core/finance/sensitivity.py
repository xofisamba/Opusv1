"""Sensitivity analysis — Tornado and Spider charts.

Task 3.4: One-variable sensitivity (tornado) and multi-step spider analysis.
Uses cached_run_waterfall_v3 for waterfall computation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import copy

from domain.inputs import ProjectInputs
from domain.period_engine import PeriodEngine, PeriodFrequency
from utils.cache import cached_run_waterfall_v3


@dataclass
class SensitivityResult:
    """Single variable sensitivity result for tornado chart."""
    variable: str
    low_value: float
    high_value: float
    low_irr: float
    high_irr: float
    impact_bps: float  # (high_irr - low_irr) * 10000


def _get_irr(result: any, basis: str = "project") -> float:
    """Extract IRR from waterfall result."""
    if basis == "equity":
        return getattr(result, "equity_irr", 0.0) or 0.0
    return getattr(result, "project_irr", 0.0) or 0.0


def _run_with_inputs(inputs: ProjectInputs, **kwargs) -> any:
    """Run waterfall with modified inputs via copy-replace."""
    from copy import replace
    modified = replace(inputs, **kwargs)
    engine = PeriodEngine(
        financial_close=modified.info.financial_close,
        construction_months=modified.info.construction_months,
        horizon_years=modified.info.horizon_years,
        ppa_years=modified.revenue.ppa_term_years,
        frequency=PeriodFrequency.SEMESTRIAL,
    )
    rate = modified.financing.all_in_rate / 2
    tenor_periods = modified.financing.senior_tenor_years * 2
    result = cached_run_waterfall_v3(
        inputs=modified,
        engine=engine,
        rate_per_period=rate,
        tenor_periods=tenor_periods,
        target_dscr=modified.financing.target_dscr,
        lockup_dscr=modified.financing.lockup_dscr,
        tax_rate=modified.tax.corporate_rate,
        dsra_months=modified.financing.dsra_months,
        shl_amount=modified.financing.shl_amount_keur,
        shl_rate=modified.financing.shl_rate,
        discount_rate_project=0.0641,
        discount_rate_equity=0.0965,
        fixed_debt_keur=None,
    )
    return result


def run_tornado_analysis(
    inputs: ProjectInputs,
    target_irr_basis: str = "project",
) -> list[SensitivityResult]:
    """Run one-variable sensitivity for 6 standard variables.

    Variables and ranges:
    - PPA Tariff: ±25%
    - Generation: ±20%
    - CAPEX: +20% / -15%
    - OPEX: ±20%
    - Interest Rate: ±150bps

    Returns sorted by |impact_bps| descending.

    Args:
        inputs: Base ProjectInputs
        target_irr_basis: "project" (unlevered) or "equity" (levered)
    """
    base_ppa = inputs.revenue.ppa_base_tariff
    base_gen = inputs.capex.production_units.amount_keur
    base_capex = inputs.capex.total_capex_keur
    base_opex = inputs.opex.fixed_operational_cost_keur
    base_rate = inputs.financing.all_in_rate

    # Helper to run a modified scenario
    def run_scenario(**mod_kwargs) -> float:
        result = _run_with_inputs(inputs, **mod_kwargs)
        return _get_irr(result, target_irr_basis)

    results: list[SensitivityResult] = []

    # 1. PPA Tariff ±25%
    irr_low = run_scenario(revenue=copy.replace(inputs.revenue, ppa_base_tariff=base_ppa * 0.75))
    irr_high = run_scenario(revenue=copy.replace(inputs.revenue, ppa_base_tariff=base_ppa * 1.25))
    results.append(SensitivityResult(
        variable="PPA Tariff",
        low_value=base_ppa * 0.75,
        high_value=base_ppa * 1.25,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 2. Generation ±20% (scale all generation items)
    irr_low = run_scenario(capex=copy.replace(inputs.capex,
        production_units=copy.replace(inputs.capex.production_units, amount_keur=base_gen * 0.80)))
    irr_high = run_scenario(capex=copy.replace(inputs.capex,
        production_units=copy.replace(inputs.capex.production_units, amount_keur=base_gen * 1.20)))
    results.append(SensitivityResult(
        variable="Generation",
        low_value=base_gen * 0.80,
        high_value=base_gen * 1.20,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 3. CAPEX +20% / -15%
    irr_low = run_scenario(capex=copy.replace(inputs.capex, total_capex_keur=base_capex * 0.85))
    irr_high = run_scenario(capex=copy.replace(inputs.capex, total_capex_keur=base_capex * 1.20))
    results.append(SensitivityResult(
        variable="CAPEX",
        low_value=base_capex * 0.85,
        high_value=base_capex * 1.20,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 4. OPEX ±20%
    irr_low = run_scenario(opex=copy.replace(inputs.opex, fixed_operational_cost_keur=base_opex * 1.20))
    irr_high = run_scenario(opex=copy.replace(inputs.opex, fixed_operational_cost_keur=base_opex * 0.80))
    results.append(SensitivityResult(
        variable="OPEX",
        low_value=base_opex * 1.20,
        high_value=base_opex * 0.80,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 5. Interest Rate ±150bps
    irr_low = run_scenario(financing=copy.replace(inputs.financing,
        margin_bps=int((base_rate + 0.015) * 10000)))
    irr_high = run_scenario(financing=copy.replace(inputs.financing,
        margin_bps=int((base_rate - 0.015) * 10000)))
    results.append(SensitivityResult(
        variable="Interest Rate",
        low_value=base_rate + 0.015,
        high_value=base_rate - 0.015,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # Sort by |impact_bps| descending
    results.sort(key=lambda r: abs(r.impact_bps), reverse=True)
    return results


def run_spider_analysis(
    inputs: ProjectInputs,
    n_steps: int = 7,
    target_irr_basis: str = "project",
) -> dict:
    """Multi-step sensitivity: returns matrix of variable × IRR at each step.

    Steps are symmetric around base: -20%, -13%, -7%, base, +7%, +13%, +20%
    For interest rate: steps in bps around base rate.

    Returns dict with keys:
        "variables": list of variable names
        "steps": list of step multipliers (e.g. [-0.20, -0.13, -0.07, 0, 0.07, 0.13, 0.20])
        "matrix": dict mapping variable -> list of IRR values at each step

    Args:
        inputs: Base ProjectInputs
        n_steps: Number of steps (default 7)
        target_irr_basis: "project" or "equity"
    """
    # Symmetric steps
    if n_steps == 7:
        steps = [-0.20, -0.13, -0.07, 0.0, 0.07, 0.13, 0.20]
    elif n_steps == 5:
        steps = [-0.20, -0.10, 0.0, 0.10, 0.20]
    else:
        # Linear spacing
        steps = [(-1 + 2 * i / (n_steps - 1)) for i in range(n_steps)]

    matrix: dict[str, list[float]] = {}

    def run_mod(**mod_kwargs) -> float:
        result = _run_with_inputs(inputs, **mod_kwargs)
        return _get_irr(result, target_irr_basis)

    # 1. PPA Tariff
    matrix["PPA Tariff"] = [
        run_mod(revenue=copy.replace(inputs.revenue, ppa_base_tariff=inputs.revenue.ppa_base_tariff * (1 + s)))
        for s in steps
    ]

    # 2. Generation
    base_gen = inputs.capex.production_units.amount_keur
    matrix["Generation"] = [
        run_mod(capex=copy.replace(inputs.capex,
            production_units=copy.replace(inputs.capex.production_units, amount_keur=base_gen * (1 + s))))
        for s in steps
    ]

    # 3. CAPEX
    base_capex = inputs.capex.total_capex_keur
    matrix["CAPEX"] = [
        run_mod(capex=copy.replace(inputs.capex, total_capex_keur=base_capex * (1 + s)))
        for s in steps
    ]

    # 4. OPEX
    base_opex = inputs.opex.fixed_operational_cost_keur
    matrix["OPEX"] = [
        run_mod(opex=copy.replace(inputs.opex, fixed_operational_cost_keur=base_opex * (1 + s)))
        for s in steps
    ]

    # 5. Interest Rate (steps in bps: ±200bps around base)
    base_rate = inputs.financing.all_in_rate
    rate_steps = [s * 0.02 for s in steps]  # ±200bps range
    matrix["Interest Rate"] = [
        run_mod(financing=copy.replace(inputs.financing,
            margin_bps=int((base_rate + rs) * 10000)))
        for rs in rate_steps
    ]

    return {
        "variables": list(matrix.keys()),
        "steps": steps,
        "matrix": matrix,
    }