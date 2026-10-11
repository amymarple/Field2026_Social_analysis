# In-box CH07: SAM 3 detection, SAM 3 point-prompt boxes, and a DINOv3 identity probe, scored on the user's head clicks

Date: 2026-10-11. Status: **PLANNED** — approved by the user 2026-10-11 ("sam3/dino3 上吧 写完之后让astra audit一下 记得用
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
