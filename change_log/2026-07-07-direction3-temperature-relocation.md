# Change log — Direction 3: tiered relocation (Stage A) + within-day temperature relocation (Stage B)

**Date:** 2026-07-07
**Commit:** uncommitted at time of writing.
**Plan:** [implementation_plan/2026-07-07-direction3-temperature-relocation.md](../implementation_plan/2026-07-07-direction3-temperature-relocation.md)
**Tracker:** [wiser/ANALYSIS_STATUS.md](../wiser/ANALYSIS_STATUS.md)
**Skill:** `.claude/skills/regime-aware-wiser-tracking` (weather acts on BOTH the animal path and the
UWB dropout path; a gap ≠ absence; jitter floor ~7 in; inch frame UNVERIFIED).

## Why

The prior Direction-3 run headlined "8/10 animal-day pairs relocated (>3× jitter ~21 in)", which
overstated it — several shifts were 22–28 in, i.e. jitter-scale. And it only measured across-day
primary-site change, not whether rest-site choice follows a **within-day** (temperature-linked)
pattern.

## What changed

### Stage A — tiered across-day relocation (no more "8/10 relocated")
- **`src/wiser_analysis_utils.py`**: `nearest_shelter`, `relocation_tier` (stable <30 · marginal
  30–75 · borderline 75–100 · robust 100–180 · major_shelter_switch ≥180 in **or** a house_1↔house_2
  identity switch), `classify_across_day` (enriches the stability table).
- **`scripts/analyze_daytime_sleep_site.py`**: `rest_site_stability.csv` gains
  `nearest_shelter_prev/nearest_shelter/shelter_switch/relocation_tier`; S2 figure recoloured by
  tier with 30/100/180 reference lines; verdict rewritten to the cautious claim.

### Stage B — within-day rest-site relocation & temperature
- **`src/wiser_analysis_utils.py`**: `day_window`, `zone_class`, `rest_bouts` (gap-aware low-speed
  rest bouts + dominant zone + dist-to-shelter + `dropout_frac`), `within_day_sequence` (per
  (night, shortid, window) dominant rest **site** with centroid + nearest shelter), `relocation_events`
  (between-window centroid shift ≥100 in / shelter-identity / zone change; jitter-scale excluded).
- **`scripts/analyze_daytime_rest_temperature.py`** (new driver): rest bouts, window sequence,
  relocation events, per-window rest-zone entropy + shelter-sharing (convergence proxy), AWN weather
  aligned to bouts/windows, **per-animal-day dropout guard**, per-day timelines + convergence figures,
  and a version-controlled report.
- **`scripts/selftest_rest_temperature.py`** (new): tiers, `nearest_shelter`,
  `within_day_sequence`+`relocation_events` (switcher → 1 shelter_switch, stable → 0), `rest_bouts`.

## Findings (3 days, 5 tags, exploratory / candidate)

> **Extended 2026-07-08 to 8 days (06-28 → 07-05).** The 3-day findings below are the original
> record; see the **"Update — 2026-07-08"** section at the end for the extended-day results, which
> **correct the Stage A headline** (switching is common to all 5 animals, heterogeneous by *rate*,
> not "only 2 animals") and **strengthen** the Stage B heat-peak-dispersal signature (now 6/7 days).

**Stage A (across-day):** rest-site fidelity is **heterogeneous** — **12386 and 12407** do a
`major_shelter_switch` (house_1↔house_2, ~185–212 in) on both day-pairs; **12378, 12380, 12395** are
`stable` (all shifts < 30 in). The prior "8/10 relocated" was 4 jitter-scale pairs mislabeled; the
tightened count is **4 major switches (2 animals), 6 stable**.

**Stage B (within-day):**
- **Regular within-day sequence on the hot dry day (6/29, ~30 °C):** cool early morning (~17 °C) →
  rats OUT (refuge/open, 0 in shelter); late morning (~26 °C) → **all 5 converge to house_1**; at the
  **12:00–15:00 heat peak (~29–30 °C) rest sites DISPERSE** — 12386 & 12407 relocate to **house_2**
  and stay there through the afternoon. This house_1→house_2 midday move is a **candidate
  temperature-linked relocation** (NOT proof; the inch frame is unverified so house_2 is *not*
  verified cooler; "prefer above metal/in shade, house may be too hot" is an observer hypothesis).
- **Wet/hot day (6/30, ~34 °C + rain ~17:30):** rats START in house_1 (warm 22 °C morning, unlike the
  cool 6/29 morning), then **all leave shelters (open field) at the midday heat peak**; afternoon is
  the most dispersed window (rain confound).
- **Dropout guard:** 6/29 and 6/30 daytime dropout ≈ **0.0** (full WISER coverage) — so the wet-day
  reads are **real, not a UWB dropout artifact** (6/28 is 0.90 dropout = evening-only partial day, not
  a sensor problem).
- **Convergence vs dispersal:** peak *shelter* convergence is **late-morning**, not midday — the heat
  peak is associated with **dispersal** (to house_2 on 6/29, to open on 6/30), not shelter-seeking.

**Interpretation:** candidate / **measurement-limited**. WISER supports site-level within-day
movement and cross-shelter switching by 2 animals with hot-hour timing; thermal vs social vs
individual-habit cannot be separated without shelter temperature or more days. Language kept to
"temperature-linked". CV corroborates only visible shelter-resident periods (lower bound;
[2026-07-06 reconciliation](2026-07-06-cv-wiser-reconciliation-reframe.md)).

## Verification

- `python scripts/selftest_rest_temperature.py` → **PASS**; `scripts/selftest_cv_crossval.py` still
  **PASS** (regression). Real run on the snapshot `1stcohort_2026_2026-07-01.sqlite` + AWN weather:
  15 rest bouts, 17 within-day relocation events; figures T1 (timeline) / T2 (convergence)
  spot-checked. Read-only on the DB + weather CSVs.
- **Outputs:** data (CSVs + figures) → `D:\Field2026_analysis_out\direction3_temperature_relocation_<ts>\`;
  version-controlled report → `wiser/outputs/direction3_temperature_relocation/
  direction3_temperature_relocation_report.md`.

## Known limitations / next steps
- 3 days only (**now 8 — see the Update below**); temperature is an **outside-air proxy** (no shelter
  thermistor) and a covariate on both the animal and the UWB paths. Georeference confirmation would let
  sites be placed physically and test a real shade/cool-side hypothesis. A shelter-temperature logger or
  ephys would move "sleep" and "microclimate preference" from proxy to validated.

---

## Update — 2026-07-08: extended to 8 rest days (06-28 → 07-05)

**Why.** The 3-day window (06-28 → 06-30) was the binding limitation. The analysis PC now holds
snapshots through `1stcohort_2026_2026-07-06.sqlite`, so both drivers were re-run over the full
**8 daytime-rest days (06-28 → 07-05)**, 5 tags. Weather = AWN through 07-05 (1951 rows).

**Code changes (both drivers generalize to N days; no logic change to the metrics):**
- `analyze_daytime_rest_temperature.py`: `DEFAULT_DB` → the 07-06 snapshot; `DAY_CONTEXT` extended
  (07-01…07-05, incl. 07-04 fireworks + the refuge_4 burrow window); a new **refuge_4 BURROW caveat**
  block (`_burrow_reads`) that flags any dominant-`refuge_4` rest window inside 07-03 → 07-07 as
  burrow-entrance behaviour + a UWB-dropout lower bound, **not sleep**; stale "3 days" text made
  dynamic; the hardcoded 6/29 closing note replaced with a **data-driven cross-day summary**;
  Direct-answers made data-driven.
- `analyze_daytime_sleep_site.py`: verdict rewritten to report the **per-animal switch RATE** (robust
  when many/all animals switch) instead of the now-false "these switch / the others are stable" split.

**Stage A — corrected headline (switching is common, heterogeneous by RATE).** Over 8 days,
tiers = **{stable: 20, major_shelter_switch: 15}** across 35 consecutive-day transitions. **All 5
animals** switch house_1↔house_2 at least once; the real signal is the *rate*:
`12407 5/7 · 12395 4/7 · 12378 2/7 · 12380 2/7 · 12386 2/7`. 12407 switches nearly every day (settles
house_2 late); 12386 switches only the first two days then locks to house_1. **This corrects the
3-day "only 12386 & 12407 relocate" read as a small-sample artifact** — day-to-day house alternation
is the norm, not a two-animal quirk. Switches are genuine ~185–212 in house-to-house moves (≈ the
5 ft house spacing), far above the ~7 in jitter floor. The primary daytime site is always
house_1/house_2/open — **`refuge_4` never dominates a full day**, so the burrow window does **not**
contaminate the across-day switches.

**Stage B — strengthened + a burrow caveat.**
- **Heat-peak dispersal now repeats:** on **6/7 days** with both windows present, FEWER animals are
  in a shelter at the 12:00–15:00 heat peak than in late morning (06-29, 06-30, 07-01, 07-02, 07-03,
  07-04) — the late-morning shelter aggregation **thins/disperses at the heat peak** (to house_2
  and/or open field), not the reverse. This makes the **candidate temperature-linked** signature a
  repeated pattern rather than a single-day observation. 57 within-day relocation events over 8 days.
- **refuge_4 burrow caveat (NEW):** 9 animal-windows show `refuge_4` as the dominant midday/afternoon
  rest ROI **exactly in the burrow window** (07-03/12378; 07-04/12378×2, 12386, 12395×2; 07-05/12378,
  12386×2). These are **burrow-entrance behaviour + UWB-dropout lower bound, never sleep** — flagged,
  not counted as a rest site or a relocation. house_1/house_2 reads unaffected. (See
  [2026-07-07 shelter-4 burrow](2026-07-07-shelter4-burrow-removed.md).)
- **Dropout guard:** daytime dropout ≈ **0.0** on every full day (06-28 is 0.90 = evening-only partial
  day, expected) — the reads, including the wet days, are real, not UWB artifacts.

**Covariate flags carried (not exclusions):** 07-01 rain ~19:45 (post-window); 07-03 pre-dawn fog;
**07-04 July-4th fireworks ~21:00** (rest-window edge — minimal daytime impact but noted); 07-05
weather not logged; the refuge_4 burrow regime (07-03 → 07-07) as above.

**Interpretation unchanged in kind, stronger in support:** candidate / measurement-limited; thermal
vs social vs individual-habit still not separable without a shelter thermistor / ephys; inch frame
still unverified (house_2 not confirmed cooler). Language stays "temperature-**linked**".

**Verification.** `selftest_rest_temperature.py` → **PASS** after the edits. Both drivers re-run
read-only on the 07-06 snapshot (exit 0). Outputs → `D:\Field2026_analysis_out\daytime_sleep_site_20260708_1221\`
and `…\direction3_temperature_relocation_20260708_1221\`; version-controlled report refreshed at
`wiser/outputs/direction3_temperature_relocation/`.

---

## Update — 2026-07-09: extended to 11 days (06-28 → 07-08)

Re-ran on the newest snapshot `1stcohort_2026_2026-07-09.sqlite` (`DEFAULT_DB` bumped). Window now
**11 daytime dates, 06-28 → 07-08**, 5 rats.
- **Stage A holds:** tiers **{stable 31, major_switch 19}** over 50 consecutive-day transitions; all 5
  still switch house_1↔house_2, heterogeneous by **rate** — **12395 5/10 · 12407 5/10 · 12378/12380/12386
  3/10**. Same conclusion as the 8-day run (12395/12407 the frequent switchers). refuge_4 still never a
  full-day primary site → no burrow contamination.
- **Stage B:** 56 rest bouts, 66 within-day relocation events; the **midday heat-peak shelter-thinning**
  signature now holds on **9/10 days** with both windows present (all but 07-05) — strengthened by the
  added days.
- **Weather refreshed to cover the full window** (2026-07-09): the AWN export
  `AWN-…-20260628-20260709.csv` was dropped in, so temperature now aligns for **all 11 days**
  (weather rows 1951 → 3305; 07-06/07/08 midday ~24–25 °C — milder than the 30–35 °C 06-29→07-04 peak
  days). The `DEFAULT_WEATHER` in the driver was switched to **auto-discover** all `AWN-*.csv`
  (`load_weather_multi` dedups on `datetime_utc`), so future exports are picked up without a code edit.
  The temperature-linked claim now spans the whole record, not just 06-29→07-05.
- **Burrow window widened** to include **07-07 up to the 13:00 removal** (`valid_until` drops `refuge_4`
  after that); the burrow caveat now flags pre-removal `refuge_4` rest reads through 07-06 (11 windows).
- **Verification:** `selftest_rest_temperature.py` **PASS**; drivers read-only, exit 0
  (`D:\Field2026_analysis_out\{daytime_sleep_site,direction3_temperature_relocation}_20260709_*`).
