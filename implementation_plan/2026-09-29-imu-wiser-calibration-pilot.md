# IMU ↔ WISER calibration pilot (cohort 2026c) — PLAN

- **Status:** approved by the user 2026-09-29 (pilot proposed by the read-only IMU audit of the same day, main
  session). Written before the code, per CONVENTIONS.md. **Done 2026-09-29** — results and verdicts in
  [`change_log/2026-09-29-imu-wiser-calibration-pilot.md`](../change_log/2026-09-29-imu-wiser-calibration-pilot.md).
- **Direction:** `wiser_baseline` (measurement quality; no behavioural claim).
- **Driver (new):** `wiser/scripts/analyze_imu_wiser_calibration.py --cohort 2026c` (+ `--selftest`); per-cohort
  inputs in `wiser/configs/imu_wiser_calibration_2026c.json`.
- **Outputs:** bulk `$FIELD2026_ANALYSIS_OUT_ROOT/2026c/imu_wiser_calibration_pilot_<ts>/`; report
  `results/2026c/wiser_baseline/reports/wiser_baseline_imu_calibration_pilot_2026c.md`, figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_imu_calibration_pilot_*_2026c.png`, and a pointer
  `run_manifest_imu_calibration_pilot_2026c.json` (the folder's `run_manifest.json` belongs to the accuracy report and
  is not overwritten).

## Why

The cohort-3 WISER precision numbers (`wiser_baseline_cohort3_accuracy_2026c.md`: rest bouts p50/p90/RMSE =
3.57/8.19/5.87 in; speed-noise p99 10.24 in/s) select "stationary" periods **with WISER itself** (5-s medians within
8 in), which is circular: the selector favours calm, low-scatter periods. The head IMU (`ephys/make_imu.py`) is an
independent stillness and turning sensor on the same animals and the same field-PC clock. The pilot asks five
measurement questions — no behaviour:

| # | Question | Pre-registered acceptance |
|---|---|---|
| M1 | Effective clock lag τ* between IMU movement and WISER speed | per-animal 95 % CI width ≤ 0.3 s **and** all animals' τ* within 0.2 s |
| M2 | Non-circular jitter floor: WISER scatter while the IMU says still | ≥ 20 bouts per stratum; a > 20 % difference from 3.57/8.19/5.87 in is flagged as bias of the WISER-based selector |
| M3 | Speed-noise floor over IMU-still time | reported against 10.24 in/s (p99) |
| M4 | Frame handedness: WISER heading change vs IMU turn (and gyro scale) | same-sign ρ on all five animals, each \|ρ\| ≥ 0.3 and ≥ 70 % sign agreement for \|Δψ_I\| > 45°, else **inconclusive**; a pass stays a **candidate** until a video event confirms it |
| M5 | Agreement of the library WISER rest proxy (`rest_mask`) with IMU stillness | reported (κ, sensitivity, specificity); no threshold |

## Data (all read-only)

- **Window:** regime-B night 2026-09-08 20:00 → 09-09 06:00 (field-PC local), SF07 SF08 SF09 SF10 SF12 (SF11 had no
  implant by then). Two still events: the SF11 dropped implant with tag 3058 lying in the CH07 box 09-07 06:12–08:12
  (fixed-tag reference; stillness confirmed from the implant's own raw IMU, see below) and SF07 motionless at a paddock
  corner 09-09 22:33–23:06 (Notion behaviour log / `field2026-sync/from-field/behaviour_observations_cohort3.csv`).
- **IMU:** `<ephys.analysis_root>/imu/<SFxx>/<session>.imu.npz` (50 Hz, full-precision `t_pc_ms`) — not the 4-digit
  `t_pc_ms` of the old `.imu_1s.csv`. Sessions in the config JSON. The files are being regenerated on 09-29 by commit
  `6451d6c` (frozen flag, `invalid` after `imu_valid_until`, integer `t_pc_ms`); the pilot reads them only after that
  rerun and records their size/mtime/sha256.
- **WISER:** `D:/Field2026_analysis_out/2026c/wiser_working/3rdcohort_Spike_2026_3_4.sqlite`, table `reports`, opened
  `mode=ro` + `query_only` (`wiser_io._connect_readonly`); tag map `wiser/configs/rat_identities_2026c.csv`.
- **Out-of-arena:** `cv/configs/cohort3_handling_windows.json` + the accuracy run's
  `c3_all_tag_silences_merged.csv` (each silence padded ± 2 min, as in that report).

## QC mask (per second, per animal; applied inside the pilot, no upstream file is changed)

A second is dropped when any 50-Hz sample in it is saturated, frozen, `invalid` or NaN; when > 50 % of its samples are
Fusion-`unreliable`; when it lies in a handling window or a padded all-tag silence; or after the tag's `valid_until`.
**Frozen:** the new make_imu `frozen` column is primary. The audit's derived-signal rule is kept as a cross-check:
runs of ≥ 0.5 s with $|\Delta|\omega|| < 10^{-4}$ °/s and VeDBA < $10^{-3}$ m/s², padded ± 2 s (VeDBA's 2-s running
mean and the FIR resampler smear the edges by ~1 s); it is verified against the two known freezes (SF12
`14_20260902_191103.245` 09-02 19:39:38 → 00:22; SF07 `9_20260906_194035.495` 09-07 07:56:40 → 08:06:06) and its
agreement with the new flag is reported. WISER fixes: library `add_speed` + `add_validity_flags` (`valid` =
anchors ≥ 4, no gap, no jump).

## Methods (full formulas go in the report's Definitions section)

- **M1.** $x_b=\log_{10}(\overline{\mathrm{VeDBA}}_b+0.01)$ over 0.25-s bins; $v_W$ = `add_speed` smoothed speed of
  valid fixes, linearly interpolated at $c_b+\tau$ (only between fixes ≤ 1 s apart). $\tau^\*=\arg\max_\tau
  \mathrm{Pearson}(x_b, v_W(c_b+\tau))$, $\tau\in[-3,3]$ s step 0.05 s, same bins for every τ. 95 % CI: non-overlapping
  **300-s block bootstrap**, 1000 replicates (blocks ≫ movement bouts). Positive τ* = WISER later than IMU. τ* is an
  *effective* lag (clock offset + WISER processing latency + head-vs-body kinematics), not a pure clock offset.
- **M2.** IMU-still second: $\mathrm{VeDBA}_{1s}<\theta_a$ (per-animal `IMU_STILL_THR`, read from
  `ephys/imu_lfp_state_check.py`) and $|\omega|_{1s}<10$ °/s, QC-ok. Bout = maximal run ≥ 60 s. WISER fixes with
  aligned time ($t-\tau^\*$) inside the bout trimmed by 1 s at each end, ≥ 30 fixes. $r_i=\lVert\mathbf p_i-
  \operatorname{median}_B\mathbf p\rVert$; p50/p90/RMSE overall (all fixes, the baseline's method; valid-only too), by
  zone (house = bout median inside a house ROI grown by 14 in, else outside), by `anchors_used`, and for 1-s medians;
  same for the implant (IMU-still runs inside the window) and the SF07 corner event.
- **M3.** p50/p95/p99 of $v_W$ (valid fixes) inside M2 bouts (headline, = the library's in-bout floor) and over all
  IMU-still seconds.
- **M4.** Non-overlapping 3-s windows of four consecutive aligned 1-s WISER medians (≥ 2 valid fixes each); path
  $\sum_k\lVert\mathbf d_k\rVert\ge 30$ in; $\Delta\psi_W=\sum_{k=1}^{2}\operatorname{atan2}(\mathbf d_k\times
  \mathbf d_{k+1},\mathbf d_k\cdot\mathbf d_{k+1})$ (+ = rotation from WISER +x toward +y); $\Delta\psi_I=\int
  \mathrm{turn\_dps}\,dt$ over the matching 2-s span (+ = counter-clockwise seen from above). Spearman ρ, Theil–Sen
  slopes both ways (the true scale lies between $b_{I|W}$ and $1/b_{W|I}$), sign agreement for $|\Delta\psi_I|>45°$.
- **M5.** Per aligned second: $\mathrm{rest}_W$ = majority of the second's fixes resting by the library
  `rest_mask` (smoothed speed < 10.24 in/s, the cohort-3 p99 floor; NaN = not resting) vs IMU-still; Cohen's κ,
  sensitivity, specificity.

## Sign conventions to state (M4)

- **IMU:** `turn_dps` $=\boldsymbol\omega\cdot\hat{\mathbf u}$ (head up axis from the 6-axis AHRS). A dot product of
  two vectors in one orthonormal basis does not depend on the basis handedness or on the axis map S, so + =
  counter-clockwise seen from above **provided** each gyro axis reports the right-hand-rule rate about the same
  positive axis as the accelerometer axis of that index (the usual MEMS datasheet convention; the CE64 IMU chip and its
  datasheet are undocumented here — an assumption).
- **WISER:** + = rotation from +x toward +y. It is counter-clockwise from above iff (x, y, up) is right-handed. The
  paddock/calibration frame is (x long, y across, z up) with proper rotations (`calibration_qc`), and the user states
  the WISER axes point the same way (2026-09-28), so the expectation under that statement is ρ > 0.

## Deviations from the approved text (decided before seeing any result)

1. The fixed-tag reference's stillness comes from the implant's **raw** `analogin.dat` (`ephys/read_imu.py`, E:,
   read-only; resampled to 100 Hz like make_imu), because the rerun blanks SF11's IMU after 06:10 (`invalid`).
2. The frozen rule is a cross-check; the new make_imu `frozen` flag is primary (it is exact on the raw lanes).
3. The run pointer is a named manifest (above), not `run_manifest.json`.

## Verification

`--selftest` (synthetic track + IMU with a known lag of +0.8 s, known CCW/CW turns, known jitter and an injected
freeze): recovers τ*, ρ > 0 and a slope bracket containing 1, ρ < 0 after mirroring y, the Rayleigh jitter
percentiles, the freeze, and κ > 0.5. Runtime target < 15 min.
