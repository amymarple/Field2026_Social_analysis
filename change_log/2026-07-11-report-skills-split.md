# Change log — split report skills into claim-audit + narrative (two skills)

**Date:** 2026-07-11
**Type:** tooling / workflow (revise one Claude skill, add one; no analysis code, no data, no existing
technical-ledger entry touched).
**Supersedes the design of:** `change_log/2026-07-11-scientific-report-promotion-skill.md` (kept intact
for provenance — that entry describes the original single skill; this entry records the split).

## Why
The first `scientific-report-promotion` skill mixed three responsibilities — claim auditing, end-of-run
workflow orchestration, and human-readable narrative generation. That risked (a) the skill reading like an
automatic post-run hook, and (b) final reports staying long and checklist-driven even when scientifically
correct. Split into two narrow, explicitly-invoked skills with a clean hand-off.

## What changed

### `scientific-report-promotion` (revised, v0.1.0 → v0.2.0) — now ONLY audits atomic claims
- **Sole responsibility:** decompose an analysis into minimal claims and decide each claim's evidence
  **status, scope, and allowed/forbidden wording**. It no longer writes the final narrative.
- **Removed auto-hook language** ("It auto-fires", "at the end of every analysis run", "always output
  this"). Now runs **explicitly** (preparing for review · claim materially changed · construct/state space
  changed · summary may be stale · user asks if a finding is ready). Note that an external hook may mark a
  summary `STALE` but must not rewrite/promote.
- **Replaced the end-of-run report with a compact atomic claim-audit table** (10 fields: `claim`,
  `measurement`, `scope`, `status`, `main_evidence`, `main_limitation`, `allowed_wording`,
  `forbidden_wording`, `required_validation`, `ledger_reference`).
- **Audit atomic claims, not whole projects.** Removed the global "Nothing in this pilot is currently
  Established" freeze; require decomposition; different claims from one run get different statuses (e.g.
  a measurement interpretation can be Established while a causal claim is Unresolved).
- **Added scope-limited promotion:** a claim may be promoted only within its validated measurement/state
  scope, and wording must not imply broader coverage. An incomplete state space blocks whole-distribution
  wording, not a within-scope narrower claim (rescope rather than reject).
- **Separated status from inclusion:** Candidate ≠ erased from the summary. This skill sets status +
  wording; the summary skill decides selection/emphasis within those bounds.
- **Shortened** (consolidated why/checks/stop-conditions/rewrite/relationship). `references/promotion_gate.md`
  rewritten as the claim-audit gate (six checks + scope rule + stop conditions + output schema + one filled
  example row). The old `references/scientific_summary_template.md` was **moved** to the new skill.

### `human-readable-scientific-summary` (new, v0.1.0) — turns an audit into a concise report
- **Sole responsibility:** convert the atomic claim-audit into a report a scientist unfamiliar with the
  code understands after **one read**. Consumes the audit; **may downgrade emphasis, never upgrade status
  or broaden scope.**
- Core principle (summary ≠ compressed ledger; readability = selection + hierarchy), five required
  pre-writing decisions (incl. the one-sentence biological picture gate), **length budget 700–1,200 words /
  ≤3 findings / ≤3 figures**, a compact default structure (biological picture · three findings · candidate ·
  what's no longer supported · unresolved · next decision · technical references — `individual differences`
  only if it is a top-3 finding), information-selection rule, evidence hierarchy, the audit distinctions to
  preserve, readability prohibitions, figure discipline, and a final readability test.
- References: `references/summary_template.md` (compact fillable structure) and `references/worked_example.md`
  (a full hand-off: example atomic claim audit → ~900-word summary → self-critique of what was omitted).

### Integration contract (documented in both skills + CLAUDE.md)
`analysis → technical ledger → scientific-report-promotion → atomic claim audit →
human-readable-scientific-summary → scientific summary`. Promotion controls status/scope/wording/blocking
inconsistencies; summary controls selection/hierarchy/brevity/narrative/omission.

## Preserved (unchanged in spirit)
Two-artifact discipline · measurement validity · outcome/state-space validity · design validity · internal
numerical consistency · explicit evidence-status taxonomy · sensitivity & alternatives · synthetic tests =
code verification not biological validation · regenerate-don't-append on substantive change · superseded
work stays in the ledger.

## Verification
- Both skills load and are listed (`/scientific-report-promotion`, `/human-readable-scientific-summary`).
- Documentation-only: no analysis re-run; no DB/weather/output read or written; **no existing change_log or
  report edited** (the prior skill change_log entry is left intact for provenance; CLAUDE.md pointer updated).
- Worked example is self-consistent with `change_log/2026-07-10-biological-day-sleep.md` numbers and is
  labeled illustrative (not the live summary).

## Not done (by design)
No real `SCIENTIFIC_SUMMARY.md` generated for any direction yet — first application (Direction 3) left for
a follow-up so the user approves the split first.

## Addendum 2026-07-11 — quantitative depth (numbers inline + a "how it was quantified" appendix)
**Why:** user feedback — the summary skill was over-suppressing numbers; a scientist needs the load-bearing
values inline AND a way to see how each conclusion was reached (definition → value → null → inference).
Only the `human-readable-scientific-summary` skill + its references changed; the promotion skill was touched
by one line only.

**`human-readable-scientific-summary/SKILL.md`:**
- New principle **"Numbers are load-bearing"** — separates load-bearing numbers (effect size + n + the
  comparison/null; **stated inline in the narrative** for every headline/candidate finding) from supporting
  numbers (full tables/matrices/per-day rows → appendix). A finding with no number in the narrative is not
  reportable.
- Length budget clarified: the **700–1,200-word one-read test applies to the narrative**; the **quantitative
  appendix is separate and NOT counted** (read on demand).
- New **required section "Appendix — how each finding was quantified"**: one block per main/candidate finding
  following `/analysis-definitions` — quantity (symbol, units, range), **formula** (LaTeX), value (with n +
  dispersion), decision rule/null, sensitivity, and a one-line inference.
- Information-selection rule and readability prohibitions **scoped to the narrative** (the appendix is where
  formula/value/null belong); two new final-readability checks (load-bearing number present; appendix
  reproduces each inference).

**References:** `summary_template.md` gains the appendix template + a "state the number inline" cue in
main-findings/candidate; `worked_example.md` rewritten so the narrative carries the numbers (≈3.1 moves/day,
≈46% non-house, E≈20.8 h ρ=−0.02 n=11, τ median 13.5 h 11% near 10:00, any-shelter ρ=−0.44 doorway +0.58
n=55) and gains a full **Appendix A1–A5** (formula + value + null + inference per finding); critique updated
(narrative ≈620 words + on-demand appendix; what stays out entirely vs what the appendix carries).

**Promotion skill (one line):** the `main_evidence` audit field now explicitly must carry the load-bearing
statistic (effect size + n + null/threshold) so the summary appendix can expand it.

**Preserved:** the whole claim-governance foundation and the narrative's one-read discipline are unchanged;
this only restores quantitative depth (inline + appendix) without letting the narrative bloat.
