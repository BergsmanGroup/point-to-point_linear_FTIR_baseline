# Point-to-point linear FTIR baseline removal

This desktop application performs interactive linear point-to-point baseline
subtraction on FTIR spectra. It was designed to complement
[Spectragryph](https://www.effemm2.de/spectragryph/) and reads the CSV format
exported by Spectragryph.

![FTIR baseline removal](example_image.png)

## Features

- Open and display one or more spectra at the same time.
- Add baseline anchors snapped to the active spectrum or at free cursor
  coordinates.
- Hover to highlight unfinished anchors, drag them along the data curve, or
  right-click an anchor to delete it.
- Interpolate a piecewise-linear baseline, extending the first and last
  segments beyond the outer anchors.
- Apply multiple corrections while preserving the correction history.
- Adjust the display offset between related spectra.
- Export corrected spectra with or without the cumulative display offset.
- Optionally export exact correction anchor coordinates alongside spectrum CSVs.
- Export a plot image for the selected spectra.

## Requirements

- Windows
- Python 3.10 or newer with Tcl/Tk support
- Dependencies listed in [`requirements.txt`](requirements.txt)

## Installation and launch

The included Windows scripts create a local virtual environment and install
the dependencies:

```bat
setup.bat
run_gui.bat
```

Alternatively, install the dependencies into an existing Python environment:

```powershell
python -m pip install -r requirements.txt
python ftir_gui.py
```

When no files are supplied, the application opens all CSV files in the
project directory. Files can also be supplied explicitly:

```powershell
python ftir_gui.py Example_Data.csv
```

## Input data

Input files must contain at least two numeric X,Y rows. The loader accepts
comma-, semicolon-, or tab-delimited files, optional leading header rows, and
additional columns after X and Y. X values must be unique and strictly
increasing or strictly decreasing. Spectragryph exports such as
[`Example_Data.csv`](Example_Data.csv) are supported.

## Workflow

1. Export a csv from Spectragryph
2. Open a CSV file with **Open CSV...**, or pass it on the command line.
3. Select the spectrum to correct in the spectrum list.
4. Use the pencil button in the Matplotlib toolbar; it is enabled by default.
5. Drag with the left mouse button to place points snapped to the spectrum.
   Hold **Shift** while dragging to place a point at the cursor's X and Y.
   Hover over an existing unfinished anchor to highlight it, then left-drag
   to move it along the active data curve (even if Shift is held). Release
   to commit the move; **Esc** or releasing outside the plot cancels it.
6. Add at least two points and click **Apply**. The corrected spectrum is
   inserted directly below its parent. Check **Retain baseline spectrum**
   before applying if you also want the calculated piecewise-linear baseline
   added as a separate, unchecked spectrum.
7. Use **Save spectra** to export selected spectra, choosing whether to
   include the cumulative display offset. Check the baseline spectrum first if
   you want to save or display it. Enable **Also save explicit anchor coordinates**
   in the save dialog to write a companion `<spectrum filename>_Anchors.csv`
   for each exported spectrum with saved correction anchors.

Use the **Move active up/down** buttons below the spectrum table to control
table order. This order controls plot layering and color assignment. The
toolbar also provides palette choices, including a colorblind-friendly
palette, and a line-weight control.

Right-clicking an unfinished anchor deletes only that anchor and reconnects
its neighbors. Right-clicking elsewhere in the plot removes the most recently
created remaining baseline point. Moving an anchor does not change this order;
deleting one removes it from the undo history. These controls are enabled only
in baseline-point mode, not during pan/zoom.
**Clear anchors** removes the current unfinished baseline and **Apply
baseline** creates a corrected spectrum. A highlighted spectrum is the
active spectrum used for baseline editing and offset changes; checked spectra
are visible and selected for operations. Enable **Show anchor points** to
display saved correction points for checked spectra.

Anchor CSVs contain the exact X,Y coordinates used to calculate the correction,
in creation order, including free-coordinate anchors. Y is always unshifted
absorbance in the corrected spectrum's **parent** coordinate system, regardless
of the spectrum export's offset option. The CSV header identifies the parent.
Both corrected and retained baseline spectra carry these anchors; original
spectra without correction anchors do not produce companion files. The full
baseline spectrum remains a separate export: enable **Retain baseline spectrum**
before applying, then check it for saving. Saved correction anchors are
provenance, not editable points for an already-applied correction.

**Offset spectrum (absorbance)** is a vertical offset in Y-axis units. Each
newly corrected spectrum defaults to the offset required to place its lowest
point at the same height as the highest point of its parent. Adjusting the
value changes only the spectrum's vertical display position.

## Round trip from OMNIC to Spectragryph and back again
See "OMNIC_Spectragryph_Data_Transfer_Guide" in this repository for a detailed set of instructions on how to process data in spectragryph and re-introduce the processed data to OMNIC. The .spa -> .spc -> .spa process will result in a file with incorrect metadata. Although the metadata can be injected into the binary through the OMNIC software, the new .spa file will retain the "blank" metadata as well as the user-created (true) metadata AND NOT ALL THE METADATA WILL SURVIVE. It is reccomended that you record the full metadata from OMNIC as soon as you finish collecting data so that you can always reference it without accessing the OMNIC software. 

## Tests

Run the test suite from the project directory:

```powershell
python -m unittest discover -s tests -v
```

## Experimental automatic baseline backend

The automatic method is available for numerical review only; the GUI has not
been wired to it. It assumes absorbance spectra with positive-going bands.
Every generated anchor is an exact measured X,Y sample, joined to its neighbors
by straight lines. The internal smooth envelope only guides sample selection;
it is never used as the final baseline.

```python
from automatic_baseline import automatic_baseline
from spectra_model import load_spectrum
from pathlib import Path

spectrum = load_spectrum(Path("Example_Data.csv"))
result = automatic_baseline(spectrum, coarseness=55)
# result.anchors, result.baseline, result.corrected, result.warnings
```

Coarseness is an integer from **0 to 100**. Larger values bridge wider features;
smaller values follow more spectral detail. The physical window width is
`5 * (2**(C/10) - 1)` cm^-1, rather than a number of sample rows. `C=0`
intentionally tracks nearly all signal; `C=100` deliberately leaves excessive
broad structure in these examples. Start reviewing around **45, 55, and 65**;
these are comparison candidates, not scientifically validated defaults.

Generate the five-spectrum reference comparison, extreme-parameter examples,
and full 101-value sweep:

```powershell
python baseline_review.py
python -m unittest discover -s tests -p test_automatic_baseline.py -v
```

Outputs are written to
[`Automated_Baseline_Examples/Automated_Results/`](Automated_Baseline_Examples/Automated_Results/):
start with [`review_overview.png`](Automated_Baseline_Examples/Automated_Results/review_overview.png),
then [`parameter_extremes.png`](Automated_Baseline_Examples/Automated_Results/parameter_extremes.png).
There is a full-range/detail image for each spectrum, a parameter-sweep image,
numeric metrics, and input hashes/settings in the run metadata. Circles in
baseline panels mark the actual anchors; the legend reports their count.
[`review_anchors.csv`](Automated_Baseline_Examples/Automated_Results/review_anchors.csv)
lists the exact coordinates for the C=45/55/65 comparison curves. Regeneration
overwrites only the named generated outputs, not the manual examples.

See the [proposal and implementation notes](Automated_Baseline_Examples/AUTOMATED_BASELINE_PROPOSAL.md)
for the method, measured reference comparisons, and limitations. Broad absorption
and baseline curvature cannot be distinguished reliably by shape alone.

## Project files

- [`ftir_gui.py`](ftir_gui.py): Tkinter and Matplotlib desktop interface.
- [`spectra_model.py`](spectra_model.py): spectrum loading, correction, and
  export logic.
- [`automatic_baseline.py`](automatic_baseline.py): experimental numerical
  baseline estimation, without GUI/session changes.
- [`baseline_review.py`](baseline_review.py): reproducible reference sweeps and plots.
- [`Example_Data.csv`](Example_Data.csv): example Spectragryph-style input.
- [`tests/`](tests/): model and GUI tests.
