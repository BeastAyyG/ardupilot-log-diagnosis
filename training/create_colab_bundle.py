#!/usr/bin/env python3
"""Create a compressed data bundle for Google Colab runs."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _resolve_output(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def _collect_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for rel in paths:
        item = ROOT_DIR / rel
        if not item.exists():
            raise FileNotFoundError(f"Path not found: {item}")
        if item.is_file():
            files.append(item)
            continue
        for child in sorted(item.rglob("*")):
            if child.is_file():
                files.append(child)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a tar.gz bundle for Colab")
    parser.add_argument(
        "--output",
        default="colab_data_bundle.tar.gz",
        help="Output tar.gz path (absolute or repo-relative)",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=["data/final_training_dataset_2026-02-23"],
        help="Repo-relative files/directories to include in the bundle",
    )
    args = parser.parse_args()

    output_path = _resolve_output(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files = _collect_files(args.paths)
    if not files:
        raise RuntimeError("No files selected for bundle")

    total_bytes = 0
    with tarfile.open(output_path, "w:gz") as tar:
        for file_path in files:
            arcname = file_path.relative_to(ROOT_DIR)
            tar.add(file_path, arcname=str(arcname))
            total_bytes += file_path.stat().st_size

    print("Created Colab bundle")
    print(f"output={output_path}")
    print(f"file_count={len(files)}")
    print(f"total_bytes={total_bytes}")
    print("Upload this bundle to Google Drive, then extract in Colab:")
    print(f"tar -xzf {output_path.name}")


if __name__ == "__main__":
    main()
