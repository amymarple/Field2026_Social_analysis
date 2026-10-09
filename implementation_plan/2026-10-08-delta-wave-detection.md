# Delta-wave detection (cortical DOWN-state LFP waves) — plan, 2026-10-08

## Goal

Detect cortical delta waves in cohort 3 (2026c) NREM sleep with the lab's method, validated against lab outputs first.

The user (2026-10-08) asked:
- to start from the local LFPs;
- to use the top channels of SF07 and SF11, which are "very cortical".

The lab method is `neurocode/lfp/FindDeltaWaves.m` + `detect_delta_waves.m`. `neuro_py` has no detector; it only loads
`<basename>.deltaWaves.events.mat`.

## Method (lab code, read 2026-10-08)

**`FindDeltaWaves`** (current version, neurocode `c2feb3b`; the band changed on 2022-10-03):
- The LFP is filtered 0.5–9 Hz with `FilterLFP`: cheby2, filtfilt, on a 1250-Hz grid interpolated over gaps.
- The derivative is low-passed 0–9 Hz (order 8) and z-scored.
- The zero crossings of the derivative give minimum → maximum → minimum triplets.
- Duration (min to min) must be 150–650 ms.
- z-scored amplitudes must satisfy (peak > 3 and end ≤ 0) or (peak ≥ 1 and end < −1.5), with the peak above its start.
- The detector finds positive waves only.

**`detect_delta_waves`**:
- NREM restrict (`SleepState.ints.NREMstate`);
- `CleanLFP [6 10]` (±0.5 s / ±0.1 s, linearly interpolated);
- immobility gate: `EMGFromLFP < 0.6` for ≥ 1 s;
- keep events with peak − end > 3 z;
- optional `verify_firing`: raise that threshold until cortical units are still suppressed at the peak.

**The user's older script** (`R_Project/PPP/codebook/pre_Ephys_pipline.m`, the PPP and HYC3 sessions):
- whole session, manual cortical channel;
- `CleanLFP [6 Inf]` (codebook version, ±2 s);
- `FindDeltaWaves(clean)`, then peak − end > 4.5.
- The codebook `FindDeltaWaves` is the 2017 version: it does no internal filtering, max duration is 450 ms and highPeak
  is 2.

## Steps

1. **Exact port** `ephys/delta_detect.py`, with `--selftest`. It covers FilterLFP / Filter / ZeroCrossings /
   FindDeltaWaves (current and 2017) / CleanLFP (current and codebook) / Restrict / the EMG gate.
2. **Replay against the lab outputs held locally** (`D:/Field2026_analysis_out/swr_reference/`, read-only copies; events
   matched by peak within ±1 sample and ±10 ms):
   - **Exact tests** (`detect_delta_waves`, threshold 3, no firing step): HP17 d36, HP18 d49, PPP20 d4.
   - **With the stored final threshold** (firing step applied): HP17 d2, HP18 d17/d52, RM10 d5.
   - **The user's older script, threshold 4.5:** PPP4 d11, PPP7 d7/d12/d14. Both FindDeltaWaves versions are tried,
     which tells us which version was on the MATLAB path.
3. **Cohort 3, SF07 and SF11 first** (local LFPs `D:/3rd_rat_spikes/analysis/lfp/`, the final channel maps, final
   sleep `imu_remclean`):
   - **Channel choice:** among the top sites of each shank, the lab rule (NREM 1–6 Hz / 1–625 Hz power), plus the
     polarity of the NREM delta wave.
   - **Check that it is a DOWN state, not a sharp wave:** there is no sorting, so the wrapper's `verify_firing` is
     replaced by the high-frequency LFP power (and, on one session, raw multi-unit activity), which must drop at the
     delta peak.
   - **No EMG gate at first:** the scorer's EMG is the IMU, and the LFP-EMG baseline is high on SF07. Report its
     effect.
4. **The rest of the cohort and the server**, only after the user accepts the channels and the check
   (`run_then_store.sh`, new storage part).

## Rules

Local first. Raw folders and the lab reference copies are read-only. No sorting. The user judges any figure.
