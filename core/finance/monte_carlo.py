"""Monte Carlo simulation and Cash-at-Risk (Tasks 3.7–3.8).

Uses numpy for random sampling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np

from domain.inputs import ProjectInputs, OpexItem
from domain.period_engine import PeriodEngine, PeriodFrequency
from utils.cache import cached_run_waterfall_v3
from dataclasses import replace as dc_replace


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation result."""
    n_iterations: int
    equity_irr_distribution: list[float]
    project_irr_distribution: list[float]
    min_dscr_distribution: list[float]
    p10_equity_irr: float
    p50_equity_irr: float
    p90_equity_irr: float
    prob_dscr_below_1: float
    prob_dscr_below_110: float


@dataclass
class CashAtRiskResult:
    """Cash-at-Risk result: E[distributions] − VaR_alpha(distr)."""
    expected_distributions_keur: float
    var_95_keur: float
    cash_at_risk_keur: float
    confidence_level: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_single_iteration(
    inputs: ProjectInputs,
    seed: int,
    ppa_sigma: float,
    gen_sigma: float,
    capex_sigma: float,
    opex_sigma: float,
) -> tuple[float, float, float]:
    """Run one Monte Carlo iteration, return (equity_irr, project_irr, min_dscr)."""
    rng = np.random.default_rng(seed)

    # ── 1. PPA tariff ──────────────────────────────────────────────────
    ppa_base = inputs.revenue.ppa_base_tariff
    ppa_tariff = rng.normal(ppa_base, ppa_sigma)

    # ── 2. Generation (capacity × hours) ────────────────────────────────
    cap_mw = inputs.technical.capacity_mw
    hours_p50 = inputs.technical.operating_hours_p50
    # generation = capacity × hours × rng_factor
    # σ = (P50 - P90) / 1.28
    p90_hours = getattr(inputs.technical, 'operating_hours_p90_10y', hours_p50 * 0.85)
    gen_sigma_abs = (hours_p50 - p90_hours) / 1.28
    generation_factor = rng.normal(1.0, gen_sigma_abs / hours_p50)
    gen_amount = cap_mw * hours_p50 * generation_factor  # MWh

    # ── 3. CAPEX ──────────────────────────────────────────────────────
    from core.finance.sensitivity import _scale_capex
    capex_total = inputs.capex.total_capex
    capex_scaled = capex_total * rng.normal(1.0, capex_sigma)
    capex_factor = capex_scaled / capex_total
    capex_modified = _scale_capex(inputs.capex, capex_factor)

    # ── 4. OPEX ───────────────────────────────────────────────────────
    from core.finance.sensitivity import _scale_opex
    opex_modified = _scale_opex(inputs.opex, rng.normal(1.0, opex_sigma))

    # ── 5. Build modified inputs ──────────────────────────────────────
    mod_rev = dc_replace(inputs.revenue, ppa_base_tariff=max(ppa_tariff, 0.001))
    mod_inputs = dc_replace(
        inputs,
        revenue=mod_rev,
        capex=capex_modified,
        opex=opex_modified,
    )

    # ── 6. Run waterfall ──────────────────────────────────────────────
    engine = PeriodEngine(
        financial_close=mod_inputs.info.financial_close,
        construction_months=mod_inputs.info.construction_months,
        horizon_years=mod_inputs.info.horizon_years,
        ppa_years=mod_inputs.revenue.ppa_term_years,
        frequency=PeriodFrequency.SEMESTRIAL,
    )
    rate = mod_inputs.financing.all_in_rate / 2
    tenor_periods = mod_inputs.financing.senior_tenor_years * 2
    result = cached_run_waterfall_v3(
        inputs=mod_inputs,
        engine=engine,
        rate_per_period=rate,
        tenor_periods=tenor_periods,
        target_dscr=mod_inputs.financing.target_dscr,
        lockup_dscr=mod_inputs.financing.lockup_dscr,
        tax_rate=mod_inputs.tax.corporate_rate,
        dsra_months=mod_inputs.financing.dsra_months,
        shl_amount=mod_inputs.financing.shl_amount_keur,
        shl_rate=mod_inputs.financing.shl_rate,
        discount_rate_project=0.0641,
        discount_rate_equity=0.0965,
        fixed_debt_keur=None,
    )

    equity_irr = getattr(result, 'equity_irr', 0.0) or 0.0
    project_irr = getattr(result, 'project_irr', 0.0) or 0.0
    min_dscr = getattr(result, 'min_dscr', 0.0) or 0.0

    return equity_irr, project_irr, min_dscr


# ---------------------------------------------------------------------------
# Task 3.7 — Monte Carlo
# ---------------------------------------------------------------------------

def run_monte_carlo(
    inputs: ProjectInputs,
    n_iterations: int = 1000,
    seed: int | None = None,
) -> MonteCarloResult:
    """Run Monte Carlo simulation with default distributions.

    Default distributions:
        PPA tariff:  Normal(base, base × 0.10)
        Generation: Normal(P50, (P50-P90) / 1.28)
        CAPEX:      Normal(base, base × 0.07)
        OPEX:       Normal(base, base × 0.08)

    Args:
        inputs: Base ProjectInputs
        n_iterations: Number of MC iterations (default 1000)
        seed: Optional random seed for reproducibility
    """
    if seed is not None:
        np.random.seed(seed)

    ppa_base = inputs.revenue.ppa_base_tariff
    cap_mw = inputs.technical.capacity_mw
    hours_p50 = inputs.technical.operating_hours_p50
    capex_base = inputs.capex.total_capex

    ppa_sigma = ppa_base * 0.10
    capex_sigma = 0.07
    opex_sigma = 0.08
    # Generation sigma as fraction of capacity
    p90_hours = getattr(inputs.technical, 'operating_hours_p90_10y', hours_p50 * 0.85)
    gen_sigma_abs = (hours_p50 - p90_hours) / 1.28
    gen_sigma = gen_sigma_abs / hours_p50  # fraction

    equity_irr_dist: list[float] = []
    project_irr_dist: list[float] = []
    min_dscr_dist: list[float] = []

    for i in range(n_iterations):
        eq_irr, proj_irr, min_dscr = _run_single_iteration(
            inputs=inputs,
            seed=None if seed is None else (seed + i),
            ppa_sigma=ppa_sigma,
            gen_sigma=gen_sigma,
            capex_sigma=capex_sigma,
            opex_sigma=opex_sigma,
        )
        equity_irr_dist.append(eq_irr)
        project_irr_dist.append(proj_irr)
        min_dscr_dist.append(min_dscr)

    # Percentiles
    eq_arr = np.array(equity_irr_dist)
    p10 = float(np.percentile(eq_arr, 10))
    p50 = float(np.percentile(eq_arr, 50))
    p90 = float(np.percentile(eq_arr, 90))

    dscr_arr = np.array(min_dscr_dist)
    prob_lt_1 = float(np.mean(dscr_arr < 1.0))
    prob_lt_110 = float(np.mean(dscr_arr < 1.10))

    return MonteCarloResult(
        n_iterations=n_iterations,
        equity_irr_distribution=equity_irr_dist,
        project_irr_distribution=project_irr_dist,
        min_dscr_distribution=min_dscr_dist,
        p10_equity_irr=p10,
        p50_equity_irr=p50,
        p90_equity_irr=p90,
        prob_dscr_below_1=prob_lt_1,
        prob_dscr_below_110=prob_lt_110,
    )


# ---------------------------------------------------------------------------
# Task 3.8 — Cash-at-Risk
# ---------------------------------------------------------------------------

def cash_at_risk(mc_result: MonteCarloResult, confidence_level: float = 0.95) -> CashAtRiskResult:
    """Compute Cash-at-Risk = E[distributions] − VaR_alpha(distr).

    CaR = E[total_distributions] − VaR_alpha(distr)
    where VaR_alpha = percentile_{alpha}(distributions) of equity IRR.

    Note: mc_result contains equity IRR distribution, not distributions.
    This function interprets CaR as E[equity_irr] − VaR_alpha(equity_irr),
    i.e. the IRR shortfall at the confidence_level percentile.

    Args:
        mc_result: MonteCarloResult from run_monte_carlo
        confidence_level: VaR confidence level (default 0.95 = 95%)
    """
    alpha = confidence_level
    irr_arr = np.array(mc_result.equity_irr_distribution)

    expected_irr = float(np.mean(irr_arr))
    var_irr = float(np.percentile(irr_arr, (1 - alpha) * 100))
    expected_dist_keur = expected_irr * 10000  # scale to kEUR (IRR × 10000 bps → approximate)
    var_keur = var_irr * 10000

    return CashAtRiskResult(
        expected_distributions_keur=expected_dist_keur,
        var_95_keur=var_keur,
        cash_at_risk_keur=expected_dist_keur - var_keur,
        confidence_level=confidence_level,
    )