# Kilosort4 unit yield, cohort `2026c`

Generated 2026-09-04T21:03:21+00:00 by `ephys/unit_yield_report.py` (git 9c82df8+dirty) from `E:\3rd_rat_spikes\analysis\sort`. One ~8-h FM65 daytime session per logger (2026-09-02), PreprocessPipeline defaults (500–8000 Hz, local CMR 20–200 µm, per-shank high-amplitude artifact removal at 5 σ), Kilosort4 per shank, postprocess (dedupe → merge → autosplit → metrics → noise labels). Definitions in the script docstring. **Counts are pre-curation**: `candidate` = everything not auto-labelled noise; **`< 3 Hz` = the hippocampal count** (pyramidal cells fire sparsely, so cells are counted by rate < 3 Hz, no minimum-rate gate beyond the 0.01-Hz postprocess floor); `≥ 3 Hz` = fast-firing candidates (putative interneurons / multi-unit); `well-isolated` = ISI-violation ratio < 0.5 and SNR ≥ 5 (isolation only). Channel maps: SF07 verified; SF08/10/11/12 provisional (SF07's map); SF09 data-derived groups without geometry. Rows with stage `ks4-raw` are Kilosort4 output whose postprocess has not run yet: labels = Kilosort's KSLabel (+ the sorter runner's low-rate relabel), `well-isolated` there = KSLabel good & ContamPct < 10, amplitude/SNR medians unavailable. `post_mode` fast = features on ≤ 500 spikes per unit, no PCA autosplit, no Phy pc_features (see ephys/run_sort_session.py); full = the pipeline's all-spike passes.

## Per logger

| logger | session | h | FW | status | shanks | KS4 units | final clusters | noise | candidate units | **< 3 Hz** | < 3 Hz & well-isolated | ≥ 3 Hz | spikes | median rate Hz | median amp µV | bad ch | sort time min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | `15_20260902_082418.755` | 8.5 | FM65 | done (full) | 4 | 227 | 217 | 147 | 70 | **65** | 6 | 5 | 2,002,338 | 0.15 | 34 | - | 545 |
| SF08 | `13_20260902_082748.094` | 9.9 | FM65 | done (fast) | 4 | 285 | 227 | 67 | 160 | **146** | 4 | 14 | 6,187,100 | 0.07 | 25 | 32 | 375 |
| SF09 | `10_20260902_083015.335` | 8.5 | FM65 | done (fast) | 7 | 90 | 87 | 15 | 72 | **66** | 4 | 6 | 3,385,483 | 0.21 | 35 | 1 2 3 4 5 6 7 11 12 13 14 15 21 22 25 32 33 36 47 49 51 52 54 55 56 58 59 60 62 63 | 328 |
| **total** | | | | | | 602 | 531 | 229 | 302 | **277** | 14 | 25 | | | | | |

## Per shank

| logger | shank | stage | KS4 units | final | good | mua | unsorted | noise | candidate | < 3 Hz | < 3 Hz & well-isolated | ≥ 3 Hz | spikes | median rate Hz | median amp µV | median SNR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SF07 | 1 | post | 47 | 63 | 0 | 0 | 27 | 36 | 27 | 22 | 2 | 5 | 1,513,790 | 0.40 | 45 | 4.2 |
| SF07 | 2 | post | 44 | 60 | 0 | 0 | 13 | 47 | 13 | 13 | 1 | 0 | 199,708 | 0.10 | 30 | 3.2 |
| SF07 | 3 | post | 69 | 55 | 0 | 0 | 19 | 36 | 19 | 19 | 2 | 0 | 173,220 | 0.18 | 33 | 3.3 |
| SF07 | 4 | post | 67 | 39 | 0 | 0 | 11 | 28 | 11 | 11 | 1 | 0 | 115,620 | 0.08 | 32 | 3.3 |
| SF08 | 1 | post | 69 | 67 | 0 | 0 | 45 | 22 | 45 | 43 | 0 | 2 | 1,411,199 | 0.23 | 21 | 2.3 |
| SF08 | 2 | post | 49 | 48 | 0 | 0 | 31 | 17 | 31 | 26 | 2 | 5 | 1,875,650 | 0.09 | 30 | 3.3 |
| SF08 | 3 | post | 92 | 56 | 0 | 0 | 42 | 14 | 42 | 39 | 2 | 3 | 1,238,487 | 0.00 | 28 | 3.0 |
| SF08 | 4 | post | 75 | 56 | 0 | 0 | 42 | 14 | 42 | 38 | 0 | 4 | 1,661,764 | 0.15 | 25 | 2.5 |
| SF09 | 1 | post | 26 | 26 | 0 | 0 | 21 | 5 | 21 | 19 | 2 | 2 | 819,030 | 0.20 | 29 | 2.6 |
| SF09 | 2 | post | 31 | 28 | 0 | 0 | 23 | 5 | 23 | 22 | 2 | 1 | 962,606 | 0.00 | 29 | 2.6 |
| SF09 | 3 | post | 8 | 8 | 0 | 0 | 5 | 3 | 5 | 3 | 0 | 2 | 721,263 | 2.39 | 27 | 2.2 |
| SF09 | 4 | post | 8 | 8 | 0 | 0 | 7 | 1 | 7 | 6 | 0 | 1 | 492,588 | 1.36 | 35 | 2.9 |
| SF09 | 5 | post | 8 | 8 | 0 | 0 | 7 | 1 | 7 | 7 | 0 | 0 | 236,996 | 1.18 | 45 | 3.4 |
| SF09 | 6 | post | 6 | 6 | 0 | 0 | 6 | 0 | 6 | 6 | 0 | 0 | 106,395 | 0.30 | 39 | 3.1 |
| SF09 | 7 | post | 3 | 3 | 0 | 0 | 3 | 0 | 3 | 3 | 0 | 0 | 46,605 | 0.48 | 48 | 3.4 |

## Caveats

- Pre-curation numbers from one session per logger; Phy curation (merges/splits, the 'good' label) is still to be done, so treat `candidate` as an upper bound and `well-isolated` as a conservative lower bound.
- SF09's channel groups are data-derived (no geometry); SF08/10/11/12 use SF07's map provisionally; a wrong map lowers yield rather than inflating it.
- Amplitudes assume the Intan 0.195 µV/count scale (WILD gain not verified).
