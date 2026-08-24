"""Provider cleanup helpers for the Jarvis canary launcher."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

POLL_SECONDS = 5.0


def wait_fleet_gone(
    run: Callable[..., Any],
    dstack: Sequence[str],
    fleet: str,
    *,
    project: str,
    env: Mapping[str, str],
    cwd: Path,
    timeout: float,
    secret: str,
) -> None:
    """Wait for asynchronous fleet deletion to remove every instance."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = run(
            [*dstack, "fleet", "--project", project, "get", fleet, "--json"],
            env=env,
            cwd=cwd,
            allow_failure=True,
            secret=secret,
        )
        if result.returncode:
            detail = (result.stdout + "\n" + result.stderr).lower()
            if any(
                marker in detail for marker in ("not found", "does not exist", "404")
            ):
                return
        else:
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                instances = payload.get("instances")
                if isinstance(instances, list) and not instances:
                    return
                if payload.get("status") in {"terminated", "failed"} and not instances:
                    return
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"fleet {fleet} deletion did not finish before the timeout")


def wait_active_instances_gone(
    server_url: str,
    token: str,
    *,
    project: str,
    timeout: float,
) -> None:
    """Verify dstack's active-instance inventory is empty before shutdown."""

    body = json.dumps(
        {"project_names": [project], "only_active": True, "limit": 1000}
    ).encode()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        request = urllib.request.Request(
            f"{server_url}/api/instances/list",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode())
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(POLL_SECONDS)
            continue
        instances = payload.get("instances") if isinstance(payload, dict) else payload
        if isinstance(instances, list) and not instances:
            return
        time.sleep(POLL_SECONDS)
    raise RuntimeError("dstack active-instance inventory did not empty before timeout")
