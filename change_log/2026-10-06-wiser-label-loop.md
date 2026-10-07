# 2026-10-06 — WISER-guided labelling loop, round 1: WISER pixel kit (A) + 400-frame package and test set to 100 (B)

Plan: [`implementation_plan/2026-10-06-wiser-label-loop.md`](../implementation_plan/2026-10-06-wiser-label-loop.md)
(pre-registered; approved "做吧" 2026-10-06; amendments 1–3 before results, 4 after the first package build). Report:
[`results/2026c/cv_field/reports/cv_field_wiser_label_loop_round1_2026c.md`](../results/2026c/cv_field/reports/cv_field_wiser_label_loop_round1_2026c.md)
(+ pointer `run_manifest_wiser_label_loop_round1_2026c.json`). Data map: [`cv/cv_field/DATA_MAP_c1yolo_wiser.md`](../cv/cv_field/DATA_MAP_c1yolo_wiser.md),
section I. Part C (the loop code in the undergrad's repo clone `social-field-rat-wiser-loop`, branch `wiser-loop`) was
built in parallel by another agent against the shared formats and is **pending** here. The agent looked at no frame,
video or figure.

## What was built

- **`cv/cv_field/build_wiser_pixel_kit.py`** (`--selftest` 12 checks, `--build --pool`): per camera (CH01, CH02) and
  night (08-30 … 09-10 except the frozen test night 09-05) a 1-Hz table `t_pc, animal, tracked, in_house, u, v, r_px,
  hidden_share, in_support, motion, all_tracked, map_validated` (WISER default track → accepted phase-0 map → rev g
  calibration inverse at z = 60 mm → the night's frame correction, interpolated per second exactly as
  `Corrections.correction`; round trip through `Corrections.to_paddock` < 1e-12 in), `support.json` and `occluders.json`
  by night (label hulls; house_1 from its 09-04 cohort labels), `visibility_mask.npz`, `checks.csv`; `kit.json` (versions,
  commits, map, sha256 of every input, validation table), README, `MANIFEST_sha256.csv` + `verify_manifest.py`.
- **`cv/cv_field/select_label_round1.py`** (`--selftest` 16 checks): `--pool` (draw, grab, v5, DINOv3; resumable),
  `--select` (scores, quotas, test extension, package, report). New pieces: a fragmented-MP4 sample-table reader (frame
  index without decoding; = ffprobe), the grab_frames command returning the integer PTS (showinfo's `pts_time` has 6
  significant digits), thread-safe video-index cache.
- **`cv/cv_field/ch01_occlusion.py`**: `build_scene(cam=…)` — the v2 scene seen from CH02 with CH02's own 09-18 L/R labels
  (A0, A4, B0–B4) as label planes; CH01 unchanged (the kit's CH01 mask equals the v2 run's on all 18 976 support cells).

## Results

- **Pool** `D:/Field2026_analysis_out/2026c/label_round1_pool_20261006_1840/`: 3 000 frames (1 500 per camera: 1 200
  WISER-stratified, ~171 per stratum, + 300 uniform), 0 failures, 2 993 usable (7 CH02 09-04 frames landed 0.7–15 s after
  their target second, amendment 3); 22 858 v5 boxes ≥ 0.05; identity check vs `grab_frames.grab` 0 px; wall time 71 min.
- **Kit** `D:/Field2026_analysis_out/2026c/wiser_pixel_kit_20261006_1952/` (32 MB): **19 of 22 camera-nights validated**;
  failing CH01 09-01 (median 18.0 in), CH02 09-01 (18.0 in), CH02 09-02 (15.5 in) — all before the 09-03 13:59 WISER
  restart (frame shifted 7–18 in); passing medians 3.6–13.7 in, within-14 share 0.22–0.77 vs control 0.00–0.05.
- **Package** `D:/Field2026_analysis_out/2026c/label_round1_20261006_2015/` (9.2 GB, 1 776 files, `verify_manifest.py` OK):
  400 train frames (per camera: visible suspected miss 60/60, social 30/30, hard negative 20/20, WISER strata 50/50,
  DINOv3 diversity 20/20, uniform random 20/20; candidates CH01 227 / 131 / 85, CH02 196 / 120 / 65), editable v5 `.txt`
  on 391 (none where v5 found nothing, amendment 2), pristine `prelabels_v5/` for all 400, 400 sidecars (356 map-validated);
  ≤ 25 per camera-night; **test 100** (40 existing `.jpg` unchanged + 60 new on 09-05, ≥ 5 min apart; no model, prelabel or
  sidecar); 20 overlap frames (10 per camera, seed 0). Clip-review export absent at selection time → miss quota 60, no
  fixed-spot negatives.

## Amendments

1 (before results) implementation details + the 5-min test spacing (10 min cannot fit 50 per camera in 7.3 h); 2 (before
results, the coordinator) editable `.txt` only where v5 has a box, `prelabels_v5` always, README wording "reviewed only
when `<stem>.prov.json` exists"; 3 (before results) pool frames > 0.5 s after their target second unused; 4 (after the
first package build) the test-extension refill (09-05 has 27 min of 'zero' bins; the rule drew 29 per camera) — the first
package `label_round1_20261006_2003` was deleted unused and rebuilt; its training manifest is identical to the rebuild's.

## Not verified

Grass occlusion is not modelled; the suspected-miss and social scores are proposals for the labeller, not measurements;
the map is validated per camera-night on v5 boxes (which include false positives) and on one similarity fitted on 09-06;
the CH02 occlusion scene has no independent pole check beyond its own label-plane residuals (0.8–7.1 px) and house_2
(11.2 px). Part C has not been run against this kit here.

## Files

New: `cv/cv_field/build_wiser_pixel_kit.py`, `cv/cv_field/select_label_round1.py`, this file, the report + pointer.
Edited: `cv/cv_field/ch01_occlusion.py` (`build_scene(cam=…)`), the plan (status, amendments 1–4), both index READMEs,
`CLAUDE.md` (cv_field map), `cv/cv_field/HANDOFF.md`, `cv/cv_field/DATA_MAP_c1yolo_wiser.md` (section I).
