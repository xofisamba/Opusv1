"""Analytics page - Monte Carlo, LCOE, BESS."""
import streamlit as st
import pandas as pd
import numpy as np

from domain.analytics.monte_carlo import run_monte_carlo, probability_exceed_threshold
from domain.analytics.lcoe import calculate_lcoe
from domain.analytics.bess import BESSParams, simulate_bess_annual


def render_analytics(inputs, engine) -> None:
    st.header("📈 Advanced Analytics")
    
    s = st.session_state
    capex = inputs.capex
    financing = inputs.financing
    
    # Tab layout
    tab1, tab2, tab3 = st.tabs(["🎲 Monte Carlo", "⚡ LCOE", "🔋 BESS"])
    
    with tab1:
        render_monte_carlo(inputs, engine, s)
    
    with tab2:
        render_lcoe(inputs, s)
    
    with tab3:
        render_bess(s)


def render_monte_carlo(inputs, engine, s):
    st.subheader("🎲 Monte Carlo Simulation")
    
    col1, col2 = st.columns(2)
    
    with col1:
        n_sims = st.slider("Number of Simulations", 100, 5000, 1000, step=100)
        generation_cv = st.slider("Generation CV (%)", 1, 30, 10, step=1) / 100
    
    with col2:
        st.write("**Scenario:** Solar/Wind uncertainty")
        st.write(f"Yield Hours: {s.yield_p50:.0f} ± {generation_cv*100:.0f}%")
        
        if st.button("🎲 Run Simulation", type="primary"):
            with st.spinner("Running Monte Carlo..."):
                # Build base case from inputs
                capacity = s.capacity_dc if s.technology == 'Solar' else s.wind_capacity
                hours = s.yield_p50
                total_capex = inputs.capex.total_capex
                debt = total_capex * s.gearing_ratio
                equity = total_capex - debt
                
                # EBITDA schedule (simplified)
                tariff = s.ppa_base_tariff
                opex_y1 = sum(item.y1_amount_keur for item in inputs.opex)
                
                periods = list(engine.periods())
                op_periods = [p for p in periods if p.is_operation]
                
                ebitda_schedule = []
                revenue_schedule = []
                
                for p in op_periods:
                    gen = capacity * hours * 0.99 / 1000  # MWh
                    rev = gen * tariff
                    opex = opex_y1 / 2  # Semi-annual
                    ebit = rev - opex
                    ebitda_schedule.append(ebit)
                    revenue_schedule.append(rev)
                
                # Prepare base case
                base_case = {
                    'total_capex': total_capex,
                    'debt': debt,
                    'equity': equity,
                    'ebitda_schedule': ebitda_schedule,
                    'revenue_schedule': revenue_schedule,
                    'discount_rate_project': 0.0641,
                    'discount_rate_equity': 0.0965,
                    'rate_per_period': inputs.financing.all_in_rate / 2,
                    'n_periods': len(op_periods),
                    'dates': [p.end_date for p in op_periods],
                }
                
                result = run_monte_carlo(
                    base_case,
                    n_simulations=n_sims,
                    generation_cv=generation_cv,
                    seed=42,
                )
                
                # Store in session for display
                st.session_state.mc_result = result
    
    # Display results if available
    if hasattr(st.session_state, 'mc_result'):
        result = st.session_state.mc_result
        
        st.divider()
        st.subheader("Project IRR Distribution")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Mean", f"{result.project_irr_mean*100:.2f}%")
        with col2:
            st.metric("Median", f"{result.project_irr_median*100:.2f}%")
        with col3:
            st.metric("P10", f"{result.project_irr_p10*100:.2f}%")
        with col4:
            st.metric("P90", f"{result.project_irr_p90*100:.2f}%")
        
        st.divider()
        
        # Histogram
        st.write("**Project IRR Distribution**")
        
        hist_data = pd.DataFrame({
            'IRR': result.project_irr_all,
        })
        
        # Bin into categories
        bins = list(range(0, 20, 1))
        hist_data['Bin'] = pd.cut(hist_data['IRR'] * 100, bins=bins)
        hist_counts = hist_data['Bin'].value_counts().sort_index()
        
        bar_data = pd.DataFrame({
            'IRR Range (%)': [str(i) for i in bins[:-1]],
            'Count': [hist_counts.get(pd.Interval(i, i+1), 0) for i in bins[:-1]],
        }).set_index('IRR Range (%)')
        
        st.bar_chart(bar_data)
        
        st.divider()
        
        # Probability analysis
        st.subheader("Probability Analysis")
        
        prob_above_8 = probability_exceed_threshold(result.project_irr_all, 0.08)
        prob_above_10 = probability_exceed_threshold(result.project_irr_all, 0.10)
        prob_loss = probability_exceed_threshold(result.project_irr_all, 0) / len(result.project_irr_all)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("P(IRR > 8%)", f"{prob_above_8:.1%}")
        with col2:
            st.metric("P(IRR > 10%)", f"{prob_above_10:.1%}")
        with col3:
            st.metric("P(Loss)", f"{prob_loss:.1%}")
        
        st.divider()
        
        # Equity IRR
        st.subheader("Equity IRR Distribution")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Mean", f"{result.equity_irr_mean*100:.2f}%")
        with col2:
            st.metric("Median", f"{result.equity_irr_median*100:.2f}%")
        with col3:
            st.metric("P10", f"{result.equity_irr_p10*100:.2f}%")
        with col4:
            st.metric("P90", f"{result.equity_irr_p90*100:.2f}%")
        
        st.caption(f"Based on {result.n_simulations} simulations | CV = {generation_cv*100:.0f}%")


def render_lcoe(inputs, s):
    st.subheader("⚡ Levelized Cost of Energy")
    
    col1, col2 = st.columns(2)
    
    with col1:
        capacity = s.capacity_dc if s.technology == 'Solar' else s.wind_capacity
        hours = s.yield_p50
        capex_total = inputs.capex.total_capex
        opex_y1 = sum(item.y1_amount_keur for item in inputs.opex)
        
        st.write(f"**Configuration:**")
        st.write(f"- Capacity: {capacity:.1f} MWp")
        st.write(f"- P50 Hours: {hours:.0f} hrs/year")
        st.write(f"- Total CAPEX: {capex_total:,.0f} k€")
        st.write(f"- OPEX Y1: {opex_y1:,.0f} k€")
    
    with col2:
        discount = st.number_input("Discount Rate (%)", value=6.41, min_value=1.0, max_value=20.0, step=0.1) / 100
        horizon = st.number_input("Horizon (years)", value=30, min_value=10, max_value=50, step=1)
    
    if st.button("📊 Calculate LCOE", type="primary"):
        result = calculate_lcoe(
            capacity_mw=capacity,
            operating_hours_p50=hours,
            total_capex_keur=capex_total,
            opex_y1_keur=opex_y1,
            opex_inflation=s.tariff_escalation,
            discount_rate=discount,
            horizon_years=int(horizon),
            availability=0.99,
            degradation=0.004 if s.technology == 'Solar' else 0.003,
        )
        
        st.session_state.lcoe_result = result
    
    if hasattr(st.session_state, 'lcoe_result'):
        result = st.session_state.lcoe_result
        
        st.divider()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("LCOE", f"{result.lcoe_eur_mwh:.1f} €/MWh",
                      help="Levelized Cost of Energy")
        with col2:
            st.metric("CAPEX/MW", f"{result.capex_per_mw:,.0f} k€/MW",
                      help="CAPEX per MW installed")
        with col3:
            st.metric("Total Generation", f"{result.total_generation_mwh/1e6:.2f} TWh",
                      help="Total generation over project life")
        with col4:
            capex_pct = result.pv_capex_opex_keur * result.total_capex_keur / result.pv_capex_opex_keur / result.pv_capex_opex_keur * 100 if result.pv_capex_opex_keur > 0 else 0
            st.metric("CAPEX Component", f"{result.total_capex_keur/result.pv_capex_opex_keur*100:.0f}%",
                      help="% of LCOE from CAPEX")
        
        st.divider()
        
        # Components breakdown
        st.subheader("LCOE Components")
        
        components = [
            {"Component": "CAPEX", "Amount (k€)": result.total_capex_keur, "€/MWh": result.lcoe_eur_mwh * result.total_capex_keur / result.pv_capex_opex_keur if result.pv_capex_opex_keur > 0 else 0},
            {"Component": "OPEX", "Amount (k€)": result.total_opex_keur, "€/MWh": result.lcoe_eur_mwh * result.total_opex_keur / result.pv_capex_opex_keur if result.pv_capex_opex_keur > 0 else 0},
            {"Component": "Total", "Amount (k€)": result.pv_capex_opex_keur, "€/MWh": result.lcoe_eur_mwh},
        ]
        
        st.table(pd.DataFrame(components).set_index("Component"))
        
        st.caption(f"Based on {result.horizon_years} year horizon | {discount*100:.2f}% discount rate")


def render_bess(s):
    st.subheader("🔋 Battery Energy Storage (BESS)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        bess_enabled = st.checkbox("Enable BESS", value=s.bess_enabled)
        
        if bess_enabled:
            capacity_mwh = st.number_input("Capacity (MWh)", value=s.bess_capacity_mwh, min_value=1.0, max_value=2000.0, step=1.0)
            power_mw = st.number_input("Power (MW)", value=s.bess_power_mw, min_value=0.5, max_value=500.0, step=0.5)
            cost_per_mwh = st.number_input("Cost (€/MWh)", value=s.bess_cost_per_mwh, min_value=100000, max_value=600000, step=10000)
        
            rte = st.slider("Roundtrip Efficiency (%)", 70, 95, int(s.bess_roundtrip_efficiency * 100), step=1) / 100
            degr = st.slider("Annual Degradation (%)", 0, 5, int(s.bess_degradation_rate * 100), step=1) / 100
            cycles = st.slider("Annual Cycles", 100, 365, s.bess_annual_cycles, step=10)
        
        price_low = st.number_input("Charging Price (€/MWh)", value=40.0, min_value=10.0, max_value=200.0, step=1.0)
        price_high = st.number_input("Discharging Price (€/MWh)", value=100.0, min_value=20.0, max_value=500.0, step=1.0)
        capacity_payment = st.number_input("Capacity Payment (€/year)", value=50000.0, min_value=0.0, max_value=1000000.0, step=10000.0)
    
    with col2:
        st.write("**BESS Parameters:**")
        
        if bess_enabled:
            st.write(f"- Power: {power_mw:.1f} MW")
            st.write(f"- Capacity: {capacity_mwh:.1f} MWh")
            st.write(f"- Duration: {capacity_mwh/power_mw:.1f} hours")
            st.write(f"- Cost: {cost_per_mwh * capacity_mwh * 1.3:,.0f} €")
            st.write(f"- RTE: {rte*100:.0f}%")
            st.write(f"- Degradation: {degr*100:.1f}%/year")
            
            if st.button("📊 Simulate BESS", type="primary"):
                params = BESSParams(
                    capacity_mwh=capacity_mwh,
                    power_mw=power_mw,
                    cost_per_mwh=cost_per_mwh,
                    rte=rte,
                    degradation_rate=degr,
                    annual_cycles=cycles,
                )
                
                result = simulate_bess_annual(
                    params,
                    price_low,
                    price_high,
                    capacity_payment_eur=capacity_payment,
                )
                
                st.session_state.bess_result = result
    
    if hasattr(st.session_state, 'bess_result'):
        result = st.session_state.bess_result
        
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Energy Arbitrage", f"{result.energy_arbitrage_eur:,.0f} €",
                      help="Annual revenue from price arbitrage")
        with col2:
            st.metric("Total Revenue", f"{result.total_revenue_eur:,.0f} €",
                      help="Total annual BESS revenue")
        with col3:
            st.metric("Net Revenue", f"{result.net_revenue_eur:,.0f} €",
                      help="Net after OPEX and replacement")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Capacity @ Y10", f"{result.capacity_at_year_10_mwh:.1f} MWh",
                      help="Usable capacity at year 10")
        with col2:
            st.metric("Capacity @ Y20", f"{result.capacity_at_year_20_mwh:.1f} MWh",
                      help="Usable capacity at year 20")
        with col3:
            st.metric("OPEX", f"{result.opex_annual_eur:,.0f} €/yr",
                      help="Annual O&M cost")
        
        st.divider()
        
        # BESS CAPEX
        st.write("**BESS CAPEX:**")
        capex_total = result.total_capex_eur
        capex_per_mw = capex_total / power_mw if power_mw > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total CAPEX", f"{capex_total:,.0f} €",
                      help="Total BESS CAPEX including power equipment")
        with col2:
            st.metric("CAPEX/MW", f"{capex_per_mw:,.0f} €/MW",
                      help="CAPEX per MW of power capacity")
        with col3:
            st.metric("CAPEX/MWh", f"{result.capex_per_mwh:,.0f} €/MWh",
                      help="CAPEX per MWh of energy capacity")
    else:
        if not bess_enabled:
            st.info("Enable BESS in the sidebar to simulate battery storage.")