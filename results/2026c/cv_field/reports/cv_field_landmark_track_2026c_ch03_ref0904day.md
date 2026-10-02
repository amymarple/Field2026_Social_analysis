# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch03_ref0904day`)

Reference other than 09-18 — CH03: `landmarks_CH03_20260904_120000.json` tied to 09-18 by the label sets — unreliable, held-out 4.16 / 8.11 px over 5 units, rejected {'NAILS#1': 12.6, 'NAILS#2': 7.7, 'NAILS#3': 12.7, 'NAILS#4': 10.2, 'NAILS#5': 11.9, 'NAILS#6': 13.9, 'NAILS#7': 11.8, 'NAILS#9': 10.6, 'NAILS#10': 10.0, 'NAILS#11': 11.7, 'NAILS#12': 10.7, 'NAILS#13': 12.6, 'NAILS#14': 14.0, 'NAILS#15': 12.3, 'NAILS#17': 8.2}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-01 22:46 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch03_ref0904day_20261001_2242` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH03 | 14 | 8 | 6 | 2.27 | -72.2..+16.0 | -25.6..-4.7 | -0.4..+0.6 | 0.9956..1.0048 | - | 44 (14) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
