r"""Head-IMU inertial fusion with WISER, V5 (cohort 2026c): attitude outside the position filter (Stage A, IMU only) and a
16-Hz EKF + RTS position filter with WISER updates at the fix times (Stage B), scored on held-out WISER fixes against B2'
and V2 with a +1 h-shifted-IMU control.

Plan: implementation_plan/2026-10-01-wiser-ins-fusion-v5.md (approved by the user 2026-10-01 "start v5"; pre-registered
before any computation on the test periods). Follows the attitude gate v2 (change_log/2026-10-01-imu-attitude-gate-v2.md)
and the V4 audit (change_log/2026-09-29-wiser-ins-fusion.md, final section).

Stage A (per animal-period, IMU only): gate v2's `process_period` (A1/A3 caches -> Phase-0 gyro chain with held-reading
reconstruction -> strict still windows); per-animal gyro scale from gate v2's selection; gyro bias piecewise-linear in
clock time anchored at every strict window (raw ZARU or noise-weighted RTS-smoothed anchors, chosen on the tuning periods by
a leave-window-out test); 100-Hz attitude with gravity aiding only inside strict windows (linear closure between window
centres); world-frame horizontal specific force low-passed 2 Hz -> 16 Hz; sigma_theta from the gate-v2 clock-time law.
Written as the reusable cache <OUT>/2026c/attitude16_cache/<SFxx>/<period>.npz (+ README).

Stage B: state p (2), v (2), world-frame horizontal acceleration bias b (2, Gauss-Markov, stationary SD = g sin sigma_theta),
yaw offset psi (random walk; initialised by regression of WISER velocity changes on IMU velocity changes), WISER drift d
(2, AR(1), only if the measured variogram justifies it). INS mode u = R(psi) f - b where the IMU is usable and a strict
window is recent; V2-like CV mode elsewhere. WISER updates with the measured per-anchor white variance, chi2 gate + Huber
IRLS, soft ZUPT in IMU-still and rhythmic body-stationary states. Tuned (sigma_res, tau_b, T_max, sigma_v, sigma_vr) on the
tuning periods: minimum held-out RMSE on (s) + (g-0.5 s) subject to NIS in [1.5, 3].

Inputs (read-only): caches under D:/Field2026_analysis_out/2026c/ (A1 imu_raw_cache, A3 imu100_cache incl. day_ files,
A2 wiser_fix_cache) and the make_imu 50-Hz npz (night per-second IMU QC/states of the smoothing pilot, unchanged). Raw
drives are never read. Reused unmodified by import: analyze_wiser_imu_smoothing.py, analyze_wiser_ins_fusion.py,
analyze_imu_attitude_phase0.py, analyze_imu_attitude_gate_v2.py, analyze_imu_wiser_calibration.py.

Usage:
  python wiser/scripts/analyze_wiser_ins_fusion_v5.py --cohort 2026c [--workers 5] [--threads 22]
  python wiser/scripts/analyze_wiser_ins_fusion_v5.py --cohort 2026c --roles tuning        # development, tuning only
  python wiser/scripts/analyze_wiser_ins_fusion_v5.py --report-only <run_dir>
  python wiser/scripts/analyze_wiser_ins_fusion_v5.py --selftest
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit, prange, set_num_threads
from scipy import signal
from scipy.ndimage import uniform_filter1d
from scipy.optimize import least_squares, minimize

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (smoothing pilot: Track, hidden sets, baselines, boot_delta; unmodified)
import analyze_wiser_ins_fusion as V4  # noqa: E402  (context, per-second IMU tables; unmodified)
import analyze_imu_attitude_phase0 as P0  # noqa: E402  (quaternion kernels, bout propagation; unmodified)
import analyze_imu_attitude_gate_v2 as GV2  # noqa: E402  (process_period, strict windows, bouts; unmodified)
import analyze_imu_wiser_calibration as C  # noqa: E402  (to_ms, in_any, tag helpers; unmodified)
import make_imu as MI  # noqa: E402

DIRECTION = "wiser_baseline"
NAME = "wiser_ins_fusion_v5"
STEM = f"{DIRECTION}_ins_fusion_v5"
G = MI.G                                   # 9.81 m/s^2
IN_PER_M = 39.37007874
G_IN = G * IN_PER_M                        # in/s^2
FS100, DT100 = 100.0, 0.01
DT16 = 1.0 / 16.0
D2R, R2D = math.pi / 180.0, 180.0 / math.pi
SCHEMES = ("s", "g05", "g10", "a", "a2")
SCHEME_LABEL = {"s": "(s) single-fix", "g05": "(g) 0.5-s gaps", "g10": "(g) 1.0-s gaps", "a": "(a) runs of 4-8", "a2": "(a′) 2-s windows"}
LABEL = {**P.LABEL, "V5": "V5 INS (Stage A + EKF/RTS)", "V5_shift": "V5 (IMU +1 h)", "V5_p90": "V5, p90 σθ law"}
_qmul, _qexp, _g_head = P0._qmul, P0._qexp, P0._g_head
_qrot = GV2._qrot


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
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, Path):
        return str(o)
    return str(o)


def fval(x) -> float:
    """Config value -> float ('inf' allowed)."""
    return math.inf if (isinstance(x, str) and x.lower() == "inf") else float(x)


def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_ins_fusion_v5_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def relpath(p) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(p)


def to_ms(local: str, tz: str = "America/New_York") -> int:
    return C.to_ms(local, tz)


def ms_local(ms: float, tz: str = "America/New_York") -> str:
    return pd.Timestamp(int(round(ms)), unit="ms", tz="UTC").tz_convert(tz).strftime("%Y-%m-%d %H:%M:%S")


def period_bounds(cfg: dict, pk: str) -> tuple[float, float]:
    p = cfg["periods"][pk]
    return float(to_ms(p["start"], cfg["tz"])), float(to_ms(p["end"], cfg["tz"]))


def gyro_scales(cfg: dict) -> dict:
    sel = json.loads(Path(cfg["gate_v2_selection"]).read_text(encoding="utf-8"))
    assert sel["selected_model"] == "scalar", sel["selected_model"]
    return {a: float(v["M"][0][0]) for a, v in sel["per_animal"].items()}


# ====================================================================================================== Stage A kernels
@njit(cache=True)
def _q_from_up(ux, uy, uz):
    """q (head -> world, minimal rotation) with R(q) u = e_z for the unit head-frame up vector u."""
    n = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / n, uy / n, uz / n
    ax, ay = uy, -ux
    s = math.sqrt(ax * ax + ay * ay)
    if s < 1e-12:
        if uz > 0:
            return (1.0, 0.0, 0.0, 0.0)
        return (0.0, 1.0, 0.0, 0.0)
    ang = math.atan2(s, uz)
    h = math.sin(0.5 * ang) / s
    return (math.cos(0.5 * ang), ax * h, ay * h, 0.0)


@njit(cache=True)
def _qnorm(q):
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


@njit(cache=True)
def _stage_a_kernel(w, valid, wc, gw, dt, q_out, clos):
    """Attitude at 100 Hz with gravity aiding only at strict-window centres.
    w (n,3) rad/s head frame (bias removed, scaled); valid (n,) bool (invalid samples hold q); wc (m,) window-centre sample
    indices (increasing); gw (m,3) unit window gravity (head frame). q_out (n,4) head->world; clos (m,) closure angle (rad)
    of the forward propagation from window i-1's centre to window i's (NaN for i = 0). Between centres the closure rotation
    (world frame, horizontal axis) is applied linearly in sample index."""
    n = w.shape[0]
    m = wc.shape[0]
    k0 = wc[0]
    q = _q_from_up(gw[0, 0], gw[0, 1], gw[0, 2])
    q_out[k0, 0], q_out[k0, 1], q_out[k0, 2], q_out[k0, 3] = q[0], q[1], q[2], q[3]
    for k in range(k0 - 1, -1, -1):
        if valid[k]:
            q = _qnorm(_qmul(q, _qexp(-w[k, 0] * dt, -w[k, 1] * dt, -w[k, 2] * dt)))
        q_out[k, 0], q_out[k, 1], q_out[k, 2], q_out[k, 3] = q[0], q[1], q[2], q[3]
    clos[0] = np.nan
    for i in range(m):
        ka = wc[i]
        kb = wc[i + 1] if i + 1 < m else n - 1
        q = (q_out[ka, 0], q_out[ka, 1], q_out[ka, 2], q_out[ka, 3])
        for k in range(ka, kb):
            if valid[k]:
                q = _qnorm(_qmul(q, _qexp(w[k, 0] * dt, w[k, 1] * dt, w[k, 2] * dt)))
            q_out[k + 1, 0], q_out[k + 1, 1], q_out[k + 1, 2], q_out[k + 1, 3] = q[0], q[1], q[2], q[3]
        if i + 1 < m:
            u = _qrot(q, gw[i + 1, 0], gw[i + 1, 1], gw[i + 1, 2])
            ax, ay = u[1], -u[0]
            s = math.sqrt(ax * ax + ay * ay)
            ang = math.atan2(s, u[2])
            clos[i + 1] = ang
            if s > 1e-12 and kb > ka:
                ax, ay = ax / s, ay / s
                for k in range(ka + 1, kb + 1):
                    r = ang * (k - ka) / (kb - ka)
                    sh = math.sin(0.5 * r)
                    dq = (math.cos(0.5 * r), ax * sh, ay * sh, 0.0)
                    qq = _qnorm(_qmul(dq, (q_out[k, 0], q_out[k, 1], q_out[k, 2], q_out[k, 3])))
                    q_out[k, 0], q_out[k, 1], q_out[k, 2], q_out[k, 3] = qq[0], qq[1], qq[2], qq[3]


@njit(cache=True)
def _rw_filter(tc, y, d, start, qb, sr2, sw2, clip, xs, ps, xf_out, pf_out, xp_out, pp_out):
    """1-D random-walk Kalman filter (+ RTS) over window ZARU estimates y (deg/s) with measurement variance
    sr2/d^2 + sw2/d; robust: a standardized innovation beyond `clip` inflates R (Huber). start[i] marks a sequence start.
    Returns the Huber negative log-likelihood (first observation of each sequence excluded); writes smoothed xs, ps."""
    N = y.shape[0]
    nll = 0.0
    x, Pv = 0.0, 0.0
    for i in range(N):
        R = sr2 / (d[i] * d[i]) + sw2 / d[i]
        if start[i]:
            x, Pv = y[i], R
            xp_out[i], pp_out[i] = y[i], 1e12
            xf_out[i], pf_out[i] = x, Pv
            continue
        Pv += qb * max(tc[i] - tc[i - 1], 0.0)
        xp_out[i], pp_out[i] = x, Pv
        S = Pv + R
        nu = y[i] - x
        r = abs(nu) / math.sqrt(S)
        if r > clip:
            nll += 0.5 * (math.log(S) + 2.0 * clip * r - clip * clip)
            R = R * r / clip
            S = Pv + R
        else:
            nll += 0.5 * (math.log(S) + r * r)
        K = Pv / S
        x += K * nu
        Pv = (1.0 - K) * Pv
        xf_out[i], pf_out[i] = x, Pv
    # RTS per sequence (backwards; a sequence ends where the next one starts)
    for i in range(N - 1, -1, -1):
        if i == N - 1 or start[i + 1]:
            xs[i], ps[i] = xf_out[i], pf_out[i]
        else:
            Cg = pf_out[i] / pp_out[i + 1]
            xs[i] = xf_out[i] + Cg * (xs[i + 1] - xp_out[i + 1])
            ps[i] = pf_out[i] + Cg * Cg * (ps[i + 1] - pp_out[i + 1])
    return nll


def rw_smooth(tc: np.ndarray, y: np.ndarray, d: np.ndarray, start: np.ndarray, par: dict, clip: float) -> tuple[np.ndarray, float]:
    N = len(y)
    xs, ps, a, b, c_, d_ = (np.empty(N) for _ in range(6))
    nll = _rw_filter(tc.astype(np.float64), y.astype(np.float64), d.astype(np.float64), start.astype(np.bool_), par["qb"], par["sr"] ** 2,
                     par["sw"] ** 2, clip, xs, ps, a, b, c_, d_)
    return xs, nll


def fit_bias_smoother(Wt: pd.DataFrame, clip: float) -> dict:
    """ML fit of (q_b, sigma_r, sigma_w) per head axis on the tuning windows (animals and periods pooled; one sequence per
    animal-period). Units: deg/s, s."""
    Wt = Wt.sort_values(["animal", "period", "t_c_s"]).reset_index(drop=True)
    start = np.r_[True, (Wt["animal"].to_numpy()[1:] != Wt["animal"].to_numpy()[:-1]) | (Wt["period"].to_numpy()[1:] != Wt["period"].to_numpy()[:-1])]
    tc, d = Wt["t_c_s"].to_numpy(float), Wt["dur_s"].to_numpy(float)
    out = {}
    for ax in "xyz":
        y = Wt[f"bhat_{ax}"].to_numpy(float)

        def nll(th):
            par = {"qb": math.exp(th[0]), "sr": math.exp(th[1]), "sw": math.exp(th[2])}
            return rw_smooth(tc, y, d, start, par, clip)[1]

        x0 = np.log([1.5e-6, 0.05, 0.03])
        r = minimize(nll, x0, method="Nelder-Mead", options={"maxiter": 600, "xatol": 1e-3, "fatol": 1e-3})
        out[ax] = {"qb": float(math.exp(r.x[0])), "sr": float(math.exp(r.x[1])), "sw": float(math.exp(r.x[2])), "nll": float(r.fun),
                   "n": int(len(y)), "converged": bool(r.success),
                   "qb_rate_dps_per_min_at_1min": float(math.sqrt(math.exp(r.x[0]) * 60.0) * 60.0)}
    return out


def anchor_biases(tc: np.ndarray, bhat: np.ndarray, dur: np.ndarray, rule: str, spar: dict | None, clip: float) -> np.ndarray:
    if rule == "raw" or len(tc) == 0:
        return bhat.copy()
    out = np.empty_like(bhat)
    st = np.zeros(len(tc), bool)
    st[0] = True
    for j, ax in enumerate("xyz"):
        out[:, j] = rw_smooth(tc, bhat[:, j], dur, st, spar[ax], clip)[0]
    return out


def bias_series(n: int, wc: np.ndarray, banch: np.ndarray) -> np.ndarray:
    k = np.arange(n, dtype=np.float64)
    return np.column_stack([np.interp(k, wc.astype(np.float64), banch[:, j]) for j in range(3)])


def run_attitude(w_rad: np.ndarray, valid: np.ndarray, wc: np.ndarray, gw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = len(w_rad)
    q = np.empty((n, 4))
    clos = np.full(len(wc), np.nan)
    if len(wc) == 0:
        q[:] = np.array([1.0, 0, 0, 0])
        return q, clos
    _stage_a_kernel(np.ascontiguousarray(w_rad, np.float64), np.ascontiguousarray(valid, np.bool_), np.ascontiguousarray(wc, np.int64),
                    np.ascontiguousarray(gw, np.float64), DT100, q, clos)
    return q, clos


def g_head_np(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.column_stack([2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)])


def t_since_windows(n: int, ws: np.ndarray, we: np.ndarray) -> np.ndarray:
    """Seconds since the end of the last strict window (0 inside one); before the first window: seconds to its start."""
    t = np.full(n, np.nan)
    if len(ws) == 0:
        return np.full(n, 1e9)
    inw = np.zeros(n + 1, np.int64)
    np.add.at(inw, ws, 1)
    np.add.at(inw, we, -1)
    inside = np.cumsum(inw)[:n] > 0
    k = np.arange(n)
    j = np.searchsorted(we, k, side="right") - 1                  # last window ending at or before k
    t = np.where(j >= 0, (k - we[np.maximum(j, 0)] + 1) * DT100, (ws[0] - k) * DT100)
    t[inside] = 0.0
    return np.maximum(t, 0.0)


def sigma_law(t: np.ndarray, law: dict) -> np.ndarray:
    if "sigma0_deg" in law:
        return np.sqrt(law["sigma0_deg"] ** 2 + (law["k_deg_per_s"] * t) ** 2)
    return np.sqrt(law["p0_deg"] ** 2 + (law["k90_deg_per_s"] * t) ** 2)


def lwo_eval(w100: np.ndarray, wb_a3: np.ndarray, valid: np.ndarray, Wt: pd.DataFrame, scale: float, rule: str, spar: dict | None,
             clip: float) -> pd.DataFrame:
    """Leave-window-out: odd-numbered windows withheld from the bias anchors and the closures; tilt error at their centres."""
    m = len(Wt)
    if m < 3:
        return pd.DataFrame()
    keep = np.arange(m) % 2 == 0
    s, e, c = Wt["s"].to_numpy(), Wt["e"].to_numpy(), Wt["c"].to_numpy()
    gw = Wt[["g_x", "g_y", "g_z"]].to_numpy(float)
    if rule == "a3":
        wr = scale * wb_a3 * D2R
    else:
        ba = anchor_biases(Wt["t_c_s"].to_numpy(float)[keep], Wt[["bhat_x", "bhat_y", "bhat_z"]].to_numpy(float)[keep],
                           Wt["dur_s"].to_numpy(float)[keep], rule, spar, clip)
        wr = scale * (w100 - bias_series(len(w100), c[keep], ba)) * D2R
    q, _ = run_attitude(wr, valid, c[keep], gw[keep])
    j = np.flatnonzero(~keep)
    j = j[j < m - 1]                                             # needs a kept window after it
    up = g_head_np(q[c[j]])
    err = P0.angle_deg(up, gw[j])
    t_last = (c[j] - e[j - 1]) * DT100
    t_next = (s[j + 1] - c[j]) * DT100
    return pd.DataFrame({"animal": Wt["animal"].iloc[0], "period": Wt["period"].iloc[0], "role": Wt["role"].iloc[0], "kind": Wt["kind"].iloc[0],
                         "rule": rule, "win": j, "t_c_ms": Wt["t_c_ms"].to_numpy()[j], "in_analysis": Wt["in_analysis"].to_numpy()[j],
                         "dur_s": Wt["dur_s"].to_numpy()[j], "t_since_last_kept_s": t_last, "dist_nearest_kept_s": np.minimum(t_last, t_next),
                         "gap_kept_s": t_last + t_next, "err_deg": err})


# ====================================================================================================== Stage A per period
def extended_gcfg(gcfg: dict, pk: str, imu100_root: Path, animal: str) -> tuple[dict, float, float]:
    """Gate-v2 config copy whose period window is the whole cached window (so Stage A covers the +1 h control)."""
    g = copy.deepcopy(gcfg)
    with np.load(imu100_root / animal / f"{pk}.npz", allow_pickle=True) as z:
        t = z["t_unix_ms"]
        t0, t1 = float(t[0]), float(t[-1])
    g["periods"][pk]["start"] = ms_local(t0 + 1000.0, g["tz"])
    g["periods"][pk]["end"] = ms_local(t1 - 1000.0, g["tz"])
    return g, t0, t1


def shake_mask(R: pd.DataFrame, n: int, p0cfg: dict) -> np.ndarray:
    """Phase-0 shake-train spans (+- suspect window) on the 100-Hz grid (as P0.gyro_chain)."""
    out = np.zeros(n, bool)
    if R is None or len(R) == 0 or "cls" not in R:
        return out
    win = int(round(p0cfg["saturation"]["suspect_window_ms"] / 1000 * 1250.0))
    for _, grp in R[R["cls"] == "shake_train"].groupby("train_id"):
        a, b = int(grp["i0"].min()) - win, int(grp["i1"].max()) + win
        out[max(0, int(a / 12.5)):min(n, int(math.ceil(b / 12.5)) + 1)] = True
    return out


def any_in_support(flag100: np.ndarray, centers: np.ndarray, half: float) -> np.ndarray:
    return P0.any_in_support(flag100, centers, half)


def day_seconds_table(t100, acc, gyr_a3, f_up, valid_imu, sat100, frozen100, an_lo, an_hi, lite: dict, animal: str, cfg: dict) -> pd.DataFrame:
    """Cache-equivalent per-second IMU table for a day period (plan section 1): the pilot's columns and rules from the
    A3-equivalent day cache and Stage A's vertical world-frame acceleration."""
    ds = cfg["stage_a"]["day_seconds"]
    s_lo, s_hi = int(an_lo // 1000), int(-(-an_hi // 1000))
    secs = np.arange(s_lo, s_hi, dtype=np.int64)
    n = len(secs)
    vwin = int(cfg["stage_a"]["vedba_window_samples"])
    vedba = np.linalg.norm(acc - uniform_filter1d(acc, vwin, axis=0, mode="nearest"), axis=1)
    om = np.linalg.norm(gyr_a3, axis=1)
    idx = np.floor(t100 / 1000).astype(np.int64) - s_lo
    inb = (idx >= 0) & (idx < n)
    good = inb & valid_imu

    def S(v, m):
        return np.bincount(idx[m], weights=np.asarray(v, float)[m], minlength=n)

    cnt = np.bincount(idx[good], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        vedba_1s = S(vedba, good) / cnt
        omega_1s = S(om, good) / cnt
    t_mid = (secs + 0.5) * 1000.0
    tag = C.resolve_tag(lite["ids"], animal, an_lo, an_hi)
    vf, vu = C.tag_window(lite["ids"], tag, animal, (an_lo + an_hi) / 2)
    adc_a = [wd for wd in lite["adc"] if wd[2] == animal]
    df = pd.DataFrame({"sec": secs, "n": cnt, "vedba_1s": vedba_1s, "omega_1s": omega_1s,
                       "m_nodata": cnt < int(ds["min_samples_per_s"]),
                       "m_saturated": S(sat100, inb) > 0, "m_frozen_flag": S(frozen100, inb) > 0,
                       "m_handling": C.in_any(t_mid, lite["handling"]), "m_silence": C.in_any(t_mid, lite["silences"]),
                       "m_tag_validity": (t_mid < vf) | (t_mid >= vu), "m_adc": C.in_any(t_mid, adc_a)})
    df["ok"] = ~df[["m_nodata", "m_saturated", "m_frozen_flag", "m_handling", "m_silence", "m_tag_validity", "m_adc"]].any(axis=1)
    df["still"] = (df["ok"] & (df["vedba_1s"] < lite["thr"][animal]) & (df["omega_1s"] < float(ds["omega_still_dps"]))).to_numpy(bool)
    m50 = (len(t100) // 2) * 2
    u50 = t100[:m50].reshape(-1, 2).mean(axis=1)
    up50 = f_up[:m50].reshape(-1, 2).mean(axis=1)
    df["sbf"] = P.stride_band_fraction(u50, up50, secs.astype(float))
    return df


def circular_shift_table(ps: pd.DataFrame, shift_s: int = 3600) -> pd.DataFrame:
    """Per-second table of the circularly shifted IMU: row for true second s carries the values of second
    lo + ((s - lo + shift) mod L), and its 'sec' is s + shift (the Track's +1 h convention)."""
    L = len(ps)
    src = (np.arange(L) + shift_s) % L
    out = ps.iloc[src].reset_index(drop=True).copy()
    out["sec"] = ps["sec"].to_numpy() + shift_s
    return out


def stage_a_job(job: dict) -> dict:
    """One animal-period. mode 'windows': strict windows + ZARU only; 'lwo': + leave-window-out for every bias rule;
    'full': + the attitude with the chosen rule, 16-Hz products, validation A1, day per-second table, cache file."""
    try:
        t0 = time.time()
        a, pk, mode = job["animal"], job["period"], job["mode"]
        cfg, p0cfg = job["cfg"], job["p0cfg"]
        sa = cfg["stage_a"]
        clip = float(sa["smoother_nu_clip"])
        per = cfg["periods"][pk]
        gcfg, c0, c1 = extended_gcfg(job["gcfg"], pk, Path(cfg["cache_roots"]["imu100"]), a)
        ctxg = GV2.context(gcfg)
        Pp = GV2.process_period(a, pk, gcfg, p0cfg, ctxg)
        t100 = Pp["t100"]
        n = len(t100)
        acc = Pp["acc"].astype(np.float64)
        wb_a3rec = Pp["wb"].astype(np.float64)                     # reconstructed gyro - A3 running-median bias
        b_a3 = (Pp["w_pre"] - Pp["wb_a3"]).astype(np.float64)
        w100 = wb_a3rec + b_a3                                     # reconstructed gyro, pre-bias (deg/s, head frame)
        valid = Pp["valid"].astype(bool)
        an_lo, an_hi = period_bounds(cfg, pk)
        W = Pp["W"].reset_index(drop=True)
        s, e, c = W["s"].to_numpy(np.int64), W["e"].to_numpy(np.int64), W["c"].to_numpy(np.int64)
        cs = np.vstack([np.zeros((1, 3)), np.cumsum(w100, axis=0)])
        bhat = (cs[e] - cs[s]) / np.maximum(e - s, 1)[:, None]
        csa = np.vstack([np.zeros((1, 3)), np.cumsum(b_a3, axis=0)])
        ba3w = (csa[e] - csa[s]) / np.maximum(e - s, 1)[:, None]
        Wt = pd.DataFrame({"animal": a, "period": pk, "role": per["role"], "kind": per["kind"], "s": s, "e": e, "c": c,
                           "dur_s": (e - s) / FS100, "t_c_ms": t100[c] if len(c) else np.zeros(0),
                           "t_c_s": (t100[c] - t100[0]) / 1000.0 if len(c) else np.zeros(0),
                           "in_analysis": ((t100[c] >= an_lo) & (t100[c] < an_hi)) if len(c) else np.zeros(0, bool),
                           "wiser": W["wiser"].to_numpy(), "g_x": W["g_x"].to_numpy(), "g_y": W["g_y"].to_numpy(), "g_z": W["g_z"].to_numpy(),
                           "bhat_x": bhat[:, 0], "bhat_y": bhat[:, 1], "bhat_z": bhat[:, 2],
                           "ba3_x": ba3w[:, 0], "ba3_y": ba3w[:, 1], "ba3_z": ba3w[:, 2]})
        res = {"animal": a, "period": pk, "W": Wt, "n100": n, "valid_frac": float(valid.mean()), "cache_t0": c0, "cache_t1": c1}
        if mode == "windows":
            res["elapsed_s"] = time.time() - t0
            return res
        scale = float(job["scale"])
        spar = job["smoother"]
        lw = [lwo_eval(w100, wb_a3rec, valid, Wt, scale, r, spar, clip) for r in ("raw", "smoothed", "a3")]
        res["lwo"] = pd.concat([x for x in lw if len(x)], ignore_index=True) if any(len(x) for x in lw) else pd.DataFrame()
        if mode == "lwo":
            res["elapsed_s"] = time.time() - t0
            return res
        # ---------------- full: attitude with the chosen rule
        rule = job["bias_rule"]
        tc, dur, gw = Wt["t_c_s"].to_numpy(float), Wt["dur_s"].to_numpy(float), Wt[["g_x", "g_y", "g_z"]].to_numpy(float)
        anch = {r: anchor_biases(tc, bhat, dur, r, spar, clip) for r in ("raw", "smoothed")}
        for r in ("raw", "smoothed"):
            for j, ax in enumerate("xyz"):
                Wt[f"b{r}_{ax}"] = anch[r][:, j]
        bser = bias_series(n, c, anch[rule]) if len(c) else b_a3
        w_rad = scale * (w100 - bser) * D2R
        q, clos = run_attitude(w_rad, valid, c, gw)
        Wt["closure_deg"] = clos * R2D
        Wt["T_in_prev_s"] = np.r_[np.nan, (s[1:] - e[:-1]) / FS100] if len(s) else np.zeros(0)
        tsw = t_since_windows(n, s, e)
        f_w = P0.rotate_world(q, acc)
        f_w[:, 2] -= G
        f_w[~valid] = 0.0
        # 16-Hz grid (resample_poly(4, 25): output j <-> input 6.25 j), as the A4 cache
        n16 = int(math.ceil(n * 4 / 25))
        centers = 6.25 * np.arange(n16)
        near = np.clip(np.round(centers).astype(int), 0, n - 1)
        half = 3.125
        sos = signal.butter(int(sa["butter_order"]), float(sa["lp_hz"]), fs=FS100, output="sos")
        lp = signal.sosfiltfilt(sos, f_w, axis=0)
        d16 = signal.resample_poly(lp, 4, 25, axis=0)[:n16]
        pad = int(round(float(sa["ok_pad_s"]) * FS100))
        bad = ~valid
        if pad > 0 and bad.any():
            bad = uniform_filter1d(bad.astype(float), 2 * pad + 1, mode="nearest") > 1e-9
        inwin = np.zeros(n, bool)
        for a_, b_ in zip(s, e):
            inwin[a_:b_] = True
        shake100 = shake_mask(Pp["sat_runs"], n, p0cfg)
        arrays = {"t_unix_ms": np.interp(centers, np.arange(n), t100), "f_xy_2hz": d16[:, :2].astype(np.float32),
                  "f_z_2hz": d16[:, 2].astype(np.float32), "q_wh": q[near].astype(np.float32),
                  "t_since_win_s": tsw[near].astype(np.float32),
                  "sigma_theta_deg": sigma_law(tsw[near], sa["sigma_law"]).astype(np.float32),
                  "p90_theta_deg": sigma_law(tsw[near], sa["p90_law"]).astype(np.float32),
                  "ok": ~any_in_support(bad, centers, half), "in_window": any_in_support(inwin, centers, half),
                  "sat": any_in_support(Pp["satcnt"] > 0, centers, half), "shake": any_in_support(shake100, centers, half)}
        wn = np.linalg.norm(w_rad, axis=1) * R2D
        an = np.linalg.norm(acc, axis=1)
        bwin = int(round(float(sa["band_power_window_s"]) * FS100))
        for lo_, hi_ in sa["band_powers_hz"]:
            sosb = signal.butter(4, [float(lo_), float(hi_)], btype="bandpass", fs=FS100, output="sos")
            for nm, x in (("w", wn), ("a", an)):
                bp = signal.sosfiltfilt(sosb, x)
                arrays[f"bp_{nm}_{int(lo_)}_{int(hi_)}"] = uniform_filter1d(bp * bp, bwin, mode="nearest")[near].astype(np.float32)
        vwin = int(sa["vedba_window_samples"])
        vedba = np.linalg.norm(acc - uniform_filter1d(acc, vwin, axis=0, mode="nearest"), axis=1)
        arrays["vedba"] = uniform_filter1d(vedba, 7, mode="nearest")[near].astype(np.float32)
        qi = np.flatnonzero(inwin)[::50]
        tilt_check = float(np.median(P0.angle_deg(g_head_np(q[qi]), acc[qi]))) if len(qi) else np.nan
        # ---------------- validation A1 (gate-v2 bout test)
        Pp["wb_anch"] = (w100 - bser).astype(np.float32)
        other = "raw" if rule == "smoothed" else "smoothed"
        Pp["wb_other"] = (w100 - (bias_series(n, c, anch[other]) if len(c) else b_a3)).astype(np.float32)
        brow = []
        for variant in ("L1.0", "L1.0_nf"):
            bt, arr = GV2.make_bouts(Pp, variant, gcfg)
            if len(bt) == 0:
                continue
            Mx = scale * np.eye(3)
            bt = bt.copy()
            bt["e_a3"] = P0.bout_errors(GV2.boutset(Pp, arr, "cc", "wb"), Mx, 0.0, p0cfg)[0]
            bt["e_anch"] = P0.bout_errors(GV2.boutset(Pp, arr, "cc", "wb_anch"), Mx, 0.0, p0cfg)[0]
            bt["e_other"] = P0.bout_errors(GV2.boutset(Pp, arr, "cc", "wb_other"), Mx, 0.0, p0cfg)[0]
            bt["in_analysis"] = (bt["t0_ms"] >= an_lo) & (bt["t1_ms"] < an_hi)
            bt["role"], bt["kind"] = per["role"], per["kind"]
            brow.append(bt.drop(columns=[x for x in ("wiser0", "wiser1") if x in bt]))
        res["bouts"] = pd.concat(brow, ignore_index=True) if brow else pd.DataFrame()
        res["rule"], res["other_rule"] = rule, other
        # ---------------- day per-second table (cache-equivalent) + write the cache
        out_root = Path(cfg["cache_roots"]["attitude16"]) / a
        out_root.mkdir(parents=True, exist_ok=True)
        if per["kind"] == "day":
            with np.load(Pp["a3_path"], allow_pickle=True) as z3:
                sat100 = z3["sat_acc"].astype(bool) | z3["sat_gyr"].astype(bool)
                frozen100 = z3["frozen"].astype(bool)
                gyr_a3 = z3["gyr"].astype(np.float64)
            ps = day_seconds_table(t100, acc, gyr_a3, f_w[:, 2], ~frozen100, sat100, frozen100, an_lo, an_hi, job["lite"], a, cfg)
            ps.to_csv(out_root / f"{pk}_imu_seconds.csv.gz", index=False)
            res["day_seconds_path"] = str(out_root / f"{pk}_imu_seconds.csv.gz")
        calib = {"gyro_scale": scale, "gyro_scale_source": cfg["gate_v2_selection"], "bias_rule": rule, "bias_smoother": spar,
                 "sigma_law": sa["sigma_law"], "p90_law": sa["p90_law"], "lp_hz": sa["lp_hz"], "butter_order": sa["butter_order"],
                 "strict_windows": gcfg["strict"], "wiser_veto": "none (Stage A is IMU-only)", "acc_calibration": "A3 / A3-equivalent ellipsoid",
                 "gyro_chain": "Phase-0: Hampel -> held-reading reconstruction of clipped runs -> 40-Hz Butterworth-4 zero-phase -> 100 Hz -> head frame",
                 "quat_convention": "[w, x, y, z], v_world = R(q) v_head; yaw arbitrary (0 at the first strict window), continuous"}
        meta = {"animal": a, "period": pk, "role": per["role"], "kind": per["kind"], "source_a1": str(Pp["a1_path"]), "source_a3": str(Pp["a3_path"]),
                "cache_window_local": [ms_local(c0), ms_local(c1)], "analysis_window_local": [per["start"], per["end"]],
                "n_strict_windows": int(len(Wt)), "still_min": float(Wt["dur_s"].sum() / 60.0), "quiet_tilt_check_median_deg": tilt_check,
                "t_clock": "field-PC Unix ms on the IMU clock (tau* NOT applied); 16-Hz grid j <-> 100-Hz sample 6.25 j",
                "units": {"f_xy": "m/s^2 world frame (yaw arbitrary), gravity removed", "bp_w": "(deg/s)^2", "bp_a": "(m/s^2)^2", "vedba": "m/s^2"},
                "git_commit": job["git"], "run_dir": job["run_dir"], "written_local": pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds"),
                "writer": "wiser/scripts/analyze_wiser_ins_fusion_v5.py (Stage A)", "config_hash": job["cfg_hash"]}
        pth = out_root / f"{pk}.npz"
        tmp = out_root / f"{pk}.partial.npz"
        np.savez_compressed(tmp, calib_json=np.array(json.dumps(calib, default=_jd)), meta_json=np.array(json.dumps(meta, default=_jd)), **arrays)
        os.replace(tmp, pth)
        Wt.to_csv(out_root / f"{pk}_windows.csv.gz", index=False)
        sel_an = (arrays["t_unix_ms"] >= an_lo) & (arrays["t_unix_ms"] < an_hi)
        res.update({"cache_path": str(pth), "cache_bytes": pth.stat().st_size, "n16": n16, "tilt_check_deg": tilt_check,
                    "frac_ok16": float(arrays["ok"][sel_an].mean()), "elapsed_s": time.time() - t0,
                    "tsw_quantiles_s": np.percentile(arrays["t_since_win_s"][sel_an], [50, 75, 90, 99]).tolist()})
        res["W"] = Wt
        return res
    except Exception as ex:  # noqa: BLE001
        import traceback
        return {"animal": job.get("animal"), "period": job.get("period"), "error": f"{type(ex).__name__}: {ex}", "tb": traceback.format_exc()}


def load_attitude16(cfg: dict, a: str, pk: str) -> dict:
    p = Path(cfg["cache_roots"]["attitude16"]) / a / f"{pk}.npz"
    with np.load(p, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    d["meta"] = json.loads(str(d.pop("meta_json")))
    d["calib"] = json.loads(str(d.pop("calib_json")))
    return d


# ====================================================================================================== Stage B kernel
# state order: 0 px, 1 py, 2 vx, 3 vy, 4 bx, 5 by, 6 psi, 7 dx, 8 dy  (in, in/s, in/s^2, rad, in)
NS = 9
NPAR = 28
D2R_ = math.pi / 180.0
# parameter vector indices
I_SRES, I_TAUB, I_TMAX, I_SV, I_SVR, I_QPSI, I_SDX, I_SDY, I_TD, I_DRIFT, I_LS0, I_LK, I_CVQ = range(13)
I_M0, I_M1, I_M2, I_M3 = 13, 14, 15, 16
I_PSI0, I_PSI0V, I_P0POS, I_P0VEL, I_GATE2, I_HUBK, I_PSIREACQ, I_PSIOBSMIN, I_PSIOBSMAX, I_GIN, I_DT16 = range(17, 28)


@njit(cache=True)
def _wrap(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a <= -math.pi:
        a += 2.0 * math.pi
    return a


@njit(cache=True)
def _sub_step(x, Pm, Phi, dt, ins, fx, fy, S, phib, sbss2, qpsi, phid, sd2x, sd2y, fc, fv, nz, FP, Pn):
    """Propagate state x, covariance Pm and the accumulated transition Phi over dt (one piecewise-constant IMU interval)."""
    psi = x[6]
    if ins:
        c, s = math.cos(psi), math.sin(psi)
        rfx, rfy = c * fx - s * fy, s * fx + c * fy
        ux, uy = rfx - x[4], rfy - x[5]
        jx, jy = -rfy, rfx
    else:
        ux, uy, jx, jy = 0.0, 0.0, 0.0, 0.0
    h2 = 0.5 * dt * dt
    x[0] += x[2] * dt + h2 * ux
    x[1] += x[3] * dt + h2 * uy
    x[2] += ux * dt
    x[3] += uy * dt
    x[4] *= phib
    x[5] *= phib
    x[7] *= phid
    x[8] *= phid
    insf = 1.0 if ins else 0.0
    # sparse F rows (columns fixed in fc)
    fv[0, 0], fv[0, 1], fv[0, 2], fv[0, 3] = 1.0, dt, -h2 * insf, h2 * jx
    fv[1, 0], fv[1, 1], fv[1, 2], fv[1, 3] = 1.0, dt, -h2 * insf, h2 * jy
    fv[2, 0], fv[2, 1], fv[2, 2] = 1.0, -dt * insf, dt * jx
    fv[3, 0], fv[3, 1], fv[3, 2] = 1.0, -dt * insf, dt * jy
    fv[4, 0], fv[5, 0], fv[6, 0], fv[7, 0], fv[8, 0] = phib, phib, 1.0, phid, phid
    for i in range(NS):
        for j in range(NS):
            acc = 0.0
            for k in range(nz[i]):
                acc += fv[i, k] * Pm[fc[i, k], j]
            FP[i, j] = acc
    for i in range(NS):
        for j in range(i, NS):
            acc = 0.0
            for k in range(nz[j]):
                acc += fv[j, k] * FP[i, fc[j, k]]
            Pn[i, j] = acc
            Pn[j, i] = acc
    for i in range(NS):
        for j in range(NS):
            Pm[i, j] = Pn[i, j]
    # Phi <- F Phi
    for i in range(NS):
        for j in range(NS):
            acc = 0.0
            for k in range(nz[i]):
                acc += fv[i, k] * Phi[fc[i, k], j]
            FP[i, j] = acc
    for i in range(NS):
        for j in range(NS):
            Phi[i, j] = FP[i, j]
    # process noise
    q3, q2, q1 = S * dt * dt * dt / 3.0, S * dt * dt / 2.0, S * dt
    Pm[0, 0] += q3
    Pm[1, 1] += q3
    Pm[0, 2] += q2
    Pm[2, 0] += q2
    Pm[1, 3] += q2
    Pm[3, 1] += q2
    Pm[2, 2] += q1
    Pm[3, 3] += q1
    qb = sbss2 * (1.0 - phib * phib)
    Pm[4, 4] += qb
    Pm[5, 5] += qb
    Pm[6, 6] += qpsi * dt
    Pm[7, 7] += sd2x * (1.0 - phid * phid)
    Pm[8, 8] += sd2y * (1.0 - phid * phid)


@njit(cache=True)
def _chol_solve(A, B, L, out):
    """Solve A X = B for SPD A (NS x NS) and B (NS x NS) via Cholesky (with a tiny jitter)."""
    n = A.shape[0]
    for i in range(n):
        for j in range(i + 1):
            s = A[i, j]
            for k in range(j):
                s -= L[i, k] * L[j, k]
            if i == j:
                if s <= 1e-300:
                    s = 1e-300
                L[i, i] = math.sqrt(s)
            else:
                L[i, j] = s / L[j, j]
        for j in range(i + 1, n):
            L[i, j] = 0.0
    m = B.shape[1]
    for c in range(m):
        for i in range(n):
            s = B[i, c]
            for k in range(i):
                s -= L[i, k] * out[k, c]
            out[i, c] = s / L[i, i]
        for i in range(n - 1, -1, -1):
            s = out[i, c]
            for k in range(i + 1, n):
                s -= L[k, i] * out[k, c]
            out[i, c] = s / L[i, i]


@njit(cache=True)
def _scalar_update(x, Pm, idx, innov, r, tmp, row):
    """Scalar Kalman update of state component idx with innovation innov and variance r."""
    s = Pm[idx, idx] + r
    if s <= 0.0:
        return
    for i in range(NS):
        row[i] = Pm[idx, i]
        tmp[i] = Pm[i, idx] / s
    for i in range(NS):
        x[i] += tmp[i] * innov
    for i in range(NS):
        for j in range(NS):
            Pm[i, j] -= tmp[i] * row[j]
    for i in range(NS):
        for j in range(i + 1, NS):
            v = 0.5 * (Pm[i, j] + Pm[j, i])
            Pm[i, j] = v
            Pm[j, i] = v


@njit(cache=True)
def _v5_kernel(tn, z, r2w, vis, zf, psio, psisd, tg, f, tsw, okg, cvs, par, n_iter, want_cov,
               out_p, out_d, out_v, out_b, out_psi, out_var, out_nis, out_w, out_mode, out_ll):
    """V5 EKF + RTS over the nodes tn (fix times, s) with the 16-Hz IMU grid tg (s), f (m,2) in/s^2 world (Stage A) frame,
    tsw (m,) s since a strict window, okg (m,) usable, cvs (m,) int8 pilot state. Writes smoothed outputs per node."""
    n = tn.shape[0]
    m = tg.shape[0]
    sres, taub, tmax, sv, svr = par[I_SRES], par[I_TAUB], par[I_TMAX], par[I_SV], par[I_SVR]
    qpsi, sdx2, sdy2, Td = par[I_QPSI], par[I_SDX] ** 2, par[I_SDY] ** 2, par[I_TD]
    ls0, lk, cvq = par[I_LS0], par[I_LK], par[I_CVQ]
    gate2, hubk, g_in, dt16 = par[I_GATE2], par[I_HUBK], par[I_GIN], par[I_DT16]
    S_ins = sres * sres * dt16
    xp = np.zeros((n, NS))
    Pp = np.zeros((n, NS, NS))
    xf = np.zeros((n, NS))
    Pf = np.zeros((n, NS, NS))
    Ph = np.zeros((n, NS, NS))
    w = np.ones(n)
    x = np.zeros(NS)
    Pm = np.zeros((NS, NS))
    Phi = np.zeros((NS, NS))
    FP = np.zeros((NS, NS))
    Pn = np.zeros((NS, NS))
    fc = np.zeros((NS, 4), np.int64)
    fv = np.zeros((NS, 4))
    nz = np.zeros(NS, np.int64)
    fc[0, 0], fc[0, 1], fc[0, 2], fc[0, 3] = 0, 2, 4, 6
    fc[1, 0], fc[1, 1], fc[1, 2], fc[1, 3] = 1, 3, 5, 6
    fc[2, 0], fc[2, 1], fc[2, 2] = 2, 4, 6
    fc[3, 0], fc[3, 1], fc[3, 2] = 3, 5, 6
    fc[4, 0], fc[5, 0], fc[6, 0], fc[7, 0], fc[8, 0] = 4, 5, 6, 7, 8
    nz[0], nz[1], nz[2], nz[3] = 4, 4, 3, 3
    nz[4], nz[5], nz[6], nz[7], nz[8] = 1, 1, 1, 1, 1
    tmp = np.zeros(NS)
    row = np.zeros(NS)
    PHt = np.zeros((NS, 2))
    K = np.zeros((NS, 2))
    Lc = np.zeros((NS, NS))
    Xs = np.zeros((NS, NS))
    Bm = np.zeros((NS, NS))
    Cm = np.zeros((NS, NS))
    Ps = np.zeros((NS, NS))
    D = np.zeros((NS, NS))
    dxs = np.zeros(NS)
    xs = np.zeros(NS)
    k0 = 0
    while k0 < n and not vis[k0]:
        k0 += 1
    if k0 == n:
        for k in range(n):
            out_p[k, 0] = np.nan
            out_p[k, 1] = np.nan
        out_ll[0] = np.nan
        return
    log2pi = math.log(2.0 * math.pi)
    for it in range(n_iter + 1):
        ll = 0.0
        # ---------------- forward
        j = 0                       # grid pointer: tg[j] <= t < tg[j+1]
        for k in range(n):
            if k == 0:
                for i in range(NS):
                    x[i] = 0.0
                    for jj in range(NS):
                        Pm[i, jj] = 0.0
                        Phi[i, jj] = 1.0 if i == jj else 0.0
                x[0], x[1] = z[k0, 0], z[k0, 1]
                x[6] = par[I_PSI0]
                # initial b variance from the law at the first node
                while j + 1 < m and tg[j + 1] <= tn[0]:
                    j += 1
                ts0 = tsw[j] if m > 0 else 1e9
                sth = math.sqrt(ls0 * ls0 + (lk * ts0) ** 2)
                if sth > 90.0:
                    sth = 90.0
                sb2 = (g_in * math.sin(sth * math.pi / 180.0)) ** 2
                Pm[0, 0], Pm[1, 1] = par[I_P0POS], par[I_P0POS]
                Pm[2, 2], Pm[3, 3] = par[I_P0VEL], par[I_P0VEL]
                Pm[4, 4], Pm[5, 5] = sb2, sb2
                Pm[6, 6] = par[I_PSI0V]
                Pm[7, 7], Pm[8, 8] = sdx2, sdy2
            else:
                for i in range(NS):
                    for jj in range(NS):
                        Phi[i, jj] = 1.0 if i == jj else 0.0
                t = tn[k - 1]
                t_end = tn[k]
                while t < t_end - 1e-12:
                    while j + 1 < m and tg[j + 1] <= t:
                        j += 1
                    if m == 0 or t < tg[0] or j + 1 >= m:
                        # outside the IMU grid: CV mode, state 0
                        t_next = t_end
                        if m > 0 and t < tg[0] and tg[0] < t_end:
                            t_next = tg[0]
                        ins = False
                        fx, fy, ts_, cst = 0.0, 0.0, 1e9, 0
                    else:
                        t_next = tg[j + 1] if tg[j + 1] < t_end else t_end
                        okj = okg[j] and okg[j + 1]
                        ts_ = tsw[j] if tsw[j] > tsw[j + 1] else tsw[j + 1]
                        ins = okj and ts_ <= tmax
                        fx = 0.5 * (f[j, 0] + f[j + 1, 0])
                        fy = 0.5 * (f[j, 1] + f[j + 1, 1])
                        cst = cvs[j]
                    dt = t_next - t
                    if dt > 0.0:
                        sth = math.sqrt(ls0 * ls0 + (lk * ts_) ** 2)
                        if sth > 90.0:
                            sth = 90.0
                        sb2 = (g_in * math.sin(sth * math.pi / 180.0)) ** 2
                        S = S_ins if ins else cvq * par[I_M0 + cst]
                        phib = math.exp(-dt / taub)
                        phid = math.exp(-dt / Td)
                        qps = 2.0 * (lk * D2R_) ** 2 * (ts_ if ts_ < 1e8 else 1e8)
                        if qps < qpsi:
                            qps = qpsi
                        _sub_step(x, Pm, Phi, dt, ins, fx, fy, S, phib, sb2, qps, phid, sdx2, sdy2, fc, fv, nz, FP, Pn)
                    t = t_next
                x[6] = _wrap(x[6])
            for i in range(NS):
                xp[k, i] = x[i]
                for jj in range(NS):
                    Pp[k, i, jj] = Pm[i, jj]
                    Ph[k, i, jj] = Phi[i, jj]
            # mode at the node (for reporting)
            if m > 0 and j + 1 < m and tn[k] >= tg[0]:
                tsn = tsw[j] if tsw[j] > tsw[j + 1] else tsw[j + 1]
                out_mode[k] = 1 if (okg[j] and okg[j + 1] and tsn <= tmax) else 0
            else:
                out_mode[k] = 0
            # ---------------- WISER update
            use = vis[k] and (it == 0 or w[k] > 0.0)
            if use:
                nu0 = z[k, 0] - (x[0] + x[7])
                nu1 = z[k, 1] - (x[1] + x[8])
                for i in range(NS):
                    PHt[i, 0] = Pm[i, 0] + Pm[i, 7]
                    PHt[i, 1] = Pm[i, 1] + Pm[i, 8]
                s00 = PHt[0, 0] + PHt[7, 0]
                s01 = PHt[0, 1] + PHt[7, 1]
                s11 = PHt[1, 1] + PHt[8, 1]
                r0, r1 = r2w[k, 0], r2w[k, 1]
                a00, a11 = s00 + r0, s11 + r1
                det = a00 * a11 - s01 * s01
                d2 = (a11 * nu0 * nu0 - 2.0 * s01 * nu0 * nu1 + a00 * nu1 * nu1) / det
                if it == 0:
                    out_nis[k] = d2
                    ll += -0.5 * (d2 + math.log(det) + 2.0 * log2pi)
                    infl = d2 / gate2 if d2 > gate2 else 1.0
                    r0 *= infl
                    r1 *= infl
                else:
                    r0 /= w[k]
                    r1 /= w[k]
                a00, a11 = s00 + r0, s11 + r1
                det = a00 * a11 - s01 * s01
                i00, i01, i11 = a11 / det, -s01 / det, a00 / det
                for i in range(NS):
                    K[i, 0] = PHt[i, 0] * i00 + PHt[i, 1] * i01
                    K[i, 1] = PHt[i, 0] * i01 + PHt[i, 1] * i11
                for i in range(NS):
                    x[i] += K[i, 0] * nu0 + K[i, 1] * nu1
                for i in range(NS):
                    for jj in range(NS):
                        Pm[i, jj] -= K[i, 0] * PHt[jj, 0] + K[i, 1] * PHt[jj, 1]
                for i in range(NS):
                    for jj in range(i + 1, NS):
                        v = 0.5 * (Pm[i, jj] + Pm[jj, i])
                        Pm[i, jj] = v
                        Pm[jj, i] = v
            elif it == 0:
                out_nis[k] = np.nan
            # ---------------- soft ZUPT
            if zf[k] == 1 and sv < 1e8:
                _scalar_update(x, Pm, 2, -x[2], sv * sv, tmp, row)
                _scalar_update(x, Pm, 3, -x[3], sv * sv, tmp, row)
            elif zf[k] == 2 and svr < 1e8:
                _scalar_update(x, Pm, 2, -x[2], svr * svr, tmp, row)
                _scalar_update(x, Pm, 3, -x[3], svr * svr, tmp, row)
            # ---------------- psi (re-)acquisition
            if Pm[6, 6] > par[I_PSIREACQ] and psisd[k] == psisd[k] and psisd[k] <= par[I_PSIOBSMAX]:
                rv = psisd[k] * psisd[k]
                if rv < par[I_PSIOBSMIN]:
                    rv = par[I_PSIOBSMIN]
                _scalar_update(x, Pm, 6, _wrap(psio[k] - x[6]), rv, tmp, row)
            x[6] = _wrap(x[6])
            for i in range(NS):
                xf[k, i] = x[i]
                for jj in range(NS):
                    Pf[k, i, jj] = Pm[i, jj]
        if it == 0:
            out_ll[0] = ll
        # ---------------- RTS
        last = (it == n_iter)
        for i in range(NS):
            xs[i] = xf[n - 1, i]
            for jj in range(NS):
                Ps[i, jj] = Pf[n - 1, i, jj]
        for i in range(2):
            out_p[n - 1, i] = xs[i]
            out_v[n - 1, i] = xs[2 + i]
            out_b[n - 1, i] = xs[4 + i]
            out_d[n - 1, i] = xs[7 + i]
        out_psi[n - 1] = xs[6]
        if last and want_cov:
            out_var[n - 1, 0] = Ps[0, 0] + 2 * Ps[0, 7] + Ps[7, 7]
            out_var[n - 1, 1] = Ps[0, 1] + Ps[0, 8] + Ps[7, 1] + Ps[7, 8]
            out_var[n - 1, 2] = Ps[1, 1] + 2 * Ps[1, 8] + Ps[8, 8]
        for k in range(n - 2, -1, -1):
            # Bm = Phi_{k+1} Pf_k ;  Pp_{k+1} X = Bm  ->  X = C^T
            for i in range(NS):
                for jj in range(NS):
                    acc = 0.0
                    for l in range(NS):
                        acc += Ph[k + 1, i, l] * Pf[k, l, jj]
                    Bm[i, jj] = acc
                    D[i, jj] = Pp[k + 1, i, jj]
            _chol_solve(D, Bm, Lc, Xs)
            for i in range(NS):
                for jj in range(NS):
                    Cm[i, jj] = Xs[jj, i]
            for i in range(NS):
                dxs[i] = xs[i] - xp[k + 1, i]
            dxs[6] = _wrap(dxs[6])
            for i in range(NS):
                acc = xf[k, i]
                for jj in range(NS):
                    acc += Cm[i, jj] * dxs[jj]
                tmp[i] = acc
            for i in range(NS):
                xs[i] = tmp[i]
            xs[6] = _wrap(xs[6])
            if last and want_cov:
                # Ps_k = Pf_k + C (Ps_{k+1} - Pp_{k+1}) C^T
                for i in range(NS):
                    for jj in range(NS):
                        D[i, jj] = Ps[i, jj] - Pp[k + 1, i, jj]
                for i in range(NS):
                    for jj in range(NS):
                        acc = 0.0
                        for l in range(NS):
                            acc += Cm[i, l] * D[l, jj]
                        Bm[i, jj] = acc
                for i in range(NS):
                    for jj in range(NS):
                        acc = Pf[k, i, jj]
                        for l in range(NS):
                            acc += Bm[i, l] * Cm[jj, l]
                        Ps[i, jj] = acc
                out_var[k, 0] = Ps[0, 0] + 2 * Ps[0, 7] + Ps[7, 7]
                out_var[k, 1] = Ps[0, 1] + Ps[0, 8] + Ps[7, 1] + Ps[7, 8]
                out_var[k, 2] = Ps[1, 1] + 2 * Ps[1, 8] + Ps[8, 8]
            for i in range(2):
                out_p[k, i] = xs[i]
                out_v[k, i] = xs[2 + i]
                out_b[k, i] = xs[4 + i]
                out_d[k, i] = xs[7 + i]
            out_psi[k] = xs[6]
        # ---------------- IRLS weights from the smoothed residuals
        if it < n_iter:
            for k in range(n):
                if not vis[k]:
                    continue
                r0 = z[k, 0] - out_p[k, 0] - out_d[k, 0]
                r1 = z[k, 1] - out_p[k, 1] - out_d[k, 1]
                mm = math.sqrt(r0 * r0 / r2w[k, 0] + r1 * r1 / r2w[k, 1])
                w[k] = 1.0 if mm <= hubk else hubk / mm
    for k in range(n):
        out_w[k] = w[k]


@njit(parallel=True, cache=True)
def _v5_batch(tn, z_s, r2w, vis_s, zf_s, psio_s, psisd_s, tg, f_s, tsw_s, ok_s, cvs_s, pars, c_z, c_vis, c_zf, c_psi, c_grid,
              n_iter, want_cov, out_p, out_d, out_v, out_b, out_psi, out_var, out_nis, out_w, out_mode, out_ll):
    for i in prange(pars.shape[0]):
        g = c_grid[i]
        _v5_kernel(tn, z_s[c_z[i]], r2w, vis_s[c_vis[i]], zf_s[c_zf[i]], psio_s[c_psi[i]], psisd_s[c_psi[i]], tg, f_s[g], tsw_s[g],
                   ok_s[g], cvs_s[g], pars[i], n_iter, want_cov, out_p[i], out_d[i], out_v[i], out_b[i], out_psi[i], out_var[i],
                   out_nis[i], out_w[i], out_mode[i], out_ll[i])


def make_par(c: dict, sb: dict, law: dict, nm: dict, psi0: float, psi0_var: float) -> np.ndarray:
    """Parameter vector for one run. c = tuned scalars (sig_res, tau_b, t_max, sig_v, sig_vr, kappa_cv); sb = stage_b config;
    law = sigma law (median or p90); nm = WISER noise model (drift)."""
    p = np.zeros(NPAR)
    p[I_SRES], p[I_TAUB], p[I_TMAX] = c["sig_res"], c["tau_b"], min(fval(c["t_max"]), 1e12)
    p[I_SV], p[I_SVR] = min(fval(c["sig_v"]), 1e12), min(fval(c["sig_vr"]), 1e12)
    p[I_QPSI] = float(sb["q_psi_deg2_per_s"]) * D2R * D2R
    if nm.get("drift_on"):
        p[I_SDX], p[I_SDY], p[I_TD], p[I_DRIFT] = nm["sigma_d_x"], nm["sigma_d_y"], nm["T_d_s"], 1.0
    else:
        p[I_SDX], p[I_SDY], p[I_TD], p[I_DRIFT] = 1e-4, 1e-4, 1.0, 0.0
    if "sigma0_deg" in law:
        p[I_LS0], p[I_LK] = law["sigma0_deg"], law["k_deg_per_s"]
    else:
        p[I_LS0], p[I_LK] = law["p0_deg"], law["k90_deg_per_s"]
    p[I_CVQ] = float(sb["cv_q_in2_s3"]) * float(c.get("kappa_cv", 1.0))
    p[I_M0:I_M3 + 1] = np.asarray(sb["cv_mult"], float)
    p[I_PSI0], p[I_PSI0V] = psi0, psi0_var
    p[I_P0POS], p[I_P0VEL] = float(sb["p0_pos_in2"]), float(sb["p0_vel_in2s2"])
    p[I_GATE2], p[I_HUBK] = float(sb["gate2"]), float(sb["huber_k"])
    p[I_PSIREACQ] = (float(sb["psi_reacq_sd_deg"]) * D2R) ** 2
    p[I_PSIOBSMIN] = (float(sb["psi_obs_min_sd_deg"]) * D2R) ** 2
    p[I_PSIOBSMAX] = float(sb["psi_obs_max_sd_deg"]) * D2R
    p[I_GIN], p[I_DT16] = G_IN, DT16
    return p


def run_v5(tn, z_list, r2w, vis_list, zf_list, psio_list, psisd_list, tg, grids, pars, c_z, c_vis, c_zf, c_psi, c_grid,
           n_iter: int, want_cov: bool) -> dict:
    """Batch of V5 runs on one animal-period (prange over runs). grids = list of dicts with f, tsw, ok, cvs."""
    n = len(tn)
    R = len(pars)
    f_s = np.ascontiguousarray(np.stack([g["f"] for g in grids]), np.float64)
    tsw_s = np.ascontiguousarray(np.stack([g["tsw"] for g in grids]), np.float64)
    ok_s = np.ascontiguousarray(np.stack([g["ok"] for g in grids]), np.bool_)
    cvs_s = np.ascontiguousarray(np.stack([g["cvs"] for g in grids]), np.int64)
    out = {"p": np.full((R, n, 2), np.nan), "d": np.zeros((R, n, 2)), "v": np.zeros((R, n, 2)), "b": np.zeros((R, n, 2)),
           "psi": np.zeros((R, n)), "var": np.full((R, n, 3), np.nan), "nis": np.full((R, n), np.nan), "w": np.ones((R, n)),
           "mode": np.zeros((R, n), np.int8), "ll": np.zeros((R, 1))}
    _v5_batch(np.ascontiguousarray(tn, np.float64), np.ascontiguousarray(np.stack(z_list), np.float64), np.ascontiguousarray(r2w, np.float64),
              np.ascontiguousarray(np.stack(vis_list), np.bool_), np.ascontiguousarray(np.stack(zf_list), np.int8),
              np.ascontiguousarray(np.stack(psio_list), np.float64), np.ascontiguousarray(np.stack(psisd_list), np.float64),
              np.ascontiguousarray(tg, np.float64), f_s, tsw_s, ok_s, cvs_s, np.ascontiguousarray(pars, np.float64),
              np.asarray(c_z, np.int64), np.asarray(c_vis, np.int64), np.asarray(c_zf, np.int64), np.asarray(c_psi, np.int64),
              np.asarray(c_grid, np.int64), int(n_iter), bool(want_cov), out["p"], out["d"], out["v"], out["b"], out["psi"], out["var"],
              out["nis"], out["w"], out["mode"], out["ll"])
    out["zhat"] = out["p"] + out["d"]
    return out


# ====================================================================================================== Stage B inputs
def build_context(cfg: dict) -> dict:
    v4 = V4.context(cfg["_cohort"])
    scfg = v4["scfg"]
    ptuned = scfg["tuned"]
    gcfg, p0cfg = GV2.load_cfg(cfg["_cohort"])
    return {"v4": v4, "scfg": scfg, "ptuned": ptuned, "table": {int(k): v for k, v in ptuned["anchor_sigma"].items()},
            "loco": ptuned["loco"], "taus": scfg["tau_star_s"], "seed": int(scfg["seed"]), "gcfg": gcfg, "p0cfg": p0cfg,
            "lite": {"ids": v4["ids"], "handling": v4["handling"], "silences": v4["silences"], "adc": v4["adc"], "thr": v4["thr"]}}


def per_second_tables(ctx: dict, cfg: dict, pk: str, a: str, lo: float, hi: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    per = cfg["periods"][pk]
    if per["kind"] == "night":
        ni = V4.night_info(ctx["v4"], per["smoothing_night"])
        assert abs(ni["lo"] - lo) < 1 and abs(ni["hi"] - hi) < 1, (ni["lo"], lo)
        ps = V4.imu_seconds(ctx["v4"], ni, a, lo, hi)
        ps_s = V4.imu_seconds(ctx["v4"], ni, a, lo + 3.6e6, hi + 3.6e6)
    else:
        ps = pd.read_csv(Path(cfg["cache_roots"]["attitude16"]) / a / f"{pk}_imu_seconds.csv.gz")
        ps_s = circular_shift_table(ps)
    return ps, ps_s


def sec_lookup(secs: np.ndarray, vals: np.ndarray, q: np.ndarray, default):
    s0 = int(secs[0])
    i = q.astype(np.int64) - s0
    ok = (i >= 0) & (i < len(vals))
    out = np.full(len(q), default, dtype=np.asarray(vals).dtype)
    out[ok] = np.asarray(vals)[i[ok]]
    return out


def rhythm_flags(stA: dict, idx: np.ndarray, pmin: float) -> np.ndarray:
    bhi = stA["bp_w_8_12"][idx].astype(np.float64) + stA["bp_w_12_20"][idx]
    blo = stA["bp_w_2_4"][idx].astype(np.float64) + stA["bp_w_4_8"][idx]
    return stA["ok"][idx] & (stA["shake"][idx] | ((bhi >= blo) & (bhi + blo >= pmin)))


def make_grids(stA: dict, lo: float, hi: float, kind: str, tr, cfg: dict) -> tuple[np.ndarray, dict]:
    """The 16-Hz IMU grid on the true clock (s from the period start) and the inputs for the true and the +1 h-shifted IMU
    (nights: from the cached window; days: circular within the analysis window). p90 shares the true grid."""
    sb = cfg["stage_b"]
    t16 = stA["t_unix_ms"]
    marg = float(sb["grid_margin_s"]) * 1000.0
    idx = np.flatnonzero((t16 >= lo - marg) & (t16 < hi + marg))
    tq = t16[idx]
    tg = (tq - lo) / 1000.0
    pmin = float(sb["rhythm_pmin_dps2"])
    out = {}
    for which in ("true", "shift"):
        if which == "true":
            src, found = idx, np.ones(len(idx), bool)
        else:
            if kind == "night":
                tsrc = tq + 3.6e6
                found = np.ones(len(idx), bool)
            else:
                inside = (tq >= lo) & (tq < hi)
                tsrc = np.where(inside, lo + np.mod(tq - lo + 3.6e6, hi - lo), tq)
                found = inside.copy()
            j = np.clip(np.searchsorted(t16, tsrc), 1, len(t16) - 1)
            jj = np.where(np.abs(t16[j - 1] - tsrc) < np.abs(t16[j] - tsrc), j - 1, j)
            found &= np.abs(t16[jj] - tsrc) < 40.0
            src = jj
        secs_q = np.floor(tq / 1000.0)
        if which == "true":
            cvs = sec_lookup(tr.ps["sec"].to_numpy(), tr.st_sec, secs_q, 0)
        else:
            cvs = sec_lookup(tr.ps_shift["sec"].to_numpy(), tr.st_sec_shift, secs_q + 3600, 0)
        ok = stA["ok"][src] & found
        out[which] = {"f": stA["f_xy_2hz"][src].astype(np.float64) * IN_PER_M, "tsw": stA["t_since_win_s"][src].astype(np.float64),
                      "ok": ok, "cvs": cvs.astype(np.int64), "rhythm": rhythm_flags(stA, src, pmin) & ok}
    return tg, out


def node_flags(tr, tg: np.ndarray, grid: dict, which: str) -> np.ndarray:
    """0 none, 1 IMU-still second (pilot rule), 2 rhythmic body-stationary sample (not still, pilot state != locomoting)."""
    j = np.clip(np.searchsorted(tg, tr.t), 1, max(len(tg) - 1, 1))
    jj = np.where(np.abs(tg[j - 1] - tr.t) < np.abs(tg[j] - tr.t), j - 1, j) if len(tg) > 1 else np.zeros(tr.n, int)
    near = np.abs(tg[jj] - tr.t) < 0.04 if len(tg) else np.zeros(tr.n, bool)
    rh = grid["rhythm"][jj] & near
    if which == "true":
        still, st = tr.still, tr.st_at
    else:
        ps = tr.ps_shift
        secs = ps["sec"].to_numpy()
        still = sec_lookup(secs, (ps["still"].to_numpy(bool) & ps["ok"].to_numpy(bool)), tr.sec + 3600, False)
        st = tr.st_at_shift
    return np.where(still, 1, np.where(rh & (st != 3), 2, 0)).astype(np.int8)


def psi_regression(tr, z_use: np.ndarray, vis: np.ndarray, tg: np.ndarray, grid: dict, r2_pilot: np.ndarray, pc: dict) -> dict:
    """Yaw offset from the visible fixes: complex regression of WISER (B2) velocity changes on IMU velocity changes over
    0.4-0.75 s pairs (plan 3.4, amendment 2: only pairs whose IMU span is usable and within `max_tsw_s` of a strict
    window; standard error of the mean direction 1 / (Rbar sqrt(2 n_eff)), n_eff = (sum|c|)^2 / sum|c|^2)."""
    n = tr.n
    res = {"psio": np.full(n, np.nan), "psisd": np.full(n, np.nan), "psi0": 0.0, "psi0_var": math.pi ** 2, "Rbar": np.nan,
           "n_pairs": 0, "n_eff": 0.0, "psi_whole": np.nan, "psi_whole_se_deg": np.nan, "frac_nodes_with_est": 0.0}
    if len(tg) < 2 or vis.sum() < 10:
        return res
    _, _, V = P.kf_run(tr.t, z_use, r2_pilot, [vis], [tr.st_mid], [tr.st_at], [{"q": float(pc["b2_q"]), "mrej": 1e9}])
    V = V[0]
    f = grid["f"]
    dtg = np.diff(tg)
    Fc = np.vstack([np.zeros((1, 2)), np.cumsum(0.5 * (f[1:] + f[:-1]) * dtg[:, None], axis=0)])
    usable = grid["ok"] & (grid["tsw"] <= float(pc["max_tsw_s"]))
    Bc = np.r_[0, np.cumsum(~usable)]
    iv = np.flatnonzero(vis)
    tv = tr.t[iv]
    lag0, lag1 = pc["lag_s"]
    jl = np.searchsorted(tv, tv + lag0)
    okp = jl < len(tv)
    jl = np.minimum(jl, len(tv) - 1)
    okp &= tv[jl] <= tv + lag1
    okp &= (tv >= tg[0]) & (tv[jl] <= tg[-1])
    i0, i1 = np.flatnonzero(okp), jl[okp]
    ta, tb = tv[i0], tv[i1]
    Fa = np.column_stack([np.interp(ta, tg, Fc[:, k]) for k in range(2)])
    Fb = np.column_stack([np.interp(tb, tg, Fc[:, k]) for k in range(2)])
    dI = (Fb[:, 0] - Fa[:, 0]) + 1j * (Fb[:, 1] - Fa[:, 1])
    dW = (V[iv[i1], 0] - V[iv[i0], 0]) + 1j * (V[iv[i1], 1] - V[iv[i0], 1])
    nbad = Bc[np.minimum(np.searchsorted(tg, tb, side="right"), len(tg))] - Bc[np.searchsorted(tg, ta, side="left")]
    keep = (np.abs(dI) >= float(pc["min_dv_inps"])) & (nbad == 0) & np.isfinite(dW)
    c = dW[keep] * np.conj(dI[keep])
    tp = 0.5 * (ta[keep] + tb[keep])
    res["n_pairs"] = int(len(c))
    if len(c) < int(pc["min_pairs"]):
        return res
    o = np.argsort(tp)
    tp, c = tp[o], c[o]
    sd_lo, sd_hi = (np.asarray(pc["sd_bounds_deg"], float) * D2R)

    def se(S, A, A2):
        with np.errstate(invalid="ignore", divide="ignore"):
            Rb = np.abs(S) / A
            neff = A * A / A2
            return Rb, neff, 1.0 / (Rb * np.sqrt(2.0 * neff))

    Rw, nw, sew = se(c.sum(), np.abs(c).sum(), (np.abs(c) ** 2).sum())
    res["Rbar"], res["n_eff"], res["psi_whole"] = float(Rw), float(nw), float(np.angle(c.sum()))
    res["psi_whole_se_deg"] = float(sew * R2D)
    cs = np.r_[0, np.cumsum(c)]
    ca = np.r_[0, np.cumsum(np.abs(c))]
    ca2 = np.r_[0, np.cumsum(np.abs(c) ** 2)]
    tgrid = np.arange(tr.t[0], tr.t[-1] + pc["grid_step_s"], pc["grid_step_s"])
    h = float(pc["half_window_s"])
    a_ = np.searchsorted(tp, tgrid - h)
    b_ = np.searchsorted(tp, tgrid + h)
    cnt = b_ - a_
    S = cs[b_] - cs[a_]
    _, _, sd = se(S, ca[b_] - ca[a_], ca2[b_] - ca2[a_])
    est = np.angle(S)
    good = (cnt >= int(pc["min_pairs"])) & np.isfinite(sd) & (sd <= sd_hi)
    sd = np.clip(np.nan_to_num(sd, nan=sd_hi), sd_lo, sd_hi)
    gi = np.clip(np.round((tr.t - tgrid[0]) / pc["grid_step_s"]).astype(int), 0, len(tgrid) - 1)
    res["psio"] = np.where(good[gi], est[gi], np.nan)
    res["psisd"] = np.where(good[gi], sd[gi], np.nan)
    res["frac_nodes_with_est"] = float(np.mean(good[gi]))
    if good[gi[0]]:
        res["psi0"], s0 = float(est[gi[0]]), float(sd[gi[0]])
    elif np.isfinite(sew) and sew <= sd_hi:
        res["psi0"], s0 = res["psi_whole"], float(max(sew, sd_lo))
    else:
        res["psi0"], s0 = 0.0, math.pi
    res["psi0_var"] = max(s0, float(pc.get("psi0_min_sd_deg", 10.0)) * D2R) ** 2
    return res


# ====================================================================================================== WISER noise model
def still_runs_fixes(tr, ps: pd.DataFrame, min_run_s: int) -> np.ndarray:
    """Run id per fix (-1 = not in a still run): maximal runs of consecutive pilot-still seconds >= min_run_s."""
    sec = ps["sec"].to_numpy()
    st = (ps["ok"].to_numpy(bool) & ps["still"].to_numpy(bool))
    runs = P0.true_runs(st)
    runs = runs[(runs[:, 1] - runs[:, 0]) >= min_run_s]
    rid = np.full(len(sec), -1, np.int64)
    for i, (a_, b_) in enumerate(runs):
        rid[a_:b_] = i
    return sec_lookup(sec, rid, tr.sec, -1)


def measure_noise(items: list, nc: dict, seed: int) -> dict:
    """Measured WISER noise model (plan 3.3) from still runs of tuning tracks: per-anchor nugget from consecutive-fix
    differences, 9-anchor variogram fitted with nugget + exponential drift (common T_d), keep rule."""
    rng = np.random.default_rng(seed)
    pairs, vg = [], []
    base = 0
    for k, (tr, ps) in enumerate(items):
        rid = still_runs_fixes(tr, ps, int(nc["min_run_s"]))
        m = rid >= 0
        t, z, A = tr.t[m], tr.z[m], np.clip(tr.A[m], 3, 9).astype(int)
        r = rid[m] + base
        base = int(r.max()) + 1 if len(r) else base
        same = (r[1:] == r[:-1]) & ((t[1:] - t[:-1]) <= float(nc["max_pair_dt_s"])) & (A[1:] == A[:-1])
        pairs.append(pd.DataFrame({"A": A[1:][same], "dx": (z[1:, 0] - z[:-1, 0])[same], "dy": (z[1:, 1] - z[:-1, 1])[same],
                                   "dt": (t[1:] - t[:-1])[same]}))
        m9 = A == 9
        vg.append(pd.DataFrame({"run": r[m9], "t": t[m9], "x": z[m9, 0], "y": z[m9, 1]}))
    pr = pd.concat(pairs, ignore_index=True)
    V = pd.concat(vg, ignore_index=True).sort_values(["run", "t"]).reset_index(drop=True)
    rsd = lambda v: 1.4826 * np.median(np.abs(v - np.median(v)))  # noqa: E731
    nug = {}
    for A in range(3, 10):
        d = pr[pr.A == A]
        nug[A] = {"n_pairs": int(len(d)), "x": 0.5 * rsd(d["dx"].to_numpy()) ** 2 if len(d) >= int(nc["min_pairs"]) else np.nan,
                  "y": 0.5 * rsd(d["dy"].to_numpy()) ** 2 if len(d) >= int(nc["min_pairs"]) else np.nan}
    for A in range(9, 2, -1):
        for ax in "xy":
            if not np.isfinite(nug[A][ax]):
                lower = [nug[j][ax] for j in range(A - 1, 2, -1) if np.isfinite(nug[j][ax])]
                nug[A][ax] = lower[0] if lower else max(nug[j][ax] for j in range(3, 10) if np.isfinite(nug[j][ax]))
                nug[A][f"{ax}_filled"] = True
    # variogram of 9-anchor fixes
    key = V["run"].to_numpy(float) * 1e6 + V["t"].to_numpy(float)
    X, Y = V["x"].to_numpy(), V["y"].to_numpy()
    tol = float(nc["lag_tol"])
    rows = []
    for lag in nc["lags_s"]:
        lo_i = np.searchsorted(key, key + lag * (1 - tol))
        hi_i = np.searchsorted(key, key + lag * (1 + tol))
        cnt = hi_i - lo_i
        tot = int(cnt.sum())
        if tot == 0:
            continue
        cap = int(nc["max_pairs_per_lag"])
        sel = np.flatnonzero(cnt > 0)
        if tot > cap:
            sel = sel[rng.random(len(sel)) < cap / tot]
        ii = np.repeat(sel, cnt[sel])
        offs = np.concatenate([np.arange(c_) for c_ in cnt[sel]]) if len(sel) else np.zeros(0, int)
        jj = lo_i[sel].repeat(cnt[sel]) + offs
        gx = 0.5 * rsd(X[jj] - X[ii]) ** 2
        gy = 0.5 * rsd(Y[jj] - Y[ii]) ** 2
        rows.append({"lag_s": lag, "n_pairs": int(len(ii)), "gamma_x": gx, "gamma_y": gy})
    vgm = pd.DataFrame(rows)
    lags, wts = vgm["lag_s"].to_numpy(), np.sqrt(vgm["n_pairs"].to_numpy(float))

    def resid(th):
        nx, sx, ny, sy, lT = th
        T = math.exp(lT)
        mx = nx + sx * (1 - np.exp(-lags / T))
        my = ny + sy * (1 - np.exp(-lags / T))
        return np.r_[wts * (mx - vgm["gamma_x"]) / vgm["gamma_x"], wts * (my - vgm["gamma_y"]) / vgm["gamma_y"]]

    g0x, g0y = float(vgm["gamma_x"].iloc[0]), float(vgm["gamma_y"].iloc[0])
    fit = least_squares(resid, x0=[0.8 * g0x, 0.3 * g0x, 0.8 * g0y, 0.3 * g0y, math.log(10.0)],
                        bounds=([0, 0, 0, 0, math.log(0.05)], [np.inf, np.inf, np.inf, np.inf, math.log(1000.0)]))
    nx, sx, ny, sy, lT = fit.x
    T = math.exp(lT)
    share_x, share_y = sx / (nx + sx), sy / (ny + sy)
    keep = (max(share_x, share_y) >= float(nc["keep_min_share"])) and (nc["keep_T_range_s"][0] <= T <= nc["keep_T_range_s"][1])
    dtm = float(pr["dt"].median()) if len(pr) else 0.27
    white = {}
    for A in range(3, 10):
        row = {}
        for ax, s_ in (("x", sx), ("y", sy)):
            v = nug[A][ax]
            if keep:
                w_ = v - s_ * (1 - math.exp(-dtm / T))
                row[ax] = max(w_, float(nc["white_floor_frac"]) * v)
            else:
                row[ax] = v
        white[A] = row
    if not keep:
        # no drift state: total robust variance about the run median per anchors
        tot = []
        for k, (tr, ps) in enumerate(items):
            rid = still_runs_fixes(tr, ps, int(nc["min_run_s"]))
            m = rid >= 0
            df = pd.DataFrame({"r": rid[m], "A": np.clip(tr.A[m], 3, 9).astype(int), "x": tr.z[m, 0], "y": tr.z[m, 1]})
            df["dx"] = df["x"] - df.groupby("r")["x"].transform("median")
            df["dy"] = df["y"] - df.groupby("r")["y"].transform("median")
            tot.append(df)
        tot = pd.concat(tot)
        for A in range(3, 10):
            d = tot[tot.A == A]
            if len(d) >= int(nc["min_pairs"]):
                white[A] = {"x": rsd(d["dx"].to_numpy()) ** 2, "y": rsd(d["dy"].to_numpy()) ** 2}
    return {"drift_on": bool(keep), "sigma_d_x": float(math.sqrt(sx)), "sigma_d_y": float(math.sqrt(sy)), "T_d_s": float(T),
            "nugget_fit_x": float(nx), "nugget_fit_y": float(ny), "share_x": float(share_x), "share_y": float(share_y),
            "pair_dt_median_s": dtm, "nugget_pairs": {str(k): v for k, v in nug.items()}, "white_var": {str(k): v for k, v in white.items()},
            "variogram": vgm.to_dict(orient="records"), "n_pairs_total": int(len(pr)), "n_fix_9": int(len(V))}


def r2_measured(A: np.ndarray, nm: dict) -> np.ndarray:
    a = np.clip(np.asarray(A, float), 3, 9).astype(int)
    wx = np.array([nm["white_var"][str(k)]["x"] for k in range(3, 10)])
    wy = np.array([nm["white_var"][str(k)]["y"] for k in range(3, 10)])
    return np.column_stack([wx[a - 3], wy[a - 3]])


# ====================================================================================================== held-out schemes
def make_schemes(tr, cfg: dict, pk: str, i: int, seed: int) -> dict:
    sc = cfg["schemes"]
    pi = int(cfg["periods"][pk]["index"])
    hp = P.make_hidden(tr, seed + int(sc["a_seed_offsets"][pk]) + i)
    h = {"a": hp["a"], "a2": hp["a2"]}
    r = int(np.random.default_rng(seed + int(sc["s_seed_offset"]) + 100 * pi + i).integers(int(sc["s_every"])))
    h["s"] = (np.arange(tr.n) % int(sc["s_every"])) == r
    for nm in ("g05", "g10"):
        h[nm] = P.hide_windows(tr.t, np.random.default_rng(seed + int(sc[f"{nm}_seed_offset"]) + 100 * pi + i),
                               win_s=float(sc["g_windows_s"][nm]), frac=float(sc["g_frac"]))
    return h


# ====================================================================================================== statistics
def boot_dist(e_m: np.ndarray, e_ref: np.ndarray, blocks: np.ndarray, strata: np.ndarray, rng: np.random.Generator,
              n_boot: int = 1000, chunk: int = 100) -> tuple[dict, np.ndarray]:
    """The smoothing pilot's paired block bootstrap (P.boot_delta, identical draws for the same rng state) that also
    returns the replicate distribution of D = 1 - med(e_m)/med(e_ref) and the one-sided p = (1 + #{D* <= 0})/(1 + B)."""
    e_m, e_ref = np.asarray(e_m, float), np.asarray(e_ref, float)
    n = len(e_m)
    if n < 20:
        return {"n": int(n), "d_med": np.nan, "lo": np.nan, "hi": np.nan, "d_rmse": np.nan, "rmse_lo": np.nan, "rmse_hi": np.nan,
                "med_m": np.nan, "med_ref": np.nan, "rmse_m": np.nan, "rmse_ref": np.nan, "p_one": np.nan}, np.full(n_boot, np.nan)
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
    return ({"n": int(n), "med_m": med_m, "med_ref": med_r, "d_med": 1.0 - med_m / med_r,
             "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
             "rmse_m": rmse_m, "rmse_ref": rmse_r, "d_rmse": 1.0 - rmse_m / rmse_r,
             "rmse_lo": float(np.percentile(dr_, 2.5)), "rmse_hi": float(np.percentile(dr_, 97.5)),
             "p_one": float((1 + np.sum(d <= 0)) / (1 + n_boot))}, d)


def verdict_v5(comp: pd.DataFrame, animals: list, acc: dict) -> dict:
    """Pre-registered acceptance (plan section 6): Holm over the primary schemes on the per-animal eligibility p-values,
    then the +1 h control and the moving-fix condition on every passing scheme."""
    alpha, gain, kmin = float(acc["alpha"]), float(acc["min_gain"]), int(acc["min_animals"])
    sch = {}
    for s in acc["primary_schemes"]:
        c = comp[(comp.scheme == s) & (comp.subset == "all")]
        pa = {}
        for a in animals:
            ps_, ok = [], True
            for ref in acc["references"]:
                r = c[(c.method == "V5") & (c.ref == ref) & (c.animal == a)]
                if not len(r) or not np.isfinite(r.d_med.iloc[0]) or r.d_med.iloc[0] < gain:
                    ok = False
                    ps_.append(1.0)
                else:
                    ps_.append(float(r.p_one.iloc[0]))
            pa[a] = max(ps_) if ok else 1.0
        sp = sorted(pa.values())
        p_s = sp[kmin - 1] if len(sp) >= kmin else 1.0
        n_elig_unadj = int(sum(v <= alpha for v in pa.values()))
        ctrl = c[(c.method == "V5_shift") & (c.ref == "B2p") & c.animal.isin(animals)]
        n_ctrl = int((ctrl.lo <= 0).sum())
        mv = {ref: comp[(comp.scheme == s) & (comp.subset == "moving") & (comp.method == "V5") & (comp.ref == ref) & (comp.animal == "pooled")]
              for ref in acc["references"]}
        d_mov = {ref: (float(v.d_med.iloc[0]) if len(v) else np.nan) for ref, v in mv.items()}
        sch[s] = {"p_animal": pa, "p_scheme": p_s, "n_animals_p_le_alpha": n_elig_unadj, "n_control_no_gain": n_ctrl,
                  "control_ok": n_ctrl >= kmin, "pooled_moving_d": d_mov,
                  "moving_ok": all(np.isfinite(v) and v >= float(acc["moving_max_loss"]) for v in d_mov.values())}
    order = sorted(sch, key=lambda s: sch[s]["p_scheme"])
    m = len(order)
    passed = {s: False for s in order}
    for r, s in enumerate(order):
        thr = alpha / (m - r)
        sch[s]["holm_threshold"] = thr
        if sch[s]["p_scheme"] <= thr:
            passed[s] = True
        else:
            for s2 in order[r + 1:]:
                sch[s2]["holm_threshold"] = alpha / (m - order.index(s2))
            break
    for s in sch:
        sch[s]["primary_pass"] = passed[s]
        sch[s]["accepted"] = passed[s] and sch[s]["control_ok"] and sch[s]["moving_ok"]
    if any(sch[s]["accepted"] for s in sch):
        v = "ACCEPTED"
    elif any(sch[s]["primary_pass"] for s in sch) or any(sch[s]["n_animals_p_le_alpha"] >= kmin - 1 for s in sch):
        v = "INCONCLUSIVE"
    else:
        v = "FAIL"
    return {"schemes": sch, "holm_order": order, "verdict": v}


# ====================================================================================================== Stage A orchestration
def cfg_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=_jd).encode()).hexdigest()[:12]


def run_stage_a(cfg: dict, ctx: dict, pkeys: list, mode: str, workers: int, extra: dict, log_, out: Path) -> list:
    jobs = [{"animal": a, "period": pk, "mode": mode, "cfg": cfg, "gcfg": ctx["gcfg"], "p0cfg": ctx["p0cfg"], "lite": ctx["lite"],
             "git": extra.get("git", ""), "run_dir": str(out), **extra} for pk in pkeys for a in cfg["_animals"]]
    for j in jobs:
        j["scale"] = extra["scales"][j["animal"]] if "scales" in extra else 1.0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(stage_a_job, jobs))
    errs = [r for r in res if "error" in r]
    for r in errs:
        log_(f"Stage A ERROR {r['animal']} {r['period']}: {r['error']}\n{r.get('tb', '')}")
    if errs:
        raise SystemExit("Stage A failed")
    log_(f"Stage A [{mode}] {len(res)} animal-periods in {time.time() - t0:.0f} s")
    return res


def stage_a_all(cfg: dict, ctx: dict, roles: list, workers: int, out: Path, log_, git: str, frozen: dict | None = None) -> dict:
    """Stage A: smoother fit + bias-rule choice on the tuning periods (passes 1-2), then the full pass for the periods of
    `roles`. Returns the decisions and the per-period results."""
    sa = cfg["stage_a"]
    scales = gyro_scales(cfg)
    tun = [pk for pk, p in cfg["periods"].items() if p["role"] == "tuning"]
    if frozen is None:
        r1 = run_stage_a(cfg, ctx, tun, "windows", workers, {"scales": scales}, log_, out)
        Wt = pd.concat([r["W"] for r in r1], ignore_index=True)
        spar = fit_bias_smoother(Wt, float(sa["smoother_nu_clip"]))
        log_("bias smoother (tuning windows, per head axis): " + "; ".join(
            f"{ax}: q_b {v['qb']:.2e} (deg/s)^2/s, sigma_r {v['sr']:.3f} deg/s*s, sigma_w {v['sw']:.3f} deg/s*sqrt(s), n {v['n']}" for ax, v in spar.items()))
        r2 = run_stage_a(cfg, ctx, tun, "lwo", workers, {"scales": scales, "smoother": spar}, log_, out)
        L = pd.concat([r["lwo"] for r in r2 if len(r.get("lwo", []))], ignore_index=True)
        L = L[L["in_analysis"]]
        med = L.groupby("rule")["err_deg"].median().to_dict()
        rule = "smoothed" if med["smoothed"] <= med["raw"] + float(sa["bias_rule_tie_deg"]) else "raw"
        log_(f"bias rule (tuning leave-window-out median tilt error, deg): raw {med['raw']:.4f}, smoothed {med['smoothed']:.4f}, "
             f"A3 reference {med['a3']:.4f} -> {rule}")
        frozen = {"smoother": spar, "rule": rule, "lwo_tuning_median_deg": med, "scales": scales,
                  "frozen_local": pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds")}
        (out / "stage_a_decisions.json").write_text(json.dumps(frozen, indent=1, default=_jd), encoding="utf-8")
        L.to_csv(out / "csv" / "stage_a_lwo_tuning_dev.csv.gz", index=False)
    pk_run = [pk for pk, p in cfg["periods"].items() if p["role"] in roles]
    h = cfg_hash({"stage_a": sa, "smoother": frozen["smoother"], "rule": frozen["rule"], "scales": frozen["scales"]})
    r3 = run_stage_a(cfg, ctx, pk_run, "full", workers, {"scales": frozen["scales"], "smoother": frozen["smoother"],
                                                         "bias_rule": frozen["rule"], "git": git, "cfg_hash": h}, log_, out)
    for r in r3:
        log_(f"  Stage A {r['animal']} {r['period']}: windows {len(r['W'])}, quiet tilt check {r['tilt_check_deg']:.3f} deg, "
             f"ok16 {r['frac_ok16']:.3f}, t_since quantiles (50/75/90/99) {[round(x) for x in r['tsw_quantiles_s']]} s, {r['elapsed_s']:.0f} s")
    return {"decisions": frozen, "results": r3, "hash": h}


def write_attitude_readme(cfg: dict, dec: dict, git: str, out: Path) -> None:
    root = Path(cfg["cache_roots"]["attitude16"])
    root.mkdir(parents=True, exist_ok=True)
    sa = cfg["stage_a"]
    txt = f"""# attitude16_cache — Stage A of the V5 head-IMU / WISER fusion (cohort 2026c)

Written by `wiser/scripts/analyze_wiser_ins_fusion_v5.py` (git {git}, run `{out}`), plan
`implementation_plan/2026-10-01-wiser-ins-fusion-v5.md`. One file per animal-period: `<SFxx>/<period>.npz` (period =
`night_<date>` / `day_<date>`, the whole cached IMU window: nights 20:50 -> 05:30, days as cached), plus
`<SFxx>/<period>_windows.csv.gz` (strict still windows: sample bounds, centre time, duration, gravity direction, raw ZARU
`bhat_*`, anchor biases `braw_*` / `bsmoothed_*`, A3 bias over the window `ba3_*`, closure angle `closure_deg`) and, for days,
`<SFxx>/<period>_imu_seconds.csv.gz` (cache-equivalent per-second IMU table with the smoothing pilot's columns/rules).
IMU only — **no WISER** information enters Stage A. Derived from the A1 (raw 1250-Hz) and A3 (100-Hz calibrated) caches;
raw drives are never read.

Pipeline: gate v2 `process_period` (Hampel -> held-reading reconstruction of clipped gyro runs -> 40-Hz Butterworth-4
zero-phase -> 100 Hz -> head frame; A3 ellipsoid-calibrated accelerometer) -> strict still windows (gate v2: every 0.1-s
acc direction within 0.3 deg of the window mean, | |a| - g | < 0.03 g, |omega| < 3 deg/s, >= 1 s; **no WISER veto**) ->
per-animal gyro scale (gate v2 selection: {', '.join(f'{a} {s:.3f}' for a, s in dec['scales'].items())}) -> gyro bias =
piecewise-linear in clock time through anchors at every strict-window centre (rule `{dec['rule']}`: random-walk Kalman/RTS
smoother of the window ZARUs with measurement variance sigma_r^2/d^2 + sigma_w^2/d, parameters fitted by ML on the tuning
windows: {json.dumps({ax: {k: round(v, 8) for k, v in p.items() if k in ('qb', 'sr', 'sw')} for ax, p in dec['smoother'].items()})};
flat extrapolation) -> quaternion integration at 100 Hz with gravity aiding **only** at strict-window centres (closure
rotation distributed linearly in clock time between consecutive centres; no tilt resets, no dynamic gravity pull) ->
f = R(q) a - g e_z -> zero-phase Butterworth-{sa['butter_order']} low-pass {sa['lp_hz']} Hz -> resample_poly(4, 25) -> 16 Hz.

| key | dtype / shape | meaning |
|---|---|---|
| `t_unix_ms` | float64 (n,) | field-PC Unix ms on the IMU clock (tau* NOT applied); grid j <-> 100-Hz sample 6.25 j |
| `f_xy_2hz` | float32 (n, 2) | world-frame horizontal specific force (m/s^2, gravity removed, 2-Hz low-pass). **Yaw arbitrary** (0 at the first strict window) and **drifting** with the residual yaw bias — never re-anchored |
| `f_z_2hz` | float32 (n,) | vertical specific force minus g (m/s^2) |
| `q_wh` | float32 (n, 4) | attitude [w, x, y, z], v_world = R(q) v_head (head: x nose, y left, z up), nearest 100-Hz sample |
| `t_since_win_s` | float32 (n,) | seconds since the end of the last strict window (0 inside one; before the first: seconds to it) |
| `sigma_theta_deg` | float32 (n,) | gate-v2 clock-time law sqrt({sa['sigma_law']['sigma0_deg']}^2 + ({sa['sigma_law']['k_deg_per_s']} t)^2) at t = t_since_win_s (per-axis SD; median tilt angle = 1.1774 sigma). **Validated only to 10 min** (gate-v2 chains, mostly day records) |
| `p90_theta_deg` | float32 (n,) | p90 envelope sqrt({sa['p90_law']['p0_deg']}^2 + ({sa['p90_law']['k90_deg_per_s']} t)^2) |
| `ok` | bool (n,) | all 100-Hz samples of the support valid and >= {sa['ok_pad_s']} s from an invalid one |
| `in_window`, `sat`, `shake` | bool (n,) | support overlaps a strict window / a raw gyro saturation / a Phase-0 shake-train span |
| `bp_w_<lo>_<hi>`, `bp_a_<lo>_<hi>` | float32 (n,) | band powers of |omega| ((deg/s)^2) and |a| ((m/s^2)^2), A4 definition (2-4, 4-8, 8-12, 12-20 Hz) |
| `vedba` | float32 (n,) | VeDBA (|a - 2-s running mean|, m/s^2), 70-ms mean |
| `calib_json`, `meta_json` | str | scale, bias rule + smoother, laws, filters, sources, git, config hash |

**Usability (measured in the V5 run, report section 3):** inside strict windows |f_xy| is ~0.01 m/s^2; beyond ~60 s from a
strict window the attitude error grows to tens of degrees and |f_xy| is dominated by gravity leakage (median 2-6 m/s^2).
At night most samples are minutes from a strict window. Treat f_xy as meaningful only within ~10-60 s of a strict window,
and never trust the yaw across gaps.
"""
    (root / "README.md").write_text(txt, encoding="utf-8")


# ====================================================================================================== period containers
def build_period(ctx: dict, cfg: dict, pk: str, a: str, i: int) -> dict:
    per = cfg["periods"][pk]
    lo, hi = period_bounds(cfg, pk)
    ps, ps_s = per_second_tables(ctx, cfg, pk, a, lo, hi)
    fx = pd.read_csv(Path(cfg["cache_roots"]["wiser_fix"]) / pk / f"{a}.csv.gz")
    tr = P.Track(fx, lo, hi, ctx["taus"][a])
    tr.attach_imu(ps, ps_s, ctx["loco"]["theta_l"], ctx["loco"]["rho_l"])
    tr.ps_shift = ps_s
    stA = load_attitude16(cfg, a, pk)
    tg, grids = make_grids(stA, lo, hi, per["kind"], tr, cfg)
    hid = make_schemes(tr, cfg, pk, i, ctx["seed"])
    zf = {w_: node_flags(tr, tg, grids[w_], w_) for w_ in ("true", "shift")}
    t16 = stA["t_unix_ms"]
    sel = (t16 >= lo) & (t16 < hi)
    fxy = np.hypot(*stA["f_xy_2hz"][sel].T)
    tsw = stA["t_since_win_s"][sel]
    fx_tab = []
    for lo_, hi_ in zip(cfg["stage_a"]["lwo_bins_s"][:-1], cfg["stage_a"]["lwo_bins_s"][1:]):
        m = (tsw >= lo_) & (tsw < hi_)
        fx_tab.append({"animal": a, "period": pk, "kind": per["kind"], "tsw_lo": lo_, "tsw_hi": hi_, "n16": int(m.sum()),
                       "frac": float(m.mean()), "fxy_median": float(np.median(fxy[m])) if m.any() else np.nan,
                       "fxy_p90": float(np.percentile(fxy[m], 90)) if m.any() else np.nan,
                       "fz_median": float(np.median(stA["f_z_2hz"][sel][m])) if m.any() else np.nan})
    return {"animal": a, "period": pk, "kind": per["kind"], "role": per["role"], "lo": lo, "hi": hi, "tr": tr, "tg": tg,
            "grids": grids, "hid": hid, "zf": zf, "r2p": P.r2_from_anchors(tr.A, ctx["table"]), "psi": {}, "fxy_tab": fx_tab,
            "i": i, "stage_a_meta": stA["meta"]}


def get_psi(C_: dict, cfg: dict, vis_key: str, which: str, mirror: bool) -> dict:
    k = (vis_key, which, mirror)
    if k not in C_["psi"]:
        tr = C_["tr"]
        vis = np.ones(tr.n, bool) if vis_key == "full" else ~C_["hid"][vis_key]
        z = tr.z.copy()
        if mirror:
            z[:, 1] = -z[:, 1]
        C_["psi"][k] = psi_regression(tr, z, vis, C_["tg"], C_["grids"][which], C_["r2p"],
                                      {**cfg["psi_reg"], "psi0_min_sd_deg": cfg["stage_b"]["psi0_min_sd_deg"]})
    return C_["psi"][k]


def run_spec(C_: dict, cfg: dict, specs: list, want_cov: bool, nm: dict, mirror_frame: bool, chunk: int = 66) -> list:
    """specs: list of dicts {conf, vis_key, which ('true'|'shift'), law ('median'|'p90'), mirror (bool, relative to the
    chosen frame)}. Runs them in chunks with prange; returns one output dict per spec."""
    tr = C_["tr"]
    sb = cfg["stage_b"]
    laws = {"median": cfg["stage_a"]["sigma_law"], "p90": cfg["stage_a"]["p90_law"]}
    r2w = r2_measured(tr.A, nm)
    zN = tr.z.copy()
    zM = tr.z.copy()
    zM[:, 1] = -zM[:, 1]
    if mirror_frame:
        zN, zM = zM, zN
    outs = []
    for c0 in range(0, len(specs), chunk):
        sp = specs[c0:c0 + chunk]
        vis_keys = sorted({s["vis_key"] for s in sp})
        vis_list = [np.ones(tr.n, bool) if v == "full" else ~C_["hid"][v] for v in vis_keys]
        psi_keys = sorted({(s["vis_key"], s["which"], bool(s.get("mirror", False)) != mirror_frame) for s in sp})
        psis = [get_psi(C_, cfg, *k) for k in psi_keys]
        pars, cz, cv, czf, cpsi, cg = [], [], [], [], [], []
        for s in sp:
            mir = bool(s.get("mirror", False)) != mirror_frame
            pk_ = psi_keys.index((s["vis_key"], s["which"], mir))
            ps_ = psis[pk_]
            pars.append(make_par(s["conf"], sb, laws[s.get("law", "median")], nm, ps_["psi0"], ps_["psi0_var"]))
            cz.append(1 if s.get("mirror", False) else 0)
            cv.append(vis_keys.index(s["vis_key"]))
            czf.append(0 if s["which"] == "true" else 1)
            cpsi.append(pk_)
            cg.append(0 if s["which"] == "true" else 1)
        o = run_v5(tr.t, [zN, zM], r2w, vis_list, [C_["zf"]["true"], C_["zf"]["shift"]], [p["psio"] for p in psis],
                   [p["psisd"] for p in psis], C_["tg"], [C_["grids"]["true"], C_["grids"]["shift"]], np.array(pars), cz, cv, czf, cpsi,
                   cg, int(sb["n_irls"]), want_cov)
        for i in range(len(sp)):
            outs.append({k: (v[i] if isinstance(v, np.ndarray) and v.shape[0] == len(sp) else v) for k, v in o.items()})
    return outs


# ====================================================================================================== tuning
def conf_key(c: dict) -> tuple:
    return tuple((k, str(c[k])) for k in ("sig_res", "tau_b", "t_max", "sig_v", "sig_vr", "kappa_cv"))


def evaluate_configs(confs: list, conts: list, cfg: dict, nms: dict, frame_mirror: bool, log_, cache: dict) -> list:
    """J (pooled held-out RMSE on the tuning schemes) and the trimmed NIS of each configuration over the tuning
    containers. Results are cached by configuration."""
    tc = cfg["tuning"]
    schemes = tc["schemes"]
    todo = [c for c in confs if conf_key(c) not in cache]
    if todo:
        acc = {conf_key(c): {"se": 0.0, "n": 0, "nis_t": 0.0, "n_t": 0, "nis_u": 0.0, "n_u": 0, "gt599": 0, "gt1382": 0,
                             "se_by": {}, "n_by": {}} for c in todo}
        t0 = time.time()
        for C_ in conts:
            nm = nms[C_["kind"]]
            tr = C_["tr"]
            specs = [{"conf": c, "vis_key": v, "which": "true"} for c in todo for v in list(schemes) + ["full"]]
            outs = run_spec(C_, cfg, specs, False, nm, frame_mirror)
            for s, o in zip(specs, outs):
                a_ = acc[conf_key(s["conf"])]
                if s["vis_key"] == "full":
                    nis = o["nis"]
                    ok = np.isfinite(nis) & (tr.A >= 7)
                    v = nis[ok]
                    t_ = v[v <= float(tc["nis_trim"])]
                    a_["nis_t"] += float(t_.sum())
                    a_["n_t"] += int(len(t_))
                    a_["nis_u"] += float(v.sum())
                    a_["n_u"] += int(len(v))
                    a_["gt599"] += int((v > 5.991).sum())
                    a_["gt1382"] += int((v > float(tc["nis_trim"])).sum())
                else:
                    sc = P.scored_mask(tr, C_["hid"][s["vis_key"]])
                    e2 = np.sum((tr.z[sc] - o["zhat"][sc]) ** 2, axis=1)
                    e2 = e2[np.isfinite(e2)]
                    a_["se"] += float(e2.sum())
                    a_["n"] += int(len(e2))
                    kk = f"{C_['kind']}|{s['vis_key']}"
                    a_["se_by"][kk] = a_["se_by"].get(kk, 0.0) + float(e2.sum())
                    a_["n_by"][kk] = a_["n_by"].get(kk, 0) + int(len(e2))
        for c in todo:
            a_ = acc[conf_key(c)]
            cache[conf_key(c)] = {**{k: c[k] for k in ("sig_res", "tau_b", "t_max", "sig_v", "sig_vr", "kappa_cv")},
                                  "J": math.sqrt(a_["se"] / max(a_["n"], 1)), "n": a_["n"], "nis": a_["nis_t"] / max(a_["n_t"], 1),
                                  "nis_untrimmed": a_["nis_u"] / max(a_["n_u"], 1), "frac_gt_5.99": a_["gt599"] / max(a_["n_u"], 1),
                                  "frac_gt_13.82": a_["gt1382"] / max(a_["n_u"], 1),
                                  **{f"rmse_{k}": math.sqrt(a_["se_by"][k] / max(a_["n_by"][k], 1)) for k in a_["se_by"]}}
        log_(f"  evaluated {len(todo)} configurations on {len(conts)} tuning animal-periods in {time.time() - t0:.0f} s")
    return [cache[conf_key(c)] for c in confs]


def pick(rows: list, tc: dict, constrained: bool = True) -> dict:
    lo_, hi_ = tc["nis_range"]
    tie = float(tc["tie_J_in"])
    tmaxv = lambda r: fval(r["t_max"])  # noqa: E731
    if constrained:
        inside = [r for r in rows if lo_ <= r["nis"] <= hi_]
        if inside:
            pool = inside
        else:
            dist = lambda r: max(lo_ - r["nis"], r["nis"] - hi_, 0.0)  # noqa: E731
            dmin = min(dist(r) for r in rows)
            pool = [r for r in rows if dist(r) <= dmin + 1e-12]
    else:
        pool = rows
    jmin = min(r["J"] for r in pool)
    cand = [r for r in pool if r["J"] <= jmin + tie]
    cand.sort(key=lambda r: (-float(r["sig_res"]), tmaxv(r)))
    return cand[0]


def tune(conts: list, cfg: dict, nms: dict, frame_mirror: bool, log_) -> dict:
    tc = cfg["tuning"]
    cache = {}
    s1 = tc["stage1"]
    g1 = [{"sig_res": sr, "tau_b": tb, "t_max": tm, "sig_v": s1["sig_v"], "sig_vr": s1["sig_vr"], "kappa_cv": kc}
          for sr in s1["sig_res"] for tb in s1["tau_b"] for tm in s1["t_max"] for kc in s1["kappa_cv"]]
    r1 = evaluate_configs(g1, conts, cfg, nms, frame_mirror, log_, cache)
    b1 = pick(r1, tc)
    log_(f"tuning stage 1 ({len(g1)}): sig_res {b1['sig_res']} tau_b {b1['tau_b']} t_max {b1['t_max']} kappa_cv {b1['kappa_cv']} -> "
         f"J {b1['J']:.4f} in, NIS {b1['nis']:.3f}")
    s2 = tc["stage2"]
    g2 = [{**{k: b1[k] for k in ("sig_res", "tau_b", "t_max", "kappa_cv")}, "sig_v": sv, "sig_vr": svr} for sv in s2["sig_v"] for svr in s2["sig_vr"]]
    r2 = evaluate_configs(g2, conts, cfg, nms, frame_mirror, log_, cache)
    b2 = pick(r2, tc)
    log_(f"tuning stage 2 ({len(g2)}): sig_v {b2['sig_v']} sig_vr {b2['sig_vr']} -> J {b2['J']:.4f}, NIS {b2['nis']:.3f}")
    g3 = [{**{k: b2[k] for k in ("tau_b", "t_max", "kappa_cv", "sig_v", "sig_vr")}, "sig_res": float(b2["sig_res"]) * f}
          for f in tc["stage3"]["sig_res_factor"]]
    r3 = evaluate_configs(g3, conts, cfg, nms, frame_mirror, log_, cache)
    b3 = pick(r3, tc)
    log_(f"tuning stage 3 ({len(g3)}): sig_res {b3['sig_res']} -> J {b3['J']:.4f}, NIS {b3['nis']:.3f}")
    allr = list(cache.values())
    unc = pick(allr, tc, constrained=False)
    log_(f"unconstrained J-minimiser (V5_unc, secondary): {[(k, unc[k]) for k in ('sig_res', 'tau_b', 't_max', 'kappa_cv', 'sig_v', 'sig_vr')]} "
         f"J {unc['J']:.4f} NIS {unc['nis']:.3f}")
    edge = {}
    for k, grid in (("sig_res", s1["sig_res"]), ("tau_b", s1["tau_b"]), ("t_max", s1["t_max"]), ("kappa_cv", s1["kappa_cv"]),
                    ("sig_v", s2["sig_v"]), ("sig_vr", s2["sig_vr"])):
        vals = [fval(x) for x in grid]
        v = fval(b3[k])
        edge[k] = bool(v <= min(vals) or v >= max(vals))
    return {"tuned": {k: b3[k] for k in ("sig_res", "tau_b", "t_max", "sig_v", "sig_vr", "kappa_cv")}, "best": b3, "unc": unc,
            "stage1": r1, "stage2": r2, "stage3": r3, "all": allr, "on_grid_edge": edge}


# ====================================================================================================== evaluation
V5_METHODS = ("V5", "V5_shift", "V5_p90", "V5_unc")


def evaluate_container(C_: dict, cfg: dict, ctx: dict, nm: dict, tuned: dict, unc: dict, frame_mirror: bool, out: Path) -> dict:
    """All V5 variants + the pilot baselines on one animal-period; saves the filter outputs; returns per-fix predictions."""
    tr = C_["tr"]
    hid = C_["hid"]
    specs = [{"conf": tuned, "vis_key": "full", "which": "true", "tag": "V5|full"}]
    specs += [{"conf": tuned, "vis_key": s, "which": "true", "tag": f"V5|{s}"} for s in SCHEMES]
    specs += [{"conf": tuned, "vis_key": s, "which": "shift", "tag": f"V5_shift|{s}"} for s in SCHEMES]
    specs += [{"conf": tuned, "vis_key": "full", "which": "true", "law": "p90", "tag": "V5_p90|full"}]
    specs += [{"conf": tuned, "vis_key": s, "which": "true", "law": "p90", "tag": f"V5_p90|{s}"} for s in SCHEMES]
    if conf_key(unc) != conf_key(tuned):
        specs += [{"conf": unc, "vis_key": s, "which": "true", "tag": f"V5_unc|{s}"} for s in SCHEMES]
    specs += [{"conf": tuned, "vis_key": "full", "which": "true", "mirror": True, "tag": "V5_mirror|full"}]
    outs = run_spec(C_, cfg, specs, True, nm, frame_mirror)
    O = {s["tag"]: o for s, o in zip(specs, outs)}
    if conf_key(unc) == conf_key(tuned):
        for s in SCHEMES:
            O[f"V5_unc|{s}"] = O[f"V5|{s}"]
    preds = P.predict_all(tr, ctx["table"], ctx["ptuned"], hid)
    r2w = r2_measured(tr.A, nm)
    for m in V5_METHODS:
        for s in SCHEMES:
            o = O[f"{m}|{s}"]
            zh = o["zhat"]
            if frame_mirror:
                zh = zh.copy()
                zh[:, 1] = -zh[:, 1]
            preds[(m, s)] = np.where(hid[s][:, None], zh, np.nan)
            preds[(m + "_var", s)] = o["var"]
            preds[(m + "_mode", s)] = o["mode"]
    fd = out / "fusion" / C_["period"] / C_["animal"]
    fd.mkdir(parents=True, exist_ok=True)
    full = O["V5|full"]
    np.savez_compressed(fd / "v5_full.npz", t_al_s=tr.t, t_ms=tr.fx["t_ms"].to_numpy(), z=tr.z, anchors=tr.A, r2w=r2w, zf_true=C_["zf"]["true"],
                        **{k: full[k] for k in ("p", "v", "b", "psi", "d", "var", "nis", "w", "mode", "ll")},
                        **{f"p90_{k}": O["V5_p90|full"][k] for k in ("p", "d", "var", "nis", "mode", "ll")},
                        mirror_ll=O["V5_mirror|full"]["ll"], frame_mirror=np.array(frame_mirror))
    np.savez_compressed(fd / "v5_heldout.npz", **{f"hidden_{s}": hid[s] for s in SCHEMES},
                        **{f"{m}_{s}_{k}": (preds[(m, s)] if k == "zhat" else O[f"{m}|{s}"][k]) for m in V5_METHODS for s in SCHEMES
                           for k in ("zhat", "var", "mode", "nis")})
    psi_rows = []
    for (vk, which, mir), p in C_["psi"].items():
        psi_rows.append({"animal": C_["animal"], "period": C_["period"], "vis": vk, "imu": which, "mirror": mir, "Rbar": p["Rbar"],
                         "n_pairs": p["n_pairs"], "n_eff": p["n_eff"], "psi_whole_deg": p["psi_whole"] * R2D if np.isfinite(p["psi_whole"]) else np.nan,
                         "psi_whole_se_deg": p["psi_whole_se_deg"], "psi0_sd_deg": math.sqrt(p["psi0_var"]) * R2D,
                         "frac_nodes_with_est": p["frac_nodes_with_est"]})
    # NIS / held-out z2 / handedness
    nis = full["nis"]
    ok = np.isfinite(nis) & (tr.A >= 7)
    v = nis[ok]
    trim = float(cfg["tuning"]["nis_trim"])
    row = {"animal": C_["animal"], "period": C_["period"], "n": int(ok.sum()), "nis_trimmed_mean": float(np.mean(v[v <= trim])),
           "nis_mean": float(np.mean(v)), "nis_median": float(np.median(v)), "frac_gt_5.99": float(np.mean(v > 5.991)),
           "frac_gt_13.82": float(np.mean(v > trim)), "irls_w_lt1": float(np.mean(full["w"][np.isfinite(nis)] < 1.0)),
           "ins_frac_nodes": float(np.mean(full["mode"] == 1)), "ll_normal": float(full["ll"][0]), "ll_mirrored": float(O["V5_mirror|full"]["ll"][0])}
    row["llr_per_fix"] = (row["ll_normal"] - row["ll_mirrored"]) / max(int(np.isfinite(nis).sum()), 1) * (-1 if frame_mirror else 1)
    for s in SCHEMES:
        o = O[f"V5|{s}"]
        sc = P.scored_mask(tr, hid[s])
        zh = preds[("V5", s)]
        r_ = tr.z - zh
        Sxx, Sxy, Syy = o["var"][:, 0] + r2w[:, 0], o["var"][:, 1], o["var"][:, 2] + r2w[:, 1]
        det = Sxx * Syy - Sxy ** 2
        z2 = (Syy * r_[:, 0] ** 2 - 2 * Sxy * r_[:, 0] * r_[:, 1] + Sxx * r_[:, 1] ** 2) / det
        row[f"heldout_z2_mean_{s}"] = float(np.nanmean(z2[sc]))
        row[f"heldout_z2_median_{s}"] = float(np.nanmedian(z2[sc]))
        row[f"heldout_frac_gt_5.99_{s}"] = float(np.nanmean(z2[sc] > 5.991))
    # plausibility of the position tracks
    walls = json.loads(Path(ctx["scfg"]["walls_json"]).read_text(encoding="utf-8"))
    still_sec = set(tr.ps["sec"].to_numpy()[tr.ps["still"].to_numpy(bool)].tolist())
    b2p = ctx["ptuned"]["B2p"]
    vis = np.ones(tr.n, bool)
    Pp_, Bp_, _ = P.kf_run(tr.t, tr.z, P.r2_from_anchors(tr.A, ctx["table"]), [vis], [tr.st_mid], [tr.st_at],
                           [{"q": b2p["q"], "tb": b2p["tb"], "sb": b2p["sb"], "mrej": ctx["ptuned"]["B2"]["mrej"]},
                            {"q": b2p["q"], "tb": b2p["tb"], "sb": b2p["sb"], "mrej": ctx["ptuned"]["B2"]["mrej"], "mult": tuple(ctx["ptuned"]["V2"]["mult"])}])
    p5 = full["p"].copy()
    if frame_mirror:
        p5[:, 1] = -p5[:, 1]
    plaus = []
    s0 = tr.lo / 1000.0
    for name, p in (("raw", tr.z), ("B2p_p", Pp_[0]), ("V2_p", Pp_[1]), ("V5_p", np.where(np.isfinite(p5), p5, Pp_[0]))):
        plaus.append({"animal": C_["animal"], "period": C_["period"], "method": name, **P.track_metrics(tr.t, p, walls, still_sec, s0)})
    ex = None
    if C_["animal"] == cfg.get("example_animal", "SF09") and C_["period"] == cfg["accept"].get("primary_period", "night_20260910"):
        ex = {"t": tr.t, "z": tr.z, "V5_s": preds[("V5", "s")], "V2_s": preds[("V2", "s")], "B2p_s": preds[("B2p", "s")], "hid_s": hid["s"],
              "V5_full": np.where(np.isfinite(p5), p5 + (full["d"] * np.array([1, -1 if frame_mirror else 1])), np.nan), "mode": full["mode"],
              "still": tr.still, "zf": C_["zf"]["true"]}
        np.savez_compressed(out / "example_test.npz", **ex)
    return {"preds": preds, "nis_row": row, "plaus": plaus, "psi_rows": psi_rows}


def errors_table(C_: dict, preds: dict) -> pd.DataFrame:
    tr = C_["tr"]
    rows = []
    methods = ["B1", "B2", "B2p", "B2p_p", "V1", "V2", "V1_shift", "V2_shift"] + list(V5_METHODS)
    for s in SCHEMES:
        sc = P.scored_mask(tr, C_["hid"][s])
        idx = np.flatnonzero(sc)
        mode = preds[("V5_mode", s)][sc]
        for m in methods:
            zh = preds.get((m, s))
            if zh is None:
                continue
            e = np.hypot(*(tr.z[sc] - zh[sc]).T)
            rows.append(pd.DataFrame({"period": C_["period"], "animal": C_["animal"], "method": m, "scheme": s, "i": idx, "e": e,
                                      "still": tr.still[sc], "moving": tr.moving[sc], "loco": tr.loco[sc], "block": tr.block[sc],
                                      "anchors": tr.A[sc], "ins": mode == 1}))
    return pd.concat(rows, ignore_index=True)


PAIRS_MAIN = [("V5", "B2p"), ("V5", "V2"), ("V5_shift", "B2p"), ("V5_shift", "V2")]
PAIRS_ALL = [("V2", "B2p"), ("B1", "B2p"), ("B2", "B2p"), ("V1", "B2p"), ("V5_p90", "B2p"), ("V5_p90", "V2"), ("V5_unc", "B2p"),
             ("V5_unc", "V2"), ("V5", "B2"), ("V5", "V5_shift")]


def _boot_job(job: dict) -> list:
    err, animals, seed = job["err"], job["animals"], job["seed"]
    rng = np.random.default_rng(seed)
    rows = []
    for sub in job["subsets"]:
        for m, ref in job["pairs"]:
            em_all, er_all = err[err.method == m], err[err.method == ref]
            if not len(em_all) or not len(er_all):
                continue
            for who in animals + ["pooled"]:
                em = em_all if who == "pooled" else em_all[em_all.animal == who]
                er = er_all if who == "pooled" else er_all[er_all.animal == who]
                if sub in ("still", "moving", "loco", "ins"):
                    em, er = em[em[sub]], er[er[sub]]
                elif sub == "cv":
                    em, er = em[~em["ins"]], er[~er["ins"]]
                em = em.sort_values(["animal", "i"])
                er = er.sort_values(["animal", "i"])
                assert np.array_equal(em["i"].to_numpy(), er["i"].to_numpy()), (m, ref, who, sub)
                r, _ = boot_dist(em["e"].to_numpy(), er["e"].to_numpy(), em["block"].to_numpy(), em["animal"].to_numpy(), rng,
                                 int(job["n_boot"]))
                rows.append({"period": job["period"], "scheme": job["scheme"], "subset": sub, "method": m, "ref": ref, "animal": who, **r})
    return rows


def compare_all(err: pd.DataFrame, animals: list, cfg: dict, ctx: dict, workers: int, log_) -> pd.DataFrame:
    jobs = []
    for pk in err["period"].unique():
        pi = int(cfg["periods"][pk]["index"])
        for s in SCHEMES:
            e = err[(err.period == pk) & (err.scheme == s)]
            base = ctx["seed"] + int(cfg["boot"]["seed_offsets"][pk]) * 1000 + SCHEMES.index(s) * 100
            jobs.append({"err": e, "animals": animals, "seed": base, "period": pk, "scheme": s, "pairs": PAIRS_MAIN,
                         "subsets": ["all", "moving", "still", "loco"], "n_boot": cfg["boot"]["n"]})
            jobs.append({"err": e, "animals": animals, "seed": base + 1, "period": pk, "scheme": s, "pairs": PAIRS_ALL,
                         "subsets": ["all"], "n_boot": cfg["boot"]["n"]})
            jobs.append({"err": e, "animals": animals, "seed": base + 2, "period": pk, "scheme": s, "pairs": [("V5", "V2"), ("V5", "B2p")],
                         "subsets": ["ins", "cv"], "n_boot": cfg["boot"]["n"]})
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_boot_job, jobs))
    log_(f"bootstrap comparisons: {len(jobs)} jobs in {time.time() - t0:.0f} s")
    return pd.DataFrame([r for rr in res for r in rr])


# ====================================================================================================== driver
def stage_a_tables(SA: dict) -> dict:
    res = SA["results"]
    W = pd.concat([r["W"] for r in res], ignore_index=True)
    L = pd.concat([r["lwo"] for r in res if len(r.get("lwo", []))], ignore_index=True)
    B = pd.concat([r["bouts"] for r in res if len(r.get("bouts", []))], ignore_index=True)
    info = pd.DataFrame([{"animal": r["animal"], "period": r["period"], "n_windows": len(r["W"]), "still_min": float(r["W"]["dur_s"].sum() / 60),
                          "tilt_check_deg": r["tilt_check_deg"], "frac_ok16": r["frac_ok16"], "cache_bytes": r["cache_bytes"],
                          "tsw_p50": r["tsw_quantiles_s"][0], "tsw_p75": r["tsw_quantiles_s"][1], "tsw_p90": r["tsw_quantiles_s"][2],
                          "tsw_p99": r["tsw_quantiles_s"][3], "elapsed_s": r["elapsed_s"], "cache_path": r["cache_path"]} for r in res])
    return {"W": W, "L": L, "B": B, "info": info}


def run(cfg: dict, roles: list, workers: int, threads: int, out: Path, log_) -> dict:
    t_start = time.time()
    set_num_threads(threads)
    ctx = build_context(cfg)
    git = C.git_commit()
    animals = cfg["_animals"]
    csv = out / "csv"
    csv.mkdir(exist_ok=True)
    seed = ctx["seed"]
    # ---------------- Stage A on the tuning periods (decisions frozen inside)
    SA_t = stage_a_all(cfg, ctx, ["tuning"], workers, out, log_, git)
    dec = SA_t["decisions"]
    write_attitude_readme(cfg, dec, git, out)
    tun_pks = [pk for pk, p in cfg["periods"].items() if p["role"] == "tuning"]
    t0 = time.time()
    conts_t = [build_period(ctx, cfg, pk, a, i) for pk in tun_pks for i, a in enumerate(animals)]
    log_(f"tuning containers built ({time.time() - t0:.0f} s): " + ", ".join(f"{C_['period'][:5]} {C_['animal']} {C_['tr'].n:,}" for C_ in conts_t))
    # ---------------- measured WISER noise model (tuning, per period kind)
    nms = {}
    for kind in ("night", "day"):
        items = [(C_["tr"], C_["tr"].ps) for C_ in conts_t if C_["kind"] == kind]
        if not items:
            continue
        nms[kind] = measure_noise(items, cfg["noise_model"], int(cfg["noise_model"]["seed"]))
        nm = nms[kind]
        log_(f"noise model [{kind}]: drift {'ON' if nm['drift_on'] else 'off'} (share x {nm['share_x']:.3f}, y {nm['share_y']:.3f}; sigma_d "
             f"{nm['sigma_d_x']:.2f}/{nm['sigma_d_y']:.2f} in, T_d {nm['T_d_s']:.1f} s); white SD at 9/8/7 anchors x "
             f"{math.sqrt(nm['white_var']['9']['x']):.2f}/{math.sqrt(nm['white_var']['8']['x']):.2f}/{math.sqrt(nm['white_var']['7']['x']):.2f}, y "
             f"{math.sqrt(nm['white_var']['9']['y']):.2f}/{math.sqrt(nm['white_var']['8']['y']):.2f}/{math.sqrt(nm['white_var']['7']['y']):.2f} in")
    for kind in ("night", "day"):
        if kind not in nms:
            other = [k for k in nms][0]
            log_(f"WARNING: no tuning period of kind {kind}; using the {other} noise model for it (development configurations only)")
            nms[kind] = nms[other]
    (out / "noise_model.json").write_text(json.dumps(nms, indent=1, default=_jd), encoding="utf-8")
    # ---------------- handedness (tuning)
    votes = {"normal": 0, "mirrored": 0, "none": 0}
    hand_rows = []
    for C_ in conts_t:
        pn, pm = get_psi(C_, cfg, "full", "true", False), get_psi(C_, cfg, "full", "true", True)
        if np.isfinite(pn["Rbar"]) and np.isfinite(pm["Rbar"]):
            votes["normal" if pn["Rbar"] > pm["Rbar"] else "mirrored"] += 1
        else:
            votes["none"] += 1
        hand_rows.append({"animal": C_["animal"], "period": C_["period"], "Rbar_normal": pn["Rbar"], "Rbar_mirrored": pm["Rbar"],
                          "n_pairs": pn["n_pairs"], "n_eff": pn["n_eff"]})
    kmin = int(cfg["psi_reg"]["handed_min_periods"])
    frame_mirror = votes["mirrored"] >= kmin
    hand_rule = "normal" if votes["normal"] >= kmin else ("mirrored" if frame_mirror else "normal (no decision: V4 candidate kept)")
    log_(f"handedness (tuning regression resultants): votes {votes} -> {hand_rule}")
    # ---------------- tuning
    T = tune(conts_t, cfg, nms, frame_mirror, log_)
    tuned, unc = T["tuned"], T["unc"]
    for nm_, rows in (("stage1", T["stage1"]), ("stage2", T["stage2"]), ("stage3", T["stage3"]), ("all", T["all"])):
        pd.DataFrame(rows).to_csv(csv / f"tuning_{nm_}.csv", index=False)
    frozen_t = pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds")
    (out / "tuned_frozen.json").write_text(json.dumps({"tuned": tuned, "best": T["best"], "unc": unc, "frame_mirror": frame_mirror,
                                                       "on_grid_edge": T["on_grid_edge"], "frozen_local": frozen_t,
                                                       "test_periods_read": False}, indent=1, default=_jd), encoding="utf-8")
    log_(f"TUNING FROZEN {frozen_t}: {tuned} (J {T['best']['J']:.4f} in, NIS {T['best']['nis']:.3f}) -> tuned_frozen.json, before any test period is read")
    # ---------------- evaluation: tuning periods
    errs, nis_rows, plaus, psi_rows, fxy_rows = [], [], [], [], []
    for C_ in conts_t:
        t1 = time.time()
        r = evaluate_container(C_, cfg, ctx, nms[C_["kind"]], tuned, unc, frame_mirror, out)
        errs.append(errors_table(C_, r["preds"]))
        nis_rows.append(r["nis_row"])
        plaus += r["plaus"]
        psi_rows += r["psi_rows"]
        fxy_rows += C_["fxy_tab"]
        log_(f"  evaluated {C_['period']} {C_['animal']} ({time.time() - t1:.0f} s): NIS trimmed {r['nis_row']['nis_trimmed_mean']:.2f}, "
             f"INS nodes {r['nis_row']['ins_frac_nodes']:.3f}")
    del conts_t
    SA_e = None
    if "test" in roles:
        SA_e = stage_a_all(cfg, ctx, ["test"], workers, out, log_, git, frozen=dec)
        test_pks = [pk for pk, p in cfg["periods"].items() if p["role"] == "test"]
        for pk in test_pks:
            for i, a in enumerate(animals):
                t1 = time.time()
                C_ = build_period(ctx, cfg, pk, a, i)
                r = evaluate_container(C_, cfg, ctx, nms[C_["kind"]], tuned, unc, frame_mirror, out)
                errs.append(errors_table(C_, r["preds"]))
                nis_rows.append(r["nis_row"])
                plaus += r["plaus"]
                psi_rows += r["psi_rows"]
                fxy_rows += C_["fxy_tab"]
                log_(f"  evaluated {pk} {a} ({time.time() - t1:.0f} s, {C_['tr'].n:,} fixes): NIS trimmed {r['nis_row']['nis_trimmed_mean']:.2f}, "
                     f"INS nodes {r['nis_row']['ins_frac_nodes']:.3f}, LLR/fix {r['nis_row']['llr_per_fix']:+.4f}")
                del C_
    err = pd.concat(errs, ignore_index=True)
    err.to_csv(csv / "heldout_errors_all.csv.gz", index=False)
    comp = compare_all(err, animals, cfg, ctx, min(workers * 2, 12), log_)
    comp.to_csv(csv / "bootstrap_comparisons.csv", index=False)
    verdicts = {}
    for pk in comp["period"].unique():
        verdicts[pk] = verdict_v5(comp[comp.period == pk], animals, cfg["accept"])
    primary = cfg["accept"].get("primary_period", "night_20260910")
    if primary in verdicts:
        v = verdicts[primary]
        log_(f"VERDICT (test night, pre-registered): {v['verdict']} — " + "; ".join(
            f"{s}: p_scheme {d['p_scheme']:.3f} (Holm thr {d.get('holm_threshold', float('nan')):.4f}, primary {'PASS' if d['primary_pass'] else 'fail'}), "
            f"control no-gain {d['n_control_no_gain']}/5, moving {d['pooled_moving_d']}" for s, d in v["schemes"].items()))
    # ---------------- tables + summary
    SAt = stage_a_tables({"results": SA_t["results"] + (SA_e["results"] if SA_e else [])})
    SAt["W"].to_csv(csv / "stage_a_windows.csv.gz", index=False)
    SAt["L"].to_csv(csv / "stage_a_lwo.csv.gz", index=False)
    SAt["B"].to_csv(csv / "stage_a_bouts.csv.gz", index=False)
    SAt["info"].to_csv(csv / "stage_a_info.csv", index=False)
    pd.DataFrame(fxy_rows).to_csv(csv / "stage_a_fxy_by_tsince.csv", index=False)
    pd.DataFrame(nis_rows).to_csv(csv / "nis_consistency.csv", index=False)
    pd.DataFrame(plaus).to_csv(csv / "plausibility.csv", index=False)
    pd.DataFrame(psi_rows).to_csv(csv / "psi_regression.csv", index=False)
    pd.DataFrame(hand_rows).to_csv(csv / "handedness_tuning_regression.csv", index=False)
    summ = {}
    for (pk, m, s), d in err.groupby(["period", "method", "scheme"]):
        summ[f"{pk}|{m}|{s}"] = {w_: {"med": float(np.median(g.e)), "rmse": float(np.sqrt(np.mean(g.e ** 2))), "p90": float(np.percentile(g.e, 90)),
                                      "frac_gt24": float(np.mean(g.e > 24)), "frac_gt100": float(np.mean(g.e > 100)), "max": float(g.e.max()), "n": int(len(g))}
                                 for w_, g in list(d.groupby("animal")) + [("pooled", d)]}
    S = {"cohort": cfg["_cohort"], "roles": roles, "animals": animals, "stage_a_decisions": dec, "stage_a_hash": SA_t["hash"],
         "noise_models": nms, "handedness": {"votes": votes, "rule": hand_rule, "frame_mirror": frame_mirror},
         "tuned": tuned, "tuned_best": T["best"], "unc": unc, "on_grid_edge": T["on_grid_edge"], "tuning_frozen_local": frozen_t,
         "verdicts": verdicts, "summ": summ, "runtime_s": time.time() - t_start, "git_commit": git,
         "config": relpath(cfg["_path"]), "cache_roots": cfg["cache_roots"]}
    (out / "summary.json").write_text(json.dumps(S, indent=1, default=_jd), encoding="utf-8")
    prov = {"config": S["config"], "smoothing_config": cfg["smoothing_config"], "gate_v2_selection": cfg["gate_v2_selection"],
            "stage_a_caches": SAt["info"][["animal", "period", "cache_path", "cache_bytes"]].to_dict(orient="records"),
            "a1_index": [str(Path(cfg["cache_roots"]["imu_raw"]) / f) for f in ("index_2026c.csv", "index_day_2026c.csv")],
            "wiser_fix_index": [str(Path(cfg["cache_roots"]["wiser_fix"]) / f) for f in ("index_2026c.csv", "index_day_2026c.csv")],
            "make_imu_npz_root": ctx["v4"]["cfg"]["imu_npz_root"], "git_commit": git}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=1, default=_jd), encoding="utf-8")
    if "test" in roles:
        c = json.loads(Path(cfg["_path"]).read_text(encoding="utf-8"))
        c["tuned"] = {"fitted_on": "tuning night 2026-09-08 21:00 -> 2026-09-09 04:20 + tuning day 2026-09-08 08:00 -> 18:30 only",
                      "fitted_by": "wiser/scripts/analyze_wiser_ins_fusion_v5.py", "run_dir": str(out), "frozen_local": frozen_t,
                      "objective": cfg["tuning"]["objective"], "constraint": f"trimmed NIS in {cfg['tuning']['nis_range']}",
                      "values": tuned, "J_in": T["best"]["J"], "nis": T["best"]["nis"], "unconstrained_V5_unc": {k: unc[k] for k in tuned},
                      "on_grid_edge": T["on_grid_edge"], "frame": "mirrored" if frame_mirror else "normal"}
        c["fitted"] = {"stage_a": {"bias_rule": dec["rule"], "smoother": dec["smoother"], "lwo_tuning_median_deg": dec["lwo_tuning_median_deg"],
                                   "gyro_scales": dec["scales"], "config_hash": SA_t["hash"]},
                       "noise_models": {k: {kk: vv for kk, vv in v.items() if kk not in ("variogram",)} for k, v in nms.items()},
                       "handedness": S["handedness"], "verdict_test_night": verdicts.get(primary, {}).get("verdict"), "run_dir": str(out),
                       "written_local": pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds")}
        Path(cfg["_path"]).write_text(json.dumps(c, indent=2, ensure_ascii=False, default=_jd) + "\n", encoding="utf-8")
    log_(f"run done in {(time.time() - t_start) / 60:.1f} min")
    return S


# ====================================================================================================== figures + report
def _f(x, nd: int = 2) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "—"
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def _pct(x, nd: int = 1) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{100 * x:+.{nd}f} %"


def _ci(r) -> str:
    return f"{_pct(r['d_med'])} [{_pct(r['lo'])}, {_pct(r['hi'])}]"


def make_figures(out: Path, S: dict, cfg: dict, fdir: Path, cohort: str) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    csv = out / "csv"
    figs = []
    comp = pd.read_csv(csv / "bootstrap_comparisons.csv")
    animals = S["animals"]
    # 1 Stage A
    fx = pd.read_csv(csv / "stage_a_fxy_by_tsince.csv")
    L = pd.read_csv(csv / "stage_a_lwo.csv.gz")
    B = pd.read_csv(csv / "stage_a_bouts.csv.gz")
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    law = cfg["stage_a"]["sigma_law"]
    edges = np.asarray(cfg["stage_a"]["lwo_bins_s"], float)
    mids = np.sqrt(np.maximum(edges[:-1], 0.5) * np.minimum(edges[1:], 7200))
    for (kind, role), g in fx.groupby(["kind", fx["period"].map(lambda p: cfg["periods"][p]["role"])]):
        gg = g.groupby("tsw_lo").agg(med=("fxy_median", "median"), frac=("frac", "mean")).reindex(edges[:-1])
        ax[0].plot(mids, gg["med"], "o-", label=f"{kind} ({role})")
    tt = np.logspace(-1, 3.9, 100)
    ax[0].plot(tt, G * np.sin(np.radians(np.minimum(1.1774 * sigma_law(tt, law), 90))), "k--", label="g·sin(median tilt), σθ law")
    ax[0].set_xscale("log"); ax[0].set_yscale("log"); ax[0].set_xlabel("time since a strict still window (s)"); ax[0].set_ylabel("median |f_xy| (m/s²)")
    ax[0].set_title("Stage A horizontal specific force (2 Hz)"); ax[0].legend(fontsize=7)
    Ls = L[L["in_analysis"].astype(bool)].copy()
    Ls["bin"] = pd.cut(Ls["t_since_last_kept_s"], [0, 2, 5, 10, 30, 60, 120, 300, 600, 1e9])
    for (rule, role), g in Ls.groupby(["rule", "role"]):
        m = g.groupby("bin", observed=False)["err_deg"].median()
        xs = [iv.mid if np.isfinite(iv.right) and iv.right < 1e8 else 1200 for iv in m.index]
        ax[1].plot(xs, m.values, "o-", label=f"{rule} ({role})")
    ax[1].plot(tt, 1.1774 * sigma_law(tt, law), "k--", label="σθ law (median)")
    ax[1].set_xscale("log"); ax[1].set_yscale("log"); ax[1].set_xlabel("time since the last kept window (s)"); ax[1].set_ylabel("median tilt error at withheld windows (°)")
    ax[1].set_title("Leave-window-out tilt error"); ax[1].legend(fontsize=6)
    Bg = B[B["in_analysis"].astype(bool) & B["active"].astype(bool) & ~B["sat"].astype(bool)]
    rows = []
    for (var, role), g in Bg.groupby(["variant", "role"]):
        for lab in ("2-5 s", "5-15 s", "15-40 s"):
            gb = g[g["dbin"] == lab]
            rows.append((f"{var}\n{role}\n{lab}", gb["e_a3"].median(), gb["e_anch"].median()))
    xs = np.arange(len(rows))
    ax[2].bar(xs - 0.2, [r[1] for r in rows], 0.4, label="A3 running-median bias (gate v2)")
    ax[2].bar(xs + 0.2, [r[2] for r in rows], 0.4, label="Stage A anchored bias")
    ax[2].set_xticks(xs); ax[2].set_xticklabels([r[0] for r in rows], fontsize=6); ax[2].set_ylabel("median centre-to-centre tilt error (°)")
    ax[2].set_title("Gate-v2 bout test"); ax[2].legend(fontsize=7)
    fig.tight_layout()
    fn = f"{STEM}_stage_a_{cohort}.png"
    fig.savefig(fdir / fn, dpi=130); plt.close(fig); figs.append(fn)
    # 2 held-out deltas (test night)
    pk = cfg["accept"].get("primary_period", "night_20260910")
    c = comp[(comp.period == pk) & (comp.subset == "all")]
    if len(c):
        fig, axs = plt.subplots(1, len(SCHEMES), figsize=(18, 4.4), sharey=True)
        for k, s in enumerate(SCHEMES):
            a_ = axs[k]
            for j, (m, ref, col) in enumerate((("V5", "B2p", "C0"), ("V5", "V2", "C1"), ("V5_shift", "B2p", "C7"), ("V2", "B2p", "C2"))):
                cc = c[(c.scheme == s) & (c.method == m) & (c.ref == ref)].set_index("animal").reindex(animals + ["pooled"])
                x = np.arange(len(cc)) + (j - 1.5) * 0.18
                a_.errorbar(x, 100 * cc["d_med"], yerr=[100 * (cc["d_med"] - cc["lo"]), 100 * (cc["hi"] - cc["d_med"])], fmt="o", color=col,
                            ms=4, capsize=2, label=f"{LABEL.get(m, m)} vs {LABEL.get(ref, ref)}")
            a_.axhline(0, color="k", lw=0.7); a_.axhline(3, color="r", lw=0.7, ls=":")
            a_.set_xticks(np.arange(len(animals) + 1)); a_.set_xticklabels(animals + ["pooled"], rotation=45, fontsize=7)
            a_.set_title(SCHEME_LABEL[s], fontsize=9)
        axs[0].set_ylabel("Δ median held-out error (%; + = better)")
        axs[0].legend(fontsize=6, loc="lower left")
        fig.suptitle("Test night 2026-09-10/11: V5 vs B2′ / V2 (95 % block-bootstrap CI)")
        fig.tight_layout()
        fn = f"{STEM}_heldout_{cohort}.png"
        fig.savefig(fdir / fn, dpi=130); plt.close(fig); figs.append(fn)
    # 3 tuning
    Tall = pd.read_csv(csv / "tuning_all.csv")
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for tm, g in Tall.groupby(Tall["t_max"].astype(str)):
        ax.scatter(g["nis"], g["J"], s=14, label=f"T_max {tm}")
    b, u = S["tuned_best"], S["unc"]
    ax.scatter([b["nis"]], [b["J"]], s=120, facecolors="none", edgecolors="r", label="selected (constrained)")
    ax.scatter([u["nis"]], [u["J"]], s=120, marker="s", facecolors="none", edgecolors="k", label="V5_unc (unconstrained)")
    ax.axvspan(*cfg["tuning"]["nis_range"], color="g", alpha=0.08, label="NIS range")
    ax.set_xlabel("trimmed NIS (tuning, full-data runs)"); ax.set_ylabel("J = held-out RMSE (s + g-0.5, tuning) (in)")
    ax.set_xscale("log"); ax.legend(fontsize=7); ax.set_title("Tuning grid")
    fig.tight_layout()
    fn = f"{STEM}_tuning_{cohort}.png"
    fig.savefig(fdir / fn, dpi=130); plt.close(fig); figs.append(fn)
    # 4 by mode / state
    c2 = comp[(comp.period == pk) & (comp.animal == "pooled") & (comp.method == "V5")]
    if len(c2):
        fig, ax = plt.subplots(figsize=(9, 4.2))
        subs = ["all", "still", "moving", "loco", "ins", "cv"]
        for j, ref in enumerate(("B2p", "V2")):
            vals, los, his = [], [], []
            for s in ("s", "g05"):
                for sub in subs:
                    r = c2[(c2.scheme == s) & (c2.subset == sub) & (c2.ref == ref)]
                    vals.append(100 * r["d_med"].iloc[0] if len(r) else np.nan)
                    los.append(100 * r["lo"].iloc[0] if len(r) else np.nan)
                    his.append(100 * r["hi"].iloc[0] if len(r) else np.nan)
            x = np.arange(len(vals)) + (j - 0.5) * 0.35
            ax.errorbar(x, vals, yerr=[np.array(vals) - np.array(los), np.array(his) - np.array(vals)], fmt="o", capsize=2, label=f"V5 vs {LABEL[ref]}")
        ax.set_xticks(np.arange(2 * len(subs))); ax.set_xticklabels([f"{s}\n{sub}" for s in ("s", "g05") for sub in subs], fontsize=7)
        ax.axhline(0, color="k", lw=0.7); ax.set_ylabel("Δ median (%)"); ax.legend(fontsize=7)
        ax.set_title("Test night, pooled: by IMU state and by V5 mode at the hidden fix (ins = INS mode, cv = V2-like mode)")
        fig.tight_layout()
        fn = f"{STEM}_by_mode_{cohort}.png"
        fig.savefig(fdir / fn, dpi=130); plt.close(fig); figs.append(fn)
    # 5 example
    exf = out / "example_test.npz"
    if exf.exists():
        ex = dict(np.load(exf))
        t = ex["t"]
        ins = ex["mode"] == 1
        # choose the 120-s window with the most INS-mode moving fixes
        k = np.floor(t / 120).astype(int)
        score = pd.Series(ins & ~ex["still"]).groupby(k).sum()
        k0 = int(score.idxmax()) if len(score) else 0
        sel = (k == k0)
        fig, axs = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        for j, ax_ in enumerate(axs):
            ax_.plot(t[sel], ex["z"][sel, j], ".", color="0.6", ms=3, label="WISER fixes")
            h = sel & ex["hid_s"].astype(bool)
            ax_.plot(t[h], ex["V2_s"][h, j], "x", color="C1", ms=4, label="V2 prediction (s)")
            ax_.plot(t[h], ex["V5_s"][h, j], "+", color="C0", ms=5, label="V5 prediction (s)")
            ax_.plot(t[sel], ex["V5_full"][sel, j], "-", color="C0", lw=0.8, label="V5 full-data p + d")
            yl = ax_.get_ylim()
            ax_.fill_between(t[sel], yl[0], yl[1], where=ins[sel], color="C2", alpha=0.08, label="INS mode")
            ax_.set_ylabel(f"{'xy'[j]} (in, unverified frame)")
        axs[0].legend(fontsize=7, ncol=3); axs[1].set_xlabel("s from the period start")
        fig.suptitle(f"SF09, test night: 120-s window with the most INS-mode moving fixes")
        fig.tight_layout()
        fn = f"{STEM}_example_{cohort}.png"
        fig.savefig(fdir / fn, dpi=130); plt.close(fig); figs.append(fn)
    return figs


DEFINITIONS = r"""
All positions in the WISER native **inch** frame (UNVERIFIED offset origin, handedness a candidate); IMU in the head frame
(x nose, y left, z up) and a Stage-A world frame (z up, yaw arbitrary). $g$ = 9.81 m/s² = 386.1 in/s².

**Strict still window $W_i=[s_i,e_i)$** (gate v2, unchanged; **no WISER veto** here): consecutive 0.1-s blocks whose
accelerometer directions stay within 0.3° of the window mean, $\big||\bar{\mathbf a}_W|-g\big|<0.03g$, every sample
$|\boldsymbol\omega^{A3}|<3$ °/s, all samples valid, ≥ 1.0 s. Centre $c_i$, duration $d_i$, gravity direction
$\hat{\mathbf g}_{W_i}=\sum_W\mathbf a/|\sum_W\mathbf a|$. **Text:** the head is still (no rotation beyond ≈ 0.6°, no
acceleration) for at least 1 s.

**ZARU estimate** $\hat{\mathbf b}_i=\frac{1}{|W_i|}\sum_{k\in W_i}\mathbf w_k$ (°/s; $\mathbf w$ = reconstructed gyro before
bias removal). **Anchor smoother** (per head axis): $b_{i+1}=b_i+\eta_i$, $\eta_i\sim\mathcal N(0,q_b(c_{i+1}-c_i))$;
$\hat b_i=b_i+\epsilon_i$, $\epsilon_i\sim\mathcal N(0,\sigma_r^2/d_i^2+\sigma_w^2/d_i)$; Huber-robust Kalman filter + RTS,
$(q_b,\sigma_r,\sigma_w)$ by maximum innovation likelihood on the tuning windows. **Bias function**
$\mathbf b(t)=$ linear interpolation of the anchors $\tilde{\mathbf b}_i$ between window centres, flat outside. **Text:** the gyro
bias is re-estimated at every strict window, short windows weighted down (their ZARU carries residual micro-rotation).

**Stage-A attitude** $q_k$: $q_{k+1}=q_k\otimes\mathrm{Exp}(\boldsymbol\omega_k\Delta t)$, $\boldsymbol\omega_k=s_a(\mathbf w_k-\mathbf b(t_k))$
($s_a$ = per-animal gyro scale), tilt set from $\hat{\mathbf g}_{W}$ at window centres; closure
$\boldsymbol\delta_{i+1}$ = horizontal world-frame rotation with $\mathrm{Exp}(\boldsymbol\delta_{i+1})R(q^f_{c_{i+1}})\hat{\mathbf g}_{W_{i+1}}=\mathbf e_z$,
applied as $q_k=\mathrm{Exp}(\alpha_k\boldsymbol\delta_{i+1})\otimes q^f_k$, $\alpha_k=(k-c_i)/(c_{i+1}-c_i)$. **Closure angle**
$|\boldsymbol\delta_{i+1}|$ = centre-to-centre tilt error with the anchored bias.

**Horizontal specific force** $\mathbf f_{xy}=[R(q)\mathbf a-g\mathbf e_z]_{xy}$, zero-phase Butterworth-4 low-pass 2 Hz, 16 Hz
(m/s²; in/s² in Stage B). **Time since a strict window** $t_{since}$ (s) = time since the end of the last window (0 inside).
**σθ law** (gate v2, chain records vs clock time) $\sigma_\theta(t)=\sqrt{0.78^2+(0.0227\,t)^2}$° (per-axis SD; median tilt
angle $1.1774\,\sigma_\theta$); **p90 law** $\sqrt{3.07^2+(0.0921\,t)^2}$°.

**Leave-window-out (LWO) tilt error** at a withheld window $j$ (odd-numbered windows withheld from anchors and closures):
$e_j=\angle\big(R(q_{c_j})^\top\mathbf e_z,\ \hat{\mathbf g}_{W_j}\big)$ (°). **Bout test** (gate v2): centre-to-centre propagation
error $e=\angle(\mathbf g_{c_{i+1}},\hat{\mathbf g}_{W_{i+1}})$ over gate-v2 bouts (active, no saturation; 2–5 s and 5–15 s),
with the A3 running-median bias (gate v2) or Stage A's anchored bias.

**Stage-B model** (state $\mathbf x=[\mathbf p,\mathbf v,\mathbf b,\psi,\mathbf d]$): INS mode ($\mathbf f_{xy}$ ok and $t_{since}\le T_{max}$):
$\dot{\mathbf p}=\mathbf v$, $\dot{\mathbf v}=R(\psi)\mathbf f_{xy}-\mathbf b+\mathbf w$, $\mathbf w$ white with PSD $\sigma_{res}^2\Delta_{16}$;
CV mode: $\dot{\mathbf v}=\mathbf w$ with PSD $\kappa_{cv}\,q\,m_c$ ($q$ = 1 in²/s³, $m$ = V2's state multipliers);
$\mathbf b$: Gauss–Markov, time constant $\tau_b$, stationary SD $g\sin\sigma_\theta(t_{since})$; $\psi$: random walk,
$\dot{\mathrm{Var}}(\psi)=\max(0.0309\ \mathrm{deg^2/s},2k^2t_{since})$; $\mathbf d$: AR(1) with the measured
$(\sigma_d,T_d)$. WISER update $\mathbf z=\mathbf p+\mathbf d+\boldsymbol\varepsilon$, $\boldsymbol\varepsilon\sim\mathcal N(0,\mathrm{diag}\,\sigma^2_{w}(A))$;
pass 0 χ² gate $d^2>13.82$ inflates $R$; passes 1–2 Huber ($k$ = 2.5). Soft ZUPT $0=\mathbf v+\boldsymbol\epsilon$ ($\sigma_v$ in IMU-still
seconds, $\sigma_{vr}$ in rhythmic samples). EKF + RTS (extended Kalman smoother). **Prediction**
$\hat{\mathbf z}_h=\mathbf p^s_h+\mathbf d^s_h$. **Text:** the IMU supplies the acceleration where its attitude is recent;
elsewhere V5 is a V2-like smoother.

**Rhythmic body-stationary sample**: ok ∧ not IMU-still ∧ pilot state ≠ locomoting ∧ [shake-train span ∨
($B_{hi}\ge B_{lo}$ ∧ $B_{hi}+B_{lo}\ge(20\ ^\circ/\mathrm s)^2$)], $B_{hi}$ = |ω| band power 8–12 + 12–20 Hz, $B_{lo}$ = 2–4 + 4–8 Hz.

**Measured WISER noise** (tuning, still runs ≥ 20 s): nugget $\sigma^2_{w}(A)=\tfrac12(1.4826\,\mathrm{MAD}(\Delta))^2$ over
consecutive same-anchor fixes ≤ 0.5 s apart; robust variogram $\gamma(\tau)=\tfrac12(1.4826\,\mathrm{MAD}(z(t+\tau)-z(t)))^2$ of
9-anchor fixes, fit $\gamma(\tau)=n+\sigma_d^2(1-e^{-\tau/T_d})$; drift kept iff $\sigma_d^2\ge0.10(n+\sigma_d^2)$ in one axis
and $1\le T_d\le120$ s.

**ψ regression**: pairs of visible fixes 0.4–0.75 s apart with the IMU span ok and $t_{since}\le60$ s; $\Delta v_W$ = B2
velocity change, $\Delta v_I=\int\mathbf f_{xy}dt$ (complex), $|\Delta v_I|\ge8$ in/s; $c=\Delta v_W\overline{\Delta v_I}$;
$\hat\psi=\arg\sum c$, resultant $\bar R=|\sum c|/\sum|c|$ (0 = no consistent direction, 1 = perfect), standard error
$1/(\bar R\sqrt{2n_{eff}})$, $n_{eff}=(\sum|c|)^2/\sum|c|^2$.

**Held-out schemes:** (s) every 5th fix hidden alone; (g) all fixes in a random 10 % of 0.5-s / 1.0-s windows; (a) runs of
4–8 fixes (20 %); (a′) a random 10 % of 2-s windows (pilot). **Scored fix:** hidden ∧ anchors ≥ 7 ∧ IMU-QC-ok ∧
shifted-IMU-QC-ok. **Held-out error** $e=\lVert\mathbf z_h-\hat{\mathbf z}_h\rVert$ (in). **Δ** $=1-\mathrm{med}(e_M)/\mathrm{med}(e_{ref})$
(+ = method better); 95 % CI from 1000 paired 5-min-block bootstrap replicates (stratified by animal when pooled);
one-sided $p=(1+\#\{\Delta^*\le0\})/1001$. **Holm** over (s) and (g-0.5 s): animal eligible iff Δ ≥ 3 % vs B2′ and V2;
$p_a=\max(p_{B2'},p_{V2})$; scheme statistic = 4th-smallest $p_a$; first scheme at 0.0125, second at 0.025.
**Control**: V5 with every IMU input from t + 3600 s (days: circular within the window); passes iff its CI lower bound vs
B2′ is ≤ 0 in ≥ 4/5 animals. **Moving fixes**: IMU-QC-ok and not IMU-still (pilot).

**NIS** $d^2=\boldsymbol\nu^\top S^{-1}\boldsymbol\nu$ of forward pass-0 innovations (visible fixes, anchors ≥ 7, full-data run);
**trimmed NIS** = mean over $d^2\le13.82$ (≈ 1.99 if consistent). **Held-out $z^2$** $=(\mathbf z_h-\hat{\mathbf z}_h)^\top(P^s_{p+d}+R)^{-1}(\mathbf z_h-\hat{\mathbf z}_h)$
(χ²₂ ⇒ mean 2). **Handedness LLR** = forward pass-0 log-likelihood of the visible fixes, normal − mirrored WISER y (per fix).
**Plausibility** (pilot `track_metrics`): speed / acceleration percentiles on a 0.25-s grid, path length per hour, wall excursions.
"""


def write_report(out: Path, S: dict, cfg: dict, figs: list, rdir: Path, cohort: str) -> Path:
    csv = out / "csv"
    comp = pd.read_csv(csv / "bootstrap_comparisons.csv")
    animals = S["animals"]
    nis = pd.read_csv(csv / "nis_consistency.csv")
    plaus = pd.read_csv(csv / "plausibility.csv")
    info = pd.read_csv(csv / "stage_a_info.csv")
    L = pd.read_csv(csv / "stage_a_lwo.csv.gz")
    B = pd.read_csv(csv / "stage_a_bouts.csv.gz")
    fx = pd.read_csv(csv / "stage_a_fxy_by_tsince.csv")
    psi = pd.read_csv(csv / "psi_regression.csv")
    hand = pd.read_csv(csv / "handedness_tuning_regression.csv")
    T1 = pd.read_csv(csv / "tuning_all.csv")
    summ = S["summ"]
    V = S["verdicts"]
    pk0, pkd = cfg["accept"].get("primary_period", "night_20260910"), cfg["accept"].get("secondary_period", "day_20260911")
    dec = S["stage_a_decisions"]
    tuned, best, unc = S["tuned"], S["tuned_best"], S["unc"]
    nmN, nmD = S["noise_models"]["night"], S["noise_models"]["day"]

    def crow(pk, s, sub, m, ref, who="pooled"):
        r = comp[(comp.period == pk) & (comp.scheme == s) & (comp.subset == sub) & (comp.method == m) & (comp.ref == ref) & (comp.animal == who)]
        return r.iloc[0] if len(r) else None

    def med(pk, m, s, who="pooled", key="med"):
        d = summ.get(f"{pk}|{m}|{s}", {}).get(who)
        return d[key] if d else np.nan

    lines = []
    v0 = V.get(pk0, {})
    verdict = v0.get("verdict", "n/a")
    lines.append(f"# Head-IMU inertial fusion with WISER, V5 (cohort {cohort}): Stage-A attitude outside the filter + 16-Hz EKF/RTS — **{verdict}**\n")
    lines.append(f"- **Status:** pre-registered in [`implementation_plan/2026-10-01-wiser-ins-fusion-v5.md`](../../../../implementation_plan/2026-10-01-wiser-ins-fusion-v5.md) "
                 f"(user approval 2026-10-01 \"start v5\"; seven amendments written in §11 after tuning-only development runs, before any test period was read). "
                 f"Stage-A decisions frozen at {dec.get('frozen_local')}, Stage-B tuning frozen at {S['tuning_frozen_local']} (`tuned_frozen.json`) before the test periods were read; "
                 f"the verdict is evaluated once on the test night 2026-09-10/11.")
    lines.append(f"- **Follows:** attitude gate v2 ([change log](../../../../change_log/2026-10-01-imu-attitude-gate-v2.md)), V4 audit ([change log](../../../../change_log/2026-09-29-wiser-ins-fusion.md)), smoothing pilot ([change log](../../../../change_log/2026-09-29-wiser-imu-smoothing-pilot.md)).")
    lines.append(f"- **Run:** `python wiser/scripts/analyze_wiser_ins_fusion_v5.py --cohort {cohort}`; bulk `{out}`; config `{S['config']}` (`tuned`/`fitted` written by this run); "
                 f"git `{S['git_commit']}`; runtime {S['runtime_s'] / 60:.1f} min. Stage-A cache `{cfg['cache_roots']['attitude16']}` (+ README). Pointer `run_manifest_ins_fusion_v5_{cohort}.json`.")
    lines.append("- **Classification (regime-aware WISER):** measurement results only, on the unverified inch frame; held-out fixes contain WISER's own drift — a gain means better prediction of WISER, necessary but not sufficient for better head position.\n")
    # ---------------- headline
    lines.append("## 1. Headline\n")
    hl = []
    sch = v0.get("schemes", {})
    if sch:
        parts = []
        for s in cfg["accept"]["primary_schemes"]:
            d = sch[s]
            rb, rv = crow(pk0, s, "all", "V5", "B2p"), crow(pk0, s, "all", "V5", "V2")
            parts.append(f"{SCHEME_LABEL[s]}: pooled Δ vs B2′ {_ci(rb) if rb is not None else '—'}, vs V2 {_ci(rv) if rv is not None else '—'}; "
                         f"animals eligible (Δ ≥ 3 % vs both) with p ≤ 0.025: {d['n_animals_p_le_alpha']}/5; scheme p {d['p_scheme']:.3f} "
                         f"(Holm threshold {d.get('holm_threshold', float('nan')):.4f}) → primary {'PASS' if d['primary_pass'] else 'fail'}; "
                         f"control no-gain {d['n_control_no_gain']}/5; pooled moving Δ vs B2′ {_pct(d['pooled_moving_d'].get('B2p'))}, vs V2 {_pct(d['pooled_moving_d'].get('V2'))}")
        hl.append(f"**Verdict (pre-registered, test night): {verdict}.** " + " | ".join(parts) + ".")
    # stage A
    Lt = L[(L["role"] == "test") & L["in_analysis"].astype(bool)]
    Bt = B[(B["role"] == "test") & B["in_analysis"].astype(bool) & B["active"].astype(bool) & ~B["sat"].astype(bool)]

    def bmed(var, lab, col):
        g = Bt[(Bt["variant"] == var) & (Bt["dbin"] == lab)]
        return g[col].median() if len(g) else np.nan

    hl.append(f"**Stage A (IMU only) works where it is anchored, and only there.** Bias rule `{dec['rule']}` (tuning LWO medians: raw {_f(dec['lwo_tuning_median_deg']['raw'], 3)}°, "
              f"smoothed {_f(dec['lwo_tuning_median_deg']['smoothed'], 3)}°, A3 reference {_f(dec['lwo_tuning_median_deg']['a3'], 3)}°). Gate-v2 bout test on the test periods "
              f"(L1.0 set): A3 bias {_f(bmed('L1.0', '2-5 s', 'e_a3'))}° / {_f(bmed('L1.0', '5-15 s', 'e_a3'))}° (gate v2: 0.30° / 0.62°), Stage-A anchored bias "
              f"{_f(bmed('L1.0', '2-5 s', 'e_anch'))}° / {_f(bmed('L1.0', '5-15 s', 'e_anch'))}°; 15–40 s: {_f(bmed('L1.0', '15-40 s', 'e_a3'))}° → {_f(bmed('L1.0', '15-40 s', 'e_anch'))}°. "
              f"LWO tilt error at withheld test windows: median {_f(Lt[Lt.rule == dec['rule']]['err_deg'].median(), 3)}°. "
              f"But strict windows are rare at night: median time since a strict window on the test night "
              f"{_f(info[info.period == pk0]['tsw_p50'].median(), 0)} s (per-animal medians), and beyond ≈ 60 s the 2-Hz |f_xy| is dominated by gravity leakage "
              f"(test night median {_f(fx[(fx.period == pk0) & (fx.tsw_lo >= 300)]['fxy_median'].median())} m/s² at ≥ 300 s vs "
              f"{_f(fx[(fx.period == pk0) & (fx.tsw_hi <= 0.01 + 1e-9)]['fxy_median'].median(), 3)} inside windows; σθ law: g·sin(1.1774 σθ(300 s)) = "
              f"{_f(G * math.sin(math.radians(1.1774 * float(sigma_law(np.array([300.0]), cfg['stage_a']['sigma_law'])[0]))))} m/s²).")
    psi_t = psi[(psi.vis == "full") & (psi.imu == "true") & (~psi.mirror.astype(bool))]
    hl.append(f"**No usable yaw signal.** The ψ regression (visible fixes, IMU within 60 s of a strict window) gives resultants "
              f"{_f(psi_t['Rbar'].min(), 3)}–{_f(psi_t['Rbar'].max(), 3)} (median {_f(psi_t['Rbar'].median(), 3)}; 1 = consistent direction) on "
              f"{int(psi_t['n_pairs'].median())} pairs per animal-period (median); handedness votes on the tuning periods {S['handedness']['votes']} → frame "
              f"{S['handedness']['rule']}.")
    hl.append(f"**Tuning** (tuning night + day): σ_res {tuned['sig_res']} in/s², τ_b {tuned['tau_b']} s, T_max {tuned['t_max']} s, κ_cv {tuned['kappa_cv']}, "
              f"σ_v {tuned['sig_v']} in/s, σ_vr {tuned['sig_vr']} in/s → J {_f(best['J'], 3)} in, trimmed NIS {_f(best['nis'])} "
              f"(constraint [1.5, 3.0] {'met' if cfg['tuning']['nis_range'][0] <= best['nis'] <= cfg['tuning']['nis_range'][1] else 'NOT met — closest configuration'}). "
              f"Unconstrained J-minimiser (V5_unc): J {_f(unc['J'], 3)} in at NIS {_f(unc['nis'])}. Grid-edge flags: {', '.join(k for k, v in S['on_grid_edge'].items() if v) or 'none'}.")
    n_in = int(((T1.nis >= cfg["tuning"]["nis_range"][0]) & (T1.nis <= cfg["tuning"]["nis_range"][1])).sum())
    hl[-1] += (f" The NIS constraint was not binding: {n_in} of {len(T1)} configurations had trimmed NIS in range (all {_f(T1['nis'].min())}–{_f(T1['nis'].max())}), "
               f"so the constrained and unconstrained choices coincide{' (V5_unc = V5)' if all(str(unc[k]) == str(tuned[k]) for k in tuned) else ''}; "
               f"the 30 best configurations differ in J by < {_f(T1.sort_values('J')['J'].iloc[min(29, len(T1) - 1)] - T1['J'].min(), 3)} in.")
    rs = {s_: crow(pk0, s_, "all", "V5", "V5_shift") for s_ in ("s", "g05")}
    rsv = {s_: crow(pk0, s_, "all", "V5_shift", "V2") for s_ in ("s", "g05")}
    ri = {s_: crow(pk0, s_, "ins", "V5", "V2") for s_ in ("s", "g05")}
    rc = {s_: crow(pk0, s_, "cv", "V5", "V2") for s_ in ("s", "g05")}
    rst = {s_: crow(pk0, s_, "still", "V5", "V2") for s_ in ("s", "g05")}
    rmv = {s_: crow(pk0, s_, "moving", "V5", "V2") for s_ in ("s", "g05")}
    if rs["s"] is not None and ri["s"] is not None:
        hl.append(f"**Where V5 differs from V2 (test night, V5 vs V2, (s) / (g-0.5 s)):** INS-mode fixes {_pct(ri['s']['d_med'])} / {_pct(ri['g05']['d_med'])} "
                  f"(n {ri['s']['n']:,} / {ri['g05']['n']:,}), CV-mode fixes {_pct(rc['s']['d_med'])} / {_pct(rc['g05']['d_med'])}; IMU-still fixes "
                  f"{_pct(rst['s']['d_med'])} / {_pct(rst['g05']['d_med'])}, moving fixes {_pct(rmv['s']['d_med'])} / {_pct(rmv['g05']['d_med'])}. "
                  f"V5 vs its own +1 h control (amendment 8): {_ci(rs['s'])} / {_ci(rs['g05'])} — but the shifted IMU is actively harmful "
                  f"(V5 + 1 h vs V2 {_pct(rsv['s']['d_med'])} / {_pct(rsv['g05']['d_med'])}: a misaligned acceleration input in INS mode), so this contrast measures "
                  f"the damage a wrong IMU does, not information the right IMU adds.")
    nn = nis[nis.period == pk0]
    hl.append(f"**Consistency on the test night:** trimmed NIS {_f(nn['nis_trimmed_mean'].median())} (animals {_f(nn['nis_trimmed_mean'].min())}–{_f(nn['nis_trimmed_mean'].max())}), "
              f"fraction > 13.82 {_f(100 * nn['frac_gt_13.82'].median(), 1)} %; held-out z² mean on (s) {_f(nn['heldout_z2_mean_s'].median())}; INS mode on "
              f"{_f(100 * nn['ins_frac_nodes'].median(), 1)} % of fixes (median animal).")
    if pkd in V:
        vd = V[pkd]
        rb, rv = crow(pkd, "s", "all", "V5", "B2p"), crow(pkd, "s", "all", "V5", "V2")
        rg, rgv = crow(pkd, "g05", "all", "V5", "B2p"), crow(pkd, "g05", "all", "V5", "V2")
        rsd = {s_: crow(pkd, s_, "all", "V5", "V5_shift") for s_ in ("s", "g05")}
        rcd = {s_: crow(pkd, s_, "all", "V5_shift", "B2p") for s_ in ("s", "g05")}
        rstd = crow(pkd, "s", "still", "V5", "V2")
        rmvd = crow(pkd, "s", "moving", "V5", "V2")
        hl.append(f"**Test day (secondary, mostly sleep; INS mode on {_f(100 * nis[nis.period == pkd]['ins_frac_nodes'].median(), 0)} % of fixes):** V5 vs B2′ (s) {_ci(rb) if rb is not None else '—'}, "
                  f"(g-0.5 s) {_ci(rg) if rg is not None else '—'}; vs V2 {_ci(rv) if rv is not None else '—'} / {_ci(rgv) if rgv is not None else '—'} — real but below the 3 % "
                  f"threshold in every animal (the same rule would read {vd['verdict']}); the +1 h control also beats B2′ ({_pct(rcd['s']['d_med'])} / {_pct(rcd['g05']['d_med'])}, "
                  f"V5's non-inertial parts), V5 vs its control {_pct(rsd['s']['d_med'])} / {_pct(rsd['g05']['d_med'])}; the gain is on IMU-still fixes "
                  f"(vs V2 {_pct(rstd['d_med']) if rstd is not None else '—'}) and not on moving ones ({_pct(rmvd['d_med']) if rmvd is not None else '—'}).")
    for i, h in enumerate(hl, 1):
        lines.append(f"{i}. {h}")
    lines.append("")
    for f in figs:
        lines.append(f"![{f}](../figures/{f})\n")
    lines.append("## 2. Definitions\n")
    lines.append(DEFINITIONS)
    # ---------------- data
    lines.append("## 3. Data, regime context, Stage A\n")
    lines.append("| period | role | analysis window (field-PC local) |\n|---|---|---|")
    for pk, p in cfg["periods"].items():
        lines.append(f"| `{pk}` | {p['role']} | {p['start']} → {p['end']} |")
    lines.append("\nRegime context (gate-v2 report §3, field record): construction near the paddock from 09-08 ~07:50 (tuning day disturbed); SF08/SF12 test-night IMU from "
                 "21:02:45 / 21:05:18; no handling round, ADC window or implant loss inside the windows. Nights use the smoothing pilot's per-second IMU tables "
                 "(make_imu npz); days use cache-equivalent tables (SF12's 09-11 session has no make_imu npz).\n")
    lines.append(f"**Stage-A decisions (tuning only):** gyro scales {', '.join(f'{a} {s:.3f}' for a, s in dec['scales'].items())}; bias smoother (ML, tuning windows): "
                 + "; ".join(f"{ax}: q_b {p['qb']:.2e} (°/s)²/s, σ_r {p['sr']:.3f} °/s·s, σ_w {p['sw']:.4f} °/s·√s" for ax, p in dec["smoother"].items())
                 + f"; rule `{dec['rule']}`.\n")
    lines.append("| animal | period | strict windows | still min | quiet tilt check (°) | t_since p50 / p75 / p90 (s) |\n|---|---|---|---|---|---|")
    for _, r in info.iterrows():
        lines.append(f"| {r.animal} | {r.period} | {r.n_windows} | {_f(r.still_min, 1)} | {_f(r.tilt_check_deg, 3)} | {_f(r.tsw_p50, 0)} / {_f(r.tsw_p75, 0)} / {_f(r.tsw_p90, 0)} |")
    lines.append("\n**Horizontal specific force vs time since a strict window** (median over animals of the per-animal median |f_xy|, m/s²; share of samples):\n")
    lines.append("| t_since (s) | " + " | ".join(cfg["periods"].keys()) + " |\n|---|" + "---|" * len(cfg["periods"]))
    for lo_ in sorted(fx["tsw_lo"].unique()):
        cells = []
        for pk in cfg["periods"]:
            g = fx[(fx.period == pk) & (fx.tsw_lo == lo_)]
            cells.append(f"{_f(g['fxy_median'].median(), 3)} ({_f(100 * g['frac'].mean(), 0)} %)" if len(g) else "—")
        hi_ = fx[fx.tsw_lo == lo_]["tsw_hi"].iloc[0]
        lines.append(f"| {lo_:g}–{'∞' if hi_ > 1e8 else f'{hi_:g}'} | " + " | ".join(cells) + " |")
    lines.append(f"\nσθ law prediction of the leakage $g\\sin(1.1774\\sigma_\\theta)$: 60 s {_f(G * math.sin(math.radians(1.1774 * float(sigma_law(np.array([60.0]), cfg['stage_a']['sigma_law'])[0]))))} m/s², "
                 f"300 s {_f(G * math.sin(math.radians(1.1774 * float(sigma_law(np.array([300.0]), cfg['stage_a']['sigma_law'])[0]))))}, 1800 s "
                 f"{_f(G * math.sin(math.radians(min(90, 1.1774 * float(sigma_law(np.array([1800.0]), cfg['stage_a']['sigma_law'])[0])))))}.\n")
    lines.append("**Validation A2 — leave-window-out tilt error (median °, windows inside the analysis windows):**\n")
    Ls = L[L["in_analysis"].astype(bool)].copy()
    Ls["bin"] = pd.cut(Ls["t_since_last_kept_s"], [0, 2, 5, 10, 30, 60, 120, 300, 600, 1e9])
    lines.append("| role | rule | " + " | ".join(str(b) for b in Ls["bin"].cat.categories) + " | all (n) |\n|---|---|" + "---|" * (len(Ls["bin"].cat.categories) + 1))
    for (role, rule), g in Ls.groupby(["role", "rule"]):
        mm = g.groupby("bin", observed=False)["err_deg"].median()
        lines.append(f"| {role} | {rule} | " + " | ".join(_f(x, 3) for x in mm.values) + f" | {_f(g['err_deg'].median(), 3)} ({len(g)}) |")
    lines.append("\n**Validation A1 — gate-v2 bout test (active, no saturation, median °):**\n")
    lines.append("| role | set | bin | n | A3 bias (gate v2) | Stage A anchored | other rule |\n|---|---|---|---|---|---|---|")
    Bg = B[B["in_analysis"].astype(bool) & B["active"].astype(bool) & ~B["sat"].astype(bool)]
    for (role, var, lab), g in Bg.groupby(["role", "variant", "dbin"]):
        lines.append(f"| {role} | {var} | {lab} | {len(g)} | {_f(g['e_a3'].median(), 3)} | {_f(g['e_anch'].median(), 3)} | {_f(g['e_other'].median(), 3)} |")
    # ---------------- noise model
    lines.append("\n## 4. Measured WISER noise model (tuning, never tuned)\n")
    lines.append("| kind | drift state | σ_d x / y (in) | T_d (s) | slow share x / y | white SD at 9 / 8 / 7 anchors, x (in) | y (in) |\n|---|---|---|---|---|---|---|")
    for kind, nm in (("night", nmN), ("day", nmD)):
        lines.append(f"| {kind} | {'kept' if nm['drift_on'] else 'not kept'} | {_f(nm['sigma_d_x'])} / {_f(nm['sigma_d_y'])} | {_f(nm['T_d_s'], 1)} | "
                     f"{_f(nm['share_x'], 3)} / {_f(nm['share_y'], 3)} | " + " / ".join(_f(math.sqrt(nm['white_var'][str(a)]['x'])) for a in (9, 8, 7))
                     + " | " + " / ".join(_f(math.sqrt(nm['white_var'][str(a)]['y'])) for a in (9, 8, 7)) + " |")
    lines.append("\nVariogram (9-anchor fixes in still runs, in²): " + "; ".join(
        f"{kind}: " + ", ".join(f"{r['lag_s']:g} s {r['gamma_x']:.2f}/{r['gamma_y']:.2f}" for r in nm["variogram"]) for kind, nm in (("night", nmN), ("day", nmD)))
        + ". For comparison B2′ uses σ_b = 2.5 in (T_b 15 s) with white = max(σ² − σ_b², σ²/4) (pilot).\n")
    # ---------------- psi
    lines.append("## 5. Yaw offset ψ — regression and handedness\n")
    lines.append("| animal | period | pairs | n_eff | resultant R̄ (normal) | R̄ (mirrored) | ψ whole (°) | SE (°) | nodes with a local estimate |\n|---|---|---|---|---|---|---|---|---|")
    for _, r in psi_t.iterrows():
        rm = psi[(psi.vis == "full") & (psi.imu == "true") & psi.mirror.astype(bool) & (psi.animal == r.animal) & (psi.period == r.period)]
        lines.append(f"| {r.animal} | {r.period} | {r.n_pairs} | {_f(r.n_eff, 0)} | {_f(r.Rbar, 3)} | {_f(rm['Rbar'].iloc[0], 3) if len(rm) else '—'} | "
                     f"{_f(r.psi_whole_deg, 0)} | {_f(r.psi_whole_se_deg, 0)} | {_f(100 * r.frac_nodes_with_est, 1)} % |")
    psh = psi[(psi.vis == "s") & (psi.imu == "shift")]
    lines.append(f"\n+1 h-shifted IMU (scheme s visible fixes): R̄ median {_f(psh['Rbar'].median(), 3)} — the null level. Handedness (tuning votes): {S['handedness']['votes']} → {S['handedness']['rule']}.\n")
    hd = nis[nis.period.isin([pk0, pkd])][["animal", "period", "llr_per_fix"]]
    lines.append("Handedness LLR on the test periods (forward pass 0, per fix, + = normal frame fits better): " + ", ".join(
        f"{r.period[:5]} {r.animal} {r.llr_per_fix:+.4f}" for r in hd.itertuples()) + ".\n")
    # ---------------- tuning
    lines.append("## 6. Tuning (tuning night + tuning day only)\n")
    lines.append(f"Objective J = pooled held-out RMSE over the scored fixes of (s) and (g-0.5 s), both tuning periods; constraint trimmed NIS ∈ {cfg['tuning']['nis_range']}. "
                 f"{len(T1)} configurations evaluated. Best ten by J among those meeting the constraint (or all if none):\n")
    Tc = T1[(T1.nis >= cfg["tuning"]["nis_range"][0]) & (T1.nis <= cfg["tuning"]["nis_range"][1])]
    Tshow = (Tc if len(Tc) else T1).sort_values("J").head(10)
    cols = ["sig_res", "tau_b", "t_max", "kappa_cv", "sig_v", "sig_vr", "J", "nis", "nis_untrimmed", "frac_gt_13.82"]
    lines.append("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    for _, r in Tshow.iterrows():
        lines.append("| " + " | ".join(_f(r[c], 4) if c in ("J", "nis", "nis_untrimmed", "frac_gt_13.82") else str(r[c]) for c in cols) + " |")
    lines.append(f"\nNIS range of all configurations: {_f(T1['nis'].min())}–{_f(T1['nis'].max())}; configurations meeting the constraint: {len(Tc)} of {len(T1)}. "
                 f"Selected: {tuned} (J {_f(best['J'], 4)}, NIS {_f(best['nis'])}); V5_unc: { {k: unc[k] for k in tuned} } (J {_f(unc['J'], 4)}, NIS {_f(unc['nis'])}).\n")
    # ---------------- test night
    for pk, title in ((pk0, "7. Test night 2026-09-10/11 (primary)"), (pkd, "8. Test day 2026-09-11 (secondary)"),
                      ("night_20260908", "9a. Tuning night 2026-09-08/09 (in-sample for V5's scalars)"), ("day_20260908", "9b. Tuning day 2026-09-08 (in-sample)")):
        if not any(k.startswith(pk + "|") for k in summ):
            continue
        lines.append(f"## {title}\n")
        lines.append("Pooled held-out error (median / RMSE / fraction > 24 in, in) and Δ vs B2′ and vs V2 (95 % CI):\n")
        lines.append("| method | " + " | ".join(SCHEME_LABEL[s] for s in SCHEMES) + " |\n|---|" + "---|" * len(SCHEMES))
        for m in ("B1", "B2", "B2p", "V1", "V2", "V5", "V5_shift", "V5_p90", "V5_unc"):
            cells = []
            for s in SCHEMES:
                txt = f"{_f(med(pk, m, s))} / {_f(med(pk, m, s, key='rmse'))} / {_f(100 * med(pk, m, s, key='frac_gt24'), 2)}%"
                if m != "B2p":
                    rb = crow(pk, s, "all", m, "B2p")
                    if rb is not None:
                        txt += f"<br>vs B2′ {_ci(rb)}"
                if m.startswith("V5"):
                    rv = crow(pk, s, "all", m, "V2")
                    if rv is not None:
                        txt += f"<br>vs V2 {_ci(rv)}"
                cells.append(txt)
            lines.append(f"| {LABEL.get(m, m)} | " + " | ".join(cells) + " |")
        lines.append("\nPer animal, primary schemes (Δ of V5; control = V5 IMU + 1 h vs B2′):\n")
        lines.append("| animal | scheme | n | V5 vs B2′ | p | V5 vs V2 | p | control vs B2′ | V2 vs B2′ |\n|---|---|---|---|---|---|---|---|---|")
        for s in cfg["accept"]["primary_schemes"] + ["g10", "a", "a2"]:
            for a in animals + ["pooled"]:
                rb, rv, rc, r2 = crow(pk, s, "all", "V5", "B2p", a), crow(pk, s, "all", "V5", "V2", a), crow(pk, s, "all", "V5_shift", "B2p", a), crow(pk, s, "all", "V2", "B2p", a)
                if rb is None:
                    continue
                lines.append(f"| {a} | {s} | {rb['n']} | {_ci(rb)} | {_f(rb['p_one'], 3)} | {_ci(rv) if rv is not None else '—'} | {_f(rv['p_one'], 3) if rv is not None else '—'} | "
                             f"{_ci(rc) if rc is not None else '—'} | {_ci(r2) if r2 is not None else '—'} |")
        lines.append("\nBy subset (pooled, V5 vs B2′ / V5 vs V2):\n")
        lines.append("| scheme | " + " | ".join(["all", "still", "moving", "loco", "INS mode", "CV mode"]) + " |\n|---|" + "---|" * 6)
        for s in SCHEMES:
            cells = []
            for sub in ("all", "still", "moving", "loco", "ins", "cv"):
                rb, rv = crow(pk, s, sub, "V5", "B2p"), crow(pk, s, sub, "V5", "V2")
                cells.append(f"{_pct(rb['d_med']) if rb is not None else '—'} / {_pct(rv['d_med']) if rv is not None else '—'} (n {rb['n'] if rb is not None else 0})")
            lines.append(f"| {s} | " + " | ".join(cells) + " |")
        if pk in V:
            vv = V[pk]
            lines.append(f"\nRule applied ({'verdict' if pk == pk0 else 'information only'}): **{vv['verdict']}**; Holm order {vv['holm_order']}; " + "; ".join(
                f"{s}: p per animal {', '.join(f'{a} {p:.3f}' for a, p in d['p_animal'].items())}, scheme p {d['p_scheme']:.3f}" for s, d in vv["schemes"].items()) + ".\n")
        nn = nis[nis.period == pk]
        lines.append("| animal | trimmed NIS | NIS mean | frac > 5.99 | frac > 13.82 | held-out z² mean (s) / (g05) | frac z² > 5.99 (s) | INS nodes | LLR/fix |\n|---|---|---|---|---|---|---|---|---|")
        for _, r in nn.iterrows():
            lines.append(f"| {r.animal} | {_f(r.nis_trimmed_mean)} | {_f(r.nis_mean)} | {_f(r['frac_gt_5.99'], 3)} | {_f(r['frac_gt_13.82'], 3)} | "
                         f"{_f(r.heldout_z2_mean_s)} / {_f(r.heldout_z2_mean_g05)} | {_f(r['heldout_frac_gt_5.99_s'], 3)} | {_f(r.ins_frac_nodes, 3)} | {r.llr_per_fix:+.4f} |")
        pp = plaus[plaus.period == pk]
        if len(pp):
            lines.append("\nPlausibility of the full-data position tracks (median over animals): " + "; ".join(
                f"{m}: v p50/p95/p99 {_f(g['v_p50'].median(), 1)}/{_f(g['v_p95'].median(), 1)}/{_f(g['v_p99'].median(), 1)} in/s, a p99 {_f(g['a_p99'].median(), 0)} in/s², "
                f"path {_f(g['path_in_per_h'].median(), 0)} in/h, wall-out {_f(100 * g['wall_out_frac'].median(), 3)} %" for m, g in pp.groupby("method")) + ".\n")
        lines.append("Tails (pooled, scheme s): " + "; ".join(f"{m} max {_f(med(pk, m, 's', key='max'), 1)} in, > 100 in {_f(100 * med(pk, m, 's', key='frac_gt100'), 3)} %"
                                                       for m in ("B2p", "V2", "V5", "V5_shift")) + ".\n")
    # ---------------- interpretation, caveats, deviations, verification
    lines.append("## 10. What limits V5 (interpretation of the measurements above)\n")
    lines.append("- The fixes of V4's audit are in place: attitude outside the filter, no dynamic gravity pull, no tilt resets, gate-v2 gyro scales, the bias re-anchored at every strict window, "
                 "2-Hz low-pass before integration, measured WISER noise, NIS-constrained tuning, single-fix and short-gap schemes.")
    lines.append("- Stage A is accurate near strict windows (LWO and bout tests), but strict windows are stillness: at night they are minutes to hours apart while the animal is active, and the "
                 "unaided tilt then drifts to tens of degrees (the |f_xy| table), far beyond the gate-v2 clock-time law, which was fitted on ≤ 10-min chains dominated by day records.")
    lines.append("- Where the attitude is good the head barely translates; where the head translates the attitude is poor. Consistently, the yaw regression finds no consistent "
                 "direction between IMU and WISER velocity changes, so ψ — and with it the direction of any inertial acceleration — is unobservable, and the INS mode can at best leave V2-like smoothing intact.")
    lines.append(f"- Tuning confirmed it: the selected $T_{{max}}$ = {tuned['t_max']} s (grid minimum) uses the inertial acceleration only within {tuned['t_max']} s of a strict "
                 f"window — {_f(100 * nis[nis.period == pk0]['ins_frac_nodes'].median(), 0)} % of test-night fixes (median animal), "
                 f"{_f(100 * nis[nis.period == pkd]['ins_frac_nodes'].median(), 0) if pkd in set(nis.period) else '—'} % on the test day — and the "
                 f"CV fallback at κ_cv = {tuned['kappa_cv']} (grid maximum) is ten times V2's process noise, chosen by the RMSE objective.")
    ev = pd.read_csv(csv / "heldout_errors_all.csv.gz", usecols=["period", "method", "scheme", "still", "moving", "loco", "ins"])
    ev = ev[(ev.period == pk0) & (ev.method == "V5") & (ev.scheme == "s")]
    ins_ = ev[ev["ins"]]
    rlo = {s_: crow(pk0, s_, "loco", "V5", "V2") for s_ in ("s", "g05")}
    lines.append(f"- Inside INS mode V5 beats V2 by ≈ 1.5–2 % on the test night, but {_f(100 * ins_['still'].mean(), 0)} % of those fixes are IMU-still (strict windows are stillness) "
                 f"and only {_f(100 * ev[ev['loco']]['ins'].mean(), 1)} % of locomoting / {_f(100 * ev[ev['moving']]['ins'].mean(), 1)} % of moving fixes fall in INS mode: "
                 f"the IMU helps by certifying that the head is not accelerating — the information V1/V2 already use — not by bridging motion. The small locomotion "
                 f"difference vs V2 ((s) {_ci(rlo['s'])}, (g-0.5 s) {_ci(rlo['g05'])}) arises in CV mode (κ_cv), not from inertial data.")
    lines.append("- The measured WISER noise model (night: no drift state kept — slow share 9.7 % / 4.7 % below the 10 % rule — so the white variance is the robust total static "
                 "variance; day: a 0.46/0.72-in drift kept) is honest but gives up the 'flexible low-frequency term' that B2′'s σ_b = 2.5 in provides; together with κ_cv this is why "
                 "V5 in CV mode is ≈ 0.5–0.8 % worse than V2 on held-out medians (by-mode table).")
    cv2 = comp[(comp.subset == "all") & (comp.method == "V5") & (comp.ref == "V2") & (comp.animal != "pooled") & comp.period.isin([pk0, pkd])]
    cvp = cv2[cv2.scheme.isin(cfg["accept"]["primary_schemes"])]
    mx = cv2.loc[cv2["d_med"].idxmax()] if len(cv2) else None
    lines.append(f"- The verdict would not change with a looser reading: no animal reaches Δ ≥ 3 % against V2 on (s) or (g-0.5 s), night or day (largest "
                 f"{_pct(cvp['d_med'].max())}); over all schemes and both test periods the largest per-animal Δ vs V2 is {_pct(mx['d_med']) if mx is not None else '—'} "
                 f"({mx['animal'] if mx is not None else ''}, {mx['period'] if mx is not None else ''}, {mx['scheme'] if mx is not None else ''}).\n")
    lines.append("## 11. Caveats, deviations, verification\n")
    lines.append("- One test night (regime B) and one test day; five animals; WISER frame unverified; held-out targets include WISER's own drift.")
    lines.append("- Day per-second IMU tables are cache-equivalent (not make_imu), the day control is a circular +1 h shift; SF12's 09-11 session is field-flagged for its neural connector only.")
    lines.append("- The σθ law is used as specified (real-time, t since the last window); the run shows it understates night errors beyond ≈ 1 min (report §3).")
    lines.append("- **Deviations:** plan §11 amendments 1–7 (written before any test period was read): ML-fitted anchor smoother evidence; ψ regression restricted to usable pairs "
                 "within 60 s of a strict window with a proper standard error; ψ process noise following the clock-time law; κ_cv added to the tuned scalars (on the SF09 "
                 "development night the NIS constraint was only reachable by a degenerate configuration; pooled over all tuning animal-periods it turned out not to be binding); "
                 "V5_unc secondary; handedness tie rule; V5 vs V5 (+1 h) secondary (amendment 8). Ties in the tuning stages were resolved by the registered rule "
                 "(larger σ_res, then smaller T_max, then grid order); the tied configurations differ in J by < 0.001 in. Days: cache-equivalent per-second tables "
                 "and circular control (plan §1/§4).")
    lines.append(f"- **Verification:** `--selftest` (synthetic) — see the change log; Stage-A selection and Stage-B tuning frozen before the test periods were read (log + "
                 f"`stage_a_decisions.json`, `tuned_frozen.json`); the pilot baselines are recomputed with the pilot's code and tuned values (B2′ (a) test-night pooled median "
                 f"{_f(med(pk0, 'B2p', 'a'), 3)} in; pilot 3.93); no raw file, existing cache or existing script was modified; the WISER fixes come from the A2 cache; "
                 f"no images were opened; not committed.")
    rp = rdir / f"{STEM}_{cohort}.md"
    rp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rp


def finish(out: Path, S: dict, cfg: dict, fh=None) -> None:
    cohort = S["cohort"]
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(out, S, cfg, fdir, cohort)
    (out / "figures").mkdir(exist_ok=True)
    for f in figs:
        shutil.copy2(fdir / f, out / "figures" / f)
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rp = write_report(out, S, cfg, figs, rdir, cohort)
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rp.name, "driver": "wiser/scripts/analyze_wiser_ins_fusion_v5.py",
            "config": S["config"], "git_commit": S["git_commit"], "runtime_s": S["runtime_s"], "caches": cfg["cache_roots"],
            "verdict_test_night": S["verdicts"].get(cfg["accept"].get("primary_period", "night_20260910"), {}).get("verdict"), "tuned": S["tuned"], "figures": figs}
    output_paths.write_run_manifest(out, out, **meta)
    (rdir / f"run_manifest_ins_fusion_v5_{cohort}.json").write_text(json.dumps({"run_dir": str(out), **meta}, indent=2, ensure_ascii=False, default=_jd), encoding="utf-8")
    log(f"report {rp}; figures {figs}", fh)


# ====================================================================================================== selftest
def _qz(a):
    return np.column_stack([np.cos(a / 2), np.zeros_like(a), np.zeros_like(a), np.sin(a / 2)])


def _qy(a):
    return np.column_stack([np.cos(a / 2), np.zeros_like(a), np.sin(a / 2), np.zeros_like(a)])


def _qx(a):
    return np.column_stack([np.cos(a / 2), np.sin(a / 2), np.zeros_like(a), np.zeros_like(a)])


def _qmul_np(a, b):
    w1, x1, y1, z1 = a.T
    w2, x2, y2, z2 = b.T
    return np.column_stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def synth_session(seed: int = 7, dur_s: float = 1500.0, psi_true_deg: float = 0.0) -> dict:
    """Synthetic head track: still bouts, locomotion bouts and 'grooming' bouts (stationary body, 6-Hz head rotation +
    translation); IMU with a gyro bias drifting linearly in clock time; WISER fixes at ~3.7 Hz with anchor-dependent white
    noise + an AR(1) drift."""
    rng = np.random.default_rng(seed)
    fs = 100.0
    n = int(dur_s * fs)
    t = np.arange(n) / fs
    kind = np.zeros(n, np.int8)                    # 0 still, 1 locomotion, 2 grooming
    vel = np.zeros((n, 2))
    head_yaw = np.zeros(n)
    cur, yaw = 0, rng.uniform(-math.pi, math.pi)
    while cur < n:
        for k_, (lo_, hi_) in ((0, (20, 40)), (1, (6, 12)), (0, (15, 30)), (2, (8, 14)), (1, (5, 10))):
            L = int(rng.uniform(lo_, hi_) * fs)
            seg = slice(cur, min(n, cur + L))
            m = seg.stop - seg.start
            if m <= 0:
                break
            kind[seg] = k_
            if k_ == 1:
                tau = np.arange(m) / m
                vmax = rng.uniform(15, 30)
                turn = np.radians(rng.uniform(-25, 25))
                hd = yaw + turn * np.arange(m) / fs
                sp = vmax * np.sin(np.pi * tau) ** 2
                vel[seg] = np.column_stack([sp * np.cos(hd), sp * np.sin(hd)])
                head_yaw[seg] = hd
                yaw = hd[-1]
            else:
                head_yaw[seg] = yaw
            cur += m
    body = np.cumsum(vel, axis=0) / fs + np.array([200.0, 100.0])
    groom = kind == 2
    osc = np.sin(2 * np.pi * 6.0 * t)
    env = uniform_filter1d((kind != 0).astype(float), 200, mode="nearest")      # still bouts are truly still (no slow tilt)
    pitch = np.radians(5.0 * np.sin(2 * np.pi * 0.05 * t) * env + 12.0 * osc * groom)
    roll = np.radians(3.0 * np.sin(2 * np.pi * 0.07 * t) * env)
    head_off = 3.0 + 0.3 * osc * groom
    head = body + np.column_stack([head_off * np.cos(head_yaw), head_off * np.sin(head_yaw)])
    q = _qmul_np(_qmul_np(_qz(head_yaw), _qy(pitch)), _qx(roll))
    # body-frame angular velocity from successive quaternions
    qc = q * np.array([1, -1, -1, -1])
    dq = _qmul_np(qc[:-1], q[1:])
    om = 2.0 * dq[:, 1:] * np.sign(dq[:, :1]) * fs
    om = np.vstack([om, om[-1:]])
    acc_w = np.zeros((n, 3))
    acc_w[:, :2] = np.gradient(np.gradient(head, axis=0), axis=0) * fs * fs / IN_PER_M
    f_w = acc_w + np.array([0, 0, G])
    a_h = P0.rotate_world(q * np.array([1, -1, -1, -1]), f_w) + rng.normal(0, 0.02, (n, 3))
    b0 = np.array([0.3, -0.2, 0.15])
    rate = np.array([0.04, -0.03, 0.05]) / 1000.0           # deg/s per s
    bias = b0 + np.outer(t, rate)
    w = om * R2D + bias + rng.normal(0, 0.3, (n, 3))
    # WISER fixes (true frame = Stage A frame rotated by psi_true)
    tf = np.cumsum(rng.uniform(0.2, 0.35, int(dur_s / 0.2)))
    tf = tf[tf < dur_s - 1]
    A = rng.choice([7, 8, 9], size=len(tf), p=[0.15, 0.30, 0.55])
    sd = {7: (2.3, 3.2), 8: (1.7, 3.0), 9: (1.4, 2.5)}
    ps_ = np.radians(psi_true_deg)
    Rz = np.array([[math.cos(ps_), -math.sin(ps_)], [math.sin(ps_), math.cos(ps_)]])
    hx = np.column_stack([np.interp(tf, t, head[:, j]) for j in range(2)]) @ Rz.T
    bx = np.column_stack([np.interp(tf, t, body[:, j]) for j in range(2)]) @ Rz.T
    drift = np.zeros((len(tf), 2))
    for j in range(1, len(tf)):
        ph = math.exp(-(tf[j] - tf[j - 1]) / 10.0)
        drift[j] = ph * drift[j - 1] + math.sqrt(1 - ph * ph) * 0.6 * rng.normal(size=2)
    noise = np.column_stack([rng.normal(0, [sd[a_][0] for a_ in A]), rng.normal(0, [sd[a_][1] for a_ in A])])
    z = hx + drift + noise
    return {"t": t, "acc": a_h, "w": w, "bias": bias, "q": q, "kind": kind, "head": head, "body": body, "tf": tf, "A": A, "z": z,
            "z_true_head": hx, "z_true_body": bx, "drift": drift, "psi_true": ps_}


def synth_stage_a(sy: dict, gcfg: dict, cfg: dict, spar: dict | None = None, rule: str = "smoothed") -> dict:
    """Stage A on a synthetic session with the production helpers (strict windows, anchors, attitude, 16-Hz products)."""
    n = len(sy["t"])
    acc, w = sy["acc"], sy["w"]
    valid = np.ones(n, bool)
    om_a3 = np.linalg.norm(w - sy["bias"][0], axis=1)
    win = GV2.detect_strict(acc, om_a3, valid, gcfg, 1.0)
    s, e = win[:, 0], win[:, 1]
    c = (s + e) // 2
    cs = np.vstack([np.zeros((1, 3)), np.cumsum(w, axis=0)])
    bhat = (cs[e] - cs[s]) / (e - s)[:, None]
    csa = np.vstack([np.zeros((1, 3)), np.cumsum(acc, axis=0)])
    gw = csa[e] - csa[s]
    gw /= np.linalg.norm(gw, axis=1, keepdims=True)
    Wt = pd.DataFrame({"animal": "SYN", "period": "syn", "role": "tuning", "kind": "day", "s": s, "e": e, "c": c, "dur_s": (e - s) / FS100,
                       "t_c_ms": sy["t"][c] * 1000.0, "t_c_s": sy["t"][c], "in_analysis": True, "g_x": gw[:, 0], "g_y": gw[:, 1], "g_z": gw[:, 2],
                       "bhat_x": bhat[:, 0], "bhat_y": bhat[:, 1], "bhat_z": bhat[:, 2]})
    clip = float(cfg["stage_a"]["smoother_nu_clip"])
    if spar is None:
        spar = fit_bias_smoother(Wt, clip)
    anch = anchor_biases(Wt["t_c_s"].to_numpy(), bhat, Wt["dur_s"].to_numpy(), rule, spar, clip)
    bser = bias_series(n, c, anch)
    q, clos = run_attitude((w - bser) * D2R, valid, c, gw)
    f_w = P0.rotate_world(q, acc)
    f_w[:, 2] -= G
    tsw = t_since_windows(n, s, e)
    n16 = int(math.ceil(n * 4 / 25))
    centers = 6.25 * np.arange(n16)
    near = np.clip(np.round(centers).astype(int), 0, n - 1)
    sos = signal.butter(4, 2.0, fs=FS100, output="sos")
    d16 = signal.resample_poly(signal.sosfiltfilt(sos, f_w, axis=0), 4, 25, axis=0)[:n16]
    stA = {"t_unix_ms": np.interp(centers, np.arange(n), sy["t"] * 1000.0), "f_xy_2hz": d16[:, :2], "t_since_win_s": tsw[near],
           "ok": np.ones(n16, bool), "shake": np.zeros(n16, bool)}
    wn = np.linalg.norm(w - bser, axis=1)
    for lo_, hi_ in cfg["stage_a"]["band_powers_hz"]:
        sosb = signal.butter(4, [float(lo_), float(hi_)], btype="bandpass", fs=FS100, output="sos")
        bp = signal.sosfiltfilt(sosb, wn)
        stA[f"bp_w_{int(lo_)}_{int(hi_)}"] = uniform_filter1d(bp * bp, 50, mode="nearest")[near]
    lwo = lwo_eval(w, w - sy["bias"][0], valid, Wt, 1.0, rule, spar, clip)
    return {"stA": stA, "W": Wt, "anch": anch, "spar": spar, "q": q, "lwo": lwo, "bser": bser, "clos": clos}


def selftest() -> int:
    t_all = time.time()
    set_num_threads(min(8, os.cpu_count() or 4))
    cfg = load_cfg("2026c")
    gcfg, _ = GV2.load_cfg("2026c")
    scfg = json.loads((REPO / cfg["smoothing_config"]).read_text(encoding="utf-8"))
    ptuned = scfg["tuned"]
    table = {int(k): v for k, v in ptuned["anchor_sigma"].items()}
    res = []

    def check(name, ok, detail):
        res.append((name, bool(ok), detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    sy = synth_session(seed=7, psi_true_deg=35.0)
    SA = synth_stage_a(sy, gcfg, cfg)
    Wt = SA["W"]
    tb = sy["bias"][Wt["c"].to_numpy()]
    err_b = np.abs(SA["anch"] - tb).max(axis=1)
    drift_tot = float(np.abs(sy["bias"][-1] - sy["bias"][0]).max())
    check("1 Stage A recovers the linear gyro-bias drift", np.median(err_b) < 0.2 * drift_tot,
          f"{len(Wt)} strict windows; median |anchor - true bias| {np.median(err_b):.4f} deg/s vs total drift {drift_tot:.4f} deg/s")
    lw = SA["lwo"]
    check("1b withheld-window tilt error small", len(lw) and lw["err_deg"].median() < 0.5, f"LWO median {lw['err_deg'].median():.3f} deg (n {len(lw)})")
    # ---------------- Track + per-second tables
    t0_ms = 1.7e12
    lo, hi = t0_ms, t0_ms + 1500e3
    fx = pd.DataFrame({"t_ms": t0_ms + sy["tf"] * 1000.0, "x": sy["z"][:, 0], "y": sy["z"][:, 1], "anchors_used": sy["A"]})
    secs = np.arange(int(lo // 1000), int(hi // 1000), dtype=np.int64)
    ksec = np.clip(((secs * 1000 - t0_ms) / 10).astype(int), 0, len(sy["kind"]) - 1)
    kind_s = np.array([np.bincount(sy["kind"][max(0, k - 50):k + 100], minlength=3).argmax() for k in ksec])
    ps = pd.DataFrame({"sec": secs, "ok": True, "still": kind_s == 0, "vedba_1s": np.where(kind_s == 1, 5.0, np.where(kind_s == 2, 1.0, 0.01)),
                       "sbf": np.where(kind_s == 1, 0.3, 0.0)})
    stA = SA["stA"]
    stA["t_unix_ms"] = stA["t_unix_ms"] + t0_ms
    ps_s = circular_shift_table(ps)
    tr = P.Track(fx, lo, hi, 0.0)
    tr.attach_imu(ps, ps_s, 3.93, 0.1)
    tr.ps_shift = ps_s
    tg, grids = make_grids(stA, lo, hi, "day", tr, cfg)
    # ---------------- noise model: dedicated static synthetic (40 still runs of 150 s, planted nugget + AR(1) drift)
    rng_n = np.random.default_rng(5)
    tf = np.cumsum(rng_n.uniform(0.2, 0.35, 30000))
    tf = tf[tf < 6000]
    An = rng_n.choice([7, 8, 9], size=len(tf), p=[0.15, 0.30, 0.55])
    sdn = {7: (2.3, 3.2), 8: (1.7, 3.0), 9: (1.4, 2.5)}
    dr = np.zeros((len(tf), 2))
    for j in range(1, len(tf)):
        ph = math.exp(-(tf[j] - tf[j - 1]) / 10.0)
        dr[j] = ph * dr[j - 1] + math.sqrt(1 - ph * ph) * np.array([0.6, 0.9]) * rng_n.normal(size=2)
    zn = dr + np.column_stack([rng_n.normal(0, [sdn[a_][0] for a_ in An]), rng_n.normal(0, [sdn[a_][1] for a_ in An])]) + 100.0
    fxn = pd.DataFrame({"t_ms": t0_ms + tf * 1000.0, "x": zn[:, 0], "y": zn[:, 1], "anchors_used": An})
    secs_n = np.arange(int(t0_ms // 1000), int(t0_ms // 1000) + 6000, dtype=np.int64)
    psn = pd.DataFrame({"sec": secs_n, "ok": True, "still": (np.arange(6000) % 150) != 149})
    trn = P.Track(fxn, t0_ms, t0_ms + 6000e3, 0.0)
    nm_s = measure_noise([(trn, psn)], cfg["noise_model"], 1)
    w9x, w9y = math.sqrt(nm_s["white_var"]["9"]["x"]), math.sqrt(nm_s["white_var"]["9"]["y"])
    check("8 noise model recovers the planted nugget and drift", abs(w9x - 1.4) < 0.2 and abs(w9y - 2.5) < 0.3 and nm_s["drift_on"]
          and abs(nm_s["sigma_d_x"] - 0.6) < 0.25 and abs(nm_s["sigma_d_y"] - 0.9) < 0.35 and 4 < nm_s["T_d_s"] < 25,
          f"white SD at 9 anchors {w9x:.2f}/{w9y:.2f} (planted 1.4/2.5), drift {'on' if nm_s['drift_on'] else 'off'} sigma_d {nm_s['sigma_d_x']:.2f}/{nm_s['sigma_d_y']:.2f} "
          f"(planted 0.6/0.9), T_d {nm_s['T_d_s']:.1f} s (planted 10)")
    nm = measure_noise([(tr, ps)], {**cfg["noise_model"], "min_run_s": 15}, 1)
    if not nm["drift_on"]:
        nm = {**nm_s, "white_var": nm_s["white_var"]}
    # ---------------- psi regression + handedness
    r2p = P.r2_from_anchors(tr.A, table)
    C_ = {"tr": tr, "tg": tg, "grids": grids, "hid": make_schemes(tr, {**cfg, "periods": {"syn": {"index": 9}},
                                                                         "schemes": {**cfg["schemes"], "a_seed_offsets": {"syn": 0}}}, "syn", 0, 99),
          "zf": {w_: node_flags(tr, tg, grids[w_], w_) for w_ in ("true", "shift")}, "r2p": r2p, "psi": {}}
    pn = get_psi(C_, cfg, "full", "true", False)
    pm = get_psi(C_, cfg, "full", "true", True)
    a_true = np.column_stack([np.interp(tg, sy["t"], np.gradient(np.gradient(sy["head"][:, j])) * 1e4) for j in range(2)])
    ok = np.hypot(*grids["true"]["f"].T) > 5
    c_emp = ((a_true[ok, 0] + 1j * a_true[ok, 1]) * np.conj(grids["true"]["f"][ok, 0] + 1j * grids["true"]["f"][ok, 1])).sum()
    psi_emp = float(np.angle(c_emp)) + sy["psi_true"]
    dpsi = abs(_wrap(pn["psi_whole"] - psi_emp)) * R2D
    check("6 psi regression recovers the yaw offset and the handedness", dpsi < 10 and pn["Rbar"] > pm["Rbar"],
          f"psi_hat {pn['psi_whole'] * R2D:.1f} deg vs truth {psi_emp * R2D:.1f} (|d| {dpsi:.1f}); Rbar normal {pn['Rbar']:.3f} > mirrored {pm['Rbar']:.3f}")
    # ---------------- V5 vs B2, control, NIS
    conf = {"sig_res": 8.0, "tau_b": 5.0, "t_max": 60.0, "sig_v": 0.25, "sig_vr": 1.0, "kappa_cv": 1.0}
    specs = [{"conf": conf, "vis_key": v, "which": w_} for v in ("s", "g05", "full") for w_ in ("true", "shift")]
    outs = run_spec(C_, cfg, specs, True, nm, False)
    O = {(s_["vis_key"], s_["which"]): o for s_, o in zip(specs, outs)}
    tr.ok_both = np.ones(tr.n, bool)
    preds = P.predict_all(tr, table, ptuned, {k: C_["hid"][k] for k in ("s", "g05")}, methods=("B2", "B2p"))
    ok_all = True
    det = []
    for s_ in ("s", "g05"):
        sc = C_["hid"][s_] & (tr.A >= 7)
        e5 = np.hypot(*(tr.z[sc] - O[(s_, "true")]["zhat"][sc]).T)
        e5s = np.hypot(*(tr.z[sc] - O[(s_, "shift")]["zhat"][sc]).T)
        eb = np.hypot(*(tr.z[sc] - preds[("B2", s_)][sc]).T)
        mov = (sy["kind"][np.clip((tr.t * 100).astype(int), 0, len(sy["kind"]) - 1)] == 1)[sc]
        gain = 1 - np.sqrt(np.mean(e5[mov] ** 2)) / np.sqrt(np.mean(eb[mov] ** 2))
        gain_s = 1 - np.sqrt(np.mean(e5s[mov] ** 2)) / np.sqrt(np.mean(eb[mov] ** 2))
        gmed = 1 - np.median(e5) / np.median(eb)
        gmed_s = 1 - np.median(e5s) / np.median(eb)
        ok_all &= (gain > 0.05) and (gmed > 0.0)
        det.append(f"{s_}: median V5 {np.median(e5):.2f} vs B2 {np.median(eb):.2f} in (d {100 * gmed:+.1f} %), RMSE on locomotion fixes d {100 * gain:+.1f} %; "
                   f"shifted control d median {100 * gmed_s:+.1f} %, locomotion RMSE {100 * gain_s:+.1f} %")
        res.append((f"_ctrl_{s_}", gmed_s, gain_s))
    check("3 V5 beats B2 on (s) and (g-0.5 s)", ok_all, "; ".join(det))
    ctrl_ok = all(r[1] < 0.02 and r[2] < 0.05 for r in res if r[0].startswith("_ctrl_"))
    check("4 the shifted control gives no gain", ctrl_ok, ", ".join(f"{r[0][6:]} dmed {100 * r[1]:+.1f} %, loco RMSE {100 * r[2]:+.1f} %" for r in res if r[0].startswith("_ctrl_")))
    res[:] = [r for r in res if not r[0].startswith("_ctrl_")]
    nis = O[("full", "true")]["nis"]
    v = nis[np.isfinite(nis) & (tr.A >= 7)]
    nt = float(np.mean(v[v <= 13.8155]))
    check("5 NIS ~ 2 on synthetic data", 1.5 <= nt <= 3.0, f"trimmed NIS {nt:.2f}, untrimmed {np.mean(v):.2f}, frac > 13.82 {np.mean(v > 13.8155):.4f}")
    # ---------------- oscillation on a stationary body
    full = O[("full", "true")]
    kf = sy["kind"][np.clip((tr.t * 100).astype(int), 0, len(sy["kind"]) - 1)]
    eb_ = np.hypot(*(full["p"] - sy["z_true_head"]).T)
    groom, still = kf == 2, kf == 0
    r_g, r_s = float(np.sqrt(np.mean(eb_[groom] ** 2))), float(np.sqrt(np.mean(eb_[still] ** 2)))
    zf = C_["zf"]["true"]
    check("2 2-Hz low-pass + body-stationary ZUPT keep the 6-Hz oscillation from moving the position", r_g < 1.5 * r_s + 0.5,
          f"position RMSE vs truth: grooming bouts {r_g:.2f} in, still bouts {r_s:.2f} in; rhythmic ZUPT flags on {np.mean(zf[groom] == 2):.2f} of grooming fixes")
    # ---------------- bootstrap and Holm
    rng_e = np.random.default_rng(3)
    e1, e2 = rng_e.gamma(2, 1.5, 4000), rng_e.gamma(2, 1.6, 4000)
    blk, strata = np.repeat(np.arange(40), 100), np.repeat(np.arange(4), 1000)
    r1 = P.boot_delta(e1, e2, blk, strata, np.random.default_rng(11))
    r2, d2 = boot_dist(e1, e2, blk, strata, np.random.default_rng(11))
    check("7 bootstrap reproduces boot_delta", abs(r1["lo"] - r2["lo"]) < 1e-12 and abs(r1["hi"] - r2["hi"]) < 1e-12 and len(d2) == 1000,
          f"lo/hi {r1['lo']:.5f}/{r1['hi']:.5f} vs {r2['lo']:.5f}/{r2['hi']:.5f}; one-sided p {r2['p_one']:.4f}")
    animals = ["A1", "A2", "A3", "A4", "A5"]
    rows = []
    for s_, pv in (("s", [0.001, 0.002, 0.004, 0.01, 0.5]), ("g05", [0.001, 0.02, 0.03, 0.04, 0.9])):
        for a_, p_ in zip(animals, pv):
            for ref in ("B2p", "V2"):
                rows.append({"scheme": s_, "subset": "all", "method": "V5", "ref": ref, "animal": a_, "d_med": 0.05, "lo": 0.01, "p_one": p_})
            rows.append({"scheme": s_, "subset": "all", "method": "V5_shift", "ref": "B2p", "animal": a_, "d_med": 0.0, "lo": -0.01, "p_one": 0.5})
        for ref in ("B2p", "V2"):
            rows.append({"scheme": s_, "subset": "moving", "method": "V5", "ref": ref, "animal": "pooled", "d_med": 0.01, "lo": 0.0, "p_one": 0.1})
    vv = verdict_v5(pd.DataFrame(rows), animals, cfg["accept"])
    check("7b Holm verdict logic", vv["verdict"] == "ACCEPTED" and vv["schemes"]["s"]["primary_pass"] and not vv["schemes"]["g05"]["primary_pass"],
          f"verdict {vv['verdict']}, s p_scheme {vv['schemes']['s']['p_scheme']:.3f} (thr {vv['schemes']['s']['holm_threshold']:.4f}), "
          f"g05 p_scheme {vv['schemes']['g05']['p_scheme']:.3f} (thr {vv['schemes']['g05']['holm_threshold']:.4f})")
    n_fail = sum(1 for r in res if not r[1])
    print(f"{'ALL PASS' if n_fail == 0 else f'{n_fail} FAIL'} ({len(res)} checks, {time.time() - t_all:.0f} s)")
    return 0 if n_fail == 0 else 1


# ====================================================================================================== main (report functions below)
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--roles", nargs="*", default=["tuning", "test"], choices=["tuning", "test"])
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--threads", type=int, default=22)
    ap.add_argument("--report-only", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    cfg = load_cfg(args.cohort, args.config)
    cfg["_animals"] = args.animals or cfg["animals"]
    if args.report_only:
        out = Path(args.report_only)
        S = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        fh = open(out / "log.txt", "a", encoding="utf-8")
    else:
        out = output_paths.run_dir(NAME, args.cohort)
        (out / "csv").mkdir(exist_ok=True)
        fh = open(out / "log.txt", "a", encoding="utf-8")
        log(f"run dir {out}; animals {cfg['_animals']}; roles {args.roles}; config {cfg['_path']}; git {C.git_commit()}; "
            f"threads {args.threads}; workers {args.workers}", fh)

        def logger(msg):
            log(msg, fh)

        S = run(cfg, args.roles, args.workers, args.threads, out, logger)
    if "test" not in S["roles"]:
        log("development run (tuning only): no figures/report written", fh)
        fh.close()
        return 0
    finish(out, S, cfg, fh)
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
