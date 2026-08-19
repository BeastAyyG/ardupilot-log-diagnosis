"""Deterministic time-lagged causal DAG for pre-impact hypotheses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real

import numpy as np


@dataclass(frozen=True, slots=True)
class CitaDagResult:
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    topological_order: tuple[str, ...]
    root_candidates: tuple[str, ...]
    root_cause: str | None
    impact_boundary_us: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "cita-dag.v1",
            "method": "time-lagged-deterministic",
            "nodes": list(self.nodes),
            "edges": [{"from": source, "to": target} for source, target in self.edges],
            "topological_order": list(self.topological_order),
            "root_candidates": list(self.root_candidates),
            "root_cause": self.root_cause,
            "impact_boundary_us": self.impact_boundary_us,
        }


def _event_value(event: Mapping[str, object], key: str, name: str) -> float:
    value = event.get(key)
    if not isinstance(value, Real) or isinstance(value, bool) or not np.isfinite(value):
        raise ValueError(f"event {name!r} requires a finite {key!r}")
    return float(value)


def build_cita_dag(
    events: Mapping[str, Mapping[str, object]],
    *,
    dependencies: Sequence[tuple[str, str]] | None = None,
    max_lag_us: float = 30_000_000.0,
    impact_boundary_us: float | None = None,
) -> CitaDagResult:
    """Build a causal graph from onset order and optional domain edges.

    Edges point from an earlier candidate to a later candidate.  Explicit
    dependency edges are retained only when they respect the time window;
    without them, all temporally plausible earlier/later pairs are connected.
    """

    if not np.isfinite(max_lag_us) or max_lag_us <= 0:
        raise ValueError("max_lag_us must be finite and positive")
    if impact_boundary_us is not None and not np.isfinite(impact_boundary_us):
        raise ValueError("impact_boundary_us must be finite")
    normalized: dict[str, tuple[float, float]] = {}
    for raw_name, event in events.items():
        name = str(raw_name).strip()
        if not name or name in normalized:
            raise ValueError("event names must be unique and non-empty")
        onset = _event_value(event, "onset_us", name)
        score = _event_value(event, "score", name)
        if impact_boundary_us is None or onset < impact_boundary_us:
            normalized[name] = (onset, score)

    names = tuple(sorted(normalized, key=lambda item: (normalized[item][0], item)))
    allowed = set(names)
    candidate_edges: set[tuple[str, str]] = set()
    if dependencies is not None:
        for raw_source, raw_target in dependencies:
            source, target = str(raw_source).strip(), str(raw_target).strip()
            if source not in allowed or target not in allowed or source == target:
                continue
            source_time = normalized[source][0]
            target_time = normalized[target][0]
            if 0 < target_time - source_time <= max_lag_us:
                candidate_edges.add((source, target))
    else:
        for position, source in enumerate(names):
            for target in names[position + 1 :]:
                lag = normalized[target][0] - normalized[source][0]
                if 0 < lag <= max_lag_us:
                    candidate_edges.add((source, target))

    indegree = {name: 0 for name in names}
    outgoing: dict[str, list[str]] = {name: [] for name in names}
    for source, target in sorted(candidate_edges):
        outgoing[source].append(target)
        indegree[target] += 1
    ready = sorted(name for name, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=lambda item: (normalized[item][0], item))
    if len(order) != len(names):
        raise ValueError("causal dependencies contain a cycle")
    roots = tuple(name for name in order if not any(target == name for _, target in candidate_edges))
    root = min(roots, key=lambda item: (normalized[item][0], -normalized[item][1], item), default=None)
    return CitaDagResult(
        nodes=names,
        edges=tuple(sorted(candidate_edges)),
        topological_order=tuple(order),
        root_candidates=roots,
        root_cause=root,
        impact_boundary_us=impact_boundary_us,
    )
