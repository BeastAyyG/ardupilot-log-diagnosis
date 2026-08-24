from pathlib import Path

import pytest

from ops.jarvis import run_dstack_canary as canary


def test_fleet_config_is_bounded_and_region_scoped() -> None:
    config = canary._fleet_config("india-chennai-01")
    assert config["name"] == canary.FLEET_NAME
    assert config["nodes"] == 1
    assert config["max_price"] == 8.50
    assert config["regions"] == ["india-chennai-01"]


def test_task_config_forces_the_ready_fleet(tmp_path: Path) -> None:
    source = tmp_path / "task.yml"
    source.write_text(
        "type: task\nname: old\nbackends: [jarvislabs]\n", encoding="utf-8"
    )
    payload = canary._task_config(source, "new-run")
    assert payload["name"] == "new-run"
    assert payload["fleets"] == [canary.FLEET_NAME]


def test_wait_fleet_requires_an_idle_or_busy_instance(monkeypatch) -> None:
    responses = iter(
        [
            {"status": "active", "instances": [{"status": "provisioning"}]},
            {"status": "active", "instances": [{"status": "idle"}]},
        ]
    )
    monkeypatch.setattr(
        canary, "_json_command", lambda *args, **kwargs: next(responses)
    )
    monkeypatch.setattr(canary.time, "sleep", lambda _: None)
    result = canary._wait_fleet(
        ["dstack"],
        canary.FLEET_NAME,
        env={},
        cwd=Path("."),
        timeout=1,
        secret="",
    )
    assert result["instances"][0]["status"] == "idle"


def test_wait_run_matches_run_name_and_accepts_done(monkeypatch) -> None:
    monkeypatch.setattr(
        canary,
        "_json_command",
        lambda *args, **kwargs: {
            "runs": [{"status": "done", "run_spec": {"run_name": "canary"}}]
        },
    )
    result = canary._wait_run(
        ["dstack"],
        "canary",
        env={},
        cwd=Path("."),
        timeout=1,
        secret="",
    )
    assert result["status"] == "done"


def test_run_canary_rejects_missing_api_key(tmp_path: Path) -> None:
    with pytest.raises(canary.CanaryError, match="JL_API_KEY is empty"):
        canary.run_canary(api_key="", repo_root=tmp_path, results_dir=tmp_path / "out")
