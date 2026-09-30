r"""WISER + head-IMU smoothing pilot: can the head IMU improve WISER UWB position accuracy beyond a good position-only
smoother?

Plan: implementation_plan/2026-09-29-wiser-imu-smoothing-pilot.md (approved by the user 2026-09-29, "开始").
Report (full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_imu_smoothing_pilot_<cohort>.md

Methods (per tag and night, WISER inches, times aligned onto the IMU clock by the animal's tau*):
  B1   library centred 7-sample coordinate-wise median (wiser_analysis_utils.add_speed); a hidden fix = median of the 7
       visible fixes nearest in time
  B2   robust constant-velocity Kalman filter + RTS smoother per axis, per-fix R from anchors_used (robust SD, tuning-night
       IMU-still bouts), soft chi2 innovation gate (pass 0) + Huber IRLS on smoothed residuals (passes 1..n)
  B2'  B2 + per-axis AR(1) measurement drift b (state (p, v, b)); a hidden fix is predicted by p + b
  V1   B2' + zero-velocity pseudo-measurement at every step whose aligned second is IMU-still
  V2   B2' with the process noise switched by the IMU state (still / active / locomoting)
  V3   heading-aided, only if the tuning-night turn diagnostic passes (rho >= 0.5 in >= 4 of 5 animals)
  controls: V1/V2 with every IMU input taken from t + 1 h
Evaluation: (a) 20 % of fixes hidden in runs of 4-8, (a') a random 10 % of 2-s windows hidden; e = |z - z_hat| on hidden
fixes with >= 7 anchors; paired 5-min block bootstrap vs B2'. Tuning night 2026-09-08/09, test night 2026-09-10/11
(21:00-04:20). Secondary: static references (dropped implant, cohort-1 fixed tags) and track plausibility.

Inputs (all read-only): the WISER SQLite copies (wiser_io._connect_readonly: mode=ro + query_only), make_imu 50-Hz npz,
the previous pilot's masks and helpers (imported from analyze_imu_wiser_calibration.py, unmodified).

Usage:
  python wiser/scripts/analyze_wiser_imu_smoothing.py --cohort 2026c
  python wiser/scripts/analyze_wiser_imu_smoothing.py --selftest      # synthetic data, no field data needed
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import wiser_io  # noqa: E402
import analyze_imu_wiser_calibration as C  # noqa: E402  (previous pilot: masks, IMU loader, helpers; reused unmodified)
from cohorts import load_cohort  # noqa: E402  (put on sys.path by the import above)

try:  # numba makes the Kalman loops ~100x faster; the pure-Python fallback gives the same numbers, slowly
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
NAME = "wiser_imu_smoothing_pilot"
STEM = f"{DIRECTION}_imu_smoothing_pilot"
FS_IMU = 50.0
GATE2 = 13.8155            # chi2_2 0.999 quantile: pass-0 soft innovation gate
HUBER_K = 2.5              # Huber constant on the 2-D Mahalanobis residual (fixed a priori)
N_IRLS = 2                 # IRLS passes after the gated pass
P0_POS, P0_VEL = 1.0e4, 400.0
MIN_ANCHORS_SCORE = 7
HIDE_RUN = (4, 8)          # (a): run lengths 4..8 fixes
HIDE_GAP = (1, 47)         # (a): visible gaps 1..47 fixes -> E[hidden] = 6 / (6 + 24) = 20 %
WIN_S, WIN_FRAC = 2.0, 0.10  # (a')
BLOCK_S = 300
N_BOOT = 1000
WALL_OUT_IN = 15.0
SPEED_LOCO_INPS, SPEED_STILL_INPS = 10.0, 3.0
ACCEPT = {"min_gain": 0.03, "min_animals": 4, "moving_max_loss": -0.02}
STATE_NAMES = {0: "IMU not usable", 1: "still", 2: "active", 3: "locomoting"}
METHODS_ALL = ["B1", "B2", "B2p", "V1", "V2", "V1_shift", "V2_shift"]
LABEL = {"B1": "B1 median-7", "B2": "B2 robust CV", "B2p": "B2′ + drift", "V1": "V1 ZUPT", "V2": "V2 IMU-switched q",
         "V1_shift": "V1 (IMU +1 h)", "V2_shift": "V2 (IMU +1 h)", "B2p_p": "B2′ (p only)", "raw": "raw fixes"}


# ================================================================ Kalman core
@njit(cache=True)
def _inv_small(A, ns, out):
    """Inverse of a symmetric positive-definite ns x ns (ns = 2 or 3) matrix."""
    if ns == 2:
        det = A[0, 0] * A[1, 1] - A[0, 1] * A[1, 0]
        out[0, 0] = A[1, 1] / det
        out[1, 1] = A[0, 0] / det
        out[0, 1] = -A[0, 1] / det
        out[1, 0] = -A[1, 0] / det
        return
    a, b, c = A[0, 0], A[0, 1], A[0, 2]
    d, e, f = A[1, 0], A[1, 1], A[1, 2]
    g, h, i = A[2, 0], A[2, 1], A[2, 2]
    c00 = e * i - f * h
    c01 = -(d * i - f * g)
    c02 = d * h - e * g
    det = a * c00 + b * c01 + c * c02
    out[0, 0] = c00 / det
    out[1, 0] = c01 / det
    out[2, 0] = c02 / det
    out[0, 1] = -(b * i - c * h) / det
    out[1, 1] = (a * i - c * g) / det
    out[2, 1] = -(a * h - b * g) / det
    out[0, 2] = (b * f - c * e) / det
    out[1, 2] = -(a * f - c * d) / det
    out[2, 2] = (a * e - b * d) / det


@njit(cache=True)
def _kf_rts(t, z, r2tot, vis, st_mid, st_at, q, mult, tb, sb2, sv2, huber_k, m_rej, gate2, n_iter, P_out, B_out, V_out):
    """Robust CV (+ AR(1) drift) Kalman filter + RTS smoother, two independent axes coupled only by the outlier weights.

    t (n,) s, increasing; z (n, 2) in; r2tot (n, 2) in^2 per-fix total measurement variance; vis (n,) bool = fix used;
    st_mid (n,) int8 IMU state of the interval (t[k-1], t[k]] (0 unusable, 1 still, 2 active, 3 loco), st_at (n,) state at
    t[k]; q in^2/s^3; mult (4,) process-noise multipliers per state; tb s and sb2 in^2 = drift time constant / variance
    (sb2 = 0: no drift state); sv2 (in/s)^2 zero-velocity pseudo-measurement variance at still steps (<= 0: off).
    Writes the smoothed p, b, v (n, 2) into P_out, B_out, V_out. White measurement variance = max(r2tot - sb2, r2tot/4)."""
    n = t.shape[0]
    drift = sb2 > 0.0
    ns = 3 if drift else 2
    xf = np.zeros((n, 2, 3))
    Pf = np.zeros((n, 2, 3, 3))
    xp = np.zeros((n, 2, 3))
    Pp = np.zeros((n, 2, 3, 3))
    dts = np.zeros(n)
    phis = np.ones(n)
    w = np.ones(n)
    r2w = np.empty((n, 2))
    F = np.zeros((3, 3))
    FP = np.zeros((3, 3))
    Pi = np.zeros((3, 3))
    Cm = np.zeros((3, 3))
    x = np.zeros(3)
    P = np.zeros((3, 3))
    PHt = np.zeros(3)
    dx = np.zeros(3)
    nu = np.zeros(2)
    S = np.zeros(2)
    for k in range(n):
        for a in range(2):
            v = r2tot[k, a]
            if drift:
                v2 = v - sb2
                if v2 < 0.25 * v:
                    v2 = 0.25 * v
                r2w[k, a] = v2
            else:
                r2w[k, a] = v
        if k > 0:
            dt = t[k] - t[k - 1]
            if dt < 0.0:
                dt = 0.0
            dts[k] = dt
            if drift and tb > 0.0:
                phis[k] = math.exp(-dt / tb)
    k0 = 0
    while k0 < n and not vis[k0]:
        k0 += 1
    if k0 == n:
        for k in range(n):
            for a in range(2):
                P_out[k, a] = np.nan
                B_out[k, a] = np.nan
                V_out[k, a] = np.nan
        return
    for it in range(n_iter + 1):
        # ---------------- forward filter
        for k in range(n):
            if k == 0:
                for a in range(2):
                    for i in range(3):
                        xp[0, a, i] = 0.0
                        for j in range(3):
                            Pp[0, a, i, j] = 0.0
                    xp[0, a, 0] = z[k0, a]
                    Pp[0, a, 0, 0] = P0_POS
                    Pp[0, a, 1, 1] = P0_VEL
                    if drift:
                        Pp[0, a, 2, 2] = sb2
            else:
                dt = dts[k]
                ph = phis[k]
                qk = q * mult[st_mid[k]]
                for i in range(3):
                    for j in range(3):
                        F[i, j] = 0.0
                F[0, 0] = 1.0
                F[0, 1] = dt
                F[1, 1] = 1.0
                F[2, 2] = ph
                for a in range(2):
                    for i in range(ns):
                        s_ = 0.0
                        for j in range(ns):
                            s_ += F[i, j] * xf[k - 1, a, j]
                        xp[k, a, i] = s_
                    for i in range(ns):
                        for j in range(ns):
                            s_ = 0.0
                            for l in range(ns):
                                s_ += F[i, l] * Pf[k - 1, a, l, j]
                            FP[i, j] = s_
                    for i in range(ns):
                        for j in range(ns):
                            s_ = 0.0
                            for l in range(ns):
                                s_ += FP[i, l] * F[j, l]
                            Pp[k, a, i, j] = s_
                    Pp[k, a, 0, 0] += qk * dt * dt * dt / 3.0
                    Pp[k, a, 0, 1] += qk * dt * dt / 2.0
                    Pp[k, a, 1, 0] += qk * dt * dt / 2.0
                    Pp[k, a, 1, 1] += qk * dt
                    if drift:
                        Pp[k, a, 2, 2] += sb2 * (1.0 - ph * ph)
            # measurement update (both axes; gate/weights shared)
            use = vis[k] and (it == 0 or w[k] > 0.0)
            infl = 1.0
            if use:
                d2 = 0.0
                for a in range(2):
                    hx = xp[k, a, 0] + (xp[k, a, 2] if drift else 0.0)
                    nu[a] = z[k, a] - hx
                    hph = Pp[k, a, 0, 0]
                    if drift:
                        hph += 2.0 * Pp[k, a, 0, 2] + Pp[k, a, 2, 2]
                    rr = r2w[k, a] if it == 0 else r2w[k, a] / w[k]
                    S[a] = hph + rr
                    d2 += nu[a] * nu[a] / S[a]
                if it == 0 and d2 > gate2:
                    infl = d2 / gate2
            for a in range(2):
                for i in range(3):
                    x[i] = xp[k, a, i]
                    for j in range(3):
                        P[i, j] = Pp[k, a, i, j]
                if use:
                    rr = r2w[k, a] * infl if it == 0 else r2w[k, a] / w[k]
                    for i in range(ns):
                        PHt[i] = P[i, 0] + (P[i, 2] if drift else 0.0)
                    s_ = PHt[0] + (PHt[2] if drift else 0.0) + rr
                    for i in range(ns):
                        x[i] += PHt[i] / s_ * nu[a]
                    for i in range(ns):
                        for j in range(ns):
                            P[i, j] -= PHt[i] * PHt[j] / s_
                if sv2 > 0.0 and st_at[k] == 1:
                    for i in range(ns):
                        PHt[i] = P[i, 1]
                    s_ = P[1, 1] + sv2
                    innov = -x[1]
                    for i in range(ns):
                        x[i] += PHt[i] / s_ * innov
                    for i in range(ns):
                        for j in range(ns):
                            P[i, j] -= PHt[i] * PHt[j] / s_
                for i in range(ns):
                    xf[k, a, i] = x[i]
                    for j in range(ns):
                        Pf[k, a, i, j] = 0.5 * (P[i, j] + P[j, i])
        # ---------------- RTS smoother (means only)
        for a in range(2):
            for i in range(3):
                x[i] = xf[n - 1, a, i]
            P_out[n - 1, a] = x[0]
            V_out[n - 1, a] = x[1]
            B_out[n - 1, a] = x[2] if drift else 0.0
            for k in range(n - 2, -1, -1):
                dt = dts[k + 1]
                for i in range(3):
                    for j in range(3):
                        F[i, j] = 0.0
                F[0, 0] = 1.0
                F[0, 1] = dt
                F[1, 1] = 1.0
                F[2, 2] = phis[k + 1]
                for i in range(ns):
                    for j in range(ns):
                        P[i, j] = Pp[k + 1, a, i, j]
                _inv_small(P, ns, Pi)
                # C = Pf[k] F^T Pp[k+1]^-1
                for i in range(ns):
                    for j in range(ns):
                        s_ = 0.0
                        for l in range(ns):
                            s_ += Pf[k, a, i, l] * F[j, l]
                        FP[i, j] = s_
                for i in range(ns):
                    for j in range(ns):
                        s_ = 0.0
                        for l in range(ns):
                            s_ += FP[i, l] * Pi[l, j]
                        Cm[i, j] = s_
                for i in range(ns):
                    dx[i] = x[i] - xp[k + 1, a, i]
                for i in range(ns):
                    s_ = xf[k, a, i]
                    for j in range(ns):
                        s_ += Cm[i, j] * dx[j]
                    PHt[i] = s_
                for i in range(ns):
                    x[i] = PHt[i]
                P_out[k, a] = x[0]
                V_out[k, a] = x[1]
                B_out[k, a] = x[2] if drift else 0.0
        # ---------------- IRLS weights from the smoothed residuals
        if it < n_iter:
            for k in range(n):
                if not vis[k]:
                    continue
                m2 = 0.0
                for a in range(2):
                    r = z[k, a] - P_out[k, a] - B_out[k, a]
                    m2 += r * r / r2w[k, a]
                m = math.sqrt(m2)
                if m <= huber_k:
                    w[k] = 1.0
                elif m <= m_rej:
                    w[k] = huber_k / m
                else:
                    w[k] = 0.0


@njit(parallel=True, cache=True)
def _kf_batch(t, z, r2tot, vis_s, stmid_s, stat_s, cq, cmult, ctb, csb2, csv2, cmrej, cvis, csrc, huber_k, gate2, n_iter,
              P_out, B_out, V_out):
    for i in prange(cq.shape[0]):
        _kf_rts(t, z, r2tot, vis_s[cvis[i]], stmid_s[csrc[i]], stat_s[csrc[i]], cq[i], cmult[i], ctb[i], csb2[i],
                csv2[i], huber_k, cmrej[i], gate2, n_iter, P_out[i], B_out[i], V_out[i])


def kf_run(t, z, r2tot, vis_list, st_mid_list, st_at_list, cfgs, chunk: int = 24):
    """Run a list of smoother configs on one track. cfg keys: q, tb, sb, sv (0 = off), mult (4,), mrej, vis (index into
    vis_list), src (index into the IMU-state lists). Returns (P, B, V) arrays (n_cfg, n, 2)."""
    t = np.ascontiguousarray(t, np.float64)
    z = np.ascontiguousarray(z, np.float64)
    r2tot = np.ascontiguousarray(r2tot, np.float64)
    vis_s = np.ascontiguousarray(np.stack(vis_list).astype(np.bool_))
    stmid = np.ascontiguousarray(np.stack(st_mid_list).astype(np.int8))
    stat = np.ascontiguousarray(np.stack(st_at_list).astype(np.int8))
    n = len(t)
    Pall, Ball, Vall = (np.empty((len(cfgs), n, 2)) for _ in range(3))
    for c0 in range(0, len(cfgs), chunk):
        cc = cfgs[c0:c0 + chunk]
        m = len(cc)
        cq = np.array([c["q"] for c in cc], float)
        cmult = np.array([c.get("mult", (1.0, 1.0, 1.0, 1.0)) for c in cc], float)
        ctb = np.array([c.get("tb", 0.0) for c in cc], float)
        csb2 = np.array([c.get("sb", 0.0) ** 2 for c in cc], float)
        csv2 = np.array([(c.get("sv") or 0.0) ** 2 for c in cc], float)
        cmrej = np.array([c.get("mrej", 1e9) for c in cc], float)
        cvis = np.array([c.get("vis", 0) for c in cc], np.int64)
        csrc = np.array([c.get("src", 0) for c in cc], np.int64)
        Po, Bo, Vo = (np.empty((m, n, 2)) for _ in range(3))
        _kf_batch(t, z, r2tot, vis_s, stmid, stat, cq, cmult, ctb, csb2, csv2, cmrej, cvis, csrc, HUBER_K, GATE2, N_IRLS,
                  Po, Bo, Vo)
        Pall[c0:c0 + m], Ball[c0:c0 + m], Vall[c0:c0 + m] = Po, Bo, Vo
    return Pall, Ball, Vall


# ================================================================ B1 and helpers
def b1_full(z: np.ndarray, window: int = 7) -> np.ndarray:
    """Library smoothing: centred rolling coordinate-wise median of `window` samples, min_periods=1 (as add_speed)."""
    return np.column_stack([pd.Series(z[:, a]).rolling(window, center=True, min_periods=1).median().to_numpy()
                            for a in range(2)])


def b1_predict(t_vis: np.ndarray, z_vis: np.ndarray, t_q: np.ndarray, k: int = 7) -> np.ndarray:
    """Coordinate-wise median of the k visible fixes nearest in time to each query time."""
    j = np.searchsorted(t_vis, t_q)
    cand = j[:, None] + np.arange(-k, k)[None, :]
    valid = (cand >= 0) & (cand < len(t_vis))
    cc = np.clip(cand, 0, len(t_vis) - 1)
    d = np.where(valid, np.abs(t_vis[cc] - t_q[:, None]), np.inf)
    o = np.argsort(d, axis=1, kind="stable")[:, :k]
    pick = np.take_along_axis(cc, o, axis=1)
    return np.column_stack([np.median(z_vis[pick, a], axis=1) for a in range(2)])


def dedup_fixes(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One fix per (shortid, timestamp): keep the largest anchors_used, ties -> the smallest reportid."""
    n0 = len(df)
    g = df.groupby(["shortid", "timestamp"]).size()
    nd = int((g > 1).sum())
    same_xy = int(df.duplicated(["shortid", "timestamp", "location_x", "location_y"], keep="first").sum())
    d = df.sort_values(["shortid", "timestamp", "anchors_used", "reportid"], ascending=[True, True, False, True],
                       kind="stable")
    d = d[~d.duplicated(["shortid", "timestamp"], keep="first")]
    return d, {"rows": n0, "dup_groups": nd, "rows_dropped": n0 - len(d), "dropped_same_xy": same_xy}


def hide_runs(n: int, rng: np.random.Generator, run=HIDE_RUN, gap=HIDE_GAP) -> np.ndarray:
    """(a): runs of run[0]..run[1] consecutive fixes hidden, separated by gap[0]..gap[1] visible fixes."""
    h = np.zeros(n, bool)
    pos = int(rng.integers(gap[0], gap[1] + 1))
    while pos < n:
        L = int(rng.integers(run[0], run[1] + 1))
        h[pos:pos + L] = True
        pos += L + int(rng.integers(gap[0], gap[1] + 1))
    return h


def hide_windows(t_s: np.ndarray, rng: np.random.Generator, win_s=WIN_S, frac=WIN_FRAC) -> np.ndarray:
    """(a'): all fixes in a random `frac` of the 2-s windows (t_s = seconds from the night start)."""
    k = np.maximum(np.floor(t_s / win_s).astype(np.int64), 0)
    nw = int(k.max()) + 1 if len(k) else 0
    sel = rng.random(nw) < frac
    return sel[k]


def anchor_sigma_table(dev: pd.DataFrame) -> dict:
    """Per-axis robust SD (1.4826 MAD) and plain SD of deviations about the bout median, per anchors_used (<= 3 pooled)."""
    out = {}
    a = dev["anchors_used"].clip(upper=9).where(dev["anchors_used"] > 3, 3).astype(int)
    for k in range(3, 10):
        d = dev[a == k]
        row = {"n": int(len(d))}
        for ax in ("dx", "dy"):
            v = d[ax].to_numpy(float)
            if len(v) >= 20:
                row[f"rsd_{ax[1]}"] = float(1.4826 * np.median(np.abs(v - np.median(v))))
                row[f"sd_{ax[1]}"] = float(np.std(v))
            else:
                row[f"rsd_{ax[1]}"] = row[f"sd_{ax[1]}"] = np.nan
        out[k] = row
    # fill sparse strata from the next-lower anchor count (noisier) -> conservative
    for k in range(9, 2, -1):
        for key in ("rsd_x", "rsd_y", "sd_x", "sd_y"):
            if not np.isfinite(out[k][key]):
                nxt = [out[j][key] for j in range(k - 1, 2, -1) if np.isfinite(out[j][key])]
                out[k][key] = nxt[0] if nxt else 50.0
    return out


def r2_from_anchors(A: np.ndarray, table: dict) -> np.ndarray:
    a = np.clip(np.asarray(A, float), 3, 9).astype(int)
    sx = np.array([table[k]["rsd_x"] for k in range(3, 10)])
    sy = np.array([table[k]["rsd_y"] for k in range(3, 10)])
    return np.column_stack([sx[a - 3] ** 2, sy[a - 3] ** 2])


# ================================================================ statistics
def boot_delta(e_m: np.ndarray, e_ref: np.ndarray, blocks: np.ndarray, strata: np.ndarray, rng: np.random.Generator,
               n_boot: int = N_BOOT, chunk: int = 100) -> dict:
    """Paired block bootstrap of the relative median improvement D = 1 - med(e_m)/med(e_ref) (+ = method better) and of
    the RMSE improvement. blocks: block id per fix; strata: stratum (animal) id per fix; blocks are resampled with
    replacement within each stratum, the same draw for both methods."""
    e_m, e_ref = np.asarray(e_m, float), np.asarray(e_ref, float)
    n = len(e_m)
    if n < 20:
        return {"n": int(n), "d_med": np.nan, "lo": np.nan, "hi": np.nan, "d_rmse": np.nan, "rmse_lo": np.nan,
                "rmse_hi": np.nan, "med_m": np.nan, "med_ref": np.nan, "rmse_m": np.nan, "rmse_ref": np.nan}
    _, scode = np.unique(np.asarray(strata), return_inverse=True)
    key = scode.astype(np.int64) * 10_000_000 + (np.asarray(blocks, np.int64) + 1_000)
    ub, binv = np.unique(key, return_inverse=True)
    bstr = ub // 10_000_000
    K = len(ub)
    counts = np.zeros((n_boot, K))
    for s in np.unique(bstr):
        idx = np.flatnonzero(bstr == s)
        dr = rng.integers(0, len(idx), size=(n_boot, len(idx)))
        flat = (dr + np.arange(n_boot)[:, None] * len(idx)).ravel()
        counts[:, idx] += np.bincount(flat, minlength=n_boot * len(idx)).reshape(n_boot, len(idx))

    def wmed(e):
        o = np.argsort(e, kind="stable")
        es, bs = e[o], binv[o]
        out = np.empty(n_boot)
        for c0 in range(0, n_boot, chunk):
            W = counts[c0:c0 + chunk][:, bs]
            cw = np.cumsum(W, axis=1)
            half = cw[:, -1] / 2.0
            j = (cw < half[:, None]).sum(axis=1)
            out[c0:c0 + chunk] = es[np.minimum(j, n - 1)]
        return out

    mm, mr = wmed(e_m), wmed(e_ref)
    d = 1.0 - mm / mr
    bs2m = np.bincount(binv, e_m ** 2, K)
    bs2r = np.bincount(binv, e_ref ** 2, K)
    bc = np.bincount(binv, minlength=K).astype(float)
    rm = np.sqrt(counts @ bs2m / (counts @ bc))
    rr = np.sqrt(counts @ bs2r / (counts @ bc))
    dr_ = 1.0 - rm / rr
    med_m, med_r = float(np.median(e_m)), float(np.median(e_ref))
    rmse_m, rmse_r = float(np.sqrt(np.mean(e_m ** 2))), float(np.sqrt(np.mean(e_ref ** 2)))
    return {"n": int(n), "med_m": med_m, "med_ref": med_r, "d_med": 1.0 - med_m / med_r,
            "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
            "rmse_m": rmse_m, "rmse_ref": rmse_r, "d_rmse": 1.0 - rmse_m / rmse_r,
            "rmse_lo": float(np.percentile(dr_, 2.5)), "rmse_hi": float(np.percentile(dr_, 97.5))}


def spearman_theil(x: np.ndarray, y: np.ndarray) -> dict:
    from scipy import stats
    if len(x) < 10:
        return {"n": int(len(x)), "rho": np.nan, "p": np.nan, "slope_w_on_i": np.nan, "slope_i_on_w": np.nan}
    rho, p = stats.spearmanr(x, y)
    return {"n": int(len(x)), "rho": float(rho), "p": float(p),
            "slope_w_on_i": float(stats.theilslopes(y, x)[0]), "slope_i_on_w": float(stats.theilslopes(x, y)[0])}


# ================================================================ IMU per-second states
def stride_band_fraction(unix_ms: np.ndarray, acc_up: np.ndarray, secs: np.ndarray) -> np.ndarray:
    """SBF(s) = P[4-7 Hz] / P[1-20 Hz] of the vertical earth-frame linear acceleration over the 2-s Hann window
    [s - 0.5, s + 1.5) (100 samples at 50 Hz); NaN when the window is incomplete, gapped or has NaN."""
    nwin = int(2 * FS_IMU)
    i0 = np.searchsorted(unix_ms, (secs - 0.5) * 1000.0)
    idx = i0[:, None] + np.arange(nwin)[None, :]
    ok = idx[:, -1] < len(unix_ms)
    idxc = np.clip(idx, 0, len(unix_ms) - 1)
    seg = acc_up[idxc]
    tt = unix_ms[idxc]
    span = tt[:, -1] - tt[:, 0]
    ok &= np.abs(span - (nwin - 1) * 1000.0 / FS_IMU) < 30.0
    ok &= np.all(np.isfinite(seg), axis=1)
    seg = np.where(np.isfinite(seg), seg, 0.0)
    seg = seg - seg.mean(axis=1, keepdims=True)
    pw = np.abs(np.fft.rfft(seg * np.hanning(nwin)[None, :], axis=1)) ** 2
    f = np.fft.rfftfreq(nwin, 1.0 / FS_IMU)
    band = pw[:, (f >= 4.0) & (f <= 7.0)].sum(axis=1)
    tot = pw[:, (f >= 1.0) & (f <= 20.0)].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = band / tot
    out[~ok] = np.nan
    return out


def load_imu_seconds(npz: Path, start_local: str, lo: float, hi: float, handling, silences, adc, vf: float, vu: float,
                     thr: float) -> pd.DataFrame:
    """Per field-PC second in [lo, hi): the previous pilot's QC mask and still rule, plus the ADC-lane mask and SBF."""
    imu = C.load_imu_npz(npz, start_local, lo - 5_000, hi + 5_000)
    base = C.to_ms(start_local[:10] + " 00:00:00")
    with np.load(npz) as zz:
        u = base + zz["t_pc_ms"].astype(np.float64)
        sel = (u >= lo - 5_000) & (u < hi + 5_000)
        acc_up = zz["lin_acc_earth_ms2"][sel, 2].astype(np.float64)
    frm, _ = C.frozen_rule(imu["omega_dps"], imu["vedba_ms2"])
    ps = C.per_second(imu, lo, hi, handling, silences, vf, vu, frm)
    t_mid = (ps["sec"].to_numpy() + 0.5) * 1000.0
    ps["m_adc"] = C.in_any(t_mid, adc)
    ps["ok"] = ps["ok"] & ~ps["m_adc"]
    ps["still"] = C.still_mask(ps, thr)
    ps["sbf"] = stride_band_fraction(imu["unix_ms"], acc_up, ps["sec"].to_numpy().astype(float))
    # integrated turn per second (for the V3 diagnostic): sum turn_dps * dt over samples in the second
    u_in, tr = imu["unix_ms"], np.where(np.isfinite(imu["turn_dps"]), imu["turn_dps"], 0.0)
    dt = np.clip(np.r_[np.diff(u_in), 1000.0 / FS_IMU] / 1000.0, 0, 2.0 / FS_IMU)
    cum = np.r_[0.0, np.cumsum(tr * dt)]
    ps["_cum_turn_at_start"] = cum[np.searchsorted(u_in, ps["sec"].to_numpy() * 1000.0)]
    return ps


def imu_state(ps: pd.DataFrame, theta_l: float, rho_l: float) -> np.ndarray:
    """0 = IMU not usable, 1 = still, 2 = active (not locomoting), 3 = locomoting."""
    ok = ps["ok"].to_numpy(bool)
    st = np.where(ok, 2, 0).astype(np.int8)
    loco = ok & ~ps["still"].to_numpy(bool) & (ps["vedba_1s"].to_numpy() >= theta_l) & (np.nan_to_num(ps["sbf"].to_numpy(), nan=-1) >= rho_l)
    st[loco] = 3
    st[ok & ps["still"].to_numpy(bool)] = 1
    return st


def step_states(t_al_ms: np.ndarray, secs: np.ndarray, st_sec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per fix step: IMU state of the interval midpoint (process noise) and at the fix time (ZUPT)."""
    s0 = int(secs[0])
    look = lambda tm: np.where((np.floor(tm / 1000).astype(np.int64) - s0 >= 0) & (np.floor(tm / 1000).astype(np.int64) - s0 < len(st_sec)),  # noqa: E731
                               st_sec[np.clip(np.floor(tm / 1000).astype(np.int64) - s0, 0, len(st_sec) - 1)], 0).astype(np.int8)
    at = look(t_al_ms)
    mid = np.r_[at[:1], look(0.5 * (t_al_ms[1:] + t_al_ms[:-1]))]
    return mid, at


# ================================================================ track plausibility (c)
def track_metrics(t_s: np.ndarray, p: np.ndarray, walls: dict | None, still_sec: set | None, s0_unix: float) -> dict:
    """Method-agnostic plausibility of a position track sampled at fix times: resample on a 0.25-s grid (linear, only
    inside inter-fix gaps <= 1 s), v(t) = |p(t+0.5)-p(t-0.5)| / 1 s, a(t) = |p(t+0.5) - 2p(t) + p(t-0.5)| / 0.25 s^2, path
    length on the 1-s grid, wall excursions > 15 in outside the regime-B ridge rectangle (at fix times)."""
    g = np.arange(np.ceil(t_s[0] * 4) / 4, t_s[-1], 0.25)
    j = np.searchsorted(t_s, g)
    okg = (j > 0) & (j < len(t_s))
    jj = np.clip(j, 1, len(t_s) - 1)
    okg &= (t_s[jj] - t_s[jj - 1]) <= 1.0
    pg = np.column_stack([np.interp(g, t_s, p[:, a]) for a in range(2)])
    pg[~okg] = np.nan
    v = np.full(len(g), np.nan)
    acc = np.full(len(g), np.nan)
    v[2:-2] = np.hypot(*(pg[4:] - pg[:-4]).T) / 1.0
    acc[2:-2] = np.hypot(*(pg[4:] - 2 * pg[2:-2] + pg[:-4]).T) / 0.25
    one = pg[::4]
    stepl = np.hypot(*(np.diff(one, axis=0)).T)
    hours = (t_s[-1] - t_s[0]) / 3600.0
    out = {"v_p50": float(np.nanpercentile(v, 50)), "v_p95": float(np.nanpercentile(v, 95)),
           "v_p99": float(np.nanpercentile(v, 99)), "v_frac_gt60": float(np.nanmean(v > 60)),
           "a_p50": float(np.nanpercentile(acc, 50)), "a_p99": float(np.nanpercentile(acc, 99)),
           "a_frac_gt400": float(np.nanmean(acc > 400)), "path_in_per_h": float(np.nansum(stepl) / hours)}
    if walls is not None:
        d = C_dist_to_ridge_rect(p[:, 0], p[:, 1], walls)
        out["wall_out_frac"] = float(np.mean(d < -WALL_OUT_IN))
    if still_sec is not None:
        gs = np.floor(g + s0_unix).astype(np.int64)
        m = np.isin(gs, np.fromiter(still_sec, np.int64)) & np.isfinite(v)
        out["v_still_p50"] = float(np.nanpercentile(v[m], 50)) if m.any() else np.nan
        out["v_still_p95"] = float(np.nanpercentile(v[m], 95)) if m.any() else np.nan
    return out


def C_dist_to_ridge_rect(x, y, walls):
    """Signed distance (in) to the regime-B wall-ridge rectangle, + inside (as common_c3.dist_to_ridge_rect of the accuracy
    run; lines y = a + b x for bottom/top, x = a + b y for left/right)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    db = y - (walls["bottom"]["a"] + walls["bottom"]["b"] * x)
    dt = (walls["top"]["a"] + walls["top"]["b"] * x) - y
    dl = x - (walls["left"]["a"] + walls["left"]["b"] * y)
    dr = (walls["right"]["a"] + walls["right"]["b"] * y) - x
    return np.minimum.reduce([db, dt, dl, dr])


# ================================================================ one track = one animal on one night
class Track:
    """Deduplicated fixes of one tag in one night window + the IMU states on the aligned clock."""

    def __init__(self, fx: pd.DataFrame, lo: float, hi: float, tau_s: float):
        f = fx[(fx.t_ms >= lo) & (fx.t_ms < hi)].sort_values("t_ms").reset_index(drop=True)
        self.fx = f
        self.lo, self.hi, self.tau = lo, hi, tau_s
        self.t_al_ms = f["t_ms"].to_numpy(float) - tau_s * 1000.0
        self.t = (self.t_al_ms - lo) / 1000.0                      # s from the night start (aligned)
        self.z = f[["x", "y"]].to_numpy(float)
        self.A = f["anchors_used"].to_numpy(float)
        self.sec = np.floor(self.t_al_ms / 1000.0).astype(np.int64)
        self.block = np.maximum(np.floor((self.t_al_ms - lo) / (BLOCK_S * 1000.0)).astype(np.int64), 0)
        self.n = len(f)

    def attach_imu(self, ps: pd.DataFrame, ps_shift: pd.DataFrame | None, theta_l: float, rho_l: float):
        self.ps = ps
        secs = ps["sec"].to_numpy()
        self.st_sec = imu_state(ps, theta_l, rho_l)
        self.st_mid, self.st_at = step_states(self.t_al_ms, secs, self.st_sec)
        okmap = pd.Series(ps["ok"].to_numpy(bool), index=secs)
        stillmap = pd.Series(ps["still"].to_numpy(bool), index=secs)
        self.ok_true = okmap.reindex(self.sec).fillna(False).to_numpy(bool)
        self.still = stillmap.reindex(self.sec).fillna(False).to_numpy(bool) & self.ok_true
        if ps_shift is not None:
            self.st_sec_shift = imu_state(ps_shift, theta_l, rho_l)
            secs_s = ps_shift["sec"].to_numpy() - 3600
            self.st_mid_shift, self.st_at_shift = step_states(self.t_al_ms, secs_s, self.st_sec_shift)
            oks = pd.Series(ps_shift["ok"].to_numpy(bool), index=secs_s)
            self.ok_shift = oks.reindex(self.sec).fillna(False).to_numpy(bool)
        else:
            self.st_mid_shift, self.st_at_shift = self.st_mid, self.st_at
            self.ok_shift = self.ok_true
        self.ok_both = self.ok_true & self.ok_shift
        self.moving = self.ok_true & ~self.still
        self.loco = np.isin(self.st_at, [3]) & self.ok_true


def make_hidden(tr: Track, seed: int) -> dict:
    return {"a": hide_runs(tr.n, np.random.default_rng(seed)),
            "a2": hide_windows(tr.t, np.random.default_rng(seed + 50))}


def scored_mask(tr: Track, hid: np.ndarray) -> np.ndarray:
    return hid & (tr.A >= MIN_ANCHORS_SCORE) & tr.ok_both


def predict_all(tr: Track, table: dict, tuned: dict, hidden: dict, methods=("B1", "B2", "B2p", "V1", "V2", "V1_shift", "V2_shift"),
                extra: list | None = None) -> dict:
    """Held-out predictions z_hat (n, 2) for every method and hidden scheme ('a', 'a2'); NaN where not hidden."""
    r2 = r2_from_anchors(tr.A, table)
    schemes = list(hidden)
    vis_list = [~hidden[s] for s in schemes]
    stm = [tr.st_mid, tr.st_mid_shift]
    sta = [tr.st_at, tr.st_at_shift]
    b2, b2p, v1, v2 = tuned["B2"], tuned["B2p"], tuned["V1"], tuned["V2"]
    base_p = {"q": b2p["q"], "tb": b2p["tb"], "sb": b2p["sb"], "mrej": b2["mrej"]}
    cfgs, keys = [], []
    for si, s in enumerate(schemes):
        spec = {"B2": {"q": b2["q"], "mrej": b2["mrej"]}, "B2p": dict(base_p),
                "V1": {**base_p, "sv": v1["sv"]}, "V2": {**base_p, "mult": tuple(v2["mult"])},
                "V1_shift": {**base_p, "sv": v1["sv"], "src": 1}, "V2_shift": {**base_p, "mult": tuple(v2["mult"]), "src": 1}}
        for m in methods:
            if m in spec:
                cfgs.append({**spec[m], "vis": si})
                keys.append((m, s))
        for name, c in (extra or []):
            cfgs.append({**c, "vis": si})
            keys.append((name, s))
    P, B, V = kf_run(tr.t, tr.z, r2, vis_list, stm, sta, cfgs)
    out = {}
    for i, (m, s) in enumerate(keys):
        zh = P[i] + B[i]
        out[(m, s)] = np.where(hidden[s][:, None], zh, np.nan)
        if m == "B2p":
            out[("B2p_p", s)] = np.where(hidden[s][:, None], P[i], np.nan)
    if "B1" in methods:
        for s in schemes:
            h = hidden[s]
            zh = np.full((tr.n, 2), np.nan)
            zh[h] = b1_predict(tr.t[~h], tr.z[~h], tr.t[h])
            out[("B1", s)] = zh
    return out


# ================================================================ tuning (tuning night only)
def tune(tracks: dict, table: dict, hidden: dict, log) -> tuple[dict, dict]:
    """Grid searches on scheme (a) of the tuning night; objective = pooled median error on scored fixes (tie: RMSE)."""
    animals = list(tracks)
    curves = {}

    def evaluate(cfg_list):
        errs = [[] for _ in cfg_list]
        for a in animals:
            tr = tracks[a]
            r2 = r2_from_anchors(tr.A, table)
            h = hidden[a]["a"]
            sc = scored_mask(tr, h)
            P, B, _ = kf_run(tr.t, tr.z, r2, [~h], [tr.st_mid, tr.st_mid_shift], [tr.st_at, tr.st_at_shift],
                             [{**c, "vis": 0} for c in cfg_list])
            for i in range(len(cfg_list)):
                errs[i].append(np.hypot(*(tr.z[sc] - (P[i] + B[i])[sc]).T))
        res = []
        for i, c in enumerate(cfg_list):
            e = np.concatenate(errs[i])
            res.append({**{k: (list(v) if isinstance(v, tuple) else v) for k, v in c.items()},
                        "med": float(np.median(e)), "rmse": float(np.sqrt(np.mean(e ** 2))), "n": int(len(e))})
        return res

    def best(res):
        return min(res, key=lambda r: (round(r["med"], 4), r["rmse"]))

    t0 = time.time()
    g_b2 = [{"q": q, "mrej": mr} for q in (1, 3, 10, 30, 100, 300, 1000, 3000) for mr in (5.0, 8.0, 1e9)]
    r_b2 = evaluate(g_b2)
    curves["B2"] = r_b2
    bb2 = best(r_b2)
    log(f"tune B2: q {bb2['q']} mrej {bb2['mrej']} -> med {bb2['med']:.3f} rmse {bb2['rmse']:.3f} ({time.time() - t0:.0f} s)")
    q0, mrej = bb2["q"], bb2["mrej"]
    g_b2p = [{"q": q, "tb": tb, "sb": sb, "mrej": mrej} for q in (q0 / 3, q0, q0 * 3) for tb in (5, 15, 30, 60, 120)
             for sb in (0.5, 1.0, 1.5, 2.5)]
    r_b2p = evaluate(g_b2p)
    curves["B2p"] = r_b2p
    bb2p = best(r_b2p)
    log(f"tune B2': q {bb2p['q']:.3g} tb {bb2p['tb']} sb {bb2p['sb']} -> med {bb2p['med']:.3f} ({time.time() - t0:.0f} s)")
    base = {"q": bb2p["q"], "tb": bb2p["tb"], "sb": bb2p["sb"], "mrej": mrej}
    r_v1 = evaluate([{**base, "sv": sv} for sv in (0.25, 0.5, 1.0, 2.0, 4.0)])
    curves["V1"] = r_v1
    bv1 = best(r_v1)
    log(f"tune V1: sv {bv1['sv']} -> med {bv1['med']:.3f} ({time.time() - t0:.0f} s)")
    g_v2 = [{**base, "mult": (1.0, ms, ma, ml)} for ms in (0.01, 0.03, 0.1, 0.3, 1.0) for ma in (0.3, 1.0, 3.0)
            for ml in (1.0, 3.0, 10.0)]
    r_v2 = evaluate(g_v2)
    curves["V2"] = r_v2
    bv2 = best(r_v2)
    log(f"tune V2: mult {bv2['mult']} -> med {bv2['med']:.3f} ({time.time() - t0:.0f} s)")
    tuned = {"B2": {"q": q0, "mrej": mrej, "med": bb2["med"]},
             "B2p": {"q": bb2p["q"], "tb": bb2p["tb"], "sb": bb2p["sb"], "med": bb2p["med"]},
             "V1": {"sv": bv1["sv"], "med": bv1["med"]}, "V2": {"mult": list(bv2["mult"]), "med": bv2["med"]}}
    return tuned, curves


def tune_extended(tracks: dict, table: dict, hidden: dict, tuned: dict, log) -> dict:
    """POST HOC (added after the first run, 2026-09-29, because several tuned values sat on a grid edge): a wider grid on
    the TUNING night only, to ask whether a wider pre-registered grid could have promised a >= 3 % IMU gain. Nothing here
    is evaluated on the test night and no verdict uses it."""
    animals = list(tracks)

    def evaluate(cfg_list):
        errs = [[] for _ in cfg_list]
        for a in animals:
            tr = tracks[a]
            r2 = r2_from_anchors(tr.A, table)
            h = hidden[a]["a"]
            sc = scored_mask(tr, h)
            P, B, _ = kf_run(tr.t, tr.z, r2, [~h], [tr.st_mid, tr.st_mid_shift], [tr.st_at, tr.st_at_shift],
                             [{**c, "vis": 0} for c in cfg_list])
            for i in range(len(cfg_list)):
                errs[i].append(np.hypot(*(tr.z[sc] - (P[i] + B[i])[sc]).T))
        return [{**{k: (list(v) if isinstance(v, tuple) else v) for k, v in c.items()},
                 "med": float(np.median(np.concatenate(e))), "rmse": float(np.sqrt(np.mean(np.concatenate(e) ** 2)))}
                for c, e in zip(cfg_list, errs)]

    def best(r):
        return min(r, key=lambda row: (round(row["med"], 4), row["rmse"]))

    mrej = tuned["B2"]["mrej"]
    r_b2 = evaluate([{"q": q, "mrej": mrej} for q in (0.1, 0.3, 1.0, 3.0)])
    r_b2p = evaluate([{"q": q, "tb": tb, "sb": sb, "mrej": mrej} for q in (0.1, 0.3, 1.0) for tb in (15, 30, 60)
                      for sb in (2.5, 4.0, 6.0)])
    bp = best(r_b2p)
    base = {"q": bp["q"], "tb": bp["tb"], "sb": bp["sb"], "mrej": mrej}
    r_v1 = evaluate([{**base, "sv": sv} for sv in (0.03, 0.1, 0.25)])
    r_v2 = evaluate([{**base, "mult": (1.0, ms, ma, ml)} for ms in (0.001, 0.003, 0.01) for ma in (0.1, 0.3, 1.0)
                     for ml in (10.0, 30.0, 100.0)])
    out = {"B2": best(r_b2), "B2p": bp, "V1": best(r_v1), "V2": best(r_v2),
           "curves": {"B2": r_b2, "B2p": r_b2p, "V1": r_v1, "V2": r_v2}}
    for k in ("V1", "V2"):
        out[f"{k}_gain_vs_B2p"] = 1.0 - out[k]["med"] / bp["med"]
    log(f"post hoc extended grid (tuning night only): B2 q {out['B2']['q']} med {out['B2']['med']:.3f}; B2' {bp['q']}/{bp['tb']}/{bp['sb']} "
        f"med {bp['med']:.3f}; V1 sv {out['V1']['sv']} gain {100 * out['V1_gain_vs_B2p']:+.2f} %; V2 {out['V2']['mult']} gain "
        f"{100 * out['V2_gain_vs_B2p']:+.2f} %")
    return out


def fit_loco_thresholds(tracks: dict) -> dict:
    """(theta_L, rho_L) maximising Youden's J of 'IMU locomoting' vs WISER 1-s median speed >= 10 in/s (negatives:
    < 3 in/s), over IMU-QC-ok, non-still seconds of the tuning night (pooled animals)."""
    V, S, Y = [], [], []
    for tr in tracks.values():
        ps = tr.ps
        f = tr.fx[tr.fx["valid"]]
        s = np.floor((f["t_ms"].to_numpy(float) - tr.tau * 1000.0) / 1000.0).astype(np.int64)
        sp = pd.Series(f["speed_inps_smooth"].to_numpy(float)).groupby(s).median()
        v1 = sp.reindex(ps["sec"].to_numpy()).to_numpy()
        m = ps["ok"].to_numpy(bool) & ~ps["still"].to_numpy(bool) & np.isfinite(v1)
        lab = np.where(v1 >= SPEED_LOCO_INPS, 1, np.where(v1 < SPEED_STILL_INPS, 0, -1))
        m &= lab >= 0
        V.append(ps["vedba_1s"].to_numpy()[m])
        S.append(np.nan_to_num(ps["sbf"].to_numpy()[m], nan=-1))
        Y.append(lab[m])
    V, S, Y = np.concatenate(V), np.concatenate(S), np.concatenate(Y)
    best = None
    for th in np.quantile(V, np.linspace(0.05, 0.95, 37)):
        for rl in (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5):
            pred = (V >= th) & (S >= rl)
            tpr = float(pred[Y == 1].mean())
            fpr = float(pred[Y == 0].mean())
            if best is None or tpr - fpr > best["J"]:
                best = {"theta_l": float(th), "rho_l": float(rl), "J": tpr - fpr, "tpr": tpr, "fpr": fpr}
    best.update({"n_pos": int((Y == 1).sum()), "n_neg": int((Y == 0).sum())})
    return best


def v3_diagnostic(tr: Track) -> pd.DataFrame:
    """Locomotion windows (>= 3 s of WISER 1-s speed >= 10 in/s with the IMU QC-ok and not still): turn between successive
    1-s-median displacements (WISER) vs the integrated IMU turn over the same second (WISER shifted by tau*)."""
    ps = tr.ps
    secs = ps["sec"].to_numpy()
    med = C.wiser_1s_medians(tr.fx, tr.tau, secs)
    f = tr.fx[tr.fx["valid"]]
    s = np.floor((f["t_ms"].to_numpy(float) - tr.tau * 1000.0) / 1000.0).astype(np.int64)
    v1 = pd.Series(f["speed_inps_smooth"].to_numpy(float)).groupby(s).median().reindex(secs).to_numpy()
    cond = ps["ok"].to_numpy(bool) & ~ps["still"].to_numpy(bool) & (np.nan_to_num(v1) >= SPEED_LOCO_INPS) & (med["n"].fillna(0).to_numpy() >= 2)
    mx, my = med["x"].to_numpy(float), med["y"].to_numpy(float)
    cum = ps["_cum_turn_at_start"].to_numpy(float)
    rows = []
    for a, b in C.true_runs(cond):
        if b - a < 3:
            continue
        for s0 in range(a + 1, b - 1):
            d1 = np.array([mx[s0] - mx[s0 - 1], my[s0] - my[s0 - 1]])
            d2 = np.array([mx[s0 + 1] - mx[s0], my[s0 + 1] - my[s0]])
            dpw = math.degrees(math.atan2(d1[0] * d2[1] - d1[1] * d2[0], float(d1 @ d2)))
            # d1 is centred at the boundary s0 (between medians of seconds s0-1 and s0), d2 at s0+1
            if s0 + 1 >= len(cum):
                continue
            dpi = float(cum[s0 + 1] - cum[s0])
            rows.append({"sec": int(secs[s0]), "dpsi_w_deg": dpw, "dpsi_i_deg": dpi,
                         "step1_in": float(np.hypot(*d1)), "step2_in": float(np.hypot(*d2))})
    return pd.DataFrame(rows)


# ================================================================ evaluation
def score_night(tracks: dict, preds: dict, rng: np.random.Generator, animals: list) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Per fix errors (long table) and bootstrap comparisons. preds[a][(method, scheme)] = z_hat."""
    rows = []
    for ai, a in enumerate(animals):
        tr = tracks[a]
        for (m, s), zh in preds[a].items():
            sc = scored_mask(tr, ~np.isnan(zh[:, 0]))
            e = np.hypot(*(tr.z[sc] - zh[sc]).T)
            rows.append(pd.DataFrame({"animal": a, "method": m, "scheme": s, "i": np.flatnonzero(sc), "e": e,
                                      "still": tr.still[sc], "moving": tr.moving[sc], "loco": tr.loco[sc],
                                      "block": tr.block[sc], "anchors": tr.A[sc]}))
    err = pd.concat(rows, ignore_index=True)
    comps = []
    pairs = [(m, "B2p") for m in ("B1", "B2", "V1", "V2", "V1_shift", "V2_shift", "B2p_p")] + [("B2", "B1"), ("B2p", "B1")]
    summ = {}
    for s in ("a", "a2"):
        for sub in ("all", "still", "moving", "loco"):
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
                    assert np.array_equal(em["i"].to_numpy(), er["i"].to_numpy()), "unpaired errors"
                    r = boot_delta(em["e"].to_numpy(), er["e"].to_numpy(), em["block"].to_numpy(),
                                   em["animal"].to_numpy(), rng)
                    comps.append({"scheme": s, "subset": sub, "method": m, "ref": ref, "animal": who, **r})
    comp = pd.DataFrame(comps)
    for s in ("a", "a2"):
        for m in ("B1", "B2", "B2p", "V1", "V2", "V1_shift", "V2_shift", "B2p_p"):
            d = err[(err.method == m) & (err.scheme == s)]
            summ[(m, s)] = {w_: {"med": float(np.median(g.e)), "rmse": float(np.sqrt(np.mean(g.e ** 2))), "n": int(len(g))}
                            for w_, g in list(d.groupby("animal")) + [("pooled", d)]} if len(d) else {}
    return err, comp, summ


def verdicts(comp: pd.DataFrame, animals: list) -> dict:
    out = {}
    for v in ("V1", "V2"):
        per = {}
        for s in ("a", "a2"):
            c = comp[(comp.scheme == s) & (comp.subset == "all") & (comp.ref == "B2p")]
            main = c[(c.method == v) & c.animal.isin(animals)]
            ctrl = c[(c.method == f"{v}_shift") & c.animal.isin(animals)]
            n_pass = int(((main.d_med >= ACCEPT["min_gain"]) & (main.lo > 0)).sum())
            n_ctrl_ok = int((ctrl.lo <= 0).sum())
            mv = comp[(comp.scheme == s) & (comp.subset == "moving") & (comp.method == v) & (comp.ref == "B2p") & (comp.animal == "pooled")]
            d_mov = float(mv.d_med.iloc[0]) if len(mv) else np.nan
            ctrl_ok = n_ctrl_ok >= ACCEPT["min_animals"]
            mov_ok = bool(np.isfinite(d_mov) and d_mov >= ACCEPT["moving_max_loss"])
            if n_pass >= ACCEPT["min_animals"] and ctrl_ok and mov_ok:
                ver = "ACCEPTED"
            elif n_pass == ACCEPT["min_animals"] - 1 or (n_pass >= ACCEPT["min_animals"] and not ctrl_ok):
                ver = "INCONCLUSIVE"
            else:
                ver = "FAIL"
            per[s] = {"n_animals_gain": n_pass, "n_control_no_gain": n_ctrl_ok, "pooled_moving_d": d_mov,
                      "control_ok": ctrl_ok, "moving_ok": mov_ok, "verdict": ver}
        rank = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "FAIL": 0}
        out[v] = {"schemes": per, "verdict": max((p["verdict"] for p in per.values()), key=lambda x: rank[x])}
    return out


# ================================================================ static references (b)
def static_reference(fx: pd.DataFrame, windows: list, table: dict, tuned: dict) -> list:
    """Position-only B1/B2/B2' on the full fixes of one static tag; scored inside each (label, lo, hi) window against the
    window's raw median position (constant truth)."""
    f = fx.sort_values("t_ms").reset_index(drop=True)
    t = (f["t_ms"].to_numpy(float) - f["t_ms"].iloc[0]) / 1000.0
    z = f[["x", "y"]].to_numpy(float)
    r2 = r2_from_anchors(f["anchors_used"].to_numpy(float), table)
    vis = np.ones(len(f), bool)
    zero = np.zeros(len(f), np.int8)
    b2, b2p = tuned["B2"], tuned["B2p"]
    P, B, V = kf_run(t, z, r2, [vis], [zero], [zero],
                     [{"q": b2["q"], "mrej": b2["mrej"]}, {"q": b2p["q"], "tb": b2p["tb"], "sb": b2p["sb"], "mrej": b2["mrej"]}])
    tracks = {"raw": z, "B1": b1_full(z), "B2": P[0], "B2p_p": P[1], "B2p": P[1] + B[1]}
    rows = []
    tm = f["t_ms"].to_numpy(float)
    for lab, lo, hi in windows:
        m = (tm >= lo) & (tm < hi)
        truth = np.median(z[m], axis=0)
        for k, p in tracks.items():
            d = p[m] - truth
            r = np.hypot(d[:, 0], d[:, 1])
            rows.append({"window": lab, "method": k, "n": int(m.sum()), "bias_in": float(np.hypot(*d.mean(axis=0))),
                         "rmse_in": float(np.sqrt(np.mean(r ** 2))), "p50_in": float(np.median(r)),
                         "p90_in": float(np.percentile(r, 90)), "sd_x": float(np.std(p[m, 0])), "sd_y": float(np.std(p[m, 1]))})
    return rows


# ================================================================ WISER I/O
def query_fixes(db: Path, table: str, tags: list, lo: float, hi: float) -> tuple[pd.DataFrame, dict]:
    con = wiser_io._connect_readonly(Path(db))
    try:
        ph = ",".join("?" * len(tags))
        df = pd.read_sql(f'SELECT reportid, shortid, timestamp, location_x, location_y, anchors_used FROM "{table}" '
                         f'WHERE timestamp >= ? AND timestamp < ? AND shortid IN ({ph})', con,
                         params=[int(lo), int(hi), *[int(t) for t in tags]])
    finally:
        con.close()
    df, st = dedup_fixes(df)
    df = df.rename(columns={"timestamp": "ts_raw", "location_x": "x", "location_y": "y"})
    return (C.prepare_fixes(df) if len(df) else df), st


# ================================================================ selftest
def synth_track(seed: int, dur_s: float = 5400.0, drift_sd: float = 1.0, drift_tau: float = 30.0):
    """Synthetic head track: alternating still (40-150 s) and moving (20-60 s, OU velocity ~15 in/s) segments; bimodal
    0.13/0.26-s fix intervals; anchors 5..9; white noise by anchors; AR(1) drift; 0.5 % clustered outliers."""
    rng = np.random.default_rng(seed)
    dt_f = rng.choice([0.134, 0.268], size=int(dur_s / 0.18) + 10, p=[0.45, 0.55]) + rng.normal(0, 0.003, int(dur_s / 0.18) + 10)
    t = np.cumsum(dt_f)
    t = t[t < dur_s]
    n = len(t)
    # truth on a 0.02-s grid
    g = np.arange(0, dur_s + 1, 0.02)
    still = np.zeros(len(g), bool)
    pos = 0.0
    while pos < dur_s + 1:
        Ls = rng.uniform(40, 150)
        still[(g >= pos) & (g < pos + Ls)] = True
        pos += Ls + rng.uniform(20, 60)
    vel = np.zeros((len(g), 2))
    vv = np.zeros(2)
    for k in range(1, len(g)):
        if still[k]:
            vv = np.zeros(2)
        else:
            vv = vv + (-vv / 1.5) * 0.02 + rng.normal(0, 15 * math.sqrt(2 * 0.02 / 1.5), 2)
        vel[k] = vv
    p_true_g = 300 + np.cumsum(vel, axis=0) * 0.02
    p_true = np.column_stack([np.interp(t, g, p_true_g[:, a]) for a in range(2)])
    A = rng.choice([5, 6, 7, 8, 9], size=n, p=[0.02, 0.05, 0.08, 0.2, 0.65])
    sig = {5: (8.0, 6.0), 6: (5.0, 4.5), 7: (2.8, 4.0), 8: (2.0, 3.2), 9: (1.5, 2.6)}
    sw = np.array([sig[a] for a in A])
    b = np.zeros((n, 2))
    for k in range(1, n):
        ph = math.exp(-(t[k] - t[k - 1]) / drift_tau)
        b[k] = ph * b[k - 1] + rng.normal(0, drift_sd * math.sqrt(1 - ph * ph), 2)
    w = rng.normal(0, 1, (n, 2)) * sw
    z = p_true + b + w
    out_idx = []
    k = 0
    while k < n:
        if rng.random() < 0.005 / 3:
            L = int(rng.integers(1, 6))
            off = rng.normal(0, 40, 2)
            z[k:k + L] += off
            out_idx.extend(range(k, min(n, k + L)))
            k += L
        k += 1
    still_fix = np.interp(t, g, still.astype(float)) > 0.5
    secs = np.arange(0, int(dur_s) + 1)
    still_sec = np.interp(secs + 0.5, g, still.astype(float)) > 0.5
    return {"t": t, "z": z, "p": p_true, "b": b, "w": w, "A": A, "sw": sw, "still_fix": still_fix, "still_sec": still_sec,
            "secs": secs, "outliers": np.array(out_idx, int)}


def selftest() -> int:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    t0 = time.time()
    # 1) dedup rule
    d = pd.DataFrame({"reportid": [5, 3, 7, 8, 9], "shortid": [1, 1, 1, 1, 2], "timestamp": [10, 10, 10, 11, 10],
                      "location_x": [1.0, 2.0, 3.0, 4.0, 5.0], "location_y": [0.0] * 5, "anchors_used": [8, 9, 9, 7, 6]})
    dd, st = dedup_fixes(d)
    keep = dd[(dd.shortid == 1) & (dd.timestamp == 10)]
    check("dedup keeps max anchors, then min reportid", len(keep) == 1 and int(keep.reportid.iloc[0]) == 3 and st["rows_dropped"] == 2)
    # 2) hidden generators
    h = hide_runs(100_000, np.random.default_rng(1))
    runs = [b - a for a, b in C.true_runs(h)]
    check("(a) hides ~20 % in runs >= 4", 0.18 < h.mean() < 0.22 and min(runs) >= 4, f"frac {h.mean():.3f}, min run {min(runs)}")
    tt = np.cumsum(np.full(50_000, 0.25))
    h2 = hide_windows(tt, np.random.default_rng(2))
    check("(a') hides ~10 % of 2-s windows", 0.08 < h2.mean() < 0.12, f"frac {h2.mean():.3f}")
    # 3) bootstrap sanity
    rng = np.random.default_rng(3)
    e = rng.rayleigh(3, 5000)
    blk = np.repeat(np.arange(50), 100)
    r = boot_delta(e, e, blk, np.zeros(5000, int), rng)
    check("bootstrap: identical methods -> D = 0, CI [0, 0]", abs(r["d_med"]) < 1e-12 and abs(r["lo"]) < 1e-12 and abs(r["hi"]) < 1e-12)
    r = boot_delta(0.9 * e, e, blk, np.zeros(5000, int), rng)
    check("bootstrap: 10 % better -> D = 0.10 inside CI", abs(r["d_med"] - 0.1) < 1e-9 and r["lo"] <= 0.1 <= r["hi"])

    # 4) synthetic tracks: calibration + methods
    syn = [synth_track(s) for s in (11, 12, 13)]
    devs = []
    for s in syn:
        for a_, b_ in C.true_runs(s["still_sec"]):
            if b_ - a_ < 60:
                continue
            m = (s["t"] >= a_ + 1) & (s["t"] < b_ - 1)
            if m.sum() < 30:
                continue
            zz = s["z"][m]
            devs.append(pd.DataFrame({"anchors_used": s["A"][m], "dx": zz[:, 0] - np.median(zz[:, 0]), "dy": zz[:, 1] - np.median(zz[:, 1])}))
    table = anchor_sigma_table(pd.concat(devs))
    exp9 = math.hypot(1.5, 1.0)
    check("anchor-noise calibration recovers white+drift SD at 9 anchors (x)", abs(table[9]["rsd_x"] - exp9) / exp9 < 0.25,
          f"{table[9]['rsd_x']:.2f} vs {exp9:.2f}")
    res = {k: [] for k in ("B1", "B2", "B2p", "V1", "V1s", "orc", "orc_clean", "B2p_st", "V1_st", "V1s_st", "V2", "V2s")}
    orc_expected = []
    blocks, strata = [], []
    for si, s in enumerate(syn):
        n = len(s["t"])
        hid = hide_runs(n, np.random.default_rng(100 + si))
        sc = hid & (s["A"] >= 7)
        st_sec = np.where(s["still_sec"], 1, 3).astype(np.int8)
        sh = np.roll(st_sec, len(st_sec) // 3)                 # 'shifted IMU': decorrelated from the truth
        mid, at = step_states(s["t"] * 1000.0, s["secs"], st_sec)
        mid_s, at_s = step_states(s["t"] * 1000.0, s["secs"], sh)
        r2 = r2_from_anchors(s["A"], table)
        cf = [{"q": 30.0, "mrej": 8.0}, {"q": 30.0, "tb": 30.0, "sb": 1.0, "mrej": 8.0},
              {"q": 30.0, "tb": 30.0, "sb": 1.0, "mrej": 8.0, "sv": 0.5},
              {"q": 30.0, "tb": 30.0, "sb": 1.0, "mrej": 8.0, "sv": 0.5, "src": 1},
              {"q": 30.0, "tb": 30.0, "sb": 1.0, "mrej": 8.0, "mult": (1.0, 0.01, 1.0, 3.0)},
              {"q": 30.0, "tb": 30.0, "sb": 1.0, "mrej": 8.0, "mult": (1.0, 0.01, 1.0, 3.0), "src": 1}]
        P, B, _ = kf_run(s["t"], s["z"], r2, [~hid], [mid, mid_s], [at, at_s], cf)
        zb1 = b1_predict(s["t"][~hid], s["z"][~hid], s["t"][sc])
        e = lambda zh: np.hypot(*(s["z"][sc] - zh).T)  # noqa: E731
        res["B1"].append(e(zb1))
        res["B2"].append(e((P[0] + B[0])[sc]))
        res["B2p"].append(e((P[1] + B[1])[sc]))
        res["V1"].append(e((P[2] + B[2])[sc]))
        res["V1s"].append(e((P[3] + B[3])[sc]))
        res["V2"].append(e((P[4] + B[4])[sc]))
        res["V2s"].append(e((P[5] + B[5])[sc]))
        res["orc"].append(e((s["p"] + s["b"])[sc]))
        clean = np.ones(n, bool)
        clean[s["outliers"]] = False
        res["orc_clean"].append(e((s["p"] + s["b"])[sc])[clean[sc]])
        stf = s["still_fix"][sc]
        res["B2p_st"].append(e((P[1] + B[1])[sc])[stf])
        res["V1_st"].append(e((P[2] + B[2])[sc])[stf])
        res["V1s_st"].append(e((P[3] + B[3])[sc])[stf])
        orc_expected.append(np.sum(s["sw"][sc & clean] ** 2, axis=1))
        blocks.append(np.floor(s["t"][sc] / BLOCK_S).astype(int))
        strata.append(np.full(sc.sum(), si))
    cat = {k: np.concatenate(v) for k, v in res.items()}
    blocks, strata = np.concatenate(blocks), np.concatenate(strata)
    rms_orc = float(np.sqrt(np.mean(cat["orc_clean"] ** 2)))      # outlier fixes excluded: the known noise is the white part
    rms_exp = float(np.sqrt(np.mean(np.concatenate(orc_expected))))
    check("held-out scorer recovers the white noise (oracle RMS = sigma_w)", abs(rms_orc / rms_exp - 1) < 0.05,
          f"{rms_orc:.2f} vs {rms_exp:.2f} in")
    med = {k: float(np.median(v)) for k, v in cat.items()}
    check("B2 beats B1 (median held-out error)", med["B2"] < med["B1"], f"{med['B2']:.2f} vs {med['B1']:.2f}")
    check("every method stays above the oracle floor", min(med[k] for k in ("B1", "B2", "B2p", "V1")) > med["orc"])
    check("V1 beats B2' on IMU-still hidden fixes", med["V1_st"] < med["B2p_st"], f"{med['V1_st']:.2f} vs {med['B2p_st']:.2f}")
    rb = boot_delta(cat["V1s"], cat["B2p"], blocks, strata, np.random.default_rng(5))
    check("+1 h-shifted IMU control shows no gain (CI lower bound <= 0)", rb["lo"] <= 0, f"D {rb['d_med']:+.3f} [{rb['lo']:+.3f}, {rb['hi']:+.3f}]")
    rb2 = boot_delta(cat["V2s"], cat["B2p"], blocks, strata, np.random.default_rng(6))
    check("shifted V2 control shows no gain", rb2["lo"] <= 0, f"D {rb2['d_med']:+.3f} [{rb2['lo']:+.3f}, {rb2['hi']:+.3f}]")
    # 5) static track: smoother RMSE < raw RMSE about the truth
    s = synth_track(21, dur_s=1800.0)
    st_sec = np.ones(len(s["secs"]), np.int8)
    zero = np.zeros(len(s["t"]), np.int8)
    zs = s["z"] - s["p"] + 300.0          # a static tag at (300, 300) with the same noise
    r2 = r2_from_anchors(s["A"], table)
    P, B, _ = kf_run(s["t"], zs, r2, [np.ones(len(s["t"]), bool)], [zero], [zero], [{"q": 30.0, "mrej": 8.0}])
    rmse_raw = float(np.sqrt(np.mean(np.sum((zs - 300.0) ** 2, axis=1))))
    rmse_b2 = float(np.sqrt(np.mean(np.sum((P[0] - 300.0) ** 2, axis=1))))
    check("static tag: B2 track RMSE < raw RMSE", rmse_b2 < rmse_raw, f"{rmse_b2:.2f} vs {rmse_raw:.2f} in")
    print(f"numba: {HAVE_NUMBA}; selftest {time.time() - t0:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ================================================================ driver
def run(cohort: str, imu_root: Path | None, out_root: Path | None, threads: int) -> None:
    t_start = time.time()
    if HAVE_NUMBA:
        import numba
        threads = max(1, min(threads, numba.config.NUMBA_NUM_THREADS))
        set_num_threads(threads)
    coh = load_cohort(cohort)
    cfg_path = REPO / "wiser" / "configs" / f"wiser_imu_smoothing_{cohort}.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    tz = cfg.get("tz", "America/New_York")
    if imu_root is None:
        ar = (coh.get("ephys") or {}).get("analysis_root")
        if not ar:
            raise SystemExit("no ephys.analysis_root in the cohort YAML; pass --imu-root")
        imu_root = Path(ar) / "imu"
    thr = C.imu_still_thr()
    ids = pd.read_csv(REPO / coh["identities"], dtype={"shortid": int, "physical_tag_id": str})
    ids["from_ms"] = pd.to_datetime(ids["valid_from"], utc=True).astype("int64") // 10**6
    ids["until_ms"] = pd.to_datetime(ids["valid_until"], utc=True).astype("int64") // 10**6
    hj = json.loads((REPO / cfg["handling_json"]).read_text(encoding="utf-8"))
    handling = [(C.to_ms(a, tz), C.to_ms(b, tz), note) for a, b, note in hj["windows"]]
    sil = pd.read_csv(cfg["silences_csv"])
    pad = cfg["silence_pad_s"] * 1000
    silences = [(C.to_ms(r.start, tz) - pad, C.to_ms(r.end, tz) + pad, r.kind) for r in sil.itertuples()]
    adc = [(C.to_ms(wd["on_from"], tz), C.to_ms(wd["off_at"], tz), wd["animal"])
           for wd in ((coh.get("ephys") or {}).get("adc_lane") or {}).get("on_windows", [])]
    walls = json.loads(Path(cfg["walls_json"]).read_text(encoding="utf-8"))
    taus = cfg["tau_star_s"]
    out = output_paths.run_dir(NAME, cohort, root=out_root)
    csv_dir = out / "csv"
    csv_dir.mkdir(exist_ok=True)
    logf = open(out / "log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log(f"run dir: {out}; numba {HAVE_NUMBA}, threads {threads}")
    db = Path(cfg["wiser_db"])
    dbi = C.file_info(db)
    if not dbi["sha256"].startswith(cfg["wiser_db_sha256_prefix_expected"]):
        raise SystemExit(f"WISER DB sha256 {dbi['sha256'][:12]} != expected {cfg['wiser_db_sha256_prefix_expected']}")
    prov = {"config": cfg_path.relative_to(REPO).as_posix(), "files": [{"role": "wiser_db", **dbi}], "imu_still_thr": thr}
    log(f"inputs hashed ({time.time() - t_start:.0f} s)")

    def sidecar(a, s):
        return json.loads((imu_root / a / f"{s}.imu.json").read_text(encoding="utf-8"))

    def build_night(key: str) -> tuple[dict, dict, dict]:
        night = cfg["nights"][key]
        lo, hi = C.to_ms(night["start"], tz), C.to_ms(night["end"], tz)
        animals = list(night["sessions"])
        tags = {a: C.resolve_tag(ids, a, lo, hi) for a in animals}
        fx, dst = query_fixes(db, cfg["wiser_table"], list(tags.values()), lo - 60_000, hi + 60_000)
        tracks, info = {}, {"dedup": dst, "tags": tags, "animals": {}}
        for a in animals:
            s = night["sessions"][a]
            npz = imu_root / a / f"{s}.imu.npz"
            sc = sidecar(a, s)
            prov["files"].append({"role": f"{key}_{a}", **C.file_info(npz, hash_it=False)})
            vf, vu = C.tag_window(ids, tags[a], a, (lo + hi) / 2)
            adc_a = [wd for wd in adc if wd[2] == a]          # this logger's ADC-lane on-windows only
            ps = load_imu_seconds(npz, sc["start_local"], lo, hi, handling, silences, adc_a, vf, vu, thr[a])
            ps_s = load_imu_seconds(npz, sc["start_local"], lo + 3.6e6, hi + 3.6e6, handling, silences, adc_a, vf, vu, thr[a])
            tr = Track(fx[fx.shortid == tags[a]], lo, hi, taus[a])
            tr.ps, tr.ps_shift = ps, ps_s
            tracks[a] = tr
            info["animals"][a] = {"tag": tags[a], "session": s, "n_fix": tr.n, "pc_time_verdict": (sc.get("pc_time_fit") or {}).get("verdict"),
                                  "seconds": int(len(ps)), "ok_s": int(ps.ok.sum()), "still_s": int(ps.still.sum()),
                                  "ok_shift_s": int(ps_s.ok.sum()),
                                  "mask": {c: int(ps[c].sum()) for c in C.MASK_COLS + ["m_adc"]},
                                  "anchors_ge7_frac": float((tr.A >= 7).mean())}
            log(f"{key} {a}: tag {tags[a]}, {tr.n:,} fixes, {int(ps.ok.sum())}/{len(ps)} s QC-ok, {int(ps.still.sum())} still; "
                f"shifted ok {int(ps_s.ok.sum())}")
        return tracks, info, {"lo": lo, "hi": hi, "animals": animals}

    # ---------------- tuning night
    tune_tracks, tune_info, tn = build_night("tuning")
    animals = tn["animals"]
    # per-anchor noise table from IMU-still bouts (>= 60 s, trimmed 1 s, >= 30 fixes), as the previous pilot's M2
    devs = []
    for a, tr in tune_tracks.items():
        ps = tr.ps
        secs = ps["sec"].to_numpy()
        tf = tr.t_al_ms
        for a0, b0 in C.true_runs(ps["still"].to_numpy(bool)):
            if b0 - a0 < C.MIN_BOUT_S:
                continue
            i0, i1 = np.searchsorted(tf, [(secs[a0] + C.TRIM_S) * 1000.0, (secs[b0 - 1] + 1 - C.TRIM_S) * 1000.0])
            if i1 - i0 < C.MIN_BOUT_FIX:
                continue
            zz = tr.z[i0:i1]
            devs.append(pd.DataFrame({"animal": a, "bout": f"{a}_{a0}", "t_s": tf[i0:i1] / 1000.0, "anchors_used": tr.A[i0:i1],
                                      "dx": zz[:, 0] - np.median(zz[:, 0]), "dy": zz[:, 1] - np.median(zz[:, 1])}))
    dev = pd.concat(devs, ignore_index=True)
    table = anchor_sigma_table(dev)
    log("anchor table (robust SD x/y): " + ", ".join(f"{k}: {v['rsd_x']:.2f}/{v['rsd_y']:.2f}" for k, v in table.items()))
    acf = drift_acf(dev)
    loco = fit_loco_thresholds_prepare(tune_tracks)
    log(f"loco thresholds: VeDBA >= {loco['theta_l']:.3f} m/s2, SBF >= {loco['rho_l']:.2f}; J {loco['J']:.3f} "
        f"(TPR {loco['tpr']:.3f}, FPR {loco['fpr']:.3f})")
    for a, tr in tune_tracks.items():
        tr.attach_imu(tr.ps, tr.ps_shift, loco["theta_l"], loco["rho_l"])
    # V3 diagnostic (gate)
    v3_rows, v3 = [], {}
    for a, tr in tune_tracks.items():
        d = v3_diagnostic(tr)
        d.insert(0, "animal", a)
        v3_rows.append(d)
        v3[a] = spearman_theil(d["dpsi_i_deg"].to_numpy(), d["dpsi_w_deg"].to_numpy()) if len(d) else {"n": 0, "rho": np.nan}
        log(f"V3 diag {a}: n {v3[a]['n']}, rho {v3[a]['rho']:+.3f}")
    v3_df = pd.concat(v3_rows, ignore_index=True)
    n_v3 = sum(1 for a in animals if np.isfinite(v3[a]["rho"]) and v3[a]["rho"] >= 0.5)
    v3_gate = n_v3 >= 4
    log(f"V3 gate: {n_v3}/5 animals with rho >= 0.5 -> {'CONTINUE' if v3_gate else 'SKIP (head turn does not constrain the path)'}")
    if v3_gate:
        log("V3 gate passed: the heading-aided smoother is not implemented in this driver version -> reported as a deviation")
    hidden_tune = {a: make_hidden(tune_tracks[a], cfg["seed"] + i) for i, a in enumerate(animals)}
    tuned, curves = tune(tune_tracks, table, hidden_tune, log)
    posthoc = tune_extended(tune_tracks, table, hidden_tune, tuned, log)   # post hoc, tuning night only, no verdict uses it
    tuned["loco"] = loco
    tuned["anchor_sigma"] = {str(k): {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in table.items()}
    # tuning-night scores (for the record; nothing is re-fitted on the test night)
    preds_tune = {a: predict_all(tune_tracks[a], table, tuned, hidden_tune[a]) for a in animals}
    err_tune, comp_tune, summ_tune = score_night(tune_tracks, preds_tune, np.random.default_rng(cfg["seed"] + 7), animals)
    # write the tuned values into the config (marked as fitted on the tuning night)
    cfg["tuned"] = {"fitted_on": f"tuning night {cfg['nights']['tuning']['start']} -> {cfg['nights']['tuning']['end']} (2026-09-08/09) only",
                    "fitted_by": "wiser/scripts/analyze_wiser_imu_smoothing.py", "run_dir": str(out),
                    "written_local": pd.Timestamp.now(tz=tz).strftime("%Y-%m-%d %H:%M:%S"),
                    "objective": "pooled median held-out error on scheme (a), hidden fixes with >= 7 anchors",
                    "huber_k": HUBER_K, "gate2": GATE2, "n_irls": N_IRLS, **json.loads(json.dumps(tuned, default=float))}
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"tuned values written to {cfg_path.name} ({time.time() - t_start:.0f} s)")

    # ---------------- test night
    test_tracks, test_info, te = build_night("test")
    for a, tr in test_tracks.items():
        tr.attach_imu(tr.ps, tr.ps_shift, loco["theta_l"], loco["rho_l"])
    hidden_test = {a: make_hidden(test_tracks[a], cfg["seed"] + 1000 + i) for i, a in enumerate(animals)}
    preds_test = {a: predict_all(test_tracks[a], table, tuned, hidden_test[a]) for a in animals}
    err_test, comp_test, summ_test = score_night(test_tracks, preds_test, np.random.default_rng(cfg["seed"] + 11), animals)
    ver = verdicts(comp_test, animals)
    for v, r in ver.items():
        log(f"verdict {v}: {r['verdict']} " + "; ".join(f"{s}: {p['n_animals_gain']}/5 gain, ctrl ok {p['n_control_no_gain']}/5, "
                                                          f"moving {p['pooled_moving_d']:+.3f}" for s, p in r["schemes"].items()))
    log(f"test night scored ({time.time() - t_start:.0f} s)")

    # ---------------- (c) plausibility on the test night, full data
    plaus = []
    for a in animals:
        tr = test_tracks[a]
        r2 = r2_from_anchors(tr.A, table)
        vis = np.ones(tr.n, bool)
        b2, b2p = tuned["B2"], tuned["B2p"]
        base = {"q": b2p["q"], "tb": b2p["tb"], "sb": b2p["sb"], "mrej": b2["mrej"]}
        cf = [{"q": b2["q"], "mrej": b2["mrej"]}, dict(base), {**base, "sv": tuned["V1"]["sv"]}, {**base, "mult": tuple(tuned["V2"]["mult"])}]
        P, B, V = kf_run(tr.t, tr.z, r2, [vis], [tr.st_mid, tr.st_mid_shift], [tr.st_at, tr.st_at_shift], cf)
        still_sec = set(tr.ps["sec"].to_numpy()[tr.ps["still"].to_numpy(bool)].tolist())
        s0 = tr.lo / 1000.0
        for name, p in (("raw", tr.z), ("B1", b1_full(tr.z)), ("B2", P[0]), ("B2p", P[1]), ("V1", P[2]), ("V2", P[3])):
            plaus.append({"animal": a, "method": name, **track_metrics(tr.t, p, walls, still_sec, s0)})
        if a == cfg.get("example_animal", "SF09"):
            example = {"t": tr.t, "raw": tr.z, "B1": b1_full(tr.z), "B2p": P[1], "V1": P[2], "V2": P[3],
                       "still": tr.still, "ok": tr.ok_true, "st_at": tr.st_at}
    plaus = pd.DataFrame(plaus)
    log(f"plausibility done ({time.time() - t_start:.0f} s)")

    # ---------------- (b) static references
    static_rows = []
    ir = cfg["static_implant"]
    lo_i, hi_i = C.to_ms(ir["run_start"], tz), C.to_ms(ir["run_end"], tz)
    fxi, _ = query_fixes(db, cfg["wiser_table"], [ir["shortid"]], lo_i, hi_i)
    wins = [(w_["label"], C.to_ms(w_["start"], tz), C.to_ms(w_["end"], tz)) for w_ in ir["windows"]]
    for r in static_reference(fxi, wins, table, tuned):
        static_rows.append({"reference": "implant 12376 (2026-09-07)", "tag": ir["shortid"], **r})
    c1 = cfg["static_cohort1"]
    db1 = Path(c1["db"])
    prov["files"].append({"role": "cohort1_fixed_db", **C.file_info(db1)})
    lo1, hi1 = C.to_ms(c1["start"], tz), C.to_ms(c1["end"], tz)
    fx1, dst1 = query_fixes(db1, c1["table"], c1["tags"], lo1, hi1)
    for tag in c1["tags"]:
        for r in static_reference(fx1[fx1.shortid == tag], [("whole window", lo1, hi1)], table, tuned):
            static_rows.append({"reference": "cohort-1 fixed test (2026-06-21/22)", "tag": tag, **r})
    static_df = pd.DataFrame(static_rows)
    log(f"static references done ({time.time() - t_start:.0f} s)")

    # ---------------- bulk tables
    err_test.to_csv(csv_dir / "heldout_errors_test.csv.gz", index=False)
    err_tune.to_csv(csv_dir / "heldout_errors_tuning.csv.gz", index=False)
    comp_test.to_csv(csv_dir / "bootstrap_comparisons_test.csv", index=False)
    comp_tune.to_csv(csv_dir / "bootstrap_comparisons_tuning.csv", index=False)
    for k, v in curves.items():
        pd.DataFrame(v).to_csv(csv_dir / f"tuning_grid_{k}.csv", index=False)
    for k, v in posthoc["curves"].items():
        pd.DataFrame(v).to_csv(csv_dir / f"posthoc_extended_grid_{k}.csv", index=False)
    v3_df.to_csv(csv_dir / "v3_diagnostic_pairs.csv", index=False)
    dev.to_csv(csv_dir / "anchor_calibration_deviations.csv.gz", index=False)
    plaus.to_csv(csv_dir / "plausibility_test.csv", index=False)
    static_df.to_csv(csv_dir / "static_references.csv", index=False)
    pd.DataFrame(acf).to_csv(csv_dir / "drift_acf_9anchor.csv", index=False)
    res = {"tuning_info": tune_info, "test_info": test_info, "tuned": tuned, "v3": v3, "v3_gate": v3_gate, "n_v3": n_v3,
           "verdicts": ver, "summ_test": {f"{m}|{s}": v for (m, s), v in summ_test.items()},
           "summ_tune": {f"{m}|{s}": v for (m, s), v in summ_tune.items()}, "cohort1_dedup": dst1,
           "posthoc": {k: v for k, v in posthoc.items() if k != "curves"},
           "runtime_s": time.time() - t_start, "numba": HAVE_NUMBA}
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=_jd), encoding="utf-8")
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")

    # ---------------- figures + report
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(comp_test, curves, tuned, v3_df, v3, example, animals, fdir, cohort, out)
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name,
            "driver": "wiser/scripts/analyze_wiser_imu_smoothing.py", "config": cfg_path.relative_to(REPO).as_posix(),
            "git_commit": C.git_commit(), "runtime_s": round(time.time() - t_start, 1)}
    rep.write_text(render_report(res, cfg, comp_test, comp_tune, summ_test, summ_tune, curves, table, acf, plaus,
                                 static_df, v3, ver, animals, taus, thr, out, figs, cohort, meta, dev), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_imu_smoothing_pilot_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    log(f"report: {rep}\nmanifest: {mp}\nruntime {time.time() - t_start:.0f} s")
    logf.close()


def fit_loco_thresholds_prepare(tracks: dict) -> dict:
    """fit_loco_thresholds needs tr.ps with still + sbf (set by load_imu_seconds); kept separate for clarity."""
    return fit_loco_thresholds(tracks)


def drift_acf(dev: pd.DataFrame, lags=(0.25, 0.5, 1, 2, 5, 10, 20, 30, 60)) -> list:
    """Autocorrelation of 9-anchor per-axis deviations within IMU-still bouts at time lags (pairs within +-15 % of lag)."""
    d9 = dev[dev.anchors_used >= 9]
    rows = []
    for ax in ("dx", "dy"):
        num = {L: 0.0 for L in lags}
        cnt = {L: 0 for L in lags}
        var_s, var_n = 0.0, 0
        for _, g in d9.groupby("bout"):
            t = g["t_s"].to_numpy()
            v = g[ax].to_numpy() - g[ax].mean()
            var_s += float((v ** 2).sum())
            var_n += len(v)
            for L in lags:
                j = np.searchsorted(t, t + L * 0.85)
                k = np.searchsorted(t, t + L * 1.15)
                for i in range(len(t)):
                    if k[i] > j[i]:
                        num[L] += float(v[i] * v[j[i]:k[i]].mean())
                        cnt[L] += 1
        var = var_s / max(var_n, 1)
        for L in lags:
            rows.append({"axis": ax[1], "lag_s": L, "acf": num[L] / max(cnt[L], 1) / var, "n_pairs": cnt[L]})
    return rows


def _jd(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    return str(o)


# ================================================================ figures
def make_figures(comp, curves, tuned, v3_df, v3, example, animals, fdir, cohort, out) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = {}
    # 1) held-out gains vs B2'
    meths = ["B1", "B2", "V1", "V2", "V1_shift", "V2_shift"]
    cols = {"B1": "0.55", "B2": "C0", "V1": "C2", "V2": "C3", "V1_shift": "C2", "V2_shift": "C3"}
    fig, axs = plt.subplots(2, 1, figsize=(11, 7.5), sharey=False)
    for ax, s, title in ((axs[0], "a", "(a) runs of 4–8 hidden fixes"), (axs[1], "a2", "(a′) hidden 2-s windows")):
        c = comp[(comp.scheme == s) & (comp.subset == "all") & (comp.ref == "B2p")]
        who = animals + ["pooled"]
        for j, m in enumerate(meths):
            d = c[c.method == m].set_index("animal").reindex(who)
            x = np.arange(len(who)) + (j - 2.5) * 0.12
            ax.errorbar(x, 100 * d.d_med, yerr=[100 * (d.d_med - d.lo), 100 * (d.hi - d.d_med)], fmt="o" if "shift" not in m else "x",
                        color=cols[m], ms=4, capsize=2, lw=1, label=LABEL[m], mfc="none" if "shift" in m else cols[m])
        ax.axhline(0, color="k", lw=0.8)
        ax.axhline(3, color="k", lw=0.8, ls=":")
        ax.set_xticks(np.arange(len(who)))
        ax.set_xticklabels(who)
        ax.set_ylabel("Δ median error vs B2′ (%)\n+ = better than B2′")
        ax.set_title(f"Test night 2026-09-10/11 — {title}; 95 % block-bootstrap CI; dotted = +3 % acceptance")
        ax.grid(alpha=0.3)
    axs[0].legend(fontsize=7, ncol=6, loc="lower center")
    fig.tight_layout()
    figs["heldout"] = fdir / f"{STEM}_heldout_{cohort}.png"
    fig.savefig(figs["heldout"], dpi=130)
    plt.close(fig)
    # 2) tuning curves
    fig, axs = plt.subplots(1, 4, figsize=(15, 3.6))
    b2 = pd.DataFrame(curves["B2"])
    for mr, g in b2.groupby("mrej"):
        axs[0].plot(g.q, g.med, "o-", ms=3, label=f"m_rej {mr:g}" if mr < 1e8 else "m_rej ∞")
    axs[0].set_xscale("log")
    axs[0].set_xlabel("q (in²/s³)")
    axs[0].set_ylabel("pooled median held-out error (in)")
    axs[0].set_title("B2")
    axs[0].legend(fontsize=7)
    b2p = pd.DataFrame(curves["B2p"])
    g = b2p[b2p.q == tuned["B2p"]["q"]].pivot(index="sb", columns="tb", values="med")
    im = axs[1].imshow(g.to_numpy(), aspect="auto", origin="lower", cmap="viridis")
    axs[1].set_xticks(range(len(g.columns)))
    axs[1].set_xticklabels([f"{c:g}" for c in g.columns])
    axs[1].set_yticks(range(len(g.index)))
    axs[1].set_yticklabels([f"{c:g}" for c in g.index])
    axs[1].set_xlabel("T_b (s)")
    axs[1].set_ylabel("σ_b (in)")
    axs[1].set_title(f"B2′ at q = {tuned['B2p']['q']:.3g}")
    fig.colorbar(im, ax=axs[1], fraction=0.05)
    v1 = pd.DataFrame(curves["V1"])
    axs[2].plot(v1.sv, v1.med, "o-")
    axs[2].axhline(tuned["B2p"]["med"], color="k", ls=":", lw=0.8, label="B2′")
    axs[2].set_xscale("log")
    axs[2].set_xlabel("σ_v (in/s)")
    axs[2].set_title("V1")
    axs[2].legend(fontsize=7)
    v2 = pd.DataFrame(curves["V2"])
    v2["ms"] = v2["mult"].apply(lambda m: m[1])
    for ms, gg in v2.groupby("ms"):
        axs[3].plot(np.arange(len(gg)), np.sort(gg.med.to_numpy()), "o-", ms=3, label=f"m_still {ms:g}")
    axs[3].axhline(tuned["B2p"]["med"], color="k", ls=":", lw=0.8)
    axs[3].set_xlabel("(m_active, m_loco) configs, sorted")
    axs[3].set_title("V2")
    axs[3].legend(fontsize=7)
    fig.suptitle("Tuning night 2026-09-08/09, scheme (a), hidden fixes with ≥ 7 anchors", fontsize=10)
    fig.tight_layout()
    figs["tuning"] = fdir / f"{STEM}_tuning_{cohort}.png"
    fig.savefig(figs["tuning"], dpi=130)
    plt.close(fig)
    # 3) V3 diagnostic
    fig, axs = plt.subplots(1, len(animals), figsize=(3.2 * len(animals), 3.4), sharex=True, sharey=True)
    for ax, a in zip(np.atleast_1d(axs), animals):
        d = v3_df[v3_df.animal == a]
        ax.scatter(d.dpsi_i_deg, d.dpsi_w_deg, s=3, alpha=0.3)
        ax.plot([-180, 180], [-180, 180], "k:", lw=0.7)
        ax.axhline(0, color="k", lw=0.4)
        ax.axvline(0, color="k", lw=0.4)
        ax.set_xlim(-250, 250)
        ax.set_ylim(-185, 185)
        ax.set_title(f"{a}: ρ {v3[a]['rho']:+.2f}, n {v3[a]['n']}", fontsize=9)
        ax.set_xlabel("Δψ_I, 1 s (deg, + CCW)")
    np.atleast_1d(axs)[0].set_ylabel("Δψ_W path turn (deg)")
    fig.suptitle("V3 gate diagnostic, tuning night: locomotion windows (WISER ≥ 10 in/s ≥ 3 s, IMU active); gate ρ ≥ 0.5 in ≥ 4/5", fontsize=9)
    fig.tight_layout()
    figs["v3"] = fdir / f"{STEM}_v3_diagnostic_{cohort}.png"
    fig.savefig(figs["v3"], dpi=130)
    plt.close(fig)
    # 4) example snippet (deterministic: the first 4-min stretch of the test night with >= 60 s IMU-still and >= 20 s locomoting)
    t = example["t"]
    stt = example["st_at"]
    t0 = None
    for s0 in np.arange(0, t[-1] - 240, 30):
        m = (t >= s0) & (t < s0 + 240)
        if m.sum() > 400 and (stt[m] == 1).mean() * 240 >= 60 and (stt[m] == 3).mean() * 240 >= 20:
            t0 = s0
            break
    if t0 is None:
        t0 = 3600.0
    m = (t >= t0) & (t < t0 + 240)
    fig, axs = plt.subplots(2, 1, figsize=(11, 5.5), sharex=True)
    for k, ax in enumerate(axs):
        ax.plot(t[m] - t0, example["raw"][m, k], ".", ms=2, color="0.6", label="raw fixes")
        for name, c in (("B1", "0.2"), ("B2p", "C0"), ("V1", "C2"), ("V2", "C3")):
            ax.plot(t[m] - t0, example[name][m, k], "-", lw=0.9, color=c, label=LABEL[name])
        still = example["st_at"][m] == 1
        for a_, b_ in C.true_runs(still):
            ax.axvspan(t[m][a_] - t0, t[m][b_ - 1] - t0, color="C2", alpha=0.08, lw=0)
        ax.set_ylabel(f"{'xy'[k]} (in)")
        ax.grid(alpha=0.3)
    axs[0].legend(fontsize=7, ncol=6)
    axs[1].set_xlabel(f"s after night start + {t0:.0f} s (aligned clock); green shading = IMU-still")
    fig.suptitle(f"Example, {cfg_example_label(example)} (full data, no hiding)", fontsize=10)
    fig.tight_layout()
    figs["example"] = fdir / f"{STEM}_example_{cohort}.png"
    fig.savefig(figs["example"], dpi=130)
    plt.close(fig)
    for p in figs.values():
        (out / "figures" / p.name).write_bytes(p.read_bytes())
    return figs


def cfg_example_label(example) -> str:
    return "test night 2026-09-10/11"


# ================================================================ report
def pct(x, nd=1):
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:+.{nd}f} %"


def fnum(x, nd=2):
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


DEFINITIONS = r"""
## Definitions

Units: WISER positions in **inches** in the WISER native frame (unverified offset origin; no georeference); IMU
acceleration m/s², angular rate °/s. Times are field-PC time (WISER `timestamp`, the IMU's `t_pc_ms`). Symbols:
$a$ = animal, $i$ = WISER fix, $k$ = filter step (one per fix), $s$ = field-PC second, $A_i$ = `anchors_used`,
$\mathbf z_i=(x_i,y_i)$ = the raw fix.

### Duplicate rule
Rows sharing (tag, `timestamp`) are collapsed to one: the row with the largest $A_i$; ties → the smallest `reportid`.
**Text:** one fix per timestamp; the higher-anchor solve is the more precise one (static SD table below).

### Aligned time
$t^{\mathrm{al}}_i=t_i-\tau^*_a$ with $\tau^*_a$ the tuning-night effective lag of the previous pilot (M1). **Text:**
puts WISER on the IMU clock; it does not change any position-only result (all times shift together).

### IMU per-second classes (IMU QC mask, still rule: previous pilot, reused unmodified)
$$ \mathrm{still}(s)=\mathrm{ok}(s)\wedge\mathrm{VeDBA}_{1s}(s)<\theta_a\wedge|\omega|_{1s}(s)<10^\circ/\mathrm s,\qquad
\mathrm{loco}(s)=\mathrm{ok}(s)\wedge\neg\mathrm{still}(s)\wedge \mathrm{VeDBA}_{1s}(s)\ge\theta_L\wedge \mathrm{SBF}(s)\ge\rho_L $$
$$ \mathrm{SBF}(s)=\frac{\sum_{4\le f\le7\,\mathrm{Hz}}|\hat a_\uparrow(f)|^2}{\sum_{1\le f\le20\,\mathrm{Hz}}|\hat a_\uparrow(f)|^2} $$
$\hat a_\uparrow$ = FFT of the Hann-windowed vertical earth-frame linear acceleration (`lin_acc_earth_ms2[:,2]`,
unaffected by yaw drift) over $[s-0.5,s+1.5)$ (100 samples); active = ok ∧ ¬still ∧ ¬loco; state 0 = not ok.
$\mathrm{ok}(s)$ = the previous pilot's mask (nodata, saturated, frozen flag and rule, invalid, NaN, unreliable,
handling, all-tag silence ± 2 min, tag validity) ∧ outside the cohort YAML's `ephys.adc_lane.on_windows`.
**Text:** still = the head does not move (thresholds fixed before this pilot); locomoting = strong head acceleration
with stride-band (4–7 Hz) power; $(\theta_L,\rho_L)$ maximise Youden's $J=\mathrm{TPR}-\mathrm{FPR}$ against WISER
1-s median speed ≥ 10 in/s (positives) vs < 3 in/s (negatives) over ok, non-still tuning-night seconds.

### Per-anchor measurement noise $\sigma_{\mathrm{ax}}(A)$
$$ d_{i,\mathrm{ax}}=\mathrm{ax}_i-\operatorname{median}_{j\in B}\mathrm{ax}_j,\qquad \sigma_{\mathrm{ax}}(A)=1.4826\cdot\operatorname{median}_{i:A_i=A}\big|d_{i,\mathrm{ax}}-\operatorname{median}(d_{\mathrm{ax}})\big| $$
$B$ = a tuning-night IMU-still bout (≥ 60 s, trimmed 1 s each end, ≥ 30 fixes), ax ∈ {x, y}, $A\le3$ pooled.
**Text:** robust per-axis SD (in) of a fix about the still head's position, by anchor count; the core of the error
distribution (outliers are left to the robust weights). $R_i=\mathrm{diag}(\sigma^2_x(A_i),\sigma^2_y(A_i))$.

### B1 — library median smoother
Full data: $\hat{\mathbf p}_i=\operatorname{median}_{j=i-3}^{i+3}\mathbf z_j$ (coordinate-wise, as `add_speed`).
Held-out: $\hat{\mathbf z}_h=\operatorname{median}\{\mathbf z_j: j\in\mathcal N_7(h)\}$, $\mathcal N_7(h)$ = the 7 visible
fixes with the smallest $|t_j-t_h|$. **Text:** the current library position, used as the reference baseline.

### B2 — robust constant-velocity Kalman/RTS smoother
Per axis, state $\mathbf x=(p,v)$; between steps $\Delta t=t_k-t_{k-1}$:
$$ \mathbf x_k=\begin{pmatrix}1&\Delta t\\0&1\end{pmatrix}\mathbf x_{k-1}+\boldsymbol\eta_k,\quad
\mathrm{Cov}(\boldsymbol\eta_k)=q\begin{pmatrix}\Delta t^3/3&\Delta t^2/2\\\Delta t^2/2&\Delta t\end{pmatrix},\qquad
z_k=p_k+\varepsilon_k,\ \varepsilon_k\sim\mathcal N(0,\sigma^2_{\mathrm{ax}}(A_k)/w_k) $$
Forward Kalman filter, then the Rauch–Tung–Striebel smoother (means). **Outliers:** pass 0 inflates $R_k$ by
$d_k^2/13.8$ when the 2-D innovation Mahalanobis distance $d_k^2=\sum_{\mathrm{ax}}\nu^2_{k,\mathrm{ax}}/S_{k,\mathrm{ax}}>\chi^2_{2,0.999}=13.8$;
passes 1–2 are IRLS: $m_k^2=\sum_{\mathrm{ax}}(z_{k,\mathrm{ax}}-\hat z_{k,\mathrm{ax}})^2/\sigma^2_{\mathrm{ax}}(A_k)$ from
the previous smoothed track, $w_k=1$ ($m_k\le2.5$), $2.5/m_k$ ($2.5<m_k\le m_{\mathrm{rej}}$), 0 (rejected, $m_k>m_{\mathrm{rej}}$).
Hidden fixes enter as steps without an update; $\hat{\mathbf z}_h=\hat{\mathbf p}(t_h)$. **Text:** a continuous-time
correlated-random-walk smoother (Johnson et al. 2008) with per-fix error from `anchors_used` and robust outlier
weights; $q$ (in²/s³) sets how fast velocity may change; $m_{\mathrm{rej}}$ and $q$ tuned.

### B2′ — B2 with slow measurement drift
State $(p,v,b)$ per axis, $b_k=\phi_k b_{k-1}+\xi_k$, $\phi_k=e^{-\Delta t/T_b}$, $\mathrm{Var}(\xi_k)=\sigma_b^2(1-\phi_k^2)$,
$z_k=p_k+b_k+\varepsilon_k$ with white variance $\sigma^2_w(A)=\max(\sigma^2_{\mathrm{ax}}(A)-\sigma_b^2,\ \sigma^2_{\mathrm{ax}}(A)/4)$.
Held-out prediction $\hat{\mathbf z}_h=\hat{\mathbf p}(t_h)+\hat{\mathbf b}(t_h)$ (the expected measurement); position
output $\hat{\mathbf p}$. **Text:** WISER's slow correlated wander (seconds to minutes) is modelled as part of the
measurement, not of the head; $T_b$ (s) and $\sigma_b$ (in) tuned.

### V1 — zero-velocity pseudo-measurement (ZUPT)
At every step $k$ (visible or hidden) whose aligned second is IMU-still, per axis an extra update $0=v_k+\epsilon$,
$\epsilon\sim\mathcal N(0,\sigma_v^2)$. **Text:** the IMU says the head (and the tag on it) does not move; $\sigma_v$
(in/s) sets how hard that is enforced; tuned.

### V2 — IMU-switched process noise
$q_k=m_{c(k)}\,q_{B2'}$ with $c(k)$ the IMU class of the second containing the interval midpoint
$(t_{k-1}+t_k)/2$: $m_0=1$ (IMU unusable), $m_s$ (still), $m_a$ (active), $m_l$ (locomoting). **Text:** a
state-switching movement model driven by the IMU (Michelot & Blackwell 2019); tuned multipliers.

### +1 h-shifted IMU control
V1 and V2 rerun with every IMU-derived input (classes, ZUPT, QC) taken from $s+3600$ instead of $s$. **Text:** keeps
the IMU's statistics but breaks its link to the WISER track; a real IMU gain must vanish.

### Held-out schemes and error
(a): per tag, hide runs of $L\sim\mathcal U\{4..8\}$ consecutive fixes separated by $G\sim\mathcal U\{1..47\}$ visible fixes
($E[\text{hidden}]=6/30=20\,\%$), fixed seed. (a′): hide every fix in a random 10 % of the night's 2-s windows.
$$ e_h=\lVert\mathbf z_h-\hat{\mathbf z}_h\rVert_2 $$
over the **scored set**: hidden fixes with $A_h\ge7$ whose aligned second is ok for both the IMU and the shifted IMU.
Subsets: still = IMU-still second; moving = ok ∧ ¬still; loco = IMU locomoting. **Text:** how well each method predicts a
fix it has not seen (in). Why smoothing cannot game it: the hidden fix is $\mathbf z_h=\mathbf p_h+\mathbf b_h+\boldsymbol\varepsilon_h$
with $\boldsymbol\varepsilon_h$ independent of every visible fix, so
$$ E[e_h^2]=E\lVert\mathbf p_h+\mathbf b_h-\hat{\mathbf z}_h\rVert^2+E\lVert\boldsymbol\varepsilon_h\rVert^2 ,$$
the second term is the same for every method; a method lowers $e$ only by predicting the predictable part better, and
over- and under-smoothing are both penalised. The target includes WISER's drift $\mathbf b_h$, so (a) rewards
predicting the drift too; the static references test the head position itself.

### Relative median improvement and its CI
$$ \Delta_M=1-\frac{\operatorname{median}(e_M)}{\operatorname{median}(e_{\mathrm{ref}})},\qquad
\Delta^{\mathrm{RMSE}}_M=1-\frac{\mathrm{RMSE}(e_M)}{\mathrm{RMSE}(e_{\mathrm{ref}})} $$
over the same fixes (ref = B2′ unless stated). 95 % CI: 1000 paired block-bootstrap replicates — the 5-min blocks
of the night are drawn with replacement (within each animal for the pooled value), both methods get the same draw,
$\Delta$ is recomputed (weighted median), CI = 2.5–97.5 % quantiles. **Text:** + = the method's typical error is that
fraction smaller than B2′'s; blocks of 5 min keep the within-block autocorrelation.

### Acceptance (pre-registered)
Per IMU variant on the test night, on (a) or (a′): (i) $\Delta\ge3\,\%$ with CI lower bound > 0 in ≥ 4 of 5 animals;
(ii) the +1 h control's CI lower bound ≤ 0 (no significant gain) in ≥ 4 of 5 animals; (iii) pooled $\Delta$ on moving
fixes ≥ −2 %. ACCEPTED = (i) ∧ (ii) ∧ (iii); INCONCLUSIVE = (i) in exactly 3 animals, or (i) ∧ ¬(ii); else FAIL.

### V3 gate diagnostic
$$ \mathbf d_s=\tilde{\mathbf p}_s-\tilde{\mathbf p}_{s-1},\qquad \Delta\psi_W(s)=\operatorname{atan2}(d_{s,x}d_{s+1,y}-d_{s,y}d_{s+1,x},\ \mathbf d_s\!\cdot\!\mathbf d_{s+1}),\qquad \Delta\psi_I(s)=\int_s^{s+1}\omega_{\mathrm{turn}}\,dt $$
$\tilde{\mathbf p}_s$ = aligned 1-s median of ≥ 2 valid fixes; pairs inside locomotion windows = runs of ≥ 3 s with
WISER 1-s median speed ≥ 10 in/s and IMU ok ∧ ¬still. Spearman $\rho(\Delta\psi_I,\Delta\psi_W)$ and Theil–Sen slopes per
animal. **Gate:** V3 only if $\rho\ge0.5$ in ≥ 4 of 5 animals. **Text:** does the head's turn predict the path's turn
over one second while the animal runs? (Head yaw ≠ travel direction: Hou et al. 2020.)

### Static-reference error (b)
$$ \mathbf p^*=\operatorname{median}_{i\in W}\mathbf z_i,\quad \mathrm{bias}=\big\lVert\overline{\hat{\mathbf p}}_W-\mathbf p^*\big\rVert,\quad
\mathrm{RMSE}=\sqrt{\tfrac1{|W|}\textstyle\sum_{i\in W}\lVert\hat{\mathbf p}_i-\mathbf p^*\rVert^2} $$
$W$ = the fixes of a static window, $\hat{\mathbf p}_i$ = the method's full-data position at fix $i$. **Text:** how far a
method's track of a tag that did not move stays from its (constant) median position, in inches.

### Track plausibility (c)
On a 0.25-s grid (linear interpolation only inside inter-fix gaps ≤ 1 s): $v(t)=\lVert\hat{\mathbf p}(t+0.5)-\hat{\mathbf p}(t-0.5)\rVert/1\,\mathrm s$,
$a(t)=\lVert\hat{\mathbf p}(t+0.5)-2\hat{\mathbf p}(t)+\hat{\mathbf p}(t-0.5)\rVert/0.25\,\mathrm s^2$; path length
$=\sum\lVert\hat{\mathbf p}(s+1)-\hat{\mathbf p}(s)\rVert$ on the 1-s grid, per hour; wall excursion = share of fixes with
signed distance to the regime-B wall-ridge rectangle $d<-15$ in (accuracy report). **Text:** method-agnostic speed
(in/s), acceleration (in/s²), distance (in/h) and out-of-paddock share; speed during IMU-still seconds is circular for
the IMU variants (reported only). Smoothing scale changes speed and distance (Noonan et al. 2019; Gupte et al. 2022).
"""


def render_report(res, cfg, comp, comp_tune, summ, summ_tune, curves, table, acf, plaus, static_df, v3, ver, animals,
                  taus, thr, out, figs, cohort, meta, dev) -> str:
    L = []
    A = L.append
    tn, te = cfg["nights"]["tuning"], cfg["nights"]["test"]
    tu = res["tuned"]
    rel = lambda p: "../figures/" + Path(p).name  # noqa: E731

    def cget(scheme, subset, method, who, ref="B2p", c=comp):
        d = c[(c.scheme == scheme) & (c.subset == subset) & (c.method == method) & (c.ref == ref) & (c.animal == who)]
        return d.iloc[0] if len(d) else None

    def dstr(r):
        return "–" if r is None else f"{pct(r['d_med'])} [{pct(r['lo'])}, {pct(r['hi'])}]"

    A("# WISER + head-IMU smoothing pilot — `wiser_baseline` (2026c)")
    A("")
    A("- **What this is:** a *measurement* report. Question: can the head IMU (same rigid headstage as the WISER tag; user, 2026-09-29) improve WISER UWB position estimates **beyond a good position-only smoother**? Scored by predicting held-out WISER fixes. **No behavioural claim.**")
    A(f"- **Nights:** tuning {tn['start']} → {tn['end']} (every hyperparameter, noise model, threshold fitted here only); test {te['start']} → {te['end']} (named in the plan before any result). Field-PC local time (EDT).")
    A("- **Animals and tags (shortid):** " + ", ".join(f"{a} = {res['test_info']['tags'][a]}" for a in animals) + ".")
    A("- **Frame status:** WISER native inches, unverified offset origin; nothing here places a position in the paddock.")
    A("- **Plan:** [`implementation_plan/2026-09-29-wiser-imu-smoothing-pilot.md`](../../../../implementation_plan/2026-09-29-wiser-imu-smoothing-pilot.md) (approved by the user 2026-09-29, \"开始\"). Design, grids, acceptance and deviations were fixed there before coding.")
    A(f"- **Run:** `python wiser/scripts/analyze_wiser_imu_smoothing.py --cohort {cohort}`; bulk `{out}` (per-fix errors, bootstrap tables, tuning grids, V3 pairs, calibration deviations, `summary.json`, `input_provenance.json`, `log.txt`); pointer `run_manifest_imu_smoothing_pilot_{cohort}.json`. Git `{meta['git_commit']}`; runtime {res['runtime_s'] / 60:.1f} min; numba {res['numba']}.")
    A("")
    # ---------------- verdicts
    A("## 0. Verdicts")
    A("")
    A("| IMU variant | (a) animals with Δ ≥ 3 % & CI > 0 | (a) control no-gain | (a) pooled moving Δ | (a′) animals | (a′) control no-gain | (a′) pooled moving Δ | **Verdict** |")
    A("|---|---|---|---|---|---|---|---|")
    for v in ("V1", "V2"):
        s = ver[v]["schemes"]
        A(f"| {LABEL[v]} | {s['a']['n_animals_gain']}/5 | {s['a']['n_control_no_gain']}/5 | {pct(s['a']['pooled_moving_d'])} | "
          f"{s['a2']['n_animals_gain']}/5 | {s['a2']['n_control_no_gain']}/5 | {pct(s['a2']['pooled_moving_d'])} | **{ver[v]['verdict']}** |")
    A(f"| V3 heading-aided | gate: ρ ≥ 0.5 in {res['n_v3']}/5 animals | | | | | | **{'RUN' if res['v3_gate'] else 'SKIPPED — head turn does not constrain the path'}** |")
    A("")
    A("Pooled test-night held-out error (in), hidden fixes with ≥ 7 anchors, and Δ vs B2′ (95 % block-bootstrap CI):")
    A("")
    A("| Method | (a) median | (a) RMSE | (a) Δ median vs B2′ | (a′) median | (a′) RMSE | (a′) Δ median vs B2′ |")
    A("|---|---|---|---|---|---|---|")
    for m in ("B1", "B2", "B2p", "V1", "V2", "V1_shift", "V2_shift", "B2p_p"):
        sa, sb = summ.get((m, "a"), {}).get("pooled", {}), summ.get((m, "a2"), {}).get("pooled", {})
        da = "(reference)" if m == "B2p" else dstr(cget("a", "all", m, "pooled"))
        db = "(reference)" if m == "B2p" else dstr(cget("a2", "all", m, "pooled"))
        A(f"| {LABEL[m]} | {fnum(sa.get('med'))} | {fnum(sa.get('rmse'))} | {da} | {fnum(sb.get('med'))} | {fnum(sb.get('rmse'))} | {db} |")
    A("")
    A("Position-only smoothers vs the library B1 (pooled, test night): " + "; ".join(
        f"{LABEL[m]} (a) {dstr(cget('a', 'all', m, 'pooled', ref='B1'))}, (a′) {dstr(cget('a2', 'all', m, 'pooled', ref='B1'))}" for m in ("B2", "B2p")) + ".")
    A("")
    A("Classification (regime-aware-wiser-tracking): every result here is a **measurement** result. The held-out target is a WISER fix (head position + WISER's own slow drift + white noise), so a gain means better prediction of WISER, which is necessary but not sufficient for better head position; §6 (static references) is the check on position itself.")
    A("")
    # ---------------- reading
    r_ = lambda s, sub, m, ref="B2p": cget(s, sub, m, "pooled", ref=ref)  # noqa: E731
    dm = lambda r: pct(r["d_med"]) if r is not None else "–"  # noqa: E731
    n_still = r_("a", "still", "V1")["n"] if r_("a", "still", "V1") is not None else 0
    n_all = summ.get(("B2p", "a"), {}).get("pooled", {}).get("n", 1)
    c1s = static_df[static_df.reference.str.startswith("cohort-1")].groupby("method")["rmse_in"].median()
    plm = plaus.groupby("method")[["path_in_per_h", "wall_out_frac", "v_p50"]].median()
    A("**Reading.**")
    A("")
    A(f"1. **The gain is in position-only smoothing.** On the test night B2′ predicts held-out fixes better than the library median by {dm(r_('a', 'all', 'B2p', 'B1'))} (a) and {dm(r_('a2', 'all', 'B2p', 'B1'))} (a′) in median error, and much more in RMSE ({pct(r_('a', 'all', 'B1')['d_rmse'])} for B1 vs B2′ on (a): the median-7 has heavy tails). The difference is largest on IMU-locomoting fixes (B1 vs B2′ {dm(r_('a', 'loco', 'B1'))}). The drift term adds little over B2 ({dm(r_('a', 'all', 'B2'))} for B2 vs B2′).")
    gains = [r_(s, "all", m)["d_med"] for s in ("a", "a2") for m in ("V1", "V2") if r_(s, "all", m) is not None]
    passing = []
    for m in ("V1", "V2"):
        for s in ("a", "a2"):
            cc = comp[(comp.scheme == s) & (comp.subset == "all") & (comp.method == m) & (comp.ref == "B2p") & comp.animal.isin(animals)]
            ok_ = cc[(cc.d_med >= ACCEPT["min_gain"]) & (cc.lo > 0)].animal.tolist()
            if ok_:
                passing.append(f"{m} {'(a)' if s == 'a' else '(a′)'}: {', '.join(ok_)}")
    pass_txt = ("Animals passing the per-animal bar: " + "; ".join(passing) + ".") if passing else "No animal passes the per-animal bar."
    A(f"2. **The head IMU adds {100 * min(gains):.1f}–{100 * max(gains):.1f} % beyond B2′ (pooled), below the pre-registered 3 %.** V1 {dm(r_('a', 'all', 'V1'))} / {dm(r_('a2', 'all', 'V1'))} and V2 {dm(r_('a', 'all', 'V2'))} / {dm(r_('a2', 'all', 'V2'))} ((a) / (a′), pooled; CIs above 0). The gain sits where the IMU is informative: on IMU-still fixes (only {100 * n_still / max(n_all, 1):.0f} % of scored fixes) V1 gains {dm(r_('a', 'still', 'V1'))} (a) and {dm(r_('a2', 'still', 'V1'))} (a′), V2 {dm(r_('a', 'still', 'V2'))} / {dm(r_('a2', 'still', 'V2'))}; V2 also gains on locomoting fixes on (a) ({dm(r_('a', 'loco', 'V2'))}). The +1 h controls show no gain (V1 {dm(r_('a', 'all', 'V1_shift'))}, V2 {dm(r_('a', 'all', 'V2_shift'))} on (a)), so the small gain is specific to the aligned IMU. {pass_txt}")
    A(f"3. **Head turn does not pass the gate for heading aid**: ρ = {', '.join(f'{v3[a]['rho']:.2f}' for a in animals)} (1-s turns while running); the association is moderate but below the pre-registered ρ ≥ 0.5 in 4 of 5 animals, so V3 was not built.")
    if len(c1s):
        A(f"4. **Static references agree with (1):** on the six cohort-1 fixed tags the median RMSE about the true (median) position falls from {c1s.get('raw', np.nan):.2f} in (raw) to {c1s.get('B1', np.nan):.2f} (B1), {c1s.get('B2', np.nan):.2f} (B2) and {c1s.get('B2p_p', np.nan):.2f} in (B2′ position output); the dropped implant shows the same order in its first quiet window and little difference between the smoothers in the second (§6).")
    A(f"5. **Smoothing changes derived kinematics a lot:** median path length {plm.loc['raw', 'path_in_per_h']:,.0f} in/h (raw) → {plm.loc['B1', 'path_in_per_h']:,.0f} (B1) → {plm.loc['B2p', 'path_in_per_h']:,.0f} (B2′); share of fixes > 15 in beyond the wall ridge {100 * plm.loc['raw', 'wall_out_frac']:.2f} % → {100 * plm.loc['B1', 'wall_out_frac']:.3f} % → {100 * plm.loc['B2p', 'wall_out_frac']:.3f} %. Distances from any of these tracks are smoothing-scale dependent (§7).")
    A("")
    # ---------------- data and masks
    A("## 1. Data, masks and what they removed")
    A("")
    A(f"- **WISER:** `{cfg['wiser_db']}` (table `{cfg['wiser_table']}`), opened `mode=ro` + `query_only`; sha256 prefix checked (`{cfg['wiser_db_sha256_prefix_expected']}`). Duplicate rule applied (Definitions): tuning night {res['tuning_info']['dedup']['dup_groups']} (tag, timestamp) groups → {res['tuning_info']['dedup']['rows_dropped']} rows dropped of {res['tuning_info']['dedup']['rows']:,} ({res['tuning_info']['dedup']['dropped_same_xy']} identical xy); test night {res['test_info']['dedup']['dup_groups']} groups → {res['test_info']['dedup']['rows_dropped']} of {res['test_info']['dedup']['rows']:,}.")
    A("- **IMU:** make_imu 50-Hz npz (regenerated with frozen/invalid flags, commit `6451d6c`). Still thresholds θ_a (`IMU_STILL_THR`, m/s²): " + ", ".join(f"{a} {thr[a]}" for a in animals) + "; |ω| < 10 °/s.")
    A("- **τ\\* (s, tuning night, previous pilot M1):** " + ", ".join(f"{a} {taus[a]:+.2f}" for a in animals) + " — applied unchanged on the test night.")
    A("")
    for key, info in (("tuning", res["tuning_info"]), ("test", res["test_info"])):
        A(f"**{key.capitalize()} night** (seconds of the {cfg['nights'][key]['start'][11:16]}–{cfg['nights'][key]['end'][11:16]} window removed per reason; reasons overlap):")
        A("")
        A("| Animal | session | pc_time verdict | fixes | ≥ 7 anchors | seconds | nodata | saturated | frozen flag | frozen rule | unreliable | handling | silence | ADC lane | QC-ok | IMU-still | shifted-IMU ok |")
        A("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for a in animals:
            r = info["animals"][a]
            mk = r["mask"]
            A(f"| {a} | `{r['session']}` | {str(r['pc_time_verdict'])[:40]} | {r['n_fix']:,} | {100 * r['anchors_ge7_frac']:.1f} % | {r['seconds']} | {mk['m_nodata']} | {mk['m_saturated']} | "
              f"{mk['m_frozen_flag']} | {mk['m_frozen_rule']} | {mk['m_unreliable']} | {mk['m_handling']} | {mk['m_silence']} | {mk['m_adc']} | {r['ok_s']} | {r['still_s']} | {r['ok_shift_s']} |")
        A("")
    A("No handling window or all-tag silence falls inside either night window. On the test night SF08 and SF12 start their lane-off sessions at 21:02:45 and 21:05:18 (after the ADC-lane night pieces, quarantined), so their first minutes have no IMU (`nodata`); SF07's session carries the chain verdict 'inconsistent' but is accepted on its native fit (39 anchors, 32 ms; `cohorts/2026c.yaml ephys.pc_time_accept`).")
    A("")
    A(DEFINITIONS)
    # ---------------- prior work
    A("## 2. Prior work (web audit, 2026-09-29)")
    A("")
    A("- UWB+IMU fusion gains of 27–53 % are reported against **raw** UWB, never against a tuned position-only smoother; this pilot's reference is B2′, not raw.")
    A("- Robust smoothing with a per-fix error model and outlier handling is expected to give most of the gain: Johnson et al. 2008, continuous-time correlated random walk ([ESA](https://esajournals.onlinelibrary.wiley.com/doi/10.1890/07-1032.1)); Wen et al. 2021 ([NAVIGATION](https://navi.ion.org/content/68/2/315)); Fleming et al. — DOP-type quality numbers can mislead ([bioRxiv](https://www.biorxiv.org/content/10.1101/2020.06.12.130195v2)); here `calculation_error` is useless and `anchors_used` is the error proxy.")
    A("- IMU-driven state switching: Michelot & Blackwell 2019 ([MEE](https://besjournals.onlinelibrary.wiley.com/doi/10.1111/2041-210X.13154)) → V2.")
    A("- Smoothing scale changes speed and distance: Noonan et al. 2019 ([Mov. Ecol.](https://movementecologyjournal.biomedcentral.com/articles/10.1186/s40462-019-0177-1)); Gupte et al. 2022 ([J. Anim. Ecol.](https://besjournals.onlinelibrary.wiley.com/doi/10.1111/1365-2656.13610)) → §7.")
    A("- Held-out validation of state-space predictions: Jonsen et al. 2020 ([arXiv](https://arxiv.org/abs/2005.00401)) → schemes (a)/(a′).")
    A("- Head yaw ≠ travel direction: Hou et al. 2020 ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7664376/)) → the V3 gate. Rat head-acceleration gait bands: Alves et al. 2016 ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC4976156/)) → the 4–7 Hz stride band.")
    A("- No study of head-IMU + UWB on rodents was found.")
    A("")
    # ---------------- tuning
    A("## 3. Tuning (night 2026-09-08/09 only)")
    A("")
    A(f"![tuning]({rel(figs['tuning'])})")
    A("")
    A("**Per-anchor noise** (robust SD, in, per axis; plain SD in brackets; IMU-still bouts of the tuning night, "
      f"{dev['bout'].nunique()} bouts, {len(dev):,} fixes):")
    A("")
    A("| anchors | fixes | σ_x robust (SD) | σ_y robust (SD) |")
    A("|---|---|---|---|")
    for k in range(3, 10):
        r = table[k]
        A(f"| {'≤ 3' if k == 3 else k} | {r['n']:,} | {r['rsd_x']:.2f} ({r['sd_x']:.2f}) | {r['rsd_y']:.2f} ({r['sd_y']:.2f}) |")
    A("")
    ad = pd.DataFrame(acf)
    A("Autocorrelation of 9-anchor deviations inside IMU-still bouts (bout-mean removed; lag ± 15 %): " + "; ".join(
        f"{L_:g} s x {ad[(ad.axis == 'x') & (ad.lag_s == L_)].acf.iloc[0]:.2f} / y {ad[(ad.axis == 'y') & (ad.lag_s == L_)].acf.iloc[0]:.2f}"
        for L_ in sorted(ad.lag_s.unique())) + ". Bout-centring biases long-lag values low.")
    A("")
    lo_ = tu["loco"]
    A(f"**IMU locomotion class:** VeDBA_1s ≥ **{lo_['theta_l']:.3f} m/s²** and SBF ≥ **{lo_['rho_l']:.2f}**; Youden J {lo_['J']:.3f} (TPR {lo_['tpr']:.3f}, FPR {lo_['fpr']:.3f}; {lo_['n_pos']:,} WISER-locomoting vs {lo_['n_neg']:,} WISER-slow seconds).")
    A("")
    A("| Method | tuned values | pooled median held-out error (a), tuning night (in) |")
    A("|---|---|---|")
    A(f"| B2 | q = {tu['B2']['q']:g} in²/s³, m_rej = {'∞' if tu['B2']['mrej'] > 1e8 else tu['B2']['mrej']} (k = {HUBER_K}, gate χ² = {GATE2:.1f}, {N_IRLS} IRLS passes) | {tu['B2']['med']:.3f} |")
    A(f"| B2′ | q = {tu['B2p']['q']:.3g} in²/s³, T_b = {tu['B2p']['tb']:g} s, σ_b = {tu['B2p']['sb']:g} in | {tu['B2p']['med']:.3f} |")
    A(f"| V1 | σ_v = {tu['V1']['sv']:g} in/s | {tu['V1']['med']:.3f} |")
    A(f"| V2 | m_still / m_active / m_loco = {tu['V2']['mult'][1]:g} / {tu['V2']['mult'][2]:g} / {tu['V2']['mult'][3]:g} | {tu['V2']['med']:.3f} |")
    A("")
    A("Tuning-night Δ vs B2′ (pooled, same statistics as the test): " + "; ".join(
        f"{LABEL[m]} (a) {dstr(cget('a', 'all', m, 'pooled', c=comp_tune))}" for m in ("B1", "B2", "V1", "V2", "V1_shift", "V2_shift")) + ".")
    A("")
    A("All tuned values are written to `wiser/configs/wiser_imu_smoothing_2026c.json` → `tuned` (marked as fitted on 2026-09-08/09); full grids in the bulk `csv/tuning_grid_*.csv`.")
    A("")
    edges = []
    if tu["B2"]["q"] in (1, 3000):
        edges.append(f"B2 q = {tu['B2']['q']:g}")
    if tu["B2p"]["q"] in (tu["B2"]["q"] / 3, tu["B2"]["q"] * 3):
        edges.append(f"B2′ q = {tu['B2p']['q']:.3g}")
    if tu["B2p"]["tb"] in (5, 120):
        edges.append(f"T_b = {tu['B2p']['tb']:g} s")
    if tu["B2p"]["sb"] in (0.5, 2.5):
        edges.append(f"σ_b = {tu['B2p']['sb']:g} in")
    if tu["V1"]["sv"] in (0.25, 4.0):
        edges.append(f"σ_v = {tu['V1']['sv']:g} in/s")
    ms_, ma_, ml_ = tu["V2"]["mult"][1:]
    edges += [f"m_still = {ms_:g}"] if ms_ in (0.01, 1.0) else []
    edges += [f"m_active = {ma_:g}"] if ma_ in (0.3, 3.0) else []
    edges += [f"m_loco = {ml_:g}"] if ml_ in (1.0, 10.0) else []
    A("**Grid edges:** " + (", ".join(edges) + " sit on the edge of their pre-registered grid, so the optimum may lie outside it." if edges else "no tuned value sits on a grid edge."))
    A("")
    ph = res.get("posthoc")
    if ph:
        A("**Post hoc, tuning night only** (added after the first run because of the edge hits; no verdict uses it; nothing of it was evaluated on the test night): "
          f"a wider grid (B2 q ∈ {{0.1, 0.3, 1, 3}}; B2′ q ∈ {{0.1, 0.3, 1}} × T_b ∈ {{15, 30, 60}} × σ_b ∈ {{2.5, 4, 6}}; V1 σ_v ∈ {{0.03, 0.1, 0.25}}; "
          f"V2 m_still ∈ {{0.001, 0.003, 0.01}} × m_active ∈ {{0.1, 0.3, 1}} × m_loco ∈ {{10, 30, 100}}) gives B2 q = {ph['B2']['q']:g} ({ph['B2']['med']:.3f} in), "
          f"B2′ q = {ph['B2p']['q']:g}, T_b = {ph['B2p']['tb']:g} s, σ_b = {ph['B2p']['sb']:g} in ({ph['B2p']['med']:.3f} in), "
          f"V1 σ_v = {ph['V1']['sv']:g} (gain vs that B2′ {pct(ph['V1_gain_vs_B2p'], 2)}), V2 multipliers {'/'.join(f'{x:g}' for x in ph['V2']['mult'][1:])} "
          f"(gain {pct(ph['V2_gain_vs_B2p'], 2)}). Pre-registered grid, for comparison: V1 {pct(1 - tu['V1']['med'] / tu['B2p']['med'], 2)}, V2 {pct(1 - tu['V2']['med'] / tu['B2p']['med'], 2)} on the tuning night.")
        A("")
    # ---------------- V3
    A("## 4. V3 gate diagnostic (tuning night)")
    A("")
    A(f"![v3]({rel(figs['v3'])})")
    A("")
    A("| Animal | turn pairs | Spearman ρ | p | Theil–Sen Δψ_W on Δψ_I | Theil–Sen Δψ_I on Δψ_W |")
    A("|---|---|---|---|---|---|")
    for a in animals:
        r = v3[a]
        A(f"| {a} | {r['n']} | {fnum(r['rho'], 3)} | {r.get('p', np.nan):.1e} | {fnum(r.get('slope_w_on_i', np.nan), 3)} | {fnum(r.get('slope_i_on_w', np.nan), 3)} |")
    A("")
    A(f"Gate: ρ ≥ 0.5 in {res['n_v3']} of 5 animals → **{'V3 continues' if res['v3_gate'] else 'V3 skipped: over one second of running, the head turn does not constrain the path turn well enough to aid the smoother'}**.")
    A("")
    # ---------------- test night results
    A("## 5. Test night 2026-09-10/11 — held-out results")
    A("")
    A(f"![heldout]({rel(figs['heldout'])})")
    A("")
    for s, title in (("a", "(a) runs of 4–8 hidden fixes"), ("a2", "(a′) hidden 2-s windows")):
        A(f"**{title}** — median error (in) per animal and Δ vs B2′ [95 % CI]:")
        A("")
        A("| Animal | scored | B1 | B2 | B2′ | V1 | V2 | Δ B1 | Δ B2 | Δ V1 | Δ V2 | Δ V1 +1 h | Δ V2 +1 h |")
        A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for who in animals + ["pooled"]:
            md = {m: summ.get((m, s), {}).get(who, {}).get("med", np.nan) for m in ("B1", "B2", "B2p", "V1", "V2")}
            n_ = summ.get(("B2p", s), {}).get(who, {}).get("n", 0)
            A(f"| {who} | {n_:,} | " + " | ".join(fnum(md[m]) for m in ("B1", "B2", "B2p", "V1", "V2")) + " | " +
              " | ".join(dstr(cget(s, "all", m, who)) for m in ("B1", "B2", "V1", "V2", "V1_shift", "V2_shift")) + " |")
        A("")
        A("By IMU state (pooled; Δ vs B2′ [CI]; n = scored fixes):")
        A("")
        A("| Subset | n | B2′ median (in) | Δ B1 | Δ B2 | Δ V1 | Δ V2 | Δ V1 +1 h | Δ V2 +1 h |")
        A("|---|---|---|---|---|---|---|---|---|")
        for sub in ("still", "moving", "loco"):
            r0 = cget(s, sub, "V1", "pooled")
            A(f"| {sub} | {int(r0['n']) if r0 is not None else 0:,} | {fnum(r0['med_ref']) if r0 is not None else '–'} | " +
              " | ".join(dstr(cget(s, sub, m, "pooled")) for m in ("B1", "B2", "V1", "V2", "V1_shift", "V2_shift")) + " |")
        A("")
        A("RMSE-based Δ vs B2′ (pooled, all scored fixes): " + "; ".join(
            f"{LABEL[m]} {pct(cget(s, 'all', m, 'pooled')['d_rmse'])} [{pct(cget(s, 'all', m, 'pooled')['rmse_lo'])}, {pct(cget(s, 'all', m, 'pooled')['rmse_hi'])}]"
            for m in ("B1", "B2", "V1", "V2") if cget(s, "all", m, "pooled") is not None) + ".")
        A("")
    A(f"![example]({rel(figs['example'])})")
    A("")
    A("The example (x and y against time, full data, one animal of the test night; green = IMU-still) is chosen by a fixed rule: the first 4-min stretch with ≥ 60 s IMU-still and ≥ 20 s IMU-locomoting.")
    A("")
    # ---------------- static references
    A("## 6. Static references (position-only methods, full data)")
    A("")
    A("| Reference | tag | window | fixes | method | bias (in) | RMSE (in) | p50 (in) | p90 (in) |")
    A("|---|---|---|---|---|---|---|---|---|")
    for (ref, tag, win), g in static_df.groupby(["reference", "tag", "window"], sort=False):
        for r in g.itertuples():
            A(f"| {ref} | {tag} | {win} | {r.n:,} | {LABEL.get(r.method, r.method)} | {r.bias_in:.2f} | {r.rmse_in:.2f} | {r.p50_in:.2f} | {r.p90_in:.2f} |")
    A("")
    c1 = static_df[static_df.reference.str.startswith("cohort-1")]
    if len(c1):
        pv = c1.groupby("method")[["rmse_in", "p90_in", "bias_in"]].median()
        A("Cohort-1 fixed tags, median over the 6 tags: " + "; ".join(f"{LABEL.get(m, m)} RMSE {pv.loc[m, 'rmse_in']:.2f} in, p90 {pv.loc[m, 'p90_in']:.2f} in"
                                                                     for m in ("raw", "B1", "B2", "B2p_p", "B2p") if m in pv.index) + ".")
        A("")
    A("Truth = the raw median position of the window (the cohort-1 fixed-test convention), so the bias column only shows how far the smoothed track's *mean* sits from the raw *median*. The implant lay in the CH07 box under huddling rats (worst-case in-house placement; accuracy report §5.2); only its quiet windows are scored. The cohort-1 tags use the cohort-3 per-anchor noise table (transfer; different anchor layout and mounting). B2′ (p only) is the head-position output of B2′; B2′ (p + b) the expected measurement.")
    A("")
    # ---------------- plausibility
    A("## 7. Track plausibility (test night, full data)")
    A("")
    A("| Animal | method | v p50 | v p95 | v p99 (in/s) | v > 60 in/s | a p99 (in/s²) | a > 400 in/s² | path (in/h) | beyond wall > 15 in | v during IMU-still p50 / p95 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    pl = plaus.copy()
    pooled = pl.groupby("method", sort=False).median(numeric_only=True).reset_index()
    pooled["animal"] = "median of 5"
    for r in pd.concat([pl, pooled]).itertuples():
        A(f"| {r.animal} | {LABEL.get(r.method, r.method)} | {r.v_p50:.2f} | {r.v_p95:.1f} | {r.v_p99:.1f} | {100 * r.v_frac_gt60:.2f} % | {r.a_p99:.0f} | "
          f"{100 * r.a_frac_gt400:.2f} % | {r.path_in_per_h:,.0f} | {100 * r.wall_out_frac:.3f} % | {r.v_still_p50:.2f} / {r.v_still_p95:.2f} |")
    A("")
    A("Speed during IMU-still seconds is circular for V1/V2 (they use the IMU-still class) and is reported only. Path length depends on the smoothing scale (Noonan et al. 2019), so no method's distance is 'the true distance'.")
    A("")
    # ---------------- caveats
    A("## 8. Caveats")
    A("")
    A("- **One test night, five animals, regime B.** 2026-09-10/11: colour sampling in the boxes; SF12's headstage-connector problem that night affects its ephys only (the IMU flags decide here). Regime A and the post-09-11 population are not covered.")
    A("- **The held-out target is a WISER fix**, which includes WISER's slow drift; (a) therefore rewards predicting the drift as well as the head. The static references (§6) test position against a constant truth, but only for tags that did not move.")
    A("- **WISER's internal filtering is unknown**; if the engine already smooths at rest, part of the stillness information is already in the fixes.")
    A("- **Per-anchor noise comes from IMU-still bouts** (the head still; a slightly moving body can inflate it) and is applied unchanged to moving fixes; UWB error while moving may differ (body shadowing).")
    A(f"- **B2′'s 'drift' is not a faithful drift model.** The tuned σ_b = {tu['B2p']['sb']:g} in (T_b = {tu['B2p']['tb']:g} s) is larger than the slow component the within-bout autocorrelation implies (9-anchor acf ≈ 0.16 x / 0.08 y at 1 s, i.e. a slow share of ~10–15 % of the variance), and σ_b exceeds the 9-anchor σ, so the white part sits at its 25 % floor. The extra state acts as a flexible low-frequency term that also absorbs part of real head motion: B2′'s position output p is smoother than B2's (§7) and should not be used for speed or distance without its own validation. For (a)/(a′) this does not matter (the target is p + b); B2′ is simply the best position-only reference found on the pre-registered grid.")
    A("- **ZUPT and process-noise switching are per fix step**; long gaps use the IMU class of the interval midpoint.")
    A("- **The IMU classes are coarse.** 'Still' covers only ~10–20 % of night seconds; the locomotion class has TPR 0.75 / FPR 0.15 against WISER speed; a richer IMU state could change V2, but the tuning-night post-hoc grid (§3) bounds what the present classes can give.")
    for sr in cfg.get("superseded_runs", []):
        A(f"- **Superseded run** `{sr['run_dir']}`: {sr['note']}")
    A("- **B1's held-out predictor** (median of the 7 nearest visible fixes) is the natural held-out form of the library's centred 7-sample median; its full-data form is exactly `add_speed`'s.")
    A("- **Deviations from the brief** (declared in the plan before running): control criterion read as 'no significant gain' (CI lower bound ≤ 0); one scored set requiring both the IMU and the +1 h-shifted IMU to be QC-ok; implant windows = the accuracy report's quiet windows (no raw analogin read); the moving-fix condition evaluated pooled; numba for the Kalman loops." + (" V3 passed its gate but is not implemented in this version (deviation)." if res["v3_gate"] else ""))
    A("")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--imu-root", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=None, help="off-repo artifact root (default: output_paths.out_root())")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest())
    if not a.cohort:
        raise SystemExit("--cohort is required (e.g. 2026c)")
    run(a.cohort, a.imu_root, a.output, a.threads)


if __name__ == "__main__":
    main()
