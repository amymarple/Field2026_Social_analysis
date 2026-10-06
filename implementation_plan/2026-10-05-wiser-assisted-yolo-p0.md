# WISER-assisted YOLO, phase 0: WISER → CH01 mapping, WISER presence at the fixed spots, missed-rat candidates

Date: 2026-10-05. Status: **DONE 2026-10-05** (approved "可以试试" 2026-10-05; run
`$OUT/2026c/cv_field_wiser_assist_p0_20261005_2211`, report
`results/2026c/cv_field/reports/cv_field_wiser_assist_p0_2026c.md`; amendment 1 before results, 2–3 after results). The
user agreed to having this written as a plan ("可以"). Pre-registered before any result; amendments dated and marked
*before* or *after results*.
Every data location involved is listed in [`cv/cv_field/DATA_MAP_c1yolo_wiser.md`](../cv/cv_field/DATA_MAP_c1yolo_wiser.md).

## Why

The cohort-1 YOLO v5 (`social-field-rat`, plan `2026-10-05-c1-yolo-transfer-sam3.md`) transfers to cohort-3 CH01 at
night, but the user saw many false positives and false negatives that are **fixed in place** (review clips of 09-06
21:00–22:00), and the cached detections agree (one spot has a box in ≈ 49 % of frames, another in 34 %). The user asked
whether WISER can help train YOLO. WISER cannot give boxes (≈ 4–7 in error plus mapping error ≈ 50–150 px ≈ one rat),
but before the 09-11 population change almost every animal in the paddock carries a tag, so WISER can say **whether an
animal is near a place** — enough to tell an object from a resting rat at a fixed spot, and to point at seconds when a
tagged rat is in view but YOLO has no box. Phase 0 tests whether that works on the one hour already processed.

## Scope and inputs (read-only)

- Hour: CH01, field-PC 2026-09-06 21:00:00 → 22:00:00 (the step-2 hour). All six implanted animals SF07–SF12 tagged.
- YOLO: `$OUT/2026c/cv_field_c1yolo_video_20261005_1848/detections.csv.gz` (+ `frames.csv.gz`); fixed spots from that
  run's `fixed_spots/fixed_spots.csv` (being produced; phase 0 starts after it exists).
- WISER: default tracks `$OUT/2026c/wiser_default_tracks/SF07…SF12/20260906.csv.gz` via `wiser/src/default_tracks.py`
  (columns t_ms, x, y, vx, vy, valid, m_* flags, anchors_used, method, imu_state). Only rows with `valid` and no
  `m_*` flag. House zones `wiser/configs/wiser_rois.json` (rectangle + 14 in).
- Camera: `Corrections("2026c").to_paddock("CH01", t, uv, z_mm=60)` (`cv/cv_field/frame_correction.py`); box centre
  as the image point; rows with a failing `info["flag"]` dropped and counted.

## A. Mapping WISER → paddock, checked against CH01 detections

1. **Pairs.** One frame per second (the frame nearest each whole second, 3 600 frames). YOLO boxes with conf ≥ 0.5,
   centre outside every fixed spot (occupancy ≥ 5 %), mapped to paddock inches. WISER animals outside the houses,
   positions linearly interpolated at frame time + lag L.
2. **Model (primary).** paddock = WISER + d (the axes are known to align, user 2026-09-28): parameters d = (dx, dy)
   and the lag L ∈ [−90, +90] s (0.5-s grid; file-name start times may be offset). Fit: coarse grid over d (± 100 in
   around the difference of the means, 2-in steps) scoring the fraction of detections with a WISER animal within
   20 in, then refinement by iterated Hungarian assignment (gate 30 in) and a Huber-loss least squares on matched
   pairs (k = 6 in), L re-chosen on the grid at each iteration until d moves < 0.1 in.
3. **Validation.** Alternate 5-min blocks: fit on blocks 1, 3, 5, 7, 9, 11, test on 2, 4, …, 12. Report on test
   blocks: matched-pair residual median / p90 (in), the fraction of detections with an animal within 14 in, the same
   split by the WISER animal's IMU state (still vs moving: the still subset is free of timing error), and the
   **negative control**: WISER from 22:00–23:00 placed on the 21:00–22:00 frames, refitted the same way.
4. **Sensitivity.** 4-parameter similarity (rotation θ, scale s, d); reported, adopted only if the test median
   residual improves by ≥ 10 %. θ and s are reported either way.
5. **Acceptance (fixed now).** The mapping is accepted if the test median residual ≤ 14 in **and** the control's
   within-14-in fraction ≤ half the real one. If not accepted, B and C are **not** produced; the report says why.

## B. WISER presence at each fixed spot (blind to the user's verdicts)

Spot centre pixel → paddock (`to_paddock` at the spot's median time) → WISER frame (inverse of the accepted map). Per
minute: spot "on" if it has a box in ≥ 50 % of that minute's frames; distance from the spot to the nearest tagged
animal (all animals, in or out of houses), that animal's id and its fraction of `imu_state = still` seconds. Per spot:
minutes on; of those, minutes with an animal within 14 in and within 30 in, and with a **still** animal within 14 in;
the same for minutes off; Spearman ρ between per-minute occupancy and an animal-within-14-in indicator. Spots outside
CH01's calibrated support are listed as NaN. Written only to the run folder (`wiser_spots.csv`), **not** onto the
user's review page; the user fills `fixed_spots_review.csv` first. The agreement table (user verdict vs WISER) is a
separate later step, run only after the user's verdicts are in.

## C. Missed-rat candidates (for the user's labelling; not a metric)

CH01 ground support = the paddock polygon covered by a 40-px pixel grid mapped with `to_paddock`. Per second, each
tagged animal outside the houses, mapped into paddock and inside the support, with no YOLO box (conf ≥ 0.25) mapped
within 20 in → a miss second; consecutive miss seconds of one animal form an episode (≥ 3 s kept). Output per episode:
start, duration, animal, paddock x/y, approximate upright-pano pixel (nearest grid point), IMU state; plus a 40-in
paddock grid of miss seconds. A WISER "miss" can also be occlusion (grass, house roof), WISER error or an animal out
of view, so episodes are proposals for the user's eyes only.

## Outputs, code, pointers

- Code `cv/cv_field/wiser_assist_p0.py` (`--selftest` on synthetic data: known offset + lag recovered, control fails,
  B and C on synthetic spots / misses). cv env or base Python.
- Run folder `$OUT/2026c/cv_field_wiser_assist_p0_<ts>/`: `mapping.json` (d, L, θ, s, acceptance), `pairs.csv.gz`,
  `residuals_test.csv`, `control.json`, `support_polygon.json`, `wiser_spots.csv` (blind), `fn_episodes.csv`,
  `fn_grid.csv`, `run.json`.
- Report `results/2026c/cv_field/reports/cv_field_wiser_assist_p0_2026c.md`, figures
  `results/2026c/cv_field/figures/wiser_assist_p0/`, pointer `run_manifest_wiser_assist_p0_2026c.json`.
- Afterwards: change_log, both index READMEs, CLAUDE.md cv_field map, `cv/cv_field/HANDOFF.md`, and the data map.

## Rules

The agent never judges images. WISER-derived positions are proposals, never boxes or labels. No training in phase 0.
The lag L is reported only — it is not written into any clock configuration (the video-clock work is the separate plan
`2026-10-05-video-clock-sync.md`). The 09-06 21–22 h hour becomes "WISER-touched": it cannot later serve as an
independent CV-vs-WISER validation. The frozen test night 09-05 and `cv/dataset/rat_pano_test/` stay untouched. Before
09-11 19:40 only; SF11 untracked windows and handling windows (`cv/configs/cohort3_handling_windows.json`) excluded if
any fall in the hour.

## Later (not approved; sketched only)

Phase 1, only if A is accepted and B agrees with the user's verdicts: apply the mapping on other calm nights (new
detections needed per night) to mine hard negatives at confirmed object spots and missed-rat frames, the user labels
them together with the 60 round-0 cohort-3 frames, fine-tune v5 → v6, score on the 40 frozen test frames labelled from
scratch.

## Cost

CPU only, ≈ 10–20 min (3 600 frames × ≤ 10 boxes, grid search, two fits, control).

## Amendments

### Amendment 1 — 2026-10-05, *before results*: implementation clarifications

Written after the code and its synthetic self-test, before the driver touched the real hour. None changes a
threshold, a split or the acceptance rule; each fixes a choice the plan left open.

1. **Frame per second** = the frame whose PTS is nearest each whole second s = 0 … 3 599 after the file-name start.
2. **WISER time**: `t_ms` (WISER = field-PC clock), local = UTC − 4 h. `t_al_ms` is not used; L absorbs WISER's
   0.1–0.2 s fix latency (below the 0.5-s grid). **Interpolation**: linear between the two bracketing clean fixes only
   when they are ≤ 5 s apart, else the animal is not located at that time; IMU state = that of the nearer fix.
   *Outside the houses* = not inside either `wiser_rois.json` house rectangle grown by 14 in, judged on the
   interpolated position.
3. **Box mapping**: box centre at z = 60 mm, `to_paddock` evaluated once per whole-second window (frames with PTS
   within ± 0.5 s) at that second's time; the correction moves by a fraction of a pixel per hour. A frame whose
   correction flag is not `ok` loses all its boxes; a NaN (outside the verified support) loses that box; both counted.
   **Fixed-spot exclusion** (A): box centre inside a 40-px cell with occupancy ≥ 5 % in the step-2
   `fixed_spots/cells.csv.gz` (= the cells of the two spots).
4. **Coarse grid** evaluated at L = 0; its centre = mean paddock position of the fit detections − mean WISER position
   of the animals outside the houses over all fit seconds; ties → the grid point nearest the centre.
5. **L choice** at each iteration: minimise the mean truncated Huber cost of the per-second Hungarian assignment,
   C(L) = mean over fit detections of ρ₆(min(r, 30)), an unmatched detection costing ρ₆(30); ties → smallest |L|.
   **Hungarian cost** = Euclidean distance capped at the 30-in gate; pairs beyond the gate dropped. **Huber LS** =
   IRLS on the residual norm (k = 6 in). Convergence: d moves < 0.1 in (max 50 iterations); L is then re-chosen once
   at the final d.
6. **Similarity**: p = s R(θ)(w − c) + c + d with c = the mean WISER position of the final primary fit pairs (so its d
   is comparable with the primary d); weighted Umeyama under Huber weights; the same L / Hungarian loop, starting from
   the primary fit; converged when no fit pair's mapped position moves ≥ 0.1 in. Acceptance (A5) is judged on the
   primary model; if the similarity is adopted (≥ 10 % better test median) B and C use it.
7. **Test statistics**: residual median / p90 over the test Hungarian pairs (truncated at 30 in by the gate; the
   matched share is reported with it). Within-14-in share = per test detection, nearest animal outside the houses (no
   one-to-one constraint), denominator = all test detections. IMU split: still = `imu_state` 1, moving = 2 (active) or
   3 (locomoting), also reported separately, plus 0 (unusable); residuals grouped by the matched animal's state, the
   within-14 share by the nearest animal's state.
8. **Negative control**: WISER queried at frame time + 3 600 s + L, L on the same ± 90-s grid relative to that shift;
   own coarse grid, own fit; evaluated on the test blocks with its own (d, L).
9. **B**: spot centre = the median pano centre in `fixed_spots.csv`, mapped at the time of the spot's middle frame
   (`frame_middle`). Minute *on* = the step-2 per-minute occupancy (`occ_minNN`, boxes ≥ 0.25) ≥ 0.5. Per second the
   distance to the nearest located animal (in or out of houses) at second + L; minute distance = median over the
   minute's seconds with ≥ 1 animal located; minute's animal = the most frequent per-second nearest one; its still
   share = share of the minute's seconds (where it is located) with `imu_state` 1; *still animal within 14 in* =
   minute distance ≤ 14 in and still share ≥ 0.5. Spearman ρ over the 60 minutes. `wiser_spots.csv` holds one row per
   spot (summary) and per spot-minute (`level` column).
10. **C**: support = union of the 40-px pixel cells whose four corners map (to_paddock at 21:30, z = 60 mm), rasterised
    at 1 in, its outline = the raster's external contours; nearest grid point = nearest mapped 40-px cell centre.
    Boxes for a miss = the sampled frame's boxes with conf ≥ 0.25, fixed-spot boxes included. Episodes = strictly
    consecutive miss seconds. Added descriptive columns (no threshold): share of the frames within ± 0.5 s of each
    episode second holding a box within 20 in (a flicker indicator), seconds without any box, nearest-box distance.
11. **Blinding of B**: B's numbers go only to `wiser_spots.csv`; the driver prints only the file name and row count,
    and the report, `run.json`, `mapping.json` and the figures carry none.

### Amendment 2 — 2026-10-05, *after results* (external review relayed by the user): model selection on the fit blocks only

**Why.** A4 picked between the translation (d) and the similarity (θ, s, d) by the test-block residual and A5 then
judged acceptance on the same test blocks, which turns the test blocks into a validation set.

**Change.** The model and its lag L are chosen on the fit blocks only: both models fitted on fit blocks 1, 5, 9 and
compared on fit blocks 3, 7, 11 (inner validation); the "≥ 10 % better" rule now applies to the inner-validation median
residual. The chosen model is refitted (with its L) on all six fit blocks. The test blocks (2, 4, …, 12) are used once,
for the acceptance verdict and the reported test numbers of the chosen model; A5 reads "the chosen model's test median
≤ 14 in and the control's within-14-in share ≤ half the chosen model's". The negative control is unchanged (translation,
six fit blocks). Also made explicit in code and report (both already the plan's intent): WISER never creates a negative
(an animal WISER does not locate is unknown, never "no rat"; nothing is marked empty), and C episodes are *suspected
misses* (`kind = suspected_miss`), never boxes — an occluded animal must not get a box.

**Old vs new selection** (part A had already run when this arrived):

| | first run `cv_field_wiser_assist_p0_20261005_2158` (superseded) | amended run `cv_field_wiser_assist_p0_20261005_2211` |
|---|---|---|
| selection basis | test blocks: median translation 5.54 in vs similarity 4.39 in, gain 20.8 % | inner validation (3, 7, 11): translation 6.03 in vs similarity 4.17 in, gain 30.9 % |
| model chosen | similarity | similarity |
| map, L (six fit blocks) | d = (−272.85, −605.80) in, θ 0.114°, s 0.9634, L 0.0 s | identical |
| acceptance judged on | translation's test median 5.54 in; within-14 87.1 % vs control 2.9 % | similarity's test median 4.39 in; within-14 88.5 % vs control 2.9 % |
| verdict | accepted | **accepted — unchanged** |

Because the chosen model and its refit are identical, B (`wiser_spots.csv`, byte-identical by sha256; never opened) and C
(`fn_episodes.csv` identical apart from the new `kind` column) are unchanged. The first run folder carries
`SUPERSEDED.txt`.

### Amendment 3 — 2026-10-05, *after results*: descriptive diagnostics (no decision depends on them)

Added to the amended run and its report: test residuals and within-14-in shares by 80-in paddock x band, with the signed
median residual per axis (a local mapping offset would show there), in `residuals_test_by_x.csv`; the lag-cost shape
(relative cost at L ± 0.5 s; the L range within 5 % of the minimum); how many test detections without an outside animal
within 14 in have an in-house-zone animal within 14 in; the C cell with the most suspected-miss seconds and the part-A
residual of the detections inside it; a top-5 table of `fn_grid.csv`. Reason: the first report showed a strong
cluster of suspected misses at the paddock's +x end, and whether the map is locally off there decides how the user should
read it (it is not: the 106 detections inside that cell match with median residual 5.0 in).

### Amendment 4 — 2026-10-05, *after results (user request)*: review clips of the suspected-miss episodes

The user asked to see the part-C episodes by eye. Nothing is refitted and YOLO is not rerun: cached step-2 detections,
the accepted map (similarity d, θ, s, L = 0) and `fn_episodes.csv` of run `cv_field_wiser_assist_p0_20261005_2211`.

**Selection (rule only; the agent never looks at frames).** Rank the episodes by duration (ties → earlier start); walk
the list; each episode's clip window = [start − 5 s, end + 5 s], capped at 90 s from the window start; skip an episode
whose window overlaps an already chosen window; stop at 12 clips. Report how many clips fall in the +x hotspot cell
(paddock x 440–480, y 120–160 in, judged on the episode's median paddock position) and how many elsewhere. Other
episodes that fall inside a chosen window are listed with that clip.

**Rendering.** Every frame of the window (PyAV, as step 2 — pixel-identical to `grab_frames`), 20 fps H.264, canvas
3840 × 2160: top = the whole upright pano scaled to 3840 × 1080; bottom left = a native 1920 × 1080 crop following the
episode animal's projected pixel (1-s running median, clamped to the pano); bottom right = a text panel (field-PC frame
time; episode id, animal, "SUSPECTED MISS (WISER proposal, not a box)"; per animal: id, in / out of a house zone,
distance to its nearest YOLO box in inches, or "out of view"; the YOLO count). YOLO boxes conf ≥ 0.25 thin green with
their conf on both views. WISER animals SF07–SF12 projected with the accepted map and a numeric inverse of `to_paddock`
(Newton on the pixel, accurate to ≤ 1 in, not the 40-px grid); a circle of 14 in projected locally by a
finite-difference Jacobian, plus the id; the episode animal red, the others cyan; animals in a house zone dimmed and
dashed; outside CH01's support: "out of view" in the panel, nothing drawn. Burned-in note: "WISER circles = position
± ~14 in; absence of a box can be occlusion". Outputs in `<run>/review_clips/`: `<k>_ep<id>_<animal>_<HH-MM-SS>.mp4`,
`clips.csv`, `index.html` (top line: fill `fixed_spots_review.csv` before opening the clips, since the WISER circles
reveal what part B tests), an empty `review_template.csv` (verdicts visible_missed / occluded / not_there_wiser_wrong /
box_present / unsure). Checks: ffprobe frame counts = expected; `--selftest` covers the inverse (round trip ≤ 1 in) and
the overlap rule. The B file stays unopened and no sealed number appears anywhere.

*Done 2026-10-05* (`wiser_assist_p0.py --clips <run>`, cv env): 12 clips (4 in the hotspot, 8 elsewhere), 16 140 frames,
written = expected = ffprobe for every clip, inverse round trip ≤ 0.98 in, 17.3 min; listed in the report. One
rendering detail differs from the wording above: OpenCV's Hershey fonts are ASCII-only, so the burned-in note reads
"+/- ~14 in" instead of "± ~14 in" (the index page keeps "±"). An animal whose projection is inside the support but has no
pixel within 1 in (rare, near the support edge / the pano seam) is labelled "no pixel: inverse failed" in the panel and
not drawn.
