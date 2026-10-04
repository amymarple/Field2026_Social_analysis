# Default WISER tracks for all of cohort 2026c — production (V3 for the implanted animals, B2 otherwise)

**Status:** production run 20261004_1010 (caches written at git `363df84+dirty`; report rendered at `137e2db+dirty`). **Production only — no new test, no tuning, no behavioural or spatial claim.** Plan: [`implementation_plan/2026-10-04-wiser-default-tracks-2026c.md`](../../../../implementation_plan/2026-10-04-wiser-default-tracks-2026c.md) (approved 2026-10-04, committed 5281fc6 before any output; amendments at its end). Driver `wiser/scripts/build_wiser_default_tracks.py` (`--selftest` passes); reader `wiser/src/default_tracks.py`. Bulk run: `D:\Field2026_analysis_out\2026c\wiser_default_tracks_run_20261004_1010`; pointer `run_manifest_default_tracks_2026c.json`.

The default itself was decided earlier ([V3 report](wiser_baseline_v3_2026c.md), [change_log 2026-10-03](../../../../change_log/2026-10-03-wiser-v3.md)): **V3** for SF07–SF12 wherever the head-IMU QC passes (the same filter runs with B2 dynamics where it fails or no IMU session exists), **B2** for every other tag. This step only applies it to every label and day and checks that the production code reproduces the audited numbers.

> **Carry these caveats into every use.** Positions are in the **unverified WISER inch frame** (offset origin; no paddock georeference until the anchor ↔ pole fit exists). **V3's 1-s speed / summed path during in-place activity that the head IMU labels 'locomoting' is +62–69 % above B2's — not translation.** The default's validation covers only the audit periods (09-03 … 09-11); 08-30 – 09-02 (regime A), the other rain days and every other hour are produced with the same rule but were never audited.

## 1. What was written

| cache / output | path | files | size |
|---|---|---|---|
| full-day WISER fixes (day ± 10 min) | `D:\Field2026_analysis_out\2026c\wiser_fix_cache\full_<YYYYMMDD>\<label>.csv.gz` + `index_full_2026c.csv` | 80 | 773 MB |
| IMU seconds (QC, states, head layer) | `D:\Field2026_analysis_out\2026c\imu_seconds_cache\<SFxx>\<YYYYMMDD>.csv.gz` + `index_2026c.csv` + README | 73 | 156 MB |
| default tracks | `D:\Field2026_analysis_out\2026c\wiser_default_tracks\<label>\<YYYYMMDD>.csv.gz` + `index_2026c.csv` + README | 79 | 950 MB |
| run (logs, provenance, tables) | `D:\Field2026_analysis_out\2026c\wiser_default_tracks_run_20261004_1010` | | |

## 2. Inputs

WISER DB copies (one per WISER restart; opened `mode=ro` + `query_only`; spans are the first / last fix of any tag, field-PC local):

| file | first fix | last fix | rows | shortids | sha256 (first 16) |
|---|---|---|---|---|---|
| `3rdcohort_Spike_2026_3.sqlite` | 2026-08-30 18:32:35 | 2026-09-01 04:20:06 | 1,869,951 | 12376, 12377, 12378, 12386, 12395, 12407, 12409 | `0fe2b6bfac7a1575` |
| `3rdcohort_Spike_2026_3_2.sqlite` | 2026-09-01 05:23:34 | 2026-09-01 06:47:16 | 100,998 | 12377, 12378, 12386, 12395, 12407, 12409 | `00e1afad632b77cd` |
| `3rdcohort_Spike_2026_3_3.sqlite` | 2026-09-01 07:23:14 | 2026-09-03 13:55:58 | 3,698,453 | 12376, 12377, 12378, 12386, 12395, 12407, 12409 | `4bea8c3d1ba20d6d` |
| `3rdcohort_Spike_2026_3_4.sqlite` | 2026-09-03 13:59:55 | 2026-09-12 10:51:19 | 15,550,527 | 12376, 12377, 12386, 12395, 12407, 12409 | `82ccadfde5897d00` |

The 4 copies do not overlap in time; between consecutive copies there is no fix at all (09-01 04:20 → 09-01 05:23, 09-01 06:47 → 09-01 07:23, 09-03 13:55 → 09-03 13:59). The identity table is `wiser/configs/rat_identities_2026c.csv`; the IMU is the make_imu 50-Hz npz under `D:/3rd_rat_spikes/analysis/imu/`; method parameters come unchanged from `wiser/configs/wiser_v3_2026c.json` → `wiser_imu_smoothing_2026c.json` (`tuned`) and the exclusions from `wiser_failure_audit_2026c.json`.

## 3. Labels

| shortid | label(s) [validity, local) | DBs | first fix | last fix | fixes tracked | fixes outside every window (dedup.) | outside first → last |
|---|---|---|---|---|---|---|---|
| 12376 | SF11 [09-02 08:15 → 09-07 08:20); SF12_tag12376 [08-30 19:00 → 08-31 19:24) | 3;3_3;3_4 | 08-30 18:32:35 | 09-12 10:40:18 | 1,568,284 | 5,508 | 08-30 18:32:35 → 09-12 10:40:18 |
| 12377 | SF12 [08-30 19:00 → 09-12 10:10) | 3;3_2;3_3;3_4 | 08-31 06:36:50 | 09-12 10:51:19 | 3,778,144 | 2,640 | 09-12 10:10:00 → 09-12 10:51:19 |
| 12378 | SF11 [08-30 19:00 → 09-02 00:03) | 3;3_2;3_3 | 08-30 18:32:35 | 09-02 00:03:26 | 529,699 | 6,251 | 08-30 18:32:35 → 09-02 00:03:26 |
| 12386 | SF08 [08-30 19:00 → 09-12 10:10) | 3;3_2;3_3;3_4 | 08-30 18:32:36 | 09-12 10:38:57 | 3,842,126 | 7,915 | 08-30 18:32:36 → 09-12 10:38:57 |
| 12395 | SF10 [08-30 19:00 → 09-12 10:10) | 3;3_2;3_3;3_4 | 08-30 18:32:35 | 09-12 10:50:38 | 3,848,348 | 8,471 | 08-30 18:32:35 → 09-12 10:50:38 |
| 12407 | SF09 [08-30 19:00 → 09-12 10:10) | 3;3_2;3_3;3_4 | 08-30 18:32:35 | 09-12 10:24:39 | 3,815,973 | 8,621 | 08-30 18:32:35 → 09-12 10:24:39 |
| 12409 | SF07 [08-30 19:00 → 09-12 10:10) | 3;3_2;3_3;3_4 | 08-30 18:32:35 | 09-12 10:40:36 | 3,784,682 | 8,563 | 08-30 18:32:35 → 09-12 10:40:36 |

**Unknown shortids: 0.** No shortid outside the identity table appears in any of the four DB copies, so no `tag_<shortid>` label exists; the five non-implanted females released 09-11 19:40 left no tag in the WISER record (their tags were never stated).
 SF12 wore two tags at once from the release to 08-31 19:24 (3059 = 12377, the primary, first fix 08-31 06:36, and 3058 = 12376): the second gets its own label `SF12_tag12376` (amendment 1). Tag 3058 then carried no animal until SF11's remount (09-02 08:15) and again after 09-07 08:20 — those fixes are not tracked. SF11's track from the implant loss (2026-09-07 06:10:45, video-confirmed) to 08:20 is the tag riding on the dropped implant (left in the house, retrieved 07:24–08:09 per `cohorts/2026c.yaml`), not the rat: flagged `m_off_animal` (amendment 3).
 First tracked fix per label: SF07 08-30 19:00, SF08 08-30 19:00, SF09 08-30 19:00, SF10 08-30 19:00, SF11 08-30 19:00, SF12 08-31 06:36, SF12_tag12376 08-31 06:10 (release 08-30 19:00). Label-days with a fix-cache file but no tracked fix (all their fixes outside the validity window): SF12_tag12376 2026-08-30.

## 4. Coverage per label × day

Hours = field-PC seconds holding ≥ 1 tracked fix ÷ 3600; V3 = share of the day's fixes whose aligned second is IMU-QC-ok (the rest run with B2 dynamics = the IMU fallback).

| date | SF07 | SF08 | SF09 | SF10 | SF11 | SF12 | SF12_tag12376 |
|---|---|---|---|---|---|---|---|
| 2026-08-30 | 4.7 h · V3 0 % | 4.7 h · V3 0 % | 4.7 h · V3 0 % | 4.7 h · V3 0 % | 4.7 h · V3 0 % | — | — |
| 2026-08-31 | 15.5 h · V3 31 % | 15.4 h · V3 31 % | 15.6 h · V3 30 % | 15.4 h · V3 31 % | 15.4 h · V3 31 % | 9.9 h · V3 48 % | 1.3 h · V3 5 % |
| 2026-09-01 | 19.6 h · V3 86 % | 20.1 h · V3 73 % | 19.8 h · V3 80 % | 19.9 h · V3 80 % | 19.9 h · V3 80 % | 20.2 h · V3 85 % | — |
| 2026-09-02 | 21.0 h · V3 96 % | 21.6 h · V3 97 % | 21.0 h · V3 95 % | 21.3 h · V3 95 % | 14.2 h · V3 94 % | 21.7 h · V3 77 % | — |
| 2026-09-03 | 21.7 h · V3 80 % | 21.9 h · V3 90 % | 21.7 h · V3 91 % | 21.8 h · V3 91 % | 21.7 h · V3 89 % | 22.0 h · V3 90 % | — |
| 2026-09-04 | 22.5 h · V3 92 % | 22.7 h · V3 92 % | 22.6 h · V3 91 % | 22.6 h · V3 91 % | 22.5 h · V3 94 % | 22.6 h · V3 90 % | — |
| 2026-09-05 | 22.3 h · V3 90 % | 22.4 h · V3 90 % | 22.4 h · V3 89 % | 22.4 h · V3 82 % | 22.3 h · V3 91 % | 22.4 h · V3 90 % | — |
| 2026-09-06 | 21.7 h · V3 91 % | 22.5 h · V3 88 % | 22.5 h · V3 87 % | 22.5 h · V3 79 % | 21.6 h · V3 92 % | 22.4 h · V3 88 % | — |
| 2026-09-07 | 22.4 h · V3 89 % | 22.5 h · V3 90 % | 22.4 h · V3 88 % | 22.4 h · V3 89 % | 8.2 h · V3 74 % | 22.4 h · V3 90 % | — |
| 2026-09-08 | 22.5 h · V3 93 % | 22.4 h · V3 93 % | 22.5 h · V3 93 % | 22.5 h · V3 93 % | — | 22.4 h · V3 94 % | — |
| 2026-09-09 | 22.5 h · V3 93 % | 22.6 h · V3 93 % | 22.5 h · V3 93 % | 22.5 h · V3 93 % | — | 22.5 h · V3 94 % | — |
| 2026-09-10 | 22.5 h · V3 71 % | 22.5 h · V3 70 % | 22.5 h · V3 71 % | 22.5 h · V3 71 % | — | 22.4 h · V3 71 % | — |
| 2026-09-11 | 22.2 h · V3 91 % | 22.2 h · V3 91 % | 22.2 h · V3 87 % | 22.2 h · V3 91 % | — | 21.7 h · V3 54 % | — |
| 2026-09-12 | 10.0 h · V3 99 % | 10.0 h · V3 99 % | 9.9 h · V3 99 % | 10.0 h · V3 97 % | — | 9.9 h · V3 96 % | — |

**Totals per label:**

| label | method | days | fixes | hours | V3 share (fixes) | IMU fallback share | ZUPT share | loco ×10 share | m_handling | m_silence | m_adc_lane | m_off_animal | τ* (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | V3 | 14 | 3,784,682 | 271.2 | 84.2 % | 15.8 % | 37.2 % | 9.8 % | 252,009 | 16,849 | 77,477 | 0 | 0.2 |
| SF08 | V3 | 14 | 3,842,126 | 273.6 | 83.9 % | 16.1 % | 38.0 % | 6.7 % | 272,689 | 17,788 | 76,346 | 0 | 0.15 |
| SF09 | V3 | 14 | 3,815,973 | 272.2 | 83.7 % | 16.3 % | 38.9 % | 9.3 % | 272,388 | 17,436 | 76,752 | 0 | 0.1 |
| SF10 | V3 | 14 | 3,848,348 | 272.7 | 82.7 % | 17.3 % | 38.7 % | 10.8 % | 269,474 | 17,517 | 78,294 | 0 | 0.2 |
| SF11 | V3 | 9 | 2,082,585 | 150.6 | 80.8 % | 19.2 % | 37.9 % | 6.6 % | 172,720 | 10,315 | 0 | 30,257 | 0.15 (assumed) |
| SF12 | V3 | 13 | 3,778,144 | 262.5 | 83.2 % | 16.8 % | 39.0 % | 9.0 % | 223,088 | 18,483 | 78,488 | 0 | 0.15 |
| SF12_tag12376 | V3 | 1 | 15,398 | 1.3 | 5.2 % | 94.8 % | 1.3 % | 1.2 % | 11,122 | 0 | 0 | 0 | 0.15 |

**Label-days of implanted animals with no IMU-QC-ok fix** (B2 dynamics all day; 5): SF07 2026-08-30 (4.7 h), SF08 2026-08-30 (4.7 h), SF09 2026-08-30 (4.7 h), SF10 2026-08-30 (4.7 h), SF11 2026-08-30 (4.7 h).
 Animal-days in the scope without any make_imu sample: SF07 2026-08-30, SF08 2026-08-30, SF09 2026-08-30, SF10 2026-08-30, SF11 2026-08-30, SF11 2026-09-08, SF11 2026-09-09, SF11 2026-09-10, SF11 2026-09-11, SF11 2026-09-12, SF12 2026-08-30.

## 5. Reproduction

**(a) IMU seconds vs the failure audit's `imu_seconds`** (50 animal-periods, 1,512,000 seconds; the audit computed each period with ± 10 min of samples, the cache each calendar day with ± 10 min and night periods are joined across midnight): agreement ok ≥ 100.000 %, still ≥ 100.000 %, state ≥ 100.000 %; seconds missing from the cache 0; max |Δ| VeDBA_1s 5e-05 m/s² (max relative 5e-06; the cache stores 6 significant digits), omega_1s 0.0005 °/s, sbf on the audit's ok seconds 5e-07. sbf NaN / value mismatches: 59,037 seconds, 0 of them in an ok second — they sit in QC-failed seconds (e.g. SF10's IMU data gap from 09-06 04:02:08), where the pilot's SBF function reads the 2 s after a data gap when those lie inside the loaded window (the audit's window ended earlier); sbf enters the state only in ok seconds, so no state differs.

**(b) Production V3 vs the V3 run's saved V3** (`D:\Field2026_analysis_out\2026c\wiser_v3_20261003_1425`, float32; 50 animal-periods): fixes missing from production 0; at the 5,566,901 fixes ≥ 10 min inside the audit windows max |Δ| = 0.067 in (p99 ≤ 4e-05 in). Fixes among them with |Δ| > 0.001 in: SF07 day_20260910 37 fixes 08:20:30–08:20:41 (V3 run's first fix 08:20:29); SF08 day_20260910 38 fixes 08:20:30–08:20:37 (V3 run's first fix 08:20:30); SF09 day_20260910 3 fixes 08:20:30–08:20:31 (V3 run's first fix 07:55:44); SF10 day_20260910 1 fixes 08:11:06–08:11:06 (V3 run's first fix 08:03:18); SF12 day_20260910 42 fixes 08:20:30–08:20:40 (V3 run's first fix 08:20:30). They are the first fixes after an all-tag silence (operator round) that reaches into the audit window's start: the V3 run had no fix — or only an isolated one before the gap — in its margin, so its track effectively *starts* at these fixes (a run edge in data terms although minutes inside the window), while production carries the earlier fixes. Measured ≥ 10 min from the audit-window edges **and** ≥ 10 min of fix coverage (inter-fix intervals capped at 5 s) from the V3 run's first / last fix (5,555,044 fixes): max |Δ| = **4.4e-05 in** (float32 storage of the saved track); ZUPT / loco masks agree on 100.000 % / 100.000 % of the ≥ 10-min fixes. Closer to the window edges production differs by design (the V3 run had no IMU seconds in its ± 10-min margins, production runs continuous days): max |Δ| 4.3e-05 in at 5–10 min, 0.00094 in at 1–5 min, 5.8 in within 1 min of an edge. **B2 rebuilt from the full-day caches** (same day stitching, no IMU) vs the saved B2: max |Δ| 0.067 in over every window fix (the same silence-edge fixes), 4.3e-05 in ≥ 10 min from the effective edges — the day stitching and the fix caches reproduce B2 to float32 resolution.

**(c) Full-day fix caches vs the existing caches** (60 files: nights, days and failure-audit periods, all from `3rdcohort_Spike_2026_3_4.sqlite`): rows only in the existing caches 0, only in the full-day caches 0; unequal values in reportid / x / y / anchors_used / anchors_list / n_list / dup_n / the four masks: 0 (of 7,151,362 rows). Window-dependent library columns: `valid` agrees on ≥ 100.0000 % of the rows ≥ 60 s and ≥ 10 rows from a window edge (≥ 99.9991 % overall; its gap flag compares each interval with the window's median interval, so a few rows flip anywhere), `speed_inps_smooth` max |Δ| 5.2e-09 in/s there (floating-point noise of the window-relative time origin; 20 in/s overall: the 7-row rolling median and the 1-s window are truncated at a window's ends). The filter uses neither column.

## 6. How to load

```python
import sys; sys.path.insert(0, r"<repo>/wiser/src")
from default_tracks import load_default_track, list_default_tracks
idx = list_default_tracks("2026c")              # label, date, n_fix, hours, share_V3, share_imu_ok, ...
df = load_default_track("SF09", "2026-09-08")  # one row per fix: t_ms, t_al_ms, x_raw, y_raw, masks, x, y, vx, vy, method, imu_ok, imu_state, zupt, loco_boost
```

A day file holds the fixes with WISER time in [00:00, 24:00) local; concatenating consecutive days gives the continuous track (each day was filtered with ± 10 min on both sides). Masks are flags — the filter used every tracked fix — so an analysis drops `m_handling` / `m_silence` / `m_adc_lane` / `m_off_animal` rows itself. The head-IMU per-second layer (`D:\Field2026_analysis_out\2026c\imu_seconds_cache`) is joined on `floor(t_al_ms / 1000)`.

## 7. Caveats

- SF11's τ*: not measured; median of the measured tau* (SF07 0.2, SF08 0.15, SF09 0.1, SF10 0.2, SF12 0.15) = 0.15 s (plan [op]) — flagged in the index (`tau_assumed`).
- The females' tags are unidentified and absent from the DB copies; after 09-11 19:40 the paddock holds 10 rats, 5 tracked.
- `SF12_tag12376` uses SF12's IMU and τ* (the tag's own lag was never measured).
- Production days include periods never audited (08-30 – 09-02 regime A, rain days, every non-audit hour); the default's validation covers only the audit periods.
- In-place activity: see the boxed caveat above. Positions: unverified WISER frame; no distance below 14 in is resolvable.

## Definitions

Units: inches (WISER frame, unverified origin), seconds; $t^{\rm W}_k$ = WISER time of fix $k$ (ms, field-PC clock); $\mathcal{D} = [d_0, d_1)$ = a field-PC calendar day (local 00:00–24:00); $m$ = 600 s margin.

### Label and validity
$$ \ell(k) = \begin{cases} a & t^{\rm W}_k \in [v^{\rm from}_{s,a}, v^{\rm until}_{s,a}) \text{ for the tag } s \text{ of fix } k \text{ and animal } a \\ \varnothing & \text{otherwise (not tracked)} \end{cases} $$
**Text:** a fix belongs to the animal whose identity-table window for its tag contains its time; a second tag worn at the same time as the animal's longer-valid tag is labelled `<animal>_tag<shortid>`, an unlisted shortid `tag_<shortid>` (window = release → end).

### Aligned time
$$ t^{\rm al}_k = t^{\rm W}_k - \tau^*_a $$
**Text:** the WISER fix time moved onto the IMU clock by the animal's measured WISER-behind-IMU lag $\tau^*_a$ (s; SF11 assumed); IMU per-second values are read at second $\lfloor t^{\rm al}_k / 1000 \rfloor$.

### Day stitching
$$ \hat{\mathbf p}_k = \mathrm{V3}\big(\{ \mathbf z_j : t^{\rm W}_j \in [d_0 - m, d_1 + m) \}\big)_k, \quad k : t^{\rm W}_k \in \mathcal D $$
**Text:** each day is filtered once with 10 min of fixes and IMU seconds on both sides and only the core is written; the selftest shows the stitched days equal one continuous run.

### V3 / B2 (unchanged; full definitions in the V3 report)
Constant-velocity Kalman filter + RTS per axis with $Q_k = q\,\mu_k \begin{pmatrix} \Delta t^3/3 & \Delta t^2/2 \\ \Delta t^2/2 & \Delta t \end{pmatrix}$, $q = 3$ in²/s³, $\mu_k = 10$ if the step's midpoint second is IMU-QC-ok and locomoting else 1; fix noise $R_k = \mathrm{diag}(\sigma_x^2, \sigma_y^2)(A_k)$ from the anchors-used table; pseudo-measurement $0 = v$ with $\sigma_Z = 0.25$ in/s at fixes in eroded still runs; χ² gate 13.8155 then 2 Huber IRLS passes ($k_H = 2.5$). B2 = $\mu_k \equiv 1$, no pseudo-measurement. **Text:** V3 is B2 wherever the IMU is unusable.

### Per-fix method
$$ \mathrm{method}_k = \mathrm{V3} \iff a \text{ has a head IMU} \wedge \mathrm{ok}(\lfloor t^{\rm al}_k/1000 \rfloor) $$
**Text:** which dynamics were in force at the fix; the IMU fallback share of a label-day is $1 - $ its V3 share.

### Coverage hours
$$ H = \frac{1}{3600} \big|\{ \lfloor t^{\rm W}_k / 1000 \rfloor : k \in \mathcal D,\ \ell(k) = \text{label} \}\big| $$
**Text:** hours of the day with at least one tracked fix in the second (h, 0–24).

### Shares
V3 share $= \frac{1}{N}\sum_k \mathbb 1[\mathrm{method}_k = \mathrm{V3}]$; ZUPT share $= \frac{1}{N}\sum_k \mathbb 1[\text{ZUPT at } k]$; loco ×10 share $= \frac{1}{N}\sum_k \mathbb 1[\mu_k = 10]$, $N$ = tracked fixes of the label-day (or label, pooled by fixes).

### Reproduction statistics
Agreement $= \frac{1}{|\mathcal S|}\sum_{s \in \mathcal S} \mathbb 1[x^{\rm cache}_s = x^{\rm audit}_s]$ over the audit period's seconds $\mathcal S$ (missing = disagreement); $\max|\Delta| = \max_k \lVert \hat{\mathbf p}^{\rm prod}_k - \hat{\mathbf p}^{\rm saved}_k \rVert_2$ (in) over the fixes common to both, restricted where stated to $t^{\rm al}_k \in [\mathrm{lo} + 10\,\mathrm{min}, \mathrm{hi} - 10\,\mathrm{min})$ of the audit window; the saved tracks are float32 (≈ 3e-5 in resolution at 500 in). Fix-cache comparison: rows matched on (shortid, t_ms); 'unequal' counts matched rows whose value differs.

