"""Input validation for sidebar session state.

Provides pure functions (no Streamlit calls) for validating inputs.
Results are returned as ValidationResult dataclass.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """Result of input validation."""
    errors: list[str]
    warnings: list[str]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def validate_session_inputs(s) -> ValidationResult:
    """Validate sidebar session state inputs.

    Pure function — no Streamlit calls. Call this before
    _build_inputs_from_session() and use results to display errors.

    Args:
        s: Session state dict-like object

    Returns:
        ValidationResult with errors and warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Yield validation: P90 must be less than P50
    p50 = s.get('yield_p50', 0)
    p90 = s.get('yield_p90', 0)
    if p90 >= p50:
        errors.append(
            f"P90 yield ({p90:.0f} hrs) must be less than "
            f"P50 ({p50:.0f} hrs)."
        )

    # Gearing validation
    # Note: slider stores as percent (0-95), need to check if > 1 to detect percent form
    gearing = s.get('gearing_ratio', 0)
    if gearing > 1.0:
        gearing_frac = gearing / 100.0  # Convert percent to fraction
    else:
        gearing_frac = gearing

    if gearing_frac > 0.90:
        errors.append(
            f"Gearing {gearing_frac:.1%} exceeds 90% — "
            "DSCR covenant cannot be met."
        )
    elif gearing_frac > 0.80:
        warnings.append(
            f"Gearing {gearing_frac:.1%} is high — recommended < 80%."
        )

    # PPA term validation
    ppa_term = s.get('ppa_term', 0)
    horizon = s.get('investment_horizon', 30)
    if ppa_term > horizon:
        errors.append(
            f"PPA term ({ppa_term}y) cannot exceed horizon ({horizon}y)."
        )

    # Capacity validation
    if s.get('technology') == 'Solar':
        capacity = s.get('capacity_dc', 0)
    else:
        capacity = s.get('wind_capacity', 0)

    if capacity <= 0:
        errors.append(f"Capacity must be positive, got {capacity}.")

    if capacity > 500:
        warnings.append(f"Capacity {capacity} MW is very large — check input.")

    # Tariff validation
    tariff = s.get('ppa_base_tariff', 0)
    if tariff <= 0:
        errors.append(f"PPA tariff must be positive, got {tariff}.")

    if tariff > 500:
        warnings.append(f"PPA tariff {tariff} €/MWh is very high.")

    # Base rate validation
    base_rate = s.get('base_rate', 0)
    if base_rate > 1.0:
        base_rate_frac = base_rate / 100.0
    else:
        base_rate_frac = base_rate

    if base_rate_frac < 0 or base_rate_frac > 0.30:
        errors.append(
            f"Base rate {base_rate_frac:.2%} is outside reasonable range (0-30%)."
        )

    # Debt tenor validation
    debt_tenor = s.get('debt_tenor', 0)
    if debt_tenor < 1 or debt_tenor > 30:
        errors.append(f"Debt tenor must be 1-30 years, got {debt_tenor}.")

    # Target DSCR validation
    target_dscr = s.get('target_dscr', 1.15)
    if target_dscr < 1.0 or target_dscr > 3.0:
        errors.append(
            f"Target DSCR {target_dscr:.2f}x is outside reasonable range (1.0-3.0x)."
        )

    # Construction period validation
    const_period = s.get('construction_period', 12)
    if const_period < 1 or const_period > 60:
        errors.append(
            f"Construction period must be 1-60 months, got {const_period}."
        )

    return ValidationResult(errors=errors, warnings=warnings)


def validate_inputs_with_errors(s) -> Optional[str]:
    """Convenience wrapper: returns first error or None.

    Use this when you only need to know if there's an error,
    not the full list. For display, use validate_session_inputs().

    Args:
        s: Session state dict-like object

    Returns:
        First error message, or None if valid
    """
    result = validate_session_inputs(s)
    return result.errors[0] if result.errors else None