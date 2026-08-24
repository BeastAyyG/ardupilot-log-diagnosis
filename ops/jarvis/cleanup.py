"""Provider cleanup helpers for the Jarvis canary launcher."""

from __future__ import annotations

import json
import time
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
