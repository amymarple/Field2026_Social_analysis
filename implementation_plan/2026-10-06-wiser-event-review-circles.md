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

## Amendment 1 (2026-10-06, implementation; written before any circle verdict exists)

Places where the plan was ambiguous or could not be followed literally. Each entry gives the closest faithful choice.

1. **`--circles` is an opt-in flag.** The plan says "default on for new runs"; the task said "add `--circles`, keep v1
   reproducible without it". Without the flag the driver rebuilds v1: overlays, `selection.csv` and `events.json` are
   identical to `wiser_event_review_20261005_2236` (checked on all 80 events). The page template gained the v2 code
   paths, which stay inactive unless the data carry `circles`. New runs are documented with `--circles`.
2. **Flagged corrections are drawn, not dropped.** `wiser_assist_p0`'s mapper and its `Support` accept only correction
   flag `ok`. Here a correction flagged `night` (a CH01/CH02 night that fails the ≤ 3-px dawn-closure rule) or `sample`
   is still drawn. The flag is named in the clip (per-camera note) and in `projection_coverage.csv`. Reason: the
   precision loss is a few pixels against a 14-in circle; dropping the flag would remove the circles from three whole
   CH01 nights. The projector passes `ok` to p0's `Support` only for building the grid.
3. **Day frames** = frames more than 30 min outside their night's sampled correction span (21:00 → 04:20).
   `frame_correction` already returns the nearest sample there. The clip says "outside the corrected night hours:
   nearest night correction (HH:MM) — circles approximate". `CAMERA_GEOMETRY_2026c.md` puts this error at up to ~30 px
   on CH02 at noon.
4. **Time base and sampling.** WISER is read on the aligned clock t_al = t_WISER − τ* (as v1), with the map's lag L = 0 s
   applied to it. There is one position per 0.25-s overlay step, at the step centre. V3 is interpolated linearly between
   rows ≤ 5 s apart (p0's `Tracks` rule), else the step is "not located". The raw dot is the nearest unmasked raw fix
   within ± 0.5 s. Rows carrying an `m_*` mask are excluded, as in v1's panel.
5. **Pixel inverse.** `wiser_assist_p0.invert_mapper` runs on `Corrections("2026c").to_paddock(cam, t, uv, z_mm=60)` at each
   step's whole second (as p0's clips). It starts from the nearest mapped 40-px grid centre of p0's `Support`, built at
   the event onset, and keeps a solution only if the round trip is ≤ 1 in. The 14-in ring is 48 paddock points, each
   inverted separately (the plan's "ring of paddock points"; p0's clips drew a local-Jacobian ellipse instead). A
   circle is drawn only if its centre inverts. A ring segment is drawn only if both ends invert and it is ≤ 3× the
   median segment, which guards the pano seam and the edge of the support. The static start circle is projected once,
   at the onset.
6. **Round-trip check, pano seam.** On CH01/CH02 the calibration maps two pixels to one ground point in the stitch seam
   band (`paddock_map.RayCamera` note), so a grid pixel there can come back as its twin. A dry run on all 128 projected
   event-cameras put every round-trip miss (> 1 px) within 137 px of u = 3840. The ≤ 1-px criterion is therefore
   reported outside the band |u − 3840| < 150 px; misses inside the band are counted separately. Their paddock error is
   < 1 in by construction. A midpoint-consistency test of consecutive moving circles found no flip between the two
   branches.
7. **Page details.** The second question uses keys 7 / 8 / 9 and the "start circle off" tick uses key m. The tick is
   available in both phases, but only when a start circle exists. After the reveal, Enter waits until the circle
   question is answered (n moves on without it). When the reveal clip has no circle on either camera, Q2 is disabled
   and the page exports `circle_verdict = no_circle`; this is not a reviewer answer. `map_flag` is blank when there is
   no start circle. Extra export columns: `circle_at`, `circle_available`, `start_circle_available`, `reveal_clip`. New
   status: `revealed` (verdict saved, circle question open). The export schema stays `wiser_event_review_labels/1`; the
   new columns are appended.
8. **Where the map caveat appears.** It is on the page in both phases (circles box and help), in the run README and in
   the reveal clip's legend. It is not in the blind clip, because it names WISER and the blind overlay must not.
9. **Rendering.** Both clips come from one decode (ffmpeg `split` → two subtitle passes), so the blind and reveal frames
   are identical apart from the overlay. Circles are ASS vector drawings (`\p3`). Labels: "start" next to the dashed
   circle and "WISER" next to the moving one. The upright → clip pixel mapping and the drawing positions were verified
   on synthetic frames by numeric luma checks (self-test).
10. **Cameras without projection** are found from `to_paddock`'s refusal (CH05, CH07, CH08), not from a hard-coded list;
    the on-screen note adds the reason in parentheses. Each camera's upright size (panos 7680 × 2160, CH05–CH08
    2560 × 1920) is checked against its source file by ffprobe.
