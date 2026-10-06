# Event-review GUI v2: WISER circles drawn on the clips (cohort 2026c)

**Status:** PLANNED 2026-10-06. **Approval:** the user (2026-10-06): "先用wiser把老鼠圈出来这样我好看" — circle the rat with
WISER so the clips are easy to judge. A viewing-aid change to Part 2 of
`implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md`; no new test. Operational details **[op]**.
**Driver:** extend `wiser/scripts/make_wiser_event_review.py` (new flag `--circles`, default on for new runs); reuse the
projection code of `cv/cv_field/wiser_assist_p0.py` (WISER → paddock similarity map; Newton inverse of
`Corrections("2026c").to_paddock`, as used by its `--clips`).

## Facts (not re-derived)

- GUI v1: `D:\Field2026_analysis_out\2026c\wiser_event_review_20261005_2236\index.html` — 80 events W01–W80 (30 largest I1,
  20 random I1, 30 largest I2; seed 20261005), blind overlay, panel after the first answer (`verdict_blind`).
- WISER → paddock: similarity map from WISER-assisted YOLO P0 (`implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md`;
  `mapping.json` in its run): paddock = s R(θ)(WISER − c) + c + d, d = (−272.85, −605.80) in, θ 0.11°, s 0.963, lag 0 s;
  **accepted on one hour of CH01 (09-06 21–22 h), test median residual 4.39 in** — other nights and CH02 are extrapolations.
- Paddock → pixel: `cv/cv_field/frame_correction.py` `Corrections("2026c").to_paddock(cam, t, uv, z_mm=60)` (cohort px →
  09-18 px → 09-24 calibration), inverted numerically; nights hourly for CH01–CH06; CH05 (house_1 moved 09-18) and CH07/CH08
  (uncalibrated) are refused by `to_paddock`; whole-field cameras are corrected only at night.

## What changes

1. **Circles.** For every clip frame time (0.25-s overlay grid), the WISER position of the reviewed animal is mapped
   WISER → paddock → camera pixel and drawn as the projected **14-in circle** (a ring of paddock points mapped to pixels):
   - **Blind phase (first answer):** only a **static dashed circle at the pre-event position** P0 (the I1 reference /
     I2 window start; where the rat was) — it helps find the right rat without showing WISER's excursion. Label "start".
   - **Reveal phase (after the first answer):** the clip is replaced by a version with the **moving WISER circle** (V3
     track, solid) and the raw fix as a small dot, plus the static start circle, and a **second question**: "Does the WISER
     circle stay on the rat?" → *on the rat* / *drifts off the rat* / *cannot tell*. Saved as `circle_verdict`.
2. **Where no projection exists** (CH05 house_1, CH07/CH08 in-box, frames outside a camera's verified support, day frames
   without a correction **[op: day frames use the nearest night correction, flagged on screen]**): no circle; an on-screen
   note "no projection — use the IR mark"; the other camera of the pair may still have one.
3. **Same events, same W ids, same order**, new output folder `D:\Field2026_analysis_out\2026c\wiser_event_review_<ts>\`;
   export format unchanged plus `circle_verdict` (Part 1's reader keeps using `verdict_blind` / `verdict`).
4. **Map caveat on screen and in the README:** the map was accepted on one CH01 hour; if the start circle is not on the
   rat at onset, the map (not WISER) is off for that clip — the user can tick "start circle off" (saved as `map_flag`).

## Checks (the agent never judges a frame)

- Round trip pixel → paddock → pixel ≤ 1 px on a grid for every projected camera; inverse convergence rate per clip.
- Projection coverage table: per event and camera, share of frames with a circle; list of events with no circle at all.
- `--selftest`: synthetic camera model + map → circle placement, the static/moving split between phases, the export
  fields, and the "no projection" branch.

## Outputs

New run folder with `clips/` (blind, start circle), `clips_reveal/` (moving circle), `panels/`, `index.html`,
`projection_coverage.csv`; `change_log/2026-10-06-wiser-event-review-circles.md`. The main session updates CLAUDE.md and the
index READMEs and commits. GUI v1 stays as is (answers saved in v1's browser storage do not carry over — export them first).
