# Following structure — stable pairs vs. herd (Phase B report, PER-NIGHT)

**Generated (UTC):** 2026-07-08T01:53:50.745813  
**Commit:** `384d1d019d914c19daa3411b2397adeca5e29812`  
**Nights:** 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-05 (07-04 fireworks excluded: True)  
**Animals:** Siesta, Hypnos, Nox, Sen, Dormi  
**Follow radius:** 24 in (3× jitter floor); lags 1–30 s; heading cos>0.5; 100 shuffles  
**Frame:** inches, UNVERIFIED — 'leader/follower' = temporal order, not geometry  

## Verdict: **Herd / shared-road (promiscuous), NOT stable dyads.** On 7/7 nights a majority of pairs beat their null, and the **top pair changes almost every night** (4 distinct top pairs over 7 nights) — no dyad recurs.


> Reported **per night**, not averaged. This builds on Phase A (co-movement is real: it beat the circular-shift null 10/10 pairs at zero lag). Phase B asks whether that co-movement is carried by **specific, stable pairs** or is **promiscuous** (a shared road / herd). Zero-lag was the anchor; here the score is lag- and heading-aware directional following vs a per-pair circular-shift null.

## Specificity & top pair — per night

Are the significant pairs a concentrated subset (dyads) or spread (herd), and does the same pair recur? (`specificity_by_night.csv`; z-grid `plots/pair_z_by_night.png`.)

| Night | pairs sig (z>2) | score Gini | max score | top pair | top z |
|---|---|---|---|---|---|
| 2026-06-28 | 9/10 | 0.16 | 0.106 | Hypnos–Sen | 19 |
| 2026-06-29 | 10/10 | 0.26 | 0.213 | Nox–Sen | 28 |
| 2026-06-30 | 10/10 | 0.19 | 0.111 | Hypnos–Sen | 13 |
| 2026-07-01 | 7/10 | 0.29 | 0.151 | Siesta–Sen | 17 |
| 2026-07-02 | 8/10 | 0.22 | 0.117 | Siesta–Sen | 16 |
| 2026-07-03 | 9/10 | 0.18 | 0.105 | Hypnos–Sen | 9 |
| 2026-07-05 | 9/10 | 0.15 | 0.132 | Hypnos–Nox | 11 |

Read the **top pair** column top-to-bottom: it reshuffles ⇒ no stable dyad. Gini stays low (spread), and most pairs are significant every night (herd).

## Leadership — per night

For each night, the number of its 4 pairs each animal **led** (higher-scoring direction); the last column is that night's top leader. (`per_night_leadership.csv`; `plots/leadership_by_night.png`.)

| Night | Siesta | Hypnos | Nox | Sen | Dormi | top leader |
|---|---|---|---|---|---|---|
| 2026-06-28 | 2 | 2 | 2 | 3 | 1 | **Sen** (3/4) |
| 2026-06-29 | 0 | 1 | 3 | 4 | 2 | **Sen** (4/4) |
| 2026-06-30 | 2 | 1 | 0 | 4 | 3 | **Sen** (4/4) |
| 2026-07-01 | 3 | 2 | 1 | 3 | 1 | **Siesta** (3/4) |
| 2026-07-02 | 2 | 2 | 1 | 4 | 1 | **Sen** (4/4) |
| 2026-07-03 | 3 | 2 | 1 | 2 | 2 | **Siesta** (3/4) |
| 2026-07-05 | 2 | 1 | 3 | 4 | 0 | **Sen** (4/4) |

- Top leader by night: **Sen** on 5/7 nights. Whether that is *every* night or shifts is visible above — this is the per-night test of the leadership asymmetry, not an average.
- Per-pair leader-consistency (still useful as a summary) is in `leadership_consistency.csv`.

## Pair ranking (context)

- `pair_stability_summary.csv` + `plots/pair_ranking.png`: per-pair mean score and how many of the 7 nights each pair was significant / was the top pair. Consecutive-night rank correlation of the pair vector = **0.11** (≈0 ⇒ reshuffles; a summary of the per-night reshuffling shown in the table above).

### Herd control

- `group_cohesion.csv`: per-night mean pairwise distance + clumped-bin fraction. If the group travels as a herd, every pair's follow score rides on this — a **uniform** significance pattern is the herd/road answer, a **concentrated** one is the dyad answer.

### Key refinement — movement is SEQUENTIAL, not a synchronized herd

- Any given pair is moving **at the same time** only **0.0125** of grid-seconds on average (`simultaneity_summary.csv`) — the rats mostly move **one at a time**. So the co-movement is not side-by-side herd travel; it is **sequential re-use of the same corridor**, with weak lag-following (B walks where A walked, seconds later). This reconciles the video (which reads as 'following') with the shared-road result: a common road used at *different times*, occasionally with one animal trailing another.

## Video bridge

- `top_following_bouts.csv`: the longest **lagged-following** episodes for the top pairs (follower retraces the leader's path within 24 in at the pair's best lag, gap-tolerant), with **local-EDT start times** to line up against the following/parallel episodes observed on video. (48 episodes exported.)
- These are *lagged* (B where A was, seconds later), matching sequential corridor use — not instantaneous side-by-side travel (which is rare here). Confirm active *pursuit* vs. coincidental co-use on the video itself.

## What this can and cannot say

- **Can:** whether co-movement is concentrated vs spread, whether the pattern recurs across nights, and who tends to lead — all above each animal's own habit (circular-shift null).
- **Cannot:** prove social *attraction* vs. shared-corridor co-use from WISER alone (a stable dyad could still be two animals that independently prefer the same route at the same time); resolve <24 in geometry (jitter); or place any of it in the physical frame (no georeference).
- n=5 → 10 undirected pairs: gross structure only. 07-04 excluded; 07-03/07-05 carry the refuge_4 dropout (moving bouts less affected than resting).

## Definitions

Units: **inches** (WISER native, UNVERIFIED offset frame; a "leader" is temporal order, not
geometry). Positions are on a common **1 s grid**, positions smoothed by a 5 s rolling median;
$\mathbf{x}_A(t)$ = animal $A$'s position at second $t$; $\hat{\mathbf u}_A(t)$ = its unit heading
(velocity / speed); $\text{mov}_A(t)$ = moving mask ($\text{speed}>v_{\min}$). $\#\{\cdot\}$ = count.

### Moving threshold $v_{\min}$ and follow radius $R$
$v_{\min}$ = p99 of the stationary baseline **grid** speed (in/s) — the speed below which grid motion
is jitter. $R=\max(3\times\text{jitter floor},\,24)=24$ in. **Text:** $R$ is the spatial tolerance
for "same place", set to $3\times$ the ~7 in jitter floor so following is above localization noise.

### Follow score $f_{A\to B}(\ell)$ (directional, lag $\ell$)
$$ f_{A\to B}(\ell)=\frac{\#\{t:\ \text{mov}_A(t)\wedge \text{mov}_B(t{+}\ell)\wedge
   \lVert \mathbf{x}_B(t{+}\ell)-\mathbf{x}_A(t)\rVert_2<R\wedge
   \hat{\mathbf u}_A(t)\cdot\hat{\mathbf u}_B(t{+}\ell)>c\}}
   {\#\{t:\ \text{mov}_A(t)\wedge \text{mov}_B(t{+}\ell)\}} $$
where $c=0.5$ = heading-cosine cutoff, $\ell$ = lag in seconds. **Text:** of the seconds both animals
move, the fraction where follower $B$ (read at $t{+}\ell$) is within $R$ of where leader $A$ was at
$t$, headings aligned. Range $[0,1]$; the **denominator is both-moving seconds only**. Peak score
$f^{\ast}_{A\to B}=\max_{\ell\in[1,30]}f_{A\to B}(\ell)$; best lag = the $\ell$ achieving it.

### Circular-shift null $z$ (per ordered pair)
$$ z_{A\to B}=\frac{f^{\ast}_{A\to B}-\mu_{\text{null}}}{\sigma_{\text{null}}},\qquad
   \text{null}=\{\,f^{\ast}\ \text{after rolling }B\text{'s whole track by a random }
   \delta\in[5,20]\ \text{min}\,\} $$
**Text:** the shift preserves each animal's own activity/route habit and the shared road but destroys
real-time alignment; a pair's following is credible when $z>2$. Computed over 100 shuffles.

### Undirected pair score and leader
For unordered pair $\{A,B\}$ the score is $\max(f^{\ast}_{A\to B},f^{\ast}_{B\to A})$ and the **leader**
is the animal on the larger side. **Text:** collapses direction to the stronger one per night.

### Specificity: significant-pair fraction and Gini (per night)
$$ \text{frac\_sig}=\frac{\#\{\text{pairs with } z>2\}}{\#\text{pairs}},\qquad
   G=\frac{2\sum_{r=1}^{n} r\,x_{(r)}}{n\sum_r x_{(r)}}-\frac{n+1}{n} $$
where $x_{(r)}$ are the $n$ undirected pair scores sorted ascending. **Text:** frac_sig ∈ $[0,1]$
(near 1 = many pairs follow = herd); Gini ∈ $[0,1]$ (0 = all pairs equal/flat = herd, →1 = a few
dominant pairs = dyads).

### Stability: consecutive-night Spearman
$\rho$ = Spearman rank correlation between the vector of the 10 pair scores on night $k$ and on night
$k{+}1$, averaged over consecutive nights. **Text:** $\rho\approx1$ ⇒ the same pairs recur;
$\rho\approx0$ ⇒ the "preferred" pair reshuffles nightly.

### Per-night leadership
For animal $a$ on a night: $\text{n\_led}(a)=\#\{$ its pairs whose leader is $a\}$ (0..4); the night's
**top leader** = $\arg\max_a \text{n\_led}(a)$. **Text:** how many of its pairings each animal leads,
reported per night (not averaged).

### Simultaneity (both-moving fraction)
$$ \text{both\_moving\_frac}_{\{A,B\}}=\frac{\#\{t:\ \text{mov}_A(t)\wedge\text{mov}_B(t)\}}
   {\#\{\text{grid seconds}\}} $$
**Text:** fraction of the night both animals move at the same instant. Low (~1%) ⇒ movement is
sequential (one at a time), not synchronized herd travel.

### Group cohesion (herd control)
Per night, mean/median of the synchronous pairwise distance $\lVert\mathbf{x}_A(t)-\mathbf{x}_B(t)\rVert$
(2 s grid), and frac_clumped = fraction of bins with median pairwise distance $<39.37$ in (1 m).
**Text:** if the group travels as a herd, every pair's follow score rides on this; a **uniform**
significance pattern is the herd answer, a **concentrated** one is the dyad answer.

### Jitter floor
~7 in (documented stationary median; p95 ~15 in) — sets $R$ and gates sub-floor spatial claims.
Proximity/following thresholds kept $\ge$ 1 m.

## Outputs

`following_pairs_by_night.csv` · `undirected_pair_scores.csv` · `specificity_by_night.csv` · `per_night_leadership.csv` · `pair_stability_summary.csv` · `leadership_consistency.csv` · `group_cohesion.csv` · `simultaneity_summary.csv` · `top_following_bouts.csv` · `run_manifest.json` · `plots/` (incl. `leadership_by_night.png`, `pair_z_by_night.png`)
