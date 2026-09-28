# field_motion rebuild — locally-normalized spatiotemporal proposal generator

**Date:** 2026-07-13 · **Status:** implemented + validated · **Direction:** cv_field

## Context / why (not a threshold tune)

The first `field_motion` used a GLOBAL frame-level threshold (temporal-median diff > mean+3σ, fixed floor).
It localized rats well on the calm 06-28 night (~378× rat-density, ~100% box recall) but **collapsed on the
windy/wet 07-05 night**: correlation(motion boxes, detector rats) = 0.02, 8.4 boxes/frame vs 0.4 rats. This is
a **base-rate problem** — a low per-pixel false-positive rate × an enormous vegetated background floods the
frame — and no global threshold can fix it (rats and wind-blown leaves have overlapping intensity-swing
magnitudes). The correct role of motion is **not** rat/non-rat classification; it is to shrink the search space
and emit **high-recall, coherence-scored candidate tracklets** for DINOv3 crop selection, editable label
proposals, and YOLO-missed discovery. Precision is downstream.

## Design (multi-perspective panel → synthesis)

A 3-lens design panel (per-pixel local normalization · spatiotemporal tracklet coherence · flow/saliency) +
a synthesis converged on a **locally-normalized spatiotemporal generator**:

1. **Scalar illumination-flicker cancel** — subtract each frame's own level (kills uniform IR-AGC steps).
2. **Temporal-median background + dark-polarity residual** (rats are darker than IR ground).
3. **Per-pixel temporal-MAD z-score (the base-rate fix).** Each pixel is judged against ITS OWN noise scale
   (σ = 1.4826·MAD, floored); the σ map is surround-MAX dilated so no lucky-quiet pixel inside a flickering
   patch fires. The decision constant is fixed in z-units but *locally-varying in intensity* — full
   sensitivity on static ground, auto-desensitized on chronically-active vegetation. On a calm burst every σ
   sits at the floor, so z reduces algebraically to the old sensitive test ⇒ **calm recall preserved by
   construction**.
4. **Rat-scale white top-hat** on the peak-z map — annihilates any response on structures larger than a rat.
5. **Permissive per-frame candidates → deterministic gap-tolerant tracklet linking → survival by
   TRANSLATION (net displacement + heading coherence, ≥2 steps) OR PERSISTENCE-while-holding-position**
   (a slow/still rat). This changes the FP unit from "a pixel over threshold in one frame" to "a compact
   rat-sized blob that persists and translates coherently" — background flicker with per-frame probability p
   fakes a coherent track only at ~p^S, the exponential base-rate crusher. Each survivor carries a coherence
   score for downstream ranking.

**Interface unchanged (strict superset):** `motion_from_burst` returns the same
`{score,n_blobs,boxes,mask,H,W,thr}` + new `box_scores/tracklets/n_tracklets`; accepts old kwargs
(`noise_floor/min_blob_area/k_sigma`, ignored); `frame_motion` burst 1.2→2.0 s at fixed 12 fps; `union_crop`
/ `boxes_to_yolo` unchanged. `enrich_motion.py` + `select_frames --use-motion` keep working verbatim.

## Validation

- **Synthetic self-test** (numpy, deterministic): calm translating blob localized; static quiet; **windy
  base-rate case** (blob + per-pixel high-variance vegetation + global brightness step) → O(1) proposals at
  the true rat AND far fewer than the old global method on the same frames; fine vegetation texture → 0
  survivors; part-stationary and fast-with-dropout rats survive. All PASS.
- **Gate B — noisy FP collapse (07-05, real):** mean proposals/frame **8.4 → 0.04** (8/209 frames fire),
  corr with detector **0.02 → 0.36**. PASS.
- **Gate A — calm recall preserved (06-28, labeled):** new box-recall vs the old global method's on the same
  frames (still rats legitimately produce no motion, so compared to old, not to 100%). [see change_log]

## Notes / residual

Rats fully static for the whole burst are out of scope for any background-subtraction motion (YOLO's job).
A rat-sized wind-dragged foliage mass translating coherently is the acknowledged residual FP for downstream
human/DINOv3/YOLO adjudication. Ledger: `change_log/2026-07-13-cv-field-motion-selection.md`.
