import base64
import csv
from pathlib import Path

import pytest

from src.reporting.parameter_catalog import list_parameters, load_catalog, search_parameters, validate_parameter
from src.reporting.parameter_validation import validate_parameters
from src.reporting.plot_export import generate_plot
from src.reporting.graph_pack import export_graph_pack, generate_graph_pack
from src.reporting.artifacts import artifact_manifest, export_artifacts
from src.reporting.raw_export import derived_series, export_csv, export_parquet


def _parsed():
    return {"messages": {"GPS": [{"TimeUS": 1, "Alt": 10}, {"TimeUS": 2, "Alt": 12}], "BARO": [{"TimeUS": 1, "Alt": 9}, {"TimeUS": 2, "Alt": 11}]}}


def test_raw_csv_parquet_and_derived_exports(tmp_path: Path):
    csv_path = export_csv(_parsed(), tmp_path / "messages.csv", message_types=["GPS"])
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    parquet_path = export_parquet(_parsed(), tmp_path / "messages.parquet")
    assert parquet_path.stat().st_size > 0
    derived = derived_series(_parsed(), "GPS.Alt-BARO.Alt")
    assert derived["values"] == [1.0, 1.0]


def test_derived_export_rejects_code_and_malformed_arithmetic():
    with pytest.raises(ValueError, match="not valid arithmetic"):
        derived_series(_parsed(), "GPS.Alt-)")
    with pytest.raises(ValueError, match="Only MESSAGE.FIELD"):
        derived_series(_parsed(), "GPS.Alt.__class__")


def test_plot_export_is_valid_png():
    result = generate_plot({"health_score": {"score": 88, "module_scores": {"battery": 90}}, "diagnoses": []}, kind="health")
    assert result["status"] == "reliable"
    assert base64.b64decode(result["data"]).startswith(b"\x89PNG")


def test_graph_pack_is_self_contained_html(tmp_path: Path):
    result = generate_graph_pack({"health_score": {"score": 91}, "diagnoses": []}, parsed=_parsed())
    assert result["status"] == "reliable"
    assert result["network_requests"] == 0
    assert "const data=" in result["html"]
    path = export_graph_pack({"health_score": {"score": 91}}, tmp_path / "pack.html")
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_artifact_export_writes_hashed_manifest(tmp_path: Path):
    parsed = {"messages": {"CMD": [{"CNum": 0, "CId": 16, "Lat": 1.0, "Lng": 2.0, "Alt": 3.0}], "LUA": [{"Name": "script.lua"}]}}
    manifest = artifact_manifest(parsed)
    assert manifest["artifacts"]["cmd"]["count"] == 1
    destination = export_artifacts(parsed, tmp_path / "artifacts")
    assert (destination / "cmd.json").exists()
    assert (destination / "manifest.json").exists()


def test_parameter_catalog_is_explicit_and_conservative():
    listed = list_parameters(category="pid")
    assert listed["count"] >= 3
    assert search_parameters("notch")["count"] >= 2
    assert validate_parameter("INS_GYRO_FILTER", 60)["status"] == "valid"
    assert validate_parameter("NOT_A_REAL_PARAM", 1)["status"] == "not_validated"


def test_supplied_firmware_catalog_is_used_without_global_mutation(tmp_path: Path):
    catalog_path = tmp_path / "firmware-4.6.json"
    catalog_path.write_text('{"parameters":[{"name":"CUSTOM_GAIN","platform":"ardupilot","category":"pid","unit":"gain","min":0,"max":2}]}', encoding="utf-8")
    catalog = load_catalog(catalog_path)
    assert list_parameters(catalog=catalog)["count"] == 1
    assert validate_parameter("CUSTOM_GAIN", 3, catalog=catalog)["status"] == "invalid"
    assert validate_parameter("ATC_RAT_RLL_P", 1)["status"] == "valid"
    report = validate_parameters({"CUSTOM_GAIN": 3}, catalog=catalog)
    assert report["status"] == "invalid"
    assert report["catalog"]["source"] == "supplied"
