"""Dashboard page - main KPIs and summary."""
import streamlit as st
from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
from domain.opex.projections import opex_year


def render_dashboard(inputs, engine) -> None:
    st.header("📊 Project Dashboard")
    
    s = st.session_state
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        capacity = inputs.technical.capacity_mw
        st.metric("Capacity", f"{capacity:.1f} MWp", 
                  help="Installed DC capacity")
    
    with col2:
        horizon = inputs.info.horizon_years
        st.metric("Horizon", f"{horizon} years",
                  help="Investment horizon")
    
    with col3:
        ppa_term = inputs.revenue.ppa_term_years
        st.metric("PPA Term", f"{ppa_term} years",
                  help="Power Purchase Agreement duration")
    
    with col4:
        gearing = inputs.financing.gearing_ratio
        st.metric("Gearing", f"{gearing:.0%}",
                  help="Debt / Total CAPEX ratio")
    
    st.divider()
    
    # CAPEX section
    st.subheader("💰 Capital Expenditure")
    
    col1, col2, col3 = st.columns(3)
    
    capex = inputs.capex
    with col1:
        st.metric("Hard CAPEX", f"{capex.hard_capex_keur:,.0f} k€",
                  help="Total capital expenditure excluding IDC")
    with col2:
        st.metric("IDC", f"{capex.idc_keur:,.0f} k€",
                  help="Interest During Construction")
    with col3:
        st.metric("Total CAPEX", f"{capex.total_capex:,.0f} k€",
                  help="Total including IDC and fees")
    
    # Per MW metrics
    per_mw_capex = capex.total_capex / inputs.technical.capacity_mw
    st.caption(f"CAPEX Intensity: {per_mw_capex:,.0f} k€/MW")
    
    st.divider()
    
    # Revenue section
    st.subheader("💵 Revenue (Y1)")
    
    revenue = full_revenue_schedule(inputs, engine)
    op_periods = [p for p in engine.periods() if p.is_operation]
    
    # Y1 is periods 2,3 (H1, H2)
    y1_revenue = sum(v for k, v in revenue.items() if k in [2, 3])
    
    generation = full_generation_schedule(inputs, engine)
    y1_gen = sum(v for k, v in generation.items() if k in [2, 3])
    
    tariff = inputs.revenue.ppa_base_tariff
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("PPA Tariff", f"{tariff:.0f} €/MWh",
                  help="Feed-in tariff Y1")
    with col2:
        avg_price = y1_revenue / y1_gen * 1000 if y1_gen > 0 else 0
        st.metric("Avg Price Y1", f"{avg_price:.0f} €/MWh",
                  help="Average revenue per MWh Y1")
    with col3:
        st.metric("Generation Y1", f"{y1_gen:,.0f} MWh",
                  help="Y1 electricity production")
    with col4:
        st.metric("Revenue Y1", f"{y1_revenue:,.0f} k€",
                  help="Y1 gross revenue")
    
    st.divider()
    
    # OPEX section
    st.subheader("📤 Operating Expenditure (Y1)")
    
    opex_y1 = opex_year(inputs.opex, 1)
    per_mw_opex = opex_y1 / inputs.technical.capacity_mw
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("OPEX Y1", f"{opex_y1:,.0f} k€",
                  help="Total operating expenditure Y1")
    with col2:
        st.metric("OPEX/MW", f"{per_mw_opex:.1f} k€/MW",
                  help="OPEX intensity")
    with col3:
        hours = inputs.technical.operating_hours_p50
        per_mwh = opex_y1 / (inputs.technical.capacity_mw * hours) * 1000 if hours > 0 else 0
        st.metric("OPEX/MWh", f"{per_mwh:.1f} €/MWh",
                  help="OPEX per unit of generation")
    
    st.divider()
    
    # EBITDA section
    st.subheader("📈 Profitability")
    
    ebitda_y1 = y1_revenue - opex_y1
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("EBITDA Y1", f"{ebitda_y1:,.0f} k€",
                  help="Earnings Before Interest, Tax, Depreciation & Amortization")
    with col2:
        margin = ebitda_y1 / y1_revenue if y1_revenue > 0 else 0
        st.metric("EBITDA Margin", f"{margin:.1%}",
                  help="EBITDA / Revenue")
    with col3:
        # Simple payback
        payback = capex.total_capex / ebitda_y1 if ebitda_y1 > 0 else 0
        st.metric("Payback", f"{payback:.1f} years",
                  help="Simple payback (CAPEX / EBITDA)")
    
    st.divider()
    
    # Financing section
    st.subheader("🏦 Financing")
    
    debt = inputs.capex.total_capex * inputs.financing.gearing_ratio
    equity = inputs.capex.total_capex - debt
    rate = inputs.financing.all_in_rate
    tenor = inputs.financing.senior_tenor_years
    dscr = inputs.financing.target_dscr
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Senior Debt", f"{debt:,.0f} k€",
                  help="Project finance debt")
    with col2:
        st.metric("Equity", f"{equity:,.0f} k€",
                  help="Sponsor equity contribution")
    with col3:
        st.metric("All-in Rate", f"{rate:.2%}",
                  help="Base rate + margin")
    with col4:
        st.metric("Debt Tenor", f"{tenor} years",
                  help="Loan maturity")
    
    st.divider()
    
    # Key assumptions
    st.subheader("📋 Key Assumptions")
    
    assumptions = [
        f"Technology: {s.technology}",
        f"Construction: {s.construction_period} months",
        f"PPA Escalation: {s.tariff_escalation:.1%}",
        f"Corporate Tax: {s.corporate_tax_rate:.1%}",
        f"Semi-Annual Mode: {'Yes' if s.semi_annual_mode else 'No'}",
        f"BESS: {'Enabled' if s.bess_enabled else 'Disabled'}",
    ]
    
    for a in assumptions:
        st.markdown(f"- {a}")
    
    st.divider()
    
    # vs Baseline
    st.subheader("📐 vs Oborovo Baseline")
    
    baseline = {
        "Total CAPEX": "56,899 k€",
        "OPEX Y1": "1,354 k€",
        "Revenue Y1": "6,447 k€",
        "Project IRR": "8.42%",
        "Equity IRR": "11.00%",
    }
    
    current = {
        "Total CAPEX": f"{capex.total_capex:,.0f} k€",
        "OPEX Y1": f"{opex_y1:,.0f} k€",
        "Revenue Y1": f"{y1_revenue:,.0f} k€",
    }
    
    comparison_df = []
    for metric in baseline:
        if metric in current:
            comparison_df.append({"Metric": metric, "Current": current[metric], "Baseline": baseline[metric]})
        else:
            comparison_df.append({"Metric": metric, "Current": "—", "Baseline": baseline[metric]})
    
    st.table(comparison_df)
