# Sleep-behaviour explore — Step D2 and Step E (ii) / (vi) on simulated records (cohort 2026c)

Plan §5 (rules written before results). Driver `ephys/sleep_sim_checks.py` (commit 0c8ddeb+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_explore_D2E_20261009_0805`; 100 replicates (carry-over: 3); runtime 0 min. **Technical ledger.**

## Definitions

```
Steps D2 and E (ii) / (vi) of the sleep-behaviour explore (plan implementation_plan/2026-10-08-sleep-behaviour-explore.md
§5, written before results), measured on records simulated by `ephys/sleep_sim.py` (the counter rules, conditional on
the observed long wakes and gaps; no REM-deficit variable).

Usage:  python ephys/sleep_sim_checks.py [--scorings pass2med final] [--reps 100] [--carry-reps 3] [--workers 8]

Definitions:
  D2      the morning-round REM payback slope (REM payback in the 1 h / 3 h after a battery round on the REM debt of the
          3 h before; phase x day baselines; day-demeaned; NREM debt partialled) measured with
          `sleep_explore_d.payback_from_records` on every simulated replicate. The model has no REM deficit, so a
          simulated slope near the observed one would mean the payback is produced by the counter seen through the clock.
          Pass for "a slow REM deficit exists" (plan Step D): the observed D1 slope > 0.2 (sleep_explore_d, Step D1) AND
          the simulated slope < 0.1 (mean over replicates; 95 % range reported). The D2 number is the row kind = morning,
          outcome = pay_rem, predictors = debt_rem, day_demeaned = True, B_h = 1 and 3 (phase x day baselines refitted on
          each simulated record set). The simulator is sleep_sim v2 (short wakes sampled with their next state), no H19.
  (vi)    the night -> next-day deviation slope with day fixed effects (`sleep_explore_d.budget_from_records`) on the
          simulated records; the model has no budget, so ~ 0 is expected; reported next to the observed value.
  (ii)    the carry-over curve (Phase 2 B1): post-wake NREM steps, held-out log-loss of C1 (pre-wake history: N_pre spline,
          wake before, REM_pre, anchor) vs R0 (current state only), by wake bin (< 40 s, 40-120 s, 2-7 min, 7-30 min,
          >= 30 min), forward chaining (Phase 2 `run_cv`), on the observed records and on `--carry-reps` simulated
          replicates. Pass: the simulated Delta has the observed sign in every bin where the observed CI excludes 0, and
          the same order of magnitude by bin (rank correlation reported).
```

## D2: the morning-round payback, observed vs simulated without a REM deficit

| kind | B_h | outcome | predictors | day_demeaned | scores | stat | observed | sim_mean | sim_2.5% | sim_97.5% | n_sim |
|---|---|---|---|---|---|---|---|---|---|---|---|
| evening | 1 | pay_nrem | debt_nrem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | slope | 0.173 | 0.2908 | 0.1577 | 0.4592 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | ci_lo | -0.0168 | 0.0241 | -0.0824 | 0.1518 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | ci_hi | 0.3629 | 0.5575 | 0.3794 | 0.7769 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | p | 0.0741 | 0.0499 | 0.0008 | 0.1634 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | animals_positive | 5.0 | 5.45 | 4.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | mean_x | -7.1583 | -7.3924 | -9.0596 | -6.1823 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | final | mean_y | -4.8748 | -3.3183 | -3.9236 | -2.7161 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | slope | 0.312 | 0.3205 | 0.1991 | 0.439 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | ci_lo | 0.1143 | 0.0674 | -0.0806 | 0.1972 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | ci_hi | 0.5097 | 0.5736 | 0.4036 | 0.7878 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | p | 0.002 | 0.0259 | 0.0 | 0.121 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | animals_positive | 6.0 | 5.46 | 4.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | mean_x | -7.6746 | -7.3169 | -8.7057 | -6.1048 | 100 |
| evening | 1 | pay_nrem | debt_nrem | False | pass2med | mean_y | -4.292 | -3.3946 | -3.9723 | -2.919 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | slope | -0.0047 | 0.0585 | -0.0976 | 0.1894 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | ci_lo | -0.1873 | -0.0851 | -0.2634 | 0.063 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | ci_hi | 0.178 | 0.202 | 0.0367 | 0.384 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | p | 0.96 | 0.3645 | 0.0046 | 0.9696 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | animals_positive | 4.0 | 3.76 | 1.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | mean_x | -7.1583 | -7.3924 | -9.0596 | -6.1823 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | final | mean_y | -4.8748 | -3.3183 | -3.9236 | -2.7161 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | slope | 0.0703 | 0.0947 | -0.0604 | 0.2382 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | ci_lo | -0.0643 | -0.0692 | -0.2762 | 0.0835 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | ci_hi | 0.2048 | 0.2587 | 0.0863 | 0.5245 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | p | 0.3061 | 0.2963 | 0.0009 | 0.8293 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | animals_positive | 4.0 | 4.19 | 2.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | mean_x | -7.6746 | -7.3169 | -8.7057 | -6.1048 | 100 |
| evening | 1 | pay_nrem | debt_nrem | True | pass2med | mean_y | -4.292 | -3.3946 | -3.9723 | -2.919 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | slope | 0.0329 | 0.0434 | -0.0725 | 0.1522 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | ci_lo | -0.0406 | -0.0493 | -0.1898 | 0.0432 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | ci_hi | 0.1064 | 0.1361 | 0.0208 | 0.3201 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | p | 0.3803 | 0.3518 | 0.0002 | 0.9186 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | animals_positive | 5.0 | 3.62 | 1.0 | 5.525 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem | debt_rem | False | final | mean_y | -0.7739 | -0.5063 | -0.8627 | -0.0871 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | slope | 0.0564 | 0.0394 | -0.0745 | 0.1461 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | ci_lo | 0.0136 | -0.0606 | -0.251 | 0.0517 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | ci_hi | 0.0992 | 0.1395 | 0.0148 | 0.2708 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | p | 0.0098 | 0.3347 | 0.0013 | 0.9076 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | animals_positive | 5.0 | 3.59 | 1.0 | 6.0 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem | debt_rem | False | pass2med | mean_y | -0.7055 | -0.451 | -0.8528 | -0.0081 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | slope | 0.0293 | 0.0094 | -0.1189 | 0.1426 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | ci_lo | -0.0591 | -0.092 | -0.2812 | 0.0028 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | ci_hi | 0.1176 | 0.1107 | -0.0052 | 0.3541 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | p | 0.5159 | 0.3971 | 0.0159 | 0.9343 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | animals_positive | 3.0 | 3.16 | 1.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem | debt_rem | True | final | mean_y | -0.7739 | -0.5063 | -0.8627 | -0.0871 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | slope | 0.0409 | 0.0092 | -0.1 | 0.1196 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | ci_lo | -0.0236 | -0.0975 | -0.2883 | 0.0168 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | ci_hi | 0.1053 | 0.116 | 0.0083 | 0.2869 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | p | 0.2138 | 0.4155 | 0.015 | 0.9601 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | animals_positive | 5.0 | 3.11 | 0.0 | 6.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem | debt_rem | True | pass2med | mean_y | -0.7055 | -0.451 | -0.8528 | -0.0081 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | slope | 0.0327 | 0.043 | -0.0718 | 0.1334 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | ci_lo | -0.0451 | -0.0462 | -0.1941 | 0.0462 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | ci_hi | 0.1106 | 0.1321 | 0.0148 | 0.3267 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | p | 0.4101 | 0.3307 | 0.0032 | 0.9246 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | animals_positive | 4.0 | 3.03 | 1.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | final | mean_y | -0.7739 | -0.5063 | -0.8627 | -0.0871 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | slope | 0.0412 | 0.0423 | -0.0632 | 0.1482 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_lo | -0.0081 | -0.0553 | -0.2282 | 0.0534 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_hi | 0.0904 | 0.1399 | 0.0181 | 0.289 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | p | 0.1012 | 0.359 | 0.0017 | 0.968 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals_positive | 4.0 | 2.98 | 0.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_y | -0.7055 | -0.451 | -0.8528 | -0.0081 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | slope | 0.014 | 0.0151 | -0.1127 | 0.1417 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | ci_lo | -0.0807 | -0.0905 | -0.2669 | 0.0163 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | ci_hi | 0.1087 | 0.1208 | -0.0018 | 0.3753 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | p | 0.772 | 0.41 | 0.0085 | 0.9539 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | animals_positive | 3.0 | 2.58 | 1.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | final | mean_y | -0.7739 | -0.5063 | -0.8627 | -0.0871 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | slope | 0.034 | 0.0196 | -0.1009 | 0.1371 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_lo | -0.0527 | -0.0902 | -0.2767 | 0.0306 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_hi | 0.1207 | 0.1294 | 0.0022 | 0.2923 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | p | 0.4422 | 0.4028 | 0.0088 | 0.9811 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals_positive | 4.0 | 2.75 | 0.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_y | -0.7055 | -0.451 | -0.8528 | -0.0081 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | n_windows | 16.0 | 18.46 | 15.0 | 22.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | clusters | 5.0 | 5.65 | 4.0 | 7.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | slope | 1.8553 | 0.0561 | -2.1177 | 2.5941 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | ci_lo | 0.0524 | -2.2981 | -6.1538 | 0.5887 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | ci_hi | 3.6582 | 2.4103 | -0.5044 | 6.0504 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | p | 0.0437 | 0.4641 | 0.0001 | 0.9625 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | animals_positive | 0.0 | 0.43 | 0.0 | 2.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | animals | 0.0 | 0.81 | 0.0 | 2.525 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | final | mean_y | -3.4585 | -0.792 | -11.023 | 12.6173 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | n_windows | 16.0 | 21.3 | 18.0 | 25.525 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | clusters | 4.0 | 6.45 | 5.0 | 8.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | slope | -1.6232 | -0.1214 | -2.0957 | 1.9572 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | ci_lo | -4.7147 | -2.0611 | -5.4513 | 0.8628 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | ci_hi | 1.4683 | 1.8182 | -0.5354 | 4.4833 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | p | 0.3034 | 0.4058 | 0.0004 | 0.9667 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | animals_positive | 0.0 | 0.92 | 0.0 | 3.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | animals | 0.0 | 1.77 | 0.0 | 4.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | False | pass2med | mean_y | 2.8424 | -0.6819 | -11.9167 | 12.2421 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | n_windows | 16.0 | 18.46 | 15.0 | 22.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | clusters | 5.0 | 5.65 | 4.0 | 7.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | slope | 1.6626 | 0.1926 | -2.2339 | 3.7236 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | ci_lo | -0.0817 | -2.371 | -7.1958 | 1.5533 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | ci_hi | 3.4069 | 2.7563 | -0.4483 | 8.6939 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | p | 0.0617 | 0.4194 | 0.0 | 0.9782 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | animals_positive | 0.0 | 0.5 | 0.0 | 2.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | animals | 0.0 | 0.81 | 0.0 | 2.525 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | final | mean_y | -3.4585 | -0.792 | -11.023 | 12.6173 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | n_windows | 16.0 | 21.3 | 18.0 | 25.525 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | clusters | 4.0 | 6.45 | 5.0 | 8.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | slope | -1.0557 | 0.0529 | -2.7669 | 2.6076 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | ci_lo | -2.8969 | -2.0679 | -5.1439 | 0.7513 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | ci_hi | 0.7854 | 2.1738 | -0.9722 | 5.6659 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | p | 0.2611 | 0.3951 | 0.0005 | 0.9826 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | animals_positive | 0.0 | 0.81 | 0.0 | 2.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | animals | 0.0 | 1.77 | 0.0 | 4.0 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem_dur | debt_rem | True | pass2med | mean_y | 2.8424 | -0.6819 | -11.9167 | 12.2421 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | slope | 0.0008 | 0.0502 | -0.0554 | 0.1483 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | ci_lo | -0.0589 | -0.0409 | -0.1375 | 0.0501 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | ci_hi | 0.0605 | 0.1413 | 0.0139 | 0.292 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | p | 0.9787 | 0.3107 | 0.0005 | 0.836 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | animals_positive | 2.0 | 3.88 | 1.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | final | mean_y | -0.7057 | -0.5103 | -0.9345 | -0.0964 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | slope | 0.0428 | 0.0481 | -0.0752 | 0.1541 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | ci_lo | 0.0197 | -0.0486 | -0.2008 | 0.0585 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | ci_hi | 0.0659 | 0.1447 | 0.0226 | 0.2857 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | p | 0.0003 | 0.3024 | 0.001 | 0.9347 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | animals_positive | 5.0 | 3.9 | 2.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem_n | debt_rem | False | pass2med | mean_y | -0.7141 | -0.4564 | -0.8595 | -0.0729 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | slope | -0.0081 | 0.0121 | -0.1071 | 0.1142 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | ci_lo | -0.0837 | -0.088 | -0.2312 | 0.0186 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | ci_hi | 0.0674 | 0.1122 | 0.0054 | 0.3159 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | p | 0.8331 | 0.4278 | 0.0049 | 0.9467 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | animals_positive | 3.0 | 3.19 | 1.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | final | mean_y | -0.7057 | -0.5103 | -0.9345 | -0.0964 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | slope | 0.0232 | 0.0099 | -0.1049 | 0.1076 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | ci_lo | -0.0462 | -0.0856 | -0.2372 | 0.0211 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | ci_hi | 0.0926 | 0.1053 | 0.0031 | 0.2419 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | p | 0.5128 | 0.4262 | 0.0136 | 0.9225 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | animals_positive | 4.0 | 3.17 | 1.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 1 | pay_rem_n | debt_rem | True | pass2med | mean_y | -0.7141 | -0.4564 | -0.8595 | -0.0729 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | slope | 0.1142 | 0.1677 | -0.0765 | 0.3657 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | ci_lo | -0.4535 | -0.3089 | -0.5137 | -0.1223 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | ci_hi | 0.6819 | 0.6443 | 0.3072 | 0.9272 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | p | 0.6934 | 0.4936 | 0.163 | 0.8783 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | animals_positive | 4.0 | 4.59 | 3.0 | 6.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | mean_x | -7.1583 | -7.3924 | -9.0596 | -6.1823 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | final | mean_y | -11.1202 | -9.4999 | -10.2434 | -8.7337 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | slope | 0.3054 | 0.2588 | 0.0362 | 0.4637 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | ci_lo | -0.2755 | -0.2705 | -0.5484 | -0.0152 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | ci_hi | 0.8863 | 0.788 | 0.409 | 1.0675 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | p | 0.3028 | 0.3747 | 0.0582 | 0.8764 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | animals_positive | 5.0 | 4.74 | 3.0 | 6.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | mean_x | -7.6746 | -7.3169 | -8.7057 | -6.1048 | 100 |
| evening | 3 | pay_nrem | debt_nrem | False | pass2med | mean_y | -10.9513 | -10.0527 | -10.7122 | -9.213 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | slope | 0.0125 | -0.0294 | -0.311 | 0.2013 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | ci_lo | -0.2435 | -0.3231 | -0.587 | -0.0294 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | ci_hi | 0.2686 | 0.2642 | -0.067 | 0.5127 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | p | 0.9235 | 0.5014 | 0.0059 | 0.9764 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | animals_positive | 3.0 | 2.7 | 1.0 | 4.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | mean_x | -7.1583 | -7.3924 | -9.0596 | -6.1823 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | final | mean_y | -11.1202 | -9.4999 | -10.2434 | -8.7337 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | slope | 0.0924 | 0.0627 | -0.1543 | 0.3701 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | ci_lo | -0.1686 | -0.2165 | -0.4654 | 0.06 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | ci_hi | 0.3535 | 0.3419 | 0.0838 | 0.6881 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | p | 0.4877 | 0.5228 | 0.0127 | 0.983 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | animals_positive | 4.0 | 3.46 | 2.0 | 6.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | mean_x | -7.6746 | -7.3169 | -8.7057 | -6.1048 | 100 |
| evening | 3 | pay_nrem | debt_nrem | True | pass2med | mean_y | -10.9513 | -10.0527 | -10.7122 | -9.213 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | slope | 0.0495 | 0.0145 | -0.1117 | 0.1137 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | ci_lo | -0.0242 | -0.0863 | -0.2818 | 0.0215 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | ci_hi | 0.1232 | 0.1152 | 0.015 | 0.2734 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | p | 0.1882 | 0.4213 | 0.0135 | 0.9087 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | animals_positive | 5.0 | 3.42 | 1.0 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem | debt_rem | False | final | mean_y | -1.4605 | -1.1394 | -1.5998 | -0.6748 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | slope | 0.0892 | 0.0123 | -0.1134 | 0.1296 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | ci_lo | 0.015 | -0.1021 | -0.3101 | 0.0419 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | ci_hi | 0.1634 | 0.1268 | 0.0048 | 0.2832 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | p | 0.0184 | 0.404 | 0.0029 | 0.9165 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | animals_positive | 5.0 | 3.31 | 1.0 | 6.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem | debt_rem | False | pass2med | mean_y | -1.402 | -1.1525 | -1.6045 | -0.6327 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | slope | 0.0385 | -0.0044 | -0.1568 | 0.1397 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | ci_lo | -0.068 | -0.12 | -0.3248 | 0.0094 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | ci_hi | 0.145 | 0.1111 | -0.0085 | 0.3732 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | p | 0.4784 | 0.4191 | 0.0113 | 0.9707 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | animals_positive | 4.0 | 2.86 | 0.475 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem | debt_rem | True | final | mean_y | -1.4605 | -1.1394 | -1.5998 | -0.6748 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | slope | 0.0633 | -0.0079 | -0.1624 | 0.1218 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | ci_lo | -0.0592 | -0.1288 | -0.3557 | 0.0037 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | ci_hi | 0.1858 | 0.1129 | -0.0081 | 0.2987 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | p | 0.3111 | 0.4495 | 0.0146 | 0.9628 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | animals_positive | 4.0 | 2.87 | 1.0 | 6.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem | debt_rem | True | pass2med | mean_y | -1.402 | -1.1525 | -1.6045 | -0.6327 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | slope | 0.0495 | 0.0138 | -0.0984 | 0.1121 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | ci_lo | -0.0253 | -0.0854 | -0.2637 | 0.0314 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | ci_hi | 0.1244 | 0.113 | 0.0074 | 0.2834 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | p | 0.1948 | 0.4271 | 0.0056 | 0.9511 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | animals_positive | 5.0 | 2.62 | 1.0 | 4.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | final | mean_y | -1.4605 | -1.1394 | -1.5998 | -0.6748 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | slope | 0.079 | 0.0148 | -0.11 | 0.1363 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_lo | -0.0133 | -0.098 | -0.2832 | 0.0519 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_hi | 0.1713 | 0.1275 | 0.0033 | 0.2891 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | p | 0.0934 | 0.4188 | 0.0003 | 0.8859 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals_positive | 4.0 | 2.75 | 0.0 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_y | -1.402 | -1.1525 | -1.6045 | -0.6327 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | slope | 0.0153 | -0.0001 | -0.1552 | 0.1394 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | ci_lo | -0.097 | -0.1193 | -0.3131 | 0.0059 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | ci_hi | 0.1277 | 0.1191 | -0.0013 | 0.3911 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | p | 0.7889 | 0.4525 | 0.0083 | 0.9508 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | animals_positive | 3.0 | 2.31 | 0.0 | 4.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | final | mean_y | -1.4605 | -1.1394 | -1.5998 | -0.6748 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | slope | 0.0466 | -0.0003 | -0.1563 | 0.1407 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_lo | -0.096 | -0.1235 | -0.3692 | 0.0112 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_hi | 0.1891 | 0.1228 | -0.0065 | 0.3343 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | p | 0.5219 | 0.4407 | 0.0232 | 0.9567 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals_positive | 2.0 | 2.46 | 0.475 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_y | -1.402 | -1.1525 | -1.6045 | -0.6327 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | n_windows | 19.0 | 22.84 | 19.0 | 28.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | clusters | 7.0 | 7.33 | 6.0 | 9.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | slope | 1.1839 | -0.0612 | -1.9343 | 1.632 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | ci_lo | -1.1118 | -2.0587 | -4.8887 | 0.1228 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | ci_hi | 3.4795 | 1.9362 | -0.5175 | 5.2963 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | p | 0.3121 | 0.4386 | 0.0016 | 0.9142 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | animals_positive | 1.0 | 0.97 | 0.0 | 2.525 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | animals | 1.0 | 1.91 | 0.0 | 4.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | final | mean_y | 3.5822 | 0.308 | -11.0981 | 13.8311 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | n_windows | 21.0 | 27.08 | 23.475 | 31.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | clusters | 7.0 | 8.21 | 7.0 | 9.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | slope | 0.4443 | -0.0384 | -2.0256 | 1.5242 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | ci_lo | -2.2903 | -1.7356 | -4.3528 | 0.264 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | ci_hi | 3.1789 | 1.6587 | -0.2765 | 3.3453 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | p | 0.7501 | 0.4505 | 0.0051 | 0.9598 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | animals_positive | 0.0 | 1.6 | 0.0 | 3.525 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | animals | 1.0 | 3.09 | 2.0 | 4.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | False | pass2med | mean_y | 8.8306 | -0.9892 | -10.7588 | 8.1668 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | n_windows | 19.0 | 22.84 | 19.0 | 28.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | clusters | 7.0 | 7.33 | 6.0 | 9.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | slope | 0.9849 | -0.1327 | -2.1745 | 2.7881 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | ci_lo | -0.4777 | -2.3177 | -6.2902 | 0.0409 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | ci_hi | 2.4475 | 2.0524 | -0.6783 | 6.8914 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | p | 0.1869 | 0.433 | 0.0001 | 0.9585 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | animals_positive | 0.0 | 0.98 | 0.0 | 2.525 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | animals | 1.0 | 1.91 | 0.0 | 4.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | final | mean_y | 3.5822 | 0.308 | -11.0981 | 13.8311 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | n_windows | 21.0 | 27.08 | 23.475 | 31.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | clusters | 7.0 | 8.21 | 7.0 | 9.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | slope | 0.4988 | 0.0729 | -1.838 | 2.3301 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | ci_lo | -2.2675 | -1.8665 | -5.0618 | 0.7117 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | ci_hi | 3.2651 | 2.0123 | -0.2477 | 4.8005 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | p | 0.7238 | 0.429 | 0.0023 | 0.9462 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | animals_positive | 0.0 | 1.55 | 0.0 | 3.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | animals | 1.0 | 3.09 | 2.0 | 4.0 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem_dur | debt_rem | True | pass2med | mean_y | 8.8306 | -0.9892 | -10.7588 | 8.1668 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | slope | 0.0062 | 0.0236 | -0.0851 | 0.1093 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | ci_lo | -0.0533 | -0.0732 | -0.2304 | 0.0212 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | ci_hi | 0.0656 | 0.1204 | 0.0269 | 0.2552 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | p | 0.8391 | 0.417 | 0.0097 | 0.941 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | animals_positive | 3.0 | 3.53 | 2.0 | 5.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | final | mean_y | -1.4616 | -1.1913 | -1.6925 | -0.8166 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | slope | 0.06 | 0.022 | -0.0982 | 0.1409 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | ci_lo | 0.0064 | -0.0862 | -0.2481 | 0.0527 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | ci_hi | 0.1137 | 0.1301 | 0.0048 | 0.2835 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | p | 0.0283 | 0.4367 | 0.0029 | 0.9859 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | animals_positive | 4.0 | 3.36 | 1.0 | 6.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem_n | debt_rem | False | pass2med | mean_y | -1.577 | -1.2329 | -1.6392 | -0.8283 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | slope | 0.0025 | 0.0018 | -0.1427 | 0.1261 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | ci_lo | -0.0851 | -0.1083 | -0.3274 | 0.0258 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | ci_hi | 0.09 | 0.1119 | -0.0146 | 0.3302 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | p | 0.9562 | 0.4376 | 0.006 | 0.9501 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | animals_positive | 3.0 | 3.04 | 1.0 | 5.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | mean_x | -3.6355 | -1.2567 | -2.522 | -0.1152 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | final | mean_y | -1.4616 | -1.1913 | -1.6925 | -0.8166 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | n_windows | 44.0 | 44.0 | 44.0 | 44.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | clusters | 9.0 | 9.0 | 9.0 | 9.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | slope | 0.0341 | -0.007 | -0.1394 | 0.0937 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | ci_lo | -0.0583 | -0.111 | -0.2887 | 0.0093 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | ci_hi | 0.1265 | 0.0971 | -0.0164 | 0.2391 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | p | 0.4692 | 0.4734 | 0.0165 | 0.9671 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | animals_positive | 5.0 | 2.95 | 1.0 | 5.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | mean_x | -2.4905 | -1.3581 | -2.5008 | -0.3031 | 100 |
| evening | 3 | pay_rem_n | debt_rem | True | pass2med | mean_y | -1.577 | -1.2329 | -1.6392 | -0.8283 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | slope | 0.1301 | 0.1009 | 0.0328 | 0.1572 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | ci_lo | -0.0074 | -0.0329 | -0.117 | 0.0299 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | ci_hi | 0.2676 | 0.2347 | 0.1565 | 0.3276 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | p | 0.0637 | 0.1823 | 0.01 | 0.6239 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | animals_positive | 5.0 | 4.75 | 3.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | mean_x | -7.6034 | -7.0557 | -7.9956 | -5.8043 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | final | mean_y | -6.674 | -5.8234 | -6.8977 | -5.0171 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | slope | 0.1627 | 0.1066 | 0.0401 | 0.1535 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | ci_lo | 0.0326 | -0.0262 | -0.0898 | 0.0398 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | ci_hi | 0.2928 | 0.2393 | 0.1529 | 0.2982 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | p | 0.0142 | 0.1521 | 0.0055 | 0.5066 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | animals_positive | 5.0 | 5.0 | 4.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | mean_x | -9.155 | -8.5999 | -9.364 | -7.7547 | 100 |
| morning | 1 | pay_nrem | debt_nrem | False | pass2med | mean_y | -7.611 | -6.4389 | -7.4162 | -5.5316 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | slope | 0.0455 | 0.0772 | -0.0374 | 0.1727 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | ci_lo | -0.1147 | -0.0968 | -0.2359 | 0.0299 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | ci_hi | 0.2056 | 0.2512 | 0.1024 | 0.3979 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | p | 0.578 | 0.411 | 0.017 | 0.9248 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | animals_positive | 5.0 | 3.74 | 2.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | mean_x | -7.6034 | -7.0557 | -7.9956 | -5.8043 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | final | mean_y | -6.674 | -5.8234 | -6.8977 | -5.0171 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | slope | 0.1669 | 0.129 | 0.0174 | 0.2405 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | ci_lo | -0.0051 | -0.0325 | -0.1738 | 0.1038 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | ci_hi | 0.3389 | 0.2906 | 0.1509 | 0.437 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | p | 0.0572 | 0.1874 | 0.0005 | 0.7154 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | animals_positive | 5.0 | 4.36 | 3.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | mean_x | -9.155 | -8.5999 | -9.364 | -7.7547 | 100 |
| morning | 1 | pay_nrem | debt_nrem | True | pass2med | mean_y | -7.611 | -6.4389 | -7.4162 | -5.5316 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | slope | 0.0866 | 0.0603 | -0.1493 | 0.3041 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | ci_lo | -0.0995 | -0.1694 | -0.4364 | 0.1092 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | ci_hi | 0.2728 | 0.2901 | 0.0508 | 0.6168 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | p | 0.3618 | 0.4514 | 0.0013 | 0.9656 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | animals_positive | 5.0 | 3.52 | 1.0 | 6.0 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem | debt_rem | False | final | mean_y | -2.3202 | -2.4151 | -3.1769 | -1.7349 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | slope | 0.3974 | 0.0321 | -0.212 | 0.3004 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | ci_lo | 0.23 | -0.184 | -0.53 | 0.1567 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | ci_hi | 0.5648 | 0.2483 | -0.0285 | 0.516 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | p | 0.0 | 0.4145 | 0.0004 | 0.9787 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | animals_positive | 6.0 | 3.21 | 1.0 | 5.525 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem | debt_rem | False | pass2med | mean_y | -2.8313 | -2.3951 | -3.0236 | -1.7494 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | slope | 0.0401 | 0.036 | -0.2044 | 0.3405 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | ci_lo | -0.1406 | -0.222 | -0.5251 | 0.0904 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | ci_hi | 0.2207 | 0.294 | 0.0346 | 0.6407 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | p | 0.6637 | 0.4693 | 0.0037 | 0.9772 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | animals_positive | 3.0 | 3.22 | 1.0 | 6.0 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem | debt_rem | True | final | mean_y | -2.3202 | -2.4151 | -3.1769 | -1.7349 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | slope | 0.3355 | 0.0048 | -0.2272 | 0.2746 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | ci_lo | 0.1753 | -0.2425 | -0.5879 | 0.0723 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | ci_hi | 0.4956 | 0.252 | -0.0336 | 0.5605 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | p | 0.0 | 0.4418 | 0.0015 | 0.9401 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | animals_positive | 5.0 | 3.05 | 1.0 | 5.525 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem | debt_rem | True | pass2med | mean_y | -2.8313 | -2.3951 | -3.0236 | -1.7494 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | slope | 0.0648 | 0.0429 | -0.1916 | 0.2877 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | ci_lo | -0.0607 | -0.1992 | -0.4765 | 0.0636 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | ci_hi | 0.1902 | 0.2851 | 0.047 | 0.6139 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | p | 0.3116 | 0.4743 | 0.0072 | 0.9735 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | animals_positive | 3.0 | 2.85 | 1.0 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | final | mean_y | -2.3202 | -2.4151 | -3.1769 | -1.7349 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | slope | 0.3742 | 0.0137 | -0.2247 | 0.2862 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_lo | 0.1675 | -0.2118 | -0.5685 | 0.1369 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_hi | 0.5808 | 0.2391 | -0.0199 | 0.4853 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | p | 0.0004 | 0.4283 | 0.0014 | 0.9759 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals_positive | 5.0 | 2.61 | 0.0 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_y | -2.8313 | -2.3951 | -3.0236 | -1.7494 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | slope | 0.0403 | 0.0282 | -0.2089 | 0.3324 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | ci_lo | -0.1487 | -0.231 | -0.5369 | 0.0682 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | ci_hi | 0.2292 | 0.2874 | 0.0157 | 0.6403 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | p | 0.676 | 0.4771 | 0.0041 | 0.9751 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | animals_positive | 3.0 | 2.73 | 1.0 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | final | mean_y | -2.3202 | -2.4151 | -3.1769 | -1.7349 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | slope | 0.3205 | 0.0067 | -0.2245 | 0.3022 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_lo | 0.1286 | -0.2432 | -0.6057 | 0.0883 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_hi | 0.5124 | 0.2566 | -0.0074 | 0.5459 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | p | 0.0011 | 0.4489 | 0.0029 | 0.9616 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals_positive | 3.0 | 2.49 | 0.475 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_y | -2.8313 | -2.3951 | -3.0236 | -1.7494 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | n_windows | 47.0 | 46.38 | 44.0 | 49.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | slope | -3.5402 | 0.0112 | -2.8577 | 2.7723 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | ci_lo | -8.5994 | -2.6786 | -6.6753 | 0.399 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | ci_hi | 1.5191 | 2.7009 | -0.6252 | 6.5878 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | p | 0.1702 | 0.4518 | 0.0039 | 0.9724 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | animals_positive | 2.0 | 3.09 | 1.0 | 5.525 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | animals | 6.0 | 5.94 | 5.0 | 6.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | final | mean_y | 8.911 | 1.3938 | -7.6178 | 12.1958 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | n_windows | 48.0 | 47.85 | 45.475 | 49.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | slope | 0.897 | -0.0419 | -2.226 | 2.477 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | ci_lo | -5.1683 | -2.3195 | -5.6645 | 0.2695 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | ci_hi | 6.9623 | 2.2357 | -0.2364 | 5.2514 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | p | 0.7719 | 0.484 | 0.0089 | 0.9598 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | animals_positive | 4.0 | 3.0 | 1.0 | 5.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | animals | 6.0 | 5.96 | 5.0 | 6.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | False | pass2med | mean_y | 6.9383 | 1.2236 | -7.3411 | 11.3787 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | n_windows | 47.0 | 46.38 | 44.0 | 49.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | slope | -2.9094 | 0.063 | -3.5513 | 4.4756 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | ci_lo | -8.2201 | -3.2128 | -7.4774 | 1.0021 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | ci_hi | 2.4012 | 3.3389 | -1.0119 | 8.5716 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | p | 0.2829 | 0.4246 | 0.0019 | 0.9454 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | animals_positive | 2.0 | 2.93 | 1.0 | 5.525 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | animals | 6.0 | 5.94 | 5.0 | 6.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | final | mean_y | 8.911 | 1.3938 | -7.6178 | 12.1958 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | n_windows | 48.0 | 47.85 | 45.475 | 49.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | slope | 0.3397 | 0.102 | -2.6183 | 2.5978 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | ci_lo | -7.9464 | -2.6443 | -6.2117 | 0.1611 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | ci_hi | 8.6259 | 2.8484 | -0.1918 | 6.1511 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | p | 0.936 | 0.4892 | 0.0242 | 0.9786 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | animals_positive | 4.0 | 2.96 | 1.0 | 5.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | animals | 6.0 | 5.96 | 5.0 | 6.0 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem_dur | debt_rem | True | pass2med | mean_y | 6.9383 | 1.2236 | -7.3411 | 11.3787 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | slope | 0.1271 | 0.0469 | -0.1356 | 0.2097 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | ci_lo | -0.0969 | -0.115 | -0.3565 | 0.0558 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | ci_hi | 0.3511 | 0.2088 | 0.0478 | 0.4175 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | p | 0.2661 | 0.4192 | 0.0021 | 0.9853 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | animals_positive | 4.0 | 3.29 | 1.0 | 5.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | final | mean_y | -1.8764 | -1.9533 | -2.496 | -1.4002 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | slope | 0.263 | 0.0279 | -0.1458 | 0.291 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | ci_lo | 0.148 | -0.1325 | -0.3815 | 0.1309 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | ci_hi | 0.378 | 0.1883 | 0.0009 | 0.4491 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | p | 0.0 | 0.43 | 0.0004 | 0.9835 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | animals_positive | 5.0 | 3.3 | 0.0 | 6.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem_n | debt_rem | False | pass2med | mean_y | -2.3951 | -1.984 | -2.4229 | -1.496 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | slope | 0.0636 | 0.0313 | -0.1542 | 0.2001 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | ci_lo | -0.1687 | -0.1536 | -0.3694 | 0.0588 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | ci_hi | 0.2959 | 0.2163 | 0.0078 | 0.4256 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | p | 0.5918 | 0.4715 | 0.0017 | 0.9841 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | animals_positive | 3.0 | 3.22 | 1.0 | 5.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | final | mean_y | -1.8764 | -1.9533 | -2.496 | -1.4002 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | slope | 0.1825 | 0.0031 | -0.1842 | 0.2326 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | ci_lo | 0.0289 | -0.1736 | -0.412 | 0.1071 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | ci_hi | 0.3361 | 0.1798 | -0.0655 | 0.4097 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | p | 0.0199 | 0.4165 | 0.0001 | 0.9355 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | animals_positive | 4.0 | 3.22 | 1.0 | 5.525 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 1 | pay_rem_n | debt_rem | True | pass2med | mean_y | -2.3951 | -1.984 | -2.4229 | -1.496 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | slope | 0.1678 | 0.184 | 0.0212 | 0.3045 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | ci_lo | -0.0487 | 0.026 | -0.1627 | 0.1718 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | ci_hi | 0.3842 | 0.3419 | 0.1662 | 0.4859 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | p | 0.1287 | 0.0957 | 0.0 | 0.7394 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | animals_positive | 5.0 | 4.88 | 3.0 | 6.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | mean_x | -7.6034 | -7.0557 | -7.9956 | -5.8043 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | final | mean_y | -3.6394 | -4.3837 | -5.9989 | -2.87 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | slope | 0.3183 | 0.1947 | 0.0814 | 0.3199 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | ci_lo | 0.1809 | 0.0436 | -0.1084 | 0.1805 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | ci_hi | 0.4557 | 0.3458 | 0.2002 | 0.5106 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | p | 0.0 | 0.0543 | 0.0 | 0.3962 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | animals_positive | 6.0 | 5.03 | 3.0 | 6.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | mean_x | -9.155 | -8.5999 | -9.364 | -7.7547 | 100 |
| morning | 3 | pay_nrem | debt_nrem | False | pass2med | mean_y | -5.28 | -5.3544 | -6.6876 | -4.0926 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | slope | 0.0861 | 0.0929 | -0.1416 | 0.2727 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | ci_lo | -0.1484 | -0.1535 | -0.4089 | 0.0629 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | ci_hi | 0.3206 | 0.3394 | 0.0624 | 0.5996 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | p | 0.4719 | 0.4265 | 0.0076 | 0.9688 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | animals_positive | 4.0 | 3.68 | 2.0 | 5.525 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | mean_x | -7.6034 | -7.0557 | -7.9956 | -5.8043 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | final | mean_y | -3.6394 | -4.3837 | -5.9989 | -2.87 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | slope | 0.2377 | 0.154 | -0.0422 | 0.3593 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | ci_lo | 0.0706 | -0.0921 | -0.331 | 0.135 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | ci_hi | 0.4048 | 0.4 | 0.1428 | 0.6356 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | p | 0.0053 | 0.3156 | 0.0002 | 0.908 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | animals_positive | 5.0 | 4.1 | 2.0 | 6.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | mean_x | -9.155 | -8.5999 | -9.364 | -7.7547 | 100 |
| morning | 3 | pay_nrem | debt_nrem | True | pass2med | mean_y | -5.28 | -5.3544 | -6.6876 | -4.0926 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | slope | 0.1738 | 0.0802 | -0.3703 | 0.5551 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | ci_lo | -0.5678 | -0.3949 | -0.9135 | 0.1458 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | ci_hi | 0.9154 | 0.5554 | 0.0593 | 1.1337 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | p | 0.646 | 0.4769 | 0.004 | 0.9789 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | animals_positive | 4.0 | 3.3 | 1.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem | debt_rem | False | final | mean_y | 0.2919 | -0.7382 | -1.8995 | 0.4904 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | slope | 0.7433 | 0.0748 | -0.3781 | 0.5955 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | ci_lo | 0.4609 | -0.3736 | -1.0338 | 0.2294 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | ci_hi | 1.0257 | 0.5231 | -0.009 | 1.1454 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | p | 0.0 | 0.4062 | 0.0008 | 0.972 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | animals_positive | 4.0 | 3.5 | 1.0 | 6.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem | debt_rem | False | pass2med | mean_y | -0.8037 | -0.6961 | -1.5837 | 0.4526 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | slope | -0.0622 | 0.0284 | -0.4807 | 0.4853 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | ci_lo | -0.8187 | -0.4855 | -1.11 | -0.0072 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | ci_hi | 0.6944 | 0.5424 | -0.0068 | 1.2725 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | p | 0.8721 | 0.4889 | 0.0209 | 0.97 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | animals_positive | 2.0 | 3.07 | 1.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem | debt_rem | True | final | mean_y | 0.2919 | -0.7382 | -1.8995 | 0.4904 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | slope | 0.9607 | 0.0133 | -0.5087 | 0.539 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | ci_lo | 0.4702 | -0.4955 | -1.2116 | 0.2169 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | ci_hi | 1.4511 | 0.5221 | -0.0471 | 1.2822 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | p | 0.0001 | 0.4082 | 0.0024 | 0.9898 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | animals_positive | 5.0 | 3.06 | 1.0 | 6.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem | debt_rem | True | pass2med | mean_y | -0.8037 | -0.6961 | -1.5837 | 0.4526 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | slope | 0.1192 | 0.0271 | -0.4264 | 0.5309 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | ci_lo | -0.4418 | -0.4791 | -0.9946 | 0.0387 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | ci_hi | 0.6803 | 0.5332 | -0.0066 | 1.1661 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | p | 0.677 | 0.5202 | 0.0162 | 0.9843 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | animals_positive | 3.0 | 2.57 | 0.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | final | mean_y | 0.2919 | -0.7382 | -1.8995 | 0.4904 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | slope | 0.5941 | 0.0191 | -0.489 | 0.5323 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_lo | -0.0092 | -0.4457 | -1.0959 | 0.1525 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | ci_hi | 1.1973 | 0.4839 | -0.0167 | 1.0042 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | p | 0.0536 | 0.393 | 0.0043 | 0.946 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals_positive | 2.0 | 2.71 | 1.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | False | pass2med | mean_y | -0.8037 | -0.6961 | -1.5837 | 0.4526 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | slope | -0.0551 | 0.0135 | -0.5049 | 0.4536 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | ci_lo | -0.797 | -0.4974 | -1.118 | 0.0036 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | ci_hi | 0.6868 | 0.5245 | -0.0188 | 1.1889 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | p | 0.8843 | 0.5118 | 0.0261 | 0.9707 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | animals_positive | 3.0 | 2.47 | 0.475 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | final | mean_y | 0.2919 | -0.7382 | -1.8995 | 0.4904 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | slope | 0.8929 | 0.0142 | -0.5541 | 0.5846 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_lo | 0.2879 | -0.5058 | -1.2535 | 0.2226 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | ci_hi | 1.498 | 0.5343 | -0.0438 | 1.3241 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | p | 0.0038 | 0.4115 | 0.0009 | 0.9904 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals_positive | 5.0 | 2.38 | 0.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | animals | 5.0 | 5.0 | 5.0 | 5.0 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem | debt_rem + debt_nrem | True | pass2med | mean_y | -0.8037 | -0.6961 | -1.5837 | 0.4526 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | n_windows | 49.0 | 48.96 | 48.0 | 49.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | slope | -0.2615 | -0.0829 | -1.1505 | 0.7509 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | ci_lo | -2.063 | -1.1796 | -2.5627 | -0.0448 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | ci_hi | 1.54 | 1.0137 | -0.0707 | 2.166 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | p | 0.776 | 0.536 | 0.0242 | 0.9833 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | animals_positive | 2.0 | 3.01 | 1.0 | 5.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | final | mean_y | 1.55 | 0.1343 | -3.1675 | 3.2817 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | slope | 0.8457 | -0.0628 | -1.1708 | 1.1068 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | ci_lo | -0.2748 | -1.0814 | -2.4795 | 0.185 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | ci_hi | 1.9662 | 0.9558 | -0.1023 | 2.7728 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | p | 0.1391 | 0.3956 | 0.0048 | 0.9545 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | animals_positive | 3.0 | 2.82 | 0.0 | 5.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | False | pass2med | mean_y | 0.2947 | -0.1352 | -3.1462 | 2.9527 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | n_windows | 49.0 | 48.96 | 48.0 | 49.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | slope | -0.0027 | -0.0341 | -1.2562 | 1.06 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | ci_lo | -1.1852 | -1.3314 | -2.7863 | -0.093 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | ci_hi | 1.1799 | 1.2631 | -0.0274 | 2.7638 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | p | 0.9965 | 0.5195 | 0.0341 | 0.9827 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | animals_positive | 4.0 | 2.99 | 1.0 | 5.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | final | mean_y | 1.55 | 0.1343 | -3.1675 | 3.2817 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | slope | 2.2222 | -0.0741 | -1.2941 | 1.3745 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | ci_lo | 0.7273 | -1.2941 | -3.0926 | 0.3992 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | ci_hi | 3.7172 | 1.146 | -0.2549 | 2.7911 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | p | 0.0036 | 0.4261 | 0.001 | 0.9877 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | animals_positive | 4.0 | 2.83 | 0.475 | 5.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem_dur | debt_rem | True | pass2med | mean_y | 0.2947 | -0.1352 | -3.1462 | 2.9527 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | slope | 0.1302 | 0.0626 | -0.2349 | 0.4204 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | ci_lo | -0.5826 | -0.266 | -0.6504 | 0.1089 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | ci_hi | 0.843 | 0.3912 | -0.0111 | 0.7942 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | p | 0.7204 | 0.465 | 0.0072 | 0.9287 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | animals_positive | 4.0 | 3.28 | 1.0 | 5.525 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | final | mean_y | 0.3406 | -0.494 | -1.2489 | 0.2242 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | slope | 0.438 | 0.0796 | -0.2555 | 0.4496 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | ci_lo | 0.0181 | -0.2579 | -0.7127 | 0.0884 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | ci_hi | 0.8579 | 0.4171 | 0.0582 | 0.8297 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | p | 0.0409 | 0.4577 | 0.0042 | 0.9592 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | animals_positive | 4.0 | 3.54 | 1.475 | 6.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem_n | debt_rem | False | pass2med | mean_y | -0.5951 | -0.502 | -1.3071 | 0.2994 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | slope | -0.1458 | 0.0199 | -0.348 | 0.2826 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | ci_lo | -0.7402 | -0.3252 | -0.7108 | 0.0108 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | ci_hi | 0.4486 | 0.365 | -0.0788 | 0.7327 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | p | 0.6307 | 0.5051 | 0.0047 | 0.9673 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | animals_positive | 3.0 | 2.93 | 0.0 | 5.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | mean_x | 0.1373 | -0.9349 | -1.6921 | -0.2853 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | final | mean_y | 0.3406 | -0.494 | -1.2489 | 0.2242 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | n_windows | 49.0 | 49.0 | 49.0 | 49.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | clusters | 12.0 | 12.0 | 12.0 | 12.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | slope | 0.2378 | 0.0296 | -0.3716 | 0.4543 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | ci_lo | -0.2338 | -0.3311 | -0.8229 | 0.1594 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | ci_hi | 0.7094 | 0.3903 | -0.0652 | 0.9292 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | p | 0.3229 | 0.3962 | 0.0013 | 0.9071 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | animals_positive | 4.0 | 3.13 | 0.0 | 6.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | mean_x | -0.6947 | -0.8833 | -1.4199 | -0.1969 | 100 |
| morning | 3 | pay_rem_n | debt_rem | True | pass2med | mean_y | -0.5951 | -0.502 | -1.3071 | 0.2994 | 100 |

## E (vi): the night -> next-day deviation slope, observed vs simulated

| quantity | model | x | y | scores | stat | observed | sim_mean | sim_2.5% | sim_97.5% | n_sim |
|---|---|---|---|---|---|---|---|---|---|---|
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | slope | -0.1676 | -0.1579 | -0.2068 | -0.1052 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | ci_lo | -0.5957 | -0.4048 | -0.5402 | -0.2817 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | ci_hi | 0.2606 | 0.0891 | -0.0011 | 0.2027 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | p | 0.443 | 0.2136 | 0.0483 | 0.4011 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | animals_negative | 4.0 | 4.28 | 3.0 | 5.0 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | slope | -0.124 | -0.1302 | -0.1747 | -0.0943 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | ci_lo | -0.4545 | -0.3779 | -0.519 | -0.2881 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | ci_hi | 0.2066 | 0.1175 | 0.0465 | 0.2036 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | p | 0.4623 | 0.2993 | 0.1486 | 0.4817 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | animals_negative | 4.0 | 4.25 | 3.0 | 5.0 | 100 |
| NREM | drift: day deviation | day | day_NREM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | slope | 0.066 | 0.0573 | 0.0376 | 0.0791 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | ci_lo | -0.2456 | -0.2417 | -0.2872 | -0.2032 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | ci_hi | 0.3775 | 0.3562 | 0.3024 | 0.4085 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | p | 0.6782 | 0.7078 | 0.6078 | 0.795 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | animals_negative | 1.0 | 1.34 | 1.0 | 2.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | slope | 0.0179 | 0.0206 | -0.0008 | 0.0416 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | ci_lo | -0.2158 | -0.2538 | -0.2932 | -0.2118 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | ci_hi | 0.2516 | 0.2949 | 0.2583 | 0.3305 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | p | 0.881 | 0.8818 | 0.7512 | 0.9923 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | animals_negative | 2.0 | 2.09 | 1.0 | 3.0 | 100 |
| NREM | drift: night deviation | day | night_NREM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | slope | 0.279 | 0.0013 | -0.1787 | 0.1646 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | ci_lo | -0.1399 | -0.2719 | -0.4932 | -0.0335 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | ci_hi | 0.6979 | 0.2745 | 0.0435 | 0.4811 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | p | 0.1918 | 0.6248 | 0.0813 | 0.9917 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | animals_negative | 2.0 | 2.72 | 1.0 | 4.0 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | slope | -0.0679 | 0.0302 | -0.1584 | 0.2242 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | ci_lo | -0.3152 | -0.2309 | -0.435 | 0.0006 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | ci_hi | 0.1795 | 0.2913 | 0.0845 | 0.5062 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | p | 0.5907 | 0.5492 | 0.024 | 0.9615 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals_negative | 3.0 | 2.66 | 1.0 | 4.525 | 100 |
| NREM | within animal | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | slope | -0.1212 | -0.1302 | -0.3501 | 0.0771 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | ci_lo | -0.5333 | -0.4222 | -0.6776 | -0.1852 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | ci_hi | 0.2908 | 0.1618 | -0.0688 | 0.355 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | p | 0.5553 | 0.4183 | 0.0138 | 0.9781 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | animals_negative | 5.0 | 3.97 | 2.0 | 6.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | slope | -0.1005 | -0.0909 | -0.2814 | 0.1099 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | ci_lo | -0.3125 | -0.3688 | -0.5643 | -0.134 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | ci_hi | 0.1115 | 0.1869 | -0.0249 | 0.3847 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | p | 0.3435 | 0.481 | 0.0313 | 0.9267 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals_negative | 4.0 | 3.77 | 2.0 | 6.0 | 100 |
| NREM | within animal + day FE | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | slope | 0.3051 | 0.0214 | -0.1598 | 0.1823 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | ci_lo | -0.0578 | -0.2045 | -0.4147 | 0.0112 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | ci_hi | 0.668 | 0.2473 | 0.0355 | 0.4308 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | p | 0.0994 | 0.5454 | 0.034 | 0.9633 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | animals_negative | 2.0 | 2.72 | 1.0 | 4.0 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | slope | -0.0623 | 0.0367 | -0.1525 | 0.2328 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | ci_lo | -0.3141 | -0.217 | -0.4565 | 0.039 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | ci_hi | 0.1895 | 0.2903 | 0.0928 | 0.4797 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | p | 0.6279 | 0.5416 | 0.0077 | 0.9644 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals_negative | 3.0 | 2.66 | 1.0 | 4.525 | 100 |
| NREM | within animal + linear day | night_NREM_rate_dev | day_NREM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | slope | -0.0233 | -0.0242 | -0.0608 | 0.0138 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | ci_lo | -0.1973 | -0.1487 | -0.2421 | -0.0685 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | ci_hi | 0.1507 | 0.1003 | 0.0383 | 0.1937 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | p | 0.793 | 0.68 | 0.3154 | 0.9846 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | animals_negative | 3.0 | 3.26 | 1.475 | 5.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | slope | -0.0393 | -0.0254 | -0.0578 | 0.004 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | ci_lo | -0.1924 | -0.1447 | -0.2425 | -0.0758 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | ci_hi | 0.1137 | 0.0939 | 0.0329 | 0.1803 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | p | 0.6143 | 0.6626 | 0.2397 | 0.9756 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | animals_negative | 4.0 | 3.29 | 2.0 | 5.0 | 100 |
| REM | drift: day deviation | day | day_REM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | slope | 0.0159 | 0.0072 | -0.0056 | 0.0191 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | ci_lo | -0.012 | -0.0292 | -0.0553 | -0.0099 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | ci_hi | 0.0438 | 0.0436 | 0.0207 | 0.0724 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | p | 0.2649 | 0.6636 | 0.2689 | 0.9747 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | animals_negative | 1.0 | 2.31 | 1.0 | 4.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | slope | 0.0155 | 0.0063 | -0.0044 | 0.0175 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | ci_lo | -0.0166 | -0.0272 | -0.0464 | -0.0089 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | ci_hi | 0.0475 | 0.0397 | 0.0162 | 0.0638 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | p | 0.3444 | 0.6791 | 0.3237 | 0.993 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | animals_negative | 1.0 | 2.34 | 1.0 | 4.0 | 100 |
| REM | drift: night deviation | day | night_REM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | slope | -1.1664 | 0.0743 | -0.9231 | 1.24 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | ci_lo | -1.803 | -0.9289 | -2.2861 | 0.2593 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | ci_hi | -0.5298 | 1.0775 | -0.0468 | 2.4848 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | p | 0.0003 | 0.4644 | 0.0004 | 0.9868 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | animals_negative | 5.0 | 2.84 | 1.0 | 5.0 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | slope | -0.5632 | -0.1495 | -1.1526 | 0.94 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | ci_lo | -1.2604 | -1.1596 | -2.4135 | 0.0119 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | ci_hi | 0.134 | 0.8607 | -0.321 | 2.069 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | p | 0.1134 | 0.4225 | 0.0051 | 0.9523 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals_negative | 5.0 | 3.22 | 1.0 | 5.525 | 100 |
| REM | within animal | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | slope | -0.3615 | -0.0355 | -1.3625 | 1.1468 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | ci_lo | -1.8178 | -1.2468 | -2.5366 | -0.0771 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | ci_hi | 1.0949 | 1.1759 | -0.0604 | 2.4495 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | p | 0.6185 | 0.4869 | 0.0278 | 0.9753 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | animals_negative | 4.0 | 3.03 | 1.0 | 5.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | slope | -0.0341 | -0.2498 | -1.3754 | 0.845 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | ci_lo | -0.96 | -1.4776 | -2.6761 | -0.3743 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | ci_hi | 0.8919 | 0.978 | -0.1476 | 2.2661 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | p | 0.9411 | 0.4569 | 0.0249 | 0.9598 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals_negative | 3.0 | 3.49 | 1.0 | 6.0 | 100 |
| REM | within animal + day FE | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | slope | -1.1569 | 0.0915 | -0.9124 | 1.2533 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | ci_lo | -1.7359 | -0.9211 | -2.2008 | 0.2603 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | ci_hi | -0.5779 | 1.1042 | -0.0647 | 2.5722 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | p | 0.0001 | 0.4688 | 0.0008 | 0.9728 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | animals_negative | 5.0 | 2.84 | 1.0 | 5.0 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | final | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | n_animal_days | 56.0 | 56.0 | 56.0 | 56.0 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals | 6.0 | 6.0 | 6.0 | 6.0 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | slope | -0.4919 | -0.134 | -1.1378 | 0.9657 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | ci_lo | -0.9608 | -1.1495 | -2.3302 | 0.0132 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | ci_hi | -0.0229 | 0.8814 | -0.298 | 2.0711 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | p | 0.0398 | 0.425 | 0.0043 | 0.9762 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals_negative | 5.0 | 3.22 | 1.0 | 5.525 | 100 |
| REM | within animal + linear day | night_REM_rate_dev | day_REM_rate_dev | pass2med | animals_with_slope | 6.0 | 6.0 | 6.0 | 6.0 | 100 |

## E (ii): the carry-over curve (held-out gain of pre-wake history by wake bin), observed vs simulated

| scores | source | subset | delta_pct | ci_lo_pct | ci_hi_pct |
|---|---|---|---|---|---|
| final | observed | all post-wake | -0.3957 | -0.5833 | -0.2255 |
| final | observed | wake 2-7 min | -0.2793 | -0.738 | 0.2704 |
| final | observed | wake 40-120 s | -0.3342 | -0.5751 | -0.1217 |
| final | observed | wake 7-30 min | 0.545 | -0.0254 | 1.0523 |
| final | observed | wake < 40 s | -0.4664 | -0.6985 | -0.2418 |
| final | observed | wake >= 30 min | 0.24 | -0.1791 | 0.7002 |
| final | simulated | all post-wake | -0.2604 | -0.3709 | -0.1189 |
| final | simulated | wake 2-7 min | -0.1612 | -0.5163 | 0.1835 |
| final | simulated | wake 40-120 s | -0.2346 | -0.456 | -0.0138 |
| final | simulated | wake 7-30 min | 0.0659 | -0.4552 | 0.6194 |
| final | simulated | wake < 40 s | -0.2982 | -0.4169 | -0.1409 |
| final | simulated | wake >= 30 min | 0.319 | -0.0553 | 0.6992 |
| pass2med | observed | all post-wake | -0.2978 | -0.4204 | -0.159 |
| pass2med | observed | wake 2-7 min | -0.2923 | -0.5846 | 0.0806 |
| pass2med | observed | wake 40-120 s | -0.2799 | -0.4805 | -0.1008 |
| pass2med | observed | wake 7-30 min | 0.6145 | 0.3396 | 0.8378 |
| pass2med | observed | wake < 40 s | -0.3413 | -0.5041 | -0.1525 |
| pass2med | observed | wake >= 30 min | 0.1104 | -0.3835 | 0.6527 |
| pass2med | simulated | all post-wake | -0.2381 | -0.3257 | -0.1199 |
| pass2med | simulated | wake 2-7 min | 0.0442 | -0.3494 | 0.422 |
| pass2med | simulated | wake 40-120 s | -0.224 | -0.3846 | -0.0459 |
| pass2med | simulated | wake 7-30 min | 0.1174 | -0.2511 | 0.5095 |
| pass2med | simulated | wake < 40 s | -0.2829 | -0.3857 | -0.1412 |
| pass2med | simulated | wake >= 30 min | 0.2982 | -0.0609 | 0.6552 |

