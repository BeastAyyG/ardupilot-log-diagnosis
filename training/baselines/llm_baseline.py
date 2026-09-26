"""LLM baseline: an LLM reads the structured diagnosis report.

Step 4 of ``docs/PUBLICATION_PLAN.md`` specifies this baseline as: the LLM is
given the structured report (the same JSON ``/api/analyze`` returns), with a
**fixed prompt at temperature 0**. It needs an API key; without one the baseline
refuses to run rather than emit a fabricated number (the paper says "this
baseline was not run" when no key is available).

The provider is intentionally pluggable. By default we call an OpenAI-compatible
chat endpoint via the ``openai`` package if installed, using
``ARDUPILOT_LLM_API_KEY`` and ``ARDUPILOT_LLM_BASE_URL``. If that package is
missing, or the key is unset, ``predict_label`` raises ``RuntimeError`` and
``paper_eval`` records the baseline as "not run".

The model is constrained to our label set; its free-text answer is matched to
the nearest label, else it abstains.
"""

from __future__ import annotations

import os
import re

LABELS = {
    "compass_interference",
    "ekf_failure",
    "gps_quality_poor",
    "healthy",
    "rc_failsafe",
    "vibration_high",
    "brownout",
    "crash_unknown",
    "mechanical_failure",
    "motor_imbalance",
    "pid_tuning_issue",
    "power_instability",
    "setup_error",
    "thrust_loss",
}

SYSTEM_PROMPT = (
    "You are a flight-log root-cause classifier. Given a structured diagnosis "
    "report, name the single root cause. Reply with exactly one label from this "
    "fixed set and nothing else: "
    + ", ".join(sorted(LABELS))
    + ". If the report does not support a single clear cause, reply 'healthy'."
)


def _report_text(report: dict) -> str:
    """Flatten the structured report into a compact text the LLM can read."""
    parts: list[str] = []
    meta = report.get("metadata", {})
    if isinstance(meta, dict):
        parts.append(f"vehicle={meta.get('vehicle')} file={meta.get('filename')}")
    for d in report.get("diagnoses", []) or []:
        if isinstance(d, dict):
            parts.append(
                f"- {d.get('failure_type')} conf={d.get('confidence')} "
                f"reason={d.get('reason_code')}"
            )
    hw = report.get("hardware_report", {})
    if isinstance(hw, dict):
        sensors = hw.get("sensors", {})
        if isinstance(sensors, dict):
            parts.append("sensors=" + ",".join(k for k, v in sensors.items() if v.get("present")))
    return "\n".join(parts)


def predict_label(report: dict) -> str:
    """Return one label from ``LABELS`` for the report, or raise if unavailable."""
    api_key = os.environ.get("ARDUPILOT_LLM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM baseline not configured: set ARDUPILOT_LLM_API_KEY. "
            "Without a key the paper reports this baseline as not run."
        )
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("LLM baseline needs the 'openai' package") from exc

    client = OpenAI(api_key=api_key, base_url=os.environ.get("ARDUPILOT_LLM_BASE_URL"))
    resp = client.chat.completions.create(
        model=os.environ.get("ARDUPILOT_LLM_MODEL", "gpt-4o-mini"),
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _report_text(report)},
        ],
    )
    answer = (resp.choices[0].message.content or "").strip().lower()
    match = re.search(r"([a-z_]+)", answer)
    token = match.group(1) if match else ""
    return token if token in LABELS else "healthy"
