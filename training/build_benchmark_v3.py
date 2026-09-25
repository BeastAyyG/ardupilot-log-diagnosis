"""Build benchmark v3: v2 thread-verified logs plus newly labelled pool logs.

Inputs:

* ``data/benchmark/ground_truth_real_v2.json`` (thread-verified, from
  ``training/build_incident_registry.py``);
* ``data/benchmark/thread_annotations_pool.json`` (previously unlabelled real
  logs labelled from their forum threads; files fetched by
  ``training/fetch_adaptation_pool.py`` into ``data/raw/adaptation/``).

Pool records with status ``labelled`` and exactly one local ``.bin`` whose
SHA256 matches are added. An incident whose logs carry different labels is
dropped entirely. Pool files are hard-linked (or copied) into the stage
directory used by ``training/build_dataset.py``.

Example::

    python training/build_benchmark_v3.py
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--v2", default="data/benchmark/ground_truth_real_v2.json")
    parser.add_argument("--pool", default="data/benchmark/thread_annotations_pool.json")
    parser.add_argument("--pool-dir", default="data/raw/adaptation")
    parser.add_argument("--stage-dir", default="data/raw/benchmark_v1")
    parser.add_argument("--output", default="data/benchmark/ground_truth_real_v3.json")
    args = parser.parse_args()

    v2 = json.loads((ROOT / args.v2).read_text(encoding="utf-8"))
    pool = json.loads((ROOT / args.pool).read_text(encoding="utf-8"))["records"]
    stage = ROOT / args.stage_dir
    stage.mkdir(parents=True, exist_ok=True)

    logs = [dict(entry, origin="v2") for entry in v2["logs"]]
    skipped: Counter[str] = Counter()
    for record in pool:
        if record["status"] != "labelled":
            skipped[record["status"]] += 1
            continue
        if len(record["files"]) != 1:
            skipped["multiple_bins_in_payload"] += 1
            continue
        item = record["files"][0]
        source = ROOT / args.pool_dir / item["file"]
        if not source.exists() or _sha256(source) != item["sha256"]:
            skipped["file_missing_or_hash_mismatch"] += 1
            continue
        target = stage / item["file"]
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
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
                "trainable": True,
                "origin": "pool",
            }
        )

    labels_by_incident: dict[str, set[str]] = defaultdict(set)
    for entry in logs:
        labels_by_incident[entry["incident_id"]].add(entry["labels"][0])
    conflicted = {inc for inc, labels in labels_by_incident.items() if len(labels) > 1}
    kept = [entry for entry in logs if entry["incident_id"] not in conflicted]

    doc = {
        "schema": "logdiagnosis.real-benchmark-ground-truth/v3",
        "label_policy": v2["label_policy"],
        "sources": {"v2": args.v2, "pool": args.pool},
        "logs": kept,
    }
    (ROOT / args.output).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    summary = {
        "logs": len(kept),
        "incidents": len({entry["incident_id"] for entry in kept}),
        "from_v2": sum(entry["origin"] == "v2" for entry in kept),
        "from_pool": sum(entry["origin"] == "pool" for entry in kept),
        "explicit": sum(entry["certainty"] == "explicit" for entry in kept),
        "dropped_conflicted_incidents": sorted(conflicted),
        "pool_skipped": dict(skipped),
        "label_distribution": dict(Counter(entry["labels"][0] for entry in kept)),
        "pool_status_counts": dict(Counter(record["status"] for record in pool)),
    }
    (ROOT / "data/benchmark/benchmark_v3_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
