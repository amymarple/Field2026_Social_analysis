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
