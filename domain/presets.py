"""Project presets - pre-configured projects for comparison.

Three pre-loaded projects:
1. Oborovo Solar (Croatia, 53.63 MWp, default)
2. Trebinje Solar (Bosnia, 53.63 MWp)
3. Krnovo Wind (Bosnia, 60 MWp, 72 turbines)
"""
from domain.inputs import (
    ProjectInputs, ProjectInfo, CapexStructure, CapexItem,
    OpexItem, TechnicalParams, RevenueParams, FinancingParams, TaxParams,
    PeriodFrequency
)


def create_trebinje_solar() -> ProjectInputs:
    """Trebinje Solar - 53.63 MWp solar project in Bosnia."""
    info = ProjectInfo(
        name="Trebinje Solar",
        company="Greene",
        code="TREBINJE",
        country_iso="BA",
        financial_close=date(2029, 6, 29),
        construction_months=12,
        cod_date=date(2030, 6, 29),
        horizon_years=30,
        period_frequency=PeriodFrequency.SEMESTRIAL,
    )
    
    technical = TechnicalParams(
        capacity_mw=53.63,
        yield_scenario="P_50",
        operating_hours_p50=1536,
        operating_hours_p90_10y=1300,
        pv_degradation=0.004,
        bess_degradation=0.0,
        plant_availability=0.99,
        grid_availability=0.99,
        bess_enabled=False,
    )
    
    # CAPEX from old model
    epc = CapexItem(name="EPC Contract", amount_keur=42897, y0_share=0.0)
    production = CapexItem(name="Production Units", amount_keur=10724, y0_share=0.0)
    
    capex = CapexStructure(
        epc_contract=epc,
        production_units=production,
        epc_other=CapexItem(name="Other EPC", amount_keur=3200, y0_share=0.5),
        grid_connection=CapexItem(name="Grid Connection", amount_keur=1800, y0_share=0.5),
        ops_prep=CapexItem(name="Operations Preparation", amount_keur=500, y0_share=1.0),
        insurances=CapexItem(name="Insurances", amount_keur=400, y0_share=1.0),
        lease_tax=CapexItem(name="Lease & Property Tax", amount_keur=200, y0_share=1.0),
        construction_mgmt_a=CapexItem(name="Construction Mgmt A", amount_keur=1000, y0_share=0.5),
        commissioning=CapexItem(name="Commissioning", amount_keur=300, y0_share=0.5),
        audit_legal=CapexItem(name="Audit & Legal", amount_keur=200, y0_share=0.5),
        construction_mgmt_b=CapexItem(name="Construction Mgmt B", amount_keur=500, y0_share=0.5),
        contingencies=CapexItem(name="Contingencies", amount_keur=2800, y0_share=1.0),
        taxes=CapexItem(name="Taxes", amount_keur=1138, y0_share=1.0),
        project_acquisition=CapexItem(name="Project Acquisition", amount_keur=743, y0_share=1.0),
        project_rights=CapexItem(name="Project Rights", amount_keur=1664, y0_share=1.0),
        idc_keur=0,
        commitment_fees_keur=0,
        bank_fees_keur=0,
        other_financial_keur=0,
    )
    
    opex_y1 = 53.63 * 15  # k€/MW
    opex_items = (
        OpexItem(name="Technical Management", y1_amount_keur=opex_y1 * 0.15, annual_inflation=0.02),
        OpexItem(name="Infrastructure Maintenance", y1_amount_keur=opex_y1 * 0.18, annual_inflation=0.02),
        OpexItem(name="Insurance", y1_amount_keur=opex_y1 * 0.19, annual_inflation=0.02),
        OpexItem(name="Lease & Property Tax", y1_amount_keur=opex_y1 * 0.15, annual_inflation=0.02),
        OpexItem(name="Power Expenses", y1_amount_keur=opex_y1 * 0.09, annual_inflation=0.0),
        OpexItem(name="Fees", y1_amount_keur=opex_y1 * 0.07, annual_inflation=0.0),
        OpexItem(name="Audit & Legal", y1_amount_keur=opex_y1 * 0.02, annual_inflation=0.02),
        OpexItem(name="Bank Fees", y1_amount_keur=opex_y1 * 0.015, annual_inflation=0.02),
        OpexItem(name="Environmental & Social", y1_amount_keur=opex_y1 * 0.01, annual_inflation=0.02),
        OpexItem(name="Contingencies", y1_amount_keur=opex_y1 * 0.04, annual_inflation=0.02),
    )
    
    revenue = RevenueParams(
        ppa_base_tariff=65.0,
        ppa_term_years=10,
        ppa_index=0.02,
        ppa_production_share=1.0,
        market_scenario="P50",
        market_prices_curve=tuple([60.0] * 30),
        market_inflation=0.02,
        balancing_cost_pv=0.025,
        balancing_cost_bess=0.025,
        co2_enabled=False,
        co2_price_eur=1.5,
    )
    
    financing = FinancingParams(
        share_capital_keur=17070,
        share_premium_keur=0,
        shl_amount_keur=0,
        shl_rate=0.06,
        gearing_ratio=0.70,
        senior_tenor_years=12,
        base_rate=0.0303,
        margin_bps=200,
        floating_share=0.2,
        fixed_share=0.8,
        hedge_coverage=0.8,
        commitment_fee=0.005,
        arrangement_fee=0.015,
        structuring_fee=0.0,
        target_dscr=1.15,
        lockup_dscr=1.10,
        min_llcr=1.15,
        dsra_months=6,
    )
    
    tax = TaxParams(
        corporate_rate=0.10,
        loss_carryforward_years=5,
        loss_carryforward_cap=1.0,
        legal_reserve_cap=0.10,
        thin_cap_enabled=False,
        thin_cap_de_ratio=0.8,
        atad_ebitda_limit=0.30,
        atad_min_interest_keur=3000,
        wht_sponsor_dividends=0.05,
        wht_sponsor_shl_interest=0.0,
        shl_cap_applies=False,
    )
    
    return ProjectInputs(
        info=info, technical=technical, capex=capex, opex=opex_items,
        revenue=revenue, financing=financing, tax=tax,
    )


def create_krnovo_wind() -> ProjectInputs:
    """Krnovo Wind - 60 MW wind project in Bosnia (72 turbines, 6MW each... actually 60 x 1MW)."""
    info = ProjectInfo(
        name="Krnovo Wind",
        company="Greene",
        code="KRNOVO",
        country_iso="BA",
        financial_close=date(2029, 6, 29),
        construction_months=18,
        cod_date=date(2030, 12, 29),
        horizon_years=30,
        period_frequency=PeriodFrequency.SEMESTRIAL,
    )
    
    technical = TechnicalParams(
        capacity_mw=60.0,  # 60 MW
        yield_scenario="P_50",
        operating_hours_p50=2500,
        operating_hours_p90_10y=2200,
        pv_degradation=0.003,  # Wind degradation
        bess_degradation=0.0,
        plant_availability=0.95,
        grid_availability=0.99,
        bess_enabled=False,
    )
    
    # CAPEX - wind is more expensive
    epc = CapexItem(name="EPC Contract", amount_keur=60000, y0_share=0.0)
    production = CapexItem(name="Production Units", amount_keur=18000, y0_share=0.0)
    
    capex = CapexStructure(
        epc_contract=epc,
        production_units=production,
        epc_other=CapexItem(name="Other EPC", amount_keur=4800, y0_share=0.5),
        grid_connection=CapexItem(name="Grid Connection", amount_keur=2700, y0_share=0.5),
        ops_prep=CapexItem(name="Operations Preparation", amount_keur=750, y0_share=1.0),
        insurances=CapexItem(name="Insurances", amount_keur=600, y0_share=1.0),
        lease_tax=CapexItem(name="Lease & Property Tax", amount_keur=300, y0_share=1.0),
        construction_mgmt_a=CapexItem(name="Construction Mgmt A", amount_keur=1500, y0_share=0.5),
        commissioning=CapexItem(name="Commissioning", amount_keur=450, y0_share=0.5),
        audit_legal=CapexItem(name="Audit & Legal", amount_keur=300, y0_share=0.5),
        construction_mgmt_b=CapexItem(name="Construction Mgmt B", amount_keur=750, y0_share=0.5),
        contingencies=CapexItem(name="Contingencies", amount_keur=4200, y0_share=1.0),
        taxes=CapexItem(name="Taxes", amount_keur=1700, y0_share=1.0),
        project_acquisition=CapexItem(name="Project Acquisition", amount_keur=1100, y0_share=1.0),
        project_rights=CapexItem(name="Project Rights", amount_keur=2500, y0_share=1.0),
        idc_keur=0,
        commitment_fees_keur=0,
        bank_fees_keur=0,
        other_financial_keur=0,
    )
    
    # Wind OPEX is higher (35k/MW vs 15k/MW for solar)
    opex_y1 = 60.0 * 35  # k€/MW
    opex_items = (
        OpexItem(name="Technical Management", y1_amount_keur=opex_y1 * 0.15, annual_inflation=0.02),
        OpexItem(name="Infrastructure Maintenance", y1_amount_keur=opex_y1 * 0.18, annual_inflation=0.02),
        OpexItem(name="Insurance", y1_amount_keur=opex_y1 * 0.19, annual_inflation=0.02),
        OpexItem(name="Lease & Property Tax", y1_amount_keur=opex_y1 * 0.15, annual_inflation=0.02),
        OpexItem(name="Power Expenses", y1_amount_keur=opex_y1 * 0.09, annual_inflation=0.0),
        OpexItem(name="Fees", y1_amount_keur=opex_y1 * 0.07, annual_inflation=0.0),
        OpexItem(name="Audit & Legal", y1_amount_keur=opex_y1 * 0.02, annual_inflation=0.02),
        OpexItem(name="Bank Fees", y1_amount_keur=opex_y1 * 0.015, annual_inflation=0.02),
        OpexItem(name="Environmental & Social", y1_amount_keur=opex_y1 * 0.01, annual_inflation=0.02),
        OpexItem(name="Contingencies", y1_amount_keur=opex_y1 * 0.04, annual_inflation=0.02),
    )
    
    revenue = RevenueParams(
        ppa_base_tariff=55.0,  # Wind tariff
        ppa_term_years=15,
        ppa_index=0.02,
        ppa_production_share=1.0,
        market_scenario="P50",
        market_prices_curve=tuple([50.0] * 30),
        market_inflation=0.02,
        balancing_cost_pv=0.025,
        balancing_cost_bess=0.025,
        co2_enabled=False,
        co2_price_eur=1.5,
    )
    
    financing = FinancingParams(
        share_capital_keur=26610,
        share_premium_keur=0,
        shl_amount_keur=0,
        shl_rate=0.06,
        gearing_ratio=0.70,
        senior_tenor_years=15,  # Longer tenor for wind
        base_rate=0.0303,
        margin_bps=200,
        floating_share=0.2,
        fixed_share=0.8,
        hedge_coverage=0.8,
        commitment_fee=0.005,
        arrangement_fee=0.015,
        structuring_fee=0.0,
        target_dscr=1.20,  # Wind usually needs higher DSCR
        lockup_dscr=1.15,
        min_llcr=1.20,
        dsra_months=6,
    )
    
    tax = TaxParams(
        corporate_rate=0.10,
        loss_carryforward_years=5,
        loss_carryforward_cap=1.0,
        legal_reserve_cap=0.10,
        thin_cap_enabled=False,
        thin_cap_de_ratio=0.8,
        atad_ebitda_limit=0.30,
        atad_min_interest_keur=3000,
        wht_sponsor_dividends=0.05,
        wht_sponsor_shl_interest=0.0,
        shl_cap_applies=False,
    )
    
    return ProjectInputs(
        info=info, technical=technical, capex=capex, opex=opex_items,
        revenue=revenue, financing=financing, tax=tax,
    )


def get_preset_projects() -> dict[str, ProjectInputs]:
    """Get all preset projects as dict."""
    return {
        "Oborovo Solar": None,  # Will use current session state
        "Trebinje Solar": create_trebinje_solar(),
        "Krnovo Wind": create_krnovo_wind(),
    }


# Import date at module level
from datetime import date