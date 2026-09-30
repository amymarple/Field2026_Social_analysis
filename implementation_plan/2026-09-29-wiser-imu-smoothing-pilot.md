# Can the head IMU improve WISER position accuracy beyond a good position-only smoother? (cohort 2026c pilot)

- **Status:** approved by the user 2026-09-29 ("开始", on the design below); written **before** coding.
- **Direction:** `wiser_baseline` (a measurement question; no behavioural claim).
- **Driver:** `wiser/scripts/analyze_wiser_imu_smoothing.py` (new; `--cohort 2026c`, `--selftest`).
- **Config:** `wiser/configs/wiser_imu_smoothing_2026c.json` (inputs + the tuned values, written after tuning and
  marked "fitted on 2026-09-08/09").
- **Report:** `results/2026c/wiser_baseline/reports/wiser_baseline_imu_smoothing_pilot_2026c.md`, figures on the same
  stem, pointer `run_manifest_imu_smoothing_pilot_2026c.json` (the folder's `run_manifest.json` belongs to the
  accuracy run and is not touched). Bulk: `D:\Field2026_analysis_out\2026c\wiser_imu_smoothing_pilot_<ts>\`.

## Question

Head-IMU + UWB fusion papers report 27–53 % gains, but always against **raw** UWB. The question here is narrower
and harder: after a robust, per-fix-weighted, drift-aware position-only smoother (B2′), does adding head-IMU
information (stillness, motion state, head turn) still reduce the error of predicting held-out WISER fixes?

## Facts this rests on (sources)

- **Tag mounting (user, 2026-09-29):** WISER tag and IMU are on the same rigid headstage → IMU-still ⇒ tag still;
  WISER positions are head positions.
- **WISER:** `D:\Field2026_analysis_out\2026c\wiser_working\3rdcohort_Spike_2026_3_4.sqlite`, table `reports`
  (`location_x/y` in, `anchors_used`, `timestamp` Unix ms UTC on the field-PC clock). Solved positions only (no raw
  ranges); `calculation_error` is a quantized count ratio → not used. Fix intervals bimodal 0.13/0.26 s (~3.5 Hz);
  92 % of rows share a ms timestamp with another tag's row (batch arrival). Duplicate (tag, timestamp) with different
  xy: a rule is fixed below.
- **Static per-axis SD by `anchors_used`** (IMU-still bouts, 09-08/09; x/y in): 9: 1.6/2.9, 8: 2.1/3.7, 7: 2.9/4.7,
  6: 10.6/7.9, 5: 14.6/9.3, 4: 16.5/12.0, 3: 47/37. Head fixes are nearly independent fix to fix (acf 0.11 at lag
  1) but static tags wander slowly (implant acf 0.30 at ~25 s; cohort-1 ground tags 0.20–0.27 at ~100 s); within
  IMU-still bouts the first-half vs second-half WISER shift is 2.4× the shuffled value (p50 0.66 vs 0.28 in) — with
  the tag on the head this is **WISER slow drift**, not body motion. Outliers (> 30 in step within ≤ 0.35 s):
  0.57 % of fixes, clustered, 44 % from ≤ 6-anchor fixes. (Today's exploratory work, main session.)
- **Previous pilot** (`results/2026c/wiser_baseline/reports/wiser_baseline_imu_calibration_pilot_2026c.md`, driver
  `wiser/scripts/analyze_imu_wiser_calibration.py`, config `wiser/configs/imu_wiser_calibration_2026c.json`): WISER
  lags the head IMU by τ* = +0.20/+0.15/+0.10/+0.20/+0.15 s (SF07/08/09/10/12, 09-08/09); IMU-still scatter
  2.39/5.95/4.98 in; IMU-still definition, QC mask and M4 heading statistics are **reused by import**.
  Accuracy report: `results/2026c/wiser_baseline/reports/wiser_baseline_cohort3_accuracy_2026c.md` (walls, bulge,
  regime-A shift; regime-B wall-ridge rectangle in its bulk `csv/c3_wall_ridges_regimeB.json`).
- **IMU:** `D:\3rd_rat_spikes\analysis\imu\<SFxx>\<session>.imu.npz` (50 Hz; `t_pc_ms`, `omega_dps`, `vedba_ms2`,
  `turn_dps` + = CCW from above, pitch/roll, quaternion with relative yaw, `lin_acc_earth_ms2`, QC flags
  saturated/unreliable/quiet_calib/frozen/invalid), regenerated with frozen/invalid flags (commit `6451d6c`). Yaw
  residual drift on still runs p50/p90 0.03/0.11 °/s.
- Tag map `wiser/configs/rat_identities_2026c.csv`; handling windows `cv/configs/cohort3_handling_windows.json`; tag
  silences `…\wiser_cohort3_accuracy_20260928_1405\csv\c3_all_tag_silences_merged.csv`. Current library smoothing:
  `wiser_analysis_utils.add_speed` (centred 7-sample median).

## Prior work (web audit, 2026-09-29)

- UWB+IMU gains of 27–53 % are measured against raw UWB, never against a tuned position-only smoother.
- Robust smoothing with a per-fix error model and outlier handling is expected to give the largest gain: Johnson
  et al. 2008, continuous-time correlated random walk (https://esajournals.onlinelibrary.wiley.com/doi/10.1890/07-1032.1);
  Wen et al. 2021 (https://navi.ion.org/content/68/2/315); Fleming et al. bioRxiv — DOP-type quality numbers can
  mislead (https://www.biorxiv.org/content/10.1101/2020.06.12.130195v2).
- IMU-driven state switching of the movement model: Michelot & Blackwell 2019
  (https://besjournals.onlinelibrary.wiley.com/doi/10.1111/2041-210X.13154).
- The smoothing scale changes speed and distance: Noonan et al. 2019
  (https://movementecologyjournal.biomedcentral.com/articles/10.1186/s40462-019-0177-1); Gupte et al. 2022
  (https://besjournals.onlinelibrary.wiley.com/doi/10.1111/1365-2656.13610).
- Held-out validation of state-space predictions: Jonsen et al. 2020 (https://arxiv.org/abs/2005.00401).
- Head yaw ≠ travel direction: Hou et al. 2020 (https://pmc.ncbi.nlm.nih.gov/articles/PMC7664376/).
- Rat head-acceleration gait bands: Alves et al. 2016 (https://pmc.ncbi.nlm.nih.gov/articles/PMC4976156/).
- No study of head-IMU + UWB on rodents was found.

## Design (pre-registered)

**Animals and tags:** SF07 12409, SF08 12386, SF09 12407, SF10 12395, SF12 12377 (tag table).
**Night window:** 21:00 → 04:20 field-PC local (EDT).
**Tuning night:** 2026-09-08/09 — every hyperparameter, noise model, threshold and lag is fitted here only
(sessions of the previous pilot). **Test night:** 2026-09-10/11, named now. IMU sessions covering it (lane-off
restarts after the ADC-lane night pieces): SF07 `12_20260910_204411.854`, SF08 `2_20260910_210245.604`, SF09
`15_20260910_204912.017`, SF10 `9_20260910_205611.775`, SF12 `15_20260910_210518.445`. SF08/SF12 start at
21:02:45/21:05:18, so their first minutes have no IMU (masked as `nodata`); the `ephys.adc_lane.on_windows` of the
cohort YAML are applied as an extra mask. The tuning-night τ* of each animal is applied on the test night.

**Duplicate rule (decided now):** rows sharing (tag, timestamp) are collapsed to one fix: keep the row with the
largest `anchors_used`; ties → the smallest `reportid`. Reason: a time series needs one fix per timestamp, and the
higher-anchor solve is the more precise one (static SD table). Exact duplicates (same xy) collapse trivially.

**Masks** (as the previous pilot; reused by import): handling ± nothing extra (windows already span Stop → Start),
all-tag silences ± 2 min, tag validity, IMU saturated / unreliable / frozen (flag + derived rule) / invalid / NaN /
nodata, plus the ADC-lane on-windows. Masks decide which **scored** fixes and which **IMU inputs** are used; all
fixes stay available as smoother inputs.

### Methods

All methods run per tag and night on the deduplicated fixes, times shifted by the animal's τ*
($t^{\mathrm{al}}_i=t_i-\tau^*_a$; immaterial for position-only methods).

- **B1 (library):** full-data position = centred 7-sample coordinate-wise median (as `add_speed`). A hidden fix is
  predicted by the coordinate-wise median of the **7 visible fixes nearest in time**.
- **B2 (robust CV smoother):** per axis, constant-velocity (white-noise acceleration, spectral density $q$) Kalman
  filter + RTS smoother; per-fix measurement variance $R_i=\sigma^2_{\mathrm{axis}}(A_i)$ from `anchors_used` $A_i$
  (robust SD = 1.4826·MAD of per-axis deviations about the bout median in tuning-night IMU-still bouts, per anchor
  count; ≤ 3 anchors pooled). Outliers: pass 0 soft χ² gate on the 2-D innovation ($R$ inflated by $d^2/13.8$ when
  $d^2>\chi^2_{2,0.999}=13.8$); passes 1–2 IRLS with Huber weights on the 2-D Mahalanobis smoothed residual
  ($w=1$ for $m\le k$, $k/m$ above, 0 above $m_{\mathrm{rej}}$), $k=2.5$. A hidden fix is predicted by the smoothed
  position at its time (the filter steps through hidden times without an update).
- **B2′ (B2 + slow drift):** measurement = position + per-axis AR(1) drift $b$ (time constant $T_b$, SD $\sigma_b$) +
  white noise with $\sigma^2_w(A)=\max(\sigma^2(A)-\sigma_b^2,\ 0.25\,\sigma^2(A))$; state $(p,v,b)$ per axis. The
  hidden fix is predicted by $\hat p+\hat b$ (the expectation of a measurement); the position output is $\hat p$.
- **V1 (B2′ + zero-velocity pseudo-measurement):** at every time step (visible or hidden) whose aligned second is
  IMU-still, a scalar update $v=0$ with SD $\sigma_v$ (tuned; start ≈ 1 in/s) per axis.
- **V2 (B2′ + IMU-switched process noise):** $q$ per interval from the IMU state of the second containing the
  interval midpoint: still → $m_s q$, active-not-locomoting → $m_a q$, locomoting → $m_l q$, IMU not usable → $q$.
  Locomoting = QC-ok ∧ not still ∧ VeDBA_1s ≥ θ_L ∧ stride-band fraction SBF ≥ ρ_L, where SBF = power of the
  vertical earth-frame acceleration in 4–7 Hz ÷ power in 1–20 Hz over a 2-s Hann window; (θ_L, ρ_L) maximise
  Youden's J against WISER 1-s median speed ≥ 10 in/s (vs < 3 in/s) on the tuning night.
- **V3 (heading-aided), gated:** first a diagnostic on the tuning night. Locomotion windows = runs of ≥ 3 s with
  WISER 1-s speed ≥ 10 in/s and IMU QC-ok ∧ not still; Δψ_W = turn between successive 1-s-median displacements,
  Δψ_I = ∫ turn_dps dt over the matching 1 s (lag-shifted). Per-animal Spearman ρ and Theil–Sen slope.
  **Gate:** continue with V3 only if ρ ≥ 0.5 in ≥ 4 of 5 animals; otherwise report "head turn does not constrain
  the path" and skip V3. If it continues: an extended RTS smoother with state (x, y, s, θ), θ̇ = k·turn_dps + noise
  during locomotion, CV otherwise (documented then).
- **Controls:** V1 and V2 (V3 if run) rerun with every IMU-derived input taken from $t+1$ h (seconds without shifted
  IMU → treated as IMU not usable). The IMU gain must vanish.

### Tuning (tuning night only; objective = pooled median held-out error on (a), fixes with ≥ 7 anchors)

1. B2: $q\in\{1,3,10,30,100,300,1000,3000\}$ in²/s³ × $m_{\mathrm{rej}}\in\{5,8,\infty\}$.
2. B2′: $m_{\mathrm{rej}}$ from B2; $q\in\{q_{B2}/3,q_{B2},3q_{B2}\}$ × $T_b\in\{5,15,30,60,120\}$ s ×
   $\sigma_b\in\{0.5,1,1.5,2.5\}$ in.
3. V1: B2′ values; $\sigma_v\in\{0.25,0.5,1,2,4\}$ in/s.
4. V2: B2′ values; $m_s\in\{0.01,0.03,0.1,0.3,1\}$ × $m_a\in\{0.3,1,3\}$ × $m_l\in\{1,3,10\}$.

The tuned values go into the config, marked as fitted on 2026-09-08/09. Nothing is re-tuned on the test night.

### Evaluation (test night)

- **Primary (a):** hide 20 % of each tag's fixes in runs of 4–8 consecutive fixes separated by 1–47 visible fixes
  (fixed seed per animal); predict every hidden fix from the rest; score $e_i=\lVert\mathbf z_i-\hat{\mathbf z}_i\rVert$
  on hidden fixes with ≥ 7 anchors whose aligned second is QC-ok for both the IMU and the +1 h-shifted IMU (one
  scored set for all methods); median and RMSE, split IMU-still / moving (QC-ok ∧ not still).
- **(a′):** hide all fixes in a random 10 % of the night's 2-s windows (fixed seed); same scoring.
- **Why smoothing cannot game (a):** the white-noise part of a hidden fix is independent of every visible fix, so
  $E[e^2]=\mathrm{MSE}_{\mathrm{pred}}+\sigma^2_w$ with $\sigma^2_w$ method-independent; a method only lowers $e$ by
  predicting the predictable part (position + drift) better. Over-smoothing and under-smoothing are both penalised.
- **Statistics:** relative median improvement $\Delta=1-\mathrm{med}(e_M)/\mathrm{med}(e_{B2'})$ (+ = M better);
  95 % CI by a paired block bootstrap (5-min blocks, 1000 reps, blocks stratified by animal for the pooled value).
- **Acceptance (fixed now):** an IMU variant is **accepted** if on the test night, on (a) or (a′):
  (i) Δ ≥ 3 % with CI lower bound > 0 in ≥ 4 of 5 animals; (ii) its +1 h-shifted control shows **no significant
  gain** in ≥ 4 of 5 animals (CI lower bound ≤ 0 — the literal "CI includes 0" is read so that a control that
  significantly *hurts* also counts as "the gain vanishes"; the raw CIs are reported); (iii) pooled Δ on moving fixes
  ≥ −2 %. Otherwise **fail**; **inconclusive** if (i) holds in exactly 3 animals or the control condition fails. B2 and
  B2′ vs B1 are reported separately (same statistics).

### Secondary

- **(b) static references** (position-only B1/B2/B2′, full data): the dropped SF11 implant, tag 12376, in the
  accuracy report's two quiet windows 2026-09-07 06:23–06:44 and 06:55–07:24 (smoothers run on 06:12–08:12; its IMU
  is blanked after `imu_valid_until`, so no IMU variants); and the cohort-1 fixed-position test (6 tags,
  `tag_reports.sqlite`, 2026-06-21 18:16 → 06-22 12:06, the last 10 min dropped as in `wiser/README.md`). Truth =
  the raw median position; bias and RMSE of the smoothed track.
- **(c) plausibility** (test night, full data): wall-crossing rate (> 15 in outside the regime-B ridge rectangle),
  speed and acceleration distributions of the track, path length per hour, and speed during IMU-still seconds
  (circular for IMU variants — reported only).

## Deviations from the brief (declared before running)

1. The control criterion reads "CI includes 0" as "no significant gain" (lower bound ≤ 0), see above.
2. One scored set for all methods: seconds QC-ok for both the IMU and the shifted IMU.
3. The implant reference uses the accuracy report's quiet windows instead of re-deriving IMU-still runs from the raw
   `analogin.dat` (no raw read needed); cohort-1 fixed tags use the cohort-3 per-anchor noise table (transfer).
4. The moving-fix condition (iii) is evaluated on the pooled five animals.
5. The Kalman loops use numba when installed (it is in `C:\Python313`), with a pure-Python fallback.

## Risks

- One test night, regime B; the 09-10/11 night has colour sampling in the boxes and SF12's connector problems
  (ephys only; the IMU flags decide).
- The held-out target includes WISER's slow drift, so (a) rewards predicting the drift, not only the head position;
  (b) is the check on true position.
- WISER's internal filtering is unknown (it may already smooth at rest).

## Outcome (2026-09-29, after the run)

**V1 FAIL, V2 FAIL, V3 skipped at the gate.** The position-only B2′ beats the library median. Two things happened
after this plan was written:

1. **The first run was superseded** (it applied all loggers' ADC-lane windows to every animal); the fix and rerun left
   the verdicts unchanged.
2. **A clearly labelled post-hoc wider grid** was added on the tuning night only, because several tuned values sat on
   grid edges.

See the [change log](../change_log/2026-09-29-wiser-imu-smoothing-pilot.md) and the report.

## Deliverables

Plan (this file) + index row; driver + self-test; config; bulk run; report + figures + pointer; change log + index
row; the `wiser_baseline` row of CLAUDE.md's WISER table. No commit (the main session reviews and commits).
