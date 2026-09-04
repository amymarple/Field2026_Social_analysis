# WILD neurologger session index — cohort `2026c`

Generated 2026-09-04T07:49:06+00:00 by `ephys/build_session_index.py` (git 94ef5a6+dirty) from `E:\3rd_rat_spikes`. Machine-readable twin: `ephys_spikes_session_index_2026c.csv`. Regenerate; do not hand-edit.

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

## Foreign logger folders (ignored)

Session folders under a MAC folder that is NOT the animal's registered logger (a spare logger's card downloaded into the wrong animal folder). They are excluded from every table until moved out of the raw tree (e.g. to `<root>/_other_loggers/<MAC>/`).

- `SF11/2AD87D50B0FA/0_20260902_130113.385`

## Per-animal summary

| animal | logger MAC | sessions | hours offloaded | firmware seen | recovery.bin (GB) |
|---|---|---|---|---|---|
| SF10 | CACB6D600151 | 27 | 64.72 | FM62, FM64, FM65 | 512.7 |
| SF11 | 1DFE7F77721C | 29 | 60.43 | FM62, FM64, FM65 | 512.1 |
| SF12 | FBED2F2321B1 | 26 | 66.25 | FM62, FM64, FM65 | 512.1 |
| SF7 | D0DBEFEF3111 | 22 | 53.33 | FM64, FM65 | 512.1 |
| SF8 | 128C2F27E131 | 31 | 63.52 | FM62, FM64, FM65 | 512.1 |
| SF9 | 68BDFFFF62DB | 28 | 65.46 | FM62, FM64, FM65 | 512.1 |
| analysis | — | 0 | 0.00 | — | — |

**163 sessions indexed: 69 require de-glitching (firmware < FM65), 94 flagged clean by firmware.**

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
| SF10 | `0_20260901_080100.926` | 2026-09-01 08:01:00.926 | 2026-09-01 08:01:36 | 0:00:35 | 0.091 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 247.4 | 0.993 | 622.0 | 8.71 | 32 34 60 |  |
| SF10 | `1_20260901_080143.036` | 2026-09-01 08:01:43.036 | 2026-09-01 12:58:41 | 4:56:59 | 45.616 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 2239.9 | 0.999 | 1386.0 | 8.72 | 2 32 34 56 |  |
| SF10 | `2_20260901_125856.163` | 2026-09-01 12:58:56.163 | 2026-09-01 17:16:05 | 4:17:09 | 39.498 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1239.67 | 0.999 | 1013.0 | 9.01 | 2 32 34 56 |  |
| SF10 | `3_20260901_171620.845` | 2026-09-01 17:16:20.845 | 2026-09-01 18:21:54 | 1:05:33 | 10.069 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1402.8 | 0.999 | 1126.0 | 8.81 | 2 32 34 56 |  |
| SF10 | `4_20260901_193512.911` | 2026-09-01 19:35:12.911 | 2026-09-01 19:35:47 | 0:00:34 | 0.088 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.77 | 1.0 | 777.0 | 11.98 | 32 34 |  |
| SF10 | `5_20260901_193554.435` | 2026-09-01 19:35:54.435 | 2026-09-01 23:39:11 | 4:03:17 | 37.368 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.33 | 1.0 | 934.0 | 10.86 | 32 34 56 |  |
| SF10 | `6_20260901_233920.182` | 2026-09-01 23:39:20.182 | 2026-09-02 07:26:28 | 7:47:08 | 71.751 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.77 | 0.981 | 1292.0 | 10.61 | 2 32 34 |  |
| SF10 | `7_20260902_080750.935` | 2026-09-02 08:07:50.935 | 2026-09-02 08:07:54 | 0:00:04 | 0.01 | FM65 | no | clean | normal | 0.0 | 1.0 | 653.0 | 10.23 | 2 32 34 60 |  |
| SF10 | `8_20260902_083204.119` | 2026-09-02 08:32:04.119 | 2026-09-02 08:32:38 | 0:00:34 | 0.087 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.07 | 1.0 | 1311.0 | 8.09 | 2 32 34 63 |  |
| SF10 | `9_20260902_083247.835` | 2026-09-02 08:32:47.835 | 2026-09-02 17:00:52 | 8:28:05 | 78.041 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.77 | 1.0 | 1226.0 | 11.74 | 32 34 56 |  |
| SF10 | `10_20260902_170101.421` | 2026-09-02 17:01:01.421 | 2026-09-02 18:15:08 | 1:14:07 | 11.383 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.47 | 1.0 | 1075.0 | 8.96 | 2 32 34 56 |  |
| SF10 | `11_20260902_185302.329` | 2026-09-02 18:53:02.329 | 2026-09-02 18:53:06 | 0:00:04 | 0.011 | FM65 | no | clean | normal | 0.7 | 0.333 | 678.0 | 9.47 | 2 32 34 60 |  |
| SF10 | `12_20260902_190631.592` | 2026-09-02 19:06:31.592 | 2026-09-02 19:07:02 | 0:00:31 | 0.079 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.43 | 1.0 | 847.0 | 9.21 | 2 32 34 |  |
| SF10 | `13_20260902_190711.525` | 2026-09-02 19:07:11.525 | 2026-09-03 00:25:19 | 5:18:08 | 48.864 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.1 | 1.0 | 1559.0 | 10.89 | 2 32 34 56 |  |
| SF10 | `14_20260903_002530.902` | 2026-09-03 00:25:30.902 | 2026-09-03 05:56:06 | 5:30:35 | 50.778 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 7.37 | 0.317 | 1202.0 | 11.18 | 2 32 34 |  |
| SF10 | `15_20260903_055614.833` | 2026-09-03 05:56:14.833 | 2026-09-03 06:47:59 | 0:51:45 | 7.948 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.33 | 0.978 | 1578.0 | 8.16 | 2 32 34 56 63 |  |
| SF10 | `0_20260903_072345.895` | 2026-09-03 07:23:45.895 | 2026-09-03 07:23:52 | 0:00:06 | 0.017 | FM65 | no | glitchy+broadband | broadband | 28549.73 | 0.102 | 9664.0 | 13.68 |  | MEASURED GLITCHY although firmware >= clean_firmware_min; BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF10 | `1_20260903_075838.181` | 2026-09-03 07:58:38.181 | 2026-09-03 07:59:10 | 0:00:33 | 0.083 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.1 | 1.0 | 1253.0 | 8.26 | 2 32 34 |  |
| SF10 | `2_20260903_075920.109` | 2026-09-03 07:59:20.109 | 2026-09-03 16:53:08 | 8:53:49 | 81.994 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.47 | 1.0 | 1218.0 | 8.55 | 2 32 34 56 63 |  |
| SF11 | `0_20260831_072408.414` | 2026-08-31 07:24:08.414 | 2026-08-31 07:57:36 | 0:33:28 | 5.142 | FM62 | YES | glitchy+broadband | broadband,normal,wide-impulse,wide-impulse,normal | 54897.97 | 0.245 | 5302.0 | 8.67 | 38 39 43 52 54 56 58 59 61 | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF11 | `0_20260831_191252.932` | 2026-08-31 19:12:52.932 | 2026-08-31 19:13:31 | 0:00:39 | 0.099 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 204.07 | 1.0 | 1394.0 | 8.18 |  |  |
| SF11 | `1_20260831_191341.611` | 2026-08-31 19:13:41.611 | 2026-09-01 00:28:51 | 5:15:10 | 48.41 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 319.2 | 1.0 | 1472.0 | 11.14 |  |  |
| SF11 | `2_20260901_002906.850` | 2026-09-01 00:29:06.850 | 2026-09-01 03:21:53 | 2:52:47 | 26.539 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 507.03 | 1.0 | 1657.0 | 12.04 |  |  |
| SF11 | `3_20260901_054537.933` | 2026-09-01 05:45:37.933 | 2026-09-01 05:46:36 | 0:00:58 | 0.149 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 141.03 | 1.0 | 585.0 | 9.07 | 32 56 60 |  |
| SF11 | `4_20260901_054836.484` | 2026-09-01 05:48:36.484 | 2026-09-01 05:48:47 | 0:00:11 | 0.027 | FM64 | YES | glitchy | normal | 97.24 | 1.0 | 600.0 | 11.01 | 32 56 60 |  |
| SF11 | `5_20260901_054906.988` | 2026-09-01 05:49:06.988 | 2026-09-01 05:49:17 | 0:00:11 | 0.028 | FM64 | YES | glitchy | normal | 138.44 | 1.0 | 617.0 | 11.2 | 32 56 60 62 |  |
| SF11 | `0_20260901_075752.499` | 2026-09-01 07:57:52.499 | 2026-09-01 07:58:27 | 0:00:35 | 0.091 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 178.67 | 1.0 | 641.0 | 9.76 | 32 56 60 |  |
| SF11 | `1_20260901_075834.745` | 2026-09-01 07:58:34.745 | 2026-09-01 07:59:09 | 0:00:35 | 0.089 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 384.03 | 1.0 | 746.0 | 9.52 | 32 56 60 |  |
| SF11 | `2_20260901_075919.035` | 2026-09-01 07:59:19.035 | 2026-09-01 13:03:38 | 5:04:20 | 46.745 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 750.73 | 1.0 | 1154.0 | 10.13 |  |  |
| SF11 | `3_20260901_130404.084` | 2026-09-01 13:04:04.084 | 2026-09-01 17:17:38 | 4:13:34 | 38.949 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 982.83 | 1.0 | 1327.0 | 8.86 |  |  |
| SF11 | `4_20260901_171752.763` | 2026-09-01 17:17:52.763 | 2026-09-01 18:22:41 | 1:04:48 | 9.954 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1080.6 | 1.0 | 1371.0 | 8.67 |  |  |
| SF11 | `6_20260901_193706.332` | 2026-09-01 19:37:06.332 | 2026-09-01 19:37:38 | 0:00:32 | 0.082 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 796.0 | 10.62 | 32 56 60 62 |  |
| SF11 | `7_20260901_193749.076` | 2026-09-01 19:37:49.076 | 2026-09-01 23:24:39 | 3:46:51 | 34.843 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.17 | 1.0 | 802.0 | 11.28 |  |  |
| SF11 | `8_20260901_232454.815` | 2026-09-01 23:24:54.815 | 2026-09-02 06:34:47 | 7:09:53 | 66.03 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.5 | 1.0 | 1796.0 | 10.6 |  |  |
| SF11 | `9_20260902_063458.913` | 2026-09-02 06:34:58.913 | 2026-09-02 07:27:36 | 0:52:38 | 8.084 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1921.0 | 8.39 |  |  |
| SF11 | `10_20260902_075255.597` | 2026-09-02 07:52:55.597 | 2026-09-02 07:53:00 | 0:00:04 | 0.011 | FM65 | no | glitchy | normal | 35.71 | 0.488 | 642.0 | 10.98 | 32 56 60 62 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF11 | `11_20260902_083438.021` | 2026-09-02 08:34:38.021 | 2026-09-02 08:35:18 | 0:00:41 | 0.105 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.57 | 1.0 | 1560.0 | 8.13 | 32 56 60 62 |  |
| SF11 | `12_20260902_083534.755` | 2026-09-02 08:35:34.755 | 2026-09-02 17:04:30 | 8:28:56 | 78.171 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.33 | 1.0 | 1376.0 | 9.14 |  |  |
| SF11 | `13_20260902_170443.451` | 2026-09-02 17:04:43.451 | 2026-09-02 18:14:18 | 1:09:35 | 10.689 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.17 | 0.0 | 1390.0 | 9.84 |  |  |
| SF11 | `14_20260902_184246.377` | 2026-09-02 18:42:46.377 | 2026-09-02 18:42:49 | 0:00:03 | 0.008 | FM65 | no | clean | normal | 0.0 | 1.0 | 577.0 | 15.63 | 32 56 58 60 62 |  |
| SF11 | `15_20260902_184556.057` | 2026-09-02 18:45:56.057 | 2026-09-02 18:45:59 | 0:00:03 | 0.008 | FM65 | no | clean | normal | 0.0 | 1.0 | 810.0 | 9.09 | 32 56 58 60 62 |  |
| SF11 | `16_20260902_190814.621` | 2026-09-02 19:08:14.621 | 2026-09-02 19:08:45 | 0:00:31 | 0.079 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.3 | 1.0 | 1120.0 | 9.01 | 32 56 60 62 |  |
| SF11 | `17_20260902_190852.526` | 2026-09-02 19:08:52.526 | 2026-09-03 05:53:38 | 10:44:46 | 99.036 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 787.0 | 10.4 |  |  |
| SF11 | `18_20260903_055348.084` | 2026-09-03 05:53:48.084 | 2026-09-03 06:53:38 | 0:59:51 | 9.193 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.3 | 1.0 | 1785.0 | 8.1 |  |  |
| SF11 | `1_20260903_073453.241` | 2026-09-03 07:34:53.241 | 2026-09-03 07:34:58 | 0:00:06 | 0.014 | FM65 | no | clean | normal | 0.18 | 1.0 | 441.0 | 9.66 | 32 56 60 62 |  |
| SF11 | `2_20260903_080118.639` | 2026-09-03 08:01:18.639 | 2026-09-03 08:01:51 | 0:00:33 | 0.084 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1543.0 | 7.71 | 32 56 60 |  |
| SF11 | `3_20260903_080159.850` | 2026-09-03 08:01:59.850 | 2026-09-03 15:54:52 | 7:52:53 | 72.634 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.17 | 1.0 | 1290.0 | 8.06 |  |  |
| SF11 | `4_20260903_155503.475` | 2026-09-03 15:55:03.475 | 2026-09-03 16:05:42 | 0:10:39 | 1.636 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.3 | 1.0 | 1236.0 | 8.37 |  |  |
| SF12 | `0_20260831_070947.667` | 2026-08-31 07:09:47.667 | 2026-08-31 07:10:24 | 0:00:37 | 0.095 | FM62 | YES | glitchy | normal,normal,normal,normal,normal | 536.37 | 1.0 | 921.0 | 13.04 | 58 60 |  |
| SF12 | `1_20260831_071033.005` | 2026-08-31 07:10:33.005 | 2026-08-31 07:18:29 | 0:07:56 | 1.219 | FM62 | YES | glitchy+broadband | wide-impulse,broadband,normal,broadband,normal | 24440.47 | 0.389 | 4763.0 | 7.98 |  | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF12 | `2_20260831_071845.540` | 2026-08-31 07:18:45.540 | 2026-08-31 11:27:26 | 4:08:41 | 38.199 | FM62 | YES | glitchy+broadband | broadband,normal,normal,normal,broadband | 15905.97 | 0.231 | 3460.0 | 7.85 |  | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF12 | `1_20260831_191521.024` | 2026-08-31 19:15:21.024 | 2026-08-31 19:15:56 | 0:00:36 | 0.092 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 177.5 | 0.999 | 795.0 | 10.63 |  |  |
| SF12 | `2_20260831_191613.417` | 2026-08-31 19:16:13.417 | 2026-09-01 00:30:37 | 5:14:24 | 48.292 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 572.47 | 1.0 | 1249.0 | 8.48 |  |  |
| SF12 | `3_20260901_003050.862` | 2026-09-01 00:30:50.862 | 2026-09-01 04:57:36 | 4:26:45 | 40.973 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 502.8 | 0.995 | 1148.0 | 11.29 |  |  |
| SF12 | `4_20260901_054714.722` | 2026-09-01 05:47:14.722 | 2026-09-01 05:49:04 | 0:01:50 | 0.282 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 261.9 | 1.0 | 1021.0 | 8.03 |  |  |
| SF12 | `0_20260901_080334.683` | 2026-09-01 08:03:34.683 | 2026-09-01 13:12:09 | 5:08:35 | 47.397 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 908.37 | 1.0 | 1121.0 | 10.88 |  |  |
| SF12 | `1_20260901_131223.398` | 2026-09-01 13:12:23.398 | 2026-09-01 17:19:07 | 4:06:44 | 37.899 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1405.83 | 1.0 | 1185.0 | 7.69 |  |  |
| SF12 | `2_20260901_171924.960` | 2026-09-01 17:19:24.960 | 2026-09-01 18:23:37 | 1:04:13 | 9.863 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1186.37 | 1.0 | 1079.0 | 7.96 |  |  |
| SF12 | `3_20260901_194447.773` | 2026-09-01 19:44:47.773 | 2026-09-01 19:45:26 | 0:00:39 | 0.099 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.97 | 1.0 | 1007.0 | 8.38 | 58 |  |
| SF12 | `4_20260901_194535.925` | 2026-09-01 19:45:35.925 | 2026-09-01 19:46:42 | 0:01:06 | 0.17 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.27 | 1.0 | 1187.0 | 7.67 |  |  |
| SF12 | `5_20260901_195539.194` | 2026-09-01 19:55:39.194 | 2026-09-01 19:56:11 | 0:00:32 | 0.082 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.97 | 1.0 | 1104.0 | 10.54 | 58 |  |
| SF12 | `6_20260901_195621.144` | 2026-09-01 19:56:21.144 | 2026-09-01 23:26:36 | 3:30:15 | 32.294 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.63 | 0.842 | 1329.0 | 9.63 |  |  |
| SF12 | `7_20260901_232651.122` | 2026-09-01 23:26:51.122 | 2026-09-02 06:30:18 | 7:03:27 | 65.042 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 1.0 | 1210.0 | 10.65 |  |  |
| SF12 | `8_20260902_063032.282` | 2026-09-02 06:30:32.282 | 2026-09-02 07:37:24 | 1:06:52 | 10.271 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.4 | 0.25 | 1309.0 | 7.26 |  |  |
| SF12 | `9_20260902_075722.923` | 2026-09-02 07:57:22.923 | 2026-09-02 07:57:35 | 0:00:13 | 0.033 | FM65 | no | clean | normal | 0.47 | 1.0 | 957.0 | 9.72 | 58 |  |
| SF12 | `10_20260902_083702.135` | 2026-09-02 08:37:02.135 | 2026-09-02 08:37:35 | 0:00:33 | 0.084 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.4 | 1.0 | 939.0 | 8.1 | 58 |  |
| SF12 | `11_20260902_083748.804` | 2026-09-02 08:37:48.804 | 2026-09-02 18:20:58 | 9:43:10 | 89.573 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.0 | 0.3 | 1109.0 | 7.84 |  |  |
| SF12 | `12_20260902_185346.222` | 2026-09-02 18:53:46.222 | 2026-09-02 18:53:50 | 0:00:04 | 0.011 | FM65 | no | clean | normal | 0.0 | 1.0 | 722.0 | 9.41 | 58 |  |
| SF12 | `13_20260902_191006.815` | 2026-09-02 19:10:06.815 | 2026-09-02 19:10:54 | 0:00:48 | 0.122 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.67 | 0.643 | 1217.0 | 8.14 |  |  |
| SF12 | `14_20260902_191103.245` | 2026-09-02 19:11:03.245 | 2026-09-03 00:22:17 | 5:11:15 | 47.807 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.37 | -2.0 | 1457.0 | 10.19 |  |  |
| SF12 | `15_20260903_002228.142` | 2026-09-03 00:22:28.142 | 2026-09-03 06:51:40 | 6:29:12 | 59.781 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.7 | 0.81 | 1400.0 | 10.67 |  |  |
| SF12 | `1_20260903_073631.699` | 2026-09-03 07:36:31.699 | 2026-09-03 07:36:35 | 0:00:04 | 0.01 | FM65 | no | clean | normal | 0.0 | 1.0 | 881.0 | 10.48 |  |  |
| SF12 | `2_20260903_080832.082` | 2026-09-03 08:08:32.082 | 2026-09-03 08:09:15 | 0:00:43 | 0.111 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.33 | 1.0 | 878.0 | 8.91 |  |  |
| SF12 | `3_20260903_080924.473` | 2026-09-03 08:09:24.473 | 2026-09-03 16:55:27 | 8:46:03 | 80.802 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 11.73 | 0.867 | 1202.0 | 8.51 |  | MEASURED GLITCHY although firmware >= clean_firmware_min |
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
| SF7 | `0_20260902_183440.393` | 2026-09-02 18:34:40.393 | 2026-09-02 18:34:46 | 0:00:06 | 0.017 | FM65 | no | glitchy | normal | 29.92 | 0.979 | 601.0 | 10.53 |  | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF7 | `1_20260902_183616.989` | 2026-09-02 18:36:16.989 | 2026-09-02 18:36:20 | 0:00:04 | 0.01 | FM65 | no | clean | normal | 0.0 | 1.0 | 643.0 | 10.6 |  |  |
| SF7 | `2_20260902_190005.320` | 2026-09-02 19:00:05.320 | 2026-09-02 19:00:37 | 0:00:33 | 0.084 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.73 | 0.589 | 657.0 | 12.52 |  |  |
| SF7 | `3_20260902_190047.109` | 2026-09-02 19:00:47.109 | 2026-09-03 00:15:47 | 5:15:00 | 48.385 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 807.0 | 11.17 |  |  |
| SF7 | `4_20260903_001558.656` | 2026-09-03 00:15:58.656 | 2026-09-03 04:18:17 | 4:02:19 | 37.221 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 6.57 | 0.508 | 738.0 | 12.3 |  |  |
| SF8 | `0_20260831_070148.859` | 2026-08-31 07:01:48.859 | 2026-08-31 07:12:27 | 0:10:39 | 1.635 | FM62 | YES | glitchy+broadband | broadband,wide-impulse,wide-impulse,wide-impulse,normal | 34988.23 | 0.183 | 5178.0 | 12.9 |  | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF8 | `1_20260831_071239.713` | 2026-08-31 07:12:39.713 | 2026-08-31 07:15:31 | 0:02:52 | 0.441 | FM62 | YES | glitchy | normal,normal,normal,normal,normal | 2012.73 | 1.0 | 1395.0 | 8.49 | 32 |  |
| SF8 | `2_20260831_071541.642` | 2026-08-31 07:15:41.642 | 2026-08-31 08:30:55 | 1:15:14 | 11.556 | FM62 | YES | glitchy+broadband | wide-impulse,broadband,broadband,broadband,broadband | 15120.33 | 0.399 | 3685.0 | 14.32 | 32 52 53 61 | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF8 | `3_20260831_083101.996` | 2026-08-31 08:31:01.996 | 2026-08-31 08:31:07 | 0:00:05 | 0.013 | FM62 | YES | glitchy | normal | 1233.48 | 1.0 | 1379.0 | 8.45 | 32 |  |
| SF8 | `4_20260831_083120.285` | 2026-08-31 08:31:20.285 | 2026-08-31 11:26:32 | 2:55:12 | 26.911 | FM62 | YES | glitchy+wide-impulse | normal,normal,normal,wide-impulse,normal | 6051.8 | 0.406 | 2158.0 | 8.57 | 32 | WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF8 | `0_20260831_190133.486` | 2026-08-31 19:01:33.486 | 2026-08-31 19:02:18 | 0:00:45 | 0.116 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 287.7 | 1.0 | 677.0 | 10.4 | 32 |  |
| SF8 | `1_20260831_190229.919` | 2026-08-31 19:02:29.919 | 2026-09-01 00:23:12 | 5:20:42 | 49.261 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 678.9 | 1.0 | 671.0 | 10.94 | 32 |  |
| SF8 | `2_20260901_002327.839` | 2026-09-01 00:23:27.839 | 2026-09-01 03:32:06 | 3:08:39 | 28.976 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1247.83 | 1.0 | 1135.0 | 10.89 | 32 |  |
| SF8 | `3_20260901_054222.420` | 2026-09-01 05:42:22.420 | 2026-09-01 05:44:27 | 0:02:05 | 0.32 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 666.57 | 1.0 | 765.0 | 10.8 | 32 |  |
| SF8 | `0_20260901_075204.484` | 2026-09-01 07:52:04.484 | 2026-09-01 07:52:56 | 0:00:52 | 0.132 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 296.83 | 1.0 | 673.0 | 12.52 | 32 |  |
| SF8 | `1_20260901_075304.063` | 2026-09-01 07:53:04.063 | 2026-09-01 12:56:10 | 5:03:06 | 46.557 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1855.73 | 1.0 | 1384.0 | 8.34 | 32 |  |
| SF8 | `2_20260901_125621.840` | 2026-09-01 12:56:21.840 | 2026-09-01 13:28:20 | 0:31:59 | 4.912 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1199.5 | 1.0 | 1233.0 | 8.73 | 32 |  |
| SF8 | `3_20260901_151059.837` | 2026-09-01 15:10:59.837 | 2026-09-01 15:14:10 | 0:03:11 | 0.489 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1472.8 | 1.0 | 1206.0 | 8.88 | 32 |  |
| SF8 | `4_20260901_152951.697` | 2026-09-01 15:29:51.697 | 2026-09-01 17:13:24 | 1:43:33 | 15.905 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1400.83 | 1.0 | 1120.0 | 8.3 | 32 |  |
| SF8 | `5_20260901_171339.094` | 2026-09-01 17:13:39.094 | 2026-09-01 18:20:28 | 1:06:49 | 10.263 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1217.33 | 1.0 | 1144.0 | 8.66 | 32 |  |
| SF8 | `6_20260901_193023.481` | 2026-09-01 19:30:23.481 | 2026-09-01 19:31:00 | 0:00:37 | 0.095 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.37 | 1.0 | 750.0 | 11.19 | 32 |  |
| SF8 | `7_20260901_193109.475` | 2026-09-01 19:31:09.475 | 2026-09-01 23:31:53 | 4:00:44 | 36.977 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.4 | 1.0 | 784.0 | 12.28 | 32 |  |
| SF8 | `8_20260901_233239.239` | 2026-09-01 23:32:39.239 | 2026-09-02 06:24:19 | 6:51:41 | 63.234 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.2 | 1.0 | 1185.0 | 12.33 | 32 |  |
| SF8 | `9_20260902_062432.012` | 2026-09-02 06:24:32.012 | 2026-09-02 07:30:11 | 1:05:39 | 10.084 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.1 | 1.0 | 1462.0 | 8.6 | 32 |  |
| SF8 | `11_20260902_080414.269` | 2026-09-02 08:04:14.269 | 2026-09-02 08:04:21 | 0:00:07 | 0.017 | FM65 | no | clean | normal | 0.15 | 1.0 | 661.0 | 11.78 | 32 |  |
| SF8 | `12_20260902_082624.125` | 2026-09-02 08:26:24.125 | 2026-09-02 08:27:40 | 0:01:16 | 0.195 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 749.0 | 10.16 | 32 |  |
| SF8 | `13_20260902_082748.094` | 2026-09-02 08:27:48.094 | 2026-09-02 18:20:23 | 9:52:36 | 91.023 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.5 | 1.0 | 1309.0 | 8.63 | 32 |  |
| SF8 | `14_20260902_183725.225` | 2026-09-02 18:37:25.225 | 2026-09-02 18:37:27 | 0:00:03 | 0.007 | FM65 | no | clean | normal | 0.78 | 1.0 | 1316.0 | 8.16 | 32 |  |
| SF8 | `15_20260902_184139.248` | 2026-09-02 18:41:39.248 | 2026-09-02 18:42:13 | 0:00:35 | 0.089 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.57 | 1.0 | 643.0 | 11.0 | 32 |  |
| SF8 | `16_20260902_190202.601` | 2026-09-02 19:02:02.601 | 2026-09-02 19:02:33 | 0:00:31 | 0.078 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.87 | 1.0 | 765.0 | 10.14 | 32 |  |
| SF8 | `17_20260902_190241.916` | 2026-09-02 19:02:41.916 | 2026-09-03 06:00:20 | 10:57:38 | 101.013 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 0.167 | 779.0 | 11.91 | 32 |  |
| SF8 | `18_20260903_060030.122` | 2026-09-03 06:00:30.122 | 2026-09-03 06:44:40 | 0:44:10 | 6.785 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 0.167 | 1342.0 | 10.58 | 32 |  |
| SF8 | `0_20260903_071202.892` | 2026-09-03 07:12:02.892 | 2026-09-03 07:12:10 | 0:00:08 | 0.021 | FM65 | no | glitchy | normal | 65.48 | 0.994 | 597.0 | 10.73 | 32 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF8 | `1_20260903_075302.441` | 2026-09-03 07:53:02.441 | 2026-09-03 07:53:44 | 0:00:42 | 0.107 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.37 | 1.0 | 598.0 | 10.2 | 32 |  |
| SF8 | `2_20260903_075352.907` | 2026-09-03 07:53:52.907 | 2026-09-03 15:58:04 | 8:04:12 | 74.372 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 14.0 | 1.0 | 1039.0 | 9.96 | 32 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF8 | `3_20260903_160306.510` | 2026-09-03 16:03:06.510 | 2026-09-03 16:27:46 | 0:24:40 | 3.788 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 8.63 | 1.0 | 1195.0 | 8.78 | 32 |  |
| SF9 | `0_20260831_070319.133` | 2026-08-31 07:03:19.133 | 2026-08-31 07:13:46 | 0:10:28 | 1.606 | FM62 | YES | glitchy+broadband | wide-impulse,broadband,wide-impulse,wide-impulse,wide-impulse | 14983.0 | 0.22 | 2757.0 | 12.85 | 2 4 32 54 56 58 62 | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF9 | `1_20260831_071357.350` | 2026-08-31 07:13:57.350 | 2026-08-31 11:29:22 | 4:15:25 | 39.232 | FM62 | YES | glitchy+wide-impulse | normal,wide-impulse,normal,wide-impulse,wide-impulse | 10061.67 | 0.237 | 1310.0 | 13.48 | 2 4 32 36 54 56 58 62 | WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF9 | `0_20260831_190404.508` | 2026-08-31 19:04:04.508 | 2026-08-31 19:05:10 | 0:01:06 | 0.169 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 314.97 | 0.958 | 1364.0 | 8.26 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260831_190522.711` | 2026-08-31 19:05:22.711 | 2026-08-31 19:05:58 | 0:00:36 | 0.092 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 318.8 | 0.964 | 1300.0 | 8.42 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260831_190743.879` | 2026-08-31 19:07:43.879 | 2026-08-31 19:08:23 | 0:00:40 | 0.101 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 289.1 | 0.959 | 1128.0 | 10.41 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `3_20260831_190834.640` | 2026-08-31 19:08:34.640 | 2026-09-01 00:24:57 | 5:16:23 | 48.597 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 326.1 | 0.963 | 916.0 | 11.77 | 2 4 32 36 54 56 58 62 |  |
| SF9 | `4_20260901_002514.385` | 2026-09-01 00:25:14.385 | 2026-09-01 03:34:28 | 3:09:14 | 29.066 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 365.87 | 0.971 | 897.0 | 12.68 | 2 4 32 36 54 56 58 62 |  |
| SF9 | `5_20260901_054317.203` | 2026-09-01 05:43:17.203 | 2026-09-01 05:44:33 | 0:01:16 | 0.195 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 457.73 | 0.936 | 989.0 | 8.22 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `0_20260901_075436.934` | 2026-09-01 07:54:36.934 | 2026-09-01 07:55:20 | 0:00:44 | 0.111 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 438.4 | 0.987 | 815.0 | 13.1 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260901_075532.964` | 2026-09-01 07:55:32.964 | 2026-09-01 12:57:27 | 5:01:54 | 46.372 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 2463.2 | 0.999 | 1326.0 | 10.88 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260901_125743.131` | 2026-09-01 12:57:43.131 | 2026-09-01 17:14:43 | 4:17:00 | 39.475 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1832.47 | 1.0 | 1094.0 | 9.64 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `3_20260901_171502.588` | 2026-09-01 17:15:02.588 | 2026-09-01 18:21:13 | 1:06:11 | 10.167 | FM64 | YES | glitchy | normal,normal,normal,normal,normal | 1944.17 | 1.0 | 1082.0 | 9.85 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `4_20260901_193233.034` | 2026-09-01 19:32:33.034 | 2026-09-01 19:33:10 | 0:00:38 | 0.096 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.17 | 1.0 | 720.0 | 10.47 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `5_20260901_193330.365` | 2026-09-01 19:33:30.365 | 2026-09-01 23:22:33 | 3:49:04 | 35.184 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.67 | 1.0 | 1060.0 | 13.52 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `6_20260901_232245.983` | 2026-09-01 23:22:45.983 | 2026-09-02 06:25:49 | 7:03:04 | 64.982 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.73 | 1.0 | 1306.0 | 12.83 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `7_20260902_062601.722` | 2026-09-02 06:26:01.722 | 2026-09-02 07:29:26 | 1:03:25 | 9.741 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 1469.0 | 9.65 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `8_20260902_081433.629` | 2026-09-02 08:14:33.629 | 2026-09-02 08:14:36 | 0:00:03 | 0.009 | FM65 | no | ambiguous | normal | 1.5 | 1.0 | 644.0 | 10.08 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `9_20260902_082928.325` | 2026-09-02 08:29:28.325 | 2026-09-02 08:30:06 | 0:00:39 | 0.099 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.33 | 1.0 | 979.0 | 9.37 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `10_20260902_083015.335` | 2026-09-02 08:30:15.335 | 2026-09-02 16:58:18 | 8:28:03 | 78.036 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.7 | 1.0 | 1135.0 | 9.85 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `11_20260902_165826.634` | 2026-09-02 16:58:26.634 | 2026-09-02 18:13:58 | 1:15:32 | 11.602 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.1 | 1.0 | 1186.0 | 10.02 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `12_20260902_183208.214` | 2026-09-02 18:32:08.214 | 2026-09-02 18:32:13 | 0:00:06 | 0.015 | FM65 | no | clean | normal | 0.17 | 1.0 | 650.0 | 12.7 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `13_20260902_190350.404` | 2026-09-02 19:03:50.404 | 2026-09-02 19:04:21 | 0:00:31 | 0.079 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 834.0 | 11.36 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `14_20260902_190428.646` | 2026-09-02 19:04:28.646 | 2026-09-02 19:05:01 | 0:00:33 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.53 | 1.0 | 867.0 | 11.15 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `15_20260902_190508.575` | 2026-09-02 19:05:08.575 | 2026-09-03 00:18:18 | 5:13:10 | 48.103 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.37 | 1.0 | 1365.0 | 9.63 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `16_20260903_001828.515` | 2026-09-03 00:18:28.515 | 2026-09-03 06:46:39 | 6:28:11 | 59.626 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.1 | 0.5 | 2125.0 | 9.85 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `0_20260903_072302.755` | 2026-09-03 07:23:02.755 | 2026-09-03 07:23:07 | 0:00:05 | 0.012 | FM65 | no | ambiguous | normal | 6.82 | 0.061 | 794.0 | 11.82 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260903_075611.131` | 2026-09-03 07:56:11.131 | 2026-09-03 07:56:44 | 0:00:33 | 0.086 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.33 | 1.0 | 949.0 | 9.67 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260903_075655.297` | 2026-09-03 07:56:55.297 | 2026-09-03 16:39:43 | 8:42:48 | 80.303 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 1366.0 | 9.6 | 2 4 32 36 52 54 56 58 60 62 |  |

## How to use

1. Never analyse a `deglitch? = YES` session from its raw `amplifier.dat`; stage it first: `python ephys/stage_session.py --cohort 2026c --animal <SFxx> --session <folder>` (de-glitches by the firmware gate, writes a clean working copy off-repo).
2. Sort from the staged copy: `python ephys/run_sort_session.py --cohort 2026c --animal <SFxx> --session <folder>`.
3. When FM65 sessions arrive, re-run this index; their `measured_verdict` is the evidence that they are clean.
