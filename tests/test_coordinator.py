"""Cross-node coordinator lifecycle, worker contract, and collection
pair-commit enforcement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from synthetic_data.cluster import ClusterCoordinator
from synthetic_data.cluster.coordinator import SSHTransport
from synthetic_data.cluster.worker import load_task
from synthetic_data.collector import VerificationError, _require_pair_commit


def _plans():
    plans = []
    for pair in range(2):
        lineage = f"pair:{pair}"
        plans.append(
            {
                "run_id": f"c-{pair}",
                "lineage_root_id": lineage,
                "pair_role": "sham_control",
                "scenario": "thrust_loss",
            }
        )
        plans.append(
            {
                "run_id": f"f-{pair}",
                "lineage_root_id": lineage,
                "pair_role": "intervention",
                "scenario": "thrust_loss",
            }
        )
    return plans


@pytest.fixture()
def coord(tmp_path):
    return ClusterCoordinator(
        tmp_path / "state",
        attempts_root=tmp_path / "attempts",
        commits_dir=tmp_path / "commits",
        transport=SSHTransport(dry_run=True),
    )


class TestCoordinatorLifecycle:
    def test_freeze_submit_status_seal_happy_path(self, coord, tmp_path) -> None:
        manifest = coord.freeze(
            "campaign-001",
            _plans(),
            ["spark-01", "spark-02"],
            salt="rack7",
            image_digest="sha256:" + "a" * 64,
            binary_sha256="b" * 64,
        )
        assert manifest["runs_total"] == 4
        assert len(manifest["lineages"]) == 2
        ledger = json.loads(
            (coord.state_dir / "campaign-001.assignment.json").read_text(
                encoding="utf-8"
            )
        )
        # Pairs co-located on one node.
        for lineage in ("pair:0", "pair:1"):
            members = [
                rid
                for rid, m in manifest["runs_index"].items()
                if m["lineage_root_id"] == lineage
            ]
            nodes_used = {ledger["placement"][rid] for rid in members}
            assert len(nodes_used) == 1

        issued = coord.submit("campaign-001")
        assert len(issued) == 2  # one dispatch per pair (lineage-scoped)
        assert all(i["argv"][0] == "ssh" for i in issued)
        assert all("cluster.worker" in " ".join(i["argv"]) for i in issued)

        status = coord.status()
        assert len(status["claims"]) == 2
        assert all(not c["lease_expired"] for c in status["claims"])

        # Expire leases so the next refusal is about commits, not leases.
        claims_dir = coord.state_dir / "claims"
        for path in claims_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["leased_until"] = 0.0
            path.write_text(json.dumps(payload), encoding="utf-8")

        # Seal must refuse: nothing committed yet.
        with pytest.raises(ValueError, match="without pair-commit"):
            from synthetic_data.cluster.scheduler import BatchReport

            coord.seal("campaign-001", BatchReport(), output_path=tmp_path / "s.json")

    def test_seal_refuses_live_leases_and_missing_commits(self, coord) -> None:
        coord.freeze("c1", _plans()[:2], ["spark-01"])
        coord.submit("c1")
        with pytest.raises(ValueError, match="still leased"):
            from synthetic_data.cluster.scheduler import BatchReport

            coord.seal("c1", BatchReport(), output_path="x.json")

    def test_seal_succeeds_when_all_pairs_committed_and_leases_expired(
        self, coord, tmp_path, monkeypatch
    ) -> None:
        coord.freeze("c2", _plans(), ["spark-01"])
        coord.submit("c2")

        # Simulate completed workers: commits + expired leases.
        coord.commits_dir.mkdir(parents=True, exist_ok=True)
        for lineage in ("pair:0", "pair:1"):
            safe = lineage.replace(":", "_")
            commit = {
                "schema": "logdiagnosis.pair-commit/v1",
                "lineage_root_id": lineage,
                "members": {},
                "fencing_epoch": 1,
                "commit_sha256": "0" * 64,
            }
            (coord.commits_dir / f"{safe}.json").write_text(
                json.dumps(commit), encoding="utf-8"
            )
        claims_dir = coord.state_dir / "claims"
        for path in claims_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["leased_until"] = 0.0
            path.write_text(json.dumps(payload), encoding="utf-8")

        from synthetic_data.cluster.scheduler import BatchReport

        report = BatchReport(
            entries=[
                {"run_id": rid, "status": "succeeded", "attempts": []}
                for rid in ("c-0", "f-0", "c-1", "f-1")
            ]
        )
        sha = coord.seal("c2", report, output_path=tmp_path / "sealed.json")
        assert len(sha) == 64
        sealed = json.loads(
            (coord.state_dir / "c2.sealed.json").read_text(encoding="utf-8")
        )
        assert sealed["schema"] == "logdiagnosis.cluster-sealed-batch/v1"
        assert sealed["committed_lineages"] == ["pair:0", "pair:1"]

    def test_reconcile_fences_stale_workers(self, coord, tmp_path) -> None:
        stale = tmp_path / "attempts" / "r0" / "attempt-0"
        stale.mkdir(parents=True)
        (stale / ".lock").write_text(
            json.dumps({"pid": 999_999_999, "acquired_at": 0.0, "epoch": 4}),
            encoding="utf-8",
        )
        result = coord.reconcile()
        assert result["fenced"][0]["attempt_dir"] == str(stale)
        assert not (stale / ".lock").exists()


class TestWorkerTaskContract:
    def test_task_validation_fails_closed(self, tmp_path) -> None:
        good = {
            "schema": "logdiagnosis.cluster-worker-task/v1",
            "run_id": "r0",
            "experiment_dir": "/experiment",
            "binary_path": "/opt/ardupilot/arducopter",
            "endpoint": "tcpin:127.0.0.1:14550",
            "attempt_dir": str(tmp_path / "attempt-0"),
            "fencing_epoch": 7,
        }
        assert load_task(_write(tmp_path, good))["run_id"] == "r0"

        bad_schema = dict(good, schema="other/v9")
        with pytest.raises(ValueError, match="unsupported worker task schema"):
            load_task(_write(tmp_path, bad_schema))
        missing = {k: v for k, v in good.items() if k != "fencing_epoch"}
        with pytest.raises(ValueError, match="lacks required fields"):
            load_task(_write(tmp_path, missing))
        bad_epoch = dict(good, fencing_epoch=True)
        with pytest.raises(ValueError, match="positive integer"):
            load_task(_write(tmp_path, bad_epoch))

    def test_preflight_rejects_fleet_dispatch_without_deployment(self):
        from synthetic_data.cli import build_parser

        args = build_parser().parse_args(["cluster", "preflight", "--all-nodes"])
        with pytest.raises(ValueError, match="SSH coordinator deployment"):
            from synthetic_data.cli import _cluster_command

            _cluster_command(args)


def _write(tmp_path, payload):
    path = tmp_path / "task.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestPairCommitEnforcementInCollection:
    def test_missing_pointer_makes_lone_arm_untrainable(self, tmp_path) -> None:
        plan = {
            "run_id": "f-0",
            "lineage_root_id": "pair:0",
            "pair_role": "intervention",
        }
        receipts = tmp_path / "receipts"
        receipts.mkdir(parents=True)
        receipt = receipts / "f-0.execution.json"
        receipt.write_bytes(b"{}")
        commits = tmp_path / "commits"

        # No commits dir at all -> lone arm refused.
        with pytest.raises(VerificationError, match="no sealed pair-commit"):
            _require_pair_commit(tmp_path, plan, commits_dir=commits)

        # Pointer exists but does not bind this receipt hash -> refused.
        commits.mkdir(parents=True)
        commit = {
            "schema": "logdiagnosis.pair-commit/v1",
            "lineage_root_id": "pair:0",
            "members": {
                "f-0": {"receipt_sha256": "0" * 64},
            },
            "fencing_epoch": 3,
        }
        (commits / "pair_0.json").write_text(json.dumps(commit), encoding="utf-8")
        with pytest.raises(VerificationError, match="does not match the sealed"):
            _require_pair_commit(tmp_path, plan, commits_dir=commits)

        # Correct binding -> accepted.
        actual = hashlib.sha256(receipt.read_bytes()).hexdigest()
        commit["members"]["f-0"]["receipt_sha256"] = actual
        (commits / "pair_0.json").write_text(json.dumps(commit), encoding="utf-8")
        _require_pair_commit(tmp_path, plan, commits_dir=commits)

    def test_unpaired_runs_carry_no_pair_contract(self, tmp_path) -> None:
        plan = {"run_id": "solo", "lineage_root_id": "", "pair_role": ""}
        _require_pair_commit(tmp_path, plan, commits_dir=tmp_path / "absent")


class TestDockerfileGuards:
    CONTAINER_DIR = (
        Path(__file__).parents[1] / "synthetic_data" / "cluster" / "containers"
    )

    def test_exact_commit_checkout_not_branch_clone(self) -> None:
        text = (self.CONTAINER_DIR / "Dockerfile.ardupilot-sitl").read_text(
            encoding="utf-8"
        )
        assert (
            "git clone --recurse-submodules -j8 --depth 1 \\\n        --branch"
            not in text
        )
        assert 'fetch --depth 1 origin "${ARDUPILOT_COMMIT}"' in text
        assert "checkout --detach FETCH_HEAD" in text
        assert "40-character SHA" in text

    def test_base_digest_placeholder_hard_fails_build(self) -> None:
        text = (self.CONTAINER_DIR / "Dockerfile.ardupilot-sitl").read_text(
            encoding="utf-8"
        )
        assert "FATAL: BASE_DIGEST is not pinned" in text
