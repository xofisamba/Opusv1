"""Financing module - debt scheduling, sculpting, and covenants.

Canonical implementations:
- iterative_sculpt_debt (sculpting_iterative.py) — used by waterfall engine
- standard_amortization (schedule.py) — used in charts/outputs
"""
from domain.financing.schedule import (
    AmortizationResult,
    DebtServiceResult,
    senior_debt_amount,
    standard_amortization,
    annuity_payment,
    balance_after_n_periods,
    sculpted_amortization,  # still used in tests/charts
)
from domain.financing.sculpting_iterative import (
    iterative_sculpt_debt,
    IterativeSculptResult,
    dscr_at_period,
    average_dscr,
    min_dscr,
)
from domain.financing.covenants import dscr, llcr, plcr

__all__ = [
    # Active
    "AmortizationResult",
    "DebtServiceResult",
    "senior_debt_amount",
    "standard_amortization",
    "annuity_payment",
    "balance_after_n_periods",
    "iterative_sculpt_debt",
    "IterativeSculptResult",
    # DSCR utilities (moved from deprecated sculpting.py)
    "dscr_at_period",
    "average_dscr",
    "min_dscr",
    # Deprecated but still used
    "sculpted_amortization",
    # Covenants
    "dscr",
    "llcr",
    "plcr",
]
