# 🧠 Neural Guard: Parallel Workstream Definition
*Architecture for Simultaneous Development*

To accelerate development, we will decouple the system into two autonomous workstreams.
**Agent A (Embedded/Edge)** and **Agent B (Cloud/Frontend)** can work in parallel using this API Contract.

---

## 🤖 Workstream A: Edge Intelligence (Current Context)
**Owner**: Embedded AI Specialist
**Focus**: Raspberry Pi, MAVLink, Real-time Inference, Lua Scripts.

### Responsibilities
1.  **Data Ingestion**: Read MAVLink streams (Vibration, Battery, Servo).
2.  **Inference Engine**: Run `anomaly_model.joblib` at 10Hz.
3.  **Local API**: Expose `GET /api/stats` and `GET /api/health` on Port 5000.
4.  **Failsafe Handling**: Trigger MAVLink commands (RTL/Land) upon detection.

---

## ☁️ Workstream B: Cloud & Visualization (The "Other AI")
**Owner**: Full-Stack/Cloud Specialist
**Focus**: React Dashboard, Historical Logging, Multi-Drone Fleet Management.

### Responsibilities
1.  **Modern Dashboard**: Build a React/TypeScript frontend (replaces simple HTML).
2.  **Fleet Aggregator**: A Cloud Service (FastAPI) that receives data from multiple drones.
3.  **Data Persistence**: Store long-term logs in InfluxDB or TimescaleDB.
4.  **Alerting System**: Send Email/SMS alerts via Twilio/SendGrid when `AI_RISK > 0.8`.

---

## 🔌 The API Contract (Interface)
*Both Agents must adhere strictly to this interface.*

### 1. Drone Telemetry Endpoint (`GET http://<drone-ip>:5000/api/telemetry`)
**Response Format (JSON)**:
```json
{
  "drone_id": "drone_01",
  "timestamp_ms": 1678900000,
  "status": {
    "connection": "online",
    "ai_active": true,
    "battery_pct": 82
  },
  "inference": {
    "risk_score": 0.05,  // 0.0 - 1.0
    "anomaly_type": "none", // "vibration", "voltage_sag", "none"
    "confidence": 0.98
  },
  "physics": {
    "roll": 0.02,
    "pitch": -0.01,
    "vibe_x": 12.5
  }
}
```

### 2. Fleet Sync Endpoint (`POST https://cloud.neuralguard.com/ingest`)
*Agent A posts to this; Agent B builds this.*
**Payload**: Same as above, plus:
```json
{
  "location": { "lat": -35.363, "lon": 149.165, "alt": 15.0 }
}
```

---

## 🚀 Execution Plan for "Agent B"
If you assign another AI, give them this prompt:
> "You are the Cloud/Frontend Specialist for Project Neural Guard.
> Your goal is to build a React Dashboard and FastAPI Backend that consumes the JSON API defined in `architecture_handoff.md`.
> Ignore the drone hardware; mock the API responses for now."
