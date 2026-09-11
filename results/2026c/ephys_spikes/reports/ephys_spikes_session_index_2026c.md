# WILD neurologger session index — cohort `2026c`

Generated 2026-09-11T02:20:39+00:00 by `ephys/build_session_index.py` (git 4c92621+dirty) from `E:\3rd_rat_spikes`. Machine-readable twin: `ephys_spikes_session_index_2026c.csv`. Regenerate; do not hand-edit.

## Firmware provenance (the rule that decides what may be analysed)

- `firmware` is read from each session's `CE_params.bin` (uint16 at byte 328). `deglitch_required = firmware < 65` (`clean_firmware_min` in `cohorts/2026c.yaml`).
- **FM62** — stop-only commit (session exists only after a clean Record Stop) + glitch defects A/B
- **FM64** — glitch defects A/B (~100-1400 ticks/s summed over 64 ch); stop-only commit
- **FM65** — maker fix, both parts now VERIFIED. Glitch defects absent: measured clean on all six loggers over 94 field sessions (240.8 h) - see the offload QC report. Power-cut-safe commit: survives a HARD power cut (battery pulled mid-recording), tested by the operator 2026-09-04; and the logger's own low-battery auto-stop closes the files byte-exact - SF09 2_20260903_075655.297 (8.713 h) and SF07 4_20260903_001558.656 (4.039 h) both have amplifier.dat a whole number of 128-byte samples, time.dat = 4 x n_samples and analogin.dat = 2 x n_samples. Consequence for the field protocol: a mid-night Stop->Start restart is no longer needed as insurance, so the midnight BLE touch can be a mid-session anchor instead of a session start - worth ~50 ms on the unanchored tail (see change_log 2026-09-04)
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
| `field_flag` | text from `cohorts/<key>.yaml` `ephys.field_flags` (empty = none) | the field record marks the session as not a real recording (zombie restart of a dying cell) or as a TEST recording; kept in this inventory, excluded from coverage, the firmware verdict and any analysis until decided. `[no field-PC time]` = recorded from another PC's console: its BLE anchors are not field-PC time and `pc_time_chain` does not fit it |
| `valid_until` | 'YYYY-MM-DD HH:MM:SS' from `cohorts/<key>.yaml` `ephys.valid_until` (empty = whole session valid), logger wallclock | the neural signal ended before the Stop (implant detached mid-session): the session is a normal session up to this time (fitted, counted, sortable) and open-circuit noise after it; the probe windows and the coverage tables stop here |

## Foreign logger folders (ignored)

Session folders under a MAC folder that is NOT the animal's registered logger (a spare logger's card downloaded into the wrong animal folder). They are excluded from every table until moved out of the raw tree (e.g. to `<root>/_other_loggers/<MAC>/`).

- `SF7/2AD87D50B0FA/0_20260908_180103.769`

## Field-flagged sessions (indexed, excluded from coverage and analysis)

- SF10 `10_20260905_070012.038` (0:29:47): zombie restarts of a dying 900 mAh cell after its 06:58 auto-stop (cell retired); high-IR sag, exclude
- SF10 `11_20260905_080522.427` (0:34:55): zombie restarts of a dying 900 mAh cell after its 06:58 auto-stop (cell retired); high-IR sag, exclude
- SF11 `0_20260906_124136.884` (0:33:46): probe-position TEST on a 64 GB test card from another PC's console during the 09-06 12:32-13:33 advance; anchors are NOT field-PC time; inclusion undecided (operator 09-06) [no field-PC time]
- SF7 `0_20260906_123827.548` (0:00:39): probe-position TEST on a 64 GB test card from another PC's console during the 09-06 12:31-13:29 advance; anchors are NOT field-PC time; inclusion undecided (operator 09-06) [no field-PC time]
- SF7 `1_20260906_123931.995` (0:21:22): probe-position TEST on a 64 GB test card from another PC's console during the 09-06 12:31-13:29 advance; anchors are NOT field-PC time; inclusion undecided (operator 09-06) [no field-PC time]
- SF8 `9_20260910_184248.287` (): ADC lane ON: 312.5 Hz ~5.5 mV pulse train on all 64 channels (measured 09-10); ephys unusable; 10_ is an empty record (fs 0). QUARANTINED 2026-09-10: moved to E:/3rd_rat_spikes/_quarantine_adc_lane_on/SF8/<MAC>/ (invisible to the index); listed here for the record

## Sessions with a validity boundary (neural signal ended before the Stop)

- SF11 `13_20260906_195234.827` (12:20:07): valid until 2026-09-07 06:10:00; recording continues 2.04 h past valid_until 2026-09-07 06:10:00 (cohorts/<key>.yaml ephys.valid_until): probe windows and coverage limited to the valid part

## Per-animal summary

| animal | logger MAC | sessions | hours offloaded | firmware seen | recovery.bin (GB) |
|---|---|---|---|---|---|
| SF10 | CACB6D600151 | 72 | 196.57 | FM62, FM64, FM65 | 512.7 |
| SF11 | 1DFE7F77721C | 65 | 140.95 | FM62, FM64, FM65 | 512.1 |
| SF12 | FBED2F2321B1 | 64 | 199.34 | FM62, FM64, FM65 | 512.1 |
| SF7 | D0DBEFEF3111 | 73 | 196.56 | FM64, FM65 | 512.1 |
| SF8 | 128C2F27E131 | 75 | 217.47 | FM62, FM64, FM65 | 512.1 |
| SF9 | 68BDFFFF62DB | 69 | 199.80 | FM62, FM64, FM65 | 512.1 |

**418 sessions indexed: 69 require de-glitching (firmware < FM65), 348 flagged clean by firmware.**

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
| SF10 | `0_20260903_173135.541` | 2026-09-03 17:31:35.541 | 2026-09-03 17:31:40 | 0:00:05 | 0.012 | FM65 | no | glitchy | normal | 28.32 | 0.964 | 699.0 | 9.91 | 2 32 34 60 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF10 | `1_20260903_180043.639` | 2026-09-03 18:00:43.639 | 2026-09-03 18:02:14 | 0:01:31 | 0.232 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 0.0 | 973.0 | 8.75 | 2 32 34 60 |  |
| SF10 | `2_20260903_180222.843` | 2026-09-03 18:02:22.843 | 2026-09-04 07:23:58 | 13:21:36 | 123.125 | FM65 | no | ambiguous+broadband | normal,normal,normal,broadband,normal | 1.63 | 0.959 | 2789.0 | 9.4 | 2 32 34 56 60 | BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use |
| SF10 | `3_20260904_081614.901` | 2026-09-04 08:16:14.901 | 2026-09-04 08:16:46 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.3 | 0.889 | 886.0 | 8.19 | 2 32 34 |  |
| SF10 | `4_20260904_081653.075` | 2026-09-04 08:16:53.075 | 2026-09-04 08:17:23 | 0:00:31 | 0.079 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.97 | 1.0 | 1267.0 | 8.2 | 2 32 34 |  |
| SF10 | `5_20260904_081730.895` | 2026-09-04 08:17:30.895 | 2026-09-04 19:34:41 | 11:17:11 | 104.016 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.5 | 1.0 | 1349.0 | 8.26 | 2 32 34 56 63 |  |
| SF10 | `6_20260904_200004.108` | 2026-09-04 20:00:04.108 | 2026-09-04 20:00:08 | 0:00:04 | 0.01 | FM65 | no | clean | normal | 0.25 | 1.0 | 818.0 | 10.94 | 2 32 34 56 60 |  |
| SF10 | `7_20260904_202457.187` | 2026-09-04 20:24:57.187 | 2026-09-04 20:25:30 | 0:00:33 | 0.085 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.97 | 0.339 | 896.0 | 11.28 | 2 32 34 60 |  |
| SF10 | `8_20260904_202538.175` | 2026-09-04 20:25:38.175 | 2026-09-04 20:26:06 | 0:00:28 | 0.072 | FM65 | no | ambiguous | normal | 5.77 | 0.809 | 890.0 | 11.08 |  |  |
| SF10 | `9_20260904_202620.386` | 2026-09-04 20:26:20.386 | 2026-09-05 06:56:34 | 10:30:14 | 96.805 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.3 | 0.867 | 824.0 | 11.28 | 32 34 60 |  |
| SF10 | `10_20260905_070012.038` | 2026-09-05 07:00:12.038 | 2026-09-05 07:29:58 | 0:29:47 | 4.574 | FM65 | no | glitchy+wide-impulse | normal,normal,normal,wide-impulse,wide-impulse | 2339.23 | 0.406 | 1466.0 | 9.58 |  | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF10 | `11_20260905_080522.427` | 2026-09-05 08:05:22.427 | 2026-09-05 08:40:17 | 0:34:55 | 5.363 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.9 | 0.68 | 1512.0 | 8.5 |  |  |
| SF10 | `3_20260905_091037.124` | 2026-09-05 09:10:37.124 | 2026-09-05 09:10:40 | 0:00:03 | 0.009 | FM65 | no | ambiguous | normal | 2.39 | 1.0 | 564.0 | 9.57 | 2 32 34 |  |
| SF10 | `4_20260905_091435.882` | 2026-09-05 09:14:35.882 | 2026-09-05 09:14:39 | 0:00:04 | 0.009 | FM65 | no | glitchy+wide-impulse | wide-impulse | 153.51 | 0.304 | 845.0 | 11.26 |  | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF10 | `5_20260905_091632.194` | 2026-09-05 09:16:32.194 | 2026-09-05 09:16:36 | 0:00:05 | 0.012 | FM65 | no | ambiguous | normal | 2.21 | 0.8 | 1022.0 | 10.49 |  |  |
| SF10 | `6_20260905_093836.419` | 2026-09-05 09:38:36.419 | 2026-09-05 09:39:19 | 0:00:43 | 0.11 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.57 | 1.0 | 1061.0 | 8.27 | 2 32 34 62 |  |
| SF10 | `7_20260905_093927.479` | 2026-09-05 09:39:27.479 | 2026-09-05 18:06:44 | 8:27:17 | 77.92 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 12.23 | 1.0 | 1192.0 | 8.81 | 2 32 34 56 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF10 | `0_20260905_182915.337` | 2026-09-05 18:29:15.337 | 2026-09-05 18:29:21 | 0:00:06 | 0.017 | FM65 | no | glitchy | normal | 13.02 | 1.0 | 582.0 | 10.41 | 2 32 34 60 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF10 | `1_20260905_185628.363` | 2026-09-05 18:56:28.363 | 2026-09-05 18:57:02 | 0:00:34 | 0.087 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 1230.0 | 8.8 | 2 32 34 56 60 |  |
| SF10 | `2_20260905_185709.365` | 2026-09-05 18:57:09.365 | 2026-09-06 04:02:07 | 9:04:58 | 83.706 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 4.87 | 1.0 | 1351.0 | 10.62 | 2 32 34 56 60 62 |  |
| SF10 | `3_20260906_055804.599` | 2026-09-06 05:58:04.599 | 2026-09-06 07:00:21 | 1:02:17 | 9.566 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.47 | 0.885 | 1494.0 | 8.61 | 2 32 34 60 62 |  |
| SF10 | `4_20260906_073108.111` | 2026-09-06 07:31:08.111 | 2026-09-06 07:31:10 | 0:00:02 | 0.005 | FM65 | no | clean | normal | 0.51 | 1.0 | 660.0 | 9.5 | 2 32 58 60 |  |
| SF10 | `5_20260906_080407.877` | 2026-09-06 08:04:07.877 | 2026-09-06 08:04:40 | 0:00:32 | 0.082 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.03 | 1.0 | 1232.0 | 8.03 | 2 32 34 60 62 63 |  |
| SF10 | `6_20260906_080449.175` | 2026-09-06 08:04:49.175 | 2026-09-06 19:06:51 | 11:02:02 | 101.689 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.6 | 0.278 | 1500.0 | 8.82 | 2 32 34 56 60 |  |
| SF10 | `7_20260906_192951.209` | 2026-09-06 19:29:51.209 | 2026-09-06 19:29:56 | 0:00:05 | 0.013 | FM65 | no | clean | normal | 0.2 | 1.0 | 770.0 | 10.87 | 2 32 34 56 60 |  |
| SF10 | `8_20260906_194840.721` | 2026-09-06 19:48:40.721 | 2026-09-06 19:49:14 | 0:00:33 | 0.085 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.57 | 0.75 | 927.0 | 9.55 | 2 32 34 60 |  |
| SF10 | `9_20260906_194921.983` | 2026-09-06 19:49:21.983 | 2026-09-07 08:12:27 | 12:23:06 | 114.14 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.23 | 0.905 | 1099.0 | 10.42 | 2 32 34 56 60 |  |
| SF10 | `0_20260907_083846.238` | 2026-09-07 08:38:46.238 | 2026-09-07 08:38:51 | 0:00:05 | 0.012 | FM65 | no | ambiguous | normal | 1.03 | 1.0 | 618.0 | 10.34 |  |  |
| SF10 | `2_20260907_083913.009` | 2026-09-07 08:39:13.009 | 2026-09-07 08:39:16 | 0:00:04 | 0.009 | FM65 | no | ambiguous | normal | 2.51 | 1.0 | 770.0 | 10.36 |  |  |
| SF10 | `3_20260907_090035.749` | 2026-09-07 09:00:35.749 | 2026-09-07 09:01:26 | 0:00:51 | 0.131 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.03 | 0.717 | 863.0 | 9.79 |  |  |
| SF10 | `4_20260907_090135.869` | 2026-09-07 09:01:35.869 | 2026-09-07 16:59:56 | 7:58:21 | 73.474 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 12.87 | 0.632 | 1425.0 | 8.94 | 2 32 34 56 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF10 | `2_20260907_173420.856` | 2026-09-07 17:34:20.856 | 2026-09-07 17:34:46 | 0:00:26 | 0.066 | FM65 | no | ambiguous | normal | 5.39 | 0.993 | 702.0 | 9.23 | 2 32 34 56 58 60 |  |
| SF10 | `3_20260907_175619.012` | 2026-09-07 17:56:19.012 | 2026-09-07 17:56:52 | 0:00:34 | 0.087 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.27 | 1.0 | 1170.0 | 8.53 | 2 32 34 56 58 60 |  |
| SF10 | `4_20260907_175705.905` | 2026-09-07 17:57:05.905 | 2026-09-07 17:57:37 | 0:00:31 | 0.081 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 1.0 | 1269.0 | 8.46 | 2 32 34 56 58 60 |  |
| SF10 | `5_20260907_175744.885` | 2026-09-07 17:57:44.885 | 2026-09-08 06:26:57 | 12:29:12 | 115.078 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 8.2 | 0.244 | 1384.0 | 10.31 | 2 32 34 56 60 |  |
| SF10 | `6_20260908_070444.819` | 2026-09-08 07:04:44.819 | 2026-09-08 07:04:48 | 0:00:03 | 0.008 | FM65 | no | clean | normal | 0.63 | 1.0 | 665.0 | 10.35 | 2 32 60 |  |
| SF10 | `7_20260908_072257.739` | 2026-09-08 07:22:57.739 | 2026-09-08 07:23:42 | 0:00:44 | 0.114 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 1361.0 | 8.18 | 2 32 34 58 60 |  |
| SF10 | `8_20260908_072352.245` | 2026-09-08 07:23:52.245 | 2026-09-08 18:58:43 | 11:34:52 | 106.731 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.33 | 0.903 | 1166.0 | 8.46 | 2 32 34 56 |  |
| SF10 | `9_20260908_192609.401` | 2026-09-08 19:26:09.401 | 2026-09-08 19:26:12 | 0:00:03 | 0.008 | FM65 | no | clean | normal | 0.0 | 1.0 | 733.0 | 9.72 | 2 32 34 56 60 |  |
| SF10 | `10_20260908_192858.415` | 2026-09-08 19:28:58.415 | 2026-09-08 19:29:07 | 0:00:09 | 0.023 | FM65 | no | ambiguous | normal | 4.78 | 1.0 | 1005.0 | 10.49 |  |  |
| SF10 | `11_20260908_194504.649` | 2026-09-08 19:45:04.649 | 2026-09-08 19:45:40 | 0:00:36 | 0.092 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 0.5 | 1037.0 | 8.61 | 2 32 34 56 60 |  |
| SF10 | `12_20260908_194550.363` | 2026-09-08 19:45:50.363 | 2026-09-09 08:20:32 | 12:34:42 | 115.923 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.97 | 0.538 | 1478.0 | 10.23 | 2 32 34 56 60 |  |
| SF10 | `0_20260909_084938.378` | 2026-09-09 08:49:38.378 | 2026-09-09 08:49:41 | 0:00:03 | 0.008 | FM65 | no | clean | normal | 0.62 | 0.5 | 609.0 | 10.07 | 2 32 34 56 60 |  |
| SF10 | `1_20260909_091016.538` | 2026-09-09 09:10:16.538 | 2026-09-09 09:10:53 | 0:00:37 | 0.094 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.1 | 1.0 | 1263.0 | 8.43 | 2 32 34 60 63 |  |
| SF10 | `2_20260909_091105.736` | 2026-09-09 09:11:05.736 | 2026-09-09 18:00:31 | 8:49:26 | 81.321 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.63 | 0.959 | 1527.0 | 8.35 | 2 32 34 56 63 |  |
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
| SF11 | `0_20260903_174306.448` | 2026-09-03 17:43:06.448 | 2026-09-03 17:43:12 | 0:00:06 | 0.017 | FM65 | no | glitchy | normal | 134.7 | 0.933 | 871.0 | 8.22 | 4 32 56 60 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF11 | `1_20260903_174550.305` | 2026-09-03 17:45:50.305 | 2026-09-03 17:45:55 | 0:00:05 | 0.013 | FM65 | no | clean | normal | 0.2 | 1.0 | 629.0 | 8.11 | 4 32 56 60 62 |  |
| SF11 | `2_20260903_180447.941` | 2026-09-03 18:04:47.941 | 2026-09-03 18:05:19 | 0:00:32 | 0.082 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 589.0 | 9.36 | 4 32 56 60 62 |  |
| SF11 | `3_20260903_180527.746` | 2026-09-03 18:05:27.746 | 2026-09-03 18:06:50 | 0:01:23 | 0.212 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1095.0 | 8.17 | 32 56 60 62 |  |
| SF11 | `4_20260903_180700.416` | 2026-09-03 18:07:00.416 | 2026-09-04 07:56:58 | 13:49:58 | 127.482 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.77 | 1.0 | 1587.0 | 10.72 |  |  |
| SF11 | `5_20260904_081927.812` | 2026-09-04 08:19:27.812 | 2026-09-04 08:19:59 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.1 | 1.0 | 805.0 | 9.04 | 32 56 60 |  |
| SF11 | `6_20260904_082008.276` | 2026-09-04 08:20:08.276 | 2026-09-04 08:20:43 | 0:00:35 | 0.09 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.43 | 1.0 | 910.0 | 9.82 | 32 56 60 62 |  |
| SF11 | `7_20260904_082050.456` | 2026-09-04 08:20:50.456 | 2026-09-04 13:41:26 | 5:20:36 | 49.243 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 1.0 | 1813.0 | 8.37 |  |  |
| SF11 | `8_20260904_135558.740` | 2026-09-04 13:55:58.740 | 2026-09-04 13:56:42 | 0:00:44 | 0.113 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.53 | -0.375 | 610.0 | 10.52 | 60 62 |  |
| SF11 | `9_20260904_135650.425` | 2026-09-04 13:56:50.425 | 2026-09-04 19:38:11 | 5:41:21 | 52.432 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.13 | 1.0 | 1248.0 | 8.25 |  |  |
| SF11 | `10_20260904_200952.853` | 2026-09-04 20:09:52.853 | 2026-09-04 20:10:00 | 0:00:08 | 0.02 | FM65 | no | clean | normal | 0.13 | 1.0 | 511.0 | 9.02 | 32 56 60 62 |  |
| SF11 | `11_20260904_202754.501` | 2026-09-04 20:27:54.501 | 2026-09-04 20:28:48 | 0:00:54 | 0.139 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.27 | 1.0 | 944.0 | 8.23 | 32 56 60 62 |  |
| SF11 | `12_20260904_202856.246` | 2026-09-04 20:28:56.246 | 2026-09-05 08:42:45 | 12:13:49 | 112.714 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.57 | 1.0 | 2054.0 | 10.49 |  |  |
| SF11 | `0_20260905_092100.459` | 2026-09-05 09:21:00.459 | 2026-09-05 09:21:06 | 0:00:06 | 0.017 | FM65 | no | clean | normal | 0.62 | 0.75 | 491.0 | 9.72 | 32 56 58 60 62 |  |
| SF11 | `1_20260905_092337.689` | 2026-09-05 09:23:37.689 | 2026-09-05 09:23:44 | 0:00:07 | 0.019 | FM65 | no | clean | normal | 0.0 | 1.0 | 642.0 | 10.96 | 32 56 58 60 62 |  |
| SF11 | `2_20260905_094119.699` | 2026-09-05 09:41:19.699 | 2026-09-05 09:41:56 | 0:00:37 | 0.094 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 528.0 | 8.76 | 32 56 60 62 |  |
| SF11 | `3_20260905_094205.930` | 2026-09-05 09:42:05.930 | 2026-09-05 15:02:10 | 5:20:04 | 49.164 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 1.0 | 1510.0 | 7.94 |  |  |
| SF11 | `4_20260905_150551.060` | 2026-09-05 15:05:51.060 | 2026-09-05 15:05:52 | 0:00:02 | 0.005 | FM65 | no | clean | normal | 0.0 | 1.0 | 600.0 | 10.86 | 58 62 |  |
| SF11 | `5_20260905_151020.899` | 2026-09-05 15:10:20.899 | 2026-09-05 15:10:22 | 0:00:02 | 0.005 | FM65 | no | clean | normal | 0.0 | 1.0 | 620.0 | 9.31 | 58 62 |  |
| SF11 | `6_20260905_151054.529` | 2026-09-05 15:10:54.529 | 2026-09-05 15:11:26 | 0:00:32 | 0.081 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 11.4 | 0.532 | 906.0 | 10.87 | 58 62 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF11 | `7_20260905_151133.499` | 2026-09-05 15:11:33.499 | 2026-09-05 18:08:21 | 2:56:48 | 27.157 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.3 | 0.556 | 1378.0 | 8.87 |  |  |
| SF11 | `0_20260905_183840.121` | 2026-09-05 18:38:40.121 | 2026-09-05 18:39:22 | 0:00:42 | 0.107 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 568.0 | 10.14 | 32 56 58 60 62 |  |
| SF11 | `1_20260905_185845.311` | 2026-09-05 18:58:45.311 | 2026-09-05 18:59:17 | 0:00:33 | 0.084 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 1.0 | 1252.0 | 8.05 | 4 32 56 60 62 |  |
| SF11 | `2_20260905_185931.246` | 2026-09-05 18:59:31.246 | 2026-09-06 07:01:56 | 12:02:25 | 110.964 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.33 | 1.0 | 1853.0 | 12.06 | 58 62 |  |
| SF11 | `3_20260906_072250.053` | 2026-09-06 07:22:50.053 | 2026-09-06 07:22:53 | 0:00:03 | 0.009 | FM65 | no | clean | normal | 0.0 | 1.0 | 458.0 | 10.47 | 4 32 56 58 62 |  |
| SF11 | `4_20260906_080655.015` | 2026-09-06 08:06:55.015 | 2026-09-06 08:07:26 | 0:00:32 | 0.081 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 1476.0 | 7.99 | 4 32 56 60 62 |  |
| SF11 | `5_20260906_080735.254` | 2026-09-06 08:07:35.254 | 2026-09-06 12:32:32 | 4:24:57 | 40.697 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.0 | 0.422 | 1913.0 | 7.86 | 3 |  |
| SF11 | `0_20260906_124136.884` | 2026-09-06 12:41:36.884 | 2026-09-06 13:15:23 | 0:33:46 | 5.187 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.47 | 1.0 | 1346.0 | 9.32 |  |  |
| SF11 | `6_20260906_132454.539` | 2026-09-06 13:24:54.539 | 2026-09-06 13:31:15 | 0:06:21 | 0.976 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.33 | 1.0 | 708.0 | 10.12 | 32 56 58 60 62 |  |
| SF11 | `7_20260906_133154.505` | 2026-09-06 13:31:54.505 | 2026-09-06 13:32:26 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 618.0 | 9.51 | 58 |  |
| SF11 | `8_20260906_133237.255` | 2026-09-06 13:32:37.255 | 2026-09-06 13:33:28 | 0:00:51 | 0.131 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 16.03 | 0.142 | 641.0 | 9.03 | 58 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF11 | `9_20260906_133337.885` | 2026-09-06 13:33:37.885 | 2026-09-06 19:03:52 | 5:30:14 | 50.725 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.73 | 1.0 | 1412.0 | 7.93 |  |  |
| SF11 | `10_20260906_193132.234` | 2026-09-06 19:31:32.234 | 2026-09-06 19:31:36 | 0:00:04 | 0.01 | FM65 | no | clean | normal | 0.0 | 1.0 | 493.0 | 11.24 | 56 58 60 62 |  |
| SF11 | `11_20260906_193522.535` | 2026-09-06 19:35:22.535 | 2026-09-06 19:35:26 | 0:00:04 | 0.01 | FM65 | no | ambiguous | normal | 6.89 | 1.0 | 548.0 | 9.87 | 56 58 60 62 |  |
| SF11 | `12_20260906_195111.187` | 2026-09-06 19:51:11.187 | 2026-09-06 19:52:22 | 0:01:12 | 0.183 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 993.0 | 8.62 | 32 56 60 62 |  |
| SF11 | `13_20260906_195234.827` | 2026-09-06 19:52:34.827 | 2026-09-07 08:12:41 | 12:20:07 | 113.681 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.07 | 1.0 | 702.0 | 10.41 | 58 | recording continues 2.04 h past valid_until 2026-09-07 06:10:00 (cohorts/<key>.yaml ephys.valid_until): probe windows and coverage limited to the valid part |
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
| SF12 | `0_20260903_173523.573` | 2026-09-03 17:35:23.573 | 2026-09-03 17:35:28 | 0:00:05 | 0.012 | FM65 | no | glitchy | normal | 29.76 | 0.993 | 899.0 | 12.08 |  | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF12 | `1_20260903_174101.465` | 2026-09-03 17:41:01.465 | 2026-09-03 17:41:05 | 0:00:05 | 0.012 | FM65 | no | clean | normal | 0.44 | 0.5 | 948.0 | 11.01 | 58 |  |
| SF12 | `2_20260903_180850.290` | 2026-09-03 18:08:50.290 | 2026-09-03 18:09:26 | 0:00:36 | 0.092 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.17 | 0.667 | 901.0 | 7.67 | 58 |  |
| SF12 | `3_20260903_180935.835` | 2026-09-03 18:09:35.835 | 2026-09-04 06:59:36 | 12:50:00 | 118.273 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.5 | 0.143 | 2005.0 | 12.79 |  |  |
| SF12 | `4_20260904_082757.469` | 2026-09-04 08:27:57.469 | 2026-09-04 08:28:28 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.63 | 1.0 | 885.0 | 11.47 | 58 |  |
| SF12 | `5_20260904_082836.973` | 2026-09-04 08:28:36.973 | 2026-09-04 19:39:51 | 11:11:15 | 103.103 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.27 | 0.974 | 1305.0 | 8.01 |  |  |
| SF12 | `6_20260904_201333.325` | 2026-09-04 20:13:33.325 | 2026-09-04 20:13:39 | 0:00:06 | 0.015 | FM65 | no | clean | normal | 0.87 | 1.0 | 951.0 | 11.77 |  |  |
| SF12 | `7_20260904_203029.951` | 2026-09-04 20:30:29.951 | 2026-09-04 20:31:23 | 0:00:54 | 0.138 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.7 | 1.0 | 967.0 | 11.11 |  |  |
| SF12 | `8_20260904_203130.725` | 2026-09-04 20:31:30.725 | 2026-09-05 08:34:14 | 12:02:44 | 111.013 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.9 | 1.0 | 1327.0 | 11.5 |  |  |
| SF12 | `0_20260905_092422.513` | 2026-09-05 09:24:22.513 | 2026-09-05 09:24:27 | 0:00:05 | 0.012 | FM65 | no | glitchy+wide-impulse | wide-impulse | 765.13 | 0.192 | 1088.0 | 11.54 | 58 | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF12 | `1_20260905_094345.171` | 2026-09-05 09:43:45.171 | 2026-09-05 09:44:45 | 0:01:00 | 0.154 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.6 | 1.0 | 1156.0 | 7.44 |  |  |
| SF12 | `2_20260905_094454.579` | 2026-09-05 09:44:54.579 | 2026-09-05 18:01:55 | 8:17:01 | 76.343 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 13.4 | 1.0 | 1279.0 | 7.86 |  | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF12 | `0_20260905_183520.265` | 2026-09-05 18:35:20.265 | 2026-09-05 18:35:34 | 0:00:15 | 0.037 | FM65 | no | glitchy+wide-impulse | wide-impulse | 801.44 | 0.319 | 1323.0 | 10.03 | 58 60 62 | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF12 | `1_20260905_184232.979` | 2026-09-05 18:42:32.979 | 2026-09-05 18:42:36 | 0:00:03 | 0.009 | FM65 | no | clean | normal | 0.0 | 1.0 | 1265.0 | 11.9 |  |  |
| SF12 | `2_20260905_190104.519` | 2026-09-05 19:01:04.519 | 2026-09-05 19:01:05 | 0:00:01 | 0.003 | FM65 | no | clean | normal | 0.0 | 1.0 | 1132.0 | 7.78 | 58 |  |
| SF12 | `3_20260905_190131.729` | 2026-09-05 19:01:31.729 | 2026-09-05 19:02:33 | 0:01:02 | 0.158 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 1117.0 | 7.88 | 58 |  |
| SF12 | `4_20260905_190240.835` | 2026-09-05 19:02:40.835 | 2026-09-06 06:56:58 | 11:54:18 | 109.716 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.2 | 0.4 | 1432.0 | 10.49 |  |  |
| SF12 | `5_20260906_075001.232` | 2026-09-06 07:50:01.232 | 2026-09-06 07:50:08 | 0:00:07 | 0.019 | FM65 | no | ambiguous | normal | 6.19 | 0.978 | 767.0 | 10.11 | 58 |  |
| SF12 | `6_20260906_080910.472` | 2026-09-06 08:09:10.472 | 2026-09-06 08:09:42 | 0:00:32 | 0.081 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 5.37 | 0.993 | 1008.0 | 7.62 | 58 |  |
| SF12 | `7_20260906_080951.055` | 2026-09-06 08:09:51.055 | 2026-09-06 19:09:33 | 10:59:42 | 101.331 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.4 | 0.806 | 1210.0 | 7.2 |  |  |
| SF12 | `8_20260906_193324.937` | 2026-09-06 19:33:24.937 | 2026-09-06 19:33:29 | 0:00:04 | 0.011 | FM65 | no | ambiguous | normal | 2.46 | 1.0 | 654.0 | 7.92 | 58 60 |  |
| SF12 | `9_20260906_195406.514` | 2026-09-06 19:54:06.514 | 2026-09-06 19:54:52 | 0:00:46 | 0.118 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 5.7 | 0.846 | 803.0 | 10.44 | 58 60 |  |
| SF12 | `10_20260906_195502.355` | 2026-09-06 19:55:02.355 | 2026-09-07 08:14:08 | 12:19:06 | 113.525 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 10.27 | 0.721 | 884.0 | 10.96 |  | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF12 | `0_20260907_084725.760` | 2026-09-07 08:47:25.760 | 2026-09-07 08:47:28 | 0:00:03 | 0.008 | FM65 | no | ambiguous | normal | 5.89 | 0.211 | 837.0 | 10.31 | 58 |  |
| SF12 | `1_20260907_090326.668` | 2026-09-07 09:03:26.668 | 2026-09-07 09:04:29 | 0:01:03 | 0.162 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.43 | 1.0 | 731.0 | 7.48 | 58 |  |
| SF12 | `2_20260907_090439.409` | 2026-09-07 09:04:39.409 | 2026-09-07 17:01:37 | 7:56:58 | 73.262 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 7.4 | 0.153 | 1034.0 | 6.06 |  |  |
| SF12 | `0_20260907_174123.397` | 2026-09-07 17:41:23.397 | 2026-09-07 17:41:31 | 0:00:08 | 0.021 | FM65 | no | clean | normal | 0.0 | 1.0 | 607.0 | 9.71 | 58 60 62 |  |
| SF12 | `1_20260907_175922.250` | 2026-09-07 17:59:22.250 | 2026-09-07 17:59:54 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 877.0 | 6.83 | 58 60 62 |  |
| SF12 | `2_20260907_180003.285` | 2026-09-07 18:00:03.285 | 2026-09-08 06:28:36 | 12:28:34 | 114.979 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 9.17 | 0.225 | 1390.0 | 7.21 |  |  |
| SF12 | `3_20260908_070852.297` | 2026-09-08 07:08:52.297 | 2026-09-08 07:08:56 | 0:00:04 | 0.011 | FM65 | no | clean | normal | 0.0 | 1.0 | 760.0 | 11.8 | 58 60 |  |
| SF12 | `4_20260908_072539.270` | 2026-09-08 07:25:39.270 | 2026-09-08 07:26:12 | 0:00:33 | 0.084 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 896.0 | 6.86 | 58 60 |  |
| SF12 | `5_20260908_072624.615` | 2026-09-08 07:26:24.615 | 2026-09-08 19:00:35 | 11:34:11 | 106.626 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.3 | 1.0 | 1160.0 | 6.65 |  |  |
| SF12 | `6_20260908_193131.395` | 2026-09-08 19:31:31.395 | 2026-09-08 19:31:38 | 0:00:07 | 0.017 | FM65 | no | clean | normal | 0.15 | 0.0 | 799.0 | 10.67 |  |  |
| SF12 | `7_20260908_194739.984` | 2026-09-08 19:47:39.984 | 2026-09-08 19:48:13 | 0:00:34 | 0.086 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 862.0 | 6.69 | 58 60 |  |
| SF12 | `8_20260908_194824.915` | 2026-09-08 19:48:24.915 | 2026-09-09 08:22:00 | 12:33:36 | 115.752 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 827.0 | 11.41 |  |  |
| SF12 | `0_20260909_085559.729` | 2026-09-09 08:55:59.729 | 2026-09-09 08:56:02 | 0:00:03 | 0.008 | FM65 | no | clean | normal | 0.0 | 1.0 | 600.0 | 8.02 | 58 60 |  |
| SF12 | `1_20260909_091306.837` | 2026-09-09 09:13:06.837 | 2026-09-09 09:13:42 | 0:00:35 | 0.09 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 716.0 | 7.16 | 58 |  |
| SF12 | `2_20260909_091353.804` | 2026-09-09 09:13:53.804 | 2026-09-09 18:01:55 | 8:48:02 | 81.105 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1085.0 | 7.51 | 63 |  |
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
| SF7 | `0_20260903_071048.371` | 2026-09-03 07:10:48.371 | 2026-09-03 07:10:56 | 0:00:08 | 0.021 | FM65 | no | clean | normal | 0.0 | 1.0 | 620.0 | 12.33 |  |  |
| SF7 | `1_20260903_075030.323` | 2026-09-03 07:50:30.323 | 2026-09-03 07:51:04 | 0:00:34 | 0.088 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 853.0 | 8.4 |  |  |
| SF7 | `2_20260903_075114.355` | 2026-09-03 07:51:14.355 | 2026-09-03 16:46:44 | 8:55:31 | 82.254 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1160.0 | 8.6 |  |  |
| SF7 | `3_20260903_164808.815` | 2026-09-03 16:48:08.815 | 2026-09-03 17:08:07 | 0:19:59 | 3.068 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 960.0 | 12.72 |  |  |
| SF7 | `4_20260903_171804.804` | 2026-09-03 17:18:04.804 | 2026-09-03 17:18:13 | 0:00:09 | 0.023 | FM65 | no | ambiguous | normal | 4.17 | 1.0 | 604.0 | 13.07 |  |  |
| SF7 | `5_20260903_175103.583` | 2026-09-03 17:51:03.583 | 2026-09-03 17:51:36 | 0:00:33 | 0.084 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 759.0 | 9.56 |  |  |
| SF7 | `6_20260903_175144.375` | 2026-09-03 17:51:44.375 | 2026-09-04 07:30:45 | 13:39:01 | 125.801 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 874.0 | 13.46 |  |  |
| SF7 | `7_20260904_080858.239` | 2026-09-04 08:08:58.239 | 2026-09-04 08:09:29 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 592.0 | 11.54 |  |  |
| SF7 | `8_20260904_080936.435` | 2026-09-04 08:09:36.435 | 2026-09-04 13:40:27 | 5:30:51 | 50.818 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1141.0 | 7.99 |  |  |
| SF7 | `9_20260904_135937.346` | 2026-09-04 13:59:37.346 | 2026-09-04 14:00:08 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 675.0 | 9.05 |  |  |
| SF7 | `10_20260904_140015.895` | 2026-09-04 14:00:15.895 | 2026-09-04 14:00:47 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 699.0 | 8.74 |  |  |
| SF7 | `11_20260904_140054.476` | 2026-09-04 14:00:54.476 | 2026-09-04 19:28:33 | 5:27:39 | 50.327 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1042.0 | 8.35 |  |  |
| SF7 | `12_20260904_195148.989` | 2026-09-04 19:51:48.989 | 2026-09-04 19:51:56 | 0:00:08 | 0.02 | FM65 | no | clean | normal | 0.0 | 1.0 | 578.0 | 12.22 |  |  |
| SF7 | `13_20260904_201742.999` | 2026-09-04 20:17:42.999 | 2026-09-04 20:18:15 | 0:00:33 | 0.084 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 677.0 | 14.35 |  |  |
| SF7 | `14_20260904_201825.406` | 2026-09-04 20:18:25.406 | 2026-09-05 08:35:37 | 12:17:13 | 113.235 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.57 | 0.636 | 1425.0 | 8.41 |  |  |
| SF7 | `0_20260905_085618.431` | 2026-09-05 08:56:18.431 | 2026-09-05 08:56:36 | 0:00:18 | 0.045 | FM65 | no | glitchy+wide-impulse | wide-impulse | 276.82 | 0.349 | 1074.0 | 13.25 |  | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF7 | `1_20260905_093210.807` | 2026-09-05 09:32:10.807 | 2026-09-05 09:33:02 | 0:00:52 | 0.133 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 684.0 | 13.18 |  |  |
| SF7 | `2_20260905_093310.289` | 2026-09-05 09:33:10.289 | 2026-09-05 13:15:40 | 3:42:30 | 34.176 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 947.0 | 8.63 |  |  |
| SF7 | `3_20260905_132229.331` | 2026-09-05 13:22:29.331 | 2026-09-05 13:22:34 | 0:00:05 | 0.012 | FM65 | no | clean | normal | 0.0 | 1.0 | 498.0 | 13.36 |  |  |
| SF7 | `4_20260905_132736.589` | 2026-09-05 13:27:36.589 | 2026-09-05 13:27:40 | 0:00:04 | 0.011 | FM65 | no | clean | normal | 0.0 | 1.0 | 716.0 | 15.35 |  |  |
| SF7 | `5_20260905_133036.709` | 2026-09-05 13:30:36.709 | 2026-09-05 13:31:11 | 0:00:34 | 0.088 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 673.0 | 13.03 |  |  |
| SF7 | `6_20260905_133118.469` | 2026-09-05 13:31:18.469 | 2026-09-05 18:00:13 | 4:28:55 | 41.307 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 0.0 | 945.0 | 8.45 |  |  |
| SF7 | `0_20260905_182217.589` | 2026-09-05 18:22:17.589 | 2026-09-05 18:22:28 | 0:00:11 | 0.029 | FM65 | no | glitchy+wide-impulse | wide-impulse | 1559.49 | 0.404 | 1594.0 | 11.96 |  | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF7 | `1_20260905_184646.993` | 2026-09-05 18:46:46.993 | 2026-09-05 18:47:24 | 0:00:37 | 0.095 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 766.0 | 8.65 |  |  |
| SF7 | `2_20260905_184732.855` | 2026-09-05 18:47:32.855 | 2026-09-06 06:54:09 | 12:06:36 | 111.606 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1279.0 | 12.87 |  |  |
| SF7 | `3_20260906_075328.665` | 2026-09-06 07:53:28.665 | 2026-09-06 07:54:19 | 0:00:51 | 0.13 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 662.0 | 13.12 |  |  |
| SF7 | `4_20260906_075426.615` | 2026-09-06 07:54:26.615 | 2026-09-06 12:31:20 | 4:36:54 | 42.531 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1134.0 | 8.45 |  |  |
| SF7 | `0_20260906_123827.548` | 2026-09-06 12:38:27.548 | 2026-09-06 12:39:06 | 0:00:39 | 0.099 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 738.0 | 14.28 |  |  |
| SF7 | `1_20260906_123931.995` | 2026-09-06 12:39:31.995 | 2026-09-06 13:00:54 | 0:21:22 | 3.283 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.27 | 1.0 | 803.0 | 8.75 |  |  |
| SF7 | `5_20260906_132901.675` | 2026-09-06 13:29:01.675 | 2026-09-06 13:29:34 | 0:00:33 | 0.085 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 644.0 | 11.85 |  |  |
| SF7 | `6_20260906_132942.035` | 2026-09-06 13:29:42.035 | 2026-09-06 19:00:56 | 5:31:14 | 50.879 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 977.0 | 8.54 |  |  |
| SF7 | `7_20260906_191821.460` | 2026-09-06 19:18:21.460 | 2026-09-06 19:18:23 | 0:00:02 | 0.006 | FM65 | no | clean | normal | 0.0 | 1.0 | 607.0 | 12.49 |  |  |
| SF7 | `8_20260906_193945.691` | 2026-09-06 19:39:45.691 | 2026-09-06 19:40:24 | 0:00:38 | 0.098 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 650.0 | 12.23 |  |  |
| SF7 | `9_20260906_194035.495` | 2026-09-06 19:40:35.495 | 2026-09-07 08:06:07 | 12:25:32 | 114.515 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.03 | 0.348 | 1176.0 | 13.6 |  |  |
| SF7 | `0_20260907_082905.579` | 2026-09-07 08:29:05.579 | 2026-09-07 08:29:10 | 0:00:05 | 0.012 | FM65 | no | clean | normal | 0.0 | 1.0 | 622.0 | 14.86 |  |  |
| SF7 | `1_20260907_085204.393` | 2026-09-07 08:52:04.393 | 2026-09-07 08:52:40 | 0:00:36 | 0.092 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 679.0 | 13.6 |  |  |
| SF7 | `2_20260907_085247.979` | 2026-09-07 08:52:47.979 | 2026-09-07 09:07:33 | 0:14:46 | 2.267 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.1 | 1.0 | 828.0 | 11.27 |  |  |
| SF7 | `3_20260907_091429.415` | 2026-09-07 09:14:29.415 | 2026-09-07 09:15:00 | 0:00:31 | 0.079 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 656.0 | 13.98 |  |  |
| SF7 | `4_20260907_091511.369` | 2026-09-07 09:15:11.369 | 2026-09-07 16:54:17 | 7:39:06 | 70.519 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 1072.0 | 8.3 |  |  |
| SF7 | `0_20260907_171130.879` | 2026-09-07 17:11:30.879 | 2026-09-07 17:11:37 | 0:00:06 | 0.017 | FM65 | no | clean | normal | 0.0 | 1.0 | 635.0 | 17.56 |  |  |
| SF7 | `1_20260907_174716.243` | 2026-09-07 17:47:16.243 | 2026-09-07 17:48:31 | 0:01:15 | 0.193 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 748.0 | 11.24 |  |  |
| SF7 | `2_20260907_174841.816` | 2026-09-07 17:48:41.816 | 2026-09-08 06:21:07 | 12:32:26 | 115.573 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.1 | 0.667 | 1362.0 | 14.56 |  |  |
| SF7 | `3_20260908_064550.936` | 2026-09-08 06:45:50.936 | 2026-09-08 06:45:56 | 0:00:05 | 0.014 | FM65 | no | clean | normal | 0.0 | 1.0 | 568.0 | 13.31 |  |  |
| SF7 | `4_20260908_071432.143` | 2026-09-08 07:14:32.143 | 2026-09-08 07:15:03 | 0:00:32 | 0.081 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 691.0 | 11.64 |  |  |
| SF7 | `5_20260908_071513.175` | 2026-09-08 07:15:13.175 | 2026-09-08 18:55:54 | 11:40:41 | 107.626 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1035.0 | 8.2 |  |  |
| SF7 | `6_20260908_190921.663` | 2026-09-08 19:09:21.663 | 2026-09-08 19:09:25 | 0:00:03 | 0.009 | FM65 | no | clean | normal | 0.0 | 1.0 | 571.0 | 16.48 |  |  |
| SF7 | `7_20260908_193646.481` | 2026-09-08 19:36:46.481 | 2026-09-08 19:37:18 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 753.0 | 10.26 |  |  |
| SF7 | `8_20260908_193733.435` | 2026-09-08 19:37:33.435 | 2026-09-09 08:16:08 | 12:38:35 | 116.519 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.43 | 0.651 | 1484.0 | 15.28 |  |  |
| SF7 | `1_20260909_083201.648` | 2026-09-09 08:32:01.648 | 2026-09-09 08:32:05 | 0:00:04 | 0.01 | FM65 | no | clean | normal | 0.0 | 1.0 | 538.0 | 12.7 |  |  |
| SF7 | `2_20260909_090244.932` | 2026-09-09 09:02:44.932 | 2026-09-09 09:03:20 | 0:00:35 | 0.09 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 620.0 | 9.97 |  |  |
| SF7 | `3_20260909_090331.016` | 2026-09-09 09:03:31.016 | 2026-09-09 17:55:29 | 8:51:58 | 81.711 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 992.0 | 8.83 |  |  |
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
| SF8 | `0_20260903_171601.361` | 2026-09-03 17:16:01.361 | 2026-09-03 17:16:06 | 0:00:05 | 0.012 | FM65 | no | glitchy | normal | 25.21 | 1.0 | 573.0 | 11.21 | 32 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF8 | `1_20260903_175406.043` | 2026-09-03 17:54:06.043 | 2026-09-03 17:54:46 | 0:00:40 | 0.102 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 1.0 | 928.0 | 8.22 | 32 |  |
| SF8 | `2_20260903_175453.625` | 2026-09-03 17:54:53.625 | 2026-09-04 07:33:42 | 13:38:49 | 125.769 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1115.0 | 11.57 | 32 |  |
| SF8 | `3_20260904_081121.301` | 2026-09-04 08:11:21.301 | 2026-09-04 08:11:58 | 0:00:38 | 0.096 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.43 | 1.0 | 1069.0 | 7.95 | 32 |  |
| SF8 | `4_20260904_081205.535` | 2026-09-04 08:12:05.535 | 2026-09-04 19:30:31 | 11:18:26 | 104.208 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.7 | 0.909 | 1433.0 | 11.01 | 32 |  |
| SF8 | `5_20260904_195428.533` | 2026-09-04 19:54:28.533 | 2026-09-04 19:54:32 | 0:00:04 | 0.01 | FM65 | no | clean | normal | 0.26 | 1.0 | 472.0 | 9.7 | 32 |  |
| SF8 | `6_20260904_202001.469` | 2026-09-04 20:20:01.469 | 2026-09-04 20:20:49 | 0:00:48 | 0.122 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 776.0 | 8.52 | 32 |  |
| SF8 | `7_20260904_202056.765` | 2026-09-04 20:20:56.765 | 2026-09-05 08:37:14 | 12:16:18 | 113.095 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.83 | 1.0 | 1170.0 | 10.81 | 32 |  |
| SF8 | `0_20260905_090305.847` | 2026-09-05 09:03:05.847 | 2026-09-05 09:03:09 | 0:00:03 | 0.008 | FM65 | no | clean | normal | 0.0 | 1.0 | 601.0 | 9.83 | 32 |  |
| SF8 | `1_20260905_093454.761` | 2026-09-05 09:34:54.761 | 2026-09-05 09:35:27 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 594.0 | 8.99 | 32 |  |
| SF8 | `2_20260905_093534.819` | 2026-09-05 09:35:34.819 | 2026-09-05 18:03:42 | 8:28:07 | 78.048 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 9.1 | 1.0 | 1366.0 | 8.02 | 32 |  |
| SF8 | `0_20260905_182324.045` | 2026-09-05 18:23:24.045 | 2026-09-05 18:23:30 | 0:00:06 | 0.017 | FM65 | no | glitchy | normal | 50.07 | 0.997 | 529.0 | 10.25 | 32 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF8 | `1_20260905_185019.429` | 2026-09-05 18:50:19.429 | 2026-09-05 18:50:53 | 0:00:35 | 0.088 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 650.0 | 10.69 | 32 |  |
| SF8 | `2_20260905_185104.563` | 2026-09-05 18:51:04.563 | 2026-09-06 06:55:33 | 12:04:29 | 111.282 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 0.75 | 1515.0 | 11.34 | 32 |  |
| SF8 | `3_20260906_073730.115` | 2026-09-06 07:37:30.115 | 2026-09-06 07:37:32 | 0:00:03 | 0.007 | FM65 | no | clean | normal | 0.39 | 1.0 | 540.0 | 10.63 | 32 |  |
| SF8 | `4_20260906_075745.756` | 2026-09-06 07:57:45.756 | 2026-09-06 07:58:36 | 0:00:51 | 0.129 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1275.0 | 9.33 | 32 |  |
| SF8 | `5_20260906_075845.465` | 2026-09-06 07:58:45.465 | 2026-09-06 07:59:16 | 0:00:31 | 0.081 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 933.0 | 7.93 | 32 |  |
| SF8 | `6_20260906_075927.555` | 2026-09-06 07:59:27.555 | 2026-09-06 19:02:29 | 11:03:02 | 101.842 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.7 | 1.0 | 1154.0 | 12.02 | 32 |  |
| SF8 | `7_20260906_192154.815` | 2026-09-06 19:21:54.815 | 2026-09-06 19:21:57 | 0:00:03 | 0.007 | FM65 | no | clean | normal | 0.36 | 1.0 | 462.0 | 11.37 | 32 |  |
| SF8 | `8_20260906_194246.031` | 2026-09-06 19:42:46.031 | 2026-09-06 19:43:24 | 0:00:38 | 0.098 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1114.0 | 9.36 | 32 |  |
| SF8 | `9_20260906_194333.465` | 2026-09-06 19:43:33.465 | 2026-09-07 08:07:57 | 12:24:24 | 114.341 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 1.0 | 1614.0 | 15.11 | 32 |  |
| SF8 | `0_20260907_082936.983` | 2026-09-07 08:29:36.983 | 2026-09-07 08:29:46 | 0:00:10 | 0.025 | FM65 | no | glitchy+wide-impulse | wide-impulse | 1812.69 | 0.299 | 1375.0 | 10.69 | 32 | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF8 | `1_20260907_085434.285` | 2026-09-07 08:54:34.285 | 2026-09-07 08:55:25 | 0:00:51 | 0.13 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 1.0 | 909.0 | 8.35 | 32 |  |
| SF8 | `2_20260907_085534.719` | 2026-09-07 08:55:34.719 | 2026-09-07 16:55:47 | 8:00:13 | 73.762 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 3.17 | 1.0 | 1289.0 | 10.06 | 32 |  |
| SF8 | `0_20260907_171731.629` | 2026-09-07 17:17:31.629 | 2026-09-07 17:17:39 | 0:00:08 | 0.021 | FM65 | no | glitchy+wide-impulse | wide-impulse | 2426.22 | 0.282 | 1741.0 | 10.47 | 32 | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF8 | `1_20260907_175028.925` | 2026-09-07 17:50:28.925 | 2026-09-07 17:51:05 | 0:00:36 | 0.093 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1181.0 | 8.1 | 32 |  |
| SF8 | `2_20260907_175113.385` | 2026-09-07 17:51:13.385 | 2026-09-08 06:30:03 | 12:38:50 | 116.556 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 744.0 | 10.77 | 32 |  |
| SF8 | `3_20260908_065207.638` | 2026-09-08 06:52:07.638 | 2026-09-08 06:52:11 | 0:00:03 | 0.009 | FM65 | no | clean | normal | 0.29 | 1.0 | 555.0 | 9.83 | 32 |  |
| SF8 | `4_20260908_071653.373` | 2026-09-08 07:16:53.373 | 2026-09-08 07:17:44 | 0:00:51 | 0.13 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 800.0 | 9.1 | 32 |  |
| SF8 | `5_20260908_071754.325` | 2026-09-08 07:17:54.325 | 2026-09-08 18:54:15 | 11:36:22 | 106.961 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 1274.0 | 8.39 | 32 |  |
| SF8 | `6_20260908_191553.671` | 2026-09-08 19:15:53.671 | 2026-09-08 19:16:01 | 0:00:08 | 0.021 | FM65 | no | clean | normal | 0.25 | 1.0 | 478.0 | 9.21 | 32 |  |
| SF8 | `7_20260908_193914.721` | 2026-09-08 19:39:14.721 | 2026-09-08 19:39:48 | 0:00:34 | 0.086 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 604.0 | 10.64 | 32 |  |
| SF8 | `8_20260908_193958.035` | 2026-09-08 19:39:58.035 | 2026-09-09 08:17:50 | 12:37:52 | 116.409 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1332.0 | 9.92 | 32 |  |
| SF8 | `0_20260909_083708.518` | 2026-09-09 08:37:08.518 | 2026-09-09 08:37:13 | 0:00:05 | 0.012 | FM65 | no | clean | normal | 0.21 | 1.0 | 521.0 | 9.46 | 32 |  |
| SF8 | `1_20260909_090526.132` | 2026-09-09 09:05:26.132 | 2026-09-09 09:05:58 | 0:00:33 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 554.0 | 9.68 | 32 |  |
| SF8 | `2_20260909_090608.006` | 2026-09-09 09:06:08.006 | 2026-09-09 17:57:34 | 8:51:26 | 81.629 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 1.0 | 1594.0 | 8.55 | 32 |  |
| SF8 | `0_20260909_181432.740` | 2026-09-09 18:14:32.740 | 2026-09-09 18:15:00 | 0:00:27 | 0.07 | FM65 | no | glitchy+wide-impulse | wide-impulse | 678.32 | 0.204 | 1397.0 | 8.96 | 32 | MEASURED GLITCHY although firmware >= clean_firmware_min; WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use |
| SF8 | `1_20260909_181543.715` | 2026-09-09 18:15:43.715 | 2026-09-09 18:16:52 | 0:01:09 | 0.177 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.2 | 1.0 | 695.0 | 9.41 | 32 |  |
| SF8 | `2_20260909_184954.514` | 2026-09-09 18:49:54.514 | 2026-09-09 18:50:27 | 0:00:33 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 1247.0 | 8.57 | 32 |  |
| SF8 | `3_20260909_185036.554` | 2026-09-09 18:50:36.554 | 2026-09-10 07:21:43 | 12:31:07 | 115.37 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 712.0 | 10.81 | 32 |  |
| SF8 | `4_20260910_075715.519` | 2026-09-10 07:57:15.519 | 2026-09-10 07:57:17 | 0:00:02 | 0.004 | FM65 | no | clean | normal | 0.57 | 1.0 | 523.0 | 10.04 | 32 |  |
| SF8 | `5_20260910_082534.281` | 2026-09-10 08:25:34.281 | 2026-09-10 08:26:15 | 0:00:41 | 0.106 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1099.0 | 8.06 | 32 |  |
| SF8 | `6_20260910_082629.685` | 2026-09-10 08:26:29.685 | 2026-09-10 14:41:44 | 6:15:14 | 57.637 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.53 | 1.0 | 1398.0 | 7.91 | 32 |  |
| SF8 | `9_20260910_184248.287` | 2026-09-10 18:42:48.287 |  |  |  | FM | ? |  |  |  |  |  |  |  | CE_params.bin missing; amplifier.dat missing |
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
| SF9 | `0_20260903_172814.047` | 2026-09-03 17:28:14.047 | 2026-09-03 17:28:18 | 0:00:05 | 0.012 | FM65 | no | glitchy | normal | 20.05 | 1.0 | 517.0 | 11.83 | 2 4 32 36 52 54 56 58 60 62 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF9 | `1_20260903_175700.435` | 2026-09-03 17:57:00.435 | 2026-09-03 17:57:35 | 0:00:35 | 0.089 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 1.0 | 686.0 | 8.96 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260903_175742.843` | 2026-09-03 17:57:42.843 | 2026-09-03 17:58:33 | 0:00:50 | 0.129 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.13 | 1.0 | 868.0 | 8.99 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `3_20260903_175840.384` | 2026-09-03 17:58:40.384 | 2026-09-04 07:14:21 | 13:15:41 | 122.217 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 2.57 | 1.0 | 907.0 | 10.97 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `4_20260904_081348.459` | 2026-09-04 08:13:48.459 | 2026-09-04 08:14:19 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.63 | 1.0 | 792.0 | 7.92 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `5_20260904_081426.496` | 2026-09-04 08:14:26.496 | 2026-09-04 19:32:35 | 11:18:09 | 104.163 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.93 | 1.0 | 1322.0 | 9.42 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `6_20260904_200457.699` | 2026-09-04 20:04:57.699 | 2026-09-04 20:05:02 | 0:00:05 | 0.013 | FM65 | no | ambiguous | normal | 1.38 | 1.0 | 670.0 | 10.29 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `7_20260904_202245.030` | 2026-09-04 20:22:45.030 | 2026-09-04 20:23:17 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.4 | 1.0 | 722.0 | 12.22 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `8_20260904_202324.405` | 2026-09-04 20:23:24.405 | 2026-09-05 08:38:41 | 12:15:17 | 112.941 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.37 | 1.0 | 1566.0 | 9.56 | 0 2 4 14 32 36 48 52 54 56 58 60 62 |  |
| SF9 | `0_20260905_090533.177` | 2026-09-05 09:05:33.177 | 2026-09-05 09:05:39 | 0:00:06 | 0.017 | FM65 | no | clean | normal | 0.93 | 0.667 | 706.0 | 10.4 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260905_090827.360` | 2026-09-05 09:08:27.360 | 2026-09-05 09:08:33 | 0:00:06 | 0.015 | FM65 | no | clean | normal | 0.17 | 1.0 | 654.0 | 10.46 | 2 4 32 36 48 52 54 56 58 60 62 |  |
| SF9 | `2_20260905_094626.859` | 2026-09-05 09:46:26.859 | 2026-09-05 09:46:58 | 0:00:32 | 0.081 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.5 | 1.0 | 779.0 | 7.3 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `3_20260905_094705.608` | 2026-09-05 09:47:05.608 | 2026-09-05 18:05:04 | 8:17:59 | 76.49 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 17.27 | 1.0 | 908.0 | 9.5 | 2 4 32 36 52 54 56 58 62 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF9 | `0_20260905_182816.369` | 2026-09-05 18:28:16.369 | 2026-09-05 18:28:22 | 0:00:06 | 0.017 | FM65 | no | ambiguous | normal | 3.88 | 1.0 | 631.0 | 12.71 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260905_183137.335` | 2026-09-05 18:31:37.335 | 2026-09-05 18:31:40 | 0:00:03 | 0.008 | FM65 | no | glitchy | normal | 62.57 | 0.243 | 816.0 | 12.71 | 2 4 32 36 52 54 56 58 60 62 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF9 | `2_20260905_185327.844` | 2026-09-05 18:53:27.844 | 2026-09-05 18:54:15 | 0:00:47 | 0.121 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.0 | 1.0 | 1104.0 | 9.48 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `3_20260905_185422.206` | 2026-09-05 18:54:22.206 | 2026-09-06 06:58:58 | 12:04:37 | 111.301 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.47 | 0.857 | 1650.0 | 12.82 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `4_20260906_074331.963` | 2026-09-06 07:43:31.963 | 2026-09-06 07:43:33 | 0:00:02 | 0.004 | FM65 | no | clean | normal | 0.0 | 1.0 | 483.0 | 9.69 | 2 4 14 32 36 52 54 56 58 60 62 |  |
| SF9 | `5_20260906_080057.451` | 2026-09-06 08:00:57.451 | 2026-09-06 08:01:30 | 0:00:33 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.1 | 1.0 | 715.0 | 7.08 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `6_20260906_080138.006` | 2026-09-06 08:01:38.006 | 2026-09-06 08:02:09 | 0:00:31 | 0.08 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.47 | 1.0 | 812.0 | 7.04 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `7_20260906_080216.656` | 2026-09-06 08:02:16.656 | 2026-09-06 19:05:17 | 11:03:01 | 101.84 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.37 | 1.0 | 1290.0 | 9.18 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `8_20260906_192429.559` | 2026-09-06 19:24:29.559 | 2026-09-06 19:24:38 | 0:00:09 | 0.022 | FM65 | no | clean | normal | 0.12 | 1.0 | 770.0 | 11.09 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `9_20260906_194509.557` | 2026-09-06 19:45:09.557 | 2026-09-06 19:45:42 | 0:00:33 | 0.085 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.13 | 1.0 | 731.0 | 12.71 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `10_20260906_194554.666` | 2026-09-06 19:45:54.666 | 2026-09-06 19:46:26 | 0:00:32 | 0.082 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.63 | 1.0 | 720.0 | 12.45 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `11_20260906_194634.836` | 2026-09-06 19:46:34.836 | 2026-09-07 08:09:20 | 12:22:46 | 114.088 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.23 | 1.0 | 871.0 | 11.5 | 0 2 4 32 36 48 52 54 56 58 60 62 |  |
| SF9 | `0_20260907_083821.055` | 2026-09-07 08:38:21.055 | 2026-09-07 08:38:25 | 0:00:05 | 0.012 | FM65 | no | ambiguous | normal | 7.65 | 0.0 | 642.0 | 10.03 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260907_085726.079` | 2026-09-07 08:57:26.079 | 2026-09-07 08:58:32 | 0:01:06 | 0.169 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 547.0 | 9.45 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260907_085841.028` | 2026-09-07 08:58:41.028 | 2026-09-07 16:57:05 | 7:58:25 | 73.484 | FM65 | no | glitchy | normal,normal,normal,normal,normal | 13.07 | 1.0 | 1160.0 | 12.4 | 2 4 32 36 52 54 56 58 62 | MEASURED GLITCHY although firmware >= clean_firmware_min |
| SF9 | `0_20260907_172319.145` | 2026-09-07 17:23:19.145 | 2026-09-07 17:23:23 | 0:00:05 | 0.012 | FM65 | no | ambiguous | normal | 2.48 | 0.167 | 791.0 | 11.2 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260907_175303.871` | 2026-09-07 17:53:03.871 | 2026-09-07 17:53:35 | 0:00:32 | 0.082 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 687.0 | 9.64 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260907_175350.496` | 2026-09-07 17:53:50.496 | 2026-09-07 17:54:23 | 0:00:33 | 0.085 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.07 | 1.0 | 690.0 | 9.66 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `3_20260907_175435.676` | 2026-09-07 17:54:35.676 | 2026-09-08 06:25:38 | 12:31:03 | 115.362 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.5 | 0.0 | 1533.0 | 13.33 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `4_20260908_065839.235` | 2026-09-08 06:58:39.235 | 2026-09-08 06:58:42 | 0:00:04 | 0.009 | FM65 | no | clean | normal | 0.28 | 1.0 | 740.0 | 13.42 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `5_20260908_072013.430` | 2026-09-08 07:20:13.430 | 2026-09-08 07:20:48 | 0:00:35 | 0.089 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.97 | 1.0 | 1141.0 | 10.45 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `6_20260908_072057.385` | 2026-09-08 07:20:57.385 | 2026-09-08 18:57:24 | 11:36:27 | 106.974 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.57 | 1.0 | 1530.0 | 9.44 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `7_20260908_192020.964` | 2026-09-08 19:20:20.964 | 2026-09-08 19:20:34 | 0:00:13 | 0.034 | FM65 | no | clean | normal | 0.83 | 0.182 | 692.0 | 11.49 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `8_20260908_194228.662` | 2026-09-08 19:42:28.662 | 2026-09-08 19:43:01 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.37 | 1.0 | 826.0 | 9.63 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `9_20260908_194312.545` | 2026-09-08 19:43:12.545 | 2026-09-09 08:19:09 | 12:35:57 | 116.113 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.8 | 1.0 | 1577.0 | 13.41 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `0_20260909_084505.692` | 2026-09-09 08:45:05.692 | 2026-09-09 08:45:13 | 0:00:08 | 0.021 | FM65 | no | clean | normal | 0.12 | 1.0 | 637.0 | 10.13 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `1_20260909_090751.518` | 2026-09-09 09:07:51.518 | 2026-09-09 09:08:24 | 0:00:32 | 0.083 | FM65 | no | clean | normal,normal,normal,normal,normal | 0.03 | 1.0 | 941.0 | 9.73 | 2 4 32 36 52 54 56 58 60 62 |  |
| SF9 | `2_20260909_090835.027` | 2026-09-09 09:08:35.027 | 2026-09-09 17:59:04 | 8:50:30 | 81.485 | FM65 | no | ambiguous | normal,normal,normal,normal,normal | 1.47 | 1.0 | 1266.0 | 9.59 | 2 4 32 36 52 54 56 58 60 62 |  |

## How to use

1. Never analyse a `deglitch? = YES` session from its raw `amplifier.dat`; stage it first: `python ephys/stage_session.py --cohort 2026c --animal <SFxx> --session <folder>` (de-glitches by the firmware gate, writes a clean working copy off-repo).
2. Sort from the staged copy: `python ephys/run_sort_session.py --cohort 2026c --animal <SFxx> --session <folder>`.
3. When FM65 sessions arrive, re-run this index; their `measured_verdict` is the evidence that they are clean.
