---
name: research-logic
description: >-
  Update the research logic map after a RESEARCH phase: dispatch the research-logic agent (Opus) to add the phase's
  results to the logic graph (questions → competing hypotheses → tests → results → judgments → next steps), route any
  conflict it finds to a Fable reviewer, optionally ask the Codex "astra" session for a text-only logic review, rebuild
  the interactive map and republish it. Trigger phrases: "更新研究逻辑：Phase X，报告路径……，审查路径……",
  "/research-logic", "update the research logic map", "研究逻辑图". Only for real research steps; never for
  preprocessing (scoring, LFP / EMG / IMU extraction, sorting, sync, QC, storage).
version: 0.1.0
---

# Research logic update

## Invocation

```text
更新研究逻辑：Phase 7，报告路径 results/2026c/ephys_spikes/reports/<report>.md，审查路径 <claim audit or review>.md
/research-logic Phase 7 <report.md> [<review.md> ...] [graph=research_logic/graphs/sleep_2026c.yaml] [astra]
/research-logic check            # validate + rebuild only (no new round)
```

Default graph: `research_logic/graphs/sleep_2026c.yaml`. Its published map is
https://claude.ai/artifact/F5rCafmi6VuoXspRbEuczS (republish to that URL; see `research_logic/README.md`).

## Gate

If the step is preprocessing, say so in one line and stop. If the phase has no claim audit yet, offer to run
`/scientific-report-promotion` first; without it, the new results enter as `ledger` (reported, not audited).

## Steps (the main session orchestrates; subagents cannot spawn subagents)

1. **Dispatch** `subagent_type: research-logic` (its definition pins Opus) with: the graph path, the phase label, the
   report path(s), the review / claim-audit path(s). It edits the YAML, runs `logic_map.py check` and `build`, and
   returns the five answers, the changed ids and `需要裁决的冲突`.
2. **Conflicts → Fable.** If it lists conflicts, launch one read-only `general-purpose` agent with `model: "fable"`:
   give it the conflict ids, the YAML path and the sources, and ask for a verdict per conflict (genuine / different
   quantities / resolved), what may be said, and the discriminating analysis, with file:line citations; plus a check of
   the round's statuses against the audits. Send its findings back to the research-logic agent (SendMessage, same
   agent) to record them: resolved conflicts with `resolved_by: "Fable review rN (...)"`, and the review in the round's
   `reviews`. If Fable fails, use astra (step 3) for the same questions.
3. **Optional logic review by astra** (when the user asks, for a large round, or as the Fable fallback). The Codex
   session "量化每日NREM与REM并绘制昼夜图", thread `01a112d6-96ff-7643-8bd2-2d470daa44da`; the CLI is
   `%LOCALAPPDATA%\OpenAI\Codex\bin\<hash>\codex.exe` (not on PATH):
   `codex queue --thread <thread> --message <text> -s read-only`. The user's limits for astra: **text review only**,
   and PNG / SVG generation if ever needed; **never code, never files, never web pages** (no tokens for it). Its reply
   lands in `~/.codex/sessions/**/rollout-*<thread>*.jsonl` (last assistant messages). Fold its points in as for Fable;
   where it disagrees with an audit's wording, the agent opens a conflict instead of changing the audit.
4. **Rebuild and republish, with the figures** (the user, 2026-10-09: every figure is linked so it is easy to see):
   - `python research_logic/logic_map.py build`;
   - `python research_logic/logic_map.py figs` prints the `files` map `{figs/<name>: repo path}` of every linked and
     watched figure;
   - publish `research_logic/maps/<id>.html` with the Artifact tool and that map as `files`, to the URL above (`url`
     when this conversation did not publish it).
   - If the publish is refused because a newer version exists (another session's round), check that its embedded
     data is contained in yours. The page is rebuilt from the shared YAML, so a fresh build normally contains it. Then
     publish again.
5. **Report to the user in short Chinese:** the five answers, the conflicts and how they were settled, the top next
   step with its outcome-dependent consequences, and the link.

## Guardrails

- Statuses come from the claim audits; the graph never upgrades a conclusion or widens a scope.
- Not detected ≠ no effect; prediction ≠ mechanism; time order ≠ causation; Phase numbers are source labels only.
- New hypotheses are marked `proposed`; superseded nodes keep their history; nothing is deleted.
- No statistics are run by this skill; a "next step" is a proposal for the user.
