# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0508_ref0904day`)

Reference other than 09-18 — CH05: `landmarks_CH05_20260904_120002.json`; CH06: `landmarks_CH06_20260904_120002.json` tied to 09-18 by the label sets — ok, held-out 2.36 / 3.07 px over 11 units, rejected {'NAILS#2': 4.0, 'NAILS#5': 3.2, 'NAILS#6': 6.3, 'NAILS#7': 4.2, 'NAILS#9': 5.7}; CH07: `landmarks_CH07_20260904_120002.json`; CH08: `landmarks_CH08_20260904_120002.json`. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-02 19:08 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0508_ref0904day_20261002_1859` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH05 | 14 | 13 | 1 | 0.42 | -12.2..+27.4 | -1.7..+18.7 | -0.8..-0.0 | 0.9971..1.0005 | 5.69 | 0 (0) |
| CH06 | 14 | 13 | 1 | 1.44 | -33.7..+5.9 | -8.0..+1.1 | -0.2..+1.2 | 1.0010..1.0072 | 1.73 | 0 (0) |
| CH07 | 14 | 3 | 11 | inf | -18.3..+11.2 | -17.5..+0.1 | -1.0..-0.0 | 0.9926..1.0061 | - | 74 (14) |
| CH08 | 14 | 8 | 6 | 1.82 | -78.7..+12.9 | -24.4..+63.7 | -0.0..+1.3 | 0.9971..1.0026 | - | 48 (13) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
