# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start here

The canonical constitution is **[CONVENTIONS.md](CONVENTIONS.md)** — read it before any non-trivial change, and put
durable *conventions* there. This file is the operational layer: commands, cross-file architecture, and a **code
map** of every subsystem and of the two sibling repos, so you can orient **without reading the code** — open only
the driver you are about to change. **Keep this map current:** a new/renamed driver, a moved output, or a changed
env is not done until this file says so (same rule as the index READMEs).

**Order of truth** when docs disagree: `CONVENTIONS.md` → the code (`common/`, then the subsystem) → a subsystem
README. Known-stale docs: `wiser/README.md`, `wiser/README_occupancy.md`, the body of `wiser/ANALYSIS_STATUS.md`,
`cv/README_cv.md` (old-repo paths, `outputs/`, `LATEST_RUN.txt`, `rat_daynight`, "PnP" calibration), parts of
`ephys/README.md` (incomplete file table; `WILD_generate_pc_time` is superseded by `pc_time_chain.py
--write-pc-time`), `cv/cv_field/assets_manifest.json` `current_state`. Current: `cv/cv_field/HANDOFF.md`,
`thermal/README.md`, `wiser/audit/README.md`, the shim/resolver docstrings.

Quick rules (all detailed in CONVENTIONS.md):
- **Analysis only.** Recording lives in the sibling repo **`Field_2026_Social_Recording`**
  (github amymarple/Field_2026_Social_Recording); the field↔lab channel and storage map is **`field2026-sync`** — see
  [Sibling repos](#sibling-repos-the-field-record). Nothing that writes/manages raw capture belongs here.
- **What happened in the field is recorded THERE, not here** (rounds, battery swaps/deaths, probe moves, session
  splits, Resyncs, PC incidents, clock steps): `BATTERY_LOG_cohort3.md`, `change_log/` and the `README_*.md` of the
  recording repo; the field-PC **incident log** `E:\recording_health_reports\incident_log.md`, mirrored as
  `field2026-sync/from-field/<date>_cohort3-incident-log.md` (newest date = current, newest entry at the bottom); and the
  Notion page "4-Rat 3rd cohort full (SF07–SF12)":
  https://app.notion.com/p/4-Rat-3rd-cohort-full-SF07-SF12-3c23b0530d4a8152a204cce3afa11671 . `git pull` both sibling
  repos and read those before explaining a gap, a split session, a drift verdict or a unit-yield change, and keep
  `cohorts/<key>.yaml` (probe moves, clock steps, outages, firmware, field_flags) consistent with them.
- **Cohort-appendable:** canonical results at `results/<cohort>/<direction>/`; bulk off-repo; a new cohort is a
  `cohorts/<key>.yaml` + a re-run, never a restructure. Most WISER drivers, audio and the episode browser do not take
  `--cohort` yet (see [Known gaps](#known-gaps-verified-2026-09-28)).
- **One repo, many pipelines — merge to `main` often.** Ephys and CV preprocessing live here side by side because they
  share the cohort registry, `common/`, the ledgers and the cross-modal clock chain. A four-week ephys branch caused the
  2026-09-28 merge conflicts; keep branches short-lived.
- **Local first, then the server (user rule, 2026-09-28).** Every new ephys / LFP / IMU / sorting step is developed and
  validated on this PC against the local raw copy `E:\3rd_rat_spikes` (read-only) before it runs on BioHPC. The server
  runs only code already validated here, deployed from a commit, and its output is spot-checked against the local result
  (e.g. the LFP of SF07 `9_20260901_192912.215` is byte-identical on both machines).
- **Derived data lives on storage; analyse from there (user rule, 2026-10-07).** The cohort-3 LFP and sleep scores
  are on BioHPC storage `Q:\hc997\SocialFieldRat2026\3rd_rat\analysis\{lfp,sleep}\` (server
  `/fs/cbsuruizfs1/storage/hc997/…`, each folder with `README.md`, `VERIFY.txt`, `MD5SUMS`), next to `pc_time\`. The
  BioHPC workdir is scratch: a server job writes there, `ephys/server/copy_to_storage.sh` (`UPDATE=1` for additions)
  copies and verifies the result into storage, and the workdir copy is then deleted (sleep tree deleted 2026-10-07;
  the workdir LFP is kept for now for pending rescores). Local `D:` copies are partial working copies.
  **Post-run hook (user, 2026-10-07): every new server job ends through `ephys/server/run_then_store.sh`**
  (`PART=<part> bash run_then_store.sh <command…>`): it runs the job and, only if it exits 0, runs `copy_to_storage.sh`
  with `PARTS=<part> UPDATE=1`. That copy verifies paths, sizes and MD5 against an O_DIRECT read-back, and writes
  `VERIFY.txt` + `MD5SUMS` on storage. A job must exit non-zero when any of its files failed. A new output folder
  needs its own part in `copy_to_storage.sh` (`units` + `log_glob`); parts so far: `lfp`, `sleep`, `audio_levels`, `swr`,
  `emg_from_lfp`. When BioHPC is overloaded, a job can run on this PC, reading storage read-only, and its folder is uploaded
  to the workdir and stored with the same verified copy (done for `emg_from_lfp`, 2026-10-08). Run each job from its own
  per-commit checkout (`~/src/Field2026_Social_analysis_<commit>`), so a running job's scripts are never overwritten.
  Nothing is deleted automatically.
- Medium/large change: `implementation_plan/<date>-topic.md` **before**, `change_log/<date>-topic.md` **after**, and
  both index READMEs updated.
- `/analysis-definitions` for any deliverable; `/regime-aware-wiser-tracking` / `/regime-aware-cv-measurement` before
  interpreting WISER/CV behavior.
- Link integrity: a moved file with a broken inbound reference is a failure.
- Write Windows paths and LaTeX with raw strings / forward slashes when generating files from Python: `"E:\3rd…"`,
  `"\recovery"`, `"\beta"` have already turned into control bytes in five docs here (repaired 2026-09-28).

## Machines, environments, env vars

Clone paths differ per machine. On this PC (`DESKTOP-HUA1FJN`) the three repos sit side by side in
`D:\Documents\GitHub\` (so do `ProbeMaps` etc.); the other machine uses `C:/Users/Cornell/Documents/GitHub/`. Refer to
sibling repos as `../<name>` — in ephys code via `_common.sibling_repo("<name>")`, which falls back to the C: layout —
and never hard-code either absolute root in new code.

No repo-wide venv or lockfile; each subsystem has its own:

| Subsystem | Interpreter / env | Notes |
|---|---|---|
| `wiser/`, `ephys/` (all but sorting), `common/`, `analysis_exchange/`, generators | base Python (here `C:\Python313`) + pandas numpy matplotlib pyyaml | `analysis_exchange` is stdlib-only |
| `thermal/` | base Python + OpenCV ≥ 4.12 + numpy; ffmpeg on PATH | no GPU, no weights |
| `cv/` (shelter + `cv_field`) | conda env `cv` (`cv/environment.yml`, then a GPU torch built for CUDA ≥ 12.8 — the RTX 5070 Ti is sm_120; here `torch 2.13.0+cu130` / `torchvision 0.28.0+cu130` since 2026-09-28, installed with an exact `+cu130` pin because pip treats the old `+cu126` as satisfying `==2.13.0`; a `+cu126` build reports `cuda.is_available()` True but every kernel fails). Here call `C:\Users\Cornell\.conda\envs\cv\python.exe` directly (not `conda run`) | GPU for YOLO/DINOv3; set `PYTHONIOENCODING=utf-8` |
| `audio/` | conda env `audio` (`audio/environment.yml`); ffmpeg path set in `audio/configs/*.yaml` | |
| ephys sorting (`run_sort_session.py`, `resort_shanks.py`) | PreprocessPipeline's `preprocess` env (spikeinterface 0.103.2 + Kilosort4, GPU); pipeline root = `--pipeline-root` → `$PREPROCESS_PIPELINE_ROOT` → cohort YAML | Phy curation: `ephys/open_phy.py` → `phy2` env |
| `episode_browser/` | `episode_browser/requirements.txt` (streamlit, pyarrow required) | |

The miniforge3/anaconda3 paths in older docs and `.claude/launch.json` (`C:\Users\Cornell\miniforge3\…`,
`…\anaconda3\…`) do not exist on this PC.

Env vars: `FIELD2026_ANALYSIS_OUT_ROOT` (off-repo bulk; default `D:\Field2026_analysis_out`), `FIELD2026_COHORT`
(default `2026a`), `FIELD2026_WISER_ROOT` / `FIELD2026_MACHINE` (WISER snapshot dir), `PREPROCESS_PIPELINE_ROOT`,
`DINOV3_WEIGHTS`, `REOLINK_REC_ROOT` / `REOLINK_FFMPEG` (shelter CV), `EPISODE_BROWSER_*`.

**Data-server guard.** A PreToolUse hook (`.claude/hooks/protect_data_servers.py`) makes `Q:` (BioHPC storage) and
`S:`–`Z:` (ayadata) read-only, leaves `N:` (BioHPC workdir) writable and blocks `M:`/`P:`. It matches drive letters in
the command text, so an inline script that merely contains e.g. `M:` can be blocked — put such code in a script file. A
denial is policy: copy data to a local drive for a writable copy.

## Common commands

There is no test runner, linter or build step; run scripts directly. **Offline self-tests** use synthetic data (no
field data, no GPU unless noted) — run the one for the code you touched:

```powershell
python wiser\scripts\selftest_<module>.py        # ~22, one per wiser module (table in the WISER map); output_paths/wiser_inputs cover common/
python ephys\selftest.py                         # 20 checks: CE_params, de-glitch, index, staging (skips chanMap check outside `preprocess`)
python cv\view_quality.py --selftest             # shelter glass/view-quality decision logic
python cv\cv_field\selftest_field_select.py      # + selftest_field_mask.py, selftest_field_motion.py
python cv\cv_field\dino_gate.py --selftest       # + stratify_test.py / mask_field.py --selftest (cv env)
python cv\cv_field\landmark_track.py --selftest  # + landmark_night.py --selftest (ffmpeg), grab_frames.py --selftest
python cv\cv_field\sam3_vs_yolo_c1.py --selftest # + backup_social_field_rat.py, c1_yolo_video_test.py, c1_yolo_fixed_spots.py --selftest (ffmpeg + PyAV)
python thermal\detect_blobs.py --selftest        # + thermal\detect_traces.py --selftest
python audio\scripts\selftest_features.py
python episode_browser\selftest.py
python -m analysis_exchange.tests.test_bridge    # run as a module from the repo root
```

```powershell
python summaries\_generate_summaries.py   # regenerate after a registry edit, a new cohort, or any added/moved canonical report/figure
python analyses\_generate_analyses.py     # (both read analyses/registry.yaml; never hand-edit their outputs)
python analysis_exchange\scripts\bridge_cli.py new|validate|publish|verify|list ...   # or /export-analysis-result
python -c "from common.output_paths import prune; print(prune('my_analysis', keep=3))"  # dry run; apply=True deletes
cd episode_browser; python -m streamlit run app.py                                   # researcher-facing browser
bash ephys/run_qc.sh 2026c 8              # full post-offload ephys QC (index -> time chain -> QC report -> coverage), ~2 h
```

## Architecture (the parts that need several files to understand)

**Path + cohort SSOT with import shims.** `common/output_paths.py` is the only place that knows the output layout;
`common/cohorts.py` loads `cohorts/<key>.yaml`; `common/wiser_inputs.py` resolves WISER snapshots. Subsystems reach
them three ways: WISER drivers put `wiser/src` on `sys.path` and `import output_paths` / `wiser_inputs` (re-export
shims); `cv/cv_field/` has its own `output_paths.py` + `cohorts.py` shims; `ephys/_common.py` inserts `common/` on
`sys.path` directly. Add logic in `common/`, never in a shim. `output_paths`: `run_dir()` (off-repo, timestamped),
`report_dir()`/`figure_dir()` (in-repo; a single argument is treated as the direction), `archive_report_dir()`,
`write_run_manifest()` (in-repo pointer to the off-repo run), `list_runs`/`latest_run`/`prune`.

**Two homes for every run's output.** Off-repo bulk under `$FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/<name>_<ts>/`;
in-repo canonical report + figures under `results/<cohort>/<direction>/{reports,figures}/` with a `run_manifest.json`
pointer. Ephys adds a per-cohort derived-data root (`ephys.analysis_root`, below). Regenerable bulk (per-second
tables, per-channel JSON) never goes into `results/` — the ephys ones moved out on 2026-09-28 and `.gitignore` guards
them. In 2026a, figures sit in per-question subfolders `figures/<question_id>/` (the analyses generator relies on it).

**Research directions** key results, summaries, analyses and archive: `wiser_baseline`, `wiser_d1_nightly`,
`wiser_d2_routes`, `wiser_d3_sleep`, `wiser_policy`, `cv_shelter`, `cv_field`, `audio_soundscape`, `crossmodal`,
`ephys_spikes`. Cohorts: `2026a` (1st cohort, 2026-06-28 → 07-08, WISER/CV/audio) and `2026c` (3rd cohort SF07–SF12,
2026-08-30 → 09-12, first with WILD neurologgers); there is no `2026b` registry file.

**Navigation, not code, is the entry point for the science.** `analyses/README.md` → `analyses/<direction>/<id>.md`
(verdict, evidence, canonical driver+report, figures, blockers, superseded claims, rerun command) and
`summaries/<direction>.md`, all generated from `analyses/registry.yaml` (33 questions; `cv_field` and `ephys_spikes`
have no entries yet). `STATUS.md` is the cohort × direction board. **`research_logic/`** keeps the *reasoning* of a
research direction: one YAML logic graph per direction (questions → competing hypotheses → tests → results → current
judgments → next steps; typed edges, cited sources, rounds, conflicts), validated and rendered into an interactive map
by `research_logic/logic_map.py` (`check` / `build` / `show` / `index`). It is updated only after research steps (never
preprocessing) via the `research-logic` skill / agent. Current graph: `graphs/sleep_2026c.yaml` (map:
https://claude.ai/artifact/F5rCafmi6VuoXspRbEuczS).

**Two coordinate frames that do not trivially convert.** WISER = inches in an unverified offset frame; CV = the
paddock frame, origin pole A0, 609.6 × 1219.2 cm = 240 × 480 in (`cv/field_coords.py` works in cm; the newest camera
calibration release, `calibration_qc/` in the recording repo, returns inches and is exploratory-only). The WISER↔field
bridge is the georeference transform (`wiser/src/field_transform.py`); its config
`wiser/configs/wiser_to_field_transform.json` does not exist yet, so the transform is a no-op. No directional/physical
WISER claims; only topology and distances ≥ 14 in. Known so far (user): the WISER axes point the same way as the
paddock/calibration axes (2026-09-28; the origin is offset — cohort-3 houses sit near WISER (423, 730) / (614, 730) in
vs paddock ≈ (135, 120) / (347, 119) in), and **the box on each paddock pole is a WISER UWB anchor** (2026-09-29) — so
anchors sit at known paddock positions. The DBs hold only tag fixes (up to 9 anchors per fix, arena `DefaultArena`),
no anchor coordinates: the anchor layout (IDs, WISER-frame XYZ, which pole) is requested from the field PC
(field2026-sync `tasks/2026-09-28_lab-request-cohort3-weather-and-sync-logs.md`, item 4). With it, the WISER → paddock
transform is a direct fit on anchor ↔ pole pairs; the same boxes (`BOX_<pole>`) are camera landmarks.

**Identity differs by modality.** WISER = `shortid` tag (resolve via `wiser/configs/rat_identities.csv`, which has
per-tag `valid_until`; a tag is not an animal). Video: coband color only in color frames; IR frames (night, and
CH03–CH06 much of the day) are monochrome = coband pattern, never color — cams switch mode with the light, so check the
frame; no cross-camera identity exists. Ephys = logger MAC per animal
(`cohorts/2026c.yaml ephys.loggers`). Roster: `FIELD_OBSERVATIONS.md` (2026a).

**Clocks differ per device** — treat any cross-modality alignment as unverified unless a shared event confirms it.
WISER is Unix-ms UTC (local time via a hard-coded `LOCAL_TZ_OFFSET_HOURS = -4` in `wiser_analysis_utils.py`: EDT
only). Recorder file names and PTS are field-PC local time; the OSD burned into CH01–CH08 is the NVR clock (~PC − 59½
min, drifting) and the thermal OSD also runs ~1 h behind — never read an OSD clock. Weather uses the console clock.
Neurologger RTC = logger wallclock, mapped to field-PC time by `ephys/pc_time_chain.py` → `pc_time.dat`; video↔PC
phase by the LED sync. The field-PC clock itself stepped several times (`cohorts/2026c.yaml
ephys.field_pc_clock_steps`). Details of every mechanism: [Sibling repos](#sibling-repos-the-field-record).

**Measurement is regime-confounded by construction.** WISER UWB ~4–7 in jitter plus weather and burrow dropout; CV
shelter cams image through IR-filter glass (fog/condensation/rain/glare); tall grass occludes the whole-field cams;
thermal is auto-gain. Carry that context before any behavioral claim — the `/regime-aware-*` skills and the
`wiser-measurement-auditor` / `cv-measurement-auditor` subagents enforce it.

## Code map

### `ephys/` — WILD CE64 neurologgers (64 ch, 20 kHz, int16) → direction `ephys_spikes`

Raw (read-only): `E:\3rd_rat_spikes\<SFx>\<MAC>\<slot>_<YYYYMMDD>_<HHMMSS>.<ms>\` (`raw_data_roots.analysis_pc.ephys`).
Off-repo root `<ar>` = `ephys.analysis_root` (2026c: `D:/3rd_rat_spikes/analysis`; fallback `<OUT_ROOT>/<c>/ephys_*`)
holding `index/` (SESSION_INDEX mirror + regenerable bulk), `stage/`, `sort/`, `pc_time/`, `tools/`.

**Before choosing, sorting, matching or interpreting any session, run `/regime-aware-ephys`.** It holds the per-logger
record: probe advances and their ~4 h unstable windows, contact/implant losses, the ADC lane, battery gaps, clock
steps, disturbance windows and the 09-11 population change. It also points to the current sources (Notion cohort page,
the incident log and offload QC in field2026-sync, BATTERY_LOG). **Sorting strategy:** sort per *block* (continuous FM65,
gaps < 5 min joined; never across a battery round, probe move or firmware change), then match units across blocks. The
plan and the SF07 pilot are in `implementation_plan/2026-09-28-ephys-block-sorting-strategy.md`. On this PC the pipeline
checkout is `D:\Documents\ayalab\PreprocessPipeline` (set `PREPROCESS_PIPELINE_ROOT`), and the `preprocess` env has to
be rebuilt. On BioHPC the env exists (`/home/hc997/src/PreprocessPipeline/.venv`, uv, torch cu130); access needs one
shared SSH connection the user opens in Git Bash (`ssh -M -S ~/.ssh/cm-gpu -o ControlPersist=12h -fN gpu`, one Duo code), then
`ssh -S ~/.ssh/cm-gpu gpu '<cmd>'` — details in the plan's *Production on BioHPC*.

| # | Stage | Command (`--cohort 2026c`) | Output |
|---|---|---|---|
| 0 | card size check / ADC-lane quarantine | `check_offload_sizes.py --card SF7=<records>:<MB>`; `quarantine_adc_sessions.py [--move]` | `reports/…offload_sizes_*.csv`; moves lane-ON sessions to `<raw>/_quarantine_adc_lane_on/` |
| 1 | QC wrapper | `bash ephys/run_qc.sh 2026c 8` = 1a–1d | |
| 1a | session index | `build_session_index.py --workers 8` | `reports/…session_index_<c>.{csv,md}`; JSON detail + mirror → `<ar>/index/` |
| 1b | field-PC time chain | `pc_time_chain.py --write-pc-time <ar>/pc_time` | `reports/…pc_time_chain_<c>.{csv,md}`; `<ar>/pc_time/<SFxx>/<s>/pc_time.dat` + `pc_time_fit.json` |
| 1c | offload QC report | `offload_qc_report.py` | `reports/…offload_qc_<c>.{md,csv}` |
| 1d | coverage | `coverage_tables.py` | hourly csv/md + raster (in-repo); 1-s CSVs → `<ar>/index/` |
| 1e | field request | `field_request.py [--push/--check]` (or the `/offload-field-request` skill) | a task file in field2026-sync (`--push` commits + pushes there) |
| L | LFP for every session (before sorting; phase L of the plan) | `make_lfp.py [--animal …] [--session …] [--workers 8]` (`--dry-run`, `--selftest`) | `<ar>/lfp/<SFxx>/<session>.lfp` + `.lfp.json` (pipeline filter: Butterworth-5 450 Hz zero-phase on raw, ÷16 → 1250 Hz; FM64 de-glitched in the stream; one sequential read stream per worker; ~60× real time on this PC from the USB HDD, ~200× on BioHPC with `--workers 8`; server and PC outputs byte-identical). Windows: `--start-seconds S --max-seconds D`; `--src <staged dir> --out-name N` converts a staged (already de-glitched) copy instead of the raw session. Whole cohort on BioHPC: `ephys/server/run_make_lfp.sh` → `/workdir/hc997/ephys_2026c/lfp/` + MD5 manifest, copied 2026-10-06 to storage `3rd_rat/analysis/lfp/` (never into `WILD/`) by `ephys/server/copy_to_storage.sh` (also `analysis/sleep/` = the sleep scores without the hard-linked `.lfp`; never deletes, refuses foreign destinations, verifies paths + sizes, MD5 source vs an O_DIRECT read-back, and the LFP manifest → `VERIFY.txt` + `MD5SUMS` per folder) |
| EMG | LFP-EMG per session (the user, 2026-10-08: save it like the lab's `day8.EMGFromLFP.LFP.mat`) | `emg_from_lfp.py --lfp-root <…/analysis/lfp> --out <dir> [--animal …] [--session …] --pc-time-root <…/analysis/pc_time> [--workers N]` (`--selftest`); whole cohort on BioHPC: `ephys/server/run_emg_from_lfp.sh` (part `emg_from_lfp` of `copy_to_storage.sh`) | storage `3rd_rat/analysis/emg_from_lfp/<SFxx>/`, per session:<br>• `<s>.EMGFromLFP.LFP.mat` — STANDARD: the pipeline's own `_compute_emg_from_lfp` (= neurocode `getEMGFromLFP`), 300-600 Hz (effectively 300-450 Hz: the `.lfp` is low-passed at 450 Hz), ±0.5 s at 2 Hz, one channel per shank;<br>• `<s>.EMGFromLFP50Hz.npz` — FAST: 50.4-ms windows every 20 ms, 2 channels per shank; `j` = make_imu's 50-Hz index, `t_pc_ms`, `corr`, `log_rms`;<br>• `.json` — parameters.<br>The scorer's `lfpemg` pilot used all 64 channels: the pipeline flattens a Python list of equal-length spike groups, so pass a 1-D object array. The sleep scores are unaffected (EMG channel choice only). SF07's correlation baseline is high (common mode). |
| IMU | read the head IMU (read-only) | `read_imu.py --check <session_dir>`; `read_imu(session_dir, start_s, dur_s)` | nothing written; `analogin.dat` lanes 1-3 acc, 4-6 gyro, 7-9 mag at 1250 Hz (frame k ↔ amplifier 16k). **Magnetometer x saturated on all six loggers — the headstage carries a magnet (user, 2026-09-28) → no magnetic heading; never use lanes 7-9 for orientation.** Layout, validation and the audit of the lab MATLAB IMU scripts: `docs/methods/wild_ce64_imu.md` |
| IMU+ | movement / 2D turning / posture per session (sleep-EMG, identity with video and WISER) | `make_imu.py [--animal …] [--session …] --pc-time-root <…/analysis/pc_time>` (`--selftest`) | `<ar>/imu/<SFxx>/<session>.imu.npz` (50 Hz), `.imu_1s.csv` (per second, field-PC time), `.imu.json`; 6-axis Fusion AHRS in the head frame (lab map S verified); ~45 s per 12-h session locally |
| S | sleep score (PILOT) | `score_sleep.py --sessions SF10:<s> … [--variants imu imu_nremgate lfpemg imu_remclean] [--anchor A:S:REC_S:STATE]`; no `--sessions` = rebuild the CSVs. `imu_remclean` is *derived* from `imu_nremgate` (copied, not rescored) + REM post-rules: no REM after > 10 s WAKE, none where the head IMU moves ≥ 3 of 5 s, REM ≥ 7 s (`change_log/2026-10-05-sleep-rem-clean.md`). Per-session channel overrides (1-based, the scorer's numbering): `ephys/configs/sleep_channel_overrides_<c>.yaml`, applied on the next rescore (`--redo`: clears the scorer's reused products but never the EMG file; keeps a user-edited review copy). Batch: `--all --workers N`, resumable, failures → `<out>/_errors/`; `--lfp-root/--imu-root/--out-root`; `--report-name` (pilot = `sleep_pilot`, full run = `sleep_scores`). The server gets the compact IMU inputs from `--export-imu-bundle DIR` (861 MB vs 15 GB, identical scores) and runs `ephys/server/run_score_sleep.sh` (imu_nremgate + imu_remclean → `/workdir/hc997/ephys_2026c/sleep/`). Review: `sleep_review.py [--root …] [--variant imu_remclean]` writes `<root>/review_<variant>.html` (every SSResults figure in order, keys 1 ok / 2 logger noise / 3 bad, autosave + CSV export → keep in `ephys/configs/sleep_review_<c>/`); `sleep_review.py --merge <export>` → `reports/…sleep_review_<c>.csv` (scores + the user's verdict/note + YAML `tags`). Quantification: `sleep_quant.py export --src <sleep root> --out <dir>` (server; compact 1-s states + metrics, local copy `D:/3rd_rat_spikes/analysis/sleep_server/states_1s/`) → `sleep_quant.py quantify --states <dir>` → `reports/…sleep_quant_<c>.md` + `_days/_hourly/_sessions/_window_per_animal/_weather_daily/_glm/_slopes` CSVs (weather from field2026-sync: quasi-binomial GLM of the 24-h share on temperature / humidity / rain, cluster-robust by day; per-animal REM/NREM slopes over days), figures `…sleep_quant_{per_day,circadian}_<c>.png` (NREM/REM per 24 h phase-weighted by sunrise/sunset, window 08-31→09-06 = all 6 animals, mean ± SEM) | `<ar>/sleep/<variant>/<SFxx>/<s>/` (hard-linked `.lfp`, `session.mat`, SleepScoreMaster outputs, `complex_system/` = the user's review copy for `Sleep_dynamics/state_editor.py`, never overwritten); `reports/…sleep_pilot_<c>.csv` + `_agreement_<c>.csv`. Scorer = PreprocessPipeline `state_scoring.py`, unmodified; the IMU enters as `EMGFromLFP.LFP.mat`. Refuses sessions with frozen/invalid IMU. ~10–12 min per variant per 8-h session |
| S2 | sleep pass 2 (fixed per-animal channels / rescaling / thresholds) | `score_sleep.py --variants imu_fixch` (server, all sessions; channels `ephys/configs/sleep_channels_<c>.yaml`; writes `<session>.SleepScoreRaw.npz`) → `sleep_pass2.py --src <sleep tree> --imu-root <bundles> --threshold-rule median_session --out-variant pass2med_remclean --workers 24` | reproduction gate first (must be exact); **CONTROLS only** (user 2026-10-07: per-session thresholds follow the probe, which may move daily): `imu_fixch`, `pass2med_remclean` (median rule), `pass2_remclean` (pooled_dip, wrong for SF07). Kept; never the main score. Reports `reports/…sleep_pass2{,med}_{gate,scale,changes,probe_advance_check}_<c>.csv` |
| SF | **FINAL sleep scores (use these)** | `sleep_final.py --cohort 2026c` (config `ephys/configs/sleep_final_<c>.yaml`) | = `imu_remclean` (reviewed per-session scores) with **only SF07 `2_20260905_093310` replaced** by `pass2med_remclean`; 1-s states `D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final/`; table `reports/…sleep_review_<c>.csv` (rebuilt with `sleep_review.py --merge … --scores reports/…sleep_scores_final_<c>.csv --variant final`). Exclusions: user `noise`, `SF12_contact_failing`, `valid_until`, refused, < 0.5 h (skill `regime-aware-ephys` § Sleep scores) |
| SC | REM timing vs sleep history (the PI's scheduling hypothesis, as a test) | `sleep_cycles.py --cohort 2026c [--states <states_1s>] [--states-s3 <nremgate states_1s>]` (`--selftest`, 12 checks) | REM-anchored cycles (no merging, censored at session ends) + descriptive R1–R3 + discrete-time (10 s) competing-risks NREM → REM / Wake, M0/M1/M2, leave-one-date-out on the light phase, LOAO, night transfer, ablations, S1–S3; bulk `$OUT_ROOT/2026c/sleep_cycles_<ts>/`, report `reports/…sleep_cycles_<c>.md` + CSVs, 4 figures, pointer `run_manifest_sleep_cycles_<c>.json`. Excludes SF07 `2_20260905_093310` (`EXTRA_EXCLUDE`; v1 only). **v2 (current):** `sleep_cycles_v2.py --states <states_1s_final> --review reports/…sleep_review_<c>.csv --tag final` (`--selftest`, 14 checks): 24 h, records joined across file splits ≤ 60 s (gap = unknown), rolling 10/60/180-min history + REM-anchor terms, 2-harmonic phase + experiment time, leave-one-day-half-out + forward chaining → `reports/…sleep_cycles_v2_<tag>_<c>.md` + claim audit v2 |
| SWR | sharp-wave ripples, automatic (plan `implementation_plan/2026-10-07-swr-detection-automation.md`) | `swr_auto.py --animal SF10 --sessions … \| --all [--min-minutes 10] --out DIR [--lfp-root Q:/…/analysis/lfp] [--fit block\|nrem\|all]`; channels + `reference_session` per animal × probe block in `configs/swr_channels_2026c.yaml` (0-based cols = Neuroscope; all confirmed by the user 10-08; `boundary_features: ripple` where the probe has no clear sharp-wave reversal = SF07 / SF11 / SF12 block 3 (user, LFP 10-08); **SF11 has clear ripples only to the 09-02 evening round (block 1a; `quality_flags` SF11_ripples_lost from 09-02 19:08); SF11 after that and SF12 block 3 are low-contrast: 19–29 % of candidates selected, not SWR-specific — screen per session before use**; `skip` = SF12 09-09 18:47→09-10 08:35; proposals from `swr_channel_scan.py --animal --session --out [--spw-ref]`: NREM ripple-envelope ratio + sharp wave per column (`spw_ref_uV` = the team's `lfp_profile_check` events + baseline-subtracted 1–50 Hz), noise = top ripple-free site); LFP-EMG = `swr_emg.py` (= the pipeline's EMGFromLFP, one site per shank); BioHPC: `server/run_swr.sh` (all animals in parallel via `server/swr_all_animals.sh`, 18 workers each; needs the final 1-s states in `swr_inputs/states_1s_final/`; ends via `run_then_store.sh`, part `swr`) | `<out>/<SFxx>/<s>/<s>.swr_events.csv/.npz` (start/stop/peak s, SwMax/RipMax local z, state + IMU emg at the peak, envelope ratio per shank + noise, emg_lfp, theta_delta_log, flags x_rem/x_theta/x_moving/x_emg_lfp, **`excluded`** = REM + theta everywhere, + movement + LFP-EMG on no-reversal blocks; use `excluded == False`), `.SWR.evt`, `.swr_summary.json` (boundary source, own-fit fraction + NREM amplitude ratio to the reference = drift checks), `.swr_qc.png`; storage `3rd_rat/analysis/swr/`. Method = the lab's DetectSWR ported exactly (`swr_detect.py`, `--selftest`; replay of the user's clicks = their final events on 17 lab sessions) with the manual `check` replaced by ONE standardized k-means boundary per animal × block (fitted on NREM candidates of the block's reference session, applied in raw units: a per-session refit drifted, F1 0.49 vs 0.83 on the SF10 09-11 night) + check-mode localisation, rat parameters. Validation vs the user's GUI scoring, kept events: F1 0.81–0.91 (SF07 ×3, SF09, SF10 ×2; lab median 0.91 = the user's same-animal consistency); flags from the user's blind review (SF07 flagged 1/40 ripple). **Temperature: `swr_temperature.py run` (NREM ripples vs outdoor temperature, day vs night; 30-min bins per animal × block; model P pre-registered + model H with hour harmonics, animal-level inference, LOAO; → `reports/…swr_temperature_2026c.md`) — result 10-08: no ambient-temperature effect Established; time of day dominates (frequency +4.5 → −3.2 Hz, rate +18 → −8.5 /NREM min over the rest phase); night ripples faster and more frequent (6/6).** **Depth: `swr_depth.py run` (NREM depth = the scorer's raw spectral slope of `imu_fixch`, storage `analysis/sleep/imu_fixch/`, z within block; day vs night, time of day, rate ~ depth) — 10-09: night NREM deeper than day (6/6), depth explains ~1/4 of the ripple-rate time-of-day profile.** **Quality / user guide: `swr_quality.py validate` (production events vs the user's GUI scoring in `configs/swr_validation_2026c.yaml` + server-vs-local check) → `build` → `reports/…swr_quality_2026c.{md,csv}` = per-session tier validated / good / check / low_contrast / exclude + `use_until` + regime `info`; read it before using SWRs.** Evaluation tools: `swr_auto_eval.py`, `swr_judge.py extract\|context\|evaluate\|evaluate-c3` (reference sessions `configs/swr_reference_sessions.yaml`, copies `D:/Field2026_analysis_out/swr_reference/`; user clicks `configs/swr_review_2026c/`). Review GUI: `swr_check_gui.py --animal --session --channels R S N (1-based) [--hide-flagged]` (local server: MATLAB-helper scatter + ±0.5/±2 s popup, live 1-NN propagation, blind until 'done', blind 'Review flagged sample' of 60 events) |
| DW | delta waves (cortical DOWN states; plan `implementation_plan/2026-10-08-delta-wave-detection.md`) | `delta_detect.py --selftest` / `replay --session-dir <lab session> [--script lab\|user] [--wrapper 2024-06\|2025-09]` / `scan --lfp <s>.lfp --states <SleepState.states.mat> --xml <final XML> --out DIR --label L [--workers N]`; `delta_mua_check.py --raw <raw session> --states … --xml … --scan-npz <L>_delta_scan.npz --ref-col C --out X.npz`; review page for the user `delta_review_gui.py --set ANIMAL:SESSION:COL … --n 30 --lfp-root … --raw-root … --states-root … --scan-dir … --out DIR` (per event the shank's LFP ±1.5 s + raw MUA raster; keys 1/2/3; exports → `ephys/configs/delta_review_2026c/`); per-event DOWN-state check `mua_nrem.py --raw <raw session> --states … --xml … --out <s>.mua_nrem.npz [--workers 10]` (reusable NREM threshold crossings, all 64 ch, FM65 only; `D:/Field2026_analysis_out/2026c/mua_nrem/<SFxx>/`; 2–11 min/session) → `delta_detect.py verify --scan-npz … --ref-col C --mua-npz … --out <stem>` (spikes ±50 ms vs −1…−0.4 s over sites ≥ 1 Hz whose firing does not rise at the peak; ratio ≤ 0.5 = verified; replaces verify_firing's sorted units) | Exact port of neurocode `FindDeltaWaves.m` (0.5–9 Hz FilterLFP, min→max→min of 150–650 ms, z rules) + `detect_delta_waves.m` (NREM, CleanLFP [6 10], EMG < 0.6, peak − end > 3; `ignore_intervals` dropped after detection up to 2025-09, cut from the LFP since) and the user's older script (`R_Project/PPP/codebook/pre_Ephys_pipline.m`: whole session, CleanLFP [6 Inf] ±0.5 s, > 4.5); replay on 9 local lab sessions: recall 1.000 at ±10 ms, ≤ 2 extras. `scan` → `<out>/<L>_delta_scan.{csv,npz,json,png}` + `_delta_profile.png`: per channel NREM rate, 1–6 Hz share (lab channel rule), 250–450 Hz LFP power at the peak (CAR; DOWN-state proxy — no sorting), delta-triggered LFP of all sites, per-shank proposal. **SF11 top sites: DOWN state confirmed (raw MUA 10–35 % of baseline); SF07 top sites carry no units → per-event check on shank-1 spiking sites: verified (ratio ≤ 0.5) SF11 70–93 %, SF07 35–62 % of events; user review (reference) agrees moderately (SF07 AUC 0.77); threshold + output pending the user** (`D:/Field2026_analysis_out/2026c/delta_scan_20261008/`). The detector keys on a peak then a deep trough — check polarity on the channel. |
| PR | phasic vs tonic REM (plan `implementation_plan/2026-10-09-phasic-tonic-rem.md`; reference Montgomery 2008 = `Ref/zns6731.pdf`) | `phasic_rem.py --selftest` / `run --animal A --session S … --lfp-root … --states-root <states_1s_final> --imu-root <ar>/imu --emg-root <…/analysis/emg_from_lfp> --out DIR`; sites `configs/phasic_rem_channels_2026c.yaml` (per animal × block, from the SWR session 10-09: B = `ripple_col`, A = `sharpwave_col` → tip on that shank; skip SF11 after 09-02 19:08, SF12 from 09-08 07:26; no A for SF07 / SF11 1a); blind review page `phasic_rem_review_gui.py --set A:S … --run DIR …` (exports → `configs/phasic_rem_review_2026c/`) | `<out>/<SFxx>/<s>.phasic_rem.{json,npz}` + `_events.csv` / `_controls.csv`. B = Mizuseki 2011 Online Methods (`Ref/nn.2894.pdf` p. 10; `--b-variant paper`, default: 5–12 Hz, theta peaks = dy/dt zero crossings, 11-sample smoothed intervals < P10 for > 900 ms, min < P5, amplitude > REM mean; the paper names no filter → the `phasic_tonic` FIR) or `--b-variant phasic_tonic` (exact port of that package: Hilbert troughs, ≤ / ≥; replay identical). With this FIR dy/dt also marks double crests → the paper variant finds fewer epochs (2.3–3.5 % vs 4.6–4.8 % of REM), with the same IMU / EMG checks; A = Montgomery 2008 (AR(2) whitening, 0–250 Hz power in 1-s windows, mean + 2 SD, ±1 s maxima) on the radiatum substitute — **no probe reaches SLM / DG ml (REM theta phase shift ≤ 80°)**. Pilot 10-09 (SF10, SF12 × 2, `D:/Field2026_analysis_out/2026c/phasic_rem_pilot_20261009/`): B 1.2–1.3 /REM min, 4.7 % of REM; A↔B overlap 4–6× chance; B epochs carry more head movement / LFP-EMG than tonic controls, A events not; review page `…/phasic_rem_review_20261009_1520/index.html` awaiting the user. |
| SS | internal sleep schedule: memory, carry-over across wakes, compensation (plan `implementation_plan/2026-10-07-sleep-internal-schedule.md`, rev. 2; literature `docs/methods/sleep_sequence_literature_audit_2026-10-07.md`) | `sleep_schedule.py phase0` / `phase1` (`--selftest`; `--smoke` writes everything to the run folder, for synthetic data) | Phase 0 (definitions + counts, no outcomes): records, wake bouts, Watson-2016 episode units (MA < 40 s; 100 s = our pipeline's `_states_to_episodes`; 20 s = Park), gaps with cause (probe_move / round_logged / round_inferred / no_handling_recorded) + WISER movement as description → `reports/…sleep_schedule_phase0_<c>.md`. Phase 1: 10-s NREM steps, layers L0 clock → L1 current state → L2 accumulated since the last REM → L3 bands to 12 h, clocks (NREM / wall), other animals' REM (S), forward chaining over day-half blocks, opportunity / timing split (Larson–Dinse), cycles ahead, refractory curve → `reports/…sleep_schedule_phase1_<c>.md`. `phase2` (`sleep_schedule_phase2.py`): carry-over across natural wakes by wake length, long wake → next REMs, compensation (both scorings), battery gaps with purge, empirical hazards; `phase2b` (`_phase2b.py`): effect sizes, lagged NREM depth, NREM tails, morning vs evening; `phase3` / `phase3b` (`_phase3.py`): naps vs day sleep, recovery trajectories, fragmentation, same-events check, 24-h budget. `phase4` (`sleep_schedule_temp.py`): ambient temperature anomaly as a slow REM gate. `phase5` (`sleep_sync.py`): REM synchrony between animals (housemates vs animals elsewhere, WISER house per second). `phase5b` / `phase5c`: movement coupling among sleeping housemates (head-IMU seconds cache; 50-Hz IMU-as-EMG VeDBA at 20 ms) and twitch-vs-awakening outcomes. `phase6 --emg-root <emg_from_lfp>` (`sleep_events.py`): the **sleep-perturbation event library** for later use:
- sources: movement events (first mover; followers tight ≤ 0.1 s / loose ≤ 1 s; non-movers), sound candidates (house-mic jumps ≥ 20 dB, unvalidated), battery-round handling, random co-sleep controls;
- per participant: outcome (stay / to REM / to NREM / wake at 10 / 30 / 60 s; scenario woke / not_woken; wake length);
- pointers to the IMU, LFP, EMG, house videos and mics;
- a time-shift chance level, and the LFP-EMG by role with matched-size and timing controls.

Library `$OUT_ROOT/2026c/sleep_events_<ts>/` (`events`, `participants`, `control_*`, `handling` csv.gz, `traces.npz`, README, `thresholds.json`), report `reports/…sleep_events_2026c.md`. Cut at 09-11 19:40 (females). **Next stage: the "sleep behaviour explore"** — [plan](implementation_plan/2026-10-08-sleep-behaviour-explore.md) (sequence + IMU + WISER + temperature + handling only, no LFP features), after the [logic audit](docs/methods/sleep_logic_audit_2026-10-08.md) (#13 night–day "balance" withdrawn: a cohort-wide drift of sleep from night into day). Drivers: `sleep_explore.py stepA` (the reproduction gate of the audit's checks, both scorings; `--selftest`) → `reports/…sleep_explore_A_2026c.md`; `sleep_model.py stepB [--scorings final pass2med] [--workers N]` (the scheduler model: counter P = NREM since the last REM, emptied at REM by exp(−r/κ), discounted over a wake by exp(−d/τ_w), spline read-out in the 10-s NREM hazard; grid τ_w × κ + hard reset / pause / constant discharge, nested forward chaining vs M2t / gate-only, leave-one-animal-out τ_w; `--selftest` recovers a simulated τ_w; ~3.5 h on 6 workers — check free memory first) → `reports/…sleep_explore_B_2026c.md`; `sleep_model_diag.py` (post-hoc split of step B by the wake class since the last REM); `sleep_explore_c.py stepC [--parts c1 c2 c3 c4] [--scorings FINAL pass2med] [--workers 8]` (day vs night with the counter: C1 night gain at matched count and prior wake, C2 light step vs smooth clock at dusk / dawn, C3 WISER location and housemates, C4 the 12-day drift vs weather and time outside; own Newton multinomial with cluster-robust CIs; `--selftest`; ~15 min) → `reports/…sleep_explore_C_2026c.md`. `sleep_explore_d.py stepD1` (natural dawn wakes vs the morning-round REM payback; also `payback_from_records(recs, gaps, label)` / `budget_from_records(recs, label)` for any — e.g. simulated — record set, ~1–3 s per call) → `reports/…sleep_explore_D1_2026c.md`; `sleep_model_e.py heldout` (counter vs a 2nd-order semi-Markov momentum model; + an NREM homeostat S) → `reports/…sleep_explore_E_heldout_2026c.md`; **`sleep_sim.py stepE [--h19] [--reps 100]`** (the generative scheduler model: the fitted counter / clock / REM-exit rules tabulated and simulated in numba, conditional on the observed long wakes ≥ 7 min and unknown runs; short wakes sampled with their next state; checks daily REM / NREM and their SD, day / night REM share and rate, first-REM latencies; `--selftest`; ~2 min) → `reports/…sleep_explore_E_2026c.md` (read its Reading first); D2 and E (ii) / (vi): `sleep_sim_checks.py [--from-run <dir>]` → `reports/…sleep_explore_D2E_2026c.md`. Amendment 1 (plan §9): `sleep_stability.py predict | analyse` (sleep stability: `predict` writes the held-out per-10-s-NREM-step predictions of B-full, the model without the count and a perturbation-blind B-full trained without the 3 h after rounds to `$OUT_ROOT/2026c/sleep_heldout_steps/heldout_steps_{final,pass2med}.csv.gz` (reuse them); `analyse` = S1 which movements wake (Phase-6 library), S2 / S2b post-round and post-long-wake O/E, S3 the simulated response with the post-round hours masked; `--selftest`; ~12 min) → `reports/…sleep_explore_S_2026c.md` (read its Reading first); `sleep_explore_g.py run` (G1–G4: the origin of the REM repayment #43) → `…_G_2026c.md`; `sleep_explore_f2.py run` (WISER / environment / social hypotheses H4, H14–H17, H22, H25) → `…_F2_2026c.md`; `sleep_explore_f1.py run` (sequence-only hypotheses H5, H7–H11, H20, H23; ~26 min on 6 workers) → `…_F1_2026c.md`. Amendment 2: `sleep_perturb.py run` (part P, the perturbation dynamics: a decaying arousal on the NREM → WAKE logit after the rounds, fitted on waking only, cross-fitted by date parity; `sleep_sim.simulate_records(..., arousal={record_id: (a, tau_s)})`, identical output without it; `--selftest`; ~7 min) → `…_P_2026c.md`; `sleep_perturb.py runT` (part T: + a delayed second phase b (s/τ2) e^(1 − s/τ2) over the 6 h after rounds, bases blind to them; ~19 min) → `…_T_2026c.md`. Result: one counter beats M2t, REM empties it, a wake forgets it with τ ≈ 5–10 min; at the same count and prior wake the night lowers REM entry to about a third, with no step at dusk / dawn; housemates' sleep predicts a rat's own transitions; simulated from these rules the model reproduces daily REM and its day-to-day variation without a budget, but not the REM repayment after handling; it predicts the amounts of sleep after a battery round, not its stability — the first hour has ~1.3–1.4× the predicted waking in all six rats, and the count cannot tell which movements wake; the same count also predicts the next REM bout's length; a decaying arousal captures the post-round waking but not the REM delay, and a delayed calm phase adds nothing (claims #32–#58). **Read the [claim audit](results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md) before citing any result** (e.g. the night limits REM entry, not REM duration — Established; "delay then catch-up" — withdrawn; per-session thresholds create false within-record persistence — use `pass2med_remclean` as the check) |
| AU | in-house mics + camera audio, per-second band levels | `mic_band_levels.py --root <3rd_rat> --mics MIC01 MIC02 CH01 CH02 --dates … --out <dir> --workers N` (`--selftest`); server `ephys/server/run_audio_levels.sh` (through the post-run hook) | `<stream>/<raw stem>.csv.gz`: t_pc (field-PC s), `<band>_mean_db` / `_max_db` (mics b0–b4 50 Hz–100 kHz, cameras c0–c2 50 Hz–8 kHz) + `extract_log_<ts>.csv` (one per run; timing = stretched / end_anchored / pts, `timing_err_s`, `missing_s`; camera audio decoded on its stream timestamps — some hours have holes up to ~13 min); workdir `/workdir/hc997/ephys_2026c/audio_levels/` → storage `3rd_rat/analysis/audio_levels/` (VERIFY PASS, commit 7fbd966; local copy `D:/Field2026_analysis_out/2026c/audio_levels/`). MIC01 / MIC02 are on the ceiling inside the two houses (user); MIC01 = house_2 confirmed from data (daily ρ 0.52–0.74), MIC02 = house_1 confirmed 2026-10-08 by the mic ↔ IMU cross-correlation (`mic_imu_sync.py pilot`: in-house rats couple 44 / 46, rats elsewhere 1 / 37; mic file-name timing good to ~20 ms; a rat deviating from its house's lag flags a logger PC-time error; plan `implementation_plan/2026-10-08-mic-imu-sync.md`). USV: DeepSqueak's R1 rat networks via `ephys/usv/ds_batch.m` (MATLAB R2021b, CPU; the 2025 networks need newer MATLAB). Pilot `mic_wake_pilot.py` (description only: per-day mic vs per-house IMU movement; sound / housemate / outdoor cues before wakes vs a 2-min-earlier chance reference; the 10-dB rule is not specific — needs the user's listening check) → `reports/…mic_wake_pilot_<c>.md`. Blind listening page for the user: `mic_listen_review.py --pilot-run <run>` → `$OUT_ROOT/2026c/mic_listen_review_<ts>/index.html` (answers → `ephys/configs/mic_listen_review_2026c/`) |
| NS | night sleep / wake with WISER (plan `implementation_plan/2026-10-09-night-sleep-wiser.md`) | `night_sleep_wiser.py run [--long-wake-min 30]` (`--selftest`): FINAL 1-s states + WISER house_1 / house_2 / field (confirmed rectangles + 14 in, nearest unmasked fix ± 5 s, else unknown) + head-IMU locomotion per second; main sleep onset = first sleep after the last long wake (≥ 30 min) of the night; naps; ripple rate / depth vs time since onset | `reports/…night_sleep_wiser_2026c.md` + `_nights/_hourly/_tau_profile/_naps/_clock_vs_tau` CSVs, rasters per animal + summary; per-second tables `$OUT_ROOT/2026c/night_sleep_wiser_<ts>/`. Result 10-09: main sleep onset ≈ 06:00 (43/45 in house_2); night NREM = naps (~69 min/night) with the highest ripple rate per NREM minute (6/6 > main-sleep start). `night_sleep_wiser.py naps`: strict naps (exploration ± 30 min, house / field by `hysteretic_visits` on V3 with cohort-3 re-centred houses, lid events excluded) → 115 naps, peak 22 h. `swr_rem_naps.py run`: the nap advantage survives depth (+10.9 /NREM min, 5/5; depth-matched 6/6); REM per NREM mirrors the ripple rate; ripples drop in the last minute before REM more than before WAKE (6/6, also with flags ignored) |
| RR | NREM ripples in the REM-entry model (plan `implementation_plan/2026-10-09-rem-ripple-model.md`, pre-registered with the owner of `sleep_model.py`; Amendments 1–2) | `rem_ripple_model.py run [--scorings final pass2med] [--workers 8]` → `checks` → `posthoc` → `followup` → `report --run <run> --checks <checks>` (`--selftest`; `--features-only` / `--smoke`); reuses Step B's B-full (P_tw600_k0) unchanged; ripple features per 10-s NREM step from earlier seconds only (ALL events = flags ignored, primary; KEPT; causal animal × probe-block normaliser); subsets with a ripple-covered past; holds = CI < 0 and ≥ n − 1 animals on both scorings | `reports/…rem_ripple_model_2026c.md` + `_comparisons_2026c.csv`, figure, pointer `run_manifest_rem_ripple_model_2026c.json`; runs `$OUT_ROOT/2026c/rem_ripple_model_<ts>/`, `rem_ripple_checks_<ts>/`; input cache `$OUT_ROOT/2026c/rem_ripple_inputs/swr_events_and_slope.pkl`. Result 10-09 (after a read-only Fable audit, Amendment 3): no REM-timing information from ripples beyond the counter, clock and wake history (no gain > ~0.05 % from a 10-min window, none from ripples older than the last minute); the ripple counter's −0.3 % gain comes from the first 1–2 min of NREM bouts — 40 % of REM entries come from NREM bouts ≤ 60 s that are ripple-poor (21–24 vs 48–51 /min before WAKE), often inside REM episodes, not separable from the scorer's REM cuts (shared LFP); depth control inconclusive. `followup` = Amendment 3 |
| SB | short NREM bouts that end in REM (plan `implementation_plan/2026-10-09-short-rem-bouts.md`) | `short_rem_bouts.py features [--scorings final pass2med] [--workers 8]` → `review --run <run>` → `report --run <run>` (`--selftest`) | label-free LFP features per second (CA1 θ, θ/δ; cortical δ, σ; all SWRs; fast LFP-EMG) of R60 / W60 bouts vs N / R / T references, LDA pREM per animal × block → `reports/…short_rem_bouts_2026c.md` + `_summary`, figure, pointer; run `$OUT_ROOT/2026c/short_rem_bouts_<ts>/` with the blind reading page `review/index.html` (key `review_key_SEALED.csv`; answers → `ephys/configs/short_bout_review_2026c/`). Part A 10-09: short NREM bouts between REM bouts are REM-like (pREM 0.58–0.90 vs REM 0.95–0.99; 6/6, both scorings), as ripple-poor as REM; Part B (human reading) pending |
| 2 | stage | `stage_session.py --animal SF10 --session <s> [--window-s S D]` | `<ar>/stage/<SFxx>/<s>/`: clean `amplifier.dat`, sidecars, `<s>.xml`, manifest |
| 3 | sort | `run_sort_session.py --animal … --session … --partition shank` (`preprocess` env) | `<ar>/sort/<SFxx>/<s>/` (KS4 per shank, `_spi` postprocessed); row in `reports/…sort_runs_<c>.csv` |
| 4 | yield / curate | `unit_yield_report.py`; `open_phy.py --list` / `--animal --session --shank k [--raw]` | `reports/…ks4_unit_yield_*`; Phy edits in `_spi` |

Core library: `_common.py` (`ephys_block`, `raw_ephys_root`, `analysis_root`/`stage_root`/`sort_root`/`tools_root`/
`index_root`, `report_dir`/`figure_dir`, `iter_raw_sessions` — skips foreign-MAC cards, `git_commit`, `write_json`),
`wild_ce_params.py` (header), `signal_probe.py` (glitch probe/regime), `deglitch_wild.py` (vendored field de-glitch),
`make_session_xml.py`, `resort_shanks.py`, `backup_manifest.py` (SHA-256 tree compare). Everything else is a one-off
**check**: channel map (`probe_group_check`, `probe_map_check`, `footprint_map_check`, `lfp_profile_check` [`--raw <dir> --offset-min M --minutes N [--no-deglitch] [--derive-xml OUT] --save-profile OUT.npz`: keep the profiles; **NREM bout mode** (user 2026-10-05, preferred over the IMU gate) `--lfp <ar>/lfp/<SFxx>/<s>.lfp --states <…>/complex_system/<s>.SleepState.states.mat [--range-min A B]` = only trimmed NREM bouts of the session LFP, theta from REM bouts; user reference windows per animal in `configs/lfp_reference_windows_2026c.yaml`; `swr_gradient_order.py --profiles *.npz --orders NAME=xml …` scores/derives orders by the SWR gradient — amplitude and width rising along the shank, no polarity reversal needed (user rule; absolute amplitude, valid only without a reversal); **`swr_layer_order.py --profiles <day1>.npz <day2>.npz … --orders REF=xml [--exclude COL] [--shanks …] --xml-out`** = the current method (2026-10-06): exact shortest-path seriation in (SPW, signed ripple, theta phase, log theta power) space with the ripple kept unimodal, contrast-weighted multi-day consensus, literature-based orientation; validated blind on the user's correct-order templates HYC3 day26 (4×16 linear, `G:\3rd_rat_spikes\analysis\inspect\template_HYC3_day26\`) and WT2 day10 probe 3 (SF09's 5-shank "middle finger" 12/12/16/12/12 probe, `…\template_WT2_day10_5x12\`; source on `Q:\shared` is someone else's data, read-only)],
`wiring_pattern_check`, `bridged_pins_check`, `make_probe_xml` → `configs/xml/`), FM64 residue
(`template_width_check`: reject units with neighbour/peak ratio < 0.4), raw corruption (`integrity_scan`), HPC vs
cortex (`hpc_signature_check`, `swr_strict_check`), probe advance (`probe_move_check`, `probe_move_timeseries`), SF12 shank-1 integrity (`sf12_shank1_check`) — the
last four hard-code 2026c windows. Configs: `configs/probes_2026c.yaml` (per-animal maps, `verified:` flags),
`configs/kilosort4_wild.yaml`; `patches/*.patch` are upstream proposals only — the fixes are applied at runtime (a
`run_sorter` shim + a patched Kilosort4 copy in `<ar>/tools/Kilosort4_field2026`).

`cohorts/2026c.yaml ephys:` keys the code reads: `loggers.<SF>.mac` (foreign-card filter), `clean_firmware_min` (65),
`deglitch.{k_mad,floor_adc}`, `field_pc_clock_steps`, `field_flags` (excluded from coverage; `pc_time: false` = not
fitted/chained), `valid_until` (clips coverage), `pc_time_accept`, `adc_lane.on_windows`, `probe_config`,
`preprocess_pipeline_root`, `analysis_root`, `imu_valid_until` (make_imu), `quality_flags` (record-quality periods, e.g. `SF12_contact_failing` from 09-10 14:53:45; `sleep_review.py --merge` tags overlapping sessions — a tag never excludes). Informational only (no code reads them): `probe_moves`, `probe_notes`,
`logger_notes`, `field_pc_outages`, `implant_lost`, `last_valid_ephys`.

Gotchas: never write into a raw session folder (only `quarantine_adc_sessions --move` moves whole folders). Firmware
< FM65 is de-glitched, FM65 copied verbatim; FM62 wide-impulse/broadband regimes are unfixable. Raw folders are `SF8`,
stage/sort/config use `SF08`. XMLs use exported-column numbering — never also apply `vendor/correct_intan_dat_channel_order.py`;
only make shank/depth claims for animals with `verified: true`. Staged copies have no `analogin.dat`; PC time comes
from raw `analogin.dat` lanes 14/15 (undo mod-2^20 packing and the 86,400,000 ms day wrap; clock steps are added back).
Never merge units across a probe move (nothing enforces it). Fast postprocess leaves no `pc_features` — use
`open_phy --raw` or `--post-full`. `sort_manifest.probe_verified` is always false (reads a key the YAML lacks).

### `cv/` shelter pipeline — CH05/CH06 (RLC-520A, looking down through IR glass) → `cv_shelter`

Output is a shelter state per time bin: `empty` / `occupied_low_motion` (rest proxy) / `occupied_high_motion` /
`indeterminate` — not tracking, not sleep. Run from `cv/`:
calibrate once (`extract_clip.py --channel CH05 --frame` → `calibration.py --pick` → `configs/CH05_calib.json`;
optional `place_zones.py`) → harvest (`scan_for_rats.py --channel CH05 --date D --hours 19 20`) → label
(`label_frames.py`, rules in `cv/LABELING_PROTOCOL.md`) → train (`train_detector.py`, yolo11s, 1280, split by whole
video → `runs/detect/rat_feasibility[-N]`) → run (`shelter_sleep.py --date 2026-06-30 [--hours 3 4 5]` →
`cv/outputs/<CH>_sleep_<date>.csv` + PNGs + `.measurement_context.json`) → validate (`run_validate.ps1 --date D --n 60`).
It writes `cv/outputs/`, not `output_paths`; the canonical `results/2026a/cv_shelter/reports/` were written by hand.
Decision logic lives only in `view_quality.py` (+ `configs/view_quality.yaml`); `glass_regime.py`,
`measurement_context.py`, `fog_risk.py`, `stripe_flow.py` annotate/diagnose and must never feed a decision. External
inputs: `data_manifests/field_conditions.yaml` (forces a bin to ≥ degraded) and `glass_treatments.yaml`. A degraded
bin never becomes `occupied_high_motion`. CH05/CH06 calib is a 4-point homography (RMSE 0.0 is an exact fit, not
accuracy). Default weights `runs/detect/rat_feasibility-6` and `dataset/rat` are not on this PC.

### `cv/cv_field/` — whole-field night-IR detector, CH03/CH04 (RLC-1212A), 21:00→04:20 → `cv_field`

Start from `cv/cv_field/HANDOFF.md` (status + where everything lives). Production candidate = **`rat_field_div3`
(YOLO11, 1280) + DINOv3 gate (`cv_field/dino_gate.npz`) + valid-field masks (`cv/configs/CH0{3,4}_field_mask.json`)**:
recall ≈ 0.65, true precision ≈ 0.9 on the frozen 07-06 night; fallback `div1`. Active-learning round: harvest
(`scan_for_rats.py --channel CH03 --src <mp4s> --no-detector …`) → motion sidecar (`cv_field/enrich_motion.py`) →
select (`select_frames.py --round N --use-motion --embed-backend dino …`; bulk → `$OUT_ROOT/<c>/cv_field_select_<ts>/`,
report → `results/<c>/cv_field/`) → label (`label_frames.py --dir dataset/rat_field/images --proposals …`) → train
(`train_detector.py --data-root dataset/rat_field --name rat_field_divN …`) → gate fit (`dino_gate.py --fit`) → eval
(`stratify_test.py --eval`) → audit (`field_audit.py`). Inference: `run_field.py --cohort 2026a --channels CH03 CH04
--weights …` → `$OUT_ROOT/<c>/cv_field_tracks_<ts>/` — **it applies neither the mask nor the gate**.
Library: `field_mask`, `field_motion`, `field_embed`, `field_cluster`, `acquire`, `stratify_test`, `dino_gate`; GUI
`mask_field.py`. **Rejected, keep for the record only:** native tiling (`tile_dataset.py`, `tile_infer.py`,
`eval_frozen.py`), runs `rat_field_tiles`, `rat_field_div2`. Local-only, gitignored: `cv/dataset/` (labels are
irreplaceable human work), `cv/runs/detect/*/weights/`, `cv/scratch/`, `cv/outputs/`. DINOv3 checkpoint:
`~/.cache/torch/hub/checkpoints/dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth` or `$DINOV3_WEIGHTS` (else DINOv2).
Rules: motion boxes are proposals, never labels; the frozen test night is never used to train, fit the gate or tune;
evaluate by center-matching and review "false positives" by eye (test GT is incomplete → recall is a lower bound);
label only clearly visible rats (Long Evans hoods read darker than grass → `polarity="dark"`). `label_frames`,
`scan_for_rats`, `train_detector` default to the **shelter** dataset `dataset/rat` — pass `dataset/rat_field`.
CH01/CH02 daytime colour was corrupt in **cohort 1** (keyframe truncation fixed 07-11, VBR cap 07-19 — before cohort 3).

**Cohort 3 (2026c), user decisions 2026-09-28:** start with the **CH01/CH02 panoramas** — they map ~68–69 % of the
paddock each in the 09-24 calibration (CH03/CH04 ~12 % each, the two ends) and so carry the occupancy map; this repo's
detector and its 255 labels are cohort-1 CH03/CH04; cohort-1 CH01/CH02 labels + a CH01/CH02 YOLO exist only in the
`social-field-rat` backup (next paragraph); cohort-3 CH01/CH02 have zero labels. A rat is ~70–160 px in the
native upright pano (7680×2160) → never the 1280 default (11–16 px); compare whole pano @2560 vs half @1920 after
labelling. **Workflow:** local first — frames from the local copy `F:\3rd_rat\` with `cv/cv_field/grab_frames.py`
(`--targets camera,time[,tag] --out <dir>`; exact CPU decode ≈ 0.9 s/frame — the benchmark showed decode is not the
bottleneck and NVDEC gives no single-frame gain, so `--decode gpu` is for whole-night inference), times chosen by
`select_pano_targets.py` (tagged animals outside the houses per 5-s WISER bin → stratified night targets, a held-out
test night), frames stored locally (`cv/dataset/rat_pano*`), labelled locally, small pilot; only then large batches on
BioHPC (`cv/cv_field/REMOTE_COMPUTE.md`). Plan: `implementation_plan/2026-09-28-cohort3-ch0102-yolo-pilot.md`. **Camera stability is judged by a person**:
`cv/cv_field/camera_review.py` lays out daily frames with the 09-18 wall-foot lines for review (an automatic ECC check
failed — grass, rain, IR/colour changes); weather-driven moves are reported manually. **The agent does not judge
images** and confirms every test plan with the user first. **Houses (user, checked on CH05/CH06, 2026-10-01):**
house_1 = `HOUSE_1` = roof number **4** (by pole B1, under CH05) was **moved on 09-18** (calibration day, farther from
its pole); house_2 = `HOUSE_2` = roof number **7** (by pole B3, under CH06) never moved; neither moved while the rats were
in the field. So house_1's position from 09-18 imagery or the calibration (e.g. `field_layout.json` shelter "left")
does not hold for cohort 3, and the CH01/CH02 difference vs the calibration is most likely this move, not distortion
(to be confirmed with rigid landmarks — `cv/configs/landmarks/2026c/README.md`).
**Rigid-landmark correction (cohort px → 09-18 calibration-epoch px):** the user labels rigid structures on the 09-18
reference frames with `landmark_gui.py CHxx "<time>" --cohort 2026c [--guide …]` (poles L/R edges, pole boxes = WISER
anchors, wall tops, towers, PC box, houses for validation; CH03/CH04 also `NAILS`, `PATCHES`, `SEAMS`, CH04 `BUILDING`,
`WOOD`) → exports in `cv/configs/landmarks/2026c/` (also cohort frames, e.g. CH04 09-04 12:00 / 03:01).
`landmark_track.py --cohort 2026c [--times 12:00]` tracks them into daily frames (coarse-to-fine NCC on gradient
magnitude, Gaussian sub-pixel peaks, Huber affine with a weak identity prior; stable tier first, occludable pieces gated;
patches matched as whole masked blocks; leave-one-out held-out error) → `$OUT_ROOT/2026c/cv_field_landmark_track_<ts>/` +
`results/2026c/cv_field/reports/cv_field_landmark_track_2026c.md`. `--ref-labels <cohort-frame labels> --tie --tag <name>`
tracks from a user-labelled cohort frame and ties it to 09-18 from the two label sets (`tie_labels`, no image matching)
→ `…_track_2026c_<tag>.md` + `run_manifest_landmark_track_<tag>_2026c.json`. Night frames need a night reference:
`landmark_night.py --cohort 2026c --nights <dusk dates…> --cameras CH01 CH02` chains through dusk (direct from 09-18 while
ok, then from an anchor frame) and checks by dawn closure → `cv_field_landmark_night_<ts>/` + `cv_field_landmark_night_2026c.md`
(own pointer `run_manifest_landmark_night_2026c.json`; pass = median of the first three dawn closure frames ≤ 3 px, user
2026-10-02; `--report-only <run>` re-judges). Both have `--selftest`; plan revision 3 in
`implementation_plan/2026-09-28-cohort3-camera-stability.md`.
**Use the correction, not the raw pixel, for any CH01–CH04 position:** `frame_correction.py build --cohort 2026c` assembles
`results/2026c/cv_field/reports/cv_field_frame_corrections_2026c.csv` (per camera and sampled night time, hourly
21:00→04:20; CH01/CH02 from the night chain, CH03/CH04 from the user's 09-04 03:01 labels tied to 09-18) and
`Corrections("2026c").to_paddock(cam, t, uv_upright, z_mm=60)` maps a detection pixel at field-PC time `t` to paddock
inches (cohort px → 09-18 px → 09-24 calibration); check the returned `info["flag"]`. Coverage (user, 2026-10-02):
CH01–CH06 nights hourly; the in-box CH07/CH08 all day, segmented at the house-lid events (`cv/configs/cohort3_lid_events.json`,
battery rounds / catches) with one median correction per lid-closed segment (outliers > 10 px flagged). CH05 (house_1
moved 09-18) and CH07/CH08 (uncalibrated) map to user-labelled 09-04 frames, not 09-18 — use `to_09_18` for their
reference-frame pixels; `to_paddock` refuses them. Precision: CH01/CH02 ≤ 3 px on passing nights, CH03/CH04 ~5–10 px,
CH05/CH06 held-out ~0.5–1.8 px, CH07/CH08 in-segment spread ~3 / ~1 px. **The table is night-only for CH01–CH06**: at a
daytime time it returns the nearest night sample (09-04 12:00 on CH02: 30 px off) — track daytime frames directly with
`landmark_track.py --times HH:MM --start D --end D --tag …`. Summary for detector/tracking work (camera motion, house_1,
landmark names, occluder regions): **`cv/cv_field/CAMERA_GEOMETRY_2026c.md`**.
**Cohort-1 CH01/CH02 pano detector (`social-field-rat`, another lab member's folder, broken `.git`, 2026-10-05):** the
project's only CH01/CH02 labels — 887 cohort-1 frames / 1 692 boxes (CH01 06-30, 07-04, 07-07; CH02 06-30, 07-06; all
21:00–22:00; upright 7680 × 2160 YOLO txt; `labeled_yolo/` 710 train / 177 val) + two partly labelled, never-trained clips
(`frames_0704_CH02_selective` 60, `frames_0705_CH01_selective` 33) — and YOLO11 v1–v5 (`outputs/runs/rat_m_v5/weights/
best.pt` = yolo11m @1280, the author's best). **Read the verified backup, never the source:**
`D:/Field2026_analysis_out/2026a/social_field_rat_backup_20261005/` (5 469 files, 51.35 GB; `MANIFEST_sha256.csv`,
`README.md`, `VERIFY.json`; `backup_social_field_rat.py --verify-only`). `sam3_vs_yolo_c1.py` (SAM3 text-prompt zero-shot
vs v5 on those labels → `results/2026a/cv_field/reports/cv_field_sam3_vs_yolo_c1_2026a.md`): v5 AP 0.83 (S-val) / 0.47
(held-out CH01 07-05) vs SAM3 "rat" 0.23 / 0.02 — SAM3 is no detector here; the CH02 07-04 labels are v5's own boxes
(circular) and most labelled frames are numerically IR. `c1_yolo_video_test.py` (v5 on every frame of cohort-3 CH01
09-06 21:00–22:00 via in-process PyAV, ~42 fps; WISER outside-count per 5-s bin; `review_10min.mp4` + rule-chosen 60-s
review clips with `index.html` → `$OUT_ROOT/2026c/cv_field_c1yolo_video_<ts>/`, report
`results/2026c/cv_field/reports/cv_field_c1yolo_video_2026c.md`): count ρ 0.10 vs WISER (plausibility only, awaiting the
user's review; the user saw many fixed-position false positives / negatives → `c1_yolo_fixed_spots.py --run <run>` maps them from the cached detections into `<run>/fixed_spots/index.html` for the user's verdicts). Reolink PTS come in bursts (frames < 1 ms apart) — join frames by PTS at 1 µs, and seek a frame with
`grab_frames.grab` at the midpoint to the previous PTS. Plan `implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md`.
**Review GUI:** `c1yolo_review_gui.py --build` → `$OUT_ROOT/2026c/cv_field_c1yolo_review_gui_<ts>/index.html` (click verdicts: Step 1
the fixed spots, Step 2 — locked until Step 1 is saved — the phase-0 suspected-miss clips; Export CSV + JSON → `cv/configs/c1yolo_review_2026c/`).
**WISER-assisted YOLO phase 0** (`wiser_assist_p0.py --run`, plan `2026-10-05-wiser-assisted-yolo-p0.md`, 2026-10-05): on that
CH01 hour, WISER default tracks → paddock = similarity d (−272.85, −605.80) in, θ 0.11°, s 0.963, L 0.0 s, chosen on fit
blocks only; test median 4.39 in, 88.5 % of boxes with an animal ≤ 14 in vs 2.9 % (+1 h control) → **accepted** (one hour,
CH01 only). → `$OUT_ROOT/2026c/cv_field_wiser_assist_p0_<ts>/` (`mapping.json`, `fn_episodes.csv` = suspected YOLO misses,
never boxes; `wiser_spots.csv` = WISER presence at the fixed spots, **sealed until the user's spot verdicts**), report
`results/2026c/cv_field/reports/cv_field_wiser_assist_p0_2026c.md`. WISER only adds presence, never a negative.
`--clips <run>` (cv env, PyAV) renders 12 rule-chosen review clips of the suspected misses (pano + crop + panel, WISER
14-in circles via a Newton inverse of `to_paddock`) → `<run>/review_clips/index.html` + empty `review_template.csv`;
`--episode-clips <run>` renders one clip per episode that follows THAT animal (`<run>/review_clips_per_episode/`, 58) — the review GUI plays these.
**CH01 occlusion geometry** (`ch01_occlusion.py --run`, plan `2026-10-06-ch01-occlusion-geometry.md`): rays from CH01's rev g
centre to each suspected-miss rat; v2: CH01-labelled poles hide by CH01's own edge planes, other poles capsules, gabled
houses (house_2 calibration pose; house_1 at its fitted cohort pose `cv/configs/house1_cohort_pose_2026c.json`, made by
`--house1-fit` = house_check on the CH01 + CH02 09-04 noon labels), 7-in perturbations clamped → pooled 5.0 % hidden / 5.0 %
partly / 50.7 % clear / 39.3 % ambiguous of 300 episodes; `$OUT_ROOT/2026c/cv_field_ch01_occlusion_<ts>/` (`visibility_mask.npz`, `occluders.json`,
`checks.csv`; per-episode classes **sealed** in `episodes.csv` until the user's clip verdicts), report
`results/2026c/cv_field/reports/cv_field_ch01_occlusion_2026c.md`. Geometry never makes a label. `build_scene(cam=…)`
also builds the same scene seen from CH02 (its own 09-18 L/R labels of A0, A4, B0–B4).
**WISER-guided labelling loop, round 1** (plan `2026-10-06-wiser-label-loop.md`; parts A + B here, part C = the loop code in
the undergrad's repo clone `D:/Documents/GitHub/social-field-rat-wiser-loop/`, branch `wiser-loop`, reads only the kit and
the videos): `select_label_round1.py --pool` (cv env) → `$OUT_ROOT/2026c/label_round1_pool_<ts>/` (per camera 1 500 night
times, WISER-stratified + uniform, ≥ 10 s apart, test night 09-05 excluded; PNG via the grab_frames command + v5 conf ≥ 0.05 +
DINOv3 1024 × 288 CLS; frame index from the fMP4 sample table; resumable, never re-grabbed) → `build_wiser_pixel_kit.py
--build --pool <pool>` → **WISER pixel kit** `$OUT_ROOT/2026c/wiser_pixel_kit_<ts>/` (per camera and night 08-30…09-10 except
09-05: 1-Hz `t_pc, animal, tracked, in_house, u, v, r_px, hidden_share, in_support, motion, all_tracked, map_validated`;
`support.json`, `occluders.json` by night, `visibility_mask.npz`; map validated per camera-night from the pool's v5 boxes:
19 / 22 pass, not CH01/CH02 09-01 and CH02 09-02) → `select_label_round1.py --select --pool <pool> --kit <kit>` →
**label package** `$OUT_ROOT/2026c/label_round1_<ts>/` (400 train frames with editable v5 txt only where v5 has a box,
`prelabels_v5/`, WISER sidecars `wiser_sidecar/1`; test 100 on 09-05 — never a model, prelabel or sidecar; 20 overlap frames;
`MANIFEST_sha256.csv` + `verify_manifest.py`) + report `results/2026c/cv_field/reports/cv_field_wiser_label_loop_round1_2026c.md`.

### `thermal/` — cams `108_thermal` / `109_thermal` (1 fps, 1280×960 HEVC, white-hot, auto-gain); no results direction

Phase-0, candidate-only: `detect_blobs.py --cam 108_thermal --date D --hour 21 --out <dir> [--preview]` →
`detections.csv`, `tracks.csv`, `summary.json`; label/score with `make_label_set.py` → `label_tool.html` →
`score_labels.py`; `train_filter.py` (sklearn); heat-ghost traces `trace_feasibility.py` (GO on 108, NO-GO on 109) →
`detect_traces.py` (108 only). Output only to `--out`; raw via `--base` (default an old `Q:/hc997/SocialFieldRat2026/…`
path). Never threshold absolute gray (per-frame AGC), not temperature, not identity, counts are a lower bound; never
parse the OSD clock. See `thermal/README.md`.

### `wiser/` — UWB tag tracking (inches) → `wiser_baseline`, `wiser_d1_nightly`, `wiser_d2_routes`, `wiser_d3_sleep`, `wiser_policy`

Inputs: snapshot SQLite via `common/wiser_inputs.py` — `--db` wins; default **latest** `1stcohort_2026_*.sqlite`
(cumulative superset); `--canonical` = cohort-pinned `1stcohort_2026_2026-07-12.sqlite` + sha256 in
`wiser_input_provenance.json`. Snapshot dir = first existing of `raw_data_roots.{analysis_pc, biohpc, field_pc}`
(local `D:/Reolink_record/audio_in/Wiser_backup/snapshots` before the `Q:` master). D2/policy drivers read incremental
`*.csv.gz` from a hard-coded `D:\Reolink_record\audio_in\Wiser_backup\incremental`. Some drivers default to the live DB
`D:\Wiser\data\1stcohort_2026.sqlite` (absent here). Command form:
`python wiser/scripts/<driver>.py [--canonical] [--db P] [--output ROOT]` (D2/policy: `--incremental-dir --nights
--out --fast`). Outputs mostly bypass `results/`: bulk → `<OUT_ROOT>/<name>_<ts>` (no cohort folder) and chained
CSVs → gitignored `wiser/outputs/`; `results/2026a/wiser_*` hold migrated copies.

| Direction | Canonical drivers (`wiser/scripts/`) | Self-tests |
|---|---|---|
| `wiser_baseline` | `analyze_fixed_position_test`, `plot_hourly_occupancy`; `analyze_imu_wiser_calibration --cohort 2026c` (head IMU vs WISER: lag, IMU-selected jitter/speed floor, handedness, `rest_mask` agreement; inputs `configs/imu_wiser_calibration_<c>.json`; its report pointer is `run_manifest_imu_calibration_pilot_<c>.json` so the accuracy report's `run_manifest.json` survives); `analyze_wiser_imu_smoothing --cohort 2026c` (held-out-fix test of smoothers: library median-7 vs robust per-anchor CV Kalman/RTS ± drift vs + head-IMU ZUPT / IMU-switched process noise, +1 h-IMU controls; tune 09-08/09, test 09-10/11; config `configs/wiser_imu_smoothing_<c>.json` incl. the fitted `tuned` block; numba if installed; pointer `run_manifest_imu_smoothing_pilot_<c>.json`); `build_imu_wiser_cache --cohort 2026c` (Phase A caches, read raw E: once: A1 raw IMU lanes 1–6 at 1250 Hz per animal-night 20:50→05:30 `<OUT>/2026c/imu_raw_cache/<SFxx>/<session>__<start>_<end>.npz` + index, A2 deduplicated WISER fixes + masks `<OUT>/2026c/wiser_fix_cache/night_<date>/<SFxx>.csv.gz`) → `analyze_wiser_ins_fusion --cohort 2026c` (V4: IMU quality + smoothing → A3 100-Hz calibrated head-frame IMU `<OUT>/2026c/imu100_cache/<SFxx>/night_<date>.npz`; 6-axis ESKF + RTS of head IMU + WISER, yaw hypotheses, mirrored-frame handedness LLR, +1 h control; config `configs/wiser_ins_fusion_<c>.json` incl. `tuned`; pointer `run_manifest_ins_fusion_<c>.json`; start later IMU work from the A1/A3 caches, not raw); `analyze_imu_attitude_phase0 --cohort 2026c` (Phase 0 of the head-IMU attitude, IMU only: floor, per-animal gyro matrix chosen by tuning-night CV, saturation classes + held-reading reconstruction, 100-Hz attitude with quiet-only gravity aiding → **A4 16-Hz cache** `<OUT>/2026c/imu16_cache/<SFxx>/night_<date>.npz` + README (world-frame f_xy at 2/1/4 Hz, quaternion, σ_θ(t_active), flags, band powers), growth law, pre-registered gate → **FAIL** 09-30; config `configs/imu_attitude_phase0_<c>.json` incl. `fitted`; pointer `run_manifest_imu_attitude_phase0_<c>.json`; facts: IMU lanes are sample-and-hold ≈ 190 Hz, 80 % of gyro clipping is 12–20 Hz shake trains, the audit's gravity-window test is limited by motion inside its own edge windows); `analyze_imu_attitude_gate_v2 --cohort 2026c` (gate re-test with strict accelerometer-led still windows — every 0.1-s acc direction < 0.3° from the window mean over ≥ 1 s, WISER veto > 6 in — and window-centre → centre propagation, nights + day sleep; `--build-day-caches` wrote the **day caches** in the same roots/formats: A1 `imu_raw_cache/<SFxx>/<session>__<start>_<end>.npz` + `index_day_2026c.csv`, A3-equivalent `imu100_cache/<SFxx>/day_20260908.npz` / `day_20260911.npz`, A2 `wiser_fix_cache/day_<date>/<SFxx>.csv.gz` + `index_day_2026c.csv`, README per root; → **PASS** 10-01 on gentle bouts, drift linear in clock time ≈ 2 °/min (bias-like); config `configs/imu_attitude_gate_v2_<c>.json` incl. `fitted`; pointer `run_manifest_imu_attitude_gate_v2_<c>.json`); `make_imu_video_review --cohort 2026c` (video-review GUI of head-IMU events, for the USER to judge: one clip per gate-v2 `human_checks.csv` event, event ± 5 s from `F:\3rd_rat` by file-name time, cameras from the WISER zone (house_1 → CH08 + CH05, house_2 → CH07 + CH06, else CH01 + CH02 panoramas), ASS overlay with the IMU state every 0.25 s (SHAKE / STILL / QUIET / LOCOMOTION / RHYTHMIC 4–12 Hz / ACTIVE) → `<OUT>/2026c/imu_video_review_<ts>/` (`clips/`, `index.html` review page, `events.json`); exported human labels → `configs/imu_video_review_<c>/`); `analyze_wiser_ins_fusion_v5 --cohort 2026c` (V5 head-IMU/WISER fusion from the caches only: Stage A, IMU-only attitude — gate-v2 strict windows without the WISER veto, gate-v2 gyro scales, bias piecewise-linear in clock time through ML-smoothed ZARU anchors at every strict window, gravity aiding only at window centres — → reusable **`<OUT>/2026c/attitude16_cache/<SFxx>/<period>.npz`** (16-Hz world-frame f_xy at 2 Hz, quaternion, time since a strict window, σθ laws, flags, band powers) + `<period>_windows.csv.gz` + day `<period>_imu_seconds.csv.gz` + README; Stage B 16-Hz EKF + RTS (p, v, world acc bias, yaw offset ψ, measured WISER noise/drift, ZUPTs, V2-like CV fallback), tuned on 09-08 night + day, schemes (s)/(g)/(a)/(a′) vs B2′/V2 + 1-h control → **FAIL** 10-01 (night unanchored, yaw unobservable; f_xy is usable only within ~1 min of a strict window); config `configs/wiser_ins_fusion_v5_<c>.json` incl. `tuned`/`fitted`; pointer `run_manifest_ins_fusion_v5_<c>.json`); `analyze_wiser_failure_audit --cohort 2026c` (WISER failure audit with the head IMU as the stillness truth — certified still segments = gate-v2 strict windows where the 100-Hz caches exist, else S50 = the same rule on the accelerometer rebuilt from the make_imu quaternion + earth acceleration, ellipsoid self-calibrated; jitter / 10-s & 60-s drift / crazy drift / jumps / fake speed & path during stillness, raw → B1 → B2 → B2′ (V1/V2 circular), night motion-side failures, rain vs calm block bootstrap with anchors × zone standardisation; extracted the WISER fix caches `wiser_fix_cache/night_20260903/05/06/07/09`, `day_20260905/07/10` + `index_failure_audit_2026c.csv`; `--report-only <run_dir>` re-scores from the saved tables; config `configs/wiser_failure_audit_<c>.json`; pointer `run_manifest_failure_audit_<c>.json`; result 10-02: WISER jitters and jumps but rarely drifts far from a still rat, B2′ removes jumps and most jitter but not drift, rain confirmed largely via fewer anchors; score any V6 against its certified-still segments, not held-out fixes); `analyze_wiser_default_smoother --cohort 2026c` (chooses the **default WISER smoother** by a pre-registered rule from the failure audit's saved run — candidates B1, B2, B2′, V1, V2, V2b = V2's IMU-switched q on the B2 base, IMU methods falling back to B2 where the IMU QC fails; still metrics on the certified segments, safety S1 held-out moving fixes vs B2, S2 1-s speed p50/p95 within ± 10 % of B2, S3 rain ≥ 12-in excursions ≤ raw, S4 zero jumps, S5 lags; `--report-only <run_dir>`; config `configs/wiser_default_smoother_<c>.json` with the result in its `decision` block; pointer `run_manifest_default_smoother_<c>.json`; result 10-02: **default = B2** (no-survivor fallback; B2 fails only S3 by one event, sole survivor if S3 is read by its CI; every IMU method fails S2) — B2 (`tuned.B2` of `configs/wiser_imu_smoothing_<c>.json`) stays the universal baseline; **superseded 10-03 for the implanted animals by V1b**, next); `analyze_wiser_v1b --cohort 2026c` (step A after the Fable SOTA audit: **V1b = one B2 filter + a Huber zero-velocity pseudo-measurement (σ 1 in/s) in IMU-still runs ≥ 3 s eroded by 1 s, released for the rest of a run after > 5 s of ≥ 12-in raw-WISER displacement; no drift state, no q switching, no splice — where the IMU QC fails it is B2 in the same filter**; acceptance = V1b's own claim, not superiority over B2: E1 identical to B2 in motion, E2 onset/offset median Δ ± 0.5 s, E3 zero jumps; reported: circular still metrics, ZUPT coverage, releases, false-still probe, S1, S3, NIS by anchors × zone × IMU state; sensitivities V1b-noRelease, V1b-raw (σ 0.25, no guards); config `configs/wiser_v1b_<c>.json` (verdict in `decision`); pointer `run_manifest_v1b_<c>.json`; result 10-03: **PASS → default for the implanted animals = V1b (B2 elsewhere), superseded the same day by V3 (below)** — E1a p99 0.02 in, E1b ≤ 2.4 %, E2 medians 0.00 s (but 16–29 % of events shift: onsets later, offsets earlier), 0 jumps; still fake path 38.9 | 50.8 → 12.8 | 20.0 in/min (circular; σ 1 in/s is soft); 108 of 155 releases fell inside certified stillness (a cost); NIS under B2 ≈ 2.4–2.6 still but 8–10 locomoting → the CV q is stiff in runs; the same step fixed the failure audit's per-group speed quantiles (`--report-only` regenerated: rain fake-speed p95 by set × kind 11.1/14.1 → 19.9/17.8 in/s)); `analyze_imu_speed_proxy --cohort 2026c` (step B: smoother-independent speed — clean-WISER 3-s / 1-s speed from medians of raw fixes (all fixes ≥ 8 anchors, open field, no jumps, ≥ 3 Hz) with its noise floor from certified stillness (u3 p50 0.59, u1 1.90 in/s); per-second head-IMU features cached once in **`<OUT>/2026c/imu_speed_features/<SFxx>/<period>.csv.gz`** + README; M1 per-animal OLS vs M2 pooled gradient boosting (train 09-05/06, tune 09-07, test 09-08, rain 09-03/09); R1 re-scores every track's speed against clean WISER, R2 against the proxy only if valid; config `configs/imu_speed_proxy_<c>.json` (`fitted`, `result`); pointer `run_manifest_imu_speed_proxy_<c>.json`; result 10-03: **IMU proxy not valid** (3 s MdARE 0.262 vs ≤ 0.25, ρ 0.82; 1 s 0.41) → no R2, no ephys speed file; **R1 at the 3-s p95 of the > 15 in/s band: B2 = V1b −8 %, B2′/V1 −18.5 %, V2 −4.3 %, V2b −1.4 %, B1 −0.7 % → B2/V1b under-follow fast bursts** (matches the NIS); negative p50s mostly mean removed noise (the reference p50 sits at its floor)); `analyze_wiser_v3 --cohort 2026c` (**V3 = one B2 filter + q × 10 only on IMU-locomoting steps + Huber ZUPT σ 0.25 in/s in IMU-still runs ≥ 3 s eroded by 1 s, no release, no splice; IMU-QC-failed = B2 in the same filter**; first test with a truth-referenced motion criterion: T1 3-s p95 speed within ± 3 % of step B's clean-WISER speed (all clean seconds and the > 15 in/s band), T2 zero jumps, T3 onset/offset median Δ ≤ + 0.5 s vs B2; reported: circular still metrics, in-place jitter, NIS by IMU state, S1, S3; sensitivities σ 0.5/1, × 3/× 30, loco-only; config `configs/wiser_v3_<c>.json` (verdict in `decision`); pointer `run_manifest_v3_<c>.json`; result 10-03: **PASS → V3 = default WISER track for the implanted animals (IMU-QC-ok stretches; B2 elsewhere), B2 = universal baseline** — T1 −2.1 % / −1.2 % (B2 −5.2 / −8.0), 0 jumps, T3 medians 0.00 s; still fake path 3.3 | 3.6 in/min (circular); NIS locomoting 10.1 → 7.1; rain ≥ 12-in excursions 4 (raw 6); **cost: on seconds the IMU calls locomoting but the rat barely translates, V3's 1-s speed is +62 % / +69 % above B2 → do not read V3 1-s speed/path during in-place activity as translation**); `analyze_wiser_v6_fusion --cohort 2026c` (V6 = short-horizon head-IMU / WISER fusion: EKF + extended RTS on a 16-Hz grid, state p, v, world-acceleration bias, heading offset ψ, input = make_imu Fusion-AHRS earth-frame acceleration low-passed at 2 Hz, B2 noise model + V3 ZUPT, V3/B2 dynamics where the IMU QC fails; tuned on 09-07 only; primary = floor-corrected gap-fill prediction RMS at hidden 0.5/1/2/3-s blocks vs V3, + T1–T4 and a +1 h-shifted negative control; writes the reusable cache **`<OUT>/2026c/imu_acc16_cache/<SFxx>/<period>.npz`** + README; config `configs/wiser_v6_fusion_<c>.json` (`tuned`, `decision`); pointer `run_manifest_v6_fusion_<c>.json`; result 10-03: **rule 2 — the inertial-position line is CLOSED, V3 stays**: V6 is worse than V3 at every horizon (calm test −5.6 % / −11.5 % / −25 % / −45 % at 0.5/1/2/3 s; every animal), worse than its own +1 h control, fails T3 (offsets +7 s) and T4 (in-place speed +148 %); tuned values at the loosest grid edge; ψ unobservable (60° RMS about its drift line) → no head-direction signal; post hoc: the IMU's 1-Hz horizontal acceleration in locomotion (≈ 29 in/s²) is ≈ 4× the track's (≈ 7 in/s²) and a best rotation explains R² 0.05 — head sweep + tilt leak, not body translation. **Do not build further acceleration-fusion variants for WISER position**); `analyze_imu_turn_vs_heading --cohort 2026c` (Phase 0 of turn-aided WISER: on step-B clean locomotion (≥ 10 in/s) the WISER raw-median heading change vs the integrated make_imu gyro turn (`turn_dps`, + = CCW seen from above) over W = 1/2/3 s; gate (calm, W = 2 s) |slope| 0.8–1.2 and R² ≥ 0.5; +1 h control; config `configs/imu_turn_vs_heading_<c>.json` (`decision`); pointer `run_manifest_imu_turn_vs_heading_<c>.json`; result 10-04: **FAIL → no turn-aided smoother (V7)** — slope +0.64, R² 0.20 (V3-track heading, post hoc: R² 0.49), residual median 20°, 35 % of pairs > 30° apart (head scanning); turn-sign agreement for clear head turns 83 %; the path turn lags the head turn by ≈ 0.2 s; the gyro sees ≈ 27 turns per IMU-ok hour that WISER misses (in place; field 36, house 19); handedness normal for all five animals (V6's "SF07 mirrored" not supported). Head turn stays a head-behaviour signal (`imu_seconds_cache/` head layer), not a body-path constraint); **`build_wiser_default_tracks --cohort 2026c [--method V3|B2] [--labels …] [--dates …]`** (production, 10-04: **the default WISER tracks for all of cohort 3 — start any 2026c WISER analysis here, read with `wiser/src/default_tracks.py` `load_default_track(label, date)` / `list_default_tracks()`**; V3 for the implanted animals, B2 where the IMU fails or is absent (08-30 evening); per field-PC calendar day ± 10-min margins, release → 09-12 10:10; labels SF07–SF12 by `configs/rat_identities_2026c.csv` validity windows + `SF12_tag12376` (SF12's second tag, 08-30/31); **the five females released 09-11 left no tag in WISER** (only the 7 known shortids exist); SF11 fixes after its implant came off (09-07 06:10:45 → 08:20) are flagged `m_off_animal`; three caches: **`<OUT>/2026c/wiser_fix_cache/full_<YYYYMMDD>/<label>.csv.gz`** (all four DB copies `3rdcohort_Spike_2026_3*.sqlite` joined, index `index_full_2026c.csv`), **`<OUT>/2026c/imu_seconds_cache/<SFxx>/<YYYYMMDD>.csv.gz`** (per-second IMU QC/state + head layer turn_net/abs, pitch, roll; reproduces the audit's states 100 %), **`<OUT>/2026c/wiser_default_tracks/<label>/<YYYYMMDD>.csv.gz`** (+ `index_2026c.csv`, README with the in-place-speed caveat); `--method B2` writes a separate folder; pointer `run_manifest_default_tracks_<c>.json`; reproduction: V3 run matched to 4.4e-5 in, fix caches identical to the 60 existing ones); `analyze_wiser_imu_consistency --cohort 2026c` (the user's "IMU as a lie detector for WISER" audit, 10-05, on the production tracks: I1 = ≥ 12-in displacement inside a ≥ 5-s run with no IMU-locomoting second (trimmed 2 s), I2 = path turn ≥ 90° in 2 s at ≥ 10 in/s while the gyro turns < 20°, I3 = the reverse; rates by day/night, house/field, rain/wet/dry; enrichment in ≤ 6-anchor fixes vs matched controls; `--report-only <run> --reuse`, `--install-flags <run>`; writes **`<OUT>/2026c/wiser_default_tracks_qc/<label>/<date>.csv.gz`** (per-fix `qc_i1`, `qc_i2` + event ids, keyed by `t_ms`; + README, index) and used B2 tracks from **`<OUT>/2026c/wiser_tracks_B2/`** (`build_wiser_default_tracks --method B2`); config `configs/wiser_imu_consistency_<c>.json` (`decision`); pointer `run_manifest_imu_consistency_<c>.json`; result: **not material → V3 unchanged, the QC flags are the deliverable** — V3 I1 4.24 per IMU-ok hour (night 6.8, field 7.4, rain 6.7; none in all-still runs), I2 0.10 (raw 21.9); low-anchor enrichment only 1.43× (I1; rule ≥ 2×), I2 not enriched → I1 events are largely real movement the loco detector misses or in-place drift of modest geometry; the 30 largest I1 / I2 events with `F:\3rd_rat` files are listed for the user's video check (report §5)); `analyze_wiser_i1_return --cohort 2026c [--render-only] [--with-verdicts <file|dir>]` (I1 "return test", 10-05: WISER's error is mean-reverting (user), so each V3 I1 event is classed by the raw-fix median before vs after — return < 6 in / relocate ≥ 12 in / ambiguous / censored; config `configs/wiser_i1_return_<c>.json` (`reading`, later `validation`); pointer `run_manifest_i1_return_<c>.json`; result: **reading NOT ESTABLISHED → V3 stays, no V8** — 69 % censored (by construction the I1 window runs to the run end for a held shift, so a held relocation can never be "relocate"; the run-end check gives 54 % relocate / 16 % return of the classifiable), return 28 % of the classifiable and the least low-anchor-enriched (1.28×); WISER alone cannot separate a slow relocation the IMU missed from an offset held until the next walk → **the user's video verdicts decide** (`--with-verdicts`, confusion table + κ)); `make_wiser_event_review --cohort 2026c` (blind video-review GUI of 80 audit events — 30 largest I1, 20 random I1 by size quartile, 30 largest I2 — shuffled as W01–W80; clips event ± 10 s (long I1 cut at 60 s) from `F:\3rd_rat` by file-name time on the audit's aligned clock, cameras by the pre-event zone (house_1 CH08 + CH05, house_2 CH07 + CH06, field CH01 + CH02); overlay = animal, IR mark, coban, EVENT bar, field-PC clock only; the WISER/IMU panel is revealed after the first answer (`verdict_blind`; later changes → `verdict_final`) → `<OUT>/2026c/wiser_event_review_<ts>/index.html`; the user exports JSON + CSV into **`configs/wiser_event_review_2026c/`**; **v2 `--circles [--map-run <p0 run>]`** (10-06, the user: circle the rat with WISER) draws the projected 14-in WISER circle — WISER → paddock by the `cv/cv_field/wiser_assist_p0.py` similarity map (accepted on one CH01 hour only → on-screen caveat + `map_flag`), paddock → pixel by a Newton inverse of `frame_correction.Corrections.to_paddock` — a static start circle in the blind clip, the moving V3 circle + raw dot in `clips_reveal/` after the first answer with a second question (`circle_verdict` on_rat / drifts_off / cannot_tell / no_circle); outputs `clips_reveal/`, `overlay_ass_reveal/`, `projection_coverage.csv`, `circles_summary.json`; **current page `<OUT>/2026c/wiser_event_review_20261006_1637/index.html`** (68 / 80 events with a circle: panoramas 48 / 54, CH06 20 / 20, none on CH05 / CH07 / CH08); without `--circles` it rebuilds v1 exactly); `analyze_wiser_common_mode --cohort 2026c` (cross-tag common-mode WISER error during joint certified stillness, from the failure audit's run: C1 residual correlation by zone pairing / timescale + shared `anchors_list` losses, C2 pairwise-distance precision and the SD ratio vs independent errors, C3 leave-one-tag-out differential correction from the other still tags; config `configs/wiser_common_mode_<c>.json`; pointer `run_manifest_common_mode_<c>.json`; result 10-03: **not material** — same-house 10-s correlation 0.04 calm / 0.27 rain, the correction makes the still error worse on average (+18 % RMS), the only shared ≥ 12-in excursions are the 09-10 09:46–10:04 episode with anchor 104 unlisted; B2 still-pair distance error p95 3.1 in (calm 2.7, rain 4.6), little cancels (R 0.88); the 14-in rule unchanged); config GUIs `place_wiser_rois`, `place_exclude_region`, `georeference_wiser` | `selftest_georeference`, `_output_paths`, `_wiser_inputs`; `analyze_imu_wiser_calibration.py --selftest`; `analyze_wiser_imu_smoothing.py --selftest`; `build_imu_wiser_cache.py --selftest`; `analyze_wiser_ins_fusion.py --selftest`; `analyze_imu_attitude_phase0.py --selftest`; `analyze_imu_attitude_gate_v2.py --selftest`; `make_imu_video_review.py --selftest` (ffmpeg + node); `analyze_wiser_ins_fusion_v5.py --selftest`; `analyze_wiser_failure_audit.py --selftest`; `analyze_wiser_default_smoother.py --selftest`; `analyze_wiser_v1b.py --selftest`; `analyze_imu_speed_proxy.py --selftest`; `analyze_wiser_v3.py --selftest`; `analyze_wiser_v6_fusion.py --selftest`; `analyze_imu_turn_vs_heading.py --selftest`; `build_wiser_default_tracks.py --selftest`; `analyze_wiser_imu_consistency.py --selftest`; `analyze_wiser_i1_return.py --selftest`; `make_wiser_event_review.py --selftest` (ffmpeg); `analyze_wiser_common_mode.py --selftest` |
| `wiser_d1_nightly` | `analyze_nightly_progression`, `analyze_nightly_behavior` | none |
| `wiser_d2_routes` | `analyze_route_structure`, `analyze_trajectory_stereotypy`, `analyze_following_structure`, `analyze_following_incidents` (+ `audit_following_video`, `calibrate_camera_visibility`), `analyze_route_vocabulary`, `analyze_route_motifs`, fireworks scripts | `_trajectory_stereotypy`, `_following_incidents`, `_route_vocabulary` |
| `wiser_d3_sleep` | **core `analyze_biological_day_sleep`**; `analyze_sleep_site_hierarchy`, `_heat_gated_relocation`, `_circadian_rest`, `_night_consolidated_rest`, `_daytime_rest_temperature`, `_sleep_site_cv_crossval`; partly superseded `analyze_evening_morning_sleep` (`sleep_end` retired); legacy `analyze_daytime_sleep_site` | `_biological_day_sleep`, `_sleep_site_hierarchy`, `_heat_gated_relocation`, `_circadian_rest`, `_night_consolidated_rest`, `_rest_temperature`, `_cv_crossval`, `_evening_morning_sleep`, `_daytime_sleep_site` |
| `wiser_policy` | `build_decision_tables` (superseded raw point-in-ROI unit) → `diagnose_decision_unit` → `build_ladder_grid` (hysteretic) → `aggregate_ladder_grid` / `analyze_policy_identifiability`; `analyze_temporal_policy`; `build_locomotor_states`, `build_settlement_transitions`, `build_approach_avoid`, `build_search_excursions` + their `analyze_*` | `_policy_identifiability`, `_temporal_policy`, `_locomotor_states`, `_settlement_transitions`, `_approach_avoid`, `_search_excursions` |

Library (`wiser/src/`): `wiser_io` (read-only SQLite/CSV loaders), `time_utils`, **`wiser_analysis_utils`** (~4.8 k
lines: `load_wiser_session`, `add_speed`, `add_validity_flags` — flags, never drops rows —, `apply_tag_cutoffs`,
`speed_noise_floor`, hysteretic shelter state `wiser_shelter_state`, D3 sleep functions incl.
`locomotor_emergence`), `semimarkov_decisions.hysteretic_visits` (14 in buffer, 5 s bins, enter 10 s / exit 30 s),
`field_transform`, `metrics`, `environment_map`, `default_tracks` (reader of the 2026c default tracks), plus one module per policy builder. Configs (`wiser/configs/`):
`rat_identities.csv`, `wiser_rois.json` (boundary + 11 ROIs with validity windows, e.g. `refuge_4` until 07-07 13:00),
`environment_map/*.yaml` (regime/dropout maps), `behavioral_policy_modules.yaml` (jitter 7 in, min resolvable 14 in),
`fixed_position_ground_truth.csv`. Gotchas: `refuge_4` ("shelter 4") dropout 07-03→07-07 is a burrow below the anchor
plane — a lower bound, not sleep; tag cutoffs apply only where `apply_tag_cutoffs` is called; live-DB tools open
`mode=ro` and must never write near `D:\Wiser`; policy builders hard-code 7.0 in / 12 in/s.

### Smaller subsystems

- **`audio/`** (→ `audio_soundscape`): relative camera-mic dBFS + soundscape indices from CH01/CH02 hourly MP4s, 60-s
  windows: `audio/scripts/extract_audio_features.py --channel CH01 --date … [--config configs/audio_analysis.analysis_pc.yaml]`,
  `summarize_soundscape.py`, `plot_soundscape_day.py`; Phase 2 in `audio/analysis/` (hard-codes `1stcohort_2026_*.sqlite`).
  Outputs to gitignored `audio/outputs/`; not cohort-aware.
- **`crossmodal/`**: an index README only — the drivers live in `wiser/scripts/` (`analyze_sleep_site_cv_crossval`,
  `analyze_fireworks_*`, `analyze_following_weather`) and audio Phase 2; reports in `results/2026a/crossmodal/`.
- **`aggregate/`**: empty cross-cohort layer (`aggregate/<c1>+<c2>/<direction>/`).
- **`episode_browser/`**: Streamlit reviewer of WISER route bouts / strict-following candidates with append-only
  judgments: `python build_real_slice.py`, then `python -m streamlit run app.py` from inside the folder (demo:
  `EPISODE_BROWSER_DATA_MODE=demo`). Imports only sealed `episode_candidate` bundles; data in gitignored `data/`, `outputs/`.
- **`analysis_exchange/`** (+ `ANALYSIS_BRIDGE.md`): sealed producer→consumer bundles (schema
  `contracts/analysis-result-bundle-0.1.0.schema.json`); `staging/` mutable, `published/` immutable — corrections are a
  new bundle with `supersedes_bundle_id`; missing scores stay missing, never zero.

### Shared layers and top-level docs

- **`cohorts/<key>.yaml`** — the only file to add per cohort. Blocks read by code: `raw_data_roots.<machine>`
  (`wiser_inputs`, `ephys/_common`), `wiser:` (2026a only), `ephys:` (2026c). `field_events` (2026c: acoustic
  disturbances, CH07/CH08 color-light windows, the 09-11 19:40 release of five non-implanted females → population 5→10)
  has no code reader yet but must be honored by any behaviour/sleep/ephys-state analysis.
- **`data_manifests/`**: per-dataset YAML manifests; `glass_treatments.yaml` and `field_conditions.yaml` are read by the
  shelter CV code. **`docs/`**: behavioral-policy map, methods notes. **`archive/`**: superseded reports (same shape as
  `results/`). **`PARKED_ITEMS.md`**: unresolved migration items. **`FIELD_OBSERVATIONS.md`**: 2026a daily field log +
  roster. **`runs/detect/`** (root) and `yolo*.pt`: untracked Ultralytics debris — ignore.
- **`.claude/`**: agents `analysis-result-bridge`, `analysis-status-simplifier`, `cv-measurement-auditor`,
  `wiser-measurement-auditor`, `recording-inquiry` (cited answers from the two sibling repos + the Notion cohort page),
  `research-logic` (Opus; keeps `research_logic/graphs/*.yaml` after each research phase; conflicts go to a Fable
  reviewer, the Codex "astra" session may review the logic as text only);
  skills `analysis-definitions`, `analysis-status`, `export-analysis-result`, `research-logic`,
  `scientific-report-promotion` → `human-readable-scientific-summary`, `regime-aware-*` (WISER, CV, **ephys**),
  `multi-agent-behavior-modeling-audit`, `offload-field-request` (after each neurologger offload QC); hook
  `protect_data_servers.py`. Mirrors for Codex: `.agents/skills/`, `.codex/agents/`.

## Sibling repos (the field record)

What follows is a **snapshot (2026-09-28)** of the two sibling repos and the Notion cohort page: enough to orient and
to know which rules apply. For anything specific or current — where a given stream/day lives and which copy is
original, a parameter on a given date, a gap or clock step, an animal's identity or probe move, what the field PC
reported — **dispatch the `recording-inquiry` subagent**: it fetches both repos, reads the Notion page through the
Notion connector, reads only the relevant notes and returns a cited answer. Don't read those sources wholesale in the
main session.

### Notion cohort page — the operator's notebook (always check it)

"4-Rat 3rd cohort — full (SF07–SF12)", https://app.notion.com/p/3c23b0530d4a8152a204cce3afa11671 (parent
"Rat_field_social_sleep_2026"). It is the **newest** field record: the repo archives of it
(`NOTION_OBSERVATION_LOG_ARCHIVE_cohort3.md`, `field2026-sync/from-field/*notion-observation-log*`) stop at 09-10, the
page runs through 09-12 and the 09-16/17 post-cohort temperature run. It holds:
- **Per-animal table** — probe advances with exact pre-/post-move session times and "kilosort: unstable until …"
  windows; implant losses (SF11 09-07, SF12 09-17 ≈03:16); WISER tag history; and the **identity marks**: coban colour
  (SF10 and SF12 changed on 08-31), sticker colour, and the IR-visible **pattern** (SF07 x, SF08 none, SF09 star, SF10
  square with cross, SF11 circle, SF12 two lines) — the only per-animal cue a monochrome IR frame can carry.
- **Observation log** per day (rounds, battery deaths, hardware findings, disturbance windows, the 09-11 19:40 females).
- **Behaviour log** with logger session + rec-seconds per observation (e.g. 09-09 22:33–23:06 SF07 motionless at a
  paddock corner) — ready-made WISER/video/LFP cross-check events.

The page can disagree with itself (e.g. SF11's tag 3058 retired at 06:10:45 in the observation log vs `valid_until
08:20` in the animal table): report both, prefer the version that cites video/card/telemetry evidence. The cohort-3
identity CSV `rat_identities_cohort3.csv` it refers to lives in the old `Field_2026_Social` repo, not here; the five
females' tags/marks were never stated.

### `Field_2026_Social_Recording` — rig tooling, setup, sync, field ledgers (`../Field_2026_Social_Recording`)

Standalone PowerShell 5.1 tooling for the 24/7 field rig (recorders, QC watchdogs, copy/delete) plus the field ledgers.
It never re-encodes (`ffmpeg -c copy`), never auto-deletes, never opens the live WISER DB (WISER acquisition is
operator-run). Its own `README.md` is stale (6 channels, D:, old NVR IP) — start from its `CLAUDE.md`. The field has
been demolished; no new capture is possible.

**Setup.** Everything is captured on the field PC: video/thermal/audio → `E:`, live WISER DB `D:\Wiser\data`, weather
`D:\weather_data`. Streams are hourly clock-aligned fragmented MP4/WAV named
`<stream>_YYYY-MM-DD_HH-MM-SS_to_HH-MM-SS.<ext>` (no `_to_` = still open / killed; starts may be offset ≤ ~1 min per
stream).

| Stream | Hardware / role | Format |
|---|---|---|
| CH01/CH02 | Reolink Duo 3, 180° panoramas, mid-field | HEVC 2160×7680 stored rotated 90°, ~20 fps; bottom band lost to keyframe truncation before 07-11 (`README_capped_kf.md`) |
| CH03/CH04 | RLC-1212A, one at each end of the paddock | |
| CH05/CH06 | RLC-520A, near-nadir over the shelters, through IR glass | 2560×1920 |
| CH07/CH08 | in-box cams (CH07 = house_2, CH08 = house_1); a **different camera** before 07-12 (direct-IP Dahua 720p ~6 fps) than from 07-17 (NVR-fed RLC-520A, 2560×1920, 20 fps) | |
| `108/109_thermal`, `_visual` | EmpireTech, direct IP (not via the NVR) | thermal 1280×960 ~1 fps; visual 2336×1752 ~1 fps |
| MIC01 / MIC02 | UltraMic 384K / 250K | hourly mono 16-bit WAV; MIC02 from 08-16 16:29 |
| Weather | Ambient console AWN-F8B3B78DEAC9 | 5-min CSV in `D:\weather_data\local` from 2026-09-03 |

Cameras switch between color and IR with the light (e.g. 09-18: CH04–CH06 IR until ~14:35), so check the frame, not
the channel, before using color; CH07/CH08 run IR with deliberate color inserts (`COLOUR_SAMPLING_LOG_cohort3.md`).

**Sync and clocks** (the part analysis most often gets wrong):
1. File names and PTS are **field-PC time**; a segment's `_to_` end = the next segment's start.
2. The OSD burned into CH01–CH08 is the **NVR clock**: PC − 60:00 (08-19), − 59:40 (09-10), − 59:25 (09-18), i.e.
   drifting — never align on it. The NVR reboots every Sunday 14:00 PC time (a few-minute gap on every channel).
3. **LED sync** (`README_led_sync.md`, from 2026-08-29): a Pico blinks an LED in camera view at 1 Hz from the PC clock;
   `E:\led_sync\LEDSYNC_<date>_<HH>-00-00.txt` has one `RISE` line per second with `offset_ms` (+0.3–1.4 ms, plus 1–3 ms
   USB). Phase only, no absolute marker — the file name supplies the second. The join pipeline is
   `field2026-sync/from-field/2026-09-03_led_sync_pipeline.py`; `ephys/pc_time_chain.py` emits its schema.
4. **PC drift** (`README_pc_drift.md`, from 2026-08-29): NTP sampled 4×/day, never sets the clock →
   `E:\recording_qc\pc_drift_log.csv` (`offset_ms` = **NTP − PC, + = PC slow**: the code computes the standard NTP θ; the
   script's docstring and `README_pc_drift.md` say the opposite and are wrong —
   `field2026-sync/from-field/2026-09-07_pc-clock-drift-analysis.md` §0; `w32time`, `tz_id`). A step = the clock was
   set → split the analysis there. The recording repo does not list clock steps: derive them from this log + the
   incident log; this repo's registry of them is `cohorts/2026c.yaml ephys.field_pc_clock_steps`.
5. **Neurologgers (cohort 3):** Resync only on an idle logger before Record Start; Sync[Live] anchors land on the
   logger's SD (`analogin.dat`) about every 5 s — the PC stores nothing sync-critical. Per-round Start/Stop and anchor
   counts: `BATTERY_LOG_cohort3.md`. The console `ble_messages.csv` is UTC. (`README_neurologger_daily_resync.md` is the
   superseded cohort-2 procedure.)
6. WISER, mics and wild_console follow the PC clock; weather rows use the console's own `dateutc` (the raw JSONL
   `received_local` is PC time).

**Data flow.** Field `E:` → `copy_to_analysis.ps1` → `\\192.168.50.2\audio_in` (analysis mini PC; stream-first
`Reolink_record\CHxx`, `thermal_record`, `ultramic_record`, `Wiser_backup`, `nvr_rescue`; `copy_manifest_<date>.csv`;
verified on the receiving side per `README_verify_server_copy.md`). And field `E:` → `copy_day_to_usb.ps1` /
`copy_cohort_to_usb.ps1` (day-first, writes the save log) → campus PC `copy_ssd_to_server.ps1` →
`Q:\hc997\SocialFieldRat2026\…` (name + exact byte size). The field PC has no route to BioHPC. Deletion only via
`delete_day.ps1`, which refuses days missing from the save log. `E:\led_sync`, `E:\recording_qc`, `D:\weather_data` and
`E:\WILD` are not copied by `copy_to_analysis`.

**Calibration.** The release is `calibration_qc/` (2026-09-24, `CALIBRATION_REPORT_2026-09-24_rev2.md`; loads without
`E:`): ChArUco plate sessions 09-18/19, bundle adjustment + per-camera ground warp, **CH01–CH06 only**. Use
`paddock_map.load()` → `to_paddock(px, z_mm, units="in")` (NaN outside each camera's verified support; pano pixels
upright). Frame: 480 × 240 in, origin pole A0, defined by the laid lattice of cords/cones/wall. Status: exploratory,
region-restricted only — held-out cross-camera disagreement median 76 mm, p90 137 mm (worst at the +x end), ground plane
only; not accepted for whole-field accuracy (`AUDIT_CALIBRATION_2026-09-24*.md`). CH07/CH08 and thermal are
uncalibrated; the older CH05/CH06 4-point fits are not accepted.

**Per-cohort records.** `BATTERY_LOG_cohort3.md` (per round: Stop/Start, fleet gaps, anchor counts, SD cards, probe
moves, ADC lane; SF11 retired 09-07; five females added 09-11 19:40), `COLOUR_SAMPLING_LOG_cohort3.md`,
`EXPERIMENT_END_2026-07-12.md` / `_2026-07-31.md` (stop times, unrenamed final segments), `change_log/` (provenance
boundaries: 06-29 NVR IP gap, 06-30 fps change, 07-07/07-17 CH07/CH08 swaps, 07-11 keyframe fix, 08-19 `nvr_rescue`),
`NOTION_OBSERVATION_LOG_ARCHIVE_cohort3.md`, `COHORTS.csv` (only cohort1 and cohort1_mice rows). Where to look:
video↔ephys alignment → `README_led_sync.md`, `README_pc_drift.md`; filename parsing and holes →
`README_verify_server_copy.md`; camera identity changes → `change_log/2026-07-17-ch07-ch08-moved-to-nvr.md`; CH01/CH02
image damage → `README_capped_kf.md`, `EXPERIMENT_encoder_bitrate_2026-07-09.md`; weather schema →
`README_weather_listener.md`; in-box identity → `EXPERIMENT_ir_identity_color_sampling.md`.

### `field2026-sync` — field↔lab channel and the storage map (`../field2026-sync`)

Text-only exchange between the field recording PC and the lab (md/csv/json/ps1/py, < ~10 MB; media and SQLite are
gitignored). **Entry point for cohort 3: `COHORT3_DATA_GUIDE.md`** (regime boundaries, traps, where each stream
lives). Every file is `YYYY-MM-DD_<title>` (America/New_York). `from-field/` = field-PC agent, `from-lab/` = lab
agent, `tasks/` = requests both ways: the other side appends `## Response (side, time)` and moves the file to
`tasks/done/`. Operator decisions are relayed inside notes/tasks.

Where the data lives (verify against the dated reconciliation notes — drive letters are not identity; `E:` has been
three different disks):

| Data | Original / authoritative | Other copies | Naming / rules |
|---|---|---|---|
| Video CH01–CH08, thermal `108/109_{thermal,visual}`, mics `MIC01/02` | field PC `E:\Reolink_record\CHxx`, `E:\thermal_record\…`, `E:\ultramic_record\MIC0x`; authoritative copy `Q:\hc997\SocialFieldRat2026\3rd_rat\<date>\<stream>\` | 20 TB HDD (`from-field/2026-09-18_external-hdd-backup-f.md`); Q: reconciled 09-23 (24.31 TB, 10,143 files) | `<stream>_<date>_<start>[_to_<end>].mp4/.wav`, hourly; no `_to_` = open/killed last segment, valid up to its mtime |
| Ephys raw (WILD) | analysis PC `E:\3rd_rat_spikes` | `Q:\…\3rd_rat\WILD\SF7..SF12\<MAC>\<session>\`; L: backup (verified 09-20); SD cards unformatted — keep | raw `SF7` unpadded, pc_time `SF07` padded; lane-ON sessions in `WILD\_quarantine_adc_lane_on\` |
| `recovery.bin` (night-1 card images) | `Q:\…\3rd_rat\WILD\SF*\` | E:, F: | forensic only, parsed by nothing |
| `pc_time` | `Q:\…\3rd_rat\analysis\pc_time\SF07..SF12\<session>\` (`pc_time.dat` + `pc_time_fit.json`, 429 sessions) | SanDisk 4 TB `cohort3_pc_time\`; algorithm + fits + `regen_pc_time.py` in `from-lab/2026-09-21_pc-time-algorithm-backup/` (rebuild ≈ 70 min) | uint32 ms-of-day, wraps at midnight |
| WISER | field PC `D:\Wiser\data\3rdcohort_Spike_2026_3_N.sqlite` (N grows per restart) | `E:\Wiser_backup` (snapshots + incrementals), `Q:\…\3rd_rat\wiser\data\`, `Q:\…\3rd_rat\Wiser_backup\` | `tag_reports.sqlite` holds test epochs — filter by time |
| Weather | field PC `D:\weather_data\local\AWN-F8B3B78DEAC9_<date>.csv` (the record; cloud is a mirror) | git copies `from-field/AWN-*`, `NWS-KITH-*_gapfill.csv` | hole 09-03 15:05–15:16; no weather folder on Q: |
| Logs / health | field PC `E:\recording_qc\*`, `E:\led_sync\LEDSYNC_<date>_<HH>-00-00.txt`, `E:\recording_health_reports\incident_log.md` | mirrors in `from-field/`: `*_ledsync_<day>.txt`, `*_pc-drift-log.csv`, `*_pc-side-session-marks.csv`, `*_autostop-ends.csv`, `*_cohort3-incident-log.md` (newest = complete) | |
| Other cohorts | `Q:\hc997\SocialFieldRat2026\{1st_rat, 1st_mice, 2nd_rat_LFP}` (pilot: `1st_rat\<date>\<stream>`, `1st_rat\Wiser_backup`) | `W:\data\Field_social_2026` (WILD SF1–SF6 only) | the cohort-3 WISER archive is on Q:, not W: |

Retention: deletions happen one day at a time, only after a lab GO sign-off + save-log entry, via `delete_day.ps1
-RequireSaved`; never delete `E:\Wiser_backup` or `E:\nvr_rescue`; keep the 09-17 empty-arena mic WAVs (acoustic
baseline); `*.config.psd1` files contain credentials — never copy them to a shared location.

Where to look: gaps → newest `from-field/*_cohort3-incident-log.md`; clock steps →
`from-lab/2026-09-03_cohort3-field-pc-clock-steps.md`, `2026-09-04_cohort3-reboot-step-measured.md`,
`from-field/2026-09-07_pc-clock-drift-analysis.md`; video↔PC sync → `from-field/2026-09-03_led-sync-pipeline.md`;
de-glitch / ADC lane → `from-field/2026-09-01_fm59-62-signal-defects.md`, `2026-09-10_adc-lane-contamination-boundaries.csv`;
channel map → `from-lab/2026-09-03_cohort3-channel-map-fm65.md`; behaviour notes →
`from-field/behaviour_observations_cohort3.csv`; IR identity → `from-field/2026-09-10_ir-identity-label-sources.md`;
weather → `from-field/2026-09-10_cohort3-weather.md`; per-animal ephys hours →
`from-lab/2026-09-17_cohort3-ephys-offload-complete.md`; Q: layout → `from-lab/2026-09-23_*reconciliation.md`,
`2026-09-24_*`.

## Known gaps (verified 2026-09-28)

Fix these or confirm before relying on the affected code:
- `analyses/registry.yaml` rerun commands pass `--cohort 2026a`, but only `analyze_circadian_rest.py`,
  `analyze_heat_gated_relocation.py` and `prune_wiser_runs.py` define it — the others exit with an argparse error (they
  read `FIELD2026_COHORT`).
- `wiser/scripts/georeference_wiser.py`, `analyze_sleep_site_cv_crossval.py`, `calibrate_camera_visibility.py` still
  point at the pre-migration `preprocessing/computer_vision/` tree (now `cv/`).
- `cohorts/2026c.yaml` `ephys.analysis_root` (`D:/3rd_rat_spikes/analysis`) does not exist on this PC (only the
  `index/` created 2026-09-28); the pc_time master is now `Q:\…\3rd_rat\analysis\pc_time`. **Deferred by the user:** it
  gets re-specified when cohort-3 analysis restarts — until then pass `--pc-time-root` / `--stage-root` / `--sort-root`
  explicitly rather than trusting the default. After pulling onto the ephys PC, restore the session-index JSON once:
  `git show fcaa792:results/2026c/ephys_spikes/reports/ephys_spikes_session_index_2026c.json > <ar>/index/ephys_spikes_session_index_2026c.json`.
- `cohorts/2026c.yaml raw_data_roots.biohpc` lists every cohort-3 location on `Q:\hc997\SocialFieldRat2026\3rd_rat\`
  (video/thermal/mics `<date>\<stream>\`, `WILD\`, `wiser\data\`, `Wiser_backup\`, `analysis\pc_time\`; filled 2026-09-28).
  Cohort-3 WISER still cannot go through `common/wiser_inputs.py`: 2026c has no `wiser:` block (snapshot glob / pin) —
  the resolver raises instead of guessing; use the production default tracks (`wiser/src/default_tracks.py`, built from the
  `wiser_working` DB copies) instead. The
  `analysis_pc` video/thermal/WISER entries stay `null`. `cohorts/2026a.yaml` and `thermal --base` use Q: paths from
  before the per-cohort reorganisation (`Q:\…\1st_rat\…` now).
- Sibling repos resolve through `ephys/_common.sibling_repo()` (`../<name>`, fallback `C:/Users/Cornell/Documents/GitHub/`);
  `ephys/selftest.py` still hard-codes `C:/…/PreprocessPipeline` (absent here; that check is skipped).
- `cv_field` and `ephys_spikes` have no `analyses/registry.yaml` entries (no cards/summaries); `STATUS.md` and
  `aggregate/README.md` still describe one cohort.
- `data_manifests/README.md` points to "AGENTS.md → Data Manifest Requirements", which no longer exists.
