# Field2026_Social_analysis

Offline **analysis** for the Field_2026_Social study — continuous multimodal recordings from outdoor rat
experiments in a 20 × 40 ft paddock (WISER/UWB tracking, Reolink video + CV shelter occupancy, camera-mic
audio, weather, cross-modal). Recording lives in the separate `social_recording` repo; this repo never
writes or manages raw capture.

Conventions are in **[CONVENTIONS.md](CONVENTIONS.md)** (the canonical constitution). Scientific status is in
**[STATUS.md](STATUS.md)**; the machine-readable handoff contract is **[ANALYSIS_BRIDGE.md](ANALYSIS_BRIDGE.md)**.

## Find the science first

You should never need to read `scripts/` to learn what was done. Start at:
- **`analyses/README.md`** — a map of every scientific question, its verdict and cohort coverage, linking to
  a per-question card (canonical driver, report, figures, blockers, superseded claims, exact rerun command).
- **`summaries/<direction>.md`** — regenerated cross-cohort narrative per research direction.

## Layout

```
cohorts/<key>.yaml          registry: one YAML per cohort (date range, raw-data roots, identities, caveats)
common/                     output_paths.py (cohort-aware) + cohorts.py loader — shared, cohort-agnostic
wiser/ cv/ audio/           pipeline code + libraries (cohort-agnostic; take --cohort)
crossmodal/                 cross-modal drivers index (code lives in the wiser import graph — see its README)
analysis_exchange/          producer -> consumer bridge contract
episode_browser/            researcher-facing episode UI (consumer)
results/<cohort>/<dir>/      reports/ + figures/  (flat, canonical, tracked)
archive/<cohort>/<dir>/      superseded, mirrored shape (never deleted)
analyses/                    human navigation cards per scientific question (index only)
summaries/                   regenerated per-direction narrative
aggregate/                   cross-cohort layer (empty until >1 cohort)
docs/ change_log/ implementation_plan/ data_manifests/
```

Bulk run artifacts (CSVs, figure dumps) and large assets (labeled datasets, model weights) live **off-repo**
under `FIELD2026_ANALYSIS_OUT_ROOT` (default `D:\Field2026_analysis_out`), keyed by cohort; the repo keeps
only the canonical report + figures + a `run_manifest.json` / `assets_manifest.json` pointer.

## Adding a cohort (zero restructuring)

1. Drop the new cohort's raw data on disk (per-machine roots).
2. `cp cohorts/2026a.yaml cohorts/<key>.yaml` and edit the date range / roots / identities / notes. **No code edits.**
3. Re-run pipelines with `--cohort <key>` (bulk → `$FIELD2026_ANALYSIS_OUT_ROOT/<key>/…`; canonical report +
   figures → `results/<key>/<direction>/`).
4. Regenerate the index layers: `python summaries/_generate_summaries.py` **and**
   `python analyses/_generate_analyses.py`.
5. (optional) run `aggregate/` cross-cohort scripts once >1 cohort exists.
6. Commit the new `cohorts/<key>.yaml` + `results/<key>/…` + regenerated `summaries/` + `analyses/`.

## Environment

Set the artifact root once per machine, e.g. (PowerShell): `$env:FIELD2026_ANALYSIS_OUT_ROOT = "D:\Field2026_analysis_out"`.
Each subsystem keeps its own `environment.yml` / `requirements.txt`. Offline self-tests per subsystem verify
the code without field data (see CONVENTIONS.md and each subsystem README).
