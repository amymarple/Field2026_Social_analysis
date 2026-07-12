# Implementation plan — Episode Browser (exploratory episode repository + GUI)

**Date:** 2026-07-02
**Scope tier:** Large (new subsystem, new data schema, new public data model + prototype UI)
**Branch base:** `wiser-analysis-clean`
**Status:** implemented + verified in the same session; this plan is the design of record.

## 2026-07-11 continuation: label existing strict-following incidents

### Goal and current problem

The real browser queue currently contains only 14 per-animal route bouts. The existing
Phase B2 analysis already exports strict lagged path-reuse incidents, but none are present
in the Episode Browser, so searching for `following` returns no real candidates and the
selected workspace cannot review a leader/follower pair.

Add the smallest useful extension:

```text
existing Phase B2 incident export
-> every incident overlapping the fixed 15-minute slice
-> pair episode with detector provenance + post-hoc following label
-> existing selected-episode evidence and append-only review
```

### Input and observed slice

- Read-only source:
  `wiser/outputs/following_incidents_2026-06-28_to_2026-07-08/strict_following_episodes.csv`
  plus its `run_manifest.json`.
- Detector is reused unchanged: 1 s grid; 5 s median-smoothed positions; both subjects
  moving; lag 1-30 s; lagged separation below 24 in; heading cosine above 0.5;
  gap tolerance 2 s; minimum run 3 bins. The inch frame is unverified and
  leader/follower means temporal order, not dominance or physical geometry.
- Exactly 16 exported incidents overlap June 30, 2026, 21:00-21:15 EDT. Import all 16;
  do not rank, cap, or select a subset.
- The source stores `t_end_local` as the timestamp of the final inclusive 1 s grid bin.
  Normalize to the browser's half-open canonical interval by adding 1 s to `t_end`.
  Preserve the source row id and original inclusive timestamp in provenance.

### State model and labeling

- Register `wiser_lagged_path_reuse_v1`, with low-level pair features
  `median_lag_s`, `min_lag_s`, `max_lag_s`, `n_lags_fired`, `mean_separation_in`,
  `mean_heading_cosine`, and `n_follow_bins`.
- Each imported record has `level: pair`, ordered `subject_ids: [leader, follower]`, and
  an explicit `role_map` in `linked_assets`.
- Attach `following` and `strict_trailing_candidate` only after import as post-hoc labels.
  The UI must call these candidates; WISER alone does not validate social following.
- Keep lens scores absent. Add QC flags for the unverified WISER frame, candidate
  behavior interpretation, and unverified camera routing.
- Reconstruct the full pair footprint from the bounded WISER sidecar and reroute with
  the browser's 15 in jitter margin. The existing map remains `confirmed: false`.

### Storage and UI

- Preserve the existing route-only generated files. Write a new v2 bounded store and
  manifest containing 14 route bouts plus 16 following candidates; normal rendering
  still uses only the bounded WISER evidence sidecar and never opens a daily gzip.
- Route-bout imported coverage remains defined only by `wiser_route_bout_v1`; pair
  following candidates must not change that denominator or be called missing data.
- Add Level and Label filters, show labels in the queue and selected provenance, and
  render pair roles as `leader -> follower` rather than an unordered subject list.
- Keep the existing selected-episode, weather, video, QC, annotation, blind-evaluation,
  and export behavior. Do not redesign the discovery platform.

### Verification

- Assert 16/16 overlapping source incidents enter the v2 store and all retain stable
  source-event provenance, ordered identities, pair level, and following labels.
- Assert the v2 store contains 30 unique episodes: 14 route bouts + 16 pair incidents.
- Validate the registry/schema, canonical UTC bounds, half-open end normalization,
  absent lens scores, and route-bout coverage invariance.
- Confirm normal app code has no daily WISER reader and no global video path.
- Browser-test search/filter `following`, pair role display, state-model provenance,
  synchronized two-subject WISER evidence, unverified video routing, and annotation
  history at desktop and narrow widths.

### Non-goals

- No detector retuning, new following inference, dominance claim, video recall claim,
  camera calibration, cross-day queue, or broad frontend rewrite.

## 2026-07-10 continuation: real selected-episode vertical slice

### Goal and current problem

Refactor the prototype only far enough to demonstrate one real path end to end:

```text
real route-bout candidate -> selected episode -> synchronized WISER/weather/video/QC
-> append-only judgment
```

The current app loads the synthetic store wholesale, keeps evidence panels on a global
time window, and can render a detail record while its status strip still says no episode
is selected. It also computes one episode-tiling percentage from the filtered table,
which conflates source-data availability with the fraction represented by an importer.

### Real integration target

- Local window: **2026-06-30 21:00-21:15 EDT**, labeled
  **pre-night-rain integration slice** relative to the recorded nighttime rain onset
  near 22:20-22:30. It carries no storm-response label or interpretation.
- Source: read-only WISER incremental backup for 2026-06-30, five valid tags after
  identity cutoffs, native **inch** frame with unverified offset origin.
- Episodes: reuse the existing route-bout cut unchanged (smoothed speed above the
  established threshold, gap <=2 s, duration >=3 s, displacement >=15 in). Run it
  uncapped inside the bounded window and import every resulting bout.
- Normal UI inputs: a small real episode Parquet plus a bounded WISER evidence Parquet.
  The Streamlit app must not open the complete daily gzip.
- Video: route the selected episode footprint through
  `camera_visibility_map.yaml` with a 15 in jitter margin. Because the map declares
  `confirmed: false`, every candidate remains visibly **unverified**. Resolve a closed
  hourly recording only for the selected candidate; never attach CH01 globally.

### Coverage definitions

Let $W$ be the configured window and $B_W$ its one-second bins. For subject $s$:

$$
C_{data}(s)=\frac{1}{|B_W|}\sum_{b\in B_W}
\mathbf{1}[n_{valid}(s,b)>0]
$$

where $n_{valid}(s,b)$ is the count of valid WISER fixes in bin $b$ after tag
cutoffs and QC validity rules. **Text:** percentage of source time with tracking
data. Units: percent; range 0-100%. Missing bins may be `tracking_lost` or
`no_data`; they are data/QC gaps.

For imported real route episodes $E_s$:

$$
C_{episode}(s)=\frac{\left|\bigcup_{e\in E_s}
([t_{e,0},t_{e,1}]\cap W)\right|}{|W|}
$$

**Text:** percentage of source time represented by the route-bout importer. Units:
percent; range 0-100%. The complement is **not represented by this importer**, not
missing data, occlusion, or tracking loss. Search/ranking filters must not alter
either denominator.

### Interfaces and selected-episode flow

- Add a bounded `EpisodeRepository` (`query_index`, `get_episode`, record span) so
  the queue reads only index columns and one selected nested record is materialized.
- Add `SelectedEpisodeContext`, `CoverageSummary`, `CameraRoute`, and
  `EvidenceStatus` data-layer values; keep Streamlit rendering out of the utilities.
- Use `selected_episode_id` as the sole standard-review selection state. Initialize
  it before status/header rendering and derive one evidence window from the episode
  bounds plus 5 s padding.
- Render a compact selected header; synchronized timeline, WISER, weather, and
  on-demand four-frame video; separate data-availability and importer-coverage
  strips; and an evidence/judgment rail with provenance, availability, absent lens
  states, annotation history, and append-only verdicts.
- Preserve blind evaluation and CSV export semantics without expanding this slice
  into saved cohorts, comparison tools, adjudication, or cross-day discovery.

### Verification

- Prove the bounded store contains every uncapped bout from the configured window.
- Prove normal app rendering never opens the full daily WISER gzip.
- Unit-test both coverage denominators and ensure `not represented by importer` is
  never emitted as a data/QC gap.
- Test camera routing for no candidate, single unverified candidate, and boundary /
  multiple candidates; confirm no blanket CH01 asset exists.
- Browser-test selection synchronization, real WISER/weather/video/QC evidence,
  append-only annotation persistence, missing/unverified states, blind score hiding,
  and desktop/narrow non-overlap.

## Goal & motivation

Build a researcher-facing **Episode Browser**: inspect, filter, sort, annotate, and
export candidate *behavioral episodes* from the field recordings. An **episode** is a
time-bounded unit of being-in-a-state (delimited by entry/exit transitions), **not** a
human behavior label. The browser *consumes* episodes; it does not produce or correct
tracks (that is the CV pipeline / SLEAP / idtracker.ai / CVAT job).

## Current problem (why now)

There is no substrate that lets a researcher look across modalities at "interesting
stretches" and judge them. The pilot analyses (WISER directions 1–3, CV shelter, audio)
each produce their own tables; nothing ties a time-bounded behavioral unit to its
provenance, its data-quality caveats, and a human verdict. Before real CV segmentation
exists, we need a data model + UI that already **survives field mess** (unknown identity,
ID swaps, gaps, fogged views, WISER dropout, conflicting sources) so the design is not
retrofitted onto clean toy data.

## Design invariants (non-negotiable)

1. **Completeness is the product; scores are UI.** Every segmented episode enters the
   store. `lens_scores` filter/rank only — never gate ingestion.
2. **The blade is not human categories.** Episodes are cut over a low-level **state
   model**; `zones`/`labels` are post-hoc annotations, never used to segment.
3. **The state model is first-class + versioned.** Every episode carries
   `state_model_id` (FK into `state_models.yaml`); the browser can always answer "what
   cut this?" and marks synthetic-cut episodes distinctly. Real + synthetic coexist in
   one store, told apart by the flag — never by separate files. Validation forbids
   `zones` as a model *feature* unless `zone_is_feature: true`.
4. **The substrate tiles; gaps are rendered, not blanked** (coverage view + % tiled).
5. **Blind evaluation exists** so the enrichment showcase is not self-confirming.
6. **Data model fully separated from UI** — logic in `utils/`, `app.py` is view-only.

## Affected / new files

New subsystem under `episode_browser/` (no existing files modified; all existing
analyses preserved):
- `episode_schema.yaml`, `state_models.yaml` — schema + state-model registry.
- `generate_synthetic_episodes.py` — messy synthetic generator (`synthetic_v0`).
- `utils/episode_io.py` (Parquet/JSONL/CSV; derives `duration_s`),
  `utils/validation.py` (schema + registry checks), `utils/coverage.py` (tiling/gaps),
  `utils/query.py` (filter + lens ranking, absence≠0), `utils/annotations.py`
  (append-only writers), `utils/load_layout.py` (read-only repo-config adapters).
- `app.py` — Streamlit UI (table / detail / coverage / timeline / field / summary /
  annotate + blind-eval).
- `selftest.py` — offline data-layer verification. `README.md`, `requirements.txt`,
  `.gitignore`.

## Inputs / outputs

- **Inputs (read-only, optional):** `cv/configs/field_layout.json`
  (cm, origin A0), `wiser/configs/wiser_rois.json` (WISER inches),
  `wiser/configs/rat_identities.csv` (shortid→name, Sova `valid_until`).
  All degrade gracefully when absent → synthetic-only behavior.
- **Outputs (git-ignored):** `data/synthetic_episodes.{parquet,jsonl}`,
  `data/coverage_gaps.jsonl`; `outputs/annotations/*.jsonl`, `outputs/evaluations/*.jsonl`
  (new, timestamped, append-only, never overwriting).

## Schema (confirmed against the spec)

Fields: `episode_id, schema_version, state_model_id, level(per_animal|pair|group|
environment), subject_ids(list, allows 'unknown'), subject_confidence, t_start, t_end,
state_vector, state_before, state_after, zones(probabilistic), labels(multi), source_streams,
boundary_confidence, identity_confidence, tracking_quality, qc_flags, lens_scores(optional;
absence first-class), environment_context, linked_assets, notes, expert_annotations`.
`duration_s` derived at load. On disk: Parquet primary, JSONL alt, CSV lossy export only.

## Timestamp / coordinate assumptions

- Time is Unix-ms UTC (matches WISER); the UI labels time UTC and assumes **no**
  cross-device sync (video/audio are EDT wall-clock).
- WISER inches vs field cm are **not** unit-convertible until georeference is confirmed;
  the field view keeps them separate and does not overlay zones on the cm frame.

## Addendum — video preview

Added `utils/video_preview.py` and a Detail-tab filmstrip that **subsamples** a few
frames across an episode's span (fast ffmpeg `-ss` seeks, downscaled — no full decode),
located via `linked_assets`. Honors the recorder safety rule (reads only CLOSED `_to_`
files; refuses an open hour). ffmpeg is an external binary (PATH /
`EPISODE_BROWSER_FFMPEG` / Reolink `bin`), optional — without it only the preview is
disabled. Synthetic episodes link to a tiny on-demand stand-in clip
(`data/sample_clip.mp4`) so the path is exercisable before real footage. Verified via the
extended `selftest.py` (frame extraction + open-file refusal) and `AppTest`.

## Non-goals

- Not a CV tracking-correction / frame-by-frame annotation tool.
- No real segmentation model in this pass (`synthetic_v0` is a placeholder; a real
  `kinematic_v1`/proximity model + ingest loader is future work).
- No claim that synthetic episodes reflect real behavior — they exist to stress the UI.

## Verification

- `python selftest.py` — offline data-layer checks (validation incl. bad `state_model_id`
  and zone-as-feature rule; JSONL + Parquet round-trip preserving nested fields;
  `duration_s` derivation; coverage tiling + gap rendering + % tiled; query lens ranking
  with absence≠0; append-only annotation + blind-eval logging) → PASS.
- `python generate_synthetic_episodes.py` — validates before writing; refuses to write an
  invalid store; produces all four levels + gap sidecar.
- `app.py` boots headless and runs clean through Streamlit `AppTest` (7 tabs, metrics
  compute; no exceptions).
