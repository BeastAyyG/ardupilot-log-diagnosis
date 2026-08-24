"""Fixed container worker entry point: exactly one attempt, one task.

Runs inside an isolated worker container (``--network none``, no GPU). The
coordinator drops a task file; this module validates it fail-closed, executes
the owned run through the existing executor, and stages artifacts into the
attempt directory. Exit codes: 0 success, 3 terminal scientific failure,
1 anything else.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TASK_SCHEMA = "logdiagnosis.cluster-worker-task/v1"

REQUIRED_TASK_FIELDS = (
    "schema",
    "run_id",
    "experiment_dir",
    "binary_path",
    "endpoint",
    "attempt_dir",
    "fencing_epoch",
)


def load_task(path: str | Path) -> dict[str, Any]:
    try:
        task = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read worker task: {exc}") from exc
    if not isinstance(task, dict):
        raise ValueError("worker task root must be an object")
    missing = [f for f in REQUIRED_TASK_FIELDS if f not in task]
    if missing:
        raise ValueError(f"worker task lacks required fields: {missing}")
    if task["schema"] != TASK_SCHEMA:
        raise ValueError(f"unsupported worker task schema: {task['schema']!r}")
    if not str(task["run_id"]).strip():
        raise ValueError("worker task run_id must be non-empty")
    epoch = task["fencing_epoch"]
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise ValueError("worker task fencing_epoch must be a positive integer")
    return task


def run_task(task: dict[str, Any]) -> int:
    """Execute one owned attempt; returns the process exit code."""

    from synthetic_data.executor import execute_run

    attempt_dir = Path(task["attempt_dir"])
    attempt_dir.mkdir(parents=True, exist_ok=True)
    receipt = execute_run(
        task["experiment_dir"],
        task["run_id"],
        binary_path=task.get("binary_path"),
        confirm_sitl=True,
        endpoint=task["endpoint"],
    )
    (attempt_dir / "receipt.json").write_text(
        json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-json", required=True)
    args = parser.parse_args(argv)
    try:
        task = load_task(args.task_json)
        return run_task(task)
    except TerminalRunForwarded as exc:
        print(f"terminal failure: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - worker boundary
        print(f"worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


class TerminalRunForwarded(RuntimeError):
    """Raised when the underlying execution reports a scientific failure."""
