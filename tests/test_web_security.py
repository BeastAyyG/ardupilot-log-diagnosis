from __future__ import annotations

from fastapi.testclient import TestClient

from src.web import app as web_app


def test_cors_defaults_to_same_origin_only(monkeypatch):
    monkeypatch.delenv("ARDUPILOT_CORS_ORIGINS", raising=False)
    origins, credentials = web_app._cors_configuration()
    assert origins == []
    assert credentials is False


def test_cors_wildcard_never_enables_credentials(monkeypatch):
    monkeypatch.setenv("ARDUPILOT_CORS_ORIGINS", "*")
    origins, credentials = web_app._cors_configuration()
    assert origins == ["*"]
    assert credentials is False


def test_fleet_http_api_fails_closed_without_token(monkeypatch, tmp_path):
    monkeypatch.setenv("ARDUPILOT_FLEET_DB", str(tmp_path / "fleet.sqlite3"))
    monkeypatch.delenv("ARDUPILOT_FLEET_TOKEN", raising=False)

    response = TestClient(web_app.app).get("/api/fleet/reports")

    assert response.status_code == 503
    assert response.json()["detail"] == "Fleet auth token is not configured"


def test_fleet_http_api_accepts_bearer_and_legacy_query_token(monkeypatch, tmp_path):
    monkeypatch.setenv("ARDUPILOT_FLEET_DB", str(tmp_path / "fleet.sqlite3"))
    monkeypatch.setenv("ARDUPILOT_FLEET_TOKEN", "test-fleet-token")
    client = TestClient(web_app.app)

    assert client.get("/api/fleet/reports").status_code == 401
    bearer = client.get("/api/fleet/reports", headers={"Authorization": "Bearer test-fleet-token"})
    query = client.get("/api/fleet/reports?token=test-fleet-token")
    mismatched = client.get(
        "/api/fleet/reports?token=wrong",
        headers={"Authorization": "Bearer test-fleet-token"},
    )

    assert bearer.status_code == 200
    assert query.status_code == 200
    assert mismatched.status_code == 401

