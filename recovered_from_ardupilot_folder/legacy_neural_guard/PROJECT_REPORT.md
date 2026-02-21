# Neural Guard - AI-Powered Drone Health Monitoring System

## Project Overview

**Neural Guard** is an AI-powered anomaly detection and health monitoring system built on top of **ArduPilot**, the world's most advanced open-source autopilot software. The system provides real-time inference to detect potential failures (vibration anomalies, voltage sags) before they cause catastrophic drone failures.

### Core Capabilities

- **Real-time Anomaly Detection**: ML-based detection running at 10Hz
- **Edge Computing**: Inference on Raspberry Pi companion computer
- **Failsafe Actions**: Automatic RTL (Return to Launch) or Land commands on anomaly detection
- **Fleet Management**: Cloud-based multi-drone monitoring dashboard
- **Historical Logging**: Long-term data persistence for analysis

---

## Architecture

The system is divided into two parallel workstreams:

### Workstream A: Edge Intelligence (Embedded)
- **Owner**: Embedded AI Specialist
- **Platform**: Raspberry Pi
- **Protocol**: MAVLink
- **Key Components**:
  - Data ingestion from flight controller
  - ML inference engine (`anomaly_model.joblib`)
  - Local REST API on Port 5000
  - Failsafe command triggering

### Workstream B: Cloud & Visualization
- **Owner**: Full-Stack/Cloud Specialist
- **Platform**: FastAPI + React
- **Key Components**:
  - React/TypeScript dashboard
  - FastAPI backend service
  - Multi-drone fleet aggregation
  - Alert management

---

## Technology Stack

### Edge (Companion Computer)
| Component | Technology |
|-----------|------------|
| Language | Python 3.x |
| MAVLink | `pymavlink` |
| ML Model | scikit-learn (`joblib`) |
| Web Server | Flask |
| Hardware | Raspberry Pi |

### Backend (Cloud)
| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Server | Uvicorn |
| API Docs | OpenAPI/Swagger |
| CORS | Enabled (all origins) |
| Port | 8000 |

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | React 18 |
| Language | TypeScript |
| Build Tool | Vite |
| Port | 3000 |

### Infrastructure
| Component | Technology |
|-----------|------------|
| Containerization | Docker + Docker Compose |
| Base Project | ArduPilot (C++) |

---

## Key Files

### Root Directory
| File | Purpose |
|------|---------|
| [`companion_monitor.py`](companion_monitor.py) | Main edge AI system - reads MAVLink, runs inference, exposes API |
| [`anomaly_model.joblib`](anomaly_model.joblib) | Trained scikit-learn model (~1.6MB) |
| [`docker-compose.yml`](docker-compose.yml) | Orchestrates backend + frontend |
| [`architecture_handoff.md`](architecture_handoff.md) | Parallel workstream definition |
| [`test_integration.sh`](test_integration.sh) | Integration test script |

### Backend (`backend/`)
| File | Purpose |
|------|---------|
| [`backend/main.py`](backend/main.py) | FastAPI app with endpoints |
| [`backend/requirements.txt`](backend/requirements.txt) | Python dependencies |
| [`backend/Dockerfile`](backend/Dockerfile) | Container build |

### Frontend (`frontend/`)
| File | Purpose |
|------|---------|
| [`frontend/src/App.tsx`](frontend/src/App.tsx) | Main React dashboard |
| [`frontend/package.json`](frontend/package.json) | Node dependencies |
| [`frontend/vite.config.ts`](frontend/vite.config.ts) | Vite configuration |

### Analysis Tools
| File | Purpose |
|------|---------|
| [`log_analyzer_app.py`](log_analyzer_app.py) | Flight log analysis GUI |
| [`vibe_check.py`](vibe_check.py) | Vibration analysis |
| [`visualize_flight_data.py`](visualize_flight_data.py) | Data visualization |
| [`generate_training_data.py`](generate_training_data.py) | Training data generation |
| [`train_anomaly_model.py`](train_anomaly_model.py) | Model training script |

### Data Files
| File | Purpose |
|------|---------|
| [`flight_data_for_ai.csv`](flight_data_for_ai.csv) | Training dataset (~53KB) |
| [`training_dataset.csv`](training_dataset.csv) | Extended training data (~106KB) |
| [`neural_guard.log`](neural_guard.log) | Runtime logs (~500KB) |

---

## API Contract

### 1. Drone Telemetry (Edge)
**Endpoint**: `GET http://<drone-ip>:5000/api/telemetry`

**Response**:
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
    "risk_score": 0.05,
    "anomaly_type": "none",
    "confidence": 0.98
  },
  "physics": {
    "roll": 0.02,
    "pitch": -0.01,
    "vibe_x": 12.5
  }
}
```

### 2. Cloud Ingest (Fleet Sync)
**Endpoint**: `POST http://localhost:8000/api/ingest`

**Payload**: Same as telemetry + location
```json
{
  "drone_id": "drone_01",
  "timestamp_ms": 1678900000,
  "status": { "connection": "online", "ai_active": true, "battery_pct": 82 },
  "inference": { "risk_score": 0.05, "anomaly_type": "none", "confidence": 0.98 },
  "physics": { "roll": 0.02, "pitch": -0.01, "vibe_x": 12.5 },
  "location": { "lat": -35.363, "lon": 149.165, "alt": 15.0 }
}
```

### 3. Backend Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/drones` | GET | List all drones |
| `/api/drones/{drone_id}/telemetry` | GET | Get telemetry for specific drone |
| `/api/ingest` | POST | Ingest telemetry data |
| `/api/alerts` | GET | Get active alerts |

---

## Running the Project

### Option 1: Docker Compose (Recommended)
```bash
docker-compose up --build
```
- Backend: http://localhost:8000
- Frontend: http://localhost:3000

### Option 2: Manual Setup

**Backend**:
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend**:
```bash
cd frontend
npm install
npm run dev
```

**Edge (Companion)**:
```bash
# Connect to flight controller via MAVLink
python companion_monitor.py
```

---

## ML Model Details

- **Algorithm**: scikit-learn classifier
- **Input Features**: Vibration (x,y,z), voltage, current, roll, pitch, yaw
- **Output Classes**: `none`, `vibration`, `voltage_sag`
- **Inference Speed**: ~10Hz on Raspberry Pi 4
- **Model File**: [`anomaly_model.joblib`](anomaly_model.joblib) (1.6MB)

---

## Integration with ArduPilot

The system integrates with ArduPilot via:
1. **MAVLink**: Reads telemetry from flight controller
2. **Companion Computer**: Runs on Raspberry Pi connected to Pixhawk
3. **Failsafe Commands**: Sends MAVLink commands (RTL/Land) on anomaly detection

---

## Development Status

| Component | Status |
|-----------|--------|
| Edge AI (companion_monitor.py) | ✅ Implemented |
| ML Model (anomaly_model.joblib) | ✅ Trained |
| FastAPI Backend | ✅ Implemented |
| React Dashboard | ✅ Implemented |
| Docker Compose | ✅ Configured |
| Integration Tests | ✅ Available |

---

---

## License

- **ArduPilot**: GNU General Public License v3.0
- **Neural Guard (this project)**: MIT License (if applicable)

---
