"""Verify the SITL randomization catalog against a captured parameter inventory.

Reads a ``parameter_inventory.parm`` captured live from the pinned firmware
(the same artifact every paired CI run produces) and reports, per catalog
entry, whether the parameter exists on the pinned build, its captured
baseline value, and the planned randomization envelope. Exit code 2 when one
or more catalog parameters are missing so callers can treat capability loss
as evidence rather than silently randomizing nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from synthetic_data.randomization import RANDOMIZATION_CATALOG


def load_inventory(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, _, raw = stripped.partition("=")
        values[name.strip()] = float(raw)
    return values


def verify_inventory(values: dict[str, float]) -> dict:
    entries = {}
    missing = []
    for spec in RANDOMIZATION_CATALOG:
        present = spec.name in values
        if not present:
            missing.append(spec.name)
        entries[spec.name] = {
            "present": present,
            "captured_baseline": values.get(spec.name),
            "low": spec.low,
            "high": spec.high,
            "physical_system": spec.physical_system,
            "rationale": spec.rationale,
        }
    by_system: dict[str, int] = {}
    for entry in entries.values():
        if entry["present"]:
            by_system[entry["physical_system"]] = (
                by_system.get(entry["physical_system"], 0) + 1
            )
    return {
        "schema": "logdiagnosis.randomization-verification/v1",
        "inventory_parameter_count": len(values),
        "catalog_size": len(RANDOMIZATION_CATALOG),
        "verified_count": len(RANDOMIZATION_CATALOG) - len(missing),
        "missing_parameters": missing,
        "verified_physical_systems": dict(sorted(by_system.items())),
        "parameters": dict(sorted(entries.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = verify_inventory(load_inventory(args.inventory))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"randomization verification: {report['verified_count']}/"
        f"{report['catalog_size']} parameters present; "
        f"missing={report['missing_parameters']}"
    )
    return 2 if report["missing_parameters"] else 0


if __name__ == "__main__":
    sys.exit(main())
