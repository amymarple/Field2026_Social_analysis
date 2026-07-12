# Implementation plan — WISER analysis output-path consolidation

**Date:** 2026-07-12
**Subsystem:** `wiser/`
**Status:** in progress

## Problem

Analysis drivers save results to two different roots under two different naming schemes,
with no shared rule. Reading the source is the only way to know where a given script writes.

- **Lineage A — "data to D:, report to repo" (timestamped runs).** ~11 drivers hard-code
  `DEFAULT_OUT_ROOT = Path(r"D:\Field2026_analysis_out")`, write a fresh `<name>_<YYYYMMDD_HHMM>/` per run
  (full CSVs + figures + `run_manifest.json`), and copy only `*_report.md` back into
  `outputs/<direction>/`. `D:\Field2026_analysis_out` has accumulated 22 run folders (~31 MB) with no
  cleanup and no marker for which run is canonical.
- **Lineage B — "everything in the repo" (overwrite in place).** The route/policy/following/
  locomotor family defaults to `ROOT/outputs/<name>_<daterange>/` and writes the full artifact
  set there, named by *data date-range* (re-runs overwrite). These scripts also pass CSVs
  between stages via hard-coded `ROOT/outputs/...` reader defaults (grid, `route_bouts.csv`,
  `stationary_episodes.csv`, ...), so they form coupled in-repo pipelines.

Both roots are git-ignored (`outputs/` and `D:\Field2026_analysis_out` never enter version control), so this
is a findability / duplication problem, not a git-hygiene risk.

## Decision (user, 2026-07-12)

Standardize on **Lineage A** everywhere: bulk artifacts live off C:/off-git on `D:\Field2026_analysis_out`
in timestamped run folders; the repo keeps only the report + a pointer to the run folder.

## Design

New single source of truth: **`src/output_paths.py`**.

- `OUT_ROOT` — resolved once from env `FIELD2026_ANALYSIS_OUT_ROOT`, default `D:\Field2026_analysis_out`. No script
  hard-codes the path anymore.
- `run_dir(name)` — create `OUT_ROOT/<name>_<YYYYMMDD_HHMM>/` (+ `figures/`), return it. Used by
  new/edited scripts instead of re-implementing the ts + mkdir boilerplate.
- `report_dir(direction)` — `PROJECT_ROOT/outputs/<direction>/`, mkdir; the in-repo report home.
- `write_latest_pointer(report_dir, run_dir)` — write `outputs/<direction>/LATEST_RUN.txt`
  naming the D: run folder, so a report is always self-locating.
- `list_runs()` / `latest_run(name)` — enumerate `OUT_ROOT` run folders (regex
  `^<name>_\d{8}_\d{4}$`), grouped by name; resolve the newest. No Windows symlink needed.
- `prune(name, keep)` — delete all but the newest `keep` runs of one analysis.

Companion tooling:
- `scripts/prune_wiser_runs.py` — CLI over `prune`; **dry-run by default**, `--apply` to delete,
  `--keep N` (default 3), optional `--name <prefix>`.
- `scripts/selftest_output_paths.py` — offline PASS/FAIL against a temp `FIELD2026_ANALYSIS_OUT_ROOT`
  (exercises `run_dir` → `list_runs` → `latest_run` → `prune`); no DB, no D: dependency.

## Steps

1. `src/output_paths.py` helper (above). [safe, additive]
2. `scripts/selftest_output_paths.py` + run it → PASS. [verification]
3. `scripts/prune_wiser_runs.py`. [additive maintenance tool]
4. Migrate the 11 Lineage A drivers: replace the hard-coded
   `DEFAULT_OUT_ROOT = Path(r"D:\Field2026_analysis_out")` (and `plot_hourly_occupancy.py`'s
   `DEFAULT_OUT_DIR`) with `from output_paths import OUT_ROOT` (via `from src.output_paths import`
   for the two scripts that only put `PROJECT_ROOT` on the path). **Behavior-preserving**: the
   default root stays `D:\Field2026_analysis_out`; only its definition moves + becomes `FIELD2026_ANALYSIS_OUT_ROOT`-overridable.
   Their existing run-dir / manifest / report-copy logic is left untouched.
5. Document the rule in `wiser/README.md`.
6. `change_log/2026-07-12-output-path-consolidation.md`.

## Deliberately staged (NOT in this change) — Lineage B relocation

Moving Lineage B's data from `ROOT/outputs/` to `D:\Field2026_analysis_out` is **not** done here: those
scripts read each other's outputs via hard-coded in-repo paths, so relocating to per-run
timestamped D: folders breaks the reader defaults across the chain. Doing it safely requires a
**per-pipeline shared run directory** (build → analyze → plot share one folder) plus updating every
reader — a separate change. Until then Lineage B keeps its in-repo pipeline store (git-ignored),
and this is recorded as a known exception. New standalone drivers should use `output_paths.run_dir`.

## Verification

- `python scripts/selftest_output_paths.py` → PASS (offline).
- Lineage A migration is behavior-preserving; spot-check that an edited driver still imports
  (`python -c "import ast; ast.parse(open(p).read())"` per file) since the real drivers need the
  WISER DB to run end-to-end.
