"""Fault-path unit tests for the strict DataFlash step-trajectory check.

These exercise ``synthetic_data.collector._observed_injection``, which enforces
the immutable baseline -> requested-value -> no-reset semantics on the raw
DataFlash PARM trajectory. Each case starts from a valid scenario and mutates a
single assumption so the collector must reject fail-closed.
"""

from __future__ import annotations

import pytest

from synthetic_data.collector import _observed_injection
from synthetic_data.integrity import VerificationError

NAME = "SIM_TEST_0"
BASELINE = 0.0
VALUE = 5.0
ONSET_SEC = 10.0
TAKEOFF_BOOT_MS = 1000.0
SCHEDULED_ONSET_BOOT_MS = TAKEOFF_BOOT_MS + ONSET_SEC * 1000.0


def _parm(time_us: float, value: float, name: str = NAME) -> dict:
    return {"Name": name, "TimeUS": time_us, "Value": value}


def _build_valid():
    plan = {
        "injection_parameters": {NAME: VALUE},
        "injection_baseline_parameters": {NAME: BASELINE},
        "planned_fault_onset_sec": ONSET_SEC,
    }
    receipt = {
        "takeoff_boot_ms": TAKEOFF_BOOT_MS,
        "scheduled_onset_boot_ms": SCHEDULED_ONSET_BOOT_MS,
    }
    acknowledgements = [
        {
            "name": NAME,
            "acknowledged": True,
            "requested": VALUE,
            "readback": VALUE,
            "send_boot_ms": SCHEDULED_ONSET_BOOT_MS,
            "ack_boot_ms": SCHEDULED_ONSET_BOOT_MS + 50.0,
            "readback_boot_ms": SCHEDULED_ONSET_BOOT_MS + 100.0,
            "attempts": 1,
        }
    ]
    parsed = {
        "messages": {
            "PARM": [
                _parm(5_000_000, BASELINE),
                _parm(SCHEDULED_ONSET_BOOT_MS * 1000, VALUE),
            ],
            "ANY": [{"_timestamp": 0.0}],
        }
    }
    return parsed, plan, receipt, acknowledgements


def test_valid_trajectory_is_accepted() -> None:
    parsed, plan, receipt, acks = _build_valid()
    onset_sec, onset_absolute, observed = _observed_injection(
        parsed, plan, receipt, acks
    )
    assert observed
    assert onset_sec is not None and onset_absolute is not None


def test_baseline_names_mismatch() -> None:
    parsed, plan, receipt, acks = _build_valid()
    plan = dict(plan)
    plan["injection_baseline_parameters"] = {"OTHER": 0.0}
    with pytest.raises(VerificationError, match="baselines"):
        _observed_injection(parsed, plan, receipt, acks)


def test_duplicate_acknowledgement() -> None:
    parsed, plan, receipt, acks = _build_valid()
    acks = acks + [dict(acks[0])]
    with pytest.raises(VerificationError, match="duplicate"):
        _observed_injection(parsed, plan, receipt, acks)


def test_missing_acknowledgement() -> None:
    parsed, plan, receipt, acks = _build_valid()
    with pytest.raises(VerificationError, match="differs"):
        _observed_injection(parsed, plan, receipt, [])


def test_healthy_run_with_acknowledgements() -> None:
    parsed, plan, receipt, acks = _build_valid()
    plan = dict(plan)
    plan["injection_parameters"] = {}
    plan["injection_baseline_parameters"] = {}
    with pytest.raises(VerificationError, match="unexpected fault"):
        _observed_injection(parsed, plan, receipt, acks)


def test_receipt_missing_onset_timing() -> None:
    parsed, plan, receipt, acks = _build_valid()
    receipt = dict(receipt)
    del receipt["scheduled_onset_boot_ms"]
    with pytest.raises(VerificationError, match="scheduled onset timing"):
        _observed_injection(parsed, plan, receipt, acks)


def test_scheduled_onset_differs_from_plan() -> None:
    parsed, plan, receipt, acks = _build_valid()
    receipt = dict(receipt)
    receipt["scheduled_onset_boot_ms"] = SCHEDULED_ONSET_BOOT_MS + 5000.0
    with pytest.raises(VerificationError, match="immutable plan"):
        _observed_injection(parsed, plan, receipt, acks)


def test_acknowledgement_not_confirmed() -> None:
    parsed, plan, receipt, acks = _build_valid()
    acks = [dict(acks[0], acknowledged=False)]
    with pytest.raises(VerificationError, match="negative or missing"):
        _observed_injection(parsed, plan, receipt, acks)


def test_request_differs_from_plan() -> None:
    parsed, plan, receipt, acks = _build_valid()
    acks = [dict(acks[0], requested=VALUE + 1.0)]
    with pytest.raises(VerificationError, match="request differs"):
        _observed_injection(parsed, plan, receipt, acks)


def test_readback_differs_from_plan() -> None:
    parsed, plan, receipt, acks = _build_valid()
    acks = [dict(acks[0], readback=VALUE + 1.0)]
    with pytest.raises(VerificationError, match="readback differs"):
        _observed_injection(parsed, plan, receipt, acks)


def test_timing_order_invalid() -> None:
    parsed, plan, receipt, acks = _build_valid()
    acks = [dict(acks[0], send_boot_ms=SCHEDULED_ONSET_BOOT_MS + 200.0)]
    with pytest.raises(VerificationError, match="timing order"):
        _observed_injection(parsed, plan, receipt, acks)


def test_lacks_parm_trajectory() -> None:
    parsed, plan, receipt, acks = _build_valid()
    parsed = {"messages": {"ANY": [{"_timestamp": 0.0}]}}
    with pytest.raises(VerificationError, match="PARM trajectory"):
        _observed_injection(parsed, plan, receipt, acks)


def test_injection_equals_baseline() -> None:
    parsed, plan, receipt, acks = _build_valid()
    plan = dict(plan)
    plan["injection_parameters"] = {NAME: BASELINE}
    plan["injection_baseline_parameters"] = {NAME: BASELINE}
    acks = [dict(acks[0], requested=BASELINE, readback=BASELINE)]
    with pytest.raises(VerificationError, match="equals its baseline"):
        _observed_injection(parsed, plan, receipt, acks)


def test_no_proving_parm_record() -> None:
    parsed, plan, receipt, acks = _build_valid()
    parsed = {
        "messages": {
            "PARM": [_parm(5_000_000, BASELINE)],
            "ANY": [{"_timestamp": 0.0}],
        }
    }
    with pytest.raises(VerificationError, match="prove injection"):
        _observed_injection(parsed, plan, receipt, acks)


def test_unstable_preinjection_baseline() -> None:
    parsed, plan, receipt, acks = _build_valid()
    parsed = {
        "messages": {
            "PARM": [
                _parm(5_000_000, VALUE),
                _parm(SCHEDULED_ONSET_BOOT_MS * 1000, VALUE),
            ],
            "ANY": [{"_timestamp": 0.0}],
        }
    }
    with pytest.raises(VerificationError, match="stable pre-injection baseline"):
        _observed_injection(parsed, plan, receipt, acks)


def test_reset_after_injection() -> None:
    parsed, plan, receipt, acks = _build_valid()
    parsed = {
        "messages": {
            "PARM": [
                _parm(5_000_000, BASELINE),
                _parm(SCHEDULED_ONSET_BOOT_MS * 1000, VALUE),
                _parm(SCHEDULED_ONSET_BOOT_MS * 1000 + 2_000_000, BASELINE),
            ],
            "ANY": [{"_timestamp": 0.0}],
        }
    }
    with pytest.raises(VerificationError, match="reset or alternate"):
        _observed_injection(parsed, plan, receipt, acks)


def test_change_count_exceeds_attempts() -> None:
    parsed, plan, receipt, acks = _build_valid()
    acks = [dict(acks[0], attempts=0)]
    with pytest.raises(VerificationError, match="bounded attempts"):
        _observed_injection(parsed, plan, receipt, acks)
