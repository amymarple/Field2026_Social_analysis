---
name: scientific-report-promotion
description: >-
  This skill audits atomic scientific claims from a Field_2026_Social analysis and decides what evidence
  status and wording each claim is eligible for. Run it EXPLICITLY (it does not auto-fire) when a result
  is being prepared for human review, when a biological claim has materially changed, when the measured
  construct or state space changed, when the current scientific summary may be stale, or when the user
  asks whether a finding is ready to report. Its output is a compact atomic claim-audit (one row per
  minimal claim: measurement, scope, status, allowed/forbidden wording, required validation, ledger ref)
  that the `human-readable-scientific-summary` skill consumes — this skill does NOT write the final
  narrative. Trigger phrases: "is this ready to report", "promote this finding", "what's the evidence
  status", "established vs candidate", "did the claim change", "audit these claims", "allowed wording",
  "scope of this result", "superseded".
version: 0.2.0
---

# Scientific-report promotion — atomic claim audit

## Responsibility (and non-responsibility)

**This skill audits atomic scientific claims and decides the evidence status and the wording each is
eligible for.** It sets `status`, `scope`, `allowed_wording`, and the blocking inconsistencies. It does
**not** write the human-readable narrative, choose what to emphasize, or decide what to omit — that is the
`human-readable-scientific-summary` skill, which consumes this skill's output and may downgrade emphasis
but may **never** upgrade status or broaden scope.

## When to run

Run **explicitly** when: a result is being prepared for human review · a biological claim has materially
changed · the measured construct or state space changed · the current scientific summary may be stale ·
the user asks whether a finding is ready to report. It is **not** an automatic post-run hook. A lightweight
external hook may mark a summary file `STALE`, but nothing here rewrites or promotes claims automatically.

## Two artifacts this sits between

- **Technical ledger** — `change_log/<date>-*.md` + `outputs/.../*_report.md` + `ANALYSIS_STATUS.md`.
  Written freely; **keeps superseded work, clearly marked** (never deleted — provenance).
- **Scientific summary** — the human-readable `outputs/<direction>/SCIENTIFIC_SUMMARY.md`.
- **This skill produces the claim audit** that gates what may pass from ledger → summary.

## Step 1 — decompose into atomic claims

Before assigning any status, split the analysis into **minimal statements**, each evaluated on its own.
Claims from one analysis routinely land in **different** categories — do not force them into one. E.g.:

- *"The WISER variable measures locomotor emergence (site departure), not true wake"* — can be
  **Established** as a **measurement interpretation**.
- *"There is no clock-stereotyped ~10:00 relocation in the observed period"* — a **scoped descriptive
  negative**, status depends on its own sensitivity checks.
- *"Heat causes thermoregulatory doorway use"* — **Candidate** (association) or **Unresolved** (the causal
  form), never asserted causally.

## Step 2 — the six checks (they set status + wording)

Apply per claim; the full mechanics are in [`references/promotion_gate.md`](references/promotion_gate.md).

1. **Measurement validity** — state what the sensor/analysis directly measured; never rename it to the
   biological construct you want (WISER = movement above the ~7 in jitter floor, not in-nest arousal).
2. **Outcome/state-space validity** — the outcome must be able to represent every relevant state;
   rat-centering / normalization / a richer model cannot rescue a misspecified state space.
3. **Design validity** — imposed boundary ≠ discovered transition; tuned threshold ≠ pre-specified event;
   repeated measures on the same animals ≠ independent exposures; shared day-level covariate ≠ per-unit.
4. **Internal consistency** — exclusive fractions sum to ≈1; counts reconcile with matrices/denominators;
   conditional-on-use ≠ population composition; date-gated/invalid states carry explicit exclusions.
5. **Evidence status** — assign exactly one status (below). Synthetic self-tests verify **code behavior
   only** — never cite them as biological validation.
6. **Sensitivity & alternatives** — record dependence on smoothing/thresholds/ROI buffers/missingness/
   exclusions; individual heterogeneity vs shared exposure; time trend/habituation; and whether video or
   another sensor is needed to validate. A claim that flips under a reasonable alternative is **Candidate
   at best**; one that disappears is **not promotable**.

## Evidence-status taxonomy (exactly one per claim)

| Status | Meaning | ANALYSIS_STATUS |
|---|---|---|
| **Established** | Robust under the current measurement AND its required sensitivity checks, **within its stated scope**. | ✅ |
| **Candidate** | Suggestive; depends on ROI definition, small n, coarse covariates, uncorrected comparisons, or incomplete validation. | ⚠️ |
| **Rejected / superseded** | A previously-used interpretation or model no longer valid. | ⛔ / struck |
| **Unresolved** | Cannot be answered with the current sensor or analysis. | ◻️ |

Status is assigned **per atomic claim from its own evidence** — do not freeze a whole project into one
category. (A descriptive/measurement claim can be Established while a causal claim from the same run is
Unresolved.)

## Scope-limited promotion

A claim may be promoted **only within the validated scope of its measurement and state space, and its
wording must not imply coverage beyond that scope.** An incomplete state space blocks claims about the
*complete* behavioral distribution, but not a narrower claim whose scope is fully covered by the measured
states.

- Invalid: "Rats choose primarily between house_1 and house_2." (implies the full choice set)
- Valid within scope: "Among fixes classified within the two primary houses, house_1 held the larger share."

## Promotion status ≠ inclusion decision

Setting a claim to **Candidate does not erase it from the summary.** A Candidate result may still appear
if it is labeled Candidate, its uncertainty is scientifically important, it is written non-causally, and
it is separated from Established findings. This skill decides **status + allowed wording**; the summary
skill decides **selection + emphasis** within those bounds.

## Regeneration, not correction

When a substantive change alters the interpretation, the summary must be **regenerated** from the current
audited claims — never patched with an appended "Correction:" paragraph. The **ledger** keeps the history
(superseded rows stay, marked). Emitting a new audit that changes a claim's status is itself the signal to
regenerate.

## Output — the atomic claim audit

Emit a compact table (or one structured markdown block per claim), one row per atomic claim, with these
fields. Keep it concise; do not narrate every file inspected.

| Field | Meaning |
|---|---|
| `claim` | Minimal scientific statement being evaluated |
| `measurement` | What the sensor or analysis directly measured |
| `scope` | Population, dates, states, conditions the claim applies to |
| `status` | Established / Candidate / Rejected-Superseded / Unresolved |
| `main_evidence` | Strongest supporting result — include the **load-bearing statistic** (effect size + n + the null/threshold it is judged against) so the summary and its quantitative appendix can cite it |
| `main_limitation` | Single limitation most likely to change interpretation |
| `allowed_wording` | Strongest wording currently justified |
| `forbidden_wording` | Stronger interpretation that is **not** justified |
| `required_validation` | Evidence needed for promotion |
| `ledger_reference` | Report/table/figure/change-log location |

A worked audit is in
[`../human-readable-scientific-summary/references/worked_example.md`](../human-readable-scientific-summary/references/worked_example.md).

## Integration

`analysis → technical ledger → **scientific-report-promotion → atomic claim audit** →
human-readable-scientific-summary → scientific summary`

Upstream, `/analysis-definitions` fixes how each quantity is defined (formula + text). The
`/regime-aware-wiser-tracking` and `/regime-aware-cv-measurement` skills (and the `wiser-`/
`cv-measurement-auditor` subagents) supply the sensor-vs-animal evidence that Checks 1 and 6 depend on —
cite their `outputs/audit/` reports in `main_evidence`/`ledger_reference` when auditing a spatial or
occupancy claim.
