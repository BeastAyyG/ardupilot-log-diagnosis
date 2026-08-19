"""Deterministic sensor, navigation, propulsion, and battery metrics."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


def _messages(parsed: dict[str, Any], names: Iterable[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in names:
        values = parsed.get("messages", {}).get(name, [])
        if isinstance(values, list):
            result.extend(values)
    return result


def _numbers(messages: list[dict[str, Any]], field_names: tuple[str, ...]) -> list[float]:
    result: list[float] = []
    for message in messages:
        for field in field_names:
            value = message.get(field)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                result.append(float(value))
                break
    return result


def _summary(values: list[float], unit: str | None = None) -> dict[str, Any]:
    if not values:
        return {"status": "insufficient_data", "count": 0, "unit": unit}
    array = np.asarray(values, dtype=float)
    result: dict[str, Any] = {
        "status": "reliable",
        "count": int(array.size),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "unit": unit,
    }
    return result


def _correlation(left: list[float], right: list[float]) -> float | None:
    size = min(len(left), len(right))
    if size < 3:
        return None
    x = np.asarray(left[:size], dtype=float)
    y = np.asarray(right[:size], dtype=float)
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _compass_fit(messages: list[dict[str, Any]]) -> dict[str, Any]:
    points = []
    for message in messages:
        values = [message.get(field) for field in ("MagX", "MagY", "MagZ")]
        if all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values):
            points.append([float(value) for value in values])
    if len(points) < 20:
        return {"status": "insufficient_data", "sample_count": len(points), "reason": "At least 20 3-axis MAG samples are required."}
    matrix = np.asarray(points, dtype=float)
    design = np.column_stack((2.0 * matrix, np.ones(matrix.shape[0])))
    target = np.sum(matrix * matrix, axis=1)
    try:
        solution, *_ = np.linalg.lstsq(design, target, rcond=None)
        offsets = solution[:3]
        radius_sq = float(solution[3] + np.dot(offsets, offsets))
        if radius_sq <= 0:
            raise ValueError("non-positive fitted radius")
        radius = math.sqrt(radius_sq)
        residuals = np.linalg.norm(matrix - offsets, axis=1) - radius
        azimuth = np.degrees(np.arctan2(matrix[:, 1], matrix[:, 0]))
        coverage = int(len(np.unique(np.floor((azimuth + 180.0) / 30.0))))
        return {
            "status": "reliable" if coverage >= 6 else "degraded",
            "sample_count": int(matrix.shape[0]),
            "offsets": {"x": float(offsets[0]), "y": float(offsets[1]), "z": float(offsets[2])},
            "field_strength": float(radius),
            "residual_rms": float(np.sqrt(np.mean(residuals * residuals))),
            "coverage_bins": coverage,
            "coverage_score": float(min(1.0, coverage / 12.0)),
            "recommendation_status": "review_only",
            "write_parameters": False,
            "source_url": "https://github.com/ArduPilot/WebTools/blob/master/MAGFit/Readme.md",
        }
    except (np.linalg.LinAlgError, ValueError):
        return {"status": "insufficient_data", "sample_count": len(points), "reason": "Compass sphere fit was not identifiable."}


def analyze_sensors(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return evidence cards; absent streams are never scored as healthy."""

    messages = parsed.get("messages", {}) or {}
    parameters = parsed.get("parameters", {}) or {}

    battery = _messages(parsed, ("BAT", "CURR"))
    volts = _numbers(battery, ("Volt", "Voltage"))
    current = _numbers(battery, ("Curr", "Current"))
    if volts and max(volts) > 100:
        volts = [value / 100.0 for value in volts]
    if current and max(current) > 500:
        current = [value / 100.0 for value in current]
    cell_count = parameters.get("BATT_CELLS")
    if not isinstance(cell_count, (int, float)) or cell_count <= 0:
        cell_count = round(max(volts) / 4.2) if volts else None
    battery_report: dict[str, Any] = {
        "status": "reliable" if volts else "insufficient_data",
        "voltage": _summary(volts, "V"),
        "current": _summary(current, "A"),
        "estimated_cell_count": int(cell_count) if cell_count else None,
        "voltage_sag": float(max(volts) - min(volts)) if volts else None,
        "low_voltage_threshold": parameters.get("BATT_LOW_VOLT"),
    }
    if volts and current:
        battery_report["voltage_current_correlation"] = _correlation(volts, current)
    threshold = parameters.get("BATT_LOW_VOLT")
    threshold_value = float(threshold) if isinstance(threshold, (int, float)) else None
    if threshold_value is not None and volts:
        battery_report["low_voltage_crossings"] = sum(
            1 for left, right in zip(volts, volts[1:]) if left >= threshold_value > right
        )
        battery_report["minimum_margin_v"] = float(min(volts) - threshold_value)
    if battery and current:
        times = [m.get("TimeUS") for m in battery]
        consumed_ah = 0.0
        for index, (left, right) in enumerate(zip(times, times[1:])):
            if isinstance(left, (int, float)) and isinstance(right, (int, float)) and index < len(current):
                consumed_ah += max(0.0, float(current[index])) * max(0.0, float(right - left)) / 3.6e9
        battery_report["estimated_consumed_ah"] = round(consumed_ah, 4)

    mags = _messages(parsed, ("MAG", "MAG2", "MAG3"))
    norms: list[float] = []
    for message in mags:
        xyz = [message.get(field) for field in ("MagX", "MagY", "MagZ")]
        if all(isinstance(value, (int, float)) for value in xyz):
            norms.append(float(math.sqrt(sum(float(value) ** 2 for value in xyz))))
    compass_report = {
        "status": "reliable" if norms else "insufficient_data",
        "field_norm": _summary(norms, "mgauss"),
        "configured_offsets": {
            name: parameters[name]
            for name in ("COMPASS_OFS_X", "COMPASS_OFS_Y", "COMPASS_OFS_Z")
            if name in parameters
        },
        "calibration_coverage": "unknown",
        "calibration_fit": _compass_fit(mags),
    }
    if len(norms) >= 4:
        compass_report["field_norm"]["range"] = float(max(norms) - min(norms))

    gps = _messages(parsed, ("GPS",))
    hdop = _numbers(gps, ("HDop", "HDOP"))
    sats = _numbers(gps, ("NSats", "SatCount"))
    status = _numbers(gps, ("Status", "Fix"))
    gps_report = {
        "status": "reliable" if gps else "insufficient_data",
        "hdop": _summary(hdop, "unitless"),
        "satellites": _summary(sats, "count"),
        "fix_rate": float(sum(value >= 3 for value in status) / len(status)) if status else None,
        "glitch_count": sum(1 for message in gps if message.get("Glitch") or message.get("GlitchCount")),
    }
    gps2 = _messages(parsed, ("GPS2", "GPS3"))
    if gps and gps2:
        primary_alt = _numbers(gps, ("Alt", "AltMSL"))
        secondary_alt = _numbers(gps2, ("Alt", "AltMSL"))
        if primary_alt and secondary_alt:
            size = min(len(primary_alt), len(secondary_alt))
            gps_report["multi_gps_altitude_disagreement"] = _summary(
                [abs(primary_alt[i] - secondary_alt[i]) for i in range(size)], "m"
            )

    imu_streams = []
    for name in ("IMU", "IMU2", "IMU3"):
        values = _numbers(messages.get(name, []) if isinstance(messages.get(name, []), list) else [], ("AccX",))
        if values:
            imu_streams.append({"stream": name, "accel_x": _summary(values, "m/s2")})
    consistency = "insufficient_data"
    if len(imu_streams) >= 2:
        means = [item["accel_x"]["mean"] for item in imu_streams]
        consistency = "consistent" if max(means) - min(means) <= 0.5 else "divergent"

    esc = _messages(parsed, ("ESC",))
    esc_metrics = {}
    for field, label, unit in (("RPM", "rpm", "rpm"), ("Curr", "current", "A"), ("Temp", "temperature", "C")):
        values = _numbers(esc, (field,))
        if values:
            esc_metrics[label] = _summary(values, unit)

    baro = _messages(parsed, ("BARO",))
    baro_alt = _numbers(baro, ("Alt", "AltMSL"))
    baro_pressure = _numbers(baro, ("Press", "Pressure"))
    baro_report = {
        "status": "reliable" if baro else "insufficient_data",
        "altitude": _summary(baro_alt, "m"),
        "pressure": _summary(baro_pressure, "Pa"),
        "drift": float(baro_alt[-1] - baro_alt[0]) if len(baro_alt) >= 2 else None,
    }

    ekf = _messages(parsed, ("XKF4", "NKF4"))
    variance_fields = {
        "velocity": ("SV", "Verr", "VelVar"),
        "position": ("SP", "Perr", "PosVar"),
        "height": ("SH", "Herr", "HgtVar"),
        "compass": ("SM", "Merr", "MagVar"),
    }
    ekf_variances = {
        label: _summary(_numbers(ekf, fields), "variance")
        for label, fields in variance_fields.items()
        if _numbers(ekf, fields)
    }
    ekf_report = {
        "status": "reliable" if ekf_variances else "insufficient_data",
        "sample_count": len(ekf),
        "variances": ekf_variances,
    }

    airspeed = _messages(parsed, ("ARSP",))
    indicated = _numbers(airspeed, ("Airspeed", "IAS", "AirspeedRaw"))
    ratio_values = _numbers(airspeed, ("AirspeedRatio", "Ratio"))
    airspeed_report = {
        "status": "reliable" if indicated else "insufficient_data",
        "indicated": _summary(indicated, "m/s"),
        "ratio": _summary(ratio_values, "unitless"),
        "configured_ratio": parameters.get("ARSPD_RATIO"),
        "write_parameters": False,
    }

    return {
        "schema_version": "sensor-metrics.v1",
        "battery": battery_report,
        "compass": compass_report,
        "gps": gps_report,
        "barometer": baro_report,
        "ekf": ekf_report,
        "airspeed": airspeed_report,
        "imu": {"status": "reliable" if imu_streams else "insufficient_data", "streams": imu_streams, "consistency": consistency},
        "esc": {"status": "reliable" if esc_metrics else "insufficient_data", "metrics": esc_metrics, "instances": len(esc)},
    }
