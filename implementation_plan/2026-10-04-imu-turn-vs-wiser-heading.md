# Phase 0 of turn-aided WISER: does the head gyro's turn track the WISER heading change? (cohort 2026c)

**Status:** PLANNED 2026-10-04, written before any number of this step was computed.
**Approval:** the user asked whether left turns etc. could be extracted from the IMU and given to WISER, and approved this
feasibility step on 2026-10-04 ("做"), with the agreed follow-up: pass → the turn annotation is usable during locomotion
and a turn-rate-aided smoother (V7) is built and tested like V3/V6; fail → head turns stay a head-behaviour signal only.
Operational details are marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_imu_turn_vs_heading.py`. **Config:** new
`wiser/configs/imu_turn_vs_heading_2026c.json` (verdict in `decision`).

## Why (established facts, not re-derived)

- V6 closed the **acceleration**-fusion line: the head's ≤ 2-Hz horizontal acceleration in locomotion is ≈ 4× the body's
  (head sweeps scale with ω²) plus tilt leak, and the absolute heading offset ψ between the IMU and WISER frames is
  unobservable. A **turn rate** is different: the gyro measures rotation directly (no double integration, no gravity leak;
  the vertical projection is insensitive to a ≤ 1.5° tilt error), bias drift ≈ 1.6–2.1 °/min (≈ 0.03 °/s, negligible over
  seconds), and a *relative* heading change needs no ψ.
- make_imu already writes the signed turn rate about the vertical `turn_dps` (50 Hz, **+ = counter-clockwise seen from
  above**) and per-second `turn_net_deg` / `turn_abs_deg` (`D:\3rd_rat_spikes\analysis\imu\<SFxx>\<session>.imu.npz` /
  `.imu_1s.csv`, field-PC time `t_pc_ms`).
- WISER heading at low speed is noise-dominated (spurious turns, cf. GPS telemetry); a turn in place is invisible to WISER.
  Head yaw ≠ body heading during scanning — this step measures how far they agree **during locomotion**.
- Step B's clean seconds (`D:\Field2026_analysis_out\2026c\imu_speed_proxy_20261003_1210`: all fixes ≥ 8 anchors, open
  field, no jumps, ≥ 3 Hz; 6 nights 09-03, 09-05 … 09-09) and its 1-s median estimator: $\mathbf m(t)$ = coordinate-wise
  median of raw fixes in $[t-0.5, t+0.5)$ s; floor of $u_1$ p50 / p95 1.90 / 5.26 in/s. Fix times are aligned by τ*.

## Quantities

- **WISER heading** at centre c: $\theta(c)=\operatorname{atan2}$ of $\mathbf d(c)=\mathbf m(c+0.5)-\mathbf m(c-0.5)$ (1-s
  displacement of raw-fix medians; smoother-independent), defined when $\lVert\mathbf d(c)\rVert/1\,\text{s}\ge$ **10 in/s**
  **[op]** and both medians exist on clean seconds. Secondary: the same from the V3 track.
- **Gyro heading:** $\psi(t)=\int\texttt{turn\_dps}\,dt$ (unwrapped, IMU-QC-ok samples only), and its 1-s mean
  $\bar\psi(c)$ over $[c-0.5, c+0.5)$ — the same averaging window as θ(c).
- **Pairs:** for separations W ∈ {1, 2, 3} s, $\Delta\theta=\operatorname{wrap}(\theta(c+W/2)-\theta(c-W/2))$ and
  $\Delta\psi=\bar\psi(c+W/2)-\bar\psi(c-W/2)$, centres c on a 0.5-s grid, both ends clean, IMU-QC-ok throughout
  **[op]**; $\Delta\psi$ is wrapped the same way for the residual $r=\operatorname{wrap}(\Delta\theta-b\,\Delta\psi)$.
- **Fit:** OLS of $\Delta\theta$ on $\Delta\psi$ through the origin and with intercept (gyro = regressor; it is the less
  noisy one), slope b, $R^2$, residual median |r| and p90 (degrees); circular correlation as a check. Pairs with
  $|\Delta\psi|>150°$ are reported but excluded from the fit (wrap ambiguity) **[op]**. 10-min block bootstrap CIs.
- **Expected heading noise:** $\sigma_\theta\approx\sigma_d/\lVert\mathbf d\rVert$ with $\sigma_d$ from the $u_1$ floor —
  reported per speed band (10–20, > 20 in/s) as the ceiling an ideal gyro could reach.

## Pre-registered gate

On the pooled **calm** nights (09-05, 09-06, 09-07, 09-08), W = 2 s, raw-median heading: **|b| ∈ [0.8, 1.2] and
R² ≥ 0.5** → **PASS**: head yaw is a usable body-turn signal during locomotion. The sign of b fixes the convention
(b ≈ +1: WISER heading increases counter-clockwise like the gyro; b ≈ −1: the WISER plan view is mirrored relative to
"seen from above" — then a left turn is negative in WISER). Otherwise **FAIL**.

**Negative control:** the same with the gyro shifted by + 1 h (expected b ≈ 0, R² ≈ 0); if the control gives R² ≥ 0.1 the
analysis is declared invalid (a pipeline artefact).

## Reported, not part of the gate

- W = 1 and 3 s; rain nights 09-03 and 09-09; per animal; per speed band; V3-track heading instead of raw medians.
- **Turn-sign agreement:** for pairs with |Δψ| ≥ 30°, the share with the same sign in WISER (after the convention from b);
  confusion table for left / right / straight (|Δ| < 15°).
- **Scanning tail:** share of pairs with |r| > 30° (head turned without the path turning).
- **What WISER misses:** gyro turns ≥ 90° within 3 s while the 1-s WISER speed stays below the $u_1$ floor p95
  (turns in place) — count per IMU-ok hour, calm | rain, house | open field.
- Lag check: b and R² for gyro shifts of −0.5 … +0.5 s (peak should be at ≈ 0 after τ*).

## Data

Read-only: make_imu npz (`turn_dps`, QC flags, `t_pc_ms`), step-B clean seconds and the failure-audit `imu_seconds/`
(QC, states), the WISER fix caches, V3 tracks (`D:\Field2026_analysis_out\2026c\wiser_v3_20261003_1425\tracks\`).

## Verification

- `--selftest` (synthetic): a path with known turns and a head yaw = path heading + scanning oscillation (± 25° at 1.5 Hz)
  + gyro bias 2 °/min; WISER-like fixes with anchor noise → the estimator recovers b ≈ 1 within 0.05 and R² close to the
  analytic value; mirrored axes give b ≈ −1; the + 1 h control gives b ≈ 0; wrap handling on a planted 170° turn.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\imu_turn_vs_heading_<ts>\`: `tables/` (pairs, fits, bootstrap, sign agreement,
  in-place turns, lag scan), `summary.json`, `input_provenance.json`, `log.txt`.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_imu_turn_vs_heading_2026c.md` (+ figures), pointer
  `run_manifest_imu_turn_vs_heading_2026c.json`; `change_log/2026-10-04-imu-turn-vs-heading.md`. The main session updates
  CLAUDE.md and both index READMEs and commits.

## Caveats known in advance

Clean seconds are open-field and ≥ 8 anchors: agreement in the houses is not measured. The 10-in/s heading threshold
selects locomotion; slow walking is excluded by construction. Raw-median heading carries WISER noise (attenuates R²
toward 0 — conservative). Head yaw includes scanning; the 1-s averaging removes part of it.
