# Bout-segmentation validation — is the "~4 s / ~100 in" scale biological or an artifact?

**Date:** 2026-07-11 · **Status:** ⚠️ candidate (validation). Re-extracts bouts from **positions**
(5.97 M cleaned night fixes, 13 nights 06-28→07-10, 21:00→04:00, 4–5 rats), not from the filtered
`route_bouts.csv`. Pure numpy (scipy/statsmodels absent). Does **not** overwrite the original
analysis. Inch frame UNVERIFIED — distances/speeds are internal.

> **Correction note (2026-07-11):** three wording issues in this report were audited and corrected in
> `decision_boundary_validation/audit/inherited_claim_corrections.md` (verdict D unchanged): (1) the
> "un-truncated median" is 0.54 s with **no** displacement filter vs 1.21 s with the 15 in filter — the
> primitive run is **sub-second at the jitter floor**; (2) **"near-memoryless" is retracted** — exponential
> is the *worst* fit; the hazard is non-monotone lognormal with no 4 s breakpoint; (3) "trip" should read
> **"merged locomotor episode"** (transitive pause-bridging, no destination validation).

## Verdict: **D — segmentation-defined scale** (true structure B + C; A falsified)

The reported "**~4 s locomotor capacity**" and "**~8 ft (100 in) characteristic bout length**" are
**artifacts of the segmentation rules**, dominated by the 3 s minimum-bout filter. The underlying
movement is **B: ballistic, ~straight, ~constant-speed primitives with a near-memoryless termination
hazard (no internal 4 s limit)**, punctuated by **reorientation pauses**, and those primitives are
**C: fragments of longer, paddock-scale, multi-stop trips**. There is **no evidence for A** (a genuine
characteristic run duration).

Engine validated first: at production parameters it reproduces the pipeline (n=1778 vs 1692 + 85
cap-dropped; disp median 97.8 vs 100.0; dur median 3.76 vs 3.8 s; max identical).

## The five decisive results

1. **The scale moves ~1:1 with the minimum-duration filter (A5).** Sweeping `min_bout_s` ∈ {0..5}:
   - duration median = **0.89 + 0.95·min_bout** (R² 0.99) — tracks the imposed minimum ~1:1;
   - displacement median = **21.6 + 25.0·min_bout** (R² 0.99), slope **25.0 in/s = the median speed**.
   The "100 in" is just `min_bout (3 s) × speed (25 in/s) + offset`. Predicted slope (25.0) = observed
   (25.0). Lower the filter and the scale collapses toward the sampling/smoothing floor.

2. **The "tight characteristic scale" is manufactured by truncation (A2/A3).** Un-truncated (min_bout 0)
   duration **CV 0.67**; at min_bout 3 s **CV 0.26**. The un-truncated **median run is 0.54 s**, and
   `median | dur ≥ 3 s = 3.76 s` — i.e. the production "3.8 s" is exactly the conditional median of a
   0.54 s distribution cut at 3 s. Nothing biological pins 4 s.

3. **The termination hazard is near-memoryless — no 4 s feature (A4/A10).** Best-fit distribution is
   **lognormal** (AIC 92,300 ≪ Weibull 102,469, gamma 103,026, exponential); Weibull shape **k = 1.10 ≈ 1**
   (flat hazard). The only piecewise-hazard breakpoint is at **1.29 s ≈ the 1 s speed-smoothing window**
   — a measurement floor, not 4 s. So verdict **A is falsified**: no reproducible elapsed-time capacity.

4. **99 % of "bouts" are fragments of longer trips (A6).** Allowing a pause of just 5 s to bridge
   run–pause–run merges **98.9 %** of production bouts into multi-leg trips; at a 30 s merge, trips reach
   **disp 524 in ≈ the full paddock diagonal (537)** over ~200 s with ~13 legs. The "never crosses the
   paddock" claim was a segmentation artifact. (Merged trips meander — straightness 1.1→4.1 — so they are
   run–pause–run journeys, not single straight corridors.)

5. **Pauses are reorientation points (A7).** Heading turns **median 64°** across a bridged pause vs
   **16°** within a continuous run (51 % vs 11 % of turns > 60°). Movement is *straight-run → pause +
   reorient → straight-run*: the pause is where direction is chosen, not a random motor interruption.

## Supporting results

- **Short bouts are NOT behaviourally wiggly (A8).** Real short-bout straightness (**1.08**) barely
  exceeds a straight-line-plus-WISER-jitter null (**1.06**). The earlier "short bouts wiggle (1.46)" was
  a small-displacement division artifact, not behaviour.
- **The artifact is universal (A11).** Every animal (un-trunc dur ~1.2 s → prod 3.6–3.8 s), every night,
  5-rat vs 4-rat, first vs second half: identical. Biology would vary across animals/nights; a
  segmentation artifact is invariant — which is what we observe.
- **Threshold & smoothing (A2).** Higher moving-threshold raises displacement via speed (86→118 in as
  thr ×0.75→×1.5) while duration stays pinned by `min_bout`; smaller smoothing shortens the base run
  (dur median 1.21→0.67 s at smooth 7→1) — the floor timescale is set by the 1 s speed window + median
  smoothing, not biology.

## Mapping to the prespecified interpretations

| Interpretation | Supported? | Evidence |
|---|---|---|
| 1 Segmentation artifact | **YES (primary)** | scale = min_bout×speed (A5); CV manufactured (A2/A3); universal (A11) |
| 2 Ballistic locomotor primitive | **YES (true structure)** | ~straight (A8), ~constant speed, near-memoryless hazard k≈1.1 (A4) |
| 3 Characteristic run duration | **NO — falsified** | hazard flat; only 'breakpoint' = 1.3 s speed-window; scale tracks min_bout |
| 4 Long journeys fragmented by pauses | **YES** | 99 % become multi-leg trips at 5 s merge; paddock-scale at 30 s (A6) |
| 5 Decision-point pauses | **PARTIAL — plausible** | ~64° reorientation across pauses vs 16° within (A7); full landmark/social test deferred |

## Definitions

- **Movement segment / bout:** maximal run of consecutive samples with smoothed speed
  $v_i > v_{\min}$ and inter-sample gap $\le$ `max_gap_s`; retained iff duration
  $T \ge$ `min_bout_s`, $\ge 2$ samples, net displacement $d \ge$ `min_disp_in`.
- **Duration** $T = t_{\text{end}}-t_{\text{start}}$ (s). **Net displacement** $d=\lVert\mathbf{x}_{\text{end}}-\mathbf{x}_{\text{start}}\rVert$ (in). **Path** $\ell=\sum\lVert\Delta\mathbf{x}\rVert$ on smoothed positions. **Straightness** $s=\ell/d\ge1$. **Speed** $v=d/T$.
- **CV** $=\sigma/\mu$; low CV + mean≈median = characteristic/capped; high CV = broad/heavy.
- **Mode:** peak of a fixed-width histogram (0.5 s duration, 10 in displacement).
- **Survival** $S(t)=P(T>t)$ (Kaplan–Meier, discrete 0.25 s grid). **Termination hazard**
  $h(t)=P(T\in[t,t{+}\Delta)\mid T\ge t)$ = (# ending in bin)/(# at risk). Constant $h$ ⇒ exponential
  (memoryless); increasing $h$ ⇒ fatigue/capacity; a reproducible step ⇒ characteristic scale.
- **Model selection:** MLE log-likelihood, $\text{AIC}=2k-2\ln L$, $\text{BIC}=k\ln n-2\ln L$ (lower
  better); left-truncated likelihoods at $a=\min T$. Families: exponential, gamma, Weibull, lognormal,
  piecewise-constant hazard.
- **`pause_merge_s` (trip):** a non-moving stretch shorter than this and free of a >`max_gap_s` dropout
  is BRIDGED, merging run–pause–run into one trip. Production = 0.
- **Turn angle across a pause:** $|\angle(\hat{\mathbf u}_{\text{next}}) - \angle(\hat{\mathbf u}_{\text{prev}})|$ wrapped to $[0,180°]$, run heading = end−start vector.
- **Ballisticity jitter null:** straight/curved runs simulated at the observed speed & sample rate with
  per-axis Gaussian noise $\sigma\approx5$ in (WISER stationary residual), same rolling-median smoothing;
  gives the straightness expected from localization noise alone.

## Coverage & limits

Done: A1 audit, A2 sensitivity surface, A3 left-truncation, A4 hazard + model comparison, A5
scale-vs-filter, A6 trips, A8 jitter null, A10 distributions, A11 stability. **Partial:** A7 (turn-angle
across pauses done; landmark/social decision-point structure deferred). **Deferred:** A9 (reuse-vs-length
matched for sample size — a secondary refinement of the earlier "mid-length routes most reused" claim; it
does not affect this verdict). Not verdict-critical items are flagged, not silently skipped.

Method caveats: scipy absent → hazard/MLE/model-comparison in numpy (truncated-gamma normalization
approximated; exponential/Weibull/lognormal exact); durations left-censored at ~2 samples (~0.13–0.4 s)
even at min_bout 0, so the true un-truncated median (0.54 s) is an upper bound on the real primitive
timescale; inch frame unverified.

## Consequence for the prior report
The `bout_length_report.md` conclusion ("fixed-length capacity ~4 s / ~8 ft") should be **read as a
property of the 3 s-minimum contiguous-run segmentation, not a biological capacity.** The corrected
statement: *rats move in ballistic, ~straight, ~constant-speed (~25 in/s) primitives with a
near-memoryless termination hazard, separated by reorientation pauses, that compose into longer
paddock-scale multi-stop trips; there is no intrinsic ~4 s run limit.*

## Outputs
`tables/` — segmentation_audit, parameter_sensitivity, scale_vs_minbout(+fits), duration_hazard,
hazard_model_comparison, distribution_model_comparison, trip_merging_results, pause_transition_results,
ballisticity_noise_null, animal_night_stability. `plots/` — duration/displacement_by_segmentation_parameters,
duration_mode_vs_minimum_duration, displacement_mode_vs_filter_prediction, survival_and_hazard,
bout_vs_trip_distributions, pause_turn_angle, ballisticity_real_vs_jitter_null, cross_animal_night_stability.
