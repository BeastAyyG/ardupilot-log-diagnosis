"""Provider cleanup helpers for the Jarvis canary launcher."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

POLL_SECONDS = 5.0
JARVIS_BASE_URL = {
    "india-01": "https://backendprod.jarvislabs.net",
    "india-chennai-01": "https://backendc.jarvislabs.net",
    "india-noida-01": "https://backendn.jarvislabs.net",
    "europe-01": "https://backendeu.jarvislabs.net",
}


def stop_process_tree(process: subprocess.Popen[Any]) -> None:
    """Stop dstack and descendants so the isolated server directory can be removed."""

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(0.5)


def capture_jarvis_instances(
    database_path: Path, *, project: str, fleet: str
) -> list[dict[str, str]]:
    """Read provider machine IDs from dstack's immutable provisioning records."""

    if not database_path.is_file():
        return []
    query = """
        SELECT i.job_provisioning_data, i.region
        FROM instances AS i
        JOIN fleets AS f ON f.id = i.fleet_id
        JOIN projects AS p ON p.id = f.project_id
        WHERE p.name = ? AND f.name = ?
    """
    try:
        with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True, timeout=5) as db:
            rows = db.execute(query, (project, fleet)).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError("cannot read dstack provisioning records") from exc
    result: list[dict[str, str]] = []
    for raw_data, row_region in rows:
        try:
            data = json.loads(raw_data or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        machine_id = data.get("instance_id")
        region = data.get("region") or row_region
        if machine_id and region:
            result.append({"machine_id": str(machine_id), "region": str(region)})
    return result


def _jarvis_request(
    api_key: str,
    instance: Mapping[str, str],
    method: str,
    path: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    base_url = JARVIS_BASE_URL.get(instance["region"])
    if base_url is None:
        raise RuntimeError(f"unsupported JarvisLabs region: {instance['region']}")
    params = kwargs.pop("params", None)
    body = kwargs.pop("json", None)
    url = f"{base_url}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"JarvisLabs provider request failed ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("JarvisLabs provider request failed") from exc
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("JarvisLabs returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("JarvisLabs returned an unexpected response")
    return payload


def cleanup_jarvis_instances(
    api_key: str,
    instances: Sequence[Mapping[str, str]],
    *,
    timeout: float,
) -> None:
    """Destroy captured provider machines and fail closed until they disappear."""

    for instance in instances:
        response = _jarvis_request(api_key, instance, "GET", f"users/fetch/{instance['machine_id']}")
        if response is None:
            continue
        payload = response
        raw_details = payload.get("instance") if isinstance(payload, dict) else {}
        details = raw_details if isinstance(raw_details, dict) else {}
        template = str(details.get("template") or details.get("framework") or "").lower()
        gpu_type = str(details.get("gpu_type") or "").upper()
        endpoint = "templates/vm/cpu/destroy" if template == "vm" and gpu_type == "CPU" else "templates/vm/destroy"
        _jarvis_request(
            api_key,
            instance,
            "POST",
            endpoint,
            params={"machine_id": instance["machine_id"]},
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = []
        for instance in instances:
            if _jarvis_request(api_key, instance, "GET", f"users/fetch/{instance['machine_id']}") is not None:
                remaining.append(instance)
        if not remaining:
            return
        time.sleep(POLL_SECONDS)
    raise RuntimeError("JarvisLabs provider inventory did not empty before timeout")


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
