# cv_field — foundational visible-regime slice (mask + native-tile SAHI + DINOv3 gate)

**Date:** 2026-07-13 · **Status:** in progress · **Direction:** cv_field

## Context / why (a reframe, not a tune)

The whole-field night detector collapsed from within-night val AP ~0.8 to frozen cross-night test AP ~0.2.
A three-mechanism diagnostic (under-fit / appearance-shift / small-object-inference) plus a visual
spot-check found the **root cause is physical occlusion**: the field grew tall grass over ~10 days, so the
short-grass training scene no longer exists on late nights (rats hidden except at edges/clearings). A
web-grounded, adversarially stress-tested SOTA audit (6 dimensions, 12 agents) was **unanimous**: no pixel
method crosses the occlusion ceiling — the collapse is occlusion, not detector capacity, labels, or
resolution. Every winning component the audit surfaced is an **asset already in hand**, tiny-label, and
single-GPU; the SOTA answer is *wiring existing pieces correctly*, not a bigger model.

Prescription adopted (owner-selected scope = **cheap foundational wins first**): reframe from "detect all
rats" to **"detect VISIBLE rats well + fuse WISER for the occluded remainder,"** and build only the
near-free layer now, measured honestly on a visible-stratified frozen test, before any tracking /
augmentation / detector-swap / WISER-georeference work.

## Guiding principle — regime split, honestly measured

Pixel methods own the **visible** fraction (early full-field nights + edges/clearings of any night). The
**occluded** fraction is a permanent pixel blind spot only grass-independent WISER UWB can localize — and
WISER stays a no-op inch frame until a pole survey passes QC, so this slice uses it for **evaluation
honesty only** (occlusion-censoring), never coordinates. Every derived number is scoped to the visible
stratum.

## The slice — four workstreams, assets-in-hand, single-GPU, no new labels

Reuses `cv/cv_field/` (`field_embed.py` DINOv3 crop path, `field_motion.py` proposal generator), the cohort
shim (`output_paths.py`), `cv/field_coords.py` (`to_pixel` for the mask GUI overlay), and
`cv/train_detector.py`. New modules under `cv/cv_field/`.

0. **Valid-field mask (regime-independent, first).** `mask_field.py` (matplotlib `PolygonSelector` GUI,
   sibling of `label_frames.py`; overlays the calib-projected field rectangle as a *guide only* — CH03
   landmarks cluster near x=0..165 cm of a 1219 cm field, reproj RMSE ~20 cm, so the far end is
   extrapolated) → `cv/configs/CH0X_field_mask.json` = **normalized (0–1) polygon + bounding crop** (calib
   reference is 2560×1426, so pixels would not port to 1280/native). `field_mask.py` = loader +
   `point_in_field` / `apply(frame)` scaling to any resolution. `field_motion.py` gains an optional mask
   and drops proposals whose box centroid is outside the valid polygon.

1. **Proposal-cued native-tile SAHI retrain (the resolution fix).** `tile_dataset.py` re-slices
   `dataset/rat_field` (120 frames / 205 boxes) into native-res tiles (~1280–1536, 20% overlap), boxes
   re-projected into tile coords → `dataset/rat_field_tiles/`; retrain via
   `train_detector.py --data-root dataset/rat_field_tiles --name rat_field_tiles --augment`. **Critical:**
   the frozen `dataset/rat_field_test` (07-06) is never sliced into training — the ablation proved
   slice-inferring a 1280-trained model is *worse* (AP 0.205→0.007, scale mismatch), so we **retrain on
   native tiles**. `tile_infer.py` runs the detector only on tiles containing a motion/mask-passed proposal
   (never blind 640-tiles × 36 cam-hours), merging with NMS/NMM at seams. Adds lazy `sahi` to the cv env.

2. **DINOv3 few-shot precision gate.** `dino_gate.py` fits a light linear/prototype head on **frozen**
   DINOv3 ViT-B/16 crop embeddings (reuse `field_embed`'s `crops=` path); positives = labeled rat crops
   from non-frozen nights, negatives = grass/wall crops from mask-failed / low-motion regions; scores each
   proposal crop. Forward-pass only. Caveat carried: 25–90 px is near the 16 px patch floor and monochrome
   IR is off DINOv3's RGB distribution, so the head absorbs a domain gap — must beat a no-gate baseline.
   Physically grounded by the **Long Evans dark hood** (black dorsal blob vs NIR-bright grass) — the same
   signal `field_motion`'s `polarity="dark"` exploits.

3. **Visible/occluded test re-stratification + honest metrics.** `stratify_test.py` tags each frozen 07-06
   frame/box `visible` vs `occluded`, then reports **TP/FP/FN and recall@matched-precision on the visible
   stratum** (not only AP on 22 boxes). Frozen test is scoring-only: never tile-trained, gate-fit,
   threshold-tuned, or acquired against.

## Verification

1. **Dark-hood contrast check first** — read-only intensity analysis (labeled-rat pixels vs surrounding
   grass on existing CH03/CH04 frames) confirms the dark-hood contrast is real in *our* footage before the
   gate / dark polarity lean on it. (Memory only if it passes.)
2. **Offline self-test** — `selftest_field_mask.py`: `point_in_field` correctness, normalized↔pixel scaling
   across 1280/2560/4512, tile box re-projection round-trips. numpy/cv2 only, no GPU/data.
3. **Pipeline acceptance (run machine)** — on the visible stratum of the frozen test: mask reduces FPs;
   native-tile retrain beats the 1280 baseline (recall@P); the DINOv3 gate raises precision at equal recall.

## Deferred (not this slice)

ByteTrack/OC-SORT association; copy-paste augmentation; WISER georeference QC + UWB-as-prior; detector swap
(RT-DETR/RF-DETR/Co-DETR); efficient-sparse (QueryDet/CEASC/ESOD); super-resolution; classical/deep BGS;
open-vocab/SAM/MegaDetector. Ranked below the four workstreams for our budget, or dominated by assets we own.
Ledger (after): `change_log/2026-07-13-cv-field-visible-regime.md`.
