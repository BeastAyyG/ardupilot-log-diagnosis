#!/usr/bin/env python3
"""Enrich existing crawler manifest with expert-derived labels."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.expert_label_miner import enrich_manifest_with_expert_labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich crawler manifest with developer diagnoses")
    parser.add_argument("--source-root", required=True, help="Folder containing crawler_manifest.csv")
    parser.add_argument("--input-manifest-name", default="crawler_manifest.csv", help="Input manifest filename")
    parser.add_argument("--output-manifest-name", default="crawler_manifest_v2.csv", help="Output manifest filename")
    parser.add_argument("--output-block1-name", default="block1_ardupilot_discuss.csv", help="Output block1 filename")
    parser.add_argument("--sleep-ms", type=int, default=250, help="Delay between topic requests in milliseconds")
    args = parser.parse_args()

    summary = enrich_manifest_with_expert_labels(
        source_root=args.source_root,
        input_manifest_name=args.input_manifest_name,
        output_manifest_name=args.output_manifest_name,
        output_block1_name=args.output_block1_name,
        sleep_ms=args.sleep_ms,
    )

    print("Expert manifest enrichment complete")
    print(f"source_root={summary['source_root']}")
    print(f"rows={summary['rows']}")
    print(f"topics_scanned={summary['topics_scanned']}")
    print(f"topics_with_expert_label={summary['topics_with_expert_label']}")
    print(f"rows_with_label={summary['rows_with_label']}")
    print(f"output_manifest={summary['output_manifest']}")
    print(f"output_block1={summary['output_block1']}")
    print(f"summary_json={summary['summary_json']}")


if __name__ == "__main__":
    main()
