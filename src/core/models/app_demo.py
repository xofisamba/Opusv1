"""Complete demo of Pydantic models with Streamlit UI.

This module demonstrates:
1. All Pydantic models with validation
2. User-friendly error messages in Croatian
3. JSON export for Save Scenario functionality
4. Form inputs for each model group

Run with: streamlit run src/core/models/app_demo.py
"""
import streamlit as st
from datetime import date
from typing import Any
from pydantic import ValidationError

from src.core.models import (
    ProjectInfo, CapexItem, CapexStructure, OpexItem,
    TechnicalParams, RevenueParams, FinancingParams, TaxParams,
    ProjectInputs, ValidationError as PydanticValidationError
)
from src.core.models.inputs import ProjectInputs as NewProjectInputs
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


# =============================================================================
# JSON Export/Import (Save Scenario)
# =============================================================================
def render_json_export(inputs: ProjectInputs) -> None:
    """Show JSON export for Save Scenario."""
    st.subheader("📤 JSON Export (Copy for Save Scenario)")
    
    json_data = inputs.to_json_dict()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.json(json_data)
    with col2:
        st.caption("Za spremanje scenarija, kopirajte gornji JSON ili:")
        st.code(f"# Ili spremite direktno\nimport json\nwith open('scenario.json', 'w') as f:\n    json.dump({json_data}, f, indent=2)", language="python")
    
    # Download button
    import json
    st.download_button(
        label="⬇️ Download JSON",
        data=json.dumps(json_data, indent=2),
        file_name="oborovo_scenario.json",
        mime="application/json"
    )


# =============================================================================
# Form Sections
# =============================================================================
def render_project_section() -> ProjectInfo | None:
    """Render ProjectInfo form section."""
    with st.expander("📐 Project Info", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Project Name", value="Oborovo Solar PV")
            company = st.text_input("Company", value="AKE Med")
            country = st.text_input("Country ISO", value="HR", max_chars=2).upper()
        with col2:
            ff_date = st.date_input("Financial Close", value=date(2029, 6, 29))
            cod_date = st.date_input("COD Date", value=date(2030, 6, 29))
        
        col3, col4 = st.columns(2)
        with col3:
            horizon = st.number_input("Horizon (years)", min_value=10, max_value=50, value=30)
            months = st.number_input("Construction (months)", min_value=1, max_value=60, value=12)
        with col4:
            freq = st.selectbox("Period Frequency", ["Semestrial", "Annual", "Quarterly"], index=0)
        
        return ProjectInfo(
            name=name,
            company=company,
            country_iso=country,
            financial_close=ff_date,
            construction_months=months,
            cod_date=cod_date,
            horizon_years=horizon,
            period_frequency=freq,
        )


def render_technical_section() -> TechnicalParams | None:
    """Render TechnicalParams form section."""
    with st.expander("⚡ Technical", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            capacity = st.number_input("Capacity (MW)", min_value=1.0, max_value=2000.0, value=75.26, step=0.1)
            scenario = st.selectbox("Yield Scenario", ["P_50", "P90-10y", "P99-1y"], index=0)
            hours_p50 = st.number_input("P50 Hours", min_value=500.0, max_value=5000.0, value=1494.0)
        with col2:
            hours_p90 = st.number_input("P90-10y Hours", min_value=500.0, max_value=5000.0, value=1410.0)
            degradation = st.slider("PV Degradation (%)", 0.0, 20.0, 0.4, step=0.1) / 100
        
        avail = st.slider("Plant Availability (%)", 80.0, 100.0, 99.0, step=0.5) / 100
        
        return TechnicalParams(
            capacity_mw=capacity,
            yield_scenario=scenario,
            operating_hours_p50=hours_p50,
            operating_hours_p90_10y=hours_p90,
            pv_degradation=degradation,
            plant_availability=avail,
            grid_availability=0.99,
        )


def render_financing_section() -> FinancingParams | None:
    """Render FinancingParams form section."""
    with st.expander("🏦 Financing", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            gearing = st.slider("Gearing (%)", 0.0, 95.0, 75.24, step=0.1) / 100
            tenor = st.number_input("Debt Tenor (years)", min_value=1, max_value=30, value=14)
            base_rate = st.number_input("Base Rate (%)", 0.0, 15.0, 3.0, step=0.1) / 100
        with col2:
            margin = st.number_input("Margin (bps)", 0, 1000, 265, step=5)
            target_dscr = st.slider("Target DSCR (x)", 1.0, 2.0, 1.15, step=0.05)
            lockup_dscr = st.slider("Lockup DSCR (x)", 1.0, 1.5, 1.10, step=0.05)
        
        dsra = st.slider("DSRA Months", 0, 12, 6, step=1)
        
        return FinancingParams(
            gearing_ratio=gearing,
            senior_tenor_years=tenor,
            base_rate=base_rate,
            margin_bps=margin,
            target_dscr=target_dscr,
            lockup_dscr=lockup_dscr,
            dsra_months=dsra,
        )


def render_tax_section() -> TaxParams | None:
    """Render TaxParams form section."""
    with st.expander("🏛️ Tax", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            corp_rate = st.slider("Corporate Tax (%)", 0.0, 50.0, 10.0, step=0.5) / 100
            loss_years = st.number_input("Loss Carryforward (years)", 0, 20, 5)
        with col2:
            thin_cap = st.checkbox("Thin Cap Rule", value=False)
            wht_div = st.slider("WHT Dividends (%)", 0.0, 30.0, 5.0, step=0.5) / 100
        
        return TaxParams(
            corporate_rate=corp_rate,
            loss_carryforward_years=loss_years,
            thin_cap_enabled=thin_cap,
            wht_sponsor_dividends=wht_div,
        )


def render_revenue_section() -> RevenueParams | None:
    """Render RevenueParams form section."""
    with st.expander("💰 Revenue", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            tariff = st.number_input("PPA Tariff (€/MWh)", 0.0, 500.0, 57.0, step=1.0)
            ppa_term = st.number_input("PPA Term (years)", 1, 30, 12)
            ppa_index = st.slider("PPA Index (%)", 0.0, 20.0, 2.0, step=0.1) / 100
        with col2:
            market_inf = st.slider("Market Inflation (%)", 0.0, 20.0, 2.0, step=0.1) / 100
            bal_cost = st.slider("Balancing Cost (%)", 0.0, 50.0, 2.5, step=0.1) / 100
        
        return RevenueParams(
            ppa_base_tariff=tariff,
            ppa_term_years=ppa_term,
            ppa_index=ppa_index,
            market_inflation=market_inf,
            balancing_cost_pv=bal_cost,
        )


# =============================================================================
# Main Demo App
# =============================================================================
def main():
    st.set_page_config(
        page_title="Pydantic Validation Demo",
        page_icon="🧪",
        layout="wide"
    )
    
    st.title("🧪 Pydantic Validation Demo")
    st.caption("Testiraj validaciju s korisničkim porukama na hrvatskom")
    
    # Initialize session state for inputs
    if "demo_inputs" not in st.session_state:
        st.session_state.demo_inputs = ProjectInputs.create_default_oborovo()
    
    # Create tabs for different sections
    tab1, tab2, tab3 = st.tabs(["📝 Forms", "✅ Validation Test", "📤 JSON Export"])
    
    with tab1:
        st.subheader("Unesi parametre modela")
        
        # Try to create inputs from forms
        project = render_project_section()
        technical = render_technical_section()
        financing = render_financing_section()
        tax = render_tax_section()
        revenue = render_revenue_section()
        
        if st.button("🔄 Validate & Create Model", type="primary", use_container_width=True):
            try:
                # Build CapexStructure minimal for now
                capex = CapexStructure(
                    epc_contract=CapexItem(name="EPC", amount_keur=26430, y0_share=0.0, spending_profile=(0.083,)*12),
                    production_units=CapexItem(name="Units", amount_keur=10912.7, y0_share=0.0, spending_profile=(0.083,)*12),
                    epc_other=CapexItem(name="Other", amount_keur=3200, y0_share=0.0),
                    grid_connection=CapexItem(name="Grid", amount_keur=1800, y0_share=0.0),
                    ops_prep=CapexItem(name="Ops", amount_keur=500, y0_share=0.0),
                    insurances=CapexItem(name="Ins", amount_keur=400, y0_share=0.0),
                    lease_tax=CapexItem(name="Lease", amount_keur=200, y0_share=0.0),
                    construction_mgmt_a=CapexItem(name="CM A", amount_keur=800, y0_share=0.0),
                    commissioning=CapexItem(name="Comm", amount_keur=300, y0_share=0.0),
                    audit_legal=CapexItem(name="Audit", amount_keur=200, y0_share=0.0),
                    construction_mgmt_b=CapexItem(name="CM B", amount_keur=400, y0_share=0.0),
                    contingencies=CapexItem(name="Cont", amount_keur=1986.4, y0_share=0.0),
                    taxes=CapexItem(name="Taxes", amount_keur=150, y0_share=0.0),
                    project_acquisition=CapexItem(name="Acq", amount_keur=1000, y0_share=0.0),
                    project_rights=CapexItem(name="Rights", amount_keur=3024.5, y0_share=0.0),
                )
                
                # Build OPEX
                opex = (
                    OpexItem(name="Technical Management", y1_amount_keur=198, annual_inflation=0.02),
                    OpexItem(name="Insurance", y1_amount_keur=255, annual_inflation=0.02),
                    OpexItem(name="Other", y1_amount_keur=900, annual_inflation=0.02),
                )
                
                inputs = ProjectInputs(
                    info=project,
                    technical=technical,
                    capex=capex,
                    opex=opex,
                    revenue=revenue,
                    financing=financing,
                    tax=tax,
                )
                
                st.session_state.demo_inputs = inputs
                st.success("✅ Model validiran! Pogledaj JSON export tab.")
                
            except PydanticValidationError as exc:
                show_validation_errors(exc)
    
    with tab2:
        st.subheader("Test validacije - pokušaj unijeti nevalidne vrijednosti:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.expander("❌ Gearing > 95%"):
                try:
                    FinancingParams(gearing_ratio=1.5)
                except PydanticValidationError as exc:
                    show_validation_errors(exc)
            
            with st.expander("❌ Target DSCR < 1.0"):
                try:
                    FinancingParams(target_dscr=0.95)
                except PydanticValidationError as exc:
                    show_validation_errors(exc)
        
        with col2:
            with st.expander("❌ Corporate Tax > 50%"):
                try:
                    TaxParams(corporate_rate=0.75)
                except PydanticValidationError as exc:
                    show_validation_errors(exc)
            
            with st.expander("❌ Capacity <= 0"):
                try:
                    TechnicalParams(capacity_mw=-10, yield_scenario="P_50", operating_hours_p50=1000)
                except PydanticValidationError as exc:
                    show_validation_errors(exc)
    
    with tab3:
        st.subheader("Trenutni model")
        
        inputs = st.session_state.demo_inputs
        summary = inputs.get_model_summary()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Projekt", summary["project"])
        with col2:
            st.metric("Kapacitet", f"{summary['capacity_mw']} MW")
        with col3:
            st.metric("CAPEX", f"{summary['total_capex_keur']:,.0f} k€")
        with col4:
            st.metric("Rate", summary["all_in_rate"])
        
        st.divider()
        render_json_export(inputs)
        
        # ================================================================
        # WATERFALL RESULTS
        # ================================================================
        st.divider()
        st.subheader("📊 Waterfall Rezultati")
        
        try:
            # Build engine from inputs
            engine = _build_engine_from_inputs(inputs)
            
            # Run waterfall calculation
            rate = inputs.financing.all_in_rate / 2
            tenor_periods = inputs.financing.senior_tenor_years * 2
            
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
            
            # Display waterfall metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Debt (k€)", f"{result.sculpting_result.debt_keur:,.0f}")
            with col2:
                st.metric("Avg DSCR", f"{result.avg_dscr:.3f}x")
            with col3:
                st.metric("Project IRR", f"{result.project_irr * 100:.2f}%")
            with col4:
                st.metric("Equity IRR", f"{result.equity_irr * 100:.2f}%")
            
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("Min LLCR", f"{result.min_llcr:.2f}x")
            with col6:
                st.metric("Min PLCR", f"{result.min_plcr:.2f}x")
            with col7:
                st.metric("Min DSCR", f"{result.min_dscr:.3f}x")
            with col8:
                status = "✅" if result.sculpting_result.converged else "⚠️"
                st.metric("Sculpting", f"{status} {result.sculpting_result.iterations} iter")
            
            st.success("✅ Waterfall izračun završen!")
            
        except Exception as exc:
            st.error(f"❌ Waterfall greška: {type(exc).__name__}: {exc}")
        
        st.divider()
        
        st.divider()
        st.subheader("📋 Detalji")
        
        cols = st.columns(3)
        with cols[0]:
            st.caption("**Info**")
            st.json(inputs.info.to_json_dict())
        with cols[1]:
            st.caption("**Technical**")
            st.json(inputs.technical.to_json_dict())
        with cols[2]:
            st.caption("**Financing**")
            st.json(inputs.financing.to_json_dict())


if __name__ == "__main__":
    main()
