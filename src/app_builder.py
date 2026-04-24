"""Build ProjectInputs from UI config objects.

This module bridges the UI layer (TechnologyConfig, RevenueConfig, DebtConfig)
with the domain layer (ProjectInputs).
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from domain.inputs import (
    ProjectInputs, ProjectInfo, TechnicalParams, CapexStructure,
    CapexItem, OpexItem, RevenueParams, FinancingParams, TaxParams,
    PeriodFrequency,
)


# =============================================================================
# CAPEX helpers
# =============================================================================

def _build_default_opex() -> tuple[OpexItem, ...]:
    """Build standard Opex items tuple for Oborovo-like project."""
    return (
        OpexItem(name="Technical Management", y1_amount_keur=198.0, annual_inflation=0.02),
        OpexItem(name="Infrastructure Maintenance", y1_amount_keur=244.0, annual_inflation=0.02,
                step_changes=((3, 185.64),)),
        OpexItem(name="Maintain Site", y1_amount_keur=45.2, annual_inflation=0.02),
        OpexItem(name="Clean Material", y1_amount_keur=40.0, annual_inflation=0.02),
        OpexItem(name="Security", y1_amount_keur=30.1, annual_inflation=0.02),
        OpexItem(name="Insurance", y1_amount_keur=255.0, annual_inflation=0.02),
        OpexItem(name="Lease & Property Tax", y1_amount_keur=208.08, annual_inflation=0.02),
        OpexItem(name="Power Expenses", y1_amount_keur=126.86, annual_inflation=0.0),
        OpexItem(name="Fees", y1_amount_keur=95.6, annual_inflation=0.0),
        OpexItem(name="Audit&Accounting&Legal", y1_amount_keur=24.0, annual_inflation=0.02),
        OpexItem(name="Bank Fees", y1_amount_keur=20.0, annual_inflation=0.02),
        OpexItem(name="Environmental&Social", y1_amount_keur=15.0, annual_inflation=0.02,
                step_changes=((3, 5.2),)),
        OpexItem(name="Contingencies", y1_amount_keur=52.07, annual_inflation=0.02),
        OpexItem(name="Taxes", y1_amount_keur=0.0, annual_inflation=0.0),
        OpexItem(name="Salary&Payroll", y1_amount_keur=0.0, annual_inflation=0.0),
    )


def _build_capex_from_capacity(capacity_mw: float) -> CapexStructure:
    """Build CAPEX structure scaled to capacity (Oborovo baseline 75.26 MW)."""
    base_capacity = 75.26
    scale = capacity_mw / base_capacity if capacity_mw > 0 else 1.0

    epc_contract = CapexItem(
        name="EPC Contract",
        amount_keur=26430.0 * scale,
        y0_share=0.0,
        spending_profile=(0.083,) * 12,
    )
    production_units = CapexItem(
        name="Production Units",
        amount_keur=10912.7 * scale,
        y0_share=0.0,
        spending_profile=(0.083,) * 12,
    )
    epc_other = CapexItem(name="Other EPC", amount_keur=3200.0 * scale, y0_share=0.0, spending_profile=(0.5, 0.5))
    grid_connection = CapexItem(name="Grid Connection", amount_keur=1800.0 * scale, y0_share=0.5, spending_profile=(0.5,))
    ops_prep = CapexItem(name="Operations Preparation", amount_keur=500.0 * scale, y0_share=0.5, spending_profile=(0.5,))
    insurances = CapexItem(name="Insurances", amount_keur=400.0 * scale, y0_share=1.0)
    lease_tax = CapexItem(name="Lease & Property Tax", amount_keur=200.0 * scale, y0_share=1.0)
    construction_mgmt_a = CapexItem(name="Construction Management A", amount_keur=800.0 * scale, y0_share=0.5, spending_profile=(0.5,))
    commissioning = CapexItem(name="Commissioning", amount_keur=300.0 * scale, y0_share=0.5, spending_profile=(0.5,))
    audit_legal = CapexItem(name="Audit & Legal", amount_keur=200.0 * scale, y0_share=0.5, spending_profile=(0.5,))
    construction_mgmt_b = CapexItem(name="Construction Management B", amount_keur=400.0 * scale, y0_share=0.5, spending_profile=(0.5,))
    contingencies = CapexItem(name="Contingencies", amount_keur=1986.4 * scale, y0_share=1.0)
    taxes = CapexItem(name="Taxes & Duties", amount_keur=150.0 * scale, y0_share=1.0)
    project_acquisition = CapexItem(name="Project Acquisition", amount_keur=1000.0 * scale, y0_share=0.5, spending_profile=(0.5,))
    project_rights = CapexItem(name="Project Rights", amount_keur=3024.5 * scale, y0_share=1.0)

    return CapexStructure(
        epc_contract=epc_contract,
        production_units=production_units,
        epc_other=epc_other,
        grid_connection=grid_connection,
        ops_prep=ops_prep,
        insurances=insurances,
        lease_tax=lease_tax,
        construction_mgmt_a=construction_mgmt_a,
        commissioning=commissioning,
        audit_legal=audit_legal,
        construction_mgmt_b=construction_mgmt_b,
        contingencies=contingencies,
        taxes=taxes,
        project_acquisition=project_acquisition,
        project_rights=project_rights,
        idc_keur=1086.0 * scale,
        commitment_fees_keur=188.6 * scale,
        bank_fees_keur=477.3 * scale,
        vat_costs_keur=216.1 * scale,
        reserve_accounts_keur=2239.1 * scale,
    )


# =============================================================================
# Main builder
# =============================================================================

def build_inputs_from_ui(
    tech_config,          # TechnologyConfig
    revenue_config,        # RevenueConfig
    debt_config,          # DebtConfig
    tax_config,           # TaxParams (from domain.inputs)
    project_name: str = "Oborovo Solar PV",
    company: str = "AKE Med",
    country_iso: str = "HR",
) -> ProjectInputs:
    """Build ProjectInputs from UI configuration.

    This is the core bridge: sidebar configs → domain ProjectInputs.
    Call this when user clicks "Run Model" or on auto-refresh.

    Args:
        tech_config: TechnologyConfig (solar/wind/bess)
        revenue_config: RevenueConfig (ppa/merchant/etc)
        debt_config: DebtConfig (senior/shl/mezz)
        tax_config: TaxParams
        project_name: Project name
        company: Company name
        country_iso: ISO country code

    Returns:
        ProjectInputs ready for waterfall computation
    """
    # Technology params from tech_config
    if hasattr(tech_config, 'solar') and tech_config.solar:
        capacity = tech_config.solar.capacity_ac_mw
        operating_hours_p50 = tech_config.solar.operating_hours_p50
        operating_hours_p90_10y = getattr(tech_config.solar, 'operating_hours_p90_10y', 1410.0)
        operating_hours_p99_1y = getattr(tech_config.solar, 'operating_hours_p99_1y', None)
        yield_scenario = "P_50"
    elif hasattr(tech_config, 'wind') and tech_config.wind:
        capacity = tech_config.wind.capacity_mw
        operating_hours_p50 = tech_config.wind.operating_hours_p50
        operating_hours_p90_10y = getattr(tech_config.wind, 'operating_hours_p90_10y', 2200.0)
        operating_hours_p99_1y = getattr(tech_config.wind, 'operating_hours_p99_1y', None)
        yield_scenario = "P_50"
    elif hasattr(tech_config, 'bess') and tech_config.bess:
        capacity = tech_config.bess.power_capacity_mw
        operating_hours_p50 = 0.0
        operating_hours_p90_10y = 0.0
        operating_hours_p99_1y = None
        yield_scenario = "P_50"
    else:
        capacity = 75.26
        operating_hours_p50 = 1494.0
        operating_hours_p90_10y = 1410.0
        operating_hours_p99_1y = None
        yield_scenario = "P_50"

    # Revenue params from revenue_config
    ppa_tariff = 57.0
    ppa_term = 12
    ppa_index = 0.02
    if revenue_config and revenue_config.ppa:
        ppa_tariff = revenue_config.ppa.ppa_base_price_eur_mwh or 57.0
        ppa_term = revenue_config.ppa.ppa_term_years or 12
        ppa_index = revenue_config.ppa.ppa_price_index or 0.02

    # Debt params from debt_config
    gearing = debt_config.senior.gearing_ratio if debt_config and debt_config.senior else 0.7524
    tenor = debt_config.senior.tenor_years if debt_config and debt_config.senior else 14
    base_rate = debt_config.senior.base_rate if debt_config and debt_config.senior else 0.03
    margin_bps = debt_config.senior.margin_bps if debt_config and debt_config.senior else 265
    target_dscr = debt_config.senior.target_dscr if debt_config and debt_config.senior else 1.15
    lockup_dscr = debt_config.senior.min_dscr_lockup if debt_config and debt_config.senior else 1.10
    dsra_months_val = debt_config.senior.dsra_months if debt_config and debt_config.senior else 6
    shl_amount_val = debt_config.shl.shl_keur if (debt_config and debt_config.shl and debt_config.shl.shl_enabled) else 0.0
    shl_rate_val = debt_config.shl.shl_rate if (debt_config and debt_config.shl and debt_config.shl.shl_enabled) else 0.08

    # Tax params — map UI TaxParams fields to domain TaxParams
    corporate_rate = getattr(tax_config, 'corporate_tax_rate', 0.10) if tax_config else 0.10
    loss_carryforward_years = getattr(tax_config, 'loss_carryforward_years', 5) if tax_config else 5
    atad_applies = getattr(tax_config, 'atad_applies', False) if tax_config else False
    atad_limit = getattr(tax_config, 'atad_ebitda_limit', 0.30) if tax_config else 0.30
    thin_cap_enabled = getattr(tax_config, 'thin_cap_enabled', False) if tax_config else False
    thin_cap_ratio = getattr(tax_config, 'thin_cap_ratio', 4.0) if tax_config else 4.0
    wht_div = getattr(tax_config, 'wht_dividends', 0.05) if tax_config else 0.05
    wht_shl = getattr(tax_config, 'wht_shl_interest', 0.0) if tax_config else 0.0

    # Market price curve (default Central scenario)
    market_prices = (
        65.0, 66.3, 67.6, 69.0, 70.4, 71.8, 73.2, 74.7, 76.2, 77.7,
        79.3, 80.9, 82.5, 84.2, 85.9, 87.6, 89.4, 91.2, 93.0, 94.9,
        96.8, 98.7, 100.7, 102.7, 104.8, 106.9, 109.0, 111.2, 113.4, 115.7,
    )

    # Build components
    info = ProjectInfo(
        name=project_name,
        company=company,
        code="OBR-001",
        country_iso=country_iso,
        financial_close=date(2029, 6, 29),
        construction_months=12,
        cod_date=date(2030, 6, 29),
        horizon_years=30,
        period_frequency=PeriodFrequency.SEMESTRIAL,
    )

    technical = TechnicalParams(
        capacity_mw=capacity,
        yield_scenario=yield_scenario,
        operating_hours_p50=operating_hours_p50,
        operating_hours_p90_10y=operating_hours_p90_10y,
        operating_hours_p99_1y=operating_hours_p99_1y,
        pv_degradation=0.004,
        bess_degradation=0.003,
        plant_availability=0.99,
        grid_availability=0.99,
        bess_enabled=False,
    )

    capex = _build_capex_from_capacity(capacity)
    opex = _build_default_opex()

    revenue = RevenueParams(
        ppa_base_tariff=ppa_tariff,
        ppa_term_years=ppa_term,
        ppa_index=ppa_index,
        ppa_production_share=1.0,
        market_scenario="Central",
        market_prices_curve=market_prices,
        market_inflation=0.02,
        balancing_cost_pv=0.025,
        balancing_cost_bess=0.025,
        co2_enabled=False,
        co2_price_eur=1.5,
    )

    financing = FinancingParams(
        share_capital_keur=500.0,
        share_premium_keur=0.0,
        shl_amount_keur=shl_amount_val,
        shl_rate=shl_rate_val,
        gearing_ratio=gearing,
        senior_debt_amount_keur=0.0,
        senior_tenor_years=tenor,
        base_rate=base_rate,
        margin_bps=margin_bps,
        floating_share=0.2,
        fixed_share=0.8,
        hedge_coverage=0.8,
        commitment_fee=0.0105,
        arrangement_fee=0.0,
        structuring_fee=0.01,
        target_dscr=target_dscr,
        lockup_dscr=lockup_dscr,
        min_llcr=1.15,
        dsra_months=dsra_months_val,
    )

    tax = TaxParams(
        corporate_rate=corporate_rate,
        loss_carryforward_years=loss_carryforward_years,
        loss_carryforward_cap=1.0,
        legal_reserve_cap=0.10,
        thin_cap_enabled=thin_cap_enabled,
        thin_cap_de_ratio=thin_cap_ratio,
        atad_ebitda_limit=atad_limit if atad_applies else 0.0,
        atad_min_interest_keur=3000.0,
        wht_sponsor_dividends=wht_div,
        wht_sponsor_shl_interest=wht_shl,
        shl_cap_applies=True,
    )

    return ProjectInputs(
        info=info,
        technical=technical,
        capex=capex,
        opex=opex,
        revenue=revenue,
        financing=financing,
        tax=tax,
    )
