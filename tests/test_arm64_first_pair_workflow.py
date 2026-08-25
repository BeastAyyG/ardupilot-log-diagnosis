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
    assert "@sha256:8162531305811a56d3d85f15616ec4619ef520ca9a6dc8fd35bffcce52081628" in workflow["env"]["SITL_IMAGE"]
    assert any(
        step.get("run") == "bash ops/dgx/run_first_pair.sh"
        for step in job["steps"]
    )
    assert any(
        step.get("uses") == "actions/upload-artifact@v4"
        for step in job["steps"]
    )
