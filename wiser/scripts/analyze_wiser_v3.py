r"""V3 = one B2 filter with a firm head-IMU zero-velocity constraint and locomotion-boosted process noise (cohort 2026c).

Plan: implementation_plan/2026-10-03-wiser-v3.md (approved by the user 2026-10-03, "做"; committed 26a1cb8 before any V3
number). Report (full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_v3_<cohort>.md

  B2        the smoothing pilot's tuned robust constant-velocity Kalman + RTS (q = 3 in^2/s^3, per-fix noise from
            anchors_used, chi2 gate + 2 Huber IRLS passes, k_H = 2.5), rebuilt here by the V3 kernel (multiplier 1, no ZUPT)
  V3        B2 with (1) q x 10 on every step whose midpoint second is IMU-QC-ok and locomoting (pilot rule; x 1 elsewhere)
            and (2) pseudo-measurements 0 = v_x, 0 = v_y, sigma_ZUPT = 0.25 in/s, Huber-weighted (k_H = 2.5) inside the IRLS
            passes, at fixes inside runs of >= 3 IMU-QC-ok still seconds eroded by 1 s at each end; no release. No IMU ->
            no ZUPT and q x 1 -> B2 dynamics in the same filter (no splice).
  sensitivities  V3_s05 / V3_s10 (sigma_ZUPT 0.5 / 1.0), V3_m3 / V3_m30 (locomotion x 3 / x 30), V3_loco (no ZUPT)
  context   B2 (rebuilt), V1b (the V1b run's track; current default for the implanted animals), V2b (default-smoother run)
Acceptance (pre-registered): T1 3-s p95 speed within +-3 % of the clean-WISER reference of step B (all clean seconds and
the > 15 in/s band, six nights); T2 zero jumps (primary certified still segments, analysis masks); T3 S5 onset/offset
median per-event lag change vs B2 <= +0.5 s (calm and rain). Reported: still metrics (circular), ZUPT coverage, in-place
jitter check, NIS by IMU state, S1, S3, fallback share.

Inputs (all read-only): the failure audit's run (tracks/, imu_seconds/, tables/), the WISER fix caches (float64 fixes,
library speed), the default-smoother config (S1/S2/S4/S5 definitions) and run (V2b tracks; reproduction), the V1b run (V1b
tracks + ZUPT masks), the step-B run (clean seconds, reference speeds, noise floor, R1 table). Existing scripts are
imported, never modified.

Usage:
  python wiser/scripts/analyze_wiser_v3.py --cohort 2026c [--workers 16]
  python wiser/scripts/analyze_wiser_v3.py --report-only <run_dir>     # re-aggregate / re-render from the saved per-job files
  python wiser/scripts/analyze_wiser_v3.py --selftest                  # synthetic data, no field data
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
import analyze_imu_wiser_calibration as C  # noqa: E402  (helpers; unmodified)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (pilot B2 kernel, noise table, IRLS constants, step states; unmodified)
import analyze_wiser_failure_audit as FA  # noqa: E402  (segment scoring, loaders, block bootstrap; unmodified)
import analyze_wiser_default_smoother as DS  # noqa: E402  (S1 masks, S2 speeds, S5 events/lags, bootstrap helpers; unmodified)
import analyze_wiser_v1b as V1B  # noqa: E402  (ZUPT intervals, membership, V1b kernel for the reproduction; unmodified)
import analyze_imu_speed_proxy as SP  # noqa: E402  (clean-WISER reference, track speeds, R1 ratio tables; unmodified)

njit = P.njit

DIRECTION = "wiser_baseline"
NAME = "wiser_v3"
STEM = f"{DIRECTION}_v3"
PLAN = "implementation_plan/2026-10-03-wiser-v3.md"
DRIVER = "wiser/scripts/analyze_wiser_v3.py"
VARS = ["V3", "V3_s05", "V3_s10", "V3_m3", "V3_m30", "V3_loco"]
SENS = VARS[1:]
KF = ["B2"] + VARS
CONTEXT = ["B2", "V1b", "V2b"]
TRACKS = ["raw", "B2", "V1b", "V2b"] + VARS
SMOOTHED = TRACKS[1:]
NIS_M = ["B2", "V1b", "V3", "V3_loco"]
S1_M = ["B2", "V3", "V3_loco"]
LABEL = {"raw": "raw fixes", "B2": "B2 robust CV", "V1b": "V1b (B2 + guarded ZUPT)", "V2b": "V2b (IMU-switched q, spliced)",
         "V3": "V3 (ZUPT 0.25 + loco ×10)", "V3_s05": "V3 σ_Z 0.5", "V3_s10": "V3 σ_Z 1.0", "V3_m3": "V3 loco ×3",
         "V3_m30": "V3 loco ×30", "V3_loco": "V3 loco-only (no ZUPT)"}
SHORT = {"raw": "raw", "B2": "B2", "V1b": "V1b", "V2b": "V2b", "V3": "V3", "V3_s05": "V3-σ0.5", "V3_s10": "V3-σ1.0",
         "V3_m3": "V3-×3", "V3_m30": "V3-×30", "V3_loco": "V3-loco"}
COL = {"raw": "#7f7f7f", "B2": "#2ca02c", "V1b": "#bcbd22", "V2b": "#e377c2", "V3": "#d62728", "V3_s05": "#ff7f0e",
       "V3_s10": "#ffbb78", "V3_m3": "#1f77b4", "V3_m30": "#9467bd", "V3_loco": "#8c564b"}
P0_POS, P0_VEL = float(P.P0_POS), float(P.P0_VEL)
SCALES = (3, 1)
SETS3 = ("all", "calm", "rain")
BANDS = SP.BANDS
BAND_LABEL = SP.BAND_LABEL
STATE_NAME = {1: "still", 2: "active", 3: "locomoting"}


def log_to(fh, msg: str) -> None:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)      # a cp1252 console must not stop the run
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_v3_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def load_acfg(cfg: dict) -> dict:
    return FA.load_cfg(cfg["_cohort"], str(REPO / cfg["audit_config"]))


def load_dcfg(cfg: dict) -> dict:
    return DS.load_cfg(cfg["_cohort"], str(REPO / cfg["default_smoother_config"]))


def load_scfg(cfg: dict) -> dict:
    return SP.load_cfg(cfg["_cohort"], str(REPO / cfg["speed_proxy_config"]))


def load_v1bcfg(cfg: dict) -> dict:
    return json.loads((REPO / cfg["v1b_config"]).read_text(encoding="utf-8"))


_CTX: dict = {}
_SEG: dict = {}


def _ctx(acfg: dict) -> dict:
    if acfg["_path"] not in _CTX:
        _CTX[acfg["_path"]] = FA.context(acfg)
    return _CTX[acfg["_path"]]


def _segments(run: Path) -> pd.DataFrame:
    k = str(run)
    if k not in _SEG:
        S = pd.read_csv(run / "tables" / "segments.csv")
        for c in ("primary", "scored", "ge30"):
            S[c] = S[c].astype(bool)
        _SEG[k] = S
    return _SEG[k]


def kf_specs(tuned: dict, cfg: dict) -> dict:
    """Kalman configurations: B2 (multiplier 1, no ZUPT), V3 and its sensitivities, all on the B2 base."""
    b2 = tuned["B2"]
    base = {"q": float(b2["q"]), "mrej": float(b2["mrej"])}
    v = cfg["v3"]
    sp = {"B2": {**base, "sv": 0.0, "huber_zupt": False, "mloco": 1.0, "zupt": False},
          "V3": {**base, "sv": float(v["sigma_zupt_inps"]), "huber_zupt": bool(v["huber_zupt"]), "mloco": float(v["loco_mult"]), "zupt": True}}
    for m, vv in cfg["variants"].items():
        z = bool(vv["zupt"])
        sp[m] = {**base, "sv": float(vv["sigma_zupt_inps"]) if z else 0.0, "huber_zupt": bool(v["huber_zupt"]) and z,
                 "mloco": float(vv["loco_mult"]), "zupt": z}
    return sp


# ====================================================================================================== Kalman kernel
@njit(cache=True)
def _kf_v3(t, z, r2, vis, zupt, qm, q, sv2, huber_zupt, huber_k, m_rej, gate2, n_iter, P_out, V_out, nis_out, wz_out):
    """V1b's kernel (B2 = the smoothing pilot's _kf_rts without drift, same operation order, + an optional Huber-weighted
    zero-velocity pseudo-measurement at the steps with zupt[k]) with a per-step process-noise multiplier: the step
    (t[k-1], t[k]] uses q_k = q * qm[k]. qm = 1 everywhere and no zupt -> B2 exactly. Writes the smoothed p, v (n, 2), the
    NIS of each visible fix in the final forward pass with the nominal (unweighted) noise and the final ZUPT weights."""
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
                qk = q * qm[k]
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
                    Pp[k, a, 0, 0] += qk * dt * dt * dt / 3.0
                    Pp[k, a, 0, 1] += qk * dt * dt / 2.0
                    Pp[k, a, 1, 0] += qk * dt * dt / 2.0
                    Pp[k, a, 1, 1] += qk * dt
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


def kf_v3(t, z, r2, vis, zupt, qm, spec: dict, tuned: dict):
    """One smoother run; returns (p (n, 2), v (n, 2), nis (n,), w_zupt (n,))."""
    n = len(t)
    Po, Vo = np.empty((n, 2)), np.empty((n, 2))
    nis, wz = np.empty(n), np.empty(n)
    sv = float(spec.get("sv") or 0.0)
    _kf_v3(np.ascontiguousarray(t, np.float64), np.ascontiguousarray(z, np.float64), np.ascontiguousarray(r2, np.float64),
           np.ascontiguousarray(vis, np.bool_), np.ascontiguousarray(zupt, np.bool_), np.ascontiguousarray(qm, np.float64),
           float(spec["q"]), sv * sv, bool(spec.get("huber_zupt", False)), float(tuned.get("huber_k", P.HUBER_K)),
           float(spec.get("mrej", 1e9)), float(tuned.get("gate2", P.GATE2)), int(tuned.get("n_irls", P.N_IRLS)), Po, Vo, nis, wz)
    return Po, Vo, nis, wz


def loco_steps(st_mid: np.ndarray, loco_state: int) -> np.ndarray:
    """Steps (t[k-1], t[k]] whose midpoint second is IMU-QC-ok and locomoting (the audit's state 3 implies QC-ok)."""
    m = np.asarray(st_mid) == int(loco_state)
    if len(m):
        m[0] = False                      # no step before the first fix
    return m


def qmult(loco: np.ndarray, mloco: float) -> np.ndarray:
    return np.where(loco, float(mloco), 1.0)


def infl_mask(zupt: np.ndarray, loco: np.ndarray) -> np.ndarray:
    """Fixes touched by V3's changes: ZUPT fixes and both end fixes of every locomoting step."""
    m = np.asarray(zupt, bool) | np.asarray(loco, bool)
    if len(m) > 1:
        m[:-1] |= np.asarray(loco, bool)[1:]
    return m


def dist_q(tq: np.ndarray, tm: np.ndarray) -> np.ndarray:
    """|tq - nearest tm| (s) for sorted tm; +inf when tm is empty."""
    if not len(tm):
        return np.full(len(tq), np.inf)
    j = np.searchsorted(tm, tq)
    a = tm[np.clip(j - 1, 0, len(tm) - 1)]
    b = tm[np.clip(j, 0, len(tm) - 1)]
    return np.minimum(np.abs(tq - a), np.abs(tq - b))


# ====================================================================================================== evaluators
def t1_eval(u: np.ndarray, v: np.ndarray, fast_inps: float, max_rel: float) -> dict:
    """T1 on paired clean seconds: d95 = Q95(v)/Q95(u) - 1 over all seconds and over the seconds with u > fast_inps; pass
    if both |d95| <= max_rel."""
    ok = np.isfinite(u) & np.isfinite(v)
    u, v = u[ok], v[ok]
    fa = u > fast_inps
    d_all = float(np.percentile(v, 95) / np.percentile(u, 95) - 1.0)
    d_fast = float(np.percentile(v[fa], 95) / np.percentile(u[fa], 95) - 1.0) if fa.sum() >= 20 else np.nan
    return {"d95_all": d_all, "d95_fast": d_fast, "n": int(len(u)), "n_fast": int(fa.sum()),
            "pass": bool(abs(d_all) <= max_rel and np.isfinite(d_fast) and abs(d_fast) <= max_rel)}


def t2_eval(t: np.ndarray, p: np.ndarray, jump_in: float, dt_s: float) -> dict:
    nj = int(len(FA.find_jumps(t, p, jump_in, dt_s)))
    return {"jumps": nj, "pass": nj == 0}


def t3_eval(lag_m: np.ndarray, lag_ref: np.ndarray, max_later: float) -> dict:
    """T3 (one-sided): median per-event lag change (events where both lags are defined) <= max_later."""
    dl = np.asarray(lag_m, float) - np.asarray(lag_ref, float)
    ok = np.isfinite(dl)
    med = float(np.median(dl[ok])) if ok.any() else np.nan
    return {"n_paired": int(ok.sum()), "dlag_med": med, "pass": bool(np.isfinite(med) and med <= max_later)}


# ====================================================================================================== one animal-period
def process(job: dict) -> dict:
    t_job = time.time()
    if P.HAVE_NUMBA:
        P.set_num_threads(1)
    cfg, acfg, dcfg, scfg = job["cfg"], job["acfg"], job["dcfg"], job["scfg"]
    animal, pkey, pi, ai, out = job["animal"], job["pkey"], int(job["pi"]), int(job["ai"]), Path(job["out"])
    ctx = _ctx(acfg)
    tz, tu = ctx["tz"], ctx["tuned"]
    pp = acfg["periods"][pkey]
    lo, hi = C.to_ms(pp["start"], tz), C.to_ms(pp["end"], tz)
    hi_s = (hi - lo) / 1000.0
    base = {"animal": animal, "period": pkey, "set": pp["set"], "kind": pp["kind"]}
    run = Path(cfg["audit_run"])
    mc, trim = acfg["metrics"], float(acfg["still"]["trim_s"])
    s1c, s2c, s5c = dcfg["s1"], dcfg["s2"], dcfg["s5"]
    vc, acc = cfg["v3"], cfg["acceptance"]
    jin, jdt = float(acc["T2_jump_in"]), float(acc["T2_jump_dt_s"])
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
    n = len(t_ms)
    t = (t_al - lo) / 1000.0
    t_abs = t_al / 1000.0
    inwin = (t >= 0) & (t < hi_s)
    core = (t >= 60.0) & (t < hi_s - 60.0)
    # ---- per-second IMU states, step states, analysis mask
    ps = pd.read_csv(run / "imu_seconds" / f"{animal}_{pkey}.csv.gz")
    secs = ps["sec"].to_numpy(np.int64)
    assert np.all(np.diff(secs) == 1), "imu_seconds not contiguous"
    ok_s = ps["ok"].to_numpy(bool)
    still_s = ps["still"].to_numpy(bool) & ok_s
    state = ps["state"].to_numpy(np.int8)
    rep["state_nonzero_where_not_ok"] = int(((state != 0) & ~ok_s).sum())
    fsec = np.floor(t_al / 1000.0).astype(np.int64)
    ok_f = DS.lookup(secs, ok_s, fsec, False)
    still_f = DS.lookup(secs, still_s, fsec, False)
    st_f = DS.lookup(secs, state, fsec, np.int8(0))
    st_mid, st_at = P.step_states(t_al, secs, state)
    loco = loco_steps(st_mid, int(vc["loco_state"]))
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    mid = (secs + 0.5) * 1000.0
    amask = ((mid >= lo) & (mid < hi) & ~C.in_any(mid, ctx["handling"]) & ~C.in_any(mid, ctx["silences"]) & (mid >= vf) & (mid < vu))
    am_f = DS.lookup(secs, amask, fsec, False)
    # ---- ZUPT intervals (relative seconds) and the ZUPT fix mask (no release)
    runs_abs = V1B.still_runs(still_s, secs)
    iv = (V1B.eroded(runs_abs, float(vc["min_run_s"]), float(vc["erode_s"])) * 1000.0 - lo) / 1000.0
    zupt = V1B.membership(t, iv)[1]
    # ---- context tracks (saved) + V1b's ZUPT masks
    with np.load(Path(cfg["v1b_run"]) / "tracks" / f"{animal}_{pkey}.npz") as zf:
        if not np.array_equal(zf["t_ms"].astype(np.int64), t_ms):
            raise RuntimeError(f"{animal} {pkey}: V1b track times differ")
        v1b_saved = zf["V1b"].astype(np.float64)
        v1b_zupt = zf["zupt"].astype(bool)
        v1b_nr = zf["zupt_nr"].astype(bool)
    with np.load(Path(cfg["default_smoother_run"]) / "tracks" / f"{animal}_{pkey}.npz") as zf:
        if not np.array_equal(zf["t_ms"].astype(np.int64), t_ms):
            raise RuntimeError(f"{animal} {pkey}: default-smoother track times differ")
        v2b_saved = zf["V2b"].astype(np.float64)
    rep["zupt_equals_V1b_noRelease_mask"] = bool(np.array_equal(zupt, v1b_nr))
    rep.update({"n_fix_win": int(inwin.sum()), "n_fix_zupt": int((zupt & inwin).sum()), "n_step_loco": int((loco & inwin).sum()),
                "iv_s": float((iv[:, 1] - iv[:, 0]).sum()) if len(iv) else 0.0, "n_iv": int(len(iv))})
    # ---- smoothers
    r2 = P.r2_from_anchors(A, ctx["table"])
    specs = kf_specs(tu, cfg)
    vis_all = np.ones(n, bool)
    none = np.zeros(n, bool)
    ones = np.ones(n)
    trk = {"raw": z, "V1b": v1b_saved, "V2b": v2b_saved}
    nis, wz = {}, {}
    for m in KF:
        sp = specs[m]
        Pk, _, nk, wk = kf_v3(t, z, r2, vis_all, zupt if sp["zupt"] else none, qmult(loco, sp["mloco"]), sp, tu)
        trk[m], nis[m], wz[m] = Pk, nk, wk
    # V1b rebuilt by this kernel (multiplier 1, V1b's final ZUPT mask, sigma 1.0 Huber): NIS + reproduction
    sp_v1b = {"q": specs["B2"]["q"], "mrej": specs["B2"]["mrej"], "sv": float(job["v1b_sigma"]), "huber_zupt": True}
    Pv1, _, nis["V1b"], _ = kf_v3(t, z, r2, vis_all, v1b_zupt, ones, sp_v1b, tu)
    dv = np.hypot(*(Pv1 - v1b_saved).T)
    rep["V1b_rebuilt_vs_saved_core_max_in"] = float(dv[core].max()) if core.any() else np.nan
    rep["V1b_rebuilt_vs_saved_all_max_in"] = float(dv.max())
    Pv1k, _, _, _ = V1B.kf_v1b(t, z, r2, vis_all, v1b_zupt, sp_v1b, tu)
    rep["kernel_vs_V1b_kernel_max_in"] = float(np.max(np.hypot(*(Pv1 - Pv1k).T)))
    # reproduction: the pilot kernel for B2 and for the x10 multiplier without ZUPT (= V3_loco)
    Pref, _, _ = P.kf_run(t, z, r2, [vis_all], [st_mid], [st_at],
                          [{"q": specs["B2"]["q"], "mrej": specs["B2"]["mrej"]},
                           {"q": specs["B2"]["q"], "mrej": specs["B2"]["mrej"], "mult": (1.0, 1.0, 1.0, specs["V3_loco"]["mloco"])}])
    rep["kernel_vs_pilot_B2_max_in"] = float(np.max(np.hypot(*(trk["B2"] - Pref[0]).T)))
    rep["kernel_vs_pilot_loco_max_in"] = float(np.max(np.hypot(*(trk["V3_loco"] - Pref[1]).T)))
    dsv = np.hypot(*(trk["B2"] - b2_saved).T)
    rep["B2_vs_saved_core_max_in"] = float(dsv[core].max()) if core.any() else np.nan
    rep["B2_vs_saved_all_max_in"] = float(dsv.max())
    d = {m: np.hypot(*(trk[m] - trk["B2"]).T) for m in VARS + ["V1b", "V2b"]}
    infl = infl_mask(zupt, loco)
    dinf = V1B.dist_to_mask(t, infl)
    house_f = V1B.house_mask(trk["B2"], houses, buf)
    (out / "tracks").mkdir(exist_ok=True)
    np.savez_compressed(out / "tracks" / f"{animal}_{pkey}.npz", t_ms=t_ms, t_al_ms=t_al, anchors=A.astype(np.int8),
                        **{m: trk[m].astype(np.float32) for m in KF}, zupt=zupt, loco_step=loco, infl=infl,
                        wz_V3=wz["V3"].astype(np.float32), **{f"nis_{m}": nis[m].astype(np.float32) for m in NIS_M},
                        inwin=inwin, amask=am_f, ok=ok_f, still=still_f, state=st_f, house=house_f, dinf=dinf.astype(np.float32),
                        **{f"d_{m}": d[m].astype(np.float32) for m in d})
    rep["wz_V3_lt1_share"] = float((wz["V3"][zupt & inwin] < 1.0).mean()) if (zupt & inwin).any() else np.nan
    # ---- per-second: S2 1-s speeds, distances to V3's changes, step-B speeds (nights)
    cs = (secs * 1000.0 + 500.0 - lo) / 1000.0
    dinf_s = dist_q(cs, t[infl])
    zs = V1B.membership(cs, iv)[1]
    vsec = {m: DS.second_speeds(t_abs, trk[m], secs, float(s2c["max_gap_s"])).astype(np.float32) for m in TRACKS}
    blk = ((secs * 1000.0 - lo) // (blk_s * 1000.0)).astype(np.int64)
    sec_d = {"sec": secs, "state": state, "ok": ok_s, "still": still_s, "mask": amask, "dinf": dinf_s.astype(np.float32), "zs": zs, "block": blk,
             **{f"v_{m}": v for m, v in vsec.items()}}
    if pkey in SP.nights(scfg):
        rc = scfg["reference"]
        sb = pd.read_csv(Path(cfg["speed_proxy_run"]) / "seconds" / f"{animal}_{pkey}.csv.gz")
        if not np.array_equal(sb["sec"].to_numpy(np.int64), secs):
            raise RuntimeError(f"{animal} {pkey}: step-B seconds differ from the audit's imu_seconds")
        cl = sb["clean"].to_numpy(bool)
        for m in TRACKS:
            w3, w1 = SP.track_speeds(t_abs, trk[m], secs, rc)
            sec_d[f"w3_{m}"], sec_d[f"w1_{m}"] = w3.astype(np.float32), w1.astype(np.float32)
        sec_d.update({"clean": cl, "u3": sb["u3"].to_numpy(np.float32), "u1": sb["u1"].to_numpy(np.float32),
                      "stepB_block": sb["block"].to_numpy(np.int64)})
        rep["stepB_block_equal"] = bool(np.array_equal(sb["block"].to_numpy(np.int64), blk))
        rep["n_clean"] = int(cl.sum())
        # this driver's estimator vs the values saved by step B (csv, 6 significant digits)
        for m, col in (("raw", "u3"), ("raw", "v3_raw"), ("B2", "v3_B2"), ("V1b", "v3_V1b"), ("V2b", "v3_V2b")):
            ref = sb[col].to_numpy(float)
            mm = cl & np.isfinite(ref)
            rep[f"stepB_{col}_vs_here_{m}_max"] = float(np.nanmax(np.abs(sec_d[f"w3_{m}"][mm].astype(float) - ref[mm]))) if mm.any() else np.nan
    (out / "seconds").mkdir(exist_ok=True)
    np.savez_compressed(out / "seconds" / f"{animal}_{pkey}.npz", **sec_d)
    # ---- certified segments (primary source): still metrics on >= 30 s, T2 jumps on all primary segments
    Sall = _segments(run)
    Sap = Sall[(Sall.animal == animal) & (Sall.period == pkey) & Sall.primary]
    mrows, frows, evrows, jrows, covrows, t2rows = [], [], [], [], [], []
    spd = {m: [] for m in TRACKS}
    spd_idx = {m: [] for m in TRACKS}
    seg_ids = []
    n_bad = 0
    jall = {m: 0 for m in TRACKS}
    j30 = {m: 0 for m in TRACKS}
    for r in Sap.itertuples():
        ts, te = (r.t0_ms - lo) / 1000.0 + trim, (r.t1_ms - lo) / 1000.0 - trim
        i0, i1 = np.searchsorted(t, [ts, te])
        for m in TRACKS:
            jk = FA.find_jumps(t[i0:i1], trk[m][i0:i1], jin, jdt)
            jall[m] += int(len(jk))
            if r.ge30:
                j30[m] += int(len(jk))
            for kk in jk:
                jrows.append({"seg_id": r.seg_id, **base, "ge30": bool(r.ge30), "method": m, "t_ms": lo + 0.5 * (t[i0 + kk] + t[i0 + kk + 1]) * 1000,
                              "size_in": float(np.hypot(*(trk[m][i0 + kk + 1] - trk[m][i0 + kk])))})
        if not (r.scored and r.ge30):
            continue
        n_bad += int((i1 - i0) != r.n_fix)
        truth = np.array([r.truth_x, r.truth_y])
        sub = {m: trk[m][i0:i1] for m in TRACKS}
        res, evs, _, speeds = FA.score_segment(t[i0:i1], sub, truth, ts, te, mc, TRACKS)
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
        dur = te - ts
        covrows.append({"seg_id": r.seg_id, **base, "dur_trim_s": dur, "zone": r.zone, "cov_V3": V1B.overlap_time(iv, ts, te) / dur,
                        "fcov_V3": float(zupt[i0:i1].mean()) if i1 > i0 else np.nan})
        seg_ids.append(r.seg_id)
        for m in TRACKS:
            spd[m].append(speeds[m])
            spd_idx[m].append(np.full(len(speeds[m]), len(seg_ids) - 1, np.int32))
    if seg_ids:
        (out / "speeds").mkdir(exist_ok=True)
        np.savez_compressed(out / "speeds" / f"{animal}_{pkey}.npz", seg_ids=np.array(seg_ids),
                            **{m: np.concatenate(spd[m]) for m in TRACKS}, **{f"idx_{m}": np.concatenate(spd_idx[m]) for m in TRACKS})
    for m in TRACKS:
        t2rows.append({**base, "method": m, "n_seg_primary": int(len(Sap)), "n_seg_ge30": int((Sap.scored & Sap.ge30).sum()),
                       "jumps_primary": jall[m], "jumps_ge30": j30[m]})
    rep["n_seg_primary"], rep["n_seg30"], rep["n_seg_fixcount_mismatch"] = int(len(Sap)), int(len(seg_ids)), n_bad
    # ---- T2 over the analysis mask (pair midpoint second)
    j4 = []
    for m in TRACKS:
        jk = FA.find_jumps(t, trk[m], jin, jdt)
        jk = jk[inwin[jk] & inwin[np.minimum(jk + 1, n - 1)]]
        sj = np.floor((0.5 * (t[jk] + t[jk + 1]) * 1000.0 + lo) / 1000.0).astype(np.int64)
        j4.append({**base, "method": m, "jumps_win": int(len(jk)), "jumps_mask": int(DS.lookup(secs, amask, sj, False).sum()),
                   "jumps_imu_ok": int(DS.lookup(secs, ok_s, sj, False).sum())})
    # ---- T3: S5 onset / offset lags (default-smoother definition)
    erows = []
    for e in DS.transition_events(state, secs, lo, hi, s5c):
        anchor = e["rb"] if e["kind"] == "onset" else e["ra"]
        row = {**base, **e, "block": int(anchor // blk_s)}
        for m in TRACKS:
            row[f"lag_{m}"], row[f"lagloco_{m}"] = DS.event_lag(t, trk[m], e, s5c)
        erows.append(row)
    # ---- S1: held-out fixes (default-smoother masks and seeds); the ZUPT / loco masks do not depend on the fixes
    seed = int(s1c["seed"])
    hid = DS.hidden_masks(n, seed + 100 * pi + ai, seed + 50_000 + 100 * pi + ai, int(s1c["s_every"]))
    s1out = {}
    for sch in ("a", "s"):
        h = hid[sch]
        vis = ~h
        sc = h & inwin & (A >= float(s1c["min_anchors"])) & ok_f
        dd = {"i": np.flatnonzero(sc).astype(np.int32), "block": np.floor(t[sc] / blk_s).astype(np.int32), "still": still_f[sc],
              "moving": ok_f[sc] & ~still_f[sc], "loco": st_f[sc] == 3, "anchors": A[sc].astype(np.int8), "zupt": zupt[sc]}
        for m in S1_M:
            sp = specs[m]
            Ph, _, _, _ = kf_v3(t, z, r2, vis, zupt if sp["zupt"] else none, qmult(loco, sp["mloco"]), sp, tu)
            dd[f"e_{m}"] = np.hypot(*(z[sc] - Ph[sc]).T).astype(np.float32)
        s1out[sch] = dd
    (out / "s1").mkdir(exist_ok=True)
    np.savez_compressed(out / "s1" / f"{animal}_{pkey}.npz", **{f"{s}__{k}": v for s, dd in s1out.items() for k, v in dd.items()})
    # ---- fallback share
    fb = {**base, "n_fix_win": int(inwin.sum()), "n_fix_win_imu_fail": int((inwin & ~ok_f).sum()),
          "n_fix_mask": int((inwin & am_f).sum()), "n_fix_mask_imu_fail": int((inwin & am_f & ~ok_f).sum()),
          "n_fix_mask_zupt": int((inwin & am_f & zupt).sum()), "n_fix_mask_loco_step": int((inwin & am_f & loco).sum())}
    rep["runtime_s"] = round(time.time() - t_job, 1)
    return {"rep": rep, "fb": pd.DataFrame([fb]), "metrics": pd.DataFrame(mrows), "fixes": pd.concat(frows, ignore_index=True) if frows else pd.DataFrame(),
            "events": pd.DataFrame(evrows), "jumps": pd.DataFrame(jrows), "coverage": pd.DataFrame(covrows), "t2still": pd.DataFrame(t2rows),
            "t2mask": pd.DataFrame(j4), "s5": pd.DataFrame(erows)}


def _process_safe(job: dict) -> dict:
    try:
        return process(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


def _warm() -> None:
    """Compile (or load the cached) kernels before the pool starts."""
    t = np.arange(20, dtype=float) * 0.2
    z = np.zeros((20, 2))
    kf_v3(t, z, np.ones((20, 2)), np.ones(20, bool), np.ones(20, bool), np.ones(20), {"q": 3.0, "sv": 1.0, "huber_zupt": True, "mrej": 1e9}, {})
    V1B._warm()


# ====================================================================================================== compute run
def run_compute(cfg: dict, workers: int) -> Path:
    t0 = time.time()
    acfg, dcfg, scfg, v1c = load_acfg(cfg), load_dcfg(cfg), load_scfg(cfg), load_v1bcfg(cfg)
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    (out / "tables").mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; audit run {cfg['audit_run']}; numba {P.HAVE_NUMBA}")
    tu = _ctx(acfg)["tuned"]
    log_to(fh, f"pilot tuned V2 multipliers {tu['V2']['mult']} -> m_loco {tu['V2']['mult'][3]} (V3 uses {cfg['v3']['loco_mult']}); "
               f"B2 q {tu['B2']['q']}; V1b sigma_ZUPT {v1c['v1b']['sigma_zupt_inps']}")
    _warm()
    jobs = [{"cfg": cfg, "acfg": acfg, "dcfg": dcfg, "scfg": scfg, "v1b_sigma": float(v1c["v1b"]["sigma_zupt_inps"]), "animal": a, "pkey": pk,
             "out": str(out), "pi": pi, "ai": ai} for pi, pk in enumerate(acfg["periods"]) for ai, a in enumerate(acfg["animals"])]
    res = []
    with ProcessPoolExecutor(max_workers=max(1, min(16, workers))) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                continue
            rp = r["rep"]
            log_to(fh, f"{rp['animal']} {rp['period']}: {rp['n_fix_win']:,} window fixes, ZUPT fixes {rp['n_fix_zupt']:,}, loco steps {rp['n_step_loco']:,}; "
                       f"kernel vs pilot B2 {rp['kernel_vs_pilot_B2_max_in']:.2e} / loco {rp['kernel_vs_pilot_loco_max_in']:.2e} in, vs saved B2 (core) "
                       f"{rp['B2_vs_saved_core_max_in']:.2e} in, V1b rebuilt vs saved (core) {rp['V1b_rebuilt_vs_saved_core_max_in']:.2e} in, {rp['runtime_s']} s")
            res.append(r)
    if len(res) != len(jobs):
        log_to(fh, f"WARNING: {len(jobs) - len(res)} jobs failed")
    tb = out / "tables"
    pd.DataFrame([r["rep"] for r in res]).to_csv(tb / "reproduction_tracks.csv", index=False)
    for key, f in (("fb", "fallback_jobs.csv"), ("metrics", "still_metrics.csv.gz"), ("fixes", "still_fixes.csv.gz"), ("events", "still_events.csv"),
                   ("jumps", "t2_still_jump_list.csv"), ("coverage", "zupt_coverage_segments.csv.gz"), ("t2still", "t2_still_jumps_jobs.csv"),
                   ("t2mask", "t2_mask_jumps_jobs.csv"), ("s5", "t3_events.csv.gz")):
        parts = [r[key] for r in res if r[key] is not None and len(r[key])]
        (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()).to_csv(tb / f, index=False)
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "audit_config": cfg["audit_config"], "audit_run": cfg["audit_run"],
            "default_smoother_config": cfg["default_smoother_config"], "default_smoother_run": cfg["default_smoother_run"],
            "v1b_config": cfg["v1b_config"], "v1b_run": cfg["v1b_run"], "speed_proxy_config": cfg["speed_proxy_config"],
            "speed_proxy_run": cfg["speed_proxy_run"], "smoothing_config": cfg["smoothing_config"], "fix_cache_root": cfg["fix_cache_root"],
            "git_commit": C.git_commit(),
            "run_manifests": {k: json.loads((Path(cfg[k]) / "run_manifest.json").read_text(encoding="utf-8"))
                              for k in ("audit_run", "default_smoother_run", "v1b_run", "speed_proxy_run")},
            "tuned_B2": tu["B2"], "tuned_V2_mult": tu["V2"]["mult"], "irls": {k: tu[k] for k in ("huber_k", "gate2", "n_irls")},
            "tau_star_s": _ctx(acfg)["taus"], "v3": cfg["v3"], "variants": cfg["variants"], "acceptance": cfg["acceptance"],
            "numba": P.HAVE_NUMBA, "workers": workers, "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    fh.close()
    return out


# ====================================================================================================== aggregation helpers
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


def t1_tables(D: pd.DataFrame, scfg: dict, nb: int, rng, sets=SETS3, bands=BANDS, tracks=TRACKS) -> pd.DataFrame:
    """Step B's R1 code path on its clean seconds: every track's speed quantiles vs the clean reference, per scale x set x
    band, paired 10-min block bootstrap (SP.ratio_table)."""
    rs = scfg["rescoring"]
    rows = []
    for scale in SCALES:
        u_all = D[f"u{scale}"].to_numpy(float)
        V = {m: D[f"w{scale}_{m}"].to_numpy(float) for m in tracks}
        paired = D["clean"].to_numpy(bool) & np.isfinite(u_all) & np.all([np.isfinite(v) for v in V.values()], axis=0)
        for s in sets:
            sm = paired & ((D["set"] == s).to_numpy() if s != "all" else True)
            for band in bands:
                m = sm & SP.band_mask(u_all, band, rs["bands_inps"])
                if m.sum() < 20:
                    continue
                rows.extend(SP.ratio_table(D[m], u_all[m], {k: v[m] for k, v in V.items()}, nb, rng, True, {"scale": scale, "set": s, "band": band}))
    return pd.DataFrame(rows)


def t3_table(EV: pd.DataFrame, sets: list, max_later: float, nb: int, rng) -> pd.DataFrame:
    """S5 lags per set x kind x periods x method: median lag, paired median change vs B2 (one-sided criterion) with a
    block-bootstrap CI, the shares of later / earlier events."""
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
                for m in TRACKS:
                    lag = dd[f"lag_{m}"].to_numpy(float)
                    ev_ = t3_eval(lag, lb, max_later)
                    dl = lag - lb
                    ok = np.isfinite(dl)
                    ch = ok & (np.abs(np.nan_to_num(dl)) > 1e-9)
                    row = {"set": s, "kind": kind, "periods": per, "method": m, "n_events": int(len(dd)), "n_defined": int(np.isfinite(lag).sum()),
                           "lag_med": float(np.nanmedian(lag)) if np.isfinite(lag).any() else np.nan,
                           "n_B2_only": int((np.isfinite(lb) & ~np.isfinite(lag)).sum()), "n_m_only": int((~np.isfinite(lb) & np.isfinite(lag)).sum()),
                           "n_paired": ev_["n_paired"], "dlag_med": ev_["dlag_med"], "pass": ev_["pass"],
                           "n_changed": int(ch.sum()), "n_later": int((ch & (np.nan_to_num(dl) > 0)).sum()), "n_earlier": int((ch & (np.nan_to_num(dl) < 0)).sum()),
                           "n_later_gt05": int((ok & (np.nan_to_num(dl) > 0.5)).sum()),
                           "dlag_med_changed": float(np.median(dl[ch])) if ch.any() else np.nan}
                    if ok.sum() >= 5:
                        wb = DS.wmedian_boot(dl[ok], blk[ok], cnt)
                        row.update({"dlag_lo": float(np.nanpercentile(wb[1:], 2.5)), "dlag_hi": float(np.nanpercentile(wb[1:], 97.5)),
                                    "dlag_mean": float(np.mean(dl[ok])), "share_changed": float(ch.sum() / ok.sum()),
                                    "share_later": float((ch & (np.nan_to_num(dl) > 0)).sum() / ok.sum()),
                                    "share_earlier": float((ch & (np.nan_to_num(dl) < 0)).sum() / ok.sum())})
                    rows.append(row)
    return pd.DataFrame(rows)


def speed_ratio_rows(dd: pd.DataFrame, cols: dict, ref: str, nb: int, rng, keys: dict) -> list:
    """p50 / p95 of each series in cols and their ratio - 1 to the series `ref` (paired block bootstrap, SP.ratio_table)."""
    if len(dd) < 20:
        return []
    rr = SP.ratio_table(dd, dd[cols[ref]].to_numpy(float), {m: dd[c].to_numpy(float) for m, c in cols.items()}, nb, rng, False, keys)
    return rr


# ====================================================================================================== aggregation
def aggregate(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    acfg, dcfg, scfg = load_acfg(cfg), load_dcfg(cfg), load_scfg(cfg)
    tb = out / "tables"
    bc = cfg["bootstrap"]
    nb = int(bc["n_boot"])
    rngs = {k: np.random.default_rng(int(bc["seed"]) + i) for i, k in enumerate(("t1", "t3", "still", "s1", "jit", "anim", "jit2", "pfix"))}
    acc = cfg["acceptance"]
    thr = float(acc["T1_max_abs_rel"])
    sets = ["calm", "rain"]
    pset = {k: v["set"] for k, v in acfg["periods"].items()}
    pkind = {k: v["kind"] for k, v in acfg["periods"].items()}
    A: dict = {"cfg": cfg, "acfg": acfg}
    rep_tr = pd.read_csv(tb / "reproduction_tracks.csv")
    A["rep_tr"] = rep_tr
    # ---------------- per-fix arrays: ZUPT stats, NIS, jitter (i) positions
    keys = ["anchors", "inwin", "amask", "ok", "still", "state", "house", "zupt", "loco_step", "dinf", "wz_V3"] + \
           [f"nis_{m}" for m in NIS_M] + [f"d_{m}" for m in VARS + ["V1b", "V2b"]]
    FX = _read_npz_dir(out / "tracks", keys + ["t_al_ms"])
    lo_map = {k: C.to_ms(v["start"], acfg["tz"]) for k, v in acfg["periods"].items()}
    FX["set"] = FX["period"].map(pset)
    FX["block"] = ((FX["t_al_ms"] - FX["period"].map(lo_map)) // (float(bc["block_s"]) * 1000.0)).astype(np.int64)
    zstats = {}
    for s in sets:
        g = FX[(FX["set"] == s) & FX["inwin"].astype(bool) & FX["amask"].astype(bool)]
        zz = g["zupt"].astype(bool)
        zstats[s] = {"n_fix": int(len(g)), "zupt_share": float(zz.mean()), "loco_step_share": float(g["loco_step"].astype(bool).mean()),
                     "imu_fail_share": float((~g["ok"].astype(bool)).mean()),
                     "wz_lt1_share": float((g.loc[zz, "wz_V3"] < 1.0).mean()) if zz.any() else np.nan,
                     "wz_p01": float(np.percentile(g.loc[zz, "wz_V3"], 1)) if zz.any() else np.nan}
    A["zstats"] = zstats
    # NIS
    pop = FX["inwin"].astype(bool) & FX["amask"].astype(bool)
    G = FX[pop].copy()
    G["abin"] = FA.anchor_bin(G["anchors"].to_numpy())
    G["zone"] = np.where(G["house"].astype(bool), "house", "outside")
    G["imu"] = np.where(~G["ok"].astype(bool), "QC failed", G["state"].map(STATE_NAME).fillna("QC failed"))
    q95 = float(cfg["nis"]["chi2_2_q95"])
    nr = []
    for m in NIS_M:
        col = f"nis_{m}"
        for by in (["set", "imu"], ["set", "abin", "imu"], ["set", "abin", "zone", "imu"], ["set", "abin", "zone"], ["set"], ["set", "anchors"]):
            g = G.dropna(subset=[col]).groupby(by)[col]
            t_ = pd.DataFrame({"n": g.size(), "mean": g.mean(), "median": g.median(), "gt95": g.apply(lambda x: float((x > q95).mean()))}).reset_index()
            t_.insert(0, "by", "×".join(by))
            t_.insert(0, "method", m)
            nr.append(t_)
    NIS = pd.concat(nr, ignore_index=True)
    NIS.to_csv(tb / "nis.csv", index=False)
    del G
    # jitter (i), positions: IMU-active fixes >= min_dist from any loco step / ZUPT fix
    md = float(cfg["jitter_check"]["min_dist_s"])
    base_i = (FX["inwin"].astype(bool) & FX["amask"].astype(bool) & FX["ok"].astype(bool) & (FX["state"] == 2)).to_numpy()
    jp = []
    for s in sets:
        sm = base_i & (FX["set"] == s).to_numpy()
        far = sm & (FX["dinf"].to_numpy(float) >= md)
        blk, K = DS.block_codes(FX["animal"].to_numpy()[far], FX["period"].to_numpy()[far], FX["block"].to_numpy()[far])
        cnt = FA.boot_counts(K, nb, rngs["pfix"])
        for m in VARS + ["V1b", "V2b"]:
            x = FX[f"d_{m}"].to_numpy(float)[far]
            row = {"set": s, "method": m, "n_active": int(sm.sum()), "n_far": int(far.sum()), "share_far": float(far.sum() / max(sm.sum(), 1))}
            if len(x):
                q = np.percentile(x, [50, 95, 99])
                qb = DS.hist_boot_q(x, blk, cnt, V1B.E1_EDGES, [0.99])[:, 0]
                row.update({"p50": float(q[0]), "p95": float(q[1]), "p99": float(q[2]), "max": float(x.max()),
                            "p99_lo": float(np.nanpercentile(qb[1:], 2.5)), "p99_hi": float(np.nanpercentile(qb[1:], 97.5))})
            jp.append(row)
    JP = pd.DataFrame(jp)
    JP.to_csv(tb / "jitter_active_position.csv", index=False)
    del FX
    log_to(fh, f"per-fix tables done ({time.time() - t0:.0f} s)")
    # ---------------- per-second arrays
    SE = _read_npz_dir(out / "seconds")
    SE["set"] = SE["period"].map(pset)
    SE["kind"] = SE["period"].map(pkind)
    for c in ("clean", "ok", "still", "mask", "zs"):
        SE[c] = SE[c].fillna(False).astype(bool) if c in SE else False
    # T1
    D = SE[SE["clean"]].copy()
    T1 = t1_tables(D, scfg, nb, rngs["t1"])
    T1["pass_d95"] = T1["d95"].abs() <= thr
    T1.to_csv(tb / "t1_speed.csv", index=False)
    arows = []
    for a in sorted(D["animal"].unique()):
        Da = D[D["animal"] == a]
        rr = t1_tables(Da, scfg, nb, rngs["anim"], sets=("all",), bands=("all", "5to15", "gt15"))
        rr.insert(0, "animal", a)
        arows.append(rr)
    T1A = pd.concat(arows, ignore_index=True)
    T1A.to_csv(tb / "t1_by_animal.csv", index=False)
    # reproduction of step B's R1 rows (B2 / V1b / V2b / raw)
    R1 = pd.read_csv(Path(cfg["speed_proxy_run"]) / "tables" / "r1_clean_reference.csv")
    Rm = T1[T1.track.isin(["raw", "B2", "V1b", "V2b"])].merge(R1, on=["scale", "set", "band", "track"], suffixes=("", "_B"))
    Rm["dd50_pp"] = 100 * (Rm["d50"] - Rm["d50_B"]).abs()
    Rm["dd95_pp"] = 100 * (Rm["d95"] - Rm["d95_B"]).abs()
    Rm["n_equal"] = Rm["n_sec"] == Rm["n_sec_B"]
    Rm[["scale", "set", "band", "track", "n_sec", "n_sec_B", "d50", "d50_B", "d95", "d95_B", "dd50_pp", "dd95_pp", "n_equal"]].to_csv(tb / "t1_repro_stepB.csv", index=False)
    rep_t1 = {"n_rows": int(len(Rm)), "max_dd50_pp": float(Rm.dd50_pp.max()), "max_dd95_pp": float(Rm.dd95_pp.max()), "n_equal_all": bool(Rm.n_equal.all()),
              "pass": bool(Rm.dd50_pp.max() <= 0.1 and Rm.dd95_pp.max() <= 0.1)}
    A["rep_t1"] = rep_t1
    log_to(fh, f"T1 done ({time.time() - t0:.0f} s); step-B R1 reproduction max |d50 diff| {rep_t1['max_dd50_pp']:.4f} pp, |d95 diff| {rep_t1['max_dd95_pp']:.4f} pp")
    # jitter (ii): clean seconds, IMU-locomoting, reference below the floor p95
    FLt = pd.read_csv(Path(cfg["speed_proxy_run"]) / "tables" / "noise_floor.csv")
    floor95 = float(FLt[(FLt.kind == "all") & (FLt.set == "all") & (FLt.scale == 3)].p95.iloc[0])
    jr = []
    for s in SETS3:
        dd = D[((D.set == s) if s != "all" else True) & (D.state == 3) & (D.u3 < floor95)]
        dd = dd[np.isfinite(dd[[f"v_{m}" for m in TRACKS]].to_numpy(float)).all(axis=1)]
        for kind_, pref in (("S2 1-s speed", "v_"), ("step-B 1-s speed v1", "w1_")):
            d2 = dd[np.isfinite(dd[[f"{pref}{m}" for m in TRACKS]].to_numpy(float)).all(axis=1)]
            for r in speed_ratio_rows(d2, {m: f"{pref}{m}" for m in TRACKS}, "B2", nb, rngs["jit2"], {"set": s, "speed": kind_}):
                jr.append(r)
    JR = pd.DataFrame(jr)
    JR.to_csv(tb / "jitter_inplace_speed.csv", index=False)
    # jitter (i), speeds: IMU-active seconds >= min_dist + 0.5 s (centre) from V3's changes
    ji = []
    sel_i = SE["mask"] & SE["ok"] & (SE["state"] == 2) & (SE["dinf"].astype(float) >= md + 0.5)
    for s in sets:
        dd = SE[sel_i & (SE.set == s)]
        dd = dd[np.isfinite(dd[[f"v_{m}" for m in TRACKS]].to_numpy(float)).all(axis=1)]
        for r in speed_ratio_rows(dd, {m: f"v_{m}" for m in TRACKS}, "B2", nb, rngs["jit"], {"set": s}):
            r["n_active_mask"] = int((SE["mask"] & SE["ok"] & (SE["state"] == 2) & (SE.set == s)).sum())
            ji.append(r)
    JI = pd.DataFrame(ji)
    JI.to_csv(tb / "jitter_active_speed.csv", index=False)
    del SE
    log_to(fh, f"jitter checks done ({time.time() - t0:.0f} s); floor p95 {floor95:.3f} in/s")
    # ---------------- T3 (S5)
    EV = pd.read_csv(tb / "t3_events.csv.gz")
    T3 = t3_table(EV, sets, float(acc["T3_max_later_s"]), nb, rngs["t3"])
    T3.to_csv(tb / "t3_lags.csv", index=False)
    log_to(fh, f"T3 done ({time.time() - t0:.0f} s)")
    # ---------------- still metrics (circular) + S3 + coverage
    run = Path(cfg["audit_run"])
    Saud = _segments(run)
    S = Saud[Saud.primary & Saud.scored & Saud.ge30].reset_index(drop=True)
    M = pd.read_csv(tb / "still_metrics.csv.gz")
    F = pd.read_csv(tb / "still_fixes.csv.gz")
    SPD = DS.load_speeds_multi(out / "speeds", S, TRACKS)
    pooled = pd.DataFrame([{"set": s, **FA.still_summary(S[S.set == s], M, F, SPD, m, S)} for s in sets for m in TRACKS])
    setkind = pd.DataFrame([{"set": s, "kind": k, **FA.still_summary(S[(S.set == s) & (S.kind == k)], M, F, SPD, m, S)}
                            for s in sets for k in ("day", "night") for m in TRACKS])
    pooled.to_csv(tb / "still_pooled.csv", index=False)
    setkind.to_csv(tb / "still_setkind.csv", index=False)
    brow = []
    for s in sets:
        gs = S[S.set == s]
        st, cnt, K = {}, None, 0
        for m in TRACKS:
            Ab = FA.block_arrays(gs, M, F, SPD, m, S)
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
    V1C = pd.read_csv(Path(cfg["v1b_run"]) / "tables" / "zupt_coverage.csv")
    cov = []
    for s in sets:
        for k in ("all", "day", "night"):
            g = CV[(CV.set == s) & ((CV.kind == k) if k != "all" else True)]
            w_ = g["dur_trim_s"].to_numpy(float)
            v1 = V1C[(V1C.set == s) & (V1C.kind == k)]
            cov.append({"set": s, "kind": k, "n_seg": int(len(g)), "still_h": float(w_.sum() / 3600),
                        "cov_V3": float((g["cov_V3"] * w_).sum() / w_.sum()) if w_.sum() else np.nan,
                        "fcov_V3": float(np.nanmean(g["fcov_V3"])) if len(g) else np.nan,
                        "cov_V1b": float(v1.cov_V1b.iloc[0]) if len(v1) else np.nan,
                        "house_share_h": float((g.zone == "house").astype(float).mul(w_).sum() / w_.sum()) if w_.sum() else np.nan})
    COV = pd.DataFrame(cov)
    COV.to_csv(tb / "zupt_coverage.csv", index=False)
    # reproduction of still rows: raw / B2 vs the audit, V1b vs the V1b run, V2b vs the default-smoother run
    cols_ = ("rms_in", "drift10_in", "path_in_per_min", "crazy_n", "jumps", "speed_p95")
    Ma = pd.read_csv(run / "tables" / "segment_metrics.csv.gz")
    Mv = pd.read_csv(Path(cfg["v1b_run"]) / "tables" / "still_metrics.csv.gz")
    Md = pd.read_csv(Path(cfg["default_smoother_run"]) / "tables" / "still_metrics_new.csv.gz")
    rep_still = {}
    for lab, ref, meths in (("raw/B2 vs audit", Ma, ["raw", "B2"]), ("V1b vs V1b run", Mv, ["V1b"]), ("V2b vs default-smoother run", Md, ["V2b"])):
        Rm_ = M[M.method.isin(meths)].merge(ref[ref.seg_id.isin(set(S.seg_id)) & ref.method.isin(meths)], on=["seg_id", "method"], suffixes=("", "_ref"))
        rep_still[lab] = {"n_rows": int(len(Rm_)), **{c: float(np.nanmax(np.abs(Rm_[c] - Rm_[f"{c}_ref"]))) for c in cols_}}
    A["rep_still"] = rep_still
    log_to(fh, f"still tables done ({time.time() - t0:.0f} s)")
    # ---------------- T2
    J2s = pd.read_csv(tb / "t2_still_jumps_jobs.csv")
    J2m = pd.read_csv(tb / "t2_mask_jumps_jobs.csv")
    T2s = J2s.groupby(["set", "method"])[["jumps_primary", "jumps_ge30", "n_seg_primary", "n_seg_ge30"]].sum().reset_index()
    T2m = J2m.groupby(["set", "kind", "method"])[["jumps_win", "jumps_mask", "jumps_imu_ok"]].sum().reset_index()
    T2s.to_csv(tb / "t2_still_jumps.csv", index=False)
    T2m.to_csv(tb / "t2_mask_jumps.csv", index=False)
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
                mb = float(np.median(dd["e_B2"]))
                row = {"set": s, "scheme": sch, "subset": subn, "n": int(len(dd)), "med_B2": mb, "zupt_share": float(dd["zupt"].astype(bool).mean()),
                       "rmse_B2": float(np.sqrt(np.mean(dd["e_B2"].astype(float) ** 2)))}
                if subn == "moving":
                    blk, K = DS.block_codes(dd["animal"], dd["period"], dd["block"])
                    cnt = FA.boot_counts(K, nb, rngs["s1"])
                    qr = DS.hist_boot_q(dd["e_B2"].to_numpy(float), blk, cnt, DS.S1_EDGES, [0.5])[:, 0]
                    row["n_blocks"] = K
                for m in S1_M[1:]:
                    mv = float(np.median(dd[f"e_{m}"]))
                    row.update({f"med_{m}": mv, f"D_{m}": 1.0 - mv / mb, f"rmse_{m}": float(np.sqrt(np.mean(dd[f"e_{m}"].astype(float) ** 2)))})
                    if subn == "moving":
                        qm = DS.hist_boot_q(dd[f"e_{m}"].to_numpy(float), blk, cnt, DS.S1_EDGES, [0.5])[:, 0]
                        b = 1.0 - qm[1:] / qr[1:]
                        row.update({f"D_{m}_lo": float(np.nanpercentile(b, 2.5)), f"D_{m}_hi": float(np.nanpercentile(b, 97.5))})
                rows.append(row)
    S1 = pd.DataFrame(rows)
    S1.to_csv(tb / "s1_heldout.csv", index=False)
    del E
    # ---------------- fallback share
    FB = pd.read_csv(tb / "fallback_jobs.csv")
    fbs = []
    for s in sets + ["all"]:
        g = FB[(FB.set == s) if s != "all" else np.ones(len(FB), bool)]
        fbs.append({"set": s, "n_fix_mask": int(g.n_fix_mask.sum()), "imu_fail_share": float(g.n_fix_mask_imu_fail.sum() / g.n_fix_mask.sum()),
                    "zupt_share": float(g.n_fix_mask_zupt.sum() / g.n_fix_mask.sum()), "loco_step_share": float(g.n_fix_mask_loco_step.sum() / g.n_fix_mask.sum()),
                    "imu_fail_share_win": float(g.n_fix_win_imu_fail.sum() / g.n_fix_win.sum())})
    FBS = pd.DataFrame(fbs)
    FBS.to_csv(tb / "fallback_share.csv", index=False)
    log_to(fh, f"T2 / S1 / fallback done ({time.time() - t0:.0f} s)")
    # ---------------- reproduction vs the default-smoother and V1b runs
    drun = Path(cfg["default_smoother_run"])
    dsr = {}
    try:
        dev = pd.read_csv(drun / "tables" / "s5_events.csv.gz")
        dsr["events"] = {f"{s} {k}": {"here": int(((EV.set == s) & (EV.kind == k)).sum()), "default_smoother": int(((dev.set == s) & (dev.kind == k)).sum())}
                         for s in sets for k in ("onset", "offset")}
        d5 = pd.read_csv(drun / "tables" / "s5_lags.csv")
        dsr["B2_lag_med"] = {f"{s} {k}": {"here": float(T3[(T3.set == s) & (T3.kind == k) & (T3.periods == "all") & (T3.method == "B2")].lag_med.iloc[0]),
                                          "default_smoother": float(d5[(d5.set == s) & (d5.kind == k) & (d5.periods == "all") & (d5.method == "B2")].lag_med.iloc[0])}
                             for s in sets for k in ("onset", "offset")}
        dsr["V2b_lag_med"] = {f"{s} {k}": {"here": float(T3[(T3.set == s) & (T3.kind == k) & (T3.periods == "all") & (T3.method == "V2b")].lag_med.iloc[0]),
                                           "default_smoother": float(d5[(d5.set == s) & (d5.kind == k) & (d5.periods == "all") & (d5.method == "V2b")].lag_med.iloc[0])}
                              for s in sets for k in ("onset", "offset")}
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
    v1r = {}
    try:
        nv = pd.read_csv(Path(cfg["v1b_run"]) / "tables" / "nis.csv")
        v1r["nis_mean_by_set"] = {f"{m} {s}": {"here": float(NIS[(NIS.method == m) & (NIS.by == "set") & (NIS.set == s)]["mean"].iloc[0]),
                                               "v1b_run": float(nv[(nv.method == m) & (nv.by == "set") & (nv.set == s)]["mean"].iloc[0])}
                                  for m in ("B2", "V1b") for s in sets}
        sv = pd.read_csv(Path(cfg["v1b_run"]) / "tables" / "still_pooled.csv")
        v1r["V1b_fake_path"] = {s: {"here": float(pooled[(pooled.set == s) & (pooled.method == "V1b")].path_in_per_min.iloc[0]),
                                    "v1b_run": float(sv[(sv.set == s) & (sv.method == "V1b")].path_in_per_min.iloc[0])} for s in sets}
    except Exception as e:  # noqa: BLE001
        v1r["error"] = f"{type(e).__name__}: {e}"
    A["repro_v1b"] = v1r
    # ---------------- verdict
    ver = {}
    for m in SMOOTHED:
        r_all = T1[(T1.scale == int(acc["T1_scale_s"])) & (T1.set == acc["T1_set"]) & (T1.band == "all") & (T1.track == m)].iloc[0]
        r_fast = T1[(T1.scale == int(acc["T1_scale_s"])) & (T1.set == acc["T1_set"]) & (T1.band == "gt15") & (T1.track == m)].iloc[0]
        t3r = T3[(T3.method == m) & (T3.periods == "all")]
        sj = int(T2s[T2s.method == m].jumps_primary.sum())
        sj30 = int(T2s[T2s.method == m].jumps_ge30.sum())
        mj = int(T2m[T2m.method == m].jumps_mask.sum())
        v = {"T1": bool(abs(r_all.d95) <= thr and abs(r_fast.d95) <= thr),
             "T1_d95_all": float(r_all.d95), "T1_d95_all_ci": [float(r_all.d95_lo), float(r_all.d95_hi)],
             "T1_d95_gt15": float(r_fast.d95), "T1_d95_gt15_ci": [float(r_fast.d95_lo), float(r_fast.d95_hi)],
             "T2": bool(sj == 0 and mj == 0), "T2_still_jumps": sj, "T2_still_jumps_ge30": sj30, "T2_mask_jumps": mj,
             "T2_mask_jumps_by_period": {f"{r.animal} {r.period}": int(r.jumps_mask) for r in J2m[J2m.method == m].itertuples() if r.jumps_mask > 0},
             "T3": bool(len(t3r) == 4 and t3r["pass"].all()), "T3_dlag": {f"{r.set} {r.kind}": float(r.dlag_med) for r in t3r.itertuples()}}
        v["pass_all"] = v["T1"] and v["T2"] and v["T3"]
        v["failed"] = [k for k in ("T1", "T2", "T3") if not v[k]]
        ver[m] = v
    dec = {"V3_passes": ver["V3"]["pass_all"], "failed_criteria": ver["V3"]["failed"],
           "default_implanted": "V3" if ver["V3"]["pass_all"] else "V1b", "universal_baseline": "B2",
           "variants_that_would_pass": [m for m in SENS if ver[m]["pass_all"]],
           "context_outcomes": {m: ("pass" if ver[m]["pass_all"] else "fail " + ", ".join(ver[m]["failed"])) for m in CONTEXT}}
    A.update({"T1": T1, "T1A": T1A, "T3": T3, "EV": EV, "T2s": T2s, "T2m": T2m, "J2m": J2m, "pooled": pooled, "setkind": setkind, "BS": BS, "S3": S3,
              "COV": COV, "S1": S1, "NIS": NIS, "JP": JP, "JI": JI, "JR": JR, "FBS": FBS, "floor95": floor95, "ver": ver, "dec": dec, "S": S,
              "Rm_t1": Rm})
    summ = {"decision": dec, "verdict": ver, "zupt_stats": zstats, "repro_t1_stepB": rep_t1, "repro_still": rep_still, "repro_default_smoother": dsr,
            "repro_v1b": v1r, "floor_p95_u3": floor95,
            "repro_tracks": {"kernel_vs_pilot_B2_max_in": float(rep_tr.kernel_vs_pilot_B2_max_in.max()),
                             "kernel_vs_pilot_loco_max_in": float(rep_tr.kernel_vs_pilot_loco_max_in.max()),
                             "kernel_vs_V1b_kernel_max_in": float(rep_tr.kernel_vs_V1b_kernel_max_in.max()),
                             "B2_vs_saved_core_max_in": float(rep_tr.B2_vs_saved_core_max_in.max()),
                             "B2_vs_saved_all_max_in": float(rep_tr.B2_vs_saved_all_max_in.max()),
                             "V1b_rebuilt_vs_saved_core_max_in": float(rep_tr.V1b_rebuilt_vs_saved_core_max_in.max()),
                             "V1b_rebuilt_vs_saved_all_max_in": float(rep_tr.V1b_rebuilt_vs_saved_all_max_in.max()),
                             "raw_vs_saved_max_in": float(rep_tr.raw_vs_saved_max_in.max()),
                             "zupt_equals_V1b_noRelease_all": bool(rep_tr.zupt_equals_V1b_noRelease_mask.all()),
                             "cache_match_all": bool(rep_tr.cache_match.all()), "anchors_match_all": bool(rep_tr.anchors_match.all()),
                             "state_nonzero_where_not_ok": int(rep_tr.state_nonzero_where_not_ok.sum()),
                             "stepB_block_equal_all": bool(rep_tr.stepB_block_equal.dropna().astype(bool).all()),
                             "stepB_u3_vs_here_raw_max": float(rep_tr["stepB_u3_vs_here_raw_max"].max()),
                             "stepB_v3_B2_vs_here_B2_max": float(rep_tr["stepB_v3_B2_vs_here_B2_max"].max()),
                             "stepB_v3_V1b_vs_here_V1b_max": float(rep_tr["stepB_v3_V1b_vs_here_V1b_max"].max()),
                             "stepB_v3_V2b_vs_here_V2b_max": float(rep_tr["stepB_v3_V2b_vs_here_V2b_max"].max()),
                             "seg_fixcount_mismatch": int(rep_tr.n_seg_fixcount_mismatch.sum()), "n_jobs": int(len(rep_tr))},
            "runtime_aggregate_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=DS._jd), encoding="utf-8")
    A["summary"] = summ
    log_to(fh, f"aggregation done ({time.time() - t0:.0f} s); V3 {'PASSES' if dec['V3_passes'] else 'FAILS ' + ', '.join(dec['failed_criteria'])}; "
               f"default for the implanted animals: {dec['default_implanted']}")
    return A


# ====================================================================================================== figures
def _eb(v, lo, hi):
    return [[max(np.nan_to_num(v - lo), 0.0)], [max(np.nan_to_num(hi - v), 0.0)]]


def make_figures(A: dict, out: Path, fdir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cfg = A["cfg"]
    cohort = cfg["_cohort"]
    thr = 100 * float(cfg["acceptance"]["T1_max_abs_rel"])
    figs = {}
    T1 = A["T1"]
    order = ["B2", "V1b", "V2b"] + VARS
    # ---- 1. T1
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8), sharey=False)
    for k, scale in enumerate(SCALES):
        pts = [("all", "all clean"), ("gt15", "> 15 in/s"), ("5to15", "5–15 in/s"), ("lt5", "< 5 in/s")]
        for i, m in enumerate(order):
            for j, (band, _) in enumerate(pts):
                r = T1[(T1.scale == scale) & (T1.set == "all") & (T1.band == band) & (T1.track == m)]
                if not len(r):
                    continue
                r = r.iloc[0]
                x = j + (i - (len(order) - 1) / 2) * 0.085
                ax[k].errorbar(x, 100 * r.d95, yerr=_eb(100 * r.d95, 100 * r.d95_lo, 100 * r.d95_hi), fmt="o", ms=4, capsize=2, color=COL[m],
                               label=SHORT[m] if j == 0 else None, mec="k" if m == "V3" else None)
        ax[k].axhspan(-thr, thr, color="g", alpha=0.08)
        ax[k].axhline(0, color="k", lw=0.5)
        ax[k].set_xticks(range(len(pts)))
        ax[k].set_xticklabels([p[1] for p in pts])
        ax[k].set_ylabel(f"d95 = Q95(track)/Q95(clean ref) − 1 (%), {scale}-s scale")
        ax[k].set_title(f"{scale}-s scale{' (T1: first two groups, ± 3 %)' if scale == 3 else ' (reported)'}")
        ax[k].grid(alpha=0.3)
    ax[0].legend(fontsize=7, ncol=2)
    fig.suptitle("T1: track speed vs the clean-WISER reference on step B's clean seconds (six nights; 95 % CIs, 10-min block bootstrap)")
    fig.tight_layout()
    f = f"{STEM}_t1_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["t1"] = f
    # ---- 2. T3
    T3 = A["T3"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    pts2 = [(s, k) for s in ("calm", "rain") for k in ("onset", "offset")]
    meths = ["V1b", "V2b"] + VARS
    for i, m in enumerate(meths):
        for j, (s, k) in enumerate(pts2):
            r = T3[(T3.method == m) & (T3.set == s) & (T3.kind == k) & (T3.periods == "all")]
            if not len(r):
                continue
            r = r.iloc[0]
            x = j + (i - (len(meths) - 1) / 2) * 0.09
            ax[0].errorbar(x, r.dlag_med, yerr=_eb(r.dlag_med, r.get("dlag_lo", np.nan), r.get("dlag_hi", np.nan)), fmt="o", ms=4, capsize=2,
                           color=COL[m], label=SHORT[m] if j == 0 else None, mec="k" if m == "V3" else None)
            ax[1].bar(x, 100 * r.get("share_later", np.nan), 0.08, color=COL[m], edgecolor="k", lw=0.3)
            ax[1].bar(x, -100 * r.get("share_earlier", np.nan), 0.08, color=COL[m], edgecolor="k", lw=0.3, alpha=0.5)
    ax[0].axhline(float(cfg["acceptance"]["T3_max_later_s"]), color="r", ls="--", lw=1)
    ax[0].axhline(0, color="k", lw=0.5)
    for a_ in ax:
        a_.set_xticks(range(len(pts2)))
        a_.set_xticklabels([f"{s}\n{k}" for s, k in pts2])
        a_.grid(alpha=0.3)
    ax[0].set_ylabel("median per-event Δ lag vs B2 (s)")
    ax[0].set_title("T3 (pass ≤ +0.5 s, red; earlier allowed)")
    ax[0].legend(fontsize=7, ncol=2)
    ax[1].axhline(0, color="k", lw=0.5)
    ax[1].set_ylabel("share of paired events later (up) / earlier (down) than B2 (%)")
    ax[1].set_title("shifted events")
    fig.suptitle("T3: S5 transition lags relative to B2 (all audit periods; 95 % CIs)")
    fig.tight_layout()
    f = f"{STEM}_t3_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["t3"] = f
    # ---- 3. still (circular) + coverage
    pooled, BS, COV = A["pooled"], A["BS"], A["COV"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [3, 1]})
    x = np.arange(len(TRACKS))
    for s, off in (("calm", -0.2), ("rain", 0.2)):
        v = np.array([float(pooled[(pooled.set == s) & (pooled.method == m)].path_in_per_min.iloc[0]) for m in TRACKS])
        lo_ = np.array([float(BS[(BS.set == s) & (BS.method == m) & (BS.metric == "path_rate")].lo.iloc[0]) for m in TRACKS])
        hi_ = np.array([float(BS[(BS.set == s) & (BS.method == m) & (BS.metric == "path_rate")].hi.iloc[0]) for m in TRACKS])
        ax[0].bar(x + off, v, 0.38, color=[COL[m] for m in TRACKS], alpha=1.0 if s == "calm" else 0.5, edgecolor="k", lw=0.5,
                  yerr=[np.clip(v - lo_, 0, None), np.clip(hi_ - v, 0, None)], capsize=2, label=s)
    ax[0].set_yscale("log")
    ax[0].set_xticks(x)
    ax[0].set_xticklabels([SHORT[m] for m in TRACKS], rotation=25)
    ax[0].set_ylabel("fake path in certified stillness (in/min, log)")
    ax[0].set_title("Still (CIRCULAR for the ZUPT forms): calm dark, rain light")
    for k, s in enumerate(("calm", "rain")):
        r = COV[(COV.set == s) & (COV.kind == "all")].iloc[0]
        ax[1].bar(np.arange(2) + (k - 0.5) * 0.38, [100 * r.cov_V1b, 100 * r.cov_V3], 0.38, color=[COL["V1b"], COL["V3"]],
                  alpha=1.0 if s == "calm" else 0.5, edgecolor="k", lw=0.5)
    ax[1].set_xticks(np.arange(2))
    ax[1].set_xticklabels(["V1b", "V3"])
    ax[1].set_ylim(80, 100)
    ax[1].set_ylabel("certified still time with the ZUPT (%)")
    ax[1].set_title("ZUPT coverage")
    fig.tight_layout()
    f = f"{STEM}_still_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["still"] = f
    # ---- 4. NIS by IMU state
    NIS = A["NIS"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    states = ["still", "active", "locomoting", "QC failed"]
    for k, s in enumerate(("calm", "rain")):
        for i, m in enumerate(NIS_M):
            g = NIS[(NIS.method == m) & (NIS.by == "set×imu") & (NIS.set == s)].set_index("imu").reindex(states)
            ax[k].bar(np.arange(4) + (i - 1.5) * 0.2, g["mean"], 0.2, color=COL[m], edgecolor="k", lw=0.4, label=SHORT[m])
        ax[k].axhline(2.0, color="k", ls=":", lw=1)
        ax[k].set_xticks(range(4))
        ax[k].set_xticklabels(states)
        ax[k].set_yscale("log")
        ax[k].set_title(f"{s}: mean NIS of the fixes (χ²₂ expectation 2)")
        ax[k].grid(alpha=0.3, axis="y")
    ax[0].set_ylabel("mean NIS (log)")
    ax[0].legend(fontsize=7)
    fig.tight_layout()
    f = f"{STEM}_nis_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["nis"] = f
    # ---- 5. upper-tail Q-Q of the 3-s speed on the clean seconds
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
    try:
        parts = []
        for f_ in sorted((out / "seconds").glob("*.npz")):
            with np.load(f_) as z:
                if "clean" not in z.files:
                    continue
                cl = z["clean"]
                parts.append(pd.DataFrame({"u3": z["u3"][cl], **{m: z[f"w3_{m}"][cl] for m in ("B2", "V1b", "V2b", "V3", "V3_loco", "V3_m30")}}))
        D = pd.concat(parts, ignore_index=True).dropna()
        qs = np.r_[np.arange(50, 99, 1.0), np.arange(99, 99.95, 0.1)]
        qu = np.percentile(D["u3"], qs)
        for m in ("B2", "V2b", "V3", "V3_loco", "V3_m30"):
            qm = np.percentile(D[m], qs)
            ax[0].plot(qu, qm, "-", color=COL[m], label=SHORT[m], lw=1.5 if m == "V3" else 1.0)
            ax[1].plot(qs, 100 * (qm / qu - 1), "-", color=COL[m], label=SHORT[m], lw=1.5 if m == "V3" else 1.0)
        ax[0].plot([0, qu.max()], [0, qu.max()], "k:", lw=0.8)
        ax[0].set_xlabel("clean-WISER reference u3 quantile (in/s)")
        ax[0].set_ylabel("track v3 quantile (in/s)")
        ax[0].set_title("Q–Q, 3-s speed, all clean seconds (50th–99.9th percentile)")
        ax[1].axhspan(-thr, thr, color="g", alpha=0.08)
        ax[1].axvline(95, color="k", ls=":", lw=0.8)
        ax[1].set_xlabel("percentile")
        ax[1].set_ylabel("Q(track)/Q(ref) − 1 (%)")
        ax[1].set_title("relative quantile difference (T1 (a) reads it at 95)")
        for a_ in ax:
            a_.grid(alpha=0.3)
            a_.legend(fontsize=7)
    except Exception as e:  # noqa: BLE001
        ax[0].text(0.1, 0.5, f"not available: {e}", transform=ax[0].transAxes)
    fig.tight_layout()
    f = f"{STEM}_qq_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["qq"] = f
    return figs


# ====================================================================================================== report
_f = DS._f
_p = DS._p


def _pf(b: bool) -> str:
    return "pass" if b else "**FAIL**"


DEFINITIONS = r"""
## Definitions

All positions are WISER **inches in the unverified offset frame**; only distances and speeds (frame-invariant) are used.
Times are field-PC local (EDT). $k$ indexes the fixes of one tag; $\mathbf z_k$ = raw fix (in, float64 from the fix
cache); $\hat{\mathbf p}^{(m)}_k$ = method $m$'s position at fix $k$; $t_k=t_k^{\text{WISER}}-\tau^*$ = fix time aligned on the
IMU clock ($\tau^*$ = 0.20 / 0.15 / 0.10 / 0.20 / 0.15 s for SF07 / 08 / 09 / 10 / 12); $s$ = an integer field-PC second
$[s, s+1)$ with IMU state $c(s)\in\{0\ \text{unusable},1\ \text{still},2\ \text{active},3\ \text{locomoting}\}$ (the audit's
`imu_seconds`; 0 wherever the IMU QC fails, outside the window and in the ± 10-min margins).

### B2 (baseline and base)
Per axis a constant-velocity state $\mathbf x_k=(p_k,v_k)$, $\mathbf x_k=F_k\mathbf x_{k-1}+\boldsymbol\eta_k$,
$F_k=\begin{pmatrix}1&\Delta t_k\\0&1\end{pmatrix}$, $\mathrm{Cov}(\boldsymbol\eta_k)=q_k\begin{pmatrix}\Delta t^3/3&\Delta t^2/2\\\Delta t^2/2&\Delta t\end{pmatrix}$
with $q_k=q$ = 3 in²/s³; fix $z_k=p_k+\varepsilon_k$, $\varepsilon_k\sim\mathcal N(0,\sigma^2_{\mathrm{ax}}(A_k)/w_k)$, $A_k$ = `anchors_used`,
$\sigma_{\mathrm{ax}}$ the smoothing pilot's robust per-anchor SD. Pass 0: forward Kalman filter with a soft χ² gate (fix
variance inflated by $d^2/13.82$ when the 2-D innovation $d^2$ exceeds the χ²₂ 0.999 point) + RTS smoother; passes 1–2:
Huber weights $w_k=\min(1,\,2.5/m_k)$, $m_k=\big(\sum_a (z_{k,a}-\hat p_{k,a})^2/\sigma^2_a(A_k)\big)^{1/2}$. **Text:** the
universal WISER baseline of 2026c (default-smoother step).

### V3 (the candidate)
B2 with two changes in the same filter:
$$ q_k=q\cdot\mu_k,\qquad \mu_k=\begin{cases}10 & c\big(\lfloor (t_{k-1}+t_k)/2\rfloor\big)=3\\ 1 & \text{otherwise}\end{cases} $$
(the step $(t_{k-1},t_k]$ whose midpoint second is IMU-QC-ok and locomoting gets 10 × the process noise; still, active,
QC-failed and margin steps keep B2's $q$; 10 = the pilot's tuned $m_{\text{loco}}$, unchanged), and, at every ZUPT fix $k$,
the pseudo-measurements $0=v_{k,a}+\epsilon_{k,a}$ ($a=x,y$), $\epsilon\sim\mathcal N(0,\sigma_Z^2/w^Z_k)$, $\sigma_Z$ = 0.25 in/s,
applied after the fix update in the same forward pass, with the Huber weight of V1b inside the IRLS passes (pass 0: $w^Z_k=1$)
$$ w^Z_k=\min\!\Big(1,\ \frac{2.5}{m^Z_k}\Big),\qquad m^Z_k=\frac{\lVert\hat{\mathbf v}_k\rVert}{\sigma_Z}. $$
No release. **Text:** where the head IMU says still, V3 is told firmly that the velocity is zero (a velocity the fixes
insist on beyond 2.5 σ_Z = 0.625 in/s is listened to with a falling weight); where it says locomoting, the motion model is
allowed 10 × the acceleration variance so the track can follow runs; everywhere else, and wherever the IMU is unusable,
V3 is B2 (no splice).

### ZUPT intervals and membership
A run $[s_a,s_b)$ of $n=s_b-s_a$ consecutive IMU-QC-ok still seconds gives, if $n\ge3$, the interval $I=[s_a+1,\,s_b-1)$
($n-2$ s); runs with $n<3$ give none. Fix $k$ is a ZUPT fix when $t_k\in I$ for some $I$. (Identical to V1b's
noRelease intervals.)

### Sensitivities and context tracks
V3-σ0.5 / V3-σ1.0: $\sigma_Z$ = 0.5 / 1.0 in/s; V3-×3 / V3-×30: $\mu_k$ = 3 / 30 on locomoting steps; V3-loco: the
multiplier without any ZUPT. Context (scored, not eligible): B2 (rebuilt here with $\mu\equiv1$, no ZUPT), V1b (the V1b
run's track: B2 + Huber ZUPT σ 1 in/s with a drift release), V2b (default-smoother run: $q_k=q\cdot(1,0.01,0.3,10)[c]$ on B2,
spliced to B2 at IMU-failed fixes).

### Clean second, window median, clean-WISER speed (step B, unchanged)
$\mathbf m_h(g)=\operatorname{median}_{\text{coord}}\{\mathbf z_k: t_k\in[g-h,g+h)\}$ (≥ 3 fixes); with $c=s+0.5$,
$$ u_3(s)=\frac{\lVert\mathbf m_{0.5}(c+1.5)-\mathbf m_{0.5}(c-1.5)\rVert}{3\ \text{s}},\qquad u_1(s)=\frac{\lVert\mathbf m_{0.375}(c+0.5)-\mathbf m_{0.375}(c-0.5)\rVert}{1\ \text{s}} $$
(in/s). Clean second: every fix in $[c-2,c+2]$ has ≥ 8 anchors, is valid and unmasked, no raw jump (> 30 in in ≤ 0.35 s)
touches the span, ≥ 12 fixes, both 3-s medians outside the house ROIs grown by 14 in, and the second is IMU-QC-ok.
**Text:** a nearly model-free head speed on open-field, well-anchored seconds; step B's saved clean seconds and $u_3,u_1$
are used as they are (six nights 09-03, 09-05 … 09-09).

### Track speed ($v_3$, $v_1$)
The same medians on the track: $v^{(m)}_3(s)=\lVert\mathbf m^{(m)}_{0.5}(c+1.5)-\mathbf m^{(m)}_{0.5}(c-1.5)\rVert/3$ with
$\mathbf m^{(m)}_h$ the window median of $\hat{\mathbf p}^{(m)}_k$ (and $v_1$ likewise). **Text:** the track's speed seen
through exactly the estimator the reference uses on the raw fixes (raw ≡ reference).

### T1 — fast motion followed (truth-referenced)
On the paired clean seconds $\mathcal C$ (every track's $v$ and the reference defined),
$$ d_{95}=\frac{Q_{95}\{v_3^{(m)}(s)\}_{s\in\mathcal C}}{Q_{95}\{u_3(s)\}_{s\in\mathcal C}}-1 $$
for (a) all of $\mathcal C$ and (b) $\mathcal C_{>15}=\{s\in\mathcal C: u_3(s)>15\ \text{in/s}\}$; **pass if $|d_{95}|\le$ 3 %
for both** (point estimates; six nights pooled). Also reported: $d_{50}$ on the 5–15 in/s band, the same at the 1-s scale
($v_1$, $u_1$, bands on $u_1$), per set and per animal, and $\mathrm{MAE}=\operatorname{median}_s|v-u|$. **Text:** $d<0$ = the
track's fast-speed distribution is slower than the clean reference (under-follows runs), $d>0$ = faster (adds noise or
overshoot). The > 15 band is chosen on the noisy reference (selection regression: a track without the reference's noise
looks slightly slow there).

### T2 — no jumps
Jump: consecutive fixes with $\lVert\hat{\mathbf p}_{k+1}-\hat{\mathbf p}_k\rVert>30$ in and $t_{k+1}-t_k\le0.35$ s. Pass if 0
inside every primary certified still segment (all lengths ≥ 10 s, 1 s trimmed; calm and rain; the ≥ 30-s subset also
reported) and 0 over the analysis mask of every audit period (pair midpoint second in the mask: window, no handling ± 5
min, no all-tag silence ± 120 s, tag valid).

### T3 — transitions not later than B2
Events (default-smoother S5): an IMU still run $[a,b)$ ≥ 10 s followed (onset) / preceded (offset) within 60 s by a
locomoting second $s_L$ (no still run or unusable second in between, ≥ 10 s from the window edges). With $v_m(g)$ the 1-s
centred speed on a 0.25-s grid,
$$ \lambda^{\text{on}}_m=\min\{g\in[b-5,\,s_L+20]:v_m(g)\ge3\}-b,\qquad \lambda^{\text{off}}_m=\max\{g\in[s_L-20,\,a+10]:v_m(g)\ge3\}+0.25-a $$
(s); $\Delta\lambda=\lambda_{V3}-\lambda_{B2}$ per event (events where both are defined). **Pass if
$\operatorname{median}\Delta\lambda\le+0.5$ s** for onsets and offsets, calm and rain (all periods; one-sided: earlier is
allowed). Shifted share = share of paired events with $\Delta\lambda\ne0$ (later: $>0$, earlier: $<0$). **Text:** onset
$\Delta\lambda>0$ = V3 starts moving later than B2; offset $\Delta\lambda>0$ = V3 keeps moving longer than B2.

### Still metrics (reported; circular for the ZUPT forms)
On the failure audit's primary certified ≥ 30-s segments (gate-v2 strict on 09-08, S50 elsewhere; 1 s trimmed), truth
$\mathbf c_\sigma=\operatorname{med}_{k\in\sigma}\mathbf z_k$: per-fix $r_k=\lVert\hat{\mathbf p}_k-\mathbf c_\sigma\rVert$, RMS
$=(\frac1N\sum r_k^2)^{1/2}$, p99 of $r_k$; drift $d^{(L)}_\sigma=\max_c\lVert\operatorname{med}_{t_k\in[c-L/2,c+L/2)}\hat{\mathbf p}_k-\mathbf c_\sigma\rVert$
($L$ = 10 s / 60 s); ≥ 12-in excursion = ≥ 10 consecutive 1-s centres with the 10-s median ≥ 12 in from $\mathbf c_\sigma$; fake path
$\Pi=\sum_s\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/(N_s/60)$ (in/min, pooled; $\tilde{\mathbf p}$ = linear interpolation
inside gaps ≤ 1 s). **Circular:** the IMU stillness that drives the ZUPT also certifies these segments.

### ZUPT coverage
$\kappa=\sum_\sigma\big|\bigcup_I I\cap[t^0_\sigma+1,t^1_\sigma-1)\big|\,/\,\sum_\sigma D_\sigma$ over the certified ≥ 30-s segments
($D_\sigma$ = trimmed duration). **Text:** the share of certified still time that receives V3's constraint.

### In-place jitter check (reported)
$\delta_k=\min_{j\in\mathcal I}|t_k-t_j|$ with $\mathcal I$ = V3's ZUPT fixes and both end fixes of every locomoting step.
(i) IMU-active fixes ($c=2$, analysis mask) with $\delta_k\ge3$ s: $Q_{99}\lVert\hat{\mathbf p}^{(m)}_k-\hat{\mathbf p}^{(B2)}_k\rVert$;
IMU-active seconds whose centre is ≥ 3.5 s from $\mathcal I$: the 1-s speed $v^{S2}_m(s)=\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert$
p50 / p95 relative to B2's. (ii) clean seconds with $c(s)=3$ and $u_3(s)<F_{95}$ = 1.64 in/s (step B's noise-floor p95 on
certified stillness) — the IMU says locomoting but the head does not translate (in-place activity): $v^{S2}_m$ and $v_1$ p50 /
p95 relative to B2's. **Text:** (i) should be ≈ 0 (V3 = B2 away from its changes); (ii) is how much jitter the × 10 lets
through when the locomotion class is wrong.

### NIS
For each visible fix, in the final forward pass, with the predicted state and the nominal (unweighted) noise,
$\text{NIS}_k=\sum_a(z_{k,a}-\hat p^{-}_{k,a})^2/(P^{-}_{k,aa}+\sigma^2_a(A_k))$; consistent model: $\chi^2_2$ (mean 2, median
1.39, 5 % above 5.99). $P^{-}$ includes V3's $q_k$. Strata: IMU state of the aligned second × anchors_used {≤ 6, 7, 8, 9} ×
zone (B2 position inside a house ROI grown by 14 in). V1b's NIS is from V1b rebuilt by this kernel (its saved ZUPT mask).
**Text:** mean > 2 = the predicted spread is too small (noise table or motion model too optimistic); < 2 = too large.

### S1 — held-out fixes (reported)
The default-smoother masks and seeds ((a) runs of 4–8 hidden fixes, (s) every 5th fix); B2, V3 and V3-loco rerun with the
hidden fixes invisible; $e_k=\lVert\mathbf z_k-\hat{\mathbf p}_{-}(t_k)\rVert$ on hidden window fixes with ≥ 7 anchors, aligned second
QC-ok; $D=1-\operatorname{med}e^{(m)}/\operatorname{med}e^{(B2)}$ on the moving (QC-ok, not still) subset; positive = closer to the
held-out raw fixes than B2.

### S3 — rain excursions (reported)
Count of ≥ 12-in excursions in the rain set's primary ≥ 30-s segments (failure audit: raw 6, B2 7; V1b 7).

### Fallback share
Share of analysis-mask window fixes whose aligned second is not IMU-QC-ok (there V3 = B2 by construction).

### Block bootstrap
$\theta^{*(b)}=\theta(\{\text{10-min animal-period blocks drawn with replacement within the set}\})$, $b$ = 1..1000; CI = 2.5–97.5 %
of $\theta^*$; paired comparisons use the same draw for both series; quantiles inside replicates come from per-block
histograms (log-spaced edges, ≈ 0.28 % relative width, for speeds; 0.001 in for distances; 0.005 in for held-out errors);
point estimates are exact. Seed 20261008 (+ offset per table).
"""


def render_report(A: dict, out: Path, figs: dict, meta: dict) -> str:
    cfg = A["cfg"]
    cohort = cfg["_cohort"]
    acc = cfg["acceptance"]
    ver, dec = A["ver"], A["dec"]
    T1, T1A, T3, T2s, T2m, pooled, setkind, BS, S3, COV, S1, NIS, JP, JI, JR, FBS = (A[k] for k in (
        "T1", "T1A", "T3", "T2s", "T2m", "pooled", "setkind", "BS", "S3", "COV", "S1", "NIS", "JP", "JI", "JR", "FBS"))
    rep_tr, zst = A["rep_tr"], A["zstats"]
    v = ver["V3"]

    def t1r(m, band="all", scale=3, s="all"):
        r = T1[(T1.scale == scale) & (T1.set == s) & (T1.band == band) & (T1.track == m)]
        return r.iloc[0] if len(r) else None

    def t3r(m, s, k, per="all"):
        r = T3[(T3.method == m) & (T3.set == s) & (T3.kind == k) & (T3.periods == per)]
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

    def nis_r(m, by, **kw):
        g = NIS[(NIS.method == m) & (NIS.by == by)]
        for k_, v_ in kw.items():
            g = g[g[k_] == v_]
        return g.iloc[0] if len(g) else None

    def nism(m, s, st_):
        r = nis_r(m, "set×imu", set=s, imu=st_)
        return float(r["mean"]) if r is not None else np.nan

    def ci_(r, col, pct=True, nd=1):
        lo_, hi_ = r.get(f"{col}_lo", np.nan), r.get(f"{col}_hi", np.nan)
        return f"[{_p(lo_, nd)}, {_p(hi_, nd)}]" if pct else f"[{_f(lo_, nd)}, {_f(hi_, nd)}]"

    L = []
    L.append(f"# V3 — B2 with a firm head-IMU ZUPT and locomotion-boosted process noise (cohort {cohort})\n")
    L.append(f"Approved by the user 2026-10-03 (\"做\"). Plan [`{PLAN}`](../../../../{PLAN}) (written and committed, 26a1cb8, before any V3 number; "
             f"amendments at its end); driver `{DRIVER}` (`--selftest` ALL PASS); config `wiser/configs/wiser_v3_{cohort}.json` (verdict in its `decision` "
             f"block); bulk `{out}`; inputs = the failure audit run, the WISER fix caches, the default-smoother, V1b and step-B runs (reused, not "
             f"recomputed); git `{meta['git_commit']}`. Measurement report: no behavioural claim; WISER inch frame unverified (only distances and "
             f"speeds used). Nothing was tuned in this step.\n")
    # ---------------- executive summary
    L.append("## Executive summary\n")
    ex = []
    if dec["V3_passes"]:
        ex.append("**Verdict: V3 passes T1–T3 → V3 replaces V1b as the default WISER track for the implanted animals** (SF07–SF12 wherever the "
                  "IMU QC passes; elsewhere it is B2 by construction); **B2 stays the universal baseline** (tags without an IMU, e.g. the five "
                  "females released 09-11, and every IMU-failed stretch).")
    else:
        ex.append(f"**Verdict: V3 fails {', '.join(dec['failed_criteria'])} → V1b stays the default WISER track for the implanted animals** "
                  f"(B2 stays the universal baseline). Failed criterion: {', '.join(dec['failed_criteria'])}.")
    ra, rf = t1r("V3"), t1r("V3", "gt15")
    ex.append(f"**T1 (3-s p95 speed vs the clean-WISER reference, bound ± 3 %):** (a) all clean seconds {_p(ra.d95, 1)} {ci_(ra, 'd95')}, "
              f"(b) > 15 in/s band {_p(rf.d95, 1)} {ci_(rf, 'd95')} (n {int(ra.n_sec):,} / {int(rf.n_sec):,} seconds) → {_pf(v['T1'])}. "
              f"Context: B2 {_p(t1r('B2').d95, 1)} / {_p(t1r('B2', 'gt15').d95, 1)}, V1b {_p(t1r('V1b').d95, 1)} / {_p(t1r('V1b', 'gt15').d95, 1)}, "
              f"V2b {_p(t1r('V2b').d95, 1)} / {_p(t1r('V2b', 'gt15').d95, 1)}.")
    ex.append(f"**T2 (jumps):** {v['T2_still_jumps']} in the primary certified still segments ({v['T2_still_jumps_ge30']} in the ≥ 30-s ones), "
              f"{v['T2_mask_jumps']} over the analysis masks → {_pf(v['T2'])}.")
    cells = []
    for s in ("calm", "rain"):
        for k in ("onset", "offset"):
            r = t3r("V3", s, k)
            cells.append(f"{s} {k} {_f(r.dlag_med, 2)} s [{_f(r.get('dlag_lo'), 2)}, {_f(r.get('dlag_hi'), 2)}] "
                         f"({_p(r.get('share_later'), 0, False)} later / {_p(r.get('share_earlier'), 0, False)} earlier of {int(r.n_paired)})")
    ex.append("**T3 (median per-event lag change vs B2, bound ≤ +0.5 s):** " + "; ".join(cells) + f" → {_pf(v['T3'])}.")
    ex.append(f"**Still (circular — the IMU stillness drives the ZUPT and certifies the segments):** fake path B2 {_f(pv('calm', 'B2', 'path_in_per_min'))} | "
              f"{_f(pv('rain', 'B2', 'path_in_per_min'))}, V1b {_f(pv('calm', 'V1b', 'path_in_per_min'))} | {_f(pv('rain', 'V1b', 'path_in_per_min'))}, "
              f"**V3 {_f(pv('calm', 'V3', 'path_in_per_min'))} | {_f(pv('rain', 'V3', 'path_in_per_min'))} in/min** (calm | rain); per-fix RMS B2 "
              f"{_f(pv('calm', 'B2', 'rms_in'), 2)} | {_f(pv('rain', 'B2', 'rms_in'), 2)} → V3 {_f(pv('calm', 'V3', 'rms_in'), 2)} | {_f(pv('rain', 'V3', 'rms_in'), 2)} in; "
              f"ZUPT coverage of certified still time {_p(cov('calm').cov_V3, 1, False)} | {_p(cov('rain').cov_V3, 1, False)} (V1b after its release "
              f"{_p(cov('calm').cov_V1b, 1, False)} | {_p(cov('rain').cov_V1b, 1, False)}); the ZUPT Huber weight is < 1 at "
              f"{_p(zst['calm']['wz_lt1_share'], 4, False)} | {_p(zst['rain']['wz_lt1_share'], 4, False)} of the ZUPT fixes (the firm ZUPT keeps the smoothed "
              f"velocity below 2.5 σ_Z = 0.625 in/s, so the Huber guard almost never acts).")
    jc = JP[(JP.method == "V3")].set_index("set")
    jic = JI[JI.track == "V3"].set_index("set") if len(JI) else None
    jrc = JR[(JR.track == "V3") & (JR.speed == "S2 1-s speed")].set_index("set") if len(JR) else None
    if jic is not None and jrc is not None and "calm" in jc.index:
        ex.append(f"**In-place jitter check:** (i) on IMU-active fixes ≥ 3 s from any locomoting step or ZUPT fix (calm {_p(jc.loc['calm', 'share_far'], 0, False)} "
                  f"of the active fixes) |V3 − B2| p99 = {_f(jc.loc['calm', 'p99'], 3)} | {_f(jc.loc['rain', 'p99'], 3)} in (calm | rain); 1-s speed p50 / p95 vs B2 "
                  f"{_p(jic.loc['calm', 'd50'], 1)} / {_p(jic.loc['calm', 'd95'], 1)} (calm). (ii) on clean IMU-locomoting seconds below the floor "
                  f"(u3 < {_f(A['floor95'], 2)} in/s; n {int(jrc.loc['all', 'n_sec']):,}) V3's 1-s speed p50 / p95 is {_p(jrc.loc['all', 'd50'], 1)} / "
                  f"{_p(jrc.loc['all', 'd95'], 1)} relative to B2 (V3-loco {_p(JR[(JR.track == 'V3_loco') & (JR.speed == 'S2 1-s speed') & (JR.set == 'all')].d50.iloc[0], 1)} / "
                  f"{_p(JR[(JR.track == 'V3_loco') & (JR.speed == 'S2 1-s speed') & (JR.set == 'all')].d95.iloc[0], 1)}).")
    ex.append(f"**NIS by IMU state (calm, mean; χ²₂ expectation 2):** B2 still {_f(nism('B2', 'calm', 'still'), 2)} / active {_f(nism('B2', 'calm', 'active'), 2)} / "
              f"locomoting {_f(nism('B2', 'calm', 'locomoting'), 2)}; V1b {_f(nism('V1b', 'calm', 'still'), 2)} / {_f(nism('V1b', 'calm', 'active'), 2)} / "
              f"{_f(nism('V1b', 'calm', 'locomoting'), 2)}; **V3 {_f(nism('V3', 'calm', 'still'), 2)} / {_f(nism('V3', 'calm', 'active'), 2)} / "
              f"{_f(nism('V3', 'calm', 'locomoting'), 2)}** (rain V3 {_f(nism('V3', 'rain', 'still'), 2)} / {_f(nism('V3', 'rain', 'active'), 2)} / "
              f"{_f(nism('V3', 'rain', 'locomoting'), 2)}).")
    s1c = S1[(S1.set == "calm") & (S1.scheme == "a") & (S1.subset == "moving")].iloc[0]
    s1r = S1[(S1.set == "rain") & (S1.scheme == "a") & (S1.subset == "moving")].iloc[0]
    s3r = S3[S3.set == "rain"].set_index("method")
    ex.append(f"**S1 (held-out moving fixes, scheme (a)):** D(V3) = {_p(s1c.D_V3, 1)} [{_p(s1c.D_V3_lo, 1)}, {_p(s1c.D_V3_hi, 1)}] calm, "
              f"{_p(s1r.D_V3, 1)} [{_p(s1r.D_V3_lo, 1)}, {_p(s1r.D_V3_hi, 1)}] rain (positive = closer than B2). **S3 (rain ≥ 12-in excursions):** raw "
              f"{int(s3r.loc['raw', 'crazy_n'])}, B2 {int(s3r.loc['B2', 'crazy_n'])}, V1b {int(s3r.loc['V1b', 'crazy_n'])}, V3 {int(s3r.loc['V3', 'crazy_n'])}.")

    def sens_txt(m):
        vv_ = ver[m]
        base_ = f"{SHORT[m]} {'passes' if vv_['pass_all'] else 'fails ' + ', '.join(vv_['failed'])}"
        return base_ + f" (T1 {_p(vv_['T1_d95_all'], 1)} / {_p(vv_['T1_d95_gt15'], 1)})"
    ex.append(f"**Sensitivities (never the decision):** " + "; ".join(sens_txt(m) for m in SENS)
              + (f" → proposal to the user only: {', '.join(SHORT[m] for m in dec['variants_that_would_pass'])}." if dec["variants_that_would_pass"] else ".")
              + f" Context tracks on T1–T3: " + "; ".join(f"{m} {dec['context_outcomes'][m]}" for m in CONTEXT) + ".")
    for i, e in enumerate(ex, 1):
        L.append(f"{i}. {e}")
    L.append("")
    # ---------------- T1-T3 table
    L.append("## Pre-registered acceptance (T1–T3)\n")
    L.append("Point estimates decide; 95 % CIs from the 10-min block bootstrap are reported. T1 on step B's clean seconds of the six nights "
             "(09-03, 09-05 … 09-09; 21:00–04:20); T2 and T3 over every audit period (calm-dry days 09-05/07/08 08:00–18:00 and nights 09-05…09-08; "
             "rain nights 09-03, 09-09 and day 09-10), SF07, SF08, SF09, SF10, SF12.\n")
    cols = ["V3"] + SENS + CONTEXT
    L.append("| criterion | bound | " + " | ".join(SHORT[m] for m in cols) + " |")
    L.append("|---|---|" + "---|" * len(cols))
    for band, lab in (("all", "T1a 3-s p95, all clean"), ("gt15", "T1b 3-s p95, > 15 in/s")):
        cs = []
        for m in cols:
            r = t1r(m, band)
            cs.append(f"{_p(r.d95, 1)} [{_p(r.d95_lo, 1)}, {_p(r.d95_hi, 1)}] {'✓' if abs(r.d95) <= float(acc['T1_max_abs_rel']) else '✗'}")
        L.append(f"| {lab} | ± 3 % | " + " | ".join(cs) + " |")
    L.append("| T2 jumps: still segments / masks | 0 / 0 | " + " | ".join(
        f"{ver[m]['T2_still_jumps']} / {ver[m]['T2_mask_jumps']} {'✓' if ver[m]['T2'] else '✗'}" for m in cols) + " |")
    for s in ("calm", "rain"):
        for k in ("onset", "offset"):
            cs = []
            for m in cols:
                r = t3r(m, s, k)
                cs.append(f"{_f(r.dlag_med, 2)} [{_f(r.get('dlag_lo'), 2)}, {_f(r.get('dlag_hi'), 2)}] {'✓' if r['pass'] else '✗'}")
            L.append(f"| T3 {s} {k}: median Δ lag (s) | ≤ +0.5 | " + " | ".join(cs) + " |")
    L.append("| **outcome** | T1 ∧ T2 ∧ T3 | " + " | ".join(
        (f"**{'PASS' if ver[m]['pass_all'] else 'FAIL (' + ', '.join(ver[m]['failed']) + ')'}**"
         + (" — decides" if m == "V3" else (" — sensitivity" if m in SENS else " — context"))) for m in cols) + " |")
    L.append("")
    L.append(f"**Decision (pre-registered).** " + ("V3 passes T1–T3: V3 replaces V1b as the default WISER track for the implanted animals (IMU-QC-ok "
                                                   "stretches; B2 elsewhere by construction); B2 stays the universal baseline."
                                                   if dec["V3_passes"] else f"V3 fails {', '.join(dec['failed_criteria'])}: V1b stays the default WISER "
                                                   f"track for the implanted animals; B2 stays the universal baseline; no variant is promoted in this step.")
             + (f" Sensitivities that would pass ({', '.join(SHORT[m] for m in dec['variants_that_would_pass'])}) are a proposal to the user, not a default."
                if dec["variants_that_would_pass"] else "") + "\n")
    L.append(f"![T1](../figures/{figs['t1']})\n")
    # T1 detail
    L.append("### T1 detail — clean-WISER reference (all six nights; d = Q(track)/Q(ref) − 1)\n")
    L.append("| scale | band | n | ref p50 / p95 (in/s) | " + " | ".join(f"{SHORT[m]} d50; d95" for m in ["V3", "V3_loco", "B2", "V1b", "V2b"]) + " |")
    L.append("|---|---|---|---|" + "---|" * 5)
    for scale in SCALES:
        for band in BANDS:
            r0 = t1r("V3", band, scale)
            if r0 is None:
                continue
            cs = []
            for m in ["V3", "V3_loco", "B2", "V1b", "V2b"]:
                r = t1r(m, band, scale)
                cs.append(f"{_p(r.d50, 1)}; {_p(r.d95, 1)}")
            L.append(f"| {scale} s | {BAND_LABEL[band]} | {int(r0.n_sec):,} | {_f(r0.p50_ref, 2)} / {_f(r0.p95_ref, 2)} | " + " | ".join(cs) + " |")
    L.append("")
    L.append("Calm vs rain nights (3-s scale, V3 d95 all / > 15 in/s; B2 in parentheses):\n")
    L.append("| set | n | V3 d95 all | V3 d95 > 15 | V3 d50 5–15 | MAE V3 (B2) in/s |")
    L.append("|---|---|---|---|---|---|")
    for s in SETS3:
        r, rf_, rm_ = t1r("V3", "all", 3, s), t1r("V3", "gt15", 3, s), t1r("V3", "5to15", 3, s)
        b_, bf_, bm_ = t1r("B2", "all", 3, s), t1r("B2", "gt15", 3, s), t1r("B2", "5to15", 3, s)
        if r is None:
            continue
        L.append(f"| {s} | {int(r.n_sec):,} | {_p(r.d95, 1)} ({_p(b_.d95, 1)}) | {_p(rf_.d95, 1) if rf_ is not None else '–'} ({_p(bf_.d95, 1) if bf_ is not None else '–'}) | "
                 f"{_p(rm_.d50, 1) if rm_ is not None else '–'} ({_p(bm_.d50, 1) if bm_ is not None else '–'}) | {_f(r.mae, 2)} ({_f(b_.mae, 2)}) |")
    L.append("")
    r5b, r5v = t1r("B2", "lt5"), t1r("V3", "lt5")
    r1v, r1b, r1v15, r1b15 = t1r("V3", "all", 1), t1r("B2", "all", 1), t1r("V3", "gt15", 1), t1r("B2", "gt15", 1)
    def _rng(m, band):
        g = T1A[(T1A.track == m) & (T1A.scale == 3) & (T1A.band == band)]
        return f"{_p(g.d95.min(), 1)} to {_p(g.d95.max(), 1)}"
    g15 = T1A[(T1A.track == "V3") & (T1A.scale == 3) & (T1A.band == "gt15")].set_index("animal")
    worst = g15.d95.idxmin() if len(g15) else None
    L.append(f"**Reading.** The × 10 lifts the upper tail: V3's 3-s p95 over all clean seconds is {_rng('V3', 'all')} per animal (B2 {_rng('B2', 'all')}) "
             f"and above 15 in/s {_rng('V3', 'gt15')} (B2 {_rng('B2', 'gt15')}; the worst V3 animal is {worst} with n = {int(g15.loc[worst, 'n_sec']) if worst else 0} "
             f"fast seconds); calm and rain nights agree. V3-loco gives the same T1 numbers as V3 (the ZUPT acts only in IMU-still seconds), and "
             f"× 3 / × 30 bracket it ({_p(t1r('V3_m3', 'gt15').d95, 1)} / {_p(t1r('V3_m30', 'gt15').d95, 1)} above 15 in/s). Below the 90th percentile every "
             f"smoothed track is slower than the reference (Q–Q figure): there the reference itself carries the fix scatter (floor p95 "
             f"{_f(A['floor95'], 2)} in/s), so a smoother that removes noise must read lower — the < 5 in/s band p95 is {_p(r5v.d95, 1)} for V3 "
             f"vs {_p(r5b.d95, 1)} for B2 (the ZUPT also zeroes clean still seconds). At the 1-s scale (reported, noisier reference) V3 is "
             f"{_p(r1v.d95, 1)} / {_p(r1v15.d95, 1)} (all / > 15 in/s) vs B2 {_p(r1b.d95, 1)} / {_p(r1b15.d95, 1)}.\n")
    L.append("Per animal (3-s scale, all six nights; V3 | B2):\n")
    L.append("| animal | n clean | d95 all | d95 > 15 (n) | d50 5–15 |")
    L.append("|---|---|---|---|---|")
    for a in sorted(T1A.animal.unique()):
        def ar(m, band):
            r = T1A[(T1A.animal == a) & (T1A.scale == 3) & (T1A.band == band) & (T1A.track == m)]
            return r.iloc[0] if len(r) else None
        r1, r2_, r3_ = ar("V3", "all"), ar("V3", "gt15"), ar("V3", "5to15")
        b1, b2_, b3_ = ar("B2", "all"), ar("B2", "gt15"), ar("B2", "5to15")
        L.append(f"| {a} | {int(r1.n_sec):,} | {_p(r1.d95, 1)} \\| {_p(b1.d95, 1)} | "
                 + (f"{_p(r2_.d95, 1)} \\| {_p(b2_.d95, 1)} ({int(r2_.n_sec)})" if r2_ is not None else "–") + " | "
                 + (f"{_p(r3_.d50, 1)} \\| {_p(b3_.d50, 1)}" if r3_ is not None else "–") + " |")
    L.append("")
    L.append(f"![QQ](../figures/{figs['qq']})\n")
    # T3 detail
    L.append("### T3 detail (all periods)\n")
    L.append("| set | kind | events | B2 median lag (n) | V3 median lag (n) | paired | V3 Δ median [CI] | later / earlier (> +0.5 s) | mean Δ | V3-loco Δ | V1b Δ |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for k in ("onset", "offset"):
            r0, r1 = t3r("B2", s, k), t3r("V3", s, k)
            L.append(f"| {s} | {k} | {int(r0.n_events)} | {_f(r0.lag_med, 2)} ({int(r0.n_defined)}) | {_f(r1.lag_med, 2)} ({int(r1.n_defined)}) | {int(r1.n_paired)} | "
                     f"{_f(r1.dlag_med, 2)} [{_f(r1.get('dlag_lo'), 2)}, {_f(r1.get('dlag_hi'), 2)}] | {int(r1.n_later)} / {int(r1.n_earlier)} ({int(r1.n_later_gt05)}) | "
                     f"{_f(r1.get('dlag_mean'), 2)} | {_f(t3r('V3_loco', s, k).dlag_med, 2)} | {_f(t3r('V1b', s, k).dlag_med, 2)} |")
    L.append("")
    L.append("Night | day split of V3's median Δ (s): " + "; ".join(
        f"{s} {k} {_f(t3r('V3', s, k, 'night').dlag_med if t3r('V3', s, k, 'night') is not None else np.nan, 2)} | "
        f"{_f(t3r('V3', s, k, 'day').dlag_med if t3r('V3', s, k, 'day') is not None else np.nan, 2)}" for s in ("calm", "rain") for k in ("onset", "offset")) + ".\n")
    o_, f_ = t3r("V3", "calm", "onset"), t3r("V3", "calm", "offset")
    L.append(f"**Reading.** The pre-registered median is 0 everywhere because most events are unchanged at the 0.25-s grid; the shifted "
             f"minority goes both ways (calm onsets {int(o_.n_later)} later / {int(o_.n_earlier)} earlier, mean Δ {_f(o_.get('dlag_mean'), 2)} s; calm "
             f"offsets {int(f_.n_later)} later / {int(f_.n_earlier)} earlier, mean Δ {_f(f_.get('dlag_mean'), 2)} s; {int(o_.n_later_gt05)} and "
             f"{int(f_.n_later_gt05)} events more than 0.5 s later). V3-loco's median Δ is also 0, and V3 has more events with a defined lag than B2 "
             f"(calm onsets {int(o_.n_defined)} vs {int(t3r('B2', 'calm', 'onset').n_defined)}) because the × 10 lets the track cross 3 in/s in short "
             f"bouts that B2 smooths below it.\n")
    L.append(f"![T3](../figures/{figs['t3']})\n")
    # ---------------- reported sections
    L.append("## 1. Inputs and reproduction\n")
    rt = A["summary"]["repro_tracks"]
    rs = A["rep_still"]
    dsr = A["repro_ds"]
    r1 = A["rep_t1"]
    L.append("| check | result |")
    L.append("|---|---|")
    L.append(f"| V3 kernel with multiplier 1 and no ZUPT vs the pilot's B2 kernel (float64, every fix) | max {rt['kernel_vs_pilot_B2_max_in']:.2e} in |")
    L.append(f"| … vs the audit's saved B2 (float32) | max {rt['B2_vs_saved_core_max_in']:.2e} in ≥ 60 s from the window edges, {rt['B2_vs_saved_all_max_in']:.2e} in over every fix |")
    L.append(f"| V3 kernel with × 10 and no ZUPT (V3-loco) vs the pilot's kernel with multipliers (1, 1, 1, 10) | max {rt['kernel_vs_pilot_loco_max_in']:.2e} in |")
    L.append(f"| V3 kernel with multiplier 1 + V1b's ZUPT mask (σ 1, Huber) vs the V1b kernel / vs V1b's saved track | max {rt['kernel_vs_V1b_kernel_max_in']:.2e} in / "
             f"{rt['V1b_rebuilt_vs_saved_core_max_in']:.2e} in (core), {rt['V1b_rebuilt_vs_saved_all_max_in']:.2e} in (all) |")
    L.append(f"| V3's ZUPT mask = V1b's noRelease mask | {'all 50 animal-periods identical' if rt['zupt_equals_V1b_noRelease_all'] else 'DIFFERS'} |")
    L.append(f"| fixes = the audit's (fix cache rows, anchors, float32 raw) | rows {'all match' if rt['cache_match_all'] else 'MISMATCH'}; anchors "
             f"{'all match' if rt['anchors_match_all'] else 'MISMATCH'}; raw max {rt['raw_vs_saved_max_in']:.1e} in; segment fix counts {rt['seg_fixcount_mismatch']} mismatching; "
             f"IMU state ≠ 0 where QC fails: {rt['state_nonzero_where_not_ok']} seconds |")
    L.append(f"| step-B R1 rows of raw / B2 / V1b / V2b reproduced by this driver's T1 code ({r1['n_rows']} rows: 2 scales × 3 sets × 4 bands) | "
             f"max \\|Δd50\\| {r1['max_dd50_pp']:.3f} pp, \\|Δd95\\| {r1['max_dd95_pp']:.3f} pp (bound 0.1 pp) → {'pass' if r1['pass'] else '**FAIL**'}; "
             f"n seconds {'identical' if r1['n_equal_all'] else 'DIFFER'} |")
    L.append(f"| per-second estimator vs step B's saved values (clean seconds; csv with 6 significant digits) | u3 from raw {rt['stepB_u3_vs_here_raw_max']:.1e}, "
             f"v3 B2 {rt['stepB_v3_B2_vs_here_B2_max']:.1e} (rebuilt float64 vs saved float32 B2), V1b {rt['stepB_v3_V1b_vs_here_V1b_max']:.1e}, "
             f"V2b {rt['stepB_v3_V2b_vs_here_V2b_max']:.1e} in/s; 10-min blocks {'identical' if rt['stepB_block_equal_all'] else 'DIFFER'} |")
    for lab, d_ in rs.items():
        L.append(f"| still metrics, {lab} ({d_['n_rows']:,} segment × method rows) | max \\|Δ\\| RMS {_f(d_['rms_in'], 5)} in, 10-s drift {_f(d_['drift10_in'], 4)} in, "
                 f"fake path {_f(d_['path_in_per_min'], 4)} in/min, events {_f(d_['crazy_n'], 0)}, jumps {_f(d_['jumps'], 0)}, speed p95 {_f(d_['speed_p95'], 4)} |")
    if "events" in dsr:
        L.append("| S5 events vs the default-smoother run | " + "; ".join(f"{k} {v_['here']} ({v_['default_smoother']})" for k, v_ in dsr["events"].items()) + " |")
        L.append("| B2 / V2b S5 median lag vs the default-smoother run | " + "; ".join(
            f"{k} {_f(v_['here'], 2)} ({_f(v_['default_smoother'], 2)}) / {_f(dsr['V2b_lag_med'][k]['here'], 2)} ({_f(dsr['V2b_lag_med'][k]['default_smoother'], 2)}) s"
            for k, v_ in dsr["B2_lag_med"].items()) + " |")
        L.append("| B2 S1 median held-out error (moving) vs the default-smoother run | " + "; ".join(
            f"{k} {_f(v_['here'], 4)} ({_f(v_['default_smoother'], 4)}) in" for k, v_ in dsr["B2_s1_med"].items()) + " |")
        L.append("| B2 calm / rain fake path vs the default-smoother run | " + "; ".join(
            f"{k} {_f(v_['here'], 2)} ({_f(v_['default_smoother'], 2)}) in/min" for k, v_ in dsr["B2_fake_path"].items()) + " |")
    elif "error" in dsr:
        L.append(f"| default-smoother reproduction | not available: {dsr['error']} |")
    v1r = A["repro_v1b"]
    if "nis_mean_by_set" in v1r:
        L.append("| NIS mean (B2 / V1b) vs the V1b run | " + "; ".join(f"{k} {_f(v_['here'], 3)} ({_f(v_['v1b_run'], 3)})" for k, v_ in v1r["nis_mean_by_set"].items()) + " |")
    L.append(f"| ZUPT fixes / locomoting steps among analysis-mask window fixes (calm / rain) | {_p(zst['calm']['zupt_share'], 1, False)} / {_p(zst['rain']['zupt_share'], 1, False)}; "
             f"{_p(zst['calm']['loco_step_share'], 1, False)} / {_p(zst['rain']['loco_step_share'], 1, False)} |")
    L.append("")
    # ---------------- still
    L.append("## 2. Still metrics on the certified ≥ 30-s segments (reported; CIRCULAR for the ZUPT forms)\n")
    L.append("The IMU stillness that drives the ZUPT also certifies these segments: the ZUPT rows show what the constraint removes, not independent "
             "accuracy. Truth = the segment's median raw fix (drift is a lower bound). CIs: 10-min block bootstrap.\n")
    L.append("| set | method | still h | fake path in/min [CI] | fake speed p95 (in/s) | per-fix RMS (in) [CI] | p99 | 10-s drift med / p90 | 60-s drift med / p90 | ≥ 12-in events (/h) | jumps |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    zf_ = [m for m in TRACKS if m in ("V1b", "V2b") or (m in VARS and m != "V3_loco")]
    for s in ("calm", "rain"):
        for m in TRACKS:
            r = pooled[(pooled.set == s) & (pooled.method == m)].iloc[0]
            bp_, br_ = bsv(s, m, "path_rate"), bsv(s, m, "rms")
            L.append(f"| {s} | {LABEL[m]}{' *(circular)*' if m in zf_ else ''} | {_f(r.still_h)} | {_f(r.path_in_per_min)} [{_f(bp_.lo)}, {_f(bp_.hi)}] | {_f(r.speed_p95, 2)} | "
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
    L.append("**ZUPT coverage** (share of certified ≥ 30-s still time inside a ZUPT interval; fix share in parentheses; V1b after its release from the V1b run):\n")
    L.append("| set | kind | still h | V3 | V1b | house share of still time |")
    L.append("|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for k in ("all", "day", "night"):
            r = cov(s, k)
            L.append(f"| {s} | {k} | {_f(r.still_h)} | {_p(r.cov_V3, 1, False)} ({_p(r.fcov_V3, 1, False)}) | {_p(r.cov_V1b, 1, False)} | {_p(r.house_share_h, 1, False)} |")
    L.append("")
    L.append(f"![still](../figures/{figs['still']})\n")
    # ---------------- jitter
    L.append("## 3. In-place jitter check (reported)\n")
    L.append("(i) Where V3 should equal B2 — IMU-active fixes / seconds ≥ 3 s from any locomoting step or ZUPT fix of V3 (analysis mask):\n")
    L.append("| set | method | active fixes | share ≥ 3 s away | \\|track − B2\\| p50 / p95 / p99 [CI] / max (in) | 1-s speed p50; p95 vs B2 [CI] |")
    L.append("|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for m in VARS + ["V1b", "V2b"]:
            r = JP[(JP.set == s) & (JP.method == m)]
            if not len(r):
                continue
            r = r.iloc[0]
            q = JI[(JI.set == s) & (JI.track == m)]
            qtxt = (f"{_p(q.iloc[0].d50, 2)} [{_p(q.iloc[0].d50_lo, 1)}, {_p(q.iloc[0].d50_hi, 1)}]; {_p(q.iloc[0].d95, 2)} [{_p(q.iloc[0].d95_lo, 1)}, {_p(q.iloc[0].d95_hi, 1)}] "
                    f"(n {int(q.iloc[0].n_sec):,} s)") if len(q) else "–"
            L.append(f"| {s} | {SHORT[m]} | {int(r.n_active):,} | {_p(r.share_far, 1, False)} | {_f(r.get('p50'), 3)} / {_f(r.get('p95'), 3)} / {_f(r.get('p99'), 3)} "
                     f"[{_f(r.get('p99_lo'), 3)}, {_f(r.get('p99_hi'), 3)}] / {_f(r.get('max'), 2)} | {qtxt} |")
    L.append("")
    L.append(f"(ii) In-place activity — clean seconds the IMU calls locomoting while the clean-WISER 3-s speed is below the noise-floor p95 "
             f"({_f(A['floor95'], 3)} in/s); each track's 1-s speed relative to B2's (p50; p95):\n")
    L.append("| set | speed | n | B2 p50 / p95 (in/s) | " + " | ".join(SHORT[m] for m in ["raw", "V1b", "V2b"] + VARS) + " |")
    L.append("|---|---|---|---|" + "---|" * (3 + len(VARS)))
    for s in SETS3:
        for sp_ in ("S2 1-s speed", "step-B 1-s speed v1"):
            g = JR[(JR.set == s) & (JR.speed == sp_)]
            if not len(g):
                continue
            b_ = g[g.track == "B2"].iloc[0]
            cs = [f"{_p(g[g.track == m].iloc[0].d50, 0)}; {_p(g[g.track == m].iloc[0].d95, 0)}" for m in ["raw", "V1b", "V2b"] + VARS]
            L.append(f"| {s} | {sp_} | {int(b_.n_sec):,} | {_f(b_.p50, 2)} / {_f(b_.p95, 2)} | " + " | ".join(cs) + " |")
    L.append("")
    ja = JR[(JR.set == "all") & (JR.speed == "S2 1-s speed")].set_index("track")
    if len(ja):
        L.append(f"**Reading.** (i) Away from its changes V3 is B2 to within p99 {_f(JP[(JP.set == 'calm') & (JP.method == 'V3')].p99.iloc[0], 2)} in "
                 f"(calm; the residual is the smoother's impulse response decaying beyond 3 s; V1b's is smaller because its ZUPT is softer and it "
                 f"has no multiplier) and its 1-s speed equals B2's (|Δ| ≤ 0.1 %); V2b differs there by design (q × 0.3 in active seconds). "
                 f"(ii) Where the locomotion class is wrong (the head moves in place), the × 10 lets jitter through: V3's 1-s speed is "
                 f"{_p(ja.loc['V3', 'd50'], 0)} / {_p(ja.loc['V3', 'd95'], 0)} above B2's (p50 / p95; B2 {_f(ja.loc['B2', 'p50'], 2)} / "
                 f"{_f(ja.loc['B2', 'p95'], 2)} in/s), about V2b's level ({_p(ja.loc['V2b', 'd50'], 0)} / {_p(ja.loc['V2b', 'd95'], 0)}); × 3 lets in "
                 f"{_p(ja.loc['V3_m3', 'd50'], 0)}, × 30 {_p(ja.loc['V3_m30', 'd50'], 0)}. Raw fixes are {_p(ja.loc['raw', 'd50'], 0)} above B2 there, so "
                 f"V3 still removes most of the scatter, but path length or 1-s speed summed over in-place bouts will be larger under V3 than under "
                 f"B2/V1b.\n")
    # ---------------- NIS
    L.append("## 4. NIS by IMU state (reported)\n")
    L.append("Normalised innovation squared of each fix in the final forward pass (nominal anchors_used noise; P⁻ includes the method's q); "
             "consistent model mean 2, 5 % above 5.99. Analysis-mask window fixes.\n")
    L.append("| set | IMU state | n | B2 mean (> 95 %) | V1b mean | V3 mean (> 95 %) | V3-loco mean |")
    L.append("|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for st_ in ("still", "active", "locomoting", "QC failed"):
            rb, rv, r3, rl = (nis_r(m, "set×imu", set=s, imu=st_) for m in NIS_M)
            if rb is None:
                continue
            L.append(f"| {s} | {st_} | {int(rb.n):,} | {_f(rb['mean'], 2)} ({_p(rb.gt95, 1, False)}) | {_f(rv['mean'], 2)} | {_f(r3['mean'], 2)} ({_p(r3.gt95, 1, False)}) | {_f(rl['mean'], 2)} |")
    L.append("")
    L.append("At 9 anchors by zone (calm; mean NIS B2 → V3):\n")
    L.append("| zone | still | active | locomoting |")
    L.append("|---|---|---|---|")
    for zn in ("house", "outside"):
        cells = []
        for st_ in ("still", "active", "locomoting"):
            a_ = nis_r("B2", "set×abin×zone×imu", set="calm", abin="9", zone=zn, imu=st_)
            b_ = nis_r("V3", "set×abin×zone×imu", set="calm", abin="9", zone=zn, imu=st_)
            cells.append(f"{_f(a_['mean'] if a_ is not None else np.nan, 2)} → {_f(b_['mean'] if b_ is not None else np.nan, 2)} (n {int(a_.n) if a_ is not None else 0:,})")
        L.append(f"| {zn} | " + " | ".join(cells) + " |")
    L.append("")
    L.append(f"**Reading.** The × 10 brings the locomoting NIS from {_f(nism('B2', 'calm', 'locomoting'), 2)} to {_f(nism('V3', 'calm', 'locomoting'), 2)} "
             f"(calm; rain {_f(nism('B2', 'rain', 'locomoting'), 2)} → {_f(nism('V3', 'rain', 'locomoting'), 2)}) — toward 2 but not to it — and lowers "
             f"active and QC-failed fixes slightly (steps next to locomoting seconds); it pushes no stratum below 2. The firm ZUPT raises the still NIS "
             f"({_f(nism('B2', 'calm', 'still'), 2)} → {_f(nism('V3', 'calm', 'still'), 2)} calm): with the velocity pinned, P⁻ is smaller, so WISER's "
             f"own wander during stillness now shows up as innovation (V1b, σ 1, sits between). The anchors_used noise table therefore remains "
             f"optimistic in motion even with × 10, and V3's predicted spread is too narrow in stillness.\n")
    L.append(f"![nis](../figures/{figs['nis']})\n")
    # ---------------- S1 / S3 / fallback
    L.append("## 5. S1 (held-out fixes), S3 (rain excursions), fallback share — reported\n")
    L.append("| set | scheme | subset | n | B2 median (in) | V3 median | D(V3) [CI] | V3-loco median | D(V3-loco) [CI] | ZUPT share |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for sch in ("a", "s"):
            for subn in ("moving", "loco", "still", "all"):
                r = S1[(S1.set == s) & (S1.scheme == sch) & (S1.subset == subn)]
                if not len(r):
                    continue
                r = r.iloc[0]
                c3 = f" [{_p(r.get('D_V3_lo'), 2)}, {_p(r.get('D_V3_hi'), 2)}]" if subn == "moving" else ""
                cl_ = f" [{_p(r.get('D_V3_loco_lo'), 2)}, {_p(r.get('D_V3_loco_hi'), 2)}]" if subn == "moving" else ""
                L.append(f"| {s} | ({sch}) | {subn} | {int(r.n):,} | {_f(r.med_B2, 4)} | {_f(r.med_V3, 4)} | {_p(r.D_V3, 2)}{c3} | {_f(r.med_V3_loco, 4)} | "
                         f"{_p(r.D_V3_loco, 2)}{cl_} | {_p(r.zupt_share, 1, False)} |")
    L.append("")
    L.append("S3 — ≥ 12-in excursions in the primary ≥ 30-s segments; rate differences per still-hour [95 % CI]:\n")
    L.append("| method | calm events | rain events | rain − raw | rain − B2 |")
    L.append("|---|---|---|---|---|")
    for m in TRACKS:
        rc0 = S3[(S3.set == "calm") & (S3.method == m)].iloc[0]
        rr0 = S3[(S3.set == "rain") & (S3.method == m)].iloc[0]
        L.append(f"| {LABEL[m]} | {int(rc0.crazy_n)} ({_f(rc0.crazy_per_h, 3)}/h) | {int(rr0.crazy_n)} ({_f(rr0.crazy_per_h, 3)}/h) | "
                 f"{_f(rr0.diff_vs_raw, 3)} [{_f(rr0.diff_raw_lo, 3)}, {_f(rr0.diff_raw_hi, 3)}] | {_f(rr0.diff_vs_B2, 3)} [{_f(rr0.diff_B2_lo, 3)}, {_f(rr0.diff_B2_hi, 3)}] |")
    L.append("")
    L.append("Fallback share (analysis-mask window fixes whose aligned second is not IMU-QC-ok → V3 = B2 there):\n")
    L.append("| set | fixes | IMU-QC failed | with ZUPT | on a locomoting step |")
    L.append("|---|---|---|---|---|")
    for r in FBS.itertuples():
        L.append(f"| {r.set} | {r.n_fix_mask:,} | {_p(r.imu_fail_share, 1, False)} | {_p(r.zupt_share, 1, False)} | {_p(r.loco_step_share, 1, False)} |")
    L.append("")
    # ---------------- do not do
    L.append("## Do not do\n")
    L.append("- Do not read the still-period gains of V3 as evidence that the IMU makes WISER more accurate: the IMU stillness that drives the ZUPT also certifies the test segments.")
    L.append("- Do not read T1 as accuracy under poor anchors or in the houses: the clean reference exists only on open-field seconds with ≥ 8 anchors.")
    L.append("- Do not run V3 on tags without a head IMU (the five females released 09-11) or through IMU-failed stretches as if it were different from B2 there: it is B2 by construction.")
    L.append("- Do not promote a sensitivity variant from this report: a passing variant is a proposal to the user.")
    L.append("- Do not generalise the still numbers to the open field (most certified stillness is inside the houses) or to other cohorts without re-running.")
    L.append("- Do not place positions in the paddock: distances are in the unverified WISER inch frame.")
    L.append("")
    L.append(DEFINITIONS)
    # ---------------- caveats
    L.append("## Caveats\n")
    L.append("- T1's reference exists only on clean open-field seconds (≥ 8 anchors, no jumps) — speed under poor anchors and in the houses stays unreferenced.")
    L.append("- The > 15 in/s band is selected on the noisy reference (selection regression, small at 3 s); the 1-s scale is noisier.")
    L.append("- The locomotion class (TPR 0.75 / FPR 0.15) was fitted against WISER speed; × 10 was tuned on 09-08/09, one of the nights T1 uses; B2's q too.")
    L.append("- Still metrics are circular; ≥ 95 % of certified stillness is in the houses; truth is the segment's own WISER median.")
    L.append("- S5 lags are defined only where the speed reaches 3 in/s; the paired medians use events where both tracks are defined; the median hides the shifted minority (reported).")
    L.append("- The rain set is three weather episodes; block CIs treat 10-min blocks as independent within a set.")
    L.append("- NIS uses the final forward pass with the nominal noise: Huber-down-weighted fixes still enter with their nominal variance.")
    L.append("- Speed CIs come from per-block histograms with log-spaced bins (≈ 0.28 % relative width, step B's code): CI ends are quantised in steps of "
             "≈ 0.28 %, and an end at exactly 0.0 % means the track and the reference fell in the same bin.")
    L.append("- S1 on the still subset favours the ZUPT forms by construction (the hidden still fixes scatter around a position the ZUPT holds); only the moving subset is an identity check.")
    L.append("")
    L.append("## Files\n")
    L.append(f"Bulk `{out}`: `tracks/<SFxx>_<period>.npz` (B2, V3 and the five sensitivities at every fix; ZUPT mask, locomoting-step mask, "
             f"influence mask and the time to it; ZUPT Huber weights; NIS of B2 / V1b (rebuilt) / V3 / V3-loco; analysis mask, IMU state, zone; "
             f"|track − B2|), `seconds/` (S2 1-s speeds of every track; on the six nights also step B's clean flag, u3, u1 and every track's v3, v1), "
             f"`speeds/` (still fake speeds), `s1/` (held-out errors), `tables/` (t1_speed, t1_by_animal, t1_repro_stepB, t2_still_jumps(_jobs), "
             f"t2_mask_jumps(_jobs), t2_still_jump_list, t3_events, t3_lags, still_metrics, still_fixes, still_pooled, still_setkind, still_bootstrap, "
             f"s3_excursions, zupt_coverage(_segments), jitter_active_position, jitter_active_speed, jitter_inplace_speed, nis, s1_heldout, "
             f"fallback_share, fallback_jobs, reproduction_tracks), `summary.json`, `input_provenance.json`, logs. Re-aggregate without recomputing: "
             f"`python {DRIVER} --report-only <run_dir>`. Pointer: `results/{cohort}/wiser_baseline/reports/run_manifest_v3_{cohort}.json`.\n")
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
    dec, ver = A["dec"], A["ver"]
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name, "driver": DRIVER,
            "config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": C.git_commit(), "figures": sorted(figs.values()),
            "audit_run": cfg["audit_run"], "v1b_run": cfg["v1b_run"], "speed_proxy_run": cfg["speed_proxy_run"],
            "default_smoother_run": cfg["default_smoother_run"], "v3_passes": dec["V3_passes"], "default_implanted": dec["default_implanted"]}
    rep.write_text(render_report(A, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_v3_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    v = ver["V3"]
    cj["decision"] = {
        "V3_passes": dec["V3_passes"], "failed_criteria": dec["failed_criteria"],
        "default_wiser_track_implanted": dec["default_implanted"], "universal_baseline": "B2",
        "where": "SF07-SF12 wherever the IMU QC passes (V3 is B2 by construction elsewhere)" if dec["V3_passes"] else "V1b stays the default for the implanted animals; B2 elsewhere",
        "T1_d95_3s_all": round(v["T1_d95_all"], 5), "T1_d95_3s_gt15": round(v["T1_d95_gt15"], 5),
        "T1_ci": {"all": [round(x, 5) for x in v["T1_d95_all_ci"]], "gt15": [round(x, 5) for x in v["T1_d95_gt15_ci"]]},
        "T2_jumps_still_mask": [v["T2_still_jumps"], v["T2_mask_jumps"]], "T3_dlag_med_s": v["T3_dlag"],
        "sensitivity": {m: ("pass" if ver[m]["pass_all"] else "fail " + ", ".join(ver[m]["failed"])) for m in SENS},
        "variants_that_would_pass": dec["variants_that_would_pass"], "context": dec["context_outcomes"],
        "run_dir": str(out), "report": f"results/{cohort}/wiser_baseline/reports/{rep.name}",
        "decided_local": pd.Timestamp.now(tz=cfg.get("tz", "America/New_York")).strftime("%Y-%m-%d %H:%M:%S")}
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}\ndecision written into {cp.name}: V3 {'passes' if dec['V3_passes'] else 'fails'}")


# ====================================================================================================== selftest
def _synth(seed: int = 7, dur_s: float = 3000.0) -> dict:
    """Synthetic head track: still bouts 40-120 s, walking bouts 20-50 s (OU velocity, tau 3 s, 8 in/s per axis) each with
    one planted 3-s fast burst (30 in/s), in-place activity bouts 15-40 s (no displacement; IMU active, every other second
    'locomoting' in the first half of each minute); WISER-like fix intervals, anchors 6-9 with anchor-dependent noise, rare outliers."""
    rng = np.random.default_rng(seed)
    m_ = int(dur_s / 0.18) + 20
    t = np.cumsum(rng.choice([0.134, 0.268], size=m_, p=[0.45, 0.55]) + rng.normal(0, 0.003, m_))
    t = t[t < dur_s]
    n = len(t)
    dg = 0.02
    g = np.arange(int(round((dur_s + 2) / dg))) * dg
    kind = np.zeros(len(g), np.int8)            # 0 still, 1 walk, 2 in place
    burst = np.zeros(len(g), bool)
    pos = 10.0
    cyc = 0
    while pos < dur_s:
        k = (0, 1, 0, 2, 1)[cyc % 5]
        L_ = {0: rng.uniform(40, 120), 1: rng.uniform(20, 50), 2: rng.uniform(15, 40)}[k]
        sel = (g >= pos) & (g < pos + L_)
        kind[sel] = k
        if k == 1:
            b0 = pos + rng.uniform(5, L_ - 8)
            burst[(g >= b0) & (g < b0 + 3.0)] = True
        pos += L_
        cyc += 1
    vel = np.zeros((len(g), 2))
    vv = np.zeros(2)
    hd = rng.uniform(0, 2 * np.pi)
    for k in range(1, len(g)):
        if kind[k] != 1:
            vv = np.zeros(2)
        elif burst[k]:
            if not burst[k - 1]:
                hd = rng.uniform(0, 2 * np.pi)
            vv = 30.0 * np.array([np.cos(hd), np.sin(hd)])
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
    secs = np.arange(0, int(dur_s) + 1)
    per = int(round(1.0 / dg))
    kb = kind[:per * len(secs)].reshape(len(secs), per)
    st_full = (kb == 0).all(axis=1)
    walk_full = (kb == 1).all(axis=1)
    inpl_full = (kb == 2).all(axis=1)
    state = np.where(st_full, 1, np.where(walk_full, 3, 2)).astype(np.int8)
    alt = (secs % 2 == 0) & (secs % 60 < 30)
    state[inpl_full & alt] = 3                  # in-place activity mislabelled as locomoting every other second (half of the time)
    burst_s = burst[:per * len(secs)].reshape(len(secs), per).all(axis=1)
    return {"t": t, "z": z, "p": p, "A": A, "secs": secs, "state": state, "g": g, "pg": pg, "burst_s": burst_s, "inpl_s": inpl_full}


def selftest() -> int:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    t0 = time.time()
    cfg = {"v3": {"sigma_zupt_inps": 0.25, "huber_zupt": True, "loco_mult": 10.0, "min_run_s": 3, "erode_s": 1},
           "variants": {"V3_s05": {"sigma_zupt_inps": 0.5, "loco_mult": 10.0, "zupt": True}, "V3_s10": {"sigma_zupt_inps": 1.0, "loco_mult": 10.0, "zupt": True},
                        "V3_m3": {"sigma_zupt_inps": 0.25, "loco_mult": 3.0, "zupt": True}, "V3_m30": {"sigma_zupt_inps": 0.25, "loco_mult": 30.0, "zupt": True},
                        "V3_loco": {"sigma_zupt_inps": 0.0, "loco_mult": 10.0, "zupt": False}}}
    tuned = {"B2": {"q": 3.0, "mrej": 1e9}, "huber_k": P.HUBER_K, "gate2": P.GATE2, "n_irls": P.N_IRLS}
    specs = kf_specs(tuned, cfg)
    check("specs: B2 multiplier 1 / no ZUPT; V3 x10 + sigma 0.25 Huber; V3-loco without ZUPT",
          specs["B2"]["mloco"] == 1.0 and not specs["B2"]["zupt"] and specs["V3"]["mloco"] == 10.0 and specs["V3"]["sv"] == 0.25
          and specs["V3"]["huber_zupt"] and not specs["V3_loco"]["zupt"] and specs["V3_loco"]["sv"] == 0.0)
    # 1) ZUPT erosion and minimum run on planted runs
    secs = np.arange(100, 140)
    st = np.zeros(len(secs), bool)
    st[2:4] = True          # 2-s run -> none
    st[6:9] = True          # 3-s run -> [107, 108)
    st[12:22] = True        # 10-s run -> [113, 121)
    iv = V1B.eroded(V1B.still_runs(st, secs), 3, 1)
    check("ZUPT erosion / minimum run: 2-s run none, 3-s run 1 s, 10-s run 8 s", iv.tolist() == [[107.0, 108.0], [113.0, 121.0]], f"{iv.tolist()}")
    tq = np.array([106.9, 107.0, 107.5, 108.0, 112.99, 113.0, 120.99, 121.0, 102.5])
    check("ZUPT membership: a fix belongs when its aligned time lies inside [e0, e1)",
          V1B.membership(tq, iv)[1].tolist() == [False, True, True, False, False, True, True, False, False])
    # locomoting steps by the midpoint second
    st_sec = np.array([0, 3, 2, 3, 1, 3], np.int8)
    tf = np.array([0.2, 0.9, 1.4, 2.1, 3.6, 4.4, 5.5]) * 1000.0     # step midpoints 0.55, 1.15, 1.75, 2.85, 4.0, 4.95 s
    mid_, _ = P.step_states(tf, np.arange(6), st_sec)
    ls = loco_steps(mid_, 3)
    check("locomoting step = midpoint second in state 3 (first fix has no step; the last fix's own second is 3 but its step's midpoint is not)",
          ls.tolist() == [False, False, True, True, False, False, False], f"{ls.tolist()}")
    # 2) synthetic track: kernel reproductions
    syn = _synth()
    t, z, A_, secs = syn["t"], syn["z"], syn["A"], syn["secs"]
    n = len(t)
    devs = []
    for a_, b_ in C.true_runs(syn["state"] == 1):
        if b_ - a_ < 40:
            continue
        m = (t >= a_ + 1) & (t < b_ - 1)
        zz = z[m]
        devs.append(pd.DataFrame({"anchors_used": A_[m], "dx": zz[:, 0] - np.median(zz[:, 0]), "dy": zz[:, 1] - np.median(zz[:, 1])}))
    table = P.anchor_sigma_table(pd.concat(devs))
    r2 = P.r2_from_anchors(A_, table)
    vis = np.ones(n, bool)
    none = np.zeros(n, bool)
    st_mid, st_at = P.step_states(t * 1000.0, secs, syn["state"])
    loco = loco_steps(st_mid, 3)
    still_s = syn["state"] == 1
    ivs = V1B.eroded(V1B.still_runs(still_s, secs), 3, 1)
    zupt = V1B.membership(t, ivs)[1]
    trk, nis, wzs = {}, {}, {}
    for m in KF:
        sp = specs[m]
        trk[m], _, nis[m], wzs[m] = kf_v3(t, z, r2, vis, zupt if sp["zupt"] else none, qmult(loco, sp["mloco"]), sp, tuned)
    Pref, _, _ = P.kf_run(t, z, r2, [vis], [st_mid], [st_at], [{"q": 3.0, "mrej": 1e9}, {"q": 3.0, "mrej": 1e9, "mult": (1.0, 1.0, 1.0, 10.0)}])
    dk = float(np.max(np.hypot(*(trk["B2"] - Pref[0]).T)))
    check("multiplier 1 + no ZUPT = the pilot's B2 (<= 1e-6 in)", dk <= 1e-6, f"max {dk:.2e} in")
    dl = float(np.max(np.hypot(*(trk["V3_loco"] - Pref[1]).T)))
    check("x10 without ZUPT = the pilot's kernel with multipliers (1, 1, 1, 10) (<= 1e-6 in)", dl <= 1e-6, f"max {dl:.2e} in")
    spv = {"q": 3.0, "mrej": 1e9, "sv": 1.0, "huber_zupt": True}
    Pa, _, _, _ = kf_v3(t, z, r2, vis, zupt, np.ones(n), spv, tuned)
    Pb_, _, _, _ = V1B.kf_v1b(t, z, r2, vis, zupt, spv, tuned)
    dv = float(np.max(np.hypot(*(Pa - Pb_).T)))
    check("multiplier 1 + ZUPT sigma 1 Huber = the V1b kernel (<= 1e-9 in)", dv <= 1e-9, f"max {dv:.2e} in")
    # 3) x10 follows the planted bursts better than B2 (3-s speed deficit vs the true track)
    rc = {"u3_offset_s": 1.5, "u3_half_s": 0.5, "u1_offset_s": 0.5, "u1_half_s": 0.375, "min_fix": 3}
    u_true, _ = SP.track_speeds(t, syn["p"], secs, rc)
    bs = syn["burst_s"] & np.isfinite(u_true)
    defi = {}
    for m in ("B2", "V3_loco", "V3"):
        v3m, _ = SP.track_speeds(t, trk[m], secs, rc)
        defi[m] = 1.0 - float(np.median(v3m[bs] / u_true[bs]))
    check("x10 follows the planted 30-in/s bursts better than B2 (smaller median 3-s speed deficit vs truth)",
          defi["V3_loco"] < defi["B2"] and defi["V3"] < defi["B2"],
          f"deficit B2 {100 * defi['B2']:.1f} %, V3-loco {100 * defi['V3_loco']:.1f} %, V3 {100 * defi['V3']:.1f} % over {int(bs.sum())} burst seconds")
    # 4) ZUPT firmness: still fake path B2 > sigma 1.0 > sigma 0.25 (sanity)
    mc = {"roll_short_s": 10.0, "roll_short_min_fix": 10, "roll_long_s": 60.0, "roll_long_min_fix": 60, "roll_long_min_seg_s": 120.0,
          "crazy_in": 12.0, "crazy_min_s": 10, "jump_in": 30.0, "jump_dt_s": 0.35, "speed_grid_s": 0.25, "speed_max_gap_s": 1.0}
    path = {m: 0.0 for m in ("B2", "V3_s10", "V3")}
    sec_ = 0.0
    for a_, b_ in C.true_runs(still_s):
        if b_ - a_ < 30:
            continue
        ts, te = a_ + 1.0, b_ - 1.0
        i0, i1 = np.searchsorted(t, [ts, te])
        res, _, _, _ = FA.score_segment(t[i0:i1], {m: trk[m][i0:i1] for m in path}, np.median(z[i0:i1], axis=0), ts, te, mc, list(path))
        for m in path:
            path[m] += res[m]["path_in"]
        sec_ += res["B2"]["path_s"]
    check("still fake path: V3 (sigma 0.25) < V3-sigma1.0 < B2", path["V3"] < path["V3_s10"] < path["B2"],
          f"{path['V3'] / (sec_ / 60):.2f} < {path['V3_s10'] / (sec_ / 60):.2f} < {path['B2'] / (sec_ / 60):.2f} in/min")
    lf = np.r_[False, loco[1:]] & np.isfinite(nis["B2"])
    check("NIS on locomoting steps is lower with x10 than with B2's q (planted bursts)", float(np.nanmean(nis["V3_loco"][lf])) < float(np.nanmean(nis["B2"][lf])),
          f"{np.nanmean(nis['V3_loco'][lf]):.2f} vs {np.nanmean(nis['B2'][lf]):.2f}")
    check("NIS defined for every visible fix; B2 mean in [1, 6]", np.isfinite(nis["B2"]).all() and 1.0 <= float(np.mean(nis["B2"])) <= 6.0,
          f"mean {np.mean(nis['B2']):.2f}")
    # 5) evaluators on planted cases
    u3r, _ = SP.track_speeds(t, z, secs, rc)
    damp = z.mean(axis=0) + 0.9 * (z - z.mean(axis=0))
    v_d, _ = SP.track_speeds(t, damp, secs, rc)
    e_raw, e_d = t1_eval(u3r, u3r, 15.0, 0.03), t1_eval(u3r, v_d, 15.0, 0.03)
    check("T1 evaluator: the reference itself passes; a x0.9 speed-damped track fails (d95 -10 %)", e_raw["pass"] and not e_d["pass"] and abs(e_d["d95_all"] + 0.1) < 1e-6,
          f"(damped d95 {100 * e_d['d95_all']:+.2f} % / fast {100 * e_d['d95_fast']:+.2f} %, n fast {e_d['n_fast']})")
    rng = np.random.default_rng(3)
    uu = rng.gamma(2.0, 4.0, 20000)
    vtop = np.where(uu > 15, uu * 0.95, uu)
    e_t = t1_eval(uu, vtop, 15.0, 0.03)
    check("T1 evaluator: +2 % passes; a damping only above 15 in/s fails (b)", t1_eval(uu, uu * 1.02, 15.0, 0.03)["pass"] and not e_t["pass"]
          and abs(e_t["d95_fast"]) > 0.03, f"(d95 all {100 * e_t['d95_all']:+.2f} %, fast {100 * e_t['d95_fast']:+.2f} %)")
    pj = trk["V3"].copy()
    kj = int(np.flatnonzero(np.diff(t) <= 0.2)[100])
    pj[kj + 1] += np.array([40.0, 0.0])
    check("T2 evaluator: V3 has no jump; a planted 40-in step is two jumps", t2_eval(t, trk["V3"], 30.0, 0.35)["pass"] and t2_eval(t, pj, 30.0, 0.35)["jumps"] == 2)
    lag = rng.normal(7.0, 3.0, 300)
    check("T3 evaluator: a planted 1-s delay fails; +0.25 s passes; 1 s earlier passes (one-sided); undefined events ignored",
          not t3_eval(lag + 1.0, lag, 0.5)["pass"] and t3_eval(lag + 0.25, lag, 0.5)["pass"] and t3_eval(lag - 1.0, lag, 0.5)["pass"]
          and t3_eval(np.where(np.arange(300) < 50, np.nan, lag + 0.25), lag, 0.5)["n_paired"] == 250)
    # 6) S5 lags through the default-smoother code on the synthetic tracks; a 1-s delayed copy of V3 fails T3
    s5 = {"speed_thr_inps": 3.0, "onset_pre_s": 5.0, "onset_post_s": 20.0, "offset_pre_s": 20.0, "offset_post_s": 10.0, "grid_s": 0.25,
          "max_gap_s": 1.0, "still_run_min_s": 10, "loco_search_s": 60, "edge_s": 10.0}
    ev = DS.transition_events(syn["state"], secs, 0.0, float(secs[-1] + 1) * 1000.0, s5)
    lb = np.array([DS.event_lag(t, trk["B2"], e, s5)[0] for e in ev])
    lv = np.array([DS.event_lag(t, trk["V3"], e, s5)[0] for e in ev])
    lv_d = np.array([DS.event_lag(t + 1.0, trk["V3"], e, s5)[0] for e in ev])
    r_ = t3_eval(lv, lb, 0.5)
    rd = t3_eval(lv_d, lb, 0.5)
    print(f"   synthetic S5: {len(ev)} events, V3 - B2 median {r_['dlag_med']:.2f} s (n {r_['n_paired']}); 1-s delayed V3 {rd['dlag_med']:.2f} s", flush=True)
    check("synthetic S5 events found, lags defined for both tracks; a 1-s delayed track fails T3", len(ev) >= 4 and r_["n_paired"] >= 4 and not rd["pass"])
    # 7) in-place activity: x10 lets some jitter through on mislabelled seconds (reported, not a criterion)
    ip = syn["inpl_s"] & (syn["state"] == 3)
    vs = {m: DS.second_speeds(t, trk[m], secs, 1.0) for m in ("B2", "V3")}
    okk = ip[:len(vs["B2"])] & np.isfinite(vs["B2"]) & np.isfinite(vs["V3"])
    print(f"   in-place 'locomoting' seconds: 1-s speed p50 B2 {np.median(vs['B2'][okk]):.2f}, V3 {np.median(vs['V3'][okk]):.2f} in/s (n {okk.sum()})", flush=True)
    dinf = V1B.dist_to_mask(t, infl_mask(zupt, loco))
    dd3 = np.hypot(*(trk["V3"] - trk["B2"]).T)
    far, near = dinf >= 3.0, dinf < 1.0
    p99f = float(np.percentile(dd3[far], 99)) if far.sum() else np.nan
    p99n = float(np.percentile(dd3[near], 99)) if near.sum() else np.nan
    # the difference decays like the smoother's impulse response (synthetic p99 ~3.3 / 0.9 / 0.3 / 0.1 / 0.05 / 0.01 in at
    # < 1 / 1-2 / 2-3 / 3-4 / 4-6 / >= 6 s), so the check is a decay check, not a hard zero
    check("V3 = B2 away from its changes: p99 |V3 - B2| >= 3 s from any locomoting step / ZUPT fix <= 0.1 in and < 5 % of the p99 within 1 s",
          far.sum() > 50 and p99f <= 0.1 and p99f < 0.05 * p99n, f"p99 {p99f:.4f} in over {far.sum()} fixes vs {p99n:.3f} in within 1 s")
    print(f"numba: {P.HAVE_NUMBA}; selftest {time.time() - t0:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--report-only", default=None, help="existing run dir: re-aggregate and re-render from its saved per-job files")
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
