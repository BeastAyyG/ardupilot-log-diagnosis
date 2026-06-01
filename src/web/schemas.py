from typing import Any

from pydantic import BaseModel, ConfigDict


class Metadata(BaseModel):
    filename: str
    duration: float
    vehicle: str


class Diagnosis(BaseModel):
    failure_type: str
    confidence: float
    evidence: list[dict]
    recommendation: str

    model_config = ConfigDict(extra="allow")


class ExplainData(BaseModel):
    decision: dict[str, Any]

    model_config = ConfigDict(extra="allow")


class TimelineEvent(BaseModel):
    t_sec: float
    type: str
    label: str
    severity: str
    gps: dict[str, Any] | None = None


class GPSQuality(BaseModel):
    hdop: list[dict[str, Any]]
    sat_count: list[dict[str, Any]]
    fix_type: list[dict[str, Any]]
    avg_hdop: float
    min_satellites: int
    # Time (seconds from log start) until the first 3-D GPS fix was achieved.
    # None when no fix was ever recorded in the log.
    ttff_sec: float | None = None


class AnalysisResponse(BaseModel):
    metadata: Metadata
    features: dict[str, Any]
    diagnoses: list[Diagnosis]
    parameter_warnings: list[dict]
    explain_data: ExplainData
    time_series: dict[str, list[dict[str, Any]]]
    timeline_events: list[TimelineEvent]
    gps_quality: GPSQuality
    rule_output_only: str
    rule_output_diagnoses: list[dict[str, Any]]


class ChatRequest(BaseModel):
    """Request schema for chat endpoint."""
    question: str
    analysis_result: dict[str, Any]


class ChatResponse(BaseModel):
    """Response schema for chat endpoint."""
    question: str
    answer: str
    confidence: float
    sources: list[str]
    follow_up: list[str]