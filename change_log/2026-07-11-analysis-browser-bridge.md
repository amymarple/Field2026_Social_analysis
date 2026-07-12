# Deterministic Analysis to Browser Bridge

**Date:** 2026-07-11  
**Git state:** uncommitted dirty worktree; unrelated user changes preserved  
**Plan:** [`../implementation_plan/2026-07-11-analysis-browser-bridge.md`](../implementation_plan/2026-07-11-analysis-browser-bridge.md)

## Why

Analysis subsystems previously handed off heterogeneous tables, reports, figures, and run manifests. The Episode Browser had one-off WISER imports but no shared contract that prevented an aggregate result, observation candidate, or model evaluation from being interpreted as a local episode. There was also no deterministic claim boundary, destination rule, payload hash, publication seal, or browser-independent consumer API.

## What changed

### Shared contract and publication core

- Added root-level `analysis_exchange/` with a versioned JSON Schema, standard-library validator/publisher/verifier, CLI, reader API, examples, tests, staging/published/rejected lifecycle, and practical README.
- Enforced exactly one object type and destination:
  `episode_candidate -> episode_browser`, `aggregate_metric -> observation_compiler`,
  `observation_candidate -> observation_registry`, `model_evaluation -> evaluation_registry`, and
  `artifact_only -> artifact_store`.
- Required `allowed_claim`, `forbidden_promotions`, run/code provenance, record semantics, payloads, QC, limitations, blockers, and import-readiness consistency.
- Added episode-specific validation for stable keys, UTC point/interval/window fields, half-open intervals, subjects/roles, original candidate labels, model/importer versions, run IDs, QC, score meaning/unit/missingness, evidence fields, and inspectable primary records.
- `publish` now validates, hashes every local payload with SHA-256, writes published status/time, seals the exact manifest hash in `BUNDLE.SEALED`, and moves only a direct staging child without overwrite. `verify` rejects manifest or payload changes.
- Corrections require a new bundle and an existing `supersedes_bundle_id`; earlier published bundles remain intact.

### Consumer and browser boundary

- Added `analysis_exchange.python.reader.iter_published_bundles`, which scans only complete `published/` directories, supports destination/object filters, verifies seals and payloads, and exposes safe local paths without browser imports.
- Added `episode_browser/utils/exchange_import.py`, which consumes the shared reader and maps only verified, import-ready interval/window episode candidates. It fails for unregistered state models, blocked handoffs, unsupported point/cohort semantics, absent fields, run/label mismatches, and duplicate mapped IDs.
- The adapter preserves original candidate labels, allowed/forbidden claims, model/importer/run provenance, ordered roles, QC, evidence, and source scores under `linked_assets.analysis_exchange`. It does not add human labels or browser lens scores.

### Claude/Codex workflow

- Added `.claude/agents/analysis-result-bridge.md` and `.claude/skills/export-analysis-result/SKILL.md`.
- Updated `CLAUDE.md` so Claude writes drafts only to staging and publishes only through the CLI.
- Updated `AGENTS.md` so Codex/browser code reads only verified published bundles and never infers or promotes semantics.
- Updated `.gitignore` so mutable staging/rejected contents stay local while directory markers remain tracked.

### Real sealed example

Added and CLI-published `lagged-path-reuse-example`. Its allowed claim is limited to the later subject occupying positions near the earlier subject's path with aligned heading in the configured lag range. It explicitly forbids promotion to social following, information transfer, or a stable leader-follower relationship. The source record has a stable ID, UTC millisecond half-open interval, ordered subjects, best lag, QC, evidence routing, and original candidate label.

## Verification

Run with `C:\Users\Cornell\.conda\envs\cv\python.exe` and the environment's ffmpeg:

```powershell
python -m unittest discover analysis_exchange\tests -v
python episode_browser\selftest.py
python analysis_exchange\scripts\bridge_cli.py validate analysis_exchange\examples\lagged-path-reuse-example
python analysis_exchange\scripts\bridge_cli.py verify analysis_exchange\published\lagged-path-reuse-example
python analysis_exchange\scripts\bridge_cli.py list
python -m compileall -q analysis_exchange episode_browser\utils\exchange_import.py
python -m json.tool analysis_exchange\contracts\analysis-result-bundle-0.1.0.schema.json
```

Observed outcomes:

- Bridge suite: **21 tests passed**, covering all requested failure/publication/reader cases plus manifest tampering, conservative draft creation, browser mapping, unknown model rejection, and the repository-published example.
- Existing Episode Browser self-test: **PASS**. Parquet repository operations and real ffmpeg four-frame extraction were exercised with no skips.
- Draft example validation: **0 errors, 0 warnings**.
- Published example: `VERIFIED lagged-path-reuse-example`; `list` reports one `episode_candidate -> episode_browser` bundle.
- Shared reader returned the sealed example; browser adapter returned one `wiser_lagged_path_reuse_v1` episode with `labels=[]` and `lens_scores={}`.
- Python compilation, JSON syntax validation, and tracked-file whitespace checks passed.

No raw data, existing analysis output, annotation, or pre-existing published artifact was modified.

## Repository-convention adaptations

- The repository has no shared package/build or mandatory `jsonschema` dependency. A JSON Schema documents the external contract, while deterministic runtime validation uses only the Python standard library.
- To keep validation independent of PyArrow, schema v0.1 requires an import-ready episode's primary records to be JSONL, JSON, or CSV. Parquet is allowed as a secondary payload and remains readable by the browser adapter. A blocked/non-import-ready Parquet-only draft may still be preserved with a warning.
- Published immutability is enforced by workflow rules, no-overwrite publication, and cryptographic verification rather than OS read-only flags, which are unreliable across Git and shared filesystems.
- The browser integration is an adapter API rather than an automatic UI queue merge. This preserves the current bounded real queue and avoids inventing WISER/weather/video evidence for arbitrary incoming bundles.

## Remaining integration work

- Decide an explicit UI/session policy for presenting or materializing mapped exchange episodes alongside the bounded real repository. The adapter and verified source records are complete; automatic queue merge is intentionally not implemented.
- Register new state models before importing their bundles and add explicit point-event window adapters when scientifically justified.
- Implement future consumers for aggregate metrics, observation candidates, model evaluations, and artifacts. This change does not build those registries, the Observation Compiler, or the Literature/Hypothesis Agent.
- A separate-repository/shared-drive deployment still needs an operational atomic-transfer mechanism; verification after transfer is already supported.

