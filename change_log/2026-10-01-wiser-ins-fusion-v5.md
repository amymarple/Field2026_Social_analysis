# Head-IMU inertial fusion with WISER, V5: Stage-A attitude outside the filter + 16-Hz EKF/RTS — **FAIL** (cohort 2026c) — 2026-10-01

- **Plan:** [`implementation_plan/2026-10-01-wiser-ins-fusion-v5.md`](../implementation_plan/2026-10-01-wiser-ins-fusion-v5.md)
  (approved by the user 2026-10-01 "start v5"; pre-registered before any test-period computation; amendments 1–8 in its §11,
  written after tuning-only development runs and a tuning-only dry run of the whole pipeline, before any test period was read).
- **Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_ins_fusion_v5_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_ins_fusion_v5_2026c.md)
  (full Definitions, Stage-A validation, measured noise model, ψ regression, tuning, per-scheme / per-animal / per-subset tables,
  NIS and held-out z², plausibility, interpretation, deviations); figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_ins_fusion_v5_{stage_a,heldout,tuning,by_mode,example}_2026c.png`;
  pointer `results/2026c/wiser_baseline/reports/run_manifest_ins_fusion_v5_2026c.json` (the folder's `run_manifest.json` is untouched).
- **Bulk:** `D:\Field2026_analysis_out\2026c\wiser_ins_fusion_v5_20261001_1325\` (1.9 GB): `stage_a_decisions.json` (frozen
  13:27:58), `tuned_frozen.json` (frozen 14:01:58, before the test periods were read), `noise_model.json`, `csv/` (Stage-A windows,
  LWO, bout test, |f_xy| by time since a window, ψ regression, handedness votes, the 161-configuration tuning grid, every held-out
  error of every method and scheme, bootstrap comparisons, NIS / z², plausibility), `fusion/<period>/<SFxx>/v5_full.npz`
  (smoothed states, (p+d) covariances, innovations/NIS, IRLS weights, INS/CV mode, log-likelihoods; p90 and mirrored-frame runs) and
  `v5_heldout.npz` (hidden masks + predictions/variances of V5, V5 + 1 h, V5_p90, V5_unc per scheme), `summary.json`,
  `input_provenance.json`, `log.txt`. Runtime 55.1 min.
- **New reusable cache:** `D:\Field2026_analysis_out\2026c\attitude16_cache\<SFxx>\<period>.npz` (20 files, 654 MB incl. the
  window tables and the day per-second tables) + `README.md` — Stage-A attitude, world-frame f_xy (2 Hz, 16 Hz), time since a strict
  window, σθ (median and p90 laws), flags, band powers, VeDBA; `<period>_windows.csv.gz` (ZARU and anchor biases, closures);
  `day_<date>_imu_seconds.csv.gz` (cache-equivalent per-second IMU tables).

## What changed

- New `wiser/scripts/analyze_wiser_ins_fusion_v5.py` (base Python + numba; `--selftest` ALL PASS, 10 checks in 18 s;
  `--roles tuning`, `--report-only <run_dir>`). Imports, unmodified: `analyze_wiser_imu_smoothing` (Track, hidden sets,
  B1/B2/B2′/V1/V2, `boot_delta`, `track_metrics`, `kf_run`), `analyze_wiser_ins_fusion` (context, per-second IMU tables),
  `analyze_imu_attitude_phase0` (quaternion kernels, bout propagation), `analyze_imu_attitude_gate_v2` (`process_period`,
  `detect_strict`, `make_bouts`), `analyze_imu_wiser_calibration`, `make_imu`.
- New config `wiser/configs/wiser_ins_fusion_v5_2026c.json` (periods, every rule and grid; the run wrote `tuned` and `fitted`).
- Inputs: caches only (A1, A3 incl. day files, A2) + the make_imu 50-Hz npz for the pilot's night per-second tables. No raw read,
  no SQLite opened, no image opened, no existing script or cache modified, not committed.

## Results

**Verdict (pre-registered, test night 2026-09-10/11): FAIL.** Held-out WISER fixes with ≥ 7 anchors (pooled, 5 animals; Δ =
1 − med(V5)/med(ref), 95 % 5-min-block bootstrap CI):

| scheme | B2′ median (in) | V2 | V5 | V5 vs B2′ | V5 vs V2 | V5 (IMU + 1 h) vs B2′ |
|---|---|---|---|---|---|---|
| (s) single fix | 3.50 | 3.45 | 3.47 | +0.8 % [+0.4, +1.2] | −0.5 % [−0.9, −0.2] | −5.5 % [−6.6, −4.4] |
| (g) 0.5-s gaps | 3.70 | 3.66 | 3.66 | +0.9 % [+0.3, +1.5] | −0.2 % [−0.7, +0.2] | −5.7 % [−6.9, −4.4] |
| (g) 1.0-s gaps | 3.85 | 3.79 | 3.80 | +1.2 % [+0.5, +1.7] | −0.3 % [−0.9, +0.1] | −5.7 % [−7.1, −4.3] |
| (a) runs of 4–8 | 3.93 | 3.86 | 3.86 | +1.7 % [+1.2, +2.2] | −0.1 % [−0.5, +0.3] | −5.4 % [−6.2, −4.5] |
| (a′) 2-s windows | 4.19 | 4.12 | 4.14 | +1.4 % [+0.6, +2.0] | −0.4 % [−1.0, +0.3] | −5.8 % [−7.1, −4.7] |

- **(i) primary:** 0/5 animals eligible (Δ ≥ 3 % vs both B2′ and V2) on (s) or (g-0.5 s); per-animal V5 vs V2 on (s) −1.1 … −0.3 %;
  Holm scheme statistics 1.000 / 1.000. (ii) control no gain 5/5; (iii) pooled moving Δ +0.6 % vs B2′, −0.7 % vs V2 (both within
  −2 %). B2′/V2/B1 reproduce the smoothing pilot on (a)/(a′) (B2′ (a) 3.93 in, V2 +1.7 %).
- **Where V5 differs from V2 (test night):** INS-mode fixes +1.5 % (s) / +1.9 % (g-0.5) on 11 % of fixes — 92 % of them IMU-still; only
  0.3 % of locomoting and 1.1 % of moving fixes are in INS mode; CV-mode fixes −0.8 % / −0.7 %. The IMU helps by certifying stillness,
  not by bridging motion. V5 vs its +1 h control +6.0 % / +6.2 %, but the shifted IMU is harmful (−6.9 % vs V2), so that contrast
  measures damage by a wrong IMU, not information.
- **Test day 2026-09-11 (secondary; INS mode on 88 % of fixes, mostly sleep):** V5 vs B2′ +2.7 % [+2.2, +3.0] (s), +4.0 % [+3.5, +4.6]
  (g-0.5); vs V2 +1.3 % [+0.9, +1.7] / +2.2 % [+1.8, +2.8]; largest per-animal vs V2 on the primary schemes +2.6 % (all schemes:
  +3.5 %, SF10 g-1.0). The +1 h control also beats B2′ (+1.0 % / +2.2 %) → the control criterion fails on the day; V5 vs control
  +1.6 % / +1.9 %; the gain is on IMU-still fixes (+1.7 % vs V2), not moving ones (−1.0 %). The same rule would read FAIL.
- **Stage A validation (IMU only):** bias rule `smoothed` (tuning leave-window-out medians raw 0.087°, smoothed 0.051°, A3 0.051°);
  ML anchor smoother q_b 2.1–3.3 × 10⁻⁶ (°/s)²/s, σ_r 0.12–0.16 °/s·s (1/d micro-rotation term dominates), σ_w → 0. Gate-v2 bout test
  on the test periods (L1.0 set): the A3 stream reproduces gate v2 exactly (0.30° / 0.62°); the anchored bias gives **0.16° / 0.36°**
  (15–40 s 1.36° → 0.82°, 40–90 s 2.56° → 1.54°). LWO tilt error at withheld test windows: median 0.054°.
- **But the night is unanchored:** median time since a strict window on the test night 1,713–3,484 s per animal; 60 % of night samples
  are > 30 min from one. Test-night median |f_xy| 0.007 m/s² inside windows, 0.30 at 30–60 s, 1.17 at 60–120 s, 3.4 at 2–5 min,
  5.8 at 10–30 min, 8.1 beyond (gravity leakage of tens of degrees of tilt); the gate-v2 law predicts 0.32 (60 s) and 1.38 m/s² (300 s).
- **ψ (yaw offset) unobservable:** regression resultants 0.004–0.150 (median 0.062; +1 h null 0.042); handedness votes 6 normal / 4
  mirrored → normal; test LLR −0.0001 … +0.0036 nats/fix (≈ 0).
- **Measured WISER noise (tuning):** night — slow share 9.7 % / 4.7 % < 10 % → no drift state, white SD at 9/8/7 anchors x 1.41/1.76/2.41,
  y 2.51/3.00/3.37 in; day — drift kept (σ_d 0.46/0.72 in, T_d 22.8 s), white x 1.32/1.64/1.91, y 2.26/2.72/3.05 in.
- **Tuning (tuning night + day only):** σ_res 8 in/s², τ_b 2 s, T_max 15 s, σ_v 0.1 in/s, σ_vr 4 in/s, κ_cv 10 → J 4.988 in, trimmed NIS
  2.80. All 161 configurations had NIS in [1.5, 3.0] (2.26–2.97): the constraint was not binding and V5_unc = V5. Grid edges: τ_b, T_max,
  κ_cv, σ_v (the 30 best configurations differ in J by < 0.011 in).
- **Consistency / plausibility (test night):** trimmed NIS 3.00–3.26 (untrimmed 4.7–5.3; 6.7–8.3 % > 13.82), held-out z² mean (s)
  5.3–5.8 → V5's predictive variance is ≈ 2.7× too small at night (test day 3.0–3.6). Path length of the V5 position track 7,420 in/h
  (B2′ 5,715, V2 5,704, raw 18,210); tails equal to B2′ (> 100 in: 0.003 %). V5_p90 ≈ V5.

## Headline definitions (mirrored from the report §2)

- **Strict still window** (gate v2, **no WISER veto**): ≥ 1 s of 0.1-s blocks whose accelerometer directions stay < 0.3° from the window
  mean, $\big||\bar{\mathbf a}|-g\big|<0.03g$, $|\boldsymbol\omega^{A3}|<3$ °/s. **ZARU** $\hat{\mathbf b}_i$ = mean pre-bias gyro in window $i$.
  **Anchor smoother:** per head axis $b_{i+1}=b_i+\eta$, $\mathrm{Var}\,\eta=q_b\Delta c$; $\hat b_i=b_i+\epsilon$,
  $\mathrm{Var}\,\epsilon=\sigma_r^2/d_i^2+\sigma_w^2/d_i$; Huber Kalman + RTS, parameters by ML on the tuning windows; bias = linear
  interpolation of the anchors in clock time.
- **Stage-A attitude:** $q_{k+1}=q_k\otimes\mathrm{Exp}(s_a(\mathbf w_k-\mathbf b(t_k))\Delta t)$; tilt set from the window gravity at
  window centres, closure $\boldsymbol\delta$ distributed linearly in time between centres. $\mathbf f_{xy}=[R(q)\mathbf a-g\mathbf e_z]_{xy}$,
  2-Hz zero-phase low-pass, 16 Hz. **Text:** horizontal head acceleration in a world frame with arbitrary, drifting yaw.
- **σθ law** $\sigma_\theta(t)=\sqrt{0.78^2+(0.0227t)^2}$° ($t$ = s since the last strict window; median tilt $1.1774\sigma_\theta$).
- **LWO tilt error** $e_j=\angle(R(q_{c_j})^\top\mathbf e_z,\hat{\mathbf g}_{W_j})$ at windows withheld from anchors and closures.
- **V5 (Stage B):** state $[\mathbf p,\mathbf v,\mathbf b,\psi,\mathbf d]$; INS mode ($t_{since}\le T_{max}$, IMU ok)
  $\dot{\mathbf v}=R(\psi)\mathbf f_{xy}-\mathbf b+\mathbf w$, PSD $\sigma_{res}^2/16$; $\mathbf b$ Gauss–Markov ($\tau_b$, stationary SD
  $g\sin\sigma_\theta$); CV mode PSD $\kappa_{cv}q\,m_c$ (V2's $q$, multipliers); $\psi$ random walk with
  $\dot{\mathrm{Var}}=\max(0.0309\ \mathrm{deg^2/s},2k^2t_{since})$; WISER $\mathbf z=\mathbf p+\mathbf d+\boldsymbol\varepsilon$ with the
  measured per-anchor white variance; χ² gate + 2 Huber IRLS passes; soft ZUPT ($\sigma_v$ IMU-still, $\sigma_{vr}$ rhythmic). EKF + RTS;
  prediction $\hat{\mathbf z}_h=\mathbf p^s+\mathbf d^s$.
- **Schemes:** (s) every 5th fix hidden alone; (g) all fixes in a random 10 % of 0.5-/1.0-s windows; (a), (a′) as the pilot. Scored fix:
  hidden ∧ anchors ≥ 7 ∧ IMU-QC-ok ∧ shifted-IMU-QC-ok. **Held-out error** $e=\lVert\mathbf z_h-\hat{\mathbf z}_h\rVert$ (in).
- **Δ** $=1-\mathrm{med}(e_M)/\mathrm{med}(e_{ref})$; 1000 paired 5-min-block bootstrap replicates; one-sided
  $p=(1+\#\{\Delta^*\le0\})/1001$. **Holm** over (s), (g-0.5): animal eligible iff Δ ≥ 3 % vs B2′ and V2; $p_a=\max(p_{B2'},p_{V2})$;
  scheme statistic = 4th-smallest $p_a$; thresholds 0.0125 then 0.025. **Control:** V5 with every IMU input from t + 3600 s (days:
  circular); passes iff its CI lower bound vs B2′ ≤ 0 in ≥ 4/5 animals. **Moving fixes:** IMU-QC-ok ∧ not IMU-still.
- **Trimmed NIS** = mean forward pass-0 $d^2=\boldsymbol\nu^\top S^{-1}\boldsymbol\nu$ over visible fixes (anchors ≥ 7) with $d^2\le13.82$
  (≈ 2 if consistent). **Held-out z²** $=(\mathbf z_h-\hat{\mathbf z}_h)^\top(P^s+R)^{-1}(\mathbf z_h-\hat{\mathbf z}_h)$ (mean 2 if consistent).
- **Measured noise:** nugget $\tfrac12(1.4826\,\mathrm{MAD}\,\Delta)^2$ of consecutive same-anchor fixes in still runs; robust variogram of
  9-anchor fixes fit $n+\sigma_d^2(1-e^{-\tau/T_d})$; drift kept iff slow share ≥ 10 % in one axis and $1\le T_d\le120$ s.
- **ψ regression:** $c=\Delta v_W\overline{\Delta v_I}$ over 0.4–0.75-s visible-fix pairs with the IMU within 60 s of a strict window;
  resultant $\bar R=|\sum c|/\sum|c|$ (0 = no consistent direction).

## Deviations (all recorded in the plan §11 before any test period was read)

1. Bias-anchor evidence (ML smoother fit; rule unchanged, chosen `smoothed` by the run).
2. ψ regression restricted to usable pairs within 60 s of a strict window, standard error $1/(\bar R\sqrt{2n_{eff}})$, uninformative ψ₀ if
   no estimate (the whole-night pairs were leakage-dominated and the original SD formula was wrong for a noise-level resultant).
3. ψ process noise follows the clock-time law instead of a constant.
4. κ_cv (CV-mode process-noise multiplier) added to the tuned scalars — motivated by the SF09 development night, where the NIS
   constraint was only reachable by a degenerate configuration; pooled over all tuning animal-periods it turned out not to be binding.
5. V5_unc secondary (identical to V5 here). 6. Development observation (no yaw signal) recorded. 7. Handedness tie rule (not needed:
   6/4). 8. V5 vs V5 (+1 h) secondary comparison and an "inside a window" bin in the |f_xy| table.
- Plan-level: day per-second IMU tables are cache-equivalent (SF12's 09-11 session has no make_imu npz) and the day control is a
  circular +1 h shift (the day caches end 10 min after the window). The (a)/(a′) and B1/B2/B2′/V1/V2 code and tuned values are the pilot's.
- Implementation choice declared in the plan: the specified acceleration-error variance $(g\sigma_\theta)^2+\sigma_{res}^2$ is carried as a
  correlated Gauss–Markov bias (tilt part) + white residual; a V2-like CV fallback where the IMU is unusable.
- Ties in tuning resolved by the registered rule (larger σ_res, then smaller T_max, then grid order; tied J within 0.001 in).

## Caveats

- One test night and one test day (regime B), five animals; WISER frame unverified; held-out targets include WISER's own drift.
- The σθ law (gate v2, ≤ 10-min chains, mostly day records) understates night attitude errors beyond ≈ 1 min by a factor of 3–4.
- V5's predictive variances are too small at night (held-out z² ≈ 5.5): the noise model is static, WISER errors during motion are larger.
- The test day gain over V2 (+1.3–2.6 %) is real but specific to sleep (IMU-still fixes); it does not reach the pre-registered 3 %.

## Verification

- `python wiser/scripts/analyze_wiser_ins_fusion_v5.py --selftest` → ALL PASS (10): Stage A recovers a linear gyro-bias drift (anchor error
  0.004 vs 0.075 °/s drift) and withheld-window tilt (0.18°); the 2-Hz low-pass + rhythmic ZUPT keep a 6-Hz head oscillation on a still body
  from moving the position (0.80 vs 0.56 in); V5 beats B2 on (s) (+4.9 %) and (g-0.5) (+10.9 %); the +1 h control gives no gain; NIS 1.81;
  ψ regression recovers the yaw (2.3°) and the handedness; the noise-model estimator recovers a planted nugget/drift; the bootstrap
  reproduces `boot_delta` exactly; Holm logic.
- A full dry run on tuning data only (tuning day in the test role, two animals, reduced grid, scratch cache/config/report) exercised every
  code path before the real run.
- Stage-A decisions (13:27:58) and Stage-B tuning (14:01:58) were frozen before the test periods were read (log; `stage_a_decisions.json`,
  `tuned_frozen.json`); test-night tracks hold 103,959–105,524 fixes and the recomputed B2′ (a) pooled median is 3.93 in, as in the pilot; the A3 stream reproduces gate v2's 0.30° / 0.62°.
- No raw file, existing cache, SQLite database or existing script was modified; caches only; no images opened; not committed.
