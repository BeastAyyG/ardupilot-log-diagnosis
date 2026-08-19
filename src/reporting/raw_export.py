"""Deterministic raw-message and derived-series exports.

The exporter is intentionally table-oriented so an expert can reproduce a
finding in pandas, R, or a spreadsheet without depending on the dashboard.
Only message/field references and arithmetic are accepted for derived series;
no Python expressions are executed.
"""

from __future__ import annotations

import ast
import csv
import operator
import re
from pathlib import Path
from typing import Any


def message_rows(parsed: dict[str, Any], *, message_types: list[str] | None = None) -> list[dict[str, Any]]:
    messages = parsed.get("messages", {}) or {}
    selected = message_types or sorted(messages)
    rows: list[dict[str, Any]] = []
    for message_type in selected:
        values = messages.get(message_type, [])
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                continue
            rows.append({"message_type": message_type, "message_index": index, **value})
    return rows


def export_csv(parsed: dict[str, Any], output_path: str | Path, *, message_types: list[str] | None = None) -> Path:
    rows = message_rows(parsed, message_types=message_types)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["message_type", "message_index"] + sorted({key for row in rows for key in row if key not in {"message_type", "message_index"}})
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return destination


def export_parquet(parsed: dict[str, Any], output_path: str | Path, *, message_types: list[str] | None = None) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - pandas is a project dependency
        raise ValueError("Parquet export requires pandas.") from exc
    rows = message_rows(parsed, message_types=message_types)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        pd.DataFrame(rows).to_parquet(destination, index=False)
    except (ImportError, ValueError) as exc:
        raise ValueError("Parquet export requires a pandas parquet engine such as pyarrow.") from exc
    return destination


_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _field_values(parsed: dict[str, Any], reference: str) -> list[float | None]:
    try:
        message_type, field = reference.strip().split(".", 1)
    except ValueError as exc:
        raise ValueError(f"Derived reference must be MESSAGE.FIELD: {reference}") from exc
    values = parsed.get("messages", {}).get(message_type, [])
    if not isinstance(values, list):
        return []
    return [float(item[field]) if isinstance(item, dict) and isinstance(item.get(field), (int, float)) else None for item in values]


def _evaluate(node: ast.AST, parsed: dict[str, Any], references: dict[str, str]) -> list[float | None]:
    if isinstance(node, ast.Name):
        return _field_values(parsed, references.get(node.id, node.id))
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return [float(node.value)]
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _evaluate(node.left, parsed, references), _evaluate(node.right, parsed, references)
        size = max(len(left), len(right))
        result: list[float | None] = []
        for index in range(size):
            a = left[index] if index < len(left) else left[-1] if left else None
            b = right[index] if index < len(right) else right[-1] if right else None
            try:
                result.append(None if a is None or b is None else float(_OPERATORS[type(node.op)](a, b)))
            except (ZeroDivisionError, TypeError):
                result.append(None)
        return result
    raise ValueError("Only MESSAGE.FIELD references and + - * / arithmetic are allowed")


def derived_series(parsed: dict[str, Any], expression: str) -> dict[str, Any]:
    names = list(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", expression)))
    if not names:
        raise ValueError("At least one MESSAGE.FIELD reference is required")
    references = {f"ref{index}": name for index, name in enumerate(names)}
    normalized = expression
    for synthetic, name in references.items():
        normalized = normalized.replace(name, synthetic)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Derived expression is not valid arithmetic") from exc

    values = _evaluate(tree.body, parsed, references)
    return {"schema_version": "derived-series.v1", "status": "reliable" if any(value is not None for value in values) else "insufficient_data", "expression": expression, "sample_count": len(values), "values": values}
