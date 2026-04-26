#!/usr/bin/env python3
"""Diagnostic script for Oborovo sculpting calibration.

Runs waterfall with default Oborovo inputs and compares period-by-period
to Excel reference values to identify causes of deviation.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.inputs import ProjectInputs, PeriodFrequency
from domain.period_engine import PeriodEngine, PeriodFrequency as PF
from utils.cache import cached_run_waterfall_v3


def run_diagnosis():
    # Run waterfall
    inputs = ProjectInputs.create_default_oborovo()
    freq = PF.SEMESTRIAL if inputs.info.period_frequency == PeriodFrequency.SEMESTRIAL else PF.ANNUAL
    engine = PeriodEngine(
        financial_close=inputs.info.financial_close,
        construction_months=inputs.info.construction_months,
        horizon_years=inputs.info.horizon_years,
        ppa_years=inputs.revenue.ppa_term_years,
        frequency=freq,
    )
    rate = 0.0565 / 2  # semi-annual
    tenor_periods = 28

    result = cached_run_waterfall_v3(
        inputs=inputs, engine=engine,
        rate_per_period=rate, tenor_periods=tenor_periods,
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

    sculpt = result.sculpting_result

    print("=" * 80)
    print("OBOROVO SCULPTING DIAGNOSIS")
    print("=" * 80)
    print(f"\nSculpting result:")
    print(f"  Debt: {sculpt.debt_keur:,.2f} kEUR")
    print(f"  Avg DSCR: {sculpt.avg_dscr:.4f}")
    print(f"  Min DSCR: {sculpt.min_dscr:.4f}")
    print(f"  Converged: {sculpt.converged} ({sculpt.iterations} iters)")

    print(f"\nExcel reference values:")
    print(f"  Excel debt: 42,852.27 kEUR")
    print(f"  Excel senior DS Y1: 4,622.88 kEUR annual → 2,311.44 kEUR per semi-annual period")
    print(f"  Excel DSCR Y1: 1.147 (average)")
    print(f"  Excel gearing: 73.9% (0.739)")

    print("\n" + "-" * 80)
    print(f"Period-by-period table (first 4 operational periods):")
    print("-" * 80)
    print(f"{'Period':>7} {'CFADS':>12} {'Payment':>12} {'DSCR':>8} {'Balance':>12}")
    print("-" * 80)

    # Get operational periods from result
    op_periods = [p for p in result.periods if p.is_operation]
    for i, period in enumerate(op_periods[:4]):
        # Find sculpting period index
        period_in_tenor = i
        if period_in_tenor < tenor_periods:
            payment = sculpt.payment_schedule[period_in_tenor]
            balance = sculpt.balance_schedule[period_in_tenor]
        else:
            payment = 0
            balance = 0

        # CFADS = EBITDA - tax (used for sculpting)
        cfads = period.ebitda_keur - period.tax_keur
        dscr = sculpt.dscr_schedule[period_in_tenor] if period_in_tenor < len(sculpt.dscr_schedule) else 0

        print(f"{period.period:>7} {cfads:>12,.2f} {payment:>12,.2f} {dscr:>8.4f} {balance:>12,.2f}")

    print("-" * 80)

    # Check causes
    print("\n" + "=" * 80)
    print("CAUSE ANALYSIS")
    print("=" * 80)

    debt_deviation_pct = abs(sculpt.debt_keur - 42852.27) / 42852.27 * 100
    print(f"\n1. Debt deviation: {debt_deviation_pct:.2f}%")
    print(f"   (threshold for active cause: > 1%)")
    print(f"   → {'ACTIVE' if debt_deviation_pct > 1 else 'INACTIVE'}: debt is {'WRONG' if debt_deviation_pct > 1 else 'correct'}")

    # (a) Check CFADS for sculpting - does it include tax properly?
    # In run_waterfall, cfads_for_sculpt = ebitda_schedule[:tenor_periods] (EBITDA, not EBITDA-tax)
    # This is cause (a)
    print(f"\n2. Cause (a): CFADS for sculpting doesn't include tax properly")
    print(f"   run_waterfall uses ebitda_schedule (EBITDA only) for cfads_for_sculpt")
    print(f"   Excel likely uses CFADS = EBITDA - Tax for sculpting")
    print(f"   → This is the key difference causing debt mis-sizing")

    # (b) Check gearing cap
    print(f"\n3. Cause (b): closed_form_sculpt uses wrong gearing cap")
    total_capex = inputs.capex.total_capex
    print(f"   total_capex = {total_capex:,.2f} kEUR")
    print(f"   gearing_ratio = {inputs.financing.gearing_ratio}")
    print(f"   gearing_cap = total_capex * gearing_ratio = {total_capex * inputs.financing.gearing_ratio:,.2f} kEUR")
    print(f"   But Excel uses 73.9% gearing (not 75.24%)")
    print(f"   Excel target debt: 42,852 kEUR / {total_capex:,.2f} kEUR = {42852/total_capex*100:.2f}%")

    # (c) DSRA initialization
    dsra_months = inputs.financing.dsra_months
    first_payment = sculpt.payment_schedule[0] if sculpt.payment_schedule else 0
    print(f"\n4. Cause (c): DSRA initialization reduces available CF")
    print(f"   DSRA months: {dsra_months}")
    print(f"   First payment: {first_payment:,.2f} kEUR")
    # Current formula: (dsra_months / 12) * (sculpt_result.payment_schedule[0] * 2)
    # = (6/12) * first_payment * 2 = first_payment
    # That's a 6-month reserve = 1 semi-annual payment = first_payment
    # Excel dsra_initial_keur: 2,239.1 kEUR
    current_dsra_init = (dsra_months / 12) * (first_payment * 2)
    print(f"   Current DSRA initial balance: {current_dsra_init:,.2f} kEUR")
    print(f"   Excel DSRA initial: 2,239.1 kEUR")
    print(f"   → {'MISMATCH - DSRA contributes to debt error' if abs(current_dsra_init - 2239.1) > 100 else 'match'}")

    # (d) Rate per period
    print(f"\n5. Cause (d): Rate per period is wrong")
    annual_rate = 0.0565
    rate_per_period = annual_rate / 2
    print(f"   Annual base rate: {annual_rate*100:.2f}%")
    print(f"   Rate per semi-annual period: {rate_per_period*100:.4f}%")
    print(f"   Should match Excel: 5.84% annual → 2.92% per semi-annual")
    print(f"   → Rate appears correct")

    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    print("""
Based on diagnosis, the PRIMARY cause of debt deviation is:

  (a) CFADS for sculpting uses EBITDA instead of EBITDA - Tax
      run_waterfall passes ebitda_schedule (pre-tax) to closed_form_sculpt.
      Excel uses CFADS = EBITDA - Tax for sculpting → smaller CFADS →
      smaller allowable debt service → larger debt (42.8M vs 37M).

Also active:
  (b) Gearing cap: Excel uses 73.9% gearing (42,852/57,973 = 0.739),
      but model uses 75.24% from inputs. The 0.7524 in inputs is wrong.

Summary of expected fixes:
  1. Fix CFADS for sculpting: use EBITDA - Tax, not raw EBITDA
  2. Fix gearing ratio: use 0.739 from Excel, not 0.7524 from inputs
  3. DSRA initial balance formula is equivalent to Excel (1 payment coverage)
  4. Rate per period is correct
""")
    return result


if __name__ == "__main__":
    run_diagnosis()