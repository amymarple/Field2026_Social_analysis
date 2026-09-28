# cv_field — whole-field CV (CH01–CH04) with an unsupervised active-learning + YOLO detector

**Date:** 2026-07-12 · **Status:** Phase 0 (code + self-tests) implemented this session; Phases 1–3 run on
the data machine / BioHPC. Scope: new subsystem + a new research direction `cv_field`. Medium/large change.

## Why

`cv/` today is a validated single-session **shelter** pipeline (CH05/CH06, detector `rat_feasibility-6`,
val mAP50 0.876) with an audit trail under `results/2026a/cv_shelter/`. There is **no detector for the
whole-field cameras** CH01–CH04, and the `results/2026a/cv_shelter/reports/2026-07-12_cv_merge_plan.md`
already names the intended split: keep `cv_shelter`, add a new `cv_field` direction for whole-field tracking.

This stands up `cv_field` and bootstraps its YOLO detector **from scratch** with an **unsupervised
active-learning labeling loop** (the user's "unsupervised method + YOLO"): embed harvested frames, cluster /
space-fill them, and hand-label only the most *diverse + most uncertain* frames, so a small label budget
yields a strong detector. `cv_shelter` is left untouched.

## Design decisions

- **New subpackage `cv/cv_field/`** (leaves every `cv_shelter` file untouched; matches the merge-plan's
  "`cv_field/` under the `cv/` umbrella"). Drivers import the cohort SSOT through re-export shims
  (`cv/cv_field/output_paths.py`, `cohorts.py`) exactly like `wiser/src/output_paths.py`.
- **Reuse, don't rebuild:** `cv/scan_for_rats.py` (harvest pool + `_gray64`), `cv/train_detector.py`
  (session-split, `--data-root dataset/rat_field --name rat_field` — its `CH0\d` regex already matches
  CH01–CH04), `cv/label_frames.py`, `cv/animal_tracking.py` + `cv/merge_cameras.py` (inference path),
  `cv/field_coords.py` (CH01–CH04 calibs already exist).
- **Active-learning loop.** Round 0 (no detector): pure diversity — embed → choose K by **silhouette**
  (robust on the L2-normalized embedding, where a likelihood BIC over-segments) → one **medoid** per cluster
  → **farthest-point** coverage of the rest. Rounds ≥1 (seed detector): **uncertainty × diversity** via
  uncertainty-weighted k-center `a(f|A) = u^γ·d(f,A)`, `u = max(conf-margin, count-instability-under-flip)`,
  with an `explore_frac` pure-exploration reserve. `--method random` is the equal-budget falsification control.
- **Embedding backends** behind one interface: `yolo` (YOLO11 backbone via ultralytics `.embed`, no new heavy
  dep) with a `gray` (gray64 + numpy-PCA) CPU fallback that makes the selector self-testable; `auto` picks by
  availability. `scikit-learn` added to `cv/environment.yml` but **lazy-imported with a numpy fallback**, so
  the selection loop and the self-test stay numpy-only.
- **Cohort-appendable:** drivers take `--cohort`; bulk (embeddings, per-round CSV, sidecar) → `run_dir`,
  canonical report + PCA coverage figure → `results/<cohort>/cv_field/`, assets (labeled `dataset/rat_field`
  + weights) off-repo with `cv/cv_field/assets_manifest.json`.
- **Provenance:** `cv/measurement_context.py` gets **additive** `embedding=`/`active_learning=` kwargs — absent
  for shelter runs so their manifest + `mc_run_id` stay byte-identical (guarded in the self-test).
- **Milestone audit** = a whole-field-specific `field_audit.py` + `FIELD_AUDIT_CHECKLIST.md`, **not** the
  shelter `cv-measurement-auditor` (its through-glass engine would misapply to glass-free cameras). Carries
  night-IR / weather / occlusion / **no cross-camera identity** caveats.
- **Compute routing:** small batches local; large batches (full-pool embedding, full-cohort retrain,
  long-video inference) dispatch to Cornell BioHPC via the `gpu-cv` skill (`D:\FastenPC`). Drivers are
  env-driven (`FIELD2026_ANALYSIS_OUT_ROOT`) so they run identically local or on the server; routing lives in
  the skill, documented in `cv/cv_field/REMOTE_COMPUTE.md`. Nothing in Phase 0 depends on the server.

## Files

New under `cv/cv_field/`: `output_paths.py`, `cohorts.py`, `field_embed.py`, `field_cluster.py`, `acquire.py`,
`select_frames.py`, `run_field.py`, `field_audit.py`, `selftest_field_select.py`, `assets_manifest.json`,
`FIELD_AUDIT_CHECKLIST.md`, `REMOTE_COMPUTE.md`. Modified: `cv/measurement_context.py` (additive kwargs),
`cv/environment.yml` + `cv/requirements.txt` (+scikit-learn).

## Constraint

This checkout is **source + configs only** — no raw video, no weights, no `dataset/`, and both
`staging/cv_attempt/` and the external `C:\Users\Cornell\Documents\CV` project are absent. So Phase 0 (code +
offline self-tests) is the only part that lands here; the merge-plan's "adopt `cv_attempt`'s extraction
front-end" is not a Phase-0/1 dependency.

## Phasing

- **Phase 0 (now):** author `cv/cv_field/` + the shims + the `measurement_context` edit + env change; self-test.
- **Phase 1 (run machine):** harvest → `select_frames --round 0` → label → `train_detector`; register assets;
  `field_audit` metadata.
- **Phase 2:** iterative rounds (`--seed-weights`) vs the equal-budget random control; label-efficiency curve.
- **Phase 3:** `run_field.py` whole-field inference. No cross-camera identity; WISER×CV blocked on georeference.

## Verification (Phase 0)

`python cv/cv_field/selftest_field_select.py` PASS — planted-cluster coverage (incl. a rare 10-point blob +
outliers), silhouette K recovery, near-duplicate suppression, uncertainty targeting + spread, determinism,
gray-backend end-to-end, and cohort path + measurement_context wiring (embedding/active_learning blocks;
`mc_run_id` flips per round; shelter byte-identity preserved). `py_compile` clean on all modules; the three
drivers `--help` cleanly; a full `select_frames` + `field_audit` end-to-end smoke on synthetic frames passes.
