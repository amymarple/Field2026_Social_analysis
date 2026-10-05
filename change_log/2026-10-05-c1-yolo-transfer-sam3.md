# 2026-10-05 — Cohort-1 pano rat detector (`social-field-rat`): backup, SAM3 zero-shot vs YOLO v5, v5 on a cohort-3 CH01 night hour, review clips

**Plan:** [`implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md`](../implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md)
(approved by the user 2026-10-05; pre-registered in c76af8c before any result; 4 amendments before results, 2 after
results — listed below). **Reports:**
[`results/2026a/cv_field/reports/cv_field_sam3_vs_yolo_c1_2026a.md`](../results/2026a/cv_field/reports/cv_field_sam3_vs_yolo_c1_2026a.md)
(pointer `run_manifest_sam3_vs_yolo_c1_2026a.json`, figures `results/2026a/cv_field/figures/sam3_vs_yolo_c1/`) and
[`results/2026c/cv_field/reports/cv_field_c1yolo_video_2026c.md`](../results/2026c/cv_field/reports/cv_field_c1yolo_video_2026c.md)
(pointer `run_manifest_c1yolo_video_2026c.json`). The agent made no visual judgement: every frame, figure and video is for
the user. Machine boxes are proposals, never labels. No training, no fine-tuning, no threshold tuned on a scored frame; the
frozen cohort-3 test night 09-05 and `cv/dataset/rat_pano_test/` were not touched.

## New code (`cv/cv_field/`, cv env, each `--selftest` on synthetic data → PASS)

| driver | step | self-test |
|---|---|---|
| `backup_social_field_rat.py` | 0: copy + hash + re-verify (`--verify-only` re-checks) | 9 checks (selection rules, source untouched, sha = source bytes, flipped byte + deleted file caught) |
| `sam3_vs_yolo_c1.py` | 1: lighting, YOLO, SAM3 tiles, NMS merge, centre / IoU match, bootstrap scoring, report (`--score-only <run>`) | 21 checks (tilings, matchers, AP 0.8333 case, R@P≥0.8, max F1, weighted bootstrap, threshold rule, mask boxes, inner-edge flag, NMS, end-to-end) |
| `c1_yolo_video_test.py` | 2 + 3: hour choice, PyAV decode + YOLO, tables, review video, rule-chosen clips, `index.html`, report (`--steps detect identity tables media report`, `--hour-only`) | 20 checks (b5 bins, PTS key, hour rule incl. frozen-night refusal, windows, clip rules incl. "no qualifying window", plausibility, decode + identity vs `grab_frames.grab`, per-second / 5-s tables, render frame count, index) |

## Step 0 — backup (verified before anything else ran)

`D:\Field2026_analysis_out\2026a\social_field_rat_backup_20261005\`: **5 469 files, 51 349 119 388 bytes (51.35 GB)**,
re-hashed against `MANIFEST_sha256.csv` (relpath, bytes, mtime, sha256 of the source bytes, rule): **0 mismatches, 0
missing, 0 extra → PASS** (`VERIFY.json`, 17:25; copy + verify 8.7 min). Included: `computer_vision/data/**` (5 301 files,
50.97 GB), `outputs/runs/**` (121 files incl. v1–v5 `best.pt`/`last.pt`), the two `tracks.csv`, docs/code/notebooks (37),
and (amendment) the pretrained start weights, `.git/refs/**` (last commit `869169753634edc1ead263503d23943db1582843`),
`.gitkeep`. Excluded (`EXCLUDED_files.csv`): `.venv/`, `__pycache__/`, 12 prediction / tracking videos (50.67 GB). The
source was only read. v5 `best.pt` sha256 `2d7294f3e29da845c8c6c26a39d427ffbe374274524e2cfd922c0edd51b63360`.

## Step 1 — SAM3 zero-shot vs YOLO v5 on labelled cohort-1 frames

Run `D:\Field2026_analysis_out\2026a\cv_field_sam3_vs_yolo_c1_20261005_1750\`. S-val = 177 `labeled_yolo/val` frames
(344 rats, 34 empty); S-held = CH02 07-04 (60) + CH01 07-05 (33, 2 empty) = 93 frames, 118 rats. SAM3 fp16 on the
RTX 5070 Ti: **8.7 s/frame** for 30 tiles of 1008 px with two prompts ("rat" + "animal", shared image features),
1.9 s/frame for 10 tiles of 2016→1008 ("rat"); YOLO 0.05–0.06 s/frame.

Centre match, AP [95 % bootstrap CI] and recall at precision ≥ 0.8:

| set (frames, rats) | YOLO v5 @1280 | YOLO v5 @2560 | SAM3 "rat" 1008 | SAM3 "rat" 2016→1008 | SAM3 "animal" 1008 |
|---|---|---|---|---|---|
| S-val all (177, 344) | AP 0.83 [0.79, 0.87], R 0.81 | 0.68, R 0.56 | **0.23 [0.18, 0.28], R 0.07** | 0.40, R 0.31 | 0.40, R 0.14 |
| S-val IR (151, 275) | 0.84 [0.80, 0.88], R 0.82 | 0.73 | 0.21 [0.15, 0.26] | 0.43 | 0.42 |
| S-val CH02 07-06 IR night (30, 22) | 0.65 [0.49, 0.82], R 0.59 | 0.43 | 0.01 [0.00, 0.06] | 0.04 | 0.02 |
| S-held all (93, 118) | 0.79 [0.70, 0.87], R 0.78 | 0.40 | 0.04 [0.01, 0.08] | 0.03 | 0.07 |
| S-held CH01 07-05 (33, 47; non-circular) | **0.47 [0.32, 0.66], R 0.38** | 0.40 | 0.02 [0.01, 0.07] | 0.01 | 0.02 |
| S-held CH02 07-04 (60, 71; circular) | 1.00 | – | 0.06 | – | – |

- **Lighting** (amended rule, fixed before scoring): chroma threshold 0.65 (gap 0.0104 → 40.8 between the IR and colour
  reference clusters). 235 of the 270 scored frames are monochrome IR, including most frames of the CH01 clips and of
  CH02 06-30 that `models.md` calls daytime / colour (all clips are 21:00–22:00).
- **Label provenance** (diagnostic, after results): 71 / 71 GT boxes of S-held CH02 07-04 are near-identical (IoU ≥ 0.95)
  to v5 boxes — those labels are v5's own pre-labels, so v5's perfect score there is circular; 34 % for CH01 07-05;
  0 % for every S-val clip.
- YOLO v5 @2560 (inference-only upscaling) is worse than @1280 everywhere. SAM3's empty-frame FP rate at 0.25 is
  0.53 (S-val, "rat"); "animal" puts ≥ 1 box on every empty frame (count MAE at 0.25 ≈ 12). Dropping inner-edge tile
  boxes changes SAM3 AP by ≤ 0.01.
- S-val is v5-favourable (seconds from training frames; best epoch selected on it).

## Step 2 — YOLO v5 on one cohort-3 CH01 night hour (plausibility only; no ground truth)

Hour by the plan's rule: **`F:\3rd_rat\2026-09-06\CH01\CH01_2026-09-06_21-00-00_to_22-00-00.mp4`** (mean WISER outside-
count 4.14 per 5-s bin, all 720 bins, 6 tags; next 23:00 3.24, 01:00 3.24, 03:00 2.66, 02:00 2.56, 00:00 2.24, 22:00 1.81;
no handling overlap, all complete). Run `D:\Field2026_analysis_out\2026c\cv_field_c1yolo_video_20261005_1848\`.

- **Decode** (amendment): in-process PyAV, CPU, 8 conversion threads — the ffmpeg → pipe path is pipe-bound (8.1 fps CPU,
  8.6 fps NVDEC). 72 000 frames, 0 decode errors, PTS monotone; pass **1 702 s = 42.3 fps** (YOLO 95 % of the wall).
- **Pixel identity** with `grab_frames.grab` (ffmpeg CLI, CPU, exact): frame 26 200 **identical (max |diff| 0)**.
- **PTS** are bursty arrival times: 1 825 frame pairs < 1 ms apart → detections joined to frames at 1 µs.
- **Detections:** 423 882 boxes ≥ 0.05, 211 043 ≥ 0.25; 97.4 % of frames have ≥ 1 box at 0.25.
- **Per 5-s bin (721 bins):** mean YOLO count 2.90 vs WISER outside 4.13; YOLO − WISER median −1, mean |·| 1.69;
  **Spearman ρ 0.10**; YOLO = 0 while WISER ≥ 1 in 1.1 % of bins; YOLO > WISER 16.2 %, = 14.6 %, < 69.2 %.
- `review_10min.mp4`: 21:21:50 → 21:31:50 (mean WISER outside 5.23), 11 998 frames, 159 MB, 3840 × 1080 H.264 20 fps.

## Step 3 — labelled review clips (user request 2026-10-05; rule fixed before step-2 results)

`<run>\review_clips\` — `index.html` (all clips + the 10-min video), `clips.csv`, `review_template.csv` (empty verdicts),
`eligible_windows.csv`. Each clip 60 s = 12 bins, every frame, rendered like the 10-min video.

| file | category | field-PC window | frames | mean WISER | mean YOLO | rule value |
|---|---|---|---|---:|---:|---:|
| `1_agree-many_21-41-35.mp4` | agree-many | 21:41:35 → 21:42:35 | 49 894–51 094 | 5.00 | 5.00 | 5.00 |
| `2_agree-many_21-46-35.mp4` | agree-many | 21:46:35 → 21:47:35 | 55 895–57 093 | 5.00 | 4.58 | 5.00 |
| – | wiser-zero | **no qualifying window** (WISER outside ≥ 1 in every bin of the hour) | | | | |
| `4_yolo-miss_21-00-35.mp4` | yolo-miss | 21:00:35 → 21:01:35 | 701–1 900 | 4.00 | 1.00 | 2 bins |
| `5_yolo-excess_21-57-30.mp4` | yolo-excess | 21:57:30 → 21:58:30 | 68 993–70 191 | 3.08 | 6.00 | 12 bins |
| `6_random_21-51-05.mp4` | random | 21:51:05 → 21:52:05 | 61 294–62 493 | 5.00 | 1.46 | index 417 |

## Amendments (all in the plan file)

Before results: (0) backup also takes the start weights, `.git/refs`, `.gitkeep`; (1) step-1 details (backup inputs,
S-held counts, SAM3 imgsz/score/NMS facts, `sam3_rat_t1008_edge`, count/FP cuts, paired differences); (1b) lighting rule
replaced — the first rule assumed CH02 06-30 is colour, but most of its frames are monochrome, so its cut fell inside the
grey cluster (run stopped in its YOLO phase, no score computed); (2) step-2 details (missing WISER bins, renderer); (2b)
decode via PyAV (pipe-bound ffmpeg path); (3) the new step 3 clip rule. After results: (4) label-provenance diagnostic
(no metric changed); (5) identity-check offset and the renderer's PTS join key fixed (the stream has frames < 1 ms apart;
a 1-ms key merged 804 frames) — the videos were rendered after the fix.

## Definitions (headline quantities; full set in both reports)

- **Centre match:** a prediction $p$ matches GT box $g$ iff its centre $c_p \in [x_1^g-0.25w_g,\,x_2^g+0.25w_g]\times[y_1^g-0.25h_g,\,y_2^g+0.25h_g]$;
  greedy by score, nearest unmatched GT centre. Text: is the box on the rat, tolerant of box conventions.
- **AP** $=\sum_k (R_k-R_{k-1})\max_{j\ge k}P_j$ over descending score cuts (all-point). Range [0, 1].
- **R@P≥0.8** $=\max\{R(t):P(t)\ge0.8\}$. Text: share of labelled rats found while ≤ 1 in 5 kept boxes is wrong.
- **Bootstrap CI:** 2.5–97.5 % percentiles over 1 000 frame resamples (seed 0); paired across detectors for differences.
- **Chroma** $C_f=\overline{|R-G|+|G-B|}$ on a 4-px grid (8-bit); IR if $C_f<0.65$ (geometric mid-point of the largest
  log10 gap of the CH02 07-06 + 06-30 reference frames).
- **YOLO count per bin** $Y_b=\operatorname{median}_{k\in b} n_k(0.25)$; **WISER outside-count** $W_b$ = tags located in the
  5-s bin whose median position lies outside both house rectangles grown by 14 in; $\rho$ = Spearman$(Y_b, W_b)$.
  Plausibility, not accuracy: CH01 sees ≈ 68 % of the paddock.

## Not verified

- No human looked at any output yet: the clips, the 10-min video and the figures await the user's review.
- Whether CH01's view of the paddock explains YOLO < WISER (no CH01 field-of-view mask was applied to WISER positions;
  the pixel → paddock correction exists but was not part of this plan).
- Whether the S-held CH01 07-05 labels are complete (they began as v5 pre-labels; 34 % of boxes are v5's own).
