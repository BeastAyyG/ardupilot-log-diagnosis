"""Clean import pipeline for external flight-log batches.

This module ingests a single source folder, validates files, deduplicates by
hash, classifies provenance quality, and emits audit artifacts suitable for
benchmark reporting.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from pymavlink import DFReader

MANIFEST_FILES = [
    "crawler_manifest.csv",
    "crawler_manifest_v2.csv",
    "fast_mode_manifest.csv",
    "download_manifest.csv",
]

MANIFEST_PRIORITY = {
    "crawler_manifest_v2.csv": 0,
    "crawler_manifest.csv": 1,
    "fast_mode_manifest.csv": 2,
    "download_manifest.csv": 3,
}

BLOCK1_FILE = "block1_ardupilot_discuss.csv"

LABEL_MAP = {
    "VIBE_HIGH": "vibration_high",
    "MAG_INTERFERENCE": "compass_interference",
}

PROVISIONAL_LABELS = {
    "ESC_DESYNC",
}

BIN_SIGNATURES = {
    b"\x89PNG": "png",
    b"GIF8": "gif",
    b"\xff\xd8\xff": "jpg",
    b"%PDF": "pdf",
}


@dataclass
class FileRecord:
    source_path: Path
    rel_path: str
    file_name: str
    extension: str
    size_bytes: int
    sha256: str
    signature: str
    parse_ok: bool
    parse_message_count: int
    parse_message_types: int
    parse_error: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _detect_signature(path: Path) -> str:
    with path.open("rb") as f:
        first = f.read(16)

    if not first:
        return "empty"

    if first.startswith(b"<"):
        return "html"

    for sig, name in BIN_SIGNATURES.items():
        if first.startswith(sig):
            return name

    return "binlike"


def _parse_probe(path: Path, max_messages: int = 3000) -> Tuple[bool, int, int, str]:
    try:
        reader = DFReader.DFReader_binary(str(path))
        count = 0
        types = set()
        while count < max_messages:
            msg = reader.recv_msg()
            if msg is None:
                break
            count += 1
            types.add(msg.get_type())
        if count == 0:
            return False, 0, 0, "no messages decoded"
        return True, count, len(types), ""
    except Exception as exc:
        return False, 0, 0, str(exc)


def _read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_provenance(source_root: Path) -> Dict[str, List[dict]]:
    by_saved_file: Dict[str, List[dict]] = defaultdict(list)

    for manifest_name in MANIFEST_FILES:
        rows = _read_csv(source_root / manifest_name)
        for row in rows:
            saved_file = (row.get("saved_file") or "").strip()
            if not saved_file:
                continue

            label = (
                (row.get("label") or row.get("normalized_label") or "")
                .strip()
                .upper()
            )
            source_type = (row.get("source_type") or "").strip()
            thread_url = (
                row.get("thread_url")
                or row.get("input_link")
                or row.get("seed_link")
                or ""
            ).strip()
            resolved_url = (
                row.get("used_url_or_error")
                or row.get("resolved_url")
                or ""
            ).strip()

            by_saved_file[saved_file].append(
                {
                    "manifest": manifest_name,
                    "status": (row.get("status") or "").strip().lower(),
                    "label_raw": label,
                    "source_type": source_type,
                    "thread_url": thread_url,
                    "resolved_url": resolved_url,
                }
            )

    return by_saved_file


def _load_expert_map(source_root: Path) -> Dict[str, dict]:
    rows = _read_csv(source_root / BLOCK1_FILE)
    by_thread: Dict[str, dict] = {}
    for row in rows:
        thread = (row.get("Thread_URL") or "").strip()
        if not thread:
            continue
        by_thread[thread] = {
            "expert_username": (row.get("Expert_Username") or "").strip(),
            "expert_quote": (row.get("Diagnostic_Quote") or "").strip(),
            "normalized_label": (row.get("Normalized_Label") or "").strip().upper(),
        }
    return by_thread


def _dedupe_records(records: Iterable[dict]) -> List[dict]:
    seen = set()
    out = []
    for rec in records:
        key = (
            rec.get("manifest", ""),
            rec.get("status", ""),
            rec.get("label_raw", ""),
            rec.get("source_type", ""),
            rec.get("thread_url", ""),
            rec.get("resolved_url", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def _choose_provenance(records: List[dict]) -> Optional[dict]:
    downloaded = [r for r in records if r.get("status") == "downloaded"]
    if not downloaded:
        return None

    def rank(rec: dict) -> Tuple[int, int, int]:
        manifest_rank = MANIFEST_PRIORITY.get(rec.get("manifest", ""), 99)
        has_discuss_thread = 0 if "discuss.ardupilot.org" in rec.get("thread_url", "") else 1
        has_label = 0 if rec.get("label_raw") else 1
        return manifest_rank, has_discuss_thread, has_label

    downloaded.sort(key=rank)
    return downloaded[0]


def _safe_copy(src: Path, dst_dir: Path, sha256: str) -> str:
    dst_dir.mkdir(parents=True, exist_ok=True)
    target = dst_dir / src.name

    if target.exists():
        if _sha256(target) == sha256:
            return target.name
        target = dst_dir / f"{src.stem}_{sha256[:8]}{src.suffix}"

    shutil.copy2(src, target)
    return target.name


def _write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _collect_files(source_root: Path) -> Tuple[List[Path], List[Path]]:
    bins = sorted([p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() == ".bin"])
    zips = sorted([p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() == ".zip"])
    return bins, zips


def run_clean_import(
    source_root: str,
    output_root: str,
    copy_files: bool = True,
) -> dict:
    src = Path(source_root).resolve()
    out = Path(output_root).resolve()
    manifests_dir = out / "manifests"
    logs_dir = out / "logs"

    if not src.exists():
        raise FileNotFoundError(f"Source folder not found: {src}")

    def src_rel(path: Path) -> str:
        return str(path.relative_to(src))

    def out_rel(path: Path) -> str:
        try:
            return str(path.relative_to(Path.cwd()))
        except Exception:
            return str(path)

    provenance_by_name = _load_provenance(src)
    expert_by_thread = _load_expert_map(src)

    bin_files, zip_files = _collect_files(src)

    source_inventory: List[dict] = []
    scanned_bin_records: List[FileRecord] = []
    rejected_rows: List[dict] = []

    for path in bin_files:
        signature = _detect_signature(path)
        parse_ok = False
        parse_count = 0
        parse_types = 0
        parse_error = ""
        if signature == "binlike":
            parse_ok, parse_count, parse_types, parse_error = _parse_probe(path)

        record = FileRecord(
            source_path=path,
            rel_path=str(path.relative_to(src)),
            file_name=path.name,
            extension=path.suffix.lower(),
            size_bytes=path.stat().st_size,
            sha256=_sha256(path),
            signature=signature,
            parse_ok=parse_ok,
            parse_message_count=parse_count,
            parse_message_types=parse_types,
            parse_error=parse_error,
        )
        scanned_bin_records.append(record)

        source_inventory.append(
            {
                "source_path": src_rel(path),
                "relative_path": record.rel_path,
                "file_name": record.file_name,
                "kind": "bin",
                "size_bytes": record.size_bytes,
                "sha256": record.sha256,
                "signature": record.signature,
                "parse_ok": record.parse_ok,
                "parse_message_count": record.parse_message_count,
                "parse_message_types": record.parse_message_types,
                "parse_error": record.parse_error,
            }
        )

        if signature != "binlike":
            rejected_rows.append(
                {
                    "source_path": src_rel(path),
                    "file_name": path.name,
                    "reason": f"not a dataflash log ({signature})",
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                }
            )

    for path in zip_files:
        zip_sha = _sha256(path)
        source_inventory.append(
            {
                "source_path": src_rel(path),
                "relative_path": str(path.relative_to(src)),
                "file_name": path.name,
                "kind": "zip",
                "size_bytes": path.stat().st_size,
                "sha256": zip_sha,
                "signature": "archive",
                "parse_ok": False,
                "parse_message_count": 0,
                "parse_message_types": 0,
                "parse_error": "archive",
            }
        )

    parseable = [r for r in scanned_bin_records if r.signature == "binlike" and r.parse_ok]
    by_hash: Dict[str, List[FileRecord]] = defaultdict(list)
    for rec in parseable:
        by_hash[rec.sha256].append(rec)

    clean_rows: List[dict] = []
    gt_candidate_logs: List[dict] = []

    categories = {
        "verified_labeled": [],
        "provisional_labeled": [],
        "verified_unlabeled": [],
        "excluded_synthetic": [],
    }

    for sha, records in sorted(by_hash.items(), key=lambda item: item[0]):
        canonical = sorted(records, key=lambda r: (len(r.rel_path), r.rel_path))[0]

        prov_records = []
        for rec in records:
            prov_records.extend(provenance_by_name.get(rec.file_name, []))
        prov_records = _dedupe_records(prov_records)
        selected = _choose_provenance(prov_records)

        raw_label = (selected or {}).get("label_raw", "")
        mapped_label = LABEL_MAP.get(raw_label, "")
        source_type = (selected or {}).get("source_type", "unknown")
        thread_url = (selected or {}).get("thread_url", "")
        resolved_url = (selected or {}).get("resolved_url", "")
        status = (selected or {}).get("status", "")

        if source_type.upper() == "SITL_SIMULATION":
            category = "excluded_synthetic"
            trainable = False
        elif mapped_label:
            category = "verified_labeled"
            trainable = True
        elif raw_label in PROVISIONAL_LABELS:
            category = "provisional_labeled"
            trainable = False
        else:
            category = "verified_unlabeled"
            trainable = False

        expert_username = ""
        expert_quote = ""
        if thread_url in expert_by_thread:
            expert_username = expert_by_thread[thread_url].get("expert_username", "")
            expert_quote = expert_by_thread[thread_url].get("expert_quote", "")

        imported_name = canonical.file_name
        if copy_files:
            imported_name = _safe_copy(
                canonical.source_path,
                logs_dir / category,
                canonical.sha256,
            )

        category_item = {
            "category": category,
            "file_name": imported_name,
            "source_path": src_rel(canonical.source_path),
            "source_relative_path": canonical.rel_path,
            "size_bytes": canonical.size_bytes,
            "sha256": canonical.sha256,
            "duplicate_count": len(records),
            "duplicate_sources": [src_rel(r.source_path) for r in records],
            "raw_label": raw_label,
            "mapped_label": mapped_label,
            "trainable": trainable,
            "source_type": source_type,
            "source_url": thread_url,
            "resolved_download_url": resolved_url,
            "provenance_status": status,
            "provenance_records": prov_records,
            "expert_username": expert_username,
            "expert_quote": expert_quote,
            "parse_message_count": canonical.parse_message_count,
            "parse_message_types": canonical.parse_message_types,
        }
        categories[category].append(category_item)
        clean_rows.append(category_item)

        gt_entry = {
            "filename": imported_name,
            "labels": [mapped_label] if mapped_label else [],
            "source_url": thread_url,
            "source_type": source_type or "unknown",
            "expert_quote": expert_quote,
            "confidence": "medium" if mapped_label else "low",
            "raw_label": raw_label,
            "trainable": trainable,
            "category": category,
            "sha256": canonical.sha256,
            "expert_username": expert_username,
        }
        gt_candidate_logs.append(gt_entry)

    zip_by_hash: Dict[str, List[Path]] = defaultdict(list)
    for zip_path in zip_files:
        zip_sha = _sha256(zip_path)
        zip_by_hash[zip_sha].append(zip_path)

    for zip_sha, paths in sorted(zip_by_hash.items(), key=lambda item: item[0]):
        canonical_zip = sorted(paths, key=lambda p: (len(str(p.relative_to(src))), str(p.relative_to(src))))[0]

        zip_prov_records = []
        for path in paths:
            zip_prov_records.extend(provenance_by_name.get(path.name, []))
        zip_prov_records = _dedupe_records(zip_prov_records)
        selected_zip = _choose_provenance(zip_prov_records)

        source_type = (selected_zip or {}).get("source_type", "unknown")
        category = "excluded_synthetic" if source_type.upper() == "SITL_SIMULATION" else "excluded_archive"

        imported_name = canonical_zip.name
        if copy_files:
            imported_name = _safe_copy(canonical_zip, logs_dir / category, zip_sha)

        clean_rows.append(
            {
                "category": category,
                "file_name": imported_name,
                "source_path": src_rel(canonical_zip),
                "source_relative_path": str(canonical_zip.relative_to(src)),
                "size_bytes": canonical_zip.stat().st_size,
                "sha256": zip_sha,
                "duplicate_count": len(paths),
                "duplicate_sources": [src_rel(p) for p in paths],
                "raw_label": (selected_zip or {}).get("label_raw", ""),
                "mapped_label": "",
                "trainable": False,
                "source_type": source_type,
                "source_url": (selected_zip or {}).get("thread_url", ""),
                "resolved_download_url": (selected_zip or {}).get("resolved_url", ""),
                "provenance_status": (selected_zip or {}).get("status", ""),
                "provenance_records": zip_prov_records,
                "expert_username": "",
                "expert_quote": "",
                "parse_message_count": 0,
                "parse_message_types": 0,
            }
        )

    benchmark_logs = [
        {
            "filename": item["file_name"],
            "labels": [item["mapped_label"]],
            "source_url": item["source_url"],
            "source_type": item["source_type"],
            "expert_quote": item["expert_quote"],
            "confidence": "medium",
        }
        for item in categories["verified_labeled"]
        if item["mapped_label"]
    ]

    benchmark_metadata = {
        "description": "Benchmark-ready subset generated from clean import",
        "source_batch": src.name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_logs": len(benchmark_logs),
        "label_distribution": {
            label: sum(1 for row in benchmark_logs if label in row["labels"])
            for label in sorted({row["labels"][0] for row in benchmark_logs})
        },
        "policy": {
            "exclude_synthetic": True,
            "exclude_provisional_labels": True,
            "exclude_unlabeled": True,
            "provisional_labels": sorted(PROVISIONAL_LABELS),
        },
    }

    benchmark_dir = out / "benchmark_ready"
    benchmark_dataset_dir = benchmark_dir / "dataset"
    if copy_files:
        benchmark_dataset_dir.mkdir(parents=True, exist_ok=True)
        for item in categories["verified_labeled"]:
            src_file = logs_dir / "verified_labeled" / item["file_name"]
            _safe_copy(src_file, benchmark_dataset_dir, item["sha256"])

    benchmark_gt = {
        "metadata": benchmark_metadata,
        "logs": benchmark_logs,
    }

    manifests_dir.mkdir(parents=True, exist_ok=True)

    source_inventory_csv = manifests_dir / "source_inventory.csv"
    source_inventory_json = manifests_dir / "source_inventory.json"
    clean_manifest_csv = manifests_dir / "clean_import_manifest.csv"
    clean_manifest_json = manifests_dir / "clean_import_manifest.json"
    rejected_manifest_csv = manifests_dir / "rejected_manifest.csv"
    gt_candidate_path = manifests_dir / "ground_truth_candidate.json"
    benchmark_gt_path = benchmark_dir / "ground_truth.json"
    proof_md_path = manifests_dir / "provenance_proof.md"

    source_inventory_fieldnames = [
        "source_path",
        "relative_path",
        "file_name",
        "kind",
        "size_bytes",
        "sha256",
        "signature",
        "parse_ok",
        "parse_message_count",
        "parse_message_types",
        "parse_error",
    ]
    _write_csv(source_inventory_csv, source_inventory, source_inventory_fieldnames)
    source_inventory_json.write_text(json.dumps(source_inventory, indent=2) + "\n")

    clean_fieldnames = [
        "category",
        "file_name",
        "source_path",
        "source_relative_path",
        "size_bytes",
        "sha256",
        "duplicate_count",
        "raw_label",
        "mapped_label",
        "trainable",
        "source_type",
        "source_url",
        "resolved_download_url",
        "provenance_status",
        "expert_username",
        "expert_quote",
        "parse_message_count",
        "parse_message_types",
    ]

    clean_rows_csv = []
    for row in clean_rows:
        csv_row = {k: row.get(k, "") for k in clean_fieldnames}
        csv_row["trainable"] = "true" if row.get("trainable") else "false"
        clean_rows_csv.append(csv_row)
    _write_csv(clean_manifest_csv, clean_rows_csv, clean_fieldnames)
    clean_manifest_json.write_text(json.dumps(clean_rows, indent=2) + "\n")

    rejected_fieldnames = ["source_path", "file_name", "reason", "sha256", "size_bytes"]
    _write_csv(rejected_manifest_csv, rejected_rows, rejected_fieldnames)

    gt_candidate_payload = {
        "metadata": {
            "description": "Candidate ground truth generated from clean import",
            "source_batch": src.name,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "policy": {
                "provisional_labels": sorted(PROVISIONAL_LABELS),
                "mapped_labels": LABEL_MAP,
                "trainable_only_for_mapped_labels": True,
            },
        },
        "logs": gt_candidate_logs,
    }
    gt_candidate_path.write_text(json.dumps(gt_candidate_payload, indent=2) + "\n")

    benchmark_dir.mkdir(parents=True, exist_ok=True)
    benchmark_gt_path.write_text(json.dumps(benchmark_gt, indent=2) + "\n")

    summary = {
        "source_root": str(src),
        "output_root": out_rel(out),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "total_bin_files": len(bin_files),
            "parseable_bin_files": len(parseable),
            "unique_parseable_after_dedupe": len(by_hash),
            "rejected_nonlog": len(rejected_rows),
            "zip_files": len(zip_files),
            "unique_zip_files": len(zip_by_hash),
            "verified_labeled": len(categories["verified_labeled"]),
            "provisional_labeled": len(categories["provisional_labeled"]),
            "verified_unlabeled": len(categories["verified_unlabeled"]),
            "benchmark_trainable": len(benchmark_logs),
        },
        "artifacts": {
            "source_inventory_csv": out_rel(source_inventory_csv),
            "source_inventory_json": out_rel(source_inventory_json),
            "clean_import_manifest_csv": out_rel(clean_manifest_csv),
            "clean_import_manifest_json": out_rel(clean_manifest_json),
            "rejected_manifest_csv": out_rel(rejected_manifest_csv),
            "ground_truth_candidate_json": out_rel(gt_candidate_path),
            "benchmark_ground_truth_json": out_rel(benchmark_gt_path),
            "proof_markdown": out_rel(proof_md_path),
        },
    }

    proof_lines = [
        "# Benchmark Data Provenance",
        "",
        f"- Source folder: `{src}`",
        f"- Generated at (UTC): `{summary['generated_at_utc']}`",
        f"- Total `.bin` files scanned: **{summary['counts']['total_bin_files']}**",
        f"- Parse-valid `.bin` files (pre-dedupe): **{summary['counts']['parseable_bin_files']}**",
        f"- Unique parse-valid files (SHA256 dedupe): **{summary['counts']['unique_parseable_after_dedupe']}**",
        f"- Rejected non-log `.bin` files: **{summary['counts']['rejected_nonlog']}**",
        f"- Provisional labeled files (not trainable): **{summary['counts']['provisional_labeled']}**",
        f"- Unlabeled files (manual review): **{summary['counts']['verified_unlabeled']}**",
        f"- Benchmark-trainable files: **{summary['counts']['benchmark_trainable']}**",
        "",
        "## Policy",
        "- No synthetic/SITL logs used for production benchmark training.",
        "- Provisional labels are excluded from trainable benchmark set.",
        "- Only mapped labels are included in benchmark-ready ground truth.",
        "",
        "## Verified Labeled Logs",
        "| File | Raw Label | Mapped Label | Thread URL | Download URL | SHA256 |",
        "|---|---|---|---|---|---|",
    ]

    for item in sorted(categories["verified_labeled"], key=lambda x: x["file_name"]):
        proof_lines.append(
            "| "
            f"`{item['file_name']}` | {item['raw_label']} | {item['mapped_label']} | "
            f"{item['source_url']} | {item['resolved_download_url']} | `{item['sha256']}` |"
        )

    proof_lines.extend(
        [
            "",
            "## Provisional Labels",
            "| File | Raw Label | Reason | Thread URL | SHA256 |",
            "|---|---|---|---|---|",
        ]
    )
    for item in sorted(categories["provisional_labeled"], key=lambda x: x["file_name"]):
        proof_lines.append(
            "| "
            f"`{item['file_name']}` | {item['raw_label']} | label not in production taxonomy | "
            f"{item['source_url']} | `{item['sha256']}` |"
        )

    if categories["verified_unlabeled"]:
        proof_lines.extend(
            [
                "",
                "## Unlabeled Valid Logs",
                "| File | Source Path | SHA256 |",
                "|---|---|---|",
            ]
        )
        for item in sorted(categories["verified_unlabeled"], key=lambda x: x["file_name"]):
            proof_lines.append(
                "| "
                f"`{item['file_name']}` | `{item['source_relative_path']}` | `{item['sha256']}` |"
            )

    proof_lines.extend(
        [
            "",
            "## Excluded SITL Sources",
            "- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip",
            "- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip",
            "- https://github.com/ArduPilot/ardupilot/issues/24445",
            "",
        "## Generated Artifacts",
            f"- `{out_rel(source_inventory_csv)}`",
            f"- `{out_rel(clean_manifest_csv)}`",
            f"- `{out_rel(rejected_manifest_csv)}`",
            f"- `{out_rel(gt_candidate_path)}`",
            f"- `{out_rel(benchmark_gt_path)}`",
        ]
    )

    proof_md_path.write_text("\n".join(proof_lines) + "\n")

    summary_path = manifests_dir / "import_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    summary["artifacts"]["summary_json"] = str(summary_path)

    return summary
