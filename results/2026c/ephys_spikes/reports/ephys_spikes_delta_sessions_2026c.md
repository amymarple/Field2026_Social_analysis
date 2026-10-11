# Delta waves (cortical DOWN states), cohort 2026c — SF07–SF12, per session

Generated 2026-10-10 from the storage summaries (`3rd_rat/analysis/delta/<SFxx>/<session>/<session>.delta_summary.json`,
VERIFY PASS, 860 files, 181 sessions). One row per session: `ephys_spikes_delta_sessions_2026c.csv`.

Code: `ephys/delta_auto.py` on BioHPC (`ephys/server/run_delta.sh`): SF07 / SF11 at commit a1dfbaa (10-09), SF08 / SF09 / SF10 / SF12 at 27e9d58 (10-10; same code, channels added). Server == local on 10 reference sessions (at least one per animal). Method and validation:
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
- **Channels** (top sites; `ephys/configs/delta_channels_2026c.yaml`):
  - SF07 col 55 (shank 1), SF11 col 11 (shank 3), user 2026-10-09;
  - SF08 col 20 (shank 4: the DOWN state is present in both probe blocks), SF09 col 21, SF10 col 9 (shank 2), SF12 col 11
    (shank 3, a clean shank), user 2026-10-10.

## Per animal

| | SF07 | SF08 | SF09 | SF10 | SF11 | SF12 |
|---|---|---|---|---|---|---|
| Sessions ≥ 10 min | 36 | 31 | 30 | 32 | 24 | 28 |
| With the MUA check | 27 | 25 | 25 | 26 | 18 | 21 |
| FM64 (no check, on hold) | 6 | 6 | 5 | 6 | 5 | 6 |
| No final sleep states (skipped) | 3 | 0 | 0 | 0 | 1 | 1 |
| NREM (h) | 90.0 | 89.1 | 93.5 | 96.4 | 45.8 | 91.3 |
| Events / verified (thousands) | 193 / 73 | 200 / 85 | 154 / 78 | 165 / 70 | 86 / 61 | 159 / 60 |
| Share verified per session, median | 0.43 | 0.47 | 0.56 | 0.48 | 0.82 | 0.49 |
| Verified per NREM minute, median | 15.4 | 17.1 | 15.7 | 13.5 | 26.6 | 13.8 |

## Caveats

- **The MUA sites differ by animal.**
  - SF07's top sites carry no units, so its events are checked on shank-1 spiking sites below them.
  - SF11's top sites show the DOWN state themselves.
  - A lower verified share on SF07 is partly the weaker check. It is not necessarily fewer DOWN states.
- **The per-event check is noisy.** About 6 spikes are expected in ±50 ms, so about 15 % of events with no true change
  still reach ≤ 0.5. Compare rates between animals with care; within an animal across days is safer.
- **There is no EMG gate.** NREM is already IMU-gated by the scorer.
- **The detector keys on "a peak, then a deep trough".** Polarity was checked on the channel, not enforced.
- **The strength of the check differs by animal.**
  - SF07 and SF12: no units at the top, so the check runs on deeper spiking sites.
  - SF10: few units at the top (1–5 Hz).
  - SF09: sits low (the user does not expect much), although col 21 itself carries units (24 Hz, ratio 0.15 on 09-02).
  - SF08 (col 20) and SF11 (col 11): units at the delta site itself, the strongest check.
- **SF12 `17_20260911`** (final night, user `noise`): its `valid_until` of 23:30 is not applied, because the SWR quality
  table has an empty `use_until` for it. Exclude the session.
