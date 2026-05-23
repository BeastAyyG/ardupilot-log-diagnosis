from __future__ import annotations

import csv
import logging
import sys
from unittest.mock import patch

from src.cli.main import main


def test_batch_no_bin_files(tmp_path, capsys):
    # Non-bin files only
    f = tmp_path / "test.txt"
    f.write_text("hello")

    output_csv = tmp_path / "results.csv"
    test_args = ["main", "batch", str(tmp_path), "--output", str(output_csv)]

    with patch.object(sys, "argv", test_args):
        try:
            main()
        except SystemExit as exc:
            assert exc.code in (0, None)

    # Assert output message
    captured = capsys.readouterr()
    assert "No .BIN files found" in captured.out
    assert not output_csv.exists()


def test_batch_single_file_success(tmp_path):
    # 1. Create a dummy .bin file (case-insensitive test)
    f = tmp_path / "flight_log.bin"
    f.write_text("dummy binary data")

    output_csv = tmp_path / "results.csv"

    # Mocks
    fake_parsed = {
        "metadata": {
            "filepath": str(f),
            "duration_sec": 45.5,
            "vehicle_type": "Plane",
            "firmware_version": "ArduPlane V4.1.0",
            "total_messages": 100,
            "message_types": {},
        },
        "messages": {},
        "parameters": {},
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
    }

    fake_features = {
        "_metadata": {
            "log_file": str(f),
            "duration_sec": 45.5,
            "vehicle_type": "Plane",
            "firmware": "ArduPlane V4.1.0",
            "extraction_success": True,
        }
    }

    fake_diagnoses = [
        {
            "failure_type": "compass_interference",
            "confidence": 0.92,
            "severity": "warning",
            "detection_method": "rule",
            "evidence": [],
            "recommendation": "Calibrate compass",
            "reason_code": "MAG",
        }
    ]

    fake_decision = {
        "status": "confirmed",
        "requires_human_review": False,
        "top_guess": "compass_interference",
        "top_confidence": 0.92,
        "rationale": [],
        "ranked_subsystems": [],
    }

    test_args = ["main", "batch", str(tmp_path), "--output", str(output_csv)]

    with patch("src.parser.bin_parser.LogParser.parse", return_value=fake_parsed), \
         patch("src.features.pipeline.FeaturePipeline.extract", return_value=fake_features), \
         patch("src.diagnosis.hybrid_engine.HybridEngine.diagnose", return_value=fake_diagnoses), \
         patch("src.cli.commands.batch.evaluate_decision", return_value=fake_decision):
        
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as exc:
                assert exc.code in (0, None)

    # 2. Assert CSV is created correctly with expected row
    assert output_csv.exists()
    with open(output_csv, "r", encoding="utf-8") as csv_file:
        reader = list(csv.DictReader(csv_file))
        assert len(reader) == 1
        row = reader[0]
        assert row["filename"] == "flight_log.bin"
        assert float(row["duration"]) == 45.5
        assert row["vehicle"] == "Plane"
        assert row["diagnosis"] == "compass_interference"
        assert float(row["confidence"]) == 0.92
        assert row["requires_review"] == "False"


def test_batch_failure_skipping(tmp_path, caplog):
    # Create 3 files:
    # 1. fail.BIN -> raises exception during parsing
    # 2. healthy.bin -> success, returns empty diagnoses
    # 3. corrupt.BIN -> metadata has extraction_success = False
    
    f_fail = tmp_path / "fail.BIN"
    f_fail.write_text("fail log")
    
    f_healthy = tmp_path / "healthy.bin"
    f_healthy.write_text("healthy log")

    f_corrupt = tmp_path / "corrupt.BIN"
    f_corrupt.write_text("corrupt log")

    output_csv = tmp_path / "results.csv"

    # Set up pipeline mocks
    def mock_parse(self):
        if "fail.BIN" in self.filepath:
            raise RuntimeError("Parser crashed")
        return {
            "metadata": {
                "filepath": self.filepath,
                "duration_sec": 10.0,
                "vehicle_type": "Rover",
                "firmware_version": "ArduRover",
            },
            "messages": {},
            "parameters": {},
            "errors": [],
            "events": [],
            "mode_changes": [],
            "status_messages": [],
        }

    def mock_extract(self, parsed):
        filepath = parsed["metadata"]["filepath"]
        if "corrupt.BIN" in filepath:
            return {
                "_metadata": {
                    "log_file": filepath,
                    "duration_sec": 0.0,
                    "vehicle_type": "Rover",
                    "extraction_success": False,
                }
            }
        return {
            "_metadata": {
                "log_file": filepath,
                "duration_sec": 10.0,
                "vehicle_type": "Rover",
                "extraction_success": True,
            }
        }

    test_args = ["main", "batch", str(tmp_path), "--output", str(output_csv)]

    with patch("src.parser.bin_parser.LogParser.parse", mock_parse), \
         patch("src.features.pipeline.FeaturePipeline.extract", mock_extract), \
         patch("src.diagnosis.hybrid_engine.HybridEngine.diagnose", return_value=[]), \
         patch("src.cli.commands.batch.evaluate_decision", return_value={"requires_human_review": True}), \
         caplog.at_level(logging.WARNING):

        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as exc:
                assert exc.code in (0, None)

    # Assert CSV exists and contains only the successful row
    assert output_csv.exists()
    with open(output_csv, "r", encoding="utf-8") as csv_file:
        reader = list(csv.DictReader(csv_file))
        assert len(reader) == 1
        row = reader[0]
        assert row["filename"] == "healthy.bin"
        assert float(row["duration"]) == 10.0
        assert row["vehicle"] == "Rover"
        assert row["diagnosis"] == "healthy"
        assert float(row["confidence"]) == 0.0
        assert row["requires_review"] == "True"

    # Assert warning was logged for both failures
    warnings = [rec.message for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert any("fail.BIN" in w and "Parser crashed" in w for w in warnings)
    assert any("corrupt.BIN" in w and "Extraction failed" in w for w in warnings)
