# cv_field — motion-aware selection + motion-assisted labeling

**Date:** 2026-07-13 · **Status:** implemented (verifying) · **Direction:** cv_field (whole-field CH01–CH04)

## Context / why

Round-1 analysis showed the whole-frame DINOv3 selector was **not** buying diversity on a single homogeneous
night: raw cosine similarity of the selected 80 (0.853) ≈ random 80 (0.850), whole-pool 0.848, and **42% of the
embedding variance was just CH03-vs-CH04** — i.e. the embedding was dominated by the static background/camera,
not the rats (the user's labeling intuition, confirmed). On the night-IR field the background is large but
static and the rats move, so **motion** isolates the rat-relevant signal.

Validated on real 06-28 footage before building: motion is **~378× denser inside labeled rat boxes** than
background, hits **~100% of labeled rats**, and empty frames stay quiet (~0.17% of pixels). Embedding the
**motion crop** instead of the whole frame cut mean pairwise similarity **0.926 → 0.559** (far more rat-content
spread).

## Approach (constraints from the user)

Motion = a **high-recall proposal + crop-localization** layer for the DINOv3 selector and an **editable**
label pre-fill. **Human-corrected boxes remain the only training labels; motion boxes are never pseudo-labels.**
Keep a **stratified quiet/random stream** so the detector isn't biased toward conspicuously moving animals.

- `cv/cv_field/field_motion.py` — burst → temporal-median background → peak-diff → robust threshold →
  candidate boxes + motion score + padded union crop. Pure core is numpy+cv2, self-tested with a synthetic
  moving blob.
- `cv/cv_field/field_embed.py` — `embed_frames(..., crops=...)`: dino/gray backends embed a per-frame crop
  (yolo rejects crops).
- `cv/cv_field/enrich_motion.py` — retrofit a motion sidecar (`<pool>/motion.json`) + editable proposals
  (`proposals/<stem>.txt`) onto an existing pool. (For a NEW night, a motion-aware harvest should do this in
  one streaming pass off a LOCAL copy / BioHPC — Q: is too slow, per the golden rule.)
- `cv/cv_field/select_frames.py` — `--use-motion`: embed the motion crop; `--quiet-frac` (default 0.25)
  reserves low/no-motion + random frames; motion params recorded in `measurement_context`.
- `cv/label_frames.py` — `--proposals <dir>`: undecided frames pre-load **editable** motion boxes (magenta,
  "review before confirm"); written to `labels/` only on advance. Never auto-promoted; shared with cv_shelter
  via behavior-preserving defaults.

## Verification

- Offline: `field_motion.py --selftest`, `selftest_field_motion.py`, `selftest_field_select.py` (unchanged
  non-motion path) all PASS; `py_compile` clean.
- Real data: motion localization (378×), motion-crop diversity (0.93→0.56), and an end-to-end
  `enrich_motion → select_frames --use-motion --dry-run` on a 30-frame test pool.

## Open / next

- Motion-aware **harvest** (one-pass, local/BioHPC) to replace the retrofit enrichment; re-run the stalled
  06-30 night that way. Freeze 07-04 as an untouched labeled multi-night test set. Then a round with
  `--use-motion` + `--proposals` and compare (matched-precision) vs the whole-frame rounds.
