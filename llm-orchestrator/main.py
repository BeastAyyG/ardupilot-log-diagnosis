from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="ArduPilot LLM Orchestrator", version="1.0.0")

class DiagnosisReport(BaseModel):
    structured_diagnosis: Dict[str, Any]
    user_query: str | None = None


def _grounded_explanation(report: Dict[str, Any], user_query: str | None) -> dict[str, Any]:
    """Explain only fields present in the structured engine report.

    This service deliberately has no model/provider configured.  It must never
    invent a failure type, telemetry value, confidence, or recommendation.
    The core engine remains the sole authority for diagnosis and abstention.
    """
    decision = report.get("decision")
    if not isinstance(decision, dict):
        decision = (report.get("explain_data") or {}).get("decision", {})
    if not isinstance(decision, dict):
        decision = {}

    diagnoses = report.get("diagnoses", [])
    if not isinstance(diagnoses, list):
        diagnoses = []
    valid = [item for item in diagnoses if isinstance(item, dict) and item.get("failure_type")]
    top_guess = decision.get("top_guess")
    status = str(decision.get("status", "uncertain"))
    review = bool(decision.get("requires_human_review", True))

    if top_guess:
        explanation = f"The core engine reported {top_guess} with decision status {status}."
    elif valid:
        explanation = f"The core engine returned {len(valid)} candidate finding(s), but did not select a single root cause."
    else:
        explanation = "The core engine did not produce a validated diagnosis from the supplied report."

    if review or status not in {"confirmed", "reliable"}:
        explanation += " Human review is required before treating this as a root-cause conclusion."

    recommendations = []
    for item in valid:
        recommendation = item.get("recommendation")
        if isinstance(recommendation, str) and recommendation.strip():
            recommendations.append(recommendation.strip())
    hypothesis = recommendations[0] if recommendations else None
    return {
        "status": "grounded",
        "explanation": explanation,
        "hypothesis": hypothesis,
        "model": "deterministic_grounded",
        "write_parameters": False,
        "user_query_received": bool(user_query and user_query.strip()),
    }

@app.post("/explain")
def explain_diagnosis(report: DiagnosisReport):
    """
    Takes the structured output from the Core Engine and translates it into
    a human-readable natural language report using an LLM.
    """
    return _grounded_explanation(report.structured_diagnosis, report.user_query)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "llm-orchestrator"}


@app.get("/ready")
def readiness_check():
    """The service is ready for grounded explanations without an LLM provider."""
    return {
        "status": "ready",
        "service": "llm-orchestrator",
        "mode": "grounded_only",
        "model_ready": False,
        "write_parameters": False,
    }
