# CONVENTIONS.md — the one canonical constitution

This is the single source of workflow truth for **Field2026_Social_analysis**. `CLAUDE.md` and `AGENTS.md`
are thin pointers to this file; edit conventions here, not there. It merges the old repo's `CLAUDE.md`
(project map) and `AGENTS.md` (workflow contract), rewritten for this repo's cohort-appendable layout.

## What this repo is

Offline **analysis** for the Field_2026_Social study — continuous multimodal recordings from outdoor rat
experiments (field season Jun–Oct 2026) in a **20 × 40 ft paddock**: WISER/UWB tracking, Reolink video +
CV shelter occupancy, camera-mic audio soundscape, weather, and cross-modal work, plus the researcher-facing
Episode Browser and the `analysis_exchange` producer→consumer bridge.

**Recording is NOT here.** RTSP/thermal capture, recorder QC, USB/backup, and the live WISER DB writer live
in the separate **`social_recording`** repo. Nothing that writes or manages raw capture belongs in this
repo. This is a scientific data-analysis project: protect raw data and provenance over convenience.

The old monolith `Field_2026_Social` is a **deprecated read-only archive** (see its `DEPRECATED.md`); all
active analysis work happens here.

## The cohort-appendable principle (the reason this repo is shaped the way it is)

**Adding a new cohort — or more days to an existing one — must require ZERO restructuring.** Concretely:

- **Code is cohort-agnostic and parameterized; results are cohort-keyed.** Pipelines take `--cohort <key>`
  (and a date range); they never hard-code a season.
- **Results live at `results/<cohort>/<direction>/{reports,figures}/`** — flat, one folder of reports per
  direction (not one subfolder per run), named `<direction>_<analysis>_<cohort>.md` with figures on the
  same stem. `2026a` is the first cohort key, not "the" results.
- **Bulk run artifacts stay OFF-repo and OFF-git** under the artifact root (`FIELD2026_ANALYSIS_OUT_ROOT`,
  default `D:\Field2026_analysis_out`), in `<OUT_ROOT>/<cohort>/<name>_<ts>/`. The repo keeps only the
  canonical report + its canonical figures + a `run_manifest.json` pointer. Large / non-regeneratable assets
  (labeled datasets, model weights) live under `<OUT_ROOT>/<cohort>/assets/` with an in-repo
  `assets_manifest.json` pointer. **Never reuse the old `WISER_OUT_ROOT` name.**
- **`common/output_paths.py` is the single source of truth** for every output path (`run_dir`, `report_dir`,
  `figure_dir`, `archive_report_dir`, `write_run_manifest`, cohort-aware `list_runs`/`prune`). Do not
  hard-code paths in drivers. `common/cohorts.py` loads the cohort registry.
- **`cohorts/<key>.yaml` is the registry** — one YAML per cohort (date range, per-machine raw-data roots,
  identity file, caveats). Adding a cohort edits *this file only*, no code.
- **Superseded work** mirrors the results shape under `archive/<cohort>/<direction>/` — never deleted.
- **Cross-cohort aggregation** gets its own layer, `aggregate/` (empty until >1 cohort exists).

### Directions

Results/summaries/analyses are keyed by **research direction**:
`wiser_baseline` (precision, occupancy, QC) · `wiser_d1_nightly` · `wiser_d2_routes` · `wiser_d3_sleep` ·
`wiser_policy` (14-module behavioral policy) · `cv_shelter` · `audio_soundscape` · `crossmodal`.

### Two index layers (regenerated, never hand-edited into drift)

- **`summaries/<direction>.md`** — regenerated cross-cohort **narrative** per direction
  (`summaries/_generate_summaries.py`). A new cohort appends a row/panel; it does not rewrite prose. Audit
  discipline: every claim = one sentence + evidence number + source path + status (ACTIVE / SUPERSEDED /
  CONTESTED). No unsourced claims.
- **`analyses/<direction>/<question>.md`** — the human **navigation card** per scientific question
  (`analyses/_generate_analyses.py` from `analyses/registry.yaml`). Index only, **no code copied in**. Each
  card states all eight: verdict, cohort coverage, canonical driver, canonical report, figures, blockers,
  superseded claims, exact rerun command. `analyses/README.md` is the top-level map. **A reader must never
  need to browse `scripts/` or a modality folder to learn the scientific structure.**

### How a new cohort gets added

1. Drop the data on disk (per-machine roots). 2. `cp cohorts/2026a.yaml cohorts/<key>.yaml` and edit — no
code. 3. Re-run pipelines with `--cohort <key>`. 4. `python summaries/_generate_summaries.py` **and**
`python analyses/_generate_analyses.py`. 5. (optional) run `aggregate/`. 6. Commit the YAML + `results/<key>/`
+ regenerated `summaries/` + `analyses/`. No restructuring.

## Two machines (know which one you're on)

- **Field PC** (RTX 5060 Ti) — runs 24/7 capture in the *other* repo; do not disturb it. Not the place for
  heavy analysis.
- **Analysis PC** (RTX 3060) — offline analysis on **transferred, read-only** copies under
  `D:\Reolink_record\audio_in\`. `conda` via anaconda3. "Recorder down" alarms are not real here.

Raw inputs are **not in the repo** (too large); their per-machine paths live in `cohorts/<key>.yaml`. Never
modify raw data in place. **Clocks differ per device** (NVR local wallclock, WISER Unix-ms UTC, AWN local
+offset) — treat any cross-modality alignment as **unverified** unless a shared event confirms it; say
"unverified alignment," not "synchronized."

## Change workflow (from the old AGENTS.md)

- **Small** (typos, formatting, label fixes): no plan; update docs if meaning changes.
- **Medium / Large** (parser/timestamp/exclusion/coordinate/QC/metric changes, new modalities/schemas/models/
  pipelines): create `implementation_plan/<YYYY-MM-DD>-topic.md` **before** coding; create
  `change_log/<YYYY-MM-DD>-topic.md` **after** verification. Keep the `README.md` indexes current
  (`change_log/`, `implementation_plan/`, `data_manifests/`). Keep links relative and valid after moves.
- **Field-data flow:** raw registration → schema validation → timestamp normalization → sync/alignment →
  QC report → derived data → analysis → figure/report → change log. Do not jump raw→figures.
- **Raw/derived data:** never modify raw in place; derived data records source paths, generating script, git
  commit, timestamp method, exclusions, calibration, coordinate system/units, and identity mapping (sidecar
  or run manifest). Don't commit bulky raw/derived artifacts (they live off-repo, above).

## Definitions & report-promotion discipline (load-bearing)

- **Any analysis deliverable** (report, `change_log/` entry, metrics table, summary) must define **every**
  derived quantity — metric, index, threshold, statistic, null/baseline model, transform, QC rule — **both
  as a formula and in plain text** (symbols, units, range, interpretation). Run `/analysis-definitions`.
- **When a run changes a biological definition, outcome/state space, exclusion rule, or conclusion,** keep
  two artifacts: the **technical ledger** (`change_log/` + the in-`results/` report + `STATUS.md`, written
  freely, keeps superseded work) and a separate standalone **human-readable scientific summary**
  (`results/<cohort>/<direction>/reports/…SCIENTIFIC_SUMMARY.md`, current-state only, ~700–1,200 words, ≤3
  findings). Flow: analysis → technical ledger → **`/scientific-report-promotion`** (audits atomic claims →
  status + scope + allowed wording) → **`/human-readable-scientific-summary`** (audit → concise narrative).
  The promotion skill sets status/scope/wording; the summary skill controls selection/brevity/omission and
  may **never** upgrade status or broaden scope.

## Analysis-result bridge

`analysis_exchange/` is the machine-readable producer→consumer contract (Codex, Episode Browser). Draft
bundles only under `analysis_exchange/staging/`; publish with
`python analysis_exchange/scripts/bridge_cli.py publish …`; never hand-edit `published/`. Classify each
object (`episode_candidate` / `aggregate_metric` / `observation_candidate` / `model_evaluation` /
`artifact_only`); preserve provenance, claim boundaries (`allowed_claim` / `forbidden_promotions`), and
missing values (missing scores never become zero). Aggregates are not episodes; Markdown is not a payload.
Use `/export-analysis-result <path>` or the `analysis-result-bridge` subagent. See `ANALYSIS_BRIDGE.md`.

## Regime-aware measurement (never skip)

Before interpreting **any** WISER-derived behavior, follow `/regime-aware-wiser-tracking` (UWB jitter ~7 in,
weather/shelter-4-burrow dropout, unverified inch frame). Before interpreting **any** CV shelter behavior,
follow `/regime-aware-cv-measurement` (glass fog/condensation/rain/film view-quality artifacts). To audit an
output as a measurement, dispatch the `wiser-measurement-auditor` / `cv-measurement-auditor` subagents
(read-only; they persist a report under the cohort's `results/.../reports/` or an `audit/` area).

## Modality-specific documentation (condensed from AGENTS.md)

Document, per modality: **WISER** — antenna layout, paddock dims, coordinate origin/orientation/units, tag→
animal map, sampling rate, calibration, exclusions, position-error metric, unverified-frame status.
**Video/NVR** — camera/channel, fps/resolution, codec, timestamp source, dropped segments, FOV/calibration.
**Thermal** — model, thermal-vs-visible channel, absolute-temp reliability. **Audio** — relative camera-mic
dBFS (not calibrated SPL), 16 kHz mono (~8 kHz ceiling), band-limited indices comparable only within-dataset.
**Weather** — source, interval, tz/clock, variables/units, missing periods, placement. **Annotations** —
annotator, schema, timestamp basis, identity confidence, ground-truth-vs-weak-label status.

## Coordinate systems (easy to get wrong)

WISER tracking = **inches** (unverified offset frame). CV pipeline = **centimetres** (physical frame, origin
pole A0; field 609.6 × 1219.2 cm). `1 in = 2.54 cm`, but a raw unit conversion does **not** align the two —
the proper bridge is the fitted georeference transform, which only exists once a pole survey passes QC. Until
then WISER positions cannot be placed in the physical frame; no directional/physical claims.

## Rat identity differs by modality

WISER identifies by **tag** (`shortid` → resolve via `wiser/configs/rat_identities.csv`, a tag is not an
animal). Color cameras CH01/CH02 identify by **coband color**; IR cameras CH03–CH06 are monochrome →
identify by **coband pattern**, never color. Roster/caveats in `FIELD_OBSERVATIONS.md`.

## Link-integrity rule

A moved or renamed file with a broken inbound reference is a **failure, not a partial success**. After any
move/rename, rewrite every inbound link (reports, skills' `references/`, script imports, index files) and
grep-verify no stale path remains. No reference to old-repo paths (`Field_2026_Social`,
`wiser/`, `cv/`, `FIELD2026_ANALYSIS_OUT_ROOT`) may exist inside this repo
(except `staging/cv_attempt/`, kept untouched, and `DEPRECATED.md` back-pointers in the old repo).

## Language

Code, APIs, schemas, comments, and durable docs in **English**. User-facing summaries may be Chinese on
request. `shortid` is never assumed to be an animal name.

## Parked / ambiguous items

Items whose recording-vs-analysis status is genuinely unresolved are **not migrated**; they are listed in
`PARKED_ITEMS.md` for a human ruling. Do not silently pull a parked item into the active tree.
