from __future__ import annotations

import os
import sys
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

    root = project_root()
    candidates = (
        root / "models",
        root / "share" / "ardupilot-log-diagnosis" / "models",
        Path(sys.prefix) / "share" / "ardupilot-log-diagnosis" / "models",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    # Preserve the development-tree location in error messages when artifacts
    # are genuinely unavailable.
    return (root / "models").resolve()


MODELS_DIR = default_models_dir()
KNOWN_FAILURES_PATH = MODELS_DIR / "known_failures.json"
