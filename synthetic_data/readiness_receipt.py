"""Reproducible, non-promoting receipts for an exact dirty source snapshot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .contracts import validate_contract
from .schema import canonical_json_bytes, sha256_bytes

READINESS_SCHEMA = "logdiagnosis.code-readiness-receipt/v1"
SNAPSHOT_SCHEMA = "logdiagnosis.git-dirty-snapshot/v1"
RECORDED_PACKAGES = ("joblib", "numpy", "pandas", "pymavlink", "pytest", "ruff", "scikit-learn", "xgboost")


def _git(root: Path, *arguments: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=60.0,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def _decode_paths(payload: bytes) -> list[str]:
    try:
        paths = [item.decode("utf-8") for item in payload.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise ValueError("Git returned a path that is not valid UTF-8") from exc
    if len(paths) != len(set(paths)):
        raise ValueError("Git returned duplicate source paths")
    return paths


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_inside(root: Path, relative: str) -> Path:
    if not relative or "\0" in relative:
        raise ValueError("source snapshot contains an invalid path")
    candidate = root / Path(relative)
    resolved_root = root.resolve()
    resolved_parent = candidate.parent.resolve()
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"source path escapes repository: {relative}") from exc
    return candidate


def _index_entries(root: Path) -> dict[str, list[dict[str, Any]]]:
    entries: dict[str, list[dict[str, Any]]] = {}
    raw = _git(root, "ls-files", "--stage", "-z")
    for record in (item for item in raw.split(b"\0") if item):
        try:
            header, raw_path = record.split(b"\t", 1)
            mode, oid, stage = header.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("Git returned a malformed index entry") from exc
        entries.setdefault(path, []).append(
            {"mode": mode, "object_id": oid.lower(), "stage": int(stage)}
        )
    return entries


def _status_records(root: Path, exclusions: set[str]) -> list[dict[str, str]]:
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    parts = [item for item in raw.split(b"\0") if item]
    records: list[dict[str, str]] = []
    index = 0
    while index < len(parts):
        record = parts[index]
        index += 1
        if len(record) < 4 or record[2:3] != b" ":
            raise ValueError("Git returned malformed porcelain status")
        try:
            code = record[:2].decode("ascii")
            path = record[3:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Git returned a non-UTF-8 status path") from exc
        item = {"code": code, "path": Path(path).as_posix()}
        if "R" in code or "C" in code:
            if index >= len(parts):
                raise ValueError("Git returned an incomplete rename status")
            try:
                original = parts[index].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("Git returned a non-UTF-8 rename path") from exc
            index += 1
            item["original_path"] = Path(original).as_posix()
        if item["path"] not in exclusions:
            records.append(item)
    return records


def _submodule_identity(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"kind": "missing"}
    top_level = _git(path, "rev-parse", "--show-toplevel", check=False)
    if top_level:
        reported_root = Path(top_level.decode("utf-8").strip()).resolve()
        if reported_root == path.resolve():
            return {
                "kind": "submodule",
                "snapshot": collect_source_snapshot(path),
            }
    entries: list[dict[str, Any]] = []

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = child.relative_to(path).as_posix()
            if child.is_symlink():
                entries.append({"path": relative, **_working_identity(child, [])})
            elif child.is_dir():
                entries.append({"path": relative, "kind": "directory"})
                visit(child)
            elif child.is_file():
                entries.append({"path": relative, **_working_identity(child, [])})
            else:
                raise ValueError(f"unsupported gitlink entry: {child}")

    visit(path)
    return {"kind": "uninitialized_gitlink", "entries": entries}


def _working_identity(path: Path, index: list[dict[str, Any]]) -> dict[str, Any]:
    if index and any(item["mode"] == "160000" for item in index):
        return _submodule_identity(path)
    if not os.path.lexists(path):
        return {"kind": "missing"}
    if path.is_symlink():
        target = os.readlink(path)
        encoded = target.encode("utf-8")
        return {
            "kind": "symlink",
            "size": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
    if not path.is_file():
        raise ValueError(f"source entry is not a regular file: {path}")
    return {"kind": "file", "size": path.stat().st_size, "sha256": _sha256_file(path)}


def collect_source_snapshot(
    root: str | Path, *, excluded_paths: Iterable[str] = ()
) -> dict[str, Any]:
    """Bind Git HEAD/index plus every tracked and non-ignored untracked byte."""

    repository = Path(root).resolve()
    if not (repository / ".git").exists() and not _git(
        repository, "rev-parse", "--git-dir", check=False
    ):
        raise ValueError("source root is not a Git worktree")
    exclusions = sorted({Path(item).as_posix() for item in excluded_paths})
    if any(item.startswith("../") or item.startswith("/") for item in exclusions):
        raise ValueError("snapshot exclusions must be repository-relative paths")
    index = _index_entries(repository)
    paths = _decode_paths(
        _git(repository, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    )
    entries = []
    for relative in sorted(set(paths) - set(exclusions)):
        path = _resolve_inside(repository, relative)
        index_state = index.get(relative, [])
        entries.append(
            {
                "path": Path(relative).as_posix(),
                "tracked": bool(index_state),
                "index": index_state,
                "working": _working_identity(path, index_state),
            }
        )
    status = _status_records(repository, set(exclusions))
    basis = {
        "schema": SNAPSHOT_SCHEMA,
        "head_revision": _git(repository, "rev-parse", "HEAD").decode().strip().lower(),
        "branch": _git(repository, "branch", "--show-current").decode().strip(),
        "excluded_paths": exclusions,
        "entries": entries,
        "status_records": status,
        "status_records_sha256": sha256_bytes(canonical_json_bytes(status)),
        "dirty": bool(status),
    }
    return {**basis, "snapshot_sha256": sha256_bytes(canonical_json_bytes(basis))}


def record_command(root: str | Path, argv: Sequence[str]) -> dict[str, Any]:
    """Run one argv-only verification command and retain exact output hashes."""

    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise ValueError("verification command must be a non-empty argv list")
    started = time.monotonic()
    result = subprocess.run(
        list(argv),
        cwd=Path(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    duration = time.monotonic() - started
    return {
        "argv": list(argv),
        "exit_code": result.returncode,
        "duration_seconds": round(duration, 6),
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "stdout_tail": result.stdout[-4000:].decode("utf-8", errors="replace"),
        "stderr_tail": result.stderr[-4000:].decode("utf-8", errors="replace"),
    }


def _json_validation(root: Path, source: dict[str, Any]) -> dict[str, Any]:
    prefixes = ("config/", "models/", "synthetic_data/", "tests/", "training/")
    paths = [
        item["path"]
        for item in source["entries"]
        if item["path"].endswith(".json")
        and item["path"].startswith(prefixes)
        and item["working"]["kind"] == "file"
    ]
    errors: list[dict[str, str]] = []
    files: list[dict[str, str]] = []
    for relative in paths:
        path = _resolve_inside(root, relative)
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append({"path": relative, "error": str(exc)})
        files.append({"path": relative, "sha256": _sha256_file(path)})
    return {"pass": not errors, "file_count": len(files), "files": files, "errors": errors}


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in RECORDED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def build_readiness_receipt(
    root: str | Path,
    output_path: str | Path,
    command_records: Sequence[dict[str, Any]],
    *,
    limitations: Sequence[str],
) -> dict[str, Any]:
    repository = Path(root).resolve()
    output = Path(output_path).resolve()
    try:
        relative_output = output.relative_to(repository).as_posix()
    except ValueError as exc:
        raise ValueError("readiness receipt must be written inside the repository") from exc
    if not limitations or not all(str(item).strip() for item in limitations):
        raise ValueError("readiness receipt requires explicit limitations")
    source = collect_source_snapshot(repository, excluded_paths=[relative_output])
    json_validation = _json_validation(repository, source)
    commands_passed = bool(command_records) and all(
        item.get("exit_code") == 0 for item in command_records
    )
    basis = {
        "schema": READINESS_SCHEMA,
        "status": "non_promoting_code_readiness",
        "release_authorized": False,
        "accuracy_gain": "not_demonstrated",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable_sha256": _sha256_file(Path(sys.executable)),
            "package_versions": _package_versions(),
        },
        "verification": {
            "all_passed": commands_passed and json_validation["pass"],
            "commands": list(command_records),
            "json_syntax": json_validation,
        },
        "limitations": list(limitations),
    }
    receipt = {
        **basis,
        "receipt_sha256": sha256_bytes(canonical_json_bytes(basis)),
    }
    validate_contract(receipt, "readiness_receipt.schema.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def verify_readiness_receipt(
    root: str | Path, receipt_path: str | Path
) -> tuple[bool, list[str]]:
    """Verify receipt self-binding and exact current source state."""

    errors: list[str] = []
    path = Path(receipt_path).resolve()
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"readiness receipt is unreadable: {exc}"]
    if not isinstance(receipt, dict) or receipt.get("schema") != READINESS_SCHEMA:
        return False, ["readiness receipt schema is unsupported"]
    try:
        validate_contract(receipt, "readiness_receipt.schema.json")
    except ValueError as exc:
        return False, [str(exc)]
    supplied_hash = receipt.get("receipt_sha256")
    basis = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if supplied_hash != sha256_bytes(canonical_json_bytes(basis)):
        errors.append("readiness receipt content hash mismatch")
    if (
        receipt.get("status") != "non_promoting_code_readiness"
        or receipt.get("release_authorized") is not False
        or receipt.get("accuracy_gain") != "not_demonstrated"
    ):
        errors.append("readiness receipt contains an invalid claim state")
    source = receipt.get("source")
    if not isinstance(source, dict):
        errors.append("readiness receipt lacks a source snapshot")
        return False, errors
    repository = Path(root).resolve()
    try:
        expected_output = path.relative_to(repository).as_posix()
    except ValueError:
        errors.append("readiness receipt is outside the repository")
        return False, errors
    if source.get("excluded_paths") != [expected_output]:
        errors.append("source snapshot exclusions differ from the receipt path")
    else:
        current = collect_source_snapshot(repository, excluded_paths=[expected_output])
        if current != source:
            errors.append("current source state differs from the receipt snapshot")
    verification = receipt.get("verification")
    if not isinstance(verification, dict) or verification.get("all_passed") is not True:
        errors.append("readiness verification commands did not all pass")
    if not receipt.get("limitations"):
        errors.append("readiness receipt omits external limitations")
    return not errors, errors


def _default_commands() -> list[list[str]]:
    return [
        [sys.executable, "-m", "ruff", "check", "synthetic_data", "training", "tests"],
        [sys.executable, "-m", "synthetic_data", "--help"],
        [sys.executable, "-m", "pytest", "tests/", "-q"],
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "verify"))
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--output", default="synthetic_data/reports/readiness_receipt.json"
    )
    args = parser.parse_args()
    if args.mode == "verify":
        passed, errors = verify_readiness_receipt(args.root, args.output)
        print(json.dumps({"pass": passed, "errors": errors}, indent=2))
        raise SystemExit(0 if passed else 1)
    records = [record_command(args.root, command) for command in _default_commands()]
    receipt = build_readiness_receipt(
        args.root,
        args.output,
        records,
        limitations=[
            "No receipt-verified current-schema SITL corpus is present.",
            "No policy-minimum physical calibration or real OOD cohort is present.",
            "No blinded physical confirmation cohort or independent authority is present.",
        ],
    )
    print(
        json.dumps(
            {
                "receipt_path": str(Path(args.output).resolve()),
                "receipt_sha256": receipt["receipt_sha256"],
                "source_snapshot_sha256": receipt["source"]["snapshot_sha256"],
                "verification_pass": receipt["verification"]["all_passed"],
                "release_authorized": receipt["release_authorized"],
                "accuracy_gain": receipt["accuracy_gain"],
            },
            indent=2,
        )
    )
    raise SystemExit(0 if receipt["verification"]["all_passed"] else 1)


if __name__ == "__main__":
    main()
