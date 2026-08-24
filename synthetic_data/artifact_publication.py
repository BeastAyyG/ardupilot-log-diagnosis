"""Crash-resistant staging for canonical execution artifacts."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


def stage_log(source: Path, staging: Path) -> tuple[str, int]:
    staging.parent.mkdir(parents=True, exist_ok=True)
    if staging.exists():
        raise FileExistsError(f"staged log already exists: {staging.name}")
    source_size = source.stat().st_size
    digest = hashlib.sha256()
    with source.open("rb") as reader, staging.open("xb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(chunk)
            digest.update(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    if staging.stat().st_size != source_size:
        raise RuntimeError("staged DataFlash size differs from the owned source log")
    return digest.hexdigest(), source_size


def publish_staged_log(staging: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"canonical log already exists: {destination.name}")
    staging.replace(destination)


def quarantine_log(path: Path, quarantine: Path) -> Path | None:
    if not path.exists():
        return None
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    if quarantine.exists():
        raise FileExistsError(f"quarantine artifact already exists: {quarantine.name}")
    try:
        path.replace(quarantine)
    except OSError:
        shutil.copy2(path, quarantine)
        path.unlink()
    return quarantine
