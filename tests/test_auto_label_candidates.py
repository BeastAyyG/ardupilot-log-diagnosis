import json

from training.auto_label_candidates import _sha256, auto_label_directory


def test_candidate_scan_skips_renamed_labeled_content(tmp_path, capsys):
    target_dir = tmp_path / "raw"
    target_dir.mkdir()
    candidate = target_dir / "renamed.bin"
    candidate.write_bytes(b"same-flight-content")
    sha256 = _sha256(str(candidate))

    ground_truth = tmp_path / "ground_truth.json"
    ground_truth.write_text(
        json.dumps(
            {
                "logs": [
                    {
                        "filename": f"{sha256[:10]}__already_labeled.bin",
                        "labels": ["rc_failsafe"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "provisional.json"

    auto_label_directory(
        target_dir=str(target_dir),
        ground_truth_path=str(ground_truth),
        output_provisional_path=str(output),
    )

    assert not output.exists()
    assert "duplicate of labeled/seen content" in capsys.readouterr().out
