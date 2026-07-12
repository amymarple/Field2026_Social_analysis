# Change log — Episode Browser (exploratory episode repository + prototype GUI)

**Date:** 2026-07-02
**Commit:** uncommitted at time of writing.
**Plan:** [Episode Browser implementation plan](../implementation_plan/2026-07-02-episode-browser.md)
**Scope tier:** Large (new subsystem, new data schema, new prototype UI).

## What changed

New self-contained subsystem `episode_browser/` — a light, researcher-facing browser for
time-bounded **behavioral episodes**. It *consumes* episodes; it does not produce or correct
tracks. No existing files were modified; all prior analyses are preserved.

- **Schema + registry.** `episode_schema.yaml` (full extensible schema; `duration_s` derived
  at load, never stored) and `state_models.yaml` (the state-model registry — every episode
  carries `state_model_id`; `synthetic_v0` is `is_synthetic: true`; validation forbids `zones`
  as a model *feature* unless `zone_is_feature: true`).
- **Data layer (`utils/`, no UI imports):** `episode_io.py` (Parquet primary / JSONL alt /
  CSV lossy-export; nested fields JSON-encoded losslessly; derives `duration_s`),
  `validation.py` (schema + registry checks, incl. unregistered `state_model_id` and the
  zone-as-feature rule), `coverage.py` (per subject×level tiling, gap reasons, % tiled),
  `query.py` (filtering + lens ranking where **absence ≠ 0**), `annotations.py` (append-only,
  timestamped writers for standard annotations + blind-eval logs), `load_layout.py`
  (read-only adapters onto `field_layout.json` / `wiser_rois.json` / `rat_identities.csv`,
  graceful when absent).
- **Synthetic messy generator.** `generate_synthetic_episodes.py` stamps every episode with
  `synthetic_v0` and fabricates field pathologies (unknown identity, ID swaps, un-episoded
  gaps, fogged views, WISER dropout/jitter, conflicting sources, thermal ambiguity) across all
  four levels — including group episodes invisible per-animal and `field_note` episodes that
  overlap behavioral ones. Validates before writing; refuses to write an invalid store.
- **UI.** `app.py` (Streamlit, view-only): Table / Detail / **Coverage (required)** / Timeline
  / Field-zones / Summary / **Annotate (standard + blind-evaluation)**. Opens on a 15-minute
  slice (does not load the whole record); materializes full nested detail only for the selected
  episode; marks synthetic-cut episodes (⚗️).
- **Support.** `selftest.py` (offline data-layer check), `README.md`, `requirements.txt`,
  `.gitignore` (+ `.gitkeep`s). Generated data and human outputs are git-ignored.

## Why

Before real CV/WISER segmentation exists, we need a substrate + UI that already survives field
mess and encodes the project's invariants: completeness is the product (lens scores rank, never
gate), the segmentation blade is a versioned low-level **state model** (not human categories),
gaps are rendered not blanked, and a **blind-evaluation** mode keeps the enrichment showcase
from being self-confirming. Building against synthetic mess now avoids retrofitting the design
onto clean toy data later.

## Verification

Run with anaconda3 base (pandas/numpy/pyyaml/pyarrow/streamlit present):

- `python selftest.py` → **PASS** — 18 checks: schema/registry validation (incl. bad
  `state_model_id` and zone-as-feature rejected), JSONL **and** Parquet round-trip preserving
  nested `state_vector`/`zones`/`lens_scores`, `duration_s` derived (=3.0 s), coverage tiling
  renders an un-episoded interval as a gap with a sane % tiled, lens ranking + range filter with
  absence ≠ 0, append-only annotation + blind-eval logging.
- `python generate_synthetic_episodes.py` → validate PASS; 358 episodes
  (per_animal 339 / pair 12 / group 4 / environment 3); 80 gap rows; Parquet + JSONL written.
- `app.py` boots headless and runs clean through Streamlit `AppTest` — 7 tabs render, header
  metrics compute (38 episodes in the default 15-min window, 62% tiled), no exceptions.

## Addendum — video preview (same day)

Added a **light, subsampled video preview** to the Detail tab.

- **`utils/video_preview.py`** (data-layer): `resolve_video` (episode → clip via
  `linked_assets.video_path` + `video_t_offset_s` + `preview_span_s`), `extract_frames`
  (N evenly-spaced frames via fast ffmpeg `-ss` seeks, one decoded frame each, downscaled
  — never a full decode), `find_ffmpeg` (PATH / `EPISODE_BROWSER_FFMPEG` / Reolink `bin`),
  `is_closed_recording` (refuses an OPEN `..._<start>.mp4` hour; only `_to_` closed files
  are read), and `ensure_sample_clip` (builds a tiny `data/sample_clip.mp4` stand-in via
  ffmpeg `testsrc` on demand).
- **Generator:** video-bearing episodes now carry `linked_assets` pointing at the stand-in
  clip with an in-clip offset, so the preview is exercisable without real footage.
- **UI (`app.py`):** Detail tab shows a filmstrip of subsampled frames (frame count +
  width adjustable), loaded on a button press and cached; warns on open-file links and
  offers to generate the sample clip when missing.
- **Verification:** `selftest.py` extended (now **PASS**, 25 checks) — `resolve_video`
  offset math, open-file refusal, `ensure_sample_clip` creation, and 4 real downscaled PNG
  frames extracted (with `EPISODE_BROWSER_FFMPEG` set to the `audio` env's ffmpeg). Sample
  clip is ~160 KB. `app.py` re-checked clean through `AppTest`.
- **Note:** ffmpeg is an external binary, not a pip dep; without it the preview is disabled
  and every other feature still works.

## Addendum — top search + Video tab (same day)

- **`query.text_search`** — NCBI-style free-text search over an in-memory episode index
  (case-insensitive, AND over tokens; matches episode id, subjects as tag id **and**
  resolved name, labels, zones, source streams, QC flags, notes). Empty query is a no-op.
- **UI:** a search bar + **Run** at the top of the page with **quick-pick chips** (the five
  rats, like NCBI's Human/Mouse/Rat, plus `group`/`pair`/`rain_response`). The search result
  feeds all tabs; the sidebar then narrows it. Uses the canonical keyed-widget +
  `on_click` callback pattern so chips and typing don't fight.
- **Video preview promoted to its own "Video" tab** (8 tabs total) with a self-contained
  episode picker; the Detail tab now points at it.
- **Verification:** `selftest.py` adds `text_search` checks (resolved-name match, zone-label
  match, empty→all, AND semantics); interactive `AppTest` confirms the search box drives
  filtering (28→2 for "Dormi", →0 for a nonsense query) with no exceptions; 8 tabs render.

## Addendum — dashboard layout (same day)

Reworked `app.py` from a tab strip into a **three-region dashboard** matching a supplied
mockup, without moving any logic out of `utils/`:
- **left (sidebar):** view nav (Dashboard / Video / Summary / Annotate), search + quick-pick
  chips, filters, and a "current slice" info card;
- **centre:** an **Episodes** table with **clickable row selection** (`st.dataframe`
  `on_select`, Streamlit 1.45) driving the detail panel, an Export (lossy CSV) button, and
  ProgressColumn confidence/score bars; below it **Timeline / Field-map / Coverage-QC**
  panels (bordered cards);
- **right:** an always-present **Episode Detail** panel — label chips, times/confidence,
  source-evidence buttons (Video jumps to the Video view), lens-score bars (absence shown as
  "absent"), notes, and quick verdict buttons that append annotations.
- Added a header bar + light CSS and a `.streamlit/config.toml` theme (blue accents).
- Fixed a Streamlit 3-level column-nesting limit by rendering the Coverage KPIs as an HTML
  grid instead of nested columns.
- **Verification:** `AppTest` runs clean across all four views (Dashboard/Video/Summary/
  Annotate), detail metrics compute; data-layer `selftest.py` still PASS. Rendered layout
  screenshotted at 1440px — three regions match the mockup.

## Addendum — weather, dates, and trajectory overlays (same day)

- **Real weather.** New `utils/weather.py` loads Ambient Weather Network (AWN) CSV exports
  from `D:\Reolink_record\audio_in\weather_data` (override `EPISODE_BROWSER_WEATHER_DIR`),
  parsing adapted from `audio/analysis/weather.py` (each subsystem stands alone).
  Added a **Weather** dashboard panel (temp line + rain-rate area + humidity summary over
  the window) and a "Weather @ start" row in the Episode Detail (nearest sample). Alignment
  is on **EDT wall-clock** and explicitly labeled **unverified** across devices (weather-
  station clock ≠ WISER/NVR clock), per the repo convention.
- **Dates + Day-1 = epoch.** Time display switched to field-local **EDT**; added a **Day**
  column/label counted from **Day 1 = 2026-06-28** (release), matching FIELD_OBSERVATIONS.
- **Field-map trajectory overlays.** A **Focus rats** control overlays each selected rat's
  trajectory (its episodes connected in time order) on the field map, and — shared with the
  Timeline — filters the lanes to those rats.
- **Verification:** `AppTest` clean across all views incl. the focus/trajectory path
  (`focus_rats` = Siesta+Nox); live app confirmed real AWN data ("Day 3 · 2026-06-30",
  "temp 25–26 °C · humidity ~89% · 4 samples"); `selftest.py` adds weather checks (missing
  dir → empty typed frame, slice_window, nearest) → PASS.

## Addendum — paddock illustration + timeline rain band (same day)

- **Field map = real paddock.** New cached `field_geometry()` reads `field_layout.json` and
  draws the paddock outline, the 15-pole grid (A0–C4), and both shelter footprints (all cm,
  origin A0), with episode positions + focus-rat trajectories on top. Shelter-distance in the
  Detail now uses the real shelter centres.
- **Timeline rain band.** The real AWN rain series is drawn as a blue background band behind the
  episode lanes (per 5-min sample where rain > 0), so storms show directly against behavior.
- **Synthetic window shifted to span the real storm.** Generator default start → 17:00 EDT / 9 h
  (was 21:00 / 3 h) so the real **6/30 17:20–17:55 shower (peak 10.2 mm/hr)** falls inside the
  record; the browser opens on a 60-min slice that includes it. Store is now 1088 episodes.
- **Verification:** live app (default window) confirmed the paddock + pole grid render, the
  timeline shows "blue band = rain", and the weather panel reads "temp 25–33 °C · mean rain-rate
  3.51 mm/hr · 13 samples" (the storm). `AppTest` clean across all views; `selftest.py` PASS.

## Addendum — viridis-by-rat + real WISER tracks (same day)

- **Field map coloured by rat (viridis, 5 rats)** instead of by level — episode points now use a
  per-rat viridis scale (shared with the trajectory overlays) so the five animals are distinct.
- **Real WISER positions.** New `utils/wiser_tracks.py` reads the read-only daily backup
  (`D:\Reolink_record\audio_in\Wiser_backup\incremental\1stcohort_2026_<date>.csv.gz`, override
  `EPISODE_BROWSER_WISER_DIR`): canonical `shortid/location_x/location_y/timestamp`, loaded only for
  the day-file(s) covering the current window, needed columns only, downsampled per tag. A **Field-map
  Synthetic / Real-WISER toggle** plots the actual rat tracks for the window.
- **Frame safety.** WISER is **inches in the offset frame** — real tracks are drawn in their **native
  inch frame** (with the `wiser_rois.json` boundary), labeled **UNVERIFIED vs field cm**; inches are
  never converted to cm (georeference pending), per CLAUDE.md / field_transform.
- **shortid → animal name** resolves via `rat_identities.csv` (`load_layout.subject_name_map`),
  matching the CLAUDE.md roster (12378 Siesta / 12395 Sen / 12407 Dormi / 12386 Nox / 12380 Hypnos /
  12409 Sova). Fixed a pandas ≥2.2/3.0 regression where `groupby(...).apply()` dropped the grouping
  column (`KeyError: ['shortid'] not in index`); the per-tag downsample is now a vectorised mask.
- **Verification:** loader returns 1521 real positions across all 5 rats for the default window (Sova
  correctly absent post-removal); `AppTest` clean on both field-map sources; live app shows the 5-rat
  viridis legend + both toggle options; `selftest.py` adds WISER checks (missing file → empty,
  candidate-date ordering, window filter + name resolve) → PASS (33 checks).

## Addendum — WISER scatter with time gradient + landmarks (same day)

- **Field map redesigned around real WISER.** Dropped the Synthetic/Real toggle — the field map is
  now a large (**full-width, height 430**) **scatter of real WISER positions**, **coloured by a
  timestamp gradient** (viridis, so temporal flow reads directly) and **shape-coded by rat**.
- **Paddock landmarks.** New `wiser_tracks.load_landmarks()` reads `wiser_rois.json` (WISER inch
  frame — the same frame as the tracks; its house boxes derive from `field_layout.json`'s shelters)
  and the map draws the **shelter/house boxes + tunnel** (rects, labeled), **refuges/water/food**
  (points, labeled), and the boundary. The layout was reflowed: Timeline + Coverage-QC share a row,
  the WISER map spans full width, Weather below.
- **Frame safety unchanged:** native inches, offset frame, **UNVERIFIED vs field cm** — not converted.
- **Verification:** `AppTest` clean across all views in the `cv` env (pandas 3.0.3) with the real
  WISER map loading by default; `selftest.py` PASS (34 checks, adds a `load_landmarks` check); live
  app confirmed time-gradient colour + landmarks + no synthetic toggle.

## Addendum — field-map colour: per-rat hue + time lightness (same day)

- The WISER scatter now encodes **rat = hue** and **time = lightness of that hue** (light early →
  dark late), instead of the previous time-viridis-colour + rat-shape. Colours are computed per
  point (`app.hex_from_hue` via `colorsys`, stable hues from `rat_hue_map`) and drawn with
  `alt.Color(scale=None)`; a single HTML legend row shows each rat's light→dark gradient swatch.
- **Verification:** colours checked (5 distinct hues, each light→dark — Dormi blue / Hypnos orange /
  Nox green / Sen magenta / Siesta purple); live app confirmed the new legend + 5 gradient swatches,
  old time/shape legends gone, UNVERIFIED note retained; `AppTest` clean (cv env); `selftest.py` PASS.

## Addendum — UX pass (workflow clarity, no scientific-logic change)

Implemented the Top-5 from `episode_browser/UX_REVIEW.md`; only `app.py` + README changed (no
data-layer/`utils/` change), preserving every invariant:
- **Table bars no longer read as ground truth.** `score_of` → `lens_rank` (**max lens or NaN, never
  0** — fixes an absence→0 bug); columns are **Boundary conf.** (bar), **Lens rank** (bar, blank when
  unscored), **Track qual** (plain number, not a bar), with a "bars are UI aids, not ground truth"
  caption.
- **Removed the inert header tray** (`ⓘ Help ⚙ Settings 🧑 HC`); the header now shows the session
  annotator ID, and a collapsed **"How to use"** (find → click row → inspect → judge) sits atop the
  dashboard.
- **Active-filter / status strip** above the table: *Showing N of M · day+slice · filters · selected ·
  click a row to inspect* (Q3/Q7 legibility).
- **Unified identity + subject controls:** one **"Your annotator ID"** in the sidebar (was entered
  twice); relabeled "Subject ID" → "Filter table by subject" and "Focus rats" → "Overlay on map &
  timeline". Dropped misleading panel numbering (1·/2·/3·/4·).
- **Data-safety made legible without friction:** append-only one-liner by the verdict actions; **Export
  → "Export CSV"** with a "lossy — not a re-import path" tooltip; verdict/Save/Reveal **block with a
  nudge** until an annotator ID is set (so self-agreement analysis always has a real id).
- **Docs aligned to reality:** README's stale "Run button" / "15-min window" claims corrected (no Run
  button; opens on 60 min).
- **Verification:** `AppTest` clean across all views (cv env); the annotator nudge blocks a write when
  the id is empty and allows it when set; the table exposes Boundary conf./Lens rank/Track qual with
  **Lens rank NaN (never 0)** for unscored episodes; live app confirmed the fake tray is gone, the
  status strip + single annotator input + export relabel render; `selftest.py` PASS (data layer
  untouched).

## Known limitations & next steps

- **Prototype on synthetic data only.** `synthetic_v0` is a placeholder segmentation, not a
  real model; synthetic episodes make no behavioral claim.
- **No real ingest yet.** Next: a real `state_model` (e.g. `kinematic_v1` / proximity-graph)
  plus a loader that segments WISER/CV streams into episodes and appends them into the **same**
  store, told apart from synthetic by `state_model_id`.
- **Frames not reconciled.** WISER inches vs field cm remain separate until the georeference
  transform is confirmed (see `wiser` georeferencing); the field view does not
  overlay WISER zones on the cm frame.
- **Streamlit full-rerun** will strain very large stores; the data layer is deliberately UI-free
  so a faster frontend can replace `app.py` without moving logic.

## Addendum - real selected-episode vertical slice (2026-07-10)

**Commit:** uncommitted at verification time.

**Plan:** [2026-07-10 continuation in the Episode Browser plan](../implementation_plan/2026-07-02-episode-browser.md#2026-07-10-continuation-real-selected-episode-vertical-slice)

**Manifest:** [June 30 route slice](../data_manifests/2026-06-30-episode-browser-route-slice.yaml)

### What changed

- Registered `wiser_route_bout_v1` with the existing route extractor parameters and
  added uncapped extraction support without changing the segmentation method.
- Added `build_real_slice.py`, which reads only the two source WISER gzip files needed
  for June 30, 21:00-21:15 EDT, applies existing tag/QC rules, and writes a small real
  episode Parquet plus a bounded WISER evidence Parquet sidecar. Canonical episode
  times are Unix milliseconds in UTC; `duration_s` remains derived at load.
- Added bounded repository access (`query_index`, `query_window`, `get_episode`),
  `SelectedEpisodeContext`, independent coverage summaries, explicit evidence states,
  and camera/video routing interfaces outside the UI.
- Refactored the Streamlit app around one `selected_episode_id`. The selected header,
  timeline, WISER, weather, routed video, QC, and judgment history now share one episode
  and a five-second padded evidence context.
- Made real mode the default. Synthetic records and the sample clip remain explicit
  demo/test fixtures and do not enter the primary queue.
- Routed each episode from its full WISER footprint with a 15-inch jitter margin. The
  visibility map remains unconfirmed, so all candidates display as unverified. No
  episode receives a blanket CH01 or other global video path.
- Added on-demand extraction of four frames in Review and six in the larger Video view.
  Only the selected channel and closed hourly recording are resolved; no video is copied
  or preloaded.
- Kept blind evaluation as a secondary regression-protected mode. The real slice has no
  lens scores, so the UI displays `not scored` rather than substituting zero.
- Kept standard judgments append-only and exposed prior records in the selected episode's
  annotation history. CSV remains a visibly lossy export.

### Derived quantity definitions

Let `W = [t_0, t_1)` be the fixed 900-second source window and let `B_W` be its
one-second bins. For subject `s`, let `n_valid(s,b)` be the number of WISER fixes in
bin `b` that remain valid after tag cutoffs and QC rules.

**Data availability**

\[
C_{data}(s) = 100\,\frac{1}{|B_W|}\sum_{b\in B_W}
\mathbf{1}[n_{valid}(s,b)>0].
\]

Plain language: the percentage of one-second source bins containing at least one valid
tracking fix for subject `s`. Units are percent, range 0-100%. A bin with only invalid
fixes is `tracking_lost`; a bin with no fixes is `no_data`.

Let `E_s` be the real `wiser_route_bout_v1` episodes for subject `s`, with episode
interval `I_e = [t_{e,0}, t_{e,1})`.

**Imported-episode coverage**

\[
C_{episode}(s) = 100\,
\frac{\left|\bigcup_{e\in E_s}(I_e\cap W)\right|}{|W|}.
\]

Plain language: the exact union duration of imported route bouts divided by the full
source-window duration. Units are percent, range 0-100%. Its complement is `not
represented by importer`; it is not a missing-data or QC state. Queue filters do not
change `W` or `E_s` used for the session summary.

**Imported episode count**

\[
N_{episode}=|E_W|,
\]

where `E_W` is the set returned by the uncapped existing route extractor within `W`.
Plain language: this is a count of imported route bouts, in episodes, with no ranking or
score threshold applied after segmentation.

For routed footprint points `P` after adding the four 15-inch axis-margin copies, and a
camera polygon `A_c`, camera footprint coverage is

\[
F_c = 100\,\frac{1}{|P|}\sum_{p\in P}\mathbf{1}[p\in A_c].
\]

Plain language: `F_c` is the percentage of jitter-expanded footprint points inside the
candidate camera polygon. Units are percent, range 0-100%. It is a routing aid, not a
calibration confidence; `meta.confirmed: false` forces the final routing state to
`unverified` regardless of `F_c`.

Episode duration is derived as

\[
d_e=(t_{e,1}-t_{e,0})/1000,
\]

where timestamps are Unix milliseconds UTC and `d_e` is seconds. It is not stored.

### Source data and observed QC

- WISER sources:
  `1stcohort_2026_2026-06-30.csv.gz` and
  `1stcohort_2026_2026-07-01.csv.gz` under the read-only incremental backup.
- Window: June 30, 2026, 21:00:00-21:15:00 EDT, described only as a
  **pre-night-rain integration slice**. Weather is a covariate; no storm-response label
  or inference was added.
- The uncapped extractor returned `N_episode = 14`; all 14 entered the store and zero
  were dropped by a cap.
- Coverage over the fixed 900-second denominator:

| Subject | Animal | Data availability | Imported-episode coverage |
|---|---|---:|---:|
| 12378 | Siesta | 98.000% | 1.314% |
| 12380 | Hypnos | 98.111% | 1.086% |
| 12386 | Nox | 98.444% | 3.102% |
| 12395 | Sen | 97.333% | 0.000% |
| 12407 | Dormi | 97.778% | 0.757% |

- The deterministic preview episode is `wiser_route_20260630_0001_12378`: one CH04
  candidate, `F_CH04 = 100%`, no boundary ambiguity, a closed
  `CH04_2026-06-30_21-00-00_to_22-00-00.mp4` recording, and four extracted frames.
  Routing is still visibly unverified because the map is unconfirmed.
- All 14 real episodes have absent lens scores. The store contains no globally attached
  `video_path`.

### Verification

- `C:\Users\Cornell\.conda\envs\cv\python.exe episode_browser/selftest.py` with
  `EPISODE_BROWSER_FFMPEG` set to the cv environment: PASS. This covers Parquet nested
  round trips, exact union coverage, filter-independent denominators, all camera-route
  states, absent scores, append-only writes, blind logging, and four-frame extraction.
- `python -m compileall -q episode_browser wiser/src/trajectory_stereotypy.py`:
  PASS.
- `git diff --check -- episode_browser wiser/src/trajectory_stereotypy.py
  implementation_plan data_manifests`: PASS.
- Real-store audit: 14 extractor bouts, 14 stored episodes, zero cap drops, and zero
  non-null lens-score records.
- Real-video audit: selected CH04 closed recording resolved; four downscaled PNG frames
  extracted; no global video path present.
- Browser audit at 1280 px and 800 px: the same selected episode appears in the header,
  queue, timeline, and evidence; the fixed 21:00-21:15 denominator remains visible;
  routed video is unverified; four frames load on demand; narrow columns stack without
  horizontal overflow.
- Append-only persistence: a verification judgment was appended to
  `annotations_vertical_slice_verification.jsonl`, read back through
  `read_episode_history`, and left out of the episode store.

### Known limitations

- The WISER native-inch origin, camera visibility polygons, and WISER/weather/NVR clock
  relationships remain unverified. The UI preserves those warnings and makes no spatial
  or causal behavior claim from this slice.
- Data availability is WISER-specific. Video occlusion is a separate modality condition.
- The real slice demonstrates standard review, not ranking enrichment; lens scoring,
  saved cohorts, comparison, adjudication, and cross-day discovery remain deferred.
- Streamlit is suitable for this bounded path but not the intended large-store frontend.
  UI-free repository, coverage, routing, selection, and annotation interfaces remain the
  migration boundary.

## Addendum - existing strict-following candidates (2026-07-11)

**Commit:** uncommitted at verification time.

**Plan:** [2026-07-11 continuation in the Episode Browser plan](../implementation_plan/2026-07-02-episode-browser.md#2026-07-11-continuation-label-existing-strict-following-incidents)

**Source analysis:** [Phase B2 following incidents](2026-07-08-following-incidents-b2.md)

### What changed

- Reused the existing Phase B2 `strict_following_episodes.csv` output unchanged;
  no detector thresholds were retuned and no new following inference was run.
- Registered `wiser_lagged_path_reuse_v1`, whose state vector records lag,
  separation, heading alignment, lag support, and follow-bin count. It does not
  use a human behavior category as a state feature.
- Imported every Phase B2 incident overlapping June 30, 21:00-21:15 EDT as a
  pair-level episode with ordered temporal leader/follower IDs, stable source-event
  provenance, absent lens scores, and post-hoc labels `following` and
  `strict_trailing_candidate`.
- Converted the source's inclusive final one-second grid timestamp to the browser's
  canonical half-open interval. The original timestamp and conversion rule remain
  in `linked_assets.following_detector`.
- Reconstructed each pair footprint from the bounded WISER evidence and rerouted it
  with the browser's 15-inch jitter margin. Every route remains unverified because
  the camera map still declares `confirmed: false`.
- Wrote new v2 Parquet/JSONL/evidence/manifest outputs. The previous route-only
  derived files were preserved and not overwritten.
- Added Level and Label filters, queue label/level columns, explicit
  `leader -> follower` text, candidate provenance, and two-subject WISER role
  markers. Route-bout importer coverage remains route-only.

### Derived quantity definitions

For temporal leader `A`, follower `B`, lag `l` in seconds, and one-second grid bin
`t`, define the strict lagged path-reuse indicator

\[
f_l(t)=\mathbf{1}[m_A(t)\land m_B(t+l)\land
\|x_B(t+l)-x_A(t)\|<24\text{ in}\land
u_A(t)\cdot u_B(t+l)>0.5].
\]

Here `m` is the existing moving mask from five-second median-smoothed WISER
positions, `x` is position in native inches, and `u` is heading. Plain language:
a bin fires when both subjects are moving, the later subject reuses the earlier
subject's position within the 24-inch threshold, and their headings align. The
24-inch radius is above the approximately 7-inch median jitter floor. This is a
candidate lagged path-reuse measurement, not proof of social following.

For each lag, firing bins form runs allowing gaps up to two seconds and requiring
at least three bins. A detector episode is the connected union of those runs over
all lags `l = 1,...,30`. Plain language: lag can vary within one sustained candidate
incident; overlapping lag detections are not counted as separate episodes.

Let `E_F` be all 2,046 exported Phase B2 episodes and `W=[w_0,w_1)` the browser
window. The imported set and count are

\[
E_F(W)=\{e\in E_F:t_{e,0}<w_1\land t^{inc}_{e,1}\ge w_0\},\qquad
N_F(W)=|E_F(W)|=16.
\]

Plain language: import every source incident whose interval overlaps the fixed
15-minute window. `N_F` is an episode count; there is no score threshold or cap.

The source end timestamp is the final inclusive one-second bin. Canonical time is

\[
t_{e,1}=t^{inc}_{e,1}+1000\text{ ms},\qquad
d_e=(t_{e,1}-t_{e,0})/1000.
\]

Plain language: add one second to represent the same bins as a half-open interval;
`d_e` is then derived in seconds and is never stored. The minimum imported duration
is 3 seconds, matching the detector's three-bin minimum.

With `N_R=14` uncapped route bouts from the prior slice, the v2 store count is

\[
N_{store}=N_R+N_F(W)=14+16=30\text{ episodes}.
\]

Plain language: the store contains both model-provenance classes. Pair incidents do
not enter the previously defined `C_episode` route-bout coverage numerator.

### Verification

- Real-store audit: PASS with 30 unique IDs, 14 `wiser_route_bout_v1` episodes,
  and 16 `wiser_lagged_path_reuse_v1` pair episodes.
- All 16 pair episodes have `following`, `strict_trailing_candidate`, unique source
  event IDs, ordered role maps, absent lens scores, and unverified camera routes.
- Schema/registry validation: PASS with 0 errors and 0 warnings. Minimum canonical
  following duration is 3.0 s.
- Route-bout coverage percentages are unchanged from the 2026-07-10 addendum.
- `episode_browser/selftest.py`: PASS, including state-model validation and
  Level+Label filtering for a following pair.
- Streamlit `AppTest`: 0 exceptions; default queue 30/30; search `following` gives
  16/30; selected `Hypnos -> Dormi` displays the new state model, both labels,
  candidate warning, and unchanged route-only coverage.
- Real video check for `wiser_follow_20260630_ev0661_12380_12407`: CH03/CH04
  candidates, map unconfirmed, closed CH03 hourly recording resolved, and four
  subsampled frames extracted.
- The in-app browser automation surface did not attach a controllable test tab in
  this session, so the responsive visual click-through was not rerun. The live
  Streamlit server and AppTest both use the v2 store.

### Scientific limitations

- `following` is a post-hoc candidate label. WISER alone cannot distinguish active
  pursuit from shared-road reuse; video recall and event interpretation remain pending.
- Leader/follower means temporal order only, not dominance, intent, or spatial lead.
- WISER positions remain native inches in an unverified offset frame; camera
  visibility polygons and cross-device clocks remain unverified.
