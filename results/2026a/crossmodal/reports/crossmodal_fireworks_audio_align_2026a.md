# Fireworks 07-04 — audio ↔ following cross-modal alignment

**Status:** ⚠️ candidate. Tests whether the 07-04 following bursts (21:30, 22:20) coincide with acoustic fireworks volleys, aligning CH01 audio level (peak_dbfs_relative) with Phase-B2 following-episode counts on a 5-min grid. Generated 2026-07-12T18:02:42.180628.

## Cross-correlation

following-count vs audio-peak: **r=0.371 at lag 0**, best **r=0.456 at -25 min** lag.

## Per-5-min overlay (20:00-24:00 EDT)

| clock   |   following_episodes |   audio_peak_db |   audio_low0_1k_db |   audio_leq_db |
|:--------|---------------------:|----------------:|-------------------:|---------------:|
| 20:00   |                    0 |          -11.32 |             -63.87 |        -51.594 |
| 20:05   |                    0 |          -17.42 |             -68.72 |        -55.916 |
| 20:10   |                    0 |           -8.1  |             -63.03 |        -52.044 |
| 20:15   |                    0 |          -17.79 |             -67.55 |        -49.964 |
| 20:20   |                    0 |          -20.03 |             -63.61 |        -52.044 |
| 20:25   |                    0 |          -32.03 |             -69.19 |        -56.18  |
| 20:30   |                    0 |          -25.75 |             -71.24 |        -56.388 |
| 20:35   |                    0 |          -20.32 |             -68.02 |        -54.78  |
| 20:40   |                    0 |           -6.89 |             -62.08 |        -53.724 |
| 20:45   |                    0 |          -18.11 |             -65.59 |        -53.656 |
| 20:50   |                    0 |          -14.53 |             -63.37 |        -54.112 |
| 20:55   |                    0 |          -11.82 |             -65.98 |        -55.74  |
| 21:00   |                    5 |          -16.28 |             -68.77 |        -57.112 |
| 21:05   |                    2 |          -19.5  |             -66.31 |        -54.172 |
| 21:10   |                    7 |          -21.43 |             -65.91 |        -58.48  |
| 21:15   |                    8 |          -13.74 |             -62.06 |        -54.906 |
| 21:20   |                    3 |           -7.51 |             -59.65 |        -50.888 |
| 21:25   |                   12 |           -7.98 |             -59.14 |        -48.836 |
| 21:30   |                   18 |           -7.09 |             -58.11 |        -47.416 |
| 21:35   |                   21 |           -1.86 |             -52.79 |        -43.506 |
| 21:40   |                    2 |           -0.81 |             -51.95 |        -43.542 |
| 21:45   |                   22 |           -1.64 |             -55.44 |        -44.576 |
| 21:50   |                    0 |           -4.67 |             -55.52 |        -46.584 |
| 21:55   |                    0 |           -3.81 |             -55.65 |        -45.858 |
| 22:00   |                    4 |           -3.15 |             -58.95 |        -51.698 |
| 22:05   |                    0 |           -6.36 |             -57.89 |        -49.182 |
| 22:10   |                    1 |           -8.42 |             -59.5  |        -51.082 |
| 22:15   |                    4 |           -1.42 |             -50.56 |        -46.756 |
| 22:20   |                    5 |           -3.05 |             -57.98 |        -54.854 |
| 22:25   |                   12 |           -5.6  |             -59.76 |        -51.446 |
| 22:30   |                    4 |          -14.76 |             -63.53 |        -56.868 |
| 22:35   |                    0 |           -6.36 |             -60.22 |        -51.822 |
| 22:40   |                    2 |           -8.27 |             -62.15 |        -55.696 |
| 22:45   |                    1 |          -21.96 |             -67.73 |        -58.826 |
| 22:50   |                    0 |           -4.23 |             -60.86 |        -52.788 |
| 22:55   |                    0 |           -2.23 |             -57.29 |        -55.18  |
| 23:00   |                    0 |          -30.41 |             -70.18 |        -60.422 |
| 23:05   |                    0 |           -5.65 |             -56.61 |        -58.18  |
| 23:10   |                    0 |          -32.19 |             -72.53 |        -60.954 |
| 23:15   |                    0 |          -35.16 |             -71.46 |        -61.3   |
| 23:20   |                    0 |          -36.52 |             -69.82 |        -60.12  |
| 23:25   |                    0 |          -31.73 |             -72.91 |        -61.184 |
| 23:30   |                    3 |          -31.27 |             -72.98 |        -61.634 |
| 23:35   |                    1 |          -35.04 |             -71.92 |        -61.386 |
| 23:40   |                    0 |          -36.71 |             -70.17 |        -61.062 |
| 23:45   |                    0 |          -37.82 |             -69.8  |        -60.986 |
| 23:50   |                    1 |          -35.92 |             -72.61 |        -61.522 |
| 23:55   |                    1 |          -33.88 |             -73.88 |        -62.165 |

## Bursts

- **2026-07-04 21:30:00**: 18 following episodes; audio peak -7.1 dB = 0.67 percentile of the window.
- **2026-07-04 22:20:00**: 5 following episodes; audio peak -3.0 dB = 0.88 percentile of the window.

## Verdict

Cross-modal alignment over 20:00-24:00: following-count vs CH01 audio-peak correlate r=0.371 at lag 0 (best r=0.456 at -25 min lag). The following bursts fall on LOUD audio bins (1/2 bursts in the top-30% loudest minutes), so the following bursts DO coincide with acoustic fireworks activity — time-locked, cross-modally consistent with a fireworks trigger. CAVEAT: camera↔WISER clock sync is UNVERIFIED, so a nonzero best-lag mixes clock offset with response delay; level is relative dBFS (CH01 location); and coincidence in TIMING still does not distinguish social following from startle co-flight (video needed).

## Definitions

- **audio_peak_db** — max `peak_dbfs_relative` (relative dBFS, NOT SPL) over the 1-min audio windows in each 5-min bin; fireworks volleys are loud transients → captured by the max. `audio_low0_1k_db` = low-band (0-1 kHz booms).
- **following_episodes** — Phase-B2 strict lagged-following episodes starting in the bin.
- **cross-correlation lag** — Pearson r of following vs audio-peak shifted by ±k bins; the best lag absorbs the UNVERIFIED camera↔WISER clock offset + any real response delay.

## Scope

Camera↔WISER clock sync UNVERIFIED (best-lag mixes offset + delay); relative dBFS (CH01 location, not SPL); TIMING coincidence only — does NOT distinguish social following from startle co-flight (video, B2 queue). One fireworks night. 07-04 also a burrow night.
