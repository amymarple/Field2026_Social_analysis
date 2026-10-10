# Awake ripples at night across the paddock (cohort 2026c) — Phase 0: counts, no maps

Plan: [2026-10-10-awake-ripple-map.md](../../../../implementation_plan/2026-10-10-awake-ripple-map.md) (Amendment 1 after the Codex audit). Driver `ephys/awake_ripple_map.py phase0`; run `D:\Field2026_analysis_out\2026c\awake_ripple_map_20261010_1452`.

## Per animal

| animal | nights | quiet wake h | in the field h | qSWR | in the field | in the houses | trials ≥ 10 min | excursions | field bins ≥ 120 s | enters inference |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| SF07 | 10 | 1.1 | 0.1 | 1152 | 32 | 1120 | 39 | 228 | 1 | no |
| SF08 | 12 | 0.6 | 0.0 | 3115 | 81 | 3034 | 37 | 293 | 0 | no |
| SF09 | 12 | 1.2 | 0.2 | 4334 | 887 | 3447 | 36 | 314 | 0 | no |
| SF10 | 12 | 0.7 | 0.0 | 3061 | 70 | 2991 | 46 | 309 | 0 | no |
| SF11 | 6 | 0.1 | 0.0 | 295 | 0 | 295 | 30 | 129 | 0 | no |
| SF12 | 9 | 0.6 | 0.0 | 1993 | 29 | 1964 | 36 | 232 | 0 | no |

Amendment 2 definition (the production's kept rule in non-locomotor, theta-detectable wake):

| animal | non-locomotor wake h | in the field h | awake ripples | in the field | in the houses | field bins >= 120 s | enters inference |
|---|---:|---:|---:|---:|---:|---:|:---:|
| SF07 | 2.9 | 0.5 | 1311 | 35 | 1276 | 2 | no |
| SF08 | 3.5 | 0.9 | 17128 | 4897 | 12231 | 7 | no |
| SF09 | 8.9 | 2.4 | 24966 | 7633 | 17333 | 15 | no |
| SF10 | 4.6 | 0.8 | 19465 | 3618 | 15847 | 4 | no |
| SF11 | 0.2 | 0.0 | 300 | 0 | 300 | 0 | no |
| SF12 | 2.8 | 0.3 | 8725 | 1157 | 7568 | 1 | no |

## Where the night's wake seconds are lost (median over animal-nights)

- in handling windows: 0.054
- theta above the session's NREM 95th pct.: 0.928
- head IMU locomoting (of IMU-ok wake): 0.200
- not SWR-covered: 0.000
- undetectable (theta / LFP-EMG above the session's NREM 95th pct.): 0.983
- no position: 0.024
- head IMU not ok: 0.036
- IMU-still share of IMU-ok wake: 0.032

Definitions in the driver's docstring and the plan. No rate, map or place statistic is computed in Phase 0.

