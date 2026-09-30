# Head-IMU inertial fusion with WISER (V4): IMU processing, reusable caches, 6-axis ESKF + RTS (cohort 2026c)

- **Plan:** [`implementation_plan/2026-09-29-wiser-ins-fusion.md`](../implementation_plan/2026-09-29-wiser-ins-fusion.md)
  (approved by the user 2026-09-29; amendments of 2026-09-30 fixed on the tuning night before the full run).
- **Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_ins_fusion_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_ins_fusion_2026c.md)
  (full Definitions, IMU quality, cache formats, tuning and development diagnostics, per-animal tables, tails, handedness,
  consistency, caveats, deviations); figures `results/2026c/wiser_baseline/figures/wiser_baseline_ins_fusion_{imu_psd,imu_quality,heldout,heading,example}_2026c.png`;
  pointer `results/2026c/wiser_baseline/reports/run_manifest_ins_fusion_2026c.json` (the folder's `run_manifest.json` is untouched).
- **Bulk:** `D:\Field2026_analysis_out\2026c\wiser_ins_fusion_20260930_0016\` (fusion intermediates per animal-night,
  per-second IMU tables, every held-out error, bootstrap tables, grids, yaw hypotheses, handedness + null, IMU-quality
  tables, PSDs, `summary.json`, `input_provenance.json`, `log.txt`). Runtime: Phase A 2.5 min, Phases B–C 25.3 min.

## What changed

- New `wiser/scripts/build_imu_wiser_cache.py` (Phase A, `--selftest` PASS, 12 checks). It reads raw data **once** into
  reusable caches:
  - **A1** `D:\Field2026_analysis_out\2026c\imu_raw_cache\<SFxx>\<session>__<start>_<end>.npz` (10 files, 701 MB): int16
    analogin lanes 1–6 at 1250 Hz, 20:50 → 05:30 per animal-night, per-lane saturation, frozen flag, the verbatim
    `pc_time_fit.json`, session metadata and the sha256 of the first 64 MiB of `analogin.dat`; `cache_unix_ms()` gives
    field-PC time. Plus `index_2026c.csv`.
  - **A2** `D:\Field2026_analysis_out\2026c\wiser_fix_cache\night_<date>\<SFxx>.csv.gz` (10 files, 39 MB): deduplicated
    WISER fixes (smoothing-pilot rule) with anchors, anchor list, library validity/speed, and handling, silence, tag
    validity and ADC-lane masks.
- New `wiser/scripts/analyze_wiser_ins_fusion.py` (Phases B–C, `--selftest` ALL PASS, 12 checks in 38 s, `--report-only`).
  It imports `ephys/make_imu.py`, `ephys/read_imu.py` and both earlier WISER pilots without editing them. Phase B writes
  **A3** `D:\Field2026_analysis_out\2026c\imu100_cache\<SFxx>\night_<date>.npz` (10 files, 791 MB): 100-Hz calibrated,
  smoothed head-frame acc/gyro, field-PC Unix ms on the IMU clock (τ* not applied), QC flags and all calibration
  parameters. Phase C runs the ESKF + RTS with numba (prange over hypotheses/configs).
- New config `wiser/configs/wiser_ins_fusion_2026c.json` (rules, grids; `tuned` block written by the run, marked as
  fitted on 2026-09-08/09 only).

## Results

**IMU quality (Phase B; decisions on the tuning night):**
- **Accelerometer:** a diagonal ellipsoid calibration beats scalar k_a on held-out quiet windows in 5/5 animals. The
  median gravity residual falls from 0.299 to 0.016 m/s². Per-axis offsets reach 1.31 m/s² (≈ 7.6° of tilt), which is
  why k_a varied 0.86–1.20 within a logger.
- **Gyro:**
  - Bias: the running median beats the 10-min blocks, but only marginally (leave-one-run-out still-run yaw drift 2.26 vs
    2.33 °/min).
  - Scale (static–dynamic–static): s* = 1.030 [1.005, 1.058] from 52 pairs, so it is applied.
  - The kinematic slope of 1.2–1.4 (r ≈ 0.75) does not move with calibration and grows with bandwidth: it measures linear
    acceleration, not gyro scale.
  - Acc–gyro latency: 9–12.5 ms (gyro late). It is measured but not applied, because it made no difference on the tuning
    night.
- **Saturation and spikes:** saturation is almost only on the head-yaw gyro (lane 4), 1,072–7,283 raw samples per night
  in bursts up to 46 ms. Single-sample spikes are rare (~1–50 per hour per lane).
- **Low-pass cutoff:** head-motion power stays above 2× the noise floor up to 100 Hz on both sensors, so the cutoff is
  the 40-Hz clip.

**V4 on the test night 2026-09-10/11** (5 animals). Held-out WISER fixes with ≥ 7 anchors, Δ vs B2′ (+ = better, 95 %
block-bootstrap CI):

| Method | (a) median (in) | (a) Δ | (a′) median (in) | (a′) Δ |
|---|---|---|---|---|
| B2′ (reference) | 3.93 | — | 4.19 | — |
| V2 IMU-switched q (smoothing pilot) | 3.86 | +1.7 % [+1.3, +2.1] | 4.12 | +1.8 % [+1.1, +2.3] |
| **V4 INS (ESKF + RTS)** | 4.23 | **−7.7 % [−8.6, −6.7]** | 4.82 | **−14.8 % [−16.6, −13.1]** |
| V4, IMU +1 h (control) | 4.65 | −18.2 % [−19.5, −17.0] | 5.46 | −30.2 % [−32.4, −28.0] |

- **Verdict (pre-registered): V4 FAIL.**
  - 0/5 animals reach Δ ≥ 3 % with the CI above 0, on either scheme.
  - The control shows no gain in 5/5 animals.
  - Pooled Δ on moving fixes is −9.1 % / −17.6 %.
  - B1/B2/B2′/V1/V2 reproduce the smoothing pilot (differences ≤ 3 × 10⁻⁵ in, identical scored counts).
- **By IMU state** ((a) / (a′)):
  - Still: +2.8 % / +3.4 %.
  - Locomoting: +1.2 % / −2.1 %.
  - Active in place (IMU-moving, not locomoting): −12.6 % / −21.4 %.
- **Tails:** 0.86 % of V4's scored hidden fixes are off by > 100 in (max 2,404 in), against 0.004 % for B2′. V4's RMSE is
  61.5 in, against 6.5 in for B2′. These are inertial divergences during violent head motion: the tilt-reset guard fired
  155–275 times per night. The filter is overconfident, with NIS mean ≈ 15 against 2.
- **Handedness (reported, not used to choose the frame):** LLR normal − mirrored is > 0 on 10/10 animal-nights (+0.17 …
  +0.37 nats per fix). With the +1 h-shifted IMU (post-hoc null) it is 5/10 positive, −0.014 … +0.097 per fix. This
  points to a right-handed WISER frame, the same sign as the calibration pilot's M4. It stays a candidate until a video
  event confirms it.

## Definitions (headline quantities; full set in the report)

- **Held-out error** $e_j=\lVert\mathbf z_j-\hat{\mathbf z}_j\rVert$ (in) on hidden fixes with $A_j\ge7$ whose second is IMU-
  and +1 h-IMU-QC-ok; **Δ** $=1-\mathrm{med}(e_{M})/\mathrm{med}(e_{B2'})$, CI from 1000 paired 5-min-block bootstrap draws
  (smoothing pilot, unchanged). **Acceptance:** Δ ≥ 3 % with CI > 0 in ≥ 4/5 animals on (a) or (a′), the +1 h control's
  CI lower bound ≤ 0 in ≥ 4/5, pooled moving Δ ≥ −2 %.
- **V4:** error-state Kalman filter with nominal $\mathbf p,\mathbf v$ (2-D, in), $q$, $\mathbf b_a$, $\mathbf b_g$, $\mathbf b_w$.
  - Propagation: $\mathbf f=R(q)(\mathbf a-\mathbf b_a)$, $\dot{\mathbf v}=\mathbf f_{xy}$, $\dot q=\tfrac12q\otimes(\boldsymbol\omega-\mathbf b_g)$.
  - Updates:
    - WISER: $\mathbf z=\mathbf p+\mathbf b_w+\boldsymbol\varepsilon$ with per-anchor noise, a soft χ² gate, then Huber IRLS.
    - In IMU-still samples: ZUPT, ZARU and the gravity update.
    - Dynamic gravity update when $||\mathbf a|-g|<0.1g$ and $|\boldsymbol\omega|<100$ °/s.
    - Tilt-reset guard.
  - RTS smoother in error-state form: the held-out prediction is $\mathbf p^s+\mathbf b^s_w$.
- **Pseudo-log-likelihood** $\ell(\psi_0)=-\tfrac12\sum_j(d_j^2+\ln\det S_j+2\ln2\pi)$ over visible fixes (pass 0);
  24 initial yaws, ML kept. **Handedness LLR** $=\max\ell_{normal}-\max\ell_{mirrored}$ (WISER $y\to-y$).
  **NIS** $d_j^2=\boldsymbol\nu_j^\top S_j^{-1}\boldsymbol\nu_j$ (χ²₂ if consistent).
- **Held-out gravity residual** $=\mathrm{med}\,||\mathbf a_{cal}(\bar{\mathbf a}_w)|-g|$ over quasi-static 0.5-s windows of the
  other fold (alternating 10-min blocks); **ellipsoid** $\mathbf a_{cal}=D(\mathbf a-\mathbf o)$.
- **Gyro scale** $s^*=\arg\min_s\sum_p\angle(R_{12}(s)^\top\mathbf u_1,\mathbf u_2)^2$ over static–dynamic–static pairs.
- **LOO yaw drift** of a still run $=|\sum(\boldsymbol\omega-\hat{\mathbf b}_{-R})\cdot\hat{\mathbf u}_R\Delta t|/T_R$.

## Deviations (details in the report §9)

- A1 was extended to 05:30 for the +1 h control, and A2 is csv.gz because pyarrow is not installed.
- The Hampel floor is the lane's global noise SD. This was changed after the self-test and before any real-data run.
- Two additions were written into the plan before coding: ZARU plus a still-period gravity update, and still-sample gyro
  noise set to the measured density.
- **Tuning-night amendments of 2026-09-30, made before any test-night V4 result** (plan §Amendments):
  - The first design lost attitude for 20–25 min at a time (tilt was corrected only in still seconds).
  - It gained a dynamic gravity update and a tilt-reset guard.
  - The grid was extended with σ_fd, σ_a = 0.01 and a moving-fix R factor k_R.
- Development diagnostics used SF09 on the tuning night.
- Post hoc (no verdict uses them): the handedness null and the tail table.

## Verification

- Both self-tests pass.
- Phase A fix counts per night equal the smoothing pilot's (103,339 … 105,524).
- The recomputed baselines reproduce the pilot's per-fix scores.
- A3 cache files load and carry their calibration JSON.
- No raw file, SQLite database or earlier script was modified. Raw data was read only by Phase A, and the WISER copy was
  opened mode=ro with query_only.
