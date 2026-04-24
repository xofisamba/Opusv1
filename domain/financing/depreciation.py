"""Depreciation — financial vs tax, straight-line vs declining balance.

HR porezni zakon (NN 177/04, 106/18, 148/18):
- Solarne elektrane: 20 godina (5% godišnje)
- Vjetroelektrane: 20 godina (5% godišnje)
- BESS: 10 godina (10% godišnje)
- Zgrade/infrastr.: 25 godina (4% godišnje)

Financial depreciation može biti kraća ili duža od tax depreciation.
Za investitore/banku: koristi se financial life za EBITDA margin i P&L.
Za tax: koristi se tax life za tax shield calculation.
"""
from dataclasses import dataclass
from typing import Sequence

from domain.period_engine import PeriodMeta


@dataclass(frozen=True)
class DepreciationParams:
    """Odvojeni parametri za financijsku i poreznu amortizaciju."""
    # Financijska amortizacija (za investitora / banku)
    financial_life_years: int  # 30 za solar, 25 za wind
    financial_method: str = "straight_line"  # straight_line | declining_balance
    financial_residual_pct: float = 0.0

    # Porezna amortizacija (HR zakon — različita od financijske)
    tax_life_years: int = 20  # HR NN 177/04: 20g solar/wind, 10g BESS
    tax_method: str = "straight_line"
    tax_residual_pct: float = 0.0

    @staticmethod
    def create_solar_hr() -> "DepreciationParams":
        """Solar — 30g financial, 20g tax (HR)."""
        return DepreciationParams(
            financial_life_years=30,
            tax_life_years=20,
        )

    @staticmethod
    def create_wind_hr() -> "DepreciationParams":
        """Wind — 25g financial, 20g tax (HR)."""
        return DepreciationParams(
            financial_life_years=25,
            tax_life_years=20,
        )

    @staticmethod
    def create_bess_hr() -> "DepreciationParams":
        """BESS — 15g financial, 10g tax (HR)."""
        return DepreciationParams(
            financial_life_years=15,
            tax_life_years=10,
        )


def financial_depreciation_schedule(
    capex_keur: float,
    params: DepreciationParams,
    horizon_years: int,
) -> list[float]:
    """Godišnja financijska amortizacija u kEUR (straight-line)."""
    if params.financial_life_years <= 0:
        return [0.0] * horizon_years

    if params.financial_method == "straight_line":
        annual = capex_keur / params.financial_life_years
        return [
            annual if y <= params.financial_life_years else 0.0
            for y in range(1, horizon_years + 1)
        ]
    elif params.financial_method == "declining_balance":
        rate = 1.0 / params.financial_life_years * 2  # Double declining
        balance = capex_keur
        schedule = []
        for y in range(1, horizon_years + 1):
            if y <= params.financial_life_years:
                dep = balance * rate
                balance -= dep
                schedule.append(dep)
            else:
                schedule.append(0.0)
        return schedule
    else:
        raise ValueError(f"Unknown method: {params.financial_method}")


def tax_depreciation_schedule(
    capex_keur: float,
    params: DepreciationParams,
    horizon_years: int,
) -> list[float]:
    """Godišnja porezna amortizacija u kEUR (HR zakon)."""
    if params.tax_life_years <= 0:
        return [0.0] * horizon_years

    if params.tax_method == "straight_line":
        annual = capex_keur / params.tax_life_years
        return [
            annual if y <= params.tax_life_years else 0.0
            for y in range(1, horizon_years + 1)
        ]
    elif params.tax_method == "declining_balance":
        rate = 1.0 / params.tax_life_years * 2  # Double declining
        balance = capex_keur
        schedule = []
        for y in range(1, horizon_years + 1):
            if y <= params.tax_life_years:
                dep = balance * rate
                balance -= dep
                schedule.append(dep)
            else:
                schedule.append(0.0)
        return schedule
    else:
        raise ValueError(f"Unknown method: {params.tax_method}")


def semi_annual_depreciation(
    annual_schedule: list[float],
    periods: Sequence[PeriodMeta],
) -> dict[int, float]:
    """Pretvori godišnji raspored u polu-godišnji po period indeksu.

    Args:
        annual_schedule: Godišnji raspored (index 0 = Y1)
        periods: Sequence of PeriodMeta

    Returns:
        Dict mapping period_index → depreciation in kEUR
    """
    result = {}
    for p in periods:
        if not p.is_operation:
            result[p.index] = 0.0
        else:
            year_dep = (
                annual_schedule[p.year_index - 1]
                if p.year_index <= len(annual_schedule)
                else 0.0
            )
            result[p.index] = year_dep / 2  # Split 50/50 H1/H2
    return result


def financial_depreciation_period(
    capex_keur: float,
    params: DepreciationParams,
    periods: Sequence[PeriodMeta],
) -> dict[int, float]:
    """Financial depreciation schedule po periodu (kEUR)."""
    annual = financial_depreciation_schedule(capex_keur, params, len(periods))
    return semi_annual_depreciation(annual, periods)


def tax_depreciation_period(
    capex_keur: float,
    params: DepreciationParams,
    periods: Sequence[PeriodMeta],
) -> dict[int, float]:
    """Tax depreciation schedule po periodu (kEUR)."""
    annual = tax_depreciation_schedule(capex_keur, params, len(periods))
    return semi_annual_depreciation(annual, periods)
