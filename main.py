"""Oborovo Solar/Wind Financial Model - Full Featured Streamlit App.

This is the main entry point with full UI mirroring the original model.
Supports Solar, Wind, and BESS modeling with all parameters.

Usage:
    streamlit run main.py
"""
import streamlit as st
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from domain.inputs import (
    ProjectInputs, ProjectInfo, CapexStructure, CapexItem,
    OpexItem, TechnicalParams, RevenueParams, FinancingParams, TaxParams,
    PeriodFrequency
)
from domain.period_engine import PeriodEngine, PeriodFrequency as PF


# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

def init_session_state():
    """Initialize session state with default values matching original model."""
    defaults = {
        # Project
        'project_name': 'Solar Project',
        'project_company': 'Company',
        'technology': 'Solar',

        # Capacity
        'capacity_dc': 53.63,
        'capacity_ac': 48.7,

        # Wind
        'wind_capacity': 60.0,
        'turbine_rating': 6.0,
        'num_turbines': 10,
        'wind_speed': 7.5,
        'hub_height': 100,
        'wake_effects': 0.0,
        'curtailment': 0.0,

        # Revenue
        'ppa_base_tariff': 65.0,
        'tariff_escalation': 0.02,
        'ppa_term': 10,
        'merchant_price': 60.0,
        'merchant_tail_enabled': False,

        # Yield
        'yield_p50': 1494.0,
        'yield_p90': 1410.0,
        'yield_p99': 1350.0,
        'availability_wind': 0.95,

        # Financing
        'gearing_ratio': 0.70,
        'debt_tenor': 12,
        'repayment_frequency': 12,
        'base_rate': 0.0303,
        'margin': 2.0,
        'arrangement_fee': 1.5,
        'commitment_fee': 0.5,
        'target_dscr': 1.15,
        'debt_sculpting': True,
        'debt_sizing_method': 'DSCR-Based (Sculpted)',

        # Tax
        'corporate_tax_rate': 0.10,
        'depreciation_rate': 0.0333,
        'depreciation_period': 30,
        'thin_cap_jurisdiction': 'None (No restriction)',
        'thin_cap_equity': 15000,

        # Construction
        'construction_start_date': date(2025, 1, 1),
        'construction_period': 12,
        'semi_annual_mode': False,
        'idc_capitalization': True,
        'idc_rate': 0.06,

        # BESS
        'bess_enabled': False,
        'bess_capacity_mwh': 10.0,
        'bess_power_mw': 5.0,
        'bess_cost_per_mwh': 250000,
        'bess_roundtrip_efficiency': 0.88,
        'bess_cycle_life': 5000,
        'bess_degradation_rate': 0.02,
        'bess_annual_cycles': 365,

        # Reserves
        'cash_sweep_enabled': False,
        'cash_sweep_threshold': 1.2,
        'dsra_enabled': True,
        'dsra_months': 6,
        'mra_enabled': False,
        'mra_months': 3,

        # SHL (Subordinated Hybrid Loan)
        'shl_rate': 0.0,

        # Horizon
        'investment_horizon': 30,

        # Active sheet
        'active_sheet': '🏠 Dashboard',
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Build inputs and engine from session state
    if 'inputs' not in st.session_state:
        st.session_state.inputs = _build_inputs_from_session()
        st.session_state.engine = _build_engine_from_inputs(st.session_state.inputs)


def _calculate_cod(financial_close, construction_months):
    """Calculate COD date from financial close and construction period."""
    return financial_close + relativedelta(months=construction_months)


def _build_inputs_from_session() -> ProjectInputs:
    """Build ProjectInputs from session state."""
    s = st.session_state

    # Determine capacity
    if s.technology == 'Solar':
        capacity = s.capacity_dc
    else:
        capacity = s.wind_capacity

    # Yield hours
    hours_p50 = s.yield_p50
    hours_p90 = s.yield_p90

    # CAPEX items (simplified - per MW basis)
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

    # 13 items for CapexStructure fields (epc_other through project_rights)
    other_items = [
        CapexItem(name="Other EPC", amount_keur=capacity * 30000 / 1000, y0_share=0.5, spending_profile=(0.5, 0.5)),
        CapexItem(name="Grid Connection", amount_keur=capacity * 30000 / 1000, y0_share=0.5, spending_profile=(0.5, 0.5)),
        CapexItem(name="Operations Preparation", amount_keur=capacity * 5000 / 1000, y0_share=1.0),
        CapexItem(name="Insurance", amount_keur=capacity * 5000 / 1000, y0_share=1.0),
        CapexItem(name="Lease & Property Tax", amount_keur=capacity * 2000 / 1000, y0_share=1.0),
        CapexItem(name="Construction Mgmt A", amount_keur=capacity * 15000 / 1000, y0_share=0.5, spending_profile=(0.5, 0.5)),
        CapexItem(name="Commissioning", amount_keur=capacity * 5000 / 1000, y0_share=0.5, spending_profile=(0.5, 0.5)),
        CapexItem(name="Audit & Legal", amount_keur=capacity * 3000 / 1000, y0_share=0.5, spending_profile=(0.5, 0.5)),
        CapexItem(name="Taxes & Duties", amount_keur=capacity * 2000 / 1000, y0_share=1.0),
        CapexItem(name="Construction Mgmt B", amount_keur=0.0, y0_share=0.5, spending_profile=(0.5, 0.5)),
        CapexItem(name="Project Acquisition", amount_keur=1000.0, y0_share=1.0),
        CapexItem(name="Project Rights", amount_keur=3000, y0_share=1.0),
        CapexItem(name="Contingencies", amount_keur=capacity * 40000 / 1000, y0_share=1.0),
    ]

    # Compute hard_capex from items
    hard_capex = epc.amount_keur + production.amount_keur + sum(i.amount_keur for i in other_items)

    # IDC calculation
    idc = 0
    if s.idc_capitalization:
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

    # OPEX items
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

    # Market prices curve
    market_prices = tuple([s.merchant_price * (1.02 ** i) for i in range(30)])

    info = ProjectInfo(
        name=s.project_name,
        company=s.project_company,
        code="PROJECT",
        country_iso="HR",
        financial_close=s.construction_start_date,
        construction_months=s.construction_period,
        cod_date=_calculate_cod(s.construction_start_date, s.construction_period),
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

    revenue = RevenueParams(
        ppa_base_tariff=s.ppa_base_tariff,
        ppa_term_years=s.ppa_term,
        ppa_index=s.tariff_escalation / 100.0 if s.tariff_escalation > 1 else s.tariff_escalation,
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
        shl_amount_keur=0.0,
        shl_rate=s.shl_rate if 'shl_rate' in s else 0.0,
        gearing_ratio=s.gearing_ratio,
        senior_tenor_years=s.debt_tenor,
        base_rate=s.base_rate / 100.0 if s.base_rate > 1 else s.base_rate,
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


def _update_inputs_and_engine():
    """Update inputs and engine from session state."""
    st.session_state.inputs = _build_inputs_from_session()
    st.session_state.engine = _build_engine_from_inputs(st.session_state.inputs)


# ============================================================================
# SIDEBAR RENDERING
# ============================================================================

def render_sidebar():
    """Render full sidebar with all parameters."""
    with st.sidebar:
        st.title("⚙️ Parameters")

        # Navigation
        nav_options = ["🏠 Dashboard", "📊 Charts", "💵 Waterfall", "📋 Scenarios", "📈 Analytics", "📁 Projects", "📊 Comparison", "📤 Export", "📤 Outputs", "📊 Excel Parity"]
        idx = nav_options.index(st.session_state.active_sheet) if st.session_state.active_sheet in nav_options else 0
        selected = st.radio("Navigate", nav_options, index=idx)
        st.session_state.active_sheet = selected

        st.divider()

        # Project section
        with st.expander("📐 Project", expanded=True):
            st.text_input("Project Name", key="project_name")
            st.text_input("Company", key="project_company")

            tech = st.selectbox("Technology", ["Solar", "Wind"], index=0 if st.session_state.technology == 'Solar' else 1)
            st.session_state.technology = tech

            if tech == 'Solar':
                st.number_input("Capacity DC (MW)", key="capacity_dc", min_value=1.0, max_value=500.0, step=0.1)
                st.number_input("Capacity AC (MW)", key="capacity_ac", min_value=1.0, max_value=500.0, step=0.1)
            else:
                st.number_input("Wind Capacity (MW)", key="wind_capacity", min_value=1.0, max_value=1000.0, step=0.1)
                st.number_input("Turbine Rating (MW)", key="turbine_rating", min_value=1.0, max_value=20.0, step=0.5)
                st.number_input("Number of Turbines", key="num_turbines", min_value=1, max_value=200, step=1)
                st.number_input("Avg Wind Speed (m/s)", key="wind_speed", min_value=3.0, max_value=15.0, step=0.1)
                st.number_input("Hub Height (m)", key="hub_height", min_value=50, max_value=200, step=5)

        # Revenue section
        with st.expander("💰 Revenue", expanded=True):
            st.number_input("PPA Tariff (€/MWh)", key="ppa_base_tariff", min_value=1.0, max_value=200.0, step=1.0)
            st.slider("Tariff Escalation (%)", key="tariff_escalation", min_value=0.0, max_value=20.0, value=2.0, step=0.1, format="%.1f")
            st.number_input("PPA Term (years)", key="ppa_term", min_value=5, max_value=30, step=1)
            st.checkbox("Merchant Tail", key="merchant_tail_enabled")
            if st.session_state.merchant_tail_enabled:
                st.number_input("Merchant Price (€/MWh)", key="merchant_price", min_value=1.0, max_value=200.0, step=1.0)

        # Yield section
        with st.expander("📊 Yield", expanded=True):
            st.number_input("P50 Yield (hours)", key="yield_p50", min_value=500.0, max_value=5000.0, step=10.0)
            st.number_input("P90 Yield (hours)", key="yield_p90", min_value=500.0, max_value=5000.0, step=10.0)
            st.number_input("P99 Yield (hours)", key="yield_p99", min_value=500.0, max_value=5000.0, step=10.0)
            if tech == 'Wind':
                st.slider("Availability (%)", key="availability_wind", min_value=80.0, max_value=99.0, value=95.0, step=0.5, format="%.1f")
                st.slider("Wake Effects (%)", key="wake_effects", min_value=0.0, max_value=20.0, step=0.5, format="%.1f")
                st.slider("Curtailment (%)", key="curtailment", min_value=0.0, max_value=20.0, step=0.5, format="%.1f")

        # Financing section
        with st.expander("🏦 Financing", expanded=True):
            st.slider("Gearing (%)", key="gearing_ratio", min_value=0.0, max_value=95.0, value=70.0, step=1.0, format="%.0f")
            st.number_input("Debt Tenor (years)", key="debt_tenor", min_value=5, max_value=30, step=1)
            st.number_input("Base Rate (%)", key="base_rate", min_value=0.0, max_value=15.0, step=0.1, format="%.2f")
            st.slider("Margin (bps)", key="margin", min_value=0, max_value=500, value=200, step=5)
            st.slider("Target DSCR (x)", key="target_dscr", min_value=1.0, max_value=2.0, value=1.15, step=0.05, format="%.2f")
            st.checkbox("Debt Sculpting", key="debt_sculpting")
            st.selectbox("Debt Sizing Method", ["Gearing Ratio", "DSCR-Based (Annuity)", "DSCR-Based (Sculpted)"],
                        index=2 if st.session_state.debt_sculpting else 0, key="debt_sizing_method")
            st.number_input("Arrangement Fee (%)", key="arrangement_fee", min_value=0.0, max_value=5.0, step=0.1)
            st.number_input("Commitment Fee (%)", key="commitment_fee", min_value=0.0, max_value=5.0, step=0.1)

        # Tax section
        with st.expander("🏛️ Tax", expanded=True):
            st.slider("Corporate Tax (%)", key="corporate_tax_rate", min_value=0.0, max_value=50.0, value=10.0, step=0.5, format="%.1f")
            st.number_input("Depreciation Period (years)", key="depreciation_period", min_value=1, max_value=50, step=1)
            thin_cap_options = ["None (No restriction)", "EU Standard", "ATAD"]
            thin_cap_idx = thin_cap_options.index(st.session_state.thin_cap_jurisdiction) if st.session_state.thin_cap_jurisdiction in thin_cap_options else 0
            st.selectbox("Thin Cap Rule", thin_cap_options, key="thin_cap_jurisdiction")

        # Construction section
        with st.expander("🏗️ Construction", expanded=True):
            st.date_input("Construction Start", key="construction_start_date")
            st.number_input("Construction Period (months)", key="construction_period", min_value=6, max_value=36, step=1)
            st.checkbox("Semi-Annual Periods", key="semi_annual_mode")
            st.checkbox("Capitalize IDC", key="idc_capitalization")
            if st.session_state.idc_capitalization:
                st.slider("IDC Rate (%)", key="idc_rate", min_value=0.0, max_value=15.0, value=6.0, step=0.5, format="%.1f")

        # BESS section
        with st.expander("🔋 BESS", expanded=False):
            st.checkbox("Enable BESS", key="bess_enabled")
            if st.session_state.bess_enabled:
                st.number_input("BESS Capacity (MWh)", key="bess_capacity_mwh", min_value=1.0, max_value=1000.0, step=1.0)
                st.number_input("BESS Power (MW)", key="bess_power_mw", min_value=1.0, max_value=500.0, step=0.1)
                st.number_input("BESS Cost (€/MWh)", key="bess_cost_per_mwh", min_value=100000, max_value=500000, step=10000)
                st.slider("Roundtrip Efficiency (%)", key="bess_roundtrip_efficiency", min_value=70.0, max_value=95.0, value=88.0, step=1.0, format="%.0f")
                st.slider("Annual Cycles", key="bess_annual_cycles", min_value=100, max_value=365, value=365, step=5)
                st.slider("Degradation Rate (%)", key="bess_degradation_rate", min_value=0.0, max_value=5.0, value=2.0, step=0.1, format="%.1f")

        # Reserves section
        with st.expander("💼 Reserves", expanded=False):
            st.checkbox("DSRA (Debt Service Reserve)", key="dsra_enabled")
            if st.session_state.dsra_enabled:
                st.slider("DSRA Months", key="dsra_months", min_value=3, max_value=12, value=6, step=1)
            st.checkbox("MRA (Maintenance Reserve)", key="mra_enabled")
            if st.session_state.mra_enabled:
                st.slider("MRA Months", key="mra_months", min_value=1, max_value=6, value=3, step=1)
            st.checkbox("Cash Sweep", key="cash_sweep_enabled")
            if st.session_state.cash_sweep_enabled:
                st.slider("Cash Sweep Threshold", key="cash_sweep_threshold", min_value=1.0, max_value=2.0, value=1.2, step=0.05, format="%.2f")

        # Horizon
        with st.expander("📅 Horizon", expanded=False):
            st.number_input("Investment Horizon (years)", key="investment_horizon", min_value=10, max_value=50, step=1)

        st.divider()

        # Update button
        if st.button("🔄 Update Model", type="primary", use_container_width=True):
            _update_inputs_and_engine()
            st.rerun()

        # Reset button
        if st.button("🔁 Reset to Defaults", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key not in ['inputs', 'engine']:
                    del st.session_state[key]
            st.rerun()


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    st.set_page_config(
        page_title="Solar/Wind Financial Model",
        page_icon="📊",
        layout="wide",
    )

    init_session_state()
    render_sidebar()

    # Header
    st.title(f"📊 {st.session_state.project_name}")
    st.caption(f"Company: {st.session_state.project_company} | Technology: {st.session_state.technology}")

    # Route to page
    page = st.session_state.active_sheet

    if page == "🏠 Dashboard":
        from ui.pages.dashboard import render_dashboard
        render_dashboard(st.session_state.inputs, st.session_state.engine)

    elif page == "📋 Scenarios":
        from ui.pages.scenarios import render_scenarios
        render_scenarios(st.session_state.inputs, st.session_state.engine)

    elif page == "💵 Waterfall":
        from ui.pages.waterfall_page import render_waterfall
        render_waterfall(st.session_state.inputs, st.session_state.engine)

    elif page == "📊 Charts":
        from ui.pages.charts_page import render_charts
        render_charts(st.session_state.inputs, st.session_state.engine)

    elif page == "📈 Analytics":
        from ui.pages.analytics_page import render_analytics
        render_analytics(st.session_state.inputs, st.session_state.engine)

    elif page == "📁 Projects":
        from ui.pages.projects_page import render_projects
        render_projects(st.session_state.inputs, st.session_state.engine)

    elif page == "📊 Comparison":
        from ui.pages.comparison import render_comparison
        render_comparison(st.session_state.inputs, st.session_state.engine)

    elif page == "📤 Export":
        from ui.pages.export_page import render_export
        render_export(st.session_state.inputs, st.session_state.engine)

    elif page == "📤 Outputs":
        from ui.pages.outputs import render_outputs
        render_outputs(st.session_state.inputs, st.session_state.engine)

    elif page == "📊 Excel Parity":
        from ui.pages.excel_parity_page import render_excel_parity
        render_excel_parity(st.session_state.inputs, st.session_state.engine)


if __name__ == "__main__":
    main()
