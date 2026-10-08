# Automatic SWR detection: the lab's DetectSWR ported, its manual `check` step replaced, and validated against the user (2026-10-07)

Plan: [implementation_plan/2026-10-07-swr-detection-automation.md](../implementation_plan/2026-10-07-swr-detection-automation.md).

User requests, in order:
- "Read DetectSWR, save me the manual labor, then do all the ripple detection."
- Use the user's existing manual sessions instead of asking for new labels.
- The noise channel must be a cortical, top, ripple-free site.
- A GUI like the 2-D helper.
- After scoring SF10 and SF09: "sounds good, go for it".

Audits:
- a Fable audit of the evaluation;
- the user's second audit;
- a Fable SOTA review;
- a rippl-AI method review.

Reports: `D:/Field2026_analysis_out/2026c/swr_*fable*.md`.

## What changed

- **`ephys/swr_detect.py`: an exact port of `neurocode/SharpWaveRipples/DetectSWR.m`.**
  - Covers features, candidates, k-means split, localisation and troughs, the 2022-10 variant, CleanLFP, and the
    helper's click propagation; `--selftest`.
  - On 17 lab sessions: identical candidate samples; features within 1e-11; replay of the user's clicks = their final
    `ripples.events.mat`, every event identical.
  - `propagate_clicks` reproduces the saved idx1 on 18/18 scoring files.
  - CleanLFP with fixed [8 5] = the user's `bad` on 17/17.
- **Evaluation:**
  - `ephys/swr_auto_eval.py` (first pass);
  - `ephys/swr_judge.py`: single-example features, context features, leave-one-animal-out judges, `evaluate` (lab,
    three separate layers, hard replay check) and `evaluate-c3` (cohort 3).
  - Reference set `configs/swr_reference_sessions.yaml`. Local copies (read-only, SHA-256 manifests):
    `D:/Field2026_analysis_out/swr_reference/`.
- **`ephys/swr_check_gui.py`: a browser version of the helper.**
  - Scatter, ±0.5 / ±2 s popup, live 1-NN propagation.
  - Blind until "done"; the automatic labels then use the production rule.
  - Click mapping is corrected for the displayed canvas size, with a hover preview.
- **Cohort 3, production:**
  - `ephys/swr_channel_scan.py`: per-block channel proposal plus a profile figure.
  - `configs/swr_channels_2026c.yaml`: channels per animal × probe block; boundaries = exact post-move session names.
  - `ephys/swr_auto.py`: the production driver.
  - `ephys/server/run_swr.sh`, plus part `swr` in `copy_to_storage.sh`.
- **The user's cohort-3 clicks:** `configs/swr_review_2026c/`.

## Definitions

- **Event match.** A detected event matches a user event when their trough peaks are within 10 ms; the matching is
  greedy one-to-one on sorted peaks.
  - $P = n_{matched}/n_{auto}$, $R = n_{matched}/n_{user}$, $F1 = 2PR/(P+R)$.
  - The user reference is the replay of the user's clicks through the same localisation (= their final file).
- **Ripple-band ratio of a column.**
  - $\rho_c = \mathrm{median}_{t\in\text{peaks}} e_c(t) / \mathrm{median}_{t\in\text{random}} e_c(t)$.
  - $e_c$ is DetectSWR's 80–250 Hz envelope (Gaussian difference-of-Gaussians, |·|, smoothed); the peaks are NREM ripple
    peaks of the ripple column (z > 4, ≥ 50 ms apart).
  - About 1 means no ripple content; the pyramidal layer is about 4–5. It is used to vet noise channels.
- **NREM-fitted boundary.**
  - z-scores and a 2-cluster k-means are fitted on the non-bad candidates in NREM seconds (final 1-s states, ≥ 10 min).
  - Every non-bad candidate is labelled by its nearest centre.
  - With < 10 min NREM, the session borrows μ, σ and the centres of the nearest NREM-fitted session of the same animal ×
    channel block (same channels, same gain).

## Results

- **Lab sessions (17, leave-one-animal-out), median event F1:**
  - standardized k-means 0.914;
  - the user's own clicks from other days of the same animal 0.918;
  - judges 0.86–0.91;
  - with vs without the sleep-state feature: identical.
  - One click flipped can move idx1 by up to several-fold; dropping one moves it by a median of 0.04–1 %.
- **Cohort 3, the user scored two sessions in the GUI:**
  - SF10 `6_20260906` (114 clicks): automatic vs user P 0.94 / R 0.91 / F1 0.92; NREM rate 78.8 vs 81.4 /min.
  - SF09 `6_20260908` (190 clicks): F1 0.87; 68.7 vs 68.4 /min.
  - The user's clicks transferred from the other animal: 0.84 / 0.85.
  - Judge accuracy on the user's clicks: 0.65–0.70 (majority baseline 0.61–0.63).
- **Literature.** Inter-expert F1 0.70 ± 0.13 (Navas-Olive 2022).
  - rippl-AI was not adopted: zero-shot ~0.5, untested on field noise.
  - Fernández-Ruiz / Oliva use the same DetectSWR lineage.
- **Noise channels.**
  - 10 of 17 lab sessions used a noise channel that carries ripples (ρ 1.4–3.1; PPP7 ch16, PPP20/21/23 ch171).
  - Clean ones: CTX/PFC channels, ρ 0.87–1.27.
- **Robustness (8 SF09 + 8 SF10 sessions from storage).**
  - The all-candidate k-means drifted on wake-heavy nights: 19.8–24.9 % of candidates, 110–148 wake events/min
    (SF10 09-09 / 09-11 / 09-01 nights, SF09 09-09 night).
  - With the NREM fit: SF10 09-09 night 5.5 %, wake 26/min; SF09 09-09 night 4.7 %, 22/min.
  - With the NREM fit plus a borrowed boundary, SF10 09-01 (96 % wake): 2.4 %, 13.7/min.
  - The 09-11 night (females released) is still 10.8 %, 57 wake events/min, under the user's GUI review (port 8767).
  - The scored sessions are unchanged by the NREM fit (F1 0.922 / 0.868).
- **Channels (`swr_channel_scan.py`, 2-h most-NREM window, same choice as the full session on SF10).**
  - SF07: all 4 blocks have positive sharp waves everywhere = above the pyramidal layer. Flagged: no reversal; noise not
    ripple-free.
  - SF11: cortex, a negative control.
  - SF12 block 3: degrading.
  - SF12 block 2: no usable session, so skip.
  - SF09/SF10 keep the GUI-scored channels.

## Not done / next

- The user confirms the channel proposals (profile figures in `D:/Field2026_analysis_out/2026c/swr_channel_scan/`) and
  reviews the SF10 09-11 night in the GUI.
- Then the BioHPC run: deploy the commit, upload `states_1s_final` to `swr_inputs/`, run `run_swr.sh` → storage
  `3rd_rat/analysis/swr/`, and spot-check server vs local.
- Per-event flags exist; strict/inclusive tiers and wake-event filters are cut downstream.
