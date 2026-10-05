# Video frames on the ephys / PC clock: per-camera clocks from the burned-in OSD, offsets from the head IMU (cohort 2026c)

**Status: PLAN / handoff** (2026-10-05; written by the recording repo's calibration session at the operator's request,
"写handoff放analysis repo 也同步到sync repo"). Nothing implemented here yet. Cohort 3 is over: everything below works
on recorded data only.

## Why

Place-cell and video-ephys analyses need every video frame on the ephys clock. A timing error dt moves a running
rat by v x dt: 33 ms is 1.7-3.3 cm at 50-100 cm/s, more than the frozen camera calibration's own error (18 / 55 mm per
cell, `Field_2026_Social_Recording/calibration_qc/CALIBRATION_FINAL_2026-10-04.md`). Today video is tied to the PC
clock only to about +-1 s.

## What is recorded (facts)

- Video (CH01-CH08 via the NVR, RTSP, `Field_2026_Social_Recording/rtsp_record.ps1`): ffmpeg `-c copy`
  `-use_wallclock_as_timestamps 1 -f segment -segment_atclocktime 1 -reset_timestamps 1`. So each frame's stored
  timestamp is the PC wall-clock time the frame ARRIVED, reset to 0 at the start of each hourly file; the file's
  absolute start is only in its name, to 1 s (truncated). Arrival times are bursty: 0.04-0.09 s rms off a steady
  clock, up to 0.57 s (calibration_qc/README.md, "The ball sweep at 20 Hz"). Frame index / rate is the better time
  base inside a file. Rates: CH01 / CH02 / CH05 / CH06 19.997-20.001 fps, CH03 / CH04 19.983-19.985 (~3 s per hour slow).
- Every frame carries the camera's burned-in OSD clock (`dd/mm/yyyy HH:MM:SS DDD`, 1 s resolution), ~59 min behind the
  PC and drifting (-59:40 on 09-10, -59:25 on 09-18, about -59:27 on 09-30, and differing between cameras by up to
  0.4 s - below). Text box (stored-frame pixels, x0-x1, y0-y1):
  CH01 / CH02 1950-2160, 3700-4500 (panos stored 2160 x 7680, the text along the right edge); CH03 / CH04 2150-2700,
  20-150 (4512 x 2512); CH05 / CH06 1240-1530, 5-75 (2560 x 1920). Not checked for CH07 / CH08 / thermal.
- Sync LED (1 Hz, PC-driven): visible in **CH02 only** (operator, 2026-10-04). Its log is one line per second (PC send
  time to the ms; daily mean send lag 0.6-2.8 ms). The video half of the LED pipeline (field2026-sync
  `from-field/2026-09-03_led_sync_pipeline.py`, `video-fit`) has never been run on real footage; the LED's pixel
  position in CH02 is not recorded; the log records the command, not the light (dark on 09-16 while logging).
- Ephys -> PC: done for all 494 sessions (`ephys/pc_time_chain.py`), 8-22 ms typical, up to 60 ms, plus an unmeasured
  constant BLE latency (est. <= 50 ms). Head IMU -> PC: same file and clock as ephys (`ephys/make_imu.py`, 203
  sessions, 1,372 h). IMU <-> WISER: +0.10 .. +0.20 s lag, one night (`wiser/scripts/analyze_imu_wiser_calibration.py`).
  IMU <-> video: review clips with a hand-entered offset (`wiser/scripts/make_imu_video_review.py`), no labels yet.
- Full anchor inventory, clock-event list and traps: `F:\calibration\qc\audit\SYNC_ANCHORS_SUMMARY_2026-10-04.md`
  (lab PC).

## Measured 2026-10-04: the OSD clocks tick on their own

`Field_2026_Social_Recording/calibration_qc/osd_tick_test.py` (commit 3b8ce31 and its docstring follow-up). On the
2026-09-30 ball session, where each camera's offset to CH02 is known from the 20 Hz ball (`ball_sync20.py`), the OSD's
seconds tick is found automatically (binarised text box, > 0.4 % of its pixels change, at most one tick per 0.6 s):
523-534 ticks in 520 s per camera, i.e. one per second, none missed. Tick phase on the ball's common clock, minus
CH02's:

| CH04 | CH06 | CH05 | CH01 | CH03 |
|---|---|---|---|---|
| +2 ms | -22 ms | +218 ms | -250 ms | -409 ms |

Per-camera residual p90 13-208 ms around its own phase; the phase itself is fixed to a few ms by ~500 ticks.
Reading: **each camera's OSD is a continuous clock of its own** - it removes the +-1 s per-file offset of the file
names - but **the cameras' OSD clocks differ by up to 0.4 s**, so every camera needs its own offset to the PC / ephys
clock (one per camera, per day if its clock drifts or is re-set), not one per hourly file.

## Proposed pipeline

**S1 - per camera, per hourly file: frame index -> camera-OSD time.** Decode short windows (e.g. the first and last
60 s of each file, plus one in the middle) - full decoding of the 8K panos over the cohort would be hundreds of CPU
hours. In each window: OSD ticks (as the test), the HH:MM:SS read once per window (OCR or a digit template: the font
is fixed per camera) for the integer second. Fit per file: t_osd(i) = a + i / r (r from the ticks across the file;
check against the timestamps' slope). Output: one table, `camera, file, n_frames, a, r, tick residual, windows used`.
Gate: residual p90 < 60 ms per window; files with gaps (restarts) split.

**S2 - per camera, per day: camera-OSD time -> ephys / PC time, from the head IMU.** For a rat whose identity is known
in a camera's track (the tracking's ID), cross-correlate the IMU gyro's yaw rate (already in PC time, bias-corrected
by the IMU work) with the head-direction rate from the video keypoints (nose / ears); lag search +-2 s; use active
stretches only (the gyro's |yaw rate| above a threshold). One offset per camera per day = the median over its
stretches; report the peak / side-lobe ratio and the spread between stretches. Because the IMU is on the ephys clock,
this ties video to ephys directly - it bypasses the LED, the PC-drift sign convention and the unmeasured BLE latency.
Gate (pre-register before running): within-day spread of the stretch offsets < 30 ms; the result stable day to day
except at known clock events (PC steps 08-30 .. 09-03, NVR / camera clock re-sets - find them as jumps of the OSD-PC
difference).

**S3 - checks.** (a) CH02 against the LED (needs the LED's pixel position and the pipeline fixes: 20 fps not 25; the
drift log stores NTP - PC, the pipeline wants PC - true); agreement < 30 ms. (b) The same rat in two cameras' overlap:
the pairwise lag from the tracks must equal the difference of the two cameras' S2 offsets (< 50 ms). (c) The 09-30
OSD phases above as the reference for the cameras' relative offsets on that day. (d) WISER as a coarse check only
(its own +0.15 s lag).

**S4 - deliverable.** A per-frame time function per camera and file (`t_ephys = f_cam,day(t_osd(i))`) with its error
budget, consumed by the tracking and place-cell code; a change_log entry with the gates' outcomes.

## Open items and traps (from the sync summary)

- The PC clock's forward steps (08-30 +2.31 s, 08-31 +2.42 s, 09-01 +2.55 s, 09-03 +1.28 s) and BSOD gaps; 12 ephys
  sessions span a step.
- LED logs for 08-30 and 09-11 19:00-24:00 only on the field PC's E:; the 09-28 copy request (`E:\led_sync`,
  `E:\recording_qc`) is open. 09-16 LED invalid, 09-17 unknown.
- CH02 had 25 gaps (~100 min) plus the 6-h stop on 08-31; dropped frames never audited; 105 files without a closing
  time in the name; the weekly NVR reboot (09-06 ~14:00).
- CH07 / CH08 / thermal: nothing but the file name.
- The tracking must time frames by index within a file (S1), never by the stored arrival timestamps.

## Cost

S1: a few CPU hours (windows only) + a digit reader. S2: once per camera-day where an identified rat is tracked with
head keypoints; minutes of compute. S3: the LED video-fit (pixel position + two fixes) and the overlap check reuse
existing code. The calibration session can build S1 in the recording repo if asked; S2 belongs here (IMU, tracking).
