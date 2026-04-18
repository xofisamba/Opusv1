"""Tax engine - corporate tax calculation with ATAD and loss carryforward.

For Oborovo (Croatia):
- Corporate tax rate: 10%
- ATAD EBITDA limit: 30% (interest deduction limit)
- Loss carryforward: 5 years, 100% cap
- Thin cap applies for related party interest
- Tax is paid annually (every 2nd semester)

Key complexity:
- Fiscal reintegration: pre-COD items (IDC, bank fees) added back to taxable profit
- Losses from prior years reduce current taxable profit
- ATAD limits interest deduction to 30% of EBITDA
"""
from typing import Optional
from dataclasses import dataclass


@dataclass
class TaxResult:
    """Result of tax calculation for a period."""
    period: int
    ebitda_keur: float
    depreciation_keur: float
    interest_keur: float
    fiscal_reintegration_keur: float
    atad_adjustment_keur: float
    loss_cf_applied_keur: float
    taxable_profit_keur: float
    tax_rate: float
    tax_keur: float
    effective_rate: float


def taxable_profit(
    ebitda_keur: float,
    depreciation_keur: float,
    interest_keur: float,
    fiscal_reintegration_keur: float = 0,
    atad_addback_keur: float = 0,
    loss_carryforward_keur: float = 0,
) -> float:
    """Calculate taxable profit.
    
    Taxable Profit = EBITDA - Depreciation - Interest + Fiscal Reintegration + ATAD Adjustment - Loss CF
    
    Args:
        ebitda_keur: EBITDA in kEUR
        depreciation_keur: Depreciation in kEUR
        interest_keur: Deductible interest in kEUR
        fiscal_reintegration_keur: Add-back for non-deductible items
        atad_addback_keur: ATAD adjustment (interest above 30% EBITDA limit)
        loss_carryforward_keur: Prior year losses applied
    
    Returns:
        Taxable profit in kEUR
    """
    profit = ebitda_keur - depreciation_keur - interest_keur
    profit += fiscal_reintegration_keur  # Add back non-deductible items
    profit += atad_addback_keur  # Add back disallowed interest
    profit -= loss_carryforward_keur  # Apply loss carryforward
    
    return max(0, profit)


def tax_liability(
    taxable_profit_keur: float,
    tax_rate: float,
) -> float:
    """Calculate tax liability.
    
    Args:
        taxable_profit_keur: Taxable profit in kEUR
        tax_rate: Tax rate (e.g., 0.10 for 10%)
    
    Returns:
        Tax liability in kEUR
    """
    return max(0, taxable_profit_keur * tax_rate)


def atad_limit(
    ebitda_keur: float,
    atad_ebitda_limit: float = 0.30,
    atad_min_interest_keur: float = 3000.0,
) -> float:
    """Calculate ATAD interest deduction limit.
    
    ATAD (Anti-Tax Avoidance Directive) limits interest deduction to:
    - 30% of EBITDA (before interest and tax)
    - OR minimum threshold (3,000 kEUR for large projects)
    
    The higher of the two limits applies.
    
    Args:
        ebitda_keur: EBITDA in kEUR
        atad_ebitda_limit: ATAD EBITDA limit (default 30%)
        atad_min_interest_keur: Minimum interest threshold
    
    Returns:
        Maximum deductible interest in kEUR
    """
    ebitda_limit = ebitda_keur * atad_ebitda_limit
    
    # ATAD allows the higher of 30% EBITDA limit or 3M EUR threshold
    return max(ebitda_limit, atad_min_interest_keur)


def atad_adjustment(
    interest_keur: float,
    ebitda_keur: float,
    atad_ebitda_limit: float = 0.30,
) -> tuple[float, float]:
    """Calculate ATAD adjustment for excess interest.
    
    Returns:
        Tuple of (deductible_interest, disallowed_interest_addback)
    
    Args:
        interest_keur: Total interest in kEUR
        ebitda_keur: EBITDA in kEUR
        atad_ebitda_limit: ATAD EBITDA limit percentage
    
    Returns:
        (deductible_interest, excess_interest_addback)
    """
    limit = atad_limit(ebitda_keur, atad_ebitda_limit)
    
    if interest_keur <= limit:
        return interest_keur, 0.0
    else:
        # Excess interest is added back to taxable profit
        return limit, interest_keur - limit


def apply_loss_carryforward(
    losses: list[float],
    taxable_profit_keur: float,
    max_years: int = 5,
    cap_pct: float = 1.0,
) -> tuple[float, list[float]]:
    """Apply loss carryforward to current period's taxable profit.
    
    Losses can be carried forward for up to max_years and offset
    up to cap_pct (100%) of current taxable profit.
    
    Args:
        losses: List of historical losses (newest first, i.e., losses[-1] = oldest)
        taxable_profit_keur: Current period taxable profit
        max_years: Maximum carryforward years (default 5)
        cap_pct: Maximum % of current profit that can be offset (1.0 = 100%)
    
    Returns:
        Tuple of (loss_applied, remaining_losses)
    """
    if not losses or taxable_profit_keur <= 0:
        return 0.0, losses
    
    # Cap at max_years
    eligible_losses = losses[:max_years]
    
    # Cap at cap_pct of current profit
    max_offset = taxable_profit_keur * cap_pct
    
    # Apply losses (oldest first - losses[0] is oldest if losses is sorted oldest->newest)
    # But typically losses list is newest first, so we reverse
    sorted_losses = sorted(enumerate(eligible_losses), key=lambda x: x[1])  # oldest first
    
    total_loss = sum(eligible_losses)
    loss_applied = min(max_offset, total_loss)
    
    # Calculate remaining losses
    remaining = total_loss - loss_applied
    
    # Update losses list (simplified - just reduce the oldest)
    if remaining > 0 and eligible_losses:
        new_losses = [remaining] + [0] * (len(eligible_losses) - 1)
    else:
        new_losses = [max(0, l - loss_applied / len(eligible_losses)) for l in eligible_losses]
    
    return loss_applied, new_losses


def loss_carryforward_simple(
    prior_year_losses: list[float],
    current_profit_keur: float,
    years: int = 5,
    cap: float = 1.0,
) -> float:
    """Simple loss carryforward calculation.
    
    Args:
        prior_year_losses: List of losses by year (most recent first)
        current_profit_keur: Current year taxable profit
        years: Carryforward period (default 5)
        cap: Maximum offset as % of profit (default 1.0 = 100%)
    
    Returns:
        Loss amount applied to current profit
    """
    if current_profit_keur <= 0 or not prior_year_losses:
        return 0.0
    
    # Take losses from most recent years first
    available = sum(prior_year_losses[:years])
    max_offset = current_profit_keur * cap
    
    return min(available, max_offset)


def effective_tax_rate(
    tax_keur: float,
    ebitda_keur: float,
) -> float:
    """Calculate effective tax rate.
    
    Args:
        tax_keur: Tax liability in kEUR
        ebitda_keur: EBITDA in kEUR
    
    Returns:
        Effective tax rate (e.g., 0.08 for 8%)
    """
    if ebitda_keur <= 0:
        return 0.0
    return tax_keur / ebitda_keur


def full_tax_schedule(
    ebitda_schedule: list[float],
    depreciation_schedule: list[float],
    interest_schedule: list[float],
    fiscal_reintegration_schedule: list[float],
    tax_rate: float,
    atad_ebitda_limit: float = 0.30,
    loss_cf_initial: list[float] = None,
) -> list[TaxResult]:
    """Calculate full tax schedule over project life.
    
    Args:
        ebitda_schedule: EBITDA per period
        depreciation_schedule: Depreciation per period
        interest_schedule: Interest per period
        fiscal_reintegration_schedule: Fiscal reintegration per period
        tax_rate: Corporate tax rate
        atad_ebitda_limit: ATAD limit percentage
        loss_cf_initial: Initial losses by year
    
    Returns:
        List of TaxResult for each period
    """
    if loss_cf_initial is None:
        loss_cf_initial = []
    
    schedule = []
    accumulated_losses = list(loss_cf_initial)
    
    for period in range(len(ebitda_schedule)):
        ebitda = ebitda_schedule[period]
        depreciation = depreciation_schedule[period] if period < len(depreciation_schedule) else 0
        interest = interest_schedule[period] if period < len(interest_schedule) else 0
        fis_reint = fiscal_reintegration_schedule[period] if period < len(fiscal_reintegration_schedule) else 0
        
        # ATAD adjustment
        deductible_interest, atad_addback = atad_adjustment(interest, ebitda, atad_ebitda_limit)
        
        # Apply loss carryforward
        taxable_before_loss = taxable_profit(
            ebitda, depreciation, deductible_interest, fis_reint, atad_addback, 0
        )
        
        loss_applied, accumulated_losses = apply_loss_carryforward(
            accumulated_losses, taxable_before_loss, max_years=5, cap_pct=1.0
        )
        
        # Final taxable profit
        taxable = max(0, taxable_before_loss - loss_applied)
        
        # Tax
        tax = tax_liability(taxable, tax_rate)
        
        # Effective rate
        eff_rate = effective_tax_rate(tax, ebitda)
        
        schedule.append(TaxResult(
            period=period,
            ebitda_keur=ebitda,
            depreciation_keur=depreciation,
            interest_keur=interest,
            fiscal_reintegration_keur=fis_reint,
            atad_adjustment_keur=atad_addback,
            loss_cf_applied_keur=loss_applied,
            taxable_profit_keur=taxable,
            tax_rate=tax_rate,
            tax_keur=tax,
            effective_rate=eff_rate,
        ))
    
    return schedule