from src.analysis.config_health import hardware_inventory, hardware_telemetry, review_configuration, throughput_health
from src.analysis.context_metrics import analyze_flight_context, raw_message_explorer
from src.analysis.estimator_propulsion import analyze_ekf_lanes, analyze_propulsion
from src.analysis.operations_metrics import acceptance_report, build_baseline, location_context, maintenance_comparison, mission_compliance, phase_replay, wind_metrics
from src.analysis.airspeed_fit import fit_airspeed
from src.analysis.weather_video import synchronize_video, weather_context
from src.analysis.safety_advanced import classify_end_of_log, counterfactual_checks, failsafe_taxonomy, review_queue
from src.analysis.tuning_advanced import pid_component_breakdown, pid_spectrogram, system_identification
from src.integrations.read_only_tools import dispatch_tool


def _parsed():
    samples = [{"TimeUS": i * 100_000, "AccZ": 1.0, "GyrZ": 0.1, "VibeZ": 2.0, "VibeX": 1.0, "VibeY": 1.0, "Clip": 0} for i in range(80)]
    return {
        "metadata": {"duration_sec": 8.0, "message_types": {"IMU": 80, "ATT": 80, "STAT": 2, "CTUN": 80, "RCOU": 80, "VIBE": 80, "GPS": 80, "MODE": 1, "CMD": 2, "PM": 2, "ERR": 1, "XKF1": 2, "XKF4": 2, "RATE": 80}, "parse_complete": True},
        "messages": {
            "IMU": samples,
            "VIBE": samples,
            "ATT": [{"TimeUS": i * 100_000, "DesRoll": 0, "DesPitch": 0, "DesYaw": 0} for i in range(80)],
            "CTUN": [{"TimeUS": i * 100_000, "ThO": 0.5, "Alt": i * 0.1} for i in range(80)],
            "RCOU": [{"TimeUS": i * 100_000, "C1": 1500, "C2": 1510} for i in range(80)],
            "GPS": [{"TimeUS": i * 100_000, "Lat": 123000000, "Lng": 456000000, "Alt": 10} for i in range(80)],
            "STAT": [{"TimeUS": 0, "isFlying": 0}, {"TimeUS": 200000, "isFlying": 1}],
            "MODE": [{"TimeUS": 200000, "ModeNum": 3}],
            "CMD": [{"TimeUS": 200000, "CNum": 1}, {"TimeUS": 300000, "CNum": 2}],
            "PM": [{"TimeUS": 0, "Load": 20, "LogDrop": 0}, {"TimeUS": 100000, "Load": 20, "LogDrop": 0}],
            "XKF1": [{"TimeUS": 0, "SV": 0.1}, {"TimeUS": 100000, "SV": 0.2}],
            "XKF4": [{"TimeUS": 0, "SV": 0.1}, {"TimeUS": 100000, "SV": 0.2}],
            "RATE": [{"TimeUS": i * 100_000, "RDes": 5.0 if i % 20 > 5 else 0.0, "R": 4.0} for i in range(80)],
        },
        "errors": [{"time_us": 400000, "subsystem_name": "FAILSAFE_RADIO", "code": 1}],
        "events": [],
        "mode_changes": [{"time_us": 200000, "mode_name": "Auto"}],
        "status_messages": [],
        "parameter_changes": [],
        "parameters": {"COMPASS_USE": 1, "GPS_TYPE": 1, "INS_GYRO_FILTER": 30},
    }


def test_extended_analysis_contracts_are_presence_gated():
    parsed = _parsed()
    assert analyze_flight_context(parsed)["schema_version"] == "flight-context.v1"
    assert raw_message_explorer(parsed)["stream_count"] > 0
    assert hardware_inventory(parsed)["schema_version"] == "hardware-inventory.v1"
    assert review_configuration(parsed)["schema_version"] == "configuration-review.v1"
    assert throughput_health(parsed)["status"] == "reliable"
    ekf_lanes = analyze_ekf_lanes(parsed)
    assert ekf_lanes["schema_version"] == "ekf-lane-metrics.v1"
    assert set(ekf_lanes["streams"]) == {"XKF"}
    assert analyze_propulsion(parsed)["schema_version"] == "propulsion-metrics.v1"
    assert pid_component_breakdown(parsed)["schema_version"] == "pid-component-breakdown.v1"
    assert pid_spectrogram(parsed)["schema_version"] == "pid-spectrogram.v1"
    assert system_identification(parsed)["schema_version"] == "system-identification.v1"


def test_safety_and_operations_contracts():
    parsed = _parsed()
    assert failsafe_taxonomy(parsed)["counts"]["rc"] == 1
    assert classify_end_of_log(parsed)["schema_version"] == "end-of-log.v1"
    assert counterfactual_checks([{"failure_type": "rc_failsafe", "evidence": []}], parsed)["checks"]
    assert review_queue(parsed, [{"failure_type": "rc_failsafe", "confidence": 0.4}])["questions"]
    assert mission_compliance(parsed)["command_count"] == 2
    assert fit_airspeed(parsed)["status"] == "insufficient_data"
    assert weather_context(parsed)["status"] == "insufficient_data"
    assert synchronize_video([0, 1_000_000], [{"log_time_us": 0, "video_sec": 2.0}])["offset_sec"] == 2.0


def test_location_context_accepts_normalized_generic_adapter_coordinates():
    result = location_context({"messages": {"GPS": [{"Lat": 12.0, "Lng": 77.0}]}})
    assert result["status"] == "review_only"
    assert result["grid_key"] == "12.000,77.000"


def test_airspeed_fit_pairs_asynchronous_streams_by_timestamp():
    gps_speeds = [10.0 + index for index in range(10)]
    gps = [{"TimeUS": index * 1_000_000, "Spd": speed, "GCrs": index * 45.0} for index, speed in enumerate(gps_speeds)]
    arsp = [{"TimeUS": index * 1_000_000, "Airspeed": 2.0 * gps_speeds[index]} for index in reversed(range(10))]
    result = fit_airspeed({"messages": {"ARSP": arsp, "GPS": gps}, "parameters": {}})
    assert result["alignment_method"] == "timestamp_nearest"
    assert result["paired_sample_count"] == 10
    assert result["fitted_arspd_ratio"] == 2.0
    assert result["identifiable"] is True


def test_wind_metrics_deduplicates_estimator_streams_and_uses_circular_direction():
    result = wind_metrics(
        {
            "messages": {
                "XKF2": [{"TimeUS": 1, "VWN": 10.0, "VWE": -0.2}, {"TimeUS": 2, "VWN": 10.0, "VWE": 0.2}],
                "NKF2": [{"TimeUS": 1, "VWN": 10.0, "VWE": -0.2}],
            }
        }
    )
    assert result["sample_count"] == 2
    assert result["direction_deg"]["mean"] < 5.0 or result["direction_deg"]["mean"] > 355.0


def test_phase_replay_normalizes_dataflash_integer_coordinates():
    result = phase_replay(
        {
            "messages": {
                "GPS": [
                    {"TimeUS": 1_000_000, "Lat": 120000000, "Lng": 770000000, "Alt": 42}
                ]
            },
            "errors": [],
        }
    )
    assert result["samples"][0]["lat"] == 12.0
    assert result["samples"][0]["lng"] == 77.0


def test_baseline_maintenance_acceptance_and_tools():
    report = {"metadata": {"filename": "healthy.bin", "vehicle": "Copter", "firmware": "4.5"}, "decision": {"status": "healthy"}, "features": {"vibe_z_mean": 1.0}, "hardware_report": {"log_quality": {"overall_status": "RELIABLE"}, "availability": {"capabilities": {}}}}
    distinct_report = {**report, "metadata": {**report["metadata"], "filename": "healthy-2.bin"}}
    baseline = build_baseline([report, distinct_report])
    assert baseline["status"] == "reliable"
    duplicate = build_baseline([report, report])
    assert duplicate["status"] == "insufficient_data"
    assert duplicate["duplicate_count"] == 1
    assert maintenance_comparison(report, report)["status"] == "review_only"
    assert acceptance_report(report)["status"] in {"pass", "review"}
    assert dispatch_tool("capabilities")["capabilities"]


def test_hardware_telemetry_exposes_webtools_sections_without_raw_rows():
    parsed = _parsed()
    parsed["messages"]["PM"] = [
        {"TimeUS": 0, "Load": 22, "Mem": 100000, "NLon": 500, "LogDrop": 0, "LogBuf": 80},
        {"TimeUS": 1_000_000, "Load": 35, "Mem": 99000, "NLon": 520, "LogDrop": 1, "LogBuf": 75},
    ]
    parsed["messages"]["POWR"] = [{"TimeUS": 0, "Vcc": 5.1, "VServo": 5.0, "Flags": 3}]
    parsed["parameters"].update({"INS_POS1_X": 0.1, "COMPASS_OFS_X": 120})
    result = hardware_telemetry(parsed)
    assert result["status"] == "reliable"
    assert result["cpu_and_memory"]["cpu_load"]["max"] == 35.0
    assert result["power_rails"]["POWR"]["max"] == 5.1
    assert result["power_flags"]["POWR"]["last"]["Flags"] == 3
    assert result["sensor_offsets"]["INS_POS1_X"] == 0.1
    assert result["clock_drift"]["streams"]["PM"]["reversal_count"] == 0
