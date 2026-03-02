#!/usr/bin/env python3
"""
detect_high_vibration.py — Physics-based high-vibration detector.

Uses VIBE messages from an ArduPilot .BIN dataflash log to flag excessive
vibration that can corrupt the IMU/EKF and cause a crash.

Physics rationale
-----------------
ArduPilot's IMU logging records acceleration variance in m/s² per axis (VibeX,
VibeY, VibeZ) plus accelerometer clipping counters (Clip0, Clip1, Clip2).

  * Healthy flight: VibeX/Y/Z typically < 15 m/s²
  * Warning range: > 30 m/s² on any axis
  * Critical / EKF corruption risk: > 60 m/s²
  * Any clipping events: immediate red flag (ADC rail saturation)

When SIM_VIB_AMP / SIM_VIB_FREQ are injected in SITL, VibeZ typically spikes
first and clipping counters accumulate rapidly.

Usage
-----
    python3 scripts/detect_high_vibration.py <path_to_log.BIN> [--verbose]

Exit codes
----------
    0  No vibration fault detected
    1  Fault detected
    2  Log file could not be read
"""

import argparse
import sys
from pymavlink import DFReader

# ── Tunable thresholds ──────────────────────────────────────────────────────
VIBE_WARN_MS2 = 30.0    # vibration warning threshold (m/s²)
VIBE_FAIL_MS2 = 60.0    # vibration critical threshold (m/s²)
MIN_SAMPLES = 5          # minimum VIBE samples required for diagnosis
# ────────────────────────────────────────────────────────────────────────────


def _parse_vibe(filepath: str) -> list:
    """Read all VIBE messages from a .BIN log file.

    Returns a list of dicts with keys: time_us, vibe_x, vibe_y, vibe_z,
    clip0, clip1, clip2.

    Raises ``IOError`` if the file cannot be opened.
    """
    try:
        log = DFReader.DFReader_binary(filepath)
    except Exception as exc:
        raise IOError(f"Cannot open log file '{filepath}': {exc}") from exc

    records = []
    try:
        while True:
            msg = log.recv_msg()
            if msg is None:
                break
            if msg.get_type() != "VIBE":
                continue
            records.append({
                "time_us": float(getattr(msg, "TimeUS", 0.0)),
                "vibe_x": float(getattr(msg, "VibeX", 0.0)),
                "vibe_y": float(getattr(msg, "VibeY", 0.0)),
                "vibe_z": float(getattr(msg, "VibeZ", 0.0)),
                "clip0": float(getattr(msg, "Clip0", 0.0)),
                "clip1": float(getattr(msg, "Clip1", 0.0)),
                "clip2": float(getattr(msg, "Clip2", 0.0)),
            })
    except Exception:
        pass  # truncated log

    return records


def analyze(filepath: str, verbose: bool = False) -> dict:
    """Analyse VIBE data in *filepath* and return a result dict.

    The returned dict has the following keys:

    * ``fault`` (bool) — True if a vibration fault was detected.
    * ``fault_type`` (str|None) — ``'vibration_high'`` or None.
    * ``confidence`` (float) — 0.0–1.0 confidence score.
    * ``evidence`` (list) — list of evidence dicts.
    * ``first_fault_time_sec`` (float|None) — earliest timestamp of fault onset.
    * ``summary`` (str) — human-readable summary line.
    """
    records = _parse_vibe(filepath)

    result = {
        "fault": False,
        "fault_type": None,
        "confidence": 0.0,
        "evidence": [],
        "first_fault_time_sec": None,
        "summary": "No vibration fault detected.",
    }

    if len(records) < MIN_SAMPLES:
        result["summary"] = (
            f"Insufficient VIBE data ({len(records)} samples — need {MIN_SAMPLES})."
        )
        return result

    first_t = records[0]["time_us"]
    x_vals = [r["vibe_x"] for r in records]
    y_vals = [r["vibe_y"] for r in records]
    z_vals = [r["vibe_z"] for r in records]
    clip_total = sum(r["clip0"] + r["clip1"] + r["clip2"] for r in records)

    x_max = max(x_vals)
    y_max = max(y_vals)
    z_max = max(z_vals)

    if verbose:
        print(f"  VIBE samples : {len(records)}")
        print(f"  VibeX max    : {x_max:.1f} m/s²")
        print(f"  VibeY max    : {y_max:.1f} m/s²")
        print(f"  VibeZ max    : {z_max:.1f} m/s²")
        print(f"  Clip total   : {clip_total:.0f}")

    evidence = []
    confidence = 0.0
    first_fault_us = None

    # ── Per-axis checks ─────────────────────────────────────────────────────
    for axis, vals, ax_max in [("x", x_vals, x_max), ("y", y_vals, y_max), ("z", z_vals, z_max)]:
        if ax_max > VIBE_FAIL_MS2:
            confidence += 0.20
            evidence.append({
                "feature": f"vibe_{axis}_max",
                "value": round(ax_max, 2),
                "threshold": VIBE_FAIL_MS2,
            })
            # Find first sample that exceeded the threshold
            for rec, val in zip(records, vals):
                if val > VIBE_FAIL_MS2:
                    if first_fault_us is None or rec["time_us"] < first_fault_us:
                        first_fault_us = rec["time_us"]
                    break
        elif ax_max > VIBE_WARN_MS2:
            confidence += 0.10
            evidence.append({
                "feature": f"vibe_{axis}_max",
                "value": round(ax_max, 2),
                "threshold": VIBE_WARN_MS2,
            })
            for rec, val in zip(records, vals):
                if val > VIBE_WARN_MS2:
                    if first_fault_us is None or rec["time_us"] < first_fault_us:
                        first_fault_us = rec["time_us"]
                    break

    # ── Clipping ────────────────────────────────────────────────────────────
    if clip_total > 0:
        confidence += 0.30
        evidence.append({
            "feature": "vibe_clip_total",
            "value": float(clip_total),
            "threshold": 0,
        })
        if clip_total > 100:
            confidence += 0.20  # very severe clipping

    confidence = min(confidence, 1.0)

    if confidence >= 0.25 and evidence:
        result["fault"] = True
        result["fault_type"] = "vibration_high"
        result["confidence"] = round(confidence, 3)
        result["evidence"] = evidence
        if first_fault_us is not None:
            result["first_fault_time_sec"] = round(
                (first_fault_us - first_t) / 1e6, 2
            )
        severity = "critical" if confidence >= 0.6 else "warning"
        result["summary"] = (
            f"FAULT DETECTED: vibration_high  "
            f"(severity={severity}, confidence={confidence:.0%}, "
            f"{len(evidence)} evidence item(s))"
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Detect high vibration in an ArduPilot .BIN log."
    )
    parser.add_argument("logfile", help="Path to ArduPilot .BIN dataflash log")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print raw feature values"
    )
    args = parser.parse_args()

    try:
        result = analyze(args.logfile, verbose=args.verbose)
    except IOError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    print(result["summary"])
    if result["evidence"]:
        for ev in result["evidence"]:
            print(f"  [{ev['feature']}] value={ev['value']}  threshold={ev['threshold']}")
    if result["first_fault_time_sec"] is not None:
        print(f"  First fault onset: {result['first_fault_time_sec']} s into flight")

    sys.exit(1 if result["fault"] else 0)


if __name__ == "__main__":
    main()
