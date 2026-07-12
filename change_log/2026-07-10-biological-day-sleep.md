# Change log — Direction 3: biological-day sleep model (core rebuild); `sleep_end` RETIRED

**Date:** 2026-07-10
**Type:** analysis (new util + driver + self-test + report). Candidate / measurement-limited.
**Plan:** `implementation_plan/2026-07-10-biological-day-sleep.md`. **Scope: core first, defer extras.**
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13.5, np 2.1.3, pd 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (06-28→07-08, 11 days, 5 rats),
baseline `tag_reports_2026-06-30.sqlite`, weather `AWN-…-20260628-20260709.csv`, ROIs `wiser_rois.json`.

## What / why
Re-cuts the daytime sleep analysis on the rat **biological day** (field-confirmed + phase-locked ~21:00
circadian result): a **sleep TRUNK ~05:00 → wake** + an active night containing a **~midnight NAP (not
trunk)**. This **RETIRES** the temperature-crossing `sleep_end` (in `analyze_evening_morning_sleep.py`,
flagged provisional 2026-07-09), which searched THROUGH the night, ran **past midnight** on hot days
(07-02 ≈02:20), and so conflated the midnight nap with the end of the main sleep.

*(Post-review revision, same day: **renamed** off "wake"; **corrected** the ~10:00 over-claim; **added**
an independent within-trunk change-point analysis. Interpretation of the trunk boundary is now stated
as **sensor-limited**, not "not an error".)*

## Definitions (formula + plain text)
- **Sleep trunk** = the main daytime rest bout, local `[05:00, locomotor_emergence(day))`.
- **`locomotor_emergence_hour(day)`** — onset of sustained locomotion / **sleep-site departure** =
  first afternoon 5-min bin (`≥15:00`) with activity `≥ baseline_active + max(0.03, 0.20·(dusk_peak −
  baseline))`, sustained ≥3 bins, clamped `[16:00, 21:00]`. Util `wiser_analysis_utils.locomotor_emergence`
  on `nightly_activity_profile`. **Sensor-limited:** WISER only sees movement above the ~7 in jitter
  floor and CANNOT observe in-shelter waking/stirring, so this is the site-departure time, not an
  in-nest wake.
- **Morning-window site** `[05:00, 10:00)` and **day-window site** `[10:00, emergence)` — per (day, rat)
  resting-fix centroid + `nearest_shelter` (`window_sleep_site`). **These fixed windows do NOT locate a
  transition time.**
- **Within-trunk change-point** (`detect_site_changepoint`) = split of the trunk (5-min median-position
  series, 3-bin smoothed) maximizing pre/post segment-median displacement; **supported** if displacement
  ≥ 100 in with ≥3 bins each side; `confidence = disp/(disp+within-scatter)`. **from/to location** via
  `classify_site_location` = house_1 / house_2 / **doorway** (≤36 in band of a house core) / **other**.
- **centroid_mad_in** = median radial deviation of a rat's per-day centroid from its own median.
  **Spearman ρ** = rank correlation.

## Results (candidate)
1. **`sleep_end` retired — the trunk boundary is circadian-clustered, NOT temperature-driven.**
   `locomotor_emergence_hour` clusters at **20.8 h** (range 16.0–21.0; 07-03's 16:0 = fog-day afternoon
   blip); **Spearman(emergence, afternoon temp) = −0.02** (n=11) → flat across warm/hot days. Direct
   evidence the old thermal `sleep_end` (past midnight, 07-02 ≈02:20) was an artifact.
2. **Sensor-limited interpretation (NOT "not an error"):** ~20:00 is the WISER *locomotor* emergence
   (site departure); it LAGS the field-observed ~18:00 in-nest wake. This is **consistent with** WISER's
   invisibility to in-nest stirring (below the jitter floor) but is **not proven** to be entirely that
   (a genuinely later departure is not excluded). Measuring the true ~18:00 arousal needs ephys /
   interior CV (CH07/CH08).
3. **The "~10:00 switch" is NOT supported — CORRECTED.** The fixed morning/day windows only show the two
   windows' site assignments **differ on 15/50 rat-days** (10:00 was the imposed boundary, so this cannot
   locate a transition time). The **independent change-point** (no fixed 10:00) instead finds
   within-trunk relocation is **common and large but SPREAD across the trunk, not at 10:00**:
   **44/55 rat-days** have a supported change-point (high-confidence: median `confidence` **0.96**, median
   displacement **203 in** ≈ house_1↔house_2 separation — clean full-shelter moves), with change-point
   **times median 13.5 h, IQR [6.8, 18.2]; only 11% within ±1 h of 10:00** (16% within ±2 h). `CP1` shows
   loose peaks at ~06:00 (trunk settling), ~13:30, ~20:00 — **10:00 is a low bin.** Direction: most common
   house_1→house_2 (11), else heterogeneous (other↔house, house↔doorway). Robust to smoothing (36/44
   stable across `smooth_bins ∈ {1,3,5}`) and to the >25%-dropout filter (median 13.4 vs 13.5 h).
4. **Across-day site stability:** morning-window very stable for 12378/12380/12386 (`centroid_mad_in`
   ~4 in) and bimodal for 12395/12407 (~95 in); day-window 12378/12380→house_1, 12395/12407→house_2,
   12386 bimodal.
5. ⚠️ **SUPERSEDED 2026-07-11 — see the multi-site revision below.** *(Original: a **binary** house_2-fraction
   test found within-rat Spearman = −0.20 → "no temperature effect". But the binary state space was
   **misspecified** — it cannot represent refuges / near-water / doorway / exposed rest, so it could not rule
   out temperature-dependent movement into non-house sites. Replaced by the multi-site analysis.)*

## Changes
- **`src/wiser_analysis_utils.py`** — new `locomotor_emergence` (renamed from `sleep_trunk_wake`; column
  `locomotor_emergence_hour`), `detect_site_changepoint` (independent within-trunk single change-point),
  `classify_site_location` (house/doorway/other via `_rect_membership`).
- **`scripts/analyze_biological_day_sleep.py`** (rewritten: rename, non-circular morning/day framing,
  change-point Section D + smoothing/dropout sensitivity, **within-rat temperature Section E**
  [`_rat_centered_temp_corr`, `_window_temp_peak`], `CP1/CP2/E1` figures) +
  **`scripts/selftest_biological_day_sleep.py`** (offline PASS: emergence + clamps, window-site difference,
  change-point recovery/direction + stable-day rejection + location buckets, within-rat temperature ρ).
- Outputs → `D:\Field2026_analysis_out\biological_day_sleep_<ts>\` (CSVs incl. `within_trunk_changepoints`,
  `changepoint_smoothing_sensitivity`, `changepoint_direction_matrix`, `trunk_site_vs_temperature`,
  `trunk_house2_temp_corr_by_rat`) + figures `BD1_emergence_vs_temp` / `BD2_morning_vs_day_site` /
  `BD3_emergence_timeline` / `CP1_changepoint_time_hist` / `CP2_changepoint_per_ratday` /
  `E1_trunk_house2_vs_temp`; report → `outputs/direction3_biological_day_sleep/…report.md`.
- **`analyze_evening_morning_sleep.py` `sleep_end` remains RETIRED** (superseded by
  `locomotor_emergence_hour`). ANALYSIS_STATUS updated.

## Verification
- `python scripts/selftest_biological_day_sleep.py` → **PASS** (emergence + no-past-midnight clamp,
  window-site difference, change-point recovery/direction + stable-day rejection + location buckets,
  within-rat temperature correlation).
- Real run 06-28→07-08: emergence ~20.8 h (all ≤21:00, none past midnight), ρ(emergence,temp)=−0.02;
  44/55 supported change-points (median conf 0.96, disp 203 in), **times spread (median 13.5 h, 11%
  within ±1 h of 10:00) → ~10:00 switch NOT supported**; **within-rat temperature ρ=−0.20 (n=55) → no
  house-choice temperature effect**; figures spot-checked. Read-only DB/weather.

## Revision 2026-07-11 — MULTI-SITE state space (fixes a state-space misspecification)
**Why:** the binary house_1/house_2 outcome (Section E) and the displacement-only "house_1→house_2"
relocation labels were a **state-space misspecification** — rats also rest in secondary refuges, near the
water tower, at shelter entrances (doorway), and exposed. A large positional displacement does **not**
establish a house_1↔house_2 move unless pre/post coordinates are **independently** mapped to the full ROI set.

**Changes (utils + driver + self-test):** new utils `classify_site_state` (full state space —
house_1/2, refuge_1/2/3, refuge_4 [date-gated burrow], water_1/2, doorway [near-shelter band],
exposed, unknown; food→house; explicit distance rule with a 15 in jitter buffer) and
`trunk_state_dwell_transitions` (bin→state sequence → dwell-by-site + relocations between ≥15-min
confident-state segments). Section D now labels change-point pre/post via `classify_site_state` +
adds the state-sequence (**transition matrix, dwell-by-site, relocations/rat-day, timing**). Section E
rebuilt **multi-site**: within-rat Spearman of any-shelter and per-state dwell fractions vs midday peak
temp. Removed the superseded binary `classify_site_location`. New figures `SS1` (dwell + transition
matrix) + `E1` (any-shelter vs temp); CSVs `trunk_state_dwell`, `trunk_relocations`,
`state_transition_matrix`, `relocations_per_ratday`, `dwell_by_site_summary`, `site_dwell_vs_temperature`,
`per_state_temp_corr`. Self-test PASS (state buckets + refuge_4 date-gating + a planted 3-state path).

**Results (candidate; supersede the binary Result 5).** ⚠️ **The three bullets below were CORRECTED by the
2026-07-11 reconciliation (next section) and are kept verbatim only as history:** the dwell values here are
**conditional-on-appearance** (not a composition), "**~46% involve non-house**" is wrong (it is 68% of 170 /
51% of the 110 interpretable), and "**shift out of the enclosed houses**" over-unified (house_1 ρ=+0.17 rises).
- **Sleep sites are genuinely multi-site.** Mean trunk dwell: house_1 0.52, house_2 0.40, then **refuge_1,
  water_2, doorway (0.05 each), exposed (0.02)** + refuge_4 (0.14 — but that's the 07-03→07-07 BURROW, not
  sleep). The binary framing hid all the non-house rest.
- **Relocations are frequent and multi-site:** **mean 3.1 / rat-day** (median 3, range 0–8; 170 total),
  and the transition matrix shows **~46% involve non-house states** (house↔refuge, house↔doorway, house↔
  water, exposed) — **NOT** all house_1↔house_2. `refuge_4`-involving rows are burrow-window artifacts
  (discounted). Timing still spread (median 13.4 h), not at 10:00.
- **A candidate temperature signal the binary test MISSED.** Within-rat Spearman(any-shelter dwell frac,
  midday peak temp) = **−0.44** (n=55) → on hotter days rats spend **less** time fully enclosed; per-state,
  **doorway ρ=+0.58**, water_2 +0.38 (↑ with heat), exposed −0.31 — i.e. a shift **out of the enclosed
  houses toward the doorway / near-water**, a plausible thermoregulation pattern. **Candidate only:** n=11
  days, uncorrected multiple comparisons, **ambient (not shelter) temperature**, doorway/exposed are
  jitter-adjacent; house_2/refuges **not verified cooler** (inch frame). Phrased as *no confirmed
  association*, and the earlier "temperature does not affect sleep-site behavior" is **retracted** — the
  binary test simply couldn't see it.

## Reconciliation + human-readable summary (2026-07-11, later same day)
A reporting-repair pass **separated the two conflated site analyses** and re-derived every number from the
`..._1515` run CSVs. Artifacts now in `outputs/direction3_biological_day_sleep/`:
- **`direction3_biological_day_sleep_canonical_results.md` / `.json`** — the **single source of truth**,
  generated from the run CSVs by `gen_canonical_json.py` (copied alongside). Authority order: **code + CSVs
  → canonical → technical report → scientific summary**; the summary **never overrides** the technical record.
- **`..._report.md`** — the technical report, **regenerated** by the fixed `_build_report` over the same
  CSVs (no DB re-read). It keeps the **single-largest change-point (A1: 100-in threshold; 44/55; median
  13.5 h; 11% within ±1 h of 10:00)** and the **multi-site state-sequence relocations (A2: 36-in threshold,
  ≥15-min segments; 170; median 13.4 h; 8%)** as SEPARATE analyses; reports dwell **unconditionally** (sums
  to 1) beside the clearly-labelled conditional means; quantifies non-house involvement; reports emergence
  with its censored/clamp days; softens emergence to "evening-clustered, no detectable temperature
  association" (not "circadian-fixed"); renames the separation score off "confidence"; and adds a two-level
  evidence-status block.
- **`..._scientific_summary.md`** — regenerated: retitled off "free-ranging" → "Daytime Low-Movement and
  Rest-Site Use in Rats Living in an Outdoor Field Enclosure"; 3 findings; ~1,400 words; 3 figures
  (`fig1_emergence`, `fig2_changepoint_timing`, `fig3_dwell_composition`); temperature as a labelled
  candidate box; nap noted as **not analyzed here**.

**Errors corrected in this pass (historical wording above kept as provenance):**
- **Threshold conflation.** The state-sequence relocation threshold is **36 in** (driver override of the
  24-in function default), NOT the 100-in change-point threshold; the report definition text previously said 24 in.
- **Timing conflation.** The single change-point (**13.5 h / 11%**) and the full relocation set
  (**13.4 h / 8%**) are distinct; the first scientific summary had substituted 13.4 h / 8% into the
  change-point paragraph.
- **Dwell reported conditionally.** The conditional-on-appearance dwell means (house_1 0.522, house_2 0.400,
  refuge_4 0.135 …) sum to **1.40** and are not a composition. The **unconditional** composition is house_1
  0.512, house_2 0.334, refuge_4 0.054, doorway 0.043, refuge_1 0.020, exposed 0.017, tunnel 0.010,
  water_2 0.009, refuge_2/3 ~0 → **sum 1.0** (house share ~85%).
- **"~46% non-house" wrong.** It is **68% (116/170)** of all relocations, or **51% (56/110)** of the 110
  interpretable ones (excluding the refuge_4 burrow + tunnel).
- **Temperature over-unified.** house_1 ρ=+0.17 (rises) vs house_2 ρ=−0.19 (falls) are opposite, so "shift
  away from the enclosed houses" is retracted; the descriptive signal is **increased doorway (+0.58) /
  near-water (+0.38) use on warm days**, any-shelter ρ=−0.44 (which **includes** the burrow/tunnel). Candidate only.
- **Provenance.** The earlier note that "the summary is authoritative where it differs from the technical
  report" is **withdrawn** — the technical report is corrected and is the authoritative record above the summary.

## Deferred (next pass)
**Nap** detection in the active night (the ~midnight rest bout, scored separately from the trunk). The
true ~18:00 in-nest behavioral wake remains out of WISER's reach (needs interior CV CH07/CH08 / ephys).
Firmer temperature test needs a shelter thermistor + more days (the doorway signal is a candidate).
