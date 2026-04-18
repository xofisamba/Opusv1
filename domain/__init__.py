"""Domain layer - pure business logic (no Streamlit/pandas dependencies).

This package contains immutable dataclasses representing project finance inputs.
All calculation functions are pure and testable.
"""
from domain.inputs import (
    ProjectInputs,
    ProjectInfo,
    CapexItem,
    CapexStructure,
    OpexItem,
    TechnicalParams,
    RevenueParams,
    FinancingParams,
    TaxParams,
)

__all__ = [
    "ProjectInputs",
    "ProjectInfo",
    "CapexItem",
    "CapexStructure",
    "OpexItem",
    "TechnicalParams",
    "RevenueParams",
    "FinancingParams",
    "TaxParams",
]