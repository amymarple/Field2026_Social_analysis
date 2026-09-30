r"""Head-IMU inertial fusion with WISER (V4): Phase B (IMU quality + physical smoothing -> A3 100-Hz cache) and Phase C
(6-axis error-state Kalman filter + RTS smoother with WISER, ZUPT/ZARU/gravity updates, initial-yaw hypotheses and a
mirrored-frame handedness test), scored exactly like the smoothing pilot.

Plan: implementation_plan/2026-09-29-wiser-ins-fusion.md (approved by the user 2026-09-29).
Report (full Definitions): results/<cohort>/wiser_baseline/reports/wiser_baseline_ins_fusion_<cohort>.md

Inputs (all read-only): the Phase-A caches (wiser/scripts/build_imu_wiser_cache.py: A1 raw IMU windows, A2 WISER fixes),
the make_imu 50-Hz npz (only for the smoothing pilot's per-second IMU QC/still classes, so the scored set is identical),
the smoothing pilot's config (nights, tau*, seed, masks, anchor-noise table, B1/B2/B2' tuned values). Reused unmodified
by import: ephys/make_imu.py (S, calibrate, fuse, pc_time_ms), analyze_wiser_imu_smoothing.py (Track, hidden sets,
predict_all, boot_delta, track_metrics), analyze_imu_wiser_calibration.py (masks, helpers).

Writes: A3 cache <imu100>/<SFxx>/night_<YYYYMMDD>.npz; bulk run dir <OUT>/<cohort>/wiser_ins_fusion_<ts>/; report, figures,
run_manifest_ins_fusion_<cohort>.json; the tuned block of wiser/configs/wiser_ins_fusion_<cohort>.json.

Usage:
  python wiser/scripts/analyze_wiser_ins_fusion.py --cohort 2026c [--threads 20] [--workers 5]
  python wiser/scripts/analyze_wiser_ins_fusion.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import analyze_imu_wiser_calibration as C  # noqa: E402  (calibration pilot: masks, helpers; unmodified)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (smoothing pilot: Track, scoring, B1/B2/B2'; unmodified)
import build_imu_wiser_cache as BC  # noqa: E402  (Phase A cache readers)
from cohorts import load_cohort  # noqa: E402
import read_imu as RI  # noqa: E402  (layout constants)
import make_imu as MI  # noqa: E402  (S, calibrate, fuse, pc_time_ms, frozen_mask; unmodified)

try:
    from numba import njit, prange, set_num_threads
    HAVE_NUMBA = True
except Exception:  # noqa: BLE001
    HAVE_NUMBA = False
    prange = range

    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

    def set_num_threads(n):  # noqa: ARG001
        return None

DIRECTION = "wiser_baseline"
NAME = "wiser_ins_fusion"
STEM = f"{DIRECTION}_ins_fusion"
G = MI.G                                   # 9.81 m/s^2 (make_imu)
IN_PER_M = 39.37007874
FS_RAW, FS100 = RI.FS_IMU, 100.0
ACC_SCALE = RI.ACC_FS_G * RI.G / 32768     # m/s^2 per count
GYR_SCALE = RI.GYR_FS_DPS / 32768          # deg/s per count
D2R = math.pi / 180.0


# ====================================================================================================== Phase B
@njit(parallel=True, cache=True)
def _hampel_lanes(x, sat, h, nsig, floor, out, flag):
    """Hampel filter per column: |x_i - med| > nsig * max(1.4826 MAD, floor[l]) over the (2h+1) window -> replaced by the
    median. Saturated samples are never replaced. x, out float32 (n, L); sat, flag bool (n, L); floor (L,) = the lane's
    global noise SD (a 7-sample MAD alone is too noisy a scale: pure noise would be flagged ~3e-3 of the time)."""
    n, L = x.shape
    m = 2 * h + 1
    for l in prange(L):
        w = np.empty(m, np.float32)
        d = np.empty(m, np.float32)
        for i in range(n):
            xi = x[i, l]
            out[i, l] = xi
            flag[i, l] = False
            if i < h or i >= n - h or sat[i, l]:
                continue
            for k in range(m):
                w[k] = x[i - h + k, l]
            for a in range(1, m):                       # insertion sort
                v = w[a]
                b = a - 1
                while b >= 0 and w[b] > v:
                    w[b + 1] = w[b]
                    b -= 1
                w[b + 1] = v
            med = w[h]
            for k in range(m):
                d[k] = abs(x[i - h + k, l] - med)
            for a in range(1, m):
                v = d[a]
                b = a - 1
                while b >= 0 and d[b] > v:
                    d[b + 1] = d[b]
                    b -= 1
                d[b + 1] = v
            s = 1.4826 * d[h]
            if s < floor[l]:
                s = floor[l]
            if abs(xi - med) > nsig * s:
                out[i, l] = med
                flag[i, l] = True


@njit(parallel=True, cache=True)
def _sds_errors(om, dt, k0s, k1s, u1, u2, sgrid, err):
    """Static-dynamic-static gyro scale test: for each pair, integrate s * omega (rad/s, body frame) from k0 to k1 and
    compare the rotated first gravity direction with the second: err[p, j] = angle(R12(s_j)^T u1, u2) (rad)."""
    npair = k0s.shape[0]
    ns = sgrid.shape[0]
    for p in prange(npair):
        for j in range(ns):
            s = sgrid[j]
            qw, qx, qy, qz = 1.0, 0.0, 0.0, 0.0
            for k in range(k0s[p], k1s[p]):
                wx, wy, wz = s * om[k, 0] * dt, s * om[k, 1] * dt, s * om[k, 2] * dt
                th = math.sqrt(wx * wx + wy * wy + wz * wz)
                if th < 1e-12:
                    dw, dx, dy, dz = 1.0, 0.5 * wx, 0.5 * wy, 0.5 * wz
                else:
                    sn = math.sin(0.5 * th) / th
                    dw, dx, dy, dz = math.cos(0.5 * th), sn * wx, sn * wy, sn * wz
                nw = qw * dw - qx * dx - qy * dy - qz * dz
                nx = qw * dx + qx * dw + qy * dz - qz * dy
                ny = qw * dy - qx * dz + qy * dw + qz * dx
                nz = qw * dz + qx * dy - qy * dx + qz * dw
                qw, qx, qy, qz = nw, nx, ny, nz
            # R (body1 -> body2 frame change): u2_pred = R^T u1 with R = rot(q)
            r00 = 1 - 2 * (qy * qy + qz * qz)
            r01 = 2 * (qx * qy - qz * qw)
            r02 = 2 * (qx * qz + qy * qw)
            r10 = 2 * (qx * qy + qz * qw)
            r11 = 1 - 2 * (qx * qx + qz * qz)
            r12 = 2 * (qy * qz - qx * qw)
            r20 = 2 * (qx * qz - qy * qw)
            r21 = 2 * (qy * qz + qx * qw)
            r22 = 1 - 2 * (qx * qx + qy * qy)
            a0, a1, a2 = u1[p, 0], u1[p, 1], u1[p, 2]
            px = r00 * a0 + r10 * a1 + r20 * a2
            py = r01 * a0 + r11 * a1 + r21 * a2
            pz = r02 * a0 + r12 * a1 + r22 * a2
            c = px * u2[p, 0] + py * u2[p, 1] + pz * u2[p, 2]
            nn = math.sqrt(px * px + py * py + pz * pz)
            c = c / nn
            if c > 1.0:
                c = 1.0
            if c < -1.0:
                c = -1.0
            err[p, j] = math.acos(c)


def hampel_floor(x: np.ndarray, min_counts: float) -> np.ndarray:
    """Per-lane global noise SD (counts) = 1.4826 * median|x[i+1] - x[i]| / sqrt(2), floored at min_counts."""
    step = max(1, x.shape[0] // 2_000_000)
    d = np.abs(np.diff(x[::step].astype(np.float64), axis=0)) if step == 1 else np.abs(x[1::step].astype(np.float64) - x[:-1:step][: len(x[1::step])])
    return np.maximum(1.4826 * np.median(d, axis=0) / math.sqrt(2.0), min_counts).astype(np.float32)


def frame_seconds_class(unix_ms: np.ndarray, sec: np.ndarray, ok: np.ndarray, still: np.ndarray) -> np.ndarray:
    """Per sample: 1 = IMU-still second, 2 = QC-ok moving second, 0 = neither (not ok / outside the table)."""
    s = np.floor(unix_ms / 1000.0).astype(np.int64) - int(sec[0])
    inb = (s >= 0) & (s < len(sec))
    cls_sec = np.where(ok & still, 1, np.where(ok & ~still, 2, 0)).astype(np.int8)
    out = np.zeros(len(unix_ms), np.int8)
    out[inb] = cls_sec[s[inb]]
    return out


def psd_by_class(x: np.ndarray, cls: np.ndarray, bad: np.ndarray, nper: int, max_seg: int, rng: np.random.Generator,
                 fs: float = FS_RAW) -> dict:
    """One-sided PSD (units^2/Hz) per column of x for 2-s Hann segments lying entirely in one class (1 still, 2 moving)
    and free of `bad` samples; at most max_seg segments per class (random, fixed seed)."""
    win = np.hanning(nper)
    norm = 2.0 / (fs * np.sum(win ** 2))
    out = {"f": np.fft.rfftfreq(nper, 1.0 / fs)}
    lab = np.where(bad, -1, cls).astype(np.int8)
    for c, name in ((1, "still"), (2, "moving")):
        runs = [(a, b) for a, b in C.true_runs(lab == c) if b - a >= nper]
        starts = np.concatenate([np.arange(a, b - nper + 1, nper) for a, b in runs]) if runs else np.zeros(0, np.int64)
        if len(starts) > max_seg:
            starts = np.sort(rng.choice(starts, max_seg, replace=False))
        out[f"n_{name}"] = int(len(starts))
        if not len(starts):
            out[name] = np.full((len(out["f"]), x.shape[1]), np.nan)
            continue
        acc = np.zeros((len(out["f"]), x.shape[1]))
        for c0 in range(0, len(starts), 256):
            idx = starts[c0:c0 + 256, None] + np.arange(nper)[None, :]
            seg = x[idx].astype(np.float64)                    # (k, nper, L)
            seg -= seg.mean(axis=1, keepdims=True)
            acc += (np.abs(np.fft.rfft(seg * win[None, :, None], axis=1)) ** 2).sum(axis=0)
        out[name] = acc / len(starts) * norm
    return out


def cutoff_rule(f: np.ndarray, p_still: np.ndarray, p_mov: np.ndarray, pb: dict) -> dict:
    """f_c = lowest f >= 5 Hz from which the 2-Hz-smoothed P_moving / N stays <= ratio up to 100 Hz; N = median still PSD
    over the noise band (white sensor noise); clipped to [5, 40] Hz. p_* = sum over the 3 axes of a sensor group."""
    band = (f >= pb["noise_band_hz"][0]) & (f <= pb["noise_band_hz"][1])
    N = float(np.nanmedian(p_still[band]))
    df = f[1] - f[0]
    k = max(1, int(round(pb["cutoff_smooth_hz"] / df)))
    sm = np.convolve(p_mov, np.ones(k) / k, mode="same")
    ratio = sm / N
    lo, hi = pb["cutoff_search_hz"]
    sel = np.flatnonzero((f >= lo) & (f <= hi))
    above = ratio[sel] > pb["cutoff_ratio"]
    if not above.any():
        fc_raw = float(f[sel[0]])
    else:
        last = int(np.flatnonzero(above)[-1])
        fc_raw = float(f[sel[min(last + 1, len(sel) - 1)]]) if last + 1 < len(sel) else float(hi)
    fc = float(np.clip(fc_raw, *pb["cutoff_clip_hz"]))
    return {"noise_floor": N, "fc_raw_hz": fc_raw, "fc_hz": fc, "ratio_at_5hz": float(np.interp(5.0, f, ratio)),
            "ratio_at_20hz": float(np.interp(20.0, f, ratio)), "ratio_at_40hz": float(np.interp(40.0, f, ratio))}


def any_per_100hz(mask_raw: np.ndarray, n100: int, dil: int = 0) -> np.ndarray:
    """100-Hz sample i covers raw frames [12.5 i - 6, 12.5 i + 6]; any flag inside -> True; then dilate by `dil`."""
    mask_raw = np.asarray(mask_raw, bool)
    c = np.r_[0, np.cumsum(mask_raw.astype(np.int64))]
    ctr = np.arange(n100) * (FS_RAW / FS100)
    a = np.clip(np.floor(ctr - 6).astype(np.int64), 0, len(mask_raw))
    b = np.clip(np.floor(ctr + 7).astype(np.int64), 0, len(mask_raw))
    m = (c[b] - c[a]) > 0
    if dil > 0 and m.any():
        m = np.convolve(m.astype(np.int32), np.ones(2 * dil + 1, np.int32), mode="same") > 0
    return m


def count_per_100hz(mask_raw: np.ndarray, n100: int) -> np.ndarray:
    c = np.r_[0, np.cumsum(np.asarray(mask_raw, bool).astype(np.int64))]
    ctr = np.arange(n100) * (FS_RAW / FS100)
    a = np.clip(np.floor(ctr - 6).astype(np.int64), 0, len(mask_raw))
    b = np.clip(np.floor(ctr + 7).astype(np.int64), 0, len(mask_raw))
    return np.minimum(c[b] - c[a], 255).astype(np.uint8)


def window_stats(a: np.ndarray, w: np.ndarray, bad: np.ndarray, wlen: int) -> dict:
    """Non-overlapping windows of wlen 100-Hz samples: mean acc, per-axis acc SD, median |w|, any bad."""
    nw = a.shape[0] // wlen
    A = a[: nw * wlen].reshape(nw, wlen, 3)
    W = np.linalg.norm(w[: nw * wlen].reshape(nw, wlen, 3), axis=2)
    return {"abar": A.mean(axis=1), "asd": A.std(axis=1), "wmed": np.median(W, axis=1),
            "amed": np.median(np.linalg.norm(A, axis=2), axis=1),
            "bad": bad[: nw * wlen].reshape(nw, wlen).any(axis=1), "i0": np.arange(nw) * wlen}


def fit_ellipsoid(abar: np.ndarray, pb: dict) -> dict:
    """a_cal = D (a - o), D diagonal; Huber loss on (|a_cal| - g) / huber_scale; priors D_ii = 1 +- sd_s, o_i = 0 +- sd_o."""
    from scipy.optimize import least_squares
    hs, ss, so = pb["ellipsoid_huber_scale"], pb["ellipsoid_prior_scale_sd"], pb["ellipsoid_prior_offset_sd"]

    def res(th):
        d, o = th[:3], th[3:]
        r = (np.linalg.norm((abar - o) * d, axis=1) - G) / hs
        return np.r_[r, (d - 1.0) / ss, o / so]

    k0 = G / np.median(np.linalg.norm(abar, axis=1))
    sol = least_squares(res, np.r_[np.full(3, k0), np.zeros(3)], loss="huber", f_scale=1.0, method="trf")
    return {"D": sol.x[:3].tolist(), "o": sol.x[3:].tolist(), "cost": float(sol.cost), "n": int(len(abar)), "ok": bool(sol.success)}


def apply_acc(a: np.ndarray, cal: dict) -> np.ndarray:
    if cal["method"] == "ellipsoid":
        return (a - np.asarray(cal["o"])) * np.asarray(cal["D"])
    return a * cal["k_a"]


def acc_cal_cv(abar: np.ndarray, t_s: np.ndarray, pb: dict) -> dict:
    """2-fold CV over alternating 10-min blocks: held-out median | |a_cal| - g | for scalar k_a and the ellipsoid."""
    fold = (np.floor(t_s / pb["cv_block_s"]).astype(np.int64) % 2)
    res = {"scalar": [], "ellipsoid": []}
    for f in (0, 1):
        tr, te = abar[fold != f], abar[fold == f]
        if len(tr) < 50 or len(te) < 50:
            return {"scalar": np.nan, "ellipsoid": np.nan, "n": int(len(abar))}
        k = G / np.median(np.linalg.norm(tr, axis=1))
        e = fit_ellipsoid(tr, pb)
        res["scalar"].append(np.abs(np.linalg.norm(te * k, axis=1) - G))
        res["ellipsoid"].append(np.abs(np.linalg.norm((te - e["o"]) * e["D"], axis=1) - G))
    return {"scalar": float(np.median(np.concatenate(res["scalar"]))),
            "ellipsoid": float(np.median(np.concatenate(res["ellipsoid"]))), "n": int(len(abar))}


def orientation_coverage(abar: np.ndarray) -> list:
    u = abar / np.linalg.norm(abar, axis=1, keepdims=True)
    return np.sort(np.linalg.eigvalsh(np.cov(u.T))).tolist()


def quiet_seconds(a: np.ndarray, w: np.ndarray, bad: np.ndarray) -> dict:
    """make_imu's quiet 1-s windows (median |w| < 10 deg/s, | k_a median|a| - g | < 0.05 g, not bad) and their median gyro."""
    ws = window_stats(a, w, bad, int(FS100))
    q0 = (ws["wmed"] < MI.QUIET_W_DPS) & ~ws["bad"]
    k = G / float(np.median(ws["amed"][q0])) if q0.sum() >= 10 else 1.0
    q = q0 & (np.abs(k * ws["amed"] - G) < MI.QUIET_A_FRAC * G)
    nw = len(ws["wmed"])
    wm = np.median(w[: nw * 100].reshape(nw, 100, 3), axis=1)
    return {"quiet": q, "wmed3": wm, "t_c": (np.arange(nw) + 0.5), "k_a": k}   # t_c in s from the array start


def bias_block(tq: np.ndarray, wq: np.ndarray, t_eval: np.ndarray, block_s: float = MI.BIAS_BLOCK_S,
               min_n: int = MI.BIAS_MIN_QUIET_S) -> np.ndarray:
    """make_imu's rule on per-quiet-second medians: block median (>= min_n quiet s) at block centres, linear interp."""
    if not len(tq):
        return np.zeros((len(t_eval), 3))
    blk = np.floor(tq / block_s).astype(np.int64)
    cs, vs = [], []
    for b in np.unique(blk):
        m = blk == b
        if m.sum() >= min_n:
            cs.append((b + 0.5) * block_s)
            vs.append(np.median(wq[m], axis=0))
    if not cs:
        return np.tile(np.median(wq, axis=0), (len(t_eval), 1))
    cs, vs = np.array(cs), np.array(vs)
    return np.column_stack([np.interp(t_eval, cs, vs[:, k]) for k in range(3)])


def bias_running(tq: np.ndarray, wq: np.ndarray, t_eval: np.ndarray, half_s: float, min_n: int) -> np.ndarray:
    """Running median of per-quiet-second gyro medians over +-half_s (widened x3 when < min_n windows), evaluated at every
    quiet window, then linearly interpolated to t_eval."""
    if not len(tq):
        return np.zeros((len(t_eval), 3))
    o = np.argsort(tq)
    tq, wq = tq[o], wq[o]
    nodes = np.empty((len(tq), 3))
    for i, t in enumerate(tq):
        for h in (half_s, 3 * half_s, 1e12):
            a, b = np.searchsorted(tq, [t - h, t + h])
            if b - a >= min_n or h > 1e11:
                nodes[i] = np.median(wq[a:b], axis=0)
                break
    step = max(1, len(tq) // 4000)
    return np.column_stack([np.interp(t_eval, tq[::step], nodes[::step, k]) for k in range(3)])


def still_runs(sec: np.ndarray, ok: np.ndarray, still: np.ndarray, min_s: int) -> list:
    return [(int(sec[a]), int(sec[b - 1]) + 1) for a, b in C.true_runs(ok & still) if b - a >= min_s]


def loo_drift(t100_s: np.ndarray, a: np.ndarray, w: np.ndarray, runs_s: list, tq: np.ndarray, wq: np.ndarray, method: str,
              pb: dict) -> np.ndarray:
    """Leave-one-run-out yaw drift rate (deg/s) on each still run: bias estimated without that run's quiet windows,
    drift = | sum((w - b) . u) dt | / duration with u = the run's mean gravity direction. t100_s, tq in s (same origin)."""
    out = []
    for r0, r1 in runs_s:
        m = (t100_s >= r0) & (t100_s < r1)
        if m.sum() < 100:
            continue
        keep = (tq < r0 - 1) | (tq > r1 + 1)
        mid = np.array([(r0 + r1) / 2.0])
        if method == "block":
            b = bias_block(tq[keep], wq[keep], mid)[0]
        else:
            b = bias_running(tq[keep], wq[keep], mid, pb["bias_running_half_s"], pb["bias_min_windows"])[0]
        u = a[m].mean(axis=0)
        u /= np.linalg.norm(u)
        yaw = float(np.sum((w[m] - b) @ u) / FS100)
        out.append(abs(yaw) / (r1 - r0))
    return np.array(out)


def kinematic(a: np.ndarray, w: np.ndarray, bad: np.ndarray, pb: dict, sel: np.ndarray | None = None) -> dict:
    """du/dt = u x w (u = gravity-up direction in the head frame): OLS slope through the origin of du/dt on u x w (all
    three components stacked) and Pearson r, both signals low-passed at kin_lowpass_hz; samples with |w| in range,
    | |a| - g | < 0.1 g, not bad (and inside `sel`)."""
    sos = signal.butter(2, pb["kin_lowpass_hz"], fs=FS100, output="sos")
    al = signal.sosfiltfilt(sos, a, axis=0)
    wl = signal.sosfiltfilt(sos, w, axis=0) * D2R
    u = al / np.linalg.norm(al, axis=1, keepdims=True)
    du = np.gradient(u, 1.0 / FS100, axis=0)
    x = np.cross(u, wl)
    wn = np.linalg.norm(wl, axis=1) / D2R
    m = (wn >= pb["kin_omega_range_dps"][0]) & (wn <= pb["kin_omega_range_dps"][1])
    m &= np.abs(np.linalg.norm(al, axis=1) - G) < pb["kin_acc_dev_frac_g"] * G
    badd = np.convolve(bad.astype(np.int32), np.ones(41, np.int32), mode="same") > 0
    m &= ~badd
    if sel is not None:
        m &= sel
    X, Y = x[m].ravel(), du[m].ravel()
    if len(X) < 100:
        return {"n": int(m.sum()), "slope": np.nan, "r": np.nan}
    return {"n": int(m.sum()), "slope": float(np.sum(X * Y) / np.sum(X * X)), "r": float(np.corrcoef(X, Y)[0, 1])}


def kin_latency(a: np.ndarray, w: np.ndarray, bad: np.ndarray, pb: dict, sel: np.ndarray | None = None,
                lags=range(-5, 6)) -> dict:
    """Acc-gyro relative latency: Pearson r of du/dt(t) with u(t) x w(t + lag) (the kinematic check, 5-Hz low-pass) over
    lags of 10 ms; parabolic interpolation of the peak. + = the gyro lags the accelerometer."""
    sos = signal.butter(2, pb["kin_lowpass_hz"], fs=FS100, output="sos")
    al = signal.sosfiltfilt(sos, a, axis=0)
    wl = signal.sosfiltfilt(sos, w, axis=0) * D2R
    u = al / np.linalg.norm(al, axis=1, keepdims=True)
    du = np.gradient(u, 1.0 / FS100, axis=0)
    wn = np.linalg.norm(wl, axis=1) / D2R
    m = (wn >= pb["kin_omega_range_dps"][0]) & (wn <= pb["kin_omega_range_dps"][1])
    m &= np.abs(np.linalg.norm(al, axis=1) - G) < pb["kin_acc_dev_frac_g"] * G
    m &= ~(np.convolve(bad.astype(np.int32), np.ones(41, np.int32), mode="same") > 0)
    if sel is not None:
        m &= sel
    L = list(lags)
    idx = np.flatnonzero(m)
    idx = idx[(idx > max(L) + 1) & (idx < len(u) - max(L) - 1)]
    rs = []
    for lag in L:
        x = np.cross(u[idx], wl[idx + lag])
        rs.append(float(np.corrcoef(x.ravel(), du[idx].ravel())[0, 1]))
    k = int(np.argmax(rs))
    off = 0.0
    if 0 < k < len(L) - 1:
        den = rs[k - 1] - 2 * rs[k] + rs[k + 1]
        off = 0.5 * (rs[k - 1] - rs[k + 1]) / den if den != 0 else 0.0
    return {"lags_ms": [10 * l for l in L], "r": rs, "peak_ms": 10.0 * (L[k] + off), "r_peak": rs[k]}


def sds_pairs(a: np.ndarray, w: np.ndarray, bad: np.ndarray, pb: dict) -> dict:
    """Quasi-static intervals (centred 0.5-s median |w| < 10 deg/s and per-axis acc SD < 0.15 m/s^2, >= 0.5 s) -> pairs of
    consecutive intervals 0.2-3 s apart with a tilt change >= 20 deg; integration indices and the two gravity directions."""
    L = int(pb["sds_min_static_s"] * FS100)
    wn = pd.Series(np.linalg.norm(w, axis=1))
    wmed = wn.rolling(L, center=True, min_periods=L).median().to_numpy()
    asd = np.max(np.column_stack([pd.Series(a[:, k]).rolling(L, center=True, min_periods=L).std().to_numpy() for k in range(3)]), axis=1)
    qs = (wmed < pb["quasi_static_omega_dps"]) & (asd < pb["quasi_static_acc_sd"]) & ~bad
    runs = [(s, e) for s, e in C.true_runs(qs) if e - s >= L]
    k0s, k1s, u1s, u2s, tilt = [], [], [], [], []
    for (s1, e1), (s2, e2) in zip(runs[:-1], runs[1:]):
        gap = (s2 - e1) / FS100
        if not (pb["sds_gap_s"][0] <= gap <= pb["sds_gap_s"][1]):
            continue
        a1 = a[e1 - L:e1].mean(axis=0)
        a2 = a[s2:s2 + L].mean(axis=0)
        u1, u2 = a1 / np.linalg.norm(a1), a2 / np.linalg.norm(a2)
        ang = math.degrees(math.acos(float(np.clip(u1 @ u2, -1, 1))))
        if ang < pb["sds_min_tilt_deg"] or bad[e1 - L:s2 + L].any():
            continue
        k0s.append(e1 - L // 2)
        k1s.append(s2 + L // 2)
        u1s.append(u1)
        u2s.append(u2)
        tilt.append(ang)
    return {"k0": np.array(k0s, np.int64), "k1": np.array(k1s, np.int64), "u1": np.array(u1s).reshape(-1, 3),
            "u2": np.array(u2s).reshape(-1, 3), "tilt_deg": np.array(tilt)}


def sds_scale(w_rad: np.ndarray, pairs: dict, grid: np.ndarray) -> np.ndarray:
    err = np.zeros((len(pairs["k0"]), len(grid)))
    if len(pairs["k0"]):
        _sds_errors(np.ascontiguousarray(w_rad), 1.0 / FS100, pairs["k0"], pairs["k1"], np.ascontiguousarray(pairs["u1"]),
                    np.ascontiguousarray(pairs["u2"]), grid, err)
    return err


def still_noise(a: np.ndarray, w: np.ndarray, still100: np.ndarray, bad: np.ndarray) -> dict:
    """RMS (per axis, pooled) of the 100-Hz acc (m/s^2) and gyro (deg/s) about their per-second mean inside IMU-still
    seconds (sigma_f and sigma_omega candidates)."""
    n = (len(still100) // 100) * 100
    st = still100[:n].reshape(-1, 100).all(axis=1) & ~bad[:n].reshape(-1, 100).any(axis=1)
    if st.sum() < 10:
        return {"acc_rms": np.nan, "gyr_rms": np.nan, "n_s": int(st.sum())}
    A = a[:n].reshape(-1, 100, 3)[st]
    W = w[:n].reshape(-1, 100, 3)[st]
    return {"acc_rms": float(np.sqrt(np.mean((A - A.mean(axis=1, keepdims=True)) ** 2))),
            "gyr_rms": float(np.sqrt(np.mean((W - W.mean(axis=1, keepdims=True)) ** 2))), "n_s": int(st.sum())}


def b_worker(job: dict) -> dict:
    """One animal-night of Phase B. Stage 1 (always): saturation, Hampel spikes, PSDs by class. Stage 2 (job['fc'] given):
    before chain (make_imu) and after chain (Hampel + low-pass) at 100 Hz, calibration candidates and every metric."""
    t0 = time.time()
    pb = job["pb"]
    cache = BC.load_imu_raw_cache(Path(job["a1"]))
    six = cache["six"]
    sat = cache["sat"]
    frz = cache["frozen"]
    n = six.shape[0]
    u = BC.cache_unix_ms(cache)
    cls = frame_seconds_class(u, job["sec"], job["ok"], job["still"])
    out = {"animal": job["animal"], "night": job["night"], "n_raw": int(n)}
    # saturation per lane (head-frame names via S: sensor x = head z (yaw axis), sensor y = -head x, sensor z = -head y)
    sat_rows = []
    for l in range(6):
        rr = [(a, b) for a, b in C.true_runs(sat[:, l])]
        lens = np.array([b - a for a, b in rr]) if rr else np.zeros(0)
        sat_rows.append({"lane": l + 1, "samples": int(sat[:, l].sum()), "runs": int(len(rr)),
                         "longest_ms": float(lens.max() / FS_RAW * 1000) if len(lens) else 0.0,
                         "seconds_touched": int(len(np.unique(np.floor(u[sat[:, l]] / 1000.0))))})
    out["saturation"] = sat_rows
    out["sat_any_seconds"] = int(len(np.unique(np.floor(u[sat.any(axis=1)] / 1000.0))))
    # Hampel on counts
    x = six.astype(np.float32)
    hx = np.empty_like(x)
    fl = np.zeros(x.shape, bool)
    hfloor = hampel_floor(six, float(pb["hampel_mad_floor_counts"]))
    out["hampel_floor_counts"] = hfloor.tolist()
    _hampel_lanes(x, sat, int(pb["hampel_half_window"]), float(pb["hampel_nsigma"]), hfloor, hx, fl)
    out["spikes"] = [{"lane": l + 1, "total": int(fl[:, l].sum()), "still": int((fl[:, l] & (cls == 1)).sum()),
                      "moving": int((fl[:, l] & (cls == 2)).sum()), "still_frames": int((cls == 1).sum()),
                      "moving_frames": int((cls == 2).sum())} for l in range(6)]
    rng = np.random.default_rng(job["seed"])
    bad = sat.any(axis=1) | frz
    scale = np.r_[np.full(3, ACC_SCALE), np.full(3, GYR_SCALE)]
    ps_h = psd_by_class(hx, cls, bad, int(pb["psd_nperseg"]), 4000, rng)
    ps_r = psd_by_class(x, cls, bad, int(pb["psd_nperseg"]), 4000, np.random.default_rng(job["seed"]))
    out["psd"] = {"f": ps_h["f"], "still": ps_h["still"] * scale ** 2, "moving": ps_h["moving"] * scale ** 2,
                  "still_raw": ps_r["still"] * scale ** 2, "moving_raw": ps_r["moving"] * scale ** 2,
                  "n_still": ps_h["n_still"], "n_moving": ps_h["n_moving"]}
    del x
    if job.get("fc") is None:
        out["elapsed_s"] = time.time() - t0
        return out
    fca, fcg = job["fc"]["acc"], job["fc"]["gyr"]
    # ---- after chain: Hampel (done) -> zero-phase Butterworth -> resample_poly 2/25 -> head frame
    lp = []
    for l in range(6):
        sos = signal.butter(int(pb["butter_order"]), fca if l < 3 else fcg, fs=FS_RAW, output="sos")
        y = signal.sosfiltfilt(sos, hx[:, l].astype(np.float64) * scale[l])
        lp.append(signal.resample_poly(y, 2, 25))
    del hx
    n100 = min(len(v) for v in lp)
    B_lp = np.column_stack([v[:n100] for v in lp])
    a_lp, w_lp = B_lp[:, :3] @ MI.S, B_lp[:, 3:] @ MI.S
    del lp, B_lp
    # ---- before chain: make_imu stages 1-4 on the same window
    acc_B = six[:, :3].astype(np.float32) * np.float32(ACC_SCALE)
    gyr_B = six[:, 3:].astype(np.float32) * np.float32(GYR_SCALE)
    a_b100, w_b100, _, frz_b = MI.to_100hz(acc_B, gyr_B, sat.any(axis=1), frz)
    del acc_B, gyr_B
    n100 = min(n100, a_b100.shape[0])
    a_lp, w_lp = a_lp[:n100], w_lp[:n100]
    a_bH, w_bH = (a_b100[:n100] @ MI.S), (w_b100[:n100] @ MI.S)
    del a_b100, w_b100
    frz100 = any_per_100hz(frz, n100)
    cal_b = MI.calibrate(a_bH, w_bH, exclude=frz100)
    a_bef = a_bH * cal_b["k_a"]
    w_bef = w_bH - cal_b["bias"]
    del a_bH, w_bH
    # ---- 100-Hz time and flags
    amp = int(cache["amp0"]) + 200.0 * np.arange(n100)
    meta = json.loads(str(cache["meta_json"]))
    fit = json.loads(str(cache["fit_json"]))
    t100 = BC.local_midnight_ms(meta["start_local"]) + MI.pc_time_ms(amp, fit)
    dil_a, dil_g = int(math.ceil(2.0 / fca * FS100)), int(math.ceil(2.0 / fcg * FS100))
    sat_acc = any_per_100hz(sat[:, :3].any(axis=1), n100, dil_a)
    sat_gyr = any_per_100hz(sat[:, 3:].any(axis=1), n100, dil_g)
    spikes100 = count_per_100hz(fl.any(axis=1), n100)
    bad100 = sat_acc | sat_gyr | frz100
    cls100 = frame_seconds_class(t100, job["sec"], job["ok"], job["still"])
    still100 = cls100 == 1
    t_s = (t100 - t100[0]) / 1000.0
    # ---- accelerometer calibration candidates (quasi-static 0.5-s windows of the after chain)
    wlen = int(pb["quasi_static_win_s"] * FS100)
    ws = window_stats(a_lp, w_lp, bad100, wlen)
    qsw = (ws["wmed"] < pb["quasi_static_omega_dps"]) & (ws["asd"].max(axis=1) < pb["quasi_static_acc_sd"]) & ~ws["bad"]
    abar, tw = ws["abar"][qsw], t_s[ws["i0"][qsw]]
    out["acc_cv"] = acc_cal_cv(abar, tw, pb)
    out["acc_cov_eig"] = orientation_coverage(abar) if len(abar) > 10 else [np.nan] * 3
    ell = fit_ellipsoid(abar, pb) if len(abar) >= 50 else None
    k_sc = G / float(np.median(np.linalg.norm(abar, axis=1))) if len(abar) else 1.0
    out["acc_fit"] = {"scalar_k_a": k_sc, "ellipsoid": ell, "n_windows": int(len(abar)), "make_imu_k_a": float(cal_b["k_a"])}
    # before chain gravity residual on the same held-out design (make_imu's k_a is global, fitted on its own windows)
    wsb = window_stats(a_bef, w_bef, bad100, wlen)
    qb = (wsb["wmed"] < pb["quasi_static_omega_dps"]) & (wsb["asd"].max(axis=1) < pb["quasi_static_acc_sd"]) & ~wsb["bad"]
    out["grav_resid_before_all"] = float(np.median(np.abs(np.linalg.norm(wsb["abar"][qb], axis=1) - G))) if qb.any() else np.nan
    # ---- gyro bias candidates on the after chain
    qs = quiet_seconds(a_lp, w_lp, bad100)
    tq, wq = qs["t_c"][qs["quiet"]], qs["wmed3"][qs["quiet"]]
    bias_blk = bias_block(tq, wq, t_s)
    bias_run = bias_running(tq, wq, t_s, pb["bias_running_half_s"], pb["bias_min_windows"])
    runs_unix = still_runs(job["sec"], job["ok"], job["still"], int(pb["still_run_min_s"]))
    runs_s = [((r0 * 1000.0 - t100[0]) / 1000.0, (r1 * 1000.0 - t100[0]) / 1000.0) for r0, r1 in runs_unix]
    a_tmp = a_lp * k_sc
    out["drift"] = {"after_block": loo_drift(t_s, a_tmp, w_lp, runs_s, tq, wq, "block", pb).tolist(),
                    "after_running": loo_drift(t_s, a_tmp, w_lp, runs_s, tq, wq, "running", pb).tolist()}
    qsb = quiet_seconds(a_bef, w_bef + cal_b["bias"], bad100)          # the before chain's own quiet windows, raw gyro
    tqb, wqb = qsb["t_c"][qsb["quiet"]], qsb["wmed3"][qsb["quiet"]]
    out["drift"]["before_block"] = loo_drift(t_s, a_bef, w_bef + cal_b["bias"], runs_s, tqb, wqb, "block", pb).tolist()
    out["n_still_runs"] = len(runs_s)
    # ---- gyro scale (static-dynamic-static) on the after chain (running bias)
    pairs = sds_pairs(a_tmp, w_lp - bias_run, bad100, pb)
    g0, g1, gs = pb["gyro_scale_grid"]
    grid = np.round(np.arange(g0, g1 + 1e-9, gs), 6)
    out["sds"] = {"grid": grid, "err": sds_scale((w_lp - bias_run) * D2R, pairs, grid), "tilt_deg": pairs["tilt_deg"]}
    out["sds_err_before"] = sds_scale((w_bef) * D2R, sds_pairs(a_bef, w_bef, bad100, pb), grid)
    # ---- kinematic consistency (before: make_imu chain; after candidates: scalar / ellipsoid, running bias, s = 1)
    night_sel = (t100 >= job["lo"]) & (t100 < job["hi"])
    out["kin_before"] = kinematic(a_bef, w_bef, bad100, pb, night_sel)
    out["kin_after_scalar"] = kinematic(a_tmp, w_lp - bias_run, bad100, pb, night_sel)
    out["kin_latency"] = kin_latency(a_tmp, w_lp - bias_run, bad100, pb, night_sel)
    if ell is not None:
        out["kin_after_ellipsoid"] = kinematic((a_lp - ell["o"]) * ell["D"], w_lp - bias_run, bad100, pb, night_sel)
    # ---- still-period noise (sigma_f, sigma_omega candidates) and post-filter angular acceleration
    out["still_noise"] = still_noise(a_tmp, w_lp - bias_run, still100, bad100)
    mov = (cls100 == 2) & ~bad100
    for nm, ww in (("before", w_bef), ("after", w_lp)):
        al = np.linalg.norm(np.gradient(ww, 1.0 / FS100, axis=0), axis=1)[mov]
        out[f"alpha_{nm}"] = {q: float(np.percentile(al, q)) for q in (50, 99, 99.9, 99.99)} | {"max": float(al.max()) if len(al) else np.nan}
    # arrays for the parent (A3 + Fusion)
    out["arrays"] = {"t100": t100, "a_lp": a_lp.astype(np.float32), "w_lp": w_lp.astype(np.float32),
                     "bias_block": bias_blk.astype(np.float32), "bias_running": bias_run.astype(np.float32),
                     "sat_acc": sat_acc, "sat_gyr": sat_gyr, "frozen": frz100, "spikes": spikes100,
                     "quiet": np.repeat(qs["quiet"], 100)[:n100] if len(qs["quiet"]) * 100 >= n100 else
                     np.r_[np.repeat(qs["quiet"], 100), np.zeros(n100 - len(qs["quiet"]) * 100, bool)],
                     "a_bef_night": a_bef[night_sel].astype(np.float32), "w_bef_night": w_bef[night_sel].astype(np.float32),
                     "night_sel": night_sel, "still100": still100}
    out["cal_before"] = {"k_a": float(cal_b["k_a"]), "bias_blocks": cal_b["bias_blocks"]}
    out["fc"] = {"acc": fca, "gyr": fcg}
    out["elapsed_s"] = time.time() - t0
    return out


def fusion_worker(job: dict) -> dict:
    """Fusion AHRS (make_imu.fuse, unchanged settings) on one chain's night-window 100-Hz data -> stability metrics."""
    a = job["a"].astype(np.float64)
    w = job["w"].astype(np.float64)
    fz = MI.fuse(a, w)
    gvec = fz["gravity"] / np.linalg.norm(fz["gravity"], axis=1, keepdims=True)
    pitch = np.degrees(np.arcsin(np.clip(gvec[:, 0], -1, 1)))
    roll = np.degrees(np.arctan2(gvec[:, 1], gvec[:, 2]))
    sds_p, sds_r = [], []
    for s, e in job["runs_idx"]:
        if e - s >= 100:
            sds_p.append(float(np.std(pitch[s:e])))
            sds_r.append(float(np.std(roll[s:e])))
    au = a / np.linalg.norm(a, axis=1, keepdims=True)
    qs = job["qs_idx"]
    ang = np.degrees(np.arccos(np.clip(np.sum(au[qs] * gvec[qs], axis=1), -1, 1))) if len(qs) else np.array([np.nan])
    return {"animal": job["animal"], "night": job["night"], "chain": job["chain"],
            "pitch_sd_still_med": float(np.median(sds_p)) if sds_p else np.nan,
            "roll_sd_still_med": float(np.median(sds_r)) if sds_r else np.nan,
            "unreliable_frac": float(fz["unreliable"].mean()), "grav_vs_acc_deg_med": float(np.nanmedian(ang)),
            "n_runs": len(sds_p)}


# ====================================================================================================== Phase C: ESKF
NS = 15                                             # error state: dp(2) dv(2) dtheta(3, global) dba(3) dbg(3) dbw(2)
IP, IV, IT, IA, IG, IW = 0, 2, 4, 7, 10, 13
(K_SA, K_SG, K_SBA, K_SBG, K_SV, K_SOM, K_SF, K_TB, K_SB2, K_GATE, K_SASAT, K_SGSAT, K_PEVERY, K_CEVERY, K_G, K_HUBER,
 K_P0P, K_P0V, K_P0T, K_P0Y, K_P0BA, K_P0BG, K_GGATE, K_SGSTILL, K_SFDYN, K_WDYN, K_RESET, K_KR) = range(28)
NPAR = 28
GATE3 = 16.2662                                     # chi2_3 0.999: soft gate of the dynamic gravity update
LOG2PI = math.log(2.0 * math.pi)


@njit(cache=True)
def _rot(q, R):
    qw, qx, qy, qz = q[0], q[1], q[2], q[3]
    R[0, 0] = 1 - 2 * (qy * qy + qz * qz)
    R[0, 1] = 2 * (qx * qy - qz * qw)
    R[0, 2] = 2 * (qx * qz + qy * qw)
    R[1, 0] = 2 * (qx * qy + qz * qw)
    R[1, 1] = 1 - 2 * (qx * qx + qz * qz)
    R[1, 2] = 2 * (qy * qz - qx * qw)
    R[2, 0] = 2 * (qx * qz - qy * qw)
    R[2, 1] = 2 * (qy * qz + qx * qw)
    R[2, 2] = 1 - 2 * (qx * qx + qy * qy)


@njit(cache=True)
def _qexp_mul(q, wx, wy, wz, left):
    """q <- q (x) Exp(w) (body increment, left=False) or Exp(w) (x) q (global correction, left=True); normalised."""
    th = math.sqrt(wx * wx + wy * wy + wz * wz)
    if th < 1e-12:
        dw, dx, dy, dz = 1.0, 0.5 * wx, 0.5 * wy, 0.5 * wz
    else:
        s = math.sin(0.5 * th) / th
        dw, dx, dy, dz = math.cos(0.5 * th), s * wx, s * wy, s * wz
    if left:
        aw, ax, ay, az = dw, dx, dy, dz
        bw, bx, by, bz = q[0], q[1], q[2], q[3]
    else:
        aw, ax, ay, az = q[0], q[1], q[2], q[3]
        bw, bx, by, bz = dw, dx, dy, dz
    nw = aw * bw - ax * bx - ay * by - az * bz
    nx = aw * bx + ax * bw + ay * bz - az * by
    ny = aw * by - ax * bz + ay * bw + az * bx
    nz = aw * bz + ax * by - ay * bx + az * bw
    nn = math.sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
    q[0] = nw / nn
    q[1] = nx / nn
    q[2] = ny / nn
    q[3] = nz / nn


@njit(cache=True)
def _phi_left(M, out, R, fN, dt, phiw):
    """out = Phi M, Phi = I + F dt + F^2 dt^2/2 + F^3 dt^3/6 of the error model
    dp' = dv; dv' = (-[f]x dtheta)_h - (R dba)_h; dtheta' = -R dbg; dbw decays by phiw (exact)."""
    a01, a02 = fN[2], -fN[1]                        # Ah = rows 0-1 of -[f]x = [[0, f2, -f1], [-f2, 0, f0]]
    a10, a12 = -fN[2], fN[0]
    ar00 = a01 * R[1, 0] + a02 * R[2, 0]
    ar01 = a01 * R[1, 1] + a02 * R[2, 1]
    ar02 = a01 * R[1, 2] + a02 * R[2, 2]
    ar10 = a10 * R[0, 0] + a12 * R[2, 0]
    ar11 = a10 * R[0, 1] + a12 * R[2, 1]
    ar12 = a10 * R[0, 2] + a12 * R[2, 2]
    d2 = 0.5 * dt * dt
    d3 = dt * dt * dt / 6.0
    for j in range(M.shape[1]):
        t0, t1, t2 = M[IT, j], M[IT + 1, j], M[IT + 2, j]
        b0, b1, b2 = M[IA, j], M[IA + 1, j], M[IA + 2, j]
        g0, g1, g2 = M[IG, j], M[IG + 1, j], M[IG + 2, j]
        at0 = a01 * t1 + a02 * t2
        at1 = a10 * t0 + a12 * t2
        rb0 = R[0, 0] * b0 + R[0, 1] * b1 + R[0, 2] * b2
        rb1 = R[1, 0] * b0 + R[1, 1] * b1 + R[1, 2] * b2
        ag0 = ar00 * g0 + ar01 * g1 + ar02 * g2
        ag1 = ar10 * g0 + ar11 * g1 + ar12 * g2
        out[IP, j] = M[IP, j] + dt * M[IV, j] + d2 * (at0 - rb0) - d3 * ag0
        out[IP + 1, j] = M[IP + 1, j] + dt * M[IV + 1, j] + d2 * (at1 - rb1) - d3 * ag1
        out[IV, j] = M[IV, j] + dt * (at0 - rb0) - d2 * ag0
        out[IV + 1, j] = M[IV + 1, j] + dt * (at1 - rb1) - d2 * ag1
        for r in range(3):
            out[IT + r, j] = M[IT + r, j] - dt * (R[r, 0] * g0 + R[r, 1] * g1 + R[r, 2] * g2)
            out[IA + r, j] = b0 if r == 0 else (b1 if r == 1 else b2)
            out[IG + r, j] = g0 if r == 0 else (g1 if r == 1 else g2)
        out[IW, j] = phiw * M[IW, j]
        out[IW + 1, j] = phiw * M[IW + 1, j]


@njit(cache=True)
def _cov_prop(P, T, T2, R, fN, dt, phiw, qa, qg, qba, qbg, qw, rts, Phi):
    _phi_left(P, T, R, fN, dt, phiw)
    for i in range(NS):
        for j in range(NS):
            T2[i, j] = T[j, i]
    _phi_left(T2, P, R, fN, dt, phiw)                # P = Phi (Phi P)^T = Phi P Phi^T
    for a in range(2):
        P[IP + a, IP + a] += qa * dt * dt / 3.0
        P[IP + a, IV + a] += qa * dt / 2.0
        P[IV + a, IP + a] += qa * dt / 2.0
        P[IV + a, IV + a] += qa
        P[IW + a, IW + a] += qw
    for r in range(3):
        P[IT + r, IT + r] += qg
        P[IA + r, IA + r] += qba * dt
        P[IG + r, IG + r] += qbg * dt
    for i in range(NS):
        for j in range(i + 1, NS):
            s = 0.5 * (P[i, j] + P[j, i])
            P[i, j] = s
            P[j, i] = s
    if rts:
        _phi_left(Phi, T, R, fN, dt, phiw)
        for i in range(NS):
            for j in range(NS):
                Phi[i, j] = T[i, j]


@njit(cache=True)
def _update(P, dx, H, m, Rd, nu, gate2, PHt, S, Si, K):
    """Kalman update with an m x 15 H (m <= 3), diagonal R (Rd), innovation nu; soft chi2 gate (R x d2/gate2 when
    d2 > gate2 > 0). dx = K nu (15). Returns (d2 raw, d2 used, log det S used)."""
    for i in range(NS):
        for a in range(m):
            s = 0.0
            for k in range(NS):
                h = H[a, k]
                if h != 0.0:
                    s += P[i, k] * h
            PHt[i, a] = s
    infl = 1.0
    d2raw = 0.0
    ld = 0.0
    for rep in range(2):
        for a in range(m):
            for b in range(m):
                s = 0.0
                for k in range(NS):
                    h = H[a, k]
                    if h != 0.0:
                        s += h * PHt[k, b]
                S[a, b] = s
            S[a, a] += Rd[a] * infl
        if m == 1:
            det = S[0, 0]
            Si[0, 0] = 1.0 / det
        elif m == 2:
            det = S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0]
            Si[0, 0] = S[1, 1] / det
            Si[1, 1] = S[0, 0] / det
            Si[0, 1] = -S[0, 1] / det
            Si[1, 0] = -S[1, 0] / det
        else:
            c00 = S[1, 1] * S[2, 2] - S[1, 2] * S[2, 1]
            c01 = -(S[1, 0] * S[2, 2] - S[1, 2] * S[2, 0])
            c02 = S[1, 0] * S[2, 1] - S[1, 1] * S[2, 0]
            det = S[0, 0] * c00 + S[0, 1] * c01 + S[0, 2] * c02
            Si[0, 0] = c00 / det
            Si[1, 0] = c01 / det
            Si[2, 0] = c02 / det
            Si[0, 1] = -(S[0, 1] * S[2, 2] - S[0, 2] * S[2, 1]) / det
            Si[1, 1] = (S[0, 0] * S[2, 2] - S[0, 2] * S[2, 0]) / det
            Si[2, 1] = -(S[0, 0] * S[2, 1] - S[0, 1] * S[2, 0]) / det
            Si[0, 2] = (S[0, 1] * S[1, 2] - S[0, 2] * S[1, 1]) / det
            Si[1, 2] = -(S[0, 0] * S[1, 2] - S[0, 2] * S[1, 0]) / det
            Si[2, 2] = (S[0, 0] * S[1, 1] - S[0, 1] * S[1, 0]) / det
        d2 = 0.0
        for a in range(m):
            for b in range(m):
                d2 += nu[a] * Si[a, b] * nu[b]
        if rep == 0:
            d2raw = d2
            if gate2 > 0.0 and d2 > gate2:
                infl = d2 / gate2
                continue
        ld = math.log(det)
        break
    for i in range(NS):
        for a in range(m):
            s = 0.0
            for b in range(m):
                s += PHt[i, b] * Si[b, a]
            K[i, a] = s
    for i in range(NS):
        s = 0.0
        for a in range(m):
            s += K[i, a] * nu[a]
        dx[i] = s
    for i in range(NS):
        for j in range(i, NS):
            s = 0.0
            for a in range(m):
                s += K[i, a] * PHt[j, a]
            P[i, j] -= s
            if j != i:
                P[j, i] = P[i, j]
    return d2raw, d2, ld


@njit(cache=True)
def _inject(x, q, dx):
    """Nominal x = [p0 p1 v0 v1 ba0 ba1 ba2 bg0 bg1 bg2 bw0 bw1]; q = head->world quaternion; global attitude error."""
    x[0] += dx[IP]
    x[1] += dx[IP + 1]
    x[2] += dx[IV]
    x[3] += dx[IV + 1]
    for r in range(3):
        x[4 + r] += dx[IA + r]
        x[7 + r] += dx[IG + r]
    x[10] += dx[IW]
    x[11] += dx[IW + 1]
    _qexp_mul(q, dx[IT], dx[IT + 1], dx[IT + 2], True)


@njit(cache=True)
def _prop(x, q, R, fN, acc_i, gyr_i, usable, dt, phiw):
    """Nominal propagation over dt with one IMU sample (held): horizontal specific force drives v, p (gravity is
    vertical, z fixed); q <- q (x) Exp((w - bg) dt); WISER drift mean decays."""
    _rot(q, R)
    if usable:
        a0, a1, a2 = acc_i[0] - x[4], acc_i[1] - x[5], acc_i[2] - x[6]
        for r in range(3):
            fN[r] = R[r, 0] * a0 + R[r, 1] * a1 + R[r, 2] * a2
    else:
        fN[0] = 0.0
        fN[1] = 0.0
        fN[2] = 0.0
    x[0] += x[2] * dt + 0.5 * fN[0] * dt * dt
    x[1] += x[3] * dt + 0.5 * fN[1] * dt * dt
    x[2] += fN[0] * dt
    x[3] += fN[1] * dt
    x[10] *= phiw
    x[11] *= phiw
    if usable:
        _qexp_mul(q, (gyr_i[0] - x[7]) * dt, (gyr_i[1] - x[8]) * dt, (gyr_i[2] - x[9]) * dt, False)
    _rot(q, R)


@njit(cache=True)
def _eskf(t_imu, acc, gyr, iq, still, i_start, t_fix, z, r2tot, fmov, vis, par, yaw0, do_rts, n_iter, store,
          o_zhat, o_var, o_p, o_v, o_bw, o_q, o_ba, o_bg, o_nu, o_S, o_nis, o_w):
    """Error-state Kalman filter (+ RTS smoother) of a head carrying both the IMU and the WISER tag.
    t_imu (N,) s; acc (N,3) in/s^2 head frame; gyr (N,3) rad/s; iq (N,) 0 ok / 1 saturated / 2 unusable; still (N,)
    pseudo-updates allowed; t_fix (M,) s (WISER time - tau*); z (M,2) in; r2tot (M,2) per-axis total fix variance;
    vis (M,) fix used. Returns (pseudo-log-likelihood of the pass-0 WISER innovations, number of such updates)."""
    N = t_imu.shape[0]
    M = t_fix.shape[0]
    sa2, sg2, sgst2 = par[K_SA] ** 2, par[K_SG] ** 2, par[K_SGSTILL] ** 2
    sba2, sbg2 = par[K_SBA] ** 2, par[K_SBG] ** 2
    sv2, som2, sf2 = par[K_SV] ** 2, par[K_SOM] ** 2, par[K_SF] ** 2
    tb, sb2, gate2 = par[K_TB], par[K_SB2], par[K_GATE]
    sasat2, sgsat2 = par[K_SASAT] ** 2, par[K_SGSAT] ** 2
    pevery, cevery = int(par[K_PEVERY]), int(par[K_CEVERY])
    Gv, hk, ggate = par[K_G], par[K_HUBER], par[K_GGATE]
    sfdyn2, wdyn, rst = par[K_SFDYN] ** 2, par[K_WDYN], par[K_RESET]
    kr = par[K_KR] if par[K_KR] > 0 else 1.0
    r2w = np.empty((M, 2))
    for j in range(M):
        for a in range(2):
            v = r2tot[j, a] - sb2
            r2w[j, a] = v if v > 0.25 * r2tot[j, a] else 0.25 * r2tot[j, a]
            if fmov[j]:
                r2w[j, a] *= kr
    npseudo = 0
    dyn = np.zeros(N, np.bool_)                     # dynamic gravity-update samples (|a| ~ g, |w| < wdyn, not still)
    for k in range(i_start + 1, N):
        if k % pevery != 0:
            continue
        if still[k]:
            npseudo += 1
        elif sfdyn2 > 0.0 and iq[k] == 0:
            an = math.sqrt(acc[k, 0] ** 2 + acc[k, 1] ** 2 + acc[k, 2] ** 2)
            wn = math.sqrt(gyr[k, 0] ** 2 + gyr[k, 1] ** 2 + gyr[k, 2] ** 2)
            if abs(an - Gv) < ggate * Gv and wn < wdyn:
                dyn[k] = True
                npseudo += 1
    Emax = M + npseudo + 1
    if do_rts:
        Pp = np.empty((Emax, NS, NS))
        Pf = np.empty((Emax, NS, NS))
        Ph = np.empty((Emax, NS, NS))
        NOM = np.empty((Emax, 16))
        DX = np.empty((Emax, NS))
        EPJ = np.empty(Emax, np.int64)
    else:
        Pp = np.empty((1, NS, NS))
        Pf = np.empty((1, NS, NS))
        Ph = np.empty((1, NS, NS))
        NOM = np.empty((1, 16))
        DX = np.empty((1, NS))
        EPJ = np.empty(1, np.int64)
    if store:
        for j in range(M):
            for a in range(2):
                o_zhat[j, a] = np.nan
                o_var[j, a] = np.nan
                o_p[j, a] = np.nan
                o_v[j, a] = np.nan
                o_bw[j, a] = np.nan
                o_nu[j, a] = np.nan
            for a in range(4):
                o_q[j, a] = np.nan
            for a in range(3):
                o_ba[j, a] = np.nan
                o_bg[j, a] = np.nan
                o_S[j, a] = np.nan
            o_nis[j] = np.nan
            o_w[j] = np.nan
    w = np.ones(M)
    x = np.zeros(12)
    q = np.zeros(4)
    P = np.zeros((NS, NS))
    R = np.zeros((3, 3))
    fN = np.zeros(3)
    T = np.zeros((NS, NS))
    T2 = np.zeros((NS, NS))
    Phi = np.zeros((NS, NS))
    H = np.zeros((3, NS))
    Rd = np.zeros(3)
    nu = np.zeros(3)
    PHt = np.zeros((NS, 3))
    S = np.zeros((3, 3))
    Si = np.zeros((3, 3))
    K = np.zeros((NS, 3))
    dx = np.zeros(NS)
    dsum = np.zeros(NS)
    es = np.zeros(NS)
    eps = np.zeros(NS)
    ll0 = 0.0
    nll0 = 0
    nreset = 0
    am = np.zeros(3)
    for it in range(n_iter + 1):
        # ---------------- initialisation at the first IMU sample
        t_cur = t_imu[i_start]
        j = 0
        while j < M and t_fix[j] < t_cur:
            j += 1
        jv = j
        while jv < M and not vis[jv]:
            jv += 1
        if jv == M:
            return ll0, nll0, nreset
        for k in range(12):
            x[k] = 0.0
        x[0] = z[jv, 0]
        x[1] = z[jv, 1]
        ux, uy, uz, cnt = 0.0, 0.0, 0.0, 0
        for k in range(i_start, min(N, i_start + 200)):
            if iq[k] == 0:
                ux += acc[k, 0]
                uy += acc[k, 1]
                uz += acc[k, 2]
                cnt += 1
        if cnt == 0:
            uz = 1.0
        nn = math.sqrt(ux * ux + uy * uy + uz * uz)
        ux, uy, uz = ux / nn, uy / nn, uz / nn
        axx, axy = uy, -ux                              # rotation axis u x e_z
        sn = math.sqrt(axx * axx + axy * axy)
        q[0], q[1], q[2], q[3] = 1.0, 0.0, 0.0, 0.0
        if sn > 1e-9:
            ang = math.atan2(sn, uz)
            q[0] = math.cos(0.5 * ang)
            q[1] = math.sin(0.5 * ang) * axx / sn
            q[2] = math.sin(0.5 * ang) * axy / sn
        _qexp_mul(q, 0.0, 0.0, yaw0, True)              # q = q_yaw (x) q_tilt
        _rot(q, R)
        am[0], am[1], am[2] = ux * Gv, uy * Gv, uz * Gv
        if it == 0:
            nreset = 0
        for a in range(NS):
            for b in range(NS):
                P[a, b] = 0.0
        for a in range(2):
            P[IP + a, IP + a] = par[K_P0P] ** 2
            P[IV + a, IV + a] = par[K_P0V] ** 2
            P[IT + a, IT + a] = par[K_P0T] ** 2
            P[IW + a, IW + a] = sb2 if sb2 > 0 else 1e-6
        P[IT + 2, IT + 2] = par[K_P0Y] ** 2
        for r in range(3):
            P[IA + r, IA + r] = par[K_P0BA] ** 2
            P[IG + r, IG + r] = par[K_P0BG] ** 2
        for a in range(NS):
            for b in range(NS):
                Phi[a, b] = 1.0 if a == b else 0.0
        qa, qg, dtp, npend = 0.0, 0.0, 0.0, 0
        e = 0
        # ---------------- forward filter
        for i in range(i_start, N - 1):
            tn = t_imu[i + 1]
            usable = iq[i] < 2
            sae2 = sasat2 if iq[i] > 0 else sa2
            sge2 = sgsat2 if iq[i] > 0 else (sgst2 if still[i] else sg2)
            while j < M and t_fix[j] < tn:
                dt = t_fix[j] - t_cur
                if dt > 0.0:
                    phw = math.exp(-dt / tb) if tb > 0 else 1.0
                    _prop(x, q, R, fN, acc[i], gyr[i], usable, dt, phw)
                    qa += sae2 * dt
                    qg += sge2 * dt
                    dtp += dt
                    t_cur = t_fix[j]
                if dtp > 0.0:
                    phw = math.exp(-dtp / tb) if tb > 0 else 1.0
                    _cov_prop(P, T, T2, R, fN, dtp, phw, qa, qg, sba2, sbg2, sb2 * (1.0 - phw * phw), do_rts, Phi)
                    qa, qg, dtp, npend = 0.0, 0.0, 0.0, 0
                if do_rts:
                    Pp[e] = P
                    Ph[e] = Phi
                    for a in range(NS):
                        for b in range(NS):
                            Phi[a, b] = 1.0 if a == b else 0.0
                for a in range(NS):
                    dsum[a] = 0.0
                use = vis[j] and (it == 0 or w[j] > 0.0)
                if use:
                    for a in range(2):
                        for b in range(NS):
                            H[a, b] = 0.0
                        H[a, IP + a] = 1.0
                        H[a, IW + a] = 1.0
                        nu[a] = z[j, a] - (x[a] + x[10 + a])
                        Rd[a] = r2w[j, a] if it == 0 else r2w[j, a] / w[j]
                    d2raw, d2u, ld = _update(P, dx, H, 2, Rd, nu, gate2 if it == 0 else -1.0, PHt, S, Si, K)
                    if it == 0:
                        ll0 += -0.5 * (d2u + ld + 2.0 * LOG2PI)
                        nll0 += 1
                        if store:
                            o_nis[j] = d2raw
                            o_nu[j, 0] = nu[0]
                            o_nu[j, 1] = nu[1]
                            o_S[j, 0] = S[0, 0]
                            o_S[j, 1] = S[0, 1]
                            o_S[j, 2] = S[1, 1]
                    _inject(x, q, dx)
                    _rot(q, R)
                    for a in range(NS):
                        dsum[a] = dx[a]
                if do_rts:
                    Pf[e] = P
                    for a in range(12):
                        NOM[e, a] = x[a]
                    for a in range(4):
                        NOM[e, 12 + a] = q[a]
                    DX[e] = dsum
                    EPJ[e] = j
                    e += 1
                elif store and it == n_iter:
                    for a in range(2):
                        o_p[j, a] = x[a]
                        o_bw[j, a] = x[10 + a]
                        o_v[j, a] = x[2 + a]
                        o_zhat[j, a] = x[a] + x[10 + a]
                        o_var[j, a] = P[IP + a, IP + a] + P[IW + a, IW + a] + 2.0 * P[IP + a, IW + a]
                    for a in range(3):
                        o_ba[j, a] = x[4 + a]
                        o_bg[j, a] = x[7 + a]
                    for a in range(4):
                        o_q[j, a] = q[a]
                j += 1
            dt = tn - t_cur
            if dt > 0.0:
                phw = math.exp(-dt / tb) if tb > 0 else 1.0
                _prop(x, q, R, fN, acc[i], gyr[i], usable, dt, phw)
                qa += sae2 * dt
                qg += sge2 * dt
                dtp += dt
                npend += 1
            t_cur = tn
            k = i + 1
            if iq[k] == 0:
                al = dt if dt < 1.0 else 1.0
                for a in range(3):
                    am[a] += (acc[k, a] - am[a]) * al
            pseudo = (still[k] or dyn[k]) and (k % pevery == 0)
            if (npend >= cevery or pseudo) and dtp > 0.0:
                phw = math.exp(-dtp / tb) if tb > 0 else 1.0
                _cov_prop(P, T, T2, R, fN, dtp, phw, qa, qg, sba2, sbg2, sb2 * (1.0 - phw * phw), do_rts, Phi)
                qa, qg, dtp, npend = 0.0, 0.0, 0.0, 0
            if pseudo:
                if do_rts:
                    Pp[e] = P
                    Ph[e] = Phi
                    for a in range(NS):
                        for b in range(NS):
                            Phi[a, b] = 1.0 if a == b else 0.0
                for a in range(NS):
                    dsum[a] = 0.0
                # tilt-reset guard: the 1-s mean specific force is ~g but points > rst away from the filter's up
                amn = math.sqrt(am[0] ** 2 + am[1] ** 2 + am[2] ** 2)
                if rst > 0.0 and abs(amn - Gv) < 0.05 * Gv:
                    _rot(q, R)
                    cang = (R[2, 0] * am[0] + R[2, 1] * am[1] + R[2, 2] * am[2]) / amn
                    if cang < math.cos(rst):
                        psi = math.atan2(R[1, 0], R[0, 0])
                        qo0, qo1, qo2, qo3 = q[0], q[1], q[2], q[3]
                        ux, uy, uz = am[0] / amn, am[1] / amn, am[2] / amn
                        sn = math.sqrt(uy * uy + ux * ux)
                        q[0], q[1], q[2], q[3] = 1.0, 0.0, 0.0, 0.0
                        if sn > 1e-9:
                            ang = math.atan2(sn, uz)
                            q[0] = math.cos(0.5 * ang)
                            q[1] = math.sin(0.5 * ang) * uy / sn
                            q[2] = -math.sin(0.5 * ang) * ux / sn
                        _qexp_mul(q, 0.0, 0.0, psi, True)
                        # global rotation from old to new: dq = q_new (x) q_old^-1 -> rotation vector
                        cw = q[0] * qo0 + q[1] * qo1 + q[2] * qo2 + q[3] * qo3
                        cx = -q[0] * qo1 + q[1] * qo0 - q[2] * qo3 + q[3] * qo2
                        cy = -q[0] * qo2 + q[1] * qo3 + q[2] * qo0 - q[3] * qo1
                        cz = -q[0] * qo3 - q[1] * qo2 + q[2] * qo1 + q[3] * qo0
                        vn = math.sqrt(cx * cx + cy * cy + cz * cz)
                        if vn > 1e-12:
                            th = 2.0 * math.atan2(vn, cw)
                            dsum[IT] += th * cx / vn
                            dsum[IT + 1] += th * cy / vn
                            dsum[IT + 2] += th * cz / vn
                        for a in range(NS):
                            for b in range(3):
                                P[IT + b, a] = 0.0
                                P[a, IT + b] = 0.0
                        P[IT, IT] = par[K_P0T] ** 2
                        P[IT + 1, IT + 1] = par[K_P0T] ** 2
                        P[IT + 2, IT + 2] = (30.0 * math.pi / 180.0) ** 2
                        _rot(q, R)
                        if it == 0:
                            nreset += 1
                if dyn[k] and not still[k]:
                    # dynamic gravity update: a_m = R^T g_up + ba, large sigma, soft chi2 gate
                    _rot(q, R)
                    for a in range(3):
                        for b in range(NS):
                            H[a, b] = 0.0
                        H[a, IT] = Gv * R[1, a]
                        H[a, IT + 1] = -Gv * R[0, a]
                        H[a, IA + a] = 1.0
                        nu[a] = acc[k, a] - (Gv * R[2, a] + x[4 + a])
                        Rd[a] = sfdyn2
                    _update(P, dx, H, 3, Rd, nu, GATE3, PHt, S, Si, K)
                    _inject(x, q, dx)
                    for a in range(NS):
                        dsum[a] += dx[a]
                    _rot(q, R)
                    if do_rts:
                        Pf[e] = P
                        for a in range(12):
                            NOM[e, a] = x[a]
                        for a in range(4):
                            NOM[e, 12 + a] = q[a]
                        DX[e] = dsum
                        EPJ[e] = -1
                        e += 1
                    continue
                # ZUPT: v = 0
                for a in range(2):
                    for b in range(NS):
                        H[a, b] = 0.0
                    H[a, IV + a] = 1.0
                    nu[a] = -x[2 + a]
                    Rd[a] = sv2
                _update(P, dx, H, 2, Rd, nu, -1.0, PHt, S, Si, K)
                _inject(x, q, dx)
                for a in range(NS):
                    dsum[a] += dx[a]
                # ZARU: w_m - bg = 0
                for a in range(3):
                    for b in range(NS):
                        H[a, b] = 0.0
                    H[a, IG + a] = 1.0
                    nu[a] = gyr[k, a] - x[7 + a]
                    Rd[a] = som2
                _update(P, dx, H, 3, Rd, nu, -1.0, PHt, S, Si, K)
                _inject(x, q, dx)
                for a in range(NS):
                    dsum[a] += dx[a]
                # gravity: a_m = R^T g_up + ba
                an = math.sqrt(acc[k, 0] ** 2 + acc[k, 1] ** 2 + acc[k, 2] ** 2)
                if iq[k] == 0 and abs(an - Gv) < ggate * Gv:
                    _rot(q, R)
                    for a in range(3):
                        for b in range(NS):
                            H[a, b] = 0.0
                        H[a, IT] = Gv * R[1, a]
                        H[a, IT + 1] = -Gv * R[0, a]
                        H[a, IA + a] = 1.0
                        nu[a] = acc[k, a] - (Gv * R[2, a] + x[4 + a])
                        Rd[a] = sf2
                    _update(P, dx, H, 3, Rd, nu, -1.0, PHt, S, Si, K)
                    _inject(x, q, dx)
                    for a in range(NS):
                        dsum[a] += dx[a]
                _rot(q, R)
                if do_rts:
                    Pf[e] = P
                    for a in range(12):
                        NOM[e, a] = x[a]
                    for a in range(4):
                        NOM[e, 12 + a] = q[a]
                    DX[e] = dsum
                    EPJ[e] = -1
                    e += 1
        if not do_rts:
            break
        # ---------------- RTS smoother (error-state form, over every epoch)
        E = e
        for a in range(NS):
            es[a] = 0.0
        Ps = Pf[E - 1].copy()
        Pj = np.empty((NS, NS))
        for ee in range(E - 1, -1, -1):
            if ee < E - 1:
                for a in range(NS):
                    eps[a] = es[a] + DX[ee + 1, a]
                A = Ph[ee + 1] @ Pf[ee]
                for a in range(NS):
                    for b in range(NS):
                        Pj[a, b] = Pp[ee + 1, a, b]
                    Pj[a, a] += 1e-12 * (1.0 + abs(Pj[a, a]))
                Ct = np.linalg.solve(Pj, A)             # = Pp^-1 Phi Pf = C^T
                for a in range(NS):
                    s_ = 0.0
                    for b in range(NS):
                        s_ += Ct[b, a] * eps[b]
                    es[a] = s_
                Ps = Pf[ee] + Ct.T @ (Ps - Pp[ee + 1]) @ Ct
            jj = EPJ[ee]
            if jj >= 0 and store:
                for a in range(2):
                    o_p[jj, a] = NOM[ee, a] + es[IP + a]
                    o_v[jj, a] = NOM[ee, 2 + a] + es[IV + a]
                    o_bw[jj, a] = NOM[ee, 10 + a] + es[IW + a]
                    o_zhat[jj, a] = o_p[jj, a] + o_bw[jj, a]
                    o_var[jj, a] = Ps[IP + a, IP + a] + Ps[IW + a, IW + a] + 2.0 * Ps[IP + a, IW + a]
                for a in range(3):
                    o_ba[jj, a] = NOM[ee, 4 + a] + es[IA + a]
                    o_bg[jj, a] = NOM[ee, 7 + a] + es[IG + a]
                qq = NOM[ee, 12:16].copy()
                _qexp_mul(qq, es[IT], es[IT + 1], es[IT + 2], True)
                for a in range(4):
                    o_q[jj, a] = qq[a]
        # ---------------- IRLS weights from the smoothed residuals (needs the stored predictions)
        if it < n_iter:
            if not store:
                break
            for jj in range(M):
                if not vis[jj] or np.isnan(o_zhat[jj, 0]):
                    continue
                m2 = 0.0
                for a in range(2):
                    rr = z[jj, a] - o_zhat[jj, a]
                    m2 += rr * rr / r2w[jj, a]
                mm = math.sqrt(m2)
                w[jj] = 1.0 if mm <= hk else hk / mm
    if store:
        for j in range(M):
            o_w[j] = w[j]
    return ll0, nll0, nreset


@njit(parallel=True, cache=True)
def _eskf_batch(t_imu, acc, gyr, iq, still, i_start, t_fix, z_s, r2tot, fmov, vis_s, pars, yaws, cz, cvis, do_rts, n_iter, store,
                o_zhat, o_var, o_p, o_v, o_bw, o_q, o_ba, o_bg, o_nu, o_S, o_nis, o_w, o_ll, o_n, o_rs):
    for c in prange(pars.shape[0]):
        ll, nn, nr = _eskf(t_imu, acc, gyr, iq, still, i_start, t_fix, z_s[cz[c]], r2tot, fmov, vis_s[cvis[c]], pars[c], yaws[c],
                       do_rts, n_iter, store, o_zhat[c], o_var[c], o_p[c], o_v[c], o_bw[c], o_q[c], o_ba[c], o_bg[c],
                       o_nu[c], o_S[c], o_nis[c], o_w[c])
        o_ll[c] = ll
        o_n[c] = nn
        o_rs[c] = nr


def make_par(c: dict, pc: dict, noise: dict) -> np.ndarray:
    """Parameter vector in filter units (in, s, rad). c = tunable (sa m/s^2/sqrt(Hz), sg rad/s/sqrt(Hz), sv in/s, tb s,
    sb in); pc = config phase_c; noise = Phase-B still-period values (sigma_omega_dps, sigma_f_ms2, sigma_g_still)."""
    p = np.zeros(NPAR)
    p[K_SA] = c["sa"] * IN_PER_M
    p[K_SG] = c["sg"]
    p[K_SBA] = pc["sigma_ba"] * IN_PER_M
    p[K_SBG] = pc["sigma_bg"]
    p[K_SV] = c["sv"]
    p[K_SOM] = noise["sigma_omega_dps"] * D2R
    p[K_SF] = noise["sigma_f_ms2"] * IN_PER_M
    p[K_TB] = c["tb"]
    p[K_SB2] = c["sb"] ** 2
    p[K_GATE] = pc["gate2"]
    p[K_SASAT] = pc["sigma_a_sat"] * IN_PER_M
    p[K_SGSAT] = pc["sigma_g_sat"]
    p[K_PEVERY] = pc["pseudo_every"]
    p[K_CEVERY] = pc["cov_every"]
    p[K_G] = G * IN_PER_M
    p[K_HUBER] = pc["huber_k"]
    p[K_P0P] = pc["p0_pos_in"]
    p[K_P0V] = pc["p0_vel_inps"]
    p[K_P0T] = pc["p0_tilt_deg"] * D2R
    p[K_P0Y] = pc["yaw0_sd_deg"] * D2R
    p[K_P0BA] = pc["p0_ba"] * IN_PER_M
    p[K_P0BG] = pc["p0_bg_dps"] * D2R
    p[K_GGATE] = 0.1
    p[K_SGSTILL] = noise["sigma_g_still"]
    p[K_SFDYN] = c.get("sfd", pc.get("sigma_f_dyn", 0.0)) * IN_PER_M
    p[K_WDYN] = pc.get("dyn_omega_max_dps", 100.0) * D2R
    p[K_RESET] = pc.get("tilt_reset_deg", 0.0) * D2R
    p[K_KR] = c.get("kr", 1.0)
    return p


class ImuIn:
    """IMU inputs of one run on the night clock (s from the night start): A3 samples inside the night +- pad, optionally
    taken from t + shift (the +1 h control), with the per-sample still flag from the pilot's per-second classes."""

    def __init__(self, a3: dict, lo: float, hi: float, shift_ms: float, st_sec: np.ndarray, sec0: int, pad_s: float = 60.0):
        t = a3["t_unix_ms"] - shift_ms
        sel = (t >= lo - pad_s * 1000.0) & (t < hi + pad_s * 1000.0)
        self.t = np.ascontiguousarray((t[sel] - lo) / 1000.0)
        self.acc = np.ascontiguousarray(a3["acc"][sel].astype(np.float64) * IN_PER_M)
        self.gyr = np.ascontiguousarray(a3["gyr"][sel].astype(np.float64) * D2R)
        nan = ~np.all(np.isfinite(a3["acc"][sel]), axis=1) | ~np.all(np.isfinite(a3["gyr"][sel]), axis=1)
        self.acc[nan] = 0.0
        self.gyr[nan] = 0.0
        self.iq = np.where(a3["frozen"][sel] | nan, 2, np.where(a3["sat_acc"][sel] | a3["sat_gyr"][sel], 1, 0)).astype(np.int8)
        s = np.floor(t[sel] / 1000.0).astype(np.int64) - int(sec0)
        inb = (s >= 0) & (s < len(st_sec))
        st = np.zeros(len(s), np.int8)
        st[inb] = st_sec[s[inb]]
        self.still = np.ascontiguousarray((st == 1) & (self.iq == 0))
        self.n = len(self.t)


def i_start_for(imu: ImuIn, t_fix: np.ndarray) -> int:
    if imu.n < 300:
        return -1
    t0 = max(float(t_fix[0]) - 1.0, float(imu.t[0]))
    return int(min(np.searchsorted(imu.t, t0), imu.n - 250))


def run_batch(imu: ImuIn, t_fix, z_list, r2tot, vis_list, pars, yaws, cz, cvis, do_rts: bool, n_iter: int, store: bool,
              chunk: int = 24, fmov=None) -> dict:
    """Run a list of filter configurations on one track (parallel over configs). fmov (M,) = fix in a non-IMU-still
    second (its white variance is multiplied by the config's k_R). Returns stacked outputs."""
    t_fix = np.ascontiguousarray(t_fix, np.float64)
    z_s = np.ascontiguousarray(np.stack(z_list), np.float64)
    vis_s = np.ascontiguousarray(np.stack(vis_list).astype(np.bool_))
    r2tot = np.ascontiguousarray(r2tot, np.float64)
    fmov = np.ascontiguousarray(np.zeros(len(t_fix), np.bool_) if fmov is None else np.asarray(fmov, np.bool_))
    i0 = i_start_for(imu, t_fix)
    C_ = len(pars)
    M = len(t_fix) if store else 1
    shapes = {"zhat": 2, "var": 2, "p": 2, "v": 2, "bw": 2, "q": 4, "ba": 3, "bg": 3, "nu": 2, "S": 3}
    out = {k: np.full((C_, M, d), np.nan) for k, d in shapes.items()}
    out["nis"] = np.full((C_, M), np.nan)
    out["w"] = np.full((C_, M), np.nan)
    out["ll"] = np.full(C_, np.nan)
    out["n"] = np.zeros(C_, np.int64)
    out["resets"] = np.zeros(C_, np.int64)
    if i0 < 0:
        return out
    for c0 in range(0, C_, chunk):
        sl = slice(c0, min(C_, c0 + chunk))
        m = sl.stop - sl.start
        o = {k: np.full((m, M, d), np.nan) for k, d in shapes.items()}
        onis, ow = np.full((m, M), np.nan), np.full((m, M), np.nan)
        oll, on, ors = np.zeros(m), np.zeros(m, np.int64), np.zeros(m, np.int64)
        _eskf_batch(imu.t, imu.acc, imu.gyr, imu.iq, imu.still, i0, t_fix, z_s, r2tot, fmov, vis_s,
                    np.ascontiguousarray(np.asarray(pars[sl], np.float64)), np.asarray(yaws[sl], np.float64),
                    np.asarray(cz[sl], np.int64), np.asarray(cvis[sl], np.int64), do_rts, n_iter, store,
                    o["zhat"], o["var"], o["p"], o["v"], o["bw"], o["q"], o["ba"], o["bg"], o["nu"], o["S"], onis, ow, oll, on, ors)
        for k in shapes:
            out[k][sl] = o[k]
        out["nis"][sl], out["w"][sl], out["ll"][sl], out["n"][sl], out["resets"][sl] = onis, ow, oll, on, ors
    return out


def yaw_grid(n: int) -> np.ndarray:
    return np.arange(n) * (2 * math.pi / n)


def select_yaw(imu: ImuIn, t_fix, z, r2tot, vis, par, n_hyp: int, mirror: bool = False, fmov=None) -> dict:
    """Forward filters over n_hyp initial yaws (and the y-mirrored WISER frame if `mirror`): pass-0 log-likelihoods."""
    yaws = yaw_grid(n_hyp)
    zl = [z] + ([z * np.array([1.0, -1.0])] if mirror else [])
    cz = np.concatenate([np.full(n_hyp, f) for f in range(len(zl))])
    pars = np.tile(par, (len(cz), 1))
    res = run_batch(imu, t_fix, zl, r2tot, [vis], pars, np.tile(yaws, len(zl)), cz, np.zeros(len(cz), np.int64),
                    False, 0, False, fmov=fmov)
    df = pd.DataFrame({"frame": np.where(cz == 0, "normal", "mirrored"), "yaw0_deg": np.degrees(np.tile(yaws, len(zl))),
                       "ll": res["ll"], "n": res["n"]})
    best = df[df.frame == "normal"].sort_values("ll", ascending=False).iloc[0]
    out = {"table": df, "yaw0": math.radians(float(best.yaw0_deg)), "ll_normal": float(best.ll)}
    if mirror:
        bm = df[df.frame == "mirrored"].sort_values("ll", ascending=False).iloc[0]
        out.update({"ll_mirrored": float(bm.ll), "yaw0_mirrored": math.radians(float(bm.yaw0_deg)),
                    "llr": float(best.ll - bm.ll), "n_upd": int(best.n)})
    return out


# ====================================================================================================== Phase C: evaluation
METHODS_BASE = ["B1", "B2", "B2p", "B2p_p", "V1", "V2", "V1_shift", "V2_shift"]
LABEL = {**P.LABEL, "V4": "V4 INS (ESKF+RTS)", "V4_shift": "V4 (IMU +1 h)"}
PAIRS_FULL = [("V4", "B2p"), ("V4_shift", "B2p"), ("B1", "B2p"), ("B2", "B2p"), ("V2", "B2p")]
PAIRS_ALL_ONLY = [("V1", "B2p"), ("V1_shift", "B2p"), ("V2_shift", "B2p"), ("B2p_p", "B2p"), ("V4", "B2"), ("V4", "V2")]


def score(tracks: dict, preds: dict, animals: list, rng: np.random.Generator, pairs_full=PAIRS_FULL,
          pairs_all=PAIRS_ALL_ONLY) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-fix held-out errors on the pilot's scored set and paired block-bootstrap comparisons (pilot's boot_delta)."""
    rows = []
    for a in animals:
        tr = tracks[a]
        for (m, s), zh in preds[a].items():
            sc = P.scored_mask(tr, ~np.isnan(zh[:, 0]))
            e = np.hypot(*(tr.z[sc] - zh[sc]).T)
            rows.append(pd.DataFrame({"animal": a, "method": m, "scheme": s, "i": np.flatnonzero(sc), "e": e,
                                      "still": tr.still[sc], "moving": tr.moving[sc], "loco": tr.loco[sc],
                                      "block": tr.block[sc], "anchors": tr.A[sc]}))
    err = pd.concat(rows, ignore_index=True)
    comps = []
    for s in ("a", "a2"):
        for subs, pairs in ((("all", "still", "moving", "loco"), pairs_full), (("all",), pairs_all)):
            for sub in subs:
                for m, ref in pairs:
                    em_all = err[(err.method == m) & (err.scheme == s)]
                    er_all = err[(err.method == ref) & (err.scheme == s)]
                    if not len(em_all) or not len(er_all):
                        continue
                    for who in animals + ["pooled"]:
                        em = em_all if who == "pooled" else em_all[em_all.animal == who]
                        er = er_all if who == "pooled" else er_all[er_all.animal == who]
                        if sub != "all":
                            em, er = em[em[sub]], er[er[sub]]
                        em = em.sort_values(["animal", "i"])
                        er = er.sort_values(["animal", "i"])
                        assert np.array_equal(em["i"].to_numpy(), er["i"].to_numpy()), f"unpaired {m} {ref} {s} {who}"
                        r = P.boot_delta(em["e"].to_numpy(), er["e"].to_numpy(), em["block"].to_numpy(), em["animal"].to_numpy(), rng)
                        comps.append({"scheme": s, "subset": sub, "method": m, "ref": ref, "animal": who, **r})
    return err, pd.DataFrame(comps)


def verdict_v4(comp: pd.DataFrame, animals: list, acc: dict) -> dict:
    per = {}
    for s in ("a", "a2"):
        c = comp[(comp.scheme == s) & (comp.subset == "all") & (comp.ref == "B2p")]
        main = c[(c.method == "V4") & c.animal.isin(animals)]
        ctrl = c[(c.method == "V4_shift") & c.animal.isin(animals)]
        n_pass = int(((main.d_med >= acc["min_gain"]) & (main.lo > 0)).sum())
        n_ctrl = int((ctrl.lo <= 0).sum())
        mv = comp[(comp.scheme == s) & (comp.subset == "moving") & (comp.method == "V4") & (comp.ref == "B2p") & (comp.animal == "pooled")]
        d_mov = float(mv.d_med.iloc[0]) if len(mv) else np.nan
        ctrl_ok = n_ctrl >= acc["min_animals"]
        mov_ok = bool(np.isfinite(d_mov) and d_mov >= acc["moving_max_loss"])
        if n_pass >= acc["min_animals"] and ctrl_ok and mov_ok:
            v = "ACCEPTED"
        elif n_pass == acc["min_animals"] - 1 or (n_pass >= acc["min_animals"] and not ctrl_ok):
            v = "INCONCLUSIVE"
        else:
            v = "FAIL"
        per[s] = {"n_animals_gain": n_pass, "n_control_no_gain": n_ctrl, "pooled_moving_d": d_mov, "control_ok": ctrl_ok,
                  "moving_ok": mov_ok, "verdict": v}
    rank = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "FAIL": 0}
    return {"schemes": per, "verdict": max((p["verdict"] for p in per.values()), key=lambda x: rank[x])}


def v4_track(tr, a3: dict, lo: float, hi: float, table: dict) -> dict:
    """True-clock and +1 h-shifted IMU inputs + WISER arrays of one Track."""
    secs = tr.ps["sec"].to_numpy()
    secs_s = tr.ps_shift["sec"].to_numpy() - 3600
    return {"imu": ImuIn(a3, lo, hi, 0.0, tr.st_sec, int(secs[0])),
            "imu_shift": ImuIn(a3, lo, hi, 3.6e6, tr.st_sec_shift, int(secs_s[0])),
            "r2tot": P.r2_from_anchors(tr.A, table),
            "fmov": ~(tr.st_at == 1), "fmov_shift": ~(tr.st_at_shift == 1)}


def tune_v4(tracks: dict, vt: dict, hidden: dict, pc: dict, noise: dict, log) -> tuple[dict, dict, dict]:
    """Tuning night, scheme (a): initial yaw per animal from the default config, then the two-stage grid; objective =
    pooled median held-out error on the pilot's scored set (tie: RMSE)."""
    animals = list(tracks)
    d0 = dict(pc["default"])
    yaw = {}
    hyp_rows = []
    t0 = time.time()
    for a in animals:
        tr, v = tracks[a], vt[a]
        sel = select_yaw(v["imu"], tr.t, tr.z, v["r2tot"], ~hidden[a]["a"], make_par(d0, pc, noise), pc["n_yaw_hyp"], fmov=v["fmov"])
        yaw[a] = sel["yaw0"]
        hyp_rows.append(sel["table"].assign(animal=a, run="tune_a"))
    log(f"tune V4: initial yaw per animal (default config) {', '.join(f'{a} {math.degrees(y):.0f}' for a, y in yaw.items())} "
        f"({time.time() - t0:.0f} s)")

    def evaluate(cfgs):
        errs = [[] for _ in cfgs]
        for a in animals:
            tr, v = tracks[a], vt[a]
            h = hidden[a]["a"]
            sc = P.scored_mask(tr, h)
            pars = np.stack([make_par(c, pc, noise) for c in cfgs])
            r = run_batch(v["imu"], tr.t, [tr.z], v["r2tot"], [~h], pars, np.full(len(cfgs), yaw[a]),
                          np.zeros(len(cfgs), np.int64), np.zeros(len(cfgs), np.int64), True, int(pc["n_irls"]), True, chunk=12,
                          fmov=v["fmov"])
            for i in range(len(cfgs)):
                zh = r["zhat"][i]
                ok = sc & np.isfinite(zh[:, 0])
                zz = np.where(ok[:, None], zh, np.nan)
                e = np.hypot(*(tr.z[sc] - zz[sc]).T)
                errs[i].append(np.where(np.isfinite(e), e, np.nan))
        out = []
        for c, e in zip(cfgs, errs):
            e = np.concatenate(e)
            n_nan = int(np.isnan(e).sum())
            e = e[np.isfinite(e)]
            out.append({**c, "med": float(np.median(e)), "rmse": float(np.sqrt(np.mean(e ** 2))), "n": int(len(e)), "n_nan": n_nan})
        return out

    def best(r):
        return min(r, key=lambda x: (round(x["med"], 4), x["rmse"]))

    g1 = [{**d0, "sa": sa, "sg": sg, "sfd": sfd} for sa in pc["grid_stage1"]["sa"] for sg in pc["grid_stage1"]["sg"]
          for sfd in pc["grid_stage1"]["sfd"]]
    r1 = evaluate(g1)
    b1 = best(r1)
    log(f"tune V4 stage 1: sa {b1['sa']} sg {b1['sg']} sfd {b1['sfd']} -> med {b1['med']:.3f} ({time.time() - t0:.0f} s)")
    g2 = [{**b1, "sv": sv, "tb": tb, "sb": sb, "kr": kr} for sv in pc["grid_stage2"]["sv"] for tb, sb in pc["grid_stage2"]["drift"]
          for kr in pc["grid_stage2"]["kr"]]
    g2 = [{k: v for k, v in c.items() if k in ("sa", "sg", "sfd", "sv", "tb", "sb", "kr")} for c in g2]
    r2 = evaluate(g2)
    b2 = best(r2)
    log(f"tune V4 stage 2: sv {b2['sv']} tb {b2['tb']} sb {b2['sb']} kr {b2['kr']} -> med {b2['med']:.3f} ({time.time() - t0:.0f} s)")
    tuned = {k: b2[k] for k in ("sa", "sg", "sfd", "sv", "tb", "sb", "kr")}
    tuned["med"] = b2["med"]
    return tuned, {"stage1": r1, "stage2": r2}, {"yaw": yaw, "hyp": pd.concat(hyp_rows, ignore_index=True)}


def v4_night(tracks: dict, vt: dict, hidden: dict, par: np.ndarray, pc: dict, log, night: str, schemes=("a", "a2"),
             controls: bool = True) -> dict:
    """Per animal: yaw hypotheses (full data with the mirrored frame; each held-out scheme on its own visible fixes; the
    same for the +1 h control), then the ML hypothesis smoothed (RTS + IRLS). Returns predictions, full-data outputs,
    hypothesis tables and handedness."""
    out = {"pred": {}, "full": {}, "hyp": [], "hand": {}, "shift_pred": {}, "fill": {}}
    n_hyp, n_irls = int(pc["n_yaw_hyp"]), int(pc["n_irls"])
    for a, tr in tracks.items():
        t0 = time.time()
        v = vt[a]
        vis_full = np.ones(tr.n, bool)
        sel_f = select_yaw(v["imu"], tr.t, tr.z, v["r2tot"], vis_full, par, n_hyp, mirror=True, fmov=v["fmov"])
        out["hyp"].append(sel_f["table"].assign(animal=a, run="full", night=night))
        out["hand"][a] = {k: sel_f[k] for k in ("ll_normal", "ll_mirrored", "llr", "n_upd")} | {
            "yaw0_deg": math.degrees(sel_f["yaw0"]), "yaw0_mirrored_deg": math.degrees(sel_f["yaw0_mirrored"])}
        vis_list, yaws, labels = [vis_full], [sel_f["yaw0"]], ["full"]
        for s in schemes:
            sel = select_yaw(v["imu"], tr.t, tr.z, v["r2tot"], ~hidden[a][s], par, n_hyp, fmov=v["fmov"])
            out["hyp"].append(sel["table"].assign(animal=a, run=s, night=night))
            vis_list.append(~hidden[a][s])
            yaws.append(sel["yaw0"])
            labels.append(s)
        C_ = len(vis_list)
        r = run_batch(v["imu"], tr.t, [tr.z], v["r2tot"], vis_list, np.tile(par, (C_, 1)), yaws, np.zeros(C_, np.int64),
                      np.arange(C_), True, n_irls, True, fmov=v["fmov"])
        out["full"][a] = {k: (val[0] if isinstance(val, np.ndarray) and val.ndim >= 1 and val.shape[0] == C_ else val)
                          for k, val in r.items()}
        out["full"][a]["yaw0"] = sel_f["yaw0"]
        out["pred"][a] = {}
        for i, s in enumerate(labels[1:], start=1):
            out["pred"][a][s] = {"zhat": np.where(hidden[a][s][:, None], r["zhat"][i], np.nan),
                                 "var": np.where(hidden[a][s][:, None], r["var"][i], np.nan), "yaw0": yaws[i]}
        if controls:
            vl, yl = [], []
            for s in schemes:
                sel = select_yaw(v["imu_shift"], tr.t, tr.z, v["r2tot"], ~hidden[a][s], par, n_hyp, fmov=v["fmov_shift"])
                out["hyp"].append(sel["table"].assign(animal=a, run=f"shift_{s}", night=night))
                vl.append(~hidden[a][s])
                yl.append(sel["yaw0"])
            rs = run_batch(v["imu_shift"], tr.t, [tr.z], v["r2tot"], vl, np.tile(par, (len(vl), 1)), yl,
                           np.zeros(len(vl), np.int64), np.arange(len(vl)), True, n_irls, True, fmov=v["fmov_shift"])
            out["shift_pred"][a] = {s: {"zhat": np.where(hidden[a][s][:, None], rs["zhat"][i], np.nan),
                                        "var": np.where(hidden[a][s][:, None], rs["var"][i], np.nan), "yaw0": yl[i]}
                                    for i, s in enumerate(schemes)}
        out["hand"][a]["tilt_resets_full"] = int(r["resets"][0])
        log(f"V4 {night} {a}: yaw0 {math.degrees(sel_f['yaw0']):.0f} deg, LLR normal-mirrored {sel_f['llr']:+.1f}, tilt resets {int(r['resets'][0])} "
            f"({sel_f['n_upd']} fixes), {time.time() - t0:.0f} s")
    return out


# ====================================================================================================== driver
def _jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def context(cohort: str) -> dict:
    coh = load_cohort(cohort)
    cfg_path = REPO / "wiser" / "configs" / f"wiser_ins_fusion_{cohort}.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    scfg = json.loads((REPO / cfg["smoothing_config"]).read_text(encoding="utf-8"))
    tz = cfg.get("tz", "America/New_York")
    ids = pd.read_csv(REPO / coh["identities"], dtype={"shortid": int, "physical_tag_id": str})
    ids["from_ms"] = pd.to_datetime(ids["valid_from"], utc=True).astype("int64") // 10**6
    ids["until_ms"] = pd.to_datetime(ids["valid_until"], utc=True).astype("int64") // 10**6
    hj = json.loads((REPO / scfg["handling_json"]).read_text(encoding="utf-8"))
    handling = [(C.to_ms(a, tz), C.to_ms(b, tz), note) for a, b, note in hj["windows"]]
    sil = pd.read_csv(scfg["silences_csv"])
    pad = scfg["silence_pad_s"] * 1000
    silences = [(C.to_ms(r.start, tz) - pad, C.to_ms(r.end, tz) + pad, r.kind) for r in sil.itertuples()]
    adc = [(C.to_ms(wd["on_from"], tz), C.to_ms(wd["off_at"], tz), wd["animal"])
           for wd in ((coh.get("ephys") or {}).get("adc_lane") or {}).get("on_windows", [])]
    roots = {k: Path(v) for k, v in cfg["cache_roots"].items()}
    return {"cohort": cohort, "coh": coh, "cfg": cfg, "cfg_path": cfg_path, "scfg": scfg, "tz": tz, "ids": ids,
            "handling": handling, "silences": silences, "adc": adc, "roots": roots, "thr": C.imu_still_thr(),
            "a1_index": pd.read_csv(roots["imu_raw"] / f"index_{cohort}.csv")}


def night_info(ctx: dict, key: str) -> dict:
    night = ctx["scfg"]["nights"][key]
    lo, hi = C.to_ms(night["start"], ctx["tz"]), C.to_ms(night["end"], ctx["tz"])
    animals = list(night["sessions"])
    tags = {a: C.resolve_tag(ctx["ids"], a, lo, hi) for a in animals}
    return {"key": key, "night": night, "lo": lo, "hi": hi, "animals": animals, "tags": tags, "nk": BC.night_key(night["start"])}


def imu_seconds(ctx: dict, ni: dict, a: str, lo: float, hi: float) -> pd.DataFrame:
    """The smoothing pilot's per-second IMU table (QC mask + still rule + SBF) from the make_imu npz, unchanged."""
    s = ni["night"]["sessions"][a]
    root = Path(ctx["cfg"]["imu_npz_root"]) / a
    side = json.loads((root / f"{s}.imu.json").read_text(encoding="utf-8"))
    vf, vu = C.tag_window(ctx["ids"], ni["tags"][a], a, (ni["lo"] + ni["hi"]) / 2)
    adc_a = [wd for wd in ctx["adc"] if wd[2] == a]
    return P.load_imu_seconds(root / f"{s}.imu.npz", side["start_local"], lo, hi, ctx["handling"], ctx["silences"], adc_a,
                              vf, vu, ctx["thr"][a])


def phase_b(ctx: dict, workers: int, log, out: Path) -> dict:
    cfg, pb = ctx["cfg"], ctx["cfg"]["phase_b"]
    seed = ctx["scfg"]["seed"]
    jobs = {}
    for key in ("tuning", "test"):
        ni = night_info(ctx, key)
        for i, a in enumerate(ni["animals"]):
            row = ctx["a1_index"][(ctx["a1_index"].animal == a) & (ctx["a1_index"].night == ni["nk"])]
            if len(row) != 1:
                raise SystemExit(f"A1 cache row for {a} {ni['nk']}: {len(row)} (run build_imu_wiser_cache.py first)")
            path = Path(row.path.iloc[0])
            with np.load(path) as zz:
                meta = json.loads(str(zz["meta_json"]))
            w0, w1 = meta["window_actual_unix_ms"]
            ps = imu_seconds(ctx, ni, a, w0, w1 + 1000.0)
            jobs[(key, a)] = {"a1": str(path), "animal": a, "night": ni["nk"], "role": key, "session": meta["session"],
                              "sec": ps["sec"].to_numpy(), "ok": ps["ok"].to_numpy(bool), "still": ps["still"].to_numpy(bool),
                              "lo": ni["lo"], "hi": ni["hi"], "seed": seed + i, "pb": pb, "fc": None}
    t0 = time.time()
    tune_keys = [k for k in jobs if k[0] == "tuning"]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        s1 = dict(zip(tune_keys, ex.map(b_worker, [jobs[k] for k in tune_keys])))
    log(f"Phase B stage 1 (tuning PSDs) {time.time() - t0:.0f} s")
    f = s1[tune_keys[0]]["psd"]["f"]
    pooled = {c: np.nanmean([s1[k]["psd"][c] for k in tune_keys], axis=0) for c in ("still", "moving", "still_raw", "moving_raw")}
    cut = {}
    for grp, sl in (("acc", slice(0, 3)), ("gyr", slice(3, 6))):
        cut[grp] = cutoff_rule(f, pooled["still"][:, sl].sum(axis=1), pooled["moving"][:, sl].sum(axis=1), pb)
        cut[grp]["per_animal"] = {k[1]: cutoff_rule(f, s1[k]["psd"]["still"][:, sl].sum(axis=1),
                                                    s1[k]["psd"]["moving"][:, sl].sum(axis=1), pb)["fc_raw_hz"] for k in tune_keys}
    fc = {"acc": cut["acc"]["fc_hz"], "gyr": cut["gyr"]["fc_hz"]}
    log(f"cutoffs (tuning night, pooled): acc {fc['acc']:.1f} Hz (raw {cut['acc']['fc_raw_hz']:.1f}), gyro {fc['gyr']:.1f} Hz "
        f"(raw {cut['gyr']['fc_raw_hz']:.1f})")
    for k in jobs:
        jobs[k]["fc"] = fc
    t0 = time.time()
    keys = list(jobs)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        s2 = dict(zip(keys, ex.map(b_worker, [jobs[k] for k in keys])))
    log(f"Phase B stage 2 (chains, calibration candidates, metrics) {time.time() - t0:.0f} s")
    # ---------------- decisions on the tuning night
    n_ell = sum(1 for k in tune_keys if s2[k]["acc_cv"]["ellipsoid"] < s2[k]["acc_cv"]["scalar"])
    acc_method = "ellipsoid" if n_ell >= pb["ellipsoid_min_animals"] else "scalar"
    d_blk = np.concatenate([s2[k]["drift"]["after_block"] for k in tune_keys])
    d_run = np.concatenate([s2[k]["drift"]["after_running"] for k in tune_keys])
    bias_method = "running" if np.median(d_run) < np.median(d_blk) else "block"
    grid = s2[tune_keys[0]]["sds"]["grid"]
    E = np.concatenate([s2[k]["sds"]["err"] for k in tune_keys], axis=0)
    obj = (E ** 2).sum(axis=0)
    s_star = float(grid[int(np.argmin(obj))])
    rng = np.random.default_rng(seed + 77)
    cnt = rng.multinomial(len(E), np.full(len(E), 1.0 / len(E)), size=1000) if len(E) else np.zeros((1000, 0))
    sb = grid[np.argmin(cnt @ (E ** 2), axis=1)] if len(E) else np.full(1000, np.nan)
    s_lo, s_hi = (float(np.percentile(sb, 2.5)), float(np.percentile(sb, 97.5))) if len(E) else (np.nan, np.nan)
    apply_s = bool(len(E) and (s_lo > 1.0 or s_hi < 1.0) and abs(s_star - 1.0) > pb["gyro_scale_min_effect"])
    gscale = s_star if apply_s else 1.0
    per_animal_s = {k[1]: float(grid[int(np.argmin((s2[k]["sds"]["err"] ** 2).sum(axis=0)))]) if len(s2[k]["sds"]["err"]) else np.nan
                    for k in tune_keys}
    Eb = np.concatenate([s2[k]["sds_err_before"] for k in tune_keys], axis=0)
    s_before = float(grid[int(np.argmin((Eb ** 2).sum(axis=0)))]) if len(Eb) else np.nan
    sig_om = float(np.nanmedian([s2[k]["still_noise"]["gyr_rms"] for k in tune_keys]))
    sig_f = float(np.nanmedian([s2[k]["still_noise"]["acc_rms"] for k in tune_keys]))
    pc = cfg["phase_c"]
    noise = {"sigma_omega_dps": max(pc["sigma_omega_floor_dps"], sig_om * gscale), "sigma_f_ms2": max(pc["sigma_f_floor"], sig_f),
             "sigma_g_still": float(math.sqrt(cut["gyr"]["noise_floor"] / 3.0 / 2.0)) * D2R * gscale,
             "sigma_omega_measured_dps": sig_om, "sigma_f_measured_ms2": sig_f}
    decisions = {"fc": fc, "cutoff": cut, "acc_method": acc_method, "n_ellipsoid_better": n_ell, "bias_method": bias_method,
                 "drift_med_block": float(np.median(d_blk)), "drift_med_running": float(np.median(d_run)),
                 "gyro_scale": gscale, "gyro_scale_star": s_star, "gyro_scale_ci": [s_lo, s_hi], "gyro_scale_applied": apply_s,
                 "gyro_scale_per_animal": per_animal_s, "gyro_scale_before_chain": s_before, "n_sds_pairs": int(len(E)),
                 "noise": noise}
    log(f"decisions: acc {acc_method} ({n_ell}/5 better), bias {bias_method} (LOO drift med block {np.median(d_blk):.4f} vs "
        f"running {np.median(d_run):.4f} deg/s), gyro scale s* {s_star:.3f} [{s_lo:.3f}, {s_hi:.3f}] -> {gscale:.3f} "
        f"({len(E)} pairs); sigma_omega {noise['sigma_omega_dps']:.3f} deg/s, sigma_f {noise['sigma_f_ms2']:.3f} m/s^2, "
        f"sigma_g_still {noise['sigma_g_still']:.2e} rad/s/sqrt(Hz)")
    # ---------------- A3 caches
    a3_paths, fus_jobs, rows = {}, [], []
    (out / "phase_b").mkdir(exist_ok=True)
    for k, r in s2.items():
        ar = r["arrays"]
        if acc_method == "ellipsoid" and r["acc_fit"]["ellipsoid"] is not None:
            cal = {"method": "ellipsoid", "D": r["acc_fit"]["ellipsoid"]["D"], "o": r["acc_fit"]["ellipsoid"]["o"]}
        else:
            cal = {"method": "scalar", "k_a": r["acc_fit"]["scalar_k_a"]}
        a = apply_acc(ar["a_lp"].astype(np.float64), cal)
        bias = ar["bias_running"] if bias_method == "running" else ar["bias_block"]
        w = gscale * (ar["w_lp"].astype(np.float64) - bias)
        t100 = ar["t100"]
        tb = np.arange(0, len(t100), 6000)
        calib = {"acc": cal, "gyro_bias_method": bias_method, "gyro_scale": gscale, "fc_hz": fc,
                 "bias_nodes_1min": {"t_unix_ms": t100[tb].tolist(), "bias_dps": np.asarray(bias)[tb].tolist()},
                 "hampel": {"half_window": pb["hampel_half_window"], "nsigma": pb["hampel_nsigma"], "mad_floor_counts": pb["hampel_mad_floor_counts"]},
                 "butter_order": pb["butter_order"], "axis_map_S": MI.S.tolist(), "resample": "resample_poly(2, 25)",
                 "decided_on": "tuning night 2026-09-08/09 (cutoffs, acc method, bias method, gyro scale); ellipsoid/bias self-calibrated per night"}
        meta = {"animal": r["animal"], "night": r["night"], "role": k[0], "session": jobs[k]["session"], "source_a1": jobs[k]["a1"],
                "t_clock": "field-PC Unix ms on the IMU clock (tau* NOT applied)", "units": {"acc": "m/s^2 head frame", "gyr": "deg/s head frame"},
                "git_commit": C.git_commit(), "written_local": pd.Timestamp.now(tz=ctx["tz"]).isoformat(timespec="seconds"),
                "writer": "wiser/scripts/analyze_wiser_ins_fusion.py"}
        od = ctx["roots"]["imu100"] / r["animal"]
        od.mkdir(parents=True, exist_ok=True)
        p3 = od / f"{r['night']}.npz"
        np.savez_compressed(p3, t_unix_ms=t100, acc=a.astype(np.float32), gyr=w.astype(np.float32), sat_acc=ar["sat_acc"],
                            sat_gyr=ar["sat_gyr"], frozen=ar["frozen"], spikes=ar["spikes"], quiet=ar["quiet"],
                            calib_json=np.array(json.dumps(calib, default=_jd)), meta_json=np.array(json.dumps(meta, default=_jd)))
        a3_paths[k] = p3
        np.savez_compressed(out / "phase_b" / f"psd_{r['night']}_{r['animal']}.npz", f=r["psd"]["f"], still=r["psd"]["still"],
                            moving=r["psd"]["moving"], still_raw=r["psd"]["still_raw"], moving_raw=r["psd"]["moving_raw"],
                            sds_err=r["sds"]["err"], sds_grid=r["sds"]["grid"], sds_tilt=r["sds"]["tilt_deg"])
        # Fusion stability jobs (night window)
        sel = ar["night_sel"]
        st = ar["still100"][sel]
        runs_idx = [(s0, e0) for s0, e0 in C.true_runs(st) if e0 - s0 >= int(pb["still_run_min_s"] * FS100)]
        qs_idx = np.flatnonzero(ar["quiet"][sel])[::10]
        for chain, aa, ww in (("before", ar["a_bef_night"], ar["w_bef_night"]), ("after", a[sel].astype(np.float32), w[sel].astype(np.float32))):
            fus_jobs.append({"animal": r["animal"], "night": r["night"], "chain": chain, "a": aa, "w": ww, "runs_idx": runs_idx, "qs_idx": qs_idx})
        kin_after = r.get("kin_after_ellipsoid") if cal["method"] == "ellipsoid" else r["kin_after_scalar"]
        dr_after = np.asarray(r["drift"]["after_running" if bias_method == "running" else "after_block"]) * gscale
        rows.append({"night": r["night"], "role": k[0], "animal": r["animal"], "a3": str(p3), "a3_bytes": p3.stat().st_size,
                     "acc_method": cal["method"], "grav_cv_scalar": r["acc_cv"]["scalar"], "grav_cv_ellipsoid": r["acc_cv"]["ellipsoid"],
                     "grav_before_makeimu": r["grav_resid_before_all"], "n_qs_windows": r["acc_fit"]["n_windows"],
                     "cov_eig_min": r["acc_cov_eig"][0], "make_imu_k_a": r["acc_fit"]["make_imu_k_a"], "scalar_k_a": r["acc_fit"]["scalar_k_a"],
                     "ell_D": json.dumps(np.round(r["acc_fit"]["ellipsoid"]["D"], 4).tolist()) if r["acc_fit"]["ellipsoid"] else "",
                     "ell_o": json.dumps(np.round(r["acc_fit"]["ellipsoid"]["o"], 4).tolist()) if r["acc_fit"]["ellipsoid"] else "",
                     "drift_before_med": float(np.median(r["drift"]["before_block"])) if len(r["drift"]["before_block"]) else np.nan,
                     "drift_before_p90": float(np.percentile(r["drift"]["before_block"], 90)) if len(r["drift"]["before_block"]) else np.nan,
                     "drift_after_med": float(np.median(dr_after)) if len(dr_after) else np.nan,
                     "drift_after_p90": float(np.percentile(dr_after, 90)) if len(dr_after) else np.nan,
                     "drift_after_block_med": float(np.median(r["drift"]["after_block"])) if len(r["drift"]["after_block"]) else np.nan,
                     "drift_after_running_med": float(np.median(r["drift"]["after_running"])) if len(r["drift"]["after_running"]) else np.nan,
                     "n_still_runs": r["n_still_runs"],
                     "kin_before_r": r["kin_before"]["r"], "kin_before_slope": r["kin_before"]["slope"],
                     "kin_after_r": kin_after["r"], "kin_after_slope": kin_after["slope"] / gscale, "kin_n": kin_after["n"],
                     "kin_latency_ms": r["kin_latency"]["peak_ms"], "kin_latency_r_peak": r["kin_latency"]["r_peak"],
                     "sds_pairs": int(len(r["sds"]["err"])),
                     "sds_s_star": float(grid[int(np.argmin((r["sds"]["err"] ** 2).sum(axis=0)))]) if len(r["sds"]["err"]) else np.nan,
                     "alpha_before_p9999": r["alpha_before"][99.99], "alpha_after_p9999": r["alpha_after"][99.99],
                     "alpha_before_max": r["alpha_before"]["max"], "alpha_after_max": r["alpha_after"]["max"],
                     "still_gyr_rms": r["still_noise"]["gyr_rms"], "still_acc_rms": r["still_noise"]["acc_rms"],
                     "sat_any_seconds": r["sat_any_seconds"], "elapsed_s": r["elapsed_s"],
                     **{f"sat_lane{s_['lane']}": s_["samples"] for s_ in r["saturation"]},
                     **{f"sat_lane{s_['lane']}_longest_ms": s_["longest_ms"] for s_ in r["saturation"]},
                     **{f"spk_lane{s_['lane']}": s_["total"] for s_ in r["spikes"]},
                     **{f"spk_lane{s_['lane']}_still_per_h": s_["still"] / max(s_["still_frames"] / FS_RAW / 3600, 1e-9) for s_ in r["spikes"]},
                     **{f"spk_lane{s_['lane']}_moving_per_h": s_["moving"] / max(s_["moving_frames"] / FS_RAW / 3600, 1e-9) for s_ in r["spikes"]}})
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=min(10, len(fus_jobs))) as ex:
        fus = list(ex.map(fusion_worker, fus_jobs))
    log(f"Fusion stability (before vs after) {time.time() - t0:.0f} s")
    q = pd.DataFrame(rows)
    fdf = pd.DataFrame(fus)
    for chain in ("before", "after"):
        f_ = fdf[fdf.chain == chain].set_index(["night", "animal"])
        for col in ("pitch_sd_still_med", "roll_sd_still_med", "unreliable_frac", "grav_vs_acc_deg_med"):
            q[f"fus_{chain}_{col}"] = [f_.loc[(n_, a_), col] for n_, a_ in zip(q.night, q.animal)]
    q.to_csv(out / "csv" / "imu_quality.csv", index=False)
    pd.DataFrame([{"lane": s_["lane"], "night": r["night"], "animal": r["animal"], **s_} for r in s2.values() for s_ in r["saturation"]]).to_csv(
        out / "csv" / "imu_saturation_lanes.csv", index=False)
    pd.DataFrame([{"night": r["night"], "animal": r["animal"], **s_} for r in s2.values() for s_ in r["spikes"]]).to_csv(
        out / "csv" / "imu_spikes_lanes.csv", index=False)
    np.savez_compressed(out / "phase_b" / "psd_pooled_tuning.npz", f=f, **pooled)
    return {"decisions": decisions, "quality": q, "a3_paths": {f"{k[0]}|{k[1]}": str(v) for k, v in a3_paths.items()},
            "a3": a3_paths, "noise": noise, "psd_f": f, "psd_pooled": pooled}


def load_a3(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def phase_c(ctx: dict, pbres: dict, log, out: Path) -> dict:
    cfg, scfg = ctx["cfg"], ctx["scfg"]
    pc = cfg["phase_c"]
    ptuned = scfg["tuned"]
    table = {int(k): v for k, v in ptuned["anchor_sigma"].items()}
    loco = ptuned["loco"]
    noise = pbres["noise"]
    taus = scfg["tau_star_s"]
    seed = scfg["seed"]
    res = {"nights": {}}

    def build(key):
        ni = night_info(ctx, key)
        tracks, vt, info = {}, {}, {}
        for a in ni["animals"]:
            fx = pd.read_csv(ctx["roots"]["wiser_fix"] / ni["nk"] / f"{a}.csv.gz")
            ps = imu_seconds(ctx, ni, a, ni["lo"], ni["hi"])
            ps_s = imu_seconds(ctx, ni, a, ni["lo"] + 3.6e6, ni["hi"] + 3.6e6)
            tr = P.Track(fx, ni["lo"], ni["hi"], taus[a])
            tr.attach_imu(ps, ps_s, loco["theta_l"], loco["rho_l"])
            tr.ps_shift = ps_s
            tracks[a] = tr
            a3 = load_a3(pbres["a3"][(key, a)])
            vt[a] = v4_track(tr, a3, ni["lo"], ni["hi"], table)
            info[a] = {"n_fix": tr.n, "tag": ni["tags"][a], "imu_samples": vt[a]["imu"].n, "imu_shift_samples": vt[a]["imu_shift"].n,
                       "still_samples": int(vt[a]["imu"].still.sum()), "sat_samples": int((vt[a]["imu"].iq == 1).sum()),
                       "imu_t0_s": float(vt[a]["imu"].t[0]) if vt[a]["imu"].n else np.nan}
            pd.concat([ps.assign(which="true"), ps_s.assign(which="shift")]).drop(columns=["_cum_turn_at_start"], errors="ignore").to_csv(
                out / "persecond" / f"{ni['nk']}_{a}.csv.gz", index=False)
        return ni, tracks, vt, info

    (out / "persecond").mkdir(exist_ok=True)
    # ---------------- tuning night
    t0 = time.time()
    ni_t, tr_t, vt_t, info_t = build("tuning")
    hid_t = {a: P.make_hidden(tr_t[a], seed + i) for i, a in enumerate(ni_t["animals"])}
    log(f"tuning tracks built ({time.time() - t0:.0f} s): " + ", ".join(f"{a} {info_t[a]['n_fix']:,}" for a in ni_t["animals"]))
    tuned, grids, tsel = tune_v4(tr_t, vt_t, hid_t, pc, noise, log)
    par = make_par(tuned, pc, noise)
    vn_t = v4_night(tr_t, vt_t, hid_t, par, pc, log, ni_t["nk"])
    preds_t = {}
    for a in ni_t["animals"]:
        preds_t[a] = P.predict_all(tr_t[a], table, ptuned, hid_t[a])
        for s in ("a", "a2"):
            preds_t[a][("V4", s)] = vn_t["pred"][a][s]["zhat"]
            preds_t[a][("V4_shift", s)] = vn_t["shift_pred"][a][s]["zhat"]
    fill_nan(preds_t, "tuning", res, log)
    err_t, comp_t = score(tr_t, preds_t, ni_t["animals"], np.random.default_rng(seed + cfg["seed_offsets"]["boot_tuning"]))
    log(f"tuning night scored ({time.time() - t0:.0f} s)")
    # ---------------- test night
    t0 = time.time()
    ni_e, tr_e, vt_e, info_e = build("test")
    hid_e = {a: P.make_hidden(tr_e[a], seed + 1000 + i) for i, a in enumerate(ni_e["animals"])}
    vn_e = v4_night(tr_e, vt_e, hid_e, par, pc, log, ni_e["nk"])
    preds_e = {}
    for a in ni_e["animals"]:
        preds_e[a] = P.predict_all(tr_e[a], table, ptuned, hid_e[a])
        for s in ("a", "a2"):
            preds_e[a][("V4", s)] = vn_e["pred"][a][s]["zhat"]
            preds_e[a][("V4_shift", s)] = vn_e["shift_pred"][a][s]["zhat"]
    fill_nan(preds_e, "test", res, log)
    err_e, comp_e = score(tr_e, preds_e, ni_e["animals"], np.random.default_rng(seed + cfg["seed_offsets"]["boot_test"]))
    ver = verdict_v4(comp_e, ni_e["animals"], cfg["accept"])
    log(f"test night scored ({time.time() - t0:.0f} s); V4 verdict {ver['verdict']}: " + "; ".join(
        f"{s}: {p['n_animals_gain']}/5 gain, control ok {p['n_control_no_gain']}/5, moving {p['pooled_moving_d']:+.3f}"
        for s, p in ver["schemes"].items()))
    # ---------------- NIS, held-out z, plausibility, saved intermediates
    walls = json.loads(Path(scfg["walls_json"]).read_text(encoding="utf-8"))
    nis_rows, plaus, example = [], [], None
    for key, ni, trs, vts, vn, hid in (("tuning", ni_t, tr_t, vt_t, vn_t, hid_t), ("test", ni_e, tr_e, vt_e, vn_e, hid_e)):
        for a in ni["animals"]:
            tr, fu = trs[a], vn["full"][a]
            r2w = np.maximum(vts[a]["r2tot"] - tuned["sb"] ** 2, 0.25 * vts[a]["r2tot"]) * np.where(vts[a]["fmov"], tuned.get("kr", 1.0), 1.0)[:, None]
            nis = fu["nis"]
            ok = np.isfinite(nis)
            hi7 = ok & (tr.A >= 7)
            row = {"night": ni["nk"], "animal": a, "n": int(ok.sum()), "nis_mean": float(np.mean(nis[ok])),
                   "nis_median": float(np.median(nis[ok])), "frac_gt_5.99": float(np.mean(nis[ok] > 5.99)),
                   "nis_mean_ge7": float(np.mean(nis[hi7])), "frac_gt_5.99_ge7": float(np.mean(nis[hi7] > 5.99)),
                   "irls_w_lt1": float(np.mean(fu["w"][np.isfinite(fu["w"])] < 1.0))}
            for s in ("a", "a2"):
                pr = vn["pred"][a][s]
                sc = P.scored_mask(tr, np.isfinite(pr["zhat"][:, 0]))
                z2 = np.sum((tr.z[sc] - pr["zhat"][sc]) ** 2 / (pr["var"][sc] + r2w[sc]), axis=1)
                row[f"heldout_z2_mean_{s}"] = float(np.mean(z2))
                row[f"heldout_frac_gt_5.99_{s}"] = float(np.mean(z2 > 5.99))
            nis_rows.append(row)
            fd = out / "fusion" / ni["nk"] / a
            fd.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(fd / "v4_full.npz", t_al_s=tr.t, t_ms=tr.fx["t_ms"].to_numpy(), z=tr.z, anchors=tr.A,
                                **{k: v for k, v in fu.items() if isinstance(v, np.ndarray) and v.ndim >= 1},
                                ll=np.float64(fu["ll"]), yaw0=np.float64(fu["yaw0"]), par=par)
            np.savez_compressed(fd / "v4_heldout.npz", hidden_a=hid[a]["a"], hidden_a2=hid[a]["a2"],
                                **{f"{m}_{s}_{k}": d[s][k] for m, d in (("V4", vn["pred"][a]), ("V4shift", vn["shift_pred"][a]))
                                   for s in ("a", "a2") for k in ("zhat", "var")},
                                **{f"yaw0_{m}_{s}": np.float64(d[s]["yaw0"]) for m, d in (("V4", vn["pred"][a]), ("V4shift", vn["shift_pred"][a]))
                                   for s in ("a", "a2")})
            if key == "test":
                r2 = vts[a]["r2tot"]
                vis = np.ones(tr.n, bool)
                b2p = ptuned["B2p"]
                Pb, Bb, Vb = P.kf_run(tr.t, tr.z, r2, [vis], [tr.st_mid, tr.st_mid_shift], [tr.st_at, tr.st_at_shift],
                                      [{"q": b2p["q"], "tb": b2p["tb"], "sb": b2p["sb"], "mrej": ptuned["B2"]["mrej"]}])
                p4 = np.where(np.isfinite(fu["p"]), fu["p"], Pb[0])
                still_sec = set(tr.ps["sec"].to_numpy()[tr.ps["still"].to_numpy(bool)].tolist())
                s0 = tr.lo / 1000.0
                for name, p in (("raw", tr.z), ("B2p_p", Pb[0]), ("V4_p", p4)):
                    plaus.append({"animal": a, "method": name, **P.track_metrics(tr.t, p, walls, still_sec, s0)})
                vv = np.hypot(*fu["v"].T)
                plaus[-1].update({"v_state_p50": float(np.nanpercentile(vv, 50)), "v_state_p95": float(np.nanpercentile(vv, 95)),
                                  "v_state_p99": float(np.nanpercentile(vv, 99))})
                if a == cfg.get("example_animal", ctx["scfg"].get("example_animal", "SF09")) and example is None:
                    example = {"t": tr.t, "raw": tr.z, "B2p": Pb[0] + Bb[0], "V4": np.where(np.isfinite(fu["zhat"]), fu["zhat"], Pb[0] + Bb[0]),
                               "still": tr.still, "st_at": tr.st_at, "animal": a}
    hyp = pd.concat([tsel["hyp"].assign(night=ni_t["nk"])] + vn_t["hyp"] + vn_e["hyp"], ignore_index=True)
    hand = pd.DataFrame([{"night": ni["nk"], "animal": a, **vn["hand"][a]} for ni, vn in ((ni_t, vn_t), (ni_e, vn_e)) for a in ni["animals"]])
    hand["llr_per_fix"] = hand["llr"] / hand["n_upd"]
    csv = out / "csv"
    err_e.to_csv(csv / "heldout_errors_test.csv.gz", index=False)
    err_t.to_csv(csv / "heldout_errors_tuning.csv.gz", index=False)
    comp_e.to_csv(csv / "bootstrap_comparisons_test.csv", index=False)
    comp_t.to_csv(csv / "bootstrap_comparisons_tuning.csv", index=False)
    pd.DataFrame(grids["stage1"]).to_csv(csv / "tuning_grid_stage1.csv", index=False)
    pd.DataFrame(grids["stage2"]).to_csv(csv / "tuning_grid_stage2.csv", index=False)
    hyp.to_csv(csv / "yaw_hypotheses.csv", index=False)
    hand.to_csv(csv / "handedness.csv", index=False)
    pd.DataFrame(nis_rows).to_csv(csv / "nis_consistency.csv", index=False)
    pd.DataFrame(plaus).to_csv(csv / "plausibility_test.csv", index=False)
    summ = {}
    for key, err in (("test", err_e), ("tuning", err_t)):
        summ[key] = {f"{m}|{s}": {w_: {"med": float(np.median(g.e)), "rmse": float(np.sqrt(np.mean(g.e ** 2))), "n": int(len(g))}
                                  for w_, g in list(d.groupby("animal")) + [("pooled", d)]}
                     for (m, s), d in err.groupby(["method", "scheme"])}
    res.update({"tuned": tuned, "grids": grids, "tune_yaw_deg": {a: math.degrees(y) for a, y in tsel["yaw"].items()},
                "verdict": ver, "info": {"tuning": info_t, "test": info_e}, "summ": summ, "comp_test": comp_e, "comp_tune": comp_t,
                "hand": hand, "nis": pd.DataFrame(nis_rows), "plaus": pd.DataFrame(plaus), "hyp": hyp, "example": example,
                "animals": ni_e["animals"], "par": par.tolist()})
    return res


def fill_nan(preds: dict, night: str, res: dict, log) -> None:
    """Hidden fixes V4 cannot predict (before the first IMU sample) get B2' predictions; counted and reported."""
    n = {}
    for a, d in preds.items():
        for s in ("a", "a2"):
            for m in ("V4", "V4_shift"):
                zh, ref = d[(m, s)], d[("B2p", s)]
                bad = np.isnan(zh[:, 0]) & ~np.isnan(ref[:, 0])
                n[f"{a}|{m}|{s}"] = int(bad.sum())
                d[(m, s)] = np.where(bad[:, None], ref, zh)
    res.setdefault("fill", {})[night] = n
    tot = sum(n.values())
    if tot:
        log(f"{night}: {tot} hidden fixes without V4 prediction filled with B2' (before the IMU start; unscored if IMU not QC-ok)")


def run(cohort: str, threads: int, workers: int, out_root: Path | None = None) -> Path:
    t_start = time.time()
    if HAVE_NUMBA:
        import numba
        set_num_threads(max(1, min(threads, numba.config.NUMBA_NUM_THREADS)))
    ctx = context(cohort)
    out = output_paths.run_dir(NAME, cohort, root=out_root)
    (out / "csv").mkdir(exist_ok=True)
    logf = open(out / "log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log(f"run dir {out}; numba {HAVE_NUMBA}; threads {threads}; workers {workers}")
    prov = {"config": ctx["cfg_path"].relative_to(REPO).as_posix(), "smoothing_config": ctx["cfg"]["smoothing_config"],
            "a1_index": ctx["a1_index"].to_dict(orient="records"),
            "wiser_fix_index": pd.read_csv(ctx["roots"]["wiser_fix"] / f"index_{cohort}.csv").to_dict(orient="records")}
    pbres = phase_b(ctx, workers, log, out)
    log(f"Phase B done ({time.time() - t_start:.0f} s)")
    pcres = phase_c(ctx, pbres, log, out)
    log(f"Phase C done ({time.time() - t_start:.0f} s)")
    cfg = ctx["cfg"]
    cfg["tuned"] = {"fitted_on": "tuning night 2026-09-08 21:00:00 -> 2026-09-09 04:20:00 (2026-09-08/09) only",
                    "fitted_by": "wiser/scripts/analyze_wiser_ins_fusion.py", "run_dir": str(out),
                    "written_local": pd.Timestamp.now(tz=ctx["tz"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "phase_b": json.loads(json.dumps({k: v for k, v in pbres["decisions"].items() if k != "cutoff"}, default=_jd)),
                    "cutoff": json.loads(json.dumps(pbres["decisions"]["cutoff"], default=_jd)),
                    "phase_c": json.loads(json.dumps(pcres["tuned"], default=_jd)),
                    "objective": "pooled median held-out error on scheme (a), hidden fixes with >= 7 anchors (smoothing pilot's scored set)"}
    ctx["cfg_path"].write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    res = {"cohort": cohort, "decisions": pbres["decisions"], "a3_paths": pbres["a3_paths"], "tuned": pcres["tuned"],
           "grids": pcres["grids"], "tune_yaw_deg": pcres["tune_yaw_deg"], "verdict": pcres["verdict"], "info": pcres["info"],
           "summ": pcres["summ"], "fill": pcres.get("fill", {}), "animals": pcres["animals"], "par": pcres["par"],
           "runtime_s": time.time() - t_start, "numba": HAVE_NUMBA, "git_commit": C.git_commit()}
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=_jd), encoding="utf-8")
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=_jd), encoding="utf-8")
    if pcres["example"] is not None:
        np.savez_compressed(out / "example_test.npz", **{k: v for k, v in pcres["example"].items() if isinstance(v, np.ndarray)},
                            animal=np.array(pcres["example"]["animal"]))
    log(f"runtime {time.time() - t_start:.0f} s; writing figures + report")
    finish(out, cohort)
    logf.close()
    return out


# ====================================================================================================== selftest
def synth_imu_wiser(seed: int, dur_s: float = 1200.0, yaw0_deg: float = 100.0, tau: float = 0.15, fs: float = 100.0) -> dict:
    """Synthetic head: still/moving bouts, smooth 2-D velocity (15 in/s SD), head yaw/pitch/roll moving independently of
    the travel direction; exact 100-Hz specific force and body rate + bias + noise (A3 units); WISER fixes (bimodal
    intervals, anchors 5-9, per-anchor noise, AR(1) drift, 0.4 % outliers) reporting the head position tau earlier."""
    from scipy.spatial.transform import Rotation as Rot
    rng = np.random.default_rng(seed)
    n = int(dur_s * fs)
    dt = 1.0 / fs
    t = np.arange(n) * dt
    still = np.zeros(n, bool)
    pos, first = 0.0, True
    while pos < dur_s:
        Ls = 30.0 if first else rng.uniform(40, 120)
        first = False
        still[(t >= pos) & (t < pos + Ls)] = True
        pos += Ls + rng.uniform(20, 60)
    env = np.clip(signal.filtfilt(*signal.butter(2, 0.5, fs=fs), (~still).astype(float)), 0, 1)
    env[still] = 0.0
    b, a = signal.butter(2, 1.0, fs=fs)
    v = np.column_stack([signal.filtfilt(b, a, rng.normal(0, 1, n)) for _ in range(2)])
    v = v / v.std() * 15.0 * env[:, None]
    acc_w = np.zeros((n, 2))
    acc_w[:-1] = (v[1:] - v[:-1]) / dt
    p = np.zeros((n, 2))
    p[0] = 300.0
    for k in range(n - 1):
        p[k + 1] = p[k] + v[k] * dt + 0.5 * acc_w[k] * dt * dt
    r = signal.filtfilt(*signal.butter(2, 0.5, fs=fs), rng.normal(0, 1, n))
    r = r / r.std() * 60.0 * env
    yaw = yaw0_deg + np.cumsum(r) * dt
    pitch = -20 + 10 * np.sin(2 * np.pi * 0.3 * t) * env
    roll = 8 * np.sin(2 * np.pi * 0.23 * t + 1) * env
    Rk = Rot.from_euler("ZYX", np.column_stack([yaw, pitch, roll]), degrees=True)
    om = np.zeros((n, 3))
    om[:-1] = (Rk[:-1].inv() * Rk[1:]).as_rotvec() / dt
    fw = np.column_stack([acc_w, np.full(n, G * IN_PER_M)])
    f_h = Rk.inv().apply(fw) / IN_PER_M
    acc = f_h + np.array([0.05, -0.03, 0.04]) + rng.normal(0, 0.03, (n, 3))
    gyr = np.degrees(om) + np.array([0.2, -0.3, 0.25]) + rng.normal(0, 0.1, (n, 3))
    dtf = rng.choice([0.134, 0.268], size=int(dur_s / 0.18) + 10, p=[0.45, 0.55]) + rng.normal(0, 0.003, int(dur_s / 0.18) + 10)
    T = np.cumsum(dtf) + 1.0
    T = T[T < dur_s - 1]
    tf = T - tau
    k = np.floor(tf * fs).astype(int)
    d = tf - k * dt
    ptrue = p[k] + v[k] * d[:, None] + 0.5 * acc_w[k] * d[:, None] ** 2
    m = len(tf)
    A = rng.choice([5, 6, 7, 8, 9], size=m, p=[0.02, 0.05, 0.08, 0.2, 0.65])
    sig = {5: (8.0, 6.0), 6: (5.0, 4.5), 7: (2.8, 4.0), 8: (2.0, 3.2), 9: (1.5, 2.6)}
    sw = np.array([sig[x] for x in A])
    drift = np.zeros((m, 2))
    for i in range(1, m):
        ph = math.exp(-(tf[i] - tf[i - 1]) / 30.0)
        drift[i] = ph * drift[i - 1] + rng.normal(0, math.sqrt(1 - ph * ph), 2)
    z = ptrue + drift + rng.normal(0, 1, (m, 2)) * sw
    out = rng.random(m) < 0.004
    z[out] += rng.normal(0, 40, (int(out.sum()), 2))
    secs = np.arange(int(dur_s))
    st_sec = np.array([still[int(s * fs):int((s + 1) * fs)].all() for s in secs])
    return {"t": t, "acc": acc, "gyr": gyr, "st_sec": np.where(st_sec, 1, 3).astype(np.int8), "tf": tf, "z": z, "A": A,
            "r2tot": sw ** 2 + 1.0, "ptrue": ptrue, "drift": drift, "yaw0": yaw0_deg}


def synth_a3(s: dict, shift_s: float = 0.0) -> dict:
    n = len(s["t"])
    k = int(round(shift_s * FS100))
    return {"t_unix_ms": s["t"] * 1000.0, "acc": np.roll(s["acc"], -k, axis=0), "gyr": np.roll(s["gyr"], -k, axis=0),
            "frozen": np.zeros(n, bool), "sat_acc": np.zeros(n, bool), "sat_gyr": np.zeros(n, bool)}


def synth_raw_poses(seed: int, n_pose: int = 60) -> dict:
    """1250-Hz raw counts (sensor frame) of static poses at random orientations joined by 1-s smooth rotations (eased:
    angular velocity continuous, as band-limited head motion), with an accelerometer ellipsoid (D, o), a gyro scale error
    (measured = true / s_true), bias, noise and 300 single-sample spikes."""
    from scipy.spatial.transform import Rotation as Rot
    rng = np.random.default_rng(seed)
    fs = FS_RAW
    keys = Rot.random(n_pose, random_state=seed)
    dwell = rng.uniform(2.0, 4.0, n_pose)
    rots = []
    for i in range(n_pose):
        rots.append(Rot.concatenate([keys[i]] * int(dwell[i] * fs)))
        if i + 1 < n_pose:
            phi = (keys[i].inv() * keys[i + 1]).as_rotvec()
            sfr = np.arange(int(fs)) / fs
            u = 3 * sfr ** 2 - 2 * sfr ** 3
            rots.append(keys[i] * Rot.from_rotvec(u[:, None] * phi[None, :]))
    Rk = Rot.concatenate(rots)
    n = len(Rk)
    om = np.zeros((n, 3))
    om[:-1] = (Rk[:-1].inv() * Rk[1:]).as_rotvec() * fs
    f = Rk.inv().apply(np.tile([0.0, 0.0, G], (n, 1)))          # head-frame specific force (m/s^2)
    D_true, o_true, s_true = np.array([1.03, 0.97, 1.01]), np.array([0.15, -0.20, 0.10]), 1.10
    a_meas = f / D_true + o_true + rng.normal(0, 0.02, f.shape)
    w_meas = np.degrees(om) / s_true + np.array([0.3, -0.2, 0.1]) + rng.normal(0, 0.05, om.shape)
    aB, wB = a_meas @ MI.S.T, w_meas @ MI.S.T
    six = np.column_stack([np.rint(aB / ACC_SCALE), np.rint(wB / GYR_SCALE)]).clip(-32768, 32767).astype(np.int16)
    spk = np.zeros(six.shape, bool)
    idx = rng.choice(np.arange(10, n - 10), 300, replace=False)
    lanes = rng.integers(0, 6, 300)
    six[idx, lanes] = np.clip(six[idx, lanes].astype(np.int32) + rng.choice([-1, 1], 300) * 2500, -32768, 32767).astype(np.int16)
    spk[idx, lanes] = True
    return {"six": six, "spikes": spk, "D": D_true, "o": o_true, "s": s_true}


def selftest() -> int:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    t0 = time.time()
    pb = json.loads((REPO / "wiser" / "configs" / "wiser_ins_fusion_2026c.json").read_text(encoding="utf-8"))["phase_b"]
    pc = json.loads((REPO / "wiser" / "configs" / "wiser_ins_fusion_2026c.json").read_text(encoding="utf-8"))["phase_c"]
    # ---- Phase B on synthetic raw poses
    sr = synth_raw_poses(4)
    x = sr["six"].astype(np.float32)
    hx, fl = np.empty_like(x), np.zeros(x.shape, bool)
    _hampel_lanes(x, np.zeros(x.shape, bool), int(pb["hampel_half_window"]), float(pb["hampel_nsigma"]),
                  hampel_floor(sr["six"], float(pb["hampel_mad_floor_counts"])), hx, fl)
    det = float((fl & sr["spikes"]).sum() / sr["spikes"].sum())
    fa = float((fl & ~sr["spikes"]).sum() / (~sr["spikes"]).sum())
    check("Hampel finds the injected single-sample spikes", det >= 0.95 and fa < 1e-4, f"detected {det:.3f}, false {fa:.2e}")
    scale = np.r_[np.full(3, ACC_SCALE), np.full(3, GYR_SCALE)]
    lp = []
    for l in range(6):
        sos = signal.butter(int(pb["butter_order"]), 20.0, fs=FS_RAW, output="sos")
        lp.append(signal.resample_poly(signal.sosfiltfilt(sos, hx[:, l].astype(np.float64) * scale[l]), 2, 25))
    n1 = min(len(v) for v in lp)
    Bm = np.column_stack([v[:n1] for v in lp])
    a100, w100 = Bm[:, :3] @ MI.S, Bm[:, 3:] @ MI.S
    bad = np.zeros(n1, bool)
    ws = window_stats(a100, w100, bad, int(pb["quasi_static_win_s"] * FS100))
    qsw = (ws["wmed"] < pb["quasi_static_omega_dps"]) & (ws["asd"].max(axis=1) < pb["quasi_static_acc_sd"])
    ell = fit_ellipsoid(ws["abar"][qsw], pb)
    e_o = float(np.max(np.abs(np.array(ell["o"]) - sr["o"])))
    e_d = float(np.max(np.abs(np.array(ell["D"]) - sr["D"])))
    check("ellipsoid recovers offsets (< 0.03 m/s^2) and scales (< 0.5 %)", e_o < 0.03 and e_d < 0.005,
          f"max |o err| {e_o:.4f}, max |D err| {e_d:.4f}")
    cv = acc_cal_cv(ws["abar"][qsw], ws["i0"][qsw] / FS100 * 60.0, {**pb, "cv_block_s": 60.0})
    check("held-out gravity residual: ellipsoid < scalar", cv["ellipsoid"] < cv["scalar"], f"{cv['ellipsoid']:.4f} vs {cv['scalar']:.4f}")
    qs = quiet_seconds(a100, w100, bad)
    b_run = bias_running(qs["t_c"][qs["quiet"]], qs["wmed3"][qs["quiet"]], np.arange(n1) / FS100, 300.0, 5)
    w_c = w100 - b_run
    a_c = apply_acc(a100, {"method": "ellipsoid", **ell})
    pairs = sds_pairs(a_c, w_c, bad, pb)
    g0, g1, gs = pb["gyro_scale_grid"]
    grid = np.round(np.arange(g0, g1 + 1e-9, gs), 6)
    err = sds_scale(w_c * D2R, pairs, grid)
    s_hat = float(grid[int(np.argmin((err ** 2).sum(axis=0)))]) if len(err) else np.nan
    check("static-dynamic-static recovers the gyro scale (1.10 +- 0.01)", abs(s_hat - sr["s"]) <= 0.01,
          f"s* {s_hat:.3f} from {len(err)} pairs")
    kin = kinematic(a_c, w_c, bad, pb)
    check("kinematic du/dt = u x w: r > 0.9 and slope ~ s_true on the uncorrected gyro", kin["r"] > 0.9 and abs(kin["slope"] - sr["s"]) < 0.05,
          f"r {kin['r']:.3f}, slope {kin['slope']:.3f}")
    # ---- cutoff rule on synthetic PSDs
    f = np.arange(0, 625.5, 0.5)
    ps_still = np.full(len(f), 1e-4)
    ps_mov = 1e-4 + np.where(f < 25, 1.0 / (1 + f), 0.0)
    cr = cutoff_rule(f, ps_still, ps_mov, pb)
    check("cutoff rule finds where motion power meets the noise floor", 24.0 <= cr["fc_hz"] <= 27.0, f"f_c {cr['fc_hz']:.1f} Hz")
    # ---- Phase C on a synthetic head
    s = synth_imu_wiser(3)
    noise = {"sigma_omega_dps": 0.5, "sigma_f_ms2": 0.05, "sigma_g_still": 0.001}
    par = make_par({"sa": 0.1, "sg": 0.003, "sv": 0.5, "tb": 30.0, "sb": 1.0}, pc, noise)
    T_ms = s["t"][-1] * 1000.0
    imu = ImuIn(synth_a3(s), 0.0, T_ms, 0.0, s["st_sec"], 0)
    imu_sh = ImuIn(synth_a3(s, 400.0), 0.0, T_ms, 0.0, np.roll(s["st_sec"], -400), 0)
    hid = P.hide_runs(len(s["tf"]), np.random.default_rng(5))
    sc = hid & (s["A"] >= 7)
    sel = select_yaw(imu, s["tf"], s["z"], s["r2tot"], ~hid, par, 24, mirror=True)
    dyaw = abs((math.degrees(sel["yaw0"]) - s["yaw0"] + 180) % 360 - 180)
    check("ML initial-yaw hypothesis recovers the true yaw (<= 15 deg)", dyaw <= 15.0, f"{math.degrees(sel['yaw0']):.0f} vs {s['yaw0']:.0f}")
    check("mirrored WISER frame scores worse (LLR > 0)", sel["llr"] > 0, f"LLR {sel['llr']:+.1f}")
    r4 = run_batch(imu, s["tf"], [s["z"]], s["r2tot"], [~hid], par[None, :], [sel["yaw0"]], [0], [0], True, 2, True)
    sel_s = select_yaw(imu_sh, s["tf"], s["z"], s["r2tot"], ~hid, par, 24)
    r4s = run_batch(imu_sh, s["tf"], [s["z"]], s["r2tot"], [~hid], par[None, :], [sel_s["yaw0"]], [0], [0], True, 2, True)
    zero = np.zeros(len(s["tf"]), np.int8)
    cf = [{"q": q, "mrej": 1e9} for q in (1, 3, 10, 30, 100)]
    Pq, Bq, _ = P.kf_run(s["tf"], s["z"], s["r2tot"], [~hid], [zero], [zero], cf)
    e_b2 = {q["q"]: np.hypot(*(s["z"][sc] - (Pq[i] + Bq[i])[sc]).T) for i, q in enumerate(cf)}
    qb = min(e_b2, key=lambda q: np.median(e_b2[q]))
    e4 = np.hypot(*(s["z"][sc] - r4["zhat"][0][sc]).T)
    e4s = np.hypot(*(s["z"][sc] - r4s["zhat"][0][sc]).T)
    blocks = np.floor(s["tf"][sc] / P.BLOCK_S).astype(int)
    st0 = np.zeros(int(sc.sum()), int)
    rb = P.boot_delta(e4, e_b2[qb], blocks, st0, np.random.default_rng(1))
    check("V4 beats the best B2 on held-out fixes (CI > 0)", rb["lo"] > 0, f"D {rb['d_med']:+.3f} [{rb['lo']:+.3f}, {rb['hi']:+.3f}] "
          f"(V4 {np.median(e4):.2f} vs B2 q={qb} {np.median(e_b2[qb]):.2f} in)")
    rbs = P.boot_delta(e4s, e_b2[qb], blocks, st0, np.random.default_rng(2))
    check("+1 h-style shifted IMU gives no gain (CI lower bound <= 0)", rbs["lo"] <= 0, f"D {rbs['d_med']:+.3f} [{rbs['lo']:+.3f}, {rbs['hi']:+.3f}]")
    eo = np.hypot(*(s["z"][sc] - (s["ptrue"] + s["drift"])[sc]).T)
    check("V4 stays above the oracle floor", np.median(e4) > np.median(eo), f"{np.median(e4):.2f} vs oracle {np.median(eo):.2f}")
    ba_hat = r4["ba"][0][np.isfinite(r4["ba"][0][:, 0])][-1] / IN_PER_M
    bg_hat = np.degrees(r4["bg"][0][np.isfinite(r4["bg"][0][:, 0])][-1])
    check("accelerometer and gyro biases recovered", np.all(np.abs(ba_hat - [0.05, -0.03, 0.04]) < 0.02) and
          np.all(np.abs(bg_hat - [0.2, -0.3, 0.25]) < 0.05), f"ba {np.round(ba_hat, 3)}, bg {np.round(bg_hat, 3)}")
    print(f"numba: {HAVE_NUMBA}; selftest {time.time() - t0:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== figures + report
def _pct(x, nd: int = 1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{100 * x:+.{nd}f} %"


def _f(x, nd: int = 2) -> str:
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def _ci(r) -> str:
    return f"{_pct(r['d_med'])} [{_pct(r['lo'])}, {_pct(r['hi'])}]"


def _crow(comp: pd.DataFrame, s: str, sub: str, m: str, ref: str, who: str):
    c = comp[(comp.scheme == s) & (comp.subset == sub) & (comp.method == m) & (comp.ref == ref) & (comp.animal == who)]
    return c.iloc[0] if len(c) else None


def make_figures(out: Path, res: dict, q: pd.DataFrame, comp: pd.DataFrame, hyp: pd.DataFrame, fdir: Path, cohort: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = {}
    dec = res["decisions"]
    # ---- F1 PSD + cutoffs
    z = np.load(out / "phase_b" / "psd_pooled_tuning.npz")
    f = z["f"]
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, grp, sl, unit in ((axs[0], "acc", slice(0, 3), "(m/s²)²/Hz"), (axs[1], "gyr", slice(3, 6), "(°/s)²/Hz")):
        m = f > 0
        ax.loglog(f[m], z["moving"][m, sl].sum(axis=1), color="#c0392b", lw=1.2, label="moving seconds (after Hampel)")
        ax.loglog(f[m], z["still"][m, sl].sum(axis=1), color="#2c7fb8", lw=1.2, label="IMU-still seconds (after Hampel)")
        ax.loglog(f[m], z["still_raw"][m, sl].sum(axis=1), color="#2c7fb8", lw=0.8, ls=":", label="IMU-still, raw")
        N = dec["cutoff"][grp]["noise_floor"]
        ax.axhline(N, color="k", lw=0.8, ls="--", label="noise floor N (150–500 Hz)")
        ax.axhline(2 * N, color="k", lw=0.6, ls=":", label="2 N")
        ax.axvline(dec["fc"][grp], color="#27ae60", lw=1.5, label=f"applied f_c = {dec['fc'][grp]:.0f} Hz")
        ax.axvline(100.0, color="grey", lw=0.8, ls="-.", label="search limit 100 Hz")
        ax.set_xlabel("frequency (Hz)")
        ax.set_ylabel(f"PSD, sum of 3 axes {unit}")
        ax.set_title(f"{'accelerometer' if grp == 'acc' else 'gyroscope'} — tuning night, 5 animals pooled")
        ax.legend(fontsize=7)
    fig.tight_layout()
    p = fdir / f"{STEM}_imu_psd_{cohort}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    figs["psd"] = p.name
    # ---- F2 IMU quality before/after
    fig, axs = plt.subplots(2, 2, figsize=(11, 7))
    lab = [f"{r.animal}\n{'tune' if r.role == 'tuning' else 'test'}" for r in q.itertuples()]
    xx = np.arange(len(q))
    w_ = 0.38
    axs[0, 0].bar(xx - w_ / 2, q.grav_cv_scalar, w_, label="scalar k_a (make_imu rule)", color="#95a5a6")
    axs[0, 0].bar(xx + w_ / 2, q.grav_cv_ellipsoid, w_, label="diagonal ellipsoid", color="#27ae60")
    axs[0, 0].set_ylabel("held-out median | |a| − g | (m/s²)")
    axs[0, 0].set_title("quiet-window gravity residual (2-fold CV)")
    axs[0, 1].bar(xx - w_ / 2, q.drift_before_med * 60, w_, label="before (make_imu chain, block bias)", color="#95a5a6")
    axs[0, 1].bar(xx + w_ / 2, q.drift_after_med * 60, w_, label="after (chosen chain)", color="#27ae60")
    axs[0, 1].set_ylabel("median |yaw drift| (°/min)")
    axs[0, 1].set_title("still-run yaw drift, leave-one-run-out bias")
    axs[1, 0].bar(xx - w_ / 2, q.fus_before_pitch_sd_still_med, w_, label="before", color="#95a5a6")
    axs[1, 0].bar(xx + w_ / 2, q.fus_after_pitch_sd_still_med, w_, label="after", color="#27ae60")
    axs[1, 0].set_ylabel("median pitch SD in still runs (°)")
    axs[1, 0].set_title("Fusion AHRS stability")
    axs[1, 1].bar(xx, q.sds_s_star, 0.6, color="#8e44ad", label="per animal-night s*")
    axs[1, 1].axhline(dec["gyro_scale_star"], color="k", lw=1, label=f"pooled tuning s* {dec['gyro_scale_star']:.3f}")
    lo_, hi_ = dec["gyro_scale_ci"]
    axs[1, 1].axhspan(lo_, hi_, color="k", alpha=0.12, label="95 % CI")
    axs[1, 1].axhline(1.0, color="grey", ls=":")
    axs[1, 1].set_ylim(0.85, 1.15)
    axs[1, 1].set_ylabel("gyro scale s* (static–dynamic–static)")
    axs[1, 1].set_title("gyro scale")
    for ax in axs.ravel():
        ax.set_xticks(xx)
        ax.set_xticklabels(lab, fontsize=7)
        ax.legend(fontsize=7)
    fig.tight_layout()
    p = fdir / f"{STEM}_imu_quality_{cohort}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    figs["quality"] = p.name
    # ---- F3 held-out deltas
    animals = res["animals"]
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, s, tl in ((axs[0], "a", "(a) runs of 4–8 hidden fixes"), (axs[1], "a2", "(a′) hidden 2-s windows")):
        whos = animals + ["pooled"]
        for k, (m, col) in enumerate((("V4", "#c0392b"), ("V4_shift", "#7f8c8d"), ("V2", "#2980b9"), ("B1", "#d35400"))):
            ys, lo, hi = [], [], []
            for wv in whos:
                r = _crow(comp, s, "all", m, "B2p", wv)
                ys.append(np.nan if r is None else 100 * r.d_med)
                lo.append(np.nan if r is None else 100 * r.lo)
                hi.append(np.nan if r is None else 100 * r.hi)
            xs = np.arange(len(whos)) + (k - 1.5) * 0.18
            ys, lo, hi = np.array(ys), np.array(lo), np.array(hi)
            ax.errorbar(xs, ys, yerr=[ys - lo, hi - ys], fmt="o", color=col, ms=4, capsize=2, label=LABEL.get(m, m))
        ax.axhline(0, color="k", lw=0.8)
        ax.axhline(100 * res.get("accept", {}).get("min_gain", 0.03), color="#27ae60", ls="--", lw=0.8, label="+3 % acceptance")
        ax.set_xticks(np.arange(len(whos)))
        ax.set_xticklabels(whos)
        ax.set_title(f"test night — {tl}")
        ax.set_ylabel("Δ median held-out error vs B2′ (%)")
        ax.legend(fontsize=7)
    fig.tight_layout()
    p = fdir / f"{STEM}_heldout_{cohort}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    figs["heldout"] = p.name
    # ---- F4 heading hypotheses
    fig, axs = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, night in zip(axs, sorted(hyp.night.unique())):
        h = hyp[(hyp.night == night) & (hyp.run == "full")]
        for a in animals:
            ha = h[h.animal == a]
            if not len(ha):
                continue
            mx = ha[ha.frame == "normal"].ll.max()
            n = ha.n.max()
            for fr, ls in (("normal", "-"), ("mirrored", "--")):
                hf = ha[ha.frame == fr].sort_values("yaw0_deg")
                ax.plot(hf.yaw0_deg, (hf.ll - mx) / n, ls=ls, lw=1, label=f"{a} {fr}" if fr == "normal" else None)
        ax.set_xlabel("initial yaw hypothesis (°)")
        ax.set_title(f"{night}: full-data pseudo-log-likelihood (solid normal, dashed y-mirrored)")
        ax.set_ylabel("(ℓ − max ℓ_normal) / fixes")
        ax.legend(fontsize=7)
    fig.tight_layout()
    p = fdir / f"{STEM}_heading_{cohort}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    figs["heading"] = p.name
    # ---- F5 example stretch (fixed rule)
    pe = out / "example_test.npz"
    if pe.exists():
        e = np.load(pe)
        t, still, st = e["t"], e["still"], e["st_at"]
        t0 = None
        for c in np.arange(0, t[-1] - 240, 60.0):
            m = (t >= c) & (t < c + 240)
            if m.sum() and still[m].mean() * 240 >= 60 and (st[m] == 3).mean() * 240 >= 20:
                t0 = c
                break
        if t0 is not None:
            m = (t >= t0) & (t < t0 + 240)
            fig, axs = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
            for k, ax in enumerate(axs):
                tt = t[m] - t0
                ax.plot(tt, e["raw"][m, k], ".", ms=2, color="#bdc3c7", label="WISER fixes")
                ax.plot(tt, e["B2p"][m, k], color="#2980b9", lw=1, label="B2′ (p + b)")
                ax.plot(tt, e["V4"][m, k], color="#c0392b", lw=1, label="V4 (p + b_w)")
                sm = still[m]
                for a_, b_ in C.true_runs(sm):
                    ax.axvspan(tt[a_], tt[min(b_, len(tt) - 1)], color="#27ae60", alpha=0.1, lw=0)
                ax.set_ylabel(f"{'x' if k == 0 else 'y'} (in, WISER frame)")
            axs[0].legend(fontsize=7)
            axs[1].set_xlabel(f"s from {t0:.0f} s after 21:00 (green = IMU-still)")
            axs[0].set_title(f"test night, {str(e['animal'])}: full-data tracks (fixed rule: first 4-min stretch with ≥ 60 s still and ≥ 20 s locomoting)")
            fig.tight_layout()
            p = fdir / f"{STEM}_example_{cohort}.png"
            fig.savefig(p, dpi=130)
            plt.close(fig)
            figs["example"] = p.name
            figs["example_t0"] = float(t0)
    return figs


DEFINITIONS = r"""
## Definitions

Units: WISER positions in **inches** in the WISER native frame (unverified offset origin, no georeference); IMU
acceleration m/s² (filter: in/s², 1 m = 39.37 in), angular rate °/s (filter: rad/s). Times: field-PC clock (WISER
`timestamp`; IMU Unix ms from `pc_time_fit.json`). Head frame H: x nose, y left, z up (`make_imu.S`); world frame N:
x, y = the WISER axes, z up (right-handed if WISER is; tested by the mirrored run). $g$ = 9.81 m/s². Symbols: $k$ = IMU
sample (100 Hz after Phase B), $j$ = WISER fix, $A_j$ = `anchors_used`, $\mathbf z_j$ = fix (in), $s$ = second.
Definitions reused unchanged from the smoothing pilot (duplicate rule, aligned time $t^{al}=t-\tau^*$, IMU-still second,
QC mask, locomotion class, per-anchor noise $\sigma_{ax}(A)$, B1/B2/B2′/V1/V2, held-out schemes (a)/(a′), scored set,
$\Delta$, block bootstrap, acceptance logic) are restated briefly here; the full text is in the pilot report.

### Phase B — IMU quality and smoothing

**Hampel spike filter** (per lane, 1250 Hz, raw counts $x$): with $m_i=\mathrm{med}(x_{i-3..i+3})$,
$\mathrm{MAD}_i=\mathrm{med}|x_{i-3..i+3}-m_i|$, $\sigma_\ell=\max(2,\ 1.4826\,\mathrm{med}_i|x_{i+1}-x_i|/\sqrt2)$,
$$ x_i\leftarrow m_i\quad\text{if}\quad |x_i-m_i|>6\,\max(1.4826\,\mathrm{MAD}_i,\ \sigma_\ell),\ \text{sample not saturated.} $$
**Text:** replaces isolated samples that jump more than 6 local robust SDs (floored at the lane's global noise SD, so
pure noise is not flagged); counts reported per hour of still / moving time.

**PSD and noise floor.** One-sided Welch-type PSD $P(f)=\frac{2}{f_s\sum w^2}\langle|\mathrm{FFT}(w\cdot x)|^2\rangle$ over
2-s Hann segments ($f_s$ = 1250 Hz, 0.5-Hz bins) lying entirely in IMU-still (resp. QC-ok moving) seconds, ≤ 4000
segments per class; summed over the 3 axes of a sensor. Noise floor $N=\mathrm{med}_{150\le f\le500\,\mathrm{Hz}}P_{still}(f)$.
**Text:** the sensor's high-band white level ((m/s²)²/Hz or (°/s)²/Hz).

**Low-pass cutoff** $f_c=\mathrm{clip}\big(\min\{f\ge5:\ \tilde P_{mov}(f')\le2N\ \forall f'\in[f,100]\},\ 5,\ 40\big)$ Hz,
$\tilde P$ = 2-Hz moving average. **Text:** where head-motion power meets the noise floor (tuning night, animals pooled);
40 Hz keeps the 100-Hz output alias-free. Filter: 4th-order Butterworth, zero phase, then `resample_poly(2, 25)`.

**Saturation flag at 100 Hz:** sample $k$ is `sat_acc` (`sat_gyr`) if any raw frame in $[12.5k-6,\,12.5k+6]$ of an acc
(gyro) lane has $|x|\ge32700$, dilated by $\lceil 2/f_c\cdot100\rceil$ samples (the filter's support). Never interpolated.

**Quasi-static window** (0.5 s at 100 Hz): median $|\boldsymbol\omega|<10$ °/s and every per-axis acc SD < 0.15 m/s²,
no flagged sample; $\bar{\mathbf a}_w$ = its mean acceleration.

**Accelerometer calibration.** Scalar: $k_a=g/\mathrm{med}_w|\bar{\mathbf a}_w|$. Ellipsoid: $\mathbf a_{cal}=D(\mathbf a-\mathbf o)$,
$D=\mathrm{diag}(d_1,d_2,d_3)$,
$$ (\hat D,\hat{\mathbf o})=\arg\min\ \sum_w\rho_H\!\Big(\tfrac{|D(\bar{\mathbf a}_w-\mathbf o)|-g}{0.1}\Big)+\sum_i\Big(\tfrac{d_i-1}{0.05}\Big)^2+\sum_i\Big(\tfrac{o_i}{0.5}\Big)^2 $$
($\rho_H$ = Huber loss, scale 1). **Held-out gravity residual** $=\mathrm{med}_{w\in\text{test fold}}\big||\mathbf a_{cal}(\bar{\mathbf a}_w)|-g\big|$
(m/s²), 2 folds = alternating 10-min blocks. **Orientation coverage** = eigenvalues of $\mathrm{Cov}(\bar{\mathbf a}_w/|\bar{\mathbf a}_w|)$.
**Text:** how far the calibrated |a| of a head at rest is from g on windows not used to fit (0 = perfect); the ellipsoid
adds per-axis offsets/scales; the priors keep poorly excited axes near identity.

**Gyro bias.** Quiet 1-s windows (make_imu: median $|\boldsymbol\omega|<10$ °/s and $|k_a\,\mathrm{med}|\mathbf a|-g|<0.05g$) give
per-window medians $\mathbf b_s$. *Block* (make_imu): median of $\mathbf b_s$ per 10-min block (≥ 30 windows) at block centres,
linear interpolation. *Running*: median of $\mathbf b_s$ within ±300 s (≥ 20 windows, else ±900 s, else all), linear
interpolation. **Leave-one-run-out yaw drift** of a still run $R$ (≥ 60 s):
$$ \dot\psi_R=\frac{1}{T_R}\Big|\sum_{k\in R}(\boldsymbol\omega_k-\hat{\mathbf b}_{-R})\cdot\hat{\mathbf u}_R\,\Delta t\Big| $$
$\hat{\mathbf b}_{-R}$ = bias at the run midpoint estimated without the run's windows (running: median within ±300 s of the
midpoint), $\hat{\mathbf u}_R$ = the run's mean gravity direction. **Text:** apparent yaw rotation (°/s, reported °/min)
of a head that does not move — the residual bias error an honest (held-out) bias estimate leaves.

**Gyro scale (static–dynamic–static).** Pairs of consecutive quasi-static intervals (≥ 0.5 s, centred 0.5-s windows),
0.2–3 s apart, tilt change ≥ 20°; $\mathbf u_1,\mathbf u_2$ = mean gravity directions of the last / first 0.5 s;
$$ e_p(s)=\angle\big(R_{12}(s)^\top\mathbf u_1,\ \mathbf u_2\big),\quad R_{12}(s)=\prod_k\mathrm{Exp}(s\,\boldsymbol\omega_k\Delta t),\qquad s^*=\arg\min_{s\in[0.8,1.4]}\sum_p e_p(s)^2 $$
95 % CI: 1000 bootstrap resamples of pairs. **Rule:** apply $s^*$ if the CI excludes 1 and $|s^*-1|>2\,\%$.
**Text:** the gyro gain that best predicts how gravity turned between two rests; immune to linear acceleration (endpoints
static), blind to rotation about the vertical.

**Kinematic consistency.** With 5-Hz low-passed signals, $\mathbf u=\mathbf a/|\mathbf a|$:
$\dot{\mathbf u}=\mathbf u\times\boldsymbol\omega$ for a pure rotation. Slope $b=\sum\mathbf x\cdot\mathbf y/\sum|\mathbf x|^2$ and
Pearson $r$ of $\mathbf y=\dot{\mathbf u}$ on $\mathbf x=\mathbf u\times\boldsymbol\omega$ (components stacked), samples with
20 ≤ |ω| ≤ 300 °/s, $||\mathbf a|-g|<0.1g$, ≥ 0.2 s from a flagged sample, night window. **Acc–gyro latency** = the lag
$\ell$ (10-ms steps, parabolic peak) maximising $r$ of $\dot{\mathbf u}(t)$ vs $\mathbf u(t)\times\boldsymbol\omega(t+\ell)$ (+ = gyro
lags). **Text:** $r$ near 1 and $b$ near 1 when acc and gyro agree; linear acceleration of the head inflates $b$, so it is
a secondary check only.

**Still-period noise:** $\sigma_\omega$ ($\sigma_f$) = RMS of the 100-Hz gyro (acc) about its per-second mean inside
IMU-still seconds (tuning night, median over animals; floors 0.5 °/s, 0.05 m/s²). **Gyro still noise density**
$\sigma_{g,still}=\sqrt{N_{gyr}/(3\cdot2)}$ (rad/s/√Hz), $N_{gyr}$ = the gyro noise floor.

**Angular acceleration:** $|\dot{\boldsymbol\omega}|$ by central differences at 100 Hz on QC-ok moving, unflagged samples;
percentiles (°/s²). **Fusion stability** (make_imu `fuse`, unchanged): median over still runs ≥ 60 s of the pitch SD
(°); share of samples in Fusion recovery; median angle between Fusion's gravity and the quasi-static acc direction.

### Phase C — V4 error-state Kalman filter + RTS smoother

**Nominal state** $\mathbf p\in\mathbb R^2$ (in), $\mathbf v\in\mathbb R^2$ (in/s), $q$ (head→world), $\mathbf b_a$ (in/s², head),
$\mathbf b_g$ (rad/s, head), $\mathbf b_w\in\mathbb R^2$ (in, WISER drift). **Propagation** per IMU sample ($\Delta t$ ≈ 0.01 s):
$$ \mathbf f=R(q)(\mathbf a_k-\mathbf b_a),\quad \mathbf p\leftarrow\mathbf p+\mathbf v\Delta t+\tfrac12\mathbf f_{xy}\Delta t^2,\quad \mathbf v\leftarrow\mathbf v+\mathbf f_{xy}\Delta t,\quad q\leftarrow q\otimes\mathrm{Exp}((\boldsymbol\omega_k-\mathbf b_g)\Delta t),\quad \mathbf b_w\leftarrow e^{-\Delta t/T_b}\mathbf b_w $$
(the vertical channel is discarded: z fixed; lever arm IMU↔tag ignored). **Error state** $\delta\mathbf x=(\delta\mathbf p,\delta\mathbf v,\delta\boldsymbol\theta,\delta\mathbf b_a,\delta\mathbf b_g,\delta\mathbf b_w)$
(15), global attitude error $R_{true}=\mathrm{Exp}(\delta\boldsymbol\theta)R$:
$\dot{\delta\mathbf v}=-([\mathbf f]_\times\delta\boldsymbol\theta)_{xy}-(R\,\delta\mathbf b_a)_{xy}$, $\dot{\delta\boldsymbol\theta}=-R\,\delta\mathbf b_g$;
$\Phi=I+F\Delta+F^2\Delta^2/2+F^3\Delta^3/6$ (Δ = 0.02 s and every epoch). Process noise: velocity $\sigma_a^2\Delta$
(position/velocity blocks $\sigma_a^2[\Delta^3/3,\Delta^2/2;\Delta^2/2,\Delta]$), attitude $\sigma_g^2\Delta$ ($\sigma_{g,still}^2\Delta$ in IMU-still
samples), $\sigma_{ba}^2\Delta$, $\sigma_{bg}^2\Delta$, drift $\sigma_b^2(1-e^{-2\Delta/T_b})$; saturated samples $\sigma_{a,sat}$ = 20 m/s²/√Hz,
$\sigma_{g,sat}$ = 1 rad/s/√Hz.

**Updates** (Kalman, error injected and reset after each): (i) **WISER** fix at $t^{al}_j$: $\mathbf z_j=\mathbf p+\mathbf b_w+\boldsymbol\varepsilon$,
$R_j=\mathrm{diag}(\sigma^2_{w,x},\sigma^2_{w,y})$, $\sigma^2_{w}=\max(\sigma^2_{ax}(A_j)-\sigma_b^2,\ \sigma^2_{ax}(A_j)/4)\times k_R^{[\text{fix not IMU-still}]}$;
pass 0: soft gate $R\leftarrow R\,d^2/13.8$ if $d^2=\boldsymbol\nu^\top S^{-1}\boldsymbol\nu>13.8$; passes 1–2: $R/w_j$ with Huber
$w_j=\min(1,2.5/m_j)$, $m_j^2=\sum_{ax}(z_{j,ax}-\hat z^s_{j,ax})^2/\sigma^2_{w,ax}$ from the smoothed track. (ii) At 10 Hz in IMU-still
samples: **ZUPT** $0=\mathbf v+\epsilon$ ($\sigma_v$), **ZARU** $\boldsymbol\omega_k=\mathbf b_g+\epsilon$ ($\sigma_\omega$), **gravity**
$\mathbf a_k=R^\top g\hat{\mathbf z}+\mathbf b_a+\epsilon$ ($\sigma_f$; $H_\theta=R^\top[g\hat{\mathbf z}]_\times$) when $||\mathbf a_k|-g|<0.1g$.
(iii) **Dynamic gravity** (amendment): at 10 Hz outside still samples when $||\mathbf a_k|-g|<0.1g$ and $|\boldsymbol\omega_k|<100$ °/s,
the same update with $\sigma_{fd}$ and a soft χ²₃ gate (16.27). (iv) **Tilt-reset guard** (amendment): with
$\bar{\mathbf a}$ = 1-s exponential mean of $\mathbf a_k$, if $||\bar{\mathbf a}|-g|<0.05g$ and $\angle(R^\top\hat{\mathbf z},\bar{\mathbf a})>30°$, the
tilt is re-initialised from $\bar{\mathbf a}$ (yaw kept), attitude covariance reset (tilt 3°, yaw 30°); counted.

**RTS smoother** (error-state form over every epoch $e$): $C_e=P^+_e\Phi_{e+1}^\top(P^-_{e+1})^{-1}$,
$\delta\mathbf x^s_e=C_e(\delta\mathbf x^s_{e+1}+\delta\mathbf x^{upd}_{e+1})$, $\mathbf x^s_e=\hat{\mathbf x}^+_e\oplus\delta\mathbf x^s_e$,
$P^s_e=P^+_e+C_e(P^s_{e+1}-P^-_{e+1})C_e^\top$. Held-out prediction $\hat{\mathbf z}_j=\mathbf p^s_j+\mathbf b^s_{w,j}$, predictive
variance per axis $P^s_{pp}+P^s_{ww}+2P^s_{pw}$.

**Initial-yaw hypotheses and pseudo-log-likelihood.** 24 initial yaws $\psi_0\in\{0°,15°,…,345°\}$ ($\sigma_{\psi_0}$ = 10°),
tilt from the first 2 s of acc; for each, the forward filter's
$$ \ell(\psi_0)=-\tfrac12\sum_{j\ \text{visible}}\big(d^2_j+\ln\det S_j+2\ln2\pi\big) $$
(pass 0, $S_j$ after the soft gate). V4 uses $\arg\max\ell$. **Handedness LLR** $=\max_{\psi_0}\ell_{normal}-\max_{\psi_0}\ell_{mirrored}$,
mirrored = WISER $y\to-y$. **Text:** > 0 means the IMU's right-handed rotations explain the WISER track better in the
WISER frame as given than in its mirror image; in nats over the night (also per fix). It does not choose the frame.

**NIS** $d^2_j$ (pass 0, before the gate) — χ²₂ if the filter is consistent: mean 2, 5 % above 5.99. **Held-out $z^2$**
$=\sum_{ax}(z_{j,ax}-\hat z_{j,ax})^2/(\mathrm{var}^s_{j,ax}+\sigma^2_{w,ax})$ on scored hidden fixes — also χ²₂ if calibrated.

**+1 h control.** V4 rerun with every IMU input (acc, gyro, flags, still classes, the $k_R$ flag) taken from $t+3600$ s
(A3 covers it); its own yaw selection. **Text:** keeps the IMU's statistics, breaks its link to the head.

**Held-out schemes, scored set, Δ, bootstrap, acceptance** (smoothing pilot, unchanged): (a) runs of 4–8 hidden fixes
separated by 1–47 visible (≈ 20 % hidden), (a′) every fix in a random 10 % of 2-s windows; seeds = the pilot's. Scored =
hidden, $A\ge7$, IMU and +1 h IMU QC-ok. $e_j=\|\mathbf z_j-\hat{\mathbf z}_j\|$;
$\Delta_M=1-\mathrm{med}(e_M)/\mathrm{med}(e_{B2'})$ (+ = better than B2′), 95 % CI from 1000 paired bootstrap draws of 5-min
blocks (stratified by animal when pooled). **Acceptance:** on (a) or (a′), (i) $\Delta\ge3\,\%$ with CI lower bound > 0 in
≥ 4/5 animals, (ii) the +1 h control's CI lower bound ≤ 0 in ≥ 4/5, (iii) pooled Δ on moving fixes ≥ −2 %; ACCEPTED =
(i)∧(ii)∧(iii); INCONCLUSIVE = (i) in exactly 3 animals, or (i)∧¬(ii); else FAIL.

**Track plausibility** (pilot's `track_metrics`, full data): speed $v(t)=|\hat{\mathbf p}(t+0.5)-\hat{\mathbf p}(t-0.5)|$/1 s and
acceleration on a 0.25-s grid, path length per hour on the 1-s grid; V4 also reports its velocity state $|\mathbf v^s|$.
"""


def render_report(out: Path, res: dict, cfg: dict, scfg: dict, q: pd.DataFrame, sat: pd.DataFrame, spk: pd.DataFrame,
                  comp: pd.DataFrame, comp_t: pd.DataFrame, hand: pd.DataFrame, nis: pd.DataFrame, plaus: pd.DataFrame,
                  g1: pd.DataFrame, g2: pd.DataFrame, figs: dict, cohort: str, sizes: dict, pilot_summ: dict | None,
                  hyp: pd.DataFrame | None = None, err: pd.DataFrame | None = None, hnull: pd.DataFrame | None = None) -> str:
    dec = res["decisions"]
    tuned = res["tuned"]
    ver = res["verdict"]
    animals = res["animals"]
    tags = {a: C.resolve_tag(pd.read_csv(REPO / "wiser" / "configs" / "rat_identities_2026c.csv").assign(
        from_ms=lambda d: pd.to_datetime(d.valid_from, utc=True).astype("int64") // 10**6,
        until_ms=lambda d: pd.to_datetime(d.valid_until, utc=True).astype("int64") // 10**6), a,
        C.to_ms(scfg["nights"]["test"]["start"]), C.to_ms(scfg["nights"]["test"]["end"])) for a in animals}
    summ = res["summ"]
    L = []
    w = L.append
    w(f"# Head-IMU inertial fusion with WISER (V4) — `wiser_baseline` ({cohort})\n")
    w("- **What this is:** a *measurement* report. Question: does a 6-axis inertial fusion of the head IMU (same rigid headstage as the WISER tag; user, 2026-09-29) with WISER fixes — an error-state Kalman filter driven by the accelerometer and gyroscope, corrected by WISER, + RTS smoother — predict held-out WISER fixes better than the best position-only smoother B2′? First, the IMU processing itself is measured and improved (user: \"if the IMU processing is poor it cannot improve WISER\"). **No behavioural claim.**")
    w(f"- **Nights:** tuning {scfg['nights']['tuning']['start']} → {scfg['nights']['tuning']['end']} (every choice made here); test {scfg['nights']['test']['start']} → {scfg['nights']['test']['end']} (named in the smoothing pilot's plan). Field-PC local time (EDT).")
    w("- **Animals and tags (shortid):** " + ", ".join(f"{a} = {tags[a]}" for a in animals) + ".")
    w("- **Frame status:** WISER native inches, unverified offset origin; the handedness test below concerns only the mirror sense of the WISER axes relative to the IMU; nothing places a position in the paddock.")
    w("- **Plan:** [`implementation_plan/2026-09-29-wiser-ins-fusion.md`](../../../../implementation_plan/2026-09-29-wiser-ins-fusion.md) (approved by the user 2026-09-29; amendments of 2026-09-30 fixed on the tuning night before the full run — §3, §9).")
    w(f"- **Run:** `python wiser/scripts/build_imu_wiser_cache.py --cohort {cohort}` (Phase A) then `python wiser/scripts/analyze_wiser_ins_fusion.py --cohort {cohort}` (Phases B–C); bulk `{out}`; pointer `run_manifest_ins_fusion_{cohort}.json`. Git `{res.get('git_commit')}`; runtime Phases B–C {res.get('runtime_s', 0) / 60:.1f} min (Phase A 2.5 min); numba {res.get('numba')}.\n")
    # ---------------- verdicts
    w("## 0. Verdicts\n")
    w("| Method | scheme | animals with Δ ≥ 3 % & CI > 0 | +1 h control: no gain | pooled Δ on moving fixes | **Verdict** |")
    w("|---|---|---|---|---|---|")
    for s, lab in (("a", "(a)"), ("a2", "(a′)")):
        p_ = ver["schemes"][s]
        w(f"| V4 INS | {lab} | {p_['n_animals_gain']}/5 | {p_['n_control_no_gain']}/5 | {_pct(p_['pooled_moving_d'])} | {p_['verdict']} |")
    w(f"\n**Overall V4 verdict (pre-registered acceptance): {ver['verdict']}.**\n")
    w("Pooled test-night held-out error (in), hidden fixes with ≥ 7 anchors, Δ vs B2′ (95 % block-bootstrap CI):\n")
    w("| Method | (a) median | (a) RMSE | (a) Δ median vs B2′ | (a′) median | (a′) RMSE | (a′) Δ median vs B2′ |")
    w("|---|---|---|---|---|---|---|")
    for m in ("B1", "B2", "B2p", "V1", "V2", "V4", "V4_shift"):
        row = [LABEL.get(m, m)]
        for s in ("a", "a2"):
            sm = summ["test"].get(f"{m}|{s}", {}).get("pooled", {})
            r = _crow(comp, s, "all", m, "B2p", "pooled")
            row += [_f(sm.get("med")), _f(sm.get("rmse")), "(reference)" if m == "B2p" else (_ci(r) if r is not None else "n/a")]
        w("| " + " | ".join(row) + " |")
    if pilot_summ:
        pm = {m: pilot_summ.get(f"{m}|a", {}).get("pooled", {}).get("med") for m in ("B1", "B2", "B2p", "V1", "V2")}
        dmax = max(abs(pm[m] - summ["test"][f"{m}|a"]["pooled"]["med"]) for m in pm if pm[m] is not None)
        nsame = all(pilot_summ.get(f"{m}|a", {}).get("pooled", {}).get("n") == summ["test"][f"{m}|a"]["pooled"]["n"] for m in pm)
        ok = dmax < 1e-3 and nsame
        w(f"\nReproduction check: B1/B2/B2′/V1/V2 pooled (a) medians {'match' if ok else 'DIFFER from'} the smoothing pilot's bulk summary "
          f"({', '.join(f'{m} {_f(pm[m], 3)}' for m in pm)}; largest difference {dmax:.1e} in — floating-point order in the parallel smoother — "
          f"and {'identical' if nsame else 'different'} scored counts), i.e. the same tracks, hidden sets and scored set.")
    # reading
    rv = {s: _crow(comp, s, "all", "V4", "B2p", "pooled") for s in ("a", "a2")}
    rs = {s: _crow(comp, s, "all", "V4_shift", "B2p", "pooled") for s in ("a", "a2")}
    st_ = {(s, sub): _crow(comp, s, sub, "V4", "B2p", "pooled") for s in ("a", "a2") for sub in ("still", "moving", "loco")}
    qt = q[q.role == "tuning"]
    w("\n**Reading.**\n")
    w(f"1. **IMU processing improved where it matters for inertial navigation.** Accelerometer: the diagonal ellipsoid "
      f"lowers the held-out quiet-window gravity residual from {_f(qt.grav_cv_scalar.median(), 3)} to {_f(qt.grav_cv_ellipsoid.median(), 3)} m/s² "
      f"(tuning-night medians; {dec['n_ellipsoid_better']}/5 animals better → {dec['acc_method']}); fitted offsets reach "
      f"{_f(np.nanmax([np.max(np.abs(json.loads(o))) for o in q.ell_o if isinstance(o, str) and o]), 2)} m/s² (≈ {_f(math.degrees(math.atan(np.nanmax([np.max(np.abs(json.loads(o))) for o in q.ell_o if isinstance(o, str) and o]) / G)), 1)}° of tilt), which a scalar k_a cannot remove. "
      f"Gyro: bias rule = {dec['bias_method']} (LOO still-run drift {_f(60 * dec['drift_med_block'], 2)} → {_f(60 * dec['drift_med_running'], 2)} °/min, block → running); "
      f"scale s* = {_f(dec['gyro_scale_star'], 3)} [{_f(dec['gyro_scale_ci'][0], 3)}, {_f(dec['gyro_scale_ci'][1], 3)}] from {dec['n_sds_pairs']} static–dynamic–static pairs → "
      f"{'applied' if dec['gyro_scale_applied'] else 'not applied (s = 1)'}. Low-pass: head-motion power stays above 2× the noise floor up to the 100-Hz search limit for both "
      f"sensors, so the rule lands on the 40-Hz clip (f_c acc {dec['fc']['acc']:.0f} Hz, gyro {dec['fc']['gyr']:.0f} Hz); single-sample spikes are rare. "
      f"Details §2.")
    if rv["a"] is not None:
        w(f"2. **V4 vs B2′ on the test night:** pooled Δ {_ci(rv['a'])} on (a) and {_ci(rv['a2'])} on (a′). "
          f"By IMU state (a): still {_ci(st_[('a', 'still')])}, moving {_ci(st_[('a', 'moving')])}, locomoting {_ci(st_[('a', 'loco')])}. "
          f"Animals passing the per-animal bar: (a) {ver['schemes']['a']['n_animals_gain']}/5, (a′) {ver['schemes']['a2']['n_animals_gain']}/5.")
        w(f"3. **+1 h control:** pooled Δ {_ci(rs['a'])} (a), {_ci(rs['a2'])} (a′); control no-gain in "
          f"{ver['schemes']['a']['n_control_no_gain']}/5 and {ver['schemes']['a2']['n_control_no_gain']}/5 animals. The aligned IMU is better than the shifted one "
          f"everywhere, so the IMU carries head-motion information — but not enough, integrated this way, to beat B2′.")
        if err is not None:
            ea = err[err.scheme == "a"]
            e4, eb = ea[ea.method == "V4"], ea[ea.method == "B2p"]
            w(f"4. **Where V4 fails — in-place head movement and divergence tails.** 'Moving' = active (IMU-moving, not locomoting: grooming, "
              f"rearing, head scanning in place) + locomoting. V4 ties B2′ while locomoting and loses while active (table §4b). Its errors are "
              f"heavy-tailed: {100 * (e4.e > 100).mean():.2f} % of scored hidden fixes are off by > 100 in (B2′ {100 * (eb.e > 100).mean():.3f} %; "
              f"V4 max {e4.e.max():,.0f} in), hence RMSE {_f(np.sqrt((e4.e ** 2).mean()), 1)} vs {_f(np.sqrt((eb.e ** 2).mean()), 1)} in. "
              f"These are inertial divergences inside hidden runs — attitude lost during violent head motion (the tilt-reset guard fired "
              f"{int(hand.tilt_resets_full.min())}–{int(hand.tilt_resets_full.max())} times per night) turning gravity into a spurious horizontal "
              f"acceleration that no fix corrects until the run ends. The filter is also overconfident (NIS ≈ 15, §6).")
    ht = hand[hand.night == sorted(hand.night.unique())[-1]]
    hu = hand[hand.night == sorted(hand.night.unique())[0]]
    npos = int((ht.llr > 0).sum()) + int((hu.llr > 0).sum())
    if npos == len(ht) + len(hu):
        hand_txt = ("the IMU-driven filter explains the WISER track better in the WISER frame as given than in its mirror image on every animal-night, "
                    "i.e. the evidence favours a right-handed WISER frame (x, y, z-up) — the same sign as the calibration pilot's M4 (rho > 0 on all five), "
                    "now with a likelihood ratio instead of a turn correlation")
    elif npos == 0:
        hand_txt = "the mirrored frame fits better on every animal-night, i.e. the evidence favours a left-handed (mirrored) WISER frame"
    else:
        hand_txt = "the sign is not consistent across animal-nights, so the handedness stays unresolved"
    w(f"5. **Handedness (reported, not used to choose the frame):** LLR normal − mirrored > 0 in {int((ht.llr > 0).sum())}/{len(ht)} animals on the test night "
      f"(median {_f(ht.llr.median(), 0)} nats, {_f(ht.llr_per_fix.median(), 3)} per fix) and {int((hu.llr > 0).sum())}/{len(hu)} on the tuning night "
      f"(median {_f(hu.llr.median(), 0)}): {hand_txt}. "
      + (f"Null check (post hoc, declared): with the +1 h-shifted IMU the same LLR is {int((hnull.llr > 0).sum())}/{len(hnull)} positive, "
         f"per fix {_f(hnull.llr_per_fix.min(), 3)} … {_f(hnull.llr_per_fix.max(), 3)} (median {_f(hnull.llr_per_fix.median(), 3)}) against "
         f"{_f(hand.llr_per_fix.min(), 3)} … {_f(hand.llr_per_fix.max(), 3)} with the aligned IMU. " if hnull is not None else "")
      + "Caveat: V4 is not a consistent model of these data (NIS ≈ 15), so the LLR is evidence from a misspecified filter; "
      "it stays a measurement result until one video event confirms the turn sense.")
    nt = nis[nis.night == sorted(nis.night.unique())[-1]]
    w(f"6. **Consistency:** test-night NIS mean {_f(nt.nis_mean.median(), 2)} (median over animals; χ²₂ expects 2) and "
      f"{_pct(nt['frac_gt_5.99'].median())[1:]} of fixes above 5.99 (expects 5 %); held-out z² mean (a) {_f(nt.heldout_z2_mean_a.median(), 2)}. "
      f"{'The filter is overconfident (innovations larger than its own covariance predicts).' if nt.nis_mean.median() > 3 else 'Roughly consistent.'}")
    w("\nClassification (regime-aware-wiser-tracking): every result here is a **measurement** result. The held-out target is a WISER fix "
      "(head position + WISER's slow drift + white noise), so a gain means better prediction of WISER — necessary, not sufficient, for better head position.\n")
    # ---------------- data & caches
    w("## 1. Data, caches and what they hold\n")
    info = res["info"]
    w("| Night | Animal | fixes in window | IMU samples (100 Hz) | IMU-still samples | saturated samples | IMU start (s after 21:00) |")
    w("|---|---|---|---|---|---|---|")
    for key in ("tuning", "test"):
        for a in animals:
            i_ = info[key][a]
            w(f"| {key} | {a} | {i_['n_fix']:,} | {i_['imu_samples']:,} | {i_['still_samples']:,} | {i_['sat_samples']:,} | {_f(i_['imu_t0_s'], 1)} |")
    fill = res.get("fill", {})
    nfill = {k: sum(v.values()) for k, v in fill.items()}
    w(f"\nHidden fixes with no V4 prediction (before the IMU start: SF08/SF12 test night) filled with B2′: {nfill}; they are not scored (IMU not QC-ok).\n")
    w("**Caches (built once; any later analysis can start from them without reading raw data):**\n")
    w("| Cache | Path | One file = | Content | Size |")
    w("|---|---|---|---|---|")
    w(f"| A1 raw IMU | `D:\\Field2026_analysis_out\\2026c\\imu_raw_cache\\<SFxx>\\<session>__<start>_<end>.npz` (+ `index_2026c.csv`) | animal-night, 20:50 → 05:30 (clipped to the session) | `six` int16 (n, 6) raw analogin lanes 1–6 (acc x/y/z, gyro x/y/z, **sensor frame**, counts) at 1250 Hz; `k0` first frame in the session, `amp0` = 16 k0; `sat` bool (n, 6) per lane (\\|raw\\| ≥ 32700); `frozen` bool (n) (all six lanes repeat ≥ 0.5 s); `fit_json` the verbatim `pc_time_fit.json`; `meta_json` (animal, MAC, session dir, start_local, windows, sha256 of the first 64 MiB of `analogin.dat`, size, mtime, git). Time of frame j: `build_imu_wiser_cache.cache_unix_ms()` = local midnight + `make_imu.pc_time_ms(amp0 + 16 j, fit)` | {sizes['a1']} |")
    w(f"| A2 WISER | `D:\\Field2026_analysis_out\\2026c\\wiser_fix_cache\\night_<YYYYMMDD>\\<SFxx>.csv.gz` (+ `index_2026c.csv`) | animal-night, night ± 10 min | deduplicated fixes (max anchors, then min reportid): reportid, shortid, t_ms (Unix ms, field-PC clock), x, y (in), anchors_used, anchors_list, n_list, dup_n, library `valid`, `speed_inps_smooth`, masks m_handling, m_silence (± 2 min), m_tag_validity, m_adc_lane (own logger) | {sizes['a2']} |")
    w(f"| A3 100-Hz IMU | `D:\\Field2026_analysis_out\\2026c\\imu100_cache\\<SFxx>\\night_<YYYYMMDD>.npz` | animal-night, same window as A1 | `t_unix_ms` (IMU clock, τ* **not** applied); `acc` float32 (n, 3) m/s² and `gyr` float32 (n, 3) °/s in the **head frame** (Hampel → {dec['fc']['acc']:.0f}-Hz zero-phase Butterworth-4 → resample_poly 2/25; {dec['acc_method']} accelerometer calibration; gyro bias ({dec['bias_method']}) removed, scale {dec['gyro_scale']:.3f}); flags `sat_acc`, `sat_gyr` (dilated), `frozen`, `spikes` (uint8, Hampel replacements in the sample's support), `quiet`; `calib_json` (all parameters incl. 1-min bias nodes), `meta_json` | {sizes['a3']} |")
    w(f"| C fusion | `{out}\\fusion\\night_<YYYYMMDD>\\<SFxx>\\v4_full.npz`, `v4_heldout.npz`; `persecond\\`; `csv\\` | animal-night | full-data V4 at every fix: smoothed `p`, `v`, `bw`, `zhat`, predictive `var`, attitude `q` (w, x, y, z), `ba`, `bg`, forward innovations `nu`, `S` (xx, xy, yy), `nis` (pass 0), IRLS weights `w`, `ll`, `yaw0`, parameter vector `par`; held-out: hidden masks (a)/(a′) + V4 and V4 +1 h predictions and variances + chosen yaws; per-second IMU tables (true and +1 h); `csv/yaw_hypotheses.csv` (every hypothesis ℓ, normal + mirrored), `heldout_errors_*.csv.gz` (every method, every scored fix), `bootstrap_comparisons_*.csv`, `imu_quality.csv`, `imu_saturation_lanes.csv`, `imu_spikes_lanes.csv`, `nis_consistency.csv`, `handedness.csv`, `plausibility_test.csv`, `tuning_grid_stage*.csv`; `phase_b\\psd_*.npz` | {sizes['c']} |")
    w("")
    w(DEFINITIONS)
    # ---------------- Phase B
    w("## 2. IMU quality and smoothing (Phase B)\n")
    w("### 2.1 Saturation and spikes\n")
    w("Head-frame names: sensor lane 1/2/3 = acc x/y/z → head up / −nose / −left; lane 4/5/6 = gyro x/y/z → head **yaw axis (z)** / −roll axis / −pitch axis (`make_imu.S`).\n")
    w("| Night | Animal | " + " | ".join(f"lane {l} samples (longest ms)" for l in range(1, 7)) + " | seconds with any saturation |")
    w("|---|---|" + "---|" * 7)
    for r in q.itertuples():
        w(f"| {r.night} | {r.animal} | " + " | ".join(f"{int(getattr(r, f'sat_lane{l}'))} ({_f(getattr(r, f'sat_lane{l}_longest_ms'), 1)})" for l in range(1, 7)) + f" | {int(r.sat_any_seconds)} |")
    w("\nHampel replacements per hour (still / moving time), lanes 1–6:\n")
    w("| Night | Animal | " + " | ".join(f"lane {l}" for l in range(1, 7)) + " |")
    w("|---|---|" + "---|" * 6)
    for r in q.itertuples():
        w(f"| {r.night} | {r.animal} | " + " | ".join(f"{_f(getattr(r, f'spk_lane{l}_still_per_h'), 1)} / {_f(getattr(r, f'spk_lane{l}_moving_per_h'), 1)}" for l in range(1, 7)) + " |")
    w(f"\n### 2.2 Noise floor and low-pass cutoff (tuning night)\n\n![psd](../figures/{figs.get('psd', '')})\n")
    cu = dec["cutoff"]
    w("| Sensor | noise floor N (3 axes) | P_moving/N at 5 / 20 / 40 Hz | f_c raw (pooled) | per-animal f_c raw | applied f_c |")
    w("|---|---|---|---|---|---|")
    for grp, unit in (("acc", "(m/s²)²/Hz"), ("gyr", "(°/s)²/Hz")):
        c = cu[grp]
        w(f"| {grp} | {c['noise_floor']:.2e} {unit} | {c['ratio_at_5hz']:.0f} / {c['ratio_at_20hz']:.0f} / {c['ratio_at_40hz']:.0f} | {c['fc_raw_hz']:.1f} Hz | "
          f"{', '.join(f'{k} {v:.0f}' for k, v in c['per_animal'].items())} | **{dec['fc'][grp]:.0f} Hz** |")
    w("\nThe still-period PSD is not white below ~100 Hz (it falls by ~2–3 decades from 40 to 200 Hz — the IMU's internal anti-alias filter and/or real micro-motion), so the pre-registered floor (150–500 Hz) sits below the in-band noise. Head-motion power exceeds even the in-band still level by 2–3 decades at 40 Hz, so under either definition the cutoff is bounded by the 40-Hz clip, not by the noise. The user's point (\"a head cannot turn that fast\") holds for large rotations, but small head vibrations carry power well above the noise to ≥ 40 Hz; they integrate to negligible angle and displacement, so the choice between 20 and 40 Hz is immaterial for navigation.\n")
    w("### 2.3–2.6 Calibration and before/after validation\n")
    w(f"![quality](../figures/{figs.get('quality', '')})\n")
    w("| Night | Animal | QS windows | coverage λ_min | gravity resid. CV scalar → ellipsoid (m/s²) | ellipsoid D | ellipsoid o (m/s²) | yaw drift before → after (°/min, median / p90) | kinematic r before → after | kinematic slope before → after | acc–gyro latency (ms) | SDS pairs, s* | Fusion pitch SD still before → after (°) | Fusion recovery share before → after | |α| p99.99 before → after (°/s²) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in q.itertuples():
        w(f"| {r.night} | {r.animal} | {int(r.n_qs_windows):,} | {_f(r.cov_eig_min, 3)} | {_f(r.grav_cv_scalar, 3)} → {_f(r.grav_cv_ellipsoid, 3)} | {r.ell_D} | {r.ell_o} | "
          f"{_f(60 * r.drift_before_med, 2)} / {_f(60 * r.drift_before_p90, 2)} → {_f(60 * r.drift_after_med, 2)} / {_f(60 * r.drift_after_p90, 2)} | "
          f"{_f(r.kin_before_r, 3)} → {_f(r.kin_after_r, 3)} | {_f(r.kin_before_slope, 3)} → {_f(r.kin_after_slope, 3)} | {_f(r.kin_latency_ms, 1)} | {int(r.sds_pairs)}, {_f(r.sds_s_star, 3)} | "
          f"{_f(r.fus_before_pitch_sd_still_med, 3)} → {_f(r.fus_after_pitch_sd_still_med, 3)} | {_f(r.fus_before_unreliable_frac, 4)} → {_f(r.fus_after_unreliable_frac, 4)} | "
          f"{r.alpha_before_p9999:,.0f} → {r.alpha_after_p9999:,.0f} |")
    nz = dec["noise"]
    w(f"\n**Decisions (tuning night):** accelerometer **{dec['acc_method']}** ({dec['n_ellipsoid_better']}/5 animals better held-out; each night then self-calibrated on its own quasi-static windows); "
      f"gyro bias **{dec['bias_method']}** (pooled LOO drift block {_f(60 * dec['drift_med_block'], 3)} vs running {_f(60 * dec['drift_med_running'], 3)} °/min); "
      f"gyro scale s* {_f(dec['gyro_scale_star'], 4)} [{_f(dec['gyro_scale_ci'][0], 4)}, {_f(dec['gyro_scale_ci'][1], 4)}] ({dec['n_sds_pairs']} pairs; per animal "
      f"{', '.join(f'{k} {v:.3f}' for k, v in dec['gyro_scale_per_animal'].items())}; make_imu chain {_f(dec['gyro_scale_before_chain'], 3)}) → **s = {dec['gyro_scale']:.3f}**; "
      f"cutoffs {dec['fc']['acc']:.0f}/{dec['fc']['gyr']:.0f} Hz. Still-period noise: σ_ω {_f(nz['sigma_omega_measured_dps'], 3)} °/s (used {_f(nz['sigma_omega_dps'], 3)}), "
      f"σ_f {_f(nz['sigma_f_measured_ms2'], 3)} m/s² (used {_f(nz['sigma_f_ms2'], 3)}), σ_g,still {nz['sigma_g_still']:.2e} rad/s/√Hz.\n")
    w("**How to read the kinematic columns.** r ≈ 0.75 and slope 1.1–1.5 barely move with calibration: the check is dominated by the head's linear acceleration (its slope grows with the analysis bandwidth; §3), so it is not a gyro-scale test. The static–dynamic–static s* is the clean one. The latency column is the lag (gyro relative to accelerometer) that maximises the kinematic r; it is measured, reported and **not applied** (a one-sample shift changed the tuning-night V4 error by < 0.1 %).\n")
    # ---------------- tuning
    w("## 3. Tuning (tuning night only) and the development amendments\n")
    w("**Development runs (SF09, tuning night, before the full run; no test-night V4 result existed):** with the design as first registered, V4 lost to B2′ on moving fixes (4.77 vs 4.34 in, NIS mean 14.5). "
      "Its tilt followed the make_imu Fusion tilt within ~3.5° most of the night but was lost completely (90–175°) for 20–25 min twice, because tilt was corrected only in IMU-still seconds. "
      "Adding a dynamic gravity update and a tilt-reset guard removed those episodes (angle to Fusion p90 7°) but V4 stayed ~5 % worse than B2′ (still fixes ~4 % better, moving ~6 % worse). "
      "More process noise made it worse (σ_a 1 → 6.1 in, 3 → 7.9 in), a residual WISER lag of −0.2…+0.45 s changed little, a one-sample gyro shift changed < 0.1 %, and the NIS of moving fixes was 2.3× that of still fixes. "
      "A filter-free check (make_imu's Fusion earth-frame acceleration integrated over 1/2/4 s) gave |Δv| 10–25× WISER's, growing linearly with the window: an acceleration error of ~0.25 m/s² sustained over seconds. "
      "The amendments (plan §Amendments) were fixed from this and the grid extended; they are deviations from the brief (§9).\n")
    w(f"Initial yaw per animal (default config, scheme (a) visible fixes): {', '.join(f'{a} {v:.0f}°' for a, v in res['tune_yaw_deg'].items())}.\n")
    g1s = g1.sort_values(["med", "rmse"]).head(6)
    w("Stage 1 (best 6 of 24; pooled median held-out error (a), in):\n")
    w("| σ_a (m/s²/√Hz) | σ_g (rad/s/√Hz) | σ_fd (m/s²) | median | RMSE |")
    w("|---|---|---|---|---|")
    for r in g1s.itertuples():
        w(f"| {r.sa} | {r.sg} | {r.sfd} | {r.med:.3f} | {r.rmse:.3f} |")
    g2s = g2.sort_values(["med", "rmse"]).head(6)
    w("\nStage 2 (best 6 of 18):\n")
    w("| σ_v (in/s) | T_b (s) | σ_b (in) | k_R | median | RMSE |")
    w("|---|---|---|---|---|---|")
    for r in g2s.itertuples():
        w(f"| {r.sv} | {r.tb} | {r.sb} | {r.kr} | {r.med:.3f} | {r.rmse:.3f} |")
    w("\nThe objective (pooled median) ignores the tails: the best-median configs have RMSE 70–100 in, while σ_a = 0.1 keeps RMSE near 23–30 in "
      "at a ~0.5 % worse median (grid CSVs). No setting on the tuning night brought V4's median near B2′'s.\n")
    b2p_t = summ["tuning"].get("B2p|a", {}).get("pooled", {}).get("med")
    w(f"\n**Tuned V4:** σ_a {tuned['sa']}, σ_g {tuned['sg']}, σ_fd {tuned['sfd']}, σ_v {tuned['sv']}, T_b {tuned['tb']}, σ_b {tuned['sb']}, k_R {tuned['kr']} → pooled median (a) {tuned['med']:.3f} in on the tuning night (B2′ {_f(b2p_t, 3)} in). "
      f"Edge hits: {', '.join(k for k, grid in (('σ_a', cfg['phase_c']['grid_stage1']['sa']), ('σ_g', cfg['phase_c']['grid_stage1']['sg']), ('σ_v', cfg['phase_c']['grid_stage2']['sv'])) if tuned[{'σ_a': 'sa', 'σ_g': 'sg', 'σ_v': 'sv'}[k]] in (min(grid), max(grid))) or 'none'}.\n")
    w("Tuning-night Δ vs B2′ (pooled, same statistics as the test): " + "; ".join(
        f"{LABEL.get(m, m)} (a) {_ci(_crow(comp_t, 'a', 'all', m, 'B2p', 'pooled'))}" for m in ("B1", "B2", "V2", "V4", "V4_shift") if _crow(comp_t, 'a', 'all', m, 'B2p', 'pooled') is not None) + ".\n")
    # ---------------- test night
    w(f"## 4. Test night — held-out results\n\n![heldout](../figures/{figs.get('heldout', '')})\n")
    for s, tl in (("a", "(a) runs of 4–8 hidden fixes"), ("a2", "(a′) hidden 2-s windows")):
        w(f"**{tl}** — median error (in) per animal and Δ vs B2′ [95 % CI]:\n")
        w("| Animal | scored | B1 | B2′ | V2 | V4 | V4 +1 h | Δ B1 | Δ V2 | Δ V4 | Δ V4 +1 h |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for who in animals + ["pooled"]:
            sm = lambda m: summ["test"].get(f"{m}|{s}", {}).get(who, {})  # noqa: E731
            cells = [who, f"{sm('B2p').get('n', 0):,}"] + [_f(sm(m).get("med")) for m in ("B1", "B2p", "V2", "V4", "V4_shift")]
            for m in ("B1", "V2", "V4", "V4_shift"):
                r = _crow(comp, s, "all", m, "B2p", who)
                cells.append(_ci(r) if r is not None else "n/a")
            w("| " + " | ".join(cells) + " |")
        w("\nBy IMU state (pooled; Δ vs B2′ [CI]):\n")
        w("| Subset | n | B2′ median (in) | Δ B1 | Δ V2 | Δ V4 | Δ V4 +1 h |")
        w("|---|---|---|---|---|---|---|")
        for sub in ("still", "moving", "loco"):
            rr = {m: _crow(comp, s, sub, m, "B2p", "pooled") for m in ("B1", "V2", "V4", "V4_shift")}
            r0 = rr["V4"]
            w(f"| {sub} | {int(r0.n) if r0 is not None else 0:,} | {_f(r0.med_ref) if r0 is not None else 'n/a'} | " + " | ".join(_ci(rr[m]) if rr[m] is not None else "n/a" for m in ("B1", "V2", "V4", "V4_shift")) + " |")
        rr = {m: _crow(comp, s, "all", m, "B2p", "pooled") for m in ("B1", "B2", "V2", "V4", "V4_shift")}
        w("\nRMSE-based Δ vs B2′ (pooled): " + "; ".join(f"{LABEL.get(m, m)} {_pct(rr[m].d_rmse)} [{_pct(rr[m].rmse_lo)}, {_pct(rr[m].rmse_hi)}]" for m in rr if rr[m] is not None) + ".\n")
    r = _crow(comp, "a", "all", "V4", "B2", "pooled")
    if r is not None:
        w(f"V4 vs B2 (no drift term), pooled (a): {_ci(r)}.\n")
    if err is not None:
        w("### 4b. Error tails by IMU state (test night, pooled; active = IMU-moving but not locomoting)\n")
        w("| Scheme | state | n | B2′ median | V4 median | Δ V4 (median) | B2′ > 24 in | V4 > 24 in | V4 > 100 in | V4 max (in) | V4 +1 h > 24 in |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for sch, sl in (("a", "(a)"), ("a2", "(a′)")):
            es = err[err.scheme == sch]
            piv = {m: es[es.method == m].set_index(["animal", "i"]) for m in ("B2p", "V4", "V4_shift")}
            j = piv["V4"][["e", "still", "loco", "moving"]].join(piv["B2p"][["e"]], rsuffix="_b").join(piv["V4_shift"][["e"]], rsuffix="_s")
            j["state"] = np.where(j.still, "still", np.where(j.loco, "locomoting", np.where(j.moving, "active", "other")))
            for stt in ("still", "locomoting", "active"):
                g = j[j.state == stt]
                if not len(g):
                    continue
                w(f"| {sl} | {stt} | {len(g):,} | {_f(g.e_b.median())} | {_f(g.e.median())} | {_pct(1 - g.e.median() / g.e_b.median())} | "
                  f"{100 * (g.e_b > 24).mean():.2f} % | {100 * (g.e > 24).mean():.2f} % | {100 * (g.e > 100).mean():.2f} % | {g.e.max():,.0f} | "
                  f"{100 * (g.e_s > 24).mean():.2f} % |")
        w("")
    if figs.get("example"):
        w(f"![example](../figures/{figs['example']})\n")
    # ---------------- handedness
    w(f"## 5. Heading hypotheses and handedness\n\n![heading](../figures/{figs.get('heading', '')})\n")
    w("| Night | Animal | ML initial yaw (°) | ML yaw, mirrored (°) | ℓ normal | ℓ mirrored | **LLR normal − mirrored** | LLR per fix | tilt resets (full data, pass 0) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in hand.itertuples():
        w(f"| {r.night} | {r.animal} | {r.yaw0_deg:.0f} | {r.yaw0_mirrored_deg:.0f} | {r.ll_normal:,.0f} | {r.ll_mirrored:,.0f} | **{r.llr:+,.0f}** | {r.llr_per_fix:+.4f} | {int(r.tilt_resets_full)} |")
    if hnull is not None:
        w("\n**Null check (post hoc, declared): the same full-data hypothesis runs with the +1 h-shifted IMU** (`csv/handedness_shift_null.csv`):\n")
        w("| Night | Animal | LLR normal − mirrored (+1 h IMU) | per fix | aligned-IMU LLR per fix |")
        w("|---|---|---|---|---|")
        for r_ in hnull.itertuples():
            al = hand[(hand.night == r_.night) & (hand.animal == r_.animal)].llr_per_fix
            w(f"| {r_.night} | {r_.animal} | {r_.llr:+,.0f} | {r_.llr_per_fix:+.4f} | {float(al.iloc[0]) if len(al) else float('nan'):+.4f} |")
    hf = hyp[hyp.run == "full"]
    npk, spread = [], []
    for (nt_, a_, fr_), h_ in hf.groupby(["night", "animal", "frame"]):
        v = h_.sort_values("yaw0_deg").ll.to_numpy()
        npk.append(int(np.sum((v > np.roll(v, 1)) & (v > np.roll(v, -1)))))
        if fr_ == "normal":
            spread.append(float((v.max() - v.min()) / max(h_.n.max(), 1)))
    w(f"\nLocal maxima per hypothesis curve (24 yaws, circular): {min(npk)}–{max(npk)} (median {int(np.median(npk))}); spread of ℓ across yaws in the normal frame "
      f"{_f(min(spread), 4)}–{_f(max(spread), 4)} nats per fix. The LLR is a pseudo-likelihood ratio (soft-gated innovations), large because it sums ~10⁵ fixes; the per-fix value is the more comparable number.\n")
    # ---------------- consistency & smoothness
    w("## 6. Consistency and track smoothness\n")
    w("| Night | Animal | fixes | NIS mean | NIS median | share NIS > 5.99 | NIS mean (≥ 7 anchors) | share IRLS w < 1 | held-out z² mean (a) / (a′) | share z² > 5.99 (a) |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for _, r in nis.iterrows():
        w(f"| {r['night']} | {r['animal']} | {int(r['n']):,} | {_f(r['nis_mean'])} | {_f(r['nis_median'])} | {100 * r['frac_gt_5.99']:.1f} % | "
          f"{_f(r['nis_mean_ge7'])} | {100 * r['irls_w_lt1']:.1f} % | {_f(r['heldout_z2_mean_a'])} / {_f(r['heldout_z2_mean_a2'])} | "
          f"{100 * r['heldout_frac_gt_5.99_a']:.1f} % |")
    w("\nχ²₂ expects mean 2, median 1.39 and 5 % above 5.99.\n")
    w("Track plausibility (test night, full data):\n")
    w("| Animal | method | v p50 | v p95 | v p99 (in/s) | a p99 (in/s²) | path (in/h) | beyond wall > 15 in | v during IMU-still p50 / p95 | V4 velocity state p50 / p95 / p99 |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in plaus.itertuples():
        vs = f"{_f(r.v_state_p50)} / {_f(r.v_state_p95)} / {_f(r.v_state_p99)}" if r.method == "V4_p" and hasattr(r, "v_state_p50") and np.isfinite(r.v_state_p50) else ""
        w(f"| {r.animal} | {r.method} | {_f(r.v_p50)} | {_f(r.v_p95, 1)} | {_f(r.v_p99, 1)} | {_f(r.a_p99, 0)} | {r.path_in_per_h:,.0f} | {100 * r.wall_out_frac:.3f} % | {_f(r.v_still_p50)} / {_f(r.v_still_p95)} | {vs} |")
    w("\nPath length and speed depend on the smoothing scale (Noonan et al. 2019); none of these is 'the true distance'.\n")
    # ---------------- caveats & deviations
    w("## 8. Caveats\n")
    w("- **One test night, five animals, regime B** (2026-09-10/11); regime A and the post-09-11 population are not covered.")
    w("- **The held-out target is a WISER fix**, which includes WISER's own slow drift and whatever smoothing the WISER engine applies internally. If WISER positions are internally low-passed/delayed, a smooth position-only model can predict them better than an accurate head trajectory; the INS predicts the head, not WISER's filter. Static references (smoothing pilot §6) are the only test against a constant truth.")
    w("- **Lever arm ignored:** the tag and the IMU are a few cm apart on the headstage; head rotations move the tag relative to the IMU by up to ~2× that distance.")
    w("- **2-D, z fixed:** the head's vertical motion (bobbing, rearing) is not modelled; tilt errors couple it and gravity into the horizontal channel.")
    w("- **Saturation:** the head-yaw gyro (lane 4) clips at 2000 °/s in hundreds of short bursts per night; those samples get inflated process noise, and the attitude is re-anchored by the gravity updates and the tilt-reset guard.")
    w("- **Per-anchor noise** comes from IMU-still bouts (smoothing pilot); k_R allows a larger white variance for moving fixes.")
    w("- **The pseudo-likelihood** uses soft-gated innovations and assumes the tuned noise model; the LLR magnitude is not a calibrated probability.")
    w("- **Tuning:** the grids and the amendments were chosen on the tuning night; development used one animal (SF09) of the tuning night.")
    w("- **V4 is misspecified on these data** (NIS mean ≈ 15, ~55 % of fixes above the 95 % χ² bound, IRLS down-weights ~45 %): its covariances are too small and its tracks show divergence excursions (1.6–4 % of full-data fixes > 15 in beyond the wall ridge vs ≤ 0.14 % for B2′; §6). The FAIL is a statement about this filter with this IMU processing, not a proof that no inertial fusion can help. Candidate reasons, untested here: attitude errors during violent head motion (saturated yaw gyro, 100-Hz propagation of > 1000 °/s rotations, 40-Hz low-pass), the IMU↔tag lever arm, WISER's internal smoothing, and the vertical channel being discarded.")
    w("- **What would be needed next** (not run): a divergence detector that hands a segment to B2′ when the INS and the fixes disagree, propagation at 1250 Hz through fast rotations, the lever arm as a state, and a direct test against a static truth (fixed tag on a moving mount) rather than held-out WISER fixes.")
    w("\n## 9. Deviations from the brief and the plan\n")
    w("- **A1 window extended** to 05:30 (night + 1 h 10 min) so the +1 h control needs no second raw read.")
    w("- **A2 as csv.gz**, not parquet (pyarrow is not installed).")
    w("- **Hampel floor:** the local 7-sample MAD is floored at the lane's global noise SD (self-test showed ~3 × 10⁻³ false flags on pure noise otherwise); changed before any real-data run.")
    w("- **ZARU and the still-period gravity update** added to the filter (plan, before coding); **gyro process noise in still samples** = the measured noise density (plan, before coding).")
    w("- **Amendments of 2026-09-30 (tuning night only, before any test-night V4 result):** dynamic gravity update, tilt-reset guard, grid extended with σ_fd, σ_a = 0.01 and the moving-fix factor k_R; default σ_a for the tuning-night yaw selection 0.1.")
    w("- **Yaw selection for the tuning grid** done once per animal with the default config (runtime).")
    w("- **Acc–gyro latency** measured, not applied (no effect on the tuning night).")
    w("- **Low-pass cutoff** set by the 40-Hz clip (the registered rule never found the noise floor below 100 Hz).")
    w("- **Control criterion** read as in the smoothing pilot: 'no significant gain' = CI lower bound ≤ 0 in ≥ 4 of 5 animals; the moving-fix condition pooled.")
    w("- **Post hoc (declared, no verdict uses it):** the handedness null with the +1 h-shifted IMU (§5) and the error-tail table (§4b) were added after the test-night result.")
    return "\n".join(L) + "\n"


def finish(out: Path, cohort: str) -> None:
    """Figures + report + manifest pointers from a run directory (also used by --report-only)."""
    out = Path(out)
    res = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    cfg = json.loads((REPO / "wiser" / "configs" / f"wiser_ins_fusion_{cohort}.json").read_text(encoding="utf-8"))
    scfg = json.loads((REPO / cfg["smoothing_config"]).read_text(encoding="utf-8"))
    res["accept"] = cfg["accept"]
    csv = out / "csv"
    q = pd.read_csv(csv / "imu_quality.csv")
    q["role"] = pd.Categorical(q["role"], ["tuning", "test"])
    q = q.sort_values(["role", "animal"]).reset_index(drop=True)
    sat = pd.read_csv(csv / "imu_saturation_lanes.csv")
    spk = pd.read_csv(csv / "imu_spikes_lanes.csv")
    comp = pd.read_csv(csv / "bootstrap_comparisons_test.csv")
    comp_t = pd.read_csv(csv / "bootstrap_comparisons_tuning.csv")
    hand = pd.read_csv(csv / "handedness.csv")
    nis = pd.read_csv(csv / "nis_consistency.csv")
    plaus = pd.read_csv(csv / "plausibility_test.csv")
    hyp = pd.read_csv(csv / "yaw_hypotheses.csv")
    g1 = pd.read_csv(csv / "tuning_grid_stage1.csv")
    g2 = pd.read_csv(csv / "tuning_grid_stage2.csv")
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(out, res, q, comp, hyp, fdir, cohort)

    def dsize(p: Path, pat: str) -> str:
        fs = list(Path(p).rglob(pat))
        return f"{len(fs)} files, {sum(f.stat().st_size for f in fs) / 1e6:,.0f} MB"

    roots = {k: Path(v) for k, v in cfg["cache_roots"].items()}
    sizes = {"a1": dsize(roots["imu_raw"], "*.npz"), "a2": dsize(roots["wiser_fix"], "*.csv.gz"), "a3": dsize(roots["imu100"], "*.npz"),
             "c": dsize(out, "*.*")}
    pilot_summ = None
    pr = Path(scfg["tuned"]["run_dir"]) / "summary.json"
    if pr.exists():
        pilot_summ = json.loads(pr.read_text(encoding="utf-8")).get("summ_test")
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    err = pd.read_csv(csv / "heldout_errors_test.csv.gz")
    hnull = pd.read_csv(csv / "handedness_shift_null.csv") if (csv / "handedness_shift_null.csv").exists() else None
    rep.write_text(render_report(out, res, cfg, scfg, q, sat, spk, comp, comp_t, hand, nis, plaus, g1, g2, figs, cohort, sizes, pilot_summ, hyp,
                                 err, hnull),
                   encoding="utf-8")
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name,
            "driver": "wiser/scripts/analyze_wiser_ins_fusion.py", "cache_builder": "wiser/scripts/build_imu_wiser_cache.py",
            "config": f"wiser/configs/wiser_ins_fusion_{cohort}.json", "git_commit": res.get("git_commit"),
            "runtime_s": round(float(res.get("runtime_s", 0)), 1), "caches": {k: str(v) for k, v in roots.items()},
            "figures": [v for k, v in figs.items() if isinstance(v, str)]}
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_ins_fusion_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    print(f"report: {rep}\nmanifest: {mp}\nfigures: {figs}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--threads", type=int, default=20)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--report-only", default=None, help="regenerate figures + report from an existing run dir")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.report_only:
        finish(Path(a.report_only), a.cohort)
        return
    run(a.cohort, a.threads, a.workers)


if __name__ == "__main__":
    main()
