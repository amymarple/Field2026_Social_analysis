---
name: analysis-definitions
description: >-
  This skill should be used whenever producing a data-analysis deliverable in Field_2026_Social —
  writing a results report, a change_log entry, an analysis summary, a metrics table, or otherwise
  reporting any derived quantity. It enforces a documentation contract: EVERY derived quantity used in
  an analysis (metric, index, threshold, statistic, score, null/baseline model, transform, or
  QC/validity rule) must be defined BOTH as a mathematical formula AND in plain text, with symbols,
  units, and interpretation. It auto-fires; run it explicitly with /analysis-definitions. Trigger
  phrases: "analysis report", "results summary", "change log", "define the metric", "how is X
  computed", "recurrence", "score", "index", "entropy", "threshold", "null model", "permutation
  test", "z-score", "what does this number mean".
---

# Analysis definitions — formula + text for every quantity

## Core rule

When an analysis reports a number, the reader must be able to reproduce it. So **every derived
quantity gets defined twice**:

1. **A mathematical formula** — the exact computation in math notation, with every symbol declared.
2. **A plain-text description** — what it measures, its units, its range, and how to read a
   high/low value.

Neither alone is sufficient: the formula makes it reproducible; the text makes it interpretable. A
report that says "recurrence is 95%" without both is incomplete.

## What counts as a "definition" (define ALL of these)

- **Metrics / indices / scores** — occupancy cosine, self-concentration, route-reuse, follow score,
  recurrence fraction, motif entropy, Gini, specificity, straightness, …
- **Thresholds & cutoffs** — jitter floor, moving threshold, follow radius R, bout min-displacement,
  min-anchors, gap factor, motif distance threshold. State the value AND how it was chosen.
- **Statistics & tests** — means, correlations (which one: Pearson/Spearman), z-scores, bootstrap CIs,
  and the exact **null/baseline model** (circular-shift, day-shuffle, label-permutation, shared-density):
  a null must have its own formula, not just a name.
- **Transforms & derived coordinates** — smoothing windows, arc-length resampling, georeference map,
  bin edges. State units on both sides.
- **Aggregation choices** — per-night vs pooled, denominator (e.g. "fraction of *both-moving* bins"),
  what is excluded (fireworks night, tag cutoffs) and why.

If a quantity feeds a headline claim, it MUST be defined. Reused library quantities may be defined by
reference to a shared definitions doc (see below), but the first use in a project defines them fully.

## Format for each definition

Use a `## Definitions` (or `### Definitions`) section in the report AND mirror the key ones in the
`change_log/` entry. One entry per quantity:

- **Name / symbol** — the symbol used elsewhere in the doc.
- **Formula** — in LaTeX delimited by `$…$` (inline) or `$$…$$` (display) so rich viewers render it;
  keep it ASCII-legible for terminals too. Declare every symbol (indices, sets, operators).
- **Text** — one or two sentences: what it means, **units**, **range/domain**, and the
  high-vs-low reading.
- **Threshold provenance** (for cutoffs) — the chosen value and its justification (e.g. "= 3× the
  jitter floor").

Units in this repo are **inches** for WISER, **cm** for the CV field frame (see CLAUDE.md); state
units explicitly and never mix them silently.

## Template (copy into the report)

```markdown
## Definitions

All quantities in the WISER native **inch** frame (UNVERIFIED offset origin) unless noted.
Symbols: $i,j$ index bouts/animals; $N$ = count; $\mathbf{p}_i$ = a resampled path; $t$ = time bin.

### <Quantity name> ($<symbol>$)
$$ <symbol> = <formula> $$
where $<sym>$ is <…>, $<sym>$ is <…>.
**Text:** <what it measures>. Units: <…>. Range: <…> (<low reading> … <high reading>).

### <Threshold name>
Value **<v> <unit>** = <how chosen, e.g. $3\times$ jitter floor>. **Text:** <role in the analysis>.

### <Null model name>
$$ <null statistic> = <formula over the shuffled/permuted data> $$
**Text:** <what structure it preserves and what it breaks>; a result is credible when
$z = (\text{obs} - \mu_{\text{null}})/\sigma_{\text{null}} > 2$.
```

## Worked example (from the trajectory-stereotypy analyses)

```markdown
## Definitions

Units: inches. $B$ = set of route bouts; $\mathbf{p}_i \in \mathbb{R}^{L\times 2}$ = bout $i$'s
arc-length-resampled path ($L$ points); $D_{ij}$ = path distance; $s(i)$ = bout $i$'s animal.

### Route (path) distance ($D_{ij}$)
$$ D_{ij} = \frac{1}{L}\sum_{k=1}^{L} \lVert \mathbf{p}_i^{(k)} - \mathbf{p}_j^{(k)} \rVert_2 $$
**Text:** mean point-to-point separation between two arc-length-aligned routes. Units: inches.
Range: $[0,\infty)$; 0 = identical route, large = different routes.

### Recurrence at threshold $\tau$ ($R(\tau)$)
$$ R(\tau) = \frac{1}{|B|}\sum_{i\in B} \mathbb{1}\!\left[\min_{j\neq i} D_{ij} \le \tau\right] $$
**Text:** fraction of route bouts that have a near-identical partner within $\tau$. Range $[0,1]$;
high = highly stereotyped/repeated routes. Reported at $\tau \in \{1.5,3,6\}\times$ jitter floor.

### Follow score ($f_{A\to B}(\ell)$)
$$ f_{A\to B}(\ell) = \frac{\#\{t : \text{mov}_A(t)\wedge \text{mov}_B(t{+}\ell)\wedge \lVert \mathbf{x}_B(t{+}\ell)-\mathbf{x}_A(t)\rVert < R \wedge \hat{\mathbf u}_A(t)\cdot\hat{\mathbf u}_B(t{+}\ell) > c\}}{\#\{t : \text{mov}_A(t)\wedge \text{mov}_B(t{+}\ell)\}} $$
where $\text{mov}$ = moving mask, $\mathbf{x}$ = position, $\hat{\mathbf u}$ = heading unit vector,
$R$ = follow radius, $c=0.5$ = heading-cosine cutoff, $\ell$ = lag (s).
**Text:** of the seconds both animals move, the fraction where the follower retraces the leader's
earlier position (within $R$, same heading) at lag $\ell$. Range $[0,1]$.

### Follow radius ($R$)
Value **24 in** $= \max(3\times \text{jitter floor}, 24)$. **Text:** the spatial tolerance for
"same place"; set to $3\times$ the ~7 in jitter floor so following is above localization noise.

### Circular-shift null ($z$)
$$ z = \frac{f^{\ast} - \mu_{\text{null}}}{\sigma_{\text{null}}}, \quad
   \text{null} = \{\, f^{\ast}\ \text{recomputed after rolling B's track by a random } \delta \in [5,20]\text{ min}\,\} $$
where $f^{\ast}=\max_\ell f_{A\to B}(\ell)$. **Text:** preserves each animal's own activity/route
habit but destroys real-time alignment; a pair's following is credible when $z>2$.
```

## Where it goes

- The analysis **report** (`outputs/.../*_report.md`) carries the full `## Definitions` section.
- The **`change_log/`** entry mirrors the definitions of the headline quantities (formula + one-line
  text) so the record is self-contained.
- If several drivers share the same quantities, put the canonical definitions in one
  `docs/methods/<topic>_definitions.md` and have each report link to it (define once, reference after).

## Checklist before publishing an analysis

- [ ] Every metric/index/score in the report appears in `## Definitions` with a formula AND text.
- [ ] Every threshold states its value, units, and how it was chosen.
- [ ] Every null/baseline/statistic has an explicit formula (not just a name), and its $z$/CI rule.
- [ ] Units are stated (inches vs cm) and never mixed silently.
- [ ] Denominators and aggregation (per-night vs pooled, exclusions) are defined.
- [ ] The change_log mirrors the headline definitions.
