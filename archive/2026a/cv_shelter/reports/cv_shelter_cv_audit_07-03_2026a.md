# CV Measurement-Context Audit — 2026-07-03 shelter output (CH05 / CH06)

- **Auditor:** cv-measurement-auditor
- **Mode:** METADATA / SUMMARY (no `validation_2026-07-03.csv` with `gt_*` labels exists → detector/count **error metrics are NOT computable** for this date; distributions only)
- **Generated (UTC):** 2026-07-07T05:15:30Z
- **Git commit:** 9226f0910399c5806c13c1c7ffa41398f0adc4ff (matches the sidecar `git_commit`)
- **Targets:**
  - `cv/outputs/CH05_sleep_2026-07-03.csv` (284 bins × 300 s)
  - `cv/outputs/CH06_sleep_2026-07-03.csv` (285 bins × 300 s)
  - `cv/outputs/shelter_sleep_2026-07-03.measurement_context.json` (per-run manifest, `mc_run_id = mc_93ff608f4035`)
- **Detector:** rat_feasibility-6 (sha256_16 `03b05d2e07d5e1ec`, val mAP50 0.876) · conf 0.3 · batch 1 · imgsz null · device 0 · every_sec 300 · n_burst 3

## Verdict

**INTERPRETABLE AS A MEASUREMENT, WITH REGIME STRATIFICATION MANDATORY.** Provenance is complete,
per-row covariates are fully populated, the schema is pure (appended-only), and **all four hard
safety rules held on this heavy-fog, dual-regime day**. The numbers may be read as a
**regime-stratified, lower-bound `visible_count` / rest proxy** — never as pooled occupancy and
never as a true headcount. No behavioral or cross-regime claim may be made from this file alone.

## Provenance & purity

- **Sidecar present** as the per-run manifest (not per-CSV) and internally consistent: `mc_run_id`,
  detector weights version + fingerprint + params, zones/calibration/config fingerprints, and the cm
  coordinate frame (origin pole A0) are all recorded. `git_commit` in the sidecar == repo HEAD.
- **Schema pure.** Both CSVs carry the current 24-column schema: the 15 metric columns in canonical
  order + the 9 covariates appended in order, with **no extra or mutated columns**. Row counts
  (284 / 285) are as declared. Annotation is append-only per the manifest `caveats`. No metric column
  was touched.
- **Per-row covariate completeness: 100%.** `camera_model`, `shelter_id`, `mc_run_id`,
  `view_quality_inside`, `glass_regime`, `n_inside_confidence`, `usable_for_headline_summary`,
  `usable_for_coarse_activity`, `weather_logged`, `glass_time_precision`, `glass_confounded` are
  non-null on every row (284/284, 285/285). Every row `mc_run_id == mc_93ff608f4035` == manifest.
- **`glass_uncertain_layers` behaves correctly**: blank in the `antifog_film` span, then
  `damaged_original_antifog_coating` on all 153 `bare_seated_post_film` bins per camera — flipping
  exactly at the 11:00 boundary (last antifog bin 10:55, first post-film bin 11:00).
- `camera_model = RLC-520A` both; `shelter_id = left` (CH05) / `right` (CH06).

## Regime stratification (NEVER pooled)

Time span each camera: 2026-07-03 00:02 → 23:55 local. Two optical regimes split at 11:00 local.

### CH05 (shelter_id = left)

| Stratum | n | clear | degraded | unusable | det_empty (n_inside==0) | weather_logged |
|---|---|---|---|---|---|---|
| glass_regime = antifog_film (00:02–10:55) | 131 | 45.0% | 55.0% (weather 19.1% / native 35.9%) | 0% | 27.5% | 19.1% |
| glass_regime = bare_seated_post_film (11:00→) | 153 | 83.0% | 17.0% (weather 17.0% / native 0.0%) | 0% | 47.1% | 17.0% |
| **whole day (do not report pooled)** | 284 | 65.5% | 34.5% | 0% | — | 18.0% |

- State by regime — antifog: `occupied_low_motion` 97, `empty` 33, `occupied_high_motion` 1;
  post-film: `occupied_low_motion` 81, `empty` 70, `occupied_high_motion` 2.
- Median `n_detected_inside` = 1 in both spans (mean 1.66 antifog → 1.10 post-film).

### CH06 (shelter_id = right) — `inside` geometry is a FALLBACK (no CH06_zones.json)

| Stratum | n | clear | degraded | unusable | det_empty (n_inside==0) | weather_logged |
|---|---|---|---|---|---|---|
| glass_regime = antifog_film (00:02–10:55) | 132 | 38.6% | 61.4% (weather 18.9% / native 42.4%) | 0% | 42.4% | 18.9% |
| glass_regime = bare_seated_post_film (11:00→) | 153 | 71.9% | 28.1% (weather 17.0% / native 11.1%) | 0% | 60.8% | 17.0% |
| **whole day (do not report pooled)** | 285 | 56.5% | 43.5% | 0% | — | 17.9% |

- State by regime — antifog: `occupied_low_motion` 81, `empty` 51;
  post-film: `empty` 86, `occupied_low_motion` 64, `occupied_high_motion` 3.
- Median `n_detected_inside` = 1 (antifog) → 0 (post-film); mean 0.88 → 0.66.

**Cross-camera caveat (measurement-context, NOT behavior):** CH06 has **no `CH06_zones.json`**
(`zones.CH06 = null` in the manifest), so its `inside` zone fell back to the calibration quad at
runtime. CH06's higher degraded fraction and higher detector-empty rate vs CH05 are therefore
partly a **different `inside` geometry**, not a CH05-vs-CH06 animal difference. Do not compare the
two cameras' occupancy as behavior.

## Safety-invariant result (heavy-fog day) — ALL PASS

| Rule | CH05 | CH06 |
|---|---|---|
| degraded/unusable bins scored `occupied_high_motion` (must be 0) | **0** | **0** |
| `unusable` bins → state != `indeterminate` (must be 0) | 0 (no unusable bins) | 0 (no unusable bins) |
| `occupied_high_motion` only on `clear` view | 3/3 clear | 3/3 clear |
| `weather_logged` bins still labelled `clear` (must be 0) | 0 (all 51 forced `degraded`) | 0 (all 51 forced `degraded`) |

The two logged fog windows (pre-dawn 04:00–06:00 and evening 21:50→end-of-day) were force-applied:
51 `weather_logged=True` bins per camera, all `degraded`, spanning 04:00 → 23:55. No unusable tier
was reached on either camera this day, so the `unusable → indeterminate` path was not exercised
(vacuously satisfied). The only `occupied_high_motion` bins (3 per camera) are all clear-view.

## Classification of each major finding

1. **View-quality / degraded-fraction split across the two regimes** — **measurement artifact
   (sensor path).** These are properties of the glass + weather, not the animals.
2. **`occupied_low_motion` bins under `degraded` view (rest proxy)** — **invalid / lower-bound only.**
   Under degraded glass "low motion / empty" can be fog-obscured, not true stillness/absence. These
   are NOT a validated rest signal (per skill: low motion under degraded glass is not rest).
3. **`n_detected_inside` / `n_inside_estimated` occupancy** — **lower-bound `visible_count` only.**
   The wall-edge blind zone (per manifest caveat + repo memory) hides rats from both human and
   detector; degraded/fog bins depress it further. A visible "empty"/low count is a floor.
4. **Post-film detector-empty rate higher than antifog span** — **mixed / ambiguous, CANDIDATE.**
   See below.
5. **`occupied_high_motion` (3 bins/camera, clear view)** — **likely behavioral (candidate),** the
   only bins on this day where a motion read is admissible; still unvalidated (no GT this date).

## Coating-damage hypothesis — the evidence, kept as CANDIDATE (observer "looks like", not proven)

Per `glass_treatments.yaml`, `bare_seated_post_film` (11:00→) carries
`uncertain_layers: [damaged_original_antifog_coating]` and must **not** be treated as recovery to the
pre-tape `bare` baseline. The two testable signals this day:

- **Native (non-weather) degraded fraction** — CH05: antifog 35.9% → post-film **0.0%**;
  CH06: antifog 42.4% → post-film 11.1%. On 07-03 itself the post-film daytime view is, if anything,
  **clearer** than the antifog span (consistent with "the film made the view worse than bare glass").
- **Detector-empty rate** — CH05: 27.5% → **47.1%**; CH06: 42.4% → **60.8%**. Higher n_inside==0 in
  the post-film span, but this coincides with the daytime/evening hours (rats plausibly out) and the
  onset of the 21:50 overnight fog — an **animal-path / weather confound**, not isolatable here.

**Interpretation (candidate only):** 07-03 daytime does NOT yet show post-film glass fogging worse
than the film span — the observer's coating-damage read hinges on the **overnight 21:50 → 07-04 09:30**
window, which mostly falls on the **07-04** output, not this file. The coating-damage hypothesis is
therefore a **measurement-context observation to test later** (compare post-film overnight fog
severity vs an original-`bare` night), not a proven optical change. Do not pool `bare_seated_post_film`
with the original `bare` regime on the strength of this day.

## Provenance gaps / caveats

- **No ground truth for 07-03** → error/accuracy/confusion metrics are not computable (metadata mode).
- **CH06 `inside` zone is a fallback** (no `CH06_zones.json`); the manifest records `zones.CH06 = null`.
  Documented, but CH06 inside geometry is not a labelled zone — treat CH06 counts as extra-uncertain.
- **Regime-boundary timing** is keyed to local wall-clock 11:00 with the ~1 h Reolink OSD-vs-filename
  offset unresolved; annotation used filename-derived `t`, so bins within ~1 h of 11:00 carry residual
  regime-assignment uncertainty (a handful of bins, `time_precision: exact` for the observer's read).
- **The overnight fog + coating-damage test data live mostly on 07-04**, not this file.

## Smallest next action

**None to the pipeline** — the 07-03 output is measurement-valid and needs no relabel/retrain/threshold
change (errors cannot even be stratified without GT, and no safety violation exists). The smallest
useful next step is a **metadata/regime-timeline follow-up, not a code change**:

> Run `validate_shelter.py` on a small stratified sample of 07-03 **clear-view, post-film** bins
> (e.g. `--date 2026-07-03 --n ~40`, weighted to `bare_seated_post_film`) to get the first ground
> truth in this new optical regime; and when the 07-04 output is audited, compare **post-film
> overnight fog severity vs an original-`bare` night** to test (not assume) the coating-damage
> hypothesis. Do NOT change thresholds or retrain on 07-03.

## Sibling handoff

Recommend dispatching **`wiser-measurement-auditor`** as the fog-immune cross-check: the 07-03
degraded/fog bins (55%/61% antifog, plus the overnight window) and the wall-edge blind zone make
"is a rat really inside under degraded glass" unanswerable from CV alone. WISER (UWB, fog-immune) is
the reference for shelter occupancy when the glass is degraded; bridge script
`wiser/scripts/analyze_sleep_site_cv_crossval.py`. Run it both ways — CV catches
huddles WISER cannot resolve, so never assume the two agree.
