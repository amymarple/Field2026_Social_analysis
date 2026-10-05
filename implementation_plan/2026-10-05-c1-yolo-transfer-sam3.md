# Cohort-1 pano rat detector (`social-field-rat`): backup, cohort-3 night transfer test, SAM3 zero-shot vs YOLO

Date: 2026-10-05. Status: **PLANNED** — approved by the user 2026-10-05 (answers: test video = "cohort 3 CH01 夜间 1
小时"; SAM3 = "有标注的定量对比"; backup = "备份到本地"). Pre-registered before any result; amendments are dated and
marked *before* or *after results*.

## Why

The sibling folder `D:\Documents\GitHub\social-field-rat` (another lab member's work, last edited 2026-09-14) holds the
only CH01/CH02 **panorama** rat detector and the only CH01/CH02 labels of the project. This repo's cohort-3 plan
(`2026-09-28-cohort3-ch0102-yolo-pilot.md`) assumed CH01/CH02 start from zero labels. The user asked what the YOLO
there achieved, to test it on one video, and how far it goes against SAM3, and said the model and the labelled frames
are what matters most.

## Inventory (read 2026-10-05; facts, do not re-derive)

- The folder is **not a working git repository**: `.git/` holds only `refs/`; `data/` and `outputs/` were gitignored
  anyway. Labels and weights exist in this one place (plus `labels_snapshot_20260914.zip`, 772 KB, labels only).
- **Labels** (YOLO txt, one class `rat`, frames upright landscape 7680 × 2160 = raw portrait rotated 90° ccw, the same
  orientation as `cv/cv_field/grab_frames.py`), all cohort 1 (2026a), all in the 21:00–22:00 clip of the day:
  CH01 06-30 287 frames (853 boxes), CH01 07-04 150 (302), CH01 07-07 150 (256), CH02 06-30 150 (187; colour dusk),
  CH02 07-06 150 (93 boxes, 86 empty; IR night) = 887 frames, 1 692 boxes, 168 empty → `labeled_yolo/` 710 train /
  177 val (random per-folder split, seed 0). Not in the dataset, partly labelled: CH02 07-04 (60 of 75 frames
  labelled, all with boxes), CH01 07-05 (33 of 75). A rat is ≈ 65 × 65 px at native resolution.
- **Models** (`computer_vision/outputs/runs/*/weights/best.pt`, all imgsz 1280, 50 epochs): v1 `rat_s_1280_e50_v1`,
  v2 `rat_s_v2`, v3 `rat_s_v3` (yolo11s), v4 `rat_m_v4`, **v5 `rat_m_v5`** (yolo11m, 887 frames; the author's
  current best). The author's per-group validation (`models.md`), v5: CH01 trained days mAP50 .824 (R .774), CH01 07-07
  .608, CH02 colour .455, CH02 IR night .585 (R .545); "colour day vs IR night is a domain split"; CH01 IR night never
  trained.
- Weaknesses noted by us (to be shown, not assumed): imgsz 1280 on a 7680-wide frame shrinks a rat to ≈ 11 px; val
  frames come from the same hour as train frames (seconds apart), so the author's val scores are probably optimistic;
  the v5 tracking of CH01 07-04 21:00–22:00 (`outputs/tracks/model_v5/track-2/tracks.csv`) has 2 045 track IDs for
  ≤ 5 rats and no detection in 18 % of frames → detection only, no identity.
- **SAM3**: `sam3.pt` (3.45 GB) is in the HF cache (`~/.cache/huggingface/hub/models--facebook--sam3/snapshots/
  3c879f39826c281e95690f02c7821c4de09afae7/sam3.pt`, downloaded 2026-10-01); the `cv` env's ultralytics 8.4.93 has
  `ultralytics.models.sam.SAM3SemanticPredictor` (text prompts). Neither repo has used it.
- Cohort 3: 100 CH01/CH02 night frames already grabbed and unlabelled (`cv/dataset/rat_pano/` 60 round-0,
  `cv/dataset/rat_pano_test/` 40 on the frozen test night 09-05; `$OUT/2026c/cv_field_pano_select_20260929_1143/`).

## Rules for this work

- The agent **never judges images**; every visual judgement is the user's. Machine-made boxes (YOLO or SAM3) are
  proposals, never labels.
- Read-only on `social-field-rat`, on `F:\3rd_rat` and on the WISER inputs. No training, no fine-tuning, no threshold
  tuned on any frame that is scored.
- The frozen cohort-3 test night **09-05** (21:00 → 09-06 04:20) and `cv/dataset/rat_pano_test/` are not touched.
- Save intermediates once (detections at a low confidence floor, SAM3 raw outputs), re-score from the caches.

## Step 0 — backup (first; nothing else starts before it verifies)

Copy, preserving relative paths, from `D:\Documents\GitHub\social-field-rat\` to
`D:\Field2026_analysis_out\2026a\social_field_rat_backup_20261005\`:
`computer_vision/data/**` (≈ 48 GB: `raw_frames`, the five `frames_*` folders incl. `manifest.csv`/`preview/`,
`labeled_yolo/`, `labels_backup_20260914/`, `labels_snapshot_20260914.zip`); `computer_vision/outputs/runs/**`
(≈ 287 MB: weights `best.pt`/`last.pt`, `args.yaml`, `results.csv`, curves, `_resolved_data.yaml`); the two
`tracks.csv`; all `*.md`, `*.yml`, `*.yaml`, `*.py`, `*.ipynb`, `*.slurm` outside `.venv`. Excluded: `.venv/`,
`__pycache__/`, the prediction / tracking videos (`*.avi`, `trails.mp4`, ≈ 49 GB, regenerable).
Write `MANIFEST_sha256.csv` (relpath, bytes, mtime, sha256 of the source) and `README.md` (source, date, inclusions,
exclusions, the broken `.git`). Verify by re-hashing every destination file against the manifest; the step passes
only with 0 mismatches and 0 missing. Never write into the source.

## Step 1 — SAM3 zero-shot vs YOLO v5 on labelled cohort-1 frames (ground truth, no human judging)

**Frame sets.**
- **S-val** = the 177 `labeled_yolo/images/val` frames (v5 never trained on them, but they sit seconds from training
  frames → v5-favourable).
- **S-held** = labelled frames of the two never-trained clips: CH02 07-04 (60) + CH01 07-05 (33 labelled frames,
  empty files counted as negatives). Selected by an earlier model as uncertain → hard for YOLO; reported separately.
- **Groups** (both sets): camera × date, and lighting per frame decided numerically (IR = mean |R−G| + |G−B| below a
  threshold fixed from the CH02 07-06 vs 06-30 distributions before any scoring and reported).

**Detectors.**
- YOLO v5 `rat_m_v5/best.pt` at imgsz 1280 (as trained) — primary; sensitivity imgsz 2560 (inference only).
  Detections cached at conf ≥ 0.01.
- SAM3 `SAM3SemanticPredictor`, text prompt `"rat"`, on **tiles of 1008 × 1008 native pixels** (≥ 20 % overlap, so a
  rat keeps its ≈ 65 px), boxes = mask bounding boxes mapped back to the frame, cross-tile duplicates merged by NMS
  (IoU 0.5); score = SAM3's presence × detection score; cached at score ≥ 0.01. Sensitivities: tiles of 2016 px
  resized to 1008 (rat ≈ 32 px); prompt `"animal"`. fp16 if it runs, else fp32 (reported).
- Also reported, no extra inference: the author's numbers from `models.md` for orientation only.

**Matching and metrics (pre-registered).** Ground truth = the label boxes. Primary match = **centre match**
(a prediction matches an unmatched GT box if its centre lies inside the GT box grown by 25 % per side; greedy by
score) — the cv_field rule, robust to box conventions (labels box the body, not the tail). Secondary = IoU ≥ 0.5.
Per group and overall: AP (all-point interpolated), recall at precision ≥ 0.8, max F1 and its P/R, the
count-error distribution per frame at the max-F1 threshold, and empty-frame false-positive rate. 95 % CIs by bootstrap
over frames (1 000 resamples). No threshold is tuned on S-val or S-held beyond reporting these threshold-free or
argmax summaries.

**Read-out (descriptive; the user decides any use).** "How far YOLO goes" = per group, AP and recall@P≥0.8 of v5 vs
SAM3 with CIs, the IR-night groups singled out. A follow-up (SAM3 as a labelling aid for cohort 3, or a
detector-plus-SAM3 combination) is only proposed, never started, from this step.

## Step 2 — YOLO v5 on one cohort-3 CH01 night hour

**Choice of hour (rule fixed now).** Calm nights per `wiser/configs/wiser_failure_audit_2026c.json` minus the test
night: 09-06, 09-07, 09-08. Prefer **night 09-06** (all six implanted animals tagged; SF11's tag came off 09-07 06:10).
Candidate files = complete hourly CH01 files `F:\3rd_rat\2026-09-06\CH01\CH01_2026-09-06_2[1-3]-*_to_*.mp4` and
`F:\3rd_rat\2026-09-07\CH01\CH01_2026-09-07_0[0-3]-*_to_*.mp4` with no overlap with
`cv/configs/cohort3_handling_windows.json`; pick the one with the **highest mean number of WISER-tagged animals outside
the houses** (5-s bins, the `select_pano_targets.py` zone rule on `c3_bins5.pkl`); ties → earlier hour. If the
F: copy of that file is missing or truncated, take the next one and say so.

**Run.** Every frame of the hour (≈ 72 000 at ≈ 20 fps), decoded sequentially (NVDEC if it works, CPU otherwise),
rotated 90° ccw to the upright 7680 × 2160 pano exactly as `grab_frames.py` (checked numerically: one frame from both
paths must be pixel-identical or the difference reported), YOLO v5 at imgsz 1280, conf floor 0.05, all boxes cached.
Time of a frame = file-name start + PTS (field-PC time, start offset caveat ≤ ~1 min as for every stream).

**Outputs.**
- Cache `$OUT/2026c/cv_field_c1yolo_video_<ts>/detections.csv.gz` (frame, pts_s, t_pc, x1, y1, x2, y2, conf; upright
  pano px) + `frames.csv.gz` (frame, pts_s, decoded ok) + run JSON (file, sha of weights, versions, runtime).
- Per second: detection count at conf 0.25 / 0.5 (median over the second's frames) and max conf.
- Per 5-s bin: YOLO count (median of per-frame counts, conf 0.25) vs the WISER count of tagged animals outside the
  houses (lower bound for what CH01 can see: CH01 covers ≈ 68 % of the paddock, and an animal in the field can be out of
  view or under grass) → table of YOLO count − WISER count, Spearman ρ, fraction of bins with YOLO = 0 while WISER ≥ 1
  and with YOLO > WISER. **Not an accuracy number** — no ground truth here; it is a plausibility check for the user.
- **Review video for the user**: the 10-min window of that hour with the highest mean WISER outside-count, every frame,
  boxes ≥ 0.25 drawn with confidence, frame time and the WISER outside-count burned in, scaled to 3840 × 1080, H.264,
  20 fps → `<run>/review_10min.mp4`. The agent does not look at it.

## Reports, code, pointers

- Code (new, `cv/cv_field/`, each with `--selftest` on synthetic data): `backup_social_field_rat.py` (step 0),
  `sam3_vs_yolo_c1.py` (step 1), `c1_yolo_video_test.py` (step 2). Run in the `cv` env
  (`C:\Users\Cornell\.conda\envs\cv\python.exe`, `PYTHONIOENCODING=utf-8`).
- Reports: `results/2026a/cv_field/reports/cv_field_sam3_vs_yolo_c1_2026a.md` (+ figures in
  `results/2026a/cv_field/figures/sam3_vs_yolo_c1/`, pointer `run_manifest_sam3_vs_yolo_c1_2026a.json`) and
  `results/2026c/cv_field/reports/cv_field_c1yolo_video_2026c.md` (+ pointer `run_manifest_c1yolo_video_2026c.json`).
- Afterwards: `change_log/2026-10-05-c1-yolo-transfer-sam3.md`, both index READMEs, CLAUDE.md code map (`cv_field`
  section: the backup location, the two drivers, that CH01/CH02 cohort-1 labels exist), `cv/cv_field/HANDOFF.md` line.

## Cost

Backup ≈ 48 GB copy + hash (~15–25 min). Step 1: SAM3 ≈ 30 tiles × 270 frames (+ sensitivities) ≈ 30–60 min GPU;
YOLO minutes. Step 2: ≈ 1 h for the hour (decode-bound) + ~5 min for the review video. Sequential on the one GPU.
