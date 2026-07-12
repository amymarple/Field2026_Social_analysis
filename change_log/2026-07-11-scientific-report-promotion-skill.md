# Change log — `scientific-report-promotion` skill (report-writing discipline, tooling)

**Date:** 2026-07-11
**Type:** tooling / workflow (new Claude skill; no analysis code, no data touched).
**Scope:** documentation-only. Adds a skill that governs how AI-generated analysis results are written up
for a human to proof-read and decide the next step. No source, config, DB, or output file changed.

## What / why
AI can produce a clean-reading report faster than a scientist can vet it, and the failure mode is a report
that silently promotes a debugging artifact, a mislabeled sensor variable, or a misspecified state space
into a scientific claim. This session's Direction-3 work is the live case: `sleep_end` (a debugging
artifact), `locomotor_emergence` mislabeled as "wake", and the binary `house_1/house_2` state-space
misspecification all had to be walked back **after** they were written into reports. The new skill puts a
**gate** between two artifacts so that walk-back happens in the ledger, not in front of the human.

## What was added
- **`.claude/skills/scientific-report-promotion/SKILL.md`** — the contract:
  - **Two artifacts, never collapsed.** (1) *Technical ledger* = this repo's `change_log/` +
    `outputs/.../*_report.md` + `ANALYSIS_STATUS.md` — written freely every run, **preserves superseded
    work** clearly marked. (2) *Human-readable scientific summary* = new
    `outputs/<direction>/SCIENTIFIC_SUMMARY.md`, organized by biological question + evidence strength,
    **current-state only**, readable in 5–10 min.
  - **Promotion gate** (six checks) a result must pass to enter the summary: measurement validity,
    outcome-space validity, design validity, internal consistency, evidence status, sensitivity/
    alternatives. Grounded in real in-repo examples (locomotor-emergence ≠ wake; binary→multi-site
    state space; imposed 10:00 window ≠ discovered change-point).
  - **Evidence-status taxonomy** Established / Candidate / Rejected-superseded / Unresolved, mapped to the
    existing `ANALYSIS_STATUS` ✅/⚠️/⛔/◻️ markers; synthetic self-tests = code verification, **never**
    biological validation.
  - **Rewrite rule:** on a substantive correction, **regenerate** the summary from the current validated
    state — do not append a correction paragraph (the ledger keeps history).
  - **Stop conditions** + a required **end-of-run report** (ledger updated? gate passed? summary rebuilt?
    what stays Candidate/Rejected/Unresolved? what blocks promotion?).
- **`references/scientific_summary_template.md`** — the fillable 10-section human-readable summary
  (biological picture → questions → data/limits → established → candidate → individual differences →
  rejected → unresolved → priority validation steps → appendix links).
- **`references/promotion_gate.md`** — the machine-checkable six-check gate + stop-condition list + the
  end-of-run report block.
- **`CLAUDE.md`** — added a sibling bullet to the `/analysis-definitions` rule pointing at the new skill
  and the two-artifact discipline.

## Relationship to existing skills
Complements, does not replace: `/analysis-definitions` defines *how each quantity is written* (formula +
text); this skill governs *which results reach the human and how*. `/regime-aware-wiser-tracking` and
`/regime-aware-cv-measurement` (plus the `wiser-`/`cv-measurement-auditor` subagents) supply the
sensor-vs-animal separation the gate's Check 1 and Check 6 rely on.

## Verification
- Skill loads: it is listed as an available skill (`/scientific-report-promotion`) after the write.
- No code path exercised (documentation-only); no analysis re-run; no DB/weather/output read or written.
- Provenance: this entry + index row (`change_log/README.md`); `implementation_plan/README.md` unchanged
  (no source change to plan).

## Not done (by design)
- Did **not** yet build the human-readable `SCIENTIFIC_SUMMARY.md` for any direction. The first
  application (Direction 3 biological-day sleep is the obvious candidate) is left for a follow-up so the
  user can approve the skill first.
