# Step B post-hoc diagnosis: where do the counter variants differ? (cohort 2026c)

**POST HOC** (added after Step B's results; not a pre-registered test). Driver `ephys/sleep_model_diag.py` (commit 03fab4d+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_explore_B_diag_20261009_0101`.

## Definitions

```
POST-HOC diagnosis of Step B (added 2026-10-08 after Step B's results; NOT a pre-registered test): where in the
sleep do the counter variants differ?

Step B's pre-registered comparison over ALL NREM steps could not separate the gradual wake discount (tau_w) from a hard
reset after wakes >= 7 min or from a pause (all within ~0.1 %), while "erase at every wake" was clearly worse. The
variants make different predictions only after wakes, so the same held-out comparison is split by what happened since
the last REM, per NREM step:
  after_long     a wake >= 420 s occurred since the last REM (or since the record start if no REM yet);
  after_medium   no such wake, but a wake of 120-419 s did;
  after_short    only wakes < 120 s (or none) since the last REM.
For each test fold (1..), the variant chosen by Step B's nested forward chaining in each family (B = discount grid,
reset, pause) is refitted on the fold's training blocks (the same fit as Step B) and its per-step held-out log-loss is
averaged within each subset; Delta and the bootstrap CI over folds as in Step B (Phase-2 `compare`), per-animal signs.
Usage: python ephys/sleep_model_diag.py [--scorings final pass2med] [--workers 6]
```

## Held-out comparisons by what happened since the last REM

| scores | subset | comparison | n_steps | n_rem | delta_pct | ci_lo_pct | ci_hi_pct | folds_better | folds | animals_better | holds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| final | after_long | B vs reset | 24497 | 174 | 0.2792 | -0.0889 | 0.6112 | 3 | 14 | 2 | False |
| final | after_long | B vs pause | 24497 | 174 | -0.3134 | -0.9247 | 0.3348 | 10 | 14 | 4 | False |
| final | after_long | reset vs pause | 24497 | 174 | -0.591 | -0.9724 | -0.1963 | 11 | 14 | 6 | True |
| final | after_medium | B vs reset | 13628 | 233 | -0.3077 | -0.5526 | -0.1076 | 11 | 15 | 6 | True |
| final | after_medium | B vs pause | 13628 | 233 | -0.3484 | -0.5712 | -0.138 | 10 | 15 | 5 | True |
| final | after_medium | reset vs pause | 13628 | 233 | -0.0409 | -0.2288 | 0.166 | 10 | 15 | 4 | False |
| final | after_short | B vs reset | 84610 | 2137 | -0.0822 | -0.1879 | 0.0463 | 12 | 15 | 6 | False |
| final | after_short | B vs pause | 84610 | 2137 | -0.0343 | -0.3087 | 0.4309 | 10 | 15 | 4 | False |
| final | after_short | reset vs pause | 84610 | 2137 | 0.048 | -0.2117 | 0.4832 | 8 | 15 | 2 | False |
| pass2med | after_long | B vs reset | 21971 | 190 | -0.0561 | -0.2234 | 0.1293 | 6 | 15 | 3 | False |
| pass2med | after_long | B vs pause | 21971 | 190 | -0.666 | -0.9058 | -0.3271 | 12 | 15 | 6 | True |
| pass2med | after_long | reset vs pause | 21971 | 190 | -0.6102 | -0.8124 | -0.3697 | 13 | 15 | 6 | True |
| pass2med | after_medium | B vs reset | 12211 | 220 | 0.0044 | -0.2795 | 0.3208 | 9 | 14 | 4 | False |
| pass2med | after_medium | B vs pause | 12211 | 220 | -0.0215 | -0.3482 | 0.3156 | 6 | 14 | 3 | False |
| pass2med | after_medium | reset vs pause | 12211 | 220 | -0.0259 | -0.3305 | 0.3734 | 5 | 14 | 4 | False |
| pass2med | after_short | B vs reset | 89122 | 2256 | 0.0478 | -0.0084 | 0.1161 | 6 | 15 | 1 | False |
| pass2med | after_short | B vs pause | 89122 | 2256 | 0.0638 | -0.2275 | 0.5567 | 11 | 15 | 2 | False |
| pass2med | after_short | reset vs pause | 89122 | 2256 | 0.016 | -0.2391 | 0.4488 | 11 | 15 | 3 | False |

