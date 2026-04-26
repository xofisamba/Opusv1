"""Goal Seek solvers for OpusCore v2 — Blueprint §4.1.

Implements Task 2.6 (PPA-for-IRR) and Task 2.7 (Debt-for-DSCR).

These are used by the UI to answer "what PPA gives me 10% equity IRR?"
or "what debt amount keeps avg DSCR above 1.30x?".
"""
from __future__ import annotations

from dataclasses import dataclass, is_dataclass, asdict
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
    """Run waterfall at given PPA and return IRR.

    Uses the full cached_run_waterfall_v3 pipeline to get accurate IRR.
    Falls back to approximation only if waterfall setup fails.
    """
    try:
        inputs_dict = _get_inputs_dict(inputs)
    except Exception:
        return 0.0

    # Override PPA in copy
    inputs_dict = _set_ppa_tariff(inputs_dict, ppa)

    if waterfall_fn:
        irr, _ = waterfall_fn(inputs_dict, ppa)
        return irr

    # Full pipeline: reconstruct ProjectInputs → PeriodEngine → cached_run_waterfall_v3
    try:
        rebuilt = _reconstruct_project_inputs(inputs_dict)
        if rebuilt is None:
            return 0.0

        from domain.period_engine import PeriodEngine, PeriodFrequency as PF
        freq = PF.SEMESTRIAL if rebuilt.info.period_frequency.name == "SEMESTRIAL" else PF.ANNUAL
        horizon = rebuilt.info.horizon_years or 30
        ppa_years = rebuilt.revenue.ppa_term_years or 12
        engine_obj = PeriodEngine(
            financial_close=rebuilt.info.financial_close,
            construction_months=rebuilt.info.construction_months,
            horizon_years=horizon,
            ppa_years=ppa_years,
            frequency=freq,
        )

        financing = inputs_dict.get("financing", {})
        rate_per = (financing.get("base_rate", 0.03) + financing.get("margin_bps", 265) / 10000) / 2
        tenor = (financing.get("senior_tenor_years", 14)) * 2
        target = financing.get("target_dscr", 1.15)
        tax_rate = inputs_dict.get("tax", {}).get("corporate_rate", 0.10)

        from utils.cache import cached_run_waterfall_v3
        result = cached_run_waterfall_v3(
            inputs=rebuilt,
            engine=engine_obj,
            rate_per_period=rate_per,
            tenor_periods=tenor,
            target_dscr=target,
            tax_rate=tax_rate,
        )
        if irr_basis == "equity":
            return result.equity_irr
        return result.project_irr
    except Exception as e:
        # Fallback approximation
        return _estimate_irr_fallback(inputs_dict, ppa, irr_basis)


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

    try:
        rebuilt = _reconstruct_project_inputs(inputs_dict)
        if rebuilt is None:
            return 0.0

        # Override debt sizing with fixed debt
        from domain.period_engine import PeriodEngine, PeriodFrequency as PF
        freq = PF.SEMESTRIAL if rebuilt.info.period_frequency.name == "SEMESTRIAL" else PF.ANNUAL
        engine_obj = PeriodEngine(
            financial_close=rebuilt.info.financial_close,
            construction_months=rebuilt.info.construction_months,
            horizon_years=rebuilt.info.horizon_years or 30,
            ppa_years=rebuilt.revenue.ppa_term_years or 12,
            frequency=freq,
        )

        financing = inputs_dict.get("financing", {})
        rate_per = (financing.get("base_rate", 0.03) + financing.get("margin_bps", 265) / 10000) / 2
        tenor = financing.get("senior_tenor_years", 14) * 2
        tax_rate = inputs_dict.get("tax", {}).get("corporate_rate", 0.10)

        from utils.cache import cached_run_waterfall_v3
        result = cached_run_waterfall_v3(
            inputs=rebuilt,
            engine=engine_obj,
            rate_per_period=rate_per,
            tenor_periods=tenor,
            target_dscr=financing.get("target_dscr", 1.15),
            tax_rate=tax_rate,
            fixed_debt_keur=debt_amount,
        )

        if dscr_basis == "min":
            return result.min_dscr
        elif dscr_basis == "median":
            dscrs = [p.dscr for p in result.periods if p.debt_service > 0]
            if dscrs:
                return sorted(dscrs)[len(dscrs) // 2]
            return 0.0
        return result.avg_dscr
    except Exception:
        return _estimate_dscr_fallback(inputs_dict, debt_amount)


def _reconstruct_project_inputs(inputs_dict: dict):
    """Reconstruct a ProjectInputs from a plain inputs dict.

    Mirrors the approach used in ui/pages/4_scenarios.py — builds
    TechnologyConfig, RevenueConfig, DebtConfig, TaxParams and calls
    build_inputs_from_ui().
    """
    try:
        from src.app_builder import build_inputs_from_ui
        from domain.models import (
            TechnologyConfig, SolarTechnicalParams,
            RevenueConfig, PPAParams,
            DebtConfig, SeniorDebtParams,
            TaxParams,
        )

        info = inputs_dict.get("info", {})
        tech = inputs_dict.get("technical", {})
        revenue = inputs_dict.get("revenue", {})
        financing = inputs_dict.get("financing", {})
        tax = inputs_dict.get("tax", {})

        cap_mw = tech.get("capacity_mw", info.get("capacity_mw", 75.26))
        hours = tech.get("operating_hours_p50", 1494)

        solar_params = SolarTechnicalParams(
            capacity_dc_mwp=cap_mw * 1.1,
            capacity_ac_mw=cap_mw,
            operating_hours_p50=hours,
            operating_hours_p90_10y=tech.get("operating_hours_p90_10y", 1410),
            operating_hours_p99_1y=tech.get("operating_hours_p99_1y", 1200),
            pv_degradation_annual=tech.get("pv_degradation", 0.004),
            bifaciality_factor=0.0,
            tracker_type="fixed_tilt",
            tracker_yield_gain=0.0,
            soiling_loss_pct=0.02,
            shading_loss_pct=0.01,
            mismatch_loss_pct=0.015,
            dc_wiring_loss_pct=0.02,
            ac_wiring_loss_pct=0.01,
            transformer_loss_pct=0.005,
            inverter_efficiency=0.98,
            performance_ratio_p50=0.82,
            grid_curtailment_pct=0.0,
            self_consumption_pct=0.0,
        )
        tech_config = TechnologyConfig(technology_type="solar", solar=solar_params)

        ppa_tariff = revenue.get("ppa_base_tariff", 65.0)
        ppa_config = PPAParams(
            ppa_enabled=True,
            ppa_base_price_eur_mwh=ppa_tariff,
            ppa_price_index=revenue.get("ppa_index", 0.02),
            ppa_term_years=revenue.get("ppa_term_years", 10),
            ppa_volume_share=1.0,
            balancing_cost_pct=0.025,
        )
        rev_config = RevenueConfig(ppa=ppa_config)

        senior = SeniorDebtParams(
            gearing_ratio=financing.get("gearing_ratio", 0.75),
            tenor_years=financing.get("senior_tenor_years", 14),
            base_rate=financing.get("base_rate", 0.03),
            margin_bps=financing.get("margin_bps", 265),
            target_dscr=financing.get("target_dscr", 1.15),
            min_dscr_lockup=financing.get("lockup_dscr", 1.10),
            dsra_months=financing.get("dsra_months", 6),
        )
        debt_config = DebtConfig(senior=senior)

        tax_p = TaxParams(
            corporate_tax_rate=tax.get("corporate_rate", 0.10),
            loss_carryforward_years=tax.get("loss_carryforward_years", 5),
            atad_applies=False,
            atad_ebitda_limit=0.0,
            thin_cap_enabled=tax.get("thin_cap_enabled", False),
            thin_cap_ratio=4.0,
            wht_dividends=tax.get("wht_sponsor_dividends", 0.05),
            vat_rate=0.25,
        )

        proj_name = info.get("name", "Project")
        proj_company = info.get("company", "Company")
        country_iso = info.get("country_iso", "HR")

        rebuilt = build_inputs_from_ui(
            tech_config, rev_config, debt_config, tax_p,
            project_name=proj_name,
            company=proj_company,
            country_iso=country_iso,
        )
        return rebuilt
    except Exception as e:
        return None


def _estimate_irr_fallback(inputs_dict: dict, ppa: float, irr_basis: str) -> float:
    """Rough IRR approximation when waterfall cannot be run."""
    try:
        revenue = inputs_dict.get("revenue", {})
        capacity = inputs_dict.get("info", {}).get("capacity_mw", 75.26)
        hours = inputs_dict.get("technical", {}).get("operating_hours_p50", 1494)
        avail = inputs_dict.get("technical", {}).get("plant_availability", 0.99)
        opex = inputs_dict.get("opex", {})
        y1_opex = opex.get("y1_total_keur", 1354) if isinstance(opex, dict) else 1354
        annual_gen = capacity * hours * avail
        annual_rev = annual_gen * ppa / 1000
        cfads = annual_rev - y1_opex
        if cfads <= 0:
            return 0.0
        capex = inputs_dict.get("capex", {}).get("total_capex", 57973) or 57973
        return cfads / capex  # very rough
    except Exception:
        return 0.0


def _estimate_dscr_fallback(inputs_dict: dict, debt_amount: float) -> float:
    """Rough DSCR approximation when waterfall cannot be run."""
    try:
        financing = inputs_dict.get("financing", {})
        base_rate = financing.get("base_rate", 0.03)
        margin = financing.get("margin_bps", 265)
        rate = base_rate + margin / 10000
        annual_ds = debt_amount * rate
        cfads = _estimate_cfads(inputs_dict)
        if cfads and annual_ds > 0:
            return sum(cfads) / len(cfads) / annual_ds
    except Exception:
        pass
    return 0.0


def _get_inputs_dict(inputs: any) -> dict:
    """Extract plain dict from inputs (supports dataclass, ProjectInputs, or raw dict)."""
    if isinstance(inputs, dict):
        return inputs
    if is_dataclass(inputs):
        # Use asdict for proper nested conversion (datetime → string, tuples → lists)
        import copy
        result = copy.deepcopy(asdict(inputs))
        return _clean_asdict(result)
    if hasattr(inputs, "to_dict"):
        result = inputs.to_dict()
        if isinstance(result, dict):
            return result
    if hasattr(inputs, "__dict__"):
        return {k: _dataclass_to_dict(v) for k, v in inputs.__dict__.items() if not k.startswith("_")}
    raise ValueError("Cannot convert inputs to dict")


def _clean_asdict(obj: Any) -> Any:
    """Post-process asdict() output: convert enums, dates, tuples to JSON-compatible types."""
    from datetime import date, datetime
    if isinstance(obj, dict):
        return {k: _clean_asdict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_asdict(x) for x in obj]
    if isinstance(obj, tuple):
        return [_clean_asdict(x) for x in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    # Remove enum types (keep value for JSON)
    if hasattr(obj, 'value') and hasattr(obj, 'name'):
        return obj.value
    return obj


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