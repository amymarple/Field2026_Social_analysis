# Analysis Exchange

`analysis_exchange/` is the deterministic handoff between analysis producers and downstream
consumers. It is at repository root because both Claude Code and Codex/browser code must read the
same contract. `.claude/` contains instructions only; it is not a shared data directory.

## Lifecycle

```text
analysis output -> staging draft -> validate -> publish/seal -> verified consumer
```

- `staging/`: mutable drafts written by analysis tooling or the Claude bridge agent.
- `published/`: immutable, validated bundles. Consumers read only here.
- `rejected/`: optional holding area for drafts a human chooses not to publish; no automatic move.
- `examples/`: editable fixtures and documentation examples, not consumer input.
- `contracts/`: versioned JSON contracts.
- `python/`: validator, publisher, verifier, and consumer reader.
- `scripts/`: cross-platform CLI.

Publication records hashes and creates `BUNDLE.SEALED`. It means the handoff is stable and internally
valid, not that a detector output or biological interpretation has been confirmed.

## Object types and destinations

| Object type | Meaning | Destination |
|---|---|---|
| `episode_candidate` | Time-local event/interval/window for evidence review | `episode_browser` |
| `aggregate_metric` | Summary over a broader unit | `observation_compiler` |
| `observation_candidate` | Repeated/comparative cross-episode pattern | `observation_registry` |
| `model_evaluation` | Detector/ranking/calibration/robustness result | `evaluation_registry` |
| `artifact_only` | Supporting report, figure, notebook, image, or video | `artifact_store` |

Different object types from one analysis require separate bundles. Only `episode_candidate` may enter
the Episode Browser.

## Claim boundary

Every manifest states `allowed_claim` and `forbidden_promotions`. Missing values stay missing; missing
scores never become zero. Aggregate rows are not fabricated into episodes. Reviewer decisions remain
separate from detector output. Markdown is supporting material, never a replacement for records.

## Basic workflow

From repository root in PowerShell:

```powershell
python analysis_exchange\scripts\bridge_cli.py new `
  --analysis-id lagged-path-reuse `
  --analysis-version 1.0.0 `
  --object-type episode_candidate `
  --title "Lagged path-reuse candidates"

python analysis_exchange\scripts\bridge_cli.py validate `
  analysis_exchange\staging\<bundle_id>

python analysis_exchange\scripts\bridge_cli.py publish `
  analysis_exchange\staging\<bundle_id>

python analysis_exchange\scripts\bridge_cli.py verify `
  analysis_exchange\published\<bundle_id>

python analysis_exchange\scripts\bridge_cli.py list
```

`new` creates a conservative, non-import-ready template and captures Git repository/commit/dirty
state when available. Complete the record contract, payload declarations, provenance, claim boundary,
and blockers before publication.

In schema v0.1, an import-ready episode bundle uses JSONL, JSON, or CSV for its single
`primary_records` payload so the standard-library validator can inspect record keys, UTC intervals,
subjects, roles, and run IDs deterministically. Parquet may be included as an additional payload and
is supported by the browser adapter, but it is not accepted as the only import-ready primary payload.

Claude users can invoke `/export-analysis-result <output-path>`. The skill delegates to the
`analysis-result-bridge` subagent, which must create and validate a real bundle rather than summarize
the output.

## Codex and browser workflow

Use the shared reader; do not scan bundle directories independently:

```python
from pathlib import Path
from analysis_exchange.python.reader import iter_published_bundles

for bundle in iter_published_bundles(
    Path("analysis_exchange"),
    destination="episode_browser",
    object_type="episode_candidate",
    verify=True,
):
    print(bundle.bundle_id, bundle.local_payloads(role="primary_records"))
```

The browser adapter is `episode_browser/utils/exchange_import.py`. It additionally requires
`import_ready=true`, no blockers, a registered `state_model_id`, and an unambiguous interval mapping.
It preserves original candidate labels as provenance and does not manufacture human labels or lens
scores.

## Same or separate repositories

The default is this same-repository directory. For a separate analysis repository or shared drive,
copy/synchronize complete sealed bundle directories into a consumer-side `published/` directory and
point the reader at that exchange root. Transfer the whole directory atomically; an incomplete
directory is ignored. Always run `verify` after transfer. Never synchronize mutable staging drafts as
consumer input.

## Corrections

Published bundles are not edited or replaced. Create a new bundle, set `supersedes_bundle_id` to the
old published bundle ID, explain the correction in provenance, publish, and retain both bundles. A
consumer can then apply its own explicit supersession policy without losing history.

## Example and tests

`examples/lagged-path-reuse-example/` is a valid draft fixture with a deliberately narrow path-reuse
claim. A real sealed copy is generated under `published/` during repository verification.

```powershell
python -m unittest discover analysis_exchange\tests -v
python episode_browser\selftest.py
```
