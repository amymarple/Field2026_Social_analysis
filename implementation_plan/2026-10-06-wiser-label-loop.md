# WISER-guided labelling loop for the CH01/CH02 rat detector (round 1 + the loop in the undergrad's repo)

Date: 2026-10-06. Status: **A, B and C DONE 2026-10-06** (approved "做吧"; amendments 1–3 before results, 4 after the first
package build; kit `D:/Field2026_analysis_out/2026c/wiser_pixel_kit_20261006_1952/`, package
`D:/Field2026_analysis_out/2026c/label_round1_20261006_2015/`, report
`results/2026c/cv_field/reports/cv_field_wiser_label_loop_round1_2026c.md`, change log
`change_log/2026-10-06-wiser-label-loop.md`); **C PENDING** (the loop code, built by another agent in
`D:/Documents/GitHub/social-field-rat-wiser-loop/`). Earlier status: PLANNED — design answers from the user 2026-10-06 (new clone + branch of the undergrad's
repo; packages built on D: and copied to Q: by the user; round 1 = 400 training frames + test set extended to 100;
training both on a Windows PC and on BioHPC); runs only after the user approves this file. Pre-registered before any
result; amendments dated and marked *before* or *after results*. Data locations: `cv/cv_field/DATA_MAP_c1yolo_wiser.md`.

## Goal

Close the active-learning loop for the cohort-3 CH01/CH02 panorama detector: **model → WISER-guided frame selection →
labelling with a WISER overlay (blind first) → training → evaluation on a frozen blind test set → next round**, run by
the undergrad in her own repo (`social-field-rat`). This repo supplies what needs our caches (WISER, calibration,
frame corrections) once, as a self-contained **WISER pixel kit**; her repo holds the loop code.

Facts this rests on (do not re-derive): YOLO v5 (`rat_m_v5`) transfers to cohort-3 CH01 at night; the WISER → paddock
map is accepted on CH01 09-06 21–22 h (test median 4.4 in, 88.5 % vs control 2.9 %, lag 0 s; `2026-10-05-wiser-
assisted-yolo-p0.md`); CH01 occlusion geometry v2 (`2026-10-06-ch01-occlusion-geometry.md`: hidden 5 %, partly 5 %,
clear 51 %, ambiguous 39 % of suspected-miss episodes); house_1 cohort pose `cv/configs/house1_cohort_pose_2026c.json`;
camera rules `cv/cv_field/CAMERA_GEOMETRY_2026c.md` (raw pixels of different days are not comparable — always go
through the correction table; the table covers CH01–CH06 at night only).

## A. WISER pixel kit (this repo; `cv/cv_field/build_wiser_pixel_kit.py`)

For every usable night (night D = D 21:00 → D+1 04:20, 08-30 → 09-11, the population change 09-11 19:40 cut) and for
CH01 and CH02:
1. **Per-camera geometry.** Support polygon; occluders as in the CH01 occlusion v2 (poles from that camera's own
   09-18 edge labels where labelled, else cylinders; house_2 calibration pose; house_1 cohort pose); a 2-in visibility
   mask. CH02 gets the same treatment as CH01 (its 09-18 labels: A0, A4, B0–B4, both houses).
2. **Map validation per camera-night.** From the round-1 candidate pool (B2 below): v5 boxes conf ≥ 0.5 vs WISER
   animals outside the houses; pass if the median distance ≤ 14 in **and** within-14-in share ≥ 2 × the +1 h-shifted
   control's. Camera-nights that fail are kept for labelling but get no WISER-dependent quota and no overlay.
3. **Table at 1 Hz** per camera-night: time, animal, tracked flag, in-house-zone flag, upright-pano pixel (u, v) at
   z = 60 mm via the accepted map + the camera's calibration + the night correction, radius in px of 14 in, hidden
   share (visibility mask), in-support flag, motion state (V3 speed + head-IMU state), the camera-night validation
   flag. Plus `kit.json` (versions, commits, map, sha256 of every input) and a README.
4. Out: `$OUT/2026c/wiser_pixel_kit_<ts>/` (≈ 150 MB), copied by the user to Q: with the label package.

Population rules carried in the kit: before 09-11 19:40 every animal in the paddock is tagged except SF12 on night
08-30 (no track), SF11 while untracked (09-02 00:03 → 08:20) and after its tag came off (09-07 06:10:45; the animal
stayed in the paddock). Per second the kit says whether **all** animals are accounted for (`all_tracked`); only then
can "no WISER animal near a box" or "all animals in houses" be used.

## B. Round-1 selection (this repo, run once; the same logic moves to her repo in C)

1. **Nights and times:** CH01 and CH02, nights 08-30 → 09-10 (+ 09-11 before 19:40 is day, so none) **minus the frozen
   test night 09-05**; 21:00 → 04:20; handling windows ± 5 min removed; calm and rain nights both (rain is real
   footage; WISER there feeds strata only, not the miss quota — the failure audit's rain caveat).
2. **Candidate pool:** per camera ≈ 1 500 times — 1 200 stratified by WISER (count of tagged animals outside the
   houses 0 / 1–2 / ≥ 3 × motion still / active / locomoting × night × hour) + 300 uniform random; ≥ 10 s apart.
   Frames grabbed with `cv/cv_field/grab_frames.py` (upright, PNG, native), v5 at imgsz 1280, conf ≥ 0.05 → cached
   (`pool/` + `pool_detections.csv.gz`) — never re-grabbed.
3. **Per-frame scores** (validated camera-nights only for 3a–3c): (a) **visible suspected miss** = a tracked animal
   outside the houses, inside the support, hidden share 0 robustly (± 7 in), no box conf ≥ 0.25 within 20 in;
   (b) **social** = ≥ 2 tagged animals in view within 20 in of each other; (c) **hard negative** = `all_tracked` and
   every animal in a house zone, or a box at a fixed spot the user verdicted "object"; (d) DINOv3 embedding (the
   `cv/cv_field` field_embed code) for diversity.
4. **Quotas per camera (200):** visible suspected miss 60 · WISER strata 50 · social 30 · hard negative 20 · DINOv3
   diversity 20 (k-means on the pool, nearest unselected frame to each centroid) · uniform random 20. **Rule fixed
   now for the user's clip review:** if the review is exported before B runs, p = share of "visible_missed" among the
   reviewed episodes (unsure excluded): p ≥ 0.5 → 60; 0.25 ≤ p < 0.5 → 40; p < 0.25 → 20; the difference goes to the
   WISER strata. Not exported yet → 60. Spacing ≥ 10 s per camera, ≤ 25 frames per camera-night, one frame per
   merged event (same-animal misses bridged over gaps ≤ 5 s, simultaneous animals = one event).
5. **Test set to 100:** + 60 frames on night 09-05 (CH01 30 + CH02 30) by the existing `select_pano_targets.py`
   stratified test rule (zero / few / many) and the existing 40 (`cv/dataset/rat_pano_test/`). No prelabels, no
   WISER sidecar, never in training, labelled blind; the 40 existing frames are not re-grabbed.
6. **Package** `$OUT/2026c/label_round1_<ts>/`: `train/images/*.png` + editable `*.txt` (v5 prelabels) +
   `train/prelabels_v5/*.txt` (pristine copy, for provenance) + `train/wiser/*.json` (sidecar: animals with pixel,
   radius, id, in-house, hidden share, tracked; occluder polygons; camera-night validation; note) +
   `train/manifest.csv` (camera, video, frame, t_pc, night, quota, reason, scores); `test/images/*.png` only +
   `test/manifest.csv`; `MANIFEST_sha256.csv`; `README.md` (how to copy to Q:, rules). Frame names keep her
   convention `<video stem>_f<frame>.png`.

## C. The loop in her repo (new clone, branch `wiser-loop`; additive — nothing of hers is changed)

New folder `computer_vision/wiser_loop/` (the pool/score/select/package logic of B, ported so it reads only the kit
and videos), plus:
- **`label_frames.py --wiser`** (an option on her labeller, default off): **blind first** — the overlay stays hidden
  until the labeller marks the frame "scan done" (`d`); `w` then toggles the WISER circles (id, ± 14 in) and the
  occluder outlines ("hidden — do not box"). Every box gets a provenance record in `<stem>.prov.json`:
  `prelabel_kept` / `prelabel_edited` / `new_blind` / `new_after_wiser`, optional tag id (assign with keys). Frames
  listed in a test manifest refuse both prelabels and the overlay.
- **`select_round.py`** — given her latest weights, the kit, a video root and the quota config → the next round's
  package (same format as B6). **`eval_test.py`** — centre-match AP, recall at P ≥ 0.8, max-F1 per camera with
  bootstrap CIs on the frozen test set (the matcher of `cv/cv_field/sam3_vs_yolo_c1.py`). **`wiser_loop_paths.yaml`**
  with `windows` and `biohpc` profiles (video root, kit, package and dataset roots, weights); a slurm wrapper next
  to her `slurm/train_yolo.slurm`. **`README_wiser_loop.md`**: label → `check_labels` → `prepare_dataset` (+ the new
  folder) → train → `eval_test` → `select_round` → label.
- Tests: `--selftest` for the selector, the overlay logic (blind lock, provenance states, test-set refusal) and the
  evaluator, on synthetic data.
- Local commits on `wiser-loop` only; the user / undergrad push and merge.

## Rules

Machine boxes and WISER positions are proposals; every box in the dataset is a human decision with its provenance
kept. WISER never makes a negative: an empty frame is the labeller's verdict. The test set is labelled blind (no
prelabels, no overlay) and never used for training, selection or tuning. Only what is visible gets a box (occluded
animals do not). The agent never judges images. This repo's outputs off-repo under `$OUT/2026c/`; Q: is written only
by the user.

## Order and cost

A (geometry for CH02 + kit table) and B2 (pool: ≈ 3 000 grabs ≈ 45–60 min + v5) first; A2 validation needs the pool;
then B3–B6 (minutes) → package for the user. C after the user gives the repository's remote (in parallel with the
labelling of round 1). GPU only for v5 on the pool and DINOv3 embeddings.

## Outputs, paperwork

Reports `results/2026c/cv_field/reports/cv_field_wiser_label_loop_round1_2026c.md` (+ pointer), code
`cv/cv_field/build_wiser_pixel_kit.py`, `cv/cv_field/select_label_round1.py` (both `--selftest`); change_log, both
index READMEs, CLAUDE.md cv_field map, HANDOFF, data map.

## Amendment 1 (2026-10-06, **before results**: written after the code and its self-tests, before the pool was drawn)

Shared file formats for A/B (fixed by the coordinator so that part C, built in parallel by another agent, can code
against them): kit `<CAM>/support.json`, `<CAM>/occluders.json` (both `by_night`), `<CAM>/<night>.csv.gz` with the columns
`t_pc, animal, tracked, in_house, u, v, r_px, hidden_share, in_support, motion, all_tracked, map_validated`; sidecar
`wiser_sidecar/1`; manifest columns `image … overlap`; package layout incl. `overlap/` (20 of the 400, 10 per camera,
random seed 0). Implementation choices fixed now:

1. **Test extension spacing 5 min** (per camera, from each other and from that camera's existing 20): 50 frames at 10 min
   need 490 min > the 440-min night. Same rule otherwise (`select_pano_targets.draw`, zero / few / many 0.2 / 0.4 / 0.4,
   c3_bins5), seeds 1000 (CH01) / 1001 (CH02).
2. **No kit table for night 09-05** (no model may run on its frames → no validation; no WISER pixels written for it).
   Kit nights = 08-30 … 09-10 minus 09-05 (11); handling windows ± 5 min have no rows; booleans 0/1.
3. **Validation statistic** (A2) per camera-night from that camera-night's pool frames: v5 boxes conf ≥ 0.5 →
   `Corrections.to_paddock` (z = 60 mm); WISER animals outside the house zones at the frame time (L = 0) through the
   accepted map. *Median distance* = median matched residual of the per-frame Hungarian assignment (gate 30 in, the
   phase-0 test statistic); *within-14 share* = share of all mapped boxes with an outside animal within 14 in;
   control = WISER + 3 600 s with the same map (no refit). Pass iff median ≤ 14 in AND share ≥ 2 × control share;
   ≥ 20 mapped boxes and ≥ 10 pairs, else "insufficient data" (= not validated). No fixed-spot exclusion.
4. **Motion** = head-IMU state where its QC passes (1 still / 2 active / 3 locomoting), else the default track's speed at
   the nearer fix (< 2 in/s still, 2–10 active, ≥ 10 locomoting); untracked = unknown.
5. **Pool strata**: n_out = tagged animals tracked and outside the house zones (0 / 1–2 / ≥ 3), motion = the most active
   state among them ("none" when 0) → 7 strata; 1 200 frames drawn equally over the strata (a stratum short of
   candidates hands its shortfall to the others, round-robin), within a stratum round-robin over its (night, clock hour)
   cells in random order; + 300 uniform; ≥ 10 s apart per camera; seconds without video excluded; seeds 0 (CH01) and
   1 (CH02).
6. **Rain nights** (no suspected-miss quota) = rain ≥ 1 mm 21:00–04:20 in the correction table (AWN): 08-31, 09-03, 09-09.
7. **Pixel radius** r_px = 14 √|det J| (J = ∂ cohort px / ∂ paddock in): the area-equivalent radius of the 14-in ring's
   image. **Robust hidden share 0** (B3a) = the camera's visibility mask (2-in cells) is 0 at the nominal position and at
   the 8 positions 7 in away (clamped 1 in inside the paddock) — the occlusion-v2 rule; the mask ships in the kit.
   CH02's scene = CH01's v2 scene seen from CH02, with CH02's own 09-18 L/R labels (A0, A4, B0–B4) as label planes
   (`ch01_occlusion.build_scene(cam=…)`; CH01 unchanged).
8. **Scores (B3)** use the paddock geometry: a box is within 20 in when its centre maps (`to_paddock`) within 20 in, or —
   if it maps outside the support — when its pixel is within 20/14 · r_px of the animal's pixel; social = two animals
   tracked, in support, outside the house zones within 20 in. Only map-validated camera-nights; misses not on rain nights.
9. **Merged event** (one frame per event): per animal, the runs of kit seconds in which it is tracked, outside the house
   zones, in support and robustly unhidden (gaps ≤ 5 s bridged); a frame's miss animals join their runs (union).
10. **Quota fill order**: visible suspected miss → social → hard negative → WISER strata (+ the shortfalls of the first
    three) → DINOv3 diversity → uniform random. Misses and social in random order (seed); hard negatives by v5 max conf
    descending (frames where v5 fires though WISER puts all six animals in the houses). WISER strata over all 11 nights
    (they use WISER counts in the WISER frame, not the map): round-robin over the 7 strata, each time the frame whose
    (night, hour) cell is least represented. DINOv3 diversity: k-means k = 20 (seed 0) on PCA-50 + L2 embeddings of the
    camera's pool, the nearest eligible frame to each centroid. ≤ 25 frames per camera-night, ≥ 10 s apart.
11. **DINOv3**: `field_embed`'s DINOv3 ViT-B/16 CLS token on the whole upright frame resized aspect-preserving to
    1024 × 288 (multiples of 16), not field_embed's square 224 resize (a 3.6:1 panorama squashed to a square).
12. **Frame index** in `<video stem>_f<frame>.png` = 0-based index of the video sample in the hourly file, read from the
    fragmented-MP4 index (= ffprobe packet order; PTS monotone, no B-frames); the grab is grab_frames.py's command plus
    the integer PTS from showinfo (its `pts_time` has only 6 significant digits). Existing test frames keep their names;
    their manifest `frame` is derived from their grab manifest (first sample ≥ the seek offset), empty if inconsistent.
13. **SF12 on night 08-30**: its second tag (`SF12_tag12376`) is used where the main tag has no fix.
14. **Kit pixels**: u, v are given whenever the inverse converges inside the frame; `in_support` says whether the
    camera's verified calibration covers it. Occluder outlines = convex hulls of the user's edge labels (house_1 from the
    09-04 noon labels through the inverse noon affine), unlabelled poles = projected 2.4-m capsule (in-frame points;
    dropped if wider than 1 500 px, i.e. wrapped around the panorama), carried into each night by the night's median
    correction and clipped to the frame.

## Amendment 2 (2026-10-06, **before results**: no package existed yet; the coordinator's correction of the shared format)

In `train/images/` and `overlap/images/` the editable `<stem>.txt` is written **only when v5 has ≥ 1 box at conf ≥ 0.25**;
no `.txt` when v5 found nothing. Reason: the undergrad's workflow (`WORKFLOW.md` in social-field-rat) leaves model-empty
frames unlabelled — `check_labels.py` counts a frame as reviewed when its `.txt` exists and `finalize_negatives.py` writes
the empties only after the human pass, so an empty `.txt` at packaging time would turn a never-opened frame into a
confirmed negative. `train/prelabels_v5/<stem>.txt` is unchanged: always written, empty when v5 found nothing (the
pristine provenance record). The package README says: frames with no `.txt` are the ones the model found nothing in —
open them, and press `s` even when they are empty. Part C aligns `select_round.py` to the same rule. Wording (the
coordinator, relaying part C's cross-check, same evening, still before any package): a frame is **reviewed only when its
`<stem>.prov.json` exists** (saved with `label_frames.py --wiser`; a frame with prelabel boxes has a `.txt` before anyone
looked at it); `finalize_negatives` only after `progress.py <pkg>` reports "train READY" (0 never-saved frames) — in the
package README and the report.

## Amendment 3 (2026-10-06, **before results**: after the pool grab, before the kit validation and the selection)

The pool grab lands on the first frame at or after each target second. In one CH02 hour (09-04 04:00, a video with
missing frames) and two other CH02 targets of 09-04, 7 of the 3 000 frames lie 0.69–15.2 s after their target second
(two targets share one frame). A pool frame is used for the validation (A2) and the selection (B3–B4) only if its frame
time is ≤ 0.5 s after the target second (the WISER row of that second then describes it), one row per image; the others
stay in the pool, unused. (Median frame − target 0.029 s.)

## Amendment 4 (2026-10-06, **after results**: after the first package build, before anyone used it)

The test extension drew 29 instead of 30 frames per camera: `select_pano_targets.draw` does not refill a stratum that
runs out of spaced bins, and night 09-05 has only 319 'zero' bins (27 min), too few for 6 more frames ≥ 5 min from each
other and from the 4 existing 'zero' frames of each camera. The plan fixes 30 per camera, so the shortfall is drawn from
the strata that still have candidates (mix renormalised, same 5-min spacing, the same seeded rng stream continued). The
first package (`label_round1_20261006_2003`, 98 test frames) was deleted unused and rebuilt by the same code; the training
selection is deterministic and unchanged. Nothing about the shortfall depends on an image or a score.

## Part C result (coordinator, 2026-10-06)

Part C DONE 2026-10-06 in `D:/Documents/GitHub/social-field-rat-wiser-loop` (import `56840d9` on main; branch `wiser-loop` b3f380f..07c6c9d, local, not pushed; patches in `patches_wiser-loop/`): `label_frames.py --wiser/--test/--labeller` (blind first, overlay after `d`, per-box provenance), `wiser_loop/` select_round / eval_test / progress (READY gate) / paths profiles / slurm; self-test 110/110; integration test on the real round-1 package, kit and pool passed (420 sidecars parse, progress gate, test guard; the port's selection shares 137 / 400 frames with round 1 because the kit carries no paddock position or robust hidden share — an exact port needs those columns).
