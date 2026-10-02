# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch04_ref0904day`)

Reference other than 09-18 — CH04: `landmarks_CH04_20260904_120002.json` tied to 09-18 by the label sets — ok, held-out 1.89 / 4.79 px over 7 units, rejected {'NAILS#2': 3.9, 'NAILS#7': 3.6, 'NAILS#8': 3.9, 'NAILS#9': 5.8, 'NAILS#10': 7.4, 'NAILS#11': 6.4, 'PATCHES#1': 11.0, 'SEAMS#1': 3.6, 'SEAMS#2': 5.1, 'BUILDING#1': 3.9, 'BUILDING#2': 5.4, 'BUILDING#3': 5.0, 'BUILDING#4': 6.1}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-01 22:09 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch04_ref0904day_20261001_2205` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH04 | 14 | 12 | 2 | 0.99 | -24.2..-2.5 | -1.7..+4.4 | +0.3..+1.0 | 0.9966..1.0030 | - | 66 (14) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
