r"""V1b = B2 + a guarded head-IMU zero-velocity constraint (cohort 2026c), tested as its own claim: "B2 in motion, still in
stillness".

Plan: implementation_plan/2026-10-03-wiser-v1b-zupt.md (approved by the user 2026-10-03, "干吧"; step A of A -> B -> C).
Report (full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_v1b_<cohort>.md

  B2        the smoothing pilot's tuned robust constant-velocity Kalman + RTS (q = 3 in^2/s^3, per-fix noise from
            anchors_used, chi2 gate + 2 Huber IRLS passes, k_H = 2.5), rebuilt here by a new kernel that reproduces it
  V1b       B2 + pseudo-measurements 0 = v_x, 0 = v_y at every fix inside a ZUPT interval, sigma_ZUPT = 1.0 in/s, Huber-
            weighted (k_H = 2.5 on |v_smoothed| / sigma_ZUPT) inside the same IRLS passes as the fixes. ZUPT intervals =
            runs of >= 3 consecutive IMU-QC-ok still seconds, eroded by 1 s at each end; release: inside a run, when the
            centred 5-s rolling median of the raw fixes stays >= 12 in from the run's reference (median of its first 5 s)
            for > 5 s, the ZUPT is dropped from the first centre of that stretch to the end of the run. No IMU -> no ZUPT
            -> B2 dynamics in the same filter (no splice).
  sensitivities  V1b-noRelease (no release), V1b-raw (no erosion, no minimum run, Gaussian sigma 0.25 in/s, no release)
Acceptance (pre-registered): E1 identical to B2 in motion (position p99 <= 0.5 in >= 3 s from any ZUPT fix; 1-s speed
p50/p95 within +-5 % of B2 on IMU-locomoting and WISER-fast seconds), E2 S5 onset/offset median per-event lag change within
+-0.5 s, E3 zero jumps. Reported: still metrics (circular), ZUPT coverage, release accounting, false-stillness probe, S1,
S3, NIS of the fixes under B2 / V1b.

Inputs (all read-only): the failure audit's run (tracks/, imu_seconds/, tables/), the WISER fix caches (float64 fixes,
library speed), the default-smoother config (S1/S2/S4/S5 definitions) and run (reproduction only). Existing scripts are
imported, never modified.

Usage:
  python wiser/scripts/analyze_wiser_v1b.py --cohort 2026c [--workers 16]
  python wiser/scripts/analyze_wiser_v1b.py --report-only <run_dir>     # re-aggregate / re-render from the saved tables
  python wiser/scripts/analyze_wiser_v1b.py --selftest                  # synthetic data, no field data
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import wiser_analysis_utils as W  # noqa: E402
import analyze_imu_wiser_calibration as C  # noqa: E402  (helpers; unmodified)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (B2 kernel, anchors noise table, IRLS constants; unmodified)
import analyze_wiser_failure_audit as FA  # noqa: E402  (segment scoring, loaders, block bootstrap)
import analyze_wiser_default_smoother as DS  # noqa: E402  (S1 masks, S2 speeds, S5 events/lags, bootstrap helpers; unmodified)

njit = P.njit

DIRECTION = "wiser_baseline"
NAME = "wiser_v1b"
STEM = f"{DIRECTION}_v1b"
PLAN = "implementation_plan/2026-10-03-wiser-v1b-zupt.md"
KF = ["B2", "V1b", "V1b_nr", "V1b_raw"]
TRACKS = ["raw"] + KF
VARIANTS = ["V1b", "V1b_nr", "V1b_raw"]
ZMASK = {"V1b": "zupt", "V1b_nr": "zupt_nr", "V1b_raw": "zupt_raw"}
LABEL = {"raw": "raw fixes", "B2": "B2 robust CV", "V1b": "V1b (guarded ZUPT)", "V1b_nr": "V1b-noRelease", "V1b_raw": "V1b-raw (original proposal)"}
SHORT = {"raw": "raw", "B2": "B2", "V1b": "V1b", "V1b_nr": "V1b-noRelease", "V1b_raw": "V1b-raw"}
COL = {"raw": "#7f7f7f", "B2": "#2ca02c", "V1b": "#9467bd", "V1b_nr": "#e377c2", "V1b_raw": "#17becf"}
P0_POS, P0_VEL = float(P.P0_POS), float(P.P0_VEL)
E1_EDGES = np.arange(0.0, 20.0 + 1e-9, 0.001)        # V1b-B2 distance histogram (in) for the bootstrap of the p99
PROFILE_BINS = list(range(0, 11))                      # time from the nearest ZUPT fix: [0,1), ..., [9,10), [10, inf) s


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_v1b_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def load_acfg(cfg: dict) -> dict:
    return FA.load_cfg(cfg["_cohort"], str(REPO / cfg["audit_config"]))


def load_dcfg(cfg: dict) -> dict:
    return DS.load_cfg(cfg["_cohort"], str(REPO / cfg["default_smoother_config"]))


_CTX: dict = {}
_SEG: dict = {}


def _ctx(acfg: dict) -> dict:
    if acfg["_path"] not in _CTX:
        _CTX[acfg["_path"]] = FA.context(acfg)
    return _CTX[acfg["_path"]]


def _audit_tables(run: Path) -> dict:
    """Segments (all) and still windows of the audit run, loaded once per process."""
    k = str(run)
    if k not in _SEG:
        S = pd.read_csv(run / "tables" / "segments.csv")
        for c in ("primary", "scored", "ge30"):
            S[c] = S[c].astype(bool)
        Wn = pd.read_csv(run / "tables" / "still_windows.csv.gz")
        _SEG[k] = {"S": S, "W": Wn}
    return _SEG[k]


def kf_specs(tuned: dict, cfg: dict) -> dict:
    """Kalman configurations: B2 (no ZUPT) and the three ZUPT forms on the B2 base."""
    b2 = tuned["B2"]
    v, vr = cfg["v1b"], cfg["variants"]["V1b_raw"]
    base = {"q": float(b2["q"]), "mrej": float(b2["mrej"])}
    return {"B2": {**base, "sv": 0.0, "huber_zupt": False},
            "V1b": {**base, "sv": float(v["sigma_zupt_inps"]), "huber_zupt": bool(v["huber_zupt"])},
            "V1b_nr": {**base, "sv": float(v["sigma_zupt_inps"]), "huber_zupt": bool(v["huber_zupt"])},
            "V1b_raw": {**base, "sv": float(vr["sigma_zupt_inps"]), "huber_zupt": bool(vr["huber_zupt"])}}


# ====================================================================================================== Kalman kernel
@njit(cache=True)
def _kf_v1b(t, z, r2, vis, zupt, q, sv2, huber_zupt, huber_k, m_rej, gate2, n_iter, P_out, V_out, nis_out, wz_out):
    """B2 (robust CV Kalman filter + RTS smoother, two axes coupled only by the outlier weights; the smoothing pilot's
    _kf_rts without drift, same operation order) + an optional zero-velocity pseudo-measurement 0 = v_a (a = x, y) at
    the steps with zupt[k], variance sv2 (in/s)^2. huber_zupt: the pseudo-measurement gets a Huber weight
    w_z = min(1, huber_k / m_z), m_z = |v_smoothed| / sqrt(sv2), updated in the same IRLS passes as the fix weights
    (pass 0 unweighted); else it stays Gaussian. Writes the smoothed p, v (n, 2), the normalised innovation squared of
    each visible fix in the final forward pass with the nominal (unweighted) noise, and the final ZUPT weights."""
    n = t.shape[0]
    xf = np.zeros((n, 2, 2))
    Pf = np.zeros((n, 2, 2, 2))
    xp = np.zeros((n, 2, 2))
    Pp = np.zeros((n, 2, 2, 2))
    dts = np.zeros(n)
    w = np.ones(n)
    wz = np.ones(n)
    F = np.zeros((2, 2))
    FP = np.zeros((2, 2))
    Pi = np.zeros((2, 2))
    Cm = np.zeros((2, 2))
    x = np.zeros(2)
    P_ = np.zeros((2, 2))
    PHt = np.zeros(2)
    dx = np.zeros(2)
    nu = np.zeros(2)
    S = np.zeros(2)
    for k in range(n):
        nis_out[k] = np.nan
        if k > 0:
            dt = t[k] - t[k - 1]
            if dt < 0.0:
                dt = 0.0
            dts[k] = dt
    k0 = 0
    while k0 < n and not vis[k0]:
        k0 += 1
    if k0 == n:
        for k in range(n):
            wz_out[k] = 1.0
            for a in range(2):
                P_out[k, a] = np.nan
                V_out[k, a] = np.nan
        return
    for it in range(n_iter + 1):
        # ---------------- forward filter
        for k in range(n):
            if k == 0:
                for a in range(2):
                    for i in range(2):
                        xp[0, a, i] = 0.0
                        for j in range(2):
                            Pp[0, a, i, j] = 0.0
                    xp[0, a, 0] = z[k0, a]
                    Pp[0, a, 0, 0] = P0_POS
                    Pp[0, a, 1, 1] = P0_VEL
            else:
                dt = dts[k]
                F[0, 0] = 1.0
                F[0, 1] = dt
                F[1, 0] = 0.0
                F[1, 1] = 1.0
                for a in range(2):
                    for i in range(2):
                        s_ = 0.0
                        for j in range(2):
                            s_ += F[i, j] * xf[k - 1, a, j]
                        xp[k, a, i] = s_
                    for i in range(2):
                        for j in range(2):
                            s_ = 0.0
                            for l in range(2):
                                s_ += F[i, l] * Pf[k - 1, a, l, j]
                            FP[i, j] = s_
                    for i in range(2):
                        for j in range(2):
                            s_ = 0.0
                            for l in range(2):
                                s_ += FP[i, l] * F[j, l]
                            Pp[k, a, i, j] = s_
                    Pp[k, a, 0, 0] += q * dt * dt * dt / 3.0
                    Pp[k, a, 0, 1] += q * dt * dt / 2.0
                    Pp[k, a, 1, 0] += q * dt * dt / 2.0
                    Pp[k, a, 1, 1] += q * dt
            use = vis[k] and (it == 0 or w[k] > 0.0)
            infl = 1.0
            if use:
                d2 = 0.0
                for a in range(2):
                    nu[a] = z[k, a] - xp[k, a, 0]
                    hph = Pp[k, a, 0, 0]
                    rr = r2[k, a] if it == 0 else r2[k, a] / w[k]
                    S[a] = hph + rr
                    d2 += nu[a] * nu[a] / S[a]
                if it == 0 and d2 > gate2:
                    infl = d2 / gate2
            if it == n_iter and vis[k]:
                nis = 0.0
                for a in range(2):
                    nn = z[k, a] - xp[k, a, 0]
                    nis += nn * nn / (Pp[k, a, 0, 0] + r2[k, a])
                nis_out[k] = nis
            for a in range(2):
                for i in range(2):
                    x[i] = xp[k, a, i]
                    for j in range(2):
                        P_[i, j] = Pp[k, a, i, j]
                if use:
                    rr = r2[k, a] * infl if it == 0 else r2[k, a] / w[k]
                    for i in range(2):
                        PHt[i] = P_[i, 0]
                    s_ = PHt[0] + rr
                    for i in range(2):
                        x[i] += PHt[i] / s_ * nu[a]
                    for i in range(2):
                        for j in range(2):
                            P_[i, j] -= PHt[i] * PHt[j] / s_
                if zupt[k] and sv2 > 0.0:
                    rz = sv2 if (it == 0 or not huber_zupt) else sv2 / wz[k]
                    for i in range(2):
                        PHt[i] = P_[i, 1]
                    s_ = P_[1, 1] + rz
                    innov = -x[1]
                    for i in range(2):
                        x[i] += PHt[i] / s_ * innov
                    for i in range(2):
                        for j in range(2):
                            P_[i, j] -= PHt[i] * PHt[j] / s_
                for i in range(2):
                    xf[k, a, i] = x[i]
                    for j in range(2):
                        Pf[k, a, i, j] = 0.5 * (P_[i, j] + P_[j, i])
        # ---------------- RTS smoother (means only)
        for a in range(2):
            for i in range(2):
                x[i] = xf[n - 1, a, i]
            P_out[n - 1, a] = x[0]
            V_out[n - 1, a] = x[1]
            for k in range(n - 2, -1, -1):
                dt = dts[k + 1]
                F[0, 0] = 1.0
                F[0, 1] = dt
                F[1, 0] = 0.0
                F[1, 1] = 1.0
                for i in range(2):
                    for j in range(2):
                        P_[i, j] = Pp[k + 1, a, i, j]
                P._inv_small(P_, 2, Pi)
                for i in range(2):
                    for j in range(2):
                        s_ = 0.0
                        for l in range(2):
                            s_ += Pf[k, a, i, l] * F[j, l]
                        FP[i, j] = s_
                for i in range(2):
                    for j in range(2):
                        s_ = 0.0
                        for l in range(2):
                            s_ += FP[i, l] * Pi[l, j]
                        Cm[i, j] = s_
                for i in range(2):
                    dx[i] = x[i] - xp[k + 1, a, i]
                for i in range(2):
                    s_ = xf[k, a, i]
                    for j in range(2):
                        s_ += Cm[i, j] * dx[j]
                    PHt[i] = s_
                for i in range(2):
                    x[i] = PHt[i]
                P_out[k, a] = x[0]
                V_out[k, a] = x[1]
        # ---------------- IRLS weights from the smoothed residuals (fixes) and smoothed velocities (ZUPT)
        if it < n_iter:
            for k in range(n):
                if vis[k]:
                    m2 = 0.0
                    for a in range(2):
                        r = z[k, a] - P_out[k, a]
                        m2 += r * r / r2[k, a]
                    m = math.sqrt(m2)
                    if m <= huber_k:
                        w[k] = 1.0
                    elif m <= m_rej:
                        w[k] = huber_k / m
                    else:
                        w[k] = 0.0
                if huber_zupt and zupt[k] and sv2 > 0.0:
                    mz = math.sqrt((V_out[k, 0] * V_out[k, 0] + V_out[k, 1] * V_out[k, 1]) / sv2)
                    wz[k] = 1.0 if mz <= huber_k else huber_k / mz
    for k in range(n):
        wz_out[k] = wz[k]


def kf_v1b(t, z, r2, vis, zupt, spec: dict, tuned: dict):
    """One smoother run; returns (p (n, 2), v (n, 2), nis (n,), w_zupt (n,))."""
    n = len(t)
    Po, Vo = np.empty((n, 2)), np.empty((n, 2))
    nis, wz = np.empty(n), np.empty(n)
    sv = float(spec.get("sv") or 0.0)
    _kf_v1b(np.ascontiguousarray(t, np.float64), np.ascontiguousarray(z, np.float64), np.ascontiguousarray(r2, np.float64),
            np.ascontiguousarray(vis, np.bool_), np.ascontiguousarray(zupt, np.bool_), float(spec["q"]), sv * sv,
            bool(spec.get("huber_zupt", False)), float(tuned.get("huber_k", P.HUBER_K)), float(spec.get("mrej", 1e9)),
            float(tuned.get("gate2", P.GATE2)), int(tuned.get("n_irls", P.N_IRLS)), Po, Vo, nis, wz)
    return Po, Vo, nis, wz


# ====================================================================================================== ZUPT intervals
def still_runs(still_s: np.ndarray, secs: np.ndarray) -> np.ndarray:
    """(m, 2) absolute seconds [s_a, s_b) of the runs of consecutive IMU-QC-ok still seconds (secs contiguous)."""
    r = C.true_runs(still_s)
    if not r:
        return np.zeros((0, 2))
    return np.array([(float(secs[a]), float(secs[b - 1]) + 1.0) for a, b in r])


def eroded(runs: np.ndarray, min_run_s: float, erode_s: float) -> np.ndarray:
    """Runs of length n >= min_run_s, shortened by erode_s at each end (n - 2 erode_s of ZUPT)."""
    if not len(runs):
        return np.zeros((0, 2))
    L = runs[:, 1] - runs[:, 0]
    keep = L >= min_run_s
    iv = np.column_stack([runs[keep, 0] + erode_s, runs[keep, 1] - erode_s])
    return iv[iv[:, 1] > iv[:, 0]]


def membership(t: np.ndarray, iv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Index of the interval [e0, e1) containing each time (-1: none) and the boolean membership (iv sorted, disjoint)."""
    if not len(iv):
        return np.full(len(t), -1, np.int64), np.zeros(len(t), bool)
    j = np.searchsorted(iv[:, 0], t, side="right") - 1
    jj = np.clip(j, 0, len(iv) - 1)
    inside = (j >= 0) & (t < iv[jj, 1])
    return np.where(inside, j, -1), inside


def release_times(t: np.ndarray, z: np.ndarray, vis: np.ndarray, iv: np.ndarray, rc: dict) -> tuple[np.ndarray, list]:
    """Release time (same clock as t; +inf = none) of every ZUPT interval. Reference r = coordinate-wise median of the
    visible raw fixes in the interval's first ref_s (if fewer than ref_min_fix there: its first ref_min_fix fixes);
    centres c on a grid_s grid in [e0, e1); m(c) = coordinate-wise median of the visible raw fixes in [c - roll_s/2,
    c + roll_s/2) (undefined with < roll_min_fix fixes); release at the first centre of the first run of consecutive
    centres with |m(c) - r| >= dist_in whose span (last - first centre) exceeds min_dur_s."""
    rel = np.full(len(iv), np.inf)
    info = []
    tv, zv = t[vis], z[vis]
    half, step = float(rc["roll_s"]) / 2.0, float(rc["grid_s"])
    need = int(math.floor(float(rc["min_dur_s"]) / step + 1e-9)) + 1       # (n - 1) step > min_dur_s
    for k, (e0, e1) in enumerate(iv):
        i0, i1 = np.searchsorted(tv, [e0, e1])
        if i1 <= i0 or (e1 - e0) <= float(rc["min_dur_s"]):
            continue
        k5 = int(np.searchsorted(tv, e0 + float(rc["ref_s"])) - i0)
        nref = k5 if k5 >= int(rc["ref_min_fix"]) else min(int(rc["ref_min_fix"]), i1 - i0)
        ref = np.median(zv[i0:i0 + nref], axis=0)
        c = np.arange(e0, e1 - 1e-9, step)
        j0, j1 = np.searchsorted(tv, [e0 - half, e1 + half])
        m, _ = FA.roll_median(tv[j0:j1], zv[j0:j1], c, half, int(rc["roll_min_fix"]))
        d = np.hypot(m[:, 0] - ref[0], m[:, 1] - ref[1])
        far = np.nan_to_num(d, nan=-1.0) >= float(rc["dist_in"])
        for a, b in C.true_runs(far):
            if b - a >= need:
                rel[k] = float(c[a])
                info.append({"k": k, "e0": float(e0), "e1": float(e1), "c0": float(c[a]), "c1": float(c[b - 1]), "stretch_s": float(c[b - 1] - c[a]),
                             "dmax_in": float(np.nanmax(d[a:b])), "dmean_in": float(np.nanmean(d[a:b])), "n_ref": int(nref),
                             "ref_x": float(ref[0]), "ref_y": float(ref[1])})
                break
    return rel, info


def zupt_masks(t: np.ndarray, z: np.ndarray, vis: np.ndarray, iv: np.ndarray, rc: dict) -> dict:
    """noRelease / released / final ZUPT fix masks for one set of visible fixes."""
    jv, in_nr = membership(t, iv)
    rel, info = release_times(t, z, vis, iv, rc)
    zu = in_nr.copy()
    zu[in_nr] = t[in_nr] < rel[jv[in_nr]]
    return {"jv": jv, "zupt_nr": in_nr, "zupt": zu, "released": in_nr & ~zu, "rel": rel, "info": info}


def final_intervals(iv: np.ndarray, rel: np.ndarray) -> np.ndarray:
    if not len(iv):
        return np.zeros((0, 2))
    e1 = np.minimum(iv[:, 1], rel)
    f = np.column_stack([iv[:, 0], e1])
    return f[f[:, 1] > f[:, 0]]


def overlap_time(iv: np.ndarray, a: float, b: float) -> float:
    """Total overlap of the sorted disjoint intervals iv with [a, b)."""
    if not len(iv) or b <= a:
        return 0.0
    j0 = int(np.searchsorted(iv[:, 1], a, side="right"))
    j1 = int(np.searchsorted(iv[:, 0], b, side="left"))
    if j1 <= j0:
        return 0.0
    s = iv[j0:j1]
    return float(np.clip(np.minimum(s[:, 1], b) - np.maximum(s[:, 0], a), 0.0, None).sum())


def dist_to_mask(t: np.ndarray, m: np.ndarray) -> np.ndarray:
    """|t - nearest t[m]| (s); +inf when the mask is empty."""
    tm = t[m]
    if not len(tm):
        return np.full(len(t), np.inf)
    j = np.searchsorted(tm, t)
    a = tm[np.clip(j - 1, 0, len(tm) - 1)]
    b = tm[np.clip(j, 0, len(tm) - 1)]
    return np.minimum(np.abs(t - a), np.abs(t - b))


def mark_seconds(secs: np.ndarray, spans_ms: np.ndarray) -> np.ndarray:
    """Seconds [s, s + 1) that overlap any span [a, b) (ms)."""
    m = np.zeros(len(secs) + 1, np.int64)
    if not len(secs) or not len(spans_ms):
        return np.zeros(len(secs), bool)
    s0 = int(secs[0])
    a = np.clip(np.floor(spans_ms[:, 0] / 1000.0).astype(np.int64) - s0, 0, len(secs))
    b = np.clip(np.ceil(spans_ms[:, 1] / 1000.0).astype(np.int64) - s0, 0, len(secs))
    ok = b > a
    np.add.at(m, a[ok], 1)
    np.add.at(m, b[ok], -1)
    return np.cumsum(m)[:-1] > 0


def in_spans(t_ms: np.ndarray, spans_ms: np.ndarray) -> np.ndarray:
    if not len(spans_ms):
        return np.zeros(len(t_ms), bool)
    o = np.argsort(spans_ms[:, 0])
    sp = spans_ms[o]
    j = np.searchsorted(sp[:, 0], t_ms, side="right") - 1
    jj = np.clip(j, 0, len(sp) - 1)
    return (j >= 0) & (t_ms < np.maximum.accumulate(sp[:, 1])[jj])


def house_mask(p: np.ndarray, houses: list, buf: float) -> np.ndarray:
    m = np.zeros(len(p), bool)
    for roi in houses:
        _, inb = W._rect_membership(p[:, 0], p[:, 1], roi, buf)
        m |= inb
    return m


# ====================================================================================================== one animal-period
def process(job: dict) -> dict:
    t_job = time.time()
    cfg, acfg, dcfg = job["cfg"], job["acfg"], job["dcfg"]
    animal, pkey, pi, ai, out = job["animal"], job["pkey"], int(job["pi"]), int(job["ai"]), Path(job["out"])
    ctx = _ctx(acfg)
    tz, tu = ctx["tz"], ctx["tuned"]
    pp = acfg["periods"][pkey]
    lo, hi = C.to_ms(pp["start"], tz), C.to_ms(pp["end"], tz)
    hi_s = (hi - lo) / 1000.0
    base = {"animal": animal, "period": pkey, "set": pp["set"], "kind": pp["kind"]}
    run = Path(cfg["audit_run"])
    mc, trim = acfg["metrics"], float(acfg["still"]["trim_s"])
    s1c, s2c, s4c, s5c = dcfg["s1"], dcfg["s2"], dcfg["s4"], dcfg["s5"]
    zc = cfg["v1b"]
    rc = zc["release"]
    blk_s = float(cfg["bootstrap"]["block_s"])
    tau = float(ctx["taus"][animal])
    houses, buf = ctx["houses"], float(acfg["house_buffer_in"])
    rep = dict(base)
    # ---- inputs: saved audit track (times, anchors, saved B2) + the float64 fixes of the cache
    with np.load(run / "tracks" / f"{animal}_{pkey}.npz") as zf:
        t_ms = zf["t_ms"].astype(np.int64)
        t_al = zf["t_al_ms"].astype(np.float64)
        A = zf["anchors"].astype(np.float64)
        b2_saved = zf["B2"].astype(np.float64)
        raw32 = zf["raw"].astype(np.float64)
    fx = FA.load_fixes(acfg, pkey, animal, lo, hi, tau)
    rep["cache_match"] = bool(len(fx) == len(t_ms) and np.array_equal(fx["t_ms"].to_numpy(np.int64), t_ms))
    if not rep["cache_match"]:
        raise RuntimeError(f"{animal} {pkey}: fix cache rows do not match the audit track")
    z = fx[["x", "y"]].to_numpy(np.float64)
    rep["anchors_match"] = bool(np.array_equal(fx["anchors_used"].to_numpy(np.float64), A))
    rep["raw_vs_saved_max_in"] = float(np.max(np.abs(z - raw32)))
    rep["t_al_maxdiff_ms"] = float(np.max(np.abs(fx["t_al_ms"].to_numpy(np.float64) - t_al)))
    n = len(t_ms)
    t = (t_al - lo) / 1000.0
    t_abs = t_al / 1000.0
    inwin = (t >= 0) & (t < hi_s)
    core = (t >= 60.0) & (t < hi_s - 60.0)
    # ---- per-second IMU states and the analysis mask (default-smoother S2 definition)
    ps = pd.read_csv(run / "imu_seconds" / f"{animal}_{pkey}.csv.gz")
    secs = ps["sec"].to_numpy(np.int64)
    assert np.all(np.diff(secs) == 1), "imu_seconds not contiguous"
    ok_s = ps["ok"].to_numpy(bool)
    still_s = ps["still"].to_numpy(bool) & ok_s
    state = ps["state"].to_numpy(np.int8)
    fsec = np.floor(t_al / 1000.0).astype(np.int64)
    ok_f = DS.lookup(secs, ok_s, fsec, False)
    still_f = DS.lookup(secs, still_s, fsec, False)
    st_f = DS.lookup(secs, state, fsec, np.int8(0))
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    mid = (secs + 0.5) * 1000.0
    amask = ((mid >= lo) & (mid < hi) & ~C.in_any(mid, ctx["handling"]) & ~C.in_any(mid, ctx["silences"]) & (mid >= vf) & (mid < vu))
    am_f = DS.lookup(secs, amask, fsec, False)
    # ---- ZUPT intervals (relative seconds) and masks
    runs_abs = still_runs(still_s, secs)
    iv = (eroded(runs_abs, float(zc["min_run_s"]), float(zc["erode_s"])) * 1000.0 - lo) / 1000.0
    runs_rel = (runs_abs * 1000.0 - lo) / 1000.0
    vis_all = np.ones(n, bool)
    zm = zupt_masks(t, z, vis_all, iv, rc)
    zupt, zupt_nr, released = zm["zupt"], zm["zupt_nr"], zm["released"]
    zupt_raw = still_f.copy()
    fin = final_intervals(iv, zm["rel"])
    rep.update({"n_still_runs": int(len(runs_abs)), "still_s": float((runs_abs[:, 1] - runs_abs[:, 0]).sum()) if len(runs_abs) else 0.0,
                "n_iv": int(len(iv)), "iv_s": float((iv[:, 1] - iv[:, 0]).sum()) if len(iv) else 0.0,
                "final_s": float((fin[:, 1] - fin[:, 0]).sum()) if len(fin) else 0.0, "n_release": int(np.isfinite(zm["rel"]).sum()),
                "n_fix_zupt": int((zupt & inwin).sum()), "n_fix_zupt_nr": int((zupt_nr & inwin).sum()), "n_fix_zupt_raw": int((zupt_raw & inwin).sum()),
                "n_fix_released": int((released & inwin).sum()), "n_fix_win": int(inwin.sum())})
    # ---- smoothers
    r2 = P.r2_from_anchors(A, ctx["table"])
    specs = kf_specs(tu, cfg)
    masks = {"B2": np.zeros(n, bool), "V1b": zupt, "V1b_nr": zupt_nr, "V1b_raw": zupt_raw}
    trk, nis, wz = {"raw": z}, {}, {}
    for m in KF:
        Pk, _, nk, wk = kf_v1b(t, z, r2, vis_all, masks[m], specs[m], tu)
        trk[m], nis[m], wz[m] = Pk, nk, wk
    # ---- reproduction: kernel vs the pilot kernel (float64) and vs the audit's saved B2 (float32)
    Pref, _, _ = P.kf_run(t, z, r2, [vis_all], [np.zeros(n, np.int8)], [np.zeros(n, np.int8)], [{"q": specs["B2"]["q"], "mrej": specs["B2"]["mrej"]}])
    rep["kernel_vs_pilot_B2_max_in"] = float(np.max(np.hypot(*(trk["B2"] - Pref[0]).T)))
    dsv = np.hypot(*(trk["B2"] - b2_saved).T)
    rep["B2_vs_saved_core_max_in"] = float(dsv[core].max()) if core.any() else np.nan
    rep["B2_vs_saved_all_max_in"] = float(dsv.max())
    d = {m: np.hypot(*(trk[m] - trk["B2"]).T) for m in VARIANTS}
    dz = {m: dist_to_mask(t, masks[m]) for m in VARIANTS}
    house_f = house_mask(trk["B2"], houses, buf)
    (out / "tracks").mkdir(exist_ok=True)
    np.savez_compressed(out / "tracks" / f"{animal}_{pkey}.npz", t_ms=t_ms, t_al_ms=t_al, anchors=A.astype(np.int8),
                        **{m: trk[m].astype(np.float32) for m in KF}, zupt=zupt, zupt_nr=zupt_nr, zupt_raw=zupt_raw, released=released,
                        wz_V1b=wz["V1b"].astype(np.float32), wz_V1b_nr=wz["V1b_nr"].astype(np.float32),
                        nis_B2=nis["B2"].astype(np.float32), nis_V1b=nis["V1b"].astype(np.float32),
                        inwin=inwin, amask=am_f, ok=ok_f, still=still_f, state=st_f, house=house_f,
                        **{f"d_{m}": d[m].astype(np.float32) for m in VARIANTS}, **{f"dz_{m}": dz[m].astype(np.float32) for m in VARIANTS})
    rep["wz_V1b_lt1_share"] = float((wz["V1b"][zupt & inwin] < 1.0).mean()) if (zupt & inwin).any() else np.nan
    # ---- certified spans (primary source of the period): windows >= 1 s and segments >= 10 s
    AT = _audit_tables(run)
    psrc = "strict" if pp.get("strict_period") else "s50"
    Sall = AT["S"]
    Sap = Sall[(Sall.animal == animal) & (Sall.period == pkey) & Sall.primary]
    Wp = AT["W"][(AT["W"].animal == animal) & (AT["W"].period == pkey) & (AT["W"].source == psrc)]
    seg_sp = Sap[["t0_ms", "t1_ms"]].to_numpy(float)
    seg30_sp = Sap.loc[Sap.ge30, ["t0_ms", "t1_ms"]].to_numpy(float)
    win_sp = Wp[["t0_ms", "t1_ms"]].to_numpy(float)
    cert_s = mark_seconds(secs, np.vstack([seg_sp, win_sp]) if len(win_sp) else seg_sp)
    cert30_s = mark_seconds(secs, seg30_sp)
    # ---- per-second speeds, library speed, ZUPT coverage of seconds, B2 5-s displacement
    fc = pd.read_csv(Path(cfg["fix_cache_root"]) / pkey / f"{animal}.csv.gz", usecols=["t_ms", "valid", "speed_inps_smooth"])
    marg = float(acfg["fix_cache"]["margin_s"]) * 1000
    fc = fc[(fc.t_ms >= lo - marg) & (fc.t_ms < hi + marg)]
    fv = fc[fc["valid"].astype(bool)]
    s_fix = np.floor((fv["t_ms"].to_numpy(np.float64) - tau * 1000.0) / 1000.0).astype(np.int64)
    u = pd.Series(fv["speed_inps_smooth"].to_numpy(float)).groupby(s_fix).median().reindex(secs).to_numpy(float)
    vsec = {m: DS.second_speeds(t_abs, trk[m], secs, float(s2c["max_gap_s"])).astype(np.float32) for m in TRACKS}
    cs = (secs * 1000.0 + 500.0 - lo) / 1000.0
    zs_v1b = membership(cs, fin)[1]
    zs_nr = membership(cs, iv)[1]
    pa = FA.interp_track(t, trk["B2"], cs - 2.5, 1.0)
    pb = FA.interp_track(t, trk["B2"], cs + 2.5, 1.0)
    D5 = np.hypot(*(pb - pa).T)
    (out / "seconds").mkdir(exist_ok=True)
    np.savez_compressed(out / "seconds" / f"{animal}_{pkey}.npz", sec=secs, state=state, ok=ok_s, still=still_s, mask=amask,
                        u=u.astype(np.float32), cert=cert_s, cert30=cert30_s, zs_V1b=zs_v1b, zs_V1b_nr=zs_nr, D5=D5.astype(np.float32),
                        **{f"v_{m}": v for m, v in vsec.items()})
    # ---- still metrics on the primary >= 30-s certified segments (the audit's own scorer)
    Sj = Sap[Sap.scored & Sap.ge30]
    mrows, frows, evrows, jrows, covrows = [], [], [], [], []
    spd = {m: [] for m in TRACKS}
    spd_idx = {m: [] for m in TRACKS}
    seg_ids = []
    n_bad = 0
    for r in Sj.itertuples():
        ts, te = (r.t0_ms - lo) / 1000.0 + trim, (r.t1_ms - lo) / 1000.0 - trim
        i0, i1 = np.searchsorted(t, [ts, te])
        n_bad += int((i1 - i0) != r.n_fix)
        truth = np.array([r.truth_x, r.truth_y])
        sub = {m: trk[m][i0:i1] for m in TRACKS}
        res, evs, jps, speeds = FA.score_segment(t[i0:i1], sub, truth, ts, te, mc, TRACKS)
        for m in TRACKS:
            mrows.append({"seg_id": r.seg_id, "method": m, **{k: v for k, v in res[m].items() if not k.startswith("_")}})
        fr = {"seg_id": np.repeat(r.seg_id, i1 - i0), "t_al_ms": (lo + t[i0:i1] * 1000).round(1), "anchors": A[i0:i1].astype(int)}
        for m in TRACKS:
            fr[f"r_{m}"] = np.hypot(*(sub[m] - truth).T).round(4)
        frows.append(pd.DataFrame(fr))
        for e in evs:
            evrows.append({"seg_id": r.seg_id, **base, "method": e["method"], "start_ms": lo + (e["c0"] - mc["roll_short_s"] / 2) * 1000,
                           "end_ms": lo + (e["c1"] + mc["roll_short_s"] / 2) * 1000, "dur_s": e["dur_s"], "size_in": e["size_in"],
                           "zone": r.zone, "anchors_med": r.anchors_med})
        for m, kk in jps:
            jrows.append({"seg_id": r.seg_id, **base, "method": m, "t_ms": lo + 0.5 * (t[i0 + kk] + t[i0 + kk + 1]) * 1000,
                          "size_in": float(np.hypot(*(sub[m][kk + 1] - sub[m][kk])))})
        dur = te - ts
        covrows.append({"seg_id": r.seg_id, **base, "dur_trim_s": dur, "zone": r.zone,
                        "cov_V1b": overlap_time(fin, ts, te) / dur, "cov_V1b_nr": overlap_time(iv, ts, te) / dur,
                        "cov_V1b_raw": overlap_time(runs_rel, ts, te) / dur,
                        "fcov_V1b": float(zupt[i0:i1].mean()) if i1 > i0 else np.nan, "fcov_V1b_nr": float(zupt_nr[i0:i1].mean()) if i1 > i0 else np.nan,
                        "fcov_V1b_raw": float(zupt_raw[i0:i1].mean()) if i1 > i0 else np.nan,
                        "released_s": overlap_time(iv, ts, te) - overlap_time(fin, ts, te)})
        seg_ids.append(r.seg_id)
        for m in TRACKS:
            spd[m].append(speeds[m])
            spd_idx[m].append(np.full(len(speeds[m]), len(seg_ids) - 1, np.int32))
    if seg_ids:
        (out / "speeds").mkdir(exist_ok=True)
        np.savez_compressed(out / "speeds" / f"{animal}_{pkey}.npz", seg_ids=np.array(seg_ids),
                            **{m: np.concatenate(spd[m]) for m in TRACKS}, **{f"idx_{m}": np.concatenate(spd_idx[m]) for m in TRACKS})
    rep["n_seg30"] = int(len(Sj))
    rep["n_seg_fixcount_mismatch"] = n_bad
    # ---- releases
    relrows = []
    for e in zm["info"]:
        c0_ms, c1_ms = lo + e["c0"] * 1000.0, lo + e["c1"] * 1000.0
        kc = int(np.clip(np.searchsorted(t, e["c0"]), 0, n - 1))
        k0, k1 = np.searchsorted(t, [e["c0"], e["c1"]])
        relrows.append({**base, "iv_start_ms": lo + e["e0"] * 1000.0, "iv_end_ms": lo + e["e1"] * 1000.0, "iv_s": e["e1"] - e["e0"],
                        "release_ms": c0_ms, "stretch_end_ms": c1_ms, "stretch_s": e["stretch_s"], "released_s": e["e1"] - e["c0"],
                        "dmax_in": e["dmax_in"], "dmean_in": e["dmean_in"], "n_ref": e["n_ref"],
                        "n_fix_dropped": int((released & (zm["jv"] == e["k"])).sum()),
                        "anchors_med": float(np.median(A[k0:k1])) if k1 > k0 else np.nan,
                        "house": bool(house_f[kc]), "in_cert": bool(in_spans(np.array([c0_ms]), seg_sp)[0]),
                        "in_cert30": bool(in_spans(np.array([c0_ms]), seg30_sp)[0]),
                        "in_window": bool(in_spans(np.array([c0_ms]), win_sp)[0]), "in_win_mask": bool(lo <= c0_ms < hi)})
    # ---- E3: jumps over the analysis mask (pair midpoint second) and in the IMU-ok seconds
    j4 = []
    for m in TRACKS:
        jk = FA.find_jumps(t, trk[m], float(s4c["jump_in"]), float(s4c["jump_dt_s"]))
        jk = jk[inwin[jk] & inwin[np.minimum(jk + 1, n - 1)]]
        sj = np.floor((0.5 * (t[jk] + t[jk + 1]) * 1000.0 + lo) / 1000.0).astype(np.int64)
        j4.append({**base, "method": m, "jumps_win": int(len(jk)), "jumps_mask": int(DS.lookup(secs, amask, sj, False).sum()),
                   "jumps_imu_ok": int(DS.lookup(secs, ok_s, sj, False).sum())})
    # ---- E2: S5 onset / offset lags (default-smoother definition)
    erows = []
    for e in DS.transition_events(state, secs, lo, hi, s5c):
        anchor = e["rb"] if e["kind"] == "onset" else e["ra"]
        row = {**base, **e, "block": int(anchor // blk_s)}
        for m in TRACKS:
            row[f"lag_{m}"], row[f"lagloco_{m}"] = DS.event_lag(t, trk[m], e, s5c)
        erows.append(row)
    # ---- S1: held-out fixes (default-smoother masks and seeds); the release sees only the visible fixes
    seed = int(s1c["seed"])
    hid = DS.hidden_masks(n, seed + 100 * pi + ai, seed + 50_000 + 100 * pi + ai, int(s1c["s_every"]))
    s1out = {}
    for sch in ("a", "s"):
        h = hid[sch]
        vis = ~h
        zh = zupt_masks(t, z, vis, iv, rc)
        Pb, _, _, _ = kf_v1b(t, z, r2, vis, masks["B2"], specs["B2"], tu)
        Pv, _, _, _ = kf_v1b(t, z, r2, vis, zh["zupt"], specs["V1b"], tu)
        sc = h & inwin & (A >= float(s1c["min_anchors"])) & ok_f
        s1out[sch] = {"i": np.flatnonzero(sc).astype(np.int32), "block": np.floor(t[sc] / blk_s).astype(np.int32), "still": still_f[sc],
                      "moving": ok_f[sc] & ~still_f[sc], "loco": st_f[sc] == 3, "anchors": A[sc].astype(np.int8),
                      "e_B2": np.hypot(*(z[sc] - Pb[sc]).T).astype(np.float32), "e_V1b": np.hypot(*(z[sc] - Pv[sc]).T).astype(np.float32),
                      "zupt": zh["zupt"][sc]}
    (out / "s1").mkdir(exist_ok=True)
    np.savez_compressed(out / "s1" / f"{animal}_{pkey}.npz", **{f"{s}__{k}": v for s, dd in s1out.items() for k, v in dd.items()})
    rep["runtime_s"] = round(time.time() - t_job, 1)
    return {"rep": rep, "metrics": pd.DataFrame(mrows), "fixes": pd.concat(frows, ignore_index=True) if frows else pd.DataFrame(),
            "events": pd.DataFrame(evrows), "jumps": pd.DataFrame(jrows), "coverage": pd.DataFrame(covrows), "releases": pd.DataFrame(relrows),
            "e3": pd.DataFrame(j4), "s5": pd.DataFrame(erows)}


def _process_safe(job: dict) -> dict:
    try:
        return process(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


def _warm() -> None:
    """Compile (or load the cached) kernel before the pool starts."""
    t = np.arange(20, dtype=float) * 0.2
    z = np.zeros((20, 2))
    kf_v1b(t, z, np.ones((20, 2)), np.ones(20, bool), np.ones(20, bool), {"q": 3.0, "sv": 1.0, "huber_zupt": True, "mrej": 1e9}, {})


# ====================================================================================================== compute run
def run_compute(cfg: dict, workers: int) -> Path:
    t0 = time.time()
    acfg, dcfg = load_acfg(cfg), load_dcfg(cfg)
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    (out / "tables").mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; audit run {cfg['audit_run']}; numba {P.HAVE_NUMBA}")
    _warm()
    jobs = [{"cfg": cfg, "acfg": acfg, "dcfg": dcfg, "animal": a, "pkey": pk, "out": str(out), "pi": pi, "ai": ai}
            for pi, pk in enumerate(acfg["periods"]) for ai, a in enumerate(acfg["animals"])]
    res = []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                continue
            rp = r["rep"]
            log_to(fh, f"{rp['animal']} {rp['period']}: {rp['n_fix_win']:,} window fixes, ZUPT fixes {rp['n_fix_zupt']:,} (noRelease {rp['n_fix_zupt_nr']:,}, "
                       f"raw {rp['n_fix_zupt_raw']:,}), releases {rp['n_release']}, kernel vs pilot B2 {rp['kernel_vs_pilot_B2_max_in']:.2e} in, "
                       f"vs saved B2 (core) {rp['B2_vs_saved_core_max_in']:.2e} in, {rp['runtime_s']} s")
            res.append(r)
    if len(res) != len(jobs):
        log_to(fh, f"WARNING: {len(jobs) - len(res)} jobs failed")
    tb = out / "tables"
    pd.DataFrame([r["rep"] for r in res]).to_csv(tb / "reproduction_tracks.csv", index=False)
    for key, f in (("metrics", "still_metrics.csv.gz"), ("fixes", "still_fixes.csv.gz"), ("events", "still_events.csv"), ("jumps", "still_jumps.csv"),
                   ("coverage", "zupt_coverage_segments.csv.gz"), ("releases", "releases.csv"), ("e3", "e3_motion_jumps.csv"), ("s5", "e2_events.csv.gz")):
        parts = [r[key] for r in res if r[key] is not None and len(r[key])]
        (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()).to_csv(tb / f, index=False)
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "audit_config": cfg["audit_config"], "audit_run": cfg["audit_run"],
            "default_smoother_config": cfg["default_smoother_config"], "default_smoother_run": cfg["default_smoother_run"],
            "smoothing_config": cfg["smoothing_config"], "fix_cache_root": cfg["fix_cache_root"], "git_commit": C.git_commit(),
            "audit_run_manifest": json.loads((Path(cfg["audit_run"]) / "run_manifest.json").read_text(encoding="utf-8")),
            "default_smoother_run_manifest": json.loads((Path(cfg["default_smoother_run"]) / "run_manifest.json").read_text(encoding="utf-8")),
            "tuned_B2": _ctx(acfg)["tuned"]["B2"], "irls": {k: _ctx(acfg)["tuned"][k] for k in ("huber_k", "gate2", "n_irls")},
            "v1b": cfg["v1b"], "variants": cfg["variants"], "numba": P.HAVE_NUMBA, "workers": workers,
            "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    fh.close()
    return out


# ====================================================================================================== evaluators
def e1a_eval(d: np.ndarray, dz: np.ndarray, base_mask: np.ndarray, min_dist_s: float, thr_in: float) -> dict:
    """E1a: p99 of the V1b-B2 distance over base-mask fixes >= min_dist_s from the nearest ZUPT fix; pass if <= thr_in."""
    sel = base_mask & (dz >= min_dist_s)
    x = d[sel]
    if not len(x):
        return {"n": 0, "p50": np.nan, "p95": np.nan, "p99": np.nan, "max": np.nan, "pass": True}
    q = np.percentile(x, [50, 95, 99])
    return {"n": int(len(x)), "p50": float(q[0]), "p95": float(q[1]), "p99": float(q[2]), "max": float(x.max()), "pass": bool(q[2] <= thr_in)}


def e1b_eval(v_m: np.ndarray, v_ref: np.ndarray, max_rel: float) -> dict:
    """E1b: p50 and p95 of the method's 1-s speeds within +-max_rel of the reference's (paired seconds)."""
    ok = np.isfinite(v_m) & np.isfinite(v_ref)
    a, b = np.percentile(v_m[ok], [50, 95]), np.percentile(v_ref[ok], [50, 95])
    dq = a / b - 1.0
    return {"d_p50": float(dq[0]), "d_p95": float(dq[1]), "pass": bool(np.all(np.abs(dq) <= max_rel))}


def e2_eval(lag_m: np.ndarray, lag_ref: np.ndarray, max_abs: float) -> dict:
    dl = np.asarray(lag_m, float) - np.asarray(lag_ref, float)
    ok = np.isfinite(dl)
    med = float(np.median(dl[ok])) if ok.any() else np.nan
    return {"n_paired": int(ok.sum()), "dlag_med": med, "pass": bool(np.isfinite(med) and abs(med) <= max_abs)}


def e3_eval(t: np.ndarray, p: np.ndarray, jump_in: float, dt_s: float) -> dict:
    nj = int(len(FA.find_jumps(t, p, jump_in, dt_s)))
    return {"jumps": nj, "pass": nj == 0}



def e1b_table(SE: pd.DataFrame, sets: list, thr: float, nb: int, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    """E1b (default-smoother S2 machinery): 1-s speed quantiles per set x subset x method and the change vs B2 with paired
    block-bootstrap CIs. Subsets loco / wfast decide; wfast_nonstill (wfast without the IMU-still seconds) is reported."""
    pil = SE["ok"].astype(bool) & SE["still"].astype(bool)
    wf = SE["mask"].astype(bool) & (SE["u"].fillna(-1) >= thr)
    subsets = {"loco": SE["state"] == 3, "wfast": wf, "wfast_nonstill": wf & ~pil}
    rows, cdf = [], {}
    for s in sets:
        for subn, cond in subsets.items():
            dd = SE[(SE.set == s) & cond & SE["paired"]]
            blk, K = DS.block_codes(dd["animal"], dd["period"], dd["block"])
            cnt = FA.boot_counts(K, nb, rng)
            qb = {m: DS.hist_boot_q(dd[f"v_{m}"].to_numpy(float), blk, cnt, FA.SPEED_EDGES, [0.5, 0.95]) for m in TRACKS}
            ex = {m: np.percentile(dd[f"v_{m}"].to_numpy(float), [50, 95]) for m in TRACKS}
            for m in TRACKS:
                row = {"set": s, "subset": subn, "method": m, "n_sec": int(len(dd)), "n_blocks": K, "imu_fail_share": float((~dd["ok"].astype(bool)).mean()),
                       "imu_still_share": float((dd["ok"].astype(bool) & dd["still"].astype(bool)).mean()),
                       "p50": float(ex[m][0]), "p95": float(ex[m][1]), "p50_B2": float(ex["B2"][0]), "p95_B2": float(ex["B2"][1])}
                for qi, qn in enumerate(("p50", "p95")):
                    row[f"d_{qn}"] = float(ex[m][qi] / ex["B2"][qi] - 1.0)
                    b = qb[m][1:, qi] / qb["B2"][1:, qi] - 1.0
                    row[f"d_{qn}_lo"] = float(np.nanpercentile(b, 2.5))
                    row[f"d_{qn}_hi"] = float(np.nanpercentile(b, 97.5))
                rows.append(row)
            if subn == "loco":
                cdf[s] = {m: np.sort(dd[f"v_{m}"].to_numpy(float))[:: max(1, len(dd) // 4000)] for m in TRACKS}
    return pd.DataFrame(rows), cdf


def e2_table(EV: pd.DataFrame, sets: list, max_abs: float, nb: int, rng: np.random.Generator) -> pd.DataFrame:
    """S5 lags per set x kind x periods x method: median lag, paired median change vs B2 with a block-bootstrap CI, and
    which events changed (B2's threshold crossing inside the IMU-still run: onset lag < 0, offset lag > 0)."""
    rows = []
    for s in sets:
        for kind in ("onset", "offset"):
            for per in ("all", "night", "day"):
                dd = EV[(EV.set == s) & (EV.kind == kind)]
                if per != "all":
                    dd = dd[dd["period"].str.startswith(per)]
                if not len(dd):
                    continue
                blk, K = DS.block_codes(dd["animal"], dd["period"], dd["block"])
                cnt = FA.boot_counts(K, nb, rng)
                lb = dd["lag_B2"].to_numpy(float)
                inside = (lb < 0) if kind == "onset" else (lb > 0)
                for m in TRACKS:
                    lag = dd[f"lag_{m}"].to_numpy(float)
                    row = {"set": s, "kind": kind, "periods": per, "method": m, "n_events": int(len(dd)), "n_defined": int(np.isfinite(lag).sum()),
                           "lag_med": float(np.nanmedian(lag)) if np.isfinite(lag).any() else np.nan,
                           "n_B2_only": int((np.isfinite(lb) & ~np.isfinite(lag)).sum()), "n_m_only": int((~np.isfinite(lb) & np.isfinite(lag)).sum())}
                    ev_ = e2_eval(lag, lb, max_abs)
                    row.update({"n_paired": ev_["n_paired"], "dlag_med": ev_["dlag_med"], "pass": ev_["pass"]})
                    dl = lag - lb
                    ok = np.isfinite(dl)
                    ch = ok & (np.abs(np.nan_to_num(dl)) > 1e-9)
                    row.update({"n_changed": int(ch.sum()), "n_changed_B2_inside_run": int((ch & inside).sum()),
                                "n_changed_later": int((ch & (np.nan_to_num(dl) > 0)).sum()), "n_changed_earlier": int((ch & (np.nan_to_num(dl) < 0)).sum()),
                                "dlag_med_changed": float(np.median(dl[ch])) if ch.any() else np.nan,
                                "n_paired_B2_inside_run": int((ok & inside).sum())})
                    if ok.sum() >= 5:
                        wb = DS.wmedian_boot(dl[ok], blk[ok], cnt)
                        row.update({"dlag_lo": float(np.nanpercentile(wb[1:], 2.5)), "dlag_hi": float(np.nanpercentile(wb[1:], 97.5)),
                                    "dlag_mean": float(np.mean(dl[ok])), "share_changed": float(ch.sum() / ok.sum())})
                    rows.append(row)
    return pd.DataFrame(rows)

# ====================================================================================================== aggregation
def _read_npz_dir(d: Path, keys: list | None = None) -> pd.DataFrame:
    parts = []
    for f in sorted(d.glob("*.npz")):
        a, pk = f.stem.split("_", 1)
        with np.load(f) as z:
            ks = keys or [k for k in z.files if z[k].ndim == 1]
            dd = pd.DataFrame({k: z[k] for k in ks})
        dd.insert(0, "period", pk)
        dd.insert(0, "animal", a)
        parts.append(dd)
    return pd.concat(parts, ignore_index=True)


def aggregate(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    acfg, dcfg = load_acfg(cfg), load_dcfg(cfg)
    tb = out / "tables"
    bc = cfg["bootstrap"]
    nb = int(bc["n_boot"])
    rngs = {k: np.random.default_rng(int(bc["seed"]) + i) for i, k in enumerate(("e1a", "e1b", "e2", "still", "s1", "nis"))}
    acc = cfg["acceptance"]
    sets = ["calm", "rain"]
    pset = {k: v["set"] for k, v in acfg["periods"].items()}
    pkind = {k: v["kind"] for k, v in acfg["periods"].items()}
    lo_map = {k: C.to_ms(v["start"], acfg["tz"]) for k, v in acfg["periods"].items()}
    A: dict = {"cfg": cfg, "acfg": acfg}
    rep_tr = pd.read_csv(tb / "reproduction_tracks.csv")
    A["rep_tr"] = rep_tr
    # ---------------- per-fix arrays
    keys = ["t_al_ms", "anchors", "inwin", "amask", "ok", "still", "state", "house", "zupt", "zupt_nr", "zupt_raw", "released",
            "nis_B2", "nis_V1b", "wz_V1b"] + [f"d_{m}" for m in VARIANTS] + [f"dz_{m}" for m in VARIANTS]
    FX = _read_npz_dir(out / "tracks", keys)
    FX["set"] = FX["period"].map(pset)
    FX["kind"] = FX["period"].map(pkind)
    FX["block"] = ((FX["t_al_ms"] - FX["period"].map(lo_map)) // (float(bc["block_s"]) * 1000.0)).astype(np.int64)
    base = FX["inwin"].astype(bool) & FX["amask"].astype(bool) & FX["ok"].astype(bool) & ~FX["still"].astype(bool)
    # ---------------- E1a (+ variants) and the distance profile
    rows, prof = [], []
    for m in VARIANTS:
        for s in sets:
            sm = (FX["set"] == s).to_numpy()
            dm, dzm = FX[f"d_{m}"].to_numpy(float), FX[f"dz_{m}"].to_numpy(float)
            r = e1a_eval(dm, dzm, base.to_numpy() & sm, float(acc["E1a_min_dist_to_zupt_s"]), float(acc["E1a_p99_max_in"]))
            sel = base.to_numpy() & sm & (dzm >= float(acc["E1a_min_dist_to_zupt_s"]))
            if sel.sum() >= 20:
                blk, K = DS.block_codes(FX["animal"].to_numpy()[sel], FX["period"].to_numpy()[sel], FX["block"].to_numpy()[sel])
                cnt = FA.boot_counts(K, nb, rngs["e1a"])
                qb = DS.hist_boot_q(dm[sel], blk, cnt, E1_EDGES, [0.99])[:, 0]
                r.update({"p99_lo": float(np.nanpercentile(qb[1:], 2.5)), "p99_hi": float(np.nanpercentile(qb[1:], 97.5)), "n_blocks": K})
            r.update({"method": m, "set": s, "n_base": int((base.to_numpy() & sm).sum()),
                      "share_ge_min_dist": float(sel.sum() / max((base.to_numpy() & sm).sum(), 1))})
            rows.append(r)
            bm = base.to_numpy() & sm
            for b0 in PROFILE_BINS:
                b1 = b0 + 1 if b0 < PROFILE_BINS[-1] else np.inf
                ss = bm & (dzm >= b0) & (dzm < b1)
                x = dm[ss]
                prof.append({"method": m, "set": s, "dz_lo": b0, "dz_hi": b1, "n": int(len(x)),
                             "p50": float(np.percentile(x, 50)) if len(x) else np.nan, "p95": float(np.percentile(x, 95)) if len(x) else np.nan,
                             "p99": float(np.percentile(x, 99)) if len(x) else np.nan, "max": float(x.max()) if len(x) else np.nan})
    E1a = pd.DataFrame(rows)
    E1a.to_csv(tb / "e1a_position.csv", index=False)
    PROF = pd.DataFrame(prof)
    PROF.to_csv(tb / "e1_profile.csv", index=False)
    log_to(fh, f"E1a done ({time.time() - t0:.0f} s)")
    # ---------------- ZUPT weights, fix shares
    zstats = {}
    for s in sets:
        g = FX[(FX["set"] == s) & FX["inwin"].astype(bool)]
        zz = g["zupt"].astype(bool)
        zstats[s] = {"n_fix_win": int(len(g)), "zupt_share": float(zz.mean()), "zupt_nr_share": float(g["zupt_nr"].astype(bool).mean()),
                     "zupt_raw_share": float(g["zupt_raw"].astype(bool).mean()), "released_share": float(g["released"].astype(bool).mean()),
                     "wz_lt1_share": float((g.loc[zz, "wz_V1b"] < 1.0).mean()) if zz.any() else np.nan,
                     "wz_p01": float(np.percentile(g.loc[zz, "wz_V1b"], 1)) if zz.any() else np.nan}
    A["zstats"] = zstats
    # ---------------- NIS
    nr = []
    pop = FX["inwin"].astype(bool) & FX["amask"].astype(bool)
    G = FX[pop].copy()
    G["abin"] = FA.anchor_bin(G["anchors"].to_numpy())
    G["zone"] = np.where(G["house"].astype(bool), "house", "outside")
    G["imu"] = np.where(~G["ok"].astype(bool), "QC failed", G["state"].map({1: "still", 2: "active", 3: "locomoting"}).fillna("QC failed"))
    q95 = float(cfg["nis"]["chi2_2_q95"])
    for m in ("B2", "V1b"):
        col = f"nis_{m}"
        for by in (["set", "abin", "zone", "imu"], ["set", "abin", "zone"], ["set", "abin"], ["set", "zone"], ["set", "imu"], ["set"], ["set", "anchors"]):
            g = G.dropna(subset=[col]).groupby(by)[col]
            t_ = pd.DataFrame({"n": g.size(), "mean": g.mean(), "median": g.median(), "gt95": g.apply(lambda x: float((x > q95).mean()))}).reset_index()
            t_.insert(0, "by", "×".join(by))
            t_.insert(0, "method", m)
            nr.append(t_)
    NIS = pd.concat(nr, ignore_index=True)
    NIS.to_csv(tb / "nis.csv", index=False)
    del G
    del FX
    log_to(fh, f"NIS done ({time.time() - t0:.0f} s)")
    # ---------------- E1b (S2 machinery) + false-still probe
    SE = _read_npz_dir(out / "seconds")
    SE["set"] = SE["period"].map(pset)
    SE["kind"] = SE["period"].map(pkind)
    SE["block"] = ((SE["sec"] * 1000.0 - SE["period"].map(lo_map)) // (float(bc["block_s"]) * 1000.0)).astype(np.int64)
    vcols = [f"v_{m}" for m in TRACKS]
    SE["paired"] = np.isfinite(SE[vcols].to_numpy(float)).all(axis=1)
    E1b, cdf = e1b_table(SE, sets, float(dcfg["s2"]["wiser_speed_thr_inps"]), nb, rngs["e1b"])
    E1b.to_csv(tb / "e1b_speed.csv", index=False)
    A["cdf"] = cdf
    # false-stillness probe
    fs = []
    pil = SE["ok"].astype(bool) & SE["still"].astype(bool) & SE["mask"].astype(bool)
    groups = {"pilot-still, outside every certified window/segment": pil & ~SE["cert"].astype(bool),
              "pilot-still, inside a certified window/segment": pil & SE["cert"].astype(bool),
              "IMU-locomoting": SE["mask"].astype(bool) & (SE["state"] == 3),
              "IMU-active": SE["mask"].astype(bool) & (SE["state"] == 2)}
    for s in sets + ["all"]:
        ss = (SE.set == s) if s != "all" else np.ones(len(SE), bool)
        npil = int((pil & ss).sum())
        for gname, gm in groups.items():
            g = SE[gm & ss]
            x = g["D5"].to_numpy(float)
            x = x[np.isfinite(x)]
            fs.append({"set": s, "group": gname, "n_s": int(len(g)), "share_of_pilot_still": (len(g) / npil) if "pilot" in gname and npil else np.nan,
                       "n_D5": int(len(x)), "D5_p50": float(np.percentile(x, 50)) if len(x) else np.nan,
                       "D5_p90": float(np.percentile(x, 90)) if len(x) else np.nan, "D5_p99": float(np.percentile(x, 99)) if len(x) else np.nan,
                       "D5_gt6": float((x > 6).mean()) if len(x) else np.nan, "D5_ge12": float((x >= 12).mean()) if len(x) else np.nan,
                       "zupt_V1b_share": float(g["zs_V1b"].astype(bool).mean()) if len(g) else np.nan,
                       "zupt_V1b_nr_share": float(g["zs_V1b_nr"].astype(bool).mean()) if len(g) else np.nan,
                       "zupt_V1b_raw_share": float((g["ok"].astype(bool) & g["still"].astype(bool)).mean()) if len(g) else np.nan})
    FS = pd.DataFrame(fs)
    FS.to_csv(tb / "false_still_probe.csv", index=False)
    del SE
    log_to(fh, f"E1b / probe done ({time.time() - t0:.0f} s)")
    # ---------------- E2 (S5)
    EV = pd.read_csv(tb / "e2_events.csv.gz")
    E2 = e2_table(EV, sets, float(acc["E2_max_abs_dlag_s"]), nb, rngs["e2"])
    E2.to_csv(tb / "e2_lags.csv", index=False)
    log_to(fh, f"E2 done ({time.time() - t0:.0f} s)")
    # ---------------- still metrics (circular) + S3 + coverage
    run = Path(cfg["audit_run"])
    Saud = pd.read_csv(run / "tables" / "segments.csv")
    for c in ("primary", "scored", "ge30"):
        Saud[c] = Saud[c].astype(bool)
    S = Saud[Saud.primary & Saud.scored & Saud.ge30].reset_index(drop=True)
    M = pd.read_csv(tb / "still_metrics.csv.gz")
    F = pd.read_csv(tb / "still_fixes.csv.gz")
    SP = DS.load_speeds_multi(out / "speeds", S, TRACKS)
    pooled = pd.DataFrame([{"set": s, **FA.still_summary(S[S.set == s], M, F, SP, m, S)} for s in sets for m in TRACKS])
    setkind = pd.DataFrame([{"set": s, "kind": k, **FA.still_summary(S[(S.set == s) & (S.kind == k)], M, F, SP, m, S)}
                            for s in sets for k in ("day", "night") for m in TRACKS])
    pooled.to_csv(tb / "still_pooled.csv", index=False)
    setkind.to_csv(tb / "still_setkind.csv", index=False)
    brow = []
    for s in sets:
        gs = S[S.set == s]
        st, cnt, K = {}, None, 0
        for m in TRACKS:
            Ab = FA.block_arrays(gs, M, F, SP, m, S)
            if cnt is None:
                cnt = FA.boot_counts(Ab["K"], nb, rngs["still"])
                K = Ab["K"]
            x = FA.set_stats(Ab, cnt)
            st[m] = {k: x[k] for k in ("path_rate", "rms", "drift_med", "crazy_rate", "jump_rate", "speed_p95")}
        for m in TRACKS:
            for k in st[m]:
                e, lo_, hi_ = FA.ci(st[m][k])
                with np.errstate(divide="ignore", invalid="ignore"):
                    r_, rlo, rhi = FA.ci(st[m][k] / st["B2"][k])
                    d_, dlo, dhi = FA.ci(st[m][k] - st["raw"][k])
                    d2_, d2lo, d2hi = FA.ci(st[m][k] - st["B2"][k])
                brow.append({"set": s, "method": m, "metric": k, "value": e, "lo": lo_, "hi": hi_, "ratio_vs_B2": r_, "ratio_lo": rlo, "ratio_hi": rhi,
                             "diff_vs_raw": d_, "diff_raw_lo": dlo, "diff_raw_hi": dhi, "diff_vs_B2": d2_, "diff_B2_lo": d2lo, "diff_B2_hi": d2hi, "n_blocks": K})
    BS = pd.DataFrame(brow)
    BS.to_csv(tb / "still_bootstrap.csv", index=False)
    S3 = pooled[["set", "method", "crazy_n", "crazy_per_h", "still_h"]].copy()
    b3 = BS[BS.metric == "crazy_rate"][["set", "method", "diff_vs_raw", "diff_raw_lo", "diff_raw_hi", "diff_vs_B2", "diff_B2_lo", "diff_B2_hi"]]
    S3 = S3.merge(b3, on=["set", "method"], how="left")
    S3.to_csv(tb / "s3_excursions.csv", index=False)
    CV = pd.read_csv(tb / "zupt_coverage_segments.csv.gz")
    cov = []
    for s in sets:
        for k in ("all", "day", "night"):
            g = CV[(CV.set == s) & ((CV.kind == k) if k != "all" else True)]
            w_ = g["dur_trim_s"].to_numpy(float)
            row = {"set": s, "kind": k, "n_seg": int(len(g)), "still_h": float(w_.sum() / 3600)}
            for m in VARIANTS:
                row[f"cov_{m}"] = float((g[f"cov_{m}"] * w_).sum() / w_.sum()) if w_.sum() else np.nan
                row[f"fcov_{m}"] = float(np.nanmean(g[f"fcov_{m}"])) if len(g) else np.nan
            row["released_h"] = float(g["released_s"].sum() / 3600)
            row["house_share_h"] = float((g.zone == "house").astype(float).mul(w_).sum() / w_.sum()) if w_.sum() else np.nan
            cov.append(row)
    COV = pd.DataFrame(cov)
    COV.to_csv(tb / "zupt_coverage.csv", index=False)
    # repro of the audit still rows (B2 and raw) on the same segments
    Ma = pd.read_csv(run / "tables" / "segment_metrics.csv.gz")
    Rm = M[M.method.isin(["raw", "B2"])].merge(Ma[Ma.seg_id.isin(set(S.seg_id))], on=["seg_id", "method"], suffixes=("", "_aud"))
    rep_still = {c: float(np.nanmax(np.abs(Rm[c] - Rm[f"{c}_aud"]))) for c in ("rms_in", "drift10_in", "path_in_per_min", "crazy_n", "jumps", "speed_p95")}
    rep_still["n_rows"] = int(len(Rm))
    A["rep_still"] = rep_still
    log_to(fh, f"still tables done ({time.time() - t0:.0f} s)")
    # ---------------- E3
    J3 = pd.read_csv(tb / "e3_motion_jumps.csv")
    E3m = J3.groupby(["set", "kind", "method"])[["jumps_win", "jumps_mask", "jumps_imu_ok"]].sum().reset_index()
    E3m.to_csv(tb / "e3_jumps_by_set.csv", index=False)
    # ---------------- releases
    RL = pd.read_csv(tb / "releases.csv") if (tb / "releases.csv").stat().st_size > 5 else pd.DataFrame()
    rel_sum = []
    for s in sets + ["all"]:
        g = RL[(RL.set == s) if s != "all" else np.ones(len(RL), bool)] if len(RL) else RL
        ch = float(S[(S.set == s) if s != "all" else np.ones(len(S), bool)].dur_trim_s.sum() / 3600)
        zh = float(rep_tr[(rep_tr.set == s) if s != "all" else np.ones(len(rep_tr), bool)].iv_s.sum() / 3600)
        n_all = int(len(g))
        n_in = int(g.in_cert.sum()) if n_all else 0
        n_in30 = int(g.in_cert30.sum()) if n_all else 0
        rel_sum.append({"set": s, "n_release": n_all, "n_in_cert": n_in, "n_in_cert30": n_in30, "n_out_cert": n_all - n_in,
                        "cert30_h": ch, "zupt_iv_h": zh, "in_cert30_per_still_h": n_in30 / ch if ch else np.nan,
                        "per_zupt_h": n_all / zh if zh else np.nan, "released_h": float(g.released_s.sum() / 3600) if n_all else 0.0,
                        "released_in_cert_h": float(g.loc[g.in_cert, "released_s"].sum() / 3600) if n_all else 0.0,
                        "house_share": float(g.house.mean()) if n_all else np.nan,
                        "dmax_med": float(g.dmax_in.median()) if n_all else np.nan})
    RS = pd.DataFrame(rel_sum)
    RS.to_csv(tb / "releases_summary.csv", index=False)
    cl = cfg["cluster"]
    c_ms = C.to_ms(cl["center"], acfg["tz"])
    CL = RL[(RL.period == cl["period"]) & ((RL.release_ms - c_ms).abs() <= 1000 * float(cl["half_window_s"]))] if len(RL) else RL
    CL.to_csv(tb / "releases_cluster.csv", index=False)
    # ---------------- S1
    E = []
    for f in sorted((out / "s1").glob("*.npz")):
        a, pk = f.stem.split("_", 1)
        with np.load(f) as z:
            for sch in ("a", "s"):
                dd = pd.DataFrame({k.split("__", 1)[1]: z[k] for k in z.files if k.startswith(sch + "__")})
                dd.insert(0, "scheme", sch)
                dd.insert(0, "period", pk)
                dd.insert(0, "animal", a)
                E.append(dd)
    E = pd.concat(E, ignore_index=True)
    E["set"] = E["period"].map(pset)
    rows = []
    for s in sets:
        for sch in ("a", "s"):
            d0 = E[(E.set == s) & (E.scheme == sch)]
            for subn in ("moving", "all", "still", "loco"):
                dd = d0 if subn == "all" else d0[d0[subn].astype(bool)]
                if not len(dd):
                    continue
                mb, mv = float(np.median(dd["e_B2"])), float(np.median(dd["e_V1b"]))
                row = {"set": s, "scheme": sch, "subset": subn, "n": int(len(dd)), "med_B2": mb, "med_V1b": mv, "D": 1.0 - mv / mb,
                       "rmse_B2": float(np.sqrt(np.mean(dd["e_B2"].astype(float) ** 2))), "rmse_V1b": float(np.sqrt(np.mean(dd["e_V1b"].astype(float) ** 2))),
                       "zupt_share": float(dd["zupt"].astype(bool).mean())}
                if subn == "moving":
                    blk, K = DS.block_codes(dd["animal"], dd["period"], dd["block"])
                    cnt = FA.boot_counts(K, nb, rngs["s1"])
                    qr = DS.hist_boot_q(dd["e_B2"].to_numpy(float), blk, cnt, DS.S1_EDGES, [0.5])[:, 0]
                    qm = DS.hist_boot_q(dd["e_V1b"].to_numpy(float), blk, cnt, DS.S1_EDGES, [0.5])[:, 0]
                    b = 1.0 - qm[1:] / qr[1:]
                    row.update({"D_lo": float(np.nanpercentile(b, 2.5)), "D_hi": float(np.nanpercentile(b, 97.5)), "n_blocks": K})
                rows.append(row)
    S1 = pd.DataFrame(rows)
    S1.to_csv(tb / "s1_heldout.csv", index=False)
    del E
    log_to(fh, f"S1 done ({time.time() - t0:.0f} s)")
    # ---------------- reproduction vs the default-smoother run
    drun = Path(cfg["default_smoother_run"])
    dsr = {}
    try:
        dev = pd.read_csv(drun / "tables" / "s5_events.csv.gz")
        dsr["events"] = {f"{s} {k}": {"here": int(((EV.set == s) & (EV.kind == k)).sum()), "default_smoother": int(((dev.set == s) & (dev.kind == k)).sum())}
                         for s in sets for k in ("onset", "offset")}
        d5 = pd.read_csv(drun / "tables" / "s5_lags.csv")
        dsr["B2_lag_med"] = {f"{s} {k}": {"here": float(E2[(E2.set == s) & (E2.kind == k) & (E2.periods == "all") & (E2.method == "B2")].lag_med.iloc[0]),
                                          "default_smoother": float(d5[(d5.set == s) & (d5.kind == k) & (d5.periods == "all") & (d5.method == "B2")].lag_med.iloc[0])}
                             for s in sets for k in ("onset", "offset")}
        d2 = pd.read_csv(drun / "tables" / "s2_speed.csv")
        dsr["B2_speed"] = {f"{s} {sub}": {"here": [float(E1b[(E1b.set == s) & (E1b.subset == sub) & (E1b.method == "B2")][q].iloc[0]) for q in ("p50", "p95")],
                                          "default_smoother": [float(d2[(d2.set == s) & (d2.subset == sub) & (d2.method == "B2")][q].iloc[0]) for q in ("p50", "p95")],
                                          "n_here": int(E1b[(E1b.set == s) & (E1b.subset == sub) & (E1b.method == "B2")].n_sec.iloc[0]),
                                          "n_default_smoother": int(d2[(d2.set == s) & (d2.subset == sub) & (d2.method == "B2")].n_sec.iloc[0])}
                           for s in sets for sub in ("loco", "wfast")}
        d1 = pd.read_csv(drun / "tables" / "s1_heldout.csv")
        dsr["B2_s1_med"] = {f"{s} ({sch})": {"here": float(S1[(S1.set == s) & (S1.scheme == sch) & (S1.subset == "moving")].med_B2.iloc[0]),
                                             "default_smoother": float(d1[(d1.set == s) & (d1.scheme == sch) & (d1.subset == "moving") & (d1.method == "B2")].med.iloc[0])}
                            for s in sets for sch in ("a", "s")}
        dp = pd.read_csv(drun / "tables" / "still_pooled.csv")
        dsr["B2_fake_path"] = {s: {"here": float(pooled[(pooled.set == s) & (pooled.method == "B2")].path_in_per_min.iloc[0]),
                                   "default_smoother": float(dp[(dp.set == s) & (dp.method == "B2")].path_in_per_min.iloc[0])} for s in sets}
    except Exception as e:  # noqa: BLE001
        dsr["error"] = f"{type(e).__name__}: {e}"
    A["repro_ds"] = dsr
    # ---------------- verdict
    ver = {}
    for m in VARIANTS:
        e1a = E1a[E1a.method == m]
        e1b = E1b[(E1b.method == m) & E1b.subset.isin(["loco", "wfast"])]
        dq = pd.concat([e1b.d_p50, e1b.d_p95]).abs()
        e2 = E2[(E2.method == m) & (E2.periods == "all")]
        still_j = int(pooled[pooled.method == m].jumps_n.sum())
        mot_j = J3[J3.method == m]
        mot_j_tot = int(mot_j.jumps_mask.sum())
        v = {"E1a": bool(len(e1a) == 2 and e1a["pass"].all()), "E1a_p99": {r.set: float(r.p99) for r in e1a.itertuples()},
             "E1b": bool(len(e1b) == 4 and (dq <= float(acc["E1b_max_rel"])).all()),
             "E1b_worst": float(dq.max()) if len(dq) else np.nan,
             "E2": bool(len(e2) == 4 and e2["pass"].all()), "E2_dlag": {f"{r.set} {r.kind}": float(r.dlag_med) for r in e2.itertuples()},
             "E3": bool(still_j == 0 and mot_j_tot == 0), "E3_still_jumps": still_j, "E3_motion_jumps": mot_j_tot,
             "E3_motion_jumps_by_period": {f"{r.animal} {r.period}": int(r.jumps_mask) for r in mot_j.itertuples() if r.jumps_mask > 0}}
        v["E1"] = v["E1a"] and v["E1b"]
        v["pass_all"] = v["E1"] and v["E2"] and v["E3"]
        v["failed"] = [k for k in ("E1", "E2", "E3") if not v[k]]
        ver[m] = v
    dec = {"V1b_passes": ver["V1b"]["pass_all"], "failed_claims": ver["V1b"]["failed"],
           "default_implanted": "V1b" if ver["V1b"]["pass_all"] else "B2", "universal_baseline": "B2",
           "variants_that_would_pass": [m for m in ("V1b_nr", "V1b_raw") if ver[m]["pass_all"]]}
    A.update({"E1a": E1a, "PROF": PROF, "E1b": E1b, "E2": E2, "EV": EV, "E3m": E3m, "J3": J3, "pooled": pooled, "setkind": setkind, "BS": BS, "S3": S3,
              "COV": COV, "RL": RL, "RS": RS, "CL": CL, "S1": S1, "NIS": NIS, "FS": FS, "ver": ver, "dec": dec, "S": S})
    summ = {"decision": dec, "verdict": ver, "zupt_stats": zstats, "repro_still": rep_still, "repro_default_smoother": dsr,
            "repro_tracks": {"kernel_vs_pilot_B2_max_in": float(rep_tr.kernel_vs_pilot_B2_max_in.max()),
                             "B2_vs_saved_core_max_in": float(rep_tr.B2_vs_saved_core_max_in.max()),
                             "B2_vs_saved_all_max_in": float(rep_tr.B2_vs_saved_all_max_in.max()),
                             "raw_vs_saved_max_in": float(rep_tr.raw_vs_saved_max_in.max()),
                             "cache_match_all": bool(rep_tr.cache_match.all()), "anchors_match_all": bool(rep_tr.anchors_match.all()),
                             "seg_fixcount_mismatch": int(rep_tr.n_seg_fixcount_mismatch.sum()), "n_jobs": int(len(rep_tr))},
            "runtime_aggregate_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=DS._jd), encoding="utf-8")
    A["summary"] = summ
    log_to(fh, f"aggregation done ({time.time() - t0:.0f} s); V1b {'PASSES' if dec['V1b_passes'] else 'FAILS ' + ', '.join(dec['failed_claims'])}; "
               f"default for the implanted animals: {dec['default_implanted']}")
    return A


# ====================================================================================================== figures
def make_figures(A: dict, out: Path, fdir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cohort = A["cfg"]["_cohort"]
    acc = A["cfg"]["acceptance"]
    figs = {}
    # ---- 1. E1 profile
    PROF = A["PROF"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for k, s in enumerate(("calm", "rain")):
        for m, ls in (("V1b", "-"), ("V1b_nr", "--"), ("V1b_raw", ":")):
            g = PROF[(PROF.method == m) & (PROF.set == s)].sort_values("dz_lo")
            xm = g.dz_lo + 0.5
            for q, mk in (("p50", "o"), ("p99", "s"), ("max", "^")):
                if m != "V1b" and q != "p99":
                    continue
                ax[k].plot(xm, np.maximum(g[q], 1e-6), ls=ls, marker=mk, ms=4, color=COL[m], label=f"{SHORT[m]} {q}")
        ax[k].axhline(float(acc["E1a_p99_max_in"]), color="r", lw=1, ls="--")
        ax[k].axvline(float(acc["E1a_min_dist_to_zupt_s"]), color="k", lw=0.8, ls=":")
        ax[k].set_yscale("log")
        ax[k].set_xlabel("time from the nearest ZUPT fix (s; last bin ≥ 10 s)")
        ax[k].set_title(f"{s}: |track − B2| on IMU-ok non-still fixes")
        ax[k].grid(alpha=0.3)
    ax[0].set_ylabel("distance from B2 (in, log)")
    ax[1].legend(fontsize=7)
    fig.suptitle("E1a: V1b equals B2 away from the ZUPT (red: 0.5-in bound for the p99 at ≥ 3 s)")
    fig.tight_layout()
    f = f"{STEM}_e1_profile_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["profile"] = f
    # ---- 2. criteria: E1b speed deltas, E2 lag deltas
    E1b, E2 = A["E1b"], A["E2"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    pts = [(s, sub, q) for s in ("calm", "rain") for sub in ("loco", "wfast") for q in ("p50", "p95")]
    for i, m in enumerate(VARIANTS):
        for j, (s, sub, q) in enumerate(pts):
            r = E1b[(E1b.method == m) & (E1b.set == s) & (E1b.subset == sub)]
            if not len(r):
                continue
            r = r.iloc[0]
            x = j + (i - 1) * 0.22
            ax[0].errorbar(x, 100 * r[f"d_{q}"], yerr=[[max(100 * (r[f"d_{q}"] - r[f"d_{q}_lo"]), 0.0)], [max(100 * (r[f"d_{q}_hi"] - r[f"d_{q}"]), 0.0)]],
                           fmt="o", color=COL[m], ms=4, capsize=2, label=SHORT[m] if j == 0 else None)
    ax[0].axhspan(-100 * float(acc["E1b_max_rel"]), 100 * float(acc["E1b_max_rel"]), color="g", alpha=0.08)
    ax[0].axhline(0, color="k", lw=0.5)
    ax[0].set_xticks(range(len(pts)))
    ax[0].set_xticklabels([f"{s}\n{'loco' if sub == 'loco' else 'fast'}\n{q}" for s, sub, q in pts], fontsize=7)
    ax[0].set_ylabel("Δ 1-s speed quantile vs B2 (%)")
    ax[0].set_title("E1b (pass inside ± 5 %)")
    ax[0].legend(fontsize=7)
    pts2 = [(s, k) for s in ("calm", "rain") for k in ("onset", "offset")]
    for i, m in enumerate(VARIANTS):
        for j, (s, k) in enumerate(pts2):
            r = E2[(E2.method == m) & (E2.set == s) & (E2.kind == k) & (E2.periods == "all")]
            if not len(r):
                continue
            r = r.iloc[0]
            x = j + (i - 1) * 0.22
            lo_, hi_ = r.get("dlag_lo", np.nan), r.get("dlag_hi", np.nan)
            ax[1].errorbar(x, r.dlag_med, yerr=[[max(np.nan_to_num(r.dlag_med - lo_), 0)], [max(np.nan_to_num(hi_ - r.dlag_med), 0)]], fmt="o", color=COL[m], ms=4, capsize=2,
                           label=SHORT[m] if j == 0 else None)
    ax[1].axhspan(-float(acc["E2_max_abs_dlag_s"]), float(acc["E2_max_abs_dlag_s"]), color="g", alpha=0.08)
    ax[1].axhline(0, color="k", lw=0.5)
    ax[1].set_xticks(range(len(pts2)))
    ax[1].set_xticklabels([f"{s}\n{k}" for s, k in pts2])
    ax[1].set_ylabel("median per-event Δ lag vs B2 (s)")
    ax[1].set_title("E2 (pass inside ± 0.5 s)")
    ax[1].legend(fontsize=7)
    fig.suptitle("V1b's identity claim in motion (95 % CIs: 10-min block bootstrap)")
    fig.tight_layout()
    f = f"{STEM}_criteria_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["criteria"] = f
    # ---- 3. still metrics (circular) + coverage
    pooled, BS, COV = A["pooled"], A["BS"], A["COV"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    x = np.arange(len(TRACKS))
    for k, (s, off) in enumerate((("calm", -0.2), ("rain", 0.2))):
        v = [float(pooled[(pooled.set == s) & (pooled.method == m)].path_in_per_min.iloc[0]) for m in TRACKS]
        lo_ = [float(BS[(BS.set == s) & (BS.method == m) & (BS.metric == "path_rate")].lo.iloc[0]) for m in TRACKS]
        hi_ = [float(BS[(BS.set == s) & (BS.method == m) & (BS.metric == "path_rate")].hi.iloc[0]) for m in TRACKS]
        ax[0].bar(x + off, v, 0.38, color=[COL[m] for m in TRACKS], alpha=1.0 if s == "calm" else 0.5, edgecolor="k", lw=0.5,
                  yerr=[np.clip(np.array(v) - np.array(lo_), 0, None), np.clip(np.array(hi_) - np.array(v), 0, None)], capsize=2, label=s)
    ax[0].set_yscale("log")
    ax[0].set_xticks(x)
    ax[0].set_xticklabels([SHORT[m] for m in TRACKS], rotation=20)
    ax[0].set_ylabel("fake path in certified stillness (in/min, log)")
    ax[0].set_title("Still (circular for the ZUPT forms): calm dark, rain light")
    for k, s in enumerate(("calm", "rain")):
        r = COV[(COV.set == s) & (COV.kind == "all")].iloc[0]
        ax[1].bar(np.arange(3) + (k - 0.5) * 0.38, [100 * r[f"cov_{m}"] for m in VARIANTS], 0.38, color=[COL[m] for m in VARIANTS],
                  alpha=1.0 if s == "calm" else 0.5, edgecolor="k", lw=0.5, label=s)
    ax[1].set_xticks(np.arange(3))
    ax[1].set_xticklabels([SHORT[m] for m in VARIANTS])
    ax[1].set_ylabel("share of certified still time with the ZUPT (%)")
    ax[1].set_ylim(0, 100)
    ax[1].set_title("ZUPT coverage of certified stillness")
    fig.tight_layout()
    f = f"{STEM}_still_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["still"] = f
    # ---- 4. NIS
    NIS = A["NIS"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    g = NIS[(NIS.method == "B2") & (NIS.by == "set×abin×zone")]
    for k, s in enumerate(("calm", "rain")):
        for zname, mk in (("house", "o"), ("outside", "s")):
            d0 = g[(g.set == s) & (g.zone == zname)].set_index("abin").reindex(FA.ANCHOR_BINS)
            ax[0].plot(range(4), d0["mean"], marker=mk, ls="-" if s == "calm" else "--", color="C0" if zname == "house" else "C3",
                       label=f"{s}, {zname}")
            ax[1].plot(range(4), 100 * d0["gt95"], marker=mk, ls="-" if s == "calm" else "--", color="C0" if zname == "house" else "C3",
                       label=f"{s}, {zname}")
    ax[0].axhline(2.0, color="k", lw=0.8, ls=":")
    ax[1].axhline(5.0, color="k", lw=0.8, ls=":")
    for a_ in ax:
        a_.set_xticks(range(4))
        a_.set_xticklabels(FA.ANCHOR_BINS)
        a_.set_xlabel("anchors_used")
        a_.grid(alpha=0.3)
    ax[0].set_yscale("log")
    ax[0].set_ylabel("mean NIS under B2 (χ²₂ expectation 2)")
    ax[1].set_ylabel("share of fixes above the χ²₂ 95 % point (%; expectation 5)")
    ax[1].legend(fontsize=7)
    fig.suptitle("NIS of the fixes under B2: is the anchors_used noise table consistent, and house-confounded?")
    fig.tight_layout()
    f = f"{STEM}_nis_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["nis"] = f
    # ---- 5. the 09-10 09:48 cluster
    CL = A["CL"]
    cl = A["cfg"]["cluster"]
    acfg = A["acfg"]
    c_ms = C.to_ms(cl["center"], acfg["tz"])
    pk = cl["period"]
    lo = C.to_ms(acfg["periods"][pk]["start"], acfg["tz"])
    hw = float(cl["half_window_s"])
    animals = acfg["animals"]
    fig, ax = plt.subplots(len(animals), 1, figsize=(12, 2.0 * len(animals)), sharex=True)
    for k, a in enumerate(animals):
        p_ = out / "tracks" / f"{a}_{pk}.npz"
        if not p_.exists():
            continue
        with np.load(p_) as z:
            ta = z["t_al_ms"]
            sel = (ta >= c_ms - 1000 * hw) & (ta < c_ms + 1000 * hw)
            tt = (ta[sel] - c_ms) / 1000.0
            b2, v1 = z["B2"][sel].astype(float), z["V1b"][sel].astype(float)
            zu, rl = z["zupt"][sel], z["released"][sel]
        with np.load(Path(A["cfg"]["audit_run"]) / "tracks" / f"{a}_{pk}.npz") as z:
            raw = z["raw"][sel].astype(float)
        if not len(tt):
            continue
        ref = np.median(raw[: max(10, len(raw) // 20)], axis=0)
        ax[k].plot(tt, np.hypot(*(raw - ref).T), ".", ms=1.5, color=COL["raw"], label="raw")
        ax[k].plot(tt, np.hypot(*(b2 - ref).T), color=COL["B2"], lw=1.0, label="B2")
        ax[k].plot(tt, np.hypot(*(v1 - ref).T), color=COL["V1b"], lw=1.2, label="V1b")
        for msk, colr in ((zu, "#9467bd"), (rl, "#d62728")):
            for a0, b0 in C.true_runs(msk):
                ax[k].axvspan(tt[a0], tt[b0 - 1], color=colr, alpha=0.12, lw=0)
        ax[k].set_ylabel(f"{a}\n|p − ref| (in)")
        ax[k].set_ylim(0, 40)
        ax[k].grid(alpha=0.3)
    ax[0].legend(fontsize=7, ncol=3, loc="upper right")
    ax[-1].set_xlabel(f"s from {cl['center']} (purple: ZUPT fixes, red: released)")
    fig.suptitle(f"{cl['label']}: distance from each tag's first-minute position ({len(CL)} releases within ± {hw / 60:.0f} min)")
    fig.tight_layout()
    f = f"{STEM}_cluster_{cohort}.png"
    fig.savefig(fdir / f, dpi=120)
    plt.close(fig)
    figs["cluster"] = f
    return figs


# ====================================================================================================== report
_f = DS._f
_p = DS._p


def _pf(b: bool) -> str:
    return "pass" if b else "**FAIL**"


DEFINITIONS = r"""
## Definitions

All positions are WISER **inches in the unverified offset frame**; only distances and speeds (frame-invariant) are used.
Times are field-PC local (EDT). $k$ indexes the fixes of one tag; $\mathbf z_k$ = raw fix (in); $\hat{\mathbf p}^{(m)}_k$ =
method $m$'s position at fix $k$; $t_k=t_k^{\text{WISER}}-\tau^*$ = fix time aligned on the IMU clock ($\tau^*$ =
0.20 / 0.15 / 0.10 / 0.20 / 0.15 s for SF07 / 08 / 09 / 10 / 12); $s$ = an integer field-PC second.

### B2 (reference and base)
Per axis a constant-velocity state $\mathbf x_k=(p_k,v_k)$, $\mathbf x_k=F_k\mathbf x_{k-1}+\boldsymbol\eta_k$,
$F_k=\begin{pmatrix}1&\Delta t_k\\0&1\end{pmatrix}$, $\mathrm{Cov}(\boldsymbol\eta_k)=q\begin{pmatrix}\Delta t^3/3&\Delta t^2/2\\\Delta t^2/2&\Delta t\end{pmatrix}$,
$q$ = 3 in²/s³; fix $z_k=p_k+\varepsilon_k$, $\varepsilon_k\sim\mathcal N(0,\sigma^2_{\mathrm{ax}}(A_k)/w_k)$ with $A_k$ = `anchors_used`
and $\sigma_{\mathrm{ax}}$ the smoothing pilot's robust per-anchor SD. Pass 0: forward Kalman filter with a soft χ² gate
(the fix variance is inflated by $d^2/13.82$ when the 2-D innovation $d^2$ exceeds the χ²₂ 0.999 point) + RTS smoother;
passes 1–2: Huber weights $w_k=\min(1,\,2.5/m_k)$, $m_k=\big(\sum_a (z_{k,a}-\hat p_{k,a})^2/\sigma^2_a(A_k)\big)^{1/2}$ from the smoothed
residuals. **Text:** the default WISER smoother of 2026c (default-smoother step).

### V1b
B2 plus, at every fix $k$ inside a ZUPT interval, the pseudo-measurements $0=v_{k,a}+\epsilon_{k,a}$ ($a=x,y$),
$\epsilon\sim\mathcal N(0,\sigma_Z^2/w^Z_k)$, $\sigma_Z$ = 1.0 in/s, applied after the fix update in the same forward pass.
Huber weight in the same IRLS passes as the fixes (pass 0: $w^Z_k=1$):
$$ w^Z_k=\min\!\Big(1,\ \frac{2.5}{m^Z_k}\Big),\qquad m^Z_k=\frac{\lVert\hat{\mathbf v}_k\rVert}{\sigma_Z} $$
with $\hat{\mathbf v}_k$ the smoothed velocity of the previous pass. **Text:** where the head IMU says still, B2 is told the
velocity is zero, but a velocity the fixes insist on (> 2.5 in/s) is listened to with a falling weight. Nothing else
changes; where the IMU is not usable there is no pseudo-measurement, so the same filter runs B2 dynamics (no splice).

### ZUPT intervals and membership
$\text{still}(s)$ = QC-ok ∧ $\overline{\text{VeDBA}}_{1s}<\theta_a$ ∧ $\overline{|\boldsymbol\omega|}_{1s}<10$ °/s (pilot rule).
A run $[s_a,s_b)$ of $n=s_b-s_a$ consecutive still seconds gives, if $n\ge3$, the interval $I=[s_a+1,\,s_b-1)$ ($n-2$ s);
runs with $n<3$ give none. Fix $k$ is a ZUPT fix of $I$ when $t_k\in I$. The ± 10-min margins have no IMU seconds → no ZUPT.

### Release
For an interval $I=[e_0,e_1)$: reference $\mathbf r=\operatorname{med}\{\mathbf z_k: t_k\in[e_0,e_0+5)\}$ (coordinate-wise; if
fewer than 10 fixes there, the first 10 fixes of $I$); centres $c\in\{e_0, e_0+0.25, \dots\}<e_1$;
$$ \mathbf m(c)=\operatorname{med}\{\mathbf z_k:\ t_k\in[c-2.5,\,c+2.5)\}\quad(\ge5\text{ fixes, else undefined}),\qquad
   D(c)=\lVert\mathbf m(c)-\mathbf r\rVert . $$
A stretch = a maximal run of consecutive centres with $D(c)\ge12$ in (an undefined centre ends it); the first stretch whose
span (last − first centre) exceeds 5 s releases $I$ from its first centre $c^\ast$: fixes with $t_k\ge c^\ast$ in $I$
get no ZUPT. **Text:** if raw WISER holds a ≥ 1-ft offset for more than 5 s inside a still run, the constraint lets the
track follow it (either the head moved despite the IMU, or WISER drifted — the release cannot tell which).

### Sensitivities
V1b-noRelease: V1b without the release. V1b-raw: a ZUPT at every fix whose aligned second is still (no erosion, no
minimum run), Gaussian $\sigma_Z$ = 0.25 in/s, no release (the original proposal). Neither can become the default here.

### E1 — identical to B2 in motion
Base set $\mathcal B$ = window fixes whose aligned second is in the analysis mask (window, no handling ± 5 min, no
all-tag silence ± 120 s, tag valid), IMU-QC-ok and not still. $\delta_k=\lVert\hat{\mathbf p}^{(V1b)}_k-\hat{\mathbf p}^{(B2)}_k\rVert$,
$\tau_k=\min_{j\in\mathcal Z}|t_k-t_j|$ with $\mathcal Z$ the V1b ZUPT fixes (after release).
**E1a:** $Q_{0.99}\{\delta_k: k\in\mathcal B,\ \tau_k\ge3\text{ s}\}\le0.5$ in, calm and rain separately.
**E1b:** with $v_m(s)=\lVert\tilde{\mathbf p}^{(m)}(s+1)-\tilde{\mathbf p}^{(m)}(s)\rVert/1$ s ($\tilde{\mathbf p}$ = linear interpolation
inside inter-fix gaps ≤ 1 s), $\Delta_q=Q_q[v_{V1b}]/Q_q[v_{B2}]-1$ for $q\in\{0.5,0.95\}$ on (i) IMU-locomoting seconds and
(ii) seconds whose WISER library 1-s median speed is ≥ 10 in/s inside the analysis mask (seconds where any track is undefined
dropped for all); pass if $|\Delta_q|\le0.05$ for both quantiles, subsets and sets. **Text:** V1b claims to be B2 wherever
the head is not still; E1 tests that identity (it does not test that B2 is right).

### E2 — transitions not shifted
Events (default-smoother S5): an IMU still run $[a,b)$ ≥ 10 s followed (onset) / preceded (offset) within 60 s by a
locomoting second $s_L$ (no still run or unusable second in between, ≥ 10 s from the window edges). With $v_m(g)$ the 1-s
centred speed on a 0.25-s grid:
$$ \lambda^{\text{on}}_m=\min\{g\in[b-5,\,s_L+20]:v_m(g)\ge3\}-b,\qquad \lambda^{\text{off}}_m=\max\{g\in[s_L-20,\,a+10]:v_m(g)\ge3\}+0.25-a $$
(s); $\Delta\lambda=\lambda_{V1b}-\lambda_{B2}$ per event (events where both are defined). Pass if the median $\Delta\lambda$ lies
within ± 0.5 s for onsets and offsets, calm and rain (all periods). **Text:** the constraint must not make the track start
later or stop earlier than B2.

### E3 — no jumps
Jump: consecutive fixes with $\lVert\hat{\mathbf p}_{k+1}-\hat{\mathbf p}_k\rVert>30$ in and $t_{k+1}-t_k\le0.35$ s. Pass if 0 in the
primary ≥ 30-s certified segments (calm and rain) and 0 over the analysis mask of every period (pair midpoint second).

### Still metrics (reported; circular for V1b)
On the failure audit's certified ≥ 30-s segments (gate-v2 strict on 09-08, S50 elsewhere; 1 s trimmed), truth
$\mathbf c_\sigma=\operatorname{med}_{k\in\sigma}\mathbf z_k$: per-fix $r_k=\lVert\hat{\mathbf p}_k-\mathbf c_\sigma\rVert$, RMS $=(\frac1N\sum r_k^2)^{1/2}$ and p99
of $r_k$ (in); rolling-median drift $d^{(L)}_\sigma=\max_c\lVert\operatorname{med}_{t_k\in[c-L/2,c+L/2)}\hat{\mathbf p}_k-\mathbf c_\sigma\rVert$
($L$ = 10 s, ≥ 10 fixes; 60 s, ≥ 60 fixes, segments ≥ 120 s; median and p90 over segments); ≥ 12-in excursion = ≥ 10
consecutive 1-s centres with the 10-s median ≥ 12 in from $\mathbf c_\sigma$; fake path
$\Pi=\sum_s\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/(N_s/60)$ (in/min, pooled). **Circular:** the IMU stillness that drives
the ZUPT also certifies these segments, so they show what the constraint removes, not independent accuracy.

### ZUPT coverage
$$ \kappa=\frac{\sum_\sigma\big|\,\bigcup_I I^{\text{fin}}\cap[t^0_\sigma+1,\,t^1_\sigma-1)\big|}{\sum_\sigma D_\sigma} $$
with $I^{\text{fin}}=[e_0,\min(e_1,c^\ast))$ the ZUPT intervals after the release and $D_\sigma$ the trimmed durations of the
certified ≥ 30-s segments. **Text:** the share of certified still time that actually receives the constraint after the guards.

### Release accounting
A release is inside a certified segment when $c^\ast$ lies in a primary certified segment (≥ 10 s; the ≥ 30-s subset
reported); there the head is certified still, so the release followed WISER drift — a cost. Rate = releases inside ≥ 30-s
segments per certified still-hour.

### False-stillness probe
Pilot-still seconds (QC-ok ∧ still, analysis mask) that overlap no primary certified window (≥ 1 s) or segment (≥ 10 s).
WISER 5-s displacement $D_5(s)=\lVert\tilde{\mathbf p}^{(B2)}(s+3)-\tilde{\mathbf p}^{(B2)}(s-2)\rVert$ (5 s centred on the second);
compared with pilot-still seconds inside certification and with IMU-locomoting / active seconds. **Text:** how often the
1-s still class may be wrong, and how much of it the guards keep away from the ZUPT.

### S1 — held-out error (identity check)
The default-smoother masks and seeds: (a) runs of 4–8 hidden fixes separated by 1–47 visible ones, (s) every 5th fix;
B2 and V1b are rerun with the hidden fixes invisible (the release sees only visible fixes); $e_k=\lVert\mathbf z_k-\hat{\mathbf p}_{-}(t_k)\rVert$
on hidden window fixes with ≥ 7 anchors and the aligned second QC-ok; $D=1-\operatorname{med}e^{(V1b)}/\operatorname{med}e^{(B2)}$ on the
moving (not still) subset. Expected ≈ 0.

### NIS
For each visible fix, in the final forward pass of the smoother, with the predicted state and the nominal (unweighted)
anchors_used noise:
$$ \text{NIS}_k=\sum_{a\in\{x,y\}}\frac{(z_{k,a}-\hat p^{-}_{k,a})^2}{P^{-}_{k,aa}+\sigma^2_a(A_k)} $$
Under a consistent model $\text{NIS}_k\sim\chi^2_2$: mean 2, median 1.39, 5 % above 5.99. Strata: anchors_used {≤ 6, 7, 8, 9}
× zone (house = the B2 position inside a house ROI grown by 14 in; else outside) × IMU state of the aligned second.
**Text:** a mean above 2 means the noise table under-states the error there (or the motion model is too stiff); a strata
pattern by zone at equal anchors means the table is house-confounded.

### Block bootstrap
$\theta^{*(b)}=\theta(\{\text{10-min animal-period blocks drawn with replacement within the set}\})$, $b$ = 1..1000; CI =
2.5–97.5 % of $\theta^*$; paired comparisons use the same draw for both methods; quantiles inside the bootstrap use
histograms (0.001 in for the E1a distance, 0.05 in/s for speeds, 0.005 in for held-out errors); point estimates are exact.
"""


def render_report(A: dict, out: Path, figs: dict, meta: dict) -> str:
    cfg, acfg = A["cfg"], A["acfg"]
    cohort = cfg["_cohort"]
    acc = cfg["acceptance"]
    ver, dec = A["ver"], A["dec"]
    E1a, PROF, E1b, E2, E3m, J3 = A["E1a"], A["PROF"], A["E1b"], A["E2"], A["E3m"], A["J3"]
    pooled, setkind, BS, S3, COV, RS, CL, RL, S1, NIS, FS = (A[k] for k in ("pooled", "setkind", "BS", "S3", "COV", "RS", "CL", "RL", "S1", "NIS", "FS"))
    rep_tr, zst = A["rep_tr"], A["zstats"]
    v = ver["V1b"]

    def e1a_r(m, s):
        r = E1a[(E1a.method == m) & (E1a.set == s)]
        return r.iloc[0] if len(r) else None

    def e1b_r(m, s, sub):
        r = E1b[(E1b.method == m) & (E1b.set == s) & (E1b.subset == sub)]
        return r.iloc[0] if len(r) else None

    def e2_r(m, s, k, per="all"):
        r = E2[(E2.method == m) & (E2.set == s) & (E2.kind == k) & (E2.periods == per)]
        return r.iloc[0] if len(r) else None

    def pv(s, m, col, tab=None):
        tab = pooled if tab is None else tab
        r = tab[(tab.set == s) & (tab.method == m)]
        return float(r[col].iloc[0]) if len(r) else np.nan

    def bsv(s, m, metric):
        r = BS[(BS.set == s) & (BS.method == m) & (BS.metric == metric)]
        return r.iloc[0] if len(r) else None

    def cov(s, k="all"):
        return COV[(COV.set == s) & (COV.kind == k)].iloc[0]

    def p34(s, m="V1b", b0=3):
        return PROF[(PROF.method == m) & (PROF.set == s) & (PROF.dz_lo == b0)].iloc[0]

    def p_ge(s, b0, m="V1b"):
        g = PROF[(PROF.method == m) & (PROF.set == s) & (PROF.dz_lo >= b0)]
        return float(g.p99.max()) if len(g) else np.nan

    def nis_r(m, by, **kw):
        g = NIS[(NIS.method == m) & (NIS.by == by)]
        for k_, v_ in kw.items():
            g = g[g[k_] == v_]
        return g.iloc[0] if len(g) else None

    L = []
    L.append(f"# V1b — B2 + a guarded head-IMU zero-velocity constraint (cohort {cohort})\n")
    L.append(f"**Step A of A → B → C** — approved by the user 2026-10-03 (\"干吧\"). Plan [`{PLAN}`](../../../../{PLAN}) (written before any V1b number; "
             f"5 amendments at its end, all made before any pooled V1b number); driver `wiser/scripts/analyze_wiser_v1b.py` (`--selftest` ALL PASS); config `wiser/configs/wiser_v1b_{cohort}.json` "
             f"(verdict in its `decision` block); bulk `{out}`; inputs = the failure audit run `{cfg['audit_run']}` and the WISER fix caches "
             f"(reused, not recomputed); git `{meta['git_commit']}`. Measurement report: no behavioural claim; WISER inch frame unverified "
             f"(only distances and speeds used).\n")
    # ---------------- executive summary
    L.append("## Executive summary\n")
    ex = []
    if dec["V1b_passes"]:
        ex.append(f"**Verdict: V1b passes E1–E3 → V1b becomes the default WISER track for the implanted animals** (SF07–SF12 wherever the IMU QC passes; "
                  f"elsewhere it is B2 by construction); **B2 remains the universal baseline** (tags without an IMU, e.g. the five females released 09-11, "
                  f"and every IMU-failed stretch).")
    else:
        ex.append(f"**Verdict: V1b fails {', '.join(dec['failed_claims'])} → B2 stays the default WISER track** (V1b's own claim "
                  f"\"B2 in motion, still in stillness\" does not hold as pre-registered; failed: {', '.join(dec['failed_claims'])}).")
    ra, rr = e1a_r("V1b", "calm"), e1a_r("V1b", "rain")
    ex.append(f"**E1a (position = B2 ≥ 3 s from any ZUPT fix):** p99 of |V1b − B2| = {_f(ra.p99, 3)} in calm [{_f(ra.get('p99_lo'), 3)}, {_f(ra.get('p99_hi'), 3)}] "
              f"and {_f(rr.p99, 3)} in rain [{_f(rr.get('p99_lo'), 3)}, {_f(rr.get('p99_hi'), 3)}] (bound 0.5 in; max {_f(ra['max'], 2)} | {_f(rr['max'], 2)} in; "
              f"{_p(ra.share_ge_min_dist, 0, False)} | {_p(rr.share_ge_min_dist, 0, False)} of the IMU-ok non-still fixes are ≥ 3 s from a ZUPT fix) → {_pf(v['E1a'])}. "
              f"The difference is local: p99 {_f(p34('calm').p99, 2)} | {_f(p34('rain').p99, 2)} in at 3–4 s from a ZUPT fix, ≤ {_f(max(p_ge('calm', 5), p_ge('rain', 5)), 2)} in from 5 s on.")
    cells = []
    for s in ("calm", "rain"):
        for sub in ("loco", "wfast"):
            r = e1b_r("V1b", s, sub)
            cells.append(f"{s} {'loco' if sub == 'loco' else 'WISER-fast'} {_p(r.d_p50, 2)} / {_p(r.d_p95, 2)}")
    ex.append(f"**E1b (1-s speed p50 / p95 vs B2, bound ± 5 %):** " + "; ".join(cells) + f" → {_pf(v['E1b'])}.")
    cells = []
    for s in ("calm", "rain"):
        for k in ("onset", "offset"):
            r = e2_r("V1b", s, k)
            cells.append(f"{s} {k} {_f(r.dlag_med, 2)} s [{_f(r.get('dlag_lo'), 2)}, {_f(r.get('dlag_hi'), 2)}] (n {int(r.n_paired)})")
    ch_txt = "; ".join(f"{s} {k} {_p(e2_r('V1b', s, k).get('share_changed'), 0, False)} changed (mean {_f(e2_r('V1b', s, k).get('dlag_mean'), 2)} s)"
                       for s in ("calm", "rain") for k in ("onset", "offset"))
    ex.append(f"**E2 (median per-event lag change vs B2, bound ± 0.5 s):** " + "; ".join(cells) + f" → {_pf(v['E2'])}. The median hides a minority of shifted "
              f"events ({ch_txt}): onsets later, offsets earlier, about half of the changed offsets where B2's 3-in/s crossing lay inside the IMU-still run (E2 detail).")
    ex.append(f"**E3 (jumps):** {v['E3_still_jumps']} in the certified ≥ 30-s segments, {v['E3_motion_jumps']} over the analysis masks → {_pf(v['E3'])}.")
    ex.append(f"**Still (circular — the IMU stillness drives the ZUPT and certifies the segments):** fake path B2 {_f(pv('calm', 'B2', 'path_in_per_min'))} | "
              f"{_f(pv('rain', 'B2', 'path_in_per_min'))} → V1b {_f(pv('calm', 'V1b', 'path_in_per_min'))} | {_f(pv('rain', 'V1b', 'path_in_per_min'))} in/min "
              f"(calm | rain); per-fix RMS {_f(pv('calm', 'B2', 'rms_in'), 2)} | {_f(pv('rain', 'B2', 'rms_in'), 2)} → {_f(pv('calm', 'V1b', 'rms_in'), 2)} | "
              f"{_f(pv('rain', 'V1b', 'rms_in'), 2)} in — σ_ZUPT = 1 in/s is a soft constraint: V1b removes {_p(1 - pv('calm', 'V1b', 'path_in_per_min') / pv('calm', 'B2', 'path_in_per_min'), 0, False)} | "
              f"{_p(1 - pv('rain', 'V1b', 'path_in_per_min') / pv('rain', 'B2', 'path_in_per_min'), 0, False)} of B2's fake path (V1b-raw, σ 0.25 Gaussian: "
              f"{_f(pv('calm', 'V1b_raw', 'path_in_per_min'))} | {_f(pv('rain', 'V1b_raw', 'path_in_per_min'))} in/min), and its Huber weight is < 1 at only "
              f"{_p(zst['calm']['wz_lt1_share'], 3, False)} | {_p(zst['rain']['wz_lt1_share'], 3, False)} of the ZUPT fixes. **ZUPT coverage** of certified still time {_p(cov('calm').cov_V1b, 1, False)} | {_p(cov('rain').cov_V1b, 1, False)} "
              f"(noRelease {_p(cov('calm').cov_V1b_nr, 1, False)} | {_p(cov('rain').cov_V1b_nr, 1, False)}; V1b-raw {_p(cov('calm').cov_V1b_raw, 1, False)} | "
              f"{_p(cov('rain').cov_V1b_raw, 1, False)}).")
    ra_ = RS[RS.set == "all"].iloc[0]
    rc_, rr_ = RS[RS.set == "calm"].iloc[0], RS[RS.set == "rain"].iloc[0]
    ex.append(f"**Releases:** {int(ra_.n_release)} in total ({int(ra_.n_in_cert)} inside certified segments — a cost: the head was certified still — and "
              f"{int(ra_.n_out_cert)} outside); inside ≥ 30-s segments {_f(rc_.in_cert30_per_still_h, 3)} | {_f(rr_.in_cert30_per_still_h, 3)} per certified "
              f"still-hour (calm | rain); the 09-10 09:48 cluster: {len(CL)} release(s) within ± 5 min ({', '.join(sorted(set(CL.animal))) if len(CL) else 'none'}).")
    s3c = S3[(S3.set == "rain")].set_index("method")
    ex.append(f"**S3 (rain ≥ 12-in excursions, reported):** raw {int(s3c.loc['raw', 'crazy_n'])}, B2 {int(s3c.loc['B2', 'crazy_n'])}, V1b "
              f"{int(s3c.loc['V1b', 'crazy_n'])} (noRelease {int(s3c.loc['V1b_nr', 'crazy_n'])}, V1b-raw {int(s3c.loc['V1b_raw', 'crazy_n'])}); "
              f"V1b − B2 rate {_f(s3c.loc['V1b', 'diff_vs_B2'], 3)}/still-h [{_f(s3c.loc['V1b', 'diff_B2_lo'], 3)}, {_f(s3c.loc['V1b', 'diff_B2_hi'], 3)}].")
    hn = [nis_r("B2", "set×abin×zone", set="calm", abin="9", zone=z_) for z_ in ("house", "outside")]
    hn_r = [nis_r("B2", "set×abin×zone", set="rain", abin="9", zone=z_) for z_ in ("house", "outside")]
    nall = nis_r("B2", "set", set="calm")

    def _nm(st_, zn):
        r = nis_r("B2", "set×abin×zone×imu", set="calm", abin="9", zone=zn, imu=st_)
        return float(r["mean"]) if r is not None else np.nan
    ns_ = [_nm("still", "house"), _nm("still", "outside")]
    nl_ = [_nm("locomoting", "house"), _nm("locomoting", "outside")]
    if all(x is not None for x in hn):
        ex.append(f"**NIS under B2 (χ²₂ expectation 2):** calm all fixes mean {_f(nall['mean'], 2)} ({_p(nall['gt95'], 1, False)} above the 95 % point); at 9 anchors "
                  f"house {_f(hn[0]['mean'], 2)} vs outside {_f(hn[1]['mean'], 2)}" + (f" (rain {_f(hn_r[0]['mean'], 2)} vs {_f(hn_r[1]['mean'], 2)})" if all(x is not None for x in hn_r) else "")
                  + (f"; mostly a motion effect — at 9 anchors, IMU-still house {_f(ns_[0], 2)} vs outside {_f(ns_[1], 2)}, locomoting {_f(nl_[0], 2)} vs {_f(nl_[1], 2)} (calm): "
                     f"the anchors_used table is roughly consistent for a still tag and too small in motion (the constant-velocity q is stiff for runs), "
                     f"with a smaller residual house/outside gap at equal state (§6)." if all(np.isfinite(x) for x in ns_ + nl_) else " — see §6."))
    vv = [m for m in ("V1b_nr", "V1b_raw") if ver[m]["pass_all"]]
    def worst_e1b(m):
        g = E1b[(E1b.method == m) & E1b.subset.isin(["loco", "wfast"])]
        dd_ = pd.concat([g[["set", "subset", "d_p50"]].rename(columns={"d_p50": "d"}).assign(q="p50"),
                         g[["set", "subset", "d_p95"]].rename(columns={"d_p95": "d"}).assign(q="p95")], ignore_index=True)
        r = dd_.loc[dd_.d.abs().idxmax()]
        return f"worst E1b {_p(r.d, 1)} at {r.set} {'WISER-fast' if r.subset == 'wfast' else 'IMU-locomoting'} {r.q}"

    def sens_txt(m):
        if ver[m]["pass_all"]:
            return f"{SHORT[m]} passes"
        return f"{SHORT[m]} fails {', '.join(ver[m]['failed'])}" + (f" ({worst_e1b(m)})" if not ver[m]["E1b"] else "")
    ex.append(f"**Sensitivities (never the decision):** {sens_txt('V1b_nr')}; {sens_txt('V1b_raw')}"
              + (f" → proposal to the user only: {', '.join(SHORT[m] for m in vv)}." if vv else "."))
    for i, e in enumerate(ex, 1):
        L.append(f"{i}. {e}")
    L.append("")
    # ---------------- E1-E3 table
    L.append("## Pre-registered acceptance (E1–E3)\n")
    L.append("Point estimates decide; 95 % CIs from the 10-min block bootstrap are reported. All periods of the audit (calm-dry days 09-05/07/08 08:00–18:00 "
             "and nights 09-05…09-08 21:00–04:20; rain nights 09-03, 09-09 and day 09-10), SF07, SF08, SF09, SF10, SF12.\n")
    L.append("| claim | criterion | " + " | ".join(SHORT[m] for m in VARIANTS) + " |")
    L.append("|---|---|" + "---|" * len(VARIANTS))

    def cell_e1a(m, s):
        r = e1a_r(m, s)
        return f"{_f(r.p99, 3)} [{_f(r.get('p99_lo'), 3)}, {_f(r.get('p99_hi'), 3)}] {'✓' if r['pass'] else '✗'}"
    for s in ("calm", "rain"):
        L.append(f"| E1a {s} | p99 \\|track − B2\\| ≤ 0.5 in, IMU-ok non-still mask fixes ≥ 3 s from a ZUPT fix | " + " | ".join(cell_e1a(m, s) for m in VARIANTS) + " |")
    for s in ("calm", "rain"):
        for sub in ("loco", "wfast"):
            cs = []
            for m in VARIANTS:
                r = e1b_r(m, s, sub)
                ok_ = abs(r.d_p50) <= float(acc["E1b_max_rel"]) and abs(r.d_p95) <= float(acc["E1b_max_rel"])
                cs.append(f"{_p(r.d_p50, 2)} [{_p(r.d_p50_lo, 1)}, {_p(r.d_p50_hi, 1)}]; {_p(r.d_p95, 2)} [{_p(r.d_p95_lo, 1)}, {_p(r.d_p95_hi, 1)}] {'✓' if ok_ else '✗'}")
            L.append(f"| E1b {s} {'IMU-locomoting' if sub == 'loco' else 'WISER ≥ 10 in/s'} | 1-s speed p50; p95 within ± 5 % of B2 | " + " | ".join(cs) + " |")
    for s in ("calm", "rain"):
        for k in ("onset", "offset"):
            cs = []
            for m in VARIANTS:
                r = e2_r(m, s, k)
                cs.append(f"{_f(r.dlag_med, 2)} s [{_f(r.get('dlag_lo'), 2)}, {_f(r.get('dlag_hi'), 2)}] {'✓' if r['pass'] else '✗'}")
            L.append(f"| E2 {s} {k} | median per-event Δ lag within ± 0.5 s | " + " | ".join(cs) + " |")
    L.append("| E3 | 0 jumps: certified ≥ 30-s segments / analysis masks | " + " | ".join(
        f"{ver[m]['E3_still_jumps']} / {ver[m]['E3_motion_jumps']} {'✓' if ver[m]['E3'] else '✗'}" for m in VARIANTS) + " |")
    L.append("| **outcome** | E1 ∧ E2 ∧ E3 | " + " | ".join(
        (f"**{'PASS' if ver[m]['pass_all'] else 'FAIL (' + ', '.join(ver[m]['failed']) + ')'}**" + (" — decides" if m == "V1b" else " — sensitivity")) for m in VARIANTS) + " |")
    L.append("")
    L.append(f"**Decision (pre-registered).** {'V1b passes E1–E3: V1b is the default WISER track for the implanted animals (IMU-QC-ok stretches; B2 elsewhere by construction), B2 the universal baseline.' if dec['V1b_passes'] else 'V1b fails ' + ', '.join(dec['failed_claims']) + ': B2 stays the default WISER track; no variant is promoted in this step.'}"
             + (f" A variant that would pass ({', '.join(SHORT[m] for m in dec['variants_that_would_pass'])}) is a proposal to the user, not a default." if dec["variants_that_would_pass"] else "") + "\n")
    wn_c, wn_r = e1b_r("V1b", "calm", "wfast_nonstill"), e1b_r("V1b", "rain", "wfast_nonstill")
    wf_c, wf_r = e1b_r("V1b", "calm", "wfast"), e1b_r("V1b", "rain", "wfast")
    if wn_c is not None and wn_r is not None:
        L.append(f"**E1b reading.** The only visible speed change is at the median of the rain WISER-fast seconds ({_p(wf_r.d_p50, 2)}). "
                 f"{_p(wf_c.imu_still_share, 0, False)} | {_p(wf_r.imu_still_share, 0, False)} of the WISER-fast seconds (calm | rain) are IMU-still "
                 f"(WISER's library speed says ≥ 10 in/s while the head IMU says still); without them the change is {_p(wn_c.d_p50, 2)} / {_p(wn_c.d_p95, 2)} (calm) and "
                 f"{_p(wn_r.d_p50, 2)} / {_p(wn_r.d_p95, 2)} (rain), so the change comes from the ZUPT acting where the IMU says still, not from motion. "
                 f"The release keeps it inside the bound: without it (V1b-noRelease) the same quantile is {_p(e1b_r('V1b_nr', 'rain', 'wfast').d_p50, 2)}.\n")
    L.append(f"![criteria](../figures/{figs['criteria']})\n")
    # E1 profile table
    L.append("**E1 profile** — |track − B2| on IMU-ok non-still analysis-mask fixes by time from the nearest ZUPT fix of the same track (in; p50 / p99 / max):\n")
    L.append("| time from ZUPT fix | n calm | V1b calm | V1b rain | V1b-noRelease calm (p99) | V1b-raw calm (p99) |")
    L.append("|---|---|---|---|---|---|")
    for b0 in PROFILE_BINS:
        rc1 = PROF[(PROF.method == "V1b") & (PROF.set == "calm") & (PROF.dz_lo == b0)].iloc[0]
        rr1 = PROF[(PROF.method == "V1b") & (PROF.set == "rain") & (PROF.dz_lo == b0)].iloc[0]
        rn = PROF[(PROF.method == "V1b_nr") & (PROF.set == "calm") & (PROF.dz_lo == b0)].iloc[0]
        rw = PROF[(PROF.method == "V1b_raw") & (PROF.set == "calm") & (PROF.dz_lo == b0)].iloc[0]
        lab = f"{b0}–{b0 + 1} s" if b0 < PROFILE_BINS[-1] else f"≥ {b0} s"
        L.append(f"| {lab} | {int(rc1.n):,} | {_f(rc1.p50, 3)} / {_f(rc1.p99, 3)} / {_f(rc1['max'], 2)} | {_f(rr1.p50, 3)} / {_f(rr1.p99, 3)} / {_f(rr1['max'], 2)} | "
                 f"{_f(rn.p99, 3)} | {_f(rw.p99, 3)} |")
    L.append("")
    L.append("**Reading.** The V1b − B2 difference is confined to the seconds next to a ZUPT interval and decays like the smoother's impulse "
             "response; E1a pools every IMU-ok non-still fix ≥ 3 s away, most of which are ≥ 10 s from any ZUPT fix, so its p99 is small. The 3–4-s "
             "bin alone has a p99 of " + f"{_f(p34('calm').p99, 2)} | {_f(p34('rain').p99, 2)} in (calm | rain); V1b-raw's differences are larger at every distance.\n")
    L.append(f"![profile](../figures/{figs['profile']})\n")
    # E2 detail
    L.append("**E2 detail** (all periods; median lag of B2 and V1b, events defined for one track only):\n")
    L.append("| set | kind | events | B2 median lag (n) | V1b median lag (n) | paired | B2-only / V1b-only defined | paired events changed (later / earlier) | of which B2 crossed inside the still run | median Δ of the changed | mean Δ |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for k in ("onset", "offset"):
            r0, r1 = e2_r("B2", s, k), e2_r("V1b", s, k)
            L.append(f"| {s} | {k} | {int(r0.n_events)} | {_f(r0.lag_med, 2)} s ({int(r0.n_defined)}) | {_f(r1.lag_med, 2)} s ({int(r1.n_defined)}) | {int(r1.n_paired)} | "
                     f"{int(r1.n_B2_only)} / {int(r1.n_m_only)} | {int(r1.n_changed)} = {_p(r1.get('share_changed'), 1, False)} ({int(r1.n_changed_later)} / {int(r1.n_changed_earlier)}) | "
                     f"{int(r1.n_changed_B2_inside_run)} | {_f(r1.dlag_med_changed, 2)} s | {_f(r1.get('dlag_mean'), 2)} s |")
    L.append("")
    L.append("**Reading.** Most events are unchanged (the ZUPT is eroded 1 s inside the still run and the onset/offset speed crossing usually lies "
             "outside it), so the pre-registered median Δ is 0 everywhere. The changed minority moves in the expected direction — onsets later, offsets "
             "earlier — mostly by a few 0.25-s grid steps, with a tail that pulls the mean to −1 to −2 s at offsets; about half of the changed "
             "offsets are events where B2's 3-in/s crossing lay inside the IMU-still run (B2's jitter read as movement), which V1b suppresses. "
             "The marginal medians (B2 vs V1b columns) also differ because the defined-event sets differ.\n")
    # ---------------- reported sections
    L.append("## 1. Inputs and reproduction\n")
    rt = A["summary"]["repro_tracks"]
    rs = A["rep_still"]
    dsr = A["repro_ds"]
    L.append("| check | result |")
    L.append("|---|---|")
    L.append(f"| new kernel without ZUPT vs the pilot's B2 kernel (float64, every fix) | max {rt['kernel_vs_pilot_B2_max_in']:.2e} in |")
    L.append(f"| B2 rebuilt here vs the audit's saved B2 (float32) | max {rt['B2_vs_saved_core_max_in']:.2e} in ≥ 60 s from the window edges, {rt['B2_vs_saved_all_max_in']:.2e} in over every fix |")
    L.append(f"| fixes = the audit's (fix cache rows, anchors, float32 raw) | rows {'all match' if rt['cache_match_all'] else 'MISMATCH'}; anchors {'all match' if rt['anchors_match_all'] else 'MISMATCH'}; "
             f"raw max {rt['raw_vs_saved_max_in']:.1e} in; segment fix counts {rt['seg_fixcount_mismatch']} mismatching |")
    L.append(f"| still metrics of raw / B2 vs the audit's saved rows ({rs['n_rows']:,} segment × method rows) | max \\|Δ\\| RMS {_f(rs['rms_in'], 5)} in, 10-s drift {_f(rs['drift10_in'], 4)} in, "
             f"fake path {_f(rs['path_in_per_min'], 4)} in/min, events {_f(rs['crazy_n'], 0)}, jumps {_f(rs['jumps'], 0)} |")
    if "events" in dsr:
        L.append("| S5 events vs the default-smoother run | " + "; ".join(f"{k} {v_['here']} ({v_['default_smoother']})" for k, v_ in dsr["events"].items()) + " |")
        L.append("| B2 S5 median lag vs the default-smoother run | " + "; ".join(f"{k} {_f(v_['here'], 2)} ({_f(v_['default_smoother'], 2)}) s" for k, v_ in dsr["B2_lag_med"].items()) + " |")
        L.append("| B2 1-s speed p50 / p95 vs the default-smoother run | " + "; ".join(
            f"{k} {_f(v_['here'][0], 3)} / {_f(v_['here'][1], 3)} ({_f(v_['default_smoother'][0], 3)} / {_f(v_['default_smoother'][1], 3)}; n {v_['n_here']:,} ({v_['n_default_smoother']:,}))"
            for k, v_ in dsr["B2_speed"].items()) + " |")
        L.append("| B2 S1 median held-out error (moving) vs the default-smoother run | " + "; ".join(f"{k} {_f(v_['here'], 4)} ({_f(v_['default_smoother'], 4)}) in" for k, v_ in dsr["B2_s1_med"].items()) + " |")
        L.append("| B2 calm / rain fake path vs the default-smoother run | " + "; ".join(f"{k} {_f(v_['here'], 2)} ({_f(v_['default_smoother'], 2)}) in/min" for k, v_ in dsr["B2_fake_path"].items()) + " |")
    elif "error" in dsr:
        L.append(f"| default-smoother reproduction | not available: {dsr['error']} |")
    L.append(f"| ZUPT fixes among window fixes (calm / rain) | V1b {_p(zst['calm']['zupt_share'], 1, False)} / {_p(zst['rain']['zupt_share'], 1, False)}; noRelease "
             f"{_p(zst['calm']['zupt_nr_share'], 1, False)} / {_p(zst['rain']['zupt_nr_share'], 1, False)}; V1b-raw {_p(zst['calm']['zupt_raw_share'], 1, False)} / "
             f"{_p(zst['rain']['zupt_raw_share'], 1, False)}; released {_p(zst['calm']['released_share'], 2, False)} / {_p(zst['rain']['released_share'], 2, False)} |")
    L.append(f"| Huber weight of the ZUPT (V1b, final pass) | < 1 at {_p(zst['calm']['wz_lt1_share'], 2, False)} / {_p(zst['rain']['wz_lt1_share'], 2, False)} of the ZUPT fixes; "
             f"1st percentile {_f(zst['calm']['wz_p01'], 3)} / {_f(zst['rain']['wz_p01'], 3)} |")
    L.append("")
    # still
    L.append("## 2. Still metrics on the certified ≥ 30-s segments (reported; CIRCULAR for the ZUPT forms)\n")
    L.append("The IMU stillness that drives the ZUPT also certifies these segments: the ZUPT rows show what the constraint removes, not independent "
             "accuracy. Truth = the segment's median raw fix (drift is a lower bound). CIs: 10-min block bootstrap.\n")
    L.append("| set | method | still h | fake path in/min [CI] | fake speed p95 (in/s) | per-fix RMS (in) [CI] | p99 | 10-s drift med / p90 | 60-s drift med / p90 | ≥ 12-in events (/h) | jumps |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for m in TRACKS:
            r = pooled[(pooled.set == s) & (pooled.method == m)].iloc[0]
            bp_, br_ = bsv(s, m, "path_rate"), bsv(s, m, "rms")
            L.append(f"| {s} | {LABEL[m]}{' *(circular)*' if m in VARIANTS else ''} | {_f(r.still_h)} | {_f(r.path_in_per_min)} [{_f(bp_.lo)}, {_f(bp_.hi)}] | {_f(r.speed_p95, 2)} | "
                     f"{_f(r.rms_in, 2)} [{_f(br_.lo, 2)}, {_f(br_.hi, 2)}] | {_f(r.p99_in)} | {_f(r.drift10_med, 2)} / {_f(r.drift10_p90, 2)} | "
                     f"{_f(r.drift60_med, 2)} / {_f(r.drift60_p90, 2)} | {int(r.crazy_n)} ({_f(r.crazy_per_h, 3)}) | {int(r.jumps_n)} |")
    L.append("")
    L.append("Day vs night (fake path in/min · per-fix RMS in · ≥ 12-in events · jumps):\n")
    L.append("| method | calm day | calm night | rain day | rain night |")
    L.append("|---|---|---|---|---|")
    for m in TRACKS:
        cells = []
        for s in ("calm", "rain"):
            for k in ("day", "night"):
                r = setkind[(setkind.set == s) & (setkind.kind == k) & (setkind.method == m)]
                cells.append(f"{_f(r.path_in_per_min.iloc[0])} · {_f(r.rms_in.iloc[0], 2)} · {int(r.crazy_n.iloc[0])} · {int(r.jumps_n.iloc[0])} ({_f(r.still_h.iloc[0])} h)" if len(r) else "–")
        L.append(f"| {LABEL[m]} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("**ZUPT coverage** (share of certified ≥ 30-s still time inside a ZUPT interval after the guards; fix share in parentheses):\n")
    L.append("| set | kind | still h | V1b | V1b-noRelease | V1b-raw | released h (V1b) |")
    L.append("|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for k in ("all", "day", "night"):
            r = cov(s, k)
            L.append(f"| {s} | {k} | {_f(r.still_h)} | {_p(r.cov_V1b, 1, False)} ({_p(r.fcov_V1b, 1, False)}) | {_p(r.cov_V1b_nr, 1, False)} ({_p(r.fcov_V1b_nr, 1, False)}) | "
                     f"{_p(r.cov_V1b_raw, 1, False)} ({_p(r.fcov_V1b_raw, 1, False)}) | {_f(r.released_h, 3)} |")
    L.append("\nThe erosion removes 2 s per still run and runs < 3 s give no ZUPT, so V1b covers less of the certified time than V1b-raw by construction.\n")
    L.append(f"![still](../figures/{figs['still']})\n")
    # releases
    L.append("## 3. Release accounting\n")
    L.append("| set | releases | inside certified segments (≥ 30 s) | outside | per certified still-hour (≥ 30 s) | per hour of ZUPT interval | released time (h; inside certified) | in a house | median max offset (in) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain", "all"):
        r = RS[RS.set == s].iloc[0]
        L.append(f"| {s} | {int(r.n_release)} | {int(r.n_in_cert)} ({int(r.n_in_cert30)}) | {int(r.n_out_cert)} | {_f(r.in_cert30_per_still_h, 3)} | {_f(r.per_zupt_h, 3)} | "
                 f"{_f(r.released_h, 3)} ({_f(r.released_in_cert_h, 3)}) | {_p(r.house_share, 0, False)} | {_f(r.dmax_med, 1)} |")
    L.append("\nA release inside a certified segment is a cost (the head was certified still, so the track followed WISER drift); outside, the release "
             "may have caught a real movement during IMU-still seconds or a WISER drift — the data here cannot tell which.\n")
    if len(CL):
        L.append(f"**{cfg['cluster']['label']}** (releases with the release time within ± {float(cfg['cluster']['half_window_s']) / 60:.0f} min of {cfg['cluster']['center']}):\n")
        L.append("| animal | release | ZUPT interval | stretch | max offset (in) | inside certified | house | anchors (median) |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in CL.sort_values("release_ms").itertuples():
            L.append(f"| {r.animal} | {FA.ms_local(r.release_ms)[11:]} | {FA.ms_local(r.iv_start_ms)[11:]} → {FA.ms_local(r.iv_end_ms)[11:]} ({_f(r.iv_s, 0)} s) | "
                     f"{_f(r.stretch_s, 1)} s | {_f(r.dmax_in, 1)} | {'yes' if r.in_cert else 'no'}{' (≥ 30 s)' if r.in_cert30 else ''} | {'yes' if r.house else 'no'} | {_f(r.anchors_med, 0)} |")
        L.append("")
    else:
        L.append(f"**{cfg['cluster']['label']}:** no release within ± {float(cfg['cluster']['half_window_s']) / 60:.0f} min of {cfg['cluster']['center']}.\n")
    L.append(f"![cluster](../figures/{figs['cluster']})\n")
    # false-still probe
    L.append("## 4. False-stillness probe\n")
    L.append("Pilot-still seconds (QC-ok ∧ 1-s still, analysis mask) that overlap no certified window or segment, vs comparison groups. "
             "D5 = B2 displacement over the 5 s centred on the second (in).\n")
    L.append("| set | group | seconds | share of pilot-still | D5 p50 / p90 / p99 | D5 > 6 in | D5 ≥ 12 in | with V1b ZUPT | noRelease | V1b-raw |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain", "all"):
        for r in FS[FS.set == s].itertuples():
            L.append(f"| {s} | {r.group} | {int(r.n_s):,} | {_p(r.share_of_pilot_still, 1, False)} | {_f(r.D5_p50, 2)} / {_f(r.D5_p90, 2)} / {_f(r.D5_p99, 1)} | "
                     f"{_p(r.D5_gt6, 1, False)} | {_p(r.D5_ge12, 2, False)} | {_p(r.zupt_V1b_share, 1, False)} | {_p(r.zupt_V1b_nr_share, 1, False)} | {_p(r.zupt_V1b_raw_share, 1, False)} |")
    L.append("\nOutside certification the rule's 'still' seconds include true stillness that the strict rule does not certify (short or slightly "
             "tilted poses), so this is an upper bound on false stillness; the D5 tail shows how much real displacement those seconds can carry.\n")
    # S1
    L.append("## 5. S1 (held-out fixes) and S3 (rain excursions) — identity checks, reported\n")
    L.append("| set | scheme | subset | n | B2 median (in) | V1b median | D = 1 − med(V1b)/med(B2) [CI] | ZUPT share of scored fixes |")
    L.append("|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for sch in ("a", "s"):
            for subn in ("moving", "still", "loco", "all"):
                r = S1[(S1.set == s) & (S1.scheme == sch) & (S1.subset == subn)]
                if not len(r):
                    continue
                r = r.iloc[0]
                ci_ = f" [{_p(r.D_lo, 2)}, {_p(r.D_hi, 2)}]" if subn == "moving" else ""
                L.append(f"| {s} | ({sch}) | {subn} | {int(r.n):,} | {_f(r.med_B2, 4)} | {_f(r.med_V1b, 4)} | {_p(r.D, 2)}{ci_} | {_p(r.zupt_share, 1, False)} |")
    L.append("")
    L.append("S3 — ≥ 12-in excursions (crazy-drift events) in the primary ≥ 30-s segments; rate differences per still-hour [95 % CI]:\n")
    L.append("| method | calm events | rain events | rain − raw | rain − B2 |")
    L.append("|---|---|---|---|---|")
    for m in TRACKS:
        rc0 = S3[(S3.set == "calm") & (S3.method == m)].iloc[0]
        rr0 = S3[(S3.set == "rain") & (S3.method == m)].iloc[0]
        L.append(f"| {LABEL[m]} | {int(rc0.crazy_n)} ({_f(rc0.crazy_per_h, 3)}/h) | {int(rr0.crazy_n)} ({_f(rr0.crazy_per_h, 3)}/h) | "
                 f"{_f(rr0.diff_vs_raw, 3)} [{_f(rr0.diff_raw_lo, 3)}, {_f(rr0.diff_raw_hi, 3)}] | {_f(rr0.diff_vs_B2, 3)} [{_f(rr0.diff_B2_lo, 3)}, {_f(rr0.diff_B2_hi, 3)}] |")
    L.append("")
    # NIS
    L.append("## 6. NIS diagnostic (Fable audit, point 4)\n")
    L.append("Normalised innovation squared of each fix under B2 (final forward pass, nominal anchors_used noise); consistent model: mean 2, "
             "median 1.39, 5 % above 5.99. Analysis-mask window fixes.\n")
    L.append("| set | anchors | zone | n | mean | median | > 95 % point | V1b mean |")
    L.append("|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for ab in FA.ANCHOR_BINS:
            for zn in ("house", "outside"):
                r = nis_r("B2", "set×abin×zone", set=s, abin=ab, zone=zn)
                r1 = nis_r("V1b", "set×abin×zone", set=s, abin=ab, zone=zn)
                if r is None:
                    continue
                L.append(f"| {s} | {ab} | {zn} | {int(r.n):,} | {_f(r['mean'], 2)} | {_f(r['median'], 2)} | {_p(r.gt95, 1, False)} | {_f(r1['mean'] if r1 is not None else np.nan, 2)} |")
    L.append("")
    L.append("By IMU state (B2; anchors 9 only; mean NIS (n)):\n")
    L.append("| zone | still calm | still rain | active calm | active rain | locomoting calm | locomoting rain | QC failed calm | QC failed rain |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for zn in ("house", "outside"):
        cells = []
        for st_ in ("still", "active", "locomoting", "QC failed"):
            a_ = nis_r("B2", "set×abin×zone×imu", set="calm", abin="9", zone=zn, imu=st_)
            b_ = nis_r("B2", "set×abin×zone×imu", set="rain", abin="9", zone=zn, imu=st_)
            cells.append(f"{_f(a_['mean'] if a_ is not None else np.nan, 2)} ({int(a_.n) if a_ is not None else 0:,}) | "
                         f"{_f(b_['mean'] if b_ is not None else np.nan, 2)} ({int(b_.n) if b_ is not None else 0:,})")
        L.append(f"| {zn} | " + " | ".join(cells) + " |")
    L.append("\n**Reading.** The noise table is roughly consistent for a still tag (mean ≈ 2.4–2.6 at 9 anchors in calm) and increasingly too "
             "optimistic as the head moves (active ≈ 4–6, locomoting ≈ 8–11): the innovation then also contains the motion the constant-velocity "
             "model did not predict, so the excess is a motion-model effect as much as a noise-table one. At equal IMU state the outside fixes are "
             "still somewhat worse than the house fixes; most of the house/outside gap in the anchors × zone table is the larger share of motion "
             "outside. Rain raises every stratum; 3–4 anchors are the worst.\n")
    L.append("By exact anchors_used (B2, calm | rain; mean NIS, n):\n")
    L.append("| anchors_used | calm | rain |")
    L.append("|---|---|---|")
    for an in range(3, 10):
        a_ = nis_r("B2", "set×anchors", set="calm", anchors=an)
        b_ = nis_r("B2", "set×anchors", set="rain", anchors=an)
        if a_ is None and b_ is None:
            continue
        L.append(f"| {an} | {_f(a_['mean'] if a_ is not None else np.nan, 2)} ({int(a_.n) if a_ is not None else 0:,}) | {_f(b_['mean'] if b_ is not None else np.nan, 2)} ({int(b_.n) if b_ is not None else 0:,}) |")
    L.append("")
    L.append(f"![nis](../figures/{figs['nis']})\n")
    # do not do
    L.append("## Do not do\n")
    L.append("- Do not read the still-period gains of V1b as evidence that the IMU makes WISER more accurate: the IMU stillness that drives the ZUPT also certifies the test segments.")
    L.append("- Do not read E1 as accuracy in motion: it tests that V1b equals B2 there; B2 is not the truth (step B builds an independent speed reference).")
    L.append("- Do not run V1b on tags without a head IMU (the five females released 09-11) or through IMU-failed stretches as if it were different from B2 there: it is B2 by construction.")
    L.append("- Do not promote V1b-noRelease or V1b-raw from this report: sensitivities only; a passing variant is a proposal to the user.")
    L.append("- Do not treat a release as proof that the rat moved: inside certified stillness a release followed WISER drift.")
    L.append("- Do not generalise the still numbers to the open field (most certified stillness is inside the houses) or to other cohorts without re-running.")
    L.append("- Do not place positions in the paddock: distances are in the unverified WISER inch frame.")
    L.append("- Do not use the anchors_used noise table as calibrated where the NIS says otherwise (§6).")
    L.append("")
    L.append(DEFINITIONS)
    # caveats
    L.append("## Caveats\n")
    L.append("- The pilot's B2 parameters were tuned on 2026-09-08/09, one of the calm audit nights.")
    L.append("- Still metrics are circular; certified stillness is ≥ 95 % inside the houses; truth is the segment's own WISER median (drift is a lower bound).")
    L.append("- B2 is not the truth in motion: E1 tests identity with B2, not correctness of either.")
    lim = float(acc["E1b_max_rel"])
    near = []
    for r in E1b[(E1b.method == "V1b") & E1b.subset.isin(["loco", "wfast"])].itertuples():
        for q in ("p50", "p95"):
            lo_, hi_ = getattr(r, f"d_{q}_lo"), getattr(r, f"d_{q}_hi")
            if lo_ <= -lim or hi_ >= lim:
                near.append(f"{r.set} {'WISER-fast' if r.subset == 'wfast' else 'IMU-locomoting'} {q} {_p(getattr(r, f'd_{q}'), 2)} [{_p(lo_, 1)}, {_p(hi_, 1)}]")
    if near:
        L.append(f"- E1 is decided on point estimates (pre-registered); the bootstrap CI of V1b reaches the ± 5 % bound at: {'; '.join(near)} "
                 f"(the IMU-still seconds inside the WISER-fast subset, see the E1b reading).")
    L.append("- The 1-s pilot still class has an unknown false-still rate; the erosion, the 3-s minimum run, the Huber weight and the release address it only partly (§4).")
    L.append("- S5 lags are defined only where the speed reaches 3 in/s; the paired medians use events where both tracks are defined.")
    L.append("- The rain set is three weather episodes; block CIs treat 10-min blocks as independent within a set.")
    L.append("- NIS uses the final forward pass with the nominal noise: Huber-down-weighted fixes still enter with their nominal variance, so outliers show up as large NIS by design.")
    L.append("")
    L.append("## Files\n")
    L.append(f"Bulk `{out}`: `tracks/<SFxx>_<period>.npz` (B2, V1b, V1b-noRelease, V1b-raw at every fix; ZUPT / noRelease / raw / released masks; "
             f"ZUPT Huber weights; NIS under B2 and V1b; analysis mask, IMU state, zone; |track − B2| and time to the nearest ZUPT fix), `seconds/` "
             f"(per-second speeds, library speed, certification and ZUPT flags, D5), `speeds/` (still fake speeds), `s1/` (held-out errors), `tables/` "
             f"(e1a_position, e1_profile, e1b_speed, e2_events, e2_lags, e3_motion_jumps, e3_jumps_by_set, still_metrics, still_fixes, still_pooled, "
             f"still_setkind, still_bootstrap, s3_excursions, zupt_coverage(_segments), releases(_summary, _cluster), false_still_probe, s1_heldout, nis, "
             f"reproduction_tracks), `summary.json`, `input_provenance.json`, logs. Re-aggregate without recomputing: "
             f"`python wiser/scripts/analyze_wiser_v1b.py --report-only <run_dir>`. Pointer: `results/{cohort}/wiser_baseline/reports/run_manifest_v1b_{cohort}.json`.\n")
    return "\n".join(L)


def publish(A: dict, out: Path, fh=None) -> None:
    import shutil
    cfg = A["cfg"]
    cohort = cfg["_cohort"]
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(A, out, fdir)
    (out / "figures").mkdir(exist_ok=True)
    for f in figs.values():
        shutil.copy2(fdir / f, out / "figures" / f)
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    dec = A["dec"]
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name, "driver": "wiser/scripts/analyze_wiser_v1b.py",
            "config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": C.git_commit(), "figures": sorted(figs.values()),
            "audit_run": cfg["audit_run"], "v1b_passes": dec["V1b_passes"], "default_implanted": dec["default_implanted"]}
    rep.write_text(render_report(A, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_v1b_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    ver = A["ver"]
    cj["decision"] = {
        "V1b_passes": dec["V1b_passes"], "failed_claims": dec["failed_claims"],
        "default_wiser_track_implanted": dec["default_implanted"], "universal_baseline": "B2",
        "where": "SF07-SF12 wherever the IMU QC passes (V1b is B2 by construction elsewhere)" if dec["V1b_passes"] else "B2 everywhere",
        "E1a_p99_in": ver["V1b"]["E1a_p99"], "E1b_worst_abs_rel": round(ver["V1b"]["E1b_worst"], 5), "E2_dlag_med_s": ver["V1b"]["E2_dlag"],
        "E3_jumps_still_motion": [ver["V1b"]["E3_still_jumps"], ver["V1b"]["E3_motion_jumps"]],
        "sensitivity": {m: ("pass" if ver[m]["pass_all"] else "fail " + ", ".join(ver[m]["failed"])) for m in ("V1b_nr", "V1b_raw")},
        "variants_that_would_pass": dec["variants_that_would_pass"],
        "run_dir": str(out), "report": f"results/{cohort}/wiser_baseline/reports/{rep.name}",
        "decided_local": pd.Timestamp.now(tz=cfg.get("tz", "America/New_York")).strftime("%Y-%m-%d %H:%M:%S")}
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}\ndecision written into {cp.name}: V1b {'passes' if dec['V1b_passes'] else 'fails'}")


# ====================================================================================================== selftest
def _synth(seed: int = 7, dur_s: float = 2400.0) -> dict:
    """Synthetic head track: still bouts 60-240 s, walking bouts 20-50 s (OU velocity, tau 3 s, 8 in/s per axis), WISER-like
    fix intervals, anchors 6-9 with anchor-dependent noise, rare outliers; planted: a 15-in WISER drift lasting 8 s inside a
    long still run, a 15-in excursion lasting 3 s in another, a 2-s false-still run during walking."""
    rng = np.random.default_rng(seed)
    m_ = int(dur_s / 0.18) + 20
    t = np.cumsum(rng.choice([0.134, 0.268], size=m_, p=[0.45, 0.55]) + rng.normal(0, 0.003, m_))
    t = t[t < dur_s]
    n = len(t)
    dg = 0.02
    g = np.arange(int(round((dur_s + 2) / dg))) * dg
    still = np.zeros(len(g), bool)
    bouts = []
    pos = 10.0
    while pos < dur_s:
        ls = rng.uniform(60, 240)
        bouts.append((pos, pos + ls))
        still[(g >= pos) & (g < pos + ls)] = True
        pos += ls + rng.uniform(20, 50)
    vel = np.zeros((len(g), 2))
    vv = np.zeros(2)
    for k in range(1, len(g)):
        if still[k]:
            vv = np.zeros(2)
        else:
            vv = vv - vv / 3.0 * dg + rng.normal(0, 8.0 * math.sqrt(2 * dg / 3.0), 2)
        vel[k] = vv
    pg = 300 + np.cumsum(vel, axis=0) * dg
    p = np.column_stack([np.interp(t, g, pg[:, a]) for a in range(2)])
    A = rng.choice([6, 7, 8, 9], size=n, p=[0.05, 0.1, 0.25, 0.6]).astype(float)
    sig = {6: (5.0, 4.5), 7: (2.8, 4.0), 8: (2.0, 3.2), 9: (1.5, 2.6)}
    sw = np.array([sig[int(a)] for a in A])
    z = p + rng.normal(0, 1, (n, 2)) * sw
    out_idx = rng.random(n) < 0.002
    z[out_idx] += rng.normal(0, 12, (int(out_idx.sum()), 2))
    long_b = [b for b in bouts if b[1] - b[0] >= 100 and b[1] < dur_s - 5]
    b_drift, b_exc = long_b[0], long_b[1]
    drift_iv = (b_drift[0] + 40.0, b_drift[0] + 48.0)
    exc_iv = (b_exc[0] + 40.0, b_exc[0] + 43.0)
    z[(t >= drift_iv[0]) & (t < drift_iv[1]), 0] += 15.0
    z[(t >= exc_iv[0]) & (t < exc_iv[1]), 1] += 15.0
    secs = np.arange(0, int(dur_s) + 1)
    per = int(round(1.0 / dg))
    blk = still[:per * len(secs)].reshape(len(secs), per)
    st_full, mov_full = blk.all(axis=1), (~blk).all(axis=1)
    state = np.where(st_full, 1, np.where(mov_full, 3, 2)).astype(np.int8)
    walk = [i for i in range(len(secs) - 3) if (state[i:i + 4] == 3).all() and i > 5]
    ws = walk[len(walk) // 2]
    false_iv = (float(secs[ws + 1]), float(secs[ws + 1]) + 2.0)
    state[ws + 1:ws + 3] = 1                 # a 2-s false-still run while the true track walks
    return {"t": t, "z": z, "p": p, "A": A, "secs": secs, "state": state, "drift_iv": drift_iv, "exc_iv": exc_iv,
            "b_drift": b_drift, "b_exc": b_exc, "false_iv": false_iv}


def selftest() -> int:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    t0 = time.time()
    cfg = {"v1b": {"sigma_zupt_inps": 1.0, "huber_zupt": True, "min_run_s": 3, "erode_s": 1,
                   "release": {"ref_s": 5.0, "ref_min_fix": 10, "roll_s": 5.0, "roll_min_fix": 5, "grid_s": 0.25, "dist_in": 12.0, "min_dur_s": 5.0}},
           "variants": {"V1b_raw": {"sigma_zupt_inps": 0.25, "huber_zupt": False}}}
    tuned = {"B2": {"q": 3.0, "mrej": 1e9}, "huber_k": P.HUBER_K, "gate2": P.GATE2, "n_irls": P.N_IRLS}
    specs = kf_specs(tuned, cfg)
    rc = cfg["v1b"]["release"]
    # 1) erosion and minimum run
    secs = np.arange(100, 140)
    st = np.zeros(len(secs), bool)
    st[2:4] = True          # 2-s run -> none
    st[6:9] = True          # 3-s run -> [107, 108)
    st[12:22] = True        # 10-s run -> [113, 121)
    iv = eroded(still_runs(st, secs), 3, 1)
    check("erosion / minimum run: 2-s run none, 3-s run 1 s, 10-s run 8 s", iv.tolist() == [[107.0, 108.0], [113.0, 121.0]], f"{iv.tolist()}")
    tq = np.array([106.9, 107.0, 107.5, 108.0, 112.99, 113.0, 120.99, 121.0, 102.5])
    jv, inside = membership(tq, iv)
    check("membership: a fix belongs when its aligned time lies inside [e0, e1)", inside.tolist() == [False, True, True, False, False, True, True, False, False],
          f"{inside.tolist()}")
    # 2) synthetic track
    syn = _synth()
    t, z, A_ = syn["t"], syn["z"], syn["A"]
    n = len(t)
    devs = []
    for a_, b_ in C.true_runs(syn["state"] == 1):
        if b_ - a_ < 60:
            continue
        m = (t >= a_ + 1) & (t < b_ - 1)
        zz = z[m]
        devs.append(pd.DataFrame({"anchors_used": A_[m], "dx": zz[:, 0] - np.median(zz[:, 0]), "dy": zz[:, 1] - np.median(zz[:, 1])}))
    table = P.anchor_sigma_table(pd.concat(devs))
    r2 = P.r2_from_anchors(A_, table)
    vis = np.ones(n, bool)
    Pb, _, nisb, _ = kf_v1b(t, z, r2, vis, np.zeros(n, bool), specs["B2"], tuned)
    Pref, _, _ = P.kf_run(t, z, r2, [vis], [np.zeros(n, np.int8)], [np.zeros(n, np.int8)], [{"q": 3.0, "mrej": 1e9}])
    dk = float(np.max(np.hypot(*(Pb - Pref[0]).T)))
    check("no-ZUPT kernel = the pilot's B2 (<= 1e-6 in)", dk <= 1e-6, f"max {dk:.2e} in")
    secs = syn["secs"]
    still_s = syn["state"] == 1
    ivs = eroded(still_runs(still_s, secs), 3, 1)
    zm = zupt_masks(t, z, vis, ivs, rc)
    Pv, _, _, wzv = kf_v1b(t, z, r2, vis, zm["zupt"], specs["V1b"], tuned)
    dz = dist_to_mask(t, zm["zupt"])
    fsec = np.floor(t).astype(np.int64)
    st_f = DS.lookup(secs, syn["state"], fsec, np.int8(0))
    moving = st_f != 1
    far = moving & (dz >= 3.0)
    dfar = np.hypot(*(Pv - Pb).T)[far]
    # the E1a statistic (p99) is checked; the max is printed (plan amendment 1: the smoother's impulse response decays
    # smoothly through 3 s, so the max sits at tau = 3.0-3.2 s and is ~2x the p99)
    check("V1b = B2 >= 3 s from any ZUPT fix (p99 <= 0.05 in)", float(np.percentile(dfar, 99)) <= 0.05,
          f"p99 {np.percentile(dfar, 99):.4f} in, max {dfar.max():.4f} in over {far.sum()} fixes")
    # release on the 8-s drift, not on the 3-s excursion
    rel_t = zm["rel"]
    k_d = int(np.flatnonzero((ivs[:, 0] <= syn["drift_iv"][0]) & (ivs[:, 1] > syn["drift_iv"][0]))[0])
    k_e = int(np.flatnonzero((ivs[:, 0] <= syn["exc_iv"][0]) & (ivs[:, 1] > syn["exc_iv"][0]))[0])
    check("release fires on the planted 8-s drift (within 1 s of its start)", np.isfinite(rel_t[k_d]) and abs(rel_t[k_d] - syn["drift_iv"][0]) <= 1.0,
          f"release at {rel_t[k_d]:.2f} s, drift starts {syn['drift_iv'][0]:.2f} s")
    check("release does not fire on the planted 3-s excursion", not np.isfinite(rel_t[k_e]), f"{rel_t[k_e]}")
    others = [k for k in range(len(ivs)) if k not in (k_d,)]
    check("no other release in the clean still runs", not np.isfinite(rel_t[others]).any(), f"{int(np.isfinite(rel_t[others]).sum())} extra")
    inf_ = (t >= syn["false_iv"][0]) & (t < syn["false_iv"][1])
    check("the planted 2-s false-still run gets no ZUPT (V1b) but does in V1b-raw", (not zm["zupt"][inf_].any()) and DS.lookup(secs, still_s, fsec, False)[inf_].all(),
          f"{int(zm['zupt'][inf_].sum())} ZUPT fixes of {int(inf_.sum())}")
    in_rel = (t >= rel_t[k_d]) & (t < ivs[k_d, 1])
    in_before = (t >= ivs[k_d, 0]) & (t < rel_t[k_d])
    check("after the release the ZUPT is off to the end of the run (and on before it)",
          in_rel.any() and not zm["zupt"][in_rel].any() and zm["released"][in_rel].all() and zm["zupt"][in_before].all(),
          f"{int(in_rel.sum())} released fixes, {int(in_before.sum())} kept")
    # still behaviour: V1b removes fake path in the clean still runs vs B2
    mc = {"roll_short_s": 10.0, "roll_short_min_fix": 10, "roll_long_s": 60.0, "roll_long_min_fix": 60, "roll_long_min_seg_s": 120.0,
          "crazy_in": 12.0, "crazy_min_s": 10, "jump_in": 30.0, "jump_dt_s": 0.35, "speed_grid_s": 0.25, "speed_max_gap_s": 1.0}
    path = {"B2": 0.0, "V1b": 0.0}
    sec_ = 0.0
    for a_, b_ in C.true_runs(syn["state"] == 1):
        if b_ - a_ < 30:
            continue
        ts, te = a_ + 1.0, b_ - 1.0
        i0, i1 = np.searchsorted(t, [ts, te])
        res, _, _, _ = FA.score_segment(t[i0:i1], {"B2": Pb[i0:i1], "V1b": Pv[i0:i1]}, np.median(z[i0:i1], axis=0), ts, te, mc, ["B2", "V1b"])
        for m in path:
            path[m] += res[m]["path_in"]
        sec_ += res["B2"]["path_s"]
    check("V1b's still fake path is below B2's (sanity; sigma_ZUPT = 1 in/s is a soft constraint)", path["V1b"] < path["B2"],
          f"{path['V1b'] / (sec_ / 60):.2f} vs {path['B2'] / (sec_ / 60):.2f} in/min")
    check("Huber weight of the ZUPT drops below 1 where the fixes insist (drift / false-still)", (wzv[zm["zupt"]] < 1.0).any(), f"min {wzv[zm['zupt']].min():.3f}")
    check("NIS defined for every visible fix, mean near the chi2_2 expectation (1-4)", np.isfinite(nisb).all() and 1.0 <= float(np.mean(nisb[np.isfinite(nisb)])) <= 4.0,
          f"mean {np.nanmean(nisb):.2f}")
    # 3) evaluators on planted cases
    dd = np.zeros(1000)
    dzz = np.full(1000, 5.0)
    bm = np.ones(1000, bool)
    ok1 = e1a_eval(dd + 0.1, dzz, bm, 3.0, 0.5)["pass"]
    dd2 = dd.copy()
    dd2[:20] = 1.0
    ok2 = e1a_eval(dd2, dzz, bm, 3.0, 0.5)["pass"]
    dzz2 = dzz.copy()
    dzz2[:20] = 1.0
    ok3 = e1a_eval(dd2, dzz2, bm, 3.0, 0.5)["pass"]
    check("E1a evaluator: 0.1 in passes; 2 % at 1 in fails; the same fixes < 3 s from a ZUPT are excluded", ok1 and not ok2 and ok3)
    rng = np.random.default_rng(3)
    vref = rng.gamma(2.0, 4.0, 5000)
    check("E1b evaluator: +2 % passes, +6 % fails, p95-only change fails", e1b_eval(vref * 1.02, vref, 0.05)["pass"] and not e1b_eval(vref * 1.06, vref, 0.05)["pass"]
          and not e1b_eval(np.where(vref > np.percentile(vref, 90), vref * 1.2, vref), vref, 0.05)["pass"])
    lag = rng.normal(7.0, 3.0, 300)
    check("E2 evaluator: +0.25 s passes, +0.75 s fails, undefined events ignored", e2_eval(lag + 0.25, lag, 0.5)["pass"] and not e2_eval(lag + 0.75, lag, 0.5)["pass"]
          and e2_eval(np.where(np.arange(300) < 50, np.nan, lag), lag, 0.5)["pass"])
    pj = Pv.copy()
    kj = int(np.flatnonzero(np.diff(t) <= 0.2)[100])
    pj[kj + 1] += np.array([40.0, 0.0])
    check("E3 evaluator: V1b has no jump; a planted 40-in step is two jumps", e3_eval(t, Pv, 30.0, 0.35)["pass"] and e3_eval(t, pj, 30.0, 0.35)["jumps"] == 2)
    # 4) S5 lags through the default-smoother code on the synthetic tracks (V1b vs B2)
    s5 = {"speed_thr_inps": 3.0, "onset_pre_s": 5.0, "onset_post_s": 20.0, "offset_pre_s": 20.0, "offset_post_s": 10.0, "grid_s": 0.25,
          "max_gap_s": 1.0, "still_run_min_s": 10, "loco_search_s": 60, "edge_s": 10.0}
    ev = DS.transition_events(syn["state"], secs, 0.0, float(secs[-1] + 1) * 1000.0, s5)
    lb = np.array([DS.event_lag(t, Pb, e, s5)[0] for e in ev])
    lv = np.array([DS.event_lag(t, Pv, e, s5)[0] for e in ev])
    r_ = e2_eval(lv, lb, 0.5)
    print(f"   synthetic S5: {len(ev)} events, median dlag {r_['dlag_med']:.2f} s (n {r_['n_paired']})", flush=True)
    check("synthetic S5 events found and lags defined for both tracks", len(ev) >= 4 and r_["n_paired"] >= 4)
    # 5) the failure audit's grouped-vs-pooled quantile check (fix of 2026-10-03)
    rq = np.random.default_rng(5)
    Sq = pd.DataFrame({"seg_id": [f"s{i}" for i in range(6)], "set": ["calm"] * 3 + ["rain"] * 3, "dur_trim_s": 60.0})
    Mq = pd.DataFrame([{"seg_id": s, "method": "raw", "drift10_in": 1.0, "drift60_in": np.nan, "crazy_n": 0, "crazy_s": 0, "jumps": 0,
                        "path_in": 10.0, "path_s": 59.0} for s in Sq.seg_id])
    Fq = pd.DataFrame({"seg_id": np.repeat(Sq.seg_id.to_numpy(), 20), "r_raw": rq.gamma(2.0, 1.0, 120)})
    spd_q = [rq.gamma(2.0, 1.0 + 3.0 * i, 200).astype(np.float32) for i in range(6)]
    SPq = {"raw": (np.repeat(np.arange(6), 200).astype(np.int64), np.concatenate(spd_q))}
    sub = Sq[Sq.set == "rain"]
    gq = FA.group_table(sub, Mq, Fq, SPq, ["set"], ["raw"], Sq).iloc[0]
    pq = FA.still_summary(sub, Mq, Fq, SPq, "raw", Sq)
    check("failure audit: grouped speed quantile = pooled for a single group", abs(gq["speed_p95"] - pq["speed_p95"]) < 1e-9,
          f"{gq['speed_p95']:.4f} vs {pq['speed_p95']:.4f}")
    print(f"numba: {P.HAVE_NUMBA}; selftest {time.time() - t0:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--report-only", default=None, help="existing run dir: re-aggregate and re-render from its saved tables")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    cfg = load_cfg(a.cohort, a.config)
    out = Path(a.report_only) if a.report_only else run_compute(cfg, a.workers or int(cfg.get("workers", 16)))
    fh = open(out / "log_report.txt", "a", encoding="utf-8")
    A = aggregate(out, cfg, fh)
    publish(A, out, fh)
    fh.close()


if __name__ == "__main__":
    main()
