# Implementation plan (PARKED) — Stage 2: CV motion to resolve the boundary/leg question WISER couldn't

**Status:** ⛔ BLOCKED — waiting on the user's CV pipeline (`C:\Users\Cornell\Documents\CV`) to be
finished. Do not start until the user says the pipeline is ready. This file captures the plan +
handoff contract so we resume cleanly. Falsification-first, same discipline as the WISER validations.

## Why Stage 2 exists

The decision-boundary validation (Stage 1) concluded WISER **cannot** resolve reorientation at pauses:
pauses are intrinsically low-displacement, and WISER measures **position only**, so heading (inferred
from displacement) is jitter at pauses. `decision_boundary_validation/validation_report.md`. The open
question — do rats have finer behavioral structure (reorientation decisions, decision-to-decision legs)
below WISER's resolution — is a **higher-resolution-motion** question, to be answered from CV.

## Dependency: the user's CV pipeline (cross-referenced 2026-07-11)

At `C:\Users\Cornell\Documents\CV` (a separate repo the user is actively building):
- `nightcv/` — **night-IR centroid detection + tracking** for CH01/CH02 (MOG2 motion proposals + shape
  gating + IoU tracks + optional DINOv2 prototype classifier). Validated 2026-07-10 (CH01+CH02, 07-03).
- Output contract: `night_out/<CH>_<date>/{detections.csv, tracks.csv, qc/, crops/}` → `scripts/to_field.py`
  (adds field-cm) → `scripts/merge_field.py` → one common-frame cm table, `animal_id = <camera>:<track_id>`
  (no cross-camera dedup yet). **Field frame = origin pole A0, x 0–1219.2 cm, y 0–609.6 cm** (same physical
  frame as `cv`).
- Calibration: 2nd-order poly fits — CH01 55.9 / CH02 51.3 / CH03 19.7 / CH04 11.3 cm RMSE. Their own
  "Stage 2" (`docs/stage2-intrinsics-refit-plan.md`) is an intrinsics refit → CH01/CH02 ~15–20 cm.
- It is **CENTROID / bbox, NOT pose / keypoints.**

## The honest resolution problem (decides whether Stage 2 is even feasible)

Centroid at ~15–20 cm ≈ WISER's ~18 cm jitter, and centroid heading is still displacement-based → it
likely will **not** out-resolve the pause-reorientation question by itself. The candidate resolvers, to be
tested at the feasibility gate:
1. **Temporal**: ~20 fps vs 4.4 Hz — finer leg segmentation even at similar per-point jitter.
2. **Body-axis from detection shape** (bbox/blob elongation axis) — orientation independent of translation
   = the exact thing WISER lacked; the cheapest route to "turning in place at a pause."
3. **Close-up cams** (CH05/CH06 shelter, CH07/CH08 in-house) where the rat spans many pixels → real body-axis.

## Plan (resume when the pipeline is ready) — feasibility gate FIRST

- **Phase 0 (gate):** measure the CV instrument the way we measured WISER's 7 in floor — per-camera
  centroid (and, if available, body-axis) noise on a resting animal, and effective fps. Define the
  resolution bar from WISER pause geometry. If CV also can't clear it, say so.
- **Phase 1:** hand-label a small night-IR clip set of human-visible pause-and-turn events + matched
  continuous controls (the ground truth WISER never had).
- **Phase 2:** consume `merge_field` cm tracks (+ body-axis from bbox if derivable) on those clips.
- **Phase 3:** re-run the Stage-1 boundary battery (matched CEM turn test + noise null + well-resolved
  restriction) with the CV noise floor; head-to-head vs WISER on the same events.
- **Phase 4 gate:** only if CV clears the bar → build the deferred decision-boundary Stages 2/3
  (leg segmentation → old-bout-vs-leg unit comparison → leg vocabulary → transition policy) on CV tracks.

## Cross-cutting

- **Georeference (WISER→field cm)** still needed to compare WISER route motifs vs CV tracks (CV is already
  in cm; WISER is inch/unverified). `wiser_to_field_transform.json` = confirmed:false. Parallel prerequisite
  for the motif-vs-CV roadway audit (spawned task) but NOT for the single-camera CV boundary test.
- Reuse the Stage-1 harness: `decision_boundary_validation/src/{matched_controls,noise_simulation}.py`
  (swap the WISER jitter floor for the CV one).
- New work lands in `wiser/cv_motion_validation/` (mirrors prior validation dirs);
  the user's CV repo stays the source of tracks.

**Resume trigger:** user confirms the CV pipeline is done. Then start at Phase 0.
