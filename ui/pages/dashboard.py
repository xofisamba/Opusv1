"""Dashboard page - main KPIs and summary."""
import streamlit as st

from domain.inputs import ProjectInputs
from domain.period_engine import PeriodEngine
from domain.opex.projections import opex_year
from domain.revenue.generation import full_revenue_schedule


def render_dashboard(inputs: ProjectInputs, engine: PeriodEngine) -> None:
    """Render dashboard with key metrics.
    
    Args:
        inputs: Project inputs
        engine: Period engine
    """
    st.header("Project Summary")
    
    # Top level metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        capacity = inputs.technical.capacity_mw
        st.metric("Capacity", f"{capacity:.1f} MWp")
    
    with col2:
        ppa_term = inputs.revenue.ppa_term_years
        st.metric("PPA Term", f"{ppa_term} years")
    
    with col3:
        total_capex = inputs.capex.total_capex
        st.metric("Total CAPEX", f"{total_capex:,.0f} k€")
    
    with col4:
        gearing = inputs.financing.gearing_ratio
        st.metric("Gearing", f"{gearing:.1%}")
    
    st.divider()
    
    # Revenue metrics
    st.subheader("Revenue (Y1)")
    
    revenue_schedule = full_revenue_schedule(inputs, engine)
    y1_revenue = sum(v for k, v in revenue_schedule.items() if k in [2, 3])  # periods 2,3 = Y1 H1+H2
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        tariff = inputs.revenue.ppa_base_tariff
        st.metric("PPA Tariff", f"{tariff:.0f} €/MWh")
    
    with col2:
        hours = inputs.technical.operating_hours_p50
        st.metric("P50 Hours", f"{hours:.0f} hrs/yr")
    
    with col3:
        st.metric("Y1 Revenue", f"{y1_revenue:,.0f} k€")
    
    st.divider()
    
    # OPEX metrics
    st.subheader("Operating Expenditure (Y1)")
    
    opex_y1 = opex_year(inputs.opex, 1)
    opex_per_mw = opex_y1 / inputs.technical.capacity_mw
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("OPEX Y1", f"{opex_y1:,.0f} k€")
    
    with col2:
        st.metric("OPEX/MW", f"{opex_per_mw:.1f} k€/MW")
    
    with col3:
        combined_av = inputs.technical.combined_availability
        st.metric("Availability", f"{combined_av:.1%}")
    
    st.divider()
    
    # Financing
    st.subheader("Financing Structure")
    
    debt = inputs.capex.total_capex * inputs.financing.gearing_ratio
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Senior Debt", f"{debt:,.0f} k€")
    
    with col2:
        tenor = inputs.financing.senior_tenor_years
        st.metric("Tenor", f"{tenor} years")
    
    with col3:
        rate = inputs.financing.all_in_rate
        st.metric("All-in Rate", f"{rate:.2%}")
    
    with col4:
        dscr = inputs.financing.target_dscr
        st.metric("Target DSCR", f"{dscr:.2f}x")
    
    st.divider()
    
    # Project dates
    st.subheader("Timeline")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write(f"**Financial Close:** {inputs.info.financial_close.strftime('%Y-%m-%d')}")
    
    with col2:
        st.write(f"**COD:** {inputs.info.cod_date.strftime('%Y-%m-%d')}")
    
    with col3:
        horizon = inputs.info.horizon_years
        st.write(f"**Horizon:** {horizon} years")
    
    st.divider()
    
    # Baseline comparison
    st.subheader("vs Excel Baseline")
    
    baseline_data = {
        "Total CAPEX": f"{inputs.capex.total_capex:,.0f} k€ vs 56,899 k€",
        "OPEX Y1": f"{opex_y1:,.0f} k€ vs 1,354 k€",
        "Revenue Y1 (est)": f"{y1_revenue:,.0f} k€ vs 6,447 k€",
    }
    
    for metric, value in baseline_data.items():
        st.write(f"**{metric}:** {value}")