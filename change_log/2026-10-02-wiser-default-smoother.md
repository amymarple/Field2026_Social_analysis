# 2026-10-02 — Default WISER smoother for cohort 2026c, chosen by a pre-registered rule

**Plan:** [`implementation_plan/2026-10-02-wiser-default-smoother.md`](../implementation_plan/2026-10-02-wiser-default-smoother.md),
approved by the user 2026-10-02 ("do 1st first"); written before any result, one amendment (before any pooled result).
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_default_smoother_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_default_smoother_2026c.md)
(decision table, one section per criterion, full Definitions, 3 figures). **Bulk:** `D:\Field2026_analysis_out\2026c\wiser_default_smoother_20261002_1626\`;
pointer `results/2026c/wiser_baseline/reports/run_manifest_default_smoother_2026c.json` (`run_manifest.json` untouched).

## Decision

**The default WISER smoother for 2026c is B2** (robust constant-velocity Kalman + RTS, per-fix noise from `anchors_used`,
q = 3 in²/s³, m_rej = ∞, Huber k = 2.5, χ² gate 13.8, 2 IRLS passes; parameters and per-anchor noise table =
`wiser/configs/wiser_imu_smoothing_2026c.json` → `tuned.B2` / `tuned.anchor_sigma`). It is position-only, so it needs no
IMU fallback. It was chosen by the pre-registered **no-survivor fallback**: no eligible method passed all of S1–S4, and
B2 failed only S3, by one event (7 vs raw's 6 rain ≥ 12-in excursions; rate difference +0.04 per still-hour
[−0.22, +0.35]). When S3 is judged by its CI, B2 is the only survivor, so the default does not depend on that reading.
The rain-specific choice is also B2. The decision is written into `wiser/configs/wiser_default_smoother_2026c.json` → `decision`.

## What changed

- **New** `wiser/scripts/analyze_wiser_default_smoother.py` (`--selftest` ALL PASS, 13 checks on synthetic data: the rule's
  tie, outside-tie and no-survivor branches; onset/offset event extraction and lags on a planted 3-s delay; the paired
  speed-quantile bootstrap; a synthetic track with still bouts, OU walking bouts, anchor-dependent noise, drift and
  outliers, where a speed-damping smoother (q × 0.01) is eliminated by S2 (−14 to −18 %) and an IMU-switched smoother is
  kept and chosen (still fake path 5 vs B2 72 in/min, |ΔS2| ≤ 0.3 %)). `--report-only <run_dir>` re-aggregates from the saved
  tables. It imports `analyze_wiser_imu_smoothing.py` (Kalman core, schemes) and `analyze_wiser_failure_audit.py`
  (segment scorer, block bootstrap, loaders) unchanged and reuses the audit's saved tracks, IMU seconds, speeds and tables.
- **New** `wiser/configs/wiser_default_smoother_2026c.json` (candidates, complexity order, S1–S5 parameters, bootstrap,
  V2b_rt grid, `decision` block).
- **New method V2b** = V2's IMU-state switching of the process noise (multipliers 1 / 0.01 / 0.3 / 10 for unusable / still /
  active / locomoting) on the B2 base, no drift state. **V2b_rt** (retuned on the pilot's tuning night with the pilot's own
  objective and grid) lands on the same multipliers (all three at grid edges), so it is identical to V2b.
- **Amendment 1 (before any pooled result, after a one-animal smoke test):** the pre-registered B2 fallback splice of an
  IMU method differs from its in-filter behaviour during fast runs, when the IMU often fails its QC (V2b follows the run,
  B2 lags it; splice vs in-filter up to 25 in, 60 of 13,459 ok↔failed boundaries add a step > 5 in). The splice stays the
  scored form; the in-filter V2b is reported as a sensitivity.
- No existing script, cache or raw file was modified; no SQLite access was needed.

## Verification

- Reproduction: V2 rebuilt from the saved in-window IMU states matches the audit's V2 to 0.03 in (≥ 60 s from the window
  edges; V1 0.6 in); the pilot's tuning night is reproduced by the same code path (fix counts 103,339 / 103,350 / 103,612 /
  103,864 / 104,813 and +1 h IMU-ok seconds identical to the pilot; B2 median 4.0912 vs 4.0911 in; V2 optimum 0.01 / 0.3 / 10
  at 3.9999 in, as the pilot); 1,780 re-derived still segment × method rows equal the saved rows (max |Δ| 0.001 in/min);
  night motion-side jumps (raw 24,595, B1 81, B2′ 0) and onset/offset events (217 / 182) equal the audit's; the fix caches
  equal the tracks' fixes in every animal-period; 0 segment fix-count mismatches.
- IMU fallback share (window fixes): calm 6.8 %, rain 16.0 % (handling rounds, the 09-10 ADC lane after ≈ 14:40).
- Implementation note: block-bootstrap quantiles use a sparse histogram product (identical to the dense one, 0.6 s instead
  of 46 s per call on this PC); each section has its own random stream (seed 20261005 + k) so the saved still bootstrap can be
  reused by `--report-only` without changing other draws. The first aggregation was stopped and re-run this way (no
  numbers changed: the compute outputs were not touched).
- Minor finding in the failure audit (not fixed here): its per-group still tables (`summary_still_{period,setkind,set,...}.csv`)
  take speed quantiles with row positions of the grouped frame instead of the full segment table (raw calm fake-speed
  p95 12.31 there vs 11.70 in/s correct); the audit report's pooled table, and every path / RMS / drift / event / jump
  number, is unaffected.

## Results (pooled primary ≥ 30-s certified still segments; calm-dry | rain)

| method | fake path in/min | per-fix RMS in | rain ≥ 12-in events (raw 6) | S1 worst Δ vs B2 | S2 calm loco Δ p50 / p95 | S4 jumps still / motion | failed |
|---|---|---|---|---|---|---|---|
| B1 median-7 | 107.0 \| 158.4 | 2.33 \| 3.84 | 9 | −6.3 % | +56.0 % / +23.8 % | 36 / 126 | S1 S2 S3 S4 |
| **B2** | 38.9 \| 50.8 | 1.60 \| 2.65 | 7 | ref | ref | 0 / 0 | S3 |
| B2′ (p) | 27.1 \| 35.6 | 1.48 \| 2.61 | 14 | −2.9 % (s) | −14.8 % / −12.1 % | 0 / 0 | S1 S2 S3 |
| V1 | 1.2 \| 1.4 | 1.24 \| 2.04 | 5 | −3.7 % (s) | −14.7 % / −12.0 % | 0 / 0 | S1 S2 |
| V2 | 3.1 \| 4.0 | 1.06 \| 2.08 | 7 | −1.4 % (s) | +10.4 % / +8.0 % | 0 / 2 | S2 S3 S4 |
| V2b | 8.2 \| 10.5 | 1.21 \| 2.13 | 8 | +0.5 % | +28.0 % / +14.7 % | 0 / 3 | S2 S3 S4 |

- **S2 is the binding constraint:** every IMU method moves the 1-s speed by more than 10 % relative to B2: B2′/V1 slower
  (they inherit B2′'s smoother p), V2/V2b faster (looser process noise while active/locomoting). At p50 the IMU-locomoting
  seconds carry little displacement (B2 3.0 in/s), so V2b's +28 % is plausibly jitter; at p95 V2b is +12–15 %. Without an
  independent motion truth the rule cannot say whether B2 under-follows fast runs or V2b over-follows them.
- **S1:** V2b predicts held-out moving fixes slightly better than B2 (+0.5 to +1.3 %), V2 within −1.4 %; B2′/V1 fail only
  on scheme (s) with their delivered track p (with p + b they pass).
- **S4:** the V2/V2b motion jumps arise only at B2-splice boundaries (in-filter forms: 0 jumps).
- **S5 (reported):** B2 starts moving a median 7.0 s after the first non-still IMU second (calm); V2b differs by +0.25 s at
  onsets and −0.75 s at offsets, V2 by +1.0 / −5.5 s.
- **Sensitivity:** S3 by CI → B2 (sole survivor); V2b without the splice → B2; S1 with p + b → V1, only because the
  fewest-failures fallback then ties V1 (S2) with B2 (S3) and takes the lower fake path — a weakness of that fallback, not
  support for V1 (whose locomotion speed is ≈ 15 % below B2's).

## Headline definitions (full set in the report)

- **Fake path** $\Pi=\sum_s\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/(N_s/60)$ (in/min) inside certified still segments
  ($\tilde{\mathbf p}$ = linear interpolation inside inter-fix gaps ≤ 1 s, pooled sum of path over sum of time). Text: path a
  tracker invents while the head is still; 0 is perfect.
- **S1** $D_m=1-\operatorname{med}(e_m)/\operatorname{med}(e_{B2})$, $e=\lVert\mathbf z_k-\hat{\mathbf p}_{-}(t_k)\rVert$ on hidden fixes
  (schemes (a) runs of 4–8, (s) every 5th fix) with ≥ 7 anchors, IMU-QC-ok and not IMU-still. Fail if $D<-0.02$ in calm or rain,
  (a) or (s). Text: + = predicts unseen moving fixes better than B2.
- **S2** $\Delta_q=Q_q[v_m]/Q_q[v_{B2}]-1$, $v(s)=\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/1$ s, q ∈ {p50, p95}, on
  IMU-locomoting seconds and on seconds with WISER library speed ≥ 10 in/s. Fail if any $|\Delta_q|>0.10$. Text: how much a
  method slows (−) or speeds up (+) real movement relative to B2.
- **S3** fail if the rain count of ≥ 12-in excursions (10-s median ≥ 12 in from the segment truth for ≥ 10 s) exceeds raw's.
- **S4** fail unless 0 jumps (> 30 in within ≤ 0.35 s) in the still segments and over every period's analysis mask.
- **Rule** eliminate S1–S4 failures; lowest calm-dry fake path; within 5 % → simpler (no drift, fewer parameters, no IMU:
  B1 < B2 < V2b < B2′ < V1 < V2); no survivor → fewest failed criteria, then the same choice.
- **Block bootstrap** 1000 resamples of 10-min animal-period blocks within each set, paired across methods; 2.5–97.5 %.

## Caveats

The pilot's parameters (and V2b_rt) were tuned on 2026-09-08/09, one of the calm nights; still time is ≥ 95 % inside the
houses and its truth is WISER's own segment median; S3 rests on 5–14 events, so one event decides it under the literal rule;
S2 has no independent motion truth (IMU locomotion class TPR 0.75 / FPR 0.15); S1 is floor-dominated; the rain set is three
weather episodes; positions stay in the unverified WISER inch frame.
