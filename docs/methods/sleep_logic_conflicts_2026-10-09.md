# Adjudication of the three r2–r6 conflicts in `research_logic/graphs/sleep_2026c.yaml`, and the round-status check (read-only, 2026-10-09)

Repo `D:\Documents\GitHub\Field2026_Social_analysis` at 307e7ba. Line numbers refer to the working-tree files. Abbreviations: `graph` = `research_logic/graphs/sleep_2026c.yaml`; `audit` = `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md`; `plan` = `implementation_plan/2026-10-08-sleep-behaviour-explore.md`; `xA/xC/xD1/xD2E/xE` = the Step A / C / D1 / D2E / E reports in `results/2026c/ephys_spikes/reports/`; `CSV` = `…/ephys_spikes_sleep_explore_E_budget_2026c.csv`; `logic_audit` = `docs/methods/sleep_logic_audit_2026-10-08.md`.

## Summary

| conflict | verdict | one line |
|---|---|---|
| `c.balance_wording` | **genuine conflict, inside the audit** (a stale row, not a graph error) | #21's allowed wording still says "balancing over the day"; #13 is withdrawn as a balance, #30 forbids it, the synthesis lists it under "Not shown", the plan forbids it. Strike "balancing over the day"; corrected wording below. #21 stays Unresolved. |
| `c.night_gain_size` | **different quantities** | "about half" = model-free REM bouts per NREM hour, night/day, in episodes after equally long (2–7-min) wakes (A3: 0.41 / 0.52). "about a third" = the per-10-s-step entry hazard at the *same count and prior wake* (C1: OR 0.36 / 0.30; clock ratio 0.37 / 0.34). They should differ in this direction. #14b's status rests on C1, so the single wording is the count-matched one: "about a third / three times less readily"; the claim text's "to about half" should be re-scoped to "REM bouts per NREM hour". |
| `c.night_day_rem` | **resolved: day fixed effects govern; the linear-day residual is a ledger item, not a failure of #40** | The plan's "(vi) after a day term" is ambiguous in its own sentence, but plan §3 / §6 (phase × day or day FE; never a common linear day term across dawn) and the E driver's pre-results definition (day FE) fix it. With day FE both scorings pass. With a linear day term a negative REM slope remains on FINAL (−1.16; outside the simulated range by point estimate, CIs overlapping) and marginally on pass2med (−0.49, inside). The CSV shows it is carried by the between-day (shared-day) component, which the simulation lacks by construction; FINAL is not the scoring for cross-session contrasts. #40 may claim the night → day pattern only *with day fixed effects*; the linear-day REM residual is unexplained (shared-day covariate, the un-modelled morning-round REM repayment, or scoring) and must not be read as a within-animal REM balance nor as refuting one. |
| rounds r2–r6 vs audit | **statuses match the audit rows; six wording / scope mismatches** | listed in §4; the largest is `j.core.r6` putting "read through a *smooth* daily curve" (#35 Candidate) inside its Established sentence. The audit's own synthesis block "Candidate (strong)" is stale for #6a and #14b — the graph is right to follow the rows. |
| `r.d2_nrem` | **over-reads by one step; weakens only the NREM clause of #10 as evidence of regulation; strengthens #43's REM-specificity** | The simulation copies the observed long wakes, so an NREM make-up that works through how much the rats slept is copied, not generated. Correct reading: no NREM homeostat is needed *in the transition rules*; a homeostat acting through the amount of waking is conditioned away, not tested. |

---

## 1. `c.balance_wording` — does #21's "balancing over the day" still stand?

**Verdict: genuine conflict, located inside the claim audit; the graph only mirrors it.**

Evidence:
- #21's allowed wording, unchanged: "The data show history-dependent, interruption-sensitive rules and balancing over the day, consistent with an internal regulation of sleep, not a fixed timetable." — audit:59; copied into the graph at `r.s21` graph:173–175 and graph:180.
- #13 "Withdrawn as a balance (2026-10-08) → see #30" — audit:50; #30 forbidden wording: "A night–day balance or budget (#13)" — audit:126; the synthesis: "**Not shown.** A day-to-day 24-h balance (#13 withdrawn)" — audit:183–184.
- The audit's own list of what changed on 2026-10-08 (audit:114–120) does not mention #21 — the row was simply not revisited.
- Plan §6 "Do not: report #13 as a balance or a one-way budget" — plan:298; logic_audit:462 "Do not report #13 as 'sleep is balanced over 24 h'".
- Nothing established now carries "balance": #9 is an established *negative* within continuous sleep (audit:46); #10 / #43 are a REM-specific repayment after morning rounds, Candidate, seen only after handled interruptions (audit:47, 157); #40 shows the daily totals arise *without* a budget (audit:154); within-rat day-FE slopes ≈ 0 (logic_audit:22–28).

Note the same staleness one row up: #13 is withdrawn, yet its `allowed_wording` cell still reads "…sleep is balanced over the 24 h" (audit:50), and the graph copies it (`r.s13` graph:2424). For a withdrawn claim the allowed wording is void and should be marked historical.

**What may be said (corrected #21 wording, status stays Unresolved):**

> "The data show history-dependent, interruption-sensitive rules — and daily REM and NREM totals that those rules reproduce without a daily budget — consistent with an internal regulation of REM entry rather than a fixed timetable. A repayment of REM has been seen only after handled interruptions (candidate); no day-to-day balance was shown."

If a shorter form is wanted: "…history-dependent, interruption-sensitive rules, consistent with an internal regulation of sleep, not a fixed timetable; no day-to-day balance was shown." Forbidden stays "mechanistic 'scheduler' wording"; add "balancing / balanced over the day (#13 withdrawn)".

**Discriminating analysis:** none needed — this is a wording repair. For the graph: add a `changes` entry to `r.s21` (r2 or r6) and strike / mark historical the `allowed` of `r.s13`; `j.core.r6` already avoids the word (graph:295–304).

---

## 2. `c.night_gain_size` — "about half" vs "about a third"

**Verdict: different quantities, both correctly reported; not a contradiction. One wording should carry #14b.**

Which number belongs to which quantity:

| wording | quantity | where |
|---|---|---|
| "to about half" (claim text, audit:52; synthesis audit:169) | **Model-free, episode-level:** REM bouts per NREM hour, night / day, within Watson SLEEP episodes whose *preceding wake* falls in the same 2–7-min bin (post-round 3 h excluded): 0.41 (FINAL: 4.92 vs 11.95 per NREM h) / 0.52 (pass2med); GLM rate ratio 0.42 [0.34, 0.53] / 0.51 [0.41, 0.64]; 6/6 rats < 1 | xA:313, 315 (verdict A3); xA:256 (rule); the logic audit's original 5.0 vs 11.7 = 0.43, audit:52; the plan's pre-written expectation "a gain that is ~0.45× at night", logic_audit:392 |
| "about three times less readily" (allowed wording, audit:52) / "to about a third" (synthesis audit:173–174) | **Model, step-level, matched on the count:** per-10-s NREM step, REM-vs-stay, dark coefficient at the same count P and ln(1 + prior wake): −1.03 → OR 0.36 (FINAL) / −1.20 → OR 0.30 (pass2med), 6/6 rats ≤ ln 0.6 (C1 (a)); the standardised night / day ratio of p(REM per step) under the 2-harmonic clock at each step's own P and d: 0.37 [0.30, 0.47] / 0.34 [0.27, 0.42] (C1 (b)); within steps after a 2–7-min wake 0.31 / 0.23 | xC:217–218, 222–223 (verdict C1); xC:63–65 ((b) definition, with A3's numbers quoted for reference); xC:126–131 (ratio table) |

Why they differ, and in this direction: A3 matches the prior wake only, not the count. At night the per-step hazard is lower at every count, so the count runs higher before REM arrives, and the hazard rises with the count (#3, audit:39); the realised bouts per NREM hour therefore fall *less* than the matched-count hazard (≈ ½ vs ≈ ⅓). A per-episode rate ratio of ~0.45 and a per-step hazard ratio of ~0.35 are two readings of the same gain.

**Which single wording #14b should use:** the count-matched one. The Established status was granted on C1 PASS ("Step C1 PASS on both scorings; Step A3 PARTIAL as model-free support", audit:52; the plan's A3 rule could not be met in the 7–30-min bin, xA:314, 316), and the allowed wording already states the condition "at the same accumulated NREM and after equally long wakes". So:

- keep the allowed wording: "At the same accumulated NREM and after equally long wakes, the rats entered REM about three times less readily at night";
- repair the claim text (audit:52) so the number carries its quantity: "Independently of the preceding wake, the night lowers REM entry — to about a third of the day's per-step rate at the same accumulated NREM, about half the REM bouts per NREM hour after equally short wakes — and delays the first REM";
- the synthesis line "Even after equally short wakes the night halves the REM-entry rate" (audit:169, still in the *Candidate (strong)* block) should move to Established and either say "about a third at the same count" or keep "halves" with "REM bouts per NREM hour" attached. The graph's `r.s14b` scope note (graph:3354) and `j.daynight.r5` (graph:3471–3472) can then drop the conflict tag.

**Discriminating analysis:** none; the two numbers are not competing estimates of one quantity.

---

## 3. `c.night_day_rem` — which day term, and is the FINAL linear-day REM slope a failure of #40?

**Verdict: resolved. Day fixed effects are the governing (pre-registered) specification; with it #40's (vi) passes on both scorings. The linear-day REM slope on FINAL is a sensitivity result — a between-day (shared-day) covariance that the conditional simulation cannot contain — not a failure of #40 as worded, and not evidence for or against a within-animal REM balance.**

### 3a. Which day term the plan's (vi) means

- The sentence itself is ambiguous: "(vi) a night → day deviation correlation ≈ 0 after a day term (the model has no budget)" — plan:250 (and its source, logic_audit:387–388, "after a day term (…the data agree)", written when the day-FE check had just given ≈ 0, logic_audit:24–28).
- The plan's methods fix it: "Every expected-amount baseline that compares windows on either side of dawn or dusk includes phase × experiment day (or day fixed effects). Reason: the opposite night / day trends of the drift (#30) contaminate a common linear day term" — plan:108–110; "Do not: use a common linear day term across dawn or dusk" — plan:305. A night → next-day contrast straddles dawn by construction.
- The E driver's definition, written before the results: "(vi) the night -> next-day deviation slope with day fixed effects (`sleep_explore_d.budget_from_records`) ~ 0" — xE:91; the E Reading: "(vi) … with day fixed effects … REM within the simulated range. PASS" — xE:35–36. The E run (07:43) preceded D1's warning (08:02, xD1:16 "The day term matters for Step E (vi) … apply the same term to the observed and the simulated records") and D2E (08:05), which then reported both terms on both record sets (xD2E:837–1000; CSV).

So: day FE is the pre-registered measure; the linear-day variant is a sensitivity added on D1's advice before its (vi) results were seen. The graph's `r.e_vi_linear` says exactly this (graph:2770, 2773) and is right.

### 3b. What the numbers say (CSV, quantity REM, stat `slope`; xD2E:963–1000)

| model | scoring | observed [CI] | simulated mean [2.5 %, 97.5 %] | observed inside? |
|---|---|---|---|---|
| within animal (no day term) | FINAL | −1.17 [−1.80, −0.53] | +0.07 [−0.92, +1.24] | no (point) |
| within animal + linear day | FINAL | −1.16 [−1.74, −0.58] | +0.09 [−0.91, +1.25] | no (point); CIs overlap −0.91…−0.58 |
| within animal + day FE | FINAL | −0.36 [−1.82, +1.09] | −0.04 [−1.36, +1.15] | yes |
| within animal | pass2med | −0.56 [−1.26, +0.13] | −0.15 [−1.15, +0.94] | yes |
| within animal + linear day | pass2med | −0.49 [−0.96, −0.02] | −0.13 [−1.14, +0.97] | yes |
| within animal + day FE | pass2med | −0.03 [−0.96, +0.89] | −0.25 [−1.38, +0.85] | yes |

Three facts follow:
1. **The linear day term changes nothing** (−1.17 → −1.16; −0.56 → −0.49): the phase × day baselines already remove the linear drift. The FINAL residual is therefore not a leftover of #30.
2. **Day fixed effects remove most of it** (−1.16 → −0.36 on FINAL; −0.49 → −0.03 on pass2med). The day-FE slope is the within-day, between-animal slope; the pooled slope is a weighted mix of within-day and between-day slopes. Hence the negative covariance sits mainly **between days** — on days when the cohort's night REM ran above its baseline, the cohort's next-day REM ran below — i.e. a shared-day component. The simulation keeps the observed long wakes and gaps per animal but has no shared-day input beyond them, so its between-day slope is ≈ 0 by construction; the simulated means (+0.09 vs −0.04) confirm it.
3. **The exclusion is marginal and FINAL-only**: by point estimate against the 2.5 % quantile of 100 replicates (−1.16 vs −0.91), with the observed CI overlapping the simulated range; on pass2med — the scoring the plan requires for any cross-session contrast ("Do not: use FINAL alone for cross-session contrasts", plan:304; the audit's Established rule, audit:19–23) — the observed −0.49 lies inside.

Also: with day FE the REM test is weak (simulated 95 % range ≈ ±1.2 against an observed effect of −0.36): "PASS" there is "no evidence of a within-animal REM balance", not "evidence of none".

### 3c. Is it a failure of #40? What #40 may claim

Not under the pre-registered rule, and not against the allowed wording. #40's allowed wording concerns daily REM / NREM amounts and their day-to-day variation given the observed waking (audit:154; graph:4786); those checks pass on both scorings (xE:14–21, 94–125). #40's claim text and `r.s40` (graph:4771, 4776–4777) list "the night → day pattern" without a specification; the audit's main-evidence cell quotes only NREM with day FE. Recommended:

- **Scope added to #40 (claim text and `r.s40`):** "…and the night → next-day deviation slope *with day fixed effects* (within day, between animals; NREM and REM)."
- **Forbidden added to #40:** "the model reproduces the night → next-day REM covariance across days (with a linear day term a FINAL −1.16 / pass2med −0.49 residual remains, dominated by the between-day component; unexplained)"; "there is no within-animal REM balance" (the day-FE test is low-powered).
- **The REM part of #13:** stays withdrawn as a balance. The FINAL linear-day slope is a FINAL-only, between-day-dominated residual; it does not re-open #13 as a within-animal balance (the within-day slope is ≈ 0 on both scorings) and is not a scoring artefact *shown*: FINAL's per-session thresholds are not an obvious generator of a negative night → next-day covariance (independent session thresholds add noise; a session spanning dawn would bias it positive), but the 2.4× FINAL / pass2med difference says scoring matters. Record it as a ledger item with two named candidates — a shared-day modulation of REM not in the model, and scoring — as `r.e_vi_linear` already does; set `c.night_day_rem` to resolved with the day-FE reading, and keep the residual as an open ledger item with the test below.

A concrete shared-day candidate the chain already contains: the morning-round REM repayment (#10 / #43) — a pre-round REM shortfall (late night, negative night deviation) followed by extra REM after the round (positive next-day deviation), cohort-wide on round days and absent from the simulation (D2: simulated +0.005 vs observed +0.34, xD2E:508) — is itself a negative night → next-day REM covariance that the model cannot produce. (It is strongest on pass2med while the (vi) residual is strongest on FINAL, so it is a candidate, not the answer.)

### 3d. Discriminating analysis (cheap; the `budget_from_records` tables exist)

1. **Decompose the slope:** regress the cohort-mean next-day REM deviation on the cohort-mean night REM deviation across the ≈ 11 day pairs (between-day), next to the day-FE (within-day) slope, on both scorings and on the simulated replicates. If the negative covariance is in the day means, it is shared-day, and no within-animal budget is implied.
2. **Name the shared-day driver:** add to the linear-day regression (i) a morning-round-day indicator, or drop the 3 h after rounds as A3 / C1 do, (ii) the night and day temperature anomalies and rain (Phase-4 T3's design, audit:68). Report how much of −1.16 / −0.49 survives.
3. **Scoring:** repeat on pass2med and on the ungated / `imu_nremgate` states for the overlapping sessions; list the animal-days where FINAL and pass2med REM deviations differ most.
4. **Power statement for the day-FE test:** state the minimal detectable REM slope from the simulated spread, so (vi) PASS is not quoted as evidence against a within-animal balance.

---

## 4. Round statuses r2–r6 vs the claim audit; the `r.d2_nrem` ledger item

### 4a. Mismatches (everything else checked matches)

Checked against the audit rows: every claim-numbered result node added or changed in r2–r6 (`r.s04/05/06/06a/06b/07/09/10/13/14/14b/16/17/24/28b/29a/29c/30/31/32/33/34/35/36/37/38/39/40/41/42/43`), the hypothesis statuses, the four current r4–r6 judgments and their link strengths, the `answers` / `supported_weakened` text of rounds r2–r6 (graph:5326–5507). Statuses agree with the audit rows (e.g. #6a / #14b / #32 / #33 / #36 / #38 / #40–#42 Established; #6b / #10 / #31 / #34 / #35 / #37 / #39 / #43 Candidate with the right qualifiers; #13 withdrawn; #17 / #24 superseded; #4 / #16 / #29c Candidate → LFP stage). The mismatches are wording / scope, not status:

| # | where | mismatch | fix |
|---|---|---|---|
| M1 | `j.core.r6` text, graph:295–296: "Established: REM entry is set by one count … read through a **smooth** daily curve that lowers entry about three-fold at night" | The three-fold gain at matched count is #14b (Established, audit:52); that the curve is smooth with no switch at dusk / dawn is #35, **Candidate (strong)** (audit:137; the graph's own `r.s35` graph:3386). The Established sentence bundles a Candidate. | "read through a daily curve (smooth, with no light switch: candidate, #35)". Same for the title of `j.daynight.r5` (graph:3468, "carried by a smooth daily curve") — its text is right (graph:3473–3474). |
| M2 | `r.s21` graph:173–175, 180 | "balancing over the day" — §1. | corrected wording in §1; add a `changes` entry. |
| M3 | `r.s13` graph:2424 (`allowed:` "…sleep is balanced over the 24 h") | a withdrawn claim carries an allowed wording; copied from the stale audit cell (audit:50). | mark historical / strike. |
| M4 | `r.s40` graph:4771, 4776–4777 (and audit:154) | "the night → day pattern" without the day-FE scope — §3. | add the scope and the forbidden wording of §3c. |
| M5 | `j.compensation.r6` link graph:2855: "weakens h.comp.nrem_homeostat, strength: **established**, scope: NREM endings (#42); the morning NREM make-up needs none (ledger)" | The established strength is #42's and is scoped to 10-s NREM endings (audit:156, forbidden "No sleep homeostasis"). The second clause rides on `r.d2_nrem`, whose reading over-reaches (§4b); as written the link lets a ledger item borrow #42's strength. | split: keep the established link scoped to NREM endings; put the NREM make-up in a separate candidate-strength note scoped "no homeostat in the transition rules; a homeostat acting through the amount of waking is conditioned away". |
| M6 | the audit itself, synthesis block "Candidate (strong)", audit:166–170 | still lists "A wake of 7 min or more is not resumed" and "Even after equally short wakes the night halves the REM-entry rate", while rows 42 / 52 and the synthesis's own later lines (audit:172 "#6a Established", audit:173–174 "#14b Established") say Established. | not a graph error — the graph follows the rows (`r.s06a`, `r.s14b` established). Flag for the audit's maintainer; move the two lines to Established and reword the #14b one per §2. |

Minor: the round summaries' strength words all match the rows (r2 "#14b, candidate" at that date; r5 "#14b Established"; r6 "#40–#42 established, #43 candidate"). `r.c1_ramp` (graph, r5) is a correctly scoped ledger null ("not evidence against #6b").

### 4b. `r.d2_nrem` — does the simulator's reproduction of the post-round NREM make-up weaken any claim?

The numbers are right (xD2E:468, 668; morning rounds, pass2med, day-demeaned, NREM payback on NREM debt): observed +0.167 (1 h) / +0.238 (3 h) vs simulated +0.129 [+0.017, +0.240] / +0.154 [−0.042, +0.359]; on FINAL both ≈ 0 (observed +0.046 / +0.086, simulated +0.077 / +0.093, xD2E:458, 658). The REM payback on the same records is *not* reproduced (observed +0.336 / +0.961 vs simulated +0.005 [−0.23, +0.27] / +0.013 [−0.51, +0.54], xD2E:508, 708).

**The reading over-reaches by one step.** The title says the make-up "is reproduced by the count rules without any NREM homeostat" (graph:2744). But the simulation is conditional on the observed long wakes (≥ 7 min) and gaps (xE:63–66; the graph's own basis `b.sim_conditional`; #40's forbidden "claims independent of the observed waking pattern", audit:154). An NREM debt before a round and an NREM make-up after it that run through *how much the rats slept* (more / longer waking before, less after) are copied from the data, not generated by the rules; the only generated part is the REM / NREM split inside sleep. So the correct statement is: **the morning NREM make-up needs no NREM homeostat in the transition rules — consistent with #42 — but a homeostat acting through the amount of waking is conditioned away, not tested.** This is exactly the distinction #42's forbidden wording draws ("only its effect on these 10-s transitions was tested; #31 and NREM amounts are separate", audit:156).

What it does to the claims:
- **#10 (audit:47), the clause "NREM lost at a morning round is partly made up within the hour":** weakened *as evidence of regulation* — a model with no NREM regulation reproduces it given the observed waking; the clause can stay as description (pass2med only) but should not be cited for a homeostat. Propose a scope note on #10 rather than a status change (it is already Candidate).
- **#43 (audit:157) and the REM-specificity of #10:** *strengthened*, not weakened — the same simulation on the same records reproduces the NREM make-up and not the REM repayment, a within-method contrast that argues against the REM result being an artefact of the payback measurement. Worth adding to #43's main evidence.
- **#42, #31, #40:** untouched. The logic audit's earlier use of the NREM make-up as homeostat evidence (which `r.d2_nrem`'s link note cites, graph:2756) was already superseded by #31 / #42; this item adds the correct reason.

Suggested title for `r.d2_nrem`: "The NREM make-up after morning rounds is reproduced by the simulation, which copies the observed waking — no NREM homeostat in the transition rules is needed; a homeostat acting through the amount of waking is not tested." Link: `weakens h.comp.nrem_homeostat`, strength candidate, scope "transition rules only; conditioned on the observed waking"; add `supports r.s43`-style note on REM-specificity.

---

Files read: graph (conflicts 5241–5266, rounds 5268–5507, nodes cited above), audit (full), plan (§3, §5 Step D–E, §6), xA (A3), xC (C1), xE (Reading, definitions, checks), xD2E (D2, (vi), (ii)), xD1 (verdict), CSV (full), logic_audit (checks 1–2, 174–183, 380–395, 462). Small read-only Python checks in this scratchpad: `budget_rows.py` (CSV dump), `graph_dump2.py` (YAML statuses). No file in the repo was modified.

---

*Provenance (appended by the main session, 2026-10-09; kept at the end so the line numbers cited by the logic graph stay valid):* read-only Fable 5.1 review of the conflicts the `research-logic` agent found in rounds r2–r6 of `research_logic/graphs/sleep_2026c.yaml`. Consequences: the claim-audit wording fixes in commit a3ca36e (#10, #13, #14b, #21, #40, #43 and the synthesis) and the three conflicts resolved in the graph. Line numbers in the text refer to the files as they were before a3ca36e.
