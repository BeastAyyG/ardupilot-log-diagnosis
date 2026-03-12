from __future__ import annotations

from typing import Any, Literal, TypeAlias, TypedDict


Severity = Literal["critical", "warning", "info"]
DecisionStatus = Literal["healthy", "uncertain", "confirmed"]


class ParsedMetadata(TypedDict):
    filepath: str
    duration_sec: float
    vehicle_type: str
    firmware_version: str
    total_messages: int
    message_types: dict[str, int]


class ParsedError(TypedDict, total=False):
    time_us: int | None
    subsystem: int
    subsystem_name: str
    code: int
    auto_label: str | None


class ParsedEvent(TypedDict, total=False):
    time_us: int | None
    id: int
    name: str


class ParsedModeChange(TypedDict, total=False):
    time_us: int | None
    mode: int
    mode_name: str
    reason: int


class ParsedStatusMessage(TypedDict, total=False):
    time_us: int | None
    message: str


class ParsedLog(TypedDict):
    metadata: ParsedMetadata
    messages: dict[str, list[dict[str, Any]]]
    parameters: dict[str, Any]
    errors: list[ParsedError]
    events: list[ParsedEvent]
    mode_changes: list[ParsedModeChange]
    status_messages: list[ParsedStatusMessage]


class FeatureMetadata(TypedDict, total=False):
    log_file: str
    duration_sec: float
    vehicle_type: str
    firmware: str
    messages_found: list[str]
    extraction_time_sec: float
    total_features: int
    auto_labels: list[str]
    extraction_success: bool


FeatureValue: TypeAlias = Any
FeatureDict: TypeAlias = dict[str, FeatureValue]


class EvidenceItem(TypedDict):
    feature: str
    value: Any
    threshold: Any
    direction: str


class DiagnosisDict(TypedDict):
    failure_type: str
    confidence: float
    severity: Severity
    detection_method: str
    evidence: list[EvidenceItem]
    recommendation: str
    reason_code: str


class RankedSubsystem(TypedDict):
    subsystem: str
    likelihood: float


class DecisionDict(TypedDict):
    status: DecisionStatus
    requires_human_review: bool
    top_guess: str | None
    top_confidence: float
    rationale: list[str]
    ranked_subsystems: list[RankedSubsystem]


class BenchmarkError(TypedDict):
    filename: str
    error: str
    type: str


class BenchmarkLogResult(TypedDict):
    filename: str
    ground_truth: list[str]
    predicted: list[DiagnosisDict]
    predicted_confidence: list[float | None]


class LabelMetrics(TypedDict):
    support: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float


class BenchmarkOverall(TypedDict):
    total_logs: int
    successful_extractions: int
    failed_extractions: int
    failed_diagnoses: int
    any_match_accuracy: float
    top1_accuracy: float
    exact_match_accuracy: float
    macro_f1: float


class BenchmarkMetrics(TypedDict):
    overall: BenchmarkOverall
    per_label: dict[str, LabelMetrics]
    confusion_details: list[dict[str, Any]]
    errors: list[BenchmarkError]
