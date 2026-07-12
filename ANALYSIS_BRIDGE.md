# ANALYSIS_BRIDGE.md — machine-readable analysis handoff

`analysis_exchange/` is the deterministic producer → consumer contract between analysis code and downstream
consumers (Codex, the Episode Browser). It is at repository root because both agent ecosystems must read the
same contract; `.claude/` holds instructions only, not shared data. Full details live in
[`analysis_exchange/README.md`](analysis_exchange/README.md); this file is the repo-level overview.

## Lifecycle

```
analysis output -> staging draft -> validate -> publish/seal -> verified consumer
```

- `analysis_exchange/staging/` — mutable drafts (analysis tooling or the Claude bridge agent write here).
- `analysis_exchange/published/` — immutable, validated, sealed bundles. Consumers read **only** here,
  through `analysis_exchange.python.reader`, with seal + payload verification enabled.
- `analysis_exchange/rejected/` — optional human hold area.
- `contracts/` — versioned JSON schema (`analysis-result-bundle-0.1.0.schema.json`).

## Rules (do not weaken)

- Classify every exported object as exactly one of `episode_candidate`, `aggregate_metric`,
  `observation_candidate`, `model_evaluation`, `artifact_only`. Different types from one run = separate
  bundles. Only `episode_candidate` may enter the Episode Browser.
- Preserve analysis/run/model IDs, git provenance, input manifests, params, QC, timestamp + subject
  semantics, score meanings/units, missing values, limitations, and original candidate labels. **Missing
  scores never become zero.**
- State the strongest directly supported `allowed_claim` and explicit `forbidden_promotions`. Never
  strengthen a computational result into a biological interpretation. Aggregates are not episodes; Markdown
  is not a payload. Publishing seals the handoff; it does not confirm the scientific claim.
- Corrections create a **new** bundle with `supersedes_bundle_id`; the prior sealed bundle is retained.
- Never hand-create/edit/delete anything under `published/`; publish only via the CLI.

## Workflow

```powershell
python analysis_exchange\scripts\bridge_cli.py new      --analysis-id <id> --analysis-version <v> --object-type <type> --title "<t>"
python analysis_exchange\scripts\bridge_cli.py validate analysis_exchange\staging\<bundle_id>
python analysis_exchange\scripts\bridge_cli.py publish  analysis_exchange\staging\<bundle_id>
python analysis_exchange\scripts\bridge_cli.py verify   analysis_exchange\published\<bundle_id>
```

Claude users can run `/export-analysis-result <output-path>`, which delegates to the `analysis-result-bridge`
subagent (it creates and validates a real bundle, not a summary). Verify offline with
`python -m unittest discover analysis_exchange\tests` and `python episode_browser\selftest.py`.
