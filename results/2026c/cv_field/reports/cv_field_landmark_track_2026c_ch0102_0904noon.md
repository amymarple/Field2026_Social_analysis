# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0102_0904noon`)

Generated 2026-10-06 15:41 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0102_0904noon_20261006_1540` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH01 | 1 | 1 | 0 | 1.27 | +10.1..+10.1 | +2.0..+2.0 | -0.0..-0.0 | 0.9999..0.9999 | 2.93 | 0 (0) |
| CH02 | 1 | 1 | 0 | 1.74 | +18.6..+18.6 | -1.8..-1.8 | -0.1..-0.1 | 1.0014..1.0014 | 2.60 | 0 (0) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
