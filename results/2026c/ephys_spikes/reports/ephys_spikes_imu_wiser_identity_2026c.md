# IMU movement vs WISER tag identity, cohort `2026c`

Generated 2026-09-28T23:27:19+00:00 by `ephys/imu_wiser_identity.py` (git 573d03c+dirty). Definitions in the script docstring. Blocks of 60 min; confident = r_best >= 0.5 and margin >= 0.25 (provisional). Expected tags from `wiser/configs/rat_identities_2026c.csv`.

| logger | blocks | confident | confident & agrees | confident & disagrees | median r(expected) | median margin (confident) |
|---|---|---|---|---|---|---|
| SF07 | 251 | 53 | 52 | 1 | 0.37 | 0.43 |
| SF08 | 249 | 59 | 59 | 0 | 0.39 | 0.45 |
| SF09 | 248 | 80 | 80 | 0 | 0.37 | 0.46 |
| SF10 | 242 | 82 | 81 | 1 | 0.42 | 0.53 |
| SF11 | 140 | 40 | 39 | 1 | 0.38 | 0.41 |
| SF12 | 240 | 89 | 89 | 0 | 0.49 | 0.48 |

| time of day | blocks | confident | agrees | disagrees |
|---|---|---|---|---|
| night 20-03 h | 528 | 300 | 300 | 0 |
| rounds / dawn / dusk 04-08, 17-19 h | 377 | 88 | 88 | 0 |
| day 09-16 h | 465 | 15 | 12 | 3 |

## Confident disagreements (3)

| block | logger | best tag (r) | expected (r) |
|---|---|---|---|
| 2026-09-01 15:00 | SF10 | 3062 (0.559) | 306b (-0.267) |
| 2026-09-05 10:00 | SF11 | 3079 (0.503) | 3058 (0.081) |
| 2026-09-08 12:00 | SF07 | 306b (0.531) | 3079 (0.148) |
