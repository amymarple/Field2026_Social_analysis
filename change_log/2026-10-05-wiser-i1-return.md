# 2026-10-05 — I1 return test: does raw WISER come back after a V3 I1 event? → reading NOT ESTABLISHED, V3 stays, no correction

**Plan:** [`implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md`](../implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md),
Part 1 (approved by the user 2026-10-05; committed d722ec0 before any result). *Amendment (Part 1) 1* was written before any number
of this step. It fixes the [op] details, resolves one ambiguity in the reading ("its CI above … the relocate class's point
estimate" = CI lower bound of the return class > the relocate point estimate) and declares one structural property of the
classifier with a sensitivity for it (S3). *Amendment (Part 1) 2* was written after the pooled numbers: a rendering bug fix, declared
descriptive additions, and the `--with-verdicts` reader aligned with Part 2's export. No class, window, threshold or rule changed.
Part 2 (the blind video GUI) is a separate step by another session (`change_log/2026-10-05-wiser-event-review.md`).
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_i1_return_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_i1_return_2026c.md)
(reading, structural caveat, 7 sections, full Definitions; figures `wiser_baseline_i1_return_{shares,enrichment,profiles}_2026c.png`).
**Driver / config:** `wiser/scripts/analyze_wiser_i1_return.py` (`--selftest` 15 checks ALL PASS; `--report-only <run>` re-aggregates,
`--render-only <run>` re-renders, `--with-verdicts <export|folder> [--run <run>]` = the validation pass, implemented and selftested,
**not run**: no verdict exists yet); `wiser/configs/wiser_i1_return_2026c.json` (reading in `reading`; the verdict pass writes `validation`).
**Bulk:** `D:\Field2026_analysis_out\2026c\wiser_i1_return_20261005_2236\` (`tables/event_classes.csv.gz` = one row per event with
P0 / P1, distances, classes of the primary and S1–S3, censoring reasons, reproduction columns, integer-ms times; class shares,
enrichment, profiles, cross-table, distance quantiles, censoring reasons; `work/profiles.npz`; `summary.json`,
`input_provenance.json`, `log.txt`, `selftest.txt`). Pointer `results/2026c/wiser_baseline/reports/run_manifest_i1_return_2026c.json`.
Inputs (read-only): the consistency audit run `wiser_imu_consistency_20261005_2038` (V3 I1 events, matched controls, per-window
dispersion) and the production default tracks (raw fixes).

## Reading (pre-registered, primary classes, pooled)

**NOT ESTABLISHED → V3 stays, no correction** (the plan's label of this branch: "I1 is mainly real movement the IMU missed"). Nothing was tuned.

| quantity | value [95 % CI] | rule | met |
|---|---|---|---|
| return / ambiguous / relocate / censored | 474 / 995 / 218 / 3,724 of 5,411 | | |
| return share of the classifiable (non-censored, n 1,687) | **28.1 %** | ≥ 50 % | no |
| ≤ 6-anchor share ratio, return class ρ_S | **1.28** [0.79, 2.30] (20.2 % vs 15.7 %) | ≥ 1.5, CI_lo > 1 | no, no |
| … CI_lo(return) > ρ_S(relocate) | relocate **1.65** [1.08, 2.47] | | no (also the looser point > point: no) |

**Structural caveat (Amendment (Part 1) 3, declared before the run, verified):** the audit's I1 window holds every second whose V3 1-s
median is ≥ 12 in from the run reference. So on every classifiable post window the V3 track is back within 12 in (max 11.9995 in on
all 1,687). A shift held until the next locomotion is therefore **censored**, never *relocate*. The primary *relocate* class is made
of raw-vs-V3 differences (D median 13.3 in; raw P0 vs V3 reference median 1.6 in, p90 5.1 in). The post window also starts on the
excursion's tail. The 50 % condition thus compares full vs partial returns, not returns vs persistent relocations.

## Reported (not the reading)

- **Class shares (primary):** all events return 8.8 %, ambiguous 18.4 %, relocate 4.0 %, censored 68.8 % (3,649 because the window
  ends < 5 s before the run end, 75 for < 10 fixes). Excluding censored: 28.1 / 59.0 / 12.9 %. House 26.9 / 60.5 / 12.6 % (censored
  57.7 %), field 32.3 / 53.5 / 14.1 % (censored 84.0 %). Night 29.8 % return (censored 77.3 %), day 23.1 % (41.7 %), twilight 31.4 %.
  Rain 33.5 %, wet 29.2 %, dry 25.8 %. Size 12–24 in: 28.2 % return (censored 62.0 %). 24–48 in: censored 95.7 %; ≥ 48 in: 99.0 %.
  Runs ≤ 10 s: 99.7 % censored. Per animal, return of the classifiable 24–31 %.
- **Enrichment by class** (ρ_S; the audit's estimator and controls): return 1.28 [0.79, 2.30], ambiguous 1.56 [1.20, 1.97],
  relocate 1.65 [1.08, 2.47], censored 1.38 [1.19, 1.61]. Within zone, return house 1.29, field 1.36; relocate field 2.10
  [1.32, 3.54]. Dispersion ratio return 1.26 [1.18, 1.45] (others 1.14–1.20). No class stands out as bad geometry: all are of the order
  of the audit's pooled 1.43, and the return class is the least ≤ 6-anchor-enriched.
- **Excursion profiles** (median raw 1-s distance from P0): 5.6–7.1 in 10 s before the onset (1-s raw noise plus earlier wandering),
  peak 14–17 in 1–2 s after it. The return class falls back to ≈ 7 in by +15 s and stays at ≈ 7.6 in at +60 s; S3-relocate events stay at
  15.4 in at +30 s and 13.6 in at +90 s.
- **Sensitivities:** S1 (10-s pre-onset reference) return 66.6 % of the classifiable, but ρ_S(return) 1.39 [1.05, 1.84] and
  ρ_S(relocate) 3.13 [2.20, 4.53]. After the excursion WISER comes back near where it was just before the onset, which is already
  6–7 in from the run start. S2 (30-s post window) return 32.4 %. **S3 (run-end window; declared)**: return 12.5 %, ambiguous 23.9 %,
  relocate 42.9 %, censored 20.6 %. Excluding censored: 15.8 / 30.1 / 54.1 %. 2,146 of the 3,724 primary-censored become relocate. S3
  relocate is 93 % / 99 % of the classifiable 24–48 / ≥ 48-in events, and S3 return is 41 % in runs > 30 min. S3 cannot tell a
  persistent shift from an excursion still out at the run end. The reading rule (information only) is not met on any variant.
- **Reproduction:** every one of the 5,411 events recomputed from the production V3 track — reference, size, onset, window end,
  duration exact (max 3.6e-15 in) → PASS. Fix counts per animal identical to the audit.
- **Not done:** the validation against the video verdicts (`--with-verdicts`). It waits for the Part-2 export in
  `wiser/configs/wiser_event_review_2026c/` and uses the blind verdict.

## Definitions (headline quantities; full set in the report)

- **Window median** $\mathbf M[a,b) = \operatorname{med}_{\rm coord}\{\mathbf z_k : t_k \in [a,b)\}$ over unmasked raw fixes (aligned time).
  A post window is valid iff $b - a \ge 5$ s and it holds ≥ 10 fixes.
- **Positions:** $\mathbf P_0 = \mathbf M[t_{r0}, t_{r0}+2)$ (the I1 reference window, raw fixes), $\mathbf P_1 = \mathbf M[t_{\rm end}, \min(t_{\rm end}+10, t_{r1}))$,
  where $[t_{r0}, t_{r1})$ is the trimmed run and $t_{\rm end}$ the end of the audit's event window (last ≥ 12-in second + 1). Inches,
  unverified WISER frame.
- **Classes:** $D = \lVert\mathbf P_1 - \mathbf P_0\rVert$; return $D < 6$, ambiguous $6 \le D < 12$, relocate $D \ge 12$ in; censored = no valid
  post window. Sensitivities: S1 $\mathbf P_0 = \mathbf M[\max(t_{\rm on}-10, t_{r0}), t_{\rm on})$; S2 a 30-s post window; S3
  $\mathbf P_1 = \mathbf M[\max(t_{\rm on}, t_{r1}-10), t_{r1})$.
- **Shares:** $s_c = n_c / n$; excluding censored $s^{\rm cl}_c = n_c / (n_{\rm ret} + n_{\rm amb} + n_{\rm rel})$.
- **Enrichment** $\rho_S(c)$ = ≤ 6-anchor share of the class's event windows / that of their matched controls (control weight $1/k_e$),
  $\rho_D$ = ratio of the median raw-fix dispersion about its 1-s median. CI: 10-min block bootstrap (animal × 10-min bin), 1,000 replicates.
- **Reading:** dominates ⇔ $s^{\rm cl}_{\rm ret} \ge 0.5 \wedge \rho_S({\rm ret}) \ge 1.5 \wedge \mathrm{CI_{lo}} > 1 \wedge \mathrm{CI_{lo}} > \rho_S({\rm rel})$.
- **Profile** $\pi_c(u)$ = median over the class of $\lVert\tilde{\mathbf p}_{\rm raw}(t_{\rm on}+u) - \mathbf P_0\rVert$ (1-s raw medians, ≥ 2 fixes,
  inside the run).
- **Verdict agreement** (pending): Cohen's $\kappa = (p_o - p_e)/(1 - p_e)$ on return ↔ stayed, relocate ↔ moved.

## Caveats

The mean-reversion premise was measured mostly in the houses during certified stillness. A rat can walk away and return within
one run, and a WISER bias can persist outside stillness: the video verdicts decide. Enrichment is circumstantial. The structural
caveat above limits what the primary relocate class means. Positions are in the unverified WISER inch frame.

## For the main session (not done here, by boundary)

- CLAUDE.md, `wiser_baseline` row: add `analyze_wiser_i1_return --cohort 2026c` (+ `--selftest`, `--render-only`, `--with-verdicts`),
  its config `configs/wiser_i1_return_<c>.json` (`reading`, later `validation`), the pointer `run_manifest_i1_return_<c>.json`, and
  the result. Suggested wording: "I1 return test 10-05: reading NOT ESTABLISHED → V3 stays, no correction, no V8. Return 28 % of
  the classifiable; 69 % censored because the I1 window by construction runs to the run end for persistent shifts. S3 run-end: 54 %
  relocate. No class is bad-geometry-enriched. The video validation is pending."
- Index READMEs (`change_log/README.md`, `implementation_plan/README.md`): add this entry and the plan's Part-1 amendments; then commit
  (driver, config, report, figures, pointer, plan amendments, this file).
