import csv
import shutil

from src.data.clean_import import _choose_provenance, _load_provenance, _map_label


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


def test_search_label_is_provisional_until_expert_manifest_proves_it(tmp_path):
    shutil.copy2("sample.bin", tmp_path / "sample.bin")
    manifest_path = tmp_path / "crawler_manifest_v2.csv"
    fieldnames = [
        "label",
        "normalized_label",
        "label_source",
        "expert_username",
        "expert_quote",
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
                "label": "mechanical_failure",
                "normalized_label": "",
                "label_source": "",
                "expert_username": "",
                "expert_quote": "",
                "saved_file": "sample.bin",
                "status": "downloaded",
                "topic_url": "https://discuss.ardupilot.org/t/example/1",
                "download_url": "https://example.com/sample.bin",
            }
        )

    from src.data.clean_import import run_clean_import

    result = run_clean_import(str(tmp_path), str(tmp_path / "clean"), copy_files=False)
    assert result["counts"]["verified_labeled"] == 0
    assert result["counts"]["provisional_labeled"] == 1


def test_verified_provenance_wins_over_higher_priority_query_manifest():
    records = [
        {
            "manifest": "crawler_manifest_v2.csv",
            "status": "downloaded",
            "label_raw": "VIBE_HIGH",
            "verified_label": "",
            "source_type": "ArduPilot_Discuss",
            "thread_url": "https://discuss.ardupilot.org/t/case/1",
        },
        {
            "manifest": "download_manifest.csv",
            "status": "downloaded",
            "label_raw": "VIBE_HIGH",
            "verified_label": "VIBE_HIGH",
            "source_type": "ArduPilot_Discuss",
            "thread_url": "https://discuss.ardupilot.org/t/case/1",
        },
    ]
    selected = _choose_provenance(records)
    assert selected is not None
    assert selected["verified_label"] == "VIBE_HIGH"
