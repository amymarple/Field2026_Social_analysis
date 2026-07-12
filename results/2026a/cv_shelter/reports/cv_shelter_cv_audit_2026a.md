# CV Measurement-Context Audit — 2026-07-04 shelter output (CH05 / CH06)

- **Auditor:** cv-measurement-auditor
- **Mode:** METADATA / SUMMARY (no `validation_2026-07-04.csv` with `gt_*` labels exists → detector /
  count **error metrics are NOT computable** for this date; distributions + safety only)
- **Generated (UTC):** 2026-07-07T05:37:45Z
- **Git commit:** 9226f0910399c5806c13c1c7ffa41398f0adc4ff (matches the sidecar `git_commit`)
- **Targets:**
  - `cv/outputs/CH05_sleep_2026-07-04.csv` (291 bins × 300 s)
  - `cv/outputs/CH06_sleep_2026-07-04.csv` (294 bins × 300 s)
  - `cv/outputs/shelter_sleep_2026-07-04.measurement_context.json`
    (per-run manifest, `mc_run_id = mc_ca25f85759ff`)
- **Detector:** rat_feasibility-6 (sha256_16 `03b05d2e07d5e1ec`, val mAP50 0.876) · conf 0.3 · batch 1 ·
  imgsz null · device 0 · every_sec 300 · n_burst 3

## Verdict

**INTERPRETABLE AS A MEASUREMENT, WITH REGIME STRATIFICATION MANDATORY — AND WITH A HARD CAVEAT ON
THE OVERNIGHT SEVERITY QUESTION.** Provenance is complete, per-row covariates are 100% populated, the
schema is pure (24 cols, appended-only, no mutated metric column), and **all four hard safety rules
held** on this heavy-degraded, single-optical-regime day. The numbers may be read as a
**regime-stratified, lower-bound `visible_count` / coarse-activity proxy** — never as pooled
occupancy, never as a true headcount, and never as native fog severity in the overnight window.

**Load-bearing measurement caveat (answers the reason for this audit):** the entire overnight
00:00–09:30 window is **weather-FORCED to `degraded`** (`weather_logged=True`, 116 bins/camera). The
`view_quality_inside=degraded` value there does **NOT** report native/auto-detected fog severity — it
is a forced floor from `field_conditions.yaml`. **The current outputs CANNOT support a post-film-vs-
prior-regime overnight fog-SEVERITY comparison.** No column in this CSV exposes the native, continuous
severity signal for the forced bins; a native-view-quality rerun is required first (see §Severity and
§Smallest next action).

## Provenance & purity

- **Sidecar present** as the per-run manifest (not per-CSV) and internally consistent: `mc_run_id`,
  detector weights version + fingerprint + params (conf/imgsz/batch/device), sampling, per-camera
  block, zones/calibration/config/field_layout fingerprints, and the cm coordinate frame (origin pole
  A0). `git_commit` in the sidecar == repo HEAD.
- **Schema pure.** Both CSVs carry the current 24-column schema: 15 metric columns in canonical order
  + 9 covariates appended in order, **no extra / mutated columns** (header == expected exactly). Row
  counts (291 / 294) as declared. Annotation is append-only per the manifest `caveats`.
- **Per-row covariate completeness: 100%.** `camera_model`, `shelter_id`, `mc_run_id`,
  `view_quality_inside`, `glass_regime`, `glass_uncertain_layers`, `glass_time_precision`,
  `glass_confounded`, `n_inside_confidence`, `usable_for_headline_summary`,
  `usable_for_coarse_activity`, `weather_logged` are non-null on every row (291/291, 294/294). Every
  row `mc_run_id == mc_ca25f85759ff` == manifest.
- **Single optical regime, as expected.** `glass_regime = bare_seated_post_film` on **all** 291/294
  rows; `glass_uncertain_layers = damaged_original_antifog_coating` on **all** rows. 07-04 is entirely
  post-film — no glass change_point falls inside the day, so no intra-day optical-regime boundary
  (R2's "do not pool across a boundary" is satisfied by construction here; the cross-DAY / cross-regime
  boundary lives at 07-03 11:00, outside this file).
- `camera_model = RLC-520A` both; `shelter_id = left` (CH05) / `right` (CH06).

## Regime stratification (NEVER pooled)

Two axes matter on 07-04: **view_quality** (clear/degraded) and **weather_logged** (forced vs native),
plus **time-of-day** (forced overnight vs clear daytime). Glass regime is constant, so it is not a
splitting axis today — but the whole day sits in the `damaged_original_antifog_coating`-suspected
regime and must not be pooled with any other day's regime.

### CH05 (shelter_id = left) — time span 00:00 → 23:55 local

| Stratum | n | clear | degraded | det-empty (n_det_inside==0) | state (empty / low / high) |
|---|---|---|---|---|---|
| view=degraded, weather_logged=True (FORCED, overnight) | 116 | — | 116 | 84.5% | 98 / 18 / 0 |
| view=degraded, weather_logged=False (NATIVE) | 14 | — | 14 | ~ | 13 / 1 / 0 |
| view=clear, weather_logged=False | 161 | 161 | — | 61.5% | 99 / 58 / 4 |
| **whole day (DO NOT report pooled)** | 291 | 55.3% | 44.7% | 73.2% | 210 / 77 / 4 |

- Time-of-day: overnight 00:00–09:30 = **115/115 degraded** (forced), empty 97 / low 18.
  Daytime 09:30–18 = 103/104 clear, empty 76 / low 27 / high 1. Evening 18–24 = 58 clear / 14 degraded.
- `n_detected_inside`: max 4, mean 0.40. Huddle-proxy (`n_det_inside≥4`) frames: 2.

### CH06 (shelter_id = right) — `inside` geometry is a FALLBACK (no CH06_zones.json)

| Stratum | n | clear | degraded | det-empty (n_det_inside==0) | state (empty / low / high) |
|---|---|---|---|---|---|
| view=degraded, weather_logged=True (FORCED, overnight) | 116 | — | 116 | 84.7% (deg) | 98 / 18 / 0 |
| view=degraded, weather_logged=False (NATIVE) | 41 | — | 41 | ~ | 31 / 10 / 0 |
| view=clear, weather_logged=False | 137 | 137 | — | 48.2% | 64 / 65 / 8 |
| **whole day (DO NOT report pooled)** | 294 | 46.6% | 53.4% | 67.7% | 193 / 93 / 8 |

- Time-of-day: overnight 00:00–09:30 = **117/117 degraded** (forced). Daytime 09:30–18 = 97 clear / 7
  degraded. Evening 18–24 = 40 clear / 33 degraded (native evening degradation onset).
- `n_detected_inside`: max 6, mean 0.64. Huddle-proxy (`n_det_inside≥4`) frames: 10.

**Cross-camera caveat (measurement-context, NOT behavior):** CH06 has **no `CH06_zones.json`**
(`zones.CH06 = null` in the manifest), so its `inside` zone fell back to the calibration quad at
runtime (R6). CH06's higher degraded fraction (53% vs 45%) and different detector-empty profile vs CH05
are therefore partly a **different `inside` geometry**, not a CH05-vs-CH06 animal difference. Do not
compare the two cameras' occupancy as behavior. Note CH05 degraded% 44.7 / CH06 53.4 differs slightly
from the audit-request summary (CH05 45 / CH06 53) at the rounding level — reconciled here to the CSV.

## Safety-invariant result (heavy-degraded day) — ALL PASS

| Rule | CH05 | CH06 |
|---|---|---|
| degraded/unusable bins scored `occupied_high_motion` (must be 0) | **0** | **0** |
| `unusable` bins → state != `indeterminate` (must be 0) | 0 (no unusable bins) | 0 (no unusable bins) |
| `occupied_high_motion` only on `clear` view | **4/4 clear** | **8/8 clear** |
| `weather_logged=True` bins still labelled `clear` (must be 0) | 0 (all 116 forced `degraded`) | 0 (all 116 forced `degraded`) |

- **The 4 CH05 / 8 CH06 OHM bins are ALL clear-view, weather_logged=False** — confirmed against the
  audit-request figures (4 / 8). No OHM bin is under degraded/forced glass. Safety core intact.
- No `unusable` tier was reached on either camera, so the `unusable → indeterminate` path was not
  exercised (vacuously satisfied). Zero `indeterminate` bins.
- **Two CH06 OHM bins have `n_detected_inside=0` while `inside_motion_score` cleared threshold**
  (11:10:01 motion 0.514, 12:50:01 motion 2.651; both clear view, `n_inside_estimated=0`). This is a
  **motion-only occupied_high_motion** — per `shelter_sleep.py::_fuse`, `present_inside` = (`n_inside>0`
  OR `motion>present_motion_floor`), so a clear bin with motion ≥ `motion_thresh` but no localized box
  yields `(0, high, occupied_high_motion)`. It is internally consistent and safety-compliant, but the
  **count evidence (`n_inside_estimated=0`) and the state label disagree** — do not read these two bins
  as a confirmed active-rat headcount; they are a motion-signal event with no detection box (candidate
  activity, or residual clear-view motion artifact). Flagged as a measurement-quality note, not a
  safety violation.

## Severity question — WHY the forced tier cannot answer it, and which columns can

The reason 07-04 was queued for audit is the coating-damage hypothesis
(`uncertain_layers: [damaged_original_antifog_coating]`): does the post-film glass fog **worse** than
pre-intervention `bare` glass? 07-04 holds the overnight test window. **But that window is exactly the
weather-forced region:**

- All 116 overnight (00:00–09:30) bins/camera have `weather_logged=True` and `view_quality_inside=degraded`.
- `field_conditions.yaml` forces any matching bin to **≥ degraded** (`view_quality.py::in_degraded_window`),
  so `degraded` here is a **logged floor**, not a measured severity. The native auto-detected tier for
  those bins is overwritten before it reaches the CSV (`vqi = "degraded"` in `analyze_channel` when
  `weather_logged` fires).
- **Therefore `view_quality_inside` in the forced window reports NEITHER native tier NOR continuous
  severity.** Comparing this forced `degraded` against another regime's overnight `degraded` compares
  two floors, not two fog intensities. **Do not infer severity from the forced tier.**

**Which columns expose native / continuous severity vs only the final categorical tier:**

- `view_quality_inside` (final tier): **categorical, and OVERWRITTEN to `degraded` when
  `weather_logged=True`** — unusable for severity in the forced window.
- `inside_motion_score`: a **motion** score (glass-noise-resistant), range 0.0–0.386 (CH05) / 0.0–2.651
  (CH06). It is **NOT a fog-severity signal** — do not repurpose it as one.
- **No continuous view-quality / fog-severity column is written to this CSV.** The per-bin severity that
  `view_quality.py` computes internally (the underlying score behind the clear/degraded/unusable tier)
  is **NOT surfaced** as a column, and is in any case moot in the forced window because the tier is
  forced regardless of the native computation.

**Consequence for the next task:** a post-film-vs-prior fog-SEVERITY comparison needs the **native
auto-detected** view-quality signal for the overnight bins, i.e. the value the pipeline would assign
**without** the weather force. The available lever is a **`--conditions ''` (or empty/omitted
conditions) rerun** of `shelter_sleep.py` for these dates, which suppresses the `weather_logged` force
so `view_quality_inside` carries the native tier (ideally alongside the continuous score if a severity
column is added). Compare like-for-like overnight windows (post-film night vs an original-`bare` night)
on that native signal — never on the forced tier here.

## Classification of each major finding

1. **View-quality split (clear vs degraded) + the forced overnight degraded block** — **measurement
   artifact (sensor path).** Property of glass + logged weather, not animals. The overnight "empty /
   no-motion" reads are fog-obscured (forced degraded), NOT true absence/stillness (R1).
2. **`occupied_low_motion` bins under `degraded` view (rest proxy)** — **invalid / lower-bound only.**
   Under degraded glass low-motion/empty can be fog-obscured; not a validated rest signal.
3. **`n_detected_inside` / `n_inside_estimated` occupancy** — **lower-bound `visible_count` only.**
   Wall-edge blind zone (manifest caveat + repo memory) + degraded/forced bins depress it further. A
   visible "empty"/low count is a floor, never a headcount (R3, R5).
4. **`occupied_high_motion` (4 CH05 / 8 CH06, all clear view)** — **likely behavioral (candidate),** the
   only bins where a motion read is admissible; unvalidated (no GT this date). The 2 CH06 `n_det=0` OHM
   bins are **mixed/ambiguous** (motion-only, no detection box).
5. **Post-film overnight fog severity vs prior regime** — **NOT COMPUTABLE from this file** (forced
   tier). Measurement-context observation to test with a native-view-quality rerun; do not classify as
   behavioral or artifact yet.
6. **CH06 higher degraded% / detector-empty vs CH05** — **measurement artifact (geometry/config),** the
   CH06 no-zones-file fallback confounds the cross-camera comparison (R6).

## Context→debugging map — rules fired

| Rule | Trigger (true on this run) | Classification | Allowed next action attached |
|---|---|---|---|
| R1 high_fog_risk_or_logged_fog | 116 `weather_logged=True` bins/camera (overnight fog window) | measurement_artifact | caveat/exclude fogged bins from headline; do not read as absence/stillness |
| R2 glass_treatment_change | all bins in `bare_seated_post_film`; `uncertain_layers` set | measurement_artifact | treat span as a DISTINCT camera; stratify by regime; do not pool with other-day `bare` |
| R3 wall_edge_blind_zone | visible inside count in use (near-nadir cams) | lower_bound | report as visible_count; dispatch wiser-measurement-auditor |
| R5 huddle_undercount | `n_det_inside≥4` on 2 (CH05) / 10 (CH06) bins | lower_bound | report count as lower bound; label huddle frames (validation mode needed for the bias number) |
| R6 zone_polygon_misalignment | CH06 has no CH06_zones.json (`zones.CH06=null`, calib-quad fallback) | measurement_artifact | flag CH06 inside-zone as uncalibrated; draw CH06_zones.json |
| R9 timestamp_or_binning_issue | benign sub-second / next-day-midnight edge bins (NOT catastrophic) | measurement_artifact (note only) | reconcile OSD-vs-filename before window mapping; no blocker |

- **R7 (detector version / sidecar) — does NOT block:** single detector rat_feasibility-6, sidecar
  present and fingerprint-consistent. No cross-version comparison is being made here.
- **R9 (interpretation_blocker) — does NOT fire as a blocker.** Expected vs actual bin counts do NOT
  diverge catastrophically. CH05: 291 rows over ~288 5-min slots; the 3 extras are ~1 s / ~299 s gaps
  from Reolink filename second-drift (`_00-00-01` boundaries), not collapsed/duplicated bins (0 exact
  duplicate timestamps). CH06: 294 rows with **1 exact-duplicate timestamp** and one bin spilling to
  `2026-07-05 00:00:00` (24th file `23-00-00_to_00-00-01` edge). These are benign edge artifacts, noted
  as minor R9-class provenance items — they do NOT change any stratum materially and do NOT block
  interpretation. Stratification proceeds.
- **R4 (heat exterior refuge) — not computable** (composite trigger; ambient temp/solar not joined,
  no house-temp sensor, no gate). Report-semantics only.

## Provenance gaps / caveats

- **No ground truth for 07-04** → error/accuracy/confusion metrics are not computable (metadata mode).
  Do not invent detector-error or count-error numbers for this date.
- **Native view-quality / fog-severity signal is not in the CSV.** The forced overnight tier
  overwrites the native tier, and no continuous severity column is written (see §Severity). This is the
  gap that blocks the post-film-vs-prior severity comparison.
- **CH06 `inside` zone is a fallback** (no `CH06_zones.json`; `zones.CH06 = null`). CH06 inside geometry
  is not a labelled zone — treat CH06 counts as extra-uncertain and do not compare cross-camera as
  behavior (metadata_gap `ch06_zones` / `zone_change_manifest`).
- **No `fog_risk_level` column** in the sleep CSV (metadata_gap `fog_risk_in_sleep_csv`) — only
  `weather_logged` is available; R1 fog-risk stratification is join-by-hand.
- **No per-bin wall-edge flag** (metadata_gap `wall_edge_flag`) — only `n_inside_confidence` proxies the
  coverage limit; the blind-zone lower bound is asserted, not measured per-bin.
- **No huddle flag** (metadata_gap `huddle_flag`) — `n_detected_inside≥4` proxies density; the huddle
  undercount bias requires ground truth (validation mode).
- **~1 h Reolink OSD-vs-filename offset** is unresolved machine-readably (metadata_gap `osd_clock_map`);
  annotation used filename-derived `t`. Bins near the 09:30 fog-window edge carry residual attribution
  uncertainty; the CH06 next-day-midnight spill bin is the visible symptom.
- **Two CH06 motion-only OHM bins** (`n_det=0`, clear view) — count and state disagree; not a headcount.

## Smallest next action

**None to the pipeline logic** — the 07-04 output is measurement-valid, safety-clean, and needs no
relabel/retrain/threshold change (errors cannot be stratified without GT, and no safety violation
exists). The smallest useful steps, in priority order:

1. **To enable the coating-damage / fog-severity comparison (the blocking gap):** re-run
   `shelter_sleep.py` for the relevant overnight windows with the weather force **suppressed**
   (`--conditions ''` / empty conditions) so `view_quality_inside` carries the **native** tier for the
   forced bins; ideally also surface the continuous view-quality score as a column. Then compare
   **post-film overnight (07-04 00:00–09:30)** native severity against an **original-`bare` night's**
   native severity — like-for-like, never the forced tier. Until that rerun exists, **state plainly
   that the severity comparison is not yet computable.**
2. **Draw `CH06_zones.json`** (`place_zones.py`) to remove the calibration-quad fallback and make the
   CH05-vs-CH06 comparison a camera comparison rather than a geometry comparison.
3. **(Optional, needs GT):** run `validate_shelter.py` on a small stratified sample of 07-04 clear-view
   post-film bins to get the first ground truth in this optical regime.

Do NOT change thresholds or retrain on 07-04.

## Sibling handoff

Recommend dispatching **`wiser-measurement-auditor`** as the fog-immune cross-check. The overnight
00:00–09:30 forced-degraded block (116 bins/camera) plus the wall-edge blind zone make "is a rat really
inside under degraded glass" unanswerable from CV alone — WISER (UWB, fog-immune) is the reference for
shelter occupancy when the glass is degraded. It is also the right cross-check for the 2 CH06
motion-only OHM bins and any suspected overnight huddle undercount. Bridge script:
`wiser/scripts/analyze_sleep_site_cv_crossval.py`. Run it both ways — CV catches
huddles WISER cannot resolve, so never assume the two agree.
