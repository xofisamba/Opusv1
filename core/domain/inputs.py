"""Core domain inputs — clean ProjectInputs without hardcoded defaults.

This module provides create_blank_project() for the application layer.
The actual ProjectInputs class remains in domain/inputs.py (backward compat).

Usage:
    from core.domain.inputs import create_blank_project
    blank = create_blank_project()
    errors = blank.validate()
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# Import from domain/inputs.py to avoid duplication
from domain.inputs import ProjectInputs, ProjectInfo, TechnicalParams
from domain.inputs import CapexStructure, CapexItem, OpexItem
from domain.inputs import RevenueParams, FinancingParams, TaxParams
from domain.inputs import PeriodFrequency


@dataclass(frozen=True)
class CapexNode:
    """Hierarchical CAPEX tree node (group or leaf item)."""
    code: str
    name: str
    parent_code: Optional[str]
    children: tuple = ()

    @property
    def total_keur(self) -> float:
        total = 0.0
        for child in self.children:
            if isinstance(child, CapexItem):
                total += child.amount_keur
            elif isinstance(child, CapexNode):
                total += child.total_keur
        return total


@dataclass(frozen=True)
class CapexTree:
    """Hierarchical CAPEX structure (Blueprint §2.1)."""
    hard_capex_root: Optional[CapexNode] = None
    idc_keur: float = 0.0
    commitment_fees_keur: float = 0.0
    bank_fees_keur: float = 0.0
    vat_costs_keur: float = 0.0
    reserve_accounts_keur: float = 0.0


def _add_validation():
    """Add validate_for_calculation() method to ProjectInputs class.

    This is applied after class definition to avoid circular imports.
    """
    def validate_for_calculation(self: ProjectInputs) -> list[str]:
        errors = []
        if not self.info:
            errors.append("Project info is missing")
        elif not getattr(self.info, 'name', None):
            errors.append("Project name is required")
        elif not getattr(self.info, 'capacity_mw', None) or getattr(self.info, 'capacity_mw', 0) <= 0:
            errors.append("Capacity (MW) must be greater than 0")
        elif not getattr(self.info, 'financial_close', None):
            errors.append("Financial close date is required")
        elif not getattr(self.info, 'horizon_years', None) or getattr(self.info, 'horizon_years', 0) <= 0:
            errors.append("Investment horizon (years) must be greater than 0")
        if not self.technical:
            errors.append("Technical parameters are missing")
        elif getattr(self.technical, 'capacity_mw', 0) <= 0:
            errors.append("Technical capacity (MW) must be greater than 0")
        if not self.capex:
            errors.append("CAPEX is missing")
        elif hasattr(self.capex, 'total_capex') and self.capex.total_capex <= 0:
            errors.append("Total CAPEX must be greater than 0")
        if not self.revenue:
            errors.append("Revenue parameters are missing")
        elif getattr(self.revenue, 'ppa_base_tariff', None) is None:
            errors.append("PPA base tariff is required")
        if not self.financing:
            errors.append("Financing parameters are missing")
        elif getattr(self.financing, 'share_capital_keur', None) is None:
            errors.append("Share capital is required")
        if not self.tax:
            errors.append("Tax parameters are missing")
        elif getattr(self.tax, 'corporate_rate', None) is None:
            errors.append("Corporate tax rate is required")
        return errors

    ProjectInputs.validate_for_calculation = validate_for_calculation


_add_validation()


def create_blank_project() -> ProjectInputs:
    """Create a blank project template with None values.

    Use this as the default session state — any calculation attempt
    will fail with a clear list of missing required fields.

    Returns:
        ProjectInputs with all fields set to None (or empty tuples).
    """
    return ProjectInputs(
        info=None,
        technical=None,
        capex=None,
        opex=(),
        revenue=None,
        financing=None,
        tax=None,
    )
