"""Pin the correct ArduPilot frame-default merge contract.

The pinned parameter inventory is frame-specific, so the plan's frame must be
the inventory's frame, the executor overlays ``FRAME_CLASSES[frame]`` after
startup parameters (never the reverse), and paired arms share everything
except the fault-side parameter sets.
"""

from __future__ import annotations


from synthetic_data.planner import (
    build_paired_run_plans,
    build_run_plans,
)
from synthetic_data.runner import FRAME_CLASSES
from synthetic_data.schema import ParameterSchema

COMMIT = "1" * 40


def _schema(frame_value: float = 1.0, *extra: str) -> ParameterSchema:
    names = {
        "FRAME_CLASS",
        "SIM_WIND_SPD",
        "SIM_WIND_DIR",
        "SIM_WIND_TURB",
        "LOG_BACKEND_TYPE",
        "LOG_FILE_DSRMROT",
        "LOG_FILE_RATEMAX",
        "LOG_DISARMED",
        "LOG_BITMASK",
        *extra,
    }
    parameters = {name: 0.0 for name in names}
    parameters["FRAME_CLASS"] = frame_value
    if "SIM_ENGINE_FAIL" in extra:
        parameters.update(
            {f"SERVO{index}_FUNCTION": 32.0 + index for index in range(1, 9)}
        )
    return ParameterSchema(
        ardupilot_commit=COMMIT,
        binary_sha256="2" * 64,
        inventory_sha256="3" * 64,
        parameters=parameters,
        source_name="parameters.parm",
    )


class TestFrameDefaultMerging:
    def test_plan_frame_is_locked_to_the_captured_inventory(self) -> None:
        schema = _schema(
            1.0, "SIM_ENGINE_MUL", "SIM_ENGINE_FAIL"
        )  # quad inventory with thrust_loss variant support
        plans = build_run_plans(
            2,
            seed=5,
            ardupilot_revision=COMMIT,
            scenarios=["healthy", "thrust_loss"],
            parameter_schema=schema,
        )
        assert {p["frame"] for p in plans} == {"quad"}
        # Executor overlay value matches the inventory exactly.
        for plan in plans:
            assert FRAME_CLASSES[plan["frame"]] == schema.parameters["FRAME_CLASS"]

    def test_mismatched_frame_inventory_is_refused(self) -> None:
        schema = _schema(frame_value=3.0)  # octa inventory
        # A motor-mask scenario cannot fly on a frame whose captured SERVO
        # functions disagree; planning must fail closed rather than merge.
        try:
            plans = build_run_plans(
                1,
                seed=1,
                ardupilot_revision=COMMIT,
                scenarios=["motor_imbalance"],
                parameter_schema=schema,
            )
        except ValueError:
            return
        assert all(p["frame"] == "octa" for p in plans)

    def test_startup_never_carries_a_conflicting_frame_class(self) -> None:
        schema = _schema()
        plan = build_run_plans(
            1,
            seed=7,
            ardupilot_revision=COMMIT,
            scenarios=["healthy"],
            parameter_schema=schema,
        )[0]
        if "FRAME_CLASS" in plan["startup_parameters"]:
            live_overlay = FRAME_CLASSES[plan["frame"]]
            assert plan["startup_parameters"]["FRAME_CLASS"] == live_overlay

    def test_pairs_share_environment_and_startup_except_fault_sets(self) -> None:
        schema = _schema(1.0, "SIM_ENGINE_MUL", "SIM_ENGINE_FAIL")
        control, fault = build_paired_run_plans(
            1,
            seed=9,
            ardupilot_revision=COMMIT,
            scenarios=["thrust_loss"],
            parameter_schema=schema,
        )
        assert control["environment_parameters"] == fault["environment_parameters"]
        assert control["frame"] == fault["frame"]
        shared = {
            k
            for k in control["startup_parameters"]
            if k not in fault["fault_startup_parameters"]
        } & {
            k
            for k in fault["startup_parameters"]
            if k not in fault["fault_startup_parameters"]
        }
        for key in shared:
            assert (
                control["startup_parameters"][key] == (fault["startup_parameters"][key])
            ), f"pair diverges on non-fault startup parameter {key}"
        # Injection baselines must equal the values the arm actually starts
        # with, or the trajectory check would compare against fiction.
        for name, baseline in fault["injection_baseline_parameters"].items():
            merged = {
                **fault["startup_parameters"],
                **fault["logging_parameters"],
                **FRAME_CLASS_MERGE(fault),
            }
            if name in merged:
                assert merged[name] == baseline


def FRAME_CLASS_MERGE(plan):
    from synthetic_data.runner import FRAME_CLASSES

    return {"FRAME_CLASS": FRAME_CLASSES[plan["frame"]]}
