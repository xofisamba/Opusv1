"""Tests for financing module."""
import pytest
from domain.financing.schedule import (
    senior_debt_amount,
    standard_amortization,
    sculpted_amortization,
    annuity_payment,
    balance_after_n_periods,
)
from domain.financing.sculpting_iterative import (
    dscr_at_period,
    average_dscr,
    min_dscr,
)
from domain.financing.covenants import (
    dscr,
    llcr,
    plcr,
    lockup_check,
)


class TestSeniorDebtAmount:
    """Test senior debt calculation."""
    
    def test_simple_gearing(self):
        """Debt = capex × gearing."""
        debt = senior_debt_amount(50000, 0.75)
        assert abs(debt - 37500) < 0.01
    
    def test_oborovo_gearing(self):
        """Oborovo: 56,899 × 75.24% = ~42,852."""
        debt = senior_debt_amount(56899.5, 0.7524)
        assert abs(debt - 42852) < 50


class TestStandardAmortization:
    """Test standard amortization schedule."""
    
    def test_annuity_payment(self):
        """Annuity payment calculation."""
        payment = annuity_payment(10000, 0.05, 10)
        
        # PV = PMT × [1 - (1+r)^-n] / r
        # 10000 = PMT × [1 - 1.05^-10] / 0.05
        # PMT ≈ 1295.05
        assert 1290 < payment < 1300
    
    def test_standard_amortization_balance(self):
        """Standard amortization should fully repay debt."""
        schedule = standard_amortization(10000, 0.05, 10)
        
        # Sum of principal payments should = initial debt
        total_principal = sum(s.principal_keur for s in schedule)
        assert abs(total_principal - 10000) < 0.1
        
        # Last period closing balance should be ~0
        assert schedule[-1].closing_balance < 0.01
    
    def test_interest_decreases_over_time(self):
        """Interest should decrease as balance reduces."""
        schedule = standard_amortization(10000, 0.05, 10)
        
        interest_values = [s.interest_keur for s in schedule]
        
        # First period interest > last period interest
        assert interest_values[0] > interest_values[-1]


class TestSculptedAmortization:
    """Test sculpted amortization."""
    
    def test_sculpted_debt_dscr(self):
        """Sculpted debt should maintain target DSCR."""
        # Simple test: constant EBITDA
        ebitda = [5000] * 14  # 14 semi-annual periods
        rate = 0.02825  # ~5.65% semi-annual
        
        schedule, dscr_list = sculpted_amortization(
            debt_keur=30000,
            ebitda_schedule=ebitda,
            rate_per_period=rate,
            tenor_periods=14,
            target_dscr=1.15,
        )
        
        # First 7 periods should maintain ~1.15 (until debt nearly repaid)
        # Later periods may have different DSCR as balance reduces
        active_dsrs = [d for d in dscr_list if d > 0]
        assert len(active_dsrs) >= 7
        for d in active_dsrs[:7]:
            assert abs(d - 1.15) < 0.3


class TestDSCRCalculation:
    """Test DSCR functions."""
    
    def test_dscr_basic(self):
        """DSCR = EBITDA / DS."""
        result = dscr(1150, 1000)
        assert abs(result - 1.15) < 0.001
    
    def test_dscr_zero_ds(self):
        """Zero debt service = infinite DSCR."""
        result = dscr(1000, 0)
        assert result == float('inf')
    
    def test_dscr_at_period(self):
        """Test single period DSCR."""
        result = dscr_at_period(1150, 1000)
        assert abs(result - 1.15) < 0.001
    
    def test_average_dscr(self):
        """Average DSCR over schedule."""
        ebitda = [1150, 1200, 1100]
        ds = [1000, 1000, 1000]
        
        avg = average_dscr(ebitda, ds)
        expected = (1150/1000 + 1200/1000 + 1100/1000) / 3
        assert abs(avg - expected) < 0.001
    
    def test_min_dscr(self):
        """Min DSCR over schedule."""
        ebitda = [1150, 1100, 1200]
        ds = [1000, 1000, 1000]
        
        min_val = min_dscr(ebitda, ds)
        assert abs(min_val - 1.10) < 0.001


class TestCovenants:
    """Test covenant calculations."""
    
    def test_llcr(self):
        """LLCR = PV(FCF) / Debt."""
        fcf = [5000] * 10
        llcr_val = llcr(fcf, 30000, 0.05, 10)
        
        # PV of 5000 × 10 period annuity at 5%
        pv_fcf = sum(5000 / (1.05 ** t) for t in range(1, 11))
        expected_llcr = pv_fcf / 30000
        
        assert abs(llcr_val - expected_llcr) < 0.01
    
    def test_lockup_check_pass(self):
        """DSCR above lockup = no lockup."""
        result = lockup_check(dscr=1.15, min_dscr_lockup=1.10)
        assert result is False
    
    def test_lockup_check_fail(self):
        """DSCR below lockup = lockup."""
        result = lockup_check(dscr=1.05, min_dscr_lockup=1.10)
        assert result is True


class TestAnnuityFormulas:
    """Test annuity payment and balance formulas."""
    
    def test_balance_after_periods(self):
        """Balance after n periods of annuity."""
        initial = 10000
        rate = 0.05
        payment = annuity_payment(initial, rate, 10)
        
        balance_after_5 = balance_after_n_periods(initial, rate, payment, 5)
        
        # Balance after 5 periods should be > 0 but < initial
        assert 0 < balance_after_5 < 10000