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

## Update 2026-10-08: SF07, flags, one boundary per block, production run

**SF07 (no sharp-wave reversal on any block: the probe sits above the pyramidal layer).** The user's concern: detection
then rests on the ripple channel alone, and EMG can contaminate it. So EMG is now excluded.

- **New `ephys/swr_emg.py`:** EMG from the LFP.
  - Definition: one site per shank (the first of each spike group); 300–600 Hz (≈ 300–450 Hz on our LFP); mean pairwise
    correlation over ±0.5 s.
  - It is PreprocessPipeline's EMGFromLFP, reproduced to 6e-11 on the sleep pilot's SF07 file.
  - It also computes theta/delta in ±0.5 s.
- **Flags per event:**
  - `x_rem`: REM second;
  - `x_theta`: θ/δ above the reference's NREM 95th percentile;
  - `x_moving`: IMU above the sleep scorer's own EMG threshold of the session;
  - `x_emg_lfp`: above the reference's NREM 95th percentile.
- **Evidence, all of it the user's judgement:**
  - Clicks on 6 sessions: theta-flagged 7/40 ripple; movement 49/87; LFP-EMG 53/95; unflagged 388/662.
  - Blind review of 60 SF07 block-4-night events (`swr_check_gui.py` "Review flagged sample"): flagged 1/40 ripple,
    movement/EMG-only 0/11, unflagged 18/20.
- **Rule:**
  - `excluded` = REM + theta everywhere;
  - plus movement + LFP-EMG on blocks without a sharp-wave reversal (SF07, SF11, SF12 block 3);
  - elsewhere movement and LFP-EMG stay flags only. Nothing is deleted.
- **Boundary on ripple power only** where there is no reversal: the user's SF07 boundary is ~90°. Event F1 vs the user
  (2-D → 1-D): night 0.869 → 0.918, block-1 day 0.739 → 0.822, block-4 day 0.876 → 0.849.

**One boundary per animal × probe block (`--fit block`, default).**

- The per-session NREM refit drifted. On the SF10 09-11 night (the user scored it: 202 clicks):
  - per-session refit: 10.8 % selected, NREM 110/min, F1 0.49;
  - the SF10 day session's boundary in raw units: 4.3 %, 74/min, F1 0.83 (user 55.9/min);
  - per-session normalisation + reference centres: 0.62. The user's criterion behaves like an absolute amplitude.
- So the block's reference session (the user-scored one where it exists, else the scan session) sets the boundary and the
  θ / LFP-EMG thresholds.
- Drift checks in each summary:
  - the session's own-fit fraction;
  - its NREM median ripple amplitude / the reference's. SF09's 09-09 night is ~0.6 (fewer events: 43 vs 59–79 NREM/min);
    SF10's 09-11 night ~0.8.
- Bug fixed: the event CSV wrote times with 5 significant digits. They are now kept to 0.1 ms.

**Final local check (kept events vs the user):** SF10 day 0.906 · SF09 day 0.850 · SF10 09-11 night 0.829 · SF07
0.814 / 0.853 / 0.879.

**Channels:**
- `swr_channel_scan.py` proposals use the 2-h most-NREM window (same choice as the full session on SF10).
- The sharp-wave site may be on another shank (lab PPP4 precedent), or else the least positive site.
- Reference sessions and exact block boundaries are in the channel config.
- All blocks were confirmed by the user on 2026-10-08. The XMLs are byte-identical to storage
  `3rd_rat/analysis/channel_maps_final_20261006/`.

**Production.**
- Commit `d522f78`, deployed to BioHPC; `states_1s_final` (198 files) uploaded to `swr_inputs/`.
- `run_swr.sh` was launched 2026-10-08 15:10 with all 6 animals in parallel, 18 workers each (user: ~100 cores).
- It ends with one verified `copy_to_storage` (part `swr`).

## Update 2026-10-08 (later): SF11 and SF12 block 3 do have a sharp-wave reversal; weak blocks over-select

The user: "SF11 SF12 should have a reversal."

- **The first channel scan was wrong there.** Its sharp wave was the DoG 2–50 Hz value at loose ripple-envelope peaks
  (z > 4 on a MAD z, ~115/min in NREM). Those events include cortical high-gamma bursts, which lift the top sites by
  30–100 µV. The same LFP and NREM bouts with the team's `lfp_profile_check` events (multi-column z > 4, ≥ 20 ms) give the
  team's profile (SF11 09-02 shank 1: −45 at the top … +132 at the tip).
- **New per-column measure `spw_ref_uV`.**
  $$\mathrm{spw\_ref}_c = \frac{1}{N}\sum_{k=1}^{N}\Big[\overline{y_c}(t_k \pm 15\,\mathrm{ms}) - \overline{y_c}\big(t_k + [-250,-150]\cup[150,250]\,\mathrm{ms}\big)\Big]\times 0.195\ \mu\mathrm{V}$$
  - $y_c$ = 1–50 Hz Butterworth-3 (zero-phase) LFP of column $c$;
  - $t_k$ = the $N$ NREM ripple peaks (130–200 Hz Hilbert envelope, 8-ms boxcar, z per column over NREM; max over
    columns > 4 for ≥ 20 ms; merged < 50 ms; peak = argmax of the summed z);
  - **text:** the ripple-triggered sharp wave relative to its own surroundings. Units µV, either sign. A sign change
    along a shank = a reversal.
  - `swr_channel_scan.py --spw-ref` adds it to cached scans; the old `spw_uV` is kept for the record.
- **Sharp-wave rule.** The SW site is chosen by contrast to the ripple site ($\mathrm{spw\_ref}_{rip} - \mathrm{spw\_ref}_c$,
  negative sites only):
  1. below the ripple site on its shank;
  2. else on the ripple shank, unless another shank gives ≥ 1.5× the contrast;
  3. else the least positive site (no reversal).
  - It reproduces every confirmed channel of SF07, SF08, SF10, SF12 and SF11 blocks 2/4.
  - On SF11 blocks 1/3 it would pick a neighbouring top site 4–8 µV more negative (42 for 37, 57 for 50); the
    confirmed sites are kept.
- **Result per animal (spw_ref, reference sessions).**
  - SF07: positive everywhere (least positive +39 … +72 µV), so it stays ripple-only. It is the only such animal.
  - SF11, all four blocks: the top is −55 … −100 µV, the ripple site +4 … +54 µV.
  - SF12 block 3: weak, −30 vs +31 µV.
  - The config now treats SF11 and SF12 block 3 as 2-D blocks; the channels are unchanged.
  - The SF12 09-09 weakness is a loosening connector contact, not the probe (Notion + field2026-sync
    `2026-09-11_sf12-connector-answer`).
- **But the boundary does not separate ripples on these weak blocks.** The ripple-band ratio there is ≈ 3.4–3.6 (SF07
  3.8–4.5). Reference sessions, both rules:

  | Block | Selected | NREM rate | Kept NREM |
  |---|---|---|---|
  | SF11 block 1 (ripple-only) | 22.8 % | | |
  | SF11 blocks 2–3 | 26–29 % | 136–163/min | 123–154/min |
  | SF12 block 3 | 19–20 % | 138–160/min | 127–152/min |

  - Before exclusion, SF11 blocks 2–3 run REM 93–129 and wake 98–115/min.
  - Compare 4–8 % selected and kept NREM 44–79/min on SF07/SF09/SF10, and the user's own 44–68/min.
  - So two-cluster k-means cuts into the bulk of the cloud there. **SF11 and SF12 block 3 are held from production**
    until the user scores one reference session of each in the GUI.
- **Bug fixed in `swr_auto.py --redo`.** A block reference whose summary already existed was run in the same pool as
  its dependants, which could read its stale boundary. Every reference that will be recomputed now runs first.
- **Server.**
  - The SF11 / SF12 jobs of the 15:10 run were stopped; SF07–SF10 continue. That run therefore ends without a storage
    copy.
  - `run_swr.sh` / `swr_all_animals.sh` accept `AFTER_PID`: a partial rerun waits for an earlier run on the same `OUT`
    before its single verified copy.
