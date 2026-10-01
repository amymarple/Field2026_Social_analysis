# Head-IMU video-review GUI: clips with the IMU's guess burnt in, a local review page, human labels (cohort 2026c) — 2026-10-01

**Request (user, 2026-10-01):** "make video clips and on the top of the frame show what you think the animal is doing
from shake or still. also tell me what animal is doing what. i need gui for this". The user judges every frame; the
agent never opens or judges an image.

## Scope

- **Events:** the 50 rows of the gate-v2 `human_checks.csv`
  (`D:\Field2026_analysis_out\2026c\imu_attitude_gate_v2_20261001_0847\`; 20 strict still windows, 20 gyro-clipped shake
  trains, 10 largest-error test bouts; also in the gate-v2 report §10). Animals SF07–SF10, SF12 (SF11's implant and tag were
  off from 09-07; the rat is still in the paddock, untracked).
- **One clip per event**, event start − 5 s → event end + 5 s, field-PC time from the video file names (local copy
  `F:\3rd_rat\<date>\<CH>\`, read-only; segment lookup incl. never-renamed files via `cv/cv_field/grab_frames.py`
  `segments()`; never the burnt-in OSD). File-name time is good to about ±1 s; the GUI records the offset the user sees.
- **Camera choice (automatic, explained per event):** WISER 1-s medians of the animal's valid fixes (A2 cache
  `wiser_fix_cache/{night,day}_<date>/<SFxx>.csv.gz`, masks as in gate v2) over the event ± 2 s (widened to ± 30 s if
  empty) → zone by the house ROIs of `wiser/configs/wiser_rois.json` grown by 14 in (`wiser_analysis_utils._rect_membership`,
  the calibration pilot's rule): house_1 → CH08 in-box + CH05 top-down; house_2 → CH07 in-box + CH06 top-down; outside or
  no WISER → CH01 + CH02 panoramas (upright = 90° counter-clockwise).
- **Layout:** houses side by side at equal height (2 × 1920 × 1440 = 3840 wide); panoramas stacked (2 × 3712 × 1044); a
  216-px dark banner on top (total height ≤ 2304, the common H.264 hardware-decoder limit); 20 fps constant; H.264
  yuv420p + faststart; `h264_nvenc` (works on this PC; VBR cq 26, chosen in the trial: SSIM 0.98–0.99 vs a cq-14
  reference at ~2/3 of the cq-23 size) with `libx264 -preset veryfast` as fallback.
- **Overlay** (ASS via the ffmpeg `subtitles` filter, DejaVu Sans so that ω ° − ▶ render): row 1–2 static (animal, tag,
  IR mark + coban, IMU event + key numbers, event time field-PC, cameras, WISER zone); row 3 dynamic every 0.25 s
  ("IMU now: <state> · |ω| · |a|−g · field-PC time", "▶ EVENT" inside the event span); small camera labels per view;
  "NO VIDEO" where a camera has no frames.
- **IMU state per 0.25-s bin** (the IMU's guess; priority order; all thresholds in the driver docstring and the GUI):
  1. `SHAKE` — bin overlaps a clipped shake train (gate-v2 `sat_runs.csv.gz`, class `shake_train`, span ± 25 ms) OR
     (gyro 12–20 Hz band power > its 99th percentile in that animal-period AND max |a| > 2 g in the bin);
  2. `STILL` — ≥ 50 % of the bin inside a gate-v2 strict still window (`detect_strict` imported unchanged: 0.1-s acc
     direction within 0.3° of the window mean, | |ā| − g | < 0.03 g, |ω| < 3 °/s, ≥ 1 s), run on the whole period with the
     gate's candidate mask;
  3. `QUIET` — **added state:** A3 1-s quiet rule (median |ω| < 10 °/s, | median |a| − g | < 0.05 g) on ≥ 50 % of the bin but
     not strict-still (resting with small movements; otherwise such bins would read "ACTIVE");
  4. `LOCOMOTION` — WISER 1-s speed (median `speed_inps_smooth` of valid fixes) ≥ 10 in/s;
  5. `RHYTHMIC 4–12 Hz` — gyro 4–12 Hz band power ≥ 60 % of the 2–20 Hz power AND ≥ 400 (°/s)² (RMS 20 °/s; could be
     grooming, scratching, sniffing — never named as such). *Amended during the 4-event trial (before the full run):* the
     first draft used the animal-period median of the non-quiet samples as the floor; it was 0.3 (°/s)² on a day-sleep
     period and ≈ 6 500 (°/s)² on a night, so the same head movement would have been labelled by time of day;
  6. `ACTIVE` — anything else; `NO IMU` for frozen / missing samples.
  Band powers: Butterworth-4 zero-phase band-pass of each gyro axis, squared, summed over axes, 0.5-s centred mean
  (bands 2–4, 4–8, 8–12, 12–20 Hz) from the A3 100-Hz cache. **Deviation:** the A4 16-Hz cache's band powers are not
  used — they are band powers of the norm |ω|, which moves an oscillation's fundamental to 2f (a 15-Hz shake → 30 Hz,
  outside 12–20), and A4 exists for nights only.
- **GUI:** one `index.html` next to `clips/` (works from file://; data embedded): event list (type, animal, time,
  status) | `<video>` with play/pause, step (←/→ 1/30 s, Shift 1 s), speed 0.25–2× and a canvas (state bar, |ω|, |a|−g,
  band powers, event span, cursor synced to the video, IMU shift by the offset the user enters) | judgement form (IMU
  label correct? / what is THIS rat doing (multi) / labelled rat identifiable? / offset seen / notes), keyboard
  shortcuts, autosave (localStorage, try/catch), Export JSON + CSV, Import; identity-cue table
  (`wiser/configs/rat_identities_2026c.csv`) and the camera-choice reason per event.

## Files

- New `wiser/scripts/make_imu_video_review.py` (base Python; imports `analyze_imu_attitude_gate_v2` (detect_strict,
  context, load_cfg, load_fixes), `cv/cv_field/grab_frames.py` (segments, find_ffmpeg), `wiser_analysis_utils`
  (`_rect_membership`) — none of them edited). `--selftest`: synthetic clip (overlay timing), classifier on synthetic
  signals, HTML generated and its JS passes `node --check`.
- Output off-repo `D:\Field2026_analysis_out\2026c\imu_video_review_<ts>\` (`clips/`, `index.html`, `events.json`,
  `README.md`, `log.txt`).
- New `wiser/configs/imu_video_review_2026c/README.md` — home of the user's exported judgements (human labels; the
  main session commits them).
- `change_log/2026-10-01-imu-video-review.md` after; one top row in each index README; one entry in the CLAUDE.md
  `wiser_baseline` row.

## Not in scope

No behavioural claim, no change to any existing script or cache, no git commit. The states are the IMU's guesses for the
user to check; nothing is promoted until the user's labels exist.
