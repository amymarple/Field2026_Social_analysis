# Cohort-3 camera stability: automatic check rejected, human review tool + flipbooks; GPU env fixed (2026-09-28)

Plan: [implementation_plan/2026-09-28-cohort3-camera-stability.md](../implementation_plan/2026-09-28-cohort3-camera-stability.md).
Context: cohort-3 (2026c) CV starts with the CH01/CH02 panoramas (user decision — they map ~68–69 % of the paddock each
in the 09-24 calibration; CH03/CH04 ~12 % each). Before any detection is mapped to paddock coordinates we need to know
whether the cameras moved between cohort 3 (08-30 → 09-12) and the 09-18/19 calibration.

## 1. Automatic check — tried and rejected

ECC registration (Euclidean: dx, dy, rotation) of CLAHE'd gradient-magnitude images inside a ±60 px band around the
wall-foot lines labelled on the 09-18 calibration frame (recording repo `calibration_qc/session_2026-09-18_line_labels_CH0x.json`);
day frames vs the 09-18 reference, nights (03:00) vs the first cohort night; status "moved" if the labelled wall points
moved > 5 px, "unreliable" if cc < 0.4 or the per-wall-line estimates disagreed by > 5 px.

- Synthetic self-test: known displacements 0 / 10.7 / 19.1 px recovered to < 0.02 px.
- Same-session 60-s controls on real footage: 0.0–0.3 px, cc 0.97–0.99 on all four cameras.
- **Every cross-day comparison was unreliable**: cc 0.14–0.65, apparent displacements 2–83 px, per-line shifts
  inconsistent (e.g. CH04 nights: `WALL_Y0` +22 px in y while the other two lines ~0). Cause: half the band is ground —
  grass growth, rain/wet vegetation and the IR/colour mode change dominate it. A frame-boundary bug also dropped some
  03:00:00 samples (segments start 1 s after the previous one ends).
- User decision: such a check cannot be made reliable ("草肯定会长…下雨也会导致偏差"); cameras are judged by eye and
  weather-driven moves reported manually as QC. The ECC script and its report were deleted (never committed); the
  numbers above are the record.

## 2. Human review tool

New `cv/cv_field/camera_review.py` (+ `--selftest`: segment lookup incl. the 1-s gap and unrenamed files probed with
ffprobe, line drawing). For each camera and day it grabs frames at 03:01 / 12:00 / 21:30 (field-PC time) from the local
copy `F:\3rd_rat\`, overlays the 09-18 wall-foot lines, and writes one HTML page per camera (09-18 reference on top, one
row per day, click to blink against the reference, full-res linked) plus a **flipbook MP4** per camera (reference first,
then chronological, 2 fps, timestamp burnt in; `--flipbook <run_dir>` rebuilds videos without decoding). It makes no
judgement.

Run 2026-09-28: CH01–CH04, 08-30 → 09-17, 42 frames per camera + reference →
`D:\Field2026_analysis_out\2026c\cv_field_camera_review_20260928_1551\` (`index.html`, `CH0x.html`,
`CH0x_flipbook.mp4`). CPU seek-decode from F: ran ~6 s/frame for the 7680×2160 panos; the user decided that frame
extraction will use GPU decode (NVDEC) from now on (not yet implemented).

**Verdict:** user's first look at the CH01/CH02 pages — "我觉得是没动" (no move). Final per-camera verdict pending the
flipbooks; to be recorded as stable periods per camera for the paddock-mapping code.

## 3. `cv` env on the new GPU

The analysis PC now has an RTX 5070 Ti (sm_120). The env's `torch 2.13.0+cu126` reported `cuda.is_available() == True`
but had no sm_120 kernels ("no kernel image"). Reinstalled `torch==2.13.0+cu130`, `torchvision==0.28.0+cu130`
(`--force-reinstall --no-deps`, exact `+cu130` pins — torch 2.13 has no cu128/cu129 wheel, and pip treats `+cu126` as
satisfying `==2.13.0`); installed the declared `sahi` (0.12.7, + `fire`; no OpenCV/torch change). Verified: GPU matmul,
ultralytics GPU inference with `rat_field_div3`, and a 1-epoch GPU training smoke run (AMP checks pass).
`cv/environment.yml`, `cv/requirements.txt`, `cv/cv_field/HANDOFF.md` and `CLAUDE.md` document the install.
