# Sleep-behaviour explore — W: the long-wake memory term (cohort 2026c)

Plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) §14 Amendment 6 (rules written before results). Driver `ephys/sleep_perturb.py runW` (commit 0ee77a0+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_explore_W_20261010_1527`; 100 replicates; runtime 16 min. **Technical ledger.**

## Reading (main session, 2026-10-10; claim #64; #6b, #60 updated)

**Question (plan §14):** does a long-wake memory — the last wake ≥ 7 min, carried to the first REM, and its interaction
with darkness — improve the count model and absorb the evening-round first-REM delay (#60)?

**Short answer.** No. The term adds no held-out gain on either scoring. Its fitted direction is the night ramp's: at
night a longer last long wake lowers REM entry (standardised −0.22 on both scorings). With it, FINAL's evening latency
falls inside the simulated range (it was at the edge), while pass2med's stays clearly above. By the plan's reading
(W1 fail): there is no general long-wake memory in the transitions, and #60 goes to the LFP stage (step L2(a)).

- **W1:**
  - B-full + {ℓ_LW, ℓ_LW × dark} vs B-full: −0.016 % [−0.162, +0.093], 3/6 (FINAL); −0.031 % [−0.113, +0.035], 5/6
    (pass2med).
  - ℓ_LW alone: +0.061 % (FINAL), +0.012 % (pass2med).
  - 21–23 % of the NREM steps carry a nonzero memory.
- **W2 (i) evening, NREM-clock latency after the first NREM in the house:**
  - FINAL 22.9 min vs 13.1–23.4 (+ LW) and 13.2–23.8 (+ LW + A): inside (before W: ≤ 21.0 / 22.3);
  - pass2med 24.1 vs ≤ 17.3 / 19.6: still above.
- **W2 (ii) morning:** inside on both.
- **W2 (iii):** Step E's checks 13/14 (FINAL) and 14/14 (pass2med), unchanged.
- **What it means:**
  - The night ramp (#6b) is not a separate memory that predicts NREM endings beyond the count, the preceding wake and
    the clock.
  - #60 remains on fixed thresholds (pass2med). It goes to the LFP stage: pre-transition depth (L2(a)) and early theta
    scored as NREM (L2(b)).
  - The behaviour stage closes here (Fable plateau audit).

## Definitions

```
Part W of the sleep-behaviour explore (plan §14, Amendment 6, written before results; the last behaviour-level term
before the LFP stage, after the Fable plateau audit): a long-wake memory — does it absorb the night ramp (#6b) and the
evening-round first-REM delay (#60)?

Usage:  python ephys/sleep_perturb.py runW [--scorings final pass2med] [--reps 100] [--workers 6]

Definitions:
  LW         at a NREM bout: the length (s) of the last WAKE bout >= 420 s in the record if no REM has occurred since it
             ended, else 0; unchanged over unknown runs (sleep_sim.lw_feature). Terms: l_lw = ln(1 + LW) and l_lw x dark,
             linear (z-scored on the training data) on all three logits of B-full (stay / REM / WAKE).
  W1         forward-chained held-out log-loss (sleep_model.run_folds; folds 1.., as Step B): B-full + {l_lw, l_lw x dark}
             vs B-full (and B-full + l_lw alone); Delta % with a fold bootstrap CI; animals better. Pass = CI < 0 and >= 5/6
             on both scorings. Full-data standardised coefficients reported (REM vs stay, WAKE vs stay).
  W2         sleep_sim with both terms (a forced wake >= 420 s sets LW, a REM bout resets it):
             (i)  part H's conditional simulation from the first NREM after the house entry (entry times from part H's
                  house_entries.csv), base fitted with the post-round 3 h masked, without and with part P's arousal A
                  (cross-fitted); evening L_N' (NREM clock) inside the simulated 95 % range on both scorings;
             (ii) the morning stays inside;
             (iii) Step E's checks (full-data fit, 100 replicates, Step E tolerances) >= 13/14 per scoring.
```

## Verdicts

| scores | part | pass | numbers |
|---|---|---|---|
| final | W1 | False | Delta -0.016 % [-0.162, +0.093], 3/6, folds 11/15 |
| final | W2 (i) evening L_N' inside | True | conditional, base + LW: obs 22.9 vs 13.1-23.4 (inside); conditional, base + LW + A: obs 22.9 vs 13.2-23.8 (inside) |
| final | W2 (ii) morning L_N' inside | True | conditional, base + LW: obs 11.8 vs 11.4-16.2 (inside); conditional, base + LW + A: obs 11.8 vs 11.0-16.3 (inside) |
| final | W2 (iii) Step E checks | True | 13/14 |
| pass2med | W1 | False | Delta -0.031 % [-0.113, +0.035], 5/6, folds 11/15 |
| pass2med | W2 (i) evening L_N' inside | False | conditional, base + LW: obs 24.1 vs 9.9-17.3 (above); conditional, base + LW + A: obs 24.1 vs 10.1-19.6 (above) |
| pass2med | W2 (ii) morning L_N' inside | True | conditional, base + LW: obs 11.8 vs 9.2-12.9 (inside); conditional, base + LW + A: obs 11.8 vs 8.9-12.7 (inside) |
| pass2med | W2 (iii) Step E checks | True | 14/14 |

## W1: held-out comparison

| scores | comparison | subset | n_steps | n_rem | delta_pct | ci_lo_pct | ci_hi_pct | folds_better | folds | animals_better | animals | holds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| final | B+lw+lw_dark vs B | all NREM steps | 122735 | 2544 | -0.0162 | -0.1617 | 0.0933 | 11 | 15 | 3 | 6 | False |
| final | B+lw vs B | all NREM steps | 122735 | 2544 | 0.0608 | -0.1075 | 0.1966 | 8 | 15 | 0 | 6 | False |
| pass2med | B+lw+lw_dark vs B | all NREM steps | 123304 | 2666 | -0.0313 | -0.1129 | 0.0354 | 11 | 15 | 5 | 6 | False |
| pass2med | B+lw vs B | all NREM steps | 123304 | 2666 | 0.0116 | -0.0475 | 0.0553 | 9 | 15 | 2 | 6 | False |

Full-data standardised coefficients:

| scores | term | share_steps_lw_gt0 | REM_vs_stay | WAKE_vs_stay |
|---|---|---|---|---|
| final | l_lw | 0.226 | -0.1348 | 0.0133 |
| final | l_lw_dark | 0.226 | -0.2228 | -0.1139 |
| pass2med | l_lw | 0.2134 | 0.0013 | -0.0114 |
| pass2med | l_lw_dark | 0.2134 | -0.228 | -0.1039 |

## W2 (i) / (ii): the first REM after the house entry, simulated with the term

| scores | kind | variant | stat | observed | sim_mean | sim_2.5% | sim_97.5% | side | rounds |
|---|---|---|---|---|---|---|---|---|---|
| final | morning | conditional, base + LW | Ls'_KM_median_min | 15.0 | 16.75 | 13.37 | 19.74 | inside | 50 |
| final | morning | conditional, base + LW | LN'_KM_median_min | 11.83 | 13.74 | 11.39 | 16.16 | inside | 50 |
| final | morning | conditional, base + LW + A | Ls'_KM_median_min | 15.0 | 17.28 | 13.99 | 20.67 | inside | 50 |
| final | morning | conditional, base + LW + A | LN'_KM_median_min | 11.83 | 13.82 | 11.04 | 16.25 | inside | 50 |
| final | evening | conditional, base + LW | Ls'_KM_median_min | 58.13 | 49.18 | 22.62 | 95.54 | inside | 44 |
| final | evening | conditional, base + LW | LN'_KM_median_min | 22.92 | 18.01 | 13.14 | 23.4 | inside | 44 |
| final | evening | conditional, base + LW + A | Ls'_KM_median_min | 58.13 | 54.06 | 25.38 | 121.72 | inside | 44 |
| final | evening | conditional, base + LW + A | LN'_KM_median_min | 22.92 | 18.17 | 13.17 | 23.83 | inside | 44 |
| pass2med | morning | conditional, base + LW | Ls'_KM_median_min | 15.43 | 13.21 | 10.86 | 16.02 | inside | 50 |
| pass2med | morning | conditional, base + LW | LN'_KM_median_min | 11.77 | 10.95 | 9.22 | 12.94 | inside | 50 |
| pass2med | morning | conditional, base + LW + A | Ls'_KM_median_min | 15.43 | 13.64 | 11.03 | 16.6 | inside | 50 |
| pass2med | morning | conditional, base + LW + A | LN'_KM_median_min | 11.77 | 10.89 | 8.93 | 12.74 | inside | 50 |
| pass2med | evening | conditional, base + LW | Ls'_KM_median_min | 73.78 | 30.0 | 14.55 | 62.42 | above | 44 |
| pass2med | evening | conditional, base + LW | LN'_KM_median_min | 24.05 | 13.78 | 9.91 | 17.34 | above | 44 |
| pass2med | evening | conditional, base + LW + A | Ls'_KM_median_min | 73.78 | 33.28 | 15.49 | 72.03 | above | 44 |
| pass2med | evening | conditional, base + LW + A | LN'_KM_median_min | 24.05 | 14.2 | 10.08 | 19.6 | above | 44 |

## W2 (iii): Step E's checks with the term

| scores | metric | observed | sim_mean | rel_diff | tolerance | pass |
|---|---|---|---|---|---|---|
| final | rem_h_per_24h | 1.6942 | 1.6951 | 0.0005 | 0.25 | True |
| final | nrem_h_per_24h | 9.4636 | 9.4078 | -0.0059 | 0.1 | True |
| final | sd_rem_daily | 0.3416 | 0.3434 | 0.0053 | 0.25 | True |
| final | sd_nrem_daily | 1.1026 | 1.003 | -0.0903 | 0.25 | True |
| final | rem_share_light | 0.1737 | 0.1745 | 0.0046 | 0.2 | True |
| final | rem_share_dark | 0.0682 | 0.0733 | 0.0747 | 0.2 | True |
| final | rem_per_h_nrem_light | 11.4096 | 11.8521 | 0.0388 | 0.2 | True |
| final | rem_per_h_nrem_dark | 4.0351 | 4.4618 | 0.1058 | 0.2 | True |
| final | lat_med_light_2-7 | 528.0 | 526.78 | -0.0023 | 0.25 | True |
| final | lat_med_light_7-30 | 779.0 | 745.04 | -0.0436 | 0.25 | True |
| final | lat_med_dark_2-7 | 899.0 | 990.33 | 0.1016 | 0.25 | True |
| final | lat_med_dark_7-30 | 810.0 | 1141.35 | 0.4091 | 0.25 | False |
| final | lat_med_dark_30-120 | 1370.0 | 1407.14 | 0.0271 | 0.25 | True |
| final | lat_med_dark_>=120 | 1593.0 | 1472.85 | -0.0754 | 0.25 | True |
| pass2med | rem_h_per_24h | 1.7679 | 1.7389 | -0.0164 | 0.25 | True |
| pass2med | nrem_h_per_24h | 9.7844 | 9.7649 | -0.002 | 0.1 | True |
| pass2med | sd_rem_daily | 0.2944 | 0.3224 | 0.095 | 0.25 | True |
| pass2med | sd_nrem_daily | 0.8998 | 0.9789 | 0.0878 | 0.25 | True |
| pass2med | rem_share_light | 0.1783 | 0.1743 | -0.0224 | 0.2 | True |
| pass2med | rem_share_dark | 0.0669 | 0.0692 | 0.0353 | 0.2 | True |
| pass2med | rem_per_h_nrem_light | 11.911 | 12.0114 | 0.0084 | 0.2 | True |
| pass2med | rem_per_h_nrem_dark | 4.2137 | 4.5321 | 0.0756 | 0.2 | True |
| pass2med | lat_med_light_2-7 | 535.0 | 548.55 | 0.0253 | 0.25 | True |
| pass2med | lat_med_light_7-30 | 771.0 | 684.32 | -0.1124 | 0.25 | True |
| pass2med | lat_med_dark_2-7 | 1115.0 | 968.31 | -0.1316 | 0.25 | True |
| pass2med | lat_med_dark_7-30 | 1316.0 | 1108.24 | -0.1579 | 0.25 | True |
| pass2med | lat_med_dark_30-120 | 1348.0 | 1299.67 | -0.0359 | 0.25 | True |
| pass2med | lat_med_dark_>=120 | 1486.0 | 1311.5 | -0.1174 | 0.25 | True |

