"""Transparent multivariate Matrix Profile baseline.

This implementation intentionally favors auditability over large-scale speed.
Telemetry is resampled to a bounded number of points before it reaches this
module, keeping the quadratic comparison cost predictable. It returns a
candidate discord window; it does not assign a failure label.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict

import numpy as np


class MatrixProfileResult(TypedDict):
    status: str
    discord_index: int | None
    nearest_neighbor_index: int | None
    score: float | None
    window_size: int
    points: int
    contributing_channels: list[dict[str, float | str]]
    reason: str


def _as_finite_array(values: Sequence[float], channel_name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"Channel {channel_name!r} must be one-dimensional")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"Channel {channel_name!r} contains non-finite values")
    return array


def _z_normalized_windows(values: np.ndarray, window_size: int) -> np.ndarray:
    windows = np.lib.stride_tricks.sliding_window_view(values, window_size)
    means = windows.mean(axis=1, keepdims=True)
    stds = windows.std(axis=1, keepdims=True)
    safe_stds = np.where(stds < 1e-12, 1.0, stds)
    normalized = (windows - means) / safe_stds
    normalized = np.where(stds < 1e-12, 0.0, normalized)
    return normalized


def multivariate_matrix_profile(
    channels: Mapping[str, Sequence[float]],
    window_size: int,
    *,
    exclusion_zone: int | None = None,
) -> MatrixProfileResult:
    """Return the most unusual multichannel subsequence.

    Distances are z-normalized, so channels with large physical units do not
    automatically dominate channels with smaller units. The score is the
    root-mean-square distance to the nearest non-trivial neighboring window.
    """

    if not channels:
        return {
            "status": "unavailable",
            "discord_index": None,
            "nearest_neighbor_index": None,
            "score": None,
            "window_size": window_size,
            "points": 0,
            "contributing_channels": [],
            "reason": "No telemetry channels were supplied.",
        }

    arrays = {
        name: _as_finite_array(values, name)
        for name, values in sorted(channels.items())
    }
    lengths = {len(values) for values in arrays.values()}
    if len(lengths) != 1:
        raise ValueError("All Matrix Profile channels must have equal length")

    points = lengths.pop()
    if window_size < 4:
        raise ValueError("window_size must be at least 4")
    if points < window_size * 2:
        return {
            "status": "unavailable",
            "discord_index": None,
            "nearest_neighbor_index": None,
            "score": None,
            "window_size": window_size,
            "points": points,
            "contributing_channels": [],
            "reason": "At least two full windows are required.",
        }

    channel_names = list(arrays)
    normalized = np.stack(
        [
            _z_normalized_windows(arrays[name], window_size)
            for name in channel_names
        ],
        axis=1,
    )
    window_count = normalized.shape[0]
    flattened = normalized.reshape(window_count, -1)
    zone = (
        max(1, window_size // 2)
        if exclusion_zone is None
        else max(0, exclusion_zone)
    )

    profile = np.full(window_count, np.inf, dtype=float)
    neighbors = np.full(window_count, -1, dtype=int)
    indices = np.arange(window_count)
    for index in range(window_count):
        deltas = flattened - flattened[index]
        distances = np.sqrt(np.mean(deltas * deltas, axis=1))
        distances[np.abs(indices - index) <= zone] = np.inf
        neighbor = int(np.argmin(distances))
        if np.isfinite(distances[neighbor]):
            profile[index] = float(distances[neighbor])
            neighbors[index] = neighbor

    finite_indices = np.flatnonzero(np.isfinite(profile))
    if finite_indices.size == 0:
        return {
            "status": "unavailable",
            "discord_index": None,
            "nearest_neighbor_index": None,
            "score": None,
            "window_size": window_size,
            "points": points,
            "contributing_channels": [],
            "reason": "No non-trivial comparison window was available.",
        }

    discord_index = int(finite_indices[np.argmax(profile[finite_indices])])
    neighbor_index = int(neighbors[discord_index])
    contributions = []
    for channel_index, channel_name in enumerate(channel_names):
        delta = (
            normalized[discord_index, channel_index]
            - normalized[neighbor_index, channel_index]
        )
        contributions.append(
            {
                "channel": channel_name,
                "distance": float(np.sqrt(np.mean(delta * delta))),
            }
        )
    contributions.sort(
        key=lambda item: float(item["distance"]),
        reverse=True,
    )

    return {
        "status": "candidate",
        "discord_index": discord_index,
        "nearest_neighbor_index": neighbor_index,
        "score": float(profile[discord_index]),
        "window_size": window_size,
        "points": points,
        "contributing_channels": contributions,
        "reason": (
            "Highest nearest-neighbor distance in the bounded, z-normalized "
            "multivariate Matrix Profile."
        ),
    }
