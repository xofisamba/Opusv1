"""Outputs page - IRR, NPV, DSCR and other KPIs."""
import streamlit as st

from domain.inputs import ProjectInputs
from domain.period_engine import PeriodEngine
from domain.returns.xirr import xirr, xnpv
from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
from domain.opex.projections import opex_schedule_period
from domain.financing.schedule import senior_debt_amount
from domain.financing.sculpting import sculpt_debt_dscr


def render_outputs(inputs: ProjectInputs, engine: PeriodEngine) -> None:
    """Render outputs page with financial metrics.
    
    Args:
        inputs: Project inputs
        engine: Period engine
    """
    st.header("Financial Outputs")
    
    # Calculate key metrics
    capex = inputs.capex.total_capex
    gearing = inputs.financing.gearing_ratio
    debt = senior_debt_amount(capex, gearing)
    
    # Get schedules
    revenue = full_revenue_schedule(inputs, engine)
    generation = full_generation_schedule(inputs, engine)
    opex = opex_schedule_period(inputs, engine)
    
    # Calculate IRR (simplified - using revenue-opex as cash flow)
    # For real IRR, we need full waterfall
    periods = engine.periods()
    op_periods = [p for p in periods if p.is_operation]
    
    # Build cash flow array for XIRR
    dates = [p.end_date for p in periods]
    cfs = []
    
    for p in periods:
        if p.is_operation:
            rev = revenue.get(p.index, 0)
            exp = opex.get(p.index, 0)
            cfs.append(rev - exp)
        else:
            cfs.append(0)
    
    # Add initial investment at FC
    cfs[0] = -capex
    
    project_irr = xirr(cfs, dates, guess=0.08)
    
    # Project NPV @ 6.41%
    project_npv = xnpv(0.0641, cfs, dates)
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Project IRR",
            f"{project_irr*100:.2f}%" if project_irr else "N/A",
            help="Unlevered Project IRR using XIRR on date-based cash flows"
        )
    
    with col2:
        st.metric(
            "Project NPV",
            f"{project_npv/1000:,.0f} k€" if project_npv else "N/A",
            help="NPV at 6.41% discount rate (HR project hurdle)"
        )
    
    with col3:
        debt_amount = debt
        st.metric("Senior Debt", f"{debt_amount:,.0f} k€")
    
    with col4:
        dscr_target = inputs.financing.target_dscr
        st.metric("Target DSCR", f"{dscr_target:.2f}x")
    
    st.divider()
    
    # Discount rates
    st.subheader("Discount Rates")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Project Rate", "6.41%", help="Hurdle rate for Project NPV (HR)")
    
    with col2:
        st.metric("Equity Rate", "9.65%", help="Hurdle rate for Equity NPV (HR)")
    
    st.divider()
    
    # Sample cash flows table
    st.subheader("Sample Cash Flows (Y1-Y3)")
    
    # Get Y1-Y3 operation periods
    sample_periods = [p for p in op_periods[:6]]  # First 6 periods = 3 years
    
    data = []
    for p in sample_periods:
        rev = revenue.get(p.index, 0)
        exp = opex.get(p.index, 0)
        gen = generation.get(p.index, 0)
        data.append({
            "Period": p.index,
            "Date": p.end_date.strftime('%Y-%m'),
            "Generation (MWh)": f"{gen:,.0f}",
            "Revenue (k€)": f"{rev:,.0f}",
            "OPEX (k€)": f"{exp:,.0f}",
            "Net (k€)": f"{rev-exp:,.0f}",
        })
    
    st.table(data)
    
    st.divider()
    
    # CO2 and PPA info
    st.subheader("Revenue Assumptions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        tariff = inputs.revenue.ppa_base_tariff
        index = inputs.revenue.ppa_index
        st.write(f"**PPA Tariff:** {tariff:.0f} €/MWh + {index:.0%} annual index")
    
    with col2:
        term = inputs.revenue.ppa_term_years
        st.write(f"**PPA Term:** {term} years")
    
    with col3:
        ppa_share = inputs.revenue.ppa_production_share
        st.write(f"**PPA Coverage:** {ppa_share:.0%}")
    
    st.divider()
    
    # Assumptions summary
    st.subheader("Key Assumptions")
    
    assumptions = [
        f"Capacity: {inputs.technical.capacity_mw:.1f} MWp",
        f"P50 Yield: {inputs.technical.operating_hours_p50:.0f} hours/year",
        f"P90-10y Yield: {inputs.technical.operating_hours_p90_10y:.0f} hours/year",
        f"Degradation: {inputs.technical.pv_degradation:.1%}/year",
        f"Availability: {inputs.technical.combined_availability:.1%}",
        f"OPEX Y1: {sum(opex.get(p.index, 0) for p in op_periods[:2]):,.0f} k€",
    ]
    
    for assumption in assumptions:
        st.write(assumption)