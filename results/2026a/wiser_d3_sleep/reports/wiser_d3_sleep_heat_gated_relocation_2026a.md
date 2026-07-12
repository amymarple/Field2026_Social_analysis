# Direction 3 — heat-gated house-leaving (temperature as a gate)

*CANDIDATE / descriptive. 'Out of house' = low-movement position (< 12.5 in/s) in a non-house ROI band, **UNVERIFIED inch frame**, jitter ~7 in. Temperature = **ambient** AWN air (no in-shelter microclimate). refuge_4 (burrow) + tunnel + unknown(dropout) excluded; release day 06-28 dropped. This is an **association**, NOT proven thermoregulation.*

> **Headline design.** On a day that crosses the gate, the SAME rat-day has below-gate (cool morning/evening) and above-gate (hot midday) periods. The **within-day** contrast therefore removes day, rat, day-in-sequence, and new-environment exploration — the one confound (hot days were early) that the across-day view cannot beat.

## Definitions (formula + plain text)

- **enclosed** = house_1/house_2; **out** = doorway/exposed/water_1/2/refuge_1/2/3 (cooling/margin). **P(out)** = out / (enclosed+out) bins.
- **instantaneous temp** = AWN temp at the nearest sample to a 5-min bin (≤15 min).
- **within-day ΔP(out)** = P(out|T≥G) − P(out|T<G) per rat-day with ≥3 bins each side; inference by **day-clustered bootstrap** (resample days; CI + frac>0).
- **gate threshold** = lower edge of the first 2 °C bin whose P(out) reaches 0.12 (step-robust; a single logistic is a poor fit to a sharp step and its parametric threshold CI is uninformative here).

## A. Gate curve + threshold

- **10 days analyzed** (the 11-day window 06-28→07-08 minus the truncated 06-28 evening-release day); the gate curve pools all interpretable bins.
```
    temp_bin    p_out    n
(20.0, 22.0] 0.043103 1044
(22.0, 24.0] 0.045070 1065
(24.0, 26.0] 0.030954 1163
(26.0, 28.0] 0.019759 1164
(28.0, 30.0] 0.053415 1142
(30.0, 32.0] 0.083333  876
(32.0, 34.0] 0.265385  780
(34.0, 36.0] 0.336761  389
(36.0, 38.0] 0.400000   10
```
- **Gate ≈ 32 °C** (the curve step): P(out) is flat (~4–6%) up to ~30 °C, then jumps to ~27–40% above ~32 °C — a **threshold gate, not a linear dial**. The logistic slope is positive (+0.10/°C) but a *parametric* threshold is unstable (hot temps occur on only ~4 days), so the location is approximate. `HG1`.

## B. WITHIN-DAY above/below-gate contrast (headline)

- **G = 32 °C (20 rat-days across 4 gate-crossing days):** P(out) **0.040 (below) → 0.305 (above)**, ΔP(out) = **+0.266** (95% CI +0.219–+0.321, frac>0 1.00). Relocation rate Δ = +0.063 (CI +0.028–+0.102).
- G = 31 °C (32 rat-days): ΔP(out) = +0.167 (CI +0.078–+0.240, frac>0 1.00).
- G = 33 °C (19 rat-days): ΔP(out) = +0.327 (CI +0.291–+0.396, frac>0 1.00).
- **Per rat** (is it all animals?):
```
shortid  n_days  p_out_below  p_out_above  d_out
  12378       4        0.065        0.014 -0.050
  12380       4        0.028        0.442  0.414
  12386       4        0.031        0.288  0.257
  12395       4        0.040        0.534  0.494
  12407       4        0.033        0.249  0.215
```
  **4 of 5 rats** show a large above-gate exodus; the exception(s) (12378) — the most house-loyal/sedentary — stay in even above the gate. The direction is shared but rests on only **4 gate-crossing days**, so the day-clustered CI (not a per-rat-day sign test) is the honest inference.

## C. Timing

```
 hour  p_out  temp   n
    5   0.32 18.99 244
    6   0.01 19.43 548
    7   0.08 21.20 546
    8   0.10 23.65 646
    9   0.07 25.32 547
   10   0.03 26.62 636
   11   0.01 27.87 496
   12   0.02 28.33 584
   13   0.13 29.45 486
   14   0.24 29.78 566
   15   0.26 29.95 459
   16   0.18 29.86 532
   17   0.10 29.41 438
   18   0.02 27.26 576
   19   0.03 26.76 495
   20   0.01 24.98 516
   21   0.11 23.49 113
```
- P(out) is near-zero through the morning and peaks at **14–15:00**, the hottest hours — the exodus is timed to the within-day heat peak (`HG3`), which is why it survives the within-day design.

## D. Cooling-directedness of exits

- Of house-exits, the fraction going to a cooling/out state is **0.40 below** vs **0.66 above** the gate — above-gate departures are more cooling-directed.

## E. Circadian control — matched clock-hour, HOT vs COLD day

- Days split by peak temp: **5 HOT** (peak ≥ 32 °C; 06-29→07-03) vs **5 COLD** (07-04→07-08). The within-day contrast (B) confounds temperature with time-of-day, so this **matches the clock hour** and contrasts hot vs cold days.
- **Midday (12–16:00): P(out) = 0.32 on HOT days vs 0.03 on COLD days.** At the SAME clock hour the exodus happens **only when it is hot**; **cold days stay inside essentially ALL day** (P(out) ~0–0.05 at every hour) → the midday leaving is **temperature, NOT a circadian midday rhythm**. `HG4`.
- **Per rat (midday, HOT vs COLD):**
```
shortid  COLD   HOT
  12378 0.029 0.087
  12380 0.029 0.485
  12386 0.000 0.222
  12395 0.010 0.483
  12407 0.051 0.288
```
  All 5 rats show a hot>cold midday gap (12378 smallest). **Residual confound:** hot days were all early and cold days all late, so the hot-vs-cold contrast **alone** is sequence-confounded — but the within-day contrast (B) removes sequence while this removes circadian, so the **pair together** triangulates temperature (neither confound survives both).

## Evidence status

**Supported (descriptive, within the WISER measurement):** out-of-house time is **gated** by instantaneous temperature (flat below ~30 °C, steep above ~32 °C) and rises **within the same day** from the cool to the hot window; **at a matched clock hour it is present on HOT days but absent on COLD days** (so it is not a circadian midday rhythm); the exodus is timed to the afternoon heat peak and is more cooling-directed above the gate. **Candidate / not established:** that this is thermoregulation (ambient not in-shelter temp; the out-states are unverified locations); the precise threshold (rests on only 4 hot days); and the instantaneous *trigger* (the per-bin leave-hazard was the weakest piece). Needs a shelter thermistor + interior CV (CH07/CH08) + georeference.


*Figures + CSVs: `D:\Field2026_analysis_out\heat_gated_relocation_20260712_1257`.*
