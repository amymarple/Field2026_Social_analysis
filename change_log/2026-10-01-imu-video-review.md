# Head-IMU video-review GUI: clips with the IMU's guess burnt in, a local review page, human labels (cohort 2026c) — 2026-10-01

- **Request (user, 2026-10-01):** "make video clips and on the top of the frame show what you think the animal is doing
  from shake or still. also tell me what animal is doing what. i need gui for this".
- **Plan:** [`implementation_plan/2026-10-01-imu-video-review.md`](../implementation_plan/2026-10-01-imu-video-review.md)
  (one amendment before the full run: the RHYTHMIC floor, below).
- **Bulk (off-repo):** `D:\Field2026_analysis_out\2026c\imu_video_review_20261001_1237\` — `clips/` = **50 H.264 clips** (h264_nvenc), 2405 MB, 21.5 min of video (10.3–99.9 s each); `index.html` (the
  review page, data embedded, works from file://), `events.json`, `event_summary.csv`, `overlay_ass/` (the exact overlay
  of each clip), `_fonts/` (DejaVu Sans), `README.md` (instructions + event table), `log.txt`.
- **Human labels go to** [`wiser/configs/imu_video_review_2026c/`](../wiser/configs/imu_video_review_2026c/README.md)
  (export format and column meanings there; commit every export, never edit one).
- The agent never opened or judged a frame; every behavioural reading is the user's. The states burnt into the clips are
  the IMU's guesses.

## What changed

- New `wiser/scripts/make_imu_video_review.py` (base Python + ffmpeg; imports unchanged:
  `analyze_imu_attitude_gate_v2` — `load_cfg`, `context`, `detect_strict`, `load_fixes`, `to_ms`;
  `cv/cv_field/grab_frames.py` — `segments` (incl. never-renamed files and the previous date folder), `probe_duration`,
  `find_ffmpeg`; `wiser_analysis_utils._rect_membership`). No existing script, config or cache was edited.
- New `wiser/configs/imu_video_review_2026c/README.md`; one row in each index README; one entry in the CLAUDE.md
  `wiser_baseline` row.

## Method (all thresholds also in the driver docstring and the page's help)

- **Events:** the 50 rows of the gate-v2 `human_checks.csv` (20 strict still windows, 20 gyro-clipped shake trains, 10
  largest-error test bouts; report §10). Clip = event start − 5 s → event end + 5 s (10.3–100 s), located by the video
  **file-name time** (field-PC); never the burnt-in OSD (≈ 59½ min behind). File-name time is good to ≈ ±1 s; the page
  lets the user shift the IMU traces and saves the offset seen. Hour boundaries: one part per segment at its own file-name
  time (the 62-s bout #41 crosses 01:00 and uses two segments per camera); frames missing in a camera show the dark canvas
  + "NO VIDEO".
- **Cameras:** WISER valid 1-s medians (A2 cache, gate-v2 masks) over the event ± 2 s (± 30 s if empty) → house rectangle
  of `wiser_rois.json` grown by 14 in: house_1 → CH08 in-box + CH05 top-down; house_2 → CH07 in-box + CH06 top-down;
  outside / no WISER → CH01 + CH02 panoramas (upright). The reason (position, per-second zone mix, core vs buffer-only) is
  stored per event and shown on the page.
- **Layout / encoding:** houses side by side 2 × 1920 × 1440 (3840 × 1656 with the banner), panoramas stacked
  2 × 3712 × 1044 (3712 × 2304); 216-px banner; 20 fps; H.264 yuv420p, faststart, GOP 1 s, `h264_nvenc` VBR cq 26
  (trial: SSIM 0.981 / 0.986 vs a cq-14 reference on an in-box / panorama sample at ~2/3 of the cq-23 size).
- **Overlay (ASS, DejaVu Sans):** rows 1–2 static — animal · tag · IR mark (coban) · IMU event + numbers / start
  (field-PC, ±1 s) · cameras · WISER zone; row 3 every 0.25 s — `IMU now: <state> · |ω| · |a|−g · field-PC time`, plus
  `▶ EVENT` inside the event span; a label per view.
- **IMU state per 0.25-s bin** (first rule that holds): SHAKE (bin overlaps a gyro-clipped shake train ± 25 ms, or gyro
  12–20 Hz band power > its animal-period 99th percentile with max |a| > 2 g) → STILL (≥ 50 % in a gate-v2 strict still
  window: acc direction < 0.3° from the window mean, ||ā| − g| < 0.03 g, |ω| < 3 °/s, ≥ 1 s; `detect_strict` on the whole
  period with the gate's candidate mask) → QUIET (**added state**: ≥ 50 % A3-quiet but not strict) → LOCOMOTION (WISER
  1-s speed ≥ 10 in/s) → RHYTHMIC 4–12 Hz (4–12 Hz ≥ 60 % of the 2–20 Hz gyro power and ≥ 400 (°/s)²) → ACTIVE; NO IMU
  when < 50 % of the samples are present and not frozen. Band power = Butterworth-4 zero-phase band-pass of each gyro
  axis, squared, summed over axes, 0.5-s centred mean (from A3).

## Deviations from the request (and why)

1. **QUIET added** to STILL / ACTIVE / SHAKE / RHYTHMIC / LOCOMOTION: resting with breathing or small head adjustments
   fails the strict still rule and would otherwise read "ACTIVE".
2. **Band powers computed from A3, per axis summed**, not read from the A4 16-Hz cache: A4's are band powers of the norm
   |ω|, which moves an oscillation's fundamental to 2f (a 15-Hz shake lands at 30 Hz, outside 12–20 Hz; self-test:
   45 000 vs 14 (°/s)²), and A4 exists for nights only.
3. **RHYTHMIC floor = 400 (°/s)², absolute** (amendment before the full run): the draft's per-period median of the
   non-quiet samples was 0.1–0.6 (°/s)² on day-sleep periods and 5 000–8 000 (°/s)² on nights, so the same head movement
   would have been labelled by time of day.
4. **Frame step = one clip frame (1/20 s)**, not 1/30 s: the clips are 20 fps, and 1/30-s steps land between frames.
5. Row 1 also shows the coban colour (useful in colour frames).

## Verification

- `python wiser/scripts/make_imu_video_review.py --selftest` → **ALL PASS (32 checks)**: classifier on synthetic 100-Hz
  signals (still → STILL, slow nod → QUIET, 6-Hz oscillation → RHYTHMIC, 16-Hz burst with |a| > 2 g → SHAKE, broadband →
  ACTIVE, WISER ≥ 10 in/s → LOCOMOTION, clipped-train span → SHAKE, frozen → NO IMU; vector vs norm band power); house
  zones and camera choice; identity per date (SF10 yellow coban after 08-31); segment parts across midnight, a never-renamed
  segment and a 2-s gap; the overlay's 0.25-s tiling, SHAKE text and EVENT tag timing; a rendered synthetic clip whose
  source frames carry their index in the luma — **320/320 output frames show the source frame of their file-name time**,
  the gap shows the empty canvas, the EVENT box appears only inside the event span, no missing-glyph warning from libass
  (checked to fire on a glyph DejaVu lacks); the page's JavaScript passes `node --check`.
- Headless Edge smoke test of the page (no screenshots; errors + scripted actions written into the DOM): every event
  loads and draws, keyboard shortcuts fill the form, filters and export rows work, no JavaScript error.
- Full run: `python wiser/scripts/make_imu_video_review.py --cohort 2026c --workers 3` → 50/50 clips, 0 libass glyph warnings, every probed clip duration = its span (± 0.05 s), `index.html` 2.2 MB passes `node --check`; wall 13.0 min (HDD-bound reads of the hourly files on `F:`; CPU ≈ 6 %). Headless Edge decodes and seeks both layouts (3840 × 1656 house clips #1, #41, #5; 3712 × 2304 panorama clips #21, #12; H.264 High@5.1). A 4-event trial before it (scratchpad) fixed the encoder quality and the RHYTHMIC floor.

## Results (what the IMU says; for the user to check)

Per animal (times field-PC `MM-DD HH:MM`; zone h1 = house_1 → CH08 + CH05, h2 = house_2 → CH07 + CH06, out = CH01 + CH02 panoramas; the IMU state is the share of 0.25-s bins inside the event span). Full table: the run's `README.md` / `event_summary.csv`.

| animal | strict STILL windows (IMU: STILL 100 % in every one) | gyro-clipped SHAKE trains (IMU: SHAKE 100 % in every one) | largest-error bouts (IMU state mix) |
|---|---|---|---|
| SF07 | #1 09-11 11:09 h2; #2 09-08 11:59 h2; #3 09-08 22:12 h2; #4 09-10 23:19 h2 | #24 09-08 22:35 out | #44 09-10 22:56 h2 (ACTIVE 75 %, QUIET 14 %, STILL 8 %, RHYTHMIC 4–12 Hz 2 %); #46 09-10 23:12 h2 (ACTIVE 74 %, QUIET 16 %, RHYTHMIC 4–12 Hz 7 %, STILL 1 %, LOCOMOTION 1 %, SHAKE 1 %) |
| SF08 | #5 09-08 17:09 h1; #6 09-11 12:11 h2; #7 09-09 00:55 h2; #8 09-09 01:01 h2 | #21 09-10 22:08 out; #23 09-10 21:47 out; #25 09-08 22:57 out; #32 09-11 02:02 out; #36 09-10 23:47 out; #38 09-08 22:45 out | #41 09-11 00:59 h2 (ACTIVE 54 %, QUIET 37 %, RHYTHMIC 4–12 Hz 5 %, STILL 4 %, LOCOMOTION 0 %); #45 09-11 16:54 h2 (QUIET 73 %, ACTIVE 21 %, STILL 6 %) |
| SF09 | #9 09-08 13:45 h2; #10 09-08 10:37 h2; #11 09-09 02:49 h2; #12 09-08 22:34 out | #33 09-08 21:48 h2 | #42 09-11 10:51 h2 (STILL 49 %, QUIET 27 %, ACTIVE 22 %, RHYTHMIC 4–12 Hz 2 %); #43 09-11 10:45 h2 (ACTIVE 98 %, STILL 2 %); #48 09-11 15:54 h2 (ACTIVE 81 %, STILL 19 %); #49 09-11 10:44 h2 (ACTIVE 98 %, STILL 2 %); #50 09-11 15:53 h2 (ACTIVE 85 %, STILL 7 %, RHYTHMIC 4–12 Hz 4 %, LOCOMOTION 2 %, QUIET 2 %) |
| SF10 | #13 09-11 15:47 h2; #14 09-11 14:22 h2; #15 09-11 01:33 h2; #16 09-10 21:44 h2 | #22 09-08 21:18 out; #26 09-08 21:46 out; #27 09-11 03:53 out; #28 09-11 03:19 out; #29 09-08 21:31 out; #30 09-09 03:11 out; #31 09-09 03:42 out; #39 09-09 00:54 out; #40 09-09 01:42 out | — |
| SF12 | #17 09-11 12:21 h2; #18 09-08 11:33 h1; #19 09-09 00:24 out; #20 09-09 00:25 out | #34 09-11 03:59 out; #35 09-10 23:05 h1; #37 09-10 22:56 h2 | #47 09-11 15:02 h2 (STILL 61 %, ACTIVE 28 %, QUIET 7 %, RHYTHMIC 4–12 Hz 3 %, SHAKE 1 %) |

Camera choice: CH07 in-box + CH06 top-down 27, CH01 + CH02 panoramas 20, CH08 in-box + CH05 top-down 3. Every still window except three (SF09 #12, SF12 #19/#20: outside) and two (SF08 #5, SF12 #18: house_1) sits in house_2; 17 of 20 shake trains are outside the houses (panoramas), SF09 #33 and SF12 #37 in house_2, SF12 #35 in house_1; all 10 bouts are in house_2. No clip has a camera without frames; only bout #41 crosses an hour boundary (two segments per camera).

## Open / next

- The user reviews the 50 clips in `index.html`, exports JSON + CSV into `wiser/configs/imu_video_review_2026c/`.
- Nothing is promoted from these clips until those labels exist; then the IMU state rules (and the gate-v2 still / shake
  classes) can be scored against them.
