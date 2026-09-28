# Thermal warm-blob (rat) detector — unsupervised, AGC-robust

**Date:** 2026-07-13
**Status:** Phase 0 — code + offline self-test + prototype run on real video. No labels, no validation yet.
**New subsystem:** `thermal/` (first code to touch the 108/109 thermal cameras; see [[thermal-cameras-108-109]]).
**Direction:** not yet a canonical research direction — this is exploratory tooling. If promoted, it would add
a `thermal_*` direction key, an `analyses/` card, and `output_paths`/`measurement_context` wiring. Until then
outputs land in a caller-chosen `--out` (scratchpad), NOT under `results/`.

## Motivation

The 108/109 thermal cameras record the paddock at 1 fps, 1280×960, HEVC, white-hot **monochrome**. They are
**auto-gain-controlled (AGC)**: the gray→temperature mapping is re-scaled every frame (see the burned-in
colorbar min/max), so absolute pixel brightness is not comparable across frames, and the video is **not
radiometric** (no per-pixel temperature). At night, rats are warm and image as compact bright blobs — thermal
is often a *cleaner* night signal than IR video. Goal: an **unsupervised, label-free** detector (user asked to
avoid a labeling tool) that finds and tracks warm blobs, so we can later decide whether thermal is worth a
canonical direction.

## Design (why each piece)

Per-frame pipeline, deliberately AGC-robust and MOG2/CLAHE-free (both amplified noise or fought the AGC):

1. **OSD mask.** Zero out the burned-in overlays (timestamp, colorbar + labels, 'Thermal' text) by filling
   with the frame **median** (not 0 — a dark hole makes the top-hat paint a bright rim), then drop any blob
   whose centroid/≥30% area falls in the OSD region dilated by the top-hat scale.
2. **White top-hat** (`gray − opening`, elliptical SE ≈ larger than a rat). A **local** operator → inherently
   robust to the per-frame global gain. This is the core "bright-blob" cue.
3. **Threshold** (Otsu + absolute floor) → **morphology** (open/close) → **connected components**.
4. **Geometry filter** — area ∈ [min,max], extent (area/bbox), aspect — rejects the thin survey **pole** and
   the thin spot-meter **crosshair**.
5. **Learned static-structure suppression.** Accumulate a persistence map of the top-hat foreground; pixels
   foreground in > `static_persist_frac` of frames (after `static_warmup`) are **static** (the pole, fixed hot
   structures) and are **erased from the binary mask**. Key effect: a rat sitting *on* the pole then
   **separates** into its own compact component instead of merging into a rejected pole shape.
6. **Motion score** — light frame-difference, recorded per blob (informational, never a hard gate, so a
   stationary/huddled rat is still kept on brightness alone).
7. **Tracker** — greedy nearest-centroid with short gap tolerance → short tracks; tracks < `track_min_len`
   dropped, which also suppresses single-frame flicker false positives.

Frames are read via an **ffmpeg gray pipe** (robust for network HEVC), not OpenCV's codec build.

## Outputs (candidate-only, explicit non-claims)

`detections.csv`, `tracks.csv`, `summary.json` (+ optional annotated preview PNGs/MP4). Every output carries:
- **NOT temperature** (AGC render, not radiometric) and **NOT animal identity** (thermal has no coat pattern).
- Camera OSD clock runs **~1 h behind** the filename time — cross-modality alignment stays unverified.
- **Unsupervised + unvalidated**: precision/recall unknown; huddled/cool rats may be missed; warm field edges /
  glare / condensation may create blobs.

## Scope / plan

- **Phase 0 (this change):** `thermal/detect_blobs.py` + `--selftest` (synthetic AGC sequence: drifting gain,
  static pole, OSD blocks, moving crosshair, two moving gaussian "rats"; asserts recall, precision, pole+
  crosshair rejection, ≥2 persistent tracks). Prototype run on `108_thermal 2026-07-01 21:00`. Parameters
  (overlay boxes, top-hat SE, area bounds) tuned from a characterization sweep across 108/109 × night hours.
- **Deferred:** a label-free evaluation (e.g. manual spot-audit of N sampled detections for a precision
  estimate; temporal-consistency / track-length sanity), 109 viewpoint, cross-check vs WISER/CH cams (blocked
  by the clock offset + unverified frames), and any promotion to a canonical direction.

## Non-goals

No radiometric temperature extraction (the MP4s cannot support it). No identity. No behavioral claim. No
change to `cv/`, `wiser/`, or any existing direction.
