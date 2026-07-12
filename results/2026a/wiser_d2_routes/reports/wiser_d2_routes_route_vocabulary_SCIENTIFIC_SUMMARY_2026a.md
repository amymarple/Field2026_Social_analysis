# Route / motif direction — scientific summary

**Status: ⚠️ candidate / provisional — nothing here is confirmed or publishable.** WISER UWB only
(~7 in jitter floor; the position frame is an UNVERIFIED inch offset, so every statement is
topological / relative — no metric, directional, or physical-road claim). 5 rats (4 from the 07-09
night), nights 2026-06-28 → 07-10, active window 21:00–04:00. Generated 2026-07-12.

## Biological picture

At night the rats travel on a **reused set of routes** — when an animal moves, it tends to retrace
paths it or another animal has taken before. But that reuse is **not** a repertoire of distinctive
route *shapes*, and it is **not** individual route memory. Almost all of the structure is carried by
**where each trip starts and ends**: routes are essentially straight travel between a shared, recurring
set of **open-field waypoints**, and those waypoints are **not** the mapped shelters, feeders, or
refuges. The picture is the same whether routes are cut into short bouts or longer merged episodes. The
one dominant limitation is sensor resolution: WISER's ~7 in jitter cannot resolve the finer,
decision-level structure that would separate a genuine route repertoire from repeated geometry — that
question needs the CV pipeline.

## Three main findings

**1. Routes recur, but there is no discrete or shared route-shape vocabulary.** Learning a dictionary
of route shapes on some nights and freezing it does reconstruct later routes — but there is no finite
"right number" of route types. A minimum-description-length comparison never prefers a compact discrete
dictionary: the best discrete code (~411 kbits at 128 prototypes) is *longer* than a smooth
low-dimensional continuous code (~271 kbits), and the route set does not close (out-of-sample coverage
rises from **39%** with a one-night dictionary to only ~**88%** after training on most nights). So
routes are stereotyped — but the widely-quoted "97% recurrence" is a **pooled upper bound** that lets
each route borrow partners from future nights; held-out, recurrence is materially lower. The negative
("not a discrete, shared route vocabulary") is the promotable core here, and it survived an independent
adversarial re-analysis. Scope: established only *above the ~7 in jitter floor* and for WISER-defined
units.

**2. Movement is endpoint-dominated, and the endpoints are open-field waypoints — not resource sites.**
A straight line between each route's own start and end reconstructs the real route to **~7.88 in** —
essentially the jitter floor, and *better* than a 176-prototype route-shape dictionary (**15.72 in**);
a 4-dimensional continuous summary (≈ the two endpoints) captures routes to ~**4 in**. So the route
"graph" is carried by its endpoints, not by path shape. And those endpoints are overwhelmingly **open
field**: only **~3%** fall in any mapped ROI (house/food/water/refuge), **94%** of routes run
open→open, and open endpoints sit a median **~55 in** from the nearest landmark. The endpoints still
cluster at recurring spots — a real endpoint graph exists — but its nodes are un-labelled field
waypoints (consistent with edge/perimeter corridors), not resources. Caveat: this is night travel
(the rats rest at the houses by day), a topological statement in an unverified frame, and the mapped
ROIs are small.

**3. The result is the same at both unit scales, and what is shared across animals is that endpoint
graph.** The identical analysis on **1,692** short bouts and on **1,609** pause-merged episodes gives
an identical verdict and identical endpoint dominance (endpoint share **0.99** vs **0.98**; the
straight chord beats the shape dictionary at both scales). Across animals, a dictionary built from
other animals transfers to a held-out animal about as well as its own — yet the endpoint chord
(~**9 in**) beats every dictionary (~**20 in**) for all animals. So what generalises across animals is
the **shared endpoint graph (common locations)**, not a shared path-shape vocabulary.

## Candidate interpretation

There is a **small, reusable, continuous** shape component beyond the straight chord: in an
endpoint-registered frame, a frozen shape dictionary (**5.81 in**) beats both the straight segment
(**7.88 in**) and a matched random-wiggle null (**7.58 in**). But this ~2 in improvement is **below the
~7 in jitter floor** — a matched-null differential, not a resolvable path shape, and nowhere near a
discrete repertoire. The cross-animal dictionary-transfer in finding 3 is likewise **candidate**: its
margins are within run-to-run sampling noise and every held-out night is a late, regime-disturbed
night.

## No longer supported

- **Individual route memory.** The earlier "own routes beat the label-shuffle null, z > 2" was a
  mis-statement: **z = 1.84**, which does not reach the pre-specified threshold, and the sign shows
  *shared* routes dominate. No individual route residual is established.
- **"97% of routes recur" as an out-of-sample fact.** That figure pools all nights (including future
  ones) into one dictionary; the leakage-controlled, held-out number is lower and grows with training.

## Unresolved (ranked by impact on the next decision)

1. **The definitive, leg-scale test needs CV.** Whether *decision-to-decision* movement legs form a
   vocabulary cannot be answered with WISER: candidate "reorientation" boundaries at pauses are
   indistinguishable from jitter — a straight *simulated* path produces a **larger** apparent turn at
   pauses (**+20.4°**) than the real data (**+17.9°**), and the effect reverses to **−3.1°** when
   headings are actually resolvable. This is the WISER resolution ceiling.
2. **Open manifold vs finite corridor graph.** Whether the endpoint repertoire keeps growing
   (continuous) or closes into a finite corridor graph is unresolved — the deciding late nights
   coincide with a shelter removal (07-07), a new south night-light (07-09), and the cohort dropping
   5→4 (07-09).
3. **The physical "worn road."** Whether these WISER corridors track the visible trampled-grass path is
   unverified (needs the pixel↔field georeference plus a camera check).

## Next decision

1. **Wait for the CV pipeline** (centroid/pose tracking); re-run the identical route battery on
   CV-resolved legs — the only route to the leg-scale vocabulary question.
2. When CV legs exist, drop them into the same trajectory-unit schema and re-run the segmentation
   comparison (they slot in beside bouts and episodes).
3. Georeference WISER to the camera field frame to test the physical-road correspondence.

## Technical references

- Ledger: `change_log/2026-07-11-route-vocabulary-validation.md`, `change_log/2026-07-11-motif-rerun-per-hour-day.md`.
- Reports: `outputs/route_vocabulary_validation_2026-06-28_to_2026-07-10/original_3s_filtered_bouts/validation_report.md`;
  `…/comparison/comparison_report.md`; `outputs/route_motifs_2026-06-28_to_2026-07-10/route_motifs_report.md`.
- Audits: `outputs/audit/ROUTE_VOCAB_AUDIT_2026-07-11.md`; `decision_boundary_validation/validation_report.md`.
- Status row: `ANALYSIS_STATUS.md` → "Route-vocabulary validation (Stage 1, PROVISIONAL)".

---

## Quantitative appendix — how each finding was quantified

All distances are inches in the WISER native (unverified) frame; a route is arc-length-resampled to
$L=20$ points $\mathbf p^{(1..L)}$; route distance $D(a,b)=\frac1L\sum_k\lVert a_k-b_k\rVert$
(mean-pointwise). "Held-out" = a dictionary is learned on training nights only and scored on other
nights/animals; the jitter floor is ~7 in.

**F1 — no discrete/shared vocabulary (MDL + closure).**
- *Quantity.* $L(K)$ = description length (bits) to encode held-out routes with a $K$-prototype
  dictionary; **novelty** = fraction of held-out routes with no prototype within $\theta=21$ in.
- *Formula.* $L(K)=\underbrace{K\,2L\,b_p}_{\text{dictionary}}+\underbrace{N\log_2 K}_{\text{assignment}}
  +\underbrace{\text{Gaussian residual bits}(\sigma)}_{\text{residual}}$, vs a PCA code that replaces
  the assignment term with $N\!\cdot\!M$ coefficient bits ($b_p=16$, $\sigma=$ jitter floor).
- *Value.* discrete min $=411{,}001$ bits at $K=128$; continuous PCA min $=271{,}538$ bits ($M=4$).
  Held-out coverage (≤21 in) $0.386$ (1-night dictionary, $n_{\text{test}}=1584$) $\to 0.883$ (12-night).
- *Decision rule.* A discrete vocabulary requires a finite-$K$ MDL minimum **shorter** than the
  continuous code AND novelty saturation. Neither holds ⇒ **reject** (verdict C).
- *Sensitivity.* Robust to the coding assumptions except one extreme corner (not load-bearing);
  independently reproduced by a 5-lens adversarial workflow and the measurement auditor.
- *Inference.* No compact discrete code beats a continuous one, and the set never closes ⇒ routes are
  stereotyped but not a discrete/shared vocabulary (above the jitter floor, WISER units).

**F2a — endpoint dominance.**
- *Quantity.* held-out reconstruction error (in) of the **endpoint chord** (straight line between a
  route's own endpoints) vs a route-shape dictionary vs PCA.
- *Value.* chord $E=7.88$; route dictionary $E=15.72$ ($K=176$); PCA $E=4.17$ at $M=4$; endpoint
  share $=(E_{\text{global}}-E_{\text{chord}})/(E_{\text{global}}-E_{\text{best}})$-family metric
  $=0.99$. $N=1692$ units (temporal split).
- *Decision rule.* endpoints dominate if the chord reconstructs $\le$ the shape dictionary and the
  endpoint share $\ge 0.8$. Both hold.
- *Sensitivity.* The chord uses each route's own 4 endpoint coordinates (not parameter-matched) — but
  the MDL and PCA comparisons agree independently.
- *Inference.* Route identity is carried by endpoints, not path shape.

**F2b — endpoints are open field, not landmarks.**
- *Quantity.* fraction of route endpoints assigned to a named ROI (`assign_roi` vs `wiser_rois.json`);
  distance to nearest ROI centre.
- *Value.* **3.1%** at a landmark, **93.8%** open→open, **0.1%** landmark→landmark; open-endpoint
  median distance **55 in**, 61.5% >42 in. $N=3384$ endpoints (1692 bouts); episodes identical (3.0%).
- *Decision rule.* topological ROI membership; "at a landmark" = endpoint inside an ROI polygon.
- *Sensitivity.* jitter (~7 in) cannot explain a 55-in median offset; food folded into houses;
  `refuge_4` (burrow, removed 07-07) flagged.
- *Inference.* Endpoints recur at open-field waypoints, not mapped resources.

**F3 — scale-invariance + shared endpoint graph.**
- *Value.* bouts ($N=1692$) vs pause-merged episodes ($N=1609$): identical verdict C and all 7
  criteria; endpoint share $0.99$ vs $0.98$; chord < dictionary at both. LOAO: $E_{\text{other}}\approx
  E_{\text{own}} < E_{\text{null}}$ (per-animal margins ≈ 1 seed-sd); endpoint chord $E_{\text{endpoint}}
  \approx 9$–$10$ in $\ll$ every dictionary $\approx 20$ in, all 5 animals.
- *Decision rule.* robustness = same verdict + criteria across segmentations; "shared = endpoint graph"
  = the endpoint chord beats every learned dictionary across animals.
- *Inference.* The conclusion does not depend on unit scale; cross-animal sharing is of locations, not
  path shapes (candidate, thin margins).

**Candidate — sub-floor continuous shape.**
- *Value.* pose-normalized (endpoint-registered) shape dictionary $5.81$ in $<$ straight segment $7.88$
  in $<$ matched Brownian-bridge null $7.58$ in; reduction ≈ 2 in $<$ the ~7 in floor.
- *Decision rule.* reusable shape = dictionary beats both the straight segment and the null by ≥0.5 in;
  it does, but the effect is sub-floor ⇒ **candidate**, differential-only.
- *Inference.* A small reusable continuous shape exists but is not a resolvable, discrete repertoire.

**Superseded — individual route memory.**
- *Value.* gap $g=\overline{\text{other\_nn}}-\overline{\text{self\_nn}}=-5.25$ in (negative ⇒ shared);
  permutation $z=1.84$ (threshold $z>2$ **not** reached), $n_{\text{perm}}=500$.
- *Inference.* No individual route residual established; the prior "z>2" statement was false.

**Unresolved — decision boundaries / leg-scale.**
- *Value.* matched pause-turn $+17.9°$ vs a jitter-only null $+20.4°$; $-3.1°$ when both movement flanks
  are well-resolved (≥30 in); changepoint detector 30–77% false-positive, 4–24% sensitive.
- *Inference.* Pause reorientation is not separable from jitter ⇒ decision-to-decision legs cannot be
  validated with WISER; needs CV pose/keypoints.
