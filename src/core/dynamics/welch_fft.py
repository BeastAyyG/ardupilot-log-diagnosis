"""Welch vibration spectrum extraction and notch-parameter estimation.

The extractor operates on one already-aligned telemetry axis.  It returns a
PSD in SI-compatible frequency units and a read-only recommendation for the
ArduPilot harmonic notch parameters.  It never writes parameters or mutates
the input signal.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral

import numpy as np


@dataclass(frozen=True, slots=True)
class WelchPeak:
    """A significant spectral peak and its measured half-power width."""

    frequency_hz: float
    power: float
    prominence: float
    bandwidth_hz: float
    harmonic: int | None


@dataclass(frozen=True, slots=True)
class WelchResult:
    """Welch PSD output and derived harmonic-notch settings."""

    sample_rate_hz: float
    segment_length: int
    resolution_hz: float
    frequencies_hz: np.ndarray
    power_spectral_density: np.ndarray
    noise_floor: float
    peaks: tuple[WelchPeak, ...]
    ins_hntch_freq: float | None
    ins_hntch_bw: float | None
    ins_hntch_hmncs: int

    @property
    def parameters(self) -> dict[str, float | int | None]:
        """Return the exact ArduPilot parameter names and derived values."""

        return {
            "INS_HNTCH_FREQ": self.ins_hntch_freq,
            "INS_HNTCH_BW": self.ins_hntch_bw,
            "INS_HNTCH_HMNCS": self.ins_hntch_hmncs,
        }

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the result."""

        return {
            "schema_version": "welch-fft.v1",
            "sample_rate_hz": self.sample_rate_hz,
            "segment_length": self.segment_length,
            "resolution_hz": self.resolution_hz,
            "frequencies_hz": self.frequencies_hz.tolist(),
            "power_spectral_density": self.power_spectral_density.tolist(),
            "noise_floor": self.noise_floor,
            "peaks": [
                {
                    "frequency_hz": peak.frequency_hz,
                    "power": peak.power,
                    "prominence": peak.prominence,
                    "bandwidth_hz": peak.bandwidth_hz,
                    "harmonic": peak.harmonic,
                }
                for peak in self.peaks
            ],
            "parameters": self.parameters,
        }


def _signal_array(samples: Sequence[float] | np.ndarray) -> np.ndarray:
    """Validate and normalize a single telemetry axis."""

    try:
        signal = np.asarray(samples, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError("samples must be a one-dimensional numeric sequence") from exc
    if signal.ndim != 1:
        raise ValueError("samples must be one-dimensional")
    if signal.size < 4:
        raise ValueError("at least four samples are required")
    if not np.isfinite(signal).all():
        raise ValueError("samples must contain only finite values")
    return np.ascontiguousarray(signal)


def _validate_options(
    sample_rate_hz: float,
    nperseg: int,
    noverlap: int,
    max_harmonics: int,
    min_peak_prominence_db: float,
) -> None:
    """Validate public numeric options at the API boundary."""

    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if not isinstance(nperseg, Integral) or isinstance(nperseg, bool) or nperseg < 4:
        raise ValueError("nperseg must be at least four")
    if (
        not isinstance(noverlap, Integral)
        or isinstance(noverlap, bool)
        or noverlap < 0
        or noverlap >= nperseg
    ):
        raise ValueError("noverlap must satisfy 0 <= noverlap < nperseg")
    if not isinstance(max_harmonics, Integral) or isinstance(max_harmonics, bool) or max_harmonics < 1:
        raise ValueError("max_harmonics must be at least one")
    if not np.isfinite(min_peak_prominence_db) or min_peak_prominence_db < 0:
        raise ValueError("min_peak_prominence_db must be finite and non-negative")


def _fundamental_index(
    frequencies: np.ndarray,
    powers: np.ndarray,
    max_harmonics: int,
    resolution_hz: float,
) -> tuple[int, np.ndarray]:
    """Select the lowest peak that explains the most harmonic energy."""

    tolerance = np.maximum(resolution_hz * 1.5, frequencies * 0.03)
    harmonic_numbers = np.arange(1, max_harmonics + 1, dtype=np.float64)
    distance = np.abs(
        frequencies[:, None, None] * harmonic_numbers[None, :, None]
        - frequencies[None, None, :]
    )
    matches = distance <= tolerance[:, None, None]
    matched_peaks = matches.any(axis=1)
    harmonic_counts = matched_peaks.sum(axis=1)
    harmonic_power = np.where(matched_peaks, powers[None, :], 0.0).sum(axis=1)
    strongest_power = powers
    # Count and total explained power dominate; the final term breaks ties
    # toward the lower frequency so a true fundamental beats its overtone.
    order = np.lexsort((frequencies, -strongest_power, -harmonic_power, -harmonic_counts))
    index = int(order[0])
    return index, matched_peaks[index]


def _loaded_scipy_signal():
    """Return an already-loaded SciPy signal module without importing SciPy."""

    if "scipy.signal" not in sys.modules:
        return None
    try:
        from scipy import signal
    except (ImportError, AttributeError):
        return None
    return signal


def _numpy_welch(
    signal: np.ndarray,
    sample_rate_hz: float,
    segment_length: int,
    noverlap: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the density-scaled one-sided Welch estimate with NumPy only."""

    step = segment_length - noverlap
    starts = range(0, signal.size - segment_length + 1, step)
    segments = np.stack([signal[start : start + segment_length] for start in starts])
    segments = segments - np.mean(segments, axis=1, keepdims=True)
    window = np.hanning(segment_length)
    transformed = np.fft.rfft(segments * window, axis=1)
    power = np.abs(transformed) ** 2
    power /= float(sample_rate_hz) * float(np.sum(window * window))
    if segment_length % 2:
        power[:, 1:] *= 2.0
    else:
        power[:, 1:-1] *= 2.0
    frequencies = np.fft.rfftfreq(segment_length, d=1.0 / sample_rate_hz)
    return frequencies, np.mean(power, axis=0)


def _numpy_peak_prominence(power: np.ndarray, index: int) -> float:
    """Use the higher side baseline as a conservative local prominence."""

    left_min = float(np.min(power[: index + 1]))
    right_min = float(np.min(power[index:]))
    return max(0.0, float(power[index]) - max(left_min, right_min))


def _numpy_find_peaks(
    power: np.ndarray, prominence_floor: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Find honest local maxima and their prominence/half-height widths."""

    if power.size < 3:
        return np.empty(0, dtype=np.int64), np.empty(0), np.empty(0)
    candidates = np.flatnonzero(
        (power[1:-1] > power[:-2]) & (power[1:-1] >= power[2:])
    ) + 1
    indices: list[int] = []
    prominences: list[float] = []
    widths: list[float] = []
    for index in candidates.tolist():
        prominence = _numpy_peak_prominence(power, index)
        if prominence < prominence_floor:
            continue
        height = float(power[index]) - prominence / 2.0
        left = index
        while left > 0 and power[left] >= height:
            left -= 1
        right = index
        last = power.size - 1
        while right < last and power[right] >= height:
            right += 1
        left_fraction = 0.0
        if left < index and power[left + 1] != power[left]:
            left_fraction = (height - power[left]) / (power[left + 1] - power[left])
        right_fraction = 0.0
        if right > index and power[right] != power[right - 1]:
            right_fraction = (height - power[right - 1]) / (power[right] - power[right - 1])
        indices.append(index)
        prominences.append(prominence)
        widths.append((index - left - 1 + left_fraction) + right_fraction)
    return (
        np.asarray(indices, dtype=np.int64),
        np.asarray(prominences, dtype=np.float64),
        np.asarray(widths, dtype=np.float64),
    )


def extract_welch_psd(
    samples: Sequence[float] | np.ndarray,
    sample_rate_hz: float,
    *,
    nperseg: int | None = None,
    noverlap: int | None = None,
    max_harmonics: int = 3,
    min_peak_prominence_db: float = 6.0,
) -> WelchResult:
    """Extract a Welch PSD and estimate ArduPilot harmonic-notch settings.

    ``INS_HNTCH_FREQ`` is the lowest significant peak that explains the most
    harmonic peaks.  ``INS_HNTCH_BW`` is its measured half-prominence width,
    clamped to one FFT bin, and ``INS_HNTCH_HMNCS`` counts detected harmonics
    including the fundamental.  A flat signal returns no notch frequency.
    """

    signal = _signal_array(samples)
    segment_length = min(1024, signal.size) if nperseg is None else nperseg
    overlap = segment_length // 2 if noverlap is None else noverlap
    _validate_options(
        float(sample_rate_hz),
        segment_length,
        overlap,
        max_harmonics,
        float(min_peak_prominence_db),
    )
    if segment_length > signal.size:
        raise ValueError("nperseg cannot exceed the number of samples")

    scipy_signal = _loaded_scipy_signal()
    if scipy_signal is None:
        frequencies, power = _numpy_welch(
            signal, float(sample_rate_hz), segment_length, overlap
        )
    else:
        frequencies, power = scipy_signal.welch(
            signal,
            fs=float(sample_rate_hz),
            window="hann",
            nperseg=segment_length,
            noverlap=overlap,
            detrend="constant",
            scaling="density",
            return_onesided=True,
        )
    frequencies = np.asarray(frequencies, dtype=np.float64)
    power = np.asarray(power, dtype=np.float64)
    positive = frequencies > 0
    positive_frequencies = frequencies[positive]
    positive_power = power[positive]
    resolution_hz = float(frequencies[1] - frequencies[0]) if frequencies.size > 1 else 0.0
    noise_floor = float(np.median(positive_power)) if positive_power.size else 0.0
    strongest_power = float(np.max(positive_power)) if positive_power.size else 0.0
    prominence_floor = max(
        noise_floor * (10.0 ** (float(min_peak_prominence_db) / 10.0) - 1.0),
        strongest_power * 1e-8,
        np.finfo(np.float64).tiny,
    )
    if scipy_signal is None:
        peak_indices, peak_prominences, widths = _numpy_find_peaks(
            positive_power, prominence_floor
        )
    else:
        peak_indices, peak_properties = scipy_signal.find_peaks(
            positive_power,
            prominence=prominence_floor,
        )
        peak_prominences = np.asarray(peak_properties["prominences"], dtype=np.float64)
        widths = scipy_signal.peak_widths(positive_power, peak_indices, rel_height=0.5)[0]

    if peak_indices.size == 0:
        return WelchResult(
            sample_rate_hz=float(sample_rate_hz),
            segment_length=segment_length,
            resolution_hz=resolution_hz,
            frequencies_hz=frequencies,
            power_spectral_density=power,
            noise_floor=noise_floor,
            peaks=(),
            ins_hntch_freq=None,
            ins_hntch_bw=None,
            ins_hntch_hmncs=0,
        )

    peak_frequencies = positive_frequencies[peak_indices]
    peak_powers = positive_power[peak_indices]
    peak_bandwidths = np.maximum(widths * resolution_hz, resolution_hz)
    fundamental_position, harmonic_matches = _fundamental_index(
        peak_frequencies,
        peak_powers,
        max_harmonics,
        resolution_hz,
    )
    fundamental_frequency = float(peak_frequencies[fundamental_position])
    tolerance = max(resolution_hz * 1.5, fundamental_frequency * 0.03)
    harmonic_numbers = np.rint(peak_frequencies / fundamental_frequency).astype(np.int64)
    harmonic_numbers = np.where(
        (harmonic_numbers >= 1)
        & (harmonic_numbers <= int(max_harmonics))
        & (np.abs(peak_frequencies - harmonic_numbers * fundamental_frequency) <= tolerance),
        harmonic_numbers,
        0,
    )
    harmonic_numbers[~harmonic_matches] = 0
    peaks = tuple(
        WelchPeak(
            frequency_hz=float(frequency),
            power=float(power_value),
            prominence=float(prominence),
            bandwidth_hz=float(bandwidth),
            harmonic=int(harmonic) if harmonic else None,
        )
        for frequency, power_value, prominence, bandwidth, harmonic in zip(
            peak_frequencies,
            peak_powers,
            peak_prominences,
            peak_bandwidths,
            harmonic_numbers,
        )
    )
    harmonic_count = int(np.unique(harmonic_numbers[harmonic_numbers > 0]).size)
    return WelchResult(
        sample_rate_hz=float(sample_rate_hz),
        segment_length=segment_length,
        resolution_hz=resolution_hz,
        frequencies_hz=frequencies,
        power_spectral_density=power,
        noise_floor=noise_floor,
        peaks=peaks,
        ins_hntch_freq=fundamental_frequency,
        ins_hntch_bw=float(peak_bandwidths[fundamental_position]),
        ins_hntch_hmncs=harmonic_count,
    )
