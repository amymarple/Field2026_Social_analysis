# Head IMU orientation and activity for cohort 3 (2026c): reuse the lab algorithm, 6-axis (2026-09-28)

**Status.** PLAN, 2026-09-28 (mounting and axis map verified on all six loggers). Nothing implemented beyond the reader (`ephys/read_imu.py`). Local first: developed and
validated on `E:\3rd_rat_spikes`, then the same commit runs on BioHPC.

## Goal

Per session, a 100 Hz time series of:
- head pitch and roll (absolute, relative to gravity);
- head turn rate, and yaw relative to the session start (drifting);
- angular speed;
- dynamic acceleration (movement intensity).

Everything is timed in field-PC time, so it can be aligned with LFP/spikes, video and WISER.

## What carries over from the lab algorithm and what changes

The algorithm is `CE32_scaleIMU_gravity.m` + `process_IMU_from_basepath.m` (WILD_frank; audit in
`docs/methods/wild_ce64_imu.md`).

| Step | Lab algorithm | Here | Why |
|---|---|---|---|
| Read | lanes 2:10 (MATLAB) = accelerometer, gyroscope, magnetometer, 1250 Hz | lanes 1–6 only (accelerometer + gyroscope) via `read_imu.py` | the headstage magnet saturates the magnetometer |
| Units | acc ±8 g, gyro ±2000 °/s | same | validated: \|acc\| ≈ g, gyro bias < 2 °/s |
| Rate | `resample` → 100 Hz | fuse at 100 Hz (anti-aliased `resample_poly(2, 25)`), **store 50 Hz** (user: 100 Hz is more than enough); 1250 Hz stays available through `read_imu.py` | the fusion integrates the gyro more accurately at 100 Hz. Stored 50 Hz sample j ↔ amplifier sample 400j exactly |
| Outliers | clip each lane at 0.1 / 99.9 % | **no clipping**; flag full-scale saturation | clipping removes real jumps/falls |
| Calibration | acc scaled so the session median \|a\| = g; gyro bias = session median; `magcal` | acc scale and gyro bias from **quiet windows**, the bias per 10-min block (interpolated); no mag | a whole-session median includes movement; bias drifts with temperature |
| Fusion | 9-axis `ahrsfilter` (NED) | **6-axis** filter: x-io Fusion AHRS (`imufusion`), gyro range 2000 °/s, acceleration rejection. Madgwick (`ahrs`) as a check | no magnetometer; Fusion recovers after gyro saturation |
| Axis map | fixed `S`: head up = sensor +x (x' = −y, y' = −z, z' = +x) | same `S` — **verified 2026-09-28 on all six loggers** | Mounting (user): the logger is on the **right side of the head**; the IMU / text side faces right (outward), the molex connector points to the tail, and the IMU is on the nose side. So the chip normal (z_B) points right, x_B up, and y_B (right-handed) to the tail: nose = −y_B, left = −z_B, up = +x_B = `S`. Data: in active night windows (median \|ω\| 30–150 °/s, first 2 h of the first FM65 night) the median roll is −9 to +4° and the median pitch −30 to −50° (nose down) on all six; a mirrored map would give roll ≈ ±180° or nose-up exploring. Quiet windows spread widely (curled / lying on the side), so rest is not a level reference. The PCB drawing function (`CE32_draw3DPCB`) is not on this machine |
| Angles | ZYX Euler [roll, yaw, pitch], unwrap + `processAxis_fast` jump "repair" | pitch and roll from the gravity vector in the head frame (no gimbal lock); yaw only as turn rate / relative yaw; no jump repair | rearing takes pitch near 90°, where ZYX breaks; the repair distorts real fast turns |
| World accel | R·a − median(R·a) | R·a − g·ẑ (exact gravity) | the median absorbs orientation bias |
| "speed" | cumsum(accel), 0.1 Hz high-pass | **not computed**; VeDBA and angular speed instead | it is not locomotion speed (speed comes from WISER/video) |
| Time | folder time + n/Fs (naive; unix_ms off by 4 h) | `pc_time.dat` at amplifier sample 200j | the logger drifts ~ −20 ppm; PC-time steps are handled by the chain |
| Output | `IMU.mat/.csv` inside the raw folder | `<analysis_root>/imu/<SFxx>/<session>.imu.npz` + `.json` sidecar | raw folders are read-only |

## Definitions

- **Frames.**
  - $B$ is the sensor frame: lanes 1–3 are $\mathbf a_B$, lanes 4–6 are $\boldsymbol\omega_B$.
  - $H$ is the head frame: $x_H$ nose, $y_H$ left, $z_H$ up, with $\mathbf v_B = S\,\mathbf v_H$.
  - $W$ is the world frame: $z_W$ up (gravity reaction), $x_W$ = initial heading.
- $R(t)$ is the fused rotation $B\to W$; $R_H(t) = R(t)\,S$ is the rotation $H\to W$.
- $g = 9.81$ m/s². $t$ runs over 100 Hz samples. $Q$ is the set of quiet samples.

### Quiet window ($Q$)
A 1-s window $w$ is quiet when
$$ \tilde\omega_w = \operatorname{median}_{t\in w}\lVert\boldsymbol\omega_B(t)\rVert < \omega_q
   \quad\text{and}\quad \operatorname{median}_{t\in w}\bigl|\lVert\mathbf a_B(t)\rVert - g\bigr| < a_q . $$
**Text:** a second in which the head barely rotates or accelerates. It is used only for calibration and checks, not as
a behavioural state.
**Thresholds (initial):** $\omega_q = 10$ °/s, $a_q = 0.05\,g$. To be set from the local distribution of
$\tilde\omega_w$ (the lower mode) before use; the chosen values go into the sidecar.

### Accelerometer scale ($k_a$)
$$ k_a = \frac{g}{\operatorname{median}_{t\in Q}\lVert\mathbf a_B^{\text{raw}}(t)\rVert}, \qquad \mathbf a_B = k_a\,\mathbf a_B^{\text{raw}} $$
**Text:** one factor per session that makes the resting acceleration equal $g$. It is dimensionless; the observed
uncorrected \|a\| of 8.9–10.3 m/s² implies $k_a \approx 0.95$–$1.10$.

### Gyroscope bias ($\mathbf b(t)$)
$$ \mathbf b_m = \operatorname{median}_{t\in Q\cap m}\boldsymbol\omega_B^{\text{raw}}(t), \quad
   \mathbf b(t) = \text{linear interpolation of } \{\mathbf b_m\} \text{ between 10-min block centres } m, \quad
   \boldsymbol\omega_B = \boldsymbol\omega_B^{\text{raw}} - \mathbf b(t) $$
**Text:** the gyro's zero-rotation offset, in °/s per axis, tracked in 10-min blocks. The observed magnitude is
0.3–1.7 °/s. The fusion filter's own offset estimator refines it further.

### Orientation ($R(t)$) — 6-axis complementary filter
$$ q_{t+1} = q_t \otimes \exp\!\Bigl(\tfrac{\Delta}{2}\,\bigl(\boldsymbol\omega_B(t) + K\,\mathbf e(t)\bigr)\Bigr), \qquad
   \mathbf e(t) = \hat{\mathbf a}_B(t) \times \bigl(R(t)^{\top}\hat{\mathbf z}_W\bigr) $$
Here $q$ is the unit quaternion of $R$, $\Delta = 0.01$ s, $K$ is the filter gain, and $\mathbf e$ is the error between
the measured and the predicted gravity direction.
- Samples with $\bigl|\lVert\mathbf a_B\rVert - g\bigr|$ above the acceleration-rejection limit do not correct the
  attitude (the fall-back is the gyro only).
- **Text:** the head attitude from integrating rotation, continuously pulled toward the measured gravity direction.
  Pitch and roll are absolute; yaw is unconstrained (no magnetometer) and drifts.
- **Parameters:** Fusion defaults (gain 0.5, acceleration rejection 10°, recovery 5 s), then tuned on local data. The
  values go into the sidecar.

### Gravity in the head frame ($\mathbf u_H$)
$$ \mathbf u_H(t) = R_H(t)^{\top}\,\hat{\mathbf z}_W $$
**Text:** the "up" direction seen from the head, a unit vector. It is $(0,0,1)$ when the head is level and upright.

### Head pitch ($\theta$)
$$ \theta(t) = \arcsin\bigl(u_{H,x}(t)\bigr) $$
**Text:** the elevation of the nose above horizontal, in degrees, range $[-90°, 90°]$. Positive means nose up
(rearing, sniffing up); negative means nose down (grooming, eating, head-down sleep). It is well defined at any
attitude.
- Absolute θ includes each logger's gluing tilt on the head (unknown, possibly tens of degrees): exploring
  medians are −30 to −50°.
- Compare animals on θ relative to the animal's own active-locomotion median, or after a video calibration.

### Head roll ($\phi$)
$$ \phi(t) = \operatorname{atan2}\bigl(u_{H,y}(t),\,u_{H,z}(t)\bigr) $$
**Text:** the sideways tilt of the head, in degrees, range $(-180°, 180°]$. 0 means ears level; the sign is set by the
verified axis map. It is ill-defined when $|\theta| \to 90°$; flagged when $|\theta| > 75°$.

### Turn rate ($\dot\psi$) and relative yaw ($\psi_{\text{rel}}$)
$$ \dot\psi(t) = \bigl(R_H(t)\,\boldsymbol\omega_H(t)\bigr)\cdot\hat{\mathbf z}_W, \qquad
   \psi_{\text{rel}}(t) = \operatorname{unwrap}\,\operatorname{atan2}\bigl(\hat x_{W,y}, \hat x_{W,x}\bigr), \quad
   \hat{\mathbf x}_W = R_H(t)\,\hat{\mathbf x}_H $$
**Text:** the rotation rate about the vertical (°/s; positive = counter-clockwise from above), and the nose heading
relative to the start of the session (degrees).
- **$\psi_{\text{rel}}$ drifts** by the residual bias; the expected order is 0.1 °/s, i.e. several degrees per minute.
- Use it only within short windows (single turns); an absolute heading must come from video or WISER.

### Angular speed ($|\omega|$)
$$ |\omega|(t) = \lVert\boldsymbol\omega_B(t)\rVert $$
**Text:** the total head rotation speed, in °/s, range $[0, 2000]$ (the sensor range). High values mean head turns,
grooming, shaking; values near 0 mean still.

### Dynamic acceleration ($\mathbf a_{\text{lin},W}$) and VeDBA
$$ \mathbf a_{\text{lin},W}(t) = R(t)\,\mathbf a_B(t) - g\,\hat{\mathbf z}_W, \qquad
   \text{VeDBA}(t) = \bigl\lVert \mathbf a_B(t) - \bar{\mathbf a}_B(t) \bigr\rVert, \quad
   \bar{\mathbf a}_B(t) = \frac{1}{2\tau+1}\sum_{s=t-\tau}^{t+\tau}\mathbf a_B(s),\ \tau = 1\text{ s} $$
**Text:** acceleration not due to gravity, in m/s², range $\ge 0$.
- $\mathbf a_{\text{lin},W}$ is in world axes (horizontal vs vertical) and depends on the orientation estimate.
- VeDBA (vectorial dynamic body acceleration, the standard biologging activity index) needs no orientation: it is the
  deviation from the 2-s running mean.
- High values mean vigorous movement; near 0 means rest.
- **Neither is locomotion speed.**

### Saturation flag
$$ s(t) = \mathbb 1\bigl[\max_{\text{lanes }1..6}|\text{raw}(t)| \ge 32700\bigr] $$
**Text:** marks samples at the sensor's full scale; at the observed rate, 2–9 × 10⁻⁵ of samples, mostly gyro x.
Orientation is marked unreliable from a saturated sample until the filter's recovery period ends.

## Time base

- The 100 Hz sample $j$ corresponds to amplifier sample $200j$: $1250/100 = 12.5$ IMU frames, and each frame is 16
  amplifier samples.
- Field-PC time: $t_{\text{PC}}(j) = \texttt{pc\_time.dat}[200j]$ (uint32 ms-of-day; unwrapped at midnight).
- Sessions without a pc_time fit keep logger time ($j/100$ s from the RTC start) and are flagged.

## Outputs

`<analysis_root>/imu/<SFxx>/<session>.imu.npz`:
- per sample: `t_pc_ms`, `t_logger_s`, `amp_sample`, quaternion $q$ (w, x, y, z), $\mathbf u_H$, θ, φ, $\dot\psi$,
  ψ_rel, \|ω\|, $\mathbf a_{\text{lin},W}$, VeDBA;
- flags: `saturated`, `quiet`, `accel_rejected`, `roll_undefined`.

`.imu.json`: $k_a$, the bias series, $S$ and its per-animal check, filter parameters, thresholds, the source file and
fingerprint, and the git commit.

## Validation (local first, `E:\3rd_rat_spikes`)

1. **Synthetic.** Known rotation sequences with noise and an injected bias: θ and φ must be recovered within 1°, and
   the bias estimate within 0.1 °/s.
2. **Static.** After calibration, \|a\| on $Q$ is 9.81 ± 0.05 m/s²; the bias series is smooth across the session.
3. **Axis map.** Per animal, the gravity direction in quiet upright windows, mapped by $S$, lies within 30° of
   $+z_H$. Otherwise derive the per-animal map from the logger mounting (question 1).
4. **Behaviour anchors** (Notion behaviour log, session + rec-seconds):
   - SF07 09-09 22:33–23:06 motionless → quiet, stable θ/φ;
   - SF08 09-10 14:37 REM twitches → quiet attitude with brief \|ω\| bursts;
   - SF09 09-10 21:30 nesting → high VeDBA and nose-down θ.

   Video spot checks of rearing (θ > 45°) and grooming are **judged by the user**, not by me.
5. **Cross-implementation.** If MATLAB with the Sensor Fusion toolbox is available here, run their scaling + a 6-axis
   `imufilter` on a 10-min segment; θ/φ agreement should be RMS < 2°.
6. Then the same commit runs on BioHPC; one session is compared with the local output.

## Decisions (user, 2026-09-28)

1. **Mounting:** the logger is on the right side of the head; the IMU/text side faces right; the molex connector
   points to the tail; the IMU is on the nose side. The lab `S` holds and is verified in the data (see the table).
2. **Rate:** 100 Hz is more than enough, so fuse at 100 Hz and store 50 Hz.
3. **Library:** x-io Fusion (`imufusion`) is primary, Madgwick a check.
4. **Where and how long:** local (IMU data is small).
   - Only `analogin.dat` is read: 144 MB per recorded hour, about 200 GB for 1,372 h, about 17 min from `E:` at
     ~200 MB/s.
   - The fusion runs at 100 Hz in C; with sessions in parallel it takes minutes.
   - The whole cohort should take about 30 min on this PC; the server is not needed for this step.
5. **Still open:** which behaviours matter first (rearing, grooming, sleep posture, head turns during following).
   That decides the validation set.
