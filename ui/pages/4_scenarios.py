"""Scenario Comparison Page — OpusCore v2 Phase 2.

Streamlit multipage app (filename starting with digit for auto-discovery).
Side-by-side comparison of two scenarios from the same project.

Run as part of: streamlit run src/app.py
Or standalone: streamlit run ui/pages/4_scenarios.py
"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from persistence.database import get_engine
from persistence.repository import ProjectRepository, ScenarioRepository
from sqlalchemy.orm import sessionmaker

st.set_page_config(
    page_title="Scenario Comparison — OpusCore v2",
    page_icon="📊",
    layout="wide"
)


def _format_keur(val):
    """Format kEUR value."""
    if val is None:
        return "N/A"
    return f"{val:,.0f} kEUR"


def _format_pct(val):
    """Format percentage."""
    if val is None:
        return "N/A"
    return f"{val * 100:.2f}%"


def _format_multiple(val):
    """Format DSCR multiple."""
    if val is None:
        return "N/A"
    return f"{val:.3f}x"


def _safe_get(d, *keys, default=None):
    """Safely get nested dict value."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


def _run_waterfall_for_inputs(inputs_dict: dict):
    """Run waterfall with given inputs dict and return key metrics."""
    try:
        from utils.cache import cached_run_waterfall_v3
        from domain.period_engine import PeriodEngine, PeriodFrequency as PF
        from utils.rate_curve import build_rate_schedule
        from src.app_builder import build_inputs_from_ui
        from domain.models import (
            TechnologyConfig, SolarTechnicalParams,
            RevenueConfig, PPAParams,
            DebtConfig, SeniorDebtParams,
            TaxParams,
        )
        from domain.inputs import ProjectInputs

        # Reconstruct ProjectInputs from nested dict
        # Use minimal rebuild approach based on what's stored
        info = inputs_dict.get("info", {})
        tech = inputs_dict.get("technical", {})
        revenue = inputs_dict.get("revenue", {})
        financing = inputs_dict.get("financing", {})
        tax = inputs_dict.get("tax", {})

        # Build a minimal tech config for waterfall
        cap_mw = tech.get("capacity_mw", 75.26)
        hours = tech.get("operating_hours_p50", 1494)

        solar_params = SolarTechnicalParams(
            capacity_dc_mwp=cap_mw * 1.1,
            capacity_ac_mw=cap_mw,
            operating_hours_p50=hours,
            operating_hours_p90_10y=tech.get("operating_hours_p90_10y", 1410),
            operating_hours_p99_1y=tech.get("operating_hours_p99_1y", 1200),
            pv_degradation=tech.get("pv_degradation", 0.004),
            bifaciality_factor=0.0,
            tracker_type="fixed_tilt",
            tracker_yield_gain=0.0,
            soiling_loss_pct=0.02,
            shading_loss_pct=0.01,
            mismatch_loss_pct=0.015,
            dc_wiring_loss_pct=0.02,
            ac_wiring_loss_pct=0.01,
            transformer_loss_pct=0.005,
            inverter_efficiency=0.98,
            performance_ratio_p50=0.82,
            grid_curtailment_pct=0.0,
            self_consumption_pct=0.0,
        )
        tech_config = TechnologyConfig(technology_type="solar", solar=solar_params)

        # Build revenue config
        ppa_tariff = revenue.get("ppa_base_tariff", 65.0)
        ppa = PPAParams(
            ppa_enabled=True,
            ppa_base_price_eur_mwh=ppa_tariff,
            ppa_price_index=revenue.get("ppa_index", 0.02),
            ppa_term_years=revenue.get("ppa_term_years", 10),
            ppa_volume_share=1.0,
            balancing_cost_pct=0.025,
        )
        rev_config = RevenueConfig(ppa=ppa)

        # Build debt config
        fin = financing
        senior = SeniorDebtParams(
            gearing_ratio=fin.get("gearing_ratio", 0.75),
            tenor_years=fin.get("senior_tenor_years", 14),
            base_rate=fin.get("base_rate", 0.03),
            margin_bps=fin.get("margin_bps", 265),
            target_dscr=fin.get("target_dscr", 1.15),
            min_dscr_lockup=fin.get("lockup_dscr", 1.10),
            dsra_months=fin.get("dsra_months", 6),
        )
        debt_config = DebtConfig(senior=senior)

        # Build tax config
        tax_p = TaxParams(
            corporate_tax_rate=tax.get("corporate_rate", 0.10),
            loss_carryforward_years=tax.get("loss_carryforward_years", 5),
            atad_applies=False,
            atad_ebitda_limit=0.0,
            thin_cap_enabled=tax.get("thin_cap_enabled", False),
            thin_cap_ratio=tax.get("thin_cap_de_ratio", 4.0),
            wht_dividends=tax.get("wht_sponsor_dividends", 0.05),
            vat_rate=0.25,
        )

        proj_name = info.get("name", "Project")
        proj_company = info.get("company", "Company")
        country_iso = info.get("country_iso", "HR")

        rebuilt = build_inputs_from_ui(
            tech_config, rev_config, debt_config, tax_p,
            project_name=proj_name,
            company=proj_company,
            country_iso=country_iso,
        )

        freq = PF.SEMESTRIAL if rebuilt.info.period_frequency.name == "SEMESTRIAL" else PF.ANNUAL
        engine_mod = PeriodEngine(
            financial_close=rebuilt.info.financial_close,
            construction_months=rebuilt.info.construction_months,
            horizon_years=rebuilt.info.horizon_years,
            ppa_years=rebuilt.revenue.ppa_term_years,
            frequency=freq,
        )

        rate_sched = build_rate_schedule(
            base_rate_type="FLAT",
            tenor_periods=14 * 2, periods_per_year=2,
            base_rate_override=0.03 / 2,
            floating_share=0.2, fixed_share=0.8,
            hedge_coverage=0.8, margin_bps=265,
            base_rate_floor=0.0,
        )

        result = cached_run_waterfall_v3(
            inputs=rebuilt, engine=engine_mod,
            rate_per_period=0.03 / 2,
            tenor_periods=14 * 2,
            target_dscr=1.15,
            lockup_dscr=1.10,
            tax_rate=0.10,
            dsra_months=6,
            shl_amount=0.0,
            shl_rate=0.06,
            discount_rate_project=0.0641,
            discount_rate_equity=0.0965,
            rate_schedule=rate_sched,
        )

        return {
            "project_irr": result.project_irr,
            "equity_irr": result.equity_irr,
            "npv_keur": result.project_npv,
            "avg_dscr": result.avg_dscr,
            "min_dscr": result.min_dscr,
            "total_capex_keur": rebuilt.capex.total_capex,
            "total_distribution_keur": result.total_distribution_keur,
            "total_senior_ds_keur": result.total_senior_ds_keur,
        }
    except Exception as e:
        return {
            "error": str(e),
            "project_irr": None,
            "equity_irr": None,
            "npv_keur": None,
            "avg_dscr": None,
            "min_dscr": None,
            "total_capex_keur": None,
            "total_distribution_keur": None,
        }


def main():
    st.title("📊 Scenario Comparison")
    st.markdown("Compare two scenarios side-by-side and see what inputs changed.")

    # Get DB connection
    engine = get_engine()
    Sm = sessionmaker(bind=engine, expire_on_commit=False)
    db = ProjectRepository(Sm())
    sc_repo = ScenarioRepository(Sm())

    # Get active project
    active_proj_id = st.session_state.get('active_project_id') if hasattr(st, 'session_state') and st.session_state.get('active_project_id') else None

    # Project selector
    projects = db.list_projects()

    if not projects:
        st.info("No projects found. Create one from the main app first.")
        st.stop()
        return

    project_options = {p.id: p.name for p in projects}
    project_options_list = list(project_options.keys())

    if active_proj_id and active_proj_id in project_options_list:
        default_idx = project_options_list.index(active_proj_id)
    else:
        default_idx = 0
        active_proj_id = project_options_list[0] if project_options_list else None

    if active_proj_id is None:
        st.info("No active project.")
        st.stop()
        return

    selected_proj_id = st.selectbox(
        "Select Project",
        options=project_options_list,
        index=default_idx,
        format_func=lambda pid: project_options[pid],
        key="sc_proj_selector",
    )

    # Load scenarios for selected project
    scenarios = sc_repo.list_scenarios(selected_proj_id)

    if len(scenarios) < 2:
        st.info(f"Project has only {len(scenarios)} scenario(s). Need at least 2 to compare.")
        for sc in scenarios:
            st.write(f"- **{sc.name}**" + (" (Base Case)" if sc.is_base_case else ""))
        st.stop()
        return

    # Scenario A selector
    sc_options = [(sc.id, sc.name) for sc in scenarios]
    col_a, col_b = st.columns(2)
    with col_a:
        sc_a_id = st.selectbox(
            "Scenario A",
            options=[s[0] for s in sc_options],
            index=0,
            format_func=lambda sid: next((s[1] for s in sc_options if s[0] == sid), sid),
            key="sc_a_selector",
        )
    with col_b:
        sc_b_id = st.selectbox(
            "Scenario B",
            options=[s[0] for s in sc_options],
            index=min(1, len(sc_options) - 1),
            format_func=lambda sid: next((s[1] for s in sc_options if s[0] == sid), sid),
            key="sc_b_selector",
        )

    # Load inputs for both scenarios
    inputs_a = db.load_inputs(sc_a_id)
    inputs_b = db.load_inputs(sc_b_id)

    if not inputs_a or not inputs_b:
        st.error("Could not load inputs for one or both scenarios. Make sure inputs were saved.")
        return

    # Run waterfall for both scenarios (or load from cache)
    st.markdown("---")
    st.markdown("### 🔢 Running calculations...")

    col_progress_a, col_progress_b = st.columns(2)
    with col_progress_a:
        with st.spinner(f"Running {sc_options[[s[0] for s in sc_options].index(sc_a_id)][1]}..."):
            metrics_a = _run_waterfall_for_inputs(inputs_a)
    with col_progress_b:
        with st.spinner(f"Running {sc_options[[s[0] for s in sc_options].index(sc_b_id)][1]}..."):
            metrics_b = _run_waterfall_for_inputs(inputs_b)

    # ============================================================
    # KPI Comparison Table
    # ============================================================
    st.markdown("### 📊 KPI Comparison")

    kpi_data = []
    kpi_labels = [
        ("project_irr", "Project IRR", "pct"),
        ("equity_irr", "Equity IRR", "pct"),
        ("npv_keur", "NPV (kEUR)", "keur"),
        ("avg_dscr", "Avg DSCR", "mult"),
        ("min_dscr", "Min DSCR", "mult"),
        ("total_capex_keur", "Total CAPEX (kEUR)", "keur"),
        ("total_distribution_keur", "Total Distribution (kEUR)", "keur"),
        ("total_senior_ds_keur", "Total Senior Debt Service (kEUR)", "keur"),
    ]

    for key, label, fmt in kpi_labels:
        val_a = metrics_a.get(key)
        val_b = metrics_b.get(key)

        if fmt == "pct":
            disp_a = _format_pct(val_a)
            disp_b = _format_pct(val_b)
        elif fmt == "mult":
            disp_a = _format_multiple(val_a)
            disp_b = _format_multiple(val_b)
        elif fmt == "keur":
            disp_a = _format_keur(val_a)
            disp_b = _format_keur(val_b)
        else:
            disp_a = str(val_a) if val_a is not None else "N/A"
            disp_b = str(val_b) if val_b is not None else "N/A"

        # Compute delta
        if val_a is not None and val_b is not None and val_a != 0:
            delta = val_b - val_a
            if fmt == "pct":
                delta_disp = f"{delta * 100:+.2f} pp"
            elif fmt == "mult":
                delta_disp = f"{delta:+.3f}x"
            elif fmt == "keur":
                delta_disp = f"{delta:+,.0f} kEUR"
            else:
                delta_disp = f"{delta:+,.2f}"
        else:
            delta_disp = "—"

        # Color for delta (positive = green for IRR/NPV, red for debt/costs)
        positive_is_good = key in ("project_irr", "equity_irr", "npv_keur", "avg_dscr", "min_dscr")
        if val_a is not None and val_b is not None and val_a != 0:
            delta_val = val_b - val_a
            if delta_val > 0:
                delta_color = "🟢" if positive_is_good else "🔴"
            elif delta_val < 0:
                delta_color = "🔴" if positive_is_good else "🟢"
            else:
                delta_color = "⚪"
        else:
            delta_color = "⚪"

        kpi_data.append({
            "KPI": label,
            "Scenario A": disp_a,
            "Scenario B": disp_b,
            f"Δ (B − A)": f"{delta_color} {delta_disp}",
        })

    df_kpi = st.dataframe(
        pd.DataFrame(kpi_data),
        use_container_width=True,
        hide_index=True,
    )

    # ============================================================
    # Changed Inputs (Diff)
    # ============================================================
    st.markdown("---")
    st.markdown("### 🔍 Changed Inputs")

    diff = sc_repo.get_diff(sc_a_id, sc_b_id)

    if not diff:
        st.info("No differences found between scenarios.")
    else:
        # Filter out deep nested technical params that are noise
        meaningful_diffs = {}
        skip_keys = {"schema_version", "inputs_hash", "created_at", "updated_at",
                     "period_frequency", "financial_close", "cod_date"}

        for path, (val_a, val_b) in diff.items():
            # Skip noise paths
            if any(s in path for s in skip_keys):
                continue
            # Skip very deep technical sub-keys
            parts = path.split(".")
            if len(parts) > 3 and parts[0] in ("technical", "capex"):
                continue
            meaningful_diffs[path] = (val_a, val_b)

        if meaningful_diffs:
            diff_rows = []
            for path, (val_a, val_b) in meaningful_diffs.items():
                diff_rows.append({
                    "Field": path,
                    "Scenario A": str(val_a) if val_a is not None else "—",
                    "Scenario B": str(val_b) if val_b is not None else "—",
                })

            df_diff = st.dataframe(
                pd.DataFrame(diff_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No meaningful input differences (only structural/metadata changed).")

    # ============================================================
    # Export
    # ============================================================
    st.markdown("---")
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        if st.button("📊 Export Comparison (CSV)"):
            import pandas as pd
            csv_data = pd.DataFrame(kpi_data).to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download KPI Comparison",
                data=csv_data,
                file_name="scenario_comparison.csv",
                mime="text/csv",
            )
    with col_exp2:
        if diff:
            import json
            diff_json = json.dumps({k: {"a": str(v[0]), "b": str(v[1])} for k, v in diff.items()}, indent=2)
            st.download_button(
                label="📋 Export Diff (JSON)",
                data=diff_json.encode('utf-8'),
                file_name="scenario_diff.json",
                mime="application/json",
            )


if __name__ == "__main__":
    main()