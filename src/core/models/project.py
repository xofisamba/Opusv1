"""Project information Pydantic models.

Corresponds to Excel Inputs sheet rows 2-18.
"""
from pydantic import Field, field_validator
from datetime import date
from enum import Enum
from typing import Optional

from .pydantic_base import FinancialBaseModel


class PeriodFrequency(str, Enum):
    """Period frequency matching Excel Inputs!D18."""
    SEMESTRIAL = "Semestrial"
    ANNUAL = "Annual"
    QUARTERLY = "Quarterly"


class YieldScenario(str, Enum):
    """Yield scenario selection matching Excel Inputs!D52."""
    P50 = "P_50"
    P90_10Y = "P90-10y"
    P99_1Y = "P99-1y"


class ProjectInfo(FinancialBaseModel):
    """Project metadata - basic identification and timing.

    Corresponds to Excel Inputs sheet rows 2-18.
    
    Attributes:
        name: Project name (e.g., "Oborovo Solar PV")
        company: Company name (e.g., "AKE Med")
        code: Project code (e.g., "OBR-001")
        country_iso: ISO 2-letter country code
        financial_close: Date when financial close occurs
        construction_months: Duration of construction in months
        cod_date: Commercial operation date (COD)
        horizon_years: Investment analysis horizon in years
        period_frequency: Payment frequency (Semestrial/Annual/Quarterly)
    
    Validation Rules:
        - country_iso: Must be exactly 2 uppercase letters
        - construction_months: Must be 1-60 months
        - horizon_years: Must be 10-50 years
        - cod_date: Must be after financial_close
    """
    name: str = Field(
        default="New Project",
        min_length=1,
        max_length=100,
        description="Project name"
    )
    company: str = Field(
        default="",
        min_length=0,
        max_length=100,
        description="Company name"
    )
    code: str = Field(
        default="",
        min_length=0,
        max_length=20,
        description="Project code"
    )
    country_iso: str = Field(
        default="HR",
        min_length=2,
        max_length=2,
        description="ISO 2-letter country code"
    )
    financial_close: date = Field(
        description="Date of financial close"
    )
    construction_months: int = Field(
        ge=1, le=60,
        description="Construction duration in months"
    )
    cod_date: date = Field(
        description="Commercial operation date"
    )
    horizon_years: int = Field(
        ge=10, le=50,
        description="Investment horizon in years"
    )
    period_frequency: PeriodFrequency = Field(
        default=PeriodFrequency.SEMESTRIAL,
        description="Payment period frequency"
    )

    @field_validator('country_iso')
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        """Validate country code is exactly 2 uppercase letters."""
        if len(v) != 2:
            raise ValueError("ISO kod mora biti točno 2 slova (npr. 'HR', 'DE').")
        if not v.isupper():
            raise ValueError("ISO kod mora biti napisan velikim slovima (npr. 'HR', ne 'hr').")
        return v

    @field_validator('cod_date')
    @classmethod
    def validate_cod_after_ff(cls, v: date, info) -> date:
        """Validate COD is after financial close (or construction period after)."""
        # Note: financial_close may not be set yet during partial validation
        # So we only validate if both dates are present
        if 'financial_close' in info.data and info.data['financial_close'] is not None:
            ff = info.data['financial_close']
            if v <= ff:
                raise ValueError(
                    f"Datum početka rada (COD) mora biti nakon datuma financijskog zatvaranja. "
                    f"Imate: COD={v}, FF={ff}."
                )
        return v

    def get_construction_end_date(self) -> date:
        """Calculate construction end date from financial close + construction months."""
        from dateutil.relativedelta import relativedelta
        return self.financial_close + relativedelta(months=self.construction_months)

    def get_operation_start_date(self) -> date:
        """Get operation start date (same as COD for solar/wind)."""
        return self.cod_date

    def to_project_summary(self) -> dict:
        """Get a summary dict for display in UI."""
        return {
            "project_name": self.name,
            "company": self.company,
            "code": self.code,
            "country": self.country_iso,
            "cod_date": self.cod_date.isoformat(),
            "horizon_years": self.horizon_years,
            "period_frequency": self.period_frequency.value,
        }


def create_project_info(
    name: str = "Oborovo Solar PV",
    company: str = "AKE Med",
    financial_close: date = date(2029, 6, 29),
    construction_months: int = 12,
    cod_date: date = date(2030, 6, 29),
    horizon_years: int = 30,
    country_iso: str = "HR",
) -> ProjectInfo:
    """Factory function to create ProjectInfo with defaults matching Excel."""
    return ProjectInfo(
        name=name,
        company=company,
        code="OBR-001",
        country_iso=country_iso,
        financial_close=financial_close,
        construction_months=construction_months,
        cod_date=cod_date,
        horizon_years=horizon_years,
        period_frequency=PeriodFrequency.SEMESTRIAL,
    )
