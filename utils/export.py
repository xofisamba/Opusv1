"""CSV/Excel export utilities for waterfall results.

Provides functions to export:
- Waterfall period data (CSV)
- Summary metrics (CSV)
- Financial statements (CSV)

Usage:
    from utils.export import export_waterfall_csv
    export_waterfall_csv(result, "waterfall_output.csv")
"""
import csv
from pathlib import Path
from typing import Optional

from domain.waterfall.waterfall_engine import WaterfallResult


def export_waterfall_csv(result: WaterfallResult, filepath: str) -> None:
    """Export waterfall period data to CSV.
    
    Args:
        result: WaterfallResult from run_waterfall
        filepath: Output CSV file path
    """
    fieldnames = [
        "period", "year_index", "period_in_year", "is_operation",
        "generation_mwh", "revenue_keur", "opex_keur", "ebitda_keur",
        "depreciation_keur", "interest_senior_keur", "interest_shl_keur",
        "tax_keur", "cf_after_tax_keur",
        "senior_ds_keur", "senior_interest_keur", "senior_principal_keur",
        "shl_service_keur", "shl_interest_keur", "shl_principal_keur",
        "dsra_contribution_keur", "dsra_balance_keur",
        "cf_after_reserves_keur", "dscr", "llcr", "plcr",
        "lockup_active", "distribution_keur", "cash_sweep_keur",
        "cum_distribution_keur", "cash_balance_keur",
    ]
    
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for p in result.periods:
            writer.writerow({
                "period": p.period,
                "year_index": p.year_index,
                "period_in_year": p.period_in_year,
                "is_operation": p.is_operation,
                "generation_mwh": round(p.generation_mwh, 2),
                "revenue_keur": round(p.revenue_keur, 2),
                "opex_keur": round(p.opex_keur, 2),
                "ebitda_keur": round(p.ebitda_keur, 2),
                "depreciation_keur": round(p.depreciation_keur, 2),
                "interest_senior_keur": round(p.interest_senior_keur, 2),
                "interest_shl_keur": round(p.interest_shl_keur, 2),
                "tax_keur": round(p.tax_keur, 2),
                "cf_after_tax_keur": round(p.cf_after_tax_keur, 2),
                "senior_ds_keur": round(p.senior_ds_keur, 2),
                "senior_interest_keur": round(p.senior_interest_keur, 2),
                "senior_principal_keur": round(p.senior_principal_keur, 2),
                "shl_service_keur": round(p.shl_service_keur, 2),
                "shl_interest_keur": round(p.shl_interest_keur, 2),
                "shl_principal_keur": round(p.shl_principal_keur, 2),
                "dsra_contribution_keur": round(p.dsra_contribution_keur, 2),
                "dsra_balance_keur": round(p.dsra_balance_keur, 2),
                "cf_after_reserves_keur": round(p.cf_after_reserves_keur, 2),
                "dscr": round(p.dscr, 4) if p.dscr < float('inf') else 999.0,
                "llcr": round(p.llcr, 4) if p.llcr < float('inf') else 999.0,
                "plcr": round(p.plcr, 4) if p.plcr < float('inf') else 999.0,
                "lockup_active": p.lockup_active,
                "distribution_keur": round(p.distribution_keur, 2),
                "cash_sweep_keur": round(p.cash_sweep_keur, 2),
                "cum_distribution_keur": round(p.cum_distribution_keur, 2),
                "cash_balance_keur": round(p.cash_balance_keur, 2),
            })


def export_summary_csv(result: WaterfallResult, filepath: str) -> None:
    """Export summary metrics to CSV.
    
    Args:
        result: WaterfallResult from run_waterfall
        filepath: Output CSV file path
    """
    sculpt = result.sculpting_result
    
    rows = [
        ("=== REVENUE ===", ""),
        ("Total Revenue (kEUR)", f"{result.total_revenue_keur:,.0f}"),
        ("Total OPEX (kEUR)", f"{result.total_opex_keur:,.0f}"),
        ("Total EBITDA (kEUR)", f"{result.total_ebitda_keur:,.0f}"),
        ("Total Tax (kEUR)", f"{result.total_tax_keur:,.0f}"),
        ("", ""),
        ("=== DEBT ===", ""),
        ("Debt Amount (kEUR)", f"{sculpt.debt_keur:,.0f}"),
        ("Total Senior DS (kEUR)", f"{result.total_senior_ds_keur:,.0f}"),
        ("Total SHL Service (kEUR)", f"{result.total_shl_service_keur:,.0f}"),
        ("", ""),
        ("=== RETURNS ===", ""),
        ("Project IRR", f"{result.project_irr*100:.3f}%"),
        ("Equity IRR", f"{result.equity_irr*100:.3f}%" if result.equity_irr else "N/A"),
        ("Project NPV (kEUR)", f"{result.project_npv:,.0f}"),
        ("Equity NPV (kEUR)", f"{result.equity_npv:,.0f}" if result.equity_npv else "N/A"),
        ("", ""),
        ("=== COVENANTS ===", ""),
        ("Avg DSCR", f"{result.avg_dscr:.3f}"),
        ("Min DSCR", f"{result.min_dscr:.3f}"),
        ("Min LLCR", f"{result.min_llcr:.3f}" if result.min_llcr else "N/A"),
        ("Min PLCR", f"{result.min_plcr:.3f}" if result.min_plcr else "N/A"),
        ("Periods in Lockup", f"{result.periods_in_lockup}"),
        ("", ""),
        ("=== DISTRIBUTIONS ===", ""),
        ("Total Distribution (kEUR)", f"{result.total_distribution_keur:,.0f}"),
    ]
    
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)


def waterfall_to_dataframe(result: WaterfallResult) -> "pd.DataFrame":
    """Convert waterfall result to pandas DataFrame.
    
    Args:
        result: WaterfallResult from run_waterfall
    
    Returns:
        DataFrame with period-level data
    """
    import pandas as pd
    
    data = []
    for p in result.periods:
        data.append({
            "Period": p.period,
            "Year": p.year_index,
            "H": p.period_in_year,
            "Op": p.is_operation,
            "Gen (MWh)": round(p.generation_mwh, 0),
            "Rev (kEUR)": round(p.revenue_keur, 0),
            "OPEX (kEUR)": round(p.opex_keur, 0),
            "EBITDA (kEUR)": round(p.ebitda_keur, 0),
            "Dep (kEUR)": round(p.depreciation_keur, 0),
            "Int Sen (kEUR)": round(p.interest_senior_keur, 0),
            "Tax (kEUR)": round(p.tax_keur, 0),
            "CFAT (kEUR)": round(p.cf_after_tax_keur, 0),
            "Sen DS (kEUR)": round(p.senior_ds_keur, 0),
            "DSCR": round(p.dscr, 2) if p.dscr < float('inf') else None,
            "Dist (kEUR)": round(p.distribution_keur, 0),
            "Sweep (kEUR)": round(p.cash_sweep_keur, 0),
            "Cash Bal (kEUR)": round(p.cash_balance_keur, 0),
        })
    
    return pd.DataFrame(data)
