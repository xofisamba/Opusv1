"""Debt page."""
import streamlit as st
from domain.financing.schedule import senior_debt_amount, standard_amortization
from domain.financing.sculpting import sculpt_debt_dscr


def render_debt_page(inputs, engine):
    st.header("🏦 Debt Structure & Service")
    
    financing = inputs.financing
    capex = inputs.capex.total_capex
    
    debt = senior_debt_amount(capex, financing.gearing_ratio)
    rate_per_period = financing.all_in_rate / 2  # Semi-annual
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Senior Debt", f"{debt:,.0f} k€")
    with col2:
        st.metric("Gearing", f"{financing.gearing_ratio:.1%}")
    with col3:
        tenor = financing.senior_tenor_years
        st.metric("Tenor", f"{tenor} years")
    with col4:
        rate = financing.all_in_rate
        st.metric("All-in Rate", f"{rate:.2%}")
    
    st.divider()
    
    # Debt terms
    st.subheader("Debt Terms")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        base = financing.base_rate
        st.metric("Base Rate", f"{base:.2%}")
    with col2:
        margin = financing.margin_bps
        st.metric("Margin", f"{margin} bps")
    with col3:
        dscr = financing.target_dscr
        st.metric("Target DSCR", f"{dscr:.2f}x")
    
    st.divider()
    
    # Amortization schedule (sample)
    st.subheader("Amortization Schedule (Sample)")
    
    tenor_periods = financing.senior_tenor_years * 2  # Semi-annual
    
    # Use standard amortization for display
    schedule = standard_amortization(debt, rate_per_period, min(tenor_periods, 20))
    
    data = []
    for s in schedule[:10]:
        data.append({
            "Period": s.period,
            "Opening (k€)": f"{s.opening_balance:,.0f}",
            "Interest (k€)": f"{s.interest_keur:,.0f}",
            "Principal (k€)": f"{s.principal_keur:,.0f}",
            "Payment (k€)": f"{s.total_keur:,.0f}",
            "Closing (k€)": f"{s.closing_balance:,.0f}",
        })
    
    st.table(data)
    
    if len(schedule) > 10:
        st.caption(f"Showing first 10 of {len(schedule)} periods. Full schedule available in exports.")
