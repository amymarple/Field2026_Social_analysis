# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0708_ref0904night_24h`)

Reference other than 09-18 — CH07: `landmarks_CH07_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 3.89 / 8.08 px over 3 units, rejected none; CH08: `landmarks_CH08_20260904_030100.json` tied to 09-18 by the label sets — unreliable, held-out 4.55 / 5.65 px over 3 units, rejected none. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-03 18:49 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0708_ref0904night_24h_20261003_1842` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH07 | 388 | 110 | 278 | 3.30 | -80.0..+42.3 | -61.7..+24.6 | -1.3..+1.5 | 0.9759..1.0335 | - | 2004 (381) |
| CH08 | 388 | 300 | 88 | 1.63 | -76.3..+33.1 | -51.7..+80.8 | -0.9..+1.7 | 0.9790..1.0132 | - | 508 (180) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
