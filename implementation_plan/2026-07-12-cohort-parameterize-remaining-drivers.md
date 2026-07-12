# 2026-07-12 — Cohort-parameterize the remaining analysis drivers

## Goal & motivation

The cohort-appendable migration wired the framework (`common/output_paths.py` cohort-aware +
`FIELD2026_ANALYSIS_OUT_ROOT` + `cohorts/<key>.yaml`) and fully parameterized two representative WISER
drivers (`analyze_circadian_rest.py`, `analyze_heat_gated_relocation.py`) plus the infra
(`prune_wiser_runs.py`, `selftest_output_paths.py`). This plan tracks parameterizing the **remaining
drivers** so that `--cohort` routes every canonical report to the correct `results/<cohort>/<direction>/`
taxonomy folder (not the driver's old ad-hoc name).

## Current problem

- The framework is **backward-compatible**: an un-edited Lineage-A driver still runs and defaults to cohort
  `2026a`, but its legacy `report_dir("<own-name>")` / `run_dir("<name>")` calls route to
  `results/2026a/<own-name>/` instead of the taxonomy direction (e.g. `wiser_d3_sleep`). That is a routing
  gap, not a crash.
- **Lineage-B** drivers (route/policy/following/locomotor/destination/approach/search/route-vocab/fireworks)
  hard-code `outputs/<name>_<daterange>/` and read each other's CSVs by path; parameterizing them is a
  driver+reader change (the old repo's own output-path consolidation deliberately deferred these).
- These edits touch scientific drivers that require the **live WISER DB** to run, so they cannot be
  runtime-verified in the migration session — they need a real run on the analysis PC.

## Recipe (per Lineage-A driver — the pattern already applied to circadian & heat_gated)

1. `import output_paths as _op` (or reuse the existing `output_paths` import).
2. Add `ap.add_argument("--cohort", default=None, help="cohort key …")`.
3. `cohort = _op.resolve_cohort(args.cohort)`.
4. Bulk: `out = _op.run_dir("<name>", cohort, root=args.output)` (replaces `out = args.output / f"<name>_{ts}"`).
5. Canonical: `report_dir = _op.report_dir(cohort, "<direction>")`; write the report as
   `report_dir / f"<direction>_<analysis>_{cohort}.md"`; drop the module-level `REPORT_DIR` constant.
6. `_op.write_run_manifest(report_dir, out, cohort=cohort, direction="<direction>", analysis="<analysis>")`.
7. Runtime-verify on the analysis PC against the live/snapshot DB.

## Per-driver direction map (remaining Lineage-A)

| Driver | `<direction>` |
|---|---|
| `analyze_daytime_sleep_site.py`, `analyze_daytime_rest_temperature.py`, `analyze_biological_day_sleep.py`, `analyze_evening_morning_sleep.py`, `analyze_night_consolidated_rest.py`, `analyze_sleep_site_hierarchy.py` | `wiser_d3_sleep` |
| `analyze_nightly_progression.py`, `analyze_nightly_behavior.py` | `wiser_d1_nightly` |
| `analyze_route_structure.py` | `wiser_d2_routes` |
| `analyze_sleep_site_cv_crossval.py` | `crossmodal` |
| `plot_hourly_occupancy.py`, `analyze_fixed_position_test.py` | `wiser_baseline` |

## Lineage-B (separate, larger change)

`analyze_trajectory_stereotypy`, `analyze_following_structure`, `analyze_route_motifs`,
`analyze_following_incidents`, `analyze_route_vocabulary`, `compare_route_segmentations`,
`build_*`/`analyze_*` policy modules (`policy_identifiability`, `locomotor`, `destination`, `approach_avoid`,
`search_excursions`, `temporal_policy`, ladder grid, social), and the fireworks/audio drivers. These pass
CSVs stage→stage by hard-coded `outputs/<name>_<daterange>/` paths; rehome the whole chain (driver + reader)
onto `common/output_paths.run_dir(name, cohort)` + a cohort-scoped intermediate store in one change so the
inter-stage links don't break. Directions: `wiser_d2_routes` (route/following/trajectory/motif/vocab),
`wiser_policy` (all policy modules), `crossmodal` (fireworks/audio).

## Non-goals

- Not changing any scientific computation, threshold, or output content — only *where* outputs land.
- Not reprocessing 2026a results (already migrated under `results/2026a/`).

## Verification

Per driver: `python -m py_compile`, then a real `--cohort 2026a` run on the analysis PC confirming the
canonical report lands in `results/2026a/<direction>/reports/` and bulk under
`$FIELD2026_ANALYSIS_OUT_ROOT/2026a/<name>_<ts>/`, and `analyses/_generate_analyses.py` +
`summaries/_generate_summaries.py` pick it up.
