# REM within sleep episodes: a time course beyond the count model? (cohort 2026c; episode rule nsw)

Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) §10 revision 4 (rules written before results), amendment 1 (§10.7, post hoc): episode boundaries from night_sleep_wiser. Driver `ephys/sleep_ramp.py run --episode-rule nsw` (commit 21626d5+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_ramp_nsw_20261010_2352`; runtime 8 min; figure [ephys_spikes_sleep_ramp_nsw_2026c.png](../figures/ephys_spikes_sleep_ramp_nsw_2026c.png). **Technical ledger.**

## Reading (main session, 2026-10-11; claims #71–#73; read with the pre-registered run, [plain](ephys_spikes_sleep_ramp_2026c.md))

This run uses amendment 1 (plan §10.7, post hoc): episode boundaries from night_sleep_wiser's long wakes. Its main
onsets match that run's MSO on 45 of 45 nights; the pre-registered rule matched 10. The pooled class **natural**
(nap + main + day) uses no future information. The nap / main split does, because naps end in a long wake by
definition.

**1. REM is held back for the first ~20 min of an episode, then catches up (#71, Candidate).**
- In natural episodes, REM entry per NREM step is below the count model's held-out prediction:
  - 0–10 min: O/E 0.40 [0.18, 0.66] on FINAL, 0.29 [0.10, 0.48] on pass2med;
  - 10–20 min: O/E 0.73 [0.51, 0.97] and 0.67 [0.50, 0.89];
  - the ramp rule passes: 5/6 animals on FINAL, 6/6 on pass2med.
- At 20–30 min REM entry runs above the prediction (O/E 1.30 [0.97, 1.69] / 1.30 [1.01, 1.63]); afterwards it sits near
  the model.
- The simulator agrees in the first bin: the REM share of sleep at 0–10 min is 0.009 vs a simulated 0.024–0.047
  (0.008 vs 0.023–0.040).
- The pre-registered rule shows the same direction (O/E 0.27 / 0.36 at 0–10 min, 0.63 / 0.59 at 10–20 min, 1.17 / 1.25
  at 20–30 min). There its first bin is too small to judge (E ≈ 11), but the simulator test flags it instead: the REM
  share at 0–20 min is below the band on both scorings.
- **Read:** after a long wake the rats almost never enter REM in the first 10 min of sleep. The count model, whose
  count is not fully emptied by a 30-min wake (it keeps e^−3 ≈ 5 %), lets REM in too early and then too smoothly.
- **Held out, the episode clock helps on one scoring only.**
  - Natural episodes: FINAL REM log-loss −0.48 % [−0.89, −0.09], 6/6 animals; pass2med −0.29 % [−0.74, +0.16], 5/6.
  - With post-round included (secondary): both hold (−0.21 % [−0.39, −0.03] / −0.22 % [−0.36, −0.09], 6/6). There it
    overlaps the known post-round dynamics (#60, #61).
  - In the pre-registered run neither primary comparison holds.
  - By the plan's table this is a residual without held-out value on both scorings: described, not yet a model term.

**2. No ramp-down detected (#72).** Later in episodes REM entry follows the model:
- natural, 1–6 h: O/E 0.77–1.13, every CI covering 1;
- post-round, 3–6 h and beyond: O/E ≈ 1.0–1.1.
The end-aligned description (selection-prone) shows the opposite of a ramp-down before a nap ends: O/E 1.6 in the last
10 min before the ending wake, because REM often exits into waking.

**3. Naps vs main sleep (#73, Candidate).** Both start with the same suppression:
- main 10–20 min: O/E 0.38 / 0.41;
- nap 0–10 min: 0.55 / 0.09;
- both run above the model at 20–30 min.
Naps last 24 min (median), so most end inside or just after the suppressed stretch. Their low REM share fits the
short-episode reading. Two things are not settled:
- under the pre-registered rule the simulator misses the nap shape (late share above the band);
- the nap / main split depends on how the episode ends.
So a nap-specific organisation is neither shown nor excluded.

**Limits:**
- Episode classes beyond "natural" use the future.
- The day class is small (20–24 episodes).
- Main sleep is mostly cut by the morning round (median 80 min).
- The episode clock was tested as one 3-hinge shape.

## Verdicts

(A) ramp residual and (B) shape not reproduced, per class (REM entry):

| cls | A_ramp_residual_REM | B_shape_not_reproduced |
|---|---|---|
| natural | True | False |
| nap | False | False |
| main | False | False |
| day | False | False |
| post-round | False | False |

(C) the episode clock on held-out steps (REM log-loss):

| subset | holds_both | numbers |
|---|---|---|
| natural (nap + main + day) | False | final -0.483 % [-0.885, -0.085], 6/6; pass2med -0.287 % [-0.739, +0.156], 5/6 |
| natural + post-round | True | final -0.206 % [-0.388, -0.034], 6/6; pass2med -0.216 % [-0.358, -0.085], 6/6 |

## Episodes

| cls | episodes | animals | median_min | observed_end | scores |
|---|---|---|---|---|---|
| day | 24 | 6 | 192.183 | 0.25 | final |
| main | 57 | 6 | 80.05 | 0.105 | final |
| nap | 156 | 6 | 24.358 | 1.0 | final |
| other | 27 | 6 | 169.533 | 0.37 | final |
| post-round | 77 | 6 | 264.933 | 0.571 | final |
| day | 20 | 6 | 283.508 | 0.25 | pass2med |
| main | 57 | 6 | 83.783 | 0.088 | pass2med |
| nap | 166 | 6 | 24.825 | 1.0 | pass2med |
| other | 29 | 6 | 169.317 | 0.345 | pass2med |
| post-round | 79 | 6 | 211.917 | 0.57 | pass2med |

Main onsets vs night_sleep_wiser's mso (FINAL):

| nights_with_mso | main_onset_within_60s | share |
|---|---|---|
| 45 | 45 | 1.0 |

## (A) REM entry, observed vs held-out B-full, by minutes since onset

| scores | cls | bin_min | at_risk | steps | O | E | oe | lo | hi | obs_per_nrem_h | pred_per_nrem_h |
|---|---|---|---|---|---|---|---|---|---|---|---|
| final | natural | 0-10 | 237 | 7046 | 9 | 22.561 | 0.399 | 0.176 | 0.663 | 0.46 | 1.153 |
| final | natural | 10-20 | 204 | 5413 | 44 | 59.949 | 0.734 | 0.514 | 0.967 | 2.926 | 3.987 |
| final | natural | 20-30 | 164 | 3734 | 55 | 42.272 | 1.301 | 0.969 | 1.687 | 5.303 | 4.075 |
| final | natural | 30-45 | 124 | 4012 | 47 | 57.29 | 0.82 | 0.568 | 1.125 | 4.217 | 5.141 |
| final | natural | 45-60 | 81 | 2698 | 38 | 43.838 | 0.867 | 0.631 | 1.167 | 5.07 | 5.849 |
| final | natural | 60-90 | 56 | 3874 | 69 | 82.32 | 0.838 | 0.604 | 1.115 | 6.412 | 7.65 |
| final | natural | 90-120 | 41 | 2840 | 43 | 56.208 | 0.765 | 0.527 | 1.031 | 5.451 | 7.125 |
| final | natural | 120-180 | 27 | 3028 | 64 | 74.634 | 0.858 | 0.556 | 1.335 | 7.609 | 8.873 |
| final | natural | 180-240 | 16 | 1448 | 33 | 35.578 | 0.928 | 0.809 | 1.088 | 8.204 | 8.845 |
| final | natural | 240-360 | 12 | 1721 | 48 | 42.623 | 1.126 | 0.576 | 1.698 | 10.041 | 8.916 |
| final | natural | >=360 | 8 | 573 | 11 | 12.167 | 0.904 | 0.884 | 0.941 | 6.911 | 7.644 |
| final | nap | 0-10 | 156 | 4622 | 5 | 9.079 | 0.551 | 0.115 | 1.081 | 0.389 | 0.707 |
| final | nap | 10-20 | 129 | 3491 | 26 | 28.716 | 0.905 | 0.608 | 1.261 | 2.681 | 2.961 |
| final | nap | 20-30 | 91 | 2092 | 32 | 19.09 | 1.676 | 1.167 | 2.338 | 5.507 | 3.285 |
| final | nap | 30-45 | 56 | 1539 | 18 | 13.059 | 1.378 | 0.816 | 2.161 | 4.211 | 3.055 |
| final | nap | 45-60 | 24 | 398 | 7 | 3.597 | 1.946 | 0.854 | 3.8 | 6.332 | 3.254 |
| final | nap | 60-90 | 5 | 8 | 0 | 0.046 | 0.0 | 0.0 | 0.0 | 0.0 | 2.083 |
| final | nap | 90-120 | 2 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| final | nap | 120-180 | 2 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| final | nap | 180-240 | 1 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| final | nap | 240-360 | 0 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| final | nap | >=360 | 0 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| final | main | 0-10 | 57 | 1734 | 0 | 6.036 | 0.0 | 0.0 | 0.0 | 0.0 | 1.253 |
| final | main | 10-20 | 55 | 1467 | 8 | 21.213 | 0.377 | 0.17 | 0.617 | 1.963 | 5.206 |
| final | main | 20-30 | 53 | 1293 | 14 | 15.399 | 0.909 | 0.564 | 1.36 | 3.898 | 4.288 |
| final | main | 30-45 | 51 | 1970 | 20 | 30.694 | 0.652 | 0.37 | 0.995 | 3.655 | 5.609 |
| final | main | 45-60 | 43 | 1831 | 22 | 28.419 | 0.774 | 0.554 | 1.067 | 4.326 | 5.588 |
| final | main | 60-90 | 37 | 3028 | 46 | 57.054 | 0.806 | 0.562 | 1.177 | 5.469 | 6.783 |
| final | main | 90-120 | 26 | 2038 | 27 | 38.366 | 0.704 | 0.453 | 1.006 | 4.769 | 6.777 |
| final | main | 120-180 | 12 | 1621 | 26 | 38.046 | 0.683 | 0.385 | 1.317 | 5.774 | 8.449 |
| final | main | 180-240 | 3 | 239 | 3 | 3.365 | 0.892 | 0.0 | 1.1 | 4.519 | 5.068 |
| final | main | 240-360 | 1 | 61 | 2 | 1.015 | 1.97 | 1.97 | 1.97 | 11.803 | 5.99 |
| final | main | >=360 | 0 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| final | day | 0-10 | 24 | 690 | 4 | 7.446 | 0.537 | 0.175 | 1.01 | 2.087 | 3.885 |
| final | day | 10-20 | 20 | 455 | 10 | 10.02 | 0.998 | 0.502 | 1.509 | 7.912 | 7.928 |
| final | day | 20-30 | 20 | 349 | 9 | 7.782 | 1.156 | 0.503 | 1.911 | 9.284 | 8.028 |
| final | day | 30-45 | 17 | 503 | 9 | 13.537 | 0.665 | 0.364 | 0.952 | 6.441 | 9.688 |
| final | day | 45-60 | 14 | 469 | 9 | 11.822 | 0.761 | 0.352 | 1.4 | 6.908 | 9.074 |
| final | day | 60-90 | 14 | 838 | 23 | 25.22 | 0.912 | 0.508 | 1.185 | 9.881 | 10.834 |
| final | day | 90-120 | 13 | 802 | 16 | 17.842 | 0.897 | 0.611 | 1.459 | 7.182 | 8.009 |
| final | day | 120-180 | 13 | 1407 | 38 | 36.589 | 1.039 | 0.73 | 1.663 | 9.723 | 9.362 |
| final | day | 180-240 | 12 | 1209 | 30 | 32.214 | 0.931 | 0.854 | 1.101 | 8.933 | 9.592 |
| final | day | 240-360 | 11 | 1660 | 46 | 41.608 | 1.106 | 0.835 | 1.617 | 9.976 | 9.023 |
| final | day | >=360 | 8 | 573 | 11 | 12.167 | 0.904 | 0.893 | 0.941 | 6.911 | 7.644 |
| final | post-round | 0-10 | 77 | 1900 | 13 | 15.545 | 0.836 | 0.478 | 1.265 | 2.463 | 2.945 |
| final | post-round | 10-20 | 61 | 801 | 6 | 10.553 | 0.569 | 0.148 | 1.176 | 2.697 | 4.743 |
| final | post-round | 20-30 | 58 | 1381 | 17 | 12.68 | 1.341 | 0.769 | 1.971 | 4.432 | 3.305 |
| final | post-round | 30-45 | 57 | 2738 | 50 | 41.009 | 1.219 | 0.943 | 1.551 | 6.574 | 5.392 |
| final | post-round | 45-60 | 56 | 2635 | 67 | 53.804 | 1.245 | 0.986 | 1.592 | 9.154 | 7.351 |
| final | post-round | 60-90 | 53 | 5021 | 116 | 104.447 | 1.111 | 0.895 | 1.392 | 8.317 | 7.489 |
| final | post-round | 90-120 | 46 | 4725 | 121 | 107.115 | 1.13 | 0.937 | 1.354 | 9.219 | 8.161 |
| final | post-round | 120-180 | 42 | 9249 | 218 | 228.236 | 0.955 | 0.806 | 1.126 | 8.485 | 8.884 |
| final | post-round | 180-240 | 41 | 8369 | 217 | 202.023 | 1.074 | 0.953 | 1.209 | 9.334 | 8.69 |
| final | post-round | 240-360 | 39 | 14791 | 390 | 369.248 | 1.056 | 0.928 | 1.19 | 9.492 | 8.987 |
| final | post-round | >=360 | 33 | 20820 | 572 | 514.4 | 1.112 | 1.009 | 1.234 | 9.89 | 8.895 |
| pass2med | natural | 0-10 | 243 | 7333 | 7 | 24.377 | 0.287 | 0.101 | 0.484 | 0.344 | 1.197 |
| pass2med | natural | 10-20 | 207 | 5628 | 47 | 70.161 | 0.67 | 0.495 | 0.887 | 3.006 | 4.488 |
| pass2med | natural | 20-30 | 170 | 3953 | 64 | 49.168 | 1.302 | 1.013 | 1.633 | 5.828 | 4.478 |
| pass2med | natural | 30-45 | 130 | 4359 | 56 | 73.9 | 0.758 | 0.563 | 1.015 | 4.625 | 6.103 |
| pass2med | natural | 45-60 | 89 | 2776 | 54 | 48.906 | 1.104 | 0.864 | 1.401 | 7.003 | 6.342 |
| pass2med | natural | 60-90 | 57 | 4007 | 82 | 100.229 | 0.818 | 0.648 | 1.038 | 7.367 | 9.005 |
| pass2med | natural | 90-120 | 39 | 2899 | 58 | 75.391 | 0.769 | 0.591 | 0.988 | 7.202 | 9.362 |
| pass2med | natural | 120-180 | 25 | 3237 | 83 | 87.727 | 0.946 | 0.727 | 1.223 | 9.231 | 9.756 |
| pass2med | natural | 180-240 | 15 | 1758 | 46 | 51.447 | 0.894 | 0.826 | 0.997 | 9.42 | 10.535 |
| pass2med | natural | 240-360 | 12 | 2275 | 61 | 64.509 | 0.946 | 0.582 | 1.374 | 9.653 | 10.208 |
| pass2med | natural | >=360 | 8 | 637 | 16 | 15.987 | 1.001 | 0.68 | 1.428 | 9.042 | 9.035 |
| pass2med | nap | 0-10 | 166 | 4769 | 1 | 11.1 | 0.09 | 0.0 | 0.299 | 0.075 | 0.838 |
| pass2med | nap | 10-20 | 134 | 3595 | 32 | 37.39 | 0.856 | 0.589 | 1.179 | 3.204 | 3.744 |
| pass2med | nap | 20-30 | 98 | 2183 | 34 | 20.723 | 1.641 | 1.171 | 2.182 | 5.607 | 3.417 |
| pass2med | nap | 30-45 | 62 | 1655 | 20 | 17.362 | 1.152 | 0.718 | 1.845 | 4.35 | 3.777 |
| pass2med | nap | 45-60 | 29 | 441 | 9 | 4.765 | 1.889 | 0.896 | 3.198 | 7.347 | 3.89 |
| pass2med | nap | 60-90 | 8 | 12 | 0 | 0.103 | 0.0 | 0.0 | 0.0 | 0.0 | 3.093 |
| pass2med | nap | 90-120 | 2 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| pass2med | nap | 120-180 | 2 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| pass2med | nap | 180-240 | 1 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| pass2med | nap | 240-360 | 0 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| pass2med | nap | >=360 | 0 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| pass2med | main | 0-10 | 57 | 1885 | 1 | 5.938 | 0.168 | 0.0 | 0.526 | 0.191 | 1.134 |
| pass2med | main | 10-20 | 56 | 1564 | 9 | 21.968 | 0.41 | 0.183 | 0.661 | 2.072 | 5.057 |
| pass2med | main | 20-30 | 55 | 1362 | 18 | 17.9 | 1.006 | 0.677 | 1.385 | 4.758 | 4.731 |
| pass2med | main | 30-45 | 53 | 2165 | 27 | 37.073 | 0.728 | 0.475 | 1.037 | 4.49 | 6.165 |
| pass2med | main | 45-60 | 48 | 1889 | 32 | 34.185 | 0.936 | 0.682 | 1.26 | 6.098 | 6.515 |
| pass2med | main | 60-90 | 37 | 3131 | 60 | 67.799 | 0.885 | 0.684 | 1.14 | 6.899 | 7.796 |
| pass2med | main | 90-120 | 26 | 2080 | 41 | 51.937 | 0.789 | 0.561 | 1.066 | 7.096 | 8.989 |
| pass2med | main | 120-180 | 12 | 1730 | 41 | 40.51 | 1.012 | 0.782 | 1.282 | 8.532 | 8.43 |
| pass2med | main | 180-240 | 3 | 299 | 6 | 5.338 | 1.124 | 0.0 | 1.189 | 7.224 | 6.427 |
| pass2med | main | 240-360 | 1 | 73 | 2 | 1.244 | 1.608 | 1.608 | 1.608 | 9.863 | 6.132 |
| pass2med | main | >=360 | 0 | 0 | 0 | 0.0 | nan | nan | nan | nan | nan |
| pass2med | day | 0-10 | 20 | 679 | 5 | 7.339 | 0.681 | 0.367 | 1.044 | 2.651 | 3.891 |
| pass2med | day | 10-20 | 17 | 469 | 6 | 10.803 | 0.555 | 0.216 | 0.98 | 4.606 | 8.293 |
| pass2med | day | 20-30 | 17 | 408 | 12 | 10.545 | 1.138 | 0.566 | 1.781 | 10.588 | 9.304 |
| pass2med | day | 30-45 | 15 | 539 | 9 | 19.465 | 0.462 | 0.226 | 0.738 | 6.011 | 13.001 |
| pass2med | day | 45-60 | 12 | 446 | 13 | 9.956 | 1.306 | 0.89 | 1.883 | 10.493 | 8.036 |
| pass2med | day | 60-90 | 12 | 864 | 22 | 32.326 | 0.681 | 0.37 | 0.906 | 9.167 | 13.469 |
| pass2med | day | 90-120 | 11 | 819 | 17 | 23.454 | 0.725 | 0.54 | 1.047 | 7.473 | 10.31 |
| pass2med | day | 120-180 | 11 | 1507 | 42 | 47.217 | 0.89 | 0.642 | 1.359 | 10.033 | 11.279 |
| pass2med | day | 180-240 | 11 | 1459 | 40 | 46.109 | 0.868 | 0.808 | 0.92 | 9.87 | 11.377 |
| pass2med | day | 240-360 | 11 | 2202 | 59 | 63.265 | 0.933 | 0.746 | 1.317 | 9.646 | 10.343 |
| pass2med | day | >=360 | 8 | 637 | 16 | 15.987 | 1.001 | 0.852 | 1.428 | 9.042 | 9.035 |
| pass2med | post-round | 0-10 | 79 | 2074 | 17 | 22.2 | 0.766 | 0.498 | 1.077 | 2.951 | 3.853 |
| pass2med | post-round | 10-20 | 66 | 833 | 7 | 14.023 | 0.499 | 0.126 | 1.039 | 3.025 | 6.061 |
| pass2med | post-round | 20-30 | 62 | 1480 | 21 | 15.218 | 1.38 | 0.904 | 2.005 | 5.108 | 3.702 |
| pass2med | post-round | 30-45 | 61 | 2813 | 52 | 47.31 | 1.099 | 0.854 | 1.379 | 6.655 | 6.055 |
| pass2med | post-round | 45-60 | 57 | 2662 | 69 | 60.652 | 1.138 | 0.933 | 1.4 | 9.331 | 8.202 |
| pass2med | post-round | 60-90 | 52 | 4950 | 117 | 123.062 | 0.951 | 0.809 | 1.118 | 8.509 | 8.95 |
| pass2med | post-round | 90-120 | 47 | 4761 | 121 | 131.286 | 0.922 | 0.789 | 1.067 | 9.149 | 9.927 |
| pass2med | post-round | 120-180 | 44 | 9239 | 225 | 270.521 | 0.832 | 0.717 | 0.959 | 8.767 | 10.541 |
| pass2med | post-round | 180-240 | 41 | 8399 | 221 | 232.517 | 0.95 | 0.848 | 1.068 | 9.473 | 9.966 |
| pass2med | post-round | 240-360 | 38 | 14198 | 366 | 376.016 | 0.973 | 0.872 | 1.078 | 9.28 | 9.534 |
| pass2med | post-round | >=360 | 33 | 19836 | 546 | 539.145 | 1.013 | 0.915 | 1.118 | 9.909 | 9.785 |

Qualifying runs of adjacent bins (both scorings, same direction):

| cls | outcome | bins | direction | animals | passes | bins_min |
|---|---|---|---|---|---|---|
| natural | REM | 0,1 | - | final 5/6; pass2med 6/6 | True | 0-10 + 10-20 |
| post-round | WAKE | 0,1 | + | final 6/6; pass2med 6/6 | True | 0-10 + 10-20 |

## (A) WAKE, observed vs held-out B-full

| scores | cls | bin_min | O | E | oe | lo | hi |
|---|---|---|---|---|---|---|---|
| final | natural | 0-10 | 242 | 447.93 | 0.54 | 0.473 | 0.612 |
| final | natural | 10-20 | 243 | 239.31 | 1.015 | 0.889 | 1.153 |
| final | natural | 20-30 | 167 | 165.899 | 1.007 | 0.846 | 1.167 |
| final | natural | 30-45 | 180 | 165.051 | 1.091 | 0.959 | 1.232 |
| final | natural | 45-60 | 98 | 103.434 | 0.947 | 0.75 | 1.137 |
| final | natural | 60-90 | 104 | 120.888 | 0.86 | 0.679 | 1.059 |
| final | natural | 90-120 | 108 | 88.285 | 1.223 | 0.968 | 1.532 |
| final | natural | 120-180 | 108 | 98.382 | 1.098 | 0.884 | 1.295 |
| final | natural | 180-240 | 43 | 47.659 | 0.902 | 0.654 | 1.145 |
| final | natural | 240-360 | 49 | 56.027 | 0.875 | 0.644 | 1.038 |
| final | natural | >=360 | 24 | 19.278 | 1.245 | 1.035 | 1.456 |
| final | nap | 0-10 | 139 | 307.775 | 0.452 | 0.38 | 0.533 |
| final | nap | 10-20 | 155 | 158.256 | 0.979 | 0.832 | 1.124 |
| final | nap | 20-30 | 82 | 98.483 | 0.833 | 0.692 | 0.978 |
| final | nap | 30-45 | 77 | 73.741 | 1.044 | 0.828 | 1.278 |
| final | nap | 45-60 | 18 | 20.641 | 0.872 | 0.552 | 1.196 |
| final | nap | 60-90 | 1 | 0.453 | 2.206 | 2.206 | 2.206 |
| final | nap | 90-120 | 0 | 0.0 | nan | nan | nan |
| final | nap | 120-180 | 0 | 0.0 | nan | nan | nan |
| final | nap | 180-240 | 0 | 0.0 | nan | nan | nan |
| final | nap | 240-360 | 0 | 0.0 | nan | nan | nan |
| final | nap | >=360 | 0 | 0.0 | nan | nan | nan |
| final | main | 0-10 | 84 | 107.625 | 0.78 | 0.623 | 0.947 |
| final | main | 10-20 | 61 | 64.194 | 0.95 | 0.729 | 1.18 |
| final | main | 20-30 | 76 | 55.228 | 1.376 | 1.078 | 1.713 |
| final | main | 30-45 | 84 | 75.783 | 1.108 | 0.937 | 1.298 |
| final | main | 45-60 | 67 | 67.526 | 0.992 | 0.749 | 1.282 |
| final | main | 60-90 | 78 | 95.855 | 0.814 | 0.607 | 1.065 |
| final | main | 90-120 | 74 | 63.052 | 1.174 | 0.902 | 1.464 |
| final | main | 120-180 | 62 | 51.0 | 1.216 | 0.931 | 1.481 |
| final | main | 180-240 | 11 | 10.403 | 1.057 | 0.0 | 1.304 |
| final | main | 240-360 | 1 | 2.151 | 0.465 | 0.465 | 0.465 |
| final | main | >=360 | 0 | 0.0 | nan | nan | nan |
| final | day | 0-10 | 19 | 32.53 | 0.584 | 0.426 | 0.723 |
| final | day | 10-20 | 27 | 16.86 | 1.601 | 1.059 | 2.16 |
| final | day | 20-30 | 9 | 12.188 | 0.738 | 0.242 | 1.281 |
| final | day | 30-45 | 19 | 15.527 | 1.224 | 0.944 | 1.439 |
| final | day | 45-60 | 13 | 15.267 | 0.851 | 0.481 | 1.348 |
| final | day | 60-90 | 25 | 24.58 | 1.017 | 0.753 | 1.372 |
| final | day | 90-120 | 34 | 25.233 | 1.347 | 0.918 | 2.074 |
| final | day | 120-180 | 46 | 47.382 | 0.971 | 0.734 | 1.126 |
| final | day | 180-240 | 32 | 37.256 | 0.859 | 0.664 | 1.092 |
| final | day | 240-360 | 48 | 53.876 | 0.891 | 0.765 | 1.028 |
| final | day | >=360 | 24 | 19.278 | 1.245 | 1.14 | 1.456 |
| final | post-round | 0-10 | 101 | 76.304 | 1.324 | 1.093 | 1.568 |
| final | post-round | 10-20 | 53 | 29.699 | 1.785 | 1.384 | 2.284 |
| final | post-round | 20-30 | 64 | 61.473 | 1.041 | 0.769 | 1.359 |
| final | post-round | 30-45 | 107 | 94.307 | 1.135 | 0.961 | 1.328 |
| final | post-round | 45-60 | 85 | 80.089 | 1.061 | 0.829 | 1.309 |
| final | post-round | 60-90 | 113 | 139.116 | 0.812 | 0.653 | 0.983 |
| final | post-round | 90-120 | 75 | 125.081 | 0.6 | 0.496 | 0.696 |
| final | post-round | 120-180 | 232 | 253.801 | 0.914 | 0.779 | 1.054 |
| final | post-round | 180-240 | 251 | 243.161 | 1.032 | 0.918 | 1.137 |
| final | post-round | 240-360 | 520 | 462.594 | 1.124 | 1.015 | 1.239 |
| final | post-round | >=360 | 818 | 780.467 | 1.048 | 0.963 | 1.138 |
| pass2med | natural | 0-10 | 212 | 464.89 | 0.456 | 0.398 | 0.516 |
| pass2med | natural | 10-20 | 227 | 243.538 | 0.932 | 0.806 | 1.063 |
| pass2med | natural | 20-30 | 144 | 168.079 | 0.857 | 0.719 | 0.999 |
| pass2med | natural | 30-45 | 171 | 166.693 | 1.026 | 0.894 | 1.165 |
| pass2med | natural | 45-60 | 91 | 100.067 | 0.909 | 0.695 | 1.131 |
| pass2med | natural | 60-90 | 92 | 114.692 | 0.802 | 0.657 | 0.949 |
| pass2med | natural | 90-120 | 99 | 83.349 | 1.188 | 0.936 | 1.431 |
| pass2med | natural | 120-180 | 94 | 99.571 | 0.944 | 0.74 | 1.145 |
| pass2med | natural | 180-240 | 45 | 60.787 | 0.74 | 0.484 | 1.032 |
| pass2med | natural | 240-360 | 73 | 86.651 | 0.842 | 0.7 | 1.002 |
| pass2med | natural | >=360 | 27 | 23.499 | 1.149 | 1.05 | 1.449 |
| pass2med | nap | 0-10 | 128 | 312.398 | 0.41 | 0.342 | 0.483 |
| pass2med | nap | 10-20 | 133 | 158.719 | 0.838 | 0.725 | 0.965 |
| pass2med | nap | 20-30 | 79 | 97.685 | 0.809 | 0.67 | 0.967 |
| pass2med | nap | 30-45 | 76 | 74.773 | 1.016 | 0.818 | 1.239 |
| pass2med | nap | 45-60 | 18 | 20.904 | 0.861 | 0.566 | 1.134 |
| pass2med | nap | 60-90 | 2 | 0.54 | 3.702 | 2.705 | 5.865 |
| pass2med | nap | 90-120 | 0 | 0.0 | nan | nan | nan |
| pass2med | nap | 120-180 | 0 | 0.0 | nan | nan | nan |
| pass2med | nap | 180-240 | 0 | 0.0 | nan | nan | nan |
| pass2med | nap | 240-360 | 0 | 0.0 | nan | nan | nan |
| pass2med | nap | >=360 | 0 | 0.0 | nan | nan | nan |
| pass2med | main | 0-10 | 64 | 118.185 | 0.542 | 0.421 | 0.669 |
| pass2med | main | 10-20 | 68 | 68.09 | 0.999 | 0.762 | 1.263 |
| pass2med | main | 20-30 | 52 | 55.311 | 0.94 | 0.676 | 1.234 |
| pass2med | main | 30-45 | 79 | 76.218 | 1.037 | 0.863 | 1.209 |
| pass2med | main | 45-60 | 59 | 63.483 | 0.929 | 0.642 | 1.238 |
| pass2med | main | 60-90 | 64 | 88.949 | 0.72 | 0.558 | 0.869 |
| pass2med | main | 90-120 | 66 | 57.408 | 1.15 | 0.883 | 1.428 |
| pass2med | main | 120-180 | 53 | 47.599 | 1.113 | 0.83 | 1.298 |
| pass2med | main | 180-240 | 10 | 10.928 | 0.915 | 0.0 | 1.147 |
| pass2med | main | 240-360 | 1 | 2.235 | 0.447 | 0.447 | 0.447 |
| pass2med | main | >=360 | 0 | 0.0 | nan | nan | nan |
| pass2med | day | 0-10 | 20 | 34.307 | 0.583 | 0.404 | 0.753 |
| pass2med | day | 10-20 | 26 | 16.729 | 1.554 | 1.045 | 2.12 |
| pass2med | day | 20-30 | 13 | 15.082 | 0.862 | 0.362 | 1.408 |
| pass2med | day | 30-45 | 16 | 15.702 | 1.019 | 0.844 | 1.125 |
| pass2med | day | 45-60 | 14 | 15.68 | 0.893 | 0.606 | 1.158 |
| pass2med | day | 60-90 | 26 | 25.203 | 1.032 | 0.746 | 1.449 |
| pass2med | day | 90-120 | 33 | 25.941 | 1.272 | 0.875 | 1.842 |
| pass2med | day | 120-180 | 41 | 51.971 | 0.789 | 0.541 | 0.992 |
| pass2med | day | 180-240 | 35 | 49.859 | 0.702 | 0.418 | 0.979 |
| pass2med | day | 240-360 | 72 | 84.416 | 0.853 | 0.761 | 0.987 |
| pass2med | day | >=360 | 27 | 23.499 | 1.149 | 1.05 | 1.217 |
| pass2med | post-round | 0-10 | 110 | 86.458 | 1.272 | 1.071 | 1.485 |
| pass2med | post-round | 10-20 | 53 | 30.879 | 1.716 | 1.344 | 2.136 |
| pass2med | post-round | 20-30 | 82 | 67.989 | 1.206 | 0.938 | 1.506 |
| pass2med | post-round | 30-45 | 119 | 97.636 | 1.219 | 1.04 | 1.424 |
| pass2med | post-round | 45-60 | 97 | 81.085 | 1.196 | 1.005 | 1.385 |
| pass2med | post-round | 60-90 | 113 | 135.522 | 0.834 | 0.684 | 1.009 |
| pass2med | post-round | 90-120 | 82 | 122.989 | 0.667 | 0.539 | 0.799 |
| pass2med | post-round | 120-180 | 229 | 252.209 | 0.908 | 0.778 | 1.042 |
| pass2med | post-round | 180-240 | 259 | 248.073 | 1.044 | 0.927 | 1.162 |
| pass2med | post-round | 240-360 | 542 | 462.863 | 1.171 | 1.062 | 1.293 |
| pass2med | post-round | >=360 | 854 | 782.123 | 1.092 | 1.026 | 1.159 |

## (B) REM share of sleep, observed vs the simulator (100 replicates)

| scores | cls | bin_i | bin_min | at_risk | sleep_min | obs_share | sim_mean | sim_lo | sim_hi |
|---|---|---|---|---|---|---|---|---|---|
| final | natural | 0 | 0-10 | 237 | 1849.4167 | 0.0094 | 0.0345 | 0.0236 | 0.0471 |
| final | natural | 1 | 10-20 | 204 | 1447.5667 | 0.0612 | 0.0718 | 0.0544 | 0.0902 |
| final | natural | 2 | 20-30 | 164 | 1091.3667 | 0.103 | 0.0955 | 0.0693 | 0.12 |
| final | natural | 3 | 30-45 | 124 | 1144.5 | 0.112 | 0.107 | 0.0861 | 0.1333 |
| final | natural | 4 | 45-60 | 81 | 811.0667 | 0.1441 | 0.1274 | 0.1 | 0.1517 |
| final | natural | 5 | 60-90 | 56 | 1161.9 | 0.1453 | 0.16 | 0.13 | 0.1878 |
| final | natural | 6 | 90-120 | 41 | 805.8333 | 0.1541 | 0.1615 | 0.1305 | 0.1987 |
| final | natural | 7 | 120-180 | 27 | 896.3667 | 0.1649 | 0.1751 | 0.1482 | 0.2035 |
| final | natural | 8 | 180-240 | 16 | 599.5167 | 0.1953 | 0.1938 | 0.1577 | 0.2377 |
| final | natural | 9 | 240-360 | 12 | 846.75 | 0.1979 | 0.199 | 0.1693 | 0.2304 |
| final | natural | 10 | >=360 | 8 | 425.9167 | 0.205 | 0.1955 | 0.1469 | 0.2405 |
| final | nap | 0 | 0-10 | 156 | 1224.3167 | 0.0041 | 0.0219 | 0.0109 | 0.0331 |
| final | nap | 1 | 10-20 | 129 | 908.7667 | 0.0388 | 0.0511 | 0.0342 | 0.067 |
| final | nap | 2 | 20-30 | 91 | 595.15 | 0.0895 | 0.069 | 0.0436 | 0.0962 |
| final | nap | 3 | 30-45 | 56 | 445.3667 | 0.0908 | 0.0729 | 0.0449 | 0.1066 |
| final | nap | 4 | 45-60 | 24 | 146.9 | 0.1621 | 0.0706 | 0.0319 | 0.1221 |
| final | nap | 5 | 60-90 | 5 | 67.9 | 0.1885 | 0.0825 | 0.0099 | 0.1615 |
| final | nap | 6 | 90-120 | 2 | 33.1167 | 0.0418 | 0.0707 | 0.0 | 0.1823 |
| final | nap | 7 | 120-180 | 2 | 38.2667 | 0.1298 | 0.0663 | 0.0 | 0.1793 |
| final | nap | 8 | 180-240 | 1 | 12.1833 | 0.1792 | 0.0976 | 0.0 | 0.4183 |
| final | nap | 9 | 240-360 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 |
| final | nap | 10 | >=360 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 |
| final | main | 0 | 0-10 | 57 | 430.6667 | 0.0018 | 0.0288 | 0.0073 | 0.0508 |
| final | main | 1 | 10-20 | 55 | 379.25 | 0.0583 | 0.0687 | 0.0368 | 0.1066 |
| final | main | 2 | 20-30 | 53 | 353.5667 | 0.0889 | 0.0997 | 0.0634 | 0.1371 |
| final | main | 3 | 30-45 | 51 | 523.0 | 0.1085 | 0.106 | 0.0777 | 0.1494 |
| final | main | 4 | 45-60 | 43 | 488.85 | 0.1205 | 0.1198 | 0.0864 | 0.1577 |
| final | main | 5 | 60-90 | 37 | 758.85 | 0.1205 | 0.1495 | 0.117 | 0.1828 |
| final | main | 6 | 90-120 | 26 | 464.2167 | 0.1455 | 0.1487 | 0.1023 | 0.1914 |
| final | main | 7 | 120-180 | 12 | 303.9833 | 0.1315 | 0.1546 | 0.1101 | 0.2142 |
| final | main | 8 | 180-240 | 3 | 41.7333 | 0.0715 | 0.141 | 0.0256 | 0.272 |
| final | main | 9 | 240-360 | 1 | 15.0833 | 0.347 | 0.1558 | 0.0 | 0.4792 |
| final | main | 10 | >=360 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 |
| final | day | 0 | 0-10 | 24 | 194.4333 | 0.0594 | 0.12 | 0.0648 | 0.1738 |
| final | day | 1 | 10-20 | 20 | 159.55 | 0.1954 | 0.1869 | 0.1207 | 0.2626 |
| final | day | 2 | 20-30 | 20 | 142.65 | 0.1938 | 0.1888 | 0.1056 | 0.2762 |
| final | day | 3 | 30-45 | 17 | 176.1333 | 0.1756 | 0.1896 | 0.1263 | 0.2612 |
| final | day | 4 | 45-60 | 14 | 175.3167 | 0.1951 | 0.1916 | 0.1171 | 0.2552 |
| final | day | 5 | 60-90 | 14 | 335.15 | 0.1926 | 0.2003 | 0.1479 | 0.2618 |
| final | day | 6 | 90-120 | 13 | 308.5 | 0.1791 | 0.1904 | 0.1367 | 0.2654 |
| final | day | 7 | 120-180 | 13 | 554.1167 | 0.1857 | 0.1928 | 0.1538 | 0.2279 |
| final | day | 8 | 180-240 | 12 | 545.6 | 0.2051 | 0.2009 | 0.1587 | 0.2475 |
| final | day | 9 | 240-360 | 11 | 831.6667 | 0.1952 | 0.1998 | 0.171 | 0.2323 |
| final | day | 10 | >=360 | 8 | 425.9167 | 0.205 | 0.1955 | 0.1469 | 0.2405 |
| final | post-round | 0 | 0-10 | 77 | 442.1833 | 0.0591 | 0.0748 | 0.0397 | 0.1066 |
| final | post-round | 1 | 10-20 | 61 | 176.1167 | 0.0519 | 0.0931 | 0.0474 | 0.152 |
| final | post-round | 2 | 20-30 | 58 | 306.7167 | 0.0696 | 0.0831 | 0.0476 | 0.122 |
| final | post-round | 3 | 30-45 | 57 | 688.3333 | 0.1304 | 0.1258 | 0.0954 | 0.1554 |
| final | post-round | 4 | 45-60 | 56 | 688.25 | 0.1823 | 0.1605 | 0.1251 | 0.2027 |
| final | post-round | 5 | 60-90 | 53 | 1277.95 | 0.1744 | 0.1633 | 0.1396 | 0.1892 |
| final | post-round | 6 | 90-120 | 46 | 1211.2833 | 0.1881 | 0.1677 | 0.137 | 0.1991 |
| final | post-round | 7 | 120-180 | 42 | 2150.3 | 0.1749 | 0.1671 | 0.148 | 0.1861 |
| final | post-round | 8 | 180-240 | 41 | 1946.3667 | 0.1812 | 0.1727 | 0.1546 | 0.1936 |
| final | post-round | 9 | 240-360 | 39 | 3583.3333 | 0.1861 | 0.1842 | 0.1679 | 0.2011 |
| final | post-round | 10 | >=360 | 33 | 5015.6333 | 0.1834 | 0.1794 | 0.1663 | 0.193 |
| pass2med | natural | 0 | 0-10 | 243 | 1951.7833 | 0.0078 | 0.0321 | 0.0233 | 0.0403 |
| pass2med | natural | 1 | 10-20 | 207 | 1554.8667 | 0.0543 | 0.0724 | 0.0591 | 0.0885 |
| pass2med | natural | 2 | 20-30 | 170 | 1208.2667 | 0.0975 | 0.0896 | 0.0744 | 0.1099 |
| pass2med | natural | 3 | 30-45 | 130 | 1297.6833 | 0.104 | 0.0979 | 0.0778 | 0.1207 |
| pass2med | natural | 4 | 45-60 | 89 | 863.25 | 0.1397 | 0.122 | 0.0978 | 0.1531 |
| pass2med | natural | 5 | 60-90 | 57 | 1205.6167 | 0.1537 | 0.1504 | 0.1297 | 0.1752 |
| pass2med | natural | 6 | 90-120 | 39 | 802.8167 | 0.1527 | 0.1572 | 0.1273 | 0.1923 |
| pass2med | natural | 7 | 120-180 | 25 | 893.9833 | 0.1753 | 0.1726 | 0.141 | 0.2129 |
| pass2med | natural | 8 | 180-240 | 15 | 615.2 | 0.1953 | 0.1834 | 0.152 | 0.222 |
| pass2med | natural | 9 | 240-360 | 12 | 917.2167 | 0.1865 | 0.1924 | 0.1635 | 0.2213 |
| pass2med | natural | 10 | >=360 | 8 | 383.4 | 0.1998 | 0.1913 | 0.1466 | 0.2425 |
| pass2med | nap | 0 | 0-10 | 166 | 1313.5 | 0.003 | 0.0213 | 0.0109 | 0.0324 |
| pass2med | nap | 1 | 10-20 | 134 | 996.4833 | 0.0393 | 0.0551 | 0.0401 | 0.0707 |
| pass2med | nap | 2 | 20-30 | 98 | 678.8167 | 0.0864 | 0.0649 | 0.0466 | 0.0873 |
| pass2med | nap | 3 | 30-45 | 62 | 539.0333 | 0.083 | 0.0658 | 0.0451 | 0.091 |
| pass2med | nap | 4 | 45-60 | 29 | 176.8333 | 0.1427 | 0.0708 | 0.0296 | 0.1219 |
| pass2med | nap | 5 | 60-90 | 8 | 85.3333 | 0.152 | 0.0593 | 0.0102 | 0.1428 |
| pass2med | nap | 6 | 90-120 | 2 | 36.3167 | 0.0725 | 0.0635 | 0.0 | 0.1729 |
| pass2med | nap | 7 | 120-180 | 2 | 40.1667 | 0.066 | 0.0559 | 0.0 | 0.1545 |
| pass2med | nap | 8 | 180-240 | 1 | 17.7 | 0.2467 | 0.069 | 0.0 | 0.2409 |
| pass2med | nap | 9 | 240-360 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 |
| pass2med | nap | 10 | >=360 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 |
| pass2med | main | 0 | 0-10 | 57 | 471.4167 | 0.0034 | 0.0331 | 0.012 | 0.0539 |
| pass2med | main | 1 | 10-20 | 56 | 417.0833 | 0.0547 | 0.0728 | 0.0445 | 0.1082 |
| pass2med | main | 2 | 20-30 | 55 | 398.1 | 0.0901 | 0.0969 | 0.0716 | 0.1261 |
| pass2med | main | 3 | 30-45 | 53 | 589.2333 | 0.1046 | 0.1022 | 0.0736 | 0.1357 |
| pass2med | main | 4 | 45-60 | 48 | 532.1667 | 0.124 | 0.1197 | 0.0851 | 0.1566 |
| pass2med | main | 5 | 60-90 | 37 | 827.0667 | 0.1439 | 0.1453 | 0.1168 | 0.1819 |
| pass2med | main | 6 | 90-120 | 26 | 492.6667 | 0.1606 | 0.1459 | 0.1081 | 0.1833 |
| pass2med | main | 7 | 120-180 | 12 | 343.7333 | 0.1803 | 0.1569 | 0.1097 | 0.2264 |
| pass2med | main | 8 | 180-240 | 3 | 58.0667 | 0.1625 | 0.1608 | 0.0543 | 0.2915 |
| pass2med | main | 9 | 240-360 | 1 | 17.05 | 0.2972 | 0.1859 | 0.0174 | 0.436 |
| pass2med | main | 10 | >=360 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 |
| pass2med | day | 0 | 0-10 | 20 | 166.8667 | 0.0577 | 0.1077 | 0.0529 | 0.1701 |
| pass2med | day | 1 | 10-20 | 17 | 141.3 | 0.1586 | 0.1851 | 0.1148 | 0.2657 |
| pass2med | day | 2 | 20-30 | 17 | 131.35 | 0.177 | 0.1885 | 0.1073 | 0.2644 |
| pass2med | day | 3 | 30-45 | 15 | 169.4167 | 0.1691 | 0.1839 | 0.1214 | 0.274 |
| pass2med | day | 4 | 45-60 | 12 | 154.25 | 0.1908 | 0.1857 | 0.1025 | 0.2769 |
| pass2med | day | 5 | 60-90 | 12 | 293.2167 | 0.1819 | 0.1897 | 0.1349 | 0.2633 |
| pass2med | day | 6 | 90-120 | 11 | 273.8333 | 0.1491 | 0.1879 | 0.1374 | 0.2543 |
| pass2med | day | 7 | 120-180 | 11 | 510.0833 | 0.1806 | 0.191 | 0.1548 | 0.2417 |
| pass2med | day | 8 | 180-240 | 11 | 539.4333 | 0.1971 | 0.1899 | 0.1591 | 0.2414 |
| pass2med | day | 9 | 240-360 | 11 | 900.1667 | 0.1844 | 0.1925 | 0.1637 | 0.223 |
| pass2med | day | 10 | >=360 | 8 | 383.4 | 0.1998 | 0.1913 | 0.1466 | 0.2425 |
| pass2med | post-round | 0 | 0-10 | 79 | 479.9167 | 0.0578 | 0.0942 | 0.0651 | 0.1293 |
| pass2med | post-round | 1 | 10-20 | 66 | 181.0 | 0.0488 | 0.1202 | 0.0684 | 0.1782 |
| pass2med | post-round | 2 | 20-30 | 62 | 327.6667 | 0.0805 | 0.0799 | 0.0482 | 0.1189 |
| pass2med | post-round | 3 | 30-45 | 61 | 701.5833 | 0.1354 | 0.1375 | 0.107 | 0.1664 |
| pass2med | post-round | 4 | 45-60 | 57 | 696.1 | 0.1834 | 0.164 | 0.1323 | 0.2048 |
| pass2med | post-round | 5 | 60-90 | 52 | 1275.8167 | 0.1707 | 0.1646 | 0.1429 | 0.1835 |
| pass2med | post-round | 6 | 90-120 | 47 | 1236.3667 | 0.1806 | 0.1698 | 0.1508 | 0.1991 |
| pass2med | post-round | 7 | 120-180 | 44 | 2159.2 | 0.1779 | 0.1708 | 0.1539 | 0.1896 |
| pass2med | post-round | 8 | 180-240 | 41 | 1962.9833 | 0.1871 | 0.1715 | 0.1526 | 0.1962 |
| pass2med | post-round | 9 | 240-360 | 38 | 3470.05 | 0.1871 | 0.1834 | 0.1688 | 0.2018 |
| pass2med | post-round | 10 | >=360 | 33 | 4864.0333 | 0.1881 | 0.1843 | 0.1712 | 0.1973 |

## (C) Held-out comparisons

| scores | subset | comparison | metric | delta_pct | ci_lo_pct | ci_hi_pct | animals_better | animals | n_steps | holds |
|---|---|---|---|---|---|---|---|---|---|---|
| final | natural (nap + main + day) | B+episode clock vs B | total | -0.332 | -0.5267 | -0.0979 | 6 | 6 | 33425 | True |
| final | natural (nap + main + day) | B+episode clock vs B | rem | -0.4833 | -0.8854 | -0.0849 | 6 | 6 | 33425 | True |
| final | natural (nap + main + day) | B+episode clock vs B | wake | -0.2656 | -0.5072 | 0.0089 | 4 | 6 | 33425 | False |
| final | natural + post-round | B+episode clock vs B | total | -0.1664 | -0.3049 | -0.0568 | 4 | 6 | 105550 | False |
| final | natural + post-round | B+episode clock vs B | rem | -0.206 | -0.3878 | -0.0338 | 6 | 6 | 105550 | True |
| final | natural + post-round | B+episode clock vs B | wake | -0.1358 | -0.3096 | 0.0267 | 4 | 6 | 105550 | False |
| pass2med | natural (nap + main + day) | B+episode clock vs B | total | -0.2619 | -0.6284 | 0.0455 | 4 | 6 | 32808 | False |
| pass2med | natural (nap + main + day) | B+episode clock vs B | rem | -0.2874 | -0.7394 | 0.1558 | 5 | 6 | 32808 | False |
| pass2med | natural (nap + main + day) | B+episode clock vs B | wake | -0.2411 | -0.6865 | 0.0802 | 3 | 6 | 32808 | False |
| pass2med | natural + post-round | B+episode clock vs B | total | -0.1989 | -0.3566 | -0.0821 | 6 | 6 | 106675 | True |
| pass2med | natural + post-round | B+episode clock vs B | rem | -0.2155 | -0.3578 | -0.0855 | 6 | 6 | 106675 | True |
| pass2med | natural + post-round | B+episode clock vs B | wake | -0.1812 | -0.4246 | 0.0266 | 4 | 6 | 106675 | False |

## (D) Description: end-aligned REM O / E (observed ends only; selection-prone)

| scores | cls | min_before_end | steps | O | E | oe | lo | hi |
|---|---|---|---|---|---|---|---|---|
| final | natural | 0-10 | 4421 | 52 | 32.737 | 1.588 | 1.201 | 2.011 |
| final | natural | 10-20 | 3538 | 27 | 20.616 | 1.31 | 0.924 | 1.831 |
| final | natural | 20-30 | 2306 | 11 | 12.936 | 0.85 | 0.442 | 1.433 |
| final | natural | 30-60 | 2265 | 5 | 11.585 | 0.432 | 0.107 | 0.811 |
| final | natural | 60-120 | 8 | 0 | 0.007 | 0.0 | 0.0 | 0.0 |
| final | natural | >=120 | 0 | 0 | 0.0 | nan | nan | nan |
| final | nap | 0-10 | 4300 | 48 | 31.346 | 1.531 | 1.131 | 1.942 |
| final | nap | 10-20 | 3454 | 25 | 19.223 | 1.301 | 0.883 | 1.794 |
| final | nap | 20-30 | 2235 | 11 | 12.473 | 0.882 | 0.399 | 1.436 |
| final | nap | 30-60 | 2153 | 4 | 10.538 | 0.38 | 0.08 | 0.784 |
| final | nap | 60-120 | 8 | 0 | 0.007 | 0.0 | 0.0 | 0.0 |
| final | nap | >=120 | 0 | 0 | 0.0 | nan | nan | nan |
| final | main | 0-10 | 28 | 2 | 0.275 | 7.263 | 7.263 | 7.263 |
| final | main | 10-20 | 48 | 0 | 0.572 | 0.0 | 0.0 | 0.0 |
| final | main | 20-30 | 58 | 0 | 0.373 | 0.0 | 0.0 | 0.0 |
| final | main | 30-60 | 112 | 1 | 1.047 | 0.955 | 0.955 | 0.955 |
| final | main | 60-120 | 0 | 0 | 0.0 | nan | nan | nan |
| final | main | >=120 | 0 | 0 | 0.0 | nan | nan | nan |
| final | day | 0-10 | 93 | 2 | 1.116 | 1.793 | 0.0 | 2.223 |
| final | day | 10-20 | 36 | 2 | 0.821 | 2.436 | 2.436 | 2.436 |
| final | day | 20-30 | 13 | 0 | 0.09 | 0.0 | 0.0 | 0.0 |
| final | day | 30-60 | 0 | 0 | 0.0 | nan | nan | nan |
| final | day | 60-120 | 0 | 0 | 0.0 | nan | nan | nan |
| final | day | >=120 | 0 | 0 | 0.0 | nan | nan | nan |
| final | post-round | 0-10 | 957 | 24 | 16.446 | 1.459 | 1.011 | 2.188 |
| final | post-round | 10-20 | 751 | 17 | 13.257 | 1.282 | 0.83 | 1.904 |
| final | post-round | 20-30 | 698 | 9 | 12.466 | 0.722 | 0.405 | 1.214 |
| final | post-round | 30-60 | 1680 | 42 | 30.985 | 1.356 | 1.041 | 1.754 |
| final | post-round | 60-120 | 2498 | 62 | 52.783 | 1.175 | 0.937 | 1.512 |
| final | post-round | >=120 | 10876 | 257 | 269.195 | 0.955 | 0.782 | 1.227 |
| pass2med | natural | 0-10 | 4640 | 58 | 40.878 | 1.419 | 1.126 | 1.732 |
| pass2med | natural | 10-20 | 3767 | 26 | 26.524 | 0.98 | 0.662 | 1.398 |
| pass2med | natural | 20-30 | 2499 | 15 | 20.925 | 0.717 | 0.422 | 1.113 |
| pass2med | natural | 30-60 | 2566 | 9 | 15.961 | 0.564 | 0.204 | 0.955 |
| pass2med | natural | 60-120 | 274 | 8 | 9.899 | 0.808 | 0.0 | 0.809 |
| pass2med | natural | >=120 | 1142 | 30 | 39.124 | 0.767 | 0.767 | 0.767 |
| pass2med | nap | 0-10 | 4418 | 52 | 37.362 | 1.392 | 1.062 | 1.795 |
| pass2med | nap | 10-20 | 3584 | 25 | 24.405 | 1.024 | 0.711 | 1.383 |
| pass2med | nap | 20-30 | 2296 | 14 | 16.546 | 0.846 | 0.511 | 1.272 |
| pass2med | nap | 30-60 | 2344 | 5 | 13.121 | 0.381 | 0.071 | 0.896 |
| pass2med | nap | 60-120 | 13 | 0 | 0.01 | 0.0 | 0.0 | 0.0 |
| pass2med | nap | >=120 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | main | 0-10 | 85 | 3 | 0.633 | 4.737 | 4.737 | 4.737 |
| pass2med | main | 10-20 | 103 | 1 | 0.647 | 1.546 | 1.546 | 1.546 |
| pass2med | main | 20-30 | 93 | 0 | 0.368 | 0.0 | 0.0 | 0.0 |
| pass2med | main | 30-60 | 113 | 1 | 0.573 | 1.746 | 1.746 | 1.746 |
| pass2med | main | 60-120 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | main | >=120 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | day | 0-10 | 137 | 3 | 2.882 | 1.041 | 0.998 | 1.139 |
| pass2med | day | 10-20 | 80 | 0 | 1.472 | 0.0 | 0.0 | 0.0 |
| pass2med | day | 20-30 | 110 | 1 | 4.011 | 0.249 | 0.0 | 0.333 |
| pass2med | day | 30-60 | 109 | 3 | 2.267 | 1.323 | 1.323 | 1.323 |
| pass2med | day | 60-120 | 261 | 8 | 9.89 | 0.809 | 0.809 | 0.809 |
| pass2med | day | >=120 | 1142 | 30 | 39.124 | 0.767 | 0.767 | 0.767 |
| pass2med | post-round | 0-10 | 1103 | 26 | 21.834 | 1.191 | 0.679 | 1.879 |
| pass2med | post-round | 10-20 | 804 | 21 | 16.385 | 1.282 | 0.899 | 1.699 |
| pass2med | post-round | 20-30 | 685 | 15 | 12.715 | 1.18 | 0.831 | 1.503 |
| pass2med | post-round | 30-60 | 1712 | 43 | 36.047 | 1.193 | 0.989 | 1.399 |
| pass2med | post-round | 60-120 | 2278 | 57 | 67.39 | 0.846 | 0.641 | 1.101 |
| pass2med | post-round | >=120 | 8539 | 206 | 251.985 | 0.818 | 0.639 | 1.024 |

## (D) Sensitivity: (A) REM with a 10-min wake threshold

| scores | cls | bin_min | at_risk | O | E | oe | lo | hi |
|---|---|---|---|---|---|---|---|---|
| final | natural | 0-10 | 483 | 74 | 89.412 | 0.828 | 0.655 | 1.017 |
| final | natural | 10-20 | 395 | 181 | 173.426 | 1.044 | 0.886 | 1.192 |
| final | natural | 20-30 | 325 | 152 | 140.127 | 1.085 | 0.919 | 1.258 |
| final | natural | 30-45 | 272 | 189 | 195.229 | 0.968 | 0.81 | 1.127 |
| final | natural | 45-60 | 198 | 189 | 168.419 | 1.122 | 0.97 | 1.281 |
| final | natural | 60-90 | 160 | 286 | 331.862 | 0.862 | 0.759 | 0.974 |
| final | natural | 90-120 | 128 | 268 | 290.345 | 0.923 | 0.785 | 1.074 |
| final | natural | 120-180 | 103 | 390 | 375.026 | 1.04 | 0.907 | 1.193 |
| final | natural | 180-240 | 55 | 254 | 231.347 | 1.098 | 0.953 | 1.271 |
| final | natural | 240-360 | 32 | 266 | 213.972 | 1.243 | 1.103 | 1.38 |
| final | natural | >=360 | 9 | 136 | 112.499 | 1.209 | 1.048 | 1.458 |
| final | nap | 0-10 | 215 | 9 | 14.871 | 0.605 | 0.263 | 1.05 |
| final | nap | 10-20 | 154 | 32 | 36.816 | 0.869 | 0.606 | 1.179 |
| final | nap | 20-30 | 99 | 36 | 23.716 | 1.518 | 1.101 | 2.022 |
| final | nap | 30-45 | 66 | 26 | 16.768 | 1.551 | 1.039 | 2.145 |
| final | nap | 45-60 | 28 | 9 | 7.756 | 1.16 | 0.563 | 2.297 |
| final | nap | 60-90 | 9 | 3 | 3.75 | 0.8 | 0.0 | 1.608 |
| final | nap | 90-120 | 2 | 1 | 2.498 | 0.4 | 0.0 | 1.504 |
| final | nap | 120-180 | 0 | 0 | 0.0 | nan | nan | nan |
| final | nap | 180-240 | 0 | 0 | 0.0 | nan | nan | nan |
| final | nap | 240-360 | 0 | 0 | 0.0 | nan | nan | nan |
| final | nap | >=360 | 0 | 0 | 0.0 | nan | nan | nan |
| final | main | 0-10 | 58 | 9 | 12.859 | 0.7 | 0.354 | 1.062 |
| final | main | 10-20 | 58 | 29 | 28.121 | 1.031 | 0.694 | 1.377 |
| final | main | 20-30 | 56 | 20 | 28.149 | 0.71 | 0.498 | 0.953 |
| final | main | 30-45 | 53 | 27 | 42.69 | 0.632 | 0.441 | 0.855 |
| final | main | 45-60 | 45 | 42 | 35.451 | 1.185 | 0.872 | 1.56 |
| final | main | 60-90 | 35 | 53 | 73.208 | 0.724 | 0.488 | 0.987 |
| final | main | 90-120 | 28 | 45 | 55.664 | 0.808 | 0.622 | 1.018 |
| final | main | 120-180 | 19 | 64 | 68.439 | 0.935 | 0.552 | 1.303 |
| final | main | 180-240 | 9 | 58 | 42.896 | 1.352 | 0.978 | 1.93 |
| final | main | 240-360 | 7 | 81 | 70.226 | 1.153 | 0.925 | 1.38 |
| final | main | >=360 | 4 | 93 | 85.434 | 1.089 | 0.953 | 1.241 |
| final | day | 0-10 | 210 | 56 | 61.682 | 0.908 | 0.684 | 1.142 |
| final | day | 10-20 | 183 | 120 | 108.488 | 1.106 | 0.913 | 1.306 |
| final | day | 20-30 | 170 | 96 | 88.261 | 1.088 | 0.919 | 1.314 |
| final | day | 30-45 | 153 | 136 | 135.771 | 1.002 | 0.822 | 1.165 |
| final | day | 45-60 | 125 | 138 | 125.212 | 1.102 | 0.943 | 1.31 |
| final | day | 60-90 | 116 | 230 | 254.903 | 0.902 | 0.794 | 1.027 |
| final | day | 90-120 | 98 | 222 | 232.183 | 0.956 | 0.819 | 1.121 |
| final | day | 120-180 | 84 | 326 | 306.587 | 1.063 | 0.938 | 1.198 |
| final | day | 180-240 | 46 | 196 | 188.451 | 1.04 | 0.904 | 1.215 |
| final | day | 240-360 | 25 | 185 | 143.747 | 1.287 | 1.12 | 1.453 |
| final | day | >=360 | 5 | 43 | 27.065 | 1.589 | 1.407 | 4.004 |
| final | post-round | 0-10 | 72 | 13 | 14.625 | 0.889 | 0.525 | 1.329 |
| final | post-round | 10-20 | 28 | 6 | 9.827 | 0.611 | 0.155 | 1.327 |
| final | post-round | 20-30 | 10 | 7 | 7.068 | 0.99 | 0.394 | 1.644 |
| final | post-round | 30-45 | 8 | 16 | 11.808 | 1.355 | 0.761 | 2.153 |
| final | post-round | 45-60 | 8 | 16 | 11.873 | 1.348 | 0.728 | 2.818 |
| final | post-round | 60-90 | 7 | 15 | 15.573 | 0.963 | 0.555 | 2.042 |
| final | post-round | 90-120 | 4 | 19 | 11.789 | 1.612 | 1.138 | 2.424 |
| final | post-round | 120-180 | 4 | 25 | 25.77 | 0.97 | 0.645 | 1.413 |
| final | post-round | 180-240 | 3 | 15 | 18.14 | 0.827 | 0.355 | 1.245 |
| final | post-round | 240-360 | 3 | 16 | 14.875 | 1.076 | 0.339 | 1.267 |
| final | post-round | >=360 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | natural | 0-10 | 495 | 91 | 104.27 | 0.873 | 0.706 | 1.043 |
| pass2med | natural | 10-20 | 400 | 189 | 203.395 | 0.929 | 0.819 | 1.066 |
| pass2med | natural | 20-30 | 336 | 174 | 165.914 | 1.049 | 0.914 | 1.216 |
| pass2med | natural | 30-45 | 280 | 208 | 219.716 | 0.947 | 0.809 | 1.074 |
| pass2med | natural | 45-60 | 211 | 202 | 207.325 | 0.974 | 0.85 | 1.103 |
| pass2med | natural | 60-90 | 167 | 324 | 389.156 | 0.833 | 0.755 | 0.927 |
| pass2med | natural | 90-120 | 133 | 296 | 340.43 | 0.869 | 0.764 | 0.983 |
| pass2med | natural | 120-180 | 108 | 390 | 428.683 | 0.91 | 0.823 | 1.008 |
| pass2med | natural | 180-240 | 58 | 258 | 257.367 | 1.002 | 0.878 | 1.149 |
| pass2med | natural | 240-360 | 31 | 256 | 235.766 | 1.086 | 0.954 | 1.229 |
| pass2med | natural | >=360 | 9 | 110 | 100.101 | 1.099 | 0.962 | 1.473 |
| pass2med | nap | 0-10 | 221 | 5 | 16.484 | 0.303 | 0.114 | 0.559 |
| pass2med | nap | 10-20 | 159 | 38 | 45.931 | 0.827 | 0.588 | 1.086 |
| pass2med | nap | 20-30 | 109 | 41 | 27.158 | 1.51 | 1.104 | 2.037 |
| pass2med | nap | 30-45 | 69 | 29 | 23.33 | 1.243 | 0.818 | 1.821 |
| pass2med | nap | 45-60 | 30 | 12 | 8.752 | 1.371 | 0.746 | 2.379 |
| pass2med | nap | 60-90 | 9 | 5 | 5.024 | 0.995 | 0.0 | 1.396 |
| pass2med | nap | 90-120 | 1 | 1 | 0.749 | 1.336 | 1.336 | 1.336 |
| pass2med | nap | 120-180 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | nap | 180-240 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | nap | 240-360 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | nap | >=360 | 0 | 0 | 0.0 | nan | nan | nan |
| pass2med | main | 0-10 | 58 | 8 | 14.38 | 0.556 | 0.265 | 0.833 |
| pass2med | main | 10-20 | 58 | 26 | 29.74 | 0.874 | 0.578 | 1.222 |
| pass2med | main | 20-30 | 58 | 29 | 34.699 | 0.836 | 0.636 | 1.066 |
| pass2med | main | 30-45 | 56 | 39 | 47.611 | 0.819 | 0.585 | 1.086 |
| pass2med | main | 45-60 | 52 | 51 | 46.318 | 1.101 | 0.888 | 1.348 |
| pass2med | main | 60-90 | 39 | 68 | 90.336 | 0.753 | 0.623 | 0.915 |
| pass2med | main | 90-120 | 29 | 54 | 74.615 | 0.724 | 0.571 | 0.934 |
| pass2med | main | 120-180 | 19 | 70 | 75.415 | 0.928 | 0.778 | 1.117 |
| pass2med | main | 180-240 | 10 | 64 | 48.411 | 1.322 | 0.978 | 1.674 |
| pass2med | main | 240-360 | 8 | 76 | 74.319 | 1.023 | 0.901 | 1.301 |
| pass2med | main | >=360 | 4 | 76 | 75.368 | 1.008 | 0.942 | 1.521 |
| pass2med | day | 0-10 | 216 | 78 | 73.406 | 1.063 | 0.831 | 1.283 |
| pass2med | day | 10-20 | 183 | 125 | 127.725 | 0.979 | 0.833 | 1.153 |
| pass2med | day | 20-30 | 169 | 104 | 104.056 | 0.999 | 0.832 | 1.224 |
| pass2med | day | 30-45 | 155 | 140 | 148.775 | 0.941 | 0.783 | 1.114 |
| pass2med | day | 45-60 | 129 | 139 | 152.255 | 0.913 | 0.76 | 1.089 |
| pass2med | day | 60-90 | 119 | 251 | 293.797 | 0.854 | 0.764 | 0.949 |
| pass2med | day | 90-120 | 103 | 241 | 265.066 | 0.909 | 0.796 | 1.035 |
| pass2med | day | 120-180 | 89 | 320 | 353.268 | 0.906 | 0.817 | 1.012 |
| pass2med | day | 180-240 | 48 | 194 | 208.956 | 0.928 | 0.82 | 1.052 |
| pass2med | day | 240-360 | 23 | 180 | 161.447 | 1.115 | 0.937 | 1.326 |
| pass2med | day | >=360 | 5 | 34 | 24.733 | 1.375 | 0.682 | 2.559 |
| pass2med | post-round | 0-10 | 74 | 16 | 20.54 | 0.779 | 0.463 | 1.106 |
| pass2med | post-round | 10-20 | 26 | 7 | 12.746 | 0.549 | 0.148 | 1.246 |
| pass2med | post-round | 20-30 | 9 | 10 | 9.05 | 1.105 | 0.429 | 2.23 |
| pass2med | post-round | 30-45 | 7 | 14 | 13.315 | 1.051 | 0.567 | 1.715 |
| pass2med | post-round | 45-60 | 7 | 15 | 10.117 | 1.483 | 0.962 | 2.442 |
| pass2med | post-round | 60-90 | 6 | 14 | 17.014 | 0.823 | 0.629 | 2.086 |
| pass2med | post-round | 90-120 | 4 | 20 | 18.417 | 1.086 | 0.742 | 1.875 |
| pass2med | post-round | 120-180 | 4 | 25 | 33.039 | 0.757 | 0.452 | 1.613 |
| pass2med | post-round | 180-240 | 3 | 19 | 21.126 | 0.899 | 0.586 | 1.34 |
| pass2med | post-round | 240-360 | 3 | 15 | 16.764 | 0.895 | 0.241 | 1.223 |
| pass2med | post-round | >=360 | 0 | 0 | 0.0 | nan | nan | nan |

