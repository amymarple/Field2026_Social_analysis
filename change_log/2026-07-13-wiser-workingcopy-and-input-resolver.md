# WISER Q:→D: working-copy migration + two-mode cohort-pinnable input resolver

**Date:** 2026-07-13 · **Direction:** infrastructure (wiser_* inputs) · **Status:** done, verified · **Scope:**
inputs only — **no analysis result changed** · **Plan:** [implementation_plan/2026-07-13-wiser-input-resolver.md](../implementation_plan/2026-07-13-wiser-input-resolver.md)

## Why

The WISER raw master moved to Cornell BioHPC permanent storage (`Q:\hc997\SocialFieldRat2026\Wiser_backup`,
a **network SMB** mount). The analysis PC was reimaged, so the local working copy the drivers expected
(`D:\Reolink_record\audio_in\Wiser_backup\`) was gone, and the exact snapshot every driver hard-coded
(`1stcohort_2026_2026-07-09.sqlite`) no longer exists anywhere — storage retains only the latest ~2 daily
cumulative snapshots. Two rules shaped the fix: **never analyze SQLite over a network mount** (slow random
I/O + unreliable SMB file locking; BioHPC's own rule is "keep data on storage, compute from local disk"), and
**the dataset must stay appendable per cohort**.

## What changed

1. **Working-copy migration (Q: master → local D: working copy).** `robocopy` of
   `Q:\hc997\SocialFieldRat2026\Wiser_backup` → `D:\Reolink_record\audio_in\Wiser_backup\` — 21 files /
   4.86 GB / 54 s, 0 failed (snapshots `…07-11`, `…07-12`, `tag_reports_2026-06-30`, and the daily
   `incremental/*.csv.gz` deltas back to 06-28). **Q: stays the permanent master/backup; D: is the working
   copy analysis reads.** The `…07-12` snapshot opens read-only locally (21,594,992 `Position` rows).

2. **Cohort registry (`cohorts/2026a.yaml`).** Added a `biohpc` block under `raw_data_roots` (Q: storage
   paths) and a per-cohort **`wiser:`** input block — `snapshot_glob`, `pinned_snapshot`
   (`…07-12`), `fixed_baseline`. A new cohort declares its own glob/pin here → no code change (appendability).

3. **Interim stopgap (superseded by #4, recorded for provenance).** The 8 snapshot drivers were first
   re-pointed off the missing `…07-09` (and `…07-01` for cv-crossval) onto the present `…07-12` so they ran
   immediately. That literal would go stale at the next snapshot rotation; #4 removes it entirely.

4. **New resolver — `common/wiser_inputs.py` (+ re-export shim `wiser/src/wiser_inputs.py`).** Resolves the
   raw WISER snapshot DB for a cohort in **two modes**:
   - **`latest`** (exploratory / default convenience): newest file matching the cohort's `snapshot_glob`.
     Snapshots are cumulative, so newest = superset — never goes stale.
   - **`canonical`** (`--canonical`, reproducible): the cohort's `pinned_snapshot` **exactly**; if no pin is
     declared it **falls back to `latest`** with `pin_fallback: true` (loud). Explicit `--db` always wins.
   Snapshots-dir selection prefers a **local** `raw_data_roots` block (analysis_pc D:) over the **network**
   master (biohpc Q:), overridable via `FIELD2026_WISER_ROOT` / `FIELD2026_MACHINE` — this makes
   `raw_data_roots` load-bearing (it was documentation-only). Every resolution returns a **provenance** record
   (path, size, mtime, mode, pin flags); **canonical additionally records a chunked `sha256` checksum**
   (cached in `.sha256cache.json` beside the DB, write-guarded so it never writes onto the read-only network
   master). `finalize(args)` gives drivers `(db, fixed, provenance)`; `write_input_provenance(out_dir, prov)`
   drops `wiser_input_provenance.json` into the off-repo run dir.

5. **Wired the 8 snapshot drivers** (`analyze_biological_day_sleep`, `analyze_circadian_rest`,
   `analyze_daytime_rest_temperature`, `analyze_evening_morning_sleep`, `analyze_heat_gated_relocation`,
   `analyze_night_consolidated_rest`, `analyze_sleep_site_cv_crossval`, `analyze_sleep_site_hierarchy`) to the
   resolver: hard-coded `DEFAULT_DB`/`DEFAULT_FIXED` literals removed; `--db`/`--fixed` default `None` + a new
   `--canonical` flag; `finalize()` after `parse_args`; `write_input_provenance()` at the run dir.

6. **New offline self-test** `wiser/scripts/selftest_wiser_inputs.py` (synthetic; latest / canonical-pin /
   pin-fallback / explicit / checksum + cache round-trip / local-first selection / missing-pin error /
   `finalize` against the shipped `2026a.yaml`).

## Explicitly left separate (semantically distinct)

The **live-DB tools** — `analyze_nightly_progression`, `analyze_nightly_behavior` (Direction 1),
`georeference_wiser`, `place_wiser_rois`, `place_exclude_region`, `plot_hourly_occupancy`,
`analyze_route_structure` (baseline), `analyze_daytime_sleep_site` — read the **growing field DB**, not the
cumulative snapshots. They keep their own defaults / explicit `--db` and do **not** use this resolver.

## Verification

- `python wiser\scripts\selftest_wiser_inputs.py` → **PASS** (all branches).
- `python wiser\scripts\<driver>.py --help` for all 8 → exit 0, `--canonical` present, imports OK.
- Real end-to-end against the shipped `2026a.yaml` + local copy: `latest` and `canonical` both resolve to
  `…07-12` from the **local D:** block (not Q:); canonical computes the sha256; `finalize` returns db + fixed.
- `python -m py_compile` on all 8 → OK.

## Reproducibility & appendability notes

- **Cumulative snapshots:** the `…07-12` snapshot is a superset of every earlier window, so the canonical
  06-28→07-08 analyses reproduce identically by date-range filtering (tag cutoffs applied in analysis).
- **The exact `…07-09` snapshot the canonical runs used is gone** (storage keeps only the latest ~2). For
  byte-exact provenance of a specific run, keep the pinned snapshot under the cohort's off-repo `assets/`; the
  `incremental/*.csv.gz` deltas (now local) also reconstruct earlier states.
- **Appendability:** cohort `2026b` = `cp cohorts/2026a.yaml cohorts/2026b.yaml`, edit its
  `wiser.{snapshot_glob,pinned_snapshot}` + `raw_data_roots`, drop the data, re-run `--cohort 2026b`. Canonical
  runs pin 2026b's snapshot; exploratory runs take 2026b's latest. No code change.

## Rollback

`git revert` this change (delete `common/wiser_inputs.py` + `wiser/src/wiser_inputs.py`, drop the `wiser:`
block, restore the driver literals). Inputs only — no result is affected.
