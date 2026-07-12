# Direction 3 — evening (baseline) vs morning (weather-driven) sleep

*Candidate / measurement-limited. Rest = low-speed proxy (< 12.5 in/s), NOT ephys. WISER inch frame UNVERIFIED (ROI-identity + RELATIVE displacement only; house_2 is not verified cooler). Jitter floor ~7 in. Weather alignment wall-clock UTC, unverified ~5 min; weather acts on BOTH the animal and UWB-dropout paths -> temperature/weather-**linked**, never causal. Field-log notes are hypotheses, not labels.*

Days: 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08 · tags: 12378, 12380, 12386, 12395, 12407.

> ⚠️ **`sleep_end` IS PROVISIONAL AND PARTLY WRONG — DO NOT USE THE PAST-MIDNIGHT VALUES.**
>
> Field observation + the phase-locked ~21:00 circadian result (activity onset does NOT drift with temperature) say the rats' **sleep TRUNK is ~05:00→18:00** (wake/emerge **~18:00**), followed by an active evening→night that contains a **~midnight NAP which is NOT the trunk**. The temperature-calibrated `sleep_end` here searches THROUGH the night and so reads **past midnight on hot nights** (e.g. 07-02 ≈02:20, 06-30 ≈01:20) — that **conflates the midnight nap with the end of the main sleep** and wrongly makes emergence temperature-driven when it is **circadian-fixed near ~18:00**. Treat every `sleep_end`/`emergence` value below (and the red/green markers in figures `A1`/`W1`) as an **artifact pending a biological-day rebuild** (sleep-trunk bout + wake detection, naps flagged separately). **The evening-baseline SITE (Section A), the morning-vs-baseline comparison, and the activity-fraction curves themselves are unaffected — only the `sleep_end` marker/interpretation is wrong.**

## Definitions (every derived quantity: formula + plain text)

- **Rest proxy** `resting` — smoothed UWB speed `v_s < c`, `c = 12.46` in/s (p99 of the stationary baseline). Plain: below this the tag is indistinguishable from a still rat; a proxy for rest/sleep, not ephys-validated.
- **Sleep site** — per (day, window, rat): centroid `= (median x, median y)` over resting fixes; `spread_in = median( ||fix − centroid|| )` (inch compactness / confidence); `nearest_shelter = argmin_s ||centroid − centre(s)||` over {house_1, house_2}; `in_shelter_frac = mean( roi ∈ {house_1,house_2} )`.
- **Morning window** — local `[05:00, 10:00)`, i.e. **before the ~10:00 sleep-site switch**: the bed-down site after the active night; expected to depend on temperature + overnight rain.
- **Evening window** — local `[17:00, sleep_end(day))` for the resting-site centroid (slice capped at 24:00, the loaded-window edge; the centroid of a stationary resting rat is the same whether measured to 24:00 or to the true past-midnight end).
- **sleep_end_hour** — the END of the daytime **SLEEP PERIOD** (evening/overnight emergence). The nocturnal rat's 'day' is one full sleep period, **not** a 0–24 h calendar day, so this is **hours since midnight** and **may exceed 24** (past midnight) on hot nights. **theta\*** `= median( T over 20:00–22:00 across days ) = 22.6 °C`; **sleep_end** `= first time after the afternoon peak — searched THROUGH the night, up to 06:00 next day — with outside T ≤ theta\*`, hours since midnight, clamped `[18, 30]`. A hotter night reaches theta\* later, so it emerges later. Independent cross-check: **behavioral emergence** = first ≥2×5-min-bin run with active fraction ≥ 0.15, searched from 15:00 through the night (also hours-since-midnight).
- **overnight_rain_mm** `= Σ rain_rate(mm/h) · Δt(h)` over local `[prev-day 21:00, this-day 11:00)` (gaps capped 30 min) — antecedent wetness at morning bed-down. **morning_temp_c** / **evening_temp_c** = mean outside T over each window.
- **Move from baseline** `morning_vs_evening_baseline_in = ||morning_centroid − baseline_centroid||`, where a rat's evening **baseline_centroid** = median of its evening centroids across days. `morning_vs_evening_same_day_in` uses the same day's evening. **shelter_switch_vs_baseline** = morning nearest_shelter ≠ baseline nearest_shelter.
- **Relocation tier** (reuse RELOCATION_TIERS, inches): stable <30 · marginal 30–75 · borderline 75–100 · robust 100–180 · major/​switch ≥180 or an identity switch >75. 30 in ≈ 4× the jitter floor, so 'stable' is within measurement noise.
- **dropout_frac** `= 1 − present_bins / expected_bins` over the window's 60-s grid — the share of the window with no WISER fix. A gap is **unknown**, never 'moved'; > 0.25 = lower-confidence. **wet** = `overnight_rain_mm > 0.2`; **warm/cool** = median split of morning_temp_c. **Spearman ρ** = Pearson correlation of the ranks (numpy).

## Sleep-period END (`sleep_end`) — ⚠️ PROVISIONAL / PARTLY WRONG, see the banner above

`sleep_end_hour` is hours since midnight, searched THROUGH the night. **This is the flagged error:** the real sleep trunk ends at the **circadian-fixed ~18:00 wake**, so the past-midnight values below are the active-night/**midnight-nap** region, NOT the end of the main sleep. Kept here only for continuity until the biological-day rebuild replaces it. `emergence_hour` (behavioral) is a cross-check on the SAME flawed 0–24 h framing:

```
 sleep_day  peak_temp_c  threshold_c  sleep_end_hour  crossed  emergence_hour  peak_active_frac
2026-06-28         30.4        22.65           20.58     True           21.00              0.31
2026-06-29         32.1        22.65           20.58     True           21.33              0.24
2026-06-30         34.2        22.65           25.33     True             NaN              0.14
2026-07-01         36.2        22.65           22.58     True           21.50              0.18
2026-07-02         36.0        22.65           26.33     True             NaN              0.18
2026-07-03         33.2        22.65           21.25     True             NaN              0.17
2026-07-04         31.6        22.65           20.58     True           21.42              0.25
2026-07-05         27.3        22.65           18.08     True             NaN              0.14
2026-07-06         25.4        22.65           18.00     True           21.17              0.24
2026-07-07         27.6        22.65           20.25     True           21.75              0.21
2026-07-08         31.2        22.65           21.33     True             NaN              0.23
```

Read: `sleep_end_hour` tracks the day's heat — a hotter afternoon peak pushes the theta\* crossing (hence emergence) later, **into the early morning (>24) on the hottest nights** rather than pinning at 24. Where the behavioral `emergence_hour` is present it lands ~21:00 on cool nights and later/absent on hot ones, corroborating the thermal end. `peak_active_frac` is low on every night (0.12–0.31): the daytime is overwhelmingly restful and there is no sharp pre-midnight activity burst, so the evening baseline centroid is measured on genuine rest.

## Activity fraction per night (figure `A1_activity_fraction_by_night.png`)

Per-night active-fraction curves on a **noon → next-noon** axis (so the evening/overnight emergence is not truncated at midnight); grey band = past midnight (hours > 24). **Co-plotted: outside temperature (red line, right °C axis) and rain rate (cyan bars, far-right mm/h axis, shown only on rain days).** The 6/28 panel shows the **release-driven pseudo peak at ~19:30** (rats let out ~19:25 — an artefact of release, not a natural emergence). Red dashed = thermal `sleep_end`, green dotted = behavioral `emergence`. Reading it: the evening **temperature cooling curve** lines up with each night's emergence, and rain shows its dual effect — e.g. **07-01's ~19:00 downpour (~45 mm/h) coincides with an activity spike** (rats bolting to shelter, per the field log) while it also cools the air. This is the human-readable view of when each night's sleep period ends vs the weather that shapes it.

## Weather by day / window

```
     night  morning_temp_c  morning_rain_mmhr  overnight_rain_mm  evening_temp_c  sleep_end_hour
2026-06-28           18.11               0.00               0.00           26.43           20.58
2026-06-29           18.83               0.00               0.00           28.12           20.58
2026-06-30           23.15               0.00               0.00           26.37           25.33
2026-07-01           26.15               0.00               0.30           26.13           22.58
2026-07-02           24.32               0.00               0.00           29.64           26.33
2026-07-03           25.93               0.00               0.00           26.48           21.25
2026-07-04           23.21               0.00               0.00           24.47           20.58
2026-07-05           20.81               0.00               0.00           24.22           18.08
2026-07-06           21.27               0.00               0.20           22.09           18.00
2026-07-07           18.97               0.02               2.37           25.84           20.25
2026-07-08           19.61               0.00               0.00           28.20           21.33
```

- **2 wet-morning day(s)** (overnight_rain > 0.2 mm): 07-01 (0.30 mm), 07-07 (2.37 mm); max 2.37 mm. So the **rain** side is now **weakly testable** — but the wet-N is tiny (a few animal-days) and confounded by individual site fidelity, so read it as suggestive, not conclusive.

## A. Evening BASELINE sleep site (the weather-clean reference)

```
shortid  n_days  baseline_x  baseline_y baseline_shelter  frac_days_at_modal_shelter  centroid_mad_in
  12378      10       435.2       727.2          house_1                         0.6             17.6
  12380      11       427.5       727.8          house_1                         0.7             10.0
  12386      10       510.3       724.4          house_1                         0.5             91.1
  12395      11       604.6       727.7          house_2                         0.5             15.4
  12407      11       618.9       723.9          house_2                         0.8              5.5
```

- **4/5** rats hold their evening site to within the 30-in jitter-scale band across days (`centroid_mad_in` < 30) — a stable individual baseline, as expected for the least daytime-influenced window. `frac_days_at_modal_shelter` shows how often each rat's evening nearest-house is its modal one.
- **1 rat(s) are NOT stable — 12386 (MAD 91 in):** their evening centroid is **bimodal** (they split evenings between house_1 and house_2), so the single median `baseline_centroid` sits *between* the houses. Consequence: their `morning_vs_evening_baseline_in` (~90 in nearly every day, tier `borderline`) is an **artifact of the bimodal baseline, NOT a real morning relocation** — read those rows as 'variable evening site', and note they inflate the cool/dry stratum medians in Section C. A per-mode baseline would be needed to score their morning moves cleanly.

## B. MORNING sleep site vs the evening baseline

```
     night shortid morning_shelter baseline_shelter  morning_vs_evening_baseline_in  shelter_switch_vs_baseline      relocation_tier  morning_temp_c  overnight_rain_mm  morning_dropout_frac
2026-06-29   12378         house_1          house_1                          144.04                       False    robust_relocation           18.83               0.00                  0.00
2026-06-29   12380         house_1          house_1                           22.18                       False               stable           18.83               0.00                  0.00
2026-06-29   12386         house_1          house_1                          220.91                       False major_shelter_switch           18.83               0.00                  0.00
2026-06-29   12395         house_1          house_2                          199.39                        True major_shelter_switch           18.83               0.00                  0.00
2026-06-29   12407         house_1          house_2                          313.15                        True major_shelter_switch           18.83               0.00                  0.00
2026-06-30   12378         house_1          house_1                           21.27                       False               stable           23.15               0.00                  0.00
2026-06-30   12380         house_1          house_1                           13.70                       False               stable           23.15               0.00                  0.00
2026-06-30   12386         house_1          house_1                           98.53                       False           borderline           23.15               0.00                  0.00
2026-06-30   12395         house_1          house_2                          191.03                        True major_shelter_switch           23.15               0.00                  0.00
2026-06-30   12407         house_1          house_2                          203.63                        True major_shelter_switch           23.15               0.00                  0.00
2026-07-01   12378         house_1          house_1                           22.38                       False               stable           26.15               0.30                  0.00
2026-07-01   12380         house_1          house_1                           14.61                       False               stable           26.15               0.30                  0.00
2026-07-01   12386         house_1          house_1                           91.92                       False           borderline           26.15               0.30                  0.00
2026-07-01   12395         house_1          house_2                          193.19                        True major_shelter_switch           26.15               0.30                  0.00
2026-07-01   12407         house_1          house_2                          199.70                        True major_shelter_switch           26.15               0.30                  0.00
2026-07-02   12378         house_1          house_1                           21.80                       False               stable           24.32               0.00                  0.00
2026-07-02   12380         house_1          house_1                           16.40                       False               stable           24.32               0.00                  0.00
2026-07-02   12386         house_1          house_1                           91.00                       False           borderline           24.32               0.00                  0.00
2026-07-02   12395         house_2          house_2                           17.42                       False               stable           24.32               0.00                  0.00
2026-07-02   12407         house_1          house_2                          204.96                        True major_shelter_switch           24.32               0.00                  0.00
2026-07-03   12378         house_1          house_1                           16.56                       False               stable           25.93               0.00                  0.00
2026-07-03   12380         house_2          house_1                          194.11                        True major_shelter_switch           25.93               0.00                  0.00
2026-07-03   12386         house_1          house_1                          100.64                       False    robust_relocation           25.93               0.00                  0.00
2026-07-03   12395         house_1          house_2                          188.71                        True major_shelter_switch           25.93               0.00                  0.00
2026-07-03   12407         house_2          house_2                            0.60                       False               stable           25.93               0.00                  0.00
2026-07-04   12378         house_2          house_1                          169.22                        True major_shelter_switch           23.21               0.00                  0.00
2026-07-04   12380         house_1          house_1                           14.06                       False               stable           23.21               0.00                  0.00
2026-07-04   12386         house_1          house_1                           91.24                       False           borderline           23.21               0.00                  0.00
2026-07-04   12395         house_2          house_2                            6.38                       False               stable           23.21               0.00                  0.00
2026-07-04   12407         house_2          house_2                            6.78                       False               stable           23.21               0.00                  0.00
2026-07-05   12378         house_1          house_1                           16.97                       False               stable           20.81               0.00                  0.00
2026-07-05   12380         house_1          house_1                            9.79                       False               stable           20.81               0.00                  0.00
2026-07-05   12386         house_1          house_1                           94.92                       False           borderline           20.81               0.00                  0.00
2026-07-05   12395         house_1          house_2                          186.60                        True major_shelter_switch           20.81               0.00                  0.02
2026-07-05   12407         house_2          house_2                           31.24                       False             marginal           20.81               0.00                  0.01
2026-07-06   12378         house_1          house_1                           22.15                       False               stable           21.27               0.20                  0.02
2026-07-06   12380         house_1          house_1                           13.24                       False               stable           21.27               0.20                  0.00
2026-07-06   12386         house_1          house_1                           89.24                       False           borderline           21.27               0.20                  0.11
2026-07-06   12395         house_2          house_2                            5.58                       False               stable           21.27               0.20                  0.13
2026-07-06   12407         house_2          house_2                           13.99                       False               stable           21.27               0.20                  0.02
2026-07-07   12378         house_1          house_1                           18.77                       False               stable           18.97               2.37                  0.06
2026-07-07   12380         house_1          house_1                           14.84                       False               stable           18.97               2.37                  0.02
2026-07-07   12386         house_1          house_1                           92.70                       False           borderline           18.97               2.37                  0.02
2026-07-07   12395         house_2          house_2                            6.86                       False               stable           18.97               2.37                  0.11
2026-07-07   12407         house_2          house_2                           16.32                       False               stable           18.97               2.37                  0.03
2026-07-08   12378         house_2          house_1                          178.10                        True major_shelter_switch           19.61               0.00                  0.00
2026-07-08   12380         house_1          house_1                           13.73                       False               stable           19.61               0.00                  0.00
2026-07-08   12386         house_1          house_1                           96.29                       False           borderline           19.61               0.00                  0.00
2026-07-08   12395         house_2          house_2                            2.25                       False               stable           19.61               0.00                  0.00
2026-07-08   12407         house_1          house_2                          203.60                        True major_shelter_switch           19.61               0.00                  0.00
```

- Morning-vs-baseline tiers: {'stable': 25, 'major_shelter_switch': 14, 'borderline': 8, 'robust_relocation': 2, 'marginal': 1}. Nearest-house switches vs baseline: 13/50 rat-days.

## C. Weather cross-check (warm/dry vs cool/wet)

```
    stratum  n  median_move_in  n_shelter_switch
 cool(<med) 25           22.18                 5
warm(>=med) 25           91.00                 8
        dry 40           60.24                11
        wet 10           20.57                 2
```

- Spearman(move-from-baseline, morning_temp) = -0.02 (n=50); Spearman(move-from-baseline, overnight_rain) = -0.20 (n=50).
  Read: a positive ρ vs rain (or the cool/wet stratum showing a larger median move / more shelter switches) is the **candidate weather-linked morning relocation**; a flat evening (by design) is the contrast. These are descriptive on a small N, outside-air proxy, and do NOT establish causation.

- **Verdict (this window):** morning sleep-site departures from the evening baseline do **NOT** track temperature (|ρ|=0.02, essentially flat). The **rain** hypothesis is now **weakly testable** (n=50, a few wet animal-days): Spearman(move, overnight_rain) = **-0.20** — near-zero / slightly **negative**, i.e. rain does NOT increase the move from baseline (if anything rats keep *more* site fidelity when wet). Tiny wet-N + the 12386 bimodal confound → **suggestive, not conclusive.** The 13 nearest-house switches read as **individual / diurnal** (e.g. 12395/12407 bed in house_1 mornings but house_2 evenings), not weather-locked.
- **Caveat on the stratum medians:** the elevated cool/dry median move is driven by the bimodal-baseline rat(s) 12386 (~90-in constant offset from a between-houses median, Section A) — a baseline artifact, not a temperature effect. Drop them and the median move falls to the jitter scale; the no-temperature verdict holds.

## Dropout guard (did a wet morning fake a move?)

- Morning animal-days with >25% dropout: 0. Rain attenuates UWB, so treat those morning moves as **lower-confidence**; a gap is 'unknown', never a relocation.

## refuge_4 burrow caveat

- `refuge_4`-dominant sleep-site reads inside 07-03 → 07-07: **2** (flagged `burrow_flag`, excluded from baseline + morning-vs-baseline). refuge_4 was a burrow ENTRANCE (>1 rat dug nightly from ~07-03 01:00; removed 07-07 13:00), so those are burrow behaviour + a UWB-dropout lower bound, never sleep. house_1/house_2 unaffected.


*Figures + CSVs: `D:\Field2026_analysis_out\direction3_evening_morning_sleep_20260709_2338`.*
