# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `2026c`, run `ch0506_ref0904day_hourly`)

Reference other than 09-18 — CH05: `landmarks_CH05_20260904_120002.json`; CH06: `landmarks_CH06_20260904_120002.json` tied to 09-18 by the label sets — ok, held-out 2.36 / 3.07 px over 11 units, rejected {'NAILS#2': 4.0, 'NAILS#5': 3.2, 'NAILS#6': 6.3, 'NAILS#7': 4.2, 'NAILS#9': 5.7}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out errors are those of the tracking from that reference.

Generated 2026-10-11 00:13 by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0506_ref0904day_hourly_20261010_2330` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses (validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. **The user reviews the overlays; this report makes no visual claim.**

| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |
|---|---|---|---|---|---|---|---|---|---|---|
| CH05 | 273 | 251 | 22 | 0.53 | -12.2..+38.2 | -3.2..+20.5 | -0.9..+0.0 | 0.9936..1.0069 | 6.11 | 0 (0) |
| CH06 | 276 | 245 | 31 | 1.45 | -33.7..+54.5 | -26.7..+16.1 | -1.0..+3.4 | 0.9476..1.0083 | 3.12 | 0 (0) |

Reference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.
