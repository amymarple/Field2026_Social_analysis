# Data map — cohort-1 pano rat detector, SAM3 comparison, cohort-3 transfer test, WISER-assisted YOLO

Written 2026-10-05 for an auditor with no prior context. It lists every input, output, cache, report and piece of
code of this line of work, with its producer and how to check it. Paths are on the analysis PC `DESKTOP-HUA1FJN`;
`$OUT` = `D:/Field2026_analysis_out`, `REPO` = `D:/Documents/GitHub/Field2026_Social_analysis` (branch `main`, local
commits only, not pushed). Status: **final** = written and committed; **in progress** = being produced by a running
job when this file was written; **planned** = not yet produced.

Plans and logs (start here): `REPO/implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md` (steps 0–3 + dated
amendments), `REPO/implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md` (the WISER phase, planned),
`REPO/change_log/2026-10-05-c1-yolo-transfer-sam3.md`. Commits: `c76af8c` (plan, before results), `bea8c9d` (steps
0–3 code, reports, docs), `951300d` (WISER phase-0 plan + this data map), `62309b3` (post-hoc SAM3 prompt "Long Evans
rat" + fixed-spot diagnostic).

## A. Cohort-1 detector: source and backup

| What | Path | Producer / status | Check |
|---|---|---|---|
| Source folder (read-only; another lab member's work, last edit 2026-09-14) | `D:/Documents/GitHub/social-field-rat/` | not a working git repo: `.git/` holds only `refs/` | never write into it |
| **Verified backup** of the source (labels, frames, weights, docs, code; excludes `.venv`, `__pycache__`, 12 prediction/tracking videos ≈ 50.7 GB) | `$OUT/2026a/social_field_rat_backup_20261005/` | `cv/cv_field/backup_social_field_rat.py`, final | `MANIFEST_sha256.csv` (5 469 files, 51 349 119 388 bytes), `VERIFY.json` (pass, 0 mismatch / missing / extra), `EXCLUDED_files.csv`, `README.md`; re-verify: `python cv/cv_field/backup_social_field_rat.py --verify-only` |
| Labelled frames, 887 (YOLO txt, class 0 = rat, upright 7680 × 2160 png) | backup `computer_vision/data/labeled_yolo/{images,labels}/{train,val}` (710 / 177) and the source folders `raw_frames/CH01_2026-06-30…`, `raw_frames/CH01_2026-07-04…`, `frames_0707_selective/images`, `frames_0630_CH02_selective/images`, `frames_0706_CH02_selective/images` | built by the source repo's `prepare_dataset.py` (seed 0) | counts in the plan's Inventory |
| Held-out partial clips (not in the dataset) | backup `computer_vision/data/frames_0704_CH02_selective/images` (75 png, 60 labelled), `frames_0705_CH01_selective/images` (75 png, 33 labelled) | — | **CH02 07-04 labels = v5 pre-labels unchanged** (`label_provenance.csv` in the step-1 run) |
| YOLO weights v1–v5 (`best.pt`, `last.pt`, `args.yaml`, `results.csv`) | backup `computer_vision/outputs/runs/{rat_s_1280_e50_v1,rat_s_v2,rat_s_v3,rat_m_v4,rat_m_v5}/` | trained 07-13 → 07-23 in the source repo | v5 `best.pt` sha256 `2d7294f3e29da845c8c6c26a39d427ffbe374274524e2cfd922c0edd51b63360` |
| Author's model log | backup `computer_vision/models.md`, `WORKFLOW.md`, `LABELING.md` | — | its "colour vs IR" split is contradicted numerically (step 1) |

## B. Step 1 — SAM3 zero-shot vs YOLO v5 on labelled cohort-1 frames

| What | Path | Status |
|---|---|---|
| Run folder | `$OUT/2026a/cv_field_sam3_vs_yolo_c1_20261005_1750/` | final |
| Ground truth, frame list, lighting class | `gt.csv`, `frames.csv`, `lighting.json`, `ref_chroma.csv` | final |
| Cached raw predictions | `yolo_preds.csv.gz` (v5 @1280 and @2560, conf ≥ 0.01), `sam3_tiles_t1008.csv` / `sam3_tiles_t2016.csv` (per-tile SAM3 boxes), `sam3_preds.csv.gz` (merged per frame), `sam3_merge_stats.json` | final |
| Scores | `metrics_center.csv` (primary, centre match), `metrics_iou.csv`, `pr_*.csv`, `counts_*.csv`, `diffs_*.csv` | final |
| Label provenance diagnostic | `label_provenance.csv` | final (after results) |
| Timing | `timing_yolo.csv`, `timing_sam3_t1008.csv`, `timing_sam3_t2016.csv` | final |
| **Post-hoc prompt "Long Evans rat"** (user suggestion, after results) | `sam3_tiles_t1008_ler.csv`, `sam3_tiles_t2016_ler.csv`, `timing_sam3_t1008_ler.csv`, `timing_sam3_t2016_ler.csv` (image features computed once per tile; "rat"/"animal" caches reused) | final (`62309b3`) |
| Report, figures, pointer | `REPO/results/2026a/cv_field/reports/cv_field_sam3_vs_yolo_c1_2026a.md`, `REPO/results/2026a/cv_field/figures/sam3_vs_yolo_c1/*.png`, `REPO/results/2026a/cv_field/reports/run_manifest_sam3_vs_yolo_c1_2026a.json` | final (post-hoc section added in `62309b3`) |
| SAM3 weights | `C:/Users/Cornell/.cache/huggingface/hub/models--facebook--sam3/snapshots/3c879f39826c281e95690f02c7821c4de09afae7/sam3.pt` (3.45 GB, downloaded 2026-10-01) | external |
| Code | `REPO/cv/cv_field/sam3_vs_yolo_c1.py` (`--selftest`, `--run`, `--phases`, `--score-only`) | final |

## C. Steps 2–3 — YOLO v5 on cohort-3 CH01, night 09-06 21:00–22:00

| What | Path | Status |
|---|---|---|
| Raw video (read-only) | `F:/3rd_rat/2026-09-06/CH01/CH01_2026-09-06_21-00-00_to_22-00-00.mp4` (1 289 651 963 bytes; local copy). Authoritative copy: `Q:/hc997/SocialFieldRat2026/3rd_rat/2026-09-06/CH01/` | raw |
| Run folder | `$OUT/2026c/cv_field_c1yolo_video_20261005_1848/` | final |
| Hour choice | `hour_selection.csv` (mean WISER outside-count per candidate hour) | final |
| Cached detections (every frame, conf ≥ 0.05, upright pano px) | `detections.csv.gz` (frame, pts_s, t_pc, x1, y1, x2, y2, conf; 423 882 rows), `frames.csv.gz` (72 000 frames) | final |
| Derived tables | `per_frame_counts.csv.gz`, `per_second.csv`, `per_5s.csv` (YOLO vs WISER outside-count), `plausibility.json` | final |
| Orientation check | `identity_check.json`, `identity_frame_26200.png` (pipeline frame vs `grab_frames.grab`, max diff 0) | final |
| Review media for the user | `review_10min.mp4` (21:21:50–21:31:50), `review_clips/` (5 clips + `clips.csv`, `eligible_windows.csv`, `index.html`, `review_template.csv`) | final; user review pending |
| **Fixed-spot diagnostic** (cached detections only) | `fixed_spots/` (`index.html`, `fixed_spots.csv`, `fixed_spots.json`, `cells.csv.gz`, `locator.png`, `heatmap.png`, `crops/`, `fixed_spots_review.csv` and `fn_notes.txt` for the user) | final (`62309b3`); user review pending |
| Run metadata | `run.json` (video, weights + sha256, versions, runtime) | final |
| Report, pointer | `REPO/results/2026c/cv_field/reports/cv_field_c1yolo_video_2026c.md`, `REPO/results/2026c/cv_field/reports/run_manifest_c1yolo_video_2026c.json` | final (fixed-spot section added in `62309b3`) |
| Code | `REPO/cv/cv_field/c1_yolo_video_test.py` (`--selftest`, `--hour-only`, `--run`, `--steps`); `REPO/cv/cv_field/c1_yolo_fixed_spots.py` (`--selftest`) | final |

## D. WISER inputs (read-only; used by step 2 and by the planned WISER phase)

| What | Path | Producer |
|---|---|---|
| WISER SQLite copies (cohort 3, four DB generations) | `$OUT/2026c/wiser_working/3rdcohort_Spike_2026_3.sqlite`, `…_3_2.sqlite`, `…_3_3.sqlite`, `…_3_4.sqlite` | copies of the field-PC DBs; originals `D:/Wiser/data/` on the field PC, archive `Q:/hc997/SocialFieldRat2026/3rd_rat/wiser/data/` |
| Per-tag 5-s bin medians (used for the outside-count) | `$OUT/2026c/wiser_working/c3_bins5.pkl` | cohort-3 WISER accuracy run (see `cv/cv_field/select_pano_targets.py` docstring) |
| **Default WISER tracks** (V3 for implanted animals, B2 where no IMU) | `$OUT/2026c/wiser_default_tracks/<SFxx>/<YYYYMMDD>.csv.gz` + `index_2026c.csv` + `README.md`; reader `REPO/wiser/src/default_tracks.py` | `wiser/scripts/build_wiser_default_tracks.py` (commit `457a4c9`, 2026-10-04) |
| Full-day fix cache | `$OUT/2026c/wiser_fix_cache/full_<YYYYMMDD>/<label>.csv.gz` | same |
| Per-second head-IMU state + head layer | `$OUT/2026c/imu_seconds_cache/<SFxx>/<YYYYMMDD>.csv.gz` | same |
| House zones (WISER inch frame) | `REPO/wiser/configs/wiser_rois.json` (`house_1`, `house_2`; zone = rectangle + 14 in) | — |
| Tag ↔ animal | `REPO/wiser/configs/rat_identities_2026c.csv` | — |
| Handling windows, release, population change | `REPO/cv/configs/cohort3_handling_windows.json` | — |
| Calm / rain periods | `REPO/wiser/configs/wiser_failure_audit_2026c.json` (`periods`, `weather`) ; weather CSVs `F:/weather_data/` | — |

## E. Camera geometry (used by the planned WISER phase)

| What | Path |
|---|---|
| Per-night pixel corrections, CH01–CH08 | `REPO/results/2026c/cv_field/reports/cv_field_frame_corrections_2026c.csv` (+ `.md`); API `REPO/cv/cv_field/frame_correction.py` → `Corrections("2026c").to_paddock(cam, t, uv_upright, z_mm=60)` |
| Camera calibration (09-24 release, exploratory) | `../Field_2026_Social_Recording/calibration_qc/` (`paddock_map.load()`), audits `AUDIT_CALIBRATION_2026-09-24*.md` there |
| Landmark labels / night chain | `REPO/cv/configs/landmarks/2026c/`, reports `REPO/results/2026c/cv_field/reports/cv_field_landmark_*` |

## F. Cohort-3 pano frames for labelling (not yet labelled)

| What | Path |
|---|---|
| Target times (WISER-stratified) | `$OUT/2026c/cv_field_pano_select_20260929_1143/` (`targets_round0.csv`, `targets_test.csv`, `selection_summary.json`) |
| Round-0 frames, 60 | `REPO/cv/dataset/rat_pano/images/` (gitignored, local only) |
| **Frozen test frames, 40 (night 09-05)** | `REPO/cv/dataset/rat_pano_test/images/` — not to be opened by any model run or used for tuning |

## G. Planned WISER phase (nothing exists yet)

Run folder `$OUT/2026c/cv_field_wiser_assist_p0_<ts>/`, report
`REPO/results/2026c/cv_field/reports/cv_field_wiser_assist_p0_2026c.md`, pointer
`run_manifest_wiser_assist_p0_2026c.json`, code `REPO/cv/cv_field/wiser_assist_p0.py` — see the plan.

## Rules an auditor should hold the work to

The agent never judged images; every visual verdict is the user's. Machine boxes (YOLO, SAM3, WISER projections) are
proposals, never labels. The frozen test night 09-05 and `rat_pano_test/` are untouched. Results are pre-registered;
deviations are dated amendments marked before / after results. Bulk lives under `$OUT`, reports and figures in
`REPO/results/`. Known weak points to check first: v5's S-val scores are optimistic (val frames seconds from training
frames; best epoch chosen on them); S-held CH02 07-04 is circular for v5; YOLO vs WISER per 5-s bin compares a camera
view (≈ 68 % of the paddock) with the whole paddock; the "Long Evans rat" prompt is post hoc.
