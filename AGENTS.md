# AGENTS.md

Workflow conventions for coding agents (Claude Code, Codex) working in this repository are consolidated in
**[CONVENTIONS.md](CONVENTIONS.md)** — the single canonical constitution. Read it before any non-trivial
change. This file is a pointer so both agent ecosystems resolve to the same contract.

**Orient from [CLAUDE.md](CLAUDE.md), not from the code:** it carries the operational layer for every agent —
environments, self-tests, and a verified **code map** of each subsystem (pipeline order, entry points, in-repo vs
off-repo outputs, gotchas), a snapshot of the two sibling repos (recording setup, sync/clocks, where data is stored),
and the known gaps. Read it first; then open only the driver you are changing.

Highlights that bite if ignored (all detailed in CONVENTIONS.md):
- Analysis only — recording lives in the sibling `Field_2026_Social_Recording` repo; the field↔lab channel and
  storage map is `field2026-sync` (both cloned next to this repo).
- Cohort-appendable: parameterize with `--cohort`; never hard-code a season; bulk outputs go off-repo under
  `FIELD2026_ANALYSIS_OUT_ROOT` via `common/output_paths.py`.
- `implementation_plan/` before medium/large changes; `change_log/` after verification; keep the index
  READMEs current.
- Field-data flow: raw registration → schema → timestamp → sync/alignment → QC → derived → analysis →
  report → change log. Never assume two devices share a clock.
- Every derived quantity gets a formula **and** plain-text definition (`/analysis-definitions`).
- Link-integrity rule: a moved file with a broken inbound reference is a failure, not partial success.
