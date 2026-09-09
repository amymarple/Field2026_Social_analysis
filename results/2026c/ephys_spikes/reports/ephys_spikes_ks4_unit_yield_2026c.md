# Kilosort4 unit yield, cohort `2026c`

Generated 2026-09-08T20:24:25+00:00 by `ephys/unit_yield_report.py` (git 60f3478+dirty) from `E:\3rd_rat_spikes\analysis\sort`. One ~8-h FM65 daytime session per logger (2026-09-02), PreprocessPipeline defaults (500–8000 Hz, local CMR 20–200 µm, per-shank high-amplitude artifact removal at 5 σ), Kilosort4 per shank, postprocess (dedupe → merge → autosplit → metrics → noise labels). Definitions in the script docstring. **Counts are pre-curation**: `candidate` = everything not auto-labelled noise; **`< 3 Hz` = the hippocampal count** (pyramidal cells fire sparsely, so cells are counted by rate < 3 Hz, no minimum-rate gate beyond the 0.01-Hz postprocess floor); `≥ 3 Hz` = fast-firing candidates (putative interneurons / multi-unit); `well-isolated` = ISI-violation ratio < 0.5 and SNR ≥ 5 (isolation only). Channel maps: SF07 verified; SF08/10/11/12 provisional (SF07's map); SF09 data-derived groups without geometry. Rows with stage `ks4-raw` are Kilosort4 output whose postprocess has not run yet: labels = Kilosort's KSLabel (+ the sorter runner's low-rate relabel), `well-isolated` there = KSLabel good & ContamPct < 10, amplitude/SNR medians unavailable. `post_mode` fast = features on ≤ 500 spikes per unit, no PCA autosplit, no Phy pc_features (see ephys/run_sort_session.py); full = the pipeline's all-spike passes.

## Per logger

| logger | session | h | FW | status | shanks | KS4 units | final clusters | noise | candidate units | **< 3 Hz** | < 3 Hz & well-isolated | ≥ 3 Hz | spikes | median rate Hz | median amp µV | bad ch | sort time min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | `15_20260902_082418.755` | 8.5 | FM65 | done (full) | 4 | 227 | 217 | 147 | 70 | **65** | 6 | 5 | 2,002,338 | 0.15 | 34 | - | 545 |
| SF07 | `2_20260901_002100.939` | 5.3 | FM64 | done (fast) | 4 | 236 | 202 | 60 | 142 | **126** | 9 | 16 | 4,603,347 | 0.09 | 32 | - | 183 |
| SF08 | `13_20260902_082748.094` | 9.9 | FM65 | done (fast) | 4 | 285 | 227 | 67 | 160 | **146** | 4 | 14 | 6,187,100 | 0.07 | 25 | 32 | 375 |
| SF09 | `10_20260902_083015.335` | 8.5 | FM65 | done (fast) | 5 | 267 | 195 | 49 | 146 | **136** | 10 | 10 | 5,520,578 | 0.01 | 30 | 2 4 32 36 52 54 56 58 60 62 | 259 |
| SF10 | `1_20260901_080143.036` | 4.9 | FM64 | done (fast) | 3 | 221 | 212 | 62 | 150 | **122** | 8 | 28 | 6,212,085 | 0.22 | 32 | 2 32 34 48 49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 | 97 |
| SF10 | `9_20260902_083247.835` | 8.5 | FM65 | done (fast) | 3 | 175 | 139 | 25 | 114 | **96** | 7 | 18 | 6,279,314 | 0.10 | 36 | 32 34 56 | 806 |
| SF11 | `12_20260902_083534.755` | 8.5 | FM65 | done (fast) | 4 | 233 | 206 | 81 | 125 | **115** | 3 | 10 | 4,451,641 | 0.09 | 20 | - | 276 |
| SF12 | `11_20260902_083748.804` | 9.7 | FM65 | done (fast) | 4 | 296 | 211 | 41 | 170 | **146** | 23 | 24 | 8,945,316 | 0.09 | 36 | - | 329 |
| **total** | | | | | | 1940 | 1609 | 532 | 1077 | **952** | 70 | 125 | | | | | |

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
| SF08 | 1 | post | 69 | 67 | 0 | 0 | 45 | 22 | 45 | 43 | 0 | 2 | 1,411,199 | 0.23 | 21 | 2.3 |
| SF08 | 2 | post | 49 | 48 | 0 | 0 | 31 | 17 | 31 | 26 | 2 | 5 | 1,875,650 | 0.09 | 30 | 3.3 |
| SF08 | 3 | post | 92 | 56 | 0 | 0 | 42 | 14 | 42 | 39 | 2 | 3 | 1,238,487 | 0.00 | 28 | 3.0 |
| SF08 | 4 | post | 75 | 56 | 0 | 0 | 42 | 14 | 42 | 38 | 0 | 4 | 1,661,764 | 0.15 | 25 | 2.5 |
| SF09 | 1 | post | 83 | 59 | 0 | 0 | 45 | 14 | 45 | 44 | 4 | 1 | 1,119,535 | 0.00 | 28 | 2.4 |
| SF09 | 2 | post | 18 | 18 | 0 | 0 | 14 | 4 | 14 | 10 | 0 | 4 | 1,557,668 | 1.33 | 40 | 3.2 |
| SF09 | 3 | post | 42 | 38 | 0 | 0 | 28 | 10 | 28 | 25 | 3 | 3 | 1,138,205 | 0.02 | 29 | 2.7 |
| SF09 | 4 | post | 36 | 31 | 0 | 0 | 20 | 11 | 20 | 20 | 2 | 0 | 165,708 | 0.01 | 31 | 2.7 |
| SF09 | 5 | post | 88 | 49 | 0 | 0 | 39 | 10 | 39 | 37 | 1 | 2 | 1,539,462 | 0.00 | 30 | 2.6 |
| SF10 | 2 | post | 66 | 66 | 0 | 0 | 45 | 21 | 45 | 35 | 2 | 10 | 1,908,695 | 0.22 | 33 | 2.9 |
| SF10 | 3 | post | 77 | 72 | 0 | 0 | 51 | 21 | 51 | 42 | 2 | 9 | 2,057,709 | 0.66 | 29 | 3.0 |
| SF10 | 4 | post | 78 | 74 | 0 | 0 | 54 | 20 | 54 | 45 | 4 | 9 | 2,245,681 | 0.13 | 35 | 3.7 |
| SF10 | 2 | post | 61 | 54 | 0 | 0 | 45 | 9 | 45 | 37 | 2 | 8 | 2,502,929 | 0.23 | 31 | 3.1 |
| SF10 | 3 | post | 52 | 35 | 0 | 0 | 29 | 6 | 29 | 25 | 2 | 4 | 1,851,536 | 0.10 | 31 | 3.4 |
| SF10 | 4 | post | 62 | 50 | 0 | 0 | 40 | 10 | 40 | 34 | 3 | 6 | 1,924,849 | 0.07 | 46 | 4.8 |
| SF11 | 1 | post | 57 | 51 | 0 | 0 | 28 | 23 | 28 | 26 | 0 | 2 | 647,771 | 0.08 | 19 | 2.0 |
| SF11 | 2 | post | 54 | 45 | 0 | 0 | 29 | 16 | 29 | 27 | 0 | 2 | 636,738 | 0.00 | 21 | 2.0 |
| SF11 | 3 | post | 57 | 48 | 0 | 0 | 28 | 20 | 28 | 27 | 0 | 1 | 1,288,249 | 0.10 | 18 | 1.8 |
| SF11 | 4 | post | 65 | 62 | 0 | 0 | 40 | 22 | 40 | 35 | 3 | 5 | 1,878,883 | 0.17 | 21 | 2.2 |
| SF12 | 1 | post | 42 | 38 | 0 | 0 | 28 | 10 | 28 | 19 | 2 | 9 | 2,498,468 | 0.17 | 43 | 3.9 |
| SF12 | 2 | post | 103 | 69 | 0 | 0 | 56 | 13 | 56 | 53 | 2 | 3 | 1,016,310 | 0.01 | 24 | 3.4 |
| SF12 | 3 | post | 96 | 51 | 0 | 0 | 42 | 9 | 42 | 37 | 13 | 5 | 2,466,964 | 0.07 | 62 | 6.0 |
| SF12 | 4 | post | 55 | 53 | 0 | 0 | 44 | 9 | 44 | 37 | 6 | 7 | 2,963,574 | 0.32 | 37 | 4.1 |

## Caveats

- Pre-curation numbers from one session per logger; Phy curation (merges/splits, the 'good' label) is still to be done, so treat `candidate` as an upper bound and `well-isolated` as a conservative lower bound.
- SF09's channel groups are data-derived (no geometry); SF08/10/11/12 use SF07's map provisionally; a wrong map lowers yield rather than inflating it.
- Amplitudes assume the Intan 0.195 µV/count scale (WILD gain not verified).
