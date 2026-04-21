"""Input builder - builds ProjectInputs from session state.

Provides _build_inputs_from_session() and _build_engine_from_inputs().
These functions are called when session state changes.
"""
from datetime import date
from typing import Optional

from domain.inputs import (
    ProjectInputs, ProjectInfo, CapexStructure, CapexItem,
    OpexItem, TechnicalParams, RevenueParams, FinancingParams, TaxParams,
    PeriodFrequency
)
from domain.period_engine import PeriodEngine, PeriodFrequency as PF


def _build_inputs_from_session() -> ProjectInputs:
    """Build ProjectInputs from session state.

    This is the main entry point for building inputs when sidebar changes.
    """
    import streamlit as st
    s = st.session_state

    # Validate inputs first
    from app.validation import validate_session_inputs
    validation = validate_session_inputs(s)

    for w in validation.warnings:
        st.warning(w)
    if validation.errors:
        for e in validation.errors:
            st.error(e)
        st.stop()

    # Normalize capacity based on technology
    if s.technology == 'Solar':
        capacity = s.capacity_dc
    else:
        capacity = s.wind_capacity

    hours_p50 = s.yield_p50
    hours_p90 = s.yield_p90

    # CAPEX items
    if s.technology == 'Solar':
        epc = CapexItem(name="EPC Contract", amount_keur=capacity * 800000 / 1000, y0_share=0.0,
                       spending_profile=tuple([1.0/12]*12))
        production = CapexItem(name="Production Units", amount_keur=capacity * 200000 / 1000, y0_share=0.0,
                              spending_profile=tuple([1.0/12]*12))
    else:
        epc = CapexItem(name="EPC Contract", amount_keur=capacity * 1100000 / 1000, y0_share=0.0,
                       spending_profile=tuple([1.0/12]*12))
        production = CapexItem(name="Production Units", amount_keur=capacity * 300000 / 1000, y0_share=0.0,
                              spending_profile=tuple([1.0/12]*12))

    # 13 items for CapexStructure fields
    other_items = [
        CapexItem(name="Other EPC", amount_keur=capacity * 30000 / 1000, y0_share=0.5, spending_profile=(0.5,)),
        CapexItem(name="Grid Connection", amount_keur=capacity * 30000 / 1000, y0_share=0.5, spending_profile=(0.5,)),
        CapexItem(name="Operations Preparation", amount_keur=capacity * 5000 / 1000, y0_share=1.0),
        CapexItem(name="Insurance", amount_keur=capacity * 5000 / 1000, y0_share=1.0),
        CapexItem(name="Lease & Property Tax", amount_keur=capacity * 2000 / 1000, y0_share=1.0),
        CapexItem(name="Construction Mgmt A", amount_keur=capacity * 15000 / 1000, y0_share=0.5, spending_profile=(0.5,)),
        CapexItem(name="Commissioning", amount_keur=capacity * 5000 / 1000, y0_share=0.5, spending_profile=(0.5,)),
        CapexItem(name="Audit & Legal", amount_keur=capacity * 3000 / 1000, y0_share=0.5, spending_profile=(0.5,)),
        CapexItem(name="Taxes & Duties", amount_keur=capacity * 2000 / 1000, y0_share=1.0),
        CapexItem(name="Construction Mgmt B", amount_keur=0.0, y0_share=0.5, spending_profile=(0.5,)),
        CapexItem(name="Project Acquisition", amount_keur=1000.0, y0_share=1.0),
        CapexItem(name="Project Rights", amount_keur=3000, y0_share=1.0),
        CapexItem(name="Contingencies", amount_keur=capacity * 40000 / 1000, y0_share=1.0),
    ]

    hard_capex = epc.amount_keur + production.amount_keur + sum(i.amount_keur for i in other_items)

    idc = 0
    if s.get('idc_capitalization', True):
        idc = hard_capex * (s.construction_period / 12 / 2) * s.idc_rate

    capex = CapexStructure(
        epc_contract=epc,
        production_units=production,
        epc_other=other_items[0],
        grid_connection=other_items[1],
        ops_prep=other_items[2],
        insurances=other_items[3],
        lease_tax=other_items[4],
        construction_mgmt_a=other_items[5],
        commissioning=other_items[6],
        audit_legal=other_items[7],
        taxes=other_items[8],
        construction_mgmt_b=other_items[9],
        project_acquisition=other_items[10],
        project_rights=other_items[11],
        contingencies=other_items[12],
        idc_keur=idc,
        commitment_fees_keur=hard_capex * s.commitment_fee / 100 * (s.construction_period / 12),
        bank_fees_keur=hard_capex * s.arrangement_fee / 100,
    )

    # OPEX
    if s.technology == 'Solar':
        opex_per_mw = 15000
    else:
        opex_per_mw = 35000

    opex_y1_total = capacity * opex_per_mw / 1000

    opex_items = [
        OpexItem(name="Technical Management", y1_amount_keur=opex_y1_total * 0.15, annual_inflation=0.02),
        OpexItem(name="Infrastructure Maintenance", y1_amount_keur=opex_y1_total * 0.18, annual_inflation=0.02),
        OpexItem(name="Insurance", y1_amount_keur=opex_y1_total * 0.19, annual_inflation=0.02),
        OpexItem(name="Lease & Property Tax", y1_amount_keur=opex_y1_total * 0.15, annual_inflation=0.02),
        OpexItem(name="Power Expenses", y1_amount_keur=opex_y1_total * 0.09, annual_inflation=0.0),
        OpexItem(name="Fees", y1_amount_keur=opex_y1_total * 0.07, annual_inflation=0.0),
        OpexItem(name="Audit & Legal", y1_amount_keur=opex_y1_total * 0.02, annual_inflation=0.02),
        OpexItem(name="Bank Fees", y1_amount_keur=opex_y1_total * 0.015, annual_inflation=0.02),
        OpexItem(name="Environmental & Social", y1_amount_keur=opex_y1_total * 0.01, annual_inflation=0.02),
        OpexItem(name="Contingencies", y1_amount_keur=opex_y1_total * 0.04, annual_inflation=0.02),
    ]

    market_prices = tuple([s.merchant_price * (1.02 ** i) for i in range(30)])

    info = ProjectInfo(
        name=s.project_name,
        company=s.project_company,
        code="PROJECT",
        country_iso="HR",
        financial_close=s.construction_start_date,
        construction_months=s.construction_period,
        cod_date=s.construction_start_date + __import__('dateutil.relativedelta', fromlist=['relativedelta']).relativedelta(months=s.construction_period),
        horizon_years=s.investment_horizon,
        period_frequency=PeriodFrequency.SEMESTRIAL if s.semi_annual_mode else PeriodFrequency.ANNUAL,
    )

    technical = TechnicalParams(
        capacity_mw=capacity,
        yield_scenario="P_50",
        operating_hours_p50=hours_p50,
        operating_hours_p90_10y=hours_p90,
        pv_degradation=0.004 if s.technology == 'Solar' else 0.003,
        bess_degradation=s.bess_degradation_rate,
        plant_availability=0.99,
        grid_availability=0.99,
        bess_enabled=s.bess_enabled,
    )

    tariff_escalation = s.tariff_escalation / 100.0 if s.tariff_escalation > 1 else s.tariff_escalation

    revenue = RevenueParams(
        ppa_base_tariff=s.ppa_base_tariff,
        ppa_term_years=s.ppa_term,
        ppa_index=tariff_escalation,
        ppa_production_share=1.0,
        market_scenario="Central",
        market_prices_curve=market_prices,
        market_inflation=0.02,
        balancing_cost_pv=0.025,
        balancing_cost_bess=0.025,
        co2_enabled=False,
        co2_price_eur=1.5,
    )

    # Normalize gearing: slider returns 0-95 (percent) → convert to 0-0.95 (fraction)
    gearing = s.gearing_ratio / 100.0 if s.gearing_ratio > 1.0 else s.gearing_ratio
    base_rate = s.base_rate / 100.0 if s.base_rate > 1 else s.base_rate

    financing = FinancingParams(
        share_capital_keur=500.0,
        share_premium_keur=0.0,
        shl_amount_keur=0.0,
        shl_rate=s.shl_rate if 'shl_rate' in s else 0.0,
        gearing_ratio=gearing,
        senior_tenor_years=s.debt_tenor,
        base_rate=base_rate,
        margin_bps=int(s.margin * 100),
        floating_share=0.2,
        fixed_share=0.8,
        hedge_coverage=0.8,
        commitment_fee=s.commitment_fee / 100,
        arrangement_fee=s.arrangement_fee / 100,
        structuring_fee=0.0,
        target_dscr=s.target_dscr,
        lockup_dscr=1.10,
        min_llcr=1.15,
        dsra_months=s.dsra_months if s.dsra_enabled else 0,
    )

    tax = TaxParams(
        corporate_rate=s.corporate_tax_rate,
        loss_carryforward_years=5,
        loss_carryforward_cap=1.0,
        legal_reserve_cap=0.10,
        thin_cap_enabled=s.thin_cap_jurisdiction != 'None (No restriction)',
        thin_cap_de_ratio=0.8,
        atad_ebitda_limit=0.30,
        atad_min_interest_keur=3000.0,
        wht_sponsor_dividends=0.05,
        wht_sponsor_shl_interest=0.0,
        shl_cap_applies=False,
    )

    return ProjectInputs(
        info=info,
        technical=technical,
        capex=capex,
        opex=tuple(opex_items),
        revenue=revenue,
        financing=financing,
        tax=tax,
    )


def _build_engine_from_inputs(inputs: ProjectInputs) -> PeriodEngine:
    """Build period engine from inputs."""
    freq = PF.SEMESTRIAL if inputs.info.period_frequency == PeriodFrequency.SEMESTRIAL else PF.ANNUAL
    return PeriodEngine(
        financial_close=inputs.info.financial_close,
        construction_months=inputs.info.construction_months,
        horizon_years=inputs.info.horizon_years,
        ppa_years=inputs.revenue.ppa_term_years,
        frequency=freq,
    )


def _update_inputs_and_engine() -> None:
    """Update inputs and engine in session state.

    Call this when sidebar inputs change.
    """
    import streamlit as st
    st.session_state.inputs = _build_inputs_from_session()
    st.session_state.engine = _build_engine_from_inputs(st.session_state.inputs)
    # Invalidate waterfall cache
    from utils.cache import invalidate_waterfall_cache
    invalidate_waterfall_cache()