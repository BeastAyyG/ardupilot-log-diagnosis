"""Distributed-contract tests: pair co-location, parallel dispatch, terminal
failures, fencing epochs, reconciliation, commit pointers, ledgers, and the
effective ArduPilot defaults merge."""

from __future__ import annotations

import json

import pytest

from synthetic_data.cluster import (
    TerminalRunError,
    assign_nodes,
    build_batch_plan,
    execute_batch,
    fence_stale,
    reconcile,
    write_assignment_ledger,
    write_batch_receipt,
)
from synthetic_data.frame_defaults import (
    apply_plan_overrides,
    merge_effective_defaults,
    parse_parm_file,
)


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


class TestPairColocatedAssignment:
    def test_pair_members_always_share_a_node(self) -> None:
        plans = [*_pair("pair:0", 0), *_pair("pair:1", 1)]
        entries = build_batch_plan(plans, max_concurrent=4)
        placement = assign_nodes(entries, ["dgx-a", "dgx-b", "dgx-c"])
        assert placement["c-0"] == placement["f-0"]
        assert placement["c-1"] == placement["f-1"]

    def test_lineages_still_spread_across_the_fleet(self) -> None:
        plans = []
        for i in range(40):
            plans.append(
                {
                    "run_id": f"r-{i:03d}",
                    "lineage_root_id": f"l{i}",
                    "pair_role": "intervention",
                    "scenario": "healthy",
                }
            )
        entries = build_batch_plan(plans, max_concurrent=4)
        placement = assign_nodes(entries, ["n1", "n2", "n3"])
        used = list(set(placement.values()))
        assert len(used) >= 2  # real spread, not everything on one node
        counts = sorted(list(placement.values()).count(n) for n in used)
        assert counts[-1] <= 30  # no node starves the fleet


class TestParallelDispatch:
    def test_same_wave_runs_concurrently_and_report_order_is_input_order(
        self, tmp_path
    ) -> None:
        import threading
        import time as _time

        plans = [
            {
                "run_id": f"r{i}",
                "lineage_root_id": f"l{i}",
                "pair_role": "intervention",
                "scenario": "healthy",
            }
            for i in range(4)
        ]
        entries = build_batch_plan(plans, max_concurrent=4)
        barrier = threading.Barrier(4, timeout=5)
        overlap_seen = []

        def runner(entry, attempt_dir):
            overlap_seen.append(barrier.wait())
            _time.sleep(0.01)
            return {"ok": entry.run_id}

        report = execute_batch(entries, runner, attempts_root=tmp_path, parallel=True)
        assert all(e["status"] == "succeeded" for e in report.entries)
        assert [e["run_id"] for e in report.entries] == [p["run_id"] for p in plans]
        assert max(overlap_seen) > 1  # lanes genuinely overlapped


class TestTerminalFailures:
    def test_terminal_scientific_failure_is_never_retried(self, tmp_path) -> None:
        plans = [
            {
                "run_id": "r0",
                "lineage_root_id": "l0",
                "pair_role": "intervention",
                "scenario": "thrust_loss",
            }
        ]
        entries = build_batch_plan(plans, max_concurrent=1)
        calls = []

        def manifestation_missing(entry, attempt_dir):
            calls.append(entry.run_id)
            raise TerminalRunError("fault acknowledged but did not manifest")

        report = execute_batch(
            entries, manifestation_missing, attempts_root=tmp_path, max_attempts=3
        )
        record = report.entries[0]
        assert record["status"] == "failed_terminal"
        assert record["attempts"][0]["status"] == "failed_terminal"
        assert len(record["attempts"]) == 1  # exactly one attempt: no bias
        assert calls == ["r0"]

    def test_transient_failures_still_retry(self, tmp_path) -> None:
        plans = [
            {
                "run_id": "r0",
                "lineage_root_id": "l0",
                "pair_role": "intervention",
                "scenario": "healthy",
            }
        ]
        entries = build_batch_plan(plans, max_concurrent=1)

        def flaky(entry, attempt_dir):
            if not attempt_dir.name.endswith("attempt-1"):
                raise OSError("transient link flap")
            return {"ok": True}

        report = execute_batch(entries, flaky, attempts_root=tmp_path, max_attempts=3)
        assert report.entries[0]["status"] == "succeeded"


class TestPairAtomicCommitPointers:
    def test_commit_pointer_binds_both_members_or_nothing(self, tmp_path) -> None:
        commits = tmp_path / "commits"
        plans = _pair("pair:0", 0) + _pair("pair:1", 1)
        entries = build_batch_plan(plans, max_concurrent=4)

        def runner(entry, attempt_dir):
            if entry.run_id == "f-1":
                raise OSError("permanent hardware fault")
            return {"ok": True}

        promoted = []
        report = execute_batch(
            entries,
            runner,
            attempts_root=tmp_path / "attempts",
            promote=lambda d, r: promoted.append(d) or d,
            pair_atomic=True,
            commits_dir=commits,
        )
        by_run = {e["run_id"]: e for e in report.entries}
        # Complete pair committed AND both members promoted together.
        assert (commits / "pair_0.json").is_file()
        commit = json.loads((commits / "pair_0.json").read_text(encoding="utf-8"))
        assert commit["schema"] == "logdiagnosis.pair-commit/v1"
        assert set(commit["members"]) == {"c-0", "f-0"}
        assert len(commit["commit_sha256"]) == 64
        assert by_run["c-0"]["attempts"][-1]["promoted_to"]
        assert by_run["f-0"]["attempts"][-1]["promoted_to"]
        # Incomplete pair: held, uncommitted, unpromoted.
        assert not (commits / "pair_1.json").exists()
        assert by_run["c-1"]["attempts"][-1]["promoted_to"] is None
        assert by_run["c-1"]["pair_held"] is True
        assert len(promoted) == 2

    def test_promotion_failure_mid_pair_leaves_no_commit(self, tmp_path) -> None:
        commits = tmp_path / "commits"
        plans = _pair("pair:0", 0)
        entries = build_batch_plan(plans, max_concurrent=2)
        state = {"n": 0}

        def failing_second_promote(attempt_dir, receipt):
            state["n"] += 1
            if state["n"] == 2:
                raise OSError("disk full during second arm publication")
            return attempt_dir

        report = execute_batch(
            entries,
            lambda e, d: {"ok": True},
            attempts_root=tmp_path,
            promote=failing_second_promote,
            pair_atomic=True,
            commits_dir=commits,
        )
        # The batch surfaces the error; the commit pointer must not exist so
        # consumers can never observe a half-pair.
        assert not (commits / "pair:0.json").exists()
        assert any(e.get("last_error") for e in report.entries)


class TestFencingAndRecovery:
    def test_locks_embed_monotonic_epochs(self, tmp_path) -> None:
        from synthetic_data.cluster.scheduler import (
            advance_epoch,
            current_epoch,
        )

        assert current_epoch(tmp_path) == 0
        assert advance_epoch(tmp_path) == 1
        assert advance_epoch(tmp_path) == 2
        assert current_epoch(tmp_path) == 2

    def test_attempt_history_records_fencing_epochs(self, tmp_path) -> None:
        plans = _pair("p0", 0)
        entries = build_batch_plan(plans, max_concurrent=2)
        report = execute_batch(
            entries, lambda e, d: {"ok": True}, attempts_root=tmp_path
        )
        epochs = {a["fencing_epoch"] for e in report.entries for a in e["attempts"]}
        assert epochs and min(epochs) >= 1

    def test_reconcile_and_fence_stale_workers(self, tmp_path) -> None:
        dead = tmp_path / "r-dead" / "attempt-0"
        dead.mkdir(parents=True)
        (dead / ".lock").write_text(
            json.dumps({"pid": 999_999_999, "acquired_at": 0.0, "epoch": 3}),
            encoding="utf-8",
        )
        states = {s["attempt_dir"]: s for s in reconcile(tmp_path)}
        item = states[str(dead)]
        assert item["lock_state"] == "stale_lock"
        assert item["resume_action"] == "fence_then_retry"
        fenced = fence_stale(tmp_path)
        assert len(fenced) == 1
        assert not (dead / ".lock").exists()
        after = reconcile(tmp_path)[0]
        assert after["resume_action"] == "retry_now"


class TestAssignmentLedger:
    def test_ledger_freezes_placement_with_build_bindings(self, tmp_path) -> None:
        entries = build_batch_plan(_pair("p0", 0), max_concurrent=2)
        sha = write_assignment_ledger(
            entries,
            ["dgx-a"],
            path=tmp_path / "ledger.json",
            salt="rack7",
            node_capabilities={"dgx-a": {"arch": "arm64", "gpus": 8}},
            image_digest="sha256:" + "a" * 64,
            binary_sha256="b" * 64,
            resource_profile="dgx-h100",
        )
        payload = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
        assert payload["placement"] == {"c-0": "dgx-a", "f-0": "dgx-a"}
        assert payload["image_digest"].startswith("sha256:")
        assert payload["binary_sha256"] == "b" * 64
        assert len(payload["ledger_sha256"]) == 64
        assert len(sha) == 64


class TestExtendedBatchReceipt:
    def test_receipt_carries_history_chain_assignments_commits(self, tmp_path) -> None:
        commits = tmp_path / "commits"
        plans = _pair("p0", 0)
        entries = build_batch_plan(plans, max_concurrent=2)
        report = execute_batch(
            entries,
            lambda e, d: {"ok": True},
            attempts_root=tmp_path,
            pair_atomic=True,
            commits_dir=commits,
        )
        ledger_sha = write_assignment_ledger(
            entries,
            ["n1"],
            path=tmp_path / "ledger.json",
            image_digest="sha256:" + "c" * 64,
            binary_sha256="d" * 64,
        )
        receipt_sha = write_batch_receipt(
            report,
            tmp_path / "batch.json",
            assignment_ledger_sha256=ledger_sha,
            build_bindings={"image_digest": "sha256:" + "c" * 64},
            pair_commit_shas={"p0": "e" * 64},
        )
        payload = json.loads((tmp_path / "batch.json").read_text(encoding="utf-8"))
        assert payload["assignment_ledger_sha256"] == ledger_sha
        assert payload["build_bindings"]["image_digest"].startswith("sha256:")
        assert payload["pair_commits"] == {"p0": "e" * 64}
        for entry in payload["entries"]:
            history = entry["attempt_history"]
            assert history and all("fencing_epoch" in a for a in history)
        assert len(receipt_sha) == 64


# ---------------------------------------------------------------------------
# Effective ArduPilot defaults merging
# ---------------------------------------------------------------------------


class TestEffectiveDefaultsMerge:
    @pytest.fixture()
    def parm_files(self, tmp_path):
        base = tmp_path / "copter.parm"
        hexa = tmp_path / "copter-hexa.parm"
        octa = tmp_path / "copter-octa.parm"
        base.write_text(
            "# generic copter defaults\n"
            "FRAME_CLASS 1\n"
            "ATC_RAT_RLL_P 0.135\n"
            "SCHED_LOOP_RATE 400\n",
            encoding="utf-8",
        )
        hexa.write_text(
            "# hexa overlay\nFRAME_CLASS 2\nMOT_PWM_TYPE 6\n",
            encoding="utf-8",
        )
        octa.write_text("# octa overlay\nFRAME_CLASS 3\n", encoding="utf-8")
        return {"base": base, "hexa": hexa, "octa": octa}

    def test_parses_real_parm_format_with_comments(self, parm_files) -> None:
        values = parse_parm_file(parm_files["base"])
        assert values == {
            "FRAME_CLASS": 1.0,
            "ATC_RAT_RLL_P": 0.135,
            "SCHED_LOOP_RATE": 400.0,
        }

    def test_merge_validates_frame_class_across_layers(self, parm_files) -> None:
        merged = merge_effective_defaults(
            (parm_files["base"],),
            overlay_files=(parm_files["octa"],),
            expected_frame="octa",
        )
        assert merged["effective_defaults"]["FRAME_CLASS"] == 3.0
        assert merged["effective_defaults"]["ATC_RAT_RLL_P"] == 0.135
        assert "MOT_PWM_TYPE" not in merged["effective_defaults"]
        assert len(merged["effective_defaults_sha256"]) == 64

        # The overlay legitimately overrides the base frame, but the FINAL
        # value must still match the plan: a hexa overlay on a quad plan is
        # exactly the silent corruption this guard prevents.
        with pytest.raises(ValueError, match="plan requires quad"):
            merge_effective_defaults(
                (parm_files["base"],),
                overlay_files=(parm_files["hexa"],),
                expected_frame="quad",
            )

    def test_conflicting_overlays_fail_closed(self, parm_files) -> None:
        with pytest.raises(ValueError, match="disagree"):
            merge_effective_defaults(
                (parm_files["base"],),
                overlay_files=(parm_files["hexa"], parm_files["octa"]),
                expected_frame="octa",
            )

    def test_plan_overrides_layer_last_and_bind_hash(self, parm_files) -> None:
        effective = merge_effective_defaults(
            (parm_files["base"],), expected_frame="quad"
        )
        final = apply_plan_overrides(effective, {"ATC_RAT_RLL_P": 0.14})
        assert final["effective_defaults"]["ATC_RAT_RLL_P"] == 0.14
        assert final["plan_overrides"] == {"ATC_RAT_RLL_P": 0.14}
        assert len(final["final_sha256"]) == 64
