"""OPEX page."""
import streamlit as st
from domain.opex.projections import opex_schedule_annual, opex_breakdown_year, opex_year


def render_opex_page(inputs, engine):
    st.header("📤 OPEX Schedule")
    
    # OPEX Y1 total
    opex_y1 = opex_year(inputs.opex, 1)
    per_mw = opex_y1 / inputs.technical.capacity_mw
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("OPEX Y1", f"{opex_y1:,.0f} k€")
    with col2:
        st.metric("OPEX/MW", f"{per_mw:.1f} k€/MW")
    with col3:
        st.metric("OPEX/MWh", f"{per_mw / inputs.technical.operating_hours_p50 * 1000:.1f} €/MWh")
    with col4:
        items = len(inputs.opex)
        st.metric("Items", f"{items}")
    
    st.divider()
    
    # OPEX breakdown Y1
    st.subheader("Y1 OPEX Breakdown")
    
    breakdown = opex_breakdown_year(inputs, 1)
    items = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    
    total = sum(breakdown.values())
    
    data = []
    for name, amount in items:
        pct = amount / total * 100 if total > 0 else 0
        data.append({
            "Item": name,
            "Y1 (k€)": f"{amount:.1f}",
            "Share": f"{pct:.1f}%",
        })
    
    st.table(data)
    
    st.divider()
    
    # Annual schedule
    st.subheader("Annual OPEX Projection")
    
    annual = opex_schedule_annual(inputs, inputs.info.horizon_years)
    
    years = list(range(1, min(11, inputs.info.horizon_years + 1)))
    
    data = []
    for y in years:
        amount = annual.get(y, 0)
        growth = amount / annual[1] - 1 if annual[1] > 0 else 0
        data.append({
            "Year": y,
            "OPEX (k€)": f"{amount:,.0f}",
            "Growth": f"{growth:.1%}",
        })
    
    st.table(data)
