# 2026-10-03 — V6 (short-horizon head-IMU acceleration fusion) loses to V3 at every gap length → inertial-position line closed; V3 stays

**Plan:** [`implementation_plan/2026-10-03-wiser-v6-fusion.md`](../implementation_plan/2026-10-03-wiser-v6-fusion.md) (approved by the user
2026-10-03, "开始"; committed e0252c8 before any V6 number). Amendment 1 (operational readings) was written before any V6 or
test-night number; Amendment 2 (after the results) holds reporting/code notes only — nothing in it enters the decision.
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_v6_fusion_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_v6_fusion_2026c.md)
(decision table, G curves for every method, tuning grid, handedness, T1–T4, heading by-product, NIS, still, S1, S3, input share,
reproduction, full Definitions; figures `wiser_baseline_v6_fusion_{gapfill,t1,heading,nis}_2026c.png`).
**Driver / config:** `wiser/scripts/analyze_wiser_v6_fusion.py` (`--selftest` ALL PASS, `--report-only <run_dir>`, `--skip-tune`);
`wiser/configs/wiser_v6_fusion_2026c.json` (`tuned` from the tuning night 09-07 only, verdict in `decision`).
**Bulk:** `D:\Field2026_analysis_out\2026c\wiser_v6_fusion_20261003_2206\`; pointer
`results/2026c/wiser_baseline/reports/run_manifest_v6_fusion_2026c.json`.
**New cache (save once, reuse):** `D:\Field2026_analysis_out\2026c\imu_acc16_cache\<SFxx>\<period>.npz` + `README.md` — 16-Hz
make_imu world-frame x/y acceleration (in/s²) low-passed at 1.5 / 2 / 3 Hz, 50-Hz-validity QC, the audit's per-second ok and state,
IMU session index, for all 50 failure-audit animal-periods (period ± 10 min, + 1 h for the control).

## Decision (pre-registered rule 2)

**Close the inertial-position line: no further INS / acceleration-fusion variants for WISER position. V3 stays the default WISER
track for the implanted animals; B2 stays the universal baseline.** The calm-test gain of V6 over V3 is significantly *below* 0 at
both L = 0.5 s and 1 s (rule 2's condition "CI includes or is below 0 at both"); the control did not invalidate; T3 and T4 also fail.

V6 = per animal and period, an EKF + extended RTS on a 16-Hz grid with the fixes inserted; state (p, v, b, ψ); input = make_imu
`lin_acc_earth_ms2` x/y × 39.37 low-passed at 2 Hz; B2 fix noise, χ² gate + 2 Huber IRLS passes; V3's ZUPT; fallback without input
at q = 3 in²/s³. Tuned on 09-07 only (27-point grid): **q_a 70 in²/s³, τ_b 10 s (σ_b 4.5 in/s²), q_ψ 16 (°)²/min — every value at
the loosest edge of the grid** (toward ignoring the input); even this best point predicts worse than V3 on the tuning night
(RMS_pred 7.23 vs 6.64 in, −8.9 %; the whole grid spans −8.9 % to −40.3 %). Handedness by the pre-registered rule: per animal —
SF07 mirrored on an LLR of −0.3 (indistinguishable from 0), SF08 / SF09 / SF10 / SF12 normal (LLR +0.9 / +0.5 / +13.5 / +25.8).

## Pre-registered criteria (calm test nights 09-05, 09-06, 09-08 pooled; 95 % CIs from the paired 10-min block bootstrap)

| criterion | V6 | bound | outcome |
|---|---|---|---|
| G gain vs V3, L = 0.5 s (13,610 hidden fixes, 5,569 blocks) | **−5.6 %** [−6.5, −4.4] | ≥ 10 %, CI > 0 (rule 1); CI ≤ 0 at both L → rule 2 | below 0 |
| G gain vs V3, L = 1 s (27,185 fixes) | **−11.5 %** [−12.8, −10.3] | (same) | below 0 |
| negative control (+1 h input), gain vs V3 at 0.5 / 1 s | −2.1 % [−2.9, −1.3] / −5.6 % [−6.5, −4.7] | invalid if ≥ 50 % of a positive V6 gain | not invalid |
| T1 3-s p95 speed vs clean WISER, all / > 15 in/s (six nights, as V3) | −0.9 % [−1.7, −0.6] / −0.1 % [−2.0, +0.6] | ± 3 % | pass (V3 −2.1 / −1.2) |
| T2 jumps, certified still segments / analysis masks | 0 / 0 | 0 / 0 | pass |
| T3 median Δ lag vs B2: calm onset / offset; rain onset / offset | −3.75 / **+7.00**; −4.50 / **+8.12** s | ≤ +0.5 s | **FAIL** (offsets) |
| T4 in-place 1-s speed p50 / p95 vs B2 (5,404 s) | 2.73 / 6.54 vs 1.10 / 2.45 in/s (**+148 % / +167 %**) | ≤ B2 | **FAIL** (V3 +62 / +69 %) |

- **G at every L** (RMS_pred, fix-noise floor √mean σ²_fix 2.93 in removed): V3 5.38 / 5.83 / 6.78 / 7.86 in, **V6 5.68 / 6.50 / 8.49 /
  11.42 in**, B2 5.97 / 6.43 / 7.30 / 8.23 in at 0.5 / 1 / 2 / 3 s; gains −5.6 / −11.5 / −25.3 [−27.4, −23.3] / −45.4 % [−48.7, −42.1].
  The V6 − V3 difference grows with L (0.30 / 0.67 / 1.72 / 3.57 in) — **no crossing**: the IMU makes the inertial prediction worse
  the longer it has to carry it. Raw median error V3 4.26 / 4.60, V6 4.46 / 5.02 in (0.5 / 1 s). Rain nights −4.1 % [−5.2, −2.9] /
  −8.6 % [−10.0, −7.2] / −21.8 / −41.2 %; tuning night −3.8 % [−6.6, −1.4] / −8.9 % [−11.4, −6.4] / −21.5 / −41.6 %. Every animal
  loses at every L (1 s: SF07 −24.0 %, SF08 −10.5, SF09 −11.4, SF10 −7.1, SF12 −9.0 %; all CIs below 0). Context: V3 beats B2 / V1b by
  ~10 % at 0.5–1 s; V2b ≈ V3 (−0.5 / −0.4 %).
- **Control** loses *less* than V6 at every L (calm −2.1 / −5.6 / −15.6 / −30.3 %): at the locomoting blocks the +1 h input mostly
  comes from rest (small), whereas the real input there is large and misdirected — the content of the input hurts.
- **Sensitivities** (never the decision): low-pass 1.5 / 3 Hz and no-ZUPT give the same G as V6 (−5.6 / −11.6 % at 0.5 / 1 s);
  ψ frozen is worse (−7.3 / −14.1 %); all fail T3 and T4.

## Reported (not the decision)

- **Heading by-product (no claim):** on the nights the smoothed ψ is not a linear drift — OLS slopes −2.33 to +2.27 °/min (median
  |slope| 0.99; gyro-bias expectation 1.6–2.1 °/min), 60° RMS (median) about the line, night ranges 100–1,102° — while σ_ψ stays
  below 10° almost all the time: the filter's ψ uncertainty is inconsistent (overconfident). ψ is not observable in the sense the
  plan needed; **no plausible head-direction signal for ephys** from V6.
- **NIS** (calm mean, still / active / locomoting): B2 2.93 / 5.42 / 10.09, V3 3.45 / 5.18 / 7.05, **V6 2.95 / 5.15 / 8.68** (rain V6
  4.87 / 6.14 / 9.36).
- **Still metrics (circular for the ZUPT forms):** fake path B2 38.9 | 50.8, V3 3.3 | 3.6, **V6 19.1 | 21.9 in/min** (calm | rain;
  V6-noZUPT 99.1 | 133.3); per-fix RMS V3 1.07 | 1.89, V6 1.34 | 2.23 in.
- **S1** (held-out moving fixes): D(V6) −14.4 % [−15.0, −13.8] calm, −14.7 % rain on scheme (a) (runs of 4–8 fixes), −0.3 / −0.9 % on (s)
  (V3 +1.0 / +1.9 %). **S3** (rain ≥ 12-in excursions): raw 6, B2 7, V3 4, **V6 8**.
- **Input share:** 96.6 % of night analysis-mask fixes and 92.4 % of night grid steps had IMU input (days 89.6 % / 75.8 %; 4 day
  sessions had < 30 locomoting seconds for a ψ fit → no input); the control's shifted sample was missing on 3.4 % of input steps.
- **Post-hoc reading (added after the decision; outside it):** on IMU-ok locomoting seconds of the 30 animal-nights the 1-Hz IMU
  input has median magnitude 28.6 in/s² (animal-night range 17.4–48.4; at IMU-still seconds 1.0) vs 6.6 in/s² for the V3 track's
  1-Hz acceleration; a best rotation of the input explains R² = 0.001 of the track acceleration over a night and 0.053 (median; p90
  0.157; mirrored 0.023) within 120-s windows. The head's 0–2 Hz horizontal specific force during locomotion is mostly *not* body
  translation (head sweeps, tilt leak in motion); the plan's 0.25 m/s² prior was a whole-night median dominated by rest. The tuned
  q_a / τ_b then put motion into the edges of still runs: within 0–1 s of a still-run edge V6's 1-s speed is ≥ 3 in/s in 8.6 % of
  seconds (B2 2.1 %, V3 0.7 %), deeper inside V6 is quieter than B2 (≤ 0.1 % vs 0.7–1.2 %) — that moves the S5 lags (T3).

## Reproduction

V3 rebuilt by this driver = the V3 run's saved track (4.3e-5 in, float32), ZUPT mask identical in all 50 animal-periods; B2 = the
audit's saved B2 (4.3e-5 in); the V6 kernel without input equals B2 (q = 3, no ZUPT) and V3 (q = 3 × V3's multipliers + V3's ZUPT) to
1.5e-12 in (median of 50 jobs; one multi-session day job 2.9e-6 in, floating point after long fix gaps; synthetic 2e-12 in); T1 rows
of raw / B2 / V1b / V2b / V3 = the V3 run's (120 rows, max |Δ| 0.000 pp, n identical); T4 set = V3's (n 5,404; B2 1.100 / 2.450, V3
1.783 / 4.140 in/s identical); still metrics of raw / B2 / V3 / V1b / V2b identical to the audit / V3 run (20,800 rows, max |Δ| 0).
Selftest (synthetic, ALL PASS): no-input V6 = B2 and = V3 (≤ 1e-6 in), ψ recovered within 5° and a 2 °/min drift tracked, V6 beats
the CV filters at 0.5–1 s on synthetic data with a true translational IMU, the shifted control gives no gain, the > 2-Hz bob creates
no speed, session resets, G / T1–T4 / decision evaluators on planted cases.

## Definitions (headline quantities; full set in the report)

- **Hidden blocks / gap-fill error.** Centres $c=s+0.5$ of step-B clean seconds with IMU state locomoting, seeded greedy ≥ 13 s apart,
  identical for every $L\in\{0.5,1,2,3\}$ s; hidden fixes $\mathcal H_L=\{k:t_k\in[c-L/2,c+L/2)\}$, every method rerun once per $L$ with
  $\mathcal H_L$ invisible; $e_k=\lVert\hat{\mathbf p}_{-\mathcal H}(t_k)-\mathbf z_k\rVert$ (in). **Text:** how far a method's prediction
  lands from the fix it did not see, during clean open-field locomotion.
- **Prediction RMS and gain.** $\mathrm{RMS}_{\text{pred}}=\sqrt{\max(0,\overline{e^2}-\overline{\sigma^2_{\text{fix}}})}$ with
  $\sigma^2_{\text{fix},k}=\sigma^2_x(A_k)+\sigma^2_y(A_k)$ (B2 anchor table), pooled over the set's hidden fixes;
  $\text{gain}=1-\mathrm{RMS}_{\text{pred}}(\text{V6})/\mathrm{RMS}_{\text{pred}}(\text{V3})$. **Text:** the prediction error with the fix's
  own (still-measured) noise removed; gain > 0 = V6 better than V3; CI = paired bootstrap of 10-min (animal, period, block) blocks.
- **Negative control.** V6 fed the same animal's input shifted by +3600 s (V6's own availability mask, ZUPT, fallback; ψ0 refitted).
  **Text:** invalid if it recovers ≥ 50 % of a positive V6 gain at L = 0.5 or 1 s.
- **V6 dynamics.** $\dot{\mathbf p}=\mathbf v$, $\dot{\mathbf v}=R(\psi)(M\mathbf a-\mathbf b)+\mathbf w_a$ ($q_a$),
  $\dot{\mathbf b}=-\mathbf b/\tau_b+\mathbf w_b$ (stationary SD $\sigma_b$), $\dot\psi=w_\psi$ ($q_\psi$); $M$ = diag(1, ±1) handedness.
  **Text:** the head's rotated, bias-corrected slow acceleration drives the velocity between fixes.
- **Initial ψ / handedness.** $\hat\psi_0=\arg\sum_i\overline{A_i}D_i$ (normal; mirrored $\arg\sum_iA_iD_i$), $A$ = 1-Hz IMU acceleration,
  $D$ = 1-Hz V3-track acceleration (complex), first 30 min of IMU-ok locomoting seconds; $\mathrm{LLR}=n_s\ln(\mathrm{RSS}_m/\mathrm{RSS}_n)$.
- **T1–T4** as in the V3 step (T1 $|d_{95}|\le3$ % on 3-s speed; T2 0 jumps > 30 in in ≤ 0.35 s; T3 median S5 lag change vs B2 ≤ +0.5 s;
  T4 = V3's in-place set, V6's S2 1-s speed p50 and p95 ≤ B2's).
- **Heading drift / observability.** OLS slope of the smoothed ψ (deg) on time (min) over input seconds; share of seconds with
  $\sigma_\psi<10°$. **Text:** whether ψ behaves like gyro-bias drift and whether the filter can pin it.

## What the main session must do

- `CLAUDE.md` (WISER code map, `wiser_baseline` row): add `analyze_wiser_v6_fusion --cohort 2026c` (V6 short-horizon IMU-acceleration
  EKF + extended RTS, config `configs/wiser_v6_fusion_<c>.json` with `tuned` / `decision`, pointer `run_manifest_v6_fusion_<c>.json`,
  new reusable cache `<OUT>/2026c/imu_acc16_cache/` + README; result 10-03: **rule 2 — inertial-position line closed, V3 stays**) and
  `analyze_wiser_v6_fusion.py --selftest` in the self-test column.
- Both index READMEs (`implementation_plan/`, `change_log/`): add this plan / entry. Commit.
