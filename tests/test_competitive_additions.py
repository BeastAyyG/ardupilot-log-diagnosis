from src.analysis.ascent_recovery import analyze_ascent_recovery
from src.analysis.health_score import calculate_health_score
from src.analysis.methodic_review import STEP_PROFILES, review_methodic_step
from src.analysis.operations_metrics import location_recurrence
from src.analysis.temporal import temporal_evidence
from src.analysis.weather_video import video_overlay_text
from src.analysis.weather_video import build_video_overlay, synchronize_video
from src.analysis.aynalike import CHECK_SPECS, run_aynalike_checks
from src.fleet.alerts import evaluate_alerts, validate_webhook_url
from src.reporting.geo_export import to_gpx, to_kml, track_points


def test_health_score_is_explainable_and_capped():
    result = calculate_health_score({"diagnoses": [{"failure_type": "battery sag", "severity": "critical", "confidence": 1.0}], "hardware_report": {"log_quality": {"overall_status": "RELIABLE"}}})
    assert result["schema_version"] == "health-score.v1"
    assert 0 <= result["score"] <= 100
    assert result["evidence"][0]["module"] == "battery"
    assert "safe-to-fly" in result["airworthiness_statement"]


def test_health_score_penalizes_unsupported_input():
    result = calculate_health_score(
        {"diagnoses": [], "hardware_report": {"log_quality": {"overall_status": "UNSUPPORTED"}}}
    )
    assert result["score"] == 75.0
    assert result["status"] == "degraded"
    assert "unsupported" in result["quality_reason"]


def test_health_score_marks_degraded_input_status():
    result = calculate_health_score(
        {"diagnoses": [], "hardware_report": {"log_quality": {"overall_status": "DEGRADED"}}}
    )
    assert result["score"] == 90.0
    assert result["status"] == "degraded"


def test_offline_track_exports_handle_scaled_and_decimal_gps():
    parsed = {"messages": {"GPS": [{"TimeUS": 1, "Lat": 120000000, "Lng": 770000000, "Alt": 10}, {"TimeUS": 2, "Lat": 120000100, "Lng": 770000100, "Alt": 11}]}}
    points = track_points(parsed)
    assert points["point_count"] == 2
    assert "<trkpt" in to_gpx(parsed)
    assert "77.0000100,12.0000100" in to_kml(parsed)


def test_methodic_review_blocks_missing_evidence_and_never_writes():
    result = review_methodic_step({"hardware_report": {"log_quality": {"overall_status": "RELIABLE"}}}, "8.1")
    assert result["status"] == "blocked"
    assert result["write_parameters"] is False


def test_methodic_catalog_covers_the_published_workflow_steps():
    expected = {"7.1", "7.1.1", "8.1", "8.2", "8.3", "8.4", "8.5", "9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7", "10.1", "10.2", "11.1", "11.2", "12.1", "12.2", "12.3", "13"}
    assert expected.issubset(STEP_PROFILES)


def test_ascent_recovery_is_inapplicable_for_flat_flight():
    parsed = {"messages": {"GPS": [{"TimeUS": i * 1_000_000, "Alt": 10.0} for i in range(8)]}}
    assert analyze_ascent_recovery(parsed)["status"] == "inapplicable"


def test_alert_preview_is_local_and_webhook_is_https_only():
    report = {"health_score": {"score": 55}, "diagnoses": []}
    result = evaluate_alerts(report, [{"id": "low", "metric": "health_score", "below": 80}])
    assert result["status"] == "alert"
    assert result["network_action"] == "none; this endpoint only previews alerts"
    assert validate_webhook_url("http://example.com")["valid"] is False
    assert validate_webhook_url("https://hooks.example.com/x")["valid"] is True


def test_location_recurrence_is_coarse_and_requires_repeated_findings():
    reports = [
        {"hardware_report": {"location_context": {"grid_key": "37.422,-122.084"}}, "diagnoses": [{"failure_type": "gps_quality_poor"}]},
        {"hardware_report": {"location_context": {"grid_key": "37.422,-122.084"}}, "diagnoses": [{"failure_type": "gps_quality_poor"}]},
    ]
    result = location_recurrence(reports)
    assert result["clusters"]["37.422,-122.084"]["recurrence_candidate"] is True
    assert result["privacy"]["coordinates_removed"] is True


def test_temporal_evidence_smoother_preserves_onset_and_caps_transient_support():
    parsed = {"messages": {"ATT": [{"TimeUS": 0}, {"TimeUS": 1_000_000}, {"TimeUS": 2_000_000}]}}
    result = temporal_evidence(parsed, [{"failure_type": "gps_quality_poor", "confidence": 0.9, "evidence": [{"time_us": 1_000_000}]}])
    assert result["schema_version"] == "temporal-evidence.v1"
    assert result["candidates"][0]["status"] == "transient"
    assert result["candidates"][0]["confidence_cap"] == 0.65
    assert result["candidates"][0]["first_onset_us"] == 1_000_000


def test_video_overlay_exports_webvtt_and_srt_content():
    sidecar = {"status": "review_only", "events": [{"video_sec": 1.25, "kind": "error", "label": "GPS"}]}
    assert "WEBVTT" in video_overlay_text(sidecar, format_name="vtt")
    assert "00:00:01,250 -->" in video_overlay_text(sidecar, format_name="srt")


def test_video_sync_rejects_nonfinite_manual_points_and_overlay_offsets():
    result = synchronize_video([0, 1_000_000], [{"log_time_us": 0, "video_sec": float("nan")}, {"log_time_us": 0, "video_sec": 2.0}])
    assert result["status"] == "review_only"
    assert result["rejected_point_count"] == 1
    assert result["sync_points"] == [{"log_time_us": 0.0, "video_sec": 2.0}]
    invalid = build_video_overlay({"errors": []}, {"status": "review_only", "offset_sec": float("nan")})
    assert invalid["status"] == "insufficient_data"


def test_community_check_catalog_has_44_evidence_cards_and_never_fabricates_missing_data():
    result = run_aynalike_checks({"messages": {}})
    assert len(CHECK_SPECS) == 44
    assert result["check_count"] == 44
    assert result["counts"]["insufficient_data"] == 44
    assert result["write_parameters"] is False
