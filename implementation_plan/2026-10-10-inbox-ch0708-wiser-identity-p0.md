# In-box cameras CH07 / CH08, phase 0: colour segments, WISER box events, WISER in-house arrangement, identity click page

Date: 2026-10-10. Status: **PLANNED** — approved by the user 2026-10-10 ("其余都可以": the four phase-0 items proposed in
the session; the colour CH07/CH08 footage is on this PC; per-rat close-ups in `C:/Users/Cornell/Downloads/SF07.MOV`
… `SF12.MOV`; identity marks on the Notion cohort page). Pre-registered before any result; amendments dated and marked
*before* or *after results*. Builds on the operator's own field design — `../Field_2026_Social_Recording/
EXPERIMENT_ir_identity_color_sampling.md` (label sources 1–4, the pilot conclusion "track-then-assign") and
`COLOUR_SAMPLING_LOG_cohort3.md` — and does not replace it.

## Why

CH01/CH02 labelling has started (WISER-guided loop, `2026-10-06-wiser-label-loop.md`). The in-box cameras CH07 (inside
house_2, roof 7) and CH08 (inside house_1, roof 4) image the houses where the rats sleep, often piled. WISER resolves
**which** house an animal is in (box entry/exit events, validated by the operator on 09-05), and probably the
**arrangement along the box** for still animals (09-10 12:27 flash: two ends separated beyond doubt; 3-min means of the
piled animals 3–14 in apart vs 2–4 in per-fix scatter; our still-pair distance error p95 ≈ 3 in). WISER cannot tell who
lies **on top** (all `location_z` = 0: a 2-D solve; checked 2026-10-10 on 142 831 fixes). The colour flashes
(09-09 → 09-11) are the identity oracle that calibrates the arrangement layer.

## Facts (do not re-derive)

- Video: `F:/3rd_rat/<YYYY-MM-DD>/CH07|CH08/CH0x_<date>_<HH-MM-SS>[_to_<HH-MM-SS>].mp4`, 2560 × 1920, 20 fps, GOP 2 s,
  all day; cameras sit in the lids, which are lifted at every battery round (moves median 4.9 px CH07 / 2.4 px CH08,
  up to 31 / 96 px; per-lid-segment corrections in `cv/cv_field/frame_correction.py`, lid events
  `cv/configs/cohort3_lid_events.json`, reference frames 09-04 12:00 / 03:01; `cv/cv_field/CAMERA_GEOMETRY_2026c.md`).
- Colour: IR by default; colour inserts per the colour log (09-09 19:10 test; 09-10 AM placement + 7 pile flashes
  12:27, 12:52, 13:52, ≈ 14:08, 14:33, 15:23, 16:30; 09-11 ≈ 09:40, ≈ 10:00, 14:10, 14:44, 14:50, 18:29; several
  "camera tbc", most video times unread). Colour settles ≈ 3.5 s after ON, IR white-out ≈ 3 s after OFF; colour needs
  daylight (unusable after ≈ 19:00).
- Identity marks (Notion animal table): SF07 tag 3079, coban green, sticker orange, IR pattern x; SF08 3062, red,
  silver, none; SF09 3077, pink/black/brown, blue, star; SF10 306b, blue → **yellow from 08-31**, yellow, square with
  cross; SF11 305a → 3058 (09-02), white, green, circle — **tag retired 09-07 06:10:45, the animal stays in the
  paddock untagged**; SF12 3059, yellow → **blue from 08-31**, red, two lines. After 09-07 06:10 the WISER roster of a
  house is therefore a **lower bound** (SF11 invisible to WISER).
- WISER box events (operator, validated 09-05): house rectangle dilated by 15 in, 6-s smoothing, 20-s minimum dwell;
  ground truth 09-05: all six exit house_2 together at 08:47:08; five enter house_2 09:49:49–09:50:15 in the order
  SF09, SF07, SF11, SF10, SF12; SF08 → house_1. CH07 = house_2 (09-07 evidence; SF11's implant came off 06:10:45 in a
  six-rat huddle in CH07).
- Scope: before the population change 09-11 19:40 (user 2026-10-07: females not tracked).

## A. Colour segments (numbers only)

1. Days 09-09 → 09-11 (both cameras, every hourly file): decode I-frames only (GOP 2 s), per frame the chroma
   c = mean |R−G| + |G−B| over the frame; IR vs colour threshold = the largest gap in log c (as in
   `sam3_vs_yolo_c1.py`), reported. Colour runs → refine both edges at full frame rate within ± 3 s.
2. Control: two random hours on each of three other days per camera → expect no colour; any found is reported.
3. Out: `colour_segments.csv` (camera, start, end in field-PC time = file-name start + PTS, duration, median c, the
   colour-log row it matches within ± 2 min of the operator's clock (the operator's clock ran ≈ 35 s fast on 09-09),
   unmatched flags). Fills the log's empty "video" column (as a table here; the recording repo is not edited).

## B. WISER box events and in-house positions

1. From the production default tracks (`wiser/src/default_tracks.py`, V3/B2; `valid`, no `m_*` flag), per tagged
   animal, 08-30 → 09-11 19:40, house membership with the operator's parameters (house_1 / house_2 rectangles from
   `wiser/configs/wiser_rois.json` + 15 in, 6-s smoothing, 20-s minimum dwell) → `box_events.csv` (animal, house,
   enter/exit, time) and `box_occupancy_1s.csv.gz` (per second: roster per house, all_tracked).
2. **Check against the operator's 09-05 ground truth** (A5 below) and report the time differences.
3. In-house positions: the accepted WISER → paddock map (`…/cv_field_wiser_assist_p0_20261005_2211/mapping.json`)
   then the house frame — house_2 pose from the calibration (centre (342.4, 117.7) in, ridge 92.0°), house_1 cohort
   pose `cv/configs/house1_cohort_pose_2026c.json` — giving (along-ridge, across-ridge) in inches. Per animal per minute
   inside a house: mean, SE, n fixes, share of IMU-still seconds (`imu_state`). → `inhouse_minutes.csv.gz`.
4. Camera assignment check: at the colour-scan resolution (I-frames, 09-09 → 09-11), per-minute frame-difference
   energy of CH07 and CH08 vs per-minute WISER entries/exits per house; the expected pairing CH07↔house_2,
   CH08↔house_1 is reported with its correlation (no decision is taken from it; the 09-05 evidence stands).
5. Ground-truth check (B2): event times vs the operator's 09-05 times, and the entry order; pass if the order matches
   and every |Δt| ≤ 30 s; else report and stop B's use for identity.

## C. Identity click page for the user

Per colour segment found in A (deduplicated by configuration: one entry per segment):
- frames: the colour frame at the segment middle, and IR frames at 6 s and 15 s after the segment end (after the
  white-out), full resolution, upright as recorded (no rotation for the in-box cams);
- panel: WISER roster of that house at the flash (tagged animals; "SF11 untagged after 09-07 06:10 — may be present"),
  each animal's minute-mean position drawn as a top view of the house (along / across ridge) with SE bars, IMU state;
  the identity legend (table above) and links to the close-up clips (`Downloads/SF07.MOV` … transcoded once to H.264
  MP4 into the run folder, originals untouched);
- the user clicks each visible rat's head on the colour frame and picks its id (SF07–SF12 / unknown) with a
  confidence (sure / likely) and, optionally, the same rat on the IR frames; per segment a field "pile composition
  complete? yes/no";
- self-contained `index.html` (file://), localStorage, Export CSV + JSON → `cv/configs/inbox_identity_2026c/`.
The agent never judges the images and never pre-fills any identity.

## Pre-registered use of the user's clicks (a later step, not run in phase 0)

Per house, fit the image ↔ house-frame mapping (2-D similarity on the clicked heads vs the WISER minute means of the
same animals, after correcting the clicks to the house's lid-segment reference frame) and the WISER bias; leave-one-
flash-out residuals. **The operator's own rule:** the arrangement layer (who lies where, from WISER minute means) is
accepted if the left-to-right order along the box from WISER matches the clicked order in **≥ 4 of the first 5**
flashes with ≥ 3 identified animals; until then trust WISER separations > 15 in per fix and > 8 in for 1-min means only.

## Outputs, code, rules

- Code `cv/cv_field/inbox_p0.py` (A, B) and `cv/cv_field/inbox_identity_page.py` (C), each `--selftest`.
- Run folder `$OUT/2026c/cv_field_inbox_p0_<ts>/`; report `results/2026c/cv_field/reports/cv_field_inbox_p0_2026c.md`
  (+ pointer `run_manifest_inbox_p0_2026c.json`); change_log, both index READMEs, CLAUDE.md cv_field map, HANDOFF,
  data map (new section).
- Read-only: `F:/3rd_rat`, the WISER caches, `Downloads/*.MOV`, the recording repo, Notion. No training, no labels made
  by the machine, the agent never judges images. Before 09-11 19:40 only. CPU (+ video decode); no GPU needed.

## Later (not approved)

Phase 1: a CH07/CH08 box-labelling package for the undergrad's loop (frames stratified by WISER house count ×
IMU still/active × day/night × lid segment, entry/exit frames with known identity, IR frames next to colour flashes),
with a house-roster panel instead of WISER circles; SAM3 tried as a pre-labeller on these close-up frames, scored on
the user's labels.
