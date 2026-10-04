r"""V6 = short-horizon head-IMU / WISER fusion: an EKF + extended RTS with the IMU's 2-Hz world acceleration as input (cohort 2026c).

Plan: implementation_plan/2026-10-03-wiser-v6-fusion.md (approved by the user 2026-10-03, "开始"; committed e0252c8 before any
V6 number; operational details in its Amendment 1, written before any V6 number). Report (full Definitions section):
results/<cohort>/wiser_baseline/reports/wiser_baseline_v6_fusion_<cohort>.md

  V6        per animal and period, state x = (p, v, b, psi) on a 16-Hz grid with the WISER fixes inserted: dp/dt = v,
            dv/dt = R(psi)(a - b) + w_a, db/dt = -b/tau_b + w_b, dpsi/dt = w_psi; a = make_imu lin_acc_earth x/y x 39.37
            low-passed at 2 Hz (zero-phase); B2 fix noise model (anchors_used), chi2 gate + 2 Huber IRLS passes (k_H 2.5);
            V3's ZUPT (sigma 0.25 in/s, Huber, IMU-still runs >= 3 s eroded by 1 s, no release); where the IMU QC fails
            (and in the margins) no input and q = 3 in^2/s^3 (B2/V3 dynamics without the x10) - same filter, no splice.
            Initial psi per IMU session by a closed-form 2-D Procrustes fit of the IMU acceleration to the V3 track's second
            derivative (both low-passed at 1 Hz); handedness decided on the tuning night; q_a, (tau_b, sigma_b), q_psi tuned
            on the tuning night 09-07 only (27-point grid, objective = gap-fill RMS_pred at L = 1 s).
  sensitivities  V6_lp15 / V6_lp3 (input low-pass 1.5 / 3 Hz), V6_psifix (psi frozen), V6_nozupt
  control   V6_ctrl: the same animal's acceleration shifted by +1 h (nights)
  comparators    V3 (reference; current default for the implanted animals), B2, V1b; V2b for context
Pre-registered evaluation: G gap-fill curve (blocks of L = 0.5/1/2/3 s hidden around clean IMU-locomoting seconds,
RMS_pred with the fix-noise floor removed, gain vs V3 with a paired 10-min block bootstrap; calm test nights decide), T1
clean 3-s speed within +-3 %, T2 0 jumps, T3 S5 transitions <= +0.5 s vs B2, T4 in-place 1-s speed p50/p95 <= B2's; the
three-way decision (replace V3 / close the inertial-position line / V3 stays).

Inputs (all read-only): the failure audit run (tracks/, imu_seconds/, tables/segments.csv), the WISER fix caches, the
make_imu 50-Hz npz (via the new 16-Hz input cache <OUT>/2026c/imu_acc16_cache/), the default-smoother / V1b / step-B / V3
runs and configs. Existing scripts are imported, never modified.

Usage:
  python wiser/scripts/analyze_wiser_v6_fusion.py --cohort 2026c [--workers 16]
  python wiser/scripts/analyze_wiser_v6_fusion.py --report-only <run_dir>     # re-aggregate / re-render from the saved files
  python wiser/scripts/analyze_wiser_v6_fusion.py --selftest                  # synthetic data, no field data
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import warnings
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
import analyze_wiser_failure_audit as FA  # noqa: E402  (loaders, segment scoring, block bootstrap; unmodified)
import analyze_wiser_default_smoother as DS  # noqa: E402  (S1 masks, S2 speeds, S5 events/lags, bootstrap helpers; unmodified)
import analyze_wiser_v1b as V1B  # noqa: E402  (ZUPT intervals, membership, V1b kernel + release; unmodified)
import analyze_imu_speed_proxy as SP  # noqa: E402  (clean-WISER reference, track speeds, ratio tables; unmodified)
import analyze_wiser_v3 as V3  # noqa: E402  (V3 kernel, specs, evaluators, T1 tables; unmodified)

njit = P.njit

DIRECTION = "wiser_baseline"
NAME = "wiser_v6_fusion"
STEM = f"{DIRECTION}_v6_fusion"
PLAN = "implementation_plan/2026-10-03-wiser-v6-fusion.md"
DRIVER = "wiser/scripts/analyze_wiser_v6_fusion.py"
SENS = ["V6_lp15", "V6_lp3", "V6_psifix", "V6_nozupt"]
V6M = ["V6"] + SENS
CTRL = "V6_ctrl"
CONTEXT = ["B2", "V1b", "V2b"]
TRACKS = ["raw", "B2", "V1b", "V2b", "V3"] + V6M
SMOOTHED = TRACKS[1:]
NIS_M = ["B2", "V3", "V6"]
S1_M = ["B2", "V3", "V6"]
LABEL = {"raw": "raw fixes", "B2": "B2 robust CV", "V1b": "V1b (B2 + guarded ZUPT)", "V2b": "V2b (IMU-switched q, spliced)",
         "V3": "V3 (ZUPT 0.25 + loco ×10)", "V6": "V6 (IMU-acceleration EKF)", "V6_lp15": "V6 low-pass 1.5 Hz",
         "V6_lp3": "V6 low-pass 3 Hz", "V6_psifix": "V6 ψ frozen", "V6_nozupt": "V6 no ZUPT", "V6_ctrl": "V6 control (+1 h)"}
SHORT = {"raw": "raw", "B2": "B2", "V1b": "V1b", "V2b": "V2b", "V3": "V3", "V6": "V6", "V6_lp15": "V6-1.5Hz", "V6_lp3": "V6-3Hz",
         "V6_psifix": "V6-ψfix", "V6_nozupt": "V6-noZUPT", "V6_ctrl": "V6-ctrl"}
COL = {"raw": "#7f7f7f", "B2": "#2ca02c", "V1b": "#bcbd22", "V2b": "#e377c2", "V3": "#d62728", "V6": "#1f77b4",
       "V6_lp15": "#17becf", "V6_lp3": "#9467bd", "V6_psifix": "#8c564b", "V6_nozupt": "#ff7f0e", "V6_ctrl": "#000000"}
P0_POS, P0_VEL = float(P.P0_POS), float(P.P0_VEL)
SETS3 = ("all", "calm", "rain")
BANDS = SP.BANDS
BAND_LABEL = SP.BAND_LABEL
STATE_NAME = {1: "still", 2: "active", 3: "locomoting"}
GRID_DT_MS = 62.5
D2R = math.pi / 180.0


def log_to(fh, msg: str) -> None:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)      # a cp1252 console must not stop the run
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_v6_fusion_{cohort}.json"
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


def load_json(rel: str) -> dict:
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


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


def tuned_grid(cfg: dict) -> list:
    """The 27 tuning combinations (grid order = tie order)."""
    g = cfg["tuning"]["grid"]
    out = []
    for qa in g["q_a"]:
        for tb, sb in g["tau_sigma_b"]:
            for qp in g["q_psi_deg2_per_min"]:
                out.append({"q_a": float(qa), "tau_b": float(tb), "sigma_b": float(sb), "q_psi_deg2_per_min": float(qp),
                            "q_psi": float(qp) * D2R * D2R / 60.0})
    return out


def v6_par(t6: dict, cfg: dict, tu: dict, variant: str, animal: str) -> dict:
    """Kernel parameters of one V6 form (tuned values t6, the variant's switches, the animal's handedness)."""
    v = cfg["v6"]
    vv = cfg["variants"].get(variant, {"lp": v["primary_lp"], "couple": True, "zupt": True})
    zc = v["zupt"]
    hand = (t6.get("handedness") or {}).get(animal, t6.get("handedness_all", "normal"))
    return {"q_a": float(t6["q_a"]), "tau_b": float(t6["tau_b"]), "sb2": float(t6["sigma_b"]) ** 2, "qpsi": float(t6["q_psi"]),
            "spsi02": (float(v["sigma_psi0_deg"]) * D2R) ** 2, "couple": bool(vv.get("couple", True)), "mirror": hand == "mirror",
            "sv2": float(zc["sigma_zupt_inps"]) ** 2 if vv.get("zupt", True) else 0.0, "huber_zupt": bool(zc["huber_zupt"]),
            "mrej": float(tu["B2"]["mrej"]), "q_fb": float(v["q_fallback"]), "lp": vv.get("lp", v["primary_lp"]),
            "shift_s": float(vv.get("shift_s", 0.0))}


# ====================================================================================================== EKF + extended RTS kernel
@njit(cache=True)
def _chol_inv(A, L, M, out):
    """Inverse of a symmetric positive-definite matrix by Cholesky (A = L L^T, A^-1 = L^-T L^-1)."""
    n = A.shape[0]
    for i in range(n):
        for j in range(n):
            L[i, j] = 0.0
            M[i, j] = 0.0
    for i in range(n):
        for j in range(i + 1):
            s = A[i, j]
            for k in range(j):
                s -= L[i, k] * L[j, k]
            if i == j:
                L[i, i] = math.sqrt(s if s > 1e-300 else 1e-300)
            else:
                L[i, j] = s / L[j, j]
    for i in range(n):
        M[i, i] = 1.0 / L[i, i]
        for j in range(i):
            s = 0.0
            for k in range(j, i):
                s -= L[i, k] * M[k, j]
            M[i, j] = s / L[i, i]
    for i in range(n):
        for j in range(i, n):
            s = 0.0
            for k in range(j, n):
                s += M[k, i] * M[k, j]
            out[i, j] = s
            out[j, i] = s


@njit(cache=True)
def _predict(x, Pm, dt, ain, ax, ay, q, rst, psi0, tau_b, sb2, qpsi, spsi02, couple, mirror, F, Q, xp, T, Pp):
    """One EKF prediction over dt: state (px, py, vx, vy, bx, by, psi); constant input over the step; CV white-acceleration
    noise q on (p, v); exact Gauss-Markov b; random-walk psi. rst: b and psi re-initialised (new IMU session)."""
    for i in range(7):
        for j in range(7):
            F[i, j] = 0.0
            Q[i, j] = 0.0
        F[i, i] = 1.0
    F[0, 2] = dt
    F[1, 3] = dt
    xp[0] = x[0] + x[2] * dt
    xp[1] = x[1] + x[3] * dt
    xp[2] = x[2]
    xp[3] = x[3]
    phi = math.exp(-dt / tau_b) if tau_b > 0.0 else 0.0
    if ain:
        c = math.cos(x[6])
        s = math.sin(x[6])
        ux = ax - x[4]
        uy = (-ay if mirror else ay) - x[5]
        wx = c * ux - s * uy
        wy = s * ux + c * uy
        h = 0.5 * dt * dt
        xp[0] += h * wx
        xp[1] += h * wy
        xp[2] += dt * wx
        xp[3] += dt * wy
        F[0, 4] = -h * c
        F[0, 5] = h * s
        F[1, 4] = -h * s
        F[1, 5] = -h * c
        F[2, 4] = -dt * c
        F[2, 5] = dt * s
        F[3, 4] = -dt * s
        F[3, 5] = -dt * c
        if couple:
            dwx = -s * ux - c * uy
            dwy = c * ux - s * uy
            F[0, 6] = h * dwx
            F[1, 6] = h * dwy
            F[2, 6] = dt * dwx
            F[3, 6] = dt * dwy
    xp[4] = phi * x[4]
    xp[5] = phi * x[5]
    xp[6] = x[6]
    F[4, 4] = phi
    F[5, 5] = phi
    q3 = q * dt * dt * dt / 3.0
    q2 = q * dt * dt / 2.0
    Q[0, 0] = q3
    Q[1, 1] = q3
    Q[0, 2] = q2
    Q[2, 0] = q2
    Q[1, 3] = q2
    Q[3, 1] = q2
    Q[2, 2] = q * dt
    Q[3, 3] = q * dt
    Q[4, 4] = sb2 * (1.0 - phi * phi)
    Q[5, 5] = sb2 * (1.0 - phi * phi)
    Q[6, 6] = qpsi * dt if couple else 0.0
    if rst:
        for j in range(7):
            F[4, j] = 0.0
            F[5, j] = 0.0
            F[6, j] = 0.0
        xp[4] = 0.0
        xp[5] = 0.0
        xp[6] = psi0
        Q[4, 4] = sb2
        Q[5, 5] = sb2
        Q[6, 6] = spsi02
    for i in range(7):
        for j in range(7):
            s_ = 0.0
            for k in range(7):
                s_ += F[i, k] * Pm[k, j]
            T[i, j] = s_
    for i in range(7):
        for j in range(i, 7):
            s_ = Q[i, j]
            for k in range(7):
                s_ += T[i, k] * F[j, k]
            Pp[i, j] = s_
            Pp[j, i] = s_


@njit(cache=True)
def _scal(x, Pm, idx, zval, r, K, row):
    """Sequential scalar measurement update of component idx (H = e_idx), variance r."""
    S = Pm[idx, idx] + r
    for i in range(7):
        K[i] = Pm[i, idx] / S
        row[i] = Pm[idx, i]
    inn = zval - x[idx]
    for i in range(7):
        x[i] += K[i] * inn
    for i in range(7):
        for j in range(7):
            Pm[i, j] -= K[i] * row[j]


@njit(cache=True)
def _kf_v6(tg, fix_of, z, r2, vis, zupt, ain, ag, qstep, rst, psi0g, tau_b, sb2, qpsi, spsi02, couple, mirror, sv2, huber_zupt,
           huber_k, m_rej, gate2, n_iter, p0pos, p0vel, want_cov, P_out, V_out, nis_out, wz_out, psi_out, spsi_out, b_out):
    """V6: EKF + extended RTS on the merged grid tg (fix k at the grid point with fix_of == k). Pass 0 with the soft chi2
    gate, passes 1..n_iter with Huber weights from the smoothed residuals (fixes) and velocities (ZUPT), as V3. With
    ain == False everywhere the (p, v) block is V3's kernel exactly (qstep = q * multiplier)."""
    N = tg.shape[0]
    n = z.shape[0]
    xf = np.zeros((N, 7))
    Pf = np.zeros((N, 7, 7))
    w = np.ones(n)
    wz = np.ones(n)
    F = np.zeros((7, 7))
    Q = np.zeros((7, 7))
    T = np.zeros((7, 7))
    Pp = np.zeros((7, 7))
    Pm = np.zeros((7, 7))
    Pi = np.zeros((7, 7))
    Lb = np.zeros((7, 7))
    Mb = np.zeros((7, 7))
    Cg = np.zeros((7, 7))
    Ps = np.zeros((7, 7))
    D = np.zeros((7, 7))
    xp = np.zeros(7)
    x = np.zeros(7)
    xs = np.zeros(7)
    dx = np.zeros(7)
    K = np.zeros(7)
    row = np.zeros(7)
    for k in range(n):
        nis_out[k] = np.nan
        wz_out[k] = 1.0
    k0 = 0
    while k0 < n and not vis[k0]:
        k0 += 1
    if k0 == n:
        for k in range(n):
            for a in range(2):
                P_out[k, a] = np.nan
                V_out[k, a] = np.nan
        for j in range(N):
            psi_out[j] = np.nan
            spsi_out[j] = np.nan
            b_out[j, 0] = np.nan
            b_out[j, 1] = np.nan
        return
    for it in range(n_iter + 1):
        final = it == n_iter
        # ---------------- forward EKF
        for j in range(N):
            if j == 0:
                for i in range(7):
                    xp[i] = 0.0
                    for l in range(7):
                        Pp[i, l] = 0.0
                xp[0] = z[k0, 0]
                xp[1] = z[k0, 1]
                xp[6] = psi0g[0]
                Pp[0, 0] = p0pos
                Pp[1, 1] = p0pos
                Pp[2, 2] = p0vel
                Pp[3, 3] = p0vel
                Pp[4, 4] = sb2
                Pp[5, 5] = sb2
                Pp[6, 6] = spsi02
            else:
                dt = tg[j] - tg[j - 1]
                if dt < 0.0:
                    dt = 0.0
                _predict(xf[j - 1], Pf[j - 1], dt, ain[j], ag[j, 0], ag[j, 1], qstep[j], rst[j], psi0g[j], tau_b, sb2, qpsi, spsi02,
                         couple, mirror, F, Q, xp, T, Pp)
            for i in range(7):
                x[i] = xp[i]
                for l in range(7):
                    Pm[i, l] = Pp[i, l]
            k = fix_of[j]
            if k >= 0:
                if vis[k]:
                    nu0 = z[k, 0] - xp[0]
                    nu1 = z[k, 1] - xp[1]
                    if final:
                        s00 = Pp[0, 0] + r2[k, 0]
                        s11 = Pp[1, 1] + r2[k, 1]
                        s01 = Pp[0, 1]
                        det = s00 * s11 - s01 * s01
                        nis_out[k] = (s11 * nu0 * nu0 - 2.0 * s01 * nu0 * nu1 + s00 * nu1 * nu1) / det
                    if it == 0 or w[k] > 0.0:
                        if it == 0:
                            rr0 = r2[k, 0]
                            rr1 = r2[k, 1]
                            s00 = Pp[0, 0] + rr0
                            s11 = Pp[1, 1] + rr1
                            s01 = Pp[0, 1]
                            det = s00 * s11 - s01 * s01
                            d2 = (s11 * nu0 * nu0 - 2.0 * s01 * nu0 * nu1 + s00 * nu1 * nu1) / det
                            if d2 > gate2:
                                rr0 *= d2 / gate2
                                rr1 *= d2 / gate2
                        else:
                            rr0 = r2[k, 0] / w[k]
                            rr1 = r2[k, 1] / w[k]
                        _scal(x, Pm, 0, z[k, 0], rr0, K, row)
                        _scal(x, Pm, 1, z[k, 1], rr1, K, row)
                if zupt[k] and sv2 > 0.0:
                    rz = sv2 if (it == 0 or not huber_zupt) else sv2 / wz[k]
                    _scal(x, Pm, 2, 0.0, rz, K, row)
                    _scal(x, Pm, 3, 0.0, rz, K, row)
            for i in range(7):
                xf[j, i] = x[i]
                for l in range(7):
                    Pf[j, i, l] = 0.5 * (Pm[i, l] + Pm[l, i])
        # ---------------- extended RTS smoother
        for i in range(7):
            xs[i] = xf[N - 1, i]
            for l in range(7):
                Ps[i, l] = Pf[N - 1, i, l]
        kk = fix_of[N - 1]
        if kk >= 0:
            P_out[kk, 0] = xs[0]
            P_out[kk, 1] = xs[1]
            V_out[kk, 0] = xs[2]
            V_out[kk, 1] = xs[3]
        if final:
            psi_out[N - 1] = xs[6]
            spsi_out[N - 1] = math.sqrt(Ps[6, 6]) if want_cov else np.nan
            b_out[N - 1, 0] = xs[4]
            b_out[N - 1, 1] = xs[5]
        for j in range(N - 2, -1, -1):
            dt = tg[j + 1] - tg[j]
            if dt < 0.0:
                dt = 0.0
            _predict(xf[j], Pf[j], dt, ain[j + 1], ag[j + 1, 0], ag[j + 1, 1], qstep[j + 1], rst[j + 1], psi0g[j + 1], tau_b, sb2,
                     qpsi, spsi02, couple, mirror, F, Q, xp, T, Pp)
            _chol_inv(Pp, Lb, Mb, Pi)
            for i in range(7):                        # T = Pf F^T
                for l in range(7):
                    s_ = 0.0
                    for m in range(7):
                        s_ += Pf[j, i, m] * F[l, m]
                    T[i, l] = s_
            for i in range(7):                        # C = Pf F^T Pp^-1
                for l in range(7):
                    s_ = 0.0
                    for m in range(7):
                        s_ += T[i, m] * Pi[m, l]
                    Cg[i, l] = s_
            for i in range(7):
                dx[i] = xs[i] - xp[i]
            for i in range(7):
                s_ = xf[j, i]
                for l in range(7):
                    s_ += Cg[i, l] * dx[l]
                x[i] = s_
            if final and want_cov:
                for i in range(7):
                    for l in range(7):
                        D[i, l] = Ps[i, l] - Pp[i, l]
                for i in range(7):                    # T = C D
                    for l in range(7):
                        s_ = 0.0
                        for m in range(7):
                            s_ += Cg[i, m] * D[m, l]
                        T[i, l] = s_
                for i in range(7):                    # Ps = Pf + C D C^T
                    for l in range(i, 7):
                        s_ = Pf[j, i, l]
                        for m in range(7):
                            s_ += T[i, m] * Cg[l, m]
                        Ps[i, l] = s_
                        Ps[l, i] = s_
            for i in range(7):
                xs[i] = x[i]
            kk = fix_of[j]
            if kk >= 0:
                P_out[kk, 0] = xs[0]
                P_out[kk, 1] = xs[1]
                V_out[kk, 0] = xs[2]
                V_out[kk, 1] = xs[3]
            if final:
                psi_out[j] = xs[6]
                spsi_out[j] = math.sqrt(Ps[6, 6]) if (want_cov and Ps[6, 6] > 0.0) else np.nan
                b_out[j, 0] = xs[4]
                b_out[j, 1] = xs[5]
        # ---------------- IRLS weights (as V3)
        if it < n_iter:
            for k in range(n):
                if vis[k]:
                    m2 = 0.0
                    for a in range(2):
                        r = z[k, a] - P_out[k, a]
                        m2 += r * r / r2[k, a]
                    mm = math.sqrt(m2)
                    if mm <= huber_k:
                        w[k] = 1.0
                    elif mm <= m_rej:
                        w[k] = huber_k / mm
                    else:
                        w[k] = 0.0
                if huber_zupt and zupt[k] and sv2 > 0.0:
                    mz = math.sqrt((V_out[k, 0] * V_out[k, 0] + V_out[k, 1] * V_out[k, 1]) / sv2)
                    wz[k] = 1.0 if mz <= huber_k else huber_k / mz
    for k in range(n):
        wz_out[k] = wz[k]


def kf_v6(G: dict, inp: dict, z, r2, vis, zupt, par: dict, tu: dict, want_cov: bool = False) -> dict:
    """One V6 smoother run on the merged grid G with the step inputs inp; returns fix-level p, v, nis, wz and grid-level
    psi, sigma_psi, b (final pass)."""
    n, N = len(z), len(G["tg"])
    Po, Vo, nis, wz = np.empty((n, 2)), np.empty((n, 2)), np.empty(n), np.empty(n)
    psi, spsi, b = np.empty(N), np.empty(N), np.empty((N, 2))
    _kf_v6(G["tg"], G["fix_of"], np.ascontiguousarray(z, np.float64), np.ascontiguousarray(r2, np.float64),
           np.ascontiguousarray(vis, np.bool_), np.ascontiguousarray(zupt, np.bool_), inp["ain"], inp["ag"], inp["qstep"], inp["rst"],
           inp["psi0g"], float(par["tau_b"]), float(par["sb2"]), float(par["qpsi"]), float(par["spsi02"]), bool(par["couple"]),
           bool(par["mirror"]), float(par["sv2"]), bool(par["huber_zupt"]), float(tu.get("huber_k", P.HUBER_K)), float(par["mrej"]),
           float(tu.get("gate2", P.GATE2)), int(tu.get("n_irls", P.N_IRLS)), P0_POS, P0_VEL, bool(want_cov), Po, Vo, nis, wz, psi, spsi, b)
    return {"p": Po, "v": Vo, "nis": nis, "wz": wz, "psi": psi, "spsi": spsi, "b": b}


# ====================================================================================================== grid and step inputs
def make_grid(t_fix: np.ndarray, t16: np.ndarray) -> dict:
    """Merged grid: the 16-Hz points strictly inside [first fix, last fix] (a point within 1 us of a fix dropped) and the
    fixes; per step (t[j-1], t[j]] the 16-Hz index i and fraction f of its midpoint."""
    n = len(t_fix)
    eps = 1e-6
    sel = (t16 > t_fix[0] + eps) & (t16 < t_fix[-1] - eps)
    g = t16[sel]
    j = np.searchsorted(t_fix, g)
    dl = np.abs(g - t_fix[np.clip(j - 1, 0, n - 1)])
    dr = np.abs(t_fix[np.clip(j, 0, n - 1)] - g)
    g = g[np.minimum(dl, dr) > eps]
    tg = np.r_[t_fix, g]
    fo = np.r_[np.arange(n, dtype=np.int64), -np.ones(len(g), np.int64)]
    o = np.argsort(tg, kind="stable")
    tg, fo = np.ascontiguousarray(tg[o], np.float64), np.ascontiguousarray(fo[o], np.int64)
    mid = 0.5 * (tg[1:] + tg[:-1])
    pos = (mid - t16[0]) * 16.0 if len(t16) else np.zeros(len(mid))
    i = np.floor(pos).astype(np.int64)
    return {"tg": tg, "fix_of": fo, "i": i, "f": pos - i, "M": int(len(t16)), "n_fix": n}


def step_sessions(G: dict, sess16: np.ndarray) -> np.ndarray:
    """IMU session of every grid point (carried forward over gaps; the first session back-filled to the start)."""
    M = G["M"]
    i = G["i"]
    inb = (i >= 0) & (i < M - 1)
    s = np.where(inb, sess16[np.clip(i, 0, max(M - 2, 0))], -1).astype(float) if M > 1 else np.full(len(i), -1.0)
    s[s < 0] = np.nan
    ss = pd.Series(s).ffill().bfill().to_numpy()
    ss = np.where(np.isfinite(ss), ss, -1).astype(np.int64)
    return np.r_[ss[:1] if len(ss) else np.array([-1]), ss]


def step_inputs(G: dict, C16: dict, par: dict, fits: dict, shift_n: int = 0) -> dict:
    """Per grid step: input available (both bracketing 16-Hz samples QC-ok, session psi fit ok, not a reset step), the
    midpoint input acceleration (IMU frame, in/s^2; shifted by shift_n samples for the control - content only), q, the
    session resets and initial psi values."""
    acc = C16["acc"][par["lp"]]
    qc = C16["qc"]
    M = G["M"]
    i, f = G["i"], G["f"]
    inb = (i >= 0) & (i < M - 1)
    ic = np.clip(i, 0, max(M - 2, 0))
    ok = inb & qc[ic] & qc[ic + 1]
    if shift_n:
        jj = ic + int(shift_n)
        inb2 = jj < M - 1
        jc = np.clip(jj, 0, max(M - 2, 0))
        ok2 = inb2 & C16["qc50"][jc] & C16["qc50"][jc + 1]
        a = acc[jc] * (1.0 - f)[:, None] + acc[jc + 1] * f[:, None]
        a = np.where(ok2[:, None] & np.isfinite(a), a, 0.0)
    else:
        a = acc[ic] * (1.0 - f)[:, None] + acc[ic + 1] * f[:, None]
    sess = step_sessions(G, C16["session"])
    rst = np.r_[False, (sess[1:] != sess[:-1]) & (sess[1:] >= 0) & (sess[:-1] >= 0)]
    ns = max(int(C16.get("n_sessions", 0)), int(sess.max()) + 1 if len(sess) else 0, 1)
    fit_ok = np.zeros(ns + 1, bool)
    psi0 = np.zeros(ns + 1)
    for sid, ff in fits.items():
        if 0 <= int(sid) < ns:
            fit_ok[int(sid)] = bool(ff["ok"])
            psi0[int(sid)] = float(ff["psi"]) if ff["ok"] else 0.0
    sidx = np.where(sess >= 0, sess, ns)
    ain = np.r_[False, ok] & fit_ok[sidx] & ~rst
    ag = np.vstack([np.zeros((1, 2)), np.where(np.isfinite(a), a, 0.0)])
    ag[~ain] = 0.0
    return {"ain": np.ascontiguousarray(ain), "ag": np.ascontiguousarray(ag, np.float64),
            "qstep": np.ascontiguousarray(np.where(ain, float(par["q_a"]), float(par["q_fb"])), np.float64),
            "rst": np.ascontiguousarray(rst), "psi0g": np.ascontiguousarray(psi0[sidx], np.float64), "sess": sess}


def noinput_inputs(G: dict, qfix: np.ndarray) -> dict:
    """No IMU input anywhere; grid step q = the q of the fix step it lies in (qfix[k] for (t[k-1], t[k]]) -> V3 / B2."""
    N = len(G["tg"])
    tf = G["tg"][G["fix_of"] >= 0]
    k = np.clip(np.searchsorted(tf, G["tg"], side="left"), 0, len(tf) - 1)
    return {"ain": np.zeros(N, bool), "ag": np.zeros((N, 2)), "qstep": np.ascontiguousarray(np.asarray(qfix, float)[k], np.float64),
            "rst": np.zeros(N, bool), "psi0g": np.zeros(N), "sess": np.zeros(N, np.int64)}


# ====================================================================================================== signal helpers / 16-Hz cache
def _sos(fc: float, fs: float, order: int):
    from scipy import signal
    return signal.butter(int(order), float(fc), btype="low", fs=float(fs), output="sos")


def valid_runs(valid: np.ndarray, u_ms: np.ndarray, fs: float) -> list:
    """Runs [a, b) of consecutive valid samples without a time gap (>= 1.5 sample periods)."""
    if not len(valid):
        return []
    gap = np.r_[True, np.diff(u_ms) >= 1.5 * 1000.0 / fs]
    cuts = set(np.flatnonzero(gap).tolist())
    out = []
    for a, b in C.true_runs(np.asarray(valid, bool)):
        s = a
        for c in sorted(x for x in cuts if a < x < b):
            out.append((s, c))
            s = c
        out.append((s, b))
    return out


def lowpass_runs(x: np.ndarray, runs: list, fc: float, fs: float, order: int) -> np.ndarray:
    """Zero-phase Butterworth low-pass (sosfiltfilt, default padding) of every column on each run; NaN elsewhere and on
    runs too short for the padding."""
    from scipy import signal
    sos = _sos(fc, fs, order)
    pad = 3 * (2 * len(sos) + 1)
    y = np.full(x.shape, np.nan)
    for a, b in runs:
        if b - a > pad:
            y[a:b] = signal.sosfiltfilt(sos, x[a:b], axis=0)
    return y


def lp16(x: np.ndarray, ok: np.ndarray, fc: float, order: int = 4) -> np.ndarray:
    """The same low-pass on a regular 16-Hz series over the runs of ok & finite."""
    m = np.asarray(ok, bool) & np.isfinite(x).all(axis=1)
    return lowpass_runs(np.where(m[:, None], x, 0.0), C.true_runs(m), fc, 16.0, order)


def runs_to_grid(g_ms: np.ndarray, u_ms: np.ndarray, ys: list, runs: list, edge_ms: float, pad: int):
    """Linear interpolation of the filtered runs onto the grid, excluding edge_ms at each run end; QC flag per grid point."""
    outs = [np.full((len(g_ms), y.shape[1]), np.nan) for y in ys]
    qc = np.zeros(len(g_ms), bool)
    for a, b in runs:
        if b - a <= pad:
            continue
        lo_, hi_ = u_ms[a] + edge_ms, u_ms[b - 1] - edge_ms
        if hi_ <= lo_:
            continue
        i0, i1 = np.searchsorted(g_ms, [lo_, hi_], side="left")
        i1 = int(np.searchsorted(g_ms, hi_, side="right"))
        if i1 <= i0:
            continue
        gg = g_ms[i0:i1]
        for o, y in zip(outs, ys):
            for c in range(y.shape[1]):
                o[i0:i1, c] = np.interp(gg, u_ms[a:b], y[a:b, c])
        qc[i0:i1] = True
    return outs, qc


def cache_path(cfg: dict, animal: str, pkey: str) -> Path:
    return Path(cfg["acc16_cache_root"]) / animal / f"{pkey}.npz"


def build_acc16(job: dict) -> dict:
    """Write <root>/<SFxx>/<period>.npz (never overwriting): the 16-Hz IMU input series of one animal-period."""
    t0 = time.time()
    cfg, acfg = job["cfg"], job["acfg"]
    animal, pkey = job["animal"], job["pkey"]
    pth = cache_path(cfg, animal, pkey)
    if pth.exists() and not job.get("rebuild"):
        return {"animal": animal, "period": pkey, "status": "exists", "path": str(pth)}
    ctx = _ctx(acfg)
    tz = ctx["tz"]
    ic = cfg["input"]
    pp = acfg["periods"][pkey]
    lo, hi = C.to_ms(pp["start"], tz), C.to_ms(pp["end"], tz)
    a_lo = lo - float(ic["margin_s"]) * 1000.0
    a_hi = hi + float(ic["margin_s"]) * 1000.0 + float(ic["control_shift_s"]) * 1000.0
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    g = np.arange(math.ceil(a_lo / GRID_DT_MS) * GRID_DT_MS, a_hi, GRID_DT_MS)
    fs, order, k = float(ic["fs_imu_hz"]), int(ic["butter_order"]), float(ic["in_per_m"])
    lps = dict(ic["lp_hz"])
    acc = {key: np.full((len(g), 2), np.nan) for key in lps}
    qc50 = np.zeros(len(g), bool)
    sess16 = np.full(len(g), -1, np.int16)
    sess = FA.sessions_for(acfg, ctx, animal, a_lo, a_hi)
    names, stats = [], []
    pad = 3 * (2 * len(_sos(2.0, fs, order)) + 1)
    for si, s in enumerate(sess):
        imu = FA.load_imu([s], a_lo, a_hi, tz)
        names.append(s["session"])
        if not len(imu["unix_ms"]):
            stats.append({"session": s["session"], "n50": 0})
            continue
        u = imu["unix_ms"].astype(np.float64)
        valid = FA.sample_valid(imu, ctx, animal, a_lo, a_hi, vf, vu)
        runs = valid_runs(valid, u, fs)
        lin = imu["lin_acc_earth_ms2"][:, :2].astype(np.float64) * k
        ys = [lowpass_runs(np.where(valid[:, None] & np.isfinite(lin), lin, 0.0), runs, fc, fs, order) for fc in lps.values()]
        outs, q = runs_to_grid(g, u, ys, runs, float(ic["edge_s"]) * 1000.0, pad)
        for key, o in zip(lps, outs):
            acc[key][q] = o[q]
        qc50[q] = True
        sess16[q] = si
        stats.append({"session": s["session"], "n50": int(len(u)), "valid_share": float(valid.mean()), "n_runs": len(runs),
                      "grid_qc": int(q.sum())})
    ps = pd.read_csv(Path(cfg["audit_run"]) / "imu_seconds" / f"{animal}_{pkey}.csv.gz")
    secs = ps["sec"].to_numpy(np.int64)
    gs = np.floor(g / 1000.0).astype(np.int64)
    ok_a = DS.lookup(secs, ps["ok"].to_numpy(bool), gs, False)
    st_a = DS.lookup(secs, ps["state"].to_numpy(np.int8), gs, np.int8(0))
    meta = {"animal": animal, "period": pkey, "lo_local": pp["start"], "hi_local": pp["end"], "grid_ms": GRID_DT_MS,
            "span_local": [C.ms_to_local(a_lo, tz), C.ms_to_local(a_hi, tz)], "lp_hz": lps, "butter_order": order,
            "edge_s": float(ic["edge_s"]), "fs_imu_hz": fs, "in_per_m": k, "sessions": names, "session_stats": stats,
            "imu_root": cfg["imu_root"], "audit_run": cfg["audit_run"], "git_commit": C.git_commit(), "writer": DRIVER,
            "written_local": pd.Timestamp.now(tz=tz).strftime("%Y-%m-%d %H:%M:%S")}
    pth.parent.mkdir(parents=True, exist_ok=True)
    tmp = pth.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, t_ms=g, **{f"acc_{key}": acc[key].astype(np.float32) for key in lps}, qc50=qc50, ok_audit=ok_a,
                        state=st_a.astype(np.int8), session=sess16, sessions=np.array(names if names else [""]), meta=json.dumps(meta))
    tmp.replace(pth)
    return {"animal": animal, "period": pkey, "status": "written", "path": str(pth), "n16": int(len(g)), "qc50": int(qc50.sum()),
            "qc": int((qc50 & ok_a).sum()), "sessions": ";".join(names), "runtime_s": round(time.time() - t0, 1)}


def _build_safe(job: dict) -> dict:
    try:
        return build_acc16(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"animal": job["animal"], "period": job["pkey"], "status": f"ERROR {type(e).__name__}: {e}", "trace": traceback.format_exc()}


def write_cache_readme(cfg: dict) -> None:
    root = Path(cfg["acc16_cache_root"])
    root.mkdir(parents=True, exist_ok=True)
    rd = root / "README.md"
    if rd.exists():
        return
    ic = cfg["input"]
    rd.write_text(
        "# imu_acc16_cache — 16-Hz head-IMU world-frame horizontal acceleration per animal-period (cohort 2026c)\n\n"
        f"Writer: `{DRIVER}` (V6 short-horizon fusion, plan `{PLAN}`, Amendment 1.2). Written once, never overwritten "
        "(`--rebuild-cache` replaces). Reuse it for any later IMU-acceleration work instead of re-reading the 50-Hz npz.\n\n"
        "One file `<SFxx>/<period>.npz` per failure-audit animal-period (`wiser/configs/wiser_failure_audit_2026c.json`):\n\n"
        "| key | content |\n|---|---|\n"
        f"| `t_ms` | float64, absolute field-PC time (unix ms) of the 16-Hz grid (multiples of 62.5 ms) over [period start − {ic['margin_s']} s, "
        f"end + {ic['margin_s']} s + {ic['control_shift_s']} s] (the extra hour feeds the +1 h control) |\n"
        "| `acc_lp15`, `acc_lp2`, `acc_lp3` | float32 (n, 2), make_imu `lin_acc_earth_ms2` x/y (Fusion AHRS NWU earth frame, gravity removed; "
        "arbitrary, drifting heading — no magnetometer) × 39.37 → **in/s²**, zero-phase Butterworth order "
        f"{ic['butter_order']} low-pass at 1.5 / 2 / 3 Hz on each contiguous run of valid 50-Hz samples, linearly interpolated onto the grid; NaN outside the runs |\n"
        f"| `qc50` | bool, the grid point lies inside a filtered run of valid 50-Hz samples, ≥ {ic['edge_s']} s from its ends (validity = the failure audit's "
        "`sample_valid`: finite, not saturated / frozen / invalid / unreliable, frozen rule, handling ± 5 min, all-tag silences ± 2 min, ADC lane, tag window) |\n"
        "| `ok_audit`, `state` | the failure audit's per-second IMU QC `ok` and state (0 unusable, 1 still, 2 active, 3 locomoting) of the grid point's second "
        "(False / 0 outside the period window) |\n"
        "| `session`, `sessions` | int16 index into `sessions` (make_imu session names; −1 = no data); make_imu's heading restarts at each session |\n"
        "| `meta` | JSON: filter, sources, per-session sample / run counts, git commit |\n\n"
        "QC-ok for V6 = `qc50 & ok_audit`. Times are field-PC local; WISER fixes are aligned by τ* before use.\n", encoding="utf-8")


def load_acc16(path: Path, lo_ms: float) -> dict:
    with np.load(path) as zz:
        d = {"t_ms": zz["t_ms"].astype(np.float64), "qc50": zz["qc50"].astype(bool), "ok_audit": zz["ok_audit"].astype(bool),
             "state": zz["state"].astype(np.int8), "session": zz["session"].astype(np.int64),
             "sessions": [str(s) for s in zz["sessions"]], "meta": json.loads(str(zz["meta"])),
             "acc": {k[4:]: zz[k].astype(np.float64) for k in zz.files if k.startswith("acc_")}}
    d["t"] = (d["t_ms"] - lo_ms) / 1000.0
    d["qc"] = d["qc50"] & d["ok_audit"]
    d["n_sessions"] = len(d["sessions"])
    return d


# ====================================================================================================== initial psi / handedness
def track_acc16(t_fix: np.ndarray, p: np.ndarray, t16: np.ndarray, fc: float, max_gap: float) -> np.ndarray:
    """Second derivative (in/s^2) of a fix-time track on the 16-Hz grid: linear interpolation (gaps <= max_gap), zero-phase
    Butterworth-4 low-pass at fc on contiguous runs, central second difference x 16^2."""
    q = FA.interp_track(t_fix, p, t16, max_gap)
    y = lp16(q, np.isfinite(q).all(axis=1), fc)
    d = np.full(y.shape, np.nan)
    if len(y) >= 3:
        d[1:-1] = (y[2:] - 2.0 * y[1:-1] + y[:-2]) * 256.0
    return d


def procrustes(a: np.ndarray, d: np.ndarray) -> dict:
    """Closed-form 2-D rotation fit D ~ s e^{i psi} A (normal) and D ~ s e^{i psi} conj(A) (mirrored), with the similarity
    residuals RSS = sum|D|^2 - |sum conj(A') D|^2 / sum|A|^2."""
    A = a[:, 0] + 1j * a[:, 1]
    Dd = d[:, 0] + 1j * d[:, 1]
    cn = np.sum(np.conj(A) * Dd)
    cm = np.sum(A * Dd)
    sa = float(np.sum(np.abs(A) ** 2))
    sd = float(np.sum(np.abs(Dd) ** 2))
    return {"psi_n": float(np.angle(cn)), "psi_m": float(np.angle(cm)), "rss_n": sd - abs(cn) ** 2 / sa if sa > 0 else np.nan,
            "rss_m": sd - abs(cm) ** 2 / sa if sa > 0 else np.nan, "scale_n": abs(cn) / sa if sa > 0 else np.nan,
            "scale_m": abs(cm) / sa if sa > 0 else np.nan, "sd": sd, "sa": sa}


def fit_psi0(C16: dict, acc: np.ndarray, avail: np.ndarray, d16: np.ndarray, hi_s: float, pz: dict, mirror: bool) -> dict:
    """Initial psi of every IMU session (Amendment 1.5): IMU input low-passed at 1 Hz, 16-Hz points of the session's IMU-ok
    locomoting seconds inside the window, fit window = 30 min from the first such second (extended to >= 60 seconds)."""
    a1 = lp16(acc, avail, float(pz["lp_hz"]))
    t16 = C16["t"]
    base = C16["qc"] & avail & (C16["state"] == 3) & (t16 >= 0) & (t16 < hi_s) & np.isfinite(a1).all(axis=1) & np.isfinite(d16).all(axis=1)
    sec = np.floor(t16).astype(np.int64)
    out = {}
    for sid in range(C16["n_sessions"]):
        m = base & (C16["session"] == sid)
        us = np.unique(sec[m])
        row = {"ok": False, "psi": 0.0, "n_sec_total": int(len(us)), "n_sec": 0, "n": 0}
        if len(us) >= int(pz["min_fit_loco_s"]):
            end = us[0] + float(pz["window_s"])
            if (us < end).sum() < int(pz["min_window_loco_s"]):
                end = us[min(int(pz["min_window_loco_s"]), len(us)) - 1] + 1
            sel = m & (sec < end)
            pr = procrustes(a1[sel], d16[sel])
            ns = int(len(np.unique(sec[sel])))
            row.update({"ok": True, "psi": pr["psi_m"] if mirror else pr["psi_n"], "n_sec": ns, "n": int(sel.sum()),
                        "psi_n": pr["psi_n"], "psi_m": pr["psi_m"], "rss_n": pr["rss_n"], "rss_m": pr["rss_m"],
                        "scale_n": pr["scale_n"], "scale_m": pr["scale_m"],
                        "llr_normal": float(ns * math.log(pr["rss_m"] / pr["rss_n"])) if pr["rss_n"] > 0 and pr["rss_m"] > 0 else np.nan,
                        "t_start_s": float(us[0]), "t_end_s": float(end)})
        out[sid] = row
    return out


def shifted_series(C16: dict, lp: str, shift_n: int) -> tuple[np.ndarray, np.ndarray]:
    """The input series shifted by shift_n samples (value at t + shift) and its 50-Hz availability."""
    acc = C16["acc"][lp]
    M = len(acc)
    a = np.full(acc.shape, np.nan)
    av = np.zeros(M, bool)
    if shift_n < M:
        a[:M - shift_n] = acc[shift_n:]
        av[:M - shift_n] = C16["qc50"][shift_n:]
    return a, av


def variant_fits(C16: dict, par: dict, d16: np.ndarray, hi_s: float, pz: dict) -> dict:
    sh = int(round(par.get("shift_s", 0.0) * 16.0))
    if sh:
        a, av = shifted_series(C16, par["lp"], sh)
        return fit_psi0(C16, a, av & C16["qc"], d16, hi_s, pz, par["mirror"])
    return fit_psi0(C16, C16["acc"][par["lp"]], C16["qc50"], d16, hi_s, pz, par["mirror"])


# ====================================================================================================== gap-fill blocks / G statistics
def select_centres(cand_c: np.ndarray, min_sep: float, seed: int) -> np.ndarray:
    """Seeded greedy selection of block centres >= min_sep apart (sorted)."""
    if not len(cand_c):
        return np.zeros(0)
    rng = np.random.default_rng(int(seed))
    order = rng.permutation(len(cand_c))
    acc = []
    taken = np.zeros(0)
    for o in order:
        c = cand_c[o]
        if len(taken):
            j = np.searchsorted(taken, c)
            if (j > 0 and c - taken[j - 1] < min_sep) or (j < len(taken) and taken[j] - c < min_sep):
                continue
        taken = np.insert(taken, np.searchsorted(taken, c), c)
        acc.append(c)
    return np.sort(np.array(acc))


def hidden_blocks(t: np.ndarray, centres: np.ndarray, L: float) -> tuple[np.ndarray, np.ndarray]:
    """Fix mask of t in [c - L/2, c + L/2) for some centre and the centre index (-1 none); centres >= L apart."""
    if not len(centres):
        return np.zeros(len(t), bool), np.full(len(t), -1, np.int64)
    j = np.searchsorted(centres, t + L / 2.0, side="right") - 1
    jj = np.clip(j, 0, len(centres) - 1)
    h = (j >= 0) & (t >= centres[jj] - L / 2.0) & (t < centres[jj] + L / 2.0)
    return h, np.where(h, jj, -1)


def rms_pred(e2_mean: np.ndarray, s2_mean: np.ndarray) -> np.ndarray:
    return np.sqrt(np.maximum(0.0, e2_mean - s2_mean))


def g_rows(d: pd.DataFrame, methods: list, nb: int, rng, keys: dict, ref: str = "V3") -> list:
    """Pooled RMS_pred per method with paired 10-min block bootstrap; gain = 1 - RMS_pred(m) / RMS_pred(ref)."""
    if not len(d):
        return []
    blk, K = DS.block_codes(d["animal"], d["period"], d["blk10"])
    cnt = FA.boot_counts(K, nb, rng)
    nf = np.bincount(blk, minlength=K).astype(float)
    Nn = cnt @ nf
    S2 = (cnt @ np.bincount(blk, weights=d["s2"].to_numpy(float), minlength=K)) / Nn
    R = {}
    for m in methods:
        e = d[f"e_{m}"].to_numpy(float)
        R[m] = rms_pred((cnt @ np.bincount(blk, weights=e ** 2, minlength=K)) / Nn, S2)
    rows = []
    for m in methods:
        e = d[f"e_{m}"].to_numpy(float)
        row = {**keys, "method": m, "n_fix": int(len(d)), "n_blocks10": int(K), "n_centres": int(d.groupby(["animal", "period", "c"]).ngroups),
               "mean_e2": float(np.mean(e ** 2)), "mean_s2": float(S2[0]), "rms_pred": float(R[m][0]),
               "rms_pred_lo": float(np.percentile(R[m][1:], 2.5)), "rms_pred_hi": float(np.percentile(R[m][1:], 97.5)),
               "med_e": float(np.median(e)), "rmse_raw": float(np.sqrt(np.mean(e ** 2)))}
        for rf in (ref, "B2"):
            with np.errstate(divide="ignore", invalid="ignore"):
                g = 1.0 - R[m] / R[rf]
            gb = g[1:][np.isfinite(g[1:])]
            row[f"gain_vs_{rf}"] = float(g[0])
            row[f"gain_vs_{rf}_lo"] = float(np.percentile(gb, 2.5)) if len(gb) else np.nan
            row[f"gain_vs_{rf}_hi"] = float(np.percentile(gb, 97.5)) if len(gb) else np.nan
        rows.append(row)
    return rows


def decide(gain: dict, ctrl: dict, tpass: dict, acc: dict) -> dict:
    """Pre-registered three-way decision (Amendment 1.15). gain / ctrl: L -> (point, lo, hi) of the calm-test gain vs V3."""
    Ls = [float(x) for x in acc["G_decide_L"]]
    rec = float(acc["control_max_recovery"])
    inval = {L: bool(gain[L][0] > 0 and ctrl[L][0] >= rec * gain[L][0]) for L in Ls}
    sig = {L: bool(gain[L][1] > 0) for L in Ls}
    big = {L: bool(gain[L][0] >= float(acc["G_min_gain"]) and gain[L][1] > 0) for L in Ls}
    tall = all(bool(v) for v in tpass.values())
    if any(inval.values()):
        rule, reason = 2, "the +1 h control recovers >= 50 % of V6's gain at L = " + ", ".join(f"{L:g} s" for L in Ls if inval[L])
    elif not any(sig.values()):
        rule, reason = 2, "the calm-test gain is not significantly above 0 (95 % CI lower bound <= 0) at both L = 0.5 s and 1 s"
    elif any(big.values()) and tall:
        rule, reason = 1, "gain >= 10 % with CI above 0 at L = " + ", ".join(f"{L:g} s" for L in Ls if big[L]) + ", T1-T4 pass, control valid"
    else:
        why = []
        if not any(big.values()):
            why.append("gain above 0 but < 10 % (or its CI not above 0) at both L")
        if not tall:
            why.append("failed " + ", ".join(k for k, v in tpass.items() if not v))
        rule, reason = 3, "; ".join(why)
    return {"rule": rule, "reason": reason, "control_invalid": inval, "significant": sig, "big": big, "T_pass": tpass,
            "outcome": {1: "V6 replaces V3 as the default for the implanted animals", 2: "close the inertial-position line; V3 stays",
                        3: "V3 stays; V6's offer and cost reported, any follow-up is a proposal to the user"}[rule]}


def t4_eval(v_m: np.ndarray, v_b2: np.ndarray) -> dict:
    ok = np.isfinite(v_m) & np.isfinite(v_b2)
    qm, qb = np.percentile(v_m[ok], [50, 95]), np.percentile(v_b2[ok], [50, 95])
    return {"n": int(ok.sum()), "p50": float(qm[0]), "p95": float(qm[1]), "p50_B2": float(qb[0]), "p95_B2": float(qb[1]),
            "pass": bool(qm[0] <= qb[0] and qm[1] <= qb[1])}


# ====================================================================================================== per-job preparation
def prepare(job: dict) -> dict:
    """Load one animal-period: fixes, IMU seconds, V3's masks, the 16-Hz cache and the merged grid."""
    cfg, acfg = job["cfg"], job["acfg"]
    v3c = job["v3cfg"]
    animal, pkey = job["animal"], job["pkey"]
    ctx = _ctx(acfg)
    tz, tu = ctx["tz"], ctx["tuned"]
    pp = acfg["periods"][pkey]
    lo, hi = C.to_ms(pp["start"], tz), C.to_ms(pp["end"], tz)
    run = Path(cfg["audit_run"])
    with np.load(run / "tracks" / f"{animal}_{pkey}.npz") as zf:
        t_ms = zf["t_ms"].astype(np.int64)
        t_al = zf["t_al_ms"].astype(np.float64)
        A = zf["anchors"].astype(np.float64)
        b2_saved = zf["B2"].astype(np.float64)
        raw32 = zf["raw"].astype(np.float64)
    tau = float(ctx["taus"][animal])
    fx = FA.load_fixes(acfg, pkey, animal, lo, hi, tau)
    if not (len(fx) == len(t_ms) and np.array_equal(fx["t_ms"].to_numpy(np.int64), t_ms)):
        raise RuntimeError(f"{animal} {pkey}: fix cache rows do not match the audit track")
    z = fx[["x", "y"]].to_numpy(np.float64)
    J = {"animal": animal, "pkey": pkey, "pi": int(job.get("pi", 0)), "ai": int(job.get("ai", 0)), "pp": pp, "lo": lo, "hi": hi,
         "hi_s": (hi - lo) / 1000.0, "t_ms": t_ms, "t_al": t_al, "A": A,
         "b2_saved": b2_saved, "z": z, "tu": tu, "ctx": ctx, "tz": tz,
         "rep": {"animal": animal, "period": pkey, "cache_match": True, "anchors_match": bool(np.array_equal(fx["anchors_used"].to_numpy(np.float64), A)),
                 "raw_vs_saved_max_in": float(np.max(np.abs(z - raw32)))}}
    t = (t_al - lo) / 1000.0
    J.update({"t": t, "t_abs": t_al / 1000.0, "inwin": (t >= 0) & (t < J["hi_s"]), "core": (t >= 60.0) & (t < J["hi_s"] - 60.0)})
    ps = pd.read_csv(run / "imu_seconds" / f"{animal}_{pkey}.csv.gz")
    secs = ps["sec"].to_numpy(np.int64)
    assert np.all(np.diff(secs) == 1), "imu_seconds not contiguous"
    ok_s = ps["ok"].to_numpy(bool)
    still_s = ps["still"].to_numpy(bool) & ok_s
    state = ps["state"].to_numpy(np.int8)
    fsec = np.floor(t_al / 1000.0).astype(np.int64)
    st_mid, st_at = P.step_states(t_al, secs, state)
    loco = V3.loco_steps(st_mid, int(v3c["v3"]["loco_state"]))
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    mid = (secs + 0.5) * 1000.0
    amask = ((mid >= lo) & (mid < hi) & ~C.in_any(mid, ctx["handling"]) & ~C.in_any(mid, ctx["silences"]) & (mid >= vf) & (mid < vu))
    runs_abs = V1B.still_runs(still_s, secs)
    iv = (V1B.eroded(runs_abs, float(v3c["v3"]["min_run_s"]), float(v3c["v3"]["erode_s"])) * 1000.0 - lo) / 1000.0
    J.update({"secs": secs, "ok_s": ok_s, "still_s": still_s, "state": state, "amask": amask, "st_mid": st_mid, "st_at": st_at,
              "ok_f": DS.lookup(secs, ok_s, fsec, False), "still_f": DS.lookup(secs, still_s, fsec, False),
              "st_f": DS.lookup(secs, state, fsec, np.int8(0)), "am_f": DS.lookup(secs, amask, fsec, False), "loco": loco,
              "mu": V3.qmult(loco, float(v3c["v3"]["loco_mult"])), "iv": iv, "zupt": V1B.membership(t, iv)[1]})
    J["r2"] = P.r2_from_anchors(A, ctx["table"])
    J["s2fix"] = J["r2"].sum(axis=1)
    J["C16"] = load_acc16(cache_path(cfg, animal, pkey), lo)
    J["G"] = make_grid(t, J["C16"]["t"])
    return J


def clean_centres(J: dict, cfg: dict, scfg: dict) -> tuple[np.ndarray, pd.DataFrame | None]:
    """Gap-fill block centres (relative s) from step B's clean seconds with audit state 3; also returns step B's table."""
    if J["pkey"] not in SP.nights(scfg):
        return np.zeros(0), None
    sb = pd.read_csv(Path(cfg["speed_proxy_run"]) / "seconds" / f"{J['animal']}_{J['pkey']}.csv.gz")
    if not np.array_equal(sb["sec"].to_numpy(np.int64), J["secs"]):
        raise RuntimeError(f"{J['animal']} {J['pkey']}: step-B seconds differ from the audit's imu_seconds")
    cand = sb["clean"].to_numpy(bool) & (J["state"] == 3)
    cc = (J["secs"][cand] * 1000.0 - J["lo"]) / 1000.0 + 0.5
    gf = cfg["gapfill"]
    sep = max(float(x) for x in gf["L_s"]) + float(gf["min_gap_s"])
    return select_centres(cc, sep, int(gf["seed"]) + 100 * int(J["pi"]) + int(J["ai"])), sb


def run_v3(J: dict, specs: dict, m: str, vis: np.ndarray):
    sp = specs[m]
    none = np.zeros(len(J["t"]), bool)
    return V3.kf_v3(J["t"], J["z"], J["r2"], vis, J["zupt"] if sp["zupt"] else none, V3.qmult(J["loco"], sp["mloco"]), sp, J["tu"])


def run_variant(J: dict, par: dict, d16: np.ndarray, vis: np.ndarray, pz: dict, want_cov: bool = False):
    fits = variant_fits(J["C16"], par, d16, J["hi_s"], pz)
    inp = step_inputs(J["G"], J["C16"], par, fits, int(round(par.get("shift_s", 0.0) * 16.0)))
    zm = J["zupt"] if par["sv2"] > 0 else np.zeros(len(J["t"]), bool)
    return kf_v6(J["G"], inp, J["z"], J["r2"], vis, zm, par, J["tu"], want_cov), inp, fits


# ====================================================================================================== tuning (09-07 only)
def tune_job(job: dict) -> dict:
    """Stage 'hand': Procrustes handedness fits on the full V3 track. Stage 'grid': every grid combination's gap-fill
    errors at L = 1 s (the tuning objective)."""
    t_job = time.time()
    if P.HAVE_NUMBA:
        P.set_num_threads(1)
    cfg = job["cfg"]
    J = prepare(job)
    v3c = job["v3cfg"]
    specs = V3.kf_specs(J["tu"], v3c)
    pz = cfg["v6"]["psi0"]
    vis_all = np.ones(len(J["t"]), bool)
    if job["stage"] == "hand":
        P3, _, _, _ = run_v3(J, specs, "V3", vis_all)
        d16 = track_acc16(J["t"], P3, J["C16"]["t"], float(pz["lp_hz"]), float(pz["max_gap_s"]))
        fits = fit_psi0(J["C16"], J["C16"]["acc"][cfg["v6"]["primary_lp"]], J["C16"]["qc50"], d16, J["hi_s"], pz, False)
        return {"animal": J["animal"], "period": J["pkey"], "fits": fits, "runtime_s": round(time.time() - t_job, 1)}
    L = float(cfg["tuning"]["L_s"])
    centres, _ = clean_centres(J, cfg, job["scfg"])
    hid, cid = hidden_blocks(J["t"], centres, L)
    vis = ~hid
    P3h, _, _, _ = run_v3(J, specs, "V3", vis)
    d16 = track_acc16(J["t"], P3h, J["C16"]["t"], float(pz["lp_hz"]), float(pz["max_gap_s"]))
    sc = hid & J["inwin"]
    rows = []
    e3 = np.hypot(*(P3h[sc] - J["z"][sc]).T)
    for gi, comb in enumerate(job["grid"]):
        t6 = {**comb, "handedness": job["handedness"]}
        par = v6_par(t6, cfg, J["tu"], "V6", J["animal"])
        out, _, _ = run_variant(J, par, d16, vis, pz)
        e = np.hypot(*(out["p"][sc] - J["z"][sc]).T)
        rows.append({"animal": J["animal"], "gi": gi, **{k: v for k, v in comb.items()}, "n_fix": int(sc.sum()), "sum_e2": float(np.sum(e ** 2)),
                     "sum_s2": float(np.sum(J["s2fix"][sc])), "sum_e2_V3": float(np.sum(e3 ** 2))})
    return {"animal": J["animal"], "rows": rows, "n_centres": int(len(centres)), "runtime_s": round(time.time() - t_job, 1)}


def _tune_safe(job: dict) -> dict:
    try:
        return tune_job(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


def run_tuning(cfg: dict, base_job: dict, workers: int, out: Path, fh) -> dict:
    acfg = base_job["acfg"]
    tp = cfg["tuning"]["period"]
    pi = list(acfg["periods"]).index(tp)
    jobs = [{**base_job, "animal": a, "pkey": tp, "pi": pi, "ai": ai, "stage": "hand"} for ai, a in enumerate(acfg["animals"])]
    hand_rows = []
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), workers))) as ex:
        res = list(ex.map(_tune_safe, jobs))
    for r in res:
        if "error" in r:
            raise RuntimeError(f"tuning (handedness) {r['animal']}: {r['error']}\n{r['trace']}")
        for sid, f in r["fits"].items():
            hand_rows.append({"animal": r["animal"], "period": r["period"], "session": sid, **f})
    H = pd.DataFrame(hand_rows)
    per = {}
    for a, g in H[H.ok].groupby("animal"):
        llr = float(g["llr_normal"].sum())
        per[a] = "normal" if llr >= 0 else "mirror"
    vals = set(per.values())
    if len(vals) == 1 and len(per) == len(acfg["animals"]):
        hand_all = vals.pop()
        hand = {a: hand_all for a in acfg["animals"]}
        mode = "one for all (all five agree)"
    else:
        hand_all = "per animal"
        hand = {a: per.get(a, "normal") for a in acfg["animals"]}
        mode = "per animal (animals disagree or a fit failed)"
    log_to(fh, f"handedness on {tp}: " + ", ".join(f"{a} {per.get(a, 'n/a')} (LLR {H[(H.animal == a) & H.ok].llr_normal.sum():+.1f})" for a in acfg["animals"])
           + f" -> {mode}")
    grid = tuned_grid(cfg)
    jobs = [{**j, "stage": "grid", "grid": grid, "handedness": hand} for j in jobs]
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), workers))) as ex:
        res = list(ex.map(_tune_safe, jobs))
    rows = []
    for r in res:
        if "error" in r:
            raise RuntimeError(f"tuning (grid) {r['animal']}: {r['error']}\n{r['trace']}")
        rows.extend(r["rows"])
        log_to(fh, f"tuning grid {r['animal']}: {r['n_centres']} centres, {r['runtime_s']} s")
    TG = pd.DataFrame(rows)
    agg = TG.groupby("gi").agg(n_fix=("n_fix", "sum"), sum_e2=("sum_e2", "sum"), sum_s2=("sum_s2", "sum"), sum_e2_V3=("sum_e2_V3", "sum")).reset_index()
    agg["rms_pred"] = np.sqrt(np.maximum(0, (agg.sum_e2 - agg.sum_s2) / agg.n_fix))
    agg["rms_pred_V3"] = np.sqrt(np.maximum(0, (agg.sum_e2_V3 - agg.sum_s2) / agg.n_fix))
    agg["gain_vs_V3"] = 1 - agg.rms_pred / agg.rms_pred_V3
    for k in ("q_a", "tau_b", "sigma_b", "q_psi_deg2_per_min", "q_psi"):
        agg[k] = [grid[int(g)][k] for g in agg.gi]
    agg = agg.sort_values("gi").reset_index(drop=True)
    best = int(agg.loc[agg.rms_pred.idxmin(), "gi"])
    b = grid[best]
    edges = [k for k, vals_ in (("q_a", cfg["tuning"]["grid"]["q_a"]), ("tau_b", [x[0] for x in cfg["tuning"]["grid"]["tau_sigma_b"]]),
                                ("q_psi_deg2_per_min", cfg["tuning"]["grid"]["q_psi_deg2_per_min"])) if b[k] in (min(vals_), max(vals_))]
    tuned = {**b, "handedness": hand, "handedness_all": hand_all, "handedness_mode": mode,
             "handedness_llr": {a: float(H[(H.animal == a) & H.ok].llr_normal.sum()) for a in acfg["animals"]},
             "objective": "pooled RMS_pred at L = 1 s, night_20260907, five animals", "rms_pred_in": float(agg.loc[agg.gi == best, "rms_pred"].iloc[0]),
             "rms_pred_V3_in": float(agg.rms_pred_V3.iloc[0]), "grid_edges_hit": edges, "tuned_on": tp,
             "tuned_local": pd.Timestamp.now(tz=cfg.get("tz", "America/New_York")).strftime("%Y-%m-%d %H:%M:%S"), "run_dir": str(out)}
    (out / "tables").mkdir(exist_ok=True)
    agg.to_csv(out / "tables" / "tuning_grid.csv", index=False)
    TG.to_csv(out / "tables" / "tuning_grid_by_animal.csv", index=False)
    H.to_csv(out / "tables" / "handedness_tuning.csv", index=False)
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    cj["tuned"] = tuned
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"tuned: q_a {b['q_a']}, tau_b {b['tau_b']} s, sigma_b {b['sigma_b']}, q_psi {b['q_psi_deg2_per_min']} deg^2/min; RMS_pred "
               f"{tuned['rms_pred_in']:.3f} in (V3 {tuned['rms_pred_V3_in']:.3f}); grid edges hit: {edges or 'none'}")
    return tuned


# ====================================================================================================== one animal-period
def psi_diag_rows(J: dict, sec_rel: np.ndarray, psi_deg: np.ndarray, spsi_deg: np.ndarray, inp_sec: np.ndarray, sess_sec: np.ndarray,
                  pdc: dict, base: dict) -> list:
    rows = []
    st = J["state"]
    win = (sec_rel >= 0) & (sec_rel < J["hi_s"])
    obs = float(pdc["observable_sigma_deg"])
    for sid in np.unique(sess_sec[win & (sess_sec >= 0)]):
        ms = win & (sess_sec == sid)
        m = ms & inp_sec & np.isfinite(psi_deg)
        row = {**base, "session": int(sid), "session_name": J["C16"]["sessions"][int(sid)] if 0 <= sid < len(J["C16"]["sessions"]) else "",
               "n_sec": int(ms.sum()), "n_input_sec": int(m.sum()),
               "obs_frac_input": float(np.mean(spsi_deg[m] < obs)) if m.any() else np.nan,
               "obs_frac_window": float(np.mean(np.nan_to_num(spsi_deg[ms], nan=1e9) < obs)) if ms.any() else np.nan}
        if m.sum() >= 600:
            tm = sec_rel[m] / 60.0
            co = np.polyfit(tm, psi_deg[m], 1)
            res = psi_deg[m] - np.polyval(co, tm)
            row.update({"drift_deg_per_min": float(co[0]), "resid_rms_deg": float(np.sqrt(np.mean(res ** 2))),
                        "psi_range_deg": float(np.ptp(psi_deg[m]))})
        bouts = [(a, b) for a, b in C.true_runs((st == 3) & ms & inp_sec) if b - a >= int(pdc["bout_min_s"])]
        if len(bouts) >= 2:
            bp = np.array([np.mean(psi_deg[a:b]) for a, b in bouts])
            bc = np.array([0.5 * (sec_rel[a] + sec_rel[b - 1]) for a, b in bouts]) / 60.0
            dpsi = np.diff(bp)
            dtm = np.diff(bc)
            row.update({"n_bouts": int(len(bouts)), "bout_dpsi_med_abs_deg": float(np.median(np.abs(dpsi))),
                        "bout_dpsi_p90_abs_deg": float(np.percentile(np.abs(dpsi), 90)),
                        "bout_rate_med_abs_deg_per_min": float(np.median(np.abs(dpsi) / np.maximum(dtm, 1e-6))),
                        "bout_gap_med_min": float(np.median(dtm))})
        rows.append(row)
    return rows


def process(job: dict) -> dict:
    t_job = time.time()
    if P.HAVE_NUMBA:
        P.set_num_threads(1)
    cfg, acfg, dcfg, scfg = job["cfg"], job["acfg"], job["dcfg"], job["scfg"]
    v3c, v1c = job["v3cfg"], job["v1cfg"]
    t6 = job["tuned"]
    out = Path(job["out"])
    J = prepare(job)
    animal, pkey, lo, hi = J["animal"], J["pkey"], J["lo"], J["hi"]
    pp, tu, ctx = J["pp"], J["tu"], J["ctx"]
    base = {"animal": animal, "period": pkey, "set": pp["set"], "kind": pp["kind"]}
    rep = {**base, **J["rep"]}
    t, z, A, r2, n = J["t"], J["z"], J["A"], J["r2"], len(J["t"])
    t_abs, inwin, core = J["t_abs"], J["inwin"], J["core"]
    secs, ok_s, state = J["secs"], J["ok_s"], J["state"]
    ok_f, still_f, st_f, am_f, zupt, loco = J["ok_f"], J["still_f"], J["st_f"], J["am_f"], J["zupt"], J["loco"]
    mc, trim = acfg["metrics"], float(acfg["still"]["trim_s"])
    s1c, s2c, s5c = dcfg["s1"], dcfg["s2"], dcfg["s5"]
    acc = cfg["acceptance"]
    jin, jdt = float(acc["T2_jump_in"]), float(acc["T2_jump_dt_s"])
    blk_s = float(cfg["bootstrap"]["block_s"])
    houses, buf = ctx["houses"], float(acfg["house_buffer_in"])
    pz = cfg["v6"]["psi0"]
    night = pp["kind"] == "night"
    vis_all = np.ones(n, bool)
    none = np.zeros(n, bool)
    specs = V3.kf_specs(tu, v3c)
    G = J["G"]
    rep.update({"n_fix_win": int(inwin.sum()), "n_grid": int(len(G["tg"])), "n16_qc": int(J["C16"]["qc"].sum()),
                "n_sessions_cache": int(J["C16"]["n_sessions"])})
    # ---- B2 / V3 (V3 kernel) + reproductions
    trk, nis = {"raw": z}, {}
    for m in ("B2", "V3"):
        trk[m], _, nis[m], _ = run_v3(J, specs, m, vis_all)
    with np.load(Path(cfg["v3_run"]) / "tracks" / f"{animal}_{pkey}.npz") as zf:
        if not np.array_equal(zf["t_ms"].astype(np.int64), J["t_ms"]):
            raise RuntimeError(f"{animal} {pkey}: V3 track times differ")
        v3_saved = zf["V3"].astype(np.float64)
        rep["zupt_equals_V3_saved_mask"] = bool(np.array_equal(zf["zupt"].astype(bool), zupt))
    d3 = np.hypot(*(trk["V3"] - v3_saved).T)
    rep["V3_rebuilt_vs_saved_core_max_in"] = float(d3[core].max()) if core.any() else np.nan
    rep["V3_rebuilt_vs_saved_all_max_in"] = float(d3.max())
    db = np.hypot(*(trk["B2"] - J["b2_saved"]).T)
    rep["B2_vs_saved_core_max_in"] = float(db[core].max()) if core.any() else np.nan
    with np.load(Path(cfg["v1b_run"]) / "tracks" / f"{animal}_{pkey}.npz") as zf:
        trk["V1b"] = zf["V1b"].astype(np.float64)
    with np.load(Path(cfg["default_smoother_run"]) / "tracks" / f"{animal}_{pkey}.npz") as zf:
        trk["V2b"] = zf["V2b"].astype(np.float64)
    # the V6 kernel without input: q = 3 everywhere and no ZUPT -> B2; q = 3 x V3's multipliers + V3's ZUPT -> V3
    par0 = v6_par(t6, cfg, tu, "V6", animal)
    pb2 = {**par0, "sv2": 0.0}
    o = kf_v6(G, noinput_inputs(G, np.full(n, float(specs["B2"]["q"]))), z, r2, vis_all, none, pb2, tu)
    rep["V6kernel_noinput_vs_B2_max_in"] = float(np.max(np.hypot(*(o["p"] - trk["B2"]).T)))
    pv3 = {**par0, "sv2": float(specs["V3"]["sv"]) ** 2, "huber_zupt": bool(specs["V3"]["huber_zupt"])}
    o = kf_v6(G, noinput_inputs(G, float(specs["V3"]["q"]) * J["mu"]), z, r2, vis_all, zupt, pv3, tu)
    rep["V6kernel_noinput_vs_V3_max_in"] = float(np.max(np.hypot(*(o["p"] - trk["V3"]).T)))
    del o
    # ---- V6 and its sensitivities (+ the control on nights), full data
    d16 = track_acc16(t, trk["V3"], J["C16"]["t"], float(pz["lp_hz"]), float(pz["max_gap_s"]))
    v6list = V6M + ([CTRL] if night else [])
    pars = {m: v6_par(t6, cfg, tu, m, animal) for m in v6list}
    fitrows, inp_main, psi_main = [], None, None
    for m in v6list:
        o, inp, fits = run_variant(J, pars[m], d16, vis_all, pz, want_cov=(m == "V6"))
        trk[m] = o["p"]
        if m == "V6":
            nis["V6"] = o["nis"]
            inp_main, psi_main = inp, o
        for sid, f in fits.items():
            fitrows.append({**base, "method": m, "session": int(sid), **{k: v for k, v in f.items()}})
    # handedness (reported, every period): both options on the full V3 track, primary input
    hfits = fit_psi0(J["C16"], J["C16"]["acc"][cfg["v6"]["primary_lp"]], J["C16"]["qc50"], d16, J["hi_s"], pz, False)
    for sid, f in hfits.items():
        fitrows.append({**base, "method": "handedness_check", "session": int(sid), **f})
    # ---- input share at the fixes (step ending at each fix)
    fo = G["fix_of"]
    gfix = np.flatnonzero(fo >= 0)
    inp_fix = np.zeros(n, bool)
    inp_fix[fo[gfix]] = inp_main["ain"][gfix]
    # ---- per-second psi, sigma_psi, b at the integer seconds of the window
    sec_rel = (secs * 1000.0 - lo) / 1000.0
    jg = np.clip(np.searchsorted(G["tg"], sec_rel, side="left"), 0, len(G["tg"]) - 1)
    good = np.abs(G["tg"][jg] - sec_rel) < 1e-6
    psi_deg = np.where(good, psi_main["psi"][jg] / D2R, np.nan)
    spsi_deg = np.where(good, psi_main["spsi"][jg] / D2R, np.nan)
    b_sec = np.where(good[:, None], psi_main["b"][jg], np.nan)
    C16 = J["C16"]
    i16 = np.clip(np.round((secs * 1000.0 - C16["t_ms"][0]) / GRID_DT_MS).astype(np.int64), 0, len(C16["t_ms"]) - 1)
    sess_sec = C16["session"][i16]
    inp_sec = np.zeros(len(secs), bool)
    jg1 = np.clip(jg + 1, 0, len(G["tg"]) - 1)
    inp_sec = good & inp_main["ain"][jg1]
    pdrows = psi_diag_rows(J, sec_rel, psi_deg, spsi_deg, inp_sec, sess_sec, cfg["psi_diag"], base)
    house_f = V1B.house_mask(trk["B2"], houses, buf)
    (out / "tracks").mkdir(exist_ok=True)
    np.savez_compressed(out / "tracks" / f"{animal}_{pkey}.npz", t_ms=J["t_ms"], t_al_ms=J["t_al"], anchors=A.astype(np.int8),
                        **{m: trk[m].astype(np.float32) for m in ["B2", "V3"] + v6list}, zupt=zupt, loco_step=loco, inp_fix=inp_fix,
                        **{f"nis_{m}": nis[m].astype(np.float32) for m in NIS_M}, inwin=inwin, amask=am_f, ok=ok_f, still=still_f,
                        state=st_f, house=house_f, sec=secs, psi_deg=psi_deg.astype(np.float32), spsi_deg=spsi_deg.astype(np.float32),
                        b_sec=b_sec.astype(np.float32), inp_sec=inp_sec, sess_sec=sess_sec.astype(np.int16), state_sec=state)
    # ---- gap-fill (nights with step-B clean seconds)
    centres, sb = clean_centres(J, cfg, scfg)
    gf = cfg["gapfill"]
    rep["n_centres"] = int(len(centres))
    gfd = {}
    if len(centres):
        rcv = v1c["v1b"]["release"]
        sp1 = V1B.kf_specs(tu, v1c)["V1b"]
        sp2 = DS.kf_specs(tu, None)["V2b"]
        for L in [float(x) for x in gf["L_s"]]:
            hid, cid = hidden_blocks(t, centres, L)
            vis = ~hid
            sc = hid & inwin
            pr = {}
            for m in ("B2", "V3"):
                pr[m], _, _, _ = run_v3(J, specs, m, vis)
            zh = V1B.zupt_masks(t, z, vis, J["iv"], rcv)
            pr["V1b"], _, _, _ = V1B.kf_v1b(t, z, r2, vis, zh["zupt"], sp1, tu)
            Pk, _, _ = P.kf_run(t, z, r2, [vis], [J["st_mid"]], [J["st_at"]], [sp2])
            pr["V2b"] = np.where(ok_f[:, None], Pk[0], pr["B2"])
            d16h = track_acc16(t, pr["V3"], C16["t"], float(pz["lp_hz"]), float(pz["max_gap_s"]))
            for m in V6M + [CTRL]:
                o, _, _ = run_variant(J, pars[m], d16h, vis, pz)
                pr[m] = o["p"]
            key = f"L{L:g}"
            gfd[f"{key}__i"] = np.flatnonzero(sc).astype(np.int32)
            gfd[f"{key}__c"] = cid[sc].astype(np.int32)
            gfd[f"{key}__blk10"] = np.floor(t[sc] / blk_s).astype(np.int32)
            gfd[f"{key}__s2"] = J["s2fix"][sc].astype(np.float32)
            gfd[f"{key}__A"] = A[sc].astype(np.int8)
            gfd[f"{key}__inp"] = inp_fix[sc]
            for m in gf["methods"]:
                gfd[f"{key}__e_{m}"] = np.hypot(*(pr[m][sc] - z[sc]).T).astype(np.float32)
            rep[f"gf_nfix_{key}"] = int(sc.sum())
        (out / "gapfill").mkdir(exist_ok=True)
        np.savez_compressed(out / "gapfill" / f"{animal}_{pkey}.npz", centres=centres, **gfd)
    # ---- per-second speeds
    blk = ((secs * 1000.0 - lo) // (blk_s * 1000.0)).astype(np.int64)
    sec_d = {"sec": secs, "state": state, "ok": ok_s, "still": J["still_s"], "mask": J["amask"], "block": blk, "inp": inp_sec,
             **{f"v_{m}": DS.second_speeds(t_abs, trk[m], secs, float(s2c["max_gap_s"])).astype(np.float32) for m in TRACKS}}
    if sb is not None:
        rc = scfg["reference"]
        cl = sb["clean"].to_numpy(bool)
        for m in TRACKS:
            w3, w1 = SP.track_speeds(t_abs, trk[m], secs, rc)
            sec_d[f"w3_{m}"], sec_d[f"w1_{m}"] = w3.astype(np.float32), w1.astype(np.float32)
        sec_d.update({"clean": cl, "u3": sb["u3"].to_numpy(np.float32), "u1": sb["u1"].to_numpy(np.float32)})
        rep["n_clean"] = int(cl.sum())
        rep["stepB_block_equal"] = bool(np.array_equal(sb["block"].to_numpy(np.int64), blk))
    (out / "seconds").mkdir(exist_ok=True)
    np.savez_compressed(out / "seconds" / f"{animal}_{pkey}.npz", **sec_d)
    # ---- certified still segments (circular): metrics on >= 30 s, T2 jumps on every primary segment
    run = Path(cfg["audit_run"])
    Sall = _segments(run)
    Sap = Sall[(Sall.animal == animal) & (Sall.period == pkey) & Sall.primary]
    mrows, frows, jrows, t2rows = [], [], [], []
    spd = {m: [] for m in TRACKS}
    spd_idx = {m: [] for m in TRACKS}
    seg_ids = []
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
        truth = np.array([r.truth_x, r.truth_y])
        sub = {m: trk[m][i0:i1] for m in TRACKS}
        res, _, _, speeds = FA.score_segment(t[i0:i1], sub, truth, ts, te, mc, TRACKS)
        for m in TRACKS:
            mrows.append({"seg_id": r.seg_id, "method": m, **{k: v for k, v in res[m].items() if not k.startswith("_")}})
        fr = {"seg_id": np.repeat(r.seg_id, i1 - i0), "t_al_ms": (lo + t[i0:i1] * 1000).round(1), "anchors": A[i0:i1].astype(int)}
        for m in TRACKS:
            fr[f"r_{m}"] = np.hypot(*(sub[m] - truth).T).round(4)
        frows.append(pd.DataFrame(fr))
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
    # ---- T2 over the analysis mask
    j4 = []
    for m in TRACKS:
        jk = FA.find_jumps(t, trk[m], jin, jdt)
        jk = jk[inwin[jk] & inwin[np.minimum(jk + 1, n - 1)]]
        sj = np.floor((0.5 * (t[jk] + t[jk + 1]) * 1000.0 + lo) / 1000.0).astype(np.int64)
        j4.append({**base, "method": m, "jumps_win": int(len(jk)), "jumps_mask": int(DS.lookup(secs, J["amask"], sj, False).sum())})
    # ---- T3: S5 onset / offset lags
    erows = []
    for e in DS.transition_events(state, secs, lo, hi, s5c):
        anchor = e["rb"] if e["kind"] == "onset" else e["ra"]
        row = {**base, **e, "block": int(anchor // blk_s)}
        for m in TRACKS:
            row[f"lag_{m}"], _ = DS.event_lag(t, trk[m], e, s5c)
        erows.append(row)
    # ---- S1 (default-smoother masks and seeds)
    pi, ai = int(job["pi"]), int(job["ai"])
    seed = int(s1c["seed"])
    hidm = DS.hidden_masks(n, seed + 100 * pi + ai, seed + 50_000 + 100 * pi + ai, int(s1c["s_every"]))
    s1out = {}
    for sch in ("a", "s"):
        h = hidm[sch]
        vis = ~h
        scm = h & inwin & (A >= float(s1c["min_anchors"])) & ok_f
        dd = {"i": np.flatnonzero(scm).astype(np.int32), "block": np.floor(t[scm] / blk_s).astype(np.int32), "still": still_f[scm],
              "moving": ok_f[scm] & ~still_f[scm], "loco": st_f[scm] == 3, "anchors": A[scm].astype(np.int8)}
        P3h = None
        for m in ("B2", "V3"):
            Ph, _, _, _ = run_v3(J, specs, m, vis)
            if m == "V3":
                P3h = Ph
            dd[f"e_{m}"] = np.hypot(*(z[scm] - Ph[scm]).T).astype(np.float32)
        d16s = track_acc16(t, P3h, C16["t"], float(pz["lp_hz"]), float(pz["max_gap_s"]))
        o, _, _ = run_variant(J, pars["V6"], d16s, vis, pz)
        dd["e_V6"] = np.hypot(*(z[scm] - o["p"][scm]).T).astype(np.float32)
        s1out[sch] = dd
    (out / "s1").mkdir(exist_ok=True)
    np.savez_compressed(out / "s1" / f"{animal}_{pkey}.npz", **{f"{s}__{k}": v for s, dd in s1out.items() for k, v in dd.items()})
    # ---- fallback share
    win16 = (C16["t"] >= 0) & (C16["t"] < J["hi_s"])
    fb = {**base, "n_fix_win": int(inwin.sum()), "n_fix_mask": int((inwin & am_f).sum()), "n_fix_mask_input": int((inwin & am_f & inp_fix).sum()),
          "n_fix_win_input": int((inwin & inp_fix).sum()), "n16_win": int(win16.sum()), "n16_win_qc": int((win16 & C16["qc"]).sum()),
          "n_steps": int(len(G["tg"]) - 1), "n_steps_input": int(inp_main["ain"].sum()),
          "n_sessions_fit_failed": int(sum(1 for r in fitrows if r["method"] == "V6" and not r["ok"] and r["n_sec_total"] > 0)),
          "ctrl_shift_missing_share": np.nan}
    if night:
        ii = np.clip(G["i"] + int(round(pars[CTRL]["shift_s"] * 16)), 0, len(C16["qc50"]) - 2)
        a_ = inp_main["ain"][1:]
        fb["ctrl_shift_missing_share"] = float(np.mean(~(C16["qc50"][ii[a_]] & C16["qc50"][ii[a_] + 1]))) if a_.any() else np.nan
    rep["runtime_s"] = round(time.time() - t_job, 1)
    return {"rep": rep, "fb": pd.DataFrame([fb]), "metrics": pd.DataFrame(mrows), "fixes": pd.concat(frows, ignore_index=True) if frows else pd.DataFrame(),
            "jumps": pd.DataFrame(jrows), "t2still": pd.DataFrame(t2rows), "t2mask": pd.DataFrame(j4), "s5": pd.DataFrame(erows),
            "psi0": pd.DataFrame(fitrows), "psidiag": pd.DataFrame(pdrows)}


def _process_safe(job: dict) -> dict:
    try:
        return process(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


def _warm() -> None:
    """Compile (or load the cached) kernels before the pools start."""
    t = np.arange(20, dtype=float) * 0.2
    z = np.zeros((20, 2))
    G = make_grid(t, np.arange(0, 64) / 16.0)
    inp = noinput_inputs(G, np.full(20, 3.0))
    par = {"tau_b": 3.0, "sb2": 1.0, "qpsi": 1e-5, "spsi02": 0.1, "couple": True, "mirror": False, "sv2": 0.0625, "huber_zupt": True, "mrej": 1e9}
    kf_v6(G, inp, z, np.ones((20, 2)), np.ones(20, bool), np.ones(20, bool), par, {}, True)
    V3._warm()


# ====================================================================================================== compute run
def base_job(cfg: dict) -> dict:
    return {"cfg": cfg, "acfg": load_acfg(cfg), "dcfg": load_dcfg(cfg), "scfg": load_scfg(cfg), "v3cfg": load_json(cfg["v3_config"]),
            "v1cfg": load_json(cfg["v1b_config"])}


def run_compute(cfg: dict, workers: int, skip_tune: bool = False, rebuild_cache: bool = False) -> Path:
    t0 = time.time()
    bj = base_job(cfg)
    acfg = bj["acfg"]
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    (out / "tables").mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; numba {P.HAVE_NUMBA}; workers {workers}")
    _warm()
    nw = max(1, min(16, workers))
    # ---- 16-Hz input cache
    write_cache_readme(cfg)
    cj = [{**bj, "animal": a, "pkey": pk, "rebuild": rebuild_cache} for pk in acfg["periods"] for a in acfg["animals"]]
    crows = []
    with ProcessPoolExecutor(max_workers=nw) as ex:
        for r in ex.map(_build_safe, cj):
            crows.append(r)
            if str(r["status"]).startswith("ERROR"):
                log_to(fh, f"cache ERROR {r['animal']} {r['period']}: {r['status']}\n{r.get('trace', '')}")
            elif r["status"] == "written":
                log_to(fh, f"cache written {r['animal']} {r['period']}: {r['n16']:,} samples, QC-ok {r['qc']:,}, sessions {r['sessions']} ({r['runtime_s']} s)")
    pd.DataFrame(crows).to_csv(out / "tables" / "cache_build.csv", index=False)
    if any(str(r["status"]).startswith("ERROR") for r in crows):
        raise SystemExit("cache build failed")
    log_to(fh, f"cache ready ({time.time() - t0:.0f} s)")
    # ---- tuning on the tuning night only
    if skip_tune and cfg.get("tuned"):
        t6 = cfg["tuned"]
        log_to(fh, f"tuning skipped; using the config's tuned block: {json.dumps({k: t6[k] for k in ('q_a', 'tau_b', 'sigma_b', 'q_psi_deg2_per_min')})}")
    else:
        t6 = run_tuning(cfg, bj, nw, out, fh)
        cfg = {**load_cfg(cfg["_cohort"], cfg["_path"])}
        bj["cfg"] = cfg
    log_to(fh, f"tuning done ({time.time() - t0:.0f} s)")
    # ---- every animal-period
    jobs = [{**bj, "tuned": t6, "animal": a, "pkey": pk, "out": str(out), "pi": pi, "ai": ai}
            for pi, pk in enumerate(acfg["periods"]) for ai, a in enumerate(acfg["animals"])]
    jobs.sort(key=lambda j: 0 if acfg["periods"][j["pkey"]]["kind"] == "night" else 1)     # long jobs first
    res = []
    with ProcessPoolExecutor(max_workers=nw) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                continue
            rp = r["rep"]
            log_to(fh, f"{rp['animal']} {rp['period']}: {rp['n_fix_win']:,} window fixes, grid {rp['n_grid']:,}, centres {rp.get('n_centres', 0)}; "
                       f"V6 kernel w/o input vs B2 {rp['V6kernel_noinput_vs_B2_max_in']:.1e} / vs V3 {rp['V6kernel_noinput_vs_V3_max_in']:.1e} in; "
                       f"V3 rebuilt vs saved (core) {rp['V3_rebuilt_vs_saved_core_max_in']:.1e} in; {rp['runtime_s']} s")
            res.append(r)
    if len(res) != len(jobs):
        log_to(fh, f"WARNING: {len(jobs) - len(res)} jobs failed")
    tb = out / "tables"
    pd.DataFrame([r["rep"] for r in res]).to_csv(tb / "reproduction_tracks.csv", index=False)
    for key, f in (("fb", "fallback_jobs.csv"), ("metrics", "still_metrics.csv.gz"), ("fixes", "still_fixes.csv.gz"),
                   ("jumps", "t2_still_jump_list.csv"), ("t2still", "t2_still_jumps_jobs.csv"), ("t2mask", "t2_mask_jumps_jobs.csv"),
                   ("s5", "t3_events.csv.gz"), ("psi0", "psi0_fits.csv"), ("psidiag", "psi_diagnostics.csv")):
        parts = [r[key] for r in res if r[key] is not None and len(r[key])]
        (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()).to_csv(tb / f, index=False)
    tu = _ctx(acfg)["tuned"]
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": C.git_commit(),
            **{k: cfg[k] for k in ("audit_config", "audit_run", "default_smoother_config", "default_smoother_run", "v1b_config", "v1b_run",
                                   "speed_proxy_config", "speed_proxy_run", "v3_config", "v3_run", "smoothing_config", "fix_cache_root",
                                   "imu_root", "acc16_cache_root")},
            "run_manifests": {k: json.loads((Path(cfg[k]) / "run_manifest.json").read_text(encoding="utf-8"))
                              for k in ("audit_run", "default_smoother_run", "v1b_run", "speed_proxy_run", "v3_run")},
            "tuned_V6": t6, "tuned_B2": tu["B2"], "irls": {k: tu.get(k) for k in ("huber_k", "gate2", "n_irls")}, "tau_star_s": _ctx(acfg)["taus"],
            "input": cfg["input"], "v6": cfg["v6"], "variants": cfg["variants"], "gapfill": cfg["gapfill"], "acceptance": cfg["acceptance"],
            "numba": P.HAVE_NUMBA, "workers": workers, "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    fh.close()
    return out


# ====================================================================================================== aggregation
def _read_npz_dir(d: Path, keys: list | None = None) -> pd.DataFrame:
    parts = []
    for f in sorted(d.glob("*.npz")):
        a, pk = f.stem.split("_", 1)
        with np.load(f) as z:
            ks = keys or [k for k in z.files if z[k].ndim == 1]
            n0 = len(z[ks[0]])
            dd = pd.DataFrame({k: z[k] for k in ks if z[k].ndim == 1 and len(z[k]) == n0})
        dd.insert(0, "period", pk)
        dd.insert(0, "animal", a)
        parts.append(dd)
    return pd.concat(parts, ignore_index=True)


def load_gapfill(out: Path, methods: list) -> pd.DataFrame:
    parts = []
    for f in sorted((out / "gapfill").glob("*.npz")):
        a, pk = f.stem.split("_", 1)
        with np.load(f) as z:
            Ls = sorted({k.split("__")[0] for k in z.files if "__" in k})
            for key in Ls:
                d = pd.DataFrame({"i": z[f"{key}__i"], "c": z[f"{key}__c"], "blk10": z[f"{key}__blk10"], "s2": z[f"{key}__s2"].astype(float),
                                  "A": z[f"{key}__A"], "inp": z[f"{key}__inp"], **{f"e_{m}": z[f"{key}__e_{m}"].astype(float) for m in methods}})
                d.insert(0, "L", float(key[1:]))
                d.insert(0, "period", pk)
                d.insert(0, "animal", a)
                parts.append(d)
    return pd.concat(parts, ignore_index=True)


def input_diagnostic(out: Path, cfg: dict, acfg: dict) -> pd.DataFrame:
    """POST-HOC (added after the decision; not part of it): on every night, IMU-ok locomoting 16-Hz samples, the 1-Hz IMU
    input magnitude vs the V3 track's 1-Hz acceleration magnitude, and how much of the track acceleration a rotation of the
    IMU input explains (similarity Procrustes R^2, whole night and in 120-s windows where the heading drift is small)."""
    tz = acfg["tz"]
    rows = []
    for pk, pp in acfg["periods"].items():
        if pp["kind"] != "night":
            continue
        lo, hi = C.to_ms(pp["start"], tz), C.to_ms(pp["end"], tz)
        hs = (hi - lo) / 1000.0
        for a in acfg["animals"]:
            C16 = load_acc16(cache_path(cfg, a, pk), lo)
            with np.load(out / "tracks" / f"{a}_{pk}.npz") as z:
                t = (z["t_al_ms"].astype(np.float64) - lo) / 1000.0
                p3 = z["V3"].astype(np.float64)
            d = track_acc16(t, p3, C16["t"], 1.0, 1.0)
            a1 = lp16(C16["acc"][cfg["v6"]["primary_lp"]], C16["qc50"], 1.0)
            win = (C16["t"] >= 0) & (C16["t"] < hs)
            fa, fd = np.isfinite(a1).all(axis=1), np.isfinite(d).all(axis=1)
            m = C16["qc"] & (C16["state"] == 3) & win & fa & fd
            st = C16["qc"] & (C16["state"] == 1) & win & fa
            pr = procrustes(a1[m], d[m])
            r2w = []
            for w0 in np.arange(0.0, hs, 120.0):
                mm = m & (C16["t"] >= w0) & (C16["t"] < w0 + 120.0)
                if len(np.unique(np.floor(C16["t"][mm]))) >= 15:
                    pw = procrustes(a1[mm], d[mm])
                    r2w.append((1 - pw["rss_n"] / pw["sd"], 1 - pw["rss_m"] / pw["sd"]))
            r2w = np.array(r2w) if r2w else np.full((1, 2), np.nan)
            rows.append({"animal": a, "period": pk, "set": pp["set"], "n_loco16": int(m.sum()),
                         "imu_acc_loco_p50": float(np.median(np.hypot(*a1[m].T))), "imu_acc_loco_p90": float(np.percentile(np.hypot(*a1[m].T), 90)),
                         "track_acc_loco_p50": float(np.median(np.hypot(*d[m].T))), "track_acc_loco_p90": float(np.percentile(np.hypot(*d[m].T), 90)),
                         "imu_acc_still_p50": float(np.median(np.hypot(*a1[st].T))), "R2_night_normal": float(1 - pr["rss_n"] / pr["sd"]),
                         "R2_night_mirror": float(1 - pr["rss_m"] / pr["sd"]), "n_win120": int(np.isfinite(r2w[:, 0]).sum()),
                         "R2_win120_normal_p50": float(np.nanmedian(r2w[:, 0])), "R2_win120_normal_p90": float(np.nanpercentile(r2w[:, 0], 90)),
                         "R2_win120_mirror_p50": float(np.nanmedian(r2w[:, 1]))})
    return pd.DataFrame(rows)


def aggregate(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    acfg, scfg = load_acfg(cfg), load_scfg(cfg)
    tb = out / "tables"
    bc = cfg["bootstrap"]
    nb = int(bc["n_boot"])
    rngs = {k: np.random.default_rng(int(bc["seed"]) + i) for i, k in enumerate(("g", "ga", "t1", "t3", "still", "s1", "t4", "anim", "t1x"))}
    acc = cfg["acceptance"]
    thr = float(acc["T1_max_abs_rel"])
    sets = ["calm", "rain"]
    pset = {k: v["set"] for k, v in acfg["periods"].items()}
    pkind = {k: v["kind"] for k, v in acfg["periods"].items()}
    gfc = cfg["gapfill"]
    gm = list(gfc["methods"])
    A: dict = {"cfg": cfg, "acfg": acfg}
    A["rep_tr"] = rep_tr = pd.read_csv(tb / "reproduction_tracks.csv")
    t6 = json.loads((out / "input_provenance.json").read_text(encoding="utf-8"))["tuned_V6"]
    A["t6"] = t6
    # ---------------- G
    GF = load_gapfill(out, gm)
    Ls = sorted(GF.L.unique())
    grows, garows = [], []
    for sname, pers in gfc["sets"].items():
        for L in Ls:
            d = GF[(GF.L == L) & GF.period.isin(pers)]
            grows.extend(g_rows(d, gm, nb, rngs["g"], {"gset": sname, "L": L}))
            for a in sorted(d.animal.unique()):
                garows.extend(g_rows(d[d.animal == a], gm, nb, rngs["ga"], {"gset": sname, "L": L, "animal": a}))
    GT = pd.DataFrame(grows)
    GA = pd.DataFrame(garows)
    GT.to_csv(tb / "gapfill.csv", index=False)
    GA.to_csv(tb / "gapfill_by_animal.csv", index=False)
    gi_ = GF[GF.period.isin(gfc["sets"]["calm_test"])]
    A["gf_input_share"] = {L: float(gi_[gi_.L == L].inp.mean()) for L in Ls}
    log_to(fh, f"G done ({time.time() - t0:.0f} s)")

    def gget(sname, L, m, col="gain_vs_V3"):
        r = GT[(GT.gset == sname) & (GT.L == L) & (GT.method == m)]
        return r.iloc[0] if len(r) else None
    gain = {float(L): (float(gget(acc["G_set"], L, "V6")["gain_vs_V3"]), float(gget(acc["G_set"], L, "V6")["gain_vs_V3_lo"]),
                       float(gget(acc["G_set"], L, "V6")["gain_vs_V3_hi"])) for L in Ls}
    ctrl = {float(L): (float(gget(acc["G_set"], L, CTRL)["gain_vs_V3"]), float(gget(acc["G_set"], L, CTRL)["gain_vs_V3_lo"]),
                       float(gget(acc["G_set"], L, CTRL)["gain_vs_V3_hi"])) for L in Ls}
    # ---------------- per-fix: NIS, input share
    keys = ["anchors", "inwin", "amask", "ok", "still", "state", "house", "zupt", "inp_fix"] + [f"nis_{m}" for m in NIS_M]
    FX = _read_npz_dir(out / "tracks", keys)
    FX["set"] = FX["period"].map(pset)
    pop = FX["inwin"].astype(bool) & FX["amask"].astype(bool)
    Gn = FX[pop].copy()
    Gn["abin"] = FA.anchor_bin(Gn["anchors"].to_numpy())
    Gn["zone"] = np.where(Gn["house"].astype(bool), "house", "outside")
    Gn["imu"] = np.where(~Gn["ok"].astype(bool), "QC failed", Gn["state"].map(STATE_NAME).fillna("QC failed"))
    q95 = float(cfg["nis"]["chi2_2_q95"])
    nr = []
    for m in NIS_M:
        col = f"nis_{m}"
        for by in (["set", "imu"], ["set", "abin", "imu"], ["set", "abin", "zone", "imu"], ["set", "abin", "zone"], ["set"]):
            g = Gn.dropna(subset=[col]).groupby(by)[col]
            t_ = pd.DataFrame({"n": g.size(), "mean": g.mean(), "median": g.median(), "gt95": g.apply(lambda x: float((x > q95).mean()))}).reset_index()
            t_.insert(0, "by", "×".join(by))
            t_.insert(0, "method", m)
            nr.append(t_)
    NIS = pd.concat(nr, ignore_index=True)
    NIS.to_csv(tb / "nis.csv", index=False)
    del Gn, FX
    # ---------------- per-second: T1, T4
    SE = _read_npz_dir(out / "seconds")
    SE["set"] = SE["period"].map(pset)
    SE["kind"] = SE["period"].map(pkind)
    for c in ("clean", "ok", "still", "mask", "inp"):
        SE[c] = SE[c].fillna(False).astype(bool) if c in SE else False
    D = SE[SE["clean"]].copy()
    T1 = V3.t1_tables(D, scfg, nb, rngs["t1"], tracks=TRACKS)
    T1["pass_d95"] = T1["d95"].abs() <= thr
    T1.to_csv(tb / "t1_speed.csv", index=False)
    tp = cfg["tuning"]["period"]
    T1X = V3.t1_tables(D[D.period != tp], scfg, nb, rngs["t1x"], sets=("all", "calm", "rain"), bands=("all", "gt15"), tracks=TRACKS)
    T1X.to_csv(tb / "t1_speed_without_tuning_night.csv", index=False)
    arows = []
    for a in sorted(D["animal"].unique()):
        rr = V3.t1_tables(D[D["animal"] == a], scfg, nb, rngs["anim"], sets=("all",), bands=("all", "gt15"), tracks=["B2", "V3", "V6"])
        rr.insert(0, "animal", a)
        arows.append(rr)
    T1A = pd.concat(arows, ignore_index=True)
    T1A.to_csv(tb / "t1_by_animal.csv", index=False)
    R1 = pd.read_csv(Path(cfg["v3_run"]) / "tables" / "t1_speed.csv")
    Rm = T1[T1.track.isin(["raw", "B2", "V1b", "V2b", "V3"])].merge(R1, on=["scale", "set", "band", "track"], suffixes=("", "_V3run"))
    Rm["dd50_pp"] = 100 * (Rm["d50"] - Rm["d50_V3run"]).abs()
    Rm["dd95_pp"] = 100 * (Rm["d95"] - Rm["d95_V3run"]).abs()
    Rm["n_equal"] = Rm["n_sec"] == Rm["n_sec_V3run"]
    Rm[["scale", "set", "band", "track", "n_sec", "n_sec_V3run", "d50", "d50_V3run", "d95", "d95_V3run", "dd50_pp", "dd95_pp", "n_equal"]].to_csv(tb / "t1_repro_V3run.csv", index=False)
    A["rep_t1"] = {"n_rows": int(len(Rm)), "max_dd50_pp": float(Rm.dd50_pp.max()), "max_dd95_pp": float(Rm.dd95_pp.max()),
                   "n_equal_all": bool(Rm.n_equal.all()), "pass": bool(Rm.dd50_pp.max() <= 0.1 and Rm.dd95_pp.max() <= 0.1)}
    FLt = pd.read_csv(Path(cfg["speed_proxy_run"]) / "tables" / "noise_floor.csv")
    floor95 = float(FLt[(FLt.kind == "all") & (FLt.set == "all") & (FLt.scale == 3)].p95.iloc[0])
    jr = []
    for s in SETS3:
        dd = D[((D.set == s) if s != "all" else True) & (D.state == 3) & (D.u3 < floor95)]
        for kind_, pref in (("S2 1-s speed", "v_"), ("step-B 1-s speed v1", "w1_")):
            d2 = dd[np.isfinite(dd[[f"{pref}{m}" for m in TRACKS]].to_numpy(float)).all(axis=1)]
            for r in V3.speed_ratio_rows(d2, {m: f"{pref}{m}" for m in TRACKS}, "B2", nb, rngs["t4"], {"set": s, "speed": kind_}):
                jr.append(r)
    JR = pd.DataFrame(jr)
    JR.to_csv(tb / "t4_inplace_speed.csv", index=False)
    J3 = pd.read_csv(Path(cfg["v3_run"]) / "tables" / "jitter_inplace_speed.csv")
    j3 = J3[(J3.set == "all") & (J3.speed == acc["T4_speed"])].set_index("track")
    jm = JR[(JR.set == "all") & (JR.speed == acc["T4_speed"])].set_index("track")
    A["rep_t4"] = {"n_here": int(jm.loc["B2", "n_sec"]), "n_V3run": int(j3.loc["B2", "n_sec"]),
                   **{f"{m}_{q}_here": float(jm.loc[m, q]) for m in ("B2", "V3") for q in ("p50", "p95")},
                   **{f"{m}_{q}_V3run": float(j3.loc[m, q]) for m in ("B2", "V3") for q in ("p50", "p95")}}
    # input share on the clean seconds / T4 set
    A["inp_share_clean"] = float(D["inp"].mean())
    A["inp_share_t4"] = float(D[(D.state == 3) & (D.u3 < floor95)]["inp"].mean())
    # POST-HOC (after the decision; not part of it): 1-s speed in IMU-still seconds of the analysis mask (the T3 mechanism)
    srows = []
    for s in SETS3:
        dd = SE[((SE.set == s) if s != "all" else np.ones(len(SE), bool)) & SE["mask"] & SE["still"] & (SE["state"] == 1)]
        for m in ["B2", "V3", "V6", "V6_nozupt"]:
            v_ = dd[f"v_{m}"].to_numpy(float)
            v_ = v_[np.isfinite(v_)]
            srows.append({"set": s, "method": m, "n_sec": int(len(v_)), "p50": float(np.median(v_)), "p95": float(np.percentile(v_, 95)),
                          "share_ge3": float(np.mean(v_ >= 3.0))})
    SS = pd.DataFrame(srows)
    SS.to_csv(tb / "posthoc_still_second_speed.csv", index=False)
    A["SS"] = SS
    # ... and by distance from the edge of the still run (runs >= 10 s, S5's minimum), all sets
    edge = np.full(len(SE), np.nan)
    pos = 0
    for _, g in SE.groupby(["animal", "period"], sort=False):
        st1 = g["state"].to_numpy() == 1
        e_ = np.full(len(g), np.nan)
        for a_, b_ in C.true_runs(st1):
            if b_ - a_ >= 10:
                ii = np.arange(a_, b_)
                e_[a_:b_] = np.minimum(ii - a_, b_ - 1 - ii)
        edge[pos:pos + len(g)] = e_
        pos += len(g)
    SE["edge_s"] = edge
    erows = []
    for lab, lo_, hi_ in (("0-1 s", 0, 2), ("2-4 s", 2, 5), ("5-9 s", 5, 10), (">= 10 s", 10, np.inf)):
        dd = SE[SE["mask"] & (SE["edge_s"] >= lo_) & (SE["edge_s"] < hi_)]
        for m in ["B2", "V3", "V6", "V6_nozupt"]:
            v_ = dd[f"v_{m}"].to_numpy(float)
            v_ = v_[np.isfinite(v_)]
            erows.append({"edge": lab, "method": m, "n_sec": int(len(v_)), "share_ge3": float(np.mean(v_ >= 3.0)) if len(v_) else np.nan,
                          "p95": float(np.percentile(v_, 95)) if len(v_) else np.nan})
    SSE = pd.DataFrame(erows)
    SSE.to_csv(tb / "posthoc_still_edge_speed.csv", index=False)
    A["SSE"] = SSE
    del SE
    log_to(fh, f"T1 / T4 done ({time.time() - t0:.0f} s)")
    # ---------------- T3
    EV = pd.read_csv(tb / "t3_events.csv.gz")
    T3 = t3_table(EV, sets, float(acc["T3_max_later_s"]), nb, rngs["t3"])
    T3.to_csv(tb / "t3_lags.csv", index=False)
    # ---------------- still metrics + S3
    run = Path(cfg["audit_run"])
    Saud = _segments(run)
    S = Saud[Saud.primary & Saud.scored & Saud.ge30].reset_index(drop=True)
    M = pd.read_csv(tb / "still_metrics.csv.gz")
    F = pd.read_csv(tb / "still_fixes.csv.gz")
    SPD = DS.load_speeds_multi(out / "speeds", S, TRACKS)
    pooled = pd.DataFrame([{"set": s, **FA.still_summary(S[S.set == s], M, F, SPD, m, S)} for s in sets for m in TRACKS])
    pooled.to_csv(tb / "still_pooled.csv", index=False)
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
                    d_, dlo, dhi = FA.ci(st[m][k] - st["raw"][k])
                    d2_, d2lo, d2hi = FA.ci(st[m][k] - st["B2"][k])
                brow.append({"set": s, "method": m, "metric": k, "value": e, "lo": lo_, "hi": hi_, "diff_vs_raw": d_, "diff_raw_lo": dlo,
                             "diff_raw_hi": dhi, "diff_vs_B2": d2_, "diff_B2_lo": d2lo, "diff_B2_hi": d2hi, "n_blocks": K})
    BS = pd.DataFrame(brow)
    BS.to_csv(tb / "still_bootstrap.csv", index=False)
    S3 = pooled[["set", "method", "crazy_n", "crazy_per_h", "still_h"]].copy()
    S3.to_csv(tb / "s3_excursions.csv", index=False)
    Ma = pd.read_csv(run / "tables" / "segment_metrics.csv.gz")
    Mv = pd.read_csv(Path(cfg["v3_run"]) / "tables" / "still_metrics.csv.gz")
    rep_still = {}
    for lab, ref, meths in (("raw/B2 vs audit", Ma, ["raw", "B2"]), ("V3/V1b/V2b vs V3 run", Mv, ["V3", "V1b", "V2b"])):
        Rm_ = M[M.method.isin(meths)].merge(ref[ref.seg_id.isin(set(S.seg_id)) & ref.method.isin(meths)], on=["seg_id", "method"], suffixes=("", "_ref"))
        rep_still[lab] = {"n_rows": int(len(Rm_)), **{c: float(np.nanmax(np.abs(Rm_[c] - Rm_[f"{c}_ref"]))) for c in ("rms_in", "path_in_per_min", "crazy_n", "jumps")}}
    A["rep_still"] = rep_still
    log_to(fh, f"still done ({time.time() - t0:.0f} s)")
    # ---------------- T2
    J2s = pd.read_csv(tb / "t2_still_jumps_jobs.csv")
    J2m = pd.read_csv(tb / "t2_mask_jumps_jobs.csv")
    T2s = J2s.groupby(["set", "method"])[["jumps_primary", "jumps_ge30", "n_seg_primary", "n_seg_ge30"]].sum().reset_index()
    T2m = J2m.groupby(["set", "kind", "method"])[["jumps_win", "jumps_mask"]].sum().reset_index()
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
            for subn in ("moving", "loco", "still", "all"):
                dd = d0 if subn == "all" else d0[d0[subn].astype(bool)]
                if not len(dd):
                    continue
                mb = float(np.median(dd["e_B2"]))
                row = {"set": s, "scheme": sch, "subset": subn, "n": int(len(dd)), "med_B2": mb}
                if subn == "moving":
                    blk, K = DS.block_codes(dd["animal"], dd["period"], dd["block"])
                    cnt = FA.boot_counts(K, nb, rngs["s1"])
                    qr = DS.hist_boot_q(dd["e_B2"].to_numpy(float), blk, cnt, DS.S1_EDGES, [0.5])[:, 0]
                for m in S1_M[1:]:
                    mv = float(np.median(dd[f"e_{m}"]))
                    row.update({f"med_{m}": mv, f"D_{m}": 1.0 - mv / mb})
                    if subn == "moving":
                        qm = DS.hist_boot_q(dd[f"e_{m}"].to_numpy(float), blk, cnt, DS.S1_EDGES, [0.5])[:, 0]
                        b = 1.0 - qm[1:] / qr[1:]
                        row.update({f"D_{m}_lo": float(np.nanpercentile(b, 2.5)), f"D_{m}_hi": float(np.nanpercentile(b, 97.5))})
                rows.append(row)
    S1 = pd.DataFrame(rows)
    S1.to_csv(tb / "s1_heldout.csv", index=False)
    # ---------------- fallback share, psi diagnostics, psi0
    FB = pd.read_csv(tb / "fallback_jobs.csv")
    fbs = []
    for s in sets + ["all"]:
        for k in ("all", "night", "day"):
            g = FB[(((FB.set == s) if s != "all" else np.ones(len(FB), bool)) & ((FB.kind == k) if k != "all" else np.ones(len(FB), bool)))]
            if not len(g):
                continue
            fbs.append({"set": s, "kind": k, "n_fix_mask": int(g.n_fix_mask.sum()), "fix_input_share": float(g.n_fix_mask_input.sum() / g.n_fix_mask.sum()),
                        "step_input_share": float(g.n_steps_input.sum() / g.n_steps.sum()), "win16_qc_share": float(g.n16_win_qc.sum() / g.n16_win.sum()),
                        "sessions_fit_failed": int(g.n_sessions_fit_failed.sum()), "ctrl_shift_missing_share": float(np.nanmean(g.ctrl_shift_missing_share))
                        if g.ctrl_shift_missing_share.notna().any() else np.nan})
    FBS = pd.DataFrame(fbs)
    FBS.to_csv(tb / "fallback_share.csv", index=False)
    ID = input_diagnostic(out, cfg, acfg)
    ID.to_csv(tb / "posthoc_input_diagnostic.csv", index=False)
    A["ID"] = ID
    PD = pd.read_csv(tb / "psi_diagnostics.csv")
    P0 = pd.read_csv(tb / "psi0_fits.csv")
    HT = pd.read_csv(tb / "handedness_tuning.csv") if (tb / "handedness_tuning.csv").exists() else pd.DataFrame()
    TG = pd.read_csv(tb / "tuning_grid.csv") if (tb / "tuning_grid.csv").exists() else pd.DataFrame()
    # ---------------- verdicts (T1-T4) and the decision
    ver = {}
    for m in SMOOTHED:
        r_all = T1[(T1.scale == int(acc["T1_scale_s"])) & (T1.set == acc["T1_set"]) & (T1.band == "all") & (T1.track == m)].iloc[0]
        r_fast = T1[(T1.scale == int(acc["T1_scale_s"])) & (T1.set == acc["T1_set"]) & (T1.band == "gt15") & (T1.track == m)].iloc[0]
        t3r = T3[(T3.method == m) & (T3.periods == "all")]
        sj = int(T2s[T2s.method == m].jumps_primary.sum())
        mj = int(T2m[T2m.method == m].jumps_mask.sum())
        t4 = jm.loc[m] if m in jm.index else None
        b4 = jm.loc["B2"]
        v = {"T1": bool(abs(r_all.d95) <= thr and abs(r_fast.d95) <= thr), "T1_d95_all": float(r_all.d95), "T1_d95_gt15": float(r_fast.d95),
             "T1_d95_all_ci": [float(r_all.d95_lo), float(r_all.d95_hi)], "T1_d95_gt15_ci": [float(r_fast.d95_lo), float(r_fast.d95_hi)],
             "T2": bool(sj == 0 and mj == 0), "T2_still_jumps": sj, "T2_mask_jumps": mj,
             "T3": bool(len(t3r) == 4 and t3r["pass"].all()), "T3_dlag": {f"{r.set} {r.kind}": float(r.dlag_med) for r in t3r.itertuples()},
             "T4": bool(t4 is not None and t4["p50"] <= b4["p50"] and t4["p95"] <= b4["p95"]),
             "T4_p50": float(t4["p50"]) if t4 is not None else np.nan, "T4_p95": float(t4["p95"]) if t4 is not None else np.nan,
             "T4_d50": float(t4["d50"]) if t4 is not None else np.nan, "T4_d95": float(t4["d95"]) if t4 is not None else np.nan}
        v["pass_all"] = v["T1"] and v["T2"] and v["T3"] and v["T4"]
        v["failed"] = [k for k in ("T1", "T2", "T3", "T4") if not v[k]]
        ver[m] = v
    dec = decide(gain, ctrl, {k: ver["V6"][k] for k in ("T1", "T2", "T3", "T4")}, acc)
    dec.update({"gain": {f"{L:g}": list(v) for L, v in gain.items()}, "control_gain": {f"{L:g}": list(v) for L, v in ctrl.items()},
                "default_implanted": "V6" if dec["rule"] == 1 else "V3", "universal_baseline": "B2",
                "close_inertial_position_line": dec["rule"] == 2})
    A.update({"GF": GF, "GT": GT, "GA": GA, "Ls": Ls, "gain": gain, "ctrl": ctrl, "T1": T1, "T1X": T1X, "T1A": T1A, "T3": T3, "T2s": T2s,
              "T2m": T2m, "J2m": J2m, "pooled": pooled, "BS": BS, "S3": S3, "S1": S1, "NIS": NIS, "JR": JR, "FBS": FBS, "PD": PD, "P0": P0,
              "HT": HT, "TG": TG, "floor95": floor95, "ver": ver, "dec": dec, "S": S, "Rm_t1": Rm})
    summ = {"decision": dec, "verdict": ver, "tuned": t6, "gapfill": GT[GT.method.isin(["V6", CTRL, "B2", "V1b", "V3"])].to_dict(orient="records"),
            "repro_t1_V3run": A["rep_t1"], "repro_t4_V3run": A["rep_t4"], "repro_still": rep_still, "floor_p95_u3": floor95,
            "repro_tracks": {"V6kernel_noinput_vs_B2_max_in": float(rep_tr.V6kernel_noinput_vs_B2_max_in.max()),
                             "V6kernel_noinput_vs_V3_max_in": float(rep_tr.V6kernel_noinput_vs_V3_max_in.max()),
                             "V3_rebuilt_vs_saved_core_max_in": float(rep_tr.V3_rebuilt_vs_saved_core_max_in.max()),
                             "V3_rebuilt_vs_saved_all_max_in": float(rep_tr.V3_rebuilt_vs_saved_all_max_in.max()),
                             "B2_vs_saved_core_max_in": float(rep_tr.B2_vs_saved_core_max_in.max()),
                             "zupt_equals_V3_saved_all": bool(rep_tr.zupt_equals_V3_saved_mask.all()),
                             "anchors_match_all": bool(rep_tr.anchors_match.all()), "raw_vs_saved_max_in": float(rep_tr.raw_vs_saved_max_in.max()),
                             "n_jobs": int(len(rep_tr))},
            "input_share_gapfill_calm": A["gf_input_share"], "input_share_clean": A["inp_share_clean"], "input_share_t4": A["inp_share_t4"],
            "runtime_aggregate_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=DS._jd), encoding="utf-8")
    A["summary"] = summ
    log_to(fh, f"aggregation done ({time.time() - t0:.0f} s); decision rule {dec['rule']}: {dec['outcome']} ({dec['reason']})")
    return A


def t3_table(EV: pd.DataFrame, sets: list, max_later: float, nb: int, rng) -> pd.DataFrame:
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
                    ev_ = V3.t3_eval(lag, lb, max_later)
                    dl = lag - lb
                    ok = np.isfinite(dl)
                    ch = ok & (np.abs(np.nan_to_num(dl)) > 1e-9)
                    row = {"set": s, "kind": kind, "periods": per, "method": m, "n_events": int(len(dd)), "n_defined": int(np.isfinite(lag).sum()),
                           "lag_med": float(np.nanmedian(lag)) if np.isfinite(lag).any() else np.nan, "n_paired": ev_["n_paired"],
                           "dlag_med": ev_["dlag_med"], "pass": ev_["pass"], "n_later": int((ch & (np.nan_to_num(dl) > 0)).sum()),
                           "n_earlier": int((ch & (np.nan_to_num(dl) < 0)).sum()), "n_later_gt05": int((ok & (np.nan_to_num(dl) > 0.5)).sum())}
                    if ok.sum() >= 5:
                        wb = DS.wmedian_boot(dl[ok], blk[ok], cnt)
                        row.update({"dlag_lo": float(np.nanpercentile(wb[1:], 2.5)), "dlag_hi": float(np.nanpercentile(wb[1:], 97.5)),
                                    "dlag_mean": float(np.mean(dl[ok])), "share_later": float((ch & (np.nan_to_num(dl) > 0)).sum() / ok.sum()),
                                    "share_earlier": float((ch & (np.nan_to_num(dl) < 0)).sum() / ok.sum())})
                    rows.append(row)
    return pd.DataFrame(rows)


# ====================================================================================================== figures
def _eb(v, lo, hi):
    return [[max(np.nan_to_num(v - lo), 0.0)], [max(np.nan_to_num(hi - v), 0.0)]]


def make_figures(A: dict, out: Path, fdir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cfg = A["cfg"]
    cohort = cfg["_cohort"]
    figs = {}
    GT, Ls = A["GT"], A["Ls"]
    # ---- 1. G curves
    fig, ax = plt.subplots(2, 3, figsize=(15, 8.5), sharex=True)
    gsets = [("calm_test", "calm test nights (decision)"), ("rain", "rain nights"), ("tune", "tuning night 09-07")]
    meths = ["B2", "V1b", "V2b", "V3", "V6", "V6_lp15", "V6_lp3", "V6_psifix", "V6_nozupt", CTRL]
    for k, (sn, lab) in enumerate(gsets):
        for m in meths:
            d = GT[(GT.gset == sn) & (GT.method == m)].sort_values("L")
            if not len(d):
                continue
            ax[0, k].plot(d.L, d.rms_pred, "-o", ms=3, color=COL[m], lw=2.0 if m in ("V6", "V3") else 1.0, label=SHORT[m],
                          ls="--" if m == CTRL else "-")
            if m != "V3":
                ax[1, k].errorbar(d.L + (meths.index(m) - 5) * 0.02, 100 * d.gain_vs_V3, yerr=[100 * (d.gain_vs_V3 - d.gain_vs_V3_lo).clip(lower=0),
                                  100 * (d.gain_vs_V3_hi - d.gain_vs_V3).clip(lower=0)], fmt="o", ms=3, capsize=2, color=COL[m], label=SHORT[m])
        ax[0, k].set_title(lab)
        ax[0, k].set_ylabel("RMS_pred (in), fix-noise floor removed")
        ax[1, k].axhline(0, color="k", lw=0.6)
        ax[1, k].axhline(100 * float(cfg["acceptance"]["G_min_gain"]), color="g", ls=":", lw=1)
        ax[1, k].set_ylabel("gain vs V3 (%) [95 % CI]")
        ax[1, k].set_xlabel("hidden block length L (s)")
        for a_ in ax[:, k]:
            a_.grid(alpha=0.3)
    ax[0, 0].legend(fontsize=7, ncol=2)
    fig.suptitle("G: gap-fill prediction RMS on hidden blocks centred on clean IMU-locomoting seconds (10-min block bootstrap)")
    fig.tight_layout()
    f = f"{STEM}_gapfill_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["gapfill"] = f
    # ---- 2. T1
    T1 = A["T1"]
    thr = 100 * float(cfg["acceptance"]["T1_max_abs_rel"])
    order = ["B2", "V1b", "V2b", "V3"] + V6M
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    for k, scale in enumerate((3, 1)):
        pts = [("all", "all clean"), ("gt15", "> 15 in/s"), ("5to15", "5–15 in/s"), ("lt5", "< 5 in/s")]
        for i, m in enumerate(order):
            for j, (band, _) in enumerate(pts):
                r = T1[(T1.scale == scale) & (T1.set == "all") & (T1.band == band) & (T1.track == m)]
                if not len(r):
                    continue
                r = r.iloc[0]
                x = j + (i - (len(order) - 1) / 2) * 0.085
                ax[k].errorbar(x, 100 * r.d95, yerr=_eb(100 * r.d95, 100 * r.d95_lo, 100 * r.d95_hi), fmt="o", ms=4, capsize=2, color=COL[m],
                               label=SHORT[m] if j == 0 else None, mec="k" if m == "V6" else None)
        ax[k].axhspan(-thr, thr, color="g", alpha=0.08)
        ax[k].axhline(0, color="k", lw=0.5)
        ax[k].set_xticks(range(len(pts)))
        ax[k].set_xticklabels([p[1] for p in pts])
        ax[k].set_ylabel(f"d95 (%), {scale}-s scale")
        ax[k].set_title(f"{scale}-s scale{' (T1: first two groups, ± 3 %)' if scale == 3 else ' (reported)'}")
        ax[k].grid(alpha=0.3)
    ax[0].legend(fontsize=7, ncol=2)
    fig.suptitle("T1: track speed vs the clean-WISER reference (six nights; 95 % CIs)")
    fig.tight_layout()
    f = f"{STEM}_t1_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["t1"] = f
    # ---- 3. heading by-product
    PD = A["PD"]
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.8), gridspec_kw={"width_ratios": [2.2, 1]})
    try:
        ex = PD[PD.period.str.startswith("night")].dropna(subset=["drift_deg_per_min"])
        pick = ex.iloc[(ex.n_input_sec).argmax()] if len(ex) else None
        if pick is not None:
            with np.load(out / "tracks" / f"{pick.animal}_{pick.period}.npz") as z:
                sec, psi, sps, st, inp = z["sec"], z["psi_deg"].astype(float), z["spsi_deg"].astype(float), z["state_sec"], z["inp_sec"]
            lo_ = sec[0]
            tm = (sec - lo_) / 3600.0
            ax[0].plot(tm, psi, "-", color=COL["V6"], lw=0.8, label="smoothed ψ")
            ax[0].fill_between(tm, psi - 2 * sps, psi + 2 * sps, color=COL["V6"], alpha=0.2, label="± 2 σ_ψ")
            yl = ax[0].get_ylim()
            ax[0].fill_between(tm, yl[0], yl[1], where=(st == 3) & inp, color="orange", alpha=0.15, step="mid", label="IMU locomoting (input on)")
            ax[0].set_ylim(yl)
            ax[0].set_xlabel("hours from period start")
            ax[0].set_ylabel("ψ (deg): IMU world frame → WISER frame")
            ax[0].set_title(f"ψ(t) {pick.animal} {pick.period}")
            ax[0].legend(fontsize=7)
        nn = PD[PD.period.str.startswith("night")].dropna(subset=["drift_deg_per_min"])
        for i, a in enumerate(sorted(nn.animal.unique())):
            g = nn[nn.animal == a]
            ax[1].scatter(np.full(len(g), i) + np.linspace(-0.2, 0.2, len(g)), g.drift_deg_per_min, s=18, color=COL["V6"])
        ax[1].set_xticks(range(len(nn.animal.unique())))
        ax[1].set_xticklabels(sorted(nn.animal.unique()))
        lo_b, hi_b = cfg["psi_diag"]["gyro_bias_expect_deg_per_min"]
        for sgn in (1, -1):
            ax[1].axhspan(sgn * lo_b, sgn * hi_b, color="r", alpha=0.1)
        ax[1].axhline(0, color="k", lw=0.5)
        ax[1].set_ylabel("ψ drift (deg/min), OLS over input seconds")
        ax[1].set_title("drift per animal-night (red: gyro-bias expectation ±)")
        for a_ in ax:
            a_.grid(alpha=0.3)
    except Exception as e:  # noqa: BLE001
        ax[0].text(0.1, 0.5, f"not available: {e}", transform=ax[0].transAxes)
    fig.tight_layout()
    f = f"{STEM}_heading_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["heading"] = f
    # ---- 4. NIS
    NIS = A["NIS"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    states = ["still", "active", "locomoting", "QC failed"]
    for k, s in enumerate(("calm", "rain")):
        for i, m in enumerate(NIS_M):
            g = NIS[(NIS.method == m) & (NIS.by == "set×imu") & (NIS.set == s)].set_index("imu").reindex(states)
            ax[k].bar(np.arange(4) + (i - 1) * 0.25, g["mean"], 0.25, color=COL[m], edgecolor="k", lw=0.4, label=SHORT[m])
        ax[k].axhline(2.0, color="k", ls=":", lw=1)
        ax[k].set_xticks(range(4))
        ax[k].set_xticklabels(states)
        ax[k].set_yscale("log")
        ax[k].set_title(f"{s}: mean NIS (χ²₂ expectation 2)")
        ax[k].grid(alpha=0.3, axis="y")
    ax[0].set_ylabel("mean NIS (log)")
    ax[0].legend(fontsize=7)
    fig.tight_layout()
    f = f"{STEM}_nis_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["nis"] = f
    return figs


# ====================================================================================================== report
_f = DS._f
_p = DS._p


def _pf(b: bool) -> str:
    return "pass" if b else "**FAIL**"


DEFINITIONS = r"""
## Definitions

All positions are WISER **inches in the unverified offset frame**; only distances, speeds and accelerations (frame-invariant
up to the rotation ψ) are used. Times are field-PC local (EDT). $k$ indexes the fixes of one tag; $\mathbf z_k$ = raw fix
(in, float64 from the fix cache); $t_k=t^{\text{WISER}}_k-\tau^*$ = fix time aligned on the IMU clock ($\tau^*$ = 0.20 / 0.15 /
0.10 / 0.20 / 0.15 s for SF07 / 08 / 09 / 10 / 12); $A_k$ = `anchors_used`; $\sigma^2_a(A)$ = the smoothing pilot's robust
per-axis fix variance for $A$ anchors (B2 table); $s$ = an integer field-PC second with the audit's IMU state
$c(s)\in\{0\ \text{unusable},1\ \text{still},2\ \text{active},3\ \text{locomoting}\}$.

### Input acceleration ($\mathbf a$)
$$ \mathbf a(t)=39.37\cdot\mathrm{LP}_{f_c}\big[(a^{E}_x,a^{E}_y)\big](t),\qquad f_c=2\ \text{Hz} $$
where $a^{E}$ = make_imu `lin_acc_earth_ms2` (Fusion AHRS earth frame NWU, gravity removed, m/s²), $\mathrm{LP}_{f_c}$ = zero-phase
Butterworth order 4 (`sosfiltfilt`) on each contiguous run of valid 50-Hz samples, sampled on the 16-Hz grid by linear
interpolation. **Text:** the head's slow horizontal acceleration in the IMU's own world frame (in/s²; heading arbitrary and
drifting). A 16-Hz sample is **QC-ok** if it lies ≥ 0.5 s inside a run and its second has the audit's `ok`; sensitivities use
$f_c$ = 1.5 / 3 Hz.

### V6 state, dynamics and measurements
$\mathbf x=(\mathbf p,\mathbf v,\mathbf b,\psi)$: position (in), velocity (in/s), IMU-frame acceleration bias (in/s²), heading
offset ψ (rad) from the IMU world frame to the WISER frame. With $R(\psi)=\begin{pmatrix}\cos\psi&-\sin\psi\\ \sin\psi&\cos\psi\end{pmatrix}$,
$M=\mathrm{diag}(1,\pm1)$ (handedness) and the step input $\mathbf u=M\mathbf a(t_{\text{mid}})-\mathbf b$ held over each grid
step $\Delta t$:
$$ \mathbf p'=\mathbf p+\mathbf v\Delta t+\tfrac12\Delta t^2R(\psi)\mathbf u,\quad \mathbf v'=\mathbf v+\Delta tR(\psi)\mathbf u,\quad
\mathbf b'=\varphi\mathbf b,\ \varphi=e^{-\Delta t/\tau_b},\quad \psi'=\psi $$
plus noise: per axis $q\begin{pmatrix}\Delta t^3/3&\Delta t^2/2\\\Delta t^2/2&\Delta t\end{pmatrix}$ on $(p,v)$ with $q=q_a$ on input
steps and $q$ = 3 in²/s³ on fallback steps, $\sigma_b^2(1-\varphi^2)$ on each $b$, $q_\psi\Delta t$ on ψ. Fallback step (no
QC-ok input, margins, a session's first step, a session without a ψ fit): $\mathbf u$ term absent (b and ψ propagate by their
own models). Fixes: $\mathbf z_k=\mathbf p(t_k)+\boldsymbol\varepsilon_k$, $\varepsilon_{k,a}\sim\mathcal N(0,\sigma_a^2(A_k)/w_k)$ —
B2's soft χ² gate in pass 0 ($R$ inflated by $d^2/13.82$ when $d^2=\boldsymbol\nu^\top S^{-1}\boldsymbol\nu>13.82$) and Huber weights
$w_k=\min(1,2.5/m_k)$ in passes 1–2. ZUPT: $0=v_{k,a}+\epsilon$, $\epsilon\sim\mathcal N(0,0.25^2/w^Z_k)$ at fixes in V3's ZUPT
intervals (IMU-still runs ≥ 3 s eroded by 1 s), Huber $w^Z_k=\min(1,2.5\,\sigma_Z/\lVert\hat{\mathbf v}_k\rVert)$. EKF (Jacobians at
the filtered state) + extended RTS smoother; outputs = smoothed $\hat{\mathbf p}(t_k)$. **Text:** where the IMU is usable the
track's velocity is driven by the rotated, bias-corrected head acceleration and corrected by the fixes; elsewhere V6 is B2's
constant-velocity smoother in the same filter.

### Initial ψ (Procrustes) and handedness
With complex accelerations $A_i=a_{x,i}+\mathrm i\,a_{y,i}$ (IMU input low-passed at 1 Hz) and $D_i$ = the V3 track's second
derivative (linear interpolation onto the 16-Hz grid, gaps ≤ 1 s, Butterworth-4 1 Hz, central second difference × 16²) over
the 16-Hz points of the session's IMU-ok locomoting seconds in its first 30 min with such seconds (≥ 60 seconds):
$$ \hat\psi_0=\arg\sum_i\overline{A_i}D_i\ \ (\text{normal}),\qquad \hat\psi_0=\arg\sum_iA_iD_i\ \ (\text{mirrored}),\qquad
\mathrm{RSS}=\sum_i|D_i|^2-\frac{|\sum_i\overline{A'_i}D_i|^2}{\sum_i|A_i|^2} $$
$$ \mathrm{LLR}=n_s\ln\frac{\mathrm{RSS}_{\text{mirror}}}{\mathrm{RSS}_{\text{normal}}} $$
($n_s$ = distinct seconds). **Text:** ψ0 is the rotation that best maps the IMU acceleration onto the track's acceleration;
LLR > 0 favours the normal (right-handed) relation. Initial σ_ψ0 = 20°.

### Gap-fill (G) — primary
Centres $c=s+0.5$ of step-B clean seconds with $c(s)=3$, seeded greedy selection ≥ 13 s apart (so the 3-s blocks are ≥ 10 s apart),
the same centres for every $L\in\{0.5,1,2,3\}$ s; hidden fixes $\mathcal H_L=\{k:t_k\in[c-L/2,c+L/2)\}$; every method rerun once per
$L$ with $\mathcal H_L$ invisible; $e_k=\lVert\hat{\mathbf p}_{-\mathcal H}(t_k)-\mathbf z_k\rVert$,
$$ \mathrm{RMS}_{\text{pred}}=\sqrt{\max\Big(0,\ \overline{e^2}-\overline{\sigma^2_{\text{fix}}}\Big)},\qquad \sigma^2_{\text{fix},k}=\sigma^2_x(A_k)+\sigma^2_y(A_k),
\qquad \text{gain}=1-\frac{\mathrm{RMS}_{\text{pred}}(\text{V6})}{\mathrm{RMS}_{\text{pred}}(\text{V3})} $$
(means over all hidden fixes of the set). **Text:** how far each method's prediction lands from where the WISER fix was, with
the fix's own (still-measured) noise removed; gain > 0 = V6 predicts the hidden positions better than V3. The raw median $e$
is reported too. CI: paired bootstrap of 10-min (animal, period, block) blocks, 1000 draws, 2.5–97.5 %.

### Negative control
V6 with the same animal's input shifted by +3600 s (value at $t+1$ h used at $t$; V6's own availability mask, ZUPT and fallback;
zero input where the shifted sample is not QC-ok; ψ0 refitted on the shifted input). **Invalid** if, at L = 0.5 or 1 s where
gain(V6) > 0, gain(control) ≥ 0.5·gain(V6). **Text:** a gain that a time-scrambled input also produces does not come from the
IMU's information (it would come from the filter structure or tuning).

### T1 — clean speed (as V3)
$d_{95}=Q_{95}\{v^{(m)}_3\}/Q_{95}\{u_3\}-1$ on the paired clean seconds of the six nights, (a) all, (b) $u_3>15$ in/s; pass if both
$|d_{95}|\le3$ %. $u_3$ = clean-WISER 3-s speed (window medians of raw fixes 3 s apart / 3 s), $v^{(m)}_3$ = the same estimator on
the track. **Text:** fast motion is followed neither slower nor faster than the model-free reference.

### T2 — no jumps
$\lVert\hat{\mathbf p}_{k+1}-\hat{\mathbf p}_k\rVert>30$ in with $t_{k+1}-t_k\le0.35$ s; pass if 0 in every primary certified still
segment and 0 over every audit period's analysis mask.

### T3 — transitions not later than B2
S5 events (still run ≥ 10 s ending (onset) / starting (offset) within 60 s of a locomoting second); lag = first (onset) / last
(offset) 0.25-s grid time with the 1-s centred speed ≥ 3 in/s, relative to the still run's end / start; pass if
$\operatorname{median}(\lambda_{V6}-\lambda_{B2})\le+0.5$ s for onsets and offsets, calm and rain.

### T4 — in-place jitter
On V3's in-place set (clean seconds with $c(s)=3$ and $u_3<F_{95}$ = 1.64 in/s, step B's noise-floor p95 on certified stillness),
the S2 1-s speed $v^{S2}_m(s)=\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert$ ($\tilde{\mathbf p}$ = linear interpolation of the
fix-time track); pass if p50 and p95 of V6 ≤ those of B2 (point estimates). **Text:** where the IMU says locomoting but the head
does not translate, V6 must not create speed.

### NIS
$\text{NIS}_k=\boldsymbol\nu_k^\top S_k^{-1}\boldsymbol\nu_k$, $\boldsymbol\nu_k=\mathbf z_k-\hat{\mathbf p}^-_k$, $S_k=P^-_{pp,k}+\mathrm{diag}(\sigma^2_x(A_k),\sigma^2_y(A_k))$
in the final forward pass with the nominal noise; consistent: χ²₂ (mean 2).

### Heading by-product
Per animal-night (per IMU session): smoothed ψ̂ and σ_ψ at the integer seconds; drift = OLS slope of ψ̂ (deg) on time (min) over
input seconds (≥ 600 needed); bout Δψ = difference of the mean ψ̂ between consecutive IMU-locomoting bouts (≥ 3 s, input on);
observable fraction = share of seconds with σ_ψ < 10°. **Text:** whether ψ is pinned down by the data (σ_ψ) and whether its drift
looks like gyro-bias drift (1.6–2.1 °/min expected from the attitude steps).

### Still metrics, S1, S3, block bootstrap
As in the V3 report: on the failure audit's primary certified ≥ 30-s segments (circular for the ZUPT forms), truth = the
segment's median raw fix; fake path $\Pi$ (in/min), per-fix RMS, ≥ 12-in excursions (S3 counts them in the rain set); S1 =
the default-smoother held-out masks ((a) runs of 4–8 fixes, (s) every 5th) with $D=1-\operatorname{med}e^{(m)}/\operatorname{med}e^{(B2)}$
on moving fixes. Block bootstrap: 10-min animal-period blocks with replacement within a set, 1000 draws, paired, percentile CIs.
"""


def render_report(A: dict, out: Path, figs: dict, meta: dict) -> str:  # noqa: C901
    cfg = A["cfg"]
    cohort = cfg["_cohort"]
    acc = cfg["acceptance"]
    ver, dec, t6 = A["ver"], A["dec"], A["t6"]
    GT, GA, T1, T1X, T1A, T3, T2s, T2m, pooled, BS, S3, S1, NIS, JR, FBS, PD, P0, HT, TG = (A[k] for k in (
        "GT", "GA", "T1", "T1X", "T1A", "T3", "T2s", "T2m", "pooled", "BS", "S3", "S1", "NIS", "JR", "FBS", "PD", "P0", "HT", "TG"))
    v = ver["V6"]
    Ls = A["Ls"]

    def g(sn, L, m):
        r = GT[(GT.gset == sn) & (GT.L == L) & (GT.method == m)]
        return r.iloc[0] if len(r) else None

    def gtxt(sn, L, m="V6"):
        r = g(sn, L, m)
        return f"{_p(r.gain_vs_V3, 1)} [{_p(r.gain_vs_V3_lo, 1)}, {_p(r.gain_vs_V3_hi, 1)}]" if r is not None else "–"

    def t1r(m, band="all", scale=3, s="all", tab=None):
        tab = T1 if tab is None else tab
        r = tab[(tab.scale == scale) & (tab.set == s) & (tab.band == band) & (tab.track == m)]
        return r.iloc[0] if len(r) else None

    def t3r(m, s, k, per="all"):
        r = T3[(T3.method == m) & (T3.set == s) & (T3.kind == k) & (T3.periods == per)]
        return r.iloc[0] if len(r) else None

    def pv(s, m, col):
        r = pooled[(pooled.set == s) & (pooled.method == m)]
        return float(r[col].iloc[0]) if len(r) else np.nan

    def nism(m, s, st_):
        r = NIS[(NIS.method == m) & (NIS.by == "set×imu") & (NIS.set == s) & (NIS.imu == st_)]
        return float(r["mean"].iloc[0]) if len(r) else np.nan

    L = []
    L.append(f"# V6 — short-horizon head-IMU / WISER fusion (cohort {cohort})\n")
    L.append(f"Approved by the user 2026-10-03 (\"开始\"). Plan [`{PLAN}`](../../../../{PLAN}) (committed e0252c8 before any V6 number; "
             f"operational Amendment 1 written before any V6 number); driver `{DRIVER}` (`--selftest` ALL PASS); config "
             f"`wiser/configs/wiser_v6_fusion_{cohort}.json` (`tuned` from the tuning night 09-07 only, verdict in `decision`); bulk `{out}`; "
             f"new cache `{cfg['acc16_cache_root']}`; git `{meta['git_commit']}`. Measurement report: no behavioural claim; WISER inch frame "
             f"unverified (only distances, speeds and a relative heading used).\n")
    # ---------------- executive summary
    L.append("## Executive summary\n")
    ex = []
    ex.append(f"**Decision (pre-registered rule {dec['rule']}): {dec['outcome']}.** Reason: {dec['reason']}. B2 stays the universal baseline.")
    cells = []
    for Lx in Ls:
        cells.append(f"L = {Lx:g} s {gtxt('calm_test', Lx)}")
    ex.append("**G — gap-fill gain of V6 over V3 (calm test nights 09-05/06/08 pooled; 95 % CI):** " + "; ".join(cells) + ". "
              "Rain nights: " + "; ".join(f"{Lx:g} s {gtxt('rain', Lx)}" for Lx in Ls) + ". Tuning night 09-07: "
              + "; ".join(f"{Lx:g} s {gtxt('tune', Lx)}" for Lx in Ls) + ".")
    r05, r1 = g("calm_test", 0.5, "V3"), g("calm_test", 1.0, "V3")
    ex.append(f"**RMS_pred (calm test):** V3 {_f(r05.rms_pred, 2)} / {_f(r1.rms_pred, 2)} in at 0.5 / 1 s, V6 {_f(g('calm_test', 0.5, 'V6').rms_pred, 2)} / "
              f"{_f(g('calm_test', 1.0, 'V6').rms_pred, 2)}, B2 {_f(g('calm_test', 0.5, 'B2').rms_pred, 2)} / {_f(g('calm_test', 1.0, 'B2').rms_pred, 2)} "
              f"(fix-noise floor {_f(math.sqrt(r05.mean_s2), 2)} in subtracted in quadrature; n {int(r05.n_fix):,} / {int(r1.n_fix):,} hidden fixes, "
              f"{int(r05.n_centres):,} blocks). Raw median error V3 {_f(r05.med_e, 2)} / {_f(r1.med_e, 2)} in, V6 {_f(g('calm_test', 0.5, 'V6').med_e, 2)} / "
              f"{_f(g('calm_test', 1.0, 'V6').med_e, 2)} in.")
    ex.append(f"**Negative control (+1 h input):** gain vs V3 " + "; ".join(f"{Lx:g} s {gtxt('calm_test', Lx, CTRL)}" for Lx in Ls)
              + f" → {'**INVALIDATES** V6' if any(dec['control_invalid'].values()) else 'does not invalidate V6'}.")
    ra, rf = t1r("V6"), t1r("V6", "gt15")
    r1a, r1f = t1r("V6", "all", 1), t1r("V6", "gt15", 1)
    ex.append(f"**T1 (3-s p95 vs clean WISER, ± 3 %):** {_p(ra.d95, 1)} [{_p(ra.d95_lo, 1)}, {_p(ra.d95_hi, 1)}] all, {_p(rf.d95, 1)} "
              f"[{_p(rf.d95_lo, 1)}, {_p(rf.d95_hi, 1)}] > 15 in/s → {_pf(v['T1'])} (V3 {_p(t1r('V3').d95, 1)} / {_p(t1r('V3', 'gt15').d95, 1)}); "
              f"1-s scale (reported) V6 {_p(r1a.d95, 1)} / {_p(r1f.d95, 1)} vs V3 {_p(t1r('V3', 'all', 1).d95, 1)} / {_p(t1r('V3', 'gt15', 1).d95, 1)}. "
              f"**T2:** {v['T2_still_jumps']} jumps in still segments, {v['T2_mask_jumps']} over the masks → {_pf(v['T2'])}. **T3:** "
              + "; ".join(f"{k} {_f(x, 2)} s" for k, x in v["T3_dlag"].items()) + f" → {_pf(v['T3'])}. **T4 (in-place, 1-s speed vs B2):** "
              f"p50 {_f(v['T4_p50'], 2)} vs {_f(JR[(JR.set == 'all') & (JR.speed == acc['T4_speed']) & (JR.track == 'B2')].p50.iloc[0], 2)} in/s, p95 "
              f"{_f(v['T4_p95'], 2)} vs {_f(JR[(JR.set == 'all') & (JR.speed == acc['T4_speed']) & (JR.track == 'B2')].p95.iloc[0], 2)} "
              f"({_p(v['T4_d50'], 0)} / {_p(v['T4_d95'], 0)}; V3 {_p(ver['V3']['T4_d50'], 0)} / {_p(ver['V3']['T4_d95'], 0)}) → {_pf(v['T4'])}.")
    ex.append(f"**Tuned on 09-07 only:** q_a {t6['q_a']:g} in²/s³, τ_b {t6['tau_b']:g} s (σ_b {t6['sigma_b']:g} in/s²), q_ψ {t6['q_psi_deg2_per_min']:g} (°)²/min"
              f"{' — grid edge(s) hit: ' + ', '.join(t6.get('grid_edges_hit', [])) if t6.get('grid_edges_hit') else ''}; handedness "
              f"{t6.get('handedness_mode', '')}: " + ", ".join(f"{a} {h} (LLR {t6.get('handedness_llr', {}).get(a, np.nan):+.0f})" for a, h in t6["handedness"].items()) + ".")
    nn = PD[PD.period.str.startswith("night")]
    if len(nn):
        ex.append(f"**Heading by-product (nights):** ψ drift {_f(nn.drift_deg_per_min.abs().median(), 2)} °/min median |slope| (range "
                  f"{_f(nn.drift_deg_per_min.min(), 2)} to {_f(nn.drift_deg_per_min.max(), 2)}; gyro-bias expectation 1.6–2.1 °/min), residual about "
                  f"the line {_f(nn.resid_rms_deg.median(), 1)}° RMS; consecutive-bout |Δψ| median {_f(nn.bout_dpsi_med_abs_deg.median(), 1)}°; σ_ψ < 10° in "
                  f"{_p(nn.obs_frac_input.median(), 0, False)} of input seconds and {_p(nn.obs_frac_window.median(), 0, False)} of window seconds (medians over "
                  f"animal-nights).")
    ex.append(f"**NIS (calm mean; still / active / locomoting):** B2 {_f(nism('B2', 'calm', 'still'), 2)} / {_f(nism('B2', 'calm', 'active'), 2)} / "
              f"{_f(nism('B2', 'calm', 'locomoting'), 2)}; V3 {_f(nism('V3', 'calm', 'still'), 2)} / {_f(nism('V3', 'calm', 'active'), 2)} / "
              f"{_f(nism('V3', 'calm', 'locomoting'), 2)}; **V6 {_f(nism('V6', 'calm', 'still'), 2)} / {_f(nism('V6', 'calm', 'active'), 2)} / "
              f"{_f(nism('V6', 'calm', 'locomoting'), 2)}**. **Still (circular):** fake path V3 {_f(pv('calm', 'V3', 'path_in_per_min'))} | "
              f"{_f(pv('rain', 'V3', 'path_in_per_min'))}, V6 {_f(pv('calm', 'V6', 'path_in_per_min'))} | {_f(pv('rain', 'V6', 'path_in_per_min'))} in/min "
              f"(calm | rain). **S3 (rain ≥ 12-in excursions):** raw {int(S3[(S3.set == 'rain') & (S3.method == 'raw')].crazy_n.iloc[0])}, B2 "
              f"{int(S3[(S3.set == 'rain') & (S3.method == 'B2')].crazy_n.iloc[0])}, V3 {int(S3[(S3.set == 'rain') & (S3.method == 'V3')].crazy_n.iloc[0])}, "
              f"V6 {int(S3[(S3.set == 'rain') & (S3.method == 'V6')].crazy_n.iloc[0])}.")
    ex.append("**Sensitivities (never the decision; calm-test gain at 0.5 / 1 s; T1–T4):** " + "; ".join(
        f"{SHORT[m]} {gtxt('calm_test', 0.5, m)} / {gtxt('calm_test', 1.0, m)}, {'T pass' if ver[m]['pass_all'] else 'fails ' + ', '.join(ver[m]['failed'])}"
        for m in SENS) + ".")
    for i, e in enumerate(ex, 1):
        L.append(f"{i}. {e}")
    L.append("")
    # ---------------- decision table
    L.append("## Pre-registered decision\n")
    L.append("| criterion | bound | V6 | outcome |")
    L.append("|---|---|---|---|")
    for Lx in (0.5, 1.0):
        r = g("calm_test", Lx, "V6")
        L.append(f"| G gain vs V3, L = {Lx:g} s, calm test | ≥ 10 % with CI > 0 (rule 1); CI ≤ 0 at both → rule 2 | {gtxt('calm_test', Lx)} | "
                 f"{'≥ 10 %, CI > 0' if dec['big'][Lx] else ('CI > 0, < 10 %' if dec['significant'][Lx] else 'CI includes / below 0')} |")
        L.append(f"| control gain, L = {Lx:g} s | < 50 % of V6's gain | {gtxt('calm_test', Lx, CTRL)} | {'INVALID' if dec['control_invalid'][Lx] else 'ok'} |")
    L.append(f"| T1 3-s p95, all / > 15 in/s | ± 3 % | {_p(ra.d95, 1)} / {_p(rf.d95, 1)} | {_pf(v['T1'])} |")
    L.append(f"| T2 jumps still / masks | 0 / 0 | {v['T2_still_jumps']} / {v['T2_mask_jumps']} | {_pf(v['T2'])} |")
    L.append(f"| T3 median Δ lag vs B2 | ≤ +0.5 s | " + ", ".join(f"{k} {_f(x, 2)}" for k, x in v["T3_dlag"].items()) + f" | {_pf(v['T3'])} |")
    L.append(f"| T4 in-place 1-s speed p50 / p95 vs B2 | ≤ B2 | {_p(v['T4_d50'], 1)} / {_p(v['T4_d95'], 1)} | {_pf(v['T4'])} |")
    L.append(f"| **decision** | rule 1 / 2 / 3 | **rule {dec['rule']}** | **{dec['outcome']}** |")
    L.append("")
    L.append(f"![gapfill](../figures/{figs['gapfill']})\n")
    # ---------------- G detail
    L.append("## 1. G — gap-fill curves (all methods)\n")
    L.append("RMS_pred (in) with the fix-noise floor removed; gain vs V3 [95 % CI]. Same hidden blocks for every method at each L.\n")
    for sn, lab in (("calm_test", "Calm test nights 09-05, 09-06, 09-08 (decision)"), ("rain", "Rain nights 09-03, 09-09 (reported)"),
                    ("tune", "Tuning night 09-07 (reported separately)")):
        L.append(f"**{lab}**\n")
        L.append("| method | " + " | ".join(f"L = {Lx:g} s: RMS_pred; gain vs V3; med e" for Lx in Ls) + " |")
        L.append("|---|" + "---|" * len(Ls))
        for m in cfg["gapfill"]["methods"]:
            cs = []
            for Lx in Ls:
                r = g(sn, Lx, m)
                cs.append(f"{_f(r.rms_pred, 2)}; {_p(r.gain_vs_V3, 1)} [{_p(r.gain_vs_V3_lo, 1)}, {_p(r.gain_vs_V3_hi, 1)}]; {_f(r.med_e, 2)}" if r is not None else "–")
            L.append(f"| {LABEL[m]} | " + " | ".join(cs) + " |")
        r0 = g(sn, Ls[0], "V3")
        L.append(f"\nn hidden fixes per L: " + ", ".join(f"{Lx:g} s {int(g(sn, Lx, 'V3').n_fix):,}" for Lx in Ls) + f"; blocks {int(r0.n_centres):,}; "
                 f"floor √mean σ²_fix {_f(math.sqrt(r0.mean_s2), 2)} in.\n")
    dif = [(Lx, g("calm_test", Lx, "V6").rms_pred - g("calm_test", Lx, "V3").rms_pred) for Lx in Ls]
    cross = [f"{a:g}–{b:g} s" for (a, da), (b, db_) in zip(dif[:-1], dif[1:]) if np.sign(da) != np.sign(db_)]
    L.append(f"**Where V6 − V3 crosses (calm test):** {', '.join(cross) if cross else 'no crossing in 0.5–3 s'} (V6 − V3 RMS_pred: "
             + ", ".join(f"{a:g} s {_f(d_, 2)} in" for a, d_ in dif) + ").\n")
    L.append("Per animal (calm test; gain of V6 vs V3 [CI]):\n")
    L.append("| animal | " + " | ".join(f"L = {Lx:g} s" for Lx in Ls) + " |")
    L.append("|---|" + "---|" * len(Ls))
    for a in sorted(GA.animal.unique()):
        cs = []
        for Lx in Ls:
            r = GA[(GA.gset == "calm_test") & (GA.L == Lx) & (GA.method == "V6") & (GA.animal == a)]
            cs.append(f"{_p(r.gain_vs_V3.iloc[0], 1)} [{_p(r.gain_vs_V3_lo.iloc[0], 1)}, {_p(r.gain_vs_V3_hi.iloc[0], 1)}]" if len(r) else "–")
        L.append(f"| {a} | " + " | ".join(cs) + " |")
    L.append(f"\nShare of hidden calm-test fixes whose step had IMU input in the full-data V6: " + ", ".join(f"{Lx:g} s {_p(A['gf_input_share'][Lx], 1, False)}" for Lx in Ls) + ".\n")
    ID, SS = A["ID"], A["SS"]
    ci_ = ID[ID.period.isin(cfg["gapfill"]["sets"]["calm_test"])]
    L.append("**Post-hoc reading (added after the decision; not part of it).** Why V6 loses: (i) on IMU-ok locomoting seconds of the "
             f"30 animal-nights the 1-Hz IMU input has median magnitude {_f(ID.imu_acc_loco_p50.median(), 1)} in/s² (animal-night range "
             f"{_f(ID.imu_acc_loco_p50.min(), 1)}–{_f(ID.imu_acc_loco_p50.max(), 1)}; at IMU-still seconds {_f(ID.imu_acc_still_p50.median(), 1)}), while the V3 track's "
             f"1-Hz acceleration has {_f(ID.track_acc_loco_p50.median(), 1)} in/s²; a best rotation of the input explains R² = "
             f"{_f(ID.R2_night_normal.median(), 3)} of the track acceleration over a night and {_f(ID.R2_win120_normal_p50.median(), 3)} (median; "
             f"p90 {_f(ID.R2_win120_normal_p90.median(), 3)}) within 120-s windows where the heading drift is negligible (mirrored: "
             f"{_f(ID.R2_win120_mirror_p50.median(), 3)}). The head's 0–2 Hz horizontal specific force during locomotion is therefore mostly not body "
             f"translation (head sweeps and tilt leak during motion — the 0.25 m/s² prior was a whole-night median dominated by rest). (ii) Tuning ran "
             f"to the loosest corner of the grid (q_a = {t6['q_a']:g}, the largest; τ_b = {t6['tau_b']:g} s, the slowest bias), i.e. toward ignoring the input. "
             f"That q_a also acts at in-place seconds (where V3 keeps q = 3 unless it calls them locomoting) → T4. Over all IMU-still seconds V6's 1-s speed "
             f"is ≥ 3 in/s about as often as B2's ({_p(SS[(SS.set == 'all') & (SS.method == 'V6')].share_ge3.iloc[0], 2, False)} vs "
             f"{_p(SS[(SS.set == 'all') & (SS.method == 'B2')].share_ge3.iloc[0], 2, False)}; V3 {_p(SS[(SS.set == 'all') & (SS.method == 'V3')].share_ge3.iloc[0], 2, False)}), "
             f"but not evenly: in still runs ≥ 10 s the share is " + "; ".join(
                 f"{e} from the run edge V6 {_p(A['SSE'][(A['SSE'].edge == e) & (A['SSE'].method == 'V6')].share_ge3.iloc[0], 1, False)} / B2 "
                 f"{_p(A['SSE'][(A['SSE'].edge == e) & (A['SSE'].method == 'B2')].share_ge3.iloc[0], 1, False)} / V3 "
                 f"{_p(A['SSE'][(A['SSE'].edge == e) & (A['SSE'].method == 'V3')].share_ge3.iloc[0], 1, False)}" for e in ("0-1 s", "2-4 s", "5-9 s", ">= 10 s"))
             + f". Motion that V6 carries from the adjacent locomotion bout into the first and last seconds of a still run is what moves the S5 "
             f"lags (T3: offsets later, onsets earlier); a plausible but untested mechanism is the slow bias state (τ_b {t6['tau_b']:g} s) carrying the "
             f"bout's input error across the transition, in both directions through the smoother. (iii) The +1 h control loses less than V6 because at the "
             f"locomoting blocks the shifted input mostly comes from rest (small), whereas the real input there is large and misdirected: the content "
             f"of the input hurts. Per-night values: `tables/posthoc_input_diagnostic.csv`, `tables/posthoc_still_second_speed.csv`, `tables/posthoc_still_edge_speed.csv`.\n")
    # ---------------- tuning / handedness
    L.append("## 2. Tuning (09-07 only) and handedness\n")
    if len(HT):
        L.append("Handedness on the tuning night (full V3 track; Procrustes on the first 30 min of IMU-ok locomoting seconds):\n")
        L.append("| animal | n seconds | ψ0 normal (°) | ψ0 mirrored (°) | RSS mirror / normal | LLR (normal over mirror) | scale normal |")
        L.append("|---|---|---|---|---|---|---|")
        for r in HT[HT.ok.astype(bool)].itertuples():
            L.append(f"| {r.animal} | {int(r.n_sec)} | {_f(np.degrees(r.psi_n), 1)} | {_f(np.degrees(r.psi_m), 1)} | {_f(r.rss_m / r.rss_n, 3)} | {_f(r.llr_normal, 1)} | {_f(r.scale_n, 3)} |")
        L.append("")
    hc = P0[P0.method == "handedness_check"]
    hc = hc[hc.ok.astype(bool)]
    if len(hc):
        L.append(f"Reported on every period with a fit ({len(hc)} session fits): LLR > 0 (normal) in {int((hc.llr_normal > 0).sum())}, median LLR "
                 f"{_f(hc.llr_normal.median(), 1)}, median RSS mirror / normal {_f((hc.rss_m / hc.rss_n).median(), 3)}, median similarity scale "
                 f"{_f(hc.scale_n.median(), 3)} (IMU 1-Hz acceleration vs the V3 track's).\n")
    if len(TG):
        L.append("Tuning grid (pooled RMS_pred at L = 1 s, five animals; V3 = " + f"{_f(TG.rms_pred_V3.iloc[0], 3)} in):\n")
        L.append("| q_a (in²/s³) | τ_b (s) | q_ψ ((°)²/min) | RMS_pred (in) | gain vs V3 |")
        L.append("|---|---|---|---|---|")
        best = TG.rms_pred.idxmin()
        for i, r in TG.iterrows():
            L.append(f"| {r.q_a:g} | {r.tau_b:g} | {r.q_psi_deg2_per_min:g} | {'**' if i == best else ''}{_f(r.rms_pred, 3)}{'**' if i == best else ''} | {_p(r.gain_vs_V3, 1)} |")
        L.append("")
    # ---------------- T1
    L.append("## 3. T1 — clean speed (six nights; as V3)\n")
    L.append("| scale | band | n | " + " | ".join(f"{SHORT[m]} d50; d95" for m in ["V6", "V3", "B2", "V6_lp3", "V6_nozupt"]) + " |")
    L.append("|---|---|---|" + "---|" * 5)
    for scale in (3, 1):
        for band in BANDS:
            r0 = t1r("V6", band, scale)
            if r0 is None:
                continue
            L.append(f"| {scale} s | {BAND_LABEL[band]} | {int(r0.n_sec):,} | " + " | ".join(
                f"{_p(t1r(m, band, scale).d50, 1)}; {_p(t1r(m, band, scale).d95, 1)}" for m in ["V6", "V3", "B2", "V6_lp3", "V6_nozupt"]) + " |")
    L.append("")
    L.append("Without the tuning night (five test nights; reported check): " + "; ".join(
        f"{s}: V6 {_p(t1r('V6', 'all', 3, s, T1X).d95, 1)} / {_p(t1r('V6', 'gt15', 3, s, T1X).d95, 1)}, V3 {_p(t1r('V3', 'all', 3, s, T1X).d95, 1)} / "
        f"{_p(t1r('V3', 'gt15', 3, s, T1X).d95, 1)}" for s in ("all", "calm", "rain") if t1r("V6", "all", 3, s, T1X) is not None) + " (3-s d95 all / > 15 in/s).\n")
    L.append("Per animal (3-s d95 all | > 15 in/s): " + "; ".join(
        f"{a} V6 {_p(T1A[(T1A.animal == a) & (T1A.scale == 3) & (T1A.band == 'all') & (T1A.track == 'V6')].d95.iloc[0], 1)} | "
        f"{_p(T1A[(T1A.animal == a) & (T1A.scale == 3) & (T1A.band == 'gt15') & (T1A.track == 'V6')].d95.iloc[0], 1) if len(T1A[(T1A.animal == a) & (T1A.scale == 3) & (T1A.band == 'gt15') & (T1A.track == 'V6')]) else '–'}"
        for a in sorted(T1A.animal.unique())) + ".\n")
    L.append(f"![T1](../figures/{figs['t1']})\n")
    # ---------------- T2-T4
    L.append("## 4. T2 jumps, T3 transitions, T4 in-place jitter\n")
    L.append("| method | T2 still / mask jumps | T3 calm onset / offset (s) | T3 rain onset / offset (s) | T4 1-s speed p50; p95 vs B2 | T1–T4 |")
    L.append("|---|---|---|---|---|---|")
    for m in ["V6"] + SENS + ["V3", "V1b", "V2b", "B2"]:
        vv = ver[m]
        L.append(f"| {LABEL[m]} | {vv['T2_still_jumps']} / {vv['T2_mask_jumps']} | {_f(vv['T3_dlag'].get('calm onset'), 2)} / {_f(vv['T3_dlag'].get('calm offset'), 2)} | "
                 f"{_f(vv['T3_dlag'].get('rain onset'), 2)} / {_f(vv['T3_dlag'].get('rain offset'), 2)} | {_p(vv['T4_d50'], 1)}; {_p(vv['T4_d95'], 1)} | "
                 f"{'pass' if vv['pass_all'] else 'fail ' + ', '.join(vv['failed'])} |")
    L.append("")
    o_, f_ = t3r("V6", "calm", "onset"), t3r("V6", "calm", "offset")
    if o_ is not None:
        L.append(f"T3 shifted minority (calm, V6 vs B2): onsets {int(o_.n_later)} later / {int(o_.n_earlier)} earlier of {int(o_.n_paired)} (mean Δ "
                 f"{_f(o_.get('dlag_mean'), 2)} s); offsets {int(f_.n_later)} later / {int(f_.n_earlier)} earlier of {int(f_.n_paired)} (mean Δ {_f(f_.get('dlag_mean'), 2)} s).\n")
    jb = JR[(JR.set == "all") & (JR.speed == acc["T4_speed"])].set_index("track")
    L.append(f"T4 set: n {int(jb.loc['B2', 'n_sec']):,} clean seconds (IMU input on in {_p(A['inp_share_t4'], 1, False)} of them); B2 p50 / p95 "
             f"{_f(jb.loc['B2', 'p50'], 2)} / {_f(jb.loc['B2', 'p95'], 2)} in/s; V6 {_f(jb.loc['V6', 'p50'], 2)} / {_f(jb.loc['V6', 'p95'], 2)}; V3 "
             f"{_f(jb.loc['V3', 'p50'], 2)} / {_f(jb.loc['V3', 'p95'], 2)}; raw {_f(jb.loc['raw', 'p50'], 2)} / {_f(jb.loc['raw', 'p95'], 2)}.\n")
    # ---------------- heading
    L.append("## 5. Heading by-product (no claim)\n")
    L.append("| animal | period | session | input s | drift (°/min) | resid RMS (°) | ψ range (°) | bouts | bout \\|Δψ\\| med / p90 (°) | bout rate med (°/min) | σ_ψ < 10° (input / window) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in PD.sort_values(["period", "animal", "session"]).itertuples():
        L.append(f"| {r.animal} | {r.period} | {int(r.session)} | {int(r.n_input_sec):,} | {_f(getattr(r, 'drift_deg_per_min', np.nan), 2)} | "
                 f"{_f(getattr(r, 'resid_rms_deg', np.nan), 1)} | {_f(getattr(r, 'psi_range_deg', np.nan), 0)} | {_f(getattr(r, 'n_bouts', np.nan), 0)} | "
                 f"{_f(getattr(r, 'bout_dpsi_med_abs_deg', np.nan), 1)} / {_f(getattr(r, 'bout_dpsi_p90_abs_deg', np.nan), 1)} | "
                 f"{_f(getattr(r, 'bout_rate_med_abs_deg_per_min', np.nan), 2)} | {_p(r.obs_frac_input, 0, False)} / {_p(r.obs_frac_window, 0, False)} |")
    L.append("")
    nn_ = PD[PD.period.str.startswith("night")]
    if len(nn_):
        L.append(f"**Reading.** On the nights the smoothed ψ is not a clean linear drift: OLS slopes {_f(nn_.drift_deg_per_min.min(), 2)} to "
                 f"{_f(nn_.drift_deg_per_min.max(), 2)} °/min (median |slope| {_f(nn_.drift_deg_per_min.abs().median(), 2)}; expectation from the gyro bias "
                 f"1.6–2.1 °/min) with {_f(nn_.resid_rms_deg.median(), 0)}° RMS (median) about the line and night ranges of "
                 f"{_f(nn_.psi_range_deg.min(), 0)}–{_f(nn_.psi_range_deg.max(), 0)}°, while the filter's σ_ψ stays below 10° nearly all the time — the "
                 f"σ_ψ is inconsistent (overconfident) because the input that is supposed to pin ψ explains almost none of the track's acceleration "
                 f"(post-hoc reading in section 1). So ψ is not observable in the sense the plan needed, and V6 gives no plausible head-direction "
                 f"signal for ephys (no claim either way about the head direction itself).\n")
    L.append(f"![heading](../figures/{figs['heading']})\n")
    # ---------------- NIS / still / S1 / S3 / fallback
    L.append("## 6. NIS, still metrics (circular), S1, S3, fallback\n")
    L.append("| set | IMU state | n | B2 mean (> 95 %) | V3 mean (> 95 %) | V6 mean (> 95 %) |")
    L.append("|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for st_ in ("still", "active", "locomoting", "QC failed"):
            rr = [NIS[(NIS.method == m) & (NIS.by == "set×imu") & (NIS.set == s) & (NIS.imu == st_)] for m in NIS_M]
            if not len(rr[0]):
                continue
            L.append(f"| {s} | {st_} | {int(rr[0].n.iloc[0]):,} | " + " | ".join(f"{_f(x['mean'].iloc[0], 2)} ({_p(x.gt95.iloc[0], 1, False)})" for x in rr) + " |")
    L.append("")
    L.append("At 9 anchors by zone (calm; mean NIS B2 → V3 → V6):\n")
    L.append("| zone | still | active | locomoting |")
    L.append("|---|---|---|---|")
    for zn in ("house", "outside"):
        cells = []
        for st_ in ("still", "active", "locomoting"):
            vals = []
            for m in NIS_M:
                r = NIS[(NIS.method == m) & (NIS.by == "set×abin×zone×imu") & (NIS.set == "calm") & (NIS.abin == "9") & (NIS.zone == zn) & (NIS.imu == st_)]
                vals.append(_f(r["mean"].iloc[0], 2) if len(r) else "–")
            cells.append(" → ".join(vals))
        L.append(f"| {zn} | " + " | ".join(cells) + " |")
    L.append("")
    L.append(f"![nis](../figures/{figs['nis']})\n")
    L.append("Still metrics on the certified ≥ 30-s segments (circular for the ZUPT forms; truth = the segment's median raw fix):\n")
    L.append("| set | method | fake path in/min [CI] | per-fix RMS (in) | 10-s drift med | ≥ 12-in events | jumps |")
    L.append("|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for m in TRACKS:
            r = pooled[(pooled.set == s) & (pooled.method == m)].iloc[0]
            b_ = BS[(BS.set == s) & (BS.method == m) & (BS.metric == "path_rate")].iloc[0]
            L.append(f"| {s} | {LABEL[m]} | {_f(r.path_in_per_min)} [{_f(b_.lo)}, {_f(b_.hi)}] | {_f(r.rms_in, 2)} | {_f(r.drift10_med, 2)} | {int(r.crazy_n)} | {int(r.jumps_n)} |")
    L.append("")
    L.append("S1 held-out fixes (moving subset, scheme (a) / (s); D = 1 − med e / med e(B2)):\n")
    L.append("| set | scheme | n | B2 median (in) | D(V3) [CI] | D(V6) [CI] |")
    L.append("|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for sch in ("a", "s"):
            r = S1[(S1.set == s) & (S1.scheme == sch) & (S1.subset == "moving")]
            if not len(r):
                continue
            r = r.iloc[0]
            L.append(f"| {s} | ({sch}) | {int(r.n):,} | {_f(r.med_B2, 3)} | {_p(r.D_V3, 1)} [{_p(r.D_V3_lo, 1)}, {_p(r.D_V3_hi, 1)}] | "
                     f"{_p(r.D_V6, 1)} [{_p(r.D_V6_lo, 1)}, {_p(r.D_V6_hi, 1)}] |")
    L.append("")
    L.append("S3 (≥ 12-in excursions in the rain set's certified segments): " + ", ".join(
        f"{SHORT[m]} {int(S3[(S3.set == 'rain') & (S3.method == m)].crazy_n.iloc[0])}" for m in TRACKS) + ".\n")
    L.append("IMU input share (V6) — analysis-mask window fixes whose step had input, all grid steps with input, QC-ok 16-Hz window samples:\n")
    L.append("| set | kind | fixes | fix input share | step input share | 16-Hz QC-ok share | sessions without a ψ fit | control: shifted sample missing |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in FBS.itertuples():
        L.append(f"| {r.set} | {r.kind} | {r.n_fix_mask:,} | {_p(r.fix_input_share, 1, False)} | {_p(r.step_input_share, 1, False)} | {_p(r.win16_qc_share, 1, False)} | "
                 f"{r.sessions_fit_failed} | {_p(r.ctrl_shift_missing_share, 1, False)} |")
    L.append("")
    # ---------------- reproduction
    L.append("## 7. Reproduction checks\n")
    rt = A["summary"]["repro_tracks"]
    r1 = A["rep_t1"]
    r4 = A["rep_t4"]
    L.append("| check | result |")
    L.append("|---|---|")
    rtt = A["rep_tr"]
    L.append(f"| V6 kernel without input, q = 3, no ZUPT vs B2 (V3 kernel), every fix | max {rt['V6kernel_noinput_vs_B2_max_in']:.2e} in, median over the "
             f"{len(rtt)} jobs {rtt.V6kernel_noinput_vs_B2_max_in.median():.1e} in; {int((rtt.V6kernel_noinput_vs_B2_max_in > 1e-6).sum())} job(s) above "
             f"the selftest's 1e-6 bound (synthetic: 2e-12), all on multi-session days (floating point after long fix gaps) |")
    L.append(f"| V6 kernel without input, q = 3 × V3's multipliers + V3's ZUPT vs V3 | max {rt['V6kernel_noinput_vs_V3_max_in']:.2e} in |")
    L.append(f"| V3 rebuilt vs the V3 run's saved track (float32) | max {rt['V3_rebuilt_vs_saved_core_max_in']:.2e} in ≥ 60 s from the edges, "
             f"{rt['V3_rebuilt_vs_saved_all_max_in']:.2e} in everywhere; ZUPT mask {'identical' if rt['zupt_equals_V3_saved_all'] else 'DIFFERS'} |")
    L.append(f"| B2 rebuilt vs the audit's saved B2 | max {rt['B2_vs_saved_core_max_in']:.2e} in (core) |")
    L.append(f"| T1 rows of raw / B2 / V1b / V2b / V3 vs the V3 run ({r1['n_rows']} rows) | max \\|Δd50\\| {r1['max_dd50_pp']:.3f} pp, \\|Δd95\\| "
             f"{r1['max_dd95_pp']:.3f} pp → {'pass' if r1['pass'] else '**FAIL**'}; n {'identical' if r1['n_equal_all'] else 'DIFFER'} |")
    L.append(f"| T4 in-place set vs the V3 run | n {r4['n_here']:,} ({r4['n_V3run']:,}); B2 p50 / p95 {_f(r4['B2_p50_here'], 3)} / {_f(r4['B2_p95_here'], 3)} "
             f"({_f(r4['B2_p50_V3run'], 3)} / {_f(r4['B2_p95_V3run'], 3)}); V3 {_f(r4['V3_p50_here'], 3)} / {_f(r4['V3_p95_here'], 3)} "
             f"({_f(r4['V3_p50_V3run'], 3)} / {_f(r4['V3_p95_V3run'], 3)}) in/s |")
    for lab, d_ in A["rep_still"].items():
        L.append(f"| still metrics, {lab} ({d_['n_rows']:,} rows) | max \\|Δ\\| RMS {_f(d_['rms_in'], 5)} in, fake path {_f(d_['path_in_per_min'], 4)} in/min, "
                 f"events {_f(d_['crazy_n'], 0)}, jumps {_f(d_['jumps'], 0)} |")
    L.append(f"| fixes = the audit's | anchors {'all match' if rt['anchors_match_all'] else 'MISMATCH'}; raw max {rt['raw_vs_saved_max_in']:.1e} in; {rt['n_jobs']} jobs |")
    L.append("")
    # ---------------- do not do / definitions / caveats / files
    L.append("## Do not do\n")
    L.append("- Do not read G as accuracy under poor anchors or in the houses: the hidden blocks sit on clean open-field seconds (≥ 8 anchors).")
    L.append("- Do not read ψ as an absolute head direction: it is the offset between two arbitrary frames, valid only while σ_ψ is small; no head-direction claim is made.")
    L.append("- Do not run V6 on tags without a head IMU or through IMU-failed stretches as if it differed from B2 there: it is B2's model by construction.")
    L.append("- Do not promote a sensitivity or tune on a test night after reading this report; any follow-up is a proposal to the user.")
    L.append("- Do not place positions in the paddock: distances are in the unverified WISER inch frame.")
    L.append("")
    L.append(DEFINITIONS)
    L.append("## Caveats\n")
    L.append("- The hidden-fix target carries WISER noise; the floor uses the still-measured anchor table, which understates the noise in motion (NIS 7–10), so every gain is diluted toward 0 (conservative).")
    L.append("- Head ≠ body: the 2-Hz low-pass removes head bob but not slow head sweeps; the Fusion AHRS tilt degrades in shake trains, where the QC fails and V6 falls back.")
    L.append("- ψ0 is fitted over a 30-min window although ψ drifts; the EKF corrects it within the first bouts, but early-night blocks may be served by a worse ψ.")
    L.append("- T1 pools all six nights as V3 did (including the tuning night; the five-test-night values are reported). B2's q and V3's × 10 were tuned on 09-08/09.")
    L.append("- Still metrics are circular for the ZUPT forms; the rain set is three weather episodes; block CIs treat 10-min blocks as independent.")
    L.append("")
    L.append("## Files\n")
    L.append(f"Bulk `{out}`: `tracks/<SFxx>_<period>.npz` (B2, V3, V6, sensitivities, control on nights at every fix; ZUPT and input masks; NIS; "
             f"per-second ψ, σ_ψ, b, input flag, session), `gapfill/` (hidden-fix errors of every method per L), `seconds/`, `speeds/`, `s1/`, `tables/` "
             f"(gapfill, gapfill_by_animal, tuning_grid(_by_animal), handedness_tuning, psi0_fits, psi_diagnostics, t1_speed, "
             f"t1_speed_without_tuning_night, t1_by_animal, t1_repro_V3run, t2_*, t3_*, t4_inplace_speed, nis, still_*, s1_heldout, s3_excursions, "
             f"fallback_*, reproduction_tracks, cache_build), `summary.json`, `input_provenance.json`, logs. New cache `{cfg['acc16_cache_root']}` (+ README). "
             f"Re-aggregate: `python {DRIVER} --report-only <run_dir>`. Pointer: `results/{cohort}/wiser_baseline/reports/run_manifest_v6_fusion_{cohort}.json`.\n")
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
            "audit_run": cfg["audit_run"], "v3_run": cfg["v3_run"], "speed_proxy_run": cfg["speed_proxy_run"], "acc16_cache_root": cfg["acc16_cache_root"],
            "decision_rule": dec["rule"], "default_implanted": dec["default_implanted"]}
    rep.write_text(render_report(A, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_v6_fusion_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    v = ver["V6"]
    cj["decision"] = {
        "rule": dec["rule"], "outcome": dec["outcome"], "reason": dec["reason"], "default_wiser_track_implanted": dec["default_implanted"],
        "universal_baseline": "B2", "close_inertial_position_line": dec["close_inertial_position_line"],
        "gain_calm_test_vs_V3": {k: [round(x, 5) for x in vv] for k, vv in dec["gain"].items()},
        "control_gain_calm_test_vs_V3": {k: [round(x, 5) for x in vv] for k, vv in dec["control_gain"].items()},
        "control_invalid": {f"{k:g}": b for k, b in dec["control_invalid"].items()},
        "T1_d95_3s_all": round(v["T1_d95_all"], 5), "T1_d95_3s_gt15": round(v["T1_d95_gt15"], 5), "T2_jumps_still_mask": [v["T2_still_jumps"], v["T2_mask_jumps"]],
        "T3_dlag_med_s": v["T3_dlag"], "T4_d50_d95_vs_B2": [round(v["T4_d50"], 5), round(v["T4_d95"], 5)], "T_pass": dec["T_pass"],
        "sensitivity_T": {m: ("pass" if ver[m]["pass_all"] else "fail " + ", ".join(ver[m]["failed"])) for m in SENS},
        "run_dir": str(out), "report": f"results/{cohort}/wiser_baseline/reports/{rep.name}",
        "decided_local": pd.Timestamp.now(tz=cfg.get("tz", "America/New_York")).strftime("%Y-%m-%d %H:%M:%S")}
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}\ndecision written into {cp.name}: rule {dec['rule']} ({dec['outcome']})")


# ====================================================================================================== selftest
def _synth(seed: int = 11, dur_s: float = 3600.0, drift_dpm: float = 2.0, mirror: bool = False, psi0_deg: float = 40.0,
           bob_amp: float = 40.0) -> dict:
    """Synthetic head track (50 Hz): still bouts, runs (OU velocity, turns, fast bursts), in-place head bob (> 2 Hz, no
    displacement); synthetic IMU = M R(psi(t))^T a_true + GM bias + slow tilt-leak noise + head bob; WISER-like fixes."""
    rng = np.random.default_rng(seed)
    dg = 0.02
    g = np.arange(int(round((dur_s + 2) / dg))) * dg
    kind = np.zeros(len(g), np.int8)               # 0 still, 1 run, 2 in place
    pos, cyc = 5.0, 0
    while pos < dur_s:
        k = (0, 1, 2, 1, 0, 1)[cyc % 6]
        L_ = {0: rng.uniform(30, 80), 1: rng.uniform(25, 50), 2: rng.uniform(15, 35)}[k]
        kind[(g >= pos) & (g < pos + L_)] = k
        pos += L_
        cyc += 1
    vel = np.zeros((len(g), 2))
    vv = np.zeros(2)
    for k in range(1, len(g)):
        if kind[k] != 1:
            vv = vv * math.exp(-dg / 0.3)          # brief deceleration into stillness / in-place
        else:
            vv = vv - vv / 2.0 * dg + rng.normal(0, 14.0 * math.sqrt(2 * dg / 2.0), 2)
        vel[k] = vv
    from scipy import signal
    sos = signal.butter(2, 1.5, fs=1 / dg, output="sos")
    vel = signal.sosfiltfilt(sos, vel, axis=0)
    vel[kind == 0] *= 0.0
    pg = 300 + np.cumsum(vel, axis=0) * dg
    acc_true = np.gradient(vel, dg, axis=0)
    psi = (psi0_deg + drift_dpm * g / 60.0) * D2R
    c, s = np.cos(psi), np.sin(psi)
    a_imu = np.column_stack([c * acc_true[:, 0] + s * acc_true[:, 1], -s * acc_true[:, 0] + c * acc_true[:, 1]])   # R^T a
    if mirror:
        a_imu[:, 1] *= -1.0
    b = np.zeros((len(g), 2))
    for k in range(1, len(g)):
        b[k] = b[k - 1] * math.exp(-dg / 5.0) + rng.normal(0, 3.0 * math.sqrt(1 - math.exp(-2 * dg / 5.0)), 2)
    leak = signal.sosfiltfilt(signal.butter(2, 0.5, fs=1 / dg, output="sos"), rng.normal(0, 12.0, (len(g), 2)), axis=0)
    bob = np.zeros((len(g), 2))
    ph = rng.uniform(0, 2 * np.pi)
    act = (kind == 2) | (kind == 1)
    bob[act] = bob_amp * np.column_stack([np.sin(2 * np.pi * 6.0 * g + ph), 0.6 * np.cos(2 * np.pi * 7.3 * g)])[act]
    a50 = a_imu + b + leak + bob
    # fixes
    m_ = int(dur_s / 0.18) + 20
    t = np.cumsum(rng.choice([0.134, 0.268], size=m_, p=[0.45, 0.55]) + rng.normal(0, 0.003, m_))
    t = t[t < dur_s]
    n = len(t)
    p = np.column_stack([np.interp(t, g, pg[:, a]) for a in range(2)])
    A = rng.choice([6, 7, 8, 9], size=n, p=[0.05, 0.1, 0.25, 0.6]).astype(float)
    sig = {6: (5.0, 4.5), 7: (2.8, 4.0), 8: (2.0, 3.2), 9: (1.5, 2.6)}
    sw = np.array([sig[int(a)] for a in A])
    z = p + rng.normal(0, 1, (n, 2)) * sw
    oi = rng.random(n) < 0.002
    z[oi] += rng.normal(0, 12, (int(oi.sum()), 2))
    secs = np.arange(0, int(dur_s))
    per = int(round(1.0 / dg))
    kb = kind[:per * len(secs)].reshape(len(secs), per)
    state = np.where((kb == 0).all(axis=1), 1, np.where((kb == 1).all(axis=1), 3, 2)).astype(np.int8)
    inpl = (kb == 2).all(axis=1)
    state[inpl & (secs % 3 == 0)] = 3              # some in-place seconds mislabelled 'locomoting'
    return {"g": g, "pg": pg, "acc_true": acc_true, "psi": psi, "a50": a50, "t": t, "z": z, "p": p, "A": A, "sw": sw, "secs": secs,
            "state": state, "inpl": inpl, "kind": kind, "dg": dg}


def _synth_cache(S: dict, shift_s: float = 0.0) -> dict:
    """The cache builder's filtering path on the synthetic 50-Hz IMU (times in s, grid relative to 0)."""
    u = S["g"] * 1000.0
    valid = np.ones(len(u), bool)
    runs = valid_runs(valid, u, 50.0)
    ys = [lowpass_runs(S["a50"], runs, fc, 50.0, 4) for fc in (1.5, 2.0, 3.0)]
    g16 = np.arange(0, u[-1], GRID_DT_MS)
    pad = 3 * (2 * len(_sos(2.0, 50.0, 4)) + 1)
    outs, q = runs_to_grid(g16, u, ys, runs, 500.0, pad)
    sec = np.floor(g16 / 1000.0).astype(np.int64)
    st = np.where(sec < len(S["state"]), S["state"][np.clip(sec, 0, len(S["state"]) - 1)], 0).astype(np.int8)
    return {"t_ms": g16, "t": g16 / 1000.0, "acc": {"lp15": outs[0], "lp2": outs[1], "lp3": outs[2]}, "qc50": q.copy(), "ok_audit": q.copy(),
            "qc": q.copy(), "state": st, "session": np.zeros(len(g16), np.int64), "sessions": ["synthetic"], "n_sessions": 1}


def selftest() -> int:  # noqa: C901
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    t0 = time.time()
    # 1) low-pass: a 6-Hz bob is removed, 0.5 Hz passes (2-Hz Butterworth-4, zero phase)
    tt = np.arange(0, 60, 0.02)
    x = np.column_stack([np.sin(2 * np.pi * 0.5 * tt), np.sin(2 * np.pi * 6.0 * tt)])
    y = lowpass_runs(x, [(0, len(tt))], 2.0, 50.0, 4)
    mid = slice(500, 2500)
    check("LP 2 Hz: 0.5-Hz amplitude kept (>= 0.97), 6-Hz bob removed (<= 0.02), zero phase",
          np.std(y[mid, 0]) / np.std(x[mid, 0]) >= 0.97 and np.std(y[mid, 1]) / np.std(x[mid, 1]) <= 0.02 and np.corrcoef(y[mid, 0], x[mid, 0])[0, 1] > 0.999)
    # 2) runs split at invalid samples and time gaps
    u = np.r_[np.arange(0, 100) * 20.0, 5000 + np.arange(0, 50) * 20.0]
    vv = np.ones(150, bool)
    vv[30] = False
    rr = valid_runs(vv, u, 50.0)
    check("valid runs split at an invalid sample and at a time gap", rr == [(0, 30), (31, 100), (100, 150)], f"{rr}")
    # 3) block selection
    cand = np.sort(np.random.default_rng(1).choice(np.arange(0, 3000), 900, replace=False)) + 0.5
    cs = select_centres(cand, 13.0, 5)
    cs2 = select_centres(cand, 13.0, 5)
    check("gap-fill centres: >= 13 s apart, all candidates, deterministic with the seed",
          np.all(np.diff(cs) >= 13.0) and np.isin(cs, cand).all() and np.array_equal(cs, cs2) and len(cs) > 100, f"({len(cs)} centres)")
    th = np.array([10.0, 10.24, 10.25, 10.74, 10.76, 20.0])
    hm, ci = hidden_blocks(th, np.array([10.5, 30.0]), 0.5)
    check("hidden block = [c - L/2, c + L/2)", hm.tolist() == [False, False, True, True, False, False] and ci.tolist() == [-1, -1, 0, 0, -1, -1])
    # 4) Procrustes recovers a planted rotation and handedness
    rng = np.random.default_rng(4)
    aa = rng.normal(0, 10, (2000, 2))
    ps_ = 0.7
    R = np.array([[math.cos(ps_), -math.sin(ps_)], [math.sin(ps_), math.cos(ps_)]])
    dd = aa @ R.T * 0.8 + rng.normal(0, 3, (2000, 2))
    pr = procrustes(aa, dd)
    am = aa * np.array([1.0, -1.0])
    prm = procrustes(am, dd)
    check("Procrustes: planted psi 40.1 deg recovered within 1 deg; normal preferred; a mirrored IMU is detected as mirrored",
          abs(pr["psi_n"] - ps_) < D2R and pr["rss_n"] < pr["rss_m"] and prm["rss_m"] < prm["rss_n"] and abs(prm["psi_m"] - ps_) < D2R,
          f"(psi {math.degrees(pr['psi_n']):.2f}, RSS ratio {pr['rss_m'] / pr['rss_n']:.2f})")
    # 5) synthetic track: kernel reproductions
    S = _synth()
    t, z, A_, secs = S["t"], S["z"], S["A"], S["secs"]
    n = len(t)
    tuned = {"B2": {"q": 3.0, "mrej": 1e9}, "huber_k": P.HUBER_K, "gate2": P.GATE2, "n_irls": P.N_IRLS}
    devs = []
    for a_, b_ in C.true_runs(S["state"] == 1):
        if b_ - a_ < 25:
            continue
        m = (t >= a_ + 1) & (t < b_ - 1)
        devs.append(pd.DataFrame({"anchors_used": A_[m], "dx": z[m, 0] - np.median(z[m, 0]), "dy": z[m, 1] - np.median(z[m, 1])}))
    table = P.anchor_sigma_table(pd.concat(devs))
    r2 = P.r2_from_anchors(A_, table)
    vis = np.ones(n, bool)
    none = np.zeros(n, bool)
    st_mid, st_at = P.step_states(t * 1000.0, secs, S["state"])
    loco = V3.loco_steps(st_mid, 3)
    ivs = V1B.eroded(V1B.still_runs(S["state"] == 1, secs), 3, 1)
    zupt = V1B.membership(t, ivs)[1]
    v3cfg = {"v3": {"sigma_zupt_inps": 0.25, "huber_zupt": True, "loco_mult": 10.0}, "variants": {}}
    specs = V3.kf_specs(tuned, v3cfg)
    B2s, _, nisB2, _ = V3.kf_v3(t, z, r2, vis, none, np.ones(n), specs["B2"], tuned)
    V3s, _, nisV3, _ = V3.kf_v3(t, z, r2, vis, zupt, V3.qmult(loco, 10.0), specs["V3"], tuned)
    C16 = _synth_cache(S)
    G = make_grid(t, C16["t"])
    check("merged grid: every fix exactly once, increasing times, 16-Hz points in between",
          np.array_equal(np.sort(G["fix_of"][G["fix_of"] >= 0]), np.arange(n)) and np.all(np.diff(G["tg"]) >= 0) and len(G["tg"]) > 4 * n)
    base_par = {"tau_b": 3.0, "sb2": 4.5 ** 2, "qpsi": 4.0 * D2R * D2R / 60.0, "spsi02": (20 * D2R) ** 2, "couple": True, "mirror": False,
                "sv2": 0.0, "huber_zupt": True, "mrej": 1e9}
    o = kf_v6(G, noinput_inputs(G, np.full(n, 3.0)), z, r2, vis, none, base_par, tuned)
    d0 = float(np.max(np.hypot(*(o["p"] - B2s).T)))
    check("V6 kernel without input, q = 3, no ZUPT = B2 (<= 1e-6 in)", d0 <= 1e-6, f"max {d0:.2e} in")
    o = kf_v6(G, noinput_inputs(G, 3.0 * V3.qmult(loco, 10.0)), z, r2, vis, zupt, {**base_par, "sv2": 0.0625}, tuned)
    d1 = float(np.max(np.hypot(*(o["p"] - V3s).T)))
    check("V6 kernel without input, q = 3 x V3's multipliers + V3's ZUPT = V3 (<= 1e-6 in)", d1 <= 1e-6, f"max {d1:.2e} in")
    dn = float(np.nanmax(np.abs(o["nis"] - nisV3)))
    check("... and its NIS equals V3's", dn <= 1e-6, f"max {dn:.1e}")
    # 6) V6 on the synthetic IMU: psi recovered and drift tracked
    pz = {"lp_hz": 1.0, "window_s": 1800.0, "min_window_loco_s": 60, "min_fit_loco_s": 30, "max_gap_s": 1.0}
    d16 = track_acc16(t, V3s, C16["t"], 1.0, 1.0)
    par = {**base_par, "q_a": 17.5, "q_fb": 3.0, "lp": "lp2", "sv2": 0.0625, "shift_s": 0.0}
    hs = S["secs"][-1] + 1.0
    fits = fit_psi0(C16, C16["acc"]["lp2"], C16["qc50"], d16, hs, pz, False)
    inp = step_inputs(G, C16, par, fits)
    o6 = kf_v6(G, inp, z, r2, vis, zupt, par, tuned, want_cov=True)
    ps_true = np.interp(G["tg"], S["g"], S["psi"])
    err = np.degrees(np.angle(np.exp(1j * (o6["psi"] - ps_true))))
    after = (G["tg"] > 300) & np.isfinite(err)
    m_err = float(np.median(np.abs(err[after])))
    ss = G["tg"][after] / 60.0
    slope = float(np.polyfit(ss, np.degrees(o6["psi"][after]), 1)[0])
    check("V6 recovers psi within 5 deg after the first runs (median |error| after 5 min) and tracks a 2 deg/min drift (slope within +-0.5)",
          m_err <= 5.0 and abs(slope - 2.0) <= 0.5, f"(psi0 fit {math.degrees(fits[0]['psi']):.1f} deg vs true 40-ish; median |err| {m_err:.2f} deg; slope {slope:.2f} deg/min)")
    so = float(np.median(np.degrees(o6["spsi"][after])))
    check("sigma_psi is finite and small during the night (median < 10 deg)", np.isfinite(so) and so < 10.0, f"(median {so:.2f} deg)")
    # 7) gap-fill: V6 beats the CV filters at 0.5-1 s; the shifted control does not
    cand_c = secs[(S["state"] == 3) & ~S["inpl"]] + 0.5
    cand_c = cand_c[(cand_c > 60) & (cand_c < hs - 60)]
    cents = select_centres(cand_c, 13.0, 7)
    res = {}
    for L in (0.5, 1.0):
        hid, _ = hidden_blocks(t, cents, L)
        vh = ~hid
        P3h, _, _, _ = V3.kf_v3(t, z, r2, vh, zupt, V3.qmult(loco, 10.0), specs["V3"], tuned)
        PBh, _, _, _ = V3.kf_v3(t, z, r2, vh, none, np.ones(n), specs["B2"], tuned)
        d16h = track_acc16(t, P3h, C16["t"], 1.0, 1.0)
        f6 = fit_psi0(C16, C16["acc"]["lp2"], C16["qc50"], d16h, hs, pz, False)
        P6h = kf_v6(G, step_inputs(G, C16, par, f6), z, r2, vh, zupt, par, tuned)["p"]
        sh = int(round(900.0 * 16))
        pc = {**par, "shift_s": 900.0}
        fc = variant_fits(C16, pc, d16h, hs, pz)
        Pch = kf_v6(G, step_inputs(G, C16, pc, fc, sh), z, r2, vh, zupt, pc, tuned)["p"]
        e = {m: np.hypot(*(pp_[hid] - S["p"][hid]).T) for m, pp_ in (("B2", PBh), ("V3", P3h), ("V6", P6h), ("ctrl", Pch))}
        rms = {m: float(np.sqrt(np.mean(v ** 2))) for m, v in e.items()}
        res[L] = rms
    g05 = 1 - res[0.5]["V6"] / res[0.5]["V3"]
    g1 = 1 - res[1.0]["V6"] / res[1.0]["V3"]
    gc05 = 1 - res[0.5]["ctrl"] / res[0.5]["V3"]
    gc1 = 1 - res[1.0]["ctrl"] / res[1.0]["V3"]
    check("gap-fill (true positions): V6 error below V3's and B2's at L = 0.5 and 1 s",
          res[0.5]["V6"] < res[0.5]["V3"] and res[1.0]["V6"] < res[1.0]["V3"] and res[0.5]["V6"] < res[0.5]["B2"] and res[1.0]["V6"] < res[1.0]["B2"],
          f"(gain vs V3 {100 * g05:.1f} % / {100 * g1:.1f} %; RMS V6 {res[1.0]['V6']:.2f}, V3 {res[1.0]['V3']:.2f}, B2 {res[1.0]['B2']:.2f} in at 1 s)")
    check("the time-shifted control recovers < 50 % of V6's gain (no information in a scrambled input)",
          gc05 < 0.5 * g05 and gc1 < 0.5 * g1, f"(control gain {100 * gc05:.1f} % / {100 * gc1:.1f} %)")
    # 8) in-place head bob does not create speed: (a) V6 with and without the > 2-Hz bob gives the same in-place 1-s speed;
    #    (b) with q_a = B2's q the input adds no in-place speed beyond B2's (the q_a effect itself is T4's job on real data)
    Snb = _synth(bob_amp=0.0)
    Cnb = _synth_cache(Snb)
    onb = kf_v6(G, step_inputs(G, Cnb, par, fit_psi0(Cnb, Cnb["acc"]["lp2"], Cnb["qc50"], d16, hs, pz, False)), z, r2, vis, zupt, par, tuned)
    p3 = {**par, "q_a": 3.0}
    oq3 = kf_v6(G, step_inputs(G, C16, p3, fits), z, r2, vis, zupt, p3, tuned)
    vs = {m: DS.second_speeds(t, pp_, secs, 1.0) for m, pp_ in (("B2", B2s), ("V3", V3s), ("V6", o6["p"]), ("V6_nobob", onb["p"]),
                                                               ("V6_q3", oq3["p"]), ("truth", S["p"]))}
    ip = S["inpl"][:len(vs["B2"])] & np.isfinite(vs["B2"]) & np.isfinite(vs["V6"])
    med = {m: float(np.median(v[ip])) for m, v in vs.items()}
    check("in-place bob (> 2 Hz, no displacement) does not create speed: V6 in-place 1-s speed p50 with vs without the bob within 10 %",
          abs(med["V6"] / med["V6_nobob"] - 1.0) <= 0.10, f"(p50 V6 {med['V6']:.2f} with the bob, {med['V6_nobob']:.2f} without, truth {med['truth']:.2f} in/s)")
    print(f"   info (not a check; T4 judges this on field data): in-place 1-s speed p50 B2 {med['B2']:.2f}, V3 {med['V3']:.2f}, V6 q_a 17.5 "
          f"{med['V6']:.2f}, V6 q_a 3 {med['V6_q3']:.2f} in/s - the bias / psi states loosen the velocity beyond q_a", flush=True)
    # 9) evaluators
    rngc = np.random.default_rng(9)
    nn_ = 6000
    dfx = pd.DataFrame({"animal": "SFx", "period": "night", "blk10": rngc.integers(0, 40, nn_), "c": np.arange(nn_) // 3,
                        "s2": np.full(nn_, 9.0)})
    noise = rngc.normal(0, 1, (nn_, 2)) * math.sqrt(4.5)
    for m, pr_ in (("V3", 4.0), ("V6", 3.0), ("B2", 5.0)):
        dfx[f"e_{m}"] = np.hypot(*(noise + rngc.normal(0, 1, (nn_, 2)) * pr_ / math.sqrt(2)).T)
    gr = pd.DataFrame(g_rows(dfx, ["V3", "V6", "B2"], 300, np.random.default_rng(2), {}))
    rv6 = gr[gr.method == "V6"].iloc[0]
    rv3 = gr[gr.method == "V3"].iloc[0]
    check("G evaluator: RMS_pred recovers planted prediction RMS (V3 4, V6 3 in) within 5 %; gain 25 % with a CI above 0",
          abs(rv3.rms_pred - 4.0) / 4.0 < 0.05 and abs(rv6.rms_pred - 3.0) / 3.0 < 0.05 and abs(rv6.gain_vs_V3 - 0.25) < 0.04 and rv6.gain_vs_V3_lo > 0,
          f"(RMS {rv3.rms_pred:.2f} / {rv6.rms_pred:.2f}, gain {100 * rv6.gain_vs_V3:.1f} % [{100 * rv6.gain_vs_V3_lo:.1f}, {100 * rv6.gain_vs_V3_hi:.1f}])")
    accd = {"G_decide_L": [0.5, 1.0], "control_max_recovery": 0.5, "G_min_gain": 0.10}
    tp = {"T1": True, "T2": True, "T3": True, "T4": True}
    d_1 = decide({0.5: (0.15, 0.05, 0.2), 1.0: (0.05, -0.01, 0.1)}, {0.5: (0.01, -0.02, 0.03), 1.0: (0.0, -0.01, 0.01)}, tp, accd)
    d_c = decide({0.5: (0.15, 0.05, 0.2), 1.0: (0.05, -0.01, 0.1)}, {0.5: (0.09, 0.0, 0.1), 1.0: (0.0, -0.01, 0.01)}, tp, accd)
    d_2 = decide({0.5: (0.02, -0.01, 0.05), 1.0: (0.01, -0.02, 0.04)}, {0.5: (0.0, -0.1, 0.1), 1.0: (0.0, -0.1, 0.1)}, tp, accd)
    d_3 = decide({0.5: (0.06, 0.01, 0.1), 1.0: (0.04, 0.0, 0.08)}, {0.5: (0.0, -0.1, 0.1), 1.0: (0.0, -0.1, 0.1)}, tp, accd)
    d_3t = decide({0.5: (0.15, 0.05, 0.2), 1.0: (0.05, -0.01, 0.1)}, {0.5: (0.01, -0.02, 0.03), 1.0: (0.0, -0.01, 0.01)}, {**tp, "T4": False}, accd)
    check("decision rule on planted cases: replace (1), control invalid (2), not significant (2), small gain (3), T failed (3)",
          d_1["rule"] == 1 and d_c["rule"] == 2 and d_2["rule"] == 2 and d_3["rule"] == 3 and d_3t["rule"] == 3,
          f"({d_1['rule']}, {d_c['rule']}, {d_2['rule']}, {d_3['rule']}, {d_3t['rule']})")
    vb = np.abs(rngc.normal(1.0, 0.5, 4000))
    check("T4 evaluator: a smoother track passes, a 10 % faster one fails", t4_eval(0.9 * vb, vb)["pass"] and not t4_eval(1.1 * vb, vb)["pass"])
    rc = {"u3_offset_s": 1.5, "u3_half_s": 0.5, "u1_offset_s": 0.5, "u1_half_s": 0.375, "min_fix": 3}
    u3r, _ = SP.track_speeds(t, z, secs, rc)
    damp = z.mean(axis=0) + 0.9 * (z - z.mean(axis=0))
    v_d, _ = SP.track_speeds(t, damp, secs, rc)
    check("T1 evaluator (V3's): the reference passes, a x0.9 track fails", V3.t1_eval(u3r, u3r, 15.0, 0.03)["pass"] and not V3.t1_eval(u3r, v_d, 15.0, 0.03)["pass"])
    pj = o6["p"].copy()
    kj = int(np.flatnonzero(np.diff(t) <= 0.2)[100])
    pj[kj + 1] += np.array([40.0, 0.0])
    check("T2 evaluator: V6 has no jump; a planted 40-in step is two jumps", V3.t2_eval(t, o6["p"], 30.0, 0.35)["pass"] and V3.t2_eval(t, pj, 30.0, 0.35)["jumps"] == 2)
    # 10) session reset: two sessions with different heading offsets
    C2 = {**C16, "session": np.where(C16["t"] < 1800, 0, 1).astype(np.int64), "n_sessions": 2, "sessions": ["a", "b"]}
    S2 = _synth(seed=11)
    jump = 1800.0
    rot = np.where(S2["g"] >= jump, 70.0 * D2R, 0.0)        # session b's IMU frame rotated by a further 70 deg
    c_, s_ = np.cos(rot), np.sin(rot)
    a2 = S2["a50"].copy()
    S2["a50"] = np.column_stack([c_ * a2[:, 0] + s_ * a2[:, 1], -s_ * a2[:, 0] + c_ * a2[:, 1]])
    C2b = _synth_cache(S2)
    C2 = {**C2b, "session": np.where(C2b["t"] < jump, 0, 1).astype(np.int64), "n_sessions": 2, "sessions": ["a", "b"]}
    f2 = fit_psi0(C2, C2["acc"]["lp2"], C2["qc50"], d16, hs, pz, False)
    inp2 = step_inputs(G, C2, par, f2)
    o2 = kf_v6(G, inp2, z, r2, vis, zupt, par, tuned, want_cov=True)
    ps2 = ps_true + np.where(G["tg"] >= jump, 70.0 * D2R, 0.0)
    e2 = np.degrees(np.angle(np.exp(1j * (o2["psi"] - ps2))))
    sel2 = ((G["tg"] > 300) & (G["tg"] < jump - 60)) | (G["tg"] > jump + 300)
    check("IMU session change: one reset at the boundary, psi re-fitted per session, both sessions recovered (median |err| <= 5 deg)",
          int(inp2["rst"].sum()) == 1 and abs(G["tg"][np.flatnonzero(inp2["rst"])[0]] - jump) < 0.2 and float(np.median(np.abs(e2[sel2]))) <= 5.0,
          f"(resets {int(inp2['rst'].sum())}, psi0 {math.degrees(f2[0]['psi']):.1f} / {math.degrees(f2[1]['psi']):.1f} deg, median |err| {np.median(np.abs(e2[sel2])):.2f} deg)")
    print(f"numba: {P.HAVE_NUMBA}; selftest {time.time() - t0:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--report-only", default=None, help="existing run dir: re-aggregate and re-render from its saved files")
    ap.add_argument("--skip-tune", action="store_true", help="reuse the config's tuned block instead of re-tuning on the tuning night")
    ap.add_argument("--rebuild-cache", action="store_true", help="rewrite the 16-Hz input cache")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    cfg = load_cfg(a.cohort, a.config)
    out = Path(a.report_only) if a.report_only else run_compute(cfg, a.workers or int(cfg.get("workers", 16)), a.skip_tune, a.rebuild_cache)
    cfg = load_cfg(a.cohort, a.config)
    fh = open(out / "log_report.txt", "a", encoding="utf-8")
    A = aggregate(out, cfg, fh)
    publish(A, out, fh)
    fh.close()


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")
    main()
