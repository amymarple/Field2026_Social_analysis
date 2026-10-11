# CH05-CH08 into the paddock frame (cohort 2026c)

**Status: DONE** (2026-10-11; started 2026-10-10; the recording repo's calibration session, at the user's request: "现在我们来做05 06 07 08
对画面的映射 … 按照我们之前的purpose 我们需要05 06 07 08 到最终2D paddock的映射我们之前做了CH01-04").

## Why

CH01-CH04 map into the paddock at any cohort time through `cv/cv_field/frame_correction.py` (cohort px -> 09-18 px) and
the frozen release calibration (rev g). CH05-CH08 do not, or only partly:
- CH05 (over house_1): nights only, tied to its own 09-04 03:01 frame, never to 09-18 - house_1 was moved on 09-18, so
  no image registration reaches the calibration frame; `to_paddock` refused it.
- CH06 (over house_2): nights only.
- CH07 / CH08 (inside house_2 / house_1): corrected all day per lid-closed segment to their 09-04 12:00 frame, but no
  pixel -> house -> paddock model exists.
The houses matter by day (rats sleep there; the IMU-video session needs those hours) and for identity work.

## What is done (recording repo, commit 0f296a2)

- `calibration_qc/house_tie.py`: CH05's turn between its 09-04 reference frames and the calibration, measured on
  house_1 at its cohort pose (rigid model, CH01 + CH02 09-04 12:00 labels) and on pole B1, differentially against the
  09-18 frame. Validated on CH06 (house_2 never moved) against this repo's own image registration: 4-5 px, 5-7 mm
  median / 13-17 mm p90 at head height. CH05 turned 2.2 deg (~9 cm on the ground). Report `HOUSE_TIE_2026-10-10.txt`.
- `calibration_qc/cohort_tie.py` + `cohort_ties_2026c.json`: applies the turn to the release camera (sha-bound).

## Steps here

1. **CH05 / CH06 all day** (`frame_correction.py`): `ROOF_CAMS` = CH05 / CH06 leave the night-only set; their samples
   are segmented at the lid events (they register on the roof, which is the lid) and a lookup interpolates only inside
   t's segment and between samples of one reference frame (CH05: 09-04 03:01 at night, 09-04 12:00 by day). New track
   run `landmark_track.py --cameras CH05 CH06 --ref-labels <09-04 12:00:02 labels> --tie --times 05:00 .. 20:00
   --extra-targets cv/configs/cohort3_lid_events.json --tag ch0506_ref0904day_hourly`; added to `TRACK_TAGS`.
2. **CH05 to the paddock**: `Corrections.to_paddock` maps a non-09-18 target through `cohort_tie.load().find(cam,
   target)`; the in-box cameras still return None.
3. **CH07 / CH08** (next): the user labels the floor (corners, floor / wall edges, wall joints, door sides) on the
   09-04 08:31-13:35 segment (recording repo `calibration_qc/inbox_floor_gui.py`). Model: lens from the RLC-520A of
   CH05 / CH06 if it carries over (to be checked on straight edges), camera pose from the floor rectangle (60.0 x 43.2
   cm = the 62.55 x 45.72 cm body minus 1/2-inch walls, user) and the vertical joints; floor -> house frame -> paddock
   through the house poses (house_2 09-18 fit, house_1 cohort pose); images = the paddock rotated 180 deg (user, both).
   Then `Corrections.to_paddock` for CH07 / CH08 through their 09-04 12:00 frame.
4. Docs: `cv/cv_field/CAMERA_GEOMETRY_2026c.md` rules and camera table; change log after.

## Checks / gates

- `frame_correction.py --selftest` (adds: roof camera, no interpolation across a lid event or between references).
- Table rebuild diff: only CH05 / CH06 rows change (segments, lid flags, new day rows); every other value identical.
- CH06 day vs night continuity at the segment boundaries; CH05 day (12:00 reference) vs night (03:01 reference) agree
  through their two ties within ~1-2 cm at the same physical time window.
- CH07 / CH08: floor-rectangle fit residual, the joints meeting at one nadir point, and WISER in-box positions /
  the identity clicks as a coarse independent check.

## Error budget (CH05 at head height, to be completed)

Tie method ~5-7 mm median (CH06 check); house_1 cohort pose ~1 cm; pivot (camera bracket vs crossbeam) ~1 cm; lid
placement between rounds (CH08's jumps at lid events bound it); plus the release's own CH05 error.
