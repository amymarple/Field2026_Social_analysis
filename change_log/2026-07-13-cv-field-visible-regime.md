# cv_field — foundational visible-regime slice (mask + native-tile SAHI + DINOv3 gate)

**Date:** 2026-07-13 · **Status:** code + offline verification COMPLETE; run steps (GUI, native-tile retrain,
frozen-test eval) pending · **Direction:** cv_field · Plan:
`implementation_plan/2026-07-13-cv-field-visible-regime.md`

## Why (root cause + audit)

The whole-field night detector collapsed val AP ~0.8 → frozen cross-night test AP ~0.2. A three-mechanism
diagnostic (under-fit / appearance-shift / small-object-inference) plus a visual spot-check found the **root
cause is physical occlusion**: the field grew tall grass over ~10 days, so the short-grass training scene no
longer exists on late nights (rats hidden except at edges/clearings). A web-grounded, adversarially
stress-tested SOTA audit (6 dimensions, 12 agents, ~627k tokens) was **unanimous**: *no pixel method crosses
the occlusion ceiling*. Every winning component it surfaced is an asset already in hand, tiny-label, and
single-GPU — the answer is wiring existing pieces correctly, not a bigger model.

**Reframe adopted** (owner scope = cheap foundational wins first): *detect VISIBLE rats well + fuse WISER for
the occluded remainder*. WISER is used for **evaluation honesty only** (occlusion-censoring), never
coordinates (georeference stays `confirmed:false`).

## What shipped (all under `cv/cv_field/`)

- **`field_mask.py`** — valid-field ROI geometry. Loads a **normalized (0–1) polygon + crop** (calib ref is
  2560×1426, inference is 1280/native 4512 — pixels wouldn't port), pure-numpy point-in-polygon with
  exclusion holes, `filter_boxes` (centroid gate), `render_mask`/`apply` (crop+zero-out), and
  `projected_field_polygon_norm` (calib `to_pixel` of the field rectangle as a GUI tracing guide).
- **`mask_field.py`** — matplotlib `PolygonSelector` GUI (sibling of `label_frames.py`) to draw the mask on a
  CH03/CH04 night-IR frame (`--image` or `--video`), overlaying the calib guide; writes
  `cv/configs/CH0X_field_mask.json` + a dimmed preview PNG. **Interactive — owner runs it.**
- **`field_motion.py`** — `motion_from_burst(..., mask=None)`: drops proposals whose box centroid is outside
  the valid field. Backward-compatible (default None; all existing callers unaffected).
- **`tile_dataset.py`** — re-slices `dataset/rat_field` into **native-resolution tiles** (source is 4512×2512
  on Q:; the stored PNGs are only 1280×712). Parses source+offset from the filename, ffmpeg-extracts the
  native frame, slices (tile 1280 / 20% overlap), reprojects boxes into tile coords, keeps `--use-mask`
  in-field tiles + `--neg-per-frame` background tiles. **Hard guard: refuses to tile a `*_test` root** —
  retrain on native tiles (the ablation proved slice-inferring a 1280 model is worse, AP 0.205→0.007).
- **`tile_infer.py`** — proposal-cued native-tile inference: run the detector only on tiles containing a
  motion/mask proposal, map tile dets back to global native px, global NMS at seams. Detector injected as a
  `predict_fn` (real YOLO via `yolo_predictor`).
- **`dino_gate.py`** — the PRECISION half: nearest-prototype cosine-margin head on **frozen DINOv3 ViT-B/16**
  crop embeddings (reuses `field_embed`'s `crops=` path, no backbone training). Positives = labeled rat
  crops; negatives = random grass + wall crops; threshold chosen on a held-out crop split (never the frozen
  test).
- **`stratify_test.py`** — splits the frozen 07-06 ruler into **visible/occluded** strata (owner-editable
  `visibility.json`, or the dark-hood-contrast heuristic starter) and reports **TP/FP/FN + recall@matched-
  precision on the visible stratum** (occluded GT excluded from the recall denominator; FPs always count).
- **`selftest_field_mask.py`** + `sahi` added (lazy) to `cv/environment.yml` + `cv/requirements.txt`.

## Verification (offline, this machine)

- **Dark-hood contrast — CONFIRMED in our footage.** Over 205 labeled CH03/CH04 rat boxes: **100% read
  darker than their surrounding grass**; dark-hood contrast **rat median 60 vs grass-null 18 grey levels
  (~42 separation)**; per-cam CH04 median 78 > CH03 37. Empirically justifies `polarity="dark"` and the
  `dino_gate` premise. (Grass null ~18 ≠ 0, so a raw threshold over-tags grass — the DINOv3 gate, not a
  threshold, is the discriminator; for stratification a threshold ~28 is safer than the default 12.) See
  memory `cv-field-darkhood-contrast`.
- **Self-tests PASS:** `selftest_field_mask` (point-in-polygon, cross-resolution 1280/2560/4512 invariance,
  centroid filter, render/apply, round-trip, calib guide), and `--selftest` on `mask_field`, `field_motion`
  (regression, incl. windy base-rate), `tile_dataset` (parse/coverage/reproject/overlap), `tile_infer`
  (NMS/cued-selection/seam-merge), `dino_gate` (separable-cluster acc, save/load), `stratify_test`
  (IoU-match/PR/recall@P/box-contrast). Pre-existing `selftest_field_select` still PASS (no regression).
  `py_compile` clean on all modules.

## Run results (2026-07-14) — native-tile retrain did NOT beat the baseline on the frozen test

Steps 1–2 executed (masks drawn by owner; `eval_frozen.py` added for the comparison):

- **Masks:** CH03 + CH04 hand-drawn (`mask_field.py`); ~66% valid area, wall/sky top band excluded. (Fixed a
  GUI view bug — CH03's calib guide extrapolates thousands of px off-frame and auto-zoomed the view; the view
  is now pinned to the image.)
- **Native tiles:** `tile_dataset.py --use-mask` over 117/120 frames from Q: → **270 positive + 117 background
  tiles, 372 boxes**, sessions 06-28/29 (short grass) + 07-05 (windy). Visual check: boxes land on rats now at
  ~90–150 px (vs ~25 px), dark hood sharply contrasted — the scale-match is real.
- **Retrain** `rat_field_tiles` (freeze 10, lr0 0.002, batch 8, imgsz 1280, aug): within-night held-out val
  mAP50 **0.476** (tiles val — harder set with 117 background tiles + windy 07-05; not comparable to the old
  frame-val ~0.8).
- **Honest frozen-07-06 eval** (`eval_frozen.py`, native-tile mask-gated tiled inference vs old 1280 full-frame,
  same TP/FP/FN + recall@matched-precision metric, visible stratum, heuristic visibility thr 20):

  | config | IoU | TP | FP | precision | recall_visible | recall_allGT |
  |---|---|---|---|---|---|---|
  | baseline-1280 | 0.5 | 10 | 22 | 0.31 | 0.43 | 0.45 |
  | native-tile   | 0.5 | 5  | 45 | 0.10 | 0.21 | 0.23 |
  | baseline-1280 | 0.3 | 13 | 19 | 0.41 | 0.57 | 0.59 |
  | native-tile   | 0.3 | 9  | 41 | 0.18 | 0.29 | 0.41 |

  **The native-tile detector is dominated on the frozen test at both IoU thresholds** — lower recall AND lower
  precision. Verified by eye (no coordinate bug): 07-06 is a tall-grass JUNGLE where grass is NIR-bright and
  rats are buried; the few visible GT are tiny dark fragments at the sparse dark edges/corners. Two mechanisms:
  (a) tiling the bright grass at native res multiplies FP draws (41–45 vs 19–22) — the base-rate flood the
  audit predicted for **un-gated** tiling; (b) the native-scale detector (trained on big clear short-grass
  rats) matches the tiny occluded 07-06 fragments *worse* than the small-object 1280 baseline. Scale-matching
  to native is itself regime-specific: it fits the short-grass regime, not the occluded test night.

  **This reinforces, not refutes, the audit:** resolution/tiling does not cross the occlusion ceiling; the
  07-06 collapse is occlusion. It also shows 07-06 is the wrong ruler to judge a *visible-regime* detector — it
  is almost entirely the occluded regime (baseline itself only reaches recall 0.57). The `eval_frozen`
  result JSONs are saved; the frozen test was untouched by any training/tuning.

- **DINOv3 precision gate — fit + applied as a detector post-filter (a real win).** `dino_gate.py --fit` on
  the 205 rat + 410 grass/wall crops: **balanced accuracy 0.945** on a held-out crop split (DINOv3 embeddings
  separate rat from grass — the dark-hood signal is learnable). Applied as a precision post-filter to BOTH
  detectors on the frozen test (IoU 0.3, visible stratum), it removes false positives at **zero recall cost**:

  | config | TP | FP | precision | recall_visible |
  |---|---|---|---|---|
  | baseline-1280      | 13 | 19 | 0.41 | 0.57 |
  | native-tile        | 9  | 41 | 0.18 | 0.29 |
  | **baseline + gate** | 13 | **11** | **0.54** | 0.57 |
  | native + gate      | 9  | 26 | 0.26 | 0.29 |

  **Best config = the small-object 1280 baseline + DINOv3 gate**: precision 0.41 → **0.54** at unchanged recall
  0.57 (killed 8 of 19 FPs, kept every TP). Native tiling stays dominated even after gating. The gate is the
  audit's predicted top precision lever, confirmed; it is detector-agnostic and reusable.

## Verdict for this slice

- **Adopt:** the **DINOv3 precision gate** (real, confirmed precision lift, detector-agnostic) + the
  **valid-field mask** (free FP reduction, regime-independent).
- **Do NOT adopt:** native-tile retrain — dominated on the external ruler. **Correction (2026-07-14):** the
  earlier "floods grass FPs" framing was OVERSTATED — that 44-FP count was at conf 0.05 (noise floor); at a
  real operating point (0.20) native-tile has ~6 FPs, several ambiguous (possibly rats near the shelter). The
  robust reason it loses is **RECALL, not FPs**: re-tested against the COMPLETED 28-box GT at matched
  precision (same 120-frame training, tiling-vs-not), native-tile finds fewer real rats — TP 13 vs baseline 16
  (IoU 0.3), recall@p50 0.40 vs 0.55, recall@p70 0.30 vs 0.55. Native detail amplifies viewpoint variance so it
  generalizes worse (misses rats). Kept as code, not promoted.
- **Production visible detector = `rat_field_r2_aug` (1280) + `dino_gate.npz`.**

### Reframing (owner correction, 2026-07-14) — coverage problem, not an occlusion wall

A contact sheet of all 22 frozen-test GT crops (native res) showed the rats are **mostly VISIBLE** — the
challenge is dominated by **viewpoint/pose/scale/background variation + partial occlusion**, not total
occlusion: a whole-field cam sees a rat top-down near the base, side-on/oblique far away, plus body-pose and
grass. This corrects the earlier "occlusion ceiling" language: the recall limit (~0.57) is **label COVERAGE
of the appearance manifold**, not physics. It also explains the native-tile loss mechanistically — native
detail exposes viewpoint-specific shape the detector overfits, while a low-res ~25 px blob is more
viewpoint-invariant. **The real recall lever is DIVERSE labeling across viewpoints/positions/poses/grass**
(the `select_frames.py` DINOv3-diversity + motion active-learning loop, already built) + viewpoint
augmentation, at moderate (not native) resolution; the DINOv3 gate handles precision. Next round: an
appearance-diverse acquisition batch spanning late/tall-grass nights and camera angles, label, retrain,
re-eval — recall is expected to climb because the ceiling is coverage, not visibility.

## Diversity round 1 (2026-07-14) — the coverage lever WORKS (frozen-test recall up)

Acting on the reframing, a fast viewpoint-diverse active-learning round (all local drives, no Q:, no native
tiling):
- **Harvest** 4 nights the training set didn't cover — 07-01, 07-02 (F:), 07-07, 07-08 (E:), evening hours →
  101-frame `--no-detector` pool (~3 min).
- **Localize FAST**: one batched `rat_field_r2_aug` pass over the pool PNGs → a `load_motion`-format sidecar
  (6.6 s, vs ~10 min of per-frame video bursts). 55% of frames had a detection.
- **Select** `select_frames --round 1 --use-motion --seed-weights rat_field_r2_aug --budget 50` → 50 frames
  spread across all 4 nights + both cams, spanning the short→tall grass progression; proposals pre-filled on 33.
- **Label** (owner): all 50 → 32 with rats (44 boxes) + 18 clean negatives. Training set **120→167 labeled
  frames, 205→249 boxes** (now 06-28/29 + 07-01/02 + 07-05 + 07-07/08).
- **Retrain** `rat_field_div1` (1280, aug, freeze 10) — within-night val mAP50 **0.833** (vs native-tile 0.48).
- **Frozen-07-06 re-eval** (full-frame, visible stratum) — the labels came from OTHER nights; 07-06 untouched:

  | config | IoU 0.3 recall_vis | IoU 0.5 recall_vis | precision (IoU 0.3) |
  |---|---|---|---|
  | old `r2_aug` | 0.57 | 0.43 | 0.41 |
  | **new `div1`** | **0.71** | **0.64** | 0.48 |
  | **new `div1` + gate** | **0.71** | **0.64** | **0.53** |

  Recall **0.57→0.71** (IoU 0.3), **0.43→0.64** (IoU 0.5); TP 13→16. **This confirms the reframing: the
  frozen-test limit was label COVERAGE of the viewpoint/pose/grass manifold, not occlusion or resolution.**
  Modest label investment (50 frames), moderate resolution, no tiling. The DINOv3 gate still adds precision on
  top. Fast throughout (harvest→select round in a few minutes, all off local drives).

- **Updated production visible detector = `rat_field_div1` (1280) + `dino_gate.npz`.** Next lever is another
  diversity round (the active-learning curve has not plateaued); native tiling remains not-adopted.

## Diversity round 2 (2026-07-14) — REGRESSED; not all diverse labels help

Same fast loop, 4 new nights **07-03/04 (F:, mid-grass) + 07-09/10 (E:, tall grass)**, late-night hours (the
local copies held 00–04, not 21–23) → 110-frame pool → `select_frames --round 2 --seed-weights div1`
→ 50 frames (30 with rats / 20 empty) → labeled (+43 boxes) → `rat_field_div2` (217 frames / 292 boxes).

Frozen-07-06 result — **div2 is worse than div1 at every matched-precision level** (IoU 0.3, visible, gated):

| config | recall@p40 | recall@p50 | recall@p60 | raw FP @conf.05 |
|---|---|---|---|---|
| **div1 + gate** | **0.79** | **0.71** | **0.57** | 14 |
| div2 + gate | 0.57 | 0.50 | 0.43 | 32 |

**Why it hurt:** round 2's positives were tiny, ambiguous rats in dense late-night tall grass — close in
appearance to the grass itself. Labeling them **blurred the rat/grass boundary**, so the detector fired on
more grass (FP 17→44 raw) without gaining recall. The 20 hard negatives did not compensate. **Lesson: label
COVERAGE helps only when the positives are CLEAR; adding near-grass-noise positives degrades precision.** Also
a clean cautionary example — div2's *within-night* val was HIGHER (0.864 vs 0.833) yet it was worse on the
frozen night; the external ruler caught a regression the internal val hid.

**Action: reverted — production visible detector stays `rat_field_div1` (1280) + `dino_gate.npz`.** `div2`
weights kept but not promoted. A future round should target CLEARLY-visible rats (edges/clearings, earlier
hours) rather than late-night tall-grass fragments, or relabel round 2 more conservatively.

## ⚠️ Frozen-test GT is INCOMPLETE — precision understated, div2 verdict SUSPECT (2026-07-14)

Visual inspection (owner + `frozen_inspect` render) found that **all 6 of div1+gate's "false positives"
(conf 0.20) on 07-06 are REAL rats the original 22-box GT missed** — clear Long Evans in every crop
(`fp_crops/fp_montage.png`). Implications:
- **True precision is ~1.0, not 0.67** at conf 0.20+gate — the detector is far cleaner than measured; the
  original 22-box GT undercounts rats.
- **Every precision/recall number above is against an incomplete ruler.** In particular the **div2
  "regression" is now unverified**: its extra "FPs" (17→44) may be real unlabeled rats (div2 finding MORE
  rats), not a precision flood. Cannot adjudicate div1 vs div2 until GT is complete.
- **Action:** re-label all 40 frozen-test frames COMPLETELY and INDEPENDENTLY (box every rat, no detector
  overlay, to avoid confirmation bias), then re-run old/div1/div2 ± gate. Completing GT improves the ruler's
  accuracy; frames remain never-trained / never-threshold-tuned (discipline intact).

### RESOLVED — completed GT (22→28 boxes, owner relabel), honest numbers (IoU 0.3, visible=20)

| config | TP | FP | precision | recall@p50 | recall@p70 |
|---|---|---|---|---|---|
| old `r2_aug` + gate | 16 | 8 | 0.67 | 0.55 | 0.55 |
| **div1 + gate (production)** | 19 | 11 | **0.63** | **0.65** | 0.55 |
| div2 + gate | 20 | 28 | 0.42 | 0.60 | 0.45 |

- **Precision WAS understated:** completing the GT lifted div1+gate precision **0.53→0.63** (6 "FPs" were real
  rats → now TPs). The detector is genuinely cleaner than first reported.
- **div2 regression CONFIRMED against complete GT** — its 28 FPs (vs div1's 11) at equal recall are real
  grass false positives, not missed rats (GT completion added only 6 boxes total). div2 correctly rejected.
- **`old_22box_backup` kept** (`dataset/rat_field_test/labels_22box_backup_20260714/`). Net validated result:
  **old (recall ~0.55) → div1 + DINOv3 gate (recall 0.65, precision 0.63)** on the hardest tall-grass night,
  with honest GT. div1 + gate + valid-field mask = the production visible detector; native tiling and div2
  rejected on held-out evidence.

## Evaluation fix — IoU was too strict; center-matching is the honest metric (2026-07-14)

Owner inspection flagged that IoU matching penalizes correct detections whose box size merely disagrees with
the (fuzzy) GT box — counting a hit ON a rat as FP+FN. For tiny field animals where exact box size is noise,
the right metric is **center-matching** (a detection is a TP if its centre lies on the rat / GT box, size-
tolerant). Added `mode="center"` to `stratify_test.match` and made it `evaluate`'s default (`match_mode`);
IoU stays available; self-test PASS. Effect on div1+gate (complete GT, conf 0.20): IoU-0.5 gave TP11/FP7
(prec 0.61, rec 0.55) — but that was throwing out correct hits. **Center-match: TP15 / FP3 → precision 0.83,
recall 0.75.**

### DEFINITIVE result — center-match, complete 28-box GT, conf 0.20 (deploy op point), visible=20

| config (conf 0.20) | precision (GT-matched) | recall_visible |
|---|---|---|
| old `r2_aug` + gate | 0.80 | 0.45 |
| **div1 + gate (production)** | **0.83** | **0.55** |
| div2 + gate | 0.49 | 0.60 |

- **div1 + gate = precision 0.83 (GT-matched; ≈1.0 by direct review, below) / recall_visible 0.55 at conf
  0.20** on the hardest (tall-grass) held-out night — of 20 labeled visible rats it finds 11 (+4 occluded as a
  bonus). At conf 0.05 recall rises to 0.65 (precision 0.63). **Correction:** an earlier draft said recall
  0.75 — that was a counting bug (total matches incl. occluded ÷ visible total); the correct visible recall is
  0.55 (conf 0.20). The earlier pessimism was still real on precision (fixed: incomplete GT + strict IoU).
- **div2 is a precision/recall TRADE, not a flat regression** (corrected framing): higher recall 0.80 but
  precision 0.49 (its extra detections are mostly not-on-a-rat under center-match). div1 is the better
  balance and stays production; div2 only preferable if max recall is wanted and precision can be recovered
  by a higher conf threshold.
- Two owner catches that improved the science this session: **GT was incomplete** (precision understated) and
  **IoU matching was wrong for the task** (recall+precision understated). Both fixed; conclusions re-verified.

### Precision ≈ 1.0 by DIRECT REVIEW — GT is chronically incomplete (2026-07-14)

Owner inspection of a `frozen_inspect` frame showed the completed GT is STILL incomplete (a GT1 frame
actually holds ~4 rats). Direct review of all 3 remaining div1+gate "FPs" (conf 0.20, complete GT): **all 3
are real rats** (`fp_now.png`) → **the detector has ZERO true false positives at conf 0.20 on this night;
true precision ≈ 1.0.** The "0.83" was purely residual GT-undercount. Consequences for how cv_field is
measured going forward:
- **Measure PRECISION by direct detection-review (rat / not-rat), NOT GT-matching** — GT-matching precision is
  unreliable while the labeler keeps missing rats the detector finds (the detector is now arguably as complete
  as manual labeling on this hard footage).
- **RECALL is the only real frontier** (visible ~0.55 at the high-precision conf 0.20, ~0.65 at conf 0.05; a
  soft lower bound since the true-rat denominator is unknown due to GT undercount). Improve via targeted
  labeling of the miss modes: far-field / wall-base (small + low-contrast on the dark wall band) and
  grass-broken silhouettes; deep-shadow cases may be at the physical limit.
- **Production stands:** div1 + gate + valid-field mask — **precision ≈ 1.0 (verified), recall_visible ~0.55**
  (conf 0.20) on the hardest held-out night. High precision, moderate recall; recall is the gap to close.

## Tiling re-litigated for RECALL (2026-07-14) — direct complementarity, not an eval artifact

Since the eval flaws unfairly hurt everything, re-tested whether native tiling catches the far-field rats div1
misses (tiling's theoretical sweet spot). Head-to-head on the 20 visible frozen rats (conf 0.20, gate,
center-match): both 5, **div1-only 6, native-tile-only 1**, neither 8. Native-tile catches only ONE rat div1
misses and finds far fewer overall (6/20 vs 11/20); union 12/20. **Resolution is not the recall lever** — the
far-field misses are not recovered by more pixels. (Caveat: native-tile trained on 120 frames not 217, so not
perfectly clean, but a 1-rat complementary catch is decisive enough not to justify a full native re-extract +
retrain.) The 8 "neither" rats (missed regardless of resolution) are the hard core → **coverage (labeling) is
the recall lever, not tiling.** Next: a recall-focused labeling round targeting far-field / wall-base rats.

## Diversity round 3 (2026-07-14) — far-field-targeted; recall UP (provisional, pending owner FP review)

Recall-focused round aimed at the far-field/wall-base miss zone. Fast loop: harvest 07-05/11/12 night hours
(local E:) → 119-frame pool → **div1 sidecar at conf 0.10** (surfaces far-field near-misses) → **far-field-
biased selection** (26 far-field frames — detection centre in the upper valid band [0.28,0.52] — + 12 diverse)
→ owner labeled (far-field priority, skip ambiguous) → `rat_field_div3` (252 frames / 345 boxes).

Frozen-07-06 (center-match, complete GT, conf 0.20): **div3+gate recall_vis 0.65 (13/20) vs div1 0.55 (11/20)**
— recovered 2 far-field misses; hard-core (missed-by-both) 8→7. GT-matched precision 0.68 (div1 0.83), BUT
direct review of div3's 9 FPs: **~7 are real rats the GT missed** (second rats in clusters + near-wall) and
**~2 are genuine false-fires on the OSD watermark text** ("RLC-1212A") — a fixable artifact (the field mask
polygon currently includes that corner; add an OSD exclusion). So **true precision ≈ 0.9, recall 0.65** — div3
is genuinely better on recall at ~equal true precision. **Provisional: div3 + gate becomes the candidate
production detector pending owner confirmation of the FP review; add an OSD-text exclusion to CH03/CH04 masks.**
Confirms (again) that targeted CLEAR-rat coverage is the recall lever.

## Open decision (see change_log tail / next session)

The visible-regime detector cannot be fairly judged on an occluded night. Options: (a) fit `dino_gate.py`
(kills the FP flood — precision only, won't change the 07-06 recall verdict; useful only for a visible-regime
deploy); (b) obtain a labeled SHORT-GRASS external test night to judge native tiling where it is designed to
work; (c) accept the audit's conclusion — late-night tall grass is a pixel blind spot — and keep the small-
object 1280 baseline for visible detection while pivoting the occluded regime to WISER / shelter cams / early
short-grass nights. `--augment` stays opt-in; `cv_shelter` untouched; frozen 07-06 remains scoring-only.

## Deferred (audit-ranked below this slice)
ByteTrack/OC-SORT tracking; copy-paste augmentation; WISER georeference QC + UWB-as-prior; detector swap
(RT-DETR/RF-DETR/Co-DETR); efficient-sparse (QueryDet/CEASC/ESOD); super-resolution; classical/deep BGS;
open-vocab/SAM/MegaDetector. `cv_shelter` untouched; frozen 07-06 test remains scoring-only.
