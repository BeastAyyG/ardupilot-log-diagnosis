from __future__ import annotations

from fastapi.testclient import TestClient

from src.web import app as web_app


def test_health_and_metrics_expose_correlation_and_security_headers():
    client = TestClient(web_app.app)
    response = client.get("/healthz", headers={"X-Request-ID": "trace-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "ardupilot_http_requests_total" in metrics.text
    assert 'path="/healthz"' in metrics.text


def test_invalid_request_id_is_replaced_and_not_reflected(monkeypatch):
    client = TestClient(web_app.app)
    response = client.get("/healthz", headers={"X-Request-ID": "bad id!"})

    request_id = response.headers["X-Request-ID"]
    assert request_id != "bad id!"
    assert len(request_id) == 32


def test_readiness_reports_legacy_model_as_degraded_but_serving(monkeypatch):
    monkeypatch.delenv("ARDUPILOT_REQUIRE_ML_MODEL", raising=False)
    monkeypatch.delenv("ARDUPILOT_REQUIRE_RELEASE_MODEL", raising=False)

    response = TestClient(web_app.app).get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["status"] in {"degraded", "ready"}
    assert body["model"]["model_kind"] in {"legacy_compatibility", "versioned_candidate"}


def test_readiness_can_fail_closed_when_release_model_is_required(monkeypatch):
    monkeypatch.setenv("ARDUPILOT_REQUIRE_RELEASE_MODEL", "1")
    monkeypatch.delenv("ARDUPILOT_REQUIRE_ML_MODEL", raising=False)

    response = TestClient(web_app.app).get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["requirements"]["release_model"] is True


def test_startup_does_not_open_mavlink_without_auth(monkeypatch):
    calls: list[str] = []

    class UnexpectedStreamer:
        def __init__(self, *_args):
            calls.append("init")

        def start(self):
            calls.append("start")

    monkeypatch.setenv("MAVLINK_CONNECTION", "tcp:127.0.0.1:5760")
    monkeypatch.delenv("MAVLINK_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(web_app, "MAVLinkStreamer", UnexpectedStreamer)

    import asyncio

    async def _run_lifespan():
        async with web_app.lifespan(web_app.app):
            pass

    asyncio.run(_run_lifespan())

    assert calls == []
    monkeypatch.delenv("MAVLINK_CONNECTION", raising=False)


def test_json_body_limit_returns_structured_413():
    client = TestClient(web_app.app)
    response = client.post(
        "/api/acceptance",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(web_app.MAX_JSON_BODY_BYTES + 1),
        },
    )

    assert response.status_code == 413
    assert response.json()["code"] == "UPLOAD_TOO_LARGE"


def test_compare_caps_file_count_before_parsing():
    client = TestClient(web_app.app)
    files = [("files", (f"flight-{index}.bin", b"", "application/octet-stream")) for index in range(web_app.MAX_COMPARE_FILES + 1)]

    response = client.post("/api/compare", files=files)

    assert response.status_code == 413
    assert response.json()["details"]["max_files"] == web_app.MAX_COMPARE_FILES


def test_framework_errors_use_versioned_error_codes(monkeypatch, tmp_path):
    monkeypatch.delenv("ARDUPILOT_FLEET_TOKEN", raising=False)
    monkeypatch.setenv("ARDUPILOT_FLEET_DB", str(tmp_path / "fleet.sqlite3"))
    client = TestClient(web_app.app)

    not_found = client.get("/does-not-exist")
    fleet = client.get("/api/fleet/reports")
    validation = client.post("/api/acceptance", json=[])

    assert not_found.status_code == 404
    assert not_found.json()["code"] == "NOT_FOUND"
    assert fleet.status_code == 503
    assert fleet.json()["code"] == "SERVICE_UNAVAILABLE"
    assert fleet.json()["detail"] == "Fleet auth token is not configured"
    assert validation.status_code == 422
    assert validation.json()["code"] == "REQUEST_VALIDATION_FAILED"
