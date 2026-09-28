# Rigid-landmark labels, cohort 2026c

Human labels exported from `cv/cv_field/landmark_gui.py` (one JSON per camera frame:
`landmarks_<CH>_<YYYYMMDD_HHMMSS>.json`, full-resolution UPRIGHT pixels). They anchor the correction from cohort-3
pixels to the calibration-epoch pixels of the 2026-09-24 calibration (plan:
`implementation_plan/2026-09-28-cohort3-camera-stability.md`; why: `change_log/2026-09-28-cohort3-camera-stability.md`).

- **Fit set (rigid):** `POLE_<row><col>` (pole centre line, paddock grid names A–C × 0–4), `WALLTOP_*` (top edge of
  the wall sheet, per side), `TOWER` (water tower outline), `PCBOX` (the PC box facing CH02), and any added structure
  that cannot move.
- **Validation only:** `HOUSE_<n>_ROOF` (outline), `HOUSE_<n>_BASE` (visible bottom edge) — no record says whether
  the houses moved, so they check the correction instead of shaping it.
- Same name = same physical structure in every frame and camera. Outlines/edges are compared point-to-curve, so
  clicks do not have to correspond point by point.

First frames to label (the 09-18 IR references, same session as the calibration): CH01 2026-09-18 13:57:30,
CH02 15:22:30, CH03 15:45:00, CH04 14:32:30. GUIs:
`python cv/cv_field/landmark_gui.py CH02 "2026-09-18 15:22:30" --cohort 2026c`
→ `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_landmarks/landmark_gui_CH02_20260918_152230.html`.
Cohort frames follow once the event-pair review has fixed the epoch boundaries; open them with
`--guide <the 09-18 export of the same camera>` to see the reference labels as dashed lines.
