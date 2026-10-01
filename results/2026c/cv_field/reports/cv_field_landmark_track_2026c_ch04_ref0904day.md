# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch04_ref0904day`)

Reference other than 09-18 — CH04: `landmarks_CH04_20260904_120002.json` tied to 09-18 by the label sets — unreliable, held-out 2.18 / 12.39 px over 9 units, rejected {'NAILS#2': 3.4, 'NAILS#7': 3.3, 'NAILS#8': 3.9, 'NAILS#9': 5.8, 'NAILS#10': 7.4, 'NAILS#11': 6.2, 'PATCHES#1': 9.8, 'SEAMS#1': 3.9, 'SEAMS#2': 6.0, 'BUILDING#1': 4.2, 'BUILDING#2': 5.6, 'BUILDING#3': 5.5, 'BUILDING#4': 6.3}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-01 18:20 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch04_ref0904day_20261001_1820` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH04 | 14 | 12 | 2 | 0.99 | -22.8..-1.1 | -0.5..+5.6 | +0.2..+1.0 | 0.9973..1.0037 | - | 66 (14) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
