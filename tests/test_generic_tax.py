"""Tests for core/tax/generic_tax.py."""
import pytest
from core.tax.generic_tax import (
    GenericTaxConfig,
    CustomTaxOverride,
    apply_custom_overrides,
)


def test_rate_passthrough():
    """Test that CIT rate 0.12 passes through correctly."""
    cfg = GenericTaxConfig(
        cit_rate=0.12,
        cit_payment_period="annual_h2",
        loss_carryforward_enabled=True,
        loss_carryforward_years=7,
        loss_carryforward_cap_pct=1.0,
        interest_cap_enabled=False,
        interest_cap_ebitda_ratio=0.30,
        interest_cap_min_keur=3000.0,
        wht_dividends=0.05,
        wht_interest_shl=0.0,
        wht_interest_senior=0.0,
        vat_rate=0.25,
        vat_recoverable_on_capex=True,
        custom_overrides=(),
    )
    assert cfg.cit_rate == 0.12
    assert cfg.loss_carryforward_years == 7
    assert cfg.interest_cap_enabled is False


def test_custom_tax_override_add():
    """Test that CustomTaxOverride 'add' 500 kEUR annually accumulates correctly."""
    override = CustomTaxOverride(
        name="Annual levy",
        apply_to="tax",
        operation="add",
        value=500.0,
        period_start=1,
        period_end=-1,  # perpetuity
    )
    result = {"ebitda": 10000.0, "ebt": 5000.0, "tax": 500.0, "net_income": 4500.0}

    # Year 1: add 500 to tax
    updated = apply_custom_overrides(5000.0, result, (override,), period=1)
    assert updated["tax"] == 1000.0

    # Year 5: still adding 500
    updated5 = apply_custom_overrides(5000.0, result, (override,), period=5)
    assert updated5["tax"] == 1000.0


def test_custom_override_multiply():
    """Test multiply override on EBITDA."""
    override = CustomTaxOverride(
        name="Growth adjustment",
        apply_to="ebitda",
        operation="multiply",
        value=1.05,  # +5%
        period_start=1,
        period_end=-1,
    )
    result = {"ebitda": 10000.0, "ebt": 5000.0, "tax": 500.0, "net_income": 4500.0}
    updated = apply_custom_overrides(5000.0, result, (override,), period=1)
    assert updated["ebitda"] == 10500.0


def test_override_not_active_before_start():
    """Test that override is not applied before period_start."""
    override = CustomTaxOverride(
        name="Late penalty",
        apply_to="tax",
        operation="add",
        value=1000.0,
        period_start=3,
        period_end=5,
    )
    result = {"ebitda": 10000.0, "ebt": 5000.0, "tax": 500.0, "net_income": 4500.0}
    updated = apply_custom_overrides(5000.0, result, (override,), period=2)
    assert updated["tax"] == 500.0  # Not applied in year 2


def test_override_not_active_after_end():
    """Test that override is not applied after period_end."""
    override = CustomTaxOverride(
        name="Temporary levy",
        apply_to="tax",
        operation="add",
        value=200.0,
        period_start=1,
        period_end=3,
    )
    result = {"ebitda": 10000.0, "ebt": 5000.0, "tax": 500.0, "net_income": 4500.0}
    updated = apply_custom_overrides(5000.0, result, (override,), period=4)
    assert updated["tax"] == 500.0  # Not applied in year 4


def test_interest_cap_disabled_no_effect():
    """Test that interest_cap_enabled=False does not apply cap."""
    cfg = GenericTaxConfig(
        cit_rate=0.10,
        cit_payment_period="annual_h2",
        loss_carryforward_enabled=False,
        loss_carryforward_years=0,
        loss_carryforward_cap_pct=1.0,
        interest_cap_enabled=False,  # Disabled!
        interest_cap_ebitda_ratio=0.30,
        interest_cap_min_keur=3000.0,
        wht_dividends=0.0,
        wht_interest_shl=0.0,
        wht_interest_senior=0.0,
        vat_rate=0.25,
        vat_recoverable_on_capex=False,
        custom_overrides=(),
    )
    assert cfg.interest_cap_enabled is False
    # No special deductibility limits applied


def test_custom_override_subtract():
    """Test subtract operation on net_income."""
    override = CustomTaxOverride(
        name="Dividend withholding",
        apply_to="net_income",
        operation="subtract",
        value=100.0,
        period_start=1,
        period_end=-1,
    )
    result = {"ebitda": 10000.0, "ebt": 5000.0, "tax": 500.0, "net_income": 4500.0}
    updated = apply_custom_overrides(5000.0, result, (override,), period=1)
    assert updated["net_income"] == 4400.0
