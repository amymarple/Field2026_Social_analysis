# Night reference by dusk hand-off + dawn closure (cohort `2026c`, night 2026-09-03 -> 2026-09-04)

Generated 2026-10-01 17:58 by `cv/cv_field/landmark_night.py` (method and definitions in its docstring). Bulk: `D:\Field2026_analysis_out\2026c\cv_field_landmark_night_20261001_1627` (brightness plots/CSVs, frames, overlays, `handoff.csv`, `night_frames.csv`). Test plan agreed with the user 2026-10-01: pass = dawn closure median <= 2 px with all three fits ok; the user reviews the 03:01 overlays. **This report makes no visual claim.**

## Hand-off and dawn closure

| camera | dusk switch (pre -> post) | z / z2 | pre frame (status, held px) | night ref | sat pre / ref | dawn switch | dawn frames (night / day, gap s) | closure median / max px | verdict |
|---|---|---|---|---|---|---|---|---|---|
| CH01 | 20:07:35 -> 20:07:43 | 1101.30 / 717.20 | 19:52:35 (unreliable, 2.65) | 20:08:04 | 0.00 / 0.00 | 06:59:33 -> 06:59:33 |  (-) /  (-), - | - / - | **dawn closure not computable (a side did not fit)** |
| CH02 | 20:03:06 -> 20:03:13 | 2973.50 / 2539.30 | 19:48:06 (ok, 1.70) | 20:03:23 | 0.00 / 0.00 | 06:50:42 -> 06:50:50 | 06:50:44 (ok) / 06:51:02 (ok), 18.00 | 1.42 / 3.51 | **PASS** |
| CH03 | 19:01:34 -> 19:01:43 | 625.60 / 623.40 | 19:00:34 (ok, 2.62) | 19:02:24 | 0.00 / 0.00 | 07:25:25 -> 07:25:33 | 07:25:25 (unreliable) / 07:25:43 (ok), 18.00 | 92.49 / 181.98 | **FAIL** |
| CH04 | 19:31:49 -> 19:31:51 | 50.30 / 42.10 | 19:30:49 (ok, 2.78) | 19:32:01 | 0.00 / 0.00 | 07:25:22 -> 07:25:30 | 07:25:22 (ok) / 07:25:40 (unreliable), 18.00 | 53.81 / 214.94 | **FAIL** |

## Night frames (tracked from the night reference; shift vs the 09-18 reference)

| camera | frame | status | fit units | held-out median / p90 px | tx px | ty px | rot deg | scale | dropped | overlay |
|---|---|---|---|---|---|---|---|---|---|---|
| CH01 | 2026-09-03 21:00:00 | unreliable | 1 | - / - | +nan | +nan | +nan | nan | 0 | `overlays/CH01_20260903_210000_night.jpg` |
| CH01 | 2026-09-04 00:00:00 | unreliable | 3 | - / - | +nan | +nan | +nan | nan | 0 | `overlays/CH01_20260904_000000_night.jpg` |
| CH01 | 2026-09-04 03:01:00 | unreliable | 4 | - / - | +nan | +nan | +nan | nan | 0 | `overlays/CH01_20260904_030100_night.jpg` |
| CH02 | 2026-09-03 21:00:00 | ok | 20 | 0.35 / 0.56 | +1.9 | +0.2 | +0.050 | 1.0013 | 0 | `overlays/CH02_20260903_210000_night.jpg` |
| CH02 | 2026-09-04 00:00:00 | ok | 20 | 1.44 / 3.90 | +14.6 | -0.7 | -0.065 | 1.0010 | 0 | `overlays/CH02_20260904_000000_night.jpg` |
| CH02 | 2026-09-04 03:01:00 | ok | 20 | 1.54 / 3.41 | +18.2 | -1.2 | -0.068 | 1.0016 | 0 | `overlays/CH02_20260904_030100_night.jpg` |
| CH03 | 2026-09-03 21:00:00 | unreliable | 5 | 25.54 / 43.13 | -190.1 | -236.0 | +6.982 | 0.8888 | 4 | `overlays/CH03_20260903_210000_night.jpg` |
| CH03 | 2026-09-04 00:00:00 | unreliable | 5 | 42.46 / 81.07 | +65.4 | -91.7 | -5.229 | 0.9695 | 4 | `overlays/CH03_20260904_000000_night.jpg` |
| CH03 | 2026-09-04 03:01:00 | unreliable | 3 | 230.23 / 333.42 | -134.0 | +125.5 | +1.042 | 1.0634 | 4 | `overlays/CH03_20260904_030100_night.jpg` |
| CH04 | 2026-09-03 21:00:00 | unreliable | 4 | 14.56 / 24.33 | +43.4 | -15.7 | +0.091 | 0.9958 | 7 | `overlays/CH04_20260903_210000_night.jpg` |
| CH04 | 2026-09-04 00:00:00 | unreliable | 4 | 8.64 / 92.04 | +15.4 | -33.9 | +1.583 | 0.9948 | 7 | `overlays/CH04_20260904_000000_night.jpg` |
| CH04 | 2026-09-04 03:01:00 | unreliable | 4 | 14.14 / 27.40 | +65.1 | -66.4 | -1.898 | 0.9758 | 7 | `overlays/CH04_20260904_030100_night.jpg` |

Overlays: red = the 09-18 labels as drawn, green = fit units moved by the total map, cyan = houses (validation), orange = occludable pieces dropped in that frame; nails are circles. sat = mean HSV saturation (IR / monochrome ~0-6, colour > 12).
