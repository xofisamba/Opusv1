"""Financing module - debt scheduling, sculpting, and covenants.

Canonical implementations:
- iterative_sculpt_debt (sculpting_iterative.py) — used by waterfall engine
- standard_amortization (schedule.py) — used in charts/outputs

Deprecated (do not use in new code):
- sculpt_debt_dscr (sculpting.py) — superseded by iterative_sculpt_debt
- sculpted_amortization (schedule.py) — superseded by iterative_sculpt_debt
"""
from domain.financing.schedule import (
    AmortizationResult,
    DebtServiceResult,
    senior_debt_amount,
    standard_amortization,
    annuity_payment,
    balance_after_n_periods,
    # Deprecated:
    sculpted_amortization,
)
from domain.financing.sculpting import sculpt_debt_dscr, dscr_at_period, average_dscr, min_dscr
from domain.financing.sculpting_iterative import iterative_sculpt_debt, IterativeSculptResult
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
    # Deprecated (still exported for backward compatibility)
    "sculpted_amortization",
    "sculpt_debt_dscr",
    # Covenants
    "dscr",
    "llcr",
    "plcr",
    "dscr_at_period",
    "average_dscr",
    "min_dscr",
]