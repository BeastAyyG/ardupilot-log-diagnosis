#!/usr/bin/env python3
"""Run clean import for external flight-log batches."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.clean_import import run_clean_import


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean import external flight-log dataset with provenance")
    parser.add_argument("--source-root", required=True, help="Source folder containing downloaded logs and manifests")
    parser.add_argument(
        "--output-root",
        default="data/clean_imports/latest",
        help="Output directory for categorized logs and generated manifests",
    )
    parser.add_argument("--no-copy", action="store_true", help="Generate manifests only without copying files")

    args = parser.parse_args()

    summary = run_clean_import(
        source_root=args.source_root,
        output_root=args.output_root,
        copy_files=not args.no_copy,
    )

    counts = summary["counts"]
    artifacts = summary["artifacts"]
    print("Clean import complete")
    print(f"source_root={summary['source_root']}")
    print(f"output_root={summary['output_root']}")
    print(f"total_bin_files={counts['total_bin_files']}")
    print(f"unique_parseable_after_dedupe={counts['unique_parseable_after_dedupe']}")
    print(f"verified_labeled={counts['verified_labeled']}")
    print(f"provisional_labeled={counts['provisional_labeled']}")
    print(f"verified_unlabeled={counts['verified_unlabeled']}")
    print(f"benchmark_trainable={counts['benchmark_trainable']}")
    print(f"proof_markdown={artifacts['proof_markdown']}")


if __name__ == "__main__":
    main()
