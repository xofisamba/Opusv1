"""Opex items — Blueprint §2.2.

Tabular opex structure for operational expenditures.
All classes are frozen/immutable.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

OpexCategory = Literal["Insurance", "O&M", "Lease", "Other"]


@dataclass(frozen=True)
class OpexItem:
    """Single OPEX line item.

    Corresponds to Blueprint §2.2 schema.
    """
    code: str
    name: str
    category: OpexCategory
    y1_amount_keur: float
    annual_inflation: float  # Fraction, e.g., 0.02 = 2%
    step_changes: tuple[tuple[int, float], ...] = ()  # (year, new_amount_keur)
    inflation_index: str = "CPI"
    deductible_for_tax: bool = True

    def amount_at_year(self, year: int) -> float:
        """Calculate opex amount at a given year (1-indexed)."""
        amount = self.y1_amount_keur
        # Apply inflation
        if year > 1:
            amount = amount * ((1 + self.annual_inflation) ** (year - 1))
        # Apply step changes
        for change_year, new_amount in self.step_changes:
            if year >= change_year:
                amount = new_amount
        return amount

    def total_over_horizon(self, horizon_years: int) -> float:
        """Calculate total opex over a given horizon."""
        return sum(self.amount_at_year(y) for y in range(1, horizon_years + 1))


@dataclass(frozen=True)
class OpexStructure:
    """Collection of opex items."""
    items: tuple[OpexItem, ...]

    @property
    def total_y1_keur(self) -> float:
        return sum(item.y1_amount_keur for item in self.items)

    def total_y1_per_mw(self, capacity_mw: float) -> float:
        return self.total_y1_keur / capacity_mw if capacity_mw > 0 else 0.0


# Default opex template (blank)
def create_blank_opex_items() -> tuple[OpexItem, ...]:
    """Create a blank opex template with default categories.

    Returns a tuple of empty OpexItems for common categories.
    """
    return (
        OpexItem(code="OP.01", name="Insurance", category="Insurance",
                 y1_amount_keur=0.0, annual_inflation=0.02),
        OpexItem(code="OP.02", name="O&M", category="O&M",
                 y1_amount_keur=0.0, annual_inflation=0.02),
        OpexItem(code="OP.03", name="Lease", category="Lease",
                 y1_amount_keur=0.0, annual_inflation=0.02),
        OpexItem(code="OP.04", name="Other", category="Other",
                 y1_amount_keur=0.0, annual_inflation=0.02),
    )
