# Trajectory stereotypy, stabilization & inter-animal correlation — Phase A report

**Generated (UTC):** 2026-07-07T16:28:09.709948  
**Commit:** `9226f0910399c5806c13c1c7ffa41398f0adc4ff`  
**Nights:** 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05  
**Animals:** Siesta, Hypnos, Nox, Sen, Dormi  
**Frame:** inches, UNVERIFIED offset origin (no georeference) — no directional claims  
**Jitter floor:** ~7 in documented (p95 ~15 in; measured stationary p50 3.39 in); occupancy bin 8 in (≥ floor)  

> Phase A builds the core quantitative evidence and the shared-road controls. Route-motif shape clustering (DTW/Fréchet) and leader-follower lag are **Phase B** (deferred). Every claim below is exploratory/candidate and classified as behavioral / measurement-artifact / mixed / lower-bound.

## Headline answers

### 1. Do trajectories become stereotyped / stabilize from 06-28 → 07-05?

- Mean similarity-to-late-reference went from **0.14** (first night) to **0.96** (last night); night-to-night reproducibility is in `stabilization_metrics.csv` and `plots/stabilization.png`.
- Per-animal stabilization-night estimate (first plateau at ≥90% of own max): {'Siesta': '2026-07-04', 'Hypnos': '2026-06-29', 'Nox': '2026-07-02', 'Sen': '2026-07-04', 'Dormi': '2026-07-04'}.
- **Caution:** occupancy similarity across nights is inflated by shared shelter/rest use and by the shared road; a rising curve is *consistent with* stabilization but is **not** proof of individual route memory (see §2–3). Wet nights (06-30/07-01/07-04) can depress similarity via UWB dropout, not behavior — though here `gap_frac` stays low (<1.5%) on all nights, so the aggregate curve is not dropout-driven. Night **07-05 is truncated** (backup ended ~07-05 23:30 EDT; ~25% fewer fixes) — treat its point cautiously.

### 2. Are stabilized routes shared across animals, or animal-specific?

- **Raw** inter-animal occupancy cosine (mean over 10 pairs): **0.90** (high). ROI-transition structure is near-identical too (edge cosine **0.95**).
- After dividing out the pooled shared-corridor 'road', residual **Pearson correlation collapses to -0.01** (residual cosine 0.86 is inflated because residual maps are non-negative — read the **correlation**, not the cosine).
- **Animal-label permutation:** 0/10 pairs are MORE similar than the shared-pool null (z>2); 4/10 are LESS similar (z<-2). The below-null animal(s) — **Dormi** — use space somewhat differently from the group (a weak *individual*-preference signal). Most pairs are no more similar than random identity assignment ⇒ their similarity is a **shared-road** effect, not a pairwise bond.
- Interpretation: near-zero residual correlation + most pairs at/below the permutation null ⇒ stabilized space-use is **mostly SHARED (environment-driven)**, with only a weak individual signature. Per-animal residual/self-concentration is in `residual_individual_summary.csv`.

### 3. Are pairwise trajectories correlated in real time beyond shuffled controls?

- circular-shift null: 10/10 pairs beat it on proximity and 10/10 on xy-correlation (z>2); but the day-shuffle null (which keeps each animal's diurnal/spatial habit) is beaten by only 0/10 pairs on proximity and 2/10 (marginal) on xy-correlation (`shuffled_controls.csv`, `plots/time_coupling_controls.png`).
- Read: real-time synchrony **exists** above the strict circular-shift null (all pairs), but it is **uniform across pairs and largely explained by shared diurnal/environmental structure** — the day-shuffle null (which preserves that structure) is beaten by far fewer pairs. No standout dyad ⇒ this is common-drive/shared-road, **not** specific social following. Fine following/lead-lag is Phase B; 07-04 fireworks excluded.

## Separating the three explanations

| Explanation | Phase-A evidence | Verdict |
|---|---|---|
| **Shared road / environment** | pooled corridor map; residual Pearson -0.01; edge cosine 0.95; most label-perm pairs ≈ null | **primary driver** |
| Individual route habit | weak: only Dormi below the label-perm null; residual concentration uniform | weak / candidate |
| Social real-time coupling | uniform across pairs; attenuates under the day-shuffle null | not supported as *specific* following |

## What to trust most

1. **`pooled_corridor.png` + the residual-correlation collapse (to ~0)** — the most robust result; a within-frame comparison immune to the unverified georeference.
2. **`coverage_summary.csv` gap/anchor columns** — read every night's result against its dropout; wet-night dips are likely sensor, not behavior.
3. **Time-coupling z-scores vs the circular-shift null** — trust these over the raw proximity numbers (raw proximity is inflated by shared road + diurnal rhythm).

## What Phase A CANNOT support

- Any **directional/physical** route claim (wall-following, shelter→food geometry) — the inch frame is unverified.
- **Memory** per se — WISER shows spatial reuse, not its cognitive cause; equal-looking reuse arises from a shared road.
- Sub-jitter route shape or true path length (jitter-inflated). Route-motif shape is Phase B.
- Fine (<1 m) proximity/following — below the jitter floor; 07-04 fireworks excluded.
- The **top ROI-transition 'edges' (house↔food) are an artifact**: `food_1`/`food_2` sit inside `house_1`/`house_2` in the inch frame, so those edges are jitter flips between co-located labels, not travel. Trust the house↔house / house↔refuge edges as real routes.

## Next analysis (Phase B, after review)

- DTW/Fréchet route-motif clustering on movement bouts (validated vs the displacement-matched jitter null) → repeated motifs, users, days, frequency-over-time.
- Leader-follower lead/lag (the `following_*` suite) on non-fireworks nights.
- If shared-road dominates: quantify **gradual corridor emergence** (trampled-road) per night and test whether residual individual preference strengthens over days.

## Definitions

Units: **inches** (WISER native, UNVERIFIED offset frame; no directional/physical claims). For an
animal $a$ on a night, $H_a\in\mathbb{R}^{G}$ = its occupancy histogram over $G$ fixed spatial bins
(bin side $\ge$ jitter floor); $\tilde H$ = a light 3×3 box-blur of $H$ (a smoothed path-density map);
$\langle\cdot,\cdot\rangle$ = dot product, $\lVert\cdot\rVert$ = L2 norm.

### Occupancy histogram + path-density
$H_a[b]=\#\{$ valid fixes of $a$ in bin $b\}$ over a shared extent; the **path-density map** is
$\tilde H_a$ (box-blurred). **Text:** where the animal spent time; bin side $\ge$ ~7 in jitter floor
so bins are above localization noise.

### Occupancy similarity (cosine, Pearson)
$$ \cos(a,b)=\frac{\langle \tilde H_a,\tilde H_b\rangle}{\lVert \tilde H_a\rVert\,\lVert \tilde H_b\rVert},
   \qquad \rho(a,b)=\text{Pearson}\big(\tilde H_a,\tilde H_b\big) $$
**Text:** overlap of two (blurred, flattened) maps. Range: cosine $[0,1]$, Pearson $[-1,1]$; 1 =
identical spatial use.

### Route (spatial) entropy
$$ p_c=\frac{H_a[c]}{\sum_{c'}H_a[c']},\qquad
   \text{entropy}=-\frac{1}{\ln C}\sum_{c:\,H_a[c]>0} p_c\ln p_c $$
over the $C$ occupied cells. **Text:** normalized Shannon entropy of occupancy; 0 = concentrated in a
few cells, 1 = uniform/dispersed.

### Stabilization: similarity to a late reference
For animal $a$, night $k$: $\text{cos\_prev}=\cos(H_a^{(k)},H_a^{(k-1)})$ and
$\text{cos\_ref}=\cos\!\big(H_a^{(k)},\ \sum_{j\in \text{last }K\text{ nights}}H_a^{(j)}\big)$.
**Text:** cos_prev = night-to-night reproducibility; cos_ref = similarity to the animal's late-window
pattern (rising toward 1 ⇒ space-use stabilizing). Reference $K=2$ nights.

### Pooled shared-corridor map + mask
$H_{\text{pool}}=\sum_{a,\text{nights}}H_a$; corridor mask = cells where $\tilde H_{\text{pool}}$
exceeds its 80th percentile over non-zero cells. **Text:** the common "road" used by all animals; the
mask + its Zhang–Suen skeleton are the corridor structure.

### Residual individual map + concentration
$$ r_a[c]=\frac{\tilde H_a[c]/\sum_{c'}\tilde H_a[c']}{\big(\tilde H_{\text{pool}}[c]/\sum_{c'}\tilde H_{\text{pool}}[c']\big)+\varepsilon},
   \qquad \text{conc}_a=\frac{\sum_{c\in \text{top }5\%} r_a[c]}{\sum_c r_a[c]} $$
**Text:** $r_a$ = the animal's occupancy with the shared-corridor density divided out (≈1 on the
common road, high where it is over-represented). conc ≈ 0.05 = flat (no individual preference beyond
the road); ≫ 0.05 = the animal favours specific off-road cells.

### Inter-animal similarity: raw vs residual
Raw pairwise cosine = $\cos(a,b)$ on $\tilde H$; **residual** pairwise cosine = $\cos$ on $r_a,r_b$.
**Text:** the drop from raw to residual is the share of similarity explained by the shared corridor;
a large drop ⇒ similarity is mostly the common road, not animal-specific overlap.

### Animal-label permutation null $z$
$$ z_{ab}=\frac{\cos(a,b)_{\text{obs}}-\mu_{\text{perm}}}{\sigma_{\text{perm}}} $$
where the null reassigns each animal's per-night maps to random identities (preserving the pool of
night-maps and per-animal counts) and recomputes pairwise cosine. **Text:** tests whether a pair's map
similarity exceeds random identity assignment; $z>2$ ⇒ above chance.

### Real-time coupling + its nulls (2 s grid)
On synchronous 2 s bins: $\text{xy\_corr}$ = mean of Pearson$(x_A,x_B)$ and Pearson$(y_A,y_B)$;
$\text{frac\_within\_r}=\#\{t:\lVert\mathbf{x}_A(t)-\mathbf{x}_B(t)\rVert<39.37\text{ in (1 m)}\}/\#\text{bins}$.
Two nulls give $z=(\text{obs}-\mu)/\sigma$: **circular-shift** rolls $B$ by a random offset (breaks
real-time alignment, keeps each animal's habit); **day-shuffle** pairs $A$'s night with $B$'s *other*
nights (breaks synchrony, keeps within-night structure). **Text:** proximity radius 1 m is kept
$\ge$ jitter floor; $z>2$ ⇒ coupling beats that null.

### Jitter floor / moving threshold
Jitter floor ~7 in (documented stationary median; p95 ~15 in) — bin side and proximity radius are set
$\ge$ it. Moving threshold = p99 of the stationary baseline smoothed speed (in/s).

## Outputs

`coverage_summary.csv` · `cleaning_log.md` · `stabilization_metrics.csv` · `pooled_corridor_*.npy` · `residual_individual_summary.csv` · `pairwise_similarity_matrix.csv` · `shuffled_controls.csv` · `label_permutation_null.csv` · `transition_edge_similarity.csv` · `run_manifest.json` · `plots/` · `residual_individual_maps/`
