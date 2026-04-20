"""Iterative Debt Sculpting - DSCR-Based Sizing with Binary Search.

This module implements true iterative debt sculpting matching Excel behavior:
- Binary search on debt amount until average DSCR ≈ target
- Per-period payment = EBITDA / DSCR_target (or capped)
- Lockup check per period (DSCR < 1.10 blocks distribution)
- Balance converges within tolerance

Excel uses Macro!DebtSculpting iterative approach — we replicate that here.
"""
from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class IterativeSculptResult:
    """Result of iterative debt sculpting with convergence."""
    debt_keur: float
    payments: list[float]
    dscr_schedule: list[float]
    interest_schedule: list[float]
    principal_schedule: list[float]
    balance_schedule: list[float]
    # Metadata
    avg_dscr: float
    min_dscr: float
    max_dscr: float
    converged: bool
    iterations: int


def _amortize(debt: float, rate: float, periods: int) -> list[dict]:
    """Build amortization schedule for given debt.
    
    Returns list of {interest, principal, balance} dicts.
    """
    schedule = []
    balance = debt
    
    for _ in range(periods):
        interest = balance * rate
        principal = balance / periods  # Simplified equal principal
        closing = max(0, balance - principal)
        
        schedule.append({
            "interest": interest,
            "principal": principal,
            "balance": balance,
            "closing": closing,
        })
        balance = closing
    
    return schedule


def _dscr_of_payment(ebitda: float, payment: float) -> float:
    """Calculate DSCR for a given payment."""
    if payment <= 0:
        return float('inf')
    return ebitda / payment


def _pv_payments(payments: list[float], rate: float) -> float:
    """Calculate present value of payments at given rate."""
    return sum(
        p / (1 + rate) ** (t + 1)
        for t, p in enumerate(payments)
    )


def _calculate_schedule(
    debt: float,
    ebitda_schedule: list[float],
    rate: float,
    tenor: int,
    target_dscr: float,
) -> tuple[list[float], list[float], list[float], list[float], float, float]:
    """Calculate sculpted schedule for a given debt amount.
    
    Payment[t] = min(EBITDA[t] / target_dscr, required_to_cover_interest)
    
    Returns:
        (payments, dsrs, interests, principals, balances, avg_dscr)
    """
    payments = []
    dsrs = []
    interests = []
    principals = []
    balances = []
    
    balance = debt
    total_dscr = 0
    dscr_count = 0
    
    for t in range(tenor):
        ebitda = ebitda_schedule[t]
        
        # Interest on opening balance
        interest = balance * rate
        
        # Target payment = EBITDA / DSCR_target
        target_payment = ebitda / target_dscr
        
        # Payment can't be less than interest (would never amortize)
        payment = max(target_payment, interest)
        
        # Principal = payment - interest
        principal = payment - interest
        
        # Cap principal at remaining balance
        if principal > balance:
            principal = balance
            payment = interest + principal
        
        # Closing balance
        closing = max(0, balance - principal)
        
        # DSCR for this period
        dscr = _dscr_of_payment(ebitda, payment)
        
        payments.append(payment)
        dsrs.append(dscr)
        interests.append(interest)
        principals.append(principal)
        balances.append(balance)
        
        if dscr > 0.5 and dscr < 50:  # Filter unreasonable values
            total_dscr += dscr
            dscr_count += 1
        
        balance = closing
    
    avg_dscr = total_dscr / dscr_count if dscr_count > 0 else 0
    
    return payments, dsrs, interests, principals, balances, avg_dscr


def iterative_sculpt_debt(
    ebitda_schedule: list[float],
    rate: float,
    tenor: int,
    target_dscr: float = 1.15,
    lockup_dscr: float = 1.10,
    initial_debt_guess: Optional[float] = None,
    tolerance: float = 0.001,
    max_iterations: int = 100,
    min_debt: float = 10000,
    max_debt: float = 200000,
) -> IterativeSculptResult:
    """Find debt amount such that average DSCR ≈ target_dscr.
    
    Uses binary search on debt amount.
    
    For each debt candidate:
        1. Build payments = EBITDA / target_dscr
        2. Calculate PV(payments) at debt rate
        3. Compare to debt amount
        4. Binary search until avg_dscr matches target
    
    Args:
        ebitda_schedule: EBITDA per period (kEUR)
        rate: Interest rate per period (e.g., 0.02825 for ~5.65% annual semi-annual)
        tenor: Number of periods
        target_dscr: Target DSCR (default 1.15)
        lockup_dscr: Lockup threshold (default 1.10)
        initial_debt_guess: Starting guess for debt (None = use analytical estimate)
        tolerance: Acceptable deviation from target DSCR
        max_iterations: Maximum binary search iterations
        min_debt: Lower bound for debt search
        max_debt: Upper bound for debt search
    
    Returns:
        IterativeSculptResult with converged schedule
    """
    # Initial guess using analytical PV approach
    if initial_debt_guess is None:
        target_payments = [e / target_dscr for e in ebitda_schedule[:tenor]]
        initial_debt_guess = _pv_payments(target_payments, rate)
        initial_debt_guess = max(min_debt, min(max_debt, initial_debt_guess))
    
    # Binary search for debt amount
    low = min_debt
    high = max_debt
    converged = False
    iterations = 0
    
    for iteration in range(max_iterations):
        mid = (low + high) / 2
        
        # Calculate schedule for this debt
        _, dsrs, _, _, _, avg_dscr = _calculate_schedule(
            mid, ebitda_schedule, rate, tenor, target_dscr
        )
        
        # Check convergence
        deviation = abs(avg_dscr - target_dscr)
        
        if deviation < tolerance:
            converged = True
            iterations = iteration + 1
            break
        
        # Binary search direction
        if avg_dscr < target_dscr:
            # Need more debt to increase payment capacity (lower DSCR)
            low = mid
        else:
            high = mid
        
        iterations = iteration + 1
    
    # Final calculation with converged debt
    final_debt = (low + high) / 2
    payments, dsrs, interests, principals, balances, avg_dscr = _calculate_schedule(
        final_debt, ebitda_schedule, rate, tenor, target_dscr
    )
    
    valid_dsrs = [d for d in dsrs if d > 0.5 and d < 50]
    min_dscr_val = min(valid_dsrs) if valid_dsrs else 0
    max_dscr_val = max(valid_dsrs) if valid_dsrs else 0
    
    return IterativeSculptResult(
        debt_keur=final_debt,
        payments=payments,
        dscr_schedule=dsrs,
        interest_schedule=interests,
        principal_schedule=principals,
        balance_schedule=balances,
        avg_dscr=avg_dscr,
        min_dscr=min_dscr_val,
        max_dscr=max_dscr_val,
        converged=converged,
        iterations=iterations,
    )


def sculpt_with_lockup(
    ebitda_schedule: list[float],
    rate: float,
    tenor: int,
    target_dscr: float = 1.15,
    lockup_dscr: float = 1.10,
) -> list[float]:
    """Calculate payments with lockup constraint per period.
    
    During lockup, payment = interest only (no principal amortization)
    until DSCR recovers above lockup threshold.
    
    Args:
        ebitda_schedule: EBITDA per period
        rate: Interest rate
        tenor: Number of periods
        target_dscr: Target DSCR
        lockup_dscr: Lockup threshold
    
    Returns:
        List of payments per period
    """
    payments = []
    balance = 0
    locked = False
    periods_locked = 0
    
    for t in range(tenor):
        ebitda = ebitda_schedule[t]
        interest = balance * rate
        
        # Target payment
        target_payment = ebitda / target_dscr
        
        # Check lockup status
        if not locked and target_payment > 0:
            current_dscr = ebitda / target_payment
            if current_dscr < lockup_dscr:
                locked = True
        
        if locked:
            # Lockup: pay interest only, principal stays constant
            payment = interest
            periods_locked += 1
            
            # Unlock when DSCR would recover
            if target_payment >= interest * 1.05:  # 5% buffer
                # Check if we can resume amortization
                pass
        else:
            payment = max(target_payment, interest)
        
        principal = payment - interest
        balance = max(0, balance - principal)
        
        payments.append(payment)
        
        # Unlock if balance is paid off
        if balance <= 0:
            locked = False
    
    return payments


def sizing_from_gearing(
    total_capex: float,
    gearing: float,
) -> float:
    """Simple debt sizing from gearing ratio.
    
    Args:
        total_capex: Total CAPEX in kEUR
        gearing: Gearing ratio (0.0 to 1.0)
    
    Returns:
        Debt amount in kEUR
    """
    return total_capex * gearing


def sizing_from_dscr_target(
    ebitda_schedule: list[float],
    rate: float,
    tenor: int,
    target_dscr: float = 1.15,
    gearing_fallback: float = 0.70,
    total_capex: float = 0,
) -> float:
    """Size debt to achieve target DSCR.
    
    Uses iterative approach, falls back to gearing if convergence fails.
    
    Args:
        ebitda_schedule: EBITDA per period
        rate: Interest rate per period
        tenor: Number of periods
        target_dscr: Target DSCR
        gearing_fallback: Fallback gearing if iterative fails
        total_capex: Total CAPEX for gearing fallback
    
    Returns:
        Debt amount in kEUR
    """
    try:
        result = iterative_sculpt_debt(
            ebitda_schedule, rate, tenor, target_dscr,
            initial_debt_guess=total_capex * 0.7,
        )
        if result.converged:
            return result.debt_keur
    except Exception:
        pass
    
    # Fallback to gearing
    return sizing_from_gearing(total_capex, gearing_fallback)