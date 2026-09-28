# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start here

The single canonical constitution is **[CONVENTIONS.md](CONVENTIONS.md)** — read it before any non-trivial
change. `CLAUDE.md` and `AGENTS.md` are deliberately thin pointers to it; put durable *conventions* there,
not here. This file adds only the operational layer CONVENTIONS.md does not: the concrete commands and the
cross-file architecture a future instance needs to be productive.

**Order of truth** when docs disagree: `CONVENTIONS.md` → the `common/` code → a subsystem `README`. Some
subsystem READMEs (`wiser/README.md`, `cv/README_cv.md`) predate the cohort-appendable migration and still
show pre-migration paths (`outputs/`, `LATEST_RUN.txt`, `WISER_OUT_ROOT`, old-repo `Field_2026_Social\…`);
trust `common/output_paths.py` and CONVENTIONS.md over them.

Quick reminders (all detailed in CONVENTIONS.md):
- This is the **analysis** repo. Recording lives in the separate **`Field_2026_Social_Recording`** repo
  (`C:/Users/Cornell/Documents/GitHub/Field_2026_Social_Recording`, github amymarple/Field_2026_Social_Recording) — nothing that writes/manages raw capture belongs here.
- **What is actually going on in the field (rounds, battery swaps/deaths, probe moves, session splits, Resyncs, PC
  incidents) is recorded THERE, not here:** `BATTERY_LOG_cohort3.md` (per-round log, updated several times a day),
  `change_log/`, the per-subsystem `README_*.md` (led_sync, pc_drift, neurologger_daily_resync, health_check, usb_copy, …),
  plus the Notion page "4-Rat 3rd cohort full (SF07–SF12)": https://app.notion.com/p/4-Rat-3rd-cohort-full-SF07-SF12-3c23b0530d4a8152a204cce3afa11671 .
  `git pull` it and read those before interpreting a gap, a split session, a drift verdict or a unit-yield change; keep the
  cohort registry (`cohorts/<key>.yaml`: probe_moves, field_pc_clock_steps, outages, firmware) consistent with it. The
  `field2026-sync` repo is the message channel to the field-PC agent, not the record — with one exception: the field PC's
  **incident log** (`E:\recording_health_reports\incident_log.md` on the field PC) is mirrored there as `C:/Users/Cornell/Documents/GitHub/field2026-sync/from-field/<date>_cohort3-incident-log.md`
  (newest date = current; one dated `## ` entry per event: outages, BSODs, clock steps, battery deaths, probe moves, anchor
  passes). Read it together with BATTERY_LOG before explaining anything.
- **Cohort-appendable:** code takes `--cohort`; canonical results live at `results/<cohort>/<direction>/`;
  bulk artifacts go off-repo under `FIELD2026_ANALYSIS_OUT_ROOT`; a new cohort is a `cohorts/<key>.yaml` + a
  re-run, never a restructure.
- Navigate the science from **`analyses/`** (per-question cards) and **`summaries/`** (per-direction
  narrative) — both regenerated, never hand-edited.
- Medium/large changes need an `implementation_plan/<date>-topic.md` entry **before** and a
  `change_log/<date>-topic.md` entry **after**; keep the index READMEs current.
- Run `/analysis-definitions` for any deliverable; `/regime-aware-wiser-tracking` and
  `/regime-aware-cv-measurement` before interpreting WISER/CV behavior.
- Link-integrity rule: a moved file with a broken inbound reference is a failure.

## Environments (per subsystem, not one repo-wide venv)

Each subsystem carries its own conda env / requirements; there is no top-level lockfile. Conda is not on
PATH — use the miniforge launcher.

```powershell
# CV pipeline (needs the cu128 PyTorch build for the Blackwell GPU)
& "C:\Users\Cornell\miniforge3\condabin\conda.bat" env create -f cv\environment.yml      # env: cv
# Audio feature pipeline
& "C:\Users\Cornell\miniforge3\condabin\conda.bat" env create -f audio\environment.yml   # env: audio
# WISER analysis is light: pip install pandas numpy matplotlib pyyaml
```

Set the off-repo artifact root once per machine (drivers read it via `common/output_paths.py`):

```powershell
$env:FIELD2026_ANALYSIS_OUT_ROOT = "D:\Field2026_analysis_out"   # default if unset
$env:FIELD2026_COHORT = "2026a"                                  # default cohort if a driver isn't given --cohort
```

## Common commands

**Offline self-tests** — every subsystem verifies its code with synthetic data, *no field data or GPU
needed*. Run the relevant one after touching that subsystem:

```powershell
python wiser\scripts\selftest_output_paths.py            # common/ path+cohort SSOT PASS/FAIL (via the wiser shim)
python wiser\scripts\selftest_wiser_inputs.py            # raw-input resolver: latest vs canonical-pin + provenance/checksum
python wiser\scripts\selftest_georeference.py            # WISER->field transform fit
# wiser/scripts has ~20 selftest_*.py, one per analysis module (routes, sleep, policy, rest, …) — run the matching one
python cv\view_quality.py --selftest                     # CV glass/view-quality logic (cv_shelter)
python cv\cv_field\selftest_field_select.py              # cv_field active-learning selector + path wiring
python audio\scripts\selftest_features.py                # audio feature extraction
python episode_browser\selftest.py                       # episode browser
python -m analysis_exchange.tests.test_bridge            # bridge contract (unittest; run as a module — it imports the package)
```

**Regenerate the two index layers** (mandatory after adding a cohort or any canonical result; never
hand-edit their outputs):

```powershell
python summaries\_generate_summaries.py     # -> summaries/<direction>.md
python analyses\_generate_analyses.py       # -> analyses/<direction>/<question>.md, from analyses/registry.yaml
```

**Publish a machine-readable result** through the bridge (never hand-edit `analysis_exchange/published/`):

```powershell
python analysis_exchange\scripts\bridge_cli.py new|validate|publish|verify|list ...
# or use the /export-analysis-result skill / analysis-result-bridge subagent
```

**Prune off-repo run folders** (timestamped runs accumulate; dry-run by default):

```powershell
python -c "from common.output_paths import prune; print(prune('my_analysis', keep=3))"   # add apply=True to delete
```

**Launch the researcher-facing Episode Browser** (Streamlit; run from inside its folder):

```powershell
cd episode_browser; python -m streamlit run app.py
```

There is no batch test runner, linter config, or build step — this is a Python analysis repo, run scripts
directly. A pipeline driver is invoked as `python <subsystem>\scripts\<driver>.py --cohort <key> [args]`.

## Architecture (the parts that need several files to understand)

**Path + cohort SSOT with an import shim.** `common/output_paths.py` is the *only* place that knows the
output layout; `common/cohorts.py` loads the `cohorts/<key>.yaml` registry. WISER drivers do **not** import
from `common` directly — they `sys.path.insert(0, "wiser/src")` and `import output_paths`, which resolves to
`wiser/src/output_paths.py`, a **re-export shim** that loads `common/output_paths.py`. Add logic in
`common/`, never in the shim. Key functions: `run_dir()` (off-repo bulk, timestamped), `report_dir()` /
`figure_dir()` (in-repo canonical, cohort+direction keyed), `archive_report_dir()` (superseded, mirrored
shape), `write_run_manifest()` (ties an in-repo report back to its off-repo bulk run). `report_dir`/
`figure_dir` accept a legacy single-arg (direction-only) call that defaults the cohort.

**Two homes for every run's output** (this is the cohort-appendable principle in code):
- *Off-repo bulk* — CSV dumps, figure dumps, full `run_manifest` — under
  `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/<name>_<timestamp>/`. Off git.
- *In-repo canonical* — the report + its canonical figures — under
  `results/<cohort>/<direction>/{reports,figures}/`, flat, tracked, with a `run_manifest.json` pointer.

**Research directions** key everything (results, summaries, analyses, archive): `wiser_baseline`,
`wiser_d1_nightly`, `wiser_d2_routes`, `wiser_d3_sleep`, `wiser_policy`, `cv_shelter`, `audio_soundscape`,
`crossmodal`.

**Navigation, not code, is the entry point.** A reader learns the science from `analyses/README.md` (map) →
`analyses/<direction>/<question>.md` (per-question card: verdict, coverage, canonical driver+report, figures,
blockers, superseded claims, exact rerun command) and `summaries/<direction>.md` (regenerated narrative). Both
are generated — `analyses/registry.yaml` is the source for the cards. Never browse `scripts/` to reconstruct
what was done.

**Two coordinate frames that do not trivially convert.** WISER tracking is **inches in an unverified offset
frame**; the CV pipeline is **cm in a surveyed physical frame** (origin pole A0, field 609.6 × 1219.2 cm).
`1 in = 2.54 cm` does *not* align them — the bridge is the fitted georeference transform
(`wiser/src/field_transform.py`, config `wiser/configs/wiser_to_field_transform.json`), which stays
`confirmed: false` and acts as a no-op until a pole survey passes QC. Until then, no directional/physical
WISER claims.

**Identity differs by modality.** WISER = `shortid` tag (resolve via `wiser/configs/rat_identities.csv`; a
tag is not an animal). CH01/CH02 color cams = coband color; CH03–CH06 IR cams are monochrome = coband
pattern, never color. Roster in `FIELD_OBSERVATIONS.md`.

**Clocks differ per device** (NVR local wallclock, WISER Unix-ms UTC, weather local+offset). Treat any
cross-modality alignment as *unverified* unless a shared event confirms it.

**Measurement is regime-confounded by construction.** WISER UWB carries ~4–7 in jitter plus weather/shelter
dropout; CV shelter cams image through IR-filter glass (fog/condensation/rain/glare). Carry that context
before any behavioral claim — the `/regime-aware-*` skills and the `wiser-measurement-auditor` /
`cv-measurement-auditor` subagents enforce it.

## Report-promotion discipline

Every derived quantity in any deliverable needs a formula **and** a plain-text definition
(`/analysis-definitions`). When a run changes a biological definition, state space, exclusion rule, or
conclusion, keep two artifacts: the technical ledger (`change_log/` + in-`results/` report + `STATUS.md`)
and a separate human-readable summary. Flow: analysis → ledger → `/scientific-report-promotion` (sets
status/scope/allowed wording) → `/human-readable-scientific-summary` (concise narrative; may never upgrade
status or broaden scope).
