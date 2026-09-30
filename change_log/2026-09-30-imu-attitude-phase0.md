# Head-IMU attitude, Phase 0: gyro self-calibration, saturation handling, attitude-error model, pre-registered fusion gate — **GATE FAIL** (cohort 2026c) — 2026-09-30

- **Plan:** [`implementation_plan/2026-09-30-imu-attitude-phase0.md`](../implementation_plan/2026-09-30-imu-attitude-phase0.md)
  (approved by the user 2026-09-30 "phase0 开始"; amendments 1–7 recorded there before the full run).
- **Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_phase0_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_phase0_2026c.md)
  (full Definitions, floor, calibration, saturation, A4 format + usability, growth law, gate, post-hoc diagnostics);
  figures `results/2026c/wiser_baseline/figures/wiser_baseline_imu_attitude_phase0_{tilt_by_bin,gyro_matrix,saturation,growth_law,omega_distribution,drift_scaling}_2026c.png`;
  pointer `run_manifest_imu_attitude_phase0_2026c.json` (the folder's `run_manifest.json` untouched).
- **Bulk:** `D:\Field2026_analysis_out\2026c\imu_attitude_phase0_20260930_1203\` (`bouts_all.csv` with every model's per-bout
  error, `floor.csv`, `sat_runs.csv` (4,320 clipped runs), `sat_bouts.csv`, `per_second/`, `omega_distribution.csv`,
  `model_selection_cv.csv`, `fits.json`, `growth_table.csv`, `a4_usability.csv`, `summary.json`, `input_provenance.json`,
  `log.txt`). Runtime 6.1 min + 1 min report. IMU only — **no WISER fusion was run.**
- **A4 cache:** `D:\Field2026_analysis_out\2026c\imu16_cache\<SFxx>\night_<date>.npz` (10 files, 390 MB) + `README.md`.

## What changed

- New `wiser/scripts/analyze_imu_attitude_phase0.py` (base Python: numpy/scipy/pandas/numba/matplotlib; `--selftest` ALL
  PASS, 16 checks in 6 s; `--report-only <run_dir>`; `--no-a4`). It imports `build_imu_wiser_cache` (A1 loader),
  `analyze_wiser_ins_fusion` (Hampel), `make_imu`, `read_imu`, `_common` — nothing existing was edited. Reads only the A1
  (raw 1250-Hz lanes) and A3 (100-Hz calibrated) caches; raw `E:` never read.
- New config `wiser/configs/imu_attitude_phase0_2026c.json` (all rules and thresholds; the run wrote `fitted`: selected
  model, per-animal matrices with bootstrap CIs, growth law, gate verdict).
- New cache **A4** (16 Hz per animal-night): `t_unix_ms`, `f_xy_2hz|1hz|4hz` (world-frame horizontal specific force, yaw
  arbitrary but continuous), `f_z_2hz`, `q_wh`, `sigma_theta_deg` + `p90_theta_deg` at each sample's `t_active_s`, flags
  `still/dyn/sat/recon/shake/frozen/invalid`, behaviour-band powers `bp_w_*`, `bp_a_*` (2–4, 4–8, 8–12, 12–20 Hz of
  |ω| and |a|), `calib_json`, `meta_json`.

## Results (test night 2026-09-10/11 unless stated; bouts without gyro saturation)

- **GATE FAIL** (pre-registered: median end-of-bout tilt error 2–5 s ≤ 1.0° AND 5–15 s ≤ 2.0°, pooled and ≥ 4/5 animals):
  pooled **1.76°** (95 % CI 1.52–2.22, n 244; audit baseline 1.93°) and **3.29°** (2.57–3.70, n 121; baseline 2.96°);
  **0/5 animals** pass both. Floor (0a, adjacent 0.5-s quiet windows, pooled) **0.048°** (1 s: 0.052°, 2 s: 0.074°) →
  excess over the floor 1.7° / 3.2°, so the pre-registered "test at its limit" clause (< 0.5°) does not apply.
  Per animal baseline → calibrated, 2–5 s / 5–15 s: SF07 2.42→2.26 / 2.96→2.68; SF08 1.81→1.65 / 4.90→4.81; SF09
  1.75→1.50 / 2.73→3.13; SF10 2.98→2.78 / 2.30→1.45; SF12 1.87→1.72 / 4.01→5.04. Pooled 15–40 s 7.47→6.23, 40–90 s 9.41→9.38.
- **Gyro self-calibration (0b) does not generalise.** Tuning-night 2-fold CV, pooled held-out median on 2–15 s bouts:
  `diag` 2.63° (selected), `scalar` 2.78°, full `M` 3.44°, `M_rate` 3.47° (post-hoc exploratory g-sensitivity models
  `scalar_gsens` 3.56°, `M_gsens` 4.47°); the 1.03 baseline per animal 1.63–3.83°. The 9-parameter matrix is *worse*
  held-out than the scalar on 3/4 animals with CV (SF07 had 24 fit bouts, no CV). Fitted diag entries (M − I) are −0.06…+0.02
  with bootstrap CIs ± 0.03–0.25: the per-axis scale is 0.94–1.02, i.e. not 1.03, but the data cannot pin it better than
  ≈ 3 %, and it moves the test-night medians by ≤ 0.25°.
- **What the residual drift scales with (calibrated):** Spearman(e, Θ) 0.57 vs (e, duration) 0.40; 1.07° per 100° turned
  (p90 6.0); 0.42 °/s of activity (p90 2.4); error direction random in the head frame (consistency 0.07). Rectification
  test: Spearman(drift rate, HF gyro power) 0.03, (rate, HF acc power) 0.02 → **not vibration rectification**; (rate,
  mean |a_h|) 0.36, (e, mean |a_h|) 0.80 → scales with movement vigour. No deterministic gyro model tested (matrix, rate
  term, g-sensitivity) captures it.
- **Post-hoc diagnostic (not the gate; report §8):** the audit's test does not propagate the gyro through its own 0.5-s
  gravity windows, which sit in "quiet" seconds carrying a median **8.5°** of integrated head rotation. Spearman(e, edge
  motion) 0.62; log-log fit $e\propto\Theta^{0.31}\,\mathrm{edge}^{0.75}\,T^{0.02}$; within every rotation bin the
  low-edge-motion half has 1.5–3× smaller error (e.g. Θ 100–200°: 1.55° vs 4.84°); by edge-motion tertile the 2–5 s bin
  gives 1.02 / 1.59 / 6.33° and the 5–15 s bin 1.64 / 3.36 / 6.48°. The naive subset edge < 2° (25 bouts, 0.06°) is
  confounded (those bouts have Θ ≈ 3°) and is reported as such. **Reading:** the verdict stands as registered, but a
  large part of the reported error is the test's own edge windows; a Phase-1 gate must propagate through them or require
  still edges.
- **IMU update rate (new fact):** all six analogin lanes are **sample-and-hold at ≈ 190 Hz** (hold 5–7 logger samples,
  mean 6.6 ≈ 5.3 ms, ≈ 5 % of updates skipped, acc and gyro synchronous). The 1250 Hz is the logger clock; nothing faster
  than ~5 ms is resolved; a clipped run of ~7 raw samples is one clipped gyro reading.
- **Saturation (0c), 10 animal-nights, 4,320 clipped gyro runs:** `shake_train` 3,455 (80 %), `rotation` 758, `impact`
  103, `suspect_monotone` 4 (SF08 1, SF09 2, SF12 1 — no SF12 excess), `short_broadband` 0. Run duration median 5.6 ms
  (one reading), p99 15 ms, max 46 ms; onset spacing 2,047/4,301 in 25–40 ms (= half-periods of 12.5–20 Hz shakes), 1,710
  isolated (> 200 ms). |a|_max during runs: shakes 6.6 g, rotation 6.3 g, impact 9.0 g (clipped), suspect 1.7 g. 240 shake
  trains, |net rotation| median 13.3° (p90 31°) — not zero-mean, so freezing the attitude across them (treatment iii)
  is harmful (sat bouts 9.4° → 19.8°). Log-quadratic reconstruction on the 2 + 2 innermost held readings: 3,599 runs
  reconstructed, 618 rejected; missing angle median 1.36° (p90 10.1°), reconstructed peaks median 2,335 °/s (p90 3,450).
  On the 75 bouts with saturation the tilt error is 10.95° (clipped, A3) → 9.34° (clipped + M) → 9.41° (reconstructed +
  M, used in A4): saturation is not what limits those bouts.
- **Head angular speed vs literature** (calibrated 100 Hz, active seconds): p50 81–108 °/s, p90 238–292, p99 488–597,
  p99.9 990–1,470, max 3,200–5,200 (reconstructed); active SD 110–137 °/s (Pasquet 2016 ambulation SD ≈ 107); quiet p50
  0.7–1.2 °/s; largest unclipped raw |ω| 2,457–2,892 °/s; 0.3–0.9 % of active seconds contain a clipped gyro sample.
- **Growth law (0e):** A (adopted, in A4) $\sigma_\theta(t)=\sqrt{0.82^2+(0.193\,t)^2}$ ° (R² 0.88); B 0.70 + 0.176 t
  (R² 0.93); p90 envelope $\sqrt{6.6^2+(0.477\,t)^2}$; baseline chain σ₀ 0.95, k 0.181; per-animal k 0.20 (SF08, SF10),
  0.35 (SF09), 0.80–0.84 °/s (SF07, SF12). σ₀ (0.82°) ≫ floor (0.05°): the error does not grow smoothly from zero —
  consistent with the edge-window effect.
- **A4 usability:** quiet-tilt check 0.19–0.29°; only 4–16 % of 16-Hz samples lie within 2 s of a quiet window, 59–91 %
  are ≥ 60 s from one; median |f_xy_2hz| 0.00–0.01 m/s² (t_active < 2 s), 0.2–0.4 (2–5 s), 0.35–0.7 (5–15 s), 3–8 m/s²
  (≥ 60 s, gravity leakage); σ_θ median 18–415° per night. Without aiding the pure-IMU horizontal specific force is
  meaningful only within seconds of a quiet window — which is what `sigma_theta_deg` encodes.

## Definitions (headline; full set in the report §2)

- **Bout / tilt error:** maximal non-quiet run $[a,b)$, 2–90 s; $\hat{\mathbf g}_{start/end}$ = normalised 0.5-s acc means
  before/after; $\mathbf g_{k+1}=\mathrm{Exp}(-\boldsymbol\omega_k\Delta t)\mathbf g_k$; $e=\angle(\mathbf g_b,\hat{\mathbf g}_{end})$ (°).
- **Floor:** $\varphi_L=\angle(\bar{\mathbf a}_{w_1},\bar{\mathbf a}_{w_2})$ for adjacent L-s windows inside quiet runs.
- **Models:** $\boldsymbol\omega=M(\mathbf w-\mathbf b)$ with $M$ = (1+s)I / diag(1+d) / I+E; `M_rate` adds $(1+c|\mathbf w-\mathbf b|^2/\omega_0^2)$;
  exploratory $+K\mathbf a$. Huber ($f$ = 3°) on $\boldsymbol\varepsilon=\mathbf g_b-\hat{\mathbf g}_{end}$ over tuning 2–15 s
  bouts; selection by pooled 2-fold CV among the four registered models; 200-draw bootstrap CIs.
- **Saturation classes (priority):** `impact` (acc clipped ± 10 ms) → `shake_train` (train spacing 25–70 ms, alternating
  sign ≥ 50 %) → `short_broadband` (1 reading, $W_{acc}$ ≥ 0.5) → `suspect_monotone` (|net| ≥ 60° in run ± 25 ms, |a| < 2 g)
  → `rotation`. Reconstruction $\ln|\omega|=p_0+p_1t+p_2t^2$ through the 2 + 2 innermost held readings; missing angle
  $\sum(|\hat\omega|-\omega_{rail})\Delta t$.
- **Growth law:** $\sigma_\theta$ = per-axis SD of the 2-D tilt error (median angle = 1.1774 σ), fitted to bin medians vs
  duration with the floor at t = 0.
- **Gate:** pooled medians ≤ 1.0° (2–5 s) and ≤ 2.0° (5–15 s) and ≥ 4/5 animals; thresholds fixed in the plan.

## Deviations (all recorded in the plan before the full run unless marked *after*)

1. Literature audit folded in before coding 0c/0d: train-structure saturation classes, band powers in A4, citations.
2. Sample-and-hold discovery (≈ 190 Hz): shoulders/slopes/reconstruction on held readings; `short_broadband` = one reading.
3. Bias taken exactly as A3 applied it (b = w − gyr_A3/1.03); A3's 1-min nodes would have been off by up to 0.5 °/s.
4. Exploratory g-sensitivity models added after the SF09 development pass — excluded from selection and gate.
5. Edge-motion diagnostic declared after the SF09 pass; the matched-activity version and the confound statement were
   added *after* the full run (report §8, labelled post-hoc; the verdict was never touched).
6. Reconstruction shoulders 2 + 2 innermost readings (synthetic-only decision); p90 growth fit anchored at the floor p90.
7. A4 usability table added *after* the full run (descriptive).
8. SF07 contributed no CV fold (24 fit bouts; 4.7 % quiet on the tuning night); the selection pooled four animals.

## Verification

- `--selftest` ALL PASS (M and rate term recovered; exploratory K recovered; isolated / held / train / spike / impact
  saturation cases; floor vs Rayleigh theory; attitude tracking, f_xy recovery and yaw continuity; growth-law fit).
- The Phase-0 gyro chain without reconstruction is A3's chain (bias identity above holds to float32 rounding).
- A4 files load; keys, shapes and flags as documented; quiet-tilt check ≤ 0.29° on all ten nights.
- No raw file, cache (A1/A3) or earlier script was modified; the three SF09 development runs were pruned (`prune(keep=1)`).
- Not committed (user rule for this session).
