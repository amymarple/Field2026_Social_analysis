# Cohort-3 CH01/CH02 panorama detector — pilot (2026-09-28)

**Status.** Step 1 in progress (user go, 2026-09-28: "抽帧工具先建立起来"; WISER-guided selection approved as the design).

**Why.** For cohort 3 (2026c) the user put the two Reolink Duo 3 panoramas first: in the 09-24 calibration they map
~68–69 % of the paddock each (CH03/CH04 ~12 % each), so they carry the occupancy map. The existing detector and all 255
labels are cohort-1 CH03/CH04, so CH01/CH02 start from zero. Rules (user): local first — GPU-decode frames from the
local copy `F:\3rd_rat\`, keep them local, label locally, small pilot; BioHPC only for large batches later; the agent
never judges images and confirms every test plan first.

**Scale.** From the 09-24 calibration geometry, a rat (20 × 8 cm, 8 cm high) spans ~70–160 px (median ~95) in the
native upright panorama (7680 × 2160). Whole pano → 1280 wide (the CH03/CH04 default) leaves 11–16 px — too small;
→ 2560 wide 23–32 px; half pano (3840) → 1920 34–48 px. Labels are made on native frames (YOLO boxes are normalised),
so the input-size choice is tested after labelling at no labelling cost.

**Steps.**
1. **Frame extraction tool** `cv/cv_field/grab_frames.py`: keyframe snap (the panos have a keyframe every ~2 s; a
   seek otherwise decodes up to ~40 full frames) + NVDEC GPU decode (`-hwaccel cuda`), CPU fallback; handles
   never-renamed segments (duration probed) and nights that span two date folders; native upright JPEGs + a manifest
   (target vs actual frame time). Offline `--selftest` on a synthetic HEVC clip; `--benchmark` on F: (20 random night
   times per camera: CPU exact / CPU key / GPU key / GPU exact, s/frame and GPU-vs-CPU pixel agreement — numbers only).
2. **Candidate pool, WISER-guided:** cohort nights 21:00–04:20 (scope to confirm with the user), one whole night held
   out as the frozen test night; per candidate time the number of WISER tags outside the houses (0 / 1–2 / ≥ 3) from the
   local WISER copies; stratified over nights × hours × that count. WISER gives presence/count only, never boxes (the
   CH01/CH02 pixel↔paddock correction is being worked out separately). Frames → `cv/dataset/rat_pano/pool/` (local,
   gitignored), separate from the cohort-1 `rat_field` set.
3. **Labelling (user):** ~30 frames per camera for round 0 (+ ~20 per camera on the test night), `label_frames.py` on
   native frames, same rules as cv_field (clear rats only, skip ambiguous / people frames).
4. **Training comparison (separate plan to the user):** whole pano @ 2560 vs half pano @ 1920; COCO yolo11s vs div3
   init; centre-matched evaluation on the test night, false positives reviewed by the user.

**Outputs.** Code in `cv/cv_field/`; frames + labels local under `cv/dataset/rat_pano*`; benchmark and selection reports
under `results/2026c/cv_field/reports/`, bulk under `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/`.
