"""Pydantic models for financial model validation.

This module provides typed input validation with user-friendly error messages.
Designed as a drop-in replacement for domain/inputs.py dataclasses.
"""
from pydantic import ValidationError

from .pydantic_base import FinancialBaseModel, ERROR_MESSAGES
from .project import (
    ProjectInfo,
    PeriodFrequency,
    YieldScenario,
    create_project_info,
)
from .capex import CapexItem, CapexStructure
from .opex import OpexItem
from .financing import FinancingParams, TaxParams

__all__ = [
    # Base
    "FinancialBaseModel",
    "ValidationError",
    "ERROR_MESSAGES",
    # Project
    "ProjectInfo",
    "PeriodFrequency",
    "YieldScenario",
    "create_project_info",
    # Capex
    "CapexItem",
    "CapexStructure",
    # Opex
    "OpexItem",
    # Financing
    "FinancingParams",
    "TaxParams",
]
