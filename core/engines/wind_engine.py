"""Wind Engine — OpusCore v2 Phase 1 Task 1.1.

Pure functions for wind generation modeling:
- Weibull wind speed distribution
- Power curve interpolation
- Annual energy production (AEP)
- Degradation and P-value calculations
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
import math


def weibull_pdf(v: float, k: float, A: float) -> float:
    """Weibull probability density function.
    
    Args:
        v: Wind speed (m/s)
        k: Shape parameter (dimensionless)
        A: Scale parameter (m/s)
    
    Returns:
        Probability density at wind speed v.
    """
    if v <= 0 or A <= 0:
        return 0.0
    return (k / A) * (v / A) ** (k - 1) * math.exp(-((v / A) ** k))


def hub_height_correction(
    v_ref: float,
    h_ref: float,
    h_hub: float,
    alpha: float = 0.14,
) -> float:
    """Power law shear correction for hub height.
    
    Args:
        v_ref: Reference wind speed at h_ref (m/s)
        h_ref: Reference height (m)
        h_hub: Hub height (m)
        alpha: Shear exponent (default 0.14 for open terrain)
    
    Returns:
        Wind speed at hub height.
    """
    return v_ref * (h_hub / h_ref) ** alpha


def weibull_scale_from_mean(v_mean: float, k: float) -> float:
    """Compute Weibull scale parameter A from mean wind speed.
    
    Args:
        v_mean: Mean wind speed (m/s)
        k: Shape parameter (dimensionless)
    
    Returns:
        Scale parameter A (m/s).
    """
    from scipy.special import gamma as gamma_fn
    return v_mean / gamma_fn(1 + 1 / k)


def power_curve_interpolate(
    v_ms: float,
    points: list[Tuple[float, float]],
) -> float:
    """Piecewise-linear interpolation of power curve.
    
    Args:
        v_ms: Wind speed (m/s)
        points: Sorted list of (wind_speed_ms, power_kw) pairs.
    
    Returns:
        Interpolated power in kW. Returns 0 below cut-in or above cut-out.
    """
    if not points or v_ms <= 0:
        return 0.0
    if v_ms < points[0][0]:
        return 0.0
    if v_ms > points[-1][0]:
        return 0.0
    for i in range(len(points) - 1):
        v0, p0 = points[i]
        v1, p1 = points[i + 1]
        if v0 <= v_ms <= v1:
            if v1 == v0:
                return p0
            return p0 + (p1 - p0) * (v_ms - v0) / (v1 - v0)
    return 0.0


@dataclass(frozen=True)
class AEPResult:
    """Annual energy production result."""
    gross_aep_mwh: float
    net_aep_mwh: float
    capacity_factor_gross: float
    capacity_factor_net: float
    hub_height_wind_speed: float
    loss_breakdown: dict[str, float]


def annual_energy_production(
    v_mean_ms: float,
    k_shape: float,
    h_ref_m: float,
    h_hub_m: float,
    power_curve: list[Tuple[float, float]],
    installed_capacity_mw: float,
    alpha: float = 0.14,
    wake_loss: float = 0.08,
    availability: float = 0.97,
    curtailment: float = 0.02,
    electrical_loss: float = 0.02,
    icing_soiling: float = 0.01,
    v_bins: int = 100,
) -> AEPResult:
    """Compute annual energy production using Weibull distribution.
    
    AEP = Σ_v P(v) × 8760 × f_Weibull(v) × Δv
    Numerical integration with v_bins steps from 0 to 30 m/s.
    
    Args:
        v_mean_ms: Mean wind speed at reference height (m/s)
        k_shape: Weibull shape parameter (dimensionless, typical 2.0)
        h_ref_m: Reference anemometer height (m)
        h_hub_m: Turbine hub height (m)
        power_curve: List of (wind_speed_ms, power_kw) points
        installed_capacity_mw: Installed capacity (MW)
        alpha: Shear exponent (default 0.14)
        wake_loss: Wake losses fraction (default 0.08)
        availability: Availability fraction (default 0.97)
        curtailment: Curtailment fraction (default 0.02)
        electrical_loss: Electrical losses fraction (default 0.02)
        icing_soiling: Icing/soiling losses fraction (default 0.01)
        v_bins: Number of integration bins (default 100)
    
    Returns:
        AEPResult with gross/net AEP and loss breakdown.
    """
    v_hub = hub_height_correction(v_mean_ms, h_ref_m, h_hub_m, alpha)
    A = weibull_scale_from_mean(v_hub, k_shape)

    dv = 30.0 / v_bins
    gross_mwh = 0.0
    for i in range(v_bins):
        v = (i + 0.5) * dv
        pdf_val = weibull_pdf(v, k_shape, A)
        power_kw = power_curve_interpolate(v, power_curve)
        gross_mwh += power_kw / 1000 * 8760 * pdf_val * dv

    net_mwh = (
        gross_mwh
        * (1 - wake_loss)
        * availability
        * (1 - curtailment)
        * (1 - electrical_loss)
        * (1 - icing_soiling)
    )

    losses = {
        "wake": gross_mwh * wake_loss,
        "availability": gross_mwh * (1 - wake_loss) * (1 - availability),
        "curtailment": gross_mwh * (1 - wake_loss) * availability * curtailment,
        "electrical": (
            gross_mwh
            * (1 - wake_loss)
            * availability
            * (1 - curtailment)
            * electrical_loss
        ),
        "icing_soiling": (
            gross_mwh
            * (1 - wake_loss)
            * availability
            * (1 - curtailment)
            * (1 - electrical_loss)
            * icing_soiling
        ),
    }

    hours = 8760
    cf_gross = gross_mwh / (installed_capacity_mw * hours) if installed_capacity_mw > 0 else 0
    cf_net = net_mwh / (installed_capacity_mw * hours) if installed_capacity_mw > 0 else 0

    return AEPResult(
        gross_aep_mwh=gross_mwh,
        net_aep_mwh=net_mwh,
        capacity_factor_gross=cf_gross,
        capacity_factor_net=cf_net,
        hub_height_wind_speed=v_hub,
        loss_breakdown=losses,
    )


def degradation_schedule(
    net_aep_y1_mwh: float,
    annual_degradation_rate: float = 0.005,
    horizon_years: int = 30,
) -> list[float]:
    """Compound degradation schedule: aep_t = net_aep_y1 × (1 - rate)^(t-1).
    
    Args:
        net_aep_y1_mwh: Year 1 net AEP (MWh)
        annual_degradation_rate: Annual degradation rate (default 0.5%)
        horizon_years: Investment horizon (default 30)
    
    Returns:
        List of annual AEP values for years 1..N.
    """
    return [
        net_aep_y1_mwh * (1 - annual_degradation_rate) ** (t - 1)
        for t in range(1, horizon_years + 1)
    ]


def p_value_from_p50(
    p50_aep_mwh: float,
    sigma_resource_pct: float = 0.06,
    sigma_loss_pct: float = 0.04,
    sigma_ti_pct: float = 0.02,
    percentile: float = 90,
    single_year: bool = True,
    n_years: int = 10,
) -> float:
    """P-value calculation from P50 and uncertainty parameters.
    
    Args:
        p50_aep_mwh: P50 annual energy production (MWh)
        sigma_resource_pct: Resource uncertainty (default 6%)
        sigma_loss_pct: Loss uncertainty (default 4%)
        sigma_ti_pct: Turbulence intensity uncertainty (default 2%)
        percentile: Target percentile (default 90 for P90)
        single_year: If True, single-year P90; if False, 10-year average
        n_years: Number of years for multi-year average (default 10)
    
    Returns:
        P-value (e.g., P90) in MWh.
    """
    from scipy.stats import norm
    sigma_total = math.sqrt(
        sigma_resource_pct ** 2
        + sigma_loss_pct ** 2
        + sigma_ti_pct ** 2
    )
    if not single_year:
        sigma_total = sigma_total / math.sqrt(n_years)
    z = norm.ppf(percentile / 100)
    return p50_aep_mwh * (1 - z * sigma_total)


@dataclass(frozen=True)
class PowerCurve:
    """Wind turbine power curve."""
    turbine_name: str
    rated_power_kw: float
    cut_in_ms: float
    cut_out_ms: float
    points: Tuple[Tuple[float, float], ...]

    @classmethod
    def from_csv_string(cls, csv_content: str, turbine_name: str) -> "PowerCurve":
        """Parse CSV format: wind_speed_ms,power_kw (header line required).
        
        Args:
            csv_content: CSV string with header and data rows
            turbine_name: Name for this turbine model
        
        Returns:
            PowerCurve instance.
        """
        lines = csv_content.strip().splitlines()
        points = []
        for line in lines[1:]:  # skip header
            parts = line.strip().split(',')
            if len(parts) >= 2:
                v, p = float(parts[0]), float(parts[1])
                points.append((v, p))
        points.sort(key=lambda x: x[0])
        rated = max(p for _, p in points) if points else 0
        cut_in = points[0][0] if points else 0
        cut_out = points[-1][0] if points else 25
        return cls(
            turbine_name=turbine_name,
            rated_power_kw=rated,
            cut_in_ms=cut_in,
            cut_out_ms=cut_out,
            points=tuple(points),
        )

    def power_at(self, v_ms: float) -> float:
        """Power output at given wind speed."""
        return power_curve_interpolate(v_ms, list(self.points))


# Generic fallback — 6 MW Class 3 turbine (synthetic, no vendor name)
GENERIC_6MW_CLASS3: PowerCurve = PowerCurve(
    turbine_name="Generic 6MW Class 3",
    rated_power_kw=6000.0,
    cut_in_ms=3.0,
    cut_out_ms=25.0,
    points=(
        (3.0, 0), (4.0, 80), (5.0, 250), (6.0, 600),
        (7.0, 1100), (8.0, 1800), (9.0, 2700), (10.0, 3700),
        (11.0, 4800), (12.0, 5500), (13.0, 5900), (14.0, 6000),
        (25.0, 6000), (25.1, 0),
    ),
)


def wind_generation_schedule(
    aep_result: AEPResult,
    horizon_years: int,
    annual_degradation: float = 0.005,
    periods_per_year: int = 2,
) -> dict[int, float]:
    """Build period-indexed generation schedule compatible with waterfall engine.
    
    Args:
        aep_result: AEP result from annual_energy_production()
        horizon_years: Investment horizon
        annual_degradation: Annual degradation rate
        periods_per_year: Periods per year (default 2 for semi-annual)
    
    Returns:
        Dict mapping period_index (starting at 2) to generation (MWh).
        Periods 0 and 1 are construction — not included.
    """
    annual = degradation_schedule(
        aep_result.net_aep_mwh, annual_degradation, horizon_years
    )
    schedule = {}
    for year_idx, aep_year in enumerate(annual, start=1):
        for h in range(periods_per_year):
            period_index = 2 + (year_idx - 1) * periods_per_year + h
            schedule[period_index] = aep_year / periods_per_year
    return schedule
