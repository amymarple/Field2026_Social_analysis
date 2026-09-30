r"""Head-IMU attitude, Phase 0 (cohort 2026c): gyro self-calibration, saturation handling, an honest attitude-error model,
and the pre-registered gate that decides whether inertial fusion with WISER is worth attempting. IMU only - no WISER.

Plan: implementation_plan/2026-09-30-imu-attitude-phase0.md (approved by the user 2026-09-30 "phase0 开始").
Follows the V4 audit (change_log/2026-09-29-wiser-ins-fusion.md, "Audit of the V4 result") and reuses its bout
construction + gravity-propagation test (audit_20260930/coning_test.py) so every number is comparable.

Inputs (cached, read-only; raw E: is never read):
  A1  <imu_raw>/<SFxx>/<session>__<start>_<end>.npz   int16 lanes 1-6 @ 1250 Hz (sensor frame), sat, frozen, fit/meta
  A3  <imu100>/<SFxx>/night_<date>.npz                100 Hz calibrated head-frame acc/gyr, quiet, flags, calib_json
Outputs:
  bulk   <OUT_ROOT>/<cohort>/imu_attitude_phase0_<ts>/   per-bout / floor / saturation-run / per-second CSVs, fits, figures
  A4     <imu16>/<SFxx>/night_<date>.npz  (+ README.md next to the root)   16-Hz world-frame horizontal specific force
         (2 Hz default, 1/4 Hz variants), attitude quaternion, sigma_theta(t_active), flags, behaviour-band powers
  report results/<cohort>/wiser_baseline/reports/wiser_baseline_imu_attitude_phase0_<cohort>.md (+ figures, pointer
         run_manifest_imu_attitude_phase0_<cohort>.json; the folder's run_manifest.json is never touched)
Tasks: 0a floor, 0b gyro matrix M per animal (tuning night; CV model choice; bootstrap CIs; held-out test night),
       0c saturation classes + log-quadratic reconstruction, 0d 100-Hz attitude -> A4, 0e sigma_theta growth law, GATE.

Usage:
  python wiser/scripts/analyze_imu_attitude_phase0.py --cohort 2026c [--no-a4] [--animals SF09 SF12]
  python wiser/scripts/analyze_imu_attitude_phase0.py --report-only <run_dir>
  python wiser/scripts/analyze_imu_attitude_phase0.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit, prange
from scipy import signal
from scipy.optimize import least_squares
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import build_imu_wiser_cache as B  # noqa: E402  (A1 loader + cache_unix_ms; unmodified)
import analyze_wiser_ins_fusion as V4  # noqa: E402  (Hampel filter; unmodified)
import make_imu as MI  # noqa: E402  (S map, G)
import read_imu as RI  # noqa: E402  (layout constants)
import _common as EC  # noqa: E402  (git_commit)

DIRECTION = "wiser_baseline"
NAME = "imu_attitude_phase0"
STEM = f"{DIRECTION}_imu_attitude_phase0"
G = MI.G
FS_RAW, FS100, FS16 = 1250.0, 100.0, 16.0
ACC_SCALE = RI.ACC_FS_G * RI.G / 32768      # m/s^2 per count
GYR_SCALE = RI.GYR_FS_DPS / 32768           # deg/s per count
D2R, R2D = math.pi / 180.0, 180.0 / math.pi
S = np.asarray(MI.S, dtype=np.float64)      # v_B = S v_H ; v_H = S^T v_B  ->  rows @ S
CLASSES = ["impact", "shake_train", "short_broadband", "suspect_monotone", "rotation"]
BANDS = [(2, 4), (4, 8), (8, 12), (12, 20)]


def log(msg: str, fh=None) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh is not None:
        fh.write(line + "\n")
        fh.flush()


def _jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


# ====================================================================================================== numba kernels
@njit(cache=True)
def _rot_vec(g, rx, ry, rz):
    """Rodrigues: rotate unit vector g by rotation vector r (in place semantics via return)."""
    th = math.sqrt(rx * rx + ry * ry + rz * rz)
    if th < 1e-12:
        return g[0], g[1], g[2]
    kx, ky, kz = rx / th, ry / th, rz / th
    c, s = math.cos(th), math.sin(th)
    dot = kx * g[0] + ky * g[1] + kz * g[2]
    cx = ky * g[2] - kz * g[1]
    cy = kz * g[0] - kx * g[2]
    cz = kx * g[1] - ky * g[0]
    x = g[0] * c + cx * s + kx * dot * (1 - c)
    y = g[1] * c + cy * s + ky * dot * (1 - c)
    z = g[2] * c + cz * s + kz * dot * (1 - c)
    n = math.sqrt(x * x + y * y + z * z)
    return x / n, y / n, z / n


@njit(parallel=True, cache=True)
def propagate_bouts(g0, w, offs, dt, out):
    """For bout i: g <- Exp(-w_k dt) g over w[offs[i]:offs[i+1]] (rad/s, head frame); out[i] = final g (audit test)."""
    nb = offs.shape[0] - 1
    for i in prange(nb):
        g = np.empty(3)
        g[0], g[1], g[2] = g0[i, 0], g0[i, 1], g0[i, 2]
        for k in range(offs[i], offs[i + 1]):
            g[0], g[1], g[2] = _rot_vec(g, -w[k, 0] * dt, -w[k, 1] * dt, -w[k, 2] * dt)
        out[i, 0], out[i, 1], out[i, 2] = g[0], g[1], g[2]


@njit(parallel=True, cache=True)
def bout_stats(g0, w, a, offs, dt, out):
    """Per bout: total rotation (deg), mean horizontal |a_h| (m/s^2, using the propagated gravity direction), max |w| (deg/s)."""
    nb = offs.shape[0] - 1
    for i in prange(nb):
        g = np.empty(3)
        g[0], g[1], g[2] = g0[i, 0], g0[i, 1], g0[i, 2]
        rot = 0.0
        ah = 0.0
        wmax = 0.0
        n = 0
        for k in range(offs[i], offs[i + 1]):
            wn = math.sqrt(w[k, 0] ** 2 + w[k, 1] ** 2 + w[k, 2] ** 2)
            rot += wn * dt
            if wn > wmax:
                wmax = wn
            g[0], g[1], g[2] = _rot_vec(g, -w[k, 0] * dt, -w[k, 1] * dt, -w[k, 2] * dt)
            d = a[k, 0] * g[0] + a[k, 1] * g[1] + a[k, 2] * g[2]
            hx, hy, hz = a[k, 0] - d * g[0], a[k, 1] - d * g[1], a[k, 2] - d * g[2]
            ah += math.sqrt(hx * hx + hy * hy + hz * hz)
            n += 1
        out[i, 0] = rot * 180.0 / math.pi
        out[i, 1] = ah / max(n, 1)
        out[i, 2] = wmax * 180.0 / math.pi


@njit(cache=True)
def _qmul(a, b):
    return (a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
            a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
            a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
            a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0])


@njit(cache=True)
def _qexp(rx, ry, rz):
    th = math.sqrt(rx * rx + ry * ry + rz * rz)
    if th < 1e-12:
        return (1.0, 0.5 * rx, 0.5 * ry, 0.5 * rz)
    s = math.sin(0.5 * th) / th
    return (math.cos(0.5 * th), rx * s, ry * s, rz * s)


@njit(cache=True)
def _g_head(q):
    """Predicted normalised specific force in the head frame at rest = R(q)^T e_z (q maps head -> world)."""
    w, x, y, z = q
    return (2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y))


@njit(cache=True)
def integrate_attitude(w, a, quiet, invalid, dt, gain, q0, q_out, t_active):
    """q_{k+1} = q_k (x) Exp(w_k dt); in quiet samples the tilt is pulled toward the measured acc direction with `gain`
    (q <- q (x) Exp(-gain * (g_pred x a_hat)); yaw untouched). Invalid samples hold q. t_active = s since last quiet."""
    n = w.shape[0]
    q = (q0[0], q0[1], q0[2], q0[3])
    ta = 0.0
    for k in range(n):
        if not invalid[k]:
            q = _qmul(q, _qexp(w[k, 0] * dt, w[k, 1] * dt, w[k, 2] * dt))
            if quiet[k]:
                an = math.sqrt(a[k, 0] ** 2 + a[k, 1] ** 2 + a[k, 2] ** 2)
                if an > 1e-6:
                    ax, ay, az = a[k, 0] / an, a[k, 1] / an, a[k, 2] / an
                    gx, gy, gz = _g_head(q)
                    dx, dy, dz = gy * az - gz * ay, gz * ax - gx * az, gx * ay - gy * ax
                    q = _qmul(q, _qexp(-gain * dx, -gain * dy, -gain * dz))
                ta = 0.0
            else:
                ta += dt
        else:
            ta += dt
        nq = math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2 + q[3] ** 2)
        q = (q[0] / nq, q[1] / nq, q[2] / nq, q[3] / nq)
        q_out[k, 0], q_out[k, 1], q_out[k, 2], q_out[k, 3] = q[0], q[1], q[2], q[3]
        t_active[k] = ta


def rotate_world(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """v_world = R(q) v_head for arrays q (n,4) [w,x,y,z], v (n,3)."""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    R = np.empty((len(q), 3, 3))
    R[:, 0, 0] = 1 - 2 * (y * y + z * z); R[:, 0, 1] = 2 * (x * y - w * z); R[:, 0, 2] = 2 * (x * z + w * y)
    R[:, 1, 0] = 2 * (x * y + w * z); R[:, 1, 1] = 1 - 2 * (x * x + z * z); R[:, 1, 2] = 2 * (y * z - w * x)
    R[:, 2, 0] = 2 * (x * z - w * y); R[:, 2, 1] = 2 * (y * z + w * x); R[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return np.einsum("nij,nj->ni", R, v)


def q_from_up(u: np.ndarray) -> np.ndarray:
    """Quaternion (head -> world, yaw 0) whose R^T e_z equals the unit head-frame up vector u."""
    u = u / np.linalg.norm(u)
    ez = np.array([0.0, 0.0, 1.0])
    axis = np.cross(u, ez)
    s = np.linalg.norm(axis)
    if s < 1e-9:
        return np.array([1.0, 0, 0, 0]) if u[2] > 0 else np.array([0.0, 1, 0, 0])
    ang = math.atan2(s, float(u @ ez))
    axis = axis / s
    return np.r_[math.cos(ang / 2), math.sin(ang / 2) * axis]


def angle_deg(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    u = u / np.linalg.norm(u, axis=-1, keepdims=True)
    v = v / np.linalg.norm(v, axis=-1, keepdims=True)
    return np.degrees(np.arccos(np.clip(np.sum(u * v, axis=-1), -1.0, 1.0)))


def true_runs(m: np.ndarray) -> np.ndarray:
    """(n_runs, 2) start/end(excl.) of True runs."""
    d = np.diff(np.r_[0, m.astype(np.int8), 0])
    return np.column_stack([np.flatnonzero(d == 1), np.flatnonzero(d == -1)])


# ====================================================================================================== loading
def load_night(animal: str, night: str, cfg: dict) -> dict:
    roots = cfg["cache_roots"]
    p3 = Path(roots["imu100"]) / animal / f"{night}.npz"
    z = np.load(p3, allow_pickle=True)
    cal = json.loads(str(z["calib_json"]))
    meta3 = json.loads(str(z["meta_json"]))
    a1 = B.load_imu_raw_cache(Path(meta3["source_a1"]))
    meta1 = json.loads(str(a1["meta_json"]))
    t100 = z["t_unix_ms"].astype(np.float64)
    bn = cal["bias_nodes_1min"]
    tb, bb = np.asarray(bn["t_unix_ms"], float), np.asarray(bn["bias_dps"], float)
    bias100 = np.column_stack([np.interp(t100, tb, bb[:, k]) for k in range(3)])
    return {"animal": animal, "night": night, "a3_path": p3, "a1_path": Path(meta3["source_a1"]), "cal": cal, "meta3": meta3,
            "meta1": meta1, "six": a1["six"], "sat_raw": a1["sat"], "frozen_raw": a1["frozen"], "t100": t100,
            "acc100": z["acc"].astype(np.float64), "gyr_a3": z["gyr"].astype(np.float64), "quiet": z["quiet"].astype(bool),
            "sat_gyr100": z["sat_gyr"].astype(bool), "frozen100": z["frozen"].astype(bool), "bias100": bias100,
            "a1_bytes": Path(meta3["source_a1"]).stat().st_size, "a3_bytes": p3.stat().st_size}


# ====================================================================================================== 0c saturation
def _acc_hf_fraction(acc_c: np.ndarray, c: int, half: int, fs: float, band: tuple) -> float:
    lo, hi = max(0, c - half), min(acc_c.shape[0], c + half + 1)
    seg = acc_c[lo:hi].astype(np.float64)
    seg = seg - seg.mean(axis=0)
    if seg.shape[0] < 8:
        return np.nan
    P = np.abs(np.fft.rfft(seg, axis=0)) ** 2
    f = np.fft.rfftfreq(seg.shape[0], 1.0 / fs)
    tot = P[1:].sum()
    return float(P[(f >= band[0]) & (f <= band[1])].sum() / tot) if tot > 0 else np.nan


def _slope(x: np.ndarray) -> float:
    if len(x) < 2:
        return np.nan
    t = np.arange(len(x), dtype=float)
    return float(np.polyfit(t, x.astype(float), 1)[0])


def held_readings(x_lane: np.ndarray) -> np.ndarray:
    """Start indices of the constant runs ('held readings') of one raw lane: the IMU updates at ~190 Hz and the logger
    repeats each reading over ~6.6 samples at 1250 Hz. Returns starts (k,), with a final sentinel = len(x)."""
    chg = np.flatnonzero(np.diff(x_lane) != 0) + 1
    return np.r_[0, chg, len(x_lane)]


def shoulder_readings(starts: np.ndarray, x_lane: np.ndarray, a: int, b: int, k: int) -> tuple:
    """The k held readings before raw index a and after raw index b: (centres (2k,), values (2k,), inside_starts, inside_ends)
    where inside_* delimit the readings overlapping [a, b). Returns None when fewer than k readings exist on a side."""
    ia = int(np.searchsorted(starts, a, side="right")) - 1        # reading containing a
    ib = int(np.searchsorted(starts, b - 1, side="right")) - 1    # reading containing b-1
    if ia - k < 0 or ib + k + 1 >= len(starts):
        return None
    pre = np.arange(ia - k, ia)
    post = np.arange(ib + 1, ib + 1 + k)
    idx = np.r_[pre, post]
    cen = 0.5 * (starts[idx] + starts[idx + 1] - 1)
    val = x_lane[starts[idx]].astype(np.float64)
    ins_s, ins_e = starts[ia:ib + 1], starts[ia + 1:ib + 2]
    return cen, val, ins_s, ins_e


def saturation_runs(six: np.ndarray, sat_raw: np.ndarray, t_raw_ms_of, cfg: dict) -> pd.DataFrame:
    """Every clipped run on a gyro lane with its features, train structure and class (plan 0c, rule as pre-registered)."""
    sc = cfg["saturation"]
    rail = float(sc["rail_counts"])
    sh = int(sc["shoulder_samples"])
    half_acc = int(round(sc["acc_window_ms"] / 1000 * FS_RAW))
    half_pk = int(round(sc["acc_peak_window_ms"] / 1000 * FS_RAW))
    n = six.shape[0]
    acc_sat_any = sat_raw[:, :3].any(axis=1)
    acc_norm_g = np.linalg.norm(six[:, :3].astype(np.float32), axis=1) * np.float32(ACC_SCALE / G)
    rows = []
    for lane in (3, 4, 5):
        runs = true_runs(sat_raw[:, lane])
        if len(runs) == 0:
            continue
        onsets = runs[:, 0]
        x = six[:, lane]
        starts = held_readings(x)
        for j, (a, b) in enumerate(runs):
            sign = int(np.sign(x[a])) if x[a] != 0 else 1
            shr = shoulder_readings(starts, x, int(a), int(b), sh)
            if shr is not None:
                cen, val, ins_s, ins_e = shr
                dtp = max(cen[sh - 1] - cen[0], 1.0) / FS_RAW * 1000
                dtn = max(cen[-1] - cen[sh], 1.0) / FS_RAW * 1000
                entry = (val[sh - 1] - val[0]) * GYR_SCALE / dtp
                exit_ = (val[-1] - val[sh]) * GYR_SCALE / dtn
                clean = bool((np.abs(val) < rail).all())
            else:
                entry = exit_ = np.nan
                clean = False
            n_read = max(1, int(round((b - a) / float(sc["imu_hold_samples"]))))   # clipped readings are indistinguishable (all at the rail)
            others = [l for l in (3, 4, 5) if l != lane]
            lo, hi = max(0, a - half_pk), min(n, b + half_pk)
            rec = {"lane": lane + 1, "i0": int(a), "i1": int(b), "n": int(b - a), "dur_ms": (b - a) / FS_RAW * 1000, "n_readings": n_read, "sign": sign,
                   "entry_slope_dps_per_ms": entry, "exit_slope_dps_per_ms": exit_,
                   "other_lanes_max_dps": float(np.abs(six[a:b][:, others]).max()) * GYR_SCALE if b > a else np.nan,
                   "acc_max_g": float(acc_norm_g[lo:hi].max()), "acc_sat": bool(acc_sat_any[lo:hi].any()),
                   "acc_hf_frac": _acc_hf_fraction(six[:, :3], (a + b) // 2, half_acc, FS_RAW, tuple(sc["acc_hf_band_hz"])),
                   "gap_prev_ms": (a - onsets[j - 1]) / FS_RAW * 1000 if j > 0 else np.nan,
                   "gap_next_ms": (onsets[j + 1] - a) / FS_RAW * 1000 if j + 1 < len(runs) else np.nan,
                   "sign_prev": int(np.sign(x[runs[j - 1, 0]])) if j > 0 else 0,
                   "sign_next": int(np.sign(x[runs[j + 1, 0]])) if j + 1 < len(runs) else 0,
                   "shoulders_clean": clean}
            rows.append(rec)
    R = pd.DataFrame(rows)
    if R.empty:
        return R
    R = R.sort_values(["lane", "i0"]).reset_index(drop=True)
    R["t_unix_ms"] = t_raw_ms_of(R["i0"].to_numpy())
    # trains: same lane, onset spacing <= train_max_spacing_ms
    tmax = float(sc["train_max_spacing_ms"])
    train_id = np.zeros(len(R), int)
    tid = 0
    for lane, grp in R.groupby("lane", sort=False):
        idx = grp.index.to_numpy()
        gaps = grp["gap_prev_ms"].to_numpy()
        for k, i in enumerate(idx):
            if k == 0 or not (gaps[k] <= tmax):
                tid += 1
            train_id[i] = tid
    R["train_id"] = train_id
    ts = R.groupby("train_id")
    R["train_size"] = ts["i0"].transform("size")
    lo_s, hi_s = sc["shake_spacing_ms"]
    alt_prev = (R["sign_prev"] == -R["sign"]) & (R["gap_prev_ms"] <= tmax)
    alt_next = (R["sign_next"] == -R["sign"]) & (R["gap_next_ms"] <= tmax)
    R["alt_pair_prev"] = alt_prev
    in_win_prev = (R["gap_prev_ms"] >= lo_s) & (R["gap_prev_ms"] <= hi_s)
    R["_pair_ok"] = (alt_prev & in_win_prev).astype(float)
    tr = R[R["train_size"] >= 2].groupby("train_id")
    pairs_ok = tr["_pair_ok"].sum()
    pairs_n = tr["i0"].size() - 1
    frac = (pairs_ok / pairs_n.clip(lower=1)).rename("alt_frac")
    R = R.merge(frac, left_on="train_id", right_index=True, how="left")
    R["alt_frac"] = R["alt_frac"].fillna(0.0)
    R["train_acc_max_g"] = ts["acc_max_g"].transform("max")
    R["acc_gt_2g"] = R["train_acc_max_g"] * G > float(sc["acc_2g_ms2"])
    R = R.drop(columns=["_pair_ok"])
    # classes (priority order)
    cls = np.full(len(R), "rotation", dtype=object)
    is_shake = (R["train_size"] >= 2) & (R["alt_frac"] >= float(sc["shake_alternation_min"]))
    is_short = (R["n_readings"] <= int(sc["short_broadband_max_readings"])) & (R["acc_hf_frac"] >= float(sc["acc_hf_fraction_max"]))
    cls[is_short.to_numpy()] = "short_broadband"
    cls[is_shake.to_numpy()] = "shake_train"
    cls[R["acc_sat"].to_numpy()] = "impact"
    R["cls"] = cls
    return R


def reconstruct_runs(x_counts: np.ndarray, R: pd.DataFrame, sat_raw_gyr: np.ndarray, cfg: dict) -> pd.DataFrame:
    """Log-quadratic (Gaussian-shaped) fit through the 4 + 4 held readings around every run not impact/short_broadband, on
    the reading centres (the IMU updates at ~190 Hz; each reading is held ~6.6 raw samples). Replaces the clipped readings
    in x_counts (float32 (n,3) gyro lanes, IN PLACE), returns R with recon columns, the isolated runs' implied net rotation
    and the final class (suspect_monotone vs rotation)."""
    sc = cfg["saturation"]
    rail = float(sc["rail_counts"])
    sh = int(sc["shoulder_samples"])
    cap = float(sc["recon_peak_max_rails"]) * rail
    win = int(round(sc["suspect_window_ms"] / 1000 * FS_RAW))
    n = x_counts.shape[0]
    R = R.copy()
    R["recon"] = False
    R["recon_failed"] = False
    R["peak_dps"] = np.nan
    R["missing_deg"] = 0.0
    R["net_deg_pm25ms"] = np.nan
    starts_by_lane = {l: held_readings(np.round(x_counts[:, l]).astype(np.int32)) for l in range(3)}
    for i, r in R.iterrows():
        if r["cls"] in ("impact", "short_broadband"):
            continue
        a, b, l = int(r["i0"]), int(r["i1"]), int(r["lane"]) - 4
        shr = shoulder_readings(starts_by_lane[l], x_counts[:, l], a, b, sh)
        if shr is None or not r["shoulders_clean"]:
            R.at[i, "recon_failed"] = True
            continue
        cen, val, ins_s, ins_e = shr
        y = np.abs(val)
        if (y <= 1).any() or (y >= rail).any():
            R.at[i, "recon_failed"] = True
            continue
        c = 0.5 * (a + b - 1)
        ok = False
        for kk in (int(sc.get("recon_shoulder_readings", 2)), int(sc.get("recon_shoulder_readings", 2)) + 1):   # innermost kk readings per side
            selr = np.r_[np.arange(sh - kk, sh), np.arange(sh, sh + kk)]
            tt = cen[selr] - c
            p = np.polyfit(tt, np.log(y[selr]), 2)
            ok = p[0] < 0
            if ok:
                tstar = -p[1] / (2 * p[0])
                ok = (a - c - 1.0) <= tstar <= (b - 1 - c + 1.0)
                peak = math.exp(np.polyval(p, tstar)) if ok else np.nan
                ok = ok and peak <= cap
            if ok:
                break
        if not ok:
            R.at[i, "recon_failed"] = True
            continue
        k = np.arange(a, b) - c
        fit = np.maximum(np.exp(np.polyval(p, k)), rail)
        x_counts[a:b, l] = (r["sign"] * fit).astype(np.float32)
        R.at[i, "recon"] = True
        R.at[i, "peak_dps"] = peak * GYR_SCALE
        R.at[i, "missing_deg"] = float((fit - rail).sum()) * GYR_SCALE / FS_RAW
    # implied net rotation over run +- 25 ms (reconstructed lane), for isolated runs
    for i, r in R.iterrows():
        a, b, l = int(r["i0"]), int(r["i1"]), int(r["lane"]) - 4
        lo, hi = max(0, a - win), min(n, b + win)
        R.at[i, "net_deg_pm25ms"] = float(x_counts[lo:hi, l].astype(np.float64).sum()) * GYR_SCALE / FS_RAW
    iso = (R["cls"] == "rotation") & (R["train_size"] == 1)
    suspect = iso & (R["net_deg_pm25ms"].abs() >= float(sc["suspect_net_deg"])) & (R["acc_max_g"] * G < float(sc["acc_2g_ms2"]))
    R.loc[suspect, "cls"] = "suspect_monotone"
    # per-train net angle
    net = {}
    for tid, grp in R.groupby("train_id"):
        l = int(grp["lane"].iloc[0]) - 4
        lo, hi = max(0, int(grp["i0"].min()) - win), min(n, int(grp["i1"].max()) + win)
        net[tid] = float(x_counts[lo:hi, l].astype(np.float64).sum()) * GYR_SCALE / FS_RAW
    R["train_net_deg"] = R["train_id"].map(net)
    return R


# ====================================================================================================== gyro chain
def hampel_counts(six: np.ndarray, sat_raw: np.ndarray, cfg: dict) -> np.ndarray:
    """V4's Hampel filter on the six raw lanes (float32 counts). Saturated samples are never replaced."""
    ch = cfg["chain"]
    x = six.astype(np.float32)
    hx = np.empty_like(x)
    fl = np.zeros(x.shape, bool)
    V4._hampel_lanes(x, sat_raw, int(ch["hampel_half_window"]), float(ch["hampel_nsigma"]),
                     V4.hampel_floor(six, float(ch["hampel_mad_floor_counts"])), hx, fl)
    del x, fl
    return hx


def to_100hz_head(counts: np.ndarray, scale: float, cfg: dict, n100: int) -> np.ndarray:
    """(n,3) sensor-frame counts -> 40-Hz zero-phase Butterworth-4 -> resample_poly(2,25) -> head frame, physical units."""
    ch = cfg["chain"]
    sos = signal.butter(int(ch["butter_order"]), float(ch["fc_hz"]), fs=FS_RAW, output="sos")
    cols = []
    for l in range(3):
        y = signal.sosfiltfilt(sos, counts[:, l].astype(np.float64) * scale)
        cols.append(signal.resample_poly(y, 2, 25)[:n100])
    m = min(len(c) for c in cols)
    out = np.column_stack([c[:m] for c in cols]) @ S
    if m < n100:
        out = np.vstack([out, np.repeat(out[-1:], n100 - m, axis=0)])
    return out


def gyro_chain(night: dict, cfg: dict, do_recon: bool = True) -> dict:
    """Hampel -> saturation classes (+ reconstruction) -> 100-Hz head-frame gyro (deg/s, pre-bias). Also the no-recon stream."""
    six, sat_raw = night["six"], night["sat_raw"]
    n100 = len(night["t100"])
    t_raw_of = lambda idx: np.interp(np.asarray(idx, float), 12.5 * np.arange(n100), night["t100"])
    hx = hampel_counts(six, sat_raw, cfg)
    R = saturation_runs(six, sat_raw, t_raw_of, cfg)
    gyr_counts = hx[:, 3:6]
    w100_norecon = to_100hz_head(gyr_counts, GYR_SCALE, cfg, n100)
    if do_recon and len(R):
        R = reconstruct_runs(gyr_counts, R, sat_raw[:, 3:6], cfg)
        w100 = to_100hz_head(gyr_counts, GYR_SCALE, cfg, n100)
    else:
        w100 = w100_norecon.copy()
        if len(R):
            for c in ("recon", "recon_failed"):
                R[c] = False
            R["missing_deg"], R["peak_dps"], R["net_deg_pm25ms"], R["train_net_deg"] = 0.0, np.nan, np.nan, np.nan
    # shake-train spans and reconstructed spans, mapped to 100 Hz
    shake100 = np.zeros(n100, bool)
    recon100 = np.zeros(n100, bool)
    if len(R):
        win = int(round(cfg["saturation"]["suspect_window_ms"] / 1000 * FS_RAW))
        for tid, grp in R[R["cls"] == "shake_train"].groupby("train_id"):
            a, b = int(grp["i0"].min()) - win, int(grp["i1"].max()) + win
            shake100[max(0, int(a / 12.5)):min(n100, int(math.ceil(b / 12.5)) + 1)] = True
        for _, r in R[R["recon"]].iterrows():
            recon100[max(0, int(r["i0"] / 12.5)):min(n100, int(math.ceil(r["i1"] / 12.5)) + 1)] = True
    w_raw_norm = np.linalg.norm(six[:, 3:6].astype(np.float32), axis=1) * np.float32(GYR_SCALE)
    del hx
    return {"w100": w100, "w100_norecon": w100_norecon, "sat_runs": R, "shake100": shake100, "recon100": recon100,
            "w_raw_norm": w_raw_norm, "sat_gyr_raw": sat_raw[:, 3:6].any(axis=1)}


# ====================================================================================================== bouts (audit)
def make_bouts(quiet: np.ndarray, cfg: dict) -> np.ndarray:
    """Maximal non-quiet runs [a,b) with min_s <= dur <= max_s and the edge windows inside the array (coning_test rule)."""
    bc = cfg["bouts"]
    e = int(bc["edge_window_s"] * FS100)
    n = len(quiet)
    runs = true_runs(~quiet)
    dur = (runs[:, 1] - runs[:, 0]) / FS100
    keep = (dur >= bc["min_s"]) & (dur <= bc["max_s"]) & (runs[:, 0] >= e) & (runs[:, 1] + e <= n)
    return runs[keep]


def edge_gravity(acc: np.ndarray, bouts: np.ndarray, e: int) -> tuple:
    if len(bouts) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    gs = np.stack([acc[a - e:a].mean(axis=0) for a, b in bouts])
    ge = np.stack([acc[b:b + e].mean(axis=0) for a, b in bouts])
    return gs / np.linalg.norm(gs, axis=1, keepdims=True), ge / np.linalg.norm(ge, axis=1, keepdims=True)


class BoutSet:
    """Concatenated 100-Hz (w - b) (deg/s, head frame) of the bouts plus start/end gravity, for the numba kernels."""

    def __init__(self, wb: np.ndarray, acc: np.ndarray, bouts: np.ndarray, gs: np.ndarray, ge: np.ndarray):
        self.bouts = bouts
        self.n = len(bouts)
        self.offs = np.r_[0, np.cumsum(bouts[:, 1] - bouts[:, 0])].astype(np.int64)
        self.wb = np.concatenate([wb[a:b] for a, b in bouts]) if self.n else np.zeros((0, 3))
        self.acc = np.concatenate([acc[a:b] for a, b in bouts]) if (self.n and acc is not None) else None
        self.gs, self.ge = gs, ge

    def take(self, idx: np.ndarray) -> "BoutSet":
        """Bouts idx (with repeats allowed) as a new set."""
        o = BoutSet.__new__(BoutSet)
        idx = np.asarray(idx, int)
        o.bouts = self.bouts[idx]
        o.n = len(idx)
        lens = self.offs[idx + 1] - self.offs[idx]
        o.offs = np.r_[0, np.cumsum(lens)].astype(np.int64)
        o.wb = np.concatenate([self.wb[self.offs[i]:self.offs[i + 1]] for i in idx]) if o.n else np.zeros((0, 3))
        o.acc = np.concatenate([self.acc[self.offs[i]:self.offs[i + 1]] for i in idx]) if (o.n and self.acc is not None) else None
        o.gs, o.ge = self.gs[idx], self.ge[idx]
        return o


# ====================================================================================================== 0b gyro models
N_PARAMS = {"scalar": 1, "diag": 3, "M": 9, "M_rate": 10, "scalar_gsens": 10, "M_gsens": 18}


def theta0(model: str, cfg: dict) -> np.ndarray:
    e = float(cfg["gyro_fit"]["x0_E_diag"])
    return {"scalar": np.array([e]), "diag": np.full(3, e), "M": (e * np.eye(3)).ravel(),
            "M_rate": np.r_[(e * np.eye(3)).ravel(), 0.0], "scalar_gsens": np.r_[e, np.zeros(9)],
            "M_gsens": np.r_[(e * np.eye(3)).ravel(), np.zeros(9)]}[model]


def theta_to_M(model: str, th: np.ndarray) -> tuple:
    """-> (matrix, c, K)  with K the g-sensitivity matrix ((deg/s) per m/s^2) or None"""
    if model == "scalar":
        return (1.0 + th[0]) * np.eye(3), 0.0, None
    if model == "diag":
        return np.diag(1.0 + th[:3]), 0.0, None
    if model == "M":
        return np.eye(3) + th[:9].reshape(3, 3), 0.0, None
    if model == "M_rate":
        return np.eye(3) + th[:9].reshape(3, 3), float(th[9]), None
    if model == "scalar_gsens":
        return (1.0 + th[0]) * np.eye(3), 0.0, th[1:10].reshape(3, 3)
    return np.eye(3) + th[:9].reshape(3, 3), 0.0, th[9:18].reshape(3, 3)


def apply_model(wb_dps: np.ndarray, Mx: np.ndarray, c: float, cfg: dict, acc: np.ndarray | None = None, K: np.ndarray | None = None) -> np.ndarray:
    """omega (rad/s) = (1 + c |w-b|^2/w0^2) Mx (w-b) + K a   (K = exploratory g-sensitivity, (deg/s)/(m/s^2))."""
    out = wb_dps @ Mx.T
    if c != 0.0:
        w0 = float(cfg["gyro_fit"]["omega0_dps"])
        out = out * (1.0 + c * (np.sum(wb_dps ** 2, axis=1) / w0 ** 2))[:, None]
    if K is not None and acc is not None:
        out = out + acc @ K.T
    return out * D2R


def bout_errors(bs: BoutSet, Mx: np.ndarray, c: float, cfg: dict, K: np.ndarray | None = None) -> tuple:
    """-> (tilt error deg (n,), error vector g_prop - g_end (n,3))"""
    if bs.n == 0:
        return np.zeros(0), np.zeros((0, 3))
    out = np.empty((bs.n, 3))
    propagate_bouts(bs.gs, apply_model(bs.wb, Mx, c, cfg, bs.acc, K), bs.offs, 1.0 / FS100, out)
    return angle_deg(out, bs.ge), out - bs.ge


def fit_model(model: str, bs: BoutSet, cfg: dict, x0: np.ndarray | None = None) -> dict:
    gf = cfg["gyro_fit"]
    f = float(gf["huber_f_deg"]) * D2R
    bE, bc, bK = float(gf["bounds_E"]), float(gf["bounds_c"]), float(gf.get("bounds_K", 1.0))
    npar = N_PARAMS[model]
    nM = 1 if model.startswith("scalar") else (3 if model == "diag" else 9)
    extra = {"M_rate": ([-bc], [bc]), "scalar_gsens": ([-bK] * 9, [bK] * 9), "M_gsens": ([-bK] * 9, [bK] * 9)}.get(model, ([], []))
    lo = np.r_[np.full(nM, -bE), extra[0]]
    hi = np.r_[np.full(nM, bE), extra[1]]

    def res(th):
        Mx, c, K = theta_to_M(model, th)
        return (bout_errors(bs, Mx, c, cfg, K)[1] / f).ravel()

    sol = least_squares(res, theta0(model, cfg) if x0 is None else x0, loss="huber", f_scale=1.0, method="trf", bounds=(lo, hi),
                        x_scale=0.01, ftol=1e-10, xtol=1e-10, gtol=1e-10, max_nfev=600)
    Mx, c, K = theta_to_M(model, sol.x)
    return {"model": model, "theta": sol.x, "M": Mx, "c": c, "K": K, "cost": float(sol.cost), "nfev": int(sol.nfev),
            "ok": bool(sol.success), "n_bouts": bs.n}


def bootstrap_fit(model: str, bs: BoutSet, cfg: dict, x_full: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(int(cfg["gyro_fit"]["seed"]))
    out = []
    for _ in range(int(cfg["gyro_fit"]["n_bootstrap"])):
        out.append(fit_model(model, bs.take(rng.integers(0, bs.n, bs.n)), cfg, x0=x_full)["theta"])
    return np.asarray(out)


# ====================================================================================================== 0a floor
def floor_pairs(acc: np.ndarray, ok_quiet: np.ndarray, L: int) -> np.ndarray:
    """Angles between the mean acc of consecutive non-overlapping L-sample windows inside quiet runs (stride 2L)."""
    ang = []
    for a, b in true_runs(ok_quiet):
        for s in range(a, b - 2 * L + 1, 2 * L):
            ang.append(angle_deg(acc[s:s + L].mean(axis=0), acc[s + L:s + 2 * L].mean(axis=0)))
    return np.asarray(ang, float)


def bridged_floor(acc: np.ndarray, w_rad: np.ndarray, ok_quiet: np.ndarray, L: int, gap: int) -> np.ndarray:
    """Start window -> gyro-propagate through `gap` quiet samples -> compare with the end window (floor + still drift)."""
    ang = []
    for a, b in true_runs(ok_quiet):
        for s in range(a, b - 2 * L - gap + 1, 2 * L + gap):
            g0 = acc[s:s + L].mean(axis=0)
            g0 = g0 / np.linalg.norm(g0)
            out = np.empty((1, 3))
            propagate_bouts(g0[None, :], w_rad[s + L:s + L + gap], np.array([0, gap], np.int64), 1.0 / FS100, out)
            ang.append(angle_deg(out[0], acc[s + L + gap:s + 2 * L + gap].mean(axis=0)))
    return np.asarray(ang, float)


# ====================================================================================================== 0e growth law
def fit_growth(dur: np.ndarray, err: np.ndarray, floor_med: float, floor_n: int, cfg: dict, floor_p90: float = np.nan) -> dict:
    gc = cfg["growth"]
    rf = float(gc["rayleigh_median_factor"])
    edges = np.asarray(gc["bin_edges_s"], float)
    rows = [{"t_lo": 0.0, "t_hi": 0.0, "t_mid": 0.0, "n": int(floor_n), "med": float(floor_med), "p90": float(floor_p90)}]
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (dur >= lo) & (dur < hi)
        if m.sum() >= int(gc["min_bouts_per_bin"]):
            rows.append({"t_lo": lo, "t_hi": hi, "t_mid": float(np.median(dur[m])), "n": int(m.sum()),
                         "med": float(np.median(err[m])), "p90": float(np.percentile(err[m], 90))})
    T = pd.DataFrame(rows)
    t, sig, wgt = T["t_mid"].to_numpy(), T["med"].to_numpy() / rf, np.sqrt(T["n"].to_numpy(float))
    wgt[0] = min(wgt[0], np.sqrt(200.0))

    def fitA(th):
        return wgt * (np.sqrt(th[0] ** 2 + (th[1] * t) ** 2) - sig)

    def fitB(th):
        return wgt * (th[0] + th[1] * t - sig)
    sA = least_squares(fitA, [max(sig[0], 0.05), 0.2], bounds=([0, 0], [50, 50]))
    sB = least_squares(fitB, [max(sig[0], 0.05), 0.2], bounds=([0, 0], [50, 50]))
    ss_tot = float(np.sum((wgt * (sig - np.average(sig, weights=wgt ** 2))) ** 2))
    r2 = lambda s: 1.0 - float(np.sum(s.fun ** 2)) / ss_tot if ss_tot > 0 else np.nan
    m90 = T["p90"].notna().to_numpy()
    t9, p9, w9 = t[m90], T["p90"].to_numpy()[m90], wgt[m90]
    s90 = least_squares(lambda th: w9 * (np.sqrt(th[0] ** 2 + (th[1] * t9) ** 2) - p9), [1.0, 0.5], bounds=([0, 0], [100, 100])) if m90.sum() >= 2 else None
    return {"table": T, "A": {"sigma0_deg": float(sA.x[0]), "k_deg_per_s": float(sA.x[1]), "r2": r2(sA)},
            "B": {"sigma0_deg": float(sB.x[0]), "k_deg_per_s": float(sB.x[1]), "r2": r2(sB)},
            "p90": {"p0_deg": float(s90.x[0]), "k90_deg_per_s": float(s90.x[1])} if s90 is not None else None,
            "rayleigh_median_factor": rf}


def sigma_theta(t_active: np.ndarray, law: dict) -> np.ndarray:
    return np.sqrt(law["sigma0_deg"] ** 2 + (law["k_deg_per_s"] * t_active) ** 2)


# ====================================================================================================== per night
def hf_power_proxy(x_counts: np.ndarray, scale: float) -> float:
    """Mean squared first difference of the raw 1250-Hz signal (sum over 3 lanes): a first-difference high-pass proxy."""
    if x_counts.shape[0] < 3:
        return np.nan
    d = np.diff(x_counts.astype(np.float32), axis=0) * np.float32(scale)
    return float(np.mean(np.sum(d * d, axis=1)))


def process_night(animal: str, night: str, role: str, cfg: dict, fh=None) -> dict:
    """Load caches, run the gyro chain, build the audit bouts + features, floor pairs and per-second raw counts."""
    t0 = time.time()
    nt = load_night(animal, night, cfg)
    ch = gyro_chain(nt, cfg, do_recon=True)
    t100, acc, quiet, frz, satg = nt["t100"], nt["acc100"], nt["quiet"], nt["frozen100"], nt["sat_gyr100"]
    n100 = len(t100)
    wb_a3 = nt["gyr_a3"] / float(cfg["audit_reference"]["baseline_gyro_scale"])
    # bias exactly as A3 applied it: b = w_lp - (gyr_A3 / 1.03) holds at every sample because the no-recon chain is A3's chain;
    # the 1-min nodes are only a sampled copy of that running median (their interpolation error is reported as bias_node_err)
    bias_exact = ch["w100_norecon"] - wb_a3
    okm = ~(satg | frz)
    bias_node_err = float(np.nanmax(np.abs(bias_exact[okm] - nt["bias100"][okm]))) if okm.any() else np.nan
    chain_check = float(np.nanmedian(np.abs(bias_exact[okm] - nt["bias100"][okm]))) if okm.any() else np.nan
    wb = ch["w100"] - bias_exact
    wb_nr = ch["w100_norecon"] - bias_exact
    e = int(cfg["bouts"]["edge_window_s"] * FS100)
    bouts = make_bouts(quiet, cfg)
    gs, ge = edge_gravity(acc, bouts, e)
    six, sat_raw = nt["six"], nt["sat_raw"]
    R = ch["sat_runs"]
    rows = []
    for i, (a, b) in enumerate(bouts):
        ra, rb = int(round(12.5 * a)), int(round(12.5 * b))
        sg = bool(sat_raw[ra:rb, 3:6].any())
        rec = {"animal": animal, "night": night, "role": role, "i0": int(a), "i1": int(b), "t0_unix_ms": float(t100[a]),
               "t0_s": float((t100[a] - t100[0]) / 1000.0), "dur_s": (b - a) / FS100, "sat_gyr": sg,
               "sat_acc": bool(sat_raw[ra:rb, :3].any()), "frozen": bool(frz[a:b].any()),
               "edge_ok": bool(not (frz[a - e:a].any() or frz[b:b + e].any() or satg[a - e:a].any() or satg[b:b + e].any())),
               "acc_dev": float(np.median(np.abs(np.linalg.norm(acc[a:b], axis=1) - G))),
               "edge_rot_deg": float((np.linalg.norm(wb[a - e:a], axis=1).sum() + np.linalg.norm(wb[b:b + e], axis=1).sum()) / FS100),
               "hf_gyr": hf_power_proxy(six[ra:rb, 3:6], GYR_SCALE), "hf_acc": hf_power_proxy(six[ra:rb, :3], ACC_SCALE),
               "n_shake": 0, "n_recon": 0, "n_suspect": 0, "n_impact": 0, "n_short": 0, "n_rotation": 0, "missing_deg": 0.0}
        if sg and len(R):
            inb = R[(R["i0"] >= ra) & (R["i0"] < rb)]
            vc = inb["cls"].value_counts()
            rec.update({"n_shake": int(vc.get("shake_train", 0)), "n_suspect": int(vc.get("suspect_monotone", 0)),
                        "n_impact": int(vc.get("impact", 0)), "n_short": int(vc.get("short_broadband", 0)),
                        "n_rotation": int(vc.get("rotation", 0)), "n_recon": int(inb["recon"].sum()),
                        "missing_deg": float(inb["missing_deg"].sum())})
        rows.append(rec)
    bt = pd.DataFrame(rows)
    # per-second raw counts (saturation, unclipped max rate)
    sec_raw = np.minimum((np.arange(six.shape[0]) // 1250), int(np.ceil(n100 / FS100)) - 1)
    nsec = int(sec_raw.max()) + 1 if six.shape[0] else 0
    n_sat_g = np.bincount(sec_raw, weights=ch["sat_gyr_raw"].astype(np.float64), minlength=nsec)
    n_sat_a = np.bincount(sec_raw, weights=sat_raw[:, :3].any(axis=1).astype(np.float64), minlength=nsec)
    wr = np.where(ch["sat_gyr_raw"], 0.0, ch["w_raw_norm"]).astype(np.float64)
    wmax_unclipped = np.zeros(nsec)
    np.maximum.at(wmax_unclipped, sec_raw, wr)
    per_sec = {"n_sat_gyr": n_sat_g.astype(int), "n_sat_acc": n_sat_a.astype(int), "wmax_raw_unclipped_dps": wmax_unclipped}
    if len(R):
        R = R.assign(animal=animal, night=night, role=role)
    log(f"{animal} {night}: n100 {n100}, quiet {quiet.mean():.3f}, bouts {len(bouts)} (sat {int(bt['sat_gyr'].sum()) if len(bt) else 0}), "
        f"sat runs {len(R)}, bias-node interpolation error median {chain_check:.2e} / max {bias_node_err:.2e} deg/s, {time.time() - t0:.1f} s", fh)
    return {"animal": animal, "night": night, "role": role, "t100": t100, "acc": acc.astype(np.float32), "wb": wb.astype(np.float32),
            "wb_nr": wb_nr.astype(np.float32), "wb_a3": wb_a3.astype(np.float32), "quiet": quiet, "frozen": frz, "sat_gyr100": satg,
            "shake100": ch["shake100"], "recon100": ch["recon100"], "bouts": bouts, "gs": gs, "ge": ge, "bt": bt, "sat_runs": R,
            "per_sec": per_sec, "chain_check": chain_check, "bias_node_err": bias_node_err, "cal": nt["cal"], "meta3": nt["meta3"], "meta1": nt["meta1"],
            "a1_path": nt["a1_path"], "a3_path": nt["a3_path"], "a1_bytes": nt["a1_bytes"], "a3_bytes": nt["a3_bytes"],
            "sat_frac_gyr_raw": float(ch["sat_gyr_raw"].mean())}


def boutsets(nd: dict) -> dict:
    return {"recon": BoutSet(nd["wb"].astype(np.float64), nd["acc"].astype(np.float64), nd["bouts"], nd["gs"], nd["ge"]),
            "norecon": BoutSet(nd["wb_nr"].astype(np.float64), None, nd["bouts"], nd["gs"], nd["ge"]),
            "a3": BoutSet(nd["wb_a3"].astype(np.float64), None, nd["bouts"], nd["gs"], nd["ge"])}


def bin_label(dur: np.ndarray, cfg: dict) -> pd.Series:
    bc = cfg["bouts"]
    return pd.cut(dur, bc["bins_s"], labels=bc["bin_labels"], include_lowest=True)


def fit_stage(tun: dict, cfg: dict, fh=None) -> dict:
    """0b on the tuning nights: per animal CV of every model, full fits; pooled model selection; bootstrap of the selected."""
    gf = cfg["gyro_fit"]
    lo, hi = gf["fit_bout_range_s"]
    models = list(gf["models"]) + list(gf.get("exploratory_models", []))
    registered = list(gf["models"])
    cv_err = {m: [] for m in models}
    fits = {}
    per_animal_cv = []
    for animal, nd in tun.items():
        bs_all = boutsets(nd)["recon"]
        bt = nd["bt"]
        fitm = ((bt["dur_s"] >= lo) & (bt["dur_s"] <= hi) & ~bt["sat_gyr"] & ~bt["frozen"] & bt["edge_ok"]).to_numpy()
        bs = bs_all.take(np.flatnonzero(fitm))
        folds = (np.floor(bt["t0_s"].to_numpy()[fitm] / float(gf["cv_block_s"])).astype(int) % 2)
        fits[animal] = {}
        for m in models:
            held = np.full(bs.n, np.nan)
            for f in (0, 1):
                tr, te = np.flatnonzero(folds != f), np.flatnonzero(folds == f)
                if len(tr) < 20 or len(te) == 0:
                    continue
                r = fit_model(m, bs.take(tr), cfg)
                held[te] = bout_errors(bs.take(te), r["M"], r["c"], cfg, r["K"])[0]
            cv_err[m].append(held)
            full = fit_model(m, bs, cfg)
            full["cv_median"] = float(np.nanmedian(held)) if np.isfinite(held).any() else np.nan
            full["train_median"] = float(np.median(bout_errors(bs, full["M"], full["c"], cfg, full["K"])[0]))
            fits[animal][m] = full
            per_animal_cv.append({"animal": animal, "model": m, "n_fit_bouts": bs.n, "cv_median_deg": full["cv_median"],
                                  "train_median_deg": full["train_median"], "cost": full["cost"], "nfev": full["nfev"], "ok": full["ok"]})
        base = bout_errors(bs, float(cfg["audit_reference"]["baseline_gyro_scale"]) * np.eye(3), 0.0, cfg)[0]
        per_animal_cv.append({"animal": animal, "model": "baseline_1.03", "n_fit_bouts": bs.n, "cv_median_deg": float(np.median(base)),
                              "train_median_deg": float(np.median(base)), "cost": np.nan, "nfev": 0, "ok": True})
        log(f"  fit {animal}: n={bs.n}  " + "  ".join(f"{m}: cv {fits[animal][m]['cv_median']:.3f} / train {fits[animal][m]['train_median']:.3f}" for m in models)
            + f"  baseline {np.median(base):.3f}", fh)
    pooled = {m: float(np.nanmedian(np.concatenate(cv_err[m]))) for m in models}
    order = sorted(registered, key=lambda m: pooled[m])          # selection among the pre-registered models only
    best = order[0]
    # tie rule: within cv_tie_deg of the best -> the simpler (fewer parameters)
    cands = [m for m in registered if pooled[m] <= pooled[best] + float(gf["cv_tie_deg"])]
    selected = min(cands, key=lambda m: N_PARAMS[m])
    log(f"  pooled CV medians: {pooled}  -> selected {selected}", fh)
    boot = {}
    for animal, nd in tun.items():
        bs_all = boutsets(nd)["recon"]
        bt = nd["bt"]
        fitm = ((bt["dur_s"] >= lo) & (bt["dur_s"] <= hi) & ~bt["sat_gyr"] & ~bt["frozen"] & bt["edge_ok"]).to_numpy()
        bs = bs_all.take(np.flatnonzero(fitm))
        tb = time.time()
        th = bootstrap_fit(selected, bs, cfg, fits[animal][selected]["theta"])
        boot[animal] = {"theta": th, "lo": np.percentile(th, 2.5, axis=0), "hi": np.percentile(th, 97.5, axis=0)}
        log(f"  bootstrap {animal} ({selected}, {len(th)} draws): {time.time() - tb:.0f} s", fh)
    return {"fits": fits, "pooled_cv": pooled, "selected": selected, "boot": boot, "cv_table": pd.DataFrame(per_animal_cv)}


def eval_night(nd: dict, fits_animal: dict, selected: str, cfg: dict) -> pd.DataFrame:
    """Per-bout tilt errors of the baseline and every model on one night (recon chain), plus treatments (i)-(iii) and stats."""
    bss = boutsets(nd)
    bt = nd["bt"].copy()
    s0 = float(cfg["audit_reference"]["baseline_gyro_scale"])
    e_base, _ = bout_errors(bss["a3"], s0 * np.eye(3), 0.0, cfg)
    bt["e_baseline"] = e_base
    for m, r in fits_animal.items():
        e, ev = bout_errors(bss["recon"], r["M"], r["c"], cfg, r.get("K"))
        bt[f"e_{m}"] = e
        if m == selected:
            bt["e_cal"] = e
            bt["ex"], bt["ey"], bt["ez"] = ev[:, 0], ev[:, 1], ev[:, 2]
            bt["e_cal_norecon"] = bout_errors(bss["norecon"], r["M"], r["c"], cfg)[0]
            # (iii) recon + attitude frozen across shake-train spans
            wz = nd["wb"].astype(np.float64).copy()
            wz[nd["shake100"]] = 0.0
            bt["e_cal_shakefrozen"] = bout_errors(BoutSet(wz, None, nd["bouts"], nd["gs"], nd["ge"]), r["M"], r["c"], cfg)[0]
            st = np.empty((bss["recon"].n, 3))
            bout_stats(bss["recon"].gs, apply_model(bss["recon"].wb, r["M"], r["c"], cfg), bss["recon"].acc, bss["recon"].offs, 1.0 / FS100, st)
            bt["rot_deg"], bt["mean_ah"], bt["wmax_dps"] = st[:, 0], st[:, 1], st[:, 2]
    bt["dbin"] = bin_label(bt["dur_s"].to_numpy(), cfg).astype(str)
    return bt


def floor_tables(nights: dict, sel_fits: dict, cfg: dict) -> pd.DataFrame:
    rows = []
    for key, nd in nights.items():
        okq = nd["quiet"] & ~nd["frozen"] & ~nd["sat_gyr100"]
        acc = nd["acc"].astype(np.float64)
        for Ls in cfg["floor"]["window_s"]:
            ang = floor_pairs(acc, okq, int(Ls * FS100))
            rows.append({"animal": nd["animal"], "night": nd["night"], "role": nd["role"], "kind": "adjacent", "L_s": Ls, "gap_s": 0.0,
                         "n": len(ang), "median_deg": float(np.median(ang)) if len(ang) else np.nan,
                         "p90_deg": float(np.percentile(ang, 90)) if len(ang) else np.nan})
        r = sel_fits[nd["animal"]]
        w_rad = apply_model(nd["wb"].astype(np.float64), r["M"], r["c"], cfg)
        L = int(cfg["floor"]["gate_window_s"] * FS100)
        for gs_ in cfg["floor"]["bridged_gap_s"]:
            ang = bridged_floor(acc, w_rad, okq, L, int(gs_ * FS100))
            rows.append({"animal": nd["animal"], "night": nd["night"], "role": nd["role"], "kind": "bridged", "L_s": cfg["floor"]["gate_window_s"],
                         "gap_s": gs_, "n": len(ang), "median_deg": float(np.median(ang)) if len(ang) else np.nan,
                         "p90_deg": float(np.percentile(ang, 90)) if len(ang) else np.nan})
    return pd.DataFrame(rows)


def floor_pooled(nights: dict, cfg: dict, role: str, Ls: float) -> tuple:
    """Pooled floor angles (all animals of a role) for window Ls."""
    allang = []
    for nd in nights.values():
        if nd["role"] != role:
            continue
        okq = nd["quiet"] & ~nd["frozen"] & ~nd["sat_gyr100"]
        allang.append(floor_pairs(nd["acc"].astype(np.float64), okq, int(Ls * FS100)))
    a = np.concatenate(allang) if allang else np.zeros(0)
    return a, (float(np.median(a)) if len(a) else np.nan)


def per_second_table(nd: dict, r: dict, cfg: dict) -> pd.DataFrame:
    """Per second: saturation counts, calibrated max |w| (100 Hz), unclipped raw max, quiet fraction, sat-run classes."""
    t100, wb = nd["t100"], nd["wb"].astype(np.float64)
    w_cal = np.linalg.norm(apply_model(wb, r["M"], r["c"], cfg), axis=1) * R2D
    sec = ((t100 - t100[0]) // 1000).astype(int)
    nsec = int(sec.max()) + 1
    wmax = np.zeros(nsec)
    np.maximum.at(wmax, sec, w_cal)
    qf = np.bincount(sec, weights=nd["quiet"].astype(float), minlength=nsec) / np.maximum(np.bincount(sec, minlength=nsec), 1)
    ps = nd["per_sec"]
    m = min(nsec, len(ps["n_sat_gyr"]))
    T = pd.DataFrame({"animal": nd["animal"], "night": nd["night"], "sec": np.arange(m), "t_unix_ms": t100[0] + 1000.0 * np.arange(m),
                      "quiet_frac": qf[:m], "wmax_cal_dps": wmax[:m], "wmax_raw_unclipped_dps": ps["wmax_raw_unclipped_dps"][:m],
                      "n_sat_gyr": ps["n_sat_gyr"][:m], "n_sat_acc": ps["n_sat_acc"][:m]})
    for c in CLASSES:
        T[f"n_{c}"] = 0
    R = nd["sat_runs"]
    if len(R):
        rs = ((R["t_unix_ms"].to_numpy() - t100[0]) // 1000).astype(int)
        for c in CLASSES:
            cnt = np.bincount(rs[(R["cls"] == c).to_numpy() & (rs >= 0) & (rs < m)], minlength=m)[:m]
            T[f"n_{c}"] = cnt
    return T


def _frac_active_sec_sat(nd: dict) -> float:
    t100 = nd["t100"]
    sec = ((t100 - t100[0]) // 1000).astype(int)
    nsec = int(sec.max()) + 1
    qf = np.bincount(sec, weights=nd["quiet"].astype(float), minlength=nsec) / np.maximum(np.bincount(sec, minlength=nsec), 1)
    m = min(nsec, len(nd["per_sec"]["n_sat_gyr"]))
    act = qf[:m] < 0.5
    return float(np.mean(nd["per_sec"]["n_sat_gyr"][:m][act] > 0)) if act.any() else np.nan


def omega_distribution(nd: dict, r: dict, cfg: dict) -> dict:
    """Per-sample |w| (100 Hz, calibrated) percentiles in active vs quiet seconds; unclipped raw max; per-second wmax percentiles."""
    w_cal = np.linalg.norm(apply_model(nd["wb"].astype(np.float64), r["M"], r["c"], cfg), axis=1) * R2D
    ok = ~nd["frozen"]
    act, qui = ok & ~nd["quiet"], ok & nd["quiet"]
    pct = (50, 90, 99, 99.9, 99.99)
    return {"animal": nd["animal"], "night": nd["night"], "role": nd["role"],
            **{f"active_p{str(p).replace('.', '_')}": float(np.percentile(w_cal[act], p)) for p in pct}, "active_max": float(w_cal[act].max()),
            "active_sd": float(w_cal[act].std()), **{f"quiet_p{p}": float(np.percentile(w_cal[qui], p)) for p in (50, 90, 99)},
            "quiet_max": float(w_cal[qui].max()), "unclipped_raw_max_dps": float(nd["per_sec"]["wmax_raw_unclipped_dps"].max()),
            "frac_active_sec_with_sat": _frac_active_sec_sat(nd),
            "sat_frac_gyr_raw": nd["sat_frac_gyr_raw"]}


# ====================================================================================================== 0d A4 cache
def any_in_support(flag100: np.ndarray, centers: np.ndarray, half: float) -> np.ndarray:
    cs = np.r_[0, np.cumsum(flag100.astype(np.int64))]
    lo = np.clip(np.round(centers - half).astype(int), 0, len(flag100))
    hi = np.clip(np.round(centers + half).astype(int), 0, len(flag100))
    return (cs[hi] - cs[lo]) > 0


def build_a4(nd: dict, r: dict, law: dict, law90: dict | None, cfg: dict, out_root: Path, run_dir: Path, fh=None) -> dict:
    ac = cfg["attitude"]
    t100, acc, wb = nd["t100"], nd["acc"].astype(np.float64), nd["wb"].astype(np.float64)
    n100 = len(t100)
    w_rad = apply_model(wb, r["M"], r["c"], cfg)
    quiet, invalid = nd["quiet"], nd["frozen"]
    dt = 1.0 / FS100
    gain = dt / float(ac["tau_quiet_s"])
    i0 = int(np.flatnonzero(quiet)[0]) if quiet.any() else 0
    q0 = q_from_up(acc[i0:i0 + 100].mean(axis=0))
    q = np.empty((n100, 4))
    ta = np.empty(n100)
    integrate_attitude(w_rad, acc, quiet, invalid, dt, gain, q0, q, ta)
    f_w = rotate_world(q, acc)
    f_w[:, 2] -= G
    # 16-Hz grid: resample_poly(4, 25) output j <-> input 6.25 j
    n16 = int(math.ceil(n100 * 4 / 25))
    centers = 6.25 * np.arange(n16)
    t16 = np.interp(centers, np.arange(n100), t100)
    near = np.clip(np.round(centers).astype(int), 0, n100 - 1)
    arrays = {"t_unix_ms": t16}
    for fc in ac["fxy_cutoffs_hz"]:
        sos = signal.butter(4, float(fc), fs=FS100, output="sos")
        lp = signal.sosfiltfilt(sos, f_w, axis=0)
        d = signal.resample_poly(lp, 4, 25, axis=0)[:n16]
        tag = f"{int(fc)}hz"
        arrays[f"f_xy_{tag}"] = d[:, :2].astype(np.float32)
        if float(fc) == float(ac["fxy_main_hz"]):
            arrays[f"f_z_{tag}"] = d[:, 2].astype(np.float32)
    arrays["q_wh"] = q[near].astype(np.float32)
    arrays["t_active_s"] = ta[near].astype(np.float32)
    arrays["sigma_theta_deg"] = sigma_theta(ta[near], law).astype(np.float32)
    if law90 is not None:
        arrays["p90_theta_deg"] = np.sqrt(law90["p0_deg"] ** 2 + (law90["k90_deg_per_s"] * ta[near]) ** 2).astype(np.float32)
    half = 3.125
    arrays["still"] = any_in_support(quiet, centers, half) & ~any_in_support(~quiet, centers, half)
    arrays["dyn"] = ~arrays["still"]
    arrays["sat"] = any_in_support(nd["sat_gyr100"], centers, half)
    arrays["recon"] = any_in_support(nd["recon100"], centers, half)
    arrays["shake"] = any_in_support(nd["shake100"], centers, half)
    arrays["frozen"] = any_in_support(invalid, centers, half)
    arrays["invalid"] = arrays["frozen"]
    # behaviour-band powers of |w| (deg/s) and |a| (m/s^2): band-pass -> square -> centred 0.5-s mean -> 16-Hz grid
    from scipy.ndimage import uniform_filter1d
    wn = np.linalg.norm(w_rad, axis=1) * R2D
    an = np.linalg.norm(acc, axis=1)
    win = int(round(float(ac["band_power_window_s"]) * FS100))
    for lo_, hi_ in ac["band_powers_hz"]:
        sos = signal.butter(4, [float(lo_), float(hi_)], btype="bandpass", fs=FS100, output="sos")
        for nm, x in (("w", wn), ("a", an)):
            bp = signal.sosfiltfilt(sos, x)
            arrays[f"bp_{nm}_{int(lo_)}_{int(hi_)}"] = uniform_filter1d(bp * bp, win, mode="nearest")[near].astype(np.float32)
    tilt_check = float(np.median(angle_deg(np.stack([_g_head(tuple(qq)) for qq in q[quiet][::50]]), acc[quiet][::50]))) if quiet.any() else np.nan
    calib = {"gyro_model": r["model"], "M": r["M"].tolist(), "c": r["c"], "omega0_dps": cfg["gyro_fit"]["omega0_dps"],
             "gyro_bias": "A3 running-median 1-min nodes (calib_json.bias_nodes_1min), linear interpolation",
             "acc": nd["cal"]["acc"], "chain": cfg["chain"], "saturation": cfg["saturation"], "attitude": ac,
             "growth_law_sigma": law, "growth_law_p90": law90, "fitted_on": "M: tuning night 2026-09-08/09; growth law: test night 2026-09-10/11",
             "axis_map_S": S.tolist(), "quat_convention": "[w, x, y, z], v_world = R(q) v_head; yaw arbitrary (0 at night start), continuous, uncorrected",
             "sigma_theta": "per-axis SD of the 2-D tilt error (deg) at the sample's t_active; median tilt angle = 1.1774 sigma"}
    meta = {"animal": nd["animal"], "night": nd["night"], "role": nd["role"], "source_a1": str(nd["a1_path"]), "source_a3": str(nd["a3_path"]),
            "t_clock": "field-PC Unix ms on the IMU clock (tau* NOT applied); 16-Hz grid j <-> 100-Hz sample 6.25 j",
            "units": {"f_xy": "m/s^2 world frame (yaw arbitrary), gravity removed", "bp_w": "(deg/s)^2", "bp_a": "(m/s^2)^2"},
            "quiet_tilt_check_median_deg": tilt_check, "git_commit": EC.git_commit(), "run_dir": str(run_dir),
            "written_local": pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds"), "writer": "wiser/scripts/analyze_imu_attitude_phase0.py"}
    od = out_root / nd["animal"]
    od.mkdir(parents=True, exist_ok=True)
    p = od / f"{nd['night']}.npz"
    np.savez_compressed(p, calib_json=np.array(json.dumps(calib, default=_jd)), meta_json=np.array(json.dumps(meta, default=_jd)), **arrays)
    log(f"  A4 {nd['animal']} {nd['night']}: {n16} samples, quiet tilt check {tilt_check:.2f} deg, {p.stat().st_size / 1e6:.1f} MB", fh)
    return {"path": str(p), "bytes": p.stat().st_size, "n16": n16, "quiet_tilt_check_deg": tilt_check}


# ====================================================================================================== evaluation
def gate_mask(bt: pd.DataFrame) -> np.ndarray:
    return ((bt["role"] == "test") & ~bt["sat_gyr"] & ~bt["frozen"] & bt["edge_ok"]).to_numpy()


def bin_table(bt: pd.DataFrame, cols: list, cfg: dict) -> pd.DataFrame:
    """median / p90 / n per (animal | pooled) x dbin for the given error columns."""
    rows = []
    groups = [(a, g) for a, g in bt.groupby("animal")] + [("pooled", bt)]
    for a, g in groups:
        for lab in cfg["bouts"]["bin_labels"]:
            gb = g[g["dbin"] == lab]
            rec = {"animal": a, "dbin": lab, "n": len(gb)}
            for c in cols:
                rec[f"{c}_med"] = float(gb[c].median()) if len(gb) else np.nan
                rec[f"{c}_p90"] = float(gb[c].quantile(0.9)) if len(gb) else np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


def evaluate_gate(bt: pd.DataFrame, floor_med: float, cfg: dict, rng_seed: int = 1) -> dict:
    gc = cfg["gate"]
    g = bt[gate_mask(bt)]
    res = {"bins": {}, "animals": {}, "floor_median_deg": floor_med, "n_bouts": int(len(g))}
    rng = np.random.default_rng(rng_seed)
    all_pass = True
    for lab, thr in gc["bins"].items():
        e = g.loc[g["dbin"] == lab, "e_cal"].to_numpy()
        med = float(np.median(e)) if len(e) else np.nan
        bs = np.array([np.median(rng.choice(e, len(e))) for _ in range(1000)]) if len(e) > 5 else np.array([np.nan])
        eb = g.loc[g["dbin"] == lab, "e_baseline"].to_numpy()
        res["bins"][lab] = {"threshold_deg": thr, "pooled_median_deg": med, "ci95": [float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))],
                            "n": int(len(e)), "pooled_pass": bool(med <= thr) if len(e) else False, "baseline_median_deg": float(np.median(eb)) if len(eb) else np.nan,
                            "excess_over_floor_deg": med - floor_med if len(e) else np.nan,
                            "within_floor_excess": bool((med - floor_med) < float(gc["floor_excess_deg"])) if len(e) else False}
        all_pass &= res["bins"][lab]["pooled_pass"]
    n_ind = 0
    for a, ga in g.groupby("animal"):
        ok = True
        rec = {}
        for lab, thr in gc["bins"].items():
            e = ga.loc[ga["dbin"] == lab, "e_cal"].to_numpy()
            med = float(np.median(e)) if len(e) else np.nan
            rec[lab] = {"median_deg": med, "n": int(len(e)), "pass": bool(med <= thr) if len(e) else False}
            ok &= rec[lab]["pass"]
        rec["pass_both"] = bool(ok)
        n_ind += int(ok)
        res["animals"][a] = rec
    res["n_animals_pass"] = n_ind
    res["n_animals"] = int(g["animal"].nunique())
    res["verdict"] = "PASS" if (all_pass and n_ind >= int(gc["min_animals_pass"])) else "FAIL"
    # post-hoc diagnostic (not the gate): the same numbers on bouts whose two 0.5-s edge windows are still (integrated |w| < thr)
    res["posthoc_edge_still"] = {}
    if "edge_rot_deg" in g.columns:
        res["spearman_e_edge_rot"] = float(spearmanr(g["edge_rot_deg"], g["e_cal"])[0]) if len(g) > 10 else np.nan
        res["edge_rot_median_deg"] = float(g["edge_rot_deg"].median())
        for thr_e in (2.0, 1.0):
            ge_ = g[g["edge_rot_deg"] < thr_e]
            d = {"n": int(len(ge_)), "bins": {}, "animals_pass_both": 0}
            for lab, thr in gc["bins"].items():
                e = ge_.loc[ge_["dbin"] == lab, "e_cal"].to_numpy()
                eb = ge_.loc[ge_["dbin"] == lab, "e_baseline"].to_numpy()
                d["bins"][lab] = {"pooled_median_deg": float(np.median(e)) if len(e) else np.nan, "n": int(len(e)),
                                  "baseline_median_deg": float(np.median(eb)) if len(eb) else np.nan,
                                  "per_animal_median_deg": {a: float(np.median(x)) for a, x in ge_[ge_["dbin"] == lab].groupby("animal")["e_cal"]}}
            for a, ga in ge_.groupby("animal"):
                ok = all((np.median(ga.loc[ga["dbin"] == lab, "e_cal"]) <= thr) if (ga["dbin"] == lab).sum() >= 5 else False for lab, thr in gc["bins"].items())
                d["animals_pass_both"] += int(ok)
            d["rot_deg_median"] = float(ge_["rot_deg"].median()) if len(ge_) else np.nan
            res["posthoc_edge_still"][f"edge_rot_lt_{thr_e:g}deg"] = d
        # matched-activity comparison: within rotation bins, split at the bin's median edge motion
        rows = []
        gg_all = g.assign(rbin=pd.cut(g["rot_deg"], [0, 50, 100, 200, 400, 800, 1e9]).astype(str))
        for rb, gg in gg_all.groupby("rbin"):
            if len(gg) < 12:
                continue
            med = gg["edge_rot_deg"].median()
            lo_, hi_ = gg[gg["edge_rot_deg"] < med], gg[gg["edge_rot_deg"] >= med]
            rows.append({"rot_bin_deg": rb, "n": int(len(gg)), "edge_rot_median_deg": float(med), "e_low_edge_median": float(lo_["e_cal"].median()),
                         "e_high_edge_median": float(hi_["e_cal"].median()), "spearman_edge_e_within": float(spearmanr(gg["edge_rot_deg"], gg["e_cal"])[0]),
                         "rot_low_median": float(lo_["rot_deg"].median()), "rot_high_median": float(hi_["rot_deg"].median())})
        res["posthoc_matched"] = rows
        X = np.column_stack([np.log(g["rot_deg"] + 1), np.log(g["edge_rot_deg"] + 0.1), np.log(g["dur_s"]), np.ones(len(g))])
        beta = np.linalg.lstsq(X, np.log(g["e_cal"] + 0.01), rcond=None)[0]
        res["posthoc_loglog"] = {"exp_rot": float(beta[0]), "exp_edge": float(beta[1]), "exp_dur": float(beta[2])}
        tert = []
        g2 = g.assign(etert=pd.qcut(g["edge_rot_deg"], 3, labels=["low", "mid", "high"]).astype(str))
        for (lab, te), gg in g2.groupby(["dbin", "etert"]):
            if lab in gc["bins"]:
                tert.append({"dbin": lab, "edge_tertile": te, "n": int(len(gg)), "e_median": float(gg["e_cal"].median()), "e_baseline_median": float(gg["e_baseline"].median()),
                             "rot_median": float(gg["rot_deg"].median()), "edge_rot_median": float(gg["edge_rot_deg"].median())})
        res["posthoc_tertiles"] = tert
    return res


def drift_scaling(g: pd.DataFrame) -> dict:
    """Audit's scaling diagnostics on calibrated no-sat test bouts + the rectification correlations."""
    if len(g) < 10:
        return {"n": int(len(g))}
    e, dur, rot = g["e_cal"].to_numpy(), g["dur_s"].to_numpy(), g["rot_deg"].to_numpy()
    rate = e / dur
    E = g[["ex", "ey", "ez"]].to_numpy()
    mv = E.mean(axis=0)
    sp = lambda x, y: float(spearmanr(x, y)[0])
    return {"n": int(len(g)), "spearman_e_dur": sp(e, dur), "spearman_e_rot": sp(e, rot), "spearman_dur_rot": sp(dur, rot),
            "deg_per_100deg_median": float(np.median(e / np.maximum(rot, 1e-6) * 100)), "deg_per_100deg_p90": float(np.percentile(e / np.maximum(rot, 1e-6) * 100, 90)),
            "deg_per_s_median": float(np.median(rate)), "deg_per_s_p90": float(np.percentile(rate, 90)),
            "error_vector_consistency": float(np.linalg.norm(mv) / np.mean(np.linalg.norm(E, axis=1))),
            "mean_error_dir_head": (mv / max(np.linalg.norm(mv), 1e-12)).round(2).tolist(),
            "spearman_rate_hf_gyr": sp(rate, g["hf_gyr"]), "spearman_rate_hf_acc": sp(rate, g["hf_acc"]),
            "spearman_rate_mean_ah": sp(rate, g["mean_ah"]), "spearman_rate_acc_dev": sp(rate, g["acc_dev"]),
            "spearman_e_hf_gyr": sp(e, g["hf_gyr"]), "spearman_e_mean_ah": sp(e, g["mean_ah"]), "spearman_e_wmax": sp(e, g["wmax_dps"])}


def saturation_summary(sat_all: pd.DataFrame, bt_all: pd.DataFrame, cfg: dict) -> dict:
    out = {}
    if len(sat_all):
        cnt = sat_all.groupby(["night", "animal", "cls"]).size().unstack(fill_value=0)
        for c in CLASSES:
            if c not in cnt.columns:
                cnt[c] = 0
        out["class_counts"] = cnt[CLASSES].reset_index()
        out["per_lane"] = sat_all.groupby(["lane"]).size().to_dict()
        edges = np.asarray(cfg["saturation"]["spacing_hist_ms"], float)
        gp = sat_all["gap_prev_ms"].dropna().to_numpy()
        out["spacing_hist"] = {"edges_ms": edges[:-1].tolist() + ["inf"], "counts": np.histogram(gp, edges)[0].tolist(), "n": int(len(gp))}
        out["dur_ms"] = {k: float(v) for k, v in sat_all["dur_ms"].describe(percentiles=[0.5, 0.9, 0.99]).items()}
        out["acc_max_g_by_class"] = sat_all.groupby("cls")["acc_max_g"].median().to_dict()
        out["acc_hf_frac_by_class"] = sat_all.groupby("cls")["acc_hf_frac"].median().to_dict()
        out["recon"] = {"n_recon": int(sat_all["recon"].sum()), "n_failed": int(sat_all["recon_failed"].sum()),
                        "missing_deg_median": float(sat_all.loc[sat_all["recon"], "missing_deg"].median()) if sat_all["recon"].any() else np.nan,
                        "missing_deg_p90": float(sat_all.loc[sat_all["recon"], "missing_deg"].quantile(0.9)) if sat_all["recon"].any() else np.nan,
                        "peak_dps_median": float(sat_all.loc[sat_all["recon"], "peak_dps"].median()) if sat_all["recon"].any() else np.nan,
                        "peak_dps_p90": float(sat_all.loc[sat_all["recon"], "peak_dps"].quantile(0.9)) if sat_all["recon"].any() else np.nan}
        sh = sat_all[sat_all["cls"] == "shake_train"].drop_duplicates("train_id")
        out["shake_trains"] = {"n_trains": int(len(sh)), "size_median": float(sh["train_size"].median()) if len(sh) else np.nan,
                               "net_deg_abs_median": float(sh["train_net_deg"].abs().median()) if len(sh) else np.nan,
                               "net_deg_abs_p90": float(sh["train_net_deg"].abs().quantile(0.9)) if len(sh) else np.nan,
                               "frac_acc_gt_2g": float(sh["acc_gt_2g"].mean()) if len(sh) else np.nan}
        su = sat_all[sat_all["cls"] == "suspect_monotone"]
        out["suspect"] = {"n": int(len(su)), "net_deg_abs_median": float(su["net_deg_pm25ms"].abs().median()) if len(su) else np.nan,
                          "by_animal": su.groupby("animal").size().to_dict()}
    sb = bt_all[bt_all["sat_gyr"] & bt_all["edge_ok"]].copy()
    if len(sb):
        sb["contains"] = np.where(sb["n_shake"] > 0, "shake", np.where(sb["n_suspect"] > 0, "suspect", np.where(sb["n_impact"] > 0, "impact", "rotation_only")))
        cols = ["e_baseline", "e_cal_norecon", "e_cal", "e_cal_shakefrozen"]
        rows = [{"contains": "all", "n": len(sb), **{c: float(sb[c].median()) for c in cols}}]
        for k, gk in sb.groupby("contains"):
            rows.append({"contains": k, "n": len(gk), **{c: float(gk[c].median()) for c in cols}})
        out["sat_bouts"] = pd.DataFrame(rows)
        out["sat_bouts_table"] = sb
    return out


def run_analysis(cfg: dict, out: Path, animals: list, do_a4: bool, fh=None) -> dict:
    t_start = time.time()
    tn, sn = cfg["nights"]["tuning"], cfg["nights"]["test"]
    tun = {a: process_night(a, tn, "tuning", cfg, fh) for a in animals}
    fs = fit_stage(tun, cfg, fh)
    sel = fs["selected"]
    sel_fits = {a: fs["fits"][a][sel] for a in animals}
    tst = {a: process_night(a, sn, "test", cfg, fh) for a in animals}
    nights = {**{("tuning", a): tun[a] for a in animals}, **{("test", a): tst[a] for a in animals}}
    bt_all = pd.concat([eval_night(nd, fs["fits"][nd["animal"]], sel, cfg) for nd in nights.values()], ignore_index=True)
    bt_all.to_csv(out / "bouts_all.csv", index=False)
    # floors
    fl = floor_tables(nights, sel_fits, cfg)
    fl.to_csv(out / "floor.csv", index=False)
    floor_ang, floor_med = floor_pooled(nights, cfg, "test", float(cfg["floor"]["gate_window_s"]))
    floor_pool = {f"L{Ls}": {"median_deg": floor_pooled(nights, cfg, "test", Ls)[1], "n": int(len(floor_pooled(nights, cfg, "test", Ls)[0]))} for Ls in cfg["floor"]["window_s"]}
    # gate + tables
    gate = evaluate_gate(bt_all, floor_med, cfg)
    log(f"GATE {gate['verdict']}: " + "; ".join(f"{k} pooled {v['pooled_median_deg']:.2f} (thr {v['threshold_deg']})" for k, v in gate["bins"].items())
        + f"; animals passing {gate['n_animals_pass']}/{gate['n_animals']}; floor {floor_med:.2f}", fh)
    models = list(cfg["gyro_fit"]["models"]) + list(cfg["gyro_fit"].get("exploratory_models", []))
    ecols = ["e_baseline"] + [f"e_{m}" for m in models] + ["e_cal_norecon", "e_cal_shakefrozen"]
    tbl_test = bin_table(bt_all[gate_mask(bt_all)], ecols, cfg)
    tbl_test.to_csv(out / "tilt_by_bin_test_nosat.csv", index=False)
    tun_m = ((bt_all["role"] == "tuning") & ~bt_all["sat_gyr"] & ~bt_all["frozen"] & bt_all["edge_ok"]).to_numpy()
    tbl_tun = bin_table(bt_all[tun_m], ecols, cfg)
    tbl_tun.to_csv(out / "tilt_by_bin_tuning_nosat.csv", index=False)
    fs["cv_table"].to_csv(out / "model_selection_cv.csv", index=False)
    # drift scaling
    g = bt_all[gate_mask(bt_all)]
    ds = {"pooled": drift_scaling(g), **{a: drift_scaling(ga) for a, ga in g.groupby("animal")}}
    ds_base = {"pooled_baseline": drift_scaling(g.assign(e_cal=g["e_baseline"]))}
    # saturation
    sat_all = pd.concat([nd["sat_runs"] for nd in nights.values() if len(nd["sat_runs"])], ignore_index=True)
    sat_all.to_csv(out / "sat_runs.csv", index=False)
    ss = saturation_summary(sat_all, bt_all, cfg)
    if "sat_bouts_table" in ss:
        ss["sat_bouts_table"].to_csv(out / "sat_bouts.csv", index=False)
    # per-second + omega distributions
    (out / "per_second").mkdir(exist_ok=True)
    om = []
    for nd in nights.values():
        per_second_table(nd, sel_fits[nd["animal"]], cfg).to_csv(out / "per_second" / f"{nd['night']}_{nd['animal']}.csv", index=False)
        om.append(omega_distribution(nd, sel_fits[nd["animal"]], cfg))
    om = pd.DataFrame(om)
    om.to_csv(out / "omega_distribution.csv", index=False)
    # growth law (test night, calibrated, no sat) + per animal
    floor_p90 = float(np.percentile(floor_ang, 90)) if len(floor_ang) else np.nan
    gl = fit_growth(g["dur_s"].to_numpy(), g["e_cal"].to_numpy(), floor_med, len(floor_ang), cfg, floor_p90)
    gl["table"].to_csv(out / "growth_table.csv", index=False)
    gl_animal = {}
    for a, ga in g.groupby("animal"):
        fa = fit_growth(ga["dur_s"].to_numpy(), ga["e_cal"].to_numpy(), floor_med, len(floor_ang), cfg, floor_p90)
        gl_animal[a] = {"A": fa["A"], "B": fa["B"], "p90": fa["p90"], "n_bins": int(len(fa["table"]))}
    gl_base = fit_growth(g["dur_s"].to_numpy(), g["e_baseline"].to_numpy(), floor_med, len(floor_ang), cfg, floor_p90)
    log(f"growth law A: sigma0 {gl['A']['sigma0_deg']:.2f} deg, k {gl['A']['k_deg_per_s']:.3f} deg/s (R2 {gl['A']['r2']:.2f}); "
        f"B: {gl['B']['sigma0_deg']:.2f} + {gl['B']['k_deg_per_s']:.3f} t (R2 {gl['B']['r2']:.2f}); p90: {gl['p90']}", fh)
    # fits json
    fits_out = {}
    for a in animals:
        fa = {m: {"theta": fs["fits"][a][m]["theta"].tolist(), "M": fs["fits"][a][m]["M"].tolist(), "c": fs["fits"][a][m]["c"],
                  "K": (fs["fits"][a][m]["K"].tolist() if fs["fits"][a][m].get("K") is not None else None),
                  "cv_median_deg": fs["fits"][a][m]["cv_median"], "train_median_deg": fs["fits"][a][m]["train_median"],
                  "n_bouts": fs["fits"][a][m]["n_bouts"], "ok": fs["fits"][a][m]["ok"]} for m in models}
        b = fs["boot"][a]
        fa["bootstrap_selected"] = {"model": sel, "lo": b["lo"].tolist(), "hi": b["hi"].tolist(), "n": int(len(b["theta"]))}
        fits_out[a] = fa
    (out / "fits.json").write_text(json.dumps(fits_out, indent=1, default=_jd), encoding="utf-8")
    # A4
    a4 = {}
    a4_use = []
    if do_a4:
        root16 = Path(cfg["cache_roots"]["imu16"])
        for nd in nights.values():
            a4[f"{nd['animal']}/{nd['night']}"] = build_a4(nd, sel_fits[nd["animal"]], gl["A"], gl["p90"], cfg, root16, out, fh)
        write_a4_readme(root16, cfg, sel, gl, EC.git_commit(), out)
        a4_use = a4_usability(cfg, animals)
        pd.DataFrame(a4_use).to_csv(out / "a4_usability.csv", index=False)
    # config fitted block
    cfg_path = REPO / "wiser" / "configs" / f"imu_attitude_phase0_{cfg.get('_cohort', '2026c')}.json"
    fitted = {"fitted_on": {"gyro_matrices": f"tuning night {tn}", "model_selection": "tuning-night 2-fold CV", "growth_law": f"test night {sn} (pre-registered)"},
              "selected_model": sel, "pooled_cv_median_deg": fs["pooled_cv"],
              "per_animal": {a: {"M": sel_fits[a]["M"].tolist(), "c": sel_fits[a]["c"], "theta": sel_fits[a]["theta"].tolist(),
                                 "ci95_lo": fs["boot"][a]["lo"].tolist(), "ci95_hi": fs["boot"][a]["hi"].tolist(), "n_fit_bouts": sel_fits[a]["n_bouts"]} for a in animals},
              "growth_law": {"A": gl["A"], "B": gl["B"], "p90": gl["p90"]}, "floor_test_L0.5_median_deg": floor_med,
              "gate": {"verdict": gate["verdict"], "bins": gate["bins"], "n_animals_pass": gate["n_animals_pass"]},
              "run_dir": str(out), "git_commit": EC.git_commit(), "written": pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds")}
    if cfg_path.exists():
        cj = json.loads(cfg_path.read_text(encoding="utf-8"))
        cj["fitted"] = json.loads(json.dumps(fitted, default=_jd))
        cfg_path.write_text(json.dumps(cj, indent=2) + "\n", encoding="utf-8")
    prov = {"caches": {f"{nd['animal']}/{nd['night']}": {"a1": str(nd["a1_path"]), "a1_bytes": nd["a1_bytes"], "a1_sha256_head": nd["meta1"].get("source_sha256_head"),
                                                         "a3": str(nd["a3_path"]), "a3_bytes": nd["a3_bytes"], "a3_written": nd["meta3"].get("written_local"),
                                                         "bias_node_err_median_dps": nd["chain_check"], "bias_node_err_max_dps": nd["bias_node_err"]} for nd in nights.values()},
            "audit_reference": cfg["audit_reference"], "git_commit": EC.git_commit()}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=1, default=_jd), encoding="utf-8")
    summary = {"cohort": cfg.get("_cohort", "2026c"), "animals": animals, "nights": cfg["nights"], "selected_model": sel, "pooled_cv": fs["pooled_cv"],
               "fits": fits_out, "gate": gate, "floor_pooled_test": floor_pool, "floor_table": fl.to_dict(orient="records"),
               "tilt_test": tbl_test.to_dict(orient="records"), "tilt_tuning": tbl_tun.to_dict(orient="records"),
               "cv_table": fs["cv_table"].to_dict(orient="records"), "drift_scaling": ds, "drift_scaling_baseline": ds_base,
               "saturation": {k: (v.to_dict(orient="records") if isinstance(v, pd.DataFrame) else v) for k, v in ss.items() if k != "sat_bouts_table"},
               "omega_distribution": om.to_dict(orient="records"), "growth": {"table": gl["table"].to_dict(orient="records"), "A": gl["A"], "B": gl["B"], "p90": gl["p90"],
                                                                                "per_animal": gl_animal, "baseline_A": gl_base["A"], "baseline_B": gl_base["B"]},
               "a4": a4, "a4_usability": a4_use, "chain_check": {f"{nd['animal']}/{nd['night']}": nd["bias_node_err"] for nd in nights.values()},
               "n_bouts": {f"{nd['animal']}/{nd['night']}": int(len(nd["bt"])) for nd in nights.values()},
               "runtime_s": time.time() - t_start, "git_commit": EC.git_commit(), "run_dir": str(out), "literature": cfg.get("literature")}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=_jd), encoding="utf-8")
    return summary


def a4_usability(cfg: dict, animals: list) -> list:
    """Per A4 file: fraction of 16-Hz samples by t_active band and the median |f_xy_2hz| / sigma_theta in each band (descriptive)."""
    rows = []
    root = Path(cfg["cache_roots"]["imu16"])
    bands = [(0, 2), (2, 5), (5, 15), (15, 60), (60, 1e9)]
    for a in animals:
        for night in (cfg["nights"]["tuning"], cfg["nights"]["test"]):
            pth = root / a / f"{night}.npz"
            if not pth.exists():
                continue
            with np.load(pth, allow_pickle=True) as z:
                ta, sg, f = z["t_active_s"], z["sigma_theta_deg"], np.linalg.norm(z["f_xy_2hz"], axis=1)
                still = z["still"]
            rec = {"animal": a, "night": night, "n": int(len(ta)), "frac_still": float(still.mean()), "sigma_median_deg": float(np.median(sg))}
            for lo, hi in bands:
                m = (ta >= lo) & (ta < hi)
                tag = f"{lo:g}_{hi:g}" if hi < 1e8 else f"{lo:g}_inf"
                rec[f"frac_t{tag}"] = float(m.mean())
                rec[f"fxy_med_t{tag}"] = float(np.median(f[m])) if m.any() else np.nan
                rec[f"sigma_med_t{tag}"] = float(np.median(sg[m])) if m.any() else np.nan
            rows.append(rec)
    return rows


def write_a4_readme(root16: Path, cfg: dict, sel: str, gl: dict, commit: str, run_dir: Path) -> None:
    root16.mkdir(parents=True, exist_ok=True)
    ac = cfg["attitude"]
    txt = f"""# A4 cache - 16-Hz head-IMU attitude and world-frame horizontal specific force (cohort 2026c)

Written by `wiser/scripts/analyze_imu_attitude_phase0.py` (git {commit}, run `{run_dir}`), plan
`implementation_plan/2026-09-30-imu-attitude-phase0.md`. One file per animal-night: `<SFxx>/night_<YYYYMMDD>.npz`
(same window as the A1/A3 caches, 20:50 -> 05:30 field-PC local). Everything here is derived from A1 (raw 1250-Hz IMU) and
A3 (100-Hz calibrated IMU); raw E: is never read. IMU only - no WISER.

Pipeline: A1 counts -> Hampel -> gyro saturation runs classified ({', '.join(CLASSES)}) and reconstructed (log-quadratic
shoulder fit; impact / short_broadband kept clipped) -> {ac and cfg['chain']['fc_hz']:.0f}-Hz zero-phase Butterworth-4 -> 100 Hz -> head frame
-> minus A3 running-median bias -> omega = M (w - b) (per-animal matrix `{sel}`, fitted on the tuning night 2026-09-08/09)
-> quaternion integration at 100 Hz with gravity aiding ONLY in quiet (quasi-static) samples (tau = {ac['tau_quiet_s']} s), no dynamic
pull -> f = R(q) a_cal - g e_z (world frame) -> low-pass {ac['fxy_cutoffs_hz']} Hz -> resample_poly(4, 25) -> 16 Hz.

| key | dtype / shape | meaning |
|---|---|---|
| `t_unix_ms` | float64 (n,) | field-PC Unix ms on the IMU clock (tau* NOT applied); grid j <-> 100-Hz sample 6.25 j |
| `f_xy_2hz`, `f_xy_1hz`, `f_xy_4hz` | float32 (n, 2) | world-frame horizontal specific force, m/s^2, gravity removed, low-passed at 2 / 1 / 4 Hz. **Yaw is arbitrary** (0 at the night start) **but continuous**: the x/y axes are a fixed but unknown rotation of the paddock frame per night, drifting slowly with the residual gyro bias. 2 Hz is the default (UWB Nyquist 1.75 Hz; the validated tilt band). |
| `f_z_2hz` | float32 (n,) | vertical specific force minus g, m/s^2 |
| `q_wh` | float32 (n, 4) | attitude quaternion [w, x, y, z], v_world = R(q) v_head (head: x nose, y left, z up), nearest 100-Hz sample (<= 5 ms) |
| `sigma_theta_deg` | float32 (n,) | per-axis SD of the 2-D tilt error at the sample's t_active, from the pre-registered law sigma(t) = sqrt(sigma0^2 + (k t)^2) with sigma0 = {gl['A']['sigma0_deg']:.3f} deg, k = {gl['A']['k_deg_per_s']:.3f} deg/s (test night 2026-09-10/11); median tilt angle = 1.1774 sigma. A filter's attitude process noise must be at least this. |
| `p90_theta_deg` | float32 (n,) | p90 envelope of the tilt error at t_active: sqrt(p0^2 + (k90 t)^2), p0 = {gl['p90']['p0_deg'] if gl['p90'] else float('nan'):.2f}, k90 = {gl['p90']['k90_deg_per_s'] if gl['p90'] else float('nan'):.3f} |
| `t_active_s` | float32 (n,) | seconds since the last quiet (gravity-aided) sample; 0 inside quiet windows |
| `still` / `dyn` | bool (n,) | the whole 62.5-ms support is quiet / not (dyn = ~still) |
| `sat`, `recon`, `shake`, `frozen`, `invalid` | bool (n,) | any raw gyro saturation / any reconstructed run / inside a shake-train span (+-25 ms) / hung chip (attitude held) / = frozen, within the support |
| `bp_w_<lo>_<hi>`, `bp_a_<lo>_<hi>` | float32 (n,) | behaviour-band powers of the 100-Hz norms |omega| ((deg/s)^2) and |a| ((m/s^2)^2): Butterworth-4 zero-phase band-pass {ac['band_powers_hz']} Hz, squared, {ac['band_power_window_s']}-s centred mean, sampled on the 16-Hz grid. Motion-state features (locomotion 4-8, grooming ~4, sniffing 8-12, shakes 14-18 Hz) - never integrate them. Note: the norm of an oscillating vector carries the double frequency too. |
| `calib_json`, `meta_json` | str | gyro matrix M, c, acc ellipsoid, chain/saturation/attitude parameters, growth laws, sources, git commit |

Rules: grooming / scratching / shaking epochs are NOT excluded (the body is stationary in them - a translation filter should treat
them as zero-velocity states, using `shake` and the band powers). Treat any sample with `invalid` as missing. The tilt
uncertainty grows with `t_active`; `f_xy` inherits a horizontal bias of g * sin(tilt error) (1 deg = 0.17 m/s^2).
"""
    (root16 / "README.md").write_text(txt, encoding="utf-8")


# ====================================================================================================== figures
def _f(x, nd: int = 2) -> str:
    try:
        if x is None or (isinstance(x, float) and not np.isfinite(x)):
            return "n/a"
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)


def param_names(model: str) -> list:
    Mn = ["xx", "xy", "xz", "yx", "yy", "yz", "zx", "zy", "zz"]
    return {"scalar": ["s"], "diag": ["dx", "dy", "dz"], "M": Mn, "M_rate": Mn + ["c"], "scalar_gsens": ["s"] + [f"K{n}" for n in Mn],
            "M_gsens": Mn + [f"K{n}" for n in Mn]}[model]


def make_figures(S_: dict, out: Path, fig_dir: Path, cohort: str) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = []
    sel = S_["selected_model"]
    animals = S_["animals"]
    labels = ["2-5 s", "5-15 s", "15-40 s", "40-90 s"]
    tt = pd.DataFrame(S_["tilt_test"])
    # 1 tilt by bin
    fig, axs = plt.subplots(2, len(animals) + 1, figsize=(3.4 * (len(animals) + 1), 7), sharey="row", squeeze=False)
    for j, a in enumerate(animals + ["pooled"]):
        g = tt[tt["animal"] == a].set_index("dbin").reindex(labels)
        x = np.arange(4)
        for row, stat in enumerate(("med", "p90")):
            ax = axs[row, j]
            ax.bar(x - 0.2, g[f"e_baseline_{stat}"], 0.38, color="#999999", label="audit baseline (A3, s = 1.03)")
            ax.bar(x + 0.2, g[f"e_{sel}_{stat}"], 0.38, color="#c0392b", label=f"calibrated ({sel})")
            if row == 0:
                ax.axhline(S_["gate"]["floor_median_deg"], color="#2c7fb8", lw=1, ls="--", label="floor (0.5-s windows)")
                for k, thr in ((0, 1.0), (1, 2.0)):
                    ax.plot([k - 0.45, k + 0.45], [thr, thr], color="k", lw=1.5, label="gate" if k == 0 else None)
            ax.set_xticks(x)
            ax.set_xticklabels([f"{l}\nn={int(n)}" for l, n in zip(labels, g["n"].fillna(0))], fontsize=8)
            ax.set_title(f"{a}  {'median' if row == 0 else 'p90'}", fontsize=10)
            ax.grid(alpha=0.3, axis="y")
    axs[0, 0].set_ylabel("end-of-bout tilt error (deg)")
    axs[1, 0].set_ylabel("p90 (deg)")
    axs[0, 0].legend(fontsize=7, loc="upper left")
    fig.suptitle(f"Test night {S_['nights']['test']}, bouts without gyro saturation: pure-gyro tilt error before/after gyro-matrix calibration; GATE {S_['gate']['verdict']}")
    fig.tight_layout()
    p = fig_dir / f"{STEM}_tilt_by_bin_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 2 gyro matrix
    fig, axs = plt.subplots(1, len(animals), figsize=(4 * len(animals), 4), sharey=True, squeeze=False)
    axs = axs[0]
    names = param_names(sel)
    for j, a in enumerate(animals):
        f = S_["fits"][a]
        th = np.asarray(f[sel]["theta"])
        lo, hi = np.asarray(f["bootstrap_selected"]["lo"]), np.asarray(f["bootstrap_selected"]["hi"])
        ax = axs[j]
        ax.errorbar(np.arange(len(th)), th, yerr=[th - lo, hi - th], fmt="o", color="#c0392b", capsize=3)
        ax.axhline(0, color="k", lw=0.8)
        ax.axhline(0.03, color="#999999", lw=1, ls="--", label="V4 scalar 1.03")
        ax.set_xticks(np.arange(len(th))); ax.set_xticklabels(names, fontsize=8)
        ax.set_title(f"{a}: {sel} parameters (M - I entries)", fontsize=10)
        ax.grid(alpha=0.3)
    # also the exploratory M_gsens matrix of each animal as text in the title area (report has the table)
    axs[0].set_ylabel("parameter value (95 % bootstrap CI)")
    axs[0].legend(fontsize=8)
    fig.tight_layout()
    p = fig_dir / f"{STEM}_gyro_matrix_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 3 saturation
    sr = pd.read_csv(out / "sat_runs.csv") if (out / "sat_runs.csv").exists() and (out / "sat_runs.csv").stat().st_size > 10 else pd.DataFrame()
    fig, axs = plt.subplots(1, 5, figsize=(24, 4.5))
    cols = {"impact": "k", "shake_train": "#2c7fb8", "short_broadband": "#f39c12", "suspect_monotone": "#8e44ad", "rotation": "#c0392b"}
    if len(sr):
        ax = axs[0]
        for c, g in sr.groupby("cls"):
            ax.scatter(g["dur_ms"], g["acc_hf_frac"], s=8, alpha=0.5, color=cols.get(c, "g"), label=f"{c} (n={len(g)})")
        ax.set_xlabel("clipped run duration (ms)"); ax.set_ylabel("acc HF fraction (100-625 Hz, +-40 ms)"); ax.legend(fontsize=7); ax.set_xscale("log"); ax.grid(alpha=0.3)
        ax = axs[1]
        gp = sr["gap_prev_ms"].dropna()
        ax.hist(np.clip(gp, 0, 400), bins=np.r_[np.arange(0, 205, 5), 400], color="#555555")
        for v in (25, 40, 70):
            ax.axvline(v, color="#2c7fb8", lw=1, ls="--")
        ax.set_xlabel("spacing to previous run, same lane (ms; > 200 clipped)"); ax.set_ylabel("runs"); ax.set_title("14-40 Hz = 25-70 ms", fontsize=9); ax.grid(alpha=0.3)
        ax = axs[2]
        data = [sr.loc[sr["cls"] == c, "acc_max_g"].to_numpy() for c in CLASSES]
        ax.boxplot([d if len(d) else [np.nan] for d in data], tick_labels=[f"{c}\n{len(d)}" for c, d in zip(CLASSES, data)], showfliers=False)
        ax.axhline(2, color="#2c7fb8", lw=1, ls="--", label="2 g"); ax.set_ylabel("|a| max within +-10 ms (g)"); ax.tick_params(axis="x", labelsize=7); ax.legend(fontsize=8); ax.grid(alpha=0.3)
        ax = axs[3]
        rc = sr[sr["recon"]]
        ax.hist(rc["missing_deg"], bins=40, color="#c0392b")
        ax.set_xlabel("recovered missing angle per run (deg)"); ax.set_ylabel("runs"); ax.set_title(f"reconstructed {len(rc)} / {len(sr)} runs; median {rc['missing_deg'].median():.2f} deg", fontsize=9); ax.grid(alpha=0.3)
    sb = S_["saturation"].get("sat_bouts")
    if sb:
        ax = axs[4]
        sbd = pd.DataFrame(sb)
        x = np.arange(len(sbd))
        for k, (c, lab) in enumerate((("e_baseline", "clipped (A3)"), ("e_cal_norecon", "(i) clipped + M"), ("e_cal", "(ii) recon + M"), ("e_cal_shakefrozen", "(iii) recon + frozen shakes"))):
            ax.bar(x + (k - 1.5) * 0.2, sbd[c], 0.2, label=lab)
        ax.set_xticks(x); ax.set_xticklabels([f"{r.contains}\nn={r.n}" for r in sbd.itertuples()], fontsize=8)
        ax.set_ylabel("median tilt error (deg)"); ax.set_title("bouts WITH gyro saturation (both nights)", fontsize=9); ax.legend(fontsize=7); ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    p = fig_dir / f"{STEM}_saturation_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 4 growth law
    gt = pd.DataFrame(S_["growth"]["table"])
    A, Bl, P9 = S_["growth"]["A"], S_["growth"]["B"], S_["growth"]["p90"]
    fig, ax = plt.subplots(figsize=(8, 5))
    t = np.linspace(0, 90, 400)
    ax.scatter(gt["t_mid"], gt["med"], s=np.sqrt(gt["n"]) * 6, color="#c0392b", label="bin median (calibrated, test night, no sat)", zorder=3)
    ax.scatter(gt["t_mid"], gt["p90"], s=np.sqrt(gt["n"]) * 6, color="#8e44ad", marker="^", label="bin p90", zorder=3)
    ax.plot(t, 1.1774 * np.sqrt(A["sigma0_deg"] ** 2 + (A["k_deg_per_s"] * t) ** 2), color="#c0392b", label=f"A: 1.1774 sqrt(s0^2 + (k t)^2), s0 {A['sigma0_deg']:.2f} deg, k {A['k_deg_per_s']:.3f} deg/s (R2 {A['r2']:.2f})")
    ax.plot(t, 1.1774 * (Bl["sigma0_deg"] + Bl["k_deg_per_s"] * t), color="#c0392b", ls=":", label=f"B: 1.1774 (s0 + k t), s0 {Bl['sigma0_deg']:.2f}, k {Bl['k_deg_per_s']:.3f} (R2 {Bl['r2']:.2f})")
    if P9:
        ax.plot(t, np.sqrt(P9["p0_deg"] ** 2 + (P9["k90_deg_per_s"] * t) ** 2), color="#8e44ad", ls="--", label=f"p90: sqrt(p0^2 + (k90 t)^2), p0 {P9['p0_deg']:.2f}, k90 {P9['k90_deg_per_s']:.3f}")
    bA = S_["growth"]["baseline_A"]
    ax.plot(t, 1.1774 * np.sqrt(bA["sigma0_deg"] ** 2 + (bA["k_deg_per_s"] * t) ** 2), color="#999999", ls="--", label=f"baseline A (audit chain): s0 {bA['sigma0_deg']:.2f}, k {bA['k_deg_per_s']:.3f}")
    ax.set_xlabel("active bout duration t (s)"); ax.set_ylabel("end-of-bout tilt error (deg)"); ax.set_xscale("symlog", linthresh=2); ax.set_yscale("log")
    ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=7); ax.set_title("Attitude-error growth law sigma_theta(t_active)")
    fig.tight_layout()
    p = fig_dir / f"{STEM}_growth_law_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 5 omega distribution
    om = pd.DataFrame(S_["omega_distribution"])
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(om))
    for k, (c, lab) in enumerate((("active_p50", "active p50"), ("active_p90", "active p90"), ("active_p99", "active p99"), ("active_p99_9", "active p99.9"), ("active_max", "active max"), ("quiet_p99", "quiet p99"))):
        ax.bar(x + (k - 2.5) * 0.14, om[c], 0.14, label=lab)
    for v, lab in ((500, "voluntary head-turn peak ~500 (Pasquet 2016)"), (107, "ambulation SD|w| ~107"), (2000, "gyro range 2000")):
        ax.axhline(v, color="k", lw=0.8, ls="--"); ax.text(len(om) - 0.5, v * 1.05, lab, fontsize=7, ha="right")
    ax.set_yscale("log"); ax.set_xticks(x); ax.set_xticklabels([f"{r.animal}\n{r.night[-4:]}" for r in om.itertuples()], fontsize=8)
    ax.set_ylabel("|omega| (deg/s), 100 Hz calibrated"); ax.legend(fontsize=7, ncol=3); ax.grid(alpha=0.3, axis="y", which="both")
    ax.set_title("Head angular speed by activity (per-sample percentiles) vs literature")
    fig.tight_layout()
    p = fig_dir / f"{STEM}_omega_distribution_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 6 drift scaling
    bt = pd.read_csv(out / "bouts_all.csv")
    g = bt[gate_mask(bt)]
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.5))
    for a, ga in g.groupby("animal"):
        axs[0].scatter(ga["rot_deg"], ga["e_cal"], s=8, alpha=0.6, label=a)
        axs[1].scatter(ga["dur_s"], ga["e_cal"], s=8, alpha=0.6, label=a)
        axs[2].scatter(ga["hf_gyr"], ga["e_cal"] / ga["dur_s"], s=8, alpha=0.6, label=a)
    ds = S_["drift_scaling"]["pooled"]
    axs[0].set_xlabel("total rotation in bout (deg)"); axs[0].set_ylabel("tilt error (deg), calibrated"); axs[0].set_title(f"Spearman {ds.get('spearman_e_rot', np.nan):.2f}; {ds.get('deg_per_100deg_median', np.nan):.2f} deg per 100 deg (median)", fontsize=9)
    axs[1].set_xlabel("bout duration (s)"); axs[1].set_title(f"Spearman {ds.get('spearman_e_dur', np.nan):.2f}; {ds.get('deg_per_s_median', np.nan):.2f} deg/s (median)", fontsize=9)
    axs[2].set_xlabel("HF gyro power proxy (deg/s)^2"); axs[2].set_ylabel("drift rate (deg/s)"); axs[2].set_title(f"rectification test: Spearman(rate, HF gyro) {ds.get('spearman_rate_hf_gyr', np.nan):.2f}", fontsize=9)
    for ax in axs:
        ax.set_xscale("log"); ax.set_yscale("log"); ax.grid(alpha=0.3, which="both")
    axs[0].legend(fontsize=7)
    fig.suptitle("What the residual drift scales with (test night, no saturation, calibrated)")
    fig.tight_layout()
    p = fig_dir / f"{STEM}_drift_scaling_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    return figs


# ====================================================================================================== report
def write_report(S_: dict, figs: list, out: Path, rdir: Path, cohort: str, cfg: dict) -> Path:
    sel = S_["selected_model"]
    animals = S_["animals"]
    gate = S_["gate"]
    labels = cfg["bouts"]["bin_labels"]
    tt = pd.DataFrame(S_["tilt_test"])
    L = []
    w = L.append
    w(f"# Head-IMU attitude, Phase 0 (cohort {cohort}): gyro self-calibration, saturation, attitude-error model, and the fusion gate — **GATE {gate['verdict']}**\n")
    w(f"- **Status:** pre-registered in [`implementation_plan/2026-09-30-imu-attitude-phase0.md`](../../../../implementation_plan/2026-09-30-imu-attitude-phase0.md) (user approval 2026-09-30 \"phase0 开始\"); all rules fixed before coding; gyro matrices and the model choice fitted on the **tuning night {S_['nights']['tuning']}** only; the gate evaluated once on the **test night {S_['nights']['test']}**. IMU only — **no WISER fusion was run**.")
    w(f"- **Follows:** the V4 audit ([`change_log/2026-09-29-wiser-ins-fusion.md`](../../../../change_log/2026-09-29-wiser-ins-fusion.md) §*Audit of the V4 result*), whose bout construction and gravity-propagation test are reused unchanged (`audit_20260930/coning_test.py`).")
    w(f"- **Run:** `python wiser/scripts/analyze_imu_attitude_phase0.py --cohort {cohort}`; bulk `{S_['run_dir']}` (per-bout `bouts_all.csv`, `floor.csv`, `sat_runs.csv`, `sat_bouts.csv`, `per_second/`, `omega_distribution.csv`, `model_selection_cv.csv`, `fits.json`, `growth_table.csv`, `summary.json`, `input_provenance.json`, `log.txt`); pointer `run_manifest_imu_attitude_phase0_{cohort}.json`; git `{S_['git_commit']}`; runtime {S_['runtime_s'] / 60:.1f} min. Config `wiser/configs/imu_attitude_phase0_{cohort}.json` (rules; `fitted` written by this run).")
    w(f"- **A4 cache:** `{cfg['cache_roots']['imu16']}/<SFxx>/night_<date>.npz` ({len(S_['a4'])} files, {sum(v['bytes'] for v in S_['a4'].values()) / 1e6:.0f} MB) + `README.md` next to the root — format in §6.")
    w("- **Inputs (read-only caches):** A1 raw 1250-Hz IMU lanes and A3 100-Hz calibrated IMU of the V4 run (`input_provenance.json` lists paths, sizes, sha256 heads). Raw `E:` was not read.\n")
    # ---- 1 headline
    w("## 1. Headline\n")
    b25, b515 = gate["bins"]["2-5 s"], gate["bins"]["5-15 s"]
    w(f"1. **GATE {gate['verdict']}.** Test night, bouts without gyro saturation, calibrated pipeline (`{sel}`): median end-of-bout tilt error "
      f"**{_f(b25['pooled_median_deg'])}°** for 2–5 s bouts (threshold 1.0°, n = {b25['n']}, 95 % CI {_f(b25['ci95'][0])}–{_f(b25['ci95'][1])}) and "
      f"**{_f(b515['pooled_median_deg'])}°** for 5–15 s (threshold 2.0°, n = {b515['n']}, CI {_f(b515['ci95'][0])}–{_f(b515['ci95'][1])}); "
      f"{gate['n_animals_pass']}/{gate['n_animals']} animals pass both bins individually (≥ {cfg['gate']['min_animals_pass']} required). "
      f"Audit baseline on the same bouts: {_f(b25['baseline_median_deg'])}° / {_f(b515['baseline_median_deg'])}°. "
      f"Measurement floor (0a, 0.5-s windows, test night pooled): **{_f(gate['floor_median_deg'])}°**; excess over the floor {_f(b25['excess_over_floor_deg'])}° / {_f(b515['excess_over_floor_deg'])}°"
      + (" — in the failing bin(s) the excess is < 0.5°, i.e. the test, not the gyro, is at its limit." if (gate["verdict"] == "FAIL" and all(v["within_floor_excess"] for v in gate["bins"].values() if not v["pooled_pass"])) else "") + ".")
    pooled = tt[tt["animal"] == "pooled"].set_index("dbin")
    w(f"2. **Gyro-matrix calibration (0b)** — selected by tuning-night CV: `{sel}` (pooled CV medians: " + ", ".join(f"{m} {_f(v, 3)}" for m, v in S_["pooled_cv"].items()) + "°). "
      f"Test-night medians baseline → calibrated: " + "; ".join(f"{lab} {_f(pooled.loc[lab, 'e_baseline_med'])} → {_f(pooled.loc[lab, f'e_{sel}_med'])}°" for lab in labels) + ".")
    ds = S_["drift_scaling"]["pooled"]
    w(f"3. **What the residual drift scales with (test night, calibrated):** Spearman(e, rotation) {_f(ds.get('spearman_e_rot'))} vs Spearman(e, duration) {_f(ds.get('spearman_e_dur'))}; "
      f"{_f(ds.get('deg_per_100deg_median'))}° per 100° turned (p90 {_f(ds.get('deg_per_100deg_p90'))}); {_f(ds.get('deg_per_s_median'))} °/s of activity (p90 {_f(ds.get('deg_per_s_p90'))}); "
      f"rectification test: Spearman(drift rate, HF gyro power) {_f(ds.get('spearman_rate_hf_gyr'))}, (rate, HF acc power) {_f(ds.get('spearman_rate_hf_acc'))}, (rate, mean |a_h|) {_f(ds.get('spearman_rate_mean_ah'))}; error-vector consistency {_f(ds.get('error_vector_consistency'))}.")
    sat = S_["saturation"]
    cc = pd.DataFrame(sat.get("class_counts", []))
    tot = {c: int(cc[c].sum()) for c in CLASSES} if len(cc) else {}
    w(f"4. **Saturation (0c):** {sum(tot.values()) if tot else 0} clipped gyro runs over the 10 animal-nights: " + ", ".join(f"{c} {n}" for c, n in tot.items())
      + (f"; {sat['recon']['n_recon']} reconstructed (median missing angle {_f(sat['recon']['missing_deg_median'])}°, p90 {_f(sat['recon']['missing_deg_p90'])}°; median reconstructed peak {_f(sat['recon']['peak_dps_median'], 0)} °/s)" if "recon" in sat else "")
      + (f"; {sat['shake_trains']['n_trains']} shake trains, |net angle| median {_f(sat['shake_trains']['net_deg_abs_median'])}°" if "shake_trains" in sat else "") + ".")
    A = S_["growth"]["A"]
    w(f"5. **Attitude-error growth law (0e, test night):** σ_θ(t) = sqrt({_f(A['sigma0_deg'])}² + ({_f(A['k_deg_per_s'], 3)} t)²) ° (R² {_f(A['r2'])}); p90 envelope sqrt({_f(S_['growth']['p90']['p0_deg'])}² + ({_f(S_['growth']['p90']['k90_deg_per_s'], 3)} t)²)°.\n")
    for f in figs:
        w(f"![{f}](../figures/{f})\n")
    # ---- 2 definitions
    w("## 2. Definitions\n")
    w("Head frame: x nose, y left, z up (`make_imu.S`, v_B = S v_H). $\\mathbf w_k$ = 100-Hz head-frame gyro after Hampel, saturation reconstruction, 40-Hz zero-phase Butterworth-4 and resample_poly 2/25 (°/s); $\\mathbf b_k$ = A3 running-median bias (1-min nodes, linear interpolation); $\\mathbf a_k$ = A3 calibrated accelerometer (ellipsoid $D(\\mathbf a-\\mathbf o)$, m/s²); $\\Delta t$ = 0.01 s; $g$ = 9.81 m/s².\n")
    w("**Quiet sample.** A3 `quiet`: 1-s window with median |ω| < 10 °/s and | k_a·median|a| − g | < 0.05 g, no bad samples (make_imu rule). **Text:** the quasi-static state in which the accelerometer direction is taken as gravity.\n")
    w("**IMU update rate (measured here).** All six analogin lanes are sample-and-hold: ≈ 190 updates/s (hold 5–7 logger samples, mean 6.6 ≈ 5.3 ms; ≈ 5 % of updates skipped; acc and gyro synchronous). The 1250-Hz lanes are the logger's clock, not the sensor's; a clipped run of ~7 raw samples is one clipped gyro reading. **Text:** the effective gyro/acc bandwidth is ≤ 95 Hz; nothing faster than ~5 ms is resolved.\n")
    w("**Bout.** Maximal run of non-quiet samples $[a,b)$ with $2 \\le (b-a)\\Delta t \\le 90$ s and 0.5 s of data on both sides; $\\hat{\\mathbf g}_{start}$ = normalised mean of $\\mathbf a$ over $[a-50,a)$, $\\hat{\\mathbf g}_{end}$ over $[b,b+50)$. Bins 2–5, 5–15, 15–40, 40–90 s. **Text:** an episode of head activity bracketed by two gravity measurements; identical to the audit's construction.\n")
    w("**Gravity propagation and end-of-bout tilt error ($e$).** $\\mathbf g_{k+1}=\\mathrm{Exp}(-\\boldsymbol\\omega_k\\Delta t)\\,\\mathbf g_k$ (Rodrigues, head frame), $\\mathbf g_a=\\hat{\\mathbf g}_{start}$; $e=\\angle(\\mathbf g_b,\\hat{\\mathbf g}_{end})$ in degrees; error vector $\\boldsymbol\\varepsilon=\\mathbf g_b-\\hat{\\mathbf g}_{end}$. **Text:** how far the gyro alone mis-tracks the vertical across the bout; 0 = perfect; it contains the floor below. Units °.\n")
    w("**Audit baseline.** $\\boldsymbol\\omega = 1.03\\,(\\mathbf w^{A3}-\\mathbf b)$, i.e. A3 `gyr` (the audit's `lp100_s1.03`). **Text:** the V4 gyro chain, scalar scale only, clipped samples as recorded.\n")
    w(f"**Floor ($\\varphi_L$, 0a).** For consecutive non-overlapping windows $w_1,w_2$ of length $L$ inside a quiet run (no saturation/frozen), $\\varphi_L=\\angle(\\bar{{\\mathbf a}}_{{w_1}},\\bar{{\\mathbf a}}_{{w_2}})$. **Text:** the tilt-error the test would report for a bout of zero activity (acc noise + residual micro-motion); the gate is read against the L = 0.5 s median. Excludes cross-orientation accelerometer-calibration residuals (A3 held-out gravity residual 0.016 m/s² ≈ 0.1°) → a lower bound. *Bridged floor*: $w_1$ propagated with the calibrated gyro through $d$ s of quiet, compared with the window after the gap (floor + still drift).\n")
    w(f"**Gyro models (0b).** scalar $\\boldsymbol\\omega=(1+s)(\\mathbf w-\\mathbf b)$; diag $\\boldsymbol\\omega=\\mathrm{{diag}}(1+d_i)(\\mathbf w-\\mathbf b)$; **M** $\\boldsymbol\\omega=(I+E)(\\mathbf w-\\mathbf b)$, $E\\in\\mathbb R^{{3\\times3}}$ free (scale, non-orthogonality, gyro-to-accelerometer misalignment); **M_rate** $\\boldsymbol\\omega=(1+c\\,|\\mathbf w-\\mathbf b|^2/\\omega_0^2)(I+E)(\\mathbf w-\\mathbf b)$, $\\omega_0$ = 1000 °/s. **Objective:** $\\sum_i\\rho_H(\\boldsymbol\\varepsilon_i/f)$ over tuning-night bouts of 2–15 s without saturation/frozen samples, Huber $\\rho_H(z)=z^2$ for $|z|\\le1$ else $2|z|-1$ per component, $f$ = 3° (scipy `least_squares`, loss huber, trf, bounds |E| ≤ 0.3, |c| ≤ 1, start E = 0.03 I). **Text:** the matrix that makes the gyro close the start→end gravity loop best; bouts with error < 3° count quadratically, larger ones linearly.\n")
    w(f"**Model selection.** 2-fold CV on the tuning night (folds = alternating 10-min blocks of bout start time); score = pooled (5 animals) held-out median $e$ on 2–15 s bouts; the lowest wins, a model within {cfg['gyro_fit']['cv_tie_deg']}° of it with fewer parameters is preferred. **Bootstrap CI:** {cfg['gyro_fit']['n_bootstrap']} resamples of the fit bouts with replacement, refit, 2.5/97.5 percentiles per entry.\n")
    w("**Drift scaling.** Spearman rank correlations of $e$ with the bout duration and with the total rotation $\\Theta=\\sum_k|\\boldsymbol\\omega_k|\\Delta t$ (°); $e/\\Theta\\cdot100$ (° per 100° turned); $e/T$ (°/s); error-vector consistency $|\\overline{\\boldsymbol\\varepsilon}|/\\overline{|\\boldsymbol\\varepsilon|}$ (1 = same direction in the head frame every bout, 0 = random). **Rectification test:** Spearman of the drift rate $e/T$ with $P_{HF}$ = mean squared first difference of the raw 1250-Hz gyro (resp. acc) over the bout, summed over the three lanes (a first-difference high-pass proxy, (°/s)² resp. (m/s²)²), and with $\\overline{|\\mathbf a_h|}$ = mean norm of the head-frame acceleration component perpendicular to the propagated gravity (m/s²). **Reading rule (pre-registered):** error ∝ rotation → calibration incomplete; ∝ duration and correlated with vibration power → rate-independent (rectified) bias.\n")
    w("**Clipped run and features (0c).** Consecutive raw samples with |raw| ≥ 32700 on one gyro lane (rail = 1996 °/s). Duration (samples / ms), sign, entry/exit slope (linear fit over the 4 unclipped samples before/after, °/s per ms), |a|_max within ±10 ms (g), acc saturation within ±10 ms, $W_{acc}$ = fraction of the mean-removed acc power in 100–625 Hz within ±40 ms (rfft), spacing to the previous/next run on the same lane (ms). **Train:** runs whose onsets are ≤ 70 ms apart. **Classes (priority order):** `impact` (acc clipped within ±10 ms) → `shake_train` (train ≥ 2 runs, spacing 25–70 ms, alternating sign in ≥ 50 % of successive pairs) → `short_broadband` (≤ 3 samples and $W_{acc}$ ≥ 0.5) → isolated: `suspect_monotone` if the implied net rotation over run ± 25 ms is ≥ 60° with |a|_max < 2 g, else `rotation`.\n")
    w("**Reconstruction and missing angle.** For every run not `impact`/`short_broadband` with clean shoulders: $\\ln|\\omega(t)|=p_0+p_1t+p_2t^2$ least-squares through the 2 + 2 innermost **held readings** (reading centres; fallback 3 + 3) around the run — chosen on synthetic sample-and-hold pulses (median recovered/true missing angle 1.00, p10 0.92, p90 1.9; the plain quadratic recovers 0.7–0.85, outer readings sit in the pulse tails); accepted if $p_2<0$, the extremum lies inside the run ± 1 sample and the peak ≤ 3 rails; clipped samples ← max(fit, rail) with the run's sign; $\\Delta\\theta=\\sum_k(|\\hat\\omega_k|-\\omega_{rail})\\Delta t_{raw}$ (°). **Net angle** of a train = $\\sum\\omega\\,\\Delta t_{raw}$ of the reconstructed lane over first onset − 25 ms → last end + 25 ms (°; ≈ 0 for a shake). **Treatments on saturation bouts:** (i) clipped + M, (ii) reconstructed + M (**used for A4**), (iii) (ii) with ω := 0 inside shake-train spans.\n")
    w("**Per-second |ω| statistics.** $|\\boldsymbol\\omega|$ of the calibrated 100-Hz stream; per-sample percentiles in active (non-quiet) and quiet seconds; `wmax_raw_unclipped` = largest raw |ω| in samples where no gyro lane is saturated. **Text:** how fast the head turns, for the literature comparison in §5.\n")
    w(f"**Attitude pipeline (0d).** $q_{{k+1}}=q_k\\otimes\\mathrm{{Exp}}(\\boldsymbol\\omega_k\\Delta t)$ (q: head → world, [w,x,y,z]); in quiet samples $q\\leftarrow q\\otimes\\mathrm{{Exp}}(-\\kappa\\,\\hat{{\\mathbf g}}_h\\times\\hat{{\\mathbf a}})$ with $\\hat{{\\mathbf g}}_h=R(q)^\\top\\mathbf e_z$, $\\kappa=\\Delta t/\\tau$, τ = {cfg['attitude']['tau_quiet_s']} s (no correction in non-quiet samples; yaw never corrected → arbitrary, continuous); frozen samples hold q. $\\mathbf f=R(q)\\mathbf a-g\\mathbf e_z$; $\\mathbf f_{{xy}}$ low-passed (Butterworth-4 zero-phase) at 2 Hz (also 1, 4) and decimated 100 → 16 Hz (resample_poly 4/25). Quiet-tilt check = median angle between $\\hat{{\\mathbf g}}_h$ and $\\hat{{\\mathbf a}}$ over quiet samples.\n")
    w("**Band powers.** $P_{band}(x)$ = 0.5-s centred mean of the squared Butterworth-4 zero-phase band-pass of the 100-Hz norm $x\\in\\{|\\boldsymbol\\omega|,|\\mathbf a|\\}$, bands 2–4, 4–8, 8–12, 12–20 Hz, sampled on the 16-Hz grid. **Text:** behaviour features (locomotion, grooming, sniffing, shakes); never integrated.\n")
    w("**Growth law (0e).** Test-night calibrated no-saturation bouts binned by duration (edges 0, 2, 3, 4, 5, 7, 10, 15, 22, 30, 45, 60, 90 s; ≥ 15 bouts) plus the floor at t = 0; $\\sigma_\\theta$ = per-axis SD of the 2-D tilt error with median angle $=1.1774\\,\\sigma_\\theta$ (Rayleigh). **A:** $\\sigma_\\theta(t)=\\sqrt{\\sigma_0^2+(kt)^2}$; **B:** $\\sigma_0+kt$; **p90:** $\\sqrt{p_0^2+(k_{90}t)^2}$ on the bin p90s; weighted least squares (weights √n). **Text:** the attitude process-noise law a filter must use; $t$ = seconds since the last quiet sample.\n")
    w(f"**Gate.** Test night, no-gyro-saturation bouts, calibrated pipeline; PASS iff pooled median $e$ ≤ 1.0° (2–5 s) **and** ≤ 2.0° (5–15 s) **and** ≥ 4 of 5 animals satisfy both. CIs = 1000 bout-bootstrap draws of the median (information only).\n")
    # ---- 3 floor
    w("## 3. 0a — Measurement floor\n")
    fl = pd.DataFrame(S_["floor_table"])
    w("Pooled test-night floor: " + ", ".join(f"L = {k[1:]} s median {_f(v['median_deg'])}° (n = {v['n']})" for k, v in S_["floor_pooled_test"].items()) + ".\n")
    w("| night | animal | adjacent 0.5 s med / p90 | 1 s | 2 s | bridged 0.5 s + 1 s quiet | + 2 s | + 5 s |\n|---|---|---|---|---|---|---|---|")
    for (n_, a_), g in fl.groupby(["night", "animal"]):
        def cell(kind, L, gap):
            r = g[(g["kind"] == kind) & (np.isclose(g["L_s"], L)) & (np.isclose(g["gap_s"], gap))]
            return f"{_f(r['median_deg'].iloc[0])} / {_f(r['p90_deg'].iloc[0])} (n {int(r['n'].iloc[0])})" if len(r) else "n/a"
        w(f"| {n_} | {a_} | {cell('adjacent', 0.5, 0)} | {cell('adjacent', 1.0, 0)} | {cell('adjacent', 2.0, 0)} | {cell('bridged', 0.5, 1)} | {cell('bridged', 0.5, 2)} | {cell('bridged', 0.5, 5)} |")
    w("\nThe floor falls with window length as the acc noise averages out; the bridged variants add the still-drift of the calibrated gyro over the quiet gap.\n")
    # ---- 4 gyro
    w("## 4. 0b — Gyro self-calibration\n")
    cv = pd.DataFrame(S_["cv_table"])
    w("**Tuning-night CV (2–15 s no-sat bouts; held-out median tilt error, °):**\n")
    allm = list(cfg["gyro_fit"]["models"]) + list(cfg["gyro_fit"].get("exploratory_models", []))
    w("| animal | n | baseline 1.03 | " + " | ".join(allm) + " |\n|---|---|---|" + "---|" * len(allm))
    for a in animals:
        ga = cv[cv["animal"] == a].set_index("model")
        w(f"| {a} | {int(ga['n_fit_bouts'].iloc[0])} | {_f(ga.loc['baseline_1.03', 'cv_median_deg'])} | " + " | ".join(f"{_f(ga.loc[m, 'cv_median_deg'])} (train {_f(ga.loc[m, 'train_median_deg'])})" for m in allm) + " |")
    w(f"| pooled | | | " + " | ".join(f"**{_f(S_['pooled_cv'][m], 3)}**" for m in allm) + f" |\n\nSelected among the pre-registered models (scalar, diag, M, M_rate): **`{sel}`**. `scalar_gsens` / `M_gsens` (ω = M(w − b) + K a, K = gyro g-sensitivity) are **post-hoc exploratory** models added after the SF09 development run showed the drift rate correlating with linear acceleration; they never enter the selection or the gate.\n")
    w(f"**Fitted matrices (`{sel}`, tuning night; 95 % bootstrap CI):**\n")
    names = param_names(sel)
    w("| animal | " + " | ".join(names) + " |\n|---|" + "---|" * len(names))
    for a in animals:
        f = S_["fits"][a]
        th, lo, hi = np.asarray(f[sel]["theta"]), np.asarray(f["bootstrap_selected"]["lo"]), np.asarray(f["bootstrap_selected"]["hi"])
        w(f"| {a} | " + " | ".join(f"{th[i]:+.4f} [{lo[i]:+.4f}, {hi[i]:+.4f}]" for i in range(len(th))) + " |")
    w("\n**All fitted models per animal (tuning night; M − I entries row-major, then c or K row-major):**\n")
    w("| animal | model | parameters |\n|---|---|---|")
    for a in animals:
        for m in allm:
            if m in S_["fits"][a]:
                w(f"| {a} | {m} | " + ", ".join(f"{n} {v:+.4f}" for n, v in zip(param_names(m), S_["fits"][a][m]["theta"])) + " |")
    w("\n**Test night, bouts without gyro saturation — median (p90) tilt error in °, baseline → every model (held-out; `e_cal_norecon` = selected model on the clipped stream, `e_cal_shakefrozen` = (iii)):**\n")
    cols = ["e_baseline"] + [f"e_{m}" for m in allm] + ["e_cal_norecon", "e_cal_shakefrozen"]
    w("| animal | bin | n | " + " | ".join(c.replace("e_", "") for c in cols) + " |\n|---|---|---|" + "---|" * len(cols))
    for a in animals + ["pooled"]:
        for lab in labels:
            r = tt[(tt["animal"] == a) & (tt["dbin"] == lab)]
            if len(r) == 0:
                continue
            r = r.iloc[0]
            w(f"| {a} | {lab} | {int(r['n'])} | " + " | ".join(f"{_f(r[f'{c}_med'])} ({_f(r[f'{c}_p90'], 1)})" for c in cols) + " |")
    w("\n**Drift scaling after calibration (test night, no sat):**\n")
    w("| set | n | ρ(e, dur) | ρ(e, Θ) | ρ(dur, Θ) | ° per 100° med (p90) | °/s med (p90) | consistency | mean dir (head) | ρ(rate, HF gyr) | ρ(rate, HF acc) | ρ(rate, |a_h|) | ρ(e, ω_max) |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, d in list(S_["drift_scaling"].items()) + list(S_["drift_scaling_baseline"].items()):
        if d.get("n", 0) < 10:
            continue
        w(f"| {k} | {d['n']} | {_f(d['spearman_e_dur'])} | {_f(d['spearman_e_rot'])} | {_f(d['spearman_dur_rot'])} | {_f(d['deg_per_100deg_median'])} ({_f(d['deg_per_100deg_p90'])}) | {_f(d['deg_per_s_median'])} ({_f(d['deg_per_s_p90'])}) | {_f(d['error_vector_consistency'])} | {d['mean_error_dir_head']} | {_f(d['spearman_rate_hf_gyr'])} | {_f(d['spearman_rate_hf_acc'])} | {_f(d['spearman_rate_mean_ah'])} | {_f(d['spearman_e_wmax'])} |")
    w("\nAudit reference (SF09 / SF12, baseline): ρ(e, Θ) 0.70 / 0.45, ρ(e, dur) 0.41 / 0.33, 1.01 / 1.38 ° per 100°, 0.41 / 0.51 °/s, consistency 0.15 / 0.20.\n")
    # ---- 5 saturation
    w("## 5. 0c — Saturation\n")
    if len(cc):
        w("**Clipped gyro runs per animal-night and class:**\n")
        w("| night | animal | " + " | ".join(CLASSES) + " | total |\n|---|---|" + "---|" * (len(CLASSES) + 1))
        for r in cc.itertuples():
            w(f"| {r.night} | {r.animal} | " + " | ".join(str(int(getattr(r, c))) for c in CLASSES) + f" | {int(sum(getattr(r, c) for c in CLASSES))} |")
        w(f"\nRuns per lane (sensor lane 4 = head yaw z, 5 = head −x, 6 = head −y): {sat.get('per_lane')}. Duration (ms): median {_f(sat['dur_ms'].get('50%'))}, p90 {_f(sat['dur_ms'].get('90%'))}, p99 {_f(sat['dur_ms'].get('99%'))}, max {_f(sat['dur_ms'].get('max'))}. "
          f"Inter-run spacing histogram (edges {sat['spacing_hist']['edges_ms']} ms): {sat['spacing_hist']['counts']} of {sat['spacing_hist']['n']} runs with a predecessor. "
          f"Median |a|_max by class (g): " + ", ".join(f"{k} {_f(v)}" for k, v in sat["acc_max_g_by_class"].items()) + "; median $W_{acc}$ by class: " + ", ".join(f"{k} {_f(v)}" for k, v in sat["acc_hf_frac_by_class"].items()) + ".")
        st = sat["shake_trains"]
        w(f"\n**Shake trains:** {st['n_trains']} trains (median size {_f(st['size_median'], 0)} runs), |net angle| over the train median {_f(st['net_deg_abs_median'])}° (p90 {_f(st['net_deg_abs_p90'])}°), fraction with |a| > 2 g {_f(st['frac_acc_gt_2g'])}. "
          f"**Suspect monotone runs:** {sat['suspect']['n']} (median |net| {_f(sat['suspect']['net_deg_abs_median'])}°), by animal {sat['suspect']['by_animal']} — SF12 (loosening contact on shanks 1/4 from 09-10 afternoon) is to be compared with the others here. "
          f"**Reconstruction:** {sat['recon']['n_recon']} runs reconstructed, {sat['recon']['n_failed']} failed (shoulders not clean or fit rejected); missing angle median {_f(sat['recon']['missing_deg_median'])}° (p90 {_f(sat['recon']['missing_deg_p90'])}°); reconstructed peak median {_f(sat['recon']['peak_dps_median'], 0)} °/s (p90 {_f(sat['recon']['peak_dps_p90'], 0)}).\n")
    sb = sat.get("sat_bouts")
    if sb:
        w("**Bouts containing gyro saturation (both nights, all animals) — median tilt error (°) per treatment:**\n")
        w("| bouts containing | n | clipped (A3 baseline) | (i) clipped + M | (ii) reconstructed + M (A4) | (iii) + frozen across shakes |\n|---|---|---|---|---|---|")
        for r in sb:
            w(f"| {r['contains']} | {r['n']} | {_f(r['e_baseline'])} | {_f(r['e_cal_norecon'])} | {_f(r['e_cal'])} | {_f(r['e_cal_shakefrozen'])} |")
        w("")
    om = pd.DataFrame(S_["omega_distribution"])
    w("**Head angular speed (calibrated 100-Hz |ω|, °/s) by activity, against the literature (voluntary head-turn peak ≈ 500 °/s and ambulation SD ≈ 107 °/s, Pasquet 2016; immobility < 12–20 °/s; shakes/twitches > 1000–2000 °/s for tens of ms):**\n")
    w("| night | animal | active p50 | p90 | p99 | p99.9 | p99.99 | max | active SD | quiet p50 | quiet p99 | max raw unclipped | active s with sat | sat fraction |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in om.itertuples():
        w(f"| {r.night} | {r.animal} | {_f(r.active_p50, 0)} | {_f(r.active_p90, 0)} | {_f(r.active_p99, 0)} | {_f(getattr(r, 'active_p99_9', np.nan), 0)} | {_f(getattr(r, 'active_p99_99', np.nan), 0)} | {_f(r.active_max, 0)} | {_f(r.active_sd, 0)} | {_f(r.quiet_p50, 1)} | {_f(r.quiet_p99, 1)} | {_f(r.unclipped_raw_max_dps, 0)} | {_f(r.frac_active_sec_with_sat * 100, 2)} % | {_f(r.sat_frac_gyr_raw * 100, 3)} % |")
    w("\nGrooming, scratching and shaking epochs are not excluded anywhere in Phase 0; the body is stationary in them, so a translation filter should treat them as zero-velocity states (the A4 `shake` flag and the 4–20 Hz band powers mark them).\n")
    # ---- 6 A4
    w("## 6. 0d — Attitude pipeline and the A4 cache\n")
    if S_["a4"]:
        w("| animal / night | samples (16 Hz) | MB | quiet-tilt check (median °) |\n|---|---|---|---|")
        for k, v in S_["a4"].items():
            w(f"| {k} | {v['n16']} | {v['bytes'] / 1e6:.1f} | {_f(v['quiet_tilt_check_deg'])} |")
    au = pd.DataFrame(S_.get("a4_usability", []))
    if len(au):
        w("\n**Where f_xy is trustworthy (descriptive).** Gravity aiding happens only in quiet samples, so the tilt uncertainty grows with `t_active`; a tilt error δθ leaks g·sin δθ into f_xy. Fraction of 16-Hz samples per `t_active` band, with the median |f_xy_2hz| (m/s²) and median σ_θ (°) in the band:\n")
        w("| animal / night | still | t_active < 2 s | 2–5 s | 5–15 s | 15–60 s | ≥ 60 s | σ_θ median (all) |\n|---|---|---|---|---|---|---|---|")
        for r in au.itertuples():
            cells = []
            for tag in ("0_2", "2_5", "5_15", "15_60", "60_inf"):
                cells.append(f"{100 * getattr(r, f'frac_t{tag}'):.0f} % · |f| {_f(getattr(r, f'fxy_med_t{tag}'), 2)} · σ {_f(getattr(r, f'sigma_med_t{tag}'), 1)}")
            w(f"| {r.animal} / {r.night} | {100 * r.frac_still:.0f} % | " + " | ".join(cells) + f" | {_f(r.sigma_median_deg, 1)} |")
        w("\nReading: without WISER (or any other) aiding, the pure-IMU horizontal specific force is only meaningful within a few seconds of a quiet window; over most of an active night it is dominated by gravity leakage — which is precisely why σ_θ is stored per sample and why this cache is an input to a fusion, not a result.\n")
    w(f"\nFormat (also in `{cfg['cache_roots']['imu16']}/README.md`): `t_unix_ms` (IMU clock, τ* not applied; grid j ↔ 100-Hz sample 6.25 j); `f_xy_2hz` / `f_xy_1hz` / `f_xy_4hz` float32 (n, 2) m/s² world-frame horizontal specific force, gravity removed — **yaw arbitrary (0 at the night start) but continuous**; `f_z_2hz`; `q_wh` float32 (n, 4) [w, x, y, z], v_world = R(q) v_head, nearest 100-Hz sample; `sigma_theta_deg` (per-axis SD of the tilt error at the sample's `t_active_s`, law A) and `p90_theta_deg`; flags `still`, `dyn`, `sat`, `recon`, `shake`, `frozen`, `invalid` (any within the 62.5-ms support); band powers `bp_w_<lo>_<hi>`, `bp_a_<lo>_<hi>` for 2–4, 4–8, 8–12, 12–20 Hz; `calib_json` (M, c, acc ellipsoid, all parameters, growth laws, sources, git) and `meta_json`. Gravity aiding happens only in quiet samples (τ = 0.25 s); there is no dynamic pull. A tilt error δθ biases f_xy by g·sin δθ (1° = 0.17 m/s²).\n")
    # ---- 7 growth
    w("## 7. 0e — Attitude-error growth law\n")
    gt = pd.DataFrame(S_["growth"]["table"])
    w("| t bin (s) | t mid | n | median e (°) | p90 e (°) |\n|---|---|---|---|---|")
    for r in gt.itertuples():
        w(f"| {r.t_lo:g}–{r.t_hi:g} | {r.t_mid:.1f} | {r.n} | {_f(r.med)} | {_f(r.p90)} |")
    Bl, P9 = S_["growth"]["B"], S_["growth"]["p90"]
    w(f"\n**A (adopted, written into A4):** σ_θ(t) = sqrt({_f(A['sigma0_deg'], 3)}² + ({_f(A['k_deg_per_s'], 4)}·t)²) °, R² {_f(A['r2'])}. **B:** σ_θ = {_f(Bl['sigma0_deg'], 3)} + {_f(Bl['k_deg_per_s'], 4)}·t, R² {_f(Bl['r2'])}. **p90 envelope:** sqrt({_f(P9['p0_deg'])}² + ({_f(P9['k90_deg_per_s'], 4)}·t)²) °. "
      f"Baseline chain for comparison: σ₀ {_f(S_['growth']['baseline_A']['sigma0_deg'], 3)}, k {_f(S_['growth']['baseline_A']['k_deg_per_s'], 4)} °/s. Per animal (A: σ₀, k): " + "; ".join(f"{a} {_f(v['A']['sigma0_deg'])}, {_f(v['A']['k_deg_per_s'], 3)}" for a, v in S_["growth"]["per_animal"].items()) + ".\n")
    # ---- 8 gate
    w("## 8. GATE (pre-registered)\n")
    w("| bin | threshold | pooled median (95 % CI) | n | baseline | excess over floor | pass |\n|---|---|---|---|---|---|---|")
    for lab, v in gate["bins"].items():
        w(f"| {lab} | ≤ {v['threshold_deg']}° | {_f(v['pooled_median_deg'])} ({_f(v['ci95'][0])}–{_f(v['ci95'][1])}) | {v['n']} | {_f(v['baseline_median_deg'])} | {_f(v['excess_over_floor_deg'])} | {'yes' if v['pooled_pass'] else 'no'} |")
    w("\n| animal | 2–5 s median (n) | 5–15 s median (n) | passes both |\n|---|---|---|---|")
    for a, v in gate["animals"].items():
        w(f"| {a} | {_f(v['2-5 s']['median_deg'])} ({v['2-5 s']['n']}) | {_f(v['5-15 s']['median_deg'])} ({v['5-15 s']['n']}) | {'yes' if v['pass_both'] else 'no'} |")
    w(f"\n**Verdict: {gate['verdict']}** ({gate['n_animals_pass']}/{gate['n_animals']} animals; floor {_f(gate['floor_median_deg'])}°). The thresholds were not moved.\n")
    pe = gate.get("posthoc_edge_still", {})
    if pe:
        w(f"**Post-hoc diagnostic (not the gate; declared in the plan amendment after the SF09 development pass):** the registered test propagates the gyro only across the non-quiet samples, while its two 0.5-s gravity windows sit in *quiet* seconds that may still contain slow head motion (≤ 10 °/s median). Over the test-night gate bouts the integrated |ω| inside the two edge windows (`edge_rot_deg`) has a median of {_f(gate.get('edge_rot_median_deg'))}° and correlates with the tilt error at Spearman {_f(gate.get('spearman_e_edge_rot'))}. Restricting to bouts whose edge windows are still:\n")
        w("| subset | n | 2–5 s median (baseline) n | 5–15 s median (baseline) n | animals passing both (≥ 5 bouts per bin) | per-animal 2–5 s | per-animal 5–15 s |\n|---|---|---|---|---|---|---|")
        for k, d in pe.items():
            b1, b2 = d["bins"]["2-5 s"], d["bins"]["5-15 s"]
            w(f"| {k} | {d['n']} | {_f(b1['pooled_median_deg'])} ({_f(b1['baseline_median_deg'])}) {b1['n']} | {_f(b2['pooled_median_deg'])} ({_f(b2['baseline_median_deg'])}) {b2['n']} | {d['animals_pass_both']} | "
              + ", ".join(f"{a} {_f(v)}" for a, v in b1["per_animal_median_deg"].items()) + " | " + ", ".join(f"{a} {_f(v)}" for a, v in b2["per_animal_median_deg"].items()) + " |")
        w(f"\n**Confound:** the bouts with < 2° of edge motion are themselves nearly motionless (median total rotation {_f(pe.get('edge_rot_lt_2deg', {}).get('rot_deg_median'))}° vs {_f(np.median([r['rot_low_median'] for r in gate.get('posthoc_matched', [])]) if gate.get('posthoc_matched') else np.nan)}–{_f(np.median([r['rot_high_median'] for r in gate.get('posthoc_matched', [])]) if gate.get('posthoc_matched') else np.nan)}° in the gate bouts), so their tiny error is not evidence about active bouts. The matched comparison below controls for activity: within each bin of total rotation Θ, bouts are split at the bin's median edge motion.\n")
        w("| Θ bin (°) | n | edge motion median (°) | e median, low-edge half | e median, high-edge half | Spearman(edge, e) within bin | Θ median low / high |\n|---|---|---|---|---|---|---|")
        for r in gate.get("posthoc_matched", []):
            w(f"| {r['rot_bin_deg']} | {r['n']} | {_f(r['edge_rot_median_deg'], 1)} | {_f(r['e_low_edge_median'])} | {_f(r['e_high_edge_median'])} | {_f(r['spearman_edge_e_within'])} | {_f(r['rot_low_median'], 0)} / {_f(r['rot_high_median'], 0)} |")
        ll = gate.get("posthoc_loglog", {})
        w(f"\nLog-log regression over the gate bouts: $e \\propto \\Theta^{{{_f(ll.get('exp_rot'))}}}\\,\\mathrm{{edge}}^{{{_f(ll.get('exp_edge'))}}}\\,T^{{{_f(ll.get('exp_dur'))}}}$ — motion inside the two 0.5-s gravity windows is the strongest single predictor of the test's error; duration adds nothing once rotation and edge motion are in.\n")
        w("| bin | edge-motion tertile | n | e median (baseline) | Θ median (°) | edge motion median (°) |\n|---|---|---|---|---|---|")
        for r in gate.get("posthoc_tertiles", []):
            w(f"| {r['dbin']} | {r['edge_tertile']} | {r['n']} | {_f(r['e_median'])} ({_f(r['e_baseline_median'])}) | {_f(r['rot_median'], 0)} | {_f(r['edge_rot_median'], 1)} |")
        w("\nReading: the registered verdict stands (the pre-registered floor criterion — excess over the 0.05° floor < 0.5° — is not met). But the error the test reports is carried to a large part by head motion inside its own \"quiet\" gravity windows, which the audit's construction does not propagate; the pre-registered floor (adjacent windows inside long quiet runs) does not capture it. A Phase-1 gate must either propagate the gyro through the edge windows (compare with de-rotated accelerometer means) or require the edge windows to be still (edge motion < ~2°) with enough such bouts.\n")
    # ---- 9 prior work
    w("## 9. Prior work used (coordinator's literature audit, 2026-09-30)\n")
    w("- Pasquet et al. 2016, *Sci Rep* (https://www.nature.com/articles/srep35689): voluntary rat head turns peak ≈ 500 °/s, 30–50°; free ambulation SD|ω| ≈ 107 °/s; immobility < 12–20 °/s; 2 Hz is the validated gravity/tilt band (also Fayat et al. 2021).")
    w("- Dickerson et al. 2012 (https://pubmed.ncbi.nlm.nih.gov/22904256/): wet-dog shakes 14–18 Hz; DISSeCT 2025, *PLOS Biol* (https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3003431): > 1000 °/s and > 2 g in rats; Halberstadt & Geyer 2013: head twitches 30–40 Hz; scratching 7–12 Hz; marmoset > 1000 °/s, lovebird saccades up to 2700 °/s in 30–45 ms.")
    w("- MEMS gyros cancel common-mode linear shocks; a loosening headstage produces genuine sensor rotation the skull does not share (→ `suspect_monotone`).")
    w("- The 2–20 Hz band (locomotion 4–8, grooming ≈ 4, sniffing 8–12, shakes 14–18 Hz) is behaviour: band powers in A4, never integrated.\n")
    # ---- 10 caveats / deviations / verification
    w("## 10. Caveats, deviations, verification\n")
    w("- The tilt error is measured against 0.5-s accelerometer means in quiet seconds; the floor (§3) is part of every number, and cross-orientation accelerometer-calibration residuals (≈ 0.1°) are not in the floor.")
    w("- The `quiet` flag has 1-s granularity, so a bout's true activity may start/stop up to 1 s inside the quiet seconds at ≤ 10 °/s median rate.")
    w("- Yaw in A4 is arbitrary per night; f_xy axes are an unknown rotation of the paddock frame and drift with the residual bias (still-run drift ≈ 2.3 °/min from V4).")
    w("- Bias b is the A3 running median (not refitted); M multiplies (w − b), so a bias error propagates as M·δb.")
    w("- The growth law is fitted on the test night as pre-registered (a descriptive uncertainty, not a tuning parameter for the gate); A4 covers both nights with it.")
    w("- **Deviations from the plan as first written (all before any real-data run):** the saturation section was amended after the literature audit (train-structure classes, log-quadratic instead of quadratic reconstruction after a synthetic prototype, treatments (i)–(iii), band powers in A4); the plan carries the amendment. Others, if any, are listed in the change log.")
    w(f"- **Verification:** the Phase-0 gyro chain (Hampel → 40-Hz Butterworth-4 → resample_poly 2/25 → head frame) is A3's chain, so the bias is taken exactly as A3 applied it (b = w − gyr_A3/1.03); the 1-min bias nodes stored in A3 would have been off by up to {max(S_['chain_check'].values()):.2e} °/s (median over nights of the per-night max); `--selftest` on synthetic data (known M and rate term recovered, saturation classes and missing angle, floor, attitude pipeline, growth-law fit) passes; no raw file, cache or earlier script was modified.\n")
    p = rdir / f"{STEM}_{cohort}.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


# ====================================================================================================== self-test
def _smooth_noise(rng, n: int, fs: float, fc: float, ncol: int = 3) -> np.ndarray:
    x = rng.standard_normal((n + 400, ncol))
    sos = signal.butter(2, fc, fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x, axis=0)[200:200 + n]


def _synth_boutset(rng, n_bouts: int, Mx: np.ndarray, c: float, cfg: dict, noise_deg: float = 0.3, dur_range=(2.0, 10.0), amp_range=(60.0, 200.0), K=None) -> BoutSet:
    """Bouts whose 'measured' (w - b) is smooth random rotation; the true rate is model(w - b) (+ K a); g_end from the truth + noise."""
    wbs, accs, gs, ge, bouts = [], [], [], [], []
    pos = 0
    for i in range(n_bouts):
        n = int(rng.uniform(*dur_range) * FS100)
        wb = _smooth_noise(rng, n, FS100, 1.5) * rng.uniform(*amp_range)
        acc = _smooth_noise(rng, n, FS100, 2.0) * 15.0 + np.array([0.0, 0.0, G])
        accs.append(acc)
        g0 = rng.standard_normal(3); g0 /= np.linalg.norm(g0)
        out = np.empty((1, 3))
        propagate_bouts(g0[None, :], apply_model(wb, Mx, c, cfg, acc, K), np.array([0, n], np.int64), 1.0 / FS100, out)
        gend = out[0]
        # noise: rotate by a random small angle
        ax = rng.standard_normal(3); ax -= ax @ gend * gend; ax /= np.linalg.norm(ax)
        th = np.deg2rad(rng.rayleigh(noise_deg / 1.1774))
        gend = gend * math.cos(th) + ax * math.sin(th)
        wbs.append(wb); gs.append(g0); ge.append(gend); bouts.append((pos, pos + n)); pos += n
    bs = BoutSet.__new__(BoutSet)
    bs.bouts = np.asarray(bouts); bs.n = n_bouts
    bs.offs = np.r_[0, np.cumsum(bs.bouts[:, 1] - bs.bouts[:, 0])].astype(np.int64)
    bs.wb = np.concatenate(wbs); bs.acc = np.concatenate(accs); bs.gs = np.asarray(gs); bs.ge = np.asarray(ge)
    return bs


def selftest() -> int:
    cfg = json.loads((REPO / "wiser" / "configs" / "imu_attitude_phase0_2026c.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(7)
    fails = []
    t0 = time.time()

    def check(name, ok, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")
        if not ok:
            fails.append(name)
    print("self-test 1: gyro matrix + rate term recovery on synthetic bouts")
    E_true = np.array([[0.031, -0.012, 0.020], [0.008, 0.045, -0.015], [-0.018, 0.010, 0.025]])
    M_true = np.eye(3) + E_true
    bs = _synth_boutset(rng, 220, M_true, 0.0, cfg)
    r = fit_model("M", bs, cfg)
    check("M recovered (|E_hat - E| < 0.005)", np.abs(r["M"] - M_true).max() < 0.005, f"max dev {np.abs(r['M'] - M_true).max():.4f}")
    e_before = np.median(bout_errors(bs, 1.03 * np.eye(3), 0.0, cfg)[0]); e_after = np.median(bout_errors(bs, r["M"], r["c"], cfg)[0])
    check("post-calibration error at the injected noise (0.3 deg)", e_after < 0.4 and e_after < e_before, f"median before {e_before:.2f} -> after {e_after:.2f} deg")
    c_true = 0.06
    bs2 = _synth_boutset(rng, 220, M_true, c_true, cfg, amp_range=(300.0, 900.0))
    r2 = fit_model("M_rate", bs2, cfg)
    check("rate term recovered (|c_hat - c| < 0.02)", abs(r2["c"] - c_true) < 0.02 and np.abs(r2["M"] - M_true).max() < 0.01, f"c_hat {r2['c']:.3f}, max |dE| {np.abs(r2['M'] - M_true).max():.4f}")
    K_true = np.array([[0.02, -0.01, 0.0], [0.005, 0.03, -0.02], [0.0, 0.01, -0.015]])
    bs3 = _synth_boutset(rng, 220, M_true, 0.0, cfg, amp_range=(100.0, 400.0), K=K_true)
    r3 = fit_model("M_gsens", bs3, cfg)
    check("exploratory g-sensitivity K recovered (|K_hat - K| < 0.01 (deg/s)/(m/s^2))", np.abs(r3["K"] - K_true).max() < 0.01 and np.abs(r3["M"] - M_true).max() < 0.01,
          f"max |dK| {np.abs(r3['K'] - K_true).max():.4f}, max |dE| {np.abs(r3['M'] - M_true).max():.4f}")
    th = bootstrap_fit("M", bs.take(np.arange(60)), {**cfg, "gyro_fit": {**cfg["gyro_fit"], "n_bootstrap": 8}}, r["theta"])
    check("bootstrap runs and brackets the truth", th.shape == (8, 9) and (np.percentile(th, 2.5, axis=0) <= E_true.ravel() + 0.005).all(), f"CI half-width max {(np.percentile(th, 97.5, axis=0) - np.percentile(th, 2.5, axis=0)).max() / 2:.4f}")
    print("self-test 2: saturation classes and reconstruction")
    n = int(20 * FS_RAW)
    t = np.arange(n) / FS_RAW
    six = np.zeros((n, 6), np.float64)
    six[:, 2] = G / ACC_SCALE + rng.normal(0, 5, n); six[:, :2] = rng.normal(0, 5, (n, 2)); six[:, 3:] = rng.normal(0, 8, (n, 3))
    P, s = 2600.0 / GYR_SCALE, 0.006
    six[:, 3] += P * np.exp(-(t - 3.0) ** 2 / (2 * s ** 2))                       # (a) isolated pulse, lane 4
    tr = (t >= 8.0) & (t < 8.4)
    six[tr, 3] += (2800.0 / GYR_SCALE) * np.sin(2 * np.pi * 15 * (t[tr] - 8.0))   # (b) 15-Hz shake train
    six[tr, 0] += (3.0 * G / ACC_SCALE) * np.sin(2 * np.pi * 15 * (t[tr] - 8.0))
    k13 = int(13.0 * FS_RAW)
    six[k13, 4] = 32767; six[k13, 1] += 4 * G / ACC_SCALE                          # (c) 1-sample spike + broadband acc
    k16 = int(16.0 * FS_RAW)
    six[k16:k16 + 10, 5] = 32767; six[k16 + 2:k16 + 5, 0] = 32767                   # (d) run coincident with acc clipping
    truth_missing = float(np.maximum(six[:, 3] - 32700, 0)[(t > 2.9) & (t < 3.1)].sum()) * GYR_SCALE / FS_RAW
    # (e) the same isolated pulse but sample-and-hold at the measured ~190 Hz (hold 7 samples), at t = 18 s on lane 4
    hold = 7
    pulse = P * np.exp(-(t - 18.0) ** 2 / (2 * s ** 2))
    k0, k1 = int(17.0 * FS_RAW), int(19.0 * FS_RAW)
    seg = six[k0:k1, 3] + pulse[k0:k1]
    idx_h = (np.arange(k1 - k0) // hold) * hold
    six[k0:k1, 3] = seg[idx_h]                                                     # reading (pulse + noise) held over 7 samples
    truth_missing_h = float(np.maximum(six[k0:k1, 3] - 32700, 0).sum()) * GYR_SCALE / FS_RAW
    six_i = np.clip(np.round(six), -32767, 32767).astype(np.int16)
    sat = np.abs(six_i.astype(np.int32)) >= 32700
    R = saturation_runs(six_i, sat, lambda idx: np.asarray(idx, float) / FS_RAW * 1000, cfg)
    xg = six_i[:, 3:6].astype(np.float32)
    R = reconstruct_runs(xg, R, sat[:, 3:6], cfg)
    ra = R[(R["lane"] == 4) & (R["t_unix_ms"] > 2800) & (R["t_unix_ms"] < 3200)]
    check("isolated pulse -> rotation, reconstructed", len(ra) == 1 and ra["cls"].iloc[0] == "rotation" and bool(ra["recon"].iloc[0]), f"{ra[['cls', 'n', 'recon', 'peak_dps', 'missing_deg', 'net_deg_pm25ms']].to_dict('records')}")
    if len(ra) == 1:
        check("missing angle within 25 %", abs(ra["missing_deg"].iloc[0] / truth_missing - 1) < 0.25, f"recovered {ra['missing_deg'].iloc[0]:.2f} vs truth {truth_missing:.2f} deg")
    re_ = R[(R["lane"] == 4) & (R["t_unix_ms"] > 17800) & (R["t_unix_ms"] < 18200)]
    check("sample-and-hold pulse (hold 7) -> reconstructed on held readings, missing angle within 25 %",
          len(re_) == 1 and bool(re_["recon"].iloc[0]) and abs(re_["missing_deg"].iloc[0] / truth_missing_h - 1) < 0.25,
          f"{re_[['cls', 'n', 'n_readings', 'recon', 'peak_dps', 'missing_deg']].to_dict('records')} truth {truth_missing_h:.2f} deg")
    rb = R[(R["lane"] == 4) & (R["t_unix_ms"] >= 7900) & (R["t_unix_ms"] < 8500)]
    check("15-Hz alternating train -> shake_train, near-zero net", len(rb) >= 8 and (rb["cls"] == "shake_train").all() and abs(rb["train_net_deg"].iloc[0]) < 5,
          f"{len(rb)} runs, classes {set(rb['cls'])}, net {rb['train_net_deg'].iloc[0] if len(rb) else np.nan:.2f} deg, spacing {rb['gap_prev_ms'].median() if len(rb) else np.nan:.1f} ms")
    rc = R[(R["lane"] == 5)]
    check("1-sample spike + broadband acc -> short_broadband", len(rc) == 1 and rc["cls"].iloc[0] == "short_broadband", f"{rc[['cls', 'n', 'acc_hf_frac']].to_dict('records')}")
    rd = R[(R["lane"] == 6)]
    check("run coincident with acc clipping -> impact", len(rd) == 1 and rd["cls"].iloc[0] == "impact", f"{rd[['cls', 'n', 'acc_sat']].to_dict('records')}")
    print("self-test 3: measurement floor")
    sig = 0.05
    acc = np.tile([0.0, 0.0, G], (int(600 * FS100), 1)) + rng.normal(0, sig, (int(600 * FS100), 3))
    L = 50
    ang = floor_pairs(acc, np.ones(len(acc), bool), L)
    theo = 1.1774 * math.sqrt(2) * sig / (G * math.sqrt(L)) * R2D
    check("floor median matches Rayleigh theory within 15 %", abs(np.median(ang) / theo - 1) < 0.15, f"measured {np.median(ang):.3f} vs theory {theo:.3f} deg (n {len(ang)})")
    print("self-test 4: attitude pipeline (tilt tracking, f_xy recovery, quiet aiding)")
    n = int(60 * FS100)
    tt = np.arange(n) / FS100
    w_true = _smooth_noise(rng, n, FS100, 0.5) * 40.0
    w_true[(tt < 5) | (tt > 55) | ((tt > 28) & (tt < 32))] = 0.0
    q = np.array([1.0, 0, 0, 0]); qs = np.empty((n, 4))
    for k in range(n):
        q = np.asarray(_qmul(tuple(q), _qexp(*(np.deg2rad(w_true[k]) / FS100)))); q /= np.linalg.norm(q); qs[k] = q
    a_world = np.zeros((n, 3)); m = (tt >= 12) & (tt < 26)
    a_world[m, 0] = 1.0 * np.sin(2 * np.pi * 1.0 * tt[m])
    Rw = np.stack([np.asarray(_g_head(tuple(qq))) for qq in qs])   # R^T e_z
    # head-frame specific force = R^T (g e_z + a_world)
    acc_h = np.empty((n, 3))
    for k in range(n):
        w_, x_, y_, z_ = qs[k]
        Rm = np.array([[1 - 2 * (y_ * y_ + z_ * z_), 2 * (x_ * y_ - w_ * z_), 2 * (x_ * z_ + w_ * y_)], [2 * (x_ * y_ + w_ * z_), 1 - 2 * (x_ * x_ + z_ * z_), 2 * (y_ * z_ - w_ * x_)], [2 * (x_ * z_ - w_ * y_), 2 * (y_ * z_ + w_ * x_), 1 - 2 * (x_ * x_ + y_ * y_)]])
        acc_h[k] = Rm.T @ (np.array([0, 0, G]) + a_world[k])
    acc_h += rng.normal(0, 0.03, acc_h.shape)
    quiet = (tt < 5) | (tt > 55) | ((tt > 28) & (tt < 32))
    w_meas = np.deg2rad(w_true) + np.deg2rad(0.3) * rng.standard_normal((n, 3)) * 0.0 + np.deg2rad(2.0 / 60.0)  # 2 deg/min bias
    qo = np.empty((n, 4)); ta = np.empty(n)
    integrate_attitude(w_meas, acc_h, quiet, np.zeros(n, bool), 1.0 / FS100, (1.0 / FS100) / 0.25, q_from_up(acc_h[:100].mean(axis=0)), qo, ta)
    tilt = angle_deg(np.stack([np.asarray(_g_head(tuple(qq))) for qq in qo]), Rw)
    check("tilt tracked within 1 deg (median) with a 2 deg/min bias and quiet-only aiding", np.median(tilt) < 1.0 and np.percentile(tilt, 95) < 3.0, f"median {np.median(tilt):.2f}, p95 {np.percentile(tilt, 95):.2f} deg; t_active max {ta.max():.1f} s")
    f_w = rotate_world(qo, acc_h); f_w[:, 2] -= G
    sos = signal.butter(4, 2.0, fs=FS100, output="sos")
    lp = signal.sosfiltfilt(sos, f_w, axis=0)
    amp = np.sqrt(2) * lp[m, 0].std()
    check("1-Hz horizontal acceleration recovered in f_xy_2hz within 10 %", abs(amp - 1.0) < 0.10, f"amplitude {amp:.3f} m/s^2; off-axis rms {lp[m, 1].std():.3f}")
    check("yaw continuous (no jump > 5 deg between samples)", np.all(np.abs(np.diff(np.degrees(2 * np.arctan2(qo[:, 3], qo[:, 0])))) % 360 < 5), "")
    print("self-test 5: growth-law fit")
    dur = rng.uniform(2, 90, 3000); s0, k = 0.4, 0.15
    err = rng.rayleigh(np.sqrt(s0 ** 2 + (k * dur) ** 2))
    gl = fit_growth(dur, err, 1.1774 * s0, 500, cfg)
    check("sigma0 and k recovered", abs(gl["A"]["sigma0_deg"] - s0) < 0.1 and abs(gl["A"]["k_deg_per_s"] / k - 1) < 0.2, f"sigma0 {gl['A']['sigma0_deg']:.3f} (0.4), k {gl['A']['k_deg_per_s']:.3f} (0.15), R2 {gl['A']['r2']:.3f}")
    print(f"self-test: {'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({time.time() - t0:.0f} s)")
    return 0 if not fails else 1


# ====================================================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--no-a4", action="store_true", help="skip writing the A4 cache")
    ap.add_argument("--report-only", default=None, help="run dir: regenerate figures + report from summary.json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    cfg_path = Path(args.config) if args.config else REPO / "wiser" / "configs" / f"imu_attitude_phase0_{args.cohort}.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["_cohort"] = args.cohort
    animals = args.animals or cfg["animals"]
    if args.report_only:
        out = Path(args.report_only)
        S_ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        fh = None
        if not S_.get("a4_usability") and S_.get("a4"):
            S_["a4_usability"] = a4_usability(cfg, S_["animals"])
            pd.DataFrame(S_["a4_usability"]).to_csv(out / "a4_usability.csv", index=False)
            (out / "summary.json").write_text(json.dumps(S_, indent=1, default=_jd), encoding="utf-8")
    else:
        out = output_paths.run_dir(NAME, args.cohort)
        fh = open(out / "log.txt", "a", encoding="utf-8")
        log(f"run dir {out}; animals {animals}; config {cfg_path}; git {EC.git_commit()}", fh)
        S_ = run_analysis(cfg, out, animals, not args.no_a4, fh)
        log(f"analysis done in {S_['runtime_s'] / 60:.1f} min", fh)
    fig_dir = output_paths.figure_dir(args.cohort, DIRECTION)
    figs = make_figures(S_, out, fig_dir, args.cohort)
    for f in figs:
        import shutil
        shutil.copy2(fig_dir / f, out / "figures" / f)
    rdir = output_paths.report_dir(args.cohort, DIRECTION)
    rp = write_report(S_, figs, out, rdir, args.cohort, cfg)
    meta = {"cohort": args.cohort, "direction": DIRECTION, "analysis": NAME, "report": rp.name, "driver": "wiser/scripts/analyze_imu_attitude_phase0.py",
            "config": str(cfg_path.relative_to(REPO)).replace("\\", "/"), "git_commit": S_["git_commit"], "runtime_s": S_["runtime_s"],
            "caches": {"imu_raw": cfg["cache_roots"]["imu_raw"], "imu100": cfg["cache_roots"]["imu100"], "imu16": cfg["cache_roots"]["imu16"]},
            "gate": S_["gate"]["verdict"], "selected_model": S_["selected_model"], "figures": figs}
    output_paths.write_run_manifest(out, out, **meta)
    (rdir / f"run_manifest_{NAME}_{args.cohort}.json").write_text(json.dumps({"run_dir": str(out), **meta}, indent=2), encoding="utf-8")
    log(f"report {rp}; figures {figs}", fh)
    if fh:
        fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
