"""Generic Tax Configuration — Blueprint §2.4.

This module provides jurisdiction-agnostic tax configuration.
All classes are frozen/immutable.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class CustomTaxOverride:
    """Custom tax override applied to a specific calculation layer.

    Example: Add 500 kEUR to tax for years 3-5:
        CustomTaxOverride(
            name="Additional levy",
            apply_to="tax",
            operation="add",
            value=500.0,
            period_start=3,
            period_end=5,
        )
    """
    name: str
    apply_to: str  # "ebitda" | "ebt" | "tax" | "net_income"
    operation: str  # "multiply" | "add" | "subtract"
    value: float  # kEUR amount or multiplier
    period_start: int  # 1-indexed year
    period_end: int  # -1 = perpetuity

    def is_active(self, period: int) -> bool:
        if self.period_end == -1:
            return period >= self.period_start
        return self.period_start <= period <= self.period_end


@dataclass(frozen=True)
class GenericTaxConfig:
    """Generic tax configuration — jurisdiction agnostic.

    Maps to TaxParams for backward compat via TaxParams.from_generic_config().
    """
    cit_rate: float  # Corporate income tax rate (e.g., 0.10 = 10%)
    cit_payment_period: str  # "annual_h2" | "quarterly" | "monthly"
    loss_carryforward_enabled: bool
    loss_carryforward_years: int  # 0 = unlimited
    loss_carryforward_cap_pct: float  # Cap as % of profit (1.0 = 100%)
    interest_cap_enabled: bool  # ATAD EBITDA interest cap
    interest_cap_ebitda_ratio: float  # e.g., 0.30 = 30% EBITDA limit
    interest_cap_min_keur: float  # Minimum interest threshold (ATAD)
    wht_dividends: float  # WHT on dividends
    wht_interest_shl: float  # WHT on SHL interest
    wht_interest_senior: float  # WHT on senior debt interest
    vat_rate: float  # VAT rate
    vat_recoverable_on_capex: bool
    custom_overrides: tuple[CustomTaxOverride, ...] = ()


def apply_custom_overrides(
    taxable_income: float,
    result: dict,
    overrides: tuple[CustomTaxOverride, ...],
    period: int,
) -> dict:
    """Apply custom tax overrides to a calculation result.

    Args:
        taxable_income: The taxable income (EBT) for the period
        result: Dict with keys: ebitda, ebt, tax, net_income
        overrides: Tuple of CustomTaxOverride to apply
        period: Current period number (1-indexed)

    Returns:
        Updated result dict with overrides applied
    """
    working = dict(result)

    for override in overrides:
        if not override.is_active(period):
            continue

        if override.apply_to == "ebitda":
            if override.operation == "add":
                working["ebitda"] = working.get("ebitda", 0) + override.value
            elif override.operation == "subtract":
                working["ebitda"] = working.get("ebitda", 0) - override.value
            elif override.operation == "multiply":
                working["ebitda"] = working.get("ebitda", 0) * override.value

        elif override.apply_to == "ebt":
            if override.operation == "add":
                working["ebt"] = working.get("ebt", 0) + override.value
            elif override.operation == "subtract":
                working["ebt"] = working.get("ebt", 0) - override.value
            elif override.operation == "multiply":
                working["ebt"] = working.get("ebt", 0) * override.value

        elif override.apply_to == "tax":
            if override.operation == "add":
                working["tax"] = working.get("tax", 0) + override.value
            elif override.operation == "subtract":
                working["tax"] = working.get("tax", 0) - override.value
            elif override.operation == "multiply":
                working["tax"] = working.get("tax", 0) * override.value

        elif override.apply_to == "net_income":
            if override.operation == "add":
                working["net_income"] = working.get("net_income", 0) + override.value
            elif override.operation == "subtract":
                working["net_income"] = working.get("net_income", 0) - override.value
            elif override.operation == "multiply":
                working["net_income"] = working.get("net_income", 0) * override.value

    # Recompute net_income if relevant layers changed
    if override.apply_to in ("ebt", "tax"):
        working["net_income"] = working.get("ebt", 0) - working.get("tax", 0)

    return working
