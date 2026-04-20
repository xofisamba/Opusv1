"""Scenarios page - P50/P75/P90/P99 analysis."""
import streamlit as st
import pandas as pd

from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
from domain.opex.projections import opex_schedule_annual
from domain.financing.schedule import senior_debt_amount


def render_scenarios(inputs, engine) -> None:
    st.header("📋 Scenarios Analysis")
    
    s = st.session_state
    capex = inputs.capex
    financing = inputs.financing
    
    # Calculate base values
    total_capex = capex.total_capex
    debt = senior_debt_amount(total_capex, financing.gearing_ratio)
    equity = total_capex - debt
    
    # Get schedules
    revenue = full_revenue_schedule(inputs, engine)
    generation = full_generation_schedule(inputs, engine)
    opex_annual = opex_schedule_annual(inputs, inputs.info.horizon_years)
    op_periods = [p for p in engine.periods() if p.is_operation]
    
    # Scenario definitions (P50, P75, P90, P99)
    scenarios = [
        {"name": "P50", "yield_hours": s.yield_p50, "probability": 0.50},
        {"name": "P75", "yield_hours": s.yield_p90 * 1.03, "probability": 0.25},  # Interpolated
        {"name": "P90", "yield_hours": s.yield_p90, "probability": 0.20},
        {"name": "P99", "yield_hours": s.yield_p99, "probability": 0.05},
    ]
    
    results = []
    for scenario in scenarios:
        hours = scenario["yield_hours"]
        cap_mw = inputs.technical.capacity_mw
        avail = inputs.technical.combined_availability
        
        # Generation per year
        gen_y1 = cap_mw * hours * avail
        
        # Revenue Y1
        tariff = inputs.revenue.ppa_base_tariff
        rev_y1 = gen_y1 * tariff / 1000
        
        # OPEX Y1
        opex_y1 = sum(item.y1_amount_keur for item in inputs.opex)
        
        # EBITDA
        ebitda = rev_y1 - opex_y1
        
        # DS (annual, first year)
        rate_per_period = financing.all_in_rate / 2
        tenor_years = financing.senior_tenor_years
        annual_ds = debt * (rate_per_period * (1 + rate_per_period) ** (tenor_years * 2)) / \
                    ((1 + rate_per_period) ** (tenor_years * 2) - 1) if rate_per_period > 0 else debt / tenor_years
        
        # Cash flow after DS
        cf = ebitda - annual_ds
        
        results.append({
            "Scenario": scenario["name"],
            "Probability": f"{scenario['probability']:.0%}",
            "Yield (hrs/yr)": f"{hours:.0f}",
            "Gen Y1 (MWh)": f"{gen_y1:,.0f}",
            "Revenue Y1 (k€)": f"{rev_y1:,.0f}",
            "OPEX Y1 (k€)": f"{opex_y1:,.0f}",
            "EBITDA Y1 (k€)": f"{ebitda:,.0f}",
            "DS Y1 (k€)": f"{annual_ds:,.0f}",
            "CF Y1 (k€)": f"{cf:,.0f}",
        })
    
    # Display table
    df = pd.DataFrame(results)
    st.dataframe(df.set_index("Scenario"), use_container_width=True)
    
    st.divider()
    
    # Chart: Revenue by scenario
    st.subheader("Revenue by Scenario")
    
    chart_data = pd.DataFrame({
        "Scenario": [r["Scenario"] for r in results],
        "Revenue Y1 (k€)": [float(r["Revenue Y1 (k€)"].replace(",", "")) for r in results],
    }).set_index("Scenario")
    
    st.bar_chart(chart_data)
    
    st.divider()
    
    # Expected value calculation
    st.subheader("Expected Values (Probability-Weighted)")
    
    expected_rev = sum(
        float(r["Revenue Y1 (k€)"].replace(",", "")) * sc["probability"]
        for r, sc in zip(results, scenarios)
    )
    expected_ebitda = sum(
        float(r["EBITDA Y1 (k€)"].replace(",", "")) * sc["probability"]
        for r, sc in zip(results, scenarios)
    )
    expected_cf = sum(
        float(r["CF Y1 (k€)"].replace(",", "")) * sc["probability"]
        for r, sc in zip(results, scenarios)
    )
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Expected Revenue Y1", f"{expected_rev:,.0f} k€")
    with col2:
        st.metric("Expected EBITDA Y1", f"{expected_ebitda:,.0f} k€")
    with col3:
        st.metric("Expected CF Y1", f"{expected_cf:,.0f} k€")


def render_comparison(inputs, engine) -> None:
    st.header("📊 Project Comparison")
    
    st.info("Compare multiple project configurations or scenarios.")
    
    # Placeholder for multi-project comparison
    # Would load saved projects from disk/database
    
    st.subheader("vs Oborovo Baseline")
    
    baseline = [
        {"Metric": "Total CAPEX", "Baseline": "56,899 k€", "Current": "—"},
        {"Metric": "Project IRR", "Baseline": "8.42%", "Current": "—"},
        {"Metric": "Equity IRR", "Baseline": "11.00%", "Current": "—"},
        {"Metric": "Avg DSCR", "Baseline": "1.147x", "Current": "—"},
    ]
    
    st.table(baseline)
    
    st.caption("Run the model to see current values vs baseline.")