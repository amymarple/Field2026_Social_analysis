# 2026-07-12 — Migration to the cohort-appendable analysis repo

## What changed

Migrated the **analysis** work out of the `Field_2026_Social` monolith into this repo
(`Field2026_Social_analysis`) under a **cohort-appendable** schema, so adding a cohort or more days requires
zero restructuring. The old repo is left intact as a read-only archive (a `DEPRECATED.md` banner points here).

### Layout (relocations)

- `wiser_tracking_analysis/` → **`wiser/`**; `preprocessing/computer_vision/` (+ `data_merging/merge_cameras.py`)
  → **`cv/`**; `audio_analysis/` → **`audio/`**; `episode_browser/`, `analysis_exchange/`, `docs/`,
  `change_log/`, `implementation_plan/`, `data_manifests/` carried over.
- New cohort layer: `cohorts/<key>.yaml` (registry) · `results/<cohort>/<direction>/{reports,figures}/` (flat,
  canonical) · `archive/<cohort>/<direction>/` (superseded, mirrored) · `analyses/` (per-question navigation
  cards) · `summaries/` (per-direction narrative) · `aggregate/` (cross-cohort, empty).
- New shared code: `common/output_paths.py` (cohort-aware) + `common/cohorts.py`. `wiser/src/output_paths.py`
  is now a shim re-exporting `common/`.
- Constitution merged: `CONVENTIONS.md` (from old `CLAUDE.md` + `AGENTS.md`); `CLAUDE.md`/`AGENTS.md` are thin
  pointers. Seeded fresh: `README.md`, `STATUS.md`, `ANALYSIS_BRIDGE.md`, `PARKED_ITEMS.md`.

### Cohort framework

- New env var **`FIELD2026_ANALYSIS_OUT_ROOT`** (default `D:\Field2026_analysis_out`) replaces the old
  `WISER_OUT_ROOT` (intentionally not reused). Bulk run artifacts → `<OUT_ROOT>/<cohort>/<name>_<ts>/`;
  canonical report + figures → `results/<cohort>/<direction>/`; large/non-regeneratable assets (CV labeled
  dataset, detector weights) → `<OUT_ROOT>/<cohort>/assets/` with an in-repo `assets_manifest.json` pointer.
- `common/output_paths.py` is cohort-aware **and backward-compatible** (legacy single-arg `report_dir`/
  `figure_dir` default to cohort `2026a`), so un-parameterized drivers still run.
- Current results migrated under cohort key **`2026a`** (50 canonical reports + 9 archived); the 2026 field
  season is `2026a`, not "the" results.

### Drivers

- Fully parameterized with `--cohort` + verified: `analyze_circadian_rest.py`, `analyze_heat_gated_relocation.py`;
  infra `prune_wiser_runs.py`, `selftest_output_paths.py` made cohort-aware.
- Remaining Lineage-A + all Lineage-B drivers: tracked in
  [`implementation_plan/2026-07-12-cohort-parameterize-remaining-drivers.md`](../implementation_plan/2026-07-12-cohort-parameterize-remaining-drivers.md)
  (they keep running via backward-compat meanwhile; runtime verification needs the live WISER DB).

### Classification decisions

- **Excluded (recording):** `reolink_record/`, `reolink_export/`, `backup_wiser_daily.py` + its docs/installer,
  the daily-recording-continuity and wiser-daily-backup change logs/plans, vendored `yolo*.pt` backbones.
- **Parked (genuinely recording-vs-analysis ambiguous):** see [`PARKED_ITEMS.md`](../PARKED_ITEMS.md)
  (`analyze_formal_recording.py`, the LFP/security stubs, `observation.md`, `.codex/`,
  `install_wiser_occupancy_task.ps1`, scratch files). Not migrated, awaiting a ruling.
- **Reclassified AMBIGUOUS → MIGRATE (evidence-driven):** `data_manifests/glass_treatments.yaml` (imported by
  CV modules), `audit_following_video.py` + `video_audit_manual.csv` (imports 5 WISER analysis modules),
  `2026-06-28-hourly-occupancy-maps` change_log/plan (document a migrated driver). Documented in `PARKED_ITEMS.md`.

### Navigation layers (regenerated, never hand-edited)

- `analyses/registry.yaml` (33 scientific questions) → `analyses/_generate_analyses.py` builds per-question
  cards (verdict, cohort coverage, canonical driver, report, figures, blockers, superseded, exact rerun) +
  `analyses/README.md`. `summaries/_generate_summaries.py` builds per-direction narrative with audit discipline
  (claim + evidence + source + ACTIVE/SUPERSEDED/CONTESTED). A reader navigates the science without opening `scripts/`.

## Why

The old repo mixed recording with analysis and hard-baked one field season into paths. This repo separates
concerns and makes cohort addition a data + one-YAML + re-run operation.

## Verification

- Offline self-tests PASS in the new tree: `wiser` `selftest_output_paths` / `selftest_georeference` /
  `selftest_daytime_sleep_site`; `episode_browser/selftest.py`; `audio/scripts/selftest_features.py`;
  `cv/animal_tracking.py --synthetic`; `analysis_exchange` `python -m unittest discover tests` (21 OK, after
  restoring the byte-frozen sealed example bundle the global rewrite must not touch).
- Link-integrity: zero `wiser_tracking_analysis` / `preprocessing/computer_vision` / `WISER_OUT_ROOT` /
  `Wiser_plot` / `audio_analysis/` tokens remain in the active tree (only `PARKED_ITEMS.md`, which intentionally
  names old-repo locations, and `staging/cv_attempt/`, kept untouched). `analyses/` + `summaries/` links resolve (0 broken).
- Appendability acceptance test (synthetic `2026_TEST` cohort) in the Phase-5 change log.

## Known limitations / next steps

- Only 2 WISER drivers are `--cohort`-verified end-to-end; the rest run via backward-compat and are tracked for
  full parameterization + live-DB runtime verification.
- `wiser/ANALYSIS_STATUS.md` inline `outputs/…` report links reflect the old in-repo layout (banner added; use
  `analyses/` / `results/` for current navigation).
- CV reconciliation with `C:\Users\Cornell\Documents\CV` is plan-only (see the CV merge plan under
  `results/2026a/cv_shelter/reports/`); the merge is a separate approved task.
