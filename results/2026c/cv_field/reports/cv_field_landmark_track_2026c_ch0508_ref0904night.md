# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0508_ref0904night`)

Reference other than 09-18 — CH05: `landmarks_CH05_20260904_030100.json`; CH06: `landmarks_CH06_20260904_030100.json` tied to 09-18 by the label sets — ok, held-out 2.54 / 3.63 px over 10 units, rejected {'NAILS#6': 5.6, 'NAILS#8': 4.6, 'NAILS#10': 4.0, 'NAILS#11': 7.5, 'NAILS#12': 10.1, 'NAILS#13': 6.5}; CH07: `landmarks_CH07_20260904_030100.json`; CH08: `landmarks_CH08_20260904_030100.json`. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-02 19:16 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0508_ref0904night_20261002_1908` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH05 | 14 | 13 | 1 | 0.45 | -6.6..+31.3 | -0.3..+19.8 | -0.5..+0.1 | 0.9954..1.0049 | 2.96 | 0 (0) |
| CH06 | 14 | 14 | 0 | 1.79 | -27.9..-0.3 | -11.1..+2.0 | -1.2..+0.9 | 0.9922..1.0051 | 4.47 | 0 (0) |
| CH07 | 14 | 6 | 8 | 2.20 | -25.2..+28.9 | -7.7..+17.9 | -0.7..+0.2 | 0.9997..1.0065 | - | 76 (13) |
| CH08 | 14 | 11 | 3 | 1.15 | -65.0..+31.5 | -2.2..+75.0 | -0.2..+0.7 | 0.9980..1.0072 | - | 42 (13) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
