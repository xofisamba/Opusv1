"""Debt sculpting via DSCR constraint.

Debt sculpting sizes debt such that DSCR = target in each period.
Payment[t] = EBITDA[t] / target_dscr
Debt = PV(payments at debt_rate)

This matches Excel's Macro sheet debt sculpting behavior.
"""
# DEPRECATION NOTICE (2026-04-21)
# ================================================================
# Funkcije u ovom modulu (sculpt_debt_dscr, find_debt_for_target_dscr) su
# zastarjele i zamijenjene s iterative_sculpt_debt u sculpting_iterative.py.
#
# Canonical implementacija: domain/financing/sculpting_iterative.py
# Koristi: domain/waterfall/waterfall_engine.py (cached_run_waterfall)
#
# Ove funkcije ostaju ovdje radi backward kompatibilnosti dok se testovi ne ažuriraju.
# ================================================================
import warnings as _warnings
from typing import Optional
from dataclasses import dataclass
from scipy.optimize import brentq


def _sculpt_debt_dscr_deprecation_warning():
    _warnings.warn(
        "sculpt_debt_dscr je deprecated. Koristi iterative_sculpt_debt iz "
        "domain.financing.sculpting_iterative",
        DeprecationWarning,
        stacklevel=3,
    )


@dataclass
class SculptingResult:
    """Result of debt sculpting calculation."""
    debt_keur: float
    payments: list[float]
    dscr_schedule: list[float]
    interest_schedule: list[float]
    principal_schedule: list[float]
    balance_schedule: list[float]


def sculpt_debt_dscr(
    ebitda_schedule: list[float],
    rate_per_period: float,
    tenor_periods: int,
    target_dscr: float = 1.15,
    min_dscr: float = 1.0,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
) -> SculptingResult:
    """Calculate sculpted debt using DSCR-based iterative approach.
    
    .. deprecated::
        Koristi :func:`iterative_sculpt_debt` iz
        :mod:`domain.financing.sculpting_iterative` umjesto ove funkcije.
    
    The sculpting works by:
    1. Assume a debt amount
    2. Calculate payments = EBITDA / target_dscr
    3. Check if PV(payments) matches the debt
    4. Adjust debt until PV = debt
    """
    _sculpt_debt_dscr_deprecation_warning()
    if tenor_periods <= 0 or len(ebitda_schedule) < tenor_periods:
        raise ValueError("Insufficient EBITDA data for tenor")
    
    # Payment = EBITDA / target_dscr for each period
    target_payments = [ebitda / target_dscr for ebitda in ebitda_schedule[:tenor_periods]]
    
    # Debt = PV(payments at debt rate)
    # This gives us the "theoretical" debt for sculpted payments
    debt = sum(
        p / (1 + rate_per_period) ** (t + 1)
        for t, p in enumerate(target_payments)
    )
    
    # Build schedule with this debt
    balance = debt
    payments = []
    dscr_list = []
    interest_list = []
    principal_list = []
    balance_list = []
    
    for period in range(tenor_periods):
        ebitda = ebitda_schedule[period]
        
        # Use target payment
        payment = target_payments[period]
        
        # Interest on opening balance
        interest = balance * rate_per_period
        
        # Principal = payment - interest
        principal = payment - interest
        
        # Ensure balance doesn't go negative
        if principal > balance:
            principal = balance
            payment = interest + principal
        
        closing = max(0, balance - principal)
        
        # DSCR = EBITDA / payment
        actual_dscr = ebitda / payment if payment > 0 else 0
        
        payments.append(payment)
        dscr_list.append(actual_dscr)
        interest_list.append(interest)
        principal_list.append(principal)
        balance_list.append(balance)
        
        balance = closing
    
    return SculptingResult(
        debt_keur=debt,
        payments=payments,
        dscr_schedule=dscr_list,
        interest_schedule=interest_list,
        principal_schedule=principal_list,
        balance_schedule=balance_list,
    )


def find_debt_for_target_dscr(
    ebitda_schedule: list[float],
    rate_per_period: float,
    tenor_periods: int,
    target_dscr: float,
    debt_bounds: tuple[float, float] = (10000, 100000),
) -> float:
    """Find the debt amount that produces exactly target_dscr average.
    
    Uses binary search to find debt amount.
    
    Args:
        ebitda_schedule: List of EBITDA values
        rate_per_period: Interest rate per period
        tenor_periods: Number of periods
        target_dscr: Target DSCR
        debt_bounds: Search bounds for debt (kEUR)
    
    Returns:
        Debt amount in kEUR
    """
    def avg_dscr(debt: float) -> float:
        """Calculate average DSCR for a given debt amount."""
        result = sculpt_debt_dscr(
            ebitda_schedule,
            rate_per_period,
            tenor_periods,
            target_dscr,
        )
        # Return average DSCR (excluding periods with very small balances)
        valid_dsrs = [d for d in result.dscr_schedule if d > 0.5]
        return sum(valid_dsrs) / len(valid_dsrs) if valid_dsrs else 0
    
    # Binary search for debt that gives target average DSCR
    low, high = debt_bounds
    
    for _ in range(50):
        mid = (low + high) / 2
        dscr = avg_dscr(mid)
        
        if abs(dscr - target_dscr) < 0.001:
            return mid
        
        if dscr < target_dscr:
            # Need more debt to reduce DSCR (lower payments relative to EBITDA)
            low = mid
        else:
            high = mid
    
    return (low + high) / 2


def dscr_at_period(
    ebitda_keur: float,
    debt_service_keur: float,
) -> float:
    """Calculate DSCR for a single period.
    
    Args:
        ebitda_keur: EBITDA in kEUR
        debt_service_keur: Debt service (interest + principal) in kEUR
    
    Returns:
        DSCR (e.g., 1.15)
    """
    if debt_service_keur <= 0:
        return float('inf')
    return ebitda_keur / debt_service_keur


def average_dscr(
    ebitda_schedule: list[float],
    debt_service_schedule: list[float],
) -> float:
    """Calculate average DSCR over schedule.
    
    Args:
        ebitda_schedule: List of EBITDA values
        debt_service_schedule: List of debt service values
    
    Returns:
        Average DSCR
    """
    dsrs = [
        dscr_at_period(ebitda, ds)
        for ebitda, ds in zip(ebitda_schedule, debt_service_schedule)
        if ds > 0
    ]
    
    return sum(dsrs) / len(dsrs) if dsrs else 0


def min_dscr(
    ebitda_schedule: list[float],
    debt_service_schedule: list[float],
) -> float:
    """Calculate minimum DSCR over schedule.
    
    Args:
        ebitda_schedule: List of EBITDA values
        debt_service_schedule: List of debt service values
    
    Returns:
        Minimum DSCR
    """
    dsrs = [
        dscr_at_period(ebitda, ds)
        for ebitda, ds in zip(ebitda_schedule, debt_service_schedule)
        if ds > 0
    ]
    
    return min(dsrs) if dsrs else 0