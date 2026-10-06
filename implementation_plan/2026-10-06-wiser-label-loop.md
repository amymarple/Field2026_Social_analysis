# WISER-guided labelling loop for the CH01/CH02 rat detector (round 1 + the loop in the undergrad's repo)

Date: 2026-10-06. Status: **PLANNED** — design answers from the user 2026-10-06 (new clone + branch of the undergrad's
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
