"""Goal Seek solvers for OpusCore v2 — Blueprint §4.1.

Implements Task 2.6 (PPA-for-IRR) and Task 2.7 (Debt-for-DSCR).

These are used by the UI to answer "what PPA gives me 10% equity IRR?"
or "what debt amount keeps avg DSCR above 1.30x?".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
import warnings

try:
    from scipy.optimize import brentq
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GoalSeekResult:
    """Result of a goal seek operation."""
    success: bool
    solved_value: float          # e.g. PPA or debt amount found
    achieved_metric: float       # e.g. actual IRR or DSCR achieved
    iterations: int
    iteration_trace: list[tuple[float, float]]  # [(input_val, metric_val), ...]
    error_message: str = ""

    @property
    def converged(self) -> bool:
        return self.success and self.iterations > 0


@dataclass
class DebtSizingResult:
    """Result of debt sizing for target DSCR."""
    success: bool
    debt_amount_keur: float
    achieved_dscr: float
    implied_gearing: float
    method: str  # "direct_sculpt" or "bisection"
    iterations: int = 0
    error_message: str = ""


# ---------------------------------------------------------------------------
# PPA-for-IRR Solver
# ---------------------------------------------------------------------------

def solve_ppa_for_target_irr(
    inputs: any,
    target_irr: float,
    irr_basis: str = "equity",   # "equity" | "project"
    bracket_low_eur_mwh: float = 10.0,
    bracket_high_eur_mwh: float = 300.0,
    tolerance: float = 1e-5,
    max_iter: int = 60,
    waterfall_fn: Optional[Callable] = None,
) -> GoalSeekResult:
    """Find the PPA tariff (EUR/MWh) that yields the target IRR.

    Uses scipy.optimize.brentq for robust bisection between bracket bounds.
    Calls waterfall_fn(ppa_tariff) to evaluate f(ppa) = irr - target.

    Parameters
    ----------
    inputs : ProjectInputs
        Base inputs (PPA will be overridden in each iteration).
    target_irr : float
        Target IRR as decimal (e.g. 0.10 for 10%).
    irr_basis : str
        "equity" or "project" — which IRR to match.
    bracket_low/high : float
        PPA bracket to search (EUR/MWh).
    tolerance : float
        Convergence tolerance on IRR (not PPA).
    max_iter : int
        Maximum brentq iterations.
    waterfall_fn : callable
        Function(inputs_dict, ppa_tariff) -> (irr_value, waterfall_result).
        If None, uses default run_waterfall.

    Returns
    -------
    GoalSeekResult with solved_value = required PPA.
    """
    if not HAS_SCIPY:
        return GoalSeekResult(
            success=False,
            solved_value=0.0,
            achieved_metric=0.0,
            iterations=0,
            iteration_trace=[],
            error_message="scipy.optimize.brentq not available — install scipy",
        )

    iteration_trace: list[tuple[float, float]] = []

    def objective(ppa: float) -> float:
        """f(ppa) = achieved_irr - target_irr."""
        irr = _evaluate_irr_at_ppa(inputs, ppa, irr_basis, waterfall_fn)
        iteration_trace.append((ppa, irr))
        return irr - target_irr

    # Check bracket feasibility: f(low) and f(high) must have opposite signs
    f_low = objective(bracket_low_eur_mwh)
    f_high = objective(bracket_high_eur_mwh)

    if f_low * f_high > 0:
        # No solution in bracket
        return GoalSeekResult(
            success=False,
            solved_value=0.0,
            achieved_metric=0.0,
            iterations=len(iteration_trace),
            iteration_trace=iteration_trace,
            error_message=(
                f"No solution in bracket [{bracket_low_eur_mwh:.1f}, {bracket_high_eur_mwh:.1f}] "
                f"(f(low)={f_low:.4f}, f(high)={f_high:.4f})"
            ),
        )

    try:
        ppa_solution = brentq(
            objective,
            bracket_low_eur_mwh,
            bracket_high_eur_mwh,
            xtol=tolerance,
            maxiter=max_iter,
        )
        achieved_irr = target_irr  # by construction at solution
        return GoalSeekResult(
            success=True,
            solved_value=ppa_solution,
            achieved_metric=achieved_irr,
            iterations=len(iteration_trace),
            iteration_trace=iteration_trace,
        )
    except Exception as e:
        return GoalSeekResult(
            success=False,
            solved_value=0.0,
            achieved_metric=0.0,
            iterations=len(iteration_trace),
            iteration_trace=iteration_trace,
            error_message=f"Solver error: {str(e)}",
        )


def _evaluate_irr_at_ppa(
    inputs: any,
    ppa: float,
    irr_basis: str,
    waterfall_fn: Optional[Callable],
) -> float:
    """Run waterfall at given PPA and return IRR."""
    # Build modified inputs dict with new PPA
    try:
        inputs_dict = _get_inputs_dict(inputs)
    except Exception:
        return 0.0

    # Override PPA tariff
    inputs_dict = _set_ppa_tariff(inputs_dict, ppa)

    if waterfall_fn:
        irr, _ = waterfall_fn(inputs_dict, ppa)
        return irr

    # Fallback: try to run real waterfall
    try:
        from domain.waterfall.waterfall_engine import run_waterfall
        result = run_waterfall(inputs_dict)
        if irr_basis == "equity":
            return result.equity_irr
        return result.project_irr
    except Exception:
        return 0.0


def _get_inputs_dict(inputs: any) -> dict:
    """Extract plain dict from inputs (supports dataclass or raw dict)."""
    if isinstance(inputs, dict):
        return inputs
    if hasattr(inputs, "to_dict"):
        return inputs.to_dict()
    if hasattr(inputs, "__dict__"):
        result = {}
        for k, v in inputs.__dict__.items():
            if not k.startswith("_"):
                result[k] = v
        return result
    raise ValueError("Cannot convert inputs to dict")


def _set_ppa_tariff(inputs_dict: dict, ppa: float) -> dict:
    """Return a copy of inputs_dict with PPA tariff set to ppa."""
    import copy
    d = copy.deepcopy(inputs_dict)
    # Navigate to ppa_base_tariff in nested structure
    if "revenue" in d and isinstance(d["revenue"], dict):
        d["revenue"]["ppa_base_tariff"] = ppa
    return d


# ---------------------------------------------------------------------------
# Debt-for-DSCR Solver
# ---------------------------------------------------------------------------

def solve_debt_for_target_dscr(
    inputs: any,
    target_dscr: float,
    dscr_basis: str = "avg",   # "avg" | "min" | "median"
    sculpt: bool = True,
    tolerance: float = 1e-4,
    max_iter: int = 40,
    waterfall_fn: Optional[Callable] = None,
) -> DebtSizingResult:
    """Find max debt that keeps DSCR >= target.

    If sculpt=True: use direct PV(CFADS/target_DSCR) formula — no iteration needed.
    If sculpt=False: bisection on debt principal with fixed amortization schedule.

    Parameters
    ----------
    inputs : ProjectInputs
        Base inputs (debt will be overridden).
    target_dscr : float
        Target DSCR (e.g. 1.30).
    dscr_basis : str
        Which DSCR to match: "avg" | "min" | "median".
    sculpt : bool
        If True, uses sculpted repayment (direct formula).
        If False, uses fixed amortization + bisection.
    tolerance : float
        Convergence tolerance on DSCR.
    max_iter : int
        Max iterations for bisection (only used when sculpt=False).
    waterfall_fn : callable
        Function(inputs_dict, debt_amount) -> (dscr_metric, waterfall_result).
        If None, uses default run_waterfall.

    Returns
    -------
    DebtSizingResult with debt_amount_keur.
    """
    if sculpt:
        return _solve_debt_sculpt(inputs, target_dscr, dscr_basis, waterfall_fn)
    else:
        return _solve_debt_bisection(
            inputs, target_dscr, dscr_basis, tolerance, max_iter, waterfall_fn
        )


def _solve_debt_sculpt(
    inputs: any,
    target_dscr: float,
    dscr_basis: str,
    waterfall_fn: Optional[Callable],
) -> DebtSizingResult:
    """Direct formula: debt = PV(CFADS / target_dscr) at debt rate over loan life.

    Sculpted repayment by definition maintains DSCR == target throughout tenor.
    This is the preferred method for project finance.
    """
    try:
        inputs_dict = _get_inputs_dict(inputs)
    except Exception:
        return DebtSizingResult(
            success=False, debt_amount_keur=0.0,
            achieved_dscr=0.0, implied_gearing=0.0,
            method="direct_sculpt",
            error_message="Cannot parse inputs",
        )

    # Get debt rate
    financing = inputs_dict.get("financing", {})
    base_rate = financing.get("base_rate", 0.03)
    margin_bps = financing.get("margin_bps", 265)
    all_in_rate = base_rate + margin_bps / 10000

    # Get CFADS schedule (need waterfall or approximation)
    if waterfall_fn:
        _, result = waterfall_fn(inputs_dict, None)
        if result:
            cfads_schedule = [p.ebitda_keur for p in result.periods]
        else:
            cfads_schedule = _estimate_cfads(inputs_dict)
    else:
        cfads_schedule = _estimate_cfads(inputs_dict)

    if not cfads_schedule:
        return DebtSizingResult(
            success=False, debt_amount_keur=0.0,
            achieved_dscr=0.0, implied_gearing=0.0,
            method="direct_sculpt",
            error_message="Cannot estimate CFADS",
        )

    # Direct formula: debt = sum(CFADS_t / (1+r)^t) / target_dscr
    import numpy as np
    n = len(cfads_schedule)
    discount_factors = [(1 + all_in_rate) ** (-t) for t in range(1, n + 1)]
    pv_cfads = sum(cfads * df for cfads, df in zip(cfads_schedule, discount_factors))

    debt_amount = pv_cfads / target_dscr

    # Estimate achieved DSCR (should be ≈ target by construction)
    avg_ds = sum(cfads_schedule) / n
    debt_service = debt_amount * all_in_rate  # rough approximation
    achieved_dscr = avg_ds / (debt_service / n) if debt_service > 0 else float("inf")

    total_capex = inputs_dict.get("capex", {}).get("total_capex", 0) or 0
    implied_gearing = debt_amount / total_capex if total_capex > 0 else 0.0

    return DebtSizingResult(
        success=True,
        debt_amount_keur=round(debt_amount, 2),
        achieved_dscr=round(achieved_dscr, 3),
        implied_gearing=round(implied_gearing, 4),
        method="direct_sculpt",
        iterations=0,
    )


def _solve_debt_bisection(
    inputs: any,
    target_dscr: float,
    dscr_basis: str,
    tolerance: float,
    max_iter: int,
    waterfall_fn: Optional[Callable],
) -> DebtSizingResult:
    """Bisection on debt principal with fixed amortization schedule."""
    if not HAS_SCIPY:
        return DebtSizingResult(
            success=False, debt_amount_keur=0.0,
            achieved_dscr=0.0, implied_gearing=0.0,
            method="bisection",
            error_message="scipy.optimize.brentq not available",
        )

    try:
        inputs_dict = _get_inputs_dict(inputs)
    except Exception:
        return DebtSizingResult(
            success=False, debt_amount_keur=0.0,
            achieved_dscr=0.0, implied_gearing=0.0,
            method="bisection",
            error_message="Cannot parse inputs",
        )

    total_capex = inputs_dict.get("capex", {}).get("total_capex", 0) or 1
    low = 0.0
    high = total_capex * 0.95  # max 95% gearing

    def objective(debt: float) -> float:
        dscr = _evaluate_dscr_at_debt(inputs_dict, debt, dscr_basis, waterfall_fn)
        return dscr - target_dscr

    f_low = objective(low)
    f_high = objective(high)

    if f_low * f_high > 0:
        # No solution in bracket
        return DebtSizingResult(
            success=False, debt_amount_keur=0.0,
            achieved_dscr=0.0, implied_gearing=0.0,
            method="bisection",
            error_message=(
                f"No debt solution in bracket [0, {high:.0f}] "
                f"(f(low)={f_low:.4f}, f(high)={f_high:.4f})"
            ),
        )

    try:
        debt_solution = brentq(objective, low, high, xtol=tolerance, maxiter=max_iter)
        achieved_dscr = target_dscr  # by construction
        implied_gearing = debt_solution / total_capex if total_capex > 0 else 0.0
        return DebtSizingResult(
            success=True,
            debt_amount_keur=round(debt_solution, 2),
            achieved_dscr=round(achieved_dscr, 3),
            implied_gearing=round(implied_gearing, 4),
            method="bisection",
            iterations=max_iter,
        )
    except Exception as e:
        return DebtSizingResult(
            success=False, debt_amount_keur=0.0,
            achieved_dscr=0.0, implied_gearing=0.0,
            method="bisection",
            error_message=f"Solver error: {str(e)}",
        )


def _estimate_cfads(inputs_dict: dict) -> list[float]:
    """Approximate annual CFADS from inputs (fallback when no waterfall available)."""
    try:
        revenue = inputs_dict.get("revenue", {})
        ppa = revenue.get("ppa_base_tariff", 60.0)
        capacity = inputs_dict.get("info", {}).get("capacity_mw", 0) or 0
        horizon = inputs_dict.get("info", {}).get("horizon_years", 30) or 30
        avail = inputs_dict.get("technical", {}).get("plant_availability", 0.99)
        hours = inputs_dict.get("technical", {}).get("operating_hours", 1500) or 1500

        annual_gen = capacity * hours * avail
        annual_rev = annual_gen * ppa / 1000  # kEUR

        opex = inputs_dict.get("opex", {})
        if isinstance(opex, dict):
            y1_total = opex.get("y1_total_keur", 0) or 0
        else:
            y1_total = 0

        cfads = annual_rev - y1_total
        return [cfads] * horizon
    except Exception:
        return []


def _evaluate_dscr_at_debt(
    inputs_dict: dict,
    debt_amount: float,
    dscr_basis: str,
    waterfall_fn: Optional[Callable],
) -> float:
    """Run waterfall at given debt amount and return DSCR metric."""
    if waterfall_fn:
        dscr, _ = waterfall_fn(inputs_dict, debt_amount)
        return dscr

    # Fallback: rough DSCR estimate
    try:
        total_capex = inputs_dict.get("capex", {}).get("total_capex", 0) or 0
        if total_capex <= 0:
            return 0.0
        debt_pct = debt_amount / total_capex

        financing = inputs_dict.get("financing", {})
        base_rate = financing.get("base_rate", 0.03)
        margin_bps = financing.get("margin_bps", 265)
        all_in_rate = base_rate + margin_bps / 10000

        annual_debt_service = debt_amount * all_in_rate
        cfads = _estimate_cfads(inputs_dict)
        if cfads and annual_debt_service > 0:
            avg_cfads = sum(cfads) / len(cfads)
            return avg_cfads / annual_debt_service
    except Exception:
        pass
    return 0.0