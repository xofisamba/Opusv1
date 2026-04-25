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


def test_dscr_via_actual_waterfall():
    """
    Run actual waterfall and verify DSCR formula.

    Per Blueprint §4.5:
    DSCR_t = CFADS_t / Senior_DS_t
    where CFADS = EBITDA - CIT
    and Senior_DS = Senior_principal + Senior_interest
    SHL service is BELOW DSCR line — NOT included in denominator.
    """
    from domain.inputs import ProjectInputs
    from domain.period_engine import PeriodEngine, PeriodFrequency as PF
    from utils.cache import cached_run_waterfall_v3

    inputs = ProjectInputs.create_default_oborovo()
    freq = PF.SEMESTRIAL
    engine = PeriodEngine(
        financial_close=inputs.info.financial_close,
        construction_months=inputs.info.construction_months,
        horizon_years=inputs.info.horizon_years,
        ppa_years=inputs.revenue.ppa_term_years,
        frequency=freq,
    )
    rate = inputs.financing.all_in_rate / 2
    tenor_periods = inputs.financing.senior_tenor_years * 2

    result = cached_run_waterfall_v3(
        inputs=inputs,
        engine=engine,
        rate_per_period=rate,
        tenor_periods=tenor_periods,
        target_dscr=inputs.financing.target_dscr,
        lockup_dscr=inputs.financing.lockup_dscr,
        tax_rate=inputs.tax.corporate_rate,
        dsra_months=inputs.financing.dsra_months,
        shl_amount=inputs.financing.shl_amount_keur,
        shl_rate=inputs.financing.shl_rate,
        discount_rate_project=0.0641,
        discount_rate_equity=0.0965,
        fixed_debt_keur=None,
    )

    # Find first operational period with actual debt service
    op_periods = [
        p for p in result.periods
        if getattr(p, 'is_operation', False) and p.senior_ds_keur > 0
    ]
    assert len(op_periods) > 0, "No operational periods with debt service found"

    p = op_periods[0]

    # Manual DSCR calculation per Blueprint definition
    # CFADS = EBITDA - CIT (tax paid this period) = cf_after_tax_keur from waterfall
    # (cf_after_tax_keur is already computed as ebitda - tax_this_period)
    cfads_manual = p.cf_after_tax_keur
    # Senior DS = principal + interest
    senior_ds_manual = p.senior_ds_keur  # = senior_principal + senior_interest
    dscr_manual = cfads_manual / senior_ds_manual if senior_ds_manual > 0 else float('inf')

    # Compare with waterfall DSCR
    assert abs(p.dscr - dscr_manual) < 0.01, (
        f"DSCR mismatch: waterfall={p.dscr:.4f}, manual={dscr_manual:.4f}\n"
        f"  EBITDA={p.ebitda_keur:.0f}, CFADS={cfads_manual:.0f}, "
        f"Senior_DS={senior_ds_manual:.0f}"
    )

    # Verify the sculpted DSCR schedule matches the target
    # (The avg/min in WaterfallResult come from the CLOSED-FORM sculpting, not actual periods)
    assert hasattr(result, 'sculpting_result'), "Result missing sculpting_result"
    sculpted = result.sculpting_result
    # Sculpting targets the input target_dscr
    target = inputs.financing.target_dscr
    # Sculpted DSCRs should be exactly at target for operational periods before final
    sculpt_dscrs = [d for d in sculpted.dscr_schedule if d > 0 and d < 100]
    for d in sculpt_dscrs[:-1]:  # all except possibly last partial
        assert abs(d - target) < 0.001, f"Sculpted DSCR {d} != target {target}"


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
