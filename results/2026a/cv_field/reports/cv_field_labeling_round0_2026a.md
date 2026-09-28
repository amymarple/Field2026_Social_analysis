# cv_field labeling round 0 — 2026a

- **direction:** cv_field (whole-field CH01-CH04)  ·  **channels:** CH03, CH04
- **selection method:** diversity  ·  **budget:** 40  ·  **selected:** 40
- **pool size:** 323 candidate frames  ·  **embed backend:** dino
- **K (silhouette):** 3  ·  **seed weights:** (none — cold start)

## Definitions

- **budget B** — number of frames selected this round for hand-labeling (count).
- **medoid** — the most-central real frame of a k-means cluster (a typical exemplar).
- **farthest-point coverage** — greedy k-center pick maximizing min-distance to the already-covered set (fills rare/edge regimes).
- **K (silhouette)** — number of k-means clusters chosen by maximizing the mean silhouette (robust on the L2-normalized embedding, where a likelihood BIC would over-segment).
- **uncertainty u in [0,1]** — max(confidence-margin about tau, count-instability under horizontal-flip TTA); higher = the detector is less sure.
- **acquisition a(f|A) = u^gamma · d(f,A)** — uncertainty-weighted k-center: selects frames that are both uncertain and far (min Euclidean distance) from the labeled set A in the L2-normalized embedding.

## Falsification guard

- single-Gaussian BIC -37501 vs k-means BIC -30981 (K=3); smooth model competitive: True.
- Clusters here are a **labeling heuristic only**, never a claim of behavioral discreteness.

## Coverage figure

![coverage](../figures/cv_field_round0_coverage_2026a.png)

## Whole-field measurement caveats (carry on every downstream number)

- scope is night-IR only (21:00–04:20); CH01/CH02 daytime color is corrupt and excluded.
- counts are a LOWER BOUND (`visible_count`): wall-edge blind band + huddle occlude animals.
- NO cross-camera identity yet (animal_id = <camera>:<track_id>) — no whole-field per-animal or cross-camera-headcount claims.
