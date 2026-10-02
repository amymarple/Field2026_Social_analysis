# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch03_ref0904night`)

Reference other than 09-18 — CH03: `landmarks_CH03_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 2.16 / 8.86 px over 8 units, rejected {'NAILS#1': 6.0, 'NAILS#2': 6.7, 'NAILS#6': 10.4, 'NAILS#7': 10.6, 'NAILS#10': 10.4, 'NAILS#11': 9.8, 'NAILS#12': 10.6, 'NAILS#13': 11.5, 'NAILS#14': 13.9, 'NAILS#15': 8.4, 'NAILS#17': 6.5}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-01 22:54 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch03_ref0904night_20261001_2246` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH03 | 41 | 12 | 29 | 3.03 | -13.0..+32.7 | -13.7..+10.4 | -2.4..+0.6 | 0.9948..1.0075 | - | 155 (41) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
