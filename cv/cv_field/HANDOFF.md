# cv_field — HANDOFF / STATUS (2026-07-14)

Self-contained pickup doc for the next agent/person. Full technical detail:
`change_log/2026-07-13-cv-field-visible-regime.md`; plan: `implementation_plan/2026-07-13-cv-field-visible-regime.md`.

## TL;DR — what this is and where it stands

Whole-field **night-IR rat detector** for the outdoor paddock cameras **CH03/CH04**, night window
21:00–04:20. (CH01/CH02 daytime color is corrupted; night-IR only.)

**Production-candidate detector = `rat_field_div3` (YOLO11, 1280) + DINOv3 gate + valid-field mask.**
On the hardest held-out night (07-06, tall grass), honest metric (center-matching, direct FP review):
**recall ≈ 0.65, true precision ≈ 0.9.** Trajectory across active-learning rounds: old baseline recall ~0.45
→ div1 0.55 → **div3 0.65**. Precision stayed ~0.9–1.0 throughout.

**PENDING (next action):** owner is inspecting div3's 9 "false positives"
(`…/scratchpad/div3_fp/div3_fp.png`). Read: **~7 are real rats the GT missed** (second rats in clusters +
near-wall), **~2 are genuine false-fires on the OSD watermark text** ("RLC-1212A"). Once confirmed:
1. **Promote `div3` + gate to production** (it beats div1 on recall at ~equal true precision).
2. **Add an OSD-text exclusion** to the CH03/CH04 field masks (kills the 2 watermark fires — the field
   polygon currently includes that bottom corner; the mask GUI is `mask_field.py`).
3. **Fold the missed cluster-rats into the frozen-test GT** (`dataset/rat_field_test/labels/`) — it still
   undercounts rats (chronically incomplete; see methodology below).

## WHERE EVERYTHING LIVES

| Artifact | Path | In git? |
|---|---|---|
| **Labeling dataset** (images+labels+proposals) | `cv/dataset/rat_field/` (252 labeled frames / 345 boxes) | **NO — local only (225M)** |
| **Frozen TEST set** (never trained on) | `cv/dataset/rat_field_test/` (40 frames; GT ~28 boxes; `labels_22box_backup_20260714/` = original) | **NO — local only (36M)** |
| **Trained model weights** | `cv/runs/detect/<name>/weights/best.pt` | **NO — local only** |
| **DINOv3 precision gate** | `cv/cv_field/dino_gate.npz` (+`.json`) | yes (small) |
| **Valid-field masks** | `cv/configs/CH03_field_mask.json`, `CH04_field_mask.json` (+ `_preview.png`) | yes |
| **DINOv3 backbone checkpoint** (license-gated) | `~/.cache/torch/hub/checkpoints/dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth` | NO — per-machine |
| **All cv_field code** | `cv/cv_field/*.py` | yes |
| **Ledgers** | `change_log/` + `implementation_plan/2026-07-13-cv-field-visible-regime.md` | yes |

**Model weights of interest** (`cv/runs/detect/<name>/weights/best.pt`):
- `rat_field_div3` — **current best (production candidate)**; 252-frame set, recall 0.65.
- `rat_field_div1` — prior production; recall 0.55, precision ~1.0. Safe fallback.
- `rat_field_r2_aug` — old baseline (pre-active-learning).
- `rat_field_tiles`, `rat_field_div2` — **REJECTED** (native tiling; round-2 tall-grass). Kept for the record, do not use.

**Raw video (for harvesting more frames):**
- **`Q:\hc997\SocialFieldRat2026\<date>\CH0x\`** = Cornell BioHPC storage master, 2026-06-28→07-12. Network
  mount — works from any PC on the Cornell network, but SLOW (~11 s/frame).
- **`F:\<date>\CH0x\`** = local copies of **2026-07-01→04**. **`E:\<date>\CH0x\`** = local copies of
  **2026-07-05→12**. Fast (~0.3 s/frame). *Prefer E:/F: over Q:.* (These are external drives — confirm they
  are attached to the new PC, or the fast local path is gone and you fall back to Q:.)

## MOVING TO A NEW PC — checklist

1. **Commit + push** the repo (gets code, masks, `dino_gate.npz`, ledgers, this file). *Ask the user first.*
2. **Manually copy** (NOT in git): `cv/dataset/`  and  `cv/runs/detect/`  → same paths on the new PC. The
   **labels in `cv/dataset/rat_field/labels/` are the irreplaceable human work.**
   - *Optional / skippable:* `D:\Field2026_analysis_out\` (`$FIELD2026_ANALYSIS_OUT_ROOT`, ~469M) is off-repo
     **provenance bulk only** — per-round selection CSVs + `measurement_context.json` + PCA figures (the audit
     trail of the harvest→select rounds). It holds **no labels/models**; the selected frames already live in
     `cv/dataset/`. Regenerable; copy only if you want the full audit record. Defaults to
     `D:\Field2026_analysis_out` on any machine unless the env var is set.
3. **Re-obtain the DINOv3 checkpoint** on the new PC (Meta license-gated): download `dinov3_vitb16_pretrain_*`
   → `~/.cache/torch/hub/checkpoints/` (or set `$DINOV3_WEIGHTS`). Without it the gate falls back to free
   DINOv2 (weaker). See `field_embed.find_dinov3_weights()`.
4. **Rebuild the `cv` conda env**: `cv/environment.yml` (+ `pip install torch torchvision --index-url
   https://download.pytorch.org/whl/cu128` for a Blackwell GPU; this PC was an RTX 3060 on cu126).
5. **ffmpeg** at `C:\ffmpeg\bin` (or set `REOLINK_FFMPEG`). Attach the E:/F: drives if you want fast harvest.

## HOW TO RUN THINGS (from `cv/`, using the env python directly)

`PY = C:\Users\Cornell\.conda\envs\cv\python.exe` — **run this directly, NOT `conda run`** (base conda
crashes re-printing child stdout under cp1252). Set `PYTHONIOENCODING=utf-8`.

**The proven active-learning round (this is the recall lever — repeat to improve):**
```
# 1. harvest a --no-detector pool from LOCAL drives (F:/E:), night hours
python scan_for_rats.py --channel CH03 --src <E:/F: night mp4s> --no-detector --every-sec 220 --max-keep 45 --out-dir scratch/pool_rN/images
# 2. FAST localize: one detector pass over the pool -> motion.json sidecar (see cv_field/ inline scripts; NOT per-frame video bursts)
# 3. select ~50 diverse/uncertain frames
python cv_field/select_frames.py --round N --budget 50 --pool scratch/pool_rN/images --use-motion \
    --seed-weights runs/detect/rat_field_div3/weights/best.pt --embed-backend dino --channels CH03 CH04
# 4. LABEL (human, GUI): prioritize CLEAR rats; skip ambiguous near-grass fragments
python label_frames.py --dir dataset/rat_field/images --proposals dataset/rat_field/proposals
# 5. retrain
python train_detector.py --data-root dataset/rat_field --name rat_field_divN --imgsz 1280 --augment --freeze 10 --lr0 0.002 --batch 8
# 6. evaluate on the frozen test (see cv_field/eval_frozen.py + the center-match/FP-review scripts)
```

**Draw/redraw a field mask (GUI, local display):**
`python cv_field/mask_field.py --channel CH03 --image dataset/rat_field/images/<a CH03 frame>.png`

## METHODOLOGY / GOTCHAS (hard-won — do not relearn these)

- **EVALUATION: use center-matching + direct FP review, NOT IoU + GT-matching.**
  - The frozen-test GT is **chronically incomplete** — the detector finds real rats the labeler misses, so
    GT-matched precision is understated. **Verify "false positives" by eye (rat vs not) before trusting a
    precision number.** `stratify_test.evaluate(match_mode="center")` is the default (size-tolerant); IoU-0.5
    wrongly rejects correct hits on tiny animals.
  - Recall is a soft **lower bound** (unknown true-rat denominator). It is the frontier; precision is ~1.0.
- **Native/high-resolution TILING was tested twice and REJECTED** — it did NOT help recall (catches ~1 rat
  div1 misses), and native detail amplifies viewpoint variance so it generalizes worse. Do not revive without
  strong new reason. Code kept: `tile_dataset.py`, `tile_infer.py`.
- **Coverage (CLEAR-rat labels) is the recall lever.** Round 1 (clear evening rats) +0.10 recall. Round 3
  (far-field/wall-base, targeted) +0.10. **Round 2 (late-night tall-grass ambiguous fragments) HURT** — do
  not label near-grass ambiguities; quality over quantity.
- **Subjects = hooded Long Evans rats**: black dorsal hood reads DARK vs NIR-bright grass (measured: rat 60 vs
  grass 18 grey; 100% darker). Grounds `field_motion polarity="dark"` and the DINOv3 gate. Rats are mostly
  VISIBLE; the hard part is viewpoint/pose/scale + partial occlusion, NOT total occlusion.
- **The frozen-test 07-06 must NEVER be trained on / threshold-tuned on** (labeling it more completely is OK —
  that improves the ruler, not the model).
- Identity is a WISER-tag job at night, not CV (monochrome, ~10 near-identical rats).

## FILE MAP (cv/cv_field/)

`field_mask.py` (valid-field geometry) · `mask_field.py` (mask GUI) · `field_motion.py` (motion proposals,
`polarity="dark"`) · `field_embed.py` (DINOv3/DINOv2 embeddings) · `select_frames.py` (active-learning
selector) · `dino_gate.py` (DINOv3 precision gate) · `stratify_test.py` (frozen-test metrics; center-match) ·
`eval_frozen.py` (baseline-vs-new comparison) · `tile_dataset.py`/`tile_infer.py` (tiling — rejected) ·
`selftest_field_mask.py`. Offline self-tests: `python cv_field/<module>.py --selftest`.
