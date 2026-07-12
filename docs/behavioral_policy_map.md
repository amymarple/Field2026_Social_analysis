# Behavioral-policy map — the rat agent is more than one process

**Purpose.** Stop the analysis from treating **one** behavioral process — *site-residence termination*
— as the animal's complete policy. This map locates what we have modeled inside the full decision /
search space, defines the module dependency graph, and fixes the language each module is allowed.

**Machine-readable registry:** [`wiser/configs/behavioral_policy_modules.yaml`](../wiser/configs/behavioral_policy_modules.yaml)
(all 18 fields per module). **Phased plan + gates:** [`implementation_plan/behavioral_policy_roadmap.md`](../implementation_plan/behavioral_policy_roadmap.md).

## Where the current model actually sits

> The existing model is **`site-residence termination` (module 5) + `destination & settlement`
> (module 6)** — "given the animal is resident at a site, when does residence end and which site comes
> next." **It is NOT "the rat policy" and NOT "search strategy."** It is the *exit side* of one loop.

```
   ┌──────────────── the locomotor loop (Phase 1 = the state machine) ───────────────┐
   │                                                                                  │
   │   (2) stable        (3) bout          (4) active          (5) site-residence     │
   │   residence/rest ──initiation──►    locomotor bout ──►   TERMINATION ────────►   │
   │        ▲            [NOT built]       [util only]         [BUILT — exit] │        │
   │        │                                                                 ▼        │
   │        └────────────  (6) destination & settlement  ◄────────  [BUILT — where]    │
   │                       [rebuild on clean state = Phase 2]                          │
   └──────────────────────────────────────────────────────────────────────────────────┘
        every module above is cut on  (1) behavioral state segmentation  [substrate]

   layered on the VALIDATED states (later phases):
     (7) approach/avoid ── within active bouts only ──┐        (12) short-term social history
     (8) following/leading ───────────────────────────┤        (13) long-term pairwise social graph
     (9) return-vs-explore ─┐                          │            = LATE CHALLENGER, not the framework
     (10) ARS vs global ────┼─ excursion-level search  │        (14) latent motivation / reward
     (11) route/corridor ───┘  (11 BLOCKED: georef)    │            = capstone, gated, likely NO-GO
```

## Dependency graph (A → B: A is a prerequisite of B)

```
                         (1) behavioral state segmentation   [substrate — everything needs it]
        ┌──────────────┬──────────────┬───────────────┬──────────────┐
        ▼              ▼              ▼               ▼              ▼
  (2) residence   (3) bout        (4) active      (5) site-       (6) destination
      /rest           initiation      bout            residence       & settlement
        │  └────►(3)                    │              termination◄───────┘ (needs 5)
        └────►(5)                       │                  │
                                        ▼                  ├────►(9) return-vs-explore◄──(6)
                                 (7) approach/avoid         │            │
                                 (8) following/leading◄─(12)│            ▼
                                        ▲                   │      (10) ARS vs global◄──(4)
                                        │                   │
                              (12) short-term social ◄──────┘      (11) route/corridor◄──(4,6) ⛔georef
                                        │
                                        ▼
                              (13) long-term pairwise social graph   [LATE CHALLENGER]
                                        │
   (3,5,6,7,9,10) ─────────────────────►(14) latent motivation / reward   [capstone, gated]
```

The **organizing framework is a hierarchical semi-Markov state machine** (the loop 2→3→4→5→6→2).
Social, search, and memory modules attach to its **validated** states. A **graph transformer is a
LATE CHALLENGER model for module 13 only** — never the project's organizing framework.

## Module summary (full fields in the YAML)

| # | Module | Action / outcome | WISER? | Status | One-line scope guard |
|---|---|---|---|---|---|
| 1 | behavioral state segmentation | state label + change-points | partial (rest=proxy) | ⚠️ partial | states ≠ validated ethogram; not "sleep" |
| 2 | stable residence / rest | rest state + episodes | yes (depth no) | ⚠️ partial | settled ≠ "decided to rest"; not "sleep" |
| 3 | **locomotor-bout initiation** | initiate-vs-stay hazard | yes (onset) | ◻️ **planned — Phase 1 / NEXT** | onset ≠ "decided to forage"; not "wake" |
| 4 | active locomotor bout | bout + kinematics | coarse yes, fine no | ⚠️ partial | endpoints yes, fine steering no |
| 5 | **site-residence termination** | leave-vs-stay hazard | yes | ⚠️ **candidate (BUILT)** | not "the policy"/"search strategy" |
| 6 | **destination & settlement** | next-ROI + settle | endpoints yes | ⚠️ partial (rebuild) | not "route choice"/"navigation" |
| 7 | approach/avoid (group/partners) | toward/away per step | ≥1 m yes | ◻️ planned — Phase 3 | association, not attraction/motivation |
| 8 | following / leading | lagged path-reuse | temporal only | ⚠️ candidate | temporal order ≠ pursuit/"leader" intent |
| 9 | return-vs-explore | return vs novel | yes | ◻️ planned — Phase 4 | not "curiosity/novelty drive" |
| 10 | ARS vs global search | radius/coverage/revisit | coarse yes | ◻️ planned — Phase 4 | geometry, not "foraging strategy/optimal" |
| 11 | route / corridor selection | path / directness | ⛔ needs georef | ⛔ blocked | no directional/metric route claims |
| 12 | short-term social history | trailing social features | ≥1 m yes | ◻️ planned — Phase 5 | predictive, not "memory"/causal |
| 13 | long-term pairwise social graph | pairwise weights | co-presence yes | ◻️ planned — Phase 5 late | not "social network/bonds"; late challenger |
| 14 | latent motivation / reward | reward class or NO-GO | no (latent) | ⛔ blocked | not "the goal/utility"; likely NO-GO |

## Standing scope statement (travels with every result)

Any policy result must state: *"This is the `<module>` process — one module of a hierarchical agent
whose behavioral-state segmentation, bout initiation, active-bout control, destination/settlement,
approach/avoid, following, search (return-vs-explore / ARS / route), social memory, and motivational
modules are separately specified in `configs/behavioral_policy_modules.yaml`; the others are
[built / planned / blocked] and are NOT represented here."* Calling one module "the rat's policy"
over-claims exactly the way the raw point-in-ROI decision unit over-claimed departures.

## Cross-cutting measurement invariants (apply to every module)

Unverified WISER inch frame → topology + coarse (≥14 in) distances only, no absolute direction; ~7 in
jitter floor (fine kinematics / <1 m social are noise); ~4 Hz; gaps are "unknown" (never a decision);
below-plane dropout ROIs excluded (refuge_4 burrow nights); whole **nights** are the outer CV block
(~8, not 40 cells); rest/sleep and motivation are latent (video/thermal/ephys needed). See
`.claude/skills/regime-aware-wiser-tracking/`.
