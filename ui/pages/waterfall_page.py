"""Waterfall page - Full financial model with DSCR-based debt sizing."""
import streamlit as st
import pandas as pd

from domain.waterfall.waterfall_engine import cached_run_waterfall, print_waterfall_summary
from domain.capex.spending_profile import construction_capex_schedule as full_capex_schedule


def render_waterfall(inputs, engine) -> None:
    st.header("💵 Cash Flow Waterfall")
    
    s = st.session_state
    capex = inputs.capex
    financing = inputs.financing
    tax = inputs.tax
    
    # Get all periods
    periods = list(engine.periods())
    op_periods = [p for p in periods if p.is_operation]
    
    # Build schedules
    revenue = full_revenue_schedule(inputs, engine)
    generation = full_generation_schedule(inputs, engine)
    opex_annual = opex_schedule_annual(inputs, inputs.info.horizon_years)
# CAPEX schedule not needed directly - use total_capex from inputs
    # capex_spend = full_capex_schedule(inputs, engine)
    
    # Semi-annual OPEX mapping
    opex_schedule = {}
    for p in periods:
        if p.is_operation:
            opex_schedule[p.index] = opex_annual.get(p.year_index, 0) / 2
    
    # Semi-annual revenue mapping
    rev_schedule = []
    gen_schedule = []
    for p in periods:
        if p.is_operation:
            rev_schedule.append(revenue.get(p.index, 0))
            gen_schedule.append(generation.get(p.index, 0))
        else:
            rev_schedule.append(0)
            gen_schedule.append(0)
    
    # EBITDA schedule (semi-annual)
    ebitda_schedule = []
    for p in periods:
        if p.is_operation:
            ebitda = max(0, revenue.get(p.index, 0) - opex_annual.get(p.year_index, 0) / 2)
        else:
            ebitda = 0
        ebitda_schedule.append(ebitda)
    
    # Depreciation schedule (annual / 2 per period)
    dep_per_year = capex.total_capex / inputs.info.horizon_years
    dep_schedule = []
    for p in periods:
        if p.is_operation:
            dep_schedule.append(dep_per_year / 2)
        else:
            dep_schedule.append(0)
    
    # Financing parameters
    total_capex = capex.total_capex
    rate = financing.all_in_rate / 2  # Semi-annual
    tenor_periods = financing.senior_tenor_years * 2
    target_dscr = financing.target_dscr
    lockup_dscr = financing.lockup_dscr
    dsra_months = financing.dsra_months
    
    # SHL parameters
    shl_amount = 0  # No SHL in base case
    shl_rate = 0.06 / 2
    
    # Run cached waterfall (rebuilds schedules internally)
    st.info(
        "ℹ️ Rezultati se ažuriraju automatski nakon klika na **🔄 Update Model** u sidebaru.",
        icon="ℹ️",
    )

    try:
        result = cached_run_waterfall(
            inputs=inputs,
            engine=engine,
            rate_per_period=rate,
            tenor_periods=tenor_periods,
            target_dscr=target_dscr,
            lockup_dscr=lockup_dscr,
            tax_rate=tax.corporate_rate,
            dsra_months=financing.dsra_months,
            shl_amount=shl_amount,
            shl_rate=shl_rate,
            discount_rate_project=0.0641,
            discount_rate_equity=0.0965,
        )
    except Exception as exc:
        st.error(
            f"❌ Waterfall izračun nije uspio: **{type(exc).__name__}**: {exc}\n\n"
            "Provjerite da EBITDA schedule nije nula i da je gearing ispod 90%."
        )
        st.stop()

    # Display summary
    st.subheader("📊 Waterfall Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Debt (Sculpted)", f"{result.sculpting_result.debt_keur:,.0f} k€",
                  help="Debt calculated via iterative DSCR targeting")
    with col2:
        st.metric("Avg DSCR", f"{result.avg_dscr:.3f}x",
                  help="Average DSCR over loan tenor")
    with col3:
        st.metric("Min DSCR", f"{result.min_dscr:.3f}x",
                  help="Minimum DSCR in any period")
    with col4:
        status = "✅" if result.sculpting_result.converged else "⚠️"
        st.metric("Sculpting", f"{status} {result.sculpting_result.iterations} iter",
                  help="Binary search iterations to converge")
    
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Min LLCR", f"{result.min_llcr:.2f}x",
                  help="Loan Life Coverage Ratio")
    with col6:
        st.metric("Min PLCR", f"{result.min_plcr:.2f}x",
                  help="Project Life Coverage Ratio")
    with col7:
        st.metric("Lockup Periods", f"{result.periods_in_lockup}",
                  help="Periods with DSCR < lockup threshold")
    with col8:
        st.metric("Total Distribution", f"{result.total_distribution_keur:,.0f} k€",
                  help="Total equity distributions")
    
    st.divider()
    
    # Returns section
    st.subheader("📈 Returns")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Project IRR", f"{result.project_irr * 100:.2f}%",
                  help="Unlevered project IRR (XIRR)")
    with col2:
        st.metric("Equity IRR", f"{result.equity_irr * 100:.2f}%",
                  help="Levered equity IRR (XIRR)")
    with col3:
        st.metric("Project NPV", f"{result.project_npv:,.0f} k€",
                  help="NPV at 6.41% discount rate")
    with col4:
        st.metric("Equity NPV", f"{result.equity_npv:,.0f} k€",
                  help="NPV at 9.65% discount rate")
    
    st.divider()
    
    # Waterfall table
    st.subheader("💵 Period Detail")
    
    waterfall_data = []
    for wp in result.periods:
        if not wp.year_index:  # Skip construction periods without year_index
            continue
            
        waterfall_data.append({
            "Period": wp.period,
            "Date": wp.date.strftime("%Y-%m") if wp.date else "—",
            "Year": wp.year_index,
            "Gen (MWh)": f"{wp.generation_mwh:,.0f}",
            "Revenue (k€)": f"{wp.revenue_keur:,.0f}",
            "OPEX (k€)": f"{wp.opex_keur:,.0f}",
            "EBITDA (k€)": f"{wp.ebitda_keur:,.0f}",
            "Tax (k€)": f"{wp.tax_keur:,.0f}",
            "Senior DS (k€)": f"{wp.senior_ds_keur:,.0f}",
            "CF (k€)": f"{wp.cf_after_reserves_keur:,.0f}",
            "DSCR": f"{wp.dscr:.2f}" if wp.dscr > 0 else "—",
            "LLCR": f"{wp.llcr:.2f}" if wp.llcr > 0 else "—",
            "Dist (k€)": f"{wp.distribution_keur:,.0f}",
            "Lockup": "🔒" if wp.lockup_active else "",
        })
    
    df_waterfall = pd.DataFrame(waterfall_data)
    
    # Display (values already formatted as strings)
    st.dataframe(df_waterfall, use_container_width=True, height=600)
    
    st.divider()
    
    # Chart: DSCR over time
    st.subheader("📉 DSCR Timeline")
    
    dscr_data = [(wp.year_index, wp.dscr) for wp in result.periods if wp.dscr > 0]
    if dscr_data:
        dscr_df = pd.DataFrame(dscr_data, columns=["Year", "DSCR"]).set_index("Year")
        
        # Add target line
        st.line_chart(dscr_df)
        
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"Target DSCR: {target_dscr:.2f}x | Lockup: {lockup_dscr:.2f}x")
        with col2:
            st.caption(f"Min: {result.min_dscr:.2f}x | Max: {result.max_dscr:.2f}x | Avg: {result.avg_dscr:.2f}x")
    
    st.divider()
    
    # Chart: Cumulative distribution
    st.subheader("📈 Cumulative Distributions")
    
    cum_dist = [(wp.year_index, wp.cum_distribution_keur) for wp in result.periods if wp.cum_distribution_keur > 0]
    if cum_dist:
        dist_df = pd.DataFrame(cum_dist, columns=["Year", "Cumulative Distribution (k€)"]).set_index("Year")
        st.line_chart(dist_df)
    
    st.divider()
    
    # Waterfall summary text
    with st.expander("📄 Waterfall Summary (Text)"):
        st.text(print_waterfall_summary(result))
    
    # vs Baseline comparison
    st.subheader("📐 vs Oborovo Baseline")
    
    baseline = {
        "Total CAPEX": ("56,899 k€", f"{total_capex:,.0f} k€"),
        "Project IRR": ("8.42%", f"{result.project_irr * 100:.2f}%"),
        "Equity IRR": ("11.00%", f"{result.equity_irr * 100:.2f}%"),
        "Avg DSCR": ("1.147x", f"{result.avg_dscr:.3f}x"),
        "Min DSCR": ("—", f"{result.min_dscr:.3f}x"),
    }
    
    comp_data = []
    for metric, (baseline_val, current_val) in baseline.items():
        diff = ""
        if "IRR" in metric or "DSCR" in metric:
            try:
                b = float(baseline_val.replace("%", "").replace("x", ""))
                c = float(current_val.replace("%", "").replace("x", ""))
                diff = f"{c - b:+.2f}"
            except:
                pass
        
        comp_data.append({
            "Metric": metric,
            "Baseline": baseline_val,
            "Current": current_val,
            "Diff": diff,
        })
    
    st.table(pd.DataFrame(comp_data).set_index("Metric"))