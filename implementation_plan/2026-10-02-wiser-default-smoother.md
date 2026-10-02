# Default WISER smoother for cohort 2026c, chosen by a pre-registered rule

**Status:** DONE 2026-10-02 — this plan was written before any result of this step was computed; one amendment (before any
pooled result) is appended at the end. Result: **default = B2** (pre-registered no-survivor fallback; B2 fails only S3, by one
event; sole survivor when S3 is read by its CI). [Report](../results/2026c/wiser_baseline/reports/wiser_baseline_default_smoother_2026c.md),
[change log](../change_log/2026-10-02-wiser-default-smoother.md).
**Approval:** the user approved this step on 2026-10-02 ("do 1st first"); the candidates, periods, metrics and the
decision rule below were set by the user's brief and are used as written. Where the brief leaves an operational
detail open, the choice made here (before computing) is marked **[op]**.
**Direction:** `wiser_baseline`. **Driver:** new `wiser/scripts/analyze_wiser_default_smoother.py` (imports, never edits,
`analyze_wiser_imu_smoothing.py` and `analyze_wiser_failure_audit.py`). **Config:** new
`wiser/configs/wiser_default_smoother_2026c.json` (the run writes the decision into its `decision` block).

## Why

The failure audit (`change_log/2026-10-02-wiser-failure-audit.md`) measured what each smoother leaves in IMU-certified
stillness, but chose nothing. Downstream WISER analyses need one default track. The default must (i) remove as much
fake motion during stillness as possible and (ii) not damage real motion. Because V1/V2 use the IMU stillness that also
defines the still-segment truth, they win the still metrics by construction; the decision therefore rests on the
motion-side safety constraints S1–S4.

## Established facts used (not re-derived)

Tag and IMU are on the head: IMU-certified stillness is WISER error truth. Audit numbers (calm-dry | rain, primary
≥ 30-s segments): raw per-fix RMS 5.6 | 7.7 in, jumps 55 | 191 per still-hour, fake path 268 | 371 in/min; B2′ leaves
1.5 | 2.6 in RMS and 27 | 36 in/min, 0 jumps, does not fix slow drift; B2/B2′ remove every impossible-speed event and every
still-head jump at night. The held-out median metric is floor-dominated and blind to drift — used here only as a safety
check (S1).

**Known before this step (disclosed, from the audit's saved tables):** rain crazy-drift (≥ 12-in) events in primary
≥ 30-s segments — raw 6, B1 9, B2 7, B2′ 14, V1 5, V2 7 (V1/V2 in their audit form, i.e. without the B2 fallback
defined below); still-segment jumps per still-hour — B1 0.4 | 0.3, all Kalman methods 0; calm fake path — B1 107,
B2 39, B2′ 27, V1 1.2, V2 3.1 in/min. So, under the literal S3 rule, **B2 (the S1/S2 reference) already fails S3 by
one event, and of the audited methods only V1 passes S3.** The smoothing pilot's test-night plausibility table (all
seconds) showed B2′ and V1 slower than B2 (speed p95 8.5 vs 9.2 in/s, median of 5 animals). V2b and V2b_rt have never
been run. Because a "no survivor" outcome is therefore plausible, the fallback below is fixed now.

## Candidates

| key | definition | eligible as default | drift state | tuned params | IMU |
|---|---|---|---|---|---|
| B1 | library centred 7-sample coordinate-wise median (`P.b1_full`) | yes | no | 1 (window) | no |
| B2 | robust CV Kalman + RTS, per-fix noise from `anchors_used` (q = 3, m_rej = ∞) | yes | no | 2 | no |
| B2p (B2′) | B2 + AR(1) drift (q = 1, T_b = 15 s, σ_b = 2.5 in); track = p | yes | yes | 4 | no |
| V1 | B2′ + ZUPT in IMU-still seconds (σ_v = 0.25 in/s) | yes | yes | 5 | yes |
| V2 | B2′ with q × (1, 0.01, 0.3, 10) by IMU state (unusable, still, active, loco) | yes | yes | 7 | yes |
| V2b | **new**: V2's state switching and multipliers (1, 0.01, 0.3, 10) on the B2 base (q = 3), no drift state, no retuning | yes | no | 5 | yes |
| V2b_rt | **new, secondary**: V2b with the three multipliers retuned on the pilot's tuning night only | **no** (reported) | no | 5 | yes |

All tuned values are the smoothing pilot's (`wiser/configs/wiser_imu_smoothing_2026c.json` → `tuned`), unchanged.
Fix times are aligned by the animal's τ* (0.10–0.20 s); IMU per-second states are the audit's saved
`imu_seconds/<SFxx>_<period>.csv.gz` (pilot rule: still, active, locomoting; 0 = QC failed).

**IMU fallback [op]:** every IMU-dependent method (V1, V2, V2b, V2b_rt) is scored in its deployable form: its value at
a fix whose aligned second is IMU-QC-ok, the B2 value elsewhere (and in the ± 10-min margins, which have no saved IMU
seconds). For V2b/V2b_rt this equals the in-filter behaviour (state 0 → multiplier 1 → B2 dynamics). The fallback share
(fixes and seconds) is reported per set. V1/V2 in their audit (in-filter, B2′-fallback) form are reported for
reproduction.

**V2b_rt retuning [op]:** the pilot's own objective — pooled median held-out error on scheme (a) of the tuning night
2026-09-08 21:00 → 09-09 04:20 (fixes with `t_ms` in the window, hidden runs with the pilot's seeds 20260929 + animal
index, scored fixes with ≥ 7 anchors whose aligned second is QC-ok for the IMU and the +1 h IMU) — over the pilot's
pre-registered V2 grid (m_still ∈ {0.01, 0.03, 0.1, 0.3, 1} × m_active ∈ {0.3, 1, 3} × m_loco ∈ {1, 3, 10}) on the B2
base; ties → RMSE. Check before use: the same code must reproduce the pilot's tuning-night B2 median (4.091 in) and
its V2 optimum (0.01 / 0.3 / 10, 4.000 in) to ≤ 0.005 in. Grid-edge hits are reported.

## Periods and data

Exactly the audit's: calm-dry days 09-05 / 09-07 / 09-08 (08:00–18:00) and nights 09-05 … 09-08 (21:00–04:20); rain
nights 09-03 (from regime B, window 21:00–04:20) and 09-09, rain day 09-10 (IMU to ≈ 14:40). Animals SF07, SF08, SF09,
SF10, SF12. Handling ± 5 min, all-tag silences ± 120 s, tag limits, each logger's ADC lane and IMU QC failures excluded
as in the audit. Inputs (read-only): audit bulk `D:\Field2026_analysis_out\2026c\wiser_failure_audit_20261002_1511\`
(`tracks/*.npz` = every audited method at every fix incl. raw, `imu_seconds/`, `speeds/`, `tables/`), the WISER fix
caches `wiser_fix_cache/<period>/<SFxx>.csv.gz` (library speed `speed_inps_smooth`, `valid`), and — only for the +1 h
QC mask of the V2b_rt tuning objective — the make_imu 50-Hz npz through the audit's own loaders. No SQLite access is
needed (the caches already hold the fixes); nothing saved is recomputed except where a new method needs it, and the
saved numbers are re-derived only as reproduction checks.

## Metrics

### Still (primary; certified segments ≥ 30 s of the audit, primary source, trimmed 1 s)
Per method, calm vs rain and day vs night: fake path (in/min), residual per-fix RMS and p99 (in, from the segment truth =
median raw fix), 10-s and 60-s rolling-median drift (median and p90 over segments), ≥ 12-in excursions (crazy-drift
events: ≥ 10 s with the 10-s median ≥ 12 in from the truth; count and per still-hour), residual jumps (> 30 in within
≤ 0.35 s; count and per still-hour). Saved audit rows are reused for B1/B2/B2′; V2b, V2b_rt and the B2-fallback forms of
V1/V2 are scored with the audit's own `score_segment` on the same segments. 95 % CIs: 1000 resamples of 10-min
animal-period blocks; ratios vs B2 with the same draw for both methods.

### Safety
- **S1 — held-out error on moving fixes.** Schemes (a) = the pilot's runs of 4–8 hidden fixes (gaps 1–47) and
  **(s) [op] = every 5th fix hidden alone with a random phase (V5's scheme (s); the pilot itself had (a)/(a′))**, new
  fixed seeds per animal-period. Every method is rerun with the hidden fixes invisible; B1 predicts by the median of the 7
  nearest visible fixes. Scored: hidden, in the period window, `anchors_used` ≥ 7, aligned second IMU-QC-ok; **moving** =
  QC-ok ∧ not IMU-still. Statistic $D=1-\operatorname{med}(e_m)/\operatorname{med}(e_{B2})$, paired 10-min block bootstrap
  (blocks within animal-period). **[op]** The prediction is each method's *delivered track* (p for B2′/V1/V2); the
  pilot's p + b predictor is reported as a sensitivity. Fail if $D<-0.02$ (point estimate) in calm **or** rain, in (a)
  **or** (s).
- **S2 — speed preservation.** 1-s centred speed $v(s)=\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/1$ s at the
  centre of each second (linear interpolation, only inside inter-fix gaps ≤ 1 s), on (i) IMU-locomoting seconds and (ii)
  **[op]** seconds whose WISER library 1-s median speed (median of `speed_inps_smooth` over the `valid` fixes of the
  aligned second — the pilot's locomotion label) is ≥ 10 in/s, in the analysis mask (window, no handling ± 5 min, no
  silence ± 120 s, tag valid; IMU not required, so the fallback is exercised). Seconds where any method's speed is
  undefined are dropped for all (paired). Statistic $\Delta_q=q_m/q_{B2}-1$ for q = p50, p95. **[op]** Fail if
  $|\Delta_q|>0.10$ for any q ∈ {p50, p95}, subset ∈ {(i), (ii)}, set ∈ {calm, rain} (point estimates; CIs reported).
- **S3 — excursions in rain.** Fail if the method's rain crazy-drift event count (primary ≥ 30-s segments) exceeds raw's
  (same segments, same truth). Point counts, as written; the 10-min block-bootstrap CI of the rate difference is reported.
- **S4 — residual jumps.** Fail unless the method has **0** jumps both (i) in the primary ≥ 30-s still segments (calm and
  rain) and (ii) **[op]** over the analysis mask of every period (days and nights; pair midpoint second in the mask).
- **S5 — onset/offset lag (reported, not in the elimination rule).** Events = the audit's onset/offset definition from the
  per-second IMU states (still run ≥ 10 s followed / preceded within 60 s by a locomoting second, no still or unusable
  second in between, ≥ 10 s from the window edges), all periods. Onset lag = first time in [b − 5 s, s_L + 20 s] at which
  the method's 0.25-s-grid 1-s centred speed reaches 3 in/s, minus b (the first non-still second); offset lag = last such
  time in [s_L − 20 s, a + 10 s] (+ 0.25 s) minus a (the first still second). Per event Δ = lag_m − lag_B2 (both defined);
  median Δ with a 10-min block-bootstrap CI.

## Decision rule (pre-registered by the brief; operational details above)

1. Eliminate any eligible method that fails S1, S2, S3 or S4.
2. Among the survivors choose the lowest **calm-dry fake path** (pooled primary ≥ 30-s segments).
3. Tie = within 5 % of the lowest (fake path ≤ 1.05 × min) → the simpler method. **[op]** Simplicity order,
   lexicographic: (1) no drift state, (2) fewer tuned parameters, (3) no IMU dependence → B1 < B2 < V2b < B2′ < V1 < V2.
4. The rain-specific choice = the same rule with the rain fake path (same eliminations); reported separately if it
   differs.
5. **[op] No survivor:** if no eligible method passes all four, the default is the eligible method with the fewest failed
   criteria (S1–S4 each counted once), then steps 2–3 among those; the report says plainly that the rule's elimination
   step left no survivor. V2b_rt is scored on every criterion but cannot be chosen; if it would have won, the report says
   so.
6. The default's fallback where the IMU QC fails is B2 (stated with its share); for a position-only default the fallback
   is itself.

**Sensitivity (reported, never the decision):** S3 judged by its CI (fail only if the 95 % CI of the rain rate excess
over raw lies above 0); S1 with the p + b predictor.

## Verification

- `--selftest` on synthetic data (no field data): a track with still periods, OU walking bouts, anchor-dependent noise,
  drift and outliers; candidates B2 (q matched to the synthetic walking), a speed-damping smoother (q × 0.01) and an
  IMU-switched smoother (q × 0.01 in true still seconds) → the rule must eliminate the damping method (S2) and keep and
  choose the IMU-switched one (lowest still fake path); plus the rule's tie and no-survivor branches, the onset/offset lag
  on a planted delay, and the paired speed-quantile bootstrap (identical methods → Δ = 0, CI [0, 0]).
- Reproduction: V2 rebuilt from the saved in-window states matches the saved audit V2 track (report max |Δ| away from the
  window edges); the pilot's tuning-night B2 / V2 medians (above); still metrics of raw/B2 re-derived for a sample of
  segments equal the saved rows; onset/offset event counts on the nights equal the audit's.

## Outputs

- Bulk `D:\Field2026_analysis_out\2026c\wiser_default_smoother_<ts>\`: `tracks/<SFxx>_<period>.npz` (V2b, V2b_rt and the
  B2-fallback V1/V2 at every fix), `tables/` (still segment metrics for the new methods, per-method still summaries,
  S1 per-fix errors + bootstrap, S2 per-second speeds + quantiles, S3/S4 counts, S5 events and lags, V2b_rt tuning grid,
  reproduction checks, decision table), `summary.json`, `input_provenance.json`, `log.txt`, `run_manifest.json`.
- Report `results/2026c/wiser_baseline/reports/wiser_baseline_default_smoother_2026c.md` (+ figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_default_smoother_*_2026c.png`), pointer
  `run_manifest_default_smoother_2026c.json` (`run_manifest.json` untouched). Report order: executive summary (decision
  + key numbers, ≤ 10 lines), decision table, one section per metric, "do not do", Definitions, caveats.
- `change_log/2026-10-02-wiser-default-smoother.md`, top rows in both index READMEs, the `wiser_baseline` row of
  `CLAUDE.md`. No commit. Stop when the decision is reported.

## Caveats known in advance

The pilot's parameters were tuned on 2026-09-08/09, which is one of the calm nights (and V2b_rt's tuning night);
still time is ≥ 95 % inside the houses; S3 rests on 6–14 events; S2's locomotion label has TPR 0.75 / FPR 0.15; speed
during motion has no independent truth, so S2 tests preservation relative to B2, not correctness.

## Amendments

1. **(Before any pooled result; after a one-animal-period smoke test, SF09 `night_20260909`.)** The B2 fallback splice is
   not identical to V2b's in-filter behaviour, contrary to the sentence above: during fast runs the IMU often fails its QC
   (saturation), V2b (loco q × 10) follows the run while B2 lags it by up to ≈ 20 in, so the splice puts steps of up to 17 in
   into the deployable V2b at those boundaries (in-filter vs splice at IMU-failed fixes: median 0.24 in, p99 3.0 in, max
   17 in on that animal-period). The scored form stays the pre-registered splice. Added as a **reported sensitivity**
   (never the decision): the in-filter V2b and V2b_rt in S2, S4 and S5, and the size of the splice steps; if the rule's
   choice would differ between the two forms, the report says so.
