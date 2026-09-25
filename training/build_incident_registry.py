"""Build the real-log incident registry used by the benchmark and paper.

Inputs are committed and hash-checked:

* ``data/cohorts/cohort_manifest.json``: the sealed real-data cohort assignment
  (its ``seal.content_sha256`` is verified before use);
* ``data/benchmark/label_corrections.json``: every label change and why;
* ``data/benchmark/llm_quote_review.json``: a secondary machine review of
  stored quotes; it can only exclude a label its own source contradicts;
* committed ground-truth and candidate manifests, used only for provenance
  notes (expert quotes, usernames, full SHA256 values).

Outputs:

* ``data/benchmark/incidents.csv``: one row per labelled real log, with the
  incident (source thread) it belongs to, label provenance, evidence tier,
  evaluation eligibility and local availability;
* ``data/benchmark/ground_truth_real_v1.json``: the evaluable subset in the
  format ``training/build_dataset.py`` consumes;
* ``data/benchmark/registry_summary.json``: counts used in the paper.

Raw logs are never committed.  With ``--stage-dir`` the script links every
locally available log into one directory under canonical names (hard links, or copies across filesystems) so the dataset
builder can find them.

Example::

    python training/build_incident_registry.py --stage-dir data/raw/benchmark_v1
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.constants import VALID_LABELS  # noqa: E402

LABELLED_COHORTS = ("training_pool", "evaluation_holdout")
DEFAULT_LOG_ROOTS = (
    "data/kaggle_backups/ardupilot-master-log-pool-v2",
    "data/clean_imports/background_expert_01/benchmark_ready/dataset",
    "data/raw",
)
NOTE_SOURCES = (
    "data/final_training_dataset_2026-02-23/ground_truth.json",
    "data/kaggle_backups/ardupilot-master-log-pool-v2/ground_truth.json",
    "data/clean_imports/*/manifests/ground_truth_candidate.json",
    "data/clean_imports/*/benchmark_ready/ground_truth.json",
)
LFS_POINTER_PREFIX = b"version https://git-lfs"


def verify_seal(manifest: dict[str, Any]) -> str:
    """Return the seal digest after checking it matches the manifest content."""
    body = {key: value for key, value in manifest.items() if key != "seal"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    expected = manifest.get("seal", {}).get("content_sha256")
    if digest != expected:
        raise ValueError(f"cohort manifest seal mismatch: {digest} != {expected}")
    return digest


def incident_id_for(url: str) -> str:
    """Group logs by source thread/issue, not by attachment URL."""
    match = re.search(r"discuss\.ardupilot\.org/t/(?:[^/]+/)?(\d+)", url)
    if match:
        return f"discuss:{match.group(1)}"
    match = re.search(r"github\.com/ArduPilot/ardupilot/(issues|files)/(\d+)", url)
    if match:
        return f"github:{match.group(1)}:{match.group(2)}"
    match = re.search(r"drive\.google\.com/drive/folders/([A-Za-z0-9_-]+)", url)
    if match:
        return f"gdrive:{match.group(1)}"
    return f"url:{url}" if url else ""


def _sha256(path: str) -> str | None:
    with open(path, "rb") as handle:
        head = handle.read(len(LFS_POINTER_PREFIX))
        if head == LFS_POINTER_PREFIX:
            return None  # an unfetched Git LFS pointer, not a log
        digest = hashlib.sha256(head)
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_local_logs(roots: list[str], skip_dir: str = "") -> dict[str, str]:
    """Map SHA256 -> path for every real log found under ``roots``."""
    found: dict[str, str] = {}
    skip = str(Path(skip_dir).resolve()) if skip_dir else ""
    for root in roots:
        for path in sorted(glob.glob(os.path.join(root, "**", "*"), recursive=True)):
            if not path.lower().endswith(".bin") or "basic_dataset" in path:
                continue
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            if skip and str(Path(path).resolve()).startswith(skip + os.sep):
                continue
            digest = _sha256(path)
            if digest:
                found.setdefault(digest, path)
    return found


def load_notes(patterns: tuple[str, ...]) -> dict[str, list[dict[str, str]]]:
    """Collect provenance notes keyed by 10-hex SHA256 prefix."""
    notes: dict[str, list[dict[str, str]]] = defaultdict(list)
    for pattern in patterns:
        for path in sorted(glob.glob(str(ROOT / pattern))):
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            entries = data.get("logs", data) if isinstance(data, dict) else data
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict):
                    continue
                sha = str(entry.get("sha256") or "").lower()
                match = re.match(r"([0-9a-f]{10})__", str(entry.get("filename", "")))
                prefix = sha[:10] or (match.group(1) if match else "")
                if not prefix:
                    continue
                notes[prefix].append(
                    {
                        "sha256": sha,
                        "quote": str(entry.get("expert_quote") or "").strip(),
                        "username": str(entry.get("expert_username") or "").strip(),
                        "source": os.path.relpath(path, ROOT),
                    }
                )
    return notes


def evidence_for(prefix: str, notes: dict[str, list[dict[str, str]]]) -> tuple[str, str, str]:
    """Return (tier, supporting text, attribution).

    ``named_user_quote``: a quoted post with a forum username exists; whether
    it actually supports the label still needs human review.
    ``author_summary``: only this project's own paraphrase of the thread.
    ``none``: no supporting text; the label may come from the search query
    that found the log.
    """
    entries = notes.get(prefix, [])
    for entry in entries:
        if entry["quote"] and entry["username"]:
            return "named_user_quote", entry["quote"], entry["username"]
    for entry in entries:
        if entry["quote"]:
            return "author_summary", entry["quote"], ""
    return "none", "", ""


def build(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(Path(args.cohort_manifest).read_text(encoding="utf-8"))
    seal = verify_seal(manifest)
    corrections = json.loads(Path(args.corrections).read_text(encoding="utf-8"))
    removals = {
        item["sha256_prefix"]: item for item in corrections["remove_rule_derived_labels"]
    }
    excluded_incidents = {
        item["incident_id"] for item in corrections["exclude_incidents_from_evaluation"]
    }
    review = {}
    if args.quote_review and Path(args.quote_review).exists():
        review = json.loads(Path(args.quote_review).read_text(encoding="utf-8"))["verdicts"]
    notes = load_notes(NOTE_SOURCES)
    local = index_local_logs(list(args.log_root), skip_dir=args.stage_dir)

    rows: list[dict[str, Any]] = []
    for key, record in sorted(manifest["records"].items()):
        if record["cohort"] not in LABELLED_COHORTS:
            continue
        prefix = key[:10]
        full_sha = key if record["key_quality"] == "sha256" else ""
        if not full_sha:
            full_sha = next(
                (n["sha256"] for n in notes.get(prefix, []) if len(n["sha256"]) == 64), ""
            )
        path = local.get(full_sha) if full_sha else None
        if path is None:
            path = next((p for digest, p in local.items() if digest.startswith(prefix)), None)
            if path is not None and not full_sha:
                full_sha = next(d for d, p in local.items() if p == path)

        original = [label for label in record["labels"] if label in VALID_LABELS]
        corrected = list(original)
        correction = removals.get(prefix)
        if correction and correction["remove"] in corrected:
            corrected.remove(correction["remove"])
        source_url = (record["source_urls"] or [""])[0]
        tier, quote, username = evidence_for(prefix, notes)
        rows.append(
            {
                "log_key": prefix,
                "sha256": full_sha,
                "incident_id": incident_id_for(source_url),
                "source_url": source_url,
                "download_url": (record["download_urls"] or [""])[0],
                "source_type": (record["source_types"] or ["unknown"])[0],
                "cohort_split": record["cohort"],
                "original_labels": "|".join(original),
                "labels": "|".join(corrected),
                "label_correction": correction["reason"] if correction else "",
                "evidence_tier": tier,
                "evidence_user": username,
                "evidence_text": quote[:300],
                "quote_review": review.get(prefix, {}).get("verdict", ""),
                "vehicle": (record.get("metadata") or {}).get("vehicle_type") or "",
                "firmware": (record.get("metadata") or {}).get("firmware_version") or "",
                "licence_status": "unverified",
                "local_available": bool(path),
                "local_path": os.path.relpath(path, ROOT) if path else "",
            }
        )

    labels_by_incident: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        labels_by_incident[row["incident_id"]].add(row["labels"])
    for row in rows:
        reasons = []
        if "|" in row["labels"] or not row["labels"]:
            reasons.append("not_single_label")
        if len(labels_by_incident[row["incident_id"]]) > 1:
            reasons.append("incident_label_conflict")
        if row["incident_id"] in excluded_incidents:
            reasons.append("contaminated_incident")
        if row["quote_review"] == "contradicted":
            reasons.append("label_contradicted_by_source")
        row["exclusion_reason"] = "|".join(reasons)
        row["evaluable"] = not reasons
        name = Path(row["local_path"]).name
        if row["local_available"] and not name.startswith(f"{row['log_key']}__"):
            name = f"{row['log_key']}__{name}"
        row["staged_filename"] = name if row["local_available"] else ""

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with (out_dir / "incidents.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    ground_truth = {
        "schema": "logdiagnosis.real-benchmark-ground-truth/v1",
        "cohort_manifest_seal": seal,
        "label_policy": corrections["policy"],
        "logs": [
            {
                "filename": row["staged_filename"],
                "labels": [row["labels"]],
                "incident_id": row["incident_id"],
                "source_url": row["source_url"],
                "source_type": row["source_type"],
                "sha256": row["sha256"],
                "cohort_split": row["cohort_split"],
                "evidence_tier": row["evidence_tier"],
                "confidence": "medium",
                "trainable": True,
            }
            for row in rows
            if row["evaluable"] and row["local_available"]
        ],
    }
    (out_dir / "ground_truth_real_v1.json").write_text(
        json.dumps(ground_truth, indent=2) + "\n", encoding="utf-8"
    )

    if args.stage_dir:
        stage = Path(args.stage_dir)
        stage.mkdir(parents=True, exist_ok=True)
        for row in rows:
            if not row["local_available"]:
                continue
            # Hard link (or copy) rather than symlink: the dataset builder
            # refuses paths that resolve outside its dataset directory.
            target = stage / row["staged_filename"]
            if target.is_symlink() or target.exists():
                target.unlink()
            source = ROOT / row["local_path"]
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)

    evaluable = [row for row in rows if row["evaluable"]]
    usable = [row for row in evaluable if row["local_available"]]
    summary = {
        "cohort_manifest_seal": seal,
        "labelled_real_logs": len(rows),
        "labelled_real_incidents": len(labels_by_incident),
        "locally_available_logs": sum(row["local_available"] for row in rows),
        "evaluable_logs": len(evaluable),
        "evaluable_and_available_logs": len(usable),
        "evaluable_and_available_incidents": len({row["incident_id"] for row in usable}),
        "labels_corrected": sum(bool(row["label_correction"]) for row in rows),
        "exclusions": dict(
            Counter(r for row in rows for r in row["exclusion_reason"].split("|") if r)
        ),
        "evidence_tiers_usable": dict(Counter(row["evidence_tier"] for row in usable)),
        "quote_review_usable": dict(Counter(row["quote_review"] or "unreviewed" for row in usable)),
        "label_distribution_usable_logs": dict(Counter(row["labels"] for row in usable)),
        "label_distribution_usable_incidents": dict(
            Counter(
                label
                for label, _ in {(row["labels"], row["incident_id"]) for row in usable}
            )
        ),
        "missing_logs": [
            {"log_key": row["log_key"], "source_url": row["source_url"]}
            for row in rows
            if not row["local_available"]
        ],
    }
    (out_dir / "registry_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cohort-manifest", default="data/cohorts/cohort_manifest.json")
    parser.add_argument("--corrections", default="data/benchmark/label_corrections.json")
    parser.add_argument("--quote-review", default="data/benchmark/llm_quote_review.json")
    parser.add_argument("--log-root", action="append", default=None)
    parser.add_argument("--output-dir", default="data/benchmark")
    parser.add_argument("--stage-dir", default="")
    args = parser.parse_args()
    args.log_root = args.log_root or list(DEFAULT_LOG_ROOTS)
    print(json.dumps(build(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
