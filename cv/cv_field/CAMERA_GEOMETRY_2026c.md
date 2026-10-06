# Cohort 3 (2026c) camera geometry for tracking: camera motion, house_1's move, landmarks, occluders

For the YOLO / tracking work on cohort 3. It says how the cameras moved, which pixel positions you may trust, where
the rigid structures are and how they are named, and what can hide a rat. Written 2026-10-06 from the landmark work
(plan revision 3 in `implementation_plan/2026-09-28-cohort3-camera-stability.md`; full history in
`change_log/2026-09-28-cohort3-camera-stability.md`). The agent that wrote this does not judge images; every visual
statement below is the user's.

## 1. Rules

1. **Never compare raw pixel positions across days or nights.** Every camera moved — by up to ~30 px a day on CH01/CH02,
   ~90 px over the first days on CH03, and up to 17 px within one night on CH02.
2. **Go through the correction table**, with the detection's field-PC time (`frame_correction.py`, §6):
   - `Corrections("2026c").to_paddock(cam, t, uv)` gives paddock inches for CH01–CH04 and CH06;
   - `to_09_18(cam, t, uv)` gives reference-frame pixels for every camera.
   Always read `info["flag"]`.
3. **The table covers nights only for CH01–CH06** (hourly 21:00 → 04:20, 14 nights). At a daytime time it silently
   returns the nearest night sample. At 09-04 12:00 that is 30 px off on CH02. For a daytime frame run
   `landmark_track.py --times HH:MM --start D --end D --tag …`, which tracks that frame directly from the 09-18 reference
   and writes the affine to `track_frames.csv`. The in-box CH07/CH08 are covered all day.
4. **house_1 (roof number 4, by pole B1) was moved on 09-18**, the calibration day; house_2 (roof 7, by B3) never moved.
   Anything placing house_1 from 09-18 imagery or from the calibration (`field_layout.json` shelter "left", the
   calibration's house fit) is its post-move position and is wrong for the cohort (08-30 → 09-12).
5. **Poles, houses and the food box hide rats.** Their image regions in any frame come from the user's labels mapped
   through the correction (§5). CH05/CH06 hang from the crossbeam on top of pole B1/B3, so that pole moves with the
   camera and is never a reference for them.

## 2. Cameras

Mount positions: taped on 09-24 (CH01–CH04, grass to lens centre) or fitted by the calibration (CH05/CH06). The paddock
frame is in inches: origin pole A0, x along the 40-ft side (0–480), y across (0–240).

| Cam | What / where | Image (upright px) | Calibrated (09-24) | Correction table: coverage → target frame | Precision |
|---|---|---|---|---|---|
| CH01 | Duo 3 panorama, mid-field, (236, 92) in, 2.36 m | 7680 × 2160 | yes | nights → 09-18 | ≤ 3 px on passing nights (11 / 14) |
| CH02 | Duo 3 panorama, mid-field, (249, 160) in, 2.34 m | 7680 × 2160 | yes | nights → 09-18 | ≤ 3 px (13 / 14) |
| CH03 | RLC-1212A, ~11 in from B1, (112, 128) in, 2.24 m, looks to x = 0 | 4512 × 2512 | yes | nights → 09-18 (via the 09-04 03:01 labels) | ~5–10 px (1–2 cm) |
| CH04 | RLC-1212A, ~9 in from B3, (369, 123) in, 2.29 m, looks to x = 480 | 4512 × 2512 | yes | nights → 09-18 (via the 09-04 03:01 labels) | ~5–10 px |
| CH05 | RLC-520A on the crossbeam of pole B1, over house_1, centre (139, 125, 91) in | 2560 × 1920 | yes | nights → the **09-04 03:01** frame (not tied to 09-18 yet) | held-out ~0.5 px |
| CH06 | RLC-520A on the crossbeam of pole B3, over house_2, centre (346, 130, 91) in | 2560 × 1920 | yes | nights → 09-18 | ~1.8 px |
| CH07 | inside house_2 (in the lid) | 2560 × 1920 | no | all day, per lid-closed segment → the **09-04 12:00** frame | in-segment spread ~3 px |
| CH08 | inside house_1 (in the lid) | 2560 × 1920 | no | all day, per lid-closed segment → the **09-04 12:00** frame | ~1 px |

- **IR versus colour.** All cohort footage is IR, even by day. CH07/CH08 have deliberate colour inserts (recording repo
  `COLOUR_SAMPLING_LOG_cohort3.md`). On CH03/CH04 an IR ↔ colour switch alone shifts the image 10–18 px (calibration
  README), so never mix modes.
- **Gaps.** There is no video 09-12 → 09-15, and the 09-17 night is missing. 09-01 04:19:56–04:22:40 is lost to a PC
  blue screen.

## 3. How the cameras moved (measured, not judged)

- **CH01/CH02:** small whole-image shifts with no distortion (scale 0.999–1.002, rotation < 0.5°). Noon to noon they
  move by up to ~19–30 px. Within a night CH01's centre spans median 1.3 / max 9 px and CH02's median 6.6 / max 17 px,
  so CH02 drifts through the night. The shift differs between nights by up to ±20 px.
- **CH03/CH04:**
  - CH03 drifted ~90 px in x from 08-31 to 09-05, then stopped.
  - CH04 rotated ~0.8° over the same days.
  - Both moved a further 20–50 px between 09-18 and 09-30 with nobody touching them.
  - Labels on CH03/CH04 never agree better than ~10 px under any rigid model (affine, lens + rotation, full pose), so
    treat their precision as 1–2 cm.
- **Likely cause** (records + weather, not established): the poles lean with soil moisture.
  - 08-31 → 09-03 was wet, with a 09-02 storm, and the drift happened then.
  - The 09-09 evening rain shifted CH01/CH02 by ~18 px; CH02 shifted back by 09-11.
  - No camera was logged as touched during cohort 3.
  - Wind shows no relation: the 09-02 storm, gusts 21 mph, moved CH01 by 3 px.
- **In-box CH07/CH08:**
  - Static between lid openings; the lid is lifted at every battery round or catch (33 events,
    `cv/configs/cohort3_lid_events.json`).
  - CH07 moves at a lid event with median 4.9 px; 8 of 32 events exceed 10 px, up to 31 px.
  - CH08 moves with median 2.4 px; 3 of 30 exceed 10 px, including 96 px at the 09-02 AM round and 41 px at the 09-12
    final round.
  - While a lid is open the camera points elsewhere; those frames carry flag `lid`.

## 4. house_1 moved on 09-18; house_2 never moved

- house_1 = `HOUSE_1` = roof number **4**, by pole B1, under CH05, inside it CH08. house_2 = `HOUSE_2` = roof number
  **7**, by B3, under CH06, inside it CH07.
- Neither house moved while the rats were in the field (user, checked on CH05/CH06). house_1 was moved on 09-18, farther
  from its pole.
- **house_2 position** (calibration `house_check.py`, 09-18 joint fit of CH01 + CH02 + CH06): centre (342.4, 117.7) in,
  ridge 92° from x, cameras agree within 35 mm. Valid for the cohort.
- **house_1 cohort position: not computed yet.** The 09-18 fit, (147.5, 121.7) in with ridge 90°, is the post-move
  position.
  - The cohort position exists in the image as the user's labels on the 09-04 12:00 frames: CH01 and CH02
    (`landmarks_CH0[12]_20260904_120002.json`, each 7 edge pieces + the roof-number label) and CH05 (09-04 12:00 / 03:01).
  - Map them with the noon transforms (`results/2026c/cv_field/reports/run_manifest_landmark_track_ch0102_0904noon_2026c.json`
    → `track_frames.csv`), not the night table.
  - A 3-D fit is planned (answers to the calibration agent in the recording repo,
    `calibration_qc/NOTE_HOUSE1_COHORT_LABELS_2026-10-06.md`).
  - Until it exists, the image labels are better evidence for house_1 than a WISER ROI.
- **The roof is the lid**, lifted at every round, so roof edges may sit a little differently after each event; the body
  corners do not.
- **house_1 cohort pose (fitted 2026-10-06):** `cv/configs/house1_cohort_pose_2026c.json` — house_check.py fit on the CH01 + CH02 09-04 noon labels: centre (142.2, 123.5) in, ridge 88.5°, soil 45 mm below z = 0, residuals and sensitivities inside.

## 5. Landmarks: where, names, files

**Grid.** The 15 paddock poles are `POLE_<row><col>`. Rows A / B / C sit at y = 0 / 120 / 240 in; columns 0–4 sit at
x = 0 / 120 / 240 / 360 / 480 in (10-ft grid). A0 is the origin corner. The box on each pole is a WISER UWB anchor.

**Names** (labels are full-resolution upright pixels; `cv/configs/landmarks/2026c/README.md` has the rules):

| Name | Meaning | Kind |
|---|---|---|
| `POLE_xx_L` / `_R` | the pole's left / right edge **as seen in that image**: image sides, not paddock directions — never pair across cameras. The centre line is side-independent | edge |
| `BOX_xx` | box on the pole (= UWB anchor), corner outline | outline |
| `WALLTOP_X0 / X480 / Y0 / Y240` | top edge of each wall sheet; the foot is hidden by grass | polyline |
| `TOWER_1` (beyond the y = 240 wall) / `TOWER_2` (beyond y = 0); `PCBOX` (facing CH02) | outside the paddock | outline |
| `HOUSE_n_ROOF_X / _ROOF_Y / _BASE_X / _BASE_Y / _BASE_Z` | house edges grouped by 3-D direction; Z = vertical body corners; only visible stretches | edge |
| `HOUSE_n_LABEL` | the roof-number plate; two plates in CH05 are pieces of one entry | outline |
| `NAILS`, `PATCHES` / `PATCH_<wall>_<n>`, `SEAMS` / `SEAM_<wall>_<n>` | wall details (CH03/CH04, nails also CH05/CH06 roofs), unnumbered | point / polyline / edge |
| `BUILDING`, `WOOD` | CH04: building wall outside the paddock; a piece of wood | polyline |
| `BLUETOOTH_ANTENNA` | CH06: antenna on house_2 | outline |
| `FOODBOX`, `DOORFRAME`, `INNER_EDGES`, `CORNERS`, `LABELS` | in-box CH07/CH08 | edge / point / outline |

**Format.** `landmarks[name]` is a list of pieces, each a list of `[u, v]`. A hidden middle splits a structure into pieces;
never join across pieces. `kind[name]` gives the kind. Only what the user could see was labelled — nothing is
extrapolated.

**Files** (20, `cv/configs/landmarks/2026c/`):
- 09-18 references: CH01 13:57:30, CH02 15:22:30, CH03 15:45, CH04 14:32:30, CH05 / CH06 14:10.
- Cohort frames:
  - CH01 / CH02 09-04 12:00, house_1 only;
  - CH03–CH06 09-04 12:00 and 03:01;
  - CH07 / CH08 09-04 12:00 and 03:01.
- Files renamed on filing carry `note_rename`; removed mis-clicks carry `note_removed`.

## 6. Occluders and how to put them in any frame

Image extents in the reference frames (upright px), from the labels. They cover only the labelled, visible stretches:
pole feet are hidden by grass and tops may be out of frame.

| Cam (frame) | Poles (x range / y range) | Houses |
|---|---|---|
| CH01 (09-18) | A0 28–410 / 1906–2160; B0 756–1174 / 938–1305; **B1 940–2013 / 462–1534**; **B2 4329–4802 / 6–1874**; B3 6546–7060 / 829–1375; C0 1428–1730 / 143–402; C1 2302–2432 / 0–98 | house_1 (09-18, moved) 1912–2594 / 1160–1944 — cohort (09-04) 1864–2512 / 1142–1908; house_2 5973–6684 / 1048–1822 |
| CH02 (09-18) | A0 6528–6832 / 0–248; A4 1373–1683 / 70–372; B0 7280–7461 / 880–1076; **B1 6506–7413 / 530–1451**; **B2 4068–4402 / 336–1924**; **B3 740–1924 / 478–1542**; B4 612–1065 / 892–1290 | house_1 (09-18) 5830–6577 / 1019–1859 — cohort 5968–6684 / 1037–1846; house_2 1864–2490 / 1136–1940 |
| CH03 (09-18) | A0 22–192 / 1–576; B0 2124–2262 / 1–206; C0 4234–4332 / 8–270 | — |
| CH04 (09-18) | A4 4194–4328 / 2–378; B4 2120–2262 / 4–162 | — |
| CH05 (09-04 12:00) | B1 1071–1292 / 1555–1918 (crossbeam pole, moves with the camera) | house_1 844–1733 / 879–1557 |
| CH06 (09-18) | B3 1252–1484 / 1470–1917 (crossbeam pole) | house_2 778–1649 / 704–1439 |

Poles near the panoramas (B1–B3) are wide in the image and the likeliest occluders; the houses hide anything behind them.

To get an occluder region in a cohort frame at field-PC time `t`:

```python
import json, sys
import numpy as np
sys.path.insert(0, "cv/cv_field")
from frame_correction import Corrections, invert

C = Corrections("2026c")
B, info = C.correction("CH01", t)            # frame px -> 09-18 px; check info["flag"] (ok / night / sample / lid / outlier)
A = invert(B)                                 # 09-18 px -> frame px
L = json.load(open("cv/configs/landmarks/2026c/landmarks_CH01_20260918_135730.json", encoding="utf-8"))["landmarks"]
pts = np.vstack([np.asarray(p, float) for k in ("POLE_B1_L", "POLE_B1_R") for p in L[k]])
pole_b1 = pts @ A[:, :2].T + A[:, 2]          # pole edges in this frame; their convex hull = the pole's visible strip
```

- **house_1 during the cohort:** take the 09-04 12:00 labels. Map them to 09-18 px with the inverse of that frame's noon
  affine (§4), then into the frame with `A`.
- **CH05 / CH07 / CH08:** their target frame is a 09-04 frame (`info["target_frame"]`), so use the labels of that frame.
- **A house region:** the convex hull of all its edge pieces is the silhouette.
- **A pole:** the hull of its two edges is the visible strip; extend it downwards if you need the grass-hidden foot.

The existing `ch01_occlusion.py` does this in 3-D (pole capsules, gabled houses). The image labels above are the ground
truth to check it against, and they give house_1's cohort position directly.

## 7. Where things are

| What | Where |
|---|---|
| Correction table + lookup | `results/2026c/cv_field/reports/cv_field_frame_corrections_2026c.{csv,md}`; `cv/cv_field/frame_correction.py` (`build`, `Corrections`) |
| Lid events | `cv/configs/cohort3_lid_events.json` |
| Tracking / night chain | `cv/cv_field/landmark_track.py`, `landmark_night.py`; reports `results/2026c/cv_field/reports/cv_field_landmark_*_2026c*.md` (+ `run_manifest_*.json` → bulk under `D:\Field2026_analysis_out\2026c\`) |
| Labels + rules | `cv/configs/landmarks/2026c/` (+ `README.md`, `paddock_schematic.png`) |
| Labelling GUI | `cv/cv_field/landmark_gui.py` (pages in `D:\Field2026_analysis_out\2026c\cv_field_landmarks\`) |
| Calibration | recording repo `calibration_qc/` (`paddock_map.load()`, `house_check.py`); exploratory, 76 mm median cross-camera |
