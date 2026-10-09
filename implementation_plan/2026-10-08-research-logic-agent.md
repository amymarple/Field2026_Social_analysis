# Research Logic Agent: a maintained logic graph + interactive map of the research (2026-10-08)

**Status:** DONE 2026-10-08 (minimal version) — [change log](../change_log/2026-10-08-research-logic-agent.md); map https://claude.ai/artifact/F5rCafmi6VuoXspRbEuczS.

**The user (2026-10-08):**
- Build a reusable **Research Logic Agent** that links the research logic: why an analysis was done, what its result
  changed, and what next step would separate the remaining explanations.
- It does not run statistics, edit results or upgrade conclusions.
- **First task:** the sleep analysis so far (v1, v2, Phases 0–6). After that, each new Phase updates the map
  incrementally.
- **Called only for real research steps**, never for preprocessing (scoring, LFP / EMG extraction, sync, storage).
- **Wants an interactive web page** to follow the research as it moves.
- **Model routing:**
  - the agent runs on Opus;
  - a conflict between sources goes to a Fable subagent for adjudication;
  - the Codex session "量化每日NREM与REM并绘制昼夜图" ("astra") may review the logic flow as text only (and
    PNG / SVG if ever needed), never code or web pages.

## Deliverables (minimal version, no platform)

| what | where |
|---|---|
| agent definition | `.claude/agents/research-logic.md` (model `opus`); thin Codex mirror `.codex/agents/research-logic.toml` |
| entry point | `.claude/skills/research-logic/SKILL.md` (`/research-logic` or "更新研究逻辑：Phase X，报告路径……，审查路径……"); thin mirror `.agents/skills/research-logic/SKILL.md` |
| machine-readable graph | `research_logic/graphs/sleep_2026c.yaml` (the only place the logic is written) |
| validator + builder | `research_logic/logic_map.py` (`check`, `build`, `--selftest`); page template `research_logic/map_template.html` |
| human-readable map | `research_logic/maps/sleep_2026c.html`, generated from the YAML (never hand-edited); published as a private Artifact for live viewing |
| usage | `research_logic/README.md` |

## Graph model

- **Nodes.** Stable text IDs. Types:
  - `question`, `hypothesis`, `prediction`, `analysis`, `result`, `judgment`, `next_step`;
  - plus `basis`: a measurement or data condition that results depend on. A `basis` node is not a research step.
- **Each node carries:**
  - the `branch` (sub-question) it belongs to;
  - content, `status`, `scope`, `sources` (repo file + line + an anchor string that must appear there);
  - `phases`: a source label only, never used for layout;
  - `round_added`, `changes`.
- **Edges** are directed and typed:
  - `proposes`, `tests`, `yields`, `supports`, `weakens`, `cannot_distinguish`, `depends_on`, `revises`, `supersedes`;
  - each may carry a `scope` / `note`.
- **Rules the validator enforces:**
  - IDs are unique, and every edge endpoint exists;
  - each edge type joins allowed node types;
  - source files exist, and anchors appear within ±3 lines of the cited line;
  - a superseded node names its replacement, and the replacement has a `supersedes` edge to it;
  - a hypothesis status matches the verdict edges of its branch's current judgment;
  - a null result states its reading (a precise null within scope, or underpowered);
  - a `mechanism`-level hypothesis cannot be `supported` without an intervention-design result;
  - every next step names the hypotheses it would separate and at least two outcomes, each with the judgment it would
    change;
  - every round answers the five questions and lists what it added and changed;
  - conflicts list both sides with sources.
- **Rounds.** Each update is a round:
  - inputs (report and review paths);
  - the five answers: aim / what was answered / supported or weakened / still indistinguishable / next step with its
    outcome-dependent consequences;
  - added and modified IDs;
  - reviews (Fable / astra) and conflicts.

## Page (generated)

- **Overview** (square-ish grid):
  - the core question;
  - the competing top-level accounts, with a matrix of how each sub-question's current judgment bears on them;
  - this round's five answers;
  - one card per sub-question, showing the flow competing hypotheses → tests → results → judgment → next step with
    labelled arrows.
- **Expanding a card** draws the full branch:
  - hypotheses, analyses with their results, judgment and next steps;
  - typed, labelled edges;
  - superseded results with their replacement, on a toggle.
- **Clicking a node** opens its evidence: status, scope, numbers, allowed and forbidden wording, sources (repo path
  + GitHub line link), edges and revision history.
- **Below the cards:** conflicts, the round log and a filterable node index.
- **Implementation:** vanilla JS, no library; the graph is embedded as JSON; light and dark themes.

## Order

1. This plan.
2. `logic_map.py` + `--selftest`.
3. The first graph from the claim audits and reports (v1, v2, Phases 0–6, mic pilot, quantification).
4. `check`, then `build`.
5. Fable adjudication of the open conflicts and astra's logic review, both run in parallel.
6. Fold their findings in, as round 1's review record.
7. Publish; then the change log, the index READMEs and the CLAUDE.md map.

Nothing is pushed.
