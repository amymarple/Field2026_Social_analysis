# Research Logic Agent + the logic map of the cohort-3 sleep analysis (2026-10-08)

Plan: [implementation_plan/2026-10-08-research-logic-agent.md](../implementation_plan/2026-10-08-research-logic-agent.md).

**The user asked for** a reusable agent that keeps the research logic:
- why an analysis was done, what its result changed, and what next step would separate the explanations;
- no statistics, no edits to results, no upgraded conclusions;
- a machine-readable graph plus a visual map generated from it, as an interactive page;
- used only for research steps, never preprocessing.

The first task was to map the whole sleep analysis so far.

## What changed

| file | what |
|---|---|
| `.claude/agents/research-logic.md` | the agent (model `opus`): scope gate (research only), hard rules, cost discipline, procedure per round, return format |
| `.claude/skills/research-logic/SKILL.md` | entry point "更新研究逻辑：Phase X，报告路径……，审查路径……" / `/research-logic`; orchestration (agent → Fable adjudication of conflicts → optional astra review → rebuild → republish) |
| `.codex/agents/research-logic.toml`, `.agents/skills/research-logic/SKILL.md` | thin mirrors that point to the canonical files (no copied rules, so no drift) |
| `research_logic/logic_map.py` | `check`, `build`, `show`, `index`, `--selftest` (12 checks) |
| `research_logic/map_template.html` | the interactive page (vanilla JS, light / dark, data embedded) |
| `research_logic/graphs/sleep_2026c.yaml` | the logic graph (the only place it is written) |
| `research_logic/maps/sleep_2026c.{html,json}` | generated |
| `research_logic/README.md` | schema, rules, usage |

The map is published as a private Artifact: https://claude.ai/artifact/F5rCafmi6VuoXspRbEuczS.

## The graph, round r1

**Size:**
- 192 nodes: 10 questions, 60 hypotheses, 4 predictions, 23 analyses, 64 results, 10 judgments, 10 next steps,
  11 measurement bases;
- 459 typed edges;
- 10 conflicts (3 open).

**Structure:**
- The core question has 9 sub-questions:
  - history matters?
  - what is carried?
  - what drives REM?
  - survives wakes?
  - made up later?
  - night vs day?
  - coupled animals?
  - outside conditions?
  - who wakes? (new: the link between individual history and who wakes in a shared event)
- Five competing accounts sit at the core:
  - internal regulation;
  - no carried history;
  - stage trade-off (the PI's first formulation);
  - sleep budget;
  - a neural scheduler (not testable here).

**Sources:**
- Statuses come from the three claim audits (schedule, v2, v1).
- Unaudited report numbers enter as `ledger`.
- Every citation is a file + line + anchor, checked by `check` (0 errors, 0 warnings).

## Reviews of round r1 (the user's routing)

**Fable** (read-only adjudication) changed:
- **two open conflicts, now resolved with their reasoning:**
  - `c.rem_length`: different quantities; where comparable, ≈ 0;
  - `c.delay_vs_minutes`: compatible; #12's null cannot detect what #6 implies.
- **one corrected premise:** v2's window terms sat on the clock baseline M0, not on the anchor history.
- **two statuses back to open:**
  - handling stress (its cause is untested);
  - the REM budget (budget wording is forbidden until it is separated from timing shifts).
- **the missing alternatives** added:
  - state persistence;
  - shared drift to lighter sleep;
  - post-wake fragility.
- **other changes:**
  - propagation wording moved off "fast coupling";
  - #28c kept a Candidate (refined, not superseded, by #29d);
  - a no-join basis node added;
  - the long-wake hazard test extended (both hazards, both clocks, first-hour REM), and its forbidden 'reset' outcome
    wording removed.

**astra** (Codex session "量化每日NREM与REM并绘制昼夜图", text only) raised four points:
- **Shares, not order.** The bands test shares, not order: new hypothesis `h.form.order`, open conflict
  `c.sequence_wording` against audit #2's wording.
- **"About one cycle" is underpowered.** It rests on an underpowered null (2nd REM +0.22, SE 0.15): new ledger
  result, open conflict `c.one_cycle`.
- **"Still" is defined after the event.** 'Still partner' is defined after the event, so #29d cannot settle
  contagion: `c.partner_waking` reopened, and contagion is open.
- **Role belongs in a secondary analysis.** In the within-event test, role is a post-event response (a mediator), so
  it moves to a secondary analysis. A history × event comparison with matched no-event moments was added, with a new
  hypothesis, `h.vul.general_arousal`.

Where a reviewer disputed an audit's wording, the audit status was kept and the dispute recorded as an open conflict
for the user.

## Verification

- `python research_logic/logic_map.py --selftest`: all 12 checks pass. Each injected error is caught:
  - dangling edge;
  - anchor not at the line;
  - line out of range;
  - hypothesis status vs judgment;
  - non-detection without a reading;
  - superseded without replacement;
  - mechanism supported by predictive evidence;
  - next step with one outcome;
  - round missing an answer;
  - relation between wrong types;
  - resolved conflict without a resolution.
- `python research_logic/logic_map.py check`: 0 errors, 0 warnings on the sleep graph.
- `build`: the page (≈ 270 KB, ASCII) and the JSON. One headless-Edge screenshot was checked:
  - overview, cards and an expanded branch render;
  - the typed edges and their labels draw;
  - the drawer shows sources with GitHub line links.

## Not done

- **Edge labels crowd** where many results converge in one branch (e.g. Q4); hovering isolates the links of one node.
- **GitHub links** resolve once the commits are pushed (nothing pushed, per the user).
- The new hypotheses and next steps are proposals; none was run.

## Update 2026-10-09: every figure linked (the user: "把每次做的图都link上")

- **Schema.** Nodes take `figs: [{p, cap}]`; `meta.figure_dir` and `meta.figure_watch` were added.
- **Builder.** `check` verifies the files and warns for every watched figure no node links. `derived.figures` records,
  for each figure, the branches that show it and the reports / change logs that cite it. `logic_map.py figs` prints
  the Artifact `files` map.
- **Page.** Figures appear in four places:
  - as thumbnails in the cards;
  - on each test in an open branch;
  - in the drawer;
  - in a Figures gallery.

  A click enlarges a figure (arrow keys page, Esc closes, a link goes to its node). Unlinked figures are listed as
  "not yet in the logic map".
- **Graph** (rounds r1–r6, the later rounds by another session): 35 figures linked on 26 nodes. 9 figures are still
  unlinked, because their reports have not been mapped in a round yet:
  - night sleep with WISER (7);
  - mic ↔ IMU sync and peaks (2).
- **Fix.** `show` / `index` crashed on the Windows console code page (cp1252) with non-ASCII titles; stdout is now
  UTF-8.
- **Docs.** The agent now links every figure a report shows. The skill republishes with the `files` map.
- **Verification.**
  - Selftest: 13 checks pass (new: a missing figure file is caught).
  - `check`: 0 errors, 9 warnings (the 9 unlinked figures).
  - Page script: `node --check` passes. One headless screenshot shows a figure in the drawer.
  - Published as version 4, after confirming that the newer version from another session carried the same data.

