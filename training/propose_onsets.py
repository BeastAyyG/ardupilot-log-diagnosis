"""Propose root-cause onset times for labelled benchmark logs.

Part of Step 3 of ``docs/PUBLICATION_PLAN.md``. CITA (causal temporal arbitration)
is only testable if we know *when* the root cause began. This tool proposes an
onset time per log from the channel(s) most associated with its label, using
fixed domain thresholds.

**This tool proposes. It does not assert.** For several labels there is no single
clean channel (``setup_error``, ``crash_unknown``, ``rc_failsafe`` are config /
event / link-layer causes with no continuous precursor). For those the tool
returns ``null`` and the maintainer confirms the onset manually from the saved
plot. Every proposal is written with a ``confidence`` field and the exact channel
and threshold that produced it, so a reviewer can audit it.

Detection rule (per mapped channel): scan the message stream for the field; take
the first ``TimeUS`` at which the value crosses the threshold in the labelled
direction (rising for failures, falling for drops). The earliest such crossing
across the mapped channels is the proposed onset. ``TimeUS`` is microseconds since
arm; we report both ``time_us`` and ``t_sec``.

Example::

    python training/propose_onsets.py \
        --annotations data/benchmark/ground_truth_real_v3.json \
        --logs data/raw/benchmark_v1 \
        --plots data/benchmark/onset_plots

The annotations file is the ground-truth JSON (it has ``logs`` with ``filename``,
``labels`` and ``sha256``). ``--logs`` points at the directory holding the staged
``.bin`` files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# label -> list of (message, field, direction, threshold)
# direction: "rise" means "failure when value goes above threshold";
#            "fall" means "failure when value drops below threshold".
# These are symptom-channel proxies, documented as such. See module docstring.
LABEL_CHANNELS: dict[str, list[tuple[str, str, str, float]]] = {
    "vibration_high": [("VIBE", "VibeZ", "rise", 30.0), ("VIBE", "VibeX", "rise", 30.0), ("VIBE", "VibeY", "rise", 30.0)],
    "ekf_failure": [("NKF1", "PN", "rise", 8.0), ("NKF1", "PE", "rise", 8.0), ("NKF1", "PD", "rise", 8.0)],
    "gps_quality_poor": [("GPS", "HDop", "rise", 2.0)],
    "compass_interference": [("NKF1", "OH", "rise", 0.5)],
    "thrust_loss": [("RCOU", "_min_output", "fall", 1100.0)],
    "motor_imbalance": [("RCOU", "_spread", "rise", 400.0)],
    "mechanical_failure": [("RCOU", "_spread", "rise", 400.0)],
    "power_instability": [("POWR", "Vcc", "fall", 4.5)],
    "brownout": [("POWR", "Vcc", "fall", 4.3)],
}


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _channel_series(messages: dict, msg: str, field: str) -> list[tuple[float, float]]:
    """Return [(time_us, value)] for a (msg, field), filtering non-numeric."""
    out: list[tuple[float, float]] = []
    for row in messages.get(msg, []):
        if not isinstance(row, dict):
            continue
        t = _to_float(row.get("TimeUS"))
        v = _to_float(row.get(field))
        if t is None or v is None:
            continue
        out.append((t, v))
    return out


def _derived_series(messages: dict, derived: str) -> list[tuple[float, float]]:
    """Derived channels computed from RCOU: min output and per-frame spread."""
    out: list[tuple[float, float]] = []
    for row in messages.get("RCOU", []):
        if not isinstance(row, dict):
            continue
        t = _to_float(row.get("TimeUS"))
        if t is None:
            continue
        outs = [_to_float(row.get(f"C{i}")) for i in range(1, 15)]
        outs = [v for v in outs if v is not None]
        if not outs:
            continue
        if derived == "_min_output":
            out.append((t, min(outs)))
        elif derived == "_spread":
            out.append((t, max(outs) - min(outs)))
    return out


def propose_onset(messages: dict, label: str) -> dict | None:
    """Return a proposal dict for ``label``, or ``None`` if no channel maps.

    Proposal keys: channel, field, direction, threshold, time_us, t_sec, value,
    confidence (always "proposed").
    """
    channels = LABEL_CHANNELS.get(label)
    if not channels:
        return None
    best: dict | None = None
    for msg, field, direction, threshold in channels:
        series = (
            _derived_series(messages, field)
            if field.startswith("_")
            else _channel_series(messages, msg, field)
        )
        for t, v in series:
            crosses = (direction == "rise" and v > threshold) or (direction == "fall" and v < threshold)
            if crosses:
                candidate = {
                    "msg": msg,
                    "field": field,
                    "direction": direction,
                    "threshold": threshold,
                    "time_us": t,
                    "t_sec": t / 1e6,
                    "value": v,
                    "confidence": "proposed",
                }
                if best is None or t < best["time_us"]:
                    best = candidate
                break  # first crossing per channel is enough
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--annotations", default="data/benchmark/ground_truth_real_v3.json")
    parser.add_argument("--logs", default="data/raw/benchmark_v1")
    parser.add_argument("--output", default="data/benchmark/onset_proposals.json")
    parser.add_argument("--plots", default=None, help="optional directory for onset plots")
    args = parser.parse_args()

    ann = json.loads((ROOT / args.annotations).read_text(encoding="utf-8"))
    logs_dir = ROOT / args.logs
    proposals: list[dict] = []
    unmapped_labels = set()

    for entry in ann["logs"]:
        label = entry["labels"][0]
        path = logs_dir / entry["filename"]
        if not path.exists():
            proposals.append(
                {"log_key": entry["sha256"][:10], "filename": entry["filename"], "label": label,
                 "status": "log_not_found", "proposal": None}
            )
            continue
        try:
            from src.parser.bin_parser import LogParser

            parsed = LogParser(str(path)).parse()
            messages = parsed.get("messages", {}) if isinstance(parsed, dict) else {}
        except Exception as exc:  # pragma: no cover - defensive on malformed logs
            proposals.append(
                {"log_key": entry["sha256"][:10], "filename": entry["filename"], "label": label,
                 "status": "parse_error", "detail": str(exc)[:200], "proposal": None}
            )
            continue

        proposal = propose_onset(messages, label)
        if proposal is None:
            unmapped_labels.add(label)
        proposals.append(
            {
                "log_key": entry["sha256"][:10],
                "filename": entry["filename"],
                "label": label,
                "status": "proposed" if proposal else "manual_only",
                "proposal": proposal,
            }
        )
        if args.plots and proposal:
            _save_plot(messages, label, proposal, Path(args.plots) / f"{entry['sha256'][:10]}.png")

    doc = {
        "schema": "logdiagnosis.onset-proposals/v1",
        "annotations": str(args.annotations),
        "manual_only_labels": sorted(unmapped_labels),
        "proposals": proposals,
    }
    (ROOT / args.output).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    proposed = sum(1 for p in proposals if p["status"] == "proposed")
    manual = sum(1 for p in proposals if p["status"] == "manual_only")
    print(f"{proposed} proposed, {manual} manual-only, {len(proposals)} total")
    print(f"labels with no auto channel (maintainer confirms manually): {sorted(unmapped_labels)}")
    return 0


def _save_plot(messages: dict, label: str, proposal: dict, out_path: Path) -> None:
    """Save a PNG of the onset channel with the proposed onset marked.

    Imported lazily so the JSON-only path never requires matplotlib (and never
    triggers its font-cache write, which the Windows sandbox blocks).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    msg, field = proposal["msg"], proposal["field"]
    series = (
        _derived_series(messages, field)
        if field.startswith("_")
        else _channel_series(messages, msg, field)
    )
    if not series:
        return
    xs = [t / 1e6 for t, _ in series]
    ys = [v for _, v in series]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(xs, ys, lw=0.7)
    ax.axhline(proposal["threshold"], color="grey", ls="--", lw=0.6)
    ax.axvline(proposal["t_sec"], color="red", ls="-", lw=0.8, label=f"proposed onset {proposal['t_sec']:.1f}s")
    ax.set_title(f"{label}: {msg}.{field}")
    ax.set_xlabel("t (s)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=90)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
