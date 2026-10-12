# WISER event review GUI v3: circles on all eight cameras, day and night; corner swap; other rats in the reveal clip (cohort 2026c) — 2026-10-12

- **Request / approval:** the user approved the plan on 2026-10-12 ("行吧 干吧"), after the calibration session made
  `Corrections("2026c").to_paddock` map CH01–CH08 at cohort times
  ([CH05–CH08 mapping](2026-10-10-ch05-ch08-paddock-mapping.md)).
- **Plan:** [`implementation_plan/2026-10-12-wiser-event-review-v3.md`](../implementation_plan/2026-10-12-wiser-event-review-v3.md)
  (committed d2a1f19 before any result). Its **Amendment 1** records the implementation choices; it was written before any
  v3 verdict existed.
- This is a viewing-aid update of GUI v2 ([change log](2026-10-06-wiser-event-review-circles.md)). There is no new test.
- **Bulk (off-repo):** `D:\Field2026_analysis_out\2026c\wiser_event_review_20261012_1054\`
  - `index.html`: the review page.
  - `clips/`: 80 blind clips, each with the start circle only.
  - `clips_reveal/`: 80 reveal clips.
  - `panels/`, `events.json`, `event_summary.csv`, `selection.csv`, `projection_coverage.csv`, `roundtrip_by_camera.csv`,
    `circles_summary.json`.
  - `overlay_ass/`, `overlay_ass_reveal/`, `_fonts/`, `README.md` (coverage, swaps, round trips, checks), `log.txt`.
  - `repro_check/`: the v1 / v2 rebuilds used for the reproducibility checks.
  - Size 11.2 GB (5.5 + 5.7 GB of clips). Building took 19 min and rendering 35 min with h264_nvenc and 3 workers; no
    failures and no glyph warnings.
- **The agent never opened a clip frame or a rendered image.** Every circle comes from WISER plus the projection. The
  only pixel checks were numeric checks on synthetic self-test frames.

## What changed

- `wiser/scripts/make_wiser_event_review.py`:
  - New flags: `--v3` (implies `--circles`) and `--kit-run` (default: the WISER pixel kit
    `wiser_pixel_kit_20261006_1952`).
  - New code:
    - `build_event_v3` and `choose_cams_v3`: the corner swap.
    - `layout_v3`: an end camera in a panorama slot.
    - `event_circles_v3`, `write_circle_overlays_v3`: other rats, in-box `+` marks, the map-status line, lid notes.
    - `circles_payload_v3`, `coverage_rows_v3`, `map_status` / `kit_tables`.
    - `others_tracks` / `merge_others`: the other animals.
    - `roundtrip_grid` / `roundtrip_by_camera`, `circle_summary_v3`, `write_circle_readme_v3`, `circles_page_info_v3`.
  - `CamProjector` accepts a Newton tolerance and a v3 mode: per-second `lid` / `no correction` states and the
    `edge of ground` status.
  - `import_p0(with_ties=True)` preloads the recording repo's cohort ties (CH05, the CH07 / CH08 floor models).
    Without it, `camera_model` fails its lazy import and refuses those cameras.
  - Page changes, all gated on `CIRC.v3`: export `gui: "v3"`; Import marks `imported_from`; the title.
  - Self-test: `selftest_v3`, 26 checks.
- **GUI v1 and v2 are unchanged without `--v3`.**
  - v1: rebuilt on all 80 events. Overlays, `selection.csv` and `events.json` are identical to
    `wiser_event_review_20261005_2236`.
  - v2: rebuilt on 12 events (open field, house_1, house_2, a corner). Blind and reveal overlays, `events.json` and
    `selection.csv` are identical to `wiser_event_review_20261006_1637`.
- [`wiser/configs/wiser_event_review_2026c/README.md`](../wiser/configs/wiser_event_review_2026c/README.md): the GUI v3
  section, export differences and v3 caveats for `circle_verdict`.
- Plan: Amendment 1 appended.
- Imported read-only and unchanged:
  - `cv/cv_field/wiser_assist_p0.py`: `Map`, `Params`, `Support`, `invert_mapper`, `Tracks`.
  - `cv/cv_field/frame_correction.py`: `Corrections.to_paddock`, `.correction`, `.camera_model`.
  - The recording repo's `paddock_map`, `cohort_tie` and `inbox_floor_fit`.

## Method

- **Same 80 events, W ids and order** (seed 20261005, order seed 20261006). The clip windows, banner, panels and question
  are as in v1 / v2.
- **Cameras**
  - Houses as in v2: house_1 → CH08 + CH05; house_2 → CH07 + CH06.
  - Open field: CH01 + CH02. When neither panorama's mapped ground holds the start position, an end camera replaces one
    panorama: CH03 (looks to x = 0) or CH04 (x = 480).
  - The end camera is the one whose mapped ground holds the start position. If none does, it is the one whose image
    frame contains it (Amendment 1.2).
  - It replaces the panorama with fewer of the clip's target positions in its mapped ground.
- **Circles** (14 in, 48 ring points each inverted, every 0.25 s; WISER on the aligned clock t_al = t_WISER − τ*;
  WISER → paddock by the accepted p0 similarity map):
  - Pixels come from the Newton inverse of `to_paddock(cam, t, uv, z_mm = 60)`, tolerance 0.005 in, on every camera of
    the clip. CH05 goes through the cohort tie. CH07 / CH08 go through the house-floor model: z is above the floor and the
    model is NaN off the floor.
  - A step whose correction is flagged `lid`, or that has no correction, gets no circle and a note.
  - On CH07 / CH08 a `+` marks the circle centre, because the 14-in circle is wider than the floor.
- **Blind clip:** v1's banner plus the target's static dashed start circle. Each view also carries the legend, the
  map-status line and its notes.
- **Reveal clip:** the start circle, plus:
  - the moving target circle (solid yellow, "WISER") and the raw fix (red dot);
  - **the other tagged rats as thin cyan circles with their id**: production tracks, masks excluded, each on its own
    aligned clock; SF12's second tag is merged under SF12;
  - per-step notes;
  - on in-box views, "in a house WISER tells who is inside, not where in the pile".
- **Map status per view:**
  - CH01 / CH02: the kit's validation for that camera and night (`real_within14_share`, pass / FAILS). An onset outside
    21:00–04:20, or a night the kit excluded, reads "not validated".
  - CH03–CH08: "map validated on CH01 only".
- **Corrections by day:** CH05–CH08 use their real day corrections (hourly CH05 / CH06, per lid segment CH07 / CH08).
  CH01–CH04 have night corrections only, so their day frames keep the nearest-night fallback, flagged (Amendment 1.1).

### Definitions

- **Share of steps with a target circle** (per event and camera):
  $s_c = N_\mathrm{ok} / N_\mathrm{steps}$.
  - $N_\mathrm{steps} = \lceil D / 0.25 \rceil$ is the number of 0.25-s overlay steps of a clip of length $D$ s.
  - $N_\mathrm{ok}$ is the number of steps where the target's centre status is `ok`: located by WISER, inside the camera's
    mapped ground, correction not `lid`, and the inverse converged.
  - It is the fraction of the clip during which a moving circle is drawn on that camera.
- **Round-trip error:** $e = \lVert u - \hat f^{-1}(f(u)) \rVert$ in px.
  - $u$ is a grid pixel (120-px grid) whose paddock point $f(u)$ lies in the camera's mapped ground.
  - $\hat f^{-1}$ is the Newton inverse, started from the nearest mapped 40-px cell centre.
  - Reported as median, p99 and max, overall and outside the panorama seam band ($|u_x - 3840| \ge 150$ px on
    CH01 / CH02, where two pixels map to one ground point).
- **Convergence rate:** $N_\mathrm{converged} / N_\mathrm{in\ support}$. It counts the target's centre, ring and raw-dot
  points with status `ok` or `inverse failed`; `edge of ground` points are counted separately.
- **Kit within-14-in share** (`real_within14_share`, from the WISER pixel kit, not recomputed): the share of mapped YOLO
  detections (confidence ≥ 0.5) that have a WISER animal within 14 in, per camera and night. A night passes when the
  median residual ≤ 14 in and the control share ≤ half the real share.
- **Edge of ground:** a target inside p0's 1-in support raster whose Newton iterate maps to nothing (NaN forward). The
  raster overshoots its mapped cells. Such a target is not drawn and is not counted as a convergence failure.

## Results (projection only — no review has been done)

**75 of 80 events have a circle on at least one camera** (v2: 68). 65 have a start circle and 75 a moving circle. The
new ones are W02 (via CH03) and the six house_1 events W17, W24, W56, W57, W59 and W60 (CH05 / CH08). No v2 circle was
lost.

| camera | event-cameras | with start circle | with any moving circle | events with a circle | median share of steps with a target circle |
|---|---:|---:|---:|---:|---:|
| CH01 panorama | 43 | 32 | 39 | 39 | 1.00 |
| CH02 panorama | 53 | 29 | 38 | 38 | 0.90 |
| CH03 end | 6 | 1 | 3 | 3 | 0.03 |
| CH04 end | 6 | 0 | 4 | 4 | 0.10 |
| CH05 top-down (house_1) | 6 | 5 | 6 | 6 | 0.95 |
| CH06 top-down (house_2) | 20 | 20 | 20 | 20 | 1.00 |
| CH07 in-box (house_2) | 20 | 7 | 10 | 10 | 0.02 |
| CH08 in-box (house_1) | 6 | 3 | 6 | 6 | 0.54 |

- **Every event-camera was projectable** (160 of 160).
- **In-box shares are low** because the WISER position, mapped at head height, often falls off the 60 × 43-cm floor.
  The model is NaN there and no circle is drawn. In a house WISER gives the roster, not the position in the pile.
- **Corner swaps (12):**
  - CH03 replaces CH01: W02, W04, W27, W33, W74.
  - CH04 replaces CH01: W08, W11, W20, W30, W36, W51.
  - CH03 replaces CH02: W45, the only swap where CH03's mapped ground holds the start position.
  - The other 11 are image-frame swaps: the mapped start lies beyond the wall, 9–36 in from the end camera's nearest
    mapped cell.
  - W29, W43 and W66 have their start at or beyond the y = 0 / y = 240 walls, away from the ends: (386, 244), (271, −12)
    and (358, 238) in. No end camera sees them, so they keep CH01 + CH02. All three still have moving circles.
- **Events still without any circle (5):** W04, W27 and W33 (pole A0 corner; mapped WISER position median (−11, 3),
  (−8, −5) and (−23, −17) in) and W30, W51 (far corner, (472, 6) and (475, 10) in).
  - The mapped position stays beyond the wall for the whole clip, outside every camera's verified ground.
  - The clip shows the corner through CH03 / CH04 plus CH02, with "circle outside this camera's mapped ground — use the
    IR mark".
- **Lid / no correction:** no clip overlaps a lid event (± 5 min), so 0 steps are affected. 77 target-centre steps and
  3 891 target points were `edge of ground`.
- **Day frames:** 16 event-cameras (CH01 7, CH02 8, CH03 1; events W05, W27, W48, W61, W63, W64, W66, W71) use the
  nearest night correction and are flagged. The nine house_2 day events (W22, W50, W52, W53, W55, W65, W73, W76, W80)
  now use real CH06 / CH07 day corrections. 14 projectable event-cameras carry a non-ok correction flag (`night` /
  `sample`), drawn and named.
- **Map status of the panorama event-cameras:**
  - CH01: 20 pass, 8 fails, 15 not validated.
  - CH02: 23 pass, 13 fails, 17 not validated.
  - The kit's passing nights have 22–77 % of mapped detections within 14 in. CH01 09-01, CH02 09-01 and CH02 09-02
    fail.
- **Other rats:** drawn in 76 reveal clips (71 167 circle-steps). Their lowest per-clip convergence is 0.9989.

## Checks

- **Self-test** (`--selftest`): 101 of 101 checks PASS, covering v1, v2 and the 26 new v3 checks:
  - a CH07 / CH08-like floor model: 180° rotation, NaN off the floor, ring clipped, `+` mark, round trip ≤ 1 px;
  - the corner swap: mapped ground, image frame, no video, a panorama holding the start, houses; the swapped layout, and
    a synthetic render whose marker lands < 1 px from the prediction;
  - other rats only in the reveal clip, a second tag merged, none during a lid;
  - lid-flagged steps and onsets without a circle;
  - the map-status texts and the kit parsing;
  - the v3 page: `gui: "v3"`, import of a v2 export marked `imported_from`, the node UI flow.
- **Round trip pixel → paddock → pixel** (`roundtrip_by_camera.csv`):

  | camera | points at event onsets | p99 px (outside seam) | max px (outside seam) | stand-alone grids 09-06 02:00 / 14:00: max px (outside seam) |
  |---|---:|---:|---:|---:|
  | CH01 | 29 580 | 0.058 | 0.090 | 0.060 / 0.061 |
  | CH02 | 36 901 | 0.055 | 0.089 | 0.079 / 0.075 |
  | CH03 | 2 992 | 0.055 | 0.103 | 0.059 / 0.090 |
  | CH04 | 2 867 | 0.055 | 0.095 | 0.086 / 0.086 |
  | CH05 | 1 524 | 0.057 | 0.092 | 0.074 / 0.058 |
  | CH06 | 6 173 | 0.055 | 0.065 | 0.058 / 0.072 |
  | CH07 | 3 439 | 0.046 | 0.050 | 0.050 / 0.050 |
  | CH08 | 1 042 | 0.046 | 0.050 | 0.050 / 0.050 |

  - Inside the pano seam band, CH01 has 285 event-onset points > 1 px (max 136 px; overall p99 2.19 px). These are the
    seam's twin pixels, as in v2 Amendment 1.6.
  - CH02's overall max is 0.81 px.
- **Inverse convergence:** 730 275 of 730 321 target points; lowest per clip-camera 0.9916. The largest round-trip error
  of a drawn point is 0.86 in (p0's acceptance rule is ≤ 1 in).
- **Blind overlays** (all 80): no WISER, IMU or answer words, and no cyan other-rat drawing.
- **Reproducibility:** v1 on 80 events and v2 on 12 events, byte-identical (see above).
- **Page:** `node --check` OK. The real page's script runs through the UI-flow stub: blind clip → reveal clip after
  Enter → circle question.

## For the main session

- **CLAUDE.md,** wiser_baseline row:
  - Add GUI v3: `make_wiser_event_review --v3 [--kit-run …]`.
  - Current page: `<OUT>/2026c/wiser_event_review_20261012_1054/index.html`. 75 / 80 events have a circle, on CH01–CH08.
    There are 12 corner swaps to CH03 / CH04, and the other rats appear in the reveal clip.
  - Answers from v2 carry over through Import.
  - The v2 sentence "none on CH05 / CH07 / CH08" no longer describes the current page.
- **Index READMEs:** `change_log/README.md` (this file) and `implementation_plan/README.md` (plan status → DONE, with
  Amendment 1).
- **Commit:** the driver, the config README, the plan amendment and this change log. Other sessions' uncommitted files
  were not touched.
- **Optional follow-up:** daytime corrections for CH01–CH04 (`landmark_track.py --times …` for W05, W27, W48, W61, W63,
  W64, W66, W71) would replace the remaining nearest-night fallback.
