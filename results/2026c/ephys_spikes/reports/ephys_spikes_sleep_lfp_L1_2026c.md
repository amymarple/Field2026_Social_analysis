# Sleep LFP stage — L1: NREM depth and the REM-entry count (cohort 2026c)

Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) revision 1 (rules written before results). Driver `ephys/sleep_lfp.py L1` (commit ede4bf8+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_lfp_L1_20261010_1654`; runtime 12 min. **Technical ledger.**

## Reading (main session, 2026-10-10; claims #65–#68; #4 updated)

**Question:** is the REM-entry count P a behavioural proxy for NREM depth, a parallel process, or is depth redundant?
Depth here is the scorer's raw slow-wave slope (imu_fixch), 30–150 s before each 10-s NREM step. 95–96 k held-out steps,
6/6 animals.

**Short answer.**
- P is not a proxy for depth. P carries REM-entry information that recent depth does not, on both scorings.
- Depth adds nothing beyond P on FINAL. On pass2med it adds a little, almost all for waking. pass2med is scored on this
  very slow-wave axis, so that gain is probably circular.
- The night's lower REM entry does not go through depth.
- The count predicts the coming NREM depth: the longer since the last REM, the shallower the NREM.

- **(b) P is not a proxy (#65).**
  - P + D vs D: −2.03 % [−2.39, −1.62] (FINAL) and −1.91 % [−2.17, −1.62] (pass2med), 6/6. Almost all of it is REM:
    −5.1 % / −4.7 %.
  - D-only vs P-only is worse: +2.03 % / +1.71 % (REM +5.4 % / +4.9 %).
  - Depth alone predicts waking slightly better than P: −0.14 % [−0.27, −0.01] (FINAL, 3/6); −0.36 % (pass2med, 6/6).
- **(a) Depth beyond P (#66).**
  - FINAL: −0.045 % [−0.131, +0.064], 3/6. With a 60-s lag: −0.035 %.
  - pass2med: −0.235 % [−0.341, −0.117], 6/6 — WAKE −0.34 % (6/6), REM −0.07 % (4/6). With a 60-s lag: −0.10 %, 4/6
    (not held).
  - The 1-h-earlier control is ≈ 0 on both (+0.009 % / +0.035 %).
  - Rule (a) holds on pass2med only. FINAL picks its scorer channels per session, so it is partly independent of this
    axis, and it shows nothing. The pass2med gain is read as the scorer's axis predicting the scorer's waking.
- **(d) Night via depth: no (#67).**
  - REM-vs-stay dark coefficient: −0.689 → −0.712 (FINAL), −0.697 → −0.648 (pass2med).
  - Depth × dark: +0.006 % / −0.005 %.
  - The night gate (#14b) is not depth.
- **(e) Depth as the outcome (#68).**
  - Adding the P spline to clock + wake history + elapsed time improves held-out prediction of depth 30–150 s ahead:
    MSE −3.35 % [−5.12, −1.64] (FINAL), −0.95 % [−1.65, −0.17] (pass2med).
  - The slope is negative (−0.12 / −0.08 per unit ln(1 + P)), 6/6 animals.
  - Shared predictive information, in astra's wording, not "the same homeostat". Part of it may be the decline of depth
    right before REM inside the window.
- **What it changes:**
  - #4's lagged-depth gain (−0.22 % against the older feature model) is absorbed by the count on FINAL.
  - The count model stands without depth.
  - The next LFP steps are L2(a) (#60 with pre-transition depth on the evening post-round steps) and L2(b) (theta
    before the first REM, with the scorer's th). L2(c) waits for the manual video labels.

## Definitions

```
Sleep LFP stage, step L1 (plan implementation_plan/2026-10-10-sleep-lfp-stage.md, revision 1, written before results):
NREM depth and the REM-entry count P — is P a behavioural proxy for depth, a parallel process, or is depth redundant?

Usage:  python ephys/sleep_lfp.py L1 [--scorings final pass2med] [--workers 6]
        python ephys/sleep_lfp.py --selftest

Definitions (records, 10-s NREM steps, folds and the B-full spec as ephys/sleep_model.py; t = the step start, s into
its record; the depth reading reuses ephys/rem_ripple_model.py):
  depth d       per second, the raw slow-wave slope `sw` of the fixed-channel rescore imu_fixch (SleepScoreRaw.npz on
                storage; the scorer's negative IRASA slope on the per-animal sw_channel; larger = deeper), over the
                sessions of the SWR quality guide except tier `exclude`; masked outside NREM, after `use_until` and in the
                probe-advance settle windows; z within animal x probe block (`block_from`) over its NREM seconds.
  dep           mean z over the NREM seconds with a value in [t - 150, t - 30) s (missing if < 60 such seconds)
  dep60         the same over [t - 180, t - 60) s (lag sensitivity)
  depc          the same over [t - 3750, t - 3630) s (negative control: the same width 1 h earlier)
  dep_fut       the same over [t + 30, t + 150) s (outcome of rule (e))
  models        multinomial stay / REM / WAKE on identical held-out steps (forward chaining, folds 1..):
                P = B-full; D = B-full with the P spline replaced by a spline of dep; P+D = B-full + dep (linear);
                P+D+Dd = P+D + dep x dark. Lag and control comparisons on their own subsets (P vs P+dep60, P vs P+depc).
                Delta = held-out log-loss change in % of the smaller model, fold bootstrap CI, for the total and for the
                binary REM and WAKE log-loss (rem_ripple_model.outcome_split); holds = CI upper < 0 and >= n - 1 of n
                animals better.
  rules (both scorings)
    (a) depth adds         P+D vs P holds, and the control P+depc vs P has CI covering 0
    (b) P is a proxy       P+D vs D does not hold, AND D vs P: D's log-loss <= P's (Delta <= 0)
    (c) two processes      (a) AND P+D vs D holds
    (d) night via depth    the full-data REM-vs-stay dark coefficient falls from P to P+D AND P+D+Dd vs P+D holds
                           (a smaller dark coefficient alone = reallocation)
    (e) depth reads the homeostat   held-out OLS of dep_fut on [clock, dark, day, L1, has_anchor, elapsed spline,
                           animal] + spline(ln(1 + P)) beats the same without P (Delta MSE % CI < 0) and the per-animal
                           linear P slope has the pooled sign in >= n - 1 of n animals
```

## Verdicts

| scores | rule | pass | numbers |
|---|---|---|---|
| final | (a) depth adds | False | P+D vs P -0.045 % [-0.131, +0.064], 3/6; control P+Dc vs P +0.009 % [-0.015, +0.034], 4/6 |
| final | (b) P is a proxy | False | P+D vs D -2.033 % [-2.386, -1.619], 6/6; D vs P +2.030 % [+1.556, +2.445], 0/6 |
| final | (c) two processes | False | (a) False; P+D vs D holds True |
| final | (d) night via depth | False | dark REM coef P -0.689 -> P+D -0.712; P+D+Dd vs P+D +0.006 % [-0.032, +0.047], 3/6 |
| final | (e) depth reads the homeostat | True | Delta MSE -3.35 % [-5.12, -1.64]; P slope -0.124, same sign 6/6 |
| pass2med | (a) depth adds | True | P+D vs P -0.235 % [-0.341, -0.117], 6/6; control P+Dc vs P +0.035 % [-0.051, +0.150], 1/6 |
| pass2med | (b) P is a proxy | False | P+D vs D -1.911 % [-2.167, -1.623], 6/6; D vs P +1.709 % [+1.370, +1.991], 0/6 |
| pass2med | (c) two processes | True | (a) True; P+D vs D holds True |
| pass2med | (d) night via depth | False | dark REM coef P -0.697 -> P+D -0.648; P+D+Dd vs P+D -0.005 % [-0.042, +0.029], 4/6 |
| pass2med | (e) depth reads the homeostat | True | Delta MSE -0.95 % [-1.65, -0.17]; P slope -0.080, same sign 6/6 |

## Coverage

| scores | steps_all | steps_dep | steps_dep60 | steps_control | rem_ends_dep | animals |
|---|---|---|---|---|---|---|
| final | 179668 | 139396 | 133531 | 67548 | 2752 | 6 |
| pass2med | 185090 | 144854 | 139086 | 69412 | 2958 | 6 |

## Held-out comparisons (total, REM, WAKE log-loss)

| scores | subset | comparison | metric | delta_pct | ci_lo_pct | ci_hi_pct | animals_better | animals | n_steps | holds |
|---|---|---|---|---|---|---|---|---|---|---|
| final | main (dep, lag 30 s) | P+D vs P | total | -0.0451 | -0.1305 | 0.064 | 3 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | P+D vs P | rem | 0.0485 | -0.0672 | 0.1755 | 4 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | P+D vs P | wake | -0.1063 | -0.2198 | 0.0412 | 4 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | P+D vs D | total | -2.0334 | -2.3861 | -1.6187 | 6 | 6 | 95661 | True |
| final | main (dep, lag 30 s) | P+D vs D | rem | -5.1177 | -6.0113 | -4.1076 | 6 | 6 | 95661 | True |
| final | main (dep, lag 30 s) | P+D vs D | wake | 0.0284 | -0.0571 | 0.1491 | 2 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | D vs P | total | 2.0295 | 1.5556 | 2.4449 | 0 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | D vs P | rem | 5.4449 | 4.367 | 6.4194 | 0 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | D vs P | wake | -0.1346 | -0.267 | -0.0121 | 3 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | P+D+Dd vs P+D | total | 0.0057 | -0.0319 | 0.0469 | 3 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | P+D+Dd vs P+D | rem | -0.0439 | -0.2001 | 0.0989 | 3 | 6 | 95661 | False |
| final | main (dep, lag 30 s) | P+D+Dd vs P+D | wake | 0.0359 | -0.0305 | 0.1163 | 1 | 6 | 95661 | False |
| final | lag 60 s (dep60) | P+D60 vs P | total | -0.0347 | -0.0914 | 0.0281 | 4 | 6 | 92059 | False |
| final | lag 60 s (dep60) | P+D60 vs P | rem | -0.0152 | -0.1091 | 0.1018 | 4 | 6 | 92059 | False |
| final | lag 60 s (dep60) | P+D60 vs P | wake | -0.0509 | -0.1521 | 0.0502 | 4 | 6 | 92059 | False |
| final | control subset (depc, 1 h earlier) | P+D vs P | total | 0.0745 | -0.0444 | 0.2535 | 2 | 6 | 50028 | False |
| final | control subset (depc, 1 h earlier) | P+D vs P | rem | 0.2515 | 0.0184 | 0.6276 | 0 | 6 | 50028 | False |
| final | control subset (depc, 1 h earlier) | P+D vs P | wake | -0.059 | -0.1531 | 0.0648 | 4 | 6 | 50028 | False |
| final | control subset (depc, 1 h earlier) | P+Dc vs P | total | 0.0095 | -0.0147 | 0.0343 | 4 | 6 | 50028 | False |
| final | control subset (depc, 1 h earlier) | P+Dc vs P | rem | 0.0092 | -0.0998 | 0.1161 | 2 | 6 | 50028 | False |
| final | control subset (depc, 1 h earlier) | P+Dc vs P | wake | 0.0099 | -0.0695 | 0.0844 | 3 | 6 | 50028 | False |
| pass2med | main (dep, lag 30 s) | P+D vs P | total | -0.235 | -0.3413 | -0.1172 | 6 | 6 | 96145 | True |
| pass2med | main (dep, lag 30 s) | P+D vs P | rem | -0.0701 | -0.1214 | -0.0089 | 4 | 6 | 96145 | False |
| pass2med | main (dep, lag 30 s) | P+D vs P | wake | -0.3392 | -0.4936 | -0.1768 | 6 | 6 | 96145 | True |
| pass2med | main (dep, lag 30 s) | P+D vs D | total | -1.9113 | -2.1665 | -1.6226 | 6 | 6 | 96145 | True |
| pass2med | main (dep, lag 30 s) | P+D vs D | rem | -4.7171 | -5.3564 | -4.0099 | 6 | 6 | 96145 | True |
| pass2med | main (dep, lag 30 s) | P+D vs D | wake | 0.0192 | -0.0556 | 0.0944 | 3 | 6 | 96145 | False |
| pass2med | main (dep, lag 30 s) | D vs P | total | 1.7089 | 1.3695 | 1.9909 | 0 | 6 | 96145 | False |
| pass2med | main (dep, lag 30 s) | D vs P | rem | 4.8771 | 4.1408 | 5.5295 | 0 | 6 | 96145 | False |
| pass2med | main (dep, lag 30 s) | D vs P | wake | -0.3583 | -0.5407 | -0.1583 | 6 | 6 | 96145 | True |
| pass2med | main (dep, lag 30 s) | P+D+Dd vs P+D | total | -0.0049 | -0.042 | 0.0286 | 4 | 6 | 96145 | False |
| pass2med | main (dep, lag 30 s) | P+D+Dd vs P+D | rem | -0.0161 | -0.0962 | 0.0613 | 3 | 6 | 96145 | False |
| pass2med | main (dep, lag 30 s) | P+D+Dd vs P+D | wake | 0.0036 | -0.0112 | 0.0166 | 3 | 6 | 96145 | False |
| pass2med | lag 60 s (dep60) | P+D60 vs P | total | -0.1036 | -0.1571 | -0.0573 | 4 | 6 | 92467 | False |
| pass2med | lag 60 s (dep60) | P+D60 vs P | rem | 0.0084 | -0.0334 | 0.0543 | 3 | 6 | 92467 | False |
| pass2med | lag 60 s (dep60) | P+D60 vs P | wake | -0.1813 | -0.2717 | -0.1117 | 4 | 6 | 92467 | False |
| pass2med | control subset (depc, 1 h earlier) | P+D vs P | total | -0.1106 | -0.2169 | 0.0151 | 5 | 6 | 49350 | False |
| pass2med | control subset (depc, 1 h earlier) | P+D vs P | rem | -0.0139 | -0.1298 | 0.1035 | 3 | 6 | 49350 | False |
| pass2med | control subset (depc, 1 h earlier) | P+D vs P | wake | -0.1823 | -0.3461 | 0.0206 | 5 | 6 | 49350 | False |
| pass2med | control subset (depc, 1 h earlier) | P+Dc vs P | total | 0.0346 | -0.0512 | 0.1498 | 1 | 6 | 49350 | False |
| pass2med | control subset (depc, 1 h earlier) | P+Dc vs P | rem | -0.0225 | -0.1116 | 0.0568 | 3 | 6 | 49350 | False |
| pass2med | control subset (depc, 1 h earlier) | P+Dc vs P | wake | 0.0798 | -0.0142 | 0.2439 | 2 | 6 | 49350 | False |

## (d) The dark coefficient (REM vs stay, per unit of dark, full data)

| scores | dark_REM_coef_P | dark_REM_coef_P+D |
|---|---|---|
| final | -0.6889 | -0.7116 |
| pass2med | -0.6968 | -0.6482 |

## (e) Depth as the outcome

| scores | steps | delta_mse_pct | ci_lo_pct | ci_hi_pct | pooled_P_slope | animals_same_sign | animals | per_animal_slopes |
|---|---|---|---|---|---|---|---|---|
| final | 112758 | -3.3533 | -5.1207 | -1.6358 | -0.1242 | 6 | 6 | SF07 -0.211; SF08 -0.052; SF09 -0.108; SF10 -0.048; SF11 -0.051; SF12 -0.110 |
| pass2med | 118045 | -0.9453 | -1.6535 | -0.1737 | -0.0801 | 6 | 6 | SF07 -0.118; SF08 -0.054; SF09 -0.079; SF10 -0.053; SF11 -0.065; SF12 -0.114 |

