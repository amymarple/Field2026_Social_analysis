# Change log — Direction 3: heat-gated house-leaving (temperature as a gate)

**Date:** 2026-07-12 · **Type:** analysis (new stats primitives + driver + self-test + report). Candidate / descriptive.
**Plan:** `implementation_plan/2026-07-12-heat-gated-relocation.md`.
**Env:** `C:\Users\Cornell\anaconda3\python.exe` (3.13, np 2.1.3, pd 2.2.3), `KMP_DUPLICATE_LIB_OK=TRUE`.
**Data (read-only):** WISER snapshot `1stcohort_2026_2026-07-09.sqlite` (static; 06-28→07-08, 5 rats),
baseline `tag_reports_2026-06-30.sqlite`, weather `AWN-…20260628-20260709.csv`, ROIs `wiser_rois.json`.
**Run:** `D:\Field2026_analysis_out\heat_gated_relocation_20260712_0139` (via `output_paths`).

## What / why
Tests a user field hypothesis, sharpened over several iterations: daytime temperature acts as a **gate**
(a threshold), not a linear dial — below it the (nocturnal, day-resting) rats stay inside a group house;
above it they come out toward cooling/margin sites. The decisive design (user's idea) uses the fact that
**only midday crosses the gate**: on a hot day the SAME rat-day has below-gate (cool morning/evening) and
above-gate (hot midday) periods, so a **within-day** contrast removes day, rat, day-in-sequence, and
new-environment exploration — the one confound (hot days were early) the across-day view cannot beat.

**Supersedes the earlier framing** that temperature had "no detectable" effect on daytime movement: that
used full-day aggregation + linear/median-split tests, which cannot see a **threshold**. It also explains
why the "house vs floater" personality split dissolved — the response is largely a **shared gate**, not a
trait (see `change_log/…` sleep-site individual-differences note; ICC≈0 for out-of-shelter floating).

## Definitions (formula + plain text)
Trunk = local `[05:00, locomotor_emergence)`, rest = smoothed speed `< 12.46 in/s`; 5-min bins →
`classify_site_state`. **enclosed** = {house_1, house_2}; **out** = {doorway, exposed, water_1/2,
refuge_1/2/3} (cooling/margin; refuge_4 burrow + tunnel + unknown-dropout **excluded**). Release day
06-28 dropped (truncated). **instantaneous temp** = AWN `temp_c` merged to each bin (nearest ≤15 min).
- **P(out)** = out / (enclosed+out) bins.
- **within-day ΔP(out)** = `P(out|T≥G) − P(out|T<G)` per rat-day with ≥3 bins each side; **day-clustered
  bootstrap** (resample days; 95% CI + fraction of replicates >0) is the inference.
- **gate threshold** = lower edge of the first 2 °C bin whose P(out) reaches 0.12 (step-robust; a single
  logistic mis-fits a sharp step and its parametric threshold CI is uninformative). New primitives
  `logistic_fit_1d`, `logistic_threshold`, `cluster_bootstrap`.

## Results (candidate; descriptive)
1. **A temperature GATE, not a linear dial.** P(out of enclosed house) is flat (~4–6%) up to ~30 °C, then
   jumps: 30–32 °C **0.08**, 32–34 °C **0.27**, 34–36 °C **0.34**. Gate ≈ **32 °C** (curve step). A parametric
   logistic threshold is **unstable** (hot temps on only ~4 days), so the location is approximate.
2. **Within-day (headline, confound-controlled).** On a day crossing 32 °C, the **same rat-day** goes from
   P(out) **0.04 (below-gate) → 0.31 (above-gate)**, **ΔP(out) = +0.27, 95% CI [+0.22, +0.32], frac>0 = 1.0**
   (day-clustered; consistent across **all 4** gate-crossing days). Relocation rate Δ = +0.06 [+0.03, +0.10].
   Robust across gates (G=31 → +0.17; G=33 → +0.33).
3. **Timed to the heat peak.** P(out) is ~0–3% through the morning and peaks at **14:00–15:00** (hottest
   hours), then falls by evening — the exodus is a within-day midday event, which is why it survives the
   within-day design.
4. **Cooling-directed.** Of house-exits, the fraction going to a cooling/out state rises **0.40 → 0.66**
   above the gate.
5. **4 of 5 rats respond;** the sedentary house-loyalist **12378** is the exception (ΔP(out) −0.05) — the
   gate is a mostly-shared response with one non-responder.
6. **Circadian control (matched clock-hour, HOT vs COLD day).** The within-day contrast (2) confounds
   temperature with time-of-day; matching the clock hour and contrasting hot vs cold days isolates it. At
   **midday (12–16 h), P(out) = 0.32 on HOT days (peak ≥32 °C) vs 0.03 on COLD days**; cold days stay inside
   at **every** hour (P(out) ~0–0.05), so the midday leaving is **temperature, not a circadian midday
   rhythm** — all 5 rats show the hot>cold midday gap. **Triangulation:** the within-day test (2) removes
   day-in-sequence, the matched-hour test (6) removes circadian — hot days are all early, so the hot-vs-cold
   contrast alone is sequence-confounded, but the two together defeat both confounds.

## Changes
- **`src/wiser_analysis_utils.py`** — new pure primitives `logistic_fit_1d` (IRLS), `logistic_threshold`,
  `cluster_bootstrap` (day-clustered CI + frac>0).
- **`scripts/analyze_heat_gated_relocation.py`** — new driver (gate curve + robust threshold; within-day
  above/below-gate contrast with day-clustered bootstrap + per-rat; timing; cooling-directed exits;
  **matched clock-hour HOT-vs-COLD circadian control**); figures `HG1_gate_curve`,
  `HG2_within_day_gate_contrast`, `HG3_timing`, `HG4_matched_hour_hot_cold`; CSVs (`gate_curve`,
  `within_day_contrast`, `per_rat_contrast`, `timing_by_hour`, `matched_hour_hot_cold`,
  `matched_hour_per_rat`, `heat_gate_verdict`); report via `output_paths.run_dir`/`report_dir`/`write_latest_pointer`.
- **`scripts/selftest_heat_gated_relocation.py`** — offline planted PASS (logistic threshold recovery 31.97
  for a planted 32 °C gate; cluster_bootstrap positive-excludes-0 / null-straddles-0; within-day Δ recovery).
- Report → `outputs/direction3_heat_gated_relocation/…report.md`; outputs → git-ignored `D:\Field2026_analysis_out`.

## Verification
- `python scripts/selftest_heat_gated_relocation.py` → **PASS** (0 failures).
- Real run (snapshot): 8,428 interpretable bins, **10 days** (11-day window minus 06-28 release), 5 rats;
  gate ≈32 °C; within-day ΔP(out)=+0.27 [+0.22,+0.32], frac>0=1.0 across **4** gate days; timing peaks
  14–15 h; exits 0.40→0.66; **circadian control** midday HOT 0.32 vs COLD 0.03 (5 HOT / 5 COLD days).
  Figures spot-checked. Read-only DB/weather.

## Evidence status (two levels)
**Supported (descriptive, within the WISER measurement):** out-of-house time is **gated** by instantaneous
temperature (flat below ~30 °C, steep above ~32 °C); it rises **within the same day** from the cool to the
hot window (day-clustered CI excludes 0); the exodus is timed to the afternoon heat peak and is more
cooling-directed above the gate. **Candidate / not established:** that this is **thermoregulation** (ambient
not in-shelter temperature; the out-states are unverified locations in the inch frame); the **precise
threshold** (rests on only 4 hot days); the instantaneous **trigger** (per-bin leave-hazard was the weakest
piece). Needs a shelter thermistor + interior CV (CH07/CH08) + georeference.

## Deferred / non-goals
No causal/thermoregulation claim; no in-shelter microclimate; no georeference/directional claim; no reward/
IRL. Firmer threshold + trigger need more hot days + a shelter thermistor.
