"""Oborovo Solar/Wind Financial Model - Streamlit App.

This is the main entry point for the Streamlit application.
It routes to different pages based on sidebar selection.

Usage:
    streamlit run main.py
    
Or:
    python main.py
"""
import streamlit as st
from datetime import date

from domain.inputs import ProjectInputs, PeriodFrequency
from domain.period_engine import PeriodEngine

# Page config
st.set_page_config(
    page_title="Oborovo Financial Model",
    page_icon="☀️",
    layout="wide",
)


def init_session_state():
    """Initialize session state with default inputs."""
    if "inputs" not in st.session_state:
        st.session_state.inputs = ProjectInputs.create_default_oborovo()
    
    if "engine" not in st.session_state:
        inputs = st.session_state.inputs
        st.session_state.engine = PeriodEngine(
            financial_close=inputs.info.financial_close,
            construction_months=inputs.info.construction_months,
            horizon_years=inputs.info.horizon_years,
            ppa_years=inputs.revenue.ppa_term_years,
            frequency=PeriodFrequency.SEMESTRIAL,
        )


def main():
    """Main application entry point."""
    init_session_state()
    
    st.title("☀️ Oborovo Solar PV Financial Model")
    st.caption("75.26 MWp Solar PV + BESS | Croatia | AKE Med")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        ["Dashboard", "Outputs", "Scenarios", "CapEx", "OpEx", "Debt Service", "Advanced"]
    )
    
    # Import and render pages
    if page == "Dashboard":
        from ui.pages.dashboard import render_dashboard
        render_dashboard(st.session_state.inputs, st.session_state.engine)
    
    elif page == "Outputs":
        from ui.pages.outputs import render_outputs
        render_outputs(st.session_state.inputs, st.session_state.engine)
    
    elif page == "Scenarios":
        st.info("Scenarios page - select P50/P90/P99 yield")
        _render_scenarios_page()
    
    elif page == "CapEx":
        st.info("CapEx page - CAPEX breakdown and spending profile")
        _render_capex_page()
    
    elif page == "OpEx":
        st.info("OpEx page - operational expenditure breakdown")
        _render_opex_page()
    
    elif page == "Debt Service":
        st.info("Debt Service page - amortization schedule")
        _render_debt_page()
    
    elif page == "Advanced":
        st.info("Advanced settings")


def _render_scenarios_page():
    """Scenarios selection page."""
    st.header("Yield Scenario Selection")
    
    scenario = st.selectbox(
        "Select Yield Scenario",
        ["P50", "P90-10y", "P99-1y"],
        index=0
    )
    
    st.write(f"Selected: **{scenario}**")
    
    inputs = st.session_state.inputs
    if scenario == "P50":
        hours = inputs.technical.operating_hours_p50
    elif scenario == "P90-10y":
        hours = inputs.technical.operating_hours_p90_10y
    else:
        hours = inputs.technical.operating_hours_p50 * 0.95  # Approximate
    
    st.metric("Operating Hours", f"{hours:.0f} hrs/year")


def _render_capex_page():
    """CapEx breakdown page."""
    st.header("Capital Expenditure")
    
    inputs = st.session_state.inputs
    capex = inputs.capex
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Hard CAPEX", f"{capex.hard_capex_keur:,.0f} k€")
    
    with col2:
        st.metric("IDC", f"{capex.idc_keur:,.0f} k€")
    
    with col3:
        st.metric("Total CAPEX", f"{capex.total_capex:,.0f} k€")
    
    st.divider()
    st.subheader("CAPEX Breakdown")
    
    items_data = [
        ("EPC Contract", inputs.capex.epc_contract.amount_keur),
        ("Production Units", inputs.capex.production_units.amount_keur),
        ("Grid Connection", inputs.capex.grid_connection.amount_keur),
        ("Contingencies", inputs.capex.contingencies.amount_keur),
        ("Project Rights", inputs.capex.project_rights.amount_keur),
        ("Other", capex.total_capex - capex.hard_capex_keur),
    ]
    
    st.table({"Item": [x[0] for x in items_data], "Amount (k€)": [x[1] for x in items_data]})


def _render_opex_page():
    """OpEx breakdown page."""
    st.header("Operational Expenditure")
    
    inputs = st.session_state.inputs
    
    from domain.opex.projections import opex_year, opex_per_mw_y1, opex_per_mwh_y1
    
    y1_opex = opex_year(inputs.opex, 1)
    per_mw = opex_per_mw_y1(inputs)
    per_mwh = opex_per_mwh_y1(inputs)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("OPEX Y1", f"{y1_opex:,.0f} k€")
    
    with col2:
        st.metric("OPEX/MW", f"{per_mw:,.1f} k€/MW")
    
    with col3:
        st.metric("OPEX/MWh", f"{per_mwh:.1f} €/MWh")
    
    st.divider()
    st.subheader("OPEX Items (Y1)")
    
    from domain.opex.projections import opex_breakdown_year
    breakdown = opex_breakdown_year(inputs, 1)
    
    items = list(breakdown.items())
    st.table({
        "Item": [x[0] for x in items],
        "Y1 Amount (k€)": [f"{x[1]:.1f}" for x in items]
    })


def _render_debt_page():
    """Debt service page."""
    st.header("Debt Service Schedule")
    
    inputs = st.session_state.inputs
    capex = inputs.capex.total_capex
    gearing = inputs.financing.gearing_ratio
    
    debt = capex * gearing
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Senior Debt", f"{debt:,.0f} k€")
    
    with col2:
        st.metric("Gearing", f"{gearing:.1%}")
    
    with col3:
        rate = inputs.financing.all_in_rate
        st.metric("All-in Rate", f"{rate:.2%}")
    
    st.divider()
    st.subheader("Debt Terms")
    
    st.write(f"**Tenor:** {inputs.financing.senior_tenor_years} years")
    st.write(f"**Target DSCR:** {inputs.financing.target_dscr:.2f}x")
    st.write(f"**Lockup DSCR:** {inputs.financing.lockup_dscr:.2f}x")


if __name__ == "__main__":
    main()