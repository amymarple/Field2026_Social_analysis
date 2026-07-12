# Route motifs — stereotyped movement patterns (Phase B report)

**Generated (UTC):** 2026-07-11T21:45:43.602910  
**Commit:** `384d1d019d914c19daa3411b2397adeca5e29812`  
**Nights:** 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08, 2026-07-09, 2026-07-10  
**Animals:** Siesta, Hypnos, Nox, Sen, Dormi  
**Bouts:** 1692 (displacement > 15 in); **253 motifs** at threshold 21.0 in (3.0× jitter floor)  
**Frame:** inches, UNVERIFIED — motifs internally consistent, no physical claims  

## Verdict: **Stereotyped routes are present but SHARED** — recurring motifs are common corridors used by several animals; no individual signal beyond the null.

> Confirms the ORIGINAL question (do trajectories become stereotyped route motifs?) at the path-shape level — complementary to Phase A's occupancy stabilization. Bouts require displacement > jitter, so a motif is a real repeated route, not a jitter artifact.

## 1. Are there recurring route motifs? (recurrence — threshold-robust)

- **Recurrence** = fraction of route bouts that have a near-identical partner elsewhere (mean-pointwise route distance ≤ threshold). At **21 in (3.0× jitter)**: **97%** of bouts recur. Full curve: 10 in → 83%, 21 in → 97%, 42 in → 100%.
- Compact (non-chaining, leader) clustering gives **253 motifs** from 1692 bouts; the **top 10 hold 25%** — a few routes dominate. **109 SHARED** (≥3 animals), **144 individual** (1–2). Fréchet metric → 579 motifs (same order). (`motif_catalog.csv`, `plots/top_motifs.png`, `plots/all_bouts_by_motif.png`.)
- So trajectories ARE stereotyped: a large fraction of routes recur, and movement concentrates in a few dominant path shapes.
- **Leakage caveat:** recurrence uses a **globally-pooled** nearest-neighbour dictionary — every other bout on every night (including *future* nights) is an eligible partner, with no same-animal / same-night / adjacent-bout exclusion — so it is an **upper bound** and is *retrospective*, not a leakage-controlled or out-of-sample result. See the route-vocabulary validation study for held-out compression + generalization.

### Top motifs

| motif | bouts | rats | nights | endpoints (provisional) | shared? |
|---|---|---|---|---|---|
| 0 | 51 | 5 | 13 | open→open | yes |
| 1 | 50 | 5 | 13 | open→open | yes |
| 2 | 49 | 5 | 13 | open→open | yes |
| 3 | 45 | 5 | 13 | open→open | yes |
| 4 | 45 | 5 | 12 | open→open | yes |
| 5 | 44 | 5 | 11 | open→open | yes |
| 6 | 40 | 5 | 12 | open→open | yes |
| 7 | 39 | 5 | 12 | open→open | yes |

## 2. Individual route memory or shared corridors?

- Per animal, nearest-neighbour route distance to its OWN other-day bouts (`self_nn`) vs to OTHER animals' bouts (`other_nn`), in `individual_route_memory.csv`. Across animals **other_nn ≈ 9 in < self_nn ≈ 15 in** — an animal's *nearest* route is typically **another animal's**, not its own past route. **Shared corridors dominate.**
- But vs the **animal-label permutation null**: the gap g = mean(other_nn) − mean(self_nn) = -5.25 in (negative ⇒ shared) vs null -5.58 ± 0.18 ⇒ **z = 1.84**, which did NOT reach the prespecified z>2 threshold: this analysis does **not** establish an individual-specific route residual — shared corridors dominate (g < 0). Per-animal CSV column `self_minus_other_in` = self − other = −g_i (the negation of g) — do not conflate the two directions.
- Matches Phase A (shared-road dominant; a faint individual component). `plots/individual_route_memory.png`.

## 3. Does stereotypy strengthen over days? (per night)

Mean per-animal motif entropy and top-motif fraction by night (`motif_stereotypy_by_animal_night.csv`):

| night | recurrence (NN≤21in) | mean motif entropy | mean top-motif frac | mean bouts |
|---|---|---|---|---|
| 2026-06-28 | 98% | 0.98 | 0.13 | 22 |
| 2026-06-29 | 93% | 0.78 | 0.31 | 18 |
| 2026-06-30 | 97% | 0.99 | 0.07 | 29 |
| 2026-07-01 | 99% | 0.99 | 0.12 | 15 |
| 2026-07-02 | 97% | 0.97 | 0.11 | 31 |
| 2026-07-03 | 98% | 0.97 | 0.14 | 26 |
| 2026-07-04 | 99% | 0.98 | 0.12 | 27 |
| 2026-07-05 | 99% | 0.99 | 0.10 | 23 |
| 2026-07-06 | 98% | 0.98 | 0.09 | 27 |
| 2026-07-07 | 98% | 0.97 | 0.10 | 33 |
| 2026-07-08 | 98% | 0.98 | 0.09 | 35 |
| 2026-07-09 | 97% | 0.98 | 0.08 | 38 |
| 2026-07-10 | 92% | 0.99 | 0.11 | 30 |

- **Stereotypy is present from night 1, NOT developing.** Recurrence is already **98%** on the release night (06-28) and stays **92–99%** every night — the route repertoire is set by the paddock geometry immediately, not learned over days. (Motif entropy fell for 0 animals, rose for 1 first-vs-last; `stereotypy_emergence.csv`.)
- **Caveat (global-dictionary leakage):** these per-night recurrence numbers use the pooled dictionary above, so 'present from night 1' is **retrospective** — a night-1 bout may match a partner on a *later* night. Whether the repertoire is genuinely available on night 1 *without* future data is tested directly by the first-night-closure analysis in the route-vocabulary validation study (not asserted here).
- Motif entropy stays **high (~0.98)**: animals use a **diverse set of recurring routes**, not one obsessive path — many distinct shared motifs, each reused, rather than a single stereotyped loop. (06-29 is the one lower-entropy night — hotter, more concentrated use.)

## 4. When in the night, and which night? (per-hour / per-day)

Night window = **21:00→04:00** (data-driven active period from `circadian_rest`: activity peaks 21:00, elevated to ~04:00, troughs 07:00).

**Per clock-hour (pooled over nights, `motif_by_hour.csv`):**

| hour (EDT) | bouts/animal | n motifs | recurrence |
|---|---|---|---|
| 00:00 | 32.8 | 82 | 99% |
| 01:00 | 27.0 | 77 | 99% |
| 02:00 | 42.2 | 100 | 97% |
| 03:00 | 50.0 | 111 | 97% |
| 21:00 | 90.0 | 152 | 97% |
| 22:00 | 56.2 | 123 | 97% |
| 23:00 | 40.2 | 93 | 97% |

- **Route activity concentrates at dusk onset:** the **21:00 hour carries the most bouts (~90/animal)**, tapering overnight — matching the circadian 21:00 activity peak. **Route reuse (recurrence) stays ~96–99% at every hour**: whenever they move, they move on established routes; the stereotypy is not confined to one part of the night.

**Per night (group, `motif_by_day.csv`):**

| night | bouts | rats | recurrence | dominant-motif share | group entropy |
|---|---|---|---|---|---|
| 2026-06-28 | 108 | 5 | 98% | 10% | 0.94 |
| 2026-06-29 | 89 | 5 | 93% | 8% | 0.95 |
| 2026-06-30 | 146 | 5 | 97% | 4% | 0.96 |
| 2026-07-01 | 74 | 5 | 99% | 5% | 0.96 |
| 2026-07-02 | 154 | 5 | 97% | 6% | 0.94 |
| 2026-07-03 | 129 | 5 | 98% | 6% | 0.95 |
| 2026-07-04 | 135 | 5 | 99% | 5% | 0.95 |
| 2026-07-05 | 115 | 5 | 99% | 6% | 0.95 |
| 2026-07-06 | 133 | 5 | 98% | 6% | 0.94 |
| 2026-07-07 | 164 | 5 | 98% | 6% | 0.93 |
| 2026-07-08 | 175 | 5 | 98% | 5% | 0.96 |
| 2026-07-09 | 150 | 4 | 97% | 5% | 0.96 |
| 2026-07-10 | 120 | 4 | 92% | 3% | 0.97 |

- **Recurrence is high (92–99%) every night** and **no single motif dominates** (top-motif share only ~3–10%): the group reuses a **broad repertoire** of established routes, not one corridor. Cohort is **5 rats through the 07-08 night, 4 from 07-09** (Hypnos implant dropped 07-09 03:35 — `apply_tag_cutoffs`). `plots/motif_by_hour_and_day.png`.
- **Covariate flags (not exclusions):** the **south barn light** is on from the **07-09 night** onward (a directional night-light that could bias routes — FIELD_OBSERVATIONS Day 12); **refuge_4 burrow UWB dropout** on 07-03→07-06 nights; **07-04 fireworks**. Read 07-09/07-10 under the barn-light caveat.

## What this confirms / cannot say

- **Confirms:** recurring, location-anchored route motifs exist and dominate movement (a few routes carry most bouts) — trajectories ARE stereotyped at the path level.
- **On individual vs shared:** decided by the permutation z above — not asserted.
- **Cannot:** call it spatial *memory* (WISER shows route reuse, not its cognitive cause); resolve sub-jitter path detail; or place motifs in the physical frame (no georeference). Endpoint ROI labels are provisional (food ROIs sit inside houses).
- **UNDONE — roadway camera audit:** the field observation is that the rats have worn a **visible flattened-grass 'road'** and mostly travel along it. The ~97% route recurrence here is consistent with that, but **whether these WISER motifs geometrically track the physical trampled path has NOT been verified against camera footage** (needs the pixel↔field georeference / CH01–CH04 overlay). Marked as a follow-up, not claimed.

## Definitions

Units: **inches** (WISER native, UNVERIFIED offset frame). $B$ = set of route bouts;
$\mathbf{p}_i \in \mathbb{R}^{L\times 2}$ = bout $i$'s arc-length-resampled path ($L$ points,
$\mathbf{p}_i^{(k)}$ its $k$-th point); $s(i)$ = the animal of bout $i$; $n(i)$ = its night;
$\mathbb{1}[\cdot]$ = indicator (1 if true, else 0).

### Movement bout + displacement filter
A bout is a maximal run of consecutive 1 s grid samples with smoothed speed $v>v_{\min}$ (moving),
inter-sample gap $\le 2$ s, duration $\ge 3$ s, kept only if net displacement
$\lVert \mathbf{p}_i^{(L)}-\mathbf{p}_i^{(1)}\rVert_2 \ge d_{\min}$.
**Text:** one directed travel segment above the noise floor. $d_{\min}=15$ in (> the ~7 in jitter
floor, so a bout's shape is a real route, not localization noise); $v_{\min}$ = p99 of the stationary
baseline smoothed speed (in/s). Range of a bout: any path with end-to-end distance $\ge 15$ in.

### Arc-length resampling
Each bout's path is resampled to $L$ points **equally spaced by arc length** (not time), so index $k$
corresponds across bouts and the distance below is **speed-invariant**.

### Route distance $D_{ij}$ (mean-pointwise; primary)
$$ D_{ij} = \frac{1}{L}\sum_{k=1}^{L}\big\lVert \mathbf{p}_i^{(k)}-\mathbf{p}_j^{(k)}\big\rVert_2 $$
**Text:** mean point-to-point separation between two aligned routes. Units: inches. Range
$[0,\infty)$; 0 = identical route, large = different routes. Robustness metrics (same inputs):
Fréchet $D^{F}_{ij}=\max_k\lVert \mathbf{p}_i^{(k)}-\mathbf{p}_j^{(k)}\rVert$; Hausdorff
$D^{H}_{ij}=\max\!\big(\max_a\min_b \lVert a-b\rVert,\ \max_b\min_a \lVert a-b\rVert\big)$ over the two
point sets; DTW = warp-tolerant alignment cost.

### Recurrence $R(\tau)$
$$ R(\tau)=\frac{1}{|B|}\sum_{i\in B}\mathbb{1}\!\Big[\min_{j\neq i}D_{ij}\le\tau\Big] $$
**Text:** fraction of route bouts that have a near-identical partner within $\tau$ inches. Range
$[0,1]$; high = strongly stereotyped (routes repeat). Reported at $\tau\in\{1.5,3,6\}\times$ jitter
floor.

### Motif (leader clustering) + threshold $\theta$
Greedy leader clustering: repeatedly take the still-unassigned bout with the most neighbours within
$\theta$ and assign it + all unassigned $j$ with $D_{ij}\le\theta$ to a new motif.
**Text:** a motif is a compact bundle of near-identical routes (every member within $\theta$ of the
leader; non-chaining, unlike single-linkage). $\theta = 3\times$ jitter floor ($\approx 21$ in). A
motif is **shared** if used by $\ge 3$ animals, else **individual**.

### Motif entropy $H$ and top-motif fraction (per animal-night)
$$ q_m=\frac{\#\{\text{bouts in motif } m\}}{\#\{\text{bouts}\}},\qquad
   H=-\frac{1}{\ln M}\sum_{m=1}^{M} q_m\ln q_m,\qquad \text{top-motif frac}=\max_m q_m $$
**Text:** $H$ = normalized Shannon entropy of one animal-night's bouts over the $M$ motifs it uses.
Range $[0,1]$; $H{=}0$ = all bouts in one motif (one obsessive route), $H{\to}1$ = spread uniformly
over many motifs (diverse repertoire).

### Individual-vs-shared route memory + permutation null $z$
For bout $i$: self-NN $u_i=\min_{j:\,s(j)=s(i),\,n(j)\neq n(i)}D_{ij}$ (nearest of the animal's OWN
other-day routes); other-NN $o_i=\min_{j:\,s(j)\neq s(i)}D_{ij}$ (nearest OTHER animal's route). Gap
$$ g=\overline{o}-\overline{u},\qquad
   z=\frac{g_{\text{obs}}-\mu_{\text{perm}}}{\sigma_{\text{perm}}} $$
where the null recomputes $g$ over many random permutations of the animal labels $s(\cdot)$.
**Text:** $g>0$ ⇒ an animal's own routes are more similar than others' (individual); $g<0$ ⇒ others'
routes are nearer (shared). $z>2$ ⇒ own-route self-similarity exceeds the label-shuffle null.

### Jitter floor
~7 in (documented stationary median; p95 ~15 in). The scale below which position differences are
localization noise, not movement; $d_{\min}$, $\tau$, and $\theta$ are all set as multiples of it.

## Outputs

`route_bouts.csv` · `motif_catalog.csv` · `motif_stereotypy_by_animal_night.csv` · `recurrence_by_night.csv` · `motif_by_hour.csv` · `motif_by_day.csv` · `individual_route_memory.csv` · `stereotypy_emergence.csv` · `run_manifest.json` · `plots/` (top_motifs, all_bouts_by_motif, stereotypy_over_days, individual_route_memory, motif_by_hour_and_day)
