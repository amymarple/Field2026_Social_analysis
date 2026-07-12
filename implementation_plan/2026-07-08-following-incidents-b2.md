# Implementation plan — Following incidents (Phase B2): incident recall + video audit + camera routing

**Date:** 2026-07-08
**Status:** planned. **Additive only** — Phase B (`analyze_following_structure.py`) stays intact.

## Goal and motivation

Phase B reports pair/night structure via the **peak** directional follow score (`max f*` over lags
1–30 s) + circular-shift null — a good conservative structure/null layer, but it **compresses event
frequency**: one max score per pair/night hides how *often* strict trailing happens. The user
observes on video that strict trailing is common, so the peak-score framing likely **under-represents
incident frequency**. Phase B2 adds a **human-readable incident layer** and a **video-audit +
camera-routing** workflow to measure detector recall against video, without discarding Phase B.

Framing (required): *"The original Phase B score detects significant lagged path reuse but compresses
event frequency into pair/night peak scores. Phase B2 estimates incident frequency directly and
validates detector recall against video-observed strict trailing."* Avoid "following is weak/rare"
unless episode-level AND video-audit metrics support it.

## Constraints

Additive scripts/modules only; no destructive rewrites; keep all existing Phase B outputs; every
threshold configurable (CLI + config); provenance in `run_manifest.json`; small smoke tests with
synthetic WISER coordinates and fake camera polygons. Inch frame is UNVERIFIED — camera polygons are
defined **empirically in WISER inches** (the calibration file IS the mapping), so routing needs no
georeference; "leader/follower" stays temporal order, not geometry.

## New files (all additive)

- **`src/following_incidents.py`** — episode extraction across ALL lags + incident metrics + audit
  classifier.
- **`src/camera_router.py`** — WISER (x,y) footprint → ranked camera channels.
- **`scripts/analyze_following_incidents.py`** — Phase B2 driver (incident metrics + video queue +
  report).
- **`scripts/audit_following_video.py`** — video false-negative audit driver.
- **`scripts/selftest_following_incidents.py`** — offline synthetic tests.
- **`configs/camera_visibility_map.yaml`** — editable per-channel visibility polygons (TEMPLATE, seeded
  with UNCALIBRATED placeholders from the paddock boundary; the user edits).
- **`configs/video_audit_manual.csv`** — editable manual audit input (TEMPLATE + example row).
- Outputs → `outputs/following_incidents_2026-06-28_to_2026-07-06/` and
  `outputs/following_video_audit/`.

## Method

### 1. Strict-following incidents (`following_incidents.py`)
Reuse Phase B's grid + per-bin follow test (`w.build_following_grid`, `w._pair_follow`, `follow_radius_in`).
For each night, ordered pair (A→B):
- `strict_following_episodes(grid, A, B, lags=1..30, R, cos_thresh, min_bout_s, max_gap_s)`: for **every
  lag**, compute the follow mask, extract gap-tolerant runs ≥ `min_bout_s`, tag each with its lag; then
  **merge overlapping/adjacent runs (same ordered pair) into episodes** (union of time intervals).
  Each episode keeps: start/end (grid s → local EDT), duration, mean separation, mean heading cosine,
  and the **lag distribution** (set/histogram of lags that fired, median lag). This does NOT rely on a
  single best lag, so lag-varying trailing is not missed.
- Per (night, pair, direction): `strict_follow_episode_count_per_hour`,
  `strict_follow_total_duration_per_hour`, `fraction_of_movement_bouts_that_are_following` (follower
  bouts overlapping an episode ÷ follower movement bouts), `median_episode_duration_s`,
  `p95_episode_duration_s`, `episodes_per_active_hour` (denominator = follower moving-hours). All
  denominators explicit + configurable. Keep the Phase-B `peak_score`/`z` columns alongside (joined),
  never as the sole reader-facing stat.

### 2. Camera router (`camera_router.py`)
- `load_visibility_map(path)` → channels with `polygon` (WISER-inch [[x,y],…]) or `bbox`, `priority`,
  `notes`, optional `examples`.
- `route_event(footprint_xy, vis_map, margin_in)` → ranked channels: per channel `coverage` = fraction
  of the event footprint inside its polygon; `score = coverage × priority`; rank desc. Returns
  `channel_rank_1/2`, `confidence` (best coverage, discounted near boundaries), `reason` (coverage
  breakdown), `near_boundary` (footprint split across channels or best coverage in (0.1,0.9)). Footprint
  = leader+follower positions over the episode ± margin.
- Config template seeds CH01–CH05 with placeholder polygons carved from the boundary rect
  `[247.15, 786.02, 542.31, 888.27]`, clearly marked **UNCALIBRATED — edit me**, with an `examples`
  block the user fills (WISER x/y → expected channel).

### 3. Connect routing → video queue (in the B2 driver)
For each candidate episode: footprint from leader/follower positions during the episode → `route_event`
→ write `strict_following_video_queue.csv` (`event_id, night, t_start_local, duration_s, leader,
follower, median_lag_s, mean_sep_in, mean_cos, channel_rank_1, channel_rank_2, confidence, reason`),
sorted for fast human inspection (longest / highest-confidence first). Also stamp channel columns onto
the Phase-B `top_following_bouts` equivalent.

### 4. Video false-negative audit (`audit_following_video.py`)
Reads `configs/video_audit_manual.csv` (schema: `date, start_local, end_local, leader, follower,
confidence, notes, camera_channel?, wiser_zone?`). For each marked event: convert local EDT→UTC, pull
WISER fixes ±`margin_s` (default 60) for leader+follower, build a local grid, run
`strict_following_episodes`, and classify:
- **detected** (an episode for that ordered pair overlaps the window), else diagnose by relaxing ONE
  constraint at a time — **missed because**: lag outside 1–30 · heading cutoff · distance radius ·
  moving mask · identity/tag dropout (gap in window) · clock/alignment (no overlapping WISER time) ·
  visually-strict-but-not-WISER-geometrically-strict (no single relaxation recovers it).
Outputs: `video_audit_events.csv` (per event + class + which relaxation recovered it),
`video_audit_detection_summary.csv` (recall, counts), `video_audit_failure_modes.csv` (per-mode
counts), optional per-event trajectory plots.

### 5. Report (`following_structure_phaseB2_incident_audit.md`, NEW file)
Four explicit sections: (a) pair/night structure (herd vs dyads — summarize Phase B, don't rerun);
(b) incident frequency (episodes/hr, duration/hr, fraction-of-bouts — per night/pair/animal);
(c) video calibration (recall vs marked events + failure modes); (d) camera-routing confidence. Plus a
`## Definitions` section (formula + text) per the `analysis-definitions` skill. Use the required
framing; no "rare" claim unless episode + audit metrics support it.

## Verification

- `scripts/selftest_following_incidents.py` (offline, PASS): (i) planted trailing pair on synthetic grid
  → episodes extracted, `episodes_per_hour`>0, fraction-of-bouts high; a lag-varying trail is still
  merged into one episode; (ii) fake camera polygons → `route_event` ranks the correct channel, flags a
  boundary-straddling footprint; (iii) audit classifier: a planted detected event → "detected"; a
  planted event with distance just over R → "missed because distance radius"; a tag-gap event → "missed
  because identity/tag dropout".
- Smoke: B2 driver on 1–2 nights; audit driver on the template's example row.
- Full B2 run on the non-fireworks nights; provenance in `run_manifest.json`.
- Docs: this plan + index; change_log + index; ANALYSIS_STATUS row (additive B2 note).
