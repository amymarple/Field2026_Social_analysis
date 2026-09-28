# thermal/ — unsupervised warm-blob (rat) detector for the 108/109 thermal cameras

First code to touch the field's **thermal** cameras (`108_thermal`, `109_thermal`; paired with
`108_visual`/`109_visual`). See the memory note on [thermal camera nature](../implementation_plan/2026-07-13-thermal-warm-blob-detector.md)
and the plan for context. **Status: Phase 0 prototype — unsupervised, unvalidated, candidate-only.**

## What the data is (and what it is not)

The thermal MP4s are **1 fps, 1280×960, HEVC, white-hot monochrome, auto-gain-controlled (AGC)**: the
gray→temperature mapping is re-normalized *every frame* (watch the burned-in colorbar min/max move). So:

- **Absolute pixel brightness is NOT a stable temperature** — a fixed gray maps to a temperature that
  drifts a few °C frame-to-frame, and when a warm animal enters, the whole scene darkens as the scale
  stretches. Detection must use **per-frame local contrast**, never a global gray threshold.
- The video is **not radiometric** (no per-pixel temperature array). The only temperature info is the
  burned-in colorbar endpoints and the moving spot-meter readout.
- The burned-in **OSD clock runs ~1 h behind the filename time**. Timestamps here use the frame index +
  filename wallclock only — never parse the OSD clock.

## What the detector does

Per-frame, AGC-robust pipeline (`detect_blobs.py`), MOG2/CLAHE-free:

1. **Overlay guard** — mask the static OSD (timestamp, colorbar+labels, 'Thermal') + a 6 px border, plus a
   **dynamic red-chroma mask** of the moving spot-meter crosshair and its white readout text (it tracks the
   hottest pixel and roams onto warm structures, so a static mask can't catch it; the diamond sits *on* the
   true rat, so only a tight rightward text box is masked).
2. **White top-hat** on the luma — a *local* operator, inherently robust to the per-frame AGC gain.
3. **Robust-adaptive threshold** — `T = max(floor=45, median+5·1.4826·MAD)`. **Not Otsu** (Otsu invents a
   foreground in the majority-empty frames). The floor is the single most important knob.
4. **Morphology** (open r=3, close r=7) → **connected components** → **geometry filter**
   (area∈[120,4500] px², aspect ≤ 4.5, extent ≥ 0.35, solidity ≥ 0.5, mean-response ≥ 0.5·floor).
5. **Static-structure suppression** — pixels persistently foreground **and** part of a LARGE/ELONGATED
   component (pole, wires, berms) are erased before components, so a rat on the pole *separates* into its
   own blob. Compact persistent blobs (a possible resting rat) are **not** erased. (On real data the pole
   is mostly handled by the aspect filter; the learned mask mainly catches large persistent structure.)
6. **Motion score** — frame-difference support per blob (informational, never a gate).
7. **Tracking** — greedy nearest-centroid, 110 px gate @1 fps, short gap tolerance.

## Outputs (all candidate-only)

`detections.csv` (per frame), `tracks.csv` (short tracks, with `mean_tophat` contrast, `path_len_px`,
`net_disp_px`, and a `motion_class` ∈ {moving, stationary_ambiguous}), `summary.json` (params + caveats),
`static_mask.png`, and optional annotated `preview/*.png` + `preview.mp4`.

**Read them as RELATIVE warm-blob detections** — NOT temperature, NOT identity, NOT a certified count.
Counts are a **lower bound** (occlusion / refuge / haze suppress true rats; 0 detections ≠ 0 animals).
`moving` high-contrast tracks are the strongest rat candidates; `stationary_ambiguous` compact blobs are
genuinely indistinguishable (a resting rat vs a sun-warmed rock) without labels.

## Usage

```bash
python thermal/detect_blobs.py --selftest                       # offline synthetic PASS/FAIL (no video/GPU)
python thermal/detect_blobs.py --cam 108_thermal --date 2026-07-01 --hour 21 \
    --out D:/tmp/thermal_run --max-frames 600 --preview
python thermal/detect_blobs.py --video <path.mp4> --out <dir> --preview \
    --tophat-floor 55   # raise the floor to cut warm-berm FPs (at the cost of faint/cool rats)
```

Env: base `python` with OpenCV ≥ 4.12 + numpy (no conda needed). Frames read via an ffmpeg BGR pipe.

## Validating it — WITHOUT supervised learning

The labels below are for **measuring and threshold-tuning** the unsupervised detector, not for training. If
precision/recall are good after correcting a few dozen frames, no supervised model is needed.

```bash
# 1) run detection on an hour (writes detections.csv)
python thermal/detect_blobs.py --video <mp4> --cam 108_thermal --out D:/tmp/run

# 2) build a pre-filled labeling page (candidate boxes already drawn; samples multi-object frames too).
#    For speed over a network drive, remux the source to a LOCAL copy first and pass that as --video.
python thermal/make_label_set.py --run D:/tmp/run --video <local_mp4> --cam 108_thermal --n-frames 40

# 3) open D:/tmp/run/label_tool.html in a browser. Drag / resize boxes, drag empty area to ADD a missed
#    rat, Delete to remove a false one, "No rats here" for empty frames. Work autosaves; "Export labels"
#    downloads labels.json.

# 4) score the detector against your corrections and get the operating point
python thermal/score_labels.py --labels D:/tmp/run/labels.json --run D:/tmp/run
```

`score_labels.py` sweeps a contrast (`tophat_mean`) threshold and reports precision/recall/F1 at each — pick
the knee, then set `--tophat-floor` there. A `moving`/`stationary_ambiguous` split plus a contrast threshold
is usually enough to separate rats from warm-berm FPs; supervised learning is a fallback only if that fails.

## Known limits (see `summary.json` caveats + the plan's failure-mode list)

Unsupervised & unvalidated — precision/recall unknown; **per-hour threshold sweep + a small human
spot-check are required before any count is trusted**. Warm heat-retaining berms/rocks are the hardest FP
(stationary, compact — flagged `stationary_ambiguous`, not eliminable single-frame). Huddled/cool rats and
rats in the refuge are missed. Right-edge colorbar mask is a declared blind spot. Not georeferenced to the
CV (cm) or WISER (inch) frames. Camera assumed static.

## Thermal TRACES (heat-ghosts) — `trace_feasibility.py` + `detect_traces.py`

A separate goal: not where rats are, but the **warm traces they leave behind** — a resting-spot "heat ghost"
(warmed ground) that appears, PERSISTS after the rat leaves, and DECAYS. `trace_feasibility.py` (Phase 0)
auto-anchors on rat rest-then-depart events and measures annulus-referenced contrast(t) + an exponential
decay fit to answer "is a trace visible, and for how long?" — verified on 2026-07-01: **GO on 108** (ghosts
decay over ~30 s–2 min), **NO-GO on 109** (no lingering warmth; traces are substrate-dependent — warmable
ground vs vegetation). `detect_traces.py` (Phase 1, 108-scoped) promotes that into a detector: rest-then-
depart events → onset + post-departure persistence + exponential-decay acceptance (a flat, never-decaying
structure the rat merely sat by is rejected by decay physics) → candidate **`traces.csv`** event list + a
nightly persistence-weighted **`trace_heatmap.png`**. Run `python thermal/detect_traces.py --selftest`.
Same hard caveats as above **plus**: tau is a RELATIVE-brightness relaxation time (not °C); traces are
candidate resting heat-ghosts, biased toward larger/longer-lived ones — small fast urine deposits are
systematically missed.
