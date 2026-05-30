from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import numpy as np

from hmm_filter import TemporalHMMFilter

app = FastAPI(title="ArduPilot Temporal Layer", version="1.0.0")

# Initialize the HMM (in production this would load a trained artifact)
hmm_filter = TemporalHMMFilter()

class FeatureSequence(BaseModel):
    features: List[List[float]]
    window_size: int = 5

class FilterResponse(BaseModel):
    smoothed_states: List[int]
    transient_noise_detected: bool

@app.post("/filter", response_model=FilterResponse)
def filter_sequence(seq: FeatureSequence):
    """
    Takes a sequence of raw telemetry features over time.
    Returns the HMM-smoothed state sequence (0=Healthy, 1=Degrading, 2=Failing).
    """
    if not seq.features:
        raise HTTPException(status_code=400, detail="Empty feature sequence")
        
    feature_array = np.array(seq.features)
    
    # In a real scenario, this requires a pre-trained model.
    # For now, we simulate the return if it's not fitted.
    try:
        smoothed = hmm_filter.filter_transients(feature_array, seq.window_size)
        raw_states = hmm_filter.predict_states(feature_array)
        
        # If the smoothed state differs from raw state, we filtered out noise
        noise_detected = not np.array_equal(smoothed, raw_states)
        
        return FilterResponse(
            smoothed_states=smoothed.tolist(),
            transient_noise_detected=noise_detected
        )
    except Exception:
        # Fallback if model isn't trained yet
        return FilterResponse(
            smoothed_states=[0] * len(seq.features),
            transient_noise_detected=False
        )

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "temporal-layer"}
