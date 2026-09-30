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
have no entries yet). `STATUS.md` is the cohort × direction board.

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
| L | LFP for every session (before sorting; phase L of the plan) | `make_lfp.py [--animal …] [--session …] [--workers 8]` (`--dry-run`, `--selftest`) | `<ar>/lfp/<SFxx>/<session>.lfp` + `.lfp.json` (pipeline filter: Butterworth-5 450 Hz zero-phase on raw, ÷16 → 1250 Hz; FM64 de-glitched in the stream; one sequential read stream per worker; ~60× real time on this PC from the USB HDD, ~200× on BioHPC with `--workers 8`; server and PC outputs byte-identical). Windows: `--start-seconds S --max-seconds D`; `--src <staged dir> --out-name N` converts a staged (already de-glitched) copy instead of the raw session. Whole cohort on BioHPC: `ephys/server/run_make_lfp.sh` → `/workdir/hc997/ephys_2026c/lfp/` + MD5 manifest, then copied to storage `3rd_rat/analysis/lfp/` (never into `WILD/`) |
| IMU | read the head IMU (read-only) | `read_imu.py --check <session_dir>`; `read_imu(session_dir, start_s, dur_s)` | nothing written; `analogin.dat` lanes 1-3 acc, 4-6 gyro, 7-9 mag at 1250 Hz (frame k ↔ amplifier 16k). **Magnetometer x saturated on all six loggers — the headstage carries a magnet (user, 2026-09-28) → no magnetic heading; never use lanes 7-9 for orientation.** Layout, validation and the audit of the lab MATLAB IMU scripts: `docs/methods/wild_ce64_imu.md` |
| IMU+ | movement / 2D turning / posture per session (sleep-EMG, identity with video and WISER) | `make_imu.py [--animal …] [--session …] --pc-time-root <…/analysis/pc_time>` (`--selftest`) | `<ar>/imu/<SFxx>/<session>.imu.npz` (50 Hz), `.imu_1s.csv` (per second, field-PC time), `.imu.json`; 6-axis Fusion AHRS in the head frame (lab map S verified); ~45 s per 12-h session locally |
| S | sleep score (PILOT) | `score_sleep.py --sessions SF10:<s> … [--variants imu imu_nremgate lfpemg] [--anchor A:S:REC_S:STATE]`; no `--sessions` = rebuild the CSVs | `<ar>/sleep/<variant>/<SFxx>/<s>/` (hard-linked `.lfp`, `session.mat`, SleepScoreMaster outputs, `complex_system/` = the user's review copy for `Sleep_dynamics/state_editor.py`, never overwritten); `reports/…sleep_pilot_<c>.csv` + `_agreement_<c>.csv`. Scorer = PreprocessPipeline `state_scoring.py`, unmodified; the IMU enters as `EMGFromLFP.LFP.mat`. Refuses sessions with frozen/invalid IMU. ~10–12 min per variant per 8-h session |
| 2 | stage | `stage_session.py --animal SF10 --session <s> [--window-s S D]` | `<ar>/stage/<SFxx>/<s>/`: clean `amplifier.dat`, sidecars, `<s>.xml`, manifest |
| 3 | sort | `run_sort_session.py --animal … --session … --partition shank` (`preprocess` env) | `<ar>/sort/<SFxx>/<s>/` (KS4 per shank, `_spi` postprocessed); row in `reports/…sort_runs_<c>.csv` |
| 4 | yield / curate | `unit_yield_report.py`; `open_phy.py --list` / `--animal --session --shank k [--raw]` | `reports/…ks4_unit_yield_*`; Phy edits in `_spi` |

Core library: `_common.py` (`ephys_block`, `raw_ephys_root`, `analysis_root`/`stage_root`/`sort_root`/`tools_root`/
`index_root`, `report_dir`/`figure_dir`, `iter_raw_sessions` — skips foreign-MAC cards, `git_commit`, `write_json`),
`wild_ce_params.py` (header), `signal_probe.py` (glitch probe/regime), `deglitch_wild.py` (vendored field de-glitch),
`make_session_xml.py`, `resort_shanks.py`, `backup_manifest.py` (SHA-256 tree compare). Everything else is a one-off
**check**: channel map (`probe_group_check`, `probe_map_check`, `footprint_map_check`, `lfp_profile_check` [`--raw <dir> --offset-min M --minutes N [--no-deglitch] [--derive-xml OUT] --save-profile OUT.npz`: keep the profiles; user reference windows per animal in `configs/lfp_reference_windows_2026c.yaml`; `swr_gradient_order.py --profiles *.npz --orders NAME=xml …` scores/derives orders by the SWR gradient — amplitude and width rising along the shank, no polarity reversal needed (user rule)],
`wiring_pattern_check`, `bridged_pins_check`, `make_probe_xml` → `configs/xml/`), FM64 residue
(`template_width_check`: reject units with neighbour/peak ratio < 0.4), raw corruption (`integrity_scan`), HPC vs
cortex (`hpc_signature_check`, `swr_strict_check`), probe advance (`probe_move_check`, `probe_move_timeseries`) — the
last four hard-code 2026c windows. Configs: `configs/probes_2026c.yaml` (per-animal maps, `verified:` flags),
`configs/kilosort4_wild.yaml`; `patches/*.patch` are upstream proposals only — the fixes are applied at runtime (a
`run_sorter` shim + a patched Kilosort4 copy in `<ar>/tools/Kilosort4_field2026`).

`cohorts/2026c.yaml ephys:` keys the code reads: `loggers.<SF>.mac` (foreign-card filter), `clean_firmware_min` (65),
`deglitch.{k_mad,floor_adc}`, `field_pc_clock_steps`, `field_flags` (excluded from coverage; `pc_time: false` = not
fitted/chained), `valid_until` (clips coverage), `pc_time_accept`, `adc_lane.on_windows`, `probe_config`,
`preprocess_pipeline_root`, `analysis_root`. Informational only (no code reads them): `probe_moves`, `probe_notes`,
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
paddock each in the 09-24 calibration (CH03/CH04 ~12 % each, the two ends) and so carry the occupancy map; the existing
detector and all 255 labels are cohort-1 CH03/CH04, so CH01/CH02 start from zero labels. A rat is ~70–160 px in the
native upright pano (7680×2160) → never the 1280 default (11–16 px); compare whole pano @2560 vs half @1920 after
labelling. **Workflow:** local first — frames from the local copy `F:\3rd_rat\` with `cv/cv_field/grab_frames.py`
(`--targets camera,time[,tag] --out <dir>`; exact CPU decode ≈ 0.9 s/frame — the benchmark showed decode is not the
bottleneck and NVDEC gives no single-frame gain, so `--decode gpu` is for whole-night inference), times chosen by
`select_pano_targets.py` (tagged animals outside the houses per 5-s WISER bin → stratified night targets, a held-out
test night), frames stored locally (`cv/dataset/rat_pano*`), labelled locally, small pilot; only then large batches on
BioHPC (`cv/cv_field/REMOTE_COMPUTE.md`). Plan: `implementation_plan/2026-09-28-cohort3-ch0102-yolo-pilot.md`. **Camera stability is judged by a person**:
`cv/cv_field/camera_review.py` lays out daily frames with the 09-18 wall-foot lines for review (an automatic ECC check
failed — grass, rain, IR/colour changes); weather-driven moves are reported manually. **The agent does not judge
images** and confirms every test plan with the user first.

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
| `wiser_baseline` | `analyze_fixed_position_test`, `plot_hourly_occupancy`; `analyze_imu_wiser_calibration --cohort 2026c` (head IMU vs WISER: lag, IMU-selected jitter/speed floor, handedness, `rest_mask` agreement; inputs `configs/imu_wiser_calibration_<c>.json`; its report pointer is `run_manifest_imu_calibration_pilot_<c>.json` so the accuracy report's `run_manifest.json` survives); `analyze_wiser_imu_smoothing --cohort 2026c` (held-out-fix test of smoothers: library median-7 vs robust per-anchor CV Kalman/RTS ± drift vs + head-IMU ZUPT / IMU-switched process noise, +1 h-IMU controls; tune 09-08/09, test 09-10/11; config `configs/wiser_imu_smoothing_<c>.json` incl. the fitted `tuned` block; numba if installed; pointer `run_manifest_imu_smoothing_pilot_<c>.json`); config GUIs `place_wiser_rois`, `place_exclude_region`, `georeference_wiser` | `selftest_georeference`, `_output_paths`, `_wiser_inputs`; `analyze_imu_wiser_calibration.py --selftest`; `analyze_wiser_imu_smoothing.py --selftest` |
| `wiser_d1_nightly` | `analyze_nightly_progression`, `analyze_nightly_behavior` | none |
| `wiser_d2_routes` | `analyze_route_structure`, `analyze_trajectory_stereotypy`, `analyze_following_structure`, `analyze_following_incidents` (+ `audit_following_video`, `calibrate_camera_visibility`), `analyze_route_vocabulary`, `analyze_route_motifs`, fireworks scripts | `_trajectory_stereotypy`, `_following_incidents`, `_route_vocabulary` |
| `wiser_d3_sleep` | **core `analyze_biological_day_sleep`**; `analyze_sleep_site_hierarchy`, `_heat_gated_relocation`, `_circadian_rest`, `_night_consolidated_rest`, `_daytime_rest_temperature`, `_sleep_site_cv_crossval`; partly superseded `analyze_evening_morning_sleep` (`sleep_end` retired); legacy `analyze_daytime_sleep_site` | `_biological_day_sleep`, `_sleep_site_hierarchy`, `_heat_gated_relocation`, `_circadian_rest`, `_night_consolidated_rest`, `_rest_temperature`, `_cv_crossval`, `_evening_morning_sleep`, `_daytime_sleep_site` |
| `wiser_policy` | `build_decision_tables` (superseded raw point-in-ROI unit) → `diagnose_decision_unit` → `build_ladder_grid` (hysteretic) → `aggregate_ladder_grid` / `analyze_policy_identifiability`; `analyze_temporal_policy`; `build_locomotor_states`, `build_settlement_transitions`, `build_approach_avoid`, `build_search_excursions` + their `analyze_*` | `_policy_identifiability`, `_temporal_policy`, `_locomotor_states`, `_settlement_transitions`, `_approach_avoid`, `_search_excursions` |

Library (`wiser/src/`): `wiser_io` (read-only SQLite/CSV loaders), `time_utils`, **`wiser_analysis_utils`** (~4.8 k
lines: `load_wiser_session`, `add_speed`, `add_validity_flags` — flags, never drops rows —, `apply_tag_cutoffs`,
`speed_noise_floor`, hysteretic shelter state `wiser_shelter_state`, D3 sleep functions incl.
`locomotor_emergence`), `semimarkov_decisions.hysteretic_visits` (14 in buffer, 5 s bins, enter 10 s / exit 30 s),
`field_transform`, `metrics`, `environment_map`, plus one module per policy builder. Configs (`wiser/configs/`):
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
  `wiser-measurement-auditor`, `recording-inquiry` (cited answers from the two sibling repos + the Notion cohort page);
  skills `analysis-definitions`, `analysis-status`, `export-analysis-result`,
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
  to be added when cohort-3 WISER analysis starts; until then the resolver raises instead of guessing. The
  `analysis_pc` video/thermal/WISER entries stay `null`. `cohorts/2026a.yaml` and `thermal --base` use Q: paths from
  before the per-cohort reorganisation (`Q:\…\1st_rat\…` now).
- Sibling repos resolve through `ephys/_common.sibling_repo()` (`../<name>`, fallback `C:/Users/Cornell/Documents/GitHub/`);
  `ephys/selftest.py` still hard-codes `C:/…/PreprocessPipeline` (absent here; that check is skipped).
- `cv_field` and `ephys_spikes` have no `analyses/registry.yaml` entries (no cards/summaries); `STATUS.md` and
  `aggregate/README.md` still describe one cohort.
- `data_manifests/README.md` points to "AGENTS.md → Data Manifest Requirements", which no longer exists.
