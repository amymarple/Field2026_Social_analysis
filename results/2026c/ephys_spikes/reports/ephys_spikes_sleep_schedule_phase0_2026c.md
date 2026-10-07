# Internal sleep schedule — Phase 0: definitions and counts (cohort 2026c)

Plan: [implementation_plan/2026-10-07-sleep-internal-schedule.md](../../../../implementation_plan/2026-10-07-sleep-internal-schedule.md). Driver: `ephys/sleep_schedule.py phase0` (commit 9465206+dirty). Bulk: `D:\Field2026_analysis_out\2026c\sleep_schedule_phase0_20261007_1818`.

**Phase 0 computes no outcome**: no REM hazard, no history effect, no payback. Only the units and how many there are.

## Inclusion

- The FINAL sleep scores and their exclusions, cut at 2026-09-11 19:40 (the females).
- 169 sessions → 129 records, 1227 h; unknown seconds inside records (file splits ≤ 60 s): 670.

| animal | records | hours | wakes_ge_10min | usable_gaps |
|---|---|---|---|---|
| SF07 | 23 | 206.0 | 74 | 17 |
| SF08 | 24 | 232.8 | 86 | 20 |
| SF09 | 23 | 233.9 | 70 | 19 |
| SF10 | 25 | 230.5 | 74 | 20 |
| SF11 | 15 | 127.0 | 50 | 13 |
| SF12 | 19 | 196.4 | 75 | 15 |

## Wake bouts inside records (durations as observed; curve 2 uses d continuously)

Reference marks from Watson et al. 2016: < 40 s = microarousal range; > 120 s ends a SLEEP; ≥ 7 min = the WAKE of a WAKE–SLEEP cycle.

| d_class | dark | light | followed by NREM in the record |
|---|---|---|---|
| < 40 s (MA range) | 1256 | 6257 | 6837 |
| 40-120 s | 601 | 1506 | 2097 |
| 2-7 min | 182 | 541 | 705 |
| >= 7 min | 296 | 261 | 524 |

## Episode units (Watson et al. 2016) for the microarousal limit m = 40 s (primary), 100 s (our pipeline's code), 20 s (Park)

Counts:

| unit | 20 | 40 | 100 |
|---|---|---|---|
| ma | 2877 | 4860 | 6256 |
| nrem_episodes | 8522 | 6539 | 5143 |
| packets | 11399 | 11399 | 11399 |
| rem_cycles | 3642 | 3642 | 3642 |
| sleep | 555 | 555 | 555 |
| wake_sleep | 191 | 191 | 191 |

Median durations at m = 40 s (min):

| unit | median_min |
|---|---|
| ma | 0.28 |
| nrem_episodes | 3.03 |
| packets | 1.35 |
| rem_cycles | 3.56 |
| sleep | 41.47 |
| wake_sleep | 19.25 |

## Gaps between records (battery rounds and others)

A gap is a handled interruption of unknown state. WISER columns are descriptive only (share of gap minutes with ≥ 14 in movement of the 1-min median; share of gap seconds flagged `m_handling`). `prev_autostop` = the cell before the gap auto-stopped (unobserved, undisturbed time before the round).

| cause | kind | usable | n | median_gap_min | with_swap | prev_autostop | median_wiser_moving | median_wiser_handling |
|---|---|---|---|---|---|---|---|---|
| no_handling_recorded | evening | False | 1 | 1.01 | 0 | 0 | 0.0 | 0.0 |
| no_handling_recorded | other | False | 6 | 261.05 | 0 | 1 | 0.2 | 0.48 |
| no_handling_recorded | other | True | 2 | 118.77 | 0 | 0 | 0.25 | 0.08 |
| probe_move | evening | True | 2 | 49.51 | 2 | 0 | 0.25 | 1.0 |
| probe_move | morning | True | 1 | 52.11 | 1 | 0 | 0.21 | 0.99 |
| probe_move | other | False | 1 | 398.0 | 0 | 0 | 0.03 | 0.05 |
| probe_move | other | True | 5 | 15.67 | 0 | 0 | 0.33 | 1.0 |
| round_inferred | evening | False | 4 | 54.86 | 0 | 0 | 0.21 | 1.0 |
| round_inferred | evening | True | 9 | 70.71 | 0 | 0 | 0.31 | 0.42 |
| round_inferred | morning | True | 3 | 73.57 | 0 | 0 | 0.18 | 1.0 |
| round_logged | evening | False | 3 | 854.27 | 3 | 0 | 0.34 | 0.06 |
| round_logged | evening | True | 35 | 50.43 | 35 | 2 | 0.23 | 1.0 |
| round_logged | morning | True | 47 | 60.31 | 47 | 5 | 0.23 | 1.0 |
| round_logged | other | False | 4 | 373.15 | 4 | 0 | 0.15 | 0.13 |

## Compensation windows available (A = 3 h before, B = the next 1 h / 3 h; ≥ 80 % recorded)

| setting | A_h | B_h | windows |
|---|---|---|---|
| across gap | 3 | 1 | 101 |
| across gap | 3 | 3 | 98 |
| within record | 3 | 1 | 794 |
| within record | 3 | 3 | 557 |

## Next

Phase 1 (curve 1: memory curve, clock, cycles ahead, own vs shared; refractoriness; opportunity / timing split) after the user has seen these counts.
