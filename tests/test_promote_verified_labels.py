import json

from training.promote_verified_labels import _sha256, promote


def test_promote_copies_verified_log_into_buildable_dataset(tmp_path):
    source = tmp_path / "flight.bin"
    source.write_bytes(b"verified-flight")
    sha256 = _sha256(str(source))
    provisional = tmp_path / "provisional.json"
    provisional.write_text(
        json.dumps(
            {
                "logs": [
                    {
                        "filename": source.name,
                        "path": str(source),
                        "sha256": sha256,
                        "status": "auto_labeled_high_confidence",
                        "auto_label": "power_instability",
                        "confidence": 0.85,
                        "engine": "rule",
                        "evidence": ["bat_sag_ratio=0.2"],
                        "human_verified": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "batch"

    result = promote(str(provisional), str(output_dir))

    promoted_name = f"{sha256[:10]}__flight.bin"
    copied_log = output_dir / "benchmark_ready" / "dataset" / promoted_name
    ground_truth_path = output_dir / "benchmark_ready" / "ground_truth.json"
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    manifest_path = output_dir / "manifests" / "clean_import_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result["promoted"] == 1
    assert copied_log.read_bytes() == source.read_bytes()
    assert ground_truth["logs"][0]["filename"] == promoted_name
    assert ground_truth["logs"][0]["sha256"] == sha256
    assert ground_truth["logs"][0]["human_verified"] is True
    assert manifest[0]["category"] == "verified_labeled"
    assert manifest[0]["file_name"] == promoted_name
    assert manifest[0]["mapped_label"] == "power_instability"
