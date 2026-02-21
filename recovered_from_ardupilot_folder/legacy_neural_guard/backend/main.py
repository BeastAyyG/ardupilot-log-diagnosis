"""
Neural Guard - FastAPI Backend
Cloud service for drone fleet management and telemetry visualization.
"""

from typing import Dict, List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import uuid

# Initialize FastAPI app
app = FastAPI(
    title="Neural Guard API",
    description="Cloud service for drone fleet management",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Data Models ====================

class DroneStatus(BaseModel):
    connection: str
    ai_active: bool
    battery_pct: int


class InferenceResult(BaseModel):
    risk_score: float
    anomaly_type: str
    confidence: float


class PhysicsData(BaseModel):
    roll: float
    pitch: float
    vibe_x: float


class Location(BaseModel):
    lat: float
    lon: float
    alt: float


class TelemetryData(BaseModel):
    drone_id: str
    timestamp_ms: int
    status: DroneStatus
    inference: InferenceResult
    physics: PhysicsData
    location: Optional[Location] = None


class Drone(BaseModel):
    drone_id: str
    name: str
    status: str
    last_seen: datetime
    battery_pct: int
    risk_score: float
    location: Optional[Location] = None


class Alert(BaseModel):
    id: str
    drone_id: str
    alert_type: str
    message: str
    severity: str
    timestamp: datetime
    acknowledged: bool = False


# ==================== In-Memory Data Store ====================

# Mock drone fleet
drones_db: Dict[str, Drone] = {
    "drone_01": Drone(
        drone_id="drone_01",
        name="Reaper Alpha",
        status="online",
        last_seen=datetime.now(),
        battery_pct=82,
        risk_score=0.05,
        location=Location(lat=-35.363, lon=149.165, alt=15.0)
    ),
    "reaper_02": Drone(
        drone_id="reaper_02",
        name="Reaper Bravo",
        status="online",
        last_seen=datetime.now(),
        battery_pct=64,
        risk_score=0.12,
        location=Location(lat=-35.368, lon=149.170, alt=12.0)
    ),
    "reaper_03": Drone(
        drone_id="reaper_03",
        name="Reaper Charlie",
        status="warning",
        last_seen=datetime.now(),
        battery_pct=23,
        risk_score=0.87,
        location=Location(lat=-35.355, lon=149.160, alt=8.0)
    ),
    "hunter_01": Drone(
        drone_id="hunter_01",
        name="Hunter One",
        status="online",
        last_seen=datetime.now(),
        battery_pct=95,
        risk_score=0.02,
        location=Location(lat=-35.370, lon=149.175, alt=20.0)
    ),
    "hunter_02": Drone(
        drone_id="hunter_02",
        name="Hunter Two",
        status="offline",
        last_seen=datetime.now(),
        battery_pct=0,
        risk_score=0.0,
        location=None
    ),
}

# Telemetry history
telemetry_db: Dict[str, List[TelemetryData]] = {drone_id: [] for drone_id in drones_db.keys()}

# Alerts
alerts_db: List[Alert] = [
    Alert(
        id=str(uuid.uuid4()),
        drone_id="reaper_03",
        alert_type="high_risk",
        message="An vibration levels",
        severity="omaly detected: Highcritical",
        timestamp=datetime.now(),
        acknowledged=False
    ),
    Alert(
        id=str(uuid.uuid4()),
        drone_id="reaper_03",
        alert_type="low_battery",
        message="Battery level critically low: 23%",
        severity="warning",
        timestamp=datetime.now(),
        acknowledged=False
    ),
]


# ==================== Helper Functions ====================

def generate_mock_telemetry(drone_id: str) -> TelemetryData:
    """Generate mock telemetry data for a drone."""
    drone = drones_db.get(drone_id)
    if not drone:
        raise HTTPException(status_code=404, detail="Drone not found")
    
    # Generate realistic mock values
    anomaly_types = ["none", "vibration", "voltage_sag", "none", "none"]
    anomaly_type = random.choice(anomaly_types)
    
    if drone.risk_score > 0.7:
        anomaly_type = random.choice(["vibration", "voltage_sag"])
    
    return TelemetryData(
        drone_id=drone_id,
        timestamp_ms=int(datetime.now().timestamp() * 1000),
        status=DroneStatus(
            connection=drone.status,
            ai_active=True,
            battery_pct=drone.battery_pct
        ),
        inference=InferenceResult(
            risk_score=drone.risk_score,
            anomaly_type=anomaly_type,
            confidence=round(random.uniform(0.85, 0.99), 2)
        ),
        physics=PhysicsData(
            roll=round(random.uniform(-0.1, 0.1), 2),
            pitch=round(random.uniform(-0.1, 0.1), 2),
            vibe_x=round(random.uniform(5.0, 25.0), 1)
        ),
        location=drone.location
    )


def update_drone_from_telemetry(telemetry: TelemetryData):
    """Update drone status from incoming telemetry."""
    if telemetry.drone_id in drones_db:
        drone = drones_db[telemetry.drone_id]
        drone.status = telemetry.status.connection
        drone.battery_pct = telemetry.status.battery_pct
        drone.risk_score = telemetry.inference.risk_score
        drone.last_seen = datetime.now()
        drone.location = telemetry.location
        
        # Check for high risk and create alert if needed
        if telemetry.inference.risk_score > 0.8:
            # Check if alert already exists
            existing_alert = any(
                a.drone_id == telemetry.drone_id and 
                a.alert_type == "high_risk" and 
                not a.acknowledged
                for a in alerts_db
            )
            if not existing_alert:
                alerts_db.append(Alert(
                    id=str(uuid.uuid4()),
                    drone_id=telemetry.drone_id,
                    alert_type="high_risk",
                    message=f"AI Risk Score: {telemetry.inference.risk_score:.2f} - {telemetry.inference.anomaly_type}",
                    severity="critical",
                    timestamp=datetime.now(),
                    acknowledged=False
                ))


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Neural Guard API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "drones_count": len(drones_db),
        "alerts_count": len([a for a in alerts_db if not a.acknowledged])
    }


@app.get("/api/drones", response_model=List[Drone])
async def get_drones():
    """Get all drones in the fleet."""
    return list(drones_db.values())


@app.get("/api/drones/{drone_id}", response_model=Drone)
async def get_drone(drone_id: str):
    """Get a specific drone by ID."""
    if drone_id not in drones_db:
        raise HTTPException(status_code=404, detail="Drone not found")
    return drones_db[drone_id]


@app.get("/api/drones/{drone_id}/telemetry", response_model=TelemetryData)
async def get_telemetry(drone_id: str):
    """Get current telemetry for a specific drone."""
    return generate_mock_telemetry(drone_id)


@app.get("/api/drones/{drone_id}/history", response_model=List[TelemetryData])
async def get_telemetry_history(drone_id: str, limit: int = 50):
    """Get telemetry history for a specific drone."""
    if drone_id not in telemetry_db:
        raise HTTPException(status_code=404, detail="Drone not found")
    return telemetry_db[drone_id][-limit:]


@app.post("/api/ingest", response_model=dict)
async def ingest_telemetry(telemetry: TelemetryData):
    """Ingest telemetry data from a drone."""
    # Update drone status
    update_drone_from_telemetry(telemetry)
    
    # Store in history
    if telemetry.drone_id in telemetry_db:
        telemetry_db[telemetry.drone_id].append(telemetry)
        # Keep only last 1000 records
        if len(telemetry_db[telemetry.drone_id]) > 1000:
            telemetry_db[telemetry.drone_id] = telemetry_db[telemetry.drone_id][-1000:]
    
    return {
        "status": "ingested",
        "drone_id": telemetry.drone_id,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/alerts", response_model=List[Alert])
async def get_alerts(acknowledged: Optional[bool] = None):
    """Get all alerts, optionally filtered by acknowledged status."""
    if acknowledged is not None:
        return [a for a in alerts_db if a.acknowledged == acknowledged]
    return alerts_db


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert."""
    for alert in alerts_db:
        if alert.id == alert_id:
            alert.acknowledged = True
            return {"status": "acknowledged", "alert_id": alert_id}
    raise HTTPException(status_code=404, detail="Alert not found")


@app.get("/api/stats")
async def get_stats():
    """Get fleet statistics."""
    online_count = sum(1 for d in drones_db.values() if d.status == "online")
    warning_count = sum(1 for d in drones_db.values() if d.status == "warning")
    offline_count = sum(1 for d in drones_db.values() if d.status == "offline")
    high_risk_count = sum(1 for d in drones_db.values() if d.risk_score > 0.7)
    
    return {
        "total_drones": len(drones_db),
        "online": online_count,
        "warning": warning_count,
        "offline": offline_count,
        "high_risk": high_risk_count,
        "total_alerts": len(alerts_db),
        "unacknowledged_alerts": len([a for a in alerts_db if not a.acknowledged])
    }


# ==================== Mock Data Generation ====================

@app.post("/api/mock/generate")
async def generate_mock_data():
    """Generate mock data for all drones (for demo purposes)."""
    for drone_id in drones_db.keys():
        telemetry = generate_mock_telemetry(drone_id)
        update_drone_from_telemetry(telemetry)
        telemetry_db[drone_id].append(telemetry)
        
        if len(telemetry_db[drone_id]) > 1000:
            telemetry_db[drone_id] = telemetry_db[drone_id][-1000:]
    
    return {"status": "generated", "drones_updated": len(drones_db)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
