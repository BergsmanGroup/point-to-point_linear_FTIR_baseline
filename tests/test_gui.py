import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from matplotlib.backend_bases import MouseButton, MouseEvent
from numpy.testing import assert_allclose

from ftir_gui import BaselineApp
from spectra_model import load_spectrum


ROOT = Path(__file__).resolve().parents[1]


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.window = tk.Toplevel(self.root)
        self.app = BaselineApp(self.window)
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "raw.csv"
        self.path.write_text("X,Y\n4,4\n3,7\n2,4\n1,3\n0,0\n", encoding="utf-8")
        self.app.open_path(self.path)
        self.window.update()
        self.assertTrue(self.app.add_points.get())
        self.errors = []
        self.window.report_callback_exception = self.record_error

    def record_error(self, exception, value, traceback):
        self.errors.append(value)

    def tearDown(self):
        self.app._cancel_flash()
        self.window.destroy()
        self.root.update()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def plot_event(self, name, x, y, button=MouseButton.LEFT, key=None):
        self.app.canvas.draw()
        px, py = self.app.axes.transData.transform((x, y))
        event = MouseEvent(name, self.app.canvas, px, py, button=button, key=key)
        self.app.canvas.callbacks.process(name, event)
        self.window.update()

    def click_plot(self, x, y, button=MouseButton.LEFT, key=None):
        self.plot_event("button_press_event", x, y, button, key)
        self.plot_event("button_release_event", x, y, button, key)

    def click_row(self, spectrum, checkbox=False, release=True):
        row = self.app._row_for(spectrum)
        self.app.table.see(row)
        self.window.update()
        x, y, width, height = self.app.table.bbox(row)
        click_x = x + (20 if checkbox else 90)
        self.app.table.event_generate("<ButtonPress-1>", x=click_x, y=y + height // 2)
        self.window.update()
        if release:
            self.app.table.event_generate("<ButtonRelease-1>", x=click_x, y=y + height // 2)
            self.window.update()

    def correct(self):
        self.app.session.add_anchor(0, 0)
        self.app.session.add_anchor(4, 0)
        self.app.apply()
        self.window.update()
        return self.app.session.active

    def test_click_snap_shift_undo_clear_apply(self):
        raw = self.app.session.active
        self.click_plot(3.05, 2)
        assert_allclose(self.app.session.anchors, [(3, 7)])
        self.click_plot(1.5, 2.5, key="shift")
        assert_allclose(self.app.session.anchors[-1], [1.5, 2.5], atol=1e-10)
        self.assertTrue(self.app.baseline_line.get_visible())
        self.assertEqual(len(self.app.baseline_line.get_xdata()), 2)
        self.click_plot(2, 2, button=MouseButton.RIGHT)
        self.assertEqual(len(self.app.session.anchors), 1)
        self.app.clear_button.invoke()
        self.assertEqual(self.app.session.anchors, [])
        self.assertFalse(self.app.baseline_line.get_visible())
        child = self.correct()
        self.assertIs(child.parent, raw)
        self.assertTrue(child.visible)
        self.assertEqual(self.app.table.selection(), (self.app._row_for(child),))
        self.assertEqual(self.app.lines[child].get_linewidth(), 2.8)
        self.assertIsNotNone(self.app.flash_job)
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            self.window.update()
            time.sleep(0.01)
        self.assertIsNone(self.app.flash_job)
        self.assertEqual(self.app.lines[child].get_linewidth(), 1)
        self.assertFalse(self.app.baseline_line.get_visible())
        self.assertEqual(self.app.session.anchors, [])
        # A free anchor on a displayed corrected spectrum must remove its shift.
        self.click_plot(2.0, float(child.displayed_y[2]), key="shift")
        assert_allclose(self.app.session.anchors[0], [2, child.y[2]], atol=1e-10)

    def test_visible_activation_prompt_cancel_accept_and_hold(self):
        raw = self.app.session.active
        child = self.correct()
        self.app._finish_flash()
        self.app.session.add_anchor(1, 0)
        with patch("ftir_gui.messagebox.askokcancel", return_value=False) as confirm:
            self.click_row(raw)
        confirm.assert_called_once()
        self.assertIs(self.app.session.active, child)
        self.assertEqual(len(self.app.session.anchors), 1)
        self.assertEqual(self.app.table.selection(), (self.app._row_for(child),))
        self.assertEqual(self.app.lines[child].get_linewidth(), 2.8)
        self.assertIsNotNone(self.app.flash_job)
        with patch("ftir_gui.messagebox.askokcancel", return_value=True):
            self.click_row(raw, release=False)
            self.app.table.event_generate("<ButtonRelease-1>", x=90, y=30)
            self.window.update()
        self.assertIs(self.app.session.active, raw)
        self.assertEqual(self.app.session.anchors, [])
        self.assertEqual(self.app.lines[raw].get_linewidth(), 1)
        self.app.table.event_generate("<ButtonRelease-1>", x=90, y=30)
        self.window.update()
        self.assertEqual(self.app.lines[raw].get_linewidth(), 1)

    def test_table_name_columns_truncate_and_expand(self):
        raw = self.app.session.active
        raw.name = "A very long spectrum name that needs truncation"
        self.app.table.column("name", width=120)
        self.app._refresh_table_labels()
        displayed = self.app.table.set(self.app._row_for(raw), "name")
        self.assertTrue(displayed.endswith("..."))
        self.app.table.column("name", width=500)
        self.app._refresh_table_labels()
        self.assertEqual(self.app.table.set(self.app._row_for(raw), "name"), raw.name)

    def test_checkbox_master_and_hidden_preview_preserve_active_and_drawing(self):
        raw = self.app.session.active
        child = self.correct()
        self.app._finish_flash()
        self.click_row(raw, checkbox=True)
        self.assertFalse(raw.visible)
        self.assertIs(self.app.session.active, child)
        self.assertEqual(str(self.app.rename_button["state"]), "normal")
        self.app.session.add_anchor(2, 0)
        old_limits = self.app.axes.get_ylim()
        with patch("ftir_gui.messagebox.askokcancel") as confirm:
            self.click_row(raw, release=False)
            confirm.assert_not_called()
            self.assertEqual(self.app.table.selection(), (self.app._row_for(raw),))
            self.assertEqual(self.app.lines[raw].get_linewidth(), 2.8)
            self.assertTrue(self.app.lines[raw].get_visible())
            preview_min, preview_max = self.app.axes.get_ylim()
            self.assertLessEqual(preview_min, float(np.min(raw.displayed_y)))
            self.assertGreaterEqual(preview_max, float(np.max(raw.displayed_y)))
            self.app.table.event_generate("<ButtonRelease-1>", x=90, y=30)
            self.window.update()
        self.assertIs(self.app.session.active, child)
        self.assertEqual(self.app.table.selection(), (self.app._row_for(child),))
        self.assertFalse(self.app.lines[raw].get_visible())
        self.assertEqual(self.app.lines[raw].get_linewidth(), 1)
        self.app.table.event_generate("<ButtonRelease-1>", x=90, y=30)
        self.window.update()
        self.assertFalse(self.app.lines[raw].get_visible())
        self.assertEqual(self.app.table.selection(), (self.app._row_for(child),))
        self.assertEqual(self.app.lines[child].get_linewidth(), 1)
        assert_allclose(self.app.axes.get_ylim(), old_limits)
        self.assertEqual(len(self.app.session.anchors), 1)
        self.app.master.set(True)
        self.app.toggle_all()
        self.assertTrue(all(s.visible for s in self.app.session.spectra))
        self.assertIs(self.app.session.active, child)
        self.assertEqual(str(self.app.rename_button["state"]), "disabled")
        self.app.master.set(False)
        self.app.toggle_all()
        self.assertTrue(all(not s.visible for s in self.app.session.spectra))
        self.assertEqual(str(self.app.save_button["state"]), "disabled")
        self.assertIs(self.app.session.active, child)

    def test_show_anchor_points_for_checked_spectra(self):
        raw = self.app.session.active
        child = self.correct()
        self.app.show_anchor_points.set(True)
        self.app._refresh()
        self.assertTrue(self.app.anchor_lines[child].get_visible())
        assert_allclose(self.app.anchor_lines[child].get_xdata(), [0, 4])
        assert_allclose(
            self.app.anchor_lines[child].get_ydata(),
            [child.displayed_y[4], child.displayed_y[0]],
        )
        self.click_row(raw, checkbox=True)
        self.assertFalse(self.app.anchor_lines[raw].get_visible())
        self.app._activate(raw)
        self.app._refresh()
        self.assertFalse(self.app.show_anchor_points.get())
        self.assertFalse(self.app.anchor_lines[child].get_visible())

    def test_pan_zoom_and_duplicate_points_do_not_add(self):
        self.app.toolbar.pan()
        self.click_plot(2, 2)
        self.assertEqual(self.app.session.anchors, [])
        self.app.toolbar.pan()
        self.app.add_points_button.invoke()
        self.click_plot(2, 2)
        self.click_plot(2.1, 2)
        self.assertEqual(len(self.app.session.anchors), 1)
        self.assertIn("already exists", self.app.status.get())

    def test_real_tk_drag_and_release_bindings(self):
        widget = self.app.canvas.get_tk_widget()

        def send(sequence, x, y, state=0):
            self.app.canvas.draw()
            px, py = self.app.axes.transData.transform((x, y))
            widget.event_generate(
                sequence, x=round(px), y=round(widget.winfo_height() - py), state=state
            )
            self.window.update()

        send("<ButtonPress-1>", 1, 2)
        self.assertEqual(self.app.session.anchors, [])
        self.assertEqual(self.app.drag_point, (1, 3))
        send("<B1-Motion>", 3, 2, state=256)
        self.assertEqual(self.app.drag_point, (3, 7))
        self.assertEqual(self.app.session.anchors, [])
        send("<ButtonRelease-1>", 3, 2)
        self.assertEqual(self.app.session.anchors, [(3, 7)])
        self.assertIsNone(self.app.drag_free)
        send("<ButtonPress-1>", 1.5, 2.5, state=1)
        self.assertTrue(self.app.drag_free)
        send("<B1-Motion>", 2.5, 3.5, state=257)
        self.assertEqual(len(self.app.session.anchors), 1)
        send("<ButtonRelease-1>", 2.5, 3.5, state=1)
        assert_allclose(self.app.session.anchors[-1], [2.5, 3.5], atol=0.01)
        send("<ButtonPress-1>", 1, 2)
        self.app.table.event_generate("<ButtonRelease-1>", x=90, y=30)
        self.window.update()
        self.assertIsNone(self.app.drag_free)
        self.assertEqual(len(self.app.session.anchors), 2)

    def test_toolbar_toggle_and_navigation_exclusion(self):
        self.app.add_points_button.invoke()
        self.assertFalse(self.app.add_points.get())
        self.click_plot(2, 2)
        self.click_plot(1, 2, key="shift")
        self.assertEqual(self.app.session.anchors, [])
        self.app.session.add_anchor(0, 0)
        self.click_plot(1, 2, button=MouseButton.RIGHT)
        self.assertEqual(self.app.session.anchors, [(0, 0)])
        for navigate in (self.app.toolbar.pan, self.app.toolbar.zoom):
            navigate()
            self.assertTrue(self.app.toolbar.mode)
            self.app.add_points_button.invoke()
            self.assertTrue(self.app.add_points.get())
            self.assertFalse(self.app.toolbar.mode)
            self.plot_event("button_press_event", 2, 2)
            self.assertIsNotNone(self.app.drag_point)
            navigate()
            self.assertFalse(self.app.add_points.get())
            self.assertIsNone(self.app.drag_point)
            self.assertFalse(self.app.cursor_line.get_visible())
            self.plot_event("button_release_event", 2, 2)
            self.assertEqual(self.app.session.anchors, [(0, 0)])
            navigate()

    def test_drag_snapped_preview_interpolation_extrapolation_and_release(self):
        self.click_plot(0.1, 1)
        self.plot_event("button_press_event", 2.1, 6)
        self.assertEqual(self.app.session.anchors, [(0, 0)])
        self.assertEqual(self.app.drag_point, (2, 4))
        self.assertTrue(self.app.cursor_line.get_visible())
        self.assertTrue(self.app.cursor_point.get_visible())
        assert_allclose(self.app.cursor_line.get_xdata(), [2.1, 2.1])
        assert_allclose(self.app.baseline_line.get_ydata(), [0, 4])
        assert_allclose(self.app.extension_line.get_ydata()[-2:], [4, 8])
        self.plot_event("motion_notify_event", 3.1, 1)
        self.assertEqual(self.app.session.anchors, [(0, 0)])
        self.assertEqual(self.app.drag_point, (3, 7))
        assert_allclose(self.app.baseline_line.get_ydata(), [0, 7])
        assert_allclose(self.app.extension_line.get_ydata()[-2:], [7, 28 / 3])
        # Release uses its own coordinates, not the last motion or press.
        self.plot_event("button_release_event", 4, 1)
        self.assertEqual(self.app.session.anchors, [(0, 0), (4, 4)])
        assert_allclose(self.app.baseline_line.get_ydata(), [0, 4])
        self.assertIsNone(self.app.drag_point)
        self.assertIsNone(self.app.drag_free)
        self.assertFalse(self.app.cursor_line.get_visible())
        self.assertFalse(self.app.cursor_point.get_visible())

    def test_shift_drag_preview_and_release_on_offset_spectrum(self):
        child = self.correct()
        self.plot_event("button_press_event", 1.5, 8.5, key="shift")
        self.assertFalse(self.app.cursor_line.get_visible())
        self.assertTrue(self.app.cursor_point.get_visible())
        assert_allclose(self.app.drag_point, [1.5, 8.5 - child.shift])
        self.plot_event("motion_notify_event", 2.25, 9.5)
        self.assertEqual(self.app.session.anchors, [])
        assert_allclose(self.app.drag_point, [2.25, 9.5 - child.shift])
        assert_allclose(self.app.cursor_point.get_ydata(), [9.5])
        self.app._finish_flash()
        self.assertIsNotNone(self.app.drag_point)
        self.plot_event("button_release_event", 2.5, 10.5)
        assert_allclose(self.app.session.anchors, [(2.5, 10.5 - child.shift)])

    def test_cancel_drag_and_duplicate_recovery(self):
        self.click_plot(2, 1)
        self.plot_event("button_press_event", 2.1, 2)
        self.assertIsNone(self.app.drag_point)
        self.assertIn("already exists", self.app.status.get())
        self.plot_event("motion_notify_event", 3, 2)
        self.assertEqual(self.app.drag_point, (3, 7))
        self.plot_event("button_release_event", 3, 2)
        self.assertEqual(len(self.app.session.anchors), 2)
        # Out-of-axes motion removes the transient baseline and release cancels.
        self.plot_event("button_press_event", 1, 2)
        outside = MouseEvent(
            "motion_notify_event", self.app.canvas, -10, -10, button=MouseButton.LEFT
        )
        self.app.canvas.callbacks.process("motion_notify_event", outside)
        self.assertIsNone(self.app.drag_point)
        self.assertFalse(self.app.cursor_point.get_visible())
        outside_release = MouseEvent(
            "button_release_event", self.app.canvas, -10, -10, button=MouseButton.LEFT
        )
        self.app.canvas.callbacks.process("button_release_event", outside_release)
        self.assertIsNone(self.app.drag_free)
        self.assertEqual(len(self.app.session.anchors), 2)
        # Turning off the mode mid-drag cannot commit on a later release.
        self.plot_event("button_press_event", 1, 2)
        self.app.add_points_button.invoke()
        self.plot_event("button_release_event", 1, 2)
        self.assertEqual(len(self.app.session.anchors), 2)
        self.assertIsNone(self.app.drag_free)
        self.app.add_points_button.invoke()
        self.plot_event("button_press_event", 1, 2)
        self.app._cancel_drag()  # Escape handler.
        self.plot_event("button_release_event", 1, 2)
        self.assertEqual(len(self.app.session.anchors), 2)
        self.plot_event("button_press_event", 1, 2)
        self.app.clear()
        self.plot_event("button_release_event", 1, 2)
        self.assertEqual(self.app.session.anchors, [])

    def test_offset_chain_rename_and_delete_parent(self):
        raw = self.app.session.active
        first = self.correct()
        second = self.correct()
        self.app._finish_flash()
        self.click_row(first)
        self.app.offset.set("-1.54")
        self.app.change_offset()
        self.assertEqual(first.offset, -1.54)
        self.assertEqual(self.app.offset.get(), "-1.5400")
        self.assertEqual(float(self.app.spinner["increment"]), 0.05)
        assert_allclose(self.app.lines[second].get_ydata(), second.displayed_y)
        self.assertAlmostEqual(np.min(second.displayed_y), np.max(first.displayed_y))
        with patch("ftir_gui.messagebox.showerror") as error:
            self.app.offset.set("nan")
            self.app.change_offset()
        error.assert_called_once()
        self.assertEqual(first.offset, -1.54)
        self.app.offset.set("1.5")
        self.app.change_offset()
        self.assertEqual(first.offset, 1.5)
        plot_min, plot_max = self.app.axes.get_ylim()
        self.assertLessEqual(plot_min, float(np.min(raw.displayed_y)))
        self.assertGreaterEqual(plot_max, float(np.max(second.displayed_y)))
        # Select only the raw spectrum for bulk operations, without changing active.
        self.click_row(first, checkbox=True)
        self.click_row(second, checkbox=True)
        self.assertEqual(self.app.checked(), [raw])
        with patch("ftir_gui.simpledialog.askstring", return_value="renamed"):
            self.app.rename_button.invoke()
        self.assertEqual(raw.name, "renamed")
        self.assertIs(self.app.session.active, first)
        previous_shift = second.shift
        with patch("ftir_gui.messagebox.askokcancel", return_value=True) as confirm:
            self.app.delete_button.invoke()
        confirm.assert_called_once()
        self.assertNotIn(raw, self.app.session.spectra)
        self.assertIs(first.parent, raw)
        self.assertEqual(previous_shift, second.shift)
        self.assertIs(self.app.session.active, first)

    def test_delete_active_cancel_and_delete_all(self):
        self.app.session.add_anchor(2, 0)
        with patch("ftir_gui.messagebox.askokcancel", return_value=False):
            self.app.delete()
        self.assertEqual(len(self.app.session.spectra), 1)
        with patch("ftir_gui.messagebox.askokcancel", return_value=True):
            self.app.delete()
        self.assertEqual(self.app.session.spectra, [])
        self.assertIsNone(self.app.session.active)
        self.assertEqual(self.app.table.get_children(), ())
        self.assertEqual(self.app.session.anchors, [])

    def test_open_files_defaults_to_repository_folder(self):
        with patch("ftir_gui.filedialog.askopenfilenames", return_value=[]) as dialog:
            self.app.open_files()
        self.assertEqual(dialog.call_args.kwargs["initialdir"], ROOT)

    def test_exports_and_duplicate_names(self):
        raw = self.app.session.active
        child = self.correct()
        self.app._finish_flash()
        child.name = raw.name
        with patch("ftir_gui.filedialog.askdirectory", return_value=self.temp.name), patch(
            "ftir_gui.messagebox.askokcancel", return_value=True
        ):
            self.app._export_spectra([raw, child], with_offset=False)
        assert_allclose(load_spectrum(Path(self.temp.name) / "raw_2.csv").y, child.y)
        output = Path(self.temp.name) / "single.csv"
        with patch("ftir_gui.filedialog.asksaveasfilename", return_value=str(output)):
            self.app._export_spectra([child], with_offset=True)
        assert_allclose(load_spectrum(output).y, child.displayed_y)
        for extension, signature in [("png", b"\x89PNG"), ("pdf", b"%PDF"), ("svg", b"<?xml")]:
            output = Path(self.temp.name) / f"image.{extension}"
            self.app.export_image(output, [child])
            self.assertTrue(output.read_bytes().startswith(signature))
            self.assertGreater(output.stat().st_size, 1000)
        self.assertEqual(self.app._safe_filename('CON'), "_CON")
        self.assertEqual(self.app._safe_filename('test:bad/name'), "test_bad_name")

    def test_save_popup_buttons(self):
        for label, expected in [("Save with offset", True), ("Save without offset", False)]:
            def choose():
                for window in self.window.winfo_children():
                    if isinstance(window, tk.Toplevel):
                        for widget in window.winfo_children():
                            if widget.winfo_class() == "TButton" and widget["text"] == label:
                                widget.invoke()
                                return
                self.fail("Save dialog button missing")

            self.window.after(30, choose)
            with patch.object(self.app, "_export_spectra") as export:
                self.app.save_spectra()
            export.assert_called_once_with(self.app.checked(), expected)

    def test_actual_sample_end_to_end(self):
        self.app.open_path(next(ROOT.glob("SID*.csv")))
        raw = self.app.session.active
        for x in [4000, 3400, 3000, 2400, 2200, 2000, 1650, 1500, 1300, 850, 650]:
            self.app.session.add_anchor(x, 0)
        indexes = [int(np.argmin(abs(raw.x - x))) for x, _ in self.app.session.anchors]
        self.app.apply()
        child = self.app.session.active
        self.assertEqual(len(child.y), 6950)
        assert_allclose(child.y[indexes], 0, atol=1e-12)
        self.assertTrue(np.all(np.isfinite(child.displayed_y)))
        self.assertAlmostEqual(np.min(child.displayed_y), np.max(raw.displayed_y))


if __name__ == "__main__":
    unittest.main()
