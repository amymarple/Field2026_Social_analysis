# IMU–WISER consistency audit: where does WISER move while the head IMU says it cannot? (cohort 2026c)

**Status:** PLANNED 2026-10-05, written before any number of this step was computed.
**Approval:** the user's intent (2026-10-04): use the IMU as a **lie detector** for WISER — "WISER jumps away while the IMU
did not move → correct it". Approved on 2026-10-05 ("搞"). This step **measures** the residual inconsistencies in the
production default tracks; a correction is a separate, later test. Operational details are marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_wiser_imu_consistency.py`. **Config:** new
`wiser/configs/wiser_imu_consistency_2026c.json` (verdict in `decision`).

## Why (established facts, not re-derived)

- Already handled in **V3** (the default for implanted animals): WISER motion while the IMU says **still** (Huber ZUPT in
  still runs ≥ 3 s; certified-still jumps 55 | 191 per hour raw → 0; fake path 268 → 3.3 in/min, circular) and every jump
  > 30 in within ≤ 0.35 s (robust gate). Night jumps with a quiet IMU (6 | 23 per hour raw) → 0 in B2/B2′.
- **Not checked:** (i) WISER displacement while the IMU says the head is **active but not locomoting** (in-place
  activity; V3 applies no constraint there); (ii) the WISER **path turning sharply while the head gyro does not turn**
  (a real body turn of ≥ 90° essentially always involves a head turn; the reverse — head turns, path straight — is common
  scanning). Phase 0 (`change_log/2026-10-04-imu-turn-vs-heading.md`) measured the forward direction only (slope 0.64,
  R² 0.20, sign agreement 83 %, path turn lags head turn ≈ 0.2 s).
- The IMU locomotion class has TPR 0.75 / FPR 0.15 (vs WISER speed): a quarter of real walking seconds are labelled
  still/active, so a "displacement without locomotion" event can be a detector miss rather than a WISER error. The
  evidence that an event is a WISER error is therefore its **enrichment in bad-geometry fixes** (≤ 6 anchors, wide raw
  dispersion) relative to matched control windows.
- Inputs exist: production default tracks `D:\Field2026_analysis_out\2026c\wiser_default_tracks\<label>\<date>.csv.gz`
  (V3 / B2 per fix, `imu_ok`, `imu_state`, masks, `x_raw`, `y_raw`, `anchors_used`), the IMU-seconds + head-layer cache
  `…\imu_seconds_cache\<SFxx>\<date>.csv.gz` (`turn_net_deg` + = CCW seen from above), full-day fix caches; reader
  `wiser/src/default_tracks.py`. Handedness normal for all five animals (Phase 0).

## Scope

SF07–SF12 (label = animal), all production days, IMU-QC-ok seconds only, excluding the masks (handling, silence, tag
validity, ADC lane, `m_off_animal`). Tracks: **V3** (the default, primary), **B2** (from `build_wiser_default_tracks
--method B2`, run if absent **[op]**) and the 1-s raw-fix medians for comparison.

## Event definitions

$\tilde{\mathbf p}(s)$ = the coordinate-wise median of the track's fixes with aligned time in $[s, s+1)$ (≥ 2 fixes).

- **I1 — displacement without locomotion.** A run = maximal stretch of consecutive IMU-QC-ok seconds with **no
  locomoting second** (state still or active), length ≥ 5 s, trimmed by **2 s at both ends** **[op]** (loco-detector edge
  misses). Reference $\mathbf r$ = median of $\tilde{\mathbf p}$ over the first 2 s of the trimmed run; event when
  $\lVert\tilde{\mathbf p}(s)-\mathbf r\rVert\ge$ **12 in** for ≥ 2 consecutive seconds inside the run; size = the maximum,
  duration = seconds ≥ 12 in. Sub-typed by the run's states (all still / any active).
- **I2 — path turn without head turn.** On a 0.5-s grid of centres c, with the 1-s track speed ≥ 10 in/s at c − 1 and c + 1
  and IMU-QC-ok throughout: heading change $\Delta\theta$ (W = 2 s, Phase-0 definition, from the track) with
  $|\Delta\theta|\ge$ **90°** while the gyro turn $|\Delta\psi|<$ **20°**; overlapping centres merge into one event.
- **I3 (reported only) — head turn without path turn:** $|\Delta\psi|\ge 90°$ while $|\Delta\theta|<20°$ (same grid and speed
  rule) — expected to be mostly scanning / turning in place.

## Metrics

- **Rates** per IMU-ok hour for I1, I2, I3, per track (V3, B2, raw medians), by day | night, house | open field (house
  ROIs + 14 in), weather class of the hour **[op]**: *rain* (any 5-min row of the on-site AWN station with rain rate > 0,
  `F:\weather_data`), *wet* (≤ 12 h after rain), *dry*; per animal.
- **Enrichment (the evidence that an event is WISER's fault):** for each event window vs **matched controls** (same type of
  window without an event — no-loco runs of similar length for I1, locomotion pairs ≥ 10 in/s for I2 — same animal and
  night, up to 5 per event **[op]**): the share of raw fixes with ≤ 6 anchors, the median raw-fix dispersion about the 1-s
  median, the fix rate. Ratio event / control with a 10-min block-bootstrap CI.
- **Size distributions** (I1 displacement, I2 turn angle) and how many I1 events V3 vs B2 contain (does V3's ZUPT already
  remove the still-run part).
- **Event list for the user's video check:** the 30 largest I1 and the 30 largest I2 events (V3), with animal, time,
  zone, anchors, and the hourly file + offset under `F:\3rd_rat\<date>\<CH>\` by file-name time (house_1 → CH08 + CH05,
  house_2 → CH07 + CH06, open field → CH01 + CH02; IR at night). The agent does not look at any frame.
- **QC flags (always written):** per fix, `qc_i1`, `qc_i2` (inside an event window) →
  `D:\Field2026_analysis_out\2026c\wiser_default_tracks_qc\<label>\<date>.csv.gz` (+ README); the production tracks are not
  modified.

## Pre-registered decision

**Material** if, for V3 pooled over all included hours, the combined rate of I1 + I2 is **≥ 1 per IMU-ok hour** **and** the
pooled ≤ 6-anchor share in event windows is **≥ 2×** that of the matched controls (point estimate, CI lower bound > 1) →
propose a correction (e.g. a soft speed cap during non-locomoting runs, down-weighting fixes of turn-inconsistent windows)
as a new pre-registered test, scored against these events, certified stillness and the clean-WISER speed. Otherwise
**not material**: V3 stays as is; the QC flags are the deliverable. Per-type results are reported either way.

## Verification

- `--selftest` (synthetic): a track with walking bouts (head turns = path turns + scanning), in-place activity with a
  planted 15-in WISER drift built from ≤ 6-anchor fixes, a planted sideways 90° WISER kink during straight running with no
  gyro turn, a real 90° turn with a gyro turn, and IMU states with planted loco-detector misses at run edges → I1 / I2 / I3
  find the planted events and not the real turn; the 2-s trimming removes edge misses; enrichment ≈ planted ratio; flags
  cover the event windows.
- Reproduction: the Phase-0 heading / gyro-turn quantities on its clean pairs are reproduced from the production caches
  (same W = 2 s values to ≤ 0.1°) **[op: on a sample]**.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\wiser_imu_consistency_<ts>\`: `tables/` (events, controls, rates, enrichment,
  bootstrap, event lists), `summary.json`, `input_provenance.json`, `log.txt`; QC flags as above.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_imu_consistency_2026c.md` (+ figures), pointer
  `run_manifest_imu_consistency_2026c.json`; `change_log/2026-10-05-wiser-imu-consistency.md`. The main session updates
  CLAUDE.md and both index READMEs and commits.

## Caveats known in advance

No ground truth: an event is a WISER error, a detector miss or a real movement the IMU state does not capture (e.g. being
pushed in a huddle); enrichment is circumstantial evidence, the video check decides. Head turn ≠ body turn (scanning), so I2
uses a strict asymmetric rule. House interiors have worse geometry by default, so enrichment is also reported within zone.
The 12-in / 90° / 20° thresholds were set in advance and are not tuned.
