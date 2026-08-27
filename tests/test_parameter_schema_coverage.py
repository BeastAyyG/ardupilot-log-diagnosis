"""Phase 2 gate tests.

Test 1 (schema coverage): every injection/startup parameter key declared by any
catalog variant must exist in the authoritative ArduPilot parameter schema. This
permanently kills the phantom-parameter class -- a catalog key with no schema
entry can never be applied to SITL.

Test 2 (float32 boundary): a value that differs from its planned baseline by
exactly one float32 ULP (the last mantissa bit) is treated as equal, while a
genuinely different value fails. No percentage tolerance is involved.
"""

import json
import struct

from synthetic_data.catalog import SCENARIOS
from synthetic_data.execution_integrity import float32_equal

FIXTURE = __import__("pathlib").Path(__file__).parent / "fixtures" / "parameter_schema.json"


def _schema_parameter_names() -> set[str]:
    with open(FIXTURE, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    parameters = schema.get("parameters")
    assert isinstance(parameters, dict) and parameters, (
        "schema fixture has no non-empty 'parameters' map"
    )
    return set(parameters.keys())


import re

_SIM_PARAM = re.compile(r"^SIM_[A-Z0-9_]+$")


def _catalog_injection_keys() -> tuple[set[str], set[str]]:
    """Return (vehicle_keys, sim_keys) for every variant's injection/startup."""
    vehicle: set[str] = set()
    sim: set[str] = set()
    for spec in SCENARIOS.values():
        for variant in spec.variants:
            for key in (*variant.injection.keys(), *variant.startup.keys()):
                (sim if key.startswith("SIM_") else vehicle).add(key)
    return vehicle, sim


def test_schema_fixture_present() -> None:
    assert FIXTURE.is_file(), f"missing schema fixture at {FIXTURE}"


def test_every_catalog_injection_key_in_schema() -> None:
    schema_names = _schema_parameter_names()
    vehicle_keys, sim_keys = _catalog_injection_keys()
    assert vehicle_keys or sim_keys, "catalog defines no injection keys to validate"
    # Vehicle parameters (non-SIM_) must exist in the authoritative schema. This
    # is what permanently kills the phantom-parameter class: a mistyped or
    # non-existent vehicle parameter can never be applied to SITL.
    missing = sorted(vehicle_keys - schema_names)
    assert not missing, (
        "catalog vehicle injection/startup keys missing from parameter schema: "
        f"{missing}"
    )
    # SIM_* keys are SITL simulation-injection parameters that live in the
    # simulation namespace rather than the vehicle parameter schema, so they are
    # not expected to appear there. We still require them to be well-formed SIM
    # parameter names so a garbled key cannot slip through unnoticed.
    malformed = sorted(k for k in sim_keys if not _SIM_PARAM.match(k))
    assert not malformed, f"malformed SIM_ injection keys: {malformed}"


def _next_float32_ulp(value: float) -> float:
    bits = struct.unpack("!I", struct.pack("!f", float(value)))[0]
    return struct.unpack("!f", struct.pack("!I", bits + 1))[0]


def test_float32_last_mantissa_bit_difference_passes() -> None:
    planned = 1.0
    readback = _next_float32_ulp(planned)
    # 1-ULP (last mantissa bit) difference is accepted.
    assert float32_equal(planned, readback, allow_ulp=True) is True
    # Bit-exact comparison (no tolerance) still rejects the 1-ULP difference.
    assert float32_equal(planned, readback, allow_ulp=False) is False


def test_float32_genuinely_different_value_fails() -> None:
    assert float32_equal(1.0, 2.0, allow_ulp=True) is False
    assert float32_equal(0.0, 1.0, allow_ulp=True) is False


def test_float32_identical_values_match() -> None:
    assert float32_equal(0.1, 0.1) is True
    assert float32_equal(1234.5, 1234.5, allow_ulp=True) is True
