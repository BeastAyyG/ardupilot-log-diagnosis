"""Fail-closed activation checks for schema-v3 development model artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Iterable

PROMOTION_SCHEMA = "logdiagnosis.model-promotion-authorization/v1"
GATE_SCHEMA = "logdiagnosis.synthetic-gate-evaluation/v2"
TRUST_ENV_VAR = "LOGDIAGNOSIS_TRUSTED_PROMOTION_RECEIPTS"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def authorization_decision_sha256(receipt: Mapping[str, Any]) -> str:
    """Recompute the canonical promotion decision binding for a receipt."""

    payload = {
        "schema": PROMOTION_SCHEMA,
        "status": receipt.get("status"),
        "receipt_id": receipt.get("receipt_id"),
        "authorized_by": receipt.get("authorized_by"),
        "authorized_at": receipt.get("authorized_at"),
        "candidate_manifest_sha256": receipt.get("candidate_manifest_sha256"),
        "acceptance_gate_report_sha256": receipt.get(
            "acceptance_gate_report_sha256"
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def resolve_trusted_receipt_sha256s(
    trusted_receipt_sha256s: Iterable[str] | None,
) -> frozenset[str]:
    """Resolve the external trust anchor; empty means fail closed."""

    if trusted_receipt_sha256s is not None:
        values = trusted_receipt_sha256s
    else:
        raw = os.environ.get(TRUST_ENV_VAR, "")
        values = [part for part in raw.replace(";", ",").split(",") if part.strip()]
    return frozenset(value.strip().lower() for value in values if value.strip())


def validate_artifact_activation(
    model_root: str | Path,
    manifest: Mapping[str, Any],
    *,
    trusted_receipt_sha256s: Iterable[str] | None = None,
) -> tuple[bool, str]:
    """Require independent promotion authorization for the current artifact schema."""

    try:
        version = int(manifest.get("artifact_schema_version", 0) or 0)
    except (TypeError, ValueError):
        return False, "invalid artifact schema version"
    if version > 3:
        return False, "unsupported future artifact schema"
    if version < 3:
        return True, "legacy artifact activation policy"
    if manifest.get("release_status") != (
        "development_candidate_requires_blinded_confirmation"
    ) or manifest.get("evaluation", {}).get("non_promoting") is not True:
        return False, "schema-v3 manifest has an invalid development state"

    root = Path(model_root)
    manifest_path = root / "manifest.json"
    gate_path = root / "acceptance_gate_report.json"
    receipt_path = root / "promotion_receipt.json"
    if not gate_path.is_file() or not receipt_path.is_file():
        return False, "development candidate lacks promotion authorization"
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "promotion evidence is unreadable"
    if not isinstance(gate, dict) or not isinstance(receipt, dict):
        return False, "promotion evidence roots must be objects"
    if (
        gate.get("schema") != GATE_SCHEMA
        or gate.get("pass") is not True
        or gate.get("release_authorized") is not False
        or not _valid_hash(gate.get("evidence_sha256"))
        or not _valid_hash(gate.get("policy_sha256"))
    ):
        return False, "acceptance gate report is not a complete technical pass"
    if (
        receipt.get("schema") != PROMOTION_SCHEMA
        or receipt.get("status") != "authorized"
        or receipt.get("candidate_manifest_sha256") != sha256_file(manifest_path)
        or receipt.get("acceptance_gate_report_sha256") != sha256_file(gate_path)
        or not _valid_hash(receipt.get("authorization_decision_sha256"))
        or not str(receipt.get("authorized_by", "")).strip()
        or not str(receipt.get("authorized_at", "")).strip()
        or not str(receipt.get("receipt_id", "")).strip()
    ):
        return False, "promotion receipt is invalid or bound to another candidate"
    if receipt.get("authorization_decision_sha256") != authorization_decision_sha256(
        receipt
    ):
        return False, "promotion decision binding does not match the receipt"
    trusted = resolve_trusted_receipt_sha256s(trusted_receipt_sha256s)
    if not trusted:
        return False, "no external promotion trust anchor is configured"
    receipt_sha256 = sha256_file(receipt_path)
    if receipt_sha256 not in trusted:
        return False, (
            "promotion receipt is not pinned by the external trust anchor "
            f"(receipt_sha256={receipt_sha256})"
        )
    return True, "independently authorized schema-v3 artifact"
