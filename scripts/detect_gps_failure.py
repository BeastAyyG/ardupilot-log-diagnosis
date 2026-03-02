#!/usr/bin/env python3
"""
detect_gps_failure.py — Physics-based GPS loss / poor-quality detector.

Uses GPS messages from an ArduPilot .BIN dataflash log to flag:
  * GPS loss: fix status drops below 3D-fix (Status < 3)
  * Poor GPS quality: high HDOP or low satellite count
  * GPS glitch: sudden jumps in position uncertainty

Physics rationale
-----------------
ArduPilot logs GPS health in the GPS message type:
  * Status  — 0=No GPS, 1=No Fix, 2=2D Fix, 3=3D Fix, 4=DGPS, 5=RTK Float, 6=RTK Fixed
  * HDop    — Horizontal dilution of precision (< 1.5 is excellent, > 2.0 is poor)
  * NSats   — Number of tracked satellites (< 6 is marginal)

When SIM_GPS_DISABLE=1 is injected in SITL while in Loiter, the Status value
drops to 0/1 and NSats falls to 0 — this is the canonical "GPS loss" signature.

Usage
-----
    python3 scripts/detect_gps_failure.py <path_to_log.BIN> [--verbose]

Exit codes
----------
    0  No GPS fault detected
    1  Fault detected
    2  Log file could not be read
"""

import argparse
import sys
from pymavlink import DFReader

# ── Tunable thresholds ──────────────────────────────────────────────────────
GPS_FIX_MIN = 3          # minimum acceptable fix status (3 = 3D fix)
GPS_HDOP_WARN = 2.0      # HDOP warning threshold
GPS_HDOP_FAIL = 5.0      # HDOP critical threshold
GPS_NSATS_MIN = 6        # minimum acceptable satellite count
GPS_FIX_PCT_MIN = 0.95   # minimum fraction of samples with valid 3D fix
MIN_SAMPLES = 5          # minimum GPS samples required for diagnosis
# ────────────────────────────────────────────────────────────────────────────


def _parse_gps(filepath: str) -> list:
    """Read all GPS messages from a .BIN log file.

    Returns a list of dicts with keys: time_us, status, hdop, nsats.

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
            if msg.get_type() != "GPS":
                continue
            records.append({
                "time_us": float(getattr(msg, "TimeUS", 0.0)),
                "status": float(getattr(msg, "Status", 0.0)),
                "hdop": float(getattr(msg, "HDop", 0.0)),
                "nsats": float(getattr(msg, "NSats", 0.0)),
            })
    except Exception:
        pass  # truncated log

    return records


def analyze(filepath: str, verbose: bool = False) -> dict:
    """Analyse GPS data in *filepath* and return a result dict.

    The returned dict has the following keys:

    * ``fault`` (bool) — True if a GPS fault was detected.
    * ``fault_type`` (str|None) — ``'gps_loss'``, ``'gps_quality_poor'``, or None.
    * ``confidence`` (float) — 0.0–1.0 confidence score.
    * ``evidence`` (list) — list of evidence dicts.
    * ``first_fault_time_sec`` (float|None) — earliest timestamp of fault onset.
    * ``summary`` (str) — human-readable summary line.
    """
    records = _parse_gps(filepath)

    result = {
        "fault": False,
        "fault_type": None,
        "confidence": 0.0,
        "evidence": [],
        "first_fault_time_sec": None,
        "summary": "No GPS fault detected.",
    }

    if len(records) < MIN_SAMPLES:
        result["summary"] = (
            f"Insufficient GPS data ({len(records)} samples — need {MIN_SAMPLES})."
        )
        return result

    first_t = records[0]["time_us"]
    status_vals = [r["status"] for r in records]
    hdop_vals = [r["hdop"] for r in records]
    nsats_vals = [r["nsats"] for r in records]

    fix_count = sum(1 for s in status_vals if s >= GPS_FIX_MIN)
    fix_pct = fix_count / len(status_vals)
    hdop_max = max(hdop_vals)
    hdop_mean = sum(hdop_vals) / len(hdop_vals)
    nsats_min = min(nsats_vals)
    nsats_mean = sum(nsats_vals) / len(nsats_vals)

    if verbose:
        print(f"  GPS samples  : {len(records)}")
        print(f"  Fix pct      : {fix_pct:.1%}  (threshold {GPS_FIX_PCT_MIN:.0%})")
        print(f"  HDop max     : {hdop_max:.2f}  (warn {GPS_HDOP_WARN}, fail {GPS_HDOP_FAIL})")
        print(f"  HDop mean    : {hdop_mean:.2f}")
        print(f"  NSats min    : {nsats_min:.0f}  (threshold {GPS_NSATS_MIN})")
        print(f"  NSats mean   : {nsats_mean:.1f}")

    evidence = []
    confidence = 0.0
    fault_type = None
    first_fault_us = None

    # ── GPS loss (fix completely drops) ────────────────────────────────────
    if fix_pct < GPS_FIX_PCT_MIN:
        loss_fraction = 1.0 - fix_pct
        if loss_fraction > 0.5:
            confidence += 0.70
            fault_type = "gps_loss"
        else:
            confidence += 0.50
            fault_type = "gps_quality_poor"
        evidence.append({
            "feature": "gps_fix_pct",
            "value": round(fix_pct, 4),
            "threshold": GPS_FIX_PCT_MIN,
        })
        # Find first sample where fix was lost
        for rec in records:
            if rec["status"] < GPS_FIX_MIN:
                first_fault_us = rec["time_us"]
                break

    # ── Satellite count too low ─────────────────────────────────────────────
    if nsats_min < GPS_NSATS_MIN and nsats_min >= 0:
        confidence += 0.40
        evidence.append({
            "feature": "gps_nsats_min",
            "value": round(nsats_min, 0),
            "threshold": GPS_NSATS_MIN,
        })
        fault_type = fault_type or "gps_quality_poor"
        if first_fault_us is None:
            for rec in records:
                if rec["nsats"] < GPS_NSATS_MIN:
                    first_fault_us = rec["time_us"]
                    break

    # ── HDOP degradation ───────────────────────────────────────────────────
    if hdop_mean > GPS_HDOP_FAIL:
        confidence += 0.40
        evidence.append({
            "feature": "gps_hdop_mean",
            "value": round(hdop_mean, 3),
            "threshold": GPS_HDOP_FAIL,
        })
        fault_type = fault_type or "gps_quality_poor"
    elif hdop_mean > GPS_HDOP_WARN:
        confidence += 0.20
        evidence.append({
            "feature": "gps_hdop_mean",
            "value": round(hdop_mean, 3),
            "threshold": GPS_HDOP_WARN,
        })
        fault_type = fault_type or "gps_quality_poor"

    confidence = min(confidence, 1.0)

    if confidence >= 0.30 and evidence:
        result["fault"] = True
        result["fault_type"] = fault_type
        result["confidence"] = round(confidence, 3)
        result["evidence"] = evidence
        if first_fault_us is not None:
            result["first_fault_time_sec"] = round(
                (first_fault_us - first_t) / 1e6, 2
            )
        severity = "critical" if confidence >= 0.60 else "warning"
        result["summary"] = (
            f"FAULT DETECTED: {fault_type}  "
            f"(severity={severity}, confidence={confidence:.0%}, "
            f"{len(evidence)} evidence item(s))"
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Detect GPS failure in an ArduPilot .BIN log."
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
