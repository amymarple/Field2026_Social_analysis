# Human video judgements of head-IMU events — cohort 2026c

**Human labels: commit every export here; never edit or delete one.** A correction is a new export; the newest file per
reviewer wins, and older ones stay for the record.

## Where they come from

`wiser/scripts/make_imu_video_review.py` (plan `implementation_plan/2026-10-01-imu-video-review.md`, change log
`change_log/2026-10-01-imu-video-review.md`) cut one clip per head-IMU event and burnt the IMU's guess into the top of each
frame. The events are the 50 suggested human checks of the attitude gate v2 (20 strict still windows, 20 gyro-clipped
shake trains, 10 largest-error test bouts; report
`results/2026c/wiser_baseline/reports/wiser_baseline_imu_attitude_gate_v2_2026c.md` §10). The review page is
`D:\Field2026_analysis_out\2026c\imu_video_review_<ts>\index.html` (off-repo, next to its `clips/`). The person judges
the frames; the agent never does.

## File naming

The page's **Export JSON** / **Export CSV** buttons write `imu_video_review_2026c_<reviewer>_<YYYYMMDD_HHMM>.{json,csv}`.
Copy both into this folder unchanged.

## Format

JSON (`schema: imu_video_review_labels/1`): `cohort`, `run_id` (the review run folder name), `run_dir`, `tool`,
`exported_local`, `reviewer`, `n_events`, `n_done`, `rows` (one per event, same columns as the CSV) and `judgements`
(keyed by event id, as stored by the page).

CSV columns, one row per event:

| column | meaning |
|---|---|
| `id` | event id `E<nn>_<still/shake/bout>_<SFxx>_<MMDD>_<HHMMSS>` (row number of `human_checks.csv`, type, animal, start) |
| `idx`, `animal`, `type`, `period`, `start_local`, `end_local` | the event (field-PC local time, EDT) |
| `clip`, `cameras`, `wiser_zone` | the clip file and the cameras chosen from the WISER zone |
| `imu_event`, `imu_dominant_state`, `imu_state_fractions` | what the IMU said (event + numbers; share of 0.25-s bins per state inside the event span) |
| `imu_correct` | reviewer: `yes` / `no` / `cant_tell` |
| `behaviours` | reviewer, `;`-separated, any of `still` (still / sleeping), `wetdog`, `headshake`, `grooming`, `scratching`, `locomotion` (walking / running), `rearing`, `digging`, `eating`, `interacting`, `other` |
| `identifiable` | reviewer: `yes` (the labelled rat) / `another_rat` (a rat is in view, not sure it is this one) / `not_visible` |
| `offset_s` | reviewer (optional): video time − IMU time in s (positive = the video shows the behaviour later than the IMU says); empty = not judged |
| `notes`, `reviewer`, `updated`, `status` | free text; who; ISO time of the last edit; `todo` / `partial` / `done` |

## How to use them

- Rows with `identifiable` ≠ `yes` say nothing about the IMU label (the rat was not confirmed in view).
- `imu_correct` judges the IMU event label; the per-0.25-s states in the banner are guesses with the thresholds listed
  in the driver docstring and the page's help.
- Clip time is the video file-name time (±1 s); `offset_s` collects what the reviewer saw.
