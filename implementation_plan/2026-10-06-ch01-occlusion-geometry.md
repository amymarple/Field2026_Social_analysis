# CH01 occlusion geometry: which WISER-flagged misses are hidden by a pole or a house

Date: 2026-10-06. Status: **DONE 2026-10-06** (approved "行上吧" 2026-10-06; run
`$OUT/2026c/cv_field_ch01_occlusion_20261006_1445`, report `results/2026c/cv_field/reports/cv_field_ch01_occlusion_2026c.md`;
amendment 1 before results, 2 after results, descriptive only; per-episode classes sealed). Pre-registered before any result;
amendments dated and marked *before* or *after results*. Data locations: `cv/cv_field/DATA_MAP_c1yolo_wiser.md`.

## Why

The user reviewed the phase-0 review clips (`2026-10-05-wiser-assisted-yolo-p0.md`, amendment 4) and saw that part
of the CV misses are animals hidden by a house or a pole (user, 2026-10-06). A suspected miss behind an occluder is not
a detector error and must never become a box (`LABELING` rule: only what is visible). Separating "geometrically hidden"
from "in clear view but missed" turns the 300 suspected-miss episodes into (a) a list of real detector failures for
labelling and (b) a per-camera visibility mask that later analyses (occupancy, CH01/CH02 coverage) need anyway.

## Inputs (read-only)

- Phase-0 run `$OUT/2026c/cv_field_wiser_assist_p0_20261005_2211/`: `mapping.json` (accepted WISER → paddock map,
  similarity, L = 0), `fn_episodes.csv` (300 episodes), the per-second miss table the episodes were built from,
  `support_polygon.json`.
- WISER default tracks SF07–SF12, 2026-09-06 (`wiser/src/default_tracks.py`), as in phase 0.
- Camera: `../Field_2026_Social_Recording/calibration_qc/` — the frozen FINAL calibration (release 2026-10-03, rev g,
  frozen 10-04), at the recording-repo commit recorded in the run JSON (phase 0 used `a667cfe`). CH01's camera
  centre = `RayCamera.centre` of `paddock_map.load()["CH01"]` (paddock mm).
- Occluders:
  - **Poles**: vertical cylinders, 2.4 m tall. Positions = the calibration's measured pole centre lines where the pole
    check (`calibration_qc/pole_check.py`, `session_2026-09-18_pole_check.txt`) gives them, else the design grid of
    `cv/configs/field_layout.json` (10-ft grid, A/B/C × 0–4). Radius = perimeter / 2π from
    `calibration_qc/survey_2026-10-03.json` (B1 18.5, B2 16.5, B3 17.5 in → 2.6–2.9 in); other poles: the mean.
  - **house_2** (roof 7, never moved): rigid box from `calibration_qc/HOUSE_CHECK_2026-10-04_revg.txt` — centre
    (342.4, 117.7) in, ridge 92.0° from x, footprint 62.55 × 45.72 cm, eaves 60.8 cm, ridge 87.8 cm (gable roof).
  - **house_1** (roof 4): **moved on 09-18**, so the calibration's position (147.5, 121.7) in is post-move and not
    used. Cohort position = WISER ROI `house_1` (`wiser/configs/wiser_rois.json`) through the accepted map; same
    footprint and heights (eaves 59.0, ridge 88.2 cm). Cross-check (reported, not used to place it): the CH01 cohort
    labels `landmarks_CH01_20260904_120002.json` (`HOUSE_1_*` edges) against the placed box, in pixels. The same map
    check is done for house_2 (WISER ROI through the map vs the calibration's position), as a check of the map.

## Method

1. **Rat model.** Each animal = its WISER position mapped to the paddock (accepted map), taken as a short vertical
   segment at heights 30 / 60 / 90 mm (body) and ± 40 mm across the line of sight (body half-width).
2. **Visibility.** For each sample point, the segment from CH01's camera centre to the point; a point is hidden if the
   segment passes through a pole cylinder or the house box (with the gable roof). Hidden share h = fraction of the
   9 sample points (3 heights × 3 lateral offsets) hidden.
3. **Classes per second:** *hidden* (h ≥ 0.8), *partly hidden* (0 < h < 0.8), *clear* (h = 0); with the occluder id.
   **WISER uncertainty:** the same test with the animal moved by 7 in in 8 directions; a second is *robustly clear*
   only if clear in all 9 positions, *robustly hidden* only if hidden (h ≥ 0.8) in all 9; otherwise *ambiguous*.
4. **Per episode:** shares of hidden / partly / clear / ambiguous seconds; episode class = the majority class
   (ties → ambiguous).
5. **Visibility mask:** a 2-in paddock grid over CH01's support, the hidden share for a rat at each cell (same rat
   model), per occluder → `visibility_mask.npz` + figure (shadows of each pole and house as seen from CH01).
6. **Checks.** House boxes and pole cylinders projected into the CH01 cohort frame (via the calibration and the
   inverse frame correction) against the user's landmark labels (`landmarks_CH01_20260904_120002.json` for house_1,
   `landmarks_CH01_20260918_135730.json` for house_2 and the poles): median pixel distance from the projected
   silhouette edges to the labelled edges, per object. Reported; if an object is off by more than 20 px, its
   results are flagged (not refitted).

## Outputs and blinding

- Run folder `$OUT/2026c/cv_field_ch01_occlusion_<ts>/`: `seconds.csv.gz` (per suspected-miss second: animal, paddock
  x/y, h, class, occluder, robustness), `episodes.csv` (sealed, see below), `visibility_mask.npz`, `occluders.json`
  (every object's position and size with its source), `checks.csv`, `run.json`.
- **Blinding:** the user is filling `review_template.csv` of the phase-0 review clips (59 episodes: visible_missed /
  occluded / not_there_wiser_wrong / box_present / unsure). The per-episode geometry classes stay in the run folder
  and out of the report until those verdicts are in; then a separate step tabulates geometry class vs user verdict
  (the test of this geometry). Pooled numbers over all 300 episodes (shares hidden / partly / clear / ambiguous, by
  occluder) and the visibility mask are reported at once — they do not reveal individual clips.
- Report `results/2026c/cv_field/reports/cv_field_ch01_occlusion_2026c.md`, figures
  `results/2026c/cv_field/figures/ch01_occlusion/`, pointer `run_manifest_ch01_occlusion_2026c.json`. Code
  `cv/cv_field/ch01_occlusion.py` with `--selftest` (synthetic camera, cylinder and box: known hidden / clear points,
  partial cases, the 7-in perturbation). Afterwards: change_log, both index READMEs, CLAUDE.md cv_field map,
  `cv/cv_field/HANDOFF.md`, data map.

## Rules

The agent never judges images. Geometry says "hidden"; it never makes a label — a hidden animal gets no box, and a
"clear" suspected miss is still only a proposal for the user. Grass, other rats and the animal's own posture are not
modelled (they can hide a "clear" animal). One hour, one camera; CH02 follows only if the user asks. The recording-repo
files are read, never modified.

## Cost

CPU, minutes (≈ 3 500 miss seconds × 9 positions × 9 sample points × ~17 objects; the mask ≈ 25 000 cells).

## Amendments

### Amendment 1 — 2026-10-06, *before results*: pole sources and implementation clarifications

Written after the code, its synthetic self-test and the pole re-measurement (an input), before any occlusion class was
computed. Recording repo read at `a667cfe` (no pull; the same calibration files as phase 0).

1. **Poles.** `session_2026-09-18_pole_check.txt` dates from 2026-10-01, before revisions e–g, so the pole check's method
   (`pole_check.py`: per camera and height, the axis offset across the line of sight from the operator's 09-18 L / R
   pole-edge labels; per height, the least-squares crossing of ≥ 2 cameras' lines) is re-run read-only on the frozen
   rev g cameras (CH01–CH04 labels, + the IR → colour offset house_check uses). A pole's measured line is used if: ≥ 2
   heights each crossed by ≥ 2 cameras at ≥ 10° (camera residual ≤ 50 mm with ≥ 3 cameras); a straight line in height
   through them with residuals ≤ 50 mm; its 1.05-m point ≤ 400 mm from the design grid; and a lean ≤ 15° (this last
   bound was added after seeing the pole table: it removes only A4, whose two-height line leaned 23°). Else the
   vertical design-grid line of `cv/configs/field_layout.json`. **Sources used:** measured (CH01 + CH02) for **B1, B2,
   B3** (crossing 29.5°, 17.0°, 32.0°; 5 / 5 / 3 heights; leans 9.5°, 3.7°, 6.4°; at 1.05 m their spacings agree with
   the operator's tape: B1–B2 ≈ 119.8 in vs 120, B2–B3 ≈ 117.3 in vs 116); **design grid** for A0, A1, A2, A3, A4, B0,
   B4, C0, C1, C2, C3, C4 (fewer than 2 clean heights, or A4's lean). Each pole is a capsule from the local ground to
   2.4 m above it (measured lines extrapolated beyond their measured heights); radius = perimeter / 2π for B1–B3, the
   mean of those (70.7 mm) for the others.
2. **Houses** = `house_check.py`'s rigid model from the survey: body box (footprint 62.55 × 45.72 cm) from the soil to
   the eave height + a gable-roof prism with the 66-cm ridge and the eave lines ± run from the ridge (the roof
   overhang), in the calibration's absolute z: house_2 at the rev g pose (342.4, 117.7) in, ridge 92.0°, soil 93 mm below
   the calibration's z = 0; house_1 at the WISER ROI centre through the accepted map, ridge = the ROI's 90° + the map's
   θ, soil 58 mm below z = 0 (its own house-check fit; the house sat ≈ 9 in from there before the move).
3. **Rat and camera z**: the calibration's absolute datum (camera centre; terrain under each rat point + 30 / 60 / 90 mm).
4. **Per-second category** (the four the plan names): hidden = robustly hidden; clear = robustly clear; partly = nominal
   0 < h < 0.8; ambiguous = otherwise (nominally hidden or clear but a 7-in move changes it). Occluder of a second = the
   object blocking the most sample points summed over the 9 positions; of an episode = the most frequent occluder of its
   non-clear seconds. The suspected-miss seconds analysed = all 3 482 (in or out of ≥ 3-s episodes); episodes use theirs.
5. **Per-second table.** Not saved by phase 0; rebuilt with the phase-0 code unchanged in substance: the box
   preparation was moved verbatim from `run_pipeline` into `wiser_assist_p0.prepare_boxes`, and `part_c` gained an
   optional `seconds_out` that only reports its arrays. Accepted only if the regenerated `fn_episodes.csv` is
   byte-identical to phase 0's.
6. **Checks.** 09-18 labels compared in 09-18 px (+ the IR → colour offset); the 09-04 cohort house_1 labels → 09-18 px
   with `Corrections.to_09_18` at the label time, which for a 12:00 frame uses the nearest night sample (09-04 21:00);
   the daily 12:00 landmark track of that frame is reported next to it. Projected edges use the calibration's own
   inverse, each point verified to 0.02°. Also reported, as a check of the projection code only: the calibration's
   post-move house_1 against the 09-18 labels.
7. **Blinding.** `episodes.csv` and `seconds.csv.gz` (it carries episode ids) are sealed in the run folder
   (`SEALED_README.txt`); report, figures and messages carry pooled numbers and the mask only.

### Amendment 2 — 2026-10-06, *after results*: descriptive additions only (no class, threshold or object changed)

1. The report's by-occluder tables name each occluder's source and its own landmark-check status (flagged objects:
   poles A0, B0, B2, C0, C1 and house_1; B1, B3, house_2 within 20 px; poles without CH01 labels "not checked").
2. Per suspected-miss second, whether its 7-in ring crosses a paddock wall (the perturbed positions are not clipped):
   pooled, 30 % of the ambiguous seconds; it explains the wall-line poles (C2, C1, B4) among the occluders.
3. Why B2 is flagged: CH01 and CH02 see it from nearly opposite sides (17° from collinear), so its position along that
   line is poorly constrained; its 45 px ≈ 1° ≈ 15 mm at 0.82 m. A diagnostic exact-ray triangulation (not used) was far
   less stable. Per the plan, B2 is flagged, not refitted; a single-camera range from CH01's own edge width and the
   surveyed radius would be the follow-up if wanted.
4. The 09-04 label correction (night sample 09-04 21:00) and the daily 12:00 landmark track differ by ≈ 5 px at the frame
   centre — immaterial next to house_1's 125-px miss.
