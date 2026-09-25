"""Download the raw logs of a benchmark release from their public sources.

The release does not redistribute raw logs (their licence is unverified). It
ships each log's source URL and SHA256 instead. This script fetches every log
listed in a ground-truth file, checks its SHA256 and writes it to a git-ignored
directory. Logs whose download fails or no longer matches are reported, never
silently replaced.

Example::

    python training/hydrate_benchmark.py \\
        --ground-truth data/benchmark/ground_truth_real_v3.json \\
        --out data/raw/hydrated_v3
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.fetch_adaptation_pool import _download  # noqa: E402


def download_urls(root: Path = ROOT) -> dict[str, str]:
    """Map full log SHA256 to its public download URL."""
    urls = {}
    with (root / "data/benchmark/incidents.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["download_url"]:
                urls[row["sha256"]] = row["download_url"]
    pool = json.loads((root / "data/benchmark/thread_annotations_pool.json").read_text())
    for record in pool["records"]:
        for item in record.get("files", []):
            if record.get("download_url"):
                urls[item["sha256"]] = record["download_url"]
    extra = json.loads((root / "data/benchmark/hydration_sources.json").read_text())
    for source in extra["sources"]:
        urls.setdefault(source["sha256"], source["download_url"])
    return urls


def extract_matching(payload: bytes, sha256: str) -> bytes | None:
    """Return the log in ``payload`` (raw or zipped) whose SHA256 matches."""
    if hashlib.sha256(payload).hexdigest() == sha256:
        return payload
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                data = archive.read(info)
                if hashlib.sha256(data).hexdigest() == sha256:
                    return data
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ground-truth", default="data/benchmark/ground_truth_real_v3.json")
    parser.add_argument("--out", default="data/raw/hydrated_v3")
    args = parser.parse_args()

    logs = json.loads((ROOT / args.ground_truth).read_text())["logs"]
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    urls = download_urls()
    report = []
    for entry in logs:
        sha, target = entry["sha256"], out / entry["filename"]
        status = "ok"
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
            status = "already_present"
        elif sha not in urls:
            status = "no_public_url"
        else:
            try:
                data = extract_matching(_download(urls[sha]), sha)
            except Exception as exc:  # noqa: BLE001
                data, status = None, f"download_failed: {str(exc)[:80]}"
            if data is None and status == "ok":
                status = "sha256_mismatch"
            if data is not None:
                target.write_bytes(data)
            time.sleep(0.5)
        report.append({"filename": entry["filename"], "sha256": sha, "status": status})
        print(f"{status:20s} {entry['filename']}")
    (out / "hydration_report.json").write_text(json.dumps(report, indent=1) + "\n")
    missing = [r for r in report if r["status"] not in {"ok", "already_present"}]
    print(f"{len(report) - len(missing)}/{len(report)} logs hydrated and hash-verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
