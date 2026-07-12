# Implementation plan — Direction 3: biological-day sleep model (core rebuild)

**Date:** 2026-07-10
**Status:** planned → implementing
**Supersedes:** the temperature-calibrated `sleep_end` in `analyze_evening_morning_sleep.py` (flagged
provisional 2026-07-09). **Scope chosen: "core first, defer extras."**

## Context / why
Field observation (confirmed) + this project's own phase-locked ~21:00 circadian result establish the rat
**biological day**: a **sleep TRUNK ~05:00 → wake ~18:00** (main daytime sleep) followed by an active
evening→night ~18:00→05:00 that contains a **~midnight NAP which is NOT the trunk**. The old
`sleep_end` searched THROUGH the night and read **past midnight** on hot nights (07-02 ≈02:20) — it
**conflated the midnight nap with the trunk end** and wrongly made emergence temperature-driven when
wake is **circadian-fixed ~18:00**. This rebuild re-cuts the sleep analysis on the biological day and
**retires** the temperature-crossing `sleep_end`.

## Scope (this pass)
IN: define the sleep trunk `[05:00, wake(D))`; DETECT **wake** per day behaviorally (retire `sleep_end`);
**morning site** `[05:00, 10:00)` vs **day site** `[10:00, wake(D))` and the **~10:00 switch**, with
across-day stability. DEFER (follow-up): explicit **nap** detection in the active night; **temperature
modulates the SITE-within-trunk** modeling.

## Data (analysis PC, read-only)
WISER snapshot `…\snapshots\1stcohort_2026_2026-07-09.sqlite` (06-28→07-08, 11 days, 5 rats), baseline
`tag_reports_2026-06-30.sqlite`, weather `AWN-…-20260628-20260709.csv`, ROIs `configs/wiser_rois.json`.
Sova(12409) dropped; Hypnos(12380) auto-cut 07-09 (valid through 07-08). refuge_4 burrow flag reused.

## Reuse (do NOT reinvent — in `wiser_analysis_utils.py` unless noted)
- `nightly_activity_profile(df, moving_thr_inps, bin_s, anchor_hour=12)` — the noon→noon per-sleep-day
  activity-fraction profile; the afternoon rise (bin_hours ≈ clock hour) carries **wake**.
- `window_sleep_site(win_slice, roi_cfg, window_label)` — per-(night,shortid) resting-site centroid +
  nearest_shelter + dominant_roi + in_shelter_frac (used for morning & day sub-windows).
- `nearest_shelter`, `relocation_tier`, `RELOCATION_TIERS`, `rest_mask`, `assign_roi`,
  `select_route_window`, `add_speed`, `add_validity_flags`, `apply_tag_cutoffs`, `_bin_utc_ns`,
  `LOCAL_TZ_OFFSET_HOURS`, `load_weather_multi`, `write_run_manifest`.
- `_window_weather`, `_burrow_flag`, `_spearman` — copy the small helpers from
  `analyze_evening_morning_sleep.py` (or import) for the wake-vs-temperature check.

## New util `wiser_analysis_utils.py`
`sleep_trunk_wake(profile, *, base_lo=12.0, base_hi=15.5, search_from=15.0, margin=0.06,
sustain_bins=3, wake_lo=16.0, wake_hi=21.0) -> per-sleep_day df` — from `nightly_activity_profile`,
per sleep_day: **daytime baseline** = median active_frac over `bin_hours ∈ [base_lo, base_hi)` (deep
mid-afternoon rest); **wake_hour** = first `bin_hours ≥ search_from` starting a run of `sustain_bins`
bins with `active_frac ≥ baseline + margin`, clamped `[wake_lo, wake_hi]`; also `baseline_active`,
`peak_active`, `crossed`. Plain: the trunk ends when afternoon activity first rises off the deep-sleep
baseline — the biological wake — **not** an overnight temperature crossing.

## New driver `scripts/analyze_biological_day_sleep.py`
Load snapshot → speed → validity → cutoffs → drop Sova → `rest_mask` → `assign_roi`; local time.
- **Wake:** `profile = nightly_activity_profile(df, moving_thr)`; `wake = sleep_trunk_wake(profile)`;
  `wake_map[night] = wake_hour`. Retire `sleep_end`.
- **Sites:** morning slice `[05:00,10:00)`, day slice `[10:00, min(wake(D),21))` (site centroid is
  robust to the exact end since `window_sleep_site` keeps only resting fixes); `window_sleep_site` on
  each → `morning_sites`, `day_sites`; `_burrow_flag` each.
- **~10:00 switch:** per (night, shortid) morning→day centroid shift + nearest_shelter change +
  `relocation_tier`; dropout guard per window.
- **Across-day stability:** per rat — morning-site MAD, day-site MAD, modal morning/day shelter, switch
  frequency (fraction of days with a nearest-house change morning→day).
- **Wake vs weather (retire-`sleep_end` check):** per day mean afternoon temp; Spearman(wake, temp) —
  expect ~0 (phase-locked, temperature-independent), which is the evidence that the old temperature
  `sleep_end` was wrong.
- **Figures:** `BD1_wake_vs_temp.png` (wake_hour per day + afternoon temp twin axis → flat wake),
  `BD2_morning_vs_day_site.png` (per-rat morning vs day centroid_x across days + the ~10:00 switch),
  `BD3_trunk_timeline.png` (per day: trunk band 05:00→wake shaded on the activity profile).
- **Outputs** → `D:\Field2026_analysis_out\biological_day_sleep_<ts>\` (CSVs: `trunk_wake_by_day.csv`,
  `morning_sites.csv`, `day_sites.csv`, `morning_to_day_switch.csv`, `site_stability_by_rat.csv`,
  `dropout_by_window.csv`, `run_manifest.json`) + report
  `outputs/direction3_biological_day_sleep/…report.md` (defines every quantity; `/analysis-definitions`).

## Self-test `scripts/selftest_biological_day_sleep.py` (offline)
Synthetic: (a) a profile flat until an injected afternoon rise at bin_hours 18 → `sleep_trunk_wake`
recovers wake≈18 and clamps; a hot "late" day that only rises at 20 → wake≈20 (bounded, NOT past
midnight). (b) a rat with morning site house_1 and day site house_2 → `window_sleep_site` + the switch
logic flag a nearest-house change; a stable rat flags none. Exit-coded PASS/FAIL.

## Docs (AGENTS.md + analysis-definitions)
This plan + index row; `change_log/2026-07-10-biological-day-sleep.md` (after verify) + index row;
ANALYSIS_STATUS Direction-3: add a **biological-day sleep** row and mark the evening/morning `sleep_end`
**RETIRED → superseded by wake** (keep the flag, point to the new driver). Report defines trunk, wake,
morning/day site, switch, MAD, Spearman.

## Verification
- Offline: `python scripts/selftest_biological_day_sleep.py` → PASS.
- Real run 06-28→07-08: wake clusters ~17–19:00 (NOT past midnight), Spearman(wake,temp)≈0; morning vs
  day sites + ~10:00 switch per rat; spot-check BD1/BD2/BD3. Env: anaconda3 python + `KMP_DUPLICATE_LIB_OK`.
- Read-only DB/weather; git-ignored data outputs; unrelated working-tree changes untouched.

## Non-goals (deferred)
Nap detection in the active night; temperature-modulates-SITE modeling; ephys/CV sleep validation;
georeference (relative inch frame only).

## Revision 2026-07-10 (post-review — tighten interpretation before temperature analysis)
1. **Rename** `wake_hour` → **`locomotor_emergence_hour`** and util `sleep_trunk_wake` →
   `locomotor_emergence` everywhere (WISER cannot observe in-shelter waking/stirring; this variable is
   only the onset of sustained locomotion / sleep-site departure). Reframe the ~18:00↔~20:00 gap as a
   **sensor-limited interpretation** — *consistent with* WISER's invisibility to in-nest behavior but
   **not proven** to be entirely caused by it (a genuinely later departure is not excluded). Not "not an
   error."
2. **Fix the overclaim:** with 10:00 used as the morning/day window boundary, the result only shows
   morning-window vs day-window site assignments **differ** on 15/50 rat-days — it does **NOT** establish
   a transition *at* 10:00. Reword report/status/change-log/figures accordingly.
3. **NEW change-point analysis (before temperature-site).** Estimate the within-trunk sleep-site
   transition **independently per rat-day**, no fixed 10:00. New utils: `detect_site_changepoint(g, *,
   bin_s, smooth_bins, min_seg_bins, min_disp_in)` (single max-displacement split on `bin_s`-median
   position; `supported` if displacement ≥ `min_disp_in`; `confidence` = disp/(disp+within-scatter)) and
   `classify_site_location(x, y, roi_cfg)` (house_1 / house_2 / doorway / other via `_rect_membership`).
   Driver: per (night, shortid) trunk resting fixes `[05:00, emergence)` → change-point; localize to a
   clock hour; classify from→to. **Report:** # rat-days with a supported change-point; the change-point
   **time distribution** (and whether it clusters near 10:00 — fraction within ±1 h/±2 h, median/IQR);
   **direction matrix** (house_1/house_2/doorway/other); the min-displacement + confidence criteria;
   **sensitivity to smoothing** (`smooth_bins ∈ {1,3,5}` — supported + time stable?) and **to missing
   data** (per-rat-day trunk dropout; does excluding >25% shift the median?). Figures `CP1` (time
   histogram, 10:00 marked) + `CP2` (per-rat-day time, colored by supported). Self-test adds a planted
   change-point (house_1→house_2) recovered + a stable day not flagged.
   **Only after this validates** → temperature-modulates-day-site. Nap stays deferred.

## Revision 2 — temperature modulates the within-trunk sleep site (Section E)
The change-point validated (44/55 rat-days, high-confidence, robust), so add **Section E** to the same
driver. Reframed by what it showed: relocations are frequent + large + mostly **house_1→house_2** but
**spread across the trunk**, and the absolute house choice is dominated by **individual identity**
(12378/12380 → house_1; 12395/12407 → house_2; 12386 bimodal). So the temperature test must be
**within-rat** (remove identity), not on raw house fractions.
- Per (rat, day): `trunk_frac_house2` = house_2 fixes / (house_1 + house_2) fixes among trunk resting
  fixes; `dominant_trunk_house`. Per day: `midday_peak_temp_c` (max over 12:00–18:00).
- **Primary test:** Spearman(**rat-centered** `trunk_frac_house2` [= value − that rat's mean],
  `midday_peak_temp_c`) across all rat-days → does a rat use house_2 MORE on its hotter days? Also per-rat
  Spearman (in CSV) + a warm/cool median split.
- **Relocation direction vs temp:** of the supported change-points, compare `midday_peak_temp_c` for
  `house_1→house_2` vs `house_2→house_1` moves (does the →house_2 move concentrate on hot days?).
- **Guardrails:** candidate / measurement-limited; inch frame UNVERIFIED so **house_2 is NOT verified
  cooler** (report "temperature-linked", never "moves to the cooler house"); temperature is a covariate
  on BOTH the animal and the UWB-dropout paths (read against trunk dropout); small N (11 days, 5 rats);
  refuge_4 burrow days flagged. Figure `E1` (rat-centered house_2 fraction vs day peak temp).
- Self-test: a synthetic rat whose house_2 fraction rises with temp → positive rat-centered ρ.

## Revision 3 — multi-site state space (Section E binary was misspecified → superseded)
The binary house_2-fraction (and the displacement-only "house_1→house_2" change-point labels) are a
**state-space misspecification** — rats also rest in secondary refuges, near the water tower, at
shelter entrances, and exposed. Rebuild the site analysis over the **full ROI state space**.
1. **States** (canonical): house_1, house_2, refuge_1, refuge_2, refuge_3, refuge_4 (date-gated by
   `valid_until`, flagged burrow in-window), water_1, water_2, doorway (near a shelter core, jitter band),
   exposed (open), unknown. `food_1/food_2 → house_1/house_2` (inside the houses). **Gaps flagged:** no
   dedicated water-tower shelter ROI (near-water = water_1/water_2); the boundary rect is inconsistent
   with the house positions, so a reliable "perimeter/entrance" zone is unavailable (doorway band is the
   entrance proxy).
2. **Explicit distance/uncertainty rule** — new util `classify_site_state(cx, cy, roi_cfg, *, date,
   shelter_buffer_in=15, doorway_buffer_in=24)` on a **segment centroid**: distance to each ROI footprint
   edge; enter a shelter if ≤ `shelter_buffer_in` (absorbs ~7 in jitter, p95 ~15 in); `doorway` if within
   a further `doorway_buffer_in`; else `exposed`; `unknown` if the segment is too dispersed / sparse. Both
   the change-point pre/post segments AND the dwell bins are classified **independently** — never labelled
   by displacement direction.
3. **State-sequence** — new util `trunk_state_dwell_transitions(g, roi_cfg, *, date, bin_s=300,
   min_dwell_bins=3, min_disp_in=24)`: bin the trunk, per-bin centroid → state, collapse runs; returns
   **dwell time by state**, and **relocations** = transitions between two ≥-min-dwell confident-state
   segments with centroid shift ≥ `min_disp_in`. Driver reports the **full transition matrix**,
   **# relocations per rat-day**, **dwell by site**, and **relocation timing** (still no fixed 10:00).
4. **Section E → multi-site temperature.** Per rat-day dwell fractions per state + `midday_peak_temp_c`.
   (a) **any-shelter vs exposed**: rat-centered Spearman(shelter dwell fraction, peak temp) — does heat
   change refuge use at all? (b) **which shelter**: rat-centered Spearman(per-state dwell fraction, peak
   temp) for the main states — does heat shift *which* refuge? Descriptive (multiple comparisons, small N).
5. Ambient temperature is a **coarse covariate** (no site-specific microclimate); a null is phrased
   **"no detectable association under the current measurement and sample size"**, never "temperature does
   not affect sleep-site behavior." Mark the old binary Section E **superseded/exploratory**.
- Figures: `E1` → rat-centered shelter-vs-exposed fraction vs temp; `SS1` → dwell-by-state stacked bars
  per rat + transition-matrix heatmap. Self-test: `classify_site_state` buckets (house/refuge/water/
  doorway/exposed + refuge_4 date-gating) + a planted multi-site relocation recovered.
