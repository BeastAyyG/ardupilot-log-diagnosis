from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_dgx_first_pair_launcher_is_digest_pinned_and_pair_atomic() -> None:
    script = (ROOT / "ops" / "dgx" / "run_first_pair.sh").read_text(
        encoding="utf-8"
    )
    assert "sha256:6e52d13408155c05f362510348a47e6a9774152cca36eae51acb6b4496b4ba8d" in script
    assert "--privileged --network host" in script
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
