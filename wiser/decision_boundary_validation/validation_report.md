# Decision-boundary validation — INTERIM REPORT (Stage 1, verdict-critical core)

**Date:** 2026-07-11 · **Status:** ⚠️ candidate (validation). Re-extracts candidate boundaries from
the native ~4.4 Hz positions (5.97 M cleaned night fixes, 13 nights 06-28→07-10, 4–5 rats), NOT from
`route_bouts.csv`. Pure numpy (scipy/statsmodels absent). Does not overwrite prior analyses.
**Stopped at the interim boundary verdict per the staging gate — Stages 2 (legs) and 3
(vocabulary/policy) were NOT built, because the boundary interpretation failed.**

## 1. Executive verdict

**Boundary verdict: NO reliable boundary class exists at WISER resolution.** The apparent
"reorientation at pauses" is **not separable from WISER localization jitter**:
- a **jitter-only null** (straight simulated path with pauses, no real turns) reproduces a matched
  pause-vs-continuous turn difference of **+20.4°**, *larger* than the real **+17.9°**;
- restricting to **well-resolved headings** (both movement flanks ≥ 30 in ≫ the 7 in jitter floor) makes
  the effect **vanish and reverse to −3.1°**;
- the in-motion heading-changepoint detector is **30 % false-positive on straight paths, 77 % on
  speed changes**, and detects only **4–24 %** of real 90° turns;
- the pause "predictability" advantage is a **speed confound** (a paused animal is trivially "stay-put"
  predictable), not a control-update signal.

Because pauses are intrinsically **low-displacement** events (the animal barely moves before/after a
stop), WISER cannot resolve whether a pause involves reorientation. **Unit verdict: insufficient
resolution — decision-to-decision legs cannot be validated.** Vocabulary/policy verdicts: **not
testable** (downstream not built, per the gate).

This is a **successful falsification**: the decision-boundary interpretation does not survive the
matched-control + noise-null tests the design demanded.

## 2. Corrections to inherited bout-segmentation claims

See `audit/inherited_claim_corrections.md`. Verdict D (the ~4 s/~100 in scale is a segmentation
artifact) is **unchanged**; three wordings were corrected and carried forward here: (1) the primitive
run median is **sub-second at the jitter floor** (0.54 s no-filter / 0.67 s at 7 in / 1.21 s at 15 in) —
the "0.54 vs 1.21" were the same min_bout=0 set at different displacement floors; (2) **"near-memoryless"
retracted** — exponential is the *worst* fit; the hazard is non-monotone lognormal, no 4 s breakpoint;
(3) **"trip" → "merged locomotor episode"** (transitive pause-bridging, no destination validation).

## 3. Candidate-boundary definitions (Analysis 1)

131,566 candidate events from the native grid (`tables/candidate_boundaries.csv`): **pause** (101,256;
low-speed interval flanked by movement), **heading_cp** (4,575; a local-max windowed heading change
> 40° with no full stop), **continuous** (25,735; mid-run control points). Per event: robust pre/post
heading at 0.5/1/2 s windows (endpoint-anchored, requiring flank displacement > 7 in jitter floor),
turn angle, reversal, pre/post speed, pause duration, ROI, distance-to-boundary, nearest-neighbour
distance, data-quality flags. None discarded — confidence-flagged.

## 4. Matched-control reorientation test (Analysis 3, H1)

Coarsened-exact-matching on animal, night, clock-hour, ROI, pre-speed, boundary-distance. Raw pause
turn **64.9°** vs continuous **22.7°** → after matching **42.9° vs 25.0° (diff +17.9°, RR>90° = 6.2)**.
It held across all 5 animals (+14–22°) and 13 nights (+12–38°) and dropping any single match variable
(diff 18–20°). **But** it is window-sensitive (0.5 s window → +4.9°) and — decisively — **disappears
under the noise null and the well-resolved restriction (§7).** `tables/boundary_matched_*`.

## 5. Predictability-break test (Analysis 4, H3)

Pre-event velocity extrapolation error at 0.5–5 s horizons. At **pauses**, error is *lower* than
continuous (ratio 0.41–0.54) — a **speed confound** (near-stationary → "stay-put" wins), NOT a break.
**heading_cp** show higher error (ratio 1.2–1.9) but partly by construction (selected as turns).
Only clean signal: post-pause heading is better predicted by **location** (residual 0.83 rad) than by
pre-heading persistence (1.15 rad) — weak, location-structure driven. `tables/predictability_break_results.json`.

## 6. Segmentation-method comparison (Analyses 5/6) — DEFERRED per the staging gate

The design gates the S0–S4 segmentation comparison and threshold sweep behind a defensible boundary
class. Since §7 shows no boundary class survives the noise null, building leg segmentations on invalid
boundaries would be misleading. Deferred, not silently skipped. (A pause-only S1 would inherit the
jitter-artifact reorientation; a heading-cp S2 inherits the 30–77 % false-positive rate.)

## 7. Noise and threshold sensitivity (Analysis 7) — the decisive control

Straight-line simulated motion (speed profile sampled from real data, incl. sub-threshold pauses, **no
real turns**), per-axis jitter σ = 5 in (≈ 7 in radial floor), through the exact pipeline:

| test | result | meaning |
|---|---|---|
| matched pause-turn on a STRAIGHT path | pause 35.5° vs cont 15.1°, **diff +20.4°** | jitter alone ≥ the real +17.9° |
| heading_cp false-positive rate | **0.30** straight / **0.77** speed-change | detector fires on noise |
| real-turn detection sensitivity | **0.24** (90° moving) / **0.04** (pause+turn) | misses most real turns |
| apparent turn vs flank displacement | 33° at <10 in, still 29° at 15–25 in | jitter inflates turn at low displacement |

Well-resolved data-only restriction (independent of the sim): flank displacement ≥ 30 in →
**diff −3.1°** (RR>90° = 0.51). `tables/noise_null_results.json`, `well_resolved_pause_turn.csv`,
`plots/real_vs_noise_null.png`.

## 8. Spatial and social context (Analysis 8/9) — not built

Deferred with the downstream analyses (boundary class failed). Candidate events do carry ROI,
boundary-distance and nearest-neighbour fields for a future pass if resolution improves.

## 9–11. Legs, unit comparison, leg vocabulary — NOT built (gate)

Per the staging instruction, no locomotor-leg extraction, unit comparison, or leg-vocabulary
validation was performed, because Stage 1 did not identify a defensible boundary class.

## 12. Negative and ambiguous findings

- **Negative:** pause reorientation not separable from jitter; heading-cp detector noise-dominated;
  pause "predictability" is a speed confound.
- **Ambiguous / weak:** post-pause heading is modestly location-predictable (could reflect route
  geometry rather than a decision); the raw matched effect is real *in the data* but within the
  jitter-artifact range, so it cannot be attributed to behaviour.
- **Resolution limit:** pauses are intrinsically low-displacement, so their headings are jitter-limited
  by construction — WISER (~7 in, ~4.4 Hz) is the wrong instrument to validate reorientation decisions.

## 13. Claim table

| proposed claim | required evidence | observed result | verdict |
|---|---|---|---|
| Pauses are reorientation boundaries (H1) | matched turn > continuous, exceeding jitter null | matched +17.9° but null +20.4°; −3.1° when well-resolved | **REJECTED** (not separable from jitter) |
| Heading-changepoints are cleaner boundaries | low false-positive vs jitter | 30–77 % false-positive; 4–24 % sensitivity | **REJECTED** |
| Pauses are predictability-break points (H3) | higher post-event error, speed-controlled | pause error *lower* (speed confound) | **REJECTED** (confounded) |
| Post-boundary choice is location-structured | location beats persistence for post-heading | residual 1.15→0.83 rad | **WEAKLY SUPPORTED** (geometry, not proven decision) |
| Decision-to-decision legs are a better unit (H2/H4) | legs beat bouts on coherence/prediction | not testable — no valid boundary | **NOT TESTED** (gate) |

## Plain-language answer

**No.** At WISER's ~7 in jitter and ~4.4 Hz sampling, pauses and kinematic changepoints are **not**
demonstrable control-update boundaries — the apparent reorientation at pauses is what localization
noise produces on a straight path, and it disappears when headings are actually resolvable. So
decision-to-decision "legs" cannot be validated as a more natural vocabulary than the 3 s-filtered
bouts **with this sensor**. The right next step is not more segmentation tuning but **higher-resolution
motion** (CV pose/keypoints, or georeferenced multi-camera tracking) to resolve heading at the low
displacements where pauses live. Both the old bouts and any leg scheme remain WISER-resolution-limited.

## Coverage & limits

Done (Stage 1): Stage 0 audit, A1 candidate extraction, A2 robust heading, A3 matched controls
(+sensitivity), A4 predictability break, A7 noise null (+well-resolved restriction). Deferred **by the
staging gate** (boundary failed): A5/A6 segmentation comparison + threshold sweep, A8 spatial, A9
social, A10 legs, A11 unit comparison, A12 leg vocabulary, A13 policy. scipy absent → all stats in
numpy. Jitter σ for the null estimated ~5 in/axis (≈ documented 7 in radial floor); the well-resolved
data test is simulation-independent and agrees. Inch frame unverified.
