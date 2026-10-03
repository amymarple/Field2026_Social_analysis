# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0708_ref0904night_24h`)

Reference other than 09-18 — CH07: `landmarks_CH07_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 3.89 / 8.08 px over 3 units, rejected none; CH08: `landmarks_CH08_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 4.55 / 5.65 px over 3 units, rejected none. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-03 16:02 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0708_ref0904night_24h_20261003_1554` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH07 | 388 | 36 | 352 | 5.65 | -23.6..+60.0 | -61.7..+29.9 | -1.7..+0.8 | 0.9803..1.0335 | - | 2914 (386) |
| CH08 | 388 | 226 | 162 | 1.82 | -79.5..+36.0 | -24.6..+89.9 | -0.4..+1.6 | 0.9755..1.0163 | - | 1376 (386) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
