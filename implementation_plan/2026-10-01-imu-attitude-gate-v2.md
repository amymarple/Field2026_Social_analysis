# Head-IMU attitude gate v2: strict accelerometer-led still windows, centre-to-centre propagation, day-sleep data, and a chained-anchor test of whether the gyro drift is linear (cohort 2026c)

- **Status:** approved by the user 2026-10-01 ("去吧"); written **before** any computation on the test data. Every rule
  that turns data into a choice is fixed here; development runs touch the **tuning periods only**; the gate is evaluated
  once, on the test periods, with the Phase-0 thresholds unchanged. Amendments, if any, are appended below *before* the
  full run and listed as deviations in the report.
- **Why (user, 2026-10-01):** Phase 0 FAILED its gate (2–5 s 1.76°, 5–15 s 3.29° vs 1.0° / 2.0°), but its "quiet"
  edge windows were defined by |ω| < 10 °/s and an |a|-based criterion that is blind to rotation (gravity redistributes
  between axes at constant |a|); those windows carried a median 8.5° of integrated head rotation that the test did not
  propagate, and the error scaled with edge motion (e ∝ Θ^0.31·edge^0.75), not duration
  ([Phase-0 report §8](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_phase0_2026c.md)). User:
  "静止你肯定不能用gyroscope得用acc做判定 … 门槛失败可能是关键"; "静止window可以用wiser+acc选白天老鼠睡觉几乎不动";
  "gyroscope是线性漂移么". This plan re-tests the gate with still windows chosen by the accelerometer direction, adds
  daytime sleep (long, truly still windows), propagates through the windows from centre to centre, and asks whether
  the residual drift is linear in time, a random walk, or rotation-driven.
- **Follows:** [`change_log/2026-09-30-imu-attitude-phase0.md`](../change_log/2026-09-30-imu-attitude-phase0.md),
  plan [`2026-09-30-imu-attitude-phase0.md`](2026-09-30-imu-attitude-phase0.md). Phase-0 functions are **imported, never
  edited** (`wiser/scripts/analyze_imu_attitude_phase0.py`: cache loading, Hampel + saturation classes + held-reading
  reconstruction, the 100-Hz gyro chain, `BoutSet`, the four gyro models + Huber fit + bootstrap, Rodrigues propagation,
  `fit_growth`). The day caches are built with the cache builder's own functions
  (`wiser/scripts/build_imu_wiser_cache.py`: `cache_imu_window`, `wiser_night`) and the V4 A3 chain functions
  (`wiser/scripts/analyze_wiser_ins_fusion.py`: `_hampel_lanes`, `hampel_floor`, `any_per_100hz`, `count_per_100hz`,
  `window_stats`, `fit_ellipsoid`, `quiet_seconds`, `bias_running`, `apply_acc`).
- **Scope:** IMU attitude only; WISER is used only as a still-window filter. No fusion is run. Direction
  `wiser_baseline` (a measurement question; no behavioural claim).
- **Rules (user):** never open or judge images; raw drives read-only (E:, F:, Q:); SQLite `mode=ro`; do not edit
  existing scripts; no git commit; pre-register before touching test data; report pass/fail honestly; runtime ≤ 2 h.
- **Code (new):** `wiser/scripts/analyze_imu_attitude_gate_v2.py` (`--build-day-caches`, `--roles tuning` for
  development, `--selftest`, `--report-only <run_dir>`). **Config (new):** `wiser/configs/imu_attitude_gate_v2_2026c.json`
  (periods, sessions, every threshold below; the run writes the frozen model selection and results into `fitted`).
- **Outputs:** bulk `D:\Field2026_analysis_out\2026c\imu_attitude_gate_v2_<ts>\`; report
  `results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_gate_v2_2026c.md` + figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_imu_attitude_gate_v2_*_2026c.png`, pointer
  `run_manifest_imu_attitude_gate_v2_2026c.json` (the folder's `run_manifest.json` is never touched);
  `change_log/2026-10-01-imu-attitude-gate-v2.md` + top rows in both index READMEs; only the `wiser_baseline` row of
  CLAUDE.md's WISER table is edited (mention the day caches). Index files are re-read right before editing.

## 1. Data

### Periods (field-PC local time, EDT, naive)

| key | role | analysis window | source |
|---|---|---|---|
| `night_20260908` | tuning | 2026-09-08 21:00 → 09-09 04:20 | existing A1 / A3 / A2 caches |
| `day_20260908` | tuning | 2026-09-08 08:00 → 18:30 | **new day caches** |
| `night_20260910` | test | 2026-09-10 21:00 → 09-11 04:20 | existing caches |
| `day_20260911` | test | 2026-09-11 10:00 → 17:30 | **new day caches** |

Animals SF07 SF08 SF09 SF10 SF12. Still windows, bouts, anchors and chains must lie inside the analysis window (the
cached margins are processed by the filters and the bias estimate but never analysed). This narrows Phase 0, which used
the whole cached 20:50 → 05:30 night window (declared deviation, as specified by the user).

**Day sessions** (session index `results/2026c/ephys_spikes/reports/ephys_spikes_session_index_2026c.csv`; all FM65;
pc_time chain verdict `OK-native` for all ten; fits at
`Q:\hc997\SocialFieldRat2026\3rd_rat\analysis\pc_time\<SFxx>\<session>\pc_time_fit.json`; raw
`E:\3rd_rat_spikes\<SFx>\<MAC>\<session>\analogin.dat` via `ephys/_common.find_session_dir`):

| animal | tuning day 09-08 | test day 09-11 |
|---|---|---|
| SF07 | `5_20260908_071513.175` (07:15:13 → 18:55:54) | `2_20260911_091615.116` (09:16:15 → 18:27:25) |
| SF08 | `5_20260908_071754.325` (07:17:54 → 18:54:15) | `3_20260911_091931.245` (09:19:31 → 18:23:51) |
| SF09 | `6_20260908_072057.385` (07:20:57 → 18:57:24) | `2_20260911_092224.167` (09:22:24 → 17:35:59, auto-stop) |
| SF10 | `8_20260908_072352.245` (07:23:52 → 18:58:43) | `2_20260911_092441.104` (09:24:41 → 18:25:50) |
| SF12 | `5_20260908_072624.615` (07:26:24 → 19:00:35) | `3_20260911_094747.706` (09:47:47 → 18:29:17; field-flagged for its neural connector only — the IMU is usable, as instructed) |

**Regime record checked** (field2026-sync `f667640` incident log 2026-09-21; recording repo `f03b0c0`;
`cv/configs/cohort3_handling_windows.json`; `cohorts/2026c.yaml`): no handling round inside any analysis window (09-08
AM 06:21–07:26, PM 18:54–19:48; 09-10 PM 18:39–19:50; 09-11 AM 08:06–09:48, PM 18:23–19:40); no ADC-lane window (09-10
only, ends 20:53); no `imu_valid_until` for these animals (only SF11). Context carried into the report, not masked:
**construction near the paddock from ~07:50 on 09-08 (end never logged)** — the tuning day is a disturbed day; BLE-only
connect/anchor passes 09-08 12:15–12:41 and 09-11 16:51–16:58 (no handling); SF09's 09-11 day cell ran low from 16:41
(auto-stop ~17:32–17:36, after the window); SF12 shanks 1/4 loosening contact from 09-10 (neural, not IMU).

### Day caches (built once, same roots and formats, never overwriting)

- **A1 day:** `cache_imu_window` on each day session for [day start − 10 min, day end + 10 min] clipped to the session
  (09-08: 07:50 → 18:40; 09-11: 09:50 → 17:40) → `D:\Field2026_analysis_out\2026c\imu_raw_cache\<SFxx>\<session>__<start>_<end>.npz`
  (the builder's own name; the stamps T0750…/T0950… and the session distinguish them from the night files); meta
  `night = "day_<date>"`, `night_role = "day_tuning" | "day_test"`. New index `imu_raw_cache\index_day_2026c.csv` (the
  existing `index_2026c.csv` is not rewritten).
- **A3-equivalent day:** `imu100_cache\<SFxx>\day_<date>.npz` with exactly the A3 keys and chain as decided by V4 on the
  tuning night and stored in the night A3 `calib_json` (Hampel half-window 3 / 6 σ / floor 2 counts → Butterworth-4
  zero-phase 40 Hz on acc and gyro → `resample_poly(2, 25)` → head frame `S`; per-window ellipsoid accelerometer
  calibration from the 0.5-s quasi-static windows; running-median gyro bias of the quiet-second medians ± 300 s, ≥ 20;
  `gyr = 1.03 (w − b)`; flags `sat_acc`, `sat_gyr` (dilated 5 samples), `frozen`, `spikes`, `quiet` (make_imu 1-s rule);
  `calib_json` incl. `bias_nodes_1min`; `meta_json.source_a1`). Because the chain is identical, the Phase-0 identity
  b = w − gyr/1.03 holds and Phase 0's loader, saturation reconstruction and gyro models apply unchanged ("the Phase-0
  calibration chain" = Phase 0's `gyro_chain` on these files at analysis time).
- **A2 day:** `wiser_night` on `D:\Field2026_analysis_out\2026c\wiser_working\3rdcohort_Spike_2026_3_4.sqlite`
  (`mode=ro`, sha256 prefix `82ccadfde589` checked) for the day window ± 10 min, tags from
  `wiser/configs/rat_identities_2026c.csv`, same dedup rule and masks (handling, all-tag silences ± 120 s, tag validity,
  ADC lane) → `wiser_fix_cache\day_<date>\<SFxx>.csv.gz`; new index `wiser_fix_cache\index_day_2026c.csv`.
- A `README.md` is written in each of the three cache roots (none exists yet) documenting the formats and the day files.

## 2. Definitions and rules (all fixed now)

Notation: 100-Hz head-frame samples k, Δt = 0.01 s; $\mathbf a_k$ = calibrated accelerometer (m/s²);
$\mathbf w_k-\mathbf b_k$ = Phase-0 gyro chain (Hampel → held-reading reconstruction → 40 Hz → 100 Hz → head frame)
minus the A3 bias (°/s); $\boldsymbol\omega_k=M(\mathbf w_k-\mathbf b_k)$ for a gyro model M; $g$ = 9.81 m/s².
**Valid sample:** inside the analysis window, not `frozen`, not in a handling window, IMU-valid.

### 2.1 Strict still window (accelerometer-led)
- 0.1-s blocks j (10 samples, aligned to the period array): block mean $\mathbf m_j$, direction $\hat{\mathbf u}_j=\mathbf m_j/|\mathbf m_j|$.
  A block is a **candidate** iff all its samples are valid, not `sat_acc`/`sat_gyr`, and
  $|\boldsymbol\omega^{A3}_k| < 3$ °/s for every sample (A3 baseline gyro $1.03(\mathbf w-\mathbf b)$; the gyro is auxiliary).
- Windows are grown greedily, left to right, inside each run of consecutive candidate blocks: a window [s, e) of blocks
  is extended by block e while, with $\bar{\mathbf m}=\frac1{e-s+1}\sum_{j=s}^{e}\mathbf m_j$,
  $$\max_{s\le j\le e}\angle(\hat{\mathbf u}_j,\bar{\mathbf m})<0.3^\circ \quad\text{and}\quad \big|\,|\bar{\mathbf m}|-g\,\big|<0.03\,g .$$
  When block e would violate either condition the window is closed at e and a new one starts at e (a block that fails
  the magnitude condition on its own is skipped). Windows of ≥ 1.0 s (10 blocks) are kept (**gate variant**); the
  **2.0-s variant** keeps only windows ≥ 2.0 s (shorter ones then become part of the bout between).
- Window gravity $\hat{\mathbf g}_W$ = normalised mean of $\mathbf a$ over the window; centre $c_W=\lfloor(s_W+e_W)/2\rfloor$ (samples).
- **Text:** a stretch in which the measured gravity direction does not move by more than 0.3° from its mean at 0.1-s
  resolution — a slowly rotating head (constant |a|) is rejected, which the Phase-0 |a|-based rule could not do. A
  rotation of rate r keeps a window ≤ 0.6°/r seconds long, so ≥ 1-s windows bound the in-window rotation to ≈ 0.6°.

### 2.2 WISER support (filter only where available)
- Span = [window start − 2 s, window end + 2 s]; fixes of the animal's tag from A2 with `valid` and none of
  `m_handling`, `m_silence`, `m_tag_validity`, `m_adc_lane`; 1-s bins (Unix-second floor); per bin with ≥ 1 fix the
  median position $\mathbf p_k$ (in); $\tilde{\mathbf p}$ = coordinate-wise median of the $\mathbf p_k$.
- **available** iff ≥ 3 bins have fixes and ≥ 50 % of the span's whole seconds have ≥ 1 fix; **confirmed** iff
  available and $\max_k|\mathbf p_k-\tilde{\mathbf p}|\le 6$ in; **contradicted** iff available and not confirmed;
  otherwise **unavailable**.
- **Filter:** contradicted windows are dropped from every analysis below; confirmed and unavailable windows are kept.
  The IMU↔WISER lag τ* (0.1–0.2 s) is ignored at 1-s resolution; the WISER frame (inches, unverified origin) is used only
  for distances. **Text:** WISER can veto a window in which the tag (on the headstage) moved by more than 6 in; it
  cannot see head rotation. Counts confirmed / contradicted / unavailable are reported per animal and period, and the
  gate is also reported without the filter (information only).

### 2.3 Measurement floor
For filtered strict windows of duration D ≥ 4 s with midpoint m:
$\varphi_L=\angle(\bar{\mathbf a}_{[m-L,m)},\bar{\mathbf a}_{[m,m+L)})$ for L = 1.0 and 2.0 s (adjacent L-s pieces at the split);
$\varphi_{half}$ = angle between the means of the two halves; $\varphi_{half,prop}$ = the same after propagating the first
half's gravity from its centre to the second half's centre with the calibrated gyro (the zero-activity version of the
bout test). **The gate floor is the pooled test median of $\varphi_{1.0}$** (the gate's shortest allowed window); all
four are reported (median, p90) per animal and period type. Cross-orientation accelerometer-calibration residuals
(≈ 0.1°) are not in the floor (lower bound).

### 2.4 Bouts and the centre-to-centre test
- Consecutive filtered strict windows $W_i, W_{i+1}$ (same period, same variant) whose span $[c_i, c_{i+1})$ contains only
  valid samples (saturation allowed). **Inner duration** $T_{in}=(s_{i+1}-e_i)\Delta t$ (used for binning),
  centre-to-centre duration $T_{cc}=(c_{i+1}-c_i)\Delta t$ (reported). **Active bout** iff $[e_i, s_{i+1})$ contains at
  least one A3 non-`quiet` sample (the Phase-0 activity definition); gaps without one are reported as quasi-still gaps.
  Bins on $T_{in}$: 2–5, 5–15, 15–40, 40–90 s (Phase-0 `pd.cut` convention); $T_{in}$ > 90 s excluded.
- Propagation: $\mathbf g_{c_i}=\hat{\mathbf g}_{W_i}$, $\mathbf g_{k+1}=\mathrm{Exp}(-\boldsymbol\omega_k\Delta t)\,\mathbf g_k$
  for $k=c_i,\dots,c_{i+1}-1$ (Phase-0 Rodrigues kernel); **tilt error** $e=\angle(\mathbf g_{c_{i+1}},\hat{\mathbf g}_{W_{i+1}})$ (°).
  **Text:** the window-mean gravity belongs to the window centre, so propagating from centre to centre leaves no
  unpropagated motion at either edge.
- Per bout also: $e_{edge}$ (Phase-0 style on the same bout: $\hat{\mathbf g}_{W_i}$ placed at $e_i$, propagated over
  $[e_i,s_{i+1})$ only — diagnostic of the edge effect), $t_{act}$ = Δt·#non-quiet samples in $[c_i,c_{i+1})$,
  $\Theta=\sum|\boldsymbol\omega_k|\Delta t$ (°), in-window rotation over $[c_i,e_i)\cup[s_{i+1},c_{i+1})$, raw gyro
  saturation in $[12.5c_i,12.5c_{i+1})$ (+ Phase-0 run classes), WISER status of both windows.
- **Saturated bouts** (any raw gyro lane |raw| ≥ 32700 inside the span) are reported separately with the Phase-0
  reconstruction (treatment ii); gate bouts have none.

### 2.5 Model choice — tuning periods only, frozen before the test periods are loaded
- Fit set: tuning-night + tuning-day active, no-saturation bouts with 2 ≤ $T_{in}$ ≤ 15 s (gate variant), per animal.
- Models (Phase 0, registered set): `scalar`, `diag`, `M`, `M_rate`; reference 1.03 baseline. Phase-0 Huber objective
  ($f$ = 3°) on the error vectors $\mathbf g_{c_{i+1}}-\hat{\mathbf g}_{W_{i+1}}$, same bounds/starts.
- 2-fold CV, folds = alternating 10-min blocks of bout start time (seconds since the period's analysis-window start,
  per period); an animal contributes held-out errors only if each training fold has ≥ 20 bouts; selection = lowest
  pooled held-out median; a model within 0.05° with fewer parameters wins. The selected model refitted on all tuning
  bouts per animal (+ 200-draw bootstrap CIs) is written to `selection.json` and the config **before** any test period is
  read. The Phase-0 exploratory g-sensitivity models are not refitted.

### 2.6 GATE (thresholds unchanged from Phase 0)
Test night + test day pooled, active strict no-saturation bouts (gate variant, WISER-filtered), selected model, median
centre-to-centre tilt error: **2–5 s ≤ 1.0° AND 5–15 s ≤ 2.0°, pooled AND in ≥ 4 of 5 animals individually** (an
animal without bouts in a bin fails it). **Floor clause:** if a bin fails but its pooled median exceeds the floor
($\varphi_{1.0}$, pooled test median) by < 0.5°, the report says the test is at its limit. Verdict PASS / FAIL; 1000-draw
bootstrap CIs for information. Also reported (information only, never the verdict): night-only, day-only (posture
shifts during sleep), without the WISER filter, the 2.0-s variant, $e_{edge}$, the 1.03 baseline and all four models.

### 2.7 Is the drift linear? Chained-anchor test
- **Anchors:** filtered strict windows (gate variant), thinned chronologically so successive anchor centres are ≥ 30 s
  apart, in all four periods.
- **Chain:** from $c_A$, quaternion $q$ (head → world estimate) with $q_0$ = tilt from $\hat{\mathbf g}_A$, yaw 0;
  $q_{k+1}=q_k\otimes\mathrm{Exp}(\boldsymbol\omega_k\Delta t)$ with the frozen per-animal model, **no aiding, no reset**.
  The chain ends at the first of: $c_A$ + 600 s, an invalid sample, the period end, or (primary) the first raw gyro
  saturated sample; a secondary variant continues through reconstructed saturation.
- **Records:** at every later filtered strict window j with $c_j$ inside the chain: $t=(c_j-c_A)\Delta t$;
  $t_{act}$ = Δt·#non-quiet samples in $[c_A,c_j)$; $t_{still}=t-t_{act}$; $\Theta$ (°) over the chain so far; the tilt-error
  vector $\boldsymbol\phi_j$ = rotation vector of the smallest rotation taking $\mathbf e_z$ to $\mathbf u_j=R(q_{c_j})\hat{\mathbf g}_{W_j}$
  (horizontal, in the anchor-initialised world frame = a fixed rotation of the anchor's head frame), $e_j=|\boldsymbol\phi_j|$ (°).
- **Models** for the per-axis variance $\sigma_\theta^2$ of $\boldsymbol\phi$ (so $e$ is Rayleigh with scale $\sigma_\theta$,
  $E[e^2]=2\sigma_\theta^2$):
  `L_t` $\sigma_0^2+(bt)^2$ (constant bias → linear); `RW_t` $\sigma_0^2+qt$ (random walk → √t); `R` $\sigma_0^2+(c\Theta)^2$;
  `LR_t` $\sigma_0^2+(bt)^2+(c\Theta)^2$; `L_a`, `RW_a`, `LR_a` = the same with $t_{act}$. Exploratory (labelled):
  `RWR` $\sigma_0^2+q_\Theta\Theta$, `RW_t+R`.
  Fit by maximum likelihood ($\ell=\sum\ln(e/\sigma^2)-e^2/2\sigma^2$) on **tuning** records (animals pooled; per-animal
  fits reported); compared by the **held-out test** log-likelihood per record and by tuning AIC; 95 % CIs of test ΔLL by
  a 1000-draw block bootstrap (blocks = 10-min anchor-time blocks per animal-period).
- **Direction consistency:** per chain with ≥ 3 increments between records ≥ 30 s apart, $C_{inc}=|\sum\Delta\boldsymbol\phi|/\sum|\Delta\boldsymbol\phi|$
  against a null with the increment directions randomised (200 draws, magnitudes kept): linear bias → $C_{inc}$ near 1,
  random walk → at the null. The cumulative-vector resultant length is reported with the caveat that a random walk is
  also persistent in its cumulative direction.
- **Gyro bias residual during long still periods:** filtered strict windows ≥ 10 s:
  $\mathbf r=\overline{\boldsymbol\omega}$ over the window with the A3 bias (in-sample) and with a leave-window-out bias
  (running median ± 300 s of the quiet-second medians excluding the window's seconds); tilt component
  $|\mathbf r-(\mathbf r\cdot\hat{\mathbf g})\hat{\mathbf g}|$ and yaw component $\mathbf r\cdot\hat{\mathbf g}$ in °/min (median, p90).
- **Verdict rule (stated now):** "linear in time (bias-like)" iff the best registered model by test LL contains the
  $(bt)^2$ term (`L_t`/`LR_t`, or `L_a`/`LR_a` for active time) **and** beats its random-walk counterpart with the ΔLL CI
  excluding 0 **and** the median $C_{inc}$ exceeds the median null; "random-walk-like" iff the RW counterpart wins with the
  CI excluding 0; "rotation-driven" iff the best model is `R`, or `LR_*` with the $c\Theta$ term carrying > 50 % of the
  modelled variance at the median test record; otherwise "not resolved". The same fits on day-only and night-only
  records (still-dominated vs active regime) are reported and the statement names the regime.

### 2.8 Corrected growth law
Phase-0 method (`fit_growth`: bin edges 0, 2, 3, 4, 5, 7, 10, 15, 22, 30, 45, 60, 90 s; ≥ 15 bouts per bin; weights √n;
median = 1.1774 σ) on the **test** active no-saturation bouts with $t=t_{act}$ and the floor ($\varphi_{1.0}$ median and p90) at
t = 0 → $\sigma_\theta(t_{act})=\sqrt{\sigma_0^2+(kt_{act})^2}$ (median) and the p90 envelope, compared with Phase 0's
$\sqrt{0.82^2+(0.193t)^2}$ (p90 $\sqrt{6.61^2+(0.477t)^2}$); also vs $T_{in}$, and the chain-record law vs $t_{act}$ (edges
extended to 120, 180, 300, 600 s) as the law for a filter aided only at strict still windows.

### 2.9 Suggested human video checks (listed, never judged by the agent)
20 strict still windows (2 per animal × period type, ≥ 3 s, seeded random, WISER confirmed or unavailable), 20 shake
trains (Phase-0 class `shake_train`, seeded random) and the 10 largest-error test bouts, each with field-PC local times,
the WISER position, and for CH01–CH08 the hourly segment on `F:\3rd_rat\<date>\<CH>\` containing the time with the offset
from the file name's start (file names are field-PC time; never the burned-in OSD).

## 3. Self-test (`--selftest`, synthetic, no field data)
1. The strict detector rejects a head rotating at 2 °/s about a horizontal axis at constant |a| (gyro below 3 °/s; the
   Phase-0 quasi-static rule accepts it) and returns one window over a truly still segment with sensor noise.
2. Centre-to-centre propagation removes a known edge bias: with rotation inside both edge windows and a perfect gyro,
   the edge-style error equals the planted in-window rotation and the centre-to-centre error is at the noise level.
3. The chained-anchor fit recovers a planted constant gyro bias (`L_t` wins, b within 25 %, high $C_{inc}$) versus a
   planted angle random walk (`RW_t` wins, q within 35 %, $C_{inc}$ at the null).
4. WISER support classes on synthetic fixes (confirmed / contradicted / unavailable).

## 4. Order of work
0. This plan + top row in `implementation_plan/README.md`.
1. Script + config + `--selftest`.
2. `--build-day-caches` (both days; extraction only — no test-period result is computed).
3. Development on the tuning periods only (`--roles tuning`): detector counts, WISER agreement, floor, bout counts,
   model CV. Any rule change is appended below as an amendment before step 4.
4. One full run (tuning → frozen selection → test → gate, linearity, growth law, figures, report).
5. Change log, index rows, CLAUDE.md `wiser_baseline` row.

## Amendments (before the full run)

1. **Linearity verdict rule made two-part (2026-10-01, from the synthetic self-test, before any real-data run).** The
   first self-test planted bursts at regular 20-s intervals, so rotation Θ and active time were proportional to clock
   time; `R` then tied `L_t` and the §2.7 rule ("best model is R → rotation-driven") called a planted constant bias
   "rotation-driven". The rule now makes two statements, each requiring a CI-separated held-out contrast:
   **shape** — linear vs random walk, from `L_t − RW_t` (clock time) and `L_a − RW_a` (active time);
   **driver** — among the linear-shape models `L_t` (clock time: a bias that also acts while still), `L_a` (active time)
   and `R` (rotation), a driver is named only if it beats both others with the 95 % block-bootstrap CI excluding 0,
   otherwise "not separable". Headline: **LINEAR IN TIME (bias-like)** iff shape linear in clock time AND driver = clock
   time AND median $C_{inc}$ > median null; **RANDOM-WALK-LIKE** iff an RW model beats its linear counterpart (CI
   excluding 0) and the other contrast does not favour linear; **LINEAR, driven by rotation / active time** iff that
   driver is named and a linear shape wins; otherwise **NOT RESOLVED**. The self-test synthetic now draws bursts in a
   random half of the slots with random amplitude (10–60 °/s), and checks both verdicts (bias → LINEAR IN TIME,
   random walk → RANDOM-WALK-LIKE). The `rot_share` of the `LR_*` fits is still reported.
2. **Descriptive and exploratory additions after the tuning-only development pass (2026-10-01 08:42, before the full
   run; no test period had been read; no rule, threshold or model choice changed).** The development pass ran the
   whole pipeline on the two tuning periods only (gate procedure applied to tuning bouts: 2–5 s 0.26°, 5–15 s 0.43°; floor
   $\varphi_{1.0}$ 0.026°; tuning CV selected `scalar` by the tie rule; still-window gyro residual ≈ 1.4 °/min tilt;
   chain increments strongly direction-consistent, $C_{inc}$ 0.86 vs null 0.31; WISER contradicted 7–37 % of the windows).
   Added, all labelled descriptive/exploratory in the report and never part of the gate or the verdict rule:
   (a) **net in-window rotation** $|\sum\boldsymbol\omega\Delta t|$ over the two half-windows next to the integrated |ω|
   (the latter carries the gyro-noise floor of |ω|); (b) the **floor split by WISER status** (all windows ≥ 4 s incl.
   contradicted) to show whether a WISER contradiction is real motion or jitter; (c) a **rotation-matched comparison**
   with Phase 0's test-night no-saturation bouts (median error per Θ bin), because bouts between strict windows are far
   less vigorous than Phase 0's; (d) **anchor-ZARU chains**: on identical anchors (kept windows ≥ 10 s, thinned ≥ 30 s),
   chains with the standard A3 bias vs chains with the anchor window's own mean calibrated gyro subtracted for the whole
   chain (a zero-rate bias update), compared per t-bin and with the same model fits — does re-estimating the bias at a
   still window remove the drift?
