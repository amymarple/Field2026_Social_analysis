# Frame corrections, CH01-CH08 (cohort `2026c`)

Generated 2026-10-11 00:13 by `cv/cv_field/frame_correction.py build` (method, columns, flags and lookup in its docstring). Table: `cv_field_frame_corrections_2026c.csv` (A = 09-18 px -> frame px, B = frame px -> 09-18 px; full-resolution upright pixels). Use `Corrections(cohort).to_paddock(cam, t, uv, z_mm=60)`.

Sources: CH01/CH02 night chain: `D:\Field2026_analysis_out\2026c\cv_field_landmark_night_20261002_0417`; ch0304_ref0904night_hourly: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0304_ref0904night_hourly_20261003_1849`; ch0506_ref0904night_hourly: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0506_ref0904night_hourly_20261003_1427`; ch0506_ref0904day_hourly: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0506_ref0904day_hourly_20261010_2330`; ch0708_ref0904day_24h: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0708_ref0904day_24h_20261003_1834`; ch0708_ref0904night_24h: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0708_ref0904night_24h_20261003_1842`.

Reference alignment (CH07/CH08 night-reference samples -> the day reference, median over frames where both fit): CH07: n 110, centre difference median 7.7 -> 6.8 px, p90 25.2 -> 24.9 px; CH08: n 280, centre difference median 1.9 -> 2.0 px, p90 11.9 -> 11.8 px.

Precision (user, 2026-10-02): CH01/CH02 dawn closure <= 3 px on passing nights (< 1 cm); CH03/CH04 ~5-10 px (~1-2 cm). Sample rule (held-out median / p90): CH01/CH02 3 / 6 px, CH03/CH04 5 / 10 px. The calibration's own error is separate and not reduced here (release 2026-10-03 rev g: CALIBRATION_FINAL_2026-10-04.md).

House-top cameras (CH05/CH06, all day since 2026-10-10): registered on the roof = the house lid, so a correction never spans a lid event and samples inside one are flagged 'lid'; CH05 keeps its 09-04 reference frames (03:01 at night, 12:00 by day) and maps to the paddock through the recording repo's cohort tie (cohort_tie.py).

In-box cameras (CH07/CH08): static between lid events -> per lid-closed segment the median of its usable samples; samples > 10 px from it are flagged 'outlier'. CH07: 33 segments, 84 outliers, in-segment spread median 2.9 px; CH08: 32 segments, 35 outliers, in-segment spread median 1.1 px.

Summary: CH01 98 ok / 0 sample / 26 night / 0 outlier / 0 lid of 124; CH02 116 ok / 1 sample / 8 night / 0 outlier / 0 lid of 125; CH03 102 ok / 22 sample / 0 night / 0 outlier / 0 lid of 124; CH04 124 ok / 2 sample / 0 night / 0 outlier / 0 lid of 126; CH05 327 ok / 26 sample / 0 night / 0 outlier / 41 lid of 394; CH06 337 ok / 17 sample / 0 night / 0 outlier / 38 lid of 392; CH07 202 ok / 86 sample / 0 night / 43 outlier / 30 lid of 361; CH08 296 ok / 40 sample / 0 night / 7 outlier / 42 lid of 385.

| camera | night | samples | ok / sample / night flags | held-out median px (median) | night quality px | verdict | rain mm (21:00-04:20) | shift range tx, ty px |
|---|---|---|---|---|---|---|---|---|
| CH01 | 2026-08-30 | 9 | 9 / 0 / 0 | 0.56 | 2.86 | PASS | 0.00 | see CSV |
| CH01 | 2026-08-31 | 8 | 8 / 0 / 0 | 0.54 | 1.49 | PASS | 2.50 | see CSV |
| CH01 | 2026-09-01 | 9 | 9 / 0 / 0 | 0.38 | 2.93 | PASS | 0.00 | see CSV |
| CH01 | 2026-09-02 | 9 | 9 / 0 / 0 | 1.38 | 1.19 | PASS | 0.25 | see CSV |
| CH01 | 2026-09-03 | 9 | 9 / 0 / 0 | 0.82 | 2.34 | PASS | 18.40 | see CSV |
| CH01 | 2026-09-04 | 9 | 0 / 0 / 9 | 0.39 | 3.03 | FAIL | 0.00 | see CSV |
| CH01 | 2026-09-05 | 9 | 9 / 0 / 0 | 0.31 | 1.76 | PASS | 0.00 | see CSV |
| CH01 | 2026-09-06 | 9 | 9 / 0 / 0 | 0.45 | 1.65 | PASS | 0.00 | see CSV |
| CH01 | 2026-09-07 | 9 | 0 / 0 / 9 | 0.49 | 3.11 | FAIL | 0.00 | see CSV |
| CH01 | 2026-09-08 | 9 | 9 / 0 / 0 | 0.32 | 2.36 | PASS | 0.00 | see CSV |
| CH01 | 2026-09-09 | 9 | 9 / 0 / 0 | 0.72 | 2.54 | PASS | 7.20 | see CSV |
| CH01 | 2026-09-10 | 8 | 0 / 0 / 8 | 0.38 | 3.24 | FAIL | 0.00 | see CSV |
| CH01 | 2026-09-11 | 9 | 9 / 0 / 0 | 0.41 | 1.58 | PASS | 0.00 | see CSV |
| CH01 | 2026-09-16 | 9 | 9 / 0 / 0 | 0.33 | 1.85 | PASS | 0.00 | see CSV |
| CH02 | 2026-08-30 | 9 | 9 / 0 / 0 | 0.44 | 2.86 | PASS | 0.00 | see CSV |
| CH02 | 2026-08-31 | 8 | 8 / 0 / 0 | 0.40 | 1.83 | PASS | 2.50 | see CSV |
| CH02 | 2026-09-01 | 9 | 9 / 0 / 0 | 0.39 | 2.24 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-02 | 9 | 0 / 1 / 8 | 1.45 | 2.72 | FAIL | 0.25 | see CSV |
| CH02 | 2026-09-03 | 9 | 9 / 0 / 0 | 1.59 | 1.52 | PASS | 18.40 | see CSV |
| CH02 | 2026-09-04 | 9 | 9 / 0 / 0 | 0.54 | 1.48 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-05 | 9 | 9 / 0 / 0 | 0.76 | 1.06 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-06 | 9 | 9 / 0 / 0 | 0.53 | 1.33 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-07 | 9 | 9 / 0 / 0 | 0.49 | 2.57 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-08 | 9 | 9 / 0 / 0 | 0.66 | 0.69 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-09 | 9 | 9 / 0 / 0 | 0.61 | 1.35 | PASS | 7.20 | see CSV |
| CH02 | 2026-09-10 | 9 | 9 / 0 / 0 | 0.42 | 2.30 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-11 | 9 | 9 / 0 / 0 | 0.48 | 2.93 | PASS | 0.00 | see CSV |
| CH02 | 2026-09-16 | 9 | 9 / 0 / 0 | 0.36 | 1.34 | PASS | 0.00 | see CSV |
| CH03 | 2026-08-30 | 9 | 3 / 6 / 0 | 4.54 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-08-31 | 8 | 3 / 5 / 0 | 4.86 | 2.16 | unreliable | 2.50 | see CSV |
| CH03 | 2026-09-01 | 9 | 4 / 5 / 0 | 2.88 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-02 | 9 | 8 / 1 / 0 | 1.93 | 2.16 | unreliable | 0.25 | see CSV |
| CH03 | 2026-09-03 | 9 | 9 / 0 / 0 | 0.51 | 2.16 | unreliable | 18.40 | see CSV |
| CH03 | 2026-09-04 | 9 | 9 / 0 / 0 | 3.43 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-05 | 9 | 9 / 0 / 0 | 2.77 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-06 | 9 | 9 / 0 / 0 | 3.07 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-07 | 9 | 9 / 0 / 0 | 2.88 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-08 | 9 | 9 / 0 / 0 | 1.85 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-09 | 9 | 9 / 0 / 0 | 1.86 | 2.16 | unreliable | 7.20 | see CSV |
| CH03 | 2026-09-10 | 8 | 8 / 0 / 0 | 1.64 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-11 | 9 | 8 / 1 / 0 | 3.20 | 2.16 | unreliable | 0.00 | see CSV |
| CH03 | 2026-09-16 | 9 | 5 / 4 / 0 | 4.77 | 2.16 | unreliable | 0.00 | see CSV |
| CH04 | 2026-08-30 | 9 | 7 / 2 / 0 | 3.37 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-08-31 | 9 | 9 / 0 / 0 | 2.73 | 3.05 | unreliable | 2.50 | see CSV |
| CH04 | 2026-09-01 | 9 | 9 / 0 / 0 | 2.38 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-02 | 9 | 9 / 0 / 0 | 1.34 | 3.05 | unreliable | 0.25 | see CSV |
| CH04 | 2026-09-03 | 9 | 9 / 0 / 0 | 0.34 | 3.05 | unreliable | 18.40 | see CSV |
| CH04 | 2026-09-04 | 9 | 9 / 0 / 0 | 0.83 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-05 | 9 | 9 / 0 / 0 | 1.15 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-06 | 9 | 9 / 0 / 0 | 1.26 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-07 | 9 | 9 / 0 / 0 | 1.57 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-08 | 9 | 9 / 0 / 0 | 2.25 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-09 | 9 | 9 / 0 / 0 | 1.22 | 3.05 | unreliable | 7.20 | see CSV |
| CH04 | 2026-09-10 | 9 | 9 / 0 / 0 | 1.40 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-11 | 9 | 9 / 0 / 0 | 2.06 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-16 | 9 | 9 / 0 / 0 | 2.74 | 3.05 | unreliable | 0.00 | see CSV |
| CH05 | 2026-08-30 | 23 | 16 / 0 / 0 | 0.51 | - | - | 0.00 | see CSV |
| CH05 | 2026-08-31 | 21 | 18 / 0 / 0 | 0.49 | - | - | 2.50 | see CSV |
| CH05 | 2026-09-01 | 29 | 27 / 0 / 0 | 0.84 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-02 | 29 | 27 / 0 / 0 | 0.44 | - | - | 0.25 | see CSV |
| CH05 | 2026-09-03 | 29 | 27 / 0 / 0 | 0.40 | - | - | 18.40 | see CSV |
| CH05 | 2026-09-04 | 29 | 27 / 0 / 0 | 0.52 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-05 | 33 | 28 / 0 / 0 | 0.57 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-06 | 30 | 26 / 0 / 0 | 0.49 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-07 | 29 | 26 / 0 / 0 | 0.55 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-08 | 29 | 27 / 0 / 0 | 0.56 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-09 | 29 | 27 / 0 / 0 | 0.44 | - | - | 7.20 | see CSV |
| CH05 | 2026-09-10 | 26 | 24 / 0 / 0 | 0.45 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-11 | 28 | 24 / 1 / 0 | 0.48 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-16 | 29 | 2 / 25 / 0 | 3.33 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-17 | 1 | 1 / 0 / 0 | 2.46 | - | - | - | see CSV |
| CH06 | 2026-08-30 | 23 | 15 / 1 / 0 | 2.74 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-08-31 | 21 | 13 / 6 / 0 | 2.86 | 2.36 | ok | 2.50 | see CSV |
| CH06 | 2026-09-01 | 29 | 26 / 2 / 0 | 1.39 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-02 | 28 | 25 / 1 / 0 | 1.33 | 2.36 | ok | 0.25 | see CSV |
| CH06 | 2026-09-03 | 29 | 25 / 2 / 0 | 1.25 | 2.36 | ok | 18.40 | see CSV |
| CH06 | 2026-09-04 | 28 | 26 / 0 / 0 | 1.10 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-05 | 33 | 28 / 0 / 0 | 1.63 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-06 | 30 | 26 / 0 / 0 | 1.52 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-07 | 29 | 22 / 4 / 0 | 2.63 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-08 | 29 | 27 / 0 / 0 | 1.41 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-09 | 29 | 27 / 0 / 0 | 1.49 | 2.36 | ok | 7.20 | see CSV |
| CH06 | 2026-09-10 | 27 | 26 / 0 / 0 | 1.56 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-11 | 27 | 24 / 0 / 0 | 1.45 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-16 | 29 | 26 / 1 / 0 | 1.63 | 2.36 | ok | 0.00 | see CSV |
| CH06 | 2026-09-17 | 1 | 1 / 0 / 0 | 1.07 | 2.36 | ok | - | see CSV |
| CH07 | 2026-08-30 | 21 | 12 / 2 / 0 | 2.83 | 3.89 | unreliable | 0.00 | see CSV |
| CH07 | 2026-08-31 | 20 | 14 / 2 / 0 | 2.75 | 0.00 | same frame | 2.50 | see CSV |
| CH07 | 2026-09-01 | 27 | 15 / 7 / 0 | 2.59 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-02 | 25 | 13 / 7 / 0 | 3.03 | 0.00 | same frame | 0.25 | see CSV |
| CH07 | 2026-09-03 | 26 | 23 / 1 / 0 | 1.25 | 0.00 | same frame | 18.40 | see CSV |
| CH07 | 2026-09-04 | 26 | 21 / 2 / 0 | 1.99 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-05 | 30 | 19 / 7 / 0 | 2.70 | 3.89 | unreliable | 0.00 | see CSV |
| CH07 | 2026-09-06 | 28 | 17 / 6 / 0 | 2.68 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-07 | 25 | 14 / 5 / 0 | 3.00 | 3.89 | unreliable | 0.00 | see CSV |
| CH07 | 2026-09-08 | 26 | 7 / 9 / 0 | 3.22 | 3.89 | unreliable | 0.00 | see CSV |
| CH07 | 2026-09-09 | 26 | 15 / 7 / 0 | 3.37 | 0.00 | same frame | 7.20 | see CSV |
| CH07 | 2026-09-10 | 26 | 15 / 8 / 0 | 3.34 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-11 | 27 | 10 / 8 / 0 | 3.44 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-16 | 27 | 6 / 15 / 0 | 4.18 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-17 | 1 | 1 / 0 / 0 | 3.08 | 0.00 | same frame | - | see CSV |
| CH08 | 2026-08-30 | 22 | 7 / 9 / 0 | 4.58 | 4.55 | unreliable | 0.00 | see CSV |
| CH08 | 2026-08-31 | 20 | 15 / 2 / 0 | 2.43 | 0.00 | same frame | 2.50 | see CSV |
| CH08 | 2026-09-01 | 30 | 15 / 13 / 0 | 3.90 | 4.55 | unreliable | 0.00 | see CSV |
| CH08 | 2026-09-02 | 28 | 22 / 2 / 0 | 1.38 | 0.00 | same frame | 0.25 | see CSV |
| CH08 | 2026-09-03 | 28 | 24 / 0 / 0 | 1.04 | 0.00 | same frame | 18.40 | see CSV |
| CH08 | 2026-09-04 | 28 | 26 / 0 / 0 | 0.90 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-05 | 32 | 27 / 0 / 0 | 1.05 | 4.55 | unreliable | 0.00 | see CSV |
| CH08 | 2026-09-06 | 29 | 25 / 0 / 0 | 0.78 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-07 | 28 | 25 / 0 / 0 | 1.02 | 4.55 | unreliable | 0.00 | see CSV |
| CH08 | 2026-09-08 | 28 | 26 / 0 / 0 | 1.23 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-09 | 28 | 26 / 0 / 0 | 1.41 | 4.55 | unreliable | 7.20 | see CSV |
| CH08 | 2026-09-10 | 28 | 25 / 0 / 0 | 1.24 | 4.55 | unreliable | 0.00 | see CSV |
| CH08 | 2026-09-11 | 27 | 21 / 2 / 0 | 1.73 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-16 | 28 | 11 / 12 / 0 | 3.66 | 4.55 | unreliable | 0.00 | see CSV |
| CH08 | 2026-09-17 | 1 | 1 / 0 / 0 | 3.69 | 4.55 | unreliable | - | see CSV |

The shift itself is in the CSV (a13 / a23 are the translation terms at the image origin; landmark_track.params gives tx, ty at the frame centre). Nights 09-12 -> 09-15 have no video.
