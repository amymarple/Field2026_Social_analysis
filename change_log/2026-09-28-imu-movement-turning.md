# Head IMU: reader, audit, and movement / 2D turning / posture for all of cohort 3 (2026-09-28)

Plan: [head IMU orientation and activity](../implementation_plan/2026-09-28-imu-orientation.md). Method note and audit
of the lab MATLAB scripts: [docs/methods/wild_ce64_imu.md](../docs/methods/wild_ce64_imu.md).

## What changed

- **`ephys/read_imu.py`** — read-only reader of the WILD CE64 IMU in `analogin.dat` (lanes 1–3 accelerometer ±8 g,
  4–6 gyroscope ±2000 °/s, 7–9 magnetometer; 1250 Hz; frame k ↔ amplifier sample 16k), with plausibility checks.
- **`ephys/make_imu.py`** — per session:
  - lanes 1–6 → 100 Hz;
  - the lab axis map `S` (nose = −y_B, left = −z_B, up = +x_B);
  - quiet-window calibration: accelerometer scale, and gyro bias per 10-min block;
  - 6-axis x-io Fusion AHRS;
  - outputs VeDBA, |ω|, turn rate about the vertical, pitch, roll and the quaternion at 50 Hz, plus a per-second
    table in field-PC time from `pc_time_fit.json`, and a provenance sidecar.
- **Output location:** `D:\3rd_rat_spikes\analysis\imu\<SFxx>\<session>.imu.{npz,_1s.csv,json}`.
- **Rules:**
  - local first, then the server (user; CLAUDE.md and `regime-aware-ephys`);
  - the magnetometer is unusable because the headstage carries a magnet (user).

## Findings

- **The magnetometer x axis is saturated on all six loggers.** Cause: a magnet on the headstage (user). There is no
  magnetic heading, so the lab's 9-axis yaw is invalid here. The pipeline is 6-axis.
- **The mounting is confirmed by the data.** The logger is on the right side of the head; the IMU/text face points
  right; the molex connector points to the tail (user). With the lab `S`, active night windows give a median roll of
  −9 to +4° and a median pitch of −30 to −50° on all six loggers.
- **Validation against the operator record.** In SF07 `2_20260909_183802.795`, "motionless at a corner" from 22:33
  (rec 14,100 s → 22:33:03.75 PC time) compared with the rest of the night:
  - VeDBA median 0.09 vs 2.98 m/s²;
  - |ω| 1.7 vs 112 °/s;
  - turn rate 0.6 vs 46 °/s.

  The per-second VeDBA is bimodal (still ≈ 0.05, active ≈ 3 m/s², trough ≈ 0.15–0.3 m/s²).
- **Full run** (local, `E:` raw → `D:`): 203 sessions, 1,372 h, all with field-PC time. The first attempt stopped at
  77 sessions on a bug in the short-session bias fallback (a mask-length mismatch). It was fixed and covered in the
  self-test, and the resumed run completed the remaining 126 sessions with 0 errors.

  | Logger | Sessions | Hours | Accel scale k_a | Quiet % | Unreliable % | Saturated |
  |---|---|---|---|---|---|---|
  | SF07 | 38 | 250.6 | 0.87–1.13 | 21.7 | 1.15 | 1.2e-4 |
  | SF08 | 35 | 248.1 | 0.86–1.06 | 31.5 | 0.89 | 1.6e-4 |
  | SF09 | 33 | 248.7 | 0.93–1.03 | 37.2 | 1.29 | 2.2e-4 |
  | SF10 | 34 | 244.7 | 0.96–1.04 | 39.7 | 1.25 | 2.5e-4 |
  | SF11 | 27 | 139.6 | 0.90–1.20 | 25.7 | 0.45 | 3.8e-5 |
  | SF12 | 36 | 240.1 | 0.93–1.13 | 22.8 | 2.76 | 8.9e-5 |

## WISER cross-check (one night, `ephys/imu_wiser_crosscheck.py`)

Night 2026-09-08 20:00 → 09-09 06:00: five animals; WISER incremental exports from the local `F:` backup,
de-duplicated. Tags (Notion, hex → decimal shortid): SF07 3079 = 12409, SF08 3062 = 12386, SF09 3077 = 12407,
SF10 306B = 12395, SF12 3059 = 12377.

- **Identity.** Spearman r between the 10-s smoothed log IMU VeDBA and the log WISER speed is **0.62–0.77 on the
  diagonal and ≤ 0.25 off it**. Every logger's best tag is its own, which confirms the tag table from movement alone.
- **Clocks.** The matched pairs peak at +1 to +2 s (WISER later than IMU); r at the peak barely exceeds r at 0. About
  +1 s comes from the backward 2-s WISER displacement. So the pc_time-mapped IMU and the WISER field-PC clock agree
  within about 1 s at 1-s resolution; the exact latency needs a centred estimate at finer resolution.
- **Stillness.** While the IMU is still (provisional VeDBA < 0.2 m/s²), WISER shows a median of 1.1 in/s (p90 about
  3). While it is moving, 2.1–2.9 (p90 6.6–9.7). Apparent WISER motion during IMU stillness is UWB jitter, which is
  the basis for IMU-gated WISER denoising.
- WISER covers 72–73 % of seconds that night; the IMU covers 100 %.

## Definitions (headline; full set in the plan)

- **Quiet window.** A 1-s window with median $\lVert\boldsymbol\omega\rVert < 10$ °/s and median
  $\bigl|\lVert\mathbf a\rVert - g\bigr| < 0.05\,g$. Used for calibration only, not as a behavioural state.
- **VeDBA.**
  $\text{VeDBA}(t) = \lVert\mathbf a_H(t) - \bar{\mathbf a}_H(t)\rVert$, where $\bar{\mathbf a}_H$ is the 2-s running
  mean.
  Movement intensity in m/s², ≥ 0; near 0 means still. It is not locomotion speed.
- **Angular speed.**
  $|\omega|(t) = \lVert\boldsymbol\omega_H(t)\rVert$.
  Total head rotation speed in °/s, range 0–2000.
- **Turn rate.**
  $\dot\psi(t) = \boldsymbol\omega_H(t)\cdot\mathbf u_H(t)$, where $\mathbf u_H$ is the fused "up" direction in the
  head frame.
  Rotation about the vertical ("2D head turning") in °/s, positive = counter-clockwise from above. It is drift-free;
  only its integral drifts.
- **Pitch.**
  $\theta = \arcsin u_{H,x}$.
  Degrees, [−90°, 90°]; + = nose up. It includes each logger's gluing tilt, so compare within animal.
- **Roll.**
  $\phi = \operatorname{atan2}(u_{H,y}, u_{H,z})$.
  Degrees; 0 = ears level.

## Verification

- `python ephys/make_imu.py --selftest` PASS: pitch/roll 0.06 / 0.03° RMS, turn rate 0.5 °/s RMS, gyro bias within
  0.01 °/s, short-session fallback.
- `python ephys/selftest.py`: 20/20.

## Not done yet

- The immobility threshold, set from the per-animal per-second VeDBA distributions.
- Validation of the IMU "EMG" against the LFP state (theta vs delta/SWR).
- Identity matching against video tracks and WISER.
- Whether the FM64 sessions' `analogin` lanes carry any firmware artefact (FM64 sessions are included; their k_a and
  quiet fractions look normal).
- A server run, which is not needed: the whole cohort takes about 1 h locally.
