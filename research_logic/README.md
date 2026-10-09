# research_logic — the logic graph of a research direction, and its interactive map

**What it is for:** keeping the reasoning of an analysis direction in one place:
- why each analysis was done;
- what its result changed;
- which explanations still compete;
- which next step would separate them.

It is an index layer, like `analyses/` and `summaries/`, and it adds no science of its own. Statuses come from the
claim audits.

## Files

| file | role |
|---|---|
| `graphs/<id>.yaml` | **the only place the logic is written** (edited by the research-logic agent) |
| `logic_map.py` | `check` (validate), `build` (write the map), `show <id or branch>`, `index`, `--selftest` |
| `map_template.html` | page template (ASCII only; data embedded at build) |
| `maps/<id>.html`, `maps/<id>.json` | generated, never hand-edited: the interactive map and the normalised graph (nodes, typed edges with stable ids, rounds, conflicts, derived summaries) |

| graph | scope | published map (private) |
|---|---|---|
| `graphs/sleep_2026c.yaml` | cohort 2026c sleep analysis: v1, v2, Phases 0–6, mic pilot, daily quantification | https://claude.ai/artifact/F5rCafmi6VuoXspRbEuczS |

## How to use it

- **After a research phase:** "更新研究逻辑：Phase X，报告路径……，审查路径……" or `/research-logic …`. The skill is
  `.claude/skills/research-logic/SKILL.md`; the agent is `.claude/agents/research-logic.md`, pinned to Opus.
- **Model routing (the user, 2026-10-08):**
  - conflicts the agent finds go to a read-only Fable reviewer;
  - the Codex session "astra" may review the logic flow, as text only (and PNG / SVG if ever needed), never code or
    web pages.
- **Not for preprocessing:** scoring, feature extraction, sorting, sync, QC and storage are not research steps.
- **Local view:** open `maps/<id>.html` in a browser. It works offline except for the web fonts.

```powershell
python research_logic\logic_map.py check            # 0 errors required
python research_logic\logic_map.py build            # -> maps\sleep_2026c.html + .json
python research_logic\logic_map.py show q.carryover # one branch, compact
python research_logic\logic_map.py index --type result --status candidate
python research_logic\logic_map.py figs             # Artifact `files` map for the figures
python research_logic\logic_map.py --selftest       # 13 checks on a synthetic graph
```

## Schema

**Node types:**

| type | meaning |
|---|---|
| `question` | research question (one `core`, plus the branch questions in `meta.branches`) |
| `hypothesis` | competing explanation (`level` = pattern or mechanism; `short` = its pill label) |
| `prediction` | testable prediction of a hypothesis (`of`) |
| `analysis` | a test that was run |
| `result` | one audited claim (or a `ledger` result) |
| `judgment` | the current verdict of a branch (one `current` per branch) |
| `next_step` | proposed discriminating step |
| `basis` | measurement or data condition that results depend on; not a research step |

**Fields:**
- Every node: `id` (stable, `^[a-z][a-z0-9_.-]*$`), `type`, `title`, `round_added`, `src`, and `changes`
  (`{round, what}`) when modified.
- Optional on any node: `text`, `scope`, `ph` (phase tags = source labels only), `note`.
- **Sources** are `{f: alias or path, l: line or [first, last], a: anchor}`. `check` verifies that the file exists, that
  the lines are in range, and that the anchor appears within ±3 lines of them.

**Statuses:**

| type | statuses |
|---|---|
| result | established · candidate · unresolved · rejected · withdrawn · superseded (needs `superseded_by` + `previous_status`) · ledger (reported, no audit status) |
| hypothesis | supported · weakened · rejected · mixed · open · proposed · untestable |
| prediction | held · failed · mixed · open |
| judgment | current · superseded |
| next_step | proposed · planned · in_progress · done · dropped |

**Relations** (directed, typed). They are written as shorthand on the nodes (`from`, `tests`, `depends`, `basis`, `of`,
`superseded_by`, `links: [{rel, to, vs, scope, note, strength}]`) and expanded into explicit edges:

| relation | from → to |
|---|---|
| `proposes` | question / result / judgment / hypothesis → question / hypothesis / prediction / next_step (auto: core → branches, branch → its hypotheses, judgment → its next steps) |
| `tests` | analysis / next_step → hypothesis / prediction |
| `yields` | analysis → result |
| `supports` · `weakens` · `cannot_distinguish` | result / judgment → hypothesis / prediction (`vs` names the rival; judgment verdicts carry `strength`) |
| `depends_on` | result / judgment / analysis / next_step → basis / result / analysis / next_step |
| `revises` · `supersedes` | same type on both ends |

**Results also carry:**
- `effect`: positive · not_detected · mixed · descriptive;
- `inference`: predictive · association · descriptive · intervention;
- `null_reading`, required when `not_detected`: a precise null within scope, or underpowered;
- `allowed` / `forbidden`: the audit's wording, copied verbatim.

**Figures** (the user, 2026-10-09: link every figure so it is easy to see). Any node may carry
`figs: [{p, cap}]`:
- `p` is a file name in `meta.figure_dir` or a repo path; `cap` says what the figure shows;
- `check` verifies that the file exists and that published names are unique.

On the page, a figure appears:
- in the card of every branch that shows it;
- on its test in the open branch;
- in the drawer of the node and of its test / results;
- in the Figures gallery.

Click a figure to enlarge it and page through with the arrow keys.

Every figure matching `meta.figure_watch` that no node links yet is warned about by `check` and listed in the gallery
as "not yet in the logic map". `logic_map.py figs` prints the Artifact `files` map; locally the page falls back to the
repo path.

**Next steps** carry `priority` (1 = first), `stage` (now · measurement · next_stage_lfp · needs_video), `tests`, `cost`,
and ≥ 2 `outcomes` `{if, then, changes: [judgment ids]}`.

**Rounds** carry:
- `inputs`;
- the five answers: `aim`, `answered`, `supported_weakened`, `indistinguishable`, `next`;
- `next_steps`;
- `reviews` (`{by, summary}`).

**Conflicts** carry ≥ 2 `sides` (`{node, says}`), a `status` (open or resolved) and, when resolved, `resolution` and
`resolved_by`.

## Rules `check` enforces

- Every edge endpoint exists, and each relation joins allowed node types.
- Every citation resolves (file, lines, anchor).
- One current judgment per branch.
- **Hypothesis status = the verdict edges of the current judgments:**
  - supports only → supported;
  - weakens only → weakened or rejected;
  - supports plus weakens or cannot-distinguish → mixed;
  - cannot-distinguish only → open or untestable;
  - none → open, proposed or untestable.

  Prediction status is derived the same way, from the current results.
- A mechanism-level hypothesis cannot be supported without an intervention-design result.
- A non-detection states its reading.
- A superseded node names its replacement, of the same type, and keeps its previous status.
- Every next step names what it would separate, and ≥ 2 outcomes with the judgments they change.
- Every round answers the five questions and names its next steps.
- A resolved conflict says how and by whom.

## Conventions the agent follows

These are not machine-checkable; see the agent definition.
- Phases are source tags, never the backbone, and time order is never drawn as cause.
- New hypotheses are `proposed`.
- Nothing is deleted.
- Audit wording is kept verbatim. When a reviewer disputes it, the dispute becomes an open conflict.
