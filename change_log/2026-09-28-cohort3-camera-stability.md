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

**Verdict (user, after the IR-reference flipbooks, 2026-09-28; supersedes an earlier "not moved" reading):**
- The differences are **not colour/IR** — the reference and the cohort frames are both IR.
- **CH01/CH02 (Duo 3 panoramas): a large image DISTORTION change** between cohort 3 and the 09-18 calibration — a
  house's size in the image clearly differs — while the central pole barely moves (so it is not a simple camera
  move). The user does not attribute it to reboots (the machines were certainly rebooted mid-recording); the event
  timeline is being checked against the records.
- **CH03/CH04: no distortion change, but larger day-to-day image motion than CH01/CH02.**
- **Consequence:** the calibration anchors were established after the cohort (09-18/19), so cohort-3 pixels cannot be
  mapped to paddock coordinates with the 09-24 calibration as is. A correction from cohort-epoch pixels to
  calibration-epoch pixels is needed — per epoch for the CH01/CH02 distortion, per day (or finer) for the CH03/CH04
  motion — from rigid structures that do not move over days (user's proposal). Plan to follow.
- The flipbooks show the reference at the start and the end.

**Resolved (user, 2026-10-01, from the CH05/CH06 pairs and flipbooks — runs `cv_field_camera_events_20261001_1243`,
`cv_field_camera_review_20261001_1250`, config `cv/configs/cohort3_house_check_events.json`):** **house1 was moved —
it now stands farther from its pole; house7 never moved; the houses did not move while the rats were in the field.**
Names (user): house1 = HOUSE_1 = lab `house_1` = **roof number 4** (by pole B1, under CH05); house2 = HOUSE_2 = lab
`house_2` = **roof number 7** (by pole B3, under CH06) — the 09-18/19 calibration sheets' "house 4" / "house 7".
**house1 (roof 4) was moved on 09-18**, the calibration day, so the calibration frames show it in its new place. The CH01/CH02 "distortion" (a house's size
differs) is most likely this move, not a lens/stitching change → CH01/CH02 may need only a small displacement correction.
To be confirmed with the rigid landmarks (poles, pole boxes = WISER anchors, wall tops, towers): if one small rigid
correction aligns them between cohort and 09-18 with small residuals, there is no distortion. House landmarks: the
unmoved house may enter the cohort→calibration fit; house1 only within 08-31→09-17. Anything measured on post-09-17
imagery about house1 (e.g. its centre in `cv/configs/field_layout.json`) does not hold for cohort 3.

**Event timeline and event-pair review.** The records (field2026-sync incident log, recording repo, file names,
weather) show no Duo 3 settings/firmware/mount change and no house move logged; one NVR reboot during the cohort
(09-06 ~13:00→14:04:44, all NVR channels, not in the incident log); PC blue screens 09-01 04:19:56 and 09-03 13:56
(PC-side only); 08-31 ~11:52→19:01 unlogged troubleshooting; 26 h unrecorded 09-17 12:01→09-18 13:54 during which the
image mode was switched (cohort footage all IR even at noon; colour again on 09-18); storm 09-02 21:05–21:25; heavy rain
09-03 23:25–23:45. **CH01/CH02 drop their stream in dawn/dusk clusters** (1–3-min pieces ~4 min apart for ~20 min,
e.g. CH01 09-03 18:45:23→19:07:48, CH02 09-12 06:01:44→06:06:16). `camera_review.py --events` (config
`cv/configs/cohort3_camera_events.json`) extracted IR before/after pairs around each candidate (run
`cv_field_camera_events_20260928_1934`: per-camera pages + MP4s) for the user to date the changes.
New `cv/cv_field/landmark_gui.py` (adapted from the recording repo's `line_gui.py`) for the rigid-landmark labels;
labels go to `cv/configs/landmarks/2026c/`.

## 3. `cv` env on the new GPU

The analysis PC now has an RTX 5070 Ti (sm_120). The env's `torch 2.13.0+cu126` reported `cuda.is_available() == True`
but had no sm_120 kernels ("no kernel image"). Reinstalled `torch==2.13.0+cu130`, `torchvision==0.28.0+cu130`
(`--force-reinstall --no-deps`, exact `+cu130` pins — torch 2.13 has no cu128/cu129 wheel, and pip treats `+cu126` as
satisfying `==2.13.0`); installed the declared `sahi` (0.12.7, + `fire`; no OpenCV/torch change). Verified: GPU matmul,
ultralytics GPU inference with `rat_field_div3`, and a 1-epoch GPU training smoke run (AMP checks pass).
`cv/environment.yml`, `cv/requirements.txt`, `cv/cv_field/HANDOFF.md` and `CLAUDE.md` document the install.

**Automatic landmark tracking (2026-10-01, `cv/cv_field/landmark_track.py`, run `cv_field_landmark_track_20261001_1441`,
report `results/2026c/cv_field/reports/cv_field_landmark_track_2026c.md`).** The user's 09-18 labels were tracked into
raw daily frames (03:01 / 12:00 / 21:30, 08-30→09-17; 42 frames per camera) by coarse-to-fine NCC on gradient magnitude
(coarse ~120-px patches at half resolution → affine A0; fine ±8 px around A0 so a point cannot jump to a parallel
edge — found by the synthetic self-test) and a Huber affine per frame on the fit set; leave-one-landmark-out error only
where the rest still constrains both directions. Reference self-check: ~0 shift, 0.2 px on all four cameras.
- **Daytime works:** CH01 12:00 14/14 ok, held-out median 1.35 px; CH02 12/14 ok, 1.0 px. Day-ok CH01/CH02 fits have
  **scale 0.999–1.001 and rotation < 0.5°**, translations CH01 −11..+19 / −2..+7 px, CH02 −3..+30 / −2..+1 px, and the
  unmoved house_2 (validation only) agrees at 2.3 / 1.2 px → **no CH01/CH02 distortion; a small per-day shift.** The
  shift varies from day to day (e.g. CH02 +30 px on 09-01, −3 px on 09-05) → per-day correction needed.
- **Night fails** (03:01, 21:30: ≤ 2 of 14 ok per camera; half the landmarks unmatched) — the 09-18 reference is
  daytime and the IR illuminator changes appearance. Proposed: the user labels one night frame per camera; night frames
  are tracked against it, and that frame is tied to 09-18 geometrically through the two label sets.
- **CH03/CH04** have too few landmarks (CH04: two poles + two wall tops): 4–6 of 14 day frames ok; more fixed structures
  would help.

**Occlusion tiers, extra wall landmarks, automatic night reference (2026-10-01, plan revision 3; tests agreed with the
user).** The user added CH03/CH04 wall landmarks on the 09-18 references (`NAILS` points; `PATCHES`/`PATCH_*`;
`SEAMS`/`SEAM_*`; CH04 `BUILDING`, later `WOOD`) and noted their reliability (nails very stable; patches low on the
wall, a rat can hide one; people can stand in front of the building). `landmark_track.py` now fits a stable tier first
and admits each occludable piece only if it matches (≥ 60 % of samples, median residual ≤ 3 px under the stable fit);
new `cv/cv_field/landmark_night.py` makes a night reference by a dusk hand-off and checks it by dawn closure. The
previous daytime report is archived (`archive/2026c/cv_field/reports/cv_field_landmark_track_2026c_run20261001_1441.md`).
- **Daytime, 12:00 daily 08-31→09-17 (run `cv_field_landmark_track_20261001_1624`; 14 frames per camera, no 12:00 video
  on 08-30 and 09-12→09-15):** CH01 14/14 ok (held-out median 1.35 px, house_2 validation 2.3 px), CH02 12/14 (09-02 and
  09-03 miss only on p90 6.9 / 7.1 px; house_2 1.5 px) — unchanged. **CH03 5/14, CH04 2/14** even with the new landmarks;
  their fits report shifts up to 55 px (CH03) and 190 px / 7.4° / scale 0.93–1.05 (CH04), beyond the coarse search
  (±120 px) — tracking failures or real moves, for the user to judge on the overlays. Patches are dropped in most CH03
  frames (residual 3–24 px); the building matches only on 09-17. Hypotheses (unverified): moves larger than the search
  window; wide-angle lens → an affine is the wrong model near the image edges.
- **Night 09-03 → 09-04 (run `cv_field_landmark_night_20261001_1627`, report
  `results/2026c/cv_field/reports/cv_field_landmark_night_2026c.md`): CH02 PASS** — dawn closure median 1.42 / max
  3.51 px, the three night frames ok (held-out 0.35–1.54 px), shift vs 09-18 +2 → +18 px over the night. **CH01, CH03,
  CH04 FAIL** (CH01: night frames do not fit at all; CH03 / CH04 closure 92 / 54 px). Cause found in the brightness
  series (numbers, not images): the "largest keyframe jump" is a **one-keyframe spike** (a single much brighter or
  darker keyframe, mostly near stream restarts; persistent 30-s step ≈ 0), not the illuminator switch; at dusk the
  level falls gradually (persistent steps only 3–9 grey levels), while at dawn all four cameras show one persistent
  step at **07:25 ± 1 min**. All hand-off frames are monochrome (saturation 0.0), confirming IR by day. CH02 passed
  because its hand-off frames happened to work. Next step (to agree with the user): a step detector that ignores
  spikes plus a dusk chain for CH01; user-labelled 09-04 references (day 12:00 and night 03:01) for CH03/CH04, whose
  daytime tracking already fails.
