# Change log — circadian / diel REST profile (Direction 3 companion)

**Date:** 2026-07-08
**Type:** new analysis (WISER) — per-hour rest/activity profile.
**Tracker:** [wiser/ANALYSIS_STATUS.md](../wiser/ANALYSIS_STATUS.md)
**Skill:** `.claude/skills/regime-aware-wiser-tracking` (rest = low-speed PROXY, not ephys; a signal
gap is 'unknown', never rest; jitter floor ~7 in; weather + refuge_4 burrow act on BOTH the animal
and the UWB-dropout paths → hence the coverage panel).

## Why

Direction 3 assumes a **05:00–21:00 daytime rest window** but never verified *when* the animals
actually stop moving. This companion produces the diel/circadian **REST fraction per local clock
hour** — the group **mean ± SEM across animals** with each **per-animal trace** overlaid — both to
answer "when do they sleep / stop moving" and to check the daytime-window assumption is data-driven.

## What changed

- **`src/wiser_analysis_utils.py`**: two new functions.
  - `circadian_rest_profile(df, *, rest_thr_inps, ...)` → `(per_tag, group)`. Per (tag, local
    clock-hour) REST fraction over the full 24 h, **pooled over all days**; NaN-safe (matches
    `rest_mask`); a `cover_frac` (observed minutes / n_days·60) so **dropout is never read as rest**.
    `group` = across-tag mean ± SEM (SEM = sample SD/√n_tags).
  - `circadian_rest_by_night(df, *, rest_thr_inps, ..., anchor_hour=0)` → per **(tag, day,
    clock-hour)** rest fraction + `cover_frac` (60-min denominator) — the **day-resolved** version,
    for testing whether the diel rhythm DRIFTS across days. `anchor_hour=0` → calendar date; setting
    it to the daily **activity trough** gives a **BIOLOGICAL-NIGHT** cut so a dusk→dawn active bout
    stays in one unit (no calendar split).
- **`scripts/analyze_circadian_rest.py`** (new driver): full-24 h load (no window selection), rest
  cutoff + jitter from the stationary baseline; **five figures** — C1 pooled (REST 0–1 · ACTIVE
  1−rest auto-scaled · coverage); **C2 per-animal REST small-multiples** (one panel per rat, one line
  per date); **C3 group-by-date REST** (one group-mean line per date + phase + amplitude);
  **C4 per-animal ACTIVITY** and **C5 group ACTIVITY-by-date** — the auto-scaled activity (1−rest)
  views, easiest to read per night; **C6 biological-night–aligned ACTIVITY** — each dusk→dawn night
  as one unit (anchored at the data-driven activity trough), with onset & peak clock-hour per
  biological night. Low-coverage cells (< 30%) masked; group per-date points need ≥ 2 rats; a date's
  **activity-peak (phase)** is reported for ≥ 3 covered hours (so the 06-28 release evening is
  included as a hollow 'pseudo' peak), while **diel amplitude** is filled only for ≥ 16-covered-hour
  dates. CSVs, a report with a full **Definitions** block, and a run manifest. Read-only on the DB.
- **`scripts/selftest_circadian_rest.py`** (new): synthetic rest-by-day / move-by-night fixes →
  asserts daytime rest_frac≈1 (half-rester≈0.5), night≈0, group mean/SEM at a daytime hour,
  cover_frac∈[0,1]≈1 at full sampling, NaN speed → not resting, **and** the day-resolved
  `circadian_rest_by_night` per-date rest/coverage. **PASS**.

## Definitions (also in the report)

- **REST (per fix):** `resting = 1` iff `speed_inps_smooth < θ_rest`, else `0`; NaN → 0.
  `θ_rest = 12.46 in/s` = p99 of the stationary fixed-position tag's smoothed speed
  (`speed_noise_floor`). Below θ_rest the animal is indistinguishable from a stationary tag (jitter).
- **Rest fraction** `rest_frac(a,h) = (# resting fixes)/(# valid fixes)` for rat `a` in local hour
  `h`, pooled over days; unitless ∈ [0,1]; denominator = observed fixes only.
- **Group mean ± SEM** `mean_h = mean_a rest_frac(a,h)`; `SEM_h = SD_a / √n_a` (sample SD; across
  rats, equal weight per rat).
- **Coverage** `cover_frac(a,h) = observed_minutes / (n_days·60)`, capped at 1 — the guard that a low
  value = missing data (weather / refuge_4 burrow at night), **not** stillness.
- **Active fraction** `= 1 − rest_frac` (shown auto-scaled because rest is high everywhere).

## Findings (candidate; 5 rats × 8 full days 06-28→07-05, +07-06 early hours)

- **Clear nocturnal / crepuscular rhythm.** Mean REST fraction **0.92 across 05:00–21:00** vs
  **0.87 at night** — small on the rest axis but a **~2.4× swing in ACTIVE fraction**: locomotor
  activity **peaks sharply at 21:00 (~0.19)**, stays elevated overnight (00:00–04:00 ~0.12–0.14), and
  bottoms midday (07:00 ~0.08). This **corroborates the Direction-3 05:00–21:00 daytime rest window
  as data-driven**, not assumed.
- **Highly synchronized across animals.** The SEM band is very narrow (per-rat rest fractions pooled
  over ~1 M fixes each), widening only at the 21:00 activity peak (12395 highest, 12407 lowest) — the
  5 rats share one clock.
- **Coverage ≥ 0.5 every hour** (≈1.0 almost everywhere) → the profile is not a dropout artifact.

**Key caveat (stated in the report):** `θ_rest` is the jitter *ceiling*, so anything slower than
~1 ft/s (sitting, grooming, slow foraging) counts as "rest" → "rest fraction" **overcounts true
sleep** and compresses the diel swing. This is an **activity-onset rhythm, not sleep depth**; true
sleep needs ephys/CV corroboration. Rest is a proxy; refuge_4 burrow + wet nights raise night dropout
(guarded by coverage); 06-28 is a partial day; no spatial claim (unverified inch frame does not bite).

### Do they change their circadian across days? (per-date; the question this run set out to answer)

- **Phase is STABLE — no drift after the first night.** The group activity-onset peak sits at
  **21:00 on 6 of 7 scored dates** (max circular spread 4 h). The one exception is **06-29** (peak
  01:00) — the **first full day after the ~19:25 evening release**, i.e. first-night settling, not a
  rhythm shift. The dusk activity-onset clock is the robust feature.
- **Amplitude is modestly modulated (not a phase change).** Diel amplitude (peak−trough active
  fraction) ranges **0.089–0.131**; sharpest on **06-29** (novelty / first full night) and **07-04**
  (**July-4th fireworks**, FIELD_OBSERVATIONS Day 7 — an external disturbance), lowest on 07-03 /
  07-05. Candidate disturbance/novelty-linked amplitude modulation (hypotheses, not labels) on top of
  an otherwise fixed rhythm.
- **Per-animal (C2):** each rat's by-date REST lines are tightly stacked, and the **daytime plateau
  (05:00–20:00, ~0.92) is stable across all days** — the diel pattern is individually consistent day
  to day, not a group-averaging artifact. The between-date spread lives in the night hours (deepest
  21:00 dip on 06-29).
- **First-night (06-28) release 'pseudo' peak — now included in the panel.** The evening release
  (~19:25) means 06-28 has only evening coverage (~5 h from ~19:30); its activity peaks at **21:00
  with the highest active fraction of any day (0.26)** — a release-driven novelty burst. It is now
  plotted in the phase panel as a **hollow (partial)** point (amplitude left blank — too little
  coverage to define a diel trough). The settling sequence reads end-to-end: **06-28 release 21:00
  (pseudo) → 06-29 first full night 01:00 → 21:00 locked from 06-30 on.**
- **Bottom line:** over these 9 days the rats do **not** re-phase their circadian rhythm; they keep a
  fixed dusk-onset nocturnal schedule and only modulate how sharply activity concentrates at dusk
  (more on the novel first night and the 07-04 fireworks night).

### Biological-night alignment (C6) — resolves the phase question cleanly

The calendar-date cut splits a single dusk→dawn night across two date labels (an evening onset and
its post-midnight tail fall on different dates) — that split is exactly why 06-29 *looked* like a
01:00 peak. Re-cutting each night as ONE unit, **anchored at the data-driven activity trough
(07:00 EDT, the quietest clock-hour)**, removes the artifact:
- **The activity PEAK is at 21:00 on ALL 8 biological nights, including the release night** (peak
  spread 0 h). The dusk **onset** (half-max) is ~21:00 on every night except **07-03** (onset flagged
  ~16:00 — an earlier afternoon rise on the pre-dawn-fog day; peak still 21:00, so onset is the softer
  measure). **So the dusk-onset phase is fixed from night 1** — the "06-29 → 01:00 shift" was purely
  the calendar split (that overnight activity is the release night's own tail, now inside
  biological-night 06-28).
- **What varies is the overnight DEPTH / lateness, not the phase:** in C6 the **release night (06-28)
  sustains the highest activity latest into the overnight (21:00→~04:00)** while later nights
  concentrate near the 21:00 onset and fall off faster; the largest full-night amplitude is 07-04
  (fireworks). (The half-max `hours_active` count is threshold-sensitive/noisy — read the C6 curves,
  not that number.)
- **Net answer to "is the circadian fixed by the second night?":** essentially it is fixed from the
  **first** biological night — dusk onset ~21:00 is present from release; only how deep/late the
  night's activity runs habituates over the first day or two. **Caveat unchanged:** activity proxy,
  not validated sleep/ephys; n=5, one cohort, one settling event → circadian entrainment vs
  novelty-habituation is not separable here.

## Verification

- `python scripts/selftest_circadian_rest.py` → **PASS** (exit 0, incl. the by-night check).
  `selftest_rest_temperature.py` still **PASS** (utils regression). Real run read-only on
  `1stcohort_2026_2026-07-06.sqlite` (exit 0): 5 rats, days 06-28→07-06, coverage ≈1.0; bio-night
  anchor auto-detected at the 07:00 activity trough; all six figures + phase/amplitude + bio-night
  onset/peak tables spot-checked (peak 21:00 on all 8 biological nights).
- **Outputs:** `D:\Field2026_analysis_out\circadian_rest_<ts>\` — CSVs (`circadian_rest_{per_tag,group}.csv`,
  `circadian_rest_by_night_{per_tag,group}.csv`, `circadian_phase_amplitude_by_date.csv`,
  `circadian_bio_night_{per_tag,group}.csv`, `circadian_bio_night_onset_peak.csv`) + figures
  `C1_circadian_rest.png` / `C2_per_animal_by_day.png` / `C3_group_by_day_drift.png` /
  `C4_per_animal_activity_by_day.png` / `C5_group_activity_by_day.png` /
  `C6_biological_night_activity.png` + manifest; version-controlled report →
  `wiser/outputs/circadian_rest/circadian_rest_report.md`.

## Next
- A lower/second speed threshold (or mean-speed / active-distance) would sharpen "true sleep" vs
  "slow movement"; CV shelter cams / ephys would validate the sleep proxy; per-day (not pooled)
  profiles would test day-to-day rhythm stability (e.g. the hot days vs the wet day).

---

## Update — 2026-07-09: extended to 11 days (06-28 → 07-08)

Re-ran on the newest snapshot `1stcohort_2026_2026-07-09.sqlite` (`DEFAULT_DB` bumped). Window is now
**11 daytime dates / 11 biological nights, 06-28 → 07-08**, 5 rats. **All conclusions hold and
strengthen:**
- **Biological-night peak = 21:00 on ALL 11 nights** (including the 3 new ones 07-06/07/08); onset
  ~21:00 on every night except the same 07-03 fog-day outlier (16:00, peak still 21:00). So the
  **dusk-onset phase is fixed from night 1** over the full 11-night record.
- Pooled REST 0.92 day vs **0.86** night (~**2.5×** active-fraction swing, 21:00 peak / 07:00 trough).
  Rats remain tightly synchronized (narrow SEM).
- Highest full-night amplitude now on 07-04 (fireworks), 07-07 and 07-08; the release night (06-28)
  still sustains activity latest into the overnight.
- Circadian uses **no weather**, so the post-07-05 AWN gap (below) does not affect it.
- **Verification:** `selftest_circadian_rest.py` **PASS**; driver read-only, exit 0; all six figures
  + bio-night onset/peak table refreshed (`D:\Field2026_analysis_out\circadian_rest_20260709_*`).
