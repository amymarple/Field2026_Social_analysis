# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0506_ref0904night_hourly`)

Reference other than 09-18 — CH05: `landmarks_CH05_20260904_030100.json`; CH06: `landmarks_CH06_20260904_030100.json` tied to 09-18 by the label sets — ok, held-out 2.54 / 3.63 px over 10 units, rejected {'NAILS#6': 5.6, 'NAILS#8': 4.6, 'NAILS#10': 4.0, 'NAILS#11': 7.5, 'NAILS#12': 10.1, 'NAILS#13': 6.5}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-03 14:51 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0506_ref0904night_hourly_20261003_1427` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH05 | 125 | 116 | 9 | 0.46 | -6.7..+38.4 | -0.3..+20.7 | -0.5..+0.1 | 0.9949..1.0066 | 3.20 | 0 (0) |
| CH06 | 126 | 123 | 3 | 1.84 | -29.8..+3.6 | -11.1..+4.0 | -1.3..+0.9 | 0.9924..1.0061 | 4.48 | 0 (0) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
