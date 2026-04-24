"""Waterfall visualization functions for the financial model UI."""
import plotly.graph_objects as go
from typing import TYPE_CHECKING

from utils.ui_constants import (
    FINANCIAL_CHART_LAYOUT,
    KEUR_HOVER,
    PCT_HOVER,
    CHART_CONFIG,
    add_dscr_thresholds,
)

if TYPE_CHECKING:
    from domain.waterfall.waterfall_engine import WaterfallResult


def create_waterfall_summary_chart(result: "WaterfallResult") -> go.Figure:
    """Create cash flow waterfall bar chart (stacked by component).
    
    Shows annual cash flow waterfall: Revenue → EBITDA → Tax → Debt Service → Distribution.
    """
    if not result.periods:
        return go.Figure()
    
    # Aggregate by year
    years_data = {}
    for p in result.periods:
        y = p.year_index
        if y not in years_data:
            years_data[y] = {
                "revenue": 0.0, "opex": 0.0, "ebitda": 0.0,
                "tax": 0.0, "senior_ds": 0.0, "shl_service": 0.0,
                "distribution": 0.0, "cash_sweep": 0.0,
            }
        years_data[y]["revenue"] += p.revenue_keur
        years_data[y]["opex"] += p.opex_keur
        years_data[y]["ebitda"] += p.ebitda_keur
        years_data[y]["tax"] += abs(p.tax_keur) if p.tax_keur > 0 else 0
        years_data[y]["senior_ds"] += p.senior_ds_keur
        years_data[y]["shl_service"] += p.shl_service_keur
        years_data[y]["distribution"] += p.distribution_keur
        years_data[y]["cash_sweep"] += p.cash_sweep_keur
    
    sorted_years = sorted(years_data.keys())
    year_labels = [f"Y{y+1}" for y in sorted_years]
    
    fig = go.Figure()
    
    # Revenue (green, positive)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[years_data[y]["revenue"] for y in sorted_years],
        name="Revenue",
        marker_color="#2ecc71",  # green
    ))
    
    # OPEX (red, negative)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[-years_data[y]["opex"] for y in sorted_years],
        name="OPEX",
        marker_color="#e74c3c",  # red
    ))
    
    # EBITDA (light green)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[years_data[y]["ebitda"] for y in sorted_years],
        name="EBITDA",
        marker_color="#27ae60",  # dark green
    ))
    
    # Tax (orange)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[-years_data[y]["tax"] for y in sorted_years],
        name="Tax",
        marker_color="#e67e22",  # orange
    ))
    
    # Senior Debt Service (purple)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[-years_data[y]["senior_ds"] for y in sorted_years],
        name="Senior DS",
        marker_color="#9b59b6",  # purple
    ))
    
    # SHL Service (dark blue)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[-years_data[y]["shl_service"] for y in sorted_years],
        name="SHL Service",
        marker_color="#2980b9",  # dark blue
    ))
    
    # Distributions (blue)
    fig.add_trace(go.Bar(
        x=year_labels,
        y=[years_data[y]["distribution"] for y in sorted_years],
        name="Distribution",
        marker_color="#3498db",  # blue
    ))
    
    fig.update_layout(
        **FINANCIAL_CHART_LAYOUT,
        title="Annual Cash Flow Waterfall",
        xaxis_title="Period",
        yaxis_title="kEUR",
        barmode="relative",
    )
    fig.update_layout(config=CHART_CONFIG)
    
    return fig


def create_dscr_chart(result: "WaterfallResult") -> go.Figure:
    """Create DSCR over time chart with lockup threshold."""
    if not result.periods:
        return go.Figure()
    
    periods = [p.period for p in result.periods]
    dscr_values = [p.dscr for p in result.periods]
    
    fig = go.Figure()
    
    # DSCR line
    fig.add_trace(go.Scatter(
        x=periods,
        y=dscr_values,
        name="DSCR",
        mode="lines+markers",
        line=dict(color="#3498db", width=2),
        marker=dict(size=6),
        hovertemplate=PCT_HOVER,
    ))

    # Target DSCR reference line (1.15)
    fig.add_trace(go.Scatter(
        x=periods,
        y=[1.15] * len(periods),
        name="Target (1.15x)",
        mode="lines",
        line=dict(color="#F59E0B", dash="dash", width=1.5),
    ))

    # Lockup DSCR reference line (1.10)
    fig.add_trace(go.Scatter(
        x=periods,
        y=[1.10] * len(periods),
        name="Lockup (1.10x)",
        mode="lines",
        line=dict(color="#EF4444", dash="dash", width=1.5),
    ))

    # Highlight lockup periods
    lockup_periods = [p.period for p in result.periods if p.lockup_active]
    lockup_dscr = [p.dscr for p in result.periods if p.lockup_active]
    
    fig.add_trace(go.Scatter(
        x=lockup_periods,
        y=lockup_dscr,
        name="Lockup Active",
        mode="markers",
        marker=dict(color="#EF4444", size=10, symbol="x"),
    ))
    
    fig.update_layout(
        **FINANCIAL_CHART_LAYOUT,
        title="DSCR Over Time",
        yaxis_title="DSCR (x)",
        xaxis_title="Period",
    )
    fig.update_layout(config=CHART_CONFIG)
    
    return fig


def create_debt_balance_chart(result: "WaterfallResult") -> go.Figure:
    """Create senior debt balance over time."""
    if not result.periods:
        return go.Figure()
    
    # Calculate remaining senior debt balance from periods
    # We don't store balance directly, but can derive from DSRA movements
    periods = [p.period for p in result.periods]
    
    # Approximate - use cumulative principal paid
    # We'll show DSRA balance as proxy for debt paydown
    dsra_balances = [p.dsra_balance_keur for p in result.periods]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=periods,
        y=dsra_balances,
        name="DSRA Balance",
        mode="lines+markers",
        line=dict(color="#9b59b6", width=2),
        marker=dict(size=5),
    ))
    
    fig.update_layout(
        **FINANCIAL_CHART_LAYOUT,
        title="DSRA Reserve Balance Over Time",
        yaxis_title="kEUR",
        xaxis_title="Period",
    )
    fig.update_layout(config=CHART_CONFIG)
    
    return fig


def waterfall_metrics_html(result: "WaterfallResult") -> str:
    """Generate HTML summary of waterfall metrics."""
    if not result.periods:
        return "<p>No waterfall data available.</p>"
    
    return f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1rem 0;">
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Project IRR</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: #2ecc71;">{result.project_irr*100:.2f}%</div>
        </div>
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Equity IRR</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: #3498db;">{result.equity_irr*100:.2f}%</div>
        </div>
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Total Distributions</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: #e67e22;">{result.total_distribution_keur:,.0f} kEUR</div>
        </div>
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Avg DSCR</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: #9b59b6;">{result.avg_dscr:.2f}x</div>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;">
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Min DSCR</div>
            <div style="font-size: 1.2rem; font-weight: bold; color: {'#e74c3c' if result.min_dscr < 1.10 else '#2ecc71'};">{result.min_dscr:.2f}x</div>
        </div>
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Lockup Periods</div>
            <div style="font-size: 1.2rem; font-weight: bold;">{result.periods_in_lockup}</div>
        </div>
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Total Senior DS</div>
            <div style="font-size: 1.2rem; font-weight: bold;">{result.total_senior_ds_keur:,.0f} kEUR</div>
        </div>
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">Total Tax</div>
            <div style="font-size: 1.2rem; font-weight: bold;">{result.total_tax_keur:,.0f} kEUR</div>
        </div>
    </div>
    """


__all__ = [
    "create_waterfall_summary_chart",
    "create_dscr_chart", 
    "create_debt_balance_chart",
    "waterfall_metrics_html",
]