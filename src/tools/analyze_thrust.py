"""
analyze_thrust.py — Comprehensive thrust-loss / underpowered-aircraft analyser.

Combines RCOU (motor output) and CTUN (control tuning) signals for a
multi-signal diagnosis of thrust loss — the exact failure mode identified
by ArduPilot forum expert dkemxr:

  "This craft was underpowered to start with and by the end of the flight
   the motors were being commanded to maximum producing the very easy to
   see Thrust Loss errors."

Signal chain
------------
1. RCOU  — Raw motor commands. Thrust loss: all channels → 1900-2000 PWM.
2. CTUN  — Control tuning. Thrust loss: ThO (throttle output) → 1.0 (100%),
            altErr (altitude error) grows uncontrolled.

Both signals must agree for high-confidence diagnosis.  If only RCOU is
available the tool still works (many older logs lack CTUN).

Usage
-----
    python3 scripts/analyze_thrust.py <path_to_log.BIN> [--verbose] [--json]

    --json  Output machine-readable JSON instead of formatted text.

Exit codes
----------
    0  No thrust fault detected
    1  Thrust fault detected
    2  Log file could not be read
"""

import argparse
import json
import sys
from pymavlink import DFReader

# ── Tunable thresholds ──────────────────────────────────────────────────────
RCOU_SATURATION_PWM = 1900    # motor output "saturated" if ≥ this
RCOU_ALL_HIGH_PWM = 1800      # "all high" if every motor ≥ this
RCOU_SATURATION_FRAC = 0.20   # fraction of samples that must be saturated
RCOU_ALL_HIGH_FRAC = 0.15     # fraction of samples where all motors are high
CTUN_THO_SATURATION = 0.95    # throttle output fraction considered saturated
CTUN_THO_FRAC = 0.20          # fraction of CTUN samples with ThO saturated
CTUN_ALT_ERR_MAX = 5.0        # altitude error (m) indicating loss of alt hold
STARTUP_SKIP_SEC = 10.0       # skip first N seconds to avoid arm/takeoff noise
MIN_RCOU_SAMPLES = 10         # minimum RCOU samples required
# ────────────────────────────────────────────────────────────────────────────


def _parse_log(filepath: str) -> tuple:
    """Parse RCOU and CTUN messages from *filepath*.

    Returns ``(rcou_records, ctun_records)`` where each is a list of dicts.
    Raises ``IOError`` if the file cannot be opened.
    """
    try:
        log = DFReader.DFReader_binary(filepath)
    except Exception as exc:
        raise IOError(f"Cannot open log file '{filepath}': {exc}") from exc

    rcou_records = []
    ctun_records = []
    try:
        while True:
            msg = log.recv_msg()
            if msg is None:
                break
            msg_type = msg.get_type()
            if msg_type == "RCOU":
                time_us = float(getattr(msg, "TimeUS", 0.0))
                channels = {}
                for field in msg.get_fieldnames():
                    if (field.startswith("C") and field[1:].isdigit()) or (field.startswith("Ch") and field[2:].isdigit()):
                        val = float(getattr(msg, field, 0.0))
                        if val > 800:
                            channels[field] = val
                if channels:
                    rcou_records.append({"time_us": time_us, "channels": channels})
            elif msg_type == "CTUN":
                ctun_records.append({
                    "time_us": float(getattr(msg, "TimeUS", 0.0)),
                    "tho": float(getattr(msg, "ThO", 0.0)),
                    # DAlt = desired (target) altitude; Alt = actual altitude
                    "alt_err": abs(float(getattr(msg, "DAlt", 0.0))
                                   - float(getattr(msg, "Alt", 0.0))),
                })
    except Exception:
        pass  # truncated log — use what was collected

    return rcou_records, ctun_records


def _analyze_rcou(rcou_records: list, verbose: bool) -> tuple:
    """Return (confidence_contribution, evidence_list, first_fault_us)."""
    if not rcou_records:
        return 0.0, [], None

    first_t = rcou_records[0]["time_us"]
    skip_until = first_t + STARTUP_SKIP_SEC * 1e6

    spread_vals = []
    saturation_count = 0
    all_high_count = 0
    total = 0
    first_fault_us = None

    for rec in rcou_records:
        vals = list(rec["channels"].values())
        if not vals:
            continue
        max_ch = max(vals)
        min_ch = min(vals)

        total += 1
        if max_ch >= RCOU_SATURATION_PWM:
            saturation_count += 1
            if first_fault_us is None:
                first_fault_us = rec["time_us"]
        if len(vals) >= 4 and min_ch >= RCOU_ALL_HIGH_PWM:
            all_high_count += 1
            if first_fault_us is None:
                first_fault_us = rec["time_us"]
        if rec["time_us"] >= skip_until:
            spread_vals.append(max_ch - min_ch)

    sat_pct = saturation_count / total if total > 0 else 0.0
    all_high_pct = all_high_count / total if total > 0 else 0.0

    if verbose:
        print(f"  [RCOU] samples={total}  sat={sat_pct:.1%}  all_high={all_high_pct:.1%}")

    conf = 0.0
    evidence = []

    if sat_pct > RCOU_SATURATION_FRAC:
        conf += 0.45 if sat_pct > 0.25 else 0.25
        evidence.append({
            "signal": "RCOU",
            "feature": "motor_saturation_pct",
            "value": round(sat_pct, 4),
            "threshold": RCOU_SATURATION_FRAC,
            "meaning": "fraction of samples where any motor output ≥ 1900 PWM",
        })

    if all_high_pct > RCOU_ALL_HIGH_FRAC:
        conf += 0.25
        evidence.append({
            "signal": "RCOU",
            "feature": "motor_all_high_pct",
            "value": round(all_high_pct, 4),
            "threshold": RCOU_ALL_HIGH_FRAC,
            "meaning": "fraction of samples where ALL motors ≥ 1800 PWM simultaneously",
        })

    return conf, evidence, first_fault_us


def _analyze_ctun(ctun_records: list, verbose: bool) -> tuple:
    """Return (confidence_contribution, evidence_list, first_fault_us)."""
    if not ctun_records:
        return 0.0, [], None

    total = len(ctun_records)
    tho_sat_count = sum(1 for r in ctun_records if r["tho"] >= CTUN_THO_SATURATION)
    tho_sat_pct = tho_sat_count / total
    alt_err_max = max(r["alt_err"] for r in ctun_records)

    if verbose:
        print(f"  [CTUN] samples={total}  tho_sat={tho_sat_pct:.1%}  alt_err_max={alt_err_max:.1f}m")

    conf = 0.0
    evidence = []
    first_fault_us = None

    if tho_sat_pct > CTUN_THO_FRAC:
        conf += 0.20
        evidence.append({
            "signal": "CTUN",
            "feature": "ctrl_thr_saturated_pct",
            "value": round(tho_sat_pct, 4),
            "threshold": CTUN_THO_FRAC,
            "meaning": "fraction of samples where throttle output ≥ 95%",
        })
        # First time throttle was saturated
        for rec in ctun_records:
            if rec["tho"] >= CTUN_THO_SATURATION:
                first_fault_us = rec["time_us"]
                break

    if alt_err_max > CTUN_ALT_ERR_MAX:
        conf += 0.10
        evidence.append({
            "signal": "CTUN",
            "feature": "ctrl_alt_error_max",
            "value": round(alt_err_max, 2),
            "threshold": CTUN_ALT_ERR_MAX,
            "meaning": "maximum altitude error between desired and actual altitude (m)",
        })

    return conf, evidence, first_fault_us


def analyze(filepath: str, verbose: bool = False) -> dict:
    """Comprehensive thrust-loss analysis of *filepath*.

    Returns a result dict with keys:

    * ``fault`` (bool)
    * ``fault_type`` (str|None) — ``'thrust_loss'`` or None
    * ``confidence`` (float) — 0.0–1.0
    * ``evidence`` (list) — per-signal evidence items
    * ``first_fault_time_sec`` (float|None)
    * ``rcou_available`` (bool)
    * ``ctun_available`` (bool)
    * ``summary`` (str)
    * ``recommendations`` (list[str]) — actionable next checks
    """
    rcou_records, ctun_records = _parse_log(filepath)

    result = {
        "fault": False,
        "fault_type": None,
        "confidence": 0.0,
        "evidence": [],
        "first_fault_time_sec": None,
        "rcou_available": len(rcou_records) >= MIN_RCOU_SAMPLES,
        "ctun_available": len(ctun_records) > 0,
        "summary": "No thrust fault detected.",
        "recommendations": [],
    }

    if len(rcou_records) < MIN_RCOU_SAMPLES:
        result["summary"] = (
            f"Insufficient RCOU data ({len(rcou_records)} samples — need {MIN_RCOU_SAMPLES}). "
            "Cannot diagnose thrust loss."
        )
        return result

    first_t = rcou_records[0]["time_us"]

    rcou_conf, rcou_ev, rcou_fault_us = _analyze_rcou(rcou_records, verbose)
    ctun_conf, ctun_ev, ctun_fault_us = _analyze_ctun(ctun_records, verbose)

    total_conf = min(rcou_conf + ctun_conf, 1.0)
    evidence = rcou_ev + ctun_ev

    # Determine first fault onset timestamp (earliest of RCOU or CTUN)
    fault_candidates = [t for t in [rcou_fault_us, ctun_fault_us] if t is not None]
    first_fault_us = min(fault_candidates) if fault_candidates else None

    if total_conf >= 0.40 and evidence:
        result["fault"] = True
        result["fault_type"] = "thrust_loss"
        result["confidence"] = round(total_conf, 3)
        result["evidence"] = evidence
        if first_fault_us is not None:
            result["first_fault_time_sec"] = round(
                (first_fault_us - first_t) / 1e6, 2
            )
        severity = "critical" if total_conf >= 0.60 else "warning"
        result["summary"] = (
            f"THRUST LOSS DETECTED  "
            f"(severity={severity}, confidence={total_conf:.0%}, "
            f"RCOU={len(rcou_ev)} signals, CTUN={len(ctun_ev)} signals)"
        )
        result["recommendations"] = [
            "Verify total thrust-to-weight ratio ≥ 2:1 for the loaded all-up weight.",
            "Check motor/ESC performance under load — bench test at 100% throttle.",
            "Review battery C-rating vs peak current draw (motor × 4 × stall amps).",
            "Check ArduPilot THRUST_LOSS error messages in STATUS log lines.",
            "If flying heavy payload, consider upgrading motors or reducing weight.",
        ]

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive thrust-loss analysis of an ArduPilot .BIN log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage")[0].strip(),
    )
    parser.add_argument("logfile", help="Path to ArduPilot .BIN dataflash log")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-signal feature values"
    )
    parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="Output machine-readable JSON",
    )
    args = parser.parse_args()

    try:
        result = analyze(args.logfile, verbose=args.verbose)
    except IOError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        print("  ArduPilot Thrust Loss Analyser")
        print(f"  Log: {args.logfile}")
        print(f"{'='*60}")
        print(f"\n  {result['summary']}")
        print(f"\n  RCOU data available: {'YES' if result['rcou_available'] else 'NO'}")
        print(f"  CTUN data available: {'YES' if result['ctun_available'] else 'NO'}")
        if result["evidence"]:
            print("\n  Evidence:")
            for ev in result["evidence"]:
                print(f"    [{ev['signal']}] {ev['feature']} = {ev['value']}  "
                      f"(threshold: {ev['threshold']})")
                print(f"           → {ev['meaning']}")
        if result["first_fault_time_sec"] is not None:
            print(f"\n  ⚠  First fault onset: {result['first_fault_time_sec']} s into flight")
        if result["recommendations"]:
            print("\n  Recommended next checks:")
            for i, rec in enumerate(result["recommendations"], 1):
                print(f"    {i}. {rec}")
        print()

    sys.exit(1 if result["fault"] else 0)


if __name__ == "__main__":
    main()
