# Event-review GUI v3: WISER circles on all eight cameras, day and night (cohort 2026c)

**Status:** PLANNED 2026-10-12. **Approval:** the user, 2026-10-12 ("行吧 干吧"), after the calibration session made
`Corrections("2026c").to_paddock` work for CH01–CH08 at any cohort time (`change_log/2026-10-10-ch05-ch08-paddock-mapping.md`).
A viewing-aid update of GUI v2 (`implementation_plan/2026-10-06-wiser-event-review-circles.md`); no new test. Operational
details **[op]**. **Driver:** extend `wiser/scripts/make_wiser_event_review.py` (new flag `--v3`, implying `--circles`;
v1 and v2 stay reproducible).

## Facts (not re-derived)

- GUI v2 `D:\Field2026_analysis_out\2026c\wiser_event_review_20261006_1637\index.html`: 80 events W01–W80 (30 largest I1,
  20 random I1, 30 largest I2), blind start circle → reveal clip with the moving V3 circle + raw dot, `circle_verdict`,
  `map_flag`; 68 / 80 events had a circle. No circle on CH05 (refused then), CH07 / CH08 (no map) or the 6 corner I2 events
  outside both panoramas' mapped ground; 17 day / twilight events used the nearest night correction.
- Now: `to_paddock(cam, t, uv, z_mm)` works for **CH01–CH08, day and night**.
  - CH05 goes through the cohort tie (house_1 + pole B1; 5–7 mm median on CH06).
  - CH05 / CH06 are segmented at the lid events (flag contains "lid" inside an event).
  - CH07 / CH08 use house-floor models: z above the house floor, NaN outside the floor, 79.6 px/in at head height, images =
    paddock rotated 180°, ~1–2 cm.
  - CH03 / CH04 cover the two paddock ends.
- WISER → paddock is still the phase-0 similarity map (`cv/cv_field/wiser_assist_p0.py`), accepted on one CH01 hour. Per
  CH01 / CH02 night the WISER pixel kit's validation (`D:\Field2026_analysis_out\2026c\wiser_pixel_kit_20261006_1952\kit.json`
  → `validation_table`) gives a within-14-in share of 0.22–0.77; CH01 09-01, CH02 09-01 and CH02 09-02 fail. In houses WISER
  gives the roster and the door events, not the order inside a pile.

## What changes

1. **Circles on every camera of a clip** through the inverse of `to_paddock`, with z = 60 mm (head height; above the house
   floor for CH07 / CH08). Real day corrections replace the nearest-night fallback. Frames flagged "lid" or outside a
   camera's support get no circle and a short on-screen note.
2. **Corner events [op]:** for an open-field event where neither panorama has the target's start position in its support,
   CH03 or CH04 (whichever has it) replaces the panorama without it. Cameras for the houses stay as in v2 (house_1 CH08 +
   CH05, house_2 CH07 + CH06).
3. **Reveal clip [op]:** besides the target's moving circle (solid yellow) and raw fix (red dot), the **other tagged
   animals' circles** are drawn thin, in cyan, labelled with their id. This helps decide whether the target circle sits
   on the right rat. The **blind** clip is unchanged: only the target's static start circle.
4. **Map status on screen:** per clip, the night's kit validation share for CH01 / CH02 (or "not validated" / "fails").
   For CH03–CH08 the line reads "map validated on CH01 only".
5. **Same 80 events, W ids and order;** new output folder `D:\Field2026_analysis_out\2026c\wiser_event_review_<ts>\`;
   export schema unchanged plus `gui: "v3"`. Answers from v2 carry over through **Import** of a v2 JSON export, because the
   W ids are the same.

## Checks (the agent never judges a frame)

- Round trip pixel → paddock → pixel per camera on a grid (report max and p99, outside the pano seam band).
- Coverage per event × camera: share of frames with a target circle; events with no circle on any camera, and why.
- `--selftest` extended: CH07 / CH08-like floor model (rotation 180°, NaN off the floor), the corner-camera swap, other-animal
  circles only in the reveal clip, lid-flagged frames without a circle.

## Outputs

New run folder (`clips/`, `clips_reveal/`, `panels/`, `index.html`, `projection_coverage.csv`, `circles_summary.json`),
`change_log/2026-10-12-wiser-event-review-v3.md`, an updated `wiser/configs/wiser_event_review_2026c/README.md` (v3 fields).
The main session updates CLAUDE.md and both index READMEs and commits.
