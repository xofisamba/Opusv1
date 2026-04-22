"""Oborovo Solar/Wind Financial Model - Full Featured Streamlit App.

This is the main entry point with full UI mirroring the original model.
Supports Solar, Wind, and BESS modeling with all parameters.

Usage:
    streamlit run main.py

Architecture (T5 refactoring):
    - app/session.py: Session state initialization and defaults
    - app/builder.py: Input building and engine creation
    - app/validation.py: Input validation
    - ui/pages/: Page rendering functions
"""
import streamlit as st
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

# Import from app/ module (T5: main.py decomposition)
from app.session import init_session_state
from app.builder import (
    _build_inputs_from_session,
    _build_engine_from_inputs,
    _update_inputs_and_engine,
)


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

        # Collapse/Expand All buttons
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("− Collapse All", use_container_width=True, help="Zatvori sve sekcije"):
                for k in ['exp_project', 'exp_revenue', 'exp_yield', 'exp_financing', 
                          'exp_tax', 'exp_construction', 'exp_reserves', 'exp_horizon']:
                    st.session_state[k] = False
                st.rerun()
        with col2:
            if st.button("+ Expand All", use_container_width=True, help="Otvori sve sekcije"):
                for k in ['exp_project', 'exp_revenue', 'exp_yield', 'exp_financing', 
                          'exp_tax', 'exp_construction', 'exp_reserves', 'exp_horizon']:
                    st.session_state[k] = True
                st.rerun()

        # Project section
        with st.expander("📐 Project", expanded=st.session_state.get('exp_project', True)):
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
        with st.expander("💰 Revenue", expanded=st.session_state.get('exp_revenue', False)):
            st.number_input("PPA Tariff (€/MWh)", key="ppa_base_tariff", min_value=1.0, max_value=200.0, step=1.0)
            st.slider("Tariff Escalation (%)", key="tariff_escalation", min_value=0.0, max_value=20.0, value=2.0, step=0.1, format="%.1f")
            st.number_input("PPA Term (years)", key="ppa_term", min_value=5, max_value=30, step=1)
            st.checkbox("Merchant Tail", key="merchant_tail_enabled")
            if st.session_state.merchant_tail_enabled:
                st.number_input("Merchant Price (€/MWh)", key="merchant_price", min_value=1.0, max_value=200.0, step=1.0)

        # Yield section
        with st.expander("📊 Yield", expanded=st.session_state.get('exp_yield', False)):
            st.number_input("P50 Yield (hours)", key="yield_p50", min_value=500.0, max_value=5000.0, step=10.0)
            st.number_input("P90 Yield (hours)", key="yield_p90", min_value=500.0, max_value=5000.0, step=10.0)
            st.number_input("P99 Yield (hours)", key="yield_p99", min_value=500.0, max_value=5000.0, step=10.0)
            if tech == 'Wind':
                st.slider("Availability (%)", key="availability_wind", min_value=80.0, max_value=99.0, value=95.0, step=0.5, format="%.1f")
                st.slider("Wake Effects (%)", key="wake_effects", min_value=0.0, max_value=20.0, step=0.5, format="%.1f")
                st.slider("Curtailment (%)", key="curtailment", min_value=0.0, max_value=20.0, step=0.5, format="%.1f")

        # Financing section
        with st.expander("🏦 Financing", expanded=st.session_state.get('exp_financing', True)):
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
        with st.expander("🏛️ Tax", expanded=st.session_state.get('exp_tax', False)):
            st.slider("Corporate Tax (%)", key="corporate_tax_rate", min_value=0.0, max_value=50.0, value=10.0, step=0.5, format="%.1f")
            st.number_input("Depreciation Period (years)", key="depreciation_period", min_value=1, max_value=50, step=1)
            thin_cap_options = ["None (No restriction)", "EU Standard", "ATAD"]
            thin_cap_idx = thin_cap_options.index(st.session_state.thin_cap_jurisdiction) if st.session_state.thin_cap_jurisdiction in thin_cap_options else 0
            st.selectbox("Thin Cap Rule", thin_cap_options, key="thin_cap_jurisdiction")

        # Construction section
        with st.expander("🏗️ Construction", expanded=st.session_state.get('exp_construction', False)):
            st.date_input("Construction Start", key="construction_start_date")
            st.number_input("Construction Period (months)", key="construction_period", min_value=6, max_value=36, step=1)
            st.checkbox("Semi-Annual Periods", key="semi_annual_mode")
            st.checkbox("Capitalize IDC", key="idc_capitalization")
            if st.session_state.idc_capitalization:
                st.slider("IDC Rate (%)", key="idc_rate", min_value=0.0, max_value=15.0, value=6.0, step=0.5, format="%.1f")

        # Reserves section
        with st.expander("💼 Reserves", expanded=st.session_state.get('exp_reserves', False)):
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
        with st.expander("📅 Horizon", expanded=st.session_state.get('exp_horizon', False)):
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

        # Clear cache button
        if st.button("🗑️ Clear Cache", use_container_width=True, help="Briše cache izračuna"):
            st.cache_data.clear()
            st.success("Cache obrisan.")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    st.set_page_config(
        page_title="Solar/Wind Financial Model",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get Help": "https://github.com/xofisamba/Opusv1",
            "Report a bug": "https://github.com/xofisamba/Opusv1/issues",
            "About": "# Oborovo Financial Model\nProject finance model za solarne i wind projekte.",
        }
    )

    init_session_state()
    render_sidebar()

    # Build inputs/engine on first load if not present
    if 'inputs' not in st.session_state or st.session_state.inputs is None:
        st.session_state.inputs = _build_inputs_from_session()
        st.session_state.engine = _build_engine_from_inputs(st.session_state.inputs)

    # Header
    st.title(f"📊 {st.session_state.project_name}")
    st.caption(f"Company: {st.session_state.project_company} | Technology: {st.session_state.technology}")

    # Route to page
    page = st.session_state.active_sheet

    if page == "🏠 Dashboard":
        from ui.pages.dashboard import render_dashboard
        render_dashboard(st.session_state.inputs, st.session_state.engine)

    elif page == "📋 Scenarios":
        from ui.pages.scenarios import render_scenario_manager
        render_scenario_manager(st.session_state.inputs, None)

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
