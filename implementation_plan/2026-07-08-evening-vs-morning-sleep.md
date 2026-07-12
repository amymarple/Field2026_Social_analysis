# Implementation plan — Direction 3: evening (baseline) vs morning (weather-driven) sleep, analyzed separately

**Date:** 2026-07-08
**Author:** analysis PC
**Status:** planned → implementing
**Depends on:** Direction 3 Stage A/B (`analyze_daytime_sleep_site.py`, `analyze_daytime_rest_temperature.py`),
`wiser_analysis_utils` sleep-site machinery, AWN weather loader.

## Motivation (from the request)

Sleep sites are already quantified (nearest house, centroid, dominant ROI). The current Stage B lumps
**all** daytime rest (05:00–21:00) into one window. But the two rest episodes that bracket the
nocturnal active period have **different drivers** and should be analyzed **separately**:

1. **Evening sleep (~17:00–22:00, "5–10 pm")** — the settle after the daytime heat has passed, before
   nocturnal emergence. It is the **least daytime-influenced** readout of a rat's *baseline* sleep-site
   preference. Its **end** is not a fixed 22:00 — rats emerge to activity **when the evening cools**, so
   the window end is **calibrated per day by temperature** (a common thermal criterion → later end on
   hot days, earlier on cool days).
2. **Morning sleep (~05:00–11:00)** — the bed-down after the active night. Its **site** is expected to be
   **influenced by temperature and (overnight) rain** — a cold/wet return may shift where a rat sleeps.

So: characterize the **evening baseline**, characterize the **morning** site, and test whether the
**morning departs from the evening baseline as a function of temperature/rain**. Weather data
(AWN, 06-28 → 07-05) is the cross-check.

## Data (analysis PC, read-only)

- WISER snapshot `…\snapshots\1stcohort_2026_2026-07-06.sqlite` (daytime coverage **06-28 → 07-05**, 8 days).
- Fixed baseline `tag_reports_2026-06-30.sqlite` (jitter floor + rest cutoff only).
- Weather `AWN-…-20260628-20260705.csv` (+ the two shorter exports) — `temp_c`, `rain_rate_mmhr`, `humidity`.
- ROIs `configs/wiser_rois.json` (`house_1`/`house_2`; `refuge_4` `valid_until` 07-07 already set).

## Governing constraints (WISER skill — honor, don't hand-wave)

- **Sleep = low-speed proxy**, not ephys. **Dropout ≠ absence** — rain attenuates UWB, so a wet morning
  can *fake* a site change; every (animal, day, window) carries a **dropout fraction** and high-dropout
  reads are **lower-confidence**, never "moved".
- **Inch frame UNVERIFIED** — ROI-identity + **relative** displacement only. No "house_2 is cooler", no
  directional claim.
- **Jitter floor ~7 in** — displacement/relocation thresholds reuse `RELOCATION_TIERS` (stable <30 in).
- **`refuge_4` is a burrow entrance 07-03 → 07-07** (not sleep) — flag, never count as a rest site.
- **Weather acts on BOTH paths** (behavior *and* UWB dropout) — language stays **"temperature/weather-linked"**,
  **never "causes"**. Field-log notes are hypotheses, not labels.
- **Sova `12409` dropped**; tag cutoffs applied.

## New utils (`wiser/src/wiser_analysis_utils.py`)

1. `temperature_calibrated_evening_end(wx, nights, *, evening_start=17, peak_lo=12, peak_hi=18,
   floor_h=20.0, ceil_h=24.0, threshold_c=None) -> (per_night_df, threshold_c)`
   - Per night: afternoon peak time/temp (max in [peak_lo, peak_hi)); **T_end = first local time after the
     peak where outside T ≤ θ\***, clamped to `[floor_h, ceil_h]`; `θ\*` = `threshold_c` or the **pooled
     median** of 20:00–22:00 evening temps across nights (documented, single cross-day thermal criterion).
   - Columns: `night, peak_local, peak_temp_c, threshold_c, evening_end_local, evening_end_hour, n_wx`.
2. `window_sleep_site(win_slice, roi_cfg, *, window_label, shelters=DAYTIME_SHELTERS,
   near_shelter_in=48.0) -> per-(night,shortid) df`
   - Generalizes `within_day_sequence` to **one arbitrary clock slice**: resting-fix centroid (median),
     `spread_in`, `dominant_roi`/`dominant_zone_class`, `nearest_shelter` + `dist_nearest_shelter_in`,
     `near_shelter`, `in_shelter_frac`, `n_rest_fix`. Window slice is pre-filtered by the driver.
3. `evening_activity_onset(win, *, moving_thr_inps, onset_start=17, onset_end=24, bin_s=300,
   sustain_bins=2) -> per-night df` (cross-check only)
   - Group median speed per 5-min bin after 17:00; first sustained (`sustain_bins`) rise above the rest
     cutoff = behavioral **emergence time**. Reported next to the thermal `evening_end` to check the
     temperature criterion ≈ real emergence (not used to cut the window → not circular).

## New driver `scripts/analyze_evening_morning_sleep.py`

Load snapshot → `add_speed` → `add_validity_flags(jitter)` → `apply_tag_cutoffs` → drop Sova.
`select_route_window(5, 24)` (whole daylight+evening), attach per-fix local time.
Compute `θ*` + per-night `evening_end` (util 1). Slice:
- **morning** = local `[05:00, 11:00)`; **evening** = local `[17:00, evening_end(D))`.
`rest_mask` on each slice; `window_sleep_site` per slice → `morning_sites`, `evening_sites`.

Per (night, shortid, window) **dropout guard** (present vs expected minute-bins). Merge weather:
- `morning_temp_c` = mean T [05,11); `morning_rain_mmhr` = mean rain [05,11);
  `overnight_rain_mm` = Σ rain·Δt over [D-1 21:00, D 11:00] (antecedent wetness).
- `evening_temp_c` = mean T [17, evening_end).

**Analyses**
- **A. Evening baseline:** per rat, evening `nearest_shelter` + centroid across days; across-day stability
  (`site_shift_in`, `relocation_tier`); this is the reference "home base". Report `evening_end` + activity
  onset per day.
- **B. Morning vs baseline:** per (rat, day): `morning_vs_evening_same_day_in` = |morning − evening(D)|;
  `morning_vs_evening_baseline_in` = |morning − rat's median evening centroid|; `shelter_switch` (morning
  nearest_shelter ≠ evening baseline). Tier each with `relocation_tier`.
- **C. Weather cross-check:** relate morning displacement + shelter-switch to `morning_temp_c` /
  `overnight_rain_mm`; stratify days **warm-dry vs cool-wet** (median split, documented); descriptive +
  Spearman ρ if ≥ 5 usable animal-days (else report the split table only). Same for evening (expect ~flat
  vs temperature — the "less influenced" claim).

**Outputs** → `D:\Field2026_analysis_out\direction3_evening_morning_sleep_<ts>\` : `evening_sites.csv`,
`morning_sites.csv`, `evening_end_by_day.csv`, `morning_vs_evening_baseline.csv`,
`weather_by_day_window.csv`, `dropout_by_animal_day_window.csv`, figures
(`E1_evening_baseline_by_rat.png`, `M1_morning_vs_baseline_vs_weather.png`,
`W1_evening_end_vs_temp.png`), `run_manifest.json`, and the report
`direction3_evening_morning_sleep_report.md` (also copied to `outputs/direction3_evening_morning_sleep/`).

## Self-test `scripts/selftest_evening_morning_sleep.py` (offline, no DB/weather)

Synthetic: (a) a warm-vs-cool day pair where the temperature curve crosses θ\* at a **known later time**
on the warm day → assert `temperature_calibrated_evening_end` recovers ordering + clamps; (b) a rat with a
**fixed evening** site but a **morning** site that flips house on the wet/cold day → assert
`window_sleep_site` + baseline displacement flag it, and a stable rat flags nothing; (c) dropout accounting
matches. Exit-coded PASS/FAIL like the sibling self-tests.

## Docs (AGENTS.md + analysis-definitions)

- This plan (before code) + `implementation_plan/README.md` row.
- `change_log/2026-07-08-evening-morning-sleep.md` (after verify) + `change_log/README.md` row.
- New **Direction 3** row in `ANALYSIS_STATUS.md` (candidate).
- The report runs `/analysis-definitions`: **every** derived quantity (rest proxy, θ\*, `evening_end`,
  morning/overnight rain, sleep-site centroid/nearest_shelter, `spread_in`, `dropout_frac`,
  displacement-from-baseline, relocation tiers, `in_shelter_frac`, activity onset, warm-dry/cool-wet split,
  Spearman ρ) defined as **formula + plain text** with units + interpretation.

## Verification

- Offline: `python scripts/selftest_evening_morning_sleep.py` → PASS.
- Real run on 06-28 → 07-05: prints θ\*, per-day `evening_end` vs activity onset, evening baseline per rat,
  morning-vs-baseline displacement + weather split; spot-check figures.
- Env: `C:\Users\Cornell\anaconda3\python.exe` + `KMP_DUPLICATE_LIB_OK=TRUE`.
- Git surface: new script/utils/selftest/docs only; data outputs to `D:\Field2026_analysis_out` (git-ignored);
  read-only on DB + weather; unrelated working-tree changes untouched.

## Non-goals

- Not ephys sleep validation; not a georeference (relative displacement only); not a causal temperature
  claim; morning window bounds fixed (only the **evening end** is temperature-calibrated, per the request).
