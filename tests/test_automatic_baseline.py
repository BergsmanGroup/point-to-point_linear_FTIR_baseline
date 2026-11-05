import csv
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure
from numpy.testing import assert_allclose, assert_array_equal

from automatic_baseline import (
    ALGORITHM_VERSION, _local_envelope, _median_signal, automatic_baseline, coarseness_width,
)
from baseline_review import _metrics, _panel, load_references
from spectra_model import Spectrum, SpectraSession, linear_baseline, load_spectrum


ROOT = Path(__file__).resolve().parents[1]


def spectrum(x, y):
    return Spectrum("synthetic", np.asarray(x, dtype=float), np.asarray(y, dtype=float), Path("test.csv"))


class AutomaticBaselineTests(unittest.TestCase):
    def assert_data_anchors_and_straight_segments(self, raw, result):
        samples = dict(zip(raw.x, raw.y))
        xs = [x for x, _ in result.anchors]
        self.assertEqual(xs, sorted(set(xs)))
        for x, y in result.anchors:
            self.assertIn(x, samples)
            self.assertEqual(y, samples[x])
            index = np.flatnonzero(raw.x == x)[0]
            self.assertAlmostEqual(result.corrected[index], 0, places=14)
        assert_array_equal(linear_baseline(raw.x, list(result.anchors)), result.baseline)
        for (left_x, left_y), (right_x, right_y) in zip(result.anchors[:-1], result.anchors[1:]):
            section = (raw.x >= left_x) & (raw.x <= right_x)
            line = left_y + (raw.x[section] - left_x) * (right_y - left_y) / (right_x - left_x)
            assert_allclose(result.baseline[section], line, atol=1e-14, rtol=1e-14)

    def test_integer_parameter_and_physical_mapping(self):
        assert_allclose([coarseness_width(c) for c in [0, 10, 40, 60, 100]], [0, 5, 75, 315, 5115])
        self.assertEqual(coarseness_width(np.int64(40)), 75)
        for value in [True, False, np.bool_(True), 1.0, "40", None, -1, 101, np.nan]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                coarseness_width(value)
        widths = [coarseness_width(c) for c in range(101)]
        self.assertTrue(np.all(np.diff(widths) > 0))

    def test_invalid_inputs(self):
        for x, y in [
            ([0, 1], [1, 2]), ([0, 1, 2], [1, 2]), ([[0, 1, 2]], [[1, 2, 3]]),
            ([0, 0, 1], [0, 0, 0]), ([0, 2, 1], [0, 0, 0]),
            ([0, 1, np.inf], [0, 0, 0]), ([0, 1, 2], [0, np.nan, 0]),
            ([-1e308, 0, 1e308], [0, 0, 0]),
        ]:
            with self.subTest(x=x, y=y), self.assertRaises(ValueError):
                automatic_baseline(spectrum(x, y), 50)

    def test_constant_and_affine_baselines_on_nonuniform_grids(self):
        rng = np.random.default_rng(42)
        x = np.cumsum(rng.uniform(0.1, 0.6, 2000))
        for y in [np.full(x.size, -0.5), 0.003 * x - 0.8]:
            raw = spectrum(x, y)
            for coarseness in [0, 40, 70, 100]:
                with self.subTest(coarseness=coarseness):
                    result = automatic_baseline(raw, coarseness)
                    assert_allclose(result.baseline, y, atol=1e-11, rtol=0)
                    assert_allclose(result.corrected, 0, atol=1e-11, rtol=0)
                    self.assertEqual(len(result.anchors), 2)

    def test_coordinate_windows_match_brute_force_hulls(self):
        x = np.array([0, 0.2, 1.5, 2, 4, 9, 9.1, 10.0])
        y = np.array([0, 1, 2, -1, 3, 0, 4, 1.0])
        width = 4
        total, weights = np.zeros_like(y), np.zeros_like(y)
        for center in np.arange(0, 11, 1.0):
            ids = np.flatnonzero(abs(x - center) <= width / 2)
            for index in ids:
                # All chords through pairs bracketed around the evaluation sample.
                values = [y[index]]
                for left in ids[ids < index]:
                    for right in ids[ids > index]:
                        t = (x[index] - x[left]) / (x[right] - x[left])
                        values.append(y[left] + t * (y[right] - y[left]))
                weight = max(0, 1 - abs(x[index] - center) / (width / 2))
                total[index] += min(values) * weight
                weights[index] += weight
        assert_allclose(_local_envelope(x, y, width), total / weights, atol=1e-14)

    def test_direction_shape_offset_and_session_compatibility(self):
        x = np.linspace(650, 4000, 3000)
        y = -0.1 + 1e-5 * x + 0.05 * np.exp(-((x - 1500) / 80) ** 2)
        raw = spectrum(x, y)
        raw.parent = spectrum(x, np.zeros_like(x))
        raw.offset = 100
        raw.anchors = ((1000, -0.2), (3500, -0.1))
        before = (raw.x.copy(), raw.y.copy(), raw.anchors, raw.offset)
        forward = automatic_baseline(raw, 55)
        reverse = automatic_baseline(spectrum(x[::-1], y[::-1]), 55)
        self.assertEqual(forward.algorithm_version, ALGORITHM_VERSION)
        self.assertEqual(forward.anchors, reverse.anchors)
        assert_allclose(forward.baseline, reverse.baseline[::-1], atol=0)
        assert_array_equal(forward.boundary_mask, reverse.boundary_mask[::-1])
        assert_allclose(y, forward.baseline + forward.corrected, atol=1e-15)
        self.assertEqual(forward.baseline.shape, y.shape)
        assert_array_equal(raw.x, before[0])
        assert_array_equal(raw.y, before[1])
        self.assertEqual((raw.anchors, raw.offset), before[2:])
        assert_allclose(linear_baseline(x, list(forward.anchors)), forward.baseline, atol=0)
        session = SpectraSession()
        session.add(raw)
        session.anchors = list(forward.anchors)
        corrected = session.apply()
        assert_allclose(corrected.y, forward.corrected, atol=0)
        self.assertEqual(corrected.anchors, forward.anchors)

    def test_extremes_remove_or_preserve_broad_features(self):
        x = np.linspace(0, 2000, 4001)
        baseline = -0.05 + 0.00002 * x
        narrow = 0.03 * np.exp(-((x - 700) / 8) ** 2)
        broad = 0.08 * np.exp(-((x - 1200) / 100) ** 2)
        raw = spectrum(x, baseline + narrow + broad)
        fine = automatic_baseline(raw, 0)
        moderate = automatic_baseline(raw, 65)
        coarse = automatic_baseline(raw, 100)
        self.assertLess(float(np.max(abs(fine.corrected))), 0.001)
        self.assertLess(float(np.sqrt(np.mean((moderate.baseline - baseline) ** 2))), 0.006)
        for index in [int(np.argmax(narrow)), int(np.argmax(broad))]:
            self.assertGreater(moderate.corrected[index], 0.75 * (narrow[index] + broad[index]))
        assert_allclose(coarse.baseline, baseline, atol=1e-6)
        self.assertEqual(coarse.effective_width, 4000)
        self.assertTrue(any("global lower hull" in message for message in coarse.warnings))
        self.assertLessEqual(len(coarse.anchors), 3)

    def test_sampling_density_and_irregular_grid(self):
        def signal(x):
            return -0.03 + 1e-5 * x + 0.08 * np.exp(-((x - 1500) / 100) ** 2)

        dense_x = np.linspace(650, 4000, 6701)
        dense = automatic_baseline(spectrum(dense_x, signal(dense_x)), 60)
        rng = np.random.default_rng(3)
        irregular = np.r_[650, np.sort(rng.uniform(650, 4000, 6500)), 4000]
        for x in [dense_x[::2], irregular]:
            result = automatic_baseline(spectrum(x, signal(x)), 60)
            assert_allclose(result.baseline, np.interp(x, dense_x, dense.baseline), atol=0.0015, rtol=0)
            self.assertEqual(result.requested_width, dense.requested_width)

    def test_on_data_selection_noise_and_spikes(self):
        rng = np.random.default_rng(2)
        x = np.linspace(650, 4000, 6950)
        y = 0.00001 * x + 0.04 * np.exp(-((x - 1800) / 50) ** 2)
        y += rng.normal(0, 0.0001, x.size)
        y[1000] += 0.2
        y[2000] -= 0.2
        result = automatic_baseline(spectrum(x, y), 55)
        signal = _median_signal(x - x[0], y)
        self.assert_data_anchors_and_straight_segments(spectrum(x, y), result)
        self.assertLessEqual(
            float(np.max(result.baseline - signal)), result.simplification_tolerance + 1e-12,
        )
        self.assertNotIn(float(x[1000]), [point[0] for point in result.anchors])
        self.assertNotIn(float(x[2000]), [point[0] for point in result.anchors])
        self.assertLess(len(result.anchors), 100)
        self.assertLess(abs(result.noise_sigma / 0.0001 - 1), 0.25)
        self.assertTrue(any("sharp structure" in message for message in result.warnings))
        self.assertLess(result.corrected[2000], -0.19)
        self.assertGreater(result.corrected[1000], 0.19)
        self.assertTrue(np.all(np.isfinite(result.baseline)))

    def test_large_gaps_small_span_and_boundary_peak(self):
        raw = spectrum([0, 0.5, 1, 999, 999.5, 1000], [1, 0, 0, 0, 0, 0])
        result = automatic_baseline(raw, 10)
        self.assertTrue(any("Sampling gaps" in message for message in result.warnings))
        self.assertTrue(result.boundary_mask[0])
        self.assertTrue(result.boundary_mask[-1])
        self.assertEqual(result.baseline[0], 1)
        sparse = automatic_baseline(spectrum([0, 10, 20], [0, 1, 0]), 1)
        self.assertEqual(sparse.effective_width, 10)
        self.assertTrue(any("sample spacing" in message for message in sparse.warnings))
        tiny = automatic_baseline(spectrum([0, 0.1, 0.2], [0, 1, 0]), 100)
        self.assertEqual(tiny.effective_width, 0.4)
        self.assertTrue(np.all(np.isfinite(tiny.baseline)))

    def test_smooth_transition_to_global_hull_and_full_boundary_support(self):
        x = np.linspace(0, 100, 1001)
        y = 0.5 * np.exp(-((x - 40) / 20) ** 2) - 0.0001 * x ** 2
        near_global = _local_envelope(x, y, 199.999)
        global_hull = _local_envelope(x, y, 200)
        self.assertLess(float(np.max(abs(near_global - global_hull))), 0.1 * np.max(abs(np.diff(y))))
        raw = spectrum(x, y)
        result = automatic_baseline(raw, 30)
        self.assertTrue(result.boundary_mask[np.argmin(abs(x - 30))])
        self.assertFalse(result.boundary_mask[np.argmin(abs(x - 50))])

    def test_all_reference_spectra_and_scale_separation(self):
        folder = ROOT / "Automated_Baseline_Examples" / "Coarse Baseline"
        paths = [path for path in folder.glob("*.csv") if "_Baseline" not in path.stem]
        self.assertEqual(len(paths), 5)
        for path in paths:
            with self.subTest(spectrum=path.stem):
                raw = load_spectrum(path)
                fine, middle, coarse = [automatic_baseline(raw, c) for c in [0, 55, 100]]
                self.assertEqual(middle.baseline.shape, raw.y.shape)
                assert_allclose(raw.y, middle.baseline + middle.corrected, atol=1e-15)
                self.assertLess(np.sqrt(np.mean(fine.corrected ** 2)), 0.002)
                self.assertGreater(
                    np.sqrt(np.mean(coarse.corrected ** 2)),
                    2 * np.sqrt(np.mean(middle.corrected ** 2)),
                )
                self.assertEqual(middle.anchors[0][0], float(np.min(raw.x)))
                self.assertEqual(middle.anchors[-1][0], float(np.max(raw.x)))
                for result in (fine, middle, coarse):
                    self.assert_data_anchors_and_straight_segments(raw, result)
                self.assertLess(len(middle.anchors), 100)

    def test_exact_sample_membership_on_nonuniform_grid_in_both_directions(self):
        rng = np.random.default_rng(7)
        x = 1e6 + np.cumsum(rng.uniform(0.1, 0.8, 1500))
        y = -0.5 + 0.002 * (x - x[0]) + 0.02 * np.sin((x - x[0]) / 30)
        y += rng.normal(0, 0.0001, x.size)
        for order in (slice(None), slice(None, None, -1)):
            raw = spectrum(x[order], y[order])
            raw.parent = spectrum(x, np.zeros_like(y))
            raw.offset = 100
            for coarseness in (0, 20, 45, 55, 65, 100):
                with self.subTest(coarseness=coarseness, order=order):
                    self.assert_data_anchors_and_straight_segments(raw, automatic_baseline(raw, coarseness))

    def test_reference_validation_and_metrics(self):
        examples = ROOT / "Automated_Baseline_Examples"
        references = load_references(examples)
        self.assertEqual(len(references), 5)
        for reference in references:
            result = automatic_baseline(reference.raw, 55)
            metrics = _metrics(reference, result)
            self.assertTrue(np.isfinite(metrics["area_1300_1650"]))
            self.assertGreater(metrics["rmse_to_fine"], 0)
            self.assertEqual(metrics["coarseness"], 55)
            self.assertEqual(metrics["anchor_sample_max_error"], 0)
        reference = references[0]
        result = automatic_baseline(reference.raw, 55)
        x, y = result.anchors[0]
        invalid = replace(result, anchors=((x, y + 0.1),) + result.anchors[1:])
        with self.assertRaisesRegex(ValueError, "not an exact measured sample"):
            _metrics(reference, invalid)
        with self.assertRaisesRegex(ValueError, "not the anchor polyline"):
            _metrics(reference, replace(result, baseline=result.baseline + 0.01))
        figure = Figure()
        axes = figure.add_subplot()
        _panel(axes, reference, {55: result}, (55,), corrected=False, zoom=False)
        markers = [line for line in axes.lines if line.get_marker() == "o"]
        self.assertEqual(len(markers), 1)
        assert_array_equal(markers[0].get_xdata(), [x for x, _ in result.anchors])
        assert_array_equal(markers[0].get_ydata(), [y for _, y in result.anchors])
        figure.clear()
        # A shifted baseline must not be silently treated as a manual reference.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = references[0]
            for source in reference.files:
                target = root / source.parent.name / source.name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(source.read_bytes())
            baseline_path = root / reference.fine.source.parent.name / reference.fine.source.name
            with baseline_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.reader(stream))
            rows[1][1] = str(float(rows[1][1]) + 0.1)
            with baseline_path.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerows(rows)
            with self.assertRaisesRegex(ValueError, "offsets or inconsistent anchors"):
                load_references(root)


if __name__ == "__main__":
    unittest.main()
