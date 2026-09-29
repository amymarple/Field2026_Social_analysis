# Rigid-landmark labels, cohort 2026c

Human labels exported from `cv/cv_field/landmark_gui.py` (one JSON per camera frame:
`landmarks_<CH>_<YYYYMMDD_HHMMSS>.json`, full-resolution UPRIGHT pixels). They anchor the correction from cohort-3
pixels to the calibration-epoch pixels of the 2026-09-24 calibration (plan:
`implementation_plan/2026-09-28-cohort3-camera-stability.md`; why: `change_log/2026-09-28-cohort3-camera-stability.md`).

- **Fit set (rigid):** `POLE_<row><col>_L` / `_R` (a pole is a vertical cylinder: its LEFT and RIGHT edge as seen in
  the image, two parallel lines — more points, and their spacing measures the image scale; paddock grid names A–C × 0–4), `WALLTOP_*` (top edge of
  the wall sheet, per side), `TOWER_1` / `TOWER_2` (the two water towers outside the paddock: TOWER_1 beyond the row-C wall, y = 240 — the
  top of the schematic; TOWER_2 beyond the row-A wall, y = 0 — the bottom; user 2026-09-29), `BOX_<pole>` (the box on each pole =
  a WISER UWB anchor), `PCBOX` (the PC box facing CH02), and any added structure
  that cannot move.
- **Validation only:** `HOUSE_B1_*` / `HOUSE_B3_*` — the house next to pole B1 / B3 — as `_ROOF` (outline) and `_BASE`
  (visible bottom edge). No record says whether the houses moved, so they check the correction instead of shaping it.
  (Named by the pole, not house_1/house_2, because the documents disagree on which is which.)
- **Which name is which:** `paddock_schematic.png` here (top view: A0 = origin corner, x along the 40 ft length with
  columns 0–4, rows A/B/C across; wall sides; houses; each camera's position and bearing from the 09-24 calibration),
  and the named dashed "NAME?" guides in the GUI = the calibration's prediction of each structure (identification
  only — click the real structure). Both from `cv/cv_field/landmark_guides.py`; annotated 09-18 IR frames per camera:
  `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_landmarks/guides_CH0x_0918IR.jpg`.
  Visible per camera (calibration): CH03 → POLE_A0/B0/C0, WALLTOP_X0/Y0/Y240; CH04 → POLE_A4/B4/C4, WALLTOP_X480/Y0;
  CH01 → mostly rows B/C (+A0), all four wall tops, both houses; CH02 → mostly rows A/B (+C4), WALLTOP_X0/X480/Y0,
  both houses.
- Same name = same physical structure in every frame and camera. Outlines/edges are compared point-to-curve, so
  clicks do not have to correspond point by point.

First frames to label (the 09-18 IR references, same session as the calibration): CH01 2026-09-18 13:57:30,
CH02 15:22:30, CH03 15:45:00, CH04 14:32:30. GUIs:
`python cv/cv_field/landmark_gui.py CH02 "2026-09-18 15:22:30" --cohort 2026c`
→ `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_landmarks/landmark_gui_CH02_20260918_152230.html`.
Cohort frames follow once the event-pair review has fixed the epoch boundaries; open them with
`--guide <the 09-18 export of the same camera>` to see the reference labels as dashed lines.
