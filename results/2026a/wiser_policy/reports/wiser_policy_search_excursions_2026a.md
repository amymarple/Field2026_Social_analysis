# Return-vs-explore & coarse search geometry (Phase 4, Modules 9 & 10, 11 nights)

**Status:** ⚠️ candidate (gate-first). Module 9 (return-vs-explore) is WISER-native; Module 10 (area-restricted-vs-global search) is capped at COARSE geometry by the decision_boundary_validation verdict. Extended 06-28→07-08 window. Generated 2026-07-12T07:29:27.139378. Frame UNVERIFIED (topology + coarse distance only); whole-night sign tests; association not motivation.

## Definitions (formula + plain text)

- **Named-destination excursion** — a validated departure (module 6) that settles at a NAMED site: a
  ``relocation`` (different site) or a ``same_site_return`` (back to the same site). The denominator for
  return-vs-explore. Open-field terminations and pass-throughs are NOT return/explore decisions.
- **Prior site-visit history** — for an excursion departing at $t$, the animal's sequence of settled
  sites at times $t' < t$ (strictly prior; no leakage).
- **is_return** — the destination is in the animal's last $k$=3 DISTINCT settled sites (RECENCY) OR its
  prior-visit frequency there exceeds the uniform per-site share $1/S$ (FREQUENCY), $S$ = number of named
  sites. **is_explore** = otherwise; **dest_novel** = never settled there before.
- **Layout base-rate null** — replace the destination with a draw from the GLOBAL site-popularity
  distribution and recompute is_return against the SAME prior history. Answers: does the animal return
  MORE than site popularity alone would produce?
- **History-shuffle null** — permute the animal's residence ORDER (keeps site composition/frequency,
  destroys recency) and recompute is_return. Beating it means the return is RECENCY-specific, not merely
  frequency-driven.
- **Night-block effect** $e = \text{rate}_{obs} - \text{rate}_{null}$ per night; significance = a binomial
  SIGN TEST on $e$ across the whole nights (the outer blocks), NOT a per-excursion test.
- **Coarse search geometry** (module 10, per excursion, from the contiguous fix segment): ``radius_in`` =
  max distance from the start; ``path_len_in`` = summed step length; ``net_disp_in`` = start→end straight
  line; ``straightness`` = net/path $\in[0,1]$ (low = tortuous/looping). ``resolvable`` = radius
  $\ge 3\times$ the ~7 in jitter floor. NO turn-by-turn kinematics (DBV-blocked).


## Module 9 — return vs explore

- Named-destination excursions: **123** over **11** nights
  (pooled return rate **0.76**, novelty rate **0.14**,
  same-site-return fraction **0.39**).
- **vs the layout base rate:** night-block sign test p = **0.548828125** (mean e = 0.082,
  7/11 nights positive) → beats layout: **False**.
- **vs history-shuffle (recency specificity):** p = **0.453125** → beats shuffle:
  **False** (recency-specific: False).
- **Verdict:** resolvable but NOT distinguishable from the layout base rate at the night level

## Module 10 — coarse area-restricted-vs-global search geometry

Coarse path geometry of 1541 locomotor bouts (100% clear 3 jitter floors).

| bout mode | n | median radius (in) | median straightness | resolvable frac |
|---|---|---|---|---|
| in_place | 203 | 100.2 | 0.205 | 0.99 |
| open | 1284 | 141.6 | 0.192 | 0.998 |
| relocating | 54 | 124.0 | 0.172 | 1.0 |

- in_place median radius = 100.2 in; relocating = 124.0 in (in_place bouts have a SMALLER radius than relocating bouts (a coarse area-restricted vs directed-travel separation)).
- **Measurement verdict:** COARSE geometry only (DBV): fine turn/ARS structure is NOT resolvable at the ~7 in jitter floor; 100% of bouts have a radius >= 3 jitter floors so coarse radius/coverage is meaningful for that subset (in_place vs relocating separation is a geometry statistic, NOT an inferred search strategy)

## Scope

Module 9: return/novelty are defined on the ROI set in the UNVERIFIED inch frame; an unvisited site is a
coverage gap, not a demonstrated avoidance. "return-vs-explore tendency / site-history dependence" only —
NOT curiosity or novelty-seeking as a drive. Module 10: coarse radius/coverage only; fine ARS turn
structure is jitter-unresolvable (DBV); geometry, not a foraging strategy. Group-level, single 11-night
pilot; whole nights are the outer blocks.
