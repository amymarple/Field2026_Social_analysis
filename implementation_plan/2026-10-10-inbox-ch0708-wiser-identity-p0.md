# In-box cameras CH07 / CH08, phase 0: colour segments, WISER box events, WISER in-house arrangement, identity click page

Date: 2026-10-10. Status: **DONE (phase 0), 2026-10-10** — amendments 1–11 at the end; the clicks step ran 2026-10-11 on a browser snapshot (PRELIMINARY, status at the end). Approved by the user 2026-10-10 ("其余都可以": the four phase-0 items proposed in
the session; the colour CH07/CH08 footage is on this PC; per-rat close-ups in `D:/Field2026_analysis_out/2026c/inhand_closeups/SF07.MOV` (amendment 5)
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
  house is therefore a **lower bound** (SF11 invisible to WISER). **[corrected 2026-10-11, see amendment 12: SF11 kept its tag
  and left the paddock at the 09-07 AM round (last fix 08:20); rosters are complete except in tag dropouts]**
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
- panel: WISER roster of that house at the flash (tagged animals; "SF11 untagged after 09-07 06:10 — may be present"
  **[corrected 2026-10-11, see amendment 12]**),
  each animal's minute-mean position drawn as a top view of the house (along / across ridge) with SE bars, IMU state;
  the identity legend (table above) and links to the close-up clips (`$OUT/2026c/inhand_closeups/SF07.MOV` … (amendment 5) transcoded once to H.264
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
- Read-only: `F:/3rd_rat`, the WISER caches, `$OUT/2026c/inhand_closeups/*.MOV` (amendment 5), the recording repo, Notion. No training, no labels made
  by the machine, the agent never judges images. Before 09-11 19:40 only. CPU (+ video decode); no GPU needed.

## Later (not approved)

Phase 1: a CH07/CH08 box-labelling package for the undergrad's loop (frames stratified by WISER house count ×
IMU still/active × day/night × lid segment, entry/exit frames with known identity, IR frames next to colour flashes),
with a house-roster panel instead of WISER circles; SAM3 tried as a pre-labeller on these close-up frames, scored on
the user's labels.

## Amendments

**Amendment 1 (2026-10-10, before any B result) — fix rule for the box events.** The default tracks' `m_handling` mask
covers every operator round (09-05: 08:40:00–09:49:59), i.e. exactly the moments of the 09-05 ground-truth events, so the
plan's "no `m_*` flag" would delete the events B2 / B5 must check. Primary rule: `valid` ∧ ¬`m_off_animal` ∧
¬`m_tag_validity`; `m_handling`, `m_silence` and `m_adc_lane` fixes are kept (`m_adc_lane` is a neural-logger electrical
window with no bearing on the UWB tag) and each event carries `in_handling`. The literal rule is computed and reported as a
sensitivity (box_events_sensitivity.csv.gz, check_0905_sensitivity.csv).

**Amendment 2 (2026-10-10, before any B result) — the operator's parameters, made exact.** The operator's script
(`wiser_box_transitions.py`, old `Field_2026_Social` repo) is not on this PC, so "6-s smoothing" and "20-s minimum dwell" are
implemented as: per second s the share of fixes in [s − 3, s + 3) inside the dilated rectangle, in-house if ≥ 0.5, unknown
without fixes; a change of state is accepted only when the new state lasts ≥ 20 s (shorter runs keep the old state); unknown
stretches < 20 s are bridged, longer ones make the state unknown and a change across them is flagged with its length.
Membership uses the default-track (x, y); the raw fixes are a sensitivity. Definitions in the report.

**Amendment 3 (2026-10-10, before any result) — specification details.** A2 controls: per camera 3 days drawn from
08-31 … 09-08 (full video days before the first colour insert) and 2 daylight hours 08–18 each (colour needs daylight),
seed 20261010. A3 log matching: nearest row of the same date whose camera field names the camera, operator ON (else OFF,
else the planned slot of an un-noted row) within ± 120 s of the segment interval; a round row without a time matches a
segment inside the round window (− 5 / + 30 min); Δ is reported raw and + 35 s. B4: I-frames within ± 10 s of a colour
segment are excluded from the energy; reported for all minutes and outside lid events (± 5 min); a circular-shift share is
added as context. C: the pre-flash position window is [ON − 60 s, ON); the roster is read at the segment middle.

**Amendment 4 (2026-10-10, after the first B3 table) — in-house fixes.** In the first in-house table 1.4 % of minute means lay
> 30 in from the house centre: excursions shorter than the 20-s dwell keep the cleaned state but their fixes pulled the minute
mean. In-house fixes are now those whose second has the house state AND that lie in the house's dilated rectangle; a
descriptive column `in_body_footprint` (minute mean within the body rectangle + 3 in) is added. Box events and occupancy are
unchanged. After the change 1.0 % of minute means remain > 30 in from the centre (animals inside the dilated rectangle but
beside the house); 77 % of minutes have `in_body_footprint`.

**Amendment 5 (2026-10-10, the user via the session) — close-up source.** The six in-hand clips are read from
`D:/Field2026_analysis_out/2026c/inhand_closeups/SF07.MOV … SF12.MOV` (read-only; sha256 checked against its
`MANIFEST_sha256.csv`; the folder was made for them at the user's request on 2026-10-10). SF07–SF10 and SF12 were filmed 2026-09-10 07:54–08:19; SF11 on
2026-08-30 (its implant came off early); the files' `creation_time` tag is the transfer time.

**Amendment 6 (2026-10-10, after the A results) — floor of the IR / colour threshold.** With the pre-registered floor 10⁻⁴
the largest log-chroma gap over the 243 630 I-frames of 09-09 → 09-11 19:40 fell inside the IR cluster (0.00081 → 0.0114,
1.15 decades; thr 0.0030): seven isolated IR I-frames carry rounding-level chroma 0.0008–0.53 (two of them on CH08 at
23:00 and 23:39, when colour is impossible; decoded at full rate, their whole GOP carries it). The pre-registered threshold
gave 28 colour runs, six of them single-I-frame 2-s runs on such frames, and 5 "colour" I-frames in the control hours
(09-01 08:xx). The same largest-gap rule with the floor raised to 0.01 (2.4 decades below the lowest colour I-frame) gives
thr = 1.18 (gap 0.53 → 2.61, 0.69 decades; next gap 0.65 decades): 22 segments, 0 colour I-frames in the controls, and every
threshold in (0.53, 2.61) gives the identical classification because no I-frame lies in that interval. The pre-registered
outputs stay in the run (`colour_segments_prereg_thr.csv`, `colour_log_rows_prereg_thr.csv`, `control_hours_prereg_thr.csv`,
`colour_threshold_prereg.json`; `colour_threshold.json` → `prereg_floor_1e-4`). One isolated I-frame lies near a planned
slot (CH07 09-11 13:02:09, c = 0.36, 2.1 min after the un-noted 13:00 slot): IR under the amended rule, listed in the report.

**Amendment 7 (2026-10-10, after results; the user's correction) — identifying colours.** The colour that identifies each rat
(authoritative for the cohort except the first, "messy" days ≈ 08-30 / 08-31; **SF09 / SF10 reversed — corrected the same day by
amendment 10: SF09 black, SF10 blue**): SF07 green, SF08 red, SF09 blue, SF10 black,
SF11 white (looks grey), SF12 yellow. It differs from Notion's coban column for SF09 (Notion pink/black/brown; blue = the
sticker), SF10 (Notion blue → yellow from 08-31; black is not in Notion) and SF12 (Notion yellow → blue from 08-31; yellow =
the pre-08-31 coban and the 09-09 incident log); the user's statement wins. Added as columns `id_colour` / `id_colour_note` to
`wiser/configs/rat_identities_2026c.csv` (no existing column changed; `make_imu_video_review.py` and
`make_wiser_event_review.py`, which parse `coband_color`, load it unchanged and their self-tests pass). The click page's legend
is built from that CSV (identifying colour first and bold, Notion coban / sticker for reference; click markers take the
identifying colour); re-rendered at the same path, no video decoded, localStorage key unchanged.

**Amendment 8 (2026-10-10, after results; the user's bug report and the session's recommendation) — click editing and blind
first.** The user: markers could not be deleted or were hard to select / move. The page now selects a marker clicked within
12 screen px (never adds one there), drags, nudges (Shift / Alt + arrows = 1 / 10 image px), relabels (1–6 = SF07–SF12,
0 = unknown, c = sure / likely, or the list's dropdowns), deletes (Delete / Backspace, right-click, × in a per-frame list),
with undo / redo (Ctrl+Z / Ctrl+Y); markers have a constant screen size with the id inside. **Blind first:** per segment the
WISER roster and top view are hidden until "Save clicks & reveal WISER" (per segment, cannot be undone); the clicks saved then
get `before_reveal: true` and a frozen `verdict_first`, and the pre-registered ≥ 4-of-5 order test uses those; later edits are
recorded separately (`edited_after_reveal`, `deleted_after_reveal`, `before_reveal: false` for new clicks); `revealed_at` per
segment. Clicks stored by the first page version become `before_reveal: true, legacy: true` on first load — that version
showed the WISER panel, so legacy clicks are not blind; the later step must treat them accordingly. Checked in headless Chrome
on the synthetic self-test page and on the real page (throwaway profiles).

**Amendment 9 (2026-10-10, after results; display only) — top-view orientation.** The user: "before the rotation I thought
it was right, after the rotation not quite". The top view had been drawn in the house frame (along = ridge ≈ paddock +y to
the right, across ≈ −x up), a ~90° rotation of the paddock map, and the in-box image has its own unknown orientation, so
side-by-side views can look rotated or mirrored and the left-right order flips. (The user had suspected SF09 / SF10 swapped
in WISER; the session's head-IMU vs raw-WISER-speed cross-correlation has a dominant diagonal on 09-06 and 09-08, so WISER
identity stands; identities and `id_colour` are unchanged, the user decides after the oriented view.) The top view is now drawn
in paddock directions with an orientation control **per house** (applies to all its segments): 4 rotations × mirror; default
= WISER / paddock orientation (+x right, +y up); edges labelled "toward x = 0 wall / x = 480 wall / y = 0 (row A) / y = 240
(row C)"; the nearest pole drawn (house_1 B1, house_2 B3); house body outline and ridge kept. Visible only after the reveal.
Stored per house with a timestamp and exported as `orientation_by_house: {house: {rot_deg, mirror, chosen_at}}`. It is a
display setting, **not a fit and not the pre-registered camera ↔ WISER mapping** (still fitted from the blind clicks); the
user's chosen orientation may serve as an independent prior / check for that fit.

**Amendment 10 (2026-10-10, after results; the user's correction) — SF09 black, SF10 blue.** With the oriented top view the
user: "感觉是我错了 SF9是黑色，SF10是蓝色。这样就对上了" — the user had the two colours reversed. `id_colour` is now SF09 black (agrees
with Notion's coban pink/black/brown, nickname "black pink") and SF10 blue (agrees with Notion's coban; Notion's "yellow coban
08-31" note is not in effect on the labelling days); SF07 / SF08 / SF11 / SF12 unchanged. The session renamed the close-up
sources the same way (`inhand_closeups/SF09.MOV` = the 51.6-s clip, `SF10.MOV` = the 41.4-s clip; manifest updated); the page's
transcoded MP4s were relinked by the source sha256 recorded at transcode time (renamed, not re-transcoded; durations
51.64 / 41.45 s match). Stored clicks: on the first load of the fixed page, SF09 ↔ SF10 is swapped once on every click saved
before that moment (and on `verdict_first`), originals kept (`animal_before_sf09_sf10_fix`, `relabelled_sf09_sf10`), a banner
offers a one-click undo; guarded by a stored flag `sf09_sf10_fix`; exported. The identity of WISER tags is unaffected
(the session's IMU ↔ WISER check); only the colour → animal key changed.

**Status (2026-10-10): phase 0 DONE** — A, B, C run; report `results/2026c/cv_field/reports/cv_field_inbox_p0_2026c.md`;
change log `change_log/2026-10-10-inbox-ch0708-p0.md`. The pre-registered use of the user's clicks waits for the clicks.

**Amendment 11 (2026-10-11, the click step; written before any fit, order or assignment result was computed — only the
click table had been listed) — how the pre-registered use of the clicks is run.** Input: the browser snapshot
`cv/configs/inbox_identity_2026c/browser_snapshot_20261010T2017.json` (the page's localStorage, not a formal export; 141
clicks in 11 of 22 segments, all CH07 / house_2; no legacy click). *Blind record* = clicks with `before_reveal` true,
`legacy` not true and a `verdict_first`, read from `verdict_first`; clicks added after the reveal and clicks of a segment not
yet revealed are reported but used by none of the fit, the order test or the assignment. Each click → the lid-segment
reference pixel by its `B_frame_to_ref`; display coordinates (p, q) = (u_ref, −v_ref) (image right, image up). WISER = the
page's minute means (default-track mean of the in-house fixes over [ON − 60 s, ON)); raw-fix means and a window centred on
the colour frame, [mid − 30 s, mid + 30 s), are sensitivities. **Fit:** least-squares 2-D similarity (p, q) → (along,
across) in inches, both handednesses (proper = no mirror of the displayed image; improper = mirrored), on the blind
colour-frame clicks of named animals that have a WISER mean; leave-one-flash-out (LOFO) residuals in inches and px; the
handedness with the lower LOFO RMS is used downstream, the other is reported. The fitted rotation is converted to the
page's orientation convention and compared with the user's display orientation (house_2: 180°, no mirror). **Order test:**
a flash is eligible if ≥ 3 animals have both a blind named colour click and a WISER mean; the first 5 eligible flashes in
time order; WISER order = by along-ridge mean; click order = by the along coordinate of the clicks mapped by the fit that
leaves that flash out; exact match = identical permutation; ACCEPTED if ≥ 4 of 5. Tie version: pairs with
|Δalong_WISER| < 8 in are not tested; the flash matches if every tested pair is concordant. Reported with it: Kendall τ per
flash, all eligible flashes, a fixed-rotation map at the user's orientation (scale and offset fitted LOFO), and a reading in
which a flash with ≥ 3 clicked animals but no WISER mean counts as a non-match. **Assignment (beyond the test):** per flash,
Hungarian assignment on the Euclidean distance (in) between the LOFO-mapped clicks and the WISER means of the roster animals
with a mean; accuracy per click against the user's colour IDs, by the clicked animal's WISER separation (distance to the
nearest other roster animal's mean); chance = 1 / (number of candidates). **Colour → IR stability:** per animal clicked on
the colour frame and on an IR frame of the same segment, the head displacement in px (and in inches at the fitted scale),
with the time between the two frames and the head-IMU state over it (`imu_seconds_cache`). Driver
`cv/cv_field/inbox_click_analysis.py`; report `results/2026c/cv_field/reports/cv_field_inbox_clicks_2026c.md`.

**Status (2026-10-11, after results): the click step, PRELIMINARY** — run on the browser snapshot `cv/configs/inbox_identity_2026c/browser_snapshot_20261010T2017.json` (not a formal export; 10 revealed segments, 8 in the fit). Fit: proper handedness, 79.3 px/in, page-equivalent rotation 178° vs the user's 180° (Δ −1.8°), LOFO RMS 5.96 in / 470 px. **Pre-registered order test: NOT ACCEPTED** (exact order 0 of the first 5 flashes, 0 of 8); tie version (pairs < 8 in not tested) 4 of 5; Kendall τ median +0.40. The arrangement layer is therefore not accepted; WISER separations stay trusted only above 15 in per fix / 8 in for 1-min means. Report `results/2026c/cv_field/reports/cv_field_inbox_clicks_2026c.md`, change log `change_log/2026-10-11-inbox-clicks.md`. Re-run on the user's export when it exists.

**Amendment 12 (2026-10-11, correction of a fact; no result changes) — SF11 kept its tag and left the paddock.** The user:
"SF11 has tag". The Facts line "tag retired 09-07 06:10:45, the animal stays in the paddock untagged … the WISER roster of a
house is therefore a lower bound (SF11 invisible to WISER)" was wrong. The field record
(`field2026-sync/from-field/2026-09-21_cohort3-incident-log.md`, 09-07): "Rat SF11 stays in the group: WISER tag 3058 and
video/behavior continue; only the ephys stream ends" and "tag 3058 (SF11) last regular fix 2026-09-07 08:20 … the animal left
the arena at the round"; 09-11 19:40 "population 5 -> 10". So the tag stayed on the rat when the implant fell off (≈ 06:10),
the rat left the paddock at the 09-07 AM round, and from 08:20 to 09-11 19:40 the paddock held five animals, all tagged.
Rosters are incomplete only in tag dropouts: SF11's 305a 09-02 00:03 → ≈ 08:00–08:15, and SF12 on night 08-30/31 (its tag's
first fix 08-31 06:36). The SF11 rule of `inbox_p0.py` / `inbox_identity_page.py` is corrected: after 09-07 08:20 SF11 is
**absent** (`sf11_absent`), not "untagged, present"; the page's roster note reads "SF11 left the paddock at the 09-07 AM round
(last fix 08:20); rosters are complete except in tag dropouts"; the 09-02 dropout note is unchanged. **No result changes:**
box events, the 09-05 check, segments, in-house positions, rosters (re-checked for all 22 segments against `states_1s.npz`),
the camera ↔ house check and every click-step number are identical; the only quantity that depended on the premise is the
coverage share `all_tracked` (box_occupancy_1s.csv.gz rebuilt from the unchanged states: 48.9 % → 83.8 % of the scope; the
10-10 file is kept in `superseded_20261011/`). **Possible error to check separately (not changed):** SF11's fixes 09-07
06:10:45 → 08:20 are flagged `m_off_animal` in the production default tracks (the tag "rode on the dropped implant"), while the
field note says the tag stayed on the rat and 07:40 → 08:20 is real position data for it; here SF11 is counted present but
untracked in that window. The production tracks are not changed.
