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
    assert "@sha256:fcea4016c58485695bc12afc119e3b6dc4e44c525d813ceab7792ee69ce2fb9b" in workflow["env"]["SITL_IMAGE"]
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["workflow_dispatch"]["inputs"]["seed"]["default"] == "20260840"
    assert any(
        step.get("run") == "bash ops/dgx/run_first_pair.sh"
        for step in job["steps"]
    )
    assert any(
        step.get("uses") == "actions/upload-artifact@v4"
        for step in job["steps"]
    )
