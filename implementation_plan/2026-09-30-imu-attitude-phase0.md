# Head-IMU attitude, Phase 0: gyro self-calibration, saturation handling, honest attitude-error model, and a pre-registered gate for inertial fusion (cohort 2026c)

- **Status:** approved by the user 2026-09-30 ("phase0 开始"); written **before** coding. Every rule that turns data into
  a choice is fixed here and evaluated on the **tuning night only**; the gate below is evaluated once, on the test night,
  with the thresholds as written.
- **Follows:** the V4 inertial-fusion change log
  [`change_log/2026-09-29-wiser-ins-fusion.md`](../change_log/2026-09-29-wiser-ins-fusion.md), whose final section
  *Audit of the V4 result* (main session, 2026-09-30) measured the root cause of the V4 FAIL: pure-gyro attitude across
  active bouts drifts 0.4–0.5 °/s of activity (median; p90 2.5 °/s), i.e. end-of-bout tilt error 1.8–1.9° (2–5 s bouts),
  2.8–3.9° (5–15 s), 6.7–7.5° (15–40 s) — not the integration rate, not the scalar gyro scale, only partly saturation
  (12/219 bouts, 15–19° when present), scaling with total rotation more than with duration (≈ 1.0–1.4° per 100° turned),
  error direction not fixed in the head frame. Audit scripts:
  `D:\Field2026_analysis_out\2026c\wiser_ins_fusion_20260930_0016\audit_20260930\coning_test.py` (+ `*_output.txt`).
  This plan **reuses its bout construction and gravity-propagation test** so every number here is comparable.
- **Scope:** IMU only. **No WISER fusion is run.** Phase 0 decides, by the gate, whether inertial fusion with WISER is
  worth attempting at all.
- **Direction:** `wiser_baseline` (a measurement question; no behavioural claim).
- **Code (new):** `wiser/scripts/analyze_imu_attitude_phase0.py` (base Python: numpy/scipy/pandas/numba/matplotlib;
  `--selftest` on synthetic data). Existing code is **imported, never edited** (`ephys/make_imu.py`, `ephys/read_imu.py`,
  `wiser/scripts/build_imu_wiser_cache.py`, `wiser/scripts/analyze_wiser_ins_fusion.py` for the Hampel filter and the
  cache loaders).
- **Config:** `wiser/configs/imu_attitude_phase0_2026c.json` (inputs, rules, thresholds; the run writes the fitted
  per-animal matrices into `fitted`, marked "fitted on 2026-09-08/09").
- **Outputs:** bulk `D:\Field2026_analysis_out\2026c\imu_attitude_phase0_<ts>\` (per-bout, per-floor-pair, per-saturation-run
  and per-second CSVs, fits, figures, `summary.json`, `log.txt`); the **A4 cache**
  `D:\Field2026_analysis_out\2026c\imu16_cache\<SFxx>\night_<date>.npz` + `README.md` next to the cache root; report
  `results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_phase0_2026c.md`, figures on the same stem under
  `results/2026c/wiser_baseline/figures/`, pointer `run_manifest_imu_attitude_phase0_2026c.json` (the folder's
  `run_manifest.json` is never touched); `change_log/2026-09-30-imu-attitude-phase0.md`.
- **Rules of this run (user):** never open or judge images; raw drives read-only; use the caches (A1, A3), never re-read
  `E:`; do not edit existing analysis scripts; no git commit; tune only on the tuning night; report pass/fail honestly.
  Runtime target ≤ 2 h.

## Inputs (all cached, read-only)

- **A1** `D:\Field2026_analysis_out\2026c\imu_raw_cache\<SFxx>\<session>__<start>_<end>.npz`: int16 `six` (n, 6) =
  analogin lanes 1–6 at 1250 Hz in the **sensor frame** (acc x/y/z, gyro x/y/z), `sat` (n, 6) = |raw| ≥ 32700, `frozen`,
  `fit_json`, `meta_json`. Units: acc = raw/32768 · 8 · 9.81 m/s², gyro = raw/32768 · 2000 °/s. Sensor → head map
  `S` (`ephys/make_imu.py`): v_B = S v_H, head x nose / y left / z up; sensor lane 4 (gyro x) = head z (yaw).
- **A3** `D:\Field2026_analysis_out\2026c\imu100_cache\<SFxx>\night_<date>.npz`: 100 Hz `t_unix_ms` (IMU clock;
  `t100[i]` = A1 frame 12.5 i, verified to < 0.4 ms), `acc` (calibrated: ellipsoid a_cal = D(a − o), head frame, m/s²),
  `gyr` = 1.03 · (w_lp − b) °/s head frame (Hampel → 40-Hz Butterworth-4 zero-phase → resample_poly 2/25; running-median
  bias b), flags `quiet` (make_imu 1-s rule: median |ω| < 10 °/s, | k_a·median|a| − g | < 0.05 g, not bad), `sat_gyr`,
  `frozen`, `calib_json` (`acc.D`, `acc.o`, `bias_nodes_1min` = b at 1-min nodes, head frame, °/s, pre-scale).
- Animals SF07 SF08 SF09 SF10 SF12; **tuning night** `night_20260908` (2026-09-08/09), **test night** `night_20260910`
  (2026-09-10/11). Whole cached window (20:50 → 05:30) as in the audit.

## Gyro chain of this phase (the "calibrated pipeline")

From A1, per animal-night: counts → Hampel per lane (V4 `_hampel_lanes`, half-window 3, 6 σ, floor = lane noise SD;
saturated samples never replaced) → **saturation reconstruction** on the gyro lanes (0c, raw domain) → °/s → 40-Hz
Butterworth-4 zero-phase → resample_poly(2, 25) → 100 Hz → head frame → **− b** (A3 1-min nodes, linear interpolation)
→ **ω = M (w − b)** (0b). With reconstruction off and M = 1.03 I this reproduces A3 `gyr` (checked, reported as the max
absolute difference on non-saturated samples). The **audit baseline** is A3 `gyr` itself (= the audit's `lp100_s1.03`).

## Bout construction and the gravity-propagation test (reused from the audit, unchanged)

- Bout = maximal run of non-`quiet` 100-Hz samples [a, b) with 2 ≤ (b − a)/100 ≤ 90 s, a ≥ 50, b + 50 ≤ n.
- $\hat{\mathbf g}_{start}$ = normalised mean of A3 `acc` over [a − 50, a) (the 0.5 s before), $\hat{\mathbf g}_{end}$ over
  [b, b + 50).
- Propagation in the head frame at 100 Hz: $\mathbf g_{k+1} = \mathrm{Exp}(-\boldsymbol\omega_k\Delta t)\,\mathbf g_k$
  (Rodrigues), $\Delta t$ = 0.01 s.
- **End-of-bout tilt error** $e = \angle(\mathbf g_{prop}(b), \hat{\mathbf g}_{end})$ in degrees; error vector
  $\boldsymbol\varepsilon = \mathbf g_{prop} - \hat{\mathbf g}_{end}$ (head frame).
- Per bout also: duration, `sat_gyr` (any raw gyro lane |raw| ≥ 32700 inside [12.5a, 12.5b)), `sat_acc`, `frozen`,
  $\omega_{max}$, total rotation $\Theta=\sum|\boldsymbol\omega_k|\Delta t$ (°), acc deviation median | |a| − g |,
  high-frequency gyro/acc power (raw 1250 Hz, > 20 Hz), mean horizontal specific force $\overline{|\mathbf a_h|}$ (using
  the propagated attitude).
- Duration bins 2–5, 5–15, 15–40, 40–90 s. **Gate bins: 2–5 and 5–15 s; gate bouts: no gyro saturation.**

## Tasks (each quantity gets formula + text in the report)

### 0a. Measurement floor of the test
- Quiet runs = maximal runs of `quiet` samples free of `sat`/`frozen`. For window length L ∈ {0.5, 1, 2} s, consecutive
  non-overlapping window pairs inside a quiet run: $\varphi_L=\angle(\bar{\mathbf a}_{w_1},\bar{\mathbf a}_{w_2})$, the
  angle between the gravity directions of two **adjacent** quasi-static windows with no motion between (equivalently one
  2L window split in two). Report median / p90 per animal-night and pooled; the L = 0.5 s median is **the floor the gate
  is read against** (the gate test uses 0.5-s start/end windows).
- Supplement: the same test with a quiet gap d ∈ {1, 2, 5} s bridged by the calibrated gyro (floor + still-drift).
- Caveat stated in the report: the floor is measured at one orientation and excludes accelerometer-calibration residuals
  between different orientations (A3 held-out gravity residual 0.016 m/s² ≈ 0.1°); it is a lower bound of the test noise.

### 0b. Gyro self-calibration, per animal
- Model 1 (**M**): $\boldsymbol\omega = M(\mathbf w-\mathbf b)$, $M = I + E$, $E\in\mathbb R^{3\times3}$ free (9
  parameters: per-axis scale, non-orthogonality, gyro-to-accelerometer misalignment); $\mathbf b$ = the existing
  running-median bias (not refitted).
- Model 2 (**M + rate**): $\boldsymbol\omega = \big(1 + c\,|\mathbf w-\mathbf b|^2/\omega_0^2\big)\,M(\mathbf w-\mathbf b)$,
  $\omega_0$ = 1000 °/s, one extra scalar c.
- Nested references: model 0 scalar s (1 parameter; s = 1.03 is the audit baseline), model D diagonal (3).
- **Fit set:** tuning-night bouts, 2–15 s, no gyro saturation, no frozen samples. **Objective:** Huber-robust sum of
  squared gravity-mismatch vectors, $\sum_i \rho\big(\boldsymbol\varepsilon_i(\theta)/f\big)$ with scipy
  `least_squares(loss="huber", f_scale=1)` on residuals $\boldsymbol\varepsilon_i/f$, $f$ = 3° = 0.0524 rad (bouts with
  error below ~3° count quadratically, larger ones linearly); start $E = 0.03I$, $c = 0$; bounds |E_ij| ≤ 0.3, |c| ≤ 1.
- **Model selection (tuning night only):** 2-fold CV by alternating 10-min blocks of bout start time; the selected model
  is the one with the lowest pooled (5 animals) held-out median tilt error on 2–15 s bouts; if two are within 0.05° the
  simpler one is taken. The selected model, refitted on all tuning bouts per animal, is the calibrated pipeline for 0c–0e
  and the gate. All four models are still reported on the test night.
- **Uncertainty:** 200 bootstrap resamples of the fit bouts → 2.5/97.5 percentiles of every entry of M (and c).
- **Report:** M per animal with CIs; per-bin median/p90 tilt error on the **test night**, audit baseline → calibrated,
  per animal and pooled; drift scaling after calibration (Spearman of e with Θ vs duration; ° per 100° turned; ° per s);
  and the rectification test: Spearman of the per-bout drift rate e/dur with the high-frequency gyro power, the
  high-frequency acc power, and $\overline{|\mathbf a_h|}$. Reading rule stated in advance: error still ∝ rotation →
  calibration incomplete; ∝ duration and correlated with vibration power → rate-independent (rectified) bias.

### 0c. Saturation (amended 2026-09-30 before coding, after the coordinator's literature audit — see *Prior work*)
- Clipped run = consecutive raw samples with |raw| ≥ 32700 on one gyro lane. Per run: lane, start time, duration (samples,
  ms), sign, entry/exit slope (linear fit over the 4 unclipped samples on each side, °/s per ms), max |ω| of the other two
  gyro lanes, accelerometer |a|_max within ±10 ms (in g), acc saturation within ±10 ms, the acc spectral width
  $W_{acc}$ = fraction of the acc power in 100–625 Hz within ±40 ms (mean removed), and the **train structure**: runs on
  the same lane whose onsets are ≤ 70 ms apart form a train; per run the spacing to the previous/next run (ms), the train
  size, and whether the sign alternates with the neighbours.
- **Classification rule (stated now, in this priority order):**
  1. `impact` — an accelerometer lane clipped (±8 g) within ±10 ms of the run.
  2. `shake_train` — the run belongs to a train of ≥ 2 runs with onset spacing 25–70 ms (14–40 Hz: wet-dog shakes,
     head twitches) and alternating sign between consecutive runs (≥ 50 % of the successive pairs). Real, zero-mean head
     oscillation; the accelerometer flag `acc_gt_2g` (|a|_max > 2 g during the train) is reported, not required.
  3. `short_broadband` — duration < 4 samples (3.2 ms) and $W_{acc}$ ≥ 0.5 (a broadband transient; MEMS gyros largely
     reject common-mode linear shocks, so this class is expected to be small).
  4. otherwise isolated: after reconstruction, the **implied net rotation** of the lane over the run ± 25 ms is computed;
     `suspect_monotone` if it is ≥ 60° with |a|_max < 2 g (no rodent study reports a voluntary monotone flick of this size
     in < 50 ms → headstage/loosening artefact suspected; SF12's loosening contact 09-10/11 is checked by comparing its
     counts), else `rotation`.
  The 2-D feature distributions (duration × $W_{acc}$, spacing histogram in 0–25/25–40/40–70/70–200/> 200 ms bins,
  |a|_max during runs) and per-night counts per class are reported so the rule can be judged.
- **Reconstruction (all runs except `impact` and `short_broadband`):** log-quadratic (Gaussian-shaped)
  $\ln|\omega(t)|=p_0+p_1t+p_2t^2$ least-squares through the 4 + 4 unclipped shoulder samples (a prototype on synthetic
  Gaussian / raised-cosine / asymmetric pulses recovered 99–125 % of the missing angle, the plain quadratic only
  50–90 %); accepted when $p_2<0$, the extremum lies inside the run ± 1 sample, and the peak is ≤ 3 × the rail
  (6000 °/s); clipped samples are replaced by the fit (never below the rail); **missing angle**
  $\Delta\theta=\sum(|\hat\omega_k| - \omega_{rail})\Delta t$ (°). Otherwise the clipped value is kept and the run is
  flagged `recon_failed`. `impact` / `short_broadband` runs keep the clipped value.
- **Per train:** the net integrated angle of the reconstructed lane over the train span (first onset − 25 ms → last end
  + 25 ms), expected near 0 for a shake.
- **Evaluation:** tilt error on the bouts **with** gyro saturation (both nights, all animals), per bout and by the classes
  the bout contains, for three treatments: (i) clipped as is, (ii) reconstructed, (iii) reconstructed + attitude frozen
  (ω := 0) across `shake_train` spans. **A4 uses (ii)** (fixed now); (iii) is reported as the alternative.
- **Per-second tables** (per animal-night CSV): saturated gyro/acc samples per second, max |ω| (100 Hz calibrated),
  max unclipped raw |ω|, quiet fraction, runs per class; the distribution of per-second max |ω| by activity (quiet vs
  active), the percentiles (p50/p90/p99/p99.9/max) of per-sample |ω| in active seconds, the largest |ω| seen with no
  lane saturated — set against the literature values in *Prior work*.

### 0d. Attitude pipeline at 100 Hz → A4 cache
- Quaternion $q$ (world ← head) integrated at 100 Hz with the calibrated gyro:
  $q_{k+1}=q_k\otimes\mathrm{Exp}(\boldsymbol\omega_k\Delta t)$; yaw initialised to 0 and never corrected (**arbitrary
  but continuous**; it drifts with the residual bias).
- **Gravity aiding only in `quiet` samples**: tilt correction toward the measured direction with gain $k=\Delta t/\tau$,
  $\tau$ = 0.25 s (after one quiet second the tilt error is reduced by e⁻⁴); **no dynamic pull** in non-quiet samples.
  Initial tilt from the first quiet second.
- Saturation handled per 0c (reconstructed rotation runs; shock runs kept and flagged). Frozen samples: attitude held,
  flagged `invalid`.
- World-frame specific force $\mathbf f = R(q)\,\mathbf a_{cal} - g\,\mathbf e_z$; **f_xy** = its horizontal components,
  low-passed (Butterworth-4 zero-phase) at 2 Hz, also 1 and 4 Hz, and decimated 100 → 16 Hz (resample_poly 4/25).
- **A4** `D:\Field2026_analysis_out\2026c\imu16_cache\<SFxx>\night_<date>.npz`: `t_unix_ms` (16 Hz, IMU clock),
  `f_xy_2hz`, `f_xy_1hz`, `f_xy_4hz` (n, 2) float32 m/s², `f_z_2hz`, `q_wh` (n, 4) [w, x, y, z] nearest 100-Hz sample
  (≤ 5 ms), `sigma_theta_deg` from 0e, `t_active_s`, flags `still`, `dyn`, `sat`, `recon`, `shake`, `frozen`, `invalid`
  (any within the 62.5-ms support), **behaviour-band powers** `bp_w_<band>`, `bp_a_<band>` for the bands 2–4, 4–8, 8–12,
  12–20 Hz (Butterworth-4 zero-phase band-pass of the 100-Hz |ω| and |a| norms, squared, 0.5-s centred mean, sampled on
  the 16-Hz grid; (°/s)² and (m/s²)²; a motion-state feature for a later classifier — never to be integrated), `calib_json`,
  `meta_json`. Format documented in the report and in a README next to the cache root. The 2-Hz default follows the
  literature (≤ the UWB Nyquist 1.75 Hz at 3.5 fixes/s; the validated tilt band); 1 and 4 Hz are kept as variants.

### 0e. Attitude-error growth model
- From the **test-night** calibrated no-saturation bouts (5 animals pooled, 2–90 s) plus the floor at t = 0: bin by
  duration (edges 0, 2, 3, 4, 5, 7, 10, 15, 22, 30, 45, 60, 90 s; bins with ≥ 15 bouts), median and p90 tilt error per bin.
- $\sigma_\theta$ = per-axis SD of the 2-D tilt error, median angle = 1.1774 σ (Rayleigh).
  Fit **model A** $\sigma_\theta(t)=\sqrt{\sigma_0^2+(k\,t)^2}$ and **model B** $\sigma_0 + k\,t$ to the bin medians
  (weights √n), and the **p90 envelope** $p_{90}(t)=\sqrt{p_0^2+(k_{90}t)^2}$. Model A is the law written into A4
  (`sigma_theta_deg` at each sample's $t_{active}$ = seconds since the last quiet sample); both fits and per-animal fits
  are reported. This is the process-noise law a future filter must use.

## GATE (pre-registered; evaluated once, on the test night)

Test night 2026-09-10/11, **no-saturation bouts, calibrated pipeline (the model selected on the tuning night), median
end-of-bout tilt error**:

- **2–5 s bouts ≤ 1.0°** AND **5–15 s bouts ≤ 2.0°**, both pooled over the 5 animals **and** in ≥ 4 of 5 animals
  individually.
- The floor from 0a (L = 0.5 s median) is reported next to it. If the gate is missed but the excess over the floor is
  < 0.5° in the failing bin, the report says so (the test, not the gyro, is at its limit). The thresholds are not moved.
- Verdict **PASS / FAIL** with the numbers. Bootstrap CIs of the pooled medians are reported for information only.

## Amendments during development (2026-09-30, before the full run; after a single-animal SF09 development pass)

1. **The IMU lanes are sample-and-hold.** All six analogin lanes update ≈ 190 times per second (hold 5–7 logger samples,
   ≈ 6.6 on average, ≈ 5 % of updates skipped; acc and gyro synchronous; measured on SF09 09-08 and SF12 09-10). A
   "clipped run" of the median 7 raw samples is therefore **one clipped gyro reading**, and the 4 + 4 raw shoulder
   samples collapse onto two constant levels. Shoulders, entry/exit slopes and the log-quadratic reconstruction now
   operate on **held readings** (reading centres, 4 + 4 readings ≈ ±21 ms); `short_broadband` is re-expressed as a
   single clipped reading (≤ 1 reading) with $W_{acc}$ ≥ 0.5; runs carry `n_readings`. Nothing else in the rule changes.
2. **Bias taken exactly as A3 applied it.** The Phase-0 chain without reconstruction is A3's chain, so
   $\mathbf b = \mathbf w - \mathbf w^{A3}/1.03$ at every sample; the 1-min bias nodes stored in A3 are only a sampled copy
   (their interpolation error, up to ≈ 0.3 °/s, is reported instead of being introduced).
3. **Post-hoc exploratory models (not in the selection, not in the gate):** on SF09's tuning night the drift *rate*
   correlated with the mean horizontal acceleration (Spearman 0.57) more than with the high-frequency power (0.30), which
   is the signature of gyro g-sensitivity rather than vibration rectification. Two exploratory models
   $\boldsymbol\omega = M(\mathbf w-\mathbf b) + K\mathbf a$ (`scalar_gsens`: s + K, 10 parameters; `M_gsens`: E + K,
   18) are fitted and cross-validated exactly like the registered ones and reported on the test night, **clearly labelled
   post-hoc**; the pre-registered selection is restricted to scalar / diag / M / M_rate, and the gate uses the selected
   registered model. (The SF09 test-night numbers had been seen when this was added; the gate rule was not touched.)
4. **Edge-window motion diagnostic (post-hoc, descriptive):** per bout the integrated |ω| over the two 0.5-s gravity
   windows (`edge_rot_deg`) is stored so the report can show whether residual head motion inside the "quiet" edge windows
   limits the test.
5. Treatment (iii) (attitude frozen across shake trains) is kept as a reported alternative only; on SF09 it was much
   worse than (ii) because shake trains carry a non-zero net rotation (median |net| ≈ 11°).
6. **Reconstruction shoulders = the 2 innermost held readings per side** (fallback 3 + 3): on synthetic sample-and-hold
   pulses (Gaussian and half-sine, peaks 2200–4000 °/s, hold 6–7) the 4 + 4 outer readings lie in the pulse tails and the
   log-quadratic then under-reaches the rail; with 2 + 2 the recovered/true missing angle is median 1.00 (p10 0.92,
   p90 1.9, 15 % rejected), the plain quadratic 0.7–0.85. Decided on synthetic data only.
7. **Post-hoc edge-still diagnostic for the gate (declared here after the SF09 development pass, before the full run):**
   the registered test does not propagate the gyro through its own 0.5-s gravity windows, which lie in "quiet" seconds
   that may still contain slow head motion (SF09 test night: median integrated |ω| in the two edge windows 8°,
   Spearman(e, edge motion) 0.73; bouts with edge motion below the median: 0.57° / 1.72°). The report therefore adds
   the gate numbers on the subsets `edge_rot_deg` < 2° and < 1°, labelled post-hoc; **the verdict is still the
   registered test.** The p90 growth-envelope fit is anchored at the floor's p90 at t = 0.

## Prior work folded in (coordinator's literature audit, 2026-09-30; before coding 0c/0d)

- Rat **voluntary** head turns peak ≈ 500 °/s with 30–50° displacement; free ambulation SD|ω| ≈ 107 °/s; immobility
  < 12–20 °/s (Pasquet et al. 2016, Sci Rep, https://www.nature.com/articles/srep35689). No rodent study reports a
  monotone ≈ 100° flick in 40 ms.
- **Oscillatory** behaviours do reach > 2000 °/s for tens of ms: wet-dog shakes at 14–18 Hz (Dickerson et al. 2012,
  https://pubmed.ncbi.nlm.nih.gov/22904256/; DISSeCT 2025, PLOS Biol, > 1000 °/s and > 2 g in rats,
  https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3003431), head twitches 30–40 Hz (Halberstadt &
  Geyer 2013), scratching 7–12 Hz; comparative bounds marmoset > 1000 °/s, lovebird saccades up to 2700 °/s in 30–45 ms.
- MEMS gyros cancel common-mode linear shocks (a shock hits the accelerometer, not the rate output); a loosening
  headstage produces genuine sensor rotation that the skull does not share → the `suspect_monotone` class above.
- Translation channel: a 1.5–2 Hz zero-phase low-pass is the validated gravity/tilt band (Pasquet 2016; Fayat et al.
  2021) and ≤ the UWB Nyquist; the 2–20 Hz band (locomotion 4–8 Hz, grooming ≈ 4 Hz, sniffing 8–12 Hz, shakes 14–18 Hz)
  is behaviour → A4 band-power columns, never integrated.
- Grooming / scratching / shaking epochs are **not excluded** anywhere in Phase 0; the report notes that the body is
  stationary in them, so a translation filter should treat them as zero-velocity states.
- The gate is unchanged by this audit.

## Self-test (`--selftest`, synthetic data, no field data)

1. Known $M$ (E entries up to ±0.05) and rate term recovered from synthetic bouts with the bias known (|Ê − E| < 0.005,
   |ĉ − c| < 0.02); the post-calibration tilt error falls to the injected end-window noise.
2. Saturation: a synthetic isolated Gaussian pulse (peak 3000 °/s, clipped at 2000) is classified `rotation` and its
   missing angle recovered within 25 %; a synthetic 15-Hz alternating train is `shake_train` with a near-zero net angle;
   a 1-sample spike with broadband acc is `short_broadband`; a clipped run coincident with acc clipping is `impact`.
3. Floor: synthetic quiet acc with known noise gives the theoretical median floor within 15 %.
4. Attitude pipeline: on synthetic motion with known attitude the tilt error stays small with quiet-window aiding, and a
   known 1-Hz horizontal acceleration appears in `f_xy_2hz` (amplitude within 10 %).
5. Growth-law fit recovers known σ₀, k.

## Deliverables and bookkeeping

- Plan (this file) + top row in `implementation_plan/README.md`; after the run: `change_log/2026-09-30-imu-attitude-phase0.md`
  + top row in `change_log/README.md`; only the `wiser_baseline` row of CLAUDE.md's WISER table is edited (mention the
  A4 cache). Both index files are re-read right before editing.
- Deviations from this plan are listed in the report's *Deviations* section and in the change log.
