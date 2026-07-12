# Direction 3 — sleep-site landmark hierarchy (state role in the decision process)

*Candidate / descriptive. Rest = low-speed proxy (< 12.5 in/s), NOT ephys. WISER inch frame UNVERIFIED — state ROLE/ordering is identifiable, physical CAUSE is NOT. Jitter ~7 in. Semi-Markov descriptive level; **no reward/IRL**. n=5 rats × 11 days = 55 rat-days; permutation nulls (2000×) are the inference; uncorrected.*

> **Question.** Are the daytime rest-site landmarks the SAME status in the decision, or RANKED (house_1 a top morning/return anchor, others midday/secondary)? refuge_4 (burrow 07-03→07-07) + tunnel are interpretation-limited and excluded from the headline.

## Definitions (formula + plain text)

- **dwell share** w(s) = trunk bins in s / all trunk bins (unconditional; sums to 1).
- **anchor share** α(s) = fraction of rat-days whose FIRST confident (≥15-min) state is s.
- **terminal share** ω(s) = fraction of rat-days whose LAST confident state (before emergence) is s.
- **net-flux** φ(s) = (In−Out)/(In+Out), In/Out = relocation arrivals/departures. φ>0 = net **sink** (returned-to).
- **home-base index** H(s) = mean(α, ω) — start+end prominence; the ranking column.
- **exchangeability KL** D = Σ α(s)·log(α(s)/w(s)) — anchor concentration BEYOND occupancy; p from an occupancy-weighted permutation null (redraw each day's anchor ∝ w).
- **diurnal separation** = std across states of their mean occupancy hour; **label-permutation** null (permute state labels across pooled bins — breaks the state↔hour association).
- **round-trip R** = of rat-days that LEAVE house_1, the fraction that RE-ENTER it later; Markov (order-shuffle) null.
- **Kendall W** = concordance of the 5 rats' home-base rankings; label-permutation null.
- **excursion_frac** E = fraction of trunk away from that rat's own primary (modal-dwell) state; within-rat Spearman vs midday peak temp (candidate).

## A. State-role table (ranked by home-base index)

```
   state  dwell_share  anchor_share  terminal_share  arrivals  departures  net_flux  home_base_index
 house_1        0.512         0.509           0.600        58          53     0.045            0.555
 house_2        0.334         0.182           0.382        58          47     0.105            0.282
refuge_4        0.054         0.164           0.018        20          28    -0.167            0.091
  tunnel        0.010         0.091           0.000         4           9    -0.385            0.045
 exposed        0.017         0.055           0.000         0           3    -1.000            0.027
 doorway        0.043         0.000           0.000        20          18     0.053            0.000
refuge_2        0.000         0.000           0.000         0           0       NaN            0.000
refuge_1        0.020         0.000           0.000         9           9     0.000            0.000
refuge_3        0.000         0.000           0.000         0           0       NaN            0.000
 water_2        0.009         0.000           0.000         1           3    -0.500            0.000
```

- **house_1 leads the home-base ranking** (H=0.55) — it both **starts** (anchor 0.51) and **ends** (terminal 0.60) the day most often. **Both houses are net sinks** (flux>0) while the peripheral states are net **sources**: exposed −1.00, water_2 −0.50. Traffic settles into the houses and drains from the periphery — so the states are NOT the same status (houses = home-bases/sinks; doorway/exposed/near-water = transient waypoints/sources). *(house_2's mid-trunk net-flux 0.11 slightly exceeds house_1's 0.05, but house_1 dominates the start+end home-base role.)*

## B. Are the landmarks exchangeable? (anchor / terminal role vs occupancy)

- **Anchor role:** KL(anchor ‖ dwell-weighted) = **0.331**, permutation **p<0.001** → **day-starts are concentrated BEYOND occupancy** (states are NOT exchangeable as anchors).
  *Nuance:* house_1 anchors ≈ its occupancy (0.51 vs dwell 0.51); the concentration is driven by **house_2 anchoring LESS than its dwell** (0.18 vs 0.33 — a daytime destination, not a morning start) and the burrow (refuge_4, interpretation-limited) over-anchoring on its window.
- **Terminal role:** KL = **0.125**, **p=0.053** → only borderline vs occupancy (both houses over-represented as day-end states, but not beyond the p=0.05 null).

## C. Diurnal ordering — when is each landmark used?

- **Mean occupancy hour by state:** refuge_1 9.9h, house_1 12.0h, house_2 13.9h, exposed 14.7h, doorway 15.0h.
- Cross-state hour separation std = **1.91 h**, label-permutation **p=0.001** → a **reproducible time-of-day ordering** (states are used at different times). Consistent with a morning-anchor → midday-excursion pattern.

## D. Path structure — excursion-and-return vs one-way

- **Round-trip:** of the rat-days that leave house_1, **R=0.78** return to it the same day; Markov-shuffle **p=0.138** → not above a memoryless re-ordering — returns are common but not beyond chance ordering.
- **Direct vs via-doorway:** house_1↔house_2 moves are **54 direct** vs **7 via a doorway stop** → doorway is **not** a systematic intermediate between the houses.

## E. Shared vs idiosyncratic ranking

- **Kendall's W = 0.79** across the 5 rats (permutation **p<0.001**) → the rats **share** a landmark ranking.
- **Shared-anchor test:** even the house_2-DWELLING rats (12395, 12407) start the day in **house_1** on **32%** of their rat-days → house_1's morning-anchor role is partly shared across the cohort, distinct from where the bulk of daytime dwell accrues.

## F. Excursion vs temperature (CANDIDATE)

- Within-rat Spearman(fraction of trunk away from own primary, midday peak temp) = **0.18** (n=55). No detectable within-rat association under the current measurement + N. **Candidate only** — ambient (not shelter) temperature, unverified frame, uncorrected; this is NOT a demonstrated thermal cause.

## Evidence status (two levels)

**Supported within the current WISER measurement (descriptive):** the landmarks are NOT the same status — house_1 is a top-ranked anchor/return (net sink), there is a reproducible diurnal ordering, and the anchor role is partly shared across rats. **Candidate / not established:** any PHYSICAL cause (temperature, a spatial 'toward-out' gradient), that the ROIs are specific refuges, and that low-movement = sleep. Frame unverified; needs georeference + interior CV/ephys.

## Deferred / non-goals
- No reward/IRL policy (identifiability). No physical-cause claim. No cross-night personalization or social structure.


*Figures + CSVs: `D:\Field2026_analysis_out\sleep_site_hierarchy_20260711_2004`.*
