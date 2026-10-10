# Sleep LFP stage — L1b: naps vs main sleep (P and depth), and the rule-(e) selection check (cohort 2026c)

Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) §8 revision 2 (rules written before results). Driver `ephys/sleep_lfp.py L1b` (commit 87541f7+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_lfp_L1b_20261010_1741`; runtime 9 min. **Technical ledger.** Labels from the SWR session's night_sleep_wiser (FINAL only); outcome = REM entry (the labels look into the future, so WAKE differs by construction); naps are all dark, so a difference reads 'label or light'.

## Reading (main session, 2026-10-10; claim #69; #68 downgraded)

**Naps vs main sleep: no difference detected.** At the same count, depth and clock, the count and depth predict REM
entry the same way in night naps and in the main sleep.
- nap × P: +0.080 % [−0.034, +0.208] (all naps), −0.076 % [−0.401, +0.096] (strict).
- nap × depth: −0.138 % [−0.529, +0.118] (all), −0.110 % [−0.392, +0.055] (strict).
- No nap main effect beyond the count, depth and clock: +0.165 % [−0.013, +0.519].
- 175 REM entries in naps (94 in strict naps), 6/6 animals with nap REM. The CIs allow effects of a few tenths of a
  percent.
- Naps are all dark, so the label and the light cannot be told apart. The full-data coefficients (nap × depth +0.16 /
  +0.27 on REM vs stay) point the same way as the held-out comparisons, without held-out gain.

**Rule (e) on fixed windows (astra's selection check):**
- 56 % of the main (e) set has a future window entirely NREM (mean NREM coverage 0.90).
- On those steps the count still predicts the coming depth on FINAL: MSE −7.6 % [−13.4, −2.9], slope −0.093. But the
  per-animal sign holds in only 4/6 (SF08 and SF10 ≈ 0).
- On pass2med it disappears: +0.22 % [−0.48, +1.08], 4/6.
- Part of the earlier association was composition: P also predicts which seconds stay NREM. #68 goes down to Candidate.

## Verdicts (REM entry)

| variant | term | pass | nap_rem_entries | animals_with_nap_rem | numbers |
|---|---|---|---|---|---|
| all naps | nap x P | False | 175 | 6 | REM log-loss +0.080 % [-0.034, +0.208], 1/6 |
| all naps | nap x depth | False | 175 | 6 | REM log-loss -0.138 % [-0.529, +0.118], 3/6 |
| all naps | nap main effect | False | 175 | 6 | REM log-loss +0.165 % [-0.013, +0.519], 1/6 |
| strict naps | nap x P | False | 94 | 6 | REM log-loss -0.076 % [-0.401, +0.096], 4/6 |
| strict naps | nap x depth | False | 94 | 6 | REM log-loss -0.110 % [-0.392, +0.055], 3/6 |
| strict naps | nap main effect | False | 94 | 6 | REM log-loss +0.117 % [-0.061, +0.474], 3/6 |

## Steps and REM entries per label

| variant | label | steps | rem_entries |
|---|---|---|---|
| all naps | main | 91975 | 1909 |
| all naps | nap | 19873 | 175 |
| strict naps | main | 91975 | 1909 |
| strict naps | nap | 12190 | 94 |

| variant | label | animal | steps | rem_entries |
|---|---|---|---|---|
| all naps | nap | SF07 | 2583 | 26 |
| all naps | nap | SF08 | 2779 | 15 |
| all naps | nap | SF09 | 4119 | 37 |
| all naps | nap | SF10 | 4436 | 35 |
| all naps | nap | SF11 | 2195 | 33 |
| all naps | nap | SF12 | 3761 | 29 |
| all naps | main | SF07 | 17096 | 393 |
| all naps | main | SF08 | 18869 | 368 |
| all naps | main | SF09 | 18813 | 346 |
| all naps | main | SF10 | 16655 | 384 |
| all naps | main | SF11 | 6336 | 145 |
| all naps | main | SF12 | 14206 | 273 |
| strict naps | nap | SF07 | 1184 | 10 |
| strict naps | nap | SF08 | 1826 | 9 |
| strict naps | nap | SF09 | 2698 | 18 |
| strict naps | nap | SF10 | 3094 | 28 |
| strict naps | nap | SF11 | 479 | 5 |
| strict naps | nap | SF12 | 2909 | 24 |
| strict naps | main | SF07 | 17096 | 393 |
| strict naps | main | SF08 | 18869 | 368 |
| strict naps | main | SF09 | 18813 | 346 |
| strict naps | main | SF10 | 16655 | 384 |
| strict naps | main | SF11 | 6336 | 145 |
| strict naps | main | SF12 | 14206 | 273 |

## Held-out comparisons (total, REM, WAKE)

| scores | subset | comparison | metric | delta_pct | ci_lo_pct | ci_hi_pct | animals_better | animals | n_steps | holds |
|---|---|---|---|---|---|---|---|---|---|---|
| final | all naps | M0 vs B+dep | total | 0.0454 | -0.0018 | 0.1316 | 2 | 6 | 83365 | False |
| final | all naps | M0 vs B+dep | rem | 0.1653 | -0.0129 | 0.5195 | 1 | 6 | 83365 | False |
| final | all naps | M0 vs B+dep | wake | -0.0283 | -0.1117 | 0.0232 | 4 | 6 | 83365 | False |
| final | all naps | M0+napP vs M0 | total | 0.0502 | 0.0034 | 0.1028 | 1 | 6 | 83365 | False |
| final | all naps | M0+napP vs M0 | rem | 0.0801 | -0.0342 | 0.2078 | 1 | 6 | 83365 | False |
| final | all naps | M0+napP vs M0 | wake | 0.0308 | -0.0101 | 0.071 | 2 | 6 | 83365 | False |
| final | all naps | M0+napD vs M0 | total | -0.031 | -0.1186 | 0.0352 | 2 | 6 | 83365 | False |
| final | all naps | M0+napD vs M0 | rem | -0.1384 | -0.5287 | 0.1185 | 3 | 6 | 83365 | False |
| final | all naps | M0+napD vs M0 | wake | 0.0328 | -0.0437 | 0.1393 | 2 | 6 | 83365 | False |
| final | all naps | M0+both vs M0 | total | 0.0289 | -0.0412 | 0.0864 | 1 | 6 | 83365 | False |
| final | all naps | M0+both vs M0 | rem | -0.063 | -0.4458 | 0.1673 | 2 | 6 | 83365 | False |
| final | all naps | M0+both vs M0 | wake | 0.0834 | 0.0067 | 0.2119 | 1 | 6 | 83365 | False |
| final | strict naps | M0 vs B+dep | total | 0.0289 | -0.0486 | 0.1578 | 4 | 6 | 80416 | False |
| final | strict naps | M0 vs B+dep | rem | 0.1171 | -0.0605 | 0.4741 | 3 | 6 | 80416 | False |
| final | strict naps | M0 vs B+dep | wake | -0.0283 | -0.08 | 0.0289 | 5 | 6 | 80416 | False |
| final | strict naps | M0+napP vs M0 | total | -0.0096 | -0.0807 | 0.0428 | 2 | 6 | 80416 | False |
| final | strict naps | M0+napP vs M0 | rem | -0.0763 | -0.4009 | 0.0964 | 4 | 6 | 80416 | False |
| final | strict naps | M0+napP vs M0 | wake | 0.0323 | -0.0337 | 0.1283 | 2 | 6 | 80416 | False |
| final | strict naps | M0+napD vs M0 | total | -0.0294 | -0.0955 | 0.0135 | 3 | 6 | 80416 | False |
| final | strict naps | M0+napD vs M0 | rem | -0.1102 | -0.3922 | 0.0547 | 3 | 6 | 80416 | False |
| final | strict naps | M0+napD vs M0 | wake | 0.0234 | -0.0335 | 0.1011 | 3 | 6 | 80416 | False |
| final | strict naps | M0+both vs M0 | total | -0.0219 | -0.0888 | 0.0234 | 1 | 6 | 80416 | False |
| final | strict naps | M0+both vs M0 | rem | -0.0711 | -0.4008 | 0.1141 | 3 | 6 | 80416 | False |
| final | strict naps | M0+both vs M0 | wake | 0.0093 | -0.0614 | 0.1154 | 3 | 6 | 80416 | False |

## Full-data coefficients (M0 + both; per unit)

| variant | term | REM_vs_stay_per_unit | WAKE_vs_stay_per_unit |
|---|---|---|---|
| all naps | dep | -0.0983 | -0.2295 |
| all naps | nap | 0.3893 | 0.0708 |
| all naps | nap_lP | -0.1235 | -0.0092 |
| all naps | nap_dep | 0.1625 | 0.0186 |
| strict naps | dep | -0.0211 | -0.2128 |
| strict naps | nap | 0.0064 | -0.5103 |
| strict naps | nap_lP | -0.1096 | -0.0284 |
| strict naps | nap_dep | 0.2724 | 0.005 |

## Rule (e) on future windows entirely NREM (selection check)

| scores | subset | steps | delta_mse_pct | ci_lo_pct | ci_hi_pct | pooled_P_slope | animals_same_sign | animals | per_animal_slopes | fut_cov_main_median | fut_cov_main_mean | share_main_entirely_nrem |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| final | future window entirely NREM | 61553 | -7.6139 | -13.4049 | -2.9102 | -0.0926 | 4 | 6 | SF07 -0.162; SF08 +0.002; SF09 -0.098; SF10 +0.003; SF11 -0.040; SF12 -0.029 | 1.0 | 0.9022 | 0.5623 |
| pass2med | future window entirely NREM | 65112 | 0.2238 | -0.476 | 1.0798 | -0.0281 | 4 | 6 | SF07 -0.082; SF08 +0.015; SF09 -0.032; SF10 +0.003; SF11 -0.045; SF12 -0.052 | 1.0 | 0.9033 | 0.5678 |

