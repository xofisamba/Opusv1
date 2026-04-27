"""Session state initialization for Oborovo financial model.

Provides init_session_state() and defaults dict.
"""
from datetime import date
from enum import Enum
from typing import Any, Optional
from sqlalchemy.orm import sessionmaker


# Default values matching original model
DEFAULTS = {
    # Project
    'project_name': 'Solar Project',
    'project_company': 'Company',
    'technology': 'Solar',

    # Capacity
    'capacity_dc': 0.0,
    'capacity_ac': 0.0,

    # Wind
    'wind_capacity': 0.0,
    'turbine_rating': 6.0,
    'num_turbines': 10,
    'wind_speed': 0.0,
    'hub_height': 100,
    'wake_effects': 0.0,
    'curtailment': 0.0,

    # Revenue
    'ppa_base_tariff': 0.0,
    'tariff_escalation': 0.02,
    'ppa_term': 10,
    'merchant_price': 0.0,
    'merchant_tail_enabled': False,

    # Yield
    'yield_p50': 0.0,
    'yield_p90': 0.0,
    'yield_p99': 0.0,
    'availability_wind': 0.95,

    # Financing
    'gearing_ratio': 0.70,
    'debt_tenor': 12,
    'repayment_frequency': 12,
    'base_rate': 0.0303,
    'margin': 2.0,
    'arrangement_fee': 1.5,
    'commitment_fee': 0.5,
    'target_dscr': 1.15,
    'debt_sculpting': True,
    'debt_sizing_method': 'DSCR-Based (Sculpted)',

    # Tax
    'corporate_tax_rate': 0.0,
    'depreciation_rate': 0.0333,
    'depreciation_period': 30,
    'thin_cap_jurisdiction': 'None (No restriction)',
    'thin_cap_equity': 15000,

    # Construction
    'construction_start_date': date(2025, 1, 1),
    'construction_period': 12,
    'semi_annual_mode': False,
    'idc_capitalization': True,
    'idc_rate': 0.06,

    # BESS
    'bess_enabled': False,
    'bess_capacity_mwh': 10.0,
    'bess_power_mw': 5.0,
    'bess_cost_per_mwh': 250000,
    'bess_roundtrip_efficiency': 0.88,
    'bess_cycle_life': 5000,
    'bess_degradation_rate': 0.02,
    'bess_annual_cycles': 365,

    # Reserves
    'cash_sweep_enabled': False,
    'cash_sweep_threshold': 1.2,
    'dsra_enabled': True,
    'dsra_months': 6,
    'mra_enabled': False,
    'mra_months': 3,

    # SHL
    'shl_rate': 0.0,

    # Opex items (Task 0.6)
    'opex_items': None,  # None = use blank template

    # Sponsors / equity structure (Task 0.7)
    'sponsors': [
        {"sponsor_id": "SP-001", "name": "Investor 1",
         "equity_pct": 100.0, "shl_pct": 0.0, "shl_rate_pct": 8.0},
    ],
    'distribution_policy': 'pro_rata',

    # Horizon
    'investment_horizon': 30,

    # Active sheet
    'active_sheet': '🏠 Dashboard',

    # Expander states (for collapse/expand all)
    'exp_project': True,
    'exp_revenue': False,
    'exp_yield': False,
    'exp_financing': True,
    'exp_tax': False,
    'exp_construction': False,
    'exp_reserves': False,
    'exp_horizon': False,
}


def _opex_items_to_dict(items) -> list[dict]:
    """Convert OpexItem tuple to list of dicts for session state."""
    return [
        {
            "code": getattr(item, 'code', f"OP.{i:02d}"),
            "name": item.name,
            "category": getattr(item, 'category', 'Other'),
            "y1_amount_keur": item.y1_amount_keur,
            "inflation_pct": item.annual_inflation * 100,
            "deductible": getattr(item, 'deductible_for_tax', True),
        }
        for i, item in enumerate(items)
    ]


def _defaults_to_project_inputs(flat: dict) -> dict:
    """Convert flat session-state dict to nested ProjectInputs-compatible dict.

    Maps flat DEFAULTS keys to nested structure expected by persistence layer.
    Used when auto-creating a default project.
    """
    import copy
    d = copy.deepcopy(flat)

    # Pull out relevant fields
    capacity_mw = d.get('capacity_ac', d.get('capacity_dc', 48.7))
    yield_p50 = d.get('yield_p50', 1494.0)
    yield_p90_10y = d.get('yield_p90', 1410.0)
    ppa_tariff = d.get('ppa_base_tariff', 65.0)
    ppa_term = d.get('ppa_term', 10)
    ppa_index = d.get('tariff_escalation', 0.02)
    gearing = d.get('gearing_ratio', 0.70)
    tenor = d.get('debt_tenor', 12)
    base_rate = d.get('base_rate', 0.0303)
    margin = d.get('margin', 2.0)
    target_dscr = d.get('target_dscr', 1.15)
    dsra_months = d.get('dsra_months', 6)
    corporate_tax = d.get('corporate_tax_rate', 0.10)

    # Build nested info dict
    info = {
        "name": d.get('project_name', 'Solar Project'),
        "company": d.get('project_company', 'Company'),
        "code": "AUTO-001",
        "country_iso": "HR",
        "financial_close": "2029-06-29",
        "construction_months": int(d.get('construction_period', 12)),
        "cod_date": "2030-06-29",
        "horizon_years": int(d.get('investment_horizon', 30)),
        "period_frequency": "SEMESTRIAL",
    }

    technical = {
        "capacity_mw": float(capacity_mw),
        "yield_scenario": "P_50",
        "operating_hours_p50": float(yield_p50),
        "operating_hours_p90_10y": float(yield_p90_10y),
        "operating_hours_p99_1y": None,
        "pv_degradation": 0.004,
        "bess_degradation": 0.003,
        "plant_availability": 0.99,
        "grid_availability": 0.99,
        "bess_enabled": bool(d.get('bess_enabled', False)),
    }

    # Build opex from flat opex_items
    opex_items_raw = d.get('opex_items') or []
    opex_list = []
    for item in opex_items_raw:
        opex_list.append({
            "name": item.get('name', 'Unknown'),
            "y1_amount_keur": float(item.get('y1_amount_keur', 0)),
            "annual_inflation": float(item.get('inflation_pct', 2.0)) / 100,
        })
    opex = {"items": opex_list}

    revenue = {
        "ppa_base_tariff": float(ppa_tariff),
        "ppa_term_years": int(ppa_term),
        "ppa_index": float(ppa_index),
        "ppa_production_share": 1.0,
        "market_scenario": "Central",
        "market_prices_curve": list(range(65, 96)),
        "market_inflation": 0.02,
        "balancing_cost_pv": 0.025,
        "co2_enabled": False,
    }

    financing = {
        "share_capital_keur": 500.0,
        "share_premium_keur": 0.0,
        "shl_amount_keur": 0.0,
        "shl_rate": 0.08,
        "gearing_ratio": float(gearing),
        "senior_debt_amount_keur": 0.0,
        "senior_tenor_years": int(tenor),
        "base_rate": float(base_rate),
        "margin_bps": int(float(margin) * 100),
        "floating_share": 0.2,
        "fixed_share": 0.8,
        "hedge_coverage": 0.8,
        "commitment_fee": 0.0105,
        "arrangement_fee": 0.0,
        "structuring_fee": 0.01,
        "target_dscr": float(target_dscr),
        "lockup_dscr": 1.10,
        "min_llcr": 1.15,
        "dsra_months": int(dsra_months),
    }

    tax = {
        "corporate_rate": float(corporate_tax),
        "loss_carryforward_years": 5,
        "loss_carryforward_cap": 1.0,
        "legal_reserve_cap": 0.10,
        "thin_cap_enabled": False,
        "thin_cap_de_ratio": 4.0,
        "atad_ebitda_limit": 0.0,
        "atad_min_interest_keur": 3000.0,
        "wht_sponsor_dividends": 0.05,
        "wht_sponsor_shl_interest": 0.0,
        "shl_cap_applies": True,
    }

    return {
        "info": info,
        "technical": technical,
        "opex": opex,
        "revenue": revenue,
        "financing": financing,
        "tax": tax,
    }


def _project_inputs_to_flat(inputs_dict: dict) -> dict:
    """Convert nested ProjectInputs dict back to flat session-state dict.

    Used when loading from DB to populate session state with defaults.
    Note: Only the subset of fields that map to DEFAULTS keys are restored.
    """
    import copy
    result = copy.deepcopy(DEFAULTS)

    try:
        info = inputs_dict.get("info", {})
        technical = inputs_dict.get("technical", {})
        revenue = inputs_dict.get("revenue", {})
        financing = inputs_dict.get("financing", {})
        tax = inputs_dict.get("tax", {})

        result['project_name'] = info.get("name", "Solar Project")
        result['project_company'] = info.get("company", "Company")
        result['capacity_ac'] = technical.get("capacity_mw", 48.7)
        result['capacity_dc'] = technical.get("capacity_mw", 48.7) * 1.1
        result['yield_p50'] = technical.get("operating_hours_p50", 1494.0)
        result['yield_p90'] = technical.get("operating_hours_p90_10y", 1410.0)
        result['ppa_base_tariff'] = revenue.get("ppa_base_tariff", 65.0)
        result['ppa_term'] = revenue.get("ppa_term_years", 10)
        result['tariff_escalation'] = revenue.get("ppa_index", 0.02)
        result['gearing_ratio'] = financing.get("gearing_ratio", 0.70)
        result['debt_tenor'] = financing.get("senior_tenor_years", 12)
        result['base_rate'] = financing.get("base_rate", 0.0303)
        result['margin'] = financing.get("margin_bps", 265) / 100
        result['target_dscr'] = financing.get("target_dscr", 1.15)
        result['dsra_months'] = financing.get("dsra_months", 6)
        result['corporate_tax_rate'] = tax.get("corporate_rate", 0.10)
        result['investment_horizon'] = info.get("horizon_years", 30)
    except Exception:
        pass  # If conversion fails, return defaults

    return result


def get_defaults() -> dict[str, Any]:
    """Return the defaults dict (for testing)."""
    return DEFAULTS.copy()


def init_session_state() -> None:
    """Initialize session state with DB-backed persistence.

    On first run (no active project in session state):
    - Initialize the DB (create tables)
    - Seed Oborovo Solar and TUHO Wind default projects
    - Create a default project with one Base Case scenario
    - Store project/scenario IDs in session state
    - Load blank default inputs into session state

    On subsequent runs (project already active):
    - Ensure DB is initialized
    - Load the inputs for the active scenario into session state

    Only sets defaults if keys don't exist yet (preserves existing state).
    """
    import streamlit as st
    from persistence.database import init_db, get_engine
    from persistence.repository import ProjectRepository, ScenarioRepository
    from domain.inputs import ProjectInputs

    # Ensure DB exists
    engine = get_engine()
    init_db(engine)
    Sm = sessionmaker(bind=engine, expire_on_commit=False)

    def _convert_inputs_to_nested(inputs) -> dict:
        """Convert ProjectInputs to nested dict for DB storage."""
        from datetime import date, datetime
        from dataclasses import is_dataclass, asdict

        def _to_serializable(obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            if isinstance(obj, Enum):
                return obj.value
            if is_dataclass(obj):
                return {k: _to_serializable(v) for k, v in asdict(obj).items() if not k.startswith("_")}
            if isinstance(obj, list):
                return [_to_serializable(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _to_serializable(v) for k, v in obj.items() if not k.startswith("_")}
            return obj

        return _to_serializable(inputs)

    def _seed_default_projects(repo: ProjectRepository) -> None:
        """Seed Oborovo Solar and TUHO Wind projects if not already present."""
        existing = [p.name for p in repo.list_projects()]
        defaults = [
            (
                "Oborovo Solar",
                "solar",
                ProjectInputs.create_default_oborovo(),
                "75.26 MW Solar PV | COD 2030 | PPA 14 god | IRR ~10.6%",
            ),
            (
                "TUHO Wind",
                "wind",
                ProjectInputs.create_default_tuho_wind1(),
                "35 MW Wind (5×7MW) | COD 2029 | tenor 14 god | IRR ~9.3%",
            ),
        ]
        for name, tech_type, inputs, desc in defaults:
            if name not in existing:
                proj = repo.create_project(name, technology_type=tech_type, description=desc)
                base = proj.scenarios[0]
                inputs_dict = _convert_inputs_to_nested(inputs)
                repo.save_inputs(base.id, inputs_dict)

    # Seed default projects on first run
    if "projects_seeded" not in st.session_state:
        db = ProjectRepository(Sm())
        _seed_default_projects(db)
        st.session_state.projects_seeded = True

    # Bootstrap: create flat session state keys from DEFAULTS
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Initialize opex_items with blank template if None
    if st.session_state.get('opex_items') is None:
        from core.domain.opex import create_blank_opex_items
        st.session_state.opex_items = _opex_items_to_dict(create_blank_opex_items())

    # Check if we have an active project
    if 'active_project_id' not in st.session_state:
        db = ProjectRepository(Sm())
        sc_repo = ScenarioRepository(Sm())
        projects = db.list_projects()

        if projects:
            # Učitaj prvi seedani projekt (Oborovo) kao default aktivni projekt
            proj = projects[0]
            base = next((s for s in proj.scenarios if s.is_base_case), proj.scenarios[0])

            st.session_state.active_project_id = proj.id
            st.session_state.active_scenario_id = base.id

            stored_inputs = db.load_inputs(base.id)
            st.session_state.inputs = stored_inputs

            if stored_inputs:
                flat = _project_inputs_to_flat(stored_inputs)
                for k, v in flat.items():
                    if k not in st.session_state:
                        st.session_state[k] = v
            st.session_state.result_from_cache = False
        else:
            # Fallback: DB je potpuno prazna — kreiraj novi projekt
            proj = db.create_project("My Solar Project", "solar", "Auto-created project")
            base = proj.scenarios[0]

            defaults = get_defaults()
            inputs_nested = _defaults_to_project_inputs(defaults)
            db.save_inputs(base.id, inputs_nested)

            st.session_state.active_project_id = proj.id
            st.session_state.active_scenario_id = base.id
            st.session_state.inputs = inputs_nested
            st.session_state.result_from_cache = False
    else:
        # Active project exists — load inputs from DB
        db = ProjectRepository(Sm())

        active_scenario_id = st.session_state.get('active_scenario_id')
        if active_scenario_id:
            stored_inputs = db.load_inputs(active_scenario_id)
            if stored_inputs:
                st.session_state.inputs = stored_inputs
                # Also update flat keys for UI
                flat = _project_inputs_to_flat(stored_inputs)
                for key, value in flat.items():
                    if key not in st.session_state:
                        st.session_state[key] = value
            else:
                st.session_state.inputs = None