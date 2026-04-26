"""PDF Export — OpusCore v2 Phase 3 Task 3.2.

Generates a formatted Credit Memo PDF using WeasyPrint (HTML → PDF).
Falls back to ReportLab if WeasyPrint is not available.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

try:
    import weasyprint
    HAS_WEASYPRINT = True
except ImportError:
    HAS_WEASYPRINT = False


def _build_html(
    result: any,
    inputs: any,
    project_name: str,
    technology: str,
    capacity_mw: float,
    cod_date: str,
    financial_close: str,
    logo_bytes: Optional[bytes],
    footer_text: str,
    disclaimer: str,
) -> str:
    """Build the full HTML document for PDF export."""
    project_irr = getattr(result, "project_irr", 0) or 0
    equity_irr = getattr(result, "equity_irr", 0) or 0
    project_npv = getattr(result, "project_npv", 0) or 0
    avg_dscr = getattr(result, "avg_dscr", 0) or 0
    min_dscr = getattr(result, "min_dscr", 0) or 0
    min_llcr = getattr(result, "min_llcr", 0) or 0
    eq_irr_val = equity_irr
    lcoe = _calc_lcoe_pdf(result, capacity_mw)

    logo_html = ""
    if logo_bytes:
        import base64
        b64 = base64.b64encode(logo_bytes).decode()
        logo_html = f'<img src="data:image/png;base64,{b64}" height="80" style="max-height:80px;float:left;" />'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<style>
  @page {{
    size: A4;
    margin: 18mm 20mm 22mm 20mm;
    @top-center {{ content: "{footer_text}"; font-size: 8pt; color: #888; }}
    @bottom-left {{ content: "OpusCore v2 — {datetime.now().strftime('%Y-%m-%d')}"; font-size: 8pt; color: #888; }}
    @bottom-center {{ content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #888; }}
    @bottom-right {{ content: "{disclaimer}"; font-size: 7pt; color: #aaa; font-style: italic; }}
  }}
  body {{ font-family: Calibri, Arial, sans-serif; font-size: 10pt; color: #222; margin: 0; padding: 0; }}
  .cover-header {{ background: #1F3864; color: white; padding: 12mm 15mm; margin-bottom: 8mm; }}
  .cover-header h1 {{ margin: 0 0 4mm 0; font-size: 18pt; font-weight: bold; }}
  .cover-header p {{ margin: 1mm 0; font-size: 10pt; color: #ccd; }}
  .section {{ margin-bottom: 10mm; }}
  h2 {{ font-size: 12pt; color: #1F3864; border-bottom: 1.5px solid #1F3864; padding-bottom: 1mm; margin-bottom: 3mm; }}
  .meta-table {{ width: 100%; border-collapse: collapse; margin-bottom: 6mm; }}
  .meta-table td {{ padding: 2mm 4mm; border: 0.5px solid #ccc; }}
  .meta-table td.label {{ font-weight: bold; width: 35%; background: #f5f5f5; color: #333; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; margin-bottom: 6mm; }}
  .kpi-card {{ background: #f0f5fb; border-left: 3px solid #2E75B6; padding: 3mm 4mm; }}
  .kpi-card .label {{ font-size: 8pt; color: #666; text-transform: uppercase; margin-bottom: 1mm; }}
  .kpi-card .value {{ font-size: 14pt; font-weight: bold; color: #1F3864; }}
  .kpi-card .unit {{ font-size: 8pt; color: #888; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 5mm; }}
  th {{ background: #1F3864; color: white; padding: 2mm 3mm; text-align: left; font-size: 9pt; }}
  td {{ padding: 1.5mm 3mm; border-bottom: 0.5px solid #ddd; font-size: 9pt; }}
  tr:nth-child(even) td {{ background: #f9f9f9; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.neg {{ color: #c00000; }}
  .footer {{ font-size: 8pt; color: #888; border-top: 0.5px solid #ccc; padding-top: 2mm; margin-top: 5mm; }}
  .lockup {{ color: #c00000; font-weight: bold; }}
  .section-page-break {{ page-break-before: always; }}
</style>
</head>
<body>

<!-- PAGE 1: Cover -->
<div class="cover-header">
  {logo_html}
  <h1>FID Credit Memo — {project_name}</h1>
  <p>Technology: {technology} &nbsp;|&nbsp; Capacity: {capacity_mw:.1f} MW &nbsp;|&nbsp; COD: {cod_date}</p>
  <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; Financial Close: {financial_close}</p>
</div>

<div class="meta-table">
  <tr><td class="label">Technology</td><td>{technology}</td></tr>
  <tr><td class="label">Capacity (MW)</td><td>{capacity_mw:.2f}</td></tr>
  <tr><td class="label">Commercial Operation Date</td><td>{cod_date}</td></tr>
  <tr><td class="label">Financial Close</td><td>{financial_close}</td></tr>
  <tr><td class="label">Country</td><td>{getattr(inputs.info, 'country_iso', 'N/A') if hasattr(inputs, 'info') else 'N/A'}</td></tr>
</div>

<div class="kpi-grid">
  <div class="kpi-card"><div class="label">Project IRR</div><div class="value">{project_irr:.2%}</div><div class="unit">unlevered, post-tax</div></div>
  <div class="kpi-card"><div class="label">Equity IRR</div><div class="value">{equity_irr:.2%}</div><div class="unit">levered, post-tax</div></div>
  <div class="kpi-card"><div class="label">Project NPV</div><div class="value">{project_npv:,.0f}</div><div class="unit">kEUR @ {getattr(result, 'project_discount_rate', 0.0641):.2%} WACC</div></div>
  <div class="kpi-card"><div class="label">LCOE</div><div class="value">{lcoe:.1f}</div><div class="unit">EUR/MWh</div></div>
  <div class="kpi-card"><div class="label">Avg DSCR</div><div class="value">{avg_dscr:.2f}x</div><div class="unit">min lockup: 1.10x</div></div>
  <div class="kpi-card"><div class="label">Min DSCR</div><div class="value">{min_dscr:.2f}x</div><div class="unit">{'⚠ LOCKUP' if min_dscr < 1.10 else 'OK'}</div></div>
  <div class="kpi-card"><div class="label">LLCR</div><div class="value">{min_llcr:.2f}x</div><div class="unit">minimum</div></div>
  <div class="kpi-card"><div class="label">Payback</div><div class="value">{_calc_payback_pdf(result):.1f}</div><div class="unit">years (equity)</div></div>
</div>

<div class="footer">
  {disclaimer}
</div>

<!-- PAGE 2: Returns Summary -->
<div class="section-page-break">
<h2>Returns Summary</h2>

<h3>Unlevered Returns</h3>
<table>
  <tr><th>Metric</th><th>Value</th><th>Unit</th></tr>
  <tr><td>Project IRR (unlevered, post-tax)</td><td class="num">{project_irr:.2%}</td><td></td></tr>
  <tr><td>Project NPV</td><td class="num">{project_npv:,.0f}</td><td>kEUR</td></tr>
  <tr><td>LCOE</td><td class="num">{lcoe:.1f}</td><td>EUR/MWh</td></tr>
</table>

<h3>Levered Returns (per Sponsor)</h3>
<table>
  <tr><th>Sponsor</th><th>Equity kEUR</th><th>SHL kEUR</th>
      <th>Distributions kEUR</th><th>IRR</th><th>MOIC</th><th>Payback yr</th></tr>
  <tr><td>Investor 1</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td></tr>
  <tr style="font-weight:bold;background:#e8f0fb;"><td>Total</td>
      <td class="num">—</td><td class="num">—</td><td class="num">—</td>
      <td class="num">{equity_irr:.2%}</td><td class="num">—</td><td class="num">—</td></tr>
</table>

<h3>Coverage Ratios</h3>
<table>
  <tr><th>Metric</th><th>Value</th><th>Threshold</th><th>Status</th></tr>
  <tr><td>Average DSCR</td><td class="num">{avg_dscr:.3f}x</td><td>≥ 1.15x</td>
      <td>{"✓ OK" if avg_dscr >= 1.15 else "⚠ Below covenant"}</td></tr>
  <tr><td>Minimum DSCR</td><td class="num">{min_dscr:.3f}x</td><td>≥ 1.00x</td>
      <td>{"⚠ LOCKUP" if min_dscr < 1.10 else "✓ OK"}</td></tr>
  <tr><td>LLCR</td><td class="num">{min_llcr:.3f}x</td><td>≥ 1.20x</td>
      <td>{"✓ OK" if min_llcr >= 1.20 else "⚠ Below"}</td></tr>
  <tr><td>Periods in lockup</td><td class="num">{getattr(result, 'periods_in_lockup', 0)}</td><td></td><td></td></tr>
</table>
</div>

<!-- PAGE 3: P&L Summary -->
<div class="section-page-break">
<h2>Profit &amp; Loss — Selected Years (kEUR)</h2>
<table>
  <tr><th>Line item</th><th>Year 1</th><th>Year 3</th><th>Year 5</th><th>Year 10</th><th>Year 20</th><th>Year 30</th></tr>
  <tr><td>Revenue</td>
    <td class="num">{_ann_val(result, 1, 'rev'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'rev'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'rev'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'rev'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'rev'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'rev'):,.0f}</td>
  </tr>
  <tr><td>EBITDA</td>
    <td class="num">{_ann_val(result, 1, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'ebitda'):,.0f}</td>
  </tr>
  <tr><td>EBIT</td>
    <td class="num">{_ann_val(result, 1, 'ebit'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'ebit'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'ebit'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'ebit'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'ebit'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'ebit'):,.0f}</td>
  </tr>
  <tr><td>Net Income</td>
    <td class="num">{_ann_val(result, 1, 'ni'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'ni'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'ni'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'ni'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'ni'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'ni'):,.0f}</td>
  </tr>
</table>
</div>

<!-- PAGE 4: Cash Flow Summary -->
<div class="section-page-break">
<h2>Cash Flow — Selected Years (kEUR)</h2>
<table>
  <tr><th>Line item</th><th>Year 1</th><th>Year 3</th><th>Year 5</th><th>Year 10</th><th>Year 20</th><th>Year 30</th></tr>
  <tr><td>EBITDA</td>
    <td class="num">{_ann_val(result, 1, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'ebitda'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'ebitda'):,.0f}</td>
  </tr>
  <tr><td>Senior Debt Service</td>
    <td class="num">{_ann_val(result, 1, 'ds'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'ds'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'ds'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'ds'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'ds'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'ds'):,.0f}</td>
  </tr>
  <tr><td>FCF before distributions</td>
    <td class="num">{_ann_val(result, 1, 'fcf'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'fcf'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'fcf'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'fcf'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'fcf'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'fcf'):,.0f}</td>
  </tr>
  <tr><td>Gross Dividends</td>
    <td class="num">{_ann_val(result, 1, 'dist'):,.0f}</td>
    <td class="num">{_ann_val(result, 3, 'dist'):,.0f}</td>
    <td class="num">{_ann_val(result, 5, 'dist'):,.0f}</td>
    <td class="num">{_ann_val(result, 10, 'dist'):,.0f}</td>
    <td class="num">{_ann_val(result, 20, 'dist'):,.0f}</td>
    <td class="num">{_ann_val(result, 30, 'dist'):,.0f}</td>
  </tr>
</table>
</div>

</body>
</html>"""
    return html


def _calc_lcoe_pdf(result, cap_mw):
    try:
        capex = getattr(result, "total_capex_keur", 0) or 0
        opex = getattr(result, "total_opex_keur", 0) or 0
        total_gen = cap_mw * 1494 * 30 / 1000
        if total_gen > 0:
            return (capex + opex) / total_gen * 1000
        return 0.0
    except Exception:
        return 0.0


def _calc_payback_pdf(result):
    try:
        eq_irr = getattr(result, "equity_irr", 0) or 0
        if eq_irr > 0:
            return round(1 / eq_irr, 1)
        return 99.9
    except Exception:
        return 99.9


def _annual_val(result, year, key):
    """Get annual value for given year from result.periods."""
    try:
        periods = getattr(result, "periods", [])
        by_year = {}
        for p in periods:
            yi = getattr(p, "year_index", 0)
            if yi not in by_year:
                by_year[yi] = {"rev": 0, "opex": 0, "ebitda": 0, "dep": 0,
                               "ebit": 0, "fin": 0, "ebt": 0, "tax": 0,
                               "ni": 0, "ds": 0, "dist": 0, "fcf": 0}
            bp = by_year[yi]
            bp["rev"] += getattr(p, "revenue_keur", 0)
            bp["ebitda"] += getattr(p, "ebitda_keur", 0)
            bp["dep"] += getattr(p, "depreciation_keur", 0)
            bp["fin"] += (getattr(p, "interest_senior_keur", 0) +
                          getattr(p, "interest_shl_keur", 0))
            bp["tax"] += getattr(p, "tax_keur", 0)
            bp["ds"] += getattr(p, "debt_service_keur", 0)
            bp["dist"] += getattr(p, "distribution_keur", 0)
            bp["ebit"] = bp["ebitda"] - bp["dep"]
            bp["ebt"] = bp["ebit"] - bp["fin"]
            bp["ni"] = bp["ebt"] - bp["tax"]
            bp["fcf"] = bp["ebitda"] - bp["ds"]

        ann = by_year.get(year, {})
        return ann.get(key, 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def export_pdf(
    result: any,
    inputs: any,
    filepath: str,
    branding: dict | None = None,
    project_name: str | None = None,
) -> None:
    """Generate a formatted Credit Memo PDF.

    Uses WeasyPrint (HTML → PDF) if available, otherwise raises clear error.
    PDF has 4 pages: Cover, Returns Summary, P&L, Cash Flow.

    Args:
        result: WaterfallResult from cached_run_waterfall_v3
        inputs: ProjectInputs instance
        filepath: output .pdf path
        branding: optional dict with logo_bytes, footer_text, disclaimer
        project_name: override for project name
    """
    if not HAS_WEASYPRINT:
        raise ImportError(
            "weasyprint not installed — run: pip install weasyprint. "
            "PDF export requires weasyprint for HTML-to-PDF conversion."
        )

    proj_name = project_name or (
        getattr(inputs.info, "name", "Project")
        if hasattr(inputs, "info") else "Project"
    )
    tech = getattr(inputs.info, "technology_type", "Solar") if hasattr(inputs, "info") else "Solar"
    cap_mw = getattr(inputs.info, "capacity_mw", 75.26) if hasattr(inputs, "info") else 75.26
    cod = str(getattr(inputs.info, "cod_date", "N/A")) if hasattr(inputs, "info") else "N/A"
    fin_close = str(getattr(inputs.info, "financial_close", "N/A")) if hasattr(inputs, "info") else "N/A"
    footer_text = branding.get("footer_text", "Confidential — prepared by OpusCore v2") if branding else "Confidential — prepared by OpusCore v2"
    disclaimer = branding.get("disclaimer", "This financial model is for illustrative purposes only.") if branding else "This financial model is for illustrative purposes only."
    logo_bytes = branding.get("logo_bytes") if branding else None

    html = _build_html(
        result=result,
        inputs=inputs,
        project_name=proj_name,
        technology=tech,
        capacity_mw=cap_mw,
        cod_date=cod,
        financial_close=fin_close,
        logo_bytes=logo_bytes,
        footer_text=footer_text,
        disclaimer=disclaimer,
    )

    try:
        doc = weasyprint.HTML(string=html)
        doc.write_pdf(filepath)
    except Exception as e:
        raise RuntimeError(
            f"PDF generation failed: {e}. "
            "Try simplifying the HTML or installing additional fonts."
        ) from e
