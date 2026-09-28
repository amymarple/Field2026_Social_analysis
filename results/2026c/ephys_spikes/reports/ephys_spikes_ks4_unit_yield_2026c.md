# Kilosort4 unit yield, cohort `2026c`

Generated 2026-09-09T05:23:20+00:00 by `ephys/unit_yield_report.py` (git 28a0ed8+dirty) from `E:\3rd_rat_spikes\analysis\sort`. One ~8-h FM65 daytime session per logger (2026-09-02), PreprocessPipeline defaults (500–8000 Hz, local CMR 20–200 µm, per-shank high-amplitude artifact removal at 5 σ), Kilosort4 per shank, postprocess (dedupe → merge → autosplit → metrics → noise labels). Definitions in the script docstring. **Counts are pre-curation**: `candidate` = everything not auto-labelled noise; **`< 3 Hz` = the hippocampal count** (pyramidal cells fire sparsely, so cells are counted by rate < 3 Hz, no minimum-rate gate beyond the 0.01-Hz postprocess floor); `≥ 3 Hz` = fast-firing candidates (putative interneurons / multi-unit); `well-isolated` = ISI-violation ratio < 0.5 and SNR ≥ 5 (isolation only). Channel maps (2026-09-08): SF07 verified; SF08/SF10/SF12 LFP-derived within-shank order (test #3, operator-inspected), SF09 reconstructed from the A5x12-16-Buz datasheet, SF11 grouping only (SF07's column sets). Dead columns are skip=1 pace makers at their shank's largest sharp-wave gradient gap; SF12's and SF08's bridged connector pins are skip=1 in place. Rows with stage `ks4-raw` are Kilosort4 output whose postprocess has not run yet: labels = Kilosort's KSLabel (+ the sorter runner's low-rate relabel), `well-isolated` there = KSLabel good & ContamPct < 10, amplitude/SNR medians unavailable. `post_mode` fast = features on ≤ 500 spikes per unit, no PCA autosplit, no Phy pc_features (see ephys/run_sort_session.py); full = the pipeline's all-spike passes.

## Per logger

| logger | session | h | FW | status | shanks | KS4 units | final clusters | noise | candidate units | **< 3 Hz** | < 3 Hz & well-isolated | ≥ 3 Hz | spikes | median rate Hz | median amp µV | bad ch | sort time min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | `15_20260902_082418.755` | 8.5 | FM65 | done (full) | 4 | 227 | 217 | 147 | 70 | **65** | 6 | 5 | 2,002,338 | 0.15 | 34 | - | 545 |
| SF07 | `2_20260901_002100.939` | 5.3 | FM64 | done (fast) | 4 | 236 | 202 | 60 | 142 | **126** | 9 | 16 | 4,603,347 | 0.09 | 32 | - | 183 |
| SF10 | `1_20260901_080143.036` | 4.9 | FM64 | done (fast) | 3 | 221 | 212 | 62 | 150 | **122** | 8 | 28 | 6,212,085 | 0.22 | 32 | 2 32 34 48 49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 | 97 |
| SF10 | `9_20260902_083247.835` | 8.5 | FM65 | done (fast) | 3 | 175 | 139 | 25 | 114 | **96** | 7 | 18 | 6,279,314 | 0.10 | 36 | 32 34 56 | 806 |
| SF12 | `0_20260901_080334.683__w0s_10800s` | 3.0 | FM64 | done (fast) | 4 | 288 | 238 | 55 | 183 | **144** | 19 | 39 | 5,850,731 | 0.17 | 39 | 3 5 10 14 17 23 36 37 38 45 46 | 88 |
| SF12 | `11_20260902_083748.804__w0s_10800s` | 3.0 | FM65 | done (fast) | 4 | 259 | 120 | 19 | 101 | **85** | 19 | 16 | 2,728,198 | 0.12 | 41 | 3 5 10 14 17 23 36 37 38 45 46 | 81 |
| **total** | | | | | | 1406 | 1128 | 368 | 760 | **638** | 68 | 122 | | | | | |

## Per shank

| logger | shank | stage | KS4 units | final | good | mua | unsorted | noise | candidate | < 3 Hz | < 3 Hz & well-isolated | ≥ 3 Hz | spikes | median rate Hz | median amp µV | median SNR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | 1 | post | 47 | 63 | 0 | 0 | 27 | 36 | 27 | 22 | 2 | 5 | 1,513,790 | 0.40 | 45 | 4.2 |
| SF07 | 2 | post | 44 | 60 | 0 | 0 | 13 | 47 | 13 | 13 | 1 | 0 | 199,708 | 0.10 | 30 | 3.2 |
| SF07 | 3 | post | 69 | 55 | 0 | 0 | 19 | 36 | 19 | 19 | 2 | 0 | 173,220 | 0.18 | 33 | 3.3 |
| SF07 | 4 | post | 67 | 39 | 0 | 0 | 11 | 28 | 11 | 11 | 1 | 0 | 115,620 | 0.08 | 32 | 3.3 |
| SF07 | 1 | post | 58 | 47 | 0 | 0 | 36 | 11 | 36 | 30 | 2 | 6 | 2,018,331 | 0.62 | 43 | 4.0 |
| SF07 | 2 | post | 57 | 49 | 0 | 0 | 34 | 15 | 34 | 33 | 2 | 1 | 613,210 | 0.01 | 39 | 3.4 |
| SF07 | 3 | post | 56 | 55 | 0 | 0 | 36 | 19 | 36 | 31 | 3 | 5 | 1,145,304 | 0.11 | 23 | 2.4 |
| SF07 | 4 | post | 65 | 51 | 0 | 0 | 36 | 15 | 36 | 32 | 2 | 4 | 826,502 | 0.03 | 20 | 2.7 |
| SF10 | 2 | post | 66 | 66 | 0 | 0 | 45 | 21 | 45 | 35 | 2 | 10 | 1,908,695 | 0.22 | 33 | 2.9 |
| SF10 | 3 | post | 77 | 72 | 0 | 0 | 51 | 21 | 51 | 42 | 2 | 9 | 2,057,709 | 0.66 | 29 | 3.0 |
| SF10 | 4 | post | 78 | 74 | 0 | 0 | 54 | 20 | 54 | 45 | 4 | 9 | 2,245,681 | 0.13 | 35 | 3.7 |
| SF10 | 2 | post | 61 | 54 | 0 | 0 | 45 | 9 | 45 | 37 | 2 | 8 | 2,502,929 | 0.23 | 31 | 3.1 |
| SF10 | 3 | post | 52 | 35 | 0 | 0 | 29 | 6 | 29 | 25 | 2 | 4 | 1,851,536 | 0.10 | 31 | 3.4 |
| SF10 | 4 | post | 62 | 50 | 0 | 0 | 40 | 10 | 40 | 34 | 3 | 6 | 1,924,849 | 0.07 | 46 | 4.8 |
| SF12 | 1 | post | 76 | 59 | 0 | 0 | 40 | 19 | 40 | 31 | 1 | 9 | 1,338,224 | 0.11 | 38 | 3.7 |
| SF12 | 2 | post | 55 | 41 | 0 | 0 | 30 | 11 | 30 | 23 | 1 | 7 | 1,292,365 | 0.54 | 34 | 3.8 |
| SF12 | 3 | post | 55 | 49 | 0 | 0 | 38 | 11 | 38 | 26 | 6 | 12 | 1,692,811 | 0.39 | 46 | 4.5 |
| SF12 | 4 | post | 102 | 89 | 0 | 0 | 75 | 14 | 75 | 64 | 11 | 11 | 1,527,331 | 0.07 | 41 | 4.6 |
| SF12 | 1 | post | 25 | 15 | 0 | 0 | 14 | 1 | 14 | 8 | 1 | 6 | 717,973 | 0.71 | 38 | 3.7 |
| SF12 | 2 | post | 25 | 22 | 0 | 0 | 16 | 6 | 16 | 15 | 0 | 1 | 249,093 | 0.48 | 30 | 3.5 |
| SF12 | 3 | post | 149 | 38 | 0 | 0 | 30 | 8 | 30 | 27 | 12 | 3 | 819,323 | 0.09 | 74 | 10.0 |
| SF12 | 4 | post | 60 | 45 | 0 | 0 | 41 | 4 | 41 | 35 | 6 | 6 | 941,809 | 0.00 | 39 | 4.2 |

## Caveats

- Pre-curation numbers from one session per logger; Phy curation (merges/splits, the 'good' label) is still to be done, so treat `candidate` as an upper bound and `well-isolated` as a conservative lower bound.
- Channel maps: SF07 verified, SF08/SF10/SF12 LFP-derived order (operator-inspected 2026-09-08), SF09 reconstructed from the datasheet, SF11 grouping only; a wrong map lowers yield rather than inflating it.
- Amplitudes assume the Intan 0.195 µV/count scale (WILD gain not verified).
