"""Base Pydantic configuration with custom error messages.

This module provides shared validators and error message translations
for the financial model Pydantic schemas.
"""
from pydantic import BaseModel, ConfigDict, field_validator, ValidationError
from typing import Any


# =============================================================================
# Custom Error Messages (HR localization)
# =============================================================================
ERROR_MESSAGES: dict[str, str] = {
    "greater_than_zero": "Iznos mora biti veći od nule.",
    "greater_than_or_equal_zero": "Iznos mora biti veći ili jednak nuli.",
    "less_than_zero": "Iznos mora biti manji od nule.",
    "less_than_or_equal_zero": "Iznos mora biti manji ili jednak nuli.",
    "must_be_between": "Vrijednost mora biti između {min} i {max}.",
    "required": "Ovo polje je obavezno.",
    "invalid_enum": "Nedozvoljena vrijednost. Dopuštene opcije: {choices}",
    "invalid_date": "Neispravan datum format. Koristite YYYY-MM-DD.",
    "invalid_email": "Neispravna email adresa.",
    "string_too_short": "Tekst je prekratak. Minimalno {min} znakova.",
    "string_too_long": "Tekst je predug. Maksimalno {max} znakova.",
}


def gt_zero_message(value: float) -> str:
    """Generate 'must be > 0' message with value context."""
    return f"Iznos {value} nije validan. Iznos mora biti veći od nule."


def between_message(min_val: float, max_val: float) -> str:
    """Generate 'must be between' message."""
    return f"Vrijednost mora biti između {min_val} i {max_val}."


# =============================================================================
# Base Model with Shared Configuration
# =============================================================================
class FinancialBaseModel(BaseModel):
    """Base model with shared configuration and validators.
    
    Provides:
    - Strict type checking
    - JSON schema export capability
    - Custom error messages
    """
    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=True,
        json_schema_serialization_defaults_required=False,
    )

    def to_json_dict(self) -> dict[str, Any]:
        """Export model as JSON-serializable dict.
        
        Returns dict suitable for JSON serialization and Save Scenario.
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FinancialBaseModel":
        """Create model instance from dict (backward compat)."""
        return cls.model_validate(data)

    def validate_field(self, field_name: str) -> list[str]:
        """Get validation errors for a specific field.
        
        Returns list of human-readable error messages.
        """
        errors = []
        try:
            self.model_validate(self.model_dump())
        except ValidationError as exc:
            for err in exc.errors():
                if err["loc"] == (field_name,):
                    errors.append(self._format_error(err))
        return errors

    def _format_error(self, error: dict[str, Any]) -> str:
        """Format a single validation error into user-friendly message."""
        msg = error.get("msg", "")
        ctx = error.get("ctx", {})
        loc = error.get("loc", ())
        
        # Map Pydantic error types to user-friendly messages
        if msg.startswith("Input should be greater than"):
            return ERROR_MESSAGES["greater_than_zero"]
        elif msg.startswith("Input should be greater than or equal"):
            return ERROR_MESSAGES["greater_than_or_equal_zero"]
        elif msg.startswith("Input should be less than"):
            return ERROR_MESSAGES["less_than_zero"]
        elif msg.startswith("Input should be less than or equal"):
            return ERROR_MESSAGES["less_than_or_equal_zero"]
        elif msg.startswith("Input should be between"):
            min_val = ctx.get("ge", 0)
            max_val = ctx.get("le", 0)
            return between_message(min_val, max_val)
        elif msg.startswith("Field required"):
            return ERROR_MESSAGES["required"]
        elif msg.startswith("Input should be one of"):
            choices = ctx.get("expected", "nešto")
            return ERROR_MESSAGES["invalid_enum"].format(choices=choices)
        
        return msg

    def get_all_errors(self) -> list[str]:
        """Get all validation errors as user-friendly messages."""
        errors = []
        try:
            self.model_validate(self.model_dump())
        except ValidationError as exc:
            for err in exc.errors():
                errors.append(self._format_error(err))
        return errors
