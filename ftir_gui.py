"""Interactive point-to-point FTIR baseline editor."""

from __future__ import annotations

import argparse
import re
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk

import numpy as np
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from spectra_model import Spectrum, SpectraSession, linear_baseline, load_spectrum, save_spectrum


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, event: tk.Event | None = None) -> None:
        if self.window is not None:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 6
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.window.geometry(f"+{x}+{y}")
        tk.Label(
            self.window, text=self.text, justify=tk.LEFT, relief=tk.SOLID, borderwidth=1,
            background="#ffffe1", padx=5, pady=3,
        ).pack()

    def hide(self, event: tk.Event | None = None) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None


class BaselineToolbar(NavigationToolbar2Tk):
    def __init__(self, canvas, window, on_navigation: Callable[[], None]) -> None:
        self.on_navigation = on_navigation
        super().__init__(canvas, window, pack_toolbar=False)

    def pan(self, *args) -> None:
        super().pan(*args)
        if self.mode:
            self.on_navigation()

    def zoom(self, *args) -> None:
        super().zoom(*args)
        if self.mode:
            self.on_navigation()


class BaselineApp:
    def __init__(self, root: tk.Tk, paths: list[Path] | None = None) -> None:
        self.root = root
        self.root.title("FTIR - Linear point-to-point baseline")
        self.root.geometry("1380x820")
        self.root.minsize(1000, 620)
        self.session = SpectraSession()
        self.lines: dict[Spectrum, Line2D] = {}
        self.rows: dict[str, Spectrum] = {}
        self.row_count = 0
        self.preview: Spectrum | None = None
        self.preview_limits: tuple[tuple[float, float], tuple[float, float]] | None = None
        self.pressed: Spectrum | None = None
        self.flash_job: str | None = None
        self.anchor_lines: dict[Spectrum, Line2D] = {}
        self._blit_background = None
        self._table_tooltip: tk.Toplevel | None = None
        self._table_resize_job: str | None = None
        self._pending_row: tuple[Spectrum, Spectrum | None] | None = None
        self.shift_held = False
        self.add_points = tk.BooleanVar(value=True)
        self.show_anchor_points = tk.BooleanVar(value=False)
        self.drag_free: bool | None = None
        self.drag_point: tuple[float, float] | None = None
        self.master = tk.BooleanVar(value=False)
        self.offset = tk.StringVar(value="0.0000")
        self.status = tk.StringVar(value="Open a CSV spectrum to begin.")
        self._build_ui()
        self.root.bind_all("<ButtonRelease-1>", self._release_row, add="+")
        self.root.bind_all("<ButtonRelease-1>", self._release_outside_plot, add="+")
        self.root.bind("<Escape>", lambda event: self._cancel_drag(), add="+")
        self.root.bind_all("<KeyPress-Shift_L>", self._shift_down, add="+")
        self.root.bind_all("<KeyPress-Shift_R>", self._shift_down, add="+")
        self.root.bind_all("<KeyRelease-Shift_L>", self._shift_up, add="+")
        self.root.bind_all("<KeyRelease-Shift_R>", self._shift_up, add="+")
        self.root.bind("<FocusOut>", self._shift_up, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        for path in paths or []:
            self.open_path(path)
        self._sync_controls()

    def _build_ui(self) -> None:
        panes = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)
        sidebar = ttk.Frame(panes, padding=10, width=350)
        chart = ttk.Frame(panes)
        panes.add(sidebar, weight=0)
        panes.add(chart, weight=1)
        ttk.Button(sidebar, text="Open CSV...", command=self.open_files).pack(fill=tk.X)
        ttk.Label(sidebar, text="Spectra", font=("", 12, "bold")).pack(anchor=tk.W, pady=(14, 4))
        ttk.Style(self.root).configure("Large.TCheckbutton", padding=(4, 4))
        selection_header = ttk.Frame(sidebar)
        selection_header.pack(fill=tk.X, pady=(0, 2))
        self.master_button = ttk.Checkbutton(
            selection_header, style="Large.TCheckbutton", variable=self.master, command=self.toggle_all
        )
        self.master_button.pack(side=tk.LEFT, anchor=tk.W)
        selection_buttons = ttk.Frame(selection_header)
        selection_buttons.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.delete_button = ttk.Button(selection_buttons, text="Delete", command=self.delete)
        self.delete_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.save_button = ttk.Button(selection_buttons, text="Save spectra", command=self.save_spectra)
        self.save_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self.image_button = ttk.Button(selection_buttons, text="Save image", command=self.save_image)
        self.image_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        table_frame = ttk.Frame(sidebar)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.table = ttk.Treeview(
            table_frame, columns=("shown", "name", "parent"), show="headings", selectmode="browse",
            height=12,
        )
        self.table.heading("shown", text="Show")
        self.table.heading("name", text="Spectrum (click to activate)")
        self.table.heading("parent", text="Parent spectrum")
        self.table.column("shown", width=48, minwidth=48, stretch=False, anchor=tk.CENTER)
        self.table.column("name", width=190, minwidth=120, stretch=True)
        self.table.column("parent", width=150, minwidth=100, stretch=True)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.table.bind("<ButtonPress-1>", self._press_row)
        self.table.bind("<ButtonRelease-1>", self._release_row, add="+")
        self.table.bind("<Motion>", self._table_motion, add="+")
        self.table.bind("<Leave>", self._hide_table_tooltip, add="+")
        self.table.bind("<Configure>", self._table_configure, add="+")
        self.table.bind("<KeyPress>", lambda event: "break")
        self.table.bind("<Double-Button-1>", self._double_row)
        self.table.bind("<<TreeviewSelect>>", lambda event: self._sync_controls())
        self.rename_button = ttk.Button(sidebar, text="Rename checked spectrum...", command=self.rename)
        self.rename_button.pack(fill=tk.X, pady=2)
        ttk.Label(
            sidebar,
            text="Enable 'Add baseline points' in toolbar.\n"
                 "Left drag: snap to active spectrum\n"
                 "Shift + left drag: use cursor X,Y\n"
                 "Release: place the previewed point\n"
                 "Right click: undo last point\n\n"
                 "Checked = visible and selected for operations.\n"
                 "Highlighted = active for baseline and offset.\n"
                 "Use Show anchor points to display saved correction points.\n"
                 "End segments extend beyond outer anchors.",
            justify=tk.LEFT, wraplength=320,
        ).pack(anchor=tk.W, pady=(12, 0))
        self.figure = Figure(figsize=(10, 7), dpi=100, layout="constrained")
        self.axes = self.figure.add_subplot()
        self.axes.set_xlabel("Wavenumbers [1/cm]")
        self.axes.set_ylabel("Absorbance")
        self.axes.invert_xaxis()
        self.axes.grid(True, alpha=0.25)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart)
        self.toolbar = BaselineToolbar(self.canvas, chart, self._navigation_started)
        self.add_points_button = tk.Checkbutton(
            self.toolbar, text="✎", variable=self.add_points, indicatoron=False,
            command=self.toggle_add_points, padx=5, pady=2, width=2,
            font=("Segoe UI Symbol", 12),
        )
        self.add_points_button.pack(side=tk.LEFT, padx=5)
        ToolTip(
            self.add_points_button,
            "Add baseline points: drag to place anchors; hold Shift for free X,Y.",
        )
        self.apply_button = ttk.Button(self.toolbar, text="Apply baseline", command=self.apply)
        self.apply_button.pack(side=tk.LEFT, padx=2)
        self.anchor_points_button = tk.Checkbutton(
            self.toolbar, text="Show anchors", variable=self.show_anchor_points,
            indicatoron=False, command=self._refresh, padx=6, pady=2,
        )
        self.anchor_points_button.pack(side=tk.LEFT, padx=2)
        ttk.Label(self.toolbar, text="Offset spectrum (absorbance):").pack(side=tk.LEFT, padx=(10, 2))
        self.spinner = ttk.Spinbox(
            self.toolbar, from_=-1e100, to=1e100, increment=0.05, textvariable=self.offset,
            command=self.change_offset, width=12,
        )
        self.spinner.pack(side=tk.LEFT, padx=2)
        self.spinner.bind("<Return>", self.change_offset)
        self.spinner.bind("<FocusOut>", self.change_offset)
        self.clear_button = ttk.Button(self.toolbar, text="Clear anchors", command=self.clear)
        self.clear_button.pack(side=tk.LEFT, padx=(8, 5))
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        (self.baseline_line,) = self.axes.plot(
            [], [], color="#222222", linewidth=1.6, marker="o", markersize=5,
            label="_baseline", zorder=10,
        )
        (self.extension_line,) = self.axes.plot(
            [], [], color="#666666", linewidth=1, linestyle="--", label="_extension", zorder=9
        )
        self.cursor_line = self.axes.axvline(
            0, color="#888888", linewidth=1, linestyle=":", visible=False, label="_cursor"
        )
        (self.cursor_point,) = self.axes.plot(
            [], [], marker="o", markersize=8, markerfacecolor="none",
            markeredgecolor="#222222", linestyle="none", visible=False, zorder=11,
            label="_cursor_point",
        )
        self.canvas.mpl_connect("button_press_event", self.plot_click)
        self.canvas.mpl_connect("motion_notify_event", self.plot_motion)
        self.canvas.mpl_connect("button_release_event", self.plot_release)
        self.canvas.mpl_connect("draw_event", self._cache_blit_background)
        for artist in (
            self.baseline_line, self.extension_line, self.cursor_line, self.cursor_point
        ):
            artist.set_animated(True)
        ttk.Label(self.root, textvariable=self.status, padding=(10, 5), wraplength=1250).pack(fill=tk.X)

    def checked(self) -> list[Spectrum]:
        return [spectrum for spectrum in self.session.spectra if spectrum.visible]

    def _row_for(self, spectrum: Spectrum) -> str:
        return next(row for row, item in self.rows.items() if item is spectrum)

    def _truncate_cell(self, value: str, column: str) -> str:
        width = int(self.table.column(column, "width"))
        if tkfont.nametofont("TkDefaultFont").measure(value) <= width:
            return value
        suffix = "..."
        while value and tkfont.nametofont("TkDefaultFont").measure(value + suffix) > width:
            value = value[:-1]
        return value + suffix

    def _table_configure(self, event: tk.Event | None = None) -> None:
        if self._table_resize_job is None:
            self._table_resize_job = self.root.after_idle(self._refresh_table_labels)

    def _refresh_table_labels(self) -> None:
        self._table_resize_job = None
        for spectrum in self.session.spectra:
            row = self._row_for(spectrum)
            parent_name = spectrum.parent.name if spectrum.parent is not None else ""
            self.table.set(row, "name", self._truncate_cell(spectrum.name, "name"))
            self.table.set(row, "parent", self._truncate_cell(parent_name, "parent"))

    def _hide_table_tooltip(self, event: tk.Event | None = None) -> None:
        if self._table_tooltip is not None:
            self._table_tooltip.destroy()
            self._table_tooltip = None

    def _table_motion(self, event: tk.Event) -> None:
        row = self.table.identify_row(event.y)
        column = self.table.identify_column(event.x)
        if row not in self.rows or column not in ("#2", "#3"):
            self._hide_table_tooltip()
            return
        spectrum = self.rows[row]
        full_name = spectrum.name if column == "#2" else (
            spectrum.parent.name if spectrum.parent is not None else ""
        )
        if not full_name:
            self._hide_table_tooltip()
            return
        self._hide_table_tooltip()
        self._table_tooltip = tk.Toplevel(self.table)
        self._table_tooltip.overrideredirect(True)
        self._table_tooltip.attributes("-topmost", True)
        self._table_tooltip.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
        tk.Label(
            self._table_tooltip, text=full_name, relief=tk.SOLID, borderwidth=1,
            background="#ffffe1", padx=5, pady=3,
        ).pack()

    def _sync_controls(self) -> None:
        checked = self.checked()
        for button in (self.delete_button, self.save_button, self.image_button):
            button.configure(state=tk.NORMAL if checked else tk.DISABLED)
        self.rename_button.configure(state=tk.NORMAL if len(checked) == 1 else tk.DISABLED)
        active = self.session.active
        self.spinner.configure(state=tk.NORMAL if active is not None else tk.DISABLED)
        self.clear_button.configure(state=tk.NORMAL if self.session.anchors else tk.DISABLED)
        self.apply_button.configure(
            state=tk.NORMAL if len(self.session.anchors) >= 2 else tk.DISABLED
        )
        self.master.set(bool(checked) and len(checked) == len(self.session.spectra))
        self.master_button.state(
            ["alternate"] if checked and len(checked) < len(self.session.spectra) else ["!alternate"]
        )

    def _select_active_row(self) -> None:
        active = self.preview or self.session.active
        if active is not None:
            row = self._row_for(active)
            self.table.selection_set(row)
            self.table.focus(row)
        else:
            self.table.selection_remove(self.table.selection())

    def _refresh(self, fit: bool = False) -> None:
        self._cancel_drag(redraw=False)
        for spectrum, line in self.lines.items():
            line.set_ydata(spectrum.displayed_y)
            line.set_visible(spectrum.visible or self.preview is spectrum)
            line.set_linewidth(2.8 if self.pressed is spectrum else 1.0)
            anchor_line = self.anchor_lines[spectrum]
            anchor_x = [point[0] for point in spectrum.anchors]
            anchor_y = [
                spectrum.displayed_y[spectrum.nearest_index(x)]
                for x in anchor_x
            ]
            anchor_line.set_data(anchor_x, anchor_y)
            anchor_line.set_visible(
                self.show_anchor_points.get()
                and spectrum is self.session.active
                and spectrum.visible
            )
            self.table.set(self._row_for(spectrum), "shown", "\u2611" if spectrum.visible else "\u2610")
            line.set_label(spectrum.name)
        self._refresh_table_labels()
        self._draw_baseline()
        handles = [line for spectrum, line in self.lines.items() if spectrum.visible]
        legend = self.axes.get_legend()
        if legend:
            legend.remove()
        if handles:
            self.axes.legend(handles=handles, loc="best", fontsize=8)
        if fit:
            # Baseline extensions must not dominate the spectrum's initial view.
            self.baseline_line.set_visible(False)
            self.extension_line.set_visible(False)
            self.axes.relim(visible_only=True)
            self.axes.set_autoscale_on(True)
            self.axes.autoscale_view()
            self._draw_baseline()
        self._select_active_row()
        self._sync_controls()
        self.canvas.draw_idle()

    def _cache_blit_background(self, event: object | None = None) -> None:
        self._blit_background = self.canvas.copy_from_bbox(self.axes.bbox)
        self._blit_interactive()

    def _blit_interactive(self) -> None:
        if self._blit_background is None:
            self.canvas.draw()
            return
        self.canvas.restore_region(self._blit_background)
        for artist in (
            self.baseline_line, self.extension_line, self.cursor_line, self.cursor_point
        ):
            self.axes.draw_artist(artist)
        self.canvas.blit(self.axes.bbox)

    def _draw_baseline(self) -> None:
        active = self.session.active
        points = sorted(
            self.session.anchors + ([self.drag_point] if self.drag_point is not None else [])
        )
        visible = bool(points) and active is not None and active.visible
        self.baseline_line.set_visible(visible)
        self.extension_line.set_visible(visible and len(points) >= 2)
        if not visible or active is None:
            return
        self.baseline_line.set_data(
            [point[0] for point in points],
            [point[1] + active.display_offset_at(point[0]) for point in points],
        )
        if len(points) >= 2:
            first, second = points[:2]
            penultimate, last = points[-2:]
            left_x = float(np.min(active.x))
            right_x = float(np.max(active.x))
            left_y = first[1] + (left_x - first[0]) * (second[1] - first[1]) / (second[0] - first[0])
            right_y = last[1] + (right_x - last[0]) * (last[1] - penultimate[1]) / (
                last[0] - penultimate[0]
            )
            endpoints = np.asarray(
                [np.min(active.x), points[0][0], np.nan, points[-1][0], np.max(active.x)]
            )
            extension_values = [
                left_y + active.display_offset_at(left_x),
                first[1] + active.display_offset_at(first[0]),
                np.nan,
                last[1] + active.display_offset_at(last[0]),
                right_y + active.display_offset_at(right_x),
            ]
            self.extension_line.set_data(endpoints, extension_values)

    def _confirm_discard(self) -> bool:
        return not self.session.anchors or messagebox.askokcancel(
            "Discard unfinished baseline?",
            "The current baseline drawing will be discarded.",
            parent=self.root,
        )

    def _cancel_flash(self) -> None:
        if self.flash_job is not None:
            self.root.after_cancel(self.flash_job)
            self.flash_job = None
        self.pressed = None

    def _activate(self, spectrum: Spectrum) -> bool:
        if spectrum is not self.session.active:
            if not self._confirm_discard():
                return False
            self.session.anchors.clear()
            self.session.active = spectrum
            self.show_anchor_points.set(False)
        self.offset.set(f"{spectrum.offset:.4f}" if spectrum.parent else "0.0000")
        self.status.set(
            f"Active: {spectrum.name}. Enable 'Add baseline points' to draw a baseline."
        )
        return True

    def _double_row(self, event: tk.Event) -> str:
        return self._press_row(event)

    def _highlight_spectrum(self, spectrum: Spectrum) -> None:
        self.pressed = spectrum
        row = self._row_for(spectrum)
        self.table.selection_set(row)
        self.table.focus(row)
        for item, line in self.lines.items():
            line.set_linewidth(2.8 if item is spectrum else 1.0)

    def _restore_active_highlight(self, spectrum: Spectrum | None) -> None:
        if spectrum is None:
            self.table.selection_remove(self.table.selection())
            self.pressed = None
            return
        self._highlight_spectrum(spectrum)
        self.canvas.draw_idle()
        self.flash_job = self.root.after(250, self._finish_flash)

    def _press_row(self, event: tk.Event) -> str:
        row = self.table.identify_row(event.y)
        column = self.table.identify_column(event.x)
        if row not in self.rows:
            return ""
        spectrum = self.rows[row]
        if column == "#1":
            self._pending_row = None
            spectrum.visible = not spectrum.visible
            self._refresh(fit=True)
            return "break"
        self._cancel_flash()
        previous = self.session.active
        self._pending_row = (spectrum, previous)
        self._highlight_spectrum(spectrum)
        if not spectrum.visible:
            self.preview_limits = (self.axes.get_xlim(), self.axes.get_ylim())
            self.preview = spectrum
            self._refresh(fit=True)
        else:
            self.canvas.draw_idle()
        return "break"

    def _release_row(self, event: tk.Event | None = None) -> None:
        pending = self._pending_row
        self._pending_row = None
        if pending is None and self.pressed is None and self.preview is None:
            return
        # A newly created curve's timed emphasis is independent of mouse release.
        if self.flash_job is not None:
            return
        if pending is not None:
            spectrum, previous = pending
            if spectrum.visible and spectrum is not previous:
                if self._activate(spectrum):
                    self._refresh()
                    self.pressed = None
                    for line in self.lines.values():
                        line.set_linewidth(1.0)
                    self.canvas.draw_idle()
                else:
                    self._restore_active_highlight(previous)
                return
        self.preview = None
        self.pressed = None
        if self.preview_limits is not None:
            self.axes.set_xlim(self.preview_limits[0])
            self.axes.set_ylim(self.preview_limits[1])
            self.preview_limits = None
        self._refresh()

    def toggle_all(self) -> None:
        visible = self.master.get()
        for spectrum in self.session.spectra:
            spectrum.visible = visible
        self._refresh(fit=True)

    def _shift_down(self, event: tk.Event) -> None:
        self.shift_held = True

    def _shift_up(self, event: tk.Event) -> None:
        self.shift_held = False

    def _navigation_started(self) -> None:
        self.add_points.set(False)
        self._cancel_drag()
        self.status.set("Baseline point controls disabled while navigating.")

    def toggle_add_points(self) -> None:
        self._cancel_drag()
        if self.add_points.get():
            if self.toolbar.mode == "pan/zoom":
                self.toolbar.pan()
            elif self.toolbar.mode == "zoom rect":
                self.toolbar.zoom()
            self.status.set(
                "Baseline point controls enabled. Drag to preview; release to place. "
                "Hold Shift when starting a drag for cursor X,Y; right click to undo."
            )
        else:
            self.status.set("Baseline point controls disabled. Existing points are preserved.")

    def _cancel_drag(self, redraw: bool = True) -> None:
        self.drag_free = None
        self.drag_point = None
        self.cursor_line.set_visible(False)
        self.cursor_point.set_visible(False)
        if redraw:
            self._draw_baseline()
            self._blit_interactive()

    def _release_outside_plot(self, event: tk.Event) -> None:
        # Canvas release handlers run before this Tk "all" binding.
        if self.drag_free is not None:
            self._cancel_drag()
            self.status.set("Point placement cancelled: release inside the plot to place it.")

    def plot_click(self, event: MouseEvent) -> None:
        if not self.add_points.get() or event.inaxes is not self.axes or self.toolbar.mode:
            return
        if event.button == MouseButton.RIGHT:
            self._cancel_drag()
            if self.session.anchors:
                self.session.anchors.pop()
                self.status.set(f"Undid last point. {len(self.session.anchors)} point(s) remain.")
                self._refresh()
            return
        if event.button != MouseButton.LEFT or event.xdata is None or event.ydata is None:
            return
        active = self.session.active
        if active is None or not active.visible:
            self.status.set("Show and activate a spectrum before drawing a baseline.")
            return
        self.drag_free = self.shift_held or "shift" in event.modifiers or (
            event.key is not None and "shift" in event.key.lower()
        )
        self._update_drag(event)

    def _update_drag(self, event: MouseEvent) -> None:
        self.drag_point = None
        self.cursor_line.set_visible(False)
        self.cursor_point.set_visible(False)
        if event.inaxes is not self.axes or event.xdata is None or event.ydata is None:
            self.status.set("Release outside the plot to cancel this point, or drag back inside.")
        else:
            self.cursor_line.set_xdata([event.xdata, event.xdata])
            self.cursor_line.set_visible(self.drag_free is False)
            try:
                self.drag_point = self.session.resolve_anchor(
                    event.xdata, event.ydata, free=bool(self.drag_free)
                )
            except ValueError as error:
                self.status.set(str(error))
            else:
                x, y = self.drag_point
                active = self.session.active
                if active is not None:
                    display_y = y + active.display_offset_at(x)
                    self.cursor_point.set_data([x], [display_y])
                    self.cursor_point.set_visible(True)
                    self.status.set(
                        f"Preview: X={x:.6g}, Y={display_y:.6g}. "
                        "Drag to adjust; release to place; Esc to cancel."
                    )
        self._draw_baseline()
        self._blit_interactive()

    def plot_motion(self, event: MouseEvent) -> None:
        if self.drag_free is None:
            return
        if not self.add_points.get() or self.toolbar.mode:
            self._cancel_drag()
            return
        self._update_drag(event)

    def plot_release(self, event: MouseEvent) -> None:
        if self.drag_free is None or event.button != MouseButton.LEFT:
            return
        free = self.drag_free
        self._cancel_drag(redraw=False)
        if (
            not self.add_points.get() or self.toolbar.mode or event.inaxes is not self.axes
            or event.xdata is None or event.ydata is None
        ):
            self.status.set("Point placement cancelled.")
            self._draw_baseline()
            self._blit_interactive()
            return
        try:
            x, y = self.session.add_anchor(event.xdata, event.ydata, free=free)
        except ValueError as error:
            self.status.set(str(error))
            self.root.bell()
            self._draw_baseline()
            self._blit_interactive()
            return
        active = self.session.active
        if active is None:
            return
        display_y = y + active.display_offset_at(x)
        self.status.set(
            f"{len(self.session.anchors)} point(s): X={x:.6g}, Y={display_y:.6g}. "
            "Right click to undo; Apply subtracts the full-range piecewise-linear baseline."
        )
        self._refresh()

    def clear(self) -> None:
        self.session.anchors.clear()
        self.status.set("Baseline drawing cleared.")
        self._refresh()

    def apply(self) -> None:
        try:
            spectrum = self.session.apply()
        except ValueError as error:
            messagebox.showerror("Cannot apply baseline", str(error), parent=self.root)
            return
        self._insert(spectrum)
        self._cancel_flash()
        self.pressed = spectrum
        self.show_anchor_points.set(False)
        self.offset.set(f"{spectrum.offset:.4f}")
        self._refresh(fit=True)
        self.table.see(self._row_for(spectrum))
        self.flash_job = self.root.after(550, self._finish_flash)
        self.status.set(f"Created {spectrum.name}. Offset: {spectrum.offset:g} absorbance units.")

    def _finish_flash(self) -> None:
        self._cancel_flash()
        for line in self.lines.values():
            line.set_linewidth(1.0)
        self.canvas.draw_idle()

    def _insert(self, spectrum: Spectrum) -> None:
        self.row_count += 1
        row = f"spectrum-{self.row_count}"
        self.rows[row] = spectrum
        self.table.insert("", tk.END, iid=row, values=("\u2611", spectrum.name))
        (line,) = self.axes.plot(spectrum.x, spectrum.displayed_y, linewidth=1, label=spectrum.name)
        self.lines[spectrum] = line
        (anchor_line,) = self.axes.plot(
            [], [], linestyle="none", marker="o", markersize=6,
            markerfacecolor="none", markeredgecolor=line.get_color(),
            label="_anchor_points", zorder=12,
        )
        self.anchor_lines[spectrum] = anchor_line

    def change_offset(self, event: tk.Event | None = None) -> None:
        active = self.session.active
        if active is None:
            return
        try:
            value = float(self.offset.get())
            if not np.isfinite(value):
                raise ValueError("Offset must be a finite number.")
        except ValueError:
            messagebox.showerror(
                "Invalid offset", "Enter a finite absorbance offset.", parent=self.root
            )
            self.offset.set(f"{active.offset:.4f}")
            return
        value = round(value, 4)
        if value == active.offset:
            return
        active.offset = value
        self.status.set(
            f"Offset for {active.name}: {value:g} absorbance units (descendants follow their parents)."
        )
        self._refresh(fit=True)

    def open_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.root, title="Open FTIR spectra",
            initialdir=Path(__file__).resolve().parent,
            filetypes=[("CSV spectra", "*.csv"), ("All files", "*.*")],
        )
        for filename in paths:
            if not self.open_path(Path(filename)):
                break

    def open_path(self, path: Path) -> bool:
        try:
            spectrum = load_spectrum(path)
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror("Cannot open spectrum", f"{path.name}\n\n{error}", parent=self.root)
            return False
        if not self._confirm_discard():
            return False
        self._cancel_flash()
        self.session.add(spectrum)
        self.show_anchor_points.set(False)
        self.offset.set("0.0000")
        self._insert(spectrum)
        self._refresh(fit=True)
        self.table.see(self._row_for(spectrum))
        self.status.set(f"Loaded {path.name}: {len(spectrum.x):,} samples.")
        return True

    def delete(self) -> None:
        selected = self.checked()
        if not selected:
            return
        names = ", ".join(spectrum.name for spectrum in selected)
        if not messagebox.askokcancel(
            "Delete spectra?",
            f"Delete the selected spectrum/spectra?\n\n{names}",
            parent=self.root,
        ):
            return
        if self.session.active in selected and not self._confirm_discard():
            return
        self._cancel_flash()
        self.preview = None
        for spectrum in selected:
            self.lines.pop(spectrum).remove()
            self.anchor_lines.pop(spectrum).remove()
            row = self._row_for(spectrum)
            self.table.delete(row)
            del self.rows[row]
            self.session.spectra.remove(spectrum)
        if self.session.active in selected:
            self.session.active = self.session.spectra[0] if self.session.spectra else None
            self.session.anchors.clear()
            self.show_anchor_points.set(False)
        active = self.session.active
        self.offset.set(f"{active.offset:.4f}" if active and active.parent else "0.0000")
        self._refresh(fit=True)
        self.status.set(
            f"Deleted {len(selected)} spectrum/spectra. Surviving children retain their parent reference."
        )

    def rename(self) -> None:
        selected = self.checked()
        if len(selected) != 1:
            return
        spectrum = selected[0]
        name = simpledialog.askstring(
            "Rename spectrum", "Spectrum name:", initialvalue=spectrum.name, parent=self.root
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showerror("Invalid name", "The spectrum name cannot be empty.", parent=self.root)
            return
        spectrum.name = name
        self._refresh()

    def save_spectra(self) -> None:
        selected = self.checked()
        if not selected:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Save spectra")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        ttk.Label(dialog, text="Save checked spectra as two-column CSV files.", padding=15).pack()

        def choose(with_offset: bool) -> None:
            dialog.destroy()
            self._export_spectra(selected, with_offset)

        ttk.Button(dialog, text="Save with offset", command=lambda: choose(True)).pack(
            fill=tk.X, padx=15, pady=4
        )
        ttk.Button(dialog, text="Save without offset", command=lambda: choose(False)).pack(
            fill=tk.X, padx=15, pady=4
        )
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(fill=tk.X, padx=15, pady=(4, 15))
        dialog.grab_set()
        dialog.wait_window()

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
        if not name:
            name = "spectrum"
        if name.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)),
        }:
            name = "_" + name
        return name[:160]

    def _export_spectra(self, selected: list[Spectrum], with_offset: bool) -> None:
        targets: list[tuple[Spectrum, Path]] = []
        if len(selected) == 1:
            filename = filedialog.asksaveasfilename(
                parent=self.root, title="Save spectrum", defaultextension=".csv",
                initialfile=self._safe_filename(selected[0].name) + ".csv",
                filetypes=[("CSV spectrum", "*.csv")],
            )
            if not filename:
                return
            targets.append((selected[0], Path(filename)))
        else:
            directory = filedialog.askdirectory(parent=self.root, title="Save checked spectra in folder")
            if not directory:
                return
            used: set[str] = set()
            for spectrum in selected:
                stem = self._safe_filename(spectrum.name)
                name = stem + ".csv"
                index = 2
                while name.casefold() in used:
                    name = f"{stem}_{index}.csv"
                    index += 1
                used.add(name.casefold())
                targets.append((spectrum, Path(directory) / name))
            existing = [path.name for _, path in targets if path.exists()]
            if existing and not messagebox.askokcancel(
                "Overwrite existing files?",
                "These files already exist:\n" + "\n".join(existing) + "\n\nOverwrite them?",
                parent=self.root,
            ):
                return
        saved = 0
        try:
            for spectrum, path in targets:
                save_spectrum(spectrum, path, with_offset)
                saved += 1
        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Export failed", f"Saved {saved} of {len(targets)} file(s).\n\n{error}", parent=self.root
            )
            return
        self.status.set(
            f"Saved {saved} spectrum/spectra {'with' if with_offset else 'without cumulative'} offset."
        )

    def save_image(self) -> None:
        selected = self.checked()
        if not selected:
            return
        filename = filedialog.asksaveasfilename(
            parent=self.root, title="Save checked spectra image", defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("PDF image", "*.pdf"), ("SVG image", "*.svg")],
        )
        if not filename:
            return
        try:
            self.export_image(Path(filename), selected)
        except (OSError, ValueError) as error:
            messagebox.showerror("Cannot save image", str(error), parent=self.root)
            return
        self.status.set(f"Saved image: {filename}")

    def export_image(self, path: Path, selected: list[Spectrum]) -> None:
        # Render separately so export never captures previews, anchors, or bold-click state.
        figure = Figure(figsize=(11, 7), dpi=150, layout="constrained")
        axes = figure.add_subplot()
        for spectrum in selected:
            axes.plot(
                spectrum.x, spectrum.displayed_y, label=spectrum.name,
                color=self.lines[spectrum].get_color(), linewidth=1,
            )
        axes.set_xlabel(self.axes.get_xlabel())
        axes.set_ylabel(self.axes.get_ylabel())
        axes.set_xlim(self.axes.get_xlim())
        axes.set_ylim(self.axes.get_ylim())
        axes.grid(True, alpha=0.25)
        axes.legend(fontsize=8, loc="best")
        figure.savefig(path)
        figure.clear()

    def close(self) -> None:
        if self.session.anchors and not messagebox.askokcancel(
            "Close editor?", "Discard the unfinished baseline and close?\n"
            "Export any corrected spectra you want to keep before closing.", parent=self.root
        ):
            return
        self._cancel_flash()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="Optional input CSV files")
    args = parser.parse_args()
    root = tk.Tk()
    paths = args.files
    if not paths:
        paths = sorted(Path(__file__).parent.glob("*.csv"))
    BaselineApp(root, paths)
    root.mainloop()


if __name__ == "__main__":
    main()
