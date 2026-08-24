"""Verified ArduPilot SITL synthetic-data laboratory.

The package plans reproducible interventions, records execution evidence,
validates DataFlash logs, and evaluates augmentation only on frozen real
incident groups. Planning output is never trainable by itself.
"""

from .catalog import SCENARIOS, ScenarioSpec
from .collector import collect_verified_logs
from .planner import build_run_plans, write_experiment
from .schema import ParameterSchema

__all__ = [
    "ParameterSchema",
    "SCENARIOS",
    "ScenarioSpec",
    "build_run_plans",
    "collect_verified_logs",
    "write_experiment",
]
