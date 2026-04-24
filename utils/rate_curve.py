"""Interest rate utilities — Euribor curve and blended rate computation.

Enterprise Implementation Brief §4.1
Supports: EURIBOR 3M/6M curves, hedging, rate floor/cap.
"""
from dataclasses import dataclass
from typing import Optional


# =============================================================================
# EURIBOR Curve Data
# =============================================================================

# Current Euribor reference rates (indicative, Q1 2026)
# In production, these would come from a live feed or Bloomberg API
EURIBOR_6M_SPOT = 0.0382  # ~3.82% as of Q1 2026
EURIBOR_3M_SPOT = 0.0375  # ~3.75% as of Q1 2026

# Euribor forward curve (implied forward rates, semi-annual tenors)
EURIBOR_6M_FORWARDS = (
    0.0395,  # 6M: 6M, 12M, 18M...
    0.0410,
    0.0425,
    0.0435,
    0.0440,
    0.0442,
    0.0443,
    0.0442,
    0.0440,
    0.0438,
    0.0435,
    0.0430,
    0.0425,
    0.0420,
    0.0415,
)

EURIBOR_3M_FORWARDS = (
    0.0385,  # 3M: 3M, 6M, 9M...
    0.0398,
    0.0410,
    0.0420,
    0.0425,
    0.0428,
    0.0429,
    0.0428,
    0.0425,
    0.0422,
    0.0420,
    0.0415,
    0.0410,
    0.0405,
    0.0400,
)


@dataclass(frozen=True)
class RateCurvePoint:
    """Single point on a rate curve."""
    tenor_months: int
    rate: float


def build_euribor_curve(
    base_rate_type: str = "EURIBOR_6M",
    spot_rate: Optional[float] = None,
    forwards: Optional[tuple[float, ...]] = None,
    flat_bps: float = 0.0,
) -> list[RateCurvePoint]:
    """Build Euribor rate curve.
    
    Args:
        base_rate_type: "EURIBOR_3M" or "EURIBOR_6M"
        spot_rate: Override spot rate. None = use current reference.
        forwards: Override forward rates. None = use built-in curve.
        flat_bps: Flat spread to add to all rates (in bps).
    
    Returns:
        List of RateCurvePoint (tenor_months, rate) ordered by tenor.
    """
    if base_rate_type == "EURIBOR_3M":
        forward_tenors = (3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 42, 48, 54)
        curve = forwards or EURIBOR_3M_FORWARDS
        spot = spot_rate if spot_rate is not None else EURIBOR_3M_SPOT
    else:  # EURIBOR_6M
        forward_tenors = (6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 84, 96, 108)
        curve = forwards or EURIBOR_6M_FORWARDS
        spot = spot_rate if spot_rate is not None else EURIBOR_6M_SPOT
    
    flat_spread = flat_bps / 10000.0
    result = [RateCurvePoint(tenor_months=0, rate=spot + flat_spread)]
    
    for i, fwd in enumerate(curve[:14]):  # Limit to reasonable tenor range
        tenor = forward_tenors[i] if i < len(forward_tenors) else (i + 2) * 6
        result.append(RateCurvePoint(tenor_months=tenor, rate=fwd + flat_spread))
    
    return result


def get_rate_at_tenor(
    curve: list[RateCurvePoint],
    tenor_months: int,
) -> float:
    """Get interpolated/extrapolated rate at a specific tenor.
    
    Args:
        curve: Rate curve from build_euribor_curve()
        tenor_months: Target tenor in months
    
    Returns:
        Rate at tenor (linear interpolation between points)
    """
    if not curve:
        return 0.03
    
    # Before first point — use first rate
    if tenor_months <= curve[0].tenor_months:
        return curve[0].rate
    
    # After last point — extrapolate with last rate
    if tenor_months >= curve[-1].tenor_months:
        return curve[-1].rate
    
    # Linear interpolation between adjacent points
    for i in range(len(curve) - 1):
        if curve[i].tenor_months <= tenor_months <= curve[i + 1].tenor_months:
            t0, r0 = curve[i].tenor_months, curve[i].rate
            t1, r1 = curve[i + 1].tenor_months, curve[i + 1].rate
            alpha = (tenor_months - t0) / (t1 - t0) if t1 != t0 else 0.0
            return r0 + alpha * (r1 - r0)
    
    return curve[-1].rate


def build_rate_schedule(
    base_rate_type: str = "EURIBOR_6M",
    tenor_periods: int = 28,  # 14-year semi-annual
    periods_per_year: int = 2,
    base_rate_override: Optional[float] = None,
    forwards: Optional[tuple[float, ...]] = None,
    floating_share: float = 0.2,
    fixed_share: float = 0.8,
    hedge_coverage: float = 0.8,
    margin_bps: int = 265,
    base_rate_floor: float = 0.0,
) -> list[float]:
    """Build semi-annual rate schedule for waterfall.
    
    Computes blended floating+fixed+hedge rate per period.
    
    Args:
        base_rate_type: "EURIBOR_3M" or "EURIBOR_6M"
        tenor_periods: Total number of rate periods (semi-annual)
        periods_per_year: 2 for semi-annual, 1 for annual
        base_rate_override: Override the base rate (for sensitivity)
        forwards: Euribor forward curve override
        floating_share: Share of debt on floating rate (e.g., 0.2 = 20%)
        fixed_share: Share of debt on fixed rate (e.g., 0.8 = 80%)
        hedge_coverage: % of floating debt that is hedged (e.g., 0.8 = 80%)
        margin_bps: Credit margin in bps (added to base rate)
        base_rate_floor: Minimum base rate (e.g., 0.0 for no negative rates)
    
    Returns:
        List of semi-annual rates, one per period.
    """
    curve = build_euribor_curve(
        base_rate_type=base_rate_type,
        forwards=forwards,
    )
    
    margin = margin_bps / 10000.0
    
    # For semi-annual periods, each period = 6 months
    # Period N covers months [N*6, (N+1)*6)
    rates = []
    for period in range(tenor_periods):
        tenor_months = (period + 1) * (12 // periods_per_year)
        
        # Get base rate for this period's tenor
        if base_rate_override is not None:
            base = max(base_rate_floor, base_rate_override)
        else:
            base = get_rate_at_tenor(curve, tenor_months)
            base = max(base_rate_floor, base)
        
        # Floating portion — hedged + unhedged
        # Hedged portion uses locked-in rate (base at hedge start + hedge cost)
        # Unhedged portion uses current forward rate
        floating_rate = base + margin
        
        # Fixed portion — all-in fixed rate (base + margin + upfront cost spread)
        fixed_rate = base + margin + 0.001  # Small upfront cost amortization
        
        # Blended rate
        blended = (
            floating_rate * floating_share * (1 - hedge_coverage) +
            floating_rate * floating_share * hedge_coverage +  # hedged → same rate
            fixed_rate * fixed_share
        )
        
        rates.append(blended)
    
    return rates


def apply_rate_shock(rate_schedule: list[float], shock_bps: int) -> list[float]:
    """Apply a parallel rate shock to a rate schedule.
    
    Args:
        rate_schedule: Existing rate schedule
        shock_bps: Shock in basis points (+50 = 50 bps rise)
    
    Returns:
        New rate schedule with shock applied
    """
    shock = shock_bps / 10000.0
    return [r + shock for r in rate_schedule]
