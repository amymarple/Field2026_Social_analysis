# WILD neurologger session index — cohort `2026c`

Generated 2026-09-03T03:04:31+00:00 by `ephys/build_session_index.py` (git 2fbb2cf+dirty) from `E:\3rd_rat_spikes`. Machine-readable twin: `ephys_spikes_session_index_2026c.csv`. Regenerate; do not hand-edit.

## Firmware provenance (the rule that decides what may be analysed)

- `firmware` is read from each session's `CE_params.bin` (uint16 at byte 328). `deglitch_required = firmware < 65` (`clean_firmware_min` in `cohorts/2026c.yaml`).
- **FM62** — stop-only commit (session exists only after a clean Record Stop) + glitch defects A/B
- **FM64** — glitch defects A/B (~100-1400 ticks/s summed over 64 ch); stop-only commit
- **FM65** — maker fix: defects absent on bench; power-cut-safe commit; field data unevaluated
- `recovery.bin` (per animal) = raw card image kept for a FUTURE recovery of the FM59–62 uncommitted (stop-only-commit) sessions; never parsed here.

## Definitions

| quantity | formula | plain text |
|---|---|---|
| `duration_s` | `n_samples / fs`, `n_samples = bytes(amplifier.dat) / (2·n_channels)` | recorded length from the int16 file size; `end_local = start_local + duration_s` (logger wallclock, EDT) |
| glitch sample | `\|x_c(t) − med5_c(t)\| > max(10.0·1.4826·MAD_c, 500.0 ADC)` | sample deviating from its 5-point running median beyond a per-channel robust threshold; this is exactly what de-glitching replaces |
| `ticks_per_s` | `#{ \|x(t) − (x(t−1)+x(t+1))/2\| > 1200 ADC } / probe_seconds`, summed over channels | the defects-note impulse metric; ~100–1400/s on FM62/64 sessions, ~0 expected on clean data |
| `measured_verdict` | glitchy if `ticks_per_s > 10`, clean if `< 1`, else ambiguous; suffixed `+wide-impulse` / `+broadband` when the regime is not normal | data-side evidence from `probe_windows` windows of 30 s spread over the file (session values = WORST window: max ticks/s, min removal, max std; `regime_by_window` lists each window); checks the firmware rule rather than assuming it |
| `regime` | `broadband` if `raw_std_median_adc > 2500`; `wide-impulse` if `ticks_per_s > 100` and `tick_removal_frac < 0.9`; else `normal` | whether the impulses are the 1–2-sample FM62/64 defect (removable by the 5-point median) or something wider / a noise blow-up that de-glitching cannot fix |
| `tick_removal_frac` | `1 − ticks(after de-glitch of the window) / ticks(before)` | fraction of impulses the median rule actually removes; the FM64 defect gives ≈ 0.997 |
| `raw_std_median_adc` | median over channels of `std(x)` on the probe window | broadband level; clean night sessions ≈ 550–1000 ADC |
| `noise_uV_median` | median over channels of `1.4826·median\|hp\|·0.195 µV/ADC`, hp = 500–5000 Hz of the de-glitched window | robust spike-band noise floor (µV, RELATIVE: the 0.195 µV/ADC Intan default is unverified for WILD) |
| `bad_channel_candidates` | `noise_uV < 3` or `noise_uV > 4·median` or `raw_std < 0.25·median` | advisory dead/broken channels for `probes_<cohort>.yaml` `reject_channels` |
| `time_dat_ok` / `analogin_ok` | `bytes(time.dat) = 4·n_samples`; `bytes(analogin.dat) = 2·n_samples` (16 lanes @ fs/16) | sidecar sizes consistent with the amplifier stream |

## Per-animal summary

| animal | logger MAC | sessions | hours offloaded | firmware seen | recovery.bin (GB) |
|---|---|---|---|---|---|
| SF10 | CACB6D600151 | 8 | 12.23 | FM62, FM64 | 512.7 |
| SF11 | 1DFE7F77721C | 7 | 8.72 | FM62, FM64 | 512.1 |
| SF12 | FBED2F2321B1 | 7 | 14.01 | FM62, FM64 | 512.1 |
| SF7 | D0DBEFEF3111 | 17 | 44.02 | FM64, FM65 | 512.1 |
| SF8 | 128C2F27E131 | 9 | 12.94 | FM62, FM64 | 512.1 |
| SF9 | 68BDFFFF62DB | 8 | 12.92 | FM62, FM64 | 512.1 |

**56 sessions indexed: 47 require de-glitching (firmware < FM65), 9 flagged clean by firmware.**

## Sessions

| animal | session | start (local) | end (local) | dur | GB | FW | deglitch? | measured (worst window) | regime by window | ticks/s | removable | raw std | noise µV | bad ch cand. | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF10 | `0_20260831_070700.822` | 2026-08-31 07:07:00.822 | 2026-08-31 07:17:18 | 0:10:18 | 1.582 | FM62 | YES | glitchy | normal,normal,normal,normal,normal | 2447.17 | 1.0 | 1440.0 | 10.12 | 2 6 32 34 |  |
| SF10 | `1_20260831_071948.008` | 2026-08-31 07:19:48.008 | 2026-08-31 11:26:40 | 4:06:53 | 37.92 | FM62 | YES | glitchy | normal,normal,normal,normal,normal | 2004.87 | 1.0 | 1250.0 | 10.18 | 2 6 32 34 56 |  |
| SF10 | `0_20260831_190956.580` | 2026-08-31 19:09:56.580 | 2026-08-31 19:10:32 | 0:00:35 | 0.091 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 698.57 | 1.0 | 1194.0 | 8.24 | 2 6 32 34 62 63 |  |
| SF10 | `1_20260831_191045.259` | 2026-08-31 19:10:45.259 | 2026-08-31 19:55:31 | 0:44:46 | 6.877 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1886.63 | 1.0 | 1246.0 | 11.09 | 6 32 34 |  |
| SF10 | `2_20260831_195630.973` | 2026-08-31 19:56:30.973 | 2026-09-01 00:26:51 | 4:30:21 | 41.526 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1804.93 | 1.0 | 1320.0 | 9.77 | 2 32 34 56 |  |
| SF10 | `3_20260901_002703.626` | 2026-09-01 00:27:03.626 | 2026-09-01 00:27:09 | 0:00:05 | 0.014 | FM64 | YES | glitchy | normal | 367.48 | 1.0 | 608.0 | 9.0 | 2 32 34 56 |  |
| SF10 | `4_20260901_002730.117` | 2026-09-01 00:27:30.117 | 2026-09-01 03:07:22 | 2:39:52 | 24.556 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 2068.37 | 1.0 | 1295.0 | 10.23 | 2 32 34 56 |  |
| SF10 | `5_20260901_054403.494` | 2026-09-01 05:44:03.494 | 2026-09-01 05:44:53 | 0:00:50 | 0.128 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 558.5 | 0.996 | 671.0 | 8.71 | 32 34 60 62 |  |
| SF11 | `0_20260831_072408.414` | 2026-08-31 07:24:08.414 | 2026-08-31 07:57:36 | 0:33:28 | 5.142 | FM62 | YES | glitchy+broadband | broadband,normal,wide-impulse,wide-impulse,normal | 54897.97 | 0.245 | 5302.0 | 8.67 | 38 39 43 52 54 56 58 59 61 | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF11 | `0_20260831_191252.932` | 2026-08-31 19:12:52.932 | 2026-08-31 19:13:31 | 0:00:39 | 0.099 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 204.07 | 1.0 | 1394.0 | 8.18 |  |  |
| SF11 | `1_20260831_191341.611` | 2026-08-31 19:13:41.611 | 2026-09-01 00:28:51 | 5:15:10 | 48.41 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 319.2 | 1.0 | 1472.0 | 11.14 |  |  |
| SF11 | `2_20260901_002906.850` | 2026-09-01 00:29:06.850 | 2026-09-01 03:21:53 | 2:52:47 | 26.539 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 507.03 | 1.0 | 1657.0 | 12.04 |  |  |
| SF11 | `3_20260901_054537.933` | 2026-09-01 05:45:37.933 | 2026-09-01 05:46:36 | 0:00:58 | 0.149 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 141.03 | 1.0 | 585.0 | 9.07 | 32 56 60 |  |
| SF11 | `4_20260901_054836.484` | 2026-09-01 05:48:36.484 | 2026-09-01 05:48:47 | 0:00:11 | 0.027 | FM64 | YES | glitchy | normal | 97.24 | 1.0 | 600.0 | 11.01 | 32 56 60 |  |
| SF11 | `5_20260901_054906.988` | 2026-09-01 05:49:06.988 | 2026-09-01 05:49:17 | 0:00:11 | 0.028 | FM64 | YES | glitchy | normal | 138.44 | 1.0 | 617.0 | 11.2 | 32 56 60 62 |  |
| SF12 | `0_20260831_070947.667` | 2026-08-31 07:09:47.667 | 2026-08-31 07:10:24 | 0:00:37 | 0.095 | FM62 | YES | glitchy | normal,normal,normal,normal,normal | 536.37 | 1.0 | 921.0 | 13.04 | 58 60 |  |
| SF12 | `1_20260831_071033.005` | 2026-08-31 07:10:33.005 | 2026-08-31 07:18:29 | 0:07:56 | 1.219 | FM62 | YES | glitchy+broadband | wide-impulse,broadband,normal,broadband,normal | 24440.47 | 0.389 | 4763.0 | 7.98 |  | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF12 | `2_20260831_071845.540` | 2026-08-31 07:18:45.540 | 2026-08-31 11:27:26 | 4:08:41 | 38.199 | FM62 | YES | glitchy+broadband | broadband,normal,normal,normal,broadband | 15905.97 | 0.231 | 3460.0 | 7.85 |  | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF12 | `1_20260831_191521.024` | 2026-08-31 19:15:21.024 | 2026-08-31 19:15:56 | 0:00:36 | 0.092 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 177.5 | 0.999 | 795.0 | 10.63 |  |  |
| SF12 | `2_20260831_191613.417` | 2026-08-31 19:16:13.417 | 2026-09-01 00:30:37 | 5:14:24 | 48.292 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 572.47 | 1.0 | 1249.0 | 8.48 |  |  |
| SF12 | `3_20260901_003050.862` | 2026-09-01 00:30:50.862 | 2026-09-01 04:57:36 | 4:26:45 | 40.973 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 502.8 | 0.995 | 1148.0 | 11.29 |  |  |
| SF12 | `4_20260901_054714.722` | 2026-09-01 05:47:14.722 | 2026-09-01 05:49:04 | 0:01:50 | 0.282 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 261.9 | 1.0 | 1021.0 | 8.03 |  |  |
| SF7 | `0_20260831_185816.804` | 2026-08-31 18:58:16.804 | 2026-08-31 18:58:50 | 0:00:34 | 0.087 | FM64 | YES | clean | normal,normal,normal,normal,normal | 0.5 | 1.0 | 619.0 | 11.99 |  | measured clean on the probe window despite pre-FM65 firmware (de-glitch anyway) |
| SF7 | `1_20260831_185904.795` | 2026-08-31 18:59:04.795 | 2026-09-01 00:20:35 | 5:21:31 | 49.385 | FM64 | YES | ambiguous | normal,normal,normal,normal,normal | 6.23 | 1.0 | 788.0 | 12.95 |  |  |
| SF7 | `2_20260901_002100.939` | 2026-09-01 00:21:00.939 | 2026-09-01 05:41:08 | 5:20:07 | 49.17 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 13.0 | 0.975 | 983.0 | 12.43 |  |  |
| SF7 | `3_20260901_054126.846` | 2026-09-01 05:41:26.846 | 2026-09-01 06:36:24 | 0:54:57 | 8.441 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 13.1 | 0.94 | 895.0 | 15.42 |  |  |
| SF7 | `4_20260901_074925.529` | 2026-09-01 07:49:25.529 | 2026-09-01 07:50:43 | 0:01:18 | 0.2 | FM64 | YES | ambiguous | normal,normal,normal,normal,normal | 1.6 | 1.0 | 650.0 | 10.88 |  |  |
| SF7 | `5_20260901_075052.875` | 2026-09-01 07:50:52.875 | 2026-09-01 12:54:27 | 5:03:35 | 46.63 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 16.63 | 1.0 | 1196.0 | 8.49 |  |  |
| SF7 | `6_20260901_125442.165` | 2026-09-01 12:54:42.165 | 2026-09-01 17:11:59 | 4:17:18 | 39.52 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 21.1 | 1.0 | 1002.0 | 8.7 |  |  |
| SF7 | `7_20260901_171210.814` | 2026-09-01 17:12:10.814 | 2026-09-01 18:19:43 | 1:07:33 | 10.375 | FM64 | YES | ambiguous | normal,normal,normal,normal,normal | 9.07 | 0.787 | 786.0 | 13.87 |  |  |
| SF7 | `8_20260901_192830.797` | 2026-09-01 19:28:30.797 | 2026-09-01 19:29:03 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 707.0 | 12.15 |  |  |
| SF7 | `9_20260901_192912.215` | 2026-09-01 19:29:12.215 | 2026-09-01 23:43:19 | 4:14:07 | 39.033 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 749.0 | 13.15 |  |  |
| SF7 | `10_20260901_234332.691` | 2026-09-01 23:43:32.691 | 2026-09-02 06:22:33 | 6:39:00 | 61.288 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1162.0 | 10.25 |  |  |
| SF7 | `11_20260902_062241.295` | 2026-09-02 06:22:41.295 | 2026-09-02 07:33:57 | 1:11:16 | 10.947 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1325.0 | 8.33 |  |  |
| SF7 | `12_20260902_074608.443` | 2026-09-02 07:46:08.443 | 2026-09-02 07:46:15 | 0:00:07 | 0.018 | FM65 | no | clean | normal | 0.0 | 1.0 | 609.0 | 13.79 |  |  |
| SF7 | `13_20260902_082234.535` | 2026-09-02 08:22:34.535 | 2026-09-02 08:23:06 | 0:00:32 | 0.082 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 742.0 | 12.8 |  |  |
| SF7 | `14_20260902_082315.755` | 2026-09-02 08:23:15.755 | 2026-09-02 08:24:06 | 0:00:51 | 0.13 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 653.0 | 9.69 |  |  |
| SF7 | `15_20260902_082418.755` | 2026-09-02 08:24:18.755 | 2026-09-02 16:55:03 | 8:30:45 | 78.45 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1200.0 | 8.89 |  |  |
| SF7 | `16_20260902_165524.033` | 2026-09-02 16:55:24.033 | 2026-09-02 18:12:49 | 1:17:26 | 11.893 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 1001.0 | 8.94 |  |  |
| SF8 | `0_20260831_070148.859` | 2026-08-31 07:01:48.859 | 2026-08-31 07:12:27 | 0:10:39 | 1.635 | FM62 | YES | glitchy+broadband | broadband,wide-impulse,wide-impulse,wide-impulse,normal | 34988.23 | 0.183 | 5178.0 | 12.9 |  | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF8 | `1_20260831_071239.713` | 2026-08-31 07:12:39.713 | 2026-08-31 07:15:31 | 0:02:52 | 0.441 | FM62 | YES | glitchy | normal,normal,normal,normal,normal | 2012.73 | 1.0 | 1395.0 | 8.49 | 32 |  |
| SF8 | `2_20260831_071541.642` | 2026-08-31 07:15:41.642 | 2026-08-31 08:30:55 | 1:15:14 | 11.556 | FM62 | YES | glitchy+broadband | wide-impulse,broadband,broadband,broadband,broadband | 15120.33 | 0.399 | 3685.0 | 14.32 | 32 52 53 61 | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF8 | `3_20260831_083101.996` | 2026-08-31 08:31:01.996 | 2026-08-31 08:31:07 | 0:00:05 | 0.013 | FM62 | YES | glitchy | normal | 1233.48 | 1.0 | 1379.0 | 8.45 | 32 |  |
| SF8 | `4_20260831_083120.285` | 2026-08-31 08:31:20.285 | 2026-08-31 11:26:32 | 2:55:12 | 26.911 | FM62 | YES | glitchy+wide-impulse | normal,normal,normal,wide-impulse,normal | 6051.8 | 0.406 | 2158.0 | 8.57 | 32 | WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF8 | `0_20260831_190133.486` | 2026-08-31 19:01:33.486 | 2026-08-31 19:02:18 | 0:00:45 | 0.116 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 287.7 | 1.0 | 677.0 | 10.4 | 32 |  |
| SF8 | `1_20260831_190229.919` | 2026-08-31 19:02:29.919 | 2026-09-01 00:23:12 | 5:20:42 | 49.261 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 678.9 | 1.0 | 671.0 | 10.94 | 32 |  |
| SF8 | `2_20260901_002327.839` | 2026-09-01 00:23:27.839 | 2026-09-01 03:32:06 | 3:08:39 | 28.976 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1247.83 | 1.0 | 1135.0 | 10.89 | 32 |  |
| SF8 | `3_20260901_054222.420` | 2026-09-01 05:42:22.420 | 2026-09-01 05:44:27 | 0:02:05 | 0.32 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 666.57 | 1.0 | 765.0 | 10.8 | 32 |  |
| SF9 | `0_20260831_070319.133` | 2026-08-31 07:03:19.133 | 2026-08-31 07:13:46 | 0:10:28 | 1.606 | FM62 | YES | glitchy+broadband | wide-impulse,broadband,wide-impulse,wide-impulse,wide-impulse | 14983.0 | 0.22 | 2757.0 | 12.85 | 2 4 32 54 56 58 62 | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF9 | `1_20260831_071357.350` | 2026-08-31 07:13:57.350 | 2026-08-31 11:29:22 | 4:15:25 | 39.232 | FM62 | YES | glitchy+wide-impulse | normal,wide-impulse,normal,wide-impulse,wide-impulse | 10061.67 | 0.237 | 1310.0 | 13.48 | 2 4 32 36 54 56 58 62 | WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF9 | `0_20260831_190404.508` | 2026-08-31 19:04:04.508 | 2026-08-31 19:05:10 | 0:01:06 | 0.169 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 314.97 | 0.958 | 1364.0 | 8.26 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260831_190522.711` | 2026-08-31 19:05:22.711 | 2026-08-31 19:05:58 | 0:00:36 | 0.092 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 318.8 | 0.964 | 1300.0 | 8.42 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260831_190743.879` | 2026-08-31 19:07:43.879 | 2026-08-31 19:08:23 | 0:00:40 | 0.101 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 289.1 | 0.959 | 1128.0 | 10.41 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `3_20260831_190834.640` | 2026-08-31 19:08:34.640 | 2026-09-01 00:24:57 | 5:16:23 | 48.597 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 326.1 | 0.963 | 916.0 | 11.77 | 2 4 32 36 54 56 58 62 |  |
| SF9 | `4_20260901_002514.385` | 2026-09-01 00:25:14.385 | 2026-09-01 03:34:28 | 3:09:14 | 29.066 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 365.87 | 0.971 | 897.0 | 12.68 | 2 4 32 36 54 56 58 62 |  |
| SF9 | `5_20260901_054317.203` | 2026-09-01 05:43:17.203 | 2026-09-01 05:44:33 | 0:01:16 | 0.195 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 457.73 | 0.936 | 989.0 | 8.22 | 2 4 32 36 52 54 56 58 60 62 |  |

## How to use

1. Never analyse a `deglitch? = YES` session from its raw `amplifier.dat`; stage it first: `python ephys/stage_session.py --cohort 2026c --animal <SFxx> --session <folder>` (de-glitches by the firmware gate, writes a clean working copy off-repo).
2. Sort from the staged copy: `python ephys/run_sort_session.py --cohort 2026c --animal <SFxx> --session <folder>`.
3. When FM65 sessions arrive, re-run this index; their `measured_verdict` is the evidence that they are clean.
