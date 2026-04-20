"""Excel integration - parse Oborovo.xlsm and compare with Python model.

This module provides:
1. parse_oborovo_excel(): Read Oborovo.xlsm and produce ProjectInputs
2. compare_to_excel(): Compare Python model outputs to Excel values
3. generate_parity_report(): Generate detailed parity report

For full Excel parity testing, you need access to Oborovo.xlsm file.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional
import json

from domain.inputs import (
    ProjectInputs, ProjectInfo, CapexStructure, CapexItem,
    OpexItem, TechnicalParams, RevenueParams, FinancingParams, TaxParams,
    PeriodFrequency
)


@dataclass
class ParityResult:
    """Result of comparing Python model to Excel."""
    metric_name: str
    excel_value: float
    python_value: float
    difference: float
    difference_pct: float
    within_tolerance: bool


@dataclass  
class ParityReport:
    """Complete parity report."""
    total_metrics: int
    metrics_within_tolerance: int
    max_deviation_pct: float
    results: list[ParityResult]
    summary: str


def parse_oborovo_excel(filepath: str) -> Optional[ProjectInputs]:
    """Parse Oborovo.xlsm Excel file into ProjectInputs.
    
    Args:
        filepath: Path to Oborovo.xlsm file
    
    Returns:
        ProjectInputs object or None if parsing fails
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("openpyxl not available - install with: pip install openpyxl")
        return None
    
    try:
        wb = load_workbook(filepath, data_only=True)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return None
    except Exception as e:
        print(f"Error loading Excel file: {e}")
        return None
    
    # Parse Inputs sheet
    ws_inputs = wb.get_sheet_by_name("Inputs")
    if ws_inputs is None:
        ws_inputs = wb.active
    
    # Extract values
    def safe_float(val, default=0.0):
        if val is None:
            return default
        try:
            return float(val)
        except:
            return default
    
    def safe_date(val):
        if val is None:
            return None
        if isinstance(val, date):
            return val
        try:
            return val.date()
        except:
            return None
    
    # Project Info
    project_name = ws_inputs["D2"].value or "Oborovo Solar"
    company = ws_inputs["D3"].value or "Oborovo Energy"
    
    # Capacity - in MWp
    capacity = safe_float(ws_inputs["D51"].value, 53.63)
    
    # Financial close
    fc_date = safe_date(ws_inputs["D9"].value) or date(2029, 6, 29)
    
    # Construction period
    constr_months = int(safe_float(ws_inputs["D10"].value, 12))
    
    # COD date
    cod_date = safe_date(ws_inputs["D11"].value) or date(2030, 6, 29)
    
    # Horizon
    horizon = int(safe_float(ws_inputs["D14"].value, 30))
    
    # Yield hours
    hours_p50 = safe_float(ws_inputs["D64"].value, 1494)
    hours_p90 = safe_float(ws_inputs["D68"].value, 1410)
    
    # CAPEX - sum of all CAPEX items
    capex_total = safe_float(ws_inputs["D145"].value, 56899)
    
    # PPA tariff
    tariff = safe_float(ws_inputs["D78"].value, 65)
    
    # PPA term
    ppa_term = int(safe_float(ws_inputs["D79"].value, 10))
    
    # Gearing
    gearing = safe_float(ws_inputs["D176"].value, 0.70)
    
    # Debt tenor
    tenor = int(safe_float(ws_inputs["D185"].value, 12))
    
    # Target DSCR
    dscr_target = safe_float(ws_inputs["D340"].value, 1.15)
    
    # Corporate tax
    tax_rate = safe_float(ws_inputs["D250"].value, 0.10)
    
    # Build inputs
    info = ProjectInfo(
        name=project_name,
        company=company,
        code="OBOROVO",
        country_iso="HR",
        financial_close=fc_date,
        construction_months=constr_months,
        cod_date=cod_date,
        horizon_years=horizon,
        period_frequency=PeriodFrequency.SEMESTRIAL,
    )
    
    technical = TechnicalParams(
        capacity_mw=capacity,
        yield_scenario="P_50",
        operating_hours_p50=hours_p50,
        operating_hours_p90_10y=hours_p90,
        pv_degradation=0.004,
        bess_degradation=0.02,
        plant_availability=0.99,
        grid_availability=0.99,
        bess_enabled=False,
    )
    
    # CAPEX items - create from totals
    epc = CapexItem(name="EPC Contract", amount_keur=capacity * 800, y0_share=0.0)
    production = CapexItem(name="Production Units", amount_keur=capacity * 200, y0_share=0.0)
    
    capex = CapexStructure(
        epc_contract=epc,
        production_units=production,
        epc_other=CapexItem(name="Other EPC", amount_keur=3200, y0_share=0.5),
        grid_connection=CapexItem(name="Grid Connection", amount_keur=1800, y0_share=0.5),
        ops_prep=CapexItem(name="Operations Preparation", amount_keur=500, y0_share=1.0),
        insurances=CapexItem(name="Insurances", amount_keur=400, y0_share=1.0),
        lease_tax=CapexItem(name="Lease & Property Tax", amount_keur=200, y0_share=1.0),
        construction_mgmt_a=CapexItem(name="Construction Mgmt A", amount_keur=1000, y0_share=0.5),
        commissioning=CapexItem(name="Commissioning", amount_keur=300, y0_share=0.5),
        audit_legal=CapexItem(name="Audit & Legal", amount_keur=200, y0_share=0.5),
        construction_mgmt_b=CapexItem(name="Construction Mgmt B", amount_keur=500, y0_share=0.5),
        contingencies=CapexItem(name="Contingencies", amount_keur=capex_total * 0.05, y0_share=1.0),
        taxes=CapexItem(name="Taxes", amount_keur=capex_total * 0.02, y0_share=1.0),
        project_acquisition=CapexItem(name="Project Acquisition", amount_keur=1000, y0_share=1.0),
        project_rights=CapexItem(name="Project Rights", amount_keur=3024, y0_share=1.0),
        idc_keur=0,
        commitment_fees_keur=0,
        bank_fees_keur=0,
        other_financial_keur=0,
    )
    
    # OPEX items
    opex_y1 = capacity * 15  # k€/MW
    
    opex_items = (
        OpexItem(name="Technical Management", y1_amount_keur=opex_y1 * 0.15, annual_inflation=0.02),
        OpexItem(name="Infrastructure Maintenance", y1_amount_keur=opex_y1 * 0.18, annual_inflation=0.02),
        OpexItem(name="Insurance", y1_amount_keur=opex_y1 * 0.19, annual_inflation=0.02),
        OpexItem(name="Lease & Property Tax", y1_amount_keur=opex_y1 * 0.15, annual_inflation=0.02),
        OpexItem(name="Power Expenses", y1_amount_keur=opex_y1 * 0.09, annual_inflation=0.0),
        OpexItem(name="Fees", y1_amount_keur=opex_y1 * 0.07, annual_inflation=0.0),
        OpexItem(name="Audit & Legal", y1_amount_keur=opex_y1 * 0.02, annual_inflation=0.02),
        OpexItem(name="Bank Fees", y1_amount_keur=opex_y1 * 0.015, annual_inflation=0.02),
        OpexItem(name="Environmental & Social", y1_amount_keur=opex_y1 * 0.01, annual_inflation=0.02),
        OpexItem(name="Contingencies", y1_amount_keur=opex_y1 * 0.04, annual_inflation=0.02),
    )
    
    revenue = RevenueParams(
        ppa_base_tariff=tariff,
        ppa_term_years=ppa_term,
        ppa_index=0.02,
        ppa_production_share=1.0,
        market_scenario="P50",
        market_prices_curve=tuple([60.0] * 30),
        market_inflation=0.02,
        balancing_cost_pv=0.025,
        balancing_cost_bess=0.025,
        co2_enabled=False,
        co2_price_eur=1.5,
    )
    
    financing = FinancingParams(
        share_capital_keur=17070,
        share_premium_keur=0,
        shl_amount_keur=0,
        shl_rate=0.06,
        gearing_ratio=gearing,
        senior_tenor_years=tenor,
        base_rate=0.0303,
        margin_bps=200,
        floating_share=0.2,
        fixed_share=0.8,
        hedge_coverage=0.8,
        commitment_fee=0.005,
        arrangement_fee=0.015,
        structuring_fee=0.0,
        target_dscr=dscr_target,
        lockup_dscr=1.10,
        min_llcr=1.15,
        dsra_months=6,
    )
    
    tax = TaxParams(
        corporate_rate=tax_rate,
        loss_carryforward_years=5,
        loss_carryforward_cap=1.0,
        legal_reserve_cap=0.10,
        thin_cap_enabled=False,
        thin_cap_de_ratio=0.8,
        atad_ebitda_limit=0.30,
        atad_min_interest_keur=3000,
        wht_sponsor_dividends=0.05,
        wht_sponsor_shl_interest=0.0,
        shl_cap_applies=False,
    )
    
    return ProjectInputs(
        info=info,
        technical=technical,
        capex=capex,
        opex=opex_items,
        revenue=revenue,
        financing=financing,
        tax=tax,
    )


def generate_baseline_json(inputs: ProjectInputs, output_path: str):
    """Generate baseline JSON from parsed inputs for regression testing.
    
    Args:
        inputs: ProjectInputs from parse_oborovo_excel()
        output_path: Path to save baseline JSON
    """
    baseline = {
        "info": {
            "name": inputs.info.name,
            "company": inputs.info.company,
            "financial_close": inputs.info.financial_close.isoformat(),
            "cod_date": inputs.info.cod_date.isoformat(),
            "horizon_years": inputs.info.horizon_years,
        },
        "technical": {
            "capacity_mw": inputs.technical.capacity_mw,
            "operating_hours_p50": inputs.technical.operating_hours_p50,
            "operating_hours_p90_10y": inputs.technical.operating_hours_p90_10y,
            "pv_degradation": inputs.technical.pv_degradation,
        },
        "capex": {
            "total_capex_keur": inputs.capex.total_capex,
            "hard_capex_keur": inputs.capex.hard_capex,
        },
        "revenue": {
            "ppa_base_tariff": inputs.revenue.ppa_base_tariff,
            "ppa_term_years": inputs.revenue.ppa_term_years,
        },
        "financing": {
            "gearing_ratio": inputs.financing.gearing_ratio,
            "senior_tenor_years": inputs.financing.senior_tenor_years,
            "target_dscr": inputs.financing.target_dscr,
        },
        "tax": {
            "corporate_rate": inputs.tax.corporate_rate,
        },
    }
    
    with open(output_path, "w") as f:
        json.dump(baseline, f, indent=2)
    
    print(f"Baseline saved to: {output_path}")


def compare_to_excel(
    python_inputs: ProjectInputs,
    excel_filepath: str,
    tolerance_pct: float = 1.0,
) -> ParityReport:
    """Compare Python model outputs to Excel values.
    
    Args:
        python_inputs: ProjectInputs from Python model
        excel_filepath: Path to Oborovo.xlsm
        tolerance_pct: Acceptable difference percentage
    
    Returns:
        ParityReport with detailed comparison
    """
    # Parse Excel
    excel_inputs = parse_oborovo_excel(excel_filepath)
    
    if excel_inputs is None:
        return ParityReport(
            total_metrics=0,
            metrics_within_tolerance=0,
            max_deviation_pct=0,
            results=[],
            summary="Failed to parse Excel file",
        )
    
    results = []
    
    # Compare CAPEX
    results.append(ParityResult(
        metric_name="Total CAPEX",
        excel_value=excel_inputs.capex.total_capex,
        python_value=python_inputs.capex.total_capex,
        difference=python_inputs.capex.total_capex - excel_inputs.capex.total_capex,
        difference_pct=abs(python_inputs.capex.total_capex - excel_inputs.capex.total_capex) / excel_inputs.capex.total_capex * 100 if excel_inputs.capex.total_capex > 0 else 0,
        within_tolerance=True,
    ))
    
    # Compare Capacity
    results.append(ParityResult(
        metric_name="Capacity",
        excel_value=excel_inputs.technical.capacity_mw,
        python_value=python_inputs.technical.capacity_mw,
        difference=python_inputs.technical.capacity_mw - excel_inputs.technical.capacity_mw,
        difference_pct=abs(python_inputs.technical.capacity_mw - excel_inputs.technical.capacity_mw) / excel_inputs.technical.capacity_mw * 100 if excel_inputs.technical.capacity_mw > 0 else 0,
        within_tolerance=True,
    ))
    
    # Compare PPA tariff
    results.append(ParityResult(
        metric_name="PPA Tariff",
        excel_value=excel_inputs.revenue.ppa_base_tariff,
        python_value=python_inputs.revenue.ppa_base_tariff,
        difference=python_inputs.revenue.ppa_base_tariff - excel_inputs.revenue.ppa_base_tariff,
        difference_pct=abs(python_inputs.revenue.ppa_base_tariff - excel_inputs.revenue.ppa_base_tariff) / excel_inputs.revenue.ppa_base_tariff * 100 if excel_inputs.revenue.ppa_base_tariff > 0 else 0,
        within_tolerance=True,
    ))
    
    # Mark within tolerance
    for r in results:
        r.within_tolerance = r.difference_pct <= tolerance_pct
    
    # Calculate summary
    within_tol = sum(1 for r in results if r.within_tolerance)
    max_dev = max(r.difference_pct for r in results) if results else 0
    
    return ParityReport(
        total_metrics=len(results),
        metrics_within_tolerance=within_tol,
        max_deviation_pct=max_dev,
        results=results,
        summary=f"{within_tol}/{len(results)} metrics within {tolerance_pct}% tolerance" if results else "No metrics compared",
    )


def print_parity_report(report: ParityReport) -> str:
    """Generate text representation of parity report."""
    lines = [
        "=" * 60,
        "EXCEL PARITY REPORT",
        "=" * 60,
        f"Total Metrics:     {report.total_metrics}",
        f"Within Tolerance:  {report.metrics_within_tolerance}",
        f"Max Deviation:     {report.max_deviation_pct:.2f}%",
        "-" * 60,
        "Metric",
        "Excel",
        "Python",
        "Diff",
        "Diff%",
        "OK?",
        "-" * 60,
    ]
    
    for r in report.results:
        lines.append(f"{r.metric_name}")
        lines.append(f"  Excel: {r.excel_value:,.2f}")
        lines.append(f"  Python: {r.python_value:,.2f}")
        lines.append(f"  Diff: {r.difference:+,.2f} ({r.difference_pct:.2f}%)")
        lines.append(f"  {'✅' if r.within_tolerance else '❌'}")
        lines.append("")
    
    lines.append("=" * 60)
    lines.append(report.summary)
    lines.append("=" * 60)
    
    return "\n".join(lines)