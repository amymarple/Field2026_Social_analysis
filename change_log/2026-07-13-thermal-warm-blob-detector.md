# Thermal warm-blob (rat) detector — unsupervised, AGC-robust (Phase 0)

**Date:** 2026-07-13
**Plan:** [implementation_plan/2026-07-13-thermal-warm-blob-detector.md](../implementation_plan/2026-07-13-thermal-warm-blob-detector.md)
**Status:** Phase 0 prototype — new `thermal/` subsystem; unsupervised, unvalidated, candidate-only. No
canonical `results/` output, no research direction promoted. Triggered by "is this thermal file intact +
how to analyze it → start with unsupervised bright-blob / background-subtraction detection."

## What shipped

- `thermal/detect_blobs.py` — an unsupervised warm-blob (rat) detector for the 108/109 thermal cameras, and
  its offline synthetic self-test (`--selftest`).
- `thermal/README.md` — subsystem doc (data nature, pipeline, outputs, limits).
- First code in the repo to touch the thermal cameras (previously zero references).

## Method (AGC-robust, MOG2/CLAHE-free)

Thermal MP4s are 1 fps, 1280×960, HEVC, white-hot monochrome, **auto-gain-controlled** — the gray→°C map
re-normalizes every frame, so absolute brightness is not a stable cue and the video is not radiometric.
Pipeline: dynamic + static **overlay masking** (static OSD rects + 6 px border; a **red-chroma** mask for
the moving spot-meter crosshair/readout, since it roams onto warm structures and sits *on* the true rat) →
white **top-hat** on luma (local, AGC-robust) → **robust-adaptive threshold** `max(floor=45, median+5·MAD)`
(deliberately **not Otsu**, which invents a foreground in the majority-empty frames) → morphology →
connected components → **geometry filter** (area∈[120,4500], aspect≤4.5, extent≥0.35, solidity≥0.5,
mean-response≥0.5·floor) → **persistence static-structure suppression** restricted to LARGE/ELONGATED
components (so a rat on the pole *separates* into its own blob; a compact resting rat is never erased) →
frame-diff **motion score** (never a gate) → greedy nearest-centroid **tracker** (110 px @1 fps).

Outputs (candidate-only): `detections.csv`, `tracks.csv` (with `mean_tophat` contrast, `net_disp_px`, and a
`motion_class` ∈ {moving, stationary_ambiguous}), `summary.json`, `static_mask.png`, preview PNGs + MP4.
Every output is labeled **RELATIVE warm blobs — NOT temperature, NOT identity, NOT a certified count**
(a lower bound). Times use frame index + filename wallclock; the OSD clock runs ~1 h behind.

## How it was derived

A 13-agent characterization workflow sampled 108/109 × night hours (21,22,00,02,04) and ran three design
lenses (top-hat / temporal / adversarial-critic). Findings that set the parameters: rats are compact bright
blobs **~25–90 px, ~200–1500 px²**, mobile, with strong **local** contrast (Δ~90–190 gray) but the static
**pole** (~40–55 px) and diagonal **berms/wires** anchor the AGC max; overlay boxes measured to ~10–20 px;
AGC drift medium→high; and the **~1 h OSD-clock offset** re-confirmed. See the [thermal-cameras memory note].

## Verification

- **Offline self-test PASS** — synthetic AGC sequence (drifting gain, static pole, OSD blocks, moving
  crosshair, two moving gaussian "rats"): mean 2.00 blobs/frame, 80/80 detections near a true rat (100%
  precision), 2 persistent tracks, pole + crosshair rejected, red-chroma mask verified. Stresses the
  rat-crosses-pole case (persistence suppression separates it).
- **Real-data run** (108, 2026-07-01 21:00, 300–600 frames): tuned params give **0.45–0.73 detections/frame**
  (max 3), matching the characterization's "0–1 intermittent rats" — vs **6.8/frame** with the untuned
  defaults (Otsu + floor=6), a ~9–15× false-positive reduction. Overlays/pole/crosshair verified clean in
  previews. Track signals split cleanly: **moving high-contrast tracks** (net disp 97–159 px, mean_tophat
  72–74) are strong rat candidates; **stationary low-contrast tracks** (mean_tophat ~46) are the hardest,
  label-requiring ambiguity (resting rat vs warm berm/rock), flagged not filtered.

## Addendum (same day) — label-free validation toolkit

Added `thermal/make_label_set.py` and `thermal/score_labels.py` to *validate* the unsupervised detector
without training. `make_label_set.py` samples frames (even spread + the busiest multi-object frames), embeds
them as JPEGs, and writes a **self-contained HTML labeling page pre-filled with the detector's candidate
boxes** — drag/resize/add/delete (multiple per frame), autosave to localStorage, export `labels.json`.
`score_labels.py` matches detector detections to the hand-corrected boxes (centroid-in-box, greedy) and
**sweeps a contrast (`tophat_mean`) threshold** to report precision/recall/F1 and the F1-optimal operating
point. Purpose: answer "is unsupervised enough, and where's the floor?" with a number. Verified the HTML
editor in-browser (image + candidate boxes + resize handles + multi-object frames render; nav + review
tracking work); fixed a template-injection bug (placeholder `/*__X__*/{}` left a stray `{}` that broke the
script) and cast numpy int frame indices for JSON. Full-hour 108/21:00 run: 1619 detections, 1241 frames
with detections, 315 multi-object frames (max 4). A 52-frame label set was generated for a first pass.

## Validation result (108/21:00, 52 frames, 66 hand-labeled rats)

First label-free evaluation. Distance-tolerant scoring (centroid within max(40 px, box half-diag)):
**precision/recall = 0.80/0.42 at floor 50, 0.92/0.35 at floor 55** (raw recall 0.52 accepting all).
Default `tophat_floor` set 45→50 (the F1 knee). Two findings that answer "do we need supervised learning?":

1. **Precision is a solved, tunable knob** — berm-edge FPs sit at contrast (`tophat_mean`) ~48, real rats
   at ~65; a floor of 50–55 removes ~90% of FPs. No learning needed.
2. **The recall gap is NOT a signal limit and NOT a supervision problem.** Tracing all 33 missed rats: the
   missed locations have *higher* local top-hat contrast than the hits (median 161 vs 91) — the signal is
   strong. Causes: ~11 eaten by an over-wide right-edge colorbar overlay mask (FIXED here — mask only the
   bar + top/bottom labels, not the tall mid strip; the moving readout is covered by the dynamic red-chroma
   mask; recovered ~4 pts recall); ~14 that pass all filters but merge slightly with adjacent structure so
   the blob centroid drifts off the rat (a LOCALIZATION problem — next lever is blob-splitting / local-maxima
   seeding / watershed, still unsupervised); ~6 genuine threshold/size edge cases. Conclusion: recall is
   recoverable by classical localization work; supervised learning is a fallback, not a requirement.
   Caveat: 66 boxes is a small set — numbers are indicative; validate on a held-out hour before locking them.

3. **Localization split — tried, reverted (negative result).** Added peak-seeded blob splitting + intensity-
   weighted centroids (`_split_and_localize`/`_peak_seeds`, `Params.localize`) to recover the supposed
   "mislocalized" misses. Clean floor-45 A/B on the labeled set: **identical TP at every floor (zero recall
   gain)** and **more FPs** (over-split rats), so precision fell (0.80→0.72 at floor 50). Conclusion: the
   ~0.52 recall ceiling is genuinely-hard cases (real 2-rat merges counted as undercount, occlusion, faint-
   on-structure), NOT a centroid artifact — fair distance-tolerant scoring already credited the near-misses.
   `localize` left in the code but **default False**. Operating default: `tophat_floor=50`, localize off.

## Supervised feature-filter — tried, does NOT beat the rules (negative result)

`thermal/train_filter.py`: trains a small rat/not-rat classifier (logistic + depth-3 RF) on the per-blob
features the detector already emits (contrast, area, shape, motion, normalized image position), evaluated
with **GroupKFold on frame id** (no frame in both train/test) and scored at the GT level, head-to-head with
the contrast rule. On the 108/21:00 set (52 frames, 66 rats; a floor-30 candidate pool for max recall):
**RF out-of-fold F1 0.45 (P 0.78 / R 0.32) vs rule contrast≥45 F1 0.39 (P 0.77 / R 0.26)** — within noise
for 23 positives. Coefficients (tophat_mean +1.53, cxn −0.86, aspect −0.83) show the classifier merely
re-learned the existing rules. **Recall is fundamentally capped, not threshold-limited:** dropping the floor
to 30 surfaced 5637 candidates but still only ~23/66 rats had a nearby blob (the lower floor mainly merged
blobs and added noise). The ~half that are missed produce NO separable component — huddles, occlusion, and
rats whose warm blob overlaps warm structure. A filter on top-hat blobs cannot recover a rat that never
forms a blob. Conclusion: improving recall needs a **pixel-level learned detector** (CNN/YOLO from raw
frames), not a feature filter or threshold — a large-label, uncertain-payoff investment on this soft
imagery, justified only if recall is mission-critical. `train_filter.py` kept (reusable once more labels
exist); it did not change the shipping detector. Operating default remains rules @ `tophat_floor=50`.

## Motion channel — tried, does NOT beat top-hat (negative result)

Motivation was strong: a pixel-level diagnostic found 30/43 missed rats had a temporal-motion signal
(ceiling ~0.80 recall). Built a temporal channel (`Params.use_motion`, `--use-motion`): robust per-frame
median/MAD normalization to undo AGC, EMA background, residual = warmer-than-background, merged with the
top-hat at the DETECTION level (separate component pass + 30 px centroid dedupe — an earlier pixel-OR
version *bloated and destroyed* the clean top-hat blobs, dropping recall 0.52→0.35). Canonical re-score,
same floor: top-hat alone @50 = 28 TP / 7 FP; +motion = 28 TP / **43 FP** — **zero net new TP, +36 FP**.
Why the ceiling didn't materialize: a rat warm enough to move-detect is already caught by the top-hat (the
"both" overlap); the rats top-hat misses are FAINT, and a faint-warm rat yields a faint/diffuse motion
residual too — below threshold or unlocalizable — while AGC shimmer + vegetation supply the FPs. Left in
behind `--use-motion`, **default off**. Third rigorous negative lever (with localization + the learned
filter): the ~0.42–0.52 recall ceiling on this soft AGC imagery is real for classical unsupervised methods;
only a pixel-level learned detector (many labels) could plausibly move it. Operating default unchanged
(rules @ `tophat_floor=50`, motion & localize off).

## Not done / deferred

Label-free evaluation (human spot-audit for a precision estimate), 109 viewpoint pass, per-hour threshold
sweep, cross-check vs WISER/CH cams (blocked by the clock offset + unverified frames), and any promotion to
a canonical direction. Not radiometric temperature (the MP4s can't support it) and not identity.

[thermal-cameras memory note]: the 108/109 cams are AGC white-hot (not radiometric), 1 fps, out of prior
scope; OSD clock ~1 h behind filename.
