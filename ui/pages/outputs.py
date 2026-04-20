"""Outputs page - IRR, NPV, DSCR and financial KPIs."""
import streamlit as st
import pandas as pd

from domain.returns.xirr import xirr, xnpv
from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
from domain.opex.projections import opex_schedule_annual
from domain.financing.schedule import senior_debt_amount, standard_amortization
from domain.financing.sculpting import sculpt_debt_dscr


def render_outputs(inputs, engine) -> None:
    st.header("📤 Financial Outputs")
    
    s = st.session_state
    capex = inputs.capex
    financing = inputs.financing
    
    # Calculate key metrics
    total_capex = capex.total_capex
    debt = senior_debt_amount(total_capex, financing.gearing_ratio)
    equity = total_capex - debt
    rate_per_period = financing.all_in_rate / 2
    tenor_periods = financing.senior_tenor_years * 2
    
    # Revenue and OPEX schedules
    revenue = full_revenue_schedule(inputs, engine)
    generation = full_generation_schedule(inputs, engine)
    opex_annual = opex_schedule_annual(inputs, inputs.info.horizon_years)
    
    # Build cash flows for XIRR
    periods = engine.periods()
    dates = [p.end_date for p in periods]
    
    project_cfs = []
    equity_cfs = []
    
    for i, p in enumerate(periods):
        if p.is_operation:
            rev = revenue.get(p.index, 0)
            # Simplified OPEX (use annual / 2 for semi-annual periods)
            opex = opex_annual.get(p.year_index, 0) / 2
            cf = rev - opex
        else:
            cf = 0
        
        project_cfs.append(cf)
        equity_cfs.append(cf)
    
    # Add initial investment
    project_cfs[0] = -total_capex
    equity_cfs[0] = -equity
    
    # Calculate IRR
    project_irr = xirr(project_cfs, dates, guess=0.08)
    equity_irr = xirr(equity_cfs, dates, guess=0.10)
    
    # Calculate NPV
    project_npv = xnpv(0.0641, project_cfs, dates)
    equity_npv = xnpv(0.0965, equity_cfs, dates)
    
    # Display metrics
    st.subheader("📈 Returns")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        irr_str = f"{project_irr*100:.2f}%" if project_irr else "N/A"
        st.metric("Project IRR", irr_str,
                  help="Unlevered Project IRR using XIRR")
    with col2:
        irr_str = f"{equity_irr*100:.2f}%" if equity_irr else "N/A"
        st.metric("Equity IRR", irr_str,
                  help="Levered Equity IRR using XIRR")
    with col3:
        npv_str = f"{project_npv/1000:,.0f} k€" if project_npv else "N/A"
        st.metric("Project NPV", npv_str,
                  help="NPV at 6.41% (HR project hurdle)")
    with col4:
        npv_str = f"{equity_npv/1000:,.0f} k€" if equity_npv else "N/A"
        st.metric("Equity NPV", npv_str,
                  help="NPV at 9.65% (HR equity hurdle)")
    
    st.divider()
    
    # Debt metrics
    st.subheader("🏦 Debt Metrics")
    
    # Amortization schedule
    schedule = standard_amortization(debt, rate_per_period, min(tenor_periods, 30))
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Senior Debt", f"{debt:,.0f} k€",
                  help="Total senior debt")
    with col2:
        first_payment = schedule[0].total_keur if schedule else 0
        st.metric("First DS", f"{first_payment:,.0f} k€",
                  help="First debt service payment")
    with col3:
        total_interest = sum(s.interest_keur for s in schedule)
        st.metric("Total Interest", f"{total_interest:,.0f} k€",
                  help="Total interest over loan life")
    with col4:
        total_principal = sum(s.principal_keur for s in schedule)
        st.metric("Total Principal", f"{total_principal:,.0f} k€",
                  help="Total principal repaid")
    
    st.divider()
    
    # DSCR calculation
    st.subheader("📊 Coverage Ratios")
    
    # Simplified DSCR (would need full waterfall for real calculation)
    ebitda_annual = []
    ds_annual = []
    
    for year in range(1, min(11, inputs.info.horizon_years + 1)):
        rev_y = sum(v for k, v in revenue.items() 
                   if any(p.year_index == year for p in engine.periods() if p.index == k))
        opex_y = opex_annual.get(year, 0)
        ebitda = max(0, rev_y - opex_y)
        ebitda_annual.append(ebitda)
        
        if year <= financing.senior_tenor_years:
            ds = schedule[year-1].total_keur if year-1 < len(schedule) else 0
        else:
            ds = 0
        ds_annual.append(ds)
    
    dscr_values = [e / d if d > 0 else 0 for e, d in zip(ebitda_annual, ds_annual)]
    avg_dscr = sum(dscr_values) / len(dscr_values) if dscr_values else 0
    min_dscr = min(dscr_values) if dscr_values else 0
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Avg DSCR", f"{avg_dscr:.2f}x",
                  help="Average Debt Service Coverage Ratio")
    with col2:
        st.metric("Min DSCR", f"{min_dscr:.2f}x",
                  help="Minimum DSCR over forecast period")
    with col3:
        target = financing.target_dscr
        st.metric("Target DSCR", f"{target:.2f}x",
                  help="Target DSCR covenant")
    
    # DSCR chart
    dscr_df = pd.DataFrame({
        "Year": list(range(1, len(dscr_values) + 1)),
        "DSCR": dscr_values
    })
    st.line_chart(dscr_df.set_index("Year"))
    
    st.divider()
    
    # Cash flow table
    st.subheader("💵 Cash Flow Schedule (Sample)")
    
    # Build sample periods table
    op_periods = [p for p in engine.periods() if p.is_operation][:10]
    
    data = []
    for p in op_periods:
        rev = revenue.get(p.index, 0)
        gen = generation.get(p.index, 0)
        opex = opex_annual.get(p.year_index, 0) / 2
        ebitda = rev - opex
        
        if p.year_index <= financing.senior_tenor_years and p.period_in_year == 1:
            ds = schedule[p.year_index - 1].total_keur if p.year_index - 1 < len(schedule) else 0
        else:
            ds = 0
        
        data.append({
            "Period": p.index,
            "Date": p.end_date.strftime('%Y-%m'),
            "Year": p.year_index,
            "Gen (MWh)": f"{gen:,.0f}",
            "Revenue (k€)": f"{rev:,.0f}",
            "OPEX (k€)": f"{opex:,.0f}",
            "EBITDA (k€)": f"{ebitda:,.0f}",
            "Debt Service (k€)": f"{ds:,.0f}" if ds > 0 else "—",
        })
    
    st.table(data)
    
    st.divider()
    
    # LCOE calculation
    st.subheader("⚡ Levelized Cost (LCOE)")
    
    # Simple LCOE
    total_opex_discounted = 0
    total_gen_discounted = 0
    discount_rate = 0.0641
    
    for year in range(1, inputs.info.horizon_years + 1):
        gen = inputs.technical.capacity_mw * inputs.technical.operating_hours_p50 * inputs.technical.combined_availability
        opex = opex_annual.get(year, 0)
        
        total_opex_discounted += opex / (1 + discount_rate) ** year
        total_gen_discounted += gen / (1 + discount_rate) ** year
    
    lcoe = (total_capex + total_opex_discounted) / total_gen_discounted if total_gen_discounted > 0 else 0
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("LCOE", f"{lcoe:.2f} €/MWh",
                  help="Levelized Cost of Energy")
    with col2:
        # Simple CAPEX cost per MW
        capex_per_mw = total_capex / inputs.technical.capacity_mw
        st.metric("CAPEX Intensity", f"{capex_per_mw:,.0f} k€/MW",
                  help="CAPEX per MW installed")
