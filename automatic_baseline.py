"""Experimental automatic point-to-point baselines for positive absorbance bands."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

import numpy as np
from numpy.typing import NDArray

from spectra_model import FloatArray, Spectrum, linear_baseline


ALGORITHM_VERSION = "on-data-linear-anchors-v2"
PREFILTER_WIDTH = 3.0
MIN_COARSENESS = 0
MAX_COARSENESS = 100


@dataclass(frozen=True)
class AutomaticBaseline:
    anchors: tuple[tuple[float, float], ...]
    baseline: FloatArray
    corrected: FloatArray
    coarseness: int
    requested_width: float
    effective_width: float
    noise_sigma: float
    simplification_tolerance: float
    boundary_mask: NDArray[np.bool_]
    warnings: tuple[str, ...]
    algorithm_version: str = ALGORITHM_VERSION


def coarseness_width(coarseness: int) -> float:
    """Map integer 0..100 to a physical window width in inverse centimeters."""
    if (
        isinstance(coarseness, (bool, np.bool_))
        or not isinstance(coarseness, Integral)
        or not MIN_COARSENESS <= coarseness <= MAX_COARSENESS
    ):
        raise ValueError("Coarseness must be an integer from 0 to 100 (not a boolean).")
    return float(5.0 * (2.0 ** (int(coarseness) / 10.0) - 1.0))


def _median_signal(x: FloatArray, y: FloatArray) -> FloatArray:
    starts = np.searchsorted(x, x - PREFILTER_WIDTH / 2)
    stops = np.searchsorted(x, x + PREFILTER_WIDTH / 2, side="right")
    signal = y.copy()
    for index, (start, stop) in enumerate(zip(starts, stops)):
        if (
            stop - start < 3 or x[index] < x[0] + PREFILTER_WIDTH / 2
            or x[index] > x[-1] - PREFILTER_WIDTH / 2
        ):
            continue
        # Detrending keeps a sloping baseline invariant even on nonuniform grids.
        slope = np.median(np.diff(y[start:stop]) / np.diff(x[start:stop]))
        trend = (x[start:stop] - x[index]) * slope
        signal[index] = np.median(y[start:stop] - trend)
    return signal


def _lower_hull(x: FloatArray, y: FloatArray) -> FloatArray:
    vertices: list[int] = []
    for index in range(len(x)):
        while len(vertices) >= 2:
            left, right = vertices[-2:]
            if (
                (y[right] - y[left]) * (x[index] - x[right])
                < (y[index] - y[right]) * (x[right] - x[left])
            ):
                break
            vertices.pop()
        vertices.append(index)
    return np.interp(x, x[vertices], y[vertices])


def _local_envelope(x: FloatArray, signal: FloatArray, width: float) -> FloatArray:
    span = float(x[-1] - x[0])
    if width == 0:
        return signal.copy()
    if width / 2 >= span:
        return _lower_hull(x, signal)
    radius = width / 2
    total = np.zeros_like(signal)
    weights = np.zeros_like(signal)
    # Four overlapping windows per width; tent weights eliminate hard bin seams.
    step = width / 4
    occupied = np.floor(x / step)
    center_indices = np.unique(np.concatenate([occupied + delta for delta in (-1, 0, 1, 2)]))
    centers = center_indices[(center_indices >= 0) & (center_indices <= np.floor(span / step))] * step
    for center in centers:
        start = int(np.searchsorted(x, center - radius))
        stop = int(np.searchsorted(x, center + radius, side="right"))
        local_x = x[start:stop]
        if len(local_x) == 0:
            continue
        weight = np.maximum(0.0, 1.0 - np.abs(local_x - center) / radius)
        total[start:stop] += weight * _lower_hull(local_x, signal[start:stop])
        weights[start:stop] += weight
    if np.any(weights <= 0):
        raise ValueError("Automatic envelope left samples without window support.")
    return total / weights


def _data_anchor_indices(
    x: FloatArray, y: FloatArray, signal: FloatArray, envelope: FloatArray,
    width: float, tolerance: float, contact_tolerance: float,
) -> list[int]:
    """Choose and simplify measured samples, using the envelope only to rank them."""
    candidates = {0, len(x) - 1}
    eligible = np.abs(y - signal) <= contact_tolerance
    if width == 0:
        candidates.update(range(len(x)))
    else:
        groups = np.floor(x / (width / 2))
        boundaries = np.r_[0, np.flatnonzero(np.diff(groups)) + 1, len(x)]
        for start, stop in zip(boundaries[:-1], boundaries[1:]):
            indices = np.flatnonzero(eligible[start:stop]) + start
            if len(indices):
                residual = y[indices] - envelope[indices]
                candidates.add(int(indices[np.argmin(residual)]))
    vertices = sorted(candidates)
    keep = {vertices[0], vertices[-1]}
    segments = [(0, len(vertices) - 1)]
    while segments:
        start, stop = segments.pop()
        if stop <= start + 1:
            continue
        left, right = vertices[start], vertices[stop]
        indices = np.asarray(vertices[start + 1:stop])
        fraction = (x[indices] - x[left]) / (x[right] - x[left])
        line = y[left] + fraction * (y[right] - y[left])
        error = np.abs(line - y[indices])
        relative = int(np.argmax(error))
        if error[relative] > tolerance:
            index = start + 1 + relative
            keep.add(vertices[index])
            segments.extend(((start, index), (index, stop)))
    # Add missed valleys where a sparse straight segment cuts through the data.
    ordered = sorted(keep)
    segments = list(zip(ordered[:-1], ordered[1:]))
    while segments:
        start, stop = segments.pop()
        indices = np.flatnonzero(eligible[start + 1:stop]) + start + 1
        if len(indices) == 0:
            continue
        fraction = (x[indices] - x[start]) / (x[stop] - x[start])
        line = y[start] + fraction * (y[stop] - y[start])
        error = line - signal[indices]
        relative = int(np.argmax(error))
        if error[relative] > tolerance:
            index = int(indices[relative])
            keep.add(index)
            segments.extend(((start, index), (index, stop)))
    return sorted(keep)


def automatic_baseline(spectrum: Spectrum, coarseness: int) -> AutomaticBaseline:
    """Estimate, but do not apply, a baseline; input Y must be positive-band absorbance.

    Display offsets and existing correction/session state are not used or mutated.
    Every returned anchor is an exact original X,Y sample. Only straight segments
    between those anchors are used to evaluate the baseline.
    """
    requested = coarseness_width(coarseness)
    x = np.asarray(spectrum.x, dtype=np.float64)
    y = np.asarray(spectrum.y, dtype=np.float64)
    if x.ndim != 1 or y.shape != x.shape or len(x) < 3:
        raise ValueError("Automatic baselines require matching 1-D X,Y arrays with at least 3 samples.")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Automatic baseline input must contain only finite values.")
    with np.errstate(over="ignore"):
        steps = np.diff(x)
        span = float(np.max(x) - np.min(x))
    if not np.all(np.isfinite(steps)) or not np.isfinite(span):
        raise ValueError("The wavenumber range is too large for finite arithmetic.")
    if not (np.all(steps > 0) or np.all(steps < 0)):
        raise ValueError("Automatic baseline wavenumbers must be unique and strictly monotonic.")
    descending = bool(steps[0] < 0)
    if descending:
        x, y = x[::-1], y[::-1]
    measured_x = x
    x = x - x[0]
    width = requested if requested / 2 < span else 2 * span
    if 0 < width < float(np.median(np.diff(x))):
        width = float(np.median(np.diff(x)))
    warnings: list[str] = []
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            signal = _median_signal(x, y)
            differences = np.diff(y)
            sigma = float(1.4826 * np.median(np.abs(differences - np.median(differences))) / np.sqrt(2))
            numerical_floor = max(1e-12, 32 * np.finfo(float).eps * float(np.max(np.abs(y))))
            tolerance = (
                numerical_floor if width == 0
                else max(3 * sigma, 0.003 * float(np.ptp(signal)), numerical_floor)
            )
            contact_tolerance = max(tolerance, 3 * sigma)
            envelope = _local_envelope(x, signal, width)
            indices = _data_anchor_indices(
                x, y, signal, envelope, width, tolerance, contact_tolerance,
            )
            anchors = [(float(measured_x[index]), float(y[index])) for index in indices]
            baseline = linear_baseline(spectrum.x, anchors)
            corrected = spectrum.y - baseline
        except FloatingPointError as error:
            raise ValueError("Numerical overflow or invalid arithmetic during automatic baselining.") from error
    if not np.all(np.isfinite(baseline)) or not np.all(np.isfinite(corrected)):
        raise ValueError("Automatic baseline calculation produced non-finite values.")
    boundary_width = max(PREFILTER_WIDTH / 2, width)
    boundary = (x < boundary_width) | (x > span - boundary_width)
    if descending:
        boundary = boundary[::-1]
    warnings.append("Endpoint windows are truncated and edge prefiltering is omitted; inspect boundary-marked samples.")
    if width > 0:
        if requested / 2 >= span:
            warnings.append("Window radius spans the spectrum; using a single global lower hull as the selection guide.")
        elif requested < width:
            warnings.append("Requested width is below median sample spacing; using that spacing.")
        if float(np.max(np.diff(x))) > width / 2:
            warnings.append("Sampling gaps exceed half the window width; local estimates are weakly constrained.")
    if len(anchors) > max(50, len(x) // 10):
        warnings.append("Dense anchor refinement; inspect noise and remaining structure.")
    negative = corrected < -max(3 * sigma, numerical_floor)
    runs = np.flatnonzero(np.diff(np.r_[False, negative, False]))
    if any(abs(spectrum.x[stop - 1] - spectrum.x[start]) >= max(10.0, width / 4)
           for start, stop in zip(runs[::2], runs[1::2])):
        warnings.append("A sustained negative corrected region exceeds the estimated noise.")
    if float(np.max(np.abs(y - signal))) > max(10 * sigma, 10 * tolerance):
        warnings.append("Median prefilter changed sharp structure; inspect possible spikes or unresolved bands.")
    return AutomaticBaseline(
        anchors=tuple(anchors), baseline=baseline, corrected=corrected,
        coarseness=int(coarseness), requested_width=requested, effective_width=width,
        noise_sigma=sigma, simplification_tolerance=tolerance,
        boundary_mask=boundary, warnings=tuple(warnings),
    )
