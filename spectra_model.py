"""Numerical operations and file I/O independent of the desktop interface."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]


def _detect_delimiter(sample: str) -> str:
    # Spectragryph metadata can have fewer columns than its numeric rows.
    for delimiter in (",", ";", "\t"):
        for row in csv.reader(sample.splitlines(), delimiter=delimiter):
            if len(row) < 2:
                continue
            try:
                float(row[0])
                float(row[1])
            except ValueError:
                continue
            return delimiter
    raise ValueError("No numeric X,Y data found near the beginning of the file.")


@dataclass(eq=False)
class Spectrum:
    name: str
    x: FloatArray
    y: FloatArray
    source: Path
    parent: Spectrum | None = None
    offset: float = 0.0
    visible: bool = True
    anchors: tuple[tuple[float, float], ...] = ()

    @property
    def shift(self) -> float:
        if self.parent is None:
            return 0.0
        return self.parent.shift + self.offset

    @property
    def displayed_y(self) -> FloatArray:
        return self.y + self.shift

    def display_offset_at(self, x: float) -> float:
        """Return the y offset used to display a point at X."""
        return self.shift

    def nearest_index(self, x: float) -> int:
        """Return the index of the sample nearest to X."""
        values = self.x if self.x[0] < self.x[-1] else self.x[::-1]
        position = int(np.searchsorted(values, x))
        if position == 0:
            return 0 if self.x[0] < self.x[-1] else len(self.x) - 1
        if position == len(values):
            return len(self.x) - 1 if self.x[0] < self.x[-1] else 0
        before = values[position - 1]
        after = values[position]
        nearest = position - 1 if x - before <= after - x else position
        return nearest if self.x[0] < self.x[-1] else len(self.x) - 1 - nearest


def load_spectrum(path: Path) -> Spectrum:
    """Read two-column numeric CSV with optional leading headers/trailing columns."""
    rows: list[tuple[float, float]] = []
    started = False
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        delimiter = _detect_delimiter(sample)
        for line_number, row in enumerate(csv.reader(stream, delimiter=delimiter), 1):
            if not row or all(not cell.strip() for cell in row):
                continue
            try:
                x, y = float(row[0]), float(row[1])
            except (ValueError, IndexError) as error:
                if started:
                    raise ValueError(f"Non-numeric data at line {line_number}.") from error
                continue
            if not np.isfinite(x) or not np.isfinite(y):
                raise ValueError(f"Non-finite data at line {line_number}.")
            started = True
            rows.append((x, y))
    if len(rows) < 2:
        raise ValueError("The file must contain at least two numeric X,Y rows.")
    data = np.asarray(rows, dtype=np.float64)
    if np.unique(data[:, 0]).size != len(rows):
        raise ValueError("Wavenumbers must be unique.")
    differences = np.diff(data[:, 0])
    if not (np.all(differences > 0) or np.all(differences < 0)):
        raise ValueError("Wavenumbers must be strictly increasing or decreasing.")
    return Spectrum(path.stem, data[:, 0].copy(), data[:, 1].copy(), path)


def linear_baseline(x: FloatArray, anchors: list[tuple[float, float]]) -> FloatArray:
    """Interpolate anchors, extending the end segments over the entire X range."""
    if len(anchors) < 2:
        raise ValueError("Add at least two baseline points before applying.")
    points = np.asarray(sorted(anchors), dtype=np.float64)
    if not np.all(np.isfinite(points)):
        raise ValueError("Baseline points must be finite.")
    px, py = points[:, 0], points[:, 1]
    if np.any(np.diff(px) <= 0):
        raise ValueError("Baseline points must have distinct X coordinates.")
    baseline = np.interp(x, px, py)
    left = x < px[0]
    right = x > px[-1]
    baseline[left] = py[0] + (x[left] - px[0]) * (py[1] - py[0]) / (px[1] - px[0])
    baseline[right] = py[-1] + (x[right] - px[-1]) * (py[-1] - py[-2]) / (px[-1] - px[-2])
    return baseline


@dataclass
class SpectraSession:
    spectra: list[Spectrum] = field(default_factory=list)
    active: Spectrum | None = None
    anchors: list[tuple[float, float]] = field(default_factory=list)
    correction_count: int = 0

    def add(self, spectrum: Spectrum) -> None:
        self.spectra.append(spectrum)
        self.active = spectrum
        self.anchors.clear()

    def resolve_anchor(self, x: float, y: float, free: bool = False) -> tuple[float, float]:
        """Validate and resolve cursor coordinates without changing committed anchors."""
        spectrum = self.active
        if spectrum is None:
            raise ValueError("Open and activate a spectrum first.")
        if not np.isfinite(x) or not np.isfinite(y):
            raise ValueError("Baseline coordinates must be finite.")
        if not float(np.min(spectrum.x)) <= x <= float(np.max(spectrum.x)):
            raise ValueError("Choose a point within the active spectrum's X range.")
        if free:
            point = (float(x), float(y - spectrum.display_offset_at(x)))
        else:
            index = spectrum.nearest_index(x)
            point = (float(spectrum.x[index]), float(spectrum.y[index]))
        if any(existing[0] == point[0] for existing in self.anchors):
            raise ValueError("A baseline point already exists at this X coordinate. Undo it first.")
        return point

    def add_anchor(self, x: float, y: float, free: bool = False) -> tuple[float, float]:
        point = self.resolve_anchor(x, y, free)
        self.anchors.append(point)
        return point

    def apply(self) -> Spectrum:
        parent = self.active
        if parent is None:
            raise ValueError("Open and activate a spectrum first.")
        baseline = linear_baseline(parent.x, self.anchors)
        self.correction_count += 1
        spectrum = Spectrum(
            name=f"{parent.source.stem}_BaselineCorrected_{self.correction_count}",
            x=parent.x.copy(),
            y=parent.y - baseline,
            source=parent.source,
            parent=parent,
            offset=round(float(np.max(parent.y) - np.min(parent.y - baseline)), 1),
            anchors=tuple(self.anchors),
        )
        self.add(spectrum)
        return spectrum


def save_spectrum(spectrum: Spectrum, path: Path, with_offset: bool) -> None:
    values = spectrum.displayed_y if with_offset else spectrum.y
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Wavenumbers [1/cm]", spectrum.name])
        writer.writerows(zip(spectrum.x, values))
