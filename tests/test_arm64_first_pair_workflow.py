from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_arm64_first_pair_workflow_is_bounded_and_digest_pinned() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "run-arm64-first-pair.yml").read_text(
            encoding="utf-8"
        )
    )
    job = workflow["jobs"]["first-pair"]
    assert job["runs-on"] == "ubuntu-24.04-arm"
    assert job["timeout-minutes"] == 45
    assert "@sha256:6685a2fa202e022e68e382b14c7bd9c9b7034ba0e2b58ab22774d507875622ee" in workflow["env"]["SITL_IMAGE"]
    assert any(
        step.get("run") == "bash ops/dgx/run_first_pair.sh"
        for step in job["steps"]
    )
    assert any(
        step.get("uses") == "actions/upload-artifact@v4"
        for step in job["steps"]
    )
