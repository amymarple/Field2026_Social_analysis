# WILD offload QC — cohort `2026c`

Generated 2026-09-03T05:09:39+00:00 by `ephys/offload_qc_report.py` (git 2fbb2cf+dirty) from the session index (`ephys_spikes_session_index_2026c.csv`) and the PC-time fits under `E:\3rd_rat_spikes\analysis\pc_time`. Regenerate; do not hand-edit.

Definitions: see the docstring of `ephys/offload_qc_report.py` and the index's Definitions section (`ticks_per_s`, `tick_removal_frac`, `regime`, `noise_uV`, bad-channel rule). Times are the logger wallclock (field-PC local time at Resync, EDT).

## Firmware summary (measured, worst of 5 × 30-s windows per session)

| firmware | sessions | hours | ticks/s (median / max over sessions) | tick removal (min) | noise µV (median) | regimes |
|---|---|---|---|---|---|---|
| FM62 | 13 | 18.0 | 10061.7 / 54898.0 | 0.183 | 10.1 | broadband:6, normal:5, wide-impulse:2 |
| FM64 | 34 | 65.0 | 318.8 / 2068.4 | 0.787 | 10.8 | normal:34 |
| FM65 | 9 | 21.9 | 0.0 / 0.1 | 1.000 | 10.2 | normal:9 |

**FM65 verdict:** CLEAN — every FM65 session measures < 1 tick/s in its worst window (n = 9 sessions, max worst-window ticks/s = 0.07). FM64 sessions of the same loggers are the control.

## Per-animal timeline and continuity

### SF07 (logger D0DBEFEF3111) — 17 sessions, 44.0 h

| session | FW | start | end | dur | GB | rtc=folder | sidecars | measured (worst window) | ticks/s | removable | noise µV | bad ch | PC-time fit | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0_20260831_185816.804` | FM64 | 2026-08-31 18:58:16 | 2026-08-31 18:58:49 | 0:00:34 | 0.087 | True | ok | clean | 0.5 | 1.0 | 11.99 |  | start cluster only (8 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | measured clean on the probe window despite pre-FM65 firmware (de-glitch anyway) |
| `1_20260831_185904.795` | FM64 | 2026-08-31 18:59:04 | 2026-09-01 00:20:34 | 5:21:31 | 49.385 | True | ok | ambiguous | 6.23 | 1.0 | 12.95 |  | OK: 214 anchors, drift -23.9 ± 0.6 ppm, residual 33 ms |  |
| `2_20260901_002100.939` | FM64 | 2026-09-01 00:21:00 | 2026-09-01 05:41:07 | 5:20:07 | 49.17 | True | ok | glitchy | 13.0 | 0.975 | 12.43 |  | OK (chained next:4): drift -23.2 ± 78 ppm; start offset known to BLE precision |  |
| `3_20260901_054126.846` | FM64 | 2026-09-01 05:41:26 | 2026-09-01 06:36:23 | 0:54:57 | 8.441 | True | ok | glitchy | 13.1 | 0.94 | 15.42 |  | start cluster only (4 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `4_20260901_074925.529` | FM64 | 2026-09-01 07:49:25 | 2026-09-01 07:50:42 | 0:01:18 | 0.2 | True | ok | ambiguous | 1.6 | 1.0 | 10.88 |  | OK: 15 anchors, drift +49.4 ± 229.4 ppm, residual 18 ms | gap 73 min after previous |
| `5_20260901_075052.875` | FM64 | 2026-09-01 07:50:52 | 2026-09-01 12:54:26 | 5:03:35 | 46.63 | True | ok | glitchy | 16.63 | 1.0 | 8.49 |  | OK (chained next:8): drift -21.4 ± 82 ppm; start offset known to BLE precision |  |
| `6_20260901_125442.165` | FM64 | 2026-09-01 12:54:42 | 2026-09-01 17:11:59 | 4:17:18 | 39.52 | True | ok | glitchy | 21.1 | 1.0 | 8.7 |  | OK (chained next:7): drift +141.6 ± 97 ppm; start offset known to BLE precision |  |
| `7_20260901_171210.814` | FM64 | 2026-09-01 17:12:10 | 2026-09-01 18:19:42 | 1:07:33 | 10.375 | True | ok | ambiguous | 9.07 | 0.787 | 13.87 |  | start cluster only (7 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `8_20260901_192830.797` | FM65 | 2026-09-01 19:28:30 | 2026-09-01 19:29:02 | 0:00:32 | 0.083 | True | ok | clean | 0.0 | 1.0 | 12.15 |  | start cluster only (7 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 69 min after previous |
| `9_20260901_192912.215` | FM65 | 2026-09-01 19:29:12 | 2026-09-01 23:43:19 | 4:14:07 | 39.033 | True | ok | clean | 0.0 | 1.0 | 13.15 |  | OK: 26 anchors, drift -21.1 ± 1.0 ppm, residual 34 ms |  |
| `10_20260901_234332.691` | FM65 | 2026-09-01 23:43:32 | 2026-09-02 06:22:32 | 6:39:00 | 61.288 | True | ok | clean | 0.03 | 1.0 | 10.25 |  | OK: 19 anchors, drift -26.5 ± 1.0 ppm, residual 49 ms |  |
| `11_20260902_062241.295` | FM65 | 2026-09-02 06:22:41 | 2026-09-02 07:33:57 | 1:11:16 | 10.947 | True | ok | clean | 0.0 | 1.0 | 8.33 |  | OK: 10 anchors, drift -15.8 ± 4.6 ppm, residual 25 ms |  |
| `12_20260902_074608.443` | FM65 | 2026-09-02 07:46:08 | 2026-09-02 07:46:15 | 0:00:07 | 0.018 | True | ok | clean | 0.0 | 1.0 | 13.79 |  | start cluster only (3 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 12 min after previous |
| `13_20260902_082234.535` | FM65 | 2026-09-02 08:22:34 | 2026-09-02 08:23:06 | 0:00:32 | 0.082 | True | ok | clean | 0.0 | 1.0 | 12.8 |  | start cluster only (8 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 36 min after previous |
| `14_20260902_082315.755` | FM65 | 2026-09-02 08:23:15 | 2026-09-02 08:24:05 | 0:00:51 | 0.13 | True | ok | clean | 0.0 | 1.0 | 9.69 |  | inconsistent: drift 353.7 ppm |  |
| `15_20260902_082418.755` | FM65 | 2026-09-02 08:24:18 | 2026-09-02 16:55:02 | 8:30:45 | 78.45 | True | ok | clean | 0.0 | 1.0 | 8.89 |  | OK (chained next:9): drift -21.3 ± 49 ppm; start offset known to BLE precision |  |
| `16_20260902_165524.033` | FM65 | 2026-09-02 16:55:24 | 2026-09-02 18:12:49 | 1:17:26 | 11.893 | True | ok | clean | 0.07 | 1.0 | 8.94 |  | start cluster only (9 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |

### SF08 (logger 128C2F27E131) — 9 sessions, 12.9 h

| session | FW | start | end | dur | GB | rtc=folder | sidecars | measured (worst window) | ticks/s | removable | noise µV | bad ch | PC-time fit | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0_20260831_070148.859` | FM62 | 2026-08-31 07:01:48 | 2026-08-31 07:12:26 | 0:10:39 | 1.635 | True | ok | glitchy+broadband | 34988.23 | 0.183 | 12.9 |  | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| `1_20260831_071239.713` | FM62 | 2026-08-31 07:12:39 | 2026-08-31 07:15:31 | 0:02:52 | 0.441 | True | ok | glitchy | 2012.73 | 1.0 | 8.49 | 32 | inconsistent: drift 13273.1 ppm |  |
| `2_20260831_071541.642` | FM62 | 2026-08-31 07:15:41 | 2026-08-31 08:30:54 | 1:15:14 | 11.556 | True | ok | glitchy+broadband | 15120.33 | 0.399 | 14.32 | 32 52 53 61 | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| `3_20260831_083101.996` | FM62 | 2026-08-31 08:31:01 | 2026-08-31 08:31:06 | 0:00:05 | 0.013 | True | ok | glitchy | 1233.48 | 1.0 | 8.45 | 32 | no anchors (logger never BLE-connected) |  |
| `4_20260831_083120.285` | FM62 | 2026-08-31 08:31:20 | 2026-08-31 11:26:31 | 2:55:12 | 26.911 | True | ok | glitchy+wide-impulse | 6051.8 | 0.406 | 8.57 | 32 | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| `0_20260831_190133.486` | FM64 | 2026-08-31 19:01:33 | 2026-08-31 19:02:18 | 0:00:45 | 0.116 | True | ok | glitchy | 287.7 | 1.0 | 10.4 | 32 | inconsistent: drift -392.6 ppm | gap 455 min after previous |
| `1_20260831_190229.919` | FM64 | 2026-08-31 19:02:29 | 2026-09-01 00:23:11 | 5:20:42 | 49.261 | True | ok | glitchy | 678.9 | 1.0 | 10.94 | 32 | OK: 297 anchors, drift -17.6 ± 0.6 ppm, residual 20 ms |  |
| `2_20260901_002327.839` | FM64 | 2026-09-01 00:23:27 | 2026-09-01 03:32:05 | 3:08:39 | 28.976 | True | ok | glitchy | 1247.83 | 1.0 | 10.89 | 32 | start cluster only (5 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `3_20260901_054222.420` | FM64 | 2026-09-01 05:42:22 | 2026-09-01 05:44:26 | 0:02:05 | 0.32 | True | ok | glitchy | 666.57 | 1.0 | 10.8 | 32 | start cluster only (4 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 130 min after previous |

### SF09 (logger 68BDFFFF62DB) — 8 sessions, 12.9 h

| session | FW | start | end | dur | GB | rtc=folder | sidecars | measured (worst window) | ticks/s | removable | noise µV | bad ch | PC-time fit | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0_20260831_070319.133` | FM62 | 2026-08-31 07:03:19 | 2026-08-31 07:13:46 | 0:10:28 | 1.606 | True | ok | glitchy+broadband | 14983.0 | 0.22 | 12.85 | 2 4 32 54 56 58 62 | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| `1_20260831_071357.350` | FM62 | 2026-08-31 07:13:57 | 2026-08-31 11:29:21 | 4:15:25 | 39.232 | True | ok | glitchy+wide-impulse | 10061.67 | 0.237 | 13.48 | 2 4 32 36 54 56 58 62 | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| `0_20260831_190404.508` | FM64 | 2026-08-31 19:04:04 | 2026-08-31 19:05:10 | 0:01:06 | 0.169 | True | ok | glitchy | 314.97 | 0.958 | 8.26 | 2 4 32 36 52 54 56 58 60 62 | OK: 14 anchors, drift +66.1 ± 175.1 ppm, residual 12 ms | gap 455 min after previous |
| `1_20260831_190522.711` | FM64 | 2026-08-31 19:05:22 | 2026-08-31 19:05:57 | 0:00:36 | 0.092 | True | ok | glitchy | 318.8 | 0.964 | 8.42 | 2 4 32 36 52 54 56 58 60 62 | start cluster only (9 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `2_20260831_190743.879` | FM64 | 2026-08-31 19:07:43 | 2026-08-31 19:08:22 | 0:00:40 | 0.101 | True | ok | glitchy | 289.1 | 0.959 | 10.41 | 2 4 32 36 52 54 56 58 60 62 | start cluster only (9 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `3_20260831_190834.640` | FM64 | 2026-08-31 19:08:34 | 2026-09-01 00:24:57 | 5:16:23 | 48.597 | True | ok | glitchy | 326.1 | 0.963 | 11.77 | 2 4 32 36 54 56 58 62 | OK (chained next:9): drift -24.6 ± 79 ppm; start offset known to BLE precision |  |
| `4_20260901_002514.385` | FM64 | 2026-09-01 00:25:14 | 2026-09-01 03:34:27 | 3:09:14 | 29.066 | True | ok | glitchy | 365.87 | 0.971 | 12.68 | 2 4 32 36 54 56 58 62 | start cluster only (9 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `5_20260901_054317.203` | FM64 | 2026-09-01 05:43:17 | 2026-09-01 05:44:33 | 0:01:16 | 0.195 | True | ok | glitchy | 457.73 | 0.936 | 8.22 | 2 4 32 36 52 54 56 58 60 62 | start cluster only (4 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 129 min after previous |

### SF10 (logger CACB6D600151) — 8 sessions, 12.2 h

| session | FW | start | end | dur | GB | rtc=folder | sidecars | measured (worst window) | ticks/s | removable | noise µV | bad ch | PC-time fit | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0_20260831_070700.822` | FM62 | 2026-08-31 07:07:00 | 2026-08-31 07:17:17 | 0:10:18 | 1.582 | True | ok | glitchy | 2447.17 | 1.0 | 10.12 | 2 6 32 34 | inconsistent: drift -2689.5 ppm |  |
| `1_20260831_071948.008` | FM62 | 2026-08-31 07:19:48 | 2026-08-31 11:26:40 | 4:06:53 | 37.92 | True | ok | glitchy | 2004.87 | 1.0 | 10.18 | 2 6 32 34 56 | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time |  |
| `0_20260831_190956.580` | FM64 | 2026-08-31 19:09:56 | 2026-08-31 19:10:31 | 0:00:35 | 0.091 | True | ok | glitchy | 698.57 | 1.0 | 8.24 | 2 6 32 34 62 63 | start cluster only (8 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 463 min after previous |
| `1_20260831_191045.259` | FM64 | 2026-08-31 19:10:45 | 2026-08-31 19:55:31 | 0:44:46 | 6.877 | True | ok | glitchy | 1886.63 | 1.0 | 11.09 | 6 32 34 | OK: 14 anchors, drift -19.8 ± 1.3 ppm, residual 6 ms |  |
| `2_20260831_195630.973` | FM64 | 2026-08-31 19:56:30 | 2026-09-01 00:26:50 | 4:30:21 | 41.526 | True | ok | glitchy | 1804.93 | 1.0 | 9.77 | 2 32 34 56 | OK: 384 anchors, drift -21.6 ± 0.2 ppm, residual 10 ms |  |
| `3_20260901_002703.626` | FM64 | 2026-09-01 00:27:03 | 2026-09-01 00:27:08 | 0:00:05 | 0.014 | True | ok | glitchy | 367.48 | 1.0 | 9.0 | 2 32 34 56 | start cluster only (2 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `4_20260901_002730.117` | FM64 | 2026-09-01 00:27:30 | 2026-09-01 03:07:22 | 2:39:52 | 24.556 | True | ok | glitchy | 2068.37 | 1.0 | 10.23 | 2 32 34 56 | start cluster only (9 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `5_20260901_054403.494` | FM64 | 2026-09-01 05:44:03 | 2026-09-01 05:44:52 | 0:00:50 | 0.128 | True | ok | glitchy | 558.5 | 0.996 | 8.71 | 32 34 60 62 | start cluster only (7 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 157 min after previous |

### SF11 (logger 1DFE7F77721C) — 7 sessions, 8.7 h

| session | FW | start | end | dur | GB | rtc=folder | sidecars | measured (worst window) | ticks/s | removable | noise µV | bad ch | PC-time fit | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0_20260831_072408.414` | FM62 | 2026-08-31 07:24:08 | 2026-08-31 07:57:36 | 0:33:28 | 5.142 | True | ok | glitchy+broadband | 54897.97 | 0.245 | 8.67 | 38 39 43 52 54 56 58 59 61 | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| `0_20260831_191252.932` | FM64 | 2026-08-31 19:12:52 | 2026-08-31 19:13:30 | 0:00:39 | 0.099 | True | ok | glitchy | 204.07 | 1.0 | 8.18 |  | start cluster only (8 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 675 min after previous |
| `1_20260831_191341.611` | FM64 | 2026-08-31 19:13:41 | 2026-09-01 00:28:51 | 5:15:10 | 48.41 | True | ok | glitchy | 319.2 | 1.0 | 11.14 |  | OK (chained next:13): drift -20.9 ± 79 ppm; start offset known to BLE precision |  |
| `2_20260901_002906.850` | FM64 | 2026-09-01 00:29:06 | 2026-09-01 03:21:52 | 2:52:47 | 26.539 | True | ok | glitchy | 507.03 | 1.0 | 12.04 |  | start cluster only (13 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `3_20260901_054537.933` | FM64 | 2026-09-01 05:45:37 | 2026-09-01 05:46:35 | 0:00:58 | 0.149 | True | ok | glitchy | 141.03 | 1.0 | 9.07 | 32 56 60 | start cluster only (6 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 144 min after previous |
| `4_20260901_054836.484` | FM64 | 2026-09-01 05:48:36 | 2026-09-01 05:48:46 | 0:00:11 | 0.027 | True | ok | glitchy | 97.24 | 1.0 | 11.01 | 32 56 60 | start cluster only (3 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `5_20260901_054906.988` | FM64 | 2026-09-01 05:49:06 | 2026-09-01 05:49:16 | 0:00:11 | 0.028 | True | ok | glitchy | 138.44 | 1.0 | 11.2 | 32 56 60 62 | start cluster only (3 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |

### SF12 (logger FBED2F2321B1) — 7 sessions, 14.0 h

| session | FW | start | end | dur | GB | rtc=folder | sidecars | measured (worst window) | ticks/s | removable | noise µV | bad ch | PC-time fit | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0_20260831_070947.667` | FM62 | 2026-08-31 07:09:47 | 2026-08-31 07:10:24 | 0:00:37 | 0.095 | True | ok | glitchy | 536.37 | 1.0 | 13.04 | 58 60 | start cluster only (6 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `1_20260831_071033.005` | FM62 | 2026-08-31 07:10:33 | 2026-08-31 07:18:29 | 0:07:56 | 1.219 | True | ok | glitchy+broadband | 24440.47 | 0.389 | 7.98 |  | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| `2_20260831_071845.540` | FM62 | 2026-08-31 07:18:45 | 2026-08-31 11:27:26 | 4:08:41 | 38.199 | True | ok | glitchy+broadband | 15905.97 | 0.231 | 7.85 |  | CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| `1_20260831_191521.024` | FM64 | 2026-08-31 19:15:21 | 2026-08-31 19:15:56 | 0:00:36 | 0.092 | True | ok | glitchy | 177.5 | 0.999 | 10.63 |  | start cluster only (9 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 468 min after previous |
| `2_20260831_191613.417` | FM64 | 2026-08-31 19:16:13 | 2026-09-01 00:30:37 | 5:14:24 | 48.292 | True | ok | glitchy | 572.47 | 1.0 | 8.48 |  | OK (chained next:10): drift -18.6 ± 79 ppm; start offset known to BLE precision |  |
| `3_20260901_003050.862` | FM64 | 2026-09-01 00:30:50 | 2026-09-01 04:57:35 | 4:26:45 | 40.973 | True | ok | glitchy | 502.8 | 0.995 | 11.29 |  | start cluster only (10 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions |  |
| `4_20260901_054714.722` | FM64 | 2026-09-01 05:47:14 | 2026-09-01 05:49:03 | 0:01:50 | 0.282 | True | ok | glitchy | 261.9 | 1.0 | 8.03 |  | start cluster only (8 anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions | gap 50 min after previous |

## Field-PC-time fit overview (sessions >= 1 h)

Source: `ephys/pc_time_chain.py` (day-wrap-aware, delay word not added, adjacent-session anchors chained through the RTC). The reference generator's per-session fits are superseded: it mis-handles the 86,400,000-ms day wrap (post-midnight anchors land 416.77 s early after the 2^20 packing) and adds a delay word that shifts anchors by 0.7–2.6 s.

| verdict | sessions | hours |
|---|---|---|
| OK (chained through the next session's start) | 7 | 39.0 |
| OK | 6 | 27.3 |
| start cluster only (offset known, drift assumed) | 7 | 18.7 |
| CORRUPT SYNC LANES | 5 | 16.7 |

## Problems and flags

- noise regime broadband: SF11 `0_20260831_072408.414` (FM62, windows broadband,normal,wide-impulse,wide-impulse,normal, removal 0.245)
- noise regime broadband: SF12 `1_20260831_071033.005` (FM62, windows wide-impulse,broadband,normal,broadband,normal, removal 0.389)
- noise regime broadband: SF12 `2_20260831_071845.540` (FM62, windows broadband,normal,normal,normal,broadband, removal 0.231)
- noise regime broadband: SF08 `0_20260831_070148.859` (FM62, windows broadband,wide-impulse,wide-impulse,wide-impulse,normal, removal 0.183)
- noise regime broadband: SF08 `2_20260831_071541.642` (FM62, windows wide-impulse,broadband,broadband,broadband,broadband, removal 0.399)
- noise regime wide-impulse: SF08 `4_20260831_083120.285` (FM62, windows normal,normal,normal,wide-impulse,normal, removal 0.406)
- noise regime broadband: SF09 `0_20260831_070319.133` (FM62, windows wide-impulse,broadband,wide-impulse,wide-impulse,wide-impulse, removal 0.22)
- noise regime wide-impulse: SF09 `1_20260831_071357.350` (FM62, windows normal,wide-impulse,normal,wide-impulse,wide-impulse, removal 0.237)
- PC-time: SF08 `0_20260831_070148.859` (0.2 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time
- PC-time: SF08 `2_20260831_071541.642` (1.3 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time
- PC-time: SF08 `4_20260831_083120.285` (2.9 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time
- PC-time: SF09 `0_20260831_070319.133` (0.2 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time
- PC-time: SF09 `1_20260831_071357.350` (4.3 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time
- PC-time: SF10 `0_20260831_070700.822` (0.2 h): inconsistent: drift -2689.5 ppm
- PC-time: SF10 `1_20260831_071948.008` (4.1 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time
- PC-time: SF11 `0_20260831_072408.414` (0.6 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time
- PC-time: SF12 `2_20260831_071845.540` (4.1 h): CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time

## How to read

- `deglitch?`/firmware < 65 sessions must be staged (`ephys/stage_session.py`) before analysis; FM65 sessions are copied verbatim.
- A `wide-impulse` / `broadband` regime is not fixed by de-glitching: exclude or QC by hand.
- 'PC time' = the FIELD recording PC's clock (BLE master), embedded in each logger's analogin.dat; nothing from the analysis PC enters the fit. A fit marked OK gives a session-level field-PC-time coordinate (BLE precision, ~10–100 ms); sub-ms alignment needs the LED edges. Gaps between sessions are battery rounds unless noted.
