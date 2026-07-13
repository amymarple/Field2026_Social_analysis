# Episode Browser

A light researcher-facing browser for reviewing behavioral episodes. It consumes
episode candidates and synchronized evidence; it does not edit tracks, correct
identities frame by frame, or replace SLEAP, idtracker.ai, or CVAT.

The default app is one bounded real integration path:

```text
real WISER route bout or strict-following candidate
-> selected_episode_id
-> WISER + weather + routed video + QC
-> append-only judgment
```

The current slice is June 30, 2026, 21:00-21:15 EDT. It is labeled
**pre-night-rain integration slice** because recorded rain begins later, near
22:20-22:30. The slice carries no storm-response label or interpretation.

## Scientific Contract

- Every route bout and every existing Phase B2 incident overlapping the slice
  enters the bounded real store. Lens scores rank or filter; they never gate import.
- Every episode records `state_model_id`. Route bouts use `wiser_route_bout_v1`;
  pair incidents use `wiser_lagged_path_reuse_v1`.
- Pair records carry ordered temporal roles and the post-hoc labels `following`
  and `strict_trailing_candidate`. These are candidates, not video-validated
  behavior or dominance claims.
- `zones` and human behavior labels are post-hoc metadata, not segmentation
  features unless a future state model explicitly declares otherwise.
- WISER coordinates remain native inches in an unverified offset frame. The UI
  preserves the approximately 7-inch jitter warning.
- WISER, weather, and NVR clocks are aligned by wall clock only. Cross-device
  synchronization remains unverified.
- The camera visibility map currently declares `confirmed: false`. Camera
  recommendations therefore remain unverified even at 100% numerical footprint
  coverage.
- Standard judgments and blind-evaluation records are append-only. The episode
  Parquet file and earlier judgments are never edited.

## Real Slice Data

`build_real_slice.py` reads only the two WISER day files needed to bound the
15-minute UTC interval, applies existing tag cutoffs and QC validity rules, then
runs the existing route-bout segmentation uncapped. It also imports every existing
Phase B2 strict-following incident overlapping the slice from
`strict_following_episodes.csv`; the detector itself is not rerun or retuned. It
writes new v2 derived files under `data/` while preserving the earlier route-only
files:

- `real_episodes_20260630_2100_2115_v2.parquet`: primary episode store.
- `real_episodes_20260630_2100_2115_v2.jsonl`: readable alternative.
- `real_wiser_evidence_20260630_2100_2115_v2.parquet`: bounded evidence sidecar.
- `real_slice_manifest_20260630_2100_2115_v2.json`: generation and QC manifest.

The v2 store contains 14 route bouts and 16 pair-level following candidates. Phase
B2 source end times identify the final inclusive one-second grid bin; import converts
them to the browser's half-open interval by adding one second to canonical `t_end`.
The source event ID and original timestamp remain in `linked_assets` provenance.

The raw WISER gzip files are never modified. The builder refuses to replace an
existing derived output unless `--force` is explicitly supplied.

Normal app rendering reads the bounded episode and evidence Parquet files. It
does not open a complete daily WISER gzip. `EpisodeRepository.query_index()`
reads queue columns with Parquet filtering and pagination; `get_episode()`
materializes only the selected nested record.

## Coverage Meanings

The app deliberately shows two independent rows over the fixed 15-minute session
window. Queue search, sorting, and filters do not change either denominator.

- **Data availability:** percentage of one-second bins containing at least one
  valid WISER fix. Missing bins are `tracking_lost` or `no_data`.
- **Imported episodes:** exact union duration of real `wiser_route_bout_v1`
  intervals divided by the session duration. Its complement is
  `not represented by importer`, which is not a tracking or QC gap.

Video occlusion is a modality condition and is not used as a WISER data-gap
reason.

## Selected-Episode Workspace

`selected_episode_id` is the sole standard-review selection state. The selected
header, timeline, evidence panels, QC, and judgment rail all derive from one
`SelectedEpisodeContext` with five seconds of evidence padding.

- WISER emphasizes the selected subject and interval over field landmarks.
- Pair candidates display `leader -> follower` temporal roles; WISER marker shape
  and path distinguish the two subjects.
- Weather centers on the episode and remains an unverified wall-clock covariate.
- Video routes the complete WISER footprint with a 15-inch margin. A boundary
  or multiple-candidate route requires an explicit channel choice.
- Only the selected candidate channel and timestamp are resolved to a closed
  hourly recording. Video is not copied or preloaded.
- Four subsampled frames load on demand in Review; the Video view uses the same
  selected episode and routed recording.
- Missing lens scores display as `not scored`, never zero.
- Level and Label filters expose the pair queue directly; searching `following`
  returns the candidate incidents.

Blind evaluation remains available as a secondary view. Real episodes in this
slice have no lens scores, so there is no real ranking queue yet; demo fixtures
retain the score-hiding regression path.

## Windows Quickstart

From PowerShell:

```powershell
Set-Location C:\Users\Cornell\Documents\GitHub\Field2026_Social_analysis\episode_browser
# Optional, only for in-app video preview; point at any ffmpeg on this machine:
# $env:EPISODE_BROWSER_FFMPEG = "C:\path\to\ffmpeg.exe"
python build_real_slice.py
python -m streamlit run app.py
```

If the derived real files already exist, skip the builder command. From Windows
Command Prompt, use `set`, not the Unix `export` command:

```bat
cd /d C:\Users\Cornell\Documents\GitHub\Field2026_Social_analysis\episode_browser
rem Optional, only for in-app video preview:
rem set "EPISODE_BROWSER_FFMPEG=C:\path\to\ffmpeg.exe"
python -m streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501). Streamlit normally opens a
browser automatically; if it does not, use that URL directly.

Run the data-layer regression checks with:

```powershell
python selftest.py
```

## Demo Fixtures

Synthetic data and the generated sample clip are test/demo fixtures. They do not
appear in the primary real queue. To exercise them deliberately:

```powershell
$env:EPISODE_BROWSER_DATA_MODE = "demo"
python generate_synthetic_episodes.py
python -m streamlit run app.py
```

Unset `EPISODE_BROWSER_DATA_MODE` to return to real mode.

## Structure

```text
episode_browser/
  app.py                         UI only
  build_real_slice.py            bounded real importer
  episode_schema.yaml
  state_models.yaml
  selftest.py
  data/                          derived stores and bounded evidence
  outputs/annotations/           append-only standard judgments
  outputs/evaluations/           append-only blind-evaluation logs
  utils/
    episode_io.py                Parquet/JSONL access; CSV is lossy export
    coverage.py                  separate availability/importer coverage
    evidence.py                  camera routing and closed-video lookup
    selection.py                 SelectedEpisodeContext
    annotations.py               append-only writers and history
    validation.py                schema and state-model checks
```

Streamlit is appropriate for this bounded prototype. Its full-rerun model will
strain large tables and stateful review sessions, so all data, routing, coverage,
selection, and annotation logic remains outside `app.py` for a future frontend.

## Published analysis exchange

The repository-root `analysis_exchange/` is the deterministic handoff for future analysis outputs.
The browser does not inspect Markdown or scan draft directories. `utils/exchange_import.py` uses the
shared verified reader and accepts only sealed, import-ready `episode_candidate` bundles routed to
`episode_browser`.

The adapter maps fields only from the bundle's `record_contract`, requires the declared state model to
exist in `state_models.yaml`, preserves the source candidate label and claim boundary in provenance,
and leaves human labels and lens scores empty. Unknown models, point events without an explicit window,
blocked bundles, missing source fields, and ambiguous subject/time mappings fail loudly.
