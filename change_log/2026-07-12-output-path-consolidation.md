# Change log — WISER analysis output-path consolidation

**Date:** 2026-07-12
**Subsystem:** `wiser/`
**Plan:** `implementation_plan/2026-07-12-output-path-consolidation.md`
**Type:** refactor / housekeeping (no scientific claim changed)

## Why

Analysis drivers saved to two roots under two schemes with no shared rule, so the only way to
know where a script wrote was to read it:
- **Lineage A** hard-coded `DEFAULT_OUT_ROOT = Path(r"D:\Field2026_analysis_out")` in ~11 files and wrote a
  timestamped `<name>_<ts>/` per run (`D:\Field2026_analysis_out` had grown to 22 folders / ~31 MB with no
  cleanup and no canonical marker), copying only `*_report.md` into `outputs/<direction>/`.
- **Lineage B** (route/policy/following/locomotor) wrote the full artifact set into
  `outputs/<name>_<daterange>/` and passed CSVs between stages via in-repo paths.

Both roots are git-ignored, so this was a findability/duplication problem, not a git risk.
User decision (2026-07-12): standardize on **Lineage A** — bulk data to `D:\Field2026_analysis_out`, report +
pointer in the repo.

## What changed

Added a single source of truth and centralized the root; no run logic or output content changed.

- **New `src/output_paths.py`** — `out_root()` / `OUT_ROOT` (env `FIELD2026_ANALYSIS_OUT_ROOT`, default
  `D:\Field2026_analysis_out`), `run_dir(name)` (creates `<name>_<ts>/figures`, collision-safe),
  `report_dir(direction)`, `write_latest_pointer(report_dir, run_dir)` → `LATEST_RUN.txt`,
  `list_runs()` / `latest_run(name)` (regex-grouped, newest-first), `prune(name, keep, apply)`.
- **New `scripts/prune_wiser_runs.py`** — CLI to trim old runs per analysis; **dry-run by default**,
  `--apply` deletes, `--keep N` (default 3), `--name <prefix>`. Never touches repo report copies.
- **New `scripts/selftest_output_paths.py`** — offline PASS/FAIL in a temp `FIELD2026_ANALYSIS_OUT_ROOT`
  (no DB / no D: needed).
- **Migrated 11 Lineage A drivers** to source the root from the helper (replaced the hard-coded
  `DEFAULT_OUT_ROOT`/`DEFAULT_OUT_DIR = Path(r"D:\Field2026_analysis_out")` with
  `from output_paths import OUT_ROOT as ...`): `analyze_biological_day_sleep`, `analyze_circadian_rest`,
  `analyze_daytime_rest_temperature`, `analyze_daytime_sleep_site`, `analyze_evening_morning_sleep`,
  `analyze_nightly_behavior`, `analyze_nightly_progression`, `analyze_route_structure`,
  `analyze_sleep_site_cv_crossval`, `analyze_sleep_site_hierarchy`, `plot_hourly_occupancy`.
  **Behavior-preserving:** the default root stays `D:\Field2026_analysis_out`; only its definition moved and
  became `FIELD2026_ANALYSIS_OUT_ROOT`-overridable.
- **Documented the rule** in `wiser/README.md` ("Where analysis outputs go").

## Deliberately NOT changed (staged follow-up)

Lineage B data stays in `outputs/<name>_<daterange>/` for now: its stages read each other's CSVs
via hard-coded in-repo paths, so relocating to per-run timestamped D: folders would break the
chain. A safe move needs a shared per-pipeline run directory + reader updates — a separate change,
recorded in the plan. New standalone drivers should use `output_paths.run_dir`.

## Verification

- `python scripts/selftest_output_paths.py` → **PASS** (run_dir / list_runs / latest_run / prune / pointer).
- `python scripts/prune_wiser_runs.py --keep 3` (dry-run) correctly grouped all 22 `D:\Field2026_analysis_out`
  folders and flagged 6 stale `biological_day_sleep` runs; nothing deleted.
- All 11 migrated drivers AST-parse; the 3 import styles (standard, dual-path, `src.`-package)
  each resolve `DEFAULT_OUT_ROOT`/`DEFAULT_OUT_DIR = D:\Field2026_analysis_out`, and `FIELD2026_ANALYSIS_OUT_ROOT=E:\...`
  redirects it. Full end-to-end runs still require the WISER DB and were not exercised here.
