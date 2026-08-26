"""Command-line interface for the verified synthetic-data laboratory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ablation import run_ablation
from .catalog import SCENARIOS, UNSUPPORTED_SYNTHETIC_LABELS
from .cluster import ClusterCoordinator
from .cluster.coordinator import SSHTransport
from .cluster.topology import probe_host
from .collector import collect_verified_logs
from .confirmation import build_confirmation_report
from .evidence_bundle import assemble_evidence_bundle, load_domain_reports
from .executor import execute_run, preflight_run
from .fidelity import build_fidelity_report
from .first_pair import run_first_pair
from .gates import evaluate_files
from .ood import build_ood_report
from .owned_runner import OwnedSITLProcess
from .planner import build_paired_run_plans, build_run_plans, write_experiment
from .runner import PymavlinkSITLSession
from .schema import ParameterSchema, sha256_file
from .splits import create_split_ledger
from .temporal_fidelity import build_temporal_fidelity_report
from .temporal_ledger import build_temporal_ledger


def _cluster_command(args: argparse.Namespace) -> dict:
    sub = args.cluster_command

    if sub == "preflight":
        if args.all_nodes:
            raise ValueError(
                "--all-nodes dispatch requires the SSH coordinator "
                "deployment (spark-01..04); local probe only on this host."
            )
        return probe_host()

    attempts = getattr(args, "attempts_root", None)
    commits = getattr(args, "commits_dir", None)
    state_dir = getattr(args, "state_dir", ".cluster")
    coordinator = ClusterCoordinator(
        state_dir,
        attempts_root=attempts or state_dir + "/attempts",
        commits_dir=commits or state_dir + "/commits",
        transport=SSHTransport(dry_run=True),
    )

    if sub == "freeze":
        plans = json.loads(Path(args.plans_json).read_text(encoding="utf-8"))
        if not isinstance(plans, list):
            raise ValueError("--plans-json must be a JSON array of run plans")
        return coordinator.freeze(
            args.campaign,
            plans,
            args.nodes,
            salt=args.salt,
            image_digest=args.image_digest,
            binary_sha256=args.binary_sha256,
            resource_profile=args.resource_profile,
            max_concurrent=args.max_concurrent,
        )
    if sub == "submit":
        issued = coordinator.submit(args.campaign, pairs=args.pairs or None)
        return {"dispatched": issued, "dry_run": True}
    if sub == "status":
        status = coordinator.status()
        if args.campaign:
            status["campaign"] = coordinator._load_campaign(args.campaign)
        return status
    if sub == "reconcile":
        return coordinator.reconcile()
    if sub == "seal":
        report_path = Path(args.batch_report)
        from .cluster.scheduler import BatchReport

        raw = json.loads(report_path.read_text(encoding="utf-8"))
        report = BatchReport(
            schema=raw.get("schema", ""),
            entries=raw.get("entries", []),
            waves=int(raw.get("waves", 0)),
            max_concurrent=int(raw.get("max_concurrent", 1)),
        )
        receipt_sha = coordinator.seal(args.campaign, report, output_path=args.output)
        return {
            "sealed": True,
            "campaign": args.campaign,
            "batch_receipt_sha256": receipt_sha,
            "output": str(args.output),
        }
    raise ValueError(f"unknown cluster subcommand: {sub}")


def _bundle_evidence_command(args: argparse.Namespace) -> dict:
    candidate = json.loads(Path(args.candidate_json).read_text(encoding="utf-8"))
    if not isinstance(candidate, dict):
        raise TypeError("candidate JSON root must be an object")
    paths: dict[str, str] = {}
    for item in args.domain_reports:
        domain, separator, path = item.partition("=")
        if not separator or not domain or not path:
            raise ValueError(f"--domain-report expects DOMAIN=PATH, got {item!r}")
        paths[domain] = path
    loaded = load_domain_reports(paths)
    authority_receipt = None
    if args.authority_receipt:
        authority_receipt = json.loads(
            Path(args.authority_receipt).read_text(encoding="utf-8")
        )
    confirmation_report = json.loads(
        Path(args.confirmation_report).read_text(encoding="utf-8")
    )
    if not isinstance(confirmation_report, dict):
        raise TypeError("confirmation report root must be an object")
    bundle = assemble_evidence_bundle(
        candidate=candidate,
        confirmation_cohort_sha256=args.confirmation_cohort_sha256,
        confirmation_report=confirmation_report,
        domain_reports=loaded["reports"],
        source_report_sha256=loaded["sha256"],
        authority_receipt=authority_receipt,
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return {
        "bundle_path": str(destination),
        "bundle_status": bundle["bundle_status"],
        "release_authorized": bundle["release_authorized"],
        "metrics_bundle_sha256": bundle["metrics_bundle_sha256"],
        "evidence_binding_sha256": bundle["evidence_binding_sha256"],
    }


def _schema_command(args: argparse.Namespace) -> dict:
    binary_sha256 = sha256_file(args.binary)
    schema = ParameterSchema.from_inventory(
        args.inventory,
        ardupilot_commit=args.ardupilot_commit,
        binary_sha256=binary_sha256,
    )
    destination = schema.write(args.output)
    return {
        "schema_path": str(destination),
        "parameter_count": len(schema.parameters),
        "parameter_schema_sha256": schema.digest,
        "binary_sha256": schema.binary_sha256,
    }


def _plan_command(args: argparse.Namespace) -> dict:
    schema = ParameterSchema.read(args.parameter_schema)
    if args.unpaired:
        plans = build_run_plans(
            args.runs_per_scenario,
            seed=args.seed,
            ardupilot_revision=schema.ardupilot_commit,
            scenarios=args.scenario,
            parameter_schema=schema,
        )
    else:
        plans = build_paired_run_plans(
            args.runs_per_scenario,
            seed=args.seed,
            ardupilot_revision=schema.ardupilot_commit,
            scenarios=args.scenario,
            parameter_schema=schema,
        )
    outputs = write_experiment(
        args.output_dir,
        plans,
        seed=args.seed,
        ardupilot_revision=schema.ardupilot_commit,
        parameter_schema=schema,
    )
    return {
        "runs": len(plans),
        "paired": not args.unpaired,
        "manifest": str(outputs["manifest"]),
        "logs": str(outputs["logs"]),
        "receipts": str(outputs["receipts"]),
        "trainable_artifacts_created": 0,
    }


def _execute_command(args: argparse.Namespace) -> dict:
    if not args.confirm_sitl:
        raise ValueError("--confirm-sitl is required before launching the simulator")
    _, _, plan, _, _, _, _, _ = preflight_run(args.output_dir, args.run_id, args.binary)
    owner = OwnedSITLProcess(
        experiment_dir=args.output_dir,
        plan=plan,
        ardupilot_root=args.ardupilot_root,
        binary_path=args.binary,
        endpoint=args.endpoint,
        instance=args.instance,
    )
    session = PymavlinkSITLSession(args.endpoint)
    try:
        owner.start()
    except Exception:
        try:
            session.close()
        finally:
            owner.abort(args.timeout)
        raise


    try:
        return execute_run(
            args.output_dir,
            args.run_id,
            session=session,
            owner=owner,
            takeoff_altitude_m=args.takeoff_altitude,
            timeout=args.timeout,
            confirm_sitl=args.confirm_sitl,
        )
    except Exception:
        try:
            session.close()
        finally:
            owner.abort(args.timeout)
        raise


def _pair_command(args: argparse.Namespace) -> dict:
    if not args.confirm_sitl:
        raise ValueError("--confirm-sitl is required before launching the simulator")
    return run_first_pair(
        output_dir=args.output_dir,
        binary=args.binary,
        ardupilot_root=args.ardupilot_root,
        scenario=args.scenario,
        seed=args.seed,
        endpoint=args.endpoint,
        frame=args.frame,
        timeout=args.timeout,
        randomize=args.randomize,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    schema = commands.add_parser(
        "schema", help="Bind a live parameter inventory to a commit and SITL binary"
    )
    schema.add_argument("--inventory", required=True)
    schema.add_argument("--ardupilot-commit", required=True)
    schema.add_argument("--binary", required=True)
    schema.add_argument("--output", required=True)

    plan = commands.add_parser(
        "plan", help="Create immutable matched healthy/fault experiment plans"
    )
    plan.add_argument("--parameter-schema", required=True)
    plan.add_argument("--output-dir", required=True)
    plan.add_argument("--runs-per-scenario", type=int, default=5)
    plan.add_argument("--seed", type=int, default=20260823)
    plan.add_argument(
        "--scenario",
        action="append",
        choices=sorted(name for name in SCENARIOS if name != "healthy"),
    )
    plan.add_argument(
        "--unpaired",
        action="store_true",
        help="Do not create matched healthy controls",
    )

    execute = commands.add_parser(
        "execute", help="Launch and own one pinned direct SITL binary for a run plan"
    )
    execute.add_argument("--output-dir", required=True)
    execute.add_argument("--run-id", required=True)
    execute.add_argument("--endpoint", default="tcpin:127.0.0.1:14550")
    execute.add_argument("--binary", required=True)
    execute.add_argument("--ardupilot-root", required=True)
    execute.add_argument("--instance", type=int, default=0)
    execute.add_argument("--takeoff-altitude", type=float, default=10.0)
    execute.add_argument("--timeout", type=float, default=120.0)
    execute.add_argument(
        "--confirm-sitl",
        action="store_true",
        help="Confirm that the loopback endpoint is an isolated software simulator",
    )

    pair = commands.add_parser(
        "pair",
        help="Capture parameters, execute one sham/intervention pair, seal, and collect",
    )
    pair.add_argument("--output-dir", required=True)
    pair.add_argument("--binary", required=True)
    pair.add_argument("--ardupilot-root", required=True)
    pair.add_argument("--scenario", required=True, choices=sorted(name for name in SCENARIOS if name != "healthy"))
    pair.add_argument("--endpoint", default="tcpin:127.0.0.1:14550")
    pair.add_argument("--frame", choices=("quad", "hexa", "octa"), default="quad")
    pair.add_argument("--seed", type=int, default=20260823)
    pair.add_argument("--timeout", type=float, default=120.0)
    pair.add_argument(
        "--randomize",
        action="store_true",
        help="Draw capability-checked noise/vibration/battery parameters per run "
        "(shared by both pair members) to close the audited sim-to-real gap",
    )
    pair.add_argument(
        "--confirm-sitl",
        action="store_true",
        help="Confirm that the loopback endpoint is an isolated software simulator",
    )

    collect = commands.add_parser(
        "collect", help="Verify receipts, DataFlash identity, onset, and manifestation"
    )
    collect.add_argument("--output-dir", required=True)
    collect.add_argument("--include-experimental", action="store_true")

    split = commands.add_parser(
        "freeze-split", help="Create a source-hash-bound real incident split ledger"
    )
    split.add_argument("--labels-csv", required=True)
    split.add_argument("--groups-csv", required=True)
    split.add_argument("--output", required=True)
    split.add_argument("--seed", type=int, default=20260823)
    split.add_argument(
        "--class",
        action="append",
        dest="declared_classes",
        help="Preregister a model class before freezing the split (repeatable)",
    )

    fidelity = commands.add_parser(
        "fidelity", help="Measure sim-real feature gaps without touching the lockbox"
    )
    fidelity.add_argument("--features-csv", required=True)
    fidelity.add_argument("--labels-csv", required=True)
    fidelity.add_argument("--groups-csv", required=True)
    fidelity.add_argument("--split-ledger", required=True)
    fidelity.add_argument(
        "--design-manifest",
        help="Frozen preregistered strata denominator (fidelity-design-manifest/v1)",
    )
    fidelity.add_argument("--temporal-ledger")
    fidelity.add_argument("--temporal-design")
    fidelity.add_argument("--output", required=True)

    temporal = commands.add_parser(
        "temporal-fidelity",
        help="Compute raw time-series fidelity from a frozen temporal ledger",
    )
    temporal.add_argument("--ledger", required=True)
    temporal.add_argument("--design", required=True)
    temporal.add_argument("--features-csv", required=True)
    temporal.add_argument("--labels-csv", required=True)
    temporal.add_argument("--groups-csv", required=True)
    temporal.add_argument("--split-ledger", required=True)
    temporal.add_argument("--output", required=True)

    temporal_ledger = commands.add_parser(
        "temporal-ledger",
        help="Extract a frozen temporal ledger from dataset-bound raw logs",
    )
    temporal_ledger.add_argument("--design", required=True)
    temporal_ledger.add_argument("--logs-root", required=True)
    temporal_ledger.add_argument("--features-csv", required=True)
    temporal_ledger.add_argument("--labels-csv", required=True)
    temporal_ledger.add_argument("--groups-csv", required=True)
    temporal_ledger.add_argument("--split-ledger", required=True)
    temporal_ledger.add_argument("--output", required=True)

    ablation = commands.add_parser(
        "ablation", help="Compare verified synthetic doses on a frozen real lockbox"
    )
    ablation.add_argument("--features-csv", required=True)
    ablation.add_argument("--labels-csv", required=True)
    ablation.add_argument("--groups-csv", required=True)
    ablation.add_argument("--split-ledger", required=True)
    ablation.add_argument("--output", required=True)
    ablation.add_argument(
        "--prediction-ledger",
        help="Output path for the deterministic per-lineage prediction ledger",
    )
    ablation.add_argument("--bootstrap-draws", type=int, default=10000)

    ood = commands.add_parser(
        "ood", help="Compute lineage-level OOD and runtime-routing evidence"
    )
    ood.add_argument("--prediction-ledger", required=True)
    ood.add_argument("--design-manifest", required=True)
    ood.add_argument("--output", required=True)

    confirmation = commands.add_parser(
        "confirmation",
        help="Recompute one-time physical confirmation metrics from a sealed ledger",
    )
    confirmation.add_argument("--prediction-ledger", required=True)
    confirmation.add_argument("--cohort-manifest", required=True)
    confirmation.add_argument("--candidate-manifest", required=True)
    confirmation.add_argument("--baseline-manifest", required=True)
    confirmation.add_argument("--development-groups", required=True)
    confirmation.add_argument("--development-split-ledger", required=True)
    confirmation.add_argument("--bootstrap-draws", type=int, default=10000)
    confirmation.add_argument("--seed", type=int, default=20260823)
    confirmation.add_argument("--output", required=True)

    gate = commands.add_parser(
        "gate", help="Evaluate a complete evidence bundle against fail-closed policy"
    )
    gate.add_argument("--evidence", required=True)
    gate.add_argument(
        "--policy",
        default=str(Path(__file__).with_name("configs") / "acceptance_gates.json"),
    )
    gate.add_argument("--output", required=True)

    bundle = commands.add_parser(
        "bundle-evidence",
        help="Assemble and bind an unsigned acceptance-evidence draft",
    )
    bundle.add_argument("--candidate-json", required=True)
    bundle.add_argument(
        "--domain-report",
        action="append",
        dest="domain_reports",
        required=True,
        metavar="DOMAIN=PATH",
        help="Per-domain source report JSON (repeatable, one per domain)",
    )
    bundle.add_argument("--confirmation-cohort-sha256", required=True)
    bundle.add_argument("--confirmation-report", required=True)
    bundle.add_argument("--authority-receipt")
    bundle.add_argument("--output", required=True)

    cluster = commands.add_parser(
        "cluster",
        help="Cross-node coordinator: preflight, freeze, submit, status, "
        "reconcile, seal",
    )
    cluster_sub = cluster.add_subparsers(dest="cluster_command", required=True)
    pre = cluster_sub.add_parser(
        "preflight", help="Probe host capability (add --all-nodes for fleet)"
    )
    pre.add_argument("--all-nodes", action="store_true")
    freeze_p = cluster_sub.add_parser(
        "freeze", help="Freeze campaign placement and build bindings"
    )
    freeze_p.add_argument("--campaign", required=True)
    freeze_p.add_argument("--plans-json", required=True, help="JSON array of run plans")
    freeze_p.add_argument("--nodes", nargs="+", required=True)
    freeze_p.add_argument("--salt", default="")
    freeze_p.add_argument("--image-digest")
    freeze_p.add_argument("--binary-sha256")
    freeze_p.add_argument("--resource-profile")
    freeze_p.add_argument("--max-concurrent", type=int, default=1)
    submit_p = cluster_sub.add_parser(
        "submit", help="Issue pair claims and dispatch workers (dry-run)"
    )
    submit_p.add_argument("--campaign", required=True)
    submit_p.add_argument("--pairs", nargs="*")
    submit_p.add_argument("--state-dir", required=True)
    submit_p.add_argument("--attempts-root", required=True)
    submit_p.add_argument("--commits-dir", required=True)
    status_p = cluster_sub.add_parser("status", help="Claims/pending/commits")
    status_p.add_argument("--campaign")
    status_p.add_argument("--state-dir", required=True)
    status_p.add_argument("--attempts-root")
    status_p.add_argument("--commits-dir")
    reconcile_p = cluster_sub.add_parser(
        "reconcile", help="Fence stale workers; report pending attempts"
    )
    reconcile_p.add_argument("--state-dir", required=True)
    reconcile_p.add_argument("--attempts-root", required=True)
    reconcile_p.add_argument("--commits-dir", required=True)
    seal_p = cluster_sub.add_parser(
        "seal", help="Seal a completed batch (refuses incomplete pairs)"
    )
    seal_p.add_argument("--campaign", required=True)
    seal_p.add_argument("--batch-report", required=True)
    seal_p.add_argument("--state-dir", required=True)
    seal_p.add_argument("--attempts-root", required=True)
    seal_p.add_argument("--commits-dir", required=True)
    seal_p.add_argument("--output", required=True)

    commands.add_parser(
        "list", help="Show supported and intentionally unsupported labels"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "schema":
        result = _schema_command(args)
    elif args.command == "plan":
        result = _plan_command(args)
    elif args.command == "execute":
        result = _execute_command(args)
    elif args.command == "pair":
        result = _pair_command(args)
    elif args.command == "collect":
        result = collect_verified_logs(
            args.output_dir, include_experimental=args.include_experimental
        )
    elif args.command == "freeze-split":
        result = create_split_ledger(
            args.labels_csv,
            args.groups_csv,
            args.output,
            seed=args.seed,
            declared_classes=args.declared_classes,
        )
    elif args.command == "fidelity":
        result = build_fidelity_report(
            args.features_csv,
            args.labels_csv,
            args.groups_csv,
            args.split_ledger,
            output_path=args.output,
            design_manifest_path=args.design_manifest,
            temporal_ledger_path=args.temporal_ledger,
            temporal_design_path=args.temporal_design,
        )
    elif args.command == "temporal-fidelity":
        result = build_temporal_fidelity_report(
            args.ledger,
            args.design,
            features_csv=args.features_csv,
            labels_csv=args.labels_csv,
            groups_csv=args.groups_csv,
            split_ledger_path=args.split_ledger,
            output_path=args.output,
        )
    elif args.command == "temporal-ledger":
        result = build_temporal_ledger(
            args.design,
            args.logs_root,
            features_csv=args.features_csv,
            labels_csv=args.labels_csv,
            groups_csv=args.groups_csv,
            split_ledger_path=args.split_ledger,
            output_path=args.output,
        )
    elif args.command == "ablation":
        result = run_ablation(
            args.features_csv,
            args.labels_csv,
            args.groups_csv,
            args.split_ledger,
            output_path=args.output,
            prediction_ledger_path=args.prediction_ledger,
            bootstrap_draws=args.bootstrap_draws,
        )
    elif args.command == "ood":
        result = build_ood_report(
            args.prediction_ledger,
            args.design_manifest,
            output_path=args.output,
        )
    elif args.command == "confirmation":
        result = build_confirmation_report(
            args.prediction_ledger,
            args.cohort_manifest,
            args.candidate_manifest,
            args.baseline_manifest,
            args.development_groups,
            args.development_split_ledger,
            output_path=args.output,
            bootstrap_draws=args.bootstrap_draws,
            seed=args.seed,
        )
    elif args.command == "gate":
        result = evaluate_files(args.evidence, args.policy, args.output)
    elif args.command == "bundle-evidence":
        result = _bundle_evidence_command(args)
    elif args.command == "cluster":
        result = _cluster_command(args)
    else:
        result = {
            "supported": {
                name: {
                    "label": spec.label,
                    "root_family": spec.root_family,
                    "fault_mode": spec.fault_mode,
                    "maturity": spec.maturity,
                    "parameter_variants": [variant.name for variant in spec.variants],
                    "non_claims": list(spec.non_claims),
                }
                for name, spec in SCENARIOS.items()
            },
            "intentionally_unsupported": dict(UNSUPPORTED_SYNTHETIC_LABELS),
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
