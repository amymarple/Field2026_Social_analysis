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
