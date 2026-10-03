# 2026-10-03 — WISER common-mode error across tags and pairwise-distance precision (step C, cohort 2026c)

**Plan:** [`implementation_plan/2026-10-03-wiser-common-mode.md`](../implementation_plan/2026-10-03-wiser-common-mode.md),
step C of the A → B → C sequence approved by the user on 2026-10-03; written before any number. Amendment 1 (8 points, made
**before** any pooled number) fixes ambiguous details; Amendment 2 (made **after**) adds reporting only — no metric, threshold
or verdict changed.
**Report:** [`results/2026c/wiser_baseline/reports/wiser_baseline_common_mode_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_common_mode_2026c.md)
(verdict, findings, C1 / anchors / shared excursions / C2 / C3 / 09-10 case / reproduction, full Definitions, 5 figures
`results/2026c/wiser_baseline/figures/wiser_baseline_common_mode_*_2026c.png`).
**Bulk:** `D:\Field2026_analysis_out\2026c\wiser_common_mode_20261003_1124\` (`tables/`, `summary.json`,
`input_provenance.json`, `log.txt`); pointer `results/2026c/wiser_baseline/reports/run_manifest_common_mode_2026c.json`
(`run_manifest.json` untouched).

## Verdict (pre-registered): common mode NOT MATERIAL

| criterion | B2 | raw |
|---|---|---|
| (1) pooled same-zone ρ_v of 10-s residuals ≥ 0.3, CI > 0 | 0.19 [0.06, 0.30] — fail | 0.17 [0.05, 0.26] — fail |
| (2) C3 variant z: 10-s drift p90 or 1-s RMS ≤ −10 %, CI < 0 | drift p90 +30.9 % [+22.8, +35.5], RMS +18.0 % [+9.2, +27.0] — fail | +32.1 % / +20.8 % — fail |

No change to the 14-in distance rule is made (plan); a tighter value for still animals is only a proposal to the user.

## What changed

- **New** `wiser/scripts/analyze_wiser_common_mode.py` (`--selftest` ALL PASS, 20 checks; `--report-only <run_dir>`
  re-aggregates from the saved seconds table with the same seeds). It imports `analyze_wiser_failure_audit.py` unchanged
  (rolling median kernel, block-bootstrap counts, helpers) and reads the audit's saved run (segments, tracks raw/B1/B2/B2′,
  still fixes) plus the fix caches' `anchors_list`. No SQLite, no IMU, no Kalman run, no existing file modified.
- **New** `wiser/configs/wiser_common_mode_2026c.json` (grid, ≥ 30-s overlap rule, lags, zone pairings, distance bands, anchor
  rules, shared-excursion rule, C3 settings, bootstrap, verdict thresholds).
- **Plan amendments** (in the plan file). Before results: `anchors_list` is the *listed* set (a superset of the used anchors —
  `anchors_used ≤ n_list` in every fix), so "lost" = not listed, plus a secondary `anchors_used` stratification; C1 centred
  within each pair overlap (truth-centred as sensitivity); overlap = intersection of trimmed spans; "same zone" = identical
  zone label; C2 quantiles of |ε|; C3 compared on covered seconds; 10-min clock blocks shared by all pairs; shared-excursion
  definition. After results (reporting only): fix-weighted 1-s RMS in the reproduction, an analytic check of C3, findings.

## Verification

- Selftest (synthetic, 4 still tags, piecewise-constant 1-s processes): C1 recovers a planted 50 % common-mode share (0.499
  [0.488, 0.510]), the independent tag's pairs 0.001, the OU lag-1 decay 0.456 vs 0.452; C2's R = 0.707 vs √½ and 1.000 for
  the independent pairs, SD of the distance error 2.996 vs 3.000; C3 ratios 0.867 vs √0.75 (variant z), 0.883 vs √(7/9)
  (variant a), the independent tag × 1.289 vs √(5/3) (no improvement) and 0 coverage in variant z; a planted 30-s 20-in common
  excursion is the top cluster at the planted time with the right tags; zone pairing, the ≥ 30-s overlap rule (23 s dropped,
  38 s kept), anchor-loss categories and `anchors_list` parsing on planted cases; verdict "material" with, "not material"
  without a common mode.
- Reproduction: 4,160 segments re-read, 0 fix-count mismatches, truths recomputed to 4e-5 in; fix caches matched every track
  fix (0 missing, 0 `anchors_used` mismatches). 1-s still RMS ≤ the audit's per-fix RMS for raw (pooled calm | rain 3.16 | 4.72
  vs 5.57 | 7.74 in); for B2 the 1-s value is 0.0–1.7 % higher (1.62 | 2.67 vs 1.60 | 2.65) because the 1-s grid weights
  every second equally while dropout seconds have larger errors — fix-count-weighted it is lower (1.57 | 2.63) for every tag.

## Results (cohort 2026c, joint stillness: 5,218 pair overlaps ≥ 30 s, 91.3 pair-hours — calm 68.1, rain 23.2; 99 % of it with both tags in a house)

- **C1, is the error shared?** Same-zone (practically same-house) vector correlation of B2 residuals, calm | rain: 1 s 0.06
  [0.05, 0.07] | 0.33 [0.14, 0.46]; 10 s 0.04 [0.02, 0.06] | 0.27 [0.09, 0.39]. Different houses (calm) 0.03 [0.01, 0.04] at
  10 s; different houses / house–outside in rain rest on 3–8 blocks (unreliable CIs). Raw is similar (10 s 0.04 | 0.24). In
  rain the shared part is larger along the WISER x axis (B2 1 s ρ_x 0.47 vs ρ_y 0.22; a frame-axis statement only). Lags:
  raw 1-s cross-correlation falls to ≈ 0 at ±1 s; truth-centred values equal the overlap-centred ones within 0.02.
- **Anchor sets.** Same house, rain, raw 1 s: ρ_v 0.55 in the 6.5 % of seconds when both tags lost the same listed anchor vs
  0.24 when neither lost one (Δ +0.31 [−0.09, +0.46]); calm Δ +0.06 [+0.02, +0.12]. With both tags using < 8 anchors: rain
  ρ_v 0.33, Δ +0.21 [+0.07, +0.26] vs neither low. Anchor 104 accounts for most shared losses (2.3 % of joint seconds, ρ_v
  0.41 raw / 0.53 B2).
- **Shared excursions** (both raw 10-s residuals ≥ 12 in): 33 of 281,313 joint pair-seconds (0.012 %), 11 clusters, **all on
  2026-09-10 between 09:46 and 10:04** (rain day; tags SF07, SF08, SF09, SF10, SF12; the two tags' mean residual vectors
  aligned, cos 0.89–1.00, in 10 of 12 events); anchor 104 was lost by both tags in 42 % of their seconds vs 2.4 % of all joint seconds (enrichment 17.8; anchor 12:
  4.4) and anchors_used fell to 5–7.5. A pointer to an anchor-side cause, not a correction.
- **C2, distance precision (1-s distances of still pairs).** B2 error p95 |ε| = 3.12 [2.88, 3.53] in (calm 2.68, rain 4.62;
  same house 3.58 [3.18, 4.13], different houses 2.38 [2.23, 2.53]; truth < 14 in 3.38, 14–48 in 4.18, > 48 in 2.38), SD
  1.61 in, bias +0.13 in; raw p95 5.58 in, B2′ 2.98 in. Cancellation is small: R = 0.88 [0.82, 0.94] (calm 0.96, rain 0.81;
  same house 0.86, different houses 0.99). A single 1-s B2 distance resolves ≈ 3.1 in at 95 % (two independent ones ≈ √2 ×),
  for still animals mostly in the houses; the 14-in rule is unchanged.
- **C3, leave-one-tag-out differential correction.** Coverage 71.5 % (z) / 84.8 % (a). It **worsens** the target on average:
  B2 z 1-s RMS +18.0 % [+9.2, +27.0], drift p90 +30.9 %, median +45.9 % (calm RMS +33.1 %, rain +1.9 % [−5.6, +16.1]); raw
  and variant a likewise. The equal-noise model (each reference removes its share of the common mode but adds its own
  independent error; break-even ρ = 1/(n̄ + 1)) predicts × 1.28 calm / × 0.99 rain vs observed × 1.33 / × 1.02. It removes the
  shared episodes (B2 z ≥ 12-in events 6 → 2; rain 5 → 0).
- **09-10 09:48 case** (± 5 min, certified still seconds): the displaced tags improve with the correction (B2 1-s RMS SF07 8.7 →
  5.6, SF08 8.5 → 5.8, SF09 7.2 → 5.2 in), the undisplaced get worse (SF10 6.1 → 7.7, SF12 1.4 → 6.1).

## Headline definitions (full set in the report)

- **Residual** $\mathbf e^{(L)}_i(g)=\operatorname{med}\{\hat{\mathbf p}_k: t_k\in[g-L/2, g+L/2)\}-\mathbf c_{\sigma_i}$, $L$ = 1 s (≥ 2
  fixes) or 10 s (≥ 10 fixes), integer seconds of the IMU-aligned clock, windows inside the trimmed segment; $\mathbf c_\sigma$ =
  the audit's truth (median raw fix). Where WISER puts a still head relative to where it is (in).
- **Vector correlation** $\rho_v=\operatorname{tr}\mathbf S_{ij}/\sqrt{\operatorname{tr}\mathbf S_{ii}\operatorname{tr}\mathbf S_{jj}}$, $\mathbf S$ =
  pooled cross-products of the overlap-centred residuals of two simultaneously still tags. = the common-mode share of variance
  under $\mathbf e = \mathbf m + \mathbf n_i$ with equal independent variances; 0 = independent, 1 = identical errors.
- **Distance error** $\varepsilon = \lVert\tilde{\mathbf p}_i-\tilde{\mathbf p}_j\rVert-\lVert\mathbf c_{\sigma_i}-\mathbf c_{\sigma_j}\rVert$ (in);
  **R** $=\mathrm{SD}(\varepsilon)/\sqrt{\mathrm{Var}(\mathbf e_i\cdot\mathbf u)+\mathrm{Var}(\mathbf e_j\cdot\mathbf u)}$, $\mathbf u$ = unit vector
  between the truths; R < 1 = shared error cancels in the distance.
- **Differential correction** $\mathbf v_i(g)=\mathbf e^{(1)}_i(g)-\operatorname{mean}_{j\in J_i(g)}\mathbf e^{(1)}_j(g)$, $J_i(g)$ = the other tags
  certified still with a valid 1-s residual at $g$ (z: same zone label; a: any); relative change = θ(corrected)/θ(uncorrected) − 1
  on the covered seconds, 95 % paired block-bootstrap CI (10-min clock blocks, 1000 resamples).

## Caveats

Joint stillness is almost all inside the houses (often huddles), so common mode between distant tags and in the open field is
barely sampled; each segment's truth is its own median, so an offset constant over a segment (and, for C1, over an overlap) is
invisible — the distance error and the correlations are lower bounds. Rain is three weather episodes. `anchors_list` is a
superset of the anchors used. Distances only, in the unverified WISER inch frame; moving-animal distances have no truth here.

## For the main session (not done here, by the boundaries of this task)

- `CLAUDE.md` → WISER code map, `wiser_baseline` row: add `analyze_wiser_common_mode --cohort 2026c` (step C: cross-tag
  common mode during joint stillness from the failure audit's run, C1 correlation + anchors_list + shared excursions, C2
  pairwise-distance precision, C3 leave-one-tag-out correction; config `configs/wiser_common_mode_<c>.json`; pointer
  `run_manifest_common_mode_<c>.json`; result 10-03: **not material**; B2 still-pair distance error p95 3.1 in; the only shared
  ≥ 12-in excursions are the 09-10 09:46–10:04 episode with anchor 104 lost) and `analyze_wiser_common_mode.py --selftest` to
  the self-test column.
- `implementation_plan/README.md` and `change_log/README.md`: index the plan and this entry.
