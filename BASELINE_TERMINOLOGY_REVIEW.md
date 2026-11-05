# Proposed “Background” to “Baseline” Replacements

This is a review list only. No terminology replacements have been made in the
program. The entries below refer specifically to the point-to-point linear
curve that is subtracted from the raw spectrum.

## Proposed replacements

| Location | Current text | Proposed replacement |
|---|---|---|
| `ftir_gui.py:69` | `FTIR - Linear point-to-point background` | `FTIR - Linear point-to-point baseline` |
| `ftir_gui.py:50` | `class BackgroundToolbar` | `class BaselineToolbar` |
| `ftir_gui.py:159` | `Enable 'Add background points' in toolbar.` | `Enable 'Add baseline points' in toolbar.` |
| `ftir_gui.py:177` | `Add background points: drag to place anchors; hold Shift for free X,Y.` | `Add baseline points: drag to place anchors; hold Shift for free X,Y.` |
| `ftir_gui.py:188` | `Apply background` | `Apply baseline` |
| `ftir_gui.py:404` | `Discard unfinished background?` | `Discard unfinished baseline?` |
| `ftir_gui.py:405` | `The current background drawing will be discarded.` | `The current baseline drawing will be discarded.` |
| `ftir_gui.py:424` | `Enable 'Add background points' to draw a baseline.` | `Enable 'Add baseline points' to draw a baseline.` |
| `ftir_gui.py:514` | `Background point controls disabled while navigating.` | `Baseline point controls disabled while navigating.` |
| `ftir_gui.py:524` | `Background point controls enabled. Drag to preview; release to place. Hold Shift when starting a drag for cursor X,Y; right click to undo.` | `Baseline point controls enabled. Drag to preview; release to place. Hold Shift when starting a drag for cursor X,Y; right click to undo.` |
| `ftir_gui.py:528` | `Background point controls disabled. Existing points are preserved.` | `Baseline point controls disabled. Existing points are preserved.` |
| `ftir_gui.py:559` | `Show and activate a spectrum before drawing a background.` | `Show and activate a spectrum before drawing a baseline.` |
| `ftir_gui.py:636` | `Background drawing cleared.` | `Baseline drawing cleared.` |
| `ftir_gui.py:643` | `Cannot apply background` | `Cannot apply baseline` |
| `ftir_gui.py:895` | `Discard the unfinished background and close?` | `Discard the unfinished baseline and close?` |
| `spectra_model.py:162` | `{parent.source.stem}_BackgroundCorrected_{self.correction_count}` | `{parent.source.stem}_BaselineCorrected_{self.correction_count}` |
| `tests/test_model.py:57` | `raw_BackgroundCorrected_1` | `raw_BaselineCorrected_1` |
| `tests/test_model.py:69` | `raw_BackgroundCorrected_2` | `raw_BaselineCorrected_2` |
| `README.md:1` | `# Point-to-point linear FTIR background removal` | `# Point-to-point linear FTIR baseline removal` |
| `README.md:3` | `This desktop application performs interactive linear point-to-point background subtraction on FTIR spectra.` | `This desktop application performs interactive linear point-to-point baseline subtraction on FTIR spectra.` |
| `README.md:8` | `![FTIR background removal](example_image.png)` | `![FTIR baseline removal](example_image.png)` |
| `README.md:74` | `**Apply background** creates a corrected spectrum.` | `**Apply baseline** creates a corrected spectrum.` |

## Wording that is already correct

These references already use “baseline” for the curve and do not need a
terminology change:

- `README.md:12`: “Add baseline anchors...”
- `README.md:14`: “Interpolate a piecewise-linear baseline...”
- `README.md:62`: “baseline anchors”
- `README.md:73`: “baseline point”
- `ftir_gui.py:424`: “draw a baseline” (only the earlier “background points”
  phrase on that line needs replacement)
- `ftir_gui.py:871`: “background” does not occur; the export behavior is
  described as corrected spectra
- `spectra_model.py:145-162`: the calculation variable and function already
  use `baseline`

## References intentionally excluded

These uses of “background” refer to rendering/UI implementation details, not
the subtractive spectral curve. They are included here so every occurrence is
accounted for; the proposed action is to retain them unless the implementation
is deliberately refactored later.

| Location | Current text or symbol | Proposed change | Reason |
|---|---|---|
| `ftir_gui.py:41` | `background="#ffffe1"` | Retain unchanged | Tk tooltip background color |
| `ftir_gui.py:81` | `_blit_background` | Retain unchanged | Matplotlib blitting cache for redrawing the plot |
| `ftir_gui.py:284` | `background="#ffffe1"` | Retain unchanged | Tk table tooltip background color |
| `ftir_gui.py:352-360` | `_cache_blit_background` and `_blit_background` | Retain unchanged | Matplotlib plot-rendering buffer, not spectral data |

## Remaining path and external-resource occurrences

These occurrences are not program terminology and are not safely changed as
part of a source rename. They are listed for completeness, with the proposed
action that would be appropriate if the surrounding path or resource were
intentionally renamed.

| Location | Current text | Proposed change | Notes |
|---|---|---|---|
| Workspace parent directory | `point_to_point_linear_FTIR_background - Copy` | Rename to `point_to_point_linear_FTIR_baseline - Copy` only if the workspace is intentionally renamed | External workspace path; changing it may break open editors, scripts, shortcuts, and environment references |
| Repository working directory | `point to point linear FTIR background` | Rename to `point to point linear FTIR baseline` only if the repository checkout is intentionally renamed | External checkout path; not a source-code change |
| GitHub repository identifier | `BergsmanGroup/point-to-point-linear-FTIR-background` | Rename the repository to `BergsmanGroup/point-to-point-linear-FTIR-baseline` only if the project repository is intentionally renamed | Requires a repository rename and updates to remote URLs, links, and documentation |
| `261104 ATR Testing/110426_ATR_SingleBackground_Static.csv` | `SingleBackground` | Rename to `SingleBaseline` if the experimental data file is intentionally renamed | User/data filename; any references or analysis scripts would need updating |
| `261104 ATR Testing/110426_ATR_SingleBackground_Static/` | `SingleBackground` | Rename to `SingleBaseline` if the generated-output folder is intentionally renamed | User/data output folder; generated files should be moved together |
| `.venv/Lib/site-packages/matplotlib/mpl-data/stylelib/dark_background.mplstyle` | `dark_background` | Retain unchanged | Third-party Matplotlib resource; changing it would modify an installed dependency and is unrelated to spectral baseline terminology |

All identified path and external-resource occurrences are included above even
when the proposed action is to retain them or rename them only as part of a
separate, intentional path/resource change.
