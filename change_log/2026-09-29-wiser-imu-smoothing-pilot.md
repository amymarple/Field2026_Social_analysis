# WISER + head-IMU smoothing pilot (cohort 2026c)

> **Scope (added 2026-09-29, user review):** the IMU entered this pilot only as per-second motion-state labels (still / active / locomoting from VeDBA, |ω|, stride-band fraction). The accelerometer and gyroscope were never integrated into position — a 6-axis inertial (INS/ESKF) fusion with WISER updates was NOT tested; it had been ruled out on paper (no heading; "head ≠ body"), but the tag is on the head with the IMU, so head acceleration is the tag's acceleration, and yaw can become observable from WISER fixes while the rat moves. Read the verdicts below as "the IMU as motion-state labels adds 0.5–1.7 %", not "the IMU cannot improve WISER".

- **Plan:** [`implementation_plan/2026-09-29-wiser-imu-smoothing-pilot.md`](../implementation_plan/2026-09-29-wiser-imu-smoothing-pilot.md)
  (approved by the user 2026-09-29, "开始").
- **Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_imu_smoothing_pilot_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_smoothing_pilot_2026c.md)
  (full Definitions, prior work, tuning, V3 diagnostic, per-animal tables, verdicts, caveats); figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_imu_smoothing_pilot_{heldout,tuning,v3_diagnostic,example}_2026c.png`;
  pointer `results/2026c/wiser_baseline/reports/run_manifest_imu_smoothing_pilot_2026c.json` (the folder's
  `run_manifest.json`, which belongs to the accuracy run, is untouched).
- **Bulk:** `D:\Field2026_analysis_out\2026c\wiser_imu_smoothing_pilot_20260929_2119\` (per-fix held-out errors,
  bootstrap tables, tuning and post-hoc grids, V3 pairs, calibration deviations, `summary.json`,
  `input_provenance.json`, `log.txt`). Runtime 8.6 min.

## What changed

- New driver `wiser/scripts/analyze_wiser_imu_smoothing.py` (`--cohort 2026c`, `--selftest`). It reuses the previous
  pilot's IMU loader, QC mask, still rule and helpers by importing `analyze_imu_wiser_calibration.py` (unmodified).
  The Kalman/RTS loops use numba when it is installed (it is in `C:\Python313`); otherwise they fall back to pure
  Python, which gives the same numbers slowly.
- New config `wiser/configs/wiser_imu_smoothing_2026c.json`: inputs, nights, sessions, τ*, static references. The
  driver writes the fitted hyperparameters into `tuned`, marked as fitted on the tuning night 2026-09-08/09 only.
- Self-test: 13 checks on synthetic data, **ALL PASS** (9 s). They cover the duplicate rule, both hidden-set
  generators and bootstrap sanity. The per-anchor calibration recovers white + drift SD. The held-out scorer recovers
  the known white noise (oracle RMS 3.38 vs 3.38 in). B2 beats B1, and V1 beats B2′ on still fixes. The shifted-IMU
  controls show no gain, and a static tag's B2 track RMSE is below the raw RMSE.

## Results (test night 2026-09-10/11, 21:00–04:20; pooled over SF07/08/09/10/12)

Median held-out error (in) on hidden fixes with ≥ 7 anchors. Δ is relative to B2′ (+ = better), with the 95 % CI
from a 5-min block bootstrap:

| Method | (a) median | (a) Δ vs B2′ | (a′) median | (a′) Δ vs B2′ |
|---|---|---|---|---|
| B1 library median-7 | 4.15 | −5.6 % [−6.2, −5.0] | 4.37 | −4.1 % [−5.0, −3.2] |
| B2 robust CV Kalman/RTS | 3.97 | −1.0 % [−1.2, −0.7] | 4.22 | −0.6 % [−1.0, −0.3] |
| B2′ + drift | 3.93 | reference | 4.19 | reference |
| V1 ZUPT when IMU-still | 3.91 | +0.5 % [+0.4, +0.7] | 4.17 | +0.6 % [+0.4, +0.9] |
| V2 IMU-switched process noise | 3.86 | +1.7 % [+1.4, +2.1] | 4.12 | +1.8 % [+1.1, +2.3] |
| V1, IMU +1 h (control) | 3.94 | −0.2 % [−0.4, +0.1] | 4.20 | −0.1 % [−0.4, +0.3] |
| V2, IMU +1 h (control) | 3.97 | −0.9 % [−1.2, −0.6] | 4.23 | −0.9 % [−1.6, −0.3] |

- **Verdicts (pre-registered):**
  - **V1 FAIL.** 0/5 animals reach Δ ≥ 3 % with a CI above 0, on both (a) and (a′).
  - **V2 FAIL.** 1/5 animals pass on (a) (SF10, +3.4 %) and 0/5 on (a′). The controls show no gain in 5/5 animals.
    Pooled moving-fix Δ is +1.8 % / +1.0 %, so there is no loss on moving fixes.
  - **V3 SKIPPED.** Spearman ρ between the 1-s path turn and the head turn while running is 0.49 / 0.38 / 0.48 /
    0.58 / 0.48. That is ≥ 0.5 in 1 of 5 animals, against the required 4 of 5.
- **Where the IMU helps.** On IMU-still fixes (13 % of the scored set), V1 gains +3.4 % on (a) and +4.8 % on (a′),
  and V2 gains +3.2 % / +4.6 %. V2 also gains +2.7 % on locomoting fixes on (a). The shifted controls lose this.
  So the gain is real and specific to the aligned IMU, but diluted overall.
- **Position-only smoothing is where the gain is.** Against B1, B2′ gains +5.3 % on (a) and +4.0 % on (a′) in median
  error, and 18.5 % in RMSE on (a). On locomoting fixes B1 is 13 % worse than B2′. The six cohort-1 fixed tags give the
  median RMSE about the true (median) position shown below, and the dropped implant shows the same ordering in its
  first quiet window.

  | Track | median RMSE (in) |
  |---|---|
  | raw fixes | 7.03 |
  | B1 | 4.56 |
  | B2 | 3.91 |
  | B2′ position output | 3.80 |
- **Tuned values (tuning night only).**
  - Per-anchor robust SD, x/y in: 9 anchors 1.39/2.47, 8 anchors 1.73/3.01, 7 anchors 2.32/3.23.
  - B2: q = 3 in²/s³, no hard rejection (m_rej = ∞).
  - B2′: q = 1, T_b = 15 s, σ_b = 2.5 in.
  - V1: σ_v = 0.25 in/s.
  - V2 multipliers: still 0.01, active 0.3, locomoting 10.
  - IMU locomotion class: VeDBA ≥ 3.93 m/s² and 4–7 Hz stride-band fraction ≥ 0.10 (J = 0.60).

  Several of these values sit on the edge of their grid. A **post-hoc** wider grid, run on the tuning night only
  (no verdict uses it), gives V1 +0.05 % and V2 +0.71 % over the best extended B2′. A wider pre-registered grid would
  therefore not have promised ≥ 3 %.
- **Plausibility (test night).** Median path length is 18,210 in/h for raw fixes, 10,283 for B1 and 5,715 for B2′.
  The share of fixes more than 15 in outside the wall ridge is 0.52 % → 0.085 % → 0.026 %. Distances are
  smoothing-scale dependent.

## Headline definitions (mirrored from the report)

- **Held-out error** $e_h=\lVert\mathbf z_h-\hat{\mathbf z}_h\rVert_2$ (in). $\mathbf z_h$ is a hidden WISER fix and
  $\hat{\mathbf z}_h$ the method's prediction from the visible fixes (+ IMU). It is scored on hidden fixes with ≥ 7
  anchors whose aligned second is IMU-QC-ok for both the IMU and the +1 h-shifted IMU. **Text:** how well a method
  predicts a fix it has not seen.
  - Scheme (a) hides runs of 4–8 fixes (20 % of fixes).
  - Scheme (a′) hides all fixes in a random 10 % of 2-s windows.
  - Smoothing cannot game it: $E[e^2]=E\lVert\mathbf p_h+\mathbf b_h-\hat{\mathbf z}_h\rVert^2+E\lVert\boldsymbol\varepsilon_h\rVert^2$,
    and the white-noise term is method-independent.
- **Relative improvement** $\Delta_M=1-\operatorname{median}(e_M)/\operatorname{median}(e_{B2'})$ over the same fixes.
  The 95 % CI comes from 1000 paired block-bootstrap replicates (5-min blocks, stratified by animal for pooled values).
  **Text:** + = the method's typical error is that fraction smaller than B2′'s.
- **B2** is a per-axis constant-velocity Kalman filter + RTS smoother.
  - Process noise: $\mathrm{Cov}(\boldsymbol\eta)=q\,[\Delta t^3/3,\Delta t^2/2;\Delta t^2/2,\Delta t]$.
  - Measurement noise: $R_i=\sigma^2_{\mathrm{ax}}(A_i)$, the robust SD by `anchors_used` from tuning-night IMU-still
    bouts.
  - Outliers: pass 0 is a soft χ² innovation gate; passes 1–2 are Huber IRLS with k = 2.5 on the 2-D Mahalanobis
    smoothed residual.
- **B2′** is B2 plus an AR(1) measurement drift $b_k=e^{-\Delta t/T_b}b_{k-1}+\xi_k$, $\mathrm{Var}(b)=\sigma_b^2$. It
  predicts a hidden fix by $\hat p+\hat b$.
- **V1** adds the pseudo-measurement $0=v_k+\epsilon$, $\epsilon\sim\mathcal N(0,\sigma_v^2)$, at IMU-still steps.
  $\mathrm{still}(s)=\mathrm{ok}\wedge\mathrm{VeDBA}_{1s}<\theta_a\wedge|\omega|_{1s}<10\,^\circ/\mathrm s$ (previous
  pilot).
- **V2** switches the process noise with the IMU class of the interval midpoint: $q_k=m_{c(k)}q$, with classes
  unusable / still / active / locomoting.
- **Controls:** V1 and V2 with every IMU input taken from $s+3600$ s.
- **Acceptance:**
  - (i) Δ ≥ 3 % with CI > 0 in ≥ 4 of 5 animals.
  - (ii) The control's CI lower bound is ≤ 0 in ≥ 4 of 5 animals.
  - (iii) Pooled moving-fix Δ ≥ −2 %.
  - Each is evaluated on (a) or on (a′).
- **V3 gate:** V3 runs only if Spearman $\rho(\Delta\psi_I,\Delta\psi_W)\ge0.5$ in ≥ 4 of 5 animals.
  - $\Delta\psi_W$ is the turn between successive 1-s-median WISER displacements.
  - $\Delta\psi_I=\int_s^{s+1}\omega_{\mathrm{turn}}dt$.
  - Pairs come from locomotion windows: ≥ 3 s with WISER speed ≥ 10 in/s and the IMU active.

## Masks and deviations

- **Masks.** The previous pilot's IMU QC applies: nodata, saturated, frozen flag + rule, invalid, NaN, unreliable,
  handling, silences ± 2 min and tag validity. On top of it come each logger's own `ephys.adc_lane.on_windows`.
  - No handling window or silence falls inside either night.
  - On the test night SF08 and SF12 have no IMU for their first 2.8 and 5.3 min (lane-off restarts at 21:02:45 and
    21:05:18).
  - The ADC-lane windows remove 157 s (SF08) and 299 s (SF12).
  - Saturated and unreliable seconds: 75–237 and 269–620 per animal and night.
- **Duplicate rule.** Rows sharing (tag, timestamp) are collapsed to the max `anchors_used`, ties → min `reportid`.
  This dropped 150 rows on the tuning night and 88 on the test night.
- **Deviations** (declared in the plan before running):
  - The control criterion is read as "no significant gain" (CI lower bound ≤ 0).
  - One scored set is used, requiring both the IMU and the shifted IMU to be QC-ok.
  - The implant windows are the accuracy report's quiet windows.
  - The moving-fix condition is evaluated pooled.
  - numba runs the loops.
- **After the plan:**
  - **The first run is superseded.** `…_20260929_2108` applied every logger's ADC-lane window to all five animals, so
    SF12's window masked 299 s at 21:00–21:05 for everyone. The mask was fixed to per-logger windows and the run
    repeated. Tuned values are identical, since the tuning night has no ADC window. The verdicts did not change.
  - **The post-hoc wider tuning-night grid** was added and labelled as such.

## Caveats

- One test night, regime B.
- The held-out target includes WISER's slow drift. The static references test position only for tags that did not
  move.
- The tuned σ_b exceeds the slow share implied by the within-bout autocorrelation. B2′'s "drift" state therefore acts
  as a flexible low-frequency term, and its position output p is smoother than B2's. Do not use it for speed or
  distance without validation.
- WISER's internal filtering is unknown.

## Verification

- `python wiser/scripts/analyze_wiser_imu_smoothing.py --selftest` → ALL PASS.
- The full run completed (exit 0). The WISER DB sha256 prefix was checked (`82ccadfde589`) and opened `mode=ro` +
  `query_only`. The tag table was resolved per night.
- Test-night masks were checked against the ADC-lane YAML windows. SF08's `nodata` (167 s) and SF12's (320 s) match
  their session starts.
- `run_manifest.json` of `wiser_baseline` is unchanged. No existing analysis code was modified.
