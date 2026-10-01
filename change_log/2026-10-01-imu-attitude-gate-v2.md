# Head-IMU attitude gate v2: strict accelerometer-led still windows, centre-to-centre propagation, day sleep — **GATE PASS**; gyro drift **linear in clock time (bias-like)** (cohort 2026c) — 2026-10-01

- **Plan:** [`implementation_plan/2026-10-01-imu-attitude-gate-v2.md`](../implementation_plan/2026-10-01-imu-attitude-gate-v2.md)
  (approved by the user 2026-10-01 "去吧"; pre-registered before any computation on the test periods; amendments 1–2
  recorded there before the full run).
- **Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_gate_v2_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_gate_v2_2026c.md)
  (full Definitions, windows + WISER, floor, model choice, gate + information sets, rotation-matched comparison with
  Phase 0, linearity, bias residual, anchor-ZARU, growth law, suggested human video checks); figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_imu_attitude_gate_v2_{tilt_by_bin,still_windows,edge_effect,chain_growth,linearity,growth_law}_2026c.png`;
  pointer `run_manifest_imu_attitude_gate_v2_2026c.json` (the folder's `run_manifest.json` untouched).
- **Bulk:** `D:\Field2026_analysis_out\2026c\imu_attitude_gate_v2_20261001_0847\` (45 MB: `still_windows.csv.gz`,
  `bouts_all.csv.gz`, `floor.csv`, `floor_all_windows.csv`, `model_selection_cv.csv`, `selection.json` (frozen 08:54:33,
  before the first test period was read at 08:54:54), `fits.json`, `chain_records.csv.gz`, `chain_records_zaru_compare.csv.gz`,
  `chain_increments.csv`, `chain_curves.csv`, `bias_residuals.csv`, `growth_*.csv`, `gate_by_rotation.csv`,
  `theta_matched_vs_phase0.csv`, `sat_runs.csv.gz`, `human_checks.csv`, `summary.json`, `input_provenance.json`, `log.txt`).
  Runtime 12.2 min. Tuning-only development pass kept: `…\imu_attitude_gate_v2_20261001_0833\` (17 MB).
- **New day caches** (same roots and formats as the night caches, never overwriting; extraction 4 min, raw `E:` read once):
  A1 `D:\Field2026_analysis_out\2026c\imu_raw_cache\<SFxx>\<session>__<start>_<end>.npz` (10 files, 622 MB; new index
  `index_day_2026c.csv`); A3-equivalent `imu100_cache\<SFxx>\day_20260908.npz` / `day_20260911.npz` (10 files, 823 MB);
  A2 `wiser_fix_cache\day_<date>\<SFxx>.csv.gz` (10 files, 47 MB; new index `index_day_2026c.csv`); a `README.md` written in
  each of the three roots (none existed). The existing night files and indexes were not touched.

## What changed

- New `wiser/scripts/analyze_imu_attitude_gate_v2.py` (base Python + numba; `--build-day-caches`, `--roles tuning`,
  `--report-only <run_dir>`, `--selftest` ALL PASS, 13 checks in 6 s). It imports `analyze_imu_attitude_phase0`
  (loader, Hampel + saturation classes + held-reading reconstruction, gyro chain, `BoutSet`, gyro models + Huber fit +
  bootstrap, Rodrigues kernel, `fit_growth`), `build_imu_wiser_cache` (`cache_imu_window`, `wiser_night`),
  `analyze_wiser_ins_fusion` (A3 chain functions) and `analyze_imu_wiser_calibration` — none of them edited.
- New config `wiser/configs/imu_attitude_gate_v2_2026c.json` (periods, sessions, every rule; the run wrote `fitted`:
  frozen selection, gate, floor, linearity verdicts, growth laws).
- Day periods: tuning day 2026-09-08 08:00 → 18:30, test day 2026-09-11 10:00 → 17:30 (sessions in the plan; all FM65,
  pc_time `OK-native`; SF12's 09-11 session used for the IMU despite its neural-connector field flag, as instructed).
  Nights 21:00 → 04:20 from the existing caches.

## Results (test periods = night 2026-09-10/11 + day 2026-09-11 unless stated)

- **Strict still windows:** test 18,420 (day 15,914 in 37.5 valid h, 1,493 min still; night 2,506 in 36.5 h, 178 min);
  WISER confirmed 14,323, contradicted 4,017 (22 %, dropped), unavailable 80. Contradicted windows have the same
  accelerometer floor as confirmed ones (all windows ≥ 4 s: φ_half 0.087 vs 0.075° day, φ1.0 0.025 vs 0.027°) → WISER
  contradictions are mostly 1-s-median jitter near the 6-in radius, not motion.
- **Floor:** φ1.0 0.029° (p90 0.076), φ2.0 0.038°, halves 0.083°, halves gyro-propagated 0.127° (p90 0.47).
- **Model choice (tuning night + day, 2-fold CV, 2–15 s bouts):** scalar 0.348°, diag 0.343°, M 0.348°, M_rate 0.347° →
  `scalar` (tie rule). Fitted scale 1 + s: SF07 0.962, SF08 0.951, SF09 0.995, SF10 1.001, SF12 1.000 (not 1.03).
- **GATE PASS** (pre-registered, thresholds unchanged): 2–5 s **0.30°** (95 % CI 0.27–0.32, n 812; thr 1.0) and
  5–15 s **0.62°** (0.59–0.69, n 930; thr 2.0); **5/5 animals** pass both (SF07 0.34/0.61, SF08 0.25/0.61,
  SF09 0.38/0.82, SF10 0.14/0.45, SF12 0.33/0.64). Phase 0: 1.76° / 3.29° (FAIL). Information only: night-only
  0.27/0.69 (4/5), day-only 0.31/0.62 (5/5), without the WISER filter 0.31/0.64, ≥ 2-s windows 0.32/0.61, 1.03 baseline
  0.32/0.66, edge-style on the same bouts 0.30/0.61 — all PASS.
- **What the PASS covers:** bouts between strict windows are gentle (median Θ 8° / 28° in the gate bins) and none contains
  gyro clipping (clipping only occurs in vigorous activity, never between strict windows ≤ 90 s apart). Gate bins with
  Θ > 100°: 0.71° (n 18) / 0.92° (n 231); 5–15 s with Θ > 400°: 1.86° (n 27). Rotation-matched against Phase 0's bouts:
  2–4× smaller error for 50–400°, similar (2–4°) above 400°. Net rotation inside the propagated half-windows 0.37° (vs
  8.45° integrated |ω| in Phase 0's unpropagated edges); edge-style − centre-to-centre on the same bouts −0.04° → with
  strict windows the edge effect is gone.
- **Is the gyro drift linear? Yes — LINEAR IN TIME (bias-like)**, pooled, day, night and through saturation (two-part
  rule, amendment 1). Chained anchors (6,945 chains, 391 k records, no reset, ≤ 10 min): held-out test LL per record
  L_t −3.780 > LR_t −3.811 > LR_a −3.908 > RW_t −4.009 > RW_a −4.123 > L_a −4.154 > R −4.469; L_t − RW_t +0.229
  (block-bootstrap CI 0.145–0.323); driver clock time (L_a − L_t −0.37 [−0.60, −0.14], R − L_t −0.69 [−0.85, −0.55]);
  error increments direction-consistent (median C_inc 0.82 vs null 0.30; 74 % of chains above their null p95).
  Empirically the median error / time stays at **≈ 1.6–2.1 °/min from 5 s to 10 min** (0.2° → 12°), in day (still)
  and night records alike, slightly flattening at 5–10 min. Per animal (no CIs): L_t best for SF08, SF10; SF07 L_t ≈ RW_t;
  SF09 favours active time; SF12 rotation ≈ clock time — the pooled verdict is not uniform.
- **Bias residual during strict windows ≥ 10 s** (leave-window-out running-median bias): tilt 1.53 °/min median (p90 5.6),
  yaw |0.94| °/min — the A3 ±5-min running-median bias leaves a ≈ 1.5–2 °/min residual that drives the linear drift.
  **Exploratory anchor-ZARU** (bias re-estimated from the anchor's own ≥ 10-s window): 10–30 s 0.52 → 0.28°, 30–60 s
  1.19 → 0.64°, 60–120 s 2.38 → 1.39°, 5–10 min 10.1 → 8.5° — a local bias update halves the error for 1–2 min, then
  the bias has moved: a filter needs a zero-rate bias update at every still window.
- **Corrected growth law:** test bouts vs active time $\sigma_\theta(t_{act})=\sqrt{0.30^2+(0.037\,t_{act})^2}$° (R² 0.84),
  p90 $\sqrt{1.54^2+(0.151\,t_{act})^2}$° — k ≈ 5× smaller than Phase 0's $\sqrt{0.82^2+(0.193\,t)^2}$ (p90
  $\sqrt{6.61^2+(0.477\,t)^2}$). For horizons beyond seconds the clock is t, not t_act: chain records
  $\sigma_\theta(t)=\sqrt{0.78^2+(0.0227\,t)^2}$° (R² 0.99), p90 $\sqrt{3.07^2+(0.0921\,t)^2}$° (t ≤ 600 s since the last
  strict window). The Rayleigh chain models are misspecified in the tail (p90/median ≈ 3.4 vs 1.8), so their fitted b
  (0.043 °/s) is an RMS rate ≈ 2× the median rate.
- **Consequence (Phase-0 plan):** the gate decides whether inertial fusion with WISER is worth attempting — with this PASS
  it is, provided the filter re-estimates the gyro bias at every still window and uses the clock-time law as attitude
  process noise; minutes of vigorous activity without still windows remain bias-limited (≈ 2 °/min).

## Definitions (headline; full set in the report §2)

- **Strict still window $W$:** greedy run of 0.1-s blocks (all samples valid, no saturation, every
  $|\boldsymbol\omega^{A3}|<3$ °/s) with $\max_j\angle(\hat{\mathbf u}_j,\bar{\mathbf m}_W)<0.3^\circ$ and
  $\big||\bar{\mathbf m}_W|-g\big|<0.03g$, ≥ 1.0 s (gate) / ≥ 2.0 s. Text: the measured gravity direction stays within
  0.3° of its mean at 0.1-s resolution; rejects slow rotation at constant |a|.
- **WISER support:** 1-s median tag positions over the window ± 2 s; confirmed iff all within 6 in of their median
  (≥ 3 bins, ≥ 50 % coverage), else contradicted (dropped); otherwise unavailable (kept).
- **Centre-to-centre tilt error:** $\mathbf g_{c_i}=\hat{\mathbf g}_{W_i}$, $\mathbf g_{k+1}=\mathrm{Exp}(-\boldsymbol\omega_k\Delta t)\mathbf g_k$
  to $c_{i+1}$, $e=\angle(\mathbf g_{c_{i+1}},\hat{\mathbf g}_{W_{i+1}})$; bins by $T_{in}=(s_{i+1}-e_i)\Delta t$; active iff
  the gap holds ≥ 1 A3 non-quiet sample.
- **Floor:** $\varphi_L=\angle(\bar{\mathbf a}_{[m-L,m)},\bar{\mathbf a}_{[m,m+L)})$ in windows ≥ 4 s; gate floor = test median of $\varphi_{1.0}$.
- **Gate:** median $e$ ≤ 1.0° (2–5 s) and ≤ 2.0° (5–15 s), pooled and in ≥ 4/5 animals; floor clause < 0.5° excess.
- **Chain models:** per-axis variance $\sigma_\theta^2$ = $\sigma_0^2+(bt)^2$ (L_t, constant bias), $\sigma_0^2+qt$ (RW_t), $\sigma_0^2+(c\Theta)^2$
  (R), combinations and $t_{act}$ versions; Rayleigh likelihood $\ell=\ln(e/\sigma^2)-e^2/2\sigma^2$, fitted on tuning, scored on
  test; 1000-draw block bootstrap (10-min anchor blocks) of the test ΔLL.
- **Increment consistency:** $C_{inc}=|\sum\Delta\boldsymbol\phi|/\sum|\Delta\boldsymbol\phi|$ over ≥ 30-s steps vs randomised directions.
- **Bias residual:** mean calibrated gyro over windows ≥ 10 s minus a leave-window-out running-median bias; tilt and yaw
  components in °/min.
- **Growth law:** Phase-0 `fit_growth` ($\sigma_\theta=\sqrt{\sigma_0^2+(kt)^2}$ on bin medians/1.1774, p90 envelope), t = $t_{act}$ (bouts) or t (chains).

## Deviations

1. Amendment 1 (before any real-data run): the linearity verdict made two-part (shape and driver, each with a
   CI-separated contrast) after the first synthetic self-test showed rotation and time confounded.
2. Amendment 2 (after the tuning-only development pass, before the full run): descriptive additions (net in-window
   rotation, floor by WISER status, rotation-matched comparison with Phase 0) and the exploratory anchor-ZARU chains.
3. Analysis windows 21:00 → 04:20 (Phase 0 used the whole cached night), as specified by the user.
4. The Phase-0 exploratory g-sensitivity models were not refitted.
5. *After the run, report only:* gate bins split by rotation and the error/time table added from the saved outputs;
   per-animal linearity summary added to the headline. No number changed.

## Verification

- `--selftest` ALL PASS (13): strict detector rejects a 2 °/s rotation at constant |a| (Phase-0 rule accepts it) and
  returns one window over a still segment; centre-to-centre removes a planted 7.1° edge bias to 0.003°; anchor-ZARU
  removes a planted constant bias; chained-anchor fits recover a planted bias (b within 25 %, LINEAR IN TIME) and an
  angle random walk (q within 35 %, RANDOM-WALK-LIKE); WISER classes.
- Selection frozen in `selection.json` (08:54:33) before any test period was loaded (08:54:54, log); config `fitted`
  written by the run.
- Day A3 files reproduce the V4 chain: their stored 1-min bias nodes match the exact bias implied by the Phase-0 chain
  (b = w − gyr/1.03) to 0.02–0.20 °/s per-period maximum (nights 0.007–0.50 °/s); the exact bias is what is used.
- No raw file, existing cache file or existing script was modified; the WISER SQLite was opened mode=ro (sha256 prefix
  checked); no images were opened; not committed.
- Suggested human video checks (20 still windows, 20 shake trains, 10 largest-error test bouts with the CH01–CH08 hourly
  file and offset) are listed in the report §10 — not done.
