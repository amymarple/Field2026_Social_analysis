# Internal sleep schedule — Phase 3b: same-events catch-up and the 24-h budget checks (cohort 2026c)

Plan Amendment 5. Driver `ephys/sleep_schedule.py phase3b` (commit ea49009+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_schedule_phase3b_20261008_1153`. Technical ledger.

## Definitions

```
(1) Same-events catch-up: natural wakes followed >= 3 h (>= 6 h): REM excess at 1 / 3 (/ 6) h on the SAME events,
and the paired change; battery rounds likewise. (2) 24-h budget robustness: both scorings, minutes (obs - exp over the
recorded part) and rates, >= 50 % / >= 80 % recorded in both periods, animal fixed effects + per-animal slopes, REM and
NREM.
```

## 1. Same events: REM excess after natural wakes (coefficient of ln wake length; animal FE, dark; SEs by block)

| scores | events | n | outcome | l_d_coef | ci_lo | ci_hi | p | animals_negative | animals |
|---|---|---|---|---|---|---|---|---|---|
| FINAL | followed >= 180 min | 694 | REM excess at 60 min | -0.08 | -0.253 | 0.093 | 0.364 | 4 | 6 |
| FINAL | followed >= 180 min | 694 | REM excess at 180 min | 0.008 | -0.331 | 0.347 | 0.964 | 3 | 6 |
| FINAL | followed >= 180 min | 694 | change 60 -> 180 min | 0.088 | -0.127 | 0.303 | 0.424 | 3 | 6 |
| FINAL | followed >= 360 min | 382 | REM excess at 60 min | -0.131 | -0.347 | 0.084 | 0.233 | 4 | 6 |
| FINAL | followed >= 360 min | 382 | REM excess at 180 min | -0.054 | -0.408 | 0.3 | 0.766 | 3 | 6 |
| FINAL | followed >= 360 min | 382 | REM excess at 360 min | -0.436 | -0.975 | 0.104 | 0.113 | 4 | 6 |
| FINAL | followed >= 360 min | 382 | change 60 -> 360 min | -0.305 | -0.705 | 0.096 | 0.136 | 3 | 6 |
| pass2med_remclean | followed >= 180 min | 665 | REM excess at 60 min | -0.015 | -0.143 | 0.113 | 0.82 | 2 | 6 |
| pass2med_remclean | followed >= 180 min | 665 | REM excess at 180 min | 0.02 | -0.242 | 0.282 | 0.883 | 3 | 6 |
| pass2med_remclean | followed >= 180 min | 665 | change 60 -> 180 min | 0.034 | -0.182 | 0.251 | 0.755 | 3 | 6 |
| pass2med_remclean | followed >= 360 min | 373 | REM excess at 60 min | -0.017 | -0.163 | 0.13 | 0.822 | 3 | 6 |
| pass2med_remclean | followed >= 360 min | 373 | REM excess at 180 min | 0.074 | -0.234 | 0.382 | 0.639 | 3 | 6 |
| pass2med_remclean | followed >= 360 min | 373 | REM excess at 360 min | -0.23 | -0.615 | 0.156 | 0.243 | 3 | 6 |
| pass2med_remclean | followed >= 360 min | 373 | change 60 -> 360 min | -0.213 | -0.558 | 0.132 | 0.227 | 3 | 6 |

Battery rounds, the same events at 1 / 3 / 6 h (REM observed − expected, min):

| scores | n | h_min | REM_excess_mean | se | animals_below_0 | animals |
|---|---|---|---|---|---|---|
| FINAL | 88 | 60 | -1.168 | 0.242 | 6 | 6 |
| FINAL | 88 | 180 | -0.36 | 0.558 | 5 | 6 |
| FINAL | 88 | 360 | -0.842 | 0.936 | 4 | 6 |
| pass2med_remclean | 88 | 60 | -1.395 | 0.244 | 6 | 6 |
| pass2med_remclean | 88 | 180 | -0.931 | 0.502 | 5 | 6 |
| pass2med_remclean | 88 | 360 | -1.176 | 0.759 | 6 | 6 |

## 2. 24-h budget: next-day deviation on the preceding night's deviation

| scores | coverage_min | quantity | unit | n_animal_days | pooled_slope | pooled_ci_lo | pooled_ci_hi | within_animal_slope | within_ci_lo | within_ci_hi | within_p | animals_negative | animals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL | 0.5 | REM | min per recorded h (rate) | 56 | -0.977 | -1.792 | -0.162 | -0.865 | -1.991 | 0.261 | 0.132 | 4 | 6 |
| FINAL | 0.5 | REM | minutes over the recorded part | 56 | -0.997 | -1.824 | -0.171 | -0.877 | -1.952 | 0.198 | 0.11 | 4 | 6 |
| FINAL | 0.5 | NREM | min per recorded h (rate) | 56 | -0.443 | -0.718 | -0.169 | -0.327 | -0.622 | -0.033 | 0.03 | 5 | 6 |
| FINAL | 0.5 | NREM | minutes over the recorded part | 56 | -0.415 | -0.707 | -0.123 | -0.296 | -0.595 | 0.003 | 0.053 | 5 | 6 |
| FINAL | 0.8 | REM | min per recorded h (rate) | 37 | -0.998 | -2.198 | 0.202 | -1.08 | -2.731 | 0.571 | 0.2 | 5 | 5 |
| FINAL | 0.8 | REM | minutes over the recorded part | 37 | -1.063 | -2.261 | 0.134 | -1.173 | -2.987 | 0.641 | 0.205 | 5 | 5 |
| FINAL | 0.8 | NREM | min per recorded h (rate) | 37 | -0.477 | -0.867 | -0.087 | -0.364 | -0.892 | 0.163 | 0.176 | 5 | 5 |
| FINAL | 0.8 | NREM | minutes over the recorded part | 37 | -0.496 | -0.906 | -0.086 | -0.383 | -0.94 | 0.174 | 0.178 | 5 | 5 |
| pass2med_remclean | 0.5 | REM | min per recorded h (rate) | 56 | -0.628 | -1.255 | -0.0 | -0.407 | -1.314 | 0.5 | 0.379 | 4 | 6 |
| pass2med_remclean | 0.5 | REM | minutes over the recorded part | 56 | -0.669 | -1.285 | -0.054 | -0.473 | -1.359 | 0.413 | 0.296 | 5 | 6 |
| pass2med_remclean | 0.5 | NREM | min per recorded h (rate) | 56 | -0.629 | -0.831 | -0.426 | -0.562 | -0.8 | -0.325 | 0.0 | 6 | 6 |
| pass2med_remclean | 0.5 | NREM | minutes over the recorded part | 56 | -0.613 | -0.824 | -0.401 | -0.539 | -0.784 | -0.294 | 0.0 | 6 | 6 |
| pass2med_remclean | 0.8 | REM | min per recorded h (rate) | 37 | -1.131 | -1.895 | -0.367 | -1.067 | -2.194 | 0.06 | 0.064 | 5 | 5 |
| pass2med_remclean | 0.8 | REM | minutes over the recorded part | 37 | -1.171 | -1.937 | -0.406 | -1.111 | -2.305 | 0.083 | 0.068 | 5 | 5 |
| pass2med_remclean | 0.8 | NREM | min per recorded h (rate) | 37 | -0.903 | -1.15 | -0.655 | -0.878 | -1.26 | -0.497 | 0.0 | 5 | 5 |
| pass2med_remclean | 0.8 | NREM | minutes over the recorded part | 37 | -0.932 | -1.194 | -0.669 | -0.905 | -1.311 | -0.499 | 0.0 | 5 | 5 |

