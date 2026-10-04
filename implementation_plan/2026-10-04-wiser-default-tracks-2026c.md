# Production: default WISER tracks for all of cohort 2026c (V3 for implanted animals, B2 otherwise)

**Status:** PLANNED 2026-10-04, written before any output of this step existed.
**Approval:** proposed after V3 became the default and V6 closed the inertial-position line; the user approved it together
with the turn feasibility step on 2026-10-04 ("做"). **Production only — no new test, no new claim.** The tool is
method-parameterised so a later default (e.g. a turn-aided V7) is a re-run from the same caches. Operational details are
marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/build_wiser_default_tracks.py --cohort 2026c [--method V3]
[--labels …] [--dates …] [--workers N] [--selftest]`. **Reader:** new `wiser/src/default_tracks.py`
(`load_default_track(label, date, cohort="2026c")`, `list_default_tracks(cohort)`), re-exported nowhere else.

## Established facts (not re-derived)

- **Default** (`change_log/2026-10-03-wiser-v3.md`): **V3** = one B2 filter (pilot `tuned.B2`: q = 3 in²/s³, per-fix noise
  from `anchors_used`, χ² gate + 2 Huber IRLS passes) + q × 10 on IMU-QC-ok locomoting steps + Huber ZUPT σ 0.25 in/s in
  IMU-still runs ≥ 3 s eroded by 1 s, no release; where the IMU QC fails, B2 dynamics in the same filter. **B2** for every
  tag without an IMU and every time without an IMU session. Kernel: `analyze_wiser_v3.py` (reproduces B2 / V1b / V3 exactly).
- Identities: `wiser/configs/rat_identities_2026c.csv` (shortid → animal with valid_from / valid_until; SF11 3058
  remount 09-02 08:15 → 09-07 08:20, 3058 on no animal 08-31 19:24 → 09-02 08:00 = exclude; tags valid to 09-12 10:10).
  Five non-implanted females were released 09-11 19:40; their tags were never stated.
- WISER DBs (copies, read-only): `D:\Field2026_analysis_out\2026c\wiser_working\3rdcohort_Spike_2026_3*.sqlite` (one file per
  WISER restart). Existing caches use `wiser_night` of `build_imu_wiser_cache.py` (dedup per (tag, timestamp): max
  `anchors_used`, ties → min reportid; masks `m_handling`, `m_silence`, `m_tag_validity`, `m_adc_lane`).
- IMU per-second QC/states: the failure audit's rule (pilot thresholds per animal; QC = missing samples, saturation, frozen,
  invalid, Fusion recovery, handling ± 5 min, all-tag silence ± 120 s, own ADC lane, tag limits); step B reproduced the
  audit's `imu_seconds` from the make_imu npz with 100 % agreement. τ* = 0.20 / 0.15 / 0.10 / 0.20 / 0.15 s (SF07 / 08 / 09 /
  10 / 12); SF11's τ* is not measured **[op: use the median of the five, 0.15 s, flagged]**.

## Scope

All shortids in the DBs from release (2026-08-30 19:00) to 2026-09-12 10:10, per field-PC calendar day (00:00–24:00),
each day run with ± 10-min margins and only the core written **[op]**. Labels: the animal (`SF07` … `SF12`) inside a tag's
validity window; any other shortid → `tag_<shortid>` (no identity claim; the report lists them with first/last fix and
counts, and flags those that appear only after 09-11 19:40). Fixes outside every validity window of a known tag (e.g. 3058
on no animal) are not tracked.

## Caches written once (never overwriting existing files)

- **Full-day WISER fixes:** `D:\Field2026_analysis_out\2026c\wiser_fix_cache\full_<YYYYMMDD>\<label>.csv.gz` — same
  function and columns as the existing caches; index `index_full_2026c.csv`; README section appended.
- **IMU seconds for every session:** `D:\Field2026_analysis_out\2026c\imu_seconds_cache\<SFxx>\<YYYYMMDD>.csv.gz` — sec,
  ok, still, state, vedba_1s, omega_1s, sbf, plus the head layer from make_imu: turn_net_deg, turn_abs_deg, pitch_mean,
  roll_mean (+ README). This is the head-behaviour layer (turn left = positive turn_net_deg, counter-clockwise seen from
  above); it is **not** merged into WISER coordinates.

## Track output

`D:\Field2026_analysis_out\2026c\wiser_default_tracks\<label>\<YYYYMMDD>.csv.gz`, one row per deduplicated fix: `t_ms`
(WISER clock), `t_al_ms` (τ*-aligned, implanted only), `x_raw`, `y_raw`, `anchors_used`, `valid`, masks, `x`, `y`, `vx`,
`vy` (default track, in / in/s, WISER frame), `method` (V3 / B2 per fix), `imu_ok`, `imu_state`, `zupt`, `loco_boost`;
plus `index_2026c.csv` (label, date, method share, fixes, hours, IMU-ok share) and README (definitions, the in-place
caveat: do not read V3 1-s speed/path during in-place activity labelled locomotion as translation; positions in the
unverified WISER inch frame).

## Verification

- `--selftest` (synthetic, no field data): day stitching with margins equals one continuous run away from the seams
  (≤ 1e-6 in); label assignment across a tag swap; unknown-tag labelling; V3 with no IMU = B2.
- **Reproduction:** the IMU seconds reproduce the audit's `imu_seconds` for every audit period (100 %); the production V3
  equals the saved V3 tracks of the V3 run (`wiser_v3_20261003_1425`) at fixes ≥ 10 min from the audit-window edges
  (report max |Δ|; edges differ because production runs continuous days); fix-cache rows equal the existing caches for the
  overlapping windows.
- Coverage table per label × day; IMU fallback share; list of days/labels with no IMU session.

## Outputs in the repo

- Report `results/2026c/wiser_baseline/reports/wiser_baseline_default_tracks_2026c.md` (coverage, reproduction, how to
  load), pointer `run_manifest_default_tracks_2026c.json`; `change_log/2026-10-04-wiser-default-tracks.md`. The main
  session updates CLAUDE.md and both index READMEs and commits. No behavioural or spatial claim is made.

## Caveats

The females' tags are unidentified; SF11's τ* is assumed; production days include periods never audited (e.g. 08-30 –
09-02 regime A, rain days) — the default's validation covers only the audit periods; positions stay in the unverified
WISER frame until the anchor ↔ pole georeference exists.
