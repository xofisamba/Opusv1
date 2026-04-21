"""App module - refactored from main.py.

Contains session state, validation, builder, sidebar, and routing.
"""
from app.validation import validate_session_inputs, ValidationResult, validate_inputs_with_errors

__all__ = ["validate_session_inputs", "ValidationResult", "validate_inputs_with_errors"]