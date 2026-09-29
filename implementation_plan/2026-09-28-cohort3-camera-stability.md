# Cohort-3 camera stability (CH01–CH04) — did a camera move? (2026-09-28)

**Status.** Revised 2026-09-28 after a first attempt: **human review of daily frames** replaces the automatic check
(user decision). CH01/CH02 first — they carry most of the occupancy map.

**Why.** The only camera calibration is the 2026-09-24 release (recording repo `calibration_qc/`, sessions 09-18/19).
Nothing records a camera move between cohort 3 (08-30 → 09-12) and 09-18, but nothing ever verified it either (no
drift check, no reference stills; `AUDIT_PLACE_FIELD_READINESS_2026-09-26.md`); cohort 3 had people in the paddock
(08-31 11:00–18:00 troubleshooting), construction (09-08), mowing (09-09), rain and wind. Before cohort-3 detections
are mapped to paddock coordinates we need, per camera, the periods over which one calibration applies.

**First attempt (rejected).** ECC registration (Euclidean) on a ±60 px band around the labelled wall-foot lines,
day frames vs the 09-18 reference and nights vs the first cohort night. Same-session 60-s controls were excellent
(0.0–0.3 px, cc 0.97–0.99) but every cross-day comparison was unreliable (cc 0.14–0.65, per-wall-line shifts
inconsistent): half the band is ground, and grass growth, rain and the IR/colour mode change dominate it. The user
judged that such a check cannot be made reliable ("草肯定会长…下雨也会导致偏差") — see the change_log entry.

**What now.** `cv/cv_field/camera_review.py`: for each camera and day, frames at 03:01 / 12:00 / 21:30 (field-PC time)
from the local copy `F:\3rd_rat\`, each overlaid with the 09-18 wall-foot lines, laid out as one HTML page per camera
(09-18 reference on top, one row per day, click to blink against the reference, full-res linked). The **user** judges
by eye; weather-driven moves (rain, wind) are reported manually by the user as QC. The tool makes no judgement.
Output off-repo: `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_camera_review_<ts>/index.html`.

**Next.** The user's verdict per camera and period goes into a small registry (per camera: stable periods, move
times) that the paddock-mapping code will read; the 09-19 calibration session is added when it comes off the field PC.

## Revision 2 (2026-09-28): cohort-pixel → calibration-pixel correction from rigid landmarks

User findings after the IR-reference flipbooks: CH01/CH02 show a large DISTORTION change between cohort 3 and the
09-18 calibration (a house's size differs; the central pole barely moves); CH03/CH04 show no distortion change but
larger day-to-day MOTION. The calibration anchors were set after the cohort, so the 09-24 calibration cannot be applied
to cohort pixels as is. Plan (approved step by step with the user):

0. **When did it change?** Before/after IR frames around every candidate event from the records
   (`cv/configs/cohort3_camera_events.json`: PC blue screen as a control, 08-31 unlogged troubleshooting, the 09-06
   NVR reboot, cohort end → 09-16 restart, 09-17 → 09-18 (26 h unrecorded, image mode changed), the CH01/CH02
   dawn/dusk restart clusters, the 09-02 storm, the 09-03 rain, the 09-18 hand-held sweeps) —
   `camera_review.py --events`; the user judges each pair → epoch boundaries.
1. **Landmarks (user):** both edges of each pole (`POLE_<grid>_L/_R`, two parallel lines; their spacing also
   measures the local image scale — useful for the CH01/CH02 distortion), wall TOP edges (`WALLTOP_*`), the water tower (`TOWER`),
   the PC box facing CH02 (`PCBOX`); houses (`HOUSE_*_ROOF/BASE`) labelled for validation only. Tool:
   `cv/cv_field/landmark_gui.py` (adapted from the recording repo's `calibration_qc/line_gui.py`); labels in
   `cv/configs/landmarks/2026c/`. First: the four 09-18 IR references; then 1–2 frames per cohort epoch.
2. **Tracking (agent):** the labelled structures are located in every other IR frame by patch matching → per-landmark
   displacement series per camera → change points = epochs; reviewed by the user as overlay flipbooks.
3. **Mapping:** CH01/CH02 a smooth non-rigid warp (thin-plate spline or 2-D polynomial) per epoch; CH03/CH04 a rigid
   (rotation-dominated) map per day or finer — both depth-independent, fitted on point-to-curve distances; held-out
   landmarks give the real error.
4. **Paddock coordinates:** cohort pixel → warp → calibration-epoch pixel → 09-24 `paddock_map` → paddock. Checks:
   known poles / wall top vs design, CH01–CH02 agreement in the overlap, later WISER.
   Proposed acceptance: held-out landmark error median ≤ 3 px, p90 ≤ 6 px; known structures within the calibration's
   own error (CH01 p90 216 mm, CH02 152 mm).
