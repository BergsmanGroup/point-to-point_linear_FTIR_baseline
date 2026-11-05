import tempfile
import unittest
from pathlib import Path

import numpy as np
from numpy.testing import assert_allclose, assert_array_equal

from spectra_model import Spectrum, SpectraSession, linear_baseline, load_spectrum, save_spectrum


ROOT = Path(__file__).resolve().parents[1]


def example() -> Spectrum:
    return Spectrum(
        "raw", np.array([4.0, 3.0, 2.0, 1.0, 0.0]),
        np.array([4.0, 7.0, 4.0, 3.0, 0.0]), Path("raw.csv")
    )


class ModelTests(unittest.TestCase):
    def test_supplied_spectragryph_csv(self):
        spectrum = load_spectrum(next(ROOT.glob("SID*.csv")))
        self.assertEqual(len(spectrum.x), 6950)
        self.assertEqual(spectrum.x[0], 4000.188)
        self.assertEqual(spectrum.y[0], 0.1273825)
        self.assertTrue(np.all(np.diff(spectrum.x) < 0))

    def test_interpolation_sorted_and_extrapolated(self):
        x = np.array([6.0, 4.0, 3.0, 2.0, 1.0, 0.0, -2.0])
        assert_allclose(
            linear_baseline(x, [(4, 8), (0, 0), (2, 2)]),
            [14, 8, 5, 2, 1, 0, -2],
        )
        assert_allclose(
            linear_baseline(x[::-1], [(4, 8), (0, 0), (2, 2)]),
            np.array([14, 8, 5, 2, 1, 0, -2])[::-1],
        )

    def test_bad_baseline(self):
        for points in ([], [(0, 0)], [(0, 0), (0, 1)], [(0, 0), (1, np.nan)]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                linear_baseline(np.array([0.0, 1.0]), points)

    def test_snap_free_undo_and_parent_correction(self):
        session = SpectraSession()
        raw = example()
        original = raw.y.copy()
        session.add(raw)
        self.assertEqual(session.add_anchor(3.1, 999), (3.0, 7.0))
        session.anchors.pop()
        session.add_anchor(0.0, 999)
        session.add_anchor(4.0, 999)
        first = session.apply()
        self.assertIs(first.parent, raw)
        self.assertIs(session.active, first)
        self.assertEqual(first.name, "raw_BaselineCorrected_1")
        baseline = session.last_baseline
        self.assertIsNotNone(baseline)
        self.assertIs(baseline.parent, raw)
        self.assertFalse(baseline.visible)
        self.assertEqual(baseline.name, "raw_Baseline_1")
        assert_allclose(baseline.y, [4, 3, 2, 1, 0])
        self.assertEqual(session.spectra, [raw, first, baseline])
        self.assertEqual(session.anchors, [])
        assert_allclose(first.y, [0, 4, 2, 2, 0])
        assert_array_equal(raw.y, original)
        self.assertEqual(first.offset, 7.0)
        self.assertAlmostEqual(np.min(first.displayed_y), np.max(raw.displayed_y))
        self.assertEqual(session.add_anchor(3.5, 10.0, free=True), (3.5, 3.0))
        session.anchors.clear()
        session.add_anchor(4, 0)
        session.add_anchor(0, 0)
        second = session.apply()
        self.assertIs(second.parent, first)
        self.assertEqual(second.name, "raw_BaselineCorrected_2")
        self.assertEqual(session.spectra, [raw, first, second, session.last_baseline, baseline])
        self.assertAlmostEqual(np.min(second.displayed_y), np.max(first.displayed_y))
        old_second_shift = second.shift
        first.offset = 14
        self.assertEqual(second.shift - old_second_shift, 7)
        second.offset = 0
        self.assertEqual(second.shift, first.shift)
        first.offset = -3.5
        self.assertEqual(first.shift, -3.5)

    def test_apply_can_omit_retained_baseline(self):
        session = SpectraSession()
        raw = example()
        session.add(raw)
        session.add_anchor(0, 0)
        session.add_anchor(4, 0)
        corrected = session.apply(retain_baseline=False)
        self.assertIs(session.active, corrected)
        self.assertIsNone(session.last_baseline)
        self.assertEqual(session.spectra, [raw, corrected])

    def test_anchor_validation(self):
        session = SpectraSession()
        with self.assertRaises(ValueError):
            session.add_anchor(1, 1)
        session.add(example())
        self.assertEqual(session.resolve_anchor(1.1, 0), (1, 3))
        self.assertEqual(session.anchors, [])
        session.add_anchor(1.0, 0)
        for x, y in [(1.1, 0), (10.0, 0), (2.0, np.nan)]:
            with self.subTest(x=x), self.assertRaises(ValueError):
                session.add_anchor(x, y)

    def test_export_removes_all_offsets(self):
        session = SpectraSession()
        session.add(example())
        for _ in range(2):
            session.add_anchor(4, 0)
            session.add_anchor(0, 0)
            session.apply()
        spectrum = session.active
        self.assertIsNotNone(spectrum)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            save_spectrum(spectrum, path, with_offset=False)
            loaded = load_spectrum(path)
            assert_array_equal(loaded.x, spectrum.x)
            assert_array_equal(loaded.y, spectrum.y)
            save_spectrum(spectrum, path, with_offset=True)
            assert_array_equal(load_spectrum(path).y, spectrum.displayed_y)

    def test_loader_formats_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            for delimiter in [",", ";", "\t"]:
                path.write_text(
                    f"name{delimiter}test\nX{delimiter}Y\n"
                    f"1{delimiter}2{delimiter}\n2{delimiter}3{delimiter}\n",
                    encoding="utf-8-sig",
                )
                assert_array_equal(load_spectrum(path).y, [2, 3])
            for text in [
                "headers only\n", "0,1\n", "0,1\n0,2\n", "0,1\n2,2\n1,3\n",
                "0,1\n1,nan\n", "0,1\n1,2\nbad,row\n", "0,inf\n1,2\n",
            ]:
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(ValueError):
                    load_spectrum(path)


if __name__ == "__main__":
    unittest.main()
