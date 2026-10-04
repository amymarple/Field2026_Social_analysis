# 2026-10-04 — Default WISER tracks for all of cohort 2026c (production: V3 for the implanted animals, B2 otherwise)

**Plan:** [`implementation_plan/2026-10-04-wiser-default-tracks-2026c.md`](../implementation_plan/2026-10-04-wiser-default-tracks-2026c.md)
(approved by the user 2026-10-04, "做"; committed 5281fc6 before any output). Amendments 1–8 (operational readings only) were
written before any production output; note 9 after the first verify (an added reporting subset only, no output changed).
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_default_tracks_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_default_tracks_2026c.md)
(inputs, labels, coverage per label × day, reproduction, how to load, caveats, Definitions); pointer
`results/2026c/wiser_baseline/reports/run_manifest_default_tracks_2026c.json`.
**Driver:** `wiser/scripts/build_wiser_default_tracks.py --cohort 2026c [--method V3] [--labels …] [--dates …] [--workers N]
[--stages fix imu tracks verify report] [--run-dir …]` (`--selftest` ALL PASS). **Reader:** `wiser/src/default_tracks.py`
(`load_default_track(label, date, cohort="2026c")`, `list_default_tracks(cohort)`).
**Run:** `D:\Field2026_analysis_out\2026c\wiser_default_tracks_run_20261004_1010\` (log, `input_provenance.json` with the four DB
sha256, `tables/`: labels, DB inventory, reproduction, coverage, no-IMU list, fixes outside validity).

**Production only — no new test, no tuning, no behavioural or spatial claim.** The default was decided on 2026-10-03
([V3 change_log](2026-10-03-wiser-v3.md)); this step applies it to every label and calendar day of the cohort and checks that
the production code reproduces the audited numbers.

## What was written (never overwriting; all new)

| output | path | files | size |
|---|---|---|---|
| full-day WISER fixes (day ± 10 min; `build_imu_wiser_cache.wiser_frames`, same columns as the existing caches) | `D:\Field2026_analysis_out\2026c\wiser_fix_cache\full_<YYYYMMDD>\<label>.csv.gz` + `index_full_2026c.csv`; README section appended | 80 | 773 MB |
| IMU seconds: the audit's per-second QC / still / state + head layer (turn_net_deg, turn_abs_deg, pitch_mean, roll_mean) | `D:\Field2026_analysis_out\2026c\imu_seconds_cache\<SFxx>\<YYYYMMDD>.csv.gz` + `index_2026c.csv` + README | 73 | 156 MB |
| default tracks (one row per deduplicated fix; core day only, each day filtered with ± 10 min) | `D:\Field2026_analysis_out\2026c\wiser_default_tracks\<label>\<YYYYMMDD>.csv.gz` + `index_2026c.csv` + README | 79 | 950 MB |

Track columns: `t_ms`, `t_al_ms` (= t_ms − τ*, implanted only), `shortid`, `x_raw`, `y_raw`, `anchors_used`, `valid`, masks
`m_handling`, `m_silence`, `m_tag_validity`, `m_adc_lane`, `m_off_animal`, the default track `x`, `y`, `vx`, `vy` (in, in/s,
WISER frame), `method` (V3 / B2 per fix), `imu_ok`, `imu_state`, `zupt`, `loco_boost`.

## Inputs and labels

- **DB copies** (`D:\Field2026_analysis_out\2026c\wiser_working\`, opened `mode=ro`): `3rdcohort_Spike_2026_3.sqlite` 08-30 18:32 →
  09-01 04:20 (1.87 M rows), `_3_2` 09-01 05:23 → 06:47 (0.10 M), `_3_3` 09-01 07:23 → 09-03 13:55 (3.70 M), `_3_4` 09-03 13:59 →
  09-12 10:51 (15.55 M; sha256 82ccadfde589… as expected). They do not overlap; there is no fix between them.
- **Labels:** SF07–SF10 (one tag each, 08-30 19:00 → 09-12 10:10), SF11 (12378 to 09-02 00:03, then 3058 = 12376 09-02 08:15 →
  09-07 08:20), SF12 (12377, first fix 08-31 06:36), `SF12_tag12376` (SF12's second tag 3058, 08-30 19:00 → 08-31 19:24; first
  tracked fix 08-31 06:10; amendment 1). **No shortid outside the identity table exists in any copy** — no `tag_<shortid>`
  label; the five females released 09-11 19:40 left no tag in the WISER record. Fixes outside every validity window are not
  tracked (pre-release 08-30 18:32–19:00; after 09-12 10:10; 3058 on no animal, e.g. 1,625 fixes 09-07 09:04 → 23:53 and a few
  per day to 09-12 10:40; 12378's 56 fixes 09-02 00:03:00–00:03:26).
- **SF11 implant loss:** the identity table keeps 08:20, but the tag rode on the implant from 06:10:45 (video, `cohorts/2026c.yaml`):
  those 30,257 fixes are flagged `m_off_animal` (amendment 3).

## Coverage (tracked fixes, hours with ≥ 1 fix, V3 share)

| label | days | fixes | hours | V3 share | IMU fallback | ZUPT | loco × 10 |
|---|---|---|---|---|---|---|---|
| SF07 | 14 | 3,784,682 | 271.2 | 84.2 % | 15.8 % | 37.2 % | 9.8 % |
| SF08 | 14 | 3,842,126 | 273.6 | 83.9 % | 16.1 % | 38.0 % | 6.7 % |
| SF09 | 14 | 3,815,973 | 272.2 | 83.7 % | 16.3 % | 38.9 % | 9.3 % |
| SF10 | 14 | 3,848,348 | 272.7 | 82.7 % | 17.3 % | 38.7 % | 10.8 % |
| SF11 | 9 | 2,082,585 | 150.6 | 80.8 % | 19.2 % | 37.9 % | 6.6 % |
| SF12 | 13 | 3,778,144 | 262.5 | 83.2 % | 16.8 % | 39.0 % | 9.0 % |
| SF12_tag12376 | 1 | 15,398 | 1.3 | 5.2 % | 94.8 % | 1.3 % | 1.2 % |

No make_imu sample exists on 08-30 (night 1 was lost on every logger, `cohorts/2026c.yaml` notes), so SF07–SF11 run as B2 that
evening; SF11 has no IMU after 09-07 06:10 (blanked after the implant loss) and no WISER label after 08:20; SF12 has no WISER
fix before 08-31 06:10. The V3 share is ≈ 31 % on 08-31, ≈ 70 % on 09-10 and 54 % for SF12 on 09-11 (the IMU QC excludes
handling windows ± 5 min, ADC-lane windows, all-tag silences ± 120 s and seconds without usable samples; per-day reasons are
not itemised). Per-day table in the report §4.

## Reproduction

- **IMU seconds vs the failure audit's `imu_seconds`** (50 animal-periods, 1,512,000 s): ok / still / state agree on 100.000 %;
  VeDBA max |Δ| 5e-5 m/s² (6 significant digits stored), sbf on ok seconds 5e-7; 59,037 sbf NaN/value mismatches, none in an ok
  second (no-data seconds where the pilot's SBF reads the 2 s after a gap that lies inside the loaded window).
- **Production V3 vs the V3 run's saved V3** (`wiser_v3_20261003_1425`, float32): no fix missing; ≥ 10 min inside the audit
  windows max |Δ| 0.067 in, all of it at the first fixes after the 09-10 AM-round silence (08:20:30–08:20:41), where the V3
  run's own track starts; ≥ 10 min from the audit edges and ≥ 10 min of fix coverage from the V3 run's first/last fix
  (5,555,044 fixes) max |Δ| **4.4e-5 in** (float32), ZUPT / loco masks 100 % equal. Within 1 min of an audit edge up to 5.8 in
  by design (the V3 run had no IMU in its margins). B2 rebuilt from the full-day caches = the saved B2 to 4.3e-5 in.
- **Full-day fix caches vs the 60 existing caches** (7,151,362 rows): 0 rows missing either way, 0 unequal values in reportid /
  x / y / anchors_used / anchors_list / n_list / dup_n / the four masks; `valid` 100 % equal ≥ 60 s and ≥ 10 rows from a window
  edge (99.999 % overall: window-median gap flag), `speed_inps_smooth` equal to 5e-9 in/s there (window-truncated at the ends).
- **Selftest** (synthetic): stitched days = one continuous run (max 2e-11 in), V3 with no IMU / all-failed IMU = B2 exactly,
  label assignment across a tag swap / second tag / unknown tag, head layer, reader round trip.

## Definitions (headline; full set in the report)

- **Label** $\ell(k)$ = animal $a$ if $t^{\rm W}_k \in [v^{\rm from}_{s,a}, v^{\rm until}_{s,a})$ for fix $k$'s tag $s$, else not tracked.
  A fix belongs to the animal whose identity-table window for its tag contains its time.
- **Aligned time** $t^{\rm al}_k = t^{\rm W}_k - \tau^*_a$ (ms). τ* = 0.20 / 0.15 / 0.10 / 0.20 / 0.15 s (SF07 / 08 / 09 / 10 / 12),
  SF11 assumed 0.15 s (median); IMU seconds are read at $\lfloor t^{\rm al}_k/1000\rfloor$.
- **Day stitching** $\hat{\mathbf p}_k = \mathrm{V3}(\{\mathbf z_j : t^{\rm W}_j \in [d_0 - m, d_1 + m)\})_k$ for $t^{\rm W}_k \in [d_0, d_1)$, $m$ = 600 s:
  each calendar day is filtered once with 10 min on both sides, only the core written.
- **Per-fix method** = V3 ⇔ the label has a head IMU ∧ ok($\lfloor t^{\rm al}_k/1000\rfloor$), else B2. **IMU fallback share** =
  1 − V3 share (fraction of a label's fixes run with B2 dynamics).
- **Hours** $H = |\{\lfloor t^{\rm W}_k/1000\rfloor\}| / 3600$: hours of the day with at least one tracked fix (h).
- **Max |Δ|** $= \max_k \lVert \hat{\mathbf p}^{\rm prod}_k - \hat{\mathbf p}^{\rm saved}_k \rVert_2$ (in) over common fixes in the stated subset;
  **agreement** = share of audit seconds with equal value (missing = disagreement).

## Caveats (carry into every use)

Positions are in the **unverified WISER inch frame**. **V3's 1-s speed / summed path during in-place activity that the head IMU
labels locomoting is +62–69 % above B2's — not translation.** The default's validation covers only the audit periods; 08-30 –
09-02 (regime A), rain days and every other hour are produced with the same rule but were never audited. SF11's τ* is assumed;
`SF12_tag12376` uses SF12's IMU and τ*; the females' tags are unknown and absent.

## For the main session (not done here)

- `CLAUDE.md` WISER code map, `wiser_baseline` row: add `build_wiser_default_tracks --cohort 2026c` (production of the default
  tracks: V3 for SF07–SF12 / B2 otherwise; caches `wiser_fix_cache/full_<date>/<label>.csv.gz` (+ `index_full_2026c.csv`),
  `imu_seconds_cache/<SFxx>/<date>.csv.gz` (per-second IMU QC / states + head layer), `wiser_default_tracks/<label>/<date>.csv.gz`
  (+ index, README); run `wiser_default_tracks_run_<ts>`; pointer `run_manifest_default_tracks_<c>.json`; `--selftest`) and the
  reader `wiser/src/default_tracks.py` to the library line; state that analyses should load tracks through the reader.
- `change_log/README.md` and `implementation_plan/README.md` index rows for this entry / the plan's status (DONE 2026-10-04).
- Optional: `analyses`/`STATUS.md` need nothing (no claim).
