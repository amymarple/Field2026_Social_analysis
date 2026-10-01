# Head-IMU inertial fusion with WISER, V5: attitude outside the position filter (Stage A) + a 16-Hz EKF/RTS position filter (Stage B) (cohort 2026c)

- **Status:** approved by the user 2026-10-01 ("start v5"); written **before** any computation on the test periods
  (night 2026-09-10/11, day 2026-09-11). Every rule that turns data into a choice is fixed here. Development runs touch
  the **tuning periods only** (night 2026-09-08/09, day 2026-09-08). The verdict is evaluated once, on the test periods.
  Amendments, if any, are appended below (§11) *before* the full run and listed as deviations in the report.
- **Why:** V4 (6-axis ESKF + RTS) FAILED (−7.7 % / −14.8 % vs B2′). The audit
  ([change log](../change_log/2026-09-29-wiser-ins-fusion.md), final section) traced it to: attitude estimated inside
  the position filter with a dynamic gravity update that pulls tilt toward the specific force during motion; tilt resets;
  gyro scale 1.03 (gate v2: 0.95–1.00); gyro bias from 10-min blocks / a running median (gate v2: the residual drift is
  linear in clock time, ≈ 1.6–2.1 °/min, consistent in direction → re-estimate the bias at every strict still window);
  full-band acceleration integrated (90 % of the head's horizontal-acceleration variance is above 2 Hz = behaviour, not
  body displacement); tuning on the pooled median → overconfident (NIS 13–19); WISER white noise split with σ_b = 2.5 in
  above the measured static SD at 8–9 anchors; evaluation only on 1–2-s bridging. The attitude gate v2 PASSED
  (0.30° / 0.62°) and gave the clock-time error law; this plan is the corrected fusion it licensed.
- **Follows:** [`change_log/2026-10-01-imu-attitude-gate-v2.md`](../change_log/2026-10-01-imu-attitude-gate-v2.md)
  (report `results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_gate_v2_2026c.md`, bulk
  `D:\Field2026_analysis_out\2026c\imu_attitude_gate_v2_20261001_0847\`: `selection.json`, `fits.json`).
  Reused **by import, never edited:** `analyze_wiser_imu_smoothing.py` (Track, hidden sets, B1/B2/B2′/V1/V2 predictions,
  `boot_delta`, `track_metrics`, `kf_run`), `analyze_wiser_ins_fusion.py` (context, per-second IMU tables via the make_imu
  npz), `analyze_imu_attitude_phase0.py` (quaternion kernels, `propagate_bouts`, `q_from_up`), `analyze_imu_attitude_gate_v2.py`
  (`process_period` = A1/A3 loading + Phase-0 gyro chain with held-reading reconstruction + strict still windows,
  `make_bouts`), `build_imu_wiser_cache.py`, `analyze_imu_wiser_calibration.py`.
- **Scope:** a measurement question (direction `wiser_baseline`): can the head IMU, processed correctly, predict held-out
  WISER fixes better than the best position-only / motion-state smoothers? No behavioural claim.
- **Rules (user):** never open or judge images; raw drives read-only — **caches only** (A1 `imu_raw_cache`, A3
  `imu100_cache` incl. the `day_` files, A4 `imu16_cache`, A2 `wiser_fix_cache` under `D:\Field2026_analysis_out\2026c\`),
  no raw re-read; SQLite `mode=ro` (not needed: A2 holds the fixes); existing scripts are not edited; no git commit; the
  index files and CLAUDE.md are re-read right before editing and only this analysis's rows are changed; tune only on
  tuning data; report honestly; numba for loops; runtime target ≤ 2 h.
- **Code (new):** `wiser/scripts/analyze_wiser_ins_fusion_v5.py` (`--cohort 2026c`, `--roles tuning` for development,
  `--stage-a-only`, `--report-only <run_dir>`, `--selftest`). **Config (new):** `wiser/configs/wiser_ins_fusion_v5_2026c.json`
  (periods, every rule and grid below; the run writes the `tuned` block, marked as fitted on the tuning periods only).
- **Outputs:** bulk `D:\Field2026_analysis_out\2026c\wiser_ins_fusion_v5_<ts>\` (Stage-A validation tables, measured WISER
  noise model, ψ-regression tables, tuning grids, filter states/covariances per animal-period, per-fix predictions,
  innovations and held-out errors of every method, bootstrap tables, `summary.json`, `input_provenance.json`, `log.txt`);
  a reusable Stage-A cache **`D:\Field2026_analysis_out\2026c\attitude16_cache\<SFxx>\<period>.npz`** + `README.md`;
  report `results/2026c/wiser_baseline/reports/wiser_baseline_ins_fusion_v5_2026c.md` + figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_ins_fusion_v5_*_2026c.png`, pointer
  `run_manifest_ins_fusion_v5_2026c.json` (the folder's `run_manifest.json` is never touched);
  `change_log/2026-10-01-wiser-ins-fusion-v5.md` + top rows in both index READMEs; only the `wiser_baseline` row of
  CLAUDE.md's WISER table.

## 1. Data

| period | role | analysis window (field-PC local, EDT) | IMU source | WISER source |
|---|---|---|---|---|
| `night_20260908` | tuning | 2026-09-08 21:00:00 → 2026-09-09 04:20:00 | A1 + A3 night caches | A2 `night_20260908` |
| `day_20260908` | tuning | 2026-09-08 08:00:00 → 2026-09-08 18:30:00 | A1 + A3-equivalent day caches | A2 `day_20260908` |
| `night_20260910` | **test (primary)** | 2026-09-10 21:00:00 → 2026-09-11 04:20:00 | A1 + A3 night caches | A2 `night_20260910` |
| `day_20260911` | test (secondary) | 2026-09-11 10:00:00 → 2026-09-11 17:30:00 | A1 + A3-equivalent day caches | A2 `day_20260911` |

Animals SF07, SF08, SF09, SF10, SF12 (sessions as in `imu_attitude_gate_v2_2026c.json` / `wiser_imu_smoothing_2026c.json`).
τ* (WISER later than the IMU) per animal from the calibration pilot: SF07 0.20, SF08 0.15, SF09 0.10, SF10 0.20, SF12 0.15 s;
a fix at field-PC time t is placed at t − τ*. Masks: the pilot's per-second IMU QC (nodata, saturated, frozen, invalid, NaN,
unreliable, handling, silences ± 2 min, tag validity, each logger's own ADC-lane windows). Regime context carried from
the gate-v2 report §3: construction near the paddock from 09-08 ~07:50 (the tuning day is disturbed); SF08/SF12 test-night
IMU starts 21:02:45 / 21:05:18; no handling round or ADC window inside any analysis window; the 09-11 19:40 female release
is after every window. WISER frame: inches, **unverified offset frame**; nothing here is placed in the physical field.

**Per-second IMU tables.** Nights: the smoothing pilot's tables from the make_imu npz (identical scored sets, so (a)/(a′)
reproduce the pilot). Days: SF12's 09-11 session has no make_imu npz (field-flagged), so for **all five animals on both
days** a cache-equivalent table is built from the A3-equivalent day caches with the pilot's rules: VeDBA = |a − 2-s running
mean| (100 Hz, averaged per second), |ω| = |A3 gyr| per second, still = ok ∧ VeDBA_1s < θ_still(animal) ∧ |ω|_1s < 10 °/s
(θ_still from `ephys/imu_lfp_state_check.py`), SBF from Stage A's world-frame vertical acceleration (pair-averaged to
50 Hz), ok = no A3 saturation / frozen / missing sample in the second ∧ not handling / silence / tag-validity / ADC.
Declared deviation for the days only.

## 2. Stage A — attitude outside the position filter (IMU only, no WISER)

Per animal-period over the **whole cached window** (nights 20:50 → 05:30 so the +1 h control is served; days as cached):

1. **Load** with gate v2's `process_period` (A1 raw counts → Hampel → saturation classes + held-reading reconstruction →
   40-Hz Butterworth-4 zero-phase → 100 Hz → head frame; A3 calibrated accelerometer; validity = not frozen / handling /
   past `imu_valid_until`). Pre-bias gyro $\mathbf w_k$ (°/s) = reconstructed stream before any bias subtraction.
2. **Strict still windows** = gate v2's definition (0.1-s blocks, every block's acc direction within 0.3° of the window
   mean, $\big||\bar{\mathbf a}|-g\big|<0.03g$, every sample $|\boldsymbol\omega^{A3}|<3$ °/s, ≥ 1.0 s), **without the WISER
   veto** — Stage A uses no WISER information, so no held-out fix can leak into it (gate v2's `no_wiser_filter` variant
   passes the gate too: 0.31° / 0.64°).
3. **Gyro scale:** per-animal scalar from gate v2 `selection.json` (SF07 0.962, SF08 0.951, SF09 0.995, SF10 1.001, SF12 1.000).
4. **Gyro bias = piecewise-linear function of clock time anchored at every strict window.** Per window $i$ (centre $c_i$,
   duration $d_i$): ZARU estimate $\hat{\mathbf b}_i=\overline{\mathbf w}_{W_i}$. Anchor values $\tilde{\mathbf b}_i$; linear
   interpolation between centres; flat extrapolation before the first / after the last window. Two anchor rules:
   **(raw)** $\tilde{\mathbf b}_i=\hat{\mathbf b}_i$; **(smoothed)** per head axis a 1-D random-walk Kalman/RTS smoother over the
   window sequence, $b_{i+1}=b_i+\eta_i$, $\mathrm{Var}(\eta_i)=q_b(c_{i+1}-c_i)$, $\hat b_i=b_i+\epsilon_i$,
   $\mathrm{Var}(\epsilon_i)=\sigma_r^2/d_i^2+\sigma_w^2/d_i$ ($\sigma_r$ = residual head micro-rotation allowed by the 0.3°
   tolerance, $\sigma_w$ = gyro white noise), $(q_b,\sigma_r,\sigma_w)$ per head axis fitted by maximum innovation likelihood
   on the tuning periods' windows (animals pooled). Reason (tuning data, SF09): ZARU estimates of adjacent windows < 2 s
   apart differ by a median 0.06–0.11 °/s for 1–1.5-s windows but 0.01 °/s for ≥ 10-s windows — single 1-s ZARUs carry
   more noise than the 0.025 °/s residual bias they should correct. **Choice (tuning only):** the rule with the lower
   pooled tuning leave-window-out median tilt error (step 8); a tie (≤ 0.02°) → smoothed.
5. **Attitude at 100 Hz, gravity aiding only inside strict windows.** $\boldsymbol\omega_k=s_a(\mathbf w_k-\mathbf b(t_k))$.
   At the first window centre the tilt is set from the window gravity $\hat{\mathbf g}_{W}$ (yaw 0); backward integration
   before it. Between consecutive window centres $c_i\to c_{i+1}$: forward quaternion integration $q^f$ from $q(c_i)$; at
   $c_{i+1}$ the **closure** $\boldsymbol\delta_{i+1}$ = the world-frame rotation (horizontal axis) taking
   $R(q^f_{c_{i+1}})\hat{\mathbf g}_{W_{i+1}}$ to $\mathbf e_z$; the attitude over the segment is
   $q_k=\mathrm{Exp}(\alpha_k\boldsymbol\delta_{i+1})\otimes q^f_k$, $\alpha_k=(k-c_i)/(c_{i+1}-c_i)$ — the closure error is
   distributed linearly in clock time (the gate-v2 drift law), the tilt at every window centre equals the window's measured
   gravity, the yaw stays continuous (arbitrary origin). No gravity pull outside strict windows, no tilt resets. Invalid
   samples hold the attitude. $|\boldsymbol\delta_{i+1}|$ = the centre-to-centre tilt error of that segment (diagnostic).
6. **Outputs at 16 Hz:** $\mathbf f_w=R(q)\mathbf a-g\mathbf e_z$ (100 Hz, world frame) → zero-phase Butterworth-4 low-pass
   **2 Hz** → `resample_poly(4, 25)` → 16 Hz: `f_xy_2hz` (yaw arbitrary, continuous), `f_z_2hz`; `q_wh`; `t_since_win_s`
   = seconds since the end of the last strict window (0 inside one; before the first window: seconds to its start);
   **σθ (median law, gate v2, real time):** $\sigma_\theta(t)=\sqrt{0.78^2+(0.0227\,t)^2}$° with $t$ = `t_since_win_s`;
   **p90 law** $\sqrt{3.07^2+(0.0921\,t)^2}$° (sensitivity run); flags `ok` (all 100-Hz samples of the support valid and
   ≥ 0.5 s from an invalid sample), `in_window`, `sat`, `shake` (Phase-0 shake-train span), band powers of |ω| and |a|
   (2–4, 4–8, 8–12, 12–20 Hz; A4 definition), VeDBA. Written as **`attitude16_cache`** (+ README, window table with the raw
   and anchor biases and closures, calibration and provenance in `calib_json`/`meta_json`).
7. **Validation A1 (gate-v2 bout test):** on gate v2's bout set (`make_bouts`, variant L1.0 = WISER-filtered windows,
   active, no saturation; 2–5 s and 5–15 s bins), centre-to-centre tilt error with (i) gate v2's stream (A3 running-median
   bias, scalar) — must reproduce 0.30° / 0.62° on the test periods — and (ii) Stage A's anchored bias; also both on the
   L1.0_nf set (gate v2: 0.31° / 0.64°). Reported, no gate.
8. **Validation A2 (leave-window-out):** Stage A rerun with every odd-numbered window withheld from both the bias anchors
   and the closures; at each withheld window the tilt error $e=\angle(R(q_{c})\hat{\mathbf g}_{W},\mathbf e_z)$, binned by
   the time since the end of the last kept window (and by the distance to the nearest kept window), compared with the
   σθ law (median angle $=1.1774\,\sigma_\theta$). Tuning periods: chooses the bias rule (step 4); test periods: reported.

## 3. Stage B — position filter (EKF + RTS on the 16-Hz IMU grid, WISER at the fix times)

**State** (9): $\mathbf p$ (2, in), $\mathbf v$ (2, in/s), $\mathbf b$ (2, world-frame horizontal acceleration bias, in/s²),
$\psi$ (yaw offset between the Stage-A frame and the WISER frame, rad), $\mathbf d$ (2, WISER slow drift, in — only if the
measured variogram justifies it, §3.3). Nodes = all fixes of the animal-period (visible and hidden), at $t-\tau^*$; between
nodes the state is propagated through the 16-Hz IMU samples (piecewise constant per 16-Hz interval, partial intervals
at the ends).

### 3.1 Propagation
- **INS mode** (16-Hz sample `ok` and `t_since_win_s` ≤ $T_{max}$): $\mathbf u=R(\psi)\mathbf f_{xy}-\mathbf b$,
  $\mathbf p\leftarrow\mathbf p+\mathbf v\,\delta+\tfrac12\mathbf u\,\delta^2$, $\mathbf v\leftarrow\mathbf v+\mathbf u\,\delta$;
  white residual acceleration with per-axis PSD $\sigma_{res}^2\Delta_{16}$ ($\Delta_{16}$ = 1/16 s;
  $Q_{pp}=S\delta^3/3$, $Q_{pv}=S\delta^2/2$, $Q_{vv}=S\delta$).
- **The specified acceleration error variance $(g\,\sigma_\theta(t))^2+\sigma_{res}^2$ is implemented as two parts:** the tilt
  leakage $g\sin\sigma_\theta(t)$ is slowly varying (bias-like, gate v2) and is carried by the Gauss–Markov state
  $\mathbf b_{k+1}=e^{-\delta/\tau_b}\mathbf b_k+\boldsymbol\eta$, $\mathrm{Var}(\boldsymbol\eta)=(g\sin\sigma_\theta(t))^2(1-e^{-2\delta/\tau_b})$
  (stationary SD = the tilt leakage); $\sigma_{res}^2$ is the white part. (A white term of $(g\sigma_\theta)^2$ would
  understate a persistent tilt error by the number of 16-Hz steps it lasts.)
- **CV mode** (IMU not usable or too long since a strict window, $t_{since}>T_{max}$): $\mathbf u=0$ and the white
  acceleration PSD is V2's, $q\,m_{c}$ with $q$ = 1 in²/s³ and $m$ = (1.0, 0.01, 0.3, 10) for the pilot's per-second IMU
  state $c$ (unusable / still / active / locomoting) — so where the IMU carries no inertial information V5 reverts to a
  V2-like smoother instead of following WISER noise (with σθ growing to tens of degrees over minutes without a strict
  window, an INS-only model would have huge process noise there; V4 had no such fallback).
- $\psi$: random walk, $q_\psi=(0.0227\ ^\circ/\mathrm s)^2\times 60\ \mathrm s$ = 0.0309 deg²/s (the gate-v2 clock-time rate
  matched over 1 min). $\mathbf d$: AR(1) with the measured $(\sigma_d, T_d)$.
- EKF Jacobians at the forward estimate ($\partial\mathbf u/\partial\psi=J R(\psi)\mathbf f_{xy}$, $J$ = 90° rotation).

### 3.2 Updates
- **WISER** $\mathbf z=\mathbf p+\mathbf d+\boldsymbol\varepsilon$, $\boldsymbol\varepsilon\sim\mathcal N(0,\mathrm{diag}\,\sigma^2_{w,x}(A),\sigma^2_{w,y}(A))$
  with the measured per-anchor variances (§3.3). Pass 0: soft χ² gate ($d^2>13.82$ → R inflated by $d^2/13.82$); passes
  1–2: Huber IRLS ($k=2.5$) on the 2-D Mahalanobis smoothed residual — the smoothing pilot's B2 rules.
- **Soft ZUPT** $0=\mathbf v+\boldsymbol\epsilon$ at nodes in an **IMU-still** second (the pilot's still rule, σ_v) and at nodes
  in a **rhythmic body-stationary** 16-Hz sample (σ_vr): ok ∧ not still ∧ pilot state ≠ locomoting ∧ [Phase-0 shake-train
  span ∨ ($B_{hi}\ge B_{lo}$ ∧ $B_{hi}+B_{lo}\ge(20\ ^\circ/\mathrm s)^2$)], $B_{hi}$ = |ω| band power 8–12 + 12–20 Hz,
  $B_{lo}$ = 2–4 + 4–8 Hz (shakes 12–20 Hz, scratching / grooming strokes put |ω| power above 8 Hz — the norm doubles a
  4–7-Hz oscillation; literature: grooming, scratching and shaking keep the body stationary). The rule is fixed a priori;
  how much it is trusted is σ_vr (tuned; ∞ = off).
- **ψ (re-)acquisition** (§3.4): a pseudo-measurement $\psi^{obs}$ at a node only when $P_{\psi\psi}>(20^\circ)^2$ and a local
  estimate with SD ≤ 10° exists (wrapped innovation, variance max(SD², (5°)²)).

### 3.3 WISER noise model (measured on the tuning periods, per period kind night / day; never tuned)
- Still runs = maximal runs of pilot-still seconds ≥ 20 s; valid unmasked fixes inside (aligned time).
- **White (nugget) variance per anchors_used** $A$ (≤ 3 pooled, 3…9), per axis: $\sigma^2_{w}(A)=\tfrac12(1.4826\,\mathrm{MAD}(\Delta))^2$
  over consecutive fixes of one run with both anchors $=A$ and spacing ≤ 0.5 s, minus the drift's share at that lag;
  strata with < 50 pairs take the next-lower anchor count's value (conservative).
- **Variogram** of 9-anchor fixes (robust, lag bins 0.25, 0.5, 1, 2, 5, 10, 20, 30 s), fit
  $\gamma(\tau)=n+\sigma_d^2(1-e^{-\tau/T_d})$ per axis with a common $T_d$. **The drift state is kept iff** $\sigma_d^2\ge
  0.10\,(n+\sigma_d^2)$ in at least one axis and $1\le T_d\le120$ s; otherwise no drift state and $\sigma^2_w(A)$ is the
  pilot-style robust total variance about the run median.

### 3.4 Yaw offset ψ — initialised by regression (not multi-hypothesis)
From the **visible** fixes of the run only: B2 (q = 3, no drift) smoothed velocities at visible fixes; pairs $(i,j)$ with
$t_j-t_i\in[0.4,0.75]$ s, IMU `ok` throughout, $|\Delta\mathbf v_I|\ge 8$ in/s where $\Delta\mathbf v_I=\int_{t_i}^{t_j}\mathbf f_{xy}dt$
and $\Delta\mathbf v_W=\mathbf v_j-\mathbf v_i$. Complex form: $c=\Delta v_W\,\overline{\Delta v_I}$ (normal) or
$\Delta v_W\,\Delta v_I$ (mirrored WISER y). Local estimate $\hat\psi(t)=\arg\sum_{|t_{ij}-t|\le150\,\mathrm s}c$,
resultant $\bar R=|\sum c|/\sum|c|$, SD $=\sqrt{-2\ln\bar R/n}$ (bounded 3°–90°). $\psi_0$ = the first local estimate
(else the whole-period estimate), $P_{\psi,0}=\max(\mathrm{SD}^2,(10^\circ)^2)$. **Handedness** fixed on the tuning periods:
normal iff $\bar R_{normal}>\bar R_{mirrored}$ (whole period) in ≥ 6 of 10 tuning animal-periods; the test-period
log-likelihood ratio normal − mirrored (forward pass 0, visible fixes, both frames run with their own regression) is
reported as a secondary result.

### 3.5 Prediction and initialisation
Held-out prediction $\hat{\mathbf z}_h=\mathbf p^s_h+\mathbf d^s_h$ (RTS-smoothed after the last IRLS pass), predictive
variance $P^s_{(p+d)}+R(A)$. Initial state at the first node: $\mathbf p$ = first visible fix ($10^4$ in²), $\mathbf v=0$
(400), $\mathbf b=0$ ($(g\sin\sigma_\theta)^2$), $\psi_0$, $\mathbf d=0$ ($\sigma_d^2$).

## 4. Held-out schemes and scored set

Per animal-period, independent seeds (pilot seed 20260929 + offsets stored in the config):
- **(s) single-fix:** every 5th fix hidden alone (offset drawn per animal) → 20 %, horizon 0.13–0.26 s.
- **(g-0.5 s), (g-1.0 s):** all fixes in a random 10 % of 0.5-s / 1.0-s windows (the pilot's `hide_windows`, own seeds).
- **(a), (a′):** exactly the smoothing pilot's (`make_hidden`; test night seed + 1000 + i, tuning night seed + i →
  identical hidden fixes and scores as the pilot); days: seed + 2000 + i (tuning day), seed + 3000 + i (test day).
- **Scored fix:** hidden ∧ anchors ≥ 7 ∧ IMU-QC-ok ∧ shifted-IMU-QC-ok (the pilot's `scored_mask`), same fixes for every
  method (paired). Error $e=\lVert\mathbf z-\hat{\mathbf z}\rVert$ (in).
- **Comparators:** B2′ (reference), V2 (current best), B1, plus B2 and V1 for completeness — the pilot's code and tuned
  values, unchanged. **Controls:** V5 with every IMU input (Stage A outputs, still/rhythmic flags, CV-mode states, ψ
  regression) taken from t + 3600 s; nights from the cached window; days **circularly** within the analysis window
  (the day caches end 10 min after the window) — declared.
- **Sensitivity (secondary):** V5_p90 = V5 with the p90 σθ law, same tuned scalars.

## 5. Tuning (tuning night + tuning day only)

Tuned scalars: σ_res, τ_b, $T_{max}$, σ_v, σ_vr. Everything else is fixed above or measured (§3.3).
- **Objective** $J$ = pooled held-out RMSE over the scored fixes of schemes (s) and (g-0.5 s) on the tuning night and the
  tuning day (all animals, both schemes concatenated).
- **Constraint:** pooled NIS ∈ [1.5, 3.0], NIS = mean of forward pass-0 innovation $d^2=\boldsymbol\nu^\top S^{-1}\boldsymbol\nu$
  (model R, before gate inflation) over visible fixes with anchors ≥ 7 in the **full-data** runs of both tuning periods,
  excluding $d^2>13.82$ (χ²₂ 0.999 gross-outlier gate; a consistent filter gives ≈ 1.99 after this trim). The untrimmed
  mean and the fractions above 5.99 / 13.82 are reported. If no configuration satisfies the constraint, the one closest
  to the interval wins (then $J$).
- **Grid (staged):** stage 1 σ_res ∈ {4, 8, 16, 32} in/s² × τ_b ∈ {2, 5, 10} s × $T_{max}$ ∈ {15, 60, 300, ∞} s with
  σ_v = 0.25 in/s (V1's value), σ_vr = ∞; stage 2 (σ_v, σ_vr) ∈ {0.1, 0.25, 1, ∞} × {0.25, 1, 4, ∞} in/s at the stage-1
  winner; stage 3 σ_res × {0.7, 1, 1.4} at the stage-2 winner. Winner per stage by the constrained rule; ties (J within
  0.001 in) → the larger σ_res, then the smaller $T_{max}$. Values on a grid edge are flagged. The tuned block is written
  to the config and frozen (with a timestamp) before any test period is read.

## 6. Evaluation and acceptance (test night primary)

- **Comparison statistic** (pilot): $\Delta=1-\mathrm{med}(e_{V5})/\mathrm{med}(e_{ref})$ on the same scored fixes; 1000 paired
  5-min-block bootstrap replicates (stratified by animal for pooled values). For each animal, scheme S and reference
  $r\in\{$B2′, V2$\}$: one-sided $p_r=(1+\#\{\Delta^*\le0\})/1001$.
- **(i) Primary, Holm over the two primary schemes S ∈ {(s), (g-0.5 s)}** (family α = 0.025 one-sided, i.e. the pilot's
  "95 % CI lower bound > 0"): animal $a$ is *eligible* on S iff $\Delta\ge0.03$ vs B2′ **and** vs V2; $p_a(S)=\max(p_{B2'},p_{V2})$
  (1 if not eligible); scheme statistic $p(S)$ = the 4th-smallest $p_a(S)$ of the 5 animals. Order the schemes by $p(S)$;
  the first passes iff $p\le0.0125$; only then the second is tested at 0.025. (Equivalent: ≥ 4/5 animals beat both
  references by ≥ 3 % with the Holm-adjusted lower bound > 0.)
- **(ii) Control** on every scheme that passes (i): V5 (IMU + 1 h) vs B2′ has its 95 % CI lower bound ≤ 0 in ≥ 4/5 animals.
- **(iii) Moving fixes** (pilot: IMU-QC-ok and not IMU-still) on that scheme: pooled Δ ≥ −2 % vs B2′ **and** vs V2.
- **Verdict:** **ACCEPTED** iff some scheme passes (i)–(iii). **INCONCLUSIVE** iff (i) passes but (ii) or (iii) fails, or the
  4th-smallest is missed but ≥ 3 animals are eligible with $p_a\le0.025$ on a primary scheme. **FAIL** otherwise.
- **Secondary (reported, never the verdict):** (a), (a′), (g-1.0 s) with the same table; test-day results; RMSE and tails
  (fractions > 24 in, > 100 in, max); NIS and held-out $z^2=(\mathbf z-\hat{\mathbf z})^\top(P^s+R)^{-1}(\mathbf z-\hat{\mathbf z})$
  consistency (mean, fraction > 5.99); speed / acceleration / path plausibility of the V5 position track (pilot
  `track_metrics`); by IMU state (still / active / locomoting) and by mode (INS / CV) at the hidden fix; the handedness
  LLR; V5_p90; Stage-A validation A1/A2; the measured WISER noise model; the ψ regression (resultant, SD, coverage).

## 7. Self-test (`--selftest`, synthetic, no field data)

Synthetic head track (locomotion bouts + stationary bouts) with a 4–15-Hz behavioural head oscillation (rotation and
translation of the head about a stationary body), IMU with a gyro bias drifting linearly in clock time, strict still
windows, WISER fixes at ~3.7 Hz with anchor-dependent noise + a slow drift, a known yaw offset. Checks: (1) Stage A
recovers the bias drift (anchor bias error ≪ the drift) and the tilt at withheld windows; (2) the 2-Hz low-pass + the
body-stationary ZUPT keep the oscillation from moving the position (position RMSE during oscillation bouts ≈ the
stationary level); (3) V5 beats B2 on (s) and (g-0.5 s); (4) the +1 h-shifted control gives no gain; (5) NIS ≈ 2;
(6) the ψ regression recovers the yaw offset and the handedness; (7) the bootstrap/Holm code reproduces `boot_delta`'s
interval for the same seed; (8) the noise-model estimator recovers the planted nugget, drift SD and time constant.

## 8. Runtime and resources

Stage A ≈ 20 animal-periods × ~40 s (5 worker processes); Stage B numba kernels with `prange` over configurations; the
tuning grid (≈ 67 configurations × 10 tuning animal-periods × 3 runs) and the test evaluation (≈ 12 runs per
animal-period). Target ≤ 2 h for the full run.

## 9. What would change the conclusion

A pass on (s) or (g-0.5 s) with a passing control says the corrected inertial chain adds information at ≤ 0.5-s horizons
that motion-state labels do not. A fail with good Stage-A validation and NIS ≈ 2 says the WISER noise floor leaves no
room at these horizons. A fail with poor NIS or large tails points at the filter, not the sensor.

## 10. Classification

Regime-aware WISER: every result is a measurement result on the unverified inch frame; held-out fixes include WISER's own
drift; a gain means better prediction of WISER, which is necessary but not sufficient for better head position.

## 11. Amendments (before the full run)

All amendments below were written on 2026-10-01 after development runs on the **tuning periods only** (SF09 tuning night
and day; strict windows of all 10 tuning animal-periods for the bias-smoother fit). No test period had been read.

1. **Bias anchors (§2.4) — evidence for the rule, no rule change.** ML fit of the window smoother on the 10 tuning
   animal-periods (≈ 25 k windows): the ZARU noise is dominated by the 1/d term (σ_r ≈ 0.12–0.16 °/s·s, σ_w → 0, i.e. a
   1-s window's ZARU carries ≈ 0.13 °/s of residual head micro-rotation), q_b ≈ 2–3 × 10⁻⁶ (°/s)²/s. Predicting the
   bias of withheld ≥ 10-s windows: smoothed anchors 0.0053–0.0056 °/s, A3 running median 0.0122, raw anchors
   0.0104–0.0110. On the SF09 development pass the leave-window-out tilt error is smoothed ≈ A3 < raw. The pre-registered
   choice (§2.4, made by the full run on all tuning periods) is expected to be `smoothed`.
2. **ψ regression (§3.4).** Only pairs whose IMU span is `ok` **and within 60 s of a strict window** (`t_since_win_s` ≤ 60)
   enter; the standard error of the mean direction is $1/(\bar R\sqrt{2n_{eff}})$ with $n_{eff}=(\sum|c|)^2/\sum|c|^2$
   (bounds 3°–180°); ψ₀ is uninformative (SD 180°) when no estimate exists. Reason (SF09 tuning night): Stage A's
   |f_xy| median is 0.007 m/s² inside strict windows, 0.12 at 10–60 s, 2.0 at 60–300 s and 4.9–5.6 m/s² beyond 300 s
   (gravity leakage of a ≈ 30° tilt error; f_z −1.7 m/s²), and 77 % of the night lies > 300 s from a strict window; the
   whole-night pairs were dominated by leakage (median |Δv_I| 102 in/s over 0.5 s, resultant at the noise level 0.005)
   and the original SD formula $\sqrt{-2\ln\bar R/n}$ reported a 3° SD for that noise-level resultant.
3. **ψ process noise (§3.1)** follows the clock-time law instead of a constant: $q_\psi(t)=\max(0.0309\ \mathrm{deg^2/s},\
   2k^2\,t_{since})$ with $k$ = 0.0227 °/s, i.e. $\mathrm{Var}(\psi)$ grows like $(k\,t)^2$ since the last strict window (the
   yaw is never re-anchored by gravity). The constant rate understated the growth over the night's long gaps.
4. **CV-mode process-noise multiplier κ_cv added to the tuned scalars**, stage 1: κ_cv ∈ {1, 3, 10} (CV-mode PSD
   $=\kappa_{cv}\cdot q\,m_c$). Stage 1 becomes 4 × 3 × 4 × 3 = 144 configurations. Reason: on the SF09 tuning night the
   CV-dominated configurations ($T_{max}$ = 60 s; INS mode on 18 % of fixes) had trimmed NIS ≈ 3.6 (15 % of fixes above
   13.82) — V2's own process noise, tuned on held-out medians, is overconfident — while the INS-everywhere configurations
   ($T_{max}$ = ∞) reached NIS ≈ 2.5 but were much worse (g-0.5 RMSE 8.25 vs 5.97 in). Without a CV-mode knob the NIS
   constraint could only be met by the degenerate INS-everywhere choice.
5. **Pre-registered secondary V5_unc:** the configuration that minimises J over all evaluated configurations **without**
   the NIS constraint is also scored on the test periods (reported as secondary, never the verdict), to show what the
   constraint costs.
6. **Development observation recorded for the report (not a rule):** on the SF09 tuning night and day the complex
   regression of WISER second differences (0.25-s medians, T = 0.5–2 s) on the matching IMU kernel integral found no
   consistent direction even within 10–60 s of a strict window (local 300-s resultants at or below the null; the
   +1 h-shifted IMU alike), and neither did the independent Phase-0 A4 cache within 2–15 s of a quiet window. Where the
   attitude is good the head barely translates (strict windows are stillness); where the head translates the attitude
   is tens of degrees off. This predicts that the INS mode cannot add much; the run tests it as registered.
7. **Handedness tie (§3.4, clarification):** if neither frame wins ≥ 6 of the 10 tuning animal-periods (ties, missing
   resultants), the normal (right-handed) frame — V4's candidate — is used and the tie is reported.
8. **Secondary comparison V5 vs V5 (IMU + 1 h)** (paired, same bootstrap) added to the report: the IMU-specific part of any
   V5 gain. Reason (dry run of the whole pipeline on tuning data only, the tuning day playing the test role): V5's
   non-inertial parts (measured noise model, ZUPT, CV fallback) can move the +1 h control relative to B2′ by themselves,
   so the control-vs-B2′ criterion (unchanged, it decides) does not isolate the IMU. Also descriptive only: the |f_xy|
   table gets a 0–0.01 s ("inside a strict window") bin.
