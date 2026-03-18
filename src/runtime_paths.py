from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_repo_path(path: str | os.PathLike[str]) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (project_root() / candidate).resolve()


def default_models_dir() -> Path:
    override = os.environ.get("ARDUPILOT_DIAGNOSIS_MODEL_DIR")
    if override:
        return resolve_repo_path(override)
    return (project_root() / "models").resolve()


MODELS_DIR = default_models_dir()
KNOWN_FAILURES_PATH = MODELS_DIR / "known_failures.json"
