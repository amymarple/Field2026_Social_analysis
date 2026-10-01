# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`)

Generated 2026-10-01 15:03 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_20261001_1441` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation). **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px |
|---|---|---|---|---|---|---|---|---|---|
| CH01 | 42 | 15 | 27 | 6.11 | -51.9..+18.6 | -75.3..+83.4 | -1.2..+1.1 | 0.9650..1.0280 | 5.54 |
| CH02 | 42 | 15 | 27 | 2.78 | -25.1..+29.6 | -8.2..+16.0 | -0.5..+0.7 | 0.9965..1.0194 | 2.52 |
| CH03 | 42 | 5 | 37 | 5.66 | -211.4..+143.7 | -662.3..+914.3 | -8.6..+17.0 | 0.6836..1.4147 | - |
| CH04 | 42 | 6 | 36 | 8.13 | -175.9..+266.8 | -174.1..+73.3 | -0.2..+6.2 | 0.8525..1.0612 | - |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
