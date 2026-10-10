# Plateau audit — sleep behaviour explore → LFP stage (Fable, read-only, 2026-10-10)

Sources: claim audit #30–#63 + Synthesis; plan status, §1, §9–§13; Reading of E, S, P, T, L, H; F1/F2 verdict tables; REM-ripple Answer; logic-audit header. No code run.

## Executive summary

**GO to the LFP stage now.** The behaviour-level stage has plateaued: since F1 (10-09 midday) four amendments (P, T, L, H) produced one parametric re-description of a known effect (#56), one scoped negative (#58), two corrections of earlier readings (#57 "REM-side" withdrawn; FINAL's REM residual base-dependent) and two descriptions (#62, #63). The F2 batch held nothing. Every residual left — #60, #43, #62 — needs a modality the stage forbids (LFP or video). Finish one cheap behaviour-level term first (hours), run the long-wake generative model in parallel as a time-boxed project, not a gate. First LFP step: P vs depth vs P + depth on identical held-out steps (astra's test), with #60 and the opening field NREM as corollaries.

## 1. Has the behaviour-level stage plateaued? — Yes

**Yield by round (new biology vs correction/null):**
- A–C, D–E (10-09): the count model #32–#36, night gate #14b, social #38, generative check #40–#42, REM length #48, arousals fall with P #51 — the real yield. Nulls were informative (#42, #52, #53).
- F2: 7 hypotheses, 0 hold on both scorings; two one-scoring. F1: 5 hold, 2 are Candidates sharing a scorer rule (#49, #50).
- P/T/L/H: #56 (Candidate; held-out gain pass2med only), #58 (negative), #59 (field-record correction), #61 (no first-entry gap), #62–#63 (description). The one "new" candidate, #60, was already in L; H strengthened it on FINAL only to the edge (22.9 vs ≤ 22.3, 100 replicates).

Pattern: each amendment resolved an artefact of the previous one and converged on questions the allowed inputs cannot answer — sleep vs immobility (#62: "video or LFP decides"), the mechanism of #60, whether P is a proxy for cortical state (#4 parked). That is a plateau.

**Behaviour-level questions with real expected gain:**
- "Last long wake, carried to the first REM, × dark" term (plan's next step): cheap (one term in B-full + the conditional simulation of H3), may absorb #60 and #6b. **Do before LFP** — it decides whether #60 needs an LFP test at all.
- Generative long-wake model (unconditional 24-h simulation; tests the organising idea "regular inputs, no budget" and drift #30): substantial new model class; the long wakes are driven by foraging, housemates, weather, handling — it can fail for reasons unrelated to the scheduler. **Not essential before LFP**: nothing in LFP-1/2 depends on it, and its outcome does not change which LFP test is right. Run it in parallel, time-boxed, with pass rules written first.
- Two-phase arousal on the entry clock: low gain (H2 unresolved: clocks differ by minutes vs τ_A 20–40 min; T1 failed by +0.005 % with 3/6). **Stop.**

## 2. LFP questions, ranked by expected gain

Common preconditions: depth = slow-wave slope / delta on a **non-scorer channel** (different shank; z within animal × probe block, never across a move, unstable ~4 h windows excluded); strictly past windows (#4's [t−150, t−30) s; lag ≥ 60 s sensitivity); identical held-out steps as B-full; both scorings; 09-11 19:40 cut; post-round 3 h handled as in S. Animals: SF07–SF10 whole run; SF11 to 09-07 06:10 (implant off); SF12 to 09-10 14:53 (contact failing). Ripple tiers per the quality guide (SF11 to 09-02 only; SF12 block 3 low contrast). Theta: all shanks carry REM theta; no SLM; SF07 and SF11-1a have no radiatum site.

| rank | question | expected gain | why |
|---|---|---|---|
| 1 | **P only vs depth only vs P + depth**, REM and WAKE separately (= #4 made decisive) | high | #4's lagged depth gave −0.22 % [−0.33, −0.10], 6/6 — same league as #36 (−0.36 %), 4× the ripple bound. Decides whether P is a behavioural proxy for cortical depth or a parallel process; also tests #14b at matched depth (attenuation of dark alone = reallocation, per astra). Caveats: night NREM deeper (−1.31 SD) and onset ≈ 06:00 confound clock vs time-since-onset — use naps and evening post-round onsets where they decouple. |
| 2 | **#60 with pre-transition depth** (depth-weighted count on evening post-round records; matched natural evening onsets) | medium-high, conditional | Cleanest REM-side residual, but FINAL is at the edge; run as a corollary of rank 1 (same features), not a separate pipeline. Only if the "last long wake × dark" term does not absorb it. |
| 3 | **Theta / transition fragments before the first REM** after evening rounds; theta present but not scored REM | medium | A pass2med scoring artefact (fixed thresholds miss low-amplitude early-night theta; REM-clean removes moving REM) is a live explanation of #60. Detectors exist (phasic/tonic plan 10-09; theta-type plan waits for the user). Use a shank other than the scorer's theta channel. |
| 4 | **Opening field NREM: sleep vs awake immobility** | low for the model, **high for scorer validity** | ~50 % of post-round records (#59, #62). If awake immobility (LIA) scores as NREM under the IMU-EMG scorer, #44/#56/#63's first-hour numbers carry it. ~50 episodes, descriptive, cheap; exclude logger-start transients; pair with the user's blind review. |
| 5 | #4 alone | — | merged into rank 1. |
| 6 | SWR ↔ REM beyond #54/#55 | low | bounded negative (≤ 0.05 %); the residual signal is the scorer's cut of short bouts; a last-minute term within long bouts is transition-local. Stop unless rank 1 raises a ripple-vs-depth question. |

## 3. Recommendation: GO, ordered

**Finish at behaviour level (≤ 1 day):**
1. The "last long wake × dark" term (B-full + H3 conditional simulation; pass = held-out Δ CI < 0 both scorings, ≥ 5/6, and #60's evening L_N′ inside on both).
2. Freeze: claim audit + research-logic graph as the behaviour-level baseline the LFP stage is scored against.
3. Spin off the long-wake generative model as a parallel, time-boxed project with pre-registered checks (daily REM/NREM SD and the #30 drift emerge unconditionally; fail is informative).

**LFP-1 — depth and the count (pre-registered).** Feature: per 10-s step, mean z-depth over [t−150, t−30) s from one non-scorer site per animal × block (report scorer-shank as sensitivity); +1 h-shifted depth as negative control. Models on identical forward-chained steps: P-only (B-full), D-only (P replaced by a depth spline), P + D, and dark × depth. Pass rules: (a) "depth adds": P + D vs P Δ log-loss CI < 0 on both scorings, ≥ 5/6, control ≈ 0; (b) "P is a proxy": P + D vs D not significant on both AND D-only ≤ P-only; (c) "two processes": both (a) and P + D vs D significant; (d) "night via depth": the dark coefficient falls AND dark × depth gives held-out gain — a smaller coefficient alone is reported as reallocation; (e) depth as outcome: depth ~ P + clock + prior wake within block, sign 5/6 on both scorings. Separately for REM and WAKE exits.

**LFP-2 — #60 and the opening NREM.** (a) Depth-weighted (or depth-thresholded) count applied to the H3 evening conditional simulation: pass = evening L_N′ inside on both scorings while the morning and Step E's checks (≥ 13/14) stay intact. (b) Theta fragments: share of REM-like theta/delta seconds scored NREM in the 10 min before the first evening post-round REM vs matched natural evening onsets; pass = Δ CI excludes 0 both scorings, 5/6. (c) Opening field NREM: delta/slope and spindle-band power of the opening bout vs the same animal's house NREM within 1 h; reading rule fixed beforehand ("NREM-like" ≥ 70 % of episodes within 0.5 SD of house NREM; otherwise "awake immobility", which then becomes a scorer-validity ledger item for #44/#56/#63).

**Stop doing:** arousal-shape variants and clock re-anchoring (S2/P/T/L/H exhausted the held-out gain); WISER/weather/social hypothesis batches (F2 all null; 97 % of NREM steps are house-with-mates — no power); REM-repayment rules (#43 stays Candidate until a frozen independent state can be tested; its only robust form is pass2med's slope).

## 4. Claims whose wording bears on the decision (3)

1. **#60 "Candidate (strong)" is over-stated.** FINAL's entry-clock margin is 0.6 min above the 97.5th percentile of 100 replicates and FINAL was inside in L's subset; the robust part is pass2med (24.1 vs ≤ 17.8). Consequence: #60 is a corollary of LFP-1, not its own step, and the behaviour-level "× dark" term gets first shot. Suggested status: Candidate (pass2med strong, FINAL at the edge).
2. **The Synthesis's organising idea ("daily totals regular because inputs are regular") is untested, and #40's conditioning is doing the work.** The forbidden-wording column is correct; the stage decision should not read the scheduler as finished. This is why the long-wake model should run — in parallel, because its answer does not change LFP-1/2.
3. **#62 is under-weighted as a scorer-validity risk.** The pre-registered rule separated "settling" from a scorer-edge artefact by head stillness only; awake immobility passes the same rule. If half the post-round records open with misclassified immobility, every first-hour post-round number carries it. This moves LFP-2(c) from optional to required, and it is cheap.

## Do not do

- Do not compute depth on the scorer's channel, or without the ≥ 60 s lag sensitivity, or z-scored across a probe move.
- Do not add a REM-repayment or REM-need rule (#43); do not re-run part Q.
- Do not treat a smaller dark coefficient at matched depth as "the night effect is depth" without held-out gain.
- Do not pool SF11 after 09-07 06:10 or SF12 after 09-10 14:53; do not use SF11 ripples after 09-02.
- Do not gate the LFP stage on the long-wake generative model, and do not run further F-batch hypotheses on WISER/weather at the current power.
- Do not call the opening field NREM "sleep" or "freezing" before LFP-2(c) and the user's video/LFP review.
