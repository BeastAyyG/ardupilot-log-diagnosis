# Neural Guard - FastAPI Backend

## Requirements
- fastapi>=0.100.0
- uvicorn>=0.23.0
- pydantic>=2.0.0
- python-dateutil>=2.8.0

## Installation
```bash
pip install -r requirements.txt
```

## Running the Server
```bash
uvicorn main:app --reload --port 8000
```

## API Endpoints
- `GET /api/health` - Health check
- `GET /api/drones` - List all drones
- `GET /api/drones/{drone_id}/telemetry` - Get telemetry for a drone
- `POST /api/ingest` - Ingest telemetry data from drones
- `GET /api/alerts` - Get active alerts
