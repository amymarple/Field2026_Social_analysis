# Internal sleep schedule — Phase 4: ambient temperature as a slow REM gate (cohort 2026c)

Plan Amendment 6 (written before results). Driver `ephys/sleep_schedule.py phase4` → `ephys/sleep_schedule_temp.py` (commit e6bec0f+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_schedule_phase4_20261008_1250`. **Technical ledger; no claim audit yet.**

## Definitions

```
Phase 4 of the internal-schedule analysis: ambient temperature as a slow REM gate (plan Amendment 6, written before
any result). Called by `python ephys/sleep_schedule.py phase4`.

Definitions:
  weather        sleep_quant.load_weather: on-site console, 5 min, 08-31 -> 09-12 (NWS KITH only inside the console's
                 09-02/03 uplink hole); outdoor temperature temp_C (degC), relative humidity, rain rate.
  temp_anom      temp_C minus its fit on (sin, cos)(2 pi k h / 24), k = 1, 2, over the whole cohort (degC): warmer (+) or
                 colder (-) than usual for that time of day. Joined to a 10-s step / 10-min bin by the nearest weather
                 sample within 15 min.
  T1             held out (forward chaining, as Phase 2): M2t vs M2t + z(temp_anom); full-fit multinomial coefficients
                 (REM vs stay, Wake vs stay) per SD, and per-animal signs of the REM-vs-stay coefficient.
  T2             1-h bins with >= 20 min of sleep: REM share of sleep ~ temp_anom + phase + day + animal (binomial GLM,
                 var weights = sleep s; SEs clustered by date); and sleep share of recorded time (>= 30 min recorded).
  T3             night -> next-day sleep deviations (Phase 3b) with the night and day mean temp_anom as covariates.
  T4             empirical REM hazard per 10-s step against the total NREM since the last REM, per temp_anom tertile.
Prediction (before results): warmer than usual -> REM entry more likely, REM share higher.
```

## Weather

| samples | from | to | temp_min | temp_max | anom_sd | anom_min | anom_max |
|---|---|---|---|---|---|---|---|
| 3866 | 2026-08-31 00:00:00 | 2026-09-17 12:00:19 | 8.6 | 28.4 | 3.0 | -7.34 | 5.64 |

## T1 Held out: does the temperature anomaly add to REM-entry prediction?

| comparison | subset | n_steps | n_rem | delta_pct | ci_lo_pct | ci_hi_pct | folds_better | folds | animals_better | animals | holds | full_fit_REM_vs_stay_per_SD | full_fit_Wake_vs_stay_per_SD | animals_REM_coef_positive | animals_fit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M2t_temp vs M2t | NREM steps with weather | 126200 | 2588 | 0.0375 | -0.0748 | 0.1288 | 7 | 15 | 3 | 6 | False | 0.0442 | 0.0139 | 4 | 6 |

## T2 Hourly shares vs the temperature anomaly

| outcome | n_animal_hours | logit_coef_per_degC | ci_lo | ci_hi | p | odds_ratio_per_degC | animals_positive | animals |
|---|---|---|---|---|---|---|---|---|
| REM share of sleep (hours with >= 20 min sleep) | 723 | 0.0398 | 0.015 | 0.0646 | 0.0016 | 1.0406 | 5 | 6 |
| sleep share of recorded time (hours >= 30 min recorded) | 1230 | 0.0045 | -0.0473 | 0.0563 | 0.8646 | 1.0045 | 4 | 6 |

## T3 Night -> next-day trade-off with temperature as a covariate

| scores | quantity | model | n | within_animal_slope | ci_lo | ci_hi | p | day_temp_coef | night_temp_coef |
|---|---|---|---|---|---|---|---|---|---|
| FINAL | REM | without temperature | 56 | -0.877 | -1.952 | 0.198 | 0.11 | nan | nan |
| FINAL | REM | with night + day temp anomaly | 56 | -1.032 | -2.275 | 0.211 | 0.104 | 1.743 | -0.18 |
| FINAL | NREM | without temperature | 56 | -0.296 | -0.595 | 0.003 | 0.053 | nan | nan |
| FINAL | NREM | with night + day temp anomaly | 56 | -0.175 | -0.384 | 0.035 | 0.103 | -12.147 | -1.719 |
| pass2med_remclean | REM | without temperature | 56 | -0.473 | -1.359 | 0.413 | 0.296 | nan | nan |
| pass2med_remclean | REM | with night + day temp anomaly | 56 | -0.437 | -1.285 | 0.412 | 0.313 | 2.159 | -1.651 |
| pass2med_remclean | NREM | without temperature | 56 | -0.539 | -0.784 | -0.294 | 0.0 | nan | nan |
| pass2med_remclean | NREM | with night + day temp anomaly | 56 | -0.389 | -0.554 | -0.225 | 0.0 | -6.323 | -2.711 |

## T4 Empirical hazards by temperature-anomaly tertile

| tert | nb | n | hR | hW |
|---|---|---|---|---|
| colder | [0, 60) | 6492 | 0.0656 | 0.0555 |
| colder | [60, 240) | 14168 | 0.0078 | 0.0386 |
| colder | [240, 480) | 15112 | 0.0142 | 0.0306 |
| colder | [480, 720) | 8867 | 0.0271 | 0.0315 |
| colder | [720, 1200) | 6193 | 0.0263 | 0.0423 |
| colder | [1200, 1800) | 1829 | 0.0186 | 0.0476 |
| colder | [1800, 3600) | 1125 | 0.0142 | 0.0587 |
| usual | [0, 60) | 7529 | 0.0647 | 0.0525 |
| usual | [60, 240) | 15399 | 0.0101 | 0.036 |
| usual | [240, 480) | 15514 | 0.0181 | 0.0285 |
| usual | [480, 720) | 8332 | 0.0295 | 0.0329 |
| usual | [720, 1200) | 5412 | 0.0322 | 0.0384 |
| usual | [1200, 1800) | 1192 | 0.026 | 0.0612 |
| usual | [1800, 3600) | 354 | 0.0226 | 0.0452 |
| warmer | [0, 60) | 6560 | 0.0585 | 0.0611 |
| warmer | [60, 240) | 14709 | 0.0084 | 0.0439 |
| warmer | [240, 480) | 14560 | 0.0179 | 0.0383 |
| warmer | [480, 720) | 7651 | 0.0284 | 0.0435 |
| warmer | [720, 1200) | 5596 | 0.0254 | 0.0416 |
| warmer | [1200, 1800) | 2329 | 0.0103 | 0.064 |
| warmer | [1800, 3600) | 1969 | 0.0112 | 0.0701 |

