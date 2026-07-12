# 2026-07-12 — Appendability acceptance test (Phase 5)

## What was tested

Whether adding a cohort requires **zero restructuring** — only new data + one cohort YAML + a `--cohort` re-run.

## What was done

1. Created a synthetic cohort registry `cohorts/2026_TEST.yaml` (copy of `2026a`, edited) — **no code changes**.
2. Generated minimal synthetic WISER SQLite (3 ground-truth tags, ~2.5 days, day-rest/night-active) — a
   *data* fixture, off-repo.
3. Ran the **real parameterized driver** end-to-end:
   `analyze_circadian_rest.py --cohort 2026_TEST --db synth_session.sqlite --fixed synth_baseline.sqlite`
   (bulk artifact root pointed at a temp dir via `FIELD2026_ANALYSIS_OUT_ROOT`).
4. Regenerated the index layers: `analyses/_generate_analyses.py` + `summaries/_generate_summaries.py`.
5. Removed the test cohort (`cohorts/2026_TEST.yaml`, `results/2026_TEST/`, off-repo bulk) and regenerated.

## Result — PASS

- The driver routed **bulk** to `<OUT_ROOT>/2026_TEST/circadian_rest_<ts>/` and the **canonical report** to
  `results/2026_TEST/wiser_d3_sleep/reports/wiser_d3_sleep_circadian_rest_2026_TEST.md` + `run_manifest.json`
  — cohort-keyed, no code edits.
- Regeneration **appended** `2026_TEST` to `analyses/README.md` ("Cohorts present: 2026_TEST, 2026a") and to
  the `summaries/wiser_d3_sleep.md` coverage table (circadian question ✓ for 2026_TEST) — using the **existing
  registry**, no registry/prose edits.
- After removing the test cohort and regenerating, the working tree returned to a **byte-identical committed
  state** (`git status` clean; cohorts back to `['2026a']`) — adding/removing a cohort is fully reversible and
  touches nothing but per-cohort data + regenerated indexes.

**No step required editing code or restructuring the tree.** The only fix during the test was to the synthetic
SQLite schema (column `timestamp` not `ts_raw`; table `tag_reports`) — a data-fixture detail, not the schema.

## Delete gate (Phase: gated deletion)

- **In-repo hard deletes: none.** The migration was COPY-only; the one byte-identical DUPLICATE
  (`episode_browser/data/real_wiser_evidence_..._v1.parquet`) is git-ignored + regeneratable and was not migrated.
- `prune_wiser_runs.py --keep 3` (dry-run) on the new artifact root flags nothing (fresh root). The old
  `D:\Wiser_plot` holds stale *flat* runs from the old-repo convention; they are optional off-repo cleanup, not
  part of this repo, and are **not** deleted here. `--apply` was **not** run — awaiting explicit approval.

## Verification

`git status` clean after test teardown; `analyses/`/`summaries/` unchanged vs the committed 2026a state.
