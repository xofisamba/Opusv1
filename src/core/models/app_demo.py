"""Complete demo of Pydantic models with Streamlit UI.

This module demonstrates:
1. All Pydantic models with validation
2. User-friendly error messages in Croatian
3. Waterfall results with full integration
4. Plotly charts for visualization

Run with: streamlit run src/core/models/app_demo.py
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from typing import Any
import pandas as pd

from src.core.models import (
    ProjectInfo, CapexItem, CapexStructure, OpexItem,
    TechnicalParams, RevenueParams, FinancingParams, TaxParams,
    ProjectInputs, ValidationError as PydanticValidationError
)
from domain.waterfall.waterfall_engine import cached_run_waterfall
from domain.period_engine import PeriodEngine
from app.builder import _build_engine_from_inputs


# =============================================================================
# Error Display
# =============================================================================
def show_validation_errors(exc: PydanticValidationError) -> None:
    """Convert Pydantic ValidationError to user-friendly HR messages."""
    for error in exc.errors():
        loc = " → ".join(str(l) for l in error["loc"])
        msg = error["msg"]
        
        if msg.startswith("Input should be greater than"):
            friendly = "Iznos mora biti veći od nule."
        elif msg.startswith("Input should be less than"):
            friendly = "Iznos mora biti manji od nule."
        elif msg.startswith("Input should be between"):
            ctx = error.get("ctx", {})
            friendly = f"Vrijednost mora biti između {ctx.get('ge', 0)} i {ctx.get('le', 0)}."
        elif msg.startswith("Input should be greater than or equal"):
            friendly = "Iznos mora biti veći ili jednak dozvoljenom minimumu."
        elif msg.startswith("Input should be less than or equal"):
            friendly = "Iznos mora biti manji ili jednak dozvoljenom maksimumu."
        elif msg.startswith("Field required"):
            friendly = f"Polje '{loc}' je obavezno."
        elif "yield_scenario" in str(loc):
            friendly = "Nedozvoljeni scenario. Dopuštene opcije: P_50, P90-10y, P99-1y"
        elif "ppa_term" in str(loc):
            friendly = "PPA rok mora biti između 1 i 30 godina."
        elif "country" in str(loc).lower():
            friendly = "ISO kod mora biti točno 2 velika slova (npr. 'HR', 'DE')."
        elif "date" in str(loc).lower():
            friendly = "Neispravan format datuma."
        else:
            friendly = msg
        
        st.error(f"  • {friendly} (polje: {loc})")


def create_waterfall_chart(result) -> go.Figure:
    """Create waterfall chart showing Debt vs Equity over time."""
    if not result.periods:
        return go.Figure()
    
    periods = result.periods
    dates = [f"Y{p.year_index+1}" for p in periods]
    
    # Debt balance over time
    debt_balance = []
    for p in periods:
        # Calculate remaining debt balance
        remaining = p.senior_interest_keur + p.senior_principal_keur
        # Approximate balance from cumulative principal repaid
        total_debt = result.sculpting_result.debt_keur if result.sculpting_result else 0
        repaid = sum(wp.senior_principal_keur for wp in periods[:periods.index(p)])
        remaining = max(0, total_debt - repaid)
        debt_balance.append(remaining)
    
    fig = go.Figure()
    
    # Add debt trace
    fig.add_trace(go.Scatter(
        x=dates, y=debt_balance,
        name="Debt Balance",
        stackgroup="one",
        fillcolor="rgba(255, 100, 100, 0.5)",
        line=dict(color="red", width=2)
    ))
    
    # Add equity trace (cumulative distributions)
    equity = [result.sculpting_result.debt_keur if result.sculpting_result else 0] * len(periods)
    fig.add_trace(go.Scatter(
        x=dates, y=[e - d for e, d in zip(equity, debt_balance)],
        name="Equity",
        stackgroup="one",
        fillcolor="rgba(100, 200, 100, 0.5)",
        line=dict(color="green", width=2)
    ))
    
    fig.update_layout(
        title="Debt vs Equity Over Project Life",
        xaxis_title="Period",
        yaxis_title="Amount (kEUR)",
        hovermode="x unified",
        height=400
    )
    
    return fig


def create_dscr_chart(result) -> go.Figure:
    """Create DSCR timeline chart."""
    if not result.periods:
        return go.Figure()
    
    periods = result.periods
    dates = [f"Y{p.year_index+1}" for p in periods]
    dscrs = [p.dscr for p in periods]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates, y=dscrs,
        name="DSCR",
        line=dict(color="blue", width=2),
        mode="lines+markers"
    ))
    
    # Add target DSCR line
    fig.add_hline(
        y=1.15, 
        line_dash="dash", 
        annotation_text="Target 1.15x",
        line_color="orange"
    )
    
    fig.update_layout(
        title="DSCR Over Time",
        xaxis_title="Period",
        yaxis_title="DSCR (x)",
        hovermode="x unified",
        height=350
    )
    
    return fig


def create_cashflow_chart(result) -> go.Figure:
    """Create cash flow waterfall chart."""
    if not result.periods:
        return go.Figure()
    
    periods = result.periods
    
    # Aggregate by year
    years = {}
    for p in periods:
        y = p.year_index
        if y not in years:
            years[y] = {"revenue": 0, "opex": 0, "debt_service": 0, "distribution": 0}
        years[y]["revenue"] += p.revenue_keur
        years[y]["opex"] += p.opex_keur
        years[y]["debt_service"] += p.senior_ds_keur
        years[y]["distribution"] += p.distribution_keur
    
    year_labels = [f"Year {y+1}" for y in sorted(years.keys())]
    
    fig = go.Figure()
    
    # Revenue bars
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[years[y]["revenue"] for y in sorted(years.keys())],
        name="Revenue",
        marker_color="green"
    ))
    
    # OPEX (negative)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[-years[y]["opex"] for y in sorted(years.keys())],
        name="OPEX",
        marker_color="red"
    ))
    
    # Debt Service
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[-years[y]["debt_service"] for y in sorted(years.keys())],
        name="Debt Service",
        marker_color="orange"
    ))
    
    # Distributions
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[years[y]["distribution"] for y in sorted(years.keys())],
        name="Distribution",
        marker_color="blue"
    ))
    
    fig.update_layout(
        title="Annual Cash Flows",
        xaxis_title="Year",
        yaxis_title="Amount (kEUR)",
        barmode="relative",
        hovermode="x unified",
        height=400
    )
    
    return fig


# =============================================================================
# Main Demo App
# =============================================================================
def main():
    st.set_page_config(
        page_title="Oborovo Financial Model",
        page_icon="☀️",
        layout="wide"
    )
    
    st.title("☀️ Oborovo Solar PV - Financial Model")
    st.caption("Model s Pydantic validacijom")
    
    # Initialize session state for inputs
    if "demo_inputs" not in st.session_state:
        st.session_state.demo_inputs = ProjectInputs.create_default_oborovo()
    
    # ================================================================
    # WATERFALL RESULTS - Always calculate and show
    # ================================================================
    inputs = st.session_state.demo_inputs
    
    try:
        # Build engine from inputs
        engine = _build_engine_from_inputs(inputs)
        
        # Run waterfall calculation
        rate = inputs.financing.all_in_rate / 2
        tenor_periods = inputs.financing.senior_tenor_years * 2
        
        with st.spinner("Računam waterfall..."):
            result = cached_run_waterfall(
                inputs=inputs,
                engine=engine,
                rate_per_period=rate,
                tenor_periods=tenor_periods,
                target_dscr=inputs.financing.target_dscr,
                lockup_dscr=inputs.financing.lockup_dscr,
                tax_rate=inputs.tax.corporate_rate,
                dsra_months=inputs.financing.dsra_months,
                shl_amount=0,
                shl_rate=0.06 / 2,
                discount_rate_project=0.0641,
                discount_rate_equity=0.0965,
            )
        
        # ================================================================
        # TAB 1: KPI Dashboard
        # ================================================================
        tab_kpi, tab_waterfall, tab_charts = st.tabs([
            "📊 KPI Dashboard",
            "📋 Waterfall Detalji",
            "📈 Grafikoni"
        ])
        
        with tab_kpi:
            st.subheader("Ključni Pokazatelji")
            
            # Top level metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "Project IRR",
                    f"{result.project_irr * 100:.2f}%",
                    help="IRR cijelog projekta"
                )
            with col2:
                irr_val = result.equity_irr * 100 if result.equity_irr else 0
                st.metric(
                    "Equity IRR",
                    f"{irr_val:.2f}%",
                    help="IRR na ugrađeni kapital"
                )
            with col3:
                st.metric("Avg DSCR", f"{result.avg_dscr:.3f}x")
            with col4:
                st.metric("Min DSCR", f"{result.min_dscr:.3f}x")
            
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("Min LLCR", f"{result.min_llcr:.2f}x")
            with col6:
                st.metric("Min PLCR", f"{result.min_plcr:.2f}x")
            with col7:
                debt = result.sculpting_result.debt_keur if result.sculpting_result else 0
                st.metric("Debt (kEUR)", f"{debt:,.0f}")
            with col8:
                converged = result.sculpting_result.converged if result.sculpting_result else False
                status = "✅" if converged else "⚠️"
                iter_count = result.sculpting_result.iterations if result.sculpting_result else 0
                st.metric("Sculpting", f"{status} {iter_count}x")
            
            st.divider()
            
            # Financial summary
            st.subheader("Financijski Sažetak")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Ukupni Prihodi", f"{result.total_revenue_keur:,.0f} kEUR")
            with col2:
                st.metric("Ukupni EBITDA", f"{result.total_ebitda_keur:,.0f} kEUR")
            with col3:
                st.metric("Ukupni OPEX", f"{result.total_opex_keur:,.0f} kEUR")
            
            col4, col5, col6 = st.columns(3)
            with col4:
                st.metric("Senior Debt Service", f"{result.total_senior_ds_keur:,.0f} kEUR")
            with col5:
                st.metric("Porezi", f"{result.total_tax_keur:,.0f} kEUR")
            with col6:
                st.metric("Distributions", f"{result.total_distribution_keur:,.0f} kEUR")
        
        with tab_waterfall:
            st.subheader("Debt Service Schedule")
            
            if result.periods:
                # Build dataframe for display
                data = []
                for p in result.periods:
                    data.append({
                        "Period": p.period,
                        "Year": p.year_index + 1,
                        "Date": p.date.strftime("%Y-%m-%d"),
                        "Revenue (k€)": round(p.revenue_keur, 0),
                        "OPEX (k€)": round(p.opex_keur, 0),
                        "EBITDA (k€)": round(p.ebitda_keur, 0),
                        "Senior Interest (k€)": round(p.senior_interest_keur, 1),
                        "Senior Principal (k€)": round(p.senior_principal_keur, 1),
                        "Senior DS (k€)": round(p.senior_ds_keur, 1),
                        "DSCR": round(p.dscr, 3) if p.dscr > 0 else "-",
                        "LLCR": round(p.llcr, 3) if p.llcr > 0 else "-",
                        "PLCR": round(p.plcr, 3) if p.plcr > 0 else "-",
                        "Distribution (k€)": round(p.distribution_keur, 0),
                        "Lockup": "🔒" if p.lockup_active else "",
                    })
                
                df = pd.DataFrame(data)
                
                # Display with formatting
                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True
                )
                
                # Download button
                csv = df.to_csv(index=False)
                st.download_button(
                    "⬇️ Download CSV",
                    csv,
                    file_name="waterfall_schedule.csv",
                    mime="text/csv"
                )
            else:
                st.info("Nema dostupnih perioda.")
        
        with tab_charts:
            st.subheader("Vizualizacije")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.plotly_chart(create_dscr_chart(result), width="stretch")
            
            with col2:
                st.plotly_chart(create_waterfall_chart(result), width="stretch")
            
            st.plotly_chart(create_cashflow_chart(result), width="stretch")
        
        st.success("✅ Model izračunat!")
        
    except Exception as exc:
        st.error(f"❌ Greška: {type(exc).__name__}: {exc}")
        import traceback
        st.code(traceback.format_exc())
    
    st.divider()
    
    # ================================================================
    # Model Configuration (Forms)
    # ================================================================
    with st.expander("⚙️ Konfiguracija Modela", expanded=False):
        st.subheader("Parametri Modela")
        
        col1, col2 = st.columns(2)
        
        with col1:
            capacity = st.number_input(
                "Capacity (MW)", 
                min_value=1.0, max_value=2000.0, 
                value=inputs.technical.capacity_mw, step=0.1,
                key="cap_mw"
            )
            tariff = st.number_input(
                "PPA Tariff (€/MWh)", 
                0.0, 500.0, 
                value=inputs.revenue.ppa_base_tariff, step=1.0,
                key="ppa_tariff"
            )
            horizon = st.number_input(
                "Horizon (years)", 
                min_value=10, max_value=50, 
                value=inputs.info.horizon_years,
                key="horizon"
            )
        
        with col2:
            gearing = st.slider(
                "Gearing (%)", 
                0.0, 95.0, 
                value=inputs.financing.gearing_ratio * 100, step=0.1,
                key="gearing"
            ) / 100
            tenor = st.number_input(
                "Debt Tenor (years)", 
                min_value=1, max_value=30, 
                value=inputs.financing.senior_tenor_years,
                key="tenor"
            )
            target_dscr = st.slider(
                "Target DSCR (x)", 
                1.0, 2.0, 
                value=inputs.financing.target_dscr, step=0.05,
                key="target_dscr"
            )
        
        if st.button("🔄 Ažuriraj Model", type="primary"):
            # Update inputs
            inputs.info.horizon_years = horizon
            inputs.technical.capacity_mw = capacity
            inputs.revenue.ppa_base_tariff = tariff
            inputs.financing.gearing_ratio = gearing
            inputs.financing.senior_tenor_years = tenor
            inputs.financing.target_dscr = target_dscr
            
            st.session_state.demo_inputs = inputs
            st.rerun()


if __name__ == "__main__":
    main()