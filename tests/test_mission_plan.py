from __future__ import annotations

from src.analysis.mission_plan import mission_compliance_report, normalize_mission, validate_mission


def _parsed_track():
    return {
        "messages": {
            "GPS": [
                {"Lat": 374220000, "Lng": -1220840000, "Alt": 20, "TimeUS": 1_000_000},
                {"Lat": 374221000, "Lng": -1220841000, "Alt": 21, "TimeUS": 2_000_000},
            ]
        }
    }


def test_mission_normalizes_qgc_wpl_and_scaled_coordinates():
    qgc = "QGC WPL 110\n0\t1\t0\t16\t0\t0\t0\t0\t37.422\t-122.084\t20\t1"
    rows = normalize_mission(qgc)
    assert rows[0]["seq"] == 0
    assert rows[0]["lat"] == 37.422
    assert rows[0]["alt"] == 20.0


def test_mission_validation_is_explicitly_read_only():
    result = validate_mission([{"seq": 0, "command": 16, "lat": 37.422, "lng": -122.084, "alt": 20}])
    assert result["status"] == "reliable"
    assert result["write_parameters"] is False


def test_mission_validation_reports_malformed_altitude_and_fence():
    result = validate_mission([{"seq": 0, "lat": 37.422, "lng": -122.084, "alt": "unknown"}], geofence=[{"lat": 37.422, "lng": -122.084}])
    issue_types = {item["type"] for item in result["issues"]}
    assert {"invalid_altitude", "invalid_geofence"}.issubset(issue_types)


def test_mission_compliance_matches_track_and_reports_fence_deviation():
    mission = [{"seq": 0, "lat": 37.422, "lng": -122.084, "alt": 20}]
    fence = [{"lat": 37.421, "lng": -122.085}, {"lat": 37.421, "lng": -122.083}, {"lat": 37.423, "lng": -122.083}, {"lat": 37.423, "lng": -122.085}]
    result = mission_compliance_report(_parsed_track(), mission, geofence=fence)
    assert result["schema_version"] == "mission-compliance.v2"
    assert result["hit_count"] == 1
    assert result["fence_violation_count"] == 0
    assert result["write_parameters"] is False


def test_mission_normalizes_scaled_latitude_alias_and_rejects_nonfinite_track_points():
    rows = normalize_mission([{"seq": 1, "latitude": 374220000, "longitude": -1220840000, "altitude": 20}])
    assert rows[0]["lat"] == 37.422
    assert rows[0]["lng"] == -122.084
    parsed = {"messages": {"GPS": [{"Lat": float("nan"), "Lng": -122.084, "TimeUS": 1}, {"Lat": 37.422, "Lng": -122.084, "TimeUS": 2}]}}
    result = mission_compliance_report(parsed, [{"seq": 1, "lat": 37.422, "lng": -122.084, "alt": 20}])
    assert result["observed_points"] == 1


def test_mission_fence_result_is_invariant_to_polygon_orientation():
    mission = [{"seq": 0, "lat": 37.422, "lng": -122.084, "alt": 20}]
    fence = [{"lat": 37.421, "lng": -122.085}, {"lat": 37.421, "lng": -122.083}, {"lat": 37.423, "lng": -122.083}, {"lat": 37.423, "lng": -122.085}]
    parsed = _parsed_track()
    forward = mission_compliance_report(parsed, mission, geofence=fence)
    reverse = mission_compliance_report(parsed, mission, geofence=list(reversed(fence)))
    assert forward["fence_violation_count"] == reverse["fence_violation_count"] == 0
