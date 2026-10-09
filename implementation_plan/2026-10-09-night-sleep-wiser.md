# When do the rats sleep at night? Night sleep / wake with WISER location; is "night NREM" the start of the main sleep? (2026c)

Plan, 2026-10-09, written before computing.

## The user's request

The user asked for a detailed look, with WISER, at when the rats wake and sleep at night. The user suspects that the
night NREM with the high ripple rate (00–04 h) is the start of the main sleep, not a nap.

## Questions

- **Q1.** Per animal and night: when is the animal asleep and when awake? Where is it (house_1, house_2, field, or
  unknown), and is it moving?
- **Q2.** Is the night NREM part of the main sleep period, or are these naps inside the active phase?
- **Q3.** Do the ripple rate and NREM depth follow time since the main sleep began, rather than clock time?
- **Q4.** At the same depth, how do naps and the main sleep's start compare?

## Data (read-only)

- **Sleep:** the FINAL 1-s states (`states_1s_final`).
  - Inclusion: `sleep_schedule.included_sessions`, i.e. user `noise`, SF12 contact failure, < 0.5 h, valid_until, the
    paddock end and 09-11 19:40 excluded.
  - Records: `sleep_cycles_v2.build_records` (splits ≤ 60 s joined).
  - Clock: start_local + s, as every sleep analysis.
- **WISER:** the 2026c default tracks (`wiser/src/default_tracks.py`; V3 / B2). Positions are in the UNVERIFIED WISER
  inch frame; only membership in the confirmed house rectangles is used.
  - house_1 = (411.5, 718.6), house_2 = (613.6, 717.3); 36.4 × 26.6 in; `wiser/configs/wiser_rois.json`, as used for
    cohort 3 by the failure audit.
  - Each rectangle is grown by the audit's 14-in buffer against jitter (median ≈ 7 in, p95 ≈ 15 in).
  - Fixes flagged `m_handling` / `m_silence` / `m_off_animal` are ignored.
- **Ripples and depth:** the swr_temperature run's kept NREM events (tiers validated / good, same exclusions), and the
  raw spectral slope of `imu_fixch` (swr_depth.py).

## Definitions

- **Biological night of date D:** sunset D → sunrise D+1 (`sleep_quant.sun_times`).
- **Location per second:** the zone of the nearest valid fix within ± 5 s.
  - Zones: house_1 / house_2 if inside the buffered rectangle, else field. Unknown if no fix within ± 5 s, or the fix is
    masked.
  - A signal gap is unknown, never "left".
- **Moving per second:** the head-IMU state from the default track's fix (`imu_state` 3 = locomoting, 2 = active,
  1 = still, 0 = unusable). Unusable counts as unknown.
- **Sleep periods:** SLEEP units (Watson-type, as `sleep_schedule.episode_units`): a maximal stretch of a record with no
  wake bout > 120 s and no unknown epoch, trimmed to its sleep, ≥ 20 min.
  - Short sleep = sleep seconds outside any SLEEP unit.
- **Long wake:** a wake bout ≥ 30 min (sensitivity 20 / 60 min), merged across sleep interruptions < 120 s.
- **Main sleep onset (MSO)** of night D: the start of the first sleep epoch after the last long wake that ends between
  sunset D and sunrise D+1 + 2 h.
  - It is defined only if the record covers at least the 3 h after it, or reaches sunrise. Otherwise flagged censored.
  - Text: when the animal stops its last long active bout of the night and settles for the main sleep.
- **Naps:** night sleep (NREM + REM) between sunset D and the MSO.
- **Main sleep:** sleep from the MSO on.
- **Time since onset** $\tau$: $t - \text{MSO}$ (h). It is carried into the next day's records until the next long wake.
  The morning-round gap is handled: unknown state, $\tau$ keeps counting.

## Analyses

- **A1, per animal × night raster.**
  - Rows = nights; x = 17:00 D → 13:00 D+1.
  - Strips: the 1-s state (WAKE / NREM / REM / no record), the WISER zone (house_1 / house_2 / field / unknown), and
    IMU locomotion.
  - Marked: sunset, sunrise, MSO, long wakes.
- **A2, per night table.**
  - MSO clock time; the last long wake (start, duration, share in the field).
  - Minutes of naps vs main sleep inside the night.
  - The share of the night's NREM that is after MSO.
  - The zone at MSO.
- **A3, summary.**
  - The MSO time distribution per animal.
  - The share of night NREM after MSO, pooled and per animal.
  - The share of wake and sleep in the field vs a house, by hour.
- **A4, ripples and depth vs $\tau$.**
  - Kept NREM ripple rate and depth (z within block) in 30-min bins of $\tau$ (0–14 h, spanning the morning gap), mean
    ± SEM over animals.
  - Within block: $r = \alpha_{a,b} + f(\tau) + \beta\,\text{hour harmonics}$, comparing the clock-only, τ-only and both
    models by held-out-day likelihood. Leave-one-date-out, WLS weights = NREM minutes.
  - Reading: H_main is supported if τ predicts the rate better than the clock (ΔlogL > 0 in ≥ 4 animals), and the
    00–04 h NREM is mostly after MSO (> 50 %).
- **A5, naps vs the main sleep start.** Rate and depth in naps vs in the first 2 h after MSO: per animal means, and at
  matched depth (rate ~ depth + nap within block).

## Rules

- **WISER claims stay coarse:** house vs field only (rectangle membership with a buffer), no position in the physical
  field, gaps reported as unknown with their share. Jitter floor and anchors are stated in the report.
- **Stillness is not sleep:** sleep comes from the ephys states only.
- **Handling:** sessions start / end at battery rounds. The first and last 10 min of each record are marked as
  handling-adjacent and kept, but flagged in the raster.
- **Output:**
  - `ephys/night_sleep_wiser.py` (`run`, `--selftest`);
  - report `results/2026c/ephys_spikes/reports/ephys_spikes_night_sleep_wiser_2026c.md` + CSVs + figures (one raster per
    animal, one summary);
  - run folder `$OUT_ROOT/2026c/night_sleep_wiser_<ts>/` (per-second animal tables cached).
