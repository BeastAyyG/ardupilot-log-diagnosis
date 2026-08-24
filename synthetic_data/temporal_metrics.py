"""Raw time-series summaries for lineage-level sim-real fidelity."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.integrate import trapezoid
from scipy.signal import coherence, welch

MINIMUM_SAMPLES = 16
MAXIMUM_RESAMPLED_SAMPLES = 1_000_000


def _series(payload: Any, channel_name: str) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(payload, dict):
        raise ValueError(f"temporal channel {channel_name} must be an object")
    times_raw = payload.get("time_sec")
    values_raw = payload.get("values")
    if not isinstance(times_raw, list) or not isinstance(values_raw, list):
        raise ValueError(f"temporal channel {channel_name} lacks arrays")
    if len(times_raw) != len(values_raw) or len(times_raw) < MINIMUM_SAMPLES:
        raise ValueError(
            f"temporal channel {channel_name} needs {MINIMUM_SAMPLES} aligned samples"
        )
    try:
        times = np.asarray(times_raw, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"temporal channel {channel_name} has invalid times") from exc
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError(
            f"temporal channel {channel_name} times must be finite and increasing"
        )
    values = np.full(len(values_raw), np.nan, dtype=float)
    for index, value in enumerate(values_raw):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"temporal channel {channel_name} has invalid values")
        numeric = float(value)
        if not np.isfinite(numeric):
            raise ValueError(f"temporal channel {channel_name} has non-finite values")
        values[index] = numeric
    if np.isfinite(values).sum() < MINIMUM_SAMPLES:
        raise ValueError(f"temporal channel {channel_name} has too few finite samples")
    return times, values


def _uniform(
    times: np.ndarray, values: np.ndarray, channel_name: str
) -> tuple[np.ndarray, np.ndarray, float]:
    interval = float(np.median(np.diff(times)))
    if interval <= 0:
        raise ValueError(f"temporal channel {channel_name} has invalid cadence")
    finite = np.isfinite(values)
    start = float(times[finite][0])
    end = float(times[finite][-1])
    count = int(np.floor((end - start) / interval)) + 1
    if count < MINIMUM_SAMPLES or count > MAXIMUM_RESAMPLED_SAMPLES:
        raise ValueError(f"temporal channel {channel_name} has unusable duration")
    grid = start + np.arange(count, dtype=float) * interval
    interpolated = np.interp(grid, times[finite], values[finite])
    return grid, interpolated, interval


def _cadence_metrics(times: np.ndarray, values: np.ndarray) -> dict[str, float]:
    intervals = np.diff(times)
    median = float(np.median(intervals))
    missed = np.maximum(np.rint(intervals / median).astype(int) - 1, 0)
    expected = len(times) + int(missed.sum())
    return {
        "sample_rate_hz": 1.0 / median,
        "jitter_mad_ratio": float(np.median(np.abs(intervals - median)) / median),
        "dropout_fraction": float(missed.sum() / expected),
        "missing_value_fraction": float(np.mean(~np.isfinite(values))),
    }


def _acf(signal: np.ndarray, lag_samples: int) -> float:
    if lag_samples < 1 or lag_samples >= len(signal):
        raise ValueError("requested ACF lag is outside the observed signal duration")
    left = signal[:-lag_samples]
    right = signal[lag_samples:]
    left = left - left.mean()
    right = right - right.mean()
    denominator = float(np.sqrt(np.sum(left * left) * np.sum(right * right)))
    return float(np.sum(left * right) / denominator) if denominator > 0 else 0.0


def _band_power_fractions(
    signal: np.ndarray,
    sample_rate: float,
    bands: list[dict[str, Any]],
    channel_name: str,
) -> dict[str, float]:
    frequencies, power = welch(
        signal - float(np.mean(signal)),
        fs=sample_rate,
        nperseg=min(256, len(signal)),
        noverlap=min(128, len(signal) // 2),
    )
    usable = frequencies > 0
    total = float(trapezoid(power[usable], frequencies[usable]))
    output: dict[str, float] = {}
    for band in bands:
        low = float(band["low_hz"])
        high = float(band["high_hz"])
        if low >= sample_rate / 2:
            raise ValueError(
                f"temporal channel {channel_name} cannot resolve PSD band {band['name']}"
            )
        selected = (frequencies >= low) & (frequencies < high)
        value = float(trapezoid(power[selected], frequencies[selected]))
        output[str(band["name"])] = value / total if total > 0 else 0.0
    return output


def _aligned_pair(
    one: tuple[np.ndarray, np.ndarray, float],
    two: tuple[np.ndarray, np.ndarray, float],
) -> tuple[np.ndarray, np.ndarray, float]:
    one_time, one_values, one_interval = one
    two_time, two_values, two_interval = two
    interval = max(one_interval, two_interval)
    start = max(float(one_time[0]), float(two_time[0]))
    end = min(float(one_time[-1]), float(two_time[-1]))
    count = int(np.floor((end - start) / interval)) + 1
    if count < MINIMUM_SAMPLES or count > MAXIMUM_RESAMPLED_SAMPLES:
        raise ValueError("temporal channel pair has insufficient shared duration")
    grid = start + np.arange(count, dtype=float) * interval
    return (
        np.interp(grid, one_time, one_values),
        np.interp(grid, two_time, two_values),
        interval,
    )


def _pair_metrics(
    one: np.ndarray,
    two: np.ndarray,
    interval: float,
    bands: list[dict[str, Any]],
    maximum_lag_sec: float,
) -> dict[str, float]:
    sample_rate = 1.0 / interval
    frequencies, values = coherence(
        one,
        two,
        fs=sample_rate,
        nperseg=min(128, len(one)),
        noverlap=min(64, len(one) // 2),
    )
    output: dict[str, float] = {}
    for band in bands:
        selected = (frequencies >= float(band["low_hz"])) & (
            frequencies < float(band["high_hz"])
        )
        output[f"coherence:{band['name']}"] = (
            float(np.nanmean(values[selected])) if selected.any() else 0.0
        )
    left = one - float(np.mean(one))
    right = two - float(np.mean(two))
    left_std = float(np.std(left))
    right_std = float(np.std(right))
    if left_std <= 0 or right_std <= 0:
        output["cross_correlation_lag_sec"] = 0.0
        output["maximum_absolute_cross_correlation"] = 0.0
        return output
    correlation = np.correlate(left / left_std, right / right_std, mode="full")
    correlation /= len(one)
    lags = np.arange(-len(one) + 1, len(one))
    maximum_lag = max(1, int(round(maximum_lag_sec / interval)))
    selected = np.abs(lags) <= maximum_lag
    chosen = int(np.argmax(np.abs(correlation[selected])))
    selected_lags = lags[selected]
    selected_correlation = correlation[selected]
    output["cross_correlation_lag_sec"] = float(selected_lags[chosen] * interval)
    output["maximum_absolute_cross_correlation"] = float(
        abs(selected_correlation[chosen])
    )
    return output


def summarize_temporal_record(
    record: dict[str, Any], design: dict[str, Any]
) -> dict[str, float]:
    """Derive a fixed temporal metric vector from one raw lineage record."""

    channels = record.get("channels")
    if not isinstance(channels, dict):
        raise ValueError("temporal record lacks channels")
    metrics: dict[str, float] = {}
    uniform: dict[str, tuple[np.ndarray, np.ndarray, float]] = {}
    for name in design["required_channels"]:
        times, values = _series(channels.get(name), name)
        cadence = _cadence_metrics(times, values)
        for metric_name, value in cadence.items():
            metrics[f"channel:{name}:{metric_name}"] = value
        grid, signal, interval = _uniform(times, values, name)
        uniform[name] = (grid, signal, interval)
        for lag_sec in design["acf_lags_sec"]:
            lag_samples = int(round(float(lag_sec) / interval))
            metrics[f"channel:{name}:acf:{float(lag_sec):g}s"] = _acf(
                signal, lag_samples
            )
        for band_name, value in _band_power_fractions(
            signal,
            1.0 / interval,
            design["psd_bands_hz"],
            name,
        ).items():
            metrics[f"channel:{name}:psd_fraction:{band_name}"] = value
    for pair in design["channel_pairs"]:
        one_name = pair["one"]
        two_name = pair["two"]
        one, two, interval = _aligned_pair(uniform[one_name], uniform[two_name])
        for metric_name, value in _pair_metrics(
            one,
            two,
            interval,
            design["psd_bands_hz"],
            float(design["maximum_cross_channel_lag_sec"]),
        ).items():
            metrics[f"pair:{one_name}|{two_name}:{metric_name}"] = value
    if design["require_transition_timing"]:
        transition = record.get("transition_time_sec")
        if (
            isinstance(transition, bool)
            or not isinstance(transition, (int, float))
            or not np.isfinite(float(transition))
        ):
            raise ValueError("temporal record lacks finite transition timing")
        metrics["transition_time_sec"] = float(transition)
    if not all(np.isfinite(value) for value in metrics.values()):
        raise ValueError("temporal metric computation produced a non-finite value")
    return metrics
