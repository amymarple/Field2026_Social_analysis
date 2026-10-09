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
