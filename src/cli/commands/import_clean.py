from __future__ import annotations

from argparse import _SubParsersAction


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("import-clean", help="Clean import external log batch with provenance manifests")
    parser.add_argument("--source-root", required=True, help="Source directory to scan")
    parser.add_argument("--output-root", default="data/clean_imports/latest", help="Output directory for cleaned logs and manifests")
    parser.add_argument("--no-copy", action="store_true", help="Generate manifests only, do not copy files")
    parser.set_defaults(func=run)


def run(args) -> None:
    from src.data.clean_import import run_clean_import

    summary = run_clean_import(source_root=args.source_root, output_root=args.output_root, copy_files=not args.no_copy)
    counts = summary.get("counts", {})
    artifacts = summary.get("artifacts", {})
    print("Clean import complete.")
    print(f"Source: {summary.get('source_root')}")
    print(f"Output: {summary.get('output_root')}")
    print(f"Total .bin files: {counts.get('total_bin_files', 0)}")
    print(f"Unique parseable logs: {counts.get('unique_parseable_after_dedupe', 0)}")
    print(f"Verified labeled: {counts.get('verified_labeled', 0)}")
    print(f"Provisional labeled: {counts.get('provisional_labeled', 0)}")
    print(f"Verified unlabeled: {counts.get('verified_unlabeled', 0)}")
    print(f"Rejected non-log: {counts.get('rejected_nonlog', 0)}")
    print(f"Benchmark-trainable: {counts.get('benchmark_trainable', 0)}")
    print(f"Proof markdown: {artifacts.get('proof_markdown')}")
