"""Run the bounded JarvisLabs canary with automatic cleanup."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ops.jarvis.cleanup import (
    capture_jarvis_instances,
    cleanup_jarvis_instances,
    stop_process_tree,
    wait_active_instances_gone,
    wait_fleet_gone,
)

FLEET_NAME = "logdiagnosis-sitl-canary-fleet"
PROJECT_NAME = "main"
DEFAULT_TIMEOUT_SECONDS = 15 * 60
TEARDOWN_TIMEOUT_SECONDS = 3 * 60
POLL_SECONDS = 5.0

class CanaryError(RuntimeError):
    """Raised when the bounded canary cannot produce a successful run."""
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
def _dstack_command(explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    found = shutil.which("dstack")
    if found:
        return [found]
    raise CanaryError(
        "dstack is not installed; install dstack[all] once, then rerun this launcher"
    )
def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(yaml.safe_dump(dict(payload), sort_keys=False), encoding="utf-8")
def _run(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    timeout: float = 120.0,
    allow_failure: bool = False,
    secret: str = "",
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode and not allow_failure:
        detail = (result.stdout + "\n" + result.stderr).strip()
        if secret:
            detail = detail.replace(secret, "<redacted>")
        raise CanaryError(f"command failed ({result.returncode}): {detail[-2000:]}")
    return result


def _wait_server(url: str, process: subprocess.Popen[Any], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CanaryError(f"dstack server exited with code {process.returncode}")
        try:
            with urllib.request.urlopen(f"{url}/healthcheck", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)
    raise CanaryError("dstack server did not become healthy before the timeout")
def _json_command(
    dstack: Sequence[str],
    args: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    secret: str,
) -> dict[str, Any]:
    result = _run([*dstack, *args], env=env, cwd=cwd, secret=secret)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CanaryError(
            f"dstack returned invalid JSON: {result.stdout[-1000:]}"
        ) from exc
    if not isinstance(payload, dict):
        raise CanaryError("dstack JSON response must be an object")
    return payload
def _wait_fleet(
    dstack: Sequence[str],
    fleet: str,
    *,
    env: Mapping[str, str],
    cwd: Path,
    timeout: float,
    secret: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = _json_command(
            dstack,
            ["fleet", "--project", PROJECT_NAME, "get", fleet, "--json"],
            env=env,
            cwd=cwd,
            secret=secret,
        )
        status = str(payload.get("status", ""))
        instances = payload.get("instances")
        if status in {"failed", "terminated"}:
            raise CanaryError(f"fleet {fleet} entered terminal state: {status}")
        ready = (
            isinstance(instances, list)
            and bool(instances)
            and all(
                isinstance(item, dict)
                and str(item.get("status", "")) in {"idle", "busy"}
                for item in instances
            )
        )
        if ready:
            return payload
        time.sleep(POLL_SECONDS)
    raise CanaryError(f"fleet {fleet} did not become ready before the timeout")
def _wait_run(
    dstack: Sequence[str],
    run_name: str,
    *,
    env: Mapping[str, str],
    cwd: Path,
    timeout: float,
    secret: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = _json_command(
            dstack,
            ["ps", "--project", PROJECT_NAME, "--json"],
            env=env,
            cwd=cwd,
            secret=secret,
        )
        runs = payload.get("runs")
        run = None
        if isinstance(runs, list):
            run = next(
                (
                    item
                    for item in runs
                    if isinstance(item, dict)
                    and (
                        item.get("run_spec", {}).get("run_name") == run_name
                        or item.get("name") == run_name
                    )
                ),
                None,
            )
        if run is None:
            time.sleep(POLL_SECONDS)
            continue
        status = str(run.get("status", ""))
        if status == "done":
            return run
        if status in {"failed", "terminated"}:
            raise CanaryError(
                f"canary run {run_name} ended as {status}: {run.get('status_message', '')}"
            )
        time.sleep(POLL_SECONDS)
    raise CanaryError(f"canary run {run_name} did not finish before the timeout")
def _fleet_config(region: str | None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "type": "fleet",
        "name": FLEET_NAME,
        "nodes": 1,
        "backends": ["jarvislabs"],
        "resources": {"cpu": "x86:4", "memory": "16GB", "disk": "100GB"},
        "spot_policy": "on-demand",
        "max_price": 8.50,
        "idle_duration": "2m",
    }
    if region:
        config["regions"] = [region]
    return config
def _task_config(source: Path, run_name: str) -> dict[str, Any]:
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("type") != "task":
        raise CanaryError("canary dstack configuration is not a task")
    payload["name"] = run_name
    payload["fleets"] = [FLEET_NAME]
    return payload
def _config_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
def _write_failure_receipt(
    path: Path,
    *,
    error: str,
    run_name: str,
    task_config: Mapping[str, Any],
    fleet_config: Mapping[str, Any],
) -> None:
    payload = {
        "schema": "logdiagnosis.jarvislabs-dstack-canary/v1",
        "status": "failed",
        "error": error,
        "run_name": run_name,
        "fleet_name": FLEET_NAME,
        "image": task_config.get("image"),
        "fleet_config_sha256": _config_digest(fleet_config) if fleet_config else None,
        "task_config_sha256": _config_digest(task_config) if task_config else None,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
def run_canary(
    *,
    api_key: str,
    repo_root: Path,
    results_dir: Path,
    dstack_executable: str | None = None,
    region: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run one bounded canary and return a non-secret receipt summary."""
    if not api_key.strip():
        raise CanaryError("JL_API_KEY is empty")
    canary_source = repo_root / "ops" / "jarvis" / "sitl-canary.dstack.yml"
    if not canary_source.is_file():
        raise CanaryError(f"missing canary configuration: {canary_source}")
    dstack = _dstack_command(dstack_executable)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_name = f"logdiagnosis-sitl-canary-{int(time.time())}"
    server_process: subprocess.Popen[Any] | None = None
    task_started = False
    fleet_created = False
    provider_instances: list[dict[str, str]] = []
    fleet_config: dict[str, Any] = {}
    task_config: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(
        prefix="logdiagnosis-dstack-", ignore_cleanup_errors=True
    ) as temp_name:
        temp = Path(temp_name)
        home = temp / "home"
        server_dir = temp / "server"
        workspace = temp / "configs"
        (home / ".dstack").mkdir(parents=True)
        server_dir.mkdir()
        workspace.mkdir()
        port = _free_port()
        server_url = f"http://127.0.0.1:{port}"
        admin_token = secrets.token_urlsafe(24)
        _write_yaml(
            server_dir / "config.yml",
            {
                "projects": [
                    {
                        "name": PROJECT_NAME,
                        "backends": [
                            {
                                "type": "jarvislabs",
                                "creds": {"type": "api_key", "api_key": api_key},
                            }
                        ],
                    }
                ]
            },
        )
        _write_yaml(
            home / ".dstack" / "config.yml",
            {
                "projects": [
                    {
                        "name": PROJECT_NAME,
                        "url": server_url,
                        "token": admin_token,
                        "default": True,
                    }
                ]
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "DSTACK_SERVER_DIR": str(server_dir),
                "DSTACK_SERVER_URL": server_url,
                "HOME": str(home),
                "USERPROFILE": str(home),
                "PYTHONUTF8": "1",
            }
        )
        server_process = subprocess.Popen(
            [
                *dstack,
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--yes",
                "--token",
                admin_token,
            ],
            cwd=str(repo_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_server(server_url, server_process, min(timeout_seconds, 60.0))
            fleet_path = workspace / "fleet.yml"
            task_path = workspace / "task.yml"
            fleet_config = _fleet_config(region)
            _write_yaml(fleet_path, fleet_config)
            task_config = _task_config(canary_source, run_name)
            _write_yaml(task_path, task_config)
            _run(
                [
                    *dstack,
                    "apply",
                    "--project",
                    PROJECT_NAME,
                    "-f",
                    str(fleet_path),
                    "-y",
                    "-d",
                ],
                env=env,
                cwd=workspace,
                secret=api_key,
            )
            fleet_created = True
            fleet = _wait_fleet(
                dstack,
                FLEET_NAME,
                env=env,
                cwd=workspace,
                timeout=timeout_seconds,
                secret=api_key,
            )
            provider_instances = capture_jarvis_instances(
                server_dir / "data" / "sqlite.db", project=PROJECT_NAME, fleet=FLEET_NAME
            )
            _run(
                [
                    *dstack,
                    "apply",
                    "--project",
                    PROJECT_NAME,
                    "-f",
                    str(task_path),
                    "-y",
                    "-d",
                ],
                env=env,
                cwd=workspace,
                secret=api_key,
            )
            task_started = True
            run = _wait_run(
                dstack,
                run_name,
                env=env,
                cwd=workspace,
                timeout=timeout_seconds,
                secret=api_key,
            )
            logs = _run(
                [*dstack, "logs", "--project", PROJECT_NAME, "--diagnose", run_name],
                env=env,
                cwd=workspace,
                secret=api_key,
            ).stdout
            log_path = results_dir / f"{run_name}.log"
            log_path.write_text(logs, encoding="utf-8")
            summary = {
                "schema": "logdiagnosis.jarvislabs-dstack-canary/v1",
                "run_name": run_name,
                "fleet_name": FLEET_NAME,
                "image": task_config.get("image"),
                "fleet_config_sha256": _config_digest(fleet_config),
                "task_config_sha256": _config_digest(task_config),
                "fleet_status": fleet.get("status"),
                "run_status": run.get("status"),
                "log_path": str(log_path),
            }
            (results_dir / f"{run_name}.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return summary
        except CanaryError as exc:
            _write_failure_receipt(
                results_dir / f"{run_name}.json",
                error=str(exc),
                run_name=run_name,
                task_config=task_config,
                fleet_config=fleet_config,
            )
            raise
        finally:
            if task_started:
                _run(
                    [
                        *dstack,
                        "stop",
                        "--project",
                        PROJECT_NAME,
                        "--abort",
                        "-y",
                        run_name,
                    ],
                    env=env,
                    cwd=workspace,
                    allow_failure=True,
                    secret=api_key,
                )
            if fleet_created:
                if not provider_instances:
                    provider_instances = capture_jarvis_instances(
                        server_dir / "data" / "sqlite.db", project=PROJECT_NAME, fleet=FLEET_NAME
                    )
                _run(
                    [
                        *dstack,
                        "fleet",
                        "--project",
                        PROJECT_NAME,
                        "delete",
                        FLEET_NAME,
                        "-y",
                    ],
                    env=env,
                    cwd=workspace,
                    allow_failure=True,
                    secret=api_key,
                )
                try:
                    wait_fleet_gone(
                        _run,
                        dstack,
                        FLEET_NAME,
                        project=PROJECT_NAME,
                        env=env,
                        cwd=workspace,
                        timeout=min(TEARDOWN_TIMEOUT_SECONDS, timeout_seconds),
                        secret=api_key,
                    )
                    cleanup_jarvis_instances(
                        api_key,
                        provider_instances,
                        timeout=min(TEARDOWN_TIMEOUT_SECONDS, timeout_seconds),
                    )
                    wait_active_instances_gone(
                        server_url,
                        admin_token,
                        project=PROJECT_NAME,
                        timeout=min(TEARDOWN_TIMEOUT_SECONDS, timeout_seconds),
                    )
                except (CanaryError, RuntimeError) as exc:
                    _write_failure_receipt(
                        results_dir / f"{run_name}.json",
                        error=str(exc),
                        run_name=run_name,
                        task_config=task_config,
                        fleet_config=fleet_config,
                    )
                    raise
            if server_process is not None:
                stop_process_tree(server_process)
            shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    from ops.jarvis.canary_cli import main
    raise SystemExit(main())
