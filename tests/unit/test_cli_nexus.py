import argparse
import json
from types import SimpleNamespace

import pytest

from src.cli.commands import analyze


def _parse(*arguments: str):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze.register(subparsers)
    return parser.parse_args(["analyze", "flight.BIN", *arguments])


def _stub_analysis(monkeypatch, dispatch_result):
    parsed = {"metadata": {}, "parameters": {}}
    features = {
        "_metadata": {
            "log_file": "flight.BIN",
            "duration_sec": 0.0,
            "vehicle_type": "Unknown",
            "firmware": "",
            "quality_report": {},
            "extraction_success": True,
        }
    }
    calls = []

    monkeypatch.setattr(analyze, "load_parsed_and_features", lambda _: (parsed, features))
    monkeypatch.setattr(analyze, "ensure_extraction_success", lambda *_: None)
    monkeypatch.setattr(analyze, "diagnose_with_windowed_ml", lambda *_: ([], {}))
    monkeypatch.setattr(analyze, "evaluate_decision", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(analyze, "validate_parameters", lambda *_args: [])
    monkeypatch.setattr(analyze, "calculate_health_score", lambda **_kwargs: {})
    monkeypatch.setattr(analyze, "FailureRetrieval", lambda: SimpleNamespace(find_similar=lambda _: []))
    monkeypatch.setattr(
        analyze,
        "HardwareReportBuilder",
        lambda: SimpleNamespace(build=lambda *_args, **_kwargs: {"log_quality": {}}),
    )

    class _Engine:
        ml = SimpleNamespace(available=False, unavailable_reason="test")
        last_explain_data = None

    monkeypatch.setattr(analyze, "HybridEngine", _Engine)
    monkeypatch.setattr(analyze, "RuleEngine", _Engine)

    from src.integrations import read_only_tools

    def _dispatch(name, arguments):
        calls.append((name, arguments))
        return dispatch_result

    monkeypatch.setattr(read_only_tools, "dispatch_tool", _dispatch)
    return parsed, calls


def test_analyze_parser_accepts_nexus_without_changing_defaults():
    args = _parse("--nexus")

    assert args.nexus is True
    assert args.no_ml is False
    assert args.format == "terminal"

    defaults = _parse()
    assert defaults.nexus is False


def test_nexus_dispatch_is_called_once_with_parsed_input(monkeypatch, capsys):
    parsed, calls = _stub_analysis(
        monkeypatch,
        {
            "schema_version": "diagnose-flight-log.v1",
            "status": "degraded",
            "evidence": {"marker": "kept"},
            "read_only": True,
        },
    )

    analyze.run(_parse("--nexus", "--json"))
    report = json.loads(capsys.readouterr().out)

    assert len(calls) == 1
    assert calls[0][0] == "diagnose_flight_log"
    assert calls[0][1] == {"parsed": parsed}
    assert report["runtime"]["nexus_enabled"] is True
    assert report["runtime"]["nexus_status"] == "degraded"
    assert report["runtime"]["nexus_result"]["evidence"]["marker"] == "kept"


@pytest.mark.parametrize(
    ("arguments", "marker"),
    [
        (("--nexus",), "CITA-Nexus"),
        (("--nexus", "--format", "html"), "CITA-Nexus"),
    ],
)
def test_nexus_output_contains_explicit_evidence(monkeypatch, capsys, arguments, marker):
    _stub_analysis(
        monkeypatch,
        {
            "schema_version": "diagnose-flight-log.v1",
            "status": "error",
            "error": {"code": "INVALID_ARGUMENT", "message": "insufficient telemetry"},
            "read_only": True,
        },
    )

    analyze.run(_parse(*arguments))
    output = capsys.readouterr().out

    assert marker in output
    assert "INVALID_ARGUMENT" in output
    assert "insufficient telemetry" in output
