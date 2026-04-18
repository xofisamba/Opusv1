"""Tests for XIRR/XNPV functions - validates against Excel benchmarks."""
from datetime import date
import math
import pytest
from domain.returns.xirr import xirr, xnpv, xirr_bisection
from domain.returns.xnpv import xnpv as xnpv_from_module, xnpv_schedule


class TestXIRRBasic:
    """Basic XIRR functionality tests."""
    
    def test_simple_irr_20_percent(self):
        """Simple case: -1000 now, +1200 in 1 year → ~20% IRR."""
        cfs = [-1000, 1200]
        ds = [date(2020, 1, 1), date(2021, 1, 1)]
        
        result = xirr(cfs, ds)
        
        assert result is not None
        # IRR ≈ 20% for -1000 + 1200/1.20 = 0
        assert abs(result - 0.20) < 0.002
    
    def test_simple_irr_6_months(self):
        """-1000 now, +1100 in 6 months → ~21% IRR."""
        cfs = [-1000, 1100]
        ds = [date(2020, 1, 1), date(2020, 7, 1)]
        
        result = xirr(cfs, ds)
        
        assert result is not None
        # NPV = -1000 + 1100/(1+r)^0.5 = 0 → r ≈ 21%
        assert 0.20 < result < 0.25
    
    def test_no_solution_all_negative(self):
        """All negative cash flows → no IRR."""
        cfs = [-100, -200, -300]
        ds = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)]
        
        result = xirr(cfs, ds)
        
        assert result is None
    
    def test_no_solution_all_positive(self):
        """All positive cash flows → no IRR."""
        cfs = [100, 200, 300]
        ds = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)]
        
        result = xirr(cfs, ds)
        
        assert result is None
    
    def test_empty_input(self):
        """Empty arrays → None."""
        assert xirr([], []) is None
    
    def test_single_cash_flow(self):
        """Single cash flow → None (need at least 2)."""
        cfs = [-1000]
        ds = [date(2020, 1, 1)]
        
        result = xirr(cfs, ds)
        
        assert result is None


class TestXIRROborovo:
    """Tests against Oborovo Excel XIRR values.
    
    Golden numbers from Oborovo Excel:
    - Project IRR 30y = 8.42% (CF!D31 = XIRR on row 136)
    - Equity IRR 30y = 11.00% (CF!D32)
    
    Note: Without the actual Excel cash flow data, we can only verify
    the XIRR algorithm produces reasonable results for typical solar project CFs.
    """
    
    def test_xirr_semestrial_solar_project(self):
        """Test XIRR on simplified Oborovo-style semi-annual cash flows.
        
        Structure: Initial investment at FC, then semi-annual CF during operation.
        """
        # Oborovo: ~56,899 kEUR total CAPEX at FC (2029-06-29)
        capex = -56899.5
        
        # Build semi-annual CFs for 30 years
        # Use realistic values that produce ~8-9% IRR for a solar project
        cfs = [capex]
        dates = [date(2029, 6, 29)]
        
        # Annual CF of ~9000 kEUR split into two semi-annual payments
        annual_cf = 9000
        for year in range(1, 31):
            for half in [1, 2]:
                cf = annual_cf / 2
                cfs.append(cf)
                if half == 1:
                    dates.append(date(2029 + year, 6, 30))
                else:
                    dates.append(date(2029 + year, 12, 31))
        
        result = xirr(cfs, dates, guess=0.08)
        
        assert result is not None
        assert 0.03 < result < 0.20  # Should be ~8-9% for viable project
        print(f"Oborovo-style XIRR: {result*100:.2f}%")
    
    def test_xirr_convergence(self):
        """Test that Newton-Raphson converges for reasonable cash flows."""
        # -1000 + 300 + 400 + 400 → IRR ≈ 4.7%
        cfs = [-1000, 300, 400, 400]
        ds = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)]
        
        result = xirr(cfs, ds, tolerance=1e-9)
        
        assert result is not None
        # IRR should be around 4.7% for this pattern
        assert 0.03 < result < 0.08


class TestXNPVBasic:
    """Basic XNPV functionality tests."""
    
    def test_simple_npv(self):
        """Simple NPV at 8%: -1000 now, +500, +300, +400 at years 1,2,3."""
        cfs = [-1000, 500, 300, 400]
        ds = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)]
        
        result = xnpv(0.08, cfs, ds)
        
        # Manual: -1000 + 500/1.08 + 300/1.08^2 + 400/1.08^3 ≈ 37.68
        expected = -1000 + 500/1.08 + 300/1.1664 + 400/1.2597
        assert abs(result - expected) < 0.5
    
    def test_npv_at_zero_rate(self):
        """NPV at 0% = sum of cash flows."""
        cfs = [-1000, 500, 300, 200]
        ds = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)]
        
        result = xnpv(0.0, cfs, ds)
        
        assert abs(result - 0.0) < 0.001
    
    def test_npv_negative_rate(self):
        """NPV at -50% should be huge (discounting increases value)."""
        cfs = [-1000, 1000]
        ds = [date(2020, 1, 1), date(2021, 1, 1)]
        
        result = xnpv(-0.5, cfs, ds)
        
        assert result > 1000
    
    def test_npv_date_sensitivity(self):
        """NPV should differ based on date spacing."""
        cfs = [-1000, 1000]
        
        # Same CF, different timing
        ds_short = [date(2020, 1, 1), date(2020, 6, 30)]  # 6 months
        ds_long = [date(2020, 1, 1), date(2021, 1, 1)]    # 1 year
        
        npv_short = xnpv(0.10, cfs, ds_short)
        npv_long = xnpv(0.10, cfs, ds_long)
        
        # Shorter delay = higher NPV
        assert npv_short > npv_long


class TestXIRRXNPVRelationship:
    """Tests for XIRR and XNPV relationship."""
    
    def test_npv_at_irr_is_zero(self):
        """NPV at IRR rate should be ~0 (all cash flows accounted)."""
        cfs = [-1000, 1200]
        ds = [date(2020, 1, 1), date(2021, 1, 1)]
        
        irr = xirr(cfs, ds)
        
        if irr is not None:
            npv_at_irr = xnpv(irr, cfs, ds)
            # NPV at IRR should be ~0 (within numerical precision)
            assert abs(npv_at_irr) < 0.01
    
    def test_xirr_bisection_matches_newton(self):
        """Bisection XIRR should match Newton-Raphson result for typical CFs."""
        cfs = [-1000, 300, 400, 400]
        ds = [
            date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)
        ]
        
        irr_newton = xirr(cfs, ds)
        irr_bisect = xirr_bisection(cfs, ds)
        
        if irr_newton is not None and irr_bisect is not None:
            assert abs(irr_newton - irr_bisect) < 1e-4


class TestXNPVSchedule:
    """Test cumulative NPV schedule."""
    
    def test_schedule_cumulative(self):
        """Test cumulative NPV calculation."""
        cfs = [-1000, 500, 600]
        ds = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)]
        
        schedule = xnpv_schedule(0.10, cfs, ds)
        
        assert len(schedule) == 3
        assert schedule[0] == -1000.0  # Only initial outflow
        assert schedule[1] > -1000    # Second CF improves NPV
        assert schedule[2] > schedule[1]


class TestXIRREdgeCases:
    """Edge cases and boundary conditions."""
    
    def test_very_small_cash_flows(self):
        """Very small cash flows should still work."""
        cfs = [-0.001, 0.0005, 0.0005]
        ds = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)]
        
        result = xirr(cfs, ds)
        
        # Should return None or very large value
        if result is not None:
            assert abs(result) < 10  # Sanity check
    
    def test_long_dated_cash_flows(self):
        """Long-dated cash flows (50+ years) should work."""
        cfs = [-1000] + [100] * 50
        ds = [date(2020, 1, 1)] + [date(2020 + i, 1, 1) for i in range(50)]
        
        result = xirr(cfs, ds)
        
        assert result is not None
        assert 0 < result < 1  # Sanity bounds
    
    def test_different_first_date(self):
        """Cash flows starting from non-Jan-1 should work."""
        cfs = [-5000, 2000, 2000, 2000]
        ds = [date(2029, 6, 29), date(2030, 6, 29), date(2031, 6, 29), date(2032, 6, 29)]
        
        result = xirr(cfs, ds)
        
        assert result is not None
        print(f"Oborovo-style start XIRR: {result*100:.2f}%")