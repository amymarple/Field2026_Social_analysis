# Head-IMU inertial fusion with WISER (V4): IMU processing first, then a 6-axis ESKF + RTS smoother (cohort 2026c)

- **Status:** approved by the user 2026-09-29 (brief relayed by the main session); written **before** coding. Every
  rule below that turns data into a choice is fixed here and evaluated on the **tuning night only**.
- **Direction:** `wiser_baseline` (a measurement question; no behavioural claim).
- **Code (new):** `wiser/scripts/build_imu_wiser_cache.py` (Phase A, `--selftest`), `wiser/scripts/analyze_wiser_ins_fusion.py`
  (Phases B–C, `--selftest`). Existing code (`ephys/make_imu.py`, `ephys/read_imu.py`, the two earlier WISER pilots) is
  **imported, never edited**.
- **Config:** `wiser/configs/wiser_ins_fusion_2026c.json` (inputs, rules, grids; the driver writes the tuned values into
  `tuned`, marked "fitted on 2026-09-08/09").
- **Report:** `results/2026c/wiser_baseline/reports/wiser_baseline_ins_fusion_2026c.md`, figures on the same stem under
  `results/2026c/wiser_baseline/figures/`, pointer `run_manifest_ins_fusion_2026c.json` (the folder's
  `run_manifest.json` is not touched). Bulk: `D:\Field2026_analysis_out\2026c\wiser_ins_fusion_<ts>\`.

## Question

The smoothing pilot (`results/2026c/wiser_baseline/reports/wiser_baseline_imu_smoothing_pilot_2026c.md`) used the head
IMU only as per-second motion-state labels (+0.5–1.8 % over B2′). The WISER tag and the IMU sit on the same rigid
headstage (user, 2026-09-29), so the measured head acceleration **is** the tag's acceleration (up to a lever arm of a
few cm), and head yaw becomes observable from WISER fixes while the rat accelerates. Question: does a proper 6-axis
inertial fusion (error-state Kalman filter driven by the accelerometer and gyroscope, corrected by WISER fixes, plus an
RTS smoother) predict held-out WISER fixes better than the best position-only smoother B2′? And, first (user: "if the
IMU processing is poor it cannot improve WISER"), can the IMU processing itself be improved and validated?

## Facts this rests on

- Tag and IMU on the same rigid headstage (user, 2026-09-29); "a rat's head cannot turn that fast" → the IMU can be
  low-passed physically (user, 2026-09-29); save every intermediate so raw data are read once (user, 2026-09-29).
- IMU (`ephys/read_imu.py`, `docs/methods/wild_ce64_imu.md`): `analogin.dat` lanes 1–3 acc (±8 g), 4–6 gyro
  (±2000 °/s), int16 at 1250 Hz, frame k ↔ amplifier sample 16k; |raw| ≥ 32700 = saturated. Head frame via the lab map
  S (`make_imu.S`: x nose, y left, z up). Magnetometer unusable (headstage magnet) → no absolute heading.
- `make_imu.py` chain ("before"): resample_poly 1250→100 Hz, scalar k_a = g / median|a| on quiet 1-s windows, gyro
  bias per 10-min block (median of quiet windows, linear interpolation), Fusion AHRS 6-axis NWU gain 0.5.
- Audit (main session, 2026-09-29): k_a varies 0.86–1.20 within a logger (points to per-axis offsets); the kinematic
  check du/dt = u × ω has native signs (r 0.84–0.95) but slope 1.10–1.26 (gyro scale unverified); saturation 106–312 s
  per animal-night (calibration pilot §1), lanes not yet identified.
- Field-PC time: `pc_time_fit.json` per session (`Q:\hc997\SocialFieldRat2026\3rd_rat\analysis\pc_time\<SFxx>\<session>\`,
  read-only), formula applied by `make_imu.pc_time_ms`.
- WISER: `D:\Field2026_analysis_out\2026c\wiser_working\3rdcohort_Spike_2026_3_4.sqlite` table `reports` (solved xy,
  `anchors_used`, `anchors_list`; mode=ro + query_only; sha256 prefix `82ccadfde589`). Tags
  `wiser/configs/rat_identities_2026c.csv`: SF07 12409, SF08 12386, SF09 12407, SF10 12395, SF12 12377.
- Reused from the pilots, unmodified: τ* = +0.20/+0.15/+0.10/+0.20/+0.15 s (SF07/08/09/10/12; + = WISER later), the
  IMU-still rule, QC mask (handling, silences ± 2 min, tag validity, saturation, frozen, unreliable, nodata) + ADC-lane
  on-windows per logger, the duplicate rule, the per-axis anchor-count noise table σ_ax(A), B1/B2/B2′ and their tuned
  values (`wiser/configs/wiser_imu_smoothing_2026c.json` → `tuned`), the held-out schemes (a)/(a′) with the same seeds,
  the scorer, the paired 5-min block bootstrap, the locomotion class.
- Nights (field-PC local, EDT): **tuning** 2026-09-08 21:00 → 09-09 04:20; **test** 2026-09-10 21:00 → 09-11 04:20
  (same sessions as the smoothing pilot; SF08/SF12 test sessions start 21:02:45/21:05:18 → first minutes without IMU).

## Phase A — caches (read raw once; reusable by any later analysis)

- **A1 raw IMU cache** `D:\Field2026_analysis_out\2026c\imu_raw_cache\<SFxx>\<session>__<start>_<end>.npz`
  (start/end = local time of the cached window, `YYYYMMDDTHHMMSS`), one per animal-night: int16 lanes 1–6 at 1250 Hz,
  first frame index k0 in the session and first amplifier sample 16·k0, per-sample per-lane saturation, per-sample
  frozen flag (`make_imu.frozen_mask`), the full `pc_time_fit.json`, session metadata (animal, MAC, session dir,
  start_local, night), window requested/actual, sha256 of the first 64 MiB of `analogin.dat` + size + mtime, git
  commit. Plus `imu_raw_cache/index_2026c.csv`.
  **Window: 20:50 → 05:30** = the night ± 10 min **extended by 1 h 10 min at the end** so the +1 h-shifted control can
  be built from the cache (deviation from "night + 10 min", declared: without it the control would need raw again).
- **A2 WISER cache** `D:\Field2026_analysis_out\2026c\wiser_fix_cache\night_<YYYYMMDD>\<SFxx>.csv.gz` (pyarrow is not
  installed → csv.gz instead of parquet, declared): deduplicated fixes (smoothing-pilot duplicate rule) of the night
  ± 10 min: reportid, shortid, t_ms (Unix ms), x, y (in), anchors_used, anchors_list, library `valid` and
  `speed_inps_smooth`, and mask columns m_handling, m_silence (± 2 min), m_tag_validity, m_adc_lane.
- Phase A reads E: and Q: read-only, writes only under `D:\Field2026_analysis_out\2026c\`.

## Phase B — IMU quality and physical smoothing (tuning night decides every choice)

**Measurements** (per animal-night, from A1): saturation per lane (samples, runs, longest run); single-sample spikes
(Hampel hits per lane, still vs moving); noise floor (Welch PSD, 1250 Hz, 0.5-Hz bins, IMU-still vs moving seconds);
quiet-window gravity residual; per-axis accelerometer offset/scale (ellipsoid); gyro scale (static–dynamic–static);
yaw drift over still runs; post-filter angular acceleration.

**Candidate chain ("after")**, each step with its decision rule:
1. **Spike removal:** Hampel filter per lane at 1250 Hz, window 7 samples (±3), threshold 6 × max(1.4826 × MAD, σ_lane) with σ_lane = the lane's global
   noise SD (1.4826·median|Δx|/√2, ≥ 2 counts; changed before any real-data run after the self-test showed that a
   7-sample MAD alone flags ~3 × 10⁻³ of pure-noise samples), replacement = window median; saturated samples are never replaced (not spikes). Always applied;
   counts reported.
2. **Low-pass cutoff f_c** (separately for acc and gyro, pooled over the five animals, tuning night): noise floor
   N = median of the IMU-still PSD over 150–500 Hz (white sensor noise); motion PSD = Welch over QC-ok non-still
   seconds (both summed over the three axes). f_c = the lowest f ≥ 5 Hz from which the 2-Hz-smoothed ratio
   P_moving(f′)/N stays ≤ 2 for all f′ ∈ [f, 100 Hz] — where head-motion power meets the noise floor; clipped to
   [5, 40] Hz (40 Hz keeps the 100-Hz output alias-free). Filter: 4th-order Butterworth, zero-phase (sosfiltfilt),
   then resample_poly(2, 25) → 100 Hz.
3. **Accelerometer calibration:** scalar k_a (make_imu) vs a diagonal ellipsoid a_cal = D(a − o) (3 scales + 3
   offsets) fitted on quasi-static 0.5-s windows (median |ω| < 10 °/s, per-axis SD < 0.15 m/s²), Huber loss on
   (|a_cal| − g)/0.1 m/s², priors D_ii = 1 ± 0.05 and o_i = 0 ± 0.5 m/s² (keep unexcited axes near identity).
   Validation: 2-fold over alternating 10-min blocks, held-out median | |a_cal| − g |. **Rule:** use the ellipsoid if it
   beats k_a on held-out windows in ≥ 4 of 5 animals on the tuning night; each night is then self-calibrated on its
   own quasi-static windows (no WISER input), full data. Orientation coverage (eigenvalues of the unit-vector
   scatter) reported.
4. **Gyro bias:** make_imu 10-min-block median vs a running median (±5 min) of per-quiet-second medians. **Rule:** the
   one with the smaller pooled median leave-one-run-out yaw drift over tuning-night still runs ≥ 60 s.
5. **Gyro scale s:** static–dynamic–static pairs (two quasi-static windows ≥ 0.5 s, 0.2–3 s apart, tilt change ≥ 20°);
   s* = argmin Σ angle(u₂, R₁₂(s)ᵀu₁)² over s ∈ [0.80, 1.40]; bootstrap CI over pairs. **Rule:** apply the pooled s*
   if its 95 % CI excludes 1 and |s* − 1| > 2 %, else s = 1. (Only tilt rotations are observable; one common scale is
   assumed for all three axes.) The kinematic du/dt-vs-u×ω slope is reported before/after as a secondary check.
6. **Angular-acceleration limit:** not applied a priori; |dω/dt| percentiles before/after are reported. The low-pass
   is the physical bound (user's "a head cannot turn that fast").
7. **Saturated segments:** flagged in A3 (`sat_acc`, `sat_gyr`, dilated by the filter support), never interpolated;
   in the ESKF they get inflated process noise.

**Validation before vs after** (before = make_imu chain; tuning night decides, test night reported): kinematic
consistency r/slope; held-out quiet-window gravity residual; leave-one-run-out still-run yaw drift; Fusion-AHRS
stability (pitch/roll SD inside still runs ≥ 60 s, share of samples in acceleration recovery), Fusion run on both
chains with `make_imu.fuse` (unchanged settings).

- **A3 cache** `D:\Field2026_analysis_out\2026c\imu100_cache\<SFxx>\night_<YYYYMMDD>.npz`: 100-Hz calibrated, smoothed
  head-frame acc (m/s²) and gyro (°/s, bias-removed, scale-corrected), Unix ms on the IMU clock (τ* NOT applied),
  QC flags (sat_acc, sat_gyr, frozen, spike count, quiet), calibration parameters (JSON: f_c, D, o, k_a, s, bias
  series), covering the whole A1 window.

## Phase C — V4 inertial fusion (offline ESKF + RTS)

**State** (nominal / error): 2-D position p (in, WISER frame; z fixed), 2-D velocity v (in/s), attitude q (head →
world, error δθ global, 3), accelerometer bias b_a (3), gyro bias b_g (3), and the **WISER drift** b_w (2, AR(1), as
B2′ — the held-out target contains it). Error state = 15.
**Propagation** at 100 Hz with the A3 acc/gyro: f_N = R(a − b_a); horizontal part drives v, p (gravity is vertical;
the vertical channel is discarded, z fixed); q ← q ⊗ Exp((ω − b_g)Δt). Covariance propagated at ≥ 50 Hz and at every
epoch; continuous noise densities σ_a (horizontal acc), σ_g (gyro), σ_ba, σ_bg; b_w: e^(−Δt/T_b), σ_b.
Saturated samples: σ_a,sat = 20 m/s²/√Hz, σ_g,sat = 1 rad/s/√Hz. Unusable samples (frozen/NaN): zero input + the same
inflation. Inside IMU-still seconds the gyro process noise is the gyro's measured white-noise density (Phase B noise
floor) instead of the tuned σ_g (added before coding the filter: σ_g stands for model error that scales with head
rotation — scale, misalignment, filtering — which is absent when the head is still; otherwise yaw uncertainty would
inflate during long rests).
**Updates:** (1) WISER fix z = p + b_w + ε, R = per-axis white variance σ²_w(A) = max(σ²_ax(A) − σ_b², σ²_ax(A)/4)
(pilot table), WISER time shifted by τ*; pass 0 soft χ² gate (R × d²/13.8 when d² > 13.8), passes 1–2 Huber IRLS on
smoothed residuals (k = 2.5, as B2/B2′). (2) At 10 Hz inside IMU-still seconds (pilot's still classes): ZUPT v = 0
(σ_v), **ZARU** ω_m − b_g = 0 (σ_ω) and a **gravity update** a_m = Rᵀg + b_a (σ_f). ZARU and the gravity update are
additions to the brief (declared): without them yaw and tilt errors grow during long still periods and the first
movement after them linearises badly. **Lever arm IMU ↔ tag (a few cm) is ignored.**
**Heading:** 24 initial-yaw hypotheses (15° apart, σ_ψ0 = 10°), each a forward filter; keep the maximum-likelihood
hypothesis (pseudo-log-likelihood of the pass-0 WISER innovations). Each is also run with the WISER y axis mirrored;
report LLR = max ℓ(normal) − max ℓ(mirrored) per animal and night (a handedness test; it does **not** choose the
frame). Held-out schemes select their hypothesis on their own visible fixes. For the tuning grid the hypothesis is
selected once per animal with the default config (declared, to bound runtime).
**Smoother:** RTS over all epochs (fixes, hidden fixes, pseudo-updates) in error-state form; smoothed states and diag
covariances; hidden fix predicted by p + b_w.
**Tuning** (tuning night, scheme (a), pooled median held-out error on scored fixes, as the pilot):
stage 1 σ_a ∈ {0.03, 0.1, 0.3, 1.0} m/s²/√Hz × σ_g ∈ {0.003, 0.01, 0.03} rad/s/√Hz (σ_v = 0.5 in/s, drift = B2′'s
T_b 15 s / σ_b 2.5 in); stage 2 σ_v ∈ {0.1, 0.5, 2} in/s × (T_b, σ_b) ∈ {(15, 2.5), (15, 1.5), (60, 2.5)}.
Fixed a priori: σ_ba = 1e-3 m/s²/√s, σ_bg = 5e-5 rad/s/√s; σ_ω and σ_f = RMS of the smoothed gyro / acc about their
per-second mean inside tuning-night still seconds (pooled; floors 0.5 °/s and 0.05 m/s²).
**Saved per animal-night** under `wiser_ins_fusion_<ts>/fusion/night_<date>/<SFxx>/`: smoothed states + diag covariances
at every fix, forward innovations, S, NIS, IRLS weights, hypothesis log-likelihoods (normal + mirrored), predictions
at hidden fixes for V4 and V4 +1 h — so re-scoring needs no re-run. Plus per-second IMU tables and the error table.

## Evaluation (test night; identical to the smoothing pilot)

Same tracks, hidden sets (seeds `seed + 1000 + i`), scored set (hidden, ≥ 7 anchors, IMU and +1 h IMU QC-ok),
still/moving/loco splits, paired 5-min block bootstrap (1000) vs B2′; B1/B2/B2′ (and V1/V2) recomputed with the pilot's
functions and tuned values (checked against its report). **Control:** V4 with every IMU input (acc, gyro, still
classes) taken from t + 1 h (from A3; hypothesis selected the same way).
**Acceptance (pre-registered):** V4 is ACCEPTED if on (a) or (a′): (i) Δ ≥ 3 % with CI lower bound > 0 in ≥ 4 of 5
animals; (ii) the +1 h control shows no significant gain (CI lower bound ≤ 0) in ≥ 4 of 5 animals; (iii) pooled Δ on
moving fixes ≥ −2 %. INCONCLUSIVE = (i) in exactly 3 animals, or (i) ∧ ¬(ii); else FAIL (the pilot's logic).
**Also reported:** RMSE Δ; speed smoothness (pilot's `track_metrics` for V4 and B2′ positions; V4 velocity state);
NIS consistency (mean NIS vs 2, share > χ²₂,0.95 = 5.99 vs 5 %; normalised held-out squared error for all methods);
handedness LLR on both nights.

## Self-tests

- `build_imu_wiser_cache.py --selftest`: a synthetic `analogin.dat` + fit → cache round trip (frames, window, time
  map, saturation/frozen flags, sha), WISER dedup/mask columns on a synthetic table.
- `analyze_wiser_ins_fusion.py --selftest`: synthetic 2-D head track + simulated 1250-Hz IMU with bias, noise, spikes,
  offsets/scale and a gyro-scale error + simulated WISER fixes (noise by anchors, drift, outliers, lag) → Hampel
  removes spikes, the ellipsoid and gyro scale are recovered, the ESKF beats B2 on held-out fixes, the ML hypothesis
  recovers the initial yaw (≤ 15°), the mirrored frame scores worse, the +1 h-shifted IMU gives no gain.

## Runtime and discipline

Target ≤ 90 min (numba for the filter loops, prange over hypotheses/configs). Read-only SQLite and raw drives; no
image is opened or judged; no commit (the main session reviews). `CLAUDE.md`: only the `wiser_baseline` row of the
WISER table is edited (caches mentioned). Deviations from this plan are declared in the report.

## Amendments before the full run (2026-09-30; tuning night only, no test-night V4 result seen)

Development runs on the tuning night (SF09, default config) showed V4 worse than B2′ on moving fixes (4.77 vs 4.34 in;
NIS mean 14.5). Diagnosis, all on 2026-09-08/09: (1) the filter's tilt followed the make_imu Fusion tilt within ~3.5°
most of the night but was lost completely (90–175°) for 20–25 min twice, because tilt was corrected only in IMU-still
seconds; (2) the kinematic check peaks with the gyro shifted by ~+10 ms (acc–gyro latency) and its slope (> 1, growing
with bandwidth) is contaminated by linear acceleration, so SDS stays the gyro-scale estimate; (3) the NIS of moving
fixes was 2.3× that of still fixes (the anchor-noise table comes from still bouts). Changes, fixed now:
- **Dynamic gravity update:** at 10 Hz outside IMU-still seconds when | |a| − g | < 0.1 g and |ω| < 100 °/s, a_m = Rᵀg + b_a
  with σ_fd (grid {0.5, 1.5} m/s²) and a soft χ²₃ gate (16.27).
- **Tilt-reset guard:** when the 1-s mean specific force is within 5 % of g but > 30° from the filter's up, the tilt is
  re-initialised from it (yaw kept) and the attitude covariance reset; resets are counted and reported.
- **Grid:** stage 1 σ_a ∈ {0.01, 0.03, 0.1, 0.3} × σ_g ∈ {0.003, 0.01, 0.03} × σ_fd ∈ {0.5, 1.5}; stage 2 σ_v ∈ {0.1, 0.5, 2}
  × (T_b, σ_b) ∈ {(15, 2.5), (15, 1.5), (60, 2.5)} × k_R ∈ {1, 2} (white fix variance × k_R when the fix's second is not
  IMU-still; the +1 h control takes this flag from the shifted IMU). Default for the tuning-night yaw selection: σ_a 0.1.
- **Acc–gyro latency:** measured per animal-night and reported, **not applied** (shifting the gyro by one 100-Hz sample
  changed the tuning-night held-out error by < 0.1 %).
- The Hampel floor change above (self-test) and these amendments are listed as deviations in the report.
