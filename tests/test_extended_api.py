import asyncio

from src.web.app import acceptance, baseline, community_checks, context_location_recurrence, context_temporal, context_video_overlay, graph_pack_report, maintenance, mcp_read_only_rpc, mission_compliance, mission_validate, tools_call, tools_manifest


def _report():
    return {"metadata": {"filename": "healthy.bin", "vehicle": "Copter", "firmware": "4.5"}, "decision": {"status": "healthy"}, "features": {"vibe_z_mean": 1.0}, "hardware_report": {"log_quality": {"overall_status": "RELIABLE"}, "availability": {"capabilities": {}}}}


def test_extended_api_endpoints_are_read_only():
    assert asyncio.run(tools_manifest())["tools"]
    assert asyncio.run(tools_call({"name": "explain", "arguments": {"report": _report()}}))["read_only"] is True
    assert asyncio.run(acceptance({"report": _report()}))["schema_version"] == "flight-acceptance.v1"
    distinct_report = _report()
    distinct_report["metadata"] = {**distinct_report["metadata"], "filename": "healthy-2.bin"}
    assert asyncio.run(baseline({"reports": [_report(), distinct_report]}))["status"] == "reliable"
    assert asyncio.run(maintenance({"before": _report(), "after": _report()}))["schema_version"] == "maintenance-comparison.v1"
    assert asyncio.run(mcp_read_only_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]


def test_agent_tool_manifest_includes_smarttune_style_read_only_tools():
    manifest = asyncio.run(tools_manifest())
    names = {item["name"] for item in manifest["tools"]}
    assert {"analyze_pid", "analyze_fft", "analyze_magfit", "analyze_sysid", "analyze_filter", "hardware_telemetry", "temporal_evidence", "community_check_catalog", "list_params", "validate_param", "generate_plot", "generate_graph_pack"}.issubset(names)


def test_mission_api_and_mcp_are_read_only():
    mission = [{"seq": 0, "command": 16, "lat": 37.422, "lng": -122.084, "alt": 20}]
    assert asyncio.run(mission_validate({"mission": mission}))["status"] == "reliable"
    compliance = asyncio.run(mission_compliance({"mission": mission, "parsed": {"messages": {"GPS": []}}}))
    assert compliance["status"] == "insufficient_data"
    tool_result = asyncio.run(tools_call({"name": "mission_validate", "arguments": {"mission": mission}}))
    assert tool_result["read_only"] is True
    assert tool_result["result"]["write_parameters"] is False


def test_mission_compliance_rejects_non_numeric_tolerance():
    result = asyncio.run(mission_compliance({"mission": [], "tolerance_m": "not-a-number"}))
    assert getattr(result, "status_code", None) == 422


def test_graph_pack_api_is_offline_and_self_contained():
    result = asyncio.run(graph_pack_report({"report": _report(), "parsed": {"messages": {"GPS": []}}}))
    assert result["schema_version"] == "graph-pack.v1"
    assert result["network_requests"] == 0


def test_location_recurrence_api_is_privacy_preserving():
    result = asyncio.run(context_location_recurrence({"reports": []}))
    assert result["schema_version"] == "location-recurrence.v1"
    assert result["privacy"]["coordinates_removed"] is True


def test_video_overlay_api_returns_sorted_sidecar_events():
    result = asyncio.run(context_video_overlay({"parsed": {"errors": [{"time_us": 2_000_000, "message": "late"}, {"time_us": 1_000_000, "message": "early"}]}, "sync": {"status": "review_only", "offset_sec": 3.0}}))
    assert result["schema_version"] == "video-overlay.v1"
    assert [item["video_sec"] for item in result["events"]] == [4.0, 5.0]


def test_video_overlay_api_can_return_webvtt_and_temporal_api_is_read_only():
    result = asyncio.run(context_video_overlay({"parsed": {"errors": [{"time_us": 1_000_000, "message": "GPS"}]}, "sync": {"status": "review_only", "offset_sec": 0.0}, "format": "vtt"}))
    assert result["content_format"] == "vtt"
    assert result["content"].startswith("WEBVTT")
    temporal = asyncio.run(context_temporal({"parsed": {"messages": {"ATT": [{"TimeUS": 0}, {"TimeUS": 1_000_000}]}}, "diagnoses": []}))
    assert temporal["schema_version"] == "temporal-evidence.v1"
    assert asyncio.run(community_checks({"parsed": {}}))["check_count"] == 44
    tool_result = asyncio.run(tools_call({
        "name": "temporal_evidence",
        "arguments": {"parsed": {"messages": {"ATT": [{"TimeUS": 0}, {"TimeUS": 1_000_000}]}}, "diagnoses": []},
    }))
    assert tool_result["read_only"] is True
