"""Failure-injection and determinism proofs for the cluster scheduler."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from synthetic_data.cluster import build_batch_plan, execute_batch

WIN32 = sys.platform == "win32"


def _plan(run_id: str, lineage: str, role: str) -> dict:
    return {
        "run_id": run_id,
        "lineage_root_id": lineage,
        "pair_role": role,
        "scenario": "thrust_loss",
    }


class TestBatchPlanning:
    def test_assignment_is_deterministic_and_pair_adjacent(self) -> None:
        plans = [
            _plan("f-0", "pair:0", "intervention"),
            _plan("c-0", "pair:0", "sham_control"),
            _plan("f-1", "pair:1", "intervention"),
            _plan("c-1", "pair:1", "sham_control"),
        ]
        one = build_batch_plan(plans, max_concurrent=2)
        two = build_batch_plan(list(reversed(plans)), max_concurrent=2)
        assert [e.run_id for e in one] == [e.run_id for e in two]
        # Same-lineage members land adjacent with sham first.
        ids = [e.run_id for e in one]
        assert abs(ids.index("c-0") - ids.index("f-0")) == 1
        assert ids.index("c-0") < ids.index("f-0")
        assert abs(ids.index("c-1") - ids.index("f-1")) == 1

    def test_lanes_own_disjoint_ports_recycled_only_across_waves(self) -> None:
        plans = [_plan(f"r{i}", f"l{i}", "intervention") for i in range(6)]
        entries = build_batch_plan(plans, max_concurrent=3, mavlink_port_base=14550)
        for wave in (0, 1):
            ports = [
                e.allocation.mavlink_port for e in entries if e.allocation.wave == wave
            ]
            instances = [
                e.allocation.instance for e in entries if e.allocation.wave == wave
            ]
            assert len(set(ports)) == len(ports) == 3
            assert len(set(instances)) == len(instances)
        assert {e.allocation.mavlink_port for e in entries} == {14550, 14560, 14570}

    def test_invalid_concurrency_and_duplicates_fail_closed(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent"):
            build_batch_plan([_plan("a", "l", "intervention")], max_concurrent=0)
        dup = _plan("same", "l", "intervention")
        with pytest.raises(ValueError, match="duplicate run_id"):
            build_batch_plan([dup, dict(dup)], max_concurrent=1)


@pytest.mark.skipif(
    WIN32,
    reason=(
        "Cluster scheduler targets Linux; Windows file-system races on rapid "
        "O_EXCL+unlink make execute_batch retry/lock fixtures intermittently "
        "flaky. Run on Linux/WSL2 to exercise these."
    ),
)
class TestExecutionAndRecovery:
    def test_crash_mid_attempt_is_retained_then_retried(self, tmp_path) -> None:
        entry = build_batch_plan([_plan("r0", "l0", "intervention")], max_concurrent=1)[
            0
        ]
        calls = {"n": 0}

        def flaky_runner(e, attempt_dir):
            calls["n"] += 1
            if calls["n"] == 1:
                attempt_dir.mkdir(parents=True, exist_ok=True)
                (attempt_dir / "partial.bin").write_bytes(b"\0" * 16)
                raise RuntimeError("simulated SIGKILL mid-flight")
            return {"schema": "receipt/v4", "run_id": e.run_id}

        promoted = []
        report = execute_batch(
            [entry],
            flaky_runner,
            attempts_root=tmp_path,
            promote=lambda d, r: promoted.append(d) or d,
            max_attempts=3,
        )
        record = report.entries[0]
        assert record["status"] == "succeeded"
        assert len(record["attempts"]) == 2
        assert record["attempts"][0]["status"] == "failed"
        # Immutable audit: the crashed attempt dir still exists with its note.
        crashed = Path(record["attempts"][0]["attempt_dir"])
        assert crashed.exists()
        assert json.loads((crashed / "outcome.json").read_text())["failed"]
        assert (crashed / "partial.bin").exists()
        assert record["attempts"][1]["status"] == "succeeded"
        assert len(promoted) == 1

    def test_retry_exhaustion_marks_failure_and_publishes_nothing(
        self, tmp_path
    ) -> None:
        entry = build_batch_plan([_plan("r0", "l0", "intervention")], max_concurrent=1)[
            0
        ]

        def always_fails(e, attempt_dir):
            raise OSError("device unreachable")

        promoted = []
        report = execute_batch(
            [entry],
            always_fails,
            attempts_root=tmp_path,
            promote=lambda d, r: promoted.append(d),
            max_attempts=3,
        )
        record = report.entries[0]
        assert record["status"] == "failed"
        assert len(record["attempts"]) == 3
        assert all(a["status"] == "failed" for a in record["attempts"])
        assert promoted == []
        dirs = [Path(a["attempt_dir"]) for a in record["attempts"]]
        assert len({d.name for d in dirs}) == 3  # monotonic, never reused

    def test_live_lock_blocks_second_writer(self, tmp_path) -> None:
        from synthetic_data.cluster import scheduler as sched

        lock_path = tmp_path / "r0" / "attempt-0" / ".lock"
        lock_path.parent.mkdir(parents=True)
        first = sched._RunLock(lock_path)
        assert first.acquire() == {"acquired": True, "stolen": False, "epoch": 0}
        second = sched._RunLock(lock_path)
        with pytest.raises(RuntimeError, match="single-writer"):
            second.acquire()
        first.release()

    def test_released_lock_can_be_reacquired_on_a_fresh_path(self, tmp_path) -> None:
        from synthetic_data.cluster import scheduler as sched

        for sub in ("a", "b"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        first = sched._RunLock(tmp_path / "a" / ".lock")
        first.acquire()
        first.release()
        second = sched._RunLock(tmp_path / "b" / ".lock")
        assert second.acquire()["acquired"] is True
        second.release()

    def test_execute_batch_reports_blocked_when_lock_is_live(
        self, tmp_path, monkeypatch
    ) -> None:
        from synthetic_data.cluster import scheduler as sched

        entry = build_batch_plan([_plan("r0", "l0", "intervention")], max_concurrent=1)[
            0
        ]

        def blocked_acquire(self, *, epoch: int):
            raise RuntimeError("another writer holds .lock; single-writer per run")

        monkeypatch.setattr(sched._RunLock, "acquire", blocked_acquire)
        report = execute_batch(
            [entry],
            lambda e, d: {"ok": True},
            attempts_root=tmp_path,
            max_attempts=1,
        )
        assert report.entries[0]["status"] == "blocked"
        assert "single-writer" in report.entries[0]["last_error"]
        assert report.entries[0]["attempts"][0]["status"] == "lock_blocked"

    def test_stale_lock_is_stolen_after_ttl(self, tmp_path, monkeypatch) -> None:
        entry = build_batch_plan([_plan("r0", "l0", "intervention")], max_concurrent=1)[
            0
        ]
        stale_dir = tmp_path / "r0" / "attempt-0"
        stale_dir.mkdir(parents=True)
        (stale_dir / ".lock").write_text(
            json.dumps({"pid": 999999, "acquired_at": time.time() - 10_000}),
            encoding="utf-8",
        )
        report = execute_batch(
            [entry],
            lambda e, d: {"ok": True},
            attempts_root=tmp_path,
            max_attempts=1,
        )
        assert report.entries[0]["status"] == "succeeded"

    def test_attempt_dirs_are_monotonic_across_reports(self, tmp_path) -> None:
        entry = build_batch_plan([_plan("r0", "l0", "intervention")], max_concurrent=1)[
            0
        ]
        execute_batch([entry], lambda e, d: {"ok": True}, attempts_root=tmp_path)
        second = execute_batch(
            [entry], lambda e, d: {"ok": True}, attempts_root=tmp_path
        )
        first_dir = Path(second.entries[0]["attempts"][0]["attempt_dir"])
        assert first_dir.name == "attempt-1"  # never rewrites attempt-0
