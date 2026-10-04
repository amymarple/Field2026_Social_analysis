# V6 — short-horizon head-IMU / WISER fusion (cohort 2026c)

**Status:** PLANNED 2026-10-03, written before any V6 number was computed.
**Approval:** the user asked "IMU你难道不该做fusion么" and approved this plan on 2026-10-03 ("开始"). It is the first
*fair* test of using the IMU acceleration itself (not only an IMU state label) inside the WISER smoother, at the horizons
where physics allows it. Operational details are marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_wiser_v6_fusion.py` (imports, never edits, the
V3 / V1b / step-B / default-smoother / failure-audit / smoothing-pilot modules). **Config:** new
`wiser/configs/wiser_v6_fusion_2026c.json` (`tuned` block from the tuning night; verdict in `decision`).

## Why (established facts, not re-derived)

- V4 / V5 tested **long-horizon inertial bridging** and failed: tilt error δθ leaks g·δθ into horizontal acceleration,
  position error ½·g·δθ·T² (0.3° → 1 in at 1 s, 25 in at 5 s); V5 additionally aided tilt only at strict still windows
  (a design error; night windows 29–92 min apart). V1b / V3 use the IMU only as a **state label**.
- **Short horizons are different:** over one WISER interval (0.25 s) the IMU velocity increment errs by ≈ g·δθ·0.25 ≈
  0.5–2.5 in/s (δθ 0.3–1.5°), whereas differencing two fixes errs by ≈ 21 in/s. The make_imu Fusion AHRS (continuous gated
  accelerometer aiding) keeps the night 2-Hz horizontal specific force at median 0.25 m/s² (≤ 1.5° if all of it were tilt).
- **V3 is the current default** for the implanted animals (`change_log/2026-10-03-wiser-v3.md`): T1 3-s p95 speed −2.1 % /
  −1.2 % vs clean-WISER speed, 0 jumps, transitions unshifted, NIS locomoting 7.05 (still 3.45, active 5.18) — but its
  1-s speed is −17.6 % vs clean WISER and **+62 % / +69 % above B2 on in-place activity the IMU calls locomotion** (5,404
  clean seconds below the floor). Fusion should fix exactly this: during in-place activity the 0–2 Hz world acceleration is
  ≈ 0, so velocity is held; during runs the acceleration drives it.
- No magnetometer (headstage magnet) → the IMU's world frame has an arbitrary, drifting heading (gyro bias drift linear,
  ≈ 1.6–2.1 °/min); 90 % of head horizontal-acceleration variance is > 2 Hz (head bob/scan, not body translation).
  Frame handedness WISER vs IMU: "normal" in 10/10 animal-nights (calibration pilot); fix times already aligned by τ*.
  Step B's clean-WISER speed (≥ 8 anchors, open field, no jumps) is the speed truth; its floor u3 p50/p95 0.59/1.64 in/s.

## Candidate

**V6 (primary).** Per animal and period, an extended Kalman filter + extended RTS smoother on a 16-Hz grid with the WISER
fixes inserted at their aligned times **[op]**:
- **State** $\mathbf x=(\mathbf p,\mathbf v,\mathbf b,\psi)$: position and velocity (in, in/s, WISER frame), world-frame
  horizontal acceleration bias $\mathbf b$ (in/s², first-order Gauss–Markov), heading offset ψ between the IMU world frame
  and the WISER frame (random walk).
- **Input:** $\mathbf a(t)$ = make_imu `lin_acc_earth_ms2` x/y (gravity removed by the Fusion AHRS) × 39.37, **low-passed at
  2 Hz** (zero-phase, offline) and sampled at 16 Hz. Dynamics $\dot{\mathbf p}=\mathbf v$,
  $\dot{\mathbf v}=R(\psi)(\mathbf a-\mathbf b)+\mathbf w_a$, $\dot{\mathbf b}=-\mathbf b/\tau_b+\mathbf w_b$, $\dot\psi=w_\psi$.
- **Measurements:** WISER fixes with the B2 noise model (per-axis σ by `anchors_used`), χ² gate + 2 Huber IRLS passes
  (k_H 2.5); the V3 ZUPT (σ 0.25 in/s, Huber, IMU-still runs ≥ 3 s eroded by 1 s, no release).
- **Where the IMU QC fails** (and in margins): no input, V3's dynamics (CV, q = 3 in²/s³; × 10 never applies because the
  state is unknown) — same filter, no splice; ψ and b propagate as random walks.
- **Initial ψ and handedness:** closed-form 2-D Procrustes fit of the 2-Hz IMU acceleration to the second derivative of
  the V3 track (both low-passed at 1 Hz **[op]**) over IMU-ok locomoting seconds of the first 30 min that have them; both
  handedness options fitted on the **tuning night only**, the better one (likelihood) fixed for all animals unless it
  differs by animal (then per animal, reported).
- **Tuned parameters (tuning night 09-07 only):** acceleration process noise $q_a$, $(\tau_b,\sigma_b)$, $q_\psi$ — small
  fixed grid **[op: ≤ 3 values each, centred on physical priors: $q_a$ from the ≈ 0.25 m/s² residual, $\tau_b$ 1–10 s,
  $q_\psi$ from ≈ 2 °/min]**, objective = the gap-fill prediction RMS (below) at L = 1 s on 09-07's clean locomoting
  blocks. Nothing is tuned on any other night.

**Sensitivities (reported, never the decision):** low-pass 1.5 Hz and 3 Hz; ψ frozen at its initial value; no ZUPT.
**Negative control (pre-registered sanity check):** V6 fed the same animal's acceleration **shifted by + 1 h**. If the
control recovers ≥ 50 % of V6's gap-fill gain at L = 0.5 or 1 s, the V6 result is declared **invalid** (the gain would
not come from the IMU's information).

## Pre-registered evaluation

Test nights = calm 09-05, 09-06, 09-08 (decision) and rain 09-03, 09-09 (reported); 09-07 is the tuning night and is
reported separately. Comparators: **V3** (reference), B2, V1b; V2b for context.

- **G — gap-fill curve (primary).** Blocks of length L ∈ {0.5, 1, 2, 3} s are hidden, each centred on a clean (step-B
  filter), IMU-QC-ok, locomoting second, blocks ≥ 10 s apart, fixed seeds; every method is rerun once per L with all its
  blocks invisible **[op]**. For hidden fix k: $e_k=\lVert\hat{\mathbf p}(t_k)-\mathbf z_k\rVert$. Prediction RMS
  $\mathrm{RMS}_{\text{pred}}=\sqrt{\max(0,\ \overline{e^2}-\overline{\sigma^2_{\text{fix}}})}$ with
  $\sigma^2_{\text{fix}}$ = the per-axis variance sum of that fix's `anchors_used` (B2 table). Gain
  $=1-\mathrm{RMS}_{\text{pred}}(\text{V6})/\mathrm{RMS}_{\text{pred}}(\text{V3})$, paired 10-min block bootstrap.
  The raw median $e$ is reported too.
- **T1 — clean speed:** 3-s p95 over all clean seconds and of the > 15 in/s band within **± 3 %** of clean-WISER speed
  (as V3). The 1-s scale is reported (V3 −17.6 %).
- **T2 — 0 jumps** in the certified still segments and over every audit period's analysis mask.
- **T3 — transitions:** S5 onset / offset median Δ vs B2 **≤ + 0.5 s**.
- **T4 — in-place jitter:** on the step-V3 in-place set (clean, IMU-locomoting, clean-WISER 3-s speed < 1.64 in/s), V6's
  1-s speed p50 and p95 **≤ B2's** (point estimates).

**Decision.**
1. **V6 replaces V3** as the default for the implanted animals if the calm-test gain at L = 0.5 s **or** 1 s is **≥ 10 %**
   with its 95 % CI above 0, **and** T1–T4 pass, **and** the negative control does not invalidate it. B2 stays the universal
   baseline.
2. **Close the inertial-position line** (no further INS / acceleration-fusion variants for WISER position) if the gain is
   **not** significantly above 0 (CI includes or is below 0) at **both** L = 0.5 s and 1 s, or the control invalidates it.
   V3 stays.
3. Otherwise (a gain above 0 but < 10 %, or a T-criterion failed): V3 stays; the report states what V6 offers and at
   what cost; any follow-up is a proposal to the user.

## Reported, not part of the decision

- Gap-fill curves for every method and L, calm | rain, per animal; where the V6 − V3 curves cross.
- **Heading by-product:** ψ(t) per animal-night — drift rate vs the gyro-bias expectation, ψ change across consecutive
  locomotion bouts, the fraction of time ψ is observable (σ_ψ below 10°); whether a head-direction signal for ephys is
  plausible (no claim).
- NIS by IMU state × anchors × zone for B2, V3, V6; still metrics on certified segments (circular); S1; S3 (raw 6, B2 7,
  V3 4); IMU-QC fallback share.

## Data and caches

Inputs (read-only): make_imu 50-Hz npz `D:\3rd_rat_spikes\analysis\imu\<SFxx>\<session>.imu.npz`; the failure-audit,
default-smoother, V1b, step-B and V3 runs under `D:\Field2026_analysis_out\2026c\`; the WISER fix caches. **New cache
(save once, reuse):** the 16-Hz input series per animal-period — `<OUT>/2026c/imu_acc16_cache/<SFxx>/<period>.npz`
(time, 2-Hz / 1.5-Hz / 3-Hz world-frame x/y acceleration in in/s², QC mask, IMU state) + README.

## Verification

- `--selftest` (synthetic): a 2-D trajectory with runs, turns, in-place head bob (> 2 Hz) and stillness; a synthetic IMU =
  true acceleration rotated by a drifting ψ + bias + tilt-leak noise + head bob; WISER-like fixes with anchor-dependent
  noise and outliers. Checks: with no input and q = 3 the filter equals B2 (≤ 1e-6 in); V6 recovers ψ within 5° after the
  first runs and tracks a 2 °/min drift; V6's gap-fill error at 0.5–1 s is below the CV filter's; the +1 h-shifted control
  gives no gain; in-place bob does not create speed; T1–T4 / G evaluators on planted cases.
- Reproduction: V3 rebuilt by this driver equals the saved V3 tracks; step-B / V3 T1 numbers of B2 / V3 reproduced.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\wiser_v6_fusion_<ts>\`: tracks (V6, sensitivities, control, ψ, b), `tables/`
  (gap-fill, T1–T4, NIS, still, S1, S3, ψ diagnostics, tuning grid), `summary.json`, `input_provenance.json`, `log.txt`.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_v6_fusion_2026c.md` (+ figures), pointer
  `run_manifest_v6_fusion_2026c.json`; `change_log/2026-10-03-wiser-v6-fusion.md`. The main session updates CLAUDE.md and
  both index READMEs and commits.

## Caveats known in advance

Clean seconds are open-field, ≥ 8 anchors: fusion under poor anchors and inside the houses is not scored. The hidden-fix
target carries WISER noise; the floor subtraction uses the still-measured anchor table, which may understate the noise in
motion (NIS 7–10), diluting every gain toward 0 (conservative). Head ≠ body: the 2-Hz low-pass removes head bob but not
slow head sweeps. The Fusion AHRS tilt is good at night (≤ 1.5°) but degrades in shake trains, where the QC fails and V6
falls back. B2's q and V3's × 10 were tuned on 09-08/09; V6 is tuned on 09-07 only.

## Amendment 1 (2026-10-03, operational; written BEFORE any V6 number and before any test-night or rain-night result was seen)

The plan leaves these details open or ambiguous; the closest faithful option is fixed here before the code runs on field
data. Nothing below changes the candidate, the split, a threshold or the decision rule.

1. **Grid and discretisation.** Grid = the absolute 16-Hz field-PC grid (multiples of 62.5 ms) strictly inside
   [first fix, last fix] merged with the aligned fix times (a 16-Hz point within 1 µs of a fix is dropped). Each step
   (t_{j−1}, t_j] uses the input at its midpoint (linear interpolation of the 16-Hz series), available only if both
   bracketing 16-Hz samples are QC-ok; constant input over the step (exact for p, v); process noise of (p, v) = the
   continuous white-acceleration CV form with intensity q_a (input steps) or q = 3 in²/s³ (fallback steps); b exact
   Gauss–Markov discretisation (φ = e^{−Δt/τ_b}, added variance σ_b²(1 − φ²)); ψ random walk q_ψΔt. EKF Jacobians at the
   filtered state; extended RTS (gain P_f Fᵀ P_p⁻¹, Cholesky), smoothed covariance in the final pass only (for σ_ψ).
2. **Input and its QC.** make_imu `lin_acc_earth_ms2` x/y × 39.37, zero-phase Butterworth order 4 (`sosfiltfilt`) at
   2 Hz (1.5 / 3 Hz for the sensitivities) on each contiguous run of valid 50-Hz samples (the failure audit's
   `sample_valid`: finite, not saturated / frozen / invalid / unreliable, frozen rule, handling ± 5 min, all-tag silences
   ± 2 min, ADC lane, tag window), linearly interpolated onto the 16-Hz grid; a 16-Hz sample within 0.5 s of a run end is
   not QC-ok; QC-ok also requires the audit's per-second `ok` (so the ± 10-min margins and everything the audit excludes
   fall back). The cache covers [start − 10 min, end + 10 min + 1 h] (the extra hour feeds the +1 h control).
3. **Fallback.** "ψ and b propagate as random walks" is read as: no input coupling; ψ by its random walk, b by its own
   Gauss–Markov model (a pure random walk of b would grow without bound through hour-long QC failures).
4. **IMU session boundaries** (day periods only; every night is one session): make_imu's heading is arbitrary per
   session, so at the first step of each new session ψ := that session's initial ψ (σ_ψ0) and b := 0 (σ_b), with zero
   cross-covariance (implemented inside F/Q so the RTS stays exact); that one step carries no input. A session whose ψ fit
   has < 30 IMU-ok locomoting seconds gets no input at all (fallback).
5. **Initial ψ.** Fit window = 30 min from the session's first IMU-ok locomoting second inside the analysis window,
   extended until it holds ≥ 60 such seconds (or the session ends). Samples = 16-Hz points in those seconds. Target = the
   V3 track linearly interpolated onto the 16-Hz grid (gaps ≤ 1 s), Butterworth-4 zero-phase 1 Hz on contiguous runs,
   second difference × 16²; IMU = the input series low-passed at 1 Hz the same way. ψ̂0 = arg Σ conj(A)·D (A, D the
   complex IMU / target accelerations; mirrored: A → conj(A)). Initial σ_ψ0 = 20° (a priori). Every V6 run, including the
   gap-fill reruns, fits ψ0 on the V3 track run with the same fixes hidden; the control fits it on its shifted input.
6. **Handedness likelihood.** Similarity-Procrustes residual RSS = Σ|D|² − |Σ conj(A)D|²/Σ|A|² for each option; Gaussian
   log-likelihood ratio LLR = n_s·ln(RSS_mirror/RSS_normal) with n_s = number of distinct seconds (conservative effective
   n). Decided per animal on the 09-07 night (full V3 track); one option for all if all five agree, else per animal.
7. **Tuning grid** (27 combinations, objective = pooled RMS_pred at L = 1 s over 09-07's five animals, ties → grid
   order): q_a ∈ {4.4, 17.5, 70} in²/s³ (centre = σ_a²/(2 f_c), σ_a = 0.25 m/s² / 1.1774 per axis × 39.37 = 8.36 in/s²,
   f_c = 2 Hz; × ¼, × 4); (τ_b, σ_b) ∈ {(1 s, 4.5), (3 s, 4.5), (10 s, 4.5 in/s²)} (σ_b = g·sin 0.67°, the geometric
   mean of the 0.3–1.5° tilt range); q_ψ ∈ {1², 2², 4²} (°)²/min (2 °/min centre), in rad²/s.
8. **Gap-fill blocks.** Candidate centres c = s + 0.5 for step-B clean seconds with audit state 3 (IMU-QC-ok,
   locomoting); seeded permutation (seed 20261009 + 100·period index + animal index); greedy acceptance of centres
   ≥ 13 s from every accepted centre, so even the 3-s blocks are ≥ 10 s apart; the same centres for every L; hidden fixes
   = fixes with aligned time in [c − L/2, c + L/2), all scored. Every method is rerun once per L with all its hidden fixes
   invisible: B2 and V3 by the V3 kernel; V1b with its release recomputed from the visible fixes (as in its S1); V2b by
   the pilot kernel spliced to the rerun B2 at IMU-failed fixes (context). σ²_fix = r²_x + r²_y of the B2 table.
   RMS_pred is pooled over all hidden fixes of a set (fix-weighted); the gain CI is the paired 10-min (animal, period,
   block) bootstrap (1000 draws, percentiles); "CI above 0" = 2.5 % point > 0.
9. **Sets for G.** Calm test = nights 09-05, 09-06, 09-08 (the decision); rain = nights 09-03, 09-09; tuning = night
   09-07 (reported separately). Days have no step-B clean seconds, so no G.
10. **Negative control.** The 16-Hz input (value and QC) shifted by +3600 s; the input-availability mask, ZUPT and
    fallback are V6's own, and where the shifted sample is not QC-ok the control gets zero input (still with q_a), so the
    only difference is the content of the input. Run on the nights (G is night-only). "Recovers ≥ 50 % of V6's gain" is
    evaluated at L = 0.5 and 1 s wherever V6's gain > 0: invalid if gain(control) ≥ 0.5·gain(V6) at either.
11. **T populations ("as V3").** T1 = V3's population: step-B clean seconds of all six nights pooled (incl. the tuning
    night 09-07); T1 without 09-07 is reported as a check. T2, T3 over every audit period (calm and rain, days and
    nights). T4 = V3's in-place set (clean, state 3, u3 < 1.64 in/s, six nights), the S2 1-s speed, V6 p50 and p95 ≤ B2's.
12. **ZUPT** at the fix times only (V3's mask, applied after the fix update, also at hidden fixes — as V3's kernel).
13. **NIS** with the full 2×2 innovation covariance (equal to the per-axis form whenever P is axis-separable, i.e. for
    B2 / V3 and V6's fallback).
14. **ψ frozen** sensitivity: ψ held at each session's ψ0 with its Jacobian column zeroed (no cross-covariance, q_ψ = 0).
    The sensitivities and the control use the tuned parameters; the low-pass sensitivities refit ψ0 on their own input.
15. **Decision precedence.** Control invalid → rule 2. Else, CI lower bound ≤ 0 at both L = 0.5 and 1 s → rule 2. Else
    rule 1 if (gain ≥ 10 % with CI lower bound > 0 at L = 0.5 or 1 s) and T1–T4 pass. Else rule 3.

## Amendment 2 (2026-10-03, AFTER the results were seen; reporting and code only — nothing that enters the decision)

1. **Handedness, as pre-registered:** on 09-07 the Procrustes LLR (normal over mirror) was SF07 −0.3, SF08 +0.9, SF09 +0.5,
   SF10 +13.5, SF12 +25.8, so the animals "disagree" and the rule fixed the handedness per animal: SF07 mirrored (on an LLR
   indistinguishable from 0), the others normal. Applied as written; reported, not revisited.
2. **Kernel reproduction on field data:** the no-input V6 kernel equals B2 / V3 to 1.5e-12 in (median of 50 jobs); one
   multi-session day job (SF08 day_20260905) reaches 2.9e-6 in, above the selftest's 1e-6 bound (which the synthetic test
   meets at 2e-12). Floating point after long fix gaps; reported as is.
3. **Aggregation bug fix** (`True & True` used as a pandas index in the fallback table) after the compute finished; the
   report was re-aggregated from the saved per-job files with `--report-only` (no recompute, no number in the decision changed).
4. **Post-hoc diagnostics added to the report after the decision, clearly labelled and outside it:** (a) per night, the 1-Hz
   IMU input magnitude vs the V3 track's 1-Hz acceleration on IMU-ok locomoting seconds and the Procrustes R² (whole night,
   120-s windows); (b) the share of IMU-still seconds with a 1-s speed ≥ 3 in/s, overall and by distance from the still-run
   edge. They explain the outcome; they decide nothing.
