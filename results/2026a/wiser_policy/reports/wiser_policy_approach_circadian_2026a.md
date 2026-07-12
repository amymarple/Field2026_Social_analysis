# Approach/avoid — active-period confinement + nap/circadian cross-check (Part 2, 11 nights)

**Status:** ⚠️ candidate. Confirms the module-7 distance-dependent social spacing is a property of the ACTIVE-movement period and cross-checks it against the circadian nap rhythm, on the extended 06-28→07-08 window. Generated 2026-07-12T07:06:01.765066. Frame UNVERIFIED (topology + coarse distance only); rest is a low-speed proxy, not sleep; night-block bits/sign-tests.

## Definitions (formula + plain text)

- **Confinement to active movement** — every approach/avoid unit is a (locomotor bout, partner) pair.
  A bout is a maximal run of ``active`` bins (speed above the ~7 in jitter floor) inside the 21:00–05:00
  local night. A RESTING animal emits no bout, so it contributes no pair: the metric is already confined
  to the active-moving period by construction.
- **Population rest fraction** $\rho(h)$ — at LOCAL clock-hour $h$, the fraction of informative
  (non-``unknown``) locomotor-state bins over ALL animals that are stationary (rest ∪ pause):
  $\rho(h) = \frac{\#\{\text{bins at }h:\ \text{state}\in\{\text{rest},\text{pause}\}\}}{\#\{\text{informative bins at }h\}}$.
  Animal-independent (the group rhythm), so using it to phase a focal's bout leaks no outcome.
- **Circadian phase** — $\text{phase}(h)=\text{nap}$ if $\rho(h)\ge\operatorname{median}_h\rho(h)$, else
  $\text{active}$. A median split of the 8 night-window hours into the group's more-resting vs
  more-active halves.
- **Geometry-adjusted approach** $e_{\dir}$ and **real-time social increment** $e_{\day}$ — as in
  module 7 (`change_log/2026-07-12-approach-avoid.md`): $e_{\dir}=\overline{\text{toward}}-$ (rotation
  null), $e_{\day}=\overline{\text{toward}\mid\text{valid}}-$ (same-partner/same-hour/different-night
  null). Positive $e_{\day}$ = approach, negative = avoid. Significance = a binomial SIGN TEST on the
  per-night effects across the 11 nights (the outer blocks), NOT a per-pair z.

## Circadian rest rhythm (population, animal-independent)

| local hour | pop. rest frac ρ(h) | phase |
|---|---|---|
| 00:00 | 0.986 | nap |
| 01:00 | 0.983 | nap |
| 02:00 | 0.985 | nap |
| 03:00 | 0.982 | active |
| 04:00 | 0.982 | active |
| 21:00 | 0.952 | active |
| 22:00 | 0.974 | active |
| 23:00 | 0.984 | nap |

Median ρ = 0.983. Active-phase pairs = 3605, nap-phase pairs = 2112.

## Night-block gate WITHIN the ACTIVE phase

| dist bin | e_dir | dir n_pos | dir p | e_day | day n_pos | day p |
|---|---|---|---|---|---|---|
| ALL | 0.3074 | 11/11 | 0.001 | 0.0376 | 10/11 | 0.012 |
| 1-2m | 0.2806 | 9/9 | 0.004 | -0.1966 | 2/9 | 0.18 |
| 2-3.8m | 0.2076 | 11/11 | 0.001 | -0.1042 | 1/11 | 0.012 |
| >3.8m | 0.3453 | 11/11 | 0.001 | 0.1244 | 11/11 | 0.001 |

social bin signs: {'2-3.8m': 'avoid', '>3.8m': 'approach'} — distance-dependent: True

## Night-block gate WITHIN the NAP phase

| dist bin | e_dir | dir n_pos | dir p | e_day | day n_pos | day p |
|---|---|---|---|---|---|---|
| ALL | 0.2817 | 11/11 | 0.001 | 0.0311 | 7/11 | 0.549 |
| 1-2m | 0.0817 | 1/1 | 1.0 | -0.2965 | 0/1 | 1.0 |
| 2-3.8m | 0.1437 | 9/11 | 0.065 | -0.1321 | 0/11 | 0.001 |
| >3.8m | 0.3444 | 11/11 | 0.001 | 0.121 | 11/11 | 0.001 |

social bin signs: {'2-3.8m': 'avoid', '>3.8m': 'approach'} — distance-dependent: True

## Verdict

distance-dependent social spacing is PRESENT in the ACTIVE-movement phase -> a genuine moving-time behaviour, not a circadian-nap artifact

## Scope

Group-level (herd, not dyads), association not motivation. Circadian phase is a population-rhythm split
(a low-speed rest proxy, not sleep/ephys). The night-block sign test has only 11 outer blocks, fewer
within each phase — a phase with few informative nights is under-powered, not evidence of absence.
Frame UNVERIFIED: distance bins are coarse (≥1 m, jitter floor ~7 in), no directional/route claims.
