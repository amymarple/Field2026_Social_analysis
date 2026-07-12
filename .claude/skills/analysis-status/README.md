# `/analysis-status` — WISER analysis decision-map dashboard

Turns the dense `wiser/ANALYSIS_STATUS.md` tracker (which mixes pipeline status,
measurement validity, candidate findings, superseded interpretations, blockers, future modules, and
publication requirements) into a **graph-first, human-readable scientific decision map** — repeatably,
whenever the analysis changes. It reorganizes; it never changes a conclusion.

## What it answers

1. Where is the analysis now?
2. What do we actually know?
3. What has been ruled out or corrected?
4. What remains only a candidate?
5. Which blockers prevent stronger claims?
6. What are the next three actions, in dependency order?

## Components (project-level, checked into the repo)

| File | Role |
|---|---|
| `.claude/skills/analysis-status/SKILL.md` | The callable Skill. Finds the tracker, parses focus/path args, delegates to the subagent in an isolated context, returns only the dashboard. |
| `.claude/agents/analysis-status-simplifier.md` | The specialized **read-only** subagent (Read/Grep/Glob). A status *compiler*, not a new analyst: applies the source hierarchy, keeps measurement/result/interpretation separate, and produces the eight-section dashboard. |
| `.claude/skills/analysis-status/README.md` | This file. |
| `docs/analysis_status_dashboard_example.md` | A saved example produced by running the workflow once against the current tracker. |

## Installation

Nothing to install — these are project-level Claude Code files. As soon as they are on disk under
`.claude/`, Claude Code discovers the Skill and the subagent for this repository. (If a Claude Code
session was already open when they were added, start a new session so it picks them up.)

Requirements: the canonical tracker must exist at `wiser/ANALYSIS_STATUS.md` (or pass
an explicit path). No Python, no data, no network — the workflow only reads Markdown.

## Invocation

```text
/analysis-status                 # full dashboard, current global status
/analysis-status next            # blocker chain + next executable analysis + what to defer
/analysis-status routes          # route motifs / vocabulary-vs-manifold / georeference
/analysis-status sleep           # rest-vs-sleep / multi-site / hierarchy / temperature
/analysis-status social          # following / herd-vs-dyads / temporal-order limits
/analysis-status policy          # locomotor state / initiation / termination / identifiability
/analysis-status publication     # defensible claims / candidate-vs-publishable / replication
/analysis-status <path.md>       # explicit tracker path instead of auto-discovery
/analysis-status <focus> <path>  # focus + explicit path
```

The first argument matching `{next, routes, sleep, social, policy, publication}` is the focus; any
argument ending in `.md` is an explicit tracker path. Both are optional; with no argument you get the
full global dashboard.

## Output shape

Eight sections, always in this order:

1. **Current state in one sentence** (≤ ~70 words).
2. **Decision map** — one Mermaid `flowchart TD`, organized by scientific dependency (not filenames).
3. **What we actually know** — a ≤8-row table grouped into scientific questions.
4. **What was ruled out or corrected** — 3–6 corrections as old → why it failed → replacement.
5. **Blocker chain** — `blocker -> claim it prevents -> resolving action`, each classed measurement /
   sample-design / implementation.
6. **Next three moves** — measurement unblock → next executable science → validation/replication.
7. **Scope-safe language** — *Allowed now* vs *Do not say yet*.
8. **Provenance** — canonical file + relevant change logs, with read-vs-referenced flags.

## Guarantees

- **Read-only.** A normal invocation never edits `ANALYSIS_STATUS.md` or any analysis file.
- **No promotion.** `⚠️ candidate` stays candidate; `⛔ blocked` stays blocked.
- **Faithful to corrections.** Explicit retractions/supersessions win over older or longer statements.
- **Layer-safe.** Rest ≠ sleep, temporal order ≠ leadership, recurrence ≠ memory, shared corridors ≠
  discrete vocabulary, WISER bouts ≠ validated legs, inches ≠ physical direction/road/cooling claims.

## Rendering the Mermaid graph

The decision map is a fenced ```mermaid``` block. It renders on GitHub, in VS Code (with a Mermaid
extension), and at <https://mermaid.live>. If you only need the text, the eight sections read fine
without rendering the graph.
