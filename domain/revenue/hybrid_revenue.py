"""Hybrid revenue schedule from LP dispatch.

Converts annual LP dispatch results into semi-annual revenue schedule
compatible with waterfall_engine.py ebitda_schedule format.

Usage:
    result = hybrid_dispatch_lp(...)
    rev = hybrid_revenue_schedule(inputs, engine, dispatch_result=result)

    # Ulazi direktno u waterfall:
    ebitda_sched = []
    for p in periods:
        rev_keur = rev.period_revenues.get(p.index, 0)
        opex_keur = opex_annual.get(p.year_index, 0) / 2 if p.is_operation else 0
        ebitda_sched.append(max(0.0, rev_keur - opex_keur))
"""
from __future__ import annotations
from dataclasses import dataclass
from core.engines.hybrid_engine import HybridDispatchResult, hybrid_dispatch_lp
from core.engines.bess_engine import BESSConfig


@dataclass
class HybridRevenueResult:
    """Semi-annual hybrid revenue by period index."""
    period_revenues: dict[int, float]  # period_index → kEUR
    period_generation: dict[int, float]  # period_index → MWh
    annual_bess_revenue_keur: float
    annual_export_mwh: float
    annual_clipping_pct: float


def hybrid_revenue_schedule(
    inputs,  # ProjectInputs
    engine,  # PeriodEngine
    dispatch_result: HybridDispatchResult | None = None,
) -> HybridRevenueResult:
    """Build semi-annual hybrid revenue schedule.

    If dispatch_result is provided (pre-computed), uses it directly.
    Otherwise runs LP dispatch from inputs.

    Revenue per period = (export_mwh × tariff/1000) + bess_arbitrage
    Split semi-annually proportionally by period.day_fraction.

    INTEGRACIJA: period_revenues ulazi u ebitda_schedule
    za run_waterfall() — vidi docstring modula.
    """
    if dispatch_result is None:
        bess = None
        if hasattr(inputs, 'bess') and inputs.bess is not None:
            bess = BESSConfig(
                capacity_mwh=inputs.bess.energy_capacity_mwh,
                power_mw=inputs.bess.power_capacity_mw,
                roundtrip_efficiency=inputs.bess.roundtrip_efficiency,
            )
        dispatch_result = hybrid_dispatch_lp(
            solar_capacity_mw=getattr(inputs.technical, 'solar_capacity_mw', 0),
            wind_capacity_mw=getattr(inputs.technical, 'wind_capacity_mw', 0),
            bess=bess,
            grid_limit_mw=getattr(
                inputs.technical, 'grid_limit_mw', inputs.technical.capacity_mw
            ),
            solar_cf_annual=getattr(inputs.technical, 'solar_cf', 0),
            wind_cf_annual=getattr(inputs.technical, 'wind_cf', 0),
        )

    op_periods = [p for p in engine.periods() if p.is_operation]
    period_revenues: dict[int, float] = {}
    period_generation: dict[int, float] = {}

    for period in op_periods:
        df = period.day_fraction

        # Tariff indexing (konzistentno s PPA modelom)
        tariff = _indexed_tariff(
            base=inputs.revenue.ppa_base_tariff_eur_mwh,
            escalation=inputs.revenue.ppa_escalation,
            year_index=period.year_index,
        )

        gen_mwh = dispatch_result.annual_export_mwh * df
        ppa_revenue = gen_mwh * tariff / 1000  # kEUR

        # BESS arbitrage proporcionalno po periodu
        bess_rev = dispatch_result.bess_arbitrage_revenue_keur * df

        period_revenues[period.index] = ppa_revenue + bess_rev
        period_generation[period.index] = gen_mwh

    return HybridRevenueResult(
        period_revenues=period_revenues,
        period_generation=period_generation,
        annual_bess_revenue_keur=dispatch_result.bess_arbitrage_revenue_keur,
        annual_export_mwh=dispatch_result.annual_export_mwh,
        annual_clipping_pct=dispatch_result.clipping_pct,
    )


def _indexed_tariff(base: float, escalation: float, year_index: int) -> float:
    """Annual tariff indexing (konzistentno s PPA modelom)."""
    return base * (1 + escalation) ** (year_index - 1)