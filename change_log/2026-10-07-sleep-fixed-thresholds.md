# Sleep scoring pass 2: fixed per-animal channels, rescaling and thresholds (2026-10-07)

Plan: [implementation_plan/2026-10-07-sleep-fixed-thresholds.md](../implementation_plan/2026-10-07-sleep-fixed-thresholds.md).
- Why: per-session channels and thresholds caused every scoring failure found so far.
- It is also a prerequisite for a history that runs across sessions (sleep-cycle analysis v2).
- User go-ahead: "上吧", 2026-10-07.

## What changed

- **`ephys/score_sleep.py`.**
  - New variant `imu_fixch`: the `imu_nremgate` settings with SW / theta channels fixed per animal
    (`ephys/configs/sleep_channels_2026c.yaml`).
  - The channel rule: the mode of the scorer's own picks over the sessions ≥ 2 h the user marked ok.
    - SW: SF07 23, SF08 12, SF09 52, SF10 38, SF11 12, SF12 43.
    - Theta: 31, 44, 56, 8, 35, 44.
    - None is a bad channel in the current XMLs. SF12's channels are on shank 2.
  - An observation-only shim records the raw SW / theta / EMG metrics just before the scorer's per-session min-max
    (`<session>.SleepScoreRaw.npz`).
  - `write_summary` skips `score_sleep.json` files copied in from other trees.
- **New `ephys/sleep_pass2.py`.**
  - The reproduction gate.
  - Per-animal rescaling.
  - Two threshold rules: `pooled_dip` and `median_session`.
  - Reclassification with the scorer's own functions, then the `imu_remclean` REM rules.
  - Outputs: a change table and a probe-advance check. `--workers` parallelism.
- **`ephys/sleep_review.py --subset`** (review page for chosen sessions, with a note per card);
  `ephys/server/run_score_sleep.sh` gains `VARIANTS` / `REPORT`.

## Definitions

- **Raw metrics** (`_compute_sleep_state`, eb3dad4), each smoothed 15 s:
  - $SW$ = −(IRASA spectral slope, 4–90 Hz);
  - $TH$ = max IRASA oscillatory residual, 5–10 Hz;
  - $E$ = $\log_{10}(\overline{\text{VeDBA}}+0.01)$.
- **Per-animal rescaling:**
  $$\tilde m = \operatorname{clip}\big((m - q_{0.1\%,a})/(q_{99.9\%,a} - q_{0.1\%,a}),\,0,\,1\big)$$
  The quantiles are pooled over the animal's sessions that are scored, ≥ 0.5 h, not user `noise` and not
  contact-failing.
- **Threshold rule `pooled_dip`.** The scorer's histogram-dip search on the pooled rescaled metrics.
- **Threshold rule `median_session`.**
  $$\theta_a = \operatorname{median}_s \frac{\min_s m + \theta_s(\max_s m - \min_s m) - q_{0.1\%,a}}{q_{99.9\%,a} - q_{0.1\%,a}}$$
  - $\theta_s$ = the scorer's own threshold for session $s$ (the inverse of its min-max), over the animal's sessions
    the user marked ok, ≥ 2 h, with ≥ 30 % NREM in pass 1.
  - Text: the scorer's per-session judgement, made comparable across sessions and pooled by the median, so single bad
    thresholds (e.g. SF07's 0.29) are outvoted.

## Results (server, 198 sessions)

- **Pass 1** (`imu_fixch`, 19 min, 32 workers). Raw metrics captured for 198/198 sessions; the only refusals are the same
  5 frozen-IMU sessions. Local check: min-max of the captured raw metrics = the scorer's stored metrics, exactly.
- **Reproduction gate: 198/198 sessions exact.** With the session's own min-max and thresholds, `classify_chain` + the
  dip search reproduce the scorer's rescaled metrics, thresholds and states epoch for epoch.
- **`pooled_dip` → `pass2_remclean`: REJECTED for SF07.**
  - SF07's pooled SW threshold is 0.375 (its per-session ones are mostly 0.46–0.62).
  - Its REM collapses to **1.9 % of sleep** (previously 11.8 %), and NREM rises to 51 % of the recorded time.
  - This is the REM-absorption failure, now applied to every session.
  - The other animals are close to the current scores.
  - Kept on the server and locally as a documented result. Not used.
- **`median_session` → `pass2med_remclean`: the candidate.**
  - Thresholds: SW 0.44–0.57, EMG 0.54–0.59, theta 0.38–0.49, each from 9–13 sessions.
  - Totals versus the current reviewed scores (`imu_remclean`), sessions ≥ 0.5 h:

    | Animal | NREM, % of recorded | REM, % of sleep |
    |---|---|---|
    | SF07 | 41.1 → 42.1 | 11.8 → 12.7 |
    | SF08 | 36.1 → 36.5 | 16.6 → 17.3 |
    | SF09 | 37.9 → 38.3 | 13.4 → 13.5 |
    | SF10 | 39.6 → 41.1 | 15.7 → 15.6 |
    | SF11 | 36.3 → 39.6 | 16.4 → 16.4 |
    | SF12 | 43.3 → 44.0 | 15.6 → 15.6 |

  - The movement checks are unchanged: sustained movement is WAKE 0.998–1.000 (median per animal).
  - The two SF07 problem sessions: `2_20260905_093310` goes from 0.6 to 20.2 min REM (its unresolved threshold fixed);
    `5_20260910_082351` gives 46.7 min (51.6 with the per-session override).
  - Per session: median κ 0.91 against `imu_remclean`. **64 / 172 sessions changed materially** (|ΔNREM| > 5 pp or
    |ΔREM| > 2 pp): SF07 16, SF08 8, SF09 13, SF10 7, SF11 10, SF12 10.
- **Probe-advance check** (raw quantiles before / after, % of the pooled range):
  - SF07 / SF11 advances: ≤ 8 %.
  - SF08 09-09: SW median −11 %.
  - SF12 09-09 / 09-10: SW median −22 % / +33 %, theta −17 %.
  - The comparison mixes state composition with electrode position. SF12's post-09-10 08:35 data are one day session
    (the contact failure follows), so no split was made; flagged for the review.

## Review (pending)

- Page:
  `D:\3rd_rat_spikes\analysis\sleep_server\review_pass2med_remclean_review_subset_pass2med.html`.
- It holds the 64 changed sessions plus 10 random unchanged controls (list:
  `ephys/configs/sleep_review_2026c/review_subset_pass2med.csv`). Each card shows the old and new NREM / REM, κ and the
  earlier verdict.
- `pass2med_remclean` replaces `imu_remclean` in the analyses only after this review.

## Storage

- The server workdir sleep tree (incl. `imu_fixch`, `pass2_remclean`, `pass2med_remclean`) is being copied to storage
  by the parallel session (`ephys/server/copy_to_storage.sh`, UPDATE=1), then deleted (user decision 2026-10-07).
- Compact 1-s states:
  - `/workdir/hc997/ephys_2026c/sleep_states_1s_{pass2,pass2med,nremgate}`;
  - local copies in `D:/3rd_rat_spikes/analysis/sleep_server/states_1s_{pass2,pass2med}`, `sleep_states_1s_nremgate`.
- Light copies of the json and figures: `D:/3rd_rat_spikes/analysis/sleep_server/{pass2_remclean,pass2med_remclean}`.

## Verification

- `sleep_cycles_v2.py --selftest` 14 checks PASS; `sleep_cycles.py --selftest` 12 checks PASS.
- Raw capture exact (local, 2 sessions checked numerically).
- Reproduction gate 198/198 exact (server).
- The agent did not judge any figure.
