# Daytime Rest-Site Organization in Rats in an Outdoor Field Enclosure

**Direction 3 scientific summary (consolidated).** Field_2026_Social pilot · 20 × 40 ft outdoor paddock ·
WISER UWB position tracking · 5 implanted rats × 11 days (2026-06-28 → 2026-07-08), 55 rat-days.
**Reading time ~5 min.** This narrative is derived from, and never overrides, the technical record
(see *Technical references*). It consolidates two analyses — the biological-day rest model and the
landmark-hierarchy analysis. No claim here is validated against physiology or video.

## The biological picture

These rats are nocturnal, and everything below comes from **position and speed only** — "rest" is a
**low-movement proxy**, not measured sleep, and the spatial frame is unverified (so no site is claimed to
be physically warmer, cooler, or in a particular direction). Read that way, each animal's day is a long
**low-movement rest bout** ("the daytime trunk") from ~05:00 until it leaves its resting spot in the
evening. Where it rests is **not one fixed burrow and not an interchangeable set of spots**: two group
houses dominate, but the animal also uses secondary refuges, house entrances, and open ground, moving
between them a few times a day. Critically, the resting landmarks are **ranked, not equivalent** — one
house acts as a home-base the animals start and return to, with a reproducible morning-core → afternoon-
periphery pattern. Whether any of this is true sleep, or has a thermal cause, is beyond what position data
can settle.

## Finding 1 — The rest bout ends at an evening site-departure, and there is no fixed mid-morning switch

Scored from ~05:00, the trunk ends when the animal begins sustained locomotion and **leaves its resting
site**. This is a **site-departure time, not a wake time** — WISER cannot see an animal stirring inside a
shelter, so this evening value (~20.8 h) is necessarily later than the ~18:00 in-nest arousal that
observers note. The departure clusters in the evening and shows **no detectable association with that
day's afternoon temperature (Spearman ρ = −0.02, n = 11 days)** — so the end of daytime rest is not set by
heat (this retires an earlier "temperature-calibrated" boundary that mistakenly ran past midnight). An
earlier reading also suggested a site switch at ~10:00; an independent change-point analysis with no fixed
hour shows within-day site changes are real but **spread across the day (median 13.5 h; only 11% within an
hour of 10:00**, and 8% for the full relocation set) — there is **no ~10:00-locked switch**. Caveat: on
3 of 11 days the departure detector saturates at its 21:00 ceiling (once because the animal never crossed
threshold) and once at the 16:00 floor (a fog day); these are censored values, not exact times.

## Finding 2 — Daytime rest is a multi-site refuge network dominated by two houses

Assigning every 5-minute resting position to the full set of mapped landmarks (rather than forcing a
two-house choice) shows the two group houses hold **≈85% of low-movement trunk dwell (house_1 0.51,
house_2 0.33**, unconditional fractions that sum to 1), but the remaining ~15% is spread over secondary
refuges, house entrances, a near-water region, and open ground. Animals **relocate ≈3.1 times per rat-day**
(median 3, range 0–8; 170 moves total), and these moves are **not** predominantly house-to-house: of the
110 interpretable relocations (excluding a transient burrow and tunnel), **56 (51%) involve at least one
non-house state**. So dwell is dominated by two houses while movement routinely visits the wider network —
both are true, and a two-house description misses the second half. The landmarks are mapped regions in an
unverified frame, **not confirmed physical refuges**.

## Finding 3 — The landmarks are not the same status: a shared home-base hierarchy

This directly answers the decision-role question. The resting states are **not exchangeable**: which state
a day *starts* in is concentrated well beyond what occupancy alone predicts (**KL = 0.33 of the start-state
distribution from the occupancy-weighted expectation; p < 0.001** against an occupancy-weighted permutation
null, n = 55). The structure is a **home-base hierarchy**: the two houses are net **sinks** (traffic
settles into them) and dominate the day's *end* state, while peripheral states are net **sources**
(entered briefly and left — e.g. open ground has flux −1.0, i.e. only departures). **house_1 is the top
home-base**, being both the most common start and the most common end of the day (start 0.51 + end 0.60).
State use is also **ordered in time** — mean occupancy runs house_1 (~12.0 h) → house_2 (~13.9 h) →
entrances (~15.0 h), a reproducible morning-core → afternoon-periphery excursion (**separation 1.9 h,
p = 0.001** against a label-permutation null). And the ranking is a **cohort property, not idiosyncratic**:
the five rats agree strongly (**Kendall's W = 0.79, p < 0.001**), and even the two animals that *dwell*
mostly in house_2 still **start** the day in house_1 on **32%** of days. Two parts of the originally
proposed chain do **not** hold, though: entrances are not a systematic stepping-stone between the houses
(54 direct house-to-house moves vs 7 via an entrance), and the day ends in a house, not "fully outside."

## Candidate interpretation — a within-day temperature *gate* on leaving the house

Daytime temperature acts as a **gate, not a linear dial**. Below ~30 °C the rats are almost always inside a
house (~4–6% of resting time out); above ~**32 °C** out-of-house time jumps to ~27–34%. The decisive test
uses **each hot day as its own control**: because only midday crosses the gate, the same rat-day has cool
(morning/evening) and hot (midday) periods, so the comparison removes day, animal, sequence, and
new-environment exploration. **Within a day, crossing the gate raises out-of-house time from 0.04 to 0.31
(ΔP(out) = +0.27; day-clustered 95% CI [+0.22, +0.32]; consistent across all 4 gate-crossing days)**; the
exodus is timed to the **14:00–15:00 heat peak**; and above-gate exits are more cooling-directed (44% → 66%).
A **matched clock-hour control** rules out a circadian explanation: at midday the exodus is present on hot
days but **absent on cold days** (P(out) **0.32 vs 0.03**) — cold days stay inside at *every* hour. The two
tests **triangulate** (within-day removes day-in-sequence; matched-hour removes circadian).
**Four of five rats** show it — the sedentary house-loyalist (12378) is the lone exception.

**Status:** the *gate itself* is well supported descriptively; that it is **thermoregulation** is
**candidate** — it is **ambient** (not in-shelter) temperature, the "out" states are **unverified** locations,
and the threshold rests on only **4 hot days**. It is consistent with heat-avoidance but not proven. This
**supersedes** the earlier "no detectable temperature effect on daytime movement" (that used full-day,
linear tests, which cannot see a *threshold*), and it explains why a "house rat vs floater" personality
split dissolves: the leaving is a mostly-**shared gate**, not an individual trait. *(Full topic write-up:
[`wiser_d3_sleep_heat_gated_relocation_SCIENTIFIC_SUMMARY_2026a.md`](wiser_d3_sleep_heat_gated_relocation_SCIENTIFIC_SUMMARY_2026a.md).)*

## What is no longer supported
- **A ~10:00 site switch** — change-point times are spread, not clock-locked.
- **A binary house_1/house_2 state space** — misspecified; rest is multi-site.
- **"No detectable temperature effect on daytime movement"** — a *lens* artifact: full-day and linear tests
  cannot see a threshold. The effect is a **within-day temperature gate** (above), and it is real.
- **A stable "house rat vs floater" personality** — out-of-shelter floating is **not a stable trait**
  (between-animal identity explains ~2% of daily floating; split-half rank stability ≈ 0.10); the leaving is
  a mostly-shared temperature gate. (Which *house* an animal calls home **is** a stable individual axis.)
- **A structured there-and-back excursion** — returns to house_1 are common (78% of days that leave it)
  but **not beyond a memoryless re-ordering (p = 0.14)**.
- **A temperature-calibrated, past-midnight rest-end** — the trunk ends in the evening.

## What remains unresolved (ranked by impact on the next decision)
1. **Is the low-movement trunk actually sleep, and are the mapped landmarks the physical shelters we think?**
   Both gate every biological reading here.
2. **Does the morning→afternoon ordering have a thermal/physical cause?** Needs the frame and a microclimate measure.
3. **When do animals truly wake in-nest (~18:00)?** Below the tracker's reach.

## Next decision (highest scientific value first)
1. **Interior shelter video (CH07/CH08, installed 2026-07-07)** — test whether the low-movement proxy
   tracks animals actually at rest, and recover the true in-nest arousal time.
2. **Georeference the frame** (pole survey) — turn the ranked landmarks into verified physical locations.
3. **In-shelter temperature** (thermistor) — turn the ambient-temperature correlate into a microclimate test.

## Technical references
- Ledger: `change_log/2026-07-10-biological-day-sleep.md`, `2026-07-11-sleep-site-hierarchy.md`, `2026-07-12-heat-gated-relocation.md`; `ANALYSIS_STATUS.md` (Direction 3).
- Technical reports: `outputs/direction3_biological_day_sleep/…report.md` (+ `…_canonical_results.md/.json`); `outputs/direction3_sleep_site_hierarchy/…report.md`; `outputs/direction3_heat_gated_relocation/…report.md`.
- Figures: biological-day `summary_figures/fig1–3`; hierarchy `H1/H2/H4`; heat-gate `HG1_gate_curve`, `HG2_within_day_gate_contrast`, `HG3_timing`.
- Drivers: `analyze_biological_day_sleep.py`, `analyze_sleep_site_hierarchy.py`, `analyze_heat_gated_relocation.py` (offline self-tests are **code checks, not biological validation**).

---

## Quantitative appendix — how each finding was quantified

Definitions follow `/analysis-definitions` (formula + plain text). Trunk = local `[05:00,
locomotor_emergence)`, rest = smoothed UWB speed `< 12.46 in/s`; state = nearest mapped landmark within a
15 in buffer (jitter ~7 in), else entrance band (+24 in) or open. States `refuge_4` (burrow, 07-03→07-07)
and `tunnel` are interpretation-limited and excluded from headline denominators.

**F1 · Departure time vs temperature.**
- *Quantity:* `locomotor_emergence_hour` — local clock hour (16–21, right-censored) of sustained-locomotion onset.
- *Value:* median 20.8 h; 7/11 days interior (19.7–20.9 h), 3 censored at 21:00, 1 at 16:00.
- *Null/rule:* Spearman $\rho$(emergence, afternoon-peak temp), $n=11$; $|\rho|<0.2 \Rightarrow$ no detectable association. **ρ = −0.02.**
- *Inference:* ρ≈0 over 11 days ⇒ departure timing is **not** temperature-linked (mechanism unresolved).

**F1 · No ~10:00 switch.**
- *Quantity:* within-day change-point time (single largest position split, no fixed hour) and all state-sequence relocation times, local hours.
- *Formula:* fraction within ±1 h of 10:00 $= \frac{1}{N}\sum_i \mathbb{1}[|h_i-10|\le 1]$.
- *Value:* change-point median 13.5 h, **11%** within ±1 h (44/55 supported, ≥100 in split); relocations median 13.4 h, **8%**.
- *Rule:* clustering at 10:00 would require a peak near ±1 h; observed ⇒ **rejected**. *Sensitivity:* stable across smoothing (36/44) and a >25%-dropout filter.

**F2 · Multi-site composition.**
- *Quantity:* unconditional dwell share $w(s)=$ (trunk bins in $s$)/(all trunk bins), $\sum_s w(s)=1$.
- *Value:* house_1 0.51, house_2 0.33 (**Σ two houses ≈0.85**); relocations mean **3.1/rat-day** (median 3, range 0–8, 170 total); non-house involvement **56/110 = 51%** interpretable (116/170 = 68% of all).
- *Rule:* $\Sigma w \approx 1$ is the composition check (conditional-on-use means, which sum to 1.40, are **not** used).

**F3 · States not exchangeable (anchor role).**
- *Quantity:* $D=\sum_s \alpha(s)\log\frac{\alpha(s)}{w(s)}$ — KL of the day-start distribution $\alpha$ from occupancy $w$ (nats, ≥0).
- *Value:* **D = 0.33**, permutation **p < 0.001** ($n=55$; null redraws each day's start ∝ $w$, 2000×). *Note:* driven by house_2 under-starting (0.18 vs dwell 0.33), not house_1 over-starting.
- *Inference:* $D$ far above the occupancy-weighted null ⇒ start-states are concentrated beyond occupancy ⇒ landmarks differ in role.

**F3 · Home-base + sink/source.**
- *Quantity:* anchor $\alpha(s)$, terminal $\omega(s)$ (start/end shares), net-flux $\phi(s)=\frac{In-Out}{In+Out}\in[-1,1]$.
- *Value:* house_1 α 0.51, ω 0.60 (home-base index 0.55, top); houses φ>0 (sinks); open ground φ=−1.0, near-water −0.5 (sources).

**F3 · Diurnal ordering.**
- *Quantity:* separation $=\operatorname{std}_s(\bar h_s)$, $\bar h_s$ = mean occupancy hour of state $s$.
- *Value:* house_1 12.0 → house_2 13.9 → entrance 15.0 h; **std = 1.9 h, p = 0.001** (label-permutation null across pooled bins, 2000×).

**F3 · Shared ranking.**
- *Quantity:* Kendall's $W\in[0,1]$ over 5 rats' home-base rank vectors.
- *Value:* **W = 0.79, p < 0.001** (rank-permutation null); house_1 day-start share among house_2-dwellers = **0.32**.

**Candidate · Within-day temperature gate on house-leaving.**
- *Quantity:* $P(\text{out}) = \#\text{out}/\#(\text{enclosed}+\text{out})$ over 5-min trunk bins; enclosed = the two houses, out = doorway/exposed/near-water/secondary-refuge (burrow, tunnel, dropout excluded). Instantaneous $T$ = AWN air temp at the nearest sample (≤15 min).
- *Gate:* $P(\text{out})$ by 2 °C bin — 0.05 (≤30 °C) → **0.27** (32–34 °C) → 0.34 (34–36 °C); gate ≈ **32 °C** (curve step; a parametric logistic threshold is unstable on ~4 hot days).
- *Within-day (headline):* per rat-day with ≥3 bins each side of $G$=32 °C, $\Delta P = P(\text{out}\mid T\ge G) - P(\text{out}\mid T<G)$. **Value $\Delta P = +0.27$** (0.04→0.31), **95% CI [+0.22, +0.32]**, **frac>0 = 1.0** — a **day-clustered bootstrap** (resample the 4 gate-crossing days, 2000×); relocation-rate $\Delta = +0.06$ [+0.03, +0.10]; 4/5 rats positive.
- *Supporting:* out-of-house peaks at 14–15:00 (heat peak); cooling-directed exit fraction 0.40 (below) → 0.66 (above).
- *Circadian control:* matched clock-hour, HOT (peak ≥32 °C, 5 days) vs COLD (5 days) — **midday P(out) 0.32 vs 0.03** (all 5 rats show the gap; cold days ~0 at every hour) ⇒ not a circadian midday rhythm. Within-day removes sequence, matched-hour removes circadian — both needed because hot days were early.
- *Rule/limits:* the **within-day design** removes day/rat/sequence/exploration, so the descriptive gate is well supported; the **causal (thermoregulation)** reading is candidate — ambient not in-shelter $T$, unverified out-locations, threshold rests on 4 hot days, per-bin *trigger* weak. Supersedes the earlier full-day null.
