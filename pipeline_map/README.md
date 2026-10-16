# pipeline_map — the preprocessing tree and its progress page

**What it is for:** tracking preprocessing progress. One graph holds every stage that turns raw recordings into the
inputs research uses. For each stage it records:
- where it sits in the tree;
- its status and owner;
- its outputs and how they were validated;
- what waits on the user, and its next step;
- the record its status comes from.

Research results (hypothesis tests) live in `research_logic/`, not here.

| file | role |
|---|---|
| `graphs/<id>.yaml` | **the only place the progress is written** (edited by the preprocessing-tracker agent) |
| `pipeline_map.py` | `check`, `build`, `show <stage or trunk>`, `index`, `figs`, `relocate` (re-find citations whose anchor moved, e.g. after CLAUDE.md edits), `--selftest` (10 checks) |
| `map_template.html` | page template (may contain Unicode; the build escapes it to ASCII) |
| `maps/<id>.html`, `maps/<id>.json` | generated, never hand-edited |

| graph | published page (private) |
|---|---|
| `graphs/preprocessing_2026c.yaml` (38 stages) | https://claude.ai/artifact/6YkHULY7zU691GaoJKG1rm |

**Update:**
- Say "更新预处理进度" or run `/preprocessing-status` (skill `.claude/skills/preprocessing-status/SKILL.md`).
- The main session asks the live sessions for their status.
- The `preprocessing-tracker` agent (Opus) updates the YAML.
- The page is republished with the figure files from `pipeline_map.py figs`.

```powershell
python pipeline_map\pipeline_map.py check
python pipeline_map\pipeline_map.py build
python pipeline_map\pipeline_map.py show behavior      # one trunk, by level
python pipeline_map\pipeline_map.py index --status waiting_user
python pipeline_map\pipeline_map.py --selftest
```

## Schema

**`meta.trunks`:** each trunk has an `id`, a `title`, a `note`, `lanes` (branches = columns) and `layers` (levels =
rows, raw at the top).

| trunk | lanes | layers |
|---|---|---|
| ephys | LFP branch · logger body signals · spike branch | e0 raw / QC / clocks → e1 signals → e2 states and sorted spikes → e3 events and curated units → e4 cross-block units, theta subtypes → e5 place cells → replay |
| behavior | cameras → detection · identity · WISER / IMU / mics | b0 clocks and camera geometry → b1 position and body sensors → b2 identity and tracking → b3 behaviour |

**Fields of a stage:**

| field | content |
|---|---|
| `id` | stable |
| `done_when` | what "done" covers and its acceptance gate; the status refers to that scope only (required; astra review 2026-10-10) |
| `trunk`, `lane` | `lane: all` spans the trunk |
| `layer`, `title`, `short`, `summary` | |
| `status` | below |
| `owner` | session names as reported |
| `outputs`, `validation`, `tools` | |
| `waiting_on_user`, `blocker`, `next`, `reason` | |
| `requires` | hard inputs |
| `aids` | helpers |
| `src` | `{f, l, a}`, verified at build: file exists, lines in range, anchor within ±3 lines; a path may point into a sibling repo `../Field_2026_Social_Recording/…` |
| `figs` | `{p, cap}` |
| `updated` | |
| `changes` | `{date, what}` |

Top level: `updates` (`{date, by, summary, nodes}`), one entry per round.

**Statuses and what each needs:**

| status | needs | page colour |
|---|---|---|
| done | `outputs` + `validation` | green fill |
| in_progress | `next` + `evidence` of current work (a job, a recent commit or plan amendment, a dated report) | amber |
| waiting_user | `waiting_on_user` | violet + "needs you" |
| blocked | `blocker` | red |
| planned | — | dashed |
| not_started | — | dotted |
| closed | `reason` | grey, struck through |

A `closed` stage is a route that was tried and dropped; it stays in the tree.

**Telling the statuses apart:**
- A plan with no current work is `planned`.
- Waiting for an audit, or for an offline owner with no recorded next step, is `blocked`.
- Work handed to a person who is doing it is `in_progress`.
- Implementation, validation and downstream research never share one status: a blocked interpretation on top of a
  finished product is its own stage.

**Checks:**
- unique ids;
- trunk / lane / layer exist;
- `requires` / `aids` endpoints exist;
- no `requires` cycle;
- each status has its fields;
- citations and figures verified.

A warning is raised when a done stage needs an input that has not started.

**Page:**
- **Progress per trunk.**
- **The "waiting on you" list.**
- **Who works on what.**
- **The tree.** Two trunks, levels × branches. Solid arrows mean "needs", dashed (toggle) "helps", pink links cross the
  trunks. Hovering traces a stage, and clicking opens its outputs, validation, owner, inputs, sources and history.
- **The update log and a filterable stage list.**
