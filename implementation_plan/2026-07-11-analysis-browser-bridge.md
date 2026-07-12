# Implementation plan - deterministic Analysis to Browser Bridge

**Date:** 2026-07-11  
**Scope tier:** Large (new shared contract, CLI, consumer API, and cross-subsystem handoff)  
**Status:** implemented and verified  
**Git state:** dirty worktree with unrelated user changes; bridge work will be additive and will not revert them.

## Goal and motivation

Create a deterministic, repository-root exchange layer between scientific analyses and the Episode Browser:

```text
analysis output
-> explicitly classified draft bundle
-> deterministic validation and sealing
-> immutable published exchange
-> verified consumer reader
-> browser-specific deterministic adapter
```

The bridge must prevent downstream code from inferring scientific object type, temporal semantics, biological meaning, or missing values from Markdown, filenames, or arbitrary columns.

## Current problem

Analysis subsystems write heterogeneous CSVs, plots, reports, and `run_manifest.json` files. The existing manifests preserve useful run provenance but do not share one object classification, destination map, record contract, claim boundary, payload hash, or publication seal. `episode_browser/build_real_slice.py` therefore contains a one-off import for two WISER analyses. There is no safe general handoff for future analyses, and aggregate metrics or observation-level claims could be mistaken for time-local episodes.

No equivalent `analysis_exchange/` or sealed-bundle implementation exists. Existing functionality to reuse includes:

- Git commit and run-manifest conventions in `wiser_analysis_utils.write_run_manifest`;
- Episode Browser state-model registry, schema validation, and repository APIs;
- `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` project conventions;
- implementation-plan/change-log index workflow in `AGENTS.md`.

## Contract and object classification

Schema version `0.1.0` will support exactly one object type per bundle:

- `episode_candidate -> episode_browser`
- `aggregate_metric -> observation_compiler`
- `observation_candidate -> observation_registry`
- `model_evaluation -> evaluation_registry`
- `artifact_only -> artifact_store`

Every result declares `allowed_claim` and `forbidden_promotions`. Publication means validated/stable handoff, not biological confirmation. Separate scientific object types require separate bundles.

Episode candidates additionally require a stable record key; UTC point/interval/bounded-window semantics; explicit interval convention; subject fields and optional ordered roles; original candidate label; detector/model/importer and run provenance; QC fields; score meaning/unit declarations; limitations; a local primary machine-readable payload; and evidence-routing fields. The v0 browser adapter will accept interval or bounded-window records only and will fail loudly for point events without an explicit conversion rule.

## New shared subsystem

Create:

- `analysis_exchange/contracts/analysis-result-bundle-0.1.0.schema.json`
- `analysis_exchange/python/bridge.py`: constants, safe-path handling, validation, hashing, publication, and seal verification
- `analysis_exchange/python/reader.py`: browser-independent published-bundle iterator
- `analysis_exchange/scripts/bridge_cli.py`: `new`, `validate`, `publish`, `verify`, and `list`
- `analysis_exchange/examples/lagged-path-reuse-example/`: valid draft fixture
- `analysis_exchange/published/<example-bundle>/`: real CLI-published and sealed example
- `analysis_exchange/tests/test_bridge.py`: standard-library unit tests
- `.gitkeep` markers for empty staging/rejected directories
- package markers and practical `analysis_exchange/README.md`

The CLI will use the Python standard library. The JSON Schema documents the stable external contract; deterministic Python validation remains authoritative so the bridge has no new runtime dependency.

## Publication and immutability

`publish` will:

1. require a source directory under `analysis_exchange/staging/`;
2. validate the draft;
3. compute SHA-256 for every local payload;
4. set `status=published` and an ISO-8601 UTC publication timestamp;
5. write canonical `manifest.json`;
6. hash the exact manifest bytes;
7. write `BUNDLE.SEALED` with bundle/schema IDs, manifest hash, and seal time;
8. move the directory to `published/` without overwrite.

Corrections use a new safe bundle ID and `supersedes_bundle_id`. Code and instructions will prohibit editing published bundles; `verify` detects any manifest or payload mutation.

## Consumer and browser integration

`analysis_exchange.python.reader.iter_published_bundles` will scan only `published/`, ignore incomplete directories, reject unsafe paths, optionally filter object type/destination, and verify hashes/seals.

Add `episode_browser/utils/exchange_import.py` as the smallest browser integration boundary. It will call the shared reader, accept only verified import-ready `episode_candidate -> episode_browser` bundles, load supported local record payloads, and map records deterministically from `record_contract`. It will preserve source IDs, original candidate labels, detector/importer/run provenance, roles, QC, evidence fields, and missing scores. It will reject unknown state models, unsupported temporal/subject semantics, missing source fields, or ambiguous mappings. It will not scan `staging/` or implement observation/evaluation consumers.

## Claude and Codex instructions

- Add `.claude/agents/analysis-result-bridge.md` and `.claude/skills/export-analysis-result/SKILL.md` using existing project frontmatter conventions.
- Append bridge publication rules to `CLAUDE.md` without replacing current guidance.
- Append verified-consumer and immutability rules to `AGENTS.md` without replacing current guidance.

## Inputs and outputs

Inputs are derived analysis outputs and existing run manifests, always read-only. Draft/published bundle payloads are copied derived artifacts or external URIs; raw video and field data are not copied into Git. Outputs are small JSON/JSONL/CSV manifests, hashes, seals, and instructions under `analysis_exchange/`.

## Verification

Add tests for:

1. valid example validation;
2. destination/object mismatch;
3. aggregate-to-browser rejection;
4. missing UTC episode time contract;
5. missing payload;
6. publication hashes/seal;
7. successful verification;
8. payload tamper detection;
9. duplicate publication refusal;
10. reader filtering;
11. unsafe payload paths;
12. browser adapter mapping and fail-loud unknown-state-model behavior.

Run:

```powershell
python -m unittest discover analysis_exchange\tests -v
python episode_browser\selftest.py
python analysis_exchange\scripts\bridge_cli.py validate analysis_exchange\examples\lagged-path-reuse-example
python analysis_exchange\scripts\bridge_cli.py verify analysis_exchange\published\<example-bundle-id>
python analysis_exchange\scripts\bridge_cli.py list
```

The integration is complete only if a real sealed example is readable through both the shared reader and browser adapter and all relevant tests pass.

## Non-goals

- No Observation Compiler, Observation Registry, evaluation registry, or Literature/Hypothesis Agent.
- No automatic scientific interpretation from reports or column names.
- No message queue, database/web service, generic plugin marketplace, or browser rewrite.
- No modification of raw data or existing published analysis outputs.
- No silent biological promotion, aggregate-to-episode conversion, missing-to-zero conversion, or detector/reviewer conflation.
