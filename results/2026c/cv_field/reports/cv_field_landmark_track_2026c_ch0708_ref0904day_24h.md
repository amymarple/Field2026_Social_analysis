# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0708_ref0904day_24h`)

Reference other than 09-18 — CH07: `landmarks_CH07_20260904_120002.json` tied to 09-18 by the label sets — same frame, held-out 0.00 / 0.00 px over 0 units, rejected none; CH08: `landmarks_CH08_20260904_120002.json` tied to 09-18 by the label sets — same frame, held-out 0.00 / 0.00 px over 0 units, rejected none. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-03 18:42 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0708_ref0904day_24h_20261003_1834` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH07 | 388 | 64 | 324 | 4.23 | -64.6..+28.0 | -74.8..+57.7 | -2.2..+1.5 | 0.9812..1.0349 | - | 1242 (363) |
| CH08 | 388 | 241 | 147 | 2.02 | -90.7..+38.0 | -77.4..+91.5 | -0.6..+3.1 | 0.9860..1.0194 | - | 589 (247) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
