# 2026-07-11 — Cross-check: decision-boundary validation ↔ current locomotor/policy modeling

**Status:** ⚠️ candidate (validation reconciliation). Cross-checks the WISER agent-policy modeling
(module 5 leaving hazard, module 3 locomotor-bout initiation, module 4 bout substrate) against the
independent **`decision_boundary_validation`** (DBV) falsification suite, and fixes the carry-forward
caveats it implies. **Outcome: no current modeling result is invalidated; three caveats are added and
one Phase-2 design constraint is made mandatory.**

## What DBV established (its verdict, verbatim scope)

DBV (`wiser/decision_boundary_validation/`, Stage 1, 13 nights, 5.97 M native ~4.4 Hz
fixes) asked whether **pauses / kinematic changepoints are control-update boundaries** and whether
**decision-to-decision "legs" beat 3 s-filtered bouts**. Verdict: **NO reliable boundary class exists at
WISER resolution.** Decisive evidence:
- a **jitter-only null** (straight simulated path, no real turns) reproduces a matched pause-vs-continuous
  turn difference of **+20.4°** — *larger* than the real **+17.9°**;
- restricting to **well-resolved headings** (flank displacement ≥ 30 in ≫ the 7 in jitter floor) makes the
  effect **reverse to −3.1°**;
- the heading-changepoint detector is **30–77 % false-positive** and **4–24 % sensitive**;
- the pause "predictability" advantage is a **speed confound**.

DBV's scope is **fine within-movement kinematics** (turn angle at a pause, heading changepoints, legs),
which live at **low displacement** where WISER's ~7 in jitter dominates.

## Cross-check against the current modeling (what scale each result lives at)

| Result | Scale it uses | DBV-relevant? | Verdict |
|---|---|---|---|
| **Module 5 leaving hazard** (leave-vs-stay per epoch) | coarse hysteretic ROI residence (enter 10 s, exit 30 s; buffer 14 in) | departure = ROI-state exit, **not** a fine turn/leg | **CONSISTENT — stands** |
| **Module 3 bout-initiation hazard** | onset = debounced speed-cross > 12 in/s sustained ≥ 10 s → **large displacement** | operates *above* the jitter-limited regime | **CONSISTENT — stands** |
| **Module 3/4 bouts** (in_place/relocating, dur_s) | contiguous active runs, endpoint ROIs only | claims bout **existence + endpoints**, no turns/legs | **CONSISTENT — stands** |
| **Module 6 destination** (old `build_destination_table`) | next **named** hysteretic visit's ROI | endpoints yes, but no settlement validation & misses open terminations | **stands as-is; Phase-2 rebuild required (below)** |

**Verification that no fine-kinematic claim exists:** a grep of the module-3 code + change log for
`straight|turn_angle|heading|reorient|leg|changepoint|control-update|tortuos` returns **nothing** — the
locomotor modules never claim within-bout turn/heading/leg structure. So the DBV falsification of fine
boundaries does not touch any number the current models report. The bout onset is a lower-bound
speed-onset (already documented); DBV independently confirms that anything *finer* than that (the shape
of the movement between onsets, pause reorientation) is **not resolvable** — which is why module 3/4
correctly stop at bout existence + coarse endpoints.

## Carry-forward caveats added (this change)

1. **Modules 3 & 4 — fine within-bout kinematics are unresolvable at WISER resolution.** Bout existence,
   onset timing, and endpoint ROI are coarse and reliable; within-bout turns, sub-second pauses, path
   shape, and "legs" are **jitter-limited and not claimed** (DBV: heading-cp 30–77 % false-positive;
   pause reorientation not separable from a straight-path jitter null). Pointer added to the module-3
   change log and the registry module-4 entry.
2. **Terminology — "trip" is retired.** Per DBV's Stage-0 audit, a transitively pause-bridged locomotor
   episode is a **"merged locomotor episode," not a destination-coherent trip** (no destination
   validation was ever done for it). The current modules never used "trip"; this records the standard.
3. **Primitive-run / hazard wordings (inherited bout-segmentation).** DBV corrects the older
   `bout_segmentation_validation` claims (primitive run median is **sub-second at the jitter floor**,
   ~0.5–0.7 s; termination hazard is **non-monotone lognormal, no 4 s breakpoint** — "near-memoryless"
   retracted). These concern that prior directory, **not** the module-3/5 hazards (which are per-epoch
   discrete-time hazards over the *coarse* residence/rest state, a different construct), but are noted so
   the two are not conflated.

## Mandatory design constraint for Phase 2 (destination & settlement)

DBV's core lesson — **you cannot validate a destination from where a pause-bridged movement episode
ends; you must anchor it on observed sustained stable residence** — becomes the governing rule for the
Phase-2 rebuild (this session, next change log). Specifically: **a destination is defined only after
SUSTAINED STABLE RESIDENCE** (a named-ROI stationary episode meeting a minimum-duration + confidence
gate), and every inter-settlement transition is typed as **destination-settlement / same-site return /
open-field termination / censored**, with pass-through recorded as a covariate — and **the representation
is validated (sensitivity grid + jitter-tolerance + planted selftests) BEFORE any destination-choice or
search model is fit.** This keeps Phase 2 at the coarse scale WISER can resolve and avoids the exact trap
DBV falsified. See `change_log/2026-07-11-destination-settlement-rebuild.md`.

## Definitions (formula + plain text) referenced here

- **Matched pause-turn difference** (DBV): $\Delta\bar\theta = \bar\theta_{\text{pause}} -
  \bar\theta_{\text{continuous}}$ over coarsened-exact-matched (animal, night, hour, ROI, pre-speed,
  boundary-distance) strata; $\theta$ = robust pre→post heading change (deg). Plain: how much more a
  paused animal appears to turn than a matched moving one — **+17.9° observed, +20.4° from jitter alone**.
- **Well-resolved restriction** (DBV): the same difference computed only on events whose both movement
  flanks displace ≥ 30 in (≫ the 7 in jitter floor) → **−3.1°** (the apparent turn is a jitter artifact).
- **Jitter floor** = 7 in (fixed-position p-percentile of `speed_inps_smooth`·dt); displacement below it
  is indistinguishable from localization noise. **Sustained stable residence** (Phase-2, defined in the
  rebuild) = a stationary episode with `in_named_roi` and duration ≥ a settlement threshold — the only
  anchor at which a "destination" is measurable.

## Scope guard

This is a measurement cross-check, not a new biological result. It confirms the current models sit at the
resolvable coarse scale and imports DBV's resolution limit as an explicit constraint. Frame UNVERIFIED;
all claims topology + coarse distance only.
