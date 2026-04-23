"""Charts page - Revenue, OPEX, DSCR, Waterfall visualizations."""
import streamlit as st
import pandas as pd

from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
from domain.opex.projections import opex_schedule_annual
from domain.financing.schedule import standard_amortization, senior_debt_amount


def render_charts(inputs, engine) -> None:
    st.header("📈 Financial Charts")
    
    capex = inputs.capex
    financing = inputs.financing
    
    # Get all periods
    periods = list(engine.periods())
    op_periods = [p for p in periods if p.is_operation]
    
    # Build schedules
    revenue = full_revenue_schedule(inputs, engine)
    generation = full_generation_schedule(inputs, engine)
    opex_annual = opex_schedule_annual(inputs, inputs.info.horizon_years)
    
    # Debt schedule
    total_capex = capex.total_capex
    debt = senior_debt_amount(total_capex, financing.gearing_ratio)
    rate_per_period = financing.all_in_rate / 2
    tenor_periods = financing.senior_tenor_years * 2
    amort_schedule = standard_amortization(debt, rate_per_period, min(tenor_periods, len(op_periods)))
    
    # Annual summaries
    years = list(range(1, inputs.info.horizon_years + 1))
    
    annual_data = []
    for year in years:
        # Revenue - sum all periods for this year
        rev = sum(v for p in op_periods 
                if p.year_index == year 
                for k, v in [(p.index, revenue.get(p.index, 0))])
        
        # Generation
        gen = sum(v for p in op_periods 
                 if p.year_index == year 
                 for k, v in [(p.index, generation.get(p.index, 0))])
        
        # OPEX
        opex = opex_annual.get(year, 0)
        
        # EBITDA
        ebitda = rev - opex
        
        # Debt service (for first half of periods in this year)
        if year <= financing.senior_tenor_years:
            year_period_idx = year - 1
            if year_period_idx < len(amort_schedule):
                ds = amort_schedule[year_period_idx].total_keur * 2  # Annualize
            else:
                ds = 0
        else:
            ds = 0
        
        annual_data.append({
            "Year": year,
            "Generation (MWh)": gen,
            "Revenue (k€)": rev,
            "OPEX (k€)": opex,
            "EBITDA (k€)": ebitda,
            "Debt Service (k€)": ds,
            "DSCR": ebitda / ds if ds > 0 else None,
        })
    
    df_annual = pd.DataFrame(annual_data)
    
    # Tab layout
    tab1, tab2, tab3, tab4 = st.tabs(["Revenue", "OPEX", "DSCR", "Waterfall"])
    
    with tab1:
        st.subheader("Revenue & Generation")
        
        # Generation chart
        st.write("**Generation**")
        chart_gen = df_annual.set_index("Year")[["Generation (MWh)"]]
        st.bar_chart(chart_gen)
        
        st.divider()
        
        # Revenue chart
        st.write("**Revenue**")
        chart_rev = df_annual.set_index("Year")[["Revenue (k€)"]]
        st.bar_chart(chart_rev)
        
        st.divider()
        
        # Revenue breakdown (if multiple revenue streams)
        st.write("**Revenue Table (k€)**")
        display_cols = ["Year", "Generation (MWh)", "Revenue (k€)", "EBITDA (k€)"]
        st.dataframe(df_annual[display_cols].set_index("Year"), width="stretch")
    
    with tab2:
        st.subheader("Operating Expenditure")
        
        chart_opex = df_annual.set_index("Year")[["OPEX (k€)"]]
        st.bar_chart(chart_opex)
        
        st.divider()
        
        # OPEX per MW
        cap_mw = inputs.technical.capacity_mw
        df_annual["OPEX/MW"] = df_annual["OPEX (k€)"] / cap_mw
        
        st.write("**OPEX Intensity**")
        chart_mw = df_annual.set_index("Year")[["OPEX/MW"]]
        st.line_chart(chart_mw)
        
        st.divider()
        
        st.write("**OPEX Table (k€)**")
        st.dataframe(df_annual[["Year", "OPEX (k€)", "OPEX/MW"]].set_index("Year"), width="stretch")
    
    with tab3:
        st.subheader("Debt Service Coverage Ratio")
        
        dscr_df = df_annual[df_annual["DSCR"].notna()][["Year", "DSCR"]].copy()
        dscr_df = dscr_df.set_index("Year")
        
        # Target line at 1.15
        target_line = pd.DataFrame({"DSCR": [financing.target_dscr] * len(dscr_df)}, index=dscr_df.index)
        
        st.write("**DSCR vs Target**")
        st.line_chart(dscr_df)
        
        st.caption(f"Target DSCR: {financing.target_dscr:.2f}x | Average: {dscr_df['DSCR'].mean():.2f}x | Min: {dscr_df['DSCR'].min():.2f}x")
        
        st.divider()
        
        # Debt service chart
        st.write("**Debt Service Schedule**")
        ds_df = df_annual[df_annual["Debt Service (k€)"] > 0][["Year", "Debt Service (k€)"]].set_index("Year")
        st.bar_chart(ds_df)
        
        st.divider()
        
        st.write("**DSCR Table**")
        st.dataframe(df_annual[df_annual["DSCR"].notna()][["Year", "EBITDA (k€)", "Debt Service (k€)", "DSCR"]].set_index("Year"), width="stretch")
    
    with tab4:
        st.subheader("Cash Flow Waterfall")
        
        # Simplified waterfall for display
        waterfall_data = []
        cumulative = -total_capex  # Initial investment
        
        for year in range(1, min(11, inputs.info.horizon_years + 1)):
            ebitda = df_annual.loc[df_annual["Year"] == year, "EBITDA (k€)"].values[0]
            ds = df_annual.loc[df_annual["Year"] == year, "Debt Service (k€)"].values[0]
            
            cf_after_ds = ebitda - ds
            cumulative += cf_after_ds
            
            waterfall_data.append({
                "Year": year,
                "EBITDA": ebitda,
                "Debt Service": ds,
                "CF After DS": cf_after_ds,
                "Cumulative": cumulative,
            })
        
        wf_df = pd.DataFrame(waterfall_data)
        
        st.write("**Cumulative Cash Position**")
        st.line_chart(wf_df.set_index("Year")[["Cumulative"]])
        
        st.divider()
        
        st.write("**Annual Cash Flow**")
        st.bar_chart(wf_df.set_index("Year")[["CF After DS"]])
        
        st.divider()
        
        st.write("**Waterfall Table**")
        st.dataframe(wf_df.set_index("Year"), width="stretch")
    
    st.divider()
    
    # Advanced: Semi-annual breakdown
    with st.expander("📅 Semi-Annual Detail", expanded=False):
        st.subheader("Semi-Annual Period Detail")
        
        semi_data = []
        for p in op_periods[:20]:  # First 20 periods
            rev = revenue.get(p.index, 0)
            gen = generation.get(p.index, 0)
            
            # OPEX for this half-year (annual / 2)
            opex = opex_annual.get(p.year_index, 0) / 2
            
            # DS (only in first half of year for annual debt service)
            if p.period_in_year == 1 and p.year_index <= financing.senior_tenor_years:
                if p.year_index - 1 < len(amort_schedule):
                    ds = amort_schedule[p.year_index - 1].total_keur
                else:
                    ds = 0
            else:
                ds = 0
            
            ebitda = rev - opex
            cf = ebitda - ds
            
            semi_data.append({
                "Period": p.index,
                "Date": p.end_date.strftime("%Y-%m"),
                "Year": p.year_index,
                "Gen (MWh)": gen,
                "Revenue (k€)": rev,
                "OPEX (k€)": opex,
                "EBITDA (k€)": ebitda,
                "DS (k€)": ds,
                "CF (k€)": cf,
            })
        
        semi_df = pd.DataFrame(semi_data)
        st.dataframe(semi_df.set_index("Period"), width="stretch")