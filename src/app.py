"""Complete financial model app with generic technology support.

Supports: Solar PV, Wind, BESS, Solar+BESS, Wind+BESS, Agrivoltaics
Technology selection UI + relevant inputs per technology.

Run with: streamlit run src/app.py
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from typing import Optional, Tuple
import pandas as pd

from domain.models import (
    TechnologyConfig, SolarTechnicalParams, WindTechnicalParams,
    BESSTechnicalParams, HybridConfig,
    RevenueConfig, PPAParams, MerchantParams, FeedInTariffParams, CfDParams,
    CapacityMarketParams, BESSRevenueParams,
    DebtConfig, SeniorDebtParams, MezzanineParams, SHLParams, EBLParams,
    TaxParams, RegulatoryParams,
    CapexBreakdown, OpexParams,
    SolarCapexBreakdown, WindCapexBreakdown, BESSCapexBreakdown,
    SolarOpexParams, WindOpexParams, BESSOpexParams,
)
from utils.cache import cached_run_waterfall_v3  # v3: proper hash_funcs
from utils.rate_curve import build_rate_schedule, apply_rate_shock
from domain.period_engine import PeriodEngine, PeriodFrequency as PF
from domain.inputs import ProjectInputs, PeriodFrequency, CapexItem
from src.ui.charts import (
    create_waterfall_summary_chart, 
    create_dscr_chart,
    waterfall_metrics_html,
)
from utils.ui_constants import CHART_CONFIG
from utils.financial import format_keur, format_pct, format_multiple
from domain.analytics.scenarios import (
    YieldScenario, get_scenario_hours, run_scenario, compare_scenarios,
    ScenarioResult, _inputs_for_scenario,
)
from domain.reporting.financial_statements import (
    build_income_statement, build_balance_sheet,
    build_cash_flow_statement, build_debt_schedule_simple,
)
from domain.financing.depreciation import (
    financial_depreciation_schedule, tax_depreciation_schedule,
    DepreciationParams,
)
from src.app_builder import build_inputs_from_ui
from domain.inputs import ProjectInputs


# =============================================================================
# TECHNOLOGY CONFIGURATION UI
# =============================================================================


def _apply_sensitivity_shocks(inputs: ProjectInputs, shocks: dict) -> ProjectInputs:
    """Apply tariff/generation/CAPEX shocks to inputs.
    
    Args:
        inputs: Base ProjectInputs
        shocks: dict with keys: tariff, generation, capex (fractions, e.g. 0.2 = +20%)
    
    Returns:
        Modified ProjectInputs with shocked values
    """
    if not shocks:
        return inputs
    
    from dataclasses import replace
    
    # Tariff shock: scale ppa_base_tariff
    shock_tariff = shocks.get('tariff', 0)
    if shock_tariff != 0:
        inputs = replace(inputs, revenue=replace(
            inputs.revenue,
            ppa_base_tariff=inputs.revenue.ppa_base_tariff * (1 + shock_tariff)
        ))
    
    # Generation shock: scale operating_hours_p50 (base for all yield calculations)
    shock_gen = shocks.get('generation', 0)
    if shock_gen != 0:
        tech = inputs.technical
        inputs = replace(inputs, technical=replace(
            tech,
            operating_hours_p50=tech.operating_hours_p50 * (1 + shock_gen),
            operating_hours_p90_1y=int(tech.operating_hours_p90_1y * (1 + shock_gen)) if tech.operating_hours_p90_1y else 0,
            operating_hours_p90_10y=int(tech.operating_hours_p90_10y * (1 + shock_gen)),
            operating_hours_p99_1y=int(tech.operating_hours_p99_1y * (1 + shock_gen)) if tech.operating_hours_p99_1y else 0,
        ))
    
    # CAPEX shock: scale total_capex
    shock_capex = shocks.get('capex', 0)
    if shock_capex != 0:
        capex = inputs.capex
        # CAPEX shock: scale all individual capex items by (1 + shock_capex)
        capex_items = [
            capex.epc_contract, capex.production_units, capex.epc_other,
            capex.grid_connection, capex.ops_prep, capex.insurances,
            capex.lease_tax, capex.construction_mgmt_a, capex.commissioning,
            capex.audit_legal, capex.construction_mgmt_b, capex.contingencies,
            capex.taxes, capex.project_acquisition, capex.project_rights,
        ]
        scale = 1 + shock_capex
        scaled_items = {}
        for attr in ['epc_contract', 'production_units', 'epc_other', 'grid_connection',
                     'ops_prep', 'insurances', 'lease_tax', 'construction_mgmt_a',
                     'commissioning', 'audit_legal', 'construction_mgmt_b',
                     'contingencies', 'taxes', 'project_acquisition', 'project_rights']:
            item = getattr(capex, attr)
            scaled_items[attr] = CapexItem(
                name=item.name,
                amount_keur=item.amount_keur * scale,
                y0_share=item.y0_share,
                spending_profile=item.spending_profile,
            )
        inputs = replace(inputs, capex=replace(capex, **scaled_items))
    
    return inputs


def render_technology_selector() -> Tuple[str, TechnologyConfig]:
    """Render technology selection and return (tech_type, config)."""
    
    st.subheader("⚙️ Technology Selection")
    
    tech_options = {
        "Solar PV": "solar",
        "Wind (onshore)": "wind", 
        "BESS (Standalone)": "bess",
        "Solar + BESS": "solar_bess",
        "Wind + BESS": "wind_bess",
        "Agrivoltaics": "agrivoltaic",
    }
    
    selected_label = st.selectbox(
        "Project Type",
        options=list(tech_options.keys()),
        index=0,
        help="Select renewable energy type"
    )
    
    tech_type = tech_options[selected_label]
    
    # Create default config based on selection
    if tech_type == "solar":
        config = render_solar_inputs()
    elif tech_type == "wind":
        config = render_wind_inputs()
    elif tech_type == "bess":
        config = render_bess_inputs()
    elif tech_type == "solar_bess":
        config = render_solar_bess_inputs()
    elif tech_type == "wind_bess":
        config = render_wind_bess_inputs()
    elif tech_type == "agrivoltaic":
        config = render_agrivoltaic_inputs()
    else:
        config = TechnologyConfig.create_solar_defaults()
    
    return tech_type, config


def render_solar_inputs() -> TechnologyConfig:
    """Render Solar PV specific inputs."""
    
    st.markdown("#### ☀️ Solar PV Parameters")
    
    col1, col2 = st.columns(2)
    
    with col1:
        capacity_ac = st.number_input(
            "AC Capacity (MW)", 
            min_value=0.1, max_value=2000.0, 
            value=75.0, step=1.0,
            help="Installed AC power"
        )
        dc_ac_ratio = st.slider(
            "DC/AC Ratio", 
            1.0, 1.5, 1.2, step=0.01,
            help="DC to AC ratio"
        )
        capacity_dc = capacity_ac * dc_ac_ratio
        
        hours_p50 = st.number_input(
            "P50 Hours (annual)", 
            min_value=500, max_value=4000, 
            value=1500, step=10,
            help="Full load equivalent hours - P50"
        )
        hours_p90 = st.number_input(
            "P90-10y Hours", 
            min_value=500, max_value=4000, 
            value=1400, step=10,
            help="P90-10y scenario"
        )
    
    with col2:
        degradation = st.slider(
            "Annual Degradation (%)", 
            0.0, 2.0, 0.4, step=0.1,
            help="Annual efficiency decline"
        ) / 100
        
        tracker = st.selectbox(
            "Tracker Type",
            ["fixed_tilt", "single_axis", "dual_axis"],
            index=0,
            help="Mounting type"
        )
        
        bifacial = st.slider(
            "Bifacial Gain (%)",
            0.0, 15.0, 0.0, step=0.5,
            help="Additional yield from bifacial modules"
        ) / 100
        
        performance_ratio = st.slider(
            "Performance Ratio (%)",
            70.0, 90.0, 82.0, step=0.5,
            help="System efficiency ratio"
        ) / 100
    
    # System Losses
    with st.expander("⚡ Additional Losses", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            soiling = st.slider("Soiling (%)", 0.0, 10.0, 2.0, step=0.1) / 100
            shading = st.slider("Shading (%)", 0.0, 5.0, 1.0, step=0.1) / 100
            mismatch = st.slider("Mismatch (%)", 0.0, 5.0, 1.5, step=0.1) / 100
        with col_b:
            dc_wiring = st.slider("DC Wiring (%)", 0.0, 5.0, 2.0, step=0.1) / 100
            ac_wiring = st.slider("AC Wiring (%)", 0.0, 3.0, 1.0, step=0.1) / 100
            inverter_eff = st.slider("Inverter Eff (%)", 90.0, 99.0, 98.0, step=0.1) / 100
    
    solar = SolarTechnicalParams(
        capacity_dc_mwp=capacity_dc,
        capacity_ac_mw=capacity_ac,
        operating_hours_p50=hours_p50,
        operating_hours_p90_1y=hours_p90,
        operating_hours_p90_10y=hours_p90,
        operating_hours_p99_1y=int(hours_p90 * 0.85),
        pv_degradation_annual=degradation,
        bifaciality_factor=bifacial,
        tracker_type=tracker,
        tracker_yield_gain=0.0,
        soiling_loss_pct=soiling,
        shading_loss_pct=shading,
        mismatch_loss_pct=mismatch,
        dc_wiring_loss_pct=dc_wiring,
        ac_wiring_loss_pct=ac_wiring,
        transformer_loss_pct=0.005,
        inverter_efficiency=inverter_eff,
        performance_ratio_p50=performance_ratio,
        grid_curtailment_pct=0.0,
        self_consumption_pct=0.0,
    )
    
    return TechnologyConfig(technology_type="solar", solar=solar)


def render_wind_inputs() -> TechnologyConfig:
    """Render Wind specific inputs."""
    
    st.markdown("#### 🌬️ Wind Parameters")
    
    col1, col2 = st.columns(2)
    
    with col1:
        capacity = st.number_input(
            "Installed Capacity (MW)", 
            min_value=1.0, max_value=2000.0, 
            value=50.0, step=1.0
        )
        num_turbines = st.number_input(
            "Number of Turbines", 
            min_value=1, max_value=200, 
            value=12, step=1
        )
        turbine_rating = capacity / num_turbines if num_turbines > 0 else 4.0
        
        hub_height = st.number_input(
            "Hub Height (m)", 
            min_value=50, max_value=200, 
            value=100, step=5
        )
        
        hours_p50 = st.number_input(
            "P50 Hours", 
            min_value=1000, max_value=4000, 
            value=2200, step=50
        )
    
    with col2:
        wake_loss = st.slider(
            "Wake Losses (%)", 
            0.0, 10.0, 5.0, step=0.1
        ) / 100
        
        avail_mech = st.slider(
            "Mechanical Availability (%)",
            90.0, 100.0, 97.0, step=0.5
        ) / 100
        
        avail_grid = st.slider(
            "Grid Availability (%)",
            95.0, 100.0, 99.0, step=0.5
        ) / 100
        
        curtailment = st.slider(
            "Total Curtailment (%)",
            0.0, 20.0, 0.0, step=0.5
        ) / 100
    
    wind = WindTechnicalParams(
        capacity_mw=capacity,
        num_turbines=num_turbines,
        turbine_rating_mw=turbine_rating,
        hub_height_m=hub_height,
        rotor_diameter_m=130.0,
        operating_hours_p50=hours_p50,
        operating_hours_p90_1y=int(hours_p50 * 0.92),
        operating_hours_p90_10y=int(hours_p50 * 0.92),
        operating_hours_p99_1y=int(hours_p50 * 0.75),
        wake_loss_pct=wake_loss,
        availability_mechanical=avail_mech,
        availability_grid=avail_grid,
        hysteresis_loss_pct=0.01,
        icing_loss_pct=0.0,
        curtailment_noise_pct=0.0,
        curtailment_bat_pct=0.0,
        curtailment_grid_pct=0.0,
        wind_degradation_annual=0.003,
    )
    
    return TechnologyConfig(technology_type="wind", wind=wind)


def render_bess_inputs() -> TechnologyConfig:
    """Render BESS specific inputs."""
    
    st.markdown("#### 🔋 BESS Parameters")
    
    col1, col2 = st.columns(2)
    
    with col1:
        power_mw = st.number_input(
            "Power (MW)", 
            min_value=1.0, max_value=1000.0, 
            value=20.0, step=1.0
        )
        duration = st.selectbox(
            "Duration (hours)",
            [1, 2, 4, 6, 8],
            index=1,
            help="How many hours can discharge"
        )
        energy_mwh = power_mw * duration
        
        chemistry = st.selectbox(
            "Battery Technology",
            ["LFP", "NMC", "NaS", "flow"],
            index=0,
            help="LFP is most common for storage"
        )
    
    with col2:
        rte = st.slider(
            "Roundtrip Efficiency (%)",
            80.0, 95.0, 88.0, step=0.5
        ) / 100
        
        calendar_deg = st.slider(
            "Calendar Degradation (%/year)",
            0.0, 5.0, 1.5, step=0.1
        ) / 100
        
        cycle_deg = st.number_input(
            "Degradation per Cycle (%)",
            0.0, 0.5, 0.01, step=0.001
        ) / 100
        
        replacement_year = st.number_input(
            "Replacement Year",
            5, 20, 10, step=1
        )
    
    bess = BESSTechnicalParams(
        energy_capacity_mwh=energy_mwh,
        power_capacity_mw=power_mw,
        duration_hours=duration,
        battery_chemistry=chemistry,
        roundtrip_efficiency=rte,
        auxiliary_consumption_pct=0.01,
        calendar_degradation_annual=calendar_deg,
        cycle_degradation_per_cycle=cycle_deg,
        eol_capacity_threshold=0.80,
        soc_min_pct=0.10,
        soc_max_pct=0.95,
        annual_cycles_target=365,
        replacement_year=replacement_year,
        replacement_cost_pct_of_capex=0.70,
    )
    
    return TechnologyConfig(technology_type="bess", bess=bess)


def render_solar_bess_inputs() -> TechnologyConfig:
    """Render Solar + BESS hybrid inputs."""
    
    st.markdown("#### ☀️🔋 Solar + BESS Hybrid")
    
    solar_config = render_solar_inputs()
    
    st.markdown("---")
    st.markdown("##### BESS Komponenta")
    
    col1, col2 = st.columns(2)
    with col1:
        bess_power = st.number_input(
            "BESS Power (MW)", 
            min_value=1.0, max_value=500.0, 
            value=15.0, step=1.0
        )
        bess_duration = st.selectbox(
            "BESS Duration (hours)",
            [1, 2, 4, 6, 8],
            index=1
        )
    
    with col2:
        bess_strategy = st.selectbox(
            "BESS Strategy",
            ["peak_shaving", "arbitrage", "firm_power", "mixed"],
            index=0
        )
        grid_limit = st.number_input(
            "Grid Limit (MW)",
            min_value=0.0, max_value=1000.0,
            value=solar_config.solar.capacity_ac_mw if solar_config.solar else 75.0,
            step=1.0
        )
    
    bess = BESSTechnicalParams(
        energy_capacity_mwh=bess_power * bess_duration,
        power_capacity_mw=bess_power,
        duration_hours=bess_duration,
        battery_chemistry="LFP",
        roundtrip_efficiency=0.88,
    )
    
    hybrid = HybridConfig(
        technology_primary="solar",
        bess_enabled=True,
        shared_grid_connection=True,
        grid_connection_mw=grid_limit,
        bess_strategy=bess_strategy,
    )
    
    return TechnologyConfig(
        technology_type="solar_bess",
        solar=solar_config.solar,
        bess=bess,
        hybrid=hybrid,
    )


def render_wind_bess_inputs() -> TechnologyConfig:
    """Render Wind + BESS hybrid inputs."""
    
    st.markdown("#### 🌬️🔋 Wind + BESS Hybrid")
    
    wind_config = render_wind_inputs()
    
    st.markdown("---")
    st.markdown("##### BESS Komponenta")
    
    col1, col2 = st.columns(2)
    with col1:
        bess_power = st.number_input("BESS Power (MW)", min_value=1.0, max_value=500.0, value=15.0, step=1.0)
        bess_duration = st.selectbox("BESS Duration (hours)", [1, 2, 4, 6, 8], index=1)
    
    with col2:
        bess_strategy = st.selectbox("BESS Strategy", ["peak_shaving", "arbitrage", "firm_power", "mixed"], index=0)
        grid_limit = st.number_input("Grid Limit (MW)", min_value=0.0, max_value=1000.0, value=wind_config.wind.capacity_mw if wind_config.wind else 50.0, step=1.0)
    
    bess = BESSTechnicalParams(
        energy_capacity_mwh=bess_power * bess_duration,
        power_capacity_mw=bess_power,
        duration_hours=bess_duration,
        battery_chemistry="LFP",
        roundtrip_efficiency=0.88,
    )
    
    hybrid = HybridConfig(
        technology_primary="wind",
        bess_enabled=True,
        shared_grid_connection=True,
        grid_connection_mw=grid_limit,
        bess_strategy=bess_strategy,
    )
    
    return TechnologyConfig(
        technology_type="wind_bess",
        wind=wind_config.wind,
        bess=bess,
        hybrid=hybrid,
    )


def render_agrivoltaic_inputs() -> TechnologyConfig:
    """Render Agrivoltaics inputs."""
    
    solar_config = render_solar_inputs()
    
    st.markdown("#### 🌾 Agrivoltaics Additional Parameters")
    
    agrivoltaic_reduction = st.slider(
        "Yield Reduction (%)",
        0.0, 30.0, 10.0, step=0.5,
        help="Yield reduction due to panels above crops"
    ) / 100
    
    land_premium = st.number_input(
        "Land Rental Premium (EUR/ha/year)",
        0, 2000, 500, step=50
    )
    
    # Update solar params using replace (frozen dataclass)
    from dataclasses import replace
    solar = solar_config.solar
    solar = replace(solar,
        agrivoltaic_enabled=True,
        agrivoltaic_yield_reduction=agrivoltaic_reduction,
        agrivoltaic_land_rental_premium=land_premium,
    )
    
    return TechnologyConfig(technology_type="agrivoltaic", solar=solar)


# =============================================================================
# SPRINT 2: SIDEBAR → MODEL BRIDGE
# =============================================================================

def _build_engine_from_inputs(inputs: ProjectInputs) -> PeriodEngine:
    """"Build PeriodEngine from ProjectInputs."""
    freq = PF.SEMESTRIAL if inputs.info.period_frequency == PeriodFrequency.SEMESTRIAL else PF.ANNUAL
    return PeriodEngine(
        financial_close=inputs.info.financial_close,
        construction_months=inputs.info.construction_months,
        horizon_years=inputs.info.horizon_years,
        ppa_years=inputs.revenue.ppa_term_years,
        frequency=freq,
    )


def _get_inputs_from_session() -> ProjectInputs:
    """Get inputs from session_state or fallback to Oborovo default."""
    if st.session_state.get("inputs") is not None:
        return st.session_state.inputs
    return ProjectInputs.create_default_oborovo()



# =============================================================================
# REVENUE CONFIGURATION UI
# =============================================================================
def render_revenue_config() -> RevenueConfig:
    """Render revenue configuration UI."""
    
    st.subheader("💰 Revenue Model")
    
    # Revenue type selection
    revenue_type = st.selectbox(
        "Revenue Model Type",
        ["PPA", "Merchant", "PPA + Merchant mix", "FiT", "CfD"],
        index=0,
        help="Select revenue model"
    )
    
    if revenue_type == "PPA":
        return render_ppa_revenue()
    elif revenue_type == "Merchant":
        return render_merchant_revenue()
    elif revenue_type == "PPA + Merchant mix":
        return render_ppa_merchant_revenue()
    elif revenue_type == "FiT":
        return render_fit_revenue()
    elif revenue_type == "CfD":
        return render_cfd_revenue()
    
    return RevenueConfig.create_ppa_defaults()


def render_ppa_revenue() -> RevenueConfig:
    """PPA revenue inputs."""
    
    col1, col2 = st.columns(2)
    
    with col1:
        tariff = st.number_input(
            "PPA Price (EUR/MWh)",
            min_value=0.0, max_value=500.0,
            value=57.0, step=1.0
        )
        ppa_term = st.number_input(
            "PPA Term (years)",
            min_value=0, max_value=30,
            value=12, step=1
        )
        ppa_index = st.slider(
            "PPA Indexation (%)",
            0.0, 10.0, 2.0, step=0.1
        ) / 100
    
    with col2:
        volume_share = st.slider(
            "PPA Volume Share (%)",
            0.0, 100.0, 100.0, step=5.0
        ) / 100
        balancing = st.slider(
            "Balancing Cost (%)",
            0.0, 10.0, 2.5, step=0.1
        ) / 100
    
    ppa = PPAParams(
        ppa_enabled=True,
        ppa_type="pay_as_produced",
        ppa_base_price_eur_mwh=tariff,
        ppa_price_index=ppa_index,
        ppa_term_years=ppa_term,
        ppa_volume_share=volume_share,
        balancing_cost_pct=balancing,
    )
    
    return RevenueConfig(ppa=ppa)


def render_merchant_revenue() -> RevenueConfig:
    """Merchant revenue inputs."""
    
    col1, col2 = st.columns(2)
    
    with col1:
        base_price = st.number_input(
            "Spot Price (EUR/MWh)",
            min_value=0.0, max_value=500.0,
            value=65.0, step=1.0
        )
        escalation = st.slider(
            "Annual Escalation (%)",
            -5.0, 10.0, 2.0, step=0.1
        ) / 100
        cannibalization = st.slider(
            "Price Cannibalization (%)",
            0.0, 5.0, 0.0, step=0.1
        ) / 100
    
    with col2:
        capture_solar = st.slider(
            "Solar Capture Rate (%)",
            50.0, 100.0, 85.0, step=1.0
        ) / 100
        capture_wind = st.slider(
            "Wind Capture Rate (%)",
            50.0, 100.0, 90.0, step=1.0
        ) / 100
    
    merchant = MerchantParams(
        merchant_enabled=True,
        base_price_eur_mwh=base_price,
        price_escalation_annual=escalation,
        price_cannibalization_pct=cannibalization,
        capture_rate_solar=capture_solar,
        capture_rate_wind=capture_wind,
    )
    
    return RevenueConfig(merchant=merchant)


def render_ppa_merchant_revenue() -> RevenueConfig:
    """PPA + Merchant mix inputs."""
    
    col1, col2 = st.columns(2)
    
    with col1:
        ppa_price = st.number_input("PPA Price (EUR/MWh)", value=57.0, step=1.0)
        ppa_term = st.number_input("PPA Term (years)", value=12, step=1)
        ppa_share = st.slider("PPA Share (%)", 0.0, 100.0, 70.0, step=5.0) / 100
    
    with col2:
        merchant_price = st.number_input("Merchant Price (EUR/MWh)", value=65.0, step=1.0)
    
    ppa = PPAParams(
        ppa_enabled=True,
        ppa_base_price_eur_mwh=ppa_price,
        ppa_term_years=ppa_term,
        ppa_volume_share=ppa_share,
        balancing_cost_pct=0.025,
    )
    
    merchant = MerchantParams(
        merchant_enabled=True,
        base_price_eur_mwh=merchant_price,
    )
    
    return RevenueConfig(ppa=ppa, merchant=merchant)


def render_fit_revenue() -> RevenueConfig:
    """Feed-in Tariff inputs."""
    
    col1, col2 = st.columns(2)
    
    with col1:
        fit_price = st.number_input("FiT Price (EUR/MWh)", value=90.0, step=1.0)
        fit_term = st.number_input("FiT Term (years)", value=15, step=1)
        fit_type = st.selectbox("FiT Type", ["fixed_fit", "premium"], index=0)
    
    with col2:
        scheme = st.selectbox("Scheme", ["HROTE (HR)", "FERK (BA)", "ELEM (MK)", "EPS (RS)"], index=0)
    
    fit = FeedInTariffParams(
        fit_enabled=True,
        fit_type=fit_type,
        fit_price_eur_mwh=fit_price,
        fit_term_years=fit_term,
        fit_scheme=scheme.split()[0] if scheme else "",
    )
    
    return RevenueConfig(fit=fit)


def render_cfd_revenue() -> RevenueConfig:
    """CfD inputs."""
    
    col1, col2 = st.columns(2)
    
    with col1:
        strike = st.number_input("Strike Price (EUR/MWh)", value=75.0, step=1.0)
        cfd_term = st.number_input("CfD Term (years)", value=10, step=1)
        volume = st.number_input("Annual Volume (MWh)", value=0, step=10000, help="0 = total production")
    
    with col2:
        two_way = st.checkbox("Two-way CfD", value=True, help="Payment and receipt")
        counterparty = st.selectbox("Counterparty", ["government", "utility", "corporate"], index=0)
    
    cfd = CfDParams(
        cfd_enabled=True,
        strike_price_eur_mwh=strike,
        cfd_term_years=cfd_term,
        cfd_volume_mwh_annual=volume,
        two_way_cfd=two_way,
        cfd_counterparty=counterparty,
    )
    
    return RevenueConfig(cfd=cfd)


# =============================================================================
# DEBT CONFIGURATION UI
# =============================================================================
def render_debt_config() -> DebtConfig:
    """Render debt configuration UI."""
    
    st.subheader("🏦 Debt Structure")
    
    # Basic debt params
    col1, col2 = st.columns(2)
    
    with col1:
        gearing = st.slider(
            "Gearing (%)",
            0.0, 95.0, 75.0, step=0.5
        ) / 100
        tenor = st.number_input(
            "Senior Tenor (years)",
            min_value=1, max_value=30,
            value=14, step=1
        )
    
    with col2:
        base_rate_type = st.selectbox(
            "Rate Mode",
            ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"],
            index=0,
            help="FLAT = constant all-in rate (hedge-equivalent). EURIBOR = floating curve.",
        )
        if base_rate_type == "FLAT":
            # debt_config not yet created, use placeholder
            st.caption("FLAT — constant all-in rate (hedge-equivalent, no curve)")
        else:
            st.caption(f"{base_rate_type} — EURIBOR {base_rate_type.replace('EURIBOR_', '')} curve + margin")
        base_rate = st.number_input(
            "Base Rate (%)",
            0.0, 15.0, 5.65, step=0.1
        ) / 100
        margin = st.number_input(
            "Margin (bps)",
            0, 1000, 265, step=5
        )
    
    col3, col4 = st.columns(2)
    with col3:
        target_dscr = st.slider(
            "Target DSCR (x)",
            1.0, 2.0, 1.15, step=0.05
        )
        lockup_dscr = st.slider(
            "Lockup DSCR (x)",
            1.0, 1.5, 1.10, step=0.05
        )
    
    with col4:
        dsra_months = st.slider(
            "DSRA Months",
            0, 12, 6, step=1
        )
        amortization = st.selectbox(
            "Amortization",
            ["sculpted", "annuity", "straight_line", "bullet"],
            index=0
        )
    
    # Discount rates for NPV/IRR calculations
    st.markdown("**Discount Rates**")
    disc_col1, disc_col2, disc_col3 = st.columns(3)
    with disc_col1:
        discount_rate_project = st.number_input(
            "Project WACC (%)",
            0.0, 20.0, 6.41, step=0.1
        ) / 100
    with disc_col2:
        discount_rate_equity = st.number_input(
            "Equity Yield (%)",
            0.0, 30.0, 9.65, step=0.1
        ) / 100
    with disc_col3:
        st.caption(f"Used for NPV/IRR")
    
    senior = SeniorDebtParams(
        gearing_ratio=gearing,
        tenor_years=tenor,
        base_rate=base_rate,
        margin_bps=margin,
        target_dscr=target_dscr,
        min_dscr_lockup=lockup_dscr,
        dsra_months=dsra_months,
        amortization_type=amortization,
    )
    
    # SHL option
    use_shl = st.checkbox("Include SHL (Shareholder Loan)", value=False)
    
    shl = None
    if use_shl:
        col_shl1, col_shl2 = st.columns(2)
        with col_shl1:
            shl_amount = st.number_input(
                "SHL Amount (kEUR)",
                min_value=0.0, max_value=100000.0,
                value=5000.0, step=100.0
            )
            shl_rate = st.number_input(
                "SHL Rate (%)",
                0.0, 20.0, 8.0, step=0.5
            ) / 100
        
        with col_shl2:
            shl_repayment = st.number_input(
                "SHL Repayment (year)",
                min_value=0, max_value=30,
                value=15, step=1
            )
        
        shl = SHLParams(
            shl_enabled=True,
            shl_keur=shl_amount,
            shl_rate=shl_rate,
            shl_repayment_year=shl_repayment,
        )
    
    # Mezz option
    use_mezz = st.checkbox("Include Mezzanine", value=False)
    
    mezz = None
    if use_mezz:
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            mezz_amount = st.number_input(
                "Mezz Amount (kEUR)",
                min_value=0.0, max_value=50000.0,
                value=3000.0, step=100.0
            )
            mezz_rate = st.number_input(
                "Mezz Rate (%)",
                0.0, 20.0, 10.0, step=0.5
            ) / 100
        
        with col_m2:
            mezz_tenor = st.number_input(
                "Mezz Tenor (years)",
                min_value=1, max_value=20,
                value=8, step=1
            )
            pik = st.checkbox("PIK Interest", value=True)
        
        mezz = MezzanineParams(
            mezzanine_enabled=True,
            mezzanine_keur=mezz_amount,
            mezz_rate=mezz_rate,
            mezz_tenor_years=mezz_tenor,
            pik_interest=pik,
        )
    
    return DebtConfig(senior=senior, mezzanine=mezz, shl=shl)


# =============================================================================
# RESULTS VISUALIZATION
# =============================================================================
def create_generation_chart(tech_config: TechnologyConfig, years: int = 30) -> go.Figure:
    """Create generation chart for selected technology."""
    
    years_list = list(range(1, years + 1))
    p50 = [tech_config.annual_generation_mwh(y, "P50") for y in years_list]
    p90 = [tech_config.annual_generation_mwh(y, "P90-10y") for y in years_list]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years_list, y=p50, name="P50", line=dict(color="green")))
    fig.add_trace(go.Scatter(x=years_list, y=p90, name="P90-10y", line=dict(color="blue", dash="dash")))
    
    fig.update_layout(
        title="Annual Generation by Year",
        xaxis_title="Year",
        yaxis_title="MWh",
        height=350,
    )
    
    return fig


def create_revenue_chart(revenue_config: RevenueConfig, generation_mwh: float, tech: str = "solar") -> go.Figure:
    """Create revenue chart by scenario."""
    
    years_list = list(range(1, 31))
    ppa_rev = [revenue_config.total_annual_revenue_keur(generation_mwh, y, tech) for y in years_list]
    
    # Assume degradation of generation
    gen_p50 = [generation_mwh * (0.996 ** (y-1)) for y in years_list]  # ~0.4% deg
    rev_p50 = [revenue_config.total_annual_revenue_keur(gen_p50[y-1], y+1, tech) for y in years_list]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=years_list, y=rev_p50, name="Revenue (kEUR)", marker_color="teal"))
    
    fig.update_layout(
        title="Revenue Projection",
        xaxis_title="Year",
        yaxis_title="Revenue (kEUR)",
        height=300,
    )
    
    return fig


# =============================================================================
# MAIN APP
# =============================================================================


# =============================================================================
# TAX AND REGULATORY UI
# =============================================================================
def render_tax_config() -> TaxParams:
    """Render tax configuration UI."""
    
    st.subheader("🏛️ Tax Parameters")
    
    with st.expander("Tax Configuration", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            tax_rate = st.slider(
                "Corporate Tax Rate (%)",
                0.0, 50.0, 10.0, step=0.5
            ) / 100
            
            loss_years = st.number_input(
                "Loss Carryforward (years)",
                min_value=0, max_value=30, value=5, step=1
            )
            
            thin_cap = st.checkbox("Thin Cap Rule", value=True)
            if thin_cap:
                thin_cap_ratio = st.slider(
                    "Thin Cap Ratio (D/E)",
                    1.0, 6.0, 4.0, step=0.5
                )
            else:
                thin_cap_ratio = 4.0
        
        with col2:
            atad = st.checkbox("ATAD (EU)", value=True)
            if atad:
                atad_limit = st.slider(
                    "ATAD EBITDA Limit (%)",
                    20.0, 50.0, 30.0, step=1.0
                ) / 100
            else:
                atad_limit = 0.30
            
            wht_div = st.slider(
                "WHT Dividends (%)",
                0.0, 30.0, 5.0, step=0.5
            ) / 100
            
            vat_rate = st.slider(
                "VAT Rate (%)",
                0.0, 30.0, 25.0, step=0.5
            ) / 100
        
        # Jurisdiction-specific defaults button
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Use HR Defaults"):
                return TaxParams.create_hr_defaults()
        with col_btn2:
            if st.button("Use RS Defaults"):
                return TaxParams.create_rs_defaults()
        
        return TaxParams(
            jurisdiction="HR",
            corporate_tax_rate=tax_rate,
            loss_carryforward_years=loss_years,
            atad_applies=atad,
            atad_ebitda_limit=atad_limit,
            thin_cap_enabled=thin_cap,
            thin_cap_ratio=thin_cap_ratio,
            wht_dividends=wht_div,
            vat_rate=vat_rate,
        )


def render_regulatory_config() -> RegulatoryParams:
    """Render regulatory configuration UI."""
    
    st.subheader("📜 Regulatory Parameters")
    
    with st.expander("Regulatory Configuration", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            permits_months = st.number_input(
                "Permitting Timeline (months)",
                min_value=1, max_value=60, value=24, step=1
            )
            grid_type = st.selectbox(
                "Grid Connection Type",
                ["distribution", "direct_transmission", "submarine"],
                index=0
            )
            congestion = st.selectbox(
                "Grid Congestion Risk",
                ["low", "medium", "high"],
                index=1
            )
        
        with col2:
            curtailment = st.slider(
                "Mandatory Curtailment (%)",
                0.0, 20.0, 0.0, step=0.5
            ) / 100
            curtailment_comp = st.checkbox("Curtailment Compensation", value=True)
            
            rec_enabled = st.checkbox("GO/REC Enabled", value=True)
            if rec_enabled:
                rec_price = st.number_input(
                    "REC Price (EUR/MWh)",
                    min_value=0.0, max_value=10.0, value=0.5, step=0.1
                )
            else:
                rec_price = 0.0
        
        # Jurisdiction defaults
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("HR Regulatory"):
                return RegulatoryParams.create_hr_defaults()
        with col_btn2:
            if st.button("SI Regulatory"):
                return RegulatoryParams.create_si_defaults()
        with col_btn3:
            if st.button("RS Regulatory"):
                return RegulatoryParams.create_rs_defaults()
        
        return RegulatoryParams(
            jurisdiction="HR",
            permitting_timeline_months=permits_months,
            grid_connection_type=grid_type,
            grid_congestion_risk=congestion,
            mandatory_curtailment_pct=curtailment,
            curtailment_compensation=curtailment_comp,
            rec_enabled=rec_enabled,
            rec_price_eur_mwh=rec_price,
        )


def main():
    st.set_page_config(
        page_title="Renewable Energy Financial Model",
        page_icon="⚡",
        layout="wide"
    )
    
    st.title("⚡ Renewable Energy Financial Model")
    st.caption("Generic Project Finance Model - Solar, Wind, BESS, Hybrid")
    
    # Sidebar for project setup
    with st.sidebar:
        st.header("📋 Project Setup")
        
        # Project info
        st.subheader("📐 Basic Information")
        project_name = st.text_input("Project Name", value="Novi Projekt")
        jurisdiction = st.selectbox(
            "Jurisdiction",
            ["HR", "BA", "RS", "SI", "MK", "EU_generic"],
            index=0
        )
        horizon = st.number_input(
            "Investment Horizon (years)",
            min_value=10, max_value=50,
            value=30, step=1
        )
        
        st.divider()
        
        # Technology selection
        tech_type, tech_config = render_technology_selector()
        
        st.divider()
        
        # Revenue config
        revenue_config = render_revenue_config()
        
        st.divider()
        
        # Debt config
        debt_config = render_debt_config()
        
        st.divider()
        
        # Tax config
        tax_config = render_tax_config()
        
        st.divider()
        
        # Regulatory config
        regulatory_config = render_regulatory_config()
        
        st.divider()
        
        # === SPRINT A1: Pokreni Model Button ===
        if st.button("▶ Pokreni Model", type="primary", use_container_width=True):
            # Clear waterfall cache to force fresh calculation
            cached_run_waterfall_v3.clear()
            inputs = build_inputs_from_ui(
                tech_config=tech_config,
                revenue_config=revenue_config,
                debt_config=debt_config,
                tax_config=tax_config,
                project_name=project_name,
                company=jurisdiction,
                country_iso=jurisdiction,
            )
            st.session_state.inputs = inputs
            st.session_state.engine = _build_engine_from_inputs(inputs)
            st.rerun()
        
        # Initialize on first load
        if "inputs" not in st.session_state:
            st.session_state.inputs = None
        
        st.divider()
        
        # === SPRINT 3: Scenario Selector ===
        st.subheader("📊 Scenario Analysis")
        selected_scenarios = st.multiselect(
            "Scenarios to Compare",
            options=["P50", "P90-1y", "P90-10y", "P99-1y"],
            default=["P50", "P90-10y"],
            format_func=lambda x: {
                "P50": "P50 (Median)",
                "P90-1y": "P90-1y (Single Year)",
                "P90-10y": "P90-10y (10-Year Avg)",
                "P99-1y": "P99-1y (Extreme)",
            }.get(x, x),
            help="Select yield scenarios to compare",
        )
        if len(selected_scenarios) > 1:
            st.session_state.selected_scenarios = selected_scenarios
        elif len(selected_scenarios) == 1:
            st.session_state.selected_scenarios = selected_scenarios
        
        # === SPRINT 4: Sensitivity Analysis ===
        st.subheader("📉 Sensitivity Analysis")
        sensitivity_enabled = st.checkbox("Enable Sensitivity Analysis", value=False)
        
        if sensitivity_enabled:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                shock_tariff = st.slider("PPA Tariff Shock (±%)", 0, 30, 0, step=5) / 100
                shock_rate = st.slider("Interest Rate Shock (±bps)", 0, 200, 0, step=10)
            with col_s2:
                shock_gen = st.slider("Generation Shock (±%)", 0, 30, 0, step=5) / 100
                shock_capex = st.slider("CAPEX Shock (±%)", 0, 30, 0, step=5) / 100
            
            if any(s > 0 for s in [shock_tariff, shock_rate, shock_gen, shock_capex]):
                st.session_state.sensitivity_shocks = {
                    "tariff": shock_tariff,
                    "rate": shock_rate,
                    "generation": shock_gen,
                    "capex": shock_capex,
                }
    
    # Main content area - tabs
    tab_overview, tab_generation, tab_revenue, tab_debt, tab_pl, tab_bs, tab_cf, tab_waterfall, tab_sensitivity, tab_covenant, tab_tax, tab_regulatory, tab_validation = st.tabs([
        "📊 Overview",
        "⚡ Generation",
        "💰 Revenue",
        "🏦 Debt",
        "📋 P&L",
        "📊 Balance Sheet",
        "💵 Cash Flow",
        "📈 Waterfall",
        "📉 Sensitivity",
        "🏦 Covenant",
        "🏛️ Tax",
        "📜 Regulatory",
        "✅ Validation"
    ])
    
    with tab_overview:
        st.subheader("Project: " + project_name)
        
        # Show key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if tech_config.solar:
                st.metric("AC Kapacitet", f"{tech_config.solar.capacity_ac_mw:.1f} MW")
            elif tech_config.wind:
                st.metric("Instalirana snaga", f"{tech_config.wind.capacity_mw:.1f} MW")
            elif tech_config.bess:
                st.metric("BESS Snaga", f"{tech_config.bess.power_capacity_mw:.1f} MW")
                st.metric("BESS Energy", f"{tech_config.bess.energy_capacity_mwh:.1f} MWh")
        
        with col2:
            gen_y1 = tech_config.annual_generation_mwh(1, "P50")
            st.metric("Y1 Generation (P50)", f"{gen_y1:,.0f} MWh")
        
        with col3:
            rev_y1 = revenue_config.total_annual_revenue_keur(gen_y1, 1, tech_type.split("_")[0])
            st.metric("Y1 Revenue (P50)", f"{rev_y1:,.0f} kEUR")
        
        with col4:
            debt_keur = debt_config.total_debt_keur(100000)  # Placeholder capex
            st.metric("Debt (kEUR)", f"{debt_keur:,.0f}")
        
        # Validate configuration
        errors = tech_config.validate_configuration()
        
        if errors:
            st.error("### Configuration Errors:")
            for err in errors:
                st.error(f"  • {err}")
        else:
            st.success("✅ Configuration is valid")
        
        # === Scenario Comparison (P90 debt sizing) ===
        if selected_scenarios and len(selected_scenarios) > 1:
            inputs = _get_inputs_from_session()
            engine = _build_engine_from_inputs(inputs)
            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            
            # Build Euribor rate curve for this run
            shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
            rate_schedule = build_rate_schedule(
                base_rate_type=debt_config.senior.base_rate_type,
                tenor_periods=tenor_periods,
                periods_per_year=2,
                base_rate_override=(
                    debt_config.senior.all_in_rate / 2 if debt_config.senior.base_rate_type == "FLAT" else
                    debt_config.senior.base_rate if debt_config.senior.base_rate_type not in ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"] else
                    None  # EURIBOR modes use curve
                ),
                floating_share=debt_config.senior.floating_share,
                fixed_share=debt_config.senior.fixed_share,
                hedge_coverage=debt_config.senior.hedged_share,
                margin_bps=debt_config.senior.margin_bps,
                base_rate_floor=debt_config.senior.base_rate_floor,
            )
            if shock_bps > 0:
                rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))
            
            with st.spinner("Running P90 sizing..."):
                try:
                    # Step 1: P90-10Y sizing run — determine fixed debt
                    p90_inputs = _inputs_for_scenario(inputs, YieldScenario.P90_10Y)
                    p90_result = cached_run_waterfall_v3(
                        inputs=p90_inputs, engine=engine,
                        rate_per_period=rate, tenor_periods=tenor_periods,
                        target_dscr=debt_config.senior.target_dscr,
                        lockup_dscr=debt_config.senior.min_dscr_lockup,
                        tax_rate=inputs.tax.corporate_rate,
                        dsra_months=debt_config.senior.dsra_months,
                        shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                        shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                        discount_rate_project=discount_rate_project, discount_rate_equity=discount_rate_equity,
                        fixed_debt_keur=None,  # Let it size for P90
                        rate_schedule=rate_schedule,  # Euribor curve
                    )
                    fixed_debt_keur = p90_result.sculpting_result.debt_keur if hasattr(p90_result, 'sculpting_result') else p90_result.debt_keur
                    
                    # Create partial function for scenario runs
                    def run_fn(inputs=inputs, fixed_debt_keur=fixed_debt_keur):
                        return cached_run_waterfall_v3(
                            inputs=inputs, engine=engine,
                            rate_per_period=rate, tenor_periods=tenor_periods,
                            target_dscr=debt_config.senior.target_dscr,
                            lockup_dscr=debt_config.senior.min_dscr_lockup,
                            tax_rate=inputs.tax.corporate_rate,
                            dsra_months=debt_config.senior.dsra_months,
                            shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                            shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                            discount_rate_project=discount_rate_project, discount_rate_equity=discount_rate_equity,
                            fixed_debt_keur=fixed_debt_keur,
                            rate_schedule=rate_schedule,  # Euribor curve
                        )
                    
                    # Build scenario results
                    scenario_map = {
                        "P50": YieldScenario.P50,
                        "P90-1y": YieldScenario.P90_1Y,
                        "P90-10y": YieldScenario.P90_10Y,
                        "P99-1y": YieldScenario.P99_1Y,
                    }
                    results = []
                    for scen in selected_scenarios:
                        yld = scenario_map.get(scen)
                        if yld:
                            scen_inputs = _inputs_for_scenario(inputs, yld)
                            r = run_scenario(scen_inputs, yld, run_fn, fixed_debt_keur=fixed_debt_keur)
                            results.append(r)
                    
                    comparison = compare_scenarios(results)
                    
                    st.markdown("### 📊 Scenario Comparison (P90-sized debt)")
                    st.caption(f"Fixed P90 debt: {fixed_debt_keur:,.0f} kEUR | DSCR target: {debt_config.senior.target_dscr}")
                    st.dataframe(
                        pd.DataFrame({
                            "Scenario": comparison["scenario"],
                            "Equity IRR": comparison["equity_irr"],
                            "Project IRR": comparison["project_irr"],
                            "NPV (kEUR)": comparison["npv_keur"],
                            "LCOE (€/MWh)": comparison["lcoe"],
                            "Avg DSCR": comparison["avg_dscr"],
                            "Min DSCR": comparison["min_dscr"],
                            "Dist. (kEUR)": comparison["distribution_keur"],
                        }),
                        use_container_width=True, hide_index=True,
                    )
                except Exception as e:
                    st.warning(f"Scenario comparison: {str(e)}")
    
    with tab_generation:
        st.subheader("Generation")
        
        # Generation chart
        st.plotly_chart(create_generation_chart(tech_config, horizon), config=CHART_CONFIG)
        
        # Show by year table
        data = []
        for y in range(1, min(11, horizon + 1)):
            data.append({
                "Year": y,
                "P50 (MWh)": round(tech_config.annual_generation_mwh(y, "P50")),
                "P90-1y (MWh)": round(tech_config.annual_generation_mwh(y, "P90-1y")),
                "P90-10y (MWh)": round(tech_config.annual_generation_mwh(y, "P90-10y")),
                "P99-1y (MWh)": round(tech_config.annual_generation_mwh(y, "P99-1y")),
            })
        
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    
    with tab_revenue:
        st.subheader("Revenue")
        
        # Show revenue config summary
        col_a, col_b = st.columns(2)
        
        with col_a:
            if revenue_config.ppa and revenue_config.ppa.ppa_enabled:
                st.metric("PPA cijena", f"{revenue_config.ppa.ppa_base_price_eur_mwh:.0f} EUR/MWh")
                st.metric("PPA trajanje", f"{revenue_config.ppa.ppa_term_years} god")
                st.metric("PPA volume", f"{revenue_config.ppa.ppa_volume_share*100:.0f}%")
            elif revenue_config.merchant and revenue_config.merchant.merchant_enabled:
                st.metric("Merchant cijena", f"{revenue_config.merchant.base_price_eur_mwh:.0f} EUR/MWh")
                st.metric("Capture rate", f"{revenue_config.merchant.capture_rate_solar*100:.0f}%")
        
        with col_b:
            gen_y1 = tech_config.annual_generation_mwh(1, "P50")
            rev_y1 = revenue_config.total_annual_revenue_keur(gen_y1, 1, tech_type.split("_")[0])
            rev_y5 = revenue_config.total_annual_revenue_keur(tech_config.annual_generation_mwh(5, "P50"), 5, tech_type.split("_")[0])
            
            st.metric("Y1 Revenue (P50)", f"{rev_y1:,.0f} kEUR")
            st.metric("Y5 Revenue (P50)", f"{rev_y5:,.0f} kEUR")
        
        # Revenue chart
        st.plotly_chart(create_revenue_chart(revenue_config, gen_y1, tech_type.split("_")[0]), config=CHART_CONFIG)
    
    with tab_debt:
        st.subheader("Debt Structure")
        
        # Show debt summary
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Gearing", f"{debt_config.senior.gearing_ratio*100:.1f}%")
            st.metric("Senior tenor", f"{debt_config.senior.tenor_years} god")
        
        with col2:
            st.metric("All-in Rate", f"{debt_config.senior.all_in_rate*100:.2f}%")
            st.metric("Target DSCR", f"{debt_config.senior.target_dscr:.2f}x")
        
        with col3:
            wACD = debt_config.weighted_average_cost_of_debt(100000)
            st.metric("WACD", f"{wACD*100:.2f}%")
            st.metric("DSRA Months", f"{debt_config.senior.dsra_months}")
        
        # Show SHL and Mezz if enabled
        if debt_config.shl and debt_config.shl.shl_enabled:
            st.markdown("---")
            st.write(f"**SHL:** {debt_config.shl.shl_keur:,.0f} kEUR @ {debt_config.shl.shl_rate*100:.1f}%")
        
        if debt_config.mezzanine and debt_config.mezzanine.mezzanine_enabled:
            st.markdown("---")
            st.write(f"**Mezzanine:** {debt_config.mezzanine.mezzanine_keur:,.0f} kEUR @ {debt_config.mezzanine.mezz_rate*100:.1f}%")
    
    with tab_pl:
        st.subheader("Profit & Loss Statement")
        
        # Run waterfall to get P&L data
        try:
            inputs = _get_inputs_from_session()
            engine = _build_engine_from_inputs(inputs)
            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            
            with st.spinner("Calculating P&L..."):
                
                rate_schedule = build_rate_schedule(
                    base_rate_type=debt_config.senior.base_rate_type,
                    tenor_periods=tenor_periods,
                    periods_per_year=2,
                    base_rate_override=(
                    debt_config.senior.all_in_rate / 2 if debt_config.senior.base_rate_type == "FLAT" else
                    debt_config.senior.base_rate if debt_config.senior.base_rate_type not in ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"] else
                    None  # EURIBOR modes use curve
                ),
                    floating_share=debt_config.senior.floating_share,
                    fixed_share=debt_config.senior.fixed_share,
                    hedge_coverage=debt_config.senior.hedged_share,
                    margin_bps=debt_config.senior.margin_bps,
                    base_rate_floor=debt_config.senior.base_rate_floor,
                )
                shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
                if shock_bps > 0:
                    rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))

                # Apply tariff/gen/capex sensitivity shocks
                sensitivity_shocks = st.session_state.get("sensitivity_shocks", {})
                if sensitivity_shocks:
                    inputs = _apply_sensitivity_shocks(inputs, sensitivity_shocks)

                result = cached_run_waterfall_v3(
                    inputs=inputs, engine=engine,
                    rate_per_period=rate, tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=discount_rate_project, discount_rate_equity=discount_rate_equity,
                    rate_schedule=rate_schedule,
                )
            
            # Determine depreciation params from tech_type
            tech_prefix = tech_type.split("_")[0] if "_" in tech_type else tech_type
            if tech_prefix == "solar":
                dep_params = DepreciationParams.create_solar_hr()
            elif tech_prefix == "wind":
                dep_params = DepreciationParams.create_wind_hr()
            else:
                dep_params = DepreciationParams.create_bess_hr()
            
            # Build financial and tax depreciation schedules (annual, kEUR)
            fin_dep_annual = financial_depreciation_schedule(inputs.capex.total_capex, dep_params, horizon)
            tax_dep_annual = tax_depreciation_schedule(inputs.capex.total_capex, dep_params, horizon)
            fin_dep_dict = {y + 1: v for y, v in enumerate(fin_dep_annual)}
            tax_dep_dict = {y + 1: v for y, v in enumerate(tax_dep_annual)}
            
            # Build income statement using domain builder
            income_rows = build_income_statement(
                result.periods, fin_dep_dict, tax_dep_dict, horizon
            )
            
            # Convert to DataFrame for display
            pl_data = []
            for row in income_rows:
                pl_data.append({
                    "Year": row.year,
                    "PPA Revenue (kEUR)": f"{row.ppa_revenue_keur:,.0f}",
                    "Total Revenue (kEUR)": f"{row.total_revenue_keur:,.0f}",
                    "OPEX (kEUR)": f"{-row.opex_keur:,.0f}",
                    "EBITDA (kEUR)": f"{row.ebitda_keur:,.0f}",
                    "EBITDA Margin (%)": f"{row.ebitda_margin_pct*100:.1f}%",
                    "Fin Depreciation (kEUR)": f"{-row.depreciation_financial_keur:,.0f}",
                    "EBIT (kEUR)": f"{row.ebit_keur:,.0f}",
                    "Interest Senior (kEUR)": f"{-row.interest_senior_keur:,.0f}",
                    "Interest SHL (kEUR)": f"{-row.interest_shl_keur:,.0f}",
                    "EBT (kEUR)": f"{row.ebt_keur:,.0f}",
                    "Tax Depreciation (kEUR)": f"{row.tax_depreciation_keur:,.0f}",
                    "Taxable Profit (kEUR)": f"{row.taxable_profit_keur:,.0f}",
                    "Tax (kEUR)": f"{-row.income_tax_keur:,.0f}",
                    "Eff. Tax Rate (%)": f"{row.effective_tax_rate_pct*100:.1f}%",
                    "Net Income (kEUR)": f"{row.net_income_keur:,.0f}",
                })
            
            if pl_data:
                df_pl = pd.DataFrame(pl_data)
                st.dataframe(df_pl.set_index("Year"), use_container_width=True)
            else:
                st.info("No operating periods available yet.")
        except Exception as e:
            st.error(f"P&L calculation failed: {str(e)}")
    
    with tab_bs:
        st.subheader("Balance Sheet")
        
        try:
            inputs = _get_inputs_from_session()
            engine = _build_engine_from_inputs(inputs)
            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            
            with st.spinner("Calculating Balance Sheet..."):
                
                rate_schedule = build_rate_schedule(
                    base_rate_type=debt_config.senior.base_rate_type,
                    tenor_periods=tenor_periods,
                    periods_per_year=2,
                    base_rate_override=(
                    debt_config.senior.all_in_rate / 2 if debt_config.senior.base_rate_type == "FLAT" else
                    debt_config.senior.base_rate if debt_config.senior.base_rate_type not in ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"] else
                    None  # EURIBOR modes use curve
                ),
                    floating_share=debt_config.senior.floating_share,
                    fixed_share=debt_config.senior.fixed_share,
                    hedge_coverage=debt_config.senior.hedged_share,
                    margin_bps=debt_config.senior.margin_bps,
                    base_rate_floor=debt_config.senior.base_rate_floor,
                )
                shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
                if shock_bps > 0:
                    rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))

                # Apply tariff/gen/capex sensitivity shocks
                sensitivity_shocks = st.session_state.get("sensitivity_shocks", {})
                if sensitivity_shocks:
                    inputs = _apply_sensitivity_shocks(inputs, sensitivity_shocks)

                result = cached_run_waterfall_v3(
                    inputs=inputs, engine=engine,
                    rate_per_period=rate, tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=discount_rate_project, discount_rate_equity=discount_rate_equity,
                    rate_schedule=rate_schedule,
                )
            
            # Determine depreciation params from tech_type
            tech_prefix = tech_type.split("_")[0] if "_" in tech_type else tech_type
            if tech_prefix == "solar":
                dep_params = DepreciationParams.create_solar_hr()
            elif tech_prefix == "wind":
                dep_params = DepreciationParams.create_wind_hr()
            else:
                dep_params = DepreciationParams.create_bess_hr()
            
            fin_dep_annual = financial_depreciation_schedule(inputs.capex.total_capex, dep_params, horizon)
            tax_dep_annual = tax_depreciation_schedule(inputs.capex.total_capex, dep_params, horizon)
            fin_dep_dict = {y + 1: v for y, v in enumerate(fin_dep_annual)}
            tax_dep_dict = {y + 1: v for y, v in enumerate(tax_dep_annual)}
            
            # Build income statement (needed for BS)
            income_rows = build_income_statement(
                result.periods, fin_dep_dict, tax_dep_dict, horizon
            )
            
            # Build dsra_schedule, cash_schedule, and distribution_schedule from waterfall periods (H2 = end of year)
            dsra_schedule = {}
            cash_schedule = {}
            distribution_schedule = {}
            for p in result.periods:
                if p.is_operation and p.period_in_year == 2:
                    dsra_schedule[p.year_index] = p.dsra_balance_keur
                    cash_schedule[p.year_index] = p.cash_balance_keur
                    distribution_schedule[p.year_index] = p.distribution_keur
            
            # Build debt schedule from waterfall
            debt_schedule = build_debt_schedule_simple(result.periods, rate)
            
            # Get equity parameters
            total_capex = inputs.capex.total_capex
            share_capital = inputs.financing.share_capital_keur
            share_premium = inputs.financing.share_premium_keur
            shl_initial = inputs.financing.shl_amount_keur if hasattr(inputs.financing, 'shl_amount_keur') else (debt_config.shl.shl_keur if debt_config.shl else 0)
            
            # Build balance sheet using domain builder
            bs_rows = build_balance_sheet(
                income_rows=income_rows,
                total_capex_keur=total_capex,
                share_capital_keur=share_capital,
                share_premium_keur=share_premium,
                shl_initial_keur=shl_initial,
                dsra_schedule=dsra_schedule,
                cash_schedule=cash_schedule,
                distribution_schedule=distribution_schedule,
                debt_schedule=debt_schedule,
            )
            
            # Check if balanced
            unbalanced = [r for r in bs_rows if not r.is_balanced]
            if unbalanced:
                st.error(f"⚠️ Balance Sheet NOT balanced in {len(unbalanced)} year(s)!")
                for r in unbalanced[:3]:
                    st.caption(f"  Year {r.year}: Assets={r.total_assets_keur:,.0f} vs L+E={r.total_liabilities_and_equity_keur:,.0f}")
            
            # Convert to DataFrame for display
            bs_data = []
            for row in bs_rows:
                bs_data.append({
                    "Year": row.year,
                    "Gross Fixed Assets (kEUR)": f"{row.gross_fixed_assets_keur:,.0f}",
                    "Accumulated Dep (kEUR)": f"{-row.accumulated_depreciation_keur:,.0f}",
                    "Net Fixed Assets (kEUR)": f"{row.net_fixed_assets_keur:,.0f}",
                    "DSRA (kEUR)": f"{row.dsra_balance_keur:,.0f}",
                    "Cash (kEUR)": f"{row.cash_and_equivalents_keur:,.0f}",
                    "Total Assets (kEUR)": f"{row.total_assets_keur:,.0f}",
                    "Senior Debt (kEUR)": f"{row.senior_debt_keur:,.0f}",
                    "SHL (kEUR)": f"{row.shl_keur:,.0f}",
                    "Total Liabilities (kEUR)": f"{row.total_liabilities_keur:,.0f}",
                    "Share Capital (kEUR)": f"{row.share_capital_keur:,.0f}",
                    "Retained Earnings (kEUR)": f"{row.retained_earnings_keur:,.0f}",
                    "Equity (kEUR)": f"{row.total_equity_keur:,.0f}",
                    "L + E (kEUR)": f"{row.total_liabilities_and_equity_keur:,.0f}",
                    "Balanced": "✅" if row.is_balanced else "❌",
                })
            
            if bs_data:
                df_bs = pd.DataFrame(bs_data)
                st.dataframe(df_bs.set_index("Year"), use_container_width=True)
            else:
                st.info("No operating periods available yet.")
        except Exception as e:
            st.error(f"Balance Sheet calculation failed: {str(e)}")
    
    with tab_cf:
        st.subheader("Cash Flow Statement")
        
        try:
            inputs = _get_inputs_from_session()
            engine = _build_engine_from_inputs(inputs)
            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            
            with st.spinner("Calculating Cash Flow..."):
                
                rate_schedule = build_rate_schedule(
                    base_rate_type=debt_config.senior.base_rate_type,
                    tenor_periods=tenor_periods,
                    periods_per_year=2,
                    base_rate_override=(
                    debt_config.senior.all_in_rate / 2 if debt_config.senior.base_rate_type == "FLAT" else
                    debt_config.senior.base_rate if debt_config.senior.base_rate_type not in ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"] else
                    None  # EURIBOR modes use curve
                ),
                    floating_share=debt_config.senior.floating_share,
                    fixed_share=debt_config.senior.fixed_share,
                    hedge_coverage=debt_config.senior.hedged_share,
                    margin_bps=debt_config.senior.margin_bps,
                    base_rate_floor=debt_config.senior.base_rate_floor,
                )
                shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
                if shock_bps > 0:
                    rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))

                # Apply tariff/gen/capex sensitivity shocks
                sensitivity_shocks = st.session_state.get("sensitivity_shocks", {})
                if sensitivity_shocks:
                    inputs = _apply_sensitivity_shocks(inputs, sensitivity_shocks)

                result = cached_run_waterfall_v3(
                    inputs=inputs, engine=engine,
                    rate_per_period=rate, tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=discount_rate_project, discount_rate_equity=discount_rate_equity,
                    rate_schedule=rate_schedule,
                )
            
            # Determine depreciation params from tech_type
            tech_prefix = tech_type.split("_")[0] if "_" in tech_type else tech_type
            if tech_prefix == "solar":
                dep_params = DepreciationParams.create_solar_hr()
            elif tech_prefix == "wind":
                dep_params = DepreciationParams.create_wind_hr()
            else:
                dep_params = DepreciationParams.create_bess_hr()
            
            fin_dep_annual = financial_depreciation_schedule(inputs.capex.total_capex, dep_params, horizon)
            tax_dep_annual = tax_depreciation_schedule(inputs.capex.total_capex, dep_params, horizon)
            fin_dep_dict = {y + 1: v for y, v in enumerate(fin_dep_annual)}
            tax_dep_dict = {y + 1: v for y, v in enumerate(tax_dep_annual)}
            
            # Build income statement
            income_rows = build_income_statement(
                result.periods, fin_dep_dict, tax_dep_dict, horizon
            )
            
            # Build dsra_schedule and cash_schedule from waterfall periods
            dsra_schedule = {}
            cash_schedule = {}
            for p in result.periods:
                if p.is_operation and p.period_in_year == 2:
                    dsra_schedule[p.year_index] = p.dsra_balance_keur
                    cash_schedule[p.year_index] = p.cash_balance_keur
            
            # Build distribution_schedule (year -> total annual distributions)
            distribution_schedule = {}
            for p in result.periods:
                if p.is_operation and p.year_index > 0:
                    if p.year_index not in distribution_schedule:
                        distribution_schedule[p.year_index] = 0.0
                    distribution_schedule[p.year_index] += p.distribution_keur
            
            # Build debt schedule from waterfall
            debt_schedule = build_debt_schedule_simple(result.periods, rate)
            
            # Get equity parameters
            total_capex = inputs.capex.total_capex
            equity_injection = inputs.financing.share_capital_keur + inputs.financing.share_premium_keur
            shl_drawdown = inputs.financing.shl_amount_keur if hasattr(inputs.financing, 'shl_amount_keur') else (debt_config.shl.shl_keur if debt_config.shl else 0)
            
            # Build cash flow statement using domain builder
            cf_rows = build_cash_flow_statement(
                income_rows=income_rows,
                total_capex_keur=total_capex,
                equity_injection_keur=equity_injection,
                shl_drawdown_keur=shl_drawdown,
                dsra_schedule=dsra_schedule,
                distribution_schedule=distribution_schedule,
                debt_schedule=debt_schedule,
            )
            
            # Convert to DataFrame for display
            cf_data = []
            for row in cf_rows:
                cf_data.append({
                    "Year": row.year,
                    "Net Income (kEUR)": f"{row.net_income_keur:,.0f}",
                    "+ Depreciation (kEUR)": f"{row.add_depreciation_keur:,.0f}",
                    "- Tax (kEUR)": f"{-row.tax_paid_keur:,.0f}",
                    "Operating CF (kEUR)": f"{row.operating_cash_flow_keur:,.0f}",
                    "Capex (kEUR)": f"{row.capex_keur:,.0f}",
                    "DSRA Movement (kEUR)": f"{row.dsra_movement_keur:,.0f}",
                    "Investing CF (kEUR)": f"{row.investing_cash_flow_keur:,.0f}",
                    "Debt Drawdown (kEUR)": f"{row.debt_drawdown_keur:,.0f}",
                    "Debt Repayment (kEUR)": f"{row.debt_repayment_keur:,.0f}",
                    "Interest (kEUR)": f"{row.interest_paid_keur:,.0f}",
                    "Dividends (kEUR)": f"{row.dividends_paid_keur:,.0f}",
                    "Financing CF (kEUR)": f"{row.financing_cash_flow_keur:,.0f}",
                    "Net CF (kEUR)": f"{row.net_cash_flow_keur:,.0f}",
                    "Closing Cash (kEUR)": f"{row.closing_cash_keur:,.0f}",
                })
            
            if cf_data:
                df_cf = pd.DataFrame(cf_data)
                st.dataframe(df_cf.set_index("Year"), use_container_width=True)
            else:
                st.info("No operating periods available yet.")
        except Exception as e:
            st.error(f"Cash Flow calculation failed: {str(e)}")
    
    with tab_waterfall:
        st.subheader("Cash Flow Waterfall")
        
        # Run waterfall calculation
        try:
            inputs = _get_inputs_from_session()
            engine = _build_engine_from_inputs(inputs)
            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            
            with st.spinner("Calculating waterfall..."):
                
                rate_schedule = build_rate_schedule(
                    base_rate_type=debt_config.senior.base_rate_type,
                    tenor_periods=tenor_periods,
                    periods_per_year=2,
                    base_rate_override=(
                    debt_config.senior.all_in_rate / 2 if debt_config.senior.base_rate_type == "FLAT" else
                    debt_config.senior.base_rate if debt_config.senior.base_rate_type not in ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"] else
                    None  # EURIBOR modes use curve
                ),
                    floating_share=debt_config.senior.floating_share,
                    fixed_share=debt_config.senior.fixed_share,
                    hedge_coverage=debt_config.senior.hedged_share,
                    margin_bps=debt_config.senior.margin_bps,
                    base_rate_floor=debt_config.senior.base_rate_floor,
                )
                shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
                if shock_bps > 0:
                    rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))

                # Apply tariff/gen/capex sensitivity shocks
                sensitivity_shocks = st.session_state.get("sensitivity_shocks", {})
                if sensitivity_shocks:
                    inputs = _apply_sensitivity_shocks(inputs, sensitivity_shocks)

                result = cached_run_waterfall_v3(
                    inputs=inputs,
                    engine=engine,
                    rate_per_period=rate,
                    tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=discount_rate_project,
                    discount_rate_equity=discount_rate_equity,
                    rate_schedule=rate_schedule,
                )
            
            # KPI Strip — uvijek na vrhu, bez expandera
            st.markdown("##### 📊 Key Metrics")
            kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
            with kpi_col1:
                st.metric("Project IRR", format_pct(result.project_irr))
                st.metric("Equity IRR", format_pct(result.equity_irr))
            with kpi_col2:
                st.metric("Avg DSCR", format_multiple(result.avg_dscr))
                st.metric("Min DSCR", format_multiple(result.min_dscr))
            with kpi_col3:
                st.metric("Total Distribution", format_keur(result.total_distribution_keur))
                st.metric("Lockup Periods", str(result.periods_in_lockup))
            with kpi_col4:
                st.metric("Total Senior DS", format_keur(result.total_senior_ds_keur))
                st.metric("Total Tax", format_keur(result.total_tax_keur))
            with kpi_col5:
                st.metric("NPV (kEUR)", format_keur(int(result.project_npv)))
                st.metric("Periods", str(len([p for p in result.periods if p.is_operation])))
            
            # Waterfall chart
            st.markdown("### Cash Flow Waterfall")
            wf_chart = create_waterfall_summary_chart(result)
            st.plotly_chart(wf_chart, config=CHART_CONFIG)
            
            # DSCR chart
            st.markdown("### DSCR Over Time")
            dscr_chart = create_dscr_chart(result)
            st.plotly_chart(dscr_chart, config=CHART_CONFIG)
            
        except Exception as e:
            st.error(f"Waterfall calculation failed: {str(e)}")
            st.info("Configure technology, revenue, and debt in the sidebar to run waterfall.")
            
            # Export buttons
            st.markdown("---")
            st.markdown("##### 📥 Export Data")
            col_exp1, col_exp2, col_exp3 = st.columns(3)
            with col_exp1:
                if 'result' in dir():
                    csv_data = []
                    for p in result.periods:
                        csv_data.append({
                            "Period": p.period,
                            "Year": p.year_index,
                            "Gen (MWh)": round(p.generation_mwh, 0),
                            "Rev (kEUR)": round(p.revenue_keur, 0),
                            "EBITDA (kEUR)": round(p.ebitda_keur, 0),
                            "CFAT (kEUR)": round(p.cf_after_tax_keur, 0),
                            "Sen DS (kEUR)": round(p.senior_ds_keur, 0),
                            "DSCR": round(p.dscr, 2) if p.dscr < float('inf') else 999,
                            "Dist (kEUR)": round(p.distribution_keur, 0),
                            "Sweep (kEUR)": round(p.cash_sweep_keur, 0),
                        })
                    df_waterfall = pd.DataFrame(csv_data)
                    csv_waterfall = df_waterfall.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📊 Download Waterfall (CSV)",
                        data=csv_waterfall,
                        file_name="waterfall.csv",
                        mime="text/csv",
                        help="Download period-level waterfall data",
                    )
            with col_exp2:
                if 'result' in dir():
                    summary_data = {
                        "Metric": ["Project IRR", "Equity IRR", "Avg DSCR", "Min DSCR",
                                   "Debt (kEUR)", "Total Distribution (kEUR)", "Total Tax (kEUR)",
                                   "Total Senior DS (kEUR)"],
                        "Value": [f"{result.project_irr*100:.2f}%", 
                                  f"{result.equity_irr*100:.2f}%" if result.equity_irr else "N/A",
                                  f"{result.avg_dscr:.3f}", f"{result.min_dscr:.3f}",
                                  f"{result.sculpting_result.debt_keur:,.0f}",
                                  f"{result.total_distribution_keur:,.0f}",
                                  f"{result.total_tax_keur:,.0f}",
                                  f"{result.total_senior_ds_keur:,.0f}"],
                    }
                    df_summary = pd.DataFrame(summary_data)
                    csv_summary = df_summary.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📋 Download Summary (CSV)",
                        data=csv_summary,
                        file_name="waterfall_summary.csv",
                        mime="text/csv",
                        help="Download summary metrics",
                    )
            with col_exp3:
                if 'result' in dir():
                    try:
                        from utils.export import export_waterfall_excel
                        import io
                        buffer = io.BytesIO()
                        export_waterfall_excel(result, buffer)
                        buffer.seek(0)
                        st.download_button(
                            label="📁 Download Excel (.xlsx)",
                            data=buffer,
                            file_name="waterfall_analysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            help="Download complete waterfall analysis as formatted Excel",
                        )
                    except Exception as e:
                        st.caption(f"Excel export error: {e}")
    
    with tab_sensitivity:
        st.subheader("📉 Sensitivity Analysis — Tornado Chart")
        
        try:
            from dataclasses import replace
            
            # Build base case inputs
            inputs = _get_inputs_from_session()
            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            base_rate_type = debt_config.senior.base_rate_type
            base_rate_override = (
                debt_config.senior.all_in_rate / 2 if base_rate_type == "FLAT" else
                debt_config.senior.base_rate if base_rate_type not in ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"] else
                None
            )
            
            rate_schedule = build_rate_schedule(
                base_rate_type=base_rate_type,
                tenor_periods=tenor_periods, periods_per_year=2,
                base_rate_override=base_rate_override,
                floating_share=debt_config.senior.floating_share,
                fixed_share=debt_config.senior.fixed_share,
                hedge_coverage=debt_config.senior.hedged_share,
                margin_bps=debt_config.senior.margin_bps,
                base_rate_floor=debt_config.senior.base_rate_floor,
            )
            
            def compute_waterfall(inputs_mod):
                """Run waterfall with modified inputs."""
                freq = PF.SEMESTRIAL if inputs_mod.info.period_frequency == PeriodFrequency.SEMESTRIAL else PF.ANNUAL
                engine_mod = PeriodEngine(
                    financial_close=inputs_mod.info.financial_close,
                    construction_months=inputs_mod.info.construction_months,
                    horizon_years=inputs_mod.info.horizon_years,
                    ppa_years=inputs_mod.revenue.ppa_term_years,
                    frequency=freq,
                )
                return cached_run_waterfall_v3(
                    inputs=inputs_mod, engine=engine_mod,
                    rate_per_period=rate, tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=discount_rate_project,
                    discount_rate_equity=discount_rate_equity,
                    rate_schedule=rate_schedule,
                )
            
            # Run base case
            with st.spinner("Running base case waterfall..."):
                base_result = compute_waterfall(inputs)
            base_irr = base_result.project_irr
            base_dscr = base_result.avg_dscr
            
            # Define sensitivity variables and ranges
            sensitivity_vars = [
                {"name": "PPA Tariff", "base_mult": 1.0, "range": (0.75, 1.30), "steps": 7, "unit": "x"},
                {"name": "Generation", "base_mult": 1.0, "range": (0.80, 1.20), "steps": 5, "unit": "x"},
                {"name": "Interest Rate", "base_mult": 0.0, "range": (-150, 150), "steps": 7, "unit": "bps"},
                {"name": "CAPEX", "base_mult": 1.0, "range": (0.85, 1.20), "steps": 5, "unit": "x"},
            ]
            
            tornado_data = []
            spider_data = {}  # {var_name: {"values": [...], "irr": [...]}}
            progress_bar = st.progress(0, text="Running sensitivity analysis...")
            total_steps = sum(v["steps"] for v in sensitivity_vars)
            completed = 0
            
            for var in sensitivity_vars:
                var_name = var["name"]
                var_values = []
                irr_values = []
                
                if var_name == "PPA Tariff":
                    # Tariff multiplier: scale ppa_base_tariff
                    base_tariff = inputs.revenue.ppa_base_tariff
                    for step in range(var["steps"]):
                        mult = var["range"][0] + step * (var["range"][1] - var["range"][0]) / (var["steps"] - 1)
                        inputs_mod = replace(inputs, revenue=replace(inputs.revenue, ppa_base_tariff=base_tariff * mult))
                        result = compute_waterfall(inputs_mod)
                        var_values.append(mult)
                        irr_values.append(result.project_irr)
                        completed += 1
                        progress_bar.progress(completed / total_steps, text=f"{var_name}: {mult:.2f}x")
                        
                elif var_name == "Generation":
                    # Generation: scale operating_hours_p50
                    tech = inputs.technical
                    base_gen = tech.operating_hours_p50
                    base_gen_p90 = tech.operating_hours_p90_10y
                    for step in range(var["steps"]):
                        mult = var["range"][0] + step * (var["range"][1] - var["range"][0]) / (var["steps"] - 1)
                        inputs_mod = replace(inputs, technical=replace(tech,
                            operating_hours_p50=base_gen * mult,
                            operating_hours_p90_10y=int(base_gen_p90 * mult),
                        ))
                        result = compute_waterfall(inputs_mod)
                        var_values.append(mult)
                        irr_values.append(result.project_irr)
                        completed += 1
                        progress_bar.progress(completed / total_steps, text=f"{var_name}: {mult:.2f}x")
                        
                elif var_name == "Interest Rate":
                    # Rate: add/subtract bps from all_in_rate
                    base_rate_val = debt_config.senior.all_in_rate
                    rate_schedule_mod = build_rate_schedule(
                        base_rate_type="FLAT",
                        tenor_periods=tenor_periods, periods_per_year=2,
                        base_rate_override=base_rate_val / 2,
                        floating_share=debt_config.senior.floating_share,
                        fixed_share=debt_config.senior.fixed_share,
                        hedge_coverage=debt_config.senior.hedged_share,
                        margin_bps=debt_config.senior.margin_bps + int(var["range"][0]),  # will be updated per step
                        base_rate_floor=debt_config.senior.base_rate_floor,
                    )
                    for step in range(var["steps"]):
                        bps_offset = var["range"][0] + step * (var["range"][1] - var["range"][0]) / (var["steps"] - 1)
                        new_margin = max(0, debt_config.senior.margin_bps + int(bps_offset))
                        rate_sched = build_rate_schedule(
                            base_rate_type="FLAT",
                            tenor_periods=tenor_periods, periods_per_year=2,
                            base_rate_override=base_rate_val / 2,
                            floating_share=debt_config.senior.floating_share,
                            fixed_share=debt_config.senior.fixed_share,
                            hedge_coverage=debt_config.senior.hedged_share,
                            margin_bps=new_margin,
                            base_rate_floor=debt_config.senior.base_rate_floor,
                        )
                        freq = PF.SEMESTRIAL if inputs.info.period_frequency == PeriodFrequency.SEMESTRIAL else PF.ANNUAL
                        engine_mod = PeriodEngine(
                            financial_close=inputs.info.financial_close,
                            construction_months=inputs.info.construction_months,
                            horizon_years=inputs.info.horizon_years,
                            ppa_years=inputs.revenue.ppa_term_years,
                            frequency=freq,
                        )
                        result = cached_run_waterfall_v3(
                            inputs=inputs, engine=engine_mod,
                            rate_per_period=rate, tenor_periods=tenor_periods,
                            target_dscr=debt_config.senior.target_dscr,
                            lockup_dscr=debt_config.senior.min_dscr_lockup,
                            tax_rate=tax_config.corporate_tax_rate,
                            dsra_months=debt_config.senior.dsra_months,
                            shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                            shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                            discount_rate_project=discount_rate_project,
                            discount_rate_equity=discount_rate_equity,
                            rate_schedule=rate_sched,
                        )
                        var_values.append(bps_offset)
                        irr_values.append(result.project_irr)
                        completed += 1
                        progress_bar.progress(completed / total_steps, text=f"{var_name}: {bps_offset:+.0f}bps")
                        
                elif var_name == "CAPEX":
                    # CAPEX: scale all individual capex items
                    capex = inputs.capex
                    capex_attrs = ['epc_contract', 'production_units', 'epc_other', 'grid_connection',
                                   'ops_prep', 'insurances', 'lease_tax', 'construction_mgmt_a',
                                   'commissioning', 'audit_legal', 'construction_mgmt_b',
                                   'contingencies', 'taxes', 'project_acquisition', 'project_rights']
                    for step in range(var["steps"]):
                        mult = var["range"][0] + step * (var["range"][1] - var["range"][0]) / (var["steps"] - 1)
                        scale = mult
                        scaled = {a: CapexItem(name=getattr(capex, a).name,
                                           amount_keur=getattr(capex, a).amount_keur * scale,
                                           y0_share=getattr(capex, a).y0_share,
                                           spending_profile=getattr(capex, a).spending_profile)
                                  for a in capex_attrs}
                        inputs_mod = replace(inputs, capex=replace(capex, **scaled))
                        result = compute_waterfall(inputs_mod)
                        var_values.append(mult)
                        irr_values.append(result.project_irr)
                        completed += 1
                        progress_bar.progress(completed / total_steps, text=f"{var_name}: {mult:.2f}x")
                
                # Find low/high IRR values
                irr_low = min(irr_values)
                irr_high = max(irr_values)
                idx_low = irr_values.index(irr_low)
                idx_high = irr_values.index(irr_high)
                
                tornado_data.append({
                    "name": var_name,
                    "low": irr_low - base_irr,
                    "high": irr_high - base_irr,
                    "base_value": var["base_mult"],
                    "unit": var["unit"],
                })
                
                # Store spider data
                spider_data[var_name] = {
                    "values": var_values,
                    "irr": irr_values,
                    "unit": var["unit"],
                }
            
            progress_bar.empty()
            
            # Sort by max absolute impact
            tornado_data.sort(key=lambda x: max(abs(x["low"]), abs(x["high"])), reverse=True)
            
            # Render tornado chart
            fig = go.Figure()
            names = [d["name"] for d in tornado_data]
            # Negative = IRR decreases (left side, red)
            # Positive = IRR increases (right side, green)
            lows = [-d["low"] * 100 for d in tornado_data]  # Negate: low impact → left bar
            highs = [d["high"] * 100 for d in tornado_data]
            
            fig.add_trace(go.Bar(
                name="IRR Decrease", x=lows, y=names, orientation="h",
                marker_color="#d32f2f", hovertemplate="%{x:.2f}%<extra></extra>"
            ))
            fig.add_trace(go.Bar(
                name="IRR Increase", x=highs, y=names, orientation="h",
                marker_color="#388e3c", hovertemplate="%{x:.2f}%<extra></extra>"
            ))
            
            fig.update_layout(
                title={"text": f"Project IRR Sensitivity (Base: {base_irr*100:.2f}%)", "font": {"size": 14}},
                barmode="relative",
                height=320,
                xaxis_title="IRR Impact (%)",
                showlegend=True,
                legend={"orientation": "h", "y": -0.2, "x": 0.5, "xanchor": "center"},
                margin={"t": 50, "b": 60},
            )
            st.plotly_chart(fig, config=CHART_CONFIG)
            
            # Show summary table
            st.markdown("##### Sensitivity Summary")
            summary_rows = []
            for d in tornado_data:
                summary_rows.append({
                    "Variable": d["name"],
                    "Base IRR": f"{base_irr*100:.2f}%",
                    "Low": f"{(base_irr + d['low'])*100:.2f}%",
                    "High": f"{(base_irr + d['high'])*100:.2f}%",
                    "Δ IRR": f"{d['high']*100:+.2f}% / {d['low']*100:+.2f}%",
                })
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
            
            st.caption(f"Sensitivity analysis complete. Base case: {base_irr*100:.3f}% IRR, {base_dscr:.3f}x Avg DSCR.")
            
            # =================================================================
            # SPIDER TABLE — all IRR values for each variable
            # =================================================================
            st.markdown("##### 🕷️ Spider Table — IRR by Variable")
            
            if spider_data:
                spider_rows = []
                for var_name, data in spider_data.items():
                    row = {"Variable": var_name}
                    for i, (val, irr) in enumerate(zip(data["values"], data["irr"])):
                        unit_suffix = data["unit"] if i > 0 else ""
                        col_name = f"{val:.2f}{unit_suffix}"
                        row[col_name] = f"{irr*100:.2f}%"
                    spider_rows.append(row)
                
                if spider_rows:
                    df_spider = pd.DataFrame(spider_rows)
                    st.dataframe(df_spider, use_container_width=True, hide_index=True)
                    st.caption("Spider table: IRR at each step of the sensitivity range. Base case highlighted.")
            else:
                st.info("Spider data not available.")
            
            # =================================================================
            # TWO-WAY SENSITIVITY — heatmap matrix
            # =================================================================
            st.markdown("##### 🔲 Two-Way Sensitivity — IRR Matrix")
            
            # Let user select 2 variables for 2-way analysis
            col_tw1, col_tw2 = st.columns(2)
            with col_tw1:
                tw_var1 = st.selectbox(
                    "Variable 1 (rows)",
                    ["PPA Tariff", "Generation", "Interest Rate", "CAPEX"],
                    index=0,
                    key="tw_var1",
                )
            with col_tw2:
                tw_var2 = st.selectbox(
                    "Variable 2 (columns)",
                    ["PPA Tariff", "Generation", "Interest Rate", "CAPEX"],
                    index=1,
                    key="tw_var2",
                )
            
            if st.button("Run Two-Way Sensitivity", key="run_two_way"):
                with st.spinner(f"Running two-way analysis: {tw_var1} vs {tw_var2}..."):
                    
                    # Define ranges for each variable
                    var_ranges = {
                        "PPA Tariff": {"base": 1.0, "min": 0.75, "max": 1.30, "steps": 5, "unit": "x"},
                        "Generation": {"base": 1.0, "min": 0.80, "max": 1.20, "steps": 5, "unit": "x"},
                        "Interest Rate": {"base": 0, "min": -150, "max": 150, "steps": 5, "unit": "bps"},
                        "CAPEX": {"base": 1.0, "min": 0.85, "max": 1.20, "steps": 5, "unit": "x"},
                    }
                    
                    r1 = var_ranges[tw_var1]
                    r2 = var_ranges[tw_var2]
                    
                    # Build value grids
                    vals1 = [r1["min"] + i * (r1["max"] - r1["min"]) / (r1["steps"] - 1) for i in range(r1["steps"])]
                    vals2 = [r2["min"] + i * (r2["max"] - r2["min"]) / (r2["steps"] - 1) for i in range(r2["steps"])]
                    
                    # Compute matrix
                    matrix = []
                    for v1 in vals1:
                        row = []
                        for v2 in vals2:
                            try:
                                # Build modified inputs
                                inputs_v1 = inputs
                                inputs_v2 = inputs
                                
                                if tw_var1 == "PPA Tariff":
                                    base_t = inputs.revenue.ppa_base_tariff
                                    inputs_v1 = replace(inputs, revenue=replace(inputs.revenue, ppa_base_tariff=base_t * v1))
                                elif tw_var1 == "Generation":
                                    tech = inputs.technical
                                    base_g = tech.operating_hours_p50
                                    base_g_p90 = tech.operating_hours_p90_10y
                                    inputs_v1 = replace(inputs, technical=replace(tech,
                                        operating_hours_p50=base_g * v1,
                                        operating_hours_p90_10y=int(base_g_p90 * v1),
                                    ))
                                elif tw_var1 == "CAPEX":
                                    capex = inputs.capex
                                    capex_attrs = ['epc_contract', 'production_units', 'epc_other', 'grid_connection',
                                                   'ops_prep', 'insurances', 'lease_tax', 'construction_mgmt_a',
                                                   'commissioning', 'audit_legal', 'construction_mgmt_b',
                                                   'contingencies', 'taxes', 'project_acquisition', 'project_rights']
                                    scaled = {a: CapexItem(name=getattr(capex, a).name,
                                                      amount_keur=getattr(capex, a).amount_keur * v1,
                                                      y0_share=getattr(capex, a).y0_share,
                                                      spending_profile=getattr(capex, a).spending_profile)
                                              for a in capex_attrs}
                                    inputs_v1 = replace(inputs, capex=replace(capex, **scaled))
                                # Rate handled separately below
                                
                                if tw_var2 == "PPA Tariff":
                                    base_t = inputs.revenue.ppa_base_tariff
                                    inputs_v2 = replace(inputs_v1, revenue=replace(inputs_v1.revenue, ppa_base_tariff=base_t * v2))
                                elif tw_var2 == "Generation":
                                    tech = inputs_v1.technical
                                    base_g = tech.operating_hours_p50
                                    base_g_p90 = tech.operating_hours_p90_10y
                                    inputs_v2 = replace(inputs_v1, technical=replace(tech,
                                        operating_hours_p50=base_g * v2,
                                        operating_hours_p90_10y=int(base_g_p90 * v2),
                                    ))
                                elif tw_var2 == "CAPEX":
                                    capex = inputs_v1.capex
                                    capex_attrs = ['epc_contract', 'production_units', 'epc_other', 'grid_connection',
                                                   'ops_prep', 'insurances', 'lease_tax', 'construction_mgmt_a',
                                                   'commissioning', 'audit_legal', 'construction_mgmt_b',
                                                   'contingencies', 'taxes', 'project_acquisition', 'project_rights']
                                    scaled = {a: CapexItem(name=getattr(capex, a).name,
                                                      amount_keur=getattr(capex, a).amount_keur * v2,
                                                      y0_share=getattr(capex, a).y0_share,
                                                      spending_profile=getattr(capex, a).spending_profile)
                                              for a in capex_attrs}
                                    inputs_v2 = replace(inputs_v1, capex=replace(capex, **scaled))
                                
                                # Handle rate for both variables
                                base_rate_val = debt_config.senior.all_in_rate
                                rate1 = v1 if tw_var1 == "Interest Rate" else (0 if tw_var2 != "Interest Rate" else v2)
                                rate2 = v2 if tw_var2 == "Interest Rate" else (0 if tw_var1 != "Interest Rate" else v1)
                                
                                total_bps = int(rate1 + rate2)
                                new_margin = max(0, debt_config.senior.margin_bps + total_bps)
                                rate_sched_tw = build_rate_schedule(
                                    base_rate_type="FLAT",
                                    tenor_periods=tenor_periods, periods_per_year=2,
                                    base_rate_override=base_rate_val / 2,
                                    floating_share=debt_config.senior.floating_share,
                                    fixed_share=debt_config.senior.fixed_share,
                                    hedge_coverage=debt_config.senior.hedged_share,
                                    margin_bps=new_margin,
                                    base_rate_floor=debt_config.senior.base_rate_floor,
                                )
                                
                                result = cached_run_waterfall_v3(
                                    inputs=inputs_v2, engine=engine,
                                    rate_per_period=rate, tenor_periods=tenor_periods,
                                    target_dscr=debt_config.senior.target_dscr,
                                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                                    tax_rate=tax_config.corporate_tax_rate,
                                    dsra_months=debt_config.senior.dsra_months,
                                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                                    discount_rate_project=discount_rate_project,
                                    discount_rate_equity=discount_rate_equity,
                                    rate_schedule=rate_sched_tw,
                                )
                                row.append(result.project_irr * 100)
                            except Exception as e:
                                row.append(None)
                        matrix.append(row)
                    
                    # Render heatmap
                    
                    # Format labels
                    labels1 = [f"{v1:.2f}" for v1 in vals1]
                    labels2 = [f"{v2:.0f}" if tw_var2 == "Interest Rate" else f"{v2:.2f}" for v2 in vals2]
                    
                    # Create annotations
                    annotations = []
                    for i, row_vals in enumerate(matrix):
                        for j, val in enumerate(row_vals):
                            if val is not None:
                                annotations.append(
                                    dict(x=j, y=i, text=f"{val:.2f}%",
                                         showarrow=False, font=dict(color="white" if 7.5 < val < 10 else "black"))
                                )
                    
                    fig_tw = go.Figure(data=go.Heatmap(
                        z=matrix,
                        x=labels2,
                        y=labels1,
                        colorscale="RdYlGn",
                        reversescale=False,
                        text=[[f"{v:.2f}%" if v else "N/A" for v in row] for row in matrix],
                        showscale=True,
                        colorbar=dict(title="IRR (%)"),
                    ))
                    fig_tw.update_layout(
                        title={"text": f"Project IRR: {tw_var1} (rows) vs {tw_var2} (cols)", "font": {"size": 14}},
                        xaxis_title=tw_var2,
                        yaxis_title=tw_var1,
                        height=400,
                        annotations=annotations,
                    )
                    st.plotly_chart(fig_tw, config=CHART_CONFIG)
                    
                    # Show base case values
                    st.caption(f"Base case: {tw_var1}=1.0, {tw_var2}=0 bps → IRR={base_irr*100:.2f}%")
            
        except Exception as e:
            st.error(f"Sensitivity analysis failed: {str(e)}")
            import traceback
            st.code(traceback.format_exc())


    with tab_covenant:
        st.subheader("🏦 Bank Covenant Compliance")
        
        try:
            inputs = _get_inputs_from_session()
            engine = _build_engine_from_inputs(inputs)
            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            base_rate_type = debt_config.senior.base_rate_type
            base_rate_override = (
                debt_config.senior.all_in_rate / 2 if base_rate_type == "FLAT" else
                debt_config.senior.base_rate if base_rate_type not in ["FLAT", "EURIBOR_1M", "EURIBOR_3M", "EURIBOR_6M"] else
                None
            )
            
            rate_schedule = build_rate_schedule(
                base_rate_type=base_rate_type,
                tenor_periods=tenor_periods, periods_per_year=2,
                base_rate_override=base_rate_override,
                floating_share=debt_config.senior.floating_share,
                fixed_share=debt_config.senior.fixed_share,
                hedge_coverage=debt_config.senior.hedged_share,
                margin_bps=debt_config.senior.margin_bps,
                base_rate_floor=debt_config.senior.base_rate_floor,
            )
            shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
            if shock_bps > 0:
                rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))
            sensitivity_shocks = st.session_state.get("sensitivity_shocks", {})
            if sensitivity_shocks:
                inputs = _apply_sensitivity_shocks(inputs, sensitivity_shocks)

            result = cached_run_waterfall_v3(
                inputs=inputs, engine=engine,
                rate_per_period=rate, tenor_periods=tenor_periods,
                target_dscr=debt_config.senior.target_dscr,
                lockup_dscr=debt_config.senior.min_dscr_lockup,
                tax_rate=tax_config.corporate_tax_rate,
                dsra_months=debt_config.senior.dsra_months,
                shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                discount_rate_project=discount_rate_project, discount_rate_equity=discount_rate_equity,
                rate_schedule=rate_schedule,
            )
            
            # Thresholds
            dscr_min = debt_config.senior.target_dscr  # 1.15
            llcr_min = debt_config.senior.min_llcr    # 1.15
            plcr_min = debt_config.senior.min_plcr    # 1.20
            lockup_min = debt_config.senior.min_dscr_lockup  # 1.10
            
            # Build covenant dataframe from waterfall periods (H2 = year-end)
            covenant_rows = []
            for p in result.periods:
                if p.is_operation and p.period_in_year == 2:
                    dscr = p.dscr if p.dscr < float('inf') else 999
                    llcr = p.llcr if p.llcr < float('inf') else 999
                    plcr = p.plcr if p.plcr < float('inf') else 999
                    lockup = "🔴 LOCKUP" if p.lockup_active else "✅ OK"
                    
                    covenant_rows.append({
                        "Year": p.year_index,
                        "DSCR": round(dscr, 3),
                        "LLCR": round(llcr, 3),
                        "PLCR": round(plcr, 3),
                        "Lockup": lockup,
                        "DSCR Status": "🔴" if dscr < lockup_min else ("🟡" if dscr < dscr_min else "✅"),
                        "LLCR Status": "🔴" if llcr < llcr_min else "✅",
                        "PLCR Status": "🔴" if plcr < plcr_min else "✅",
                    })
            
            if covenant_rows:
                df_cov = pd.DataFrame(covenant_rows)
                
                # KPIs
                kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
                with kpi_col1:
                    st.metric("Min DSCR", f"{df_cov['DSCR'].min():.3f}x", 
                              delta="🔴 BREACH" if df_cov['DSCR'].min() < lockup_min else "✅ OK")
                with kpi_col2:
                    st.metric("Avg DSCR", f"{df_cov['DSCR'].mean():.3f}x")
                with kpi_col3:
                    st.metric("Min LLCR", f"{df_cov['LLCR'].min():.3f}x",
                              delta="🔴 BREACH" if df_cov['LLCR'].min() < llcr_min else "✅ OK")
                with kpi_col4:
                    st.metric("Min PLCR", f"{df_cov['PLCR'].min():.3f}x",
                              delta="🔴 BREACH" if df_cov['PLCR'].min() < plcr_min else "✅ OK")
                
                # Covenant table with status highlighting
                st.markdown("##### Covenant Schedule")
                
                # Display with colored status columns
                display_cols = ["Year", "DSCR", "DSCR Status", "LLCR", "LLCR Status", "PLCR", "PLCR Status", "Lockup"]
                st.dataframe(
                    df_cov[display_cols].set_index("Year"),
                    use_container_width=True,
                    column_config={
                        "DSCR": st.column_config.NumberColumn("DSCR", format="%.3f"),
                        "LLCR": st.column_config.NumberColumn("LLCR", format="%.3f"),
                        "PLCR": st.column_config.NumberColumn("PLCR", format="%.3f"),
                    }
                )
                
                # Legend
                st.markdown("""
                **Legend:**
                - 🔴 BREACH = below minimum threshold  
                - 🟡 WARNING = below target but above lockup
                - ✅ OK = within covenant limits
                - 🔴 LOCKUP = distribution blocked (DSCR < 1.10x)
                """)
                
                # Thresholds info
                st.caption(f"Thresholds — DSCR: {dscr_min:.2f}x target / {lockup_min:.2f}x lockup | LLCR: {llcr_min:.2f}x | PLCR: {plcr_min:.2f}x")
            else:
                st.info("No operating periods available yet.")
                
        except Exception as e:
            st.error(f"Covenant calculation failed: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

    with tab_tax:
        st.subheader("Tax Parameters")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Corporate Tax", f"{tax_config.corporate_tax_rate*100:.1f}%")
            st.metric("Loss Carryforward", f"{tax_config.loss_carryforward_years} years")
        with col2:
            st.metric("ATAD", "Yes" if tax_config.atad_applies else "No")
            st.metric("ATAD Limit", f"{tax_config.atad_ebitda_limit*100:.0f}% EBITDA")
        with col3:
            st.metric("VAT Rate", f"{tax_config.vat_rate*100:.1f}%")
            st.metric("WHT Dividends", f"{tax_config.wht_dividends*100:.1f}%")
        
        col4, col5 = st.columns(2)
        with col4:
            st.metric("Thin Cap", f"D/E {tax_config.thin_cap_ratio:.1f}x" if tax_config.thin_cap_enabled else "N/A")
        
        st.markdown("### Tax Calculation")
        st.info("Tax is calculated as: max(0, EBITDA - Interest - Depreciation) × Tax Rate")
        st.info("ATAD limits deductible interest to 30% of EBITDA (for EU jurisdictions)")
    
    with tab_regulatory:
        st.subheader("Regulatory Parameters")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Jurisdiction", regulatory_config.jurisdiction)
            st.metric("Permits Timeline", f"{regulatory_config.permitting_timeline_months} months")
        with col2:
            st.metric("Grid Type", regulatory_config.grid_connection_type)
            st.metric("Congestion Risk", regulatory_config.grid_congestion_risk)
        with col3:
            st.metric("Curtailment", f"{regulatory_config.mandatory_curtailment_pct*100:.1f}%")
            st.metric("GO/REC", f"{regulatory_config.rec_price_eur_mwh:.2f} EUR/MWh" if regulatory_config.rec_enabled else "N/A")
        
        # REC revenue
        if regulatory_config.rec_enabled:
            gen_y1 = tech_config.annual_generation_mwh(1, "P50")
            rec_rev = regulatory_config.rec_revenue_keur(gen_y1)
            st.metric("Y1 REC Revenue", f"{rec_rev:,.0f} kEUR")
    
    with tab_validation:
        st.subheader("Configuration Validation")
        
        # Technology validation
        st.markdown("### Technology")
        tech_errors = tech_config.validate_configuration()
        if tech_errors:
            for err in tech_errors:
                st.error(f"❌ {err}")
        else:
            st.success("✅ Technology: valjano")
        
        # Debt validation
        st.markdown("### Debt")
        debt_errors = debt_config.validate_configuration()
        if debt_errors:
            for err in debt_errors:
                st.error(f"❌ {err}")
        else:
            st.success("✅ Debt: valjano")
        
        # Warnings based on benchmarks
        st.markdown("### Benchmark Warnings")
        
        # Create CAPEX and OPEX for benchmark validation
        tech_type_lower = tech_type.split("_")[0] if "_" in tech_type else tech_type
        
        if tech_type_lower == "solar" and tech_config.solar:
            capex = CapexBreakdown.create_solar_defaults(tech_config.solar.capacity_ac_mw)
            warnings = capex.validate_benchmark(jurisdiction)
            if warnings:
                for w in warnings:
                    st.warning(f"⚠️ {w}")
            else:
                st.success("✅ Solar CAPEX within benchmark")
            
            opex = OpexParams.create_solar_defaults(tech_config.solar.capacity_ac_mw)
            opex_errors = opex.validate_configuration()
            if opex_errors:
                for err in opex_errors:
                    st.error(f"❌ OPEX: {err}")
        
        elif tech_type_lower == "wind" and tech_config.wind:
            capex = CapexBreakdown.create_wind_defaults(tech_config.wind.capacity_mw)
            warnings = capex.validate_benchmark(jurisdiction)
            if warnings:
                for w in warnings:
                    st.warning(f"⚠️ {w}")
            else:
                st.success("✅ Wind CAPEX within benchmark")
        
        elif tech_type_lower == "bess" and tech_config.bess:
            capex = CapexBreakdown.create_bess_defaults(
                tech_config.bess.power_capacity_mw, 
                tech_config.bess.energy_capacity_mwh / tech_config.bess.power_capacity_mw
            )
            warnings = capex.validate_benchmark(jurisdiction)
            if warnings:
                for w in warnings:
                    st.warning(f"⚠️ {w}")
            else:
                st.success("✅ BESS CAPEX within benchmark")
        
        # Tax and Regulatory validation
        st.markdown("### Tax & Regulatory")
        if tax_config:
            tax_errors = tax_config.validate_configuration()
            if tax_errors:
                for err in tax_errors:
                    st.error(f"❌ Tax: {err}")
            else:
                st.success("✅ Tax: valjano")
        
        if regulatory_config:
            reg_errors = regulatory_config.validate_configuration()
            if reg_errors:
                for err in reg_errors:
                    st.error(f"❌ Regulatory: {err}")
            else:
                st.success("✅ Regulatory: valjano")


if __name__ == "__main__":
    main()