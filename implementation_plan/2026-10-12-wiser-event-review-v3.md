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

## Amendment 1 (2026-10-12, implementation; written before any v3 verdict exists)

These are places where the plan could not be followed literally or was ambiguous. Each entry gives the closest
faithful choice. The agent never opened a frame; every number below comes from WISER, the projection or the tables.

1. **Day corrections exist only for CH05–CH08.**
   - The correction table covers CH01–CH04 at night only, 21:00 → 04:20 (`CAMERA_GEOMETRY_2026c.md` rule 3). It has no
     daytime track run for them.
   - "Real day corrections replace the nearest-night fallback" therefore holds for the house cameras only: CH05 / CH06
     hourly by day, CH07 / CH08 per lid segment.
   - Day and twilight frames on CH01–CH04 keep v2's nearest-night correction, flagged in the clip as before.
   - Day corrections for CH01–CH04 would need `landmark_track.py --times …` runs. Those write into
     `results/2026c/cv_field/`, outside this task's files; the main session may schedule them.
2. **Corner swap: "has it" means the mapped ground, otherwise the image frame.**
   - In all six named corner events the mapped start position lies **beyond the paddock wall**, in inches: W02
     (10.9, −10.5), W04 (−12.0, −0.2), W27 (−11.9, −2.5), W33 (−12.2, −20.6), W30 (477.8, 11.1), W51 (477.4, 5.4).
   - That is 9–36 in from the nearest mapped cell of CH03 / CH04, so no camera's verified ground holds it. The literal
     rule would never swap.
   - Rule used: (a) the end camera whose mapped ground holds the start position (p0 `Support` at the onset); otherwise
     (b) the end camera whose image contains it.
   - (b) uses the camera model's own inverse, `Corrections.camera_model(cam, target_frame).to_paddock_inv` (z 60 mm),
     plus the frame correction, with no support limit. It never draws a circle: circles are still drawn only on the
     verified mapped ground.
   - The plan says to replace "the panorama without it", but neither panorama has it. The replaced panorama is the one
     with fewer of the clip's target positions (V3 per 0.25-s step, mapped) in its mapped ground. Ties go to the one
     whose nearest mapped cell is farther from the start position, then to CH02.
   - An end camera without video in the clip is not used.
   - The end camera keeps its aspect, centred in the replaced panorama's slot. The canvas size is unchanged.
3. **CH05 / CH07 / CH08 need the cohort ties loaded.**
   - `Corrections.camera_model` imports the recording repo's `cohort_tie` lazily. After `import_p0` restores
     `sys.path` that import fails silently, and CH05 / CH07 / CH08 come back refused as "not calibrated".
   - `--v3` preloads every tied camera while `calibration_qc/` is on `sys.path`: CH05 09-04 03:01 and 12:00, and the
     CH07 / CH08 floor models.
   - Without `--v3` the old behaviour (refused) stays, so `--circles` still rebuilds GUI v2. This was checked
     byte-identical on 12 events (W01 W02 W03 W06 W07 W13 W17 W19 W35 W40 W49 W78): blind and reveal overlays,
     `events.json` and `selection.csv`.
   - GUI v1 (no flag) was checked on all 80 events: overlays, `events.json` and `selection.csv`.
   - Both checks are in `<run>/repro_check/`.
4. **Lid and missing corrections are handled per frame.**
   - Each 0.25-s step is checked at its whole second. A correction flag containing `lid` gives status `lid`; a refused
     correction gives `no correction`.
   - Either way the step gets no circle and the reveal clip shows a note. The start circle at the onset follows the
     same rule.
   - None of the 80 clips (± the 5-min margins) overlaps a lid event, so no step carries it in this run. The self-test
     covers it.
5. **In-box views (CH07 / CH08).**
   - The 14-in circle is wider than the house floor (60 × 43 cm), and the floor model is NaN off the floor. Only the
     arcs on the floor can be drawn.
   - A `+` marks the circle centre: white for the start, yellow for WISER, cyan for the other rats.
   - Notes: "the 14-in circle is wider than the house floor: + marks its centre, arcs only on the floor" in both clips;
     "in a house WISER tells who is inside, not where in the pile" in the reveal clip.
6. **New status "edge of ground", and a tighter Newton tolerance.**
   - p0's 1-in support raster overshoots its mapped 40-px cells. A target in that band sends Newton off the mapped
     ground (NaN forward).
   - v3 labels this case `edge of ground`: not drawn, and counted separately in `projection_coverage.csv`
     (`steps_edge_of_ground`, `targets_edge_of_ground`). `inverse failed` is kept for genuine non-convergence.
   - The Newton tolerance is 0.005 in. p0's default of 0.02 in is up to 1.6 px at CH07 / CH08's 80 px / in.
7. **Other animals.**
   - Drawn: every identity label of the production tracks (SF07–SF12, SF12_tag12376) except the target animal's own.
     Masked rows are excluded as in v1 / v2, including SF11 after 09-07 06:10:45 (`m_off_animal`).
   - Each animal is placed on its own aligned clock t_al, by p0's `Tracks` (gap ≤ 5 s).
   - A second tag of the same animal only fills steps where the primary tag is not located, and is labelled with the
     animal id.
   - Drawn under the target ring with a thin stroke.
   - The five females released 09-11 19:40 have no tag and are not drawn.
   - Neither drawn in the blind clip nor named on the page before the reveal.
8. **Map status placement.**
   - One line per view in both clips; the blind wording has no "WISER". The same line is in the page's Circles box.
   - The reveal line adds "if the dashed circle misses the rat at the onset, the map is off, not WISER".
   - CH01 / CH02:
     - The night is 12:00 → 12:00, named by its dusk date.
     - Only an onset within 21:00–04:20 uses that night's kit row (`real_within14_share`, verdict pass / fails).
     - Other hours read "map not validated at this hour".
     - Nights without a kit row read "map not validated on night MM-DD (<reason>)": 09-05 frozen test night, 09-11
       population change.
   - The status is taken per camera at the event onset.
9. **Page and export.**
   - `gui: "v3"`; the schema and the CSV columns are unchanged.
   - Import of a v2 export merges judgements by W id. Each imported judgement is marked
     `imported_from: "<gui> <run_id>"`, inside `judgements` only.
   - Events that newly have a circle reopen the circle question (status `revealed`).
   - `event_summary.csv` gains `camera_swap` and `other_rats_drawn` (v3 only).
10. **Round trip.**
    - Computed per projected event-camera at its onset (120-px grid, as v2), plus stand-alone grids for every camera at
      09-06 02:00 and 14:00. Results are in `roundtrip_by_camera.csv`.
    - p99 and max are reported both overall and outside the panorama seam band |u − 3840| < 150 px (v2 Amendment 1.6).
