# Change log — Decision-boundary validation (Stage 1): pauses are NOT resolvable control-update boundaries on WISER

**Date:** 2026-07-11
**Status:** ⚠️ candidate (validation). **Stage 1 only** — stopped at the interim boundary verdict per
the design's staging gate (boundary interpretation failed). Additive; prior analyses untouched.
**Dir:** `wiser/decision_boundary_validation/` (README, validation_report,
audit/inherited_claim_corrections.md, src/, tables/, plots/, run_manifest.json).

## Motivation

After the bout-segmentation falsification (the ~4 s/~100 in scale is a `min_bout` artifact), the
surviving observation was that movement occurs in straight legs separated by pauses with larger heading
changes. This asks: **are pauses / kinematic changepoints meaningful control-update boundaries, and do
decision-to-decision legs beat the 3 s-filtered bouts?** Falsification-first.

## Stage 0 — inherited-claim audit (done)

`audit/inherited_claim_corrections.md`. Verdict D unchanged. Corrections carried forward: primitive run
median is **sub-second at the jitter floor** (0.54 s no-filter / 0.67 s @7 in / 1.21 s @15 in — same
min_bout=0 set, different displacement floor); **"near-memoryless" retracted** (exponential is the
worst fit; hazard is non-monotone lognormal, no 4 s breakpoint); **"trip" → "merged locomotor episode"**
(transitive pause-bridging, no destination validation).

## Interim verdict: **NO reliable boundary class at WISER resolution**

- **A1** 131,566 candidate events (101,256 pause / 4,575 heading-cp / 25,735 continuous) from the native
  ~4.4 Hz positions, robust multi-window headings.
- **A3 matched CEM** (animal/night/clock/ROI/speed/boundary-dist): pause turn +17.9° over continuous
  (RR>90° = 6.2), stable across animals/nights — **but window-sensitive**.
- **A7 noise null (DECISIVE):** a straight simulated path with pauses + WISER jitter (no real turns)
  gives a matched pause-turn diff of **+20.4° ≥ the real +17.9°**; heading-cp detector is **30 %/77 %
  false-positive** (straight/speed-change), **4–24 %** sensitive to real turns.
- **Well-resolved data test (sim-independent):** requiring both flanks ≥ 30 in (≫ 7 in jitter) →
  diff **−3.1°** (reverses). Pauses are intrinsically low-displacement, so their headings are
  jitter-limited by construction.
- **A4 predictability:** pause "predictability" advantage is a **speed confound** (paused = trivially
  predictable); post-pause heading is weakly location-structured (residual 1.15→0.83 rad).

**Boundary verdict: rejected (not separable from jitter). Unit verdict: insufficient resolution —
legs cannot be validated. Vocabulary/policy: not testable.** A successful falsification.

## Staging gate — Stages 2 & 3 NOT built

Per "stop and report the interim verdict … if the boundary interpretation fails," no leg extraction,
segmentation comparison (S0–S4), spatial/social tests, unit comparison, or leg-vocabulary/policy
analysis was performed. Deferred, not silently skipped (`run_manifest.json` coverage map).

## Corrected prior report

A transparent correction note was added to `bout_segmentation_validation/validation_report.md` pointing
to the Stage 0 audit (no silent edit of its claims).

## Next step (if pursued)

Not more segmentation tuning — **higher-resolution motion** (CV pose/keypoints or georeferenced
multi-camera tracking) to resolve heading at the low displacements where pauses live. Both the old
bouts and any leg scheme are WISER-resolution-limited.
