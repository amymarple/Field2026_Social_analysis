# NREM → REM transitions and recent sleep history, v2 (final), cohort 2026c

`ephys/sleep_cycles_v2.py` (git d51e211+dirty, 2026-10-07T20:07:39+00:00). States: `D:\3rd_rat_spikes\analysis\sleep_server\states_1s_final`. Review table: `../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_review_2026c.csv`. Bulk: `D:\Field2026_analysis_out\2026c\sleep_cycles_v2_final_20261007_1500`. Definitions: the module docstring.

## Data
- **Records:** 129 continuous records; 28 of them joined across file splits of ≤ 60 s, with 670 s marked unknown.
- **Cycles:** 4488, of which 4448 complete.
- **Model steps:** 185869 (151256 light, 34613 dark). 19406 of them have no REM anchor in the record: these were dropped in v1.
- **Events:** 3933 → REM (231 in the dark phase); 7686 → Wake.
- **Blocks:** 22 day-halves.

## Held-out comparison

Baseline log-loss of M0 (leave one block out, 24 h): 0.2661 nats / step. Relative = ΔLL / the baseline of the same test set.

| Comparison | ΔLL (millinats / step) | 95 % CI | Relative | Folds better |
|---|---|---|---|---|
| M1 vs M0 (24 h, leave one block out) | -5.30 | [-6.26, -4.20] | -1.99 % | 22/22 |
| M2 vs M1 (history x phase) | +0.19 | [-0.37, +1.00] | +0.07 % | 13/22 |
| M0 + A_only vs M0 | -3.29 | [-4.52, -2.19] | -1.24 % | 22/22 |
| M0 + B_only vs M0 | -2.66 | [-3.96, -0.90] | -1.00 % | 19/22 |
| M0 + W_cum vs M0 | -3.07 | [-4.29, -2.01] | -1.15 % | 22/22 |
| M0 + N_prior vs M0 | -1.15 | [-2.01, -0.55] | -0.43 % | 19/22 |
| M0 + REM_pre vs M0 | -0.83 | [-1.78, -0.20] | -0.31 % | 18/22 |
| M1 vs M0, fitted and tested on night steps only | -1.30 | [-3.62, +1.55] | -0.49 % | 9/13 |
| M1 vs M0, fitted and tested on light steps only | -5.50 | [-6.39, -4.38] | -2.08 % | 18/22 |
| M1 vs M0, forward chaining (extrapolation) | -4.67 | [-6.22, -2.95] | -1.85 % | 15/16 |

## Direction of the history terms (full fit; per SD; log-odds against staying in NREM)

| model | outcome | term | coef_per_SD | se | p | se_kind |
|---|---|---|---|---|---|---|
| M1 | REM vs stay | l_rem_pre | 0.1306 | 0.0284 | 0.0 | cluster(block) |
| M1 | REM vs stay | l_n_prior | -0.0281 | 0.0339 | 0.4078 | cluster(block) |
| M1 | REM vs stay | l_w_cum | -0.6502 | 0.0449 | 0.0 | cluster(block) |
| M1 | REM vs stay | has_anchor | 0.6236 | 0.0717 | 0.0 | cluster(block) |
| M1 | REM vs stay | fW10 | 0.7149 | 0.0706 | 0.0 | cluster(block) |
| M1 | REM vs stay | fN10 | 0.9611 | 0.0543 | 0.0 | cluster(block) |
| M1 | REM vs stay | c10 | -0.0934 | 0.0344 | 0.0067 | cluster(block) |
| M1 | REM vs stay | fW60 | 0.2828 | 0.1617 | 0.0803 | cluster(block) |
| M1 | REM vs stay | fN60 | 0.2674 | 0.1554 | 0.0853 | cluster(block) |
| M1 | REM vs stay | c60 | 0.0232 | 0.0277 | 0.4038 | cluster(block) |
| M1 | REM vs stay | fW180 | -1.0864 | 0.2127 | 0.0 | cluster(block) |
| M1 | REM vs stay | fN180 | -0.9461 | 0.2036 | 0.0 | cluster(block) |
| M1 | REM vs stay | c180 | -0.0296 | 0.0226 | 0.1903 | cluster(block) |
| M1 | Wake vs stay | l_rem_pre | 0.066 | 0.0209 | 0.0016 | cluster(block) |
| M1 | Wake vs stay | l_n_prior | -0.0763 | 0.0197 | 0.0001 | cluster(block) |
| M1 | Wake vs stay | l_w_cum | 0.072 | 0.0268 | 0.0073 | cluster(block) |
| M1 | Wake vs stay | has_anchor | -0.0147 | 0.0224 | 0.5121 | cluster(block) |
| M1 | Wake vs stay | fW10 | 0.0963 | 0.0365 | 0.0083 | cluster(block) |
| M1 | Wake vs stay | fN10 | -0.0687 | 0.0351 | 0.0502 | cluster(block) |
| M1 | Wake vs stay | c10 | 0.003 | 0.0274 | 0.9114 | cluster(block) |
| M1 | Wake vs stay | fW60 | 0.4534 | 0.0945 | 0.0 | cluster(block) |
| M1 | Wake vs stay | fN60 | 0.4208 | 0.0757 | 0.0 | cluster(block) |
| M1 | Wake vs stay | c60 | -0.1265 | 0.0512 | 0.0134 | cluster(block) |
| M1 | Wake vs stay | fW180 | -0.2767 | 0.1034 | 0.0075 | cluster(block) |
| M1 | Wake vs stay | fN180 | -0.2829 | 0.0997 | 0.0045 | cluster(block) |
| M1 | Wake vs stay | c180 | 0.069 | 0.0517 | 0.1816 | cluster(block) |
| M2 | REM vs stay | l_rem_pre | -0.0373 | 0.0568 | 0.5116 | cluster(block) |
| M2 | REM vs stay | l_n_prior | 0.0353 | 0.0379 | 0.3524 | cluster(block) |
| M2 | REM vs stay | l_w_cum | -0.5513 | 0.0428 | 0.0 | cluster(block) |
| M2 | REM vs stay | has_anchor | 0.6502 | 0.1124 | 0.0 | cluster(block) |
| M2 | REM vs stay | fW10 | 0.7515 | 0.0687 | 0.0 | cluster(block) |
| M2 | REM vs stay | fN10 | 0.9805 | 0.0548 | 0.0 | cluster(block) |
| M2 | REM vs stay | c10 | -0.0869 | 0.0347 | 0.0123 | cluster(block) |
| M2 | REM vs stay | fW60 | 0.1769 | 0.1884 | 0.3478 | cluster(block) |
| M2 | REM vs stay | fN60 | 0.3117 | 0.1669 | 0.0618 | cluster(block) |
| M2 | REM vs stay | c60 | 0.0202 | 0.0311 | 0.5163 | cluster(block) |
| M2 | REM vs stay | fW180 | -1.1226 | 0.2139 | 0.0 | cluster(block) |
| M2 | REM vs stay | fN180 | -0.9913 | 0.2082 | 0.0 | cluster(block) |
| M2 | REM vs stay | c180 | -0.0323 | 0.0213 | 0.1308 | cluster(block) |
| M2 | REM vs stay | l_rem_pre x sin1 | -0.1381 | 0.0584 | 0.018 | cluster(block) |
| M2 | REM vs stay | l_rem_pre x cos1 | -0.2432 | 0.0741 | 0.001 | cluster(block) |
| M2 | REM vs stay | l_n_prior x sin1 | -0.0054 | 0.0301 | 0.8585 | cluster(block) |
| M2 | REM vs stay | l_n_prior x cos1 | 0.1034 | 0.0621 | 0.096 | cluster(block) |
| M2 | REM vs stay | l_w_cum x sin1 | 0.1461 | 0.0598 | 0.0145 | cluster(block) |
| M2 | REM vs stay | l_w_cum x cos1 | 0.1711 | 0.0622 | 0.0059 | cluster(block) |
| M2 | REM vs stay | fW60 x sin1 | 0.0775 | 0.0678 | 0.2529 | cluster(block) |
| M2 | REM vs stay | fW60 x cos1 | -0.2198 | 0.0704 | 0.0018 | cluster(block) |
| M2 | Wake vs stay | l_rem_pre | 0.0767 | 0.025 | 0.0021 | cluster(block) |
| M2 | Wake vs stay | l_n_prior | -0.0272 | 0.0287 | 0.3422 | cluster(block) |
| M2 | Wake vs stay | l_w_cum | 0.024 | 0.0349 | 0.4914 | cluster(block) |
| M2 | Wake vs stay | has_anchor | -0.002 | 0.0303 | 0.9467 | cluster(block) |
| M2 | Wake vs stay | fW10 | 0.1016 | 0.0365 | 0.0054 | cluster(block) |
| M2 | Wake vs stay | fN10 | -0.071 | 0.0346 | 0.04 | cluster(block) |
| M2 | Wake vs stay | c10 | 0.0005 | 0.0276 | 0.9841 | cluster(block) |
| M2 | Wake vs stay | fW60 | 0.4001 | 0.1047 | 0.0001 | cluster(block) |
| M2 | Wake vs stay | fN60 | 0.3692 | 0.0951 | 0.0001 | cluster(block) |
| M2 | Wake vs stay | c60 | -0.1228 | 0.0507 | 0.0155 | cluster(block) |
| M2 | Wake vs stay | fW180 | -0.2557 | 0.1144 | 0.0254 | cluster(block) |
| M2 | Wake vs stay | fN180 | -0.2395 | 0.1232 | 0.052 | cluster(block) |
| M2 | Wake vs stay | c180 | 0.0697 | 0.0501 | 0.1644 | cluster(block) |
| M2 | Wake vs stay | l_rem_pre x sin1 | -0.0531 | 0.0311 | 0.088 | cluster(block) |
| M2 | Wake vs stay | l_rem_pre x cos1 | 0.0369 | 0.0313 | 0.2381 | cluster(block) |
| M2 | Wake vs stay | l_n_prior x sin1 | 0.0056 | 0.0291 | 0.847 | cluster(block) |
| M2 | Wake vs stay | l_n_prior x cos1 | 0.1213 | 0.0428 | 0.0046 | cluster(block) |
| M2 | Wake vs stay | l_w_cum x sin1 | 0.094 | 0.037 | 0.0111 | cluster(block) |
| M2 | Wake vs stay | l_w_cum x cos1 | -0.1451 | 0.0535 | 0.0067 | cluster(block) |
| M2 | Wake vs stay | fW60 x sin1 | -0.0091 | 0.0398 | 0.819 | cluster(block) |
| M2 | Wake vs stay | fW60 x cos1 | -0.0816 | 0.0409 | 0.0459 | cluster(block) |

Per animal (M1, REM vs stay, per SD):

| animal | n_steps | n_rem | l_rem_pre | l_n_prior | l_w_cum | has_anchor | fW10 | fN10 | c10 | fW60 | fN60 | c60 | fW180 | fN180 | c180 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | 33377 | 773 | 0.156 | -0.144 | -0.739 | 0.922 | 1.008 | 1.191 | -0.069 | -0.083 | -0.149 | 0.122 | -0.879 | -0.878 | -0.121 |
| SF08 | 33115 | 690 | 0.253 | -0.0 | -0.703 | 0.354 | 0.8 | 0.952 | -0.252 | 0.159 | 0.23 | 0.098 | -0.605 | -0.479 | 0.039 |
| SF09 | 34905 | 634 | 0.147 | -0.033 | -0.587 | 0.525 | 0.727 | 1.019 | 0.148 | 0.425 | 0.461 | -0.007 | -1.465 | -1.174 | -0.196 |
| SF10 | 35830 | 822 | 0.028 | -0.044 | -0.431 | 0.317 | 0.387 | 0.699 | 0.215 | 0.754 | 0.843 | 0.011 | -2.056 | -1.776 | -0.066 |
| SF11 | 17182 | 418 | 0.056 | 0.12 | -0.603 | 0.284 | 0.571 | 0.962 | -0.11 | 1.14 | 0.975 | 0.086 | -2.054 | -1.652 | -0.048 |
| SF12 | 31460 | 596 | 0.171 | -0.061 | -0.624 | 0.291 | 0.725 | 1.095 | 0.212 | 1.438 | 1.509 | -0.006 | -1.271 | -0.995 | 0.171 |

## Figures
- `figures/ephys_spikes_sleep_cycles_v2_final_hazard_map_2026c.png`
- `figures/ephys_spikes_sleep_cycles_v2_final_model_comparison_2026c.png`

