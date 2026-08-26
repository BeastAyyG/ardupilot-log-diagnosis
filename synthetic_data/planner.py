"""Deterministic, capability-checked planning for ArduPilot SITL experiments."""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .catalog import SCENARIOS, ScenarioSpec
from .execution_integrity import float32_equal
from .frame_defaults import FRAME_CLASS_VALUES
from .randomization import draw_randomization
from .schema import ParameterSchema, canonical_json_bytes, sha256_bytes

GENERATOR_VERSION = "ardupilot-sitl-lab-v2"
MANIFEST_SCHEMA = "logdiagnosis.sitl-experiment/v3"
SOURCE_TYPE = "sitl"
LABEL_ORIGIN = "verified_controlled_sitl_intervention"
SAFE_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")
# ArduPilot persists these parameters by itself on every genuine flight:
# ground pressure at arming (BARO*_GND_PRESS), mission totals when the
# mission is loaded (MIS_TOTAL), in-flight hover-thrust learning
# (MOT_THST_HOVER, observed in run 32903900341), and flight statistics
# saved at disarm (STAT_*). They are firmware bookkeeping rather than
# external tampering; every other in-flight parameter change still fails
# the collection gate.
FIRMWARE_MANAGED_PARAMETER_CHANGES = (
    "BARO1_GND_PRESS",
    "BARO2_GND_PRESS",
    "MIS_TOTAL",
    "MOT_THST_HOVER",
    "STAT_DISTFLWN",
    "STAT_FLTCNT",
    "STAT_FLTTIME",
    "STAT_RUNTIME",
)
FRAME_MOTOR_MASKS: Mapping[str, tuple[int, ...]] = {
    "quad": (1, 2, 4, 8),
    "hexa": (1, 2, 4, 8, 16, 32),
    "octa": (1, 2, 4, 8, 16, 32, 64, 128),
}
FRAME_CLASS_NAMES = {1: "quad", 2: "hexa", 3: "octa"}
DOMAIN_PARAMETERS = {
    "SIM_WIND_SPD": (0.0, 2.0, 5.0, 8.0, 12.0),
    "SIM_WIND_TURB": (0.0, 0.5, 1.5, 3.0, 4.0),
}
LOGGING_CONTRACT = {
    "LOG_BACKEND_TYPE": 1.0,
    "LOG_FILE_DSRMROT": 1.0,
    "LOG_FILE_RATEMAX": 0.0,
    "LOG_DISARMED": 0.0,
}
FIXED_HOME = {
    "latitude": -35.363261,
    "longitude": 149.165230,
    "altitude_m": 584.0,
    "heading_deg": 353.0,
}
SIMULATION_START_UNIX_SEC = 1_704_067_200  # 2024-01-01T00:00:00Z
RESEARCH_BASIS = {
    "ardupilot_sitl": "https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html",
    "ardupilot_autotest": "https://ardupilot.org/dev/docs/the-ardupilot-autotest-framework.html",
    "alfa": "https://arxiv.org/abs/1907.06268",
    "domain_randomization": "https://arxiv.org/abs/1703.06907",
    "rflymad": "https://arxiv.org/abs/2311.11340",
    "digital_twin_credibility": (
        "https://www.nist.gov/publications/credibility-consideration-digital-twins-manufacturing"
    ),
}


def _immutable_revision(value: str) -> str:
    revision = str(value).strip()
    if not revision or revision.lower() in {
        "latest",
        "master",
        "main",
        "head",
        "unknown",
    }:
        raise ValueError(
            "ardupilot_revision must be an immutable release tag or resolved commit"
        )
    return revision


def _derived_seed(root_seed: int, scenario: str, index: int, role: str) -> int:
    payload = f"{int(root_seed)}:{scenario}:{index}:{role}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _joint_choice(
    choices: Mapping[str, Sequence[float]], rng: random.Random
) -> tuple[dict[str, float], float | None]:
    """Choose a common severity quantile so coupled parameters stay coherent."""

    if not choices:
        return {}, None
    quantile = rng.random()
    selected: dict[str, float] = {}
    for name, values in choices.items():
        ordered = tuple(values)
        position = min(int(quantile * len(ordered)), len(ordered) - 1)
        selected[name] = float(ordered[position])
    return dict(sorted(selected.items())), round(quantile, 6)


def _environment(rng: random.Random, available: set[str] | None) -> dict[str, float]:
    names = set(DOMAIN_PARAMETERS) if available is None else available
    values: dict[str, float] = {}
    if "SIM_WIND_SPD" in names:
        values["SIM_WIND_SPD"] = round(rng.uniform(0.0, 12.0), 3)
    if "SIM_WIND_DIR" in names:
        values["SIM_WIND_DIR"] = float(rng.randrange(0, 360))
    if "SIM_WIND_TURB" in names:
        values["SIM_WIND_TURB"] = round(rng.uniform(0.0, 4.0), 3)
    return dict(sorted(values.items()))


def _logging_parameters(schema: ParameterSchema | None) -> dict[str, float]:
    if schema is None:
        return {}
    required = {*LOGGING_CONTRACT, "LOG_BITMASK"}
    missing = sorted(required - schema.parameter_names)
    if missing:
        raise ValueError(
            "verified plans require an explicit DataFlash logging contract; missing "
            + ", ".join(missing)
        )
    return {
        **LOGGING_CONTRACT,
        "LOG_BITMASK": float(schema.parameters["LOG_BITMASK"]),
    }


def _plan_fingerprint(plan: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in plan.items() if key != "run_fingerprint"}
    return sha256_bytes(canonical_json_bytes(payload))


def _single_plan(
    spec: ScenarioSpec,
    *,
    index: int,
    root_seed: int,
    revision: str,
    schema: ParameterSchema | None,
    role: str = "intervention",
    paired_with: str | None = None,
    identity_salt: str = "",
    randomization_enabled: bool = False,
) -> dict[str, Any]:
    identity = f"{spec.name}:{identity_salt}" if identity_salt else spec.name
    run_seed = _derived_seed(root_seed, identity, index, role)
    rng = random.Random(run_seed)
    available = schema.parameter_names if schema else None
    variant = (
        spec.select_variant(available) if available is not None else spec.variants[0]
    )
    if variant is None:
        supported = ", ".join(sorted(available or set()))
        raise ValueError(
            f"scenario {spec.name} has no complete parameter variant in the pinned schema "
            f"({len(available or set())} parameters; available inventory starts: {supported[:120]})"
        )

    frame_options = tuple(FRAME_MOTOR_MASKS)
    if schema is not None:
        if "FRAME_CLASS" not in schema.parameters:
            raise ValueError("verified plans require FRAME_CLASS in the pinned schema")
        schema_frame = FRAME_CLASS_NAMES.get(round(schema.parameters["FRAME_CLASS"]))
        if schema_frame is None:
            raise ValueError(
                "the pinned schema FRAME_CLASS is not a supported quad/hexa/octa frame"
            )
        # Captured parameter inventories are frame-specific. Selecting another
        # frame would make full live-value attestation compare unlike defaults.
        frame_options = (schema_frame,)
    if spec.motor_mask and schema is not None:
        mapped_motor_functions = {
            round(value)
            for name, value in schema.parameters.items()
            if name.startswith("SERVO")
            and name.endswith("_FUNCTION")
            and 33 <= round(value) <= 40
        }
        motor_capable_frames = tuple(
            name
            for name, masks in FRAME_MOTOR_MASKS.items()
            if set(range(33, 33 + len(masks))).issubset(mapped_motor_functions)
        )
        frame_options = tuple(
            name for name in frame_options if name in motor_capable_frames
        )
        if not frame_options:
            raise ValueError(
                f"scenario {spec.name} has no frame with a proven motor-output mapping"
            )
    frame = rng.choice(frame_options)
    duration_sec = int(rng.choice(spec.durations_sec))
    startup, startup_quantile = _joint_choice(variant.startup, rng)
    injection, severity_quantile = _joint_choice(variant.injection, rng)
    environment = _environment(rng, available)
    randomization_parameters = (
        draw_randomization(rng, available) if randomization_enabled else {}
    )
    fault_startup = dict(startup)
    logging_parameters = _logging_parameters(schema)
    startup = {
        **environment,
        **logging_parameters,
        **randomization_parameters,
        **fault_startup,
    }
    if schema is not None:
        # The captured inventory is frame-specific. Persist its frame class in
        # the immutable startup file so ArduPilot does not boot with its
        # unsupported empty-default value (FRAME_CLASS=0).
        startup["FRAME_CLASS"] = float(FRAME_CLASS_VALUES[frame])
    motor_output_parameters: dict[str, float] = {}
    if spec.motor_mask:
        if available is not None and "SIM_ENGINE_FAIL" not in available:
            raise ValueError(
                f"scenario {spec.name} requires SIM_ENGINE_FAIL in the pinned schema"
            )
        masks = FRAME_MOTOR_MASKS[frame]
        if schema is not None:
            required_motors = len(masks)
            motor_output_parameters = {
                name: value
                for name, value in schema.parameters.items()
                if name.startswith("SERVO")
                and name.endswith("_FUNCTION")
                and 33 <= round(value) < 33 + required_motors
            }
            if len(motor_output_parameters) != required_motors:
                raise ValueError(
                    f"scenario {spec.name} cannot prove {required_motors} motor output mappings"
                )
            masks = tuple(
                1 << (int(name[5 : name.index("_")]) - 1)
                for name in sorted(
                    motor_output_parameters,
                    key=lambda item: round(motor_output_parameters[item]),
                )
            )
        injection["SIM_ENGINE_FAIL"] = float(rng.choice(masks))

    injection_baselines = (
        {name: float(schema.parameters[name]) for name in injection}
        if schema is not None
        else {}
    )
    if schema is not None and any(
        float32_equal(injection_baselines[name], value)
        for name, value in injection.items()
    ):
        raise ValueError(f"scenario {spec.name} injection equals its pinned baseline")

    onset = None
    if injection:
        onset = round(rng.uniform(duration_sec * 0.30, duration_sec * 0.55), 3)
    run_token = hashlib.sha256(
        f"{identity}:{index}:{run_seed}:{role}".encode("ascii")
    ).hexdigest()[:12]
    role_suffix = "fault" if role == "intervention" else role
    run_id = f"sitl_{spec.name}_{index:04d}_{role_suffix}_{run_token}"
    lineage_root_id = f"sitl-lineage:{spec.name}:{index}:{run_token}"
    source_group = f"sitl:{GENERATOR_VERSION}:{run_id}"
    plan: dict[str, Any] = {
        "run_id": run_id,
        "scenario": spec.name,
        "scenario_index": index,
        "label": spec.label,
        "root_family": spec.root_family,
        "fault_mode": spec.fault_mode,
        "causal_chain": list(spec.causal_chain),
        "non_claims": list(spec.non_claims),
        "maturity": spec.maturity,
        "role": role,
        "paired_with": paired_with,
        "lineage_root_id": lineage_root_id,
        "source_type": SOURCE_TYPE,
        "source_group": source_group,
        "label_origin": LABEL_ORIGIN,
        "generator_version": GENERATOR_VERSION,
        "scenario_sampling_seed": run_seed,
        "sitl_rng_seed": None,
        "bit_exact_replay_claim": False,
        "root_seed": int(root_seed),
        "ardupilot_revision": revision,
        "parameter_schema_sha256": schema.digest if schema else None,
        "binary_sha256": schema.binary_sha256 if schema else None,
        "capability_status": "verified" if schema else "unverified",
        "parameter_variant": variant.name,
        "parameter_variant_note": variant.note,
        "vehicle": "ArduCopter",
        "frame": frame,
        "mission_profile": "guided_takeoff_hover_land",
        "fixed_home": dict(FIXED_HOME),
        "simulation_start_unix_sec": SIMULATION_START_UNIX_SEC,
        "duration_sec": duration_sec,
        "planned_fault_onset_sec": onset,
        "minimum_post_fault_sec": 15.0 if onset is not None else 0.0,
        "temporal_profile": "step",
        "startup_parameters": dict(sorted(startup.items())),
        "environment_parameters": dict(sorted(environment.items())),
        "randomization_parameters": dict(sorted(randomization_parameters.items())),
        "logging_parameters": dict(sorted(logging_parameters.items())),
        "fault_startup_parameters": dict(sorted(fault_startup.items())),
        "control_startup_policy": variant.control_startup_policy,
        "injection_parameters": dict(sorted(injection.items())),
        "injection_baseline_parameters": dict(sorted(injection_baselines.items())),
        "allowed_automatic_parameter_changes": list(
            FIRMWARE_MANAGED_PARAMETER_CHANGES
        ),
        "motor_output_parameters": dict(sorted(motor_output_parameters.items())),
        "severity_quantile": severity_quantile,
        "startup_severity_quantile": startup_quantile,
        "required_messages": list(spec.required_messages),
        "expected_log_filename": f"{run_id}.BIN",
        "expected_receipt_filename": f"{run_id}.execution.json",
        "artifact_status": "planned",
        "trainable": False,
    }
    plan["run_fingerprint"] = _plan_fingerprint(plan)
    return plan


def build_run_plans(
    runs_per_scenario: int,
    *,
    seed: int,
    ardupilot_revision: str,
    scenarios: Iterable[str] | None = None,
    parameter_schema: ParameterSchema | None = None,
    randomization_enabled: bool = False,
) -> list[dict[str, Any]]:
    """Build independently seeded plans; order changes do not change existing runs."""

    if (
        isinstance(runs_per_scenario, bool)
        or not isinstance(runs_per_scenario, int)
        or runs_per_scenario < 1
    ):
        raise ValueError("runs_per_scenario must be a positive integer")
    revision = _immutable_revision(ardupilot_revision)
    if parameter_schema and revision.lower() != parameter_schema.ardupilot_commit:
        raise ValueError(
            "ardupilot_revision does not match the parameter schema commit"
        )
    selected = list(scenarios or SCENARIOS)
    if len(selected) != len(set(selected)):
        raise ValueError("scenario names must not be duplicated")
    unknown = sorted(set(selected) - set(SCENARIOS))
    if unknown:
        raise ValueError("Unknown SITL scenarios: " + ", ".join(unknown))
    return [
        _single_plan(
            SCENARIOS[scenario],
            index=index,
            root_seed=seed,
            revision=revision,
            schema=parameter_schema,
            randomization_enabled=randomization_enabled,
        )
        for scenario in selected
        for index in range(runs_per_scenario)
    ]


def build_paired_run_plans(
    runs_per_scenario: int,
    *,
    seed: int,
    ardupilot_revision: str,
    scenarios: Iterable[str] | None = None,
    parameter_schema: ParameterSchema,
    randomization_enabled: bool = False,
) -> list[dict[str, Any]]:
    """Create matched sham and fault runs for every selected non-healthy scenario."""

    selected = list(scenarios or (name for name in SCENARIOS if name != "healthy"))
    if "healthy" in selected:
        raise ValueError("paired plans derive their own healthy controls")
    faults = build_run_plans(
        runs_per_scenario,
        seed=seed,
        ardupilot_revision=ardupilot_revision,
        scenarios=selected,
        parameter_schema=parameter_schema,
        randomization_enabled=randomization_enabled,
    )
    paired: list[dict[str, Any]] = []
    for fault in faults:
        control = _single_plan(
            SCENARIOS["healthy"],
            index=int(fault["scenario_index"]),
            root_seed=seed,
            revision=ardupilot_revision,
            schema=parameter_schema,
            role="sham_control",
            paired_with=fault["run_id"],
            identity_salt=str(fault["scenario"]),
        )
        # Counterfactual controls reuse the same latent vehicle/environment.
        control["frame"] = fault["frame"]
        control["duration_sec"] = fault["duration_sec"]
        control["simulation_start_unix_sec"] = fault["simulation_start_unix_sec"]
        # Randomized noise/vibration/battery draws are part of the latent
        # vehicle, so both members of a pair must fly the identical values.
        shared_randomization = dict(fault["randomization_parameters"])
        control["randomization_parameters"] = dict(shared_randomization)
        control_startup = {
            **fault["environment_parameters"],
            **shared_randomization,
            **fault["logging_parameters"],
        }
        if fault["control_startup_policy"] == "share":
            control_startup.update(fault["fault_startup_parameters"])
        else:
            for name in fault["fault_startup_parameters"]:
                if name in shared_randomization:
                    continue
                control_startup[name] = float(parameter_schema.parameters[name])
        control_startup["FRAME_CLASS"] = float(FRAME_CLASS_VALUES[fault["frame"]])
        control["startup_parameters"] = dict(sorted(control_startup.items()))
        control["environment_parameters"] = dict(fault["environment_parameters"])
        control["logging_parameters"] = dict(fault["logging_parameters"])
        control["fault_startup_parameters"] = {}
        control["control_startup_policy"] = fault["control_startup_policy"]
        control["motor_output_parameters"] = dict(fault["motor_output_parameters"])
        control["required_messages"] = sorted(
            set(control["required_messages"]) | set(fault["required_messages"])
        )
        shared_lineage = f"sitl-pair:{fault['run_fingerprint'][:20]}"
        control["lineage_root_id"] = shared_lineage
        fault["lineage_root_id"] = shared_lineage
        control["paired_with"] = fault["run_id"]
        fault["paired_with"] = control["run_id"]
        control["run_fingerprint"] = _plan_fingerprint(control)
        fault["run_fingerprint"] = _plan_fingerprint(fault)
        paired.extend((control, fault))
    return paired


def _safe_plan(plan: Mapping[str, Any]) -> None:
    run_id = str(plan.get("run_id", ""))
    if not SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError(f"unsafe run_id: {run_id}")
    expected = str(plan.get("expected_log_filename", ""))
    receipt = str(plan.get("expected_receipt_filename", ""))
    if expected != f"{run_id}.BIN" or receipt != f"{run_id}.execution.json":
        raise ValueError(f"run {run_id} has an unsafe or inconsistent artifact name")
    randomization = plan.get("randomization_parameters", {})
    if not isinstance(randomization, dict):
        raise ValueError(f"run {run_id} has an invalid randomization_parameters entry")
    if not all(math.isfinite(float(value)) for value in randomization.values()):
        raise ValueError(f"run {run_id} contains non-finite randomized parameters")
    if plan.get("run_fingerprint") != _plan_fingerprint(plan):
        raise ValueError(f"run {run_id} fingerprint is invalid")
    start_time = plan.get("simulation_start_unix_sec")
    if (
        isinstance(start_time, bool)
        or not isinstance(start_time, int)
        or not 946_684_800 <= start_time <= 2_147_483_647
    ):
        raise ValueError(f"run {run_id} has an unsafe simulation start epoch")
    for mapping_name in ("startup_parameters", "injection_parameters"):
        values = plan.get(mapping_name)
        if not isinstance(values, dict):
            raise ValueError(f"run {run_id} lacks {mapping_name}")
        if not all(math.isfinite(float(value)) for value in values.values()):
            raise ValueError(f"run {run_id} contains non-finite parameter values")


def write_experiment(
    output_dir: str | Path,
    plans: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    ardupilot_revision: str,
    parameter_schema: ParameterSchema | None = None,
) -> dict[str, Path]:
    """Write an immutable experiment plan and never fabricate flight logs."""

    from .experiment_io import write_experiment as implementation

    return implementation(
        output_dir,
        plans,
        seed=seed,
        ardupilot_revision=ardupilot_revision,
        parameter_schema=parameter_schema,
    )
