# Route-Vocabulary Validation — falsifying "discrete shared route vocabulary" (Stage 1)

## Context

Phase B (`route_motifs_2026-06-28_to_2026-07-10`) established route **recurrence** (~97% of bouts
have a near-identical partner) and that recurring routes are **shared** across animals. But recurrence
≠ the stronger claim the field observation implies — that continuous 2D movement compresses into a
**finite, shared, out-of-sample route vocabulary** (`trajectory_i ≈ prototype_{m_i} + small residual`).
Clustering output alone cannot prove discreteness: any continuous space partitions into clusters. The
evidence must come from **held-out compression, cross-animal generalization, repertoire closure, and
endpoint-vs-shape separation** — and the goal is to *falsify*, not confirm.

**Config cross-check (`configs/behavioral_policy_modules.yaml`).** This question is **Module 11
(route_corridor_selection), status ⛔ blocked** on the unverified inch frame — its `language_overclaim`
bans *"'route choice'/'navigation'/directional/metric route claims"* — and **Module 4** (coarse path
only, "endpoints yes, fine path no"). So: (1) positive conclusions are **capped at topological/relative
language**, never a metric/physical-road vocabulary; (2) the expected verdict is **B/C/D, not A**;
(3) the endpoint-vs-shape test (A4) is exactly the Module 6 (endpoints, *allowed*) vs Module 11 (path,
*blocked*) separation. The roadway-camera audit stays **UNDONE** (needs georeference).

**Scope (user-directed):** Stage-1 core = audit + A1, A2, A3, A4, A5(one strong null); A7 kept as
*supplementary, not verdict-critical*. A6/full-null-battery/A8/policy are gated on the decision-boundary
analysis. Grammar is not implemented before discreteness, compression, and cross-animal generalization
are established.

**Scope correction (2026-07-11, mid-run):** the 3-second-filtered "route bouts" are NOT natural
locomotor units — their duration/displacement scale is imposed by the `min_bout_s=3` + `min_disp_in=15`
filter. So they are treated as a **provisional baseline representation** and every conclusion is labelled
**"conditional on the original 3-second-filtered bout segmentation."** The code is refactored to accept
pluggable trajectory-unit tables (`src/trajectory_units.py`: `original_3s_filtered_bouts` implemented;
`validated_locomotor_legs` / `pause_merged_episodes` pending the decision-boundary analysis) with one
schema, so segmentations can later be compared as *representations* (`run_core_battery`). A positive
result is NOT evidence of route tokens until re-tested on validated legs. STOP after the provisional
verdict.

**Adversarial verification (2026-07-11):** a 5-lens skeptic workflow + adjudicator (independently
reproduced the numbers) confirmed the verdict letter **C is robust** (NOT-A unbreakable), and flagged
must-fix hygiene issues now applied: (1) removed the tautological "endpoints explain 100%"
(`frac ≡ 1.0` by construction) → `endpoint_share` compares two error *reductions*; (2) reconciled the
Definitions block to the code; (3) replaced the binning-biased absolute-location shape test with a FAIR
endpoint-registered (pose-normalized) test vs a matched null → resolves the `shape_beyond_endpoints`
vs `beats_geometry_null` contradiction (there IS a small reusable *continuous* low-dim shape, not a
discrete vocabulary); (4) robust `novelty_saturates` tail rule + B-as-live-alternative caveat;
(5) A2 excludes same-held-out-night other-animal bouts (social-following leak) + multi-seed CIs;
(6) A7 forward/reverse size-confound stated; (7) MDL `dict_beats_pca` flagged not load-bearing.

## Part 0 — Phase-B audit corrections (done; edit + document, not silent)

Sign-convention audit completed (read-only, verified in `src/trajectory_stereotypy.py`): code
`observed_gap_in`, the z-score, and the report Definitions block all use `g = mean(other_nn) −
mean(self_nn) = −5.25` consistently. Two real defects + one naming hazard, corrected in place in
`outputs/.../route_motifs_report.md` **and** the report-generating driver `scripts/analyze_route_motifs.py`
(so future regenerations stay correct), all numbers preserved:

- §2 prose relabelled: "self−other gap −5.25" → `g = mean(other_nn) − mean(self_nn) = −5.25 (negative ⇒
  shared)`.
- §2 interpretation: "Since z>2 … weak individual residual" → **"z = 1.84 did NOT reach the prespecified
  z>2 threshold, so this analysis does not establish an individual-specific route residual; shared
  corridors dominate (g<0)."**
- Leakage caveat added to §1/§3: recurrence uses a **globally-pooled** NN dictionary (future nights
  eligible; no same-animal/same-night/adjacent-bout exclusion), so night-1 recurrence is
  **retrospective/global-dictionary** and 97% is an **upper bound**.
- Per-animal CSV column `self_minus_other_in` = `self − other` = −gᵢ flagged (do not conflate with g).

## Part 1 — New subsystem (Stage 1)

**`src/route_vocabulary.py`** (numpy + scipy + sklearn; reuses `ts.path_distance_matrix`,
`ts.cluster_paths_leader`). Out-of-sample dictionary primitives — never score a dictionary on its own
training data: `cross_distance`, `assign`/`assign_full`, `learn_leader_dictionary` (leader-medoid),
`kmeans_dictionary`, `global_mean_prototype`, `endpoint_line_paths` (chord), `endpoint_key` +
`endpoint_conditioned_recon`/`endpoint_conditioned_multi`, `pca_reconstruct`, `coverage`/`novelty_frac`/
`error_summary`, `mdl_bits` + `pca_mdl_bits` (the correct discrete-vs-continuous test: K means always
span a (K−1)-affine subspace so PCA ties on error by construction — decide by MDL, where the discrete
code pays only log₂K bits/path vs M coefficients/path), `bic_gaussian`, `brownian_bridge_null`
(endpoint-+-wiggle-preserving geometry null), and `decide_verdict` (A/B/C/D).

**`scripts/analyze_route_vocabulary.py`** (run under anaconda3, `KMP_DUPLICATE_LIB_OK=TRUE
OMP_NUM_THREADS=1`). Mirrors the Phase-B load/clean/night-window(21→4)/`apply_tag_cutoffs`; regenerates
paths in-memory via `ts.extract_route_bouts` (CSV has only endpoints). Analyses: **A0** support/kill-gate,
**A1** cumulative-training temporal held-out dictionary (acquisition curve), **A2** leave-one-animal-out
(`E_other` vs `E_own` vs geometry-null `E_null` vs endpoint-only, count-matched), **A3** compression/MDL
K-sweep {1..512} vs PCA-MDL, **A4** endpoint-vs-path-shape decomposition (global→chord→endpoint-mean→
endpoint-multi→route-dict), **A5** endpoint-preserving Brownian-bridge geometry null, **A7** first-night
repertoire closure (forward/reverse + within-night-0 cumulative windows). Derives the criteria booleans →
`decide_verdict` → interim verdict A/B/C/D; writes tables, plots, `validation_report.md` (with claim
table + Part-0 audit section + definitions), `run_manifest.json`, `README.md`.

**`scripts/selftest_route_vocabulary.py`** — 4 planted scenarios exercising the real driver analyses:
discrete shared vocabulary → A, spatial graph → B, structureless continuum → C/D, global-dictionary
leakage → in-sample ≫ held-out; plus A/B/C/D boundary unit tests. Exit-coded PASS/FAIL.

**Output** `outputs/route_vocabulary_validation_2026-06-28_to_2026-07-10/` (git-ignored): `README.md`,
`validation_report.md`, `run_manifest.json`, `tables/` (temporal_holdout, leave_one_animal_out,
compression_model_comparison, endpoint_conditioned_results, null_model_results, repertoire_closure),
`plots/` (dictionary_size_vs_test_error, mdl_vs_dictionary_size, cumulative_novel_motifs,
temporal_holdout_coverage, endpoint_vs_route_model, real_vs_geometry_null, first_night_acquisition).

**Docs:** this file; `change_log/2026-07-11-route-vocabulary-validation.md` after verification;
⚠️ candidate row in `ANALYSIS_STATUS.md`. Every derived quantity defined formula + plain text per
`/analysis-definitions`.

## Guardrails
Never score a dictionary on its own training data · never use future nights for night-1 claims · match
dict size + training-bout counts in every comparison · WISER inch frame UNVERIFIED → topological/relative
language only, **no metric/physical-road claims** (Module 11 blocked) · positive verdict capped at B/C
unless *all* A-criteria hold · O(N²) DTW/Hausdorff only on logged subsamples (no silent caps) · fixed
seeds · whole-night = outer CV block · roadway-camera audit stays UNDONE.

## Verification
1. `python scripts/selftest_route_vocabulary.py` → PASS on all planted scenarios + A/B/C/D boundaries.
2. Smoke: `analyze_route_vocabulary.py --max-nights 3`.
3. Full run → interim verdict A/B/C/D; then **STOP for review**.
4. Dispatch the `wiser-measurement-auditor` subagent on the output dir before promoting any finding.
5. A6 (bootstrap stability) + full null battery + A8 (grammar) only if Stage 1 leaves the vocabulary
   claim viable.
