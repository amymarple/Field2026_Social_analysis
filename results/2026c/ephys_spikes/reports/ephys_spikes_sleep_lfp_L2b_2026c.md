# Sleep LFP stage — L2(b): REM-like theta before the first REM, evening rounds vs natural evening wakes (cohort 2026c)

Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) §9 revision 3 (rules written before results). Driver `ephys/sleep_lfp.py L2b` (commit e66373d+dirty); bulk `D:\Field2026_analysis_out\2026c\sleep_lfp_L2b_20261010_2314` (events.csv); runtime 3 min. **Technical ledger.** th = the scorer's theta / delta axis (imu_fixch); CA1 = the theta session's cache (theta_on & f_peak < 10 Hz). SF10's CA1 site is the scorer's theta channel in 19 of its sessions: CA1 rows are also given without SF10.

## Reading (main session, 2026-10-10; claim #70; #60 updated)

**Pre-registered test: not passed, and uninformative.** The REM-like share of the scorer's th (NREM-scored seconds with
th ≥ the block's REM 25th percentile) sits at its floor: 0.0–0.5 % of seconds in both groups. That is close to
structural, because the scorer calls a second REM mainly when th is high. This test cannot detect a labelling lag either
way.

**What the data do show** (secondary measures, reported by the plan; sensitivities marked post hoc):
- **More theta across the whole window, not at the boundary.**
  - The scorer's z-th in the last 10 min of NREM before the first REM after an evening round is higher than before the
    first REM after a natural evening wake: FINAL +0.19 SD [+0.03, +0.36], pass2med +0.25 [+0.14, +0.36].
  - Without the last 2 min (post hoc): FINAL +0.21 [+0.05, +0.35], 5/6 animals; pass2med +0.25 [+0.11, +0.37], 4/6.
  - With both groups restricted to a first REM at 19–24 h (post hoc; 8 vs 11–15 events): +0.17 / +0.29.
  - Minute by minute (description), R-evening sits higher from about 8 min before REM. The final-minute rise is not
    larger (FINAL 0.42 vs 0.79 SD; pass2med 0.52 vs 0.56): REM is not being labelled late.
- **CA1 REM-like theta** (theta_on and peak < 10 Hz, the theta session's cache):
  - +4.7 points of seconds on FINAL [+1.3, +8.7], 5/5 animals; +3.2 on pass2med [+1.0, +5.8], 4/5. The same without
    SF10, whose CA1 site is the scorer's channel.
  - On IMU-still seconds only (post hoc) it shrinks to +1.8 [−0.2, +3.8] (FINAL) and +2.0 [+0.5, +3.4] (pass2med).
    About half of the extra CA1 theta falls in seconds where the head moves: brief stirring inside scored NREM.
- **Reading for #60.** The extra NREM before the first post-round REM is a lighter, theta-richer and partly restless
  NREM. It is not REM scored as NREM at the transition. This fits the raised waking in the first hour after a round
  (#61, #63).

**Limits:**
- 23 vs 12 events on FINAL (22 vs 16 on pass2med), with 1–3 natural evening events per animal.
- The groups' clocks differ (first REM at median 18 h vs 22 h); the clock-matched check is small.
- th is the scorer's own axis; on pass2med it is also the axis that decides REM.
- No video yet: whether the stirring is grooming, posture shifts or brief waking is open.

### Definitions

- **Window:** the NREM-scored seconds $s$ in $[\max(t_R - 600, t_N),\ t_R - 2)$ s.
  - $t_R$ = the first REM bout start after the sleep onset $t_N$, with no WAKE ≥ 30 min in between.
  - At least 60 such seconds (with th and a valid probe block) are required.
- **z-th:** $z_s = (\mathrm{th}_s - \mu_b)/\sigma_b$, where $\mu_b, \sigma_b$ are the mean and SD of th over all
  NREM seconds of the animal × probe block $b$. th = the scorer's theta / delta ratio (imu_fixch `SleepScoreRaw.npz`).
  Unit: block SD; 0 = a typical NREM second.
- **REM-like share (th):** $\frac{1}{|W|}\sum_{s\in W} \mathbb{1}[\mathrm{th}_s \ge q_{25}^{\mathrm{REM}}(b)]$, where
  $q_{25}^{\mathrm{REM}}(b)$ is the 25th percentile of th over the block's REM seconds. Range 0–1.
- **CA1 REM-like share:** the fraction of the window's seconds with theta_on and $f_{\mathrm{peak}} < 10$ Hz in the
  theta session's cache. Needs ≥ 60 cache seconds. The still variant keeps only seconds with head-IMU state "still".
- **Comparison:** $\Delta = \frac{1}{A}\sum_a (\bar x_{R,a} - \bar x_{N,a})$ over the $A$ animals with both kinds.
  - The 95 % CI comes from 2000 bootstrap resamples of events within each animal and kind.
  - The animal count reports how many per-animal differences are > 0.

## Verdicts

| scores | pass | numbers |
|---|---|---|
| final | False | REM-like th share R 0.001 vs N 0.005: diff -0.003 [-0.007, +0.001], 1/6 animals higher; CA1 REM-like diff +0.047 [+0.013, +0.087] |
| pass2med | False | REM-like th share R 0.001 vs N 0.000: diff +0.001 [-0.000, +0.004], 3/6 animals higher; CA1 REM-like diff +0.032 [+0.010, +0.058] |

## R-evening vs N-evening (mean of the per-animal differences; bootstrap within animals)

| scores | subset | measure | R_evening_events | N_evening_events | R_mean | N_mean | diff_mean_of_animals | ci_lo | ci_hi | animals_pos | animals | per_animal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| final | all | remlike_th_share | 23 | 12 | 0.0011 | 0.0052 | -0.0025 | -0.0072 | 0.0014 | 1 | 6 | SF07 -0.017; SF08 -0.003; SF09 +0.000; SF10 +0.000; SF11 +0.000; SF12 +0.005 |
| final | all | z_th_mean | 23 | 12 | -0.0207 | -0.1549 | 0.1943 | 0.0302 | 0.3575 | 3 | 6 | SF07 -0.052; SF08 -0.088; SF09 +0.775; SF10 +0.240; SF11 +0.323; SF12 -0.033 |
| final | all | ca1_remlike_share | 21 | 11 | 0.094 | 0.0541 | 0.0466 | 0.0133 | 0.0873 | 5 | 5 | SF07 +0.044; SF08 +0.079; SF09 +0.092; SF10 +0.006; SF12 +0.013 |
| final | all | ca1_remlike_share (no SF10) | 15 | 8 | 0.1221 | 0.0677 | 0.0567 | 0.0124 | 0.1057 | 4 | 4 | SF07 +0.044; SF08 +0.079; SF09 +0.092; SF12 +0.013 |
| final | all | ca1_logtd_mean | 21 | 11 | -0.1193 | -0.1687 | 0.0598 | -0.002 | 0.1186 | 3 | 5 | SF07 +0.127; SF08 -0.064; SF09 +0.153; SF10 +0.086; SF12 -0.003 |
| final | all | ca1_logtd_mean (no SF10) | 15 | 8 | -0.1381 | -0.1725 | 0.0532 | -0.0229 | 0.1285 | 2 | 4 | SF07 +0.127; SF08 -0.064; SF09 +0.153; SF12 -0.003 |
| final | all | z_th_early [post hoc] | 21 | 12 | -0.1321 | -0.2979 | 0.2046 | 0.0481 | 0.3539 | 5 | 6 | SF07 +0.079; SF08 +0.225; SF09 +0.435; SF10 +0.276; SF11 +0.265; SF12 -0.052 |
| final | all | ca1_remlike_share_still [post hoc] | 17 | 11 | 0.0622 | 0.0535 | 0.0177 | -0.0017 | 0.038 | 4 | 5 | SF07 +0.008; SF08 -0.013; SF09 +0.075; SF10 +0.003; SF12 +0.016 |
| final | posthoc: first REM 19-24 h | z_th_mean | 8 | 11 | -0.1623 | -0.199 | 0.1702 | 0.0735 | 0.2725 | 3 | 5 | SF08 -0.018; SF09 +0.218; SF10 +0.087; SF11 +0.673; SF12 -0.109 |
| final | posthoc: first REM 19-24 h | ca1_remlike_share | 7 | 10 | 0.0982 | 0.0473 | 0.1066 | 0.1017 | 0.1114 | 3 | 4 | SF08 +0.365; SF09 +0.065; SF10 +0.000; SF12 -0.004 |
| pass2med | all | remlike_th_share | 22 | 16 | 0.0014 | 0.0003 | 0.0013 | -0.0002 | 0.0036 | 3 | 6 | SF07 +0.007; SF08 -0.001; SF09 +0.000; SF10 +0.000; SF11 +0.000; SF12 +0.002 |
| pass2med | all | z_th_mean | 22 | 16 | 0.0089 | -0.2066 | 0.2498 | 0.1391 | 0.3625 | 4 | 6 | SF07 +0.196; SF08 -0.003; SF09 +0.669; SF10 +0.288; SF11 +0.358; SF12 -0.009 |
| pass2med | all | ca1_remlike_share | 20 | 15 | 0.0712 | 0.0446 | 0.0324 | 0.01 | 0.0578 | 4 | 5 | SF07 +0.081; SF08 -0.018; SF09 +0.076; SF10 +0.010; SF12 +0.013 |
| pass2med | all | ca1_remlike_share (no SF10) | 14 | 11 | 0.0884 | 0.0531 | 0.038 | 0.0098 | 0.0703 | 3 | 4 | SF07 +0.081; SF08 -0.018; SF09 +0.076; SF12 +0.013 |
| pass2med | all | ca1_logtd_mean | 20 | 15 | -0.1215 | -0.1924 | 0.0767 | 0.0227 | 0.1276 | 3 | 5 | SF07 +0.223; SF08 -0.088; SF09 +0.165; SF10 +0.088; SF12 -0.004 |
| pass2med | all | ca1_logtd_mean (no SF10) | 14 | 11 | -0.1466 | -0.2074 | 0.0738 | 0.0083 | 0.1353 | 2 | 4 | SF07 +0.223; SF08 -0.088; SF09 +0.165; SF12 -0.004 |
| pass2med | all | z_th_early [post hoc] | 20 | 16 | -0.1058 | -0.3123 | 0.245 | 0.1115 | 0.3709 | 4 | 6 | SF07 +0.224; SF08 -0.032; SF09 +0.625; SF10 +0.345; SF11 +0.313; SF12 -0.005 |
| pass2med | all | ca1_remlike_share_still [post hoc] | 16 | 15 | 0.0582 | 0.0443 | 0.0202 | 0.0053 | 0.0345 | 4 | 5 | SF07 +0.019; SF08 -0.007; SF09 +0.067; SF10 +0.008; SF12 +0.014 |
| pass2med | posthoc: first REM 19-24 h | z_th_mean | 8 | 15 | -0.073 | -0.2359 | 0.2935 | 0.1413 | 0.4492 | 3 | 4 | SF09 +0.470; SF10 +0.165; SF11 +0.555; SF12 -0.017 |
| pass2med | posthoc: first REM 19-24 h | ca1_remlike_share | 7 | 14 | 0.0552 | 0.0396 | 0.0248 | 0.0046 | 0.0449 | 3 | 3 | SF09 +0.063; SF10 +0.008; SF12 +0.003 |

## Trajectory: mean z-th per minute before the first REM

| scores | group | min_before_REM | mean | count |
|---|---|---|---|---|
| final | N-evening | 1 | 0.791 | 12 |
| final | N-evening | 2 | -0.149 | 12 |
| final | N-evening | 3 | -0.315 | 12 |
| final | N-evening | 4 | -0.248 | 12 |
| final | N-evening | 5 | -0.224 | 11 |
| final | N-evening | 6 | -0.355 | 10 |
| final | N-evening | 7 | -0.172 | 11 |
| final | N-evening | 8 | -0.275 | 10 |
| final | N-evening | 9 | -0.294 | 10 |
| final | N-evening | 10 | -0.252 | 10 |
| final | N-other | 1 | 0.252 | 108 |
| final | N-other | 2 | -0.448 | 105 |
| final | N-other | 3 | -0.355 | 107 |
| final | N-other | 4 | -0.368 | 104 |
| final | N-other | 5 | -0.381 | 102 |
| final | N-other | 6 | -0.444 | 98 |
| final | N-other | 7 | -0.312 | 100 |
| final | N-other | 8 | -0.296 | 92 |
| final | N-other | 9 | -0.322 | 91 |
| final | N-other | 10 | -0.263 | 92 |
| final | R-evening | 1 | 0.422 | 23 |
| final | R-evening | 2 | -0.008 | 22 |
| final | R-evening | 3 | -0.265 | 20 |
| final | R-evening | 4 | -0.077 | 21 |
| final | R-evening | 5 | -0.065 | 19 |
| final | R-evening | 6 | -0.086 | 18 |
| final | R-evening | 7 | -0.194 | 15 |
| final | R-evening | 8 | 0.161 | 15 |
| final | R-evening | 9 | -0.255 | 13 |
| final | R-evening | 10 | -0.249 | 13 |
| pass2med | N-evening | 1 | 0.557 | 16 |
| pass2med | N-evening | 2 | -0.224 | 15 |
| pass2med | N-evening | 3 | -0.349 | 15 |
| pass2med | N-evening | 4 | -0.331 | 16 |
| pass2med | N-evening | 5 | -0.208 | 13 |
| pass2med | N-evening | 6 | -0.341 | 13 |
| pass2med | N-evening | 7 | -0.441 | 15 |
| pass2med | N-evening | 8 | -0.362 | 13 |
| pass2med | N-evening | 9 | -0.243 | 14 |
| pass2med | N-evening | 10 | -0.226 | 13 |
| pass2med | N-other | 1 | 0.386 | 120 |
| pass2med | N-other | 2 | -0.407 | 118 |
| pass2med | N-other | 3 | -0.311 | 120 |
| pass2med | N-other | 4 | -0.359 | 119 |
| pass2med | N-other | 5 | -0.336 | 117 |
| pass2med | N-other | 6 | -0.371 | 113 |
| pass2med | N-other | 7 | -0.332 | 112 |
| pass2med | N-other | 8 | -0.265 | 111 |
| pass2med | N-other | 9 | -0.284 | 111 |
| pass2med | N-other | 10 | -0.206 | 106 |
| pass2med | R-evening | 1 | 0.522 | 22 |
| pass2med | R-evening | 2 | -0.08 | 22 |
| pass2med | R-evening | 3 | -0.255 | 20 |
| pass2med | R-evening | 4 | -0.032 | 20 |
| pass2med | R-evening | 5 | 0.074 | 17 |
| pass2med | R-evening | 6 | -0.043 | 16 |
| pass2med | R-evening | 7 | -0.159 | 13 |
| pass2med | R-evening | 8 | 0.143 | 13 |
| pass2med | R-evening | 9 | -0.23 | 13 |
| pass2med | R-evening | 10 | -0.241 | 12 |

