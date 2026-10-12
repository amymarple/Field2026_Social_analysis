# Human video verdicts on the IMU-WISER consistency audit's events — cohort 2026c

**Human labels: commit every export here; never edit or delete one.** A correction is a new export; the newest file per
reviewer wins, and older ones stay for the record.

## Where they come from

`wiser/scripts/make_wiser_event_review.py` (plan
[`implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md`](../../../implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md)
Part 2, change log [`change_log/2026-10-05-wiser-event-review.md`](../../../change_log/2026-10-05-wiser-event-review.md)) cut
one clip per event of the IMU-WISER consistency audit (run `D:\Field2026_analysis_out\2026c\wiser_imu_consistency_20261005_2038`,
V3 track): the 30 largest I1 ("WISER moved ≥ 12 in while the head IMU saw no locomotion"), the 30 largest I2 ("the WISER
path turned ≥ 90° while the head turned < 20°") and 20 random I1 (5 per size quartile). The review page is
`D:\Field2026_analysis_out\2026c\wiser_event_review_<ts>\index.html` (off-repo, next to its `clips/` and `panels/`). It is
**blind**: the clip banner shows only the animal, its IR mark and coban colour, the zone, the cameras and the field-PC
clock; the WISER / IMU panel and the event's numbers appear only after a verdict is saved. The person judges the frames;
the agent never does.

**GUI v2 (WISER circles, 2026-10-06;** plan
[`implementation_plan/2026-10-06-wiser-event-review-circles.md`](../../../implementation_plan/2026-10-06-wiser-event-review-circles.md),
change log [`change_log/2026-10-06-wiser-event-review-circles.md`](../../../change_log/2026-10-06-wiser-event-review-circles.md)):
the same 80 events, W ids and order, built with `--circles`. Before the first answer the clip shows a static dashed
circle at the start position (14 in around where the rat was before the event, from WISER, projected into each camera).
After the first answer the clip is swapped for one with the moving WISER circle (V3 track), the raw fix as a dot and
the start circle, and a second question opens. **Map caveat:** the WISER → paddock map was accepted on one hour of CH01
(2026-09-06 21–22 h) only. If the start circle is not on the rat at the onset, the map is off for that clip, not WISER;
the reviewer ticks "start circle off" (`map_flag`). Answers stored in v1's browser storage do not carry over (the
storage key is per run). Export them from v1 first; **Import** of a v1 export into v2 works because the W ids are the
same.

**GUI v3 (circles on all eight cameras, day and night, 2026-10-12;** plan
[`implementation_plan/2026-10-12-wiser-event-review-v3.md`](../../../implementation_plan/2026-10-12-wiser-event-review-v3.md)
+ its Amendment 1, change log
[`change_log/2026-10-12-wiser-event-review-v3.md`](../../../change_log/2026-10-12-wiser-event-review-v3.md); page
`D:\Field2026_analysis_out\2026c\wiser_event_review_20261012_1054\index.html`): the same 80 events, W ids and order, built
with `--v3`.
- Circles are drawn on every camera that maps: CH01–CH08, including CH05 and the in-box CH07 / CH08.
- In the in-box views the 14-in circle is wider than the house floor; a `+` marks its centre.
- Frames with a house lid open or with no camera correction get no circle; the clip says so.
- Open-field corner events show CH03 or CH04 in place of one panorama.
- After the first answer the clip also shows the **other tagged rats** as thin cyan circles with their id.
- Each camera line gives the map status: CH01 / CH02 = that night's WISER pixel-kit validation; CH03–CH08 = "map
  validated on CH01 only".
- CH01–CH04 still use the nearest night correction outside 21:00–04:20, flagged in the clip.
- **Answers from v2 carry over:** Import the v2 JSON export into the v3 page (same W ids). Each imported judgement gets
  `imported_from` = `"<gui> <run_id>"` of the file it came from. An event that newly has a circle asks the circle
  question again (status `revealed`).

## Student copy on the H: drive — PAUSED 2026-10-07 (incomplete; the user scores first)

Target `H:\wiser_event_review_2026c_student\` (SanDisk Extreme 2 TB external SSD, exFAT; `H:\wiser_label_loop\` on the same
drive belongs to another session). The copy was **stopped by the user** at 2026-10-07 15:54: only `clips\` is there, **32 of
80 files (2.24 GB of ≈ 11 GB; the last one may be partial)**, plus an empty `exports\`. Missing: the rest of `clips\`, all of
`clips_reveal\` and `panels\`, `index.html`, `START_HERE.html`. To finish later:
1. `robocopy <run>\clips <dst>\clips /E` (re-copies the partial file), the same for `clips_reveal` and `panels`, and copy
   `index.html`, with `<run>` = `D:\Field2026_analysis_out\2026c\wiser_event_review_20261006_1637`. Do **not** copy
   `selection.csv`, `event_summary.csv`, `events.json` or the run README — they reveal which events are the largest.
2. In the copied `index.html` set `"run_id"` to `wiser_event_review_20261006_1637_student` (own browser-storage key) and replace
   the help sentence "Verdicts autosave … --with-verdicts)." by an instruction to move the exports into `exports\`.
3. Copy [`STUDENT_INSTRUCTIONS.html`](STUDENT_INSTRUCTIONS.html) to `<dst>\START_HERE.html`.
4. Verify it stands alone: every referenced clip / reveal / panel present with the source's byte size, every mp4 probes as
   H.264, no network URL or absolute-path resource in the page, and `msedge --headless=new --dump-dom file:///H:/…/index.html`
   renders all 80 W ids. Student exports come back in `exports\` and are committed here like any other export.

## File naming

The page's **Export JSON** / **Export CSV** buttons write `wiser_event_review_2026c_<reviewer>_<YYYYMMDD_HHMM>.{json,csv}`.
Copy both into this folder unchanged. `wiser_event_review_2026c_placeholder.json` is an empty file with the export schema
(no rows); readers skip files whose `rows` list is empty.

## Format

JSON (`schema: wiser_event_review_labels/1`): `cohort`, `run_id` (the review run folder name), `run_dir`, `tool`, `plan`,
`audit_run`, `selection` (seed, quartile edges, pool sizes), `exported_local`, `reviewer`, `n_events`, `n_saved`, `rows`
(one per event, the CSV columns) and `judgements` (keyed by review id, as stored by the page).

CSV columns, one row per event:

| column | meaning |
|---|---|
| `review_id`, `idx` | neutral review id `W01` … `W80` (random order, seed 20261006) |
| `type` | `I1` (place question) or `I2` (turn question) |
| `animal`, `event_key`, `audit_event_id`, `track` | the audit event: `event_key` = `<animal>\|V3\|<type>\|<event_id>` joins to the audit's `tables/events.csv.gz` (`animal`, `track`, `type`, `event_id`) |
| `selection`, `selection_rank`, `size_quartile` | `top` (rank among the 30 largest) or `random` (V3 I1 size quartile 1–4) |
| `onset_local`, `end_local`, `onset_al_ms`, `end_al_ms` | the event window on the audit's aligned clock t_al = t_WISER − τ* (the head-IMU / field-PC clock; Unix ms) |
| `clip`, `clip_ok`, `zone`, `cameras` | the clip file and the cameras chosen by zone |
| `question` | the question shown |
| `verdict` | = `verdict_blind` (the column name the return test's `--with-verdicts` reader looks for); empty = not saved |
| `verdict_blind`, `reason_blind` | **the first saved verdict, given before the panel was revealed** — use this one |
| `verdict_final`, `reason_final` | the answer at export time (differs only if changed after the reveal) |
| `changed_after_reveal`, `n_changes_after_reveal` | whether / how often the answer changed after the reveal |
| `note`, `saved_at`, `revealed_at`, `reviewer`, `updated`, `status` | free text; ISO UTC times; who; `todo` / `partial` (answered, not saved) / `done` (saved); GUI v2 adds `revealed` (verdict saved, circle question still open) |
| `circle_verdict` (GUI v2 only) | the answer to "Does the WISER circle stay on the rat?", given **after** the reveal: `on_rat` / `drifts_off` / `cannot_tell`; `no_circle` = set by the page when the reveal clip has no WISER circle on either camera (no projection — not a reviewer answer); empty = not answered |
| `circle_at` (GUI v2 only) | ISO UTC time of the circle answer |
| `map_flag` (GUI v2 only) | `true` = the reviewer ticked "start circle off" (the dashed start circle is not on the rat at the onset → the WISER → paddock map, not WISER, is off for this clip); `false` = not ticked; empty = no start circle on either camera |
| `circle_available`, `start_circle_available` (GUI v2 only) | whether the reveal clip has a moving circle / the blind clip a start circle on at least one camera |
| `reveal_clip` (GUI v2 only) | the reveal clip file in the run's `clips_reveal/` |

Answers: I1 `moved` / `stayed` / `cannot_tell`; I2 `turned` / `ran_straight` / `cannot_tell`. Reasons (only with
`cannot_tell`, optional): `not_visible` / `identity_unsure` / `other`.

GUI v2 exports keep `schema: wiser_event_review_labels/1` (the columns above are added at the end; the v1 columns are
unchanged) and add `gui: "v2 (WISER circles)"` and `circles` (`plan`, `map_run`, `map`, `caveat`) to the JSON.

GUI v3 exports have the same schema and the same columns as v2. They differ in three ways:
- `gui: "v3"`.
- `circles.plan` = the v3 plan, and `circles.caveat` = the v3 caveat (with the pixel-kit validation range).
- A judgement imported from an earlier export carries `imported_from` in `judgements`.

In v3, `circle_verdict` was answered while the other tagged rats were visible as cyan circles.
`circle_available` / `start_circle_available` count every camera, CH05–CH08 included. Several v2 `no_circle` events
now have a circle.

## How to use them

- The verdicts are the ground truth for the return test (Part 1, `analyze_wiser_i1_return.py --with-verdicts <file>`):
  I1 `moved` ↔ relocate, `stayed` ↔ return; `cannot_tell` rows are excluded. No threshold is re-tuned on them.
- Use `verdict_blind`; report how many verdicts changed after the reveal.
- `circle_verdict` is a separate, post-reveal judgement of the projected WISER track. It is never the return test's
  ground truth. Exclude `map_flag = true` clips before reading it as a statement about WISER, because there the map
  (accepted on one CH01 hour) is off. `no_circle` is not an answer.
- **v3 caveats for `circle_verdict`:**
  - Inside a house WISER gives the roster, not the position in the pile. On CH07 / CH08 the circle is wider than the
    floor.
  - A camera line that reads "FAILS" or "not validated" means the map itself is uncertain for that clip.
  - Keep the GUI version (`gui`) and `imported_from` with every verdict you use.
- Clip time is the video file-name time (field-PC, ±1 s); the burnt-in camera clock (≈ 59½ min behind) is never used.
