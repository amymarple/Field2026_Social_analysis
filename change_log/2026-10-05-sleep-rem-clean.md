# Sleep scoring: REM with high EMG is often wake — `imu_remclean` variant (2026-10-05)

Follows [2026-09-29-sleep-scoring-pilot.md](2026-09-29-sleep-scoring-pilot.md). Trigger (user, 2026-10-05, from the
SSResults figures): NREM looks fine, but much of the scored REM has high EMG and may be wake.

## Diagnosis (`imu_nremgate`, 3 day sessions)

- **Most REM is atonic.** Median EMG in REM equals NREM (0.16 / 0.15, 0.11 / 0.08, 0.10 / 0.09). The raw head IMU is as
  still in REM as in NREM (median VeDBA 0.05 m/s² in both). Only 0.3–0.8 % of REM epochs exceed the EMG threshold.
- **REM entered from WAKE.** There are 7–12 such bouts per session, 4–7 % of REM time.
  - Median EMG 0.40–0.43 (vs 0.10–0.16 for REM entered from NREM).
  - Head moving in 27–38 % of their seconds; 23–34 % of their epochs were WAKE before the scorer's duration rules.
  - The WAKE before them lasts a median 12–24 s. So the scorer's own WAKE→REM block, which only acts after > 100 s
    of WAKE and is off by default, would catch almost none.
- **The ends of REM bouts that end in waking.** High-EMG epochs gather in the last 10 s: on SF10, 115 of them there vs
  4 in the rest of the bout. On SF08 and SF07 there are also epochs inside the bouts (287 and 178).
- **Cause.** The single EMG threshold (0.54–0.63 on the 0–1 scale) sits between rest and active movement. It separates
  moving from resting, not REM atonia from quiet wake.

## What changed

`ephys/score_sleep.py` gains derived variants (`DERIVED`). **`imu_remclean`** = the `imu_nremgate` scorer outputs,
copied and not rescored (the scorer input would be identical), plus post-rules in the driver.
- The scorer's own functions regenerate the theta epochs, the episodes and the overview figures.
- `SleepState.detectorinfo.postrules` records the rule and the seconds each rule moved.
- The base variant's files are untouched.

## Definitions

Epoch $k$ = the scorer's 1-s state at timestamp $k$ s (its 2-s spectrogram window is centred on $k$). $s(k) \in
\{\text{WAKE}, \text{NREM}, \text{REM}\}$. IMU second $j$ = $[j, j+1)$ s; $m(j) = [\text{VeDBA}_{1s}(j) \ge
\theta_a]$ with the per-animal still/active valley $\theta_a$ (SF07 0.387, SF08 0.307, SF10 0.325 m/s²).

- **Rule 1 (no REM straight out of wake).** A REM bout whose preceding WAKE run lasts $> 10$ s becomes WAKE. Duration is
  measured as the scorer does, last − first epoch timestamp, so 11 epochs count as 10 s. Implemented by the scorer's
  `_suppress_wake_to_rem_transitions(min_wake_before_rem_secs=10, preserve_rem_interruption=False)`.
  **Text:** REM after a micro-arousal of ≤ 10 s is kept; REM after longer wake is wake with theta.
  **Value:** 10 s, the user-approved choice of 2026-10-05; not tuned.
- **Rule 2 (no movement in REM):**
  $$s(k) = \text{REM} \;\wedge\; \sum_{j=k-2}^{k+2} m(j) \ge 3 \;\Rightarrow\; s(k) \leftarrow \text{WAKE}$$
  **Text:** a REM epoch becomes WAKE when the head moves in at least 3 of the 5 IMU seconds around it. Twitch bursts of
  1–2 s keep REM. **Value:** 3 of 5 s, chosen before review; not tuned.
- **Rule 3.** REM runs of ≤ 6 epochs become WAKE (the scorer's minimum REM length).
- **Order.** Rule 1 → rule 2 → (rule 1, rule 3), repeated until nothing changes. Rule 2 can open, and rule 3 can merge,
  a > 10 s WAKE gap before REM.
- **Quality measures** (per session). The share of REM epochs whose 15-s-smoothed, normalised EMG exceeds the 95th
  percentile of NREM EMG, and the share of REM seconds with $m = 1$. Both lie in [0, 1]; lower = more atonic REM.

## Results (`imu_nremgate` → `imu_remclean`)

| Session | REM time | REM share of sleep | REM epochs with EMG > NREM p95 | REM seconds with head moving | Moved to WAKE by rule 1 / 2 / 3 |
|---|---|---|---|---|---|
| SF10 `9_20260902` | 5673 → 5240 s | 22.7 → 21.3 % | 2.7 → 0.6 % | 3.6 → 0.9 % | 227 / 149 / 57 s |
| SF08 `6_20260910` | 4385 → 3838 s | 22.4 → 20.2 % | 13.3 → 5.3 % | 7.0 → 1.0 % | 265 / 228 / 54 s |
| SF07 `15_20260902` | 4292 → 3785 s | 19.1 → 17.2 % | 11.4 → 2.8 % | 7.4 → 1.0 % | 191 / 249 / 67 s |
| SF07 `9_20260901` (night) | 0 | — | — | — | unchanged (all WAKE) |

- NREM is unchanged. Agreement with `imu_nremgate`: κ 0.95–0.97.
- The REM share of sleep falls only 1.4–2.2 points. These artifacts were not the main reason for the high REM share.
- **The SF08 REM anchor gets worse.** At 14:37 (rec 22230 ± 60 s, "legs twitching") REM goes from 15 to 0 epochs,
  because the head moves there (VeDBA 0.3–5 m/s²). Either the twitching moved the head for more than 3 s, or it was an
  arousal; this is the user's call on video. If it was REM, rule 2 is too strict for vigorous twitching.

## Verification

- Every changed epoch went REM → WAKE; NREM is identical.
- After the rules, no REM follows a WAKE run longer than the 10-s rule, and the shortest REM run is 7–8 s.
- `state_editor.py` loads the `complex_system/` review copy.
- The base `imu_nremgate` files keep their 09-29 timestamps.
- Not judged by the agent: hypnograms and figures, which are left to the user.
