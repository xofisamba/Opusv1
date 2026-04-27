"""Centralizirani helper za pokretanje waterfall i caching rezultata."""
from typing import Optional, Dict, Any


def run_and_cache(
    inputs,
    scenario_id: Optional[str] = None,
    force_refresh: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """
    Pokreni waterfall za dani inputs objekt, vrati metrics dict.

    Args:
        inputs: ProjectInputs objekt
        scenario_id: Ako zadan, spremi result u DB result_snapshots
        force_refresh: Ako True, ignoriraj cache
        **kwargs: Dodatni parametri za cached_run_waterfall_v3:
            - fixed_debt_keur: float | None
            - equity_irr_method: str ("equity_only" | "combined")
            - share_capital_keur: float
            - sculpt_capex_keur: float

    Returns:
        dict s ključevima:
        project_irr, equity_irr, avg_dscr, min_dscr,
        total_debt_keur, npv_keur, total_distribution_keur,
        error (str ili None)
    """
    try:
        from utils.cache import cached_run_waterfall_v3
        from domain.period_engine import PeriodEngine, PeriodFrequency as PF
        from domain.inputs import PeriodFrequency

        if force_refresh:
            cached_run_waterfall_v3.clear()

        fin = inputs.financing
        freq = PF.SEMESTRIAL if inputs.info.period_frequency == PeriodFrequency.SEMESTRIAL else PF.ANNUAL
        engine = PeriodEngine(
            financial_close=inputs.info.financial_close,
            construction_months=inputs.info.construction_months,
            horizon_years=inputs.info.horizon_years,
            ppa_years=inputs.revenue.ppa_term_years,
            frequency=freq,
        )

        # Build kwargs with defaults
        run_kwargs = {
            "inputs": inputs,
            "engine": engine,
            "rate_per_period": fin.all_in_rate / 2,
            "tenor_periods": fin.senior_tenor_years * 2,
            "target_dscr": fin.target_dscr,
            "lockup_dscr": fin.lockup_dscr,
            "tax_rate": inputs.tax.corporate_rate,
            "dsra_months": fin.dsra_months,
            "shl_amount": fin.shl_amount_keur,
            "shl_rate": fin.shl_rate,
            "equity_irr_method": getattr(fin, 'equity_irr_method', 'equity_only'),
            "share_capital_keur": fin.share_capital_keur,
            "sculpt_capex_keur": getattr(inputs.capex, 'sculpt_capex_keur', inputs.capex.total_capex),
            "debt_sizing_method": getattr(fin, 'debt_sizing_method', 'dscr_sculpt'),
        }
        # Override with explicit kwargs
        run_kwargs.update(kwargs)

        result = cached_run_waterfall_v3(**run_kwargs)

        metrics = {
            "project_irr": result.project_irr,
            "equity_irr": result.equity_irr,
            "avg_dscr": result.avg_dscr,
            "min_dscr": result.min_dscr,
            "total_debt_keur": result.sculpting_result.debt_keur,
            "npv_keur": getattr(result, 'npv_keur', None),
            "total_distribution_keur": result.total_distribution_keur,
            "error": None,
        }

        if scenario_id:
            _save_result_to_db(scenario_id, metrics, inputs)

        return metrics

    except Exception as e:
        return {"error": str(e)}


def _save_result_to_db(scenario_id: str, metrics: dict, inputs) -> None:
    """Spremi metrics u result_snapshots."""
    try:
        from persistence.database import get_engine
        from persistence.repository import ProjectRepository
        from sqlalchemy.orm import sessionmaker
        import hashlib
        import json

        engine = get_engine()
        Sm = sessionmaker(bind=engine, expire_on_commit=False)
        db = ProjectRepository(Sm())
        # Compute inputs hash for cache invalidation
        inputs_json = json.dumps(inputs, default=str, sort_keys=True)
        inputs_hash = hashlib.sha256(inputs_json.encode()).hexdigest()
        db.save_results(scenario_id, metrics, inputs_hash)
    except Exception:
        pass  # Nije kritično — samo logging
