# Cohort-1 pano rat detector (`social-field-rat`): backup, cohort-3 night transfer test, SAM3 zero-shot vs YOLO

Date: 2026-10-05. Status: **DONE 2026-10-05** ([change log](../change_log/2026-10-05-c1-yolo-transfer-sam3.md); step 3 added by the user's request, amendments at the end) — approved by the user 2026-10-05 (answers: test video = "cohort 3 CH01 夜间 1
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

## Amendments

- **2026-10-05, before results (step 0).** The backup also takes three things the inclusion list did not name:
  `computer_vision/weights/*.pt` (the four pretrained ultralytics start checkpoints, 71 MB), `.git/refs/**` (3 files that
  name the last commit of the broken repository) and the `.gitkeep` files. Beside the manifest it writes
  `EXCLUDED_files.csv` (every left-out entry with its reason) and `VERIFY.json` (the re-hash result).
- **2026-10-05, before results (step 1; written after the backup verified, before any detector ran on a scored
  frame).** (i) Inputs are read from the verified backup, never the source. (ii) S-held = 60 labelled CH02 07-04 frames
  (the folder's `classes.txt` is not a label) + 33 labelled CH01 07-05 frames, 2 of them empty (negatives). (iii) The
  IR threshold uses all labelled CH02 07-06 and 06-30 frames (train + val): midpoint of the gap if the two chroma sets
  separate, else the cut that misclassifies the fewest reference frames. (iv) SAM3 details fixed from the installed
  ultralytics 8.4.93 source: `imgsz=1008` set explicitly (the default 640 would shrink every tile); score =
  sigmoid(detection logit) × sigmoid(presence logit); ultralytics' own within-tile NMS (IoU 0.7, on decoder boxes) runs
  before the mask boxes are taken; mask = ultralytics' upsampled mask > 0.5; a tile's image features are computed once
  and reused for "rat" and "animal" (checked on one cohort-1 tile: "rat" outputs identical alone and after "animal");
  fp16 runs. (v) One extra SAM3 sensitivity, `sam3_rat_t1008_edge`: the primary tiling with boxes that touch an inner
  tile border dropped before the cross-tile NMS (overlaps 267 / 432 px, so every rat lies whole in some tile) —
  because the plan's NMS alone leaves cut-rat fragments as duplicates. (vi) The max-F1 summary is per group; the
  count error and empty-frame FP rate use ONE cut per detector × set (that set's max-F1 cut, held fixed across its
  groups) and, additionally, the fixed cut 0.25 (the cut step 2 uses). Groups also include camera × lighting.
  Differences YOLO v5@1280 − each SAM3 variant (AP, R@P≥0.8) get paired-bootstrap CIs.
- **2026-10-05 ~17:55, before results (step 1, lighting rule; after the reference chroma values, before any detector
  score).** The first lighting pass showed the premise of rule (iii) false: CH02 07-06 chroma 0.0037 / 0.0076 / 0.0104
  (min / median / max, 8-bit units) and CH02 06-30 0.0068 / 0.0080 / 45.8 — most "colour dusk" 06-30 frames are
  numerically monochrome (neutral chroma planes), so the min-misclassification cut (0.007) fell inside the grey cluster
  and would have split it by encoder noise. The run was stopped during its YOLO phase (no score computed) and the rule
  replaced: thr = the geometric mid-point of the largest gap in log10(max(chroma, 1e-4)) over the pooled reference
  frames (both clips). Reference chroma values are saved (`ref_chroma.csv`); the old rule's cut is reported beside it.
- **2026-10-05, before results (step 2).** (i) A 5-s bin with no located tag has no WISER count (missing, not 0); the
  hour's mean outside-count is over the bins present, with their coverage reported. (ii) The 10-min review video is
  rendered after the detection pass, from a second, seeked decode of the window, with the cached detections joined by
  PTS, and burns in the frame's YOLO count (boxes ≥ 0.25) as well as the time and the WISER count — the same renderer
  as the step-3 clips. (iii) YOLO runs fp32 as in step 1.
- **2026-10-05 ~18:05, before results (step 2, decode path).** Benchmarks on the chosen-candidate file (no detection
  run yet): ffmpeg CLI decode alone ≈ 140 fps and decode + transpose + bgr24 ≈ 90 fps (`-f null`), but the
  grab_frames-style ffmpeg → pipe → Python path delivers only ≈ 8 fps (CPU) for 50-MB upright frames — the pipe, not the
  decoder, is the bound, so NVDEC cannot help; in-process PyAV (libavcodec, frame threads) with the swscale bgr24
  conversion + 90° ccw rotation in 8 threads gives ≈ 60 fps and was pixel-identical (max |diff| 0) to `grab_frames.grab`
  on a test frame. The pass therefore decodes sequentially with PyAV (CPU); PTS = frame.pts × time_base; the
  identity check against `grab_frames.grab` (CPU, exact) is still made on one frame of the run, and the pipe benchmarks
  (CPU and NVDEC) are recorded in `run.json`. The renderer also decodes with PyAV (seek to a keyframe ≥ 3 s before the
  window, frames kept by PTS) and downsizes with OpenCV INTER_AREA.
- **2026-10-05, before results — NEW step 3: labelled review clips for the user** (user request 2026-10-05: "最后给我做几个
  labelled clips 我要人工看"). Fixed now, before any step-2 result exists. From the step-2 hour, 6 clips of 60 s
  (= 12 consecutive 5-s bins on the WISER bin grid, every frame), rendered like `review_10min.mp4` (YOLO v5 boxes with
  conf ≥ 0.25 and their confidence; field-PC frame time, WISER outside-count and YOLO count burned in on every frame;
  3840 × 1080, H.264, 20 fps). Window eligibility: all 12 bins have ≥ 1 decoded frame and a WISER count. Per-bin YOLO
  = median of the per-frame counts at conf 0.25; per-bin WISER = tagged animals outside the houses. Windows may not
  overlap each other or the 10-min window; they are picked in the order below, each from the windows still free; ties
  → earlier start. (a) Two "agree-many": among windows with mean |YOLO − WISER| ≤ 1, the highest mean WISER.
  (b) One "wiser-zero": WISER = 0 in all 12 bins, the highest mean YOLO (candidate false positives, or animals at a
  house door). (c) One "yolo-miss": the most bins with YOLO = 0 while WISER ≥ 2 (needs ≥ 1 such bin). (d) One
  "yolo-excess": the most bins with YOLO > WISER + 1 (needs ≥ 1 such bin). (e) One "random": uniform over the free
  eligible windows, `numpy.random.default_rng(0)`. A category with no qualifying window is reported as such, never
  substituted. Output in `<step-2 run>/review_clips/`: `<k>_<category>_<HH-MM-SS>.mp4`, `clips.csv` (file, category,
  start / end field-PC time, frame range, mean WISER, mean YOLO, the selecting rule value), `index.html` embedding all
  clips and the 10-min video with those columns, `review_template.csv` (clip, user_verdict, notes; empty). The agent
  draws no conclusion from the clips; they are for the user's manual review.
- **2026-10-05 ~19:00, after results (step 1, diagnostic only — no metric, set or threshold changed).** Label
  provenance: per set × camera-date, the share of GT boxes near-identical (IoU ≥ 0.95) to a v5 @1280 box with conf
  ≥ 0.10 (`prelabel_frames.py` pre-labels with the newest `best.pt` = v5; `WORKFLOW.md`: pre-label, then correct). It
  is 100 % (71 / 71) for S-held CH02 07-04 — those labels are v5's own boxes, so that group's perfect YOLO score is
  circular — 34 % for CH01 07-05 and 0 % for every S-val clip. Reported in `label_provenance.csv`, a report section and
  the headline (the non-circular held-out clip CH01 07-05 is named there); the pre-registered tables are unchanged.
- **2026-10-05 ~19:25, after results (step 2, two implementation fixes; no detection, table or rule changed).** The
  hour's PTS are arrival times in bursts: 1 825 of the 72 000 consecutive frame pairs are < 1 ms apart (min 0.022 ms).
  (i) The identity check first grabbed at PTS − 1 ms and so got the previous frame (0.37 ms earlier; mean |diff| 3.2);
  redone with the offset at the midpoint to the previous frame's PTS (same frame; result in `identity_check.json`, the
  first attempt kept there). (ii) The renderer joined detections to frames by PTS rounded to 1 ms, which merges 804
  frames; the key is now 1 µs, and the 10-min video (whose first render was stopped part-way) and the clips were
  rendered only after the fix.
- **2026-10-05 ~19:50, after results — two user-approved additions (prompted by the user's review, relayed by the
  coordinator; step-1 and step-2 results already existed).** The user: the 10-min review video "is OK"; the review clips
  show many false negatives and false positives that are "very fixed"; a numeric check of `detections.csv.gz`
  (conf ≥ 0.25, 40-px cells) has cell x 6480–6520 / y 1120–1160 boxed in 37.2 % of frames (+ 11.9 % in the cell to its
  left) and x 3280–3320 / y 600–640 in 33.9 %.
  **A — SAM3 prompt "Long Evans rat" (post-hoc sensitivity, the user's suggestion).** Same 270 frames (S-val 177,
  S-held 93), same matchers, metrics, bootstrap, groups and IR rule; both tilings (1008 native, 2016 → 1008); image
  features once per tile, then the text prompt; raw outputs cached (`sam3_tiles_t1008_ler.csv`,
  `sam3_tiles_t2016_ler.csv`); the cached "rat" / "animal" outputs are reused, not rerun. Reported in a separately
  marked post-hoc section of the step-1 report beside v5 @1280, "rat" and "animal", with one sentence on whether the
  conclusion changes. The pre-registered tables and figures stay as they are.
  **B — fixed-spot diagnostic (cached step-2 detections only; YOLO not rerun)** → `<step-2 run>/fixed_spots/`: per
  40-px cell the fraction of the 72 000 frames with a box centre (conf ≥ 0.25) in it; 8-connected cells ≥ 5 % merged
  into spots, ranked by occupancy, all ≥ 5 % up to 15; per spot occupancy, median conf, median box w × h, centre SD,
  occupancy per minute. Figures for the user only (the agent does not interpret them): a 1920 × 540 locator (median of
  60 frames, one per minute) with spot outlines and numbers, an occupancy heatmap on the same scale, and per spot
  native 400 × 400 crops at the first / middle / last frame with a spot box and one frame without (thin boxes, frame
  time and conf printed); frames via PyAV as in step 2. `index.html` (locator, heatmap, one row per spot with crops,
  numbers, minute raster; a free-text section "where are the consistent misses?"), `fixed_spots.csv`,
  `fixed_spots_review.csv` (spot_id, user_verdict object/rat/unsure, notes; empty), `fn_notes.txt` stub. Driver
  `cv/cv_field/c1_yolo_fixed_spots.py`. No conclusion about what the spots are.
