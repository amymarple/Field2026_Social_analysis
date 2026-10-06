# NREM → REM transitions and recent sleep history, cohort 2026c

`ephys/sleep_cycles.py` (git 9344676+dirty, 2026-10-06T23:42:00+00:00). Plan: [implementation_plan/2026-10-06-sleep-rem-cycle-history.md](../../../../implementation_plan/2026-10-06-sleep-rem-cycle-history.md).
Bulk outputs: `D:\Field2026_analysis_out\2026c\sleep_cycles_20261006_1922`. Definitions: the module docstring, summarised here.

**Scope.**
- States are `imu_remclean`, 1-s epochs. REM bouts as scored, no merging (user decision).
- Models are fitted on the light phase; the dark-phase naps are the held-out transfer test.
- Descriptive relations, predictive evidence and mechanism are kept apart. Nothing here shows a mechanism.

## Data

| excluded | sessions | hours |
|---|---|---|
| (included) | 168 | 1281.3 |
| < 0.5 h | 21 | 1.6 |
| SF12_contact_failing | 1 | 0.0 |
| SW threshold failure, unresolved (user 2026-10-06) | 1 | 3.7 |
| noise (user) | 7 | 38.5 |
| not scored | 5 | 46.8 |

- Complete cycles: 4437 (4204 light, 233 dark); censored intervals: 158.
- Model steps (Δ = 10 s of NREM after a REM of known length): 139500 light, 23919 dark.
- Events: light 3588 → REM and 4980 → Wake; dark 183 → REM and 1514 → Wake.
- Per animal × date × phase: `ephys_spikes_sleep_cycles_coverage_2026c.csv` and the coverage figure.

## Descriptive relations (complete cycles)

- **Per animal:** Spearman ρ, for animals with ≥ 20 cycles.
- **Pooled:** $\ln(1+y) = \beta \ln x + \alpha_a$, with SEs cluster-robust by date.
- `n_pos` = animals with ρ > 0.
- **S2 threshold** (2-Gaussian intersection on ln N, light): N = 135 s. Cycles below it are 'sequential' (48% of the light cycles).

| phase | relation | variant | n | n_animals | n_pos | slope | slope_lo | slope_hi | p | rho |
|---|---|---|---|---|---|---|---|---|---|---|
| light | R1 REM_pre -> N | main | 4197 | 6 | 4 | 0.0117 | -0.0853 | 0.1087 | 0.8134 | {'SF07': -0.001, 'SF08': -0.079, 'SF09': 0.017, 'SF10': 0.122, 'SF11': 0.228, 'SF12': 0.189} |
| light | R2 REM_pre -> I | main | 4197 | 6 | 5 | 0.0871 | 0.0009 | 0.1733 | 0.0477 | {'SF07': 0.026, 'SF08': -0.048, 'SF09': 0.029, 'SF10': 0.141, 'SF11': 0.234, 'SF12': 0.199} |
| light | R3 N -> REM_next | main | 3690 | 6 | 6 | 0.1048 | 0.0774 | 0.1323 | 0.0 | {'SF07': 0.157, 'SF08': 0.285, 'SF09': 0.177, 'SF10': 0.235, 'SF11': 0.057, 'SF12': 0.203} |
| dark | R1 REM_pre -> N | main | 233 | 6 | 6 | 0.3128 | 0.0039 | 0.6216 | 0.0472 | {'SF07': 0.258, 'SF08': 0.072, 'SF09': 0.136, 'SF10': 0.332, 'SF11': 0.159, 'SF12': 0.095} |
| dark | R2 REM_pre -> I | main | 233 | 6 | 6 | 0.3233 | -0.088 | 0.7346 | 0.1234 | {'SF07': 0.375, 'SF08': 0.03, 'SF09': 0.095, 'SF10': 0.248, 'SF11': 0.063, 'SF12': 0.095} |
| dark | R3 N -> REM_next | main | 212 | 6 | 5 | 0.0407 | -0.0307 | 0.1121 | 0.2641 | {'SF07': 0.029, 'SF08': 0.255, 'SF09': 0.11, 'SF10': 0.027, 'SF11': 0.219, 'SF12': -0.094} |
| light | R1 REM_pre -> N | S1 Park micro-arousals -> N | 4197 | 6 | 5 | 0.0644 | -0.0182 | 0.147 | 0.1263 | {'SF07': 0.014, 'SF08': -0.068, 'SF09': 0.021, 'SF10': 0.133, 'SF11': 0.231, 'SF12': 0.195} |
| light | R1 REM_pre -> N | S2 single cycles only | 2170 | 6 | 6 | 0.0711 | 0.0471 | 0.0951 | 0.0 | {'SF07': 0.098, 'SF08': 0.118, 'SF09': 0.106, 'SF10': 0.105, 'SF11': 0.209, 'SF12': 0.172} |
| light | R1 REM_pre -> N | flags excluded (probe settle, shank1, females, bad) | 3740 | 6 | 5 | -0.0061 | -0.1097 | 0.0975 | 0.9078 | {'SF07': 0.009, 'SF08': -0.09, 'SF09': 0.02, 'SF10': 0.122, 'SF11': 0.23, 'SF12': 0.156} |
| light | R1 REM_pre -> N | S3 imu_nremgate states | 5162 | 6 | 3 | -0.1243 | -0.189 | -0.0596 | 0.0002 | {'SF07': -0.113, 'SF08': -0.095, 'SF09': -0.032, 'SF10': 0.036, 'SF11': 0.06, 'SF12': 0.092} |

## Does history add predictive information? (held-out)

**ΔLL** = held-out mean log-loss difference, in millinats per 10-s step; < 0 means the larger model predicts better. The CI is a bootstrap over dates. `folds better` = held-out dates on which the larger model is better.

Relative = ΔLL / the baseline's held-out log-loss: M0 on the light phase (0.2660 nats / step); for the night-transfer rows M0' on the dark phase (0.2923).

| Comparison | ΔLL (millinats / step) | 95 % CI | Relative to M0 | Folds better |
|---|---|---|---|---|
| M1 - M0, all outcomes | -2.63 | [-3.39, -1.91] | -0.99 % | 11/12 |
| M2 - M1, all outcomes | +0.03 | [-0.07, +0.18] | +0.01 % | 6/12 |
| M1 - M0, REM outcome | -2.18 | [-2.72, -1.59] | -0.82 % | 11/12 |
| M2 - M1, REM outcome | +0.01 | [-0.06, +0.13] | +0.00 % | 9/12 |
| M1 - M0, steps >= S2 threshold after REM | -1.69 | [-2.28, -1.01] | -0.64 % | 10/12 |
| night transfer M1' - M0', all outcomes | -14.41 | [-16.88, -12.03] | -4.93 % | 13/13 |
| night transfer M1' - M0', REM outcome | -9.51 | [-10.88, -8.29] | -3.25 % | 13/13 |
| M1 + day weather - M1 (secondary) | +0.20 | [-0.31, +0.92] | +0.07 % | 8/12 |
| ablation, M0 + REM_pre vs M0 | -0.07 | [-0.16, +0.02] | -0.03 % | 8/12 |
| ablation, M0 + N_prior vs M0 | -0.44 | [-0.66, -0.22] | -0.17 % | 10/12 |
| ablation, M0 + W_cum vs M0 | -2.35 | [-2.99, -1.73] | -0.88 % | 11/12 |
| ablation, M0 + REM_pre+N_prior vs M0 | -0.52 | [-0.74, -0.30] | -0.20 % | 11/12 |
| night transfer, M0' + REM_pre + N_prior vs M0' (no wake term) | -3.15 | [-3.91, -2.41] | -1.08 % | 13/13 |
| S3 imu_nremgate states, M1 vs M0 | -2.72 | [-3.48, -1.97] | -1.02 % | 11/12 |

Per fold: `ephys_spikes_sleep_cycles_cv_2026c.csv`.

**Leave one animal out** (pooled intercept), ΔLL M1 − M0 per animal (millinats / step): SF07 -4.72, SF08 -1.24, SF09 -2.68, SF10 -2.78, SF11 -2.23, SF12 -2.56.

## Direction of the history terms

Full light-phase fit; coefficients are per SD of the covariate, on the log-odds of REM (or Wake) against staying in NREM in the next 10 s. Use them for direction and size only: the predictive claim rests on the held-out table above.

| model | outcome | term | coef_per_SD | se | p | se_kind |
|---|---|---|---|---|---|---|
| M1 | REM vs stay | l_rem_pre | -0.0007 | 0.0208 | 0.9725 | cluster(date) |
| M1 | REM vs stay | l_n_prior | 0.1306 | 0.0273 | 0.0 | cluster(date) |
| M1 | REM vs stay | l_w_cum | -0.4783 | 0.0288 | 0.0 | cluster(date) |
| M1 | Wake vs stay | l_rem_pre | 0.0264 | 0.0118 | 0.0247 | cluster(date) |
| M1 | Wake vs stay | l_n_prior | -0.14 | 0.0235 | 0.0 | cluster(date) |
| M1 | Wake vs stay | l_w_cum | 0.2062 | 0.0274 | 0.0 | cluster(date) |
| M2 | REM vs stay | l_rem_pre | -0.0779 | 0.0551 | 0.1573 | cluster(date) |
| M2 | REM vs stay | l_n_prior | 0.2215 | 0.0513 | 0.0 | cluster(date) |
| M2 | REM vs stay | l_w_cum | -0.4788 | 0.0285 | 0.0 | cluster(date) |
| M2 | REM vs stay | l_rem_pre x sin | -0.0177 | 0.0331 | 0.5926 | cluster(date) |
| M2 | REM vs stay | l_rem_pre x cos | -0.1078 | 0.068 | 0.113 | cluster(date) |
| M2 | REM vs stay | l_n_prior x sin | 0.0694 | 0.0368 | 0.0591 | cluster(date) |
| M2 | REM vs stay | l_n_prior x cos | 0.114 | 0.0557 | 0.0406 | cluster(date) |
| M2 | Wake vs stay | l_rem_pre | -0.0078 | 0.0447 | 0.8616 | cluster(date) |
| M2 | Wake vs stay | l_n_prior | -0.1311 | 0.0584 | 0.0249 | cluster(date) |
| M2 | Wake vs stay | l_w_cum | 0.2019 | 0.0288 | 0.0 | cluster(date) |
| M2 | Wake vs stay | l_rem_pre x sin | -0.0741 | 0.0282 | 0.0087 | cluster(date) |
| M2 | Wake vs stay | l_rem_pre x cos | -0.0236 | 0.0634 | 0.7093 | cluster(date) |
| M2 | Wake vs stay | l_n_prior x sin | 0.0109 | 0.0262 | 0.6779 | cluster(date) |
| M2 | Wake vs stay | l_n_prior x cos | 0.0105 | 0.0608 | 0.8635 | cluster(date) |

Per-animal M1 (REM-vs-stay coefficient per SD, sign consistency):

| animal | n_steps | n_rem_events | l_rem_pre_REMvsStay | l_n_prior_REMvsStay | l_w_cum_REMvsStay | d_M1_M0_loao |
|---|---|---|---|---|---|---|
| SF07 | 23263 | 711 | 0.0102 | -0.0332 | -0.5071 | -0.0047 |
| SF08 | 25947 | 640 | 0.1105 | 0.1486 | -0.4337 | -0.0012 |
| SF09 | 27076 | 586 | 0.0163 | 0.1888 | -0.455 | -0.0027 |
| SF10 | 27423 | 754 | -0.0508 | 0.1033 | -0.4321 | -0.0028 |
| SF11 | 12465 | 357 | -0.1343 | 0.265 | -0.4643 | -0.0022 |
| SF12 | 23326 | 540 | -0.084 | 0.1905 | -0.5008 | -0.0026 |

## Figures
- `figures/ephys_spikes_sleep_cycles_coverage_2026c.png`: coverage.
- `figures/ephys_spikes_sleep_cycles_rem_pre_vs_nrem_2026c.png`: R1 per animal, light vs dark.
- `figures/ephys_spikes_sleep_cycles_hazard_map_2026c.png`: P(→ REM) over time of day × prior NREM (M2).
- `figures/ephys_spikes_sleep_cycles_model_comparison_2026c.png`: M0 / M1 / M2 held-out comparison + calibration.

## Limits that stay open
- **Scoring structure.** The scorer smooths its metrics over 15 s and imposes a 6-s minimum bout. `imu_remclean` forbids REM after > 10 s of wake, so wake → REM is not testable.
- **Per-session thresholds.** REM detection quality varies by session (see the review).
- **History mixed with time.** REM declines over days (day index in M0). Probe advances and contact degradation are flags, and a sensitivity row drops them.
- **Few units.** 6 animals and ~11 dates, so the M2 interactions have little support. The dark-phase time-of-day × history question is not answerable (too few cycles).
- **Semi-natural light.** Sunrise and sunset, not a 12:12 lab cycle: Vivaldi 2005's 'lights-on + 1–4 h' maps only loosely onto sunrise.
