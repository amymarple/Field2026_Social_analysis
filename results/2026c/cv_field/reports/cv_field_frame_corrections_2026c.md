# Frame corrections, whole-field cameras, nights (cohort `2026c`)

Generated 2026-10-02 05:31 by `cv/cv_field/frame_correction.py build` (method, columns, flags and lookup in its docstring). Table: `cv_field_frame_corrections_2026c.csv` (A = 09-18 px -> frame px, B = frame px -> 09-18 px; full-resolution upright pixels). Use `Corrections(cohort).to_paddock(cam, t, uv, z_mm=60)`.

Sources: CH01/CH02 night chain: `D:\Field2026_analysis_out\2026c\cv_field_landmark_night_20261002_0417`; CH03/CH04 from the 09-04 03:01 labels: `D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0304_ref0904night_hourly_20261002_0402`.

Precision (user, 2026-10-02): CH01/CH02 dawn closure <= 3 px on passing nights (< 1 cm); CH03/CH04 ~5-10 px (~1-2 cm). Sample rule (held-out median / p90): CH01/CH02 3 / 6 px, CH03/CH04 5 / 10 px. The 09-24 calibration's own error (76 mm median cross-camera) is separate and not reduced here.

Summary: CH01 98 ok / 0 sample / 26 night of 124; CH02 116 ok / 1 sample / 8 night of 125; CH03 102 ok / 22 sample / 0 night of 124; CH04 124 ok / 2 sample / 0 night of 126.

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

The shift itself is in the CSV (a13 / a23 are the translation terms at the image origin; landmark_track.params gives tx, ty at the frame centre). Nights 09-12 -> 09-15 have no video.
