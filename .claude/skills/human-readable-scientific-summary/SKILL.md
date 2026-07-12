---
name: human-readable-scientific-summary
description: >-
  This skill converts an audited set of scientific claims (the atomic claim-audit produced by
  scientific-report-promotion) into a concise, prioritized report that a scientist unfamiliar with the
  code can understand after one read. Run it EXPLICITLY when writing or regenerating a
  `outputs/<direction>/SCIENTIFIC_SUMMARY.md` for a human reader. It controls selection, hierarchy,
  brevity, narrative, and what is omitted from the main text — it consumes the claim audit and may
  downgrade emphasis but must NEVER upgrade evidence status or broaden claim scope. Default target
  700-1,200 words, ≤3 main findings, ≤3 figures. Trigger phrases: "write the scientific summary",
  "human-readable summary", "make this readable", "one-read report", "summary for a scientist", "condense
  the findings", "regenerate the summary", "biological picture".
version: 0.1.0
---

# Human-readable scientific summary

> A scientific summary is not a compressed technical ledger. Its job is to make the biological picture
> **memorable, correctly scoped, and decision-relevant.**

> Readability comes primarily from **selection and hierarchy**, not from adding headings or including
> every available result.

## Input contract (hard boundary)

This skill **consumes the atomic claim-audit** from `scientific-report-promotion` (status, scope,
allowed/forbidden wording per claim). It may **downgrade emphasis** (say less, or move a claim to the
appendix) but must **never upgrade `status` or broaden `scope`**. Every sentence must stay inside the
`allowed_wording` and `scope` the audit assigned. If a claim you want to feature has no audit row, stop
and run `/scientific-report-promotion` first.

## Pre-writing decisions (do these before drafting)

Write down, in one line each:

1. The **biological picture in one sentence**. *If you cannot state it in one sentence, the synthesis is
   not ready — stop.*
2. The **three findings** the reader should remember.
3. The **most important Candidate** interpretation.
4. The **previous claim most important to stop the reader repeating** (superseded).
5. The **single unresolved issue** that most affects the next decision.

## Length & reading budget

- Default **main narrative 700-1,200 words**, ~4-6 minutes, **no more than three primary findings**.
- Do **not** expand the narrative because more analyses exist. A longer narrative needs an explicit user
  request or genuine scientific necessity.
- The **quantitative appendix is separate and NOT counted in the reading budget** — it is read on demand.
  The 5-6 minute one-read test applies to the narrative; the appendix is drill-down depth.

## Numbers are load-bearing (put them where they carry weight)

A summary without numbers is not readable, it is vague. Distinguish two kinds of number:

- **Load-bearing numbers** — the effect size, its **n**, and the **comparison/null it is judged against** —
  ARE the evidence. State them **inline in the narrative** for every headline and candidate finding
  (e.g. "≈3.1 relocations/rat-day", "ρ = −0.02, n = 11", "≈46% of moves involve a non-house site"). A
  finding with no number in the narrative is not promotable to the reader.
- **Supporting numbers** — full tables, every cell of a matrix, all per-day values, the whole sensitivity
  grid — are **not** load-bearing individually; they go in the **quantitative appendix**, not the narrative.

Rule of thumb: state the single number that IS the claim; move the table it came from to the appendix.

## Default structure (compact — not ten fixed sections)

Use these; omit any that carry nothing. **`Individual differences` appears only if it is one of the three
main findings.** Template: [`references/summary_template.md`](references/summary_template.md).

- **Biological picture** — one paragraph, ~100-150 words: what was measured, the dominant biological
  pattern, the single most important limitation. Do **not** open with methods, formulas, filenames,
  thresholds, or revision history.
- **Three main findings** — max three. Each: (1) the claim, (2) the strongest evidence **including its
  load-bearing number** — effect size + n + the comparison/null it is judged against, (3) one limiting
  caveat. Not the full sensitivity history (that is the appendix).
- **Candidate interpretation** — clearly separated; only candidates that materially affect biological
  interpretation or the next experiment.
- **What is no longer supported** — short box; only superseded claims a reader might otherwise keep
  believing. Do not narrate the debugging.
- **What remains unresolved** — max three, ranked by how much resolving them changes the conclusion.
- **Next decision** — max three actions, ordered by expected scientific value.
- **Technical references** — links to ledger, methods, full tables, figures, thresholds. Do not copy them
  into the narrative.
- **Quantitative appendix — "how each finding was quantified"** (REQUIRED when the summary carries any
  numeric claim). One compact block per main + candidate finding, so a reader can see exactly how the
  conclusion was reached without opening the code. Each block, following `/analysis-definitions`
  (formula + plain text):
  - **Quantity** — symbol + one-line plain-text meaning, **units**, and **range**.
  - **Formula** — the exact computation in `$…$`/`$$…$$` LaTeX (ASCII-legible), every symbol declared.
  - **Value** — the computed number(s) with **n** and dispersion (CI / IQR / SEM), in the stated units.
  - **Decision rule / null** — the threshold, null/baseline model, or effect-size band, and the criterion
    that turns the value into the conclusion (e.g. `|ρ| < 0.2 ⇒ no association`; `z > 2`; `Σ dwell ≈ 1`).
  - **Sensitivity** — one line: what the value is robust to (smoothing, ROI buffer, dropout filter).
  - **Inference** — one line: measured value → decision rule → the finding's claim.
  The appendix MAY carry compact definition/value tables; it must NOT dump full raw matrices or every
  per-day row (link those in Technical references). It expands the claim audit's `main_evidence`; it never
  changes a status or scope.

## Information-selection rule

Include a detail in the **narrative** only if it changes at least one of: the meaning of the result, the
credibility of the result, or the next scientific decision. A **load-bearing number always qualifies** —
the effect size, its n, and the null it is judged against change credibility, so they belong in the
narrative. Everything else numeric (full tables, matrices, per-day rows, the whole sensitivity grid) goes
to the **quantitative appendix**; anything not needed even there goes to the technical reference. Never
include something merely because it is available or technically correct.

## Evidence hierarchy (emphasis order)

1. dominant biological pattern → 2. strongest supporting evidence → 3. main measurement limitation →
4. candidate interpretation → 5. secondary details. A numerically large **exploratory** correlation must
not out-shout a more reliable **descriptive** result.

## Distinctions to preserve (from the audit — never blur)

measured variable vs biological construct · dominant vs minority-but-interesting behavior · descriptive
association vs causal explanation · code verification vs biological validation · repeated individual
observations vs independent shared exposures · conditional-on-use vs population composition · **absence of
detected evidence vs evidence of absence**.

## Readability prohibitions

These apply to the **narrative**, not the quantitative appendix. Do not, **in the narrative**: organize by
code-execution order or as a chronology of corrections; reproduce long tables or paste the full transition
matrix; list every sensitivity analysis; repeat a conclusion across sections; open with data
processing/thresholds; use diary language ("I added", "self-test PASS", "the correction paid off"); put
repo paths or function names in the biological narrative; call a result validated because a synthetic test
passed; give every caveat equal weight; or add sections just to look comprehensive.

The **appendix** is where the formula, the full value with n/dispersion, the null, and the decision rule
belong — but even there, give only what is needed to reproduce the *inference* (definition → value → rule
→ claim), not every raw cell; link full matrices and per-day tables in Technical references.

## Figure discipline

Max three main figures; **each answers one biological question**. Prefer: (1) overall temporal/behavioral
structure, (2) the dominant state/transition organization, (3) the most important candidate or
individual-difference result. Full matrices, per-day tables, diagnostics, sensitivity plots → technical
reference.

## Final readability test (revise until all pass)

- [ ] The report can be summarized in one sentence.
- [ ] ≤3 main findings; the dominant result is obvious within the first 30 seconds.
- [ ] Candidate findings are visually separated from stronger findings.
- [ ] Every paragraph advances the biological interpretation; none is removable without changing meaning
      or the next decision.
- [ ] No method detail is present only because it was hard to implement.
- [ ] A scientist unfamiliar with the repo could explain the result after one read, **without** opening
      the ledger.
- [ ] The report does not imply greater state-space or sensor coverage than actually exists.
- [ ] Every headline and candidate finding carries its **load-bearing number** in the narrative (effect
      size + n + the comparison/null it is judged against).
- [ ] The **quantitative appendix** lets a reader reproduce how each conclusion was reached — for each
      finding: definition (formula + text with units/range), computed value with n/dispersion, the
      null/decision rule, and the one-line inference. No conclusion rests on a number absent from the
      appendix.

## Integration

`analysis → technical ledger → scientific-report-promotion → atomic claim audit → **this skill** →
scientific summary`. This skill owns selection / hierarchy / brevity / narrative / omission. It cannot
change what `scientific-report-promotion` decided about status or scope. Quantities still obey
`/analysis-definitions` (defined once, in the technical report; here use plain-text meaning only). A full
worked hand-off (audit → summary → critique) is in
[`references/worked_example.md`](references/worked_example.md).
