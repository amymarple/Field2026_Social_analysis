# Implementation plan — Direction 3: tiered relocation + within-day temperature/microclimate relocation

**Date:** 2026-07-07
**Scope:** medium/large — reporting change (Stage A) + new analysis (Stage B) on Direction 3.
**Subsystem:** `wiser/`
**Builds on:** [2026-07-02-daytime-sleep-site.md](2026-07-02-daytime-sleep-site.md),
[2026-07-03-wiser-shelter-occupancy-state.md](2026-07-03-wiser-shelter-occupancy-state.md)
**Skill:** follows `.claude/skills/regime-aware-wiser-tracking` (weather acts on BOTH the sensor path
— UWB dropout under rain/wet — and the animal path; a gap ≠ absence; jitter floor ~7 in; unverified
inch frame → ROI-identity claims OK, physical "shade/cooler-spot" claims NOT).

## Governing guardrails (must hold)

- **Jitter floor ~7 in.** No relocation claim below it; tiers are in absolute inches well above it.
- **Weather is a covariate on both paths, never a nuisance to regress out.** Rain/wet attenuates UWB
  → quantify per-window **dropout fraction**; on 6/30 (rain 17:30) a rat "leaving" a shelter may be a
  signal gap, not a move. Flag, don't assume.
- **Unverified frame.** Claims limited to ROI identity (house_1/house_2/refuge/…) and outside-air
  temperature/time-of-day as **proxies**; no physical "moved to shade / cooler side" claim.
- **Observer notes are hypotheses, not labels** (FIELD_OBSERVATIONS circularity warning). "House may
  be too hot" (6/29), rain-bolt-to-shelter (6/30) enter as context annotations only.
- **CV is cautious corroboration only** (2026-07-06 reconciliation): CV visible-inside is a *lower
  bound* on WISER shelter occupancy; the WISER↔CV gap is the wall-edge blind zone, not fog. Never use
  CV to invalidate a WISER rest-site.
- **Language:** "temperature-linked", "consistent with microclimate-driven relocation", "candidate
  thermal rest-site switching" — never "temperature causes".

## Stage A — tiered relocation reporting

Replace the single ">3× jitter (~21 in)" headline. **Tiers (absolute inches + shelter identity):**
- `stable` < 30 in · `marginal` 30–75 · `borderline` 75–100 · `robust` 100–180 ·
  `major_shelter_switch` ≥ 180 in **OR** nearest-shelter identity change (house_1 ↔ house_2, or
  refuge ↔ shelter) with shift > 75 in (an identity switch escalates to `major` regardless).

New utils (testable, in `wiser_analysis_utils.py`):
- `nearest_shelter(sites_df, roi_cfg, shelters=("house_1","house_2"))` → adds `nearest_shelter`,
  `dist_nearest_shelter_in`.
- `relocation_tier(shift_in, switched, *, thresholds)` → tier label.
- `classify_across_day(stab, sites, roi_cfg)` → merges nearest-shelter for `night_prev`/`night`,
  adds `nearest_shelter_prev`, `nearest_shelter`, `shelter_switch`, `relocation_tier`.

Driver `analyze_daytime_sleep_site.py`: enrich `rest_site_stability.csv` with those columns; recolor
S2 bars by tier with 30/100/180 reference lines; rewrite the verdict to the tiered, cautious claim —
> "Daytime rest-site fidelity is heterogeneous: 12386 and 12407 show robust cross-shelter relocation,
> while the other animals are mostly stable or marginal near the jitter scale."

## Stage B — within-day rest-site relocation & temperature regularity

New driver `analyze_daytime_rest_temperature.py`. New utils:
- `rest_bouts(win, *, moving_thr_inps, roi_cfg, bin_s=60, enter_s, exit_s, min_bout_s, buffer_in)` —
  per (night, shortid) segment sustained low-speed bouts via `_hysteresis_state` on the per-bin
  **resting fraction**; per bout: start/end/duration, centroid, `spread_in`, dominant zone
  (`assign_roi` majority), `dist_house_1_in`/`dist_house_2_in`, `near_shelter` flag, **`dropout_frac`**
  (share of bin grid with no fix).
- `day_window(hour)` — 05–09 early / 09–12 late-morning / 12–15 midday-heat / 15–18 afternoon /
  18–21 evening-transition.
- `within_day_sequence(bouts)` — per (night, shortid, window) dominant rest zone by total duration.
- `relocation_events(bouts, *, min_shift_in=100)` — consecutive-bout transitions with centroid shift
  ≥ 100 in **or** zone-identity change (house_1↔house_2, refuge↔shelter); jitter-scale shifts excluded.
- `rest_site_entropy(seq)` — Shannon entropy of rest-zone occupancy per window (convergence proxy).
- Weather: `load_weather_multi` (AWN spans 6/28–7/05) → `temp_c`/`humidity`/`rain_rate_mmhr`/`solar_wm2`
  at each bout start + midpoint (nearest 5-min); alignment unverified (~5 min).

Analyses / questions (report each with a reliability + interpretation tag):
1. morning→midday/afternoon rest-site moves (within_day_sequence + relocation_events).
2. relocation frequency vs temperature/time-of-day.
3. bout distance-to-shelter vs temperature (are hot-hour bouts nearer shelters?).
4. rest-zone entropy per window (does it drop at the 12–15 heat peak = convergence?).
5. shared-shelter count per window vs temp/rain (social vs thermal aggregation).
6. per-animal vs common thermal strategy.
7. **6/30 convergence to house_1** — compare vs prior-day sites AND check per-animal **dropout** at
   the other shelters/hay-wall on the wet day (convergence vs sensor dropout).

Interpretation buckets (pick per finding, never overclaim): stable-individual-habit ·
temperature-linked-relocation · wet-day-convergence · social-aggregation · measurement-limited.

## Outputs

Data run (CSVs + PNGs) → `D:\Field2026_analysis_out\direction3_temperature_relocation_<ts>\`:
`rest_bouts_by_animal_day.csv`, `within_day_rest_site_sequence.csv`, `relocation_events.csv`,
`temperature_aligned_rest_bouts.csv`, `heat_midday_convergence_summary.csv`, revised relocation
summary; per-day timeline plots (rest zone × time + temp/weather overlay), per-animal sequence plots.
Version-controlled report → `wiser/outputs/direction3_temperature_relocation/
direction3_temperature_relocation_report.md` (points at the run dir for figures).

## Verification

- Offline self-test additions (`selftest_daytime_sleep_site.py` or a new selftest): tiers on hand
  shifts; `rest_bouts` merges a jitter-crossing low-speed stay into one bout with correct zone;
  `relocation_events` fires on a house_1→house_2 identity change, not on a jitter-scale wiggle;
  entropy monotonic sanity. PASS/exit-code.
- Real run on the snapshot (`--db …snapshots\1stcohort_2026_2026-07-01.sqlite`); spot-check timelines;
  read-only on the DB + weather CSVs; data to `D:\Field2026_analysis_out`.

## Docs
Change log `change_log/2026-07-07-direction3-temperature-relocation.md` + index rows; update the
Direction-3 rows/section in `ANALYSIS_STATUS.md`; note weather alignment (unverified) in the manifest.
