"""Stable machine-readable error taxonomy for CLI/API consumers."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    UNSUPPORTED_EXTENSION = "UNSUPPORTED_EXTENSION"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
    PARSE_FAILED = "PARSE_FAILED"
    EMPTY_LOG = "EMPTY_LOG"
    PARAMETER_INPUT_INVALID = "PARAMETER_INPUT_INVALID"
    REPORT_EXPORT_FAILED = "REPORT_EXPORT_FAILED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    NOT_FOUND = "NOT_FOUND"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    REQUEST_VALIDATION_FAILED = "REQUEST_VALIDATION_FAILED"


def error_payload(code: ErrorCode | str, message: str, **details: Any) -> dict[str, Any]:
    payload = {"error": message, "code": code.value if isinstance(code, ErrorCode) else str(code)}
    if details:
        payload["details"] = details
    return payload
