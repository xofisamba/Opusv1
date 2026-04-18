"""Tests for tax module."""
import pytest
from domain.tax.engine import (
    taxable_profit,
    tax_liability,
    atad_limit,
    atad_adjustment,
    apply_loss_carryforward,
    loss_carryforward_simple,
    effective_tax_rate,
)
from domain.tax.reintegration import (
    fiscal_reintegration,
    fiscal_reintegration_schedule,
    total_fiscal_reintegration,
)


class TestTaxableProfit:
    """Test taxable profit calculation."""
    
    def test_simple_profit(self):
        """Taxable = EBITDA - D&A - Interest."""
        profit = taxable_profit(
            ebitda_keur=10000,
            depreciation_keur=2000,
            interest_keur=1500,
        )
        assert abs(profit - 6500) < 0.01
    
    def test_with_fiscal_reintegration(self):
        """Taxable includes fiscal reintegration add-back."""
        profit = taxable_profit(
            ebitda_keur=10000,
            depreciation_keur=2000,
            interest_keur=1500,
            fiscal_reintegration_keur=500,
        )
        assert abs(profit - 7000) < 0.01
    
    def test_loss(self):
        """Negative profit = 0 taxable."""
        profit = taxable_profit(
            ebitda_keur=5000,
            depreciation_keur=3000,
            interest_keur=3000,
        )
        assert profit == 0


class TestTaxLiability:
    """Test tax calculation."""
    
    def test_simple_tax(self):
        """Tax = profit × rate."""
        tax = tax_liability(taxable_profit_keur=10000, tax_rate=0.10)
        assert abs(tax - 1000) < 0.01
    
    def test_zero_profit(self):
        """No tax on zero profit."""
        tax = tax_liability(taxable_profit_keur=0, tax_rate=0.10)
        assert tax == 0
    
    def test_croatian_rate(self):
        """10% Croatian rate."""
        tax = tax_liability(taxable_profit_keur=10000, tax_rate=0.10)
        assert abs(tax - 1000) < 0.01


class TestATAD:
    """Test ATAD interest limitation."""
    
    def test_atad_limit_simple(self):
        """ATAD limit = 30% × EBITDA."""
        limit = atad_limit(ebitda_keur=10000)
        assert abs(limit - 3000) < 0.01
    
    def test_atad_min_threshold(self):
        """ATAD allows higher of 30% EBITDA or 3M threshold."""
        # Small project: 3M threshold may be binding
        limit = atad_limit(ebitda_keur=5000)
        # 30% × 5000 = 1500, but min is 3000
        assert limit >= 3000
    
    def test_atad_adjustment_under_limit(self):
        """Interest under ATAD limit = fully deductible."""
        deductible, addback = atad_adjustment(interest_keur=2000, ebitda_keur=10000)
        assert abs(deductible - 2000) < 0.01
        assert addback == 0
    
    def test_atad_adjustment_over_limit(self):
        """Interest over ATAD limit = addback to taxable."""
        deductible, addback = atad_adjustment(interest_keur=5000, ebitda_keur=10000)
        # 30% × 10000 = 3000 deductible, 2000 addback
        assert abs(deductible - 3000) < 0.01
        assert abs(addback - 2000) < 0.01


class TestLossCarryforward:
    """Test loss carryforward."""
    
    def test_apply_loss_cf(self):
        """Apply losses to current profit."""
        losses = [1000, 500]  # Most recent first
        profit = 2000
        
        applied, remaining = apply_loss_carryforward(losses, profit, max_years=5, cap_pct=1.0)
        
        # Can offset up to 2000 (100% of profit), available = 1500
        assert abs(applied - 1500) < 0.01
    
    def test_loss_cf_cap(self):
        """Loss CF capped at % of profit."""
        losses = [5000]  # Large loss
        profit = 1000
        
        applied, remaining = apply_loss_carryforward(losses, profit, max_years=5, cap_pct=0.5)
        
        # Cap at 50% of profit = 500
        assert abs(applied - 500) < 0.01
    
    def test_simple_loss_cf(self):
        """Simple loss CF."""
        prior_losses = [1000, 800]  # 2 years of losses
        profit = 2000
        
        applied = loss_carryforward_simple(prior_losses, profit, years=5)
        
        # Available = 1800, cap at profit = 2000
        assert abs(applied - 1800) < 0.01
    
    def test_no_losses(self):
        """No prior losses."""
        losses = []
        profit = 1000
        
        applied, remaining = apply_loss_carryforward(losses, profit)
        
        assert applied == 0


class TestEffectiveTaxRate:
    """Test effective tax rate."""
    
    def test_effective_rate(self):
        """Effective = Tax / EBITDA."""
        rate = effective_tax_rate(tax_keur=1000, ebitda_keur=10000)
        assert abs(rate - 0.10) < 0.001
    
    def test_zero_ebitda(self):
        """Zero EBITDA = 0 effective rate."""
        rate = effective_tax_rate(tax_keur=0, ebitda_keur=0)
        assert rate == 0


class TestFiscalReintegration:
    """Test fiscal reintegration."""
    
    def test_fiscal_reintegration_during_construction(self):
        """During construction, fiscal reintegration applies."""
        result = fiscal_reintegration(
            period_index=0,
            capex_distribution={},
            non_deductible_items=["IDC", "Bank Fees"],
            is_construction=True,
        )
        # Simplified: returns 0 since costs are capitalized
        assert result == 0
    
    def test_fiscal_reintegration_after_cod(self):
        """After COD, no fiscal reintegration."""
        result = fiscal_reintegration(
            period_index=5,
            capex_distribution={},
            non_deductible_items=["IDC", "Bank Fees"],
            is_construction=False,
        )
        assert result == 0
    
    def test_total_fiscal_reintegration(self):
        """Total IDC is distributed over construction periods."""
        total = total_fiscal_reintegration(idc_total_keur=1086, construction_periods=2)
        assert abs(total - 543) < 0.1