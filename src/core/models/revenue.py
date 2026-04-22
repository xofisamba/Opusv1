"""Technical and Revenue Pydantic models.

TechnicalParams: Corresponds to Excel Inputs rows 51-68.
RevenueParams: Corresponds to Excel Inputs rows 78-141.
"""
from pydantic import Field, field_validator, computed_field
from typing import Optional

from .pydantic_base import FinancialBaseModel


class TechnicalParams(FinancialBaseModel):
    """Technical parameters for the project.

    Corresponds to Excel Inputs rows 51-68.

    Validation Rules:
        - capacity_mw: Must be > 0
        - yield_scenario: Must be one of P_50, P90-10y, P99-1y
        - operating_hours_p50/p90_10y: Must be > 0
        - pv_degradation: Must be 0.0-0.20 (0-20%)
        - plant_availability: Must be 0.80-1.00 (80-100%)
        - grid_availability: Must be 0.80-1.00 (80-100%)
    """
    capacity_mw: float = Field(
        gt=0,
        description="Installed capacity in MW (Inputs!D51)"
    )
    yield_scenario: str = Field(
        default="P_50",
        description="Yield scenario: P_50, P90-10y, P99-1y (Inputs!D52)"
    )
    operating_hours_p50: float = Field(
        gt=0,
        description="P50 yield hours (Inputs!D64)"
    )
    operating_hours_p90_10y: float = Field(
        gt=0,
        description="P90-10y yield hours (Inputs!D68)"
    )
    pv_degradation: float = Field(
        default=0.004,
        ge=0.0, le=0.20,
        description="Annual PV degradation (Inputs!D56)"
    )
    bess_degradation: float = Field(
        default=0.003,
        ge=0.0, le=0.20,
        description="BESS degradation (Inputs!D57)"
    )
    plant_availability: float = Field(
        default=0.99,
        ge=0.80, le=1.00,
        description="Plant availability (Inputs!D58)"
    )
    grid_availability: float = Field(
        default=0.99,
        ge=0.80, le=1.00,
        description="Grid availability (Inputs!D59)"
    )
    bess_enabled: bool = Field(
        default=False,
        description="BESS enabled flag (Inputs!D140)"
    )

    @field_validator('yield_scenario')
    @classmethod
    def validate_yield_scenario(cls, v: str) -> str:
        valid = {"P_50", "P90-10y", "P99-1y"}
        if v not in valid:
            raise ValueError(
                f"yield_scenario='{v}' nije validan. "
                f"Dopuštene opcije: {', '.join(valid)}."
            )
        return v

    @field_validator('plant_availability', 'grid_availability')
    @classmethod
    def validate_availability(cls, v: float) -> float:
        if v < 0.80 or v > 1.00:
            raise ValueError(
                f"availability={v} nije validan. "
                f"Mora biti između 0.80 (80%) i 1.00 (100%)."
            )
        return v

    @computed_field
    @property
    def combined_availability(self) -> float:
        """Combined plant × grid availability."""
        return self.plant_availability * self.grid_availability

    @computed_field
    @property
    def combined_availability_percent(self) -> str:
        """Combined availability as percentage string."""
        return f"{self.combined_availability:.1%}"

    def get_technical_summary(self) -> dict:
        """Get technical summary for display."""
        return {
            "capacity_mw": self.capacity_mw,
            "yield_scenario": self.yield_scenario,
            "operating_hours": self.operating_hours_p50,
            "combined_availability": self.combined_availability_percent,
            "annual_degradation": f"{self.pv_degradation:.2%}",
        }


class RevenueParams(FinancialBaseModel):
    """Revenue parameters including PPA and market pricing.

    Corresponds to Excel Inputs rows 78-141.

    Validation Rules:
        - ppa_base_tariff: Must be >= 0
        - ppa_term_years: Must be 1-30
        - ppa_index: Must be -0.50 to +0.50 (-50% to +50%)
        - ppa_production_share: Must be 0.0-1.0
        - market_prices_curve: If provided, must have exactly horizon_years values
        - market_inflation: Must be -0.50 to +0.50
        - balancing_cost_pv/bess: Must be 0.0-0.50 (0-50%)
        - co2_price_eur: Must be >= 0
    """
    ppa_base_tariff: float = Field(
        ge=0,
        description="Base PPA tariff in €/MWh (Inputs!D78)"
    )
    ppa_term_years: int = Field(
        ge=1, le=30,
        description="PPA term in years (Inputs!D81)"
    )
    ppa_index: float = Field(
        default=0.02,
        ge=-0.50, le=0.50,
        description="PPA annual index (Inputs!D83)"
    )
    ppa_production_share: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="Share of production in PPA (Inputs!D80)"
    )
    market_scenario: str = Field(
        default="Central",
        description="Market scenario name (Inputs!B103)"
    )
    market_prices_curve: tuple[float, ...] = Field(
        default_factory=tuple,
        description="Market price curve for years 1-30 in €/MWh"
    )
    market_inflation: float = Field(
        default=0.02,
        ge=-0.50, le=0.50,
        description="Market price inflation (Inputs!B129)"
    )
    balancing_cost_pv: float = Field(
        default=0.025,
        ge=0.0, le=0.50,
        description="PV balancing cost % (Inputs!D114)"
    )
    balancing_cost_bess: float = Field(
        default=0.025,
        ge=0.0, le=0.50,
        description="BESS balancing cost % (Inputs!D115)"
    )
    co2_enabled: bool = Field(
        default=False,
        description="CO2 certificates enabled (Inputs!D139)"
    )
    co2_price_eur: float = Field(
        default=1.5,
        ge=0,
        description="CO2 price in €/ton (Inputs!E141)"
    )

    @field_validator('ppa_term_years')
    @classmethod
    def validate_ppa_term(cls, v: int) -> int:
        if v < 1 or v > 30:
            raise ValueError(
                f"ppa_term_years={v} nije validan. "
                f"Mora biti između 1 i 30 godina."
            )
        return v

    @field_validator('ppa_index', 'market_inflation')
    @classmethod
    def validate_inflation(cls, v: float) -> float:
        if v < -0.50 or v > 0.50:
            raise ValueError(
                f"inflation={v} nije validan. "
                f"Mora biti između -0.50 (-50%) i 0.50 (+50%)."
            )
        return v

    @field_validator('market_prices_curve')
    @classmethod
    def validate_market_curve(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        if len(v) > 0 and len(v) != 30:
            raise ValueError(
                f"market_prices_curve ima {len(v)} vrijednosti. "
                f"Očekivano 30 (za 30 godina horizon)."
            )
        for i, price in enumerate(v):
            if price < 0:
                raise ValueError(
                    f"market_prices_curve[{i}]={price} nije validan. "
                    f"Cijena ne može biti negativna."
                )
        return v

    @field_validator('balancing_cost_pv', 'balancing_cost_bess')
    @classmethod
    def validate_balancing_cost(cls, v: float) -> float:
        if v < 0 or v > 0.50:
            raise ValueError(
                f"balancing_cost={v} nije validan. "
                f"Mora biti između 0.0 i 0.50 (0-50%)."
            )
        return v

    def tariff_at_year(self, year: int) -> float:
        """Return PPA tariff in year with escalation.

        Args:
            year: 1-based year index (1=Y1, 2=Y2, etc.)

        Returns:
            Tariff in €/MWh
        """
        if year < 1:
            return 0.0
        if year > self.ppa_term_years:
            return 0.0  # PPA ended
        return self.ppa_base_tariff * (1 + self.ppa_index) ** (year - 1)

    def market_price_at_year(self, year: int) -> float:
        """Return market price in year.

        Args:
            year: 1-based year index (1=Y1, 2=Y2, etc.)

        Returns:
            Market price in €/MWh, or 0.0 if curve not set
        """
        if year < 1 or year > len(self.market_prices_curve):
            return 0.0
        idx = year - 1
        base_price = self.market_prices_curve[idx]
        # Apply market inflation from year 1
        return base_price * (1 + self.market_inflation) ** (year - 1)

    def get_revenue_summary(self) -> dict:
        """Get revenue summary for display."""
        return {
            "ppa_base_tariff": f"{self.ppa_base_tariff:.1f} €/MWh",
            "ppa_term_years": self.ppa_term_years,
            "ppa_index": f"{self.ppa_index:.1%}",
            "ppa_production_share": f"{self.ppa_production_share:.0%}",
            "market_scenario": self.market_scenario,
            "co2_enabled": "Da" if self.co2_enabled else "Ne",
        }
