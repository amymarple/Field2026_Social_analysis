# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch04_ref0904night`)

Reference other than 09-18 — CH04: `landmarks_CH04_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 10.43 / 16.55 px over 6 units, rejected {'NAILS#1': 6.1, 'NAILS#2': 9.7, 'NAILS#5': 7.0, 'NAILS#6': 5.9, 'NAILS#7': 12.1, 'NAILS#8': 8.0, 'NAILS#9': 9.8, 'NAILS#10': 11.2, 'PATCHES#2': 14.2, 'SEAMS#1': 3.4, 'SEAMS#2': 3.8}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-01 18:22 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch04_ref0904night_20261001_1820` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH04 | 42 | 29 | 13 | 1.73 | -30.2..+12.7 | -18.2..+33.7 | +0.2..+0.9 | 0.9836..1.0220 | - | 124 (40) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
