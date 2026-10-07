# Sleep scoring pass 2: fixed per-animal channels, rescaling and thresholds (cohort 2026c) — plan (2026-10-07)

**Why.**
- Each session is scored with its own channels and thresholds. The failures found so far all trace to that:
  - SF07 09-05 and 09-10 (REM absorbed by a low SW threshold);
  - SF12's shank-1 channel on the 09-07 night;
  - SF07's 09-01 night threshold at 0.70.
- A history that runs across sessions (the v2 sleep-cycle analysis) is only meaningful if the state definition does not
  jump at every session boundary.
- User decision 2026-10-07 ("上吧"): do this before the v2 cycle analysis.

**Key fact (PreprocessPipeline `state_scoring.py` `_compute_sleep_state`, commit eb3dad4).** The three classification
metrics are physical before the scorer min-max-rescales them per session (`_norm_to_range`, lines 1921–1923):
- $SW$ = −(IRASA power-spectrum slope, 4–90 Hz), smoothed 15 s;
- $TH$ = max IRASA oscillatory residual, 5–10 Hz, smoothed 15 s;
- $E$ = the injected IMU EMG, $\log_{10}(\overline{\text{VeDBA}} + 0.01)$, smoothed 15 s.

The slope and the residual are insensitive to overall gain.

## Pass 1 — rescore with fixed channels and capture the raw metrics (server; local test first)

- **New variant `imu_fixch`** = `imu_nremgate` settings, with SW / theta channels fixed per animal from
  `ephys/configs/sleep_channels_2026c.yaml`. A per-session override in `sleep_channel_overrides_2026c.yaml` still wins.
- **Channel rule:** the mode of the scorer's own automatic picks over the sessions ≥ 2 h the user marked `ok`.
  - SW: SF07 23, SF08 12, SF09 52, SF10 38, SF11 12, SF12 43 (shank 2);
  - theta: SF07 31, SF08 44, SF09 56, SF10 8, SF11 35, SF12 44.
- **Raw-metric capture.** `score_sleep.py` wraps the scorer's `_norm_to_range` only while `_compute_sleep_state` runs,
  records the three arrays it is given, and passes them on unchanged (observation only). It writes
  `<session>.SleepScoreRaw.npz` (sw, th, emg on the stored `t_clus` grid).
- **Check:** min-max of the captured arrays = the stored normalised metrics, exactly.

## Pass 2 — per-animal rescaling and thresholds, reclassification (`ephys/sleep_pass2.py`)

1. **Reproduction gate (must pass first).** For every session, rescale the captured raw metrics with the session's own
   min-max, take the session's stored thresholds, and run the scorer's own post-processing:
   - `_classify_sleep_states`;
   - the idx / ints round trip;
   - `_apply_minimum_state_durations`;
   - the EMG-forced wake for `useEMG_NREM`;
   - `_fill_unassigned_states`.

   The result must equal the scorer's stored states epoch for epoch. Any mismatch stops pass 2.
2. **Per-animal rescaling.** For metric $m$ of animal $a$, pooled over its included sessions (the same inclusion as the
   analyses, i.e. without user `noise`, contact-failing and not-scored sessions):
   $$\tilde m = \operatorname{clip}\!\left(\frac{m - q_{0.1\%}}{q_{99.9\%} - q_{0.1\%}},\, 0,\, 1\right)$$
   **Text:** the same 0–1 scale for every session of an animal, robust to single outliers.
3. **Per-animal thresholds.** The scorer's own histogram-dip procedure on the pooled rescaled metrics:
   `_hist_counts_centers`, `_find_peak_locs_for_threshold`, `_find_hist_dip_threshold_between`, with the same bin loops;
   theta on non-moving epochs.
4. **Reclassify** every session with the per-animal scale and thresholds, through the same post-processing; then the
   `imu_remclean` REM rules (`score_sleep.remclean_states`) → variant **`pass2_remclean`**.
5. **Outputs.**
   - The scorer's state file with the new idx / ints / metrics / thresholds.
   - Figures rendered by the scorer's own `_save_state_figures`.
   - `score_sleep.json`, the review copy, the 1-s state export, and the review page.
   - A change table against `imu_remclean`: κ, Δ REM %, Δ NREM % per session.
6. **Probe advances.** Compare the raw-metric distributions per animal before / after SF08's (09-09 18:10) and SF12's
   (09-09 18:47, 09-10 08:35) advances. If they shift materially, split that animal's rescaling at the advance (reported,
   not silent).

## Checks and user review

- Local test on the 4 pilot sessions (LFP local) first: raw capture, reproduction gate, pass 2 end to end.
- **The user reviews** the `pass2_remclean` figures of the sessions whose scores changed materially (κ < 0.9 vs
  `imu_remclean` or |Δ REM| > 2 pp), plus a random sample of unchanged ones.
- `pass2_remclean` replaces `imu_remclean` in the analyses only after that review.

## Then

The v2 sleep-cycle analysis (plan `2026-10-06-sleep-rem-cycle-history.md`, revision 2) on `pass2_remclean`.
