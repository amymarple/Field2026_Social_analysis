# Daytime Temperature Gates House-Leaving in Rats in an Outdoor Field Enclosure

**Direction 3 — temperature / relocation topic summary.** Field_2026_Social pilot · 20 × 40 ft outdoor
paddock · WISER UWB position tracking · 5 implanted rats. **Reading time ~5 min.** **Status: candidate /
measurement-limited.** This is a focused topic summary; it is derived from — and never overrides — the
technical report (`direction3_heat_gated_relocation_report.md`) and sits under the whole-direction
[`wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md`](wiser_d3_sleep_SCIENTIFIC_SUMMARY_2026a.md).

## The biological picture

These rats are nocturnal and rest through the day, almost always inside one of two group houses. Getting up
and relocating in the daytime is therefore an *event that needs a trigger*, not background noise — and the
data say the trigger is **heat**. Daytime temperature acts as a **threshold gate**: below ~30 °C the animals
are inside essentially all day; once it crosses ~**32 °C** (which happens only at midday, and only on hot
days) they come out toward house entrances, open ground, and near-water spots, peaking at the 14:00–15:00
heat peak. The effect is **shared across the cohort** (4 of 5 rats) and is **not** an individual personality,
a circadian rhythm, or an artifact of the first days in a new paddock. What position data cannot settle is
*why* — whether this is true thermoregulation, and whether the places they move to are actually cooler.

## Finding 1 — Temperature is a *gate*, not a linear dial

Probability of being out of the enclosed house is flat and low across a wide temperature range — about
**4–6% from 20 to 30 °C** — then rises sharply: **0.08 at 30–32 °C, 0.27 at 32–34 °C, 0.34 at 34–36 °C**
(~8,400 five-minute resting bins over 10 days). The step sits near **32 °C**. This threshold shape is exactly
why every earlier *linear* or *whole-day-averaged* test looked null (ρ ≈ 0.18): a gate does not show up as a
correlation. (A parametric logistic threshold is unstable here — hot temperatures occur on only 4 days — so
the ~32 °C location is approximate, read off the dose-response curve rather than a fitted point.)

## Finding 2 — The gate is real: it survives both the sequence and the circadian control

Two independent tests, each removing a different confound, agree:

- **Within-day** (removes day-in-sequence and new-environment exploration). Because only midday crosses the
  gate, the *same rat-day* has cool (morning/evening) and hot (midday) periods. Crossing the gate raises
  out-of-house time from **0.04 to 0.31 — ΔP(out) = +0.27, day-clustered 95% CI [+0.22, +0.32]**, positive on
  **all 4** gate-crossing days.
- **Matched clock-hour** (removes circadian / time-of-day). At the *same* hour, midday P(out) is **0.32 on
  hot days but only 0.03 on cold days**; cold days stay inside at *every* hour. So the midday exodus happens
  because it is *hot*, not because it is *midday*.

Neither confound survives both tests: the within-day design controls sequence, the matched-hour design
controls circadian, and hot-days-were-early (the one residual) is exactly what the within-day test removes.
Together they **triangulate** temperature as the driver of daytime house-leaving.

## Finding 3 — A shared response, not a personality

The leaving is a mostly-**shared gate**: **4 of 5 rats** show a large above-gate / hot-day exodus (per-rat
midday hot-vs-cold gaps +0.22 to +0.47); the lone exception is the most sedentary, house-loyal animal
(12378, +0.06). Earlier in this investigation the cohort looked like it split into "house rats" and
"floaters," but that split **does not survive**: out-of-shelter floating is **not a stable trait** — between-
animal identity explains only ~2% of daily floating (intraclass correlation ≈ 0), split-half rank stability
is ≈ 0.10, and once temperature is accounted for, animal identity adds ~3%. The apparent personality was an
artifact of *when* conditions happened (the hot spell and a new burrow landing on different animals). What
*is* a stable individual axis is simply **which house an animal calls home**.

> ### Candidate — is it thermoregulation?
> The *gate itself* is well supported descriptively; that it is **behavioral thermoregulation** is
> **candidate, not established**. It is **ambient** air temperature, not in-shelter microclimate; the "out"
> destinations (entrances, near-water, open ground) are **unverified** locations in an uncalibrated
> coordinate frame and are **not shown to be cooler**; and the threshold rests on only **4 hot days**. The
> pattern — leave the enclosed house at peak heat, toward peripheral/near-water spots, then return — is
> *consistent with* heat-avoidance, but confirming it needs the measurements in "Next steps."

## What is no longer supported
- **"No detectable temperature effect on daytime movement."** A *lens* artifact — full-day and linear tests
  cannot see a threshold. The effect is a within-day, circadian-controlled **gate**, and it is real.
- **A "house rat vs floater" personality.** Out-of-shelter floating is not a stable trait (ICC ≈ 0); the
  leaving is a shared temperature gate.
- **"Hot days drive digging of the burrow" (refuge_4).** That specific burrow appeared *after* the hot peak
  and its use rose as temperatures *fell* (social adoption over days, not a heat response). Hot-day digging
  was reported by observers at *other* sites (a water tower, a NW corner); those are visible only as brief
  entrance dwelling + signal dropout and are **measurement-limited** — see Unresolved.

## Unresolved / next steps (highest value first)
1. **In-shelter temperature (a shelter thermistor)** — turn the ambient-air correlate into a microclimate
   test; the single most decisive step for the thermoregulation question.
2. **Interior shelter video (CH07/CH08)** — verify that "out of house" and "inside" mean what we think, and
   whether the destinations are cooler/shaded.
3. **Georeference the frame** — place the "out" destinations physically (entrances vs near-water vs open).
4. *(Parked)* the multi-site digging + social-following story (water tower, corners, burrow) is
   measurement-limited (digging = tag dropout; sites partly unmapped; ~4–5 relevant days) and is set aside.

## Technical references
- Report + CSVs: `outputs/direction3_heat_gated_relocation/direction3_heat_gated_relocation_report.md` (run under `D:\Field2026_analysis_out\heat_gated_relocation_*`).
- Ledger: `change_log/2026-07-12-heat-gated-relocation.md`; `ANALYSIS_STATUS.md` (Direction 3).
- Figures: `HG1_gate_curve`, `HG2_within_day_gate_contrast`, `HG3_timing`, `HG4_matched_hour_hot_cold`.
- Drivers: `analyze_heat_gated_relocation.py` (+ the individual-differences checks feeding Finding 3); offline self-tests are **code checks, not biological validation**.

---

## Quantitative appendix — how each finding was quantified

Trunk = local `[05:00, locomotor_emergence)`, rest = smoothed UWB speed `< 12.46 in/s`; 5-min bins →
nearest-ROI state. **enclosed** = the two houses; **out** = doorway/exposed/near-water/secondary-refuge
(burrow, tunnel, dropout excluded). Release day 06-28 dropped (truncated) → **10 days analyzed**. Instantaneous
$T$ = AWN air temperature at the nearest sample (≤15 min). **Candidate/descriptive throughout** — ambient
temperature, unverified frame, low-movement proxy.

**F1 · Gate (dose-response).**
- *Quantity:* $P(\text{out}) = \#\text{out}/\#(\text{enclosed}+\text{out})$ per 2 °C temperature bin.
- *Value:* 0.05 (≤30 °C) → **0.27** (32–34 °C) → 0.34 (34–36 °C); gate ≈ **32 °C** (curve step). Logistic slope +0.10/°C (positive) but the parametric threshold CI is uninformative (4 hot days).
- *Rule:* a **step** (flat then steep), not a monotone line ⇒ a gate; this is why linear/full-day tests were null.

**F2 · Within-day contrast (removes sequence).**
- *Quantity:* per rat-day with ≥3 bins each side of $G$=32 °C, $\Delta P = P(\text{out}\mid T\ge G) - P(\text{out}\mid T<G)$.
- *Value:* **+0.27** (0.04→0.31); **day-clustered bootstrap** 95% CI **[+0.22, +0.32]**, frac>0 = 1.0, across 4 gate-crossing days; relocation-rate Δ +0.06 [+0.03, +0.10].
- *Inference:* CI excludes 0 with day as the resampling unit ⇒ the within-day rise is not driven by any single day.

**F2 · Matched clock-hour (removes circadian).**
- *Quantity:* midday (12–16 h) $P(\text{out})$ on HOT (peak ≥32 °C, 5 days) vs COLD (5 days) days, clock hour held fixed.
- *Value:* **0.32 (HOT) vs 0.03 (COLD)**; cold days ~0–0.05 at every hour; all 5 rats show the gap.
- *Inference:* same hour, different temperature ⇒ effect is temperature, not a circadian midday rhythm. (Residual: hot days were early ⇒ this test alone is sequence-confounded, which F2-within-day removes.)

**F3 · Shared, not a trait.**
- *Quantity:* intraclass correlation of daily out-of-shelter floating (between-animal variance / total); split-half rank stability; per-rat gate response.
- *Value:* ICC ≈ **−0.07** (η² ≈ 0.02), split-half Spearman ≈ **0.10**, residual animal-effect after temperature η² ≈ 0.03; per-rat midday hot−cold +0.06 to +0.47 (**4/5** large).
- *Inference:* identity explains ~nil of daily floating ⇒ not a stable "floater" trait; the gate is a shared response.
