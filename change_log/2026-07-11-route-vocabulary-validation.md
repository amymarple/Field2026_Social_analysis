# Change log — Route-vocabulary validation (Stage 1) + Phase-B audit corrections

**Date:** 2026-07-11
**Status:** ⚠️ candidate, **PROVISIONAL**. Interim verdict **C** (continuous route manifold, NOT a
discrete shared route vocabulary), **robust across BOTH producible WISER segmentations** — the
3s-filtered bouts AND pause-merged episodes give an identical verdict + criteria. Adversarially verified
+ measurement-audited; endpoints dominate, a small (sub-floor) reusable continuous shape, no discrete
tokens. Validated decision-to-decision legs remain BLOCKED (WISER can't validate boundaries; needs CV).
**New code:** `src/route_vocabulary.py`, `src/trajectory_units.py`, `ts.extract_pause_merged_episodes`,
`scripts/analyze_route_vocabulary.py`, `scripts/compare_route_segmentations.py`,
`scripts/selftest_route_vocabulary.py`.
**Edited (Phase-B corrections):** `scripts/analyze_route_motifs.py` + the generated
`outputs/route_motifs_2026-06-28_to_2026-07-10/route_motifs_report.md`.
**Output:** `outputs/route_vocabulary_validation_2026-06-28_to_2026-07-10/original_3s_filtered_bouts/`
(git-ignored). Runs under `C:\Users\Cornell\anaconda3\python.exe` (scipy + sklearn).

## Why

Phase B established route **recurrence** (~97%) and that recurring routes are **shared**, but recurrence
is not the stronger claim that continuous 2-D movement compresses into a **finite, shared, out-of-sample
route vocabulary** (`trajectory_i ≈ prototype_{m_i} + small residual`). Clustering output cannot prove
discreteness (any continuous space partitions into clusters). This study tries to **falsify** the
vocabulary claim with held-out compression, cross-animal generalisation, endpoint-vs-shape separation,
a geometry-preserving null, and first-night closure — cross-checked against
`configs/behavioral_policy_modules.yaml` (this is **Module 11 route_corridor_selection, ⛔ blocked** on
the unverified inch frame; verdict ceiling B/C, never a metric/directional/physical-road claim).

## Scope correction (bouts are a provisional baseline)

The 3-second-filtered "route bouts" are **NOT natural locomotor units** — their duration/displacement
scale is imposed by the `min_bout_s=3` + `min_disp_in=15` filter. They are treated as a **provisional
baseline representation**; every conclusion is labelled **"conditional on the original 3-second-filtered
bout segmentation."** The battery (`run_core_battery`) is refactored to accept pluggable trajectory-unit
tables (`src/trajectory_units.py`: `original_3s_filtered_bouts` implemented; `validated_locomotor_legs`
+ `pause_merged_episodes` registered but pending the decision-boundary analysis) so segmentations can
later be compared as **representations**. A positive result is **not** evidence of route tokens until
re-tested on validated legs. **Downstream A6 (stability) / A8 (grammar) / policy are gated** on that
analysis and are NOT run.

## Part 0 — Phase-B audit corrections (edited in place, documented, not silent)

Sign-convention audit (verified in `src/trajectory_stereotypy.individual_vs_shared`): code
`observed_gap_in`, the z-score, and the report Definitions all use `g = mean(other_nn) − mean(self_nn)
= −5.25` consistently. Corrected in the report **and** the report-generating driver:
- "Since z>2" (for z=1.84) was **false** → "z = 1.84 did NOT reach the prespecified z>2 threshold, so
  no individual-specific route residual is established; shared corridors dominate (g<0)."
- §2 prose relabelled from "self−other gap" to `g = mean(other_nn) − mean(self_nn) = −5.25 (negative ⇒
  shared)`; per-animal CSV column `self_minus_other_in = self − other = −gᵢ` flagged (do not conflate).
- Leakage caveat: Phase-B recurrence uses a **globally-pooled** NN dictionary (future nights eligible;
  no same-animal/same-night/adjacent-bout exclusion), so the 97% and "stereotyped from night 1" are a
  **retrospective upper bound**, not out-of-sample. The new A1/A7 are leakage-controlled.

## Results (candidate, PROVISIONAL — conditional on the 3-second-filtered segmentation)

1692 units, 13 nights (2026-06-28→07-10), 5 rats (4 from the 07-09 night). **Verdict C** — a continuous
route manifold with useful quantisation; **NOT a discrete shared route vocabulary**. Criteria:
`mdl_has_finite_min=✓, dict_beats_pca=✗, novelty_saturates=✗, loao_generalizes=✓, beats_geometry_null=✓,
shape_beyond_endpoints=✓, endpoint_explains_most=✓`.

- **Dominated by endpoints (locations), not path shape.** The endpoint chord (straight line between each
  route's own start/end) reconstructs held-out routes to **7.88 in** — near the ~7 in jitter floor — and
  beats the K=176 route dictionary (15.72 in) [caveat: the chord uses each route's own 4 endpoint coords,
  so this is not param-matched]. A3 PCA reaches **4.17 in at M=4** ⇒ the route "manifold" is ≈ the 4-D
  endpoint space.
- **A small reusable, low-dimensional CONTINUOUS shape component exists — but no DISCRETE vocabulary.**
  The FAIR scale-invariant (endpoint-registered) shape test: unit-scale shape dictionary **5.81 in** <
  straight segment **7.88 in** and matched Brownian-bridge null **7.58 in** ⇒ `shape_beyond_endpoints=True`
  (corroborated by A5 real 15.72 < null 18.7, and A3 PCA M=4). But there is **no finite-K MDL scale**
  (dict MDL min K=128 = 411 k bits > PCA MDL min 271 k; `dict_beats_pca=False`, and this criterion is
  **not load-bearing** — it flips at the bpp=32/σ=14 corner; A stays blocked by shape+novelty regardless).
- **Shared across animals = the endpoint GRAPH, not a path vocabulary.** LOAO (count-matched,
  same-held-out-night other-animal bouts excluded, 5-seed averaged): E_other ≈ E_own and < E_null
  (`loao_generalizes=True`), but the endpoint chord (E_endpoint ≈ 9 in) ≪ every dictionary (≈ 20 in) —
  what transfers is common locations, not shared curved paths.
- **The repertoire does not close (continuous, not a finite graph).** A1 held-out coverage rises
  0.39→0.88 over 13 cumulative training nights but next-night **novelty does not saturate** (~0.12, not
  →0). Supplementary A7: a night-0-only frozen dictionary covers only **39%** of later routes (forward),
  far below Phase-B's retrospective 97% — the repertoire accumulates; it is **not** fully present on
  night 1 (reverse direction is higher but confounded by training-set size, 108 vs 1584 units).
- **C-vs-B is UNRESOLVED** (measurement audit, below), not merely "B is a live alternative":
  `novelty_saturates` is decided by the 07-08→07-10 splits (n_test 270→120), which coincide with
  **refuge_4 removal (07-07), the south barn-light onset (07-09), and the 5→4 cohort drop (Hypnos
  cutoff 07-09)** — all of which inflate late-night novelty, so "open manifold" cannot be separated
  from regime-induced novelty. The reusable-shape differential that nominally tips C over B is itself
  **sub-jitter-floor** (5.81 in < ~7 in; ~2 in reduction) — a matched-null differential only, never a
  metric size. **What IS robust is NOT-A** — no discrete route vocabulary *resolvable above ~7 in at
  this provisional segmentation* (it does not depend on the regime-confounded closure axis).

## Adversarial verification (5-lens skeptic workflow + adjudicator)

Independent agents reproduced the load/extract/A2/A7 numbers exactly and confirmed the **verdict letter C
is robust (NOT-A unbreakable, no train/test leakage)**. Must-fix hygiene issues, all now applied (letter
unchanged): removed the tautological "endpoints explain 100%" (`frac ≡ 1.0` by construction) →
`endpoint_share` compares two error *reductions*; reconciled Definitions to the code; replaced the
binning-biased absolute-location shape test with the FAIR **scale-invariant** endpoint-registered test vs
a matched null (resolves the `shape_beyond` vs `beats_geometry_null` contradiction); robust
`novelty_saturates` tail rule + B-as-live-alternative caveat; A2 excludes same-night other-animal
near-duplicates + multi-seed CIs; A7 size-confound stated; MDL `dict_beats_pca` flagged not load-bearing.

## Measurement audit (wiser-measurement-auditor, read-only)

`outputs/audit/ROUTE_VOCAB_AUDIT_2026-07-11.md`. Verdict: **partially auditable / weaker provenance than
CV.** The NOT-A rejection and the endpoint-dominance headline are **measurement-sound** (as a
floor-bounded negative). Downgrades applied to the report/manifest: (1) **C-vs-B → UNRESOLVED** (deciding
late nights are regime-shocked on small n_test — refuge_4 removal + barn-light + 5→4 cohort); (2) the
**reusable-shape reduction is sub-jitter-floor** (~2 in < 7 in) → matched-null differential only;
(3) NOT-A bounded to "no discrete vocabulary resolvable above ~7 in at this provisional segmentation";
(4) README + manifest now carry the provisional label, the Hypnos tag-cutoff, `timestamp_method`, and
per-night×animal unit counts. **Provenance limiter (deferred to a separate PR, per the audit):** WISER
has no `measurement_context` sidecar / per-bout `mc_run_id` / fix-level `flag_summary`, so the dropout
burden behind the 1692 units is unquantifiable from the artifacts. LOAO is a weak pass (E_other−E_null
margins ≈ 1 seed-sd) and every held-out night is a late regime-shocked night — re-evaluate closure on
nights ≤ 07-08. Keep **⚠️ candidate / PROVISIONAL**; do not promote or re-tune on this run.

## Segmentation representation comparison (proceed — decision-boundary cross-check + bouts vs episodes)

Cross-checked `decision_boundary_validation/` (2026-07-11): internally consistent, verdict holds — **NO
reliable boundary class at WISER resolution**, so **validated decision-to-decision legs cannot be
produced from WISER** (matched pause-turn +17.9° but a jitter-only null gives +20.4°, and the effect
reverses to −3.1° when headings are well-resolved; the in-motion changepoint detector is 30–77%
false-positive, 4–24% sensitive). The right instrument is **CV pose/keypoints**; the user's CV pipeline
is centroid-based and still in progress → `validated_locomotor_legs` stays **BLOCKED** (`trajectory_units`
status `blocked_needs_cv`).

Its third segmentation, **pause-merged locomotor episodes** (transitive pause-bridging of the 3s bouts —
mechanical, no boundary validation needed), IS producible. Proceeding, I added
`ts.extract_pause_merged_episodes` (5 s pause-merge of the ≥3 s bouts → **1609 episodes**) and ran the
**identical battery** on it, then compared representations (`scripts/compare_route_segmentations.py`).

**The verdict and every criterion are IDENTICAL across bouts and episodes → the conclusion is robust to
unit scale within WISER:**

| metric | 3s bouts | pause-merged episodes |
|---|---|---|
| units (top-40/animal-night) | 1692 | 1609 |
| verdict | **C** | **C** |
| endpoint chord vs route dict (in) | 7.88 < 15.72 | 9.50 < 16.94 |
| endpoint share | 0.99 | 0.98 |
| shape_beyond_endpoints (fair test) | True | True |
| held-out cov ≤21in / last-3 novelty | 0.88 / 0.14 | 0.84 / 0.17 |
| MDL min K / dict_beats_pca | 128 / False | 128 / False |
| LOAO E_other vs E_endpoint chord (in) | 19.6 vs 9.4 | 20.3 vs 10.4 |

At both scales: **no discrete route vocabulary** (no finite-K MDL win over PCA), **endpoints dominate**
(the straight chord beats the route dictionary; endpoint share ~0.98–0.99), and **what generalises
across animals is the endpoint graph, not a shared path vocabulary** (E_endpoint ≪ E_other). Bouts are
marginally more compressible (episodes are longer/curvier). Both capped at 40 units/animal-night (the
comparison is matched on that budget). Outputs: `outputs/.../pause_merged_episodes/` +
`outputs/.../comparison/`. The **definitive** representation test still needs CV-resolved legs.

## Definitions (formula + text)

Units **inches**, WISER native UNVERIFIED offset frame → topological/relative only. Paths are
arc-length-resampled to L=20 points; $D(a,b)=\frac1L\sum_k\lVert a_k-b_k\rVert$ (mean-pointwise).
- **Dictionary / residual:** K prototype paths learned from TRAIN only, frozen; held-out residual
  $r_i=\min_m D(\text{path}_i,\text{proto}_m)$. **Coverage@τ** $=\frac1N\sum_i\mathbb 1[r_i\le\tau]$;
  **Novelty** $=\frac1N\sum_i\mathbb 1[r_i>\theta]$; **novelty_saturates** = last 3 cumulative splits'
  next-night novelty all $<0.15$ and range $<0.08$.
- **MDL** $L(K)=K\,2L\,b_p+N\log_2K+\text{Gaussian residual bits}(\sigma)$; **PCA MDL** swaps the
  assignment term for $N\!\cdot\!M$ coefficient bits/path; **dict_beats_pca** $=\min_K L_{dict}<\min_M
  L_{PCA}$ ($b_p=16$, $\sigma=$ jitter floor, both a priori).
- **Endpoint chord** = straight line between a route's own endpoints. **endpoint_share**
  $=\Delta_{endpoint}/(\Delta_{endpoint}+\Delta_{shape})$, $\Delta_{endpoint}=E_{global}-E_{chord}$,
  $\Delta_{shape}=\max(0,E^{pn}_{straight}-E^{pn}_{shapedict})$ (two error reductions; endpoints_explains_most
  = $\ge0.8$).
- **Scale-invariant shape test** = translate+rotate+scale-normalise each path (remove the full endpoint
  pair → unit-scale curvature), cluster at $\theta_n=\theta/\mathrm{median(disp)}$, residuals scaled back
  to inches; `shape_beyond_endpoints` = unit-scale shape dict beats BOTH the straight segment and a
  matched Brownian-bridge null by $\ge0.5$ in.
- **LOAO:** $E_{other}$ = count-matched other-animals dict (same-held-out-night excluded, 5-seed mean) on
  a held-out animal's last night; $E_{own}$ = own earlier-night dict; $E_{null}$ = Brownian-bridge null
  dict. **Geometry null** = each path → 2-D Brownian bridge between its own endpoints, RMS deviation
  matched (endpoints + wiggle amplitude preserved, template destroyed).

## Verification

- `python scripts/selftest_route_vocabulary.py` → **PASS** (planted discrete→A, spatial-graph→B,
  continuum→C/D, leakage gap, and all A/B/C/D decision boundaries).
- Full run → verdict C; report + tables + plots + manifest under the `original_3s_filtered_bouts/` subdir.

## Follow-ups (gated / blocked)

- **`validated_locomotor_legs` BLOCKED on CV** — the decision-boundary analysis (cross-checked) shows
  WISER cannot validate decision boundaries; needs CV pose/keypoints. The user's CV pipeline is
  centroid-based and in progress; WISER Stage-2 motion validation is parked pending it. When CV legs
  exist, drop them into the `trajectory_units` schema and re-run `scripts/compare_route_segmentations.py`
  for the definitive third-representation comparison.
- **A6 stability, full null battery, A8 grammar, policy** — still gated: discreteness was REJECTED at
  BOTH producible scales (bouts + episodes), so a discrete-vocabulary stability/grammar analysis is moot
  on WISER units; revisit only if CV-resolved legs reopen the discreteness question.
- **Roadway camera audit — still UNDONE** (needs the pixel↔field georeference; no physical-road claim).
