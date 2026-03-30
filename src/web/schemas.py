from typing import Any

from pydantic import BaseModel, ConfigDict


class Metadata(BaseModel):
    filename: str
    duration: float
    vehicle: str


class Diagnosis(BaseModel):
    failure_type: str
    confidence: float
    evidence: list[str]
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


class AnalysisResponse(BaseModel):
    metadata: Metadata
    features: dict[str, Any]
    diagnoses: list[Diagnosis]
    parameter_warnings: list[str]
    explain_data: ExplainData
    time_series: dict[str, list[dict[str, Any]]]
    timeline_events: list[TimelineEvent]
    rule_output_only: str
    rule_output_diagnoses: list[dict[str, Any]]
