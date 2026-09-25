"""Package a benchmark release as one zip with a SHA256 manifest.

The bundle holds everything needed to reproduce the paper's numbers except
the raw logs, which are fetched from their public sources with
``training/hydrate_benchmark.py``. It is meant for upload to Zenodo.

Example::

    python training/make_release_bundle.py --version 3.0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RELEASE_FILES = [
    "data/benchmark/README.md",
    "data/benchmark/DATASHEET.md",
    "data/benchmark/SPOT_CHECK.md",
    "data/benchmark/incidents.csv",
    "data/benchmark/registry_summary.json",
    "data/benchmark/benchmark_v3_summary.json",
    "data/benchmark/label_corrections.json",
    "data/benchmark/llm_quote_review.json",
    "data/benchmark/thread_annotations.json",
    "data/benchmark/thread_annotations_pool.json",
    "data/benchmark/hydration_sources.json",
    "data/benchmark/ground_truth_real_v1.json",
    "data/benchmark/ground_truth_real_v2.json",
    "data/benchmark/ground_truth_real_v3.json",
    "data/cohorts/cohort_manifest.json",
    "docs/PREREGISTRATION.md",
    "docs/EVIDENCE_LEDGER.md",
    "CORRECTIONS.md",
    "CITATION.cff",
    "training/hydrate_benchmark.py",
    "training/fetch_adaptation_pool.py",
    "training/paper_eval.py",
]
RELEASE_DIRS = ["data/benchmark/derived_v3", "data/benchmark/results"]


def release_paths(root: Path = ROOT) -> list[str]:
    paths = list(RELEASE_FILES)
    for directory in RELEASE_DIRS:
        paths += sorted(str(p.relative_to(root)) for p in (root / directory).glob("*") if p.is_file())
    missing = [p for p in paths if not (root / p).is_file()]
    if missing:
        raise FileNotFoundError(f"release files missing: {missing}")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--out-dir", default="dist")
    args = parser.parse_args()

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", *RELEASE_FILES, *RELEASE_DIRS],
                                cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
    paths = release_paths()
    manifest = {
        "release": f"benchmark-v{args.version}",
        "commit": commit,
        "dirty": dirty,
        "raw_logs": "not included; run training/hydrate_benchmark.py",
        "files": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
    }
    out = ROOT / args.out_dir / f"ardupilot-log-benchmark-v{args.version}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(ROOT / path, path)
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=1) + "\n")
    print(f"{out.relative_to(ROOT)}: {len(paths)} files, commit {commit[:7]}, dirty={dirty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
