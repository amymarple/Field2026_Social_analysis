# WISER failure audit with the head IMU as the stillness truth (cohort 2026c)

**Status:** DONE 2026-10-02 — this plan was written before any audit number was computed; amendments are listed below
(1 and 2 before any audit number, 3 post hoc). Result: [report](../results/2026c/wiser_baseline/reports/wiser_baseline_failure_audit_2026c.md),
[change log](../change_log/2026-10-02-wiser-failure-audit.md).
**Approval:** the user approved step 1 of the new evaluation on 2026-10-02 ("搞吧"); the period selection below was
decided with the user beforehand and is used exactly.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_wiser_failure_audit.py` (imports, never edits,
the existing scripts). **Config:** new `wiser/configs/wiser_failure_audit_2026c.json`.

## Why

The smoothing pilot, V4 and V5 all scored WISER against held-out WISER fixes. That metric is blind to drift (the
"truth" is the drifting fix itself) and is dominated by the per-fix noise floor (fix noise RMS 3.7 in vs method
prediction RMS 1.8–4.8 in). Before designing V6 we need to know **what WISER actually gets wrong and how big it is**,
measured against an independent truth. The tag and the IMU are both on the head (user), so while the head IMU is still
the tag is still and **any WISER displacement is WISER error**. While the animal moves, physical plausibility and the
IMU activity state give a second, weaker truth.

## Established facts used (not re-derived)

WISER lags the head IMU by τ* (SF07/08/09/10/12: 0.20/0.15/0.10/0.20/0.15 s; fixes are aligned by `t − τ*`). Static
per-axis SD by `anchors_used` (x/y, in): 9: 1.6/2.9, 8: 2.1/3.7, 7: 2.9/4.7, 6: 10.6/7.9, 5: 14.6/9.3, 4: 16.5/12.0,
3: 47/37. Jumps (> 30 in within ≤ 0.35 s) ≈ 0.57 % of fixes ≈ 73 per tag-hour, clustered, 44 % from ≤ 6-anchor fixes,
0.09 % during IMU stillness. Static tags wander slowly (acf ≈ 0.3 at 25–100 s). Strict stillness (gate v2): ≥ 1 s,
accelerometer-direction sweep < 0.3°, ‖|a| − g‖ < 0.03 g, |ω| < 3 °/s. The user expects WISER to drift a lot in rain
and to jitter always.

## Periods (field-PC local time; decided with the user — used exactly)

| Set | Period key | Window | Note (user) |
|---|---|---|---|
| calm-dry (primary) | `day_20260905` | 09-05 08:00–18:00 | |
| calm-dry | `day_20260907` | 09-07 08:00–18:00 | |
| calm-dry | `day_20260908` | 09-08 08:00–18:00 | 100-Hz strict windows exist (gate v2) |
| calm-dry | `night_20260905` | 09-05 21:00 → 09-06 04:20 | |
| calm-dry | `night_20260906` | 09-06 21:00 → 09-07 04:20 | |
| calm-dry | `night_20260907` | 09-07 21:00 → 09-08 04:20 | |
| calm-dry | `night_20260908` | 09-08 21:00 → 09-09 04:20 | 100-Hz strict windows exist (gate v2) |
| rain contrast (secondary) | `night_20260903` | 09-03 21:00 → 09-04 04:20 | storm 18.4 mm; regime B starts 09-03 13:59 |
| rain contrast | `night_20260909` | 09-09 21:00 → 09-10 04:20 | 7.2 mm |
| rain contrast | `day_20260910` | 09-10 08:00–18:00 | 12.3 mm in the previous 12 h (wet) |

Animals SF07, SF08, SF09, SF10, SF12 (tags 3079, 3062, 3077, 306b, 3059 via `wiser/configs/rat_identities_2026c.csv`);
SF11 excluded. Handling windows (`cv/configs/cohort3_handling_windows.json`) are excluded **± 5 min**; also excluded:
all-tag WISER silences ± 120 s (as the pilots), tag-validity limits, each logger's own ADC-lane on-windows, IMU QC
failures (no data, saturation, frozen chip, invalid, NaN, Fusion unreliable). The weather of every period (rain mm,
rain minutes, mean wind, gust p95/max, humidity) is recomputed from `F:\weather_data\` (AWN cloud export
`AWN-F8B3B78DEAC9-20260831-20260912.csv`, cross-checked with the daily local files) and listed in the report; the
user's rain figures above are checked, not assumed.

## Inputs (all read-only)

- WISER: `D:\Field2026_analysis_out\2026c\wiser_working\3rdcohort_Spike_2026_3_4.sqlite` (table `reports`, sha256
  prefix checked, opened `mode=ro`). Existing fix caches in `wiser_fix_cache\` are reused (`night_20260908`,
  `day_20260908`); the other eight periods are extracted **once** with `build_imu_wiser_cache.wiser_night` into the
  same root and format (`night_<date>\` / `day_<date>\<SFxx>.csv.gz`, window ± 10 min), never overwriting; a separate
  index `index_failure_audit_2026c.csv` and an appended README paragraph record them.
- IMU: make_imu 50-Hz npz per session (`D:\3rd_rat_spikes\analysis\imu\<SFxx>\<session>.imu.npz`; every session that
  overlaps a period is used, concatenated), the gate-v2 strict windows
  (`imu_attitude_gate_v2_20261001_0847\still_windows.csv.gz`, all windows — **no WISER veto**, the veto would be
  circular here) for `day_20260908` / `night_20260908`, and for the rule validation also `night_20260910` /
  `day_20260911`.
- Smoother parameters: `wiser/configs/wiser_imu_smoothing_2026c.json` `tuned` (unchanged).

## Methods

### 1. Certified stillness

- **Strict (100 Hz):** the gate-v2 windows, used where they exist (`day_20260908`, `night_20260908`).
- **S50 (50 Hz equivalent), everywhere else:** the head-frame specific force is rebuilt exactly from the npz,
  `a_H = R(q)ᵀ (a_earth^lin + g ẑ)` (Fusion's earth acceleration is the rotated accelerometer minus 1 g, so this
  returns the k_a-scaled, bias-free accelerometer; `R(q)ᵀ ẑ = up_head`). 0.1-s blocks (5 samples); a block is a
  candidate when all its samples are QC-valid and every sample has |ω| < 3 °/s; windows grow greedily with the gate-v2
  kernel (`analyze_imu_attitude_gate_v2._strict_kernel`, imported): every block direction within 0.3° of the window
  mean and ‖|ā| − g‖ < 0.03 g, ≥ 1 s. Same thresholds as gate v2. A literal `up_head`-sweep variant (direction of
  `up_head` blocks, |mean a_earth^lin| < 0.03 g) is computed as a check only.
- **Validation of S50** on the four periods with strict windows (`night_20260908`, `day_20260908`, `night_20260910`,
  `day_20260911`), before any audit metric is computed: time-level recall (strict still time covered by S50) and
  precision (S50 time covered by strict), and segment-level agreement (≥ 30-s segments overlapping ≥ 90 %). Allowed
  amendment, decided on these four periods only: if recall < 0.8 because make_imu calibrates the accelerometer with a
  scalar k_a only (orientation-dependent ‖a‖ error), the magnitude tolerance may be widened up to 0.05 g. Any amendment
  is recorded in the report. As a sensitivity check the audit is also run with S50 everywhere.
- **Segments:** consecutive still windows are merged when the gap is ≤ 2.0 s and every 50-Hz sample in the gap is
  QC-valid with |ω| < 20 °/s and VeDBA below the animal's still threshold θ_a (`ephys/imu_lfp_state_check.py`
  `IMU_STILL_THR`, 0.31–0.39 m/s²) — i.e. the gap contains no movement able to translate the head. Primary set:
  segments ≥ 30 s; secondary ≥ 10 s. Both edges are trimmed by 1 s before scoring (residual lag / WISER smoothing).

### 2. Q1 — WISER during certified stillness

Per segment, truth = coordinate-wise median of the raw fixes in the trimmed segment (sensitivity: median of the
≥ 8-anchor fixes). Metrics: per-fix distance RMS / p50 / p90; drift = max distance of the centred 10-s and 60-s rolling
medians from truth (1-s steps, windows wholly inside the segment, ≥ 10 / ≥ 60 fixes; the 60-s metric only for
segments ≥ 120 s); crazy-drift events = 10-s rolling median ≥ 12 in from truth for ≥ 10 s (size = max distance);
jumps = consecutive fixes > 30 in apart within ≤ 0.35 s; fake speed = 1-s centred speed on a 0.25-s grid (linear
interpolation only inside inter-fix gaps ≤ 1 s, as the pilot's `track_metrics`), p50/p95/p99; fake path per minute =
path length of the 1-s resampled track per minute. Rates per hour of stillness; splits by day/night, calm/rain, animal,
zone (house_1/house_2 ROI + 14 in vs outside, at the truth position), `anchors_used` (per fix, or per-segment median),
local hour. Because the truth is itself a WISER median, every drift number is a **lower bound** (drift spanning most of
a segment pulls the median with it) — stated in the report.

### 3. Q2 — what the position-only smoothers leave

B1 (library centred median-7), B2 (robust CV Kalman/RTS, per-fix anchor noise), B2′ (= B2 + AR(1) drift; the track is
the position state p, p + b reported for reference) are recomputed with the tuned parameters on every period (all
fixes of the period ± 10 min, IMU-free) and scored with the same truth and metrics (raw → B1 → B2 → B2′). V1 (B2′ +
ZUPT) and V2 (B2′ with IMU-switched process noise) use the pilot's IMU stillness and are therefore **circular here**:
they are reported only as "what an IMU stillness constraint removes by construction".

### 4. Q3 — motion side (nights)

Truth = physics + IMU state (pilot per-second states: QC-ok, still = VeDBA₁ₛ < θ_a and ω₁ₛ < 10 °/s, locomoting =
VeDBA₁ₛ ≥ θ_l and stride-band fraction ≥ ρ_l, tuned values). (a) Impossible speed: 1-s centred speed > 100 in/s,
events = runs on the 0.25-s grid (merged across ≤ 1 s), per IMU-ok hour, with the IMU state during the event.
(b) Jumps > 30 in within ≤ 0.35 s classified by the IMU within ± 1 s: IMU-quiet (every second QC-ok and still) =
certain WISER failure, else IMU-active. (c) Onset/offset agreement: IMU onset = ≥ 10 s still then ≥ 5 s non-still with
≥ 2 locomoting seconds; WISER departure = first time the centred 3-s median is ≥ 12 in from the pre-onset reference;
lag = departure − onset (censored after 20 s); offsets symmetric (settle = last time ≥ 12 in from the post-offset
reference). Rates by calm/rain, anchors, zone; the same detectors on B1/B2/B2′ tracks.

### 5. Q4 — is "rain → more drift" confirmed?

Rain/calm ratios with 95 % block-bootstrap CIs (blocks = 10 min of one animal-period, resampled within each set,
1000 draws) for: per-fix RMS during stillness, median segment drift₁₀, crazy-drift events per still-hour, jumps per
still-hour, fake-speed p95, and (nights) impossible-speed events and IMU-quiet jumps per IMU-ok hour. Controlled
versions: direct standardisation of the rain strata to the calm weights over `anchors_used` (9 / 8 / 7 / ≤ 6) × zone
(house / outside) for per-fix metrics, zone-only standardisation for segment/event metrics plus per-anchor-stratum
ratios. Also night-only (calm nights vs rain nights) and day-only comparisons, and raining-now vs wet-not-raining minutes
inside the rain periods. **Verdict rule (pre-registered):** "confirmed" if the ratio CI for crazy-drift rate or drift₁₀
excludes 1 in the pooled and the night-only comparison and survives the anchor × zone standardisation; "confirmed, via
fewer anchors" if it holds raw but not standardised; "not confirmed" if the CIs include 1. Confounds named in the
report: humidity/dew 90–98 % every night, animal location (house vs outside) differs between sets, rain night 09-03
starts 7 h after the 13:56 PC reboot / regime B start, extrapolated pc_time tails.

### 6. Q5 — size of the opportunity

On calm-dry periods: total error during stillness (in, fake path per minute, fake speed) raw vs B2′ residual — an ideal
stillness constraint removes the residual by construction, so the B2′ residual is the bar for V6 in still time; and
during motion failures (impossible-speed events, IMU-quiet jumps, onset/offset lags) raw vs B2′. STOP when Q1–Q5 are
answered.

### 7. Human video check list

~20 worst crazy-drift events (animal, start/end field-PC time, size, anchors, zone, camera hourly file under
`F:\3rd_rat\<date>\<CH>\` with the offset into the file, by file-name time — never the OSD): CH01/CH02 panoramas for
outside, the in-box camera for house zones (house_2 → CH07, house_1 → CH08). The agent does not open or judge images.

## Amendments (before any audit metric was computed)

1. **S50 calibration (2026-10-02, decided on validation data only).** A prototype on two validation cases
   (SF07 `night_20260908`, SF09 `day_20260908`) showed that the make_imu accelerometer (scalar k_a only) carries
   per-axis offsets of up to ≈ 1.3 m/s² (|a| ≈ 11.2 m/s² in some orientations), so the ‖|ā| − g‖ < 0.03 g test rejects
   most still time: time-level recall vs the strict windows 0.31 / 0.41 (tolerance 0.05 g: 0.31 / 0.88). Instead of
   widening the tolerance, S50 now applies **the same accelerometer self-calibration as the A3 chain** to the rebuilt
   50-Hz accelerometer: ellipsoid a_cal = D (a − o) fitted per animal-period on its own 0.5-s quasi-static windows
   (median |ω| < 10 °/s, every per-axis SD < 0.15 m/s², `analyze_wiser_ins_fusion.fit_ellipsoid` with the V4 priors,
   imported unchanged); thresholds stay 0.3° / 0.03 g / 3 °/s. Prototype result: recall 0.87 / 0.99, precision
   0.85 / 0.95; fitted offsets match the A3 ones × k_a. The full validation on the four overlap periods is reported.
2. **Onset/offset rule (2026-10-02, after a single dry-run night, before any Q3 aggregate).** On the dry run
   (SF07 `night_20260908`) the planned rule (≥ 10 s still, then 5 s all non-still with ≥ 2 locomoting seconds) fired
   once per night: after a still run the rats are first active in place and locomote later (≥ 2 locomoting seconds in
   the next 10 s after only 2–4 % of still runs ≥ 10 s). The test is now anchored on the IMU still runs (pilot 1-s
   rule, ≥ 10 s): **onset** = a still run followed by a first locomoting second within 60 s with no still or unusable
   second before it; reference = median track over the run's last 9 s; WISER departure = first time the centred 3-s
   median is ≥ 12 in from it; classes early (WISER departs while the head is still, < run end − 2 s), before-loco,
   on-time (± 2 s of the first locomoting second), late, censored. **Offset** = a still run preceded within 60 s by a
   last locomoting second with no still or unusable second after it; reference = median over the run's first 1–10 s;
   settle = last time the 3-s median is ≥ 12 in from it; late = settle > run start + 2 s (WISER still away although
   the head is still), else on-time; no-displacement = never ≥ 12 in away.
3. **Q4 standardisation of the segment metrics (2026-10-02, AFTER the first Q4 table — post hoc, both versions
   reported).** §5 specified zone-only standardisation for segment / event metrics, but the verdict rule asks for the
   result to survive "the anchor × zone standardisation". Zone-only turned out to be a no-op (98 % of certified still
   time is in the houses) and gave CONFIRMED. The median drift and the event rates are now also standardised over the
   segment's median `anchors_used` {9, 8, 7, ≤ 6} × zone (calm weights), and the verdict uses that version:
   CONFIRMED, LARGELY VIA FEWER ANCHORS (pooled standardised median-drift ratio 1.21 [1.00, 1.28]). Zone-only rows stay
   in the bootstrap table.

## Self-test (`--selftest`, synthetic, no field data)

A still tag with planted jitter, a slow drift, one crazy-drift event and jumps → each metric recovers the planted size
(RMS, drift₁₀, the event's size/duration, the jump count); the motion detector flags planted impossible jumps and not
the clean motion; S50 on a synthetic 50-Hz record (quaternion + earth linear acceleration built from a synthetic 100-Hz
accelerometer) agrees with the strict rule run on the 100-Hz original.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\wiser_failure_audit_<ts>\`: per-segment, per-fix (still), per-event
  (crazy drift, jumps, impossible speed, onsets/offsets) tables, every method's track at fix times per animal-period,
  per-second IMU states, still windows (strict, S50, check variant), validation, weather, bootstrap, log, provenance —
  so re-scoring needs no re-run.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_failure_audit_2026c.md` (executive summary ≤ 10 lines,
  one section per question, a "do not do" list, definitions with formula + text, caveats, the video check list),
  figures `results/2026c/wiser_baseline/figures/wiser_baseline_failure_audit_*_2026c.png`, pointer
  `run_manifest_failure_audit_2026c.json` (never `run_manifest.json`).
- `change_log/2026-10-02-wiser-failure-audit.md` + top rows in both index READMEs; the `wiser_baseline` row of
  `CLAUDE.md` only.

## Boundaries

No existing script is edited; raw drives read-only; SQLite `mode=ro`; no images are opened or judged; no commits (the
main session reviews and commits).
