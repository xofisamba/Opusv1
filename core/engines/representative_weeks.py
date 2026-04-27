"""Representative weeks selection for hybrid dispatch.

Selects 8 representative weeks (4 seasons × weekday/weekend)
that cover the annual generation variability.
Weights sum to 52 for correct annualization to yearly totals.

For projects without hourly profiles: synthetic profile generation
based on capacity factor and seasonal distribution.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass
class RepresentativeWeek:
    """One representative week of hourly generation profiles."""
    week_id: int
    weight: float  # annualization weight (all active weeks sum to 52)
    solar_profile_mw: list[float]  # 168 hourly values (MW)
    wind_profile_mw: list[float]  # 168 hourly values (MW)
    price_profile_eur_mwh: list[float]  # 168 hourly prices


def synthetic_solar_week(
    capacity_mw: float,
    capacity_factor_annual: float,
    week_season: str,  # "winter" | "spring" | "summer" | "autumn"
    day_type: str,  # "weekday" | "weekend" (for price profile)
) -> list[float]:
    """Generate synthetic hourly solar profile for one week (168h).
    Uses simplified sinusoidal model with seasonal scaling.
    """
    seasonal_cf = {"winter": 0.65, "spring": 1.00, "summer": 1.35, "autumn": 1.00}
    peak_hours = {
        "winter": (8, 17),   # 9 hours
        "spring": (7, 19),   # 12 hours
        "summer": (6, 20),   # 14 hours
        "autumn": (7, 18),   # 11 hours
    }
    cf = capacity_factor_annual * seasonal_cf[week_season]
    start_h, end_h = peak_hours[week_season]
    day_hours = end_h - start_h
    profile = []
    for day in range(7):
        for hour in range(24):
            if start_h <= hour < end_h:
                angle = math.pi * (hour - start_h) / day_hours
                # π/2 factor makes avg(24h) = capacity × cf (matches annual CF)
                gen = capacity_mw * cf * (math.pi / 2) * (24 / day_hours) * math.sin(angle)
                gen = max(0.0, gen)
            else:
                gen = 0.0
            profile.append(gen)
    return profile


def synthetic_wind_week(
    capacity_mw: float,
    capacity_factor_annual: float,
    week_season: str,
) -> list[float]:
    """Generate synthetic hourly wind profile for one week (168h).
    Diurnal pattern around annual CF average (no seasonal scaling —
    seasonal factors would distort annual CF matching).
    """
    diurnal = [
        1.10, 1.12, 1.14, 1.15, 1.13, 1.10,  # 00-06
        1.05, 1.00, 0.95, 0.92, 0.90, 0.92,  # 06-12
        0.95, 0.98, 1.00, 1.02, 1.05, 1.08,  # 12-18
        1.10, 1.11, 1.12, 1.13, 1.12, 1.11,  # 18-24
    ]
    # Normalize so avg(diurnal) = 1.0 (so avg power = capacity × CF)
    diurnal_avg = sum(diurnal) / len(diurnal)
    diurnal = [d / diurnal_avg for d in diurnal]
    
    cf = min(capacity_factor_annual, 0.95)
    profile = []
    for day in range(7):
        for hour in range(24):
            gen = capacity_mw * cf * diurnal[hour]
            gen = max(0.0, min(capacity_mw, gen))
            profile.append(gen)
    return profile


def synthetic_price_week(
    base_price_eur_mwh: float,
    week_season: str,
    day_type: str,
) -> list[float]:
    """Generate synthetic hourly price profile for one week (168h).
    Double-peak pattern (morning + evening peaks).
    """
    weekday_pattern = [
        0.70, 0.65, 0.62, 0.60, 0.62, 0.70,  # 00-06 (night)
        0.85, 1.10, 1.30, 1.20, 1.05, 0.95,  # 06-12 (morning peak)
        0.90, 0.85, 0.88, 0.92, 1.00, 1.25,  # 12-18 (afternoon)
        1.40, 1.35, 1.20, 1.05, 0.90, 0.75,  # 18-24 (evening peak)
    ]
    seasonal_adj = {"winter": 1.15, "spring": 0.95, "summer": 1.05, "autumn": 1.00}
    day_multiplier = 1.0 if day_type == "weekday" else 0.85
    adj = seasonal_adj[week_season] * day_multiplier
    profile = []
    for day in range(7):
        pattern = weekday_pattern if day < 5 else [0.80 + 0.20 * p for p in weekday_pattern]
        for hour in range(24):
            profile.append(max(0.0, base_price_eur_mwh * pattern[hour] * adj))
    return profile


# 8 aktivnih tjedana — weights sumiraju na 52
REPRESENTATIVE_WEEK_SPECS = [
    # (week_id, season, day_type, weight)
    (1, "winter", "weekday", 9.0),
    (2, "winter", "weekend", 4.0),
    (3, "spring", "weekday", 9.0),
    (4, "spring", "weekend", 4.0),
    (5, "summer", "weekday", 9.0),
    (6, "summer", "weekend", 4.0),
    (7, "autumn", "weekday", 9.0),
    (8, "autumn", "weekend", 4.0),
]
# Provjera: 4 × (9 + 4) = 52


def generate_representative_weeks(
    solar_capacity_mw: float,
    wind_capacity_mw: float,
    solar_cf_annual: float,
    wind_cf_annual: float,
    spot_price_eur_mwh: float = 60.0,
) -> list[RepresentativeWeek]:
    """Generate 8 representative weeks for LP dispatch.
    All weeks have weight > 0 and weights sum to 52.
    """
    weeks = []
    for week_id, season, day_type, weight in REPRESENTATIVE_WEEK_SPECS:
        solar = (
            synthetic_solar_week(solar_capacity_mw, solar_cf_annual, season, day_type)
            if solar_capacity_mw > 0 else [0.0] * 168
        )
        wind = (
            synthetic_wind_week(wind_capacity_mw, wind_cf_annual, season)
            if wind_capacity_mw > 0 else [0.0] * 168
        )
        price = synthetic_price_week(spot_price_eur_mwh, season, day_type)
        weeks.append(RepresentativeWeek(
            week_id=week_id,
            weight=weight,
            solar_profile_mw=solar,
            wind_profile_mw=wind,
            price_profile_eur_mwh=price,
        ))
    return weeks