# CH05 / CH06 into the paddock at any cohort time; CH07 / CH08 under way (2026-10-10 / 11)

Plan: `implementation_plan/2026-10-10-ch05-ch08-paddock-mapping.md`. Made by the recording repo's calibration session at
the user's request (map CH05-CH08 into the 2-D paddock like CH01-CH04).

## Changed

- `cv/cv_field/frame_correction.py` (9c3edb5):
  - CH05 / CH06 (`ROOF_CAMS`) are covered all day and segmented at the lid events, because they register on the roof,
    which is the lid. A lookup uses only t's lid-closed segment and the samples of the nearest sample's reference frame.
  - `Corrections.camera_model` / `to_paddock`: CH05 maps through the recording repo's cohort tie
    (`calibration_qc/cohort_tie.py` + `cohort_ties_2026c.json`, recording commits 0f296a2 / 0d3afb0).
  - Self-test adds a roof-camera case (PASS).
- New track run `ch0506_ref0904day_hourly` (`D:\Field2026_analysis_out\2026c\cv_field_landmark_track_ch0506_ref0904day_hourly_20261010_2330`):
  - Coverage: 05:00 -> 20:00 hourly, plus 10 min before / after every lid event, 08-30 -> 09-17.
  - References: the 09-04 12:00:02 labels.
  - 551 frames; CH05 252 ok / 22 unreliable (held-out median 0.5 px); CH06 246 ok / 31 unreliable (1.5 px, tied to 09-18).
  - An earlier start of the same run (`..._20261010_2315`) was cut off at 129 frames when its session ended. It has no
    `track_frames.csv` and is not used.
- Table `results/2026c/cv_field/reports/cv_field_frame_corrections_2026c.csv` rebuilt twice:
  - From the existing runs: only CH05 / CH06 segments changed, plus four lid flags (the 08-31 03:30-07:30 round); every
    other value is identical to 1e-13.
  - With the day run: 1496 -> 2031 rows (CH05 +269, CH06 +266); no existing row changed.
- `cv/cv_field/CAMERA_GEOMETRY_2026c.md`: rules 2, 3 and 5, and the CH05 / CH06 rows of the camera table.

## Checks

- **CH05 tie** (recording repo `calibration_qc/house_tie.py`, `HOUSE_TIE_2026-10-10.txt`):
  - Method: house_1 at its cohort pose and pole B1, differential against 09-18.
  - On CH06 (house_2 never moved) the same method agrees with this repo's image registration 09-04 <-> 09-18 to
    4-5 px, 5-7 mm median / 13-17 mm p90 at head height.
  - CH05 turned 2.2 deg between 09-04 and 09-18 (~9 cm on the ground). Untied CH05 pixels were off by that much.
- **Night <-> day in one lid segment** (04:20 night sample vs 05:00 day sample, paddock position at 60 mm):
  - CH06: 3-6 mm median per night, p90 <= 14 mm.
  - CH05: 5 mm median, p90 7-9 mm. Night and day use two independent references and their two independent ties.

## Behaviour change for users

A daytime CH05 / CH06 query now uses daytime samples of its own lid segment. Before, it silently returned the nearest
night sample. Times inside a lid event carry flag `lid`.

## CH07 / CH08 (2026-10-11)

- **Floor model**: recording repo `calibration_qc/inbox_floor_fit.py`, commit 0220388, report
  `F:\calibration\qc\inbox_floor\INBOX_FLOOR_FIT.txt`.
  - Labels: the user's floor corners and floor / wall edges on empty-house night frames of 09-03/04 (chosen with this
    repo's `box_occupancy_1s.csv.gz`, every frame checked by eye), plus the user's 03:01 INNER_EDGES as wall joints.
    Both are mapped to the 09-04 12:00 reference frame through this table.
  - Model inputs: floor 60.0 x 43.2 cm (body minus 1/2-inch walls, user); lens fixed to the CH05 / CH06 RLC-520A
    mean (a free lens is not identifiable on one plane).
  - Fit: click residuals 1-3 mm median; leaving any one item out moves the map <= 10 mm (CH07) / 3 mm (CH08);
    lens free vs fixed 11 / 6 mm median at head height.
  - Cameras 683 / 679 mm above the floor, 11-12 deg tilt. 79.6 px / in at head height, vs the identity fit's
    79.3 px / in (WISER <-> clicks, independent).
- **Orientation check against WISER (09-04 12:00)**:
  - CH08: the pile of three at along -7 in and the lone rat at +8 in, vs SF07 / SF08 / SF12 at -12 .. -16 and SF10
    at +13.
  - CH07: rats at along 0 / +9 in, vs WISER +5 / +12.
  - Both images are therefore the paddock rotated 180 deg, not mirrored.
- **`Corrections.to_paddock`**: maps CH07 / CH08 through it with no code change (cohort tie entries); z is above the
  house floor, NaN outside the floor.
- **Not covered**:
  - The house poses' ridge angle (~2 deg, ~1 cm at the box ends).
  - The 1/2-inch wall assumption (+-6 mm at the walls).
  - The in-box segment corrections' own spread (~1-3 px, ~1 mm).
