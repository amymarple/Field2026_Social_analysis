# Frame corrections, whole-field cameras, nights (cohort `2026c`)

Generated 2026-10-03 16:02 by `cv/cv_field/frame_correction.py build` (method, columns, flags and lookup in its docstring). Table: `cv_field_frame_corrections_2026c.csv` (A = 09-18 px -> frame px, B = frame px -> 09-18 px; full-resolution upright pixels). Use `Corrections(cohort).to_paddock(cam, t, uv, z_mm=60)`.

Sources: CH01/CH02 night chain: `D:\Field2026_analysis_out\2026c\cv_field_landmark_night_20261002_0417`; ch0304_ref0904night_hourly: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0304_ref0904night_hourly_20261002_0402`; ch0506_ref0904night_hourly: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0506_ref0904night_hourly_20261003_1427`; ch0708_ref0904day_24h: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0708_ref0904day_24h_20261003_1451`; ch0708_ref0904night_24h: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0708_ref0904night_24h_20261003_1554`.

Precision (user, 2026-10-02): CH01/CH02 dawn closure <= 3 px on passing nights (< 1 cm); CH03/CH04 ~5-10 px (~1-2 cm). Sample rule (held-out median / p90): CH01/CH02 3 / 6 px, CH03/CH04 5 / 10 px. The 09-24 calibration's own error (76 mm median cross-camera) is separate and not reduced here.

Summary: CH01 98 ok / 0 sample / 26 night of 124; CH02 116 ok / 1 sample / 8 night of 125; CH03 102 ok / 22 sample / 0 night of 124; CH04 124 ok / 2 sample / 0 night of 126; CH05 116 ok / 9 sample / 0 night of 125; CH06 123 ok / 3 sample / 0 night of 126; CH07 108 ok / 175 sample / 0 night of 307; CH08 268 ok / 59 sample / 0 night of 367.

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
| CH04 | 2026-09-01 | 9 | 9 / 0 / 0 | 2.47 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-02 | 9 | 9 / 0 / 0 | 1.34 | 3.05 | unreliable | 0.25 | see CSV |
| CH04 | 2026-09-03 | 9 | 9 / 0 / 0 | 0.34 | 3.05 | unreliable | 18.40 | see CSV |
| CH04 | 2026-09-04 | 9 | 9 / 0 / 0 | 0.91 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-05 | 9 | 9 / 0 / 0 | 1.42 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-06 | 9 | 9 / 0 / 0 | 1.12 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-07 | 9 | 9 / 0 / 0 | 1.56 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-08 | 9 | 9 / 0 / 0 | 1.90 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-09 | 9 | 9 / 0 / 0 | 1.31 | 3.05 | unreliable | 7.20 | see CSV |
| CH04 | 2026-09-10 | 9 | 9 / 0 / 0 | 1.40 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-11 | 9 | 9 / 0 / 0 | 2.06 | 3.05 | unreliable | 0.00 | see CSV |
| CH04 | 2026-09-16 | 9 | 9 / 0 / 0 | 2.74 | 3.05 | unreliable | 0.00 | see CSV |
| CH05 | 2026-08-30 | 9 | 9 / 0 / 0 | 0.55 | - | - | 0.00 | see CSV |
| CH05 | 2026-08-31 | 8 | 8 / 0 / 0 | 0.45 | - | - | 2.50 | see CSV |
| CH05 | 2026-09-01 | 9 | 9 / 0 / 0 | 1.09 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-02 | 9 | 9 / 0 / 0 | 0.38 | - | - | 0.25 | see CSV |
| CH05 | 2026-09-03 | 9 | 9 / 0 / 0 | 0.30 | - | - | 18.40 | see CSV |
| CH05 | 2026-09-04 | 9 | 9 / 0 / 0 | 0.43 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-05 | 9 | 9 / 0 / 0 | 0.53 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-06 | 9 | 9 / 0 / 0 | 0.46 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-07 | 9 | 9 / 0 / 0 | 0.58 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-08 | 9 | 9 / 0 / 0 | 0.53 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-09 | 9 | 9 / 0 / 0 | 0.37 | - | - | 7.20 | see CSV |
| CH05 | 2026-09-10 | 9 | 9 / 0 / 0 | 0.38 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-11 | 9 | 9 / 0 / 0 | 0.48 | - | - | 0.00 | see CSV |
| CH05 | 2026-09-16 | 9 | 0 / 9 / 0 | 3.46 | - | - | 0.00 | see CSV |
| CH06 | 2026-08-30 | 9 | 8 / 1 / 0 | 2.77 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-08-31 | 9 | 8 / 1 / 0 | 2.86 | 2.54 | ok | 2.50 | see CSV |
| CH06 | 2026-09-01 | 9 | 9 / 0 / 0 | 1.41 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-02 | 9 | 9 / 0 / 0 | 1.26 | 2.54 | ok | 0.25 | see CSV |
| CH06 | 2026-09-03 | 9 | 9 / 0 / 0 | 0.25 | 2.54 | ok | 18.40 | see CSV |
| CH06 | 2026-09-04 | 9 | 9 / 0 / 0 | 0.63 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-05 | 9 | 9 / 0 / 0 | 2.30 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-06 | 9 | 9 / 0 / 0 | 1.39 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-07 | 9 | 8 / 1 / 0 | 2.63 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-08 | 9 | 9 / 0 / 0 | 1.44 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-09 | 9 | 9 / 0 / 0 | 2.38 | 2.54 | ok | 7.20 | see CSV |
| CH06 | 2026-09-10 | 9 | 9 / 0 / 0 | 2.00 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-11 | 9 | 9 / 0 / 0 | 1.81 | 2.54 | ok | 0.00 | see CSV |
| CH06 | 2026-09-16 | 9 | 9 / 0 / 0 | 1.84 | 2.54 | ok | 0.00 | see CSV |
| CH07 | 2026-08-30 | 19 | 6 / 8 / 0 | 4.38 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-08-31 | 20 | 9 / 9 / 0 | 4.67 | 0.00 | same frame | 2.50 | see CSV |
| CH07 | 2026-09-01 | 20 | 6 / 14 / 0 | inf | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-02 | 23 | 8 / 13 / 0 | 4.34 | 0.00 | same frame | 0.25 | see CSV |
| CH07 | 2026-09-03 | 26 | 16 / 8 / 0 | 1.06 | 3.89 | unreliable | 18.40 | see CSV |
| CH07 | 2026-09-04 | 26 | 20 / 5 / 0 | 2.45 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-05 | 25 | 11 / 11 / 0 | 5.63 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-06 | 23 | 4 / 16 / 0 | inf | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-07 | 23 | 4 / 18 / 0 | 5.17 | 3.89 | unreliable | 0.00 | see CSV |
| CH07 | 2026-09-08 | 23 | 4 / 18 / 0 | 12.08 | 3.89 | unreliable | 0.00 | see CSV |
| CH07 | 2026-09-09 | 23 | 8 / 14 / 0 | 4.30 | 3.89 | unreliable | 7.20 | see CSV |
| CH07 | 2026-09-10 | 23 | 7 / 15 / 0 | 4.36 | 3.89 | unreliable | 0.00 | see CSV |
| CH07 | 2026-09-11 | 19 | 3 / 14 / 0 | 106.77 | 0.00 | same frame | 0.00 | see CSV |
| CH07 | 2026-09-16 | 14 | 2 / 12 / 0 | 15.91 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-08-30 | 15 | 6 / 5 / 0 | 4.25 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-08-31 | 18 | 9 / 6 / 0 | 3.70 | 0.00 | same frame | 2.50 | see CSV |
| CH08 | 2026-09-01 | 22 | 11 / 9 / 0 | 2.35 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-02 | 28 | 19 / 7 / 0 | 2.08 | 4.55 | unreliable | 0.25 | see CSV |
| CH08 | 2026-09-03 | 28 | 25 / 1 / 0 | 0.89 | 4.55 | unreliable | 18.40 | see CSV |
| CH08 | 2026-09-04 | 28 | 26 / 0 / 0 | 1.28 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-05 | 32 | 27 / 0 / 0 | 1.23 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-06 | 29 | 25 / 0 / 0 | 0.80 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-07 | 28 | 25 / 0 / 0 | 1.16 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-08 | 28 | 25 / 1 / 0 | 1.02 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-09 | 28 | 25 / 1 / 0 | 1.21 | 0.00 | same frame | 7.20 | see CSV |
| CH08 | 2026-09-10 | 28 | 24 / 1 / 0 | 1.65 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-11 | 27 | 19 / 4 / 0 | 2.27 | 0.00 | same frame | 0.00 | see CSV |
| CH08 | 2026-09-16 | 27 | 2 / 23 / 0 | inf | 4.55 | unreliable | 0.00 | see CSV |
| CH08 | 2026-09-17 | 1 | 0 / 1 / 0 | inf | 0.00 | same frame | - | see CSV |

The shift itself is in the CSV (a13 / a23 are the translation terms at the image origin; landmark_track.params gives tx, ty at the frame centre). Nights 09-12 -> 09-15 have no video.
