"""Shared type definitions for the diagnosis subsystem.

Provides TypedDict structures for diagnosis results and a Protocol for
engine interchangeability (RuleEngine, HybridEngine, MLClassifier).
"""

from __future__ import annotations

from typing import List, Literal, Protocol, TypedDict, Union


class EvidenceItem(TypedDict, total=False):
    """A single piece of evidence supporting a diagnosis."""

    feature: str
    value: Union[float, dict]
    threshold: Union[float, str]
    direction: str
    context: str


class DiagnosisResult(TypedDict, total=False):
    """Structured diagnosis output from any engine."""

    failure_type: str
    confidence: float
    severity: Literal["critical", "warning", "info"]
    detection_method: str
    evidence: List[EvidenceItem]
    recommendation: str
    reason_code: str


class DiagnosisEngine(Protocol):
    """Protocol satisfied by RuleEngine and HybridEngine.

    Any object with a ``diagnose(features) -> list`` method can be used
    as a diagnosis engine, removing the need for isinstance checks.
    """

    def diagnose(self, features: dict) -> list:
        ...
