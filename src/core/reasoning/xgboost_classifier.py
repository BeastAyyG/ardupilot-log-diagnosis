"""Optional XGBoost dependency boundary.

This module deliberately does not import XGBoost at module load time.  The
project's production classifier remains in :mod:`src.diagnosis.ml_classifier`;
this boundary only gives callers a typed, side-effect-free capability check or
an explicit lazy import when an optional XGBoost integration is requested.
"""

from __future__ import annotations

from types import ModuleType

__all__ = ["XGBoostUnavailableError", "is_xgboost_available", "load_xgboost"]


class XGBoostUnavailableError(ImportError):
    """Raised when the optional XGBoost package cannot be imported."""


def load_xgboost() -> ModuleType:
    """Lazily import and return the optional :mod:`xgboost` package.

    No model artifacts are loaded and no filesystem or network operations are
    initiated by this boundary.  Callers that need a classifier should use the
    existing ``MLClassifier`` artifact-loading path explicitly.
    """

    import importlib

    try:
        return importlib.import_module("xgboost")
    except ImportError as exc:
        raise XGBoostUnavailableError(
            "Optional dependency 'xgboost' is not available"
        ) from exc


def is_xgboost_available() -> bool:
    """Return whether XGBoost can be imported without raising ``ImportError``."""

    try:
        load_xgboost()
    except XGBoostUnavailableError:
        return False
    return True
