# Change log — Trajectory stereotypy, stabilization & inter-animal correlation (Phase A)

**Date:** 2026-07-07 (motifs added 2026-07-08)
**Status:** ⚠️ candidate. **Fully implemented** — Phase A (stabilization + shared-road controls),
Phase B following (stable-pairs-vs-herd), and Phase B **route motifs** (stereotypy confirmation), all
self-tested, run on all nights, audited. The motif clustering is numpy-only (mean-pointwise + Hausdorff
+ DTW), so no `scipy` was needed.
**Plan:** [implementation_plan/2026-07-07-trajectory-stereotypy.md](../implementation_plan/2026-07-07-trajectory-stereotypy.md)

## What was added

- **New module** `wiser/src/trajectory_stereotypy.py` — a thin analysis layer on
  `wiser_analysis_utils` (does not modify that ~3700-line module): multi-day incremental-backup
  loader with dedup, a cross-midnight night window, per-night per-animal occupancy maps, a
  day-to-day stabilization curve, a pooled shared-corridor map + residual individual maps, and the
  control battery (animal-label permutation, residual/shared-density expectation, circular-shift
  time-shuffle null, day-shuffle null, synchronous time-coupling).
- **New driver** `wiser/scripts/analyze_trajectory_stereotypy.py` (Phase A).
- **New self-test** `wiser/scripts/selftest_trajectory_stereotypy.py` (offline,
  synthetic, exit-coded) — PASS.
- Outputs → `wiser/outputs/trajectory_stereotypy_2026-06-28_to_2026-07-06/`.

## Method (Phase A)

Nights 2026-06-28 → 07-05, night window **21:00–05:00 EDT**, 5 core animals (Sova/12409 removed
2026-06-29 15:00, excluded; tunnel ROI auto-expires 2026-06-29 07:00). Pipeline: multi-day dedup
load → `convert_timestamps` → `add_speed` → `add_validity_flags` → `apply_tag_cutoffs` →
cross-midnight night window. Then per-night per-animal occupancy/path-density maps, stabilization
similarity (consecutive-night + vs a late-window reference), a pooled corridor "road" map, residual
individual maps (animal occupancy ÷ pooled density), and inter-animal similarity with the shuffle/
permutation control battery. Working **jitter floor = documented ~7 in median (p95 ~15 in)**; the
transferred `tag_reports_2026-06-30` baseline measures per-tag p50 ~3.4 in / p95 ~14.7 in (precision-
optimistic — reported as a detail, not cited as the floor). Occupancy bin 8 in (≥ floor).
Weather/fireworks/truncation flagged, not regressed out.

## Load-correctness finding (important)

The daily `*.csv.gz` incremental backups **overlap** (`06-30` is a cumulative snapshot dump that
already contains 06-28/06-29; `07-01…` are true increments). Deduping must use the composite key
**`(shortid, ts_raw, x, y)`**, NOT `reportid`: verified that `reportid` is per *report cycle* and is
shared across different animals' fixes (82k reportid groups span multiple `shortid`), so deduping on
`reportid` would silently drop ~94k distinct fixes. With the composite key the 9-file load yields
**12,459,676 unique fixes** (matches the 07-06 snapshot total 12,459,691 to within 15 rows);
2,235,668 backfill duplicates removed. Logged in `cleaning_log.md`.

## Key results (candidate)

- **Stabilization: yes.** Mean occupancy similarity-to-late-reference rises **0.14 → 0.96** from the
  06-28 release night to 07-05; big jump by 06-29, a transient dip ~07-02, convergence to ~0.95+ by
  07-04/07-05. `gap_frac` stays <1.5% on every night (incl. wet nights) so the curve is **not**
  dropout-driven. **Classify: behavioral (spatial reuse), not proof of memory.**
- **Shared vs individual: mostly SHARED.** Raw inter-animal occupancy cosine ~0.90 and ROI-edge
  cosine ~0.95, but **residual Pearson collapses to ~ −0.01** after dividing out the pooled corridor,
  and animal-label permutation shows **0/10 pairs above the shared-pool null**, **4/10 below** (all
  four are Dormi pairs → Dormi is the one mild individual outlier). **Classify: shared-road /
  environment is the primary driver; individual route habit weak/candidate (Dormi only).**
- **Real-time coupling: present but environmental, not dyadic.** All 10 pairs beat the circular-shift
  null on synchronous xy-correlation and proximity (z≈4–5), but **0/10 beat the day-shuffle null**
  (which preserves each animal's diurnal/spatial habit). Uniform across pairs, no standout dyad ⇒
  common-drive/shared-road, **not** specific social following. **Classify: mixed → environment.**
- **Caveats:** the top ROI-transition edges (house↔food) are an artifact — `food_1/2` are co-located
  with `house_1/2` in the inch frame (jitter flips, not travel); trust house↔house / house↔refuge
  edges. Night 07-05 truncated (~25% fewer fixes). 07-04 fireworks excluded from time-coupling. All
  spatial structure is in the **UNVERIFIED inch frame** — no directional/physical claims.

## Phase B — following structure (stable pairs vs herd)

Prompted by the field observation of following/parallel travel. Built on `w`'s validated
`following_*` suite (lag-aware, heading-aware, R = 3× jitter floor = 24 in, circular-shift null);
new module helpers (`per_night_following`, `undirected_pair_scores`, `specificity_summary`,
`stability_summary`, `leadership_consistency`, `group_cohesion`) + driver
`scripts/analyze_following_structure.py` + selftest scenarios (planted dyad vs planted herd, PASS).
Outputs → `outputs/following_structure_2026-06-28_to_2026-07-06/`. 07-04 fireworks excluded;
07-03/07-05 carry the refuge_4 burrow UWB-dropout regime (affects resting fixes, moving bouts less).

- **Co-movement is HERD / promiscuous, not stable dyads.** Reported **per night** (not averaged):
  on **7/7 nights** a majority (7–10/10) of pairs beat their circular-shift null, scores are low and
  spread (Gini 0.15–0.29), and the **top pair reshuffles** — **4 distinct top pairs over 7 nights**
  (`specificity_by_night.csv`; consecutive-night Spearman 0.11). **Classify: environment /
  shared-road; no bonded pairs.**
- **Sen (12395) leads on most nights, but not exclusively.** Per-night leadership
  (`per_night_leadership.csv`, `plots/leadership_by_night.png`): Sen is the top leader on **5/7
  nights** (leads 4/4 of its pairs on 4 of them); **Siesta leads on 07-01 and 07-03**. The top pair
  *involves Sen* on 6/7 nights. So a **Sen-dominant (not absolute) leadership hub**, consistent with
  Sen's observed dominance (won fights, field notes 07-02/07-04) — the averaged view had over-stated
  it as "all pairs." Longest lagged-following episodes are *others-trailing-Sen* at 1–2 s lag, cos
  ≈ 0.9–1.0. **Classify: candidate dominant-individual leadership (not a dyad).**
- **Movement is SEQUENTIAL.** Any pair is moving *at the same time* only **~1.25%** of grid-seconds
  (`simultaneity_summary.csv`); animals mostly move one at a time (release night 06-28 higher ~2–3%,
  then settles). So the "following" is **re-use of a shared corridor at different times** with weak
  lag-following, not synchronized side-by-side herd travel — this reconciles the video (reads as
  following) with the shared-road result.
- **Video bridge:** `top_following_bouts.csv` — 49 lagged-following episodes with local-EDT start
  times for cross-checking against the observed episodes (longest ~21 s, Sen-led).
- **Limits:** n=5 → 10 pairs (gross structure only); inch frame UNVERIFIED (leader = temporal order,
  not geometry); WISER cannot separate social attraction from independent same-route/same-time use.

## Phase B — route motifs (stereotypy confirmation)

Direct test of the ORIGINAL question at the path-shape level (social coupling is resolution-limited;
route-scale stereotypy is not). New module helpers (`extract_route_bouts` arc-length-resampled paths,
`path_distance_matrix` mean/Fréchet, `hausdorff`, `dtw_distance`, `cluster_paths_leader` compact
non-chaining clustering, `recurrence_fraction`, `motif_stereotypy`, `individual_vs_shared`) + driver
`scripts/analyze_route_motifs.py` + selftest (planted repeated route vs random routes, PASS). All 8
nights, 1063 route bouts (displacement > 15 in so shape ≠ jitter). Outputs →
`outputs/route_motifs_2026-06-28_to_2026-07-06/`.

- **Trajectories ARE strongly stereotyped.** Recurrence (fraction of bouts with a near-identical
  partner) = **80% at 1.5× jitter, 95% at 3× jitter (21 in), 100% at 6×**. 1063 bouts → **208 compact
  motifs**; the **top 10 hold 27%**; the top motifs are used by **all 5 rats on all 8 nights**.
  **Classify: behavioral — recurring route motifs confirmed.**
- **Shared-dominant, weak individual residual.** Per animal, nearest route is usually *another*
  animal's (`other_nn` ≈ 9 in < own-past `self_nn` ≈ 15 in) ⇒ shared corridors dominate. But
  own-route self-similarity beats the animal-label permutation null (**z = 3.12**) ⇒ a faint (~1 in)
  individual signature atop the road. Matches Phase A. **Classify: mixed → shared-dominant.**
- **Present from night 1, NOT developing.** Recurrence is **~96% on the release night** and flat
  (91–98%) across all 9 days — the repertoire is set by paddock geometry immediately, not learned.
  Motif entropy stays high (~0.98): animals use a **diverse set of recurring shared routes**, not one
  obsessive loop (06-29 the one more-concentrated, hotter night).
- **Limits:** endpoints mostly `open→open` (bouts are corridor segments, not ROI-to-ROI trips);
  single-linkage chains at this density (switched to leader clustering); inch frame unverified (motifs
  internally consistent, no physical labels); "stereotyped" ≠ memory (WISER shows reuse, not cause).

## Verification

- `python scripts/selftest_trajectory_stereotypy.py` → PASS (loader dedup on the composite key incl.
  a shared-reportid multi-tag survivor; cross-midnight night labeling; residual test collapses a
  planted shared road while a planted individual survives; stabilization curve rises; a planted
  coupled pair beats the circular-shift and day-shuffle nulls while an independent pair does not).
- Full run on all 8 nights (~3 min in the `cv` env; Python 3.11 / pandas 3.0 / numpy 2.4). Coverage
  cross-checked against `Wiser_backup/backup_log.txt` (unique-fix total matches the 07-06 snapshot).
- Audited by the `wiser-measurement-auditor` subagent →
  `outputs/audit/wiser_audit_trajectory_stereotypy_2026-06-28_to_2026-07-06.{md,json}`. Verdict:
  *partially auditable / weaker provenance than CV, but a disciplined run — headline supported, no
  over-claim.* Every number reproduced from the CSVs (residual Pearson −0.0147; label-perm 0/10 above,
  4/10 below, all Dormi pairs; circular-shift 10/10; day-shuffle 0/10 proximity). Its two text fixes
  (cite the documented ~7 in floor not the measured 3.39; day-shuffle 2/10 marginal on xy-corr) are
  applied above. Provenance gaps it flagged: no per-run `measurement_context` sidecar / per-row
  `mc_run_id` (WISER-wide, not this run); `calculation_error`/`battery_voltage` loaded but not gated.

## Definitions (headline quantities — full list in each report's `## Definitions`)

Units: **inches**, WISER UNVERIFIED offset frame. Symbols: $H_a$ = animal $a$'s occupancy histogram
(bin $\ge$ jitter floor), $\tilde H$ its box-blur; $\mathbf{p}_i^{(k)}$ = $k$-th point of bout $i$'s
arc-length-resampled path; $\mathbf{x}_A(t),\hat{\mathbf u}_A(t)$ = position / unit heading on a 1 s grid.

- **Occupancy similarity** $\cos(a,b)=\langle\tilde H_a,\tilde H_b\rangle/(\lVert\tilde H_a\rVert\lVert\tilde H_b\rVert)$ — overlap of two space-use maps, $[0,1]$ (Phase A stabilization uses this vs a late-night reference).
- **Residual map** $r_a[c]=(\tilde H_a[c]/\!\sum\tilde H_a)/(\tilde H_{\text{pool}}[c]/\!\sum\tilde H_{\text{pool}}+\varepsilon)$ — animal occupancy with the shared corridor divided out; residual **Pearson** ≈ 0 ⇒ similarity was the shared road.
- **Follow score** $f_{A\to B}(\ell)=\dfrac{\#\{t:\text{mov}_A(t)\wedge\text{mov}_B(t{+}\ell)\wedge\lVert\mathbf{x}_B(t{+}\ell)-\mathbf{x}_A(t)\rVert<R\wedge\hat{\mathbf u}_A(t)\cdot\hat{\mathbf u}_B(t{+}\ell)>0.5\}}{\#\{t:\text{mov}_A(t)\wedge\text{mov}_B(t{+}\ell)\}}$; $R=3\times$ jitter floor $=24$ in; peak over lags $\ell\in[1,30]$ s.
- **Route distance** $D_{ij}=\frac1L\sum_k\lVert\mathbf{p}_i^{(k)}-\mathbf{p}_j^{(k)}\rVert$ and **recurrence** $R(\tau)=\frac1{|B|}\sum_i\mathbb{1}[\min_{j\ne i}D_{ij}\le\tau]$ — fraction of routes with a near-identical partner within $\tau$; $\tau\in\{1.5,3,6\}\times$ jitter floor.
- **Individual-vs-shared** gap $g=\overline{o}-\overline{u}$ (other-NN − own-other-day-NN route distance); **null** $z=(g_{\text{obs}}-\mu_{\text{perm}})/\sigma_{\text{perm}}$ over animal-label permutations; $z>2$ ⇒ own-route similarity beats chance.
- **Nulls** (all $z=(\text{obs}-\mu)/\sigma$): **circular-shift** (roll one track by a random 5–20 min — breaks real-time alignment, keeps habit); **day-shuffle** (pair $A$'s night with $B$'s other nights); **label-permutation** (shuffle animal identities). Credible when $z>2$.

Per the `.claude/skills/analysis-definitions` convention (formula + text for every quantity).

## Follow-ups (still deferred)

- **Video cross-check** of the exported Sen-led lagged-following episodes (`top_following_bouts.csv`)
  to confirm active pursuit vs. coincidental same-route use.
- **ROI-to-ROI motifs** — extract bouts anchored at named ROIs (house→water etc.) rather than
  free corridor segments, once the georeference confirms ROI positions physically.
- Sensitivity sweep of the follow radius / heading cutoff (following) and the motif threshold, to
  confirm the herd-vs-hub and stereotypy results are stable to those parameters.
- Structural provenance (shared with the WISER pipeline): a `measurement_context` sidecar + per-row
  `mc_run_id`, per the auditor.
