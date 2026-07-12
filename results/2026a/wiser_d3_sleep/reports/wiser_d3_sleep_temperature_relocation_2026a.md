# Direction 3 (Stage B) — within-day rest-site relocation & temperature

*Candidate / measurement-limited. Rest = low-speed proxy (< 12.5 in/s), NOT ephys-validated. WISER inch frame UNVERIFIED (ROI-identity + outside-temp/time proxies only). Jitter floor ~7 in. Weather alignment wall-clock UTC, unverified ~5 min. Field-log notes are hypotheses, not labels.*

Days: 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08 · tags: 12378, 12380, 12386, 12395, 12407 · 56 rest bouts · 66 within-day relocation events.

## Dropout guard (does a wet day fake a 'move'?)

Per-animal daytime **dropout fraction** (share of the 05:00–21:00 minute grid with no WISER fix). Rain/wet attenuates UWB, so a high-dropout day can mimic a rest-site change:

```
night    2026-06-28  2026-06-29  2026-06-30  2026-07-01  2026-07-02  2026-07-03  2026-07-04  2026-07-05  2026-07-06  2026-07-07  2026-07-08
shortid                                                                                                                                    
12378           0.9         0.0         0.0        0.00         0.0         0.0         0.0        0.05        0.03        0.06         0.0
12380           0.9         0.0         0.0        0.10         0.0         0.0         0.0        0.00        0.00        0.01         0.0
12386           0.9         0.0         0.0        0.00         0.0         0.0         0.0        0.07        0.05        0.07         0.0
12395           0.9         0.0         0.0        0.08         0.0         0.0         0.0        0.02        0.04        0.03         0.0
12407           0.9         0.0         0.0        0.00         0.0         0.0         0.0        0.08        0.01        0.01         0.0
```

- Animal-days with >25% dropout: 5 (2026-06-28/12378, 2026-06-28/12380, 2026-06-28/12386, 2026-06-28/12395, 2026-06-28/12407). (6/28 is a PARTIAL day — evening release ~19:25 — so its high dropout is expected, not signal loss.) Interpret high-dropout reads as **lower-confidence**.

## refuge_4 BURROW caveat (2026-07-03 → 2026-07-07 13:00 removal, NOT sleep)

- **11 animal-window(s)** show `refuge_4` as the dominant daytime rest ROI inside the burrow window: 07-03/12378(midday), 07-04/12378(midday), 07-04/12378(afternoon), 07-04/12386(afternoon), 07-04/12395(midday), 07-04/12395(afternoon), 07-05/12378(afternoon), 07-05/12386(midday), 07-05/12386(afternoon), 07-06/12386(late), 07-06/12386(midday). `refuge_4` was a **burrow ENTRANCE** (>1 rat dug it nightly from ~07-03 01:00 EDT; removed 07-07 13:00), so these are **burrow-entrance behaviour + a UWB-dropout lower bound** (the tag vanishes when the rat goes below the anchor plane), **never daytime sleep**. Do NOT count them as a shelter/rest site or a 'relocation to refuge_4'. All house_1/house_2 reads are unaffected. (See `change_log/2026-07-07-shelter4-burrow-removed.md`.)

## Q1/Q3 — Do rats move rest sites within a day (morning → midday/afternoon)?

**2026-06-28** — warm ~22-23C (evening release ~19:25); PARTIAL day (evening only)
  - 12378: evening:house_1
  - 12380: evening:house_1
  - 12386: evening:house_1
  - 12395: evening:house_1
  - 12407: evening:house_1

**2026-06-29** — sunny/HOT ~30C; obs 11:48 'pile to sleep, prefer above metal/in shade, house may be too hot'; Sova removed 15:00
  - 12378: early:refuge_1 → late:house_1 → midday:house_1 → afternoon:open → evening:open
  - 12380: early:refuge_1 → late:house_1 → midday:open → afternoon:open → evening:open
  - 12386: early:open → late:house_1 → midday:open → afternoon:house_2 → evening:house_2
  - 12395: early:refuge_1 → late:house_1 → midday:house_1 → afternoon:open → evening:open
  - 12407: early:open → late:house_1 → midday:open → afternoon:house_2 → evening:house_2

**2026-06-30** — sunny/humid HIGH ~34C; thunderstorm/rain ~17:30 (rats bolt to shelter); AM IR-condensation fogged glass
  - 12378: early:house_1 → late:open → midday:open → afternoon:open → evening:open
  - 12380: early:house_1 → late:house_1 → midday:open → afternoon:house_2 → evening:house_2
  - 12386: early:house_1 → late:house_1 → midday:open → afternoon:house_1 → evening:house_1
  - 12395: early:house_1 → late:open → midday:open → afternoon:refuge_1 → evening:house_1
  - 12407: early:house_1 → late:house_2 → midday:open → afternoon:open → evening:open

**2026-07-01** — sunny/humid high ~36C; thunderstorm/rain ~19:45 (post rest window)
  - 12378: early:house_1 → late:house_1 → midday:house_1 → afternoon:open → evening:open
  - 12380: early:house_1 → late:house_1 → midday:open → afternoon:open → evening:open
  - 12386: early:house_1 → late:house_1 → midday:open → afternoon:open → evening:open
  - 12395: early:house_1 → late:house_1 → midday:house_1 → afternoon:open → evening:house_1
  - 12407: early:house_1 → late:open → midday:open → afternoon:house_2 → evening:house_2

**2026-07-02** — hot ~33-35C midday
  - 12378: early:house_1 → late:house_1 → midday:house_1 → afternoon:house_1 → evening:open
  - 12380: early:house_1 → late:house_1 → midday:open → afternoon:open → evening:house_1
  - 12386: early:house_1 → late:house_1 → midday:open → afternoon:open → evening:open
  - 12395: early:house_2 → late:open → midday:open → afternoon:open → evening:house_2
  - 12407: early:house_1 → late:house_1 → midday:open → afternoon:open → evening:open

**2026-07-03** — pre-dawn fog; refuge_4 BURROW digging begins ~01:00 (nightly) — refuge_4 reads = burrow, not sleep
  - 12378: early:open → late:house_1 → midday:refuge_4 → afternoon:house_2 → evening:house_2
  - 12380: early:house_2 → late:open → midday:open → afternoon:open → evening:open
  - 12386: early:house_1 → late:house_1 → midday:open → afternoon:house_1 → evening:house_1
  - 12395: early:open → late:open → midday:open → afternoon:house_1 → evening:open
  - 12407: early:house_2 → late:open → midday:open → afternoon:house_2 → evening:house_2

**2026-07-04** — July-4th fireworks ~21:00 (rest-window edge); refuge_4 burrow active
  - 12378: early:house_2 → late:house_2 → midday:refuge_4 → afternoon:refuge_4 → evening:house_2
  - 12380: early:open → late:house_1 → midday:open → afternoon:open → evening:house_2
  - 12386: early:open → late:open → midday:open → afternoon:refuge_4 → evening:open
  - 12395: early:house_2 → late:open → midday:refuge_4 → afternoon:refuge_4 → evening:house_1
  - 12407: early:house_2 → late:open → midday:open → afternoon:house_2 → evening:house_2

**2026-07-05** — refuge_4 burrow active
  - 12378: early:open → late:open → midday:open → afternoon:refuge_4 → evening:open
  - 12380: early:open → late:open → midday:open → afternoon:open → evening:open
  - 12386: early:house_1 → late:open → midday:refuge_4 → afternoon:refuge_4 → evening:open
  - 12395: early:open → late:open → midday:open → afternoon:house_2 → evening:house_1
  - 12407: early:open → late:house_2 → midday:house_2 → afternoon:house_2 → evening:house_2

**2026-07-06** — rain overnight; refuge_4 burrow active
  - 12378: early:house_1 → late:house_1 → midday:open → afternoon:house_1 → evening:house_1
  - 12380: early:open → late:house_1 → midday:open → afternoon:house_1 → evening:house_1
  - 12386: early:open → late:refuge_4 → midday:refuge_4 → afternoon:open → evening:open
  - 12395: early:house_2 → late:house_2 → midday:house_2 → afternoon:open → evening:open
  - 12407: early:house_2 → late:house_2 → midday:house_2 → afternoon:house_2 → evening:open

**2026-07-07** — refuge_4 (burrow) REMOVED ~13:00 — burrow window ends
  - 12378: early:open → late:house_1 → midday:open → afternoon:house_2 → evening:house_2
  - 12380: early:open → late:open → midday:open → afternoon:house_1 → evening:open
  - 12386: early:house_1 → late:open → midday:open → afternoon:house_2 → evening:house_2
  - 12395: early:open → late:house_2 → midday:open → afternoon:house_2 → evening:house_2
  - 12407: early:house_2 → late:house_2 → midday:open → afternoon:house_2 → evening:house_2

**2026-07-08** — no field note
  - 12378: early:open → late:open → midday:open → afternoon:open → evening:house_2
  - 12380: early:house_1 → late:house_1 → midday:house_1 → afternoon:house_2 → evening:house_2
  - 12386: early:house_1 → late:house_1 → midday:open → afternoon:open → evening:open
  - 12395: early:house_2 → late:house_2 → midday:open → afternoon:house_2 → evening:house_2
  - 12407: early:open → late:house_1 → midday:open → afternoon:open → evening:house_2

Read: a within-day sequence that changes ROI across windows is a candidate within-day relocation; a constant ROI is within-day site fidelity.

## Q2/Q4 — Relocation vs temperature / time-of-day; midday convergence

Per (day, window): rest-zone entropy across animals (low = converged to few sites), max animals sharing one shelter, and mean outside temp:

```
     night             window  n_in_shelter  house_1_count  house_2_count  max_shelter_share  zone_entropy_bits  mean_temp_c
2026-06-28 evening_transition             5              5              0                  5               0.00        25.12
2026-06-29      early_morning             0              0              0                  0               0.97        17.48
2026-06-29       late_morning             5              5              0                  5               0.00        26.17
2026-06-29        midday_heat             2              2              0                  2               0.97        29.39
2026-06-29          afternoon             2              0              2                  2               0.97        30.13
2026-06-29 evening_transition             2              0              2                  2               0.97        26.66
2026-06-30      early_morning             5              5              0                  5               0.00        22.13
2026-06-30       late_morning             3              2              1                  2               0.97        28.14
2026-06-30        midday_heat             0              0              0                  0               0.00        31.64
2026-06-30          afternoon             2              1              1                  1               1.52        31.57
2026-06-30 evening_transition             3              2              1                  2               0.97        27.47
2026-07-01      early_morning             5              5              0                  5               0.00        25.12
2026-07-01       late_morning             4              4              0                  4               0.72        31.45
2026-07-01        midday_heat             2              2              0                  2               0.97        33.58
2026-07-01          afternoon             1              0              1                  1               0.72        33.69
2026-07-01 evening_transition             2              1              1                  1               0.97        26.28
2026-07-02      early_morning             5              4              1                  4               0.00        22.84
2026-07-02       late_morning             4              4              0                  4               0.72        31.32
2026-07-02        midday_heat             1              1              0                  1               0.72        33.62
2026-07-02          afternoon             1              1              0                  1               0.72        35.09
2026-07-02 evening_transition             4              1              1                  2               0.72        31.44
2026-07-03      early_morning             3              1              2                  2               0.97        24.92
2026-07-03       late_morning             2              2              0                  2               0.97        30.96
2026-07-03        midday_heat             0              0              0                  0               0.72        32.43
2026-07-03          afternoon             4              2              2                  2               0.72        26.67
2026-07-03 evening_transition             4              1              2                  2               0.72        26.58
2026-07-04      early_morning             3              0              3                  3               0.97        22.44
2026-07-04       late_morning             2              1              1                  1               0.97        26.57
2026-07-04        midday_heat             1              0              0                  1               1.52        27.94
2026-07-04          afternoon             1              0              1                  1               1.37        28.51
2026-07-04 evening_transition             5              1              3                  3               0.00        23.66
2026-07-05      early_morning             1              1              0                  1               0.72        19.94
2026-07-05       late_morning             1              0              1                  1               0.72        24.94
2026-07-05        midday_heat             1              0              1                  1               1.37        26.49
2026-07-05          afternoon             2              0              2                  2               1.52        25.86
2026-07-05 evening_transition             2              1              1                  1               0.97        21.50
2026-07-06      early_morning             3              1              2                  2               0.97        20.92
2026-07-06       late_morning             4              2              2                  2               0.72        22.91
2026-07-06        midday_heat             2              0              2                  2               1.52        23.96
2026-07-06          afternoon             3              2              1                  2               0.97        22.60
2026-07-06 evening_transition             3              2              0                  2               0.97        20.55
2026-07-07      early_morning             2              1              1                  1               0.97        18.72
2026-07-07       late_morning             3              1              2                  2               0.97        20.91
2026-07-07        midday_heat             1              0              0                  1               0.72        25.41
2026-07-07          afternoon             5              1              4                  4               0.00        24.99
2026-07-07 evening_transition             4              0              4                  4               0.72        24.63
2026-07-08      early_morning             4              2              1                  2               0.72        18.39
2026-07-08       late_morning             4              3              1                  3               0.72        25.37
2026-07-08        midday_heat             2              1              0                  1               0.97        28.55
2026-07-08          afternoon             2              0              2                  2               0.97        30.14
2026-07-08 evening_transition             4              0              4                  4               0.72        28.09
```

Relocation events by day/kind:
```
     night           kind  n_events
2026-06-29 shelter_switch         2
2026-06-29    zone_change         6
2026-06-30 shelter_switch         5
2026-06-30    zone_change         4
2026-07-01   displacement         2
2026-07-01 shelter_switch         4
2026-07-01    zone_change         2
2026-07-02   displacement         3
2026-07-02 shelter_switch         1
2026-07-02    zone_change         3
2026-07-03   displacement         2
2026-07-03 shelter_switch         3
2026-07-03    zone_change         6
2026-07-04   displacement         2
2026-07-04 shelter_switch         1
2026-07-04    zone_change         4
2026-07-05 shelter_switch         3
2026-07-05    zone_change         4
2026-07-06    zone_change         2
2026-07-07 shelter_switch         4
2026-07-08 shelter_switch         3
```

**Observed within-day pattern (computed, descriptive over 11 days):**
  - 2026-06-28: peak shelter convergence in **evening_transition**; at the 12:00–15:00 heat peak rest sites **n/a (few in-shelter windows)** (vs late-morning).
  - 2026-06-29: peak shelter convergence in **late_morning**; at the 12:00–15:00 heat peak rest sites **DISPERSED (entropy rose)** — 2 of 5 in a shelter at the heat peak (vs late-morning).
  - 2026-06-30: peak shelter convergence in **early_morning**; at the 12:00–15:00 heat peak rest sites **CONVERGED (entropy fell)** — but all animals are OUT of shelters (open field) at the heat peak (vs late-morning).
  - 2026-07-01: peak shelter convergence in **early_morning**; at the 12:00–15:00 heat peak rest sites **DISPERSED (entropy rose)** — 2 of 5 in a shelter at the heat peak (vs late-morning).
  - 2026-07-02: peak shelter convergence in **early_morning**; at the 12:00–15:00 heat peak rest sites **unchanged** — 1 of 5 in a shelter at the heat peak (vs late-morning).
  - 2026-07-03: peak shelter convergence in **afternoon**; at the 12:00–15:00 heat peak rest sites **CONVERGED (entropy fell)** — but all animals are OUT of shelters (open field) at the heat peak (vs late-morning).
  - 2026-07-04: peak shelter convergence in **evening_transition**; at the 12:00–15:00 heat peak rest sites **DISPERSED (entropy rose)** — 1 of 5 in a shelter at the heat peak (vs late-morning).
  - 2026-07-05: peak shelter convergence in **early_morning**; at the 12:00–15:00 heat peak rest sites **DISPERSED (entropy rose)** — 1 of 5 in a shelter at the heat peak (vs late-morning).
  - 2026-07-06: peak shelter convergence in **late_morning**; at the 12:00–15:00 heat peak rest sites **DISPERSED (entropy rose)** — 2 of 5 in a shelter at the heat peak (vs late-morning).
  - 2026-07-07: peak shelter convergence in **afternoon**; at the 12:00–15:00 heat peak rest sites **CONVERGED (entropy fell)** — 1 of 5 in a shelter at the heat peak (vs late-morning).
  - 2026-07-08: peak shelter convergence in **early_morning**; at the 12:00–15:00 heat peak rest sites **DISPERSED (entropy rose)** — 2 of 5 in a shelter at the heat peak (vs late-morning).
  - House_1→house_2 shelter switches landing at/after the heat peak: 2026-06-29/12386, 2026-06-29/12407, 2026-06-30/12380, 2026-06-30/12386, 2026-06-30/12407, 2026-07-01/12380, 2026-07-01/12407, 2026-07-02/12386, 2026-07-03/12380, 2026-07-04/12380, 2026-07-05/12395, 2026-07-07/12378, 2026-07-07/12380, 2026-07-07/12386, 2026-07-08/12380, 2026-07-08/12386, 2026-07-08/12407 — a **candidate temperature-linked** midday relocation (NOT proof; house_2 is not verified cooler).

**Cross-day summary (the actual multi-day pattern):** on 9/10 days with both windows present, FEWER animals are in a shelter at the 12:00-15:00 heat peak than in late morning (06-29, 06-30, 07-01, 07-02, 07-03, 07-04, 07-06, 07-07, 07-08) — i.e. the late-morning shelter aggregation tends to **thin out / disperse at the heat peak** (rats move to house_2 and/or the open field), rather than pile deeper into one shelter. This is the repeated, candidate **temperature-linked** signature; it is DESCRIPTIVE (outside-air-temp proxy, no shelter thermistor) and does NOT establish causation, nor is house_2 verified cooler (inch frame).

## Q5/Q6 — 6/30 convergence to house_1: thermal/wet, social, habit, or measurement?

- 6/30 mean dropout 0.00 vs 6/29 0.00 — if comparable, the convergence is not merely missing data.

- Candidate interpretations (not mutually exclusive): **wet-day convergence** (rain ~17:30 + AM condensation), **thermal** (hottest day), **social aggregation** (co-location beyond site availability), vs **individual habit** (house_1 is the baseline/most-common site for most animals anyway). WISER cannot separate sleep state or true shelter microclimate — that needs shelter-temperature / ephys. CV corroborates only the visible shelter-resident periods (lower bound; 2026-07-06 reconciliation).

## Direct answers

1. **Across-day relocation:** see Stage A `rest_site_stability.csv` tiers (`analyze_daytime_sleep_site.py`) — over the full 8-day window ALL 5 animals switch house_1↔house_2 at least once, but at **heterogeneous rates** (12407 nearly every day; 12378/12380/12386 mostly house_1-faithful with late/early switches). The 3-day 'only 12386 & 12407' read was a small-sample artifact.
2. **Within-day house_1↔house_2 switching is common, not rare:** 26 within-day shelter-switch events over 11 days, involving 12378, 12380, 12386, 12395, 12407 animals — i.e. broader than the 2 animals seen across-day. Within-day site change is the norm; across-day *identity* change is the rarer signal.
3. **Within-day moves:** see the per-day sequences above (ROI change across windows), excluding refuge_4 burrow reads (flagged above).
4. **Temperature regularity:** reported as entropy/share vs window+temp — descriptive over 11 days; labelled temperature-**linked** at most (outside-air proxy).
5. **Heat-peak dispersal:** the repeated signature is the late-morning shelter aggregation THINNING at the midday heat peak (see the cross-day summary above), quantified with the dropout guard so it is not a missing-data artifact.
6. **Best interpretation:** candidate / measurement-limited — WISER supports site-level within-day movement and repeated midday shelter-dispersal; thermal vs social vs habit cannot be separated without a shelter thermistor / ephys, and the inch frame is unverified (house_2 not confirmed cooler).


*Figures + CSVs: `D:\Field2026_analysis_out\direction3_temperature_relocation_20260709_1143`.*
