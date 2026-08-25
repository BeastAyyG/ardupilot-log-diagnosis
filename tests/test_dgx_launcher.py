from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_dgx_first_pair_launcher_is_digest_pinned_and_pair_atomic() -> None:
    script = (ROOT / "ops" / "dgx" / "run_first_pair.sh").read_text(
        encoding="utf-8"
    )
    assert "sha256:dfa0468382e68806e40e9fb76ee6795cf430f96725e658e62df14f8cbb601480" in script
    assert "--privileged --network host" in script
    assert "--user 0:0" in script
    assert 'chmod 0777 "$OUTPUT_DIR"' in script
    assert 'chown -R "$HOST_UID:$HOST_GID" /output' in script
    assert "python -m synthetic_data pair" in script
    assert "--confirm-sitl" in script
    assert '[[ "$commit_count" -eq 1 ]]' in script
    assert '[[ "$receipt_count" -ge 2 ]]' in script
    assert '[[ "$bin_count" -eq 2 ]]' in script


def test_dgx_launcher_does_not_accept_a_mutable_image_tag() -> None:
    script = (ROOT / "ops" / "dgx" / "run_first_pair.sh").read_text(
        encoding="utf-8"
    )
    assert "@sha256:[0-9a-f]{64}" in script
    assert "docker pull \"$IMAGE\"" in script
