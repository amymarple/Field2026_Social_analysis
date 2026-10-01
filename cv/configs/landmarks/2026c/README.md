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
- **Validation only:** `HOUSE_1_*` = house_1 (next to pole B1, under CH05; WISER ROI `house_1`) and `HOUSE_2_*` =
  house_2 (next to pole B3, under CH06; WISER ROI `house_2`), as straight edges sorted by 3-D direction (user, 2026-10-01: no closed outline that
  cannot extend): `_ROOF_X` / `_ROOF_Y` = roof edges parallel to the paddock x / y axis, `_BASE_X` / `_BASE_Y` =
  bottom edges parallel to x / y, `_BASE_Z` = the vertical corner edges; one piece per visible straight edge, the
  same edges in every frame. A category holds up to ~3 edges that need NOT be parallel (e.g. the two sloped gable
  edges; user, 2026-10-01): each piece is its own straight line, matched to the nearest same-category line in
  another frame. Only truly parallel 3-D edges share a vanishing point (a distortion check for those).
  No record says whether the houses moved, so they check the correction instead of shaping it. (Briefly named
  HOUSE_B1/B3 on 2026-09-29; the GUI migrates such labels. What IS disputed is which in-box camera sits in which
  house: `field_layout.json` says CH07 → house_1, CH08 → house_2; the recording repo's COLOUR_SAMPLING_LOG says
  CH07 = house_2, CH08 = house_1.)
- **Which name is which:** `paddock_schematic.png` here (top view: A0 = origin corner, x along the 40 ft length with
  columns 0–4, rows A/B/C across; wall sides; houses (HOUSE_1 / HOUSE_2); each camera's position and bearing from the 09-24 calibration),
  and the named dashed "NAME?" guides in the GUI = the calibration's prediction of each structure (identification
  only — click the real structure). Both from `cv/cv_field/landmark_guides.py`; annotated 09-18 IR frames per camera:
  `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_landmarks/guides_CH0x_0918IR.jpg`.
  Visible per camera (calibration): CH03 → POLE_A0/B0/C0, WALLTOP_X0/Y0/Y240; CH04 → POLE_A4/B4/C4, WALLTOP_X480/Y0;
  CH01 → mostly rows B/C (+A0), all four wall tops, both houses; CH02 → mostly rows A/B (+C4), WALLTOP_X0/X480/Y0,
  both houses.
- **Only what is visible (user, 2026-10-01):** never draw an estimated or guessed line — an edge hidden by grass
  (e.g. a house base) or by anything else is left out, or only its visible stretches are drawn. A missing line
  costs nothing; a guessed one is a false measurement. (Same reason the wall FOOT is not used.)
- **Hidden middle → pieces:** a wall seen only at both ends, or a pole edge cut by something in front, is labelled as
  separate PIECES of the same landmark (press `b` in the GUI between them); nothing is joined across a gap. Export
  format: `landmarks[name]` = list of pieces, each a list of `[u, v]` (`"format": "pieces"`); an outline is closed
  only when it is one piece. The calibration guides follow the same convention.
- Same name = same physical structure in every frame and camera. Outlines/edges are compared point-to-curve, so
  clicks do not have to correspond point by point.

First frames to label (the 09-18 IR references, same session as the calibration): CH01 2026-09-18 13:57:30,
CH02 15:22:30, CH03 15:45:00, CH04 14:32:30. GUIs:
`python cv/cv_field/landmark_gui.py CH02 "2026-09-18 15:22:30" --cohort 2026c`
→ `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_landmarks/landmark_gui_CH02_20260918_152230.html`.
Cohort frames follow once the event-pair review has fixed the epoch boundaries; open them with
`--guide <the 09-18 export of the same camera>` to see the reference labels as dashed lines.
