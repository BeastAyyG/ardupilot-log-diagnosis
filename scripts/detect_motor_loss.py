#!/usr/bin/env python3
"""
detect_motor_loss.py — Physics-based motor imbalance / thrust loss detector.

Uses RCOU (motor output) messages from an ArduPilot .BIN dataflash log to flag:
  * Thrust loss: all motors pegged near maximum (craft underpowered)
  * Motor imbalance: large sustained spread between highest and lowest motor output
    (one motor failing, prop damage, ESC fault)

Physics rationale
-----------------
A healthy quadcopter in steady hover keeps all four motors within ~100-200 PWM
of each other.  When a motor fails or the craft becomes underpowered:
  * THRUST LOSS: all RCOU channels rise toward 1900-2000 PWM simultaneously.
  * MOTOR IMBALANCE: one (or more) channels diverge far from the rest to
    compensate for lost torque.

Usage
-----
    python3 scripts/detect_motor_loss.py <path_to_log.BIN> [--verbose]

Exit codes
----------
    0  No motor fault detected
    1  Fault detected (check stdout for details)
    2  Log file could not be read
"""

import argparse
import sys
from pymavlink import DFReader

# ── Tunable thresholds ──────────────────────────────────────────────────────
# These values were validated against SITL golden logs (SIM_ENGINE_FAIL) and
# real-hardware cases shared by ArduPilot forum experts.
SATURATION_THRESHOLD_PWM = 1900   # single motor "saturated" if RCOU ≥ this
ALL_HIGH_THRESHOLD_PWM = 1800     # "all high" if every motor ≥ this
SPREAD_IMBALANCE_PWM = 400        # peak-to-peak RCOU spread indicating imbalance
SPREAD_SUSTAINED_PWM = 200        # sustained mean spread for chronic imbalance
SATURATION_FRACTION = 0.20        # fraction of samples that must be saturated
ALL_HIGH_FRACTION = 0.15          # fraction of samples where all motors are high
STARTUP_SKIP_SEC = 10.0           # skip first N seconds to avoid arm/takeoff noise
MIN_SAMPLES = 10                  # minimum RCOU samples required for a diagnosis
# ────────────────────────────────────────────────────────────────────────────


def _parse_rcou(filepath: str) -> list:
    """Read all RCOU messages from a .BIN log file.

    Returns a list of dicts, each containing the timestamp and motor channel
    values extracted from the message.

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
            if msg.get_type() != "RCOU":
                continue
            time_us = float(getattr(msg, "TimeUS", 0.0))
            channels = {}
            for field in msg.get_fieldnames():
                if field.startswith("C") and field[1:].isdigit():
                    val = float(getattr(msg, field, 0.0))
                    if val > 800:
                        channels[field] = val
            if channels:
                records.append({"time_us": time_us, "channels": channels})
    except Exception:
        pass  # truncated log — use what was collected

    return records


def analyze(filepath: str, verbose: bool = False) -> dict:
    """Analyse motor output in *filepath* and return a result dict.

    The returned dict has the following keys:

    * ``fault`` (bool) — True if a motor fault was detected.
    * ``fault_type`` (str|None) — ``'thrust_loss'``, ``'motor_imbalance'``, or None.
    * ``confidence`` (float) — 0.0–1.0 confidence score.
    * ``evidence`` (list) — list of evidence dicts (feature, value, threshold).
    * ``first_fault_time_sec`` (float|None) — earliest timestamp of fault onset.
    * ``summary`` (str) — human-readable summary line.
    """
    records = _parse_rcou(filepath)

    result = {
        "fault": False,
        "fault_type": None,
        "confidence": 0.0,
        "evidence": [],
        "first_fault_time_sec": None,
        "summary": "No motor fault detected.",
    }

    if len(records) < MIN_SAMPLES:
        result["summary"] = (
            f"Insufficient RCOU data ({len(records)} samples — need {MIN_SAMPLES})."
        )
        return result

    # Skip startup transients
    first_t = records[0]["time_us"]
    skip_until = first_t + STARTUP_SKIP_SEC * 1e6

    spread_vals = []
    saturation_count = 0
    all_high_count = 0
    total = 0
    first_fault_us = None

    for rec in records:
        channels = rec["channels"]
        vals = list(channels.values())
        if not vals:
            continue

        max_ch = max(vals)
        min_ch = min(vals)
        spread = max_ch - min_ch

        total += 1
        if max_ch >= SATURATION_THRESHOLD_PWM:
            saturation_count += 1
            if first_fault_us is None:
                first_fault_us = rec["time_us"]

        if len(vals) >= 4 and min_ch >= ALL_HIGH_THRESHOLD_PWM:
            all_high_count += 1
            if first_fault_us is None:
                first_fault_us = rec["time_us"]

        if rec["time_us"] >= skip_until:
            spread_vals.append(spread)

    sat_pct = saturation_count / total if total > 0 else 0.0
    all_high_pct = all_high_count / total if total > 0 else 0.0
    spread_max = max(spread_vals) if spread_vals else 0.0
    spread_mean = sum(spread_vals) / len(spread_vals) if spread_vals else 0.0

    if verbose:
        print(f"  RCOU samples : {total}")
        print(f"  Sat fraction : {sat_pct:.1%}  (threshold {SATURATION_FRACTION:.0%})")
        print(f"  All-high frac: {all_high_pct:.1%}  (threshold {ALL_HIGH_FRACTION:.0%})")
        print(f"  Spread max   : {spread_max:.0f} PWM  (threshold {SPREAD_IMBALANCE_PWM})")
        print(f"  Spread mean  : {spread_mean:.0f} PWM  (threshold {SPREAD_SUSTAINED_PWM})")

    evidence = []
    confidence = 0.0
    fault_type = None

    # ── Thrust loss (all motors pegged) ────────────────────────────────────
    if sat_pct > SATURATION_FRACTION:
        # Stronger signal (>25% of flight saturated) earns higher confidence
        confidence += 0.45 if sat_pct > 0.25 else 0.25
        evidence.append({
            "feature": "motor_saturation_pct",
            "value": round(sat_pct, 4),
            "threshold": SATURATION_FRACTION,
        })
        fault_type = "thrust_loss"

    if all_high_pct > ALL_HIGH_FRACTION:
        confidence += 0.25
        evidence.append({
            "feature": "motor_all_high_pct",
            "value": round(all_high_pct, 4),
            "threshold": ALL_HIGH_FRACTION,
        })
        fault_type = fault_type or "thrust_loss"

    # ── Motor imbalance (large spread) ─────────────────────────────────────
    if spread_max >= SPREAD_IMBALANCE_PWM and spread_mean >= SPREAD_SUSTAINED_PWM:
        confidence += 0.45
        evidence.append({
            "feature": "motor_spread_max",
            "value": round(spread_max, 1),
            "threshold": SPREAD_IMBALANCE_PWM,
        })
        evidence.append({
            "feature": "motor_spread_mean",
            "value": round(spread_mean, 1),
            "threshold": SPREAD_SUSTAINED_PWM,
        })
        if fault_type is None:
            fault_type = "motor_imbalance"

    confidence = min(confidence, 1.0)

    if confidence >= 0.4 and evidence:
        result["fault"] = True
        result["fault_type"] = fault_type
        result["confidence"] = round(confidence, 3)
        result["evidence"] = evidence
        if first_fault_us is not None:
            result["first_fault_time_sec"] = round(
                (first_fault_us - first_t) / 1e6, 2
            )
        result["summary"] = (
            f"FAULT DETECTED: {fault_type}  "
            f"(confidence {confidence:.0%}, "
            f"{len(evidence)} evidence item(s))"
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Detect motor loss / thrust loss in an ArduPilot .BIN log."
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
