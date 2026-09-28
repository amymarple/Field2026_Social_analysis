"""Read the WILD CE64 IMU from a RAW session's ``analogin.dat`` (read-only; 16 int16 lanes at fs/16 = 1250 Hz).

Lane layout and scaling come from the maker/lab MATLAB code (WILD_frank repo: ``notebooks/process_IMU_from_basepath.m``,
``CE32_scaleIMU_gravity.m``; copies in ``From others/``) and were checked on cohort-3 data (2026-09-28):

    lanes 1-3   accelerometer x/y/z   raw / 32768 * 8 g            -> m/s^2   (|acc| median 9.1-10.3 across sessions)
    lanes 4-6   gyroscope x/y/z       raw / 32768 * 2000 deg/s     -> deg/s   (bias ~ -1.5..-0.3 deg/s)
    lanes 7-9   magnetometer x/y/z    raw / 32768 * [1150 1150 2500]
                ** lane 7 is saturated at -32767 in 100 % of samples on ALL six loggers (first and last FM65 session
                   checked) -> no magnetic heading for cohort 3; 9-axis (ahrsfilter/magcal) yaw is invalid. **
    lanes 14/15 packed BLE PC-time word (ephys/pc_time_chain.py); lanes 0 and 10-13 = status (undocumented, not IMU)

Timebase: analogin frames = amplifier samples / 16 exactly, so IMU frame k <-> amplifier sample 16*k; logger time =
k / 1250 s from the session start (RTC in the folder name, logger wallclock). For field-PC time use pc_time.dat at
amplifier sample 16*k (ephys/pc_time_chain.py), never the folder time + k/fs alone (the logger clock drifts ~ -20 ppm).

Usage:
  python ephys/read_imu.py --check E:/3rd_rat_spikes/SF7/D0DBEFEF3111/9_20260901_192912.215 [--max-seconds 600]
  from read_imu import read_imu; imu = read_imu(session_dir, start_s=0, dur_s=60)
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np

LANES = 16
FS_AMP = 20000.0
FS_IMU = FS_AMP / 16                       # 1250 Hz
ACC_LANES, GYR_LANES, MAG_LANES = (1, 2, 3), (4, 5, 6), (7, 8, 9)
ACC_FS_G, GYR_FS_DPS = 8.0, 2000.0
MAG_FS = np.array([1150.0, 1150.0, 2500.0])
G = 9.81
SAT = 32700                                # |raw| >= SAT counts as saturated (full scale is -32768..32767)


def read_imu(session_dir: str | os.PathLike, start_s: float = 0.0, dur_s: float | None = None) -> dict:
    """IMU of one raw session: acc (m/s^2), gyr (deg/s), mag (scaled), per-sample saturation masks, the raw lanes,
    logger time (s from the session start) and the matching amplifier sample index (16*k). Nothing is written."""
    path = Path(session_dir) / "analogin.dat"
    n_frames = os.path.getsize(path) // (2 * LANES)
    k0 = int(round(start_s * FS_IMU))
    k1 = n_frames if dur_s is None else min(n_frames, k0 + int(round(dur_s * FS_IMU)))
    raw = np.fromfile(path, dtype=np.int16, count=(k1 - k0) * LANES, offset=k0 * LANES * 2).reshape(-1, LANES)
    amp_path = Path(session_dir) / "amplifier.dat"
    ratio = (os.path.getsize(amp_path) // 128) / n_frames if amp_path.exists() else None
    k = np.arange(k0, k0 + raw.shape[0])
    r = lambda lanes: raw[:, list(lanes)].astype(np.float64)
    return {
        "acc": r(ACC_LANES) / 32768 * ACC_FS_G * G,
        "gyr": r(GYR_LANES) / 32768 * GYR_FS_DPS,
        "mag": r(MAG_LANES) / 32768 * MAG_FS,
        "sat_acc": np.abs(r(ACC_LANES)) >= SAT, "sat_gyr": np.abs(r(GYR_LANES)) >= SAT, "sat_mag": np.abs(r(MAG_LANES)) >= SAT,
        "raw": raw, "t_logger_s": k / FS_IMU, "amp_sample": 16 * k, "fs": FS_IMU,
        "amp_to_imu_ratio": ratio,           # must be 16.0 (checked in --check)
    }


def check(session_dir: str, max_seconds: float | None = None) -> None:
    """Physical plausibility of the lane assignment on real data (prints, writes nothing)."""
    imu = read_imu(session_dir, 0.0, max_seconds)
    acc, gyr = imu["acc"], imu["gyr"]
    print(f"{session_dir}\n  frames {imu['raw'].shape[0]:,} ({imu['raw'].shape[0] / FS_IMU / 3600:.2f} h); "
          f"amplifier/analogin ratio {imu['amp_to_imu_ratio']:.4f} (expect 16)")
    w = int(FS_IMU)
    nw = acc.shape[0] // w
    gact = np.linalg.norm(gyr[: nw * w], axis=1).reshape(nw, w).mean(axis=1)
    quiet = np.argsort(gact)[: max(1, nw // 10)]
    an = np.linalg.norm(acc, axis=1)
    print(f"  |acc| m/s^2: median {np.median(an):.2f}, quietest 10% of 1-s windows {np.median(an[: nw * w].reshape(nw, w)[quiet]):.2f} (expect ~9.81)")
    print(f"  gyro deg/s: median |w| {np.median(np.linalg.norm(gyr, axis=1)):.1f}, quietest windows {np.median(gact[quiet]):.1f}, "
          f"per-axis median {np.round(np.median(gyr, axis=0), 2)}")
    for name, key in (("acc", "sat_acc"), ("gyr", "sat_gyr"), ("mag", "sat_mag")):
        print(f"  saturated fraction {name}: {np.round(imu[key].mean(axis=0), 5)}")
    if imu["sat_mag"][:, 0].mean() > 0.99:
        print("  NOTE magnetometer x (lane 7) saturated -> no magnetic heading; use 6-axis (acc+gyro) orientation only")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", nargs="+", metavar="SESSION_DIR", required=True)
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args()
    for s in a.check:
        check(s, a.max_seconds)


if __name__ == "__main__":
    main()
