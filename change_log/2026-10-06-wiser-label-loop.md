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

## Addendum — part C (coordinator, 2026-10-06)

Part C DONE 2026-10-06 in `D:/Documents/GitHub/social-field-rat-wiser-loop` (import `56840d9` on main; branch `wiser-loop` b3f380f..07c6c9d, local, not pushed; patches in `patches_wiser-loop/`): `label_frames.py --wiser/--test/--labeller` (blind first, overlay after `d`, per-box provenance), `wiser_loop/` select_round / eval_test / progress (READY gate) / paths profiles / slurm; self-test 110/110; integration test on the real round-1 package, kit and pool passed (420 sidecars parse, progress gate, test guard; the port's selection shares 137 / 400 frames with round 1 because the kit carries no paddock position or robust hidden share — an exact port needs those columns). Format fix agreed by both sides before the package was built: the editable `.txt` exists only where the model has a box; a frame counts as reviewed only when its `.prov.json` exists.

## Addendum — the undergrad's portable drive (2026-10-07)

User request (2026-10-07): put everything the undergrad needs on the external SSD `H:` (SanDisk Extreme V3, 2 TB,
exFAT), usable on any computer under any drive letter, with an English instruction. Everything is in
`H:/wiser_label_loop/` (her `H:/social-field/` untouched); masters stay on D: / F: (layout and sources:
`cv/cv_field/DATA_MAP_c1yolo_wiser.md` section J).

- **History.** Her bundle `H:/social-field/social-field-rat-backup-20260914.bundle` verifies (complete history); `main` =
  `8691697` (her `origin/main` `3e46520` is its ancestor, 3 local commits behind). Its tree equals the import commit on 36
  of the 38 imported files, including every file part C changes; the two others are explained (the import's own
  `.gitignore` written because her working copy had none, and her untracked `verify_copy.py` of 09-14 20:24, after the
  20:14 bundle). The six part-C commits were cherry-picked onto `8691697` without conflict (new hashes 4dc635e 9b766bb
  0735555 586dbe6 ceb876e 4b73a21); the resulting tree differs from the old branch only in those of her own files. Then on
  `wiser-loop`: a10e40c (portable `drive` profile), 750dd02 (`--select-only` never grabs), 33ba6c3 (`os.path.abspath`
  instead of `resolve()`), 1ce4db4 (BioHPC facts, ffmpeg only when grabbing). The drive repo (`repo/social-field-rat`,
  no remote) and `D:/Documents/GitHub/social-field-rat-wiser-loop` hold the same `wiser-loop` (tip 1ce4db4); the local
  repo keeps the old branches as `old/import-main`, `old/wiser-loop-on-import`. Not pushed.
- **Portable paths.** Profile `drive` (relative paths) is the default when the scripts find the marker file
  `WISER_LOOP_ROOT` above themselves (env `WISER_LOOP_ROOT` overrides, `WISER_LOOP_PROFILE=none` disables). No code
  path of the loop opens D:, F:, C:/Users or Q:; absolute paths left on the drive are provenance (`kit.json`, v5
  `args.yaml`, the package README), docs / examples, the `windows` / `biohpc` profiles, or her non-loop tools
  (napari labelling scripts, notebooks).
- **Copied** (one stream per file with sha256 of the source bytes; 6 parallel writers because the drive took only
  ~40 MB/s per stream on this PC): package 1 777 files / 9.79 GB, kit 36 / 0.03 GB, pool 6 199 / 59.97 GB, cohort-1 data
  5 301 / 50.97 GB, models 8 / 0.15 GB, video 186 / 243.53 GB (kit nights only, nothing overlapping 09-05 21:00 →
  09-06 04:20) — 13 507 files, 364 436 144 961 bytes, 0 errors, 2 h 20 min.
- **Verified.** Destination sizes 13 507 / 13 507; package and kit pass their own `verify_manifest.py` on the drive;
  cohort-1 data + models equal the backup's manifest (5 309 / 5 309); `MANIFEST_sha256.csv` (13 718 files, written
  16:05:50) + `tools/verify_drive.py` (`--quick` OK). Full read-back of the drive against the manifest: NOT COMPLETED -- the drive was unplugged for the hand-over at ~16:50 while `verify_drive.py` (6 readers, ~44 MB/s) had read ~100 of 364 GB; the run aborted (I/O error) before its end-of-run report, so it gives no result. What stands: copy-time source hashes, all sizes, the package / kit verify scripts and the backup manifest comparison. To finish it: `python tools/verify_drive.py` on the drive (hours; `--only <folder>` for parts).
- **Portability test** (`subst K:` of the drive folder, loop env vars cleared, Python under an audit hook; outputs on C:):
  verify --quick, self-test 113/113 (`--gui`) and 99/99 (base Python), kit reader (22 camera-nights, 1 722 600 rows per
  camera), `select_round.py --select-only` (drive pool + video; 400 frames, none from round 1), one real grab from the
  drive's video, `load_frame` on 3 frames, `progress.py` NOT READY → READY on a 5-frame copy, `eval_test.py` on
  synthetic data: all pass; no D:/F:/Q: access. Found and left as is (the drive was frozen for hand-over):
  `tools/verify_drive.py` uses `Path.resolve()`, so under a subst it reads through the target letter (harmless).
- **Instruction**: `H:/wiser_label_loop/START_HERE.md` (+ `.html`): folder map and drive check, setup (two conda envs,
  exact-CUDA PyTorch, `git config safe.directory` for exFAT, fetching `wiser-loop` into her own clone), labelling round 1
  (train, overlap by a second person, test with `--test`; keys; blind first; what to box), the `progress.py` READY gate,
  dataset (`SOURCES.txt` + round-1 train; never test / overlap), training locally from v5 and BioHPC later
  (`cbsuruiz01`, module python/3.12.7 + venv + cu128, `/workdir`, copy results back), evaluation, the next round,
  tracking files, a do-not list, provenance.
- **Notes for whoever uses the drive.** USB throughput on the analysis PC was ~40 MB/s per stream (USB 2 port or link?):
  train from a local copy. Windows' 260-character path limit bites in deep folders (two scratch tests here); the drive's
  own paths are well below it.
