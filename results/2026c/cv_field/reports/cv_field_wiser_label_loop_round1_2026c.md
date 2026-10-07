# WISER-guided labelling loop, round 1 — WISER pixel kit + 400-frame package + test set to 100 (2026c, CH01/CH02)

Drivers `cv/cv_field/build_wiser_pixel_kit.py` (part A) and `cv/cv_field/select_label_round1.py` (part B); plan `implementation_plan/2026-10-06-wiser-label-loop.md` (pre-registered, approved 2026-10-06 "做吧"; amendments 1–3 before results: implementation details + the 5-min test spacing, the coordinator's prelabel-txt rule, pool frames ≤ 0.5 s from their target second; amendment 4 after the first package build: the test-extension refill). Generated 2026-10-06 20:20; code `bad7d5ff3de9cfff53438cbed3dd3c80cde2582c+dirty`. The agent did not look at any frame, video or figure; YOLO boxes and WISER positions are proposals, never labels. Part C (the loop in the undergrad's repo) is built separately.

## Outputs

- **Label package** `D:/Field2026_analysis_out/2026c/label_round1_20261006_2015`: 400 training frames (200 per camera) with editable v5 prelabels (391 frames; no `.txt` where v5 found no box ≥ 0.25 — amendment 2: those frames must be opened and saved with `s` even if they stay empty; a frame is reviewed only when its `<stem>.prov.json` exists (saved with `label_frames.py --wiser`); `finalize_negatives` only after `progress.py <pkg>` reports "train READY"), pristine prelabel copies for all and WISER sidecars; **100 test frames** (40 existing + 60 new, no txt, no sidecar); 20 overlap frames; 1776 files in `MANIFEST_sha256.csv` (+ `verify_manifest.py`, `README.md` with the copy-to-Q: steps and the labelling rules).
- **WISER pixel kit** `D:/Field2026_analysis_out/2026c/wiser_pixel_kit_20261006_1952` (`kit.json`, `README.md`, per camera `support.json`, `occluders.json`, 11 night tables, `visibility_mask.npz`, `checks.csv`; `validation.csv`).
- **Pool** `D:/Field2026_analysis_out/2026c/label_round1_pool_20261006_1840`: 3000 frames (PNG), `pool_detections.csv.gz` (v5, conf ≥ 0.05), `pool_embeddings.npz` (DINOv3), `pool_targets.csv`, `pool_frames.csv`, `video_index/` — never re-grabbed.

## Camera-night map validation (plan A2)

| camera | night | rain mm | correction | pool frames | v5 boxes ≥ 0.5 mapped | pairs | median (in) | within-14 | control | verdict |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| CH01 | 2026-08-30 | 0.0 | ok | 266 | 506 | 220 | 7.85 | 0.403 | 0.016 | **pass** |
| CH02 | 2026-08-30 | 0.0 | ok | 264 | 867 | 253 | 9.07 | 0.227 | 0.013 | **pass** |
| CH01 | 2026-08-31 | 2.5 | ok | 138 | 242 | 118 | 5.87 | 0.463 | 0.021 | **pass** |
| CH02 | 2026-08-31 | 2.5 | ok | 132 | 320 | 79 | 6.38 | 0.219 | 0.003 | **pass** |
| CH01 | 2026-09-01 | 0.0 | ok | 106 | 136 | 59 | 17.99 | 0.088 | 0.000 | **fail** |
| CH02 | 2026-09-01 | 0.0 | ok | 120 | 245 | 89 | 17.96 | 0.086 | 0.008 | **fail** |
| CH01 | 2026-09-02 | 0.2 | ok | 135 | 214 | 92 | 13.74 | 0.243 | 0.023 | **pass** |
| CH02 | 2026-09-02 | 0.2 | night | 136 | 231 | 96 | 15.47 | 0.195 | 0.022 | **fail** |
| CH01 | 2026-09-03 | 18.4 | ok | 122 | 237 | 81 | 6.17 | 0.316 | 0.017 | **pass** |
| CH02 | 2026-09-03 | 18.4 | ok | 109 | 240 | 105 | 6.02 | 0.421 | 0.025 | **pass** |
| CH01 | 2026-09-04 | 0.0 | night | 102 | 135 | 90 | 3.82 | 0.689 | 0.015 | **pass** |
| CH02 | 2026-09-04 | 0.0 | ok | 102 | 227 | 105 | 5.38 | 0.436 | 0.013 | **pass** |
| CH01 | 2026-09-06 | 0.0 | ok | 131 | 199 | 89 | 4.33 | 0.442 | 0.020 | **pass** |
| CH02 | 2026-09-06 | 0.0 | ok | 128 | 243 | 97 | 5.40 | 0.379 | 0.021 | **pass** |
| CH01 | 2026-09-07 | 0.0 | night | 130 | 136 | 89 | 5.77 | 0.640 | 0.029 | **pass** |
| CH02 | 2026-09-07 | 0.0 | ok | 124 | 254 | 99 | 7.93 | 0.327 | 0.039 | **pass** |
| CH01 | 2026-09-08 | 0.0 | ok | 134 | 133 | 103 | 3.62 | 0.767 | 0.053 | **pass** |
| CH02 | 2026-09-08 | 0.0 | ok | 138 | 288 | 104 | 3.82 | 0.347 | 0.017 | **pass** |
| CH01 | 2026-09-09 | 7.2 | ok | 125 | 256 | 72 | 5.52 | 0.262 | 0.012 | **pass** |
| CH02 | 2026-09-09 | 7.2 | ok | 129 | 423 | 126 | 7.24 | 0.267 | 0.014 | **pass** |
| CH01 | 2026-09-10 | 0.0 | night | 111 | 115 | 68 | 4.15 | 0.583 | 0.000 | **pass** |
| CH02 | 2026-09-10 | 0.0 | ok | 111 | 141 | 105 | 5.14 | 0.730 | 0.028 | **pass** |

19 of 22 camera-nights pass; failing: CH01 2026-09-01 (fail), CH02 2026-09-01 (fail), CH02 2026-09-02 (fail). A failing camera-night keeps its frames for labelling but gets `map_validated = 0`: no WISER circles, no suspected-miss / social / hard-negative quota.

## Pool (plan B2)

| camera | eligible night-seconds | targets | frames ok | failed | usable (≤ 0.5 s, amendment 3) | boxes ≥ 0.05 | frames with a box ≥ 0.25 | median grab s (per worker) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CH01 | 286575 | 1500 | 1500 | 0 | 1500 | 10775 | 1427 | 3.21 |
| CH02 | 286325 | 1500 | 1500 | 0 | 1493 | 12083 | 1481 | 2.79 |

Stratified draw by stratum (tagged animals outside the houses / motion of the most active of them):

| stratum | CH01 eligible s | CH01 drawn | CH02 eligible s | CH02 drawn |
|---|---:|---:|---:|---:|
| 0 / none | 26660 | 172 | 26664 | 172 |
| 1-2 / still | 8088 | 172 | 8088 | 172 |
| 1-2 / active | 64561 | 172 | 64683 | 172 |
| 1-2 / locomoting | 31254 | 171 | 31259 | 171 |
| >=3 / still | 720 | 171 | 720 | 171 |
| >=3 / active | 55252 | 171 | 55162 | 171 |
| >=3 / locomoting | 100040 | 171 | 99749 | 171 |

Grab: the grab_frames.py command (CPU, exact seek, transpose=2), frame = the first sample with PTS ≥ the target second; frame time − target: median 0.029 s, max 15.152 s. Identity check vs `grab_frames.grab` on CH01 2026-08-30 21:02:51: max pixel difference 0. Pool wall time 71 min over its runs (a 6-frame check, a run stopped at 1 873 frames by a race on the video-index cache — fixed, resumed — and the resume); last run 25 min; 4 grab workers; kit build 11 min; selection + package 5 min.

## Selection (plan B3–B4)

Clip-review rule: no export in cv/configs/c1yolo_review_2026c at selection time -> 60, no fixed-spot negatives → suspected-miss quota **60**. Fixed-spot negatives: none (no verdict exported).

| quota | CH01 filled / quota (candidates) | CH02 filled / quota (candidates) |
|---|---:|---:|
| visible_suspected_miss | 60 / 60 (227) | 60 / 60 (196) |
| social | 30 / 30 (131) | 30 / 30 (120) |
| hard_negative | 20 / 20 (85) | 20 / 20 (65) |
| wiser_strata | 50 / 50 (1500) | 50 / 50 (1493) |
| dino_diversity | 20 / 20 (1500) | 20 / 20 (1493) |
| uniform_random | 20 / 20 (1500) | 20 / 20 (1493) |

Frames per night (selected, train):

| night | CH01 | CH02 | rain mm |
|---|---:|---:|---:|
| 2026-08-30 | 25 | 25 | 0.0 |
| 2026-08-31 | 21 | 24 | 2.5 |
| 2026-09-01 | 13 | 15 | 0.0 |
| 2026-09-02 | 25 | 16 | 0.2 |
| 2026-09-03 | 16 | 14 | 18.4 |
| 2026-09-04 | 14 | 19 | 0.0 |
| 2026-09-06 | 19 | 19 | 0.0 |
| 2026-09-07 | 17 | 17 | 0.0 |
| 2026-09-08 | 20 | 19 | 0.0 |
| 2026-09-09 | 16 | 17 | 7.2 |
| 2026-09-10 | 14 | 15 | 0.0 |

Selected frames with ≥ 1 v5 box ≥ 0.25: 391 of 400; with ≥ 1 suspected miss: 145; map-validated: 356. DINOv3 k-means (k = 20) cluster sizes: CH01 [60, 99, 37, 66, 130, 75, 125, 90, 54, 90, 46, 74, 94, 136, 21, 78, 44, 64, 59, 58]; CH02 [64, 101, 33, 132, 63, 81, 138, 112, 85, 111, 46, 37, 69, 133, 39, 43, 66, 54, 19, 67].

## Test set to 100 (plan B5, amendment 1)

Existing 40 (`cv/dataset/rat_pano_test/images/`, `.jpg`) copied unchanged (sha256 checked) + 60 new (night 09-05, `select_pano_targets` stratified test rule: zero / few / many tagged animals outside = 0.2 / 0.4 / 0.4, ≥ 5 min from each other and from that camera's existing frames; the rule drew CH01 29, CH02 29 — 09-05 has only 27 min of 'zero' bins, too few for 6 more spaced frames next to the existing ones — and amendment 4 drew the shortfall from the other strata). No model ran on any test frame; no prelabel, no WISER sidecar. Minimum spacing per camera in the final test set (s): CH01 300, CH02 300. Strata of the new frames: CH01 {'many': 13, 'few': 12, 'zero': 5}; CH02 {'many': 13, 'few': 12, 'zero': 5}.

## Definitions

Units: paddock / WISER positions in inches; pixels = upright pano pixels (7680 × 2160); times = field-PC local seconds. Night D = D 21:00 → D+1 04:20. $j$ = animal (SF07–SF12), $t$ = whole second.

### Kit pixel ($\mathbf u_j(t)$) and radius ($r_j(t)$)
$$ \mathbf u_j(t)=A_t\big(F^{-1}(T(\mathbf w_j(t)),\,z{=}60\,\mathrm{mm})\big),\qquad r_j(t)=14\sqrt{|\det J|},\ J=\partial\mathbf u/\partial\mathbf p $$ **Text:** WISER position $\mathbf w_j$ (default track, linear between clean fixes ≤ 5 s apart) → paddock by the accepted map $T$ → 09-18 calibration pixel by the inverse of the rev g camera $F$ at 60 mm above the local ground → the night's pixel by the frame-correction affine $A_t$ (interpolated per second). $r$ = radius (px) of the circle with the area of the 14-in ring's image. Units: px.

### Hidden share ($h$) and robust hidden ($h^{rob}$)
$$ h(\mathbf p)=\tfrac19\sum_{k=1}^{9}\mathbb 1[\text{segment camera}\to\mathbf q_k(\mathbf p)\ \text{meets an occluder}],\quad h^{rob}(\mathbf p)=\max\big(h(\mathbf p),\max_{a=0..7}h(\mathbf p+7(\cos\tfrac{2\pi a}{8},\sin\tfrac{2\pi a}{8}))\big) $$ **Text:** share of a rat's 9 sample points (30/60/90 mm × −40/0/+40 mm across the line of sight) hidden by a pole or house from this camera, looked up in the 2-in visibility mask; robust = also at 8 positions 7 in away (clamped 1 in inside the paddock). Range [0, 1].

### Map validation per camera-night
$$ \tilde r=\operatorname{median}_{matched}\lVert\mathbf p_i-T(\mathbf w_{\pi(i)})\rVert,\quad f_{14}=\frac1{|I|}\sum_i\mathbb 1[\min_j\lVert\mathbf p_i-T(\mathbf w_j)\rVert\le14],\quad \text{pass}\iff\tilde r\le14\wedge f_{14}\ge2f^{+1h}_{14} $$ **Text:** $\mathbf p_i$ = paddock position of a v5 box centre (conf ≥ 0.5) of a pool frame of that camera-night (`Corrections.to_paddock`, z = 60 mm); $\pi$ = per-frame Hungarian assignment to the animals outside the house zones (gate 30 in); $f^{+1h}_{14}$ = the same share with WISER one hour later. Needs ≥ 20 mapped boxes and ≥ 10 pairs. Units: in; shares in [0, 1].

### Frame scores
$$ \mathrm{miss}_j=\mathbb 1[\mathrm{tr}_j\wedge\neg\mathrm{house}_j\wedge\mathrm{sup}_j\wedge h^{rob}_j=0\wedge\min_b\lVert\mathbf p_b-\mathbf p_j\rVert>20],\quad \mathrm{social}=\mathbb 1[\exists j\ne k\in V:\lVert\mathbf p_j-\mathbf p_k\rVert\le20] $$ **Text:** a visible suspected miss = a tracked animal outside the house zones, in the camera's support, robustly unhidden, with no v5 box (conf ≥ 0.25) whose centre maps within 20 in (a box outside the support counts as near when its pixel is within $20/14\cdot r_j$). $V$ = animals tracked, in support, outside the house zones. Hard negative = all six tracked and all in house zones. Only on map-validated camera-nights; misses not on rain nights (≥ 1 mm 21:00–04:20: 08-31, 09-03, 09-09). Merged event = per animal, a run of seconds in which it is tracked, outside, in support and robustly unhidden (gaps ≤ 5 s bridged); a frame's miss animals join their runs; ≤ 1 frame per event.

### Stratum
$$ n_{out}(t)=\sum_j\mathbb 1[\mathrm{tr}_j\wedge\neg\mathrm{house}_j],\quad \mathrm{stratum}=(\{0,1\text{–}2,\ge3\}(n_{out}),\max_{j\,out}\mathrm{motion}_j) $$ **Text:** tagged animals outside the house zones (paddock-wide, WISER frame) and the most active state among them (still < active < locomoting; none when $n_{out}=0$): 7 strata.

## Caveats

- WISER is a lower bound on the animals present when `all_tracked` = 0 (SF12 night 08-30, SF11 09-02 00:03 → 08:20 and from 09-07 06:10:45). Before the 09-03 13:59 WISER restart the WISER frame was shifted 7–18 in; the validation decides those nights.
- The suspected-miss score is a proposal for the labeller's eyes, not a measured miss rate: grass occlusion is not modelled, the box→paddock map assumes z = 60 mm, WISER is ± 3–7 in.
- The +1 h control reads WISER after 04:20 for the last hour; operator rounds there (e.g. 08-31 03:30) remove fixes and make the control easier to beat on that night.

## Rerun

```
C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/select_label_round1.py --pool
C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/build_wiser_pixel_kit.py --build --pool D:/Field2026_analysis_out/2026c/label_round1_pool_20261006_1840
C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/select_label_round1.py --select --pool D:/Field2026_analysis_out/2026c/label_round1_pool_20261006_1840 --kit D:/Field2026_analysis_out/2026c/wiser_pixel_kit_20261006_1952
```
