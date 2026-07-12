# Episode Browser scope-audit scientific reframe

**Date:** 2026-07-11  
**Git state:** uncommitted  
**Artifact:** [`../episode_browser/SCOPE_AUDIT.md`](../episode_browser/SCOPE_AUDIT.md)

## Why this changed

The first scope audit correctly characterized the implemented `episode_browser/` vertical slice, but it let that implementation boundary define the product boundary. The intended system is broader: episode evidence review is Layer 1 of an observation-centered workflow that should compile reviewed episodes into quantitative scientific observations and, only after that, support constrained literature search and competing-hypothesis generation.

## Framing changes

- Added the three-layer architecture: Episode Browser, Observation Compiler/Registry, and Literature/Hypothesis Agent.
- Added explicit status categories for implemented code, partial scaffolding, intended-but-absent architecture, and non-goals.
- Made `Observation` the principal missing scientific abstraction and specified its minimum provenance, support, counterexample, baseline, replication, literature, hypothesis, and lifecycle fields.
- Reframed BORIS as a manual-coding/review comparator and VAME/Keypoint-MoSeq as upstream representation/segmentation comparators.
- Removed unsupported `AHEAD` wording. Features absent from the bounded comparator documentation are now called local differentiators with an explicit search-limit caveat.
- Added structured agent input/output and competing-hypothesis state requirements. The audit explicitly rejects sending isolated episodes directly to an unconstrained agent.

## Priority changes

The roadmap now starts with one complete real scientific workflow, then freezes episode/observation semantics, completes review validity, builds the Observation Compiler/Registry, adds the literature/hypothesis agent, and generalizes import/exchange/storage infrastructure when scale or collaboration requires it. NWB/DANDI, Arrow-native Parquet, cursor paging, packaging, and public APIs remain valid engineering work but no longer outrank demonstration of the scientific observation workflow.

Priority-0 success quantities are defined in the audit with formulas, units, denominators, and interpretations: usable-evidence rate, verdict rates, review time, failure-mode fractions, cross-night recurrence, and counterexample usability. Review validity also defines precision/enrichment at fixed budget and Cohen's kappa. No empirical values are claimed because the required review workflow has not yet been run.

## Code findings preserved unchanged

- explicit state-model/importer provenance and candidate path-reuse semantics;
- separate source-data availability and importer coverage;
- sparse lens scores and missing-not-zero behavior;
- unverified camera routing and cross-device clock alignment;
- append-only episode judgments and blind-log scaffolding;
- JSON-encoded nested Parquet fields and post-read pagination;
- partial schema validation, hard-coded real-slice ingest, absent benchmark, and absent package/API release contract;
- missing thermal evidence, absent real lens ranking, and lack of review agreement/adjudication;
- strict lagged path reuse remains a candidate detector output, not confirmed social following.

No source code, raw data, derived episode data, annotations, or analysis results were changed.

## Verification

- Re-read the complete revised audit and confirmed all Phase 1 inventory rows remain present.
- Searched for and removed comparator-level `AHEAD` assessments.
- Confirmed the intended Observation, compiler, agent package, hypothesis state, lifecycle, non-goals, and P0-P5 roadmap are explicitly marked implemented, partial, intended/absent, or non-goal.
- Confirmed every new Priority-0 derived quantity has a mathematical definition plus plain-language units and interpretation.
- Confirmed the change-log index links to this file.

## Remaining limits

This is an architecture and scope correction, not implementation of the Observation Compiler or agent. The external comparison remains bounded to the original official documentation set; no claim of global uniqueness or state-of-the-art leadership is made.
