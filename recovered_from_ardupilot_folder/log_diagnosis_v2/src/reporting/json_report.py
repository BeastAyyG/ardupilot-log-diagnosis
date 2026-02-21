import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _normalize_diagnosis(entry: Any, engine: str) -> Dict[str, Any]:
    if hasattr(entry, "to_dict"):
        payload = entry.to_dict()
    elif isinstance(entry, dict):
        payload = dict(entry)
    else:
        payload = {"failure_type": str(entry), "confidence": 0.0, "evidence": [], "fix": ""}

    return {
        "engine": payload.get("engine", engine),
        "type": payload.get("failure_type") or payload.get("type", "unknown"),
        "confidence": float(payload.get("confidence", 0.0)),
        "severity": payload.get("severity", "unknown"),
        "evidence": payload.get("evidence", []),
        "fix": payload.get("fix", ""),
    }


def build_json_report(
    metadata: Dict[str, Any],
    features: Dict[str, Any],
    rule_diagnoses: List[Any],
    ml_diagnoses: Optional[List[Dict[str, Any]]] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    diagnoses: List[Dict[str, Any]] = []
    diagnoses.extend(_normalize_diagnosis(d, "rule") for d in (rule_diagnoses or []))
    diagnoses.extend(_normalize_diagnosis(d, "xgboost") for d in (ml_diagnoses or []))
    diagnoses.sort(key=lambda d: d["confidence"], reverse=True)

    highest_confidence = max([d["confidence"] for d in diagnoses], default=0.0)
    summary = {
        "healthy": len(diagnoses) == 0,
        "diagnosis_count": len(diagnoses),
        "highest_confidence": highest_confidence,
        "top_issue": diagnoses[0]["type"] if diagnoses else "healthy",
    }

    return {
        "generated_at": now.isoformat(),
        "timestamp_ms": int(now.timestamp() * 1000),
        "metadata": metadata,
        "summary": summary,
        "diagnoses": diagnoses,
        "features": features,
        "model_metadata": model_metadata or {},
    }


def write_json_report(report: Dict[str, Any], output_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    return output_path
