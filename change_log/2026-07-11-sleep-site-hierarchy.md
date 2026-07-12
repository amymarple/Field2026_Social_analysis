# Change log — Direction 3: sleep-site landmark hierarchy (state role in the decision process)

**Date:** 2026-07-11 · **Type:** analysis (new util primitives + driver + self-test + report). Candidate / descriptive.
**Plan:** `implementation_plan/2026-07-11-sleep-site-hierarchy.md`.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13, np 2.1.3, pd 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (static; 06-28→07-08, 5 rats, 55 rat-days),
baseline `tag_reports_2026-06-30.sqlite`, weather `AWN-…20260628-20260709.csv`, ROIs `wiser_rois.json`.
**Run:** `D:\Field2026_analysis_out\sleep_site_hierarchy_20260711_2004` · **n_perm=2000, seed=20260711**.

## What / why
Tests a user hypothesis: are the daytime rest-site landmarks the **same status** in the sleep-site
decision, or **ranked** (house_1 a top morning/return anchor, others midday/secondary)? Reframed from an
ordered chain (`house_1→doorway→house_2→out`) to **state-role structure** after a read-only exploration.
**Identifiability:** tests the decision structure over **labelled** states (identifiable without the
physical frame); does **NOT** claim the physical **cause** (frame unverified, ambient-only temperature,
sleep = low-movement proxy). Semi-Markov **descriptive** level — **no reward/IRL** (per
[[agent-policy-identifiability-nogo]]). refuge_4 (burrow 07-03→07-07) + tunnel interpretation-limited.

## Definitions (formula + plain text)
Per rat-day state sequence = ordered confident (≥3-bin = 15-min) state-segments from
`trunk_state_dwell_transitions` (trunk = 05:00→locomotor_emergence, rest = speed < 12.46 in/s).
- **dwell share** w(s), **anchor share** α(s)=P(first confident state=s), **terminal share** ω(s)=P(last=s).
- **net-flux** φ(s)=(In−Out)/(In+Out) from relocation arrivals/departures; φ>0 = net **sink**.
- **home-base index** H(s)=mean(α,ω).
- **exchangeability KL** D=Σ α(s)·log(α(s)/w(s)); occupancy-weighted permutation p (redraw anchors ∝ w).
- **diurnal separation** = std across states of mean occupancy hour; **label-permutation** null.
- **round-trip R** = of rat-days leaving house_1, fraction re-entering it; Markov order-shuffle null.
- **Kendall W** = concordance of the 5 rats' home-base rankings; label-permutation null.
- **excursion_frac** E = fraction of trunk away from own primary; within-rat Spearman vs midday peak temp.
Full formulas: report + `implementation_plan/2026-07-11-sleep-site-hierarchy.md`.

## Results (candidate; 55 rat-days, permutation nulls are the inference, uncorrected)
1. **The landmarks are NOT the same status.** The **anchor role is non-exchangeable**: KL=0.331, **p<0.001**
   — day-starts are concentrated beyond occupancy. *Nuance:* house_1 anchors ≈ its occupancy (0.51 vs 0.51);
   the concentration is driven by **house_2 anchoring LESS than its dwell** (0.18 vs 0.33 — a daytime
   destination) + the burrow over-anchoring on its window.
2. **A sink/source hierarchy.** Both **houses are net sinks** (house_1 φ=+0.05, house_2 +0.10) and dominate
   the day-**end** (terminal house_1 0.60, house_2 0.38 — both > their dwell), while the **periphery are
   sources** (exposed φ=−1.0, water_2 −0.5, tunnel −0.39). **house_1 leads the home-base ranking** (H=0.55:
   most common start AND end). Traffic settles into the houses, drains from the periphery.
3. **Reproducible diurnal ordering.** Mean occupancy hour: refuge_1 9.9h → house_1 12.0h → house_2 13.9h →
   exposed 14.7h → doorway 15.0h; cross-state separation 1.91 h, label-permutation **p=0.001** → a morning
   house_1 core → afternoon house_2/doorway excursion.
4. **Shared ranking across rats.** Kendall **W=0.79, p<0.001** — the 5 rats share a home-base ranking; even
   the two **house_2-DWELLING** rats (12395, 12407) **start** the day in house_1 on **32%** of their rat-days
   (house_1's morning-anchor role is partly shared, distinct from where bulk dwell accrues).
5. **User's ordered chain REVISED (honest nulls):** house_1↔house_2 moves are **54 direct vs 7 via a
   doorway** → doorway is **not** a systematic intermediate. **Round-trip** is common (R=0.78) **but NOT
   beyond a memoryless re-ordering (p=0.14)** — return structure not established. **Terminal** concentration
   is only **borderline (p=0.053)**. "Fully out" = the emergence (site departure), not a within-trunk state.
6. **Temperature (candidate):** within-rat Spearman(fraction away from own primary, midday peak temp) =
   **+0.18 (n=55)** → **no detectable** association; NOT a demonstrated thermal cause (ambient-only, frame
   unverified, uncorrected).

## Changes
- **`src/wiser_analysis_utils.py`** — new pure primitives: `net_flux_scores`, `anchor_concentration_kl`,
  `permutation_pvalue`, `kendall_w` (analysis-layer; self-tested).
- **`scripts/analyze_sleep_site_hierarchy.py`** — new driver: trunk per rat-day → state-role table +
  exchangeability + diurnal + path + shared-vs-idiosyncratic + excursion-temperature; figures
  `H1_state_role_ranking`, `H2_diurnal_occupancy_profile`, `H3_transition_flux`,
  `H4_shared_vs_idiosyncratic`; CSVs (`state_role_table`, `ratday_anchor_terminal`, `transition_matrix`,
  `diurnal_mean_hours`, `per_rat_homebase_ranks`, `excursion_vs_temperature`, `hierarchy_verdict`); report.
- **`scripts/selftest_sleep_site_hierarchy.py`** — offline planted PASS (net-flux sink, KL flat-vs-concentrated,
  permutation p, Kendall W, and an exchangeable-vs-ranked end-to-end recovery).
- Report → `outputs/direction3_sleep_site_hierarchy/…report.md`; outputs → git-ignored `D:\Field2026_analysis_out`.

## Verification
- `python scripts/selftest_sleep_site_hierarchy.py` → **PASS** (0 failures; primitives + end-to-end).
- Real run 06-28→07-08 (n_perm=2000): 55 rat-days; anchor p<0.001, diurnal p=0.001, shared W p<0.001
  (SUPPORTED); terminal p=0.053, round-trip p=0.14, excursion-temp ρ=0.18 (NOT established — honest nulls).
  Figures spot-checked. Read-only DB/weather.
- **Methods note:** the diurnal null was first mis-specified as a per-day circular time-shift (which
  preserves within-day cross-state ordering → p=0.59, a false negative); corrected to a state-label
  permutation (p=0.001). Driver + report carry the corrected null.

## Evidence status (two levels)
**Supported (descriptive, within the WISER measurement):** landmarks are NOT the same status — house_1 is
a top-ranked anchor/home-base, houses are sinks vs peripheral sources, a reproducible diurnal ordering, and
a cohort-shared ranking. **Candidate / not established:** any physical CAUSE (temperature / spatial
gradient), that ROIs = specific physical refuges, that low-movement = sleep, and the round-trip/terminal
structure (null-negative). Frame unverified → needs georeference + interior CV (CH07/CH08) / ephys.

## Deferred / non-goals
No reward/IRL policy (identifiability). No physical-cause claim. No cross-night personalization or social
structure. A firmer temperature test needs a shelter thermistor + more days.
