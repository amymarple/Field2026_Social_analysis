# In-box camera CH07 (house_2): the user's first identity clicks — composition, colour → IR stability, camera ↔ WISER fit, the pre-registered order test, WISER as an identity aid (cohort `2026c`)

**PRELIMINARY — data = browser snapshot 2026-10-10 20:17 of the identity page's localStorage (`cv/configs/inbox_identity_2026c/browser_snapshot_20261010T2017.json`, sha256 `b37a94cb00ae732a…`), 11 / 22 segments clicked, not a formal export.** The user has not exported yet; every number below can change when the export arrives (re-run: `python cv/cv_field/inbox_click_analysis.py --clicks <export.json>`).

Plan `implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md` (section "Pre-registered use of the user's clicks" + amendments 1–11; amendment 11 = how this step is run, written before any result). Run `D:/Field2026_analysis_out/2026c/cv_field_inbox_clicks_20261010_2042`; generated 2026-10-10T20:43:11; code `53c13c12a6ffc181770df7f24179e8fae4df20a7+dirty`. Phase-0 run `D:/Field2026_analysis_out/2026c/cv_field_inbox_p0_20261010_1702`. Driver `cv/cv_field/inbox_click_analysis.py`. The agent never looked at a frame; everything is computed from the click coordinates, the user's IDs and WISER.

**Correction 2026-10-11 (text only, plan amendment 12).** An earlier version of this report said SF11 was untagged after 09-07 06:10:45 and called every roster a lower bound. Wrong: SF11 kept its tag and left the paddock at the 09-07 AM round (last fix 08:20); from then to 09-11 19:40 the paddock held five animals, all tagged, so rosters are complete except in tag dropouts and while a tagged animal is untracked. No number in this report depended on that reading: the rosters and untracked lists come from the phase-0 page data and the cleaned per-second states, which are unchanged (all 22 segments re-checked against `states_1s.npz`), and SF11 is in no roster or untracked list after 09-07 under either reading. Edited by hand; the generator `inbox_click_analysis.py` carries the corrected wording.

## Summary

- **Data**: 141 clicks (135 blind, 5 after the reveal, 1 unsaved, 0 legacy) in 11 of 22 segments, all CH07 / house_2.
- **1. Composition**: colour-frame set = WISER roster in 8 of 10 revealed segments; SF11 never clicked; 3 unknown clicks.
- **2. Colour → IR**: where the IR frame is < 30 s after the colour frame the clicked heads moved median 27 px (≈ 0.3 in), max 387 px; 6 of 60 pairs > 100 px.
- **3. Fit**: proper handedness; 79.3 px/in; page-equivalent rotation 178° vs the user's 180° (Δ -1.8°); LOFO RMS 5.96 in / 470 px.
- **4. Pre-registered order test: NOT ACCEPTED** (0 of 5 exact; needs 4); tie version ACCEPTED (4 of 5); Kendall τ median +0.40.
- **5. WISER as an identity aid**: Hungarian assignment 65% correct (chance 20%); [0, 4) in: 70% (n 10), [4, 8) in: 60% (n 20), [8, 15) in: 50% (n 6), >= 15 in: 100% (n 4).

## The question: what do the colour labels tell us, and can WISER serve as an identity-label aid?

Preliminary (snapshot, 8 flashes in the fit); every statement is a number from the sections below.

- **Which animals are in the box — yes, WISER helps.** The house roster equalled the colour-clicked set in 8 of 10 revealed flashes, with no clicked animal outside the roster; in the other 2 (long colour segments during the morning rounds, where the colour frame lies minutes after ON) every roster animal was clicked on some frame of the segment. Rosters are complete here: all five animals in the paddock were tagged (SF11 had left at the 09-07 AM round; corrected 2026-10-11, plan amendment 12); SF11 was never clicked.
- **Who lies where inside a pile — not from WISER minute means.** The pre-registered order test is NOT ACCEPTED (exact order 0 of 5, 0 of 8 overall; Kendall τ median +0.50); mapped heads sit 6.0 in RMS from their own WISER mean while pile neighbours are a median 5.7 in apart, and neither a per-flash nor a per-tag offset removes that error. Assigning heads by WISER gets 65% right (chance 20%).
- **Where WISER separations can be trusted.** Pairs ≥ 8 in apart along the ridge were ordered correctly in 25 of 28 (89%; tie version ACCEPTED); heads ≥ 15 in from every other animal were assigned correctly in 4 of 4. So WISER can name an animal lying apart at one end of the box and order clearly separated animals; it cannot resolve the order inside the pile (the plan's rule "trust > 8 in for 1-min means only" stands).
- **The colour labels and the IR frames.** When the head IMU was still on every second between the colour and the IR frame, the clicked head moved ≤ 44 px (median 21 px ≈ 0.3 in; n 36), consistent with the operator's premise that IR frames can inherit identity from the colour frame; when the IMU registered movement the displacement reached 387 px (median 52 px, n 24). The head IMU is a candidate gate for carrying colour identities into IR (click repeatability on one head is not measured).
- **Camera geometry, as a by-product.** The blind clicks alone recover the CH07 ↔ house orientation: 178°, not mirrored, vs the user's display choice of 180° made by eye before any fit (Δ -1.8°); scale 79 px/in; the image centre lands 3.3 in from the WISER house centre.

## Which clicks were used

| status | colour_mid | ir_p06 | ir_p15 | total | named | unknown |
|---|---|---|---|---|---|---|
| after_reveal | 0 | 0 | 5 | 5 | 5 | 0 |
| blind | 47 | 49 | 39 | 135 | 133 | 2 |
| unsaved | 1 | 0 | 0 | 1 | 0 | 1 |


SF09 / SF10 one-time swap (amendment 10): applied to 6 clicks (all of segment 09-09 19:10, before the fix; `undone_at` = None); `animal` already carries it. No click is legacy; no blind click was edited or deleted after its reveal (edited 0, deleted 0); the blind record and the live values agree on all 135 blind clicks (max |Δ| 0.00 px, 0 label differences). Orientation: snapshot `orientation_by_house.house_2` = rot 180°, mirror False; `cv/configs/inbox_camera_orientation_2026c.json` = rot 180°, mirror False; chosen 2026-10-11T00:11:10.183Z UTC, after 5 segments had been revealed (so the user had seen WISER top views; the orientation used no fitted number).

## 1. Composition: clicked on the colour frame vs the WISER roster

Roster = tagged animals whose cleaned house state is house_2 at the colour frame (dilated house zone, plan B; SF11 had left the paddock at the 09-07 AM round, so the roster covers every animal present that WISER locates; corrected 2026-10-11, plan amendment 12). Clicked = named blind clicks on the colour frame.

| segment_id | revealed | n_clicks | n_blind | roster | untracked | clicked_colour | n_unknown_colour | missing | extras | agree | clicked_any_frame_blind | missing_any_frame_blind | clicked_any_frame_final |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_071415 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_083742 | yes | 14 | 14 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF10,SF12 | 1 | SF08,SF09 |  | no | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_091147 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_122703 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_125142 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_135131 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_141613 | yes | 10 | 10 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_143243 | yes | 15 | 10 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_152307 | no | 1 | 0 | SF07,SF08,SF09,SF10,SF12 |  |  | 0 | SF07,SF08,SF09,SF10,SF12 |  | - |  | SF07,SF08,SF09,SF10,SF12 |  |
| CH07_20260911_092822 | yes | 11 | 11 | SF07,SF08,SF09,SF10 | SF12 | SF07,SF08,SF09 | 0 | SF10 |  | no | SF07,SF08,SF09,SF10 |  | SF07,SF08,SF09,SF10 |


- 11 segments carry clicks, 10 of them revealed (the 11th, 09-10 15:23:07, holds 1 unsaved click(s), not yet revealed).
- Colour-frame set = WISER roster in **8 of 10** revealed segments (09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42, 09-10 13:51:31, 09-10 14:16:13, 09-10 14:32:43).
- 09-10 08:37:42: roster SF07,SF08,SF09,SF10,SF12; colour frame SF07,SF10,SF12 + 1 unknown → missing SF08,SF09, extras -; on any frame (blind) SF07,SF08,SF09,SF10,SF12 (missing -).
- 09-11 09:28:22: roster SF07,SF08,SF09,SF10 (untracked SF12); colour frame SF07,SF08,SF09 + 0 unknown → missing SF10, extras -; on any frame (blind) SF07,SF08,SF09,SF10 (missing -).
- Unknown (`None`) clicks: 3 in all (09-10 08:37:42 colour_mid, 09-10 08:37:42 ir_p15, 09-10 15:23:07 colour_mid). Extras (a clicked animal outside the roster): 0 segments. SF11 was clicked **never** (it left the paddock at the 09-07 AM round, last fix 08:20, so it cannot be in a pile here; corrected 2026-10-11, plan amendment 12).

## 2. Stability colour → IR (the premise that a pile does not move across the switch)

| segment_id | ir_frame | dt_s | n_colour | n_ir | n_both | colour_not_ir | ir_not_colour | median_px | max_px | median_in | max_in | imu |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | ir_p06 | 12.7 | 5 | 5 | 5 |  |  | 47 | 111 | 0.6 | 1.4 | moved 5 |
| CH07_20260909_191025 | ir_p15 | 21.8 | 5 | 5 | 5 |  |  | 57 | 164 | 0.7 | 2.1 | moved 5 |
| CH07_20260910_071415 | ir_p06 | 37.0 | 5 | 5 | 5 |  |  | 19 | 38 | 0.2 | 0.5 | no IMU 5 |
| CH07_20260910_071415 | ir_p15 | 46.1 | 5 | 5 | 5 |  |  | 15 | 30 | 0.2 | 0.4 | no IMU 5 |
| CH07_20260910_083742 | ir_p06 | 544.4 | 3 | 5 | 3 |  | SF08,SF09 | 956 | 1444 | 12.1 | 18.2 | moved 3 |
| CH07_20260910_083742 | ir_p15 | 553.5 | 3 | 4 | 3 |  | SF09 | 939 | 1461 | 11.8 | 18.4 | moved 3 |
| CH07_20260910_091147 | ir_p06 | 16.1 | 5 | 5 | 5 |  |  | 15 | 26 | 0.2 | 0.3 | all still 5 |
| CH07_20260910_091147 | ir_p15 | 25.1 | 5 | 5 | 5 |  |  | 17 | 28 | 0.2 | 0.4 | all still 5 |
| CH07_20260910_122703 | ir_p06 | 17.5 | 5 | 5 | 5 |  |  | 24 | 31 | 0.3 | 0.4 | all still 5 |
| CH07_20260910_122703 | ir_p15 | 26.5 | 5 | 5 | 5 |  |  | 18 | 35 | 0.2 | 0.4 | all still 4, moved 1 |
| CH07_20260910_125142 | ir_p06 | 12.5 | 5 | 5 | 5 |  |  | 43 | 294 | 0.5 | 3.7 | moved 4, all still 1 |
| CH07_20260910_125142 | ir_p15 | 21.5 | 5 | 5 | 5 |  |  | 43 | 108 | 0.5 | 1.4 | moved 4, all still 1 |
| CH07_20260910_135131 | ir_p06 | 16.7 | 5 | 5 | 5 |  |  | 21 | 44 | 0.3 | 0.6 | all still 5 |
| CH07_20260910_135131 | ir_p15 | 25.7 | 5 | 5 | 5 |  |  | 26 | 38 | 0.3 | 0.5 | all still 5 |
| CH07_20260910_141613 | ir_p06 | 17.0 | 5 | 5 | 5 |  |  | 41 | 387 | 0.5 | 4.9 | moved 3, all still 2 |
| CH07_20260910_141613 | ir_p15 | - | 5 | 0 | 0 | SF07,SF08,SF09,SF10,SF12 |  | - | - | - | - | - |
| CH07_20260910_143243 | ir_p06 | 10.8 | 5 | 5 | 5 |  |  | 35 | 91 | 0.4 | 1.2 | all still 3, moved 2 |
| CH07_20260910_143243 | ir_p15 | - | 5 | 0 | 0 | SF07,SF08,SF09,SF10,SF12 |  | - | - | - | - | - |
| CH07_20260911_092822 | ir_p06 | 126.9 | 3 | 4 | 3 |  | SF10 | 1030 | 1335 | 13.0 | 16.8 | no IMU 3 |
| CH07_20260911_092822 | ir_p15 | 135.8 | 3 | 4 | 3 |  | SF10 | 1004 | 1251 | 12.7 | 15.8 | no IMU 3 |


- Segments whose IR frame is < 30 s after the colour frame (7 segments, 60 animal × IR-frame pairs): displacement median **27 px** (≈ 0.3 in at the fitted 79 px/in), p75 46 px, max 387 px; ≤ 40 px in 40 of 60, > 100 px in 6 (09-09 19:10:25 SF07 ir_p06 111, 09-09 19:10:25 SF07 ir_p15 164, 09-10 12:51:42 SF12 ir_p06 294, 09-10 12:51:42 SF07 ir_p15 108, 09-10 14:16:13 SF07 ir_p06 336, 09-10 14:16:13 SF08 ir_p06 387).
- Long colour segments (the colour frame is the segment middle, so the IR frames come 09-10 07:14:15 37 s, 09-10 08:37:42 544 s, 09-11 09:28:22 127 s later): median 207 px, max 1461 px — not "seconds around the switch"; these do not test the premise.
- Head IMU between the two frames (short segments): all still: n 36, median 21 px, max 44 px; moved: n 24, median 52 px, max 387 px.
- Animals named on the colour frame but not clicked on the IR frame (blind record): 10 of 92 colour × IR-frame slots (09-10 14:16:13 ir_p15: SF07,SF08,SF09,SF10,SF12; 09-10 14:32:43 ir_p15: SF07,SF08,SF09,SF10,SF12); named on IR but not on colour: 09-10 08:37:42 ir_p06: SF08,SF09; 09-10 08:37:42 ir_p15: SF09; 09-11 09:28:22 ir_p06: SF10; 09-11 09:28:22 ir_p15: SF10.
- Final record (after-reveal additions): 09-10 14:32:43 ir_p15: SF08x2 (one label on two heads; excluded from the displacement).

Per animal (blind record):

| segment_id | ir_frame | animal | dt_s | d_px | d_in | imu_n_s | imu_n_ok | imu_n_still | imu_n_active | imu_n_loco | imu_class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | ir_p06 | SF07 | 12.7 | 111 | 1.4 | 14 | 14 | 0 | 12 | 2 | moved |
| CH07_20260909_191025 | ir_p06 | SF08 | 12.7 | 35 | 0.4 | 14 | 14 | 0 | 14 | 0 | moved |
| CH07_20260909_191025 | ir_p06 | SF09 | 12.7 | 47 | 0.6 | 14 | 14 | 8 | 6 | 0 | moved |
| CH07_20260909_191025 | ir_p06 | SF10 | 12.7 | 74 | 0.9 | 14 | 14 | 13 | 1 | 0 | moved |
| CH07_20260909_191025 | ir_p06 | SF12 | 12.7 | 46 | 0.6 | 14 | 14 | 5 | 9 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF07 | 21.8 | 164 | 2.1 | 23 | 23 | 0 | 21 | 2 | moved |
| CH07_20260909_191025 | ir_p15 | SF08 | 21.8 | 25 | 0.3 | 23 | 23 | 0 | 23 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF09 | 21.8 | 78 | 1.0 | 23 | 23 | 14 | 9 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF10 | 21.8 | 46 | 0.6 | 23 | 23 | 22 | 1 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF12 | 21.8 | 57 | 0.7 | 23 | 23 | 11 | 12 | 0 | moved |
| CH07_20260910_071415 | ir_p06 | SF07 | 37.0 | 6 | 0.1 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF08 | 37.0 | 16 | 0.2 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF09 | 37.0 | 26 | 0.3 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF10 | 37.0 | 19 | 0.2 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF12 | 37.0 | 38 | 0.5 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF07 | 46.1 | 15 | 0.2 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF08 | 46.1 | 14 | 0.2 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF09 | 46.1 | 26 | 0.3 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF10 | 46.1 | 12 | 0.2 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF12 | 46.1 | 30 | 0.4 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_083742 | ir_p06 | SF07 | 544.4 | 1444 | 18.2 | 545 | 545 | 117 | 406 | 22 | moved |
| CH07_20260910_083742 | ir_p06 | SF10 | 544.4 | 956 | 12.1 | 545 | 541 | 201 | 291 | 49 | moved |
| CH07_20260910_083742 | ir_p06 | SF12 | 544.4 | 222 | 2.8 | 545 | 545 | 319 | 196 | 30 | moved |
| CH07_20260910_083742 | ir_p15 | SF07 | 553.5 | 1461 | 18.4 | 554 | 554 | 125 | 407 | 22 | moved |
| CH07_20260910_083742 | ir_p15 | SF10 | 553.5 | 939 | 11.8 | 554 | 550 | 210 | 291 | 49 | moved |
| CH07_20260910_083742 | ir_p15 | SF12 | 553.5 | 191 | 2.4 | 554 | 554 | 319 | 205 | 30 | moved |
| CH07_20260910_091147 | ir_p06 | SF07 | 16.1 | 10 | 0.1 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF08 | 16.1 | 20 | 0.3 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF09 | 16.1 | 15 | 0.2 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF10 | 16.1 | 26 | 0.3 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF12 | 16.1 | 13 | 0.2 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF07 | 25.1 | 26 | 0.3 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF08 | 25.1 | 28 | 0.4 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF09 | 25.1 | 7 | 0.1 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF10 | 25.1 | 17 | 0.2 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF12 | 25.1 | 3 | 0.0 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF07 | 17.5 | 27 | 0.3 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF08 | 17.5 | 31 | 0.4 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF09 | 17.5 | 17 | 0.2 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF10 | 17.5 | 15 | 0.2 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF12 | 17.5 | 24 | 0.3 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF07 | 26.5 | 12 | 0.2 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF08 | 26.5 | 18 | 0.2 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF09 | 26.5 | 20 | 0.2 | 28 | 28 | 26 | 2 | 0 | moved |
| CH07_20260910_122703 | ir_p15 | SF10 | 26.5 | 12 | 0.2 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF12 | 26.5 | 35 | 0.4 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_125142 | ir_p06 | SF07 | 12.5 | 61 | 0.8 | 13 | 13 | 3 | 10 | 0 | moved |
| CH07_20260910_125142 | ir_p06 | SF08 | 12.5 | 15 | 0.2 | 13 | 13 | 13 | 0 | 0 | all still |
| CH07_20260910_125142 | ir_p06 | SF09 | 12.5 | 12 | 0.2 | 13 | 13 | 3 | 10 | 0 | moved |
| CH07_20260910_125142 | ir_p06 | SF10 | 12.5 | 43 | 0.5 | 13 | 13 | 0 | 13 | 0 | moved |
| CH07_20260910_125142 | ir_p06 | SF12 | 12.5 | 294 | 3.7 | 13 | 13 | 0 | 8 | 5 | moved |
| CH07_20260910_125142 | ir_p15 | SF07 | 21.5 | 108 | 1.4 | 22 | 22 | 3 | 14 | 5 | moved |
| CH07_20260910_125142 | ir_p15 | SF08 | 21.5 | 18 | 0.2 | 22 | 22 | 22 | 0 | 0 | all still |
| CH07_20260910_125142 | ir_p15 | SF09 | 21.5 | 43 | 0.5 | 22 | 22 | 12 | 10 | 0 | moved |
| CH07_20260910_125142 | ir_p15 | SF10 | 21.5 | 99 | 1.3 | 22 | 22 | 0 | 20 | 2 | moved |
| CH07_20260910_125142 | ir_p15 | SF12 | 21.5 | 22 | 0.3 | 22 | 22 | 1 | 16 | 5 | moved |
| CH07_20260910_135131 | ir_p06 | SF07 | 16.7 | 16 | 0.2 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF08 | 16.7 | 21 | 0.3 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF09 | 16.7 | 29 | 0.4 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF10 | 16.7 | 12 | 0.1 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF12 | 16.7 | 44 | 0.6 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF07 | 25.7 | 21 | 0.3 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF08 | 25.7 | 36 | 0.5 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF09 | 25.7 | 20 | 0.3 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF10 | 25.7 | 26 | 0.3 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF12 | 25.7 | 38 | 0.5 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_141613 | ir_p06 | SF07 | 17.0 | 336 | 4.2 | 18 | 18 | 0 | 16 | 2 | moved |
| CH07_20260910_141613 | ir_p06 | SF08 | 17.0 | 387 | 4.9 | 18 | 18 | 0 | 15 | 3 | moved |
| CH07_20260910_141613 | ir_p06 | SF09 | 17.0 | 18 | 0.2 | 18 | 18 | 0 | 18 | 0 | moved |
| CH07_20260910_141613 | ir_p06 | SF10 | 17.0 | 33 | 0.4 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_141613 | ir_p06 | SF12 | 17.0 | 41 | 0.5 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF07 | 10.8 | 33 | 0.4 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF08 | 10.8 | 23 | 0.3 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF09 | 10.8 | 91 | 1.2 | 12 | 12 | 0 | 12 | 0 | moved |
| CH07_20260910_143243 | ir_p06 | SF10 | 10.8 | 35 | 0.4 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF12 | 10.8 | 46 | 0.6 | 12 | 12 | 0 | 12 | 0 | moved |
| CH07_20260911_092822 | ir_p06 | SF07 | 126.9 | 615 | 7.8 | 127 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p06 | SF08 | 126.9 | 1335 | 16.8 | 127 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p06 | SF09 | 126.9 | 1030 | 13.0 | 127 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p15 | SF07 | 135.8 | 622 | 7.9 | 136 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p15 | SF08 | 135.8 | 1251 | 15.8 | 136 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p15 | SF09 | 135.8 | 1004 | 12.7 | 136 | 0 | 0 | 0 | 0 | no IMU |


## 3. Pre-registered fit: image (reference px) ↔ house frame (WISER minute means), house_2

Points: 40 blind named colour clicks with a WISER mean in 8 flashes (09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42, 09-10 13:51:31, 09-10 14:16:13, 09-10 14:32:43). Not in the fit: 09-10 08:37:42 (no WISER mean in [ON − 60 s, ON)); 09-10 15:23:07 (not revealed); 09-11 09:28:22 (no WISER mean in [ON − 60 s, ON))

| fit | n | px_per_in | theta_house_deg | theta_paddock_deg | page_rot_deg | page_mirror | d_rot_vs_prior_deg | in_rms_in | lofo_rms_in | lofo_median_in | lofo_rms_px | lofo_median_px |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| proper | 40 | 79.3 | +89.8 | -178.2 | 178.2 | no | -1.8 | 5.56 | 5.96 | 4.29 | 470 | 343 |
| improper | 40 | 224.0 | -53.0 | +39.0 | 219.0 | yes | - | 9.15 | 9.65 | 7.63 | 2416 | 1652 |
| prior_rotation (fixed at the user's 180°) | 40 | 79.3 | +88.0 | -180.0 | 180.0 | no | +0.0 | 5.57 | 5.90 | 4.26 | 466 | 336 |


- **Handedness: proper** fits better — LOFO RMS 5.96 in (proper) vs 9.65 in (improper); in-sample RMS 5.56 vs 9.15 in. Proper = the displayed image is not mirrored relative to the WISER / paddock top view (as expected for a camera looking down).
- Proper fit: scale **79.3 px/in** (WISER inches per image px at head height; at this scale the house body's 24.6-in long side would span ≈ 1952 px and its 18.0-in short side ≈ 1427 px; the ridge maps onto the image's vertical axis (1920 px), the short side onto the horizontal (2560 px) — numbers only, not checked on the image), rotation θ_house +89.8°, θ_paddock -178.2°, page-equivalent orientation **178°, no mirror** vs the user's **180°, no mirror**: Δ = -1.8°.
- LOFO fold rotations range +86.4° … +92.0° (house frame; prior +88.0°); fold scales 72.1 … 85.0 px/in.
- LOFO residuals (primary): RMS **5.96 in**, median 4.29 in; in px RMS 470, median 343 px. For scale: per-fix WISER scatter (SD of the raw fixes in the minute) in the fitted flashes median 4.3 in along (2.1–9.5), 3.0 in across (1.1–7.7); minute-mean SE median 0.24 in; still-pair distance error p95 ≈ 3 in (plan); house body 24.6 × 18 in.
- Image centre (1280, 960) lands at along +1.5 in, across -2.9 in in WISER's house frame (= the WISER bias only if the camera axis meets the house centre; not separable from the camera position with a similarity).
- What the LOFO residual is made of (head mapped − WISER, in): RMS along the ridge 5.06, across 3.15. A common offset per flash (median |mean vector| 2.3 in, max 3.8) removes little: RMS 5.96 → 5.34 in (in-sample, optimistic). A fixed per-animal (tag) offset estimated from the other flashes does not help: RMS → 6.35 in. So the error is mostly animal × flash specific (WISER's minute mean off the clicked head by 6.0 in RMS in a pile), not a bias a per-flash or per-tag correction would remove. Within a flash the WISER means spread more along the ridge than the mapped heads (mean SD 7.4 vs 6.2 in).
- Reproduction: the page's [ON − 60 s, ON) means were recomputed with the page's own code for 45 animal × flash pairs: max |Δ| 0.0000 in; 0 presence mismatches.
- Rotation held at the user's orientation (scale + offset fitted): LOFO RMS 5.90 in (free fit 5.96 in).

LOFO residual per flash (primary fit):

| segment_id | n | rms_in | max_in | rms_px | max_px | fold_theta_house_deg | fold_px_per_in | lid_flag |
|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | 5 | 5.01 | 7.31 | 392 | 573 | +89.0 | 78.4 | ok |
| CH07_20260910_071415 | 5 | 5.00 | 7.84 | 396 | 621 | +91.3 | 79.2 | lid+ok |
| CH07_20260910_091147 | 5 | 5.18 | 9.47 | 404 | 739 | +90.0 | 78.0 | ok |
| CH07_20260910_122703 | 5 | 6.82 | 12.98 | 580 | 1103 | +86.4 | 85.0 | ok |
| CH07_20260910_125142 | 5 | 5.96 | 8.50 | 501 | 714 | +89.5 | 84.0 | ok |
| CH07_20260910_135131 | 5 | 4.13 | 6.95 | 339 | 570 | +89.3 | 82.1 | ok |
| CH07_20260910_141613 | 5 | 8.12 | 16.62 | 585 | 1198 | +90.3 | 72.1 | ok |
| CH07_20260910_143243 | 5 | 6.47 | 11.22 | 494 | 858 | +92.0 | 76.5 | ok |


Mean LOFO residual per animal over its flashes (head mapped − WISER):

| animal | n | mean_along_in | mean_across_in | mean_norm_in | sd_along_in | sd_across_in |
|---|---|---|---|---|---|---|
| SF07 | 8 | -0.44 | -1.97 | 2.02 | 3.07 | 2.57 |
| SF08 | 8 | 2.16 | 2.92 | 3.63 | 5.78 | 3.22 |
| SF09 | 8 | -2.16 | -0.76 | 2.29 | 7.51 | 2.25 |
| SF10 | 8 | 0.36 | 0.24 | 0.43 | 3.87 | 2.76 |
| SF12 | 8 | 0.09 | -0.67 | 0.68 | 4.57 | 3.40 |


## 4. The pre-registered order test (the operator's rule)

Clicks used: **blind record only** (before the reveal, not legacy; there are no legacy clicks), colour frame, named animals with a WISER mean; mapped by the fit that leaves the flash out (proper handedness = the lower LOFO RMS). WISER = default-track minute means over [ON − 60 s, ON).

**Verdict: NOT ACCEPTED** — exact order match in **0 of 5** of the first 5 eligible flashes (needs ≥ 4). Tie version (pairs < 8 in by WISER not tested): **ACCEPTED** (4 of 5). Kendall τ median +0.40 (first 5), +0.50 (all).

| rank | segment_id | n | order_wiser | order_clicks | exact | tau | min_sep_along_in | n_pairs_ge_sep | n_conc_ge_sep | tie_match | discordant_ge_sep |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CH07_20260909_191025 | 5 | SF08 < SF07 < SF10 < SF12 < SF09 | SF08 < SF09 < SF07 < SF10 < SF12 | no | +0.4 | 0.5 | 4 | 4 | yes |  |
| 2 | CH07_20260910_071415 | 5 | SF12 < SF10 < SF07 < SF09 < SF08 | SF07 < SF10 < SF12 < SF09 < SF08 | no | +0.4 | 0.4 | 1 | 1 | yes |  |
| 3 | CH07_20260910_091147 | 5 | SF09 < SF12 < SF08 < SF10 < SF07 | SF08 < SF12 < SF10 < SF09 < SF07 | no | +0.2 | 0.0 | 4 | 2 | no | SF08-SF09, SF09-SF10 |
| 4 | CH07_20260910_122703 | 5 | SF08 < SF07 < SF12 < SF10 < SF09 | SF08 < SF12 < SF07 < SF10 < SF09 | no | +0.8 | 0.7 | 4 | 4 | yes |  |
| 5 | CH07_20260910_125142 | 5 | SF08 < SF12 < SF07 < SF09 < SF10 | SF08 < SF07 < SF12 < SF10 < SF09 | no | +0.6 | 2.0 | 5 | 5 | yes |  |
| 6 | CH07_20260910_135131 | 5 | SF08 < SF07 < SF12 < SF10 < SF09 | SF08 < SF12 < SF10 < SF09 < SF07 | no | +0.4 | 0.0 | 4 | 4 | yes |  |
| 7 | CH07_20260910_141613 | 5 | SF12 < SF09 < SF10 < SF07 < SF08 | SF09 < SF12 < SF10 < SF07 < SF08 | no | +0.8 | 1.3 | 2 | 2 | yes |  |
| 8 | CH07_20260910_143243 | 5 | SF10 < SF12 < SF08 < SF07 < SF09 | SF12 < SF10 < SF07 < SF08 < SF09 | no | +0.6 | 0.8 | 4 | 3 | no | SF10-SF12 |


Order is written low → high along the ridge (along ≈ paddock +y, toward row C).

Variants (secondary; the verdict above is the primary):

| variant | n_flashes | lofo_rms_in | first5 | exact_first5 | verdict | tie_first5 | verdict_tie | exact_all | tau_med_all | acc_hungarian | acc_offset | chance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| primary | 8 | 5.96 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 0 / 8 | +0.50 | 65% | 72% | 20% |
| proper | 8 | 5.96 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 0 / 8 | +0.50 | 65% | 72% | 20% |
| improper | 8 | 9.65 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 0 / 8 | +0.50 | 15% | 25% | 20% |
| prior_rotation | 8 | 5.90 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 0 / 8 | +0.50 | 65% | 68% | 20% |
| raw_fix_means | 8 | 5.85 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 3 | NOT ACCEPTED | 0 / 8 | +0.50 | 60% | 60% | 20% |
| no_lid_flag | 7 | 6.11 | 09-09 19:10:25, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42, 09-10 13:51:31 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 0 / 7 | +0.60 | 71% | 71% | 20% |
| alt_reading | 8 | 5.96 | 09-09 19:10:25, 09-10 07:14:15, 09-10 08:37:42, 09-10 09:11:47, 09-10 12:27:03 | 0 | NOT ACCEPTED | 3 | NOT ACCEPTED | 0 / 10 | +0.50 | 65% | 72% | 20% |
| centred_window | 10 | 5.24 | 09-09 19:10:25, 09-10 07:14:15, 09-10 08:37:42, 09-10 09:11:47, 09-10 12:27:03 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 1 / 10 | +0.50 | 76% | 70% | 20% |


- First 5 eligible flashes: 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42; exact matches: none.
- All 8 eligible flashes: exact 0 / 8; tie version 6 / 8 testable; Kendall τ +0.4, +0.4, +0.2, +0.8, +0.6, +0.4, +0.8, +0.6.
- Pairs ≥ 8 in apart along the ridge by WISER: 28 of 80 pairs; concordant 25 (89%).
- Not eligible: 09-10 08:37:42 (no WISER mean in [ON − 60 s, ON)); 09-10 15:23:07 (not revealed); 09-11 09:28:22 (no WISER mean in [ON − 60 s, ON))
- Alternative reading (a flash with ≥ 3 clicked animals but no WISER mean counts as a non-match: 09-10 08:37:42, 09-11 09:28:22): NOT ACCEPTED (0 of 5).

## 5. WISER as an identity aid: assigning the clicked heads by WISER

Hungarian assignment of the LOFO-mapped clicked heads to the WISER means (primary variant): **65%** of 40 clicks correct (greedy nearest 55%; with a free WISER offset per flash 72%; chance 20%).

By WISER separation of the clicked animal (2-D distance to the nearest other roster mean):

| bin_in | n_clicks | acc_hungarian | acc_greedy | acc_offset | chance |
|---|---|---|---|---|---|
| [0, 4) | 10 | 70% | 60% | 70% | 20% |
| [4, 8) | 20 | 60% | 45% | 75% | 20% |
| [8, 15) | 6 | 50% | 67% | 50% | 20% |
| >= 15 | 4 | 100% | 75% | 100% | 20% |


By along-ridge separation:

| bin_in | n_clicks | acc_hungarian | acc_greedy | acc_offset | chance |
|---|---|---|---|---|---|
| [0, 4) | 31 | 61% | 55% | 71% | 20% |
| [4, 8) | 4 | 75% | 25% | 75% | 20% |
| [8, 15) | 2 | 50% | 100% | 50% | 20% |
| >= 15 | 3 | 100% | 67% | 100% | 20% |


Per flash:

| segment_id | n | n_candidates | acc_hungarian | acc_greedy | acc_offset | swapped |
|---|---|---|---|---|---|---|
| CH07_20260909_191025 | 5 | 5 | 100% | 60% | 100% |  |
| CH07_20260910_071415 | 5 | 5 | 60% | 20% | 60% | SF07→SF12, SF12→SF07 |
| CH07_20260910_091147 | 5 | 5 | 20% | 60% | 20% | SF08→SF12, SF09→SF10, SF10→SF09, SF12→SF08 |
| CH07_20260910_122703 | 5 | 5 | 100% | 40% | 100% |  |
| CH07_20260910_125142 | 5 | 5 | 60% | 60% | 100% | SF07→SF10, SF10→SF07 |
| CH07_20260910_135131 | 5 | 5 | 100% | 80% | 100% |  |
| CH07_20260910_141613 | 5 | 5 | 20% | 40% | 40% | SF08→SF09, SF09→SF12, SF10→SF08, SF12→SF10 |
| CH07_20260910_143243 | 5 | 5 | 60% | 80% | 60% | SF10→SF12, SF12→SF10 |


- Of the 40 heads, 26 correct. Heads whose animal is ≥ 8 in from every other roster mean: 70% (n 10); < 8 in: 63% (n 30).
- Distance from a mapped head to its own animal's WISER mean: median 4.3 in, p90 8.6 in.
- Swaps (Hungarian) per flash: 09-10 07:14:15: SF07→SF12, SF12→SF07; 09-10 09:11:47: SF08→SF12, SF09→SF10, SF10→SF09, SF12→SF08; 09-10 12:51:42: SF07→SF10, SF10→SF07; 09-10 14:16:13: SF08→SF09, SF09→SF12, SF10→SF08, SF12→SF10; 09-10 14:32:43: SF10→SF12, SF12→SF10.
- Typical spacing inside a pile: the clicked animal's nearest other WISER mean is a median 5.7 in away (along the ridge 2.0 in), against a mapped-head-to-own-mean distance of median 4.3 in.

## What is not verified

- The clicks are a browser snapshot, not the user's export; 11 of 22 segments; one house (CH08 / house_1 has no clicks).
- The user's colour IDs are the reference; no second labeller; identities rest on the user's corrected key (SF09 black, SF10 blue).
- A 2-D similarity ignores perspective and head height: the camera sits in the lid ≈ 1 ft above the floor and piled heads lie at different heights, so one scale cannot hold everywhere; WISER is a 2-D solve (all z = 0) and cannot say who lies on top.
- WISER minute means come from the minute before ON; the colour frame is several seconds (long segments: minutes) later.
- Frames inside a lid-event window (`lid+ok`: 09-10 07:14, 09-11 09:28) use the lid segment's median correction; the camera may have been off it while the lid was open.
- The user's display orientation (180°) was chosen after several reveals — independent of the fit's numbers, not blind to WISER.
- Click-to-click repeatability on one head is unmeasured, so a colour → IR displacement mixes head movement and click placement.


## Definitions

Units: **reference px** = pixels of the lid-segment reference frame (09-04 12:00, user-labelled) of CH07, 2560 × 1920, origin
top-left; **inches** in the house frame of house_2. Symbols: $f$ indexes flashes (colour segments), $a$ animals, $k$ clicks.

**Click correction.** $(u'_k, v'_k)^\top = B_k\,(u_k, v_k, 1)^\top$, with $B_k$ the 2 × 3 `B_frame_to_ref` stored with the click
(frame px → reference px of its lid-closed segment; `cv/cv_field/frame_correction.py`). **Display coordinates**
$(p_k, q_k) = (u'_k, -v'_k)$: image right and image up as the page shows the frame.

**Blind record.** The clicks with `before_reveal` = true, `legacy` ≠ true and a `verdict_first`, read from `verdict_first` (the
values frozen when the user pressed "Save clicks & reveal WISER"). *After-reveal* clicks (`before_reveal` = false) and
*unsaved* clicks (in a segment not yet revealed when the browser state was taken) are listed but used by none of the fit, the
order test or the assignment. The *final* record = blind + after-reveal clicks with their live values, minus deleted ones.

**House frame.** For a paddock point $\mathbf x$ (in), $\text{along} = (\mathbf x - \mathbf c)\cdot(\cos\varphi, \sin\varphi)$,
$\text{across} = (\mathbf x - \mathbf c)\cdot(-\sin\varphi, \cos\varphi)$, house_2 centre $\mathbf c = (342.4, 117.7)$ in, ridge
$\varphi = 92.0°$ (`inbox_p0.to_house_frame`). Body 24.6 in along × 18.0 in across.

**WISER minute mean** $\mathbf W_{f,a} = (A_{f,a}, C_{f,a})$: mean over the animal's in-house default-track fixes in
$[t_{ON} - 60\,\mathrm s, t_{ON})$ mapped to the house frame — the value the page shows (`page_data.json`; reproduced here by the
page's own code). Raw-fix mean = the same over the raw fixes (sensitivity). *Centred window* = $[t_{mid} - 30\,\mathrm s,
t_{mid} + 30\,\mathrm s)$ around the colour frame (sensitivity).

**Similarity fit (Q3).** With $z_k = p_k + i\,\sigma q_k$ ($\sigma = +1$ proper, $-1$ improper = mirrored display) and
$w_k = A_k + i\,C_k$ the WISER mean of the clicked animal,
$$\hat\alpha = \frac{\sum_k \overline{(z_k - \bar z)}\,(w_k - \bar w)}{\sum_k |z_k - \bar z|^2},\qquad \hat\tau = \bar w - \hat\alpha\,\bar z,\qquad \hat w(z) = \hat\alpha z + \hat\tau ,$$
the least-squares 2-D similarity (scale $s = |\hat\alpha|$ in/px, i.e. $1/s$ px/in; rotation $\theta_{house} = \arg\hat\alpha$,
counter-clockwise, display → house frame). Rotation in the paddock: $\theta_{pad} = \theta_{house} + \varphi$. **Page-equivalent
orientation** (the page draws view $= R(\text{rot})\,M_x\,(dx, dy)$, $M_x$ = x-flip if mirrored): proper
$\text{rot} = -\theta_{pad}$, improper $\text{rot} = \theta_{pad} - 180°$ (mod 360). The user's display orientation for house_2
(rot 180°, no mirror) corresponds to $\theta_{pad} = 180°$, $\theta_{house} = 88°$. **Fixed-rotation (prior) map**: $\arg\hat\alpha$
held at the prior, $|\hat\alpha| = \max(0, \mathrm{Re}\sum \overline{e^{i\theta_0}(z_k - \bar z)}(w_k - \bar w)) / \sum|z_k - \bar z|^2$.
**Image centre in the house frame** $= \hat w(1280 - 960 i)$ (proper fit): where the reference image centre lands in WISER's
house frame; it equals the WISER bias only if the camera axis meets the house centre (not known).

**Leave-one-flash-out (LOFO).** For flash $f$, fit on all clicks of the other flashes, then
$e^{in}_{f,a} = |\hat w_{-f}(z_{f,a}) - w_{f,a}|$ (inches; the clicked head mapped into the house frame vs WISER) and
$e^{px}_{f,a} = |\hat w_{-f}^{-1}(w_{f,a}) - z_{f,a}|$ (reference px; WISER mapped into the image vs the click). RMS = $\sqrt{\text{mean}\,e^2}$.
The handedness with the lower LOFO RMS (inches) is used downstream.

**Residual decomposition.** $\mathbf r_{f,a} = \hat w_{-f}(z_{f,a}) - w_{f,a}$ (in). *Flash offset* $\bar{\mathbf r}_f$ = mean over the
flash's animals; RMS after it = $\sqrt{\text{mean}\,|\mathbf r_{f,a} - \bar{\mathbf r}_f|^2}$ (in-sample). *Animal offset (LOO)*
$\bar{\mathbf r}_{-f,a}$ = mean of the animal's residuals in the other flashes; RMS after it = $\sqrt{\text{mean}\,|\mathbf r_{f,a} - \bar{\mathbf r}_{-f,a}|^2}$.
A drop marks a bias that a per-flash or per-tag correction could remove.

**Order test (Q4; the operator's rule).** Eligible flash: ≥ 3 animals with a blind named colour click and a WISER mean. WISER
order = animals sorted by $A_{f,a}$; click order = sorted by $\hat A_{f,a} = \mathrm{Re}\,\hat w_{-f}(z_{f,a})$. *Exact match* =
identical permutations. **ACCEPTED** if exact in ≥ 4 of the first 5 eligible flashes in time order. *Kendall*
$\tau_a = \frac{\sum_{a<b} \mathrm{sgn}(A_a - A_b)\,\mathrm{sgn}(\hat A_a - \hat A_b)}{n(n-1)/2}$ (range −1 … 1; 1 = same order).
*Tie version*: only pairs with $|A_a - A_b| \ge 8$ in are tested (the plan: 1-min-mean separations < 8 in are candidates); a
flash matches if every tested pair is concordant ($\mathrm{sgn}$ equal); a flash without a tested pair is "no testable pair".
*Alternative reading*: a flash with ≥ 3 clicked animals but no WISER mean in the window counts as a non-match.

**Assignment (Q5).** Per flash, heads $h$ = blind named colour clicks mapped by $\hat w_{-f}$; candidates = roster animals with a
WISER mean. *Hungarian*: the one-to-one assignment $\pi$ minimising $\sum_h |\hat w_{-f}(z_h) - w_{\pi(h)}|$ (scipy
`linear_sum_assignment`). *Greedy*: each head to its nearest mean (repeats allowed). *Per-flash offset*: the injection minimising
$\sum_h |d_h - \bar d|^2$, $d_h = w_{\pi(h)} - \hat w_{-f}(z_h)$ (a free WISER offset per flash). Accuracy = share of heads with
$\pi(h)$ = the user's colour ID. *Chance* = $1/n_{cand}$ per head (expected accuracy of a uniformly random assignment).
*WISER separation* of a click = $\min_{b \ne a} |w_{f,a} - w_{f,b}|$ over the other roster means (2-D, in); *along separation*
= $\min_{b\ne a} |A_{f,a} - A_{f,b}|$.

**Colour → IR displacement (Q2).** For animal $a$ named once on the colour frame and once on an IR frame of the same
segment: $d = |(u'_{IR}, v'_{IR}) - (u'_{col}, v'_{col})|$ (reference px; frame px reported too; within a segment both frames
share $B$, so the two agree), $d_{in} = d / (1/s)$ at the proper fit's scale (a single scale for a camera ~ 1 ft above heads at
different heights: indicative), $\Delta t = t_{IR} - t_{col}$. **Head-IMU state between** (`imu_seconds_cache`, field-PC
seconds $\lfloor t_{col}\rfloor … \lfloor t_{IR}\rfloor$): *all still* = every second IMU-ok and still; *moved* = ≥ 1 IMU-ok
second active or locomoting; *still (partial)* = some seconds not ok, the ok ones still; *no IMU* = no ok second
(handling windows ± 5 min are not ok by construction).

## Files

Run folder `D:/Field2026_analysis_out/2026c/cv_field_inbox_clicks_20261010_2042`: `clicks_table.csv` (every click, both records, B-corrected), `composition.csv`, `stability_blind.csv`, `stability_final.csv`, `stability_counts.csv`, `fit_summary.csv`, `fit_points_<variant>.csv` (LOFO predictions per click), `order_<variant>.csv`, `assignment_<variant>.csv`, `variants.csv`, `residual_per_animal.csv`, `wiser_centred_window.json`, `wiser_reproduction_check.csv`, `run.json`; figures `figures/flash_overlays_primary.png`, `figures/colour_ir_displacement.png`, `figures/assignment_vs_separation.png`. Pointer `results/2026c/cv_field/reports/run_manifest_inbox_clicks_2026c.json`.
