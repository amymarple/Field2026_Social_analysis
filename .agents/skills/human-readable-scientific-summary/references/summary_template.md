# Scientific summary — compact template

Copy into `wiser/outputs/<direction>/SCIENTIFIC_SUMMARY.md`. **Regenerate** it (do not
patch) whenever a substantive correction changes the interpretation. Target **700-1,200 words**, ~4-6 min,
**≤3 main findings**, **≤3 figures**. Every statement stays inside the `status`/`scope`/`allowed_wording`
from the claim audit. Resolve `shortid`→name via `configs/rat_identities.csv`. Units: WISER inches
(UNVERIFIED offset frame — no directional/physical claims), CV cm; never mixed silently.

Fill the five pre-writing decisions first (biological-picture sentence; three findings; top candidate; the
superseded claim to stop; the one unresolved issue that drives the next decision). If the one-sentence
picture won't come, the synthesis is not ready.

---

# <Direction / topic> — scientific summary

_Current-state, regenerated <date> from run `<run_id>`. Methods & history: see Technical references._

## Biological picture
<One paragraph, ~100-150 words. What was measured (name the sensor variable, not the wished-for
construct), the dominant biological pattern, and the single most important limitation. No methods,
formulas, filenames, thresholds, or revision history.>

## Main findings
<Max three. Each is a short paragraph, not a table. State the LOAD-BEARING NUMBER inline — effect size +
n + the comparison/null it is judged against. The full quantification is in the appendix.>
1. **<claim, in the audit's allowed wording>.** Evidence: <the single strongest result **with its number**,
   e.g. "ρ = −0.02, n = 11" or "≈46% of moves involve a non-house site; ≈3.1 relocations/rat-day">.
   Caveat: <the one limitation most likely to change interpretation>. [status tag if not Established]
2. …
3. …

## Candidate interpretation
<Only candidates that materially change the biology or the next experiment. Non-causal wording. Clearly
marked **[Candidate]**. State the number (e.g. "any-shelter dwell ρ = −0.44; doorway ρ = +0.58, n = 11
days") and name the dependency (small n / ambient-not-shelter proxy / uncorrected comparisons / ROI
buffer) in one clause.>

## What is no longer supported
<Short. Each line: the old claim → the one-line reason it no longer holds. No debugging narrative.>
- ~~<old claim>~~ — superseded by <what>, because <state-space / measurement / consistency reason>.

## Unresolved
<Max three, ranked by how much resolving each would change the conclusion.>
- <question> — blocked by <sensor limit / unverified frame / missing modality>.

## Next decision
<Max three actions, ordered by expected scientific value; usually field/hardware, not more code.>
1. <action> → would move <which candidate> toward Established.

## Technical references
- Full technical report (methods, all sections incl. superseded): `outputs/<direction>/<...>_report.md`
- Claim audit (status/scope/wording per claim): `<location>`
- Change log / status: `change_log/<date>-<topic>.md` · `wiser/ANALYSIS_STATUS.md`
- Regime/measurement audit (spatial/occupancy claims): `outputs/audit/<...>.md`

_Figures (≤3, each answers one biological question): `<F1 overall temporal/behavioral structure>`,
`<F2 dominant state/transition organization>`, `<F3 top candidate / individual-difference>`. Full
matrices, per-day tables, diagnostics, sensitivity plots live in the technical report, not here._

## Appendix — how each finding was quantified
_Read on demand; NOT counted in the reading budget. One block per main + candidate finding, following
`/analysis-definitions` (formula + plain text). Give what reproduces the inference, not every raw cell —
link full matrices/per-day tables in Technical references._

### A<k>. <finding name> — <one-line what-this-shows>
- **Quantity** ($<sym>$): <plain-text meaning>. Units: <…>. Range: <…>.
- **Formula:** $$ <sym> = <exact computation; declare every symbol> $$
- **Value:** <number(s)> (n = <…>; <IQR / 95% CI / SEM>), in <units>.
- **Decision rule / null:** <threshold | null/baseline model | effect-size band> ⇒ <criterion, e.g.
  `|ρ| < 0.2 ⇒ no association`; `z > 2`; `Σ_s dwell_s ≈ 1`>.
- **Sensitivity:** robust to <smoothing / ROI buffer / dropout filter> (<one-line result>).
- **Inference:** <measured value> vs <rule> ⇒ <the finding's claim, in allowed wording>.

_(Repeat A1, A2, … for every numeric claim. A conclusion with no appendix block is not reportable.)_
