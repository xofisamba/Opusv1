"""CAPEX module - spending profiles and IDC calculation."""
from domain.capex.spending_profile import (
    total_hard_capex,
    spending_profile_for_item,
    generate_spending_schedule,
)
from domain.capex.idc import calculate_idc_fixed_point, calculate_idc_detailed

__all__ = [
    "total_hard_capex",
    "spending_profile_for_item",
    "generate_spending_schedule",
    "calculate_idc_fixed_point",
    "calculate_idc_detailed",
]