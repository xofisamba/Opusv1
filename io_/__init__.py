"""I/O module - Excel parsing and serialization.

This module handles reading from Excel files and serialization to/from JSON.
The actual model calculations are in domain/, not here.
"""
from io_.excel_parser import (
    parse_oborovo_excel,
    export_inputs_to_json,
    load_inputs_from_json,
    ExcelParserConfig,
    ExcelParserError,
)

__all__ = [
    "parse_oborovo_excel",
    "export_inputs_to_json",
    "load_inputs_from_json",
    "ExcelParserConfig",
    "ExcelParserError",
]