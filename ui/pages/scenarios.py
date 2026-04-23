"""Scenario Manager - Save, Load, and Compare Project Scenarios.

Project finance analysts typically work with 3 scenarios:
- Base Case (P50 + current tariff)
- Optimistic (P50 + high tariff)  
- Stress Case (P90 + low tariff)

This module provides infrastructure for managing scenarios using
ProjectInputs frozen dataclass serialization.
"""
import streamlit as st
import pandas as pd
from typing import Dict, Callable, Optional

from domain.inputs import ProjectInputs


def render_scenario_manager(
    current_inputs: ProjectInputs,
    run_model_fn: Optional[Callable] = None
) -> None:
    """Render scenario manager UI.
    
    Args:
        current_inputs: Current ProjectInputs from session state
        run_model_fn: Optional function(inputs) -> dict with KPI results
                     If not provided, shows inputs without calculated results
    """
    st.subheader("📋 Scenario Manager")
    
    # Initialize saved_scenarios in session state
    if 'saved_scenarios' not in st.session_state:
        st.session_state.saved_scenarios = {}
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        st.markdown("**Save Current Scenario**")
        scenario_name = st.text_input(
            "Scenario Name",
            value="Base Case",
            key="new_scenario_name"
        )
        
        if st.button("💾 Save Scenario", width="stretch"):
            # Serialize current inputs
            scenario_data = _serialize_inputs(current_inputs)
            st.session_state.saved_scenarios[scenario_name] = scenario_data
            st.success(f'✅ Scenario "{scenario_name}" saved.')
    
    with col1:
        saved = st.session_state.get('saved_scenarios', {})
        
        if not saved:
            st.info("📝 No scenarios saved yet. Configure your model and save it above.")
            return
        
        # Display saved scenarios
        st.markdown(f"**Saved Scenarios ({len(saved)})**")
        
        for name in list(saved.keys()):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.text(f"📁 {name}")
            with col_b:
                if st.button("🗑️", key=f"delete_{name}"):
                    del st.session_state.saved_scenarios[name]
                    st.rerun()
        
        st.divider()
        
        # Load scenario
        st.markdown("**Load Scenario**")
        scenario_to_load = st.selectbox(
            "Select scenario to load",
            [""] + list(saved.keys()),
            key="scenario_to_load"
        )
        
        if scenario_to_load and st.button("📥 Load Selected Scenario"):
            loaded_inputs = _deserialize_inputs(saved[scenario_to_load])
            _apply_inputs_to_session(loaded_inputs)
            st.success(f"✅ Loaded '{scenario_to_load}'")
            st.rerun()
    
    st.divider()
    
    # === KPI Comparison Table ===
    if saved and run_model_fn:
        st.subheader("📊 KPI Comparison")
        
        rows = []
        for name, data in saved.items():
            inputs = _deserialize_inputs(data)
            results = run_model_fn(inputs)
            
            rows.append({
                "Scenario": name,
                "Capacity (MW)": f"{inputs.technical.capacity_mw:.2f}",
                "P50 Yield (hrs)": f"{inputs.technical.operating_hours_p50:.0f}",
                "PPA Tariff (€/MWh)": f"{inputs.revenue.ppa_base_tariff:.1f}",
                "Gearing": f"{inputs.financing.gearing_ratio:.0%}",
                "Target DSCR": f"{inputs.financing.target_dscr:.2f}x",
                "Project IRR": f"{results.get('project_irr', 0) * 100:.2f}%",
                "Equity IRR": f"{results.get('equity_irr', 0) * 100:.2f}%",
                "Avg DSCR": f"{results.get('avg_dscr', 0):.3f}x",
                "Min DSCR": f"{results.get('min_dscr', 0):.3f}x",
                "NPV (k€)": f"{results.get('npv_equity', 0):,.0f}",
            })
        
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)
        
    elif saved:
        # Show inputs comparison without calculated results
        st.subheader("📋 Input Parameters Comparison")
        
        rows = []
        for name, data in saved.items():
            inputs = _deserialize_inputs(data)
            rows.append({
                "Scenario": name,
                "Capacity (MW)": f"{inputs.technical.capacity_mw:.2f}",
                "P50 (hrs)": f"{inputs.technical.operating_hours_p50:.0f}",
                "P90 (hrs)": f"{inputs.technical.operating_hours_p90_10y:.0f}",
                "Tariff (€/MWh)": f"{inputs.revenue.ppa_base_tariff:.1f}",
                "PPA Index": f"{inputs.revenue.ppa_index:.1%}",
                "Gearing": f"{inputs.financing.gearing_ratio:.0%}",
                "Debt Tenor": f"{inputs.financing.senior_tenor_years}y",
                "Base Rate": f"{inputs.financing.base_rate:.2%}",
                "Target DSCR": f"{inputs.financing.target_dscr:.2f}x",
            })
        
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)
    
    # Export/Import
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Export Scenarios**")
        if saved:
            export_json = _serialize_scenarios(saved)
            st.download_button(
                "📥 Download JSON",
                export_json.encode(),
                file_name="scenarios.json",
                mime="application/json"
            )
    
    with col2:
        st.markdown("**Import Scenarios**")
        uploaded = st.file_uploader("Upload JSON", type="json", key="scenario_upload")
        if uploaded:
            try:
                import json
                imported = json.loads(uploaded.read())
                count = 0
                for name, data in imported.items():
                    st.session_state.saved_scenarios[name] = data
                    count += 1
                st.success(f"✅ Imported {count} scenarios")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Import failed: {e}")


def _serialize_inputs(inputs: ProjectInputs) -> dict:
    """Serialize ProjectInputs to dict for JSON storage."""
    return {
        "info": {
            "name": inputs.info.name,
            "company": inputs.info.company,
            "code": inputs.info.code,
            "country_iso": inputs.info.country_iso,
            "financial_close": inputs.info.financial_close.isoformat(),
            "construction_months": inputs.info.construction_months,
            "cod_date": inputs.info.cod_date.isoformat(),
            "horizon_years": inputs.info.horizon_years,
            "period_frequency": inputs.info.period_frequency.value,
        },
        "technical": {
            "capacity_mw": inputs.technical.capacity_mw,
            "yield_scenario": inputs.technical.yield_scenario.value if hasattr(inputs.technical.yield_scenario, 'value') else str(inputs.technical.yield_scenario),
            "operating_hours_p50": inputs.technical.operating_hours_p50,
            "operating_hours_p90_10y": inputs.technical.operating_hours_p90_10y,
            "pv_degradation": inputs.technical.pv_degradation,
            "plant_availability": inputs.technical.plant_availability,
            "grid_availability": inputs.technical.grid_availability,
        },
        "revenue": {
            "ppa_base_tariff": inputs.revenue.ppa_base_tariff,
            "ppa_term_years": inputs.revenue.ppa_term_years,
            "ppa_index": inputs.revenue.ppa_index,
            "market_prices_curve": list(inputs.revenue.market_prices_curve) if inputs.revenue.market_prices_curve else [],
        },
        "financing": {
            "gearing_ratio": inputs.financing.gearing_ratio,
            "senior_tenor_years": inputs.financing.senior_tenor_years,
            "base_rate": inputs.financing.base_rate,
            "margin_bps": inputs.financing.margin_bps,
            "target_dscr": inputs.financing.target_dscr,
            "lockup_dscr": inputs.financing.lockup_dscr,
            "dsra_months": inputs.financing.dsra_months,
        },
    }


def _deserialize_inputs(data: dict) -> ProjectInputs:
    """Deserialize dict back to ProjectInputs."""
    from datetime import date
    from domain.inputs import PeriodFrequency
    
    info = ProjectInputs.create_default_oborovo().info
    info_dict = data.get("info", {})
    
    info = type(info)(
        name=info_dict.get("name", "Project"),
        company=info_dict.get("company", "Company"),
        code=info_dict.get("code", "PROJECT"),
        country_iso=info_dict.get("country_iso", "HR"),
        financial_close=date.fromisoformat(info_dict.get("financial_close", "2025-01-01")),
        construction_months=info_dict.get("construction_months", 12),
        cod_date=date.fromisoformat(info_dict.get("cod_date", "2026-01-01")),
        horizon_years=info_dict.get("horizon_years", 30),
        period_frequency=PeriodFrequency[info_dict.get("period_frequency", "SEMESTRIAL")],
    )
    
    tech_dict = data.get("technical", {})
    from domain.inputs import TechnicalParams, YieldScenario
    technical = TechnicalParams(
        capacity_mw=tech_dict.get("capacity_mw", 53.63),
        yield_scenario=YieldScenario[tech_dict.get("yield_scenario", "P50")],
        operating_hours_p50=tech_dict.get("operating_hours_p50", 1494),
        operating_hours_p90_10y=tech_dict.get("operating_hours_p90_10y", 1410),
        pv_degradation=tech_dict.get("pv_degradation", 0.004),
        plant_availability=tech_dict.get("plant_availability", 0.99),
        grid_availability=tech_dict.get("grid_availability", 0.99),
    )
    
    rev_dict = data.get("revenue", {})
    from domain.inputs import RevenueParams
    market_curve = tuple(rev_dict.get("market_prices_curve", []))
    revenue = RevenueParams(
        ppa_base_tariff=rev_dict.get("ppa_base_tariff", 65.0),
        ppa_term_years=rev_dict.get("ppa_term_years", 12),
        ppa_index=rev_dict.get("ppa_index", 0.02),
        market_prices_curve=market_curve,
    )
    
    fin_dict = data.get("financing", {})
    from domain.inputs import FinancingParams
    financing = FinancingParams(
        gearing_ratio=fin_dict.get("gearing_ratio", 0.70),
        senior_tenor_years=fin_dict.get("senior_tenor_years", 12),
        base_rate=fin_dict.get("base_rate", 0.03),
        margin_bps=fin_dict.get("margin_bps", 200),
        target_dscr=fin_dict.get("target_dscr", 1.15),
        lockup_dscr=fin_dict.get("lockup_dscr", 1.10),
        dsra_months=fin_dict.get("dsra_months", 6),
    )
    
    # Use default for capex, opex, tax from create_default_oborovo
    default = ProjectInputs.create_default_oborovo()
    return ProjectInputs(
        info=info,
        technical=technical,
        capex=default.capex,
        opex=default.opex,
        revenue=revenue,
        financing=financing,
        tax=default.tax,
    )


def _apply_inputs_to_session(inputs: ProjectInputs) -> None:
    """Apply deserialized inputs to session state for UI display."""
    st.session_state.project_name = inputs.info.name
    st.session_state.project_company = inputs.info.company
    st.session_state.capacity_dc = inputs.technical.capacity_mw
    st.session_state.yield_p50 = inputs.technical.operating_hours_p50
    st.session_state.yield_p90 = inputs.technical.operating_hours_p90_10y
    st.session_state.ppa_base_tariff = inputs.revenue.ppa_base_tariff
    st.session_state.tariff_escalation = inputs.revenue.ppa_index
    st.session_state.gearing_ratio = inputs.financing.gearing_ratio
    st.session_state.debt_tenor = inputs.financing.senior_tenor_years
    st.session_state.base_rate = inputs.financing.base_rate
    st.session_state.target_dscr = inputs.financing.target_dscr
    st.session_state.ppa_term = inputs.revenue.ppa_term_years
    
    # Rebuild model
    st.session_state.inputs = inputs
    from main import _build_engine_from_inputs
    st.session_state.engine = _build_engine_from_inputs(inputs)


def _serialize_scenarios(scenarios: Dict[str, dict]) -> str:
    """Serialize scenarios dict to JSON string."""
    import json
    return json.dumps(scenarios, indent=2)