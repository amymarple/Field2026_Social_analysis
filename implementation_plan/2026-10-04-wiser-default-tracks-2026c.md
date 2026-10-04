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

## Amendments

Amendments 1–8 were made on 2026-10-04 ≈ 10:10 local, **before any production output was written** (after the synthetic
selftest and a scratch smoke test of two days, 09-05/06, written outside the cache roots and discarded, that printed only
reproduction checks). None changes the default, a parameter, a label rule of the plan or a check; they fix operational
readings the plan left open. Source of the facts: a scan of the four DB copies (`3rdcohort_Spike_2026_3.sqlite` 08-30 18:32 →
09-01 04:20, `_3_2` 09-01 05:23 → 06:47, `_3_3` 09-01 07:23 → 09-03 13:55, `_3_4` 09-03 13:59 → 09-12 10:51; shortids 12376,
12377, 12378, 12386, 12395, 12407, 12409 only — no shortid outside the identity table).

1. **Two tags on one animal at the same time [op]:** SF12 wore 3059 (12377, valid the whole cohort) and 3058 (12376, 08-30 19:00
   → 08-31 19:24) together. One filter cannot carry two tags at once, so the tag with the longer validity window keeps the
   animal label (`SF12`) and the other gets its own label `<animal>_tag<shortid>` (`SF12_tag12376`; generic rule, ties → the
   smaller shortid keeps the animal label). It is an implanted animal's tag, so it is tracked like the animal (V3 with SF12's
   IMU and SF12's τ* — the tag's own lag was never measured; flagged in the report). SF11's two tags (12378 to 09-02 00:03,
   12376 from 09-02 08:15) do not overlap and share the label `SF11`; a column `shortid` is added to the track files so the
   tags of one label stay distinguishable.
2. **Full-day fix caches [op]:** each `full_<YYYYMMDD>/<label>.csv.gz` holds the day ± 10 min (as the existing caches hold
   their window ± 10 min), so a day's track is built from its own file; the track files hold only the core day. The rows
   come from `build_imu_wiser_cache.wiser_frames` (the function `wiser_night` calls after its SQL; `wiser_night` opens one
   DB, a day can span two or three copies, so the SQL rows of every copy overlapping the window are concatenated first —
   the copies do not overlap in time). Per label: every fix of its tag(s) in the window; a fix outside the label's
   validity window(s) is kept with `m_tag_validity` = True, recomputed per fix from the label's own window(s) (identical to
   `wiser_frames`' median-time window wherever a day holds one window of the tag — the run logs the count of differences);
   a tag's fixes outside every window that overlaps the day are not cached (they are counted in the report). The filter
   uses only fixes inside a validity window (the plan's "not tracked").
3. **SF11 implant loss [op]:** the identity table keeps SF11 / 3058 to 09-07 08:20 (the plan's source), but
   `cohorts/2026c.yaml ephys.loggers.SF11.implant_lost` = 06:10:45 (video-confirmed; the tag rode on the implant, which lay
   in the house afterwards). The label window is not changed; a track column `m_off_animal` flags fixes at or after an
   animal's `implant_lost` (SF11 06:10:45 → 08:20). The IMU is already blanked there (B2 dynamics).
4. **IMU seconds [op]:** the failure audit's `per_second_states` is called unmodified on each calendar day ± 10 min of
   make_imu samples (the audit's ± 10-min extension), only the core day written; "tag limits" = the union of the animal's
   validity windows (the audit passed the one tag window of its period — identical inside every audit period). A file is
   written for every animal-day with at least one IMU sample in the day. The head layer is computed per field-PC second
   from the 50-Hz npz with make_imu's per-second definitions (make_imu's own `.imu_1s.csv` is on the logger-second grid):
   turn_net_deg = Σ turn_dps / 50, turn_abs_deg = Σ |turn_dps| / 50 (NaN with < 40 samples or any blanked sample),
   pitch_mean, roll_mean (circular) over finite samples (NaN with < 40). Floats are stored with 6 significant digits. Track
   jobs read the IMU seconds of days D − 1, D, D + 1 for the margins.
5. **Track columns [op]:** `method` per fix = V3 where the label has a head IMU and the fix's aligned second is IMU-QC-ok,
   else B2 (the dynamics in force); `t_al_ms` = t_ms − round(1000 τ*) (integer ms; empty for labels without an IMU);
   x, y, vx, vy rounded to 6 decimals; booleans stored as 0/1 (the reader returns bool). Index "hours" = distinct
   field-PC seconds holding ≥ 1 tracked fix ÷ 3600.
6. **Unknown tags [op]:** the rule is implemented (`tag_<shortid>`, window = release 08-30 19:00 → end 09-12 10:10, B2), but
   no such shortid exists in the four copies; the report says so. The scope (release, end, 09-11 19:40) is read from
   `cv/configs/cohort3_handling_windows.json`.
7. **Method parameter [op]:** `--method V3` (default) writes `wiser_default_tracks/`; `--method B2` writes
   `wiser_tracks_B2/`, so a non-default run can never overwrite the default root. A later default is added to the
   driver's method table and run the same way.
8. **Reproduction [op]:** (a) compares ok / still / state per second and the floats; `sbf` is compared on the audit's ok
   seconds (in a second without samples the pilot's SBF function can read the 2 s after a data gap, which depends on the
   loaded window; sbf enters the state only in ok seconds). (b) adds B2 rebuilt from the full-day caches (no IMU) vs the
   V3 run's saved B2 at every window fix — a day-stitching check free of the IMU-margin difference — and the ZUPT / loco
   mask agreement; production vs saved V3 is also reported by distance to the window edge. (c) matches rows on (shortid,
   t_ms); window-independent columns must be equal; `valid` (its gap flag uses the window's median interval) and
   `speed_inps_smooth` (rolling median and 1-s window truncated at a window's ends) are reported overall and ≥ 60 s from
   the window edges.

9. **Note made after the first production verify (2026-10-04 ≈ 10:20; report text only, no cache or track changed):** the
   plan's reproduction subset "fixes ≥ 10 min from the audit-window edges" is reported as written (max |Δ| 0.067 in). Every
   difference > 0.001 in in it sits at the first fixes after the 09-10 AM-round all-tag silence (08:20:30–08:20:41), where the
   V3 run had no fix (or one isolated fix) in its margin, i.e. its own track starts there. The report therefore adds a second
   subset: also ≥ 10 min of fix coverage (inter-fix intervals capped at 5 s) from the V3 run's first / last fix (max |Δ|
   4.4e-5 in = float32 storage). Likewise the fix-cache comparison's "away from the edges" rows are ≥ 60 s **and** ≥ 10 rows
   from a window end (the library speed's rolling median runs over rows, so the first fixes after such a silence are
   row-neighbours of the window edge).
