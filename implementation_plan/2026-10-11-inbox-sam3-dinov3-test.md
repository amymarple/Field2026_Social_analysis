# In-box CH07: SAM 3 detection, SAM 3 point-prompt boxes, and a DINOv3 identity probe, scored on the user's head clicks

Date: 2026-10-11. Status: **DONE 2026-10-11** (T1–T3 run; the blind mask review awaits the user; [change log](../change_log/2026-10-11-inbox-sam3-dino.md), report `results/2026c/cv_field/reports/cv_field_inbox_sam3_dino_2026c.md`) — was PLANNED, approved by the user 2026-10-11 ("sam3/dino3 上吧 写完之后让astra audit一下 记得用
long evan rat 或者 with colorful implant (rectangular) 之类的"); to be text-audited by the Codex session astra before it
runs; amendments dated and marked before / after results. Context: `2026-10-11-identity-tracking-strategy.md` (§9 Fable
audit: SAM 3 as a point-prompt proposal labeller after a small test; frozen DINOv3 + linear probe before any trained
re-ID; §12: label individuals head-first).

## Question

The user expects that in the in-box camera (rats hundreds of px; the house fills the frame) SAM 3 and DINOv3 may work
without much labelling. Three tests answer it on existing truth, with no new labels:
1. Does SAM 3 find each rat zero-shot from a text prompt (and which prompt)?
2. Given a head point, does SAM 3 give a usable single-rat mask / box (the labelling aid)?
3. Does a frozen DINOv3 embedding of an IR head crop carry identity?

## Truth and data (read-only)

- The user's formal export `cv/configs/inbox_identity_2026c/inbox_identity_2026c_20261010_220725.csv`: blind head clicks
  (`before_reveal` true, `verdict_first` values) with identities, 20 CH07 segments; frames = the colour mid-frame and the
  IR frames 6 s and 15 s after each colour segment (`identity_page/frames/`, full resolution 2560 × 1920).
- The user's composition statement (`composition_statement_user_2026-10-11.json`): every clicked frame is complete —
  every rat in the house is clicked; the 09-10 19:50:07 segment is unusable (black).
- Classes present: SF07, SF08, SF09, SF10, SF12 (SF11 left the paddock 09-07). Colour frames identify by coban; the target
  domain is **IR** (colour results are reported separately and never mixed into the IR numbers).

**Split (fixed now):** dev = the 5 earliest usable segments (by start time); test = the remaining segments. Prompt choice
and every threshold are made on dev only; all headline numbers are on test. Frames of one segment (colour, IR +6 s, IR
+15 s) never straddle dev and test.

## Test 1 — SAM 3 zero-shot text-prompt detection

- `SAM3SemanticPredictor` (ultralytics 8.4.93, `sam3.pt`, `imgsz` 1008 set explicitly), whole frame; also a 2 × 2 tiled
  variant (tiles 1280 × 960 + overlap) as a sensitivity.
- **Prompts (pre-registered):** P1 "rat"; P2 "Long Evans rat"; P3 "rat with a colorful rectangular implant on its head";
  P4 "hooded rat". Image features computed once per frame, prompts applied on them.
- **Matching:** a mask covers a head if the clicked head point lies inside the mask (or within 15 px of it); one-to-one
  assignment heads ↔ masks by Hungarian on coverage, mask score as tie-break.
- **Metrics per frame and pooled:** head recall (heads covered by exactly one assigned mask), merged-mask rate (masks
  covering ≥ 2 heads), empty-mask rate (masks covering no head), count error (n masks − n heads), F1 of the one-to-one
  match; as a function of the mask score threshold τ.
- **Choice on dev:** the prompt and τ maximising F1 on dev IR frames; reported on test IR frames with frame-bootstrap 95 %
  CIs (resampling whole segments). All four prompts are also reported on test (descriptive).

## Test 2 — SAM 3 point-prompt masks from the head clicks (the labelling aid)

- For each clicked head on IR frames: a positive point prompt (the head), and as a variant the head plus negative points at
  the other clicked heads of the same frame. Use SAM 3's interactive (tracker / instance) predictor if ultralytics exposes
  point prompts for it, else SAM 2.1 (`sam2.1_b.pt`) as the stated fallback.
- **Metrics:** share of masks whose region contains only their own head (single-rat rate); share containing ≥ 2 heads
  (merge rate); mask-area distribution in px and in inches² via the house fit (74.8 px / in); pairwise IoU between masks
  of different rats in the same frame; box = mask bounding box, its aspect and size vs a rat's plausible size (reported).
- No threshold is tuned on test; the negative-point variant is reported side by side.
- Optional for the user's eye only (no metric depends on it): a small review page of masks / boxes on 10 test frames.

## Test 3 — frozen DINOv3 identity probe (IR)

- Crops centred on each clicked head on IR frames, square, side 2 × the median rat body length in px (from the house fit;
  ≈ 2 × 8 in × 74.8 px / in ≈ 1 200 px, capped to the frame), resized to 224; DINOv3 ViT-B/16 (repo checkpoint), CLS and
  mean-patch embeddings (both reported).
- **Classifiers:** logistic regression (linear probe, L2, C chosen by inner cross-validation inside the training folds) and
  nearest-centroid.
- **Evaluation:** primary = leave-one-segment-out (all three frames of a segment held out together); secondary =
  leave-one-day-out (09-11 held out; train 09-09 + 09-10). Metrics: top-1 accuracy, balanced accuracy, per-animal
  confusion; chance = 1 / 5 (and the majority-class rate).
- **Controls (pre-registered):** (a) position-only baseline — the same classifiers on the head pixel coordinates (u, v)
  and on the head position in the house frame (catches identity-by-place); (b) background control — crops of the same size
  at random non-head locations of the same frames, labelled with the nearest rat's id; (c) shuffled-label control.
  **Reading:** DINOv3 "carries identity" only if its leave-one-segment-out accuracy beats chance AND the position-only and
  background baselines by ≥ 15 percentage points (bootstrap CI over segments excluding 0).
- Colour crops: reported separately (expected near-trivial via coban colour), never pooled with IR.

## Outputs, rules

- Code `cv/cv_field/inbox_sam3_dino_test.py` with `--selftest` (synthetic masks / points / embeddings); run folder
  `$OUT/2026c/cv_field_inbox_sam3_dino_<ts>/` (raw SAM 3 outputs and embeddings cached); report
  `results/2026c/cv_field/reports/cv_field_inbox_sam3_dino_2026c.md` + pointer; change_log; index READMEs; CLAUDE.md line.
- The agent never judges images; truth = the user's blind clicks. No training of detectors; no labels written. GPU (cv env,
  RTX 5070 Ti); expected tens of minutes.
- Known limits stated up front: one house (CH07), ~20 segments, one labeller; IR frames are 6 s and 15 s after colour, so
  piles are mostly still and the same configuration appears twice per segment (hence segment-level holdout).

## Amendment 1 — 2026-10-11, before results: text review by the Codex session "Yolo_identity"

(The review was queued to astra first; astra's session was not open, so the user's open Codex session Yolo_identity
reviewed it — reply pasted by the user.) Adopted in full:

1. **What the truth can show.** Head clicks prove only head coverage, not that a mask / box is one whole rat; scoring a
   point-prompted mask by the same point is close to self-validation (more so with negative points at the other heads).
   → T1/T2 headline claims are restricted to **head-point exclusivity** (exactly-one-head coverage, merge and empty
   rates). Any claim that SAM 3 gives **usable single-rat boxes** requires a **blind mask review by the user**: 40 masks
   (T1 best prompt and T2 positive-point / negative-point variants, stratified by pile size, from test segments), shown
   without method or score, each judged "one whole rat / part of a rat / two or more rats / not a rat"; the page is made
   after the masks exist; the agent never judges them.
2. **Grouping.** Adjacent flashes can show the same still pile → the unit is a **still episode**: consecutive segments of
   the same house are one group if the WISER house roster is unchanged between them and every roster animal's head-IMU
   state is still for ≥ 90 % of the seconds between them (`imu_seconds_cache`). All holdout, bootstrap and inner CV use
   these groups. The dev set (T1/T2 prompt and τ choice only) = the groups containing the 5 earliest segments; T1/T2
   headline numbers on the remaining groups. **T3 does not use the dev split**: it is evaluated leave-one-group-out over
   all groups, with its only hyper-parameter (logistic C) chosen by inner grouped CV inside each training fold.
3. **T3 decision rule.** "DINOv3 carries identity" (engineering gate) = point estimate ≥ 15 percentage points above BOTH
   chance and the best control, AND the grouped-bootstrap 95 % CI of that difference excludes 0; "a gain of ≥ 15 pp is
   established" only if the CI lower bound ≥ 15. Leave-one-group-out success alone is not a cross-day claim; the
   leave-one-day-out result (09-11 held out) is reported for that.
   **Crops:** primary = head-centred square of side 4 in (≈ 300 px at 74.8 px/in) resized to 224, so a crop rarely holds
   another head; the 1 200-px body-scale crop becomes a sensitivity. **Controls replaced by matched ones:** (a) position-only
   (u, v and house-frame position) classifiers; (b) **head-masked control** — the same crop with a disc of radius 1.5 in at
   the head filled with the crop's median grey (tests context / neighbours / background); (c) **position-matched control** —
   a crop at the same image position from another group's frame, labelled with the original rat (tests place); (d)
   shuffled labels. The best of (a)–(c) is "the best control".
4. **Fixed now:** primary embedding = CLS, primary classifier = logistic regression (mean-patch and nearest-centroid
   secondary); crops clipped to the frame and padded with the frame's median grey; T1 matching: a head inside two masks goes
   to the higher-score mask, a mask with ≥ 2 heads counts as merged and is matched to one head only (its highest-score
   pairing), mask–head ties broken by mask score then area; tiled variant: cross-tile duplicates merged by mask IoU ≥ 0.5;
   T2 fallback: SAM 2.1 (`sam2.1_b.pt`) only if the installed ultralytics exposes no point prompts for SAM 3 (checked and
   reported first); CIs = paired grouped bootstrap (resampling groups, 2 000 draws); multiple comparisons: the primary
   comparisons are pre-named (T1: chosen prompt on test; T2: positive-point exclusivity; T3: CLS + logistic vs best
   control), the other prompts / variants are descriptive only; mask areas are reported in **pixels only** (one scale
   cannot convert piles at different heights).

## Amendment 2 — 2026-10-11, before results: implementation details fixed by the agent in the driver

Written into `cv/cv_field/inbox_sam3_dino_test.py` before any metric was computed. The only earlier GPU call was an API
probe on one frame (load the models, one point prompt, two text prompts; no metric, nothing kept). Nothing here changes
a rule of the plan or of amendment 1; it fixes what they left open.

1. **Truth record.** The blind clicks are the clicks with `before_reveal` true, not legacy, and a `verdict_first`
   (`first_*` in the CSV); position, animal and frame are taken from `first_*`. That gives 284 blind clicks; the 10 clicks
   made after a reveal are not used. So two IR frames whose only clicks came after the reveal drop out: 09-10 14:16:13
   `ir_p15` and 09-10 14:32:43 `ir_p15`. A blind click without an animal (2) counts as a head for T1 / T2 but is left
   out of T3. Frames where one label occurs twice (09-11 09:54 `ir_p06` SF10 × 2, `ir_p15` SF07 × 2) are kept as
   labelled; T3 also reports a sensitivity run without those clicks.
2. **Still-episode groups.** The usable segments are ordered by start. Between consecutive segments the interval is
   [last frame time of segment i, colour-frame time of segment i + 1].
   - **Roster unchanged:** the `house_2` set in the phase-0 run's `box_occupancy_1s.csv.gz` is the same in every
     second of that interval.
   - **Still:** for every roster animal, the IMU still share = (seconds with `ok` and `still`) / (all seconds of the
     interval) is ≥ 0.90. A missing or failed IMU second counts as not still.
   - Two segments are joined when both hold; chains of joined segments form a group. The table also reports the
     share computed over `ok` seconds only (descriptive).
3. **T1 detection.**
   - **Settings:** SAM 3 score floor 0.01, the predictor's own NMS (IoU 0.7). τ grid = {0.01, 0.02, 0.03, 0.05,
     0.075, 0.10, 0.15, 0.20, …, 0.95}.
   - **Head to mask:** a head goes to the covering mask with the highest score, then the smaller area.
   - **Mask to head:** a mask chosen by several heads keeps the nearest of them (distance to the mask, then distance
     to the mask centroid).
   - **Counts:** TP = masks that keep a head. P = TP / n masks, R = TP / n heads, F1 = 2 TP / (n masks + n heads).
   - **Head-point exclusivity X** = (heads kept by a mask that covers no other head) / n heads.
   - **Mask classes:** merged = a mask covering ≥ 2 heads; empty = a mask covering none.
   - **Choice:** ties go to the higher τ, then the lower prompt number.
   - **Tiled sensitivity:** 2 × 2 tiles of 1344 × 1008 px at x {0, 1216}, y {0, 912} (overlap 128 × 96 px). Tile
     masks are mapped to the frame. At each τ, among the masks ≥ τ in score order, a mask joins an already-kept
     mask from another tile when their IoU is ≥ 0.5 (union, the higher score).
4. **T2 point prompts.** Ultralytics 8.4.93 exposes point prompts for SAM 3: `SAM3Predictor`, the interactive predictor,
   is a `SAM2Predictor` subclass with `points` / `labels`. So the SAM 2.1 fallback is not triggered.
   - **Model build:** the model comes from `sam3.pt` with `imgsz` 1008. `build_interactive_sam3` is called with
     `compile=None`, because the predictor passes `compile=False`, and the backbone's `is not None` check then calls
     `torch.compile`, which fails without Triton.
   - **Output:** `multimask_output` False, the default mask threshold.
   - **Prompts:** positive = the head alone. Negative variant = the head (label 1) plus every other blind head of the
     frame (label 0).
5. **T3 identity probe.**
   - **Crops:** side 299 px (4 in × 74.8 px/in) primary, 1197 px sensitivity, resized to 224 with INTER_AREA,
     ImageNet normalisation.
   - **Model:** DINOv3 ViT-B/16 from the local hub copy and the repo checkpoint. CLS = `x_norm_clstoken`, mean-patch
     = the mean of `x_norm_patchtokens`.
   - **Logistic regression:** StandardScaler + multinomial L2 logistic regression (lbfgs, `max_iter` 5000). C ∈
     {0.001, 0.01, 0.1, 1, 10, 100} is chosen by an inner GroupKFold over the training groups (min(5, n groups)
     folds, accuracy; ties go to the smaller C).
   - **Nearest centroid:** cosine on L2-normalised embeddings, or Euclidean on standardised coordinates for the
     position controls.
   - **Head-masked control:** disc radius 112 px (1.5 in), filled with the crop's per-channel median.
   - **Position-matched control:** for each click, one IR frame is drawn uniformly (seed 20261011) from the other
     groups' IR frames.
   - **House-frame position:** the clicks run's proper similarity, refitted on its `fit_points_primary.csv` (89
     points).
   - **Shuffled labels:** 20 global permutations, CLS + logistic regression, leave-one-group-out.
   - **Best control:** the highest point accuracy among (a) u, v, (a) house frame, (b) head-masked and
     (c) position-matched, under the same classifier (and the same embedding for (b), (c)).
   - **Bootstrap:** 2 000 draws of groups with replacement (seed 20261011), percentile 95 % CI. For leave-one-day-out
     the draws are over the 09-11 groups.
   - **Verdict:** the amended rule is applied to the leave-one-group-out primary. Leave-one-day-out gets the same rule,
     reported as the cross-day result.
6. **Mask review.**
   - **Sample:** 40 masks from the test-group IR frames: 14 T1 (chosen prompt and τ, whole frame), 13 T2 positive
     and 13 T2 negative, with the T2 heads disjoint between the two variants.
   - **Strata:** pile size of the mask's head, from single linkage of the frame's blind heads at 6 in = 449 px:
     1, 2–3 and ≥ 4, plus "no head" for T1 masks that cover no head. Strata are filled round-robin with a seed; the
     items are then shuffled.
   - **Display:** each item shows the whole frame and a zoomed crop with the mask tinted (a toggle hides it). The
     page never shows the method, the score or a head point.

## Amendment 3 — 2026-10-11, before any T1–T3 result (only the grouping table had been computed)

The primary join rule (amendment 2 item 2) joined **no** pair, so the 20 usable segments are 20 groups (dev = the 5
earliest). Two kinds of split happen only because an IMU is missing, not because the measured animals moved:
- **09-11 afternoon:** the pairs 14:09:55 → 14:17:58 → 14:43:45 are 8 and 25 min apart with the roster unchanged.
  SF07–SF10 are still in ≥ 92 % of the seconds, but SF12's head IMU is never ok that afternoon.
- **09-10 16:30:56 → 17:59:35:** no animal has an ok IMU second.

Since the rule cannot verify stillness without an IMU, the primary grouping stays as pre-registered. A **sensitivity
grouping** (`group_alt`) is added:
- **Rule:** an animal with no ok IMU second in the interval is not counted. Every other roster animal must still be
  still in ≥ 90 % of all the seconds, and at least one roster animal must have an IMU.
- **What is re-run:** the T1 / T2 headline test CIs are recomputed with `group_alt` resampling. The T3 primary
  (CLS + logistic, 4-in crop) and its controls are re-run leave-one-`group_alt`-out with the decision rule. The
  dev / test split is unchanged.
- **Status:** descriptive only; the pre-named primaries use the primary grouping.

*Disclosure note (2026-10-11, written after results; it changes no rule).*
- **Probe before amendment 2:** the API probe on one IR frame (09-10 12:27:03, IR + 6 s) showed raw SAM 3 scores of at
  most 0.59 for "rat" and at most 0.021 for "Long Evans rat". No head point was matched and no metric was computed.
- **Effect on the τ grid:** its low end (0.01, 0.02, 0.03) was set with that in view, so that a low-scoring prompt can
  still be scored.
- **Execution:** the first GPU job stopped after 8 frames when its session ended; it was resumed from the atomic
  per-frame caches, and no frame was recomputed.
- **Interpreter:** scipy's L-BFGS-B crashes natively in the cv env (Windows 0xc06d007f), so the score / review / report
  phases ran in base Python, keeping the lbfgs solver.
