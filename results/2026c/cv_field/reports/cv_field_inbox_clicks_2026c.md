# In-box camera CH07 (house_2): the user's identity clicks — composition, colour → IR stability, camera ↔ WISER fit, the pre-registered order test, WISER as an identity aid (cohort `2026c`)

**Data = the user's formal CSV export** `cv/configs/inbox_identity_2026c/inbox_identity_2026c_20261010_220725.csv` (sha256 `3233d7b40db88694…`; the newest of the user's exports in `cv/configs/inbox_identity_2026c/`), 20 / 22 segments clicked, with the user's composition statement (`composition_statement_user_2026-10-11.json`). This supersedes the preliminary run on the browser snapshot of 2026-10-10 20:17 (its results: the comparison table below and the section "Superseded preliminary run").

Plan `implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md` (section "Pre-registered use of the user's clicks" + amendments 1–12; amendment 11 = how this step is run, written before any result). Run `D:/Field2026_analysis_out/2026c/cv_field_inbox_clicks_20261010_2227`; generated 2026-10-10T22:27:47; code `0e665e9eca3f80feac06ca640a67c4140567f2d2+dirty`. Phase-0 run `D:/Field2026_analysis_out/2026c/cv_field_inbox_p0_20261010_1702`. Driver `cv/cv_field/inbox_click_analysis.py`. The agent never looked at a frame; everything is computed from the click coordinates, the user's IDs and WISER.

**Correction 2026-10-11 (plan amendment 12, carried over).** SF11 kept its tag and left the paddock at the 09-07 AM round (last fix 08:20); from then to 09-11 19:40 the paddock held five animals, all tagged, so rosters are complete except in tag dropouts. No number here depends on the earlier, wrong reading.

## Summary

- **Data** (CSV export): 294 clicks (284 blind, 10 after the reveal, 0 unsaved, 0 legacy) in 20 of 22 segments, all CH07 / house_2.
- **1. Composition**: colour-frame set = WISER roster in 17 of 20 revealed segments; SF11 never clicked; 2 unknown clicks.
- **2. Colour → IR**: where the IR frame is < 30 s after the colour frame the clicked heads moved median 27 px (≈ 0.4 in), max 643 px; 12 of 140 pairs > 100 px.
- **3. Fit**: proper handedness; 74.8 px/in; page-equivalent rotation 174° vs the user's 180° (Δ -5.7°); LOFO RMS 5.45 in / 406 px.
- **4. Pre-registered order test: NOT ACCEPTED** (0 of 5 exact; needs 4); tie version NOT ACCEPTED (3 of 5); Kendall τ median +0.20.
- **5. WISER as an identity aid**: Hungarian assignment 64% correct (chance 20%); [0, 4) in: 57% (n 21), [4, 8) in: 61% (n 46), [8, 15) in: 69% (n 16), >= 15 in: 100% (n 6).

## Export vs the superseded snapshot run

| metric | snapshot (10-10 20:17, superseded) | export (primary) |
|---|---|---|
| clicks (blind / after reveal / unsaved / legacy) | 141 (135 / 5 / 1 / 0) | 294 (284 / 10 / 0 / 0) |
| segments clicked / revealed | 11 / 10 | 20 / 20 |
| 1. colour set = WISER roster | 8 of 10 | 17 of 20 |
| 2. colour → IR < 30 s: pairs, median / max px | 60, 27 / 387 | 140, 27 / 643 |
| 2. IMU all still: n, max px | 36, 44 | 64, 54 |
| 2. IMU moved: n, max px | 24, 387 | 30, 387 |
| 3. fit points / flashes | 40 / 8 | 89 / 18 |
| 3. handedness; px/in | proper; 79.3 | proper; 74.8 |
| 3. page rotation (Δ vs the user's 180°) | 178.2° (-1.8°) | 174.3° (-5.7°) |
| 3. LOFO RMS in / px | 5.96 / 470 | 5.45 / 406 |
| 4. first 5 flashes | 09-09 19:10, 09-10 07:14, 09-10 09:11, 09-10 12:27, 09-10 12:51 | 09-09 19:10, 09-10 07:14, 09-10 09:11, 09-10 12:27, 09-10 12:51 |
| 4. exact order, first 5 (verdict) | 0 of 5 (NOT ACCEPTED) | 0 of 5 (NOT ACCEPTED) |
| 4. tie version, first 5 (verdict) | 4 of 5 (ACCEPTED) | 3 of 5 (NOT ACCEPTED) |
| 4. Kendall τ median first 5 / all | +0.40 / +0.50 | +0.20 / +0.20 |
| 4. exact order, all eligible flashes | 0 of 8 | 1 of 18 |
| 4. pairs ≥ 8 in concordant | 25 of 28 | 46 of 52 |
| 5. Hungarian accuracy (chance) | 65% of 40 (20%) | 64% of 89 (20%) |
| 5. per-flash-offset accuracy | 72% | 65% |
| 5. heads ≥ 15 in apart correct | 4 of 4 | 6 of 6 |


**Blind record, snapshot vs export (by `click_id`):** 140 clicks identical (animal, position, frame, status, B), 1 changed, 153 only in the export, 0 only in the snapshot.
- changed: `kmv32qnna2i1ahp` 09-10 15:23:07 colour_mid: status unsaved → blind; animal unknown → SF10; b_animal None → SF10; b_frame_kind None → colour_mid; b_u nan → 1173.2; b_v nan → 1596.4
- only in the export: 09-10 14:02 (15), 09-10 14:16 (5), 09-10 15:23 (14), 09-10 16:30 (15), 09-10 17:59 (15), 09-11 09:54 (14), 09-11 14:09 (15), 09-11 14:17 (15), 09-11 14:43 (15), 09-11 14:50 (15), 09-11 18:28 (15).

**Order test, the first 5 flashes** (the same five in both runs): inputs (blind colour clicks after B, WISER minute means) identical in **5 of 5** — no blind click of these flashes differs. The mapping differs: each flash is now mapped by a fit on the other 17 flashes instead of 7.

| segment_id | inputs_identical | order_wiser | snapshot_clicks_order | snapshot_exact | snapshot_tau | snapshot_tie | export_clicks_order | export_exact | export_tau | export_tie |
|---|---|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | yes | SF08 < SF07 < SF10 < SF12 < SF09 | SF08 < SF09 < SF07 < SF10 < SF12 | no | +0.4 | yes | SF08 < SF09 < SF10 < SF07 < SF12 | no | +0.2 | yes |
| CH07_20260910_071415 | yes | SF12 < SF10 < SF07 < SF09 < SF08 | SF07 < SF10 < SF12 < SF09 < SF08 | no | +0.4 | yes | SF07 < SF10 < SF09 < SF08 < SF12 | no | +0.0 | no |
| CH07_20260910_091147 | yes | SF09 < SF12 < SF08 < SF10 < SF07 | SF08 < SF12 < SF10 < SF09 < SF07 | no | +0.2 | no | SF08 < SF12 < SF10 < SF09 < SF07 | no | +0.2 | no |
| CH07_20260910_122703 | yes | SF08 < SF07 < SF12 < SF10 < SF09 | SF08 < SF12 < SF07 < SF10 < SF09 | no | +0.8 | yes | SF08 < SF12 < SF07 < SF10 < SF09 | no | +0.8 | yes |
| CH07_20260910_125142 | yes | SF08 < SF12 < SF07 < SF09 < SF10 | SF08 < SF07 < SF12 < SF10 < SF09 | no | +0.6 | yes | SF08 < SF07 < SF12 < SF10 < SF09 | no | +0.6 | yes |


## The question: what do the colour labels tell us, and can WISER serve as an identity-label aid?

From the user export, 18 flashes in the fit; every statement is a number from the sections below.

- **Which animals are in the box — yes, WISER helps.** The house roster equalled the colour-clicked set in 17 of 20 revealed flashes. No clicked animal was ever missing from a roster (0 extras); the 4 roster animals not clicked (09-10 08:37 SF08, 09-10 08:37 SF09, 09-11 09:28 SF10, 09-11 09:54 SF12) were, by WISER at the colour frame, 3 outside the house body (5.1–8.8 in beyond it, inside the 15-in dilated zone) and 1 inside it. With the user's statement (fewer clicks = animals outside the house) these are WISER over-inclusions by the dilated zone / dwell rule; the colour frame of 09-10 08:37 also carries an unknown click, which could be one of its 'missing' animals. Context: 09-10 08:37: AM placement; lid event 2026-09-10 07:17-08:40 AM round + SF12 probe advance, 1077-s colour segment; 09-11 09:28: lid event 2026-09-11 08:04-09:48 AM round, 242-s colour segment; 09-11 09:54: colour segment ~10:00, 413-s colour segment. Rosters are complete here: all five animals in the paddock were tagged (SF11 had left at the 09-07 AM round; plan amendment 12); SF11 was never clicked.
- **Who lies where inside a pile — not from WISER minute means.** The pre-registered order test is NOT ACCEPTED (exact order 0 of 5, 1 of 18 overall; Kendall τ median +0.20); mapped heads sit 5.5 in RMS from their own WISER mean while pile neighbours are a median 5.5 in apart, and neither a per-flash nor a per-tag offset removes that error. Assigning heads by WISER gets 64% right (chance 20%).
- **Where WISER separations can be trusted.** Pairs ≥ 8 in apart along the ridge were ordered correctly in 46 of 52 (88%; tie version NOT ACCEPTED); heads ≥ 15 in from every other animal were assigned correctly in 6 of 6. So WISER can name an animal lying apart at one end of the box and order clearly separated animals; it cannot resolve the order inside the pile (the plan's rule "trust > 8 in for 1-min means only" stands).
- **The colour labels and the IR frames.** When the head IMU was still on every second between the colour and the IR frame, the clicked head moved ≤ 54 px (median 21 px ≈ 0.3 in; n 64), consistent with the operator's premise that IR frames can inherit identity from the colour frame; when the IMU registered movement the displacement reached 387 px (median 46 px, n 30). The head IMU is a candidate gate for carrying colour identities into IR (click repeatability on one head is not measured).
- **Camera geometry, as a by-product.** The blind clicks alone recover the CH07 ↔ house orientation: 174°, not mirrored, vs the user's display choice of 180° made by eye before any fit (Δ -5.7°); scale 75 px/in; the image centre lands 4.6 in from the WISER house centre.

## Which clicks were used

| status | colour_mid | ir_p06 | ir_p15 | total | named | unknown |
|---|---|---|---|---|---|---|
| after_reveal | 0 | 0 | 10 | 10 | 10 | 0 |
| blind | 96 | 99 | 89 | 284 | 282 | 2 |


SF09 / SF10 one-time swap (amendment 10): applied to 6 clicks (all of segment 09-09 19:10, before the fix; `undone_at` = None); `animal` already carries it. No click is legacy; no blind click was edited or deleted after its reveal (edited 0, deleted 0); the blind record and the live values agree on all 284 blind clicks (max |Δ| 0.00 px, 0 label differences). Orientation: snapshot `orientation_by_house.house_2` = rot 180°, mirror False; `cv/configs/inbox_camera_orientation_2026c.json` = rot 180°, mirror False; chosen 2026-10-11T00:11:10.183Z UTC, after 5 segments had been revealed (so the user had seen WISER top views; the orientation used no fitted number).

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
| CH07_20260910_140227 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_141613 | yes | 15 | 10 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_143243 | yes | 15 | 10 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_152307 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_163056 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260910_175935 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260911_092822 | yes | 11 | 11 | SF07,SF08,SF09,SF10 | SF12 | SF07,SF08,SF09 | 0 | SF10 |  | no | SF07,SF08,SF09,SF10 |  | SF07,SF08,SF09,SF10 |
| CH07_20260911_095409 | yes | 14 | 14 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10 | 0 | SF12 |  | no | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260911_140955 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260911_141758 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260911_144345 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260911_145024 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |
| CH07_20260911_182803 | yes | 15 | 15 | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 | 0 |  |  | yes | SF07,SF08,SF09,SF10,SF12 |  | SF07,SF08,SF09,SF10,SF12 |


- 20 segments carry clicks, 20 of them revealed.
- **The user's composition statement** (`composition_statement_user_2026-10-11.json`): every clicked colour frame is complete — every rat in the house was identified; fewer clicks = animals outside the house at that frame (not hidden, not unidentified); unusable: 09-10 19:50:04 (colour-shift transition, frame all black (the PM placement attempt the colour log calls too dark)), no click. The colour-frame set is therefore the in-house set, and the comparison below scores the WISER roster.
- Roster source (page code): the cleaned per-second house state **at the colour frame** (dilated rectangle + 15 in, 6-s smoothing, 20-s minimum dwell); only the WISER *positions* use the minute before ON.
- Colour-frame set = WISER roster in **17 of 20** revealed segments (09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42, 09-10 13:51:31, 09-10 14:02:27, 09-10 14:16:13, 09-10 14:32:43, 09-10 15:23:07, 09-10 16:30:56, 09-10 17:59:35, 09-11 14:09:55, 09-11 14:17:58, 09-11 14:43:45, 09-11 14:50:24, 09-11 18:28:03).
- 09-10 08:37:42: roster SF07,SF08,SF09,SF10,SF12; colour frame SF07,SF10,SF12 + 1 unknown → missing SF08,SF09, extras -; on any frame (blind) SF07,SF08,SF09,SF10,SF12 (missing -). WISER ±5 s around the colour frame: SF08: state house_2, along +10.6 / across +4.6 in, inside the body; SF09: state house_2, along -0.9 / across +14.1 in, 5.1 in outside the body.
- 09-11 09:28:22: roster SF07,SF08,SF09,SF10 (untracked SF12); colour frame SF07,SF08,SF09 + 0 unknown → missing SF10, extras -; on any frame (blind) SF07,SF08,SF09,SF10 (missing -). WISER ±5 s around the colour frame: SF10: state house_2, along -1.6 / across +17.7 in, 8.7 in outside the body.
- 09-11 09:54:09: roster SF07,SF08,SF09,SF10,SF12; colour frame SF07,SF08,SF09,SF10 + 0 unknown → missing SF12, extras -; on any frame (blind) SF07,SF08,SF09,SF10,SF12 (missing -). WISER ±5 s around the colour frame: SF12: state house_2, along -1.8 / across +17.8 in, 8.8 in outside the body.
- A stricter roster (in the house state *and* WISER mean ±5 s inside the 24.6 × 18 in body footprint at the colour frame) matches in only 2 of 20: WISER places animals that are in the house outside the body footprint often, so the 15-in dilation is needed and also admits animals just outside.
- Unknown (`None`) clicks: 2 in all (09-10 08:37:42 colour_mid, 09-10 08:37:42 ir_p15). Extras (a clicked animal outside the roster): 0 segments. SF11 was clicked **never** (it left the paddock at the 09-07 AM round, last fix 08:20, so it cannot be in a pile here; corrected 2026-10-11, plan amendment 12).

## 2. Stability colour → IR (the premise that a pile does not move across the switch)

| segment_id | ir_frame | dt_s | n_colour | n_ir | n_both | colour_not_ir | ir_not_colour | median_px | max_px | median_in | max_in | imu |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | ir_p06 | 12.7 | 5 | 5 | 5 |  |  | 47 | 111 | 0.6 | 1.5 | moved 5 |
| CH07_20260909_191025 | ir_p15 | 21.8 | 5 | 5 | 5 |  |  | 57 | 164 | 0.8 | 2.2 | moved 5 |
| CH07_20260910_071415 | ir_p06 | 37.0 | 5 | 5 | 5 |  |  | 19 | 38 | 0.3 | 0.5 | no IMU 5 |
| CH07_20260910_071415 | ir_p15 | 46.1 | 5 | 5 | 5 |  |  | 15 | 30 | 0.2 | 0.4 | no IMU 5 |
| CH07_20260910_083742 | ir_p06 | 544.4 | 3 | 5 | 3 |  | SF08,SF09 | 956 | 1444 | 12.8 | 19.3 | moved 3 |
| CH07_20260910_083742 | ir_p15 | 553.5 | 3 | 4 | 3 |  | SF09 | 939 | 1461 | 12.6 | 19.5 | moved 3 |
| CH07_20260910_091147 | ir_p06 | 16.1 | 5 | 5 | 5 |  |  | 15 | 26 | 0.2 | 0.3 | all still 5 |
| CH07_20260910_091147 | ir_p15 | 25.1 | 5 | 5 | 5 |  |  | 17 | 28 | 0.2 | 0.4 | all still 5 |
| CH07_20260910_122703 | ir_p06 | 17.5 | 5 | 5 | 5 |  |  | 24 | 31 | 0.3 | 0.4 | all still 5 |
| CH07_20260910_122703 | ir_p15 | 26.5 | 5 | 5 | 5 |  |  | 18 | 35 | 0.2 | 0.5 | all still 4, moved 1 |
| CH07_20260910_125142 | ir_p06 | 12.5 | 5 | 5 | 5 |  |  | 43 | 294 | 0.6 | 3.9 | moved 4, all still 1 |
| CH07_20260910_125142 | ir_p15 | 21.5 | 5 | 5 | 5 |  |  | 43 | 108 | 0.6 | 1.4 | moved 4, all still 1 |
| CH07_20260910_135131 | ir_p06 | 16.7 | 5 | 5 | 5 |  |  | 21 | 44 | 0.3 | 0.6 | all still 5 |
| CH07_20260910_135131 | ir_p15 | 25.7 | 5 | 5 | 5 |  |  | 26 | 38 | 0.4 | 0.5 | all still 5 |
| CH07_20260910_140227 | ir_p06 | 11.8 | 5 | 5 | 5 |  |  | 17 | 39 | 0.2 | 0.5 | all still 5 |
| CH07_20260910_140227 | ir_p15 | 20.8 | 5 | 5 | 5 |  |  | 19 | 53 | 0.2 | 0.7 | all still 5 |
| CH07_20260910_141613 | ir_p06 | 17.0 | 5 | 5 | 5 |  |  | 41 | 387 | 0.5 | 5.2 | moved 3, all still 2 |
| CH07_20260910_141613 | ir_p15 | - | 5 | 0 | 0 | SF07,SF08,SF09,SF10,SF12 |  | - | - | - | - | - |
| CH07_20260910_143243 | ir_p06 | 10.8 | 5 | 5 | 5 |  |  | 35 | 91 | 0.5 | 1.2 | all still 3, moved 2 |
| CH07_20260910_143243 | ir_p15 | - | 5 | 0 | 0 | SF07,SF08,SF09,SF10,SF12 |  | - | - | - | - | - |
| CH07_20260910_152307 | ir_p06 | 12.3 | 5 | 5 | 5 |  |  | 37 | 612 | 0.5 | 8.2 | no IMU 5 |
| CH07_20260910_152307 | ir_p15 | 21.3 | 5 | 5 | 5 |  |  | 36 | 643 | 0.5 | 8.6 | no IMU 5 |
| CH07_20260910_163056 | ir_p06 | 14.0 | 5 | 5 | 5 |  |  | 30 | 39 | 0.4 | 0.5 | no IMU 5 |
| CH07_20260910_163056 | ir_p15 | 23.0 | 5 | 5 | 5 |  |  | 21 | 25 | 0.3 | 0.3 | no IMU 5 |
| CH07_20260910_175935 | ir_p06 | 9.3 | 5 | 5 | 5 |  |  | 26 | 55 | 0.4 | 0.7 | no IMU 5 |
| CH07_20260910_175935 | ir_p15 | 18.4 | 5 | 5 | 5 |  |  | 46 | 52 | 0.6 | 0.7 | no IMU 5 |
| CH07_20260911_092822 | ir_p06 | 126.9 | 3 | 4 | 3 |  | SF10 | 1030 | 1335 | 13.8 | 17.9 | no IMU 3 |
| CH07_20260911_092822 | ir_p15 | 135.8 | 3 | 4 | 3 |  | SF10 | 1004 | 1251 | 13.4 | 16.7 | no IMU 3 |
| CH07_20260911_095409 | ir_p06 | 212.7 | 4 | 4 | 3 | SF09 | SF12 | 45 | 53 | 0.6 | 0.7 | moved 2 |
| CH07_20260911_095409 | ir_p15 | 221.7 | 4 | 4 | 3 | SF08 | SF12 | 107 | 179 | 1.4 | 2.4 | moved 2 |
| CH07_20260911_140955 | ir_p06 | 19.8 | 5 | 5 | 5 |  |  | 20 | 50 | 0.3 | 0.7 | all still 4, no IMU 1 |
| CH07_20260911_140955 | ir_p15 | 28.8 | 5 | 5 | 5 |  |  | 25 | 41 | 0.3 | 0.5 | all still 4, no IMU 1 |
| CH07_20260911_141758 | ir_p06 | 31.0 | 5 | 5 | 5 |  |  | 11 | 21 | 0.1 | 0.3 | all still 4, no IMU 1 |
| CH07_20260911_141758 | ir_p15 | 40.0 | 5 | 5 | 5 |  |  | 15 | 18 | 0.2 | 0.2 | all still 4, no IMU 1 |
| CH07_20260911_144345 | ir_p06 | 11.5 | 5 | 5 | 5 |  |  | 20 | 54 | 0.3 | 0.7 | all still 3, moved 1, no IMU 1 |
| CH07_20260911_144345 | ir_p15 | 20.5 | 5 | 5 | 5 |  |  | 19 | 48 | 0.3 | 0.6 | all still 3, moved 1, no IMU 1 |
| CH07_20260911_145024 | ir_p06 | 11.1 | 5 | 5 | 5 |  |  | 31 | 46 | 0.4 | 0.6 | moved 2, all still 2, no IMU 1 |
| CH07_20260911_145024 | ir_p15 | 20.1 | 5 | 5 | 5 |  |  | 42 | 113 | 0.6 | 1.5 | moved 2, all still 2, no IMU 1 |
| CH07_20260911_182803 | ir_p06 | 19.8 | 5 | 5 | 5 |  |  | 42 | 342 | 0.6 | 4.6 | no IMU 5 |
| CH07_20260911_182803 | ir_p15 | 28.7 | 5 | 5 | 5 |  |  | 46 | 70 | 0.6 | 0.9 | no IMU 5 |


- Segments whose IR frame is < 30 s after the colour frame (15 segments, 140 animal × IR-frame pairs): displacement median **27 px** (≈ 0.4 in at the fitted 75 px/in), p75 44 px, max 643 px; ≤ 40 px in 97 of 140, > 100 px in 12 (09-09 19:10:25 SF07 ir_p06 111, 09-09 19:10:25 SF07 ir_p15 164, 09-10 12:51:42 SF12 ir_p06 294, 09-10 12:51:42 SF07 ir_p15 108, 09-10 14:16:13 SF07 ir_p06 336, 09-10 14:16:13 SF08 ir_p06 387, 09-10 15:23:07 SF09 ir_p06 164, 09-10 15:23:07 SF10 ir_p06 612, 09-10 15:23:07 SF09 ir_p15 114, 09-10 15:23:07 SF10 ir_p15 643, 09-11 14:50:24 SF07 ir_p15 113, 09-11 18:28:03 SF09 ir_p06 342).
- Long colour segments (the colour frame is the segment middle, so the IR frames come 09-10 07:14:15 37 s, 09-10 08:37:42 544 s, 09-11 09:28:22 127 s, 09-11 09:54:09 213 s, 09-11 14:17:58 31 s later): median 28 px, max 1461 px — not "seconds around the switch"; these do not test the premise.
- Head IMU between the two frames (short segments): all still: n 64, median 21 px, max 54 px; moved: n 30, median 46 px, max 387 px; no IMU: n 46, median 30 px, max 643 px.
- Animals named on the colour frame but not clicked on the IR frame (blind record): 12 of 190 colour × IR-frame slots (09-10 14:16:13 ir_p15: SF07,SF08,SF09,SF10,SF12; 09-10 14:32:43 ir_p15: SF07,SF08,SF09,SF10,SF12; 09-11 09:54:09 ir_p06: SF09; 09-11 09:54:09 ir_p15: SF08); named on IR but not on colour: 09-10 08:37:42 ir_p06: SF08,SF09; 09-10 08:37:42 ir_p15: SF09; 09-11 09:28:22 ir_p06: SF10; 09-11 09:28:22 ir_p15: SF10; 09-11 09:54:09 ir_p06: SF12; 09-11 09:54:09 ir_p15: SF12.
- One label on two heads of one IR frame (excluded from the displacement): 09-11 09:54:09 ir_p06: SF10x2 (blind); 09-11 09:54:09 ir_p15: SF07x2 (blind); 09-10 14:32:43 ir_p15: SF08x2 (after the reveal).

Per animal (blind record):

| segment_id | ir_frame | animal | dt_s | d_px | d_in | imu_n_s | imu_n_ok | imu_n_still | imu_n_active | imu_n_loco | imu_class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | ir_p06 | SF07 | 12.7 | 111 | 1.5 | 14 | 14 | 0 | 12 | 2 | moved |
| CH07_20260909_191025 | ir_p06 | SF08 | 12.7 | 35 | 0.5 | 14 | 14 | 0 | 14 | 0 | moved |
| CH07_20260909_191025 | ir_p06 | SF09 | 12.7 | 47 | 0.6 | 14 | 14 | 8 | 6 | 0 | moved |
| CH07_20260909_191025 | ir_p06 | SF10 | 12.7 | 74 | 1.0 | 14 | 14 | 13 | 1 | 0 | moved |
| CH07_20260909_191025 | ir_p06 | SF12 | 12.7 | 46 | 0.6 | 14 | 14 | 5 | 9 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF07 | 21.8 | 164 | 2.2 | 23 | 23 | 0 | 21 | 2 | moved |
| CH07_20260909_191025 | ir_p15 | SF08 | 21.8 | 25 | 0.3 | 23 | 23 | 0 | 23 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF09 | 21.8 | 78 | 1.0 | 23 | 23 | 14 | 9 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF10 | 21.8 | 46 | 0.6 | 23 | 23 | 22 | 1 | 0 | moved |
| CH07_20260909_191025 | ir_p15 | SF12 | 21.8 | 57 | 0.8 | 23 | 23 | 11 | 12 | 0 | moved |
| CH07_20260910_071415 | ir_p06 | SF07 | 37.0 | 6 | 0.1 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF08 | 37.0 | 16 | 0.2 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF09 | 37.0 | 26 | 0.3 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF10 | 37.0 | 19 | 0.3 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p06 | SF12 | 37.0 | 38 | 0.5 | 38 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF07 | 46.1 | 15 | 0.2 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF08 | 46.1 | 14 | 0.2 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF09 | 46.1 | 26 | 0.3 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF10 | 46.1 | 12 | 0.2 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_071415 | ir_p15 | SF12 | 46.1 | 30 | 0.4 | 47 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_083742 | ir_p06 | SF07 | 544.4 | 1444 | 19.3 | 545 | 545 | 117 | 406 | 22 | moved |
| CH07_20260910_083742 | ir_p06 | SF10 | 544.4 | 956 | 12.8 | 545 | 541 | 201 | 291 | 49 | moved |
| CH07_20260910_083742 | ir_p06 | SF12 | 544.4 | 222 | 3.0 | 545 | 545 | 319 | 196 | 30 | moved |
| CH07_20260910_083742 | ir_p15 | SF07 | 553.5 | 1461 | 19.5 | 554 | 554 | 125 | 407 | 22 | moved |
| CH07_20260910_083742 | ir_p15 | SF10 | 553.5 | 939 | 12.6 | 554 | 550 | 210 | 291 | 49 | moved |
| CH07_20260910_083742 | ir_p15 | SF12 | 553.5 | 191 | 2.6 | 554 | 554 | 319 | 205 | 30 | moved |
| CH07_20260910_091147 | ir_p06 | SF07 | 16.1 | 10 | 0.1 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF08 | 16.1 | 20 | 0.3 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF09 | 16.1 | 15 | 0.2 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF10 | 16.1 | 26 | 0.3 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p06 | SF12 | 16.1 | 13 | 0.2 | 17 | 17 | 17 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF07 | 25.1 | 26 | 0.4 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF08 | 25.1 | 28 | 0.4 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF09 | 25.1 | 7 | 0.1 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF10 | 25.1 | 17 | 0.2 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_091147 | ir_p15 | SF12 | 25.1 | 3 | 0.0 | 26 | 26 | 26 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF07 | 17.5 | 27 | 0.4 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF08 | 17.5 | 31 | 0.4 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF09 | 17.5 | 17 | 0.2 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF10 | 17.5 | 15 | 0.2 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p06 | SF12 | 17.5 | 24 | 0.3 | 19 | 19 | 19 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF07 | 26.5 | 12 | 0.2 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF08 | 26.5 | 18 | 0.2 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF09 | 26.5 | 20 | 0.3 | 28 | 28 | 26 | 2 | 0 | moved |
| CH07_20260910_122703 | ir_p15 | SF10 | 26.5 | 12 | 0.2 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_122703 | ir_p15 | SF12 | 26.5 | 35 | 0.5 | 28 | 28 | 28 | 0 | 0 | all still |
| CH07_20260910_125142 | ir_p06 | SF07 | 12.5 | 61 | 0.8 | 13 | 13 | 3 | 10 | 0 | moved |
| CH07_20260910_125142 | ir_p06 | SF08 | 12.5 | 15 | 0.2 | 13 | 13 | 13 | 0 | 0 | all still |
| CH07_20260910_125142 | ir_p06 | SF09 | 12.5 | 12 | 0.2 | 13 | 13 | 3 | 10 | 0 | moved |
| CH07_20260910_125142 | ir_p06 | SF10 | 12.5 | 43 | 0.6 | 13 | 13 | 0 | 13 | 0 | moved |
| CH07_20260910_125142 | ir_p06 | SF12 | 12.5 | 294 | 3.9 | 13 | 13 | 0 | 8 | 5 | moved |
| CH07_20260910_125142 | ir_p15 | SF07 | 21.5 | 108 | 1.4 | 22 | 22 | 3 | 14 | 5 | moved |
| CH07_20260910_125142 | ir_p15 | SF08 | 21.5 | 18 | 0.2 | 22 | 22 | 22 | 0 | 0 | all still |
| CH07_20260910_125142 | ir_p15 | SF09 | 21.5 | 43 | 0.6 | 22 | 22 | 12 | 10 | 0 | moved |
| CH07_20260910_125142 | ir_p15 | SF10 | 21.5 | 99 | 1.3 | 22 | 22 | 0 | 20 | 2 | moved |
| CH07_20260910_125142 | ir_p15 | SF12 | 21.5 | 22 | 0.3 | 22 | 22 | 1 | 16 | 5 | moved |
| CH07_20260910_135131 | ir_p06 | SF07 | 16.7 | 16 | 0.2 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF08 | 16.7 | 21 | 0.3 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF09 | 16.7 | 29 | 0.4 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF10 | 16.7 | 12 | 0.2 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p06 | SF12 | 16.7 | 44 | 0.6 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF07 | 25.7 | 21 | 0.3 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF08 | 25.7 | 36 | 0.5 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF09 | 25.7 | 20 | 0.3 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF10 | 25.7 | 26 | 0.4 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_135131 | ir_p15 | SF12 | 25.7 | 38 | 0.5 | 27 | 27 | 27 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p06 | SF07 | 11.8 | 15 | 0.2 | 13 | 13 | 13 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p06 | SF08 | 11.8 | 6 | 0.1 | 13 | 13 | 13 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p06 | SF09 | 11.8 | 17 | 0.2 | 13 | 13 | 13 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p06 | SF10 | 11.8 | 36 | 0.5 | 13 | 13 | 13 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p06 | SF12 | 11.8 | 39 | 0.5 | 13 | 13 | 13 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p15 | SF07 | 20.8 | 7 | 0.1 | 22 | 22 | 22 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p15 | SF08 | 20.8 | 21 | 0.3 | 22 | 22 | 22 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p15 | SF09 | 20.8 | 15 | 0.2 | 22 | 22 | 22 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p15 | SF10 | 20.8 | 19 | 0.2 | 22 | 22 | 22 | 0 | 0 | all still |
| CH07_20260910_140227 | ir_p15 | SF12 | 20.8 | 53 | 0.7 | 22 | 22 | 22 | 0 | 0 | all still |
| CH07_20260910_141613 | ir_p06 | SF07 | 17.0 | 336 | 4.5 | 18 | 18 | 0 | 16 | 2 | moved |
| CH07_20260910_141613 | ir_p06 | SF08 | 17.0 | 387 | 5.2 | 18 | 18 | 0 | 15 | 3 | moved |
| CH07_20260910_141613 | ir_p06 | SF09 | 17.0 | 18 | 0.2 | 18 | 18 | 0 | 18 | 0 | moved |
| CH07_20260910_141613 | ir_p06 | SF10 | 17.0 | 33 | 0.4 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_141613 | ir_p06 | SF12 | 17.0 | 41 | 0.5 | 18 | 18 | 18 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF07 | 10.8 | 33 | 0.4 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF08 | 10.8 | 23 | 0.3 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF09 | 10.8 | 91 | 1.2 | 12 | 12 | 0 | 12 | 0 | moved |
| CH07_20260910_143243 | ir_p06 | SF10 | 10.8 | 35 | 0.5 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260910_143243 | ir_p06 | SF12 | 10.8 | 46 | 0.6 | 12 | 12 | 0 | 12 | 0 | moved |
| CH07_20260910_152307 | ir_p06 | SF07 | 12.3 | 37 | 0.5 | 14 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p06 | SF08 | 12.3 | 24 | 0.3 | 14 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p06 | SF09 | 12.3 | 164 | 2.2 | 14 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p06 | SF10 | 12.3 | 612 | 8.2 | 14 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p06 | SF12 | 12.3 | 17 | 0.2 | 14 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p15 | SF07 | 21.3 | 36 | 0.5 | 23 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p15 | SF08 | 21.3 | 26 | 0.3 | 23 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p15 | SF09 | 21.3 | 114 | 1.5 | 23 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p15 | SF10 | 21.3 | 643 | 8.6 | 23 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_152307 | ir_p15 | SF12 | 21.3 | 33 | 0.4 | 23 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p06 | SF07 | 14.0 | 24 | 0.3 | 15 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p06 | SF08 | 14.0 | 30 | 0.4 | 15 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p06 | SF09 | 14.0 | 27 | 0.4 | 15 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p06 | SF10 | 14.0 | 32 | 0.4 | 15 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p06 | SF12 | 14.0 | 39 | 0.5 | 15 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p15 | SF07 | 23.0 | 4 | 0.1 | 24 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p15 | SF08 | 23.0 | 21 | 0.3 | 24 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p15 | SF09 | 23.0 | 15 | 0.2 | 24 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p15 | SF10 | 23.0 | 25 | 0.3 | 24 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_163056 | ir_p15 | SF12 | 23.0 | 22 | 0.3 | 24 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p06 | SF07 | 9.3 | 15 | 0.2 | 10 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p06 | SF08 | 9.3 | 26 | 0.4 | 10 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p06 | SF09 | 9.3 | 12 | 0.2 | 10 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p06 | SF10 | 9.3 | 30 | 0.4 | 10 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p06 | SF12 | 9.3 | 55 | 0.7 | 10 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p15 | SF07 | 18.4 | 6 | 0.1 | 19 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p15 | SF08 | 18.4 | 36 | 0.5 | 19 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p15 | SF09 | 18.4 | 46 | 0.6 | 19 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p15 | SF10 | 18.4 | 52 | 0.7 | 19 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260910_175935 | ir_p15 | SF12 | 18.4 | 48 | 0.6 | 19 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p06 | SF07 | 126.9 | 615 | 8.2 | 127 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p06 | SF08 | 126.9 | 1335 | 17.9 | 127 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p06 | SF09 | 126.9 | 1030 | 13.8 | 127 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p15 | SF07 | 135.8 | 622 | 8.3 | 136 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p15 | SF08 | 135.8 | 1251 | 16.7 | 136 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_092822 | ir_p15 | SF09 | 135.8 | 1004 | 13.4 | 136 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_095409 | ir_p06 | SF07 | 212.7 | 38 | 0.5 | 214 | 214 | 207 | 7 | 0 | moved |
| CH07_20260911_095409 | ir_p06 | SF08 | 212.7 | 53 | 0.7 | 214 | 214 | 209 | 5 | 0 | moved |
| CH07_20260911_095409 | ir_p15 | SF09 | 221.7 | 179 | 2.4 | 223 | 223 | 210 | 13 | 0 | moved |
| CH07_20260911_095409 | ir_p15 | SF10 | 221.7 | 35 | 0.5 | 223 | 223 | 221 | 2 | 0 | moved |
| CH07_20260911_140955 | ir_p06 | SF07 | 19.8 | 20 | 0.3 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p06 | SF08 | 19.8 | 50 | 0.7 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p06 | SF09 | 19.8 | 25 | 0.3 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p06 | SF10 | 19.8 | 19 | 0.3 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p06 | SF12 | 19.8 | 15 | 0.2 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_140955 | ir_p15 | SF07 | 28.8 | 25 | 0.3 | 30 | 30 | 30 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p15 | SF08 | 28.8 | 32 | 0.4 | 30 | 30 | 30 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p15 | SF09 | 28.8 | 8 | 0.1 | 30 | 30 | 30 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p15 | SF10 | 28.8 | 41 | 0.5 | 30 | 30 | 30 | 0 | 0 | all still |
| CH07_20260911_140955 | ir_p15 | SF12 | 28.8 | 9 | 0.1 | 30 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_141758 | ir_p06 | SF07 | 31.0 | 11 | 0.1 | 32 | 32 | 32 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p06 | SF08 | 31.0 | 11 | 0.1 | 32 | 32 | 32 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p06 | SF09 | 31.0 | 21 | 0.3 | 32 | 32 | 32 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p06 | SF10 | 31.0 | 0 | 0.0 | 32 | 32 | 32 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p06 | SF12 | 31.0 | 13 | 0.2 | 32 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_141758 | ir_p15 | SF07 | 40.0 | 4 | 0.1 | 41 | 41 | 41 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p15 | SF08 | 40.0 | 9 | 0.1 | 41 | 41 | 41 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p15 | SF09 | 40.0 | 15 | 0.2 | 41 | 41 | 41 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p15 | SF10 | 40.0 | 18 | 0.2 | 41 | 41 | 41 | 0 | 0 | all still |
| CH07_20260911_141758 | ir_p15 | SF12 | 40.0 | 15 | 0.2 | 41 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_144345 | ir_p06 | SF07 | 11.5 | 54 | 0.7 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260911_144345 | ir_p06 | SF08 | 11.5 | 9 | 0.1 | 12 | 12 | 11 | 1 | 0 | moved |
| CH07_20260911_144345 | ir_p06 | SF09 | 11.5 | 10 | 0.1 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260911_144345 | ir_p06 | SF10 | 11.5 | 20 | 0.3 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260911_144345 | ir_p06 | SF12 | 11.5 | 22 | 0.3 | 12 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_144345 | ir_p15 | SF07 | 20.5 | 48 | 0.6 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_144345 | ir_p15 | SF08 | 20.5 | 21 | 0.3 | 21 | 21 | 20 | 1 | 0 | moved |
| CH07_20260911_144345 | ir_p15 | SF09 | 20.5 | 13 | 0.2 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_144345 | ir_p15 | SF10 | 20.5 | 16 | 0.2 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_144345 | ir_p15 | SF12 | 20.5 | 19 | 0.3 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_145024 | ir_p06 | SF07 | 11.1 | 46 | 0.6 | 12 | 12 | 5 | 7 | 0 | moved |
| CH07_20260911_145024 | ir_p06 | SF08 | 11.1 | 32 | 0.4 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260911_145024 | ir_p06 | SF09 | 11.1 | 31 | 0.4 | 12 | 12 | 12 | 0 | 0 | all still |
| CH07_20260911_145024 | ir_p06 | SF10 | 11.1 | 16 | 0.2 | 12 | 12 | 7 | 5 | 0 | moved |
| CH07_20260911_145024 | ir_p06 | SF12 | 11.1 | 15 | 0.2 | 12 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_145024 | ir_p15 | SF07 | 20.1 | 113 | 1.5 | 21 | 21 | 5 | 16 | 0 | moved |
| CH07_20260911_145024 | ir_p15 | SF08 | 20.1 | 42 | 0.6 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_145024 | ir_p15 | SF09 | 20.1 | 25 | 0.3 | 21 | 21 | 21 | 0 | 0 | all still |
| CH07_20260911_145024 | ir_p15 | SF10 | 20.1 | 43 | 0.6 | 21 | 21 | 7 | 14 | 0 | moved |
| CH07_20260911_145024 | ir_p15 | SF12 | 20.1 | 38 | 0.5 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p06 | SF07 | 19.8 | 95 | 1.3 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p06 | SF08 | 19.8 | 42 | 0.6 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p06 | SF09 | 19.8 | 342 | 4.6 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p06 | SF10 | 19.8 | 33 | 0.4 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p06 | SF12 | 19.8 | 21 | 0.3 | 21 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p15 | SF07 | 28.7 | 70 | 0.9 | 30 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p15 | SF08 | 28.7 | 6 | 0.1 | 30 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p15 | SF09 | 28.7 | 54 | 0.7 | 30 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p15 | SF10 | 28.7 | 21 | 0.3 | 30 | 0 | 0 | 0 | 0 | no IMU |
| CH07_20260911_182803 | ir_p15 | SF12 | 28.7 | 46 | 0.6 | 30 | 0 | 0 | 0 | 0 | no IMU |


## 3. Pre-registered fit: image (reference px) ↔ house frame (WISER minute means), house_2

Points: 89 blind named colour clicks with a WISER mean in 18 flashes (09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42, 09-10 13:51:31, 09-10 14:02:27, 09-10 14:16:13, 09-10 14:32:43, 09-10 15:23:07, 09-10 16:30:56, 09-10 17:59:35, 09-11 09:54:09, 09-11 14:09:55, 09-11 14:17:58, 09-11 14:43:45, 09-11 14:50:24, 09-11 18:28:03). Not in the fit: 09-10 08:37:42 (no WISER mean in [ON − 60 s, ON)); 09-11 09:28:22 (no WISER mean in [ON − 60 s, ON))

| fit | n | px_per_in | theta_house_deg | theta_paddock_deg | page_rot_deg | page_mirror | d_rot_vs_prior_deg | in_rms_in | lofo_rms_in | lofo_median_in | lofo_rms_px | lofo_median_px |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| proper | 89 | 74.8 | +93.7 | -174.3 | 174.3 | no | -5.7 | 5.31 | 5.45 | 4.09 | 406 | 306 |
| improper | 89 | 305.0 | -60.8 | +31.2 | 211.2 | yes | - | 9.13 | 9.37 | 7.59 | 3108 | 2346 |
| prior_rotation (fixed at the user's 180°) | 89 | 75.2 | +88.0 | -180.0 | 180.0 | no | +0.0 | 5.36 | 5.48 | 4.08 | 411 | 307 |


- **Handedness: proper** fits better — LOFO RMS 5.45 in (proper) vs 9.37 in (improper); in-sample RMS 5.31 vs 9.13 in. Proper = the displayed image is not mirrored relative to the WISER / paddock top view (as expected for a camera looking down).
- Proper fit: scale **74.8 px/in** (WISER inches per image px at head height; at this scale the house body's 24.6-in long side would span ≈ 1842 px and its 18.0-in short side ≈ 1346 px; the ridge maps onto the image's vertical axis (1920 px), the short side onto the horizontal (2560 px) — numbers only, not checked on the image), rotation θ_house +93.7°, θ_paddock -174.3°, page-equivalent orientation **174°, no mirror** vs the user's **180°, no mirror**: Δ = -5.7°.
- LOFO fold rotations range +92.6° … +95.2° (house frame; prior +88.0°); fold scales 71.2 … 77.2 px/in.
- LOFO residuals (primary): RMS **5.45 in**, median 4.09 in; in px RMS 406, median 306 px. For scale: per-fix WISER scatter (SD of the raw fixes in the minute) in the fitted flashes median 4.2 in along (2.1–11.0), 2.5 in across (1.0–14.6); minute-mean SE median 0.21 in; still-pair distance error p95 ≈ 3 in (plan); house body 24.6 × 18 in.
- Image centre (1280, 960) lands at along +2.3 in, across -4.0 in in WISER's house frame (= the WISER bias only if the camera axis meets the house centre; not separable from the camera position with a similarity).
- What the LOFO residual is made of (head mapped − WISER, in): RMS along the ridge 4.51, across 3.06. A common offset per flash (median |mean vector| 2.3 in, max 4.3) removes little: RMS 5.45 → 4.85 in (in-sample, optimistic). A fixed per-animal (tag) offset estimated from the other flashes does not help: RMS → 5.66 in. So the error is mostly animal × flash specific (WISER's minute mean off the clicked head by 5.5 in RMS in a pile), not a bias a per-flash or per-tag correction would remove. Within a flash the WISER means spread more along the ridge than the mapped heads (mean SD 6.5 vs 5.1 in).
- Reproduction: the page's [ON − 60 s, ON) means were recomputed with the page's own code for 90 animal × flash pairs: max |Δ| 0.0000 in; 0 presence mismatches.
- Rotation held at the user's orientation (scale + offset fitted): LOFO RMS 5.48 in (free fit 5.45 in).

LOFO residual per flash (primary fit):

| segment_id | n | rms_in | max_in | rms_px | max_px | fold_theta_house_deg | fold_px_per_in | lid_flag |
|---|---|---|---|---|---|---|---|---|
| CH07_20260909_191025 | 5 | 4.99 | 6.25 | 369 | 463 | +93.7 | 74.0 | ok |
| CH07_20260910_071415 | 5 | 5.15 | 8.24 | 382 | 612 | +94.4 | 74.3 | lid+ok |
| CH07_20260910_091147 | 5 | 5.43 | 10.23 | 403 | 759 | +93.6 | 74.2 | ok |
| CH07_20260910_122703 | 5 | 6.38 | 11.57 | 492 | 893 | +92.6 | 77.2 | ok |
| CH07_20260910_125142 | 5 | 5.18 | 7.75 | 396 | 592 | +93.9 | 76.4 | ok |
| CH07_20260910_135131 | 5 | 4.14 | 6.43 | 315 | 489 | +93.9 | 75.9 | ok |
| CH07_20260910_140227 | 5 | 4.67 | 6.87 | 355 | 523 | +93.4 | 76.1 | ok |
| CH07_20260910_141613 | 5 | 7.96 | 15.96 | 566 | 1136 | +94.2 | 71.2 | ok |
| CH07_20260910_143243 | 5 | 6.91 | 11.68 | 507 | 856 | +95.2 | 73.3 | ok |
| CH07_20260910_152307 | 5 | 3.33 | 4.13 | 247 | 307 | +93.8 | 74.4 | ok |
| CH07_20260910_163056 | 5 | 4.36 | 5.59 | 332 | 425 | +94.1 | 76.1 | ok |
| CH07_20260910_175935 | 5 | 3.25 | 4.77 | 245 | 359 | +93.9 | 75.4 | ok |
| CH07_20260911_095409 | 4 | 6.27 | 9.20 | 466 | 685 | +93.4 | 74.4 | ok |
| CH07_20260911_140955 | 5 | 7.15 | 12.90 | 540 | 975 | +92.8 | 75.5 | ok |
| CH07_20260911_141758 | 5 | 4.68 | 7.81 | 352 | 589 | +93.2 | 75.4 | ok |
| CH07_20260911_144345 | 5 | 5.00 | 6.69 | 375 | 501 | +93.5 | 75.0 | ok |
| CH07_20260911_145024 | 5 | 3.84 | 7.28 | 287 | 545 | +93.5 | 74.8 | ok |
| CH07_20260911_182803 | 5 | 6.80 | 8.44 | 498 | 618 | +92.8 | 73.2 | lid+ok |


Mean LOFO residual per animal over its flashes (head mapped − WISER):

| animal | n | mean_along_in | mean_across_in | mean_norm_in | sd_along_in | sd_across_in |
|---|---|---|---|---|---|---|
| SF07 | 18 | 1.14 | -0.50 | 1.24 | 3.20 | 3.03 |
| SF08 | 18 | -1.07 | 0.76 | 1.31 | 6.22 | 3.46 |
| SF09 | 18 | -1.05 | 0.39 | 1.12 | 5.33 | 2.53 |
| SF10 | 18 | 0.26 | -0.04 | 0.26 | 3.27 | 3.20 |
| SF12 | 17 | 0.86 | -0.75 | 1.14 | 3.86 | 3.21 |


## 4. The pre-registered order test (the operator's rule)

Clicks used: **blind record only** (before the reveal, not legacy; there are no legacy clicks), colour frame, named animals with a WISER mean; mapped by the fit that leaves the flash out (proper handedness = the lower LOFO RMS). WISER = default-track minute means over [ON − 60 s, ON).

**Verdict: NOT ACCEPTED** — exact order match in **0 of 5** of the first 5 eligible flashes (needs ≥ 4). Tie version (pairs < 8 in by WISER not tested): **NOT ACCEPTED** (3 of 5). Kendall τ median +0.20 (first 5), +0.20 (all).

| rank | segment_id | n | order_wiser | order_clicks | exact | tau | min_sep_along_in | n_pairs_ge_sep | n_conc_ge_sep | tie_match | discordant_ge_sep |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CH07_20260909_191025 | 5 | SF08 < SF07 < SF10 < SF12 < SF09 | SF08 < SF09 < SF10 < SF07 < SF12 | no | +0.2 | 0.5 | 4 | 4 | yes |  |
| 2 | CH07_20260910_071415 | 5 | SF12 < SF10 < SF07 < SF09 < SF08 | SF07 < SF10 < SF09 < SF08 < SF12 | no | +0.0 | 0.4 | 1 | 0 | no | SF08-SF12 |
| 3 | CH07_20260910_091147 | 5 | SF09 < SF12 < SF08 < SF10 < SF07 | SF08 < SF12 < SF10 < SF09 < SF07 | no | +0.2 | 0.0 | 4 | 2 | no | SF08-SF09, SF09-SF10 |
| 4 | CH07_20260910_122703 | 5 | SF08 < SF07 < SF12 < SF10 < SF09 | SF08 < SF12 < SF07 < SF10 < SF09 | no | +0.8 | 0.7 | 4 | 4 | yes |  |
| 5 | CH07_20260910_125142 | 5 | SF08 < SF12 < SF07 < SF09 < SF10 | SF08 < SF07 < SF12 < SF10 < SF09 | no | +0.6 | 2.0 | 5 | 5 | yes |  |
| 6 | CH07_20260910_135131 | 5 | SF08 < SF07 < SF12 < SF10 < SF09 | SF08 < SF12 < SF09 < SF10 < SF07 | no | +0.2 | 0.0 | 4 | 4 | yes |  |
| 7 | CH07_20260910_140227 | 5 | SF08 < SF07 < SF12 < SF10 < SF09 | SF08 < SF10 < SF09 < SF12 < SF07 | no | +0.0 | 0.0 | 4 | 4 | yes |  |
| 8 | CH07_20260910_141613 | 5 | SF12 < SF09 < SF10 < SF07 < SF08 | SF09 < SF12 < SF10 < SF07 < SF08 | no | +0.8 | 1.3 | 2 | 2 | yes |  |
| 9 | CH07_20260910_143243 | 5 | SF10 < SF12 < SF08 < SF07 < SF09 | SF12 < SF10 < SF07 < SF08 < SF09 | no | +0.6 | 0.8 | 4 | 3 | no | SF10-SF12 |
| 10 | CH07_20260910_152307 | 5 | SF10 < SF09 < SF12 < SF07 < SF08 | SF09 < SF12 < SF10 < SF07 < SF08 | no | +0.6 | 0.3 | 0 | 0 | - |  |
| 11 | CH07_20260910_163056 | 5 | SF07 < SF10 < SF12 < SF09 < SF08 | SF07 < SF10 < SF12 < SF09 < SF08 | yes | +1.0 | 1.0 | 7 | 7 | yes |  |
| 12 | CH07_20260910_175935 | 5 | SF07 < SF12 < SF08 < SF10 < SF09 | SF07 < SF08 < SF12 < SF09 < SF10 | no | +0.6 | 1.2 | 5 | 5 | yes |  |
| 13 | CH07_20260911_095409 | 4 | SF07 < SF09 < SF10 < SF08 | SF08 < SF10 < SF09 < SF07 | no | -1.0 | 0.8 | 0 | 0 | - |  |
| 14 | CH07_20260911_140955 | 5 | SF07 < SF10 < SF12 < SF09 < SF08 | SF08 < SF07 < SF10 < SF09 < SF12 | no | +0.0 | 0.7 | 2 | 1 | no | SF07-SF08 |
| 15 | CH07_20260911_141758 | 5 | SF10 < SF07 < SF09 < SF08 < SF12 | SF08 < SF07 < SF10 < SF09 < SF12 | no | +0.2 | 0.5 | 1 | 1 | yes |  |
| 16 | CH07_20260911_144345 | 5 | SF07 < SF08 < SF10 < SF09 < SF12 | SF10 < SF08 < SF07 < SF12 < SF09 | no | +0.2 | 0.8 | 2 | 2 | yes |  |
| 17 | CH07_20260911_145024 | 5 | SF07 < SF10 < SF12 < SF09 < SF08 | SF07 < SF10 < SF08 < SF12 < SF09 | no | +0.6 | 0.6 | 2 | 2 | yes |  |
| 18 | CH07_20260911_182803 | 5 | SF09 < SF07 < SF12 < SF10 < SF08 | SF08 < SF09 < SF10 < SF12 < SF07 | no | -0.4 | 0.7 | 1 | 0 | no | SF08-SF09 |


Order is written low → high along the ridge (along ≈ paddock +y, toward row C).

Variants (secondary; the verdict above is the primary):

| variant | n_flashes | lofo_rms_in | first5 | exact_first5 | verdict | tie_first5 | verdict_tie | exact_all | tau_med_all | acc_hungarian | acc_offset | chance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| primary | 18 | 5.45 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 3 | NOT ACCEPTED | 1 / 18 | +0.20 | 64% | 65% | 20% |
| proper | 18 | 5.45 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 3 | NOT ACCEPTED | 1 / 18 | +0.20 | 64% | 65% | 20% |
| improper | 18 | 9.37 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 0 / 18 | +0.20 | 19% | 20% | 20% |
| prior_rotation | 18 | 5.48 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 1 / 18 | +0.40 | 65% | 64% | 20% |
| raw_fix_means | 18 | 5.36 | 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42 | 0 | NOT ACCEPTED | 3 | NOT ACCEPTED | 1 / 18 | +0.20 | 62% | 65% | 20% |
| no_lid_flag | 16 | 5.37 | 09-09 19:10:25, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42, 09-10 13:51:31 | 0 | NOT ACCEPTED | 4 | ACCEPTED | 1 / 16 | +0.40 | 66% | 68% | 20% |
| alt_reading | 18 | 5.45 | 09-09 19:10:25, 09-10 07:14:15, 09-10 08:37:42, 09-10 09:11:47, 09-10 12:27:03 | 0 | NOT ACCEPTED | 2 | NOT ACCEPTED | 1 / 20 | +0.20 | 64% | 65% | 20% |
| centred_window | 20 | 5.26 | 09-09 19:10:25, 09-10 07:14:15, 09-10 08:37:42, 09-10 09:11:47, 09-10 12:27:03 | 0 | NOT ACCEPTED | 3 | NOT ACCEPTED | 2 / 20 | +0.40 | 76% | 71% | 20% |


- First 5 eligible flashes: 09-09 19:10:25, 09-10 07:14:15, 09-10 09:11:47, 09-10 12:27:03, 09-10 12:51:42; exact matches: none.
- All 18 eligible flashes: exact 1 / 18; tie version 11 / 16 testable; Kendall τ +0.2, +0.0, +0.2, +0.8, +0.6, +0.2, +0.0, +0.8, +0.6, +0.6, +1.0, +0.6, -1.0, +0.0, +0.2, +0.2, +0.6, -0.4.
- Pairs ≥ 8 in apart along the ridge by WISER: 52 of 176 pairs; concordant 46 (88%).
- Exact-order verdict across the secondary variants: NOT ACCEPTED in 5 of 5. Tie version across them: ACCEPTED in 2 of 5 (prior_rotation 4/5, raw_fix_means 3/5, no_lid_flag 4/5, alt_reading 2/5, centred_window 3/5) — borderline, it turns on one flash.
- Not eligible: 09-10 08:37:42 (no WISER mean in [ON − 60 s, ON)); 09-11 09:28:22 (no WISER mean in [ON − 60 s, ON))
- Alternative reading (a flash with ≥ 3 clicked animals but no WISER mean counts as a non-match: 09-10 08:37:42, 09-11 09:28:22): NOT ACCEPTED (0 of 5).

## 5. WISER as an identity aid: assigning the clicked heads by WISER

Hungarian assignment of the LOFO-mapped clicked heads to the WISER means (primary variant): **64%** of 89 clicks correct (greedy nearest 58%; with a free WISER offset per flash 65%; chance 20%).

By WISER separation of the clicked animal (2-D distance to the nearest other roster mean):

| bin_in | n_clicks | acc_hungarian | acc_greedy | acc_offset | chance |
|---|---|---|---|---|---|
| [0, 4) | 21 | 57% | 52% | 52% | 20% |
| [4, 8) | 46 | 61% | 54% | 65% | 20% |
| [8, 15) | 16 | 69% | 62% | 69% | 20% |
| >= 15 | 6 | 100% | 100% | 100% | 20% |


By along-ridge separation:

| bin_in | n_clicks | acc_hungarian | acc_greedy | acc_offset | chance |
|---|---|---|---|---|---|
| [0, 4) | 75 | 61% | 52% | 63% | 20% |
| [4, 8) | 7 | 71% | 86% | 71% | 20% |
| [8, 15) | 3 | 67% | 100% | 67% | 20% |
| >= 15 | 4 | 100% | 100% | 100% | 20% |


Per flash:

| segment_id | n | n_candidates | acc_hungarian | acc_greedy | acc_offset | swapped |
|---|---|---|---|---|---|---|
| CH07_20260909_191025 | 5 | 5 | 100% | 60% | 100% |  |
| CH07_20260910_071415 | 5 | 5 | 60% | 60% | 60% | SF07→SF12, SF12→SF07 |
| CH07_20260910_091147 | 5 | 5 | 60% | 60% | 60% | SF09→SF10, SF10→SF09 |
| CH07_20260910_122703 | 5 | 5 | 60% | 60% | 60% | SF07→SF10, SF10→SF07 |
| CH07_20260910_125142 | 5 | 5 | 60% | 60% | 100% | SF07→SF10, SF10→SF07 |
| CH07_20260910_135131 | 5 | 5 | 100% | 80% | 100% |  |
| CH07_20260910_140227 | 5 | 5 | 20% | 20% | 20% | SF07→SF09, SF09→SF07, SF10→SF12, SF12→SF10 |
| CH07_20260910_141613 | 5 | 5 | 20% | 60% | 20% | SF08→SF09, SF09→SF12, SF10→SF08, SF12→SF10 |
| CH07_20260910_143243 | 5 | 5 | 60% | 80% | 60% | SF10→SF12, SF12→SF10 |
| CH07_20260910_152307 | 5 | 5 | 100% | 60% | 100% |  |
| CH07_20260910_163056 | 5 | 5 | 60% | 60% | 60% | SF07→SF10, SF10→SF07 |
| CH07_20260910_175935 | 5 | 5 | 100% | 100% | 100% |  |
| CH07_20260911_095409 | 4 | 5 | 50% | 50% | 25% | SF08→SF10, SF10→SF08 |
| CH07_20260911_140955 | 5 | 5 | 60% | 40% | 60% | SF07→SF08, SF08→SF07 |
| CH07_20260911_141758 | 5 | 5 | 60% | 60% | 60% | SF08→SF09, SF09→SF08 |
| CH07_20260911_144345 | 5 | 5 | 60% | 40% | 60% | SF09→SF12, SF12→SF09 |
| CH07_20260911_145024 | 5 | 5 | 100% | 80% | 100% |  |
| CH07_20260911_182803 | 5 | 5 | 20% | 20% | 20% | SF07→SF10, SF08→SF12, SF10→SF07, SF12→SF08 |


- Of the 89 heads, 57 correct. Heads whose animal is ≥ 8 in from every other roster mean: 77% (n 22); < 8 in: 60% (n 67).
- Distance from a mapped head to its own animal's WISER mean: median 4.1 in, p90 7.9 in.
- Swaps (Hungarian) per flash: 09-10 07:14:15: SF07→SF12, SF12→SF07; 09-10 09:11:47: SF09→SF10, SF10→SF09; 09-10 12:27:03: SF07→SF10, SF10→SF07; 09-10 12:51:42: SF07→SF10, SF10→SF07; 09-10 14:02:27: SF07→SF09, SF09→SF07, SF10→SF12, SF12→SF10; 09-10 14:16:13: SF08→SF09, SF09→SF12, SF10→SF08, SF12→SF10; 09-10 14:32:43: SF10→SF12, SF12→SF10; 09-10 16:30:56: SF07→SF10, SF10→SF07; 09-11 09:54:09: SF08→SF10, SF10→SF08; 09-11 14:09:55: SF07→SF08, SF08→SF07; 09-11 14:17:58: SF08→SF09, SF09→SF08; 09-11 14:43:45: SF09→SF12, SF12→SF09; 09-11 18:28:03: SF07→SF10, SF08→SF12, SF10→SF07, SF12→SF08.
- Typical spacing inside a pile: the clicked animal's nearest other WISER mean is a median 5.5 in away (along the ridge 1.3 in), against a mapped-head-to-own-mean distance of median 4.1 in.

## Superseded preliminary run (browser snapshot 2026-10-10 20:17)

Input `cv/configs/inbox_identity_2026c/browser_snapshot_20261010T2017.json` (sha256 `b37a94cb00ae732a…`; a copy of the page's localStorage, not a formal export; 11 / 22 segments, 141 clicks), analysed on 2026-10-10 into `cv_field_inbox_clicks_20261010_2042` (report text in git history, commits e679650 / dcedabf). Re-analysed here with the current code into `D:/Field2026_analysis_out/2026c/cv_field_inbox_clicks_20261010_2227/superseded_snapshot`; identical to the 10-10 run on all 8 variants (LOFO RMS, order counts, verdicts, accuracies): **yes**. Its headline numbers are the snapshot column above; its summary was:

- **Data** (browser snapshot (not a formal export)): 141 clicks (135 blind, 5 after the reveal, 1 unsaved, 0 legacy) in 11 of 22 segments, all CH07 / house_2.
- **1. Composition**: colour-frame set = WISER roster in 8 of 10 revealed segments; SF11 never clicked; 3 unknown clicks.
- **2. Colour → IR**: where the IR frame is < 30 s after the colour frame the clicked heads moved median 27 px (≈ 0.3 in), max 387 px; 6 of 60 pairs > 100 px.
- **3. Fit**: proper handedness; 79.3 px/in; page-equivalent rotation 178° vs the user's 180° (Δ -1.8°); LOFO RMS 5.96 in / 470 px.
- **4. Pre-registered order test: NOT ACCEPTED** (0 of 5 exact; needs 4); tie version ACCEPTED (4 of 5); Kendall τ median +0.40.
- **5. WISER as an identity aid**: Hungarian assignment 65% correct (chance 20%); [0, 4) in: 70% (n 10), [4, 8) in: 60% (n 20), [8, 15) in: 50% (n 6), >= 15 in: 100% (n 4).

Why superseded: the export adds 10 flashes to the fit (89 vs 40 points) and the user's composition statement; it changes no blind click(s) of the snapshot. Order-test verdict: NOT ACCEPTED → NOT ACCEPTED; tie version ACCEPTED (4 of 5) → NOT ACCEPTED (3 of 5) — the first-5 inputs are identical, so any change comes from the leave-one-flash-out maps (more flashes in each fold's fit).

## What is not verified

- Clicks from the user's CSV export; 20 of 22 segments clicked; one house (CH08 / house_1 has no clicks).
- The user's colour IDs are the reference; no second labeller; identities rest on the user's corrected key (SF09 black, SF10 blue).
- A 2-D similarity ignores perspective and head height: the camera sits in the lid ≈ 1 ft above the floor and piled heads lie at different heights, so one scale cannot hold everywhere; WISER is a 2-D solve (all z = 0) and cannot say who lies on top.
- WISER minute means come from the minute before ON; the colour frame is several seconds (long segments: minutes) later.
- Frames inside a lid-event window (`lid+ok`: 09-10 07:14, 09-11 09:28, 09-11 18:28) use the lid segment's median correction; the camera may have been off it while the lid was open.
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

**Composition (Q1).** Roster $\mathcal R_f$ = tagged animals whose cleaned per-second state is the camera's house at the colour
frame (the page's roster: dilated rectangle + 15 in, 6-s smoothing, 20-s minimum dwell; `states_1s.npz`); clicked set
$\mathcal K_f$ = animals with a named blind click on the colour frame. *Agree* $\Leftrightarrow \mathcal K_f = \mathcal R_f$;
*missing* $= \mathcal R_f \setminus \mathcal K_f$; *extras* $= \mathcal K_f \setminus \mathcal R_f$. The user's composition statement
(every clicked frame complete; fewer clicks = animals outside the house) makes $\mathcal K_f$ the in-house set, so a missing animal
is a WISER over-inclusion and an extra a WISER omission. *WISER at the colour frame*: the mean house-frame position of all
primary-rule default-track fixes in $[t_{col} - 5\,\mathrm s, t_{col} + 5\,\mathrm s)$; *inside the body* $\Leftrightarrow |A| \le 12.3$ in
and $|C| \le 9.0$ in; *outside distance* = $\sqrt{\max(|A| - 12.3, 0)^2 + \max(|C| - 9.0, 0)^2}$ (in). *In-body roster* = roster
animals inside the body by that position (secondary).

**Blind record, snapshot vs export.** Clicks matched by `click_id`; *same* = identical status, animal, frame kind and position
in both the live and the blind (`verdict_first` / `first_*`) values and the same $B$; *changed* lists the differing fields.

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

Run folder `D:/Field2026_analysis_out/2026c/cv_field_inbox_clicks_20261010_2227`: `clicks_table.csv` (every click, both records, B-corrected), `composition.csv`, `wiser_at_colour_frame.csv`, `stability_blind.csv`, `stability_final.csv`, `stability_counts.csv`, `stability_per_segment.csv`, `fit_summary.csv`, `fit_points_<variant>.csv` (LOFO predictions per click), `lofo_per_flash.csv`, `order_<variant>.csv`, `assignment_<variant>.csv`, `variants.csv`, `residual_per_animal.csv`, `wiser_centred_window.json`, `wiser_reproduction_check.csv`, `blind_record_snapshot_vs_export.csv`, `order_test_first5_snapshot_vs_export.csv`, `headline_snapshot_vs_export.csv`, `superseded_snapshot/` (the snapshot re-analysed, same file set), `run.json`; figures `figures/flash_overlays_primary.png`, `figures/colour_ir_displacement.png`, `figures/assignment_vs_separation.png`. Pointer `results/2026c/cv_field/reports/run_manifest_inbox_clicks_2026c.json`.
