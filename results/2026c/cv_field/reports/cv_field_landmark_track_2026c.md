# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`)

Generated 2026-10-01 16:25 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_20261001_1624` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH01 | 14 | 14 | 0 | 1.35 | -11.1..+18.6 | -1.7..+6.7 | -0.1..+0.4 | 0.9989..1.0007 | 2.28 | 0 (0) |
| CH02 | 14 | 12 | 2 | 0.97 | -3.3..+29.6 | -2.3..+0.6 | -0.2..+0.1 | 0.9998..1.0021 | 1.49 | 0 (0) |
| CH03 | 14 | 5 | 9 | 2.45 | -55.0..+37.4 | -49.0..+10.2 | -0.8..+0.3 | 0.9741..1.0089 | - | 38 (14) |
| CH04 | 14 | 2 | 12 | 7.33 | -22.5..+191.2 | -169.6..+119.5 | -7.4..+0.5 | 0.9273..1.0542 | - | 92 (14) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
