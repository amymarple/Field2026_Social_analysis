# Delta waves (cortical DOWN states), cohort 2026c — SF07 and SF11, per session

Generated 2026-10-09 from the storage summaries (`3rd_rat/analysis/delta/<SFxx>/<session>/<session>.delta_summary.json`,
VERIFY PASS, 276 files). One row per session: `ephys_spikes_delta_sessions_2026c.csv`.

Code: `ephys/delta_auto.py` at commit a1dfbaa on BioHPC (`ephys/server/run_delta.sh`). Method and validation:
`change_log/2026-10-08-delta-wave-detection.md`.

## How to use the events

- **Load:** `<session>.deltaWaves.events.mat` (the lab's struct, readable like any `deltaWaves.events.mat`) or
  `<session>.delta_events.csv`. Times are session seconds (LFP sample k ↔ k / 1250 s).
- **Event filter:** `verified == 1` (multi-unit firing at the peak ≤ 0.5 × the −1…−0.4 s baseline) and
  `after_use_until == 0`. All detected events are kept, so a different threshold can be applied with `mua_ratio`.
- **Session filter:**
  - FM64 sessions (before the 09-01 evening round) have no check (`testable = 0`): use them only unverified, or not at
    all.
  - Read `info`: probe-advance settle windows, the five females from 09-11 19:40, and SF11's `SF11_ripples_lost` (that
    tag concerns the CA1 ripples, not the cortical delta).
  - Also read `sleep_verdict` / `sleep_tags`: e.g. SF07 `8_20260904` has the review verdict 'bad' (REM uncertain).
- **Channels:** SF07 col 55 (shank 1 top), SF11 col 11 (shank 3 top). Both are top, cortical sites, accepted by the user
  on 2026-10-09.

## Per animal

| | SF07 | SF11 |
|---|---|---|
| Sessions ≥ 10 min | 36 | 24 |
| With events | 33 | 23 |
| With the MUA check | 27 | 18 |
| FM64 (no check) | 6 | 5 |
| Skipped (no final sleep states) | 3 | 1 |
| NREM | 90.0 h | 45.8 h |
| Events / verified | 192 529 / 73 153 | 85 962 / 61 258 |
| Share verified per session, median [range] | 0.43 [0.24–0.62] | 0.82 [0.68–0.94] |
| Verified delta waves per NREM minute, median [range] | 15.4 [9.8–19.4] | 26.6 [20.6–36.0] |

## Caveats

- **The MUA sites differ by animal.**
  - SF07's top sites carry no units, so its events are checked on shank-1 spiking sites below them.
  - SF11's top sites show the DOWN state themselves.
  - A lower verified share on SF07 is partly the weaker check. It is not necessarily fewer DOWN states.
- **The per-event check is noisy.** About 6 spikes are expected in ±50 ms, so about 15 % of events with no true change
  still reach ≤ 0.5. Compare rates between animals with care; within an animal across days is safer.
- **There is no EMG gate.** NREM is already IMU-gated by the scorer.
- **The detector keys on "a peak, then a deep trough".** Polarity was checked on the channel, not enforced.
- **The other animals are not processed yet.** Their top sites were checked on one local session each (change log,
  2026-10-09):
  - SF08: shanks 3 and 4 are cortical;
  - SF09: cols 21 and 51;
  - SF10: few units at the top of shanks 2 and 4;
  - SF12: no units at the top.
