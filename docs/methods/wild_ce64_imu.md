# WILD CE64 IMU — layout, validation on cohort 3, audit of the lab MATLAB scripts (2026-09-28)

Reader: [`ephys/read_imu.py`](../../ephys/read_imu.py). It reads the raw session in place and writes nothing;
`--check` prints the plausibility tests below.

## Where the IMU is

In each raw session folder, `analogin.dat` holds 16 int16 lanes at fs/16 = **1250 Hz**. Frames = amplifier samples
/ 16 exactly (ratio 16.0000 on every session checked), so **IMU frame k ↔ amplifier sample 16k**.

| Lane (0-based) | Content | Scaling (maker's `raw2physical`) |
|---|---|---|
| 1–3 | accelerometer x/y/z | raw / 32768 × 8 g → m/s² |
| 4–6 | gyroscope x/y/z | raw / 32768 × 2000 °/s |
| 7–9 | magnetometer x/y/z | raw / 32768 × [1150, 1150, 2500] |
| 14–15 | packed BLE field-PC-time word | see `ephys/pc_time_chain.py` |
| 0, 10–13 | status (undocumented, not IMU) | lane 0 mostly 0 (4 values); lane 11 full-range; lane 13 all zero |

Sources: WILD_frank repo `notebooks/process_IMU_from_basepath.m` (MATLAB `ChanSelect = 2:10`, 16 channels at 1250 Hz)
and `notebooks/CE32_scaleIMU_gravity.m`.

## Validation on local cohort-3 data (E:\3rd_rat_spikes, read-only)

- **Accelerometer.** |acc| median is 9.1–10.3 m/s² across the first and last FM65 session of all six loggers (8.9–9.7
  in the quietest windows). The ±8 g scale is right to within a few %; normalize per session to 9.81 as the maker's
  calibration does.
- **Gyroscope.** The per-axis median (bias) is −1.7 to +0.7 °/s. Lane 4 saturates in ≤ 1 × 10⁻⁴ of samples (fast head
  turns).
- **Magnetometer.** **Lane 7 (x) is saturated at −32767 in 99.99–100 % of samples on all six loggers**, in the first
  and last FM65 session; lanes 8–9 are alive. So there is **no magnetic heading for cohort 3**:
  - 9-axis fusion (`magcal` + `ahrsfilter`) is invalid;
  - roll and pitch from accelerometer + gyroscope are usable;
  - yaw from gyro integration drifts and needs another heading reference (video / WISER).

  Cause unknown (hardware, sensor configuration, or a magnet near the sensor) — ask the maker.
- **Time.** The folder name gives the logger RTC at Record Start, and the logger clock drifts about −15 to −27 ppm
  (pc_time fits). For field-PC time, use `pc_time.dat` at amplifier sample 16k, not the folder time + k / fs.

## Audit of the scripts in `From others/`

**`readmulti_frank.m`** (Buzsaki lab, revised by Zifang Zhao) is a generic multi-channel int16 reader.
- Fine to use.
- `read_until` is inclusive: it reads one extra sample.
- It errors with an index error, not a clear message, when the file is missing.

**`CE32_scaleIMU_gravity.m`** (the `From others` copy differs from WILD_frank only by one comment line):
1. The **9-axis `ahrsfilter` + `magcal`** use the saturated magnetometer x → **yaw is meaningless on cohort 3** and
   the mag calibration is ill-posed. Use a 6-axis filter (`imufilter`, or Madgwick/Mahony without mag).
2. The **axis remap `S`** hard-codes the mounting of *their* device. The header comment describes a different `S`
   from the one in the code. For CE64 on our animals, check it against a known posture (gravity direction at rest)
   before naming roll/pitch/yaw.
3. **`processAxis_fast`** "repairs" any > 300° change within 50 samples (0.5 s at 100 Hz) by linear redistribution.
   It alters real fast rotations (> 600°/s head turns, grooming).
4. **`speed`** is `cumsum(world accel)` high-passed at 0.1 Hz: drift-suppressed integrated acceleration, **not
   locomotion speed**. Take speed from WISER / video.
5. **Gravity removal** subtracts the session median of world-frame acceleration. Orientation errors leak gravity into
   the horizontal components.
6. The output order `[roll, yaw, pitch]` differs from the ZYX `rotm2eul` order `[yaw pitch roll]`. It is correct in
   the code but easy to misread.
7. It needs MATLAB's Navigation/Sensor Fusion and Signal Processing toolboxes.

**`process_IMU_from_basepath.m`** (the `From others` copy is a *test* variant: its header runs it on
`I:\data\FieldRat\2024\F5\Merged\day10\121_day10`, `Fs` 50):
1. **It crashes on our layout before processing anything.** Lines 58–59 read `basepath/analogin.dat` (a merged file
   from the other project) into `dataAll`, which is never used. Our session folders have no such file, and
   `readmulti_frank` then errors.
2. **Two-digit slots are skipped.** The folder regex `^(\d{1})_(\d{8})_(\d{6}\.\d{3})$` allows a one-digit slot only.
   16 of SF07's 88 folders (`10_…` – `18_…`) would be skipped with just a warning. WILD_frank's current version
   anchors on the timestamp at the end and fixes this.
3. **It writes into the raw session folder** (`IMU.mat`, `IMU.csv`), which our raw-read-only rule forbids. Write to
   `<analysis_root>/imu/<SFxx>/<session>.*` instead.
4. **Percentile clipping** (0.1 / 99.9 % per lane) before fusion cuts real high-acceleration events (jumps, falls,
   fights) and gyro peaks. Flag saturation at full scale instead of clipping.
5. **`unix_ms` is off by 4 h (EDT) unless `TimeZone` is given.** Timestamps are the naive folder time + n / Fs, and
   MATLAB `posixtime` treats a naive datetime as UTC. They also ignore logger drift and PC clock steps (see *Time*).
6. It resamples 1250 → 100 Hz (50 Hz in the test call) with MATLAB `resample` (FIR anti-alias): fine for posture; it
   loses > 50 Hz content (impacts, tremor).
7. It loads the whole session into memory (a 12 h session is about 3.9 GB of doubles for 9 lanes).

## Recommended processing (not implemented yet)

1. Read with `read_imu.py` and write outputs to the analysis folder only.
2. Normalize acceleration to |g| = 9.81 on quiet windows and remove gyro bias on quiet windows, per session.
3. Run a **6-axis** orientation filter (acc + gyro) for roll and pitch. Treat yaw as relative (drifting) unless it is
   anchored to video / WISER heading.
4. Keep 1250 Hz, or downsample with an anti-alias filter only for posture. Mark saturated samples; do not clip.
5. Time every sample by `pc_time.dat[16k]`.
6. Validate against video-scored postures (rearing, grooming, sleep) on local data before any server run.
