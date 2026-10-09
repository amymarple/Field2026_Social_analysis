# When do the rats sleep at night? Night sleep / wake with WISER; the main sleep starts at dawn, night NREM is naps (2026-10-09)

Plan (written before computing): [implementation_plan/2026-10-09-night-sleep-wiser.md](../implementation_plan/2026-10-09-night-sleep-wiser.md).

The user asked: "look in detail at when the rats wake and sleep at night, with WISER — I suspect the night is the start of
the main sleep, not naps".

## What changed

- **New `ephys/night_sleep_wiser.py`** (`run`, `--selftest`).
- **Report:** `results/2026c/ephys_spikes/reports/ephys_spikes_night_sleep_wiser_2026c.md`.
  - CSVs: `_nights`, `_hourly`, `_tau_profile`, `_naps`, `_clock_vs_tau`.
  - Figures: one raster per animal (`…_raster_<SFxx>_2026c.png`) and a summary.
- **Run folder:** `$OUT_ROOT/2026c/night_sleep_wiser_<ts>/` (per-second state / zone / IMU tables, long wakes).

## Definitions (headline)

- **Sleep:** FINAL 1-s states, records joined across splits ≤ 60 s.
- **Long wake:** WAKE runs merged across sleep interruptions < 120 s, ≥ 30 min.
- **Main sleep onset (MSO)** of night D: the first sleep epoch after the last long wake ending between sunset D and
  sunrise D+1 + 2 h. It is censored if the record covers < 3 h after it and ends before sunrise.
- **Naps:** night sleep before the MSO.
- **τ:** time since the MSO until the next long wake.
- **WISER zone:** the nearest unmasked default-track fix within ± 5 s, inside the confirmed house_1 / house_2 rectangle
  grown by 14 in, else field; no fix = unknown. Inch frame unverified; only house membership is used.

## Results

**Main sleep onset: median 06:01** (IQR 05:34–06:21; 45 of 78 animal-nights defined), about 40 min before sunrise.
- Per animal: 05:44 to 06:13.
- Unchanged with a 20 / 60-min long-wake rule (06:16 / 05:56).
- **43 of 45 onsets are in house_2**: the shared huddle.
- It follows a last long wake of median 185 min, about half of it (with a known zone) in the field.

**The night is the active phase.**

| | Nights | Morning to afternoon |
|---|---|---|
| P(asleep) | 0.09–0.24 per hour (00–05 h), 0.01–0.19 (20–23 h) | 0.62 at 06 h, 0.69–0.81 from 07 to 17 h |
| P(field), awake | 0.50–0.62 | 0.00–0.04 |
| P(field), asleep | 0.00–0.19 | |

**Your hypothesis is not supported.**
- 0 % of the 00–04 h NREM falls after the MSO, with any threshold.
- The night NREM is **naps**: median 69 min of sleep per night (IQR 54–87), mostly in the houses, between bouts of
  activity in the field.

**Ripples.**
- **Naps** have a higher ripple rate per NREM minute than the first 2 h of the main sleep in **6 / 6** animals, e.g.
  SF09 85 vs 63, SF08 111 vs 94. Their NREM depth is equal or lower (SF09 +0.47 vs +0.81 SD).
- **Within the main sleep,** the rate and depth fall together with time since onset:
  - rate +11.5 → −7.3 /NREM min around the block mean;
  - depth +0.67 → −0.84 SD over 13 h.
  - Time since onset predicts no better than the clock (3 / 6 animals): onset is so regular (≈ 06:00) that the two
    cannot be separated.

## Reading

- The high night ripple rate belongs to naps taken between active field bouts, not to the start of the main sleep. It
  is not explained by depth (Part 2 and the nap comparison).
- This is consistent with ripples being raised in the sleep that follows waking experience. That is an interpretation,
  not tested here.
- The daytime decline matches the discharge of sleep pressure from the dawn onset.

## Update: strict naps marked in the circadian NREM figure (plan Amendments 1 + 2)

**The user's nap definition:**
- before the main sleep starts;
- plenty of activity / exploring before and after.

**Implemented:** `night_sleep_wiser.py naps`. A strict nap is a sleep stretch that:
- lasts ≥ 5 min with ≥ 3 min NREM (wake gaps < 2 min bridged);
- falls inside the night's active phase, from the first long wake after 15:00 to the main sleep onset;
- has 30-min flanks before and after that are each ≥ 80 % recorded non-handling seconds, ≥ 50 % of them WAKE, with
  ≥ 5 min in the field.

**House / field smoothed as the user asked; the other agents were consulted.**
- IMU-video校准 recommended `semimarkov_decisions.hysteretic_visits` on the V3 x / y: 5-s bins, 14-in buffer, enter
  10 s, exit 30 s, flicker merge 30 s; houses only.
- Both agents flagged the cohort-1 rectangles. The cohort-3 rest positions are about 5 in (house_1) and 16 in (house_2)
  off, so the rectangles were re-centred on the failure audit's IMU-certified still medians:
  - house_1 (417.7, 716.9);
  - house_2 (621.2, 732.6).
- The house-lid events ± 5 min (`cv/configs/cohort3_lid_events.json`) are excluded from the flanks.

**Results** (primary; figure `figures/ephys_spikes_night_naps_circadian_2026c.png`, report `…night_naps_2026c.md`):
- **Count:** 115 strict naps in 57 animal-nights, median 2 per night (IQR 1–3); 49 % of the pre-onset night sleep
  stretches qualify.
- **Shape:** median 24 min, inside a house.
- **Timing:** from 21:00 to 05:00, peaking at 22:00 (0.37 onsets per night per hour), with 89 % between 21:00 and 03:00.
  None after 05:00.
- **Ripple rate** higher than in the first 2 h of the main sleep in 6 / 6 animals.

**Sensitivity:**
- exit 10 / 60 s, the cohort-1 rectangles + 21 in, and dropping the `qc_i1` field seconds give 108–119 naps, the same
  peak hour, 88–89 % between 21:00 and 03:00, and naps higher in 5–6 / 6.
- The unsmoothed rule gave 117.
- 25 naps fall on the rain nights.

## Update: naps at equal depth; REM vs SWR (plan Amendment 3, written before computing)

New `ephys/swr_rem_naps.py` (`run`, `--selftest`). Report: `…swr_rem_naps_2026c.md`; figures
`…night_naps_circadian_rem_2026c.png` (REM per NREM added to panel C) and `…swr_rem_naps_2026c.png`.

**N1: the nap advantage survives depth.**

| Comparison | Without depth (/NREM min) | With depth (/NREM min) | Animals positive |
|---|---|---|---|
| Strict naps vs the first 2 h of the main sleep | +10.4 | +10.9 [4.3, 17.6] | 5/5 |
| Strict naps vs all main sleep | +19.4 | +13.8 [7.6, 20.0] | — |

- Depth-matched quintiles within block: +12.0 [3.3, 20.7] (p 0.016), positive in 6/6.

**R1: REM per NREM by clock hour** mirrors the ripple rate:
- 0.016–0.04 at 21–23 h, when naps are almost REM-free;
- 0.05–0.11 from 00 to 06 h;
- 0.20–0.25 from 09 to 17 h.

**R2: ripple rate vs REM share across 30-min bins within block.**
- −5.8 /NREM min per 10 % REM share; −2.19 [−3.79, −0.59] with depth + hour (p 0.012).
- Negative in 4/6 animals: SF12 −7.3, SF10 −2.5; SF07 and SF11 are positive, not significant.

**R3: the last 60 s of NREM vs the run's own −300 … −120 s baseline.**
- Ratio before REM 0.72–0.85; before WAKE 0.85–1.05.
- REM − WAKE = −0.14 (p 0.025); REM-bound lower in 6/6.

**Check with all detected NREM events (theta / movement / LFP-EMG flags ignored).** The theta exclusion could create a
pre-REM drop, because theta rises before REM.
- R3 REM − WAKE = −0.09 (p 0.042), still 6/6: the drop survives, about a third of it was the flag.
- R2 −2.17 [−3.89, −0.45], but negative in only 3/6.

**Reading (plan rule).**
- The nap advantage survives depth.
- REM / SWR exclusion is supported at the transition level: ripples fall in the minute before REM more than before
  waking, in every animal, also with the flags ignored.
- Across bins, the REM-share relationship is significant pooled but not consistent across animals.
- The 24-h mirror of REM and ripple rate is partly the clock (R2 shrinks from −5.8 to −2.2 with depth + hour).

## Update: REM vs SWR at the macro scale (plan Amendment 4, written before computing)

The user clarified that "competition" means the macro scale: REM is scarce in the night naps and abundant in the day
sleep, and ripples do the opposite.

`swr_rem_naps.py macro`. Report: `…swr_rem_macro_2026c.md`; figure `…swr_rem_macro_2026c.png`; units / days CSVs.

**M1, by sleep period.** REM goes up and ripples go down as sleep goes on:

| Period | REM per NREM | Ripple rate (× block mean) |
|---|---|---|
| Strict naps | 0.055 | 1.23 |
| Main sleep, first hour | 0.083 | 1.11 |
| Main sleep, 13th hour | 0.211 | 0.87 |

**M2, across sleep periods within animal** (naps, other night sleep, main-sleep hours):
- Spearman ρ(REM per NREM, ripple rate) mean **−0.54** (p 0.005), negative in **6/6**.
- With depth partialled out: **−0.37** (p 0.018), still 6/6.
- **Macro reciprocity is established by the plan's rule.** Depth (sleep pressure) carries part of it: SF09 −0.44 →
  −0.09, SF11 −0.90 → −0.30.

**M3, across days** (one main sleep per day): ρ −0.26 (p 0.20), negative in 3/5 (SF10 −0.68, SF12 −0.64; SF07 / SF08
≈ 0).
- **No consistent day-to-day trade-off.** The reciprocity is a within-day allocation over the sleep period, not "a day
  with more REM has fewer ripples".
