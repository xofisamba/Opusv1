"""Revenue page."""
import streamlit as st
from domain.revenue.generation import full_revenue_schedule, full_generation_schedule


def render_revenue_page(inputs, engine):
    st.header("💵 Revenue Schedule")
    
    revenue = full_revenue_schedule(inputs, engine)
    generation = full_generation_schedule(inputs, engine)
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ppa_tariff = inputs.revenue.ppa_base_tariff
        st.metric("PPA Tariff Y1", f"{ppa_tariff:.0f} €/MWh")
    
    with col2:
        ppa_index = inputs.revenue.ppa_index
        st.metric("PPA Index", f"{ppa_index:.1%}")
    
    with col3:
        ppa_term = inputs.revenue.ppa_term_years
        st.metric("PPA Term", f"{ppa_term} years")
    
    with col4:
        balancing = inputs.revenue.balancing_cost_pv
        st.metric("Balancing Cost", f"{balancing:.1%}")
    
    st.divider()
    
    # Y1 Revenue
    y1_rev = sum(v for k, v in revenue.items() if k in [2, 3])
    y1_gen = sum(v for k, v in generation.items() if k in [2, 3])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Y1 Generation", f"{y1_gen:,.0f} MWh")
    with col2:
        st.metric("Y1 Revenue", f"{y1_rev:,.0f} k€")
    with col3:
        avg_price = y1_rev / y1_gen * 1000 if y1_gen > 0 else 0
        st.metric("Avg Price Y1", f"{avg_price:.0f} €/MWh")
    
    st.divider()
    
    # Sample periods
    st.subheader("Revenue by Period (Sample)")
    
    op_periods = [p for p in engine.periods() if p.is_operation][:12]
    
    data = []
    for p in op_periods:
        rev = revenue.get(p.index, 0)
        gen = generation.get(p.index, 0)
        price = rev / gen * 1000 if gen > 0 else 0
        data.append({
            "Period": p.index,
            "Date": p.end_date.strftime('%Y-%m'),
            "Year": p.year_index,
            "PPA Active": "✓" if p.is_ppa_active else "—",
            "Gen (MWh)": f"{gen:,.0f}",
            "Rev (k€)": f"{rev:,.0f}",
            "Price": f"{price:.0f}" if price > 0 else "—",
        })
    
    st.table(data)
