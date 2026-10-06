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
| `note`, `saved_at`, `revealed_at`, `reviewer`, `updated`, `status` | free text; ISO UTC times; who; `todo` / `partial` (answered, not saved) / `done` (saved) |

Answers: I1 `moved` / `stayed` / `cannot_tell`; I2 `turned` / `ran_straight` / `cannot_tell`. Reasons (only with
`cannot_tell`, optional): `not_visible` / `identity_unsure` / `other`.

## How to use them

- The verdicts are the ground truth for the return test (Part 1, `analyze_wiser_i1_return.py --with-verdicts <file>`):
  I1 `moved` ↔ relocate, `stayed` ↔ return; `cannot_tell` rows are excluded. No threshold is re-tuned on them.
- Use `verdict_blind`; report how many verdicts changed after the reveal.
- Clip time is the video file-name time (field-PC, ±1 s); the burnt-in camera clock (≈ 59½ min behind) is never used.
