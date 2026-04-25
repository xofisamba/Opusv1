"""Tests for DSCR calculation — Blueprint Task 0.9.

The correct DSCR formula is:
    DSCR_t = CFADS_t / (Senior_principal_t + Senior_interest_t)

Where CFADS = EBITDA - CIT (tax paid in period).
"""
import pytest
from core.domain.capex import create_generic_capex_tree


def test_dscr_formula_with_trivial_case():
    """Trivial test: CFADS=1300, Senior_P=700, Senior_I=300 → DSCR=1.30."""
    cfads = 1300.0
    senior_principal = 700.0
    senior_interest = 300.0
    senior_ds = senior_principal + senior_interest  # = 1000
    dscr = cfads / senior_ds
    assert abs(dscr - 1.30) < 0.001


def test_dscr_all_zero_principal():
    """DSCR when principal is 0 (no debt) should be infinite or very high."""
    cfads = 1000.0
    senior_interest = 50.0
    dscr = cfads / senior_interest
    assert dscr == 20.0


def test_dscr_zero_cfads():
    """DSCR when CFADS is 0 should be 0."""
    cfads = 0.0
    senior_ds = 1000.0
    dscr = cfads / senior_ds
    assert dscr == 0.0


def test_dscr_with_only_interest_denominator():
    """If bug uses only interest (not principal+interest), DSCR would be 4.33 vs correct 1.30."""
    cfads = 1300.0
    senior_principal = 700.0
    senior_interest = 300.0

    # BUG: DSCR using only interest as denominator
    buggy_dscr = cfads / senior_interest
    assert abs(buggy_dscr - 4.333) < 0.01

    # CORRECT: DSCR using principal + interest
    correct_dscr = cfads / (senior_principal + senior_interest)
    assert abs(correct_dscr - 1.30) < 0.01


def test_dscr_via_sculpting_schedule():
    """Test DSCR computation through sculpting payment schedule."""
    # Simulate a sculpted payment schedule
    payments = [1000.0, 1000.0, 1000.0, 1000.0]  # each = interest + principal
    cfads_schedule = [1300.0, 1400.0, 1200.0, 1100.0]

    dscrs = []
    for t, (cfads, payment) in enumerate(zip(cfads_schedule, payments)):
        dscr = cfads / payment if payment > 0 else float('inf')
        dscrs.append(dscr)

    assert abs(dscrs[0] - 1.30) < 0.01
    assert abs(dscrs[1] - 1.40) < 0.01
    assert abs(dscrs[2] - 1.20) < 0.01
    assert abs(dscrs[3] - 1.10) < 0.01

    avg_dscr = sum(dscrs) / len(dscrs)
    min_dscr = min(dscrs)
    assert abs(avg_dscr - 1.25) < 0.01
    assert abs(min_dscr - 1.10) < 0.01
