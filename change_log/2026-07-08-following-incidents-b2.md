# Change log — Following incidents (Phase B2): incident recall + video audit + camera routing

**Date:** 2026-07-08
**Status:** ⚠️ candidate. Implemented, self-tested, run on all 8 nights. **Additive** — Phase B
(`analyze_following_structure`) outputs are untouched.
**Plan:** [implementation_plan/2026-07-08-following-incidents-b2.md](../implementation_plan/2026-07-08-following-incidents-b2.md)

## Motivation

Phase B reported pair/night structure via the **peak** follow score (`max f*` over lags 1–30 s) +
circular-shift null — a good conservative structure/null layer, but one max score per pair/night
**compresses event frequency** and made strict trailing look rarer than it is on video. Phase B2 adds
a **human-readable incident layer** + a **video-audit** + a **WISER→camera router**, without changing
Phase B. Required framing (used verbatim in the report): *"The original Phase B score detects
significant lagged path reuse but compresses event frequency into pair/night peak scores. Phase B2
estimates incident frequency directly and validates detector recall against video-observed strict
trailing."*

## What was added (all additive)

- **`src/following_incidents.py`** — `strict_following_episodes` (extracts follow runs across **all**
  lags 1–30 s and merges overlapping detections per ordered pair into episodes, preserving the
  per-episode lag distribution), `pair_incident_metrics` (per-hour rates + fraction-of-bouts +
  duration stats with explicit denominators), `moving_bouts_grid`, `episode_footprint`, and
  `classify_audit_event` (the video-audit decision tree).
- **`src/camera_router.py`** + **`configs/camera_visibility_map.yaml`** (TEMPLATE) — WISER-inch
  footprint → ranked camera channels (coverage × priority), confidence, reason, near-boundary flag.
  Polygons are calibrated **empirically in WISER inches**, so no georeference is needed.
- **`scripts/analyze_following_incidents.py`** — Phase B2 driver: incident metrics + camera routing
  → `strict_following_video_queue.csv` + report `following_structure_phaseB2_incident_audit.md`.
- **`scripts/audit_following_video.py`** + **`configs/video_audit_manual.csv`** (TEMPLATE) — you mark
  video-observed trails; it pulls WISER ±60 s and classifies detected vs missed (+ failure mode).
- **`scripts/calibrate_camera_visibility.py`** + **`configs/camera_visibility_examples.csv`** — the
  calibration kit: `--reference` renders a **WISER reference frame** (occupancy backdrop + boundary +
  labeled ROIs: the two houses, refuges, water, tunnel) so you can relate WISER (x,y) to landmarks
  seen on video; `--from-examples` builds each channel's visibility polygon as the **convex hull of
  logged example points (+ margin)** and writes the yaml + a verification figure; `--gui` draws
  polygons interactively (repo `place_*` style; `--overlay-layout` adds a faint, explicitly-unaligned
  `field_layout_map.png` backdrop). meta.confirmed flips true only when every channel has ≥3 example
  points. `--from-examples`/`--reference` are **batch** (no window, Agg backend); only `--gui` opens a
  window (interactive backend selected at import).
- **`scripts/selftest_following_incidents.py`** — synthetic coords + fake polygons + calibration
  hull/roundtrip, PASS.
- Outputs → `outputs/following_incidents_2026-06-28_to_2026-07-06/`, `outputs/following_video_audit/`,
  and `outputs/camera_calibration/` (reference + verification figures).

## Key results (candidate)

- **Strict trailing is frequent but BRIEF — the peak score compressed it.** **1429 strict-following
  episodes** across 8 nights, **median 3 s, p95 9 s**. Per-night: **06-28 (release) 454 episodes
  (~57/hr)**, then 12–24/hr; **07-04 (fireworks) elevated (190, ~24/hr)** — matches the field-note
  "increased following post-fireworks." The tiny Phase-B `peak_score` (0.05–0.10) was one compressed
  max over dozens of discrete incidents. **Classify: behavioral — trailing is common, not rare.**
- **Sen leads the top incident pairs** (Sen→Siesta 118, Sen→Hypnos 114 episodes total) — consistent
  with the Phase B / motif Sen-leadership finding, now at the incident level.
- **`fraction_of_movement_bouts_that_are_following` ≈ 0.01–0.05 per ordered pair** — of a follower's
  movement bouts, a few % coincide with trailing any *specific* leader (summed across 4 leaders it is
  higher). Reported per night/pair, never averaged into one number.
- **Camera routing works mechanically** but the map is a **PLACEHOLDER** (`meta.confirmed:false`):
  routing confidences are provisional until `configs/camera_visibility_map.yaml` is calibrated (draw
  real polygons, add `examples`). The queue flags near-boundary episodes to pull ≥2 channels.
- **Video recall is not yet claimed** — the audit runs, but on real data only once the user marks
  events. (Smoke on the fabricated template row → 1 event, correctly a miss.)

## Definitions (headline; full list in the report `## Definitions`)

- **Strict-following episode**: per lag $\ell$, bin $t$ is a follow-bin iff $\text{mov}_A(t)\wedge\text{mov}_B(t{+}\ell)\wedge\lVert\mathbf{x}_B(t{+}\ell)-\mathbf{x}_A(t)\rVert<R\wedge\hat{\mathbf u}_A(t)\cdot\hat{\mathbf u}_B(t{+}\ell)>c$; an episode = connected union over all $\ell\in[1,30]$ of gap-tolerant follow-runs $\ge$ `min_bout_s`. $R=3\times$ jitter floor $=24$ in, $c=0.5$.
- **Incident rates**: episodes/hour $=n_{\text{ep}}/H$; duration/hour $=\sum_e\Delta_e/H$; episodes/active-hour $=n_{\text{ep}}/H^{\text{mov}}_B$ ($H$ = window hours, $H^{\text{mov}}_B$ = follower moving-hours).
- **frac_bouts_following** $=\#\{\text{follower movement bouts overlapping any episode}\}/\#\{\text{follower movement bouts}\}$.
- **Camera coverage** for channel $k$ $=\frac1{|F|}\sum_{p\in F}\mathbb{1}[p\in P_k]$ over the footprint $F$; rank by coverage$\times$priority.
- **Audit classifier**: detected → else relax one constraint at a time (tag-dropout · alignment · moving-mask · distance-radius · heading · lag-range · not-geometrically-strict).

## Verification

- `python scripts/selftest_following_incidents.py` → PASS: planted trail → episodes (lag-varying trail
  merges into one, records ≥2 lags); incident rates > 0; camera router ranks the right fake channel +
  flags a boundary straddle + returns None outside all polygons; audit classifier returns detected /
  missed_distance_radius / missed_tag_dropout on planted cases.
- Full B2 run on all 8 nights (~2 min, `cv` env). Video-audit smoke on the template row runs
  end-to-end.

## Follow-ups

- **Calibrate `camera_visibility_map.yaml`** — two tools shipped:
  - **Image-based (preferred)** `place_camera_landmarks.py` + `src/camera_calibration.py`: `--extract`
    grabs a channel frame via cv2 (verified: real CH01 daytime frame → `outputs/camera_calibration/`),
    `--gui` marks landmarks in that frame and tags each with a known-WISER ROI, fitting a **pixel→WISER
    homography** (DLT, numpy) → the channel's WISER visibility polygon; `--build` does it from a saved
    landmarks json / CSV. Homography **RMS (in)** is written per channel as a QC signal. Homography +
    polygon math self-tested (RMS ~1e-11).
  - **WISER-space** `calibrate_camera_visibility.py`: `--reference` (WISER frame with labeled ROIs),
    `--from-examples` (hull of logged points), `--gui` (draw polygons). `--overlay-layout` adds a
    faint unaligned `field_layout_map.png`. Backend fix: interactive modes switch to **TkAgg** (the
    env's default `qtagg` silently fell back to Agg).
  - `meta.confirmed:true` once every channel is calibrated. Until then routing is provisional.
  - **Decoder limit (CH01/CH02) — SUPERSEDED, see 2026-07-09 diagnosis.** The mechanism I logged
    here on 2026-07-09 ("coded-frame DATA VOLUME / decoder can't decode the big daytime keyframe;
    night IR decodes fully") is **WRONG and retracted**. The byte-level root cause is a **2,000,000-byte
    keyframe cap in the camera encoder** — the daytime bottom band is **never recorded**, so no decoder
    can recover it (it's not a decode limit). Capped GOPs cluster through bright hours (~20–41 %); night
    IR (~1.1 MB keyframes) is never capped. Authoritative write-up:
    [docs/methods/duo3_keyframe_2mb_cap.md](../docs/methods/duo3_keyframe_2mb_cap.md) and
    [change_log/2026-07-09-duo3-keyframe-cap.md](2026-07-09-duo3-keyframe-cap.md). What still holds:
    calibration uses a **night frame** (`--extract` defaults CH01/CH02 to a night hour); **B/W 24/7 is
    NOT a fix**; CH03/CH05 unaffected; homography/GUI/router work on the night frame. The real fix is
    camera-side (I-frame Interval 2x→1x).
- **Mark real video events** in `video_audit_manual.csv` → run the audit → get detector recall +
  failure-mode breakdown; then (and only then) make a recall claim.
- If recall is high but per-pair `frac_bouts_following` stays low, that is "trailing is common but each
  follower splits its trailing across several leaders" — report it that way, not as "weak."
