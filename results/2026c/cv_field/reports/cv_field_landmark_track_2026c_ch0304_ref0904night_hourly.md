# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0304_ref0904night_hourly`)

Reference other than 09-18 — CH03: `landmarks_CH03_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 2.16 / 8.86 px over 8 units, rejected {'NAILS#1': 6.0, 'NAILS#2': 6.7, 'NAILS#6': 10.4, 'NAILS#7': 10.6, 'NAILS#10': 10.4, 'NAILS#11': 9.8, 'NAILS#12': 10.6, 'NAILS#13': 11.5, 'NAILS#14': 13.9, 'NAILS#15': 8.4, 'NAILS#17': 6.5}; CH04: `landmarks_CH04_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 3.05 / 3.75 px over 5 units, rejected {'NAILS#1': 5.9, 'NAILS#2': 9.9, 'NAILS#5': 7.0, 'NAILS#6': 5.8, 'NAILS#7': 12.2, 'NAILS#8': 8.1, 'NAILS#9': 10.4, 'NAILS#10': 11.9, 'SEAMS#1': 3.4}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-02 04:17 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0304_ref0904night_hourly_20261002_0402` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH03 | 124 | 35 | 89 | 2.72 | -22.2..+21.3 | -17.0..+10.4 | -2.4..+0.7 | 0.9929..1.0075 | - | 465 (124) |
| CH04 | 126 | 89 | 37 | 1.58 | -29.7..+22.3 | -32.7..+33.6 | +0.1..+0.9 | 0.9748..1.0232 | - | 351 (113) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
