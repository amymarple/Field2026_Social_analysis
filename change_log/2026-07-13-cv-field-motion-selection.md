# cv_field — motion-aware selection + motion-assisted labeling (2026-07-13)

Adds MOTION as the rat-content signal for cv_field frame selection and labeling, fixing the whole-frame
homogeneity found in the round-1 analysis. Plan: `implementation_plan/2026-07-13-cv-field-motion-selection.md`.

## Why

The whole-frame DINOv3 selector was ~equivalent to random on a single homogeneous night (selected pairwise
similarity 0.853 vs random 0.850; 42% of embedding variance was just CH03-vs-CH04). On the night-IR field the
background is static and the rats move, so a short temporal burst isolates the rats.

**Validated on real 06-28 footage before building:** motion is ~378× denser inside labeled rat boxes than
background, hits ~100% of labeled rats, empties stay quiet (~0.17%). Embedding the **motion crop** vs the whole
frame cut mean pairwise DINOv3 similarity **0.926 → 0.559** — the selector now sees rat pose/position/count
variation, not the static background.

## What changed

- **`cv/cv_field/field_motion.py`** (new) — burst → temporal-median background → peak abs-diff → robust
  threshold (mean+3σ, noise floor 18) → morphology → connected-component candidate boxes + motion score +
  padded union crop. `frame_motion()` pulls the burst from source (the only IO). Pure core self-tested with a
  synthetic moving blob (`--selftest` / `selftest_field_motion.py`).
- **`cv/cv_field/field_embed.py`** — `embed_frames(..., crops=…)`: dino/gray embed a per-frame crop instead of
  the whole frame (yolo rejects crops); `_read_bgr` guards degenerate crops.
- **`cv/cv_field/enrich_motion.py`** (new) — retrofits a `<pool>/motion.json` sidecar + editable
  `proposals/<stem>.txt` onto an existing single-still pool (parses source+offset from each frame name).
- **`cv/cv_field/select_frames.py`** — `--use-motion` embeds the motion crop; `--quiet-frac` (default 0.25)
  RESERVES low/no-motion + random frames so the detector keeps seeing still/resting rats and true negatives
  (the anti-"moving-rat-specialist" safeguard); `--motion-json` override. Motion params recorded in the run's
  `measurement_context` (`use_motion`, `quiet_frac`, `n_quiet`). Non-motion path byte-unchanged.
- **`cv/label_frames.py`** — `--proposals <dir>`: an UNDECIDED frame pre-loads **editable** motion boxes in
  magenta with a "review before confirm" banner; written to `labels/` only when the human advances. Proposals
  live in a separate dir and are **never** auto-promoted / used as pseudo-labels. Shared with cv_shelter via
  behavior-preserving defaults (no `--proposals` ⇒ identical to before).

## Contract (per user direction)

Motion = high-recall PROPOSAL + crop-localization only. **Human-corrected boxes remain the only training
labels; no raw-motion pseudo-labels.** A stratified quiet/random stream is always reserved so the training set
isn't biased toward conspicuously moving animals.

## Verification

- Offline PASS: `field_motion.py --selftest`, `selftest_field_motion.py`, `selftest_field_select.py`
  (unchanged non-motion path); `py_compile` clean across the touched files.
- Real data: motion localization 378× / ~100% box recall / quiet empties; motion-crop diversity 0.926→0.559;
  end-to-end `enrich_motion → select_frames --use-motion --dry-run` on a 30-frame test pool.

## Weather fragility — 07-05 real-night check (negative result)

Ran the pipeline on a NEW night (07-05 evening 21–23, CH03/CH04) from a **local USB copy** (`E:\2026-07-05`) —
local harvest was fast (209 frames) where the Q: harvest had stalled. But motion enrichment flagged **209/209
"with motion", 0 quiet**, so we cross-checked against the trained detector (rat reference):

- **corr(motion-box count, detector-rat count) = 0.02** (none). Overall motion **8.4 boxes/frame** vs detector
  **0.4 rats/frame**; on high-motion frames motion says **21.9** while the detector confirms **0.4** (~21
  spurious boxes/frame). Motion box areas skew **below** real rats (median 0.0004 vs labeled 0.0011).
- Conclusion: **07-05 evening motion is background-dominated (wind/rain/vegetation), not rats** —
  `field_conditions.yaml` logs rain+overnight fog across the 07-03→07-04 spell. The calm-night threshold
  (mean+3σ, 18-floor, 12 px min blob) is **too permissive under weather**. Also the detector sees ~0.4
  rats/frame, so 07-05 evening is a **rat-sparse** night anyway.
- **So: do NOT use the 07-05 motion proposals as-is** (they'd be mostly noise to delete). Motion-assist is
  **weather-sensitive** and needs hardening before blanket use — the user's caution was correct.

**Fixes (next):** add a **shape + motion-coherence gate** (rats move coherently across the burst; vegetation
flickers — cv_attempt used optical-flow coherence) and a frame-relative min/max blob area; and/or
**weather-gate** motion-assist via `field_conditions.yaml`. Validate any gate across a calm night (06-28) AND
a noisy night (07-05) before trusting proposals. Until then, restrict motion-assist to calm, rat-active nights.

## Rebuild — locally-normalized spatiotemporal generator (2026-07-13, cont.)

The `field_motion` global-blob core was **rebuilt** (design panel → synthesis, plan
`implementation_plan/2026-07-13-field-motion-rebuild.md`) after the 07-05 base-rate failure. The new core:
scalar illumination cancel → temporal-median background → **ambient-normalized z** (residual ÷ a large-scale
spatial blur of temporal activity — vegetation is area-wide so it survives the blur → high σ → suppressed;
a rat is compact so its own activity is diluted → sits on the surrounding ambient → high z) → rat-scale
top-hat → permissive per-frame candidates → **deterministic tracklet linking** → survival by TRANSLATION or
HOLD-POSITION persistence. Interface is a strict superset (`box_scores/tracklets/n_tracklets` added; old kwargs
accepted); `select_frames --use-motion`, `enrich_motion`, `union_crop`, `boxes_to_yolo` unchanged.

**Debugging surfaced a real principle** (recorded so it isn't relearned): *any* per-pixel noise estimate drawn
from the rat's own pixels is contaminated — a `|R|`-median σ absorbs **dwelling** rats (dropped 06-28 recall to
0.01), a frame-difference σ absorbs **fast** rats. Only normalizing by the **ambient (spatial-blur) activity**
is robust to both. Two alignment fixes mattered too: `abs` polarity (a dwelling rat's motion is the *bright*
residual when it leaves; dark-only misses it) and emitting the proposal at the burst's **first** frame (the
frame the pool still + its label correspond to; a moving rat has left its labeled spot by the burst centre).

**Validation (real footage) — a characterized recall/precision tradeoff, not a single point.** The two levers
that matter are polarity + candidate z-bar; measured endpoints on the SAME code:

| operating point | 06-28 calm recall (Gate A) | 07-05 noisy proposals/frame (Gate B) |
|---|---|---|
| **default** — `dark`, z_lo 2.5, blur 4× (balanced) | **0.42** | **0.65** (93/209 frames; corr 0.28) — 13× < old |
| `abs`, z_lo 2.0, blur 3× (recall-first) | 0.50 | 2.9 (207/209 frames; corr 0.14) |
| old global method (for reference) | 0.99 | 8.4 |

The **default** gives a real base-rate win — **13× fewer weather false positives** than the old method (0.65 vs
8.4/frame, well under the 1.5 target) — *while* keeping 0.42 calm-night recall. The missed rats are largely
**still/foraging** animals a motion generator cannot see anyway, covered by the stratified **quiet/random
reserve** + human labeling (by design). The `abs`-polarity / lower-`z_lo` knobs trade toward recall (0.50) but
reintroduce weather FPs (bright wet-glint → 2.9/frame), so they are exposed as arguments, not the default.
(An intermediate rebuild that over-dilated σ hit 0.04/frame on 07-05 but only 0.01 recall — a dead end,
recorded so it is not retried.) The anchor=0 fix (emit at the burst's first frame = the labeled frame) is a
free recall gain kept in all points. The operating point is the researcher's call.
- **Self-test:** all cases pass (calm localize · static quiet · windy base-rate O(1) & << old · fine-texture
  0 survivors · part-stationary · fast-with-dropout).

## Not done / next

Motion-aware **harvest** (one streaming pass, off a LOCAL copy / BioHPC — Q: is too slow, golden rule) to
replace the retrofit enrichment and re-run the stalled 06-30 night; freeze 07-04 as an untouched labeled
multi-night test set; then a `--use-motion --proposals` round compared (matched precision) against the
whole-frame rounds.
