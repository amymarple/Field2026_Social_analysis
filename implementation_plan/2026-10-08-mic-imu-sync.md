# In-house microphones ↔ head IMU: who made the sound, and the mic clock (cohort 2026c)

**Date:** 2026-10-08. **Status:** PLAN → pilot (local).

**The user:** "Correlate the IMU and the microphone directly; the rat with the large correlation is the one moving. Video can
wait for video tracking. Do the microphone–IMU sync line first; it is a calibration of movement."

**Related:**
- [2026-10-07-sleep-internal-schedule.md](2026-10-07-sleep-internal-schedule.md) section 4 D (the mic pilot, the
  listening page);
- [2026-10-05-video-clock-sync.md](2026-10-05-video-clock-sync.md) (the same idea for the cameras);
- `ephys/mic_band_levels.py` (the per-second levels and their timing model).

## Why

- **The mics have no time marker.** A file's samples are placed by its name (start / end, field-PC time) and its sample
  count: "stretched", or "end-anchored" for anomalous files. MIC01 runs ~210 ppm fast (≈ 0.76 s per hour), and
  `timing_err_s` bounds the error only within a file.
- **The IMU of every implanted rat is on the field-PC clock** (logger time chain, tens of ms).
- **A rat moving in the house makes sound** (bedding rustle, scratching, knocks).
- **One analysis then gives three things:**
  - (1) the mic's clock offset against the PC, per file, and its drift: the lag of the mic–IMU cross-correlation;
  - (2) who made a sound: the in-house rat whose IMU matches the mic;
  - (3) a calibration of sound against movement, which the sound-candidate events (Phase 6 #29e) and the listening
    page need.

## Definitions

- **Mic envelope.** Per 20-ms frame of the WAV (the same frames, Hann window and normalisation as `mic_band_levels.py`):
  - band power $p_b$ in dB re full scale, for the mic bands b0–b4;
  - frame centres placed on the PC clock by the file's timing model (stretched / end-anchored, as in
    `mic_band_levels.py`), then put on the 50-Hz PC grid by nearest centre;
  - all-zero frames are missing.
- **IMU signal.** $v_a(t) = \log_{10}(\text{VeDBA}_a + 0.01)$ at 50 Hz (make_imu `t_pc_ms`, invalid samples missing).
- **Detrending.** Both signals minus their 2-s running median, then z-scored within the window used.
- **Cross-correlation.** For a mic m, a rat a and a window W (the samples where a is in the mic's house by its WISER
  zone and both signals are valid):
  - $r_{m,a}(\ell)$ = Pearson r of $m(t)$ with $v_a(t+\ell)$, for $\ell \in [-2, +2]$ s in 20-ms steps;
  - peak lag $\hat\ell$ = argmax $r$;
  - $\hat\ell > 0$ means the IMU event lies later on the PC grid than the mic's, i.e. the mic timeline runs ahead.
- **Shift null.** The peak $r$ over $[-2, +2]$ s after moving the IMU by 30–90 s (20 shifts). A pair is "coupled" if its
  peak $r$ is above the null's 99th percentile, from the maximum over the shifts.
- **Negative control.** Rats elsewhere (the other house or the field) over the same window.
- **Mic offset per window.** The weighted median of $\hat\ell$ over the coupled in-house rats (weights = peak r).
  Drift within an hour = the slope of the offset over 10-min sub-windows.
- **Who moved (attribution).**
  - Per mic transient (the frame level in b2 ≥ 10 dB above its 2-s median, after ≥ 1 s below), with the mic offset
    applied: the in-house rats with an IMU movement onset (Phase-6 rule) within ±0.2 s.
  - Summaries: the share of transients with exactly one, several or no moving rat, vs the same count at shifted times.

## Pilot (local, before any full run)

- **Hours.** MIC01 (house_2) and MIC02 (house_1). Per mic, the 6 hours (3 days × one day hour + one night hour,
  08-31 → 09-10) with the most rat-seconds in that house that have a valid IMU. Chosen by occupancy only, before
  looking at any correlation.
- **Read** from the local raw copy `F:/3rd_rat/<date>/MIC0x/` (read-only).
- **Report** per mic-hour × rat × band: in-house seconds, peak lag, peak r, null 99th percentile, coupled yes / no, and
  the elsewhere controls; the mic offset and drift per hour; and the attribution shares.

**Pass criteria (fixed now):**
- (a) **In-house rats couple:** coupled in ≥ 75 % of mic-hour × rat pairs with ≥ 10 min in the house and ≥ 20 movement
  onsets (primary band b2 4–20 kHz; the other bands are reported).
- (b) **Rats elsewhere do not:** ≤ 10 % coupled.
- (c) **Rats agree on the offset:** within one mic-hour, the coupled rats' peak lags lie within ±40 ms of the mic
  offset (2 bins).

If the pilot passes, the full run follows: every mic file, envelope cache + per-file offset / drift table, stored on
storage as a new part (`mic_imu_sync`). If it fails, I report why (signal, band, timing) before changing anything.

## Not in scope

- Video (waits for tracking; the user).
- Labelling sounds as external.
- The camera audio (CH01 / CH02 have stream timestamps and are a separate check).

## Pilot result (2026-10-08, report `results/2026c/ephys_spikes/reports/ephys_spikes_mic_imu_sync_pilot_2026c.md`)

**Criteria (fixed before results):**
- (a) PASS: 95.7 % of in-house pairs coupled (44 / 46).
- (b) PASS: 2.7 % of pairs elsewhere coupled. This also confirms MIC02 = house_1.
- (c) FAIL by the rule: 9 / 12 mic-hours agree within 40 ms. In each of the 3 failures one rat deviates while the
  others agree:
  - SF07 −0.18 s vs the house's −0.02 s (09-03 03:00). Its session `4_20260903_001558.656` has a "one-end-only"
    PC-time fit.
  - SF10 −0.08 s (09-04 05:00). That hour lies in its session's extrapolated 7-h tail.
  - SF11 −0.08 s (09-06 14:00). OK-native fit, 15 ms residual.
  
  So the failures look like logger-clock errors, which the mic exposes as a clock common to the house; they are not
  mic errors.

**Mic offset under the file-name timing model:** −0.02 s in 10 of 12 hours (both mics), −0.04 s in one, and +0.18 s
for every rat in MIC02 09-04 12:00 (a file offset).

**Not resolved:**
- **Drift within an hour.** The 10-min windows are too noisy: single windows jump by up to 1.8 s.
- **Attribution of single transients by onset coincidence.** House_2 transients have an in-house onset within 0.2 s in
  10–23 % vs 6–10 % at shifted times. House_1 is at chance.

**Proposed next (needs the user's go):**
- **Full run** over every mic file, without the 10-min windows and with 10 null shifts:
  - an offset per file = the median over the coupled in-house rats;
  - a per-rat deviation from that median = a logger-clock QC flag;
  - the 50-Hz band-envelope cache.
- **Attribution by local correlation** around each sound, the rat with the highest r, tested against shifted times.
  This replaces the onset rule.
