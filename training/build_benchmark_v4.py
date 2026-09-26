"""Build benchmark v4: v3 base plus newly labelled incidents.

v4 is the **confirmatory holdout** described in ``docs/PREREGISTRATION_V4.md``.
It carries the v3 set forward and adds a new pile of incidents labelled with the
same protocol, so the only unseen data is the new pile.

Inputs (all produced by the maintainer; this script does not fetch or invent
labels):

* ``data/benchmark/ground_truth_real_v3.json`` — the v3 base;
* ``data/benchmark/thread_annotations_v4.json`` — new incidents, same schema as
  ``thread_annotations_pool.json`` (status ``labelled``, one hash-matched ``.bin``,
  one label per incident, a citing post + verbatim quote).

Behaviour mirrors ``build_benchmark_v3.py``:

* records with status ``labelled`` and exactly one local ``.bin`` whose SHA256
  matches are kept;
* an incident whose logs carry more than one label is dropped entirely;
* new incidents whose ``thread`` already appears in v3 are skipped (no double
  counting);
* logs are hard-linked (or copied) into the stage directory.

The maintainer must create ``thread_annotations_v4.json`` by running the forum
miner + ``training/verify_thread_annotations.py`` and a human spot-check. This
script only assembles the ground-truth file. It never fabricates labels.

Example::

    python training/build_benchmark_v4.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="data/benchmark/ground_truth_real_v3.json")
    parser.add_argument("--v4", default="data/benchmark/thread_annotations_v4.json")
    parser.add_argument("--pool-dir", default="data/raw/adaptation")
    parser.add_argument("--stage-dir", default="data/raw/benchmark_v4")
    parser.add_argument("--output", default="data/benchmark/ground_truth_real_v4.json")
    parser.add_argument(
        "--allow-missing-logs",
        action="store_true",
        help="emit the ground-truth record even when the .bin is not present locally "
        "(useful on a machine that has not hydrated the v4 pool); the log is still "
        "hash-checked when present, and flagged trainable=False when absent",
    )
    args = parser.parse_args()

    if not (ROOT / args.v4).exists():
        print(
            "MISSING: data/benchmark/thread_annotations_v4.json\n"
            "This file is produced by the maintainer (forum miner -> verify -> human\n"
            "spot-check). This script assembles v4 from it; it does not create labels.\n"
            "Run the Step 2 pipeline in docs/PUBLICATION_PLAN.md first."
        )
        return 2

    base = _load(ROOT / args.base)
    v4 = _load(ROOT / args.v4)["records"]
    stage = ROOT / args.stage_dir
    stage.mkdir(parents=True, exist_ok=True)

    logs = [dict(entry, origin="v3") for entry in base["logs"]]
    existing_threads = {entry["incident_id"] for entry in logs}

    skipped: Counter[str] = Counter()
    added = 0
    for record in v4:
        if record["status"] != "labelled":
            skipped[record["status"]] += 1
            continue
        if len(record["files"]) != 1:
            skipped["multiple_bins_in_payload"] += 1
            continue
        if record["thread"] in existing_threads:
            skipped["already_in_base"] += 1
            continue
        item = record["files"][0]
        source = ROOT / args.pool_dir / item["file"]
        if not source.exists():
            if args.allow_missing_logs:
                skipped["log_not_hydrated_trainable_false"] += 1
            else:
                skipped["file_missing"] += 1
                continue
        if source.exists() and _sha256(source) != item["sha256"]:
            skipped["file_hash_mismatch"] += 1
            continue
        if source.exists():
            target = stage / item["file"]
            if not target.exists():
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copy2(source, target)
            trainable = True
        else:
            trainable = False
        logs.append(
            {
                "filename": item["file"],
                "labels": [record["label"]],
                "incident_id": record["thread"],
                "source_url": record["source_url"],
                "source_type": "ArduPilot_Discuss",
                "sha256": item["sha256"],
                "certainty": record["certainty"],
                "diagnosing_post": record["diagnosing_post"],
                "evidence_tier": f"thread_post_{record['certainty']}",
                "confidence": "high" if record["certainty"] == "explicit" else "medium",
                "trainable": trainable,
                "origin": "v4",
            }
        )
        added += 1
        existing_threads.add(record["thread"])

    labels_by_incident: dict[str, set[str]] = defaultdict(set)
    for entry in logs:
        labels_by_incident[entry["incident_id"]].add(entry["labels"][0])
    conflicted = {inc for inc, labels in labels_by_incident.items() if len(labels) > 1}
    kept = [entry for entry in logs if entry["incident_id"] not in conflicted]

    doc = {
        "schema": "logdiagnosis.real-benchmark-ground-truth/v4",
        "label_policy": base["label_policy"],
        "sources": {"v3": args.base, "v4": args.v4},
        "frozen_protocol": "docs/PREREGISTRATION_V4.md",
        "logs": kept,
    }
    (ROOT / args.output).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    summary = {
        "logs": len(kept),
        "incidents": len({entry["incident_id"] for entry in kept}),
        "from_v3": sum(entry["origin"] == "v3" for entry in kept),
        "from_v4": sum(entry["origin"] == "v4" for entry in kept),
        "trainable": sum(entry.get("trainable", True) for entry in kept),
        "explicit": sum(entry["certainty"] == "explicit" for entry in kept),
        "dropped_conflicted_incidents": sorted(conflicted),
        "v4_added": added,
        "v4_skipped": dict(skipped),
        "label_distribution": dict(Counter(entry["labels"][0] for entry in kept)),
        "meets_gate_100_incidents": len({entry["incident_id"] for entry in kept}) >= 100,
    }
    (ROOT / "data/benchmark/benchmark_v4_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
