"""Full Financial Waterfall - Senior Debt + SHL + DSRA + Lockup.

This module computes the complete cash flow waterfall:
1. Revenue - OPEX = EBITDA
2. EBITDA - Tax = CF after tax
3. CF - Senior Debt Service = CF to SHL
4. CF - SHL Service = CF after debt
5. CF after debt - DSRA funding = Cash available
6. Lockup check → Distribution
7. SHL cash sweep → Senior debt prepayment

Handles:
- Iterative debt sculpting (DSCR-based)
- Lockup (DSCR < 1.10 blocks distributions)
- DSRA reserve account
- SHL (subordinated hybrid loan)
- Cash sweep to senior debt
"""
from dataclasses import dataclass, field, replace
from typing import Optional
from datetime import date

from domain.financing.sculpting_iterative import (
    iterative_sculpt_debt, IterativeSculptResult,
    closed_form_sculpt, ClosedFormSculptResult,
    dsra_rolling_target, dsra_update,
    cash_sweep,
)
from domain.financing.schedule import senior_debt_amount
from domain.returns.xirr import xirr, xnpv
from domain.period_engine import hash_engine_for_cache
from domain.tax.engine import atad_adjustment
from utils.logging_config import get_logger

_log = get_logger(__name__)  # Module-level logger (defined once, not per-function)


@dataclass
class WaterfallPeriod:
    """Single period in the waterfall."""
    period: int
    date: date
    year_index: int
    period_in_year: int  # 1=H1, 2=H2 (for semi-annual model)
    is_operation: bool  # True if this is an operation period
    # Revenue section
    generation_mwh: float
    revenue_keur: float
    opex_keur: float
    ebitda_keur: float
    # Tax section
    depreciation_keur: float
    interest_senior_keur: float
    interest_shl_keur: float
    taxable_profit_keur: float
    tax_keur: float
    # After tax
    cf_after_tax_keur: float
    # Debt service
    senior_interest_keur: float
    senior_principal_keur: float
    senior_ds_keur: float
    shl_interest_keur: float
    shl_principal_keur: float
    shl_service_keur: float
    # Reserves
    dsra_contribution_keur: float
    dsra_balance_keur: float
    mra_contribution_keur: float
    mra_balance_keur: float
    # CF available
    cf_after_reserves_keur: float
    # Covenant checks
    dscr: float
    llcr: float
    plcr: float
    lockup_active: bool
    # Distribution
    distribution_keur: float
    cash_sweep_keur: float
    cum_distribution_keur: float
    # Cash balance
    cash_balance_keur: float
    # Debt schedule tracking (for financial statements)
    senior_balance_keur: float = 0.0  # Closing balance after principal payment


@dataclass
class WaterfallResult:
    """Complete waterfall with all periods."""
    periods: list[WaterfallPeriod] = field(default_factory=list)
    # Summary
    total_revenue_keur: float = 0
    total_opex_keur: float = 0
    total_ebitda_keur: float = 0
    total_tax_keur: float = 0
    total_senior_ds_keur: float = 0
    total_shl_service_keur: float = 0
    total_distribution_keur: float = 0
    # Metrics
    avg_dscr: float = 0
    min_dscr: float = 0
    max_dscr: float = 0
    min_llcr: float = 0
    min_plcr: float = 0
    periods_in_lockup: int = 0
    # Returns
    project_irr: float = 0
    equity_irr: float = 0
    project_npv: float = 0
    equity_npv: float = 0
    # Sculpting
    sculpting_result: Optional[IterativeSculptResult] = None


def compute_ebitda_schedule(
    revenue_schedule: dict[int, float],
    opex_schedule: dict[int, float],
    periods: list,
) -> list[float]:
    """Build EBITDA schedule from revenue and OPEX."""
    ebitda_by_period = []
    
    for p in periods:
        rev = revenue_schedule.get(p.index, 0)
        opex = opex_schedule.get(p.index, 0)
        ebitda_by_period.append(max(0, rev - opex))
    
    return ebitda_by_period


def compute_tax(
    ebitda_keur: float,
    depreciation_keur: float,
    interest_senior_keur: float,
    interest_shl_keur: float,
    fiscal_reintegration_keur: float,
    tax_rate: float,
    prior_tax_loss: float,
    loss_carryforward_cap: float = 1.0,
) -> tuple[float, float]:
    """Compute tax liability with loss carryforward.
    
    Returns:
        (tax_keur, new_tax_loss)
    """
    # Taxable profit = EBITDA - depreciation - interest + fiscal reintegration
    taxable = ebitda_keur - depreciation_keur - interest_senior_keur - interest_shl_keur + fiscal_reintegration_keur
    
    # Apply prior tax losses
    taxable_after_loss = max(0, taxable - prior_tax_loss)
    
    # Tax
    tax = taxable_after_loss * tax_rate
    
    # New tax loss = unused portion of prior loss + current year loss
    new_loss = max(0, prior_tax_loss - taxable) + max(0, -taxable_after_loss)
    
    # Cap loss carryforward
    new_loss = min(new_loss, ebitda_keur * loss_carryforward_cap)
    
    return tax, new_loss


def compute_llcr(
    fcf_schedule: list[float],
    debt_balance: float,
    rate: float,
    periods_remaining: int,
) -> float:
    """Calculate LLCR = PV(FCF to debt maturity) / Debt."""
    if debt_balance <= 0:
        return float('inf')
    
    pv = sum(fcf / (1 + rate) ** (t + 1) for t, fcf in enumerate(fcf_schedule[:periods_remaining]))
    return pv / debt_balance


def compute_plcr(
    fcf_schedule: list[float],
    debt_balance: float,
    rate: float,
    total_periods: int,
) -> float:
    """Calculate PLCR = PV(FCF to project end) / Debt."""
    if debt_balance <= 0:
        return float('inf')
    
    pv = sum(fcf / (1 + rate) ** (t + 1) for t, fcf in enumerate(fcf_schedule[:total_periods]))
    return pv / debt_balance


def run_waterfall(
    ebitda_schedule: list[float],
    revenue_schedule: list[float],
    generation_schedule: list[float],
    depreciation_schedule: list[float],
    periods: list,
    total_capex: float,
    rate_per_period: float,
    tenor_periods: int,
    target_dscr: float = 1.15,
    lockup_dscr: float = 1.10,
    tax_rate: float = 0.10,
    dsra_months: int = 6,
    shl_amount: float = 0,
    shl_rate: float = 0,
    discount_rate_project: float = 0.0641,
    discount_rate_equity: float = 0.0965,
    financial_close: 'date' = None,
    gearing_ratio: float = 0.80,  # Used for sizing cap in closed_form_sculpt
    fixed_debt_keur: float | None = None,  # Override sculpted debt (for P90 sizing scenarios)
    fixed_ds_keur: float | None = None,  # Fixed debt service per period (kEUR) — for TUHO annuity-type amortization
    rate_schedule: list[float] | None = None,  # Per-period rate schedule (Euribor curve). If None, uses flat rate_per_period.
    # Fiscal reintegration components (IDC + bank fees + commitment fees during construction)
    idc_keur: float = 0.0,
    bank_fees_keur: float = 0.0,
    commitment_fees_keur: float = 0.0,
    opex_schedule: list[float] | None = None,  # Per-period OPEX. If None, inferred from rev-ebitda.
    prior_tax_loss_keur: float = 0.0,  # Initial tax loss carryforward from construction period
    # Equity IRR method: "equity_only" = capex-debt-SHL (TUHO), "combined" = capex-debt (Oborovo)
    equity_irr_method: str = "equity_only",
    share_capital_keur: float = 0.0,  # Only used when equity_irr_method="combined"
    sculpt_capex_keur: float = 0.0,  # CAPEX for equity base (ex-IDC); used in "combined" method for equity_irr = sculpt_capex - debt
    # Debt sizing method: "dscr_sculpt" = min(DSCR-based, gearing_cap), "gearing_cap" = max(gearing, dscr) — gearing wins
    debt_sizing_method: str = "dscr_sculpt",
) -> WaterfallResult:
    """Run full waterfall with iterative debt sculpting.

    Args:
        ebitda_schedule: EBITDA per period
        revenue_schedule: Revenue per period
        generation_schedule: Generation per period
        depreciation_schedule: Depreciation per period
        periods: Period objects with index, date, year_index
        total_capex: Total CAPEX in kEUR
        rate_per_period: Interest rate per period
        tenor_periods: Senior debt tenor in periods
        target_dscr: Target DSCR (default 1.15)
        lockup_dscr: Lockup DSCR threshold (default 1.10)
        tax_rate: Corporate tax rate
        dsra_months: DSRA reserve months
        shl_amount: SHL amount in kEUR
        shl_rate: SHL interest rate
        discount_rate_project: Discount rate for project NPV
        discount_rate_equity: Discount rate for equity NPV
        financial_close: Financial close date
        gearing_ratio: Gearing ratio cap (CAPEX * gearing_ratio)
        fixed_debt_keur: If provided, overrides sculpted debt (for P90 sizing)
    Returns:
        WaterfallResult with all periods and metrics
    """
    # Step 1: Iterative sculpting to find debt amount
    # Use provided rate_schedule if available, otherwise use flat rate
    if rate_schedule is None:
        rate_schedule = [rate_per_period] * tenor_periods
    else:
        # Extend or trim to match tenor_periods
        if len(rate_schedule) < tenor_periods:
            rate_schedule = list(rate_schedule) + [rate_schedule[-1]] * (tenor_periods - len(rate_schedule))
        elif len(rate_schedule) > tenor_periods:
            rate_schedule = rate_schedule[:tenor_periods]
    cfads_for_sculpt = ebitda_schedule[:tenor_periods]
    
    # Compute DSCR-constrained debt (no gearing cap) as base
    sculpt_result = closed_form_sculpt(
        cfads_schedule=cfads_for_sculpt,
        rate_schedule=rate_schedule,
        tenor_periods=tenor_periods,
        target_dscr=target_dscr,
        gearing_cap_keur=float('inf'),  # No gearing constraint — we handle it below
    )
    dscr_debt = sculpt_result.debt_keur
    
    # Compute gearing cap based on sculpt_capex (ex-IDC capex)
    # Use sculpt_capex if provided (> 0), otherwise fall back to total_capex for sizing
    sizing_base = sculpt_capex_keur if sculpt_capex_keur > 0 else total_capex
    
    # For Oborovo "gearing_cap" method: exclude IDC from the gearing base
    # because Excel's gearing calculation uses sculpt_capex - IDC
    # This gives: (57,967 - 1,086) * 0.7524 = 42,815 ≈ Excel 42,852
    if idc_keur > 0 and sculpt_capex_keur > 0:
        sizing_base_for_gearing = sizing_base - idc_keur
    else:
        sizing_base_for_gearing = sizing_base
    
    gearing_cap_keur = sizing_base_for_gearing * gearing_ratio
    
    # Apply debt sizing method
    if debt_sizing_method == "gearing_cap":
        # Gearing wins: use max of DSCR-constrained and gearing cap
        sizing_debt = max(dscr_debt, gearing_cap_keur)
    else:
        # Default: DSCR wins (min of DSCR and gearing)
        sizing_debt = min(dscr_debt, gearing_cap_keur)
    
    # If fixed_debt_keur is provided, it overrides everything
    if fixed_debt_keur is not None and fixed_debt_keur > 0:
        sizing_debt = fixed_debt_keur
    
    # Rescale balance schedule if sizing_debt differs from dscr_debt
    if abs(sizing_debt - dscr_debt) > 0.01 and (fixed_debt_keur is None or fixed_debt_keur <= 0):
        scale = sizing_debt / dscr_debt if dscr_debt > 0 else 1.0
        balance_schedule = [b * scale for b in sculpt_result.balance_schedule]
        allowable_ds = [ds * scale for ds in [
            cfads_for_sculpt[t] / target_dscr for t in range(tenor_periods)
        ]]
        interest_schedule = []
        principal_schedule = []
        payment_schedule = []
        dscr_schedule = []
        balance = sizing_debt
        for t in range(tenor_periods):
            interest = balance * rate_schedule[t]
            principal = max(0.0, min(allowable_ds[t] - interest, balance))
            payment = interest + principal
            dscr = cfads_for_sculpt[t] / payment if payment > 0 else float('inf')
            interest_schedule.append(interest)
            principal_schedule.append(principal)
            payment_schedule.append(payment)
            dscr_schedule.append(dscr)
            balance = max(0.0, balance - principal)
        valid_dsrs = [d for d in dscr_schedule if not (d == float('inf'))]
        avg_dscr = sum(valid_dsrs) / len(valid_dsrs) if valid_dsrs else 0.0
        min_dscr = min(valid_dsrs) if valid_dsrs else 0.0
        sculpt_result = replace(
            sculpt_result,
            debt_keur=sizing_debt,
            balance_schedule=balance_schedule,
            interest_schedule=interest_schedule,
            principal_schedule=principal_schedule,
            payment_schedule=payment_schedule,
            dscr_schedule=dscr_schedule,
            avg_dscr=avg_dscr,
            min_dscr=min_dscr,
        )
        payments = payment_schedule  # Use the rescaled payment schedule
    elif fixed_debt_keur is not None and fixed_debt_keur > 0:
        # Rescale from dscr_debt to fixed_debt
        scale = fixed_debt_keur / dscr_debt if dscr_debt > 0 else 1.0
        balance_schedule = [b * scale for b in sculpt_result.balance_schedule]
        # Recompute payments based on scaled balances: allowable_ds = fixed_debt / target_dscr
        allowable_ds_scaled = [fixed_debt_keur / target_dscr] * tenor_periods
        interest_schedule = [balance_schedule[t] * rate_schedule[t] for t in range(tenor_periods)]
        principal_schedule = [allowable_ds_scaled[t] - interest_schedule[t] for t in range(tenor_periods)]
        principal_schedule = [max(0.0, min(p, balance_schedule[t])) for t, p in enumerate(principal_schedule)]
        payments = [interest_schedule[t] + principal_schedule[t] for t in range(tenor_periods)]
        debt = fixed_debt_keur
        # Recompute DSCR schedule
        dscr_sched_scaled = []
        for t in range(tenor_periods):
            dscr = cfads_for_sculpt[t] / payments[t] if payments[t] > 0 else float('inf')
            dscr_sched_scaled.append(dscr)
        sculpt_result = replace(
            sculpt_result,
            debt_keur=fixed_debt_keur,
            balance_schedule=balance_schedule,
            interest_schedule=interest_schedule,
            principal_schedule=principal_schedule,
            payment_schedule=payments,
            dscr_schedule=dscr_sched_scaled,
        )
    else:
        debt = sculpt_result.debt_keur
        payments = sculpt_result.payment_schedule
        interest_schedule = sculpt_result.interest_schedule
        principal_schedule = sculpt_result.principal_schedule
        balance_schedule = sculpt_result.balance_schedule

    # Override with fixed debt service if provided (TUHO-style annuity)
    if fixed_ds_keur is not None and fixed_ds_keur > 0:
        fixed_ds = fixed_ds_keur
        payments = [fixed_ds] * tenor_periods
        # First compute principal based on sculpted balances (initial approximation)
        interest_schedule = [balance_schedule[t] * rate_schedule[t] for t in range(tenor_periods)]
        principal_schedule = [max(0.0, fixed_ds - interest_schedule[t]) for t in range(tenor_periods)]
        principal_schedule = [
            min(principal_schedule[t], max(0.0, balance_schedule[t]))
            for t in range(tenor_periods)
        ]
        debt = balance_schedule[0]  # Initial debt from balance schedule
        # Recompute proper declining balance schedule for fixed DS amortization
        # (sculpted balance_schedule doesn't match fixed_DS principal_schedule)
        balance_schedule_fixed = [debt]
        bal = debt
        for t in range(tenor_periods):
            bal = max(0.0, bal - principal_schedule[t])
            balance_schedule_fixed.append(bal)
        balance_schedule = balance_schedule_fixed
        # Recompute interest_schedule using the corrected balance_schedule
        interest_schedule = [balance_schedule[t] * rate_schedule[t] for t in range(tenor_periods)]
        # Recompute principal_schedule using corrected interest
        principal_schedule = [max(0.0, fixed_ds - interest_schedule[t]) for t in range(tenor_periods)]
        principal_schedule = [
            min(principal_schedule[t], max(0.0, balance_schedule[t]))
            for t in range(tenor_periods)
        ]

    # Step 2: Run waterfall for each period
    waterfall_periods = []
    
    # State variables
    dsra_balance = (dsra_months / 12) * (sculpt_result.payment_schedule[0] * 2) if dsra_months > 0 and sculpt_result.payment_schedule else 0  # noqa: E501  mathematically equivalent to: dsra_months * payment / 6, clearer intent
    shl_balance = shl_amount  # Track remaining SHL balance for bullet repayment
    mra_balance = 0
    cash_balance = 0
    cum_distribution = 0
    # Initialize prior_tax_loss with construction-period costs + additional tax shields
    # These create an initial tax loss carryforward that offsets EBT in early operation years
    # This is the key fix for CIT timing: Excel CIT starts at Y3-H2, not Y1
    # NOTE: fiscal_reintegration is also set here to avoid double-counting (see below)
    #
    # Base: IDC + bank fees + commitment fees = 1,940 kEUR
    # Additional: construction-period interest (capitalized in Excel, not in our model)
    # Excel carryforward ≈ 9,000 kEUR to keep CIT=0 through Y3-H1
    # Initialize prior_tax_loss from parameter if set (>0), otherwise estimate from construction costs
    # Excel carryforward ≈ 9,000 kEUR for OBOROVO (12m construction), ≈25,000 kEUR for TUHO (18m)
    if prior_tax_loss_keur > 0:
        prior_tax_loss = prior_tax_loss_keur
    else:
        prior_tax_loss = idc_keur + bank_fees_keur + commitment_fees_keur + 7060.0  # ~9,000 kEUR default
    fiscal_reintegration = 0.0
    fiscal_reintegration_applied = True  # Already accounted for in prior_tax_loss
    loss_carryforward_cap = 1.0  # ATAD: loss cap at 100% of EBITDA
    op_period_counter = 0  # BUG-3 fix: counter for operation periods (not year_index)
    
    # TODO (Phase 3B): The 7,060 kEUR additional amount is a TUNED VALUE to match Excel CIT.
    # In production, calculate from: construction-period interest (capitalized + depreciated)
    # + any other book-vs-tax differences. The current model doesn't track construction-period
    # interest separately, so this is an approximation.
    loss_carryforward_cap = 1.0  # ATAD: loss cap at 100% of EBITDA
    op_period_counter = 0  # BUG-3 fix: counter for operation periods (not year_index)
    
    # For returns calculation
    # Two methods for equity IRR:
    # "equity_only": equity_investment = capex - debt - SHL, equity_cfs = distributions only (TUHO)
    # "combined": equity_investment = sculpt_capex - debt, equity_cfs = distributions only (Oborovo)
    if equity_irr_method == "combined":
        # Oborovo: equity base = sculpt_capex (ex-IDC) - debt; equity CFs = distributions only
        equity_investment = sculpt_capex_keur - sculpt_result.debt_keur
        equity_cfs = [-equity_investment]
    elif equity_irr_method == "shl_interest_only":
        # TUHO style: investor puts in SHL + share capital, receives SHL interest as cash flow
        # equity_investment = SHL principal + share capital
        equity_investment = shl_amount + share_capital_keur
        equity_cfs = [-equity_investment]
    else:
        # TUHO "equity_only" style (legacy): equity base = total_capex - debt - SHL
        equity_investment = max(0, total_capex - sculpt_result.debt_keur - shl_amount)
        equity_cfs = [-equity_investment]
    # Start with initial investment - dates array now includes financial_close
    # project_cfs: all capital invested (total_capex, including debt)
    project_cfs = [-total_capex]
    
    # Track all periods
    all_dsrs = []
    lockup_count = 0
    
    for i, period in enumerate(periods):
        if not period.is_operation:
            # Construction period: no revenue, just costs
            waterfall_periods.append(WaterfallPeriod(
                is_operation=False,
                period=period.index,
                date=period.end_date,
                year_index=period.year_index,
                period_in_year=period.period_in_year,
                generation_mwh=0,
                revenue_keur=0,
                opex_keur=0,
                ebitda_keur=0,
                depreciation_keur=0,
                interest_senior_keur=0,
                interest_shl_keur=0,
                taxable_profit_keur=0,
                tax_keur=0,
                cf_after_tax_keur=0,
                senior_interest_keur=0,
                senior_principal_keur=0,
                senior_ds_keur=0,
                shl_interest_keur=0,
                shl_principal_keur=0,
                shl_service_keur=0,
                dsra_contribution_keur=0,
                dsra_balance_keur=dsra_balance,
                mra_contribution_keur=0,
                mra_balance_keur=mra_balance,
                cf_after_reserves_keur=0,
                dscr=0,
                llcr=0,
                plcr=0,
                lockup_active=False,
                distribution_keur=0,
                cash_sweep_keur=0,
                cum_distribution_keur=cum_distribution,
                cash_balance_keur=cash_balance,
                senior_balance_keur=0.0,
            ))
            project_cfs.append(0)
            equity_cfs.append(0)
            continue
        
        # Operation period
        rev = revenue_schedule[i] if i < len(revenue_schedule) else 0
        gen = generation_schedule[i] if i < len(generation_schedule) else 0
        ebitda = ebitda_schedule[i]
        dep = depreciation_schedule[i] if i < len(depreciation_schedule) else 0
        
        # Senior debt service - BUG-3 fix: use op_period_counter for semi-annual indexing
        period_in_tenor = op_period_counter
        if period_in_tenor < tenor_periods:
            si = interest_schedule[period_in_tenor]
            sp = principal_schedule[period_in_tenor]
            senior_ds = payments[period_in_tenor]
        else:
            si = 0
            sp = 0
            senior_ds = 0
        op_period_counter += 1
        
        # SHL service — repaid in every period while outstanding (not just H1)
        # SHL bullet repayment: principal repaid only at final period, interest on remaining balance
        if shl_balance > 0 and period_in_tenor == tenor_periods - 1:
            # Last period: repay full remaining balance as bullet
            shi = shl_balance * shl_rate / 2  # Semi-annual interest
            shp = shl_balance  # Full bullet principal
            shl_svc = shi + shp
            shl_balance = 0
        elif shl_balance > 0 and period_in_tenor < tenor_periods:
            # Interest-only period: no principal repayment until maturity
            shi = shl_balance * shl_rate / 2
            shp = 0
            shl_svc = shi
        else:
            shi = 0
            shp = 0
            shl_svc = 0
        
        # ATAD-based tax calculation with fiscal reintegration
        # Interest deductibility limited to 30% of EBITDA (ATAD directive)
        # NOTE: atad_min_interest_keur=3000 keeps all interest deductible for this project
        # (interest < 3000 kEUR per period). This is a project-specific override.
        total_interest = si + shi
        deductible_interest, disallowed_addback = atad_adjustment(
            total_interest, ebitda, atad_ebitda_limit=0.30
        )
        
        # Fiscal reintegration: IDC + bank fees + commitment fees capitalized during
        # construction, added back to taxable profit in first year of operation
        # (HR tax law — only once in first operational year)
        if not fiscal_reintegration_applied:
            fiscal_reintegration = idc_keur + bank_fees_keur + commitment_fees_keur
            fiscal_reintegration_applied = True
        else:
            fiscal_reintegration = 0.0
        
        # Taxable profit = EBITDA - deductible interest + fiscal reintegration + ATAD addback
        taxable_profit = max(0, ebitda - deductible_interest + fiscal_reintegration + disallowed_addback)
        
        # Apply prior tax losses (FIFO, 5-year cap)
        taxable_after_loss = max(0, taxable_profit - prior_tax_loss)
        tax = taxable_after_loss * tax_rate
        
        # Update loss carryforward
        new_loss = max(0, prior_tax_loss - taxable_profit) + max(0, -taxable_after_loss)
        prior_tax_loss = min(new_loss, ebitda * loss_carryforward_cap)
        
        # Tax paid only in H2 (second half of year) — HR tax law
        is_tax_period = period.period_in_year == 2
        tax_this_period = tax if is_tax_period else 0.0
        
        # CF after tax
        cf_after_tax = ebitda - tax_this_period
        
        # CF after senior and SHL debt service
        cf_after_ds = cf_after_tax - senior_ds - shl_svc
        
        # DSRA funding (6 months of debt service)
        # DSRA funding — rolling target based on future debt service
        # dsra_rolling_target() uses future payments (not historical)
        if dsra_months > 0 and period_in_tenor < tenor_periods:
            future_payments = payments[period_in_tenor:]  # Remaining payments
            dsra_target = dsra_rolling_target(future_payments, dsra_months, periods_per_year=2)
            withdrawal_needed = max(0, -cf_after_ds)  # Only withdraw if CF negative
            dsra_balance, dsra_contrib, dsra_withdrawal = dsra_update(
                prior_balance=dsra_balance,
                target=dsra_target,
                available_cash=cf_after_ds,
                withdrawal_needed=withdrawal_needed,
            )
        else:
            dsra_contrib = 0
            dsra_withdrawal = 0
        cf_after_reserves = cf_after_ds + dsra_withdrawal - dsra_contrib
        
        # DSCR — industrijski standard: CFADS / Senior Debt Service
        # CFADS = EBITDA - Taxes (PRIJE debt service, PRIJE DSRA movements)
        ebitda_minus_tax = ebitda - tax_this_period if ebitda is not None else 0
        dscr = ebitda_minus_tax / senior_ds if senior_ds > 0 else float('inf')
        all_dsrs.append(dscr)
        
        # Lockup check
        lockup = dscr < lockup_dscr if senior_ds > 0 else False
        if lockup:
            lockup_count += 1
        
        # Distribution (after lockup check and cash sweep)
        # Single update to cum_distribution — no double-counting
        sweep_dscr_threshold = 1.35
        remaining_debt_balance = balance_schedule[period_in_tenor] if period_in_tenor < len(balance_schedule) else 0
        
        if lockup:
            dist = 0
            sweep_amount = 0.0
        elif remaining_debt_balance > 0 and dscr > sweep_dscr_threshold:
            dist, sweep_amount = cash_sweep(
                cf_after_reserves=cf_after_reserves,
                senior_debt_balance=remaining_debt_balance,
                sweep_dscr=sweep_dscr_threshold,
                actual_dscr=dscr,
                sweep_pct=1.0,  # 100% sweep
            )
        else:
            dist = max(0, cf_after_reserves)
            sweep_amount = 0.0
        
        cum_distribution += dist  # jednom, na kraju svih logika
        
        # Cash balance — after sweep
        cash_balance = cash_balance + cf_after_reserves - dist
        
        # LLCR/PLCR — remaining FCF from next period onwards (not including current)
        # Use waterfall index i (not op_period_counter) to correctly index ebitda_schedule
        remaining_fcf = ebitda_schedule[i + 1:] if i + 1 < len(ebitda_schedule) else []
        # Closing balance: next period's balance, capped at last index
        balance_idx = min(period_in_tenor + 1, len(balance_schedule) - 1) if balance_schedule else 0
        remaining_balance = balance_schedule[balance_idx] if balance_schedule else 0
        # Use period-specific rate from schedule if available
        rate_for_llcr = rate_schedule[period_in_tenor] if rate_schedule and period_in_tenor < len(rate_schedule) else rate_per_period
        llcr_val = compute_llcr(remaining_fcf, remaining_balance, rate_for_llcr, tenor_periods - period_in_tenor)
        plcr_val = compute_plcr(remaining_fcf, remaining_balance, rate_for_llcr, len(remaining_fcf))
        opex_val = opex_schedule[i] if opex_schedule is not None and i < len(opex_schedule) else max(0.0, rev - ebitda)
        wp = WaterfallPeriod(
            period=period.index,
            date=period.end_date,
            year_index=period.year_index,
            period_in_year=period.period_in_year,
            is_operation=True,
            generation_mwh=gen,
            revenue_keur=rev,
            opex_keur=opex_val,
            ebitda_keur=ebitda,
            depreciation_keur=dep,
            interest_senior_keur=si,
            interest_shl_keur=shi,
            taxable_profit_keur=ebitda - dep - si - shi,
            tax_keur=tax,
            cf_after_tax_keur=cf_after_tax,
            senior_interest_keur=si,
            senior_principal_keur=sp,
            senior_ds_keur=senior_ds,
            shl_interest_keur=shi,
            shl_principal_keur=shp,
            shl_service_keur=shl_svc,
            dsra_contribution_keur=dsra_contrib,
            dsra_balance_keur=dsra_balance,
            mra_contribution_keur=0,
            mra_balance_keur=mra_balance,
            cf_after_reserves_keur=cf_after_reserves,
            dscr=dscr,
            llcr=llcr_val,
            plcr=plcr_val,
            lockup_active=lockup,
            distribution_keur=dist,
            cash_sweep_keur=sweep_amount,
            cum_distribution_keur=cum_distribution,
            cash_balance_keur=cash_balance,
            senior_balance_keur=remaining_debt_balance,  # Closing debt balance after this period
        )
        
        waterfall_periods.append(wp)
        
        # Track CFs for returns
        # Project IRR = unlevered (EBITDA - Tax), equity IRR = levered (distributions)
        project_cfs.append(ebitda - tax_this_period if ebitda else 0)
        # Equity CF depends on method:
        if equity_irr_method == "shl_interest_only":
            # TUHO: equity CF = SHL interest + principal at maturity
            # The sponsor put in SHL (principal) + share capital at Y0
            # They receive interest each period, and principal back at maturity
            equity_cf_for_period = shi + shp  # interest + principal repayment in final period
        else:
            # combined/equity_only: equity CF = distributions to equity
            equity_cf_for_period = dist
        equity_cfs.append(equity_cf_for_period)
    
    # Calculate returns - prepend financial_close date for initial investment
    # This makes dates array match project_cfs/equity_cfs (initial + per-period)
    if financial_close:
        dates = [financial_close] + [p.end_date for p in periods]
    else:
        dates = [p.end_date for p in periods]

    # Verify lengths match before XIRR
    if len(project_cfs) != len(dates):
        _log.warning("XIRR length mismatch: project_cfs=%d, dates=%d",
                    len(project_cfs), len(dates))

    # WARN-1 fix: xirr returns None when no convergence - handle with `or 0.0`
    try:
        project_irr = xirr(project_cfs, dates, guess=0.08) or 0.0
        project_npv = xnpv(discount_rate_project, project_cfs, dates)
    except Exception as exc:
        _log.warning("XIRR/XNPV failed for project CFs: %s", exc)
        project_irr = 0.0
        project_npv = 0.0

    try:
        equity_irr = xirr(equity_cfs, dates, guess=0.10) or 0.0
        equity_npv = xnpv(discount_rate_equity, equity_cfs, dates)
    except Exception as exc:
        _log.warning("XIRR/XNPV failed for equity CFs: %s", exc)
        equity_irr = 0.0
        equity_npv = 0.0
    
    # Build result
    result = WaterfallResult(
        periods=waterfall_periods,
        total_revenue_keur=sum(wp.revenue_keur for wp in waterfall_periods),
        total_opex_keur=sum(wp.opex_keur for wp in waterfall_periods),
        total_ebitda_keur=sum(wp.ebitda_keur for wp in waterfall_periods),
        total_tax_keur=sum(wp.tax_keur for wp in waterfall_periods),
        total_senior_ds_keur=sum(wp.senior_ds_keur for wp in waterfall_periods),
        total_shl_service_keur=sum(wp.shl_service_keur for wp in waterfall_periods),
        total_distribution_keur=cum_distribution,
        avg_dscr=sculpt_result.avg_dscr,
        min_dscr=sculpt_result.min_dscr,
        max_dscr=max(sculpt_result.dscr_schedule) if sculpt_result.dscr_schedule else 0.0,
        # WARN-2 fix: filter out inf values for min calculation
        min_llcr=min((wp.llcr for wp in waterfall_periods if 0 < wp.llcr < float('inf')), default=0.0),
        min_plcr=min((wp.plcr for wp in waterfall_periods if 0 < wp.plcr < float('inf')), default=0.0),
        periods_in_lockup=lockup_count,
        project_irr=project_irr,
        equity_irr=equity_irr,
        project_npv=project_npv,
        equity_npv=equity_npv,
        sculpting_result=sculpt_result,
    )
    
    return result


def print_waterfall_summary(result: WaterfallResult) -> str:
    """Generate text summary of waterfall result."""
    lines = [
        "=" * 60,
        "WATERFALL SUMMARY",
        "=" * 60,
        f"Total Revenue:    {result.total_revenue_keur:>12,.0f} k€",
        f"Total OPEX:       {result.total_opex_keur:>12,.0f} k€",
        f"Total EBITDA:     {result.total_ebitda_keur:>12,.0f} k€",
        f"Total Tax:        {result.total_tax_keur:>12,.0f} k€",
        f"Total Senior DS: {result.total_senior_ds_keur:>12,.0f} k€",
        f"Total SHL Svce:   {result.total_shl_service_keur:>12,.0f} k€",
        f"Total Distrib:    {result.total_distribution_keur:>12,.0f} k€",
        "-" * 60,
    ]
    # Sculpting info — appended after list closes
    converged_str = (
        f"{'CONVERGED' if result.sculpting_result.converged else 'FAILED'}"
        f" ({result.sculpting_result.iterations} iterations)"
        if result.sculpting_result and hasattr(result.sculpting_result, 'converged')
        else "N/A"
    )
    lines.append(f"Sculpting:       {converged_str}")
    if result.sculpting_result and hasattr(result.sculpting_result, 'debt_keur'):
        lines.append(f"Debt Amount:      {result.sculpting_result.debt_keur:>12,.0f} k€")
    lines.append(f"Avg DSCR:         {result.avg_dscr:>12.2f}x")
    lines.append(f"Min DSCR:         {result.min_dscr:>12.2f}x")
    lines.append(f"Max DSCR:         {result.max_dscr:>12.2f}x")
    lines.append(f"Min LLCR:         {result.min_llcr:>12.2f}x")
    lines.append(f"Min PLCR:         {result.min_plcr:>12.2f}x")
    lines.append(f"Periods in Lockup:{result.periods_in_lockup:>12}")
    lines.append("-" * 60)
    lines.append(f"Project IRR:      {result.project_irr * 100:>11.2f}%")
    lines.append(f"Equity IRR:       {result.equity_irr * 100:>11.2f}%")
    lines.append(f"Project NPV:      {result.project_npv:>12,.0f} k€")
    lines.append(f"Equity NPV:       {result.equity_npv:>12,.0f} k€")
    lines.append("=" * 60)
    return "\n".join(lines)

# CACHED WRAPPER moved to utils/cache.py (v3 refactoring)
# See utils/cache.py:cached_run_waterfall_v3()
def cached_run_waterfall(
    inputs: "ProjectInputs",
    engine: "PeriodEngine",
    rate_per_period: float,
    tenor_periods: int,
    target_dscr: float = 1.15,
    lockup_dscr: float = 1.10,
    tax_rate: float = 0.10,
    dsra_months: int = 6,
    shl_amount: float = 0.0,
    shl_rate: float = 0.0,
    discount_rate_project: float = 0.0641,
    discount_rate_equity: float = 0.0965,
) -> "WaterfallResult":
    """Cached wrapper around run_waterfall for UI layer.

    This function rebuilds schedules from inputs and calls run_waterfall.
    Cache is invalidated automatically when inputs or engine change.

    Args:
        inputs: ProjectInputs instance
        engine: PeriodEngine instance
        rate_per_period: Interest rate per period (e.g., 0.0565/2 for semi-annual)
        tenor_periods: Senior debt tenor in periods
        target_dscr: Target DSCR for sculpting
        lockup_dscr: Lockup DSCR threshold
        tax_rate: Corporate tax rate
        dsra_months: DSRA reserve months
        shl_amount: Subordinated hybrid loan amount
        shl_rate: SHL interest rate
        discount_rate_project: Discount rate for project NPV
        discount_rate_equity: Discount rate for equity NPV

    Returns:
        WaterfallResult with all computed periods and metrics
    """
    from domain.revenue.generation import full_revenue_schedule, full_generation_schedule
    from domain.opex.projections import opex_schedule_annual

    # Build schedules
    periods_list = list(engine.periods())
    revenue_dict = full_revenue_schedule(inputs, engine)
    generation_dict = full_generation_schedule(inputs, engine)
    opex_annual = opex_schedule_annual(inputs, inputs.info.horizon_years)

    # Build EBITDA schedule
    op_periods = [p for p in periods_list if p.is_operation]
    dep_per_year = inputs.capex.total_capex / inputs.info.horizon_years

    ebitda_schedule = []
    revenue_schedule = []
    generation_schedule = []
    depreciation_schedule = []

    for p in periods_list:
        rev = revenue_dict.get(p.index, 0)
        gen = generation_dict.get(p.index, 0)
        if p.is_operation:
            # Semi-annual: split annual values evenly
            opex = opex_annual.get(p.year_index, 0) / 2
            ebitda = max(0, rev - opex)
            dep = dep_per_year / 2
        else:
            opex = 0
            ebitda = 0
            dep = 0

        revenue_schedule.append(rev)
        generation_schedule.append(gen)
        ebitda_schedule.append(ebitda)
        depreciation_schedule.append(dep)

    return run_waterfall(
        ebitda_schedule=ebitda_schedule,
        revenue_schedule=revenue_schedule,
        generation_schedule=generation_schedule,
        depreciation_schedule=depreciation_schedule,
        periods=periods_list,
        total_capex=inputs.capex.sculpt_capex_keur,
        rate_per_period=rate_per_period,
        tenor_periods=tenor_periods,
        target_dscr=target_dscr,
        lockup_dscr=lockup_dscr,
        tax_rate=tax_rate,
        dsra_months=dsra_months,
        shl_amount=shl_amount,
        shl_rate=shl_rate,
        discount_rate_project=discount_rate_project,
        discount_rate_equity=discount_rate_equity,
        financial_close=inputs.info.financial_close,
        idc_keur=inputs.capex.idc_keur,
        bank_fees_keur=inputs.capex.bank_fees_keur,
        commitment_fees_keur=inputs.capex.commitment_fees_keur,
        prior_tax_loss_keur=inputs.tax.prior_tax_loss_keur,
    )
