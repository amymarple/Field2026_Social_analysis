# Following incidents & video audit — Phase B2 report

**Generated (UTC):** 2026-07-08T17:23:06.226837  
**Commit:** `384d1d019d914c19daa3411b2397adeca5e29812`  
**Nights:** 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05  
**Follow radius:** 24 in; lags 1–30 s; heading cos>0.5; min episode 3 s  
**Frame:** inches, UNVERIFIED — 'leader/follower' = temporal order, not geometry  

> **Why B2 exists.** The original Phase B score detects significant lagged path reuse but **compresses event frequency into pair/night peak scores**. Phase B2 estimates incident frequency **directly** (episodes extracted across all lags 1–30 s and merged) and validates detector recall against video-observed strict trailing. Phase B is unchanged and remains the conservative structure/null layer.

## (a) Pair/night structure — herd vs stable dyads

- Unchanged from Phase B (see `following_structure_.../following_structure_report.md`): co-movement is **promiscuous/herd, not stable dyads** (top pair reshuffles nightly), with **Sen** the most frequent leader. B2 does not re-litigate this; it adds frequency + recall.

## (b) Incident frequency — how often does strict trailing happen?

- **1429 strict-following episodes** across 8 nights (median 3 s, p95 9 s). Per-night counts in `incident_summary_by_night.csv`; per (night, ordered pair) rates in `incident_metrics_by_pair_night.csv`.
- These are **incident-level** rates (episodes/hour, duration/hour, fraction-of-movement-bouts-that-are-following) — the reader-facing frequency the Phase-B peak score compressed.

### Top ordered pairs by episodes/hour

| leader → follower | episodes/hr | frac of follower bouts | total episodes |
|---|---|---|---|
| Sen → Siesta | 1.87 | 0.02 | 118 |
| Sen → Hypnos | 1.82 | 0.03 | 114 |
| Hypnos → Nox | 1.38 | 0.02 | 87 |
| Siesta → Hypnos | 1.35 | 0.02 | 84 |
| Sen → Nox | 1.34 | 0.02 | 84 |
| Siesta → Nox | 1.31 | 0.02 | 82 |
| Sen → Dormi | 1.28 | 0.02 | 81 |
| Hypnos → Siesta | 1.28 | 0.01 | 80 |
| Dormi → Hypnos | 1.13 | 0.01 | 72 |
| Nox → Siesta | 1.12 | 0.01 | 70 |

- Per-animal totals (as follower / as leader) in `incident_by_animal.csv`. Phase-B `peak_score`/`z` are carried in `incident_metrics_by_pair_night.csv` but are **not** the reader-facing frequency statistic.

## (c) Video calibration — does WISER catch human-observed trailing?

- Run `scripts/audit_following_video.py` after marking events in `configs/video_audit_manual.csv`. It pulls WISER ±60 s per marked trail and classifies detected vs missed (lag / heading / radius / moving-mask / tag-dropout / clock-alignment / not-geometrically-strict), writing `video_audit_events.csv`, `video_audit_detection_summary.csv`, `video_audit_failure_modes.csv`.
- **Until that audit is run, no recall/false-negative claim is made here.**

## (d) Camera-routing confidence

- **1429/1429** episodes routed to a channel; **1429** flagged near a channel boundary (pull ≥2 channels). Queue: `strict_following_video_queue.csv` (sorted by routing confidence then duration).
- Camera map **confirmed: False**. **PLACEHOLDER polygons** — routing confidences are provisional until `configs/camera_visibility_map.yaml` is calibrated (add `examples`, draw real polygons, set `meta.confirmed: true`).

## How to use the queue

`strict_following_video_queue.csv` gives, per episode: local-EDT start, duration, leader, follower, median lag, mean separation, heading cosine, and recommended channel(s). Sort/filter it, open the channel at the start time, and confirm strict trailing on video.

## Definitions

Units: **inches**; time on a 1 s grid, positions 5 s-median smoothed; "leader/follower" is temporal
order, not geometry (inch frame UNVERIFIED). $\text{mov}_A(t)$ = moving mask; $R$ = follow radius;
$c$ = heading-cosine cutoff; $\ell$ = lag (s).

### Strict-following episode (merged across all lags)
For lag $\ell$, bin $t$ is a follow-bin iff
$\text{mov}_A(t)\wedge\text{mov}_B(t{+}\ell)\wedge\lVert\mathbf{x}_B(t{+}\ell)-\mathbf{x}_A(t)\rVert<R
\wedge \hat{\mathbf u}_A(t)\cdot\hat{\mathbf u}_B(t{+}\ell)>c$. Per lag, follow-bins are grouped into
gap-tolerant runs $\ge$ `min_bout_s`; an **episode** is a connected union over **all** $\ell\in[1,30]$
of those runs. **Text:** a sustained leader→follower trail; unlike Phase B it does not fix one best
lag, so a trail whose lag drifts is one episode (its `lag_hist` records which lags fired). Range: a
time interval $\ge$ `min_bout_s` seconds.

### Incident rates (per night, ordered pair)
$$ \text{episodes\_per\_hour}=\frac{n_{\text{ep}}}{H},\quad
   \text{duration\_per\_hour}=\frac{\sum_e \Delta_e}{H},\quad
   \text{episodes\_per\_active\_hour}=\frac{n_{\text{ep}}}{H^{\text{mov}}_B} $$
where $H$ = window hours, $\Delta_e$ = episode duration (s), $H^{\text{mov}}_B$ = follower moving-hours
($\#\text{moving bins}\times\text{bin\_s}/3600$). **Text:** how often / how long strict trailing
occurs; denominators are explicit. Range $[0,\infty)$.

### Fraction of movement bouts that are following
$$ \text{frac\_bouts\_following}=\frac{\#\{\text{follower movement bouts overlapping any episode}\}}
   {\#\{\text{follower movement bouts}\}} $$
**Text:** of the times the follower travels, the share that coincides with trailing the leader. Range
$[0,1]$. `median/p95_episode_duration_s` are the episode-duration order statistics.

### Peak score $f^{\ast}$ and null $z$ (Phase B, carried alongside)
$f^{\ast}_{A\to B}=\max_\ell f_{A\to B}(\ell)$ and its circular-shift $z$ (see the Phase B report).
**Text:** the conservative structure/null layer; reported next to the incident rates, never as the
sole reader-facing statistic.

### Camera routing (per episode)
Footprint = leader+follower positions during the episode. For channel $k$ with visibility polygon
$P_k$: coverage $=\frac1{|F|}\sum_{p\in F}\mathbb{1}[p\in P_k]$; score $=$ coverage $\times$
priority$_k$; channels ranked by score. **Text:** which video channel(s) to inspect; confidence = best
coverage (discounted if the footprint straddles a boundary). Polygons are calibrated empirically in
WISER inches (`configs/camera_visibility_map.yaml`) — no georeference needed.

## Outputs

`incident_metrics_by_pair_night.csv` · `incident_summary_by_night.csv` · `incident_by_animal.csv` · `strict_following_episodes.csv` · `strict_following_video_queue.csv` · `run_manifest.json` · `plots/`
