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

## Amendment 1 — mic peaks → IMU, in the quiet hour before the morning battery round (the user, 2026-10-08; before results)

**The user:** "Detect mic peaks, simplest first: daytime, rats asleep in the house; for a house-mic peak, look at the
IMU disturbance; 7–8 am, nobody around"; then "before the battery change". The morning round itself falls at 06:45–08:40
on 9 of 11 days, so the window follows the round.

**Windows.**
- Per date (08-31 → 09-11): from round_start − 60 min to round_start − 5 min. round_start = the earliest logged /
  inferred round stop between 05:00 and 10:00 (Phase-0 gap table).
- Dates without such a round: 07:00–08:00.
- Minus the logged acoustic field events (cohorts/2026c.yaml `field_events`).

**Mic peaks.**
- Per house mic (MIC02 = house_1, MIC01 = house_2), 50-Hz envelope as in the pilot.
- A peak = a frame ≥ 10 dB above its 2-s running median after ≥ 1 s below; peak size = that excess (dB).
- Primary band b2 (4–20 kHz); b1 (0.5–4 kHz) and b3 / b4 (20–100 kHz) are reported.
- PC time = mic time − 0.02 s (the pilot's median offset).

**Per peak and in-house rat** (WISER zone = that house; valid IMU):
- the FINAL score at the peak;
- `moved` = a Phase-6 IMU onset within [−0.3, +0.5] s;
- `resp` = the maximum of log10 VeDBA over [−0.3, +0.5] s minus its median over [−3, −1] s;
- the onset lag (negative = the rat moved before the sound).

**Per peak:** the number of in-house rats moving (none / one / several), and the one with the largest resp.

**Null.** The same at 5 random times per peak in the same windows, ≥ 2 s from any peak.

**Reported:**
- the shares none / one / several, observed vs null, by peak size;
- the lag distribution;
- the event-triggered mean VeDBA per rat and state;
- whether asleep rats wake (scored WAKE) within 10 s more often after a peak than at null times.

Descriptive; nothing is promoted from it without the user's listening check.

### Amendment 1 — result (2026-10-08; report `results/2026c/ephys_spikes/reports/ephys_spikes_mic_imu_peaks_2026c.md`)

**Coverage.** 12 windows, 11.1 h. House_2 holds most rats (4.5 in the house on average); house_1 had ~1 rat and 8
b2 peaks per hour, too few to say anything.

**House_2, b2 (4–20 kHz), as pre-registered:**
- 565 peaks per hour. 24.8 % have ≥ 1 in-house rat with an IMU onset within [−0.3, +0.5] s, vs 11.6 % at random times;
  31.8 % for peaks > 30 dB.
- Asleep rats around a peak: NREM moved 11.9 % vs 3.2 % at random times; woke within 10 s 6.6 % vs 3.5 % (REM 14.4 vs
  9.5 %).
- Onset lags peak at −0.1…0 s, i.e. the movement coincides with or slightly precedes the sound.

**Post hoc (not in the plan; scripts in the session scratchpad, numbers here), only house_2 b2 peaks while every
in-house rat was asleep** (n = 640, 58 per hour):
- a rat's onset 17.7 % (random 8.4 %);
- MIC02 also ≥ 10 dB in the same second 3.8 % (0.7 %);
- outdoor CH01 2–8 kHz ≥ 6 dB 19.4 % (16.1 %);
- none of these 64 % (77 %).

At no-onset peaks, asleep rats' head response exceeds the random-time 90th percentile in 19.7 % (NREM) / 13.6 % (REM) of
cases (10 % expected): some small, sub-threshold head motion.

**Reading.** During group sleep, most house-mic peaks are neither a rat's head-movement onset nor an outside or
other-house sound. Body or limb movement, rat sounds and house noises are open; this needs listening.

**Fix.** The random-time label is renamed from "null" to "random_time": pandas reads the string "null" as missing.

## Amendment 2 — USV detector v2 (2026-10-10; before its results)

**Basis.** The user labelled 254 30-s strips (36 with USV; `ephys/configs/usv_review_2026c/`). Detector v1 (median
whitening, tonal components ≥ 30 ms) found 58 % of the USV strips and flagged 20 % of the empty ones. The user says it
has few false positives but misses some; the misses are long calls cut into pieces and short calls. The user: "what
matters first is yes or no; fine detection is the next step."

**v2 (`ephys/usv/usv_detect_v2.py`).** Spectrogram as v1, then:
1. Background per frequency = the 20th percentile of the dB values over the 60-s chunk, not the median, so a frequency
   busy with calls does not raise its own background.
2. Components: excess ≥ 10 dB after a 3 × 3 median filter, 8-connected.
3. Fragments are joined into one contour when the gap is ≤ 50 ms and the ridge frequency jumps ≤ 2 kHz.
4. A contour longer than 5 s is a "line": the drifting electronic tone, which the user tagged "long line", not a call.
5. A call contour = tonal (median 1 − flatness ≥ 0.5), bandwidth ≤ 20 kHz, duration ≥ 10 ms, not a line.

**Strip presence.** Features per strip: the number of call contours (≥ 10 / 20 / 30 ms), the total call duration,
and the longest call.

**Evaluation.**
- The threshold is chosen per mic, leave-one-window-out (Youden J), against the user's labels; sensitivity /
  specificity / precision are reported for v1 and v2 side by side.
- Nothing is tuned on the held-out window itself.

**Full run.** Only if v2 is clearly better than v1 (the user's call): all mic hours, on this PC if the CPU allows,
else BioHPC through `run_then_store.sh`.

### Amendment 2 — result (2026-10-11)

On the 254 labelled strips (36 with USV), each threshold chosen leave-one-window-out per mic (`ephys/usv/usv_eval_v2.py`;
`D:/Field2026_analysis_out/2026c/usv_v2_sample/eval/`):

| mic | v1, best feature | v2, best feature |
|---|---|---|
| MIC01 | tonal any: sensitivity 0.90, specificity 0.66; tonal ≥ 20 ms: 0.86 / 0.72 | total call duration: 0.76 / 0.85, precision 0.48 (v1 0.32–0.35) |
| MIC02 | tonal any: 0.67 / 0.86 | ≤ 0.33 sensitivity: MIC02's short, weak calls are dropped |

- A per-mic logistic model on v1 + v2 features is no better: MIC01 0.76 / 0.78; MIC02 0.73 / 0.79 for one feature set,
  0.33 for the others.

**Verdict.** v2 is not clearly better (MIC01 Youden 0.61 vs 0.58; MIC02 worse), so no full run. Simple count / duration
features plateau at ~0.7–0.85 sensitivity and specificity; in MIC01, more than half of the flagged strips are labelled
"none".
