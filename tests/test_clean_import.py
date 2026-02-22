import csv

from src.data.clean_import import _load_provenance, _map_label


def test_map_label_supports_legacy_and_canonical_forms():
    assert _map_label("VIBE_HIGH") == "vibration_high"
    assert _map_label("VIBRATION_HIGH") == "vibration_high"
    assert _map_label("compass_interference") == "compass_interference"
    assert _map_label("ESC_DESYNC") == ""


def test_load_provenance_supports_collector_manifest_fields(tmp_path):
    manifest_path = tmp_path / "crawler_manifest.csv"
    fieldnames = [
        "label",
        "saved_file",
        "status",
        "topic_url",
        "download_url",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "label": "vibration_high",
                "saved_file": "log_0001_vibration_high.bin",
                "status": "downloaded",
                "topic_url": "https://discuss.ardupilot.org/t/some-topic/123",
                "download_url": "https://example.com/log_0001_vibration_high.bin",
            }
        )

    prov = _load_provenance(tmp_path)
    assert "log_0001_vibration_high.bin" in prov
    row = prov["log_0001_vibration_high.bin"][0]
    assert row["label_raw"] == "VIBRATION_HIGH"
    assert row["source_type"] == "ArduPilot_Discuss"
    assert row["thread_url"] == "https://discuss.ardupilot.org/t/some-topic/123"
    assert row["resolved_url"] == "https://example.com/log_0001_vibration_high.bin"
