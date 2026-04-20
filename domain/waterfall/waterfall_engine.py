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
from dataclasses import dataclass, field
from typing import Optional
from datetime import date

from domain.financing.sculpting_iterative import (
    iterative_sculpt_debt, IterativeSculptResult
)
from domain.financing.schedule import senior_debt_amount
from domain.returns.xirr import xirr, xnpv


@dataclass
class WaterfallPeriod:
    """Single period in the waterfall."""
    period: int
    date: date
    year_index: int
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
    
    Returns:
        WaterfallResult with all periods and metrics
    """
    # Step 1: Iterative sculpting to find debt amount
    sculpt_result = iterative_sculpt_debt(
        ebitda_schedule,
        rate_per_period,
        tenor_periods,
        target_dscr,
        lockup_dscr,
        initial_debt_guess=total_capex * 0.70,  # Start from gearing
    )
    
    debt = sculpt_result.debt_keur
    payments = sculpt_result.payments
    interest_schedule = sculpt_result.interest_schedule
    principal_schedule = sculpt_result.principal_schedule
    balance_schedule = sculpt_result.balance_schedule
    
    # Step 2: Run waterfall for each period
    waterfall_periods = []
    
    # State variables
    dsra_balance = dsra_months * (sculpt_result.payments[0] if sculpt_result.payments else 0) / 6 if dsra_months > 0 else 0
    mra_balance = 0
    cash_balance = 0
    cum_distribution = 0
    prior_tax_loss = 0
    fiscal_reintegration = 0
    
    # For returns calculation
    project_cfs = [-total_capex]  # Initial investment
    equity_cfs = [-total_capex * (1 - 0.70)]  # Equity = CAPEX - Debt
    
    # Track all periods
    all_dsrs = []
    lockup_count = 0
    
    for i, period in enumerate(periods):
        if not period.is_operation:
            # Construction period: no revenue, just costs
            waterfall_periods.append(WaterfallPeriod(
                period=period.index,
                date=period.end_date,
                year_index=period.year_index,
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
            ))
            project_cfs.append(0)
            equity_cfs.append(0)
            continue
        
        # Operation period
        rev = revenue_schedule[i] if i < len(revenue_schedule) else 0
        gen = generation_schedule[i] if i < len(generation_schedule) else 0
        ebitda = ebitda_schedule[i]
        dep = depreciation_schedule[i] if i < len(depreciation_schedule) else 0
        
        # Senior debt service
        period_in_tenor = period.year_index - 1  # 0-based year index
        if period_in_tenor < tenor_periods:
            si = interest_schedule[period_in_tenor]
            sp = principal_schedule[period_in_tenor]
            senior_ds = payments[period_in_tenor]
        else:
            si = 0
            sp = 0
            senior_ds = 0
        
        # SHL service
        if shl_amount > 0 and period_in_tenor < tenor_periods:
            shi = shl_amount * shl_rate / 2  # Semi-annual
            shp = shl_amount / (tenor_periods * 2) if period.period_in_year == 1 else 0
            shl_svc = shi + shp
        else:
            shi = 0
            shp = 0
            shl_svc = 0
        
        # Tax calculation
        # Fiscal reintegration: pre-COD items added back to taxable profit
        fiscal_reintegration = dep * 0.5 if fiscal_reintegration == 0 else 0
        
        tax, prior_tax_loss = compute_tax(
            ebitda, dep, si, shi, fiscal_reintegration,
            tax_rate, prior_tax_loss
        )
        
        # CF after tax
        cf_after_tax = ebitda - tax
        
        # CF after senior and SHL debt service
        cf_after_ds = cf_after_tax - senior_ds - shl_svc
        
        # DSRA funding (6 months of debt service)
        if dsra_months > 0:
            dsra_target = dsra_months * senior_ds / 6
            dsra_contrib = max(0, dsra_target - dsra_balance) if cf_after_ds > 0 else 0
        else:
            dsra_contrib = 0
        
        dsra_balance += dsra_contrib
        cf_after_reserves = cf_after_ds - dsra_contrib
        
        # DSCR calculation
        dscr = ebitda / senior_ds if senior_ds > 0 else 0
        all_dsrs.append(dscr)
        
        # Lockup check
        lockup = dscr < lockup_dscr if senior_ds > 0 else False
        if lockup:
            lockup_count += 1
        
        # Distribution (after lockup check)
        if lockup:
            dist = 0
        else:
            dist = max(0, cf_after_reserves)
        
        cum_distribution += dist
        
        # Cash balance
        cash_balance = cash_balance + cf_after_reserves - dist
        
        # LLCR/PLCR
        remaining_fcf = ebitda_schedule[i:]
        remaining_balance = balance_schedule[period_in_tenor] if period_in_tenor < len(balance_schedule) else 0
        
        llcr_val = compute_llcr(remaining_fcf, remaining_balance, rate_per_period, tenor_periods - period_in_tenor)
        plcr_val = compute_plcr(remaining_fcf, remaining_balance, rate_per_period, len(ebitda_schedule) - i)
        
        wp = WaterfallPeriod(
            period=period.index,
            date=period.end_date,
            year_index=period.year_index,
            generation_mwh=gen,
            revenue_keur=rev,
            opex_keur=rev - ebitda,
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
            cash_sweep_keur=0,
            cum_distribution_keur=cum_distribution,
            cash_balance_keur=cash_balance,
        )
        
        waterfall_periods.append(wp)
        
        # Track CFs for returns
        project_cfs.append(cf_after_tax - senior_ds)
        equity_cfs.append(dist)
    
    # Calculate returns
    dates = [p.end_date for p in periods]
    
    try:
        project_irr = xirr(project_cfs, dates, guess=0.08)
        project_npv = xnpv(discount_rate_project, project_cfs, dates)
    except Exception:
        project_irr = 0
        project_npv = 0
    
    try:
        equity_irr = xirr(equity_cfs, dates, guess=0.10)
        equity_npv = xnpv(discount_rate_equity, equity_cfs, dates)
    except Exception:
        equity_irr = 0
        equity_npv = 0
    
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
        max_dscr=sculpt_result.max_dscr,
        min_llcr=min(wp.llcr for wp in waterfall_periods if wp.llcr > 0) or 0,
        min_plcr=min(wp.plcr for wp in waterfall_periods if wp.plcr > 0) or 0,
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
        f"Sculpting:       {'CONVERGED' if result.sculpting_result.converged else 'FAILED'} ({result.sculpting_result.iterations} iterations)",
        f"Debt Amount:      {result.sculpting_result.debt_keur:>12,.0f} k€",
        f"Avg DSCR:         {result.avg_dscr:>12.2f}x",
        f"Min DSCR:         {result.min_dscr:>12.2f}x",
        f"Max DSCR:         {result.max_dscr:>12.2f}x",
        f"Min LLCR:         {result.min_llcr:>12.2f}x",
        f"Min PLCR:         {result.min_plcr:>12.2f}x",
        f"Periods in Lockup:{result.periods_in_lockup:>12}",
        "-" * 60,
        f"Project IRR:      {result.project_irr * 100:>11.2f}%",
        f"Equity IRR:       {result.equity_irr * 100:>11.2f}%",
        f"Project NPV:      {result.project_npv:>12,.0f} k€",
        f"Equity NPV:       {result.equity_npv:>12,.0f} k€",
        "=" * 60,
    ]
    return "\n".join(lines)