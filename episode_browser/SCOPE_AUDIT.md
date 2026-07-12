# Episode Browser Toolbox Scope Audit

**Audit date:** 2026-07-11  
**Audited scope:** `episode_browser/` plus only the WISER functions it imports directly.  
**Phase 1 rule:** repository code was inspected before any external source was consulted. README claims were not used as evidence.

## Intended Scientific Scope

The audited code is the first layer of a larger **representation-aware behavioral discovery system**. Its intended purpose is not to automate scientific truth or generate a narrative for every detected event. It is to support a human-agent workflow that can turn long-duration, multimodal recordings into evidence-grounded, testable behavioral hypotheses:

```text
Long-duration multimodal recordings
    -> multiple upstream representations and detectors
    -> candidate episodes
    -> evidence-grounded human/agent review
    -> cross-episode scientific observations
    -> relevant literature and analogous phenomena
    -> competing mechanistic hypotheses
    -> discriminating analyses and future experiments
```

Contemporary behavioral neuroscience often starts from a small set of preselected behaviors inherited from a paradigm, laboratory tradition, or prior ethological observation. The intended system instead aims to make large naturalistic datasets scientifically searchable: surface diverse candidate phenomena, expose the evidence and representation behind each candidate, consolidate repeated events into defensible observations, connect those observations to multiple literatures, and compare hypotheses through predictions and discriminating tests.

The concise architecture is:

```text
Episode Browser
    -> Observation Compiler / Observation Registry
    -> Literature and Hypothesis Agent
```

- **Layer 1 - Episode Browser:** determines whether a local candidate is real and interpretable. It exposes model/importer provenance, source availability, modality routing, identity/timing/QC limits, and reviewer judgment.
- **Layer 2 - Observation Compiler / Registry:** converts reviewed episodes, counterexamples, baselines, missingness, and replication evidence into quantitative cross-episode claims. This is architecturally intended and currently absent from `episode_browser/`.
- **Layer 3 - Literature and Hypothesis Agent:** receives a structured observation package, finds relevant and misleading analogies, and records competing explanations, unique predictions, discriminating analyses, experiments, and falsifying evidence. This is architecturally intended and currently absent.

This is best described as an **observation-centered hypothesis-generation workbench**, not a generic annotation application, pose-model package, or autonomous discovery engine.

### Status vocabulary

The remainder of the audit separates four states:

1. **Implemented now:** executable and verified in the current code inventory.
2. **Partial scaffolding:** a schema slot, UI path, or utility exists, but the scientific operation is incomplete.
3. **Intended, absent:** part of the target scientific architecture but not implemented in the audited scope.
4. **Explicit non-goal:** deliberately delegated to upstream or dedicated tools.

## Phase 1 - Code-Verified Inventory

### Capability inventory

| Module | Implemented capability | Algorithms / behavior | I/O and evidence |
|---|---|---|---|
| Episode schema and model registry | Extensible episode fields, controlled vocabularies, required-field declarations, and three registered state models | Declares canonical millisecond bounds, list-valued subjects, probabilistic zones, sparse lens-score maps, linked assets, QC, and append-only human annotations. Registry blocks `zone`/`zones` as model features unless explicitly enabled. | YAML: `episode_browser/episode_schema.yaml`; `episode_browser/state_models.yaml`; registry rule in `episode_browser/utils/validation.py:55` |
| Utility package surface | Import-safe marker for the UI-free data layer | No public re-exports or stable API facade; consumers import individual modules directly. | `episode_browser/utils/__init__.py` |
| Runtime dependency declaration | pandas/NumPy/PyYAML, PyArrow, and Streamlit; ffmpeg is an optional external binary | Requirements file only; no lockfile, package metadata, or environment resolver. | `episode_browser/requirements.txt` |
| Repository I/O | Parquet primary access, JSONL round trip, lossy CSV export, derived duration, bounded index query, selected-record lookup | Nested values are serialized as JSON strings inside Parquet columns. Parquet filters time overlap and episode ID; requested index columns are projected. `duration_s=(t_end-t_start)/1000` is derived after reads. | Parquet/JSONL/CSV: `episode_browser/utils/episode_io.py:35-185`; `EpisodeRepository` at `:113` |
| Schema validation | Registry existence, state-model FK, required-field presence, level/source enums, time order, confidence ranges, sparse-score null warnings | Accumulates errors/warnings instead of raising. | YAML in; structured `ValidationReport` out: `episode_browser/utils/validation.py:29-134` |
| Real-slice builder | Produces one bounded real episode/evidence store without loading WISER days in the UI | Chunked timestamp filtering of two gzip CSVs; WISER speed/QC/tag-cutoff preprocessing; uncapped route-bout import; import of existing Phase B2 pair incidents; inclusive-grid-end to half-open time conversion; pair footprint reconstruction; schema validation before writes; explicit overwrite refusal unless `--force`. | Gzip CSV + Phase B2 CSV/JSON + YAML/JSON configs in; Parquet, JSONL, JSON manifest out: `episode_browser/build_real_slice.py:59-401` |
| Route-bout segmentation dependency | Low-level per-animal movement episode cutting | Rolling-median positions; fixed-window displacement speed; contiguous speed-threshold runs with maximum gap, minimum duration, minimum displacement; arc-length path resampling; optional per-night cap disabled by this builder. | Direct import: `wiser/src/trajectory_stereotypy.py:831-907`; called by `episode_browser/build_real_slice.py:117-129` |
| Lagged path-reuse dependency | Pair-level strict-following candidate episode cutting | One-second common grid, five-second rolling-median positions, moving masks, lagged distance and heading test over lags 1-30 s, gap-tolerant runs, union across lags. Browser imports existing output; it does not rerun this detector. | Direct source evidence: `wiser/src/wiser_analysis_utils.py:1416-1545`, `wiser/src/following_incidents.py:63-138`; imported at `episode_browser/build_real_slice.py:234-335` |
| WISER QC preprocessing | Speed, dropout/jump/anchor/boundary flags, tag cutoffs | Raw and rolling-median speed; low-anchor flag; per-tag gap threshold; impossible-jump threshold; provisional/confirmed boundary handling; post-removal cutoff; composite `valid`. | DataFrame in/out: `wiser/src/wiser_analysis_utils.py:185-388`; used at `episode_browser/build_real_slice.py:91-101` |
| Coverage | Separate source-data availability and route-importer coverage; legacy synthetic tiling | Data availability uses one-second valid-fix bins with `tracking_lost` vs `no_data`. Route coverage uses exact merged interval union and labels its complement `not_represented`. Legacy subject-by-level episode tiling remains. | DataFrames in; `CoverageSummary`/intervals out: `episode_browser/utils/coverage.py:21-265` |
| Querying and ranking | Time/level/subject/label/zone/source/model/QC/environment/confidence filters; sparse lens ranges; free-text AND search; lens sorting | List intersection filters; explicit absent-score behavior; case-insensitive flattened text search; no query language/parser. | DataFrame in/out: `episode_browser/utils/query.py:18-191` |
| Selected context | Single selected-episode evidence context | Immutable episode ID, subjects, canonical bounds, and symmetric configurable evidence padding. | `SelectedEpisodeContext`: `episode_browser/utils/selection.py:7-32` |
| Camera and video routing | WISER footprint to ranked camera candidates; closed hourly-file resolution | Polygon coverage times channel priority; optional axis-aligned jitter ring; boundary heuristic and discounted confidence; map confirmation gates status. Filename regex resolves only finalized `_to_` recordings. | Visibility YAML + WISER footprint in; `CameraRoute`/file metadata out: `episode_browser/utils/evidence.py:22-109`; router dependency `wiser/src/camera_router.py:28-148` |
| Video preview | Lightweight frame filmstrip and synthetic test clip | Fast ffmpeg seek per evenly spaced sample; one frame per seek; resize to target width; rejects open Reolink hourly files. | MP4 in, PNG bytes out: `episode_browser/utils/video_preview.py:43-148` |
| Weather adapter | AWN file discovery, normalization, window slicing, nearest sample | Renames known AWN columns; parses explicit-offset dates then deliberately keeps local wall clock; deduplicates timestamps. | AWN CSV in, pandas frame/dict out: `episode_browser/utils/weather.py:38-94` |
| Layout/identity adapters | Lenient field/ROI JSON, WISER landmarks, tag-to-animal map | Removes JSON comments; preserves cm vs native-inch frames; extracts rectangular and point landmarks; passes unknown identities through. | JSON/CSV in: `episode_browser/utils/load_layout.py:37-107`, `episode_browser/utils/wiser_tracks.py:99-145` |
| Legacy WISER plot loader | Optional day-file loading and per-tag downsampling | Reads one gzip day file, filters UTC window/subjects, vectorized regular-row downsampling. The current real UI does not call it because it reads the bounded evidence sidecar. | Gzip CSV in, DataFrame out: `episode_browser/utils/wiser_tracks.py:35-96` |
| Human annotation | Standard verdict/labels/notes and blind-evaluation event logging | Append-only JSONL per session; UTC timestamps; history scan across annotation files; blind record includes ranking method and revealed score map. | JSONL: `episode_browser/utils/annotations.py:30-94` |
| Streamlit UI | Queue, search/filter, selected header, coverage, timeline, WISER evidence, weather, video, provenance, lens state, annotation history/verdict, secondary blind mode | Single `selected_episode_id`; Altair interval/line/scatter layers; pair role encoding; on-demand video; session-state navigation. Real queue is fixed to one 15-minute slice. | `episode_browser/app.py:35-646`; real Parquet/evidence/manifest constants at `:21-23` |
| Synthetic fixture generator | Deterministic messy-data fixture across per-animal, pair, group, and environment levels | Random duration/state vectors; probabilistic zones; sparse random lens maps; unknown IDs, swaps, WISER QC, fog, conflicting sources, thermal ambiguity, field-note overlap, explicit gap sidecar. This is fixture generation, not a segmentation algorithm. | JSONL/Parquet/gap JSONL: `episode_browser/generate_synthetic_episodes.py:64-344` |
| Tests | Offline regression suite plus Streamlit smoke testing performed externally to the module | Checks registry invariants, nested round trips, exact coverage, sparse scores, filters, append-only logs, camera states, video extraction, weather and WISER adapters. No accuracy/recall benchmark against human-labeled behavioral episodes. | `episode_browser/selftest.py:30-300` |

### Implemented metrics and thresholds

All WISER spatial quantities are in the native **inch** frame with an unverified offset origin.

#### Derived episode duration

$$d_e=(t_{e,1}-t_{e,0})/1000$$

where bounds are Unix milliseconds UTC. **Text:** episode duration in seconds; domain $[0,\infty)$. It is computed on read and not persisted (`episode_browser/utils/episode_io.py:42-47`).

#### Data availability

$$C_{data}(s)=100\,|B_W|^{-1}\sum_{b\in B_W}\mathbf{1}[n_{valid}(s,b)>0]$$

where $B_W$ is the set of one-second bins in session window $W$ and $n_{valid}(s,b)$ is the count of fixes passing WISER QC/tag cutoffs. **Text:** percent of bins with any valid tracking fix for subject $s$; range 0-100%. Invalid-only bins are `tracking_lost`; empty bins are `no_data` (`episode_browser/utils/coverage.py:78-119`).

#### Route-importer coverage

$$C_{route}(s)=100\,\frac{|\bigcup_{e\in E_s}([t_{e,0},t_{e,1})\cap W)|}{|W|}$$

where $E_s$ contains only `wiser_route_bout_v1` episodes. **Text:** percent of the fixed session represented by route bouts; range 0-100%. Its complement is importer non-coverage, not missing source data (`episode_browser/utils/coverage.py:120-147`).

#### Route-bout cut

For smoothed speed $v_s(t)$, a candidate run is a maximal run satisfying $v_s(t)>12.63$ in/s and inter-fix gap $\le2$ s. It is retained when duration $\ge3$ s and net displacement $\ge15$ in. **Text:** a low-level movement bout above the stationary-noise speed threshold and displacement floor; no human behavior label is used (`episode_browser/state_models.yaml`, `wiser/src/trajectory_stereotypy.py:831-907`).

#### Strict lagged path-reuse bin

$$f_\ell(t)=\mathbf{1}[m_A(t)\land m_B(t+\ell)\land \|x_B(t+\ell)-x_A(t)\|<24\text{ in}\land u_A(t)\cdot u_B(t+\ell)>0.5]$$

for lags $\ell\in[1,30]$ s. **Text:** a one-second candidate bin where both subjects move and the later subject revisits the earlier subject's location with aligned heading. Runs tolerate gaps up to 2 s and require at least three bins. This measures candidate path reuse, not confirmed social following (`wiser/src/following_incidents.py:63-138`).

#### Camera footprint coverage and route confidence

$$F_c=|P|^{-1}\sum_{p\in P}\mathbf{1}[p\in A_c],\qquad q=F_{c^*}(0.6\text{ if boundary else }1)$$

where $P$ is the footprint plus four axis-offset copies at the configured margin, $A_c$ is camera polygon $c$, and $c^*$ maximizes $F_c\times priority_c$. **Text:** $F_c$ is polygon sample coverage and $q$ is a routing heuristic, both range 0-1; neither is video-detection confidence. The current map is unconfirmed (`wiser/src/camera_router.py:61-123`).

#### Lens values

For stored score key $k$, $L_k(e)$ is its stored float when present and is undefined when absent. **Text:** arbitrary upstream ranking values; no scorer or calibration is implemented here. Missing is never replaced by zero (`episode_browser/utils/query.py:18-29`).

### Stubbed, legacy, or half-implemented

| Item | Status verified from code |
|---|---|
| Native nested Parquet | **Half-implemented.** Parquet is used, but all nested fields are JSON strings, so Arrow-native struct/list predicate pushdown is absent (`episode_browser/utils/episode_io.py:35-76`). |
| Scalable pagination | **Half-implemented.** Parquet time/ID filters and column projection work, but `query_index` reads and sorts all matching rows before applying `offset/limit` in pandas (`episode_browser/utils/episode_io.py:136-158`). |
| Schema enforcement | **Half-implemented.** The YAML declares detailed types, but validation does not enforce most declared types, unique IDs, exact state-vector feature keys, subject uncertainty structure, probability bounds/sums, or strict positive duration (`episode_browser/utils/validation.py:74-121`). |
| Blind enrichment evaluation | **Half-implemented.** Score hiding and event logs exist; enrichment, chance/rarity baselines, confidence intervals, inter-rater agreement, and scorer/annotator conflict analysis are absent (`episode_browser/app.py:585-620`, `episode_browser/utils/annotations.py:57-69`). Real episodes have no lens scores, so the real blind queue is unavailable. |
| Lens scoring | **Stub/data slot only.** Schema/filter/rank/display exist, but the toolbox computes no recurrence, surprise, consequence, or priority score. Synthetic values are random (`episode_browser/generate_synthetic_episodes.py:107-114`). |
| Thermal evidence | **Placeholder.** The selected workspace always emits `Thermal: missing`; there is no thermal loader or viewer (`episode_browser/app.py:500-509`). |
| Camera mapping | **Provisional.** Routing code works, but the configured visibility map is `confirmed: false`; all recommendations are unverified (`episode_browser/utils/evidence.py:40-60`). |
| Generic real-data ingest | **Absent.** `build_real_slice.py` is hard-coded to one date/window, two WISER files, one route model, and one Phase B2 output directory (`episode_browser/build_real_slice.py:29-52`). |
| Full browser filter surface | **Half-implemented.** Data-layer filters cover time, zone, source, state model, confidence, environment, and lens ranges, but the UI exposes only search, level, label, subject, and QC (`episode_browser/utils/query.py:30-116`; `episode_browser/app.py:164-187`). |
| Annotation service semantics | **Prototype.** JSONL append has no locking, transaction, authentication, role control, schema validation, adjudication, or conflict handling; the utility silently substitutes `anonymous` even though the UI requires an ID (`episode_browser/utils/annotations.py:34-69`). |
| Evaluation benchmark | **Absent.** Tests are functional/regression checks; no labeled test corpus, detector precision/recall/F1, temporal IoU, boundary error, ranking enrichment, or usability benchmark is computed (`episode_browser/selftest.py`). |
| Packaging/API stability | **Absent.** There is no `pyproject.toml`, installed package, versioned Python API, migration system, or generated API documentation under `episode_browser/`. |
| Unused/legacy paths | `EvidenceStatus`, `app.video_state`, `coverage.overall_completeness`, and several WISER/layout availability loaders are not used by the current real UI. `compute_coverage` is retained for synthetic legacy tests (`episode_browser/utils/evidence.py:22`, `episode_browser/app.py:451`, `episode_browser/utils/coverage.py:184-265`). |
| Deprecated UI calls | Streamlit reports `use_container_width` as deprecated/removal-targeted, but the app still uses it throughout `episode_browser/app.py`. |
| Real/synthetic co-storage claim | **Not implemented.** Code selects separate real and demo Parquet files with `EPISODE_BROWSER_DATA_MODE`; it does not keep both in one physical store (`episode_browser/app.py:20-29`). |

## Phase 2 - Bounded reference set

### Reading boundary

The comparison was frozen after **five toolbox candidates** and **zero survey papers**. Only official README pages, documentation feature/API indexes, and release notes were read. No comparator source code or papers were read.

Three candidates meet both domain relevance and the requested recent-maintenance test:

| Toolbox | Official material read | Officially documented scope relevant to this audit | Maintenance evidence |
|---|---|---|---|
| BORIS | [Project feature page](https://www.boris.unito.it/), [coding feature index](https://www.boris.unito.it/user_guide/coding/), [analysis feature index](https://www.boris.unito.it/user_guide/analysis/), [export documentation](https://www.boris.unito.it/user_guide/export_events/), [release notes](https://github.com/olivierfriard/BORIS/releases) | Media/live event coding, subject/ethogram/event tables, playback and frame navigation, filtering/editing, time budgets, Cohen's kappa, co-occurrence, latency, plugins, plots, and tabular/spreadsheet exports. | Mature desktop application; v9.12.4 dated 2026-07-08 in the [official release](https://github.com/olivierfriard/BORIS/releases/tag/v9.12.4). |
| VAME | [README](https://github.com/EthoML/VAME), [release notes](https://github.com/EthoML/VAME/releases) | Pose-derived behavioral action segmentation using a recurrent variational autoencoder, clustering/community analyses, visualization/statistical workflows, and pose ingestion from DLC, SLEAP, LightningPose, NWB/ndx-pose, and `movement`. | Actively released Python toolbox; v0.14.2 adds DANDI loading, full-pipeline random seeding, and training improvements in the [official release](https://github.com/EthoML/VAME/releases/tag/v0.14.2). |
| Keypoint-MoSeq | [Documentation/API index](https://keypoint-moseq.readthedocs.io/en/latest/), [I/O API](https://keypoint-moseq.readthedocs.io/en/latest/io.html), [visualization API](https://keypoint-moseq.readthedocs.io/en/latest/viz.html), [release notes](https://github.com/dattalab/keypoint-moseq/releases) | Unsupervised keypoint-based behavioral syllables; AR-HMM/full-model fitting; calibration; model comparison; application to new data; group statistics; transition matrices/graphs; trajectory plots and grid movies; broad pose/NWB loaders; HDF5/CSV results. | Actively released Python toolbox; 0.6.8 is the current [official release](https://github.com/dattalab/keypoint-moseq/releases/tag/0.6.8). |

Two prominent candidates were read but excluded from the matrix because they fail the recent-release criterion:

- **BENTO:** close in multimodal-neuroscience scope, but the [latest release](https://github.com/neuroethology/bento/releases) is v0.3.0-beta from 2024-06-19.
- **SimBA:** prominent and its [README](https://github.com/sgoldenlab/simba) contains 2025 feature announcements, but its [formal GitHub releases](https://github.com/sgoldenlab/simba/releases) stop at v1.3 from 2021. Treating announcements as current releases would weaken the maintenance rule.

No survey was needed: the three retained official feature/API indexes expose the relevant annotation, segmentation, interoperability, visualization, and evaluation categories. This leaves the survey-paper budget unused.

### Comparator-layer interpretation

These are useful comparators, but they do not define the intended product boundary:

- **BORIS** primarily covers manual behavioral coding, media review, and observer-level analysis.
- **VAME and Keypoint-MoSeq** primarily cover upstream behavioral representation, segmentation, model fitting, and motif/syllable analysis.
- **This project** currently covers provenance-aware episode evidence review and intends to add cross-episode observation formation plus constrained literature/hypothesis assistance.

The bounded search can identify local differences and missing functions. It cannot establish global state-of-the-art leadership or prove that no other system implements a similar combination. Accordingly, the revised matrices use **local differentiator** rather than `AHEAD` when a feature was not identified in the bounded comparator documentation.

## Phase 3 - Gap analysis across system layers

Effort estimates describe likely implementation size: **S** is a focused addition, **M** crosses modules and requires new tests/QC, and **L** creates a major scientific subsystem. Comparator statements remain bounded to the official sources in Phase 2.

### Current Episode Browser layer

| Capability | Current local evidence | Comparator context | Audit assessment |
|---|---|---|---|
| Representation/importer provenance | Registry, FK validation, and selected-episode display: `state_models.yaml`, `utils/validation.py:42-93`, `app.py:260-290` | Not identified in the bounded BORIS, VAME, or Keypoint-MoSeq feature/API documentation as an episode-review contract | **Implemented local differentiator; no global leadership claim** |
| Source availability versus importer coverage | Independent formulas and timelines: `utils/coverage.py:78-147` | Not identified as the same two-denominator distinction in bounded comparator docs | **Implemented local differentiator; no global leadership claim** |
| Routing uncertainty and missing modality states | Camera footprint, confirmation gate, and closed-file lookup: `utils/evidence.py:22-109`; thermal remains missing | BORIS documents media review, not this WISER-to-camera uncertainty contract | **Implemented for video routing; partial across modalities** |
| Selected-episode media inspection | On-demand frame strip and synchronized Video view: `utils/video_preview.py`, `app.py:370-510` | BORIS provides mature [media coding/playback](https://www.boris.unito.it/user_guide/coding/); Keypoint-MoSeq provides [grid movies and overlays](https://keypoint-moseq.readthedocs.io/en/latest/viz.html) | **Partial parity at episode inspection, narrower by design** |
| Episode-level human judgment | Append-only verdict, notes, labels, history, and blind score hiding: `utils/annotations.py`, `app.py:525-620` | BORIS provides denser coding ergonomics and windowed Cohen's kappa in its [coding](https://www.boris.unito.it/user_guide/coding/) and [analysis](https://www.boris.unito.it/user_guide/analysis/) docs | **Partial scaffolding; review-validity gap, effort M** |
| Upstream segmentation/model training | Fixed WISER route cut plus imported lagged path-reuse incidents only | VAME and Keypoint-MoSeq make segmentation/model fitting core capabilities: [VAME README](https://github.com/EthoML/VAME), [Keypoint-MoSeq index](https://keypoint-moseq.readthedocs.io/en/latest/) | **Explicit non-goal; import versioned outputs instead** |
| Generic importer and scientific exchange | Builder is fixed to one WISER slice and two candidate sources: `build_real_slice.py:29-52` | VAME and Keypoint-MoSeq document broad pose/NWB loaders and VAME documents DANDI: [VAME release](https://github.com/EthoML/VAME/releases/tag/v0.14.2), [Keypoint-MoSeq I/O](https://keypoint-moseq.readthedocs.io/en/latest/io.html) | **Enabling gap, effort M; priority after scientific semantics** |
| Scalable repository/package contract | JSON-encoded nested fields, read-then-slice paging, partial validation, no package/API release | VAME and Keypoint-MoSeq provide maintained packages and documented APIs | **Enabling gap, effort M; urgency depends on actual scale/collaboration load** |

### Full intended scientific system

| Capability | Status in audited scope | Required scientific function | Consequence of absence | Priority / effort |
|---|---|---|---|---|
| Episode semantic contract per state model/importer | **Partial scaffolding** | Declare event/interval meaning, candidate versus inferred state, subject roles/count, overlap rules, boundary precision, confidence meaning, required evidence/provenance, and permitted review actions | Episodes from different models can look schema-compatible while having incompatible meanings | **P1 / M** |
| First-class `Observation` object and registry | **Intended, absent** | Stable, query-backed, versioned scientific claim that links support, counterexamples, baseline, scope, missingness, replication, and lifecycle | Reviewed episodes cannot become durable scientific units | **P1 then P3 / L** |
| Episode-to-observation compiler | **Intended, absent** | Grouping, recurrence, matched comparisons, null/rarity baselines, context enrichment, emergence/decay, individual consistency, replication, counterexample retrieval, and model-version sensitivity | The system stops at local review and cannot support cross-episode inference | **P0 prototype, P3 subsystem / L** |
| Provenance-preserving observation derivation | **Intended, absent** | Store the cohort query, source episode IDs, model/importer versions, QC rules, comparison definition, and derivation version | Claims cannot be reliably rerun, audited, or superseded | **P1-P3 / M** |
| Observation replication and contradiction lifecycle | **Intended, absent** | Candidate, reviewed, replicated, contradicted, superseded, and retired states with cross-day/cohort/model evidence | Positive examples accumulate without a disciplined mechanism for counterevidence | **P2-P3 / M** |
| Quantitative review validity | **Partial scaffolding** | Inter-reviewer agreement, adjudication, ranking enrichment, chance/rarity baselines, precision at review budget, scorer-reviewer separation, and audit trails | Review can confirm examples without establishing reliability or enrichment | **P2 / M** |
| Structured agent observation package | **Intended, absent** | Send claims, quantitative support, examples, counterexamples, missingness, provenance, context, and explicit questions rather than isolated episodes | An agent would receive insufficient constraints and overproduce plausible narratives | **P4 / M** |
| Literature analogy record | **Intended, absent** | Versioned links that distinguish close analogies, partial analogies, and superficial similarity, with source provenance | Literature retrieval cannot be audited or separated from interpretive overreach | **P4 / M** |
| Competing hypothesis state | **Intended, absent** | Multiple explanations with support, conflict, unique predictions, analyses, experiments, status/confidence, literature provenance, and change history | The workflow encourages attachment to one story rather than discriminating tests | **P4 / L** |
| Audio and thermal evidence adapters | **Audio absent; thermal placeholder** | Add synchronized evidence with explicit clock/routing/QC uncertainty | Relevant multimodal evidence remains outside local episode judgment | **P0 as phenomenon requires; otherwise P5 / M each** |
| Broad importer/NWB/DANDI/API ecosystem | **Intended enabling infrastructure, absent or partial** | Generalize representations and exchange after semantics are stable | Limits adoption and model breadth, but does not itself create observations | **P5 / M-L** |

### Minimum `Observation` contract

An `Observation` must be a first-class, versioned object rather than prose in an annotation note. At minimum it should contain:

- stable `observation_id`, human-readable claim, and machine-readable cohort/query definition;
- supporting episode IDs and deliberately retrieved counterexample episode IDs;
- comparison/baseline definition, effect size or prevalence, temporal scope, and subject/cohort scope;
- evidence-quality and missingness summaries with the rules used to compute them;
- originating state-model/importer IDs and versions, source-data manifests, and derivation version;
- reviewer status, replication status, related/conflicting observations, and append-only change history;
- candidate hypothesis IDs, literature-link IDs, proposed discriminating analyses, and future experiments;
- lifecycle state: `candidate | reviewed | replicated | contradicted | superseded | retired`.

### Required episode-to-observation operations

The compiler must preserve provenance while supporting recurrence/grouping, matched comparisons, explicit null and rarity baselines, context enrichment, temporal emergence/decay, individual consistency, cross-day/cohort replication, counterexample retrieval, and sensitivity to QC and detector/model version. Ordinary counts or time budgets are useful ingredients, not substitutes for this layer.

### Agent and hypothesis interfaces

The agent input should be a versioned observation package containing the claim, quantitative support, representative positive examples, counterexamples, missing-data limitations, model/importer provenance, environmental/social context, and explicit research questions. Agent output should be structured records, not free-form prose only:

- literature links classified as close, partial, or superficial analogies;
- at least two competing hypotheses where evidence permits;
- supporting and conflicting evidence for each hypothesis;
- predictions unique enough to distinguish hypotheses;
- analyses possible with existing data and experiments required beyond it;
- evidence that would weaken, supersede, or retire each hypothesis;
- model/prompt/tool versions and append-only change history.

### Unverified - needs human decision

- **Thermal evidence comparison:** the local panel is a placeholder, but no retained official feature index advertises a comparable thermal episode workspace. Expanding the reference set would break the cap.
- **Novel lens methods:** recurrence, surprise, context dependence, and consequence are schema slots without implementations. None of the retained toolbox feature indexes claims the same lens system. A defensible method comparison would require a literature review, which was not needed for this toolbox audit and was not started.
- **Concurrent multi-user review service:** local JSONL appends have no locking or identity service. The retained docs establish multiple-observer analysis in BORIS, not a server-grade concurrent annotation backend; no stronger comparison is claimed.

## Phase 4 - Revised roadmap and verdict

### Priority 0 - Demonstrate one complete scientific workflow

Use one real phenomenon already represented in the repository, preferably strict lagged path reuse because its candidate status and video-routing uncertainty are explicit. Demonstrate:

```text
candidate episodes
    -> evidence review
    -> replicated observation
    -> literature connections
    -> competing hypotheses
    -> discriminating analysis
```

The demonstration must not rename strict path reuse as confirmed social following. It should review positives and matched counterexamples across multiple eligible nights, establish principal detector failure modes, define the observation criterion before replication assessment, and require competing hypotheses to produce distinct predictions.

#### Priority 0 success quantities

All denominators are fixed by an explicit review/eligibility manifest rather than by post-hoc filtering.

$$U=\frac{N_{usable}}{N_{reviewed}}$$

where `usable` means the preregistered required modalities, timing, identity, and QC are sufficient for judgment. **Text:** usable-evidence rate; unitless proportion from 0 to 1. It measures evidence availability, not detector correctness.

$$R_v=\frac{N_v}{N_{reviewed}},\quad v\in\{confirmed,rejected,ambiguous\}$$

**Text:** verdict-specific review rates; unitless proportions from 0 to 1. Their interpretation depends on a fixed candidate queue and review protocol.

$$T_{review}=\operatorname{median}_e(t_{submit,e}-t_{open,e})$$

**Text:** median active review time per episode in seconds. Pauses or abandoned sessions require explicit handling; the current app does not record these timestamps.

$$F_j=\frac{N_{rejected\ due\ to\ failure\ mode\ }j}{N_{rejected}}$$

**Text:** fraction of rejected candidates assigned to detector/evidence failure mode $j$; unitless, 0 to 1. Failure modes must be mutually exclusive or explicitly multi-label, because the denominator interpretation changes.

$$R_{night}=\frac{N_{eligible\ nights\ meeting\ the\ preregistered\ observation\ criterion}}{N_{eligible\ nights}}$$

**Text:** cross-night recurrence proportion; unitless, 0 to 1. An eligible night must pass declared source-availability and QC requirements. This is observation recurrence, not raw episode frequency.

$$Q_{counter}=\frac{N_{counterexamples\ passing\ the\ matching/evidence\ rubric}}{N_{counterexamples\ reviewed}}$$

**Text:** usable counterexample fraction; unitless, 0 to 1. The rubric must require adequate evidence and a declared match on exposure/context while contradicting or bounding the claim.

Robustness to QC thresholds and model/importer versions must be reported as a sensitivity table over declared configurations, not compressed into an unexplained score. Each hypothesis must also state at least one prediction whose expected result differs from another hypothesis; otherwise it is not discriminating.

### Priority 1 - Freeze episode and observation semantics

Before broad interoperability, define the episode contract for every state model/importer: event versus interval semantics, candidate versus inferred-state meaning, permitted subject count and ordered roles, overlap rules, boundary meaning/precision, confidence meaning, required evidence/provenance, and allowable human actions. Define and version the `Observation` schema and lifecycle at the same time.

### Priority 2 - Complete evaluation and review validity

Implement inter-reviewer agreement, adjudication, ranking enrichment against explicit chance/rarity baselines, precision at a fixed review budget, scorer-versus-reviewer separation, observation replication criteria, and append-only audit histories for episode judgments and observation changes. Do not add new lens scores before existing ranking claims can be evaluated.

$$P@K=\frac{1}{K}\sum_{i=1}^{K}\mathbf{1}[v_i=confirmed],\qquad E@K=\frac{P@K}{p_0}$$

where the first $K$ episodes are fixed before review and $p_0$ is the confirmed prevalence under a preregistered chance or rarity baseline. **Text:** $P@K$ is confirmed precision at review budget $K$ (episodes), a proportion from 0 to 1; $E@K$ is fold enrichment over the stated baseline, with 1 meaning no enrichment. Neither is valid if scores were visible during judgment or the baseline was selected afterward.

$$\kappa=\frac{p_o-p_e}{1-p_e}$$

where $p_o$ is observed reviewer agreement and $p_e$ is agreement expected from the reviewers' marginal verdict frequencies. **Text:** Cohen's kappa is a chance-adjusted, unitless agreement statistic, conventionally ranging from -1 to 1. It must be reported with the verdict schema, matching window/unit, sample size, and prevalence because rare categories can make kappa misleading.

### Priority 3 - Build the Observation Compiler and Registry

Treat episode grouping, matched comparisons, counterexample retrieval, baseline/null evaluation, recurrence/emergence, cross-day/cohort replication, and model-sensitivity analysis as a core scientific subsystem. It should emit versioned `Observation` objects reproducible from episode queries and manifests, not one-off notebook prose.

### Priority 4 - Add the Literature and Hypothesis Agent

Only expose observations that include quantitative support, counterexamples, missingness, context, and provenance. Store structured literature analogies and multiple competing hypothesis records with predictions, tests, falsifiers, and change history. Human review remains responsible for accepting scientific claims and experimental recommendations.

### Priority 5 - Generalize infrastructure when demanded

Add a small versioned importer contract, then NWB/DANDI exchange, Arrow-native nested storage, cursor/row-group paging, packaging, and public APIs as real scale, collaboration, or exchange requirements justify them. These remain valid engineering gaps, but they enable the scientific workflow rather than define it.

### Explicit non-goals

- Do not implement native VAE/AR-HMM pose segmentation, frame-level track correction, or identity repair. Import versioned outputs from upstream tools.
- Do not clone BORIS's complete live-coding and frame-level annotation surface. Add only review operations required for candidate validation and observation formation.
- Do not attach an unconstrained agent directly to isolated episodes or treat generated prose as an observation.

### Claims that exceed the current code

- `README.md:64-67` describes Parquet filtering and pagination, but `query_index()` materializes and sorts every matching queue row before `offset/limit`. This is bounded post-read pagination, not scalable paging.
- Nested values are JSON strings inside Parquet rather than Arrow-native structs/lists, so nested predicate pushdown is absent.
- Real and synthetic episodes occupy separate mode-selected stores rather than one physical repository.
- Completeness is guaranteed only for outputs of the two named importers in the fixed 15-minute slice, not arbitrary days, models, or modalities.
- No `Observation`, observation registry/compiler, agent observation package, literature record, hypothesis object, replication lifecycle, or hypothesis audit trail exists in `episode_browser/`.

### Final verdict

The current implementation is a scientifically careful vertical slice of a larger **representation-aware behavioral observation and hypothesis-generation workbench**. Its strongest implemented contribution is the evidence and provenance layer needed to prevent model-generated behavioral candidates from becoming unsupported scientific claims. Its largest missing scientific component is the observation layer that converts reviewed episodes into quantitative, falsifiable, and literature-connectable phenomena. The subsequent agent layer should operate on these observation objects to generate competing hypotheses and discriminating analyses, not narratives for isolated episodes.

**Without an observation layer, attaching an agent directly to episodes will scale storytelling rather than scientific discovery.**

### Prior-audit claims revised or not verifiable

- **Global `AHEAD` assessments were not verifiable.** Absence from three bounded feature/API documentation sets does not establish absence from the field. These are now local differentiators with an explicit search-limit caveat.
- **The previous final verdict became misleading under the corrected scope.** Calling the product a vertical-slice episode-review prototype was accurate for current code but incomplete as a product definition; the browser is Layer 1 of the intended system.
- **The previous priority ordering was not scientifically justified.** Import interoperability and storage/package maturity are real gaps, but the audit had no evidence that they should precede a complete episode-to-observation-to-hypothesis demonstration.
- **Video `PARITY` was too coarse.** The current browser supports selected-episode inspection, but BORIS offers a substantially more mature media-coding workflow; the revised assessment states limited functional parity and different scope.
- **No Phase 1 code finding was disproved by this revision.** The correction changes architecture, comparator interpretation, and roadmap priority, not the verified implementation inventory.
