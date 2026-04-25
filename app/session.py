"""Session state initialization for Oborovo financial model.

Provides init_session_state() and defaults dict.
"""
from datetime import date
from typing import Any


# Default values matching original model
DEFAULTS = {
    # Project
    'project_name': 'Solar Project',
    'project_company': 'Company',
    'technology': 'Solar',

    # Capacity
    'capacity_dc': 53.63,
    'capacity_ac': 48.7,

    # Wind
    'wind_capacity': 60.0,
    'turbine_rating': 6.0,
    'num_turbines': 10,
    'wind_speed': 7.5,
    'hub_height': 100,
    'wake_effects': 0.0,
    'curtailment': 0.0,

    # Revenue
    'ppa_base_tariff': 65.0,
    'tariff_escalation': 0.02,
    'ppa_term': 10,
    'merchant_price': 60.0,
    'merchant_tail_enabled': False,

    # Yield
    'yield_p50': 1494.0,
    'yield_p90': 1410.0,
    'yield_p99': 1350.0,
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
    'corporate_tax_rate': 0.10,
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


def init_session_state() -> None:
    """Initialize session state with default values.

    Only sets defaults if keys don't exist yet (preserves existing state).
    """
    import streamlit as st

    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Task 0.6: Initialize opex_items with blank template if None
    if st.session_state.get('opex_items') is None:
        from core.domain.opex import create_blank_opex_items
        st.session_state.opex_items = _opex_items_to_dict(create_blank_opex_items())


def get_defaults() -> dict[str, Any]:
    """Return the defaults dict (for testing)."""
    return DEFAULTS.copy()