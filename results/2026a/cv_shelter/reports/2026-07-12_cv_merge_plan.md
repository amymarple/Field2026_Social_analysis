# CV reconciliation — merge PLAN (no merge performed)

**Date:** 2026-07-12 · **Status:** PLAN ONLY. The actual merge is a separate approved task.

Compares the migrated shelter-CV pipeline (`cv/`, formerly `preprocessing/computer_vision/`) against the
user's newer standalone CV project at `C:\Users\Cornell\Documents\CV` (copied untouched to
`staging/cv_attempt/`; its multi-GB frame/output dumps stay at the source — see
`staging/cv_attempt/_NOT_COPIED_bulk_outputs.txt`).

## What each is

**`cv/` (migrated, this repo).** Daytime through-glass **shelter occupancy** for CH05/CH06: `shelter_sleep.py`
(zone-aware inside/doorway/outside + per-zone `view_quality`), `validate_shelter.py` (ground-truth check
stratified by view quality), the glass/regime covariate stack (`glass_regime.py`, `view_quality.py`,
`fog_risk.py`, `measurement_context.py`, `stripe_flow.py`), the YOLO detector loop
(`scan_for_rats.py` → `label_frames.py` → `train_detector.py`, hand-labeled `dataset/rat` + `runs/detect`
weights, off-repo assets), and the calibration/field-cm authoring tools (`field_coords.py`, `calibration.py`,
`intrinsics.py`, `place_cameras.py`, `merge_cameras.py`).

**`staging/cv_attempt/` (`C:\...\CV`).** A newer, frame-accurate **night-IR whole-field tracking** pipeline,
self-described as the replacement for the old extraction code. Not a git repo. Stages (evidence:
`cvpipe/`, `nightcv/`, `scripts/`, `DIAGNOSIS.md`):
`cvpipe.probe`/`sanity` (GOP/VFR/NVDEC facts + the capped-2 MB-keyframe / partial-frame diagnosis) →
`cvpipe.extract` (time-based accurate seeks; frame-number addressing banned) →
`nightcv` MOG2 motion + shape-gate + IoU tracks + optional DINOv2 prototype classifier (**centroid, not
pose**) → `filter_tracks`/`rescue_stationary` → `cvpipe.field` / `to_field` → `merge_field` (one common
field-cm table, `animal_id=<camera>:<track_id>`, no cross-camera dedup yet). Validated 2026-07-10 on
CH01/CH02 (~3.2× realtime; field-cm port reproduced ±0.1 cm).

## Overlap & who is ahead (file evidence)

| Area | `cv/` (migrated) | `staging/cv_attempt/` | Ahead |
|---|---|---|---|
| Frame extraction | `extract_clip.py` (basic) | `cvpipe/extract.py` + `sanity.py` + `DIAGNOSIS.md` (capped-GOP/VFR/NVDEC) | **cv_attempt** |
| Calibration / intrinsics **authoring** | `calibration.py`, `intrinsics.py`, `field_coords.py`, `place_cameras.py` (source of the calibs) | `configs/CHxx_calib.json` **ported from the old repo** ("reused as-is") | **cv/** (authors); cv_attempt has a validated runtime port |
| Detection / tracking | YOLO daytime whole-field + shelter | night-IR MOG2+IoU+DINOv2 centroid, CH01/CH02 | **complementary** (day-shelter vs night-field), not duplicative |
| Fog / glass quality | `fog_risk.py`, `glass_regime.py`, `view_quality.py`, `measurement_context.py` | `fog_*` scripts, `glass_observation.md`, `fog_ch05_*` | **cv/** (richer regime/measurement-context machinery) |
| Shelter occupancy CH05/CH06 | `shelter_sleep.py`, `validate_shelter.py` | CH05/CH06 calibs only, no shelter-occupancy detector | **cv/** (unique) |
| Multi-camera field merge | — | `scripts/merge_field.py` common-frame table | **cv_attempt** (unique) |
| Video-integrity method docs | `docs/methods/duo3_keyframe_2mb_cap.md` | `DIAGNOSIS.md` | overlap (consistent) |

## Recommended combination

Treat them as **two regimes of one CV frame**, not competitors:

1. **Adopt `cv_attempt`'s extraction + sanity front-end** (`cvpipe.probe/extract/sanity`) as the canonical
   decode path for *both* pipelines — it correctly handles the capped-GOP/VFR/NVDEC issues the old
   `extract_clip.py` does not (this repo's `docs/methods/duo3_keyframe_2mb_cap.md` already documents the same
   root cause).
2. **Keep `cv/` as the authoritative calibration/intrinsics + shelter-occupancy owner.** `cv_attempt` already
   consumes `cv/`'s calibs; formalize `cv/` as the source and have `cv_attempt` import them, not fork them.
3. **Add `cv_attempt`'s night-IR field tracking + `merge_field` as the `cv_field` capability** (whole-field
   CH01–CH04 tracks → field-cm), feeding `results/<cohort>/cv_field/` and the WISER×CV cross-modal
   reconciliation. Shelter occupancy stays `cv_shelter`.
4. **Unify fog/quality**: fold `cv_attempt`'s `fog_*` probes into `cv/`'s richer `measurement_context` /
   `view_quality` / `fog_risk` covariate stack (one regime layer, not two).
5. Land it in this repo's cohort schema: `cv/` (shelter) + a new `cv_field/` (night-field) under one `cv/`
   umbrella, both cohort-parameterized via `common/output_paths.py`; directions `cv_shelter` + a new `cv_field`.

## Risks

- **Calibration divergence:** `cv_attempt` ported `cv/`'s calibs; if either edits them independently the
  field-cm frames drift. Mitigate by making `cv/` the single calib source before merging.
- **No cross-camera identity** in `merge_field` yet (`animal_id=<camera>:<track_id>`) — do not claim
  whole-field per-animal trajectories until dedup exists.
- **Regime mismatch:** night-IR tracking and day through-glass shelter occupancy have different failure modes;
  keep their `view_quality`/regime tagging separate even under one umbrella.
- **Not a git repo:** `C:\...\CV` is unversioned; capture its exact state (the `staging/cv_attempt/` copy) as
  the merge baseline before any edits.
- **Env/GPU:** `cv/` needs the `cv` conda env (cu128, sm_120, `--batch 1`); verify `cv_attempt`'s NVDEC path
  under the same env before merging.

**Next:** a separate approved merge task starting from `staging/cv_attempt/` as the baseline. No code merged here.
