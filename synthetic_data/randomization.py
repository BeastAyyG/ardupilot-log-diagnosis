"""Deterministic domain randomization for paired SITL experiments.

Control/intervention pairs share one latent environment sample so the only
systematic difference inside a lineage remains the injected fault. Every
sample records the band configuration hash, making the randomization itself
preregistrable evidence rather than an undocumented generator knob.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

RANDOMIZATION_SCHEMA = "logdiagnosis.domain-randomization/v1"

DEFAULT_BANDS: dict[str, tuple[float, float]] = {
    "sim_wind_spd_mps": (0.0, 8.0),
    "sim_wind_dir_deg": (0.0, 360.0),
    "sim_wind_turb_pct": (0.0, 40.0),
}


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def validate_bands(bands: dict[str, tuple[float, float]]) -> None:
    if not bands:
        raise ValueError("randomization requires at least one parameter band")
    for name, (low, high) in sorted(bands.items()):
        if not name or not name.replace("_", "").isalnum():
            raise ValueError(f"invalid band parameter name: {name!r}")
        if not (_is_number(low) and _is_number(high)):
            raise ValueError(f"band {name} endpoints must be finite numbers")
        if low > high:
            raise ValueError(f"band {name} low exceeds high")


def bands_digest(bands: dict[str, tuple[float, float]]) -> str:
    canonical = json.dumps(
        {k: [float(v) for v in bands[k]] for k in sorted(bands)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def sample_pair_environment(
    *,
    pair_seed: int,
    bands: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """One latent environment shared verbatim by both arms of a pair."""

    if isinstance(pair_seed, bool) or pair_seed < 0:
        raise ValueError("pair_seed must be a non-negative integer")
    resolved = dict(DEFAULT_BANDS if bands is None else bands)
    validate_bands(resolved)
    digest = bands_digest(resolved)
    stream = hashlib.sha256(f"{digest}:{pair_seed}".encode()).digest()
    sampled: dict[str, float] = {}
    for index, name in enumerate(sorted(resolved)):
        low, high = resolved[name]
        # Rejection-free uniform draw from a dedicated 8-byte slice.
        unit = int.from_bytes(stream[index * 8 : index * 8 + 8], "big") / 2**64
        sampled[name] = round(low + (high - low) * unit, 6)
    return {
        "schema": RANDOMIZATION_SCHEMA,
        "bands_sha256": digest,
        "pair_seed": int(pair_seed),
        "environment": sampled,
    }
