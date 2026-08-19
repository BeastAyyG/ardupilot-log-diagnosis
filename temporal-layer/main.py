from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import numpy as np

from hmm_filter import TemporalHMMFilter

MAX_FEATURE_ROWS = 10_000
MAX_FEATURE_COLUMNS = 512

app = FastAPI(title="ArduPilot Temporal Layer", version="1.0.0")

# Initialize the HMM (in production this would load a trained artifact)
hmm_filter = TemporalHMMFilter()

class FeatureSequence(BaseModel):
    features: List[List[float]]
    window_size: int = 5

class FilterResponse(BaseModel):
    smoothed_states: List[int]
    transient_noise_detected: bool
    status: str = "review_only"
    model_ready: bool = False
    warning: str | None = None

@app.post("/filter", response_model=FilterResponse)
def filter_sequence(seq: FeatureSequence):
    """
    Takes a sequence of raw telemetry features over time.
    Returns the HMM-smoothed state sequence (0=Healthy, 1=Degrading, 2=Failing).
    """
    if not seq.features:
        raise HTTPException(status_code=400, detail="Empty feature sequence")
    if len(seq.features) > MAX_FEATURE_ROWS:
        raise HTTPException(status_code=413, detail=f"Feature sequence exceeds {MAX_FEATURE_ROWS} rows")
    if any(len(row) > MAX_FEATURE_COLUMNS for row in seq.features):
        raise HTTPException(status_code=413, detail=f"Feature sequence exceeds {MAX_FEATURE_COLUMNS} columns")
    if seq.window_size < 1:
        raise HTTPException(status_code=422, detail="window_size must be positive")
    feature_array = np.array(seq.features)
    if feature_array.ndim != 2 or not np.isfinite(feature_array).all():
        raise HTTPException(status_code=422, detail="features must be a finite rectangular numeric matrix")
    if not hmm_filter.fitted:
        raise HTTPException(
            status_code=503,
            detail="Temporal HMM is not fitted; refusing to emit synthetic healthy states.",
        )

    try:
        smoothed = hmm_filter.filter_transients(feature_array, seq.window_size)
        raw_states = hmm_filter.predict_states(feature_array)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return FilterResponse(
        smoothed_states=smoothed.tolist(),
        transient_noise_detected=not np.array_equal(smoothed, raw_states),
        status="available",
        model_ready=True,
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "temporal-layer"}


@app.get("/ready")
def readiness_check():
    if not hmm_filter.fitted:
        raise HTTPException(status_code=503, detail="Temporal HMM model is not fitted")
    return {"status": "ready", "service": "temporal-layer", "model_ready": True}
