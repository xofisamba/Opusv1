"""Period Engine: transforms financial close date into a sequence of dated periods.

This module establishes the temporal axis for all financial calculations.
It generates period metadata (start/end dates, year indices, flags) matching
the structure of the Oborovo Excel CF sheet.

For Oborovo:
- Financial Close: 2029-06-29
- Construction: 12 months (ends 2030-06-29 = COD)
- Periods: Semi-annual (2 per year)
- Horizon: 30 years operation (2030-06-29 to 2060-06-29)

Excel CF sheet row 134 dates: 2030-06-30, 2030-12-31, 2031-06-30, ...
- First operation period ends June 30, 2030
- Second operation period ends Dec 31, 2030
"""
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import List
from dateutil.relativedelta import relativedelta


class PeriodFrequency(Enum):
    """Frequency of periods within a year."""
    ANNUAL = 1
    SEMESTRIAL = 2
    QUARTERLY = 4


@dataclass(frozen=True)
class PeriodMeta:
    """Immutable metadata for a single period.
    
    Attributes:
        index: 0-based period index (0=Y0-H1, 1=Y0-H2, 2=Y1-H1, etc.)
        start_date: First day of the period
        end_date: Last day of the period (inclusive)
        year_index: Calendar year counter (starts at 0 for first year after FC)
        period_in_year: Position within year (1=H1, 2=H2 for semi-annual)
        is_construction: True if period is during construction phase
        is_operation: True if period is during operational phase
        is_ppa_active: True if PPA tariff applies in this period
        days_in_period: Number of days in this period
        day_fraction: days_in_period / 365 (for annualizing)
    """
    index: int
    start_date: date
    end_date: date
    year_index: int
    period_in_year: int
    is_construction: bool
    is_operation: bool
    is_ppa_active: bool
    days_in_period: int
    day_fraction: float


def _semestrial_end(from_date: date, period_in_year: int) -> date:
    """Return conventional period end date for semi-annual periods.
    
    H1: ends June 30
    H2: ends December 31
    """
    if period_in_year == 1:
        return date(from_date.year, 6, 30)
    else:
        return date(from_date.year, 12, 31)


class PeriodEngine:
    """Generates period sequence from financial close to end of horizon.
    
    The model operates in semi-annual periods. From Financial Close to COD
    is treated as the construction period (Y0). After COD, operation begins.
    Each operation period is exactly 6 months.
    
    Args:
        financial_close: Date when financial close occurs (debt drawn)
        construction_months: Number of months from FC to COD
        horizon_years: Number of operational years after COD
        ppa_years: Number of years PPA tariff is active (from COD)
        frequency: Period frequency (default SEMESTRIAL for Oborovo)
    
    Example:
        >>> engine = PeriodEngine(
        ...     financial_close=date(2029, 6, 29),
        ...     construction_months=12,
        ...     horizon_years=30,
        ...     ppa_years=12
        ... )
        >>> periods = engine.periods()
        >>> # First operation period ends June 30, 2030
        >>> periods[2].end_date
        datetime.date(2030, 6, 30)
    """
    
    def __init__(
        self,
        financial_close: date,
        construction_months: int,
        horizon_years: int,
        ppa_years: int,
        frequency: PeriodFrequency = PeriodFrequency.SEMESTRIAL,
    ) -> None:
        self.fc = financial_close
        self.construction_months = construction_months
        self.horizon_years = horizon_years
        self.ppa_years = ppa_years
        self.freq = frequency
        self._cod = self._add_months(financial_close, construction_months)
        self._horizon_end = self._add_years(self._cod, horizon_years)
        self._ppa_end = self._add_years(self._cod, ppa_years)
        self._periods_per_year = frequency.value
    
    @property
    def cod(self) -> date:
        """Commercial Operation Date (end of construction)."""
        return self._cod
    
    @property
    def ppa_end(self) -> date:
        """End date of PPA tariff period."""
        return self._ppa_end
    
    @property
    def horizon_end(self) -> date:
        """End of investment horizon."""
        return self._horizon_end
    
    def _add_months(self, d: date, months: int) -> date:
        """Add months to a date."""
        return d + relativedelta(months=months)
    
    def _add_years(self, d: date, years: int) -> date:
        """Add years to a date."""
        return d + relativedelta(years=years)
    
    def _days_between(self, start: date, end: date) -> int:
        """Days between two dates (end - start)."""
        return (end - start).days
    
    def periods(self) -> List[PeriodMeta]:
        """Generate all periods from construction through horizon.
        
        Construction period (Y0) runs from FC to COD.
        Operation periods run from COD to horizon_end, each 6 months.
        
        Returns:
            List of PeriodMeta objects ordered by index.
            Period 0 = Y0-H1 (first half of construction year),
            Period 1 = Y0-H2 (second half of construction year),
            Period 2 = Y1-H1 (first operation half-year), etc.
        """
        periods: List[PeriodMeta] = []
        
        # === Y0: Construction period (FC to COD) ===
        # Y0 has 2 semi-annual periods spanning the 12-month construction
        y0_h1_end = self._add_months(self.fc, 6)
        y0_h2_end = self._cod
        
        # Y0-H1: FC to end of first 6 months
        days_y0h1 = self._days_between(self.fc, y0_h1_end)
        periods.append(PeriodMeta(
            index=0,
            start_date=self.fc,
            end_date=y0_h1_end,
            year_index=0,
            period_in_year=1,
            is_construction=True,
            is_operation=False,
            is_ppa_active=False,
            days_in_period=days_y0h1,
            day_fraction=days_y0h1 / 365.0,
        ))
        
        # Y0-H2: end of first 6 months to COD
        days_y0h2 = self._days_between(y0_h1_end, y0_h2_end)
        periods.append(PeriodMeta(
            index=1,
            start_date=y0_h1_end,
            end_date=y0_h2_end,
            year_index=0,
            period_in_year=2,
            is_construction=True,
            is_operation=False,
            is_ppa_active=False,
            days_in_period=days_y0h2,
            day_fraction=days_y0h2 / 365.0,
        ))
        
        # === Operation periods: COD to horizon_end ===
        # First operation period: COD to first conventional semester end
        # If COD is June 29, first period ends June 30 (next H1)
        current_date = self._cod
        period_index = 2
        year_index = 1
        period_in_year = 1  # H1
        
        while current_date < self._horizon_end:
            # Compute conventional end date for this period
            period_end = _semestrial_end(current_date, period_in_year)
            
            # Clamp to horizon end
            if period_end > self._horizon_end:
                period_end = self._horizon_end
            
            days = self._days_between(current_date, period_end)
            
            # PPA active if within PPA term
            ppa_active = current_date < self._ppa_end
            
            periods.append(PeriodMeta(
                index=period_index,
                start_date=current_date,
                end_date=period_end,
                year_index=year_index,
                period_in_year=period_in_year,
                is_construction=False,
                is_operation=True,
                is_ppa_active=ppa_active,
                days_in_period=days,
                day_fraction=days / 365.0,
            ))
            
            period_index += 1
            period_in_year = 2 if period_in_year == 1 else 1
            if period_in_year == 1:
                year_index += 1
            
            # Move to next period start (after current period end)
            if period_in_year == 1:
                # Next H1 starts Jan 1
                current_date = date(period_end.year + 1, 1, 1)
            else:
                # Next H2 starts July 1
                current_date = date(period_end.year, 7, 1)
        
        return periods
    
    def operation_periods(self) -> List[PeriodMeta]:
        """Returns only operation periods (excludes construction)."""
        return [p for p in self.periods() if p.is_operation]
    
    def ppa_periods(self) -> List[PeriodMeta]:
        """Returns only PPA-active operation periods."""
        return [p for p in self.periods() if p.is_ppa_active]
    
    def period_dates(self) -> List[date]:
        """Returns end_dates for all periods (matches Excel CF row 134)."""
        return [p.end_date for p in self.periods()]

# =============================================================================
# Caching hash function (used by @st.cache_data in UI layer)
# =============================================================================

def hash_engine_for_cache(e: "PeriodEngine") -> tuple:
    """Deterministic hash for PeriodEngine - for @st.cache_data hash_funcs."""
    return (e.fc, e.construction_months, e.horizon_years, e.ppa_years, e.freq)
