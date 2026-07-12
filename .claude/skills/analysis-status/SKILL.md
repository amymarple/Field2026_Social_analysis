---
name: analysis-status
description: >-
  Compile the dense WISER analysis status tracker (wiser/ANALYSIS_STATUS.md) into a
  graph-first, human-readable scientific decision map — where the analysis stands, what is actually
  known, what was ruled out or corrected, what is still only a candidate, which blockers gate stronger
  claims, and the next three dependency-ordered actions — WITHOUT changing any conclusion. Run it
  explicitly with /analysis-status, optionally with a focus (next, routes, sleep, social, policy,
  publication) and/or an explicit tracker path. It reads only; it never promotes a candidate, unblocks a
  blocker, or edits repository files. Trigger phrases: "where does the analysis stand", "analysis status
  dashboard", "what do we actually know", "what was ruled out", "what is blocked", "what's next",
  "decision map", "simplify ANALYSIS_STATUS".
version: 0.1.0
---

# Analysis status dashboard

Reconstruct `wiser/ANALYSIS_STATUS.md` — which mixes pipeline status, measurement
validity, candidate findings, superseded interpretations, blockers, future modules, and publication
requirements — into a clear scientific **decision map**, without changing the underlying conclusions.

## Invocation

```text
/analysis-status                 # full dashboard, current global status
/analysis-status next            # focus: blocker chain + next executable analysis + what to defer
/analysis-status routes          # focus: route motifs / vocabulary-vs-manifold / georeference
/analysis-status sleep           # focus: rest-vs-sleep / multi-site / hierarchy / temperature
/analysis-status social          # focus: following / herd-vs-dyads / temporal-order limits
/analysis-status policy          # focus: locomotor state / initiation / termination / identifiability
/analysis-status publication     # focus: defensible claims / candidate-vs-publishable / replication
/analysis-status <path.md>       # use an explicit tracker path instead of auto-discovery
/analysis-status <focus> <path>  # combine a focus with an explicit path
```

The first bare word that matches one of `{next, routes, sleep, social, policy, publication}` is the
**focus**; any argument ending in `.md` is an **explicit tracker path**. Both are optional.

## Action

1. **Locate the canonical tracker.** Use the explicit `.md` path if given. Otherwise auto-discover
   `wiser/ANALYSIS_STATUS.md` from the repo root (fall back to a Glob for
   `**/ANALYSIS_STATUS.md`). If no tracker file exists at all, say so and stop — do not fabricate one.

2. **Delegate to the specialized subagent in an isolated context.** In Claude Code, use the Task tool
   with `subagent_type: analysis-status-simplifier`, passing the resolved tracker path and the focus (if
   any). The subagent is read-only (Read/Grep/Glob); it reads the tracker plus linked change logs and
   canonical reports **only** to preserve the current verdict, applies the source hierarchy (newest
   explicit correction/retraction/supersession > analysis change log > current status row > field
   observations as context only), keeps the three scientific layers (measurement state / analysis result
   / scientific interpretation) separate, and returns the finished dashboard.

3. **Return only the final human-readable dashboard** the subagent produces — no tool narration, no file
   edits. Ordinary invocation **never** writes to the repository.

## What the dashboard must contain (subagent enforces)

The eight fixed sections, in order: (1) current state in ≤~70 words; (2) one Mermaid `flowchart TD`
decision map organized by scientific dependency; (3) "What we actually know" table (≤8 rows,
question-grouped); (4) 3–6 corrections as old→why-it-failed→replacement; (5) blocker chain classified as
measurement / sample-design / implementation; (6) exactly three next moves (measurement unblock → next
executable science → validation/replication) each with what-not-to-do-yet; (7) scope-safe language
(Allowed now / Do not say yet); (8) provenance with read-vs-referenced flags.

## Graded evidence framing (do not flatten to "candidate everything")

The dashboard must **not** stamp every row `⚠️ candidate` — that hides which results are solid enough to
build on. Grade on two axes: a WISER-native **state/topology/statistical** result the tracker says
survived its nulls + jitter-floor + auditor is **measurement-supported**, while its
**biological/physical/causal** reading stays **candidate** with a named gate. Section 1 uses the canonical
shape: *"Several WISER-native state and topology results are measurement-supported; biological labels,
physical-space interpretation, weather causality, and sleep/microclimate mechanisms remain candidate
pending georeference, thermistors/ephys/interior CV, and replication."* The subagent **reflects** tiers
the tracker asserts; it does **not** set or upgrade them — that is the job of the
`scientific-report-promotion` skill and the `wiser-measurement-auditor` subagent. "Measurement-supported"
is never "publishable" and never licenses the causal/physical claim.

## Guardrails (do not weaken)

- No promotion to a **publishable biological/physical/causal** claim; `⛔ blocked` stays visibly blocked.
  (Graded framing above is a measurement-vs-interpretation distinction, not a status upgrade.)
- Keep separate: rest ≠ sleep; temporal order ≠ leadership/pursuit; recurrence ≠ route memory; shared
  corridors ≠ discrete route vocabulary; WISER bouts ≠ validated decision legs; inches ≠ physical
  wall/direction/road/cooling claims; field observations ≠ behavioral ground truth.
- Never recommend jumping to IRL, reward inference, a graph transformer, or broad hypothesis generation
  while georeference / representation / proxy gates are open (Module 14 likely NO-GO; graph transformer =
  late challenger for Module 13 only).
- Never edit `ANALYSIS_STATUS.md` or any analysis file during a normal `/analysis-status` run.
