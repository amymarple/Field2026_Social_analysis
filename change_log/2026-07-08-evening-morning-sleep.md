# Change log — Direction 3: evening (baseline) vs morning (weather-driven) sleep

**Date:** 2026-07-08
**Type:** analysis (new utils + driver + self-test + report); candidate / measurement-limited.
**Plan:** `implementation_plan/2026-07-08-evening-vs-morning-sleep.md`.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13.5, numpy 2.1.3, pandas 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (daytime **06-28 → 07-08**, 11 days,
5 tags), fixed baseline `tag_reports_2026-06-30.sqlite`, weather `AWN-…-20260628-20260709.csv`
(full window; the earlier 07-05 gap is now filled → **all 11 days thermally calibrated**, θ\*=22.65 °C).

> ⚠️ **2026-07-09 CORRECTION — `sleep_end` is PARTLY WRONG (flagged, refine later).** Field observation
> (confirmed with the PI) + this project's own phase-locked ~21:00 circadian result establish the rat
> **biological day**: a **sleep TRUNK ~05:00→18:00** (wake/emerge **~18:00**) followed by an active
> evening→night that contains a **~midnight NAP which is NOT the trunk**. The temperature-calibrated
> `sleep_end` in this change searches THROUGH the night and reads **past midnight on hot nights** (07-02
> ≈02:20, 06-30 ≈01:20) — that **conflates the midnight nap with the end of the main sleep** and wrongly
> makes emergence temperature-driven when it is **circadian-fixed near ~18:00**. Treat all `sleep_end`
> values (Results §2, the report `sleep_end` table, the `A1`/`W1` markers) as an **artifact pending a
> biological-day rebuild** (sleep-trunk bout + wake detection; naps flagged separately). **Unaffected:**
> the evening-baseline SITE (§1), the morning-vs-baseline comparison (§3–4), and the activity-fraction
> curves — only the `sleep_end` marker/interpretation is wrong. See the plan's "biological day" section.

## What / why

Sleep sites are already quantified, but Stage B pooled all daytime rest (05:00–21:00) into one window.
The two rest episodes bracketing the nocturnal active period have **different drivers**, so this splits
them and analyzes each separately:

- **EVENING sleep** = local `[17:00, sleep_end(day))` — the least-daytime-influenced **baseline**
  sleep-site preference (post-heat, pre-emergence). The nocturnal rat's "day" is one full **sleep
  period**, not a 0–24 h calendar day, so its **end (`sleep_end_hour`) is temperature-calibrated,
  measured as hours-since-midnight, and searched THROUGH the night — it may exceed 24** (past midnight)
  on hot nights instead of saturating at the calendar midnight.
- **MORNING sleep** = local `[05:00, 10:00)`, **before the ~10:00 sleep-site switch** — the bed-down
  after the active night; its **site** is hypothesized to depend on temperature + overnight rain.
  Tested against each rat's evening baseline.

## Headline definitions (formula + text; full set in the report)

Units: WISER **inches**, UNVERIFIED offset frame (ROI-identity + RELATIVE displacement only).

- **Rest proxy** `resting`: smoothed UWB speed `v_s < c`, `c = 12.46` in/s (= p99 of the stationary
  baseline speed). Text: below `c` a tag is indistinguishable from a still rat; a proxy for rest/sleep,
  not ephys-validated.
- **theta\*** (sleep-end criterion) `= median( outside T over 20:00–22:00 across all days ) = 22.85 °C`
  — one cross-day thermal level. **sleep_end_hour(day)** `= first time after the afternoon peak —
  searched THROUGH the night, up to 06:00 next day — with outside T ≤ theta\*`, in **hours since
  midnight** (may exceed 24), clamped `[18, 30]`. Text: a single "cool enough to emerge" temperature; a
  hotter night reaches it later — e.g. 07-02 = **24.92** (≈00:55) — instead of pinning at the calendar
  midnight. `crossed=False` = the air never cooled to theta\* all night (only 06-30, hit the 06:00 cap).
- **Sleep site** (per day, window, rat): `centroid = (median x, median y)` over resting fixes;
  `spread_in = median‖fix − centroid‖`; `nearest_shelter = argmin_s ‖centroid − centre(s)‖` over
  {house_1, house_2}; `in_shelter_frac = mean(roi ∈ {house_1,house_2})`.
- **Move from baseline** `= ‖morning_centroid − baseline_centroid‖`, where a rat's evening
  **baseline_centroid = median of its evening centroids across days**; **shelter_switch_vs_baseline** =
  morning nearest_shelter ≠ baseline nearest_shelter.
- **Relocation tier** (reuse `RELOCATION_TIERS`, inches): stable <30 · marginal 30–75 · borderline
  75–100 · robust 100–180 · major/​switch ≥180 or an identity switch >75. 30 in ≈ 4× the ~7 in jitter
  floor, so "stable" is within measurement noise.
- **dropout_frac** `= 1 − present_bins / expected_bins` over the window's 60-s grid — share of the window
  with no WISER fix; a gap is **unknown**, never "moved"; >0.25 = lower-confidence.
- **Activity fraction** (per-night profile, `nightly_activity_profile`) = per 5-min bin,
  `mean(v_s > c)` over all fixes, on a **noon → next-noon** axis (`bin_hours` = hours since midnight,
  12→36) so overnight emergence is not truncated. **behavioral emergence** (`sleep_emergence_from_profile`)
  = first ≥2-bin run with active fraction ≥ 0.15 from 15:00 through the night — the independent
  cross-check of `sleep_end` (also hours-since-midnight). **overnight_rain_mm** `= Σ rain_rate·Δt` over
  `[prev 21:00, this-day 11:00)` (gaps capped 30 min). **wet** = overnight_rain_mm > 0.2 mm;
  **warm/cool** = median split of morning_temp_c. **Spearman ρ** = Pearson correlation of ranks.

## Results (candidate / measurement-limited)

1. **Evening baseline: 4/5 rats stable, 1 bimodal (11-day update).** 12378/12380 → **house_1**,
   12395/12407 → **house_2** hold their evening centroid to within the 30-in jitter band
   (`centroid_mad_in` 6.5–18.5 in). **12386 is NOT stable — MAD 90 in**: it splits evenings between
   house_1 and house_2, so its single median baseline sits *between* the houses and its
   `morning_vs_evening_baseline_in` (~90 in every day, tier `borderline`) is a **bimodal-baseline
   artifact, not a real relocation** (flagged in the report; a per-mode baseline would be needed). *(The
   8-day "5/5 stable" claim was small-sample — 12386's second mode + 12395's house_2 shift appear with
   more days.)*
2. **`sleep_end` is temperature-calibrated (all 11 days) and no longer saturates.** Searched through the
   night, the sleep-period end reads **past midnight on the hottest nights** — 07-02 = **26.33** (≈02:20),
   06-30 = **25.33** (≈01:20), 07-01 = 22.58 — vs cool nights ending ~18–20:00. All 11 days crossed θ\*
   (the 07-05 weather gap is now filled). The per-night **activity-fraction profile** (`A1`) shows
   emergence directly (behavioral emergence ~21:00 = the circadian peak on cool nights). `peak_active_frac`
   is low every night (**0.12–0.31**) — daytime is overwhelmingly restful. **`A1` now co-plots outside
   temperature (red line) + rain rate (cyan bars)**: the evening cooling curve lines up with emergence, and
   e.g. **07-01's ~19:00 ~45 mm/h downpour coincides with an activity spike** (rats bolting to shelter) —
   6/28's release pseudo-peak at ~19:30 is annotated.
3. **Morning vs baseline (50 rat-days):** tiers {stable 25, major-switch 14, borderline 8, robust 2,
   marginal 1}; **13/50** nearest-house switches. They do **NOT track temperature** (Spearman(move,
   morning_temp) = **−0.02**, n=50). The `borderline` reads are the 12386 bimodal artifact; the warm/dry
   stratum's high median move is driven by it, **not** temperature (drop 12386 → median falls to the jitter
   scale).
4. **Rain is now weakly testable — and shows NO relocation signal.** With the full weather there are **2
   wet-morning days** (07-01 0.30 mm, **07-07 2.37 mm** overnight); Spearman(move, overnight_rain) =
   **−0.20** (n=50) — near-zero / slightly **negative**, i.e. rain does **not** increase the morning move
   from baseline (if anything rats keep *more* site fidelity when wet). Tiny wet-N + the 12386 confound →
   **suggestive, not conclusive**. The morning-vs-evening divergences still read as **individual /
   diurnal** (e.g. 12395/12407 bed in house_1 mornings but house_2 evenings), not weather-locked.

## Guardrails honored (regime-aware-wiser-tracking)

Sleep = low-speed proxy (not ephys); a gap is "unknown" not "moved" (per-window dropout reported;
0 morning animal-days >25%); inch frame UNVERIFIED (house_2 not "cooler", no directional claim); jitter
floor ~7 in (tiers ≥ it); `refuge_4` = burrow entrance 07-03→07-07 (flagged; **0** burrow-dominant sleep
reads); weather acts on BOTH the animal and UWB-dropout paths → **temperature/weather-linked, never
causal**; Sova `12409` dropped. *(The 07-01 midday weather gap in the earlier 07-05 export is now filled
by the full 06-28→07-09 AWN export — 07-01 peak 36.2 °C, sleep_end 22.58.)*

## Changes

- **`src/wiser_analysis_utils.py`** — new `temperature_calibrated_sleep_end` (searches through the night,
  sleep_end hours-since-midnight, may exceed 24), `window_sleep_site`, `nightly_activity_profile`
  (per-night active-fraction on a noon→noon axis), `sleep_emergence_from_profile` (behavioral emergence
  cross-check). *(Reframed from the earlier `temperature_calibrated_evening_end`/`evening_activity_onset`,
  which clamped at the 24:00 midnight and so "always saturated".)*
- **`scripts/analyze_evening_morning_sleep.py`** (driver; morning window tightened to 05:00–10:00, before
  the ~10:00 site switch; **`A1` figure now co-plots outside temperature (red line) + rain rate (cyan
  bars)** per night; report rain/verdict text made data-driven for wet-day detection) +
  **`scripts/selftest_evening_morning_sleep.py`** (offline, PASS: sleep-end ordering + **past-midnight** +
  clamp, site + relocation flag, activity-profile + emergence recovery, rain integral, Spearman).
- Data → `D:\Field2026_analysis_out\direction3_evening_morning_sleep_<ts>\` (CSVs incl. `activity_fraction_by_night.csv`
  + `figures/{E1,M1,W1,A1}.png` + `run_manifest.json`); report → `outputs/direction3_evening_morning_sleep/…_report.md`.

## Verification

- `python scripts/selftest_evening_morning_sleep.py` → **PASS** (all checks, incl. past-midnight sleep_end
  and activity-profile emergence).
- Real run on **06-28 → 07-08 (11 days, 07-09 snapshot + full 06-28→07-09 AWN)** → θ\*=22.65 °C; **all 11
  days crossed** — per-day `sleep_end` (h since midnight) {06-28/29 20.58, 06-30 25.33, 07-01 22.58,
  07-02 **26.33** (≈02:20), 07-03 21.25, 07-04 20.58, 07-05 18.08, 07-06 18.0, 07-07 20.25, 07-08 21.33};
  evening baseline **4/5 stable, 12386 bimodal (MAD 90)**; **13/50** morning switches; temp ρ=−0.02;
  **2 wet mornings (07-01, 07-07), rain ρ=−0.20 → suggestive not conclusive**. `A1` co-plotted
  temperature+rain spot-checked (07-01 rain-spike↔activity coincidence visible; emergence marks on all 11
  nights; 6/28 release pseudo-peak annotated).
- Read-only on DB + weather; git-ignored data outputs; unrelated working-tree changes untouched.

## Status / next

`ANALYSIS_STATUS.md` Direction 3 gains an **evening-vs-morning** row (candidate). The evening baseline is
a **promotable** stable-home-site result; the **morning weather** question stays **open/UNTESTABLE** until
a wet-morning day enters the snapshot — re-run then to test rain (positive ρ vs overnight_rain or a
larger cool/wet median move would be the candidate weather-linked morning relocation).
