# Proposal: scale-controlled automatic point-to-point FTIR baselines

> **Implementation update:** The original comparison and algorithm proposal
> below are retained as a historical design record. The expanded reference
> files replace the original pair, so the filenames and statistics in section 1
> describe the earlier files, not the current ten drawings. The implemented
> experimental backend uses local convex envelopes **only to guide selection
> of actual measured anchors**, plus a revised integer mapping instead of
> the flat morphological opening and `W=25*C` below. Every final anchor is
> an exact measured X,Y pair; only straight segments connect them.
> See [Implementation and first review](#5-implementation-and-first-review)
> for the current method, outputs, and limitations.

## Scope and recommendation

Automatically propose baseline anchors using a lower-envelope calculation with
an integer **coarseness** parameter, then connect those anchors with the
application's existing piecewise-linear baseline calculation. Larger integers
should bridge wider spectral features; smaller integers should follow more
local baseline structure.

This document compares the supplied examples and specifies a proposed numerical
method. It does not implement the method, change existing correctivon behavior,
or add GUI controls. The numerical settings below are starting hypotheses to
calibrate, not settings already demonstrated to reproduce these examples.

## 1. What the example files show

### Inputs and consistency checks

The comparison uses all six CSV files:

| Version | Uncorrected | Corrected | Baseline |
|---|---|---|---|
| Coarse | [Original](<Coarse Baseline/SID181c_Aperature32_Gain1.csv>) | [Corrected](<Coarse Baseline/SID181c_Aperature32_Gain1_BaselineCorrected_1.csv>) | [Baseline](<Coarse Baseline/SID181c_Aperature32_Gain1_Baseline_1.csv>) |
| Fine | [Original](<Fine Baseline/SID181c_Aperature32_Gain1.csv>) | [Corrected](<Fine Baseline/SID181c_Aperature32_Gain1_BaselineCorrected_2.csv>) | [Baseline](<Fine Baseline/SID181c_Aperature32_Gain1_Baseline_2.csv>) |

- The two uncorrected files are byte-for-byte identical. This is a comparison
  of two corrections of the same measurement, not of different measurements.
- All six files contain 6,950 samples on the same descending wavenumber grid,
  from 4000.188 to 649.904 cm^-1. Median sample spacing is 0.482 cm^-1.
- For both versions, `uncorrected - baseline = corrected` at every sample:
  the maximum residual using the parsed floating-point values is zero.
  Consequently, no additional vertical export offset is needed to reconcile
  these files. All numbers below use their stored Y values, not plot offsets.
- Y values are treated as absorbance, consistent with the application's
  terminology; the CSV headers themselves do not specify a Y-axis unit.

### Whole-spectrum comparison

| Measurement | Coarse correction | Fine correction |
|---|---:|---:|
| Uncorrected Y range, shared | -0.258909 to 0.081439 | -0.258909 to 0.081439 |
| Baseline Y range | -0.258555 to 0.017573 | -0.258484 to 0.075478 |
| Corrected Y range | -0.003414 to 0.074406 | -0.002622 to 0.046355 |
| Mean corrected Y over samples | 0.012361 | 0.006887 |
| Position of largest corrected value, cm^-1 | 1502.300 | 1807.003 |
| Negative corrected samples | 942 / 6950 (13.55%) | 1443 / 6950 (20.76%) |
| Detectable interior baseline slope changes | 17 | 27 |

Slope changes were counted from adjacent baseline segment slopes
`(B[i+1] - B[i]) / (x[i+1] - x[i])`, with a change threshold of
`1e-8` absorbance per cm^-1. Counts were also unchanged at thresholds of
`1e-9` and `1e-10`. These are detectable bends in the exported curves,
not necessarily the original anchor counts: collinear anchors and anchors
whose segments are extended beyond the data cannot be recovered uniquely.

The fine baseline has more local detail and removes more signal overall.
However, it is not everywhere above the coarse baseline:
`B_fine - B_coarse` ranges from -0.003147 to +0.065708. Its sample-mean
value is +0.005473 and its RMS value is 0.015312. At every wavenumber,
`corrected_fine - corrected_coarse = -(B_fine - B_coarse)`, to floating-point
precision (maximum discrepancy approximately 1.39e-17).

### Where the corrections differ

Representative samples are listed at their actual measured wavenumbers.

| Wavenumber, cm^-1 | Uncorrected | Coarse baseline | Fine baseline | Coarse corrected | Fine corrected |
|---|---:|---:|---:|---:|---:|
| 3800.107 | -0.027784 | -0.029233 | -0.028897 | 0.001449 | 0.001113 |
| 3300.143 | -0.000567 | -0.009687 | -0.009177 | 0.009120 | 0.008610 |
| 2499.816 | 0.015443 | 0.012911 | 0.014902 | 0.002531 | 0.000541 |
| 1799.771 | 0.028715 | -0.015990 | -0.016169 | 0.044705 | 0.044884 |
| 1600.172 | 0.037912 | -0.001357 | 0.029845 | 0.039269 | 0.008067 |
| 1499.890 | 0.078932 | 0.006315 | 0.070136 | 0.072617 | 0.008796 |
| 1421.303 | 0.075478 | 0.009771 | 0.075478 | 0.065708 | 0.000000 |
| 1200.008 | 0.017444 | 0.001978 | -0.000097 | 0.015466 | 0.017541 |
| 799.845 | -0.189684 | -0.188774 | -0.188790 | -0.000910 | -0.000894 |

The dominant difference is the broad elevated structure around
1300-1650 cm^-1. The mean corrected Y in that interval falls from
0.051995 (coarse) to 0.009390 (fine); the RMS baseline difference there is
0.046555. The largest pointwise difference is at 1421.303 cm^-1, where
the fine baseline touches the original spectrum and removes all signal at
that sample, while the coarse correction retains 0.065708.

The coarse baseline has a long straight section between approximately
1558.71 and 1243.88 cm^-1. The fine baseline inserts bends near 1507.12,
1488.32, 1457.94, 1421.30, and 1320.54 cm^-1 within that interval.
Thus, "fine" means following the raised structure locally, not merely
resampling the same coarse line with more points.

In contrast, much of the high-wavenumber region is similar: the RMS baseline
difference over 3000-4000.188 cm^-1 is only 0.000529. Both corrections also
remove much of the strongly negative low-wavenumber trend, despite the
original reaching -0.258909. A baseline can be negative; it must not be
constrained to zero absorbance.

Neither version is established as the scientifically correct baseline.
If the raised structure is unwanted continuum, the fine result is useful;
if it is real broad absorption, the fine result removes meaningful signal.
The files alone cannot resolve that distinction. More negative samples in
the fine result also show why minimizing corrected signal or forcing every
point to zero is not an adequate quality criterion.

## 2. Integer coarseness parameter

Define `C` as an integer greater than or equal to 1:

```text
W(C) = 25 * C cm^-1
```

`W` is the full width of a moving spectral neighborhood, not an anchor count
or a number of data rows.

| Trial C | Neighborhood width W | Intended starting behavior |
|---:|---:|---|
| 1 | 25 cm^-1 | Very local; greatest risk of treating bands as baseline |
| 4 | 100 cm^-1 | Fine starting candidate |
| 12 | 300 cm^-1 | Intermediate starting candidate |
| 24 | 600 cm^-1 | Coarse starting candidate |

These are illustrative candidates, not a fitted mapping to the supplied
labels. Calibration should determine the recommended fine and coarse values.
The approximately 315 cm^-1 coarse segment in the main differing region
motivates exploring widths of several hundred cm^-1, but segment length is
not mathematically equal to the best neighborhood width.

Increasing `C` makes the method less willing to follow narrower positive
features. Decreasing `C` allows the baseline to climb into more local valleys
and broad raised structures, as in the fine example. This is a physically
meaningful control even when sampling density changes. It is not a guarantee
of exactly one anchor every W cm^-1, or of monotonically decreasing anchor
counts after simplification.

## 3. Proposed automatic drawing method

### A. Prepare data without changing the measurement

1. Use the existing loader's finite-value, unique-X, and monotonic-X checks.
   Work on a copy in ascending wavenumber order; preserve the original order
   for returned baseline and corrected arrays.
2. Operate on stored absorbance, never on a displayed or cumulative offset.
   Assume positive-going absorption bands. Transmittance or deliberately
   inverted spectra require a separately defined conversion/polarity policy;
   do not silently apply this lower-envelope method to them.
3. Make an estimation-only signal `s(x)` using a narrow median filter, with
   a proposed fixed full width of 3 cm^-1. Use actual X distances, including
   on nonuniform grids. This suppresses isolated spikes without smoothing
   the spectrum that will ultimately be subtracted.
4. Estimate a noise scale from adjacent differences of the original signal:
   `sigma = 1.4826 * MAD(diff(y)) / sqrt(2)`. This is a starting robust
   estimate for approximately independent noise, not a universal uncertainty
   estimate for correlated FTIR data. Validate it on quiet spectral regions.

### B. Estimate a lower envelope at the chosen width

Use a one-dimensional **flat morphological opening** of `s`:

```text
r = W(C) / 2
e(x) = minimum of s(t) for |t - x| <= r
g(x) = maximum of e(t) for |t - x| <= r
```

The first operation is erosion; the second is dilation with the same
neighborhood. Together they remove positive features narrower than the
selected scale while allowing sufficiently broad structure to remain in
the baseline estimate. Unlike selecting the minimum independently in
disjoint bins, the overlapping neighborhoods do not depend on bin edges.
No requirement that absorbance be positive is introduced.

Use coordinate-based neighborhoods on the measured grid. A NumPy
implementation can use sorted-X moving-window extrema with monotonic queues;
no new numerical dependency is required. Do not equate W with a fixed number
of samples or unnecessarily resample nonuniform data.

For boundary calculations, reflect the estimation signal beyond each end
over the required support. Each output can depend on samples up to W away
through the two operations, even though each individual window has width W.
Flag the first and last W cm^-1 as boundary-influenced; reflection is a
numerical convention, not evidence about the spectrum outside its range.
If W is greater than or equal to the measured span, report an unsupported
scale instead of silently padding a mostly unmeasured neighborhood.

### C. Convert the envelope into editable straight-line anchors

1. Start with envelope points at both measured endpoints.
2. Recursively split a candidate straight segment at the sample with the
   largest **vertical absorbance error** relative to `g`. Stop splitting
   when every sample differs by at most
   `tau = max(2 * sigma, 1e-6 * (max(s) - min(s)), 1e-12 absorbance)`.
   This is a vertical-error variant of polyline simplification; do not use
   Euclidean distances that mix wavenumber and absorbance units.
3. Check the resulting interpolated line against `s`. If it rises more
   than `3 * sigma` above `s`, insert the envelope point at the worst
   violation and repeat. At an already retained sample, a remaining
   violation is a diagnostic failure rather than an infinite refinement
   loop. Use a floating-point tolerance for zero-noise data.
4. Retain the envelope Y values at the selected X positions. Do not snap
   these Y values back to the raw spectrum: that would reintroduce noise
   and change the estimated baseline. This is compatible with the
   application's existing free-coordinate anchors.
5. Evaluate the selected anchors with
   [`linear_baseline`](../spectra_model.py), then calculate
   `corrected = original_y - baseline` at the original sample positions.

Including measured endpoints avoids relying on the existing end-segment
extrapolation for automatic corrections. The final result is still an
ordinary point-to-point linear baseline, with inspectable, editable anchors,
not a hidden spline or an unrelated correction representation.

`C` controls the envelope's spectral scale. The noise-derived simplification
tolerance controls only how faithfully straight segments represent that
envelope; it is not another user-facing coarseness control. Larger scales
generally suppress more local structure, but noise filtering, edges, and
anchor simplification mean the final curves need not be strictly nested.

### D. Return diagnostics, not just a corrected spectrum

A future model-level operation should return proposed anchors, baseline,
corrected values, C, effective W, the estimated noise, and quality warnings.
Retain original data and correction provenance through the existing
[`SpectraSession`](../spectra_model.py) workflow rather than replacing the
measurement in place. Record the algorithm version and fixed internal
settings so that a result can be reproduced.

Report invalid C values (including booleans and nonintegers), unsupported
widths, too-short input for noise estimation, and nonfinite intermediate
results explicitly. Warn about boundary dependence, large sampling gaps
(for example, gaps wider than W/2), unusually dense refinement, and long
negative corrected runs beyond the estimated noise. Do not clip negative
corrected values, silently discard problematic regions, or claim success
when validation fails. A constant spectrum can return its constant baseline
and zero correction, with the numerical tolerance floor preventing division
by zero or unnecessary refinement.

## 4. Calibration and acceptance before implementation is considered finished

The current files are reference drawings, not ground-truth physical
baselines. Use them to calibrate the intended distinction:

1. Sweep valid integer C values on the shared original, initially exploring
   W from 25 to 1000 cm^-1. Score each generated baseline against each
   supplied baseline using whole-range RMSE and regional RMSE, especially
   1300-1650 cm^-1. Also report maximum absolute error and anchor count.
2. Select a smaller C for the fine target and a larger C for the coarse
   target only if that ordering is supported by the results. Compare the
   generated baseline error to the measured fine/coarse separation:
   0.015312 RMS globally and 0.046555 RMS in 1300-1650 cm^-1.
   Those separations are reference scales, not acceptance thresholds.
   Require each selected result to be closer to its intended reference
   than to the opposite reference, globally and in the main differing
   region; then review remaining errors and set application-specific
   tolerances before release.
3. Check whether the fine candidate follows the raised structure and the
   coarse candidate bridges it, while both retain comparable behavior
   near 1800 cm^-1 and remove the large negative low-wavenumber trend.
   Compare integrated corrected band areas as well as peak heights.
4. If the single-scale method cannot represent both drawings adequately,
   report that limitation. Do not conceal it through hard-coded anchor
   positions for this spectrum. Region-specific masks or user-selected
   baseline regions would be a later, explicit extension.
5. Test synthetic known baselines plus narrow and broad positive peaks,
   noise, isolated positive/negative spikes, and edge peaks. Quantify
   baseline recovery and peak-height/area retention. A narrow negative
   spike is especially important: a lower-envelope method can mistake it
   for baseline even after the median prefilter.
6. Verify ascending/descending equivalence, stable physical-scale behavior
   after changing sample density, nonuniform grids, constant inputs,
   invalid integers, excessive widths, and endpoint handling. Test exact
   output shape/grid preservation and `original = baseline + corrected`
   to an explicit floating-point tolerance. Confirm that display offsets
   have no effect and that manual correction behavior is unchanged.

No automatic method can reliably distinguish a broad chemical absorption
from broad baseline curvature using shape alone. Coarseness makes that
tradeoff explicit and reproducible; it does not eliminate the need to
choose an appropriate scientific interpretation.

## 5. Implementation and first review

### Current scope

The experimental backend is in [`automatic_baseline.py`](../automatic_baseline.py).
It neither changes the GUI nor applies a correction to the session. It returns
anchors, full baseline and corrected arrays, requested/effective scale, estimated
noise, simplification tolerance, a boundary mask, warnings, and algorithm version
`on-data-linear-anchors-v2`. The returned anchors are exact measured X,Y pairs,
not envelope values. They are evaluated with the existing `linear_baseline`
and can be used by the existing manual correction/session path. The earlier
v1 output was technically a dense polyline, but its off-data envelope anchors
made it appear smooth and did not meet the required on-data-anchor constraint.

All five current originals have 6,950 samples. Fine/coarse originals are
numerically identical for each pair. The ten baseline exports are reconstructed
by their explicit anchors and satisfy `original - baseline = corrected`, with
no export offset adjustment. The review script verifies these conditions rather
than assuming them. Inputs and manual drawings are not modified.

### Revised integer parameter

The supported range is **integer C = 0 through 100**, including intentionally
poor settings at either end:

```text
requested full window width W(C) = 5 * (2**(C/10) - 1) cm^-1
```

| C | Requested W, cm^-1 | Role in this review |
|---:|---:|---|
| 0 | 0 | Measured data polyline itself; removes essentially all signal |
| 30 | 35 | Very fine local following |
| 45 | 108.14 | Finer review candidate |
| 55 | 221.27 | Intermediate review candidate |
| 65 | 447.55 | Coarser review candidate |
| 80 | 1275 | Deliberately very broad bridging |
| 100 | 5115 | Deliberately excessive coarsening on these examples |

This logarithmic spacing gives many integer settings in the useful transition
range while retaining strong extremes. It does not merely interpolate between
the two manual drawings or constrain the result to lie between them.
Ten increments approximately double a nonzero large window width.
The physical width is independent of sample density. If it is smaller than
the median sample spacing, that spacing is used with a warning. A window radius
at least as large as the measured span uses one global lower convex hull as
the selection guide; its effective full width is capped at twice that span
and reported. The final baseline still connects selected measured samples.

### Implemented estimation and drawing

1. Validate finite, matching, one-dimensional arrays with at least three samples
   and unique monotonic X. Normalize direction for estimation; return arrays on
   the original grid and in the original order. Ignore display offsets.
2. Make an estimation-only signal using a 3 cm^-1 full-width local median.
   First remove a local slope estimated by the median of neighboring slopes,
   take the median residual, and restore the trend. This preserves affine
   baselines on irregular grids and reduces isolated positive/negative spikes.
   Boundary neighborhoods without full support retain their original values.
   The measured spectrum itself is never smoothed or replaced.
3. Lay out overlapping windows of full width W with centers W/4 apart, measured
   from the low-wavenumber endpoint. Use only centers inside the measured range.
   Within each window, compute the lower convex hull of the estimation signal
   and interpolate its vertices. A lower convex hull is the line a taut
   rubber band would take underneath those points: it bridges raised structures
   but can still follow sloping backgrounds.
4. Blend the overlapping hull estimates with triangular weights, largest at
   each window center and zero at its support edges. This avoids abrupt seams
   from disjoint bins. Coordinate-based windows handle nonuniform grids
   directly. Empty gaps do not allocate windows across the entire empty range.
   This smooth-looking estimate is an internal ranking guide only, never the
   final baseline.
5. Divide the measured range into candidate-selection intervals W/2 wide.
   In each occupied interval, choose the actual measured sample whose Y is
   closest to the lower support estimate (minimum `measured_y - envelope_y`).
   Exclude interior samples whose deviation from the median signal exceeds
   `tau = max(3*sigma, 0.003*signal_range, numerical_floor)`, avoiding isolated
   spikes. Both measured endpoints are included even if spike-like; inspect
   boundary warnings. No synthetic X or Y coordinates are introduced.
6. Simplify that sequence of measured candidates using vertical-error splitting
   with tolerance tau. Then insert additional eligible measured samples at
   missed valleys wherever a straight segment rises above the estimation signal
   by more than tau. Insertion terminates because each split retains a distinct
   original sample. This allows important valleys to survive even if their
   spacing is less than W/2. If an interval has no eligible interior samples,
   do not invent an anchor. At C=0, start from all measured samples and remove
   only numerically collinear points, deliberately following essentially all
   signal including noise.
7. Copy exact anchor X,Y coordinates from the original arrays (not from the
   normalized coordinates or filtered signal). Use `linear_baseline` to join
   those points with straight segments and subtract from the original Y.
   Corrected values are zero at anchors to floating-point precision; negative
   residuals between them are retained. The noise/shape tolerance now controls
   simplification of the measured candidate chain, not fidelity to the envelope.
   It does not impose a strict global envelope-fit error bound.

Each weighted estimate can depend on samples up to W away, so the first/last W
cm^-1 are conservatively marked as boundary-influenced (not just W/2).
Warnings also flag large gaps, dense refinement, sharp features changed by the
prefilter, and sustained negative corrected runs beyond the estimated noise.
Invalid inputs and nonfinite arithmetic raise explicit errors.

### Why not implement the original flat opening unchanged?

Initial numerical trials showed that a flat opening produces excessive
flattening as the window grows across the steep low-wavenumber background.
Sloped local hull segments gave substantially better agreement with the manual
coarse drawings while preserving exact affine baselines in synthetic tests.
There are no spectrum-specific anchor positions in the method.

### Review outputs and reproduction

Run from the repository root:

```powershell
python baseline_review.py
```

Optional `--examples` and `--output` arguments select other reference/output
folders. The script expects matching originals and one baseline/corrected pair,
with both anchor exports, in each fine/coarse folder. Inconsistent grids, offsets,
or anchors fail explicitly. The current review regions must be covered.

Outputs in [`Automated_Results/`](Automated_Results/):

- [`review_overview.png`](Automated_Results/review_overview.png): all five
  spectra, comparing C=45/55/65 against both manual references at 1200-1900 cm^-1.
- [`parameter_extremes.png`](Automated_Results/parameter_extremes.png): C=0/100,
  showing deliberate over-removal and excessive broad residual structure.
- One four-panel image per spectrum: baseline and corrected full-range views,
  plus 1200-1900 cm^-1 detail. All values are unshifted. Circles mark the
  actual measured anchors; each automatic legend reports anchor count `n`.
- [`review_anchors.csv`](Automated_Results/review_anchors.csv): exact measured
  coordinates, in ascending X order, for each displayed C=45/55/65 curve.
- [`parameter_sweep.png`](Automated_Results/parameter_sweep.png): baseline
  distances to manual references for every integer C=0..100.
- [`metrics.csv`](Automated_Results/metrics.csv): all 505 runs, with whole-range
  and 1300-1650 cm^-1 RMSE, maximum baseline errors, anchor counts, corrected
  ranges/RMS, negative fractions, signed band areas, 1700-1900 cm^-1 peak
  heights, boundary fractions, and warnings. The review script rejects off-data
  anchors or baselines that are not exactly their `linear_baseline` polyline;
  `anchor_sample_max_error` must be zero for every run.
- [`run_metadata.json`](Automated_Results/run_metadata.json): settings, version,
  reference statistics, closest-reference levels, selected results, and SHA-256
  hashes for all 50 supplied CSV files.

Distances to manual drawings describe similarity, not physical accuracy. Band
areas use ascending wavenumber integration without clipping negative residuals.
No claim of a scientifically validated default is made; C=45/55/65 are shared
comparison settings chosen to show a useful spread across all five spectra.

### Measured similarity to the expanded manual references

The full integer sweep produced the following closest **whole-spectrum**
matches. RMSE is in unshifted absorbance units:

| Spectrum | Closest fine C | Fine RMSE | Closest coarse C | Coarse RMSE |
|---|---:|---:|---:|---:|
| SID180c, AutoGain, 256 scans | 50 | 0.002792 | 56 | 0.006661 |
| SID181c, AutoGain, 256 scans | 59 | 0.008193 | 68 | 0.002560 |
| SID181c, Gain1 | 59 | 0.006860 | 63 | 0.001518 |
| SID181c, Gain4 | 46 | 0.005657 | 68 | 0.005584 |
| SID181c, Gain8 | 59 | 0.009018 | 67 | 0.009351 |

For all five spectra, the closest coarse setting exceeds the closest fine
setting, supporting the intended direction of the control. These are not
recommended settings: minimizing global error can trade away a locally
important band. Use the regional metrics and plots as well.

At the displayed C=45/55/65 levels the revised method uses 46-61, 24-35,
and 16-28 measured anchors, respectively. All 505 sweep runs pass exact
sample-membership and anchor-polyline reconstruction checks. The coordinate
export contains 547 measured anchor pairs across the 15 displayed candidates.

At C=0, corrected RMS is below 0.002 for all five inputs: virtually all signal
has been removed. At C=100, corrected RMS exceeds twice its C=55 value for
every input, and the extreme plots show large false-looking broad residuals.
Thus, both deliberately poor endpoints are available rather than artificially
clamping the method between the manual references.

### Limitations and review priorities

- One global scale cannot encode all of a human's region-specific choices.
  In particular, following the raised 1300-1650 cm^-1 structure can also remove
  part of the 1700-1900 cm^-1 band that both manual drawings preserve. Inspect
  that tradeoff in the detail panels, not just overall RMSE.
- Broad absorption and unwanted continuum remain indistinguishable by shape.
  Neither the manual examples nor synthetic tests establish physical truth.
- Window placement, discrete sampling, and simplification introduce small
  fluctuations as C changes. Larger C generally bridges more, but pointwise
  nesting and monotonically decreasing anchor counts are not guaranteed.
- Convex background troughs are followed more readily than concave background
  arches. Large C can falsely retain background curvature as broad absorption;
  that deliberately bad behavior is visible in the extreme plots.
- Endpoint peaks can be absorbed into the baseline because nothing outside the
  measured range constrains them. The boundary mask is a warning, not a repair.
- Median filtering reduces isolated spikes, but clusters or broad negative
  artifacts can still pull the lower envelope down. Original spikes remain in
  corrected data; no spike deletion or clipping is performed.
- Exact sample membership, straight segments between every pair of anchors,
  plotted marker coordinates, rejection of off-data review results,
  affine recovery, output shape/subtraction, direction and offset invariance,
  sampling-density behavior, local hulls against brute-force chords, noise,
  isolated spikes, gaps, boundaries, parameter validation, all five references,
  and reference consistency have automated numerical tests.

The next decision should come from reviewing the candidate plots and identifying
which broad structures should remain. This prototype does not add GUI controls,
fit spectrum-specific exceptions, or silently optimize all corrected signal away.
