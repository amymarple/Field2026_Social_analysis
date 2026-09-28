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

**Update after the flipbooks (user, 2026-09-28):**
- **Every camera shows small shifts across days** — one calibration per cohort cannot be assumed; a per-day (or finer)
  correction will be needed.
- The 09-18 reference looked geometrically different (a house "stretched"). The user checked
  `CH02_2026-09-18_15-00-01_to_15-49-36.mp4`, which holds colour and IR footage, and saw **no colour-vs-IR distortion**,
  and asked whether the extracted frames had been altered. Verified numerically: all files share one geometry
  (CH01/CH02 stored 2160×7680, CH03/CH04 4512×2512, no SAR, no rotation metadata); saved frames equal a pure 90° CCW
  rotation of the raw decode (panos) or the raw decode (CH03/CH04) to JPEG precision (corr 0.9988–0.9998, mean
  |Δ| 0.8–2.7 grey levels). By mean HSV saturation, **the cohort footage is all IR** (as the user states) and only the
  09-18 reference was colour — so the review had compared a colour calibration frame with IR cohort frames. The
  remaining difference therefore reflects a change between cohort 3 and 09-18 (camera pose, pano stitching, or the
  objects themselves), not the extraction and not the colour/IR mode.
- `camera_review.py` now also saves an **IR reference from the same 09-18 session** (`REFIR`, nearest the label clock
  by saturation: CH01 13:57:30, CH02 15:22:30, CH03 15:45:00, CH04 14:32:30) and blinks / opens the flipbooks with it;
  `--ir-ref <run_dir>` adds it to an existing run. Houses are not usable as references (appearance changes).
- Proposed next (user's idea): a landmark-based correction from **rigid structures** — pole outlines, the wall TOP edge
  (the foot is hidden by grass), the PC box facing CH02, the water-tower outline — labelled by the user on a few
  reference frames and tracked per day by patch matching within the same (IR) mode.

**Final verdict (user, after the IR-reference flipbooks, 2026-09-28):** the differences between the cohort frames and
the 09-18 reference are **neither colour/IR nor camera movement** — the central pole barely moves across the whole
series. So CH01–CH04 are treated as **not moved** between cohort 3 and the 09-18 calibration (the 09-24 calibration
applies to cohort-3 footage at its stated precision); what does change is in the scene itself (e.g. a house's
apparent shape/size). Consequence to keep in mind: positions of movable objects (houses) measured on 09-18 frames must
not be assumed for cohort 3. The flipbooks now show the reference at the start and the end. The rigid-landmark
correction is on hold unless a later need appears.

## 3. `cv` env on the new GPU

The analysis PC now has an RTX 5070 Ti (sm_120). The env's `torch 2.13.0+cu126` reported `cuda.is_available() == True`
but had no sm_120 kernels ("no kernel image"). Reinstalled `torch==2.13.0+cu130`, `torchvision==0.28.0+cu130`
(`--force-reinstall --no-deps`, exact `+cu130` pins — torch 2.13 has no cu128/cu129 wheel, and pip treats `+cu126` as
satisfying `==2.13.0`); installed the declared `sahi` (0.12.7, + `fire`; no OpenCV/torch change). Verified: GPU matmul,
ultralytics GPU inference with `rat_field_div3`, and a 1-epoch GPU training smoke run (AMP checks pass).
`cv/environment.yml`, `cv/requirements.txt`, `cv/cv_field/HANDOFF.md` and `CLAUDE.md` document the install.
