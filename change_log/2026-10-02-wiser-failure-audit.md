# 2026-10-02 — WISER failure audit with the head IMU as the stillness truth (cohort 2026c)

**Plan:** [`implementation_plan/2026-10-02-wiser-failure-audit.md`](../implementation_plan/2026-10-02-wiser-failure-audit.md),
approved by the user 2026-10-02 ("搞吧"); step 1 of the new evaluation. Audit only: nothing is tuned, accepted or promoted.
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_failure_audit_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_failure_audit_2026c.md)
(full Definitions section, 5 figures, video check list). **Bulk:** `D:\Field2026_analysis_out\2026c\wiser_failure_audit_20261002_1511\`;
pointer `results/2026c/wiser_baseline/reports/run_manifest_failure_audit_2026c.json` (`run_manifest.json` untouched).

## What changed

- **New** `wiser/scripts/analyze_wiser_failure_audit.py` (`--selftest` ALL PASS, 18 checks on synthetic data: a still tag with
  planted jitter / 6-in drift / 20-in × 30-s crazy drift / 5 spikes → RMS within 5 %, drift 6.1 in, one event of 20.7 in × 29 s,
  10 jumps; motion detector flags the 2 planted 150-in excursions and not 20 in/s locomotion, classifies 2 IMU-quiet + 2 IMU-active
  jumps; S50 on a synthetic 50-Hz record recovers the planted accelerometer offsets and agrees with the strict rule on the 100-Hz
  original, recall = precision = 1.00; the merge rule). `--report-only <run_dir>` re-scores from the saved tables.
  Existing scripts are imported unchanged (smoothing pilot B1/B2/B2′/V1/V2 and IMU states, gate-v2 strict kernel and video lookup,
  V4 ellipsoid fit, calibration-pilot masks, `build_imu_wiser_cache.wiser_night`).
- **New** `wiser/configs/wiser_failure_audit_2026c.json` (periods exactly as decided with the user, all thresholds).
- **New WISER fix caches** (one-time extraction, same function / format / root, never overwriting): `wiser_fix_cache\night_20260903`,
  `night_20260905`, `night_20260906`, `night_20260907`, `night_20260909`, `day_20260905`, `day_20260907`, `day_20260910` (40 files),
  index `index_failure_audit_2026c.csv`, README paragraph appended.
- Periods: calm-dry days 09-05/07/08 (08:00–18:00) + nights 09-05/06/07/08 (21:00–04:20); rain contrast nights 09-03 (18.4 mm by
  rate integral, 20.1 mm by counter), 09-09 (7.2 mm) and day 09-10 (0 mm during, 12.2 mm in the previous 12 h) — the user's figures check out.
- **Amendments:** (1) S50 = the gate-v2 strict rule on the accelerometer rebuilt from the make_imu quaternion + earth acceleration,
  ellipsoid self-calibrated like the A3 chain (the scalar-k_a accelerometer failed the 0.03-g test: prototype recall 0.31 / 0.41);
  (2) onset/offset test anchored on IMU still runs (the planned rule fired once per night) — both before any audit number;
  (3) **post hoc**: segment metrics in Q4 also standardised over the segment's median anchors × zone (zone-only, as planned, was a
  no-op and gave CONFIRMED; the verdict rule asks for anchors × zone) — both versions reported.

## Verification

- S50 vs the 100-Hz strict windows on the four gate-v2 periods (19 of 20 animal-periods; SF12 `day_20260911` has no make_imu npz):
  time recall median 0.992 (min 0.869), precision 0.902 (min 0.781); ≥ 30-s segment time recall 0.998, precision 0.889. The literal
  `up_head`-sweep variant fails (recall 0.29). On 09-08 day + night the audit metrics are the same with strict or S50 segments
  (median segment RMS 4.02 / 4.04 in, 10-s drift 1.39 / 1.41 in, jumps 44.4 / 44.0 per h, fake path 252 / 253 in/min).
- Weather recomputed from `F:\weather_data\AWN-F8B3B78DEAC9-20260831-20260912.csv` (cross-check with the local daily files).

## Results (raw WISER unless noted; certified still segments ≥ 30 s; calm-dry | rain)

- **Truth:** 97 h of IMU-certified head stillness (74.6 | 22.6 h), 98 % inside the two house ROIs (+ 14 in); 52 % of the day and
  7 % of the night (IMU-ok time) are in ≥ 30-s stillness. Fix rate 3.96 Hz (no dropout during stillness).
- **Q1 jitter / drift:** per-fix RMS 5.6 | 7.7 in (p99 18.3 | 27.4 in; ≤ 6-anchor fixes 13.8 in, 9-anchor 3.6 in); worst 10-s median
  per segment: median 1.5 | 2.1 in, p90 3.8 | 6.6 in; 60-s 0.6 | 1.0 in. Crazy drift (≥ 12 in ≥ 10 s): 3 events in 75 h (0.04/h) |
  6 in 23 h (0.27/h). Jumps (> 30 in ≤ 0.35 s): 55 | 191 per still-hour. Fake path 268 | 371 in/min, fake speed p95 11.7 | 19.4 in/s.
  No animal stands out. The wet day 09-10 is bad only until ≈ 11:00 (09–10 h: 10.2–10.5 in RMS, ≈ 415 jumps/h) and calm-like from noon.
  4 tags drifted ≥ 12 in within 4 min on 09-10 ≈ 09:49–09:52 while certified still (common-mode event).
- **Q2 smoothers:** B2′ leaves 1.48 | 2.61 in RMS, 27 | 36 in/min fake path, 1.07 | 1.53 in/s p95, 0 jumps; 10-s drift 1.28 in (−15 %),
  60-s drift +13 %; in the rain B2′ follows low-anchor clusters into more ≥ 12-in excursions than raw (14 vs 6). B1 keeps 42 % of the RMS
  and 40 % of the fake path. V1/V2 (IMU stillness inside — circular) reach ≈ 1 in/min fake path by construction.
- **Q3 motion (nights):** impossible speed (> 100 in/s) 1.15 | 1.37 events per IMU-ok hour (19 % | 9 % with a still IMU), jumps 77 | 192/h,
  IMU-quiet jumps 6.0 | 23.1/h (91 % | 63 % from ≤ 6-anchor fixes); every smoother removes the impossible speeds, B2/B2′ every jump.
  Early onsets (WISER moves while the head is still) 0 % | 4 %, late settles 0 % | 5 %; departures > 2 s after the first locomoting
  second 22 % | 25 % (ambiguous: WISER latency vs time to walk 1 ft).
- **Q4 rain:** **CONFIRMED, LARGELY VIA FEWER ANCHORS** (pre-registered rule; anchors × zone–standardised CI reaches 1). Median 10-s drift
  ×1.41 [1.26, 1.48] raw, ×1.21 [1.00, 1.28] standardised (nights ×1.24 [1.06, 1.58]); ×2.5 [1.7, 2.9] while it is actually raining;
  per-fix RMS ×1.39 (standardised ×1.13); jumps ×3.5 (×1.6); crazy drift ×6.6 [1.6, 26] raw, ×2.2 [0.5, 8.7] standardised.
  Rain still fixes: 9 anchors 30 % vs 59 %. Confounds: 3 rain episodes, humidity 90–98 % every night, location, 09-03 reboot.
- **Q5 the bar for V6:** an IMU stillness constraint can at most remove what B2′ leaves in still time — 1.5 in RMS, 27 in/min
  (≈ 41 m per still-hour) of fake path, 1.1 in/s p95 (rain 2.3–2.7 in, 36 in/min) — on 7 % of the night / 52 % of the day; on the
  motion side B2′ leaves 0 impossible speeds and 0 jumps. V6 must be scored against certified-still truth, not held-out fixes.

## Headline definitions (full set in the report)

- **Certified still segment:** gate-v2 strict windows (100 Hz) or S50 windows (block direction within 0.3° of the window mean,
  $|\lVert\bar{\mathbf a}_W\rVert-g|<0.03g$, every $|\boldsymbol\omega|<3$ °/s, ≥ 1 s) merged across gaps ≤ 2 s with every sample
  $|\boldsymbol\omega|<20$ °/s and VeDBA $<\theta_a$; ≥ 30 s (also ≥ 10 s); 1 s trimmed at both ends. Text: time when the head — and so the tag — does not move.
- **Truth** $\mathbf c_\sigma = \operatorname{med}_k \mathbf z_k$ (coordinate-wise, raw fixes of the segment). Text: the constant position of a still tag; drift is a lower bound.
- **Per-fix RMS** $(\frac1N\sum_k \lVert\hat{\mathbf p}_k-\mathbf c_\sigma\rVert^2)^{1/2}$ (in). Text: how far one fix is from the still head.
- **10-s drift** $d^{(10)}_\sigma=\max_c\lVert\operatorname{med}_{t_k\in[c-5,c+5)}\hat{\mathbf p}_k-\mathbf c_\sigma\rVert$ (in, 1-s centres, ≥ 10 fixes). Text: the worst offset surviving 10-s median averaging.
- **Crazy-drift event:** ≥ 10 consecutive centres with $\lVert\mathbf m^{(10)}(c)-\mathbf c_\sigma\rVert\ge 12$ in; rate per still-hour. Text: a still rat placed ≥ 1 ft away for ≥ 10 s.
- **Jump:** $\lVert\hat{\mathbf p}_{k+1}-\hat{\mathbf p}_k\rVert>30$ in with $t_{k+1}-t_k\le0.35$ s. **IMU-quiet jump:** every second in $[\lfloor t\rfloor-1,\lfloor t\rfloor+1]$ QC-ok and still. Text: a certain WISER failure.
- **Fake speed / path:** $v(t)=\lVert\tilde{\mathbf p}(t+0.5)-\tilde{\mathbf p}(t-0.5)\rVert/1$ s (0.25-s grid), $\Pi=\sum_s\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/(N_s/60)$ (interpolation only inside gaps ≤ 1 s). Text: speed and path invented during stillness.
- **Impossible-speed event:** a run of $v>100$ in/s in QC-ok IMU seconds (runs merged across ≤ 1 s), per IMU-ok hour.
- **Rain/calm ratio** $\rho=\theta(\text{rain})/\theta(\text{calm})$, 95 % CI from 1000 resamples of 10-min animal-period blocks within each set;
  standardised = rain strata re-weighted to the calm weights over anchors × zone (the fix's anchors for RMS, the segment's median anchors for drift and rates).

## Caveats

Truth is the segment's own WISER median (bias invisible, drift a lower bound); still time is almost all inside the houses; the rain
contrast is three weather episodes and the block CIs ignore that all tags share the weather; onset/offset lags mix WISER latency with
behaviour; the smoother parameters were tuned on the 09-08/09 night, which is one of the audit nights.
