"""Cluster-readiness audit items: pair atomicity, recovery, assignment,
receipts, power planning, lock consistency, and frame-default merging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic_data.cluster import (
    assign_nodes,
    build_batch_plan,
    execute_batch,
    recover_pending,
    write_batch_receipt,
)
from synthetic_data.design import confirmation_cohort_size
from synthetic_data.execution_integrity import SUPPORTED_PYMAVLINK_VERSION

CONTAINERS = Path(__file__).parents[1] / "synthetic_data" / "cluster" / "containers"


def _pair(lineage: str, index: int) -> list[dict]:
    return [
        {
            "run_id": f"c-{index}",
            "lineage_root_id": lineage,
            "pair_role": "sham_control",
            "scenario": "thrust_loss",
        },
        {
            "run_id": f"f-{index}",
            "lineage_root_id": lineage,
            "pair_role": "intervention",
            "scenario": "thrust_loss",
        },
    ]


class TestPairAtomicity:
    def test_incomplete_pair_is_never_promoted(self, tmp_path) -> None:
        plans = _pair("pair:0", 0) + _pair("pair:1", 1)
        entries = build_batch_plan(plans, max_concurrent=2)

        def runner(entry, attempt_dir):
            if entry.run_id == "f-1":  # one arm of pair:1 dies permanently
                raise RuntimeError("simulated flight failure")
            return {"ok": True}

        promoted = []
        report = execute_batch(
            entries,
            runner,
            attempts_root=tmp_path,
            promote=lambda d, r: promoted.append(d) or d,
            pair_atomic=True,
        )
        by_run = {e["run_id"]: e for e in report.entries}
        assert by_run["c-0"]["status"] == "succeeded"
        assert by_run["c-0"]["attempts"][-1]["promoted_to"] is not None
        assert by_run["f-0"]["attempts"][-1]["promoted_to"] is not None
        # The surviving arm of the dead pair is held, not promoted.
        assert by_run["c-1"]["status"] == "succeeded"
        assert by_run["c-1"]["pair_held"] is True
        assert by_run["c-1"]["attempts"][-1]["promoted_to"] is None
        assert len(promoted) == 2
        held_note = json.loads(
            (
                Path(by_run["c-1"]["attempts"][-1]["attempt_dir"]) / "outcome.json"
            ).read_text(encoding="utf-8")
        )
        assert held_note == {"held_pair_atomic": True}
        assert by_run["f-1"]["status"] == "failed"

    def test_complete_pairs_promote_normally(self, tmp_path) -> None:
        plans = _pair("pair:0", 0)
        entries = build_batch_plan(plans, max_concurrent=2)
        promoted = []
        report = execute_batch(
            entries,
            lambda e, d: {"ok": True},
            attempts_root=tmp_path,
            promote=lambda d, r: promoted.append(d) or d,
            pair_atomic=True,
        )
        assert all(e["attempts"][-1]["promoted_to"] for e in report.entries)
        assert len(promoted) == 2


class TestCrashRecovery:
    def test_recover_pending_lists_receipt_less_attempts(self, tmp_path) -> None:
        # Simulate a killed batch: attempts exist but never wrote a receipt.
        killed = tmp_path / "r-dead" / "attempt-0"
        killed.mkdir(parents=True)
        (killed / "partial.bin").write_bytes(b"\0" * 8)
        done = tmp_path / "r-done" / "attempt-0"
        done.mkdir(parents=True)
        (done / "receipt.json").write_text("{}", encoding="utf-8")

        pending = recover_pending(tmp_path)
        assert pending == [{"run_id": "r-dead", "attempt_dir": str(killed)}]
        assert recover_pending(tmp_path / "missing") == []

    def test_resume_continues_monotonic_numbering_after_crash(self, tmp_path) -> None:
        crashed = tmp_path / "r0" / "attempt-0"
        crashed.mkdir(parents=True)
        entries = build_batch_plan(
            [
                {
                    "run_id": "r0",
                    "lineage_root_id": "l0",
                    "pair_role": "intervention",
                    "scenario": "thrust_loss",
                }
            ],
            max_concurrent=1,
        )
        report = execute_batch(
            entries, lambda e, d: {"ok": True}, attempts_root=tmp_path, max_attempts=1
        )
        resumed = Path(report.entries[0]["attempts"][0]["attempt_dir"])
        assert resumed.name == "attempt-1"
        assert crashed.exists()  # crash evidence retained


class TestNodeAssignment:
    def test_deterministic_across_restarts_and_ordering(self) -> None:
        plans = [*_pair("p0", 0), *_pair("p1", 1)]
        one = build_batch_plan(plans, max_concurrent=2)
        two = build_batch_plan(list(reversed(plans)), max_concurrent=2)
        nodes = ["dgx-a", "dgx-b", "dgx-c"]
        assert assign_nodes(one, nodes) == assign_nodes(two, nodes)

    def test_salt_changes_placement_but_stays_balanced(self) -> None:
        plans = []
        for i in range(60):
            plans.append(
                {
                    "run_id": f"run-{i:03d}",
                    "lineage_root_id": f"l{i}",
                    "pair_role": "intervention",
                    "scenario": "healthy",
                }
            )
        entries = build_batch_plan(plans, max_concurrent=4)
        first = assign_nodes(entries, ["n1", "n2"], salt="rack7")
        other = assign_nodes(entries, ["n1", "n2"], salt="rack8")
        counts = sorted(sum(1 for v in first.values() if v == n) for n in ("n1", "n2"))
        assert 20 <= counts[0] <= 40  # balanced, not adversarially skewed
        assert first != other  # salt isolates fleets
        with pytest.raises(ValueError):
            assign_nodes(entries, [])


class TestBatchReceipts:
    def test_receipt_binds_report_and_per_run_hashes(self, tmp_path) -> None:
        plans = _pair("p0", 0)
        entries = build_batch_plan(plans, max_concurrent=2)
        report = execute_batch(
            entries, lambda e, d: {"ok": True}, attempts_root=tmp_path
        )
        receipt_sha = write_batch_receipt(report, tmp_path / "batch.json")
        payload = json.loads((tmp_path / "batch.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "logdiagnosis.cluster-batch-receipt/v1"
        assert payload["runs_succeeded"] == 2
        assert payload["runs_failed"] == 0
        assert all(e["final_receipt_sha256"] for e in payload["entries"])
        assert len(receipt_sha) == 64


class TestPowerPlanning:
    def test_normal_approximation_planning_values(self) -> None:
        # z=1.96, p=0.5: n = ceil(3.8416 * 0.25 / h^2)
        assert confirmation_cohort_size(half_width=0.1) == 97
        assert confirmation_cohort_size(half_width=0.05) == 385
        assert confirmation_cohort_size(half_width=0.05, confidence=0.99) > 385
        with pytest.raises(ValueError):
            confirmation_cohort_size(half_width=0.0)


class TestContainerLockConsistency:
    def test_lock_pins_the_enforced_pymavlink_version(self) -> None:
        lock = (CONTAINERS / "constraints.lock").read_text(encoding="utf-8")
        assert f"pymavlink=={SUPPORTED_PYMAVLINK_VERSION}" in lock

    def test_containerfile_uses_lock_and_emits_attestation(self) -> None:
        dockerfile = (CONTAINERS / "Dockerfile.ardupilot-sitl").read_text(
            encoding="utf-8"
        )
        assert "constraints.lock" in dockerfile
        assert "/attestation.json" in dockerfile
        assert "REPLACE_WITH_VERIFIED_DIGEST" in dockerfile  # explicit pin gate
