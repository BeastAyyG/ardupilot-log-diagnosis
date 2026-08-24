"""Compatibility surface for the isolated verified SITL laboratory.

New code should import from synthetic_data or run python -m synthetic_data.
This module preserves the earlier training entrypoint without maintaining a
second, conflicting scenario catalogue.
"""

from __future__ import annotations

from typing import Any

from synthetic_data.catalog import SCENARIOS
from synthetic_data.cli import main as _laboratory_main
from synthetic_data.collector import VerificationError, collect_verified_logs
from synthetic_data.planner import (
    GENERATOR_VERSION,
    LABEL_ORIGIN as SYNTHETIC_LABEL_ORIGIN,
    MANIFEST_SCHEMA,
    RESEARCH_BASIS,
    SOURCE_TYPE,
    build_paired_run_plans,
    build_run_plans,
    write_experiment,
)
from synthetic_data.schema import ParameterSchema


def _legacy_configs() -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    for name, scenario in SCENARIOS.items():
        variant = scenario.variants[0]
        configs[name] = {
            "label": scenario.label,
            "startup": dict(variant.startup),
            "injection": dict(variant.injection),
            "duration_s": scenario.durations_sec,
            "motor_mask": scenario.motor_mask,
            "maturity": scenario.maturity,
            "non_claims": scenario.non_claims,
        }
    return configs


FAILURE_CONFIGS = _legacy_configs()

__all__ = [
    "FAILURE_CONFIGS",
    "GENERATOR_VERSION",
    "MANIFEST_SCHEMA",
    "ParameterSchema",
    "RESEARCH_BASIS",
    "SOURCE_TYPE",
    "SYNTHETIC_LABEL_ORIGIN",
    "VerificationError",
    "build_paired_run_plans",
    "build_run_plans",
    "collect_verified_logs",
    "write_experiment",
]


def _main() -> int:
    return _laboratory_main()


if __name__ == "__main__":
    raise SystemExit(_main())
