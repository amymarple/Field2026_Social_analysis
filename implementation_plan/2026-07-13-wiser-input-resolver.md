# WISER raw-input resolver — two-mode, cohort-pinnable, provenance-recording

**Date:** 2026-07-13 · **Status:** plan (implemented same day) · **Direction:** infrastructure (wiser_* inputs)
· **Scope class:** medium (new `common/` module + shim + cohort-manifest schema + 8 driver defaults)

## Motivation

The WISER raw master moved to Cornell BioHPC permanent storage
(`Q:\hc997\SocialFieldRat2026\Wiser_backup`, a **network** SMB mount). The analysis PC was reimaged, so the
local working copy the drivers expected (`D:\Reolink_record\audio_in\Wiser_backup\`) was gone, and the exact
snapshot every driver hard-coded (`1stcohort_2026_2026-07-09.sqlite`) no longer exists anywhere — storage
now retains only the latest ~2 daily cumulative snapshots (`…07-11`, `…07-12`). A stopgap re-pointed the 8
snapshot drivers to `…07-12`, but that literal **goes stale at the next snapshot rotation** (tomorrow it is
`…07-13`). This is a recurring, cohort-agnostic problem: the input path is hard-coded, not resolved.

Two hard rules frame the fix:
- **Never analyze SQLite over a network mount** (SQLite random I/O + file locking are slow/unreliable over
  SMB; BioHPC's own rule is "keep data on storage, compute from local disk"). → prefer a **local** working
  copy; Q: stays the master/backup.
- **The dataset must stay appendable per cohort** — a new cohort or more nights must be *data + one cohort
  YAML + a re-run*, never a code change.

## Design — two modes, one resolver

New `common/wiser_inputs.py` (INPUT side; `common/output_paths.py` stays the OUTPUT side) + a re-export shim
`wiser/src/wiser_inputs.py` (mirrors the `output_paths` shim so drivers keep `import wiser_inputs`). It reads
the cohort registry (`cohorts/<key>.yaml`): the per-machine `raw_data_roots` **and** a new `wiser:` block.

New per-cohort `wiser:` block (this is the appendability knob — each cohort declares its own):
```yaml
wiser:
  snapshot_glob:   "1stcohort_2026_*.sqlite"            # cumulative daily snapshots for THIS cohort
  pinned_snapshot: "1stcohort_2026_2026-07-12.sqlite"   # exact file for canonical runs; null => fall back to latest
  fixed_baseline:  "tag_reports_2026-06-30.sqlite"      # stationary jitter-floor baseline db
```

**Modes** (`resolve_wiser_db(cohort, mode=...)` → `(Path, provenance)`):
- `latest` — **exploratory / default convenience.** Newest file matching `snapshot_glob` in the resolved
  snapshots dir. Snapshots are cumulative, so newest = superset; never goes stale.
- `canonical` — **reproducible.** The cohort's `pinned_snapshot` **exactly**. If no pin is declared, **fall
  back to `latest`** and flag `pin_fallback: true` in provenance (loud, not silent).
- Explicit `--db PATH` always wins over both.

**Snapshots-dir selection (local-first, cross-machine):** pick the first `raw_data_roots.<machine>.wiser_snapshots`
that exists, in preference order `analysis_pc` (local D:) → `biohpc` (network Q:) → `field_pc`; overridable
with `FIELD2026_WISER_ROOT` (direct dir) or `FIELD2026_MACHINE`. This finally makes `raw_data_roots`
load-bearing instead of documentation-only.

**Provenance (`db_provenance`)** — always records `path`, `size_bytes`, `mtime_iso`, `mode`, `pinned`,
`pin_fallback`, `snapshots_dir`, `machine`. For **canonical** runs it also computes a chunked **sha256**
(cached in a `.sha256cache.json` beside the DB, keyed by size+mtime; write-guarded so it never writes onto
the read-only network master). `write_input_provenance(out_dir, prov)` drops
`wiser_input_provenance.json` into the off-repo run dir next to `run_manifest.json`.

**Driver convenience:** `finalize(args)` reads `args.{db,fixed,canonical,cohort}` (all optional via getattr),
resolves cohort itself (defaults to `2026a`), and returns `(db_path, fixed_path, provenance)`.

## Files

- **New** `common/wiser_inputs.py` — resolver (loads `common/cohorts.py` + `common/output_paths.py` by file
  path, sys.path-independent, like the shim).
- **New** `wiser/src/wiser_inputs.py` — re-export shim.
- **Edit** `cohorts/2026a.yaml` — add the `wiser:` block.
- **New** `wiser/scripts/selftest_wiser_inputs.py` — offline synthetic self-test (latest / pinned /
  pin-fallback / explicit / checksum / local-first selection / missing-file error / `finalize` contract).
- **Edit** the **8 snapshot drivers** (`analyze_biological_day_sleep`, `analyze_circadian_rest`,
  `analyze_daytime_rest_temperature`, `analyze_evening_morning_sleep`, `analyze_heat_gated_relocation`,
  `analyze_night_consolidated_rest`, `analyze_sleep_site_cv_crossval`, `analyze_sleep_site_hierarchy`) —
  uniform recipe: `import wiser_inputs as _wi`; drop the hard-coded `DEFAULT_DB`/`DEFAULT_FIXED` literals;
  `--db`/`--fixed` default `None` + new `--canonical` flag; after `parse_args`, `args.db, args.fixed,
  _wiser_prov = _wi.finalize(args)`; after the run dir is made, `_wi.write_input_provenance(out, _wiser_prov)`.

## Explicitly OUT of scope (semantically separate)

The **live-DB tools** — `analyze_nightly_progression`, `analyze_nightly_behavior` (Direction 1),
`georeference_wiser`, `place_wiser_rois`, `place_exclude_region`, `plot_hourly_occupancy`,
`analyze_route_structure` (baseline arg) — read the **growing field DB** (`D:\Wiser\data\1stcohort_2026.sqlite`)
or the stationary baseline, not the cumulative snapshots. They keep their own defaults and take `--db`
explicitly; they do **not** use this resolver. `analyze_daytime_sleep_site` also points at the live DB and is
left as-is.

## Appendability contract (the point)

Adding cohort `2026b`: `cp cohorts/2026a.yaml cohorts/2026b.yaml`, edit its `wiser.snapshot_glob` /
`pinned_snapshot` / `raw_data_roots`, drop the data, re-run with `--cohort 2026b`. No code change; canonical
runs pin `2026b`'s snapshot, exploratory runs take `2026b`'s latest.

## Verification

- `python wiser\scripts\selftest_wiser_inputs.py` → PASS (all branches, synthetic; no field data).
- `python wiser\scripts\<driver>.py --help` for each of the 8 → imports + argparse OK (no DB touched).
- Re-open smoke test already done: the local `…07-12` snapshot opens read-only (21,594,992 `Position` rows).

## Rollback

Delete `common/wiser_inputs.py` + `wiser/src/wiser_inputs.py`, drop the `wiser:` block, and restore the 8
drivers' `DEFAULT_DB`/`DEFAULT_FIXED` literals (git revert of this change). No results are affected (inputs
only; the cumulative `…07-12` reproduces every prior window).
