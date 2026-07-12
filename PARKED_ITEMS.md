# PARKED_ITEMS.md — not migrated, awaiting a human ruling

During the migration from the old `Field_2026_Social` monolith, items whose **recording-vs-analysis** status
is genuinely unresolved were **not** pulled into the active tree (per the hard rule "AMBIGUOUS items stay
unmigrated until ruled"). They remain intact in the old repo. Rule on each; then a follow-up change either
migrates it (with links rewired) or leaves it in the archived old repo.

## Parked (genuinely ambiguous — no code dependency forces a decision)

| Item (old-repo path) | Why ambiguous | If ruled "analysis" |
|---|---|---|
| `wiser_tracking_analysis/scripts/analyze_formal_recording.py` (old repo) | ◻️ stub ("loads + cleans only"), named for capture sessions; no importers, no change log | → `wiser/scripts/` |
| `preprocessing/lfp_recording/copy_and_storage_protocol.md` | planned LFP modality; recording/storage protocol prose, no code | → `docs/` or a planned-modality area |
| `preprocessing/security_camera/copy_and_storage_protocol.md` | planned security-video modality; copy/storage protocol prose, no code | → `docs/` or a planned-modality area |
| `observation.md` (root) | a pointer to the separate `Field_2026_Social_Recording` repo (recording-oriented) | → keep as a cross-repo pointer, or drop |
| `.codex/` (root) | Codex-ecosystem counterpart to `.claude/`; not analysis content | → migrate only if this repo keeps Codex tooling |
| `wiser_tracking_analysis/install_wiser_occupancy_task.ps1` (old repo) | scheduled-task installer (ops automation) for an analysis output | → an `ops/` area, or leave in recording repo |
| `wiser_tracking_analysis/scratch_env_change_audit.py`, `scratch_habituation_power_out.json` (old repo) | untracked scratch, not wired into any pipeline | → discard or promote to a real driver |

## Reclassified AMBIGUOUS → MIGRATE (evidence-driven, not a guess) — already migrated

These were flagged AMBIGUOUS by modality/maturity, but a **code dependency or import graph proves they are
analysis infrastructure**, and parking them would break migrated code or dangle references (a link-integrity
failure). They were migrated; flagged here for your override.

| Item | Evidence it is analysis | New location |
|---|---|---|
| `data_manifests/glass_treatments.yaml` | imported by migrated CV modules `glass_regime.py`, `measurement_context.py`, `shelter_sleep.py`, `validate_shelter.py` | `data_manifests/glass_treatments.yaml` |
| `scripts/audit_following_video.py` + `configs/video_audit_manual.csv` | driver imports 5 WISER analysis modules (`wiser_analysis_utils`, `camera_router`, `following_incidents`, `trajectory_stereotypy`, `analyze_trajectory_stereotypy`); referenced by `analyze_following_incidents.py` | `wiser/scripts/`, `wiser/configs/` |
| `change_log/2026-06-28-hourly-occupancy-maps.md` + `implementation_plan/…` | document the migrated analysis driver `plot_hourly_occupancy.py`; `ANALYSIS_STATUS.md` links to them | `change_log/`, `implementation_plan/` |

## Excluded (recording — not migrated, by rule)

`reolink_record/`, `reolink_export/`, `wiser_tracking_analysis/scripts/backup_wiser_daily.py` (old repo, + its
`README_backup.md`, `install_wiser_backup_task.ps1`), `change_log/`+`implementation_plan/`
`2026-06-25-daily-recording-continuity-check.md` and `2026-06-30-wiser-daily-backup.md`, and the vendored
`yolo11n/11s/26n.pt` COCO backbones (re-downloadable). Recording belongs in the `social_recording` repo.
