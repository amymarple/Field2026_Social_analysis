# Blind video review of the IMU–WISER consistency audit's events: 80 clips, a page that reveals the WISER / IMU panel only after a verdict (cohort 2026c) — 2026-10-05

- **Request (user, 2026-10-05):** WISER's error runs back and forth in place, so a ground truth exists — asked for the
  video paths and approved a GUI ("做吧 gui").
- **Plan:** [`implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md`](../implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md),
  **Part 2** (committed d722ec0 before any result); operational details in its **Amendment (Part 2) 1**, written before any
  verdict existed. Part 1 (the return test, `analyze_wiser_i1_return.py`) is a separate session; its classes were not used.
- **Bulk (off-repo):** `D:\Field2026_analysis_out\2026c\wiser_event_review_20261005_2236\` — `index.html` (the review
  page, data embedded, works from file://), `clips/` (**80 H.264 clips**, h264_nvenc, 5.9 GB, 52.7 min of video, 22–80 s
  each), `panels/` (80 PNG, revealed after a verdict),
  `events.json`, `event_summary.csv`, `selection.csv` (review id → audit event; not to be opened before reviewing),
  `overlay_ass/`, `_fonts/` (DejaVu Sans), `README.md`, `log.txt`.
- **Human verdicts go to** [`wiser/configs/wiser_event_review_2026c/`](../wiser/configs/wiser_event_review_2026c/README.md)
  (export format there; commit every export, never edit one; an empty placeholder with the schema is in place).
- The agent never opened a clip frame or a panel image; every verdict is the user's.

## What changed

- New `wiser/scripts/make_wiser_event_review.py` (base Python + matplotlib + ffmpeg; node for the self-test). Imported
  unchanged: `make_imu_video_review` (`view_parts` → `grab_frames.segments`, `layout`, `render` / `ffmpeg_cmd`,
  `nvenc_works`, the ASS helpers, `identity_at`, `house_label`, `find_fonts`, `CAMS`), `default_tracks`
  (`load_default_track`). No existing script, config or cache was edited.
- New `wiser/configs/wiser_event_review_2026c/README.md` + `wiser_event_review_2026c_placeholder.json` (export schema,
  no rows).
- Plan: Amendment (Part 2) 1 appended.

## Method

- **Events (80):** audit run `wiser_imu_consistency_20261005_2038`, V3 track: the 30 largest I1 and the 30 largest I2 (the
  audit's `event_list_*_V3.csv`, checked against the 30 largest of `events.csv.gz`), plus 20 I1 at random, 5 per size
  quartile (edges over all 5,411 V3 I1: 14.26 / 16.94 / 22.24 in; top 30 excluded; pool per quartile 1,353 / 1,352 / 1,353
  / 1,323; seed 20261005). Shown in a random order (seed 20261006) under neutral ids W01–W80.
- **Clips:** aligned clock (head-IMU / field-PC), cut from `F:\3rd_rat\<date>\<CH>\` by the video file-name time (±1 s;
  never the burnt-in OSD); hour boundaries and never-renamed segments as in `make_imu_video_review`. Cameras by zone
  (I1: where the rat was before the event; I2: the audit's zone): house_1 → CH08 in-box + CH05 top-down, house_2 → CH07 +
  CH06, open field → CH01 + CH02 panoramas upright and stacked. One composite H.264 per event: houses 3840 × 1656,
  panoramas 3712 × 2304, 20 fps, h264_nvenc cq 26.
- **Blind banner:** review id · animal · IR mark · coban colour · zone / date · clip start → end · cameras · "ignore the
  burnt-in clock" / the field-PC clock every 0.25 s and a red ▶ EVENT box during the event window; camera labels and
  "NO VIDEO" in camera holes. No WISER displacement, IMU state, size, class or selection set.
- **Page:** question per event — I1 "Did this rat actually change place during the EVENT bar?" (moved / stayed (in
  place) / cannot tell), I2 "Did the rat's body turn sharply?" (turned / ran straight / cannot tell); optional reason for
  "cannot tell" (not visible / identity unsure / other); note. Enter saves the verdict → the panel and the event's numbers
  appear. The first saved verdict is frozen as `verdict_blind` (also exported as `verdict`, the column the return test's
  reader uses); later changes go to `verdict_final` with `changed_after_reveal`. Autosave in the browser; Export JSON /
  CSV; Import.
- **Panel (static PNG):** distance of the raw fixes (dots) and the V3 track (line) from $\mathbf P_0$ vs clip time with
  the 12-in line, the run start / end and the reference window; the IMU state per second; the cumulative head turn
  (+ the display path heading for I2); an x–y map of the window's fixes with the house rectangles. Facts table:
  selection, audit size / duration / segments / run, the turn numbers (I2), strata, ≤ 6-anchor share, anchors and
  dispersion medians.

## Definitions

Units: inches (WISER frame, unverified origin), seconds, degrees. $t$ = aligned time $t^{\rm al} = t_{\rm WISER} - \tau^*_a$
(the head-IMU / field-PC clock; $\tau^*_a$ = 0.10–0.20 s); $t_{\rm on}$, $t_{\rm end}$ = the audit's event window (`t0`, `t1`).

### Clip window $[t_{\rm lo}, t_{\rm hi}]$
$$ t_{\rm lo} = t_{\rm on} - 10, \qquad t_{\rm hi} = \min(t_{\rm end},\ t_{\rm on} + 60) + 10 $$
**Text:** 10 s before the event to 10 s after it, at most 60 s of the event; 22–80 s. Cut by file-name time, so a frame's
field-PC time is good to ±1 s.

### EVENT bar
$$ [\,t_{\rm on},\ \min(t_{\rm end}, t_{\rm hi})\,] $$
**Text:** the whole audit window (I1: first ≥ 12-in second to the end of the last ≥ 12-in segment, gaps included; I2:
$[c_{\rm first} - 2, c_{\rm last} + 2]$). An event longer than 60 s continues past the clip; the page says by how much.

### Size quartile $Q(e)$ of a random I1 draw
$$ Q(e) = 1 + \#\{k \in \{1,2,3\} : s_e \ge q_k\}, \quad q_k = \text{the } 25k\text{-th percentile of } \{s_j : j \in \text{V3 I1}\} $$
where $s_e$ = the audit's I1 size (max distance of the V3 1-s medians from the run reference). **Text:** which quarter of
the I1 size distribution an event comes from; 5 events drawn per quarter so the verdicts also cover ordinary events.

### Camera zone
$$ z = h \iff |\ell_x| \le w_h/2 + 14 \ \wedge\ |\ell_y| \le h_h/2 + 14, \qquad (\ell_x, \ell_y) = R(-\phi_h)\,(\mathbf P - \mathbf c_h) $$
for house $h$ (centre $\mathbf c_h$, size $w_h \times h_h$, orientation $\phi_h$, `wiser_rois.json`); otherwise open field.
$\mathbf P$ = the run reference (I1) — **text:** the house rectangle grown by 14 in (≈ 2× WISER's jitter), the audit's and
the IMU review's rule; I2 uses the audit's zone at the window start.

### Distance from $\mathbf P_0$ (panel)
$$ d_{\rm raw}(f) = \lVert \mathbf p^{\rm raw}_f - \mathbf P_0 \rVert_2, \qquad d_{\rm V3}(f) = \lVert \mathbf p^{\rm V3}_f - \mathbf P_0 \rVert_2 $$
for each unmasked fix $f$ in the clip window. I1: $\mathbf P_0 = \mathbf r$ = coordinate-wise median of the V3 1-s medians
$\tilde{\mathbf p}(s)$ over the first 2 s of the trimmed run (the audit's reference); I2: $\mathbf P_0$ = coordinate-wise
median of the V3 positions with $t \in [t_{\rm on}, t_{\rm on} + 1)$. **Text:** how far WISER (raw) and the production track
are from where the rat was at the reference; ≥ 12 in on the V3 1-s medians is the I1 criterion. Range $[0, \infty)$ in.

### Cumulative head turn $\psi$ (panel)
$$ \psi(b_i) = \sum_{j < i} \Delta\psi_j - \psi_{\rm ref} $$
where $b_i$ = field-PC second boundaries, $\Delta\psi_j$ = `turn_net_deg` of second $j$ (sum of the head's angular velocity
about gravity / 50 Hz; a NaN second counts 0 and is shaded), $\psi_{\rm ref}$ = the value at $t_{\rm on}$ (I1) or at
$c_{\max} - 1$ (I2). **Text:** how far the head has turned, degrees, + = counter-clockwise from above; head scanning turns
it without the body.

### Display path heading $\theta$ (I2 panel only)
$$ \theta(g) = \operatorname{atan2}(\Delta y, \Delta x), \quad \Delta\mathbf p = \tilde{\mathbf p}(g + 0.5) - \tilde{\mathbf p}(g - 0.5), \quad \text{only where } \lVert\Delta\mathbf p\rVert \ge 10 $$
with $\tilde{\mathbf p}(u)$ = coordinate-wise median of the V3 fixes in $[u - 0.5, u + 0.5)$ (≥ 2 fixes), $g$ every 0.25 s,
unwrapped, referenced to $c_{\max} - 1$. **Text:** a display of the track's direction of travel while it moves ≥ 10 in/s;
not the audit's Phase-0 estimator (its $\Delta\theta$ / $\Delta\psi$ are printed in the panel title).

### Blind and final verdict
$$ v_{\rm blind} = v(t_{\rm save}), \qquad v_{\rm final} = v(t_{\rm export}), \qquad \text{changed} = [\,v_{\rm final} \ne v_{\rm blind}\ \text{at any time after } t_{\rm save}\,] $$
**Text:** $v_{\rm blind}$ is the answer at the first save, before the panel was shown — the ground truth for the return
test; $v_{\rm final}$ may differ if the reviewer changed the answer after seeing the panel.

## Verification

- `python wiser/scripts/make_wiser_event_review.py --selftest` → **PASS, 42 checks**: selection (30 + 30 + 20 unique,
  5 per quartile on the V3 I1 edges, top 30 excluded, V3 only, deterministic per seed, shuffled ids, a wrong top list
  refused); window arithmetic (20-s, 65-s, 222-s events, I2 4-s windows on half seconds); camera zones and the house
  rectangle geometry; identity per date (SF12 coban yellow → blue 08-31; SF11 between its tags); synthetic hourly files
  across 02:00 with ~1-s start offsets, a 2-s hole and a never-renamed file (parts and offsets exact); the blind overlay
  (0.25-s clock tiling and text, EVENT box timing, NO VIDEO only in the hole, none of the WISER / IMU / class / selection
  words); a rendered clip whose source frames carry their index in the luma — **1000/1000 view-frames show the source frame
  of their file-name time** across the hour boundary, the hole shows the empty canvas, no missing glyph; panel PNGs for I1
  and I2; the page — both script blocks pass `node --check`, and in node: no reveal before a saved verdict, invalid
  answers / reasons rejected, the blind verdict kept when the answer changes after the reveal, the CSV parses back
  (quotes, comma, newline in a note), import merges.
- **Time base** (scratch check, numbers only): for all 50 I1 events the V3 1-s median of the onset second, recomputed from
  the production track with the panel's fix set, is ≥ 12 in from the audit reference (50/50), and the recomputed size and
  reference equal the audit's (max |Δ| 0.0 in).
- **Headless Edge smoke test** of the page (DOM dump, no screenshot): 80 events listed, panel hidden before a verdict,
  key 2 + Enter saves and reveals (panel path + 10 facts), a change after the reveal is flagged with the blind verdict
  kept, Enter = next event (hidden again), "cannot tell" + reason, the I2 filter (30), help, no JavaScript error.
- **Return-test reader:** an export produced by the page's own logic (node) is parsed by Part 1's
  `analyze_wiser_i1_return.load_verdicts` (imported read-only, from a scratch copy) as JSON, as CSV and as a folder with the
  placeholder: the saved I1 verdicts come back as moved / stayed / cannot_tell with their `event_id`; the blind verdict is
  used when the answer changed after the reveal; an unsaved answer, the I2 row and the placeholder are skipped.
- **Full run:** `python wiser/scripts/make_wiser_event_review.py --cohort 2026c --workers 3` (after a `--no-clips` pass into
  the same folder) → **80/80 clips**, every probed duration = its window (± 0.05 s), 0 libass glyph warnings, 80 panels;
  wall 32.5 min (reads of the hourly files on `F:` shared with a parallel job). `index.html` then rebuilt with `--html-only`
  (the `verdict` export column was added during the render) — passes `node --check`; 0.28 MB.

## Results (for the user's review)

Counts only — which events are the extremes stays hidden until each verdict is saved.

- **80 events:** I1 50 (30 largest + 20 random, 5 per size quartile), I2 30 (largest). Per animal: SF07 25, SF10 15,
  SF09 12, SF12 12, SF08 9, SF11 7 (all SF11 events precede its 09-07 implant loss).
- **Cameras:** open field → CH01 + CH02 panoramas 54 (I1 31, I2 23); house_2 → CH07 + CH06 20 (I1 15, I2 5); house_1 →
  CH08 + CH05 6 (I1 4, I2 2).
- **No missing clip.** Every event has frames from both cameras except **W51** (I2): both panoramas have no frames for 0.5 s
  (23.0–23.5 s of the clip, the 01:00 hour boundary; shown as "NO VIDEO").
- **Events longer than the clip** (> 60 s; the page says how long they continue): 7 I1 events (12–886 s past the clip end).
- **Population note** on two events after 2026-09-11 19:40 (five non-implanted females in the paddock).

## Open / next

- The user reviews the 80 clips in `index.html` and exports JSON + CSV into `wiser/configs/wiser_event_review_2026c/`.
- Part 1 then runs `analyze_wiser_i1_return.py --with-verdicts wiser/configs/wiser_event_review_2026c/ --run <its run>`
  (I1 rows only; `verdict` = the blind verdict; matching on (animal, `audit_event_id`)). The I2 verdicts check the audit's
  I2 rule (path turn without head turn) on its 30 largest events; no driver reads them yet.
