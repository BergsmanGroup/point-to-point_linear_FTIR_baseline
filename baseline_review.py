"""Reproduce automatic baseline sweeps and review plots without launching the GUI."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from automatic_baseline import (
    ALGORITHM_VERSION, PREFILTER_WIDTH, AutomaticBaseline, automatic_baseline, coarseness_width,
)
from spectra_model import Spectrum, linear_baseline, load_spectrum


ROOT = Path(__file__).resolve().parent
REVIEW_LEVELS = (45, 55, 65)
COLORS = {0: "#0072B2", 45: "#0072B2", 55: "#009E73", 65: "#D55E00", 100: "#D55E00"}
FINE_COLOR = "#8B5AA8"
COARSE_COLOR = "#B58218"
FINGERPRINT = (1300.0, 1650.0)


@dataclass
class References:
    raw: Spectrum
    fine: Spectrum
    coarse: Spectrum
    fine_anchors: tuple[tuple[float, float], ...]
    coarse_anchors: tuple[tuple[float, float], ...]
    files: tuple[Path, ...]


def _read_anchors(path: Path) -> tuple[tuple[float, float], ...]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream)
        next(rows)
        anchors = tuple((float(row[0]), float(row[1])) for row in rows)
    if len(anchors) < 2:
        raise ValueError(f"{path}: at least two manual anchors are required.")
    return anchors


def load_references(root: Path) -> list[References]:
    references = []
    folders = [root / "Fine Baseline", root / "Coarse Baseline"]
    names = [
        {path.stem for path in folder.glob("*.csv") if "_Baseline" not in path.stem}
        for folder in folders
    ]
    if not names[0] or names[0] != names[1]:
        raise ValueError("Fine and coarse folders must contain matching original spectra.")
    for name in sorted(names[0]):
        originals, baselines, anchor_sets = [], [], []
        files = []
        for folder in folders:
            original_path = folder / (name + ".csv")
            original = load_spectrum(original_path)
            matches = [
                path for path in folder.glob(name + "_Baseline_[0-9]*.csv")
                if not path.stem.endswith("_Anchors")
            ]
            if len(matches) != 1:
                raise ValueError(f"{folder}: expected exactly one baseline for {name}.")
            baseline_path = matches[0]
            suffix = baseline_path.stem.rsplit("_Baseline_", 1)[1]
            corrected_path = folder / f"{name}_BaselineCorrected_{suffix}.csv"
            anchor_path = baseline_path.with_name(baseline_path.stem + "_Anchors.csv")
            corrected_anchor_path = corrected_path.with_name(corrected_path.stem + "_Anchors.csv")
            baseline, corrected = load_spectrum(baseline_path), load_spectrum(corrected_path)
            anchors = _read_anchors(anchor_path)
            if anchors != _read_anchors(corrected_anchor_path):
                raise ValueError(f"{name}: baseline/corrected anchor exports disagree.")
            if not (
                np.array_equal(original.x, baseline.x)
                and np.array_equal(original.x, corrected.x)
            ):
                raise ValueError(f"{name}: manual exports do not share the original grid.")
            if not (
                np.allclose(original.y - baseline.y, corrected.y, rtol=0, atol=1e-10)
                and np.allclose(linear_baseline(original.x, list(anchors)), baseline.y, rtol=0, atol=1e-10)
            ):
                raise ValueError(f"{name}: manual exports contain offsets or inconsistent anchors.")
            files.extend([original_path, baseline_path, corrected_path, anchor_path, corrected_anchor_path])
            originals.append(original)
            baselines.append(baseline)
            anchor_sets.append(anchors)
        if not (
            np.array_equal(originals[0].x, originals[1].x)
            and np.array_equal(originals[0].y, originals[1].y)
        ):
            raise ValueError(f"{name}: fine and coarse originals differ.")
        references.append(References(
            originals[0], baselines[0], baselines[1], anchor_sets[0], anchor_sets[1], tuple(files),
        ))
    return references


def _rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(values ** 2)))


def _area(x: np.ndarray, y: np.ndarray, mask: np.ndarray) -> float:
    indices = np.flatnonzero(mask)
    indices = indices[np.argsort(x[indices])]
    return float(np.trapezoid(y[indices], x[indices]))


def _metrics(reference: References, result: AutomaticBaseline) -> dict[str, str | int | float]:
    x = reference.raw.x
    samples = dict(zip(x, reference.raw.y))
    if any(px not in samples or py != samples[px] for px, py in result.anchors):
        raise ValueError(f"{reference.raw.name}: automatic anchor is not an exact measured sample.")
    if not np.array_equal(linear_baseline(x, list(result.anchors)), result.baseline):
        raise ValueError(f"{reference.raw.name}: automatic baseline is not the anchor polyline.")
    mask = (x >= FINGERPRINT[0]) & (x <= FINGERPRINT[1])
    band = (x >= 1700) & (x <= 1900)
    if np.count_nonzero(mask) < 2 or not np.any(band):
        raise ValueError(f"{reference.raw.name}: review regions are not covered by the measured grid.")
    return {
        "spectrum": reference.raw.name,
        "coarseness": result.coarseness,
        "requested_width_cm-1": result.requested_width,
        "effective_width_cm-1": result.effective_width,
        "anchor_count": len(result.anchors),
        "anchor_sample_max_error": 0.0,
        "rmse_to_fine": _rmse(result.baseline - reference.fine.y),
        "rmse_to_coarse": _rmse(result.baseline - reference.coarse.y),
        "regional_rmse_to_fine": _rmse((result.baseline - reference.fine.y)[mask]),
        "regional_rmse_to_coarse": _rmse((result.baseline - reference.coarse.y)[mask]),
        "max_error_to_fine": float(np.max(np.abs(result.baseline - reference.fine.y))),
        "max_error_to_coarse": float(np.max(np.abs(result.baseline - reference.coarse.y))),
        "corrected_rms": _rmse(result.corrected),
        "corrected_min": float(np.min(result.corrected)),
        "corrected_max": float(np.max(result.corrected)),
        "negative_fraction": float(np.mean(result.corrected < 0)),
        "negative_beyond_noise_fraction": float(np.mean(result.corrected < -3 * result.noise_sigma)),
        "area_1300_1650": _area(x, result.corrected, mask),
        "peak_1700_1900": float(np.max(result.corrected[band])),
        "noise_sigma": result.noise_sigma,
        "simplification_tolerance": result.simplification_tolerance,
        "boundary_fraction": float(np.mean(result.boundary_mask)),
        "warnings": " | ".join(result.warnings),
    }


def _format_axis(axes: Axes, limits: tuple[float, float], ylabel: str) -> None:
    axes.set_xlim(*limits)
    axes.set_xlabel("Wavenumber (cm$^{-1}$)")
    axes.set_ylabel(ylabel)
    axes.grid(alpha=0.18)
    axes.tick_params(labelsize=8)


def _panel(
    axes: Axes, reference: References, results: dict[int, AutomaticBaseline],
    levels: tuple[int, ...], *, corrected: bool, zoom: bool,
) -> None:
    raw = reference.raw
    limits = (1900.0, 1200.0) if zoom else (float(np.max(raw.x)), float(np.min(raw.x)))
    mask = (raw.x >= limits[1]) & (raw.x <= limits[0])
    if not corrected:
        axes.plot(raw.x[mask], raw.y[mask], color="#aaaaaa", lw=1, label="Uncorrected")
    for name, baseline, color in [
        ("Manual fine", reference.fine, FINE_COLOR),
        ("Manual coarse", reference.coarse, COARSE_COLOR),
    ]:
        values = raw.y - baseline.y if corrected else baseline.y
        axes.plot(raw.x[mask], values[mask], color=color, ls="--", lw=1.1, label=name)
    for level in levels:
        result = results[level]
        values = result.corrected if corrected else result.baseline
        axes.plot(
            raw.x[mask], values[mask], color=COLORS[level], lw=1.25,
            label=f"C={level}, W={result.effective_width:.0f}, n={len(result.anchors)}",
        )
        if not corrected:
            points = np.asarray(result.anchors)
            visible = (points[:, 0] >= limits[1]) & (points[:, 0] <= limits[0])
            axes.plot(
                points[visible, 0], points[visible, 1], linestyle="none",
                marker="o", markersize=3.5, markerfacecolor="white",
                markeredgecolor=COLORS[level], markeredgewidth=0.8,
            )
    if corrected:
        axes.axhline(0, color="#555555", lw=0.6)
    elif not zoom:
        width = min(
            max(results[level].effective_width for level in levels),
            float(np.ptp(raw.x)) / 2,
        )
        axes.axvspan(limits[1], limits[1] + width, color="#888888", alpha=0.06)
        axes.axvspan(limits[0] - width, limits[0], color="#888888", alpha=0.06)
    _format_axis(axes, limits, "Corrected absorbance" if corrected else "Absorbance / baseline")


def _save_figure(figure: Figure, path: Path) -> None:
    FigureCanvasAgg(figure)
    figure.savefig(path, dpi=150, facecolor="white")
    figure.clear()


def generate_review(reference_root: Path, output: Path) -> None:
    references = load_references(reference_root)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    anchor_rows = []
    stored: list[dict[int, AutomaticBaseline]] = []
    sample_metadata = []
    for reference in references:
        print(f"Sweeping C=0..100: {reference.raw.name}", flush=True)
        results = {}
        sample_rows = []
        for level in range(101):
            result = automatic_baseline(reference.raw, level)
            row = _metrics(reference, result)
            rows.append(row)
            sample_rows.append(row)
            if level in (*REVIEW_LEVELS, 0, 100):
                results[level] = result
            if level in REVIEW_LEVELS:
                anchor_rows.extend(
                    (reference.raw.name, level, index, x, y)
                    for index, (x, y) in enumerate(result.anchors, 1)
                )
        stored.append(results)
        x, y = reference.raw.x, reference.raw.y
        mask = (x >= FINGERPRINT[0]) & (x <= FINGERPRINT[1])
        best_fine = min(sample_rows, key=lambda row: float(row["rmse_to_fine"]))
        best_coarse = min(sample_rows, key=lambda row: float(row["rmse_to_coarse"]))
        sample_metadata.append({
            "spectrum": reference.raw.name,
            "samples": len(x),
            "manual_fine_anchor_count": len(reference.fine_anchors),
            "manual_coarse_anchor_count": len(reference.coarse_anchors),
            "manual_separation_rmse": _rmse(reference.fine.y - reference.coarse.y),
            "manual_regional_separation_rmse": _rmse((reference.fine.y - reference.coarse.y)[mask]),
            "manual_fine_area_1300_1650": _area(x, y - reference.fine.y, mask),
            "manual_coarse_area_1300_1650": _area(x, y - reference.coarse.y, mask),
            "best_global_fine_C": best_fine["coarseness"],
            "best_global_coarse_C": best_coarse["coarseness"],
            "best_global_fine_rmse": best_fine["rmse_to_fine"],
            "best_global_coarse_rmse": best_coarse["rmse_to_coarse"],
            "selected": [row for row in sample_rows if row["coarseness"] in (*REVIEW_LEVELS, 0, 100)],
        })
        figure = Figure(figsize=(14, 9), layout="constrained")
        axes = figure.subplots(2, 2)
        for row_index, zoom in enumerate((False, True)):
            for column, corrected in enumerate((False, True)):
                ax = axes[row_index, column]
                _panel(ax, reference, results, REVIEW_LEVELS, corrected=corrected, zoom=zoom)
                ax.set_title(("Corrected spectra" if corrected else "Baseline drawing") + (" - detail" if zoom else ""))
                if row_index == 0:
                    ax.legend(fontsize=7, loc="best")
        figure.suptitle(
            f"{reference.raw.name}\nStraight segments between measured anchors (circles); C=45 / 55 / 65",
            fontsize=12,
        )
        _save_figure(figure, output / f"{reference.raw.name}_comparison.png")

    with (output / "metrics.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (output / "review_anchors.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["spectrum", "coarseness", "anchor_order", "wavenumber_cm-1", "unshifted_absorbance"])
        writer.writerows(anchor_rows)

    for filename, levels, zoom, subtitle in [
        ("review_overview.png", REVIEW_LEVELS, True, "Candidate range: C=45 / 55 / 65"),
        ("parameter_extremes.png", (0, 100), False, "Deliberately excessive endpoints: C=0 / 100"),
    ]:
        figure = Figure(figsize=(14, 3.2 * len(references)), layout="constrained")
        axes = figure.subplots(len(references), 2, squeeze=False)
        for index, (reference, results) in enumerate(zip(references, stored)):
            for column, corrected in enumerate((False, True)):
                ax = axes[index, column]
                _panel(ax, reference, results, levels, corrected=corrected, zoom=zoom)
                short = reference.raw.name.replace("_Aperature32_", " / ")
                ax.set_title(short + (" - corrected" if corrected else " - baseline"), fontsize=9)
                if index == 0:
                    ax.legend(fontsize=7, loc="best")
        figure.suptitle(
            subtitle + "\nCircles: measured anchors joined by straight lines. Manual drawings are references.",
            fontsize=13,
        )
        _save_figure(figure, output / filename)

    figure = Figure(figsize=(13, 3 * len(references)), layout="constrained")
    axes = figure.subplots(len(references), 2, squeeze=False)
    for index, reference in enumerate(references):
        sample_rows = [row for row in rows if row["spectrum"] == reference.raw.name]
        for column, regional in enumerate((False, True)):
            ax = axes[index, column]
            prefix = "regional_" if regional else ""
            for label, key, color in [
                ("Distance to manual fine", prefix + "rmse_to_fine", FINE_COLOR),
                ("Distance to manual coarse", prefix + "rmse_to_coarse", COARSE_COLOR),
            ]:
                ax.plot(range(101), [row[key] for row in sample_rows], color=color, label=label)
            ax.axvspan(min(REVIEW_LEVELS), max(REVIEW_LEVELS), alpha=0.08, color="#009E73")
            ax.set_xlabel("Coarseness C (larger = wider bridging)")
            ax.set_ylabel("Baseline RMSE (absorbance)")
            ax.set_title(reference.raw.name + (" / 1300-1650" if regional else " / full range"), fontsize=8)
            ax.grid(alpha=0.2)
            if index == 0:
                ax.legend(fontsize=8)
    figure.suptitle("Reference distances across the entire parameter range (not a correctness score)")
    _save_figure(figure, output / "parameter_sweep.png")

    metadata = {
        "algorithm_version": ALGORITHM_VERSION,
        "parameter": "integer C in [0,100]; W=5*(2**(C/10)-1) cm^-1",
        "prefilter_full_width_cm-1": PREFILTER_WIDTH,
        "review_levels": {str(level): coarseness_width(level) for level in REVIEW_LEVELS},
        "metric_region_cm-1": FINGERPRINT,
        "plot_detail_cm-1": [1200, 1900],
        "assumption": "Unshifted absorbance with positive-going bands; manual drawings are not ground truth.",
        "anchor_rule": "Exact original X,Y samples, joined only by linear_baseline; no envelope-valued anchors.",
        "reference_checks": "Fine/coarse originals identical; grids aligned; anchors reconstruct baselines; original-baseline=corrected.",
        "samples": sample_metadata,
        "input_sha256": {
            str(path.relative_to(reference_root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for reference in references for path in reference.files
        },
    }
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        f"Saved {len(references) + 3} PNGs, metrics.csv, review_anchors.csv, and run_metadata.json in {output}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, default=ROOT / "Automated_Baseline_Examples")
    parser.add_argument("--output", type=Path, default=ROOT / "Automated_Baseline_Examples" / "Automated_Results")
    args = parser.parse_args()
    generate_review(args.examples, args.output)


if __name__ == "__main__":
    main()
