"""Sensitivity analysis — Tornado and Spider charts.

Task 3.4: One-variable sensitivity (tornado) and multi-step spider analysis.
Uses cached_run_waterfall_v3 for waterfall computation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace as dc_replace
from typing import Optional

from domain.inputs import ProjectInputs, CapexStructure, OpexItem
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
    """Run waterfall with modified inputs via dc_replace."""
    modified = dc_replace(inputs, **kwargs)
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


def _scale_capex(capex: CapexStructure, factor: float) -> CapexStructure:
    """Return a new CapexStructure with all amounts scaled by factor."""
    return dc_replace(capex,
        epc_contract=dc_replace(capex.epc_contract, amount_keur=capex.epc_contract.amount_keur * factor),
        production_units=dc_replace(capex.production_units, amount_keur=capex.production_units.amount_keur * factor),
        epc_other=dc_replace(capex.epc_other, amount_keur=capex.epc_other.amount_keur * factor),
        grid_connection=dc_replace(capex.grid_connection, amount_keur=capex.grid_connection.amount_keur * factor),
        ops_prep=dc_replace(capex.ops_prep, amount_keur=capex.ops_prep.amount_keur * factor),
        insurances=dc_replace(capex.insurances, amount_keur=capex.insurances.amount_keur * factor),
        lease_tax=dc_replace(capex.lease_tax, amount_keur=capex.lease_tax.amount_keur * factor),
        construction_mgmt_a=dc_replace(capex.construction_mgmt_a, amount_keur=capex.construction_mgmt_a.amount_keur * factor),
        commissioning=dc_replace(capex.commissioning, amount_keur=capex.commissioning.amount_keur * factor),
        audit_legal=dc_replace(capex.audit_legal, amount_keur=capex.audit_legal.amount_keur * factor),
        construction_mgmt_b=dc_replace(capex.construction_mgmt_b, amount_keur=capex.construction_mgmt_b.amount_keur * factor),
        contingencies=dc_replace(capex.contingencies, amount_keur=capex.contingencies.amount_keur * factor),
        taxes=dc_replace(capex.taxes, amount_keur=capex.taxes.amount_keur * factor),
        project_acquisition=dc_replace(capex.project_acquisition, amount_keur=capex.project_acquisition.amount_keur * factor),
        project_rights=dc_replace(capex.project_rights, amount_keur=capex.project_rights.amount_keur * factor),
        idc_keur=capex.idc_keur * factor,
        commitment_fees_keur=capex.commitment_fees_keur * factor,
        bank_fees_keur=capex.bank_fees_keur * factor,
        other_financial_keur=capex.other_financial_keur * factor,
        vat_costs_keur=capex.vat_costs_keur * factor,
        reserve_accounts_keur=capex.reserve_accounts_keur * factor,
    )


def _scale_opex(opex: tuple[OpexItem, ...], factor: float) -> tuple[OpexItem, ...]:
    """Return a new opex tuple with all Y1 amounts scaled by factor."""
    return tuple(dc_replace(item, y1_amount_keur=item.y1_amount_keur * factor) for item in opex)


def run_tornado_analysis(
    inputs: ProjectInputs,
    target_irr_basis: str = "project",
) -> list[SensitivityResult]:
    """Run one-variable sensitivity for 5 standard variables.

    Variables and ranges:
    - PPA Tariff: ±25%
    - Generation: ±20%
    - CAPEX: +20% / -15%
    - OPEX: ±20%
    - Interest Rate: ±150bps

    Returns sorted by |impact_bps| descending.
    """
    base_ppa = inputs.revenue.ppa_base_tariff
    base_gen = inputs.capex.production_units.amount_keur
    base_opex = inputs.opex

    def run_scenario(**mod_kwargs) -> float:
        result = _run_with_inputs(inputs, **mod_kwargs)
        return _get_irr(result, target_irr_basis)

    results: list[SensitivityResult] = []

    # 1. PPA Tariff ±25%
    irr_low = run_scenario(revenue=dc_replace(inputs.revenue, ppa_base_tariff=base_ppa * 0.75))
    irr_high = run_scenario(revenue=dc_replace(inputs.revenue, ppa_base_tariff=base_ppa * 1.25))
    results.append(SensitivityResult(
        variable="PPA Tariff",
        low_value=base_ppa * 0.75,
        high_value=base_ppa * 1.25,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 2. Generation ±20%
    irr_low = run_scenario(
        capex=dc_replace(inputs.capex,
            production_units=dc_replace(inputs.capex.production_units, amount_keur=base_gen * 0.80))
    )
    irr_high = run_scenario(
        capex=dc_replace(inputs.capex,
            production_units=dc_replace(inputs.capex.production_units, amount_keur=base_gen * 1.20))
    )
    results.append(SensitivityResult(
        variable="Generation",
        low_value=base_gen * 0.80,
        high_value=base_gen * 1.20,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 3. CAPEX +20% / -15%
    irr_low = run_scenario(capex=_scale_capex(inputs.capex, 0.85))
    irr_high = run_scenario(capex=_scale_capex(inputs.capex, 1.20))
    results.append(SensitivityResult(
        variable="CAPEX",
        low_value=inputs.capex.total_capex * 0.85,
        high_value=inputs.capex.total_capex * 1.20,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 4. OPEX ±20%
    irr_low = run_scenario(opex=_scale_opex(base_opex, 1.20))
    irr_high = run_scenario(opex=_scale_opex(base_opex, 0.80))
    results.append(SensitivityResult(
        variable="OPEX",
        low_value=1.20,
        high_value=0.80,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    # 5. Interest Rate ±150bps
    base_rate = inputs.financing.all_in_rate
    irr_low = run_scenario(financing=dc_replace(inputs.financing,
        margin_bps=int((base_rate + 0.015) * 10000)))
    irr_high = run_scenario(financing=dc_replace(inputs.financing,
        margin_bps=int((base_rate - 0.015) * 10000)))
    results.append(SensitivityResult(
        variable="Interest Rate",
        low_value=base_rate + 0.015,
        high_value=base_rate - 0.015,
        low_irr=irr_low,
        high_irr=irr_high,
        impact_bps=(irr_high - irr_low) * 10000,
    ))

    results.sort(key=lambda r: abs(r.impact_bps), reverse=True)
    return results


def run_spider_analysis(
    inputs: ProjectInputs,
    n_steps: int = 7,
    target_irr_basis: str = "project",
) -> dict:
    """Multi-step sensitivity: matrix of variable × IRR at each step.

    Steps symmetric: -20%, -13%, -7%, base, +7%, +13%, +20%
    """
    if n_steps == 7:
        steps = [-0.20, -0.13, -0.07, 0.0, 0.07, 0.13, 0.20]
    elif n_steps == 5:
        steps = [-0.20, -0.10, 0.0, 0.10, 0.20]
    else:
        steps = [(-1 + 2 * i / (n_steps - 1)) for i in range(n_steps)]

    matrix: dict[str, list[float]] = {}

    def run_mod(**mod_kwargs) -> float:
        result = _run_with_inputs(inputs, **mod_kwargs)
        return _get_irr(result, target_irr_basis)

    base_ppa = inputs.revenue.ppa_base_tariff
    base_gen = inputs.capex.production_units.amount_keur
    base_opex = inputs.opex
    base_rate = inputs.financing.all_in_rate

    matrix["PPA Tariff"] = [
        run_mod(revenue=dc_replace(inputs.revenue, ppa_base_tariff=base_ppa * (1 + s)))
        for s in steps
    ]

    matrix["Generation"] = [
        run_mod(capex=dc_replace(inputs.capex,
            production_units=dc_replace(inputs.capex.production_units, amount_keur=base_gen * (1 + s))))
        for s in steps
    ]

    matrix["CAPEX"] = [
        run_mod(capex=_scale_capex(inputs.capex, (1 + s)))
        for s in steps
    ]

    matrix["OPEX"] = [
        run_mod(opex=_scale_opex(base_opex, (1 + s)))
        for s in steps
    ]

    rate_steps = [s * 0.02 for s in steps]
    matrix["Interest Rate"] = [
        run_mod(financing=dc_replace(inputs.financing,
            margin_bps=int((base_rate + rs) * 10000)))
        for rs in rate_steps
    ]

    return {
        "variables": list(matrix.keys()),
        "steps": steps,
        "matrix": matrix,
    }