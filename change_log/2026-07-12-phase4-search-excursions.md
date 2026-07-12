# 2026-07-12 — Phase 4: return-vs-explore (module 9) + coarse search geometry (module 10)

**Status:** ⚠️ candidate (gate-first). Builds the two Phase-4 modules of the behavioral-policy roadmap on
the extended 11-night data (06-28→07-08), on the module-6 validated settlement transitions and the
module-3 locomotor bouts. Both are bounded by the `decision_boundary_validation` verdict.

## What was built

- `src/search_excursions.py` — module 9 (`build_excursions`, `attach_site_history`,
  `return_explore_nulls`, `return_explore_gate`) and module 10 (`excursion_geometry`,
  `search_geometry_gate`).
- `scripts/selftest_search_excursions.py` — 4 planted scenarios, exit-coded **PASS** (S1 return-biased →
  beats layout; S2 layout-driven → does not beat layout; S3 explore-biased → high novelty/no signal;
  S4 geometry → tortuous vs directed straightness + jitter gate).
- `scripts/build_search_excursions.py` — gate-first driver → `outputs/search_excursions_2026-06-28_to_2026-07-08/`.

## Module 9 — return vs explore (WISER-native)

- **123 named-destination excursions** (75 relocation + 48 same-site-return) over 11 nights.
  Pooled **return rate 0.76**, **novelty rate 0.14**, **same-site-return fraction 0.39**.
- **Verdict: NO return-vs-explore preference beyond layout is resolvable.** The observed return rate does
  NOT exceed the layout base rate (site-popularity) null — night-block sign test **p = 0.55** (mean per-
  night effect +0.082, 7/11 nights positive), and it does not beat the history-shuffle null (p = 0.45).
  The high raw return rate is what site popularity alone predicts (a few sites dominate the named
  destinations), not a demonstrated recency/frequency preference.

### Definitions (formula + plain text)

- **Named-destination excursion** — a validated departure (module 6) that settles at a NAMED site
  (relocation or same-site-return). Denominator for return-vs-explore; open-field/pass-through/censored
  departures are excluded.
- **is_return** — destination ∈ the last $k$=3 DISTINCT settled sites (recency) OR prior-visit frequency
  there $> 1/S$ (frequency), $S$ = number of named sites. **dest_novel** = never settled there before.
  All history strictly prior to the departure (no leakage).
- **Layout base-rate null** — replace the destination by a draw from the global site-popularity
  distribution; recompute is_return against the SAME prior history. Tests: does the animal return MORE
  than site popularity produces?
- **History-shuffle null** — permute the animal's residence ORDER (keeps composition, destroys recency);
  recompute is_return. Beating it ⇒ recency-specific, not merely frequency-driven.
- **Night-block effect** $e = \text{rate}_{obs} - \text{rate}_{null}$ per night; significance = a binomial
  sign test on $e$ across the 11 nights (the outer blocks). Signal = beats layout; recency-specificity =
  additionally beats history-shuffle.

## Module 10 — coarse area-restricted-vs-global search geometry (DBV-capped)

- **1,541 locomotor bouts**, geometry from the actual bout path `[t_start, t_end]` (NOT the following
  residence, which would swallow post-settlement milling and drive straightness→0). **99.7 %** clear
  3 jitter floors (radius ≥ 21 in), so coarse radius is meaningful.
- Bouts are **uniformly tortuous** (median straightness 0.17–0.21) across all modes; the radius gradient
  is modest: **in_place 100 in < relocating 124 in < open 142 in** (median). No clean area-restricted-vs-
  global bimodality is resolvable — reported as **coarse geometry, NOT an inferred search strategy**
  (fine turn/ARS structure is jitter-unresolvable per DBV).

### Definitions (formula + plain text)

- **Bout geometry** (per module-3 bout, contiguous fixes, truncated at the first >120 s gap):
  `radius_in` = max distance from the start; `path_len_in` = summed step length; `net_disp_in` =
  start→end straight line; `straightness` = net/path $\in[0,1]$ (low = tortuous/looping, high =
  directed). `resolvable` = radius ≥ 3·(~7 in jitter floor). `mode` = relocating (crosses to a new named
  ROI) / in_place (stays local) / open (neither).

## Scope / caveats

Module 9: return/novelty defined on the ROI set in the UNVERIFIED inch frame; an unvisited site is a
coverage gap, not a demonstrated avoidance. "return-vs-explore tendency / site-history dependence" only —
NOT curiosity or novelty-seeking as a drive (association, not motivation). Module 10: coarse
radius/coverage only; geometry, not a foraging strategy or optimal search. Group-level, single 11-night
pilot; whole nights are the outer inference blocks.

## Verification

- `python scripts/selftest_search_excursions.py` → PASS (4/4).
- Full 11-night run → module 9 null verdict + module 10 coarse geometry, both persisted with manifests.
- Registry (`configs/behavioral_policy_modules.yaml`) modules 9 & 10 → `candidate`.
