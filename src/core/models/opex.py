"""OPEX Pydantic models.

Corresponds to Excel Inputs rows 146-161 (15 OPEX categories).
"""
from pydantic import Field, field_validator
from typing import Optional

from .pydantic_base import FinancialBaseModel


class OpexItem(FinancialBaseModel):
    """Single OPEX line item with individual escalation.

    Corresponds to Excel Inputs rows 146-161 (15 OPEX categories).
    Each item has Y1 amount and annual escalation rate.

    Example:
        Technical Management: 198 k€ Y1, 2% annual index
        Power Expenses: 126.86 k€ Y1, 0% index (flat)

    Validation Rules:
        - y1_amount_keur: Must be >= 0
        - annual_inflation: Must be >= -0.5 and <= 0.5 (-50% to +50%)
        - step_changes: tuple of (year, amount) tuples, years must be unique
    """
    name: str = Field(
        min_length=1,
        max_length=100,
        description="Item description"
    )
    y1_amount_keur: float = Field(
        ge=0,
        description="Amount in kEUR for Year 1"
    )
    annual_inflation: float = Field(
        default=0.02,
        ge=-0.5, le=0.5,
        description="Annual escalation rate (0.02 = 2%)"
    )
    step_changes: tuple[tuple[int, float], ...] = Field(
        default_factory=tuple,
        description="Hard-coded step changes as (year, amount) tuples, e.g. ((3, 185.64),)"
    )

    @field_validator('annual_inflation')
    @classmethod
    def validate_inflation(cls, v: float) -> float:
        if v < -0.5 or v > 0.5:
            raise ValueError(
                f"annual_inflation={v} nije validan. "
                f"Očekivano između -0.5 (-50%) i 0.5 (+50%)."
            )
        return v

    @field_validator('step_changes')
    @classmethod
    def validate_step_changes(cls, v: tuple[tuple[int, float], ...]) -> tuple[tuple[int, float], ...]:
        years = set()
        for i, (year, amount) in enumerate(v):
            if year < 1:
                raise ValueError(
                    f"step_changes[{i}]: godina {year} nije validna. "
                    f"Godina mora biti >= 1."
                )
            if amount < 0:
                raise ValueError(
                    f"step_changes[{i}]: iznos {amount} nije validan. "
                    f"Iznos mora biti >= 0."
                )
            if year in years:
                raise ValueError(
                    f"step_changes: duplicirana godina {year}. "
                    f"Svaka godina smije biti navedena samo jednom."
                )
            years.add(year)
        return v

    def amount_at_year(self, year: int) -> float:
        """Return OPEX amount for a given year with escalation.

        Args:
            year: 1-based year index (1=Y1, 2=Y2, etc.)

        Returns:
            Amount in kEUR for that year
        """
        if year < 1:
            return 0.0
        
        # Check for step change
        for step_year, amount in self.step_changes:
            if year == step_year:
                return amount
        
        # Apply escalation from Y1
        return self.y1_amount_keur * (1 + self.annual_inflation) ** (year - 1)

    def get_opex_summary(self) -> dict:
        """Get summary for display."""
        return {
            "name": self.name,
            "y1_amount_keur": self.y1_amount_keur,
            "annual_inflation": f"{self.annual_inflation:.1%}",
            "step_changes_count": len(self.step_changes),
        }
