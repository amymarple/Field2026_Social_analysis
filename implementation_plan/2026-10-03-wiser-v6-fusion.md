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
