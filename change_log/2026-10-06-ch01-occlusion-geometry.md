# 2026-10-06 — CH01 occlusion geometry for the WISER-flagged suspected misses (poles, houses)

Plan: [`implementation_plan/2026-10-06-ch01-occlusion-geometry.md`](../implementation_plan/2026-10-06-ch01-occlusion-geometry.md)
(pre-registered; approved "行上吧" 2026-10-06; amendment 1 before results, amendment 2 after results and descriptive only).
Report: [`results/2026c/cv_field/reports/cv_field_ch01_occlusion_2026c.md`](../results/2026c/cv_field/reports/cv_field_ch01_occlusion_2026c.md).
Data map: [`cv/cv_field/DATA_MAP_c1yolo_wiser.md`](../cv/cv_field/DATA_MAP_c1yolo_wiser.md), section H.

## Why

The user watched the phase-0 review clips: part of the suspected YOLO misses are animals hidden by a house or a pole.
A hidden animal is not a detector error and must never become a box.

## What changed

- **New** `cv/cv_field/ch01_occlusion.py` (`--selftest` 11 checks: segment–segment distance and convex clipping against
  brute force, a synthetic pole / gabled house / rat with known hidden, partly and clear points, the 7-in perturbation,
  episode majority and ties, pooled numbers without ids, the mask; `--poles-only`; `--run`). Base Python, ≈ 1.5 min.
- `cv/cv_field/wiser_assist_p0.py`: the box preparation moved verbatim from `run_pipeline` into `prepare_boxes`, and
  `part_c` gained an optional `seconds_out` that only reports its arrays. Phase-0 self-test unchanged (25 + 1 skipped
  without PyAV). The rebuilt `fn_episodes.csv` and `fn_grid.csv` are byte-identical to phase 0's.
- **Run** `D:/Field2026_analysis_out/2026c/cv_field_ch01_occlusion_20261006_1445/`: `occluders.json`, `checks.csv`,
  `visibility_mask.npz`, `miss_seconds_rebuilt.csv.gz` (the per-second table phase 0 had not saved), `pole_edges_revg.csv`,
  `pole_triangulation_revg.csv`, `run.json`, `run_log.txt`; **sealed** `episodes.csv`, `seconds.csv.gz`
  (`SEALED_README.txt`).
- In repo: the report, figures `results/2026c/cv_field/figures/ch01_occlusion/` (`visibility_mask.png`, `class_shares.png`),
  pointer `run_manifest_ch01_occlusion_2026c.json`; docs (plan, both index READMEs, CLAUDE.md, HANDOFF, data map H).

## Results (pooled only; per-episode classes sealed until the user's verdicts in `review_template.csv`)

- **Episodes (n 300): hidden 31 (10.3 %), partly 14 (4.7 %), clear 154 (51.3 %), ambiguous 101 (33.7 %).** Seconds
  (n 3 482): 11.7 / 9.1 / 49.0 / 30.2 %; at the nominal WISER position alone 25.3 % hidden, 9.1 % partly, 65.6 % clear.
- Non-clear episodes by occluder: pole B3 46 (0 hidden, 9 partly, 37 ambiguous), pole B2 32 (13 / 2 / 17), house_2 30
  (13 / 3 / 14), pole C2 19 (all ambiguous), house_1 6 (5 / 0 / 1), poles B4, C1 4 each, B1 3, B0 2. Thin poles a few
  metres away throw shadows narrower than the 7-in WISER uncertainty, so they give partly / ambiguous; the houses and B2
  (0.82 m from CH01) can hide robustly. 30 % of the ambiguous seconds have a 7-in ring crossing a paddock wall (wall-line
  poles C2, C1, B4).
- Visibility mask: 18 976 2-in cells in CH01's support; a rat is hidden (h ≥ 0.8) in 8.9 % and partly hidden in 4.3 %.
- **Poles:** measured lines (pole-check method re-run on rev g, CH01 + CH02) for B1, B2, B3; design grid for the other 12
  (A4's two-height line leaned 23°). At 1.05 m the measured B1–B2 / B2–B3 spacings are 119.8 / 117.3 in against the
  operator's tape 120 / 116 in.
- **house_1** placed from the WISER ROI through the accepted map at (142.0, 114.2) in, ridge 90.1° (9.3 in from the
  calibration's post-move position); its check against the user's 09-04 cohort labels: **125 px, flagged**. The same map
  puts house_2's ROI 7.2 in from its calibrated position (342.4, 117.7): the hand-placed ROI is the error source.
- **Landmark checks** (median px, flag > 20): poles B1 3.0, B3 3.0 (not independent: CH01's labels entered their
  triangulation), house_2 9.8; flagged: house_1 124.8, A0 57.4, C1 58.2, B2 45.5, B0 40.6, C0 24.6. Code check: the
  calibration's own post-move house_1 against the 09-18 labels 19.5 px, consistent with the calibration's fit.

## Definitions (headline quantities; full set in the report)

- **Hidden share** $h(\mathbf p)=\frac19\sum_{k,l}\mathbb 1[\exists O:[\mathbf C,\mathbf q_{kl}]\cap O\neq\emptyset]$ — the share of
  a rat's 9 body points (30 / 60 / 90 mm above the local ground × 0 / ± 40 mm across the line of sight) whose line of
  sight to CH01's centre $\mathbf C$ passes through a pole capsule or a house part. Range [0, 1].
- **Category** of a second: hidden = $h\ge0.8$ at the nominal position and at all 8 positions 7 in away; clear = $h=0$ at
  all 9; partly = nominal $0<h<0.8$; ambiguous = otherwise. **Episode class** = the unique majority category of its
  seconds (ties → ambiguous); **occluder** = the most frequent occluder of its non-clear seconds.
- **Landmark distance** = median pixel distance from the user's densified label points to the projected model edges.
- **Ring crosses a wall**: the animal is within 7 in of a paddock wall (some perturbed positions lie outside).

## Not verified / caveats

Grass, other rats, posture and unsurveyed objects are not modelled (they can hide a *clear* animal). house_1's
position and B2's position along the CH01–CH02 line are the weakest inputs (both flagged). Design-grid poles are vertical
at the 10-ft grid. One hour, one camera; the geometry vs the user's verdicts is a later, separate step.
