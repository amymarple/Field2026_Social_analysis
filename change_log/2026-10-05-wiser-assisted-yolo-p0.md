# 2026-10-05 — WISER-assisted YOLO, phase 0: WISER → CH01 mapping accepted, fixed-spot presence sealed, suspected YOLO misses

Plan: [`implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md`](../implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md)
(pre-registered; approved "可以试试" 2026-10-05; amendment 1 before results, amendments 2–3 after results). Data map:
[`cv/cv_field/DATA_MAP_c1yolo_wiser.md`](../cv/cv_field/DATA_MAP_c1yolo_wiser.md) (section G). Report:
[`results/2026c/cv_field/reports/cv_field_wiser_assist_p0_2026c.md`](../results/2026c/cv_field/reports/cv_field_wiser_assist_p0_2026c.md).

## What changed

- **New driver** `cv/cv_field/wiser_assist_p0.py` (`--selftest`: 22 checks on synthetic data — known offset and lag
  recovered, negative control fails, selection on the fit blocks only, a scaled WISER makes the similarity win on inner
  validation, B on synthetic object / rat / out-of-support spots, C finds a planted 10-s miss at the right place, the
  report carries no B number, unrelated WISER → not accepted and no B / C files; `--run`). Base Python (scipy, pandas,
  OpenCV); CPU, ≈ 2.5 min.
- **Run** `D:/Field2026_analysis_out/2026c/cv_field_wiser_assist_p0_20261005_2211/`: `mapping.json`,
  `model_selection.csv`, `pairs.csv.gz`, `residuals_test.csv`, `residuals_test_by_x.csv`, `control.json`,
  `lag_profiles.csv`, `support_polygon.json`, `fn_episodes.csv`, `fn_grid.csv`, `wiser_spots.csv` (**sealed**),
  `run.json`, `run_log.txt`. The first run `…_20261005_2158` (model picked on the test blocks) is superseded and marked
  with `SUPERSEDED.txt`; the amended run reproduced its map, its `wiser_spots.csv` (sha256) and its episodes.
- **In repo:** the report, figures `results/2026c/cv_field/figures/wiser_assist_p0/` (`coarse_grid.png`,
  `lag_profile.png`, `test_distances.png`, `fn_map.png`; no B figure), pointer
  `results/2026c/cv_field/reports/run_manifest_wiser_assist_p0_2026c.json`.
- Docs: plan status + amendments, `implementation_plan/README.md`, this entry, `CLAUDE.md` (cv_field map),
  `cv/cv_field/HANDOFF.md`, `cv/cv_field/DATA_MAP_c1yolo_wiser.md` section G.

## Results (CH01, field-PC 2026-09-06 21:00–22:00; the agent did not look at any frame or figure)

**A — mapping accepted.** 4 609 YOLO v5 boxes (conf ≥ 0.5, one frame per second, fixed-spot cells and points outside
CH01's verified support removed) against the six default-track animals outside the houses. Chosen on the fit blocks
only (inner fit 1, 5, 9 / validation 3, 7, 11): similarity (inner-validation median 6.03 → 4.17 in, gain 30.9 %).
Refitted on the six fit blocks: d = (−272.85, −605.80) in, θ = 0.114°, s = 0.9634 about WISER (501.7, 761.1) in,
**L = 0.0 s** (lag cost +10 % / +9 % at ∓ 0.5 s). Test blocks, once: matched-pair residual **median 4.39 in, p90
9.83 in** (89.1 % of 2 472 detections matched within 30 in); **88.5 %** of test detections have an animal within 14 in,
vs **2.9 %** for the WISER + 1 h negative control (its lag runs to the grid edge, cost flat) → both pre-registered
criteria met. The translation alone gives d = (−273.25, −605.40) in, 9.8 in from the d implied by house_2's hand-placed
positions. Only 12 test pairs involve an IMU-still animal, so the still/moving split cannot isolate timing error.
Descriptive: median residuals stay 2.8–5.8 in across the 80-in paddock x bands from 0 to 480 in, signed medians within
± 3.1 in, except detections mapped beyond the walls (2 below x = 0, 36 beyond x = 480: residual 10 in, signed +9 in); 239 of the 285 test detections without an outside animal within 14 in have an
animal WISER places in a house zone.

**B — sealed.** WISER presence at the two fixed spots was written only to `wiser_spots.csv` (122 rows); no B number is
in any report, log, other output or message until the user's verdicts in `fixed_spots_review.csv` are in. The
agreement table is a later step.

**C — suspected misses (proposals, never boxes).** CH01's ground support covers 66.6 % of the paddock. Of 8 925
animal-seconds with a tagged animal outside the houses inside the support, 3 482 (39.0 %) have no box ≥ 0.25 within
20 in; 300 episodes ≥ 3 s hold 2 885 s. One 40-in cell (x 440–480, y 120–160 in) holds 20.8 % of all suspected-miss
seconds (80.9 % of its animal-seconds) while the 106 detections inside it match with median residual 5.0 in — the map is
not off there. Longest episodes: SF08 21:41:41 156 s at pano ≈ (6820, 1180); SF10 21:03:12 108 s ≈ (6820, 1100); SF08
21:58:20 99 s ≈ (1940, 1660); SF09 21:16:04 90 s ≈ (7380, 2020); SF08 21:33:51 76 s ≈ (4020, 220).

## Amendments

1. *Before results* — implementation clarifications (frame per second, WISER interpolation ≤ 5-s gaps, mapping per
   whole second, coarse grid at L = 0, L by the truncated-Huber Hungarian cost, similarity centre, test statistics, IMU
   classes, control, B per-minute rules, C support raster, blinding).
2. *After results* — external review relayed by the user: model and lag chosen on the fit blocks only (inner split),
   chosen model refitted on all fit blocks, test blocks used once; WISER never creates a negative; C = suspected misses,
   never boxes. Old selection (test blocks: 5.54 vs 4.39 in → similarity) and new (inner validation: 6.03 vs 4.17 in →
   similarity) agree; map, L and verdict unchanged.
3. *After results* — descriptive diagnostics (x bands, lag shape, house-zone accounting, top miss cells); no decision.

## Definitions (headline quantities; full set in the report)

Units: inches (paddock = 09-24 calibration frame, origin pole A0; WISER = unverified native frame); seconds.

- **Map** $T(\mathbf w)=s\,R(\theta)(\mathbf w-\mathbf c)+\mathbf c+\mathbf d$ — moves a WISER position onto the paddock;
  the translation model fixes $\theta=0, s=1$. A detection in second $s$ is compared with $T(\mathbf w_j(s+L))$; **lag**
  $L>0$ = the video's nominal time (file-name start + PTS) runs $L$ s behind the WISER/field-PC clock.
- **Residual** $r_i=\lVert\mathbf p_i-T(\mathbf w_{\pi(i)}(s+L))\rVert$ for the per-second Hungarian assignment $\pi$ of
  detections to animals outside the houses (cost = distance capped at 30 in; pairs beyond 30 in dropped) — the
  detection-to-tag distance; truncated at 30 in, read with the matched share.
- **Within-14 share** $f_{14}=\frac{1}{|I|}\sum_i\mathbb 1[\min_j\lVert\mathbf p_i-T(\mathbf w_j)\rVert\le14]$ over all
  test detections — how often a box has some tagged animal within 14 in (= 2 × the ≈ 7-in WISER jitter).
- **Negative control** $\mathbf w^{ctrl}_j(t)=\mathbf w_j(t+3600)$, refitted identically — the chance level of
  $f_{14}$ after a free fit when the animals' spatial density is kept but the correspondence is broken.
- **Selection gain** $g=(\tilde r^{val}_{transl}-\tilde r^{val}_{sim})/\tilde r^{val}_{transl}$ on fit blocks 3, 7, 11
  with both models fitted on 1, 5, 9; similarity iff $g\ge0.10$.
- **Acceptance** $\tilde r_{test}\le14\ \wedge\ f^{ctrl}_{14}\le\tfrac12 f_{14}$ on the test blocks, once.
- **Suspected miss** $\mathbb 1[j\notin\text{houses}\wedge T(\mathbf w_j(s+L))\in\mathcal S\wedge\min_b\lVert\mathbf p_b-T(\mathbf w_j)\rVert>20]$
  with $\mathcal S$ = CH01's ground support and $b$ the sampled frame's boxes ≥ 0.25; ≥ 3 consecutive seconds = an
  episode. A pointer for the user's eyes, never a box; WISER's silence never marks anything empty.

## Not verified / caveats

One calm hour, one camera; the hour is now WISER-touched. The similarity's s = 0.963 (WISER displacements ≈ 3.7 %
longer than paddock ones in CH01's view) is not attributed to WISER or to the exploratory calibration. The 60-mm height
and box-centre-vs-tag offset are inside the residuals. L = 0.0 s is a fitted nuisance parameter at 0.5-s resolution,
not a clock measurement. B is unread by anyone until the user's verdicts exist.
