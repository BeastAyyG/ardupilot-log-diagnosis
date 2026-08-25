import json
import sqlite3
import subprocess
import urllib.error
from pathlib import Path

import pytest

from ops.jarvis import cleanup
from ops.jarvis import run_dstack_canary as canary
from ops.jarvis.cleanup import wait_fleet_gone


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


def test_wait_fleet_fails_when_all_instances_are_terminal(monkeypatch) -> None:
    monkeypatch.setattr(
        canary,
        "_json_command",
        lambda *args, **kwargs: {
            "status": "active",
            "instances": [{"status": "terminated"}],
        },
    )
    with pytest.raises(canary.CanaryError, match="no viable instance"):
        canary._wait_fleet(
            ["dstack"],
            canary.FLEET_NAME,
            env={},
            cwd=Path("."),
            timeout=1,
            secret="",
        )


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


def test_wait_fleet_gone_waits_for_async_instance_deletion(monkeypatch) -> None:
    responses = iter(
        [
            subprocess.CompletedProcess(
                ["dstack"],
                0,
                '{"status":"active","instances":[{"status":"destroying"}]}',
                "",
            ),
            subprocess.CompletedProcess(["dstack"], 1, "", "fleet not found"),
        ]
    )
    monkeypatch.setattr(canary, "_run", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(canary.time, "sleep", lambda _: None)
    wait_fleet_gone(
        canary._run,
        ["dstack"],
        canary.FLEET_NAME,
        project=canary.PROJECT_NAME,
        env={},
        cwd=Path("."),
        timeout=1,
        secret="",
    )


def test_wait_active_instances_gone_requires_empty_inventory(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"[]"

    monkeypatch.setattr(
        cleanup.urllib.request, "urlopen", lambda *args, **kwargs: Response()
    )
    cleanup.wait_active_instances_gone(
        "http://127.0.0.1:1", "token", project="main", timeout=1
    )


def test_capture_jarvis_instances_reads_dstack_provisioning_data(tmp_path: Path) -> None:
    database = tmp_path / "sqlite.db"
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE fleets (id TEXT PRIMARY KEY, name TEXT, project_id TEXT);
            CREATE TABLE instances (
                job_provisioning_data TEXT, region TEXT, fleet_id TEXT
            );
            """
        )
        db.execute("INSERT INTO projects VALUES ('p', 'main')")
        db.execute("INSERT INTO fleets VALUES ('f', 'fleet', 'p')")
        db.execute(
            "INSERT INTO instances VALUES (?, ?, ?)",
            (json.dumps({"instance_id": "machine-1", "region": "india-noida-01"}), "", "f"),
        )
        db.commit()
    assert cleanup.capture_jarvis_instances(database, project="main", fleet="fleet") == [
        {"machine_id": "machine-1", "region": "india-noida-01"}
    ]


def test_cleanup_jarvis_instances_destroys_and_waits(monkeypatch) -> None:
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    calls: list[tuple[str, str]] = []

    def request(request, **_kwargs):
        calls.append((request.method, request.full_url))
        if request.method == "GET" and len([item for item in calls if item[0] == "GET"]) > 1:
            raise urllib.error.HTTPError(request.full_url, 404, "gone", {}, None)
        return Response({"instance": {"template": "vm", "gpu_type": "CPU"}})

    monkeypatch.setattr(cleanup.urllib.request, "urlopen", request)
    monkeypatch.setattr(cleanup.time, "sleep", lambda _: None)
    cleanup.cleanup_jarvis_instances(
        "secret",
        [{"machine_id": "machine-1", "region": "india-noida-01"}],
        timeout=1,
    )
    assert calls[0][0] == "GET"
    assert calls[1][1].startswith("https://backendn.jarvislabs.net/templates/vm/cpu/destroy?")


def test_run_canary_rejects_missing_api_key(tmp_path: Path) -> None:
    with pytest.raises(canary.CanaryError, match="JL_API_KEY is empty"):
        canary.run_canary(api_key="", repo_root=tmp_path, results_dir=tmp_path / "out")
