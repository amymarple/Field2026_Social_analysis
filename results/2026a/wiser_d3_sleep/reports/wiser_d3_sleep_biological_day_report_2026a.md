# Direction 3 — biological-day sleep model (core rebuild)

*Candidate / measurement-limited. Rest = low-speed proxy (< 12.5 in/s), NOT ephys. WISER inch frame UNVERIFIED (ROI-identity + RELATIVE displacement only). Jitter ~7 in.*

> **This RETIRES the temperature-crossing `sleep_end`.** The rat biological day is a **sleep TRUNK ~05:00 → trunk-end** + an active night with a **~midnight nap (not trunk)**. The trunk end is `locomotor_emergence_hour` — the WISER **onset of sustained locomotion / sleep-site departure** (~20:00). **Sensor-limited interpretation:** WISER cannot observe in-shelter waking/stirring, so this variable is *only* the site-departure time; the field-observed ~18:00 in-nest wake vs this ~20:00 is **consistent with** WISER's invisibility to in-nest behavior but is **not proven** to be entirely caused by it (a genuinely later departure is not excluded without interior CV / ephys). For bounding a sleep-SITE window the locomotor edge is the correct boundary.

Days: 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08 · tags: 12378, 12380, 12386, 12395, 12407. Includes the independent change-point (Section D) + within-rat temperature-modulates-site (Section E). Nap detection deferred.

> **Reconciliation (2026-07-11).** The **single-largest change-point (A1, Section D)** and the **multi-site state-sequence relocations (A2, Section D multi-site)** are kept **separate**: different thresholds (**100 in** vs **36 in**), different timing (**13.5 h / 11%** vs **13.4 h / 8%** within ±1 h of 10:00). Dwell is reported **unconditionally** (sums to 1). Every number traces to `direction3_biological_day_sleep_canonical_results.md`/`.json` (derived from this run's CSVs). Superseded wording — conditional dwell shown as a composition, '~46% non-house', 'shift away from the houses', 'circadian-fixed' — is corrected here and recorded in `change_log/2026-07-10-biological-day-sleep.md`.

## Definitions (formula + plain text)

- **Rest proxy** `resting` = smoothed UWB speed `< c`, `c = 12.46` in/s (p99 stationary). Proxy for sleep, not ephys.
- **Sleep trunk** = the main daytime rest, local `[05:00, locomotor_emergence(day))`.
- **`locomotor_emergence_hour(day)`** = first afternoon 5-min bin (≥15:00) with activity fraction ≥ baseline_active + max(0.03, 0.20·(dusk_peak − baseline)), sustained ≥3 bins, clamped `[16:00, 21:00]`. The **relative** trip point catches the emergence, not the near-peak. Sensor-limited: locomotion onset / site departure, NOT in-nest wake.
- **Morning-window site** `[05:00, 10:00)` and **day-window site** `[10:00, emergence)` — per (day, rat) resting-fix centroid (median x,y), `nearest_shelter`, `dominant_roi`. **These fixed windows do NOT locate a transition time** — that is what Section D estimates independently.
- **Site STATE space (full ROI set)** — `classify_site_state` maps a segment centroid to **house_1, house_2, refuge_1/2/3, refuge_4** (date-gated by `valid_until`; burrow-flagged in window), **water_1, water_2, doorway** (near a shelter core, jitter band), **exposed** (open), **unknown**; `food_1/2 → house_1/2`. Explicit distance rule: enter a shelter within footprint + **15 in** (absorbs ~7 in jitter, p95 ~15); doorway a further **24 in**; else exposed. **Gaps:** no water-tower ROI (near-water = water_1/2); the boundary rect is inconsistent with the house positions → no reliable 'perimeter' (doorway is the entrance proxy).
- **Two DISTINCT site analyses (never merged):** **(A1) single-largest within-trunk change-point** (`detect_site_changepoint`) = the ONE trunk split (5-min median-position series, 3-bin smoothed) maximizing pre/post segment-median displacement; **supported** if displacement ≥ **100 in** with ≥3 bins each side. Its `confidence = disp/(disp+within-scatter)` is a **displacement-to-scatter ratio (separation score), NOT a statistical confidence / p-value / posterior**. from/to states = pre/post centroids classified **independently** via `classify_site_state`, never by displacement direction. It detects the largest early-vs-late contrast; it does NOT prove exactly one discrete relocation per rat-day. **(A2) multi-site state-sequence relocation** (`trunk_state_dwell_transitions`) = EVERY change between two ≥15-min (≥3-bin) confident state-segments whose centroids differ ≥ **36 in** (driver value, overriding the function default 24). **The 100-in change-point threshold does NOT apply to these.** **dwell fraction** = share of trunk bins in a state.
- **centroid_mad_in** = median radial deviation of a rat's per-day centroid from its own median. **Spearman ρ** = rank correlation. **dropout_frac** = 1 − present/expected 60-s bins.

## A. Locomotor emergence (sleep-site departure): evening-clustered, no detectable temperature association

```
 sleep_day  baseline_active  peak_active  locomotor_emergence_hour  crossed  afternoon_temp_c
2026-06-28              NaN         0.31                     21.00    False             28.19
2026-06-29             0.01         0.24                     21.00     True             29.76
2026-06-30             0.01         0.14                     20.67     True             31.60
2026-07-01             0.02         0.18                     19.67     True             33.64
2026-07-02             0.02         0.18                     20.92     True             34.36
2026-07-03             0.01         0.17                     16.00     True             29.55
2026-07-04             0.00         0.25                     21.00     True             28.22
2026-07-05             0.00         0.14                     20.67     True             26.17
2026-07-06             0.00         0.24                     20.58     True             23.28
2026-07-07             0.01         0.21                     20.83     True             25.20
2026-07-08             0.01         0.23                     20.92     True             29.34
```

- `locomotor_emergence_hour` median **20.8 h**; the detector crossed threshold on **10/11** days. On the **7 interior days** it lands **19.7–20.9 h**. **Boundary/censored days:** 3 at the 21:00 ceiling (2026-06-28, 2026-06-29, 2026-07-04 — 06-28 never crossed → censored, the others clamped from above), 1 at the 16:00 floor (2026-07-03 — fog-day afternoon activity blip); **clamp values are censored boundary outputs, not exact event times**. Spearman(emergence, afternoon_temp) = **-0.02** (n=11) → **no detectable monotonic association** across these 11 days. This is an **observational evening-clustering, NOT a demonstrated circadian mechanism**. It **retires** the old thermal `sleep_end` (which ran past midnight, 00:55/02:20, conflating the overnight cool-down + the midnight nap with the trunk end).
- **Sensor caveat (not an over-claim):** ~20:00 is the *locomotor* emergence (site departure). It LAGS the field-observed ~18:00 in-nest wake; that gap is **consistent with** WISER being blind to in-nest stirring (below the ~7 in jitter floor) but is **not proven** to be entirely that — measuring the true ~18:00 arousal needs ephys / interior CV (CH07/CH08).

## B. Morning-window vs day-window site — they DIFFER, but this does NOT prove a switch at 10:00

With 10:00 used as the window boundary, this section can only ask whether the morning-window [05–10] and day-window [10–emergence] **site assignments differ** — it **cannot** establish that a transition happens *at* 10:00 (that is Section D).
```
     night  shortid morning_shelter day_shelter  morning_vs_day_shift_in  shelter_differs      relocation_tier
2026-06-29    12378         house_1     house_1                    139.1            False    robust_relocation
2026-06-29    12380         house_1     house_1                     23.6            False               stable
2026-06-29    12386         house_1     house_2                    321.0             True major_shelter_switch
2026-06-29    12395         house_1     house_1                     16.9            False               stable
2026-06-29    12407         house_1     house_2                    309.2             True major_shelter_switch
2026-06-30    12378         house_1     house_1                     11.6            False               stable
2026-06-30    12380         house_1     house_2                    194.3             True major_shelter_switch
2026-06-30    12386         house_1     house_1                      5.4            False               stable
2026-06-30    12395         house_1     house_1                      5.8            False               stable
2026-06-30    12407         house_1     house_1                     19.3            False               stable
2026-07-01    12378         house_1     house_1                      2.3            False               stable
2026-07-01    12380         house_1     house_1                     16.4            False               stable
2026-07-01    12386         house_1     house_1                     11.1            False               stable
2026-07-01    12395         house_1     house_1                      6.0            False               stable
2026-07-01    12407         house_1     house_2                    179.5             True major_shelter_switch
2026-07-02    12378         house_1     house_1                      6.4            False               stable
2026-07-02    12380         house_1     house_1                     14.4            False               stable
2026-07-02    12386         house_1     house_1                     14.8            False               stable
2026-07-02    12395         house_2     house_2                     24.0            False               stable
2026-07-02    12407         house_1     house_1                     66.1            False             marginal
2026-07-03    12378         house_1     house_1                     20.2            False               stable
2026-07-03    12380         house_2     house_2                     25.9            False               stable
2026-07-03    12386         house_1     house_1                    124.0            False    robust_relocation
2026-07-03    12395         house_1     house_2                    173.1             True major_shelter_switch
2026-07-03    12407         house_2     house_2                     25.8            False               stable
2026-07-04    12378         house_2     house_2                     12.7            False               stable
2026-07-04    12380         house_1     house_2                    180.7             True major_shelter_switch
2026-07-04    12386         house_1     house_2                    188.4             True major_shelter_switch
2026-07-04    12395         house_2     house_2                     11.0            False               stable
2026-07-04    12407         house_2     house_2                     12.5            False               stable
2026-07-05    12378         house_1     house_1                     12.8            False               stable
2026-07-05    12380         house_1     house_1                      8.3            False               stable
2026-07-05    12386         house_1     house_2                    313.7             True major_shelter_switch
2026-07-05    12395         house_1     house_2                    182.5             True major_shelter_switch
2026-07-05    12407         house_2     house_2                     27.5            False               stable
2026-07-06    12378         house_1     house_1                      2.6            False               stable
2026-07-06    12380         house_1     house_1                      4.7            False               stable
2026-07-06    12386         house_1     house_2                    316.7             True major_shelter_switch
2026-07-06    12395         house_2     house_2                      0.7            False               stable
2026-07-06    12407         house_2     house_2                      3.5            False               stable
2026-07-07    12378         house_1     house_2                    199.1             True major_shelter_switch
2026-07-07    12380         house_1     house_1                      7.3            False               stable
2026-07-07    12386         house_1     house_2                    196.3             True major_shelter_switch
2026-07-07    12395         house_2     house_2                      5.0            False               stable
2026-07-07    12407         house_2     house_2                     12.4            False               stable
2026-07-08    12378         house_2     house_2                      7.7            False               stable
2026-07-08    12380         house_1     house_2                    200.6             True major_shelter_switch
2026-07-08    12386         house_1     house_2                    183.0             True major_shelter_switch
2026-07-08    12395         house_2     house_2                     17.9            False               stable
2026-07-08    12407         house_1     house_2                    206.4             True major_shelter_switch
```

- Morning-window vs day-window nearest-house **differs on 15/50** rat-days (tiers {'stable': 32, 'major_shelter_switch': 15, 'robust_relocation': 2, 'marginal': 1}). This is a **difference between two fixed windows**, not a located transition time.

## D (A1). Single-largest within-trunk change-point (no fixed 10:00) — WHEN is the biggest shift?

- **44/55 rat-days have a SUPPORTED change-point** (pre/post displacement ≥ 100 in). Full table `within_trunk_changepoints.csv`.
- **Change-point TIME distribution (supported):** median **13.5 h**, IQR [6.8, 18.2]; **11% within ±1 h of 10:00**, 16% within ±2 h. Range 5.2–20.8 h. See `CP1`.
  → The transitions are **SPREAD across the trunk, NOT tightly clustered at 10:00** (the fixed-window Section B is therefore a coarse proxy at best).
- **Change-point from→to STATES (classified independently over the full ROI set, NOT by displacement direction):**
```
from_state to_state  n
   house_1  house_2 16
   house_2  house_1  8
   exposed  house_1  3
    tunnel  house_1  3
  refuge_4  house_2  3
   house_1 refuge_4  3
  refuge_4  house_1  3
  refuge_1  house_2  2
   house_1  doorway  1
   house_1  exposed  1
   house_2  exposed  1
```
- **Separation criteria:** supported requires displacement ≥ 100 in (~14× jitter) AND ≥3 bins each side. The supported set is **high-separation** — median separation score 0.96 (= disp/(disp+scatter), a RATIO, not a statistic), median displacement **203 in** (≈ the house_1↔house_2 separation): clean full-shelter position steps, not jitter. So the largest within-trunk shift is COMMON and LARGE, just not time-locked to 10:00.
- **Sensitivity to smoothing** (`smooth_bins ∈ [1, 3, 5]`): of the 44 supported rat-days, **36** keep a supported change-point at the same time (±1 h) across all three smoothings (`changepoint_smoothing_sensitivity.csv`).
- **Sensitivity to missing data:** 5 rat-days have >25% trunk dropout (lower-confidence; a gap is 'unknown', not a move). Restricting to ≤25%-dropout supported change-points, median time = 13.4 h (vs 13.5 h all) — reports whether the timing survives the dropout filter.

### D (A2) — multi-site state-sequence: full-state dwell, ALL relocations, transition matrix

The change-point above finds only the single largest positional shift. The **state sequence** classifies EVERY trunk segment to the full ROI state space (`trunk_state_dwell_transitions`) — so relocations are labelled by **independent state mapping**, not displacement direction.
- **Dwell composition — UNCONDITIONAL** (mean over all 55 rat-days incl. zeros; **sums to 1.0**; this is the valid composition):
```
  house_1  0.512
  house_2  0.334
 refuge_4  0.054
  doorway  0.043
 refuge_1  0.020
  exposed  0.017
   tunnel  0.010
  water_2  0.009
 refuge_3  0.000
 refuge_2  0.000
  (sum 1.000; house_1+house_2 = 0.847 ≈ 85% of classified trunk dwell)
```
  *`refuge_4` (burrow) + `tunnel` are interpretation-limited; `doorway`/`exposed` are classifier-dependent and jitter-adjacent; `water_2` is a near-water ROI (NOT a validated water-tower refuge).*
- **Dwell — CONDITIONAL-on-appearance** (mean *only over rat-days where the state occurs*; `size` = # such rat-days; **does NOT sum to 1 — do not read as a composition**):
```
   state  mean  median  size
 house_1 0.522   0.536    54
 house_2 0.400   0.376    46
refuge_4 0.135   0.103    22
  tunnel 0.111   0.104     5
refuge_1 0.086   0.068    13
 doorway 0.054   0.026    43
 water_2 0.054   0.047     9
 exposed 0.023   0.010    41
refuge_3 0.011   0.011     2
refuge_2 0.005   0.005     1
  (sum 1.401 — conditional, NOT the composition)
```
- **Relocations per rat-day:** mean 3.1, median 3, range 0–8; 6/55 rat-days with 0 (170 relocations total).
- **Transition matrix (from→to over ALL relocations; independent state labels):**
```
from_state to_state  n
   house_1  house_2 28
   house_2  house_1 26
  refuge_4  house_2 17
   house_1 refuge_4 10
  refuge_4  house_1 10
   house_2  doorway 10
   house_1  doorway  9
  refuge_1  house_1  8
   doorway  house_1  8
   doorway  house_2  8
   house_2 refuge_4  8
    tunnel  house_2  4
   house_1 refuge_1  3
   house_1   tunnel  3
   doorway refuge_1  2
   water_2  house_1  2
   exposed  house_1  2
    tunnel refuge_1  2
    tunnel  house_1  2
   exposed refuge_4  1
  refuge_1  doorway  1
   house_2 refuge_1  1
   house_2   tunnel  1
   house_2  water_2  1
  refuge_4 refuge_1  1
    tunnel refuge_4  1
   water_2  house_2  1
```
  These are **NOT all house_1↔house_2** — the full state space exposes house↔refuge, house↔water, house↔doorway, and exposed transitions the binary framing hid. **Caveat:** `refuge_4`-involving rows fall in the **07-03→07-07 BURROW window** (refuge_4 = burrow entrance + UWB below-plane dropout, **NOT a sleep site**) → discount those. See `SS1`.
  **Non-house involvement (quantified):** 116/170 = 68% of all 170 relocations involve ≥1 non-house state; restricting to the **110 interpretable** relocations (excluding refuge_4/tunnel), 56/110 = 51% do.
- **Relocation timing:** median 13.4 h; 8% within ±1 h of 10:00 → spread across the trunk (consistent with the change-point), not a 10:00 switch.

## E. Does temperature modulate the MULTI-SITE sleep-site distribution? (within-rat)

> **Supersedes the earlier binary house_2-fraction test** (that state space was misspecified — rats also use secondary refuges, near-water, doorways, and exposed rest). Here the outcome is the **dwell distribution across ALL states**. Absolute use is identity-dominated, so tests are **within-rat** (rat-centered); ambient temperature is a **coarse covariate** (no shelter microclimate), so a null is *no detectable association under the current measurement + N*.

- **(a) Any-shelter vs exposed:** Spearman(rat-centered any-shelter dwell fraction, midday peak temp) = **-0.44** (n=55). **Negative** — a rat spends **LESS** time fully enclosed on its hotter days (**candidate**). NB `any_shelter_frac` **includes** the interpretation-limited refuge_4/tunnel, so read the per-state panel (b) for where the change actually is. See `E1`.
- **(b) Which site vs temp** (rat-centered Spearman of each state's dwell fraction vs peak temp; multiple comparisons, small N — descriptive):
```
   state rho_dwellfrac_vs_peaktemp_ratcentered  n  mean_dwell_frac
 house_1                                  0.17 55            0.512
 house_2                                 -0.19 55            0.334
refuge_1                                  0.27 55            0.020
refuge_2                                  0.03 55            0.000
refuge_3                                  0.11 55            0.000
 water_2                                  0.38 55            0.009
 exposed                                 -0.31 55            0.017
 doorway                                  0.58 55            0.043
```
  **Candidate multi-site temperature signal** (|ρ|>0.3, uncorrected): water_2 ρ=+0.38 (↑ with heat); exposed ρ=-0.31 (↓ with heat); doorway ρ=+0.58 (↑ with heat). The two houses go **opposite** ways (house_1 ρ=+0.17 rises, house_2 ρ=−0.19 falls), so this is **NOT** a uniform 'leave the enclosed houses' pattern; the most consistent descriptive signal is **increased doorway-classified dwell on hotter days**, with near-water (`water_2`) a weak spatial clue needing ROI validation. The binary house_2-fraction test (ρ≈−0.20) missed it. **Candidate only:** n=11 days, uncorrected multiple comparisons, ambient (not shelter) temperature; doorway/exposed are jitter-adjacent (position noise at shelter edges). Rat-centering removes each rat's MEAN occupancy only — it does not fit rat-specific slopes, model shared day-level exposure, or adjust for day-since-release.
- **Caveats:** ambient (not shelter) temperature; house_2/refuges **not verified cooler** (inch frame); temperature acts on BOTH the animal and UWB-dropout paths; refuge_4 burrow days flagged. See `SS1`/`E1` + `site_dwell_vs_temperature.csv`, `per_state_temp_corr.csv`.

## C. Across-day site stability (per rat, per window)

```
 shortid  window  n_days  centroid_mad_in modal_shelter  frac_days_at_modal
   12378 morning      10             4.18       house_1                0.80
   12380 morning      10             4.10       house_1                0.90
   12386 morning      10             4.36       house_1                1.00
   12395 morning      10            94.73       house_1                0.50
   12407 morning      10            95.07       house_1                0.50
   12378     day      11            14.49       house_1                0.73
   12380     day      11            14.36       house_1                0.64
   12386     day       9            90.63       house_1                0.56
   12395     day      11            10.34       house_2                0.64
   12407     day      11            11.70       house_2                0.73
```

- `centroid_mad_in` < 30 in = a stable across-day site (within ~4× jitter).

## Dropout guard

- Window animal-days with >25% dropout: 5. refuge_4-dominant reads (07-03→07-07) flagged `burrow_flag` and excluded (burrow entrance, not sleep).

## Evidence status (two levels)

**Supported within the current WISER measurement (descriptive):** detected within-trunk site changes are not concentrated near 10:00 (A1 11% / A2 8% within ±1 h); the two house-labelled ROIs hold ~85% of unconditional low-movement trunk dwell; the state-sequence detects multiple qualifying transitions per rat-day (mean 3.1), ~half of interpretable relocations touching a non-house state; WISER locomotor emergence is evening-clustered (~20.8 h) with no detectable temperature association over 11 days; individual differences in primary house and mobility are stable.

**Candidate biological interpretation (NOT established):** the low-movement trunk corresponds to physiological sleep; classified ROIs correspond to specific physical refuge structures (frame unverified); doorway/near-water use on hot days reflects thermoregulation; evening emergence clustering is generated by a circadian mechanism; `water_2` is the water-tower refuge. Each requires external validation (interior CV CH07/CH08 / ephys, georeference survey, in-shelter thermistor).

## Deferred (next pass)

- **Nap detection** in the active night (the ~midnight rest bout, scored separately from the trunk). The true ~18:00 in-nest behavioral wake needs interior CV (CH07/CH08) / ephys.


*Figures + CSVs: `D:\Field2026_analysis_out\biological_day_sleep_20260711_1515`.*
