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

## Amendment 1 (2026-10-05, operational; written BEFORE any number of this step was computed)

Written by the implementing session after reading the plan and the inputs, before the driver existed and before any rate,
event count or enrichment was computed (the only output seen so far is the B2 build log: file counts and run time). No
definition, threshold or decision rule above is changed; these fix details the plan leaves open (**[op]**) or that cannot be
implemented literally.

1. **B2 tracks.** Absent, so built with `build_wiser_default_tracks.py --cohort 2026c --method B2 --stages tracks --labels
   SF07 SF08 SF09 SF10 SF11 SF12` → `<OUT>/2026c/wiser_tracks_B2/` (run dir `wiser_default_tracks_run_20261005_1704`). The
   `verify` / `report` stages were skipped because the report stage writes the V3 default-tracks report and pointer in
   `results/` (they must not be overwritten); the fix and IMU caches already exist.
2. **Gyro turn Δψ (not implementable from the per-second cache).** The Phase-0 gyro quantity is the difference of 1-s means
   of the integrated 50-Hz turn, ψ̄(c + 1) − ψ̄(c − 1), on a 0.5-s grid; the per-second `turn_net_deg` cannot represent a 1-s
   mean centred on an integer second, so it cannot reproduce Phase 0 to ≤ 0.1°. Δψ is therefore computed exactly as in Phase 0
   from the make_imu 50-Hz npz (the source of the cache's head layer): `analyze_wiser_failure_audit.load_imu` /
   `sample_valid` and `analyze_imu_turn_vs_heading.Gyro`, imported unmodified. The per-second cache supplies `ok` and `state`.
   The error of a per-second approximation is reported for information only.
3. **Heading Δθ and the 1-s speed (I2, I3)** use Phase 0's estimator unchanged: m(t) = coordinate-wise median of the
   track's values at the fixes with aligned time in [t − 0.5, t + 0.5) (≥ 3 fixes), d(h) = m(h + 0.5) − m(h − 0.5), 1-s speed
   |d(h)| / 1 s, θ(h) = atan2 d(h), at h = c ± 1. Tracks: raw fixes, V3, B2. Phase 0's clean-second rule (≥ 8 anchors, open
   field) is **not** applied: it would remove exactly the bad-geometry seconds this audit is about.
4. **"IMU-QC-ok throughout"** (I2, I3) = every field-PC second overlapping the pair's support [c − 2, c + 2) (the fixes that
   enter both headings) is an included second (item 5), and every 50-Hz sample of the gyro span [c − 1.5, c + 1.5) passes
   `sample_valid`.
5. **Included seconds and masks.** Included = the cache's `ok` (which already excludes handling ± 5 min, all-tag silences
   ± 120 s, the ADC-lane window and time outside tag validity), no masked fix (`m_handling`, `m_silence`, `m_tag_validity`,
   `m_adc_lane`, `m_off_animal`) in the second, and before SF11's implant loss (cohort YAML). Masked fixes are dropped from
   every estimate. Time base: aligned time t_al = t_ms − τ* (the IMU / field-PC clock); event lists give field-PC time.
   Denominator of every rate = included seconds (IMU-ok hours).
6. **I1 details.** The ≥ 5-s run length is read before trimming. Reference = coordinate-wise median of the available p̃ over
   the first 2 s of the trimmed run (runs with no p̃ there are "not evaluable" and counted). "≥ 2 consecutive seconds" =
   consecutive seconds with p̃ defined and ≥ 12 in. At most one I1 event per run; its **window** = the union of the run's
   seconds with displacement ≥ 12 in (so its length = the plan's duration); onset = the first such second; size = the
   maximum displacement over the trimmed run; subtype from the trimmed run's states.
7. **I2 / I3 merging.** Qualifying centres whose pair windows [c − 1, c + 1] overlap (spacing < 2 s) form one event; event
   window (enrichment and flags) = [c_first − 2, c_last + 2) (the fixes that enter the headings); size = max |Δθ| (I2) or
   max |Δψ| (I3) over the event's centres.
8. **Day / night.** Night = 21:00–04:20 (the cohort's night window), day = 08:00–18:00, twilight = the remaining hours
   (reported as a third class rather than forced into either). Hour = field-PC clock hour.
9. **Weather class of an hour** (on-site AWN, `F:/weather_data/AWN-F8B3B78DEAC9-20260831-20260912.csv`, read with
   `analyze_wiser_failure_audit.load_weather`): rain = ≥ 1 five-minute row in [H, H + 1 h) with rain rate > 0; wet = not
   rain and the last rain row before H is ≤ 12 h earlier; dry = otherwise; unknown = no weather row in the hour.
10. **Zone of a second** = house when the V3 track's 1-s median p̃ lies inside a house ROI grown by 14 in, else open field;
    seconds without p̃ take the last defined zone (else the next). A window's zone = the zone of its first second (onset);
    the zone detail (house_1 / house_2 / field) chooses the cameras of the event list.
11. **Matched controls.** Same animal, same noon-to-noon "bio-day" (one night each), same track. I1: evaluable event-free
    runs with trimmed length within [0.5, 2]× the event run's; control window = one contiguous stretch of the event window's
    length placed at the event onset's offset from the trimmed-run start (clipped to fit). I2: candidate pairs (speed rule +
    IMU-ok throughout) that are not I2 centres and whose support does not overlap an I2 event window; control window
    [c − 2, c + 2); the controls of one event are ≥ 4 s apart. Up to 5 per event drawn at random (fixed seed); a control may
    serve several events. Events without a control are left out of the enrichment and counted.
12. **Enrichment** pooled over fixes: ≤ 6-anchor share Σ n≤6 / Σ n, dispersion = median over the fixes, fix rate
    Σ n / Σ duration; each event's controls weighted 1/k_e (k_e = its number of controls). Ratio event / control; CI =
    2.5–97.5 percentiles of a 10-min block bootstrap (block = animal × 10-min field-PC clock bin of the window onset;
    1000 replicates; fixed seed). The decision uses V3 I1 + I2 pooled; per type, per track and within zone are reported.
13. **Rates** assign an event to the stratum of its onset second (hour, day/night, zone, weather, animal). A 10-min
    block-bootstrap CI of the pooled rate is reported, not used by the rule.
14. **QC flags** for every V3 default-track day of SF07–SF12 (days without IMU: all 0): `qc_i1` / `qc_i2` = the fix's aligned
    time lies in a V3 I1 / I2 event window, plus `i1_event_id` / `i2_event_id`; same row order as the production file, keyed
    by `t_ms`.
15. **Reproduction** uses all of Phase 0's W = 2 s pairs (not a sample): Δθ (raw, V3) and Δψ from this run's centre arrays.

## Amendment 2 (2026-10-05, written AFTER the first full run's pooled numbers were seen; no definition, threshold or rule changed)

The first full run (`wiser_imu_consistency_20261005_1721`) computed every table, then its aggregation stopped at the
reproduction step (a pandas/numpy type error); the rates, enrichment, size and event-list tables it had written were read.
Checking them found:

1. **Bug (fixed, re-run): event and control times written with 6 significant digits.** The bulk CSVs used `%.6g`, which
   rounds an absolute time (≈ 1.79e9 s) by up to 5,000 s. Only the times in `events.csv.gz` / `controls.csv.gz` were
   affected, and so the onsets and video files of the event lists. Rates, strata, enrichment and QC flags are computed in
   memory and did not change: the re-run `wiser_imu_consistency_20261005_2038` reproduces `rates.csv`, `runs`, `exposure`,
   `repro` and the QC-flag counts exactly, and every non-time event column. Those two tables are now written at full
   precision; the selftest checks the CSV round trip. The aggregation error is fixed too. Run `…_1721` is superseded.
2. **Post-hoc sensitivity (declared; no rule uses it).** By construction (Amendment 1.6) an I1 event window holds only
   seconds with a 1-s median (≥ 2 fixes). A control window is a contiguous stretch and can include seconds with 0–1 fixes.
   This asymmetry could bias the I1 fix-rate ratio (and to a lesser degree the ≤ 6-anchor ratio). The I1 enrichment is
   therefore also reported with both windows restricted to seconds with ≥ 2 raw fixes
   (`tables/enrichment_posthoc_f2.csv`). The pre-registered decision uses the Amendment-1 windows only.
3. **Descriptive addition:** I1 events by trimmed run length (`tables/i1_by_run_length.csv`), because the events cluster in
   long runs.
