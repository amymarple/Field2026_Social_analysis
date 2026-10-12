# In-box CH07: SAM 3 text-prompt detection, SAM 3 point-prompt masks and a frozen DINOv3 identity probe (2026c)

Driver `cv/cv_field/inbox_sam3_dino_test.py`; plan `implementation_plan/2026-10-11-inbox-sam3-dinov3-test.md` (approved by the user 2026-10-11). Amendment 1 = the Codex review *Yolo_identity*; amendment 2 = implementation details; amendment 3 = a grouping sensitivity. All three were written before any T1–T3 result. Run `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320` (made 2026-10-10T23:20:42, commit `dbe25a959f9cae2ca88f27d11fb66d0b91495a88+dirty`). Truth = the user's **blind** head clicks. The agent never judged an image.

**Scope of the T1 / T2 claims.** A head click proves only that a mask covers that head point. Until the user has scored the blind mask review (below), every T1 / T2 number here is **head-point exclusivity**: one mask per head point, no mask spanning two head points, no mask on no head point. None of them is a claim that SAM 3 gives one-whole-rat masks or usable single-rat boxes.

**Correction (2026-10-12) — the T1 reading below was too strong.**
- **Corrected wording** (Codex *Yolo_identity*, accepted): the pre-registered prompt-and-threshold selection did not
  meet the bar for a stand-alone detector. Low-τ "rat" covered most head points on the exploratory frames and may serve
  as a candidate generator; the quality of whole-rat masks is not yet verified.
- **Why the old reading misled.**
  - The selection rule (pooled F1 over all masks) counts every mask on no head point as a false positive, so it chose
    "hooded rat", a prompt that returns few masks.
  - For "rat" the cache shows test IR X 50.7 % (recall 52 %) at τ 0.03, and 38 / 49 heads with their own mask (5
    missed) on the 10 exploratory IR frames at τ 0.01.
  - Its rat masks score low (mostly 0.01–0.25), so no global threshold separates them from the many other masks.
- **The user** (prompt GUI, 2026-10-12): with "rat" the rats are labelled; the extra masks are mostly garbage.
- **Codex's caution:** a mask on no head point may be a fragment of a rat, not garbage.
- **Follow-up:** plan [`2026-10-12-inbox-sam3-rat-prelabel.md`](../../../../implementation_plan/2026-10-12-inbox-sam3-rat-prelabel.md).
  It has two parts: B = a head-anchored pre-label edit pilot on these seen frames (dev); C = a frozen test on new frames.

## Headline

- **T1 (text prompt; the pre-named primary is the chosen prompt on test IR frames).** The dev choice is P4 "hooded rat" at τ = 0.01 (dev IR F1 0.252). On test IR (28 frames, 138 heads, 15 groups):
  - head-point exclusivity X = 8.0 % [2.1, 16.7]; F1 = 0.109 [0.037, 0.187];
  - recall 9.4 % [2.9, 17.6], precision 13.0 % [5.3, 20.0];
  - merged-mask rate 3.0 % [0.0, 7.1], empty-mask rate 82.0 % [70.8, 93.0];
  - count error -1.36 [-2.52, -0.18] masks per frame.
- **T2 (head point → mask, test IR, 138 heads).**
  - Positive point only (the pre-named primary): exclusivity 95.7 % [90.3, 100.0], merge 4.3 % [0.0, 9.7], own head missed 0.0 % [0.0, 0.0].
  - With negative points at the other heads: exclusivity 99.3 % [97.8, 100.0], merge 0.7 % [0.0, 2.2], own head missed 0.0 % [0.0, 0.0].
  - Difference, negative − positive: 3.6 % [0.0, 7.9]. The negative variant is partly self-validating: its negative points are the very heads the metric checks.
- **T3 (frozen DINOv3 head crop, IR; primary = CLS + logistic regression, 4-in crop, leave-one-group-out, 187 clicks, 20 groups).**
  - Accuracy 50.3 % [42.1, 58.0]; chance 20 %.
  - Best control: head-masked, 26.7 %.
  - Δ vs chance 30.3 % [22.1, 38.0]; Δ vs best control 23.5 % [15.6, 31.1].
  - "DINOv3 carries identity" (engineering gate): **YES**; "a gain of ≥ 15 pp is established": **YES**.
- **T3 cross-day (leave-one-day-out: train 09-09 + 09-10, test 09-11, 68 clicks).**
  - Accuracy 30.9 % [17.1, 45.6]; best control head-masked, 19.1 %.
  - Δ vs best control 11.8 % [-4.3, 25.7].
  - Carries identity across days: **NO**.
- **Blind mask review page for the user:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/mask_review/index.html`. It holds 40 masks with method and score hidden; exports go to `cv/configs/inbox_sam3_mask_review_2026c/`. The agent does not score it.

## Reading (what these numbers do and do not say)

- **T1** (corrected 2026-10-12; see the correction above): the pre-registered selection did not yield a stand-alone
  detector. The F1-chosen "hooded rat" gives only 8.0 % of the test head points a mask of their own. "Rat" at a low τ
  covers about half of them on test IR (X 50.7 %), but among many other masks, and no score threshold removes those.
  As a candidate generator it is untested; plan 2026-10-12 tests it. *(Superseded wording: "SAM 3 text prompts do not
  find the in-box rats zero-shot on whole IR frames.")*
  - Tiling raises head coverage to about 49 %, at the cost of about 10 surplus masks per frame (descriptive).
- **T2:** one head click gives a mask on that head every time (100 %), and the mask rarely spans a second head point (4.3 %).
  - The masks are numerically head-sized (median long side 189 px).
  - Whether they are usable single-rat masks or boxes waits for the user's blind review.
- **T3:** frozen DINOv3 embeddings of 4-in IR head crops separate the five rats well above chance and above every control when whole still episodes are held out: 50.3 % vs 26.7 % for the best control.
  - They do not do so when a whole day is held out: the cross-day difference vs the best control has a CI that includes 0.
  - So the identity signal is shown within the two click days, not as a stable cross-day IR identity.
  - Body-scale (16-in) crops carry none.

## Data and units

- **Clicks:** `cv/configs/inbox_identity_2026c/inbox_identity_2026c_20261010_220725.csv` (sha256 `3233d7b40db88694…`).
  - Blind record = `before_reveal` true, not legacy, with `verdict_first` (the `first_*` columns): 284 clicks. The 10 clicks made after a reveal are not used.
  - Frames without any blind click are dropped: CH07_20260910_141613__ir_p15, CH07_20260910_143243__ir_p15.
  - Unusable segment, from the user's composition statement: CH07_20260910_195004.
- **Frames and heads:** 58 frames (38 IR, 20 colour) with 284 blind heads, all CH07 (house_2). The user states that every clicked frame is complete: every rat in the house was clicked.
- **Scale:** 74.80 px/in, from the clicks run's proper similarity fit. That gives:
  - T3 crop 4 in = 299 px and 16 in = 1197 px;
  - head disc 1.5 in = 112.2 px; pile link 6 in = 449 px.
  - One scale cannot convert piles at different heights, so mask areas are given in px only (amendment 1).

## Still-episode groups (amendment 1 item 2, amendment 3)

- **Join rule:** two consecutive usable segments are one group when both hold over the interval from the last frame of the earlier segment to the colour frame of the later one:
  - the WISER house_2 roster (`box_occupancy_1s.csv.gz`) is the same in every second;
  - every roster animal's head IMU is ok and still in ≥ 90 % of those seconds (a missing or failed IMU counts as not still).
- **Result:** **0 of 19 pairs joined**, so each of the 20 usable segments is its own group.
- **Sensitivity grouping `group_alt` (amendment 3):** animals with no ok IMU second are left out of the rule. It joins 2 pairs, giving 18 groups: the 09-11 14:09 → 14:17 → 14:43 segments, where SF12's IMU is absent all afternoon.

| group | segments | group_alt | day | split | ir_frames | colour_frames | heads |
|---|---|---|---|---|---|---|---|
| G01 | 20260909_191025 | A01 | 2026-09-09 | dev | 2 | 1 | 15 |
| G02 | 20260910_071415 | A02 | 2026-09-10 | dev | 2 | 1 | 15 |
| G03 | 20260910_083742 | A03 | 2026-09-10 | dev | 2 | 1 | 14 |
| G04 | 20260910_091147 | A04 | 2026-09-10 | dev | 2 | 1 | 15 |
| G05 | 20260910_122703 | A05 | 2026-09-10 | dev | 2 | 1 | 15 |
| G06 | 20260910_125142 | A06 | 2026-09-10 | test | 2 | 1 | 15 |
| G07 | 20260910_135131 | A07 | 2026-09-10 | test | 2 | 1 | 15 |
| G08 | 20260910_140227 | A08 | 2026-09-10 | test | 2 | 1 | 15 |
| G09 | 20260910_141613 | A09 | 2026-09-10 | test | 1 | 1 | 10 |
| G10 | 20260910_143243 | A10 | 2026-09-10 | test | 1 | 1 | 10 |
| G11 | 20260910_152307 | A11 | 2026-09-10 | test | 2 | 1 | 15 |
| G12 | 20260910_163056 | A12 | 2026-09-10 | test | 2 | 1 | 15 |
| G13 | 20260910_175935 | A13 | 2026-09-10 | test | 2 | 1 | 15 |
| G14 | 20260911_092822 | A14 | 2026-09-11 | test | 2 | 1 | 11 |
| G15 | 20260911_095409 | A15 | 2026-09-11 | test | 2 | 1 | 14 |
| G16 | 20260911_140955 | A16 | 2026-09-11 | test | 2 | 1 | 15 |
| G17 | 20260911_141758 | A16 | 2026-09-11 | test | 2 | 1 | 15 |
| G18 | 20260911_144345 | A16 | 2026-09-11 | test | 2 | 1 | 15 |
| G19 | 20260911_145024 | A17 | 2026-09-11 | test | 2 | 1 | 15 |
| G20 | 20260911_182803 | A18 | 2026-09-11 | test | 2 | 1 | 15 |

| pair | gap_min | roster_unchanged | min still share (all s) | no IMU | joined | joined_alt |
|---|---|---|---|---|---|---|
| 20260909_191025 → 20260910_071415 | 723.9 | False | – |  | False | False |
| 20260910_071415 → 20260910_083742 | 91.2 | False | – |  | False | False |
| 20260910_083742 → 20260910_091147 | 16.1 | True | 0.87 |  | False | False |
| 20260910_091147 → 20260910_122703 | 194.9 | False | 0.91 |  | False | False |
| 20260910_122703 → 20260910_125142 | 24.2 | True | 0.82 |  | False | False |
| 20260910_125142 → 20260910_135131 | 59.6 | True | 0.81 |  | False | False |
| 20260910_135131 → 20260910_140227 | 10.4 | True | 0.89 |  | False | False |
| 20260910_140227 → 20260910_141613 | 13.5 | True | 0.49 |  | False | False |
| 20260910_141613 → 20260910_143243 | 16.0 | True | 0.04 |  | False | False |
| 20260910_143243 → 20260910_152307 | 50.1 | True | 0.14 |  | False | False |
| 20260910_152307 → 20260910_163056 | 67.5 | False | – |  | False | False |
| 20260910_163056 → 20260910_175935 | 88.2 | True | 0.00 | SF07;SF08;SF09;SF10;SF12 | False | False |
| 20260910_175935 → 20260911_092822 | 930.5 | False | – |  | False | False |
| 20260911_092822 → 20260911_095409 | 25.0 | False | 0.13 |  | False | False |
| 20260911_095409 → 20260911_140955 | 248.9 | False | – |  | False | False |
| 20260911_140955 → 20260911_141758 | 7.8 | True | 0.00 | SF12 | False | True |
| 20260911_141758 → 20260911_144345 | 24.8 | True | 0.00 | SF12 | False | True |
| 20260911_144345 → 20260911_145024 | 6.3 | True | 0.00 | SF12 | False | False |
| 20260911_145024 → 20260911_182803 | 217.5 | False | – |  | False | False |

- **dev** = the groups holding the 5 earliest usable segments (G01, G02, G03, G04, G05).
- **test** = the other 15 groups.
- T3 uses all groups, leave-one-group-out.

## T1 — SAM 3 text-prompt detection

- **Model:** SAM3SemanticPredictor (ultralytics 8.4.93), imgsz 1008 set explicitly, score floor 0.01, within-image NMS 0.7, fp32 on NVIDIA GeForce RTX 5070 Ti.
- **Prompts:** the image features are computed once per frame (or tile), and the four prompts are applied on them.
- **Cache:** raw masks (row-major RLE in bbox crops) in `sam3_t1/whole/` and `sam3_t1/tiled/`.

**Choice on dev IR** (pooled F1; ties → higher τ, then the lower prompt number): P4 "hooded rat", τ = 0.01.

Each prompt at its own dev-best τ, on test IR. This is descriptive; only the chosen prompt is the pre-named primary.

| prompt | τ (dev) | dev F1 | test X [95 % CI] | test F1 [95 % CI] | P | R | merged | empty | masks / heads | count err |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 "rat" | 0.03 | 0.136 | 50.7 % [39.2, 62.2] | 0.138 [0.110, 0.168] | 7.9 % | 52.2 % | 0.3 % | 88.3 % | 906 / 138 | 27.43 |
| P2 "Long Evans rat" | 0.01 | 0.104 | 4.3 % [1.4, 8.0] | 0.045 [0.014, 0.078] | 4.1 % | 5.1 % | 0.6 % | 92.4 % | 171 / 138 | 1.18 |
| P3 "rat with a colorful rectangular implant on its head" | 0.01 | 0.106 | 29.0 % [18.1, 40.6] | 0.229 [0.159, 0.293] | 17.9 % | 31.9 % | 2.0 % | 74.4 % | 246 / 138 | 3.86 |
| P4 "hooded rat" | 0.01 | 0.252 | 8.0 % [2.1, 16.7] | 0.109 [0.037, 0.187] | 13.0 % | 9.4 % | 3.0 % | 82.0 % | 100 / 138 | -1.36 |

- **τ at the grid floor:** the chosen τ = 0.01 is the lowest grid value and equals the cache's score floor, so no lower τ could be evaluated.
- **Chosen setting on dev IR** (reference): X 26.0 %, F1 0.252, P 24.5 %, R 26.0 %.
- **Resampling `group_alt`** (13 test groups): X CI 8.0 % [2.1, 16.8], F1 CI 0.109 [0.038, 0.195].
- **Tiled sensitivity** (2 × 2 tiles of 1344 × 1008 px, cross-tile merge at mask IoU ≥ 0.5):
  - its own dev choice, P3 τ = 0.02: test IR X 48.6 % [40.0, 57.4], F1 0.258 [0.229, 0.285];
  - at the whole-frame choice: X 47.8 % [33.6, 61.6], F1 0.209 [0.167, 0.247].
- **Colour frames** (reported separately, never pooled): the chosen setting on 15 test colour frames gives X 5.6 %, F1 0.052, P 4.8 %, R 5.6 %.

By pile size of the head (test IR, chosen setting; descriptive):

| stratum | n_heads | X | R | covered |
|---|---|---|---|---|
| 1 | 21 | 4.8 % | 4.8 % | 4.8 % |
| 2-3 | 87 | 10.3 % | 12.6 % | 14.9 % |
| 4+ | 30 | 3.3 % | 3.3 % | 3.3 % |

Further tables in the run folder:
- the full sweep (every variant × prompt × τ × domain × split): `t1_sweep.csv`;
- per frame: `t1_frame_metrics.csv.gz`; per head: `t1_head_detail.csv.gz`.

## T2 — SAM 3 point-prompt masks from the head clicks

- **Point prompts are exposed for SAM 3** in ultralytics 8.4.93: `SAM3Predictor` (the interactive predictor, a `SAM2Predictor` subclass) takes `points` / `labels`. The SAM 2.1 fallback was therefore not triggered.
- **Build workaround:** the builder passes `compile=False`, which the ViT trunk treats as a compile mode (`is not None`); that call fails without Triton. The model is built with `compile=None` instead, which changes neither the weights nor the outputs.
- **Settings:** `multimask_output` False (the predictor default) and the default mask threshold.
- **Cache:** raw masks in `sam3_t2/`.

| variant | split | heads | exclusive | merge | own head missed | area px median [p25, p75] | box long side px (median) | box aspect (median) | pair IoU median | pairs IoU > 0.1 | pairs IoU > 0.5 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| + negative points | dev | 50 | 98.0 % | 2.0 % | 0.0 % | 21,342 [18,698, 24,132] | 189 | 1.15 | 0.000 | 0.0 % | 0.0 % |
| positive point | dev | 50 | 94.0 % | 6.0 % | 0.0 % | 19,915 [11,061, 24,374] | 179 | 1.19 | 0.000 | 2.0 % | 1.0 % |
| + negative points | test | 138 | 99.3 % [97.8, 100.0] | 0.7 % [0.0, 2.2] | 0.0 % [0.0, 0.0] | 21,870 [18,479, 24,340] | 190 | 1.13 | 0.000 | 0.4 % | 0.0 % |
| positive point | test | 138 | 95.7 % [90.3, 100.0] | 4.3 % [0.0, 9.7] | 0.0 % [0.0, 0.0] | 20,826 [18,074, 24,410] | 189 | 1.15 | 0.000 | 1.8 % | 0.7 % |

- **Box size (numerical, px):** the median box long side is 189 px and the 95th percentile 309 px (positive point, test). For orientation only, an 8-in rat body spans about 598 px at the house-fit scale; animals higher in a pile sit nearer the camera and appear larger, not smaller. So the masks are numerically head-sized rather than body-sized. Whether a mask covers a whole rat is what the user's blind review decides; this number does not.
- **Resampling `group_alt`:** positive exclusivity CI 95.7 % [89.7, 100.0]; negative 99.3 % [97.5, 100.0].

By pile size (test; descriptive):

| variant | stratum | n | X | merge | miss_own |
|---|---|---|---|---|---|
| neg | 1 | 21 | 100.0 % | 0.0 % | 0.0 % |
| neg | 2-3 | 87 | 100.0 % | 0.0 % | 0.0 % |
| neg | 4+ | 30 | 96.7 % | 3.3 % | 0.0 % |
| pos | 1 | 21 | 100.0 % | 0.0 % | 0.0 % |
| pos | 2-3 | 87 | 96.6 % | 3.4 % | 0.0 % |
| pos | 4+ | 30 | 90.0 % | 10.0 % | 0.0 % |

Further tables in the run folder:
- per head: `t2_heads.csv` (areas, boxes, predicted mask score);
- pairwise IoU: `t2_pair_iou.csv`.

## T3 — frozen DINOv3 identity probe (IR)

- **Model:** DINOv3 ViT-B/16 (`dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth`, local hub copy).
- **Crops:** centred on the blind click, clipped to the frame and padded with the frame's median grey, resized to 224 (INTER_AREA), ImageNet normalisation.
- **Embeddings:** CLS = `x_norm_clstoken`; mean-patch = the mean of `x_norm_patchtokens`. Cached in `t3_embeddings.npz` (units in `t3_units.csv`).

### Decision table (amendment 1 item 3)

| role | scheme | crop | embedding | classifier | n | accuracy [95 % CI] | (a) u,v | (a) house frame | (b) head-masked | (c) position-matched | Δ chance [CI] | Δ best control [CI] | carries identity | ≥ 15 pp established |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| primary | LOGO | 4 in | CLS | logistic | 187 | 50.3 % [42.1, 58.0] | 23.5 % | 23.5 % | 26.7 % | 20.9 % | 30.3 % [22.1, 38.0] | 23.5 % [15.6, 31.1] | YES | YES |
| primary | LODO | 4 in | CLS | logistic | 68 | 30.9 % [17.1, 45.6] | 13.2 % | 13.2 % | 19.1 % | 14.7 % | 10.9 % [-2.9, 25.6] | 11.8 % [-4.3, 25.7] | no | no |
| secondary | LOGO | 4 in | CLS | nearest centroid | 187 | 36.4 % [27.5, 45.8] | 23.0 % | 24.1 % | 25.1 % | 24.6 % | 16.4 % [7.5, 25.8] | 11.2 % [4.8, 16.9] | no | no |
| secondary | LOGO | 4 in | mean-patch | logistic | 187 | 60.4 % [51.9, 68.9] | 23.5 % | 23.5 % | 29.9 % | 17.6 % | 40.4 % [31.9, 48.9] | 30.5 % [22.6, 38.7] | YES | YES |
| secondary | LOGO | 4 in | mean-patch | nearest centroid | 187 | 42.8 % [33.9, 52.2] | 23.0 % | 24.1 % | 24.6 % | 20.3 % | 22.8 % [13.9, 32.2] | 18.2 % [10.9, 26.0] | YES | no |
| secondary | LODO | 4 in | CLS | nearest centroid | 68 | 26.5 % [12.1, 42.6] | 14.7 % | 14.7 % | 16.2 % | 16.2 % | 6.5 % [-7.9, 22.6] | 10.3 % [-1.4, 25.0] | no | no |
| secondary | LODO | 4 in | mean-patch | logistic | 68 | 32.4 % [20.0, 41.4] | 13.2 % | 13.2 % | 7.4 % | 16.2 % | 12.4 % [0.0, 21.4] | 16.2 % [4.4, 26.6] | no | no |
| secondary | LODO | 4 in | mean-patch | nearest centroid | 68 | 27.9 % [18.6, 36.8] | 14.7 % | 14.7 % | 22.1 % | 19.1 % | 7.9 % [-1.4, 16.8] | 5.9 % [-2.9, 15.2] | no | no |
| sensitivity (16-in crop) | LOGO | 16 in | CLS | logistic | 187 | 25.1 % [17.8, 32.6] | 23.5 % | 23.5 % | 26.7 % | 20.3 % | 5.1 % [-2.2, 12.6] | -1.6 % [-7.5, 4.6] | no | no |
| sensitivity (16-in crop) | LOGO | 16 in | CLS | nearest centroid | 187 | 30.5 % [22.1, 39.2] | 23.0 % | 24.1 % | 24.6 % | 21.9 % | 10.5 % [2.1, 19.2] | 5.9 % [0.0, 11.4] | no | no |
| sensitivity (16-in crop) | LOGO | 16 in | mean-patch | logistic | 187 | 24.6 % [16.9, 32.3] | 23.5 % | 23.5 % | 33.2 % | 15.5 % | 4.6 % [-3.1, 12.3] | -8.6 % [-15.5, -2.1] | no | no |
| sensitivity (16-in crop) | LOGO | 16 in | mean-patch | nearest centroid | 187 | 26.7 % [21.3, 31.6] | 23.0 % | 24.1 % | 26.2 % | 23.5 % | 6.7 % [1.3, 11.6] | 0.5 % [-2.6, 3.8] | no | no |
| sensitivity (16-in crop) | LODO | 16 in | CLS | logistic | 68 | 13.2 % [4.3, 22.9] | 13.2 % | 13.2 % | 20.6 % | 16.2 % | -6.8 % [-15.7, 2.9] | -7.4 % [-14.3, -1.4] | no | no |
| sensitivity (16-in crop) | LODO | 16 in | CLS | nearest centroid | 68 | 14.7 % [7.1, 22.1] | 14.7 % | 14.7 % | 17.6 % | 17.6 % | -5.3 % [-12.9, 2.1] | -2.9 % [-10.0, 3.1] | no | no |
| sensitivity (16-in crop) | LODO | 16 in | mean-patch | logistic | 68 | 11.8 % [1.5, 23.4] | 13.2 % | 13.2 % | 16.2 % | 14.7 % | -8.2 % [-18.5, 3.4] | -4.4 % [-13.2, 0.0] | no | no |
| sensitivity (16-in crop) | LODO | 16 in | mean-patch | nearest centroid | 68 | 10.3 % [2.9, 19.1] | 14.7 % | 14.7 % | 10.3 % | 19.1 % | -9.7 % [-17.1, -0.9] | -8.8 % [-15.7, -1.4] | no | no |

- Only the first row (primary, LOGO) is the pre-named primary comparison.
- LODO is the cross-day reading of the same configuration.
- The other rows are descriptive. Chance = 1 / 5 = 20 %.
- The best control is the highest of (a)–(c) under the same classifier and embedding.

- **Primary, other measures:** balanced accuracy 50.4 %; majority-class rate of the IR clicks 20.9 %; logistic C chosen per fold: G01:100;G02:100;G03:0.01;G04:0.1;G05:100;G06:1;G07:0.01;G08:0.01;G09:1;G10:1;G11:0.1;G12:1;G13:100;G14:0.01;G15:0.01;G16:10;G17:1;G18:100;G19:10;G20:1.
- **(d) Shuffled labels** (CLS + logistic, LOGO, 20 permutations): mean accuracy 18.1 %, range 11.2 % – 25.7 %.
- **Grouping sensitivity** (amendment 3: leave-one-`group_alt`-out, 18 groups):
  - primary accuracy 46.5 % [38.9, 53.8]; best control head-masked, 24.1 %;
  - Δ vs best control 22.5 % [15.0, 31.0]; carries identity: **YES**.
- **Without the clicks whose label occurs twice on their frame** (183 clicks remain):
  - primary 54.6 %;
  - controls: u,v 21.3 %, house frame 24.0 %, head-masked 25.7 %, position-matched 21.9 %.

Confusion of the primary (IR, LOGO; rows = the user's label):

| true \ predicted | SF07 | SF08 | SF09 | SF10 | SF12 |
|---|---|---|---|---|---|
| SF07 | 18 | 5 | 3 | 2 | 11 |
| SF08 | 5 | 23 | 2 | 2 | 4 |
| SF09 | 6 | 2 | 19 | 8 | 2 |
| SF10 | 4 | 4 | 8 | 17 | 6 |
| SF12 | 9 | 3 | 3 | 4 | 17 |

**Colour crops** (reported separately, never pooled with IR):
- LOGO: CLS + logistic 60.0 % [52.1, 67.0]; best control head-masked, 32.6 %.
- LODO: CLS + logistic 37.5 % [27.3, 48.4]; best control head-masked, 21.9 %.

Further tables in the run folder:
- all configurations (both domains, every feature × classifier × scheme, with the C chosen per fold): `t3_results.csv`;
- predictions: `t3_predictions.csv.gz`; decisions: `t3_decisions.csv`.

## Blind mask review page (amendment 1 item 1) — for the user

- **Page:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/mask_review/index.html`. Open it from disk; it works offline.
- **Sample:** 40 masks from test-group IR frames: T1 14, T2neg 13, T2pos 13.
  - T1 = the chosen prompt and τ on the whole frame.
  - T2pos / T2neg = the two point-prompt variants, on different heads.
- **Strata:** pile size of the mask's head (single linkage of the frame's blind heads at 6 in): T1 1: 1; T1 2-3: 5; T1 4+: 4; T1 none: 4; T2neg 1: 5; T2neg 2-3: 4; T2neg 4+: 4; T2pos 1: 5; T2pos 2-3: 4; T2pos 4+: 4.
- **Display:** items are shuffled and named M01…M40. The page shows the whole frame and a zoomed crop with the mask tinted (a toggle hides the tint). It never shows the method, the score or a head point.
- **Choices:** one whole rat / part of a rat / two or more rats / not a rat, plus notes.
- **Saving:** answers are kept in the browser (localStorage); Export CSV / JSON → `cv/configs/inbox_sam3_mask_review_2026c/`.
- **Key:** item → method, prompt, τ, score, frame and head in `mask_key.csv` in the run folder; not linked from the page.
- **Headless check: PASS** (`mask_review_page_check.json`). It covered: 40 cards; 80 / 80 images loaded; a judgment kept across a reload; export of every item; no method or score words; no network URL.
- **The agent has not looked at any mask.**

## Exploratory prompt sweep (amendment 4; user request, after results)

**EXPLORATORY and descriptive only.** There is no gate, no choice and no claim beyond these 20 frames, and nothing here changes T1–T3. The user asked to try ten frames with rats in view and more prompts (2026-10-11).

- **Frames** (rule fixed before running):
  - per day, one segment per `group_alt` still episode, then 5 evenly spaced daytime segments with an IR frame holding ≥ 3 blind heads;
  - the colour mid-frames of the same segments are a separate block.

| day | segment_id | group | split | ir_frame | ir_heads | colour_frame | colour_heads |
|---|---|---|---|---|---|---|---|
| 2026-09-10 | CH07_20260910_071415 | G02 | dev | CH07_20260910_071415__ir_p06 | 5 | CH07_20260910_071415__colour_mid | 5 |
| 2026-09-10 | CH07_20260910_122703 | G05 | dev | CH07_20260910_122703__ir_p06 | 5 | CH07_20260910_122703__colour_mid | 5 |
| 2026-09-10 | CH07_20260910_140227 | G08 | test | CH07_20260910_140227__ir_p06 | 5 | CH07_20260910_140227__colour_mid | 5 |
| 2026-09-10 | CH07_20260910_143243 | G10 | test | CH07_20260910_143243__ir_p06 | 5 | CH07_20260910_143243__colour_mid | 5 |
| 2026-09-10 | CH07_20260910_175935 | G13 | test | CH07_20260910_175935__ir_p06 | 5 | CH07_20260910_175935__colour_mid | 5 |
| 2026-09-11 | CH07_20260911_092822 | G14 | test | CH07_20260911_092822__ir_p06 | 4 | CH07_20260911_092822__colour_mid | 3 |
| 2026-09-11 | CH07_20260911_095409 | G15 | test | CH07_20260911_095409__ir_p06 | 5 | CH07_20260911_095409__colour_mid | 4 |
| 2026-09-11 | CH07_20260911_141758 | G17 | test | CH07_20260911_141758__ir_p06 | 5 | CH07_20260911_141758__colour_mid | 5 |
| 2026-09-11 | CH07_20260911_145024 | G19 | test | CH07_20260911_145024__ir_p06 | 5 | CH07_20260911_145024__colour_mid | 5 |
| 2026-09-11 | CH07_20260911_182803 | G20 | test | CH07_20260911_182803__ir_p06 | 5 | CH07_20260911_182803__colour_mid | 5 |

- **Prompts:** "rat", "Long Evans rat" and "hooded rat" are read from the T1 cache. The other seven are new, run with the T1 settings (score floor 0.01, imgsz 1008).
- **Determinism check:** "rat" re-run on CH07_20260910_071415__ir_p06 (whole) gave 100 masks vs 100 in the cache; max score difference 0; 100 masks pixel-identical.
- **Matching:** as in T1 (coverage within 15 px).

**Columns:**
- X = heads with their own exclusive mask;
- missed = heads with no mask within 15 px;
- merged = masks over ≥ 2 heads; empty = masks over no head;
- masks = mask count (heads given in the caption).

Pooled over the 10 frames per block.

**IR, τ = 0.01** (49 heads on 10 frames):

| prompt | whole X | whole missed | whole merged | whole empty | whole masks | tiled X | tiled missed | tiled merged | tiled empty | tiled masks |
|---|---|---|---|---|---|---|---|---|---|---|
| rat | 38 (78 %) | 5 | 5 | 684 | 783 | 39 (80 %) | 8 | 8 | 2274 | 2422 |
| Long Evans rat | 4 (8 %) | 45 | 0 | 59 | 64 | 10 (20 %) | 39 | 0 | 169 | 185 |
| hooded rat | 12 (24 %) | 35 | 2 | 46 | 66 | 22 (45 %) | 23 | 3 | 143 | 195 |
| black striped rat | 43 (88 %) | 3 | 5 | 823 | 943 | 41 (84 %) | 3 | 8 | 2553 | 2710 |
| rat with a black stripe on its back | 34 (69 %) | 3 | 20 | 1247 | 1433 | 41 (84 %) | 3 | 7 | 4823 | 5054 |
| black and white rat | 43 (88 %) | 3 | 8 | 973 | 1108 | 44 (90 %) | 2 | 8 | 2562 | 2713 |
| rat with a black head and a white body | 36 (73 %) | 3 | 18 | 375 | 482 | 45 (92 %) | 0 | 9 | 1822 | 2054 |
| rat with an implant on its head | 12 (24 %) | 30 | 7 | 46 | 80 | 29 (59 %) | 12 | 23 | 175 | 292 |
| sleeping rats | 3 (6 %) | 46 | 0 | 41 | 48 | 19 (39 %) | 29 | 1 | 283 | 320 |
| pile of rats | 11 (22 %) | 0 | 51 | 705 | 975 | 22 (45 %) | 0 | 50 | 1653 | 2018 |

**IR, τ = 0.25** (49 heads on 10 frames):

| prompt | whole X | whole missed | whole merged | whole empty | whole masks | tiled X | tiled missed | tiled merged | tiled empty | tiled masks |
|---|---|---|---|---|---|---|---|---|---|---|
| rat | 2 (4 %) | 47 | 0 | 44 | 47 | 2 (4 %) | 47 | 0 | 70 | 72 |
| Long Evans rat | 0 (0 %) | 49 | 0 | 0 | 0 | 0 (0 %) | 49 | 0 | 1 | 1 |
| hooded rat | 0 (0 %) | 49 | 0 | 0 | 0 | 0 (0 %) | 49 | 0 | 0 | 0 |
| black striped rat | 2 (4 %) | 47 | 0 | 44 | 47 | 1 (2 %) | 48 | 0 | 72 | 73 |
| rat with a black stripe on its back | 3 (6 %) | 46 | 0 | 55 | 60 | 3 (6 %) | 46 | 0 | 82 | 86 |
| black and white rat | 3 (6 %) | 46 | 0 | 61 | 65 | 2 (4 %) | 47 | 0 | 77 | 80 |
| rat with a black head and a white body | 1 (2 %) | 48 | 0 | 8 | 9 | 1 (2 %) | 48 | 0 | 39 | 40 |
| rat with an implant on its head | 0 (0 %) | 49 | 0 | 0 | 0 | 0 (0 %) | 49 | 0 | 0 | 0 |
| sleeping rats | 0 (0 %) | 49 | 0 | 0 | 0 | 0 (0 %) | 49 | 0 | 4 | 4 |
| pile of rats | 5 (10 %) | 9 | 14 | 2 | 22 | 6 (12 %) | 21 | 9 | 15 | 31 |

**Colour (separate, never pooled with IR), τ = 0.01** (47 heads on 10 frames):

| prompt | whole X | whole missed | whole merged | whole empty | whole masks | tiled X | tiled missed | tiled merged | tiled empty | tiled masks |
|---|---|---|---|---|---|---|---|---|---|---|
| rat | 38 (81 %) | 6 | 15 | 1004 | 1135 | 41 (87 %) | 2 | 11 | 3393 | 3583 |
| Long Evans rat | 2 (4 %) | 45 | 0 | 61 | 63 | 12 (26 %) | 35 | 0 | 235 | 251 |
| hooded rat | 3 (6 %) | 44 | 0 | 50 | 53 | 16 (34 %) | 29 | 3 | 152 | 181 |
| black striped rat | 24 (51 %) | 22 | 3 | 347 | 394 | 35 (74 %) | 9 | 6 | 1608 | 1706 |
| rat with a black stripe on its back | 35 (74 %) | 7 | 10 | 1251 | 1383 | 38 (81 %) | 7 | 10 | 5102 | 5355 |
| black and white rat | 37 (79 %) | 9 | 4 | 917 | 1007 | 36 (77 %) | 10 | 1 | 2879 | 3002 |
| rat with a black head and a white body | 34 (72 %) | 6 | 16 | 691 | 813 | 39 (83 %) | 5 | 11 | 2331 | 2552 |
| rat with an implant on its head | 20 (43 %) | 20 | 11 | 43 | 97 | 32 (68 %) | 3 | 26 | 423 | 600 |
| sleeping rats | 5 (11 %) | 42 | 0 | 65 | 71 | 21 (45 %) | 24 | 3 | 459 | 515 |
| pile of rats | 19 (40 %) | 0 | 41 | 690 | 918 | 35 (74 %) | 0 | 35 | 2105 | 2389 |

**Colour (separate, never pooled with IR), τ = 0.25** (47 heads on 10 frames):

| prompt | whole X | whole missed | whole merged | whole empty | whole masks | tiled X | tiled missed | tiled merged | tiled empty | tiled masks |
|---|---|---|---|---|---|---|---|---|---|---|
| rat | 2 (4 %) | 45 | 0 | 68 | 70 | 1 (2 %) | 46 | 0 | 102 | 103 |
| Long Evans rat | 0 (0 %) | 47 | 0 | 0 | 0 | 0 (0 %) | 47 | 0 | 0 | 0 |
| hooded rat | 0 (0 %) | 47 | 0 | 0 | 0 | 0 (0 %) | 47 | 0 | 0 | 0 |
| black striped rat | 0 (0 %) | 47 | 0 | 5 | 5 | 0 (0 %) | 47 | 0 | 23 | 23 |
| rat with a black stripe on its back | 3 (6 %) | 44 | 0 | 65 | 68 | 0 (0 %) | 47 | 0 | 101 | 101 |
| black and white rat | 1 (2 %) | 46 | 0 | 60 | 61 | 0 (0 %) | 47 | 0 | 87 | 87 |
| rat with a black head and a white body | 1 (2 %) | 46 | 0 | 43 | 44 | 3 (6 %) | 44 | 0 | 59 | 62 |
| rat with an implant on its head | 0 (0 %) | 47 | 0 | 0 | 0 | 1 (2 %) | 46 | 0 | 2 | 3 |
| sleeping rats | 0 (0 %) | 47 | 0 | 0 | 0 | 1 (2 %) | 46 | 0 | 4 | 5 |
| pile of rats | 3 (6 %) | 23 | 6 | 9 | 20 | 6 (13 %) | 34 | 3 | 26 | 35 |

- **Descriptive reading of the counts** (no judgment of the images): at τ = 0.01, the prompts with X ≥ 50 % on the whole IR frames ("rat", "black striped rat", "rat with a black stripe on its back", "black and white rat", "rat with a black head and a white body") return 482–1433 masks for 49 heads (375–1247 of them empty).
  - So a high X there comes with many masks per head, one of which covers each head point alone.
  - It does not show a rat detector.
  - At τ = 0.25 almost every prompt misses almost every head.
  - Whether any mask outlines a rat is for the user to see on the page.
- **Page for the user:** `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320/prompt_sweep/index.html`.
  - Per frame and prompt: whole and tiled panels with mask outlines in distinct colours, the blind clicks as dots, and a τ switch (0.01 / 0.25).
  - Headless check: **PASS** (`prompt_sweep/page_check.json`).
- Tables: `prompt_sweep/sweep_summary.csv` (pooled), `sweep_frame_metrics.csv` (per frame); raw masks of the new prompts in `prompt_sweep/sam3/`.
- **The agent did not look at the panels.**

## Definitions

Units: image pixels (px) of the full-resolution frame (2560 × 1920), origin top-left; inches only where stated (scale s = 74.8 px/in from the clicks run's similarity fit). $h_i=(u_i,v_i)$ = blind head click $i$ of a frame; $M_j$ = a mask (set of pixels) with score $s_j$ and area $|M_j|$ px.

### Head–mask distance and coverage ($d_{ij}$, $c_{ij}$)
$$ d_{ij} = \begin{cases}0 & \lfloor h_i\rfloor \in M_j\\ \min_{p\in M_j}\lVert (p+\tfrac12) - h_i\rVert_2 & \text{otherwise}\end{cases},\qquad c_{ij}=\mathbb 1[d_{ij}\le 15\,\text{px}] $$
**Text:** a mask covers a head if the clicked pixel is in the mask or a mask pixel centre lies within 15 px (plan). Units px.

### T1 kept masks and matching
$K_\tau=\{j: s_j\ge\tau\}$. Head choice $a(i)=\arg\max_{j\in K_\tau, c_{ij}=1}(s_j,-|M_j|)$; mask $j$ keeps $k(j)=\arg\min_{i:a(i)=j}(d_{ij},\lVert h_i-\bar M_j\rVert)$ ($\bar M_j$ = mask centroid). **Text:** a head goes to the highest-scoring mask covering it; a mask chosen by several heads is matched to one (amendment 1 item 4).

### T1 counts and rates (pooled over a frame set $F$)
$$ TP=\sum_{f\in F}\#\{j: k(j)\text{ exists}\},\quad P=\frac{TP}{\sum_f |K_\tau|},\quad R=\frac{TP}{\sum_f n_f},\quad F_1=\frac{2\,TP}{\sum_f(|K_\tau|+n_f)} $$
$$ X=\frac{\sum_f \#\{i: i=k(a(i)),\ \sum_{i'}c_{i'a(i)}=1\}}{\sum_f n_f},\quad \text{merged}=\frac{\#\{j:\sum_i c_{ij}\ge2\}}{\sum_f|K_\tau|},\quad \text{empty}=\frac{\#\{j:\sum_i c_{ij}=0\}}{\sum_f|K_\tau|} $$
$$ \text{count error}=\frac1{|F|}\sum_f(|K_\tau|-n_f) $$
where $n_f$ = blind heads on frame $f$. **Text:** $X$ (**head-point exclusivity**) = share of heads that have their own mask covering no other head (0–1; 1 = one mask per head point); merged = share of masks spanning ≥ 2 head points; empty = share of masks on no head point; count error in masks per frame (+ = too many). $F_1$ is the dev selection criterion.

### Threshold τ and prompt choice
τ ∈ {0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, …, 0.95}; the (prompt, τ) maximising pooled $F_1$ on dev IR frames (ties → higher τ, then lower prompt number). SAM 3 score $s=\sigma(\ell_{det})\,\sigma(\ell_{presence})$ (ultralytics). **Text:** chosen once on dev, never on test.

### Tiled merge
Tile masks with $s\ge\tau$ in descending score; mask $m$ joins the first earlier-kept representative $r$ from another tile with $\mathrm{IoU}(M_m,M_r)=|M_m\cap M_r|/|M_m\cup M_r|\ge0.5$; a cluster covers a head if any member does; its score = $s_r$, its area = the union area. **Text:** removes duplicates of one object seen by two overlapping tiles.

### T2 per-head mask metrics
For head $i$ with point-prompted mask $M^{(i)}$: own $=c_{i,(i)}$, $n^{(i)}=\sum_{i'}c_{i',(i)}$; exclusive $=\text{own}\wedge n^{(i)}=1$; merge $=n^{(i)}\ge2$; own missed $=\neg\text{own}$. Rates = means over heads. Pairwise $\mathrm{IoU}(M^{(i)},M^{(i')})$ over head pairs of a frame; box = bounding box of $M^{(i)}$, aspect = long / short side. **Text:** exclusivity near 1 = each point gives a mask on its own head only (head-point level, not a whole-rat check).

### Still-episode group join rule
$$ \text{join}(i,i{+}1)=\mathbb 1\Big[\text{roster}(t)\ \text{constant on}\ [t_a,t_b]\Big]\cdot\prod_{a\in\text{roster}}\mathbb 1\Big[\tfrac{1}{N}\textstyle\sum_{t=t_a}^{t_b}\text{ok}_a(t)\,\text{still}_a(t)\ge0.9\Big] $$
$t_a$ = last frame of segment $i$, $t_b$ = colour frame of $i+1$, $N$ = seconds in $[t_a,t_b]$. **Text:** a still, unchanged pile between two flashes makes them one unit (amendment 1 item 2).

### Grouped bootstrap CI
$B=2000$ draws of the groups with replacement (seed 20261011); a pooled ratio $\hat\theta^{(b)}=\sum_g w^{(b)}_g\,\text{num}_g/\sum_g w^{(b)}_g\,\text{den}_g$ ($w_g^{(b)}$ = times group $g$ is drawn); 95 % CI = 2.5th–97.5th percentiles. Paired = the same draws for the compared quantities. **Text:** uncertainty from which still episodes happened to be sampled.

### T3 accuracy, balanced accuracy, chance
$$ \text{acc}=\frac1N\sum_n\mathbb 1[\hat y_n=y_n],\quad \text{bal}=\frac1{|C|}\sum_{c}\frac{\#\{n:y_n=c,\hat y_n=c\}}{\#\{n:y_n=c\}},\quad \text{chance}=1/5 $$
$y_n$ = the user's blind label, $\hat y_n$ = the prediction for click $n$ when its group (LOGO) or its day (LODO) was held out. Majority-class rate = largest class share.

### T3 classifiers
Logistic: standardised features, multinomial L2 logistic regression, $C\in\{10^{-3},…,10^{2}\}$ by inner GroupKFold (min(5, groups) folds, pooled accuracy, ties → smaller C) inside each training fold. Nearest centroid: $\hat y=\arg\max_c \langle z/\lVert z\rVert,\mu_c/\lVert\mu_c\rVert\rangle$ (embeddings) or $\arg\min_c\lVert z-\mu_c\rVert$ on standardised coordinates (position).

### T3 controls
(a) position only: $(u,v)$ px and the house-frame $(\text{along},\text{across})$ in from the similarity fit; (b) head-masked: the same crop with the disc $\lVert p-h\rVert\le1.5$ in filled with the crop's per-channel median; (c) position-matched: the crop at the same $(u,v)$ in one IR frame of another group (drawn uniformly, seed 20261011), labelled with the original rat; (d) shuffled: labels permuted across clicks (20 permutations). Best control = $\max$ point accuracy among (a)–(c) under the same classifier (and embedding).

### T3 decision rule (amendment 1 item 3)
$$ \Delta_{ch}=\text{acc}-0.2,\quad\Delta_{ct}=\text{acc}-\text{acc}_{best},\quad \text{carries}=[\Delta_{ch}\ge0.15]\wedge[\Delta_{ct}\ge0.15]\wedge[\mathrm{CI}_{lo}(\Delta_{ch})>0]\wedge[\mathrm{CI}_{lo}(\Delta_{ct})>0] $$
established $=\text{carries}\wedge\mathrm{CI}_{lo}(\Delta_{ch})\ge0.15\wedge\mathrm{CI}_{lo}(\Delta_{ct})\ge0.15$, CIs paired grouped bootstrap. **Text:** an engineering gate, not a biological claim.

### Pile size
Size of the head's single-linkage cluster among the frame's blind heads with link distance 6 in (= 449 px). Strata 1, 2–3, ≥ 4 (and 'none' for a T1 mask on no head). **Text:** used only to stratify the review sample and descriptive tables.

## Limits and what is not verified

- **No usable-box claim yet.** Head-point exclusivity is necessary, not sufficient, for one-whole-rat masks. The blind mask review decides that, and the user has not scored it yet.
- **T2's negative-point variant is partly self-validating:** the metric checks the same heads the prompt excludes. The positive-point variant is the pre-named primary.
- **Sample size:** one house (CH07), one labeller, 20 still-episode groups. No pair met the join rule.
  - The IR frames are 6 s and 15 s after the colour light, so one pile appears twice per segment, and sometimes again in the next segment; amendment 3 gives the sensitivity.
  - Bootstrap CIs over about 15–20 groups are approximate.
- **T3 labels and claims:**
  - The truth labels are the user's blind IDs; two IR frames carry a duplicated label (the sensitivity is reported).
  - Leave-one-group-out success alone is not a cross-day claim; LODO has one held-out day.
  - The gate is an engineering test, not a biological claim.
- **Inner-CV choice of C** for the logistic probe varies from 0.01 to 100 across the leave-one-group-out folds. The training sets are small, so the probe is not tuned finely.
- **T1 τ sits at the cache floor (0.01).** The low end of the τ grid was set after the API probe had shown one prompt scoring ≤ 0.02 on one frame; that probe matched no head and computed no metric (plan, disclosure note).
- **Execution:** the first GPU job stopped after 8 frames when its session ended. It resumed from atomic per-frame caches, and no frame was recomputed.
- **Interpreter split:** scipy's L-BFGS-B crashes natively in the cv env (0xc06d007f). So the score and review phases ran in base Python (scikit-learn 1.7.2), and the GPU phases in the cv env.
- **No training, no labels:** SAM 3 and DINOv3 are frozen; no detector was trained and no label was written.

## Rerun

```
python cv/cv_field/inbox_sam3_dino_test.py --selftest
C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/inbox_sam3_dino_test.py --phases data t1gpu t2gpu dino   # new run (GPU)
python cv/cv_field/inbox_sam3_dino_test.py --run D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320 --phases score review report
```

## Files

Run folder `D:/Field2026_analysis_out/2026c/cv_field_inbox_sam3_dino_20261010_2320`:
- inputs and groups: `frames.csv`, `heads.csv`, `groups.csv`, `group_pairs.csv`, `data.json`;
- raw masks: `sam3_t1/{whole,tiled}/*.npz`, `sam3_t2/*.npz`; timing: `timing_t1.csv`, `timing_t2.csv`;
- T1: `t1_frame_metrics.csv.gz`, `t1_sweep.csv`, `t1_head_detail.csv.gz`, `t1_by_pile_test_ir.csv`, `t1_result.json`;
- T2: `t2_heads.csv`, `t2_pair_iou.csv`, `t2_summary.csv`, `t2_by_pile_test.csv`, `t2_result.json`;
- T3: `t3_units.csv`, `t3_embeddings.npz`, `t3_results.csv`, `t3_predictions.csv.gz`, `t3_decisions.csv`, `t3_confusion.csv`, `t3_shuffled.csv`, `t3_group_alt.json`, `t3_result.json`;
- review: `mask_review/` (the page + `items/`), `mask_key.csv` (the hidden key), `mask_review_meta.json`, `mask_review_page_check.json`;
- `run.json`.
