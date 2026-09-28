# Cohort-3 neurologger offload and QC complete — final data inventory (2026-09-17)

The field phase of cohort 3 ended 2026-09-12 (animals out of the paddock 10:10, recorders stopped 11:14/11:19). Every SD card
has now been offloaded to `E:\3rd_rat_spikes`, size-checked against its console listing, scanned for holes, indexed, time-fitted
and QC'd. This entry records what the cohort produced and where the boundaries are. Regenerate the numbers from
`results/2026c/ephys_spikes/reports/ephys_spikes_session_index_2026c.csv`; do not hand-edit them here.

## Inventory

Paddock hours are FM65, sessions ≥ 10 min, excluding field-flagged sessions and truncated at each `ephys.valid_until`.
Nights count hours in 19:00–07:00.

| logger | paddock FM65 h | logger-days | nights | span | + FM64 h | home-cage h |
|---|---|---|---|---|---|---|
| SF07 | 228.5 | 9.52 | 10.3 | 09-01 19:29 → 09-12 10:24 | 22.1 | 12.02 |
| SF08 | 231.1 | 9.63 | 10.5 | 09-01 19:31 → 09-12 10:27 | 16.9 | 9.67 |
| SF09 | 229.8 | 9.58 | 10.5 | 09-01 19:33 → 09-12 10:28 | 18.8 | 10.40 |
| SF10 | 226.5 | 9.44 | 10.3 | 09-01 19:35 → 09-12 09:55 | 18.2 | 2.18 |
| SF11 | 118.9 | 4.95 | 5.7 | 09-01 19:37 → **09-07 06:10** | 18.5 | — |
| SF12 | 209.4 | 8.72 | 9.8 | 09-01 19:56 → **09-11 23:30** | 20.0 | 12.02 |
| **total** | **1,244.1 h = 51.8 logger-days** | | | | **114.6** | **46.29** |

494 sessions in the index, 148 of them counted paddock FM65 sessions ≥ 10 min. The FM64 column is the 2026-08-31 19:00 →
2026-09-01 18:20 block: usable for LFP as-is and sortable after de-glitching **with** the template-shape filter
(`implementation_plan/2026-09-07-fm64-salvage-test.md`; reject units with neighbour/peak ratio < 0.4). FM62 (08-31 daytime) is
written off: broadband/wide-impulse regimes the median rule cannot fix, and corrupt sync lanes.

## Boundaries that end a logger early

- **SF11 — implant detached 2026-09-07 06:10:45.** Measured on the card (signal → open circuit) and confirmed by video (CH07,
  inside the home box, in the dark); WISER tag 3058 rides on the implant, so its track ends there too. `ephys.valid_until`
  2026-09-07 06:10:00; the 2.04 h open-circuit tail to the 08:12:41 Stop is excluded. Logger retired, not restarted.
- **SF12 — headstage/probe contact failed 2026-09-11 23:39.** Progressive: ch 63 weak from 09-09, ch 48 from 09-10, shank 4
  joining shank 1 at half amplitude during the 09-10 afternoon, whole-shank intermittent opens through the 09-10 night, the
  09-11 day session open from its first minute and restored only by the 18:03 handling. From 23:39 of the final night it is
  broadband blow-ups alternating with open circuit. `ephys.valid_until` 2026-09-11 23:30 (4.09 h usable of that 14.51 h night).
  Not caused by either 1/4-turn advance — both were followed by normal sessions.

## Excluded material (field-flagged, kept in the index)

- **ADC / "microphone" lane, 2026-09-10 14:42 → 21:05**: 23 pieces across all five loggers. The 160 kHz ADC path injects a
  312.5 Hz full-scale pulse train into all 64 amplifier channels (spike-band noise ×7–10) and records no temperature; a firmware
  defect, not a download artefact. Quarantined out of the raw tree to `E:\3rd_rat_spikes\_quarantine_adc_lane_on\`
  (`ephys/quarantine_adc_sessions.py`), maker report in field2026-sync `from-lab/2026-09-10_maker-report-adc-mic-mode.md`.
- **Home-cage sleep sessions, 2026-09-12 10:30–10:55 starts**: real FM65 data recorded after the paddock phase, started from
  another laptop, so `pc_time: false` — a 9–20 anchor start cluster only, no end cluster, no fit. The start-cluster offset
  against the logger RTC is +74…+809 ms (field-PC sessions sit at +1,144 ms), i.e. that laptop's clock agreed with the field PC
  to ~1 s, which makes the folder RTC time good absolute wallclock to about ±2 s — enough to place the session in the day, not
  enough for cross-modal alignment (there is no paddock video/WISER after 10:10 anyway). SF07/SF08/SF09 and SF10 are clean
  signal; **SF12's 12.02 h is mostly unusable** (signal in 10 of 24 windows, continuous only 10:55–12:25) and needs a
  per-minute quality mask.
- Probe-position test recordings (09-06, another PC's console), SF10 zombie restarts (09-05), SF12's open 09-11 day session.

## Verification performed on every card

Console listing (records + total MB) against the sum of `amplifier.dat × 65/64 + adc.dat + 6.5 MB` per record — all cards
99.94–100.00 % with the residual equal to the per-record overhead; sidecar consistency (`amplifier.dat` a whole number of
128-byte samples, `time.dat` = 4 n, `analogin.dat` = 2 n); a zero-block scan of every long session (256 KB probed every 64 MB,
no holes anywhere); logger MAC in `CE_params.bin` against the animal's registered MAC — which caught one wrong-card download
(SF07's card written into the SF08 folder on 09-15, deleted after a head/middle/tail hash comparison).

## State of the data

`E:\3rd_rat_spikes` is the **only copy** (~11.5 TB) until the replacement backup drive works; SMART baseline and the re-check
procedure are in `change_log/2026-09-12-storage-health-baseline.md`. Derived data live on `D:\3rd_rat_spikes\analysis`
(`change_log/2026-09-10-analysis-root-moved-to-D.md`). **The SD cards must not be formatted**: they hold the maker's ADC-lane
records for a re-download test and are the only second copy of the final and home-cage sessions.

## What remains

Sorting and curation (channel maps settled 2026-09-08; Kilosort4 per shank), the SF08/SF12 probe-advance fingerprint check,
and the copy of the raw tree to the backup drive — that copy doubles as the full-surface read verification of E:.
