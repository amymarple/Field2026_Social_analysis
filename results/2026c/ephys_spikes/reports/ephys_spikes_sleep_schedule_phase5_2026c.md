# Internal sleep schedule — Phase 5: do the animals enter REM in sync? (cohort 2026c)

Plan Amendment 7 (written before results). Driver `ephys/sleep_schedule.py phase5` → `ephys/sleep_sync.py` (commit 3b38a12+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_schedule_phase5_20261008_1449`. **Technical ledger; no claim audit yet.**

## Definitions

```
Phase 5 of the internal-schedule analysis: do the animals enter REM in sync? (plan Amendment 7, written before results)
Called by `python ephys/sleep_schedule.py phase5`.

Definitions (FINAL 1-s states on one absolute field-PC timeline per animal, cut at 09-11 19:40; WISER zone per second from
the default tracks: house_1 / house_2 (wiser_rois.json + 14 in) / field):
  co-located     two animals in the same house at that second (both zone house_1 or both house_2).
  far            the other animal is somewhere else (other house or field) while both zones are known.
  REM onset      a REM bout that starts after >= 60 s of NREM.
  per NREM step of animal B (time t = bout start + elapsed):
    n_mates      co-located other animals with a known state; mates_asleep = their share in NREM or REM (social context,
                 in the BASE model so that huddling alone cannot produce the effect);
    mate_on60    a co-located animal had a REM onset in (t - 60, t];   mate_rem: a co-located animal is in REM at t;
    far_on60, far_rem  the same for animals that are elsewhere (the natural control).
  held out       forward chaining (as Phase 2): S0 = M2t + n_mates + mates_asleep; S_mate = S0 + mate_on60 + mate_rem;
                 S_far = S0 + far_on60 + far_rem. Full-fit REM-vs-stay coefficients per SD; per-animal signs.
  descriptive    among B's NREM steps in a house with >= 1 asleep mate: P(REM in the next 10 s) with vs without a mate
                 onset in the last 60 s, within strata of B's own total NREM since its last REM (weighted ratio); and the
                 share of B's REM seconds during which a co-located asleep mate is also in REM vs during B's NREM seconds.
```

## Held out: do a mate's REM onset / REM add to predicting this animal's REM entry?

| comparison | subset | n_steps | n_rem | delta_pct | ci_lo_pct | ci_hi_pct | folds_better | folds | animals_better | animals | holds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S_mate vs S0 | co-located mates | 126200 | 2588 | 0.085 | 0.038 | 0.144 | 2 | 15 | 0 | 6 | False |
| S_far vs S0 | animals elsewhere (control) | 126200 | 2588 | 0.014 | -0.012 | 0.04 | 5 | 15 | 2 | 6 | False |

Full-fit coefficients (per SD; REM vs stay, Wake vs stay) and per-animal signs:

| term | REM_vs_stay | Wake_vs_stay | animals_REM_coef_positive | animals |
|---|---|---|---|---|
| mate_on60 | -0.002 | -0.003 | 3 | 6 |
| mate_rem | 0.005 | 0.032 | 4 | 6 |
| far_on60 | -0.016 | -0.02 | 1 | 6 |
| far_rem | 0.003 | 0.014 | 3 | 6 |

## Descriptive: REM-entry hazard with vs without the cue, within strata of the animal's own NREM since REM

| cue | steps_with_cue | steps_without | hazard_with | hazard_without_same_strata | weighted_ratio |
|---|---|---|---|---|---|
| mate_on60 | 21394 | 124529 | 0.0258 | 0.0225 | 1.1008 |
| mate_rem | 45569 | 100354 | 0.0262 | 0.0218 | 1.1221 |
| far_on60 | 12358 | 133565 | 0.0283 | 0.0238 | 1.2511 |
| far_rem | 26240 | 119683 | 0.0291 | 0.0234 | 1.2851 |

## Simultaneous REM: P(co-located asleep mate in REM | this animal in REM) vs | in NREM

| B | A | B_REM_s | p_A_REM_given_B_REM | p_A_REM_given_B_NREM | ratio |
|---|---|---|---|---|---|
| SF07 | SF08 | 19053 | 0.1631 | 0.1711 | 0.9536 |
| SF07 | SF09 | 34472 | 0.1621 | 0.1502 | 1.0793 |
| SF07 | SF10 | 22485 | 0.2008 | 0.1638 | 1.2256 |
| SF07 | SF11 | 16044 | 0.219 | 0.1772 | 1.2363 |
| SF07 | SF12 | 11506 | 0.2328 | 0.1493 | 1.5592 |
| SF08 | SF07 | 25789 | 0.1205 | 0.1267 | 0.9512 |
| SF08 | SF09 | 23427 | 0.1798 | 0.1415 | 1.2702 |
| SF08 | SF10 | 37741 | 0.2297 | 0.1663 | 1.3815 |
| SF08 | SF11 | 5435 | 0.2447 | 0.1214 | 2.0164 |
| SF08 | SF12 | 44389 | 0.1914 | 0.1833 | 1.0439 |
| SF09 | SF07 | 36292 | 0.154 | 0.1426 | 1.0801 |
| SF09 | SF08 | 20862 | 0.2019 | 0.1599 | 1.263 |
| SF09 | SF10 | 22338 | 0.203 | 0.168 | 1.2085 |
| SF09 | SF11 | 22460 | 0.1718 | 0.1895 | 0.9069 |
| SF09 | SF12 | 13361 | 0.1793 | 0.1566 | 1.1448 |
| SF10 | SF07 | 31239 | 0.1445 | 0.1164 | 1.2415 |
| SF10 | SF08 | 37106 | 0.2336 | 0.1694 | 1.3795 |
| SF10 | SF09 | 29063 | 0.156 | 0.1278 | 1.2208 |
| SF10 | SF11 | 10680 | 0.2295 | 0.1265 | 1.8148 |
| SF10 | SF12 | 38950 | 0.1958 | 0.1714 | 1.1425 |
| SF11 | SF07 | 20613 | 0.1705 | 0.1363 | 1.251 |
| SF11 | SF08 | 5338 | 0.2492 | 0.1239 | 2.0104 |
| SF11 | SF09 | 24843 | 0.1553 | 0.1716 | 0.905 |
| SF11 | SF10 | 8872 | 0.2763 | 0.1565 | 1.7653 |
| SF11 | SF12 | 6181 | 0.1836 | 0.1228 | 1.4948 |
| SF12 | SF07 | 17180 | 0.1559 | 0.0965 | 1.6153 |
| SF12 | SF08 | 42811 | 0.1984 | 0.1902 | 1.0435 |
| SF12 | SF09 | 16325 | 0.1467 | 0.1275 | 1.1505 |
| SF12 | SF10 | 38535 | 0.1979 | 0.1733 | 1.1421 |
| SF12 | SF11 | 6132 | 0.1851 | 0.1239 | 1.4939 |

