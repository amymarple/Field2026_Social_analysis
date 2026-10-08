# Automating SWR detection (replace the manual `check` step of DetectSWR) — plan, 2026-10-07 (revised the same day)

## Goal

The user detects ripples with the lab's `neurocode/SharpWaveRipples/DetectSWR.m` in `check` mode. The manual work is:
- choosing three channels per session (ripple, sharp wave, noise);
- `CleanLFP` thresholds;
- clicking 20–76 candidates in the 2-D (sharp-wave depth `swDiff`, ripple power `ripPower`) scatter after looking at
  each one's ±0.5 s trace; every other candidate takes the nearest click's label.

The goal is to make that automatic, check it against the user's own manual results, and run it on all cohort-3
sessions (dorsal CA1 only).

## Reference data

Copied read-only to `D:/Field2026_analysis_out/swr_reference/`, with SHA-256 manifests; `configs/swr_reference_sessions.yaml`.

- **17 complete manual check runs.**
  - Mouse:
    - HYC3 d2;
    - PPP4 d11;
    - PPP7 d7, d10, d12, d14;
    - PPP8 d8, d14;
    - PPP20 d4, d5, d8;
    - PPP21 d4, d5, d7;
    - PPP23 d7, d8.
  - Rat: HP17 d2.
  - Each has `DetectSWR_manual_scoring.mat` and the final events of the same run.
- **HMC1 d10 (rat) is excluded.**
  - It is a partial scoring file from the 2022-04 DetectSWR, which ran with useSPW on.
  - The reference is not reproducible.
- **Final events only (not manual check runs):**
  - PPP7 d8 dorsal (its scoring file is the ventral run);
  - RM10 d5, HP17 d36, HP18 d17/49/52 (automatic DetectSWR + spike filter + EventExplorer).
- **Cohort 3**: the user scored SF10 `6_20260906_080449` (114 clicks) and SF09 `6_20260908_072057` (190 clicks) in
  `swr_check_gui.py`. The clicks are in `configs/swr_review_2026c/`.

## Findings (all numbers are event F1 at peak ±10 ms against the user's result)

1. **Faithful port.**
   - `swr_detect.py` reproduces DetectSWR exactly: identical candidates, features to 1e-11.
   - Replaying the user's clicks gives their final file in all 17 sessions.
   - `propagate_clicks` = the helper's 1-NN rule, exact.
   - CleanLFP with fixed [8 5] = the user's `bad` on 17/17.
2. **The manual result is a 2-D partition.** idx1 is the 1-NN partition of the 20–76 clicks, so agreement with it rewards
   reproducing a 2-D boundary. The user's waveform judgement lives only in the clicks (Fable audit).
3. **Lab data, leave-one-animal-out:**
   - standardized k-means: median 0.91;
   - the user's own clicks from other days of the same animal: 0.92;
   - waveform judges: 0.86–0.91;
   - no-state = with-state.
   - A single flipped click can move idx1 by up to several-fold.
4. **Cohort 3 (in domain):**
   - k-means: 0.92 (SF10) / 0.87 (SF09);
   - the user's clicks transferred from the other animal: 0.84 / 0.85;
   - judges trained on the other animal and/or the lab clicks: 0.78–0.89;
   - judge accuracy on the user's clicks: 0.65–0.70 (majority baseline 0.61–0.63).
5. **Literature (Fable SOTA review):**
   - inter-expert F1 0.70 ± 0.13 (Navas-Olive 2022);
   - rippl-AI/CNN zero-shot ~0.5 on new species, ~0.7 after retraining;
   - noise robustness untested on field noise → not adopted (user, 2026-10-07).
6. **Noise channel.**
   - 10 of 17 lab sessions used a noise channel that carries ripples (ripple-band ratio 1.4–3.1).
   - User rule: a cortical, top, ripple-free channel.
   - Cohort 3 has no fully clean site on SF10 (best 1.36, corr 0); SF09 col 51 is 1.14.
7. **Robustness.**
   - An all-candidate k-means drifted on wake-heavy nights: 20–25 % of candidates, 110–150 wake events/min (SF10
     09-01/09-09/09-11 nights, SF09 09-09 night).
   - Fit on NREM candidates only: same agreement on the scored sessions (0.922 / 0.868). Nights: see the change log.

## Decision (user, 2026-10-07: "sounds good go for it")

The automatic default:
- DetectSWR candidates;
- CleanLFP bad;
- standardized k-means fitted on NREM candidates;
- DetectSWR check-mode localisation, with rat parameters.

Per-event flags, never deletions:
- strength (SwMax / RipMax local z, for strict / inclusive tiers downstream instead of a per-session "relaxed"
  criterion);
- state and IMU movement at the peak (the sleep scorer's `emg`; no recomputation);
- ripple-band envelope ratio per shank and on the noise column.

The sleep state is not a classifier input, which keeps state comparisons clean.

## Steps

1. Robustness on 16 SF09/SF10 sessions (days, wake-heavy nights, FM64, the 09-11 night): done for the all-candidate fit;
   the NREM-fit rerun is in progress.
2. Channels per animal × probe block (`swr_channel_scan.py` on one NREM-rich stable session per block → proposal +
   profile figure; the user confirms → `configs/swr_channels_2026c.yaml`).
   - Blocks:
     - SF07: 4;
     - SF08: 2;
     - SF09: 1;
     - SF10: 1;
     - SF11: 4 (tiny ripples, no clear reversal: maybe cortex or poor impedance; low contrast, screen per session);
     - SF12: 3 (block 2 has no usable session; block 3 ends at the contact failure).
   - Block boundaries use the exact post-move session names.
3. The user spot-checks 1–2 wake-heavy sessions in the GUI.
4. BioHPC: deploy the commit and upload `states_1s_final` to `swr_inputs/`, then run `server/run_swr.sh` (ends via
   `run_then_store.sh`, part `swr` → storage `3rd_rat/analysis/swr/`). Then spot-check server vs local on the pilot
   sessions.

## Rules

- Raw and reference data are read-only; LFP is read from storage; local first.
- The agent does not judge figures.
- Any departure from DetectSWR is a named option.
- No labels are requested before the evaluation shows where the method is wrong (Fable audit + the user's second audit).
