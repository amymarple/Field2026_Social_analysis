# I1 "return test" (does WISER come back to where it was?) + a blind video-review GUI of the audit events (cohort 2026c)

**Status:** PLANNED 2026-10-05, written before any number of this step was computed.
**Approval:** the user (2026-10-05): WISER's error is not like the IMU's — the IMU drifts away, WISER runs back and forth
in place, so a ground truth exists; asked for the video paths and approved both parts ("做吧 gui"). Operational details
are marked **[op]**. **Direction:** `wiser_baseline`.

## Why (established facts, not re-derived)

- Consistency audit (`change_log/2026-10-05-wiser-imu-consistency.md`, run `D:\Field2026_analysis_out\2026c\wiser_imu_consistency_20261005_2038`):
  V3 I1 ("≥ 12-in displacement inside a ≥ 5-s run with no IMU-locomoting second", 2-s trimmed) 4.24 per IMU-ok hour,
  5,411 events, none in all-still runs; low-anchor enrichment only 1.43× → *not material* by its rule. I1 mixes two causes
  that the audit could not separate: WISER wandering in place, and real relocation the loco detector missed (TPR 0.75).
  V3 I2 0.10 per hour (125 events). The 30 largest I1 / I2 events are listed with `F:\3rd_rat` files + offsets.
- WISER's error is **bounded and mean-reverting**: in certified stillness the raw per-fix RMS is 5.6 in but the worst 10-s
  median strays a median 1.5 in, and ≥ 12 in for ≥ 10 s happened 3 times in 75 still-hours. So while the rat does not
  translate, the long-run WISER median is the truth; an excursion that **returns** to the start is WISER error, a shift to a
  **new stable position** is a real relocation.

## Part 1 — the return test (driver `wiser/scripts/analyze_wiser_i1_return.py`, config `wiser/configs/wiser_i1_return_2026c.json`)

Inputs (read-only): the audit's `tables/events.csv.gz` / `runs.csv.gz` / `controls.csv.gz`, the production tracks (raw
fixes `x_raw`, `y_raw`, `anchors_used`, masks) via `wiser/src/default_tracks.py`.

- **Positions** from raw fixes (smoother-independent): pre $\mathbf P_0$ = coordinate-wise median of the raw fixes in the
  audit's reference window (first 2 s of the trimmed run — the I1 reference); post $\mathbf P_1$ = median of the raw
  fixes in $[t_{\text{end}}, t_{\text{end}}+10\,\text{s})$ ∩ the trimmed run, where $t_{\text{end}}$ = the end of the
  event window; ≥ 5 s and ≥ 10 fixes required **[op]**. Sensitivities: a 10-s pre window before the onset (inside the run);
  a 30-s post window.
- **Classes:** **return** $\lVert\mathbf P_1-\mathbf P_0\rVert<6$ in; **relocate** ≥ 12 in; **ambiguous** 6–12 in;
  **censored** no valid post window inside the run (the event runs into the run end / next locomotion).
- **Report:** class shares (all, excluding censored), by zone, day/night/twilight, weather class, size band
  (12–24, 24–48, > 48 in), duration band, run length; per animal; the ≤ 6-anchor share and dispersion of each class's
  event windows vs the audit's matched controls (ratio, 10-min block-bootstrap CI); the raw-WISER excursion profile
  (median distance from $\mathbf P_0$ vs time from onset) per class.
- **Pre-registered reading:** **"WISER in-place wandering dominates I1"** if *return* is ≥ 50 % of the classifiable
  (non-censored) events **and** the *return* class's ≤ 6-anchor enrichment is ≥ 1.5× with its CI above 1 **and** above the
  *relocate* class's point estimate → propose **V8** (during non-locomoting runs the position is held piecewise constant
  and a relocation is accepted only when WISER settles at a new stable position) as a new pre-registered test. Otherwise
  I1 is mainly real movement the IMU missed → V3 stays, no correction.
- **Validation:** when the user's video verdicts (Part 2) are exported, a second pass (`--with-verdicts <file>`) reports the
  agreement of return / relocate with "did not move" / "moved" (confusion table, Cohen's κ) — the verdicts are the
  ground truth for this classifier. No threshold is re-tuned on them.
- Outputs: bulk `D:\Field2026_analysis_out\2026c\wiser_i1_return_<ts>\` (per-event classes, tables, provenance, log);
  report `results/2026c/wiser_baseline/reports/wiser_baseline_i1_return_2026c.md` (+ figures), pointer
  `run_manifest_i1_return_2026c.json`; `change_log/2026-10-05-wiser-i1-return.md`. `--selftest` (synthetic: planted
  in-place excursions that return, planted relocations, censored runs, low-anchor episodes → classes and enrichment
  recovered).

## Part 2 — blind video-review GUI (driver `wiser/scripts/make_wiser_event_review.py`, reusing `make_imu_video_review.py`)

- **Events (80):** the audit's 30 largest I1 and 30 largest I2 (V3), plus **20 I1 events drawn at random, 5 per size
  quartile**, fixed seed **[op]** (so the verdicts also cover ordinary events, not only extremes). Part 1's classes are not
  used to choose events.
- **Clips:** per event, window $[t_{\text{onset}}-10\,\text{s},\ \min(t_{\text{end}}, t_{\text{onset}}+60\,\text{s})+10\,\text{s}]$,
  from `F:\3rd_rat\<date>\<CH>\` by **file-name time** (never the OSD; video is on the PC clock to ± 1 s), two cameras by
  zone (house_1 → CH08 in-box + CH05 top-down; house_2 → CH07 + CH06; open field → CH01 + CH02 panoramas, rotated upright and
  downscaled); H.264, side by side or two players.
- **Blind by design:** the overlay shows only the animal, its IR mark (SF07 x, SF08 none, SF09 star, SF10 square with cross,
  SF11 circle, SF12 two lines) and coban colour, the zone, the field-PC time and an **EVENT** bar during the event window —
  no WISER displacement, no IMU state, no class. **After** the user saves a verdict the page reveals a static panel (WISER
  raw / V3 displacement from $\mathbf P_0$ vs time, the IMU state row, the gyro turn for I2).
- **Questions:** I1 — "Did this rat actually change place during the EVENT bar?" → *moved* / *stayed (in place)* / *cannot
  tell* (rat not visible / identity unsure); I2 — "Did the rat's body turn sharply?" → *turned* / *ran straight* / *cannot
  tell*; free-text note. Verdicts are saved in the browser and exported as JSON/CSV → `wiser/configs/wiser_event_review_2026c/`.
- Outputs: `D:\Field2026_analysis_out\2026c\wiser_event_review_<ts>\` (`clips/`, `panels/`, `index.html`, `events.json`);
  `--selftest` (ffmpeg + a synthetic video: window arithmetic, file lookup across hour boundaries, overlay, export format).
  The agent never judges a frame.

## Caveats known in advance

The return test assumes WISER's mean-reversion holds outside certified stillness (it was measured mostly in the houses);
a rat can walk away and come back within one run (a "return" that was real movement) — the video verdicts check this. Video
identity inside a crowded house depends on the IR mark being visible. The 6 / 12-in thresholds were fixed in advance.

## Amendment (Part 1) 1 (2026-10-05 22:25, operational; written BEFORE any number of Part 1 was computed)

Written by the session implementing Part 1 after reading this plan, the audit driver and the audit run's table schemas, before
the driver existed and before any class, share, enrichment or profile was computed (the only numbers seen are the audit's
published ones, listed under *Why*). No class, threshold or reading rule above is changed; these fix details the plan leaves
open (**[op]**), resolve one ambiguity, and declare one structural property of the classifier with a sensitivity for it.

1. **Inputs and fix set.** Events = the audit run `wiser_imu_consistency_20261005_2038`, `tables/events.csv.gz`, rows with
   track V3 and type I1 (5,411); matched controls = its `controls.csv.gz` rows with track V3 and type I1; the per-window raw
   dispersion of both = its `work/disp.npz` (the audit's enrichment input). Raw fixes = the production default tracks
   (`x_raw`, `y_raw`, `anchors_used`, aligned time `t_al_ms`), every fix with none of the five masks (the audit's fix set;
   `valid` is not used, as in the audit). All times are aligned seconds (field-PC / IMU clock); the event times are integer
   seconds. `runs.csv.gz` is not needed (each event row carries its trimmed run `run_t0`, `run_t1`, `run_len_s`).
2. **Windows.** $t_{\text{end}}$ = the audit's event-window end `t1` (end of the last second with displacement ≥ 12 in,
   audit Amendment 1.6); $t_{\text{onset}}$ = `t0`. $\mathbf P_0$: raw fixes in $[t_{\text{run},0}, t_{\text{run},0} + 2)$
   (the I1 reference window; ≥ 2 fixes, guaranteed by the audit's evaluability rule — an event with fewer would be counted
   and left out). Post window $[t_{\text{end}}, \min(t_{\text{end}} + 10, t_{\text{run},1}))$; valid iff its length ≥ 5 s and
   it holds ≥ 10 raw fixes; otherwise **censored** (reason recorded: window < 5 s, or < 10 fixes). Sensitivity S1 (10-s pre
   window): $[t_{\text{onset}} - 10, t_{\text{onset}}) \cap$ the trimmed run, same minimums (an invalid pre window = censored,
   reason "pre"). Sensitivity S2 (30-s post window): same minimums; the 30-s window contains the 10-s one, so S2's censored
   set is a subset of the primary's (equal for "window < 5 s"; a 10-s window with < 10 fixes can be valid at 30 s).
3. **Structural property of the primary classifier (not anticipated by the plan).** By the audit's window definition the
   I1 window contains *every* second of the trimmed run whose V3 1-s median is ≥ 12 in from the V3 reference, so on every
   second of the primary post window the V3 1-s median is < 12 in from that reference (or undefined). Consequences: (a) a
   displacement that persists until the run ends — a relocation held until the next locomotion — always runs into the run
   end and is **censored**; (b) the primary **relocate** class can arise only where the raw-fix median differs from the V3
   track (or $\mathbf P_0$ from the V3 reference) by several inches. The classes, thresholds and the reading are **not**
   changed: the reading is computed on the primary classes exactly as pre-registered and the report states this property
   next to it. **Declared sensitivity S3 (run-end window; no rule uses it):** $\mathbf P_1$ = median of the raw fixes in
   $[\max(t_{\text{onset}}, t_{\text{run},1} - 10), t_{\text{run},1})$ ("where is WISER when the IMU next calls locomotion"),
   same minimums and classes; it lets a persistent shift be classed relocate. By the same token it also classes as relocate a
   WISER excursion that is still out when the run ends (it cannot tell the two apart — the reason the plan censors them); the
   S3 shares are therefore reported by duration band too. The cross-table primary × S3 is reported.
4. **Strata.** Zone / zone detail, day-night-twilight and weather = the audit's columns of the event (its onset second);
   size bands $[12, 24)$, $[24, 48)$, $\ge 48$ in (the plan's "> 48"; sizes are continuous); duration bands (`dur_s`, seconds
   ≥ 12 in) 2–5, 6–10, 11–30, 31–60, > 60 s **[op]**; run-length bands = the audit's (trimmed length, 1–10 s, 11–30 s,
   31–60 s, 1–5 min, 5–30 min, > 30 min); per animal.
5. **Enrichment per class** = the audit's `enrichment()` (imported unmodified) on the class's events and their matched
   controls: ≤ 6-anchor share ratio, dispersion ratio (and the fix-rate ratio for information, with the audit's
   Amendment-2 caveat), 10-min block bootstrap (block = animal × 10-min bin of the window onset), 1000 replicates, seed =
   the audit's bootstrap seed + 100 + class index. Events without a control are left out (the audit's rule). Pooled is the
   reading's input; within zone (house / field) for information.
6. **Reading, operationalised.** Return share = $n_{\text{return}} / (n_{\text{return}} + n_{\text{ambiguous}} +
   n_{\text{relocate}})$ ≥ 0.5; $\rho_S(\text{return}) \ge 1.5$; its CI lower bound > 1; and — the grammatical reading of
   "with its CI above 1 **and above the relocate class's point estimate**" — the same CI lower bound > $\rho_S(\text{relocate})$.
   The looser reading (point estimate > relocate's point estimate) is reported for information only. If $\rho_S(\text{relocate})$
   is undefined (no relocate event with a control), that condition is not met and the "otherwise" branch applies.
7. **Excursion profile.** Raw 1-s medians (≥ 2 fixes, the audit's I1 estimator) on seconds inside the trimmed run; distance to
   $\mathbf P_0$; onset-aligned $u = s - t_{\text{onset}} \in [-10, 90]$ s (per class: median, quartiles, number of events with
   a value); an end-aligned version ($s - t_{\text{end}} \in [-30, 30]$ s) for information.
8. **Reproduction check.** From the production V3 track, for every event: the V3 reference, size, duration, onset and window
   end recomputed from `run_t0` / `run_t1` with the audit's I1 definition and compared with the event table (exact for the
   integer seconds, ≤ 1e-6 in for positions) — it verifies the time base and the fix set.
9. **`--with-verdicts <file or folder>`.** Reads the Part-2 export (JSON with `rows` / `judgements`, or CSV; a folder = the
   newest export per reviewer). Matching: (animal, `event_id`) of the V3 I1 events when the export carries them, else (animal,
   field-PC onset within 1.5 s). Verdicts normalised to moved / stayed / cannot_tell. Reported: the confusion table (primary
   class × verdict, all classes), Cohen's $\kappa$ on events with class ∈ {return, relocate} and verdict ∈ {stayed, moved}
   (return ↔ stayed, relocate ↔ moved) with a 1000-replicate event bootstrap CI, the same for S3 (declared). Nothing is
   re-tuned on the verdicts. Written into the report (re-rendered from the run's tables), the run dir and the config's
   `validation` block.
10. **Compute.** CPU only, ≤ 6 worker processes (one per animal).

## Amendment (Part 2) 1 (2026-10-05 22:50, operational; written before any verdict exists)

Written by the session implementing Part 2 (`wiser/scripts/make_wiser_event_review.py`) after its self-test and a no-clip
pass on the field data (selection drawn, panels drawn, page built), before any verdict exists. The agent opened no video
frame and no panel image, and saw no Part-1 class. Nothing in Part 2's spec above is changed except where stated; these fix
details the plan leaves open or ambiguous.

1. **Time base.** The audit's event times are aligned seconds $t^{\rm al} = t_{\rm WISER} - \tau^*_a$ — the head-IMU /
   field-PC clock on which the events and the IMU states were defined. Clips, the EVENT bar, the overlay clock and the
   panel all use $t^{\rm al}$. The audit's printed lists show $t^{\rm al} + \tau^*$ (the WISER-stamp time, $\tau^*$ =
   0.10–0.20 s per animal); the difference is below the ±1 s precision of the video file-name time.
2. **Event window and EVENT bar.** I1: $t_{\rm onset}$ = `t0` (first second ≥ 12 in from the run reference),
   $t_{\rm end}$ = `t1` (end of the last ≥ 12-in segment); a multi-segment event is shown as one window — the bar covers
   the gaps between segments too (marking segments would reveal WISER's timing). I2: $[t_{\rm onset}, t_{\rm end}]$ = the
   merged pair window $[c_{\rm first} - 2, c_{\rm last} + 2]$ s (4–4.5 s). Bar = $[t_{\rm onset}, \min(t_{\rm end},
   \text{clip end})]$; when the event outlasts the clip (> 60 s) the page states how long it continues.
3. **Random draws and blind order.** Quartile edges over all 5,411 V3 I1 sizes (14.26 / 16.94 / 22.24 in; Q1 = below the
   25th percentile … Q4 = from the 75th); the 30 largest are removed from the pool; pool sorted by (animal, event_id);
   `numpy.random.default_rng(20261005)`, one draw of 5 without replacement per quartile, Q1 → Q4. The 80 events are shown
   in the order `default_rng(20261006).permutation(80)` under neutral ids W01–W80, so the list does not reveal which
   events are the extremes; the selection set (top-30 rank / random quartile) is revealed with the panel.
4. **Camera zone.** I1: the zone of the run reference $\mathbf P_0$ = (`ref_x`, `ref_y`) (house rectangle of
   `wiser_rois.json` + 14 in, the audit's rule) — where the rat was before the event; the audit's zone column is taken at
   the onset second, i.e. at the first displaced WISER position. I2: the audit's zone at the window start. Result: 26
   house clips (house_2 20, house_1 6), 54 panorama clips.
5. **Overlay.** Besides the plan's items (animal, IR mark, coban, zone, field-PC time, EVENT box) the banner shows the
   review id, the cameras, a reminder to ignore the burnt-in clock, per-view camera labels and "NO VIDEO" where a camera
   has no frames — none derived from WISER or the IMU. The field-PC clock is updated every 0.25 s.
6. **Panel.** Window = the clip window, x-axis = clip time. I1 $\mathbf P_0$ = the audit's reference (median of the V3
   1-s medians over the first 2 s of the trimmed run; Part 1's raw-fix $\mathbf P_0$ is not used — Part 1's code is not
   imported); I2 $\mathbf P_0$ = V3 median over the first second of the window (the plan defines $\mathbf P_0$ only for
   I1). Rows: distance of the raw fixes and of the V3 track from $\mathbf P_0$ (12-in line, run start / end and the
   2-s reference window marked when inside the clip); IMU state per second (`imu_seconds_cache`, `ok` = false shown as
   unusable); cumulative head turn $\psi$ from `turn_net_deg` (shown for I1 too); for I2 a display path heading (1-s
   differences of 0.5-s-half-window V3 medians where ≥ 10 in/s — not the Phase-0 estimator; the audit's Δθ / Δψ are
   printed); an x–y map (WISER frame inches, unverified origin) with the house rectangles. Masked fixes are not drawn.
7. **Verdicts.** The first saved verdict is stored as `verdict_blind` (also exported as `verdict`, the column Part 1's
   `--with-verdicts` reader looks for) and cannot be overwritten; a change after the reveal updates `verdict_final` and
   sets `changed_after_reveal`. "Cannot tell" takes an optional reason (not visible / identity unsure / other). Answer
   values: I1 `moved` / `stayed` / `cannot_tell`; I2 `turned` / `ran_straight` / `cannot_tell`. Join key `event_key` =
   `<animal>|V3|<type>|<event_id>` (and `audit_event_id`). Part 1 should use the blind verdict.
8. **Clip format.** One composite H.264 file per event with `make_imu_video_review`'s layout (imported unchanged): houses
   side by side 3840 × 1656, panoramas stacked 3712 × 2304, 20 fps, h264_nvenc cq 26 (libx264 fallback); 3 render
   workers (≤ 6 concurrent ffmpeg with the parallel job).
9. **Population.** Events after 2026-09-11 19:40 carry a page note that five non-implanted females are also in the
   paddock (W42, W56).

## Amendment (Part 1) 2 (2026-10-05 23:00, written AFTER the pooled numbers of Part 1 were seen; no class, window, threshold or reading rule changed)

Run `D:\Field2026_analysis_out\2026c\wiser_i1_return_20261005_2236` (report
`results/2026c/wiser_baseline/reports/wiser_baseline_i1_return_2026c.md`). Changes after its first render:

1. **Rendering bug (fixed; no number changed).** The profile filter used `PT.align`, which pandas resolves to the
   `DataFrame.align` method, so the first render's excursion-profile figure and §4 table were empty. Fixed to `PT["align"]`
   and re-rendered from the run's saved tables with a new `--render-only <run>` option (no recompute; every table, the
   enrichment and the reading are those of the run).
2. **Descriptive additions (post hoc, declared; no rule uses them):** the reading rule evaluated on each sensitivity's classes
   (S1, S2, S3 — information only; the pre-registered reading uses the primary classes); report bullets on S1 (why the
   10-s pre-onset reference gives a higher return share), on the persistence of the larger events, and a one-line profile
   summary; the number of censored events whose window ends exactly at the run end.
3. **`--with-verdicts` reader aligned with Part 2's export** (Amendment (Part 2) 1 item 7 and
   `wiser/configs/wiser_event_review_2026c/README.md`), made before any verdict exists: `verdict_blind` read first (= `verdict`;
   `verdict_final` ignored), `event_key` / `audit_event_id` join, `onset_al_ms` for the onset fallback, exports without a saved
   verdict (e.g. the placeholder) skipped, `changed_after_reveal` counted and reported, and nothing is written when no saved
   I1 verdict exists. It changes no class. Selftest: 15 checks, all pass (synthetic data, incl. a Part-2-format folder with
   the placeholder).
