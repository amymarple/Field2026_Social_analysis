"""Head IMU -> movement, 2D turning and posture per session (plan: implementation_plan/2026-09-28-imu-orientation.md).

Purposes (user, 2026-09-28, priority order): (1) sleep epochs - the IMU is the EMG (moving vs still); (2) animal identity
with video (movement + 2D head turning); (3) WISER denoising / identity; (4) 3D head rotation (secondary). Products, in
that order: movement index (VeDBA, |w|) and the turn rate about the vertical at 50 Hz and per second, stamped in field-PC
time; then pitch / roll; the quaternion is kept.

Per session (the raw analogin.dat is read in place; nothing is written next to raw data):
  1. lanes 1-6 -> m/s^2 and deg/s (read_imu.py scaling); a sample is 'saturated' when any lane is at full scale.
  2. anti-aliased 1250 -> 100 Hz (resample_poly up 2 / down 25).
  3. sensor -> head frame with the lab map S (nose = -y_B, left = -z_B, up = +x_B; verified on all six loggers 2026-09-28).
  4. calibration on quiet 1-s windows: k_a = g / median|a|; gyro bias per 10-min block (median), interpolated.
  5. 6-axis Fusion AHRS (imufusion, NWU, gain 0.5, gyro range 2000 deg/s, acceleration rejection 10 deg, timeout 5 s).
  6. derived: |w|, VeDBA (deviation from the 2-s running mean of a), turn rate = w . u (about the vertical, + = CCW seen
     from above), pitch = asin(u_x), roll = atan2(u_y, u_z), earth-frame linear acceleration.
  7. store: <out>/<SFxx>/<session>.imu.npz (50 Hz), <session>.imu_1s.csv (per second), <session>.imu.json (sidecar).
Time: 50-Hz sample j <-> amplifier sample 400*j; 100-Hz sample i <-> 200*i. Field-PC time from
<pc_time_root>/<SFxx>/<session>/pc_time_fit.json (its own 'formula') when present, else logger time only.
No immobility threshold is applied here: it is chosen from the per-second distributions (plan).

Usage:
  python ephys/make_imu.py --cohort 2026c --animal SF7 --session 2_20260909_183802.795 \
      --pc-time-root Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/pc_time
  python ephys/make_imu.py --cohort 2026c [--animal ...] [--workers 6]        # every selected session
  python ephys/make_imu.py --selftest                                         # synthetic, no data needed
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d

from _common import analysis_root, find_session_dir, git_commit, out_root, raw_ephys_root, resolve_cohort, utc_now_iso
from read_imu import ACC_FS_G, ACC_LANES, GYR_FS_DPS, GYR_LANES, LANES, SAT
from make_lfp import _norm_animal, select_sessions

G = 9.81
FS_RAW, FS, FS_OUT = 1250.0, 100.0, 50.0
S = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])   # v_B = S v_H (head: x nose, y left, z up)
QUIET_W_DPS = 10.0            # quiet 1-s window: median |w| below this ...
QUIET_A_FRAC = 0.05           # ... and median | |a| - g | below this fraction of g (plan: initial values)
BIAS_BLOCK_S = 600.0          # gyro bias block
BIAS_MIN_QUIET_S = 30         # a block needs >= this many quiet seconds for its own bias estimate
VEDBA_WIN_S = 2.0             # VeDBA: deviation from the running mean over this window
FUSION = {"gain": 0.5, "gyroscope_range": 2000.0, "acceleration_rejection": 10.0, "magnetic_rejection": 0.0,
          "rejection_timeout": 5.0}
TZ = ZoneInfo("America/New_York")


def imu_root(cohort: str, override: str | None = None) -> Path:
    if override:
        return Path(override)
    ar = analysis_root(cohort)
    return ar / "imu" if ar else out_root() / resolve_cohort(cohort) / "ephys_imu"


# ---------------------------------------------------------------- stages
def load_raw(session_dir: Path, max_seconds: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Raw lanes 1-6 at 1250 Hz -> acc_B (m/s^2), gyr_B (deg/s) as float32, and a per-frame saturation flag."""
    path = Path(session_dir) / "analogin.dat"
    n = os.path.getsize(path) // (2 * LANES)
    if max_seconds is not None:
        n = min(n, int(max_seconds * FS_RAW))
    raw = np.fromfile(path, dtype=np.int16, count=n * LANES).reshape(n, LANES)
    six = raw[:, list(ACC_LANES) + list(GYR_LANES)]
    sat = (np.abs(six.astype(np.int32)) >= SAT).any(axis=1)
    acc = six[:, :3].astype(np.float32) * np.float32(ACC_FS_G * G / 32768)
    gyr = six[:, 3:].astype(np.float32) * np.float32(GYR_FS_DPS / 32768)
    return acc, gyr, sat


def to_100hz(acc: np.ndarray, gyr: np.ndarray, sat: np.ndarray):
    a = signal.resample_poly(acc, 2, 25, axis=0).astype(np.float64)
    w = signal.resample_poly(gyr, 2, 25, axis=0).astype(np.float64)
    n = a.shape[0]
    starts = np.floor(np.arange(n) * FS_RAW / FS).astype(np.int64)
    starts = np.clip(starts, 0, len(sat) - 1)
    s = np.maximum.reduceat(sat.astype(np.uint8), starts).astype(bool) if len(sat) else np.zeros(n, bool)
    return a, w, s[:n]


def calibrate(a_H: np.ndarray, w_H: np.ndarray) -> dict:
    """Quiet 1-s windows -> accelerometer scale k_a and a gyro-bias series (10-min blocks, interpolated)."""
    wlen = int(FS)
    nw = a_H.shape[0] // wlen
    med_w = np.median(np.linalg.norm(w_H[: nw * wlen].reshape(nw, wlen, 3), axis=2), axis=1)
    med_a = np.median(np.linalg.norm(a_H[: nw * wlen].reshape(nw, wlen, 3), axis=2), axis=1)
    quiet0 = med_w < QUIET_W_DPS
    k_a = G / float(np.median(med_a[quiet0])) if quiet0.sum() >= 10 else 1.0
    quiet = quiet0 & (np.abs(k_a * med_a - G) < QUIET_A_FRAC * G)
    wins = np.arange(nw)
    blk = (wins * wlen / FS // BIAS_BLOCK_S).astype(int)
    nblk = int(blk.max()) + 1 if nw else 1
    centers, vals = [], []
    for b in range(nblk):
        sel = wins[(blk == b) & quiet]
        if len(sel) >= BIAS_MIN_QUIET_S:
            idx = (sel[:, None] * wlen + np.arange(wlen)[None, :]).ravel()
            centers.append((b + 0.5) * BIAS_BLOCK_S * FS)
            vals.append(np.median(w_H[idx], axis=0))
    t = np.arange(a_H.shape[0])
    if vals:
        c, v = np.array(centers), np.array(vals)
        bias = np.column_stack([np.interp(t, c, v[:, k]) for k in range(3)])
    quiet_s = np.zeros(a_H.shape[0], bool)              # per sample; the tail after the last full second stays False
    quiet_s[: nw * wlen] = np.repeat(quiet, wlen)
    if not vals:                                        # short session: no block has enough quiet seconds
        b0 = np.median(w_H[quiet_s], axis=0) if quiet_s.sum() > 100 else np.zeros(3)
        bias = np.tile(b0, (a_H.shape[0], 1))
    return {"k_a": k_a, "bias": bias, "quiet": quiet_s, "n_quiet_s": int(quiet.sum()),
            "bias_blocks": [{"t_s": float(ci / FS), "bias_dps": [float(x) for x in vi]} for ci, vi in zip(centers, vals)]}


def fuse(a_H: np.ndarray, w_H: np.ndarray) -> dict:
    """6-axis Fusion AHRS on head-frame data (a in m/s^2, w in deg/s, bias removed)."""
    import imufusion
    ahrs = imufusion.Ahrs()
    st = imufusion.AhrsSettings()
    st.convention = imufusion.CONVENTION_NWU
    for k, v in FUSION.items():
        setattr(st, k, v)
    st.sample_rate = FS
    ahrs.set_settings(st)
    n = a_H.shape[0]
    grav = np.empty((n, 3))
    quat = np.empty((n, 4))
    earth = np.empty((n, 3))
    recov = np.zeros(n, bool)
    a_g = np.ascontiguousarray(a_H / G)
    w = np.ascontiguousarray(w_H)
    for i in range(n):
        ahrs.update_no_magnetometer(w[i], a_g[i])
        grav[i] = ahrs.get_gravity()
        quat[i] = ahrs.get_quaternion()
        earth[i] = ahrs.get_earth_acceleration()
        f = ahrs.get_flags()
        recov[i] = f.acceleration_recovery or f.overrange_recovery or f.startup
    return {"gravity": grav, "quat": quat, "earth_acc": earth * G, "unreliable": recov}


def derive(a_H: np.ndarray, w_H: np.ndarray, fz: dict) -> dict:
    u = fz["gravity"] / np.linalg.norm(fz["gravity"], axis=1, keepdims=True)
    pitch = np.degrees(np.arcsin(np.clip(u[:, 0], -1, 1)))
    roll = np.degrees(np.arctan2(u[:, 1], u[:, 2]))
    abar = uniform_filter1d(a_H, size=int(VEDBA_WIN_S * FS) + 1, axis=0, mode="nearest")
    return {
        "omega_dps": np.linalg.norm(w_H, axis=1),
        "vedba_ms2": np.linalg.norm(a_H - abar, axis=1),
        "turn_dps": np.sum(w_H * u, axis=1),
        "pitch_deg": pitch, "roll_deg": roll, "up_head": u,
        "lin_acc_earth_ms2": fz["earth_acc"], "quat_wxyz": fz["quat"],
    }


def pc_time_ms(amp_sample: np.ndarray, fit: dict | None) -> np.ndarray | None:
    """Field-PC ms since the session-start day's midnight, NOT wrapped (pc_time_fit.json formula without the mod)."""
    if not fit:
        return None
    fs = float(fit.get("fs", 20000.0))
    t = (float(fit["rtc_start_ms_of_day"]) + float(fit["offset_ms"])
         + (1.0 + float(fit["drift_ppm"]) * 1e-6) * amp_sample / fs * 1000.0)
    for stp in fit.get("field_pc_clock_steps_inside") or []:
        t_s, jump = float(stp.get("t_s", stp.get("session_s", 0.0))), float(stp.get("jump_s", 0.0))
        t = t + np.where(amp_sample / fs >= t_s, jump * 1000.0, 0.0)
    return t


# ---------------------------------------------------------------- one session
def process_session(session_dir: Path, out_dir: Path, name: str, *, fit: dict | None = None, start_local: str | None = None,
                    max_seconds: float | None = None, meta: dict | None = None) -> dict:
    t0 = time.time()
    acc_B, gyr_B, sat_raw = load_raw(session_dir, max_seconds)
    a_B, w_B, sat = to_100hz(acc_B, gyr_B, sat_raw)
    a_H, w_H = a_B @ S, w_B @ S                       # v_H = S^T v_B (row vectors)
    cal = calibrate(a_H, w_H)
    a_H = a_H * cal["k_a"]
    w_H = w_H - cal["bias"]
    fz = fuse(a_H, w_H)
    d = derive(a_H, w_H, fz)
    n = a_H.shape[0]
    amp100 = np.arange(n) * 200
    t_pc = pc_time_ms(amp100.astype(np.float64), fit)

    # 50 Hz: magnitudes / rates averaged over sample pairs, angles and vectors decimated
    m = n // 2
    pair = lambda x: x[: 2 * m].reshape(m, 2, *x.shape[1:]).mean(axis=1)
    every2 = lambda x: x[: 2 * m: 2]
    out_dir.mkdir(parents=True, exist_ok=True)
    npz = {
        "fs": FS_OUT, "amp_sample": every2(amp100), "t_logger_s": every2(np.arange(n) / FS),
        "omega_dps": pair(d["omega_dps"]).astype(np.float32), "vedba_ms2": pair(d["vedba_ms2"]).astype(np.float32),
        "turn_dps": pair(d["turn_dps"]).astype(np.float32),
        "pitch_deg": every2(d["pitch_deg"]).astype(np.float32), "roll_deg": every2(d["roll_deg"]).astype(np.float32),
        "up_head": every2(d["up_head"]).astype(np.float32), "quat_wxyz": every2(d["quat_wxyz"]).astype(np.float32),
        "lin_acc_earth_ms2": pair(d["lin_acc_earth_ms2"]).astype(np.float32),
        "saturated": pair(sat.astype(float)) > 0, "unreliable": pair(fz["unreliable"].astype(float)) > 0,
        "quiet_calib": pair(cal["quiet"].astype(float)) > 0.5,
    }
    if t_pc is not None:
        npz["t_pc_ms"] = every2(t_pc)
    np.savez_compressed(out_dir / f"{name}.imu.npz", **npz)

    # per second (the table for sleep / video / WISER joins)
    ns = n // int(FS)
    blk = lambda x: x[: ns * int(FS)].reshape(ns, int(FS), *x.shape[1:])
    rows_1s = {
        "sec": np.arange(ns), "amp_sample_center": np.arange(ns) * 20000 + 10000,
        "vedba_mean": blk(d["vedba_ms2"]).mean(axis=1), "omega_mean": blk(d["omega_dps"]).mean(axis=1),
        "turn_net_deg": blk(d["turn_dps"]).sum(axis=1) / FS, "turn_abs_deg": np.abs(blk(d["turn_dps"])).sum(axis=1) / FS,
        "pitch_mean": blk(d["pitch_deg"]).mean(axis=1),
        "roll_mean": np.degrees(np.arctan2(np.sin(np.radians(blk(d["roll_deg"]))).mean(axis=1),
                                           np.cos(np.radians(blk(d["roll_deg"]))).mean(axis=1))),
        "saturated": blk(sat).any(axis=1), "unreliable": blk(fz["unreliable"]).mean(axis=1) > 0.5,
        "quiet_calib": blk(cal["quiet"]).mean(axis=1) > 0.5,
    }
    if t_pc is not None:
        tc = pc_time_ms(rows_1s["amp_sample_center"].astype(np.float64), fit)
        rows_1s["t_pc_ms"] = tc
        day0 = datetime.strptime((start_local or "")[:10], "%Y-%m-%d") if start_local else None
        if day0 is not None:
            base = day0.replace(tzinfo=TZ)
            rows_1s["t_pc_local"] = [(base + timedelta(milliseconds=float(x))).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] for x in tc]
            rows_1s["t_pc_unix_ms"] = [int(round((base + timedelta(milliseconds=float(x))).timestamp() * 1000)) for x in tc]
    cols = list(rows_1s)
    with open(out_dir / f"{name}.imu_1s.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in range(ns):
            w.writerow([(f"{rows_1s[c][i]:.4g}" if isinstance(rows_1s[c][i], (float, np.floating)) else
                         int(rows_1s[c][i]) if isinstance(rows_1s[c][i], (bool, np.bool_)) else rows_1s[c][i]) for c in cols])
    side = {
        "session_dir": str(session_dir), "n_samples_100hz": int(n), "duration_s": n / FS, "truncated_to_s": max_seconds,
        "axis_map_S_vB_eq_S_vH": S.tolist(), "k_a": cal["k_a"], "n_quiet_s": cal["n_quiet_s"],
        "bias_blocks": cal["bias_blocks"], "fusion": {**FUSION, "convention": "NWU", "sample_rate": FS},
        "thresholds": {"quiet_w_dps": QUIET_W_DPS, "quiet_a_frac_g": QUIET_A_FRAC, "bias_block_s": BIAS_BLOCK_S,
                       "vedba_window_s": VEDBA_WIN_S},
        "saturated_frac": float(sat.mean()), "unreliable_frac": float(fz["unreliable"].mean()),
        "pc_time": "pc_time_fit.json formula" if fit else "none (logger time only)",
        "pc_time_fit": {k: fit.get(k) for k in ("verdict", "drift_ppm", "offset_ms", "n_anchors", "native_residual_ms")} if fit else None,
        "elapsed_s": round(time.time() - t0, 1), "git_commit": git_commit(), "written_utc": utc_now_iso(),
    }
    if meta:
        side.update(meta)
    (out_dir / f"{name}.imu.json").write_text(json.dumps(side, indent=2), encoding="utf-8")
    return side


# ---------------------------------------------------------------- self-test
def _selftest() -> int:
    """Synthetic head motion (still periods, pitch/roll oscillations, 90 deg/s turns, gyro bias, noise) written as a
    16-lane analogin.dat in the SENSOR frame; the pipeline must recover pitch/roll, the turn rate and the bias."""
    import tempfile
    from scipy.spatial.transform import Rotation as Rot
    rng = np.random.default_rng(3)
    dur = 600.0
    t = np.arange(int(dur * FS_RAW)) / FS_RAW
    moving = (t % 60) >= 20                                   # 20 s still, 40 s moving, repeated
    pitch = np.where(moving, -30 + 20 * np.sin(2 * np.pi * 0.1 * t), -30.0)
    roll = np.where(moving, 10 * np.sin(2 * np.pi * 0.05 * t), 0.0)
    yaw_rate = np.where(moving & ((t % 20) < 2), 90.0, 0.0)    # 2-s turns at 90 deg/s
    yaw = np.cumsum(yaw_rate) / FS_RAW
    R = Rot.from_euler("ZYX", np.column_stack([yaw, -pitch, roll]), degrees=True)   # head -> world
    w_H = np.degrees((R[:-1].inv() * R[1:]).as_rotvec() * FS_RAW)
    w_H = np.vstack([w_H, w_H[-1]])
    a_H = R.inv().apply(np.tile([0.0, 0.0, G], (len(t), 1)))
    bias_true = np.array([0.5, -1.0, 1.5])
    a_H = a_H + rng.normal(0, 0.05, a_H.shape)
    w_Hm = w_H + bias_true + rng.normal(0, 0.3, w_H.shape)
    a_B, w_B = a_H @ S.T, w_Hm @ S.T                             # v_B = S v_H
    raw = np.zeros((len(t), LANES), np.int16)
    raw[:, 1:4] = np.clip(np.rint(a_B / (ACC_FS_G * G) * 32768), -32768, 32767)
    raw[:, 4:7] = np.clip(np.rint(w_B / GYR_FS_DPS * 32768), -32768, 32767)
    raw[:, 7] = -32767                                            # the saturated magnetometer x
    ok = True
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "sess"
        sd.mkdir()
        raw.tofile(sd / "analogin.dat")
        side = process_session(sd, Path(td) / "out", "sess")
        with np.load(Path(td) / "out" / "sess.imu.npz") as zf:     # closed before the temp folder is removed (Windows)
            z = {key: zf[key] for key in zf.files}
        k = np.round(z["t_logger_s"] * FS_RAW).astype(int)
        keep = z["t_logger_s"] > 20
        truth_turn = (R[k].apply(np.radians(w_H[k])) * np.array([0, 0, 1])).sum(axis=1)
        e_p = np.sqrt(np.mean((z["pitch_deg"][keep] - pitch[k][keep]) ** 2))
        e_r = np.sqrt(np.mean((z["roll_deg"][keep] - roll[k][keep]) ** 2))
        tt = np.degrees(truth_turn)
        e_t = np.sqrt(np.mean((z["turn_dps"][keep] - tt[keep]) ** 2))
        bias_est = np.array(side["bias_blocks"][0]["bias_dps"]) if side["bias_blocks"] else np.full(3, np.nan)
        checks = [
            (f"pitch RMS error {e_p:.2f} deg < 2", e_p < 2),
            (f"roll RMS error {e_r:.2f} deg < 2", e_r < 2),
            (f"turn-rate RMS error {e_t:.2f} deg/s < 5", e_t < 5),
            (f"gyro bias recovered {np.round(bias_est, 2)} vs {bias_true} (< 0.2 deg/s)", np.all(np.abs(bias_est - bias_true) < 0.2)),
            (f"k_a {side['k_a']:.3f} within 1% of 1", abs(side["k_a"] - 1) < 0.01),
            ("still periods quiet, turns not", bool(z["quiet_calib"][(z["t_logger_s"] % 60) < 18].mean() > 0.9)),
        ]
        # short session with a partial last second and no bias block (the path that crashed on real data 2026-09-28)
        try:
            short = process_session(sd, Path(td) / "out", "short", max_seconds=25.12)   # 20 quiet s < BIAS_MIN_QUIET_S
            checks.append((f"short session (25.12 s) runs on the fallback bias (blocks: {len(short['bias_blocks'])}, expect 0)",
                           len(short["bias_blocks"]) == 0))
        except Exception as e:  # noqa: BLE001
            checks.append((f"short session runs ({type(e).__name__}: {e})", False))
    for name_, c in checks:
        print(f"[{'PASS' if c else 'FAIL'}] {name_}")
        ok &= bool(c)
    print("PASS - make_imu self-test" if ok else "FAIL - make_imu self-test")
    return 0 if ok else 1


# ---------------------------------------------------------------- CLI
def _run_one(args: tuple) -> str:
    """One session; an error is reported and the batch goes on (nothing partial is left: the sidecar is written last)."""
    sd, out_dir, name, fit, start_local, max_seconds, meta = args
    try:
        side = process_session(Path(sd), Path(out_dir), name, fit=fit, start_local=start_local, max_seconds=max_seconds, meta=meta)
    except Exception as e:  # noqa: BLE001
        return f"ERROR {meta['animal']} {name}: {type(e).__name__}: {e}"
    return f"{meta['animal']} {name}: {side['duration_s'] / 3600:.2f} h in {side['elapsed_s']} s, k_a {side['k_a']:.3f}, pc_time {side['pc_time']}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--animal", nargs="*", default=None)
    ap.add_argument("--session", nargs="*", default=None)
    ap.add_argument("--raw-root", default=None)
    ap.add_argument("--out-root", default=None, help="default <ephys.analysis_root>/imu")
    ap.add_argument("--pc-time-root", default=None, help="folder with <SFxx>/<session>/pc_time_fit.json")
    ap.add_argument("--workers", type=int, default=4, help="sessions in parallel")
    ap.add_argument("--min-seconds", type=float, default=60.0)
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--include-flagged", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    raw = raw_ephys_root(a.cohort, a.raw_root)
    root = imu_root(a.cohort, a.out_root)
    sel = select_sessions(a.cohort, a.animal, a.session, include_flagged=a.include_flagged, include_fm62=False,
                          min_seconds=a.min_seconds)
    jobs = []
    for r in sel:
        animal = _norm_animal(r["animal"])
        name = r["session"]
        if (root / animal / f"{name}.imu.json").exists() and not a.overwrite:
            continue
        fit = None
        if a.pc_time_root:
            fp = Path(a.pc_time_root) / animal / name / "pc_time_fit.json"
            fit = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None
        jobs.append((str(find_session_dir(raw, r["animal"], name)), str(root / animal), name, fit, r.get("start_local"),
                     a.max_seconds, {"cohort": resolve_cohort(a.cohort), "animal": animal, "session": name,
                                     "firmware": int(r.get("firmware") or 0), "start_local": r.get("start_local")}))
    print(f"{len(sel)} selected, {len(jobs)} to process -> {root}")
    with ProcessPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for msg in ex.map(_run_one, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
