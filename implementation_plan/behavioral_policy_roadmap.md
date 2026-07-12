# Implementation plan — Behavioral-policy roadmap (phased, gated)

**Date:** 2026-07-11
**Status:** roadmap / architecture only. **No new scientific models are run in this task.**
**Companions:** map [`docs/behavioral_policy_map.md`](../docs/behavioral_policy_map.md) · registry
[`wiser/configs/behavioral_policy_modules.yaml`](../wiser/configs/behavioral_policy_modules.yaml)

## Why this exists

The clean identifiability work modeled **`site-residence termination` (module 5) + `destination &
settlement` (module 6)** — the *exit side of one loop*. Treating that as "the rat's policy" would
repeat the earlier over-claim (raw jitter-flicker → false departures). This roadmap sequences the full
agent as a **hierarchical semi-Markov state machine** with social / search / memory modules layered on
its **validated** states, and gates every downstream module behind its prerequisites.

**A graph transformer is a LATE CHALLENGER model for module 13 only** (long-term pairwise social
memory), attempted only after simpler history features prove predictive. It is **not** the organizing
framework of the project. The organizing framework is the state machine.

## The four gates (every phase must pass all four before any downstream phase starts)

1. **Measurement gate** — the module's outcome and predictors are what the sensor actually observes
   (frame-invariant; ≥ jitter floor; ≥1 m for social; gaps 'unknown'); no construct is substituted for
   a measured variable (no "sleep"/"wake"/"pursuit"/"goal"). Uses `/regime-aware-wiser-tracking`.
2. **Support gate** — enough comparable at-risk events across animals × nights (state coverage, not
   just sample size); overlap of comparable states; not concentrated in one night/animal/degraded regime.
3. **Predictive gate** — held-out-**night** improvement in bits/decision over the correct null AND the
   simpler upstream model (effect size + sign across nights, not z alone); survives the module's nulls.
4. **Interpretation gate** — the result is classified (behavioral / measurement-artifact / mixed /
   lower-bound), the allowed language from the registry is used, and the scope statement travels with it.

**Blocking rule:** a downstream module stays **BLOCKED** until *all four gates* of every upstream
prerequisite pass. (E.g. approach/avoid (7) is blocked until the active-bout state (4) passes its gates.)

---

## Phase 1 — Unified locomotor state machine  ◄── THE SINGLE NEXT EXECUTABLE MODULE

Build the loop **residence/rest → bout initiation → active movement → departure → destination/
settlement → residence** on the clean hysteretic substrate. This is the next module — **not** the
social graph.

It must explicitly distinguish, and be tested on each distinction:
- **movement initiation** (rest→active, module 3) from **ROI departure** (module 5);
- **activity inside an ROI** from **leaving** it (a bout can occur without an ROI transition);
- **brief pauses** from **genuine settlement** (a stop is not a new rest visit);
- **entry into an ROI** from **stable residence** (arrival ≠ settled).

Deliverable: one state stream + a `locomotor-bout initiation` hazard (module 3, the entry-side twin of
the built module-5 leaving hazard), reusing the existing hazard machinery.

- **Measurement gate:** initiation is speed-onset above the jitter floor (a LOWER bound; in-nest
  stirring invisible — never call it "wake"); the four distinctions above are operationalized and
  selftested (planted bout-vs-flicker; planted pause-vs-settlement).
- **Support gate:** enough initiation at-risk epochs per animal-night; the four states each populated.
- **Predictive gate:** the initiation hazard beats marginal + circular-shift + conditional-permutation
  nulls at the night-block level; the state machine reconstructs held-out occupancy.
- **Interpretation gate:** "locomotor-bout initiation hazard", not "decided to forage"; states are a
  proxy, not an ethogram.

## Phase 2 — Destination & settlement, rebuilt on the clean state

Rebuild + stress-test module 6 on the clean hysteretic state (settlement = re-entry to the residence
state, not mere ROI entry); origin-specific supported choice sets; matched-choice for symmetric sites.

- **Measurement:** endpoints only (no route/direction — unverified frame); settlement distinguished
  from pass-through. **Support:** supported destinations per origin. **Predictive:** origin-conditioned
  choice beats base-rate + conditional/day-shuffle nulls, held-out. **Interpretation:** "destination +
  settlement", not "navigation/route choice".

## Phase 3 — Approach/avoid, WITHIN validated active bouts only

Build module 7 only on the Phase-1 **validated active bouts**. **Do NOT analyze approach/avoid across
stationary epochs:** crowding-dependent suppression of movement *initiation* (already seen — crowding
suppresses leaving) would otherwise confound **steering** with **failure to initiate** movement.

- **Measurement:** relative bearing needs reliable focal heading (> jitter speed); ≥1 m social only.
  **Support:** in-bout steps with ≥1 other present. **Predictive:** toward/away steering beats
  time-shift + day-shuffle + heading-permutation, held-out. **Interpretation:** "in-bout approach/avoid
  tendency", not "attraction/aversion" (association, not motivation); dyadic only if module 13 passes.

## Phase 4 — Excursion-level search outcomes

Define, on validated bouts+excursions (modules 4,5,6,9): **return vs explore**; **novelty / coverage
gain**; **area-restricted vs global search**; **search radius**; **revisit latency**; **route reuse**
(topological only — module 11 route/corridor stays ⛔ BLOCKED on georeference).

- **Measurement:** radius/coverage relative (not metric); novelty in the ROI/inch frame; unvisited ≠
  avoided. **Support:** excursions per animal-night. **Predictive:** history dependence beats
  history-shuffle + layout base-rate, held-out. **Interpretation:** search *geometry*, not "foraging
  strategy/optimal search/curiosity drive".

## Phase 5 — Social memory (short-term first, graph only if it earns it)

Add module 12 (short-term social history) as trailing pre-decision features to the residence /
initiation / steering hosts. Add module 13 (long-term pairwise social graph — the **late-challenger
graph transformer**) **only if** interpretable short-term history features first improve held-out-night
prediction.

- **Measurement:** strictly pre-decision, ≥1 m. **Support:** pair-nights with co-presence (n=5 → 10
  pairs, thin). **Predictive:** short-term history must improve held-out first; the graph model must
  then beat short-term history AND a degree-preserving graph null, held-out. **Interpretation:**
  "social-history predictive increment", not "social network/bonds"; the transformer is a challenger,
  not the framework.

## Capstone (gated, expected NO-GO)

Module 14 (latent motivation / reward) runs **only** if every upstream forward module passes all four
gates AND the reward-feasibility diagnostic passes (stationarity, coverage, observed-state Markov,
action adequacy). Given latent drives (odor/temp/food-state/social) and modest effect sizes, the
expected verdict is **NO-GO**; the endpoint is the interpretable hierarchical semi-Markov choice model,
**not** IRL.

## The one next executable module

**Phase 1 — the unified locomotor state machine + the bout-initiation hazard (module 3).** It is the
symmetric complement of the already-built leaving hazard, it is WISER-observable, it unblocks Phases
2–4, and it directly repairs the scope gap (we model *when residence ends* but not *when it begins*).
It is explicitly **not** the social-graph transformer, which is a late-Phase-5 challenger.

> **Status — 2026-07-11: Phase 1 BUILT** (⚠️ candidate). `src/locomotor_states.py` +
> `scripts/build_locomotor_states.py` + `scripts/analyze_locomotor_initiation.py`; selftest 10/10;
> decision unit = gap-holding stationary episodes; four gates met (measurement selftested; support
> 1,016 onsets/198,735 epochs; predictive state-skill 6.2%; interpretation: onset = lower bound, not
> "wake"). Finding: initiation ≠ ROI departure (D1 26×); hazard 3.3× higher from open than settled
> shelter; weather ≈0 and group-social detectable-but-negligible (NO-GO) — crowding governs *leaving*,
> not *initiation*. See [change log](../change_log/2026-07-11-locomotor-bout-initiation.md).
> **Next executable = Phase 2** (rebuild + stress-test destination/settlement, module 6, on the clean
> state), gated on Phase 1's gates. Still **not** the social-graph transformer.
